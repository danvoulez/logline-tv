"""Media IR compiler — converts lineup items into compact IR objects.

The LLM emits compact Media IR, NOT raw ffmpeg commands.
The compiler converts IR deterministically into whatever the
existing streaming MVP prep pipeline requires.
"""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.acquisition.enums import LineupStatus, MediaIRStatus, SlotType
from voulezvous.acquisition.models import (
    CandidateAsset,
    LineupItem,
    LineupRun,
    MediaIRJob,
)

logger = structlog.get_logger()

COMPILER_VERSION = "1.0.0"

# Standard export profiles
EXPORT_PROFILES = {
    "broadcast_standard": {
        "video_codec": "libx264",
        "audio_codec": "aac",
        "resolution": "1920x1080",
        "frame_rate": 30,
        "audio_sample_rate": 48000,
        "crf": 23,
    },
    "web_optimized": {
        "video_codec": "libx264",
        "audio_codec": "aac",
        "resolution": "1280x720",
        "frame_rate": 30,
        "audio_sample_rate": 44100,
        "crf": 28,
    },
}


def build_ir_for_item(item: LineupItem, candidate: CandidateAsset) -> dict:
    """Build a Media IR object for a single lineup item.

    The IR is a compact, deterministic representation.
    No raw ffmpeg strings.
    """
    ops: list[dict] = []
    duration_sec = candidate.duration_sec or 600

    # Trim to scheduled slot duration if needed
    slot_dur = None
    if item.target_start_at and item.target_end_at:
        slot_dur = int((item.target_end_at - item.target_start_at).total_seconds())

    if slot_dur and slot_dur < duration_sec:
        ops.append({
            "op": "trim",
            "start_sec": 0,
            "end_sec": slot_dur,
        })

    # Audio normalization
    ops.append({
        "op": "normalize_audio",
        "target_lufs": -14.0,
    })

    # Music underlay if paired
    if item.music_asset_ref and item.slot_type == SlotType.main:
        ops.append({
            "op": "underlay_music",
            "music_ref": item.music_asset_ref,
            "video_gain": 0.5,
            "music_gain": 0.5,
        })

    # Fades for main content
    if item.slot_type == SlotType.main:
        ops.append({"op": "fade_in", "duration_sec": 1.5})
        ops.append({"op": "fade_out", "duration_sec": 2.0})

    # Buffer gets shorter fades
    if item.slot_type == SlotType.buffer:
        ops.append({"op": "fade_in", "duration_sec": 0.5})
        ops.append({"op": "fade_out", "duration_sec": 0.5})

    # Export profile
    ops.append({
        "op": "export_profile",
        "profile": "broadcast_standard",
    })

    return {
        "asset_id": str(candidate.id),
        "source_url": candidate.source_url,
        "title": candidate.title,
        "slot_type": (
            item.slot_type.value if hasattr(item.slot_type, 'value')
            else str(item.slot_type)
        ),
        "sequence_index": item.sequence_index,
        "ops": ops,
    }


async def compile_media_ir(db: AsyncSession, lineup_id: uuid.UUID) -> dict:
    """Compile Media IR jobs for all items in a lineup."""
    lineup = (await db.execute(
        select(LineupRun).where(LineupRun.id == lineup_id)
    )).scalar_one_or_none()
    if not lineup:
        return {"error": "Lineup not found", "compiled": 0}

    items = (await db.execute(
        select(LineupItem).where(LineupItem.lineup_run_id == lineup_id)
        .order_by(LineupItem.sequence_index)
    )).scalars().all()

    compiled = 0
    failed = 0

    for item in items:
        # Skip fallback reserves (compiled on demand)
        if item.slot_type == SlotType.fallback_reserve:
            continue

        candidate = (await db.execute(
            select(CandidateAsset).where(CandidateAsset.id == item.candidate_asset_id)
        )).scalar_one_or_none()

        if not candidate:
            job = MediaIRJob(
                lineup_item_id=item.id,
                status=MediaIRStatus.failed,
                ir_json={},
                compiler_version=COMPILER_VERSION,
                error_message="Candidate asset not found",
            )
            db.add(job)
            failed += 1
            continue

        try:
            ir = build_ir_for_item(item, candidate)
            job = MediaIRJob(
                lineup_item_id=item.id,
                status=MediaIRStatus.compiled,
                ir_json=ir,
                compiler_version=COMPILER_VERSION,
            )
            db.add(job)
            compiled += 1
        except Exception as e:
            job = MediaIRJob(
                lineup_item_id=item.id,
                status=MediaIRStatus.failed,
                ir_json={},
                compiler_version=COMPILER_VERSION,
                error_message=str(e),
            )
            db.add(job)
            failed += 1

    lineup.status = LineupStatus.emitted
    await db.commit()

    logger.info("media_ir_compiled", lineup_id=str(lineup_id),
                compiled=compiled, failed=failed)
    return {"lineup_id": str(lineup_id), "compiled": compiled, "failed": failed}
