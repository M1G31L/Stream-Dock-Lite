"""
gallery.py - Ventana con la vista previa ANIMADA de cada estilo de la tecla
«Ahora suena». Clic en un estilo para elegirlo.
"""

from __future__ import annotations

import dataclasses
import time
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

import render
import spotify

PANEL = "#202026"
PANEL2 = "#2a2a31"
FG = "#e8e8ec"
MUTED = "#8b8b96"
GREEN = render.SPOTIFY_GREEN


def sample_state(app_state) -> "spotify.SpotifyState":
    """La canción actual; si Spotify está cerrado, una portada de ejemplo."""
    if app_state.running and app_state.cover is not None:
        return app_state
    img = Image.new("RGB", (300, 300), "#1b1035")
    d = ImageDraw.Draw(img)
    for i in range(9):
        r = 140 - i * 15
        d.ellipse([150 - r, 150 - r, 150 + r, 150 + r], fill=("#e2365b", "#f6a04d", "#7b2ff7")[i % 3])
    return spotify.SpotifyState(running=True, playing=True, title="Canción de ejemplo — Artista",
                                cover=img, duration=200, position=70, pos_time=time.time())


class StyleGallery:
    TILE = 112
    COLS = 4

    def __init__(self, root, key: dict, state_getter, on_choose):
        self.key = key
        self.state_getter = state_getter
        self.on_choose = on_choose
        w = self.w = tk.Toplevel(root, bg=PANEL, padx=16, pady=12)
        w.title("Estilos de «Ahora suena»")
        w.transient(root)
        w.resizable(False, False)
        tk.Label(w, text="Elige cómo se ve la portada en la tecla", bg=PANEL, fg=FG,
                 font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=self.COLS, sticky="w")
        tk.Label(w, text="Se animan igual que en el N3E. Clic para elegir  ·  ✦ = animado",
                 bg=PANEL, fg=MUTED).grid(row=1, column=0, columnspan=self.COLS, sticky="w", pady=(0, 8))
        self.tiles = {}
        for n, (style, (name, animated)) in enumerate(render.NOW_STYLES.items()):
            cell = tk.Frame(w, bg=PANEL2, padx=6, pady=6, cursor="hand2")
            cell.grid(row=2 + n // self.COLS, column=n % self.COLS, padx=5, pady=5, sticky="n")
            img = tk.Label(cell, bg=PANEL2)
            img.pack()
            lbl = tk.Label(cell, text=name + ("  ✦" if animated else ""), bg=PANEL2, fg=FG,
                           font=("Segoe UI", 8), wraplength=self.TILE)
            lbl.pack(pady=(4, 0))
            for wd in (cell, img, lbl):
                wd.bind("<Button-1>", lambda e, s=style: self.choose(s))
            self.tiles[style] = (cell, img, lbl)
        last = 2 + (len(self.tiles) + self.COLS - 1) // self.COLS
        self.paused = tk.BooleanVar(value=False)
        ttk.Checkbutton(w, text="Ver cómo queda en pausa", variable=self.paused).grid(
            row=last, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(w, text="Cerrar", command=w.destroy).grid(row=last, column=self.COLS - 1, sticky="e", pady=(8, 0))
        self._tick()

    def choose(self, style):
        self.key["now_style"] = style
        self.on_choose(style)
        self._highlight()

    def _highlight(self):
        cur = self.key.get("now_style", "portada")
        for style, (cell, img, lbl) in self.tiles.items():
            cell.config(bg=GREEN if style == cur else PANEL2)

    def _tick(self):
        try:
            if not self.w.winfo_exists():
                return
        except Exception:
            return
        st = sample_state(self.state_getter())
        if self.paused.get():
            st = dataclasses.replace(st, playing=False)
        now = time.time()
        for style, (cell, img, lbl) in self.tiles.items():
            k = dict(self.key, now_style=style, transition="nada")
            ph = ImageTk.PhotoImage(render.render_key(k, st, self.TILE, now=now))
            img.config(image=ph)
            img.image = ph
        self._highlight()
        self.w.after(140, self._tick)
