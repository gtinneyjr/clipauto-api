# app/routers/clips.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.models.db import get_db, Clip, Video, Publication, ClipStatus

router = APIRouter()


class ClipOut(BaseModel):
    id: int
    video_id: int
    title: str
    start_second: float
    end_second: float
    viral_score: float
    status: ClipStatus
    file_path: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class PublicationOut(BaseModel):
    id: int
    clip_id: int
    platform: str
    platform_url: Optional[str]
    views: int
    likes: int
    status: str
    published_at: Optional[datetime]

    class Config:
        from_attributes = True


@router.get("/", response_model=list[ClipOut])
async def list_clips(
    video_id: Optional[int] = None,
    status: Optional[ClipStatus] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Clip)
    if video_id:
        q = q.where(Clip.video_id == video_id)
    if status:
        q = q.where(Clip.status == status)
    q = q.order_by(Clip.viral_score.desc())
    return (await db.execute(q)).scalars().all()


@router.get("/{clip_id}", response_model=ClipOut)
async def get_clip(clip_id: int, db: AsyncSession = Depends(get_db)):
    clip = await db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    return clip


@router.post("/{clip_id}/publish")
async def publish_clip(
    clip_id: int,
    platforms: list[str],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger publishing of a ready clip to specific platforms."""
    clip = await db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    if clip.status not in (ClipStatus.ready, ClipStatus.failed):
        raise HTTPException(status_code=400, detail=f"Clip status is '{clip.status}', cannot publish")

    background_tasks.add_task(_publish_clip_task, clip_id, platforms)
    return {"message": "Publishing started", "clip_id": clip_id, "platforms": platforms}


async def _publish_clip_task(clip_id: int, platforms: list[str]):
    from app.models.db import AsyncSessionLocal, Channel, Video, OAuthToken
    from app.services.publishing import TikTokPublisher, YouTubeShortsPublisher
    from pathlib import Path
    from sqlalchemy import select
    from datetime import timezone
    import logging
    log = logging.getLogger("clipauto.publish")

    async with AsyncSessionLocal() as db:
        clip  = await db.get(Clip, clip_id)
        video = await db.get(Video, clip.video_id)
        channel = await db.get(Channel, video.channel_id)

        for platform in platforms:
            token_row = (await db.execute(
                select(OAuthToken).where(
                    OAuthToken.user_id == channel.user_id,
                    OAuthToken.platform == platform,
                )
            )).scalar_one_or_none()

            if not token_row:
                log.warning("No token for %s", platform)
                continue

            pub = Publication(clip_id=clip_id, platform=platform, status="pending")
            db.add(pub)
            await db.flush()

            try:
                if platform == "tiktok":
                    result = await TikTokPublisher().publish_clip(
                        token_row.access_token, Path(clip.file_path), clip.title,
                    )
                elif platform == "youtube_shorts":
                    result = await YouTubeShortsPublisher().publish_clip(
                        token_row.access_token, Path(clip.file_path), clip.title,
                    )
                else:
                    continue

                pub.platform_post_id = result.get("publish_id")
                pub.platform_url     = result.get("platform_url")
                pub.status           = "published"
                pub.published_at     = datetime.now(timezone.utc)
                clip.status          = ClipStatus.published

            except Exception as e:
                pub.status = "failed"
                pub.error  = str(e)

        await db.commit()


@router.get("/{clip_id}/publications", response_model=list[PublicationOut])
async def list_publications(clip_id: int, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Publication).where(Publication.clip_id == clip_id)
    )).scalars().all()
    return rows
