from fastapi import APIRouter

router = APIRouter()

@router.get("/platforms")
async def list_platforms():
    """Return supported publishing platforms."""
    return [
        {"id": "tiktok",         "name": "TikTok",           "auth_url": "/auth/tiktok/start"},
        {"id": "youtube_shorts", "name": "YouTube Shorts",   "auth_url": "/auth/google/start"},
        {"id": "instagram",      "name": "Instagram Reels",  "auth_url": "/auth/instagram/start"},
    ]
