"""Seed demo data for the acquisition subsystem."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from .enums import (
    AdapterType,
    CandidateRightsStatus,
    DiscoveryStatus,
    KeywordSource,
    RetrievalStatus,
    SearchMode,
)
from .models import (
    CandidateAsset,
    DomainPolicy,
    RetrievalAdapter,
    SearchKeyword,
)

logger = structlog.get_logger()


async def seed_acquisition_data(db: AsyncSession) -> dict:
    """Seed demo domain policies, keywords, and candidate assets."""

    # Domain policies
    policies = [
        DomainPolicy(
            domain="archive.org",
            is_enabled=True,
            session_profile_name=None,
            search_mode=SearchMode.keyword_search,
            allowed_actions={"search": True, "inspect": True, "download": True},
            retrieval_modes=["official_download", "direct_url"],
            requires_playback_verification=False,
            quality_floor="480p",
            max_pages_per_run=10,
            notes="Internet Archive — public domain content, direct downloads available",
        ),
        DomainPolicy(
            domain="vimeo.com",
            is_enabled=True,
            session_profile_name="vimeo_session",
            search_mode=SearchMode.keyword_search,
            allowed_actions={"search": True, "inspect": True},
            retrieval_modes=["official_download"],
            requires_playback_verification=True,
            quality_floor="720p",
            max_pages_per_run=5,
            notes="Vimeo — metadata extraction, download only if official button present",
        ),
        DomainPolicy(
            domain="pexels.com",
            is_enabled=True,
            session_profile_name=None,
            search_mode=SearchMode.keyword_search,
            allowed_actions={"search": True, "inspect": True, "download": True},
            retrieval_modes=["direct_url", "official_api"],
            requires_playback_verification=False,
            quality_floor="1080p",
            max_pages_per_run=8,
            notes="Pexels — free stock videos, direct downloads via API",
        ),
    ]
    for p in policies:
        db.add(p)
    await db.flush()

    # Keywords
    keywords = [
        # Include keywords
        SearchKeyword(keyword="ambient visuals", category="mood", weight=2.0,
                      include=True, source=KeywordSource.operator, active=True),
        SearchKeyword(keyword="nature documentary", category="theme", weight=1.8,
                      include=True, source=KeywordSource.operator, active=True),
        SearchKeyword(keyword="electronic music live", category="music", weight=1.5,
                      include=True, source=KeywordSource.operator, active=True),
        SearchKeyword(keyword="abstract art film", category="art", weight=1.5,
                      include=True, source=KeywordSource.operator, active=True),
        SearchKeyword(keyword="city timelapse", category="urban", weight=1.3,
                      include=True, source=KeywordSource.operator, active=True),
        SearchKeyword(keyword="ocean waves", category="nature", weight=1.2,
                      include=True, source=KeywordSource.operator, active=True),
        SearchKeyword(keyword="dj set", category="music", weight=2.0,
                      include=True, source=KeywordSource.operator, active=True),
        SearchKeyword(keyword="slow cinema", category="mood", weight=1.0,
                      include=True, source=KeywordSource.operator, active=True),
        # Exclude keywords
        SearchKeyword(keyword="copyright claim", category="exclusion", weight=1.0,
                      include=False, source=KeywordSource.operator, active=True),
        SearchKeyword(keyword="restricted", category="exclusion", weight=1.0,
                      include=False, source=KeywordSource.operator, active=True),
    ]
    for kw in keywords:
        db.add(kw)
    await db.flush()

    # Demo candidate assets — mix of authorized and metadata-only
    candidates = []

    # Archive.org candidates (authorized retrieval)
    archive_candidates = [
        ("Ambient Ocean Waves — 4K Relaxation", 1800,
         "https://archive.org/download/ambient-ocean/ocean_waves_4k.mp4"),
        ("City Skyline Timelapse — New York", 600,
         "https://archive.org/download/city-timelapse/nyc_timelapse.mp4"),
        ("Abstract Color Flow — Generative Art", 900,
         "https://archive.org/download/abstract-art/color_flow.mp4"),
        ("Mountain Sunrise Documentary", 2400,
         "https://archive.org/download/mountain-doc/sunrise.mp4"),
        ("Electronic Ambient Mix — 2 Hour Set", 7200,
         "https://archive.org/download/electronic-mix/ambient_set.mp4"),
        ("Deep Forest Walk — Nature Film", 1200,
         "https://archive.org/download/nature-walk/forest_walk.mp4"),
        ("Urban Night Drive — Lofi Visuals", 3600,
         "https://archive.org/download/urban-night/night_drive.mp4"),
        ("Underwater World — Coral Reef", 1500,
         "https://archive.org/download/underwater/coral_reef.mp4"),
    ]

    for title, duration, url in archive_candidates:
        c = CandidateAsset(
            domain_policy_id=policies[0].id,
            source_url=url,
            page_url=f"https://archive.org/details/{url.split('/')[-2]}",
            title=title,
            duration_sec=duration,
            quality_signals={"resolution": "1080p", "source": "archive.org"},
            tags=["ambient", "public_domain"],
            extra_metadata={"domain": "archive.org", "format": "mp4"},
            playback_verified=True,
            retrieval_status=RetrievalStatus.authorized_direct,
            rights_status=CandidateRightsStatus.approved_for_stream,
            discovery_status=DiscoveryStatus.accepted,
        )
        db.add(c)
        await db.flush()

        adapter = RetrievalAdapter(
            candidate_asset_id=c.id,
            adapter_type=AdapterType.official_download,
            adapter_spec={"url": url, "format": "mp4"},
        )
        db.add(adapter)
        c.retrieval_adapter_id = adapter.id
        candidates.append(c)

    # Vimeo candidates (metadata only — no authorized download)
    vimeo_candidates = [
        ("Cinematic Sunset — Drone Footage", 480),
        ("DJ Set @ Warehouse — Full Stream", 5400),
        ("Modern Dance Performance — 4K", 1800),
    ]
    for title, duration in vimeo_candidates:
        c = CandidateAsset(
            domain_policy_id=policies[1].id,
            source_url=None,
            page_url=f"https://vimeo.com/{hash(title) % 999999999}",
            title=title,
            duration_sec=duration,
            quality_signals={"resolution": "1080p", "source": "vimeo.com"},
            tags=["premium", "curated"],
            extra_metadata={"domain": "vimeo.com", "no_download": True},
            playback_verified=True,
            retrieval_status=RetrievalStatus.metadata_only,
            rights_status=CandidateRightsStatus.pending_review,
            discovery_status=DiscoveryStatus.inspected,
        )
        db.add(c)
        candidates.append(c)

    await db.commit()

    stats = {
        "domain_policies": len(policies),
        "keywords_include": len([k for k in keywords if k.include]),
        "keywords_exclude": len([k for k in keywords if not k.include]),
        "candidates_authorized": len(archive_candidates),
        "candidates_metadata_only": len(vimeo_candidates),
        "candidates_total": len(candidates),
    }
    logger.info("acquisition_seed_complete", **stats)
    return stats
