"""HLS serving tests for MIME types and security."""

from unittest.mock import patch

import pytest

# Mock ensure_spool_dirs to prevent directory creation
with patch("voulezvous.config.Settings.ensure_spool_dirs", return_value=None):
    from fastapi.testclient import TestClient

    from voulezvous.api.app import app


client = TestClient(app)


@pytest.fixture
def mock_hls_dir(tmp_path):
    """Create a temporary HLS directory with test files."""
    hls_dir = tmp_path / "hls"
    hls_dir.mkdir()

    # Create test playlist
    playlist = hls_dir / "stream.m3u8"
    playlist.write_text("#EXTM3U\n#EXT-X-VERSION:6\n#EXTINF:10.0\nseg_00000.ts")

    # Create test segment
    segment = hls_dir / "seg_00000.ts"
    segment.write_bytes(b"fake segment data")

    return hls_dir


def test_playlist_mime_type(mock_hls_dir):
    """Test that playlist returns correct MIME type."""
    with patch("voulezvous.config.Settings.spool_hls", mock_hls_dir):
        response = client.get("/hls/stream.m3u8")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/vnd.apple.mpegurl"
        assert "#EXTM3U" in response.text


def test_segment_mime_type(mock_hls_dir):
    """Test that segment returns correct MIME type."""
    with patch("voulezvous.config.Settings.spool_hls", mock_hls_dir):
        response = client.get("/hls/seg_00000.ts")

        assert response.status_code == 200
        assert response.headers["content-type"] == "video/mp2t"
        assert response.content == b"fake segment data"


def test_missing_segment_returns_404(mock_hls_dir):
    """Test that missing segment returns 404."""
    with patch("voulezvous.config.Settings.spool_hls", mock_hls_dir):
        response = client.get("/hls/seg_99999.ts")

        assert response.status_code == 404


def test_path_traversal_rejected(mock_hls_dir):
    """Test that path traversal attempts are rejected."""
    with patch("voulezvous.config.Settings.spool_hls", mock_hls_dir):
        response = client.get("/hls/../etc/passwd")

        # FastAPI returns 404 for unmatched routes, which is acceptable security behavior
        assert response.status_code == 404


def test_path_traversal_with_slash_rejected(mock_hls_dir):
    """Test that path traversal with slash is rejected."""
    with patch("voulezvous.config.Settings.spool_hls", mock_hls_dir):
        response = client.get("/hls/seg_00000.ts/../../etc/passwd")

        # FastAPI returns 404 for unmatched routes, which is acceptable security behavior
        assert response.status_code == 404


def test_invalid_extension_rejected(mock_hls_dir):
    """Test that invalid file extensions are rejected."""
    with patch("voulezvous.config.Settings.spool_hls", mock_hls_dir):
        # Create a file with invalid extension
        (mock_hls_dir / "test.txt").write_text("not a segment")

        response = client.get("/hls/test.txt")

        assert response.status_code == 400


def test_cache_control_headers(mock_hls_dir):
    """Test that cache control headers are set correctly."""
    with patch("voulezvous.config.Settings.spool_hls", mock_hls_dir):
        response = client.get("/hls/stream.m3u8")

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"


def test_cors_headers(mock_hls_dir):
    """Test that CORS headers are set correctly."""
    with patch("voulezvous.config.Settings.spool_hls", mock_hls_dir):
        response = client.get("/hls/stream.m3u8")

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "*"
