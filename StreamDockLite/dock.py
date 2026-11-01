"""
dock.py - Controlador USB-HID para Stream Dock (Mirabox / Ajazz y clones).

Exclusivo para el Stream Dock N3E ("N3E_1B05"):
6 teclas con pantalla, 3 botones sin pantalla y 3 perillas.

El protocolo se basa en el trabajo de ingeniería inversa de la comunidad
(proyectos mirajazz y opendeck-akp03). Mirabox no publica el protocolo.
"""

from __future__ import annotations

import io
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

try:
    import hid  # paquete "hidapi"
except Exception:  # pragma: no cover - se informa en la interfaz
    hid = None

from PIL import Image

# --------------------------------------------------------------------------
# Único modelo soportado: Stream Dock N3E  (el software oficial lo muestra
# como "N3E_1B05": 1B05 es su identificador de producto USB)
# --------------------------------------------------------------------------
TARGET_PID = 0x1B05
TARGET_TAG = "1B05"
TARGET_NAME = "Stream Dock N3E"
VENDOR_USAGE_PAGE = 0xFFA0  # 65440: interfaz de control (la que acepta comandos)

KEY_COUNT = 6       # teclas con pantalla
BUTTON_COUNT = 3    # botones sin pantalla
ENCODER_COUNT = 3   # perillas


def _hdr(*cmd: int) -> list[int]:
    """Cabecera 'CRT\\0\\0' + comando (con el byte 0 = report id)."""
    return [0x00, 0x43, 0x52, 0x54, 0x00, 0x00, *cmd]


# --------------------------------------------------------------------------
# Detección
# --------------------------------------------------------------------------
@dataclass
class Candidate:
    path: bytes
    vid: int
    pid: int
    name: str
    protocol: int
    usage_page: int
    interface: int
    product: str
    manufacturer: str
    serial: str
    reason: str
    score: int = 0

    @property
    def vidpid(self) -> str:
        return f"{self.vid:04X}:{self.pid:04X}"


def list_hid() -> list[dict]:
    if hid is None:
        return []
    try:
        return list(hid.enumerate())
    except Exception:
        return []


def _text(info: dict) -> str:
    parts = [
        str(info.get("product_string") or ""),
        str(info.get("manufacturer_string") or ""),
        str(info.get("serial_number") or ""),
    ]
    p = info.get("path") or b""
    parts.append(p.decode(errors="ignore") if isinstance(p, bytes) else str(p))
    return " ".join(parts).upper()


def score_device(info: dict, custom=None) -> tuple[int, str, str, int]:
    """Devuelve (puntaje, motivo, nombre, protocolo). 0 = no es el N3E_1B05."""
    pid = info.get("product_id", 0)
    up = info.get("usage_page", 0)
    if pid == TARGET_PID:
        reason = "PID 1B05"
    elif TARGET_TAG in _text(info):
        reason = "Identificador 1B05 en el nombre o ruta"
    else:
        return 0, "", "", 0
    # Un mismo equipo expone varias interfaces; preferimos la de control.
    score = 100 if up == VENDOR_USAGE_PAGE else 60
    return score, reason, TARGET_NAME, 3


def find_candidates(custom=None) -> list[Candidate]:
    out: list[Candidate] = []
    for info in list_hid():
        s, reason, name, proto = score_device(info, custom)
        if s <= 0:
            continue
        out.append(Candidate(
            path=info["path"], vid=info["vendor_id"], pid=info["product_id"],
            name=name, protocol=proto, usage_page=info.get("usage_page", 0),
            interface=info.get("interface_number", -1),
            product=info.get("product_string") or "",
            manufacturer=info.get("manufacturer_string") or "",
            serial=info.get("serial_number") or "", reason=reason, score=s,
        ))
    out.sort(key=lambda c: c.score, reverse=True)
    return out


# --------------------------------------------------------------------------
# Eventos
# --------------------------------------------------------------------------
@dataclass
class DockEvent:
    kind: str            # key | button | knob_turn | knob_press | raw | status | error
    index: int = -1
    value: int = 0       # 1 = presionado, 0 = soltado; giro: -1 / +1
    raw: bytes = b""
    text: str = ""


# Códigos de entrada N3 / N3E / AKP03 (byte 9 del reporte)
KEY_CODES = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
BUTTON_CODES = {0x25: 0, 0x30: 1, 0x31: 2}
KNOB_TURN = {0x90: (0, -1), 0x91: (0, 1), 0x50: (1, -1), 0x51: (1, 1), 0x60: (2, -1), 0x61: (2, 1)}
KNOB_PRESS = {0x33: 0, 0x35: 1, 0x34: 2}


def parse_input(data: bytes, both_states: bool) -> list[DockEvent]:
    if len(data) < 11:
        return []
    if not data.startswith(b"ACK"):
        return [DockEvent("raw", raw=bytes(data[:16]))]
    code = data[9]
    state = data[10] if both_states else 1
    evs: list[DockEvent] = []

    def press(kind: str, idx: int):
        if both_states:
            evs.append(DockEvent(kind, idx, 1 if state else 0, bytes(data[:16])))
        else:  # equipos sin estado "soltado": simulamos presionar + soltar
            evs.append(DockEvent(kind, idx, 1, bytes(data[:16])))
            evs.append(DockEvent(kind, idx, 0, bytes(data[:16])))

    if code in KEY_CODES:
        press("key", KEY_CODES[code])
    elif code in BUTTON_CODES:
        press("button", BUTTON_CODES[code])
    elif code in KNOB_TURN:
        i, d = KNOB_TURN[code]
        evs.append(DockEvent("knob_turn", i, d, bytes(data[:16])))
    elif code in KNOB_PRESS:
        press("knob_press", KNOB_PRESS[code])
    elif code == 0:
        pass  # "todas soltadas" en algunos firmwares
    else:
        evs.append(DockEvent("raw", value=code, raw=bytes(data[:16]),
                             text=f"Código desconocido 0x{code:02X}"))
    return evs


# --------------------------------------------------------------------------
# Dispositivo
# --------------------------------------------------------------------------
class DockDevice:
    def __init__(self, cand: Candidate, protocol: Optional[int] = None):
        if hid is None:
            raise RuntimeError("Falta el paquete 'hidapi' (pip install hidapi)")
        self.cand = cand
        self.protocol = protocol or cand.protocol
        self.packet = 1024 if self.protocol >= 2 else 512
        self.both_states = self.protocol >= 3
        self.lock = threading.Lock()
        self.txn = threading.RLock()  # una imagen (cabecera + datos) no se mezcla con otro comando
        self._sent: dict[int, bytes] = {}
        self.size_override: Optional[int] = None      # px de la imagen de cada tecla
        self.rotation_override: Optional[int] = None  # grados en sentido horario
        self.offset = (0, 0)                          # px: + derecha, + abajo (como se ve en el N3E)
        self.dev = hid.device()
        self.dev.open_path(cand.path)
        self.dev.set_nonblocking(False)
        self._probe_packet_size()
        self._wake()

    # ---- escritura -------------------------------------------------------
    def _write(self, buf: list[int]) -> int:
        buf = list(buf) + [0] * (1 + self.packet - len(buf))
        with self.lock:
            n = self.dev.write(buf[: 1 + self.packet])
        if n < 0:
            raise IOError(self.dev.error() or "Error de escritura HID")
        return n

    def _probe_packet_size(self):
        """Si el tamaño de paquete no es el correcto, Windows rechaza la
        escritura. Probamos 1024 y luego 512 para no depender de adivinar."""
        for size in ([self.packet] + [s for s in (1024, 512) if s != self.packet]):
            self.packet = size
            try:
                self._write(_hdr(0x43, 0x4F, 0x4E, 0x4E, 0x45, 0x43, 0x54))  # CONNECT
                return
            except Exception:
                continue
        raise IOError("El dispositivo no acepta comandos (¿está abierto el software oficial?)")

    def _wake(self):
        self._write(_hdr(0x44, 0x49, 0x53))                    # DIS (encender pantalla)
        self._write(_hdr(0x4C, 0x49, 0x47, 0, 0, 0))           # LIG

    def keep_alive(self):
        self._write(_hdr(0x43, 0x4F, 0x4E, 0x4E, 0x45, 0x43, 0x54))

    def set_brightness(self, pct: int):
        self._write(_hdr(0x4C, 0x49, 0x47, 0, 0, max(0, min(100, int(pct)))))

    def flush(self):
        self._write(_hdr(0x53, 0x54, 0x50))                    # STP

    def clear(self, key: int = 0xFF):
        with self.txn:
            self._sent.clear() if key == 0xFF else self._sent.pop(key, None)
            self._write(_hdr(0x43, 0x4C, 0x45, 0, 0, 0, 0xFF if key == 0xFF else key + 1))
            if self.protocol >= 2:
                self.flush()

    def sleep(self):
        self._write(_hdr(0x48, 0x41, 0x4E))                    # HAN

    def shutdown(self):
        try:
            self._write(_hdr(0x43, 0x4C, 0x45, 0, 0, 0x44, 0x43))
            self.sleep()
        except Exception:
            pass

    @property
    def image_size(self) -> int:
        return self.size_override or (64 if self.protocol >= 3 else 60)

    @property
    def rotation(self) -> int:
        if self.rotation_override is not None:
            return self.rotation_override
        return 90 if self.protocol >= 3 else 0

    def configure_screen(self, size: Optional[int], rotation: Optional[int], offset=(0, 0)):
        """Cambia tamaño, giro y posición de las imágenes y obliga a reenviar todas."""
        self.size_override, self.rotation_override = size, rotation
        self.offset = (int(offset[0]), int(offset[1]))
        self._sent.clear()

    def encode_image(self, img: Image.Image) -> bytes:
        s = self.image_size
        img = img.convert("RGB").resize((s, s), Image.LANCZOS)
        ox, oy = self.offset
        if ox or oy:  # mueve el dibujo dentro de la imagen (centrado fino por modelo)
            moved = Image.new("RGB", (s, s), (0, 0, 0))
            moved.paste(img, (ox, oy))
            img = moved
        rot = self.rotation % 360
        if rot:  # PIL gira en sentido antihorario
            img = img.transpose({90: Image.ROTATE_270, 180: Image.ROTATE_180, 270: Image.ROTATE_90}[rot])
        bio = io.BytesIO()
        img.save(bio, format="JPEG", quality=90)
        return bio.getvalue()

    def set_key_image(self, key: int, img: Image.Image, flush: bool = True) -> bool:
        """Envía la imagen de una tecla. Si es idéntica a la anterior no la
        reenvía (menos tráfico USB y sin parpadeos). Devuelve True si envió."""
        with self.txn:
            data = self.encode_image(img)
            if self._sent.get(key) == data:
                return False
            self._sent[key] = data
            n = len(data)
            self._write(_hdr(0x42, 0x41, 0x54, 0, 0, (n >> 8) & 0xFF, n & 0xFF, key + 1))  # BAT
            for off in range(0, n, self.packet):
                self._write([0x00] + list(data[off: off + self.packet]))
            if flush:
                self.flush()
            return True

    # ---- lectura ---------------------------------------------------------
    def read(self, timeout_ms: int = 100) -> bytes:
        try:
            d = self.dev.read(512, timeout_ms)
        except Exception as e:
            raise IOError(str(e))
        return bytes(d or b"")

    def close(self):
        try:
            self.dev.close()
        except Exception:
            pass


# --------------------------------------------------------------------------
# Gestor con reconexión automática
# --------------------------------------------------------------------------
class DockManager:
    """Hilo que busca el dispositivo, lo conecta, lee eventos y lo
    reconecta solo si se desenchufa."""

    def __init__(self, on_event: Callable[[DockEvent], None],
                 custom_vidpid: Optional[tuple[int, int]] = None,
                 protocol_override: Optional[int] = None):
        self.on_event = on_event
        self.custom = custom_vidpid
        self.protocol_override = protocol_override
        self.device: Optional[DockDevice] = None
        self.on_connect: Optional[Callable[[DockDevice], None]] = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._last_ka = 0.0

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self.device:
            self.device.shutdown()
            self.device.close()

    def reconnect(self):
        d, self.device = self.device, None
        if d:
            d.close()

    def _status(self, text: str):
        self.on_event(DockEvent("status", text=text))

    def _run(self):
        if hid is None:
            self.on_event(DockEvent("error", text="Falta 'hidapi'. Reinstala Stream Dock Lite"))
            return
        warned = False
        while not self._stop.is_set():
            if self.device is None:
                cands = find_candidates(self.custom)
                if not cands:
                    if not warned:
                        self._status("Buscando Stream Dock N3E (1B05)… conéctalo por USB")
                        warned = True
                    time.sleep(2)
                    continue
                err = None
                for c in cands:
                    try:
                        self.device = DockDevice(c, self.protocol_override)
                        break
                    except Exception as e:
                        err = e
                if self.device is None:
                    self._status(f"Encontrado pero no se pudo abrir: {err}. "
                                 "Cierra el software oficial Stream Dock.")
                    time.sleep(3)
                    continue
                warned = False
                d = self.device
                self._status(f"Conectado: {d.cand.name} [{d.cand.vidpid}] "
                             f"protocolo v{d.protocol}, paquete {d.packet} B")
                if self.on_connect:
                    try:
                        self.on_connect(d)
                    except Exception as e:
                        self.on_event(DockEvent("error", text=f"Error al dibujar: {e}"))
            try:
                data = self.device.read(100)
                if data:
                    for ev in parse_input(data, self.device.both_states):
                        self.on_event(ev)
                if time.time() - self._last_ka > 10:
                    self.device.keep_alive()
                    self._last_ka = time.time()
            except Exception as e:
                self._status(f"Desconectado ({e}). Reintentando…")
                self.reconnect()
                time.sleep(1)
