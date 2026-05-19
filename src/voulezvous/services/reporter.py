from datetime import date, datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.models.enums import (
    EventType,
    PrepStatus,
    ReportStatus,
    RightsStatus,
    StreamItemStatus,
)
from voulezvous.models.tables import (
    DailyReport,
    LibraryAsset,
    StreamEvent,
    StreamPlan,
    StreamPlanItem,
)

logger = structlog.get_logger()


async def generate_daily_report(db: AsyncSession, report_date: date) -> DailyReport:
    day_start = datetime(report_date.year, report_date.month, report_date.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    # Plans for this date
    q_plans = select(StreamPlan).where(StreamPlan.plan_date == report_date)
    plans = list((await db.execute(q_plans)).scalars().all())
    plan_ids = [p.id for p in plans]

    # Items
    q_items = select(StreamPlanItem).where(StreamPlanItem.stream_plan_id.in_(plan_ids)) if plan_ids else select(StreamPlanItem).where(False)  # noqa: E501
    items = list((await db.execute(q_items)).scalars().all())

    completed = [i for i in items if i.stream_status == StreamItemStatus.completed]
    failed = [i for i in items if i.stream_status == StreamItemStatus.failed]
    skipped = [i for i in items if i.stream_status == StreamItemStatus.skipped]
    prep_failed = [i for i in items if i.prep_status == PrepStatus.failed]

    # Planned hours
    planned_sec = sum(i.target_duration_sec or 0 for i in items)
    streamed_sec = sum(
        int((i.actual_end_at - i.actual_start_at).total_seconds())
        for i in completed
        if i.actual_start_at and i.actual_end_at
    )

    # Fallback events
    q_fb = (
        select(func.count())
        .select_from(StreamEvent)
        .where(StreamEvent.event_type == EventType.fallback_started)
        .where(StreamEvent.occurred_at >= day_start)
        .where(StreamEvent.occurred_at < day_end)
    )
    fallback_count = (await db.execute(q_fb)).scalar() or 0

    # Top repeated assets
    asset_counts: dict[str, int] = {}
    for i in items:
        aid = str(i.video_asset_id)
        asset_counts[aid] = asset_counts.get(aid, 0) + 1
    top_repeated = sorted(asset_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    # Blocked assets count
    q_blocked = (
        select(func.count())
        .select_from(LibraryAsset)
        .where(LibraryAsset.rights_status == RightsStatus.blocked)
    )
    blocked_count = (await db.execute(q_blocked)).scalar() or 0

    # Pending review count
    q_pending = (
        select(func.count())
        .select_from(LibraryAsset)
        .where(LibraryAsset.rights_status == RightsStatus.pending_review)
    )
    pending_count = (await db.execute(q_pending)).scalar() or 0

    # Build suggestions
    suggestions = []
    if fallback_count > 3:
        suggestions.append("Too much fallback usage — prepare more content ahead.")
    if len(prep_failed) > 0:
        suggestions.append(f"{len(prep_failed)} prep failures — check source URLs and formats.")
    if len(failed) > 0:
        suggestions.append(f"{len(failed)} stream failures — review error logs.")
    if top_repeated and top_repeated[0][1] > 5:
        aid, cnt = top_repeated[0]
        suggestions.append(f"Asset {aid} repeated {cnt} times — add variety.")
    if pending_count > 0:
        suggestions.append(f"{pending_count} assets still pending rights review.")
    if not suggestions:
        suggestions.append("All clear — stream day went smoothly.")

    summary = {
        "planned_hours": round(planned_sec / 3600, 2),
        "streamed_hours": round(streamed_sec / 3600, 2),
        "completed_items": len(completed),
        "failed_items": len(failed),
        "skipped_items": len(skipped),
        "prep_failures": len(prep_failed),
        "fallback_events": fallback_count,
        "top_repeated_assets": [{"asset_id": a, "count": c} for a, c in top_repeated],
        "blocked_assets": blocked_count,
        "pending_review_assets": pending_count,
        "suggestions": suggestions,
    }

    md = _build_markdown(report_date, summary)

    # Upsert report
    q_existing = select(DailyReport).where(DailyReport.report_date == report_date)
    existing = (await db.execute(q_existing)).scalar_one_or_none()
    if existing:
        existing.status = ReportStatus.generated
        existing.summary = summary
        existing.markdown_text = md
        report = existing
    else:
        report = DailyReport(
            report_date=report_date,
            status=ReportStatus.generated,
            summary=summary,
            markdown_text=md,
        )
        db.add(report)

    await db.commit()
    await db.refresh(report)

    logger.info("report_generated", date=str(report_date), summary=summary)
    return report


def _build_markdown(report_date: date, summary: dict) -> str:
    lines = [
        f"# Daily Report — {report_date}",
        "",
        "## Summary",
        f"- **Planned hours:** {summary['planned_hours']}",
        f"- **Streamed hours:** {summary['streamed_hours']}",
        f"- **Completed items:** {summary['completed_items']}",
        f"- **Failed items:** {summary['failed_items']}",
        f"- **Skipped items:** {summary['skipped_items']}",
        f"- **Prep failures:** {summary['prep_failures']}",
        f"- **Fallback events:** {summary['fallback_events']}",
        f"- **Blocked assets:** {summary['blocked_assets']}",
        f"- **Pending review:** {summary['pending_review_assets']}",
        "",
        "## Top Repeated Assets",
    ]
    for entry in summary.get("top_repeated_assets", []):
        lines.append(f"- {entry['asset_id']}: {entry['count']} times")
    lines += [
        "",
        "## Suggestions",
    ]
    for s in summary.get("suggestions", []):
        lines.append(f"- {s}")
    lines.append("")
    return "\n".join(lines)
