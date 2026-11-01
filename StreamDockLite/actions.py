"""
actions.py - Acciones que se ejecutan al pulsar teclas o girar perillas.
Usa solo la API de Windows (ctypes), sin dependencias extra.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser

IS_WIN = sys.platform == "win32"

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    ULONG_PTR = ctypes.c_size_t

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, KEYEVENTF_EXTENDED = 0x2, 0x4, 0x1

    def _send(*inputs):
        arr = (INPUT * len(inputs))(*inputs)
        user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))

    def _key(vk: int, up: bool = False):
        flags = KEYEVENTF_KEYUP if up else 0
        if vk in _EXTENDED:
            flags |= KEYEVENTF_EXTENDED
        return INPUT(1, _U(ki=KEYBDINPUT(vk, 0, flags, 0, 0)))

    def _uni(ch: str, up: bool = False):
        flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
        return INPUT(1, _U(ki=KEYBDINPUT(0, ord(ch), flags, 0, 0)))

VK = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
    "enter": 0x0D, "esc": 0x1B, "tab": 0x09, "space": 0x20, "backspace": 0x08,
    "delete": 0x2E, "supr": 0x2E, "insert": 0x2D, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "up": 0x26, "down": 0x28, "left": 0x25,
    "right": 0x27, "printscreen": 0x2C, "imprpant": 0x2C, "capslock": 0x14,
    "vol_up": 0xAF, "vol_down": 0xAE, "mute": 0xAD, "play_pause": 0xB3,
    "next": 0xB0, "prev": 0xB1, "stop": 0xB2,
}
VK.update({f"f{i}": 0x6F + i for i in range(1, 25)})
_EXTENDED = {0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22, 0x26, 0x28, 0x25, 0x27, 0x5B}

MEDIA = ["play_pause", "next", "prev", "stop", "mute", "vol_up", "vol_down"]
MEDIA_LABELS = {"play_pause": "Play / Pausa", "next": "Siguiente", "prev": "Anterior",
                "stop": "Detener", "mute": "Silenciar", "vol_up": "Subir volumen",
                "vol_down": "Bajar volumen"}


def _vk_for(token: str) -> int:
    t = token.strip().lower()
    if t in VK:
        return VK[t]
    if len(t) == 1:
        if IS_WIN:
            r = user32.VkKeyScanW(ord(t))
            if r != -1:
                return r & 0xFF
        return ord(t.upper())
    raise ValueError(f"Tecla desconocida: {token}")


def hotkey(combo: str):
    if not IS_WIN:
        raise RuntimeError("Solo Windows")
    keys = [_vk_for(k) for k in combo.replace(" ", "").split("+") if k]
    _send(*[_key(k) for k in keys])
    time.sleep(0.02)
    _send(*[_key(k, True) for k in reversed(keys)])


def press_vk(name: str):
    if not IS_WIN:
        raise RuntimeError("Solo Windows")
    vk = VK[name]
    _send(_key(vk), _key(vk, True))


def type_text(text: str):
    if not IS_WIN:
        raise RuntimeError("Solo Windows")
    for ch in text.replace("\r\n", "\n"):
        if ch == "\n":
            press_vk("enter")
            continue
        # Emojis y otros caracteres fuera del BMP se envían como pares sustitutos
        raw = ch.encode("utf-16-le")
        for i in range(0, len(raw), 2):
            unit = chr(int.from_bytes(raw[i:i + 2], "little"))
            _send(_uni(unit), _uni(unit, True))


def run_action(action: dict, on_page=None) -> str:
    """Ejecuta una acción. Devuelve un texto corto para el registro."""
    kind = (action or {}).get("type", "ninguna")
    val = (action or {}).get("value", "") or ""
    if kind == "ninguna" or not kind:
        return ""
    if kind == "abrir":
        if val.startswith(("http://", "https://")):
            webbrowser.open(val)
        elif IS_WIN:
            os.startfile(os.path.expandvars(val))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", val])
        return f"Abriendo {val}"
    if kind == "atajo":
        hotkey(val)
        return f"Atajo {val}"
    if kind == "texto":
        type_text(val)
        return "Texto escrito"
    if kind == "multimedia":
        press_vk(val or "play_pause")
        return MEDIA_LABELS.get(val, val)
    if kind == "comando":
        flags = 0x08000000 if IS_WIN else 0  # CREATE_NO_WINDOW
        subprocess.Popen(val, shell=True, creationflags=flags)
        return f"Comando: {val}"
    if kind == "pagina":
        if on_page:
            on_page(val)
        return f"Página: {val}"
    return f"Acción desconocida: {kind}"
