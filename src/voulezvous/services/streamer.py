import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from voulezvous.config import settings
from voulezvous.database import async_session
from voulezvous.models.enums import (
    EventType,
    PlanStatus,
    PrepStatus,
    StreamItemStatus,
)
from voulezvous.models.tables import LibraryAsset, StreamEvent, StreamPlan, StreamPlanItem
from voulezvous.services.ffmpeg import stream_to_target

logger = structlog.get_logger()


class StreamerState:
    def __init__(self) -> None:
        self.running: bool = False
        self.should_stop: bool = False
        self.current_item_id: uuid.UUID | None = None

    def request_start(self) -> None:
        self.should_stop = False
        self.running = True

    def request_stop(self) -> None:
        self.should_stop = True


streamer_state = StreamerState()


async def run_streamer() -> None:
    streamer_state.request_start()
    logger.info("streamer_started", target=settings.stream_target)

    async with async_session() as db:
        await _log_event(db, EventType.stream_started)

    try:
        while not streamer_state.should_stop:
            async with async_session() as db:
                item = await _next_ready_item(db)
                if item is None:
                    # No items — use fallback
                    await _play_fallback(db)
                    await asyncio.sleep(5)
                    continue

                streamer_state.current_item_id = item.id
                await _play_item(db, item)
                streamer_state.current_item_id = None
    finally:
        streamer_state.running = False
        streamer_state.current_item_id = None
        logger.info("streamer_stopped")


async def _next_ready_item(db: AsyncSession) -> StreamPlanItem | None:
    q = (
        select(StreamPlanItem)
        .join(StreamPlan)
        .where(StreamPlan.status.in_([PlanStatus.ready, PlanStatus.streaming]))
        .where(StreamPlanItem.prep_status == PrepStatus.ready)
        .where(StreamPlanItem.stream_status == StreamItemStatus.queued)
        .options(selectinload(StreamPlanItem.video_asset))
        .order_by(StreamPlanItem.planned_start_at, StreamPlanItem.sequence_index)
        .limit(1)
    )
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def _play_item(db: AsyncSession, item: StreamPlanItem) -> None:
    prepared_path = Path(item.prepared_file_path) if item.prepared_file_path else None
    if not prepared_path or not prepared_path.exists():
        logger.warning("prepared_file_missing", item_id=str(item.id))
        item.stream_status = StreamItemStatus.skipped
        item.error_log = "Prepared file missing"
        await db.commit()
        await _log_event(db, EventType.item_failed, plan_item_id=item.id)
        return

    # Mark streaming
    item.stream_status = StreamItemStatus.streaming
    item.actual_start_at = datetime.now(timezone.utc)
    plan = await db.get(StreamPlan, item.stream_plan_id)
    if plan and plan.status == PlanStatus.ready:
        plan.status = PlanStatus.streaming
    await db.commit()
    await _log_event(db, EventType.item_started, plan_item_id=item.id, asset_id=item.video_asset_id)

    # Stream
    try:
        rc, stderr = await stream_to_target(prepared_path, settings.stream_target)
        if rc != 0:
            raise RuntimeError(f"Stream failed rc={rc}: {stderr[-300:]}")

        item.stream_status = StreamItemStatus.completed
        item.actual_end_at = datetime.now(timezone.utc)
        await db.commit()
        await _log_event(
            db, EventType.item_completed, plan_item_id=item.id, asset_id=item.video_asset_id
        )

        # Update asset stats
        video = await db.get(LibraryAsset, item.video_asset_id)
        if video:
            video.last_streamed_at = datetime.now(timezone.utc)
            video.times_streamed += 1
            await db.commit()

        # Cleanup
        if item.delete_after_stream:
            await _cleanup_item(db, item)

    except Exception as e:
        logger.error("stream_item_error", item_id=str(item.id), error=str(e))
        item.stream_status = StreamItemStatus.failed
        item.error_log = str(e)
        item.actual_end_at = datetime.now(timezone.utc)
        await db.commit()
        await _log_event(db, EventType.item_failed, plan_item_id=item.id)


async def _play_fallback(db: AsyncSession) -> None:
    fb = settings.fallback_video_path
    if not fb.exists():
        logger.warning("fallback_missing", path=str(fb))
        await asyncio.sleep(10)
        return

    await _log_event(db, EventType.fallback_started)
    logger.info("playing_fallback", path=str(fb))
    rc, _ = await stream_to_target(fb, settings.stream_target)
    await _log_event(db, EventType.fallback_stopped)


async def _cleanup_item(db: AsyncSession, item: StreamPlanItem) -> None:
    paths_to_delete = []
    if item.prepared_file_path:
        paths_to_delete.append(Path(item.prepared_file_path))

    for p in paths_to_delete:
        try:
            if p.exists():
                p.unlink()
                logger.info("cleanup_deleted", path=str(p))
                await _log_event(
                    db, EventType.cleanup_deleted,
                    plan_item_id=item.id, asset_id=item.video_asset_id,
                )
        except Exception as e:
            logger.error("cleanup_failed", path=str(p), error=str(e))
            await _log_event(
                db, EventType.cleanup_failed,
                plan_item_id=item.id, asset_id=item.video_asset_id,
                payload={"error": str(e)},
            )


async def _log_event(
    db: AsyncSession,
    event_type: EventType,
    plan_id: uuid.UUID | None = None,
    plan_item_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    payload: dict | None = None,
) -> None:
    ev = StreamEvent(
        event_type=event_type,
        plan_id=plan_id,
        plan_item_id=plan_item_id,
        asset_id=asset_id,
        occurred_at=datetime.now(timezone.utc),
        payload=payload or {},
    )
    db.add(ev)
    await db.commit()
