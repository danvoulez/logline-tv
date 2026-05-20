"""Upload HLS segments and playlist to Cloudflare R2.

Supports two modes:
1. Wrangler CLI (preferred) — uses `wrangler r2 object put` commands
2. boto3 S3 API — requires separate S3-compatible R2 API tokens

Wrangler mode is used by default if wrangler is available and configured.
Set CLOUDFLARE_R2_ACCESS_KEY + CLOUDFLARE_R2_SECRET_KEY to use boto3 mode instead.
"""

import asyncio
import shutil
from pathlib import Path

import structlog

from voulezvous.config import settings

logger = structlog.get_logger()


def _wrangler_available() -> bool:
    return shutil.which("wrangler") is not None


async def upload_file_wrangler(local_path: Path, r2_key: str) -> bool:
    """Upload a single file to R2 via Wrangler CLI."""
    bucket = settings.cloudflare_r2_bucket
    cmd = ["wrangler", "r2", "object", "put", f"{bucket}/{r2_key}", "--file", str(local_path)]
    logger.info("r2_wrangler_upload", key=r2_key)
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error("r2_wrangler_upload_failed", key=r2_key, error=stderr.decode()[-300:])
        return False
    logger.info("r2_uploaded", key=r2_key, size=local_path.stat().st_size)
    return True


def _upload_file_boto3_sync(local_path: Path, r2_key: str) -> str:
    """Synchronous boto3 upload — always call via asyncio.to_thread()."""
    import mimetypes

    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{settings.cloudflare_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.cloudflare_r2_access_key,
        aws_secret_access_key=settings.cloudflare_r2_secret_key,
        region_name="auto",
    )

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


async def upload_file_boto3(local_path: Path, r2_key: str) -> str:
    """Upload a single file to R2 via boto3, off the event loop."""
    return await asyncio.to_thread(_upload_file_boto3_sync, local_path, r2_key)


def _boto3_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.cloudflare_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.cloudflare_r2_access_key,
        aws_secret_access_key=settings.cloudflare_r2_secret_key,
        region_name="auto",
    )


def _list_r2_ts_keys_sync() -> set[str]:
    client = _boto3_client()
    keys: set[str] = set()
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.cloudflare_r2_bucket, Prefix="hls/"):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".ts"):
                keys.add(obj["Key"])
    return keys


def _delete_r2_keys_sync(keys: list[str]) -> None:
    if not keys:
        return
    client = _boto3_client()
    objects = [{"Key": k} for k in keys]
    client.delete_objects(
        Bucket=settings.cloudflare_r2_bucket,
        Delete={"Objects": objects, "Quiet": True},
    )
    logger.info("r2_pruned", count=len(keys))


async def sync_hls_dir() -> int:
    """Upload local HLS files to R2 and prune segments no longer on disk.

    Returns count of files uploaded.
    """
    hls_dir = settings.spool_hls
    if not hls_dir.exists():
        return 0

    use_wrangler = _wrangler_available() and not settings.r2_enabled
    if not use_wrangler and not settings.r2_enabled:
        logger.debug("r2_sync_skipped", reason="neither wrangler nor r2 credentials configured")
        return 0

    local_files = {f for f in hls_dir.iterdir() if f.suffix in (".m3u8", ".ts")}
    local_keys = {f"hls/{f.name}" for f in local_files}

    count = 0
    for f in sorted(local_files):
        r2_key = f"hls/{f.name}"
        if use_wrangler:
            ok = await upload_file_wrangler(f, r2_key)
            if ok:
                count += 1
        else:
            await upload_file_boto3(f, r2_key)
            count += 1

    # Prune stale .ts segments from R2 (boto3 only — wrangler has no list API)
    if not use_wrangler and settings.r2_enabled:
        try:
            remote_keys = await asyncio.to_thread(_list_r2_ts_keys_sync)
            stale = list(remote_keys - local_keys)
            if stale:
                await asyncio.to_thread(_delete_r2_keys_sync, stale)
        except Exception as e:
            logger.warning("r2_prune_failed", error=str(e))

    logger.info("r2_sync_complete", files=count, mode="wrangler" if use_wrangler else "boto3")
    return count
