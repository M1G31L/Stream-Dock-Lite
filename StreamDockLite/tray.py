"""
tray.py - Icono de Stream Dock Lite junto al reloj de Windows (bandeja).

Al cerrar la ventana la app sigue funcionando aquí, así el N3E no deja de
responder. Doble clic en el icono = abrir la ventana.
Las órdenes del menú se mandan a la app por una cola (on_command), porque el
menú corre en su propio hilo y tkinter solo se puede tocar desde el principal.
"""

from __future__ import annotations

import os
import threading
from typing import Callable

from PIL import Image

try:
    import pystray
    TRAY_OK = True
except Exception:  # pragma: no cover
    pystray = None
    TRAY_OK = False

HERE = os.path.dirname(os.path.abspath(__file__))


class Tray:
    def __init__(self, on_command: Callable[[str], None]):
        self.on_command = on_command
        self.icon = None

    @property
    def available(self) -> bool:
        return TRAY_OK

    def start(self):
        if not TRAY_OK:
            return
        try:
            image = Image.open(os.path.join(HERE, "app.ico"))
        except Exception:
            image = Image.new("RGB", (64, 64), "#1DB954")
        cmd = lambda name: (lambda icon, item: self.on_command(name))
        menu = pystray.Menu(
            pystray.MenuItem("Abrir Stream Dock Lite", cmd("show"), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("⏯  Play / Pausa", cmd("play")),
            pystray.MenuItem("⏭  Siguiente", cmd("next")),
            pystray.MenuItem("⏮  Anterior", cmd("prev")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", cmd("quit")),
        )
        self.icon = pystray.Icon("StreamDockLite", image, "Stream Dock Lite", menu)
        threading.Thread(target=self.icon.run, daemon=True, name="tray").start()

    def notify(self, text: str, title: str = "Stream Dock Lite"):
        try:
            if self.icon:
                self.icon.notify(text, title)
        except Exception:
            pass

    def set_tooltip(self, text: str):
        try:
            if self.icon:
                self.icon.title = text[:120]
        except Exception:
            pass

    def stop(self):
        try:
            if self.icon:
                self.icon.stop()
        except Exception:
            pass
