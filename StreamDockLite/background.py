"""
background.py - Fondo de la ventana: imagen, video/GIF o la portada de la
canción que suena, con efectos (desenfoque, velo, saturación, viñeta y
movimiento lento).

Tkinter no tiene widgets transparentes, así que el fondo se dibuja en las
zonas "lienzo" de la ventana (barra superior, área del dispositivo, márgenes
entre paneles y barra inferior). Cada lienzo muestra el recorte que le toca
de una única imagen del tamaño de la ventana, así se ve continuo. Los paneles
(acciones, inspector) quedan como tarjetas encima.
"""

from __future__ import annotations

import math
import os
import time
from typing import Optional

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageSequence, ImageTk

try:
    import cv2  # opencv-python-headless (solo para videos .mp4/.webm/…)
    CV2_OK = True
except Exception:  # pragma: no cover
    cv2 = None
    CV2_OK = False

VIDEO_EXT = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".wmv")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
GIF_EXT = (".gif",)


def _cover_fit(img: Image.Image, w: int, h: int, scale: float = 1.0) -> Image.Image:
    """Escala para cubrir w×h (como 'background-size: cover') y recorta el centro."""
    iw, ih = img.size
    k = max(w / iw, h / ih) * scale
    nw, nh = max(w, int(iw * k + 0.5)), max(h, int(ih * k + 0.5))
    img = img.resize((nw, nh), Image.BILINEAR)
    x, y = (nw - w) // 2, (nh - h) // 2
    return img.crop((x, y, x + w, y + h))


class Effects:
    def __init__(self, a: dict, veil_color: str):
        self.blur = max(0, int(a.get("blur", 18)))
        self.veil = max(0, min(95, int(a.get("veil", 45)))) / 100
        self.sat = max(0, int(a.get("saturation", 110))) / 100
        self.vignette = bool(a.get("vignette", True))
        self.veil_color = veil_color
        self._vmask = {}

    def _vignette(self, size):
        if size not in self._vmask:
            w, h = size
            small = Image.new("L", (64, 64), 0)
            d = ImageDraw.Draw(small)
            for i in range(32):
                v = int(255 * (1 - i / 32) ** 2 * 0.85)
                d.ellipse([i - 10, i - 10, 73 - i, 73 - i], outline=v, width=2)
            self._vmask[size] = small.filter(ImageFilter.GaussianBlur(4)).resize((w, h), Image.BILINEAR)
        return self._vmask[size]

    def apply(self, src: Image.Image, w: int, h: int, zoom: float = 1.0, pan=(0.5, 0.5)) -> Image.Image:
        """src → imagen w×h con todos los efectos. Rápido: el desenfoque se hace a 1/4."""
        src = src.convert("RGB")
        if self.blur > 0:
            sw, sh = max(1, w // 4), max(1, h // 4)
            small = _cover_fit(src, sw, sh, zoom)
            if self.sat != 1:
                small = ImageEnhance.Color(small).enhance(self.sat)
            small = small.filter(ImageFilter.GaussianBlur(self.blur / 4))
            img = small.resize((w, h), Image.BICUBIC)
        else:
            img = _cover_fit(src, w, h, zoom)
            if self.sat != 1:
                img = ImageEnhance.Color(img).enhance(self.sat)
        if zoom > 1.0:  # movimiento lento: desplazamos la ventana visible
            big = img.resize((int(w * zoom), int(h * zoom)), Image.BILINEAR)
            x = int((big.width - w) * pan[0])
            y = int((big.height - h) * pan[1])
            img = big.crop((x, y, x + w, y + h))
        if self.veil > 0:
            img = Image.blend(img, Image.new("RGB", (w, h), self.veil_color), self.veil)
        if self.vignette:
            img.paste(Image.new("RGB", (w, h), "#000000"), (0, 0), self._vignette((w, h)))
        return img


class Backdrop:
    """Dibuja el fondo en varios lienzos (Canvas) de la ventana."""

    def __init__(self, root, surfaces, appearance: dict, veil_color: str, log=print):
        self.root = root
        self.surfaces = list(surfaces)
        self.log = log
        self.a = dict(appearance)
        self.veil_color = veil_color
        self.fx = Effects(self.a, veil_color)
        self.photos = {}
        self.frame: Optional[Image.Image] = None     # fuente actual (antes de efectos)
        self.cover = None
        self.prev_frame = None
        self.fade_t0 = 0.0
        self._src_img = None
        self._gif = None
        self._cap = None
        self._job = None
        self._resize_job = None
        self._last_full = None
        root.bind("<Configure>", self._on_resize, add="+")
        self.configure(self.a)

    # ------------------------------------------------------------ configuración
    def configure(self, appearance: dict):
        self.a = dict(appearance)
        self.fx = Effects(self.a, self.veil_color)
        self._stop_media()
        mode, path = self.a.get("bg_mode", "none"), self.a.get("bg_file", "")
        try:
            if mode == "image" and path:
                self._src_img = Image.open(path).convert("RGB")
                self._src_img.thumbnail((1920, 1920))
            elif mode == "video" and path:
                if path.lower().endswith(GIF_EXT):
                    g = Image.open(path)
                    self._gif = [(f.convert("RGB").copy(), (f.info.get("duration") or 80) / 1000)
                                 for f in ImageSequence.Iterator(g)]
                    self._gif_i, self._gif_t = 0, time.time()
                elif CV2_OK:
                    self._cap = cv2.VideoCapture(path)
                    if not self._cap.isOpened():
                        raise RuntimeError("no se pudo abrir el video")
                    self._vfps = self._cap.get(cv2.CAP_PROP_FPS) or 30
                    self._vt0 = time.time()
                else:
                    raise RuntimeError("falta el componente de video (opencv). Usa un GIF o reinstala.")
        except Exception as e:
            self.log(f"Fondo: {e}")
            self.a["bg_mode"] = "none"
        self.render(force=True)
        self._schedule()

    def set_cover(self, cover):
        """La app avisa cuando cambia la portada (modo 'Portada de la canción')."""
        if cover is self.cover:
            return
        self.prev_frame = self._source()
        self.cover = cover
        self.fade_t0 = time.time()
        if self.a.get("bg_mode") == "cover":
            self.render(force=True)
            self._schedule()

    @property
    def active(self) -> bool:
        return self.a.get("bg_mode", "none") != "none" and self._source() is not None

    # ------------------------------------------------------------ fuentes
    def _source(self) -> Optional[Image.Image]:
        mode = self.a.get("bg_mode", "none")
        if mode == "image":
            return self._src_img
        if mode == "cover":
            return self.cover
        if mode == "video":
            if self._gif:
                now = time.time()
                while now - self._gif_t >= self._gif[self._gif_i][1]:
                    self._gif_t += self._gif[self._gif_i][1]
                    self._gif_i = (self._gif_i + 1) % len(self._gif)
                    if now - self._gif_t > 2:
                        self._gif_t = now
                return self._gif[self._gif_i][0]
            if self._cap is not None:
                # avanzamos al cuadro que toca según el reloj (sin ir más lento que el video)
                want = int((time.time() - self._vt0) * self._vfps)
                pos = int(self._cap.get(cv2.CAP_PROP_POS_FRAMES))
                for _ in range(max(0, min(want - pos, 30))):
                    self._cap.grab()
                ok, fr = self._cap.read()
                if not ok:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self._vt0 = time.time()
                    ok, fr = self._cap.read()
                    if not ok:
                        return self.frame
                h, w = fr.shape[:2]
                if max(w, h) > 960:  # bajamos la resolución antes de convertir (más rápido)
                    k = 960 / max(w, h)
                    fr = cv2.resize(fr, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)
                self.frame = Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
                return self.frame
        return None

    def _animated(self) -> bool:
        mode = self.a.get("bg_mode", "none")
        if mode == "video":
            return True
        if mode in ("image", "cover") and self.a.get("motion"):
            return True
        return mode == "cover" and time.time() - self.fade_t0 < 0.7

    # ------------------------------------------------------------ dibujo
    def _visible(self) -> bool:
        try:
            return self.root.state() not in ("withdrawn", "iconic")
        except Exception:
            return True

    def render(self, force=False):
        if not self._visible() and not force:
            return
        W, H = self.root.winfo_width(), self.root.winfo_height()
        if W < 50 or H < 50:
            return
        src = self._source() if self.a.get("bg_mode", "none") != "none" else None
        if src is None:
            self._clear_all()
            return
        zoom, pan = 1.0, (0.5, 0.5)
        if self.a.get("motion"):
            t = time.time()
            zoom = 1.12
            pan = (0.5 + 0.5 * math.sin(t * 0.08), 0.5 + 0.5 * math.cos(t * 0.06))
        full = self.fx.apply(src, W, H, zoom, pan)
        # fundido al cambiar de portada
        if self.a.get("bg_mode") == "cover" and self.prev_frame is not None:
            k = (time.time() - self.fade_t0) / 0.6
            if k < 1:
                old = self.fx.apply(self.prev_frame, W, H, zoom, pan)
                full = Image.blend(old, full, max(0.0, k))
            else:
                self.prev_frame = None
        self._last_full = full
        self._paint(full)

    def _paint(self, full: Image.Image):
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        for cv in self.surfaces:
            try:
                if not cv.winfo_ismapped():
                    continue
                x, y = cv.winfo_rootx() - rx, cv.winfo_rooty() - ry
                w, h = cv.winfo_width(), cv.winfo_height()
                if w < 2 or h < 2:
                    continue
                part = full.crop((x, y, x + w, y + h))
                ph = self.photos.get(str(cv))
                if ph is not None and (ph.width(), ph.height()) == (w, h):
                    ph.paste(part)  # reutiliza la imagen de Tk: mucho más rápido que crear otra
                else:
                    ph = ImageTk.PhotoImage(part)
                    self.photos[str(cv)] = ph
                if not cv.find_withtag("bd"):
                    cv.create_image(0, 0, anchor="nw", tags="bd")
                cv.itemconfig("bd", image=ph)
                cv.tag_lower("bd")
            except Exception:
                continue

    def attach(self, cv):
        """Tras borrar un lienzo (p. ej. al redibujar el dispositivo) vuelve a poner el fondo."""
        if self._last_full is not None and self.active:
            self._paint(self._last_full)

    def _clear_all(self):
        self._last_full = None
        for cv in self.surfaces:
            try:
                cv.delete("bd")
            except Exception:
                pass
        self.photos.clear()

    # ------------------------------------------------------------ bucle
    def _schedule(self):
        if self._job:
            try:
                self.root.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        if self._animated():
            fps = max(5, min(30, int(self.a.get("fps", 15))))
            self._job = self.root.after(int(1000 / fps), self._tick)

    def _tick(self):
        self._job = None
        try:
            self.render()
        except Exception as e:
            self.log(f"Fondo: {e}")
        self._schedule()

    def _on_resize(self, e):
        if e.widget is not self.root:
            return
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(120, lambda: self.render(force=True))

    def _stop_media(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
        self._cap, self._gif, self._src_img = None, None, None

    def stop(self):
        if self._job:
            try:
                self.root.after_cancel(self._job)
            except Exception:
                pass
        self._stop_media()
