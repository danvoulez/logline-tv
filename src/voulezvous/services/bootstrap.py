"""Boot-time tasks. Run once on API startup.

- Ensure fallback.mp4 exists in /spool/fallback/. If not, synthesize a 30s
  black-screen clip with a faint 440Hz tone so the streamer never sits in
  a warning-loop when the queue is dry.
"""

import asyncio

import structlog
from sqlalchemy import update

from voulezvous.config import settings
from voulezvous.database import async_session
from voulezvous.models.enums import PrepStatus
from voulezvous.models.tables import StreamPlanItem
from voulezvous.services.ffmpeg import run_ffmpeg

logger = structlog.get_logger()


async def ensure_fallback_video() -> None:
    settings.ensure_spool_dirs()
    fb = settings.fallback_video_path
    if fb.exists() and fb.stat().st_size > 0:
        logger.info("bootstrap.fallback_present", path=str(fb))
        return

    w, h = settings.house_resolution.split("x")
    args = [
        "-y",
        "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:d=3600:r={settings.house_frame_rate}",
        "-f", "lavfi", "-i", "sine=f=440:b=4:duration=3600",
        "-c:v", settings.house_video_codec,
        "-pix_fmt", "yuv420p",
        "-c:a", settings.house_audio_codec,
        "-ar", str(settings.house_audio_sample_rate),
        "-shortest",
        "-movflags", "+faststart",
        str(fb),
    ]
    rc, _, stderr = await run_ffmpeg(args)
    if rc != 0:
        logger.error("bootstrap.fallback_creation_failed", error=stderr[-500:])
    else:
        logger.info("bootstrap.fallback_created", path=str(fb), size=fb.stat().st_size)


async def reset_stale_preparing_items() -> None:
    """Reset items stuck in prep_status=preparing from a crashed worker."""
    async with async_session() as db:
        result = await db.execute(
            update(StreamPlanItem)
            .where(StreamPlanItem.prep_status == PrepStatus.preparing)
            .values(prep_status=PrepStatus.queued)
        )
        await db.commit()
        if result.rowcount:
            logger.warning("bootstrap.reset_stale_prep", count=result.rowcount)


async def run_boot_tasks() -> None:
    try:
        await ensure_fallback_video()
        await reset_stale_preparing_items()
    except Exception as e:
        logger.exception("bootstrap.failed", error=str(e))


def start_boot_tasks_in_background() -> None:
    """Spawn boot tasks as a background asyncio task — doesn't block startup."""
    loop = asyncio.get_event_loop()
    loop.create_task(run_boot_tasks())
