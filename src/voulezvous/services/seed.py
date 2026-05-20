import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.models.enums import AssetKind, AssetStatus, RightsStatus, SourceType
from voulezvous.models.tables import LibraryAsset

logger = structlog.get_logger()

DEMO_VIDEOS = [
    {
        "title": "Test Video 1 - Black Screen",
        "source_type": SourceType.uploaded_file,
        "local_source_path": "/spool/test_media/test1.mp4",
        "duration_sec": 10,
        "tags": ["test", "local"],
        "notes": "Generated locally: 10s black screen with 440Hz tone",
    },
    {
        "title": "Test Video 2 - Color Bars",
        "source_type": SourceType.uploaded_file,
        "local_source_path": "/spool/test_media/test2.mp4",
        "duration_sec": 10,
        "tags": ["test", "local"],
        "notes": "Generated locally: 10s color bars with 880Hz tone",
    },
    {
        "title": "Test Video 3 - Noise Pattern",
        "source_type": SourceType.uploaded_file,
        "local_source_path": "/spool/test_media/test3.mp4",
        "duration_sec": 10,
        "tags": ["test", "local"],
        "notes": "Generated locally: 10s noise pattern with 220Hz tone",
    },
]

DEMO_MUSIC = [
    {
        "title": "Ambient Background Loop A",
        "source_url": "",
        "duration_sec": 120,
        "tags": ["ambient", "background"],
        "notes": "Placeholder — operator must supply actual file",
    },
    {
        "title": "Lo-Fi Chill Beat B",
        "source_url": "",
        "duration_sec": 180,
        "tags": ["lofi", "background"],
        "notes": "Placeholder — operator must supply actual file",
    },
]


async def seed_demo_data(db: AsyncSession) -> dict:
    created = {"videos": 0, "music": 0}

    for v in DEMO_VIDEOS:
        asset = LibraryAsset(
            kind=AssetKind.video,
            title=v["title"],
            source_type=v["source_type"],
            local_source_path=v["local_source_path"],
            duration_sec=v["duration_sec"],
            tags=v["tags"],
            notes=v["notes"],
            rights_status=RightsStatus.approved_for_stream,
            status=AssetStatus.approved,
        )
        db.add(asset)
        created["videos"] += 1

    for m in DEMO_MUSIC:
        asset = LibraryAsset(
            kind=AssetKind.music,
            title=m["title"],
            source_type=SourceType.uploaded_file if not m["source_url"] else SourceType.direct_url,
            source_url=m["source_url"] or None,
            duration_sec=m["duration_sec"],
            tags=m["tags"],
            notes=m["notes"],
            rights_status=RightsStatus.pending_review,
            status=AssetStatus.registered,
        )
        db.add(asset)
        created["music"] += 1

    await db.commit()
    logger.info("seed_complete", created=created)
    return created
