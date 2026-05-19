"""Autonomous orchestrator — runs the full daily cycle.

1. Read yesterday's report
2. Adjust keyword priorities
3. Run discovery
4. Enrich candidates
5. Build approved shelf
6. Generate 24h lineup
7. Emit Media IR
8. Hand off to existing streaming MVP
9. Generate autonomy report

Restart-safe: each step checks current state before proceeding.
"""

from datetime import date, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.acquisition.enums import (
    CandidateRightsStatus,
    DiscoveryStatus,
    RetrievalStatus,
)
from voulezvous.acquisition.models import (
    AutonomyReport,
    CandidateAsset,
    SearchKeyword,
)
from voulezvous.acquisition.workers.curator import generate_lineup, llm_polish_lineup
from voulezvous.acquisition.workers.discovery import run_discovery_simulated
from voulezvous.acquisition.workers.enrichment import run_enrichment
from voulezvous.acquisition.workers.media_ir import compile_media_ir
from voulezvous.acquisition.workers.reporter import generate_report

logger = structlog.get_logger()


async def _adjust_keyword_priorities(
    db: AsyncSession, yesterday_report: AutonomyReport | None,
) -> dict:
    """Adjust keyword weights based on yesterday's report signals."""
    adjustments = []

    if not yesterday_report or not yesterday_report.summary:
        return {"adjustments": [], "reason": "No yesterday report"}

    keyword_effectiveness = yesterday_report.summary.get("keyword_effectiveness", [])

    for kw_stat in keyword_effectiveness:
        keyword_text = kw_stat.get("keyword", "")
        found = kw_stat.get("candidates_found", 0)
        accepted = kw_stat.get("accepted", 0)

        kw = (await db.execute(
            select(SearchKeyword).where(
                SearchKeyword.keyword == keyword_text,
                SearchKeyword.active.is_(True),
            )
        )).scalar_one_or_none()
        if not kw:
            continue

        old_weight = float(kw.weight)

        # Boost keywords that find accepted content
        if accepted > 0:
            kw.weight = min(old_weight * 1.2, 5.0)
            adjustments.append({
                "keyword": keyword_text,
                "old_weight": old_weight,
                "new_weight": float(kw.weight),
                "reason": f"Found {accepted} accepted",
            })
        # Reduce keywords that find nothing
        elif found == 0:
            kw.weight = max(old_weight * 0.7, 0.1)
            adjustments.append({
                "keyword": keyword_text,
                "old_weight": old_weight,
                "new_weight": float(kw.weight),
                "reason": "Found nothing",
            })

    await db.commit()
    return {"adjustments": adjustments}


async def _auto_approve_candidates(db: AsyncSession) -> int:
    """Auto-approve candidates that have authorized retrieval and pass quality checks.

    This simulates the operator approval step for demo/automated runs.
    In production, candidates would need explicit operator approval.
    """
    candidates = (await db.execute(
        select(CandidateAsset).where(
            CandidateAsset.rights_status == CandidateRightsStatus.pending_review,
            CandidateAsset.retrieval_status.in_([
                RetrievalStatus.authorized_direct,
                RetrievalStatus.authorized_official,
            ]),
            CandidateAsset.duration_sec.isnot(None),
            CandidateAsset.duration_sec > 60,
        )
    )).scalars().all()

    for c in candidates:
        c.rights_status = CandidateRightsStatus.approved_for_stream
        c.discovery_status = DiscoveryStatus.accepted

    await db.flush()
    logger.info("auto_approved_candidates", count=len(candidates))
    return len(candidates)


async def run_daily_orchestration(db: AsyncSession, target_date: date | None = None) -> dict:
    """Run the full autonomous daily cycle."""
    target_date = target_date or date.today()
    yesterday = target_date - timedelta(days=1)

    steps_completed = []
    errors = []

    # Step 1: Read yesterday's report
    yesterday_report = (await db.execute(
        select(AutonomyReport).where(AutonomyReport.report_date == yesterday)
    )).scalar_one_or_none()
    steps_completed.append("read_yesterday_report")
    logger.info("orchestrator_step", step="read_yesterday_report",
                has_report=yesterday_report is not None)

    # Step 2: Adjust keyword priorities
    try:
        adjustments = await _adjust_keyword_priorities(db, yesterday_report)
        steps_completed.append("adjust_keywords")
        logger.info("orchestrator_step", step="adjust_keywords",
                    adjustments=len(adjustments.get("adjustments", [])))
    except Exception as e:
        errors.append({"step": "adjust_keywords", "error": str(e)})
        logger.error("orchestrator_step_failed", step="adjust_keywords", error=str(e))

    # Step 3: Run discovery (simulated — use run_discovery for real browser runs)
    try:
        discovery_run = await run_discovery_simulated(db, run_date=target_date)
        steps_completed.append("discovery")
        logger.info("orchestrator_step", step="discovery",
                    found=discovery_run.output_summary.get("total_found", 0))
    except Exception as e:
        errors.append({"step": "discovery", "error": str(e)})
        logger.error("orchestrator_step_failed", step="discovery", error=str(e))

    # Step 4: Enrich candidates
    try:
        enrichment_result = await run_enrichment(db)
        steps_completed.append("enrichment")
        logger.info("orchestrator_step", step="enrichment",
                    enriched=enrichment_result.get("enriched", 0))
    except Exception as e:
        errors.append({"step": "enrichment", "error": str(e)})
        logger.error("orchestrator_step_failed", step="enrichment", error=str(e))

    # Step 5: Auto-approve eligible candidates
    try:
        approved_count = await _auto_approve_candidates(db)
        steps_completed.append("auto_approve")
        logger.info("orchestrator_step", step="auto_approve", approved=approved_count)
    except Exception as e:
        errors.append({"step": "auto_approve", "error": str(e)})
        logger.error("orchestrator_step_failed", step="auto_approve", error=str(e))

    # Step 6: Generate 24h lineup
    lineup = None
    try:
        lineup = await generate_lineup(db, lineup_date=target_date)
        steps_completed.append("lineup_generation")
        logger.info("orchestrator_step", step="lineup_generation",
                    items=lineup.context_summary.get("total_items", 0))
    except ValueError as e:
        errors.append({"step": "lineup_generation", "error": str(e)})
        logger.warning("orchestrator_step_skipped", step="lineup_generation", reason=str(e))
    except Exception as e:
        errors.append({"step": "lineup_generation", "error": str(e)})
        logger.error("orchestrator_step_failed", step="lineup_generation", error=str(e))

    # Step 7: LLM polish (optional, non-blocking)
    if lineup:
        try:
            await llm_polish_lineup(db, lineup.id)
            steps_completed.append("llm_polish")
        except Exception as e:
            errors.append({"step": "llm_polish", "error": str(e)})

    # Step 8: Compile Media IR
    if lineup:
        try:
            ir_result = await compile_media_ir(db, lineup.id)
            steps_completed.append("media_ir_compile")
            logger.info("orchestrator_step", step="media_ir_compile",
                        compiled=ir_result.get("compiled", 0))
        except Exception as e:
            errors.append({"step": "media_ir_compile", "error": str(e)})
            logger.error("orchestrator_step_failed", step="media_ir_compile", error=str(e))

    # Step 9: Generate autonomy report
    try:
        await generate_report(db, report_date=target_date)
        steps_completed.append("report_generation")
        logger.info("orchestrator_step", step="report_generation")
    except Exception as e:
        errors.append({"step": "report_generation", "error": str(e)})
        logger.error("orchestrator_step_failed", step="report_generation", error=str(e))

    result = {
        "target_date": str(target_date),
        "steps_completed": steps_completed,
        "errors": errors,
        "success": len(errors) == 0,
    }

    logger.info("daily_orchestration_complete", **result)
    return result
