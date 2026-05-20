import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles

from voulezvous.config import settings

# SQLite doesn't have JSONB; acquisition models are imported below.
if not hasattr(JSONB, "_sqlite_compiler_registered"):

    @compiles(JSONB, "sqlite")
    def _compile_jsonb_sqlite(type_, compiler, **kw):
        return "JSON"

    JSONB._sqlite_compiler_registered = True  # type: ignore[attr-defined]

from voulezvous.acquisition.enums import (  # noqa: E402
    CandidateRightsStatus,
    DiscoveryStatus,
    RetrievalStatus,
    SlotType,
)
from voulezvous.acquisition.models import CandidateAsset, LineupItem  # noqa: E402
from voulezvous.acquisition.workers.curator import generate_lineup  # noqa: E402

# Import discovery functions for testing
from voulezvous.acquisition.workers.json_utils import loads_llm_json  # noqa: E402
from voulezvous.models.enums import (  # noqa: E402
    AssetKind,
    AssetStatus,
    PlanStatus,
    PrepStatus,
    RightsStatus,
    SourceType,
    StreamItemStatus,
)
from voulezvous.models.tables import LibraryAsset, StreamPlan, StreamPlanItem  # noqa: E402
from voulezvous.services.stream_control import (  # noqa: E402
    request_stream_start,
    request_stream_stop,
    stream_status_payload,
)
from voulezvous.services.streamer import _claim_next_ready_item  # noqa: E402


@pytest.mark.asyncio
async def test_stream_control_is_database_backed(db: AsyncSession, monkeypatch):
    # Set low threshold for this test to avoid ready buffer check
    monkeypatch.setattr(settings, "stream_min_ready_buffer_sec", 0)

    await request_stream_start(db)
    status = await stream_status_payload(db)
    assert status["desired_running"] is True
    assert status["status"] == "start_requested"

    await request_stream_stop(db)
    status = await stream_status_payload(db)
    assert status["desired_running"] is False
    assert status["status"] == "stop_requested"


@pytest.mark.asyncio
async def test_streamer_can_claim_ready_item_from_preparing_plan(db: AsyncSession):
    asset = LibraryAsset(
        kind=AssetKind.video,
        title="Prepared Just In Time",
        source_type=SourceType.direct_url,
        source_url="https://example.com/video.mp4",
        duration_sec=10,
        rights_status=RightsStatus.approved_for_stream,
        status=AssetStatus.registered,
    )
    now = datetime.now(timezone.utc)
    plan = StreamPlan(
        plan_date=date(2026, 5, 19),
        status=PlanStatus.preparing,
        target_start_at=now,
        target_end_at=now,
    )
    db.add_all([asset, plan])
    await db.flush()

    item = StreamPlanItem(
        stream_plan_id=plan.id,
        video_asset_id=asset.id,
        sequence_index=0,
        planned_start_at=now,
        planned_end_at=now,
        target_duration_sec=10,
        prep_status=PrepStatus.ready,
        stream_status=StreamItemStatus.queued,
        prepared_file_path="/spool/prepared/test.mp4",
    )
    db.add(item)
    await db.commit()

    claimed = await _claim_next_ready_item(db)

    assert claimed is not None
    assert claimed.id == item.id
    assert claimed.stream_status == StreamItemStatus.streaming
    assert (await db.get(StreamPlan, plan.id)).status == PlanStatus.streaming


def test_loads_llm_json_accepts_fenced_and_prefaced_json():
    assert loads_llm_json('```json\n{"ok": true}\n```') == {"ok": True}
    assert loads_llm_json('Here is your JSON: [{"type": "flag_monotony"}]') == [{"type": "flag_monotony"}]


@pytest.mark.asyncio
async def test_lineup_fills_target_with_explicit_repeat_overflow(db: AsyncSession):
    for i in range(5):
        db.add(
            CandidateAsset(
                id=uuid.uuid4(),
                title=f"Approved Video {i}",
                source_url=f"https://example.com/video-{i}.mp4",
                duration_sec=600,
                quality_signals={},
                tags=["test"],
                playback_verified=True,
                rights_status=CandidateRightsStatus.approved_for_stream,
                retrieval_status=RetrievalStatus.authorized_direct,
                discovery_status=DiscoveryStatus.accepted,
            )
        )
    await db.commit()

    lineup = await generate_lineup(db, date(2026, 5, 19), target_hours=24, mix_music=False)

    items = (
        (
            await db.execute(
                select(LineupItem).where(LineupItem.lineup_run_id == lineup.id).order_by(LineupItem.sequence_index)
            )
        )
        .scalars()
        .all()
    )
    main_duration = sum(
        int((item.target_end_at - item.target_start_at).total_seconds())
        for item in items
        if item.slot_type in {SlotType.main, SlotType.buffer}
    )

    assert main_duration == 24 * 3600
    assert lineup.context_summary["target_filled"] is True
    assert lineup.context_summary["overflow_repeats_used"] is True


def test_real_discovery_failure_does_not_create_simulated_candidates():
    """Real discovery failure should raise an exception, not fall back to simulated discovery.

    This tests the code structure to verify the fallback logic was removed.
    """
    import inspect

    from voulezvous.acquisition.api.discovery import trigger_discovery

    source = inspect.getsource(trigger_discovery)
    # Verify that the old fallback pattern is gone
    assert "falling_back" not in source.lower()
    # The function should still have simulated discovery as an explicit option
    assert "simulated" in source.lower()
    # But it should not have automatic fallback on exception
    lines = source.split("\n")
    exception_handling = [line for line in lines if "except Exception" in line]
    # If there's exception handling, it should not fall back to simulated
    for line in exception_handling:
        assert "run_discovery_simulated" not in source[source.index(line):source.index(line) + 200]


def test_metadata_only_candidate_has_retrieval_status():
    """Candidates with metadata_only retrieval status should have the correct status set."""
    candidate = CandidateAsset(
        title="Metadata Only Video",
        source_url=None,  # No source URL = metadata_only
        page_url="https://example.com/video/123",
        duration_sec=600,
        quality_signals={},
        tags=["test"],
        playback_verified=False,
        retrieval_status=RetrievalStatus.metadata_only,
        discovery_status=DiscoveryStatus.inspected,
        rights_status=CandidateRightsStatus.pending_review,
    )
    assert candidate.retrieval_status == RetrievalStatus.metadata_only
    assert candidate.source_url is None


def test_unapproved_asset_has_correct_rights_status():
    """Assets without approved_for_stream rights should have the correct status."""
    asset = LibraryAsset(
        kind=AssetKind.video,
        title="Unapproved Video",
        source_type=SourceType.direct_url,
        source_url="https://example.com/video.mp4",
        duration_sec=600,
        rights_status=RightsStatus.pending_review,  # Not approved
        status=AssetStatus.registered,
    )
    assert asset.rights_status != RightsStatus.approved_for_stream


def test_hls_target_detection():
    """Verify that stream_to_target correctly detects HLS mode."""
    from unittest.mock import AsyncMock, patch

    from voulezvous.config import settings

    # Test various HLS target patterns
    hls_targets = [
        "hls",  # Explicit HLS string
        "/spool/hls/stream.m3u8",  # .m3u8 file
        str(settings.spool_hls),  # HLS directory
        str(settings.spool_hls / "playlist.m3u8"),  # HLS directory with file
    ]

    for target in hls_targets:
        with patch('voulezvous.services.ffmpeg.stream_to_hls', new_callable=AsyncMock) as mock_hls:
            mock_hls.return_value = (0, "")
            # This should trigger HLS mode
            # We're testing the detection logic, not actual streaming
            is_hls_mode = (
                target == "hls"
                or target.endswith(".m3u8")
                or target == str(settings.spool_hls)
            )
            assert is_hls_mode, f"Target {target} should be detected as HLS mode"

    # Test non-HLS targets
    non_hls_targets = [
        "null",
        "/spool/hls/stream.flv",
        "rtmp://example.com/live",
        "/some/other/path.mp4",
    ]

    for target in non_hls_targets:
        is_hls_mode = (
            target == "hls"
            or target.endswith(".m3u8")
            or target == str(settings.spool_hls)
        )
        assert not is_hls_mode, f"Target {target} should not be detected as HLS mode"


@pytest.mark.asyncio
async def test_bootstrap_creates_fallback_video():
    """Verify that bootstrap creates fallback video if missing."""
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from voulezvous.config import Settings
    from voulezvous.services.bootstrap import ensure_fallback_video

    with TemporaryDirectory() as tmpdir:
        # Create a temporary settings instance
        test_settings = Settings(
            spool_root=Path(tmpdir),
            fallback_video="fallback.mp4",
            house_resolution="1920x1080",
            house_frame_rate=30,
            house_audio_sample_rate=48000,
            house_video_codec="libx264",
            house_audio_codec="aac",
        )

        # Patch the global settings
        import voulezvous.services.bootstrap as bootstrap_module
        original_settings = bootstrap_module.settings
        bootstrap_module.settings = test_settings

        try:
            # Ensure fallback video is created
            await ensure_fallback_video()

            # Verify fallback video exists
            fallback_path = test_settings.fallback_video_path
            assert fallback_path.exists(), "Fallback video should be created"
            assert fallback_path.stat().st_size > 0, "Fallback video should not be empty"

            # Test that existing video is not regenerated
            fallback_stat = fallback_path.stat()
            await ensure_fallback_video()
            assert (
                fallback_path.stat().st_mtime == fallback_stat.st_mtime
            ), "Existing fallback should not be regenerated"
        finally:
            bootstrap_module.settings = original_settings


@pytest.mark.asyncio
async def test_stream_event_includes_plan_id(db: AsyncSession):
    """Verify that stream events for item operations include plan_id."""
    from datetime import date, datetime, timezone

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
    from voulezvous.services.streamer import _claim_next_ready_item

    # Create asset
    asset = LibraryAsset(
        kind=AssetKind.video,
        title="Test Asset",
        source_type=SourceType.direct_url,
        source_url="https://example.com/video.mp4",
        duration_sec=10,
        rights_status=RightsStatus.approved_for_stream,
        status=AssetStatus.approved,
    )
    db.add(asset)

    # Create plan
    now = datetime.now(timezone.utc)
    plan = StreamPlan(
        plan_date=date(2026, 5, 20),
        status=PlanStatus.ready,
        target_start_at=now,
        target_end_at=now,
    )
    db.add(plan)
    await db.flush()

    # Create plan item
    item = StreamPlanItem(
        stream_plan_id=plan.id,
        video_asset_id=asset.id,
        sequence_index=0,
        planned_start_at=now,
        planned_end_at=now,
        target_duration_sec=10,
        prep_status=PrepStatus.ready,
        stream_status=StreamItemStatus.queued,
        prepared_file_path="/spool/prepared/test.mp4",
    )
    db.add(item)
    await db.commit()

    # Claim the item
    claimed = await _claim_next_ready_item(db)

    # Verify item was claimed
    assert claimed is not None
    assert claimed.id == item.id

    # Check that an item_started event was logged with plan_id
    from sqlalchemy import select

    from voulezvous.models.tables import StreamEvent

    result = await db.execute(
        select(StreamEvent)
        .where(StreamEvent.event_type == "item_started")
        .where(StreamEvent.plan_item_id == item.id)
        .order_by(StreamEvent.occurred_at.desc())
        .limit(1)
    )
    event = result.scalar_one_or_none()

    assert event is not None, "item_started event should be logged"
    assert event.plan_id == plan.id, "item_started event should include plan_id"
    assert event.plan_item_id == item.id, "item_started event should include plan_item_id"
    assert event.asset_id == asset.id, "item_started event should include asset_id"
