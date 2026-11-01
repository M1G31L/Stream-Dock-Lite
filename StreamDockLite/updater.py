"""
updater.py - Actualizaciones seguras de Stream Dock Lite.

Una actualización es un .zip con la carpeta StreamDockLite/ (la misma forma
que el paquete normal). Antes de instalar:
  • se comprueba que sea un paquete válido (app.py + version.py, rutas seguras),
  • se guarda una copia de la versión actual para poder volver atrás,
  • el usuario siempre confirma.

Conexión con Claude: si el usuario la activa, la app vigila una carpeta de
entrada. Claude solo puede dejar archivos ahí si además el usuario le da
acceso a esa carpeta desde la app de escritorio de Claude («+» → «Add folder»).
Cada actualización que llega se muestra y espera un «Sí» del usuario.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

APP_HOME = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "StreamDockLite")
INBOX = os.path.join(DATA, "entrada_claude")
BACKUPS = os.path.join(DATA, "copias")
ALLOWED = (".py", ".txt", ".md", ".bat", ".cmd", ".ps1", ".json", ".png", ".ico", ".jpg", ".jpeg",
           ".gif", ".webp", ".bmp")
KEEP = {"iconos"}  # carpetas del usuario que nunca se borran


def current_version() -> str:
    try:
        with open(os.path.join(APP_HOME, "version.py"), encoding="utf-8") as f:
            return re.search(r'VERSION\s*=\s*"([^"]+)"', f.read()).group(1)
    except Exception:
        return "0"


def vtuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4]) or (0,)


class UpdateInfo:
    def __init__(self, path, version, notes, root, needs_deps, sha256):
        self.path, self.version, self.notes = path, version, notes
        self.root, self.needs_deps, self.sha256 = root, needs_deps, sha256


def inspect(zip_path: str) -> UpdateInfo:
    """Valida el paquete y lee su versión y notas. Lanza ValueError si no sirve."""
    if not zipfile.is_zipfile(zip_path):
        raise ValueError("No es un archivo .zip válido")
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        root = next((n[: -len("version.py")] for n in names if n.endswith("version.py")
                     and n.count("/") <= 1), None)
        if root is None or root + "app.py" not in names:
            raise ValueError("El paquete no contiene app.py y version.py")
        for n in names:
            if n.startswith("/") or ".." in n.split("/") or ":" in n:
                raise ValueError(f"Ruta no permitida en el paquete: {n}")
        src = z.read(root + "version.py").decode("utf-8", "replace")
        m = re.search(r'VERSION\s*=\s*"([^"]+)"', src)
        notes = re.search(r'NOTES\s*=\s*"([^"]*)"', src)
        reqs_new = z.read(root + "requirements.txt").decode() if root + "requirements.txt" in names else ""
    try:
        with open(os.path.join(APP_HOME, "requirements.txt"), encoding="utf-8") as f:
            reqs_old = f.read()
    except Exception:
        reqs_old = ""
    h = hashlib.sha256(open(zip_path, "rb").read()).hexdigest()
    norm = lambda s: sorted(l.strip() for l in s.splitlines() if l.strip())
    return UpdateInfo(zip_path, m.group(1) if m else "?", notes.group(1) if notes else "",
                      root, norm(reqs_new) != norm(reqs_old), h)


def _app_files(base: str):
    for entry in os.listdir(base):
        if entry in KEEP or entry in ("__pycache__",) or entry.startswith("."):
            continue
        yield entry


def backup() -> str:
    os.makedirs(BACKUPS, exist_ok=True)
    dest = os.path.join(BACKUPS, f"{current_version()}_{time.strftime('%Y%m%d-%H%M%S')}")
    os.makedirs(dest)
    for e in _app_files(APP_HOME):
        s = os.path.join(APP_HOME, e)
        (shutil.copytree if os.path.isdir(s) else shutil.copy2)(s, os.path.join(dest, e))
    # nos quedamos con las 5 copias más recientes
    for old in sorted(os.listdir(BACKUPS))[:-5]:
        shutil.rmtree(os.path.join(BACKUPS, old), ignore_errors=True)
    return dest


def apply(info: UpdateInfo, log=print) -> str:
    """Instala la actualización. Devuelve la carpeta de la copia de seguridad."""
    bk = backup()
    log(f"Copia de seguridad: {bk}")
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(info.path) as z:
        for m in z.infolist():
            if m.is_dir() or not m.filename.startswith(info.root):
                continue
            rel = m.filename[len(info.root):]
            if not rel.lower().endswith(ALLOWED):
                continue
            target = os.path.abspath(os.path.join(tmp, rel))
            if not target.startswith(os.path.abspath(tmp) + os.sep):
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(m) as s, open(target, "wb") as d:
                shutil.copyfileobj(s, d)
        try:
            for root, _, files in os.walk(tmp):
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), tmp)
                    dst = os.path.join(APP_HOME, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(os.path.join(root, f), dst)
        except Exception:
            restore(bk)  # si algo falla a mitad, volvemos a dejarlo como estaba
            raise
    if info.needs_deps:
        log("Instalando componentes nuevos…")
        install_deps()
    return bk


def install_deps():
    py = sys.executable.replace("pythonw.exe", "python.exe")
    flags = 0x08000000 if sys.platform == "win32" else 0
    subprocess.run([py, "-m", "pip", "install", "-q", "-r", os.path.join(APP_HOME, "requirements.txt")],
                   check=True, creationflags=flags)


def list_backups() -> list[str]:
    if not os.path.isdir(BACKUPS):
        return []
    return sorted(os.listdir(BACKUPS), reverse=True)


def restore(backup_dir: str):
    if not os.path.isdir(backup_dir):
        backup_dir = os.path.join(BACKUPS, backup_dir)
    for e in os.listdir(backup_dir):
        s, d = os.path.join(backup_dir, e), os.path.join(APP_HOME, e)
        if os.path.isdir(s):
            shutil.rmtree(d, ignore_errors=True)
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)


def restart():
    """Abre de nuevo la app (la nueva espera a que esta se cierre)."""
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        exe = exe[:-10] + "pythonw.exe"
    flags = 0x00000008 if sys.platform == "win32" else 0  # DETACHED_PROCESS
    subprocess.Popen([exe, os.path.join(APP_HOME, "app.py"), "--restart"], creationflags=flags,
                     close_fds=True, cwd=APP_HOME)


# ---------------------------------------------------------------------------
# Carpeta de entrada (conexión con Claude)
# ---------------------------------------------------------------------------
def ensure_inbox():
    os.makedirs(INBOX, exist_ok=True)
    readme = os.path.join(INBOX, "LEEME.txt")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as f:
            f.write("Carpeta de conexión con Claude.\r\n"
                    "Si activas «Conexión con Claude» en Stream Dock Lite y das acceso a esta carpeta\r\n"
                    "en la app de escritorio de Claude (+ > Add folder), Claude puede dejar aquí\r\n"
                    "actualizaciones (.zip). La app siempre te preguntará antes de instalarlas.\r\n"
                    "Puedes quitar el acceso cuando quieras.\r\n")
    for sub in ("instaladas", "rechazadas"):
        os.makedirs(os.path.join(INBOX, sub), exist_ok=True)


def pending() -> list[str]:
    if not os.path.isdir(INBOX):
        return []
    out = []
    for f in os.listdir(INBOX):
        p = os.path.join(INBOX, f)
        if f.lower().endswith(".zip") and os.path.isfile(p):
            # esperamos a que termine de copiarse (tamaño estable)
            try:
                s1 = os.path.getsize(p)
                time.sleep(0.3)
                if os.path.getsize(p) == s1 and s1 > 0:
                    out.append(p)
            except OSError:
                pass
    return sorted(out, key=os.path.getmtime)


def archive(path: str, accepted: bool):
    dest = os.path.join(INBOX, "instaladas" if accepted else "rechazadas")
    os.makedirs(dest, exist_ok=True)
    name = time.strftime("%Y%m%d-%H%M%S_") + os.path.basename(path)
    try:
        shutil.move(path, os.path.join(dest, name))
    except Exception:
        try:
            os.remove(path)
        except Exception:
            pass
