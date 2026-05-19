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
from voulezvous.services.prep_worker import prepare_item


@pytest.mark.asyncio
async def test_prep_rejects_unapproved_asset(db: AsyncSession):
    """Preparation must hard-fail for unapproved assets."""
    asset = LibraryAsset(
        kind=AssetKind.video,
        title="Unapproved",
        source_type=SourceType.direct_url,
        source_url="https://example.com/v.mp4",
        duration_sec=60,
        rights_status=RightsStatus.pending_review,
        status=AssetStatus.registered,
    )
    db.add(asset)
    await db.flush()

    plan = StreamPlan(
        plan_date=date(2025, 6, 1),
        status=PlanStatus.approved,
        target_start_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        target_end_at=datetime(2025, 6, 2, tzinfo=timezone.utc),
    )
    db.add(plan)
    await db.flush()

    item = StreamPlanItem(
        stream_plan_id=plan.id,
        sequence_index=0,
        video_asset_id=asset.id,
        prep_status=PrepStatus.queued,
        stream_status=StreamItemStatus.queued,
    )
    db.add(item)
    await db.commit()

    # Eagerly load the relationship
    await db.refresh(item, ["video_asset"])

    with pytest.raises(ValueError, match="approved_for_stream"):
        await prepare_item(db, item)
