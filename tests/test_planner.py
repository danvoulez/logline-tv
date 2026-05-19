from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.models.enums import (
    AssetKind,
    AssetStatus,
    RightsStatus,
    SourceType,
)
from voulezvous.models.tables import LibraryAsset
from voulezvous.services.planner import generate_plan


@pytest.mark.asyncio
async def test_generate_plan_from_approved_assets(db: AsyncSession):
    for i in range(3):
        asset = LibraryAsset(
            kind=AssetKind.video,
            title=f"Video {i}",
            source_type=SourceType.direct_url,
            source_url=f"https://example.com/video{i}.mp4",
            duration_sec=600,
            rights_status=RightsStatus.approved_for_stream,
            status=AssetStatus.approved,
        )
        db.add(asset)
    await db.commit()

    plan = await generate_plan(db, date(2025, 6, 1), hours=1)

    assert plan is not None
    assert len(plan.items) > 0
    total_sec = sum(i.target_duration_sec or 0 for i in plan.items)
    assert total_sec >= 3600


@pytest.mark.asyncio
async def test_generate_plan_fails_without_approved_assets(db: AsyncSession):
    # Only unapproved asset
    asset = LibraryAsset(
        kind=AssetKind.video,
        title="Pending Video",
        source_type=SourceType.direct_url,
        source_url="https://example.com/video.mp4",
        duration_sec=600,
        rights_status=RightsStatus.pending_review,
        status=AssetStatus.registered,
    )
    db.add(asset)
    await db.commit()

    with pytest.raises(ValueError, match="No approved video assets"):
        await generate_plan(db, date(2025, 6, 2), hours=1)
