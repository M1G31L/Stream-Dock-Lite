"""
sounds.py - Sonidos al pulsar teclas y botones.

Los sonidos incluidos se generan la primera vez (no hace falta descargar nada)
en %APPDATA%\\StreamDockLite\\sonidos. Puedes añadir tus propios .wav a esa
carpeta y aparecen en la lista.
"""

from __future__ import annotations

import math
import os
import random
import struct
import sys
import wave

RATE = 44100
BUILTIN = {"clic": "Clic", "pop": "Pop", "tick": "Tic", "suave": "Suave", "mecanico": "Teclado mecánico",
           "burbuja": "Burbuja"}


def _synth(name: str) -> list:
    rnd = random.Random(7)
    out = []
    if name == "clic":
        for i in range(int(RATE * 0.025)):
            t = i / RATE
            env = math.exp(-t * 260)
            out.append(env * (0.6 * rnd.uniform(-1, 1) + 0.6 * math.sin(2 * math.pi * 2200 * t)))
    elif name == "pop":
        ph = 0.0
        for i in range(int(RATE * 0.08)):
            t = i / RATE
            f = 900 - 650 * (t / 0.08)
            ph += 2 * math.pi * f / RATE
            out.append(math.sin(ph) * math.exp(-t * 45) * min(1, t * 400))
    elif name == "tick":
        for i in range(int(RATE * 0.018)):
            t = i / RATE
            out.append(math.sin(2 * math.pi * 3200 * t) * math.exp(-t * 320))
    elif name == "suave":
        for i in range(int(RATE * 0.12)):
            t = i / RATE
            out.append(math.sin(2 * math.pi * 660 * t) * min(1, t * 120) * math.exp(-t * 28) * 0.8
                       + math.sin(2 * math.pi * 990 * t) * math.exp(-t * 40) * 0.25)
    elif name == "mecanico":
        for start, amp in ((0.0, 1.0), (0.045, 0.6)):  # al bajar y al subir la tecla
            pad = int(RATE * start) - len(out)
            out += [0.0] * max(0, pad)
            for i in range(int(RATE * 0.03)):
                t = i / RATE
                out.append(amp * math.exp(-t * 180) * (0.7 * rnd.uniform(-1, 1) + 0.5 * math.sin(2 * math.pi * 1400 * t)))
    elif name == "burbuja":
        ph = 0.0
        for i in range(int(RATE * 0.09)):
            t = i / RATE
            f = 300 + 1500 * (t / 0.09) ** 1.5
            ph += 2 * math.pi * f / RATE
            out.append(math.sin(ph) * math.sin(math.pi * t / 0.09))
    return out


def folder(app_dir: str) -> str:
    return os.path.join(app_dir, "sonidos")


def ensure(app_dir: str):
    d = folder(app_dir)
    os.makedirs(d, exist_ok=True)
    for name in BUILTIN:
        p = os.path.join(d, name + ".wav")
        if os.path.exists(p):
            continue
        samples = _synth(name)
        peak = max(1e-6, max(abs(x) for x in samples))
        with wave.open(p, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(b"".join(struct.pack("<h", int(x / peak * 0.42 * 32767)) for x in samples))


def available(app_dir: str) -> dict:
    """{clave: nombre visible}: «ninguno», los incluidos y los .wav que añadas."""
    out = {"ninguno": "Sin sonido"}
    out.update(BUILTIN)
    try:
        for f in sorted(os.listdir(folder(app_dir)), key=str.lower):
            k, ext = os.path.splitext(f)
            if ext.lower() == ".wav" and k not in out:
                out[k] = k + " (tuyo)"
    except Exception:
        pass
    return out


def play(app_dir: str, name: str):
    if not name or name == "ninguno":
        return
    p = os.path.join(folder(app_dir), name + ".wav")
    if not os.path.exists(p):
        if name in BUILTIN:
            ensure(app_dir)
        else:
            return
    if sys.platform == "win32":
        import winsound
        winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
