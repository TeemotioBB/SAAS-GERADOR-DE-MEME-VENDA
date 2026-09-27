#!/usr/bin/env python3
"""
Gerador de posts estilo tweet para a pagina de meme.
"""

import os
import sys
import json
import subprocess
import tempfile
import random
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageChops

try:
    from pilmoji import Pilmoji
    from pilmoji.source import BaseSource, TwitterEmojiSource
except ImportError:
    Pilmoji = None
    BaseSource = object
    TwitterEmojiSource = None

# ----------------- CONFIGURACOES FIXAS DO TEMPLATE -----------------
CANVAS_W = 1080
CANVAS_H = 1920
BG_COLOR = (255, 255, 255)

_BASE = os.path.dirname(os.path.abspath(__file__))


# ----------------- TEMPLATE FIXO DO SaaS -----------------
# Todos os clientes usam exatamente estas posições. Somente nome, @, avatar e
# logo mudam por conta. O render roda em processo isolado, então a identidade
# abaixo existe somente durante UMA renderização.
LAYOUT_PADRAO = {
    "margin_x": 90,
    "avatar_size": 110,
    "text_gap_x": 28,
    "gap_header_caption": 50,
    "gap_caption_video": 40,
    "card_radius": 28,
    "safe_margin_y": 80,
}

PROFILE_NAME = "Minha Página"
PROFILE_HANDLE = "@minhapagina"
AVATAR_PATH = ""
BRAND_LOGO_PATH = None
BRAND_LOGO_OPACITY = 0.25
BRAND_LOGO_WIDTH = 130

MARGIN_X = LAYOUT_PADRAO["margin_x"]
AVATAR_SIZE = LAYOUT_PADRAO["avatar_size"]
TEXT_GAP_X = LAYOUT_PADRAO["text_gap_x"]
GAP_HEADER_CAP = LAYOUT_PADRAO["gap_header_caption"]
GAP_CAP_VIDEO = LAYOUT_PADRAO["gap_caption_video"]
CARD_RADIUS = LAYOUT_PADRAO["card_radius"]
SAFE_MARGIN_Y = LAYOUT_PADRAO["safe_margin_y"]
PERFIL_ATUAL = "saas"


def set_brand(brand):
    """Aplica a identidade do cliente sem alterar o layout calibrado."""
    global PROFILE_NAME, PROFILE_HANDLE, AVATAR_PATH
    global BRAND_LOGO_PATH, BRAND_LOGO_OPACITY, BRAND_LOGO_WIDTH
    global MARGIN_X, AVATAR_SIZE, TEXT_GAP_X
    global GAP_HEADER_CAP, GAP_CAP_VIDEO, CARD_RADIUS, SAFE_MARGIN_Y

    brand = brand or {}
    PROFILE_NAME = str(brand.get("name") or "Minha Página").strip()[:60]
    handle = str(brand.get("handle") or "@minhapagina").strip()[:60]
    PROFILE_HANDLE = handle if handle.startswith("@") else "@" + handle
    AVATAR_PATH = str(brand.get("avatar_path") or "").strip()
    BRAND_LOGO_PATH = str(brand.get("logo_path") or "").strip() or None
    BRAND_LOGO_OPACITY = float(brand.get("logo_opacity") or 0.25)
    BRAND_LOGO_WIDTH = int(brand.get("logo_width") or 130)

    layout = LAYOUT_PADRAO
    MARGIN_X = layout["margin_x"]
    AVATAR_SIZE = layout["avatar_size"]
    TEXT_GAP_X = layout["text_gap_x"]
    GAP_HEADER_CAP = layout["gap_header_caption"]
    GAP_CAP_VIDEO = layout["gap_caption_video"]
    CARD_RADIUS = layout["card_radius"]
    SAFE_MARGIN_Y = layout["safe_margin_y"]


def _achar_fonte(*nomes):
    pastas = [
        os.path.join(_BASE, "fontes"),
        "/usr/share/fonts/truetype/liberation",
        "/usr/share/fonts/truetype/dejavu",
        os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
        "/Library/Fonts", "/System/Library/Fonts", "/System/Library/Fonts/Supplemental",
        _BASE,
    ]
    for nome in nomes:
        if os.path.isabs(nome) and os.path.exists(nome):
            return nome
        for pasta in pastas:
            caminho = os.path.join(pasta, nome)
            if os.path.exists(caminho):
                return caminho
    return None


FONT_BOLD = _achar_fonte("LiberationSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf")
FONT_REG = _achar_fonte("LiberationSans-Regular.ttf", "arial.ttf", "Arial.ttf", "DejaVuSans.ttf")


def _font(caminho, tamanho):
    if caminho:
        return ImageFont.truetype(caminho, tamanho)
    return ImageFont.load_default()


def _achar_fonte_emoji():
    """Procura uma fonte colorida de emojis instalada no sistema."""
    caminhos = [
        os.path.join(_BASE, "fontes", "NotoColorEmoji.ttf"),
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/usr/share/fonts/noto/NotoColorEmoji.ttf",
        "/usr/local/share/fonts/NotoColorEmoji.ttf",
    ]
    for caminho in caminhos:
        if os.path.exists(caminho):
            return caminho
    return None


class _FonteEmojiLocal(BaseSource):
    """Transforma emojis da Noto Color Emoji em PNG para o Pilmoji."""

    def __init__(self, caminho_fonte):
        self.fonte = ImageFont.truetype(caminho_fonte, 109)
        self.cache = {}

    def get_emoji(self, emoji, /):
        if emoji in self.cache:
            return BytesIO(self.cache[emoji])

        tamanho = 160
        asset = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
        draw = ImageDraw.Draw(asset)
        try:
            bbox = draw.textbbox((0, 0), emoji, font=self.fonte, embedded_color=True)
            largura = bbox[2] - bbox[0]
            altura = bbox[3] - bbox[1]
            x = (tamanho - largura) / 2 - bbox[0]
            y = (tamanho - altura) / 2 - bbox[1]
            draw.text((x, y), emoji, font=self.fonte, embedded_color=True)
        except Exception:
            return None

        if asset.getbbox() is None:
            return None

        buf = BytesIO()
        asset.save(buf, format="PNG")
        dados = buf.getvalue()
        self.cache[emoji] = dados
        return BytesIO(dados)

    def get_discord_emoji(self, id, /):
        return None


def _criar_fonte_emoji():
    caminho = _achar_fonte_emoji()
    if caminho and Pilmoji is not None:
        try:
            return _FonteEmojiLocal(caminho)
        except Exception:
            pass
    return TwitterEmojiSource if TwitterEmojiSource is not None else None


COLOR_NAME = (15, 20, 25)
COLOR_HANDLE = (83, 100, 113)
COLOR_CAPTION = (15, 20, 25)



def run(cmd):
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Comando falhou:\n{' '.join(cmd)}\n\n{res.stderr[-2000:]}")
    return res


def get_video_size(path):
    res = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", path])
    info = json.loads(res.stdout)["streams"][0]
    return int(info["width"]), int(info["height"])


def has_audio(path):
    res = run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "json", path])
    return len(json.loads(res.stdout).get("streams", [])) > 0


def get_duration(path):
    res = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path])
    return float(json.loads(res.stdout)["format"]["duration"])


# ====================== PRIVACIDADE E QUALIDADE VISUAL ======================
def _metadata_clean_args():
    """Impede a cópia de dados pessoais e tags do arquivo de origem."""
    return [
        "-map_metadata", "-1",
        "-map_chapters", "-1",
        "-metadata", "title=",
        "-metadata", "artist=",
        "-metadata", "author=",
        "-metadata", "comment=",
        "-metadata", "description=",
        "-metadata", "copyright=",
        "-metadata", "creation_time=",
        "-metadata", "date=",
        "-metadata", "location=",
        "-metadata", "location-eng=",
        "-metadata", "make=",
        "-metadata", "model=",
        "-metadata", "software=",
        "-metadata", "encoder=",
        "-metadata:s:v:0", "title=",
        "-metadata:s:v:0", "encoder=",
        "-metadata:s:v:0", "handler_name=",
        "-metadata:s:a:0", "title=",
        "-metadata:s:a:0", "encoder=",
        "-metadata:s:a:0", "handler_name=",
    ]


def deep_clean_mp4(input_path, output_path, remove_sei=True):
    """Limpeza final por stream copy: não decodifica nem recomprime o vídeo."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-c", "copy",
        "-sn", "-dn",
    ]
    cmd += _metadata_clean_args()
    cmd += ["-fflags", "+bitexact"]

    # Como a saída principal é sempre H.264, remove mensagens SEI internas.
    # Pode remover closed captions embutidas, mas não textos visíveis no vídeo.
    if remove_sei:
        cmd += ["-bsf:v", "filter_units=remove_types=6"]

    cmd += ["-movflags", "+faststart", output_path]
    run(cmd)
    return output_path



def _normalizar_preset_ffmpeg(valor):
    """Evita presets extremamente lentos no gerador de alto volume."""
    preset = str(valor or "veryfast").strip().lower()
    permitidos = {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium"}
    if preset not in permitidos:
        return "veryfast"
    return preset


def _normalizar_opcoes_uniqueness(options):
    """Normaliza opções de uniqueness.

    Chaves principais (desligadas por padrão):
    - edicoes_extras: ativa cor, grão, vinheta, zoom, crop leve e velocidade aleatória
    - usar_logo: ativa a logomarca do perfil atual
    """
    options = dict(options or {})

    try:
        crf_solicitado = int(options.get("crf", 18))
    except (TypeError, ValueError):
        crf_solicitado = 18
    crf = max(0, min(crf_solicitado, 18))

    # Chave mestre das edições extras (OFF por padrão)
    edicoes_extras = bool(options.get("edicoes_extras", False))

    # Chave da logomarca (OFF por padrão)
    usar_logo = bool(options.get("usar_logo", False))

    # Velocidade: só randomiza se edicoes_extras estiver ligada
    try:
        speed = float(options.get("speed_factor", 1.0))
    except (TypeError, ValueError):
        speed = 1.0

    if edicoes_extras:
        # Se veio 0 ou 1.0, randomiza; senão respeita o valor enviado
        if speed <= 0 or abs(speed - 1.0) < 0.001:
            speed = round(random.uniform(0.97, 1.04), 4)
    else:
        speed = 1.0

    if speed <= 0:
        speed = 1.0

    remove_metadata = bool(options.get("remove_metadata", True))

    return {
        "edicoes_extras": edicoes_extras,
        "usar_logo": usar_logo,
        # Espelhamento é independente das edições extras. Isso evita inverter
        # textos que já façam parte dos pixels do vídeo quando o usuário não quiser.
        "mirror_video": bool(options.get("mirror_video", False)),
        # Sub-opções só fazem efeito se edicoes_extras=True
        "light_crop": bool(options.get("light_crop", True)),
        "color_adjust": bool(options.get("color_adjust", True)),
        "subtle_grain": bool(options.get("subtle_grain", True)),
        "stronger_visuals": bool(options.get("stronger_visuals", True)),
        # Mantida apenas por compatibilidade com payloads antigos. A interface
        # SaaS v1.3 não usa flip aleatório dentro de edições extras.
        "random_flip": bool(options.get("random_flip", False)),
        "vignette": bool(options.get("vignette", True)),
        "dynamic_zoom": bool(options.get("dynamic_zoom", True)),
        "speed_factor": speed,
        "crf": crf,
        # veryfast mantém o mesmo CRF/qualidade-alvo, mas reduz bastante o uso
        # de CPU em comparação com slow.
        "preset": _normalizar_preset_ffmpeg(options.get("preset", "veryfast")),
        "remove_metadata": remove_metadata,
        "deep_metadata_clean": remove_metadata and bool(options.get("deep_metadata_clean", True)),
        "remove_h264_sei": remove_metadata and bool(options.get("remove_h264_sei", True)),
    }


def _atempo_filter(speed):
    """Monta uma cadeia atempo válida mesmo para valores fora de 0.5–2.0."""
    fatores = []
    restante = float(speed)

    while restante > 2.0:
        fatores.append(2.0)
        restante /= 2.0
    while restante < 0.5:
        fatores.append(0.5)
        restante /= 0.5

    fatores.append(restante)
    return ",".join(f"atempo={fator:.8f}" for fator in fatores)


# ====================== RESTO DO CÓDIGO (mantido limpo) ======================

def build_overlay(caption, video_disp_w, video_disp_h, video_y, header_y):
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), BG_COLOR + (255,))
    draw = ImageDraw.Draw(img)

    f_name = _font(FONT_BOLD, 40)
    f_handle = _font(FONT_REG, 36)
    f_caption = _font(FONT_BOLD, 44)

    av = None
    if os.path.exists(AVATAR_PATH):
        av = Image.open(AVATAR_PATH).convert("RGBA")

    if av is not None:
        # ImageOps.fit faz um recorte central quadrado antes de aplicar a máscara,
        # evitando deformação e garantindo a foto redondinha.
        from PIL import ImageOps
        av = ImageOps.fit(av, (AVATAR_SIZE, AVATAR_SIZE), method=Image.LANCZOS, centering=(0.5, 0.45))
        escala = 4
        mascara_g = Image.new("L", (AVATAR_SIZE * escala, AVATAR_SIZE * escala), 0)
        ImageDraw.Draw(mascara_g).ellipse((0, 0, AVATAR_SIZE * escala - 1, AVATAR_SIZE * escala - 1), fill=255)
        mascara = mascara_g.resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)
        alpha_atual = av.split()[3]
        nova_alpha = ImageChops.multiply(alpha_atual, mascara)
        av.putalpha(nova_alpha)
        img.paste(av, (MARGIN_X, header_y), av)

    text_x = MARGIN_X + AVATAR_SIZE + TEXT_GAP_X
    draw.text((text_x, header_y + 12), PROFILE_NAME, font=f_name, fill=COLOR_NAME)
    draw.text((text_x, header_y + 62), PROFILE_HANDLE, font=f_handle, fill=COLOR_HANDLE)

    caption_y = header_y + AVATAR_SIZE + GAP_HEADER_CAP
    max_w = CANVAS_W - 2 * MARGIN_X
    line_h = 58

    # Renderiza a legenda em uma camada separada para aceitar emojis coloridos.
    legenda_renderizada = False
    if Pilmoji is not None:
        camada_legenda = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        draw_legenda = ImageDraw.Draw(camada_legenda)
        fonte_emoji = _criar_fonte_emoji()
        if fonte_emoji is not None:
            try:
                with Pilmoji(
                    camada_legenda,
                    source=fonte_emoji,
                    draw=draw_legenda,
                    emoji_scale_factor=1.05,
                    emoji_position_offset=(0, 4),
                ) as emoji_draw:
                    lines = wrap_text(caption, f_caption, max_w, draw_legenda, emoji_draw)
                    for i, line in enumerate(lines):
                        emoji_draw.text(
                            (MARGIN_X, caption_y + i * line_h),
                            line,
                            font=f_caption,
                            fill=COLOR_CAPTION,
                            emoji_scale_factor=1.05,
                            emoji_position_offset=(0, 4),
                        )
                img.alpha_composite(camada_legenda)
                legenda_renderizada = True
            except Exception:
                legenda_renderizada = False

    # Fallback: mantém o gerador funcionando mesmo se o serviço de emojis falhar.
    if not legenda_renderizada:
        lines = wrap_text(caption, f_caption, max_w, draw)
        for i, line in enumerate(lines):
            draw.text((MARGIN_X, caption_y + i * line_h), line, font=f_caption, fill=COLOR_CAPTION)

    card_w = video_disp_w
    card_x = (CANVAS_W - card_w) // 2
    card_h = video_disp_h
    hole_full = Image.new("L", (CANVAS_W, CANVAS_H), 0)
    hole_card = Image.new("L", (card_w, card_h), 0)
    ImageDraw.Draw(hole_card).rounded_rectangle((0, 0, card_w, card_h), radius=CARD_RADIUS, fill=255)
    hole_full.paste(hole_card, (card_x, video_y))
    alpha = img.split()[3]
    inv = Image.eval(hole_full, lambda v: 255 - v)
    new_alpha = ImageChops.multiply(alpha, inv.point(lambda v: 255 if v > 127 else 0))
    img.putalpha(new_alpha)

    return img, (card_x, video_y, card_w, card_h)


def _largura_texto(texto, font, draw, emoji_draw=None):
    if emoji_draw is not None:
        try:
            return emoji_draw.getsize(texto, font=font)[0]
        except Exception:
            pass
    bbox = draw.textbbox((0, 0), texto, font=font)
    return bbox[2] - bbox[0]


def wrap_text(text, font, max_w, draw, emoji_draw=None):
    linhas_finais = []
    texto = text.replace("\r\n", "\n").replace("\r", "\n")
    for paragrafo in texto.split("\n"):
        if paragrafo.strip() == "":
            linhas_finais.append("")
            continue
        cur = ""
        for w in paragrafo.split():
            test = (cur + " " + w).strip()
            if _largura_texto(test, font, draw, emoji_draw) <= max_w:
                cur = test
            else:
                if cur:
                    linhas_finais.append(cur)
                cur = w
        if cur:
            linhas_finais.append(cur)
    return linhas_finais


def make_post(video_path, caption, output_path, brand=None, uniqueness=None):
    set_brand(brand or {})
    return _gerar(video_path, caption, output_path, crop=None, uniqueness=uniqueness)


def make_post_from_crop(video_path, caption, output_path, crop, brand=None, uniqueness=None):
    set_brand(brand or {})
    return _gerar(video_path, caption, output_path, crop=crop, uniqueness=uniqueness)


def _gerar(video_path, caption, output_path, crop=None, uniqueness=None):
    """
    Gera o post com UMA única codificação de vídeo.

    Recorte, cor, grão, velocidade, redimensionamento e template são aplicados
    no mesmo filter_complex. Depois há somente uma passagem de stream copy para
    limpeza profunda, sem perda adicional de qualidade.

    A chamada é opcional. Sem texto, o espaço reservado para a legenda também
    desaparece: fica apenas o cabeçalho da página, um respiro e o vídeo.
    """
    caption = str(caption or "")
    has_caption = bool(caption.strip())
    vw, vh = get_video_size(video_path)
    tem_audio = has_audio(video_path)
    opcoes = _normalizar_opcoes_uniqueness(uniqueness)

    if crop is not None:
        cx0, cy0, cw0, ch0 = [int(round(v)) for v in crop]
        cx0 = max(0, min(cx0, vw - 2))
        cy0 = max(0, min(cy0, vh - 2))
        cw0 = max(2, min(cw0, vw - cx0))
        ch0 = max(2, min(ch0, vh - cy0))
        cw0 -= cw0 % 2
        ch0 -= ch0 % 2
        cw0 = max(2, cw0)
        ch0 = max(2, ch0)
        aspect = cw0 / ch0
    else:
        aspect = vw / vh

    card_w = CANVAS_W - 2 * MARGIN_X
    card_h = int(card_w / aspect)

    f_caption = _font(FONT_BOLD, 44)
    tmp_img = Image.new("RGB", (10, 10))
    tmp_draw = ImageDraw.Draw(tmp_img)
    if has_caption:
        lines = wrap_text(caption, f_caption, CANVAS_W - 2 * MARGIN_X, tmp_draw)
        caption_block_h = len(lines) * 58
        header_to_video_h = GAP_HEADER_CAP + caption_block_h + GAP_CAP_VIDEO
    else:
        lines = []
        caption_block_h = 0
        # Sem chamada, não deixa um bloco fantasma no meio do layout.
        header_to_video_h = GAP_CAP_VIDEO

    margem_seg = SAFE_MARGIN_Y

    altura_disp = CANVAS_H - 2 * margem_seg

    def altura_bloco(ch):
        return AVATAR_SIZE + header_to_video_h + ch

    if altura_bloco(card_h) > altura_disp:
        sobra = AVATAR_SIZE + header_to_video_h
        card_h = max(2, altura_disp - sobra)
        card_w = int(card_h * aspect)
        if card_w > CANVAS_W - 2 * MARGIN_X:
            card_w = CANVAS_W - 2 * MARGIN_X
            card_h = int(card_w / aspect)

    card_w -= card_w % 2
    card_h -= card_h % 2
    card_w = max(2, card_w)
    card_h = max(2, card_h)

    bloco_h = altura_bloco(card_h)
    header_y = max(margem_seg, (CANVAS_H - bloco_h) // 2)
    video_y = header_y + AVATAR_SIZE + header_to_video_h

    overlay, (cx, cy, cw, ch) = build_overlay(
        caption, card_w, card_h, video_y, header_y
    )

    # Todos os filtros visuais são acumulados aqui e executados uma única vez.
    # Edições extras só rodam se a chave "edicoes_extras" estiver ligada.
    video_filters = []
    if crop is not None:
        video_filters.append(f"crop={cw0}:{ch0}:{cx0}:{cy0}")

    edicoes = opcoes.get("edicoes_extras", False)

    if edicoes and opcoes["light_crop"]:
        crop_pct = random.uniform(0.01, 0.03)
        video_filters.append(
            f"crop=iw*(1-{crop_pct:.4f}):ih*(1-{crop_pct:.4f})"
        )

    # Espelhar é uma opção própria e não depende de edições extras.
    # Isso deixa o usuário decidir caso o vídeo contenha texto visível.
    if opcoes.get("mirror_video", False):
        video_filters.append("hflip")

    if edicoes and (opcoes["color_adjust"] or opcoes.get("stronger_visuals", True)):
        brightness = round(random.uniform(0.02, 0.06), 3)
        contrast = round(random.uniform(1.03, 1.10), 3)
        saturation = round(random.uniform(1.05, 1.18), 3)
        hue_shift = round(random.uniform(-6, 6), 1)
        video_filters.append(
            f"eq=brightness={brightness}:contrast={contrast}:saturation={saturation}"
        )
        if abs(hue_shift) > 0.5:
            video_filters.append(f"hue=h={hue_shift}")
        video_filters.append(
            "curves=all='0/0 0.25/0.22 0.5/0.52 0.75/0.78 1/1'"
        )

    if edicoes and (opcoes["subtle_grain"] or opcoes.get("stronger_visuals", True)):
        grain_strength = random.randint(6, 12)
        video_filters.append(f"noise=alls={grain_strength}:allf=t")

    if edicoes and opcoes.get("vignette", True):
        video_filters.append(
            f"vignette=angle=PI/{random.uniform(3.2, 4.8):.2f}:mode=forward"
        )

    if edicoes and opcoes.get("dynamic_zoom", True):
        zoom = round(random.uniform(1.04, 1.10), 3)
        video_filters.append(
            f"scale=iw*{zoom}:ih*{zoom},"
            f"crop=iw/{zoom}:ih/{zoom}:(iw-ow)/2:(ih-oh)/2"
        )

    speed = opcoes["speed_factor"]
    if abs(speed - 1.0) > 0.001:
        video_filters.append(f"setpts={1.0 / speed:.12f}*PTS")

    video_filters += [
        f"scale={cw}:{ch}:force_original_aspect_ratio=increase",
        f"crop={cw}:{ch}",
        "setsar=1",
    ]

    # ---- Logo: identidade do cliente, mantendo posição/tamanho do template ----
    logo_path_cfg = BRAND_LOGO_PATH
    logo_width_cfg = BRAND_LOGO_WIDTH
    logo_opacity_cfg = BRAND_LOGO_OPACITY
    usar_logo = (
        opcoes.get("usar_logo", False)
        and logo_path_cfg
        and os.path.exists(logo_path_cfg)
    )
    logo_path_temp = None
    logo_w = 0
    logo_h = 0

    with tempfile.TemporaryDirectory() as td:
        overlay_path = os.path.join(td, "overlay.png")
        encoded_path = os.path.join(td, "post_encoded.mp4")
        overlay.save(overlay_path)

        inputs = ["-i", video_path, "-framerate", "30", "-loop", "1", "-i", overlay_path]
        # índice 0 = vídeo, 1 = template overlay

        if usar_logo:
            # Prepara a logo com tamanho e opacidade
            logo_src = Image.open(logo_path_cfg).convert("RGBA")
            target_w = int(logo_width_cfg)
            ratio = target_w / logo_src.width
            target_h = max(1, int(logo_src.height * ratio))
            logo_src = logo_src.resize((target_w, target_h), Image.LANCZOS)

            # Aplica opacidade 25%
            opacity = float(logo_opacity_cfg)
            alpha = logo_src.split()[3]
            alpha = alpha.point(lambda p: int(p * opacity))
            logo_src.putalpha(alpha)

            logo_path_temp = os.path.join(td, "logo.png")
            logo_src.save(logo_path_temp)
            logo_w, logo_h = logo_src.size
            inputs += ["-loop", "1", "-i", logo_path_temp]
            # índice 2 = logo

        # Monta o filter_complex
        # [0:v] → filtros → [v]
        # depois overlay da logo embaixo-esquerda do card (se houver)
        # depois coloca o card no fundo branco
        # depois o template por cima

        partes = [
            f"color=white:s={CANVAS_W}x{CANVAS_H}:r=30[bgc]",
            f"[0:v:0]{','.join(video_filters)}[v0]",
        ]

        if usar_logo:
            # logo no canto inferior esquerdo do card, com margem de 12px
            margin = 12
            partes.append(
                f"[2:v]format=rgba,scale={logo_w}:{logo_h}[logo];"
                f"[v0][logo]overlay={margin}:{ch - logo_h - margin}:shortest=1[v]"
            )
        else:
            partes.append("[v0]null[v]")

        partes += [
            f"[bgc][v]overlay={cx}:{cy}:shortest=1[based]",
            "[based][1:v:0]overlay=0:0:shortest=1[outv]",
        ]

        if tem_audio:
            if abs(speed - 1.0) > 0.001:
                partes.append(f"[0:a:0]{_atempo_filter(speed)}[outa]")
            else:
                partes.append("[0:a:0]anull[outa]")

        filter_complex = ";".join(partes)

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
        ]

        if tem_audio:
            cmd += ["-map", "[outa]", "-c:a", "aac", "-b:a", "192k"]
        else:
            cmd += ["-an"]

        cmd += [
            "-c:v", "libx264",
            "-crf", str(opcoes["crf"]),
            "-preset", opcoes["preset"],
            "-pix_fmt", "yuv420p",
            "-r", "30",
            "-sn", "-dn",
            "-shortest",
        ]
        if opcoes.get("remove_metadata", True):
            cmd += _metadata_clean_args()
            cmd += ["-fflags", "+bitexact"]
        cmd += [
            "-movflags", "+faststart",
            encoded_path,
        ]

        run(cmd)

        if opcoes.get("remove_metadata", True) and opcoes["deep_metadata_clean"]:
            deep_clean_mp4(
                encoded_path,
                output_path,
                remove_sei=opcoes["remove_h264_sei"],
            )
        else:
            os.replace(encoded_path, output_path)

    return output_path

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Uso: python3 meme_maker.py <video> <legenda> <saida.mp4>")
        sys.exit(1)
    video = sys.argv[1]
    legenda = sys.argv[2]
    saida = sys.argv[3]
    make_post(video, legenda, saida)
    print("Pronto:", saida)
