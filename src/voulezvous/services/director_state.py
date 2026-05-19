"""Compact state snapshot for the Director LLM.

The whole point is to fit in a small prompt: ~3KB, no prose, only facts
the model can act on with the bounded tool grammar.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.acquisition.enums import (
    CandidateRightsStatus,
    DiscoveryStatus,
    RetrievalStatus,
)
from voulezvous.acquisition.models import (
    CandidateAsset,
    DiscoveryRun,
    DomainPolicy,
    SearchKeyword,
)
from voulezvous.models.enums import PlanStatus, PrepStatus, RightsStatus, StreamItemStatus
from voulezvous.models.tables import (
    DirectorAction,
    LibraryAsset,
    StreamControl,
    StreamPlan,
    StreamPlanItem,
)


async def compact_state(db: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)

    # ── Stream control ────────────────────────────────────────────────────────
    control = await db.get(StreamControl, "main")
    current_item = None
    if control and control.current_item_id:
        item = await db.get(StreamPlanItem, control.current_item_id)
        if item:
            video = await db.get(LibraryAsset, item.video_asset_id)
            current_item = {
                "title": video.title if video else None,
                "duration_sec": item.target_duration_sec,
            }

    # Queued seconds across active plans
    queued_sec = (
        await db.execute(
            select(func.coalesce(func.sum(StreamPlanItem.target_duration_sec), 0))
            .join(StreamPlan)
            .where(
                StreamPlan.status.in_(
                    [
                        PlanStatus.approved,
                        PlanStatus.preparing,
                        PlanStatus.ready,
                        PlanStatus.streaming,
                    ]
                )
            )
            .where(StreamPlanItem.stream_status == StreamItemStatus.queued)
            .where(StreamPlanItem.prep_status != PrepStatus.failed)
        )
    ).scalar_one() or 0

    # Heartbeat staleness in seconds (None if never beat)
    heartbeat_stale_sec = None
    if control and control.heartbeat_at:
        heartbeat_stale_sec = int((now - control.heartbeat_at).total_seconds())

    stream_block = {
        "running": bool(control and control.desired_running),
        "status": control.status if control else "no-control-row",
        "current_item": current_item,
        "queued_hours": round(int(queued_sec) / 3600, 2),
        "heartbeat_at": control.heartbeat_at.isoformat() if control and control.heartbeat_at else None,
        "heartbeat_stale_sec": heartbeat_stale_sec,
    }

    # ── Library ───────────────────────────────────────────────────────────────
    videos_approved = (
        await db.execute(
            select(func.count(LibraryAsset.id)).where(
                LibraryAsset.rights_status == RightsStatus.approved_for_stream
            )
        )
    ).scalar_one()
    videos_pending = (
        await db.execute(
            select(func.count(LibraryAsset.id)).where(
                LibraryAsset.rights_status == RightsStatus.pending_review
            )
        )
    ).scalar_one()
    videos_blocked = (
        await db.execute(
            select(func.count(LibraryAsset.id)).where(
                LibraryAsset.rights_status == RightsStatus.blocked
            )
        )
    ).scalar_one()
    avg_health = (
        await db.execute(
            select(func.avg(LibraryAsset.health_score)).where(
                LibraryAsset.rights_status == RightsStatus.approved_for_stream
            )
        )
    ).scalar_one()

    library_block = {
        "videos_approved": int(videos_approved or 0),
        "videos_pending": int(videos_pending or 0),
        "videos_blocked": int(videos_blocked or 0),
        "avg_health_score": float(avg_health) if avg_health is not None else None,
    }

    # ── Worst-performing approved assets (candidates to block) ────────────────
    worst_rows = (
        await db.execute(
            select(LibraryAsset)
            .where(LibraryAsset.rights_status == RightsStatus.approved_for_stream)
            .where(LibraryAsset.times_streamed >= 5)
            .where(LibraryAsset.health_score < 0.4)
            .order_by(LibraryAsset.health_score)
            .limit(5)
        )
    ).scalars().all()
    worst_assets = [
        {
            "id": str(a.id),
            "title": a.title[:80],
            "health_score": float(a.health_score or 0),
            "error_count": int(a.error_count or 0),
            "times_streamed": int(a.times_streamed or 0),
        }
        for a in worst_rows
    ]

    # ── Candidates ────────────────────────────────────────────────────────────
    cand_approved_unpromoted = (
        await db.execute(
            select(func.count(CandidateAsset.id))
            .where(CandidateAsset.rights_status == CandidateRightsStatus.approved_for_stream)
            .where(CandidateAsset.library_asset_id.is_(None))
            .where(CandidateAsset.source_url.isnot(None))
            .where(
                CandidateAsset.retrieval_status.in_(
                    [RetrievalStatus.authorized_direct, RetrievalStatus.authorized_official]
                )
            )
        )
    ).scalar_one()
    cand_pending = (
        await db.execute(
            select(func.count(CandidateAsset.id))
            .where(CandidateAsset.rights_status == CandidateRightsStatus.pending_review)
        )
    ).scalar_one()

    # First 8 ready-to-promote IDs so the LLM can target them
    promotable_ids = (
        await db.execute(
            select(CandidateAsset.id, CandidateAsset.title)
            .where(CandidateAsset.rights_status == CandidateRightsStatus.approved_for_stream)
            .where(CandidateAsset.library_asset_id.is_(None))
            .where(CandidateAsset.source_url.isnot(None))
            .where(
                CandidateAsset.retrieval_status.in_(
                    [RetrievalStatus.authorized_direct, RetrievalStatus.authorized_official]
                )
            )
            .order_by(desc(CandidateAsset.created_at))
            .limit(8)
        )
    ).all()
    candidates_block = {
        "approved_unpromoted": int(cand_approved_unpromoted or 0),
        "pending_review": int(cand_pending or 0),
        "promotable": [{"id": str(r[0]), "title": (r[1] or "")[:80]} for r in promotable_ids],
    }

    # ── Discovery ─────────────────────────────────────────────────────────────
    last_run = (
        await db.execute(
            select(DiscoveryRun).order_by(desc(DiscoveryRun.created_at)).limit(1)
        )
    ).scalar_one_or_none()
    discovery_block = {
        "last_run_at": last_run.created_at.isoformat() if last_run else None,
        "last_run_found": (last_run.output_summary or {}).get("total_found", 0) if last_run else 0,
        "hours_since_last_run": (
            round((now - last_run.created_at).total_seconds() / 3600, 1)
            if last_run else None
        ),
    }

    # ── Sites (domains) ───────────────────────────────────────────────────────
    domain_rows = (await db.execute(select(DomainPolicy))).scalars().all()
    sites = [
        {
            "id": str(d.id),
            "domain": d.domain,
            "enabled": bool(d.is_enabled),
            "is_adult": bool(d.is_adult),
            "has_template": bool(d.search_url_template or d.user_url_template),
            "has_creds": bool(d.credential_email and d.credential_password),
        }
        for d in domain_rows
    ]

    # ── Keywords ──────────────────────────────────────────────────────────────
    kw_rows = (
        await db.execute(select(SearchKeyword).order_by(desc(SearchKeyword.weight)).limit(20))
    ).scalars().all()
    keywords = [
        {
            "id": str(k.id),
            "text": k.keyword,
            "weight": float(k.weight),
            "include": bool(k.include),
            "active": bool(k.active),
            "category": k.category,
        }
        for k in kw_rows
    ]

    # ── Recent director actions ───────────────────────────────────────────────
    recent_rows = (
        await db.execute(
            select(DirectorAction).order_by(desc(DirectorAction.created_at)).limit(10)
        )
    ).scalars().all()
    last_actions = [
        {
            "at": a.created_at.isoformat(),
            "verb": a.verb,
            "why": a.why,
            "status": a.status,
        }
        for a in recent_rows
    ]

    # ── Disk ──────────────────────────────────────────────────────────────────
    try:
        from voulezvous.services.cleanup import disk_usage_spool
        disk = disk_usage_spool()
    except Exception:
        disk = None

    return {
        "now": now.isoformat(),
        "stream": stream_block,
        "library": library_block,
        "worst_approved_assets": worst_assets,
        "candidates": candidates_block,
        "discovery": discovery_block,
        "sites": sites,
        "keywords": keywords,
        "disk": disk,
        "last_actions": last_actions,
    }
