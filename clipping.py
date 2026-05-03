# app/routers/auth.py
"""
OAuth callback handlers for TikTok, Instagram, and Google/YouTube.
Flow: frontend redirects user → platform → /auth/{platform}/callback
"""
import secrets
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.models.db import get_db, OAuthToken
from app.services.publishing import TikTokPublisher, InstagramPublisher, YouTubeShortsPublisher

router = APIRouter()

_STATE_STORE: dict[str, str] = {}   # state → user_id (use Redis in production)


def _gen_state(user_id: str) -> str:
    state = secrets.token_urlsafe(16)
    _STATE_STORE[state] = user_id
    return state


def _consume_state(state: str) -> str:
    user_id = _STATE_STORE.pop(state, None)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    return user_id


async def _upsert_token(db: AsyncSession, user_id: str, platform: str, token_data: dict):
    existing = (await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == user_id,
            OAuthToken.platform == platform,
        )
    )).scalar_one_or_none()

    if existing:
        for k, v in token_data.items():
            setattr(existing, k, v)
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(OAuthToken(user_id=user_id, platform=platform, **token_data))

    await db.commit()


# ── TikTok ────────────────────────────────────────────────────────────────────

@router.get("/tiktok/start")
async def tiktok_auth_start(user_id: str = "demo_user"):
    state = _gen_state(user_id)
    url   = TikTokPublisher().get_auth_url(state)
    return RedirectResponse(url)


@router.get("/tiktok/callback")
async def tiktok_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    user_id = _consume_state(state)
    token   = await TikTokPublisher().exchange_code(code)
    await _upsert_token(db, user_id, "tiktok", token)
    return {"platform": "tiktok", "status": "connected"}


# ── Instagram ─────────────────────────────────────────────────────────────────

@router.get("/instagram/start")
async def instagram_auth_start(user_id: str = "demo_user"):
    state = _gen_state(user_id)
    url   = InstagramPublisher().get_auth_url(state)
    return RedirectResponse(url)


@router.get("/instagram/callback")
async def instagram_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    user_id = _consume_state(state)
    token   = await InstagramPublisher().exchange_code(code)
    await _upsert_token(db, user_id, "instagram", token)
    return {"platform": "instagram", "status": "connected"}


# ── Google / YouTube ──────────────────────────────────────────────────────────

@router.get("/google/start")
async def google_auth_start(user_id: str = "demo_user"):
    state = _gen_state(user_id)
    url   = YouTubeShortsPublisher().get_auth_url(state)
    return RedirectResponse(url)


@router.get("/google/callback")
async def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    user_id = _consume_state(state)
    token   = await YouTubeShortsPublisher().exchange_code(code)
    await _upsert_token(db, user_id, "youtube_shorts", token)
    return {"platform": "youtube_shorts", "status": "connected"}


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
async def auth_status(user_id: str = "demo_user", db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(OAuthToken).where(OAuthToken.user_id == user_id)
    )).scalars().all()
    return {r.platform: {"connected": True, "expiry": r.token_expiry} for r in rows}
