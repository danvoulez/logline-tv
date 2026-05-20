"""Disk cleanup for /spool — keeps the LAB from filling up.

- Orphan downloads: files in /spool/downloads that no LibraryAsset still references
- Orphan prepared: files in /spool/prepared that no StreamPlanItem still references
- Orphan HLS segments: .ts files in /spool/hls that are not in the current playlist

Designed to be safe: only deletes files whose paths sit inside the spool dirs
and are NOT referenced by any active row or playlist.
"""

from __future__ import annotations

import re
import shutil

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.config import settings
from voulezvous.models.enums import StreamItemStatus
from voulezvous.models.tables import LibraryAsset, StreamPlanItem

logger = structlog.get_logger()


async def cleanup_orphan_downloads(db: AsyncSession) -> dict:
    spool = settings.spool_downloads
    if not spool.exists():
        return {"scanned": 0, "deleted": 0, "freed_bytes": 0}

    referenced = {
        str(p)
        for p in (
            await db.execute(select(LibraryAsset.current_local_path).where(LibraryAsset.current_local_path.isnot(None)))
        )
        .scalars()
        .all()
    }

    scanned = 0
    deleted = 0
    freed = 0
    for f in spool.iterdir():
        if not f.is_file():
            continue
        scanned += 1
        if str(f) in referenced:
            continue
        try:
            size = f.stat().st_size
            f.unlink()
            deleted += 1
            freed += size
        except Exception as e:
            logger.warning("cleanup.unlink_failed", path=str(f), error=str(e))

    logger.info("cleanup.downloads", scanned=scanned, deleted=deleted, freed=freed)
    return {"scanned": scanned, "deleted": deleted, "freed_bytes": freed}


async def cleanup_orphan_prepared(db: AsyncSession) -> dict:
    spool = settings.spool_prepared
    if not spool.exists():
        return {"scanned": 0, "deleted": 0, "freed_bytes": 0}

    active_statuses = [StreamItemStatus.queued, StreamItemStatus.streaming]
    if not settings.delete_after_stream:
        active_statuses.append(StreamItemStatus.completed)

    referenced = {
        str(p)
        for p in (
            await db.execute(
                select(StreamPlanItem.prepared_file_path)
                .where(StreamPlanItem.prepared_file_path.isnot(None))
                .where(StreamPlanItem.stream_status.in_(active_statuses))
            )
        )
        .scalars()
        .all()
    }

    scanned = 0
    deleted = 0
    freed = 0
    for f in spool.iterdir():
        if not f.is_file():
            continue
        scanned += 1
        if str(f) in referenced:
            continue
        try:
            size = f.stat().st_size
            f.unlink()
            deleted += 1
            freed += size
        except Exception as e:
            logger.warning("cleanup.unlink_failed", path=str(f), error=str(e))

    logger.info("cleanup.prepared", scanned=scanned, deleted=deleted, freed=freed)
    return {"scanned": scanned, "deleted": deleted, "freed_bytes": freed}


async def cleanup_orphan_hls_segments(db: AsyncSession) -> dict:
    """Delete HLS segment files not referenced in the current playlist.

    FFmpeg's delete_segments flag only works reliably within a single continuous
    FFmpeg process. When the streamer starts a new FFmpeg process for each video
    item, old segments from previous runs are not deleted. This function provides
    external cleanup by reading the current playlist and deleting orphan segments.
    """
    spool = settings.spool_hls
    if not spool.exists():
        return {"scanned": 0, "deleted": 0, "freed_bytes": 0}

    playlist_path = spool / "stream.m3u8"
    if not playlist_path.exists():
        return {"scanned": 0, "deleted": 0, "freed_bytes": 0}

    # Read the current playlist to find referenced segments
    try:
        playlist_content = playlist_path.read_text()
        # Extract segment filenames from playlist (lines ending in .ts)
        referenced_segments = set(re.findall(r"seg_\d+\.ts", playlist_content))
    except Exception as e:
        logger.warning("cleanup.playlist_read_failed", path=str(playlist_path), error=str(e))
        return {"scanned": 0, "deleted": 0, "freed_bytes": 0, "error": "playlist_read_failed"}

    scanned = 0
    deleted = 0
    freed = 0
    for f in spool.iterdir():
        if not f.is_file() or not f.name.endswith(".ts") or f.name == "stream.m3u8":
            continue
        scanned += 1
        if f.name in referenced_segments:
            continue
        try:
            size = f.stat().st_size
            f.unlink()
            deleted += 1
            freed += size
            logger.info("cleanup.hls_segment_deleted", segment=f.name, size=size)
        except Exception as e:
            logger.warning("cleanup.unlink_failed", path=str(f), error=str(e))

    logger.info("cleanup.hls_segments", scanned=scanned, deleted=deleted, freed=freed)
    return {"scanned": scanned, "deleted": deleted, "freed_bytes": freed}


def disk_usage_spool() -> dict:
    """Total / used / free for the spool's mount point."""
    settings.ensure_spool_dirs()
    usage = shutil.disk_usage(str(settings.spool_root))
    return {
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_pct": round(usage.used / usage.total * 100, 1) if usage.total else None,
    }


async def run_cleanup_cycle(db: AsyncSession) -> dict:
    dl = await cleanup_orphan_downloads(db)
    pr = await cleanup_orphan_prepared(db)
    hls = await cleanup_orphan_hls_segments(db)
    return {
        "downloads": dl,
        "prepared": pr,
        "hls_segments": hls,
        "disk": disk_usage_spool(),
    }
