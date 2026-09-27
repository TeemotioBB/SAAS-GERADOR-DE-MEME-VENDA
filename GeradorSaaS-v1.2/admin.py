from __future__ import annotations

from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import User

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


@admin_bp.get("")
@login_required
@admin_required
def index():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin.html", users=users)


@admin_bp.post("/user/<int:user_id>")
@login_required
@admin_required
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    try:
        limit = max(0, min(int(request.form.get("monthly_limit", user.monthly_limit)), 100000))
    except ValueError:
        limit = user.monthly_limit
    user.monthly_limit = limit
    user.plan_name = (request.form.get("plan_name") or user.plan_name or "Beta").strip()[:50]
    if request.form.get("reset_usage") == "1":
        user.usage_count = 0
    if user.id != current_user.id:
        user.account_active = request.form.get("account_active") == "1"
    db.session.commit()
    flash("Usuário atualizado.", "success")
    return redirect(url_for("admin.index"))
