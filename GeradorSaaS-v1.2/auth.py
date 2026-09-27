from __future__ import annotations

import re

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from extensions import db, limiter
from models import BrandProfile, User, utcnow

auth_bp = Blueprint("auth", __name__)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        accepted = request.form.get("terms") == "1"

        if not EMAIL_RE.match(email):
            flash("Digite um e-mail válido.", "error")
        elif len(password) < 8:
            flash("A senha precisa ter pelo menos 8 caracteres.", "error")
        elif password != confirm:
            flash("As senhas não coincidem.", "error")
        elif not accepted:
            flash("Você precisa aceitar os termos para criar a conta.", "error")
        elif User.query.filter_by(email=email).first():
            flash("Já existe uma conta com esse e-mail.", "error")
        else:
            admin_email = current_app.config.get("ADMIN_EMAIL", "")
            user = User(
                email=email,
                is_admin=bool(admin_email and email == admin_email),
                monthly_limit=current_app.config["MONTHLY_VIDEO_LIMIT"],
            )
            user.set_password(password)
            user.brand = BrandProfile(display_name="", handle="")
            db.session.add(user)
            db.session.commit()
            login_user(user, remember=True)
            flash("Conta criada. Agora configure sua página.", "success")
            return redirect(url_for("main.settings"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per hour")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("E-mail ou senha incorretos.", "error")
        elif not user.account_active:
            flash("Esta conta está desativada. Entre em contato com o suporte.", "error")
        else:
            user.last_login_at = utcnow()
            db.session.commit()
            login_user(user, remember=True)
            next_url = request.args.get("next")
            return redirect(next_url if next_url and next_url.startswith("/") else url_for("main.dashboard"))

    return render_template("login.html")


@auth_bp.post("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
