from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, JSON, Enum
from datetime import datetime, timezone
from typing import Optional, List
import enum
from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=settings.debug)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── Enums ─────────────────────────────────────────────────────────────────────

class ClipStatus(str, enum.Enum):
    pending   = "pending"
    processing = "processing"
    ready     = "ready"
    published  = "published"
    failed    = "failed"


class Platform(str, enum.Enum):
    tiktok    = "tiktok"
    youtube   = "youtube_shorts"
    instagram = "instagram"


# ── Models ────────────────────────────────────────────────────────────────────

class Channel(Base):
    """A YouTube channel being monitored."""
    __tablename__ = "channels"

    id: Mapped[int]            = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str]       = mapped_column(String, index=True)          # owner
    youtube_channel_id: Mapped[str] = mapped_column(String, unique=True)
    channel_handle: Mapped[str]     = mapped_column(String)
    channel_title: Mapped[str]      = mapped_column(String)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool]    = mapped_column(Boolean, default=True)
    clip_length_seconds: Mapped[int]  = mapped_column(Integer, default=40)
    clips_per_video: Mapped[int]      = mapped_column(Integer, default=3)
    caption_style: Mapped[str]        = mapped_column(String, default="auto")
    target_platforms: Mapped[list]    = mapped_column(JSON, default=list)
    created_at: Mapped[datetime]      = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    videos: Mapped[List["Video"]] = relationship(back_populates="channel", cascade="all, delete")


class Video(Base):
    """A YouTube video detected on a monitored channel."""
    __tablename__ = "videos"

    id: Mapped[int]               = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int]       = mapped_column(ForeignKey("channels.id"))
    youtube_video_id: Mapped[str] = mapped_column(String, unique=True)
    title: Mapped[str]            = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime] = mapped_column(DateTime)
    processed: Mapped[bool]       = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime]  = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    channel: Mapped["Channel"]    = relationship(back_populates="videos")
    clips: Mapped[List["Clip"]]   = relationship(back_populates="video", cascade="all, delete")


class Clip(Base):
    """A short-form clip extracted from a video."""
    __tablename__ = "clips"

    id: Mapped[int]               = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int]         = mapped_column(ForeignKey("videos.id"))
    title: Mapped[str]            = mapped_column(String)
    start_second: Mapped[float]   = mapped_column(Float)
    end_second: Mapped[float]     = mapped_column(Float)
    file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    viral_score: Mapped[float]    = mapped_column(Float, default=0.0)
    transcript_segment: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[ClipStatus]    = mapped_column(Enum(ClipStatus), default=ClipStatus.pending)
    created_at: Mapped[datetime]  = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    video: Mapped["Video"]        = relationship(back_populates="clips")
    publications: Mapped[List["Publication"]] = relationship(back_populates="clip", cascade="all, delete")


class Publication(Base):
    """Record of a clip being published to a platform."""
    __tablename__ = "publications"

    id: Mapped[int]               = mapped_column(Integer, primary_key=True)
    clip_id: Mapped[int]          = mapped_column(ForeignKey("clips.id"))
    platform: Mapped[Platform]    = mapped_column(Enum(Platform))
    platform_post_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    platform_url: Mapped[Optional[str]]     = mapped_column(String, nullable=True)
    views: Mapped[int]            = mapped_column(Integer, default=0)
    likes: Mapped[int]            = mapped_column(Integer, default=0)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str]           = mapped_column(String, default="pending")
    error: Mapped[Optional[str]]  = mapped_column(String, nullable=True)

    clip: Mapped["Clip"] = relationship(back_populates="publications")


class OAuthToken(Base):
    """Stored OAuth tokens per user+platform."""
    __tablename__ = "oauth_tokens"

    id: Mapped[int]               = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str]          = mapped_column(String, index=True)
    platform: Mapped[str]         = mapped_column(String)
    access_token: Mapped[str]     = mapped_column(String)
    refresh_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    token_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    scope: Mapped[Optional[str]]  = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime]  = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
