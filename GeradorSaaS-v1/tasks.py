from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app_factory import create_app
from caption_service import extract_caption
from extensions import db
from instagram_import import baixar_video_instagram, InstagramImportError
from media_utils import ANALYSIS_WORKER, RENDER_WORKER, ffprobe_video, run, worker_json
from models import MediaJob, User
from storage import storage

app = create_app()


def _job_or_none(job_id: str):
    return db.session.get(MediaJob, job_id)


def _set_error(job: MediaJob, exc: Exception):
    job.status = "error"
    job.error_message = str(exc)[:3000]
    db.session.commit()



def _analyze_local_file(job: MediaJob, source_path: str):
    job.status = "analyzing"
    job.error_message = None
    db.session.commit()

    vw, vh, dur = ffprobe_video(source_path)
    with tempfile.TemporaryDirectory() as td:
        frame_path = os.path.join(td, "frame.jpg")
        run([
            "ffmpeg", "-y", "-ss", f"{max(0.0, dur / 2):.2f}", "-i", source_path,
            "-frames:v", "1", "-vf", "scale=720:-2:force_original_aspect_ratio=decrease",
            "-q:v", "4", frame_path,
        ], timeout=180)

        analysis = worker_json(ANALYSIS_WORKER, {"frame_path": frame_path}, timeout=120)
        fw = int(analysis.get("frame_w") or 0)
        fh = int(analysis.get("frame_h") or 0)
        box_frame = analysis.get("box")
        confidence = float(analysis.get("confianca") or 0.0)

        if fw <= 0 or fh <= 0:
            raise RuntimeError("A análise retornou dimensões inválidas.")

        if box_frame:
            sx, sy = vw / fw, vh / fh
            x, y, bw, bh = [int(v) for v in box_frame]
            crop = {
                "x": int(round(x * sx)),
                "y": int(round(y * sy)),
                "w": int(round(bw * sx)),
                "h": int(round(bh * sy)),
            }
        else:
            crop = {
                "x": int(vw * 0.08),
                "y": int(vh * 0.30),
                "w": int(vw * 0.84),
                "h": int(vw * 0.84),
            }
            confidence = 0.0

        frame_key = f"users/{job.user_id}/jobs/{job.id}/frame.jpg"
        storage.put_file(frame_key, frame_path, "image/jpeg")
        frame_bytes = Path(frame_path).read_bytes()

    job.width = vw
    job.height = vh
    job.crop = crop
    job.confidence = max(0.0, min(confidence, 1.0))
    job.frame_key = frame_key
    if app.config.get("AUTO_READ_CAPTION"):
        job.suggested_caption = extract_caption(frame_bytes)
    job.status = "ready"
    db.session.commit()


def analyze_uploaded_job(job_id: str):
    with app.app_context():
        job = _job_or_none(job_id)
        if not job or not job.source_key:
            return
        try:
            with tempfile.TemporaryDirectory() as td:
                src = os.path.join(td, "source.mp4")
                storage.download_to(job.source_key, src)
                _analyze_local_file(job, src)
        except Exception as exc:
            _set_error(job, exc)


def import_instagram_job(job_id: str):
    with app.app_context():
        job = _job_or_none(job_id)
        if not job:
            return
        job.status = "importing"
        db.session.commit()
        try:
            with tempfile.TemporaryDirectory() as td:
                path, name = baixar_video_instagram(
                    job.source_url or "",
                    td,
                    job.id,
                    limite_mb=app.config["MAX_VIDEO_UPLOAD_MB"],
                )
                source_key = f"users/{job.user_id}/jobs/{job.id}/source.mp4"
                storage.put_file(source_key, path, "video/mp4")
                job.source_key = source_key
                job.original_name = name
                db.session.commit()
                _analyze_local_file(job, path)
        except Exception as exc:
            _set_error(job, exc)


def render_job(
    job_id: str,
    caption: str,
    crop: dict | None,
    use_logo: bool,
    extra_edits: bool = False,
    mirror_video: bool = False,
    remove_metadata: bool = True,
):
    with app.app_context():
        job = _job_or_none(job_id)
        if not job or not job.source_key:
            return

        user = db.session.get(User, job.user_id)
        brand = user.brand if user else None
        if not user or not brand or not brand.configured:
            _set_error(job, RuntimeError("Configure sua página antes de gerar."))
            return

        try:
            with tempfile.TemporaryDirectory() as td:
                source_path = os.path.join(td, "source.mp4")
                output_path = os.path.join(td, "output.mp4")
                avatar_path = os.path.join(td, "avatar")
                logo_path = None
                storage.download_to(job.source_key, source_path)
                storage.download_to(brand.avatar_key, avatar_path)
                if use_logo and brand.logo_key:
                    logo_path = os.path.join(td, "logo")
                    storage.download_to(brand.logo_key, logo_path)

                brand_payload = {
                    "name": brand.display_name,
                    "handle": brand.handle,
                    "avatar_path": avatar_path,
                    "logo_path": logo_path,
                    "logo_opacity": 0.25,
                    "logo_width": 130,
                }
                uniqueness = {
                    # Edições visuais opcionais. O espelhamento fica separado
                    # para não inverter textos que já existam dentro do vídeo.
                    "edicoes_extras": bool(extra_edits),
                    "random_flip": False,
                    "mirror_video": bool(mirror_video),
                    "usar_logo": bool(use_logo and logo_path),
                    # Privacidade: ativado por padrão, mas controlado na interface.
                    "remove_metadata": bool(remove_metadata),
                    "deep_metadata_clean": bool(remove_metadata),
                    "remove_h264_sei": bool(remove_metadata),
                    "crf": int(app.config["RAILWAY_FFMPEG_CRF"]),
                    "preset": app.config["RAILWAY_FFMPEG_PRESET"],
                }
                worker_json(
                    RENDER_WORKER,
                    {
                        "entrada": source_path,
                        "saida": output_path,
                        "legenda": caption,
                        "crop": crop,
                        "brand": brand_payload,
                        "uniqueness": uniqueness,
                    },
                    timeout=1800,
                )
                if not os.path.isfile(output_path):
                    raise RuntimeError("O render terminou sem criar o arquivo final.")

                # Nunca sobrescreve a mesma URL de resultado. Browsers/CDNs podem
                # manter o MP4 antigo em cache, o que fazia desktop mostrar uma
                # geração anterior enquanto o celular já via a nova.
                next_generation = int(job.generation_count or 0) + 1
                result_key = f"users/{job.user_id}/jobs/{job.id}/result_v{next_generation}.mp4"
                old_result_key = job.result_key
                storage.put_file(result_key, output_path, "video/mp4")

            safe_base = Path(job.original_name or "video").stem[:80] or "video"
            job.result_key = result_key
            job.result_name = f"post_{safe_base}.mp4"
            job.last_caption = caption
            job.generation_count = next_generation
            job.status = "done"
            job.error_message = None

            user.refresh_usage_period()
            user.usage_count += 1
            db.session.commit()
            if old_result_key and old_result_key != result_key:
                storage.delete(old_result_key)
        except Exception as exc:
            _set_error(job, exc)
