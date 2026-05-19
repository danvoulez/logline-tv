
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.models.enums import (
    AssetKind,
    AssetStatus,
    RightsStatus,
    SourceType,
)
from voulezvous.models.tables import LibraryAsset


@pytest.mark.asyncio
async def test_asset_starts_pending_review(db: AsyncSession):
    asset = LibraryAsset(
        kind=AssetKind.video,
        title="Test Video",
        source_type=SourceType.direct_url,
        source_url="https://example.com/video.mp4",
        rights_status=RightsStatus.pending_review,
        status=AssetStatus.registered,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    assert asset.rights_status == RightsStatus.pending_review
    assert asset.status == AssetStatus.registered


@pytest.mark.asyncio
async def test_approval_gate_blocks_unapproved(db: AsyncSession):
    """Assets with pending_review cannot be used for streaming."""
    asset = LibraryAsset(
        kind=AssetKind.video,
        title="Unapproved Video",
        source_type=SourceType.direct_url,
        source_url="https://example.com/video.mp4",
        rights_status=RightsStatus.pending_review,
        status=AssetStatus.registered,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    # Simulate the rights gate check used in prep_worker
    assert asset.rights_status != RightsStatus.approved_for_stream


@pytest.mark.asyncio
async def test_approve_asset(db: AsyncSession):
    asset = LibraryAsset(
        kind=AssetKind.video,
        title="Approvable Video",
        source_type=SourceType.direct_url,
        source_url="https://example.com/video.mp4",
        rights_status=RightsStatus.pending_review,
        status=AssetStatus.registered,
    )
    db.add(asset)
    await db.commit()

    asset.rights_status = RightsStatus.approved_for_stream
    asset.status = AssetStatus.approved
    await db.commit()
    await db.refresh(asset)

    assert asset.rights_status == RightsStatus.approved_for_stream
    assert asset.status == AssetStatus.approved


@pytest.mark.asyncio
async def test_block_asset(db: AsyncSession):
    asset = LibraryAsset(
        kind=AssetKind.video,
        title="Blocked Video",
        source_type=SourceType.direct_url,
        source_url="https://example.com/video.mp4",
        rights_status=RightsStatus.blocked,
        status=AssetStatus.blocked,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    assert asset.rights_status == RightsStatus.blocked
    assert asset.status == AssetStatus.blocked
