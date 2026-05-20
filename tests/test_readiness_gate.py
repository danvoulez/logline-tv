"""Tests for stream readiness gate."""

from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.config import settings
from voulezvous.models.enums import PlanStatus, PrepStatus, StreamItemStatus
from voulezvous.models.tables import LibraryAsset, StreamPlan, StreamPlanItem
from voulezvous.services.seed import seed_demo_data
from voulezvous.services.stream_control import (
    ReadyBufferBelowThresholdError,
    calculate_ready_buffer,
    request_stream_start,
)


async def test_calculate_ready_buffer_empty_db(db: AsyncSession) -> None:
    """Test ready buffer calculation with no items."""
    result = await calculate_ready_buffer(db)
    assert result["ready_items"] == 0
    assert result["ready_duration_sec"] == 0
    assert result["queued_items"] == 0
    assert result["queued_duration_sec"] == 0


async def test_calculate_ready_buffer_with_items(db: AsyncSession) -> None:
    """Test ready buffer calculation with mixed item states."""
    # Seed demo data
    await seed_demo_data(db)

    # Create a plan
    plan = StreamPlan(
        plan_date=date(2026, 5, 20),
        status=PlanStatus.approved,
        target_start_at=datetime(2026, 5, 20, 12, 0, 0),
        target_end_at=datetime(2026, 5, 21, 12, 0, 0),
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    # Get assets
    assets = await db.execute(select(LibraryAsset).limit(3))
    assets = assets.scalars().all()

    # Create items with different states
    # Item 1: ready, queued, 60 sec
    item1 = StreamPlanItem(
        stream_plan_id=plan.id,
        sequence_index=0,
        video_asset_id=assets[0].id,
        target_duration_sec=60,
        prep_status=PrepStatus.ready,
        stream_status=StreamItemStatus.queued,
    )
    # Item 2: ready, queued, 120 sec
    item2 = StreamPlanItem(
        stream_plan_id=plan.id,
        sequence_index=1,
        video_asset_id=assets[1].id,
        target_duration_sec=120,
        prep_status=PrepStatus.ready,
        stream_status=StreamItemStatus.queued,
    )
    # Item 3: queued (not ready), queued, 180 sec
    item3 = StreamPlanItem(
        stream_plan_id=plan.id,
        sequence_index=2,
        video_asset_id=assets[2].id,
        target_duration_sec=180,
        prep_status=PrepStatus.queued,
        stream_status=StreamItemStatus.queued,
    )
    # Item 4: ready, but already streaming (not counted)
    item4 = StreamPlanItem(
        stream_plan_id=plan.id,
        sequence_index=3,
        video_asset_id=assets[0].id,
        target_duration_sec=90,
        prep_status=PrepStatus.ready,
        stream_status=StreamItemStatus.streaming,
    )
    db.add_all([item1, item2, item3, item4])
    await db.commit()

    # Calculate ready buffer
    result = await calculate_ready_buffer(db, plan_id=plan.id)

    # Should count only ready + queued items
    assert result["ready_items"] == 2  # item1, item2
    assert result["ready_duration_sec"] == 180  # 60 + 120
    assert result["queued_items"] == 3  # item1, item2, item3
    assert result["queued_duration_sec"] == 360  # 60 + 120 + 180


async def test_stream_start_rejects_below_threshold(db: AsyncSession, monkeypatch) -> None:
    """Test that stream start rejects when ready buffer is below threshold."""
    # Seed demo data
    await seed_demo_data(db)

    # Create a plan with minimal ready buffer
    plan = StreamPlan(
        plan_date=date(2026, 5, 20),
        status=PlanStatus.approved,
        target_start_at=datetime(2026, 5, 20, 12, 0, 0),
        target_end_at=datetime(2026, 5, 21, 12, 0, 0),
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    # Get asset
    assets = await db.execute(select(LibraryAsset).limit(1))
    asset = assets.scalars().first()

    # Create one ready item with 60 sec duration
    item = StreamPlanItem(
        stream_plan_id=plan.id,
        sequence_index=0,
        video_asset_id=asset.id,
        target_duration_sec=60,
        prep_status=PrepStatus.ready,
        stream_status=StreamItemStatus.queued,
    )
    db.add(item)
    await db.commit()

    # Set high threshold to ensure rejection
    monkeypatch.setattr(settings, "stream_min_ready_buffer_sec", 1800)

    # Should raise ReadyBufferBelowThresholdError
    with pytest.raises(ReadyBufferBelowThresholdError) as exc_info:
        await request_stream_start(db)

    assert exc_info.value.ready_buffer_sec == 60
    assert exc_info.value.min_ready_buffer_sec == 1800


async def test_stream_start_accepts_when_threshold_met(db: AsyncSession, monkeypatch) -> None:
    """Test that stream start accepts when ready buffer meets threshold."""
    # Seed demo data
    await seed_demo_data(db)

    # Create a plan
    plan = StreamPlan(
        plan_date=date(2026, 5, 20),
        status=PlanStatus.approved,
        target_start_at=datetime(2026, 5, 20, 12, 0, 0),
        target_end_at=datetime(2026, 5, 21, 12, 0, 0),
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    # Get assets
    assets = await db.execute(select(LibraryAsset).limit(2))
    assets = assets.scalars().all()

    # Create ready items with sufficient duration
    item1 = StreamPlanItem(
        stream_plan_id=plan.id,
        sequence_index=0,
        video_asset_id=assets[0].id,
        target_duration_sec=1000,
        prep_status=PrepStatus.ready,
        stream_status=StreamItemStatus.queued,
    )
    item2 = StreamPlanItem(
        stream_plan_id=plan.id,
        sequence_index=1,
        video_asset_id=assets[1].id,
        target_duration_sec=1000,
        prep_status=PrepStatus.ready,
        stream_status=StreamItemStatus.queued,
    )
    db.add_all([item1, item2])
    await db.commit()

    # Set threshold to 1800 sec (30 min)
    monkeypatch.setattr(settings, "stream_min_ready_buffer_sec", 1800)

    # Should not raise exception
    control = await request_stream_start(db)
    assert control.desired_running is True
    assert control.status == "start_requested"
