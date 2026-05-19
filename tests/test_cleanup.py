from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.models.enums import (
    AssetKind,
    AssetStatus,
    PlanStatus,
    PrepStatus,
    RightsStatus,
    SourceType,
    StreamItemStatus,
)
from voulezvous.models.tables import LibraryAsset, StreamPlan, StreamPlanItem
from voulezvous.services.streamer import _cleanup_item


@pytest.mark.asyncio
async def test_cleanup_deletes_prepared_file(db: AsyncSession, tmp_path: Path):
    """Cleanup should delete local bytes but keep metadata."""
    fake_file = tmp_path / "prepared_test.mp4"
    fake_file.write_bytes(b"fake video data")

    asset = LibraryAsset(
        kind=AssetKind.video,
        title="Cleanup Test",
        source_type=SourceType.direct_url,
        source_url="https://example.com/v.mp4",
        duration_sec=60,
        rights_status=RightsStatus.approved_for_stream,
        status=AssetStatus.prepared,
        times_streamed=1,
    )
    db.add(asset)
    await db.flush()

    plan = StreamPlan(
        plan_date=date(2025, 6, 1),
        status=PlanStatus.streaming,
        target_start_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        target_end_at=datetime(2025, 6, 2, tzinfo=timezone.utc),
    )
    db.add(plan)
    await db.flush()

    item = StreamPlanItem(
        stream_plan_id=plan.id,
        sequence_index=0,
        video_asset_id=asset.id,
        prepared_file_path=str(fake_file),
        delete_after_stream=True,
        stream_status=StreamItemStatus.completed,
        prep_status=PrepStatus.ready,
    )
    db.add(item)
    await db.commit()

    assert fake_file.exists()
    await _cleanup_item(db, item)
    assert not fake_file.exists()

    # Metadata still in DB
    await db.refresh(asset)
    assert asset.title == "Cleanup Test"
    assert asset.times_streamed == 1
