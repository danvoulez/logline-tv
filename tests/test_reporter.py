from datetime import date, datetime, timezone

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
from voulezvous.services.reporter import generate_daily_report


@pytest.mark.asyncio
async def test_generate_report_empty_day(db: AsyncSession):
    report = await generate_daily_report(db, date(2025, 6, 1))
    assert report is not None
    assert report.status.value == "generated"
    assert report.summary["completed_items"] == 0
    assert "Daily Report" in report.markdown_text


@pytest.mark.asyncio
async def test_generate_report_with_data(db: AsyncSession):
    asset = LibraryAsset(
        kind=AssetKind.video,
        title="Report Test Video",
        source_type=SourceType.direct_url,
        source_url="https://example.com/v.mp4",
        duration_sec=3600,
        rights_status=RightsStatus.approved_for_stream,
        status=AssetStatus.approved,
    )
    db.add(asset)
    await db.flush()

    plan = StreamPlan(
        plan_date=date(2025, 7, 1),
        status=PlanStatus.completed,
        target_start_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
        target_end_at=datetime(2025, 7, 2, tzinfo=timezone.utc),
    )
    db.add(plan)
    await db.flush()

    item = StreamPlanItem(
        stream_plan_id=plan.id,
        sequence_index=0,
        video_asset_id=asset.id,
        target_duration_sec=3600,
        prep_status=PrepStatus.ready,
        stream_status=StreamItemStatus.completed,
        actual_start_at=datetime(2025, 7, 1, 0, 0, tzinfo=timezone.utc),
        actual_end_at=datetime(2025, 7, 1, 1, 0, tzinfo=timezone.utc),
    )
    db.add(item)
    await db.commit()

    report = await generate_daily_report(db, date(2025, 7, 1))
    assert report.summary["completed_items"] == 1
    assert report.summary["planned_hours"] == 1.0
    assert report.summary["streamed_hours"] == 1.0
    assert "suggestions" in report.summary
