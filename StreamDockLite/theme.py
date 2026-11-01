"""
theme.py - Temas de la interfaz (oscuro / claro / como Windows) y color de acento.

Los colores se aplican antes de construir la ventana, por eso cambiar de tema
o de acento reinicia la app (tarda un par de segundos). El fondo con imagen o
video sí cambia al momento (ver background.py).
"""

from __future__ import annotations

import sys

PALETTES = {
    "dark": dict(BG="#16161a", PANEL="#202026", PANEL2="#2a2a31", LINE="#34343c",
                 FG="#e8e8ec", MUTED="#8b8b96", SELECT_FG="#ffffff", DANGER="#e0675b",
                 LINK_ON="#1f3d2b"),
    "light": dict(BG="#eef0f4", PANEL="#ffffff", PANEL2="#e9ebf0", LINE="#d4d7df",
                  FG="#1c1d22", MUTED="#6a6d78", SELECT_FG="#1c1d22", DANGER="#c0392b",
                  LINK_ON="#d7f5e2"),
}
THEMES = {"dark": "Oscuro", "light": "Claro", "system": "Como Windows"}
ACCENTS = {
    "#3d7bfd": "Azul", "#1DB954": "Verde Spotify", "#8b5cf6": "Morado", "#ec4899": "Rosa",
    "#f97316": "Naranja", "#ef4444": "Rojo", "#06b6d4": "Cian",
}
DEFAULT_APPEARANCE = {
    "theme": "dark", "accent": "#3d7bfd",
    "bg_mode": "none", "bg_file": "",          # none | cover | image | video
    "blur": 18, "veil": 45, "saturation": 110, "vignette": True, "motion": False, "fps": 15,
}


def system_prefers_light() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 1
    except Exception:
        return False


def resolve(theme: str) -> str:
    if theme == "system":
        return "light" if system_prefers_light() else "dark"
    return theme if theme in PALETTES else "dark"


def lighten(hex_color: str, amount: float) -> str:
    """Aclara (amount > 0) u oscurece (amount < 0) un color #rrggbb."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    if amount >= 0:
        r, g, b = (int(c + (255 - c) * amount) for c in (r, g, b))
    else:
        r, g, b = (int(c * (1 + amount)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def readable_on(hex_color: str) -> str:
    """Texto negro o blanco, el que se lea mejor sobre ese color."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#ffffff"


def colors(appearance: dict) -> dict:
    a = dict(DEFAULT_APPEARANCE, **(appearance or {}))
    mode = resolve(a["theme"])
    pal = dict(PALETTES[mode])
    pal["ACCENT"] = a.get("accent") or DEFAULT_APPEARANCE["accent"]
    pal["ACCENT_HOVER"] = lighten(pal["ACCENT"], 0.18)
    pal["ACCENT_FG"] = readable_on(pal["ACCENT"])
    pal["MODE"] = mode
    return pal


def apply_to_modules(appearance: dict, *modules):
    """Sustituye las constantes de color (BG, PANEL, …) en los módulos de la interfaz."""
    pal = colors(appearance)
    for m in modules:
        for k, v in pal.items():
            if hasattr(m, k) or k in ("ACCENT", "ACCENT_HOVER", "ACCENT_FG", "SELECT_FG",
                                      "DANGER", "LINK_ON", "MODE"):
                setattr(m, k, v)
    return pal


def titlebar(window, dark: bool):
    """Barra de título oscura en Windows 10/11 (si el sistema lo permite)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        val = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (nuevo / antiguo)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val),
                                                          ctypes.sizeof(val)) == 0:
                break
    except Exception:
        pass
