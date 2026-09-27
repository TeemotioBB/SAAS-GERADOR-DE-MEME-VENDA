from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ANALYSIS_WORKER = str(BASE_DIR / "analysis_worker.py")
RENDER_WORKER = str(BASE_DIR / "render_worker.py")


def run(cmd, timeout=300):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "Comando falhou.")[-3000:])
    return result


def worker_json(worker_path: str, payload: dict, timeout=300):
    fd, json_path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        Path(json_path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        res = run([sys.executable, worker_path, json_path], timeout=timeout)
        lines = [x.strip() for x in res.stdout.splitlines() if x.strip()]
        if not lines:
            raise RuntimeError("Worker não retornou resposta.")
        data = json.loads(lines[-1])
        if not data.get("ok", True):
            raise RuntimeError(str(data.get("erro") or "Falha no worker."))
        return data
    finally:
        try:
            os.remove(json_path)
        except OSError:
            pass


def ffprobe_video(path: str):
    res = run([
        "ffprobe", "-v", "error", "-show_entries", "stream=width,height:format=duration",
        "-select_streams", "v:0", "-of", "json", path,
    ], timeout=60)
    data = json.loads(res.stdout)
    streams = data.get("streams") or []
    if not streams:
        raise RuntimeError("Arquivo sem faixa de vídeo válida.")
    w = int(streams[0]["width"])
    h = int(streams[0]["height"])
    dur = float((data.get("format") or {}).get("duration") or 0)
    if w <= 0 or h <= 0 or dur <= 0:
        raise RuntimeError("Vídeo inválido ou sem duração detectável.")
    return w, h, dur
