from pathlib import Path

import pytest

from app_factory import create_app
from extensions import db
from instagram_import import InstagramImportError, normalizar_url_instagram
from models import BrandProfile, MediaJob, User


@pytest.fixture()
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "STORAGE_DIR": str(tmp_path / "storage"),
        "SECRET_KEY": "test-secret",
        "TASKS_EAGER": False,
    })
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield app


def create_user(email, password="12345678"):
    user = User(email=email, monthly_limit=10)
    user.set_password(password)
    user.brand = BrandProfile(display_name="Teste", handle="@teste", avatar_key="avatar.png")
    db.session.add(user)
    db.session.commit()
    return user


def test_instagram_url_is_normalized():
    assert normalizar_url_instagram("https://instagram.com/reel/ABC_123/?igsh=x") == "https://www.instagram.com/reel/ABC_123/"
    with pytest.raises(InstagramImportError):
        normalizar_url_instagram("https://example.com/video/123")


def test_login_and_private_dashboard(app):
    client = app.test_client()
    with app.app_context():
        create_user("a@b.com")
    assert client.get("/dashboard").status_code == 302
    response = client.post("/login", data={"email":"a@b.com","password":"12345678"})
    assert response.status_code == 302
    assert client.get("/dashboard").status_code == 200


def test_job_isolation_between_users(app):
    client = app.test_client()
    with app.app_context():
        u1 = create_user("u1@test.com")
        u2 = create_user("u2@test.com")
        job = MediaJob(id="a"*32, user_id=u2.id, source_type="upload", original_name="x.mp4", status="ready")
        db.session.add(job)
        db.session.commit()

    client.post("/login", data={"email":"u1@test.com","password":"12345678"})
    assert client.get("/api/jobs/" + "a"*32).status_code == 404
