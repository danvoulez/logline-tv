"""Distributed stream control backed by the database.

The API container and streamer container do not share Python memory. This
module stores the desired runtime state in Postgres so both processes observe
the same control plane.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.config import settings
from voulezvous.models.enums import PlanStatus, PrepStatus, StreamItemStatus
from voulezvous.models.tables import StreamControl, StreamPlan, StreamPlanItem


class ReadyBufferBelowThresholdError(Exception):
    """Raised when stream start is requested but ready buffer is below threshold."""

    def __init__(self, ready_buffer_sec: int, min_ready_buffer_sec: int):
        self.ready_buffer_sec = ready_buffer_sec
        self.min_ready_buffer_sec = min_ready_buffer_sec
        super().__init__(
            f"Ready buffer ({ready_buffer_sec}s) below threshold ({min_ready_buffer_sec}s). "
            "Wait for prep_worker to prepare more items before starting stream."
        )

STREAM_CONTROL_KEY = "main"


async def get_or_create_stream_control(db: AsyncSession) -> StreamControl:
    control = await db.get(StreamControl, STREAM_CONTROL_KEY)
    if control is None:
        control = StreamControl(
            key=STREAM_CONTROL_KEY,
            desired_running=False,
            status="idle",
        )
        db.add(control)
        await db.commit()
        await db.refresh(control)
    return control


async def request_stream_start(db: AsyncSession) -> StreamControl:
    # Check ready buffer before allowing start
    ready_buffer = await calculate_ready_buffer(db)
    if ready_buffer["ready_duration_sec"] < settings.stream_min_ready_buffer_sec:
        raise ReadyBufferBelowThresholdError(
            ready_buffer_sec=ready_buffer["ready_duration_sec"],
            min_ready_buffer_sec=settings.stream_min_ready_buffer_sec,
        )

    control = await get_or_create_stream_control(db)
    control.desired_running = True
    control.status = "start_requested"
    control.heartbeat_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(control)
    return control


async def request_stream_stop(db: AsyncSession) -> StreamControl:
    control = await get_or_create_stream_control(db)
    control.desired_running = False
    control.status = "stop_requested"
    control.current_item_id = None
    control.heartbeat_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(control)
    return control


async def update_stream_runtime(
    db: AsyncSession,
    *,
    status: str,
    current_item_id: uuid.UUID | None = None,
    desired_running: bool | None = None,
) -> StreamControl:
    control = await get_or_create_stream_control(db)
    if desired_running is not None:
        control.desired_running = desired_running
    control.status = status
    control.current_item_id = current_item_id
    control.heartbeat_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(control)
    return control


async def stream_should_run(db: AsyncSession) -> bool:
    control = await get_or_create_stream_control(db)
    return control.desired_running


async def stream_status_payload(db: AsyncSession) -> dict:
    control = await get_or_create_stream_control(db)
    return {
        "desired_running": control.desired_running,
        "running": control.desired_running and control.status in {"running", "streaming", "fallback"},
        "status": control.status,
        "current_item_id": str(control.current_item_id) if control.current_item_id else None,
        "heartbeat_at": control.heartbeat_at.isoformat() if control.heartbeat_at else None,
    }


async def calculate_ready_buffer(
    db: AsyncSession,
    plan_id: uuid.UUID | None = None,
) -> dict:
    """Calculate ready buffer for stream start admission.

    Returns:
        Dict with:
        - ready_items: count of ready items
        - ready_duration_sec: sum of target_duration_sec for ready items
        - queued_items: count of queued items
        - queued_duration_sec: sum of target_duration_sec for queued items

    Filters by plan_id if provided, otherwise includes all active plans.
    """
    active_statuses = [
        PlanStatus.approved,
        PlanStatus.preparing,
        PlanStatus.ready,
        PlanStatus.streaming,
    ]

    # Ready items query
    ready_q = (
        select(
            func.count(StreamPlanItem.id).label("count"),
            func.coalesce(func.sum(StreamPlanItem.target_duration_sec), 0).label("duration"),
        )
        .join(StreamPlan)
        .where(StreamPlan.status.in_(active_statuses))
        .where(StreamPlanItem.prep_status == PrepStatus.ready)
        .where(StreamPlanItem.stream_status == StreamItemStatus.queued)
    )
    if plan_id:
        ready_q = ready_q.where(StreamPlan.id == plan_id)

    ready_result = await db.execute(ready_q)
    ready_row = ready_result.one()
    ready_items = int(ready_row.count)
    ready_duration_sec = int(ready_row.duration)

    # Queued items query (all queued, regardless of prep status)
    queued_q = (
        select(
            func.count(StreamPlanItem.id).label("count"),
            func.coalesce(func.sum(StreamPlanItem.target_duration_sec), 0).label("duration"),
        )
        .join(StreamPlan)
        .where(StreamPlan.status.in_(active_statuses))
        .where(StreamPlanItem.stream_status == StreamItemStatus.queued)
    )
    if plan_id:
        queued_q = queued_q.where(StreamPlan.id == plan_id)

    queued_result = await db.execute(queued_q)
    queued_row = queued_result.one()
    queued_items = int(queued_row.count)
    queued_duration_sec = int(queued_row.duration)

    return {
        "ready_items": ready_items,
        "ready_duration_sec": ready_duration_sec,
        "queued_items": queued_items,
        "queued_duration_sec": queued_duration_sec,
    }
