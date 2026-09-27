from __future__ import annotations

from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


def utcnow():
    return datetime.now(timezone.utc)


def current_period():
    return utcnow().strftime("%Y-%m")


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    account_active = db.Column(db.Boolean, nullable=False, default=True)
    plan_name = db.Column(db.String(50), nullable=False, default="Beta")
    monthly_limit = db.Column(db.Integer, nullable=False, default=100)
    usage_period = db.Column(db.String(7), nullable=False, default=current_period)
    usage_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_login_at = db.Column(db.DateTime(timezone=True))

    brand = db.relationship("BrandProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    jobs = db.relationship("MediaJob", back_populates="user", cascade="all, delete-orphan")

    @property
    def is_active(self):
        return bool(self.account_active)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def refresh_usage_period(self):
        periodo = current_period()
        if self.usage_period != periodo:
            self.usage_period = periodo
            self.usage_count = 0

    @property
    def remaining_quota(self):
        self.refresh_usage_period()
        return max(0, int(self.monthly_limit) - int(self.usage_count))


class BrandProfile(db.Model):
    __tablename__ = "brand_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(60), nullable=False, default="")
    handle = db.Column(db.String(60), nullable=False, default="")
    avatar_key = db.Column(db.String(500))
    logo_key = db.Column(db.String(500))
    use_logo_default = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", back_populates="brand")

    @property
    def configured(self):
        return bool(self.display_name.strip() and self.handle.strip() and self.avatar_key)


class MediaJob(db.Model):
    __tablename__ = "media_jobs"

    id = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = db.Column(db.String(20), nullable=False)  # upload | instagram
    source_url = db.Column(db.Text)
    original_name = db.Column(db.String(255), nullable=False, default="video.mp4")
    source_key = db.Column(db.String(500))
    frame_key = db.Column(db.String(500))
    result_key = db.Column(db.String(500))
    result_name = db.Column(db.String(255))

    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    crop = db.Column(db.JSON)
    confidence = db.Column(db.Float)
    suggested_caption = db.Column(db.Text)
    last_caption = db.Column(db.Text)

    status = db.Column(db.String(30), nullable=False, default="queued", index=True)
    error_message = db.Column(db.Text)
    generation_count = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", back_populates="jobs")

    def public_dict(self):
        return {
            "id": self.id,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "original_name": self.original_name,
            "status": self.status,
            "error": self.error_message,
            "width": self.width,
            "height": self.height,
            "crop": self.crop,
            "confidence": self.confidence,
            "suggested_caption": self.suggested_caption or "",
            "last_caption": self.last_caption or "",
            "has_frame": bool(self.frame_key),
            "has_result": bool(self.result_key),
            "result_name": self.result_name,
            "generation_count": self.generation_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
