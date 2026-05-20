"""Boot-time tasks. Run once on API startup.

- Ensure fallback.mp4 exists in /spool/fallback/. If not, synthesize a 10s
  black-screen clip with a faint 440Hz tone so the streamer never sits in
  a warning-loop when the queue is dry.
- Generate local test media for Phase 2 admission testing.
"""

import asyncio

import structlog

from voulezvous.config import settings
from voulezvous.services.ffmpeg import run_ffmpeg

logger = structlog.get_logger()


async def generate_test_media() -> None:
    """Generate 3 deterministic local test videos for Phase 2 admission.

    Creates:
    - test1.mp4: 10s black screen with 440Hz tone
    - test2.mp4: 10s color bars with 880Hz tone
    - test3.mp4: 10s noise pattern with 220Hz tone
    """
    test_dir = settings.spool_root / "test_media"
    test_dir.mkdir(parents=True, exist_ok=True)

    test_videos = [
        ("test1.mp4", "color=c=black", "440"),
        ("test2.mp4", "color=c=red", "880"),
        ("test3.mp4", "color=c=blue", "220"),
    ]

    w, h = settings.house_resolution.split("x")

    for filename, video_filter, audio_freq in test_videos:
        output_path = test_dir / filename
        if output_path.exists() and output_path.stat().st_size > 0:
            logger.info("bootstrap.test_video_exists", path=str(output_path))
            continue

        video_input = f"{video_filter}:s={w}x{h}:d=10:r={settings.house_frame_rate}"

        args = [
            "-y",
            "-f",
            "lavfi",
            "-i",
            video_input,
            "-f",
            "lavfi",
            "-i",
            f"sine=f={audio_freq}:b=4:duration=10",
            "-c:v",
            settings.house_video_codec,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            settings.house_audio_codec,
            "-ar",
            str(settings.house_audio_sample_rate),
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        rc, _, stderr = await run_ffmpeg(args)
        if rc != 0:
            logger.error("bootstrap.test_video_creation_failed", path=str(output_path), error=stderr[-500:])
        else:
            logger.info("bootstrap.test_video_created", path=str(output_path), size=output_path.stat().st_size)


async def ensure_fallback_video() -> None:
    settings.ensure_spool_dirs()
    fb = settings.fallback_video_path
    _FALLBACK_BYTES = 100 * 1024  # 10s black screen w/ h264 is ~100KB
    if fb.exists() and fb.stat().st_size >= _FALLBACK_BYTES:
        logger.info("bootstrap.fallback_present", path=str(fb))
        return
    if fb.exists():
        fb.unlink()  # regenerate: file is too small or corrupted

    w, h = settings.house_resolution.split("x")
    args = [
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={w}x{h}:d=10:r={settings.house_frame_rate}",
        "-f",
        "lavfi",
        "-i",
        "sine=f=440:b=4:duration=10",
        "-c:v",
        settings.house_video_codec,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        settings.house_audio_codec,
        "-ar",
        str(settings.house_audio_sample_rate),
        "-shortest",
        "-movflags",
        "+faststart",
        str(fb),
    ]
    rc, _, stderr = await run_ffmpeg(args)
    if rc != 0:
        logger.error("bootstrap.fallback_creation_failed", error=stderr[-500:])
    else:
        logger.info("bootstrap.fallback_created", path=str(fb), size=fb.stat().st_size)


async def run_boot_tasks() -> None:
    try:
        await ensure_fallback_video()
        await generate_test_media()
    except Exception as e:
        logger.exception("bootstrap.failed", error=str(e))


def start_boot_tasks_in_background() -> None:
    """Spawn boot tasks as a background asyncio task — doesn't block startup."""
    loop = asyncio.get_event_loop()
    loop.create_task(run_boot_tasks())
