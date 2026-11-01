"""
icons.py - Biblioteca de iconos.

Lugares donde se buscan iconos:
  1. carpeta "iconos" junto a la app  (copia aquí tus iconos y aparecen solos)
  2. %APPDATA%\\StreamDockLite\\iconos  (donde guarda lo que importas desde la app)

Se pueden importar archivos sueltos, carpetas, .zip y .rar/.7z.
Para .rar/.7z se usa el "tar" que trae Windows 11 (libarchive); si no puede,
se pide descomprimirlo antes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

EXTS = (".png", ".jpg", ".jpeg", ".ico", ".bmp", ".gif", ".webp")
HERE = os.path.dirname(os.path.abspath(__file__))


def icon_dirs(app_dir: str) -> list[str]:
    return [os.path.join(HERE, "iconos"), os.path.join(app_dir, "iconos")]


def list_icons(app_dir: str) -> list[str]:
    """Todos los iconos disponibles, ordenados por carpeta y nombre."""
    out, seen = [], set()
    for base in icon_dirs(app_dir):
        if not os.path.isdir(base):
            continue
        for root, _, files in os.walk(base):
            for f in sorted(files, key=str.lower):
                if f.lower().endswith(EXTS):
                    p = os.path.join(root, f)
                    key = os.path.normcase(os.path.abspath(p))
                    if key not in seen:
                        seen.add(key)
                        out.append(p)
    return out


def display_name(path: str, app_dir: str) -> str:
    for base in icon_dirs(app_dir):
        try:
            rel = os.path.relpath(path, base)
            if not rel.startswith(".."):
                return os.path.splitext(rel)[0].replace("\\", "/")
        except ValueError:
            pass
    return os.path.splitext(os.path.basename(path))[0]


def _copy_images(src_dir: str, dest_dir: str) -> int:
    n = 0
    for root, _, files in os.walk(src_dir):
        for f in files:
            if not f.lower().endswith(EXTS) or f.startswith("._"):
                continue
            rel = os.path.relpath(root, src_dir)
            dst = os.path.join(dest_dir, rel) if rel != "." else dest_dir
            os.makedirs(dst, exist_ok=True)
            shutil.copyfile(os.path.join(root, f), os.path.join(dst, f))
            n += 1
    return n


def _safe_extract_zip(path: str, dest: str):
    with zipfile.ZipFile(path) as z:
        for m in z.infolist():
            target = os.path.abspath(os.path.join(dest, m.filename))
            if not target.startswith(os.path.abspath(dest) + os.sep):
                continue  # evita rutas peligrosas tipo ../../
            if m.is_dir():
                continue
            if m.filename.lower().endswith(EXTS):
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(m) as s, open(target, "wb") as d:
                    shutil.copyfileobj(s, d)


def _extract_with_tar(path: str, dest: str):
    """Windows 11 incluye tar.exe (libarchive), que abre .rar y .7z."""
    tar = shutil.which("tar") or os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "tar.exe")
    flags = 0x08000000 if sys.platform == "win32" else 0  # sin ventana de consola
    r = subprocess.run([tar, "-xf", path, "-C", dest], capture_output=True, text=True, creationflags=flags)
    if r.returncode != 0:
        raise RuntimeError(
            "Windows no pudo abrir este archivo. Descomprímelo con clic derecho → "
            "«Extraer todo» (o WinRAR/7-Zip) e importa la carpeta.")


def import_icons(paths: list[str], app_dir: str) -> tuple[int, str]:
    """Importa archivos, carpetas, .zip y .rar. Devuelve (cantidad, carpeta destino)."""
    lib = os.path.join(app_dir, "iconos")
    os.makedirs(lib, exist_ok=True)
    total = 0
    last_dest = lib
    for p in paths:
        name = os.path.splitext(os.path.basename(p.rstrip("\\/")))[0] or "iconos"
        low = p.lower()
        if os.path.isdir(p):
            last_dest = os.path.join(lib, name)
            total += _copy_images(p, last_dest)
        elif low.endswith((".zip", ".rar", ".7z")):
            last_dest = os.path.join(lib, name)
            with tempfile.TemporaryDirectory() as tmp:
                if low.endswith(".zip"):
                    _safe_extract_zip(p, tmp)
                else:
                    _extract_with_tar(p, tmp)
                total += _copy_images(tmp, last_dest)
        elif low.endswith(EXTS):
            shutil.copyfile(p, os.path.join(lib, os.path.basename(p)))
            total += 1
    return total, last_dest
