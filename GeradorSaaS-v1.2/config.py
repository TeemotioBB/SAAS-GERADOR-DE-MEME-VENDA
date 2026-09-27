import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _db_url():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{BASE_DIR / 'instance' / 'app.db'}"
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


class Config:
    APP_NAME = os.getenv("APP_NAME", "ClipFrame").strip() or "ClipFrame"
    SECRET_KEY = os.getenv("SECRET_KEY", "").strip() or "dev-change-me"
    SQLALCHEMY_DATABASE_URI = _db_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    MAX_VIDEO_UPLOAD_MB = int(os.getenv("MAX_VIDEO_UPLOAD_MB", "200"))
    MAX_CONTENT_LENGTH = MAX_VIDEO_UPLOAD_MB * 1024 * 1024
    MONTHLY_VIDEO_LIMIT = int(os.getenv("MONTHLY_VIDEO_LIMIT", "3"))

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 7

    STORAGE_DIR = os.getenv("STORAGE_DIR", str(BASE_DIR / "instance" / "storage"))
    REDIS_URL = os.getenv("REDIS_URL", "").strip()
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "").strip() or REDIS_URL or "memory://"
    TASKS_EAGER = os.getenv("TASKS_EAGER", "0") == "1"

    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "").strip()
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001").strip()
    AUTO_READ_CAPTION = os.getenv("AUTO_READ_CAPTION", "1") == "1"

    RAILWAY_FFMPEG_PRESET = os.getenv("RAILWAY_FFMPEG_PRESET", "veryfast").strip().lower()
    RAILWAY_FFMPEG_CRF = int(os.getenv("RAILWAY_FFMPEG_CRF", "18"))

    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()
    JOB_RETENTION_DAYS = int(os.getenv("JOB_RETENTION_DAYS", "7"))
