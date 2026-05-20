"""HLS serving router with correct MIME types."""

import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from voulezvous.config import settings

router = APIRouter(prefix="/hls", tags=["hls"])

# Allowed segment file extensions
SegmentExtensions = Literal[".ts", ".m4s"]


@router.get("/stream.m3u8")
async def serve_hls_playlist(request: Request) -> FileResponse:
    """Serve HLS playlist with correct MIME type."""
    playlist_path = settings.spool_hls / "stream.m3u8"

    if not playlist_path.exists():
        raise HTTPException(status_code=404, detail="Playlist not found")

    return FileResponse(
        playlist_path,
        media_type="application/vnd.apple.mpegurl",
        headers={
            "Cache-Control": "no-cache",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/{segment_name}")
async def serve_hls_segment(request: Request, segment_name: str) -> FileResponse:
    """Serve HLS segment with correct MIME type and path validation."""
    # Basic path validation - prevent directory traversal
    if ".." in segment_name or "/" in segment_name or "\\" in segment_name:
        raise HTTPException(status_code=400, detail="Invalid segment name")

    # Validate file extension
    if not any(segment_name.endswith(ext) for ext in [".ts", ".m4s"]):
        raise HTTPException(status_code=400, detail="Invalid segment extension")

    segment_path = settings.spool_hls / segment_name

    # Ensure file is within the HLS directory
    try:
        segment_path.resolve().relative_to(settings.spool_hls.resolve())
    except (ValueError, RuntimeError):
        raise HTTPException(status_code=400, detail="Path traversal detected")

    if not segment_path.exists():
        raise HTTPException(status_code=404, detail="Segment not found")

    return FileResponse(
        segment_path,
        media_type="video/mp2t",
        headers={
            "Cache-Control": "no-cache",
            "Access-Control-Allow-Origin": "*",
        },
    )
