from __future__ import annotations

import io
import os
import tempfile
import uuid
import zipfile
from pathlib import Path

from flask import Blueprint, abort, after_this_request, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for, make_response
from flask_login import current_user, login_required
from sqlalchemy import select
from werkzeug.utils import secure_filename

from extensions import db, limiter
from caption_service import extract_caption
from instagram_import import InstagramImportError, normalizar_url_instagram
from models import BrandProfile, MediaJob, User
from queueing import enqueue
from storage import storage

main_bp = Blueprint("main", __name__)
ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm"}
ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def _job_for_user(job_id: str) -> MediaJob:
    job = db.session.get(MediaJob, job_id)
    if not job or job.user_id != current_user.id:
        abort(404)
    return job


def _require_brand():
    if not current_user.brand or not current_user.brand.configured:
        return False
    return True


@main_bp.get("/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@main_bp.get("/health")
def health():
    return jsonify({"ok": True})


@main_bp.get("/dashboard")
@login_required
def dashboard():
    current_user.refresh_usage_period()
    db.session.commit()
    recent_jobs = (
        MediaJob.query.filter_by(user_id=current_user.id)
        .order_by(MediaJob.created_at.desc())
        .limit(30)
        .all()
    )
    return render_template(
        "dashboard.html",
        brand=current_user.brand,
        recent_jobs=recent_jobs,
        remaining=current_user.remaining_quota,
    )


@main_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    brand = current_user.brand
    if brand is None:
        brand = BrandProfile(user_id=current_user.id)
        db.session.add(brand)

    if request.method == "POST":
        display_name = (request.form.get("display_name") or "").strip()[:60]
        handle = (request.form.get("handle") or "").strip()[:60]
        if handle and not handle.startswith("@"):
            handle = "@" + handle

        avatar = request.files.get("avatar")
        logo = request.files.get("logo")

        if not display_name:
            flash("Informe o nome da página.", "error")
            return render_template("settings.html", brand=brand)
        if not handle or len(handle) < 2:
            flash("Informe o @ da página.", "error")
            return render_template("settings.html", brand=brand)

        if avatar and avatar.filename:
            ext = Path(secure_filename(avatar.filename)).suffix.lower()
            if ext not in ALLOWED_IMAGE_EXT:
                flash("Avatar deve ser PNG, JPG ou WEBP.", "error")
                return render_template("settings.html", brand=brand)
            key = f"users/{current_user.id}/brand/avatar{ext}"
            storage.put_stream(key, avatar.stream, avatar.mimetype)
            if brand.avatar_key and brand.avatar_key != key:
                storage.delete(brand.avatar_key)
            brand.avatar_key = key

        if logo and logo.filename:
            ext = Path(secure_filename(logo.filename)).suffix.lower()
            if ext not in ALLOWED_IMAGE_EXT:
                flash("Logo deve ser PNG, JPG ou WEBP.", "error")
                return render_template("settings.html", brand=brand)
            key = f"users/{current_user.id}/brand/logo{ext}"
            storage.put_stream(key, logo.stream, logo.mimetype)
            if brand.logo_key and brand.logo_key != key:
                storage.delete(brand.logo_key)
            brand.logo_key = key

        if request.form.get("remove_logo") == "1" and brand.logo_key:
            storage.delete(brand.logo_key)
            brand.logo_key = None

        brand.display_name = display_name
        brand.handle = handle
        brand.use_logo_default = request.form.get("use_logo_default") == "1" and bool(brand.logo_key)
        db.session.commit()
        flash("Página salva.", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("settings.html", brand=brand)


@main_bp.get("/brand/avatar")
@login_required
def brand_avatar():
    brand = current_user.brand
    if not brand or not brand.avatar_key:
        abort(404)
    data = storage.read_bytes(brand.avatar_key)
    return send_file(io.BytesIO(data), mimetype="image/png", max_age=300)


@main_bp.get("/brand/logo")
@login_required
def brand_logo():
    brand = current_user.brand
    if not brand or not brand.logo_key:
        abort(404)
    data = storage.read_bytes(brand.logo_key)
    return send_file(io.BytesIO(data), mimetype="image/png", max_age=300)


@main_bp.get("/api/usage")
@login_required
def usage():
    current_user.refresh_usage_period()
    db.session.commit()
    return jsonify({
        "used": current_user.usage_count,
        "limit": current_user.monthly_limit,
        "remaining": current_user.remaining_quota,
        "plan": current_user.plan_name,
    })


@main_bp.post("/api/jobs/upload")
@login_required
@limiter.limit("30 per hour")
def upload_job():
    if not _require_brand():
        return jsonify({"error": "Configure sua página antes de adicionar vídeos."}), 409
    file = request.files.get("video")
    if not file or not file.filename:
        return jsonify({"error": "Selecione um vídeo."}), 400

    name = secure_filename(file.filename) or "video.mp4"
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXT:
        return jsonify({"error": "Formato não suportado. Use MP4, MOV, M4V ou WEBM."}), 400

    job_id = uuid.uuid4().hex
    key = f"users/{current_user.id}/jobs/{job_id}/source{ext}"
    storage.put_stream(key, file.stream, file.mimetype or "video/mp4")
    job = MediaJob(
        id=job_id,
        user_id=current_user.id,
        source_type="upload",
        original_name=name,
        source_key=key,
        status="queued",
    )
    db.session.add(job)
    db.session.commit()
    enqueue("tasks.analyze_uploaded_job", job.id, timeout=600)
    return jsonify(job.public_dict()), 202


@main_bp.post("/api/jobs/import")
@login_required
@limiter.limit("30 per hour")
def import_jobs():
    if not _require_brand():
        return jsonify({"error": "Configure sua página antes de importar Reels."}), 409
    data = request.get_json(silent=True) or {}
    raw_urls = data.get("urls") or []
    if isinstance(raw_urls, str):
        raw_urls = [raw_urls]
    if not isinstance(raw_urls, list) or not raw_urls:
        return jsonify({"error": "Cole pelo menos um link."}), 400
    if len(raw_urls) > 20:
        return jsonify({"error": "Importe no máximo 20 links por vez."}), 400

    created = []
    errors = []
    for raw in raw_urls:
        try:
            url = normalizar_url_instagram(str(raw))
        except InstagramImportError as exc:
            errors.append({"url": str(raw), "error": str(exc)})
            continue
        job = MediaJob(
            id=uuid.uuid4().hex,
            user_id=current_user.id,
            source_type="instagram",
            source_url=url,
            original_name="reel_instagram.mp4",
            status="queued",
        )
        db.session.add(job)
        db.session.flush()
        created.append(job)
    db.session.commit()

    for job in created:
        enqueue("tasks.import_instagram_job", job.id, timeout=900)

    return jsonify({"jobs": [j.public_dict() for j in created], "errors": errors}), 202


@main_bp.get("/api/jobs")
@login_required
def list_jobs():
    jobs = (
        MediaJob.query.filter_by(user_id=current_user.id)
        .order_by(MediaJob.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify({"jobs": [j.public_dict() for j in jobs]})


@main_bp.get("/api/jobs/<job_id>")
@login_required
def job_status(job_id):
    return jsonify(_job_for_user(job_id).public_dict())


@main_bp.get("/api/jobs/<job_id>/frame")
@login_required
def job_frame(job_id):
    job = _job_for_user(job_id)
    if not job.frame_key:
        abort(404)
    data = storage.read_bytes(job.frame_key)
    return send_file(io.BytesIO(data), mimetype="image/jpeg", max_age=60)


@main_bp.post("/api/jobs/<job_id>/caption")
@login_required
@limiter.limit("60 per hour")
def reread_caption(job_id):
    job = _job_for_user(job_id)
    if not job.frame_key:
        return jsonify({"error": "O frame ainda não está pronto."}), 409
    if not current_app.config.get("CLAUDE_API_KEY"):
        return jsonify({"error": "Leitura automática de texto não está configurada."}), 503

    try:
        text = extract_caption(storage.read_bytes(job.frame_key))
    except Exception as exc:
        return jsonify({"error": f"Falha ao ler o texto: {exc}"}), 502
    job.suggested_caption = text
    db.session.commit()
    return jsonify({"text": text})


def _normalize_crop_for_job(job, crop):
    """Normaliza o crop vindo do navegador para coordenadas reais do vídeo.

    Mantém o mesmo formato x/y/w/h do detector antigo, mas impede valores fora
    do frame e garante inteiros estáveis em qualquer navegador/dispositivo.
    """
    if not isinstance(crop, dict) or not job.width or not job.height:
        return job.crop
    try:
        x = int(round(float(crop.get("x", 0))))
        y = int(round(float(crop.get("y", 0))))
        w = int(round(float(crop.get("w", 0))))
        h = int(round(float(crop.get("h", 0))))
    except (TypeError, ValueError):
        return job.crop

    vw, vh = int(job.width), int(job.height)
    x = max(0, min(x, max(0, vw - 2)))
    y = max(0, min(y, max(0, vh - 2)))
    w = max(2, min(w, vw - x))
    h = max(2, min(h, vh - y))
    return {"x": x, "y": y, "w": w, "h": h}


@main_bp.post("/api/jobs/<job_id>/render")
@login_required
@limiter.limit("120 per hour")
def render(job_id):
    job = _job_for_user(job_id)
    if job.status not in {"ready", "done", "error"}:
        return jsonify({"error": "Este vídeo ainda não está pronto para gerar."}), 409
    if not job.source_key:
        return jsonify({"error": "Arquivo fonte indisponível."}), 409

    data = request.get_json(silent=True) or {}
    caption = (data.get("caption") or "").strip()
    crop = _normalize_crop_for_job(job, data.get("crop") if isinstance(data.get("crop"), dict) else job.crop)
    use_logo = bool(data.get("use_logo")) and bool(current_user.brand and current_user.brand.logo_key)
    extra_edits = bool(data.get("extra_edits"))
    mirror_video = bool(data.get("mirror_video"))
    # Se um navegador antigo não enviar a opção, preserva o comportamento
    # anterior e remove metadados por padrão.
    remove_metadata = data.get("remove_metadata", True) is not False

    # A chamada é opcional. Quando vazia, o render mantém apenas o cabeçalho
    # da página (avatar/nome/@), o vídeo e a logo opcional.

    # Bloqueia a linha do usuário no PostgreSQL para evitar exceder a cota com cliques concorrentes.
    stmt = select(User).where(User.id == current_user.id).with_for_update()
    user = db.session.execute(stmt).scalar_one()
    user.refresh_usage_period()
    in_progress = MediaJob.query.filter_by(user_id=user.id, status="rendering").count()
    if user.usage_count + in_progress >= user.monthly_limit:
        db.session.rollback()
        return jsonify({"error": "Seu limite mensal de vídeos foi atingido."}), 402

    job.status = "rendering"
    job.error_message = None
    job.last_caption = caption
    # Persiste exatamente o recorte que será renderizado. Assim um ajuste feito
    # no desktop/celular continua igual após refresh e em outro dispositivo.
    job.crop = crop
    db.session.commit()
    try:
        enqueue(
            "tasks.render_job",
            job.id, caption, crop, use_logo,
            extra_edits, mirror_video, remove_metadata,
            timeout=1800,
        )
    except Exception as exc:
        job.status = "ready"
        job.error_message = f"Fila indisponível: {exc}"
        db.session.commit()
        return jsonify({"error": job.error_message}), 503
    return jsonify({"ok": True, "job": job.public_dict()}), 202


@main_bp.get("/api/jobs/<job_id>/preview")
@login_required
def preview_result(job_id):
    job = _job_for_user(job_id)
    if not job.result_key:
        abort(404)
    if storage.remote:
        response = redirect(storage.presigned_get(job.result_key, expires=600))
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response
    data = storage.read_bytes(job.result_key)
    response = send_file(io.BytesIO(data), mimetype="video/mp4", conditional=True, max_age=0)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@main_bp.get("/api/jobs/<job_id>/download")
@login_required
def download_result(job_id):
    job = _job_for_user(job_id)
    if not job.result_key:
        abort(404)
    if storage.remote:
        response = redirect(storage.presigned_get(job.result_key, job.result_name or "video.mp4", expires=600))
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response
    data = storage.read_bytes(job.result_key)
    response = send_file(
        io.BytesIO(data),
        mimetype="video/mp4",
        as_attachment=True,
        download_name=job.result_name or "video.mp4",
        max_age=0,
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@main_bp.post("/api/jobs/zip")
@login_required
@limiter.limit("20 per hour")
def download_zip():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    if not isinstance(ids, list) or not ids:
        return jsonify({"error": "Nenhum vídeo selecionado."}), 400
    ids = ids[:50]

    jobs = MediaJob.query.filter(MediaJob.user_id == current_user.id, MediaJob.id.in_(ids)).all()
    jobs = [j for j in jobs if j.result_key]
    if not jobs:
        return jsonify({"error": "Nenhum resultado disponível."}), 404

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()
    try:
        used = set()
        with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
            for job in jobs:
                name = job.result_name or f"{job.id}.mp4"
                base, ext = os.path.splitext(name)
                candidate = name
                n = 2
                while candidate in used:
                    candidate = f"{base}_{n}{ext}"
                    n += 1
                used.add(candidate)
                with tempfile.NamedTemporaryFile(suffix=".mp4") as media_tmp:
                    storage.download_to(job.result_key, media_tmp.name)
                    zf.write(media_tmp.name, candidate)
        @after_this_request
        def cleanup_zip(response):
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
            return response
        return send_file(tmp.name, as_attachment=True, download_name="videos.zip", mimetype="application/zip")
    except Exception:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


@main_bp.delete("/api/jobs/<job_id>")
@login_required
def delete_job(job_id):
    job = _job_for_user(job_id)
    for key in (job.source_key, job.frame_key, job.result_key):
        storage.delete(key)
    db.session.delete(job)
    db.session.commit()
    return jsonify({"ok": True})


@main_bp.get("/terms")
def terms():
    return render_template("terms.html")


@main_bp.get("/privacy")
def privacy():
    return render_template("privacy.html")
