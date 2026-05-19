"""Upload HLS segments and playlist to Cloudflare R2."""

import mimetypes
from pathlib import Path

import structlog

from voulezvous.config import settings

logger = structlog.get_logger()


def _get_r2_client():
    """Create a boto3 S3 client configured for Cloudflare R2."""
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=(
            f"https://{settings.cloudflare_account_id}.r2.cloudflarestorage.com"
        ),
        aws_access_key_id=settings.cloudflare_r2_access_key,
        aws_secret_access_key=settings.cloudflare_r2_secret_key,
        region_name="auto",
    )


def upload_file(local_path: Path, r2_key: str) -> str:
    """Upload a single file to R2. Returns the public URL."""
    client = _get_r2_client()
    content_type = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"

    if local_path.suffix == ".m3u8":
        content_type = "application/vnd.apple.mpegurl"
    elif local_path.suffix == ".ts":
        content_type = "video/mp2t"

    client.upload_file(
        str(local_path),
        settings.cloudflare_r2_bucket,
        r2_key,
        ExtraArgs={"ContentType": content_type},
    )
    logger.info("r2_uploaded", key=r2_key, size=local_path.stat().st_size)

    if settings.cloudflare_r2_public_url:
        return f"{settings.cloudflare_r2_public_url.rstrip('/')}/{r2_key}"
    return f"https://{settings.cloudflare_r2_bucket}.r2.dev/{r2_key}"


def sync_hls_dir() -> int:
    """Upload all HLS files from spool to R2. Returns count of files uploaded."""
    if not settings.r2_enabled:
        logger.debug("r2_sync_skipped", reason="r2 not configured")
        return 0

    hls_dir = settings.spool_hls
    if not hls_dir.exists():
        return 0

    count = 0
    for f in hls_dir.iterdir():
        if f.suffix in (".m3u8", ".ts"):
            upload_file(f, f"hls/{f.name}")
            count += 1

    logger.info("r2_sync_complete", files=count)
    return count
