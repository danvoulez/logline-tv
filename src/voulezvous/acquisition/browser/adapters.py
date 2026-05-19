"""Domain adapters — structured rules for known site patterns.

Each adapter provides deterministic extraction before any LLM is consulted.
"""

import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass
class CandidateResult:
    title: str = ""
    page_url: str = ""
    source_url: str | None = None
    duration_sec: int | None = None
    quality_signals: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    has_authorized_retrieval: bool = False
    retrieval_type: str | None = None


class BaseDomainAdapter:
    """Base adapter with generic extraction rules."""

    domain_pattern: str = "*"
    search_url_template: str | None = None
    result_selector: str = "a[href]"
    title_selector: str = "h1, h2, .title"
    video_selector: str = "video, iframe"

    def matches(self, domain: str) -> bool:
        if self.domain_pattern == "*":
            return True
        return domain.endswith(self.domain_pattern) or domain == self.domain_pattern

    def build_search_url(self, domain: str, query: str) -> str | None:
        if self.search_url_template:
            return self.search_url_template.format(domain=domain, query=query)
        return f"https://{domain}/search?q={query}"

    def parse_duration(self, text: str) -> int | None:
        """Parse duration from text like '1:30:00' or '5:23' or '300s'."""
        if not text:
            return None
        # HH:MM:SS or MM:SS
        m = re.match(r"(\d+):(\d+):(\d+)", text)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        m = re.match(r"(\d+):(\d+)", text)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))
        m = re.match(r"(\d+)\s*s", text)
        if m:
            return int(m.group(1))
        try:
            return int(float(text))
        except (ValueError, TypeError):
            return None

    def classify_retrieval(self, url: str | None, page_info: dict) -> tuple[bool, str | None]:
        """Determine if URL represents an authorized retrieval path."""
        if not url:
            return False, None
        # Only allow clearly direct media URLs
        if any(url.lower().endswith(ext) for ext in [".mp4", ".webm", ".m3u8", ".mpd"]):
            return True, "direct_url"
        return False, None


class InternetArchiveAdapter(BaseDomainAdapter):
    """Adapter for archive.org — public domain content."""

    domain_pattern = "archive.org"
    search_url_template = "https://archive.org/search?query={query}&mediatype=movies"
    result_selector = ".result-item a, .item-ttl a"
    title_selector = ".item-title, h1"

    def build_search_url(self, domain: str, query: str) -> str:
        return f"https://archive.org/search?query={query}&mediatype=movies"

    def classify_retrieval(self, url: str | None, page_info: dict) -> tuple[bool, str | None]:
        if not url:
            return False, None
        # Only authorize URLs on archive.org itself
        if "archive.org" not in url:
            return False, None
        if "archive.org/download/" in url:
            return True, "official_download"
        if url.endswith((".mp4", ".ogv", ".webm")):
            return True, "direct_url"
        return False, None


class VimeoAdapter(BaseDomainAdapter):
    """Adapter for vimeo.com — official embeds and metadata."""

    domain_pattern = "vimeo.com"
    search_url_template = "https://vimeo.com/search?q={query}"
    result_selector = ".iris_video-vital a, a[href*='/video/'], a[href*='vimeo.com/']"

    def classify_retrieval(self, url: str | None, page_info: dict) -> tuple[bool, str | None]:
        # Vimeo does not offer direct downloads for most content
        # Only metadata_only unless there's an official download button
        if page_info.get("has_download_button"):
            return True, "official_download"
        return False, None


class GenericVideoAdapter(BaseDomainAdapter):
    """Generic adapter for any approved domain."""

    domain_pattern = "*"

    def classify_retrieval(self, url: str | None, page_info: dict) -> tuple[bool, str | None]:
        if not url:
            return False, None
        if any(url.lower().endswith(ext) for ext in [".mp4", ".webm", ".m3u8"]):
            return True, "direct_url"
        return False, None


# Registry of adapters, checked in order
ADAPTER_REGISTRY: list[BaseDomainAdapter] = [
    InternetArchiveAdapter(),
    VimeoAdapter(),
    GenericVideoAdapter(),
]


def get_adapter_for_domain(domain: str) -> BaseDomainAdapter:
    """Get the best adapter for a given domain."""
    for adapter in ADAPTER_REGISTRY:
        if adapter.matches(domain) and adapter.domain_pattern != "*":
            return adapter
    return GenericVideoAdapter()
