"""Observability endpoint — everything the admin panel needs in one JSON."""

from datetime import datetime, timezone

import httpx
import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from voulezvous.acquisition.models import DiscoveryRun
from voulezvous.config import settings
from voulezvous.database import get_db
from voulezvous.models.enums import PlanStatus, PrepStatus, StreamItemStatus
from voulezvous.models.tables import (
    DirectorAction,
    DirectorRun,
    LibraryAsset,
    StreamControl,
    StreamPlan,
    StreamPlanItem,
)
from voulezvous.services.cleanup import disk_usage_spool
from voulezvous.services.stream_control import calculate_ready_buffer

logger = structlog.get_logger()
router = APIRouter(prefix="/obs", tags=["observability"])


@router.get("/snapshot")
async def snapshot(db: AsyncSession = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    active_statuses = [
        PlanStatus.approved,
        PlanStatus.preparing,
        PlanStatus.ready,
        PlanStatus.streaming,
    ]

    # ── Signal block ──────────────────────────────────────────────────────────
    control = await db.get(StreamControl, "main")
    current = None
    if control and control.current_item_id:
        item = (
            await db.execute(
                select(StreamPlanItem)
                .where(StreamPlanItem.id == control.current_item_id)
                .options(selectinload(StreamPlanItem.video_asset))
            )
        ).scalar_one_or_none()
        if item:
            current = {
                "title": item.video_asset.title if item.video_asset else None,
                "duration_sec": item.target_duration_sec,
                "started_at": item.actual_start_at.isoformat() if item.actual_start_at else None,
            }

    # next 5 items
    next_items_rows = (
        (
            await db.execute(
                select(StreamPlanItem)
                .join(StreamPlan)
                .where(StreamPlan.status.in_(active_statuses))
                .where(StreamPlanItem.stream_status == StreamItemStatus.queued)
                .options(selectinload(StreamPlanItem.video_asset))
                .order_by(StreamPlanItem.planned_start_at, StreamPlanItem.sequence_index)
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    next_items = [
        {
            "title": it.video_asset.title if it.video_asset else None,
            "prep_status": it.prep_status.value if hasattr(it.prep_status, "value") else str(it.prep_status),
            "duration_sec": it.target_duration_sec,
        }
        for it in next_items_rows
    ]

    stream_status_str = control.status if control else "no-control-row"
    desired_running = bool(control and control.desired_running)
    heartbeat_stale = None
    if control and control.heartbeat_at:
        heartbeat_stale = int((now - control.heartbeat_at).total_seconds())

    signal = {
        "desired_running": desired_running,
        "status": stream_status_str,
        "running": desired_running and stream_status_str in {"running", "streaming", "fallback"},
        "current": current,
        "next_5": next_items,
        "heartbeat_at": control.heartbeat_at.isoformat() if control and control.heartbeat_at else None,
        "heartbeat_stale_sec": heartbeat_stale,
    }

    # ── Pipeline block ────────────────────────────────────────────────────────
    queued_sec = (
        await db.execute(
            select(func.coalesce(func.sum(StreamPlanItem.target_duration_sec), 0))
            .join(StreamPlan)
            .where(StreamPlan.status.in_(active_statuses))
            .where(StreamPlanItem.stream_status == StreamItemStatus.queued)
        )
    ).scalar_one() or 0

    # ready buffer calculation
    ready_buffer = await calculate_ready_buffer(db)
    ready_buffer_min = round(ready_buffer["ready_duration_sec"] / 60, 2)

    # active plan (most recent non-completed)
    active_plan = (
        await db.execute(
            select(StreamPlan)
            .where(StreamPlan.status.in_(active_statuses))
            .order_by(desc(StreamPlan.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    plan_block = None
    if active_plan:
        ready = (
            await db.execute(
                select(func.count(StreamPlanItem.id))
                .where(StreamPlanItem.stream_plan_id == active_plan.id)
                .where(StreamPlanItem.prep_status == PrepStatus.ready)
            )
        ).scalar_one() or 0
        queued_items = (
            await db.execute(
                select(func.count(StreamPlanItem.id))
                .where(StreamPlanItem.stream_plan_id == active_plan.id)
                .where(StreamPlanItem.prep_status == PrepStatus.queued)
            )
        ).scalar_one() or 0
        total = (
            await db.execute(
                select(func.count(StreamPlanItem.id)).where(StreamPlanItem.stream_plan_id == active_plan.id)
            )
        ).scalar_one() or 0
        plan_block = {
            "id": str(active_plan.id),
            "status": active_plan.status.value if hasattr(active_plan.status, "value") else str(active_plan.status),
            "items_total": int(total),
            "items_ready": int(ready),
            "items_queued": int(queued_items),
        }

    pipeline = {
        "queued_hours": round(int(queued_sec) / 3600, 2),
        "ready_buffer_sec": ready_buffer["ready_duration_sec"],
        "ready_buffer_min": ready_buffer_min,
        "ready_items": ready_buffer["ready_items"],
        "queued_items": ready_buffer["queued_items"],
        "disk": disk_usage_spool(),
        "plan": plan_block,
    }

    # ── Brain block ───────────────────────────────────────────────────────────
    last_run = (
        await db.execute(select(DirectorRun).order_by(desc(DirectorRun.started_at)).limit(1))
    ).scalar_one_or_none()
    recent_actions_rows = (
        (await db.execute(select(DirectorAction).order_by(desc(DirectorAction.created_at)).limit(30))).scalars().all()
    )
    recent_actions = [
        {
            "at": a.created_at.isoformat() if a.created_at else None,
            "verb": a.verb,
            "why": a.why,
            "status": a.status,
            "error": a.error,
        }
        for a in recent_actions_rows
    ]
    director = {
        "last_run_at": last_run.started_at.isoformat() if last_run and last_run.started_at else None,
        "last_run_actions": last_run.action_count if last_run else 0,
        "recent_actions": recent_actions,
    }

    # ── Health block ──────────────────────────────────────────────────────────
    # Ping Ollama
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(f"{settings.local_llm_url.rstrip('/')}/api/tags")
            ollama_ok = r.status_code == 200
    except Exception:
        ollama_ok = False

    last_discovery = (
        await db.execute(select(DiscoveryRun).order_by(desc(DiscoveryRun.created_at)).limit(1))
    ).scalar_one_or_none()

    # Library health
    avg_health = (
        await db.execute(select(func.avg(LibraryAsset.health_score)).where(LibraryAsset.health_score.isnot(None)))
    ).scalar_one()

    health = {
        "ollama_reachable": ollama_ok,
        "last_discovery_at": last_discovery.created_at.isoformat() if last_discovery else None,
        "avg_health_score": float(avg_health) if avg_health is not None else None,
    }

    return {
        "now": now.isoformat(),
        "signal": signal,
        "pipeline": pipeline,
        "director": director,
        "health": health,
    }
