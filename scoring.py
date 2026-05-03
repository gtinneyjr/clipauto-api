from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.models.db import get_db, Channel
from app.services.youtube import YouTubeService

router = APIRouter()


class ConnectChannelRequest(BaseModel):
    url_or_handle: str
    clip_length_seconds: int = 40
    clips_per_video: int = 3
    caption_style: str = "auto"          # none | auto | viral
    target_platforms: list[str] = ["tiktok", "youtube_shorts"]
    user_id: str = "demo_user"           # replace with real auth


class ChannelResponse(BaseModel):
    id: int
    youtube_channel_id: str
    channel_handle: str
    channel_title: str
    thumbnail_url: Optional[str]
    is_active: bool
    last_checked_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/connect", response_model=ChannelResponse, status_code=201)
async def connect_channel(
    body: ConnectChannelRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Resolve a YouTube URL/handle and start monitoring the channel."""
    yt = YouTubeService()
    try:
        meta = await yt.resolve_channel(body.url_or_handle)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Upsert
    existing = (await db.execute(
        select(Channel).where(Channel.youtube_channel_id == meta["youtube_channel_id"])
    )).scalar_one_or_none()

    if existing:
        existing.is_active          = True
        existing.clip_length_seconds = body.clip_length_seconds
        existing.clips_per_video    = body.clips_per_video
        existing.caption_style      = body.caption_style
        existing.target_platforms   = body.target_platforms
        channel = existing
    else:
        channel = Channel(
            user_id=body.user_id,
            clip_length_seconds=body.clip_length_seconds,
            clips_per_video=body.clips_per_video,
            caption_style=body.caption_style,
            target_platforms=body.target_platforms,
            **meta,
        )
        db.add(channel)

    await db.commit()
    await db.refresh(channel)

    # Kick off immediate first-run in background
    from app.services.scheduler import process_channel
    background_tasks.add_task(process_channel, channel)

    return channel


@router.get("/channels", response_model=list[ChannelResponse])
async def list_channels(user_id: str = "demo_user", db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Channel).where(Channel.user_id == user_id, Channel.is_active == True)
    )).scalars().all()
    return rows


@router.delete("/channels/{channel_id}", status_code=204)
async def disconnect_channel(channel_id: int, db: AsyncSession = Depends(get_db)):
    channel = await db.get(Channel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel.is_active = False
    await db.commit()
