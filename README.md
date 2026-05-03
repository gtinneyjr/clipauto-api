"""
APScheduler background job: polls every N minutes for new uploads,
triggers the full pipeline (download → score → clip → publish).
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from datetime import datetime, timezone
import logging

from app.models.db import AsyncSessionLocal, Channel, Video, Clip, Publication, ClipStatus
from app.services.youtube import YouTubeService
from app.services.scoring import ScoringService
from app.services.clipping import ClippingService
from app.services.publishing import TikTokPublisher, InstagramPublisher, YouTubeShortsPublisher
from app.config import get_settings

settings  = get_settings()
log       = logging.getLogger("clipauto.scheduler")
scheduler = AsyncIOScheduler()


async def start_scheduler():
    scheduler.add_job(
        poll_all_channels,
        trigger=IntervalTrigger(minutes=settings.youtube_check_interval_minutes),
        id="poll_channels",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),   # run immediately on startup
    )
    scheduler.start()
    log.info("Scheduler started — polling every %d min", settings.youtube_check_interval_minutes)


async def stop_scheduler():
    scheduler.shutdown(wait=False)


# ── Main pipeline job ─────────────────────────────────────────────────────────

async def poll_all_channels():
    async with AsyncSessionLocal() as db:
        channels = (await db.execute(
            select(Channel).where(Channel.is_active == True)
        )).scalars().all()

    for channel in channels:
        try:
            await process_channel(channel)
        except Exception as exc:
            log.exception("Error processing channel %s: %s", channel.youtube_channel_id, exc)


async def process_channel(channel: Channel):
    yt      = YouTubeService()
    scorer  = ScoringService()
    clipper = ClippingService()

    log.info("Checking channel: %s", channel.channel_handle)

    new_videos = await yt.get_new_videos(
        channel_id=channel.youtube_channel_id,
        since=channel.last_checked_at,
    )

    async with AsyncSessionLocal() as db:
        channel = await db.merge(channel)
        channel.last_checked_at = datetime.now(timezone.utc)
        await db.commit()

    for vid_data in new_videos:
        await process_video(channel, vid_data, scorer, clipper)


async def process_video(channel: Channel, vid_data: dict, scorer: ScoringService, clipper: ClippingService):
    async with AsyncSessionLocal() as db:
        # Skip if already processed
        existing = (await db.execute(
            select(Video).where(Video.youtube_video_id == vid_data["youtube_video_id"])
        )).scalar_one_or_none()
        if existing and existing.processed:
            return

        if not existing:
            video = Video(
                channel_id=channel.id,
                **{k: v for k, v in vid_data.items() if k != "thumbnail_url"},
            )
            db.add(video)
            await db.commit()
            await db.refresh(video)
        else:
            video = existing

    log.info("Processing video: %s (%s)", video.title, video.youtube_video_id)

    try:
        # 1. Get transcript
        transcript = await clipper.get_transcript(video.youtube_video_id)

        # 2. Score moments with AI
        suggestions = await scorer.score_transcript(
            transcript=transcript,
            clip_length_seconds=channel.clip_length_seconds,
            max_clips=channel.clips_per_video,
        )

        if not suggestions:
            log.warning("No clip suggestions for %s", video.youtube_video_id)
            return

        # 3. Cut clips
        clip_results = await clipper.process_video(
            youtube_video_id=video.youtube_video_id,
            clip_suggestions=suggestions,
            caption_style=channel.caption_style,
        )

        # 4. Save clip records + publish
        async with AsyncSessionLocal() as db:
            video = await db.merge(video)
            for result in clip_results:
                clip = Clip(
                    video_id=video.id,
                    title=result["title"],
                    start_second=result["start_second"],
                    end_second=result["end_second"],
                    file_path=result["file_path"],
                    viral_score=result["viral_score"],
                    transcript_segment=result.get("segment_text"),
                    status=ClipStatus.ready,
                )
                db.add(clip)
                await db.flush()

                # 5. Publish to each connected platform
                for platform in channel.target_platforms:
                    pub = await _publish_to_platform(platform, clip, channel, db)
                    if pub:
                        db.add(pub)

            video.processed = True
            await db.commit()

    except Exception as exc:
        log.exception("Failed to process video %s: %s", video.youtube_video_id, exc)
        async with AsyncSessionLocal() as db:
            video = await db.merge(video)
            video.processed = True     # mark done to avoid retry loops; check logs
            await db.commit()


async def _publish_to_platform(platform: str, clip: Clip, channel: Channel, db) -> Publication | None:
    from sqlalchemy import select
    from app.models.db import OAuthToken

    token_row = (await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == channel.user_id,
            OAuthToken.platform == platform,
        )
    )).scalar_one_or_none()

    if not token_row:
        log.warning("No token for platform %s / user %s — skipping", platform, channel.user_id)
        return None

    access_token = token_row.access_token
    file_path    = clip.file_path

    pub = Publication(clip_id=clip.id, platform=platform, status="pending")

    try:
        if platform == "tiktok":
            publisher = TikTokPublisher()
            result = await publisher.publish_clip(
                access_token=access_token,
                clip_path=__import__("pathlib").Path(file_path),
                caption=clip.title,
                hashtags=["shorts", "viral", "fyp"],
            )
        elif platform == "youtube_shorts":
            publisher = YouTubeShortsPublisher()
            result = await publisher.publish_clip(
                access_token=access_token,
                clip_path=__import__("pathlib").Path(file_path),
                title=clip.title,
                description=f"🔥 {clip.title}\n\n#Shorts #Viral",
                tags=["Shorts", "viral", "highlights"],
            )
        elif platform == "instagram":
            # Instagram requires a publicly accessible URL — serve file via CDN/S3
            log.warning("Instagram publishing requires a public video URL (CDN). Skipping for now.")
            return None
        else:
            return None

        pub.platform_post_id = result.get("publish_id")
        pub.platform_url     = result.get("platform_url")
        pub.status           = result.get("status", "published")
        pub.published_at     = datetime.now(timezone.utc)

    except Exception as exc:
        log.exception("Publish to %s failed: %s", platform, exc)
        pub.status = "failed"
        pub.error  = str(exc)

    return pub
