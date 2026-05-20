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
from voulezvous.services.prep_worker import _validate_local_path, prepare_item


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


def test_validate_local_path_accepts_valid_spool_path():
    """Local paths within spool directory should be accepted."""
    from voulezvous.config import settings
    
    # Test valid paths under spool
    valid_paths = [
        settings.spool_root / "test_media" / "test.mp4",
        settings.spool_root / "downloads" / "video.mp4",
        settings.spool_root / "prepared" / "item.mp4",
    ]
    
    for path in valid_paths:
        # Should not raise
        _validate_local_path(path)


def test_validate_local_path_rejects_path_traversal():
    """Path traversal attempts should be rejected."""
    from voulezvous.config import settings
    
    # Test path traversal attempts
    traversal_paths = [
        settings.spool_root / ".." / "etc" / "passwd",
        settings.spool_root / "test_media" / ".." / ".." / "etc" / "passwd",
        Path("/etc/passwd"),
        Path("/tmp/../../etc/passwd"),
    ]
    
    for path in traversal_paths:
        with pytest.raises(ValueError, match="outside spool directory|Invalid local path"):
            _validate_local_path(path)


def test_validate_local_path_rejects_absolute_path_outside_spool():
    """Absolute paths outside spool should be rejected."""
    from voulezvous.config import settings
    
    # Test absolute paths outside spool
    outside_paths = [
        Path("/tmp/test.mp4"),
        Path("/home/user/video.mp4"),
        Path("/var/lib/video.mp4"),
    ]
    
    for path in outside_paths:
        with pytest.raises(ValueError, match="outside spool directory"):
            _validate_local_path(path)
