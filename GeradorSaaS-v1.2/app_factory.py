from __future__ import annotations

import os
from pathlib import Path
from datetime import timedelta
import click

from flask import Flask

from config import Config
from extensions import csrf, db, limiter, login_manager
from models import MediaJob, User, utcnow
from storage import storage


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["STORAGE_DIR"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Entre na sua conta para continuar."
    login_manager.login_message_category = "error"

    @login_manager.unauthorized_handler
    def unauthorized():
        from flask import jsonify, redirect, request, url_for
        if request.path.startswith("/api/"):
            return jsonify({"error": "Sua sessão expirou. Entre novamente."}), 401
        return redirect(url_for("auth.login", next=request.path))

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except Exception:
            return None

    from auth import auth_bp
    from main import main_bp
    from admin import admin_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)

    @app.before_request
    def enforce_active_account():
        from flask import jsonify, redirect, request, url_for
        from flask_login import current_user, logout_user
        if current_user.is_authenticated and not current_user.account_active:
            logout_user()
            if request.path.startswith("/api/"):
                return jsonify({"error": "Conta desativada."}), 403
            return redirect(url_for("auth.login"))

    @app.errorhandler(413)
    def too_large(_exc):
        from flask import jsonify, request
        if request.path.startswith("/api/"):
            return jsonify({"error": f"Arquivo muito grande. Limite: {app.config['MAX_VIDEO_UPLOAD_MB']} MB."}), 413
        return "Arquivo muito grande.", 413

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request_is_https():
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.cli.command("set-admin")
    @click.argument("email")
    def set_admin(email):
        user = User.query.filter_by(email=email.strip().lower()).first()
        if not user:
            raise click.ClickException("Usuário não encontrado.")
        user.is_admin = True
        db.session.commit()
        click.echo(f"Admin liberado: {user.email}")

    @app.cli.command("cleanup-media")
    @click.option("--days", type=int, default=None, help="Apaga jobs mais antigos que N dias.")
    def cleanup_media(days):
        days = days if days is not None else app.config["JOB_RETENTION_DAYS"]
        cutoff = utcnow() - timedelta(days=max(1, days))
        jobs = MediaJob.query.filter(MediaJob.created_at < cutoff).all()
        count = 0
        for job in jobs:
            for key in (job.source_key, job.frame_key, job.result_key):
                storage.delete(key)
            db.session.delete(job)
            count += 1
        db.session.commit()
        click.echo(f"{count} job(s) removidos.")

    with app.app_context():
        db.create_all()
        admin_email = app.config.get("ADMIN_EMAIL")
        if admin_email:
            existing = User.query.filter_by(email=admin_email).first()
            if existing and not existing.is_admin:
                existing.is_admin = True
                db.session.commit()

    return app


def request_is_https():
    # Railway/Cloudflare normalmente encaminham X-Forwarded-Proto.
    from flask import request
    return request.is_secure or request.headers.get("X-Forwarded-Proto", "").lower() == "https"
