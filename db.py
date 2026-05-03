from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_secret: str = "change-me-in-production"
    debug: bool = False

    # Database
    database_url: str = "sqlite+aiosqlite:///./clipauto.db"

    # YouTube Data API v3
    youtube_api_key: str = ""
    youtube_check_interval_minutes: int = 15        # how often to poll for new videos

    # Google OAuth (for channel authentication)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    # TikTok OAuth
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_redirect_uri: str = "http://localhost:8000/auth/tiktok/callback"

    # Instagram / Facebook OAuth
    instagram_app_id: str = ""
    instagram_app_secret: str = ""
    instagram_redirect_uri: str = "http://localhost:8000/auth/instagram/callback"

    # FFmpeg
    ffmpeg_path: str = "ffmpeg"                     # or full path e.g. /usr/bin/ffmpeg
    clips_output_dir: str = "./output/clips"
    max_concurrent_jobs: int = 3

    # OpenAI (for viral moment scoring)
    openai_api_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
