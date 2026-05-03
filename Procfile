"""
Publishing service — TikTok & Instagram Reels & YouTube Shorts.

Each platform has:
  get_auth_url()      → redirect user here to connect account
  exchange_code()     → swap auth code for access token
  publish_clip()      → upload video + caption
  refresh_token()     → keep tokens alive

TikTok: Content Posting API v2
Instagram: Graph API (Creator account required)
YouTube Shorts: YouTube Data API v3 (videos.insert)
"""

import httpx
import asyncio
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional
from app.config import get_settings

settings = get_settings()


# ── TikTok ────────────────────────────────────────────────────────────────────

class TikTokPublisher:
    AUTH_URL    = "https://www.tiktok.com/v2/auth/authorize/"
    TOKEN_URL   = "https://open.tiktokapis.com/v2/oauth/token/"
    UPLOAD_URL  = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    QUERY_URL   = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

    SCOPES = "user.info.basic,video.publish,video.upload"

    def get_auth_url(self, state: str) -> str:
        from urllib.parse import urlencode
        params = {
            "client_key":    settings.tiktok_client_key,
            "scope":         self.SCOPES,
            "response_type": "code",
            "redirect_uri":  settings.tiktok_redirect_uri,
            "state":         state,
        }
        return self.AUTH_URL + "?" + urlencode(params)

    async def exchange_code(self, code: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.TOKEN_URL, data={
                "client_key":    settings.tiktok_client_key,
                "client_secret": settings.tiktok_client_secret,
                "code":          code,
                "grant_type":    "authorization_code",
                "redirect_uri":  settings.tiktok_redirect_uri,
            })
            resp.raise_for_status()
            data = resp.json()["data"]
        return {
            "access_token":  data["access_token"],
            "refresh_token": data["refresh_token"],
            "token_expiry":  datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"]),
            "scope":         data.get("scope", self.SCOPES),
        }

    async def refresh_token(self, refresh_token: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.TOKEN_URL, data={
                "client_key":    settings.tiktok_client_key,
                "client_secret": settings.tiktok_client_secret,
                "grant_type":    "refresh_token",
                "refresh_token": refresh_token,
            })
            resp.raise_for_status()
            data = resp.json()["data"]
        return {
            "access_token":  data["access_token"],
            "refresh_token": data["refresh_token"],
            "token_expiry":  datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"]),
        }

    async def publish_clip(
        self,
        access_token: str,
        clip_path: Path,
        caption: str,
        hashtags: list[str] | None = None,
    ) -> dict:
        """
        Upload via TikTok's direct post API.
        Returns {"publish_id": "...", "platform_url": None} — URL available after processing.
        """
        full_caption = caption
        if hashtags:
            full_caption += " " + " ".join(f"#{h}" for h in hashtags)

        file_size = clip_path.stat().st_size
        headers   = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        # Step 1: Init upload
        async with httpx.AsyncClient() as client:
            init_resp = await client.post(self.UPLOAD_URL, headers=headers, json={
                "post_info": {
                    "title":            full_caption[:2200],
                    "privacy_level":    "PUBLIC_TO_EVERYONE",
                    "disable_duet":     False,
                    "disable_comment":  False,
                    "disable_stitch":   False,
                    "video_cover_timestamp_ms": 1000,
                },
                "source_info": {
                    "source":        "FILE_UPLOAD",
                    "video_size":    file_size,
                    "chunk_size":    file_size,
                    "total_chunk_count": 1,
                },
            })
            init_resp.raise_for_status()
            init_data  = init_resp.json()["data"]
            publish_id = init_data["publish_id"]
            upload_url = init_data["upload_url"]

            # Step 2: Upload binary
            with clip_path.open("rb") as f:
                video_bytes = f.read()
            put_resp = await client.put(
                upload_url,
                content=video_bytes,
                headers={"Content-Range": f"bytes 0-{file_size-1}/{file_size}",
                         "Content-Type": "video/mp4"},
            )
            put_resp.raise_for_status()

        return {"publish_id": publish_id, "platform_url": None, "status": "processing"}

    async def poll_status(self, access_token: str, publish_id: str) -> dict:
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.QUERY_URL, headers=headers,
                                     json={"publish_id": publish_id})
            resp.raise_for_status()
            data = resp.json()["data"]
        return {"status": data.get("status"), "share_url": data.get("share_url")}


# ── Instagram / Facebook Graph API ───────────────────────────────────────────

class InstagramPublisher:
    AUTH_URL    = "https://api.instagram.com/oauth/authorize"
    TOKEN_URL   = "https://api.instagram.com/oauth/access_token"
    GRAPH_URL   = "https://graph.facebook.com/v19.0"
    SCOPES      = "instagram_basic,instagram_content_publish,pages_show_list"

    def get_auth_url(self, state: str) -> str:
        from urllib.parse import urlencode
        params = {
            "client_id":    settings.instagram_app_id,
            "redirect_uri": settings.instagram_redirect_uri,
            "scope":        self.SCOPES,
            "response_type":"code",
            "state":        state,
        }
        return self.AUTH_URL + "?" + urlencode(params)

    async def exchange_code(self, code: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.TOKEN_URL, data={
                "client_id":     settings.instagram_app_id,
                "client_secret": settings.instagram_app_secret,
                "grant_type":    "authorization_code",
                "redirect_uri":  settings.instagram_redirect_uri,
                "code":          code,
            })
            resp.raise_for_status()
            data = resp.json()
        # Exchange short-lived for long-lived token
        long = await self._long_lived_token(data["access_token"])
        return {
            "access_token":  long["access_token"],
            "refresh_token": None,
            "token_expiry":  datetime.now(timezone.utc) + timedelta(days=60),
            "scope":         self.SCOPES,
        }

    async def _long_lived_token(self, short_token: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.GRAPH_URL}/oauth/access_token", params={
                "grant_type":        "ig_exchange_token",
                "client_secret":     settings.instagram_app_secret,
                "access_token":      short_token,
            })
            resp.raise_for_status()
        return resp.json()

    async def publish_clip(
        self,
        access_token: str,
        ig_user_id: str,
        video_url: str,             # publicly accessible URL to the clip
        caption: str,
        hashtags: list[str] | None = None,
    ) -> dict:
        full_caption = caption
        if hashtags:
            full_caption += "\n\n" + " ".join(f"#{h}" for h in hashtags)

        async with httpx.AsyncClient() as client:
            # Step 1: Create media container
            container = await client.post(
                f"{self.GRAPH_URL}/{ig_user_id}/media",
                params={
                    "media_type":  "REELS",
                    "video_url":   video_url,
                    "caption":     full_caption[:2200],
                    "access_token": access_token,
                },
            )
            container.raise_for_status()
            container_id = container.json()["id"]

            # Step 2: Poll until container is FINISHED
            for _ in range(30):
                await asyncio.sleep(5)
                status = await client.get(
                    f"{self.GRAPH_URL}/{container_id}",
                    params={"fields": "status_code", "access_token": access_token},
                )
                if status.json().get("status_code") == "FINISHED":
                    break

            # Step 3: Publish
            pub = await client.post(
                f"{self.GRAPH_URL}/{ig_user_id}/media_publish",
                params={"creation_id": container_id, "access_token": access_token},
            )
            pub.raise_for_status()
            media_id = pub.json()["id"]

        return {
            "publish_id":    media_id,
            "platform_url":  f"https://www.instagram.com/p/{media_id}/",
            "status":        "published",
        }


# ── YouTube Shorts ────────────────────────────────────────────────────────────

class YouTubeShortsPublisher:
    UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"

    def get_auth_url(self, state: str) -> str:
        from urllib.parse import urlencode
        params = {
            "client_id":     settings.google_client_id,
            "redirect_uri":  settings.google_redirect_uri,
            "response_type": "code",
            "scope":         "https://www.googleapis.com/auth/youtube.upload",
            "access_type":   "offline",
            "state":         state,
        }
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)

    async def exchange_code(self, code: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://oauth2.googleapis.com/token", data={
                "client_id":     settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code":          code,
                "grant_type":    "authorization_code",
                "redirect_uri":  settings.google_redirect_uri,
            })
            resp.raise_for_status()
            data = resp.json()
        return {
            "access_token":  data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "token_expiry":  datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"]),
            "scope":         data.get("scope"),
        }

    async def refresh_token(self, refresh_token: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://oauth2.googleapis.com/token", data={
                "client_id":     settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "grant_type":    "refresh_token",
                "refresh_token": refresh_token,
            })
            resp.raise_for_status()
            data = resp.json()
        return {
            "access_token": data["access_token"],
            "token_expiry": datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"]),
        }

    async def publish_clip(
        self,
        access_token: str,
        clip_path: Path,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
    ) -> dict:
        metadata = {
            "snippet": {
                "title":       title[:100],
                "description": description[:5000],
                "tags":        tags or [],
                "categoryId":  "22",    # People & Blogs
            },
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
        }

        import json as _json
        async with httpx.AsyncClient(timeout=300) as client:
            with clip_path.open("rb") as f:
                resp = await client.post(
                    self.UPLOAD_URL,
                    params={"uploadType": "multipart", "part": "snippet,status"},
                    headers={"Authorization": f"Bearer {access_token}"},
                    files={
                        "metadata": (None, _json.dumps(metadata), "application/json"),
                        "video":    (clip_path.name, f, "video/mp4"),
                    },
                )
            resp.raise_for_status()
            video_id = resp.json()["id"]

        return {
            "publish_id":   video_id,
            "platform_url": f"https://www.youtube.com/shorts/{video_id}",
            "status":       "published",
        }
