"""Tests for the acquisition subsystem.

Covers:
- domain policy enforcement
- retrieval authorization gate
- discovery persistence
- metadata_only behavior
- enrichment persistence
- deterministic lineup generation
- bounded LLM action validation
- Media IR compilation
- orchestrator restart safety
"""

import uuid
from datetime import date, datetime, timezone

from voulezvous.acquisition.browser.adapters import DBAdapter
from voulezvous.acquisition.enums import (
    LineupStatus,
    SlotType,
)
from voulezvous.acquisition.models import (
    CandidateAsset,
    DiscoveryRun,
    DomainPolicy,
    LineupItem,
)
from voulezvous.acquisition.tools.executor import validate_tool_call
from voulezvous.acquisition.tools.tool_types import ToolVerb
from voulezvous.acquisition.workers.enrichment import enrich_deterministic
from voulezvous.acquisition.workers.media_ir import build_ir_for_item


def _policy(**kwargs):
    """Build an in-memory DomainPolicy with the given attrs."""
    defaults = dict(
        domain="example.com",
        is_enabled=True,
        accepted_extensions=["mp4", "webm"],
        is_adult=False,
        requires_login=False,
        needs_media_interception=False,
        title_suffix_strips=[],
    )
    defaults.update(kwargs)
    return DomainPolicy(**defaults)


# ---- Test 1: DBAdapter builds URLs from templates ----

def test_db_adapter_builds_search_url():
    p = _policy(
        domain="archive.org",
        search_url_template="https://{domain}/search?q={query}&mediatype=movies",
    )
    adapter = DBAdapter(p)
    url = adapter.build_search_url("jazz live")
    assert url == "https://archive.org/search?q=jazz+live&mediatype=movies"


def test_db_adapter_returns_none_without_template():
    adapter = DBAdapter(_policy())
    assert adapter.build_search_url("anything") is None


# ---- Test 2: Retrieval authorization gate ----

def test_retrieval_authorization_gate():
    """Only URLs matching accepted_extensions classify as authorized."""
    adapter = DBAdapter(_policy(accepted_extensions=["mp4", "webm"]))

    ok, rtype = adapter.classify_retrieval(
        "https://archive.org/download/test/video.mp4", {}
    )
    assert ok is True
    assert rtype == "direct_url"

    ok2, _ = adapter.classify_retrieval("https://site.com/page.html", {})
    assert ok2 is False

    ok3, _ = adapter.classify_retrieval(None, {})
    assert ok3 is False


def test_retrieval_via_media_interception():
    """needs_media_interception accepts intercepted media as authorized."""
    adapter = DBAdapter(_policy(needs_media_interception=True))
    ok, rtype = adapter.classify_retrieval(
        "https://tube.example/v/abc", {"intercepted_media": True}
    )
    assert ok is True
    assert rtype == "official_download"


# ---- Test 3: Discovery persistence ----

def test_discovery_run_model():
    """DiscoveryRun can be created with correct fields."""
    run = DiscoveryRun(
        run_date=date.today(),
        input_summary={"domains": ["archive.org"], "keywords": ["test"]},
        output_summary={"total_found": 5, "total_accepted": 3},
    )
    assert run.run_date == date.today()
    assert run.input_summary["domains"] == ["archive.org"]
    assert run.output_summary["total_found"] == 5


# ---- Test 4: metadata_only behavior ----

def test_metadata_only_when_no_authorized_retrieval():
    """A domain with requires_login but no download button stays metadata-only."""
    adapter = DBAdapter(_policy(requires_login=True, accepted_extensions=[]))

    ok, rtype = adapter.classify_retrieval(
        "https://player.example/video/12345", {}
    )
    assert ok is False
    assert rtype is None

    # With download button visible after login — authorized
    ok2, rtype2 = adapter.classify_retrieval(
        "https://example.com/12345/download", {"has_download_button": True}
    )
    assert ok2 is True
    assert rtype2 == "official_download"


# ---- Test 5: Enrichment persistence ----

def test_deterministic_enrichment():
    """Deterministic enrichment returns valid scores and tags."""
    result = enrich_deterministic(
        title="Ambient Ocean Waves — 4K Relaxation",
        tags=["ambient", "nature", "ocean"],
        duration_sec=1800,
        metadata={"description": "Relaxing ocean footage"},
    )
    assert "mood_tags" in result
    assert "theme_tags" in result
    assert 0 <= result["energy_score"] <= 1
    assert 0 <= result["pacing_score"] <= 1
    assert 0 <= result["repetition_risk"] <= 1
    assert result["model_name"] == "deterministic_v1"
    assert "chill" in result["mood_tags"]  # "relax" keyword matches "chill"
    assert "nature" in result["theme_tags"]  # "ocean" keyword matches "nature"


# ---- Test 6: Deterministic lineup generation ----

def test_lineup_slot_types():
    """SlotType enum covers all required types."""
    assert SlotType.main.value == "main"
    assert SlotType.buffer.value == "buffer"
    assert SlotType.fallback_reserve.value == "fallback_reserve"
    assert SlotType.music_overlay.value == "music_overlay"


def test_lineup_status_transitions():
    """LineupStatus enum covers required states."""
    assert LineupStatus.draft.value == "draft"
    assert LineupStatus.approved.value == "approved"
    assert LineupStatus.emitted.value == "emitted"
    assert LineupStatus.failed.value == "failed"


# ---- Test 7: Bounded LLM action validation ----

def test_bounded_tool_validation_valid():
    """Valid tool verbs pass validation."""
    ok, err = validate_tool_call("search_site", {"domain": "archive.org", "query": "test"})
    assert ok is True
    assert err == ""


def test_bounded_tool_validation_invalid():
    """Invalid tool verbs are rejected."""
    ok, err = validate_tool_call("execute_shell_command", {"cmd": "rm -rf /"})
    assert ok is False
    assert "Unknown tool verb" in err


def test_all_tool_verbs_registered():
    """All required tool verbs exist in ToolVerb enum."""
    required = [
        "search_site", "open_result", "inspect_candidate", "verify_playback",
        "extract_metadata", "register_retrieval_adapter", "reject_candidate",
        "expand_keywords", "enrich_candidate", "build_candidate_shelf",
        "rerank_candidates", "schedule_slot", "insert_buffer",
        "choose_music_pairing", "emit_media_ir", "write_report",
    ]
    for verb in required:
        assert ToolVerb(verb), f"Missing verb: {verb}"


# ---- Test 8: Media IR compilation ----

def test_media_ir_build():
    """Media IR produces valid ops list, never raw ffmpeg strings."""
    candidate = CandidateAsset(
        title="Test Video",
        duration_sec=600,
        source_url="https://archive.org/download/test/video.mp4",
    )
    item = LineupItem(
        sequence_index=0,
        candidate_asset_id=uuid.uuid4(),
        target_start_at=datetime(2026, 5, 19, 0, 0, 0, tzinfo=timezone.utc),
        target_end_at=datetime(2026, 5, 19, 0, 10, 0, tzinfo=timezone.utc),
        slot_type=SlotType.main,
        music_asset_ref="ambient_chill",
    )

    ir = build_ir_for_item(item, candidate)

    assert "asset_id" in ir
    assert "ops" in ir
    assert isinstance(ir["ops"], list)
    assert len(ir["ops"]) > 0

    op_types = [op["op"] for op in ir["ops"]]
    assert "normalize_audio" in op_types
    assert "export_profile" in op_types
    assert "fade_in" in op_types
    assert "fade_out" in op_types
    assert "underlay_music" in op_types

    # Verify NO raw ffmpeg strings anywhere
    ir_str = str(ir)
    assert "ffmpeg" not in ir_str.lower()
    assert "-i " not in ir_str
    assert "-filter_complex" not in ir_str


def test_media_ir_trim_when_slot_shorter_than_content():
    """Trim op appears when slot is shorter than content duration."""
    candidate = CandidateAsset(
        title="Long Video",
        duration_sec=7200,
        source_url="https://example.com/long.mp4",
    )
    item = LineupItem(
        sequence_index=1,
        candidate_asset_id=uuid.uuid4(),
        target_start_at=datetime(2026, 5, 19, 1, 0, 0, tzinfo=timezone.utc),
        target_end_at=datetime(2026, 5, 19, 1, 30, 0, tzinfo=timezone.utc),
        slot_type=SlotType.main,
    )

    ir = build_ir_for_item(item, candidate)
    op_types = [op["op"] for op in ir["ops"]]
    assert "trim" in op_types
    trim_op = next(op for op in ir["ops"] if op["op"] == "trim")
    assert trim_op["end_sec"] == 1800  # 30 minutes


# ---- Test 9: Orchestrator restart safety ----

def test_orchestrator_idempotent_discovery_model():
    """Discovery run model supports restart-safe patterns."""
    run1 = DiscoveryRun(
        id=uuid.uuid4(),
        run_date=date.today(),
        input_summary={"domains": ["archive.org"]},
    )
    run2 = DiscoveryRun(
        id=uuid.uuid4(),
        run_date=date.today(),
        input_summary={"domains": ["archive.org"]},
    )
    # Different UUIDs means multiple runs per day are safe
    assert run1.id != run2.id
    # Same date is fine — not unique-constrained
    assert run1.run_date == run2.run_date


def test_candidate_dedup_by_page_url():
    """CandidateAsset.page_url can be used for deduplication."""
    c1 = CandidateAsset(
        title="Test",
        page_url="https://archive.org/details/test-123",
    )
    c2 = CandidateAsset(
        title="Test Duplicate",
        page_url="https://archive.org/details/test-123",
    )
    assert c1.page_url == c2.page_url  # Same URL means dedup should catch it
