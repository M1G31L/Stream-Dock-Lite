"""
reactions.py - Efectos de reacción de las teclas (no se aplican a «Ahora suena»).

• Al pulsar: onda, destello, hundir, borde de color o chispas (≈0,4 s).
• Con la música: la tecla reacciona al volumen real de Spotify en cada momento
  (latido, borde que brilla, barra de nivel o destello en cada golpe/beat).
"""

from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw

PRESS_FX = {"ninguno": "Ninguno", "onda": "Onda", "destello": "Destello", "hundir": "Hundir",
            "borde": "Borde de color", "chispas": "Chispas"}
MUSIC_FX = {"ninguno": "No reaccionar", "latido": "Latido con el ritmo", "borde": "Borde que brilla",
            "nivel": "Barra de nivel", "golpe": "Destello en cada golpe"}
PRESS_S = 0.4        # duración del efecto al pulsar
BEAT_S = 0.25        # duración del destello de golpe
DEFAULT_PRESS = "onda"


def _rgb(hex_color: str):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def excluded(key: dict) -> bool:
    """La tecla de portada («Ahora suena») no lleva efectos de reacción."""
    return (key.get("action") or {}).get("type") == "sp_now"


def is_active(key: dict, pressed_at, music_on: bool, now: float) -> bool:
    if excluded(key):
        return False
    if pressed_at and now - pressed_at < PRESS_S and key.get("press_fx", DEFAULT_PRESS) != "ninguno":
        return True
    return music_on and key.get("music_fx", "ninguno") != "ninguno"


def _press(img: Image.Image, fx: str, p: float, accent: str, seed: float) -> Image.Image:
    """p: 0 (recién pulsada) → 1 (terminado)."""
    s = img.width
    ease = 1 - (1 - p) ** 3
    acc = _rgb(accent)
    if fx == "destello":
        return Image.blend(img, Image.new("RGB", img.size, "#ffffff"), 0.55 * (1 - p))
    if fx == "hundir":
        k = 1 - 0.14 * math.sin(math.pi * p)
        n = max(1, int(s * k))
        out = Image.new("RGB", img.size, img.getpixel((0, 0)))  # el color de fondo de la tecla
        out.paste(img.resize((n, n), Image.BILINEAR), ((s - n) // 2, (s - n) // 2))
        return out
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    a = int(255 * (1 - p))
    if fx == "onda":
        r = s * (0.12 + 0.75 * ease)
        w = max(2, int(s * 0.06 * (1 - p)) + 1)
        d.ellipse([s / 2 - r, s / 2 - r, s / 2 + r, s / 2 + r], outline=acc + (a,), width=w)
        r2 = r * 0.6
        d.ellipse([s / 2 - r2, s / 2 - r2, s / 2 + r2, s / 2 + r2], outline=(255, 255, 255, a // 2), width=max(1, w // 2))
    elif fx == "borde":
        w = max(2, int(s * 0.09 * (1 - ease)) + 2)
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=s * 0.08, outline=acc + (a,), width=w)
    elif fx == "chispas":
        rnd = random.Random(int(seed * 1000))
        for _ in range(14):
            ang = rnd.uniform(0, 2 * math.pi)
            dist = s * (0.08 + rnd.uniform(0.3, 0.55) * ease)
            x, y = s / 2 + math.cos(ang) * dist, s / 2 + math.sin(ang) * dist
            r = s * 0.035 * (1 - p) + 1
            col = acc if rnd.random() < 0.6 else (255, 255, 255)
            d.ellipse([x - r, y - r, x + r, y + r], fill=col + (a,))
    else:
        return img
    out = img.convert("RGBA")
    out.alpha_composite(over)
    return out.convert("RGB")


def _music(img: Image.Image, fx: str, level: float, beat_age: float, accent: str) -> Image.Image:
    s = img.width
    acc = _rgb(accent)
    if fx == "latido":
        k = 1 + 0.10 * level
        n = int(s * k)
        big = img.resize((n, n), Image.BILINEAR)
        o = (n - s) // 2
        return big.crop((o, o, o + s, o + s))
    if fx == "golpe":
        if beat_age < BEAT_S:
            q = 1 - beat_age / BEAT_S
            return Image.blend(img, Image.new("RGB", img.size, acc), 0.45 * q)
        return img
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    if fx == "borde":
        w = max(2, int(s * 0.05))
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=s * 0.08, outline=acc + (int(60 + 195 * level),),
                            width=w)
    elif fx == "nivel":
        h = max(3, int(s * 0.05))
        d.rectangle([0, s - h, s, s], fill=(0, 0, 0, 150))
        d.rectangle([0, s - h, int(s * min(1.0, level)), s], fill=acc + (255,))
    else:
        return img
    out = img.convert("RGBA")
    out.alpha_composite(over)
    return out.convert("RGB")


def apply(img: Image.Image, key: dict, pressed_at, now: float, accent: str,
          level: float = 0.0, beat_age: float = 99.0, music_on: bool = False) -> Image.Image:
    if excluded(key):
        return img
    mfx = key.get("music_fx", "ninguno")
    if music_on and mfx != "ninguno":
        img = _music(img, mfx, level, beat_age, accent)
    pfx = key.get("press_fx", DEFAULT_PRESS)
    if pressed_at and pfx != "ninguno":
        p = (now - pressed_at) / PRESS_S
        if 0 <= p < 1:
            img = _press(img, pfx, p, accent, pressed_at)
    return img
