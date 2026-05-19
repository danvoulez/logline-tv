import random
from datetime import date, datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from voulezvous.models.enums import AssetKind, AssetStatus, PlanStatus, RightsStatus
from voulezvous.models.tables import LibraryAsset, StreamPlan, StreamPlanItem

logger = structlog.get_logger()

DEFAULT_ITEM_DURATION_SEC = 600  # 10 min fallback if asset has no duration


async def generate_plan(
    db: AsyncSession,
    plan_date: date,
    hours: int = 24,
    mix_music: bool = False,
) -> StreamPlan:
    target_seconds = hours * 3600

    # Fetch approved video assets
    q_video = (
        select(LibraryAsset)
        .where(LibraryAsset.kind == AssetKind.video)
        .where(LibraryAsset.rights_status == RightsStatus.approved_for_stream)
        .where(
            LibraryAsset.status.in_(
                [AssetStatus.approved, AssetStatus.downloaded, AssetStatus.prepared]
            )
        )
    )
    result = await db.execute(q_video)
    video_assets = list(result.scalars().all())

    if not video_assets:
        raise ValueError("No approved video assets available for planning")

    # Fetch approved music assets if mixing
    music_assets: list[LibraryAsset] = []
    if mix_music:
        q_music = (
            select(LibraryAsset)
            .where(LibraryAsset.kind == AssetKind.music)
            .where(LibraryAsset.rights_status == RightsStatus.approved_for_stream)
            .where(
                LibraryAsset.status.in_(
                    [AssetStatus.approved, AssetStatus.downloaded, AssetStatus.prepared]
                )
            )
        )
        result = await db.execute(q_music)
        music_assets = list(result.scalars().all())

    start_dt = datetime(plan_date.year, plan_date.month, plan_date.day, tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(hours=hours)

    plan = StreamPlan(
        plan_date=plan_date,
        status=PlanStatus.draft,
        target_start_at=start_dt,
        target_end_at=end_dt,
    )
    db.add(plan)
    await db.flush()

    # Build items to fill target duration
    filled_seconds = 0
    sequence = 0
    last_video_id = None

    # Shuffle to provide variety, avoid immediate repeats
    shuffled_videos = list(video_assets)
    random.shuffle(shuffled_videos)
    video_idx = 0

    while filled_seconds < target_seconds:
        # Pick next video, avoid immediate repeat
        video = shuffled_videos[video_idx % len(shuffled_videos)]
        if video.id == last_video_id and len(shuffled_videos) > 1:
            video_idx += 1
            video = shuffled_videos[video_idx % len(shuffled_videos)]

        duration = video.duration_sec or DEFAULT_ITEM_DURATION_SEC
        item_start = start_dt + timedelta(seconds=filled_seconds)
        item_end = item_start + timedelta(seconds=duration)

        music_id = None
        use_mix = False
        if mix_music and music_assets:
            music_id = random.choice(music_assets).id
            use_mix = True

        item = StreamPlanItem(
            stream_plan_id=plan.id,
            sequence_index=sequence,
            video_asset_id=video.id,
            music_asset_id=music_id,
            planned_start_at=item_start,
            planned_end_at=item_end,
            target_duration_sec=duration,
            mix_enabled=use_mix,
        )
        db.add(item)

        last_video_id = video.id
        filled_seconds += duration
        sequence += 1
        video_idx += 1

        # Re-shuffle when we've cycled through
        if video_idx >= len(shuffled_videos):
            random.shuffle(shuffled_videos)
            video_idx = 0

    await db.commit()

    # Reload with items
    q = select(StreamPlan).where(StreamPlan.id == plan.id).options(selectinload(StreamPlan.items))
    result = await db.execute(q)
    plan = result.scalar_one()

    logger.info(
        "plan_generated",
        plan_id=str(plan.id),
        plan_date=str(plan_date),
        items=len(plan.items),
        total_seconds=filled_seconds,
    )
    return plan
