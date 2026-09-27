from __future__ import annotations

import base64
import json
import urllib.request

from flask import current_app


def extract_caption(frame_bytes: bytes) -> str:
    api_key = current_app.config.get("CLAUDE_API_KEY", "")
    if not api_key:
        return ""

    media_type = "image/jpeg"
    if frame_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        media_type = "image/png"
    elif frame_bytes.startswith(b"\xff\xd8\xff"):
        media_type = "image/jpeg"
    elif frame_bytes[:4] == b"RIFF" and frame_bytes[8:12] == b"WEBP":
        media_type = "image/webp"

    payload = {
        "model": current_app.config["CLAUDE_MODEL"],
        "max_tokens": 512,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.b64encode(frame_bytes).decode("ascii"),
                    },
                },
                {
                    "type": "text",
                    "text": (
                        "Essa imagem é um frame de um post de rede social. "
                        "Extraia APENAS o texto principal da legenda/chamada que aparece acima do vídeo. "
                        "Não inclua nome do perfil, @, botões nem explicações. "
                        "Preserve emojis e quebras de linha. Se não houver texto claro, responda vazio."
                    ),
                },
            ],
        }],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    for block in data.get("content") or []:
        if block.get("type") == "text":
            return (block.get("text") or "").strip()
    return ""
