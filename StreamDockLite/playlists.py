"""
playlists.py - Teclas de playlists, álbumes, artistas o canciones de Spotify.

• Pegas un enlace de Spotify (Compartir → Copiar enlace) o una URI spotify:…
• La portada y el nombre se descargan del servicio público oEmbed de Spotify
  (no necesita cuenta ni claves) y se guardan en caché.
• Al pulsar:
    - con la cuenta conectada (Ajustes → Spotify): empieza a sonar al momento;
    - sin cuenta: se abre en la app de Spotify, lista para darle a reproducir.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from typing import Optional

from PIL import Image

KINDS = ("playlist", "album", "artist", "track", "show", "episode")
_RX = re.compile(r"(?:open\.spotify\.com/(?:intl-[a-z]+/)?|spotify:)(playlist|album|artist|track|show|episode)[/:]([A-Za-z0-9]{10,40})")


def parse(link: str) -> Optional[tuple[str, str]]:
    """Devuelve (tipo, id) de un enlace o URI de Spotify, o None."""
    m = _RX.search((link or "").strip())
    return (m.group(1), m.group(2)) if m else None


def uri_of(link: str) -> Optional[str]:
    p = parse(link)
    return f"spotify:{p[0]}:{p[1]}" if p else None


def web_url(link: str) -> Optional[str]:
    p = parse(link)
    return f"https://open.spotify.com/{p[0]}/{p[1]}" if p else None


def _cache_dir(app_dir: str) -> str:
    d = os.path.join(app_dir, "portadas")
    os.makedirs(d, exist_ok=True)
    return d


def fetch_info(link: str, app_dir: str) -> dict:
    """Descarga nombre y portada (oEmbed). Devuelve {"name", "cover"} o lanza error."""
    url = web_url(link)
    if not url:
        raise ValueError("Ese enlace no es de Spotify. Usa Compartir → Copiar enlace.")
    q = "https://open.spotify.com/oembed?url=" + urllib.parse.quote(url, safe="")
    req = urllib.request.Request(q, headers={"User-Agent": "StreamDockLite"})
    with urllib.request.urlopen(req, timeout=10) as r:
        meta = json.load(r)
    name = meta.get("title") or ""
    thumb = meta.get("thumbnail_url")
    cover = ""
    if thumb:
        req = urllib.request.Request(thumb, headers={"User-Agent": "StreamDockLite"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((640, 640), Image.LANCZOS)
        cover = os.path.join(_cache_dir(app_dir), hashlib.sha1(url.encode()).hexdigest()[:16] + ".jpg")
        img.save(cover, "JPEG", quality=92)
    return {"name": name, "cover": cover, "fetched": time.time()}


def open_in_spotify(link: str):
    uri = uri_of(link)
    if not uri:
        raise ValueError("Enlace de Spotify no válido")
    if sys.platform == "win32":
        os.startfile(uri)  # type: ignore[attr-defined]
    else:
        import webbrowser
        webbrowser.open(web_url(link))


def play(link: str, web) -> str:
    """Reproduce el enlace. `web` es spotify.SpotifyWeb. Devuelve un mensaje."""
    uri = uri_of(link)
    if not uri:
        raise ValueError("Enlace de Spotify no válido")
    if web is not None and web.connected:
        try:
            web.play_uri(uri)
            return "Reproduciendo en Spotify"
        except Exception as e:  # sin dispositivo activo, sin permiso, etc.
            msg = str(e)
            if "NO_ACTIVE_DEVICE" in msg or "404" in msg:
                open_in_spotify(link)
                time.sleep(3)
                try:
                    web.play_uri(uri)
                    return "Reproduciendo en Spotify"
                except Exception:
                    return "Abierto en Spotify (dale a reproducir)"
            if "403" in msg or "scope" in msg.lower():
                open_in_spotify(link)
                return ("Abierto en Spotify. Para que empiece a sonar solo, vuelve a conectar "
                        "tu cuenta en Ajustes → Spotify.")
            open_in_spotify(link)
            return "Abierto en Spotify"
    open_in_spotify(link)
    return "Abierto en Spotify (conecta tu cuenta en Ajustes para que suene al momento)"
