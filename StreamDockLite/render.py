"""
render.py - Dibuja las teclas (estáticas y "en vivo" de Spotify).
Mismo dibujo para la vista previa en pantalla y para el dispositivo.
"""

from __future__ import annotations

import math
import os
import time
from functools import lru_cache
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SPOTIFY_GREEN = "#1DB954"
DARK = "#121212"
GREY = "#B3B3B3"

TEXT_FONTS = ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")
ICON_FONTS = ("SegoeIcons.ttf", "segmdl2.ttf")  # Windows 11 / Windows 10

# Códigos de "Segoe Fluent Icons" / "Segoe MDL2 Assets"
GLYPHS = {
    "play": "", "pause": "", "next": "", "prev": "",
    "shuffle": "", "repeat": "", "repeat_one": "",
    "heart": "", "heart_fill": "", "vol": "", "mute": "",
    "music": "", "app": "", "keyboard": "", "text": "",
    "cmd": "", "web": "", "page": "", "media": "",
}
# Respaldo si no existe la fuente de iconos de Windows
FALLBACK = {"shuffle": "⇄", "repeat": "↻", "repeat_one": "↻¹", "heart": "♡", "heart_fill": "♥",
            "vol": "🔊", "mute": "🔇", "music": "♪", "app": "⊞", "keyboard": "⌨", "text": "T",
            "cmd": ">_", "web": "◎", "page": "▦", "media": "♫"}


@lru_cache(maxsize=64)
def text_font(size: int):
    for name in TEXT_FONTS:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


@lru_cache(maxsize=32)
def icon_font(size: int):
    for name in ICON_FONTS:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return None


def _shape_glyph(d: ImageDraw.ImageDraw, name: str, cx: float, cy: float, r: float, color) -> bool:
    """Dibuja con figuras los iconos básicos (cuando no hay fuente de iconos)."""
    if name == "play":
        d.polygon([(cx - r * .6, cy - r), (cx - r * .6, cy + r), (cx + r, cy)], fill=color)
    elif name == "pause":
        w = r * .55
        d.rectangle([cx - r * .85, cy - r, cx - r * .85 + w, cy + r], fill=color)
        d.rectangle([cx + r * .85 - w, cy - r, cx + r * .85, cy + r], fill=color)
    elif name in ("next", "prev"):
        s = 1 if name == "next" else -1
        d.polygon([(cx - s * r, cy - r * .8), (cx - s * r, cy + r * .8), (cx + s * r * .5, cy)], fill=color)
        x = cx + s * r * .65
        d.rectangle([min(x, x + s * r * .3), cy - r * .8, max(x, x + s * r * .3), cy + r * .8], fill=color)
    elif name in ("vol", "mute"):
        d.rectangle([cx - r, cy - r * .35, cx - r * .45, cy + r * .35], fill=color)
        d.polygon([(cx - r * .45, cy - r * .35), (cx + r * .1, cy - r * .9),
                   (cx + r * .1, cy + r * .9), (cx - r * .45, cy + r * .35)], fill=color)
        w = max(2, int(r * .14))
        if name == "vol":
            for k in (.45, .8):
                d.arc([cx + r * .1 - r * k, cy - r * k, cx + r * .1 + r * k, cy + r * k], -50, 50, fill=color, width=w)
        else:
            d.line([cx + r * .35, cy - r * .35, cx + r, cy + r * .35], fill=color, width=w)
            d.line([cx + r * .35, cy + r * .35, cx + r, cy - r * .35], fill=color, width=w)
    else:
        return False
    return True


def draw_glyph(img: Image.Image, name: str, center, size: int, color="#FFFFFF"):
    d = ImageDraw.Draw(img)
    cx, cy = center
    f = icon_font(size)
    if f is not None and name in GLYPHS:
        ch = GLYPHS[name]
        x0, y0, x1, y1 = d.textbbox((0, 0), ch, font=f)
        d.text((cx - (x0 + x1) / 2, cy - (y0 + y1) / 2), ch, font=f, fill=color)
        return
    if _shape_glyph(d, name, cx, cy, size * 0.42, color):
        return
    ch = FALLBACK.get(name, "•")
    f = text_font(int(size * 0.8))
    x0, y0, x1, y1 = d.textbbox((0, 0), ch, font=f)
    d.text((cx - (x0 + x1) / 2, cy - (y0 + y1) / 2), ch, font=f, fill=color)


def fit_text(d, text, max_w, start, minimum):
    fs = start
    while fs > minimum and d.textlength(text, font=text_font(fs)) > max_w:
        fs -= 1
    f = text_font(fs)
    if d.textlength(text, font=f) <= max_w:
        return text, f, fs
    while len(text) > 1 and d.textlength(text + "…", font=f) > max_w:
        text = text[:-1]
    return text + "…", f, fs


def draw_title(img, title, pos="bottom", color="#FFFFFF", shadow=True):
    """Título estilo Stream Deck: arriba, centro o abajo, con sombra suave."""
    if not title:
        return
    size = img.width
    d = ImageDraw.Draw(img)
    lines = title.split("\n")[:2]
    fs0 = int(size * 0.17)
    fitted = [fit_text(d, ln, size * 0.92, fs0, int(size * 0.11)) for ln in lines]
    fs = min(f[2] for f in fitted)
    font = text_font(fs)
    lh = int(fs * 1.15)
    block = lh * len(fitted)
    y = {"top": int(size * 0.05), "middle": (size - block) // 2}.get(pos, size - block - int(size * 0.06))
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        yy = y
        for text, _, _ in fitted:
            w = sd.textlength(text, font=font)
            sd.text(((size - w) / 2 + 1, yy + 1), text, font=font, fill=(0, 0, 0, 220))
            yy += lh
        img.paste(sh.filter(ImageFilter.GaussianBlur(1.6)), (0, 0), sh.filter(ImageFilter.GaussianBlur(1.6)))
    for text, _, _ in fitted:
        w = d.textlength(text, font=font)
        d.text(((size - w) / 2, y), text, font=font, fill=color)
        y += lh


def _dark_frac(gray: Image.Image, x0: int, x1: int, y: int, th: int = 34) -> float:
    hist = gray.crop((x0, y, max(x0 + 1, x1), y + 1)).histogram()
    return sum(hist[: th + 1]) / max(1, x1 - x0)


def find_spotify_band(img: Image.Image) -> int:
    """Alto (px) de la franja inferior con el logo de Spotify, o 0 si no hay.

    La franja es negra, con el logo y la palabra «Spotify» en el centro/izquierda:
    sus extremos izquierdo y derecho son negros, y entre el arte y el logo hay
    filas totalmente negras. Además debe contener algo claro (el logo), para no
    confundirla con un borde negro que forme parte del propio arte."""
    gray = img.convert("L")
    w, h = img.size
    l1, r0 = max(1, int(w * 0.04)), int(w * 0.94)
    y = h - 1
    while y > h * 0.62:
        edges = (_dark_frac(gray, 0, l1, y) + _dark_frac(gray, r0, w, y)) / 2
        if edges < 0.9 or _dark_frac(gray, 0, w, y) < 0.45:
            break
        y -= 1
    top = y + 1                       # primera fila de la zona candidata
    if h - top < h * 0.04:
        return 0
    # el corte va en la fila totalmente negra más alta de la zona (el hueco
    # entre el arte y el logo), así no se come nada del arte
    cut = None
    for yy in range(top, h):
        if _dark_frac(gray, 0, w, yy) >= 0.985:
            cut = yy
            break
    if cut is None:
        return 0
    # ¿hay logo/texto debajo del corte?
    logo = sum(1 - _dark_frac(gray, 0, w, yy, 60) for yy in range(cut, h)) * w
    if logo < w * 0.6:
        return 0
    return h - cut


def prepare_cover(img: Image.Image, mode: str = "auto", pct: int = 0) -> Image.Image:
    """Deja solo el arte de la portada.
    mode: "auto" (detecta la franja y márgenes), "manual" (quita pct % de abajo),
          "nada" (la imagen tal cual)."""
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        box = rgba.getchannel("A").point(lambda a: 255 if a > 16 else 0).getbbox()
        if box:
            rgba = rgba.crop(box)
        img = Image.new("RGB", rgba.size, (0, 0, 0))
        img.paste(rgba, (0, 0), rgba)
    img = img.convert("RGB")
    if mode == "nada":
        return img
    w, h = img.size
    if mode == "manual":
        cut = int(h * max(0, min(40, pct)) / 100)
        return img.crop((0, 0, w, h - cut)) if cut else img
    band = find_spotify_band(img)
    if band:
        img = img.crop((0, 0, w, h - band))
    return trim_dark_margins(img)


def trim_dark_margins(img: Image.Image, tolerance: int = 18) -> Image.Image:
    """Quita márgenes negros lisos alrededor del arte (sin tocar fondos de color)."""
    w, h = img.size
    box = img.convert("L").point(lambda v: 255 if v > tolerance else 0).getbbox()
    if not box:
        return img
    l, t, r, b = box
    cw, ch = r - l, b - t
    if cw < w * 0.5 or ch < h * 0.5 or not (0.85 <= cw / ch <= 1.18):
        return img
    return img.crop(box)


_cover_cache: dict = {}


def cover_for(sp, key: dict) -> Image.Image:
    """Portada ya recortada según los ajustes de la tecla (con caché)."""
    k = (id(sp.cover), key.get("cover_crop", "auto"), int(key.get("cover_crop_pct", 15)))
    if k not in _cover_cache:
        if len(_cover_cache) > 16:
            _cover_cache.clear()
        _cover_cache[k] = prepare_cover(sp.cover, k[1], k[2])
    return _cover_cache[k]


_fill_cache: dict = {}


def fill_square_cached(img: Image.Image, size: int) -> Image.Image:
    """Igual que fill_square, pero recuerda el resultado (la portada no cambia
    entre cuadros de una animación). Devuelve una copia: quien la reciba puede dibujar encima."""
    k = (id(img), size)
    hit = _fill_cache.get(k)
    if hit is None or hit[0] is not img:
        if len(_fill_cache) > 48:
            _fill_cache.clear()
        hit = (img, fill_square(img, size))
        _fill_cache[k] = hit
    return hit[1].copy()


def fill_square(img: Image.Image, size: int) -> Image.Image:
    """Escala para CUBRIR el cuadrado (sin bandas) y recorta el sobrante centrado."""
    w, h = img.size
    sc = size / min(w, h)
    nw, nh = max(size, round(w * sc)), max(size, round(h * sc))
    img = img.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - size) // 2, (nh - size) // 2
    return img.crop((x, y, x + size, y + size))


def _fmt(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


# --------------------------------------------------------------------------
# Iconos por defecto según el tipo de acción
# --------------------------------------------------------------------------
STATIC_GLYPH = {
    "sp_next": ("next", SPOTIFY_GREEN), "sp_prev": ("prev", SPOTIFY_GREEN),
    "sp_open": ("music", SPOTIFY_GREEN), "abrir": ("app", "#4C8BF5"),
    "atajo": ("keyboard", "#8E7CC3"), "texto": ("text", "#E69138"), "comando": ("cmd", "#999999"),
    "pagina": ("page", "#F1C232"), "multimedia": ("media", "#45B5AA"),
}
MEDIA_GLYPH = {"play_pause": "play", "next": "next", "prev": "prev", "stop": "pause",
               "mute": "mute", "vol_up": "vol", "vol_down": "vol"}


# ==========================================================================
# «Ahora suena»: estilos, animaciones y transiciones
# ==========================================================================
NOW_STYLES = {           # clave -> (nombre, ¿animado mientras suena?)
    "portada": ("Solo portada", False),
    "titulo": ("Portada + título deslizante", True),
    "progreso": ("Portada + barra de progreso", False),
    "ecualizador": ("Portada + ecualizador animado", True),
    "vinilo": ("Disco de vinilo girando", True),
    "pulso": ("Portada que late", True),
    "zoom": ("Paneo lento (Ken Burns)", True),
}
PAUSE_STYLES = {"nada": "No cambiar", "atenuar": "Atenuar portada", "gris": "Blanco y negro",
                "icono": "Icono de pausa", "detener": "Detener animación"}
TRANSITIONS = {"nada": "Ninguna", "fundido": "Fundido", "deslizar": "Deslizar", "zoom": "Acercar"}
CROP_MODES = {"auto": "Automático (quita la franja de Spotify)", "manual": "Manual (% de abajo)",
              "nada": "No recortar"}
TRANSITION_S = 0.6

_track_change = {"cover": None, "prev": None, "since": 0.0}


def note_cover(cover):
    """La app avisa del cambio de portada para animar la transición."""
    if cover is not _track_change["cover"]:
        _track_change["prev"] = _track_change["cover"]
        _track_change["cover"] = cover
        _track_change["since"] = time.time()


def in_transition(key: dict, now: float) -> bool:
    return (key.get("transition", "fundido") != "nada" and _track_change["prev"] is not None
            and now - _track_change["since"] < TRANSITION_S)


def is_animated(key: dict, sp, now: Optional[float] = None) -> bool:
    """¿Esta tecla necesita redibujarse varias veces por segundo ahora mismo?"""
    if (key.get("action") or {}).get("type") != "sp_now" or not (sp and sp.running and sp.cover is not None):
        return False
    now = time.time() if now is None else now
    if in_transition(key, now):
        return True
    style = key.get("now_style", "portada")
    if not NOW_STYLES.get(style, ("", False))[1]:
        return False
    if style == "titulo":
        return True  # el texto se desliza aunque esté en pausa
    return sp.playing or key.get("pause_style", "nada") != "detener"


_vinyl_cache: dict = {}


def _vinyl_base(size: int):
    """Disco, surcos y reflejos (fijos) + máscara redonda de la etiqueta."""
    if size not in _vinyl_cache:
        img = Image.new("RGB", (size, size), "#0b0b0b")
        d = ImageDraw.Draw(img)
        c = size / 2
        d.ellipse([2, 2, size - 2, size - 2], fill="#111")
        for r in range(int(size * 0.47), int(size * 0.3), -3):  # surcos
            d.ellipse([c - r, c - r, c + r, c + r], outline="#1c1c1c")
        # reflejo suave sobre los surcos (fuera de la etiqueta, así que puede ir aquí)
        for i, r in enumerate(range(int(size * 0.46), int(size * 0.31), -4)):
            d.arc([c - r, c - r, c + r, c + r], 205, 245, fill="#3a3a3a" if i % 2 else "#2c2c2c", width=1)
            d.arc([c - r, c - r, c + r, c + r], 25, 65, fill="#2c2c2c", width=1)
        lab = int(size * 0.56)
        mask = Image.new("L", (lab, lab), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, lab - 1, lab - 1], fill=255)
        _vinyl_cache[size] = (img, mask)
    return _vinyl_cache[size]


def _vinyl(cover: Image.Image, size: int, angle: float) -> Image.Image:
    base, mask = _vinyl_base(size)
    img = base.copy()
    d = ImageDraw.Draw(img)
    c = size / 2
    lab = int(size * 0.56)
    art = fill_square_cached(cover, lab).rotate(-angle, resample=Image.BICUBIC)
    img.paste(art, (int(c - lab / 2), int(c - lab / 2)), mask)
    h = size * 0.035
    d.ellipse([c - h, c - h, c + h, c + h], fill="#0b0b0b")
    return img


def _equalizer(img: Image.Image, now: float, playing: bool):
    size = img.width
    d = ImageDraw.Draw(img, "RGBA")
    n, bw, gap = 4, size * 0.055, size * 0.03
    x0 = size - (n * bw + (n - 1) * gap) - size * 0.07
    base = size * 0.93
    d.rounded_rectangle([x0 - size * 0.035, base - size * 0.3, size - size * 0.035, base + size * 0.03],
                        radius=size * 0.05, fill=(0, 0, 0, 120))
    for i in range(n):
        if playing:
            v = 0.25 + 0.75 * abs(math.sin(now * (5.3 + i * 1.7) + i * 1.3) * math.sin(now * (2.1 + i * 0.6)))
        else:
            v = 0.15
        hh = size * 0.24 * v
        x = x0 + i * (bw + gap)
        d.rounded_rectangle([x, base - hh, x + bw, base], radius=bw / 2, fill=SPOTIFY_GREEN)


_shade_cache: dict = {}


def _bottom_shade(size: int):
    if size not in _shade_cache:
        shade = Image.new("L", (1, size))
        for y in range(size):
            shade.putpixel((0, y), int(max(0, (y - size * 0.55) / (size * 0.45)) * 210))
        _shade_cache[size] = (Image.new("RGB", (size, size), "#000"), shade.resize((size, size)))
    return _shade_cache[size]


def _marquee(img: Image.Image, text: str, now: float):
    size = img.width
    black, shade = _bottom_shade(size)
    img.paste(black, (0, 0), shade)
    fs = int(size * 0.16)
    font = text_font(fs)
    d = ImageDraw.Draw(img)
    w = d.textlength(text, font=font)
    y = size - fs - size * 0.09
    if w <= size * 0.92:
        d.text(((size - w) / 2, y), text, font=font, fill="#fff")
        return
    span = w + size * 0.35
    off = (now * size * 0.45) % span  # se desliza a ~45 % del ancho por segundo
    for x in (size * 0.04 - off, size * 0.04 - off + span):
        d.text((x, y), text, font=font, fill="#fff")


def _progress_bar(img: Image.Image, sp):
    size = img.width
    d = ImageDraw.Draw(img)
    hh = max(3, int(size * 0.045))
    frac = (sp.live_position() / sp.duration) if sp.duration else 0
    d.rectangle([0, size - hh, size, size], fill="#2a2a2a")
    d.rectangle([0, size - hh, size * max(0, min(1, frac)), size], fill=SPOTIFY_GREEN)


def _base_cover(key, sp, cover, size, now, style):
    playing = sp.playing
    if style == "vinilo":
        speed = 120 if playing else 0  # grados por segundo (33⅓ rpm ≈ 200, más suave para el N3E)
        return _vinyl(cover, size, (now * speed) % 360 if playing or key.get("pause_style") != "detener" else 0)
    if style == "pulso" and (playing or key.get("pause_style") != "detener"):
        k = 1.0 + (0.06 * (0.5 + 0.5 * math.sin(now * 2 * math.pi * 1.6)) if playing else 0)
        big = fill_square_cached(cover, int(size * k) + 1)
        o = (big.width - size) // 2
        return big.crop((o, o, o + size, o + size))
    if style == "zoom" and (playing or key.get("pause_style") != "detener"):
        k = 1.18
        big = fill_square_cached(cover, int(size * k))
        rng = big.width - size
        p = 0.5 + 0.5 * math.sin(now * 0.35)
        q = 0.5 + 0.5 * math.cos(now * 0.27)
        return big.crop((int(rng * p), int(rng * q), int(rng * p) + size, int(rng * q) + size))
    return fill_square_cached(cover, size)


def render_now_playing(key: dict, sp, size: int, now: float) -> Image.Image:
    style = key.get("now_style", "portada")
    cover = cover_for(sp, key)
    img = _base_cover(key, sp, cover, size, now, style)

    # transición al cambiar de canción
    tr = key.get("transition", "fundido")
    if in_transition(key, now) and _track_change["prev"] is not None:
        k = min(1.0, (now - _track_change["since"]) / TRANSITION_S)
        k = k * k * (3 - 2 * k)  # suavizado
        old_cover = prepare_cover(_track_change["prev"], key.get("cover_crop", "auto"),
                                  int(key.get("cover_crop_pct", 15)))
        old = _base_cover(key, sp, old_cover, size, now, style)
        if tr == "fundido":
            img = Image.blend(old, img, k)
        elif tr == "deslizar":
            frame = Image.new("RGB", (size, size))
            dx = int(size * k)
            frame.paste(old, (-dx, 0))
            frame.paste(img, (size - dx, 0))
            img = frame
        elif tr == "zoom":
            s2 = max(1, int(size * (0.4 + 0.6 * k)))
            frame = old.copy()
            frame.paste(img.resize((s2, s2), Image.LANCZOS), ((size - s2) // 2, (size - s2) // 2))
            img = frame

    # aspecto en pausa
    if not sp.playing:
        ps = key.get("pause_style", "nada")
        if ps == "atenuar":
            img = Image.blend(img, Image.new("RGB", img.size, "#000"), 0.5)
        elif ps == "gris":
            img = img.convert("L").convert("RGB")
        elif ps == "icono":
            d = ImageDraw.Draw(img, "RGBA")
            r = size * 0.2
            d.ellipse([size / 2 - r, size / 2 - r, size / 2 + r, size / 2 + r], fill=(0, 0, 0, 150))
            draw_glyph(img, "pause", (size / 2, size / 2), int(size * 0.2))

    # adornos del estilo
    if style == "titulo":
        _marquee(img, key.get("title") or sp.title or "", now)
    elif style == "progreso":
        _progress_bar(img, sp)
    elif style == "ecualizador":
        _equalizer(img, now, sp.playing)
    if key.get("title") and style != "titulo":
        draw_title(img, key["title"], key.get("title_pos", "bottom"), key.get("text_color") or "#FFFFFF")
    return img


def render_key(key: dict, sp=None, size: int = 128, now: Optional[float] = None) -> Image.Image:
    """key: configuración de la tecla. sp: SpotifyState (o None). now: reloj de animación."""
    now = time.time() if now is None else now
    action = key.get("action") or {}
    kind = action.get("type", "ninguna")
    bg = key.get("color") or DARK
    title = key.get("title", "")
    tpos = key.get("title_pos", "bottom")
    tcol = key.get("text_color") or "#FFFFFF"
    img = Image.new("RGB", (size, size), bg)
    c = (size / 2, size / 2 - (size * 0.06 if title else 0))
    gs = int(size * (0.42 if title else 0.5))
    running = bool(sp and sp.running)

    custom_icon = key.get("icon") or ""
    if custom_icon and os.path.exists(custom_icon):
        try:
            ic = Image.open(custom_icon).convert("RGBA")
            box = int(size * (0.66 if title else 0.9))
            ic.thumbnail((box, box), Image.LANCZOS)
            top = int(size * 0.06) if title and tpos == "bottom" else (size - ic.height) // 2
            img.paste(ic, ((size - ic.width) // 2, top), ic)
            draw_title(img, title, tpos, tcol)
            return img
        except Exception:
            pass

    if kind == "sp_now":
        if running and sp.cover is not None:
            img = render_now_playing(key, sp, size, now)
        else:
            img = Image.new("RGB", (size, size), DARK)
            draw_glyph(img, "music", (size / 2, size * 0.42), int(size * 0.42), SPOTIFY_GREEN)
            draw_title(img, sp.title if running else "Abrir\nSpotify", "bottom", GREY)
        return img

    if kind == "sp_playlist":
        cover = _file_image(key.get("pl_cover") or "")
        if cover is not None:
            img = fill_square(cover, size)
        else:
            img = Image.new("RGB", (size, size), DARK)
            draw_glyph(img, "music", (size / 2, size * 0.4), int(size * 0.4), SPOTIFY_GREEN)
            draw_title(img, key.get("pl_name") or ("Pega un enlace" if not action.get("value") else "Cargando…"),
                       "bottom", GREY)
            return img
        draw_title(img, title, tpos, tcol)
        return img

    if kind == "sp_play":
        playing = bool(sp and sp.playing)
        img = Image.new("RGB", (size, size), key.get("color") or DARK)
        d = ImageDraw.Draw(img)
        r = size * 0.3
        d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=SPOTIFY_GREEN)
        draw_glyph(img, "pause" if playing else "play", (c[0] + (0 if playing else size * 0.02), c[1]),
                   int(size * 0.26), "#000000")
        draw_title(img, title, tpos, tcol)
        return img

    if kind in ("sp_shuffle", "sp_repeat", "sp_like"):
        if kind == "sp_shuffle":
            on, glyph = bool(sp and sp.shuffle), "shuffle"
        elif kind == "sp_repeat":
            rep = (sp.repeat if sp else 0) or 0
            on, glyph = rep != 0, "repeat_one" if rep == 1 else "repeat"
        else:
            on = bool(sp and sp.liked)
            glyph = "heart_fill" if on else "heart"
        draw_glyph(img, glyph, c, gs, SPOTIFY_GREEN if on else GREY)
        if on and kind != "sp_like":  # puntito verde, como en Spotify
            d = ImageDraw.Draw(img)
            r = size * 0.03
            d.ellipse([c[0] - r, c[1] + gs * 0.62 - r, c[0] + r, c[1] + gs * 0.62 + r], fill=SPOTIFY_GREEN)
        draw_title(img, title, tpos, tcol)
        return img

    if kind == "sp_progress":
        d = ImageDraw.Draw(img)
        pos = sp.live_position() if running else 0
        dur = sp.duration if running else 0
        f = text_font(int(size * 0.24))
        t = _fmt(pos)
        w = d.textlength(t, font=f)
        d.text(((size - w) / 2, size * 0.2), t, font=f, fill="#FFFFFF")
        x0, x1, y = size * 0.1, size * 0.9, size * 0.62
        d.rounded_rectangle([x0, y, x1, y + size * 0.05], radius=size * 0.025, fill="#404040")
        frac = (pos / dur) if dur else 0
        d.rounded_rectangle([x0, y, x0 + (x1 - x0) * frac, y + size * 0.05], radius=size * 0.025, fill=SPOTIFY_GREEN)
        f2 = text_font(int(size * 0.13))
        rest = "-" + _fmt(dur - pos) if dur else "--:--"
        w = d.textlength(rest, font=f2)
        d.text(((size - w) / 2, size * 0.74), rest, font=f2, fill=GREY)
        return img

    if kind == "sp_volume":
        d = ImageDraw.Draw(img)
        vol = sp.volume if sp else None
        muted = bool(sp and sp.muted)
        draw_glyph(img, "mute" if muted or vol == 0 else "vol", (size / 2, size * 0.34), int(size * 0.3),
                   GREY if muted else SPOTIFY_GREEN)
        txt = "--" if vol is None else ("Silencio" if muted else f"{round(vol * 100)}%")
        f = text_font(int(size * 0.18))
        w = d.textlength(txt, font=f)
        d.text(((size - w) / 2, size * 0.58), txt, font=f, fill="#FFFFFF")
        if vol is not None:
            x0, x1, y = size * 0.15, size * 0.85, size * 0.84
            d.rounded_rectangle([x0, y, x1, y + size * 0.04], radius=size * 0.02, fill="#404040")
            d.rounded_rectangle([x0, y, x0 + (x1 - x0) * vol, y + size * 0.04], radius=size * 0.02,
                                fill=GREY if muted else SPOTIFY_GREEN)
        return img

    if kind in STATIC_GLYPH or kind == "multimedia":
        glyph, col = STATIC_GLYPH.get(kind, ("media", "#45B5AA"))
        if kind == "multimedia":
            glyph = MEDIA_GLYPH.get(action.get("value"), "media")
        draw_glyph(img, glyph, c, gs, col)
    draw_title(img, title, tpos, tcol)
    return img


_file_cache: dict = {}


def _file_image(path: str) -> Optional[Image.Image]:
    """Imagen de disco con caché (portadas de playlists)."""
    if not path or not os.path.exists(path):
        return None
    k = (path, os.path.getmtime(path))
    if k not in _file_cache:
        if len(_file_cache) > 32:
            _file_cache.clear()
        try:
            _file_cache[k] = Image.open(path).convert("RGB")
        except Exception:
            return None
    return _file_cache[k]


# --------------------------------------------------------------------------
# Protector de pantalla: la portada repartida en las 6 teclas (3 × 2)
# --------------------------------------------------------------------------
def saver_tile(cover: Image.Image, index: int, size: int = 128, cols: int = 3, rows: int = 2) -> Image.Image:
    w, h = cover.size
    target = cols / rows                     # 3:2
    if w / h > target:                        # recortamos al centro a 3:2
        nw = int(h * target)
        cover = cover.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w / target)
        cover = cover.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    big = cover.resize((cols * size, rows * size), Image.LANCZOS)
    c, r = index % cols, index // cols
    return big.crop((c * size, r * size, (c + 1) * size, (r + 1) * size))


def test_pattern(index: int, label: str, size: int = 128) -> Image.Image:
    """Patrón para ajustar el tamaño: el marco blanco debe tocar los 4 bordes
    de cada pantalla, y la flecha debe apuntar hacia arriba."""
    img = Image.new("RGB", (size, size), "#000")
    d = ImageDraw.Draw(img)
    w = max(3, size // 32)
    d.rectangle([0, 0, size - 1, size - 1], outline="#ffffff", width=w)
    d.rectangle([w * 2, w * 2, size - 1 - w * 2, size - 1 - w * 2], outline="#1DB954", width=max(2, w // 2))
    c = size / 2
    d.polygon([(c, size * 0.12), (c - size * 0.1, size * 0.28), (c + size * 0.1, size * 0.28)], fill="#f1c232")
    f = text_font(int(size * 0.34))
    t = str(index + 1)
    tw = d.textlength(t, font=f)
    d.text((c - tw / 2, size * 0.3), t, font=f, fill="#ffffff")
    f2 = text_font(int(size * 0.12))
    tw = d.textlength(label, font=f2)
    d.text((c - tw / 2, size * 0.74), label, font=f2, fill="#b3b3b3")
    return img


def is_live(key: dict) -> bool:
    return ((key.get("action") or {}).get("type", "")).startswith("sp_")


def key_signature(key: dict, sp) -> Optional[tuple]:
    """Lo que influye en el dibujo (para no redibujar si nada cambió)."""
    t = (key.get("action") or {}).get("type", "")
    if not sp or not t.startswith("sp_"):
        return None
    if t == "sp_now":
        sig = (sp.running, sp.title, id(sp.cover), sp.playing, key.get("now_style"), key.get("pause_style"),
               key.get("transition"), key.get("cover_crop"), key.get("cover_crop_pct"), key.get("title"))
        if key.get("now_style") == "progreso":
            sig += (int(sp.live_position() * 2),)
        return sig
    if t == "sp_play":
        return (sp.playing,)
    if t == "sp_shuffle":
        return (sp.shuffle,)
    if t == "sp_repeat":
        return (sp.repeat,)
    if t == "sp_like":
        return (sp.liked,)
    if t == "sp_progress":
        return (sp.running, int(sp.live_position()), int(sp.duration))
    if t == "sp_volume":
        return (sp.volume, sp.muted)
    return None
