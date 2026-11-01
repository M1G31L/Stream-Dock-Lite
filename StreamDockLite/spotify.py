"""
spotify.py - Conexión con Spotify.

Tres capas, de la más simple a la más completa:

1. Controles multimedia de Windows (SMTC). Sin cuentas ni claves: funciona
   con la app de escritorio de Spotify (gratis o Premium). Da título,
   artista, portada, estado, progreso, aleatorio y repetir, y permite
   controlar la reproducción solo en Spotify (no en YouTube u otras apps).
2. Mezclador de volumen de Windows (pycaw): sube/baja/silencia SOLO Spotify.
3. API web de Spotify (opcional): necesaria solo para "Me gusta".
   Requiere crear una app gratis en developer.spotify.com (la cuenta dueña
   debe ser Premium según las reglas de Spotify de 2026).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass, field, replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Optional

from PIL import Image

IS_WIN = sys.platform == "win32"

# ---- dependencias opcionales (solo Windows) ---------------------------------
try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    )
    from winrt.windows.storage.streams import Buffer, DataReader, InputStreamOptions
    SMTC_OK = True
except Exception:  # pragma: no cover
    MediaManager = None
    SMTC_OK = False

try:
    from winrt.windows.media import MediaPlaybackAutoRepeatMode as RepeatMode
except Exception:  # pragma: no cover
    RepeatMode = None

try:
    import comtypes  # noqa: F401
    from pycaw.pycaw import AudioUtilities
    PYCAW_OK = True
except Exception:  # pragma: no cover
    PYCAW_OK = False

PLAYING = 4  # GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING


@dataclass
class SpotifyState:
    running: bool = False          # ¿hay una sesión de Spotify activa?
    playing: bool = False
    title: str = ""
    artist: str = ""
    album: str = ""
    cover: Optional[Image.Image] = field(default=None, repr=False)
    position: float = 0.0          # segundos
    duration: float = 0.0
    shuffle: Optional[bool] = None
    repeat: Optional[int] = None   # 0 no, 1 canción, 2 lista
    volume: Optional[float] = None  # 0..1 (volumen de Spotify en Windows)
    muted: bool = False
    liked: Optional[bool] = None   # requiere la API web
    pos_time: float = 0.0          # momento en que se leyó position


    def live_position(self) -> float:
        """Posición estimada ahora mismo (Spotify actualiza el progreso con poca frecuencia)."""
        if self.playing and self.pos_time:
            return min(self.duration or 1e9, self.position + time.time() - self.pos_time)
        return self.position


def _secs(v) -> float:
    if v is None:
        return 0.0
    if hasattr(v, "total_seconds"):
        return float(v.total_seconds())
    if hasattr(v, "duration"):  # TimeSpan antiguo (unidades de 100 ns)
        return v.duration / 10_000_000
    return float(v)


def _open_spotify():
    if IS_WIN:
        try:
            os.startfile("spotify:")  # type: ignore[attr-defined]
            return
        except Exception:
            pass
    webbrowser.open("https://open.spotify.com")


# =============================================================================
# 1 + 2: controles de Windows y volumen
# =============================================================================
class SpotifyLink:
    def __init__(self, on_change: Callable[[SpotifyState], None], data_dir: str):
        self.on_change = on_change
        self.state = SpotifyState()
        self.web = SpotifyWeb(data_dir)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._manager = None
        self._last_track = None
        self._last_pos_raw = None
        self._audio_jobs: "list[Callable]" = []
        self._audio_cv = threading.Condition()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        # nivel de sonido de Spotify (para teclas que reaccionan a la música)
        self.level = 0.0
        self.beat_t = 0.0
        self._meter_thread = None

    @property
    def available(self) -> bool:
        return SMTC_OK

    @property
    def volume_available(self) -> bool:
        return PYCAW_OK

    # ---------------- arranque ----------------
    def start(self):
        if SMTC_OK:
            threading.Thread(target=self._run_loop, daemon=True, name="spotify-smtc").start()
        if PYCAW_OK:
            threading.Thread(target=self._audio_worker, daemon=True, name="spotify-vol").start()

    def stop(self):
        self._stop.set()
        with self._audio_cv:
            self._audio_cv.notify_all()

    def _emit(self, **changes):
        with self._lock:
            new = replace(self.state, **changes)
            if new == self.state:
                return
            self.state = new
        try:
            self.on_change(new)
        except Exception:
            pass

    # ---------------- SMTC ----------------
    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._poll_forever())

    async def _session(self):
        if self._manager is None:
            self._manager = await MediaManager.request_async()
        for s in self._manager.get_sessions():
            try:
                if "spotify" in (s.source_app_user_model_id or "").lower():
                    return s
            except Exception:
                continue
        return None

    async def _poll_forever(self):
        while not self._stop.is_set():
            try:
                await self._poll()
            except Exception:
                self._manager = None  # se recrea en el siguiente ciclo
            await asyncio.sleep(0.5)

    async def _poll(self):
        s = await self._session()
        if s is None:
            if self.state.running:
                self._last_track = None
                self._emit(running=False, playing=False, title="", artist="", album="",
                           cover=None, position=0.0, duration=0.0, liked=None)
            return
        info = s.get_playback_info()
        playing = int(info.playback_status) == PLAYING
        shuffle = info.is_shuffle_active
        repeat = info.auto_repeat_mode
        repeat = int(repeat) if repeat is not None else None
        tl = s.get_timeline_properties()
        pos, dur = _secs(tl.position), _secs(tl.end_time)

        changes = dict(running=True, playing=playing, shuffle=shuffle, repeat=repeat, duration=dur)
        if pos != self._last_pos_raw or playing != self.state.playing:
            self._last_pos_raw = pos
            changes.update(position=pos, pos_time=time.time())

        props = await s.try_get_media_properties_async()
        title, artist = props.title or "", props.artist or ""
        if (title, artist) != self._last_track:
            self._last_track = (title, artist)
            cover = await self._read_cover(props.thumbnail)
            changes.update(title=title, artist=artist, album=props.album_title or "",
                           cover=cover, liked=None, position=pos, pos_time=time.time())
            if self.web.connected:
                threading.Thread(target=self._refresh_liked, daemon=True).start()
        self._emit(**changes)

    async def _read_cover(self, ref) -> Optional[Image.Image]:
        if ref is None:
            return None
        try:
            stream = await ref.open_read_async()
            size = int(stream.size) or 5_000_000
            buf = Buffer(size)
            await stream.read_async(buf, buf.capacity, InputStreamOptions.READ_AHEAD)
            data = None
            try:
                data = bytes(memoryview(buf))[: buf.length]   # pywinrt 2.x
            except Exception:
                reader = DataReader.from_buffer(buf)
                try:
                    arr = bytearray(buf.length)
                    reader.read_bytes(arr)
                    data = bytes(arr)
                except Exception:
                    data = bytes(reader.read_bytes(buf.length))
            # Se guarda tal cual; el recorte (franja de Spotify) se hace al dibujar,
            # según lo que elijas en la tecla.
            img = Image.open(io.BytesIO(data))
            img.load()
            return img
        except Exception:
            return None

    def _call(self, coro_factory) -> bool:
        """Ejecuta un comando en el hilo de SMTC. Abre Spotify si no está."""
        if not (SMTC_OK and self._loop):
            return False

        async def run():
            s = await self._session()
            if s is None:
                _open_spotify()
                return
            await coro_factory(s)
            await asyncio.sleep(0.15)
            await self._poll()

        asyncio.run_coroutine_threadsafe(run(), self._loop)
        return True

    # ---------------- comandos públicos ----------------
    def play_pause(self):
        return self._call(lambda s: s.try_toggle_play_pause_async())

    def next(self):
        return self._call(lambda s: s.try_skip_next_async())

    def previous(self):
        return self._call(lambda s: s.try_skip_previous_async())

    def toggle_shuffle(self):
        cur = bool(self.state.shuffle)
        return self._call(lambda s: s.try_change_shuffle_active_async(not cur))

    def cycle_repeat(self):
        if RepeatMode is None:
            return False
        nxt = {0: 2, 2: 1, 1: 0}.get(self.state.repeat or 0, 0)  # no → lista → canción → no
        mode = RepeatMode(nxt)
        return self._call(lambda s: s.try_change_auto_repeat_mode_async(mode))

    def open(self):
        _open_spotify()

    # ---------------- volumen (solo Spotify) ----------------
    def _audio_worker(self):
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        last_read = 0.0
        while not self._stop.is_set():
            with self._audio_cv:
                if not self._audio_jobs:
                    self._audio_cv.wait(timeout=1.0)
                jobs, self._audio_jobs = self._audio_jobs, []
            for job in jobs:
                try:
                    job()
                except Exception:
                    self._sess_cache = None  # Spotify se reinició: buscar de nuevo
            if jobs or time.time() - last_read > 1.5:
                last_read = time.time()
                self._read_volume()

    def _sessions(self):
        """Sesiones de audio de Spotify. Recorrer todos los procesos es lento en
        Windows, así que la lista se recuerda 5 s (o hasta que falle)."""
        cached = getattr(self, "_sess_cache", None)
        if cached and time.time() - cached[0] < 5:
            return cached[1]
        out = []
        for s in AudioUtilities.GetAllSessions():
            try:
                if s.Process and s.Process.name().lower().startswith("spotify"):
                    out.append(s.SimpleAudioVolume)
            except Exception:
                continue
        self._sess_cache = (time.time(), out)
        return out

    def _read_volume(self):
        vols = self._sessions()
        if vols:
            try:
                vol, muted = vols[0].GetMasterVolume(), vols[0].GetMute()
            except Exception:
                self._sess_cache = None
                return
            self._emit(volume=round(vol, 3), muted=bool(muted))
        elif self.state.volume is not None:
            self._emit(volume=None, muted=False)

    def _queue_audio(self, fn):
        if not PYCAW_OK:
            return False
        with self._audio_cv:
            self._audio_jobs.append(fn)
            self._audio_cv.notify()
        return True

    # ---------------- nivel de sonido en vivo (solo Spotify) ----------------
    def want_level(self, on: bool):
        """Activa la lectura del nivel solo si alguna tecla lo usa (ahorra procesador)."""
        self._want_level = on
        if on and PYCAW_OK and not (self._meter_thread and self._meter_thread.is_alive()):
            self._meter_thread = threading.Thread(target=self._meter_loop, daemon=True, name="spotify-meter")
            self._meter_thread.start()

    def _meters(self):
        cached = getattr(self, "_meter_cache", None)
        if cached and time.time() - cached[0] < 5:
            return cached[1]
        from pycaw.pycaw import IAudioMeterInformation
        out = []
        for s in AudioUtilities.GetAllSessions():
            try:
                if s.Process and s.Process.name().lower().startswith("spotify"):
                    out.append(s._ctl.QueryInterface(IAudioMeterInformation))
            except Exception:
                continue
        self._meter_cache = (time.time(), out)
        return out

    def _meter_loop(self):
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        avg = 0.0
        while not self._stop.is_set() and getattr(self, "_want_level", False):
            peak = 0.0
            try:
                for m in self._meters():
                    peak = max(peak, float(m.GetPeakValue()))
            except Exception:
                self._meter_cache = None
            if self.state.muted or not self.state.playing:
                peak = 0.0
            # sube rápido, baja suave (se ve más natural)
            self.level = peak if peak > self.level else self.level * 0.82 + peak * 0.18
            avg = avg * 0.94 + peak * 0.06
            now = time.time()
            if peak > 0.25 and peak > avg * 1.45 and now - self.beat_t > 0.22:
                self.beat_t = now  # golpe / beat
            time.sleep(1 / 30)
        self.level = 0.0

    def volume_step(self, delta: float):
        def job():
            for v in self._sessions():
                v.SetMasterVolume(max(0.0, min(1.0, v.GetMasterVolume() + delta)), None)
                if delta > 0 and v.GetMute():
                    v.SetMute(0, None)
        return self._queue_audio(job)

    def toggle_mute(self):
        def job():
            vols = self._sessions()
            if vols:
                m = 0 if vols[0].GetMute() else 1
                for v in vols:
                    v.SetMute(m, None)
        return self._queue_audio(job)

    # ---------------- Me gusta (API web) ----------------
    def _refresh_liked(self):
        try:
            self._emit(liked=self.web.is_current_liked())
        except Exception:
            pass

    def toggle_like(self) -> str:
        if not self.web.connected:
            return "Para 'Me gusta' conecta tu cuenta en Ajustes → Spotify"
        liked = self.web.toggle_current_like()
        self._emit(liked=liked)
        return "Añadida a Tus Me gusta" if liked else "Quitada de Tus Me gusta"


# =============================================================================
# 3: API web de Spotify (OAuth PKCE, sin contraseña ni secreto)
# =============================================================================
REDIRECT_PORT = 8754
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/callback"
SCOPES = ("user-library-read user-library-modify user-read-currently-playing user-read-playback-state "
          "user-modify-playback-state")
API = "https://api.spotify.com/v1"


class SpotifyWeb:
    def __init__(self, data_dir: str):
        self.path = os.path.join(data_dir, "spotify_token.json")
        self.client_id = ""
        self.tok: dict = {}
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self.client_id, self.tok = d.get("client_id", ""), d.get("token", {})
        except Exception:
            pass

    @property
    def connected(self) -> bool:
        return bool(self.client_id and self.tok.get("refresh_token"))

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"client_id": self.client_id, "token": self.tok}, f)

    def disconnect(self):
        self.tok = {}
        try:
            os.remove(self.path)
        except Exception:
            pass

    # ---- autorización ----
    def connect(self, client_id: str, timeout: float = 180) -> str:
        """Abre el navegador para autorizar. Bloquea hasta terminar (usar en hilo)."""
        self.client_id = client_id.strip()
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(16)
        result: dict = {}

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if q.get("state", [""])[0] == state:
                    result.update({k: v[0] for k, v in q.items()})
                ok = "code" in result
                msg = ("¡Listo! Ya puedes cerrar esta pestaña y volver a Stream Dock Lite."
                       if ok else "No se pudo autorizar. Vuelve a intentarlo.")
                body = f"<html><body style='font-family:sans-serif;background:#121212;color:#fff;padding:40px'><h2>{msg}</h2></body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body.encode())

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", REDIRECT_PORT), H)
        srv.timeout = 1
        url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
            "client_id": self.client_id, "response_type": "code", "redirect_uri": REDIRECT_URI,
            "code_challenge_method": "S256", "code_challenge": challenge, "scope": SCOPES, "state": state,
        })
        webbrowser.open(url)
        t0 = time.time()
        try:
            while not result and time.time() - t0 < timeout:
                srv.handle_request()
        finally:
            srv.server_close()
        if "code" not in result:
            raise RuntimeError(result.get("error") or "Tiempo agotado esperando la autorización")
        self.tok = self._token({"grant_type": "authorization_code", "code": result["code"],
                                "redirect_uri": REDIRECT_URI, "code_verifier": verifier})
        self._save()
        return "Cuenta de Spotify conectada"

    def _token(self, data: dict) -> dict:
        data = dict(data, client_id=self.client_id)
        req = urllib.request.Request("https://accounts.spotify.com/api/token",
                                     data=urllib.parse.urlencode(data).encode(),
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as r:
            tok = json.load(r)
        tok["expires_at"] = time.time() + tok.get("expires_in", 3600) - 60
        if "refresh_token" not in tok and self.tok.get("refresh_token"):
            tok["refresh_token"] = self.tok["refresh_token"]
        return tok

    def _access(self) -> str:
        if not self.connected:
            raise RuntimeError("Cuenta de Spotify no conectada")
        if time.time() > self.tok.get("expires_at", 0):
            self.tok = self._token({"grant_type": "refresh_token", "refresh_token": self.tok["refresh_token"]})
            self._save()
        return self.tok["access_token"]

    def _api(self, method: str, path: str, params: Optional[dict] = None, body: Optional[dict] = None):
        url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
        headers = {"Authorization": f"Bearer {self._access()}"}
        data = b"" if method in ("PUT", "DELETE") else None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, method=method, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            raise RuntimeError(f"Spotify {e.code}: {detail}") from None
        return json.loads(raw) if raw else None

    def play_uri(self, uri: str):
        """Empieza a reproducir una playlist, álbum, artista o canción."""
        kind = uri.split(":")[1] if uri.count(":") >= 2 else ""
        body = {"uris": [uri]} if kind in ("track", "episode") else {"context_uri": uri}
        self._api("PUT", "/me/player/play", body=body)

    # ---- acciones ----
    def current_uri(self) -> Optional[str]:
        d = self._api("GET", "/me/player/currently-playing")
        return ((d or {}).get("item") or {}).get("uri")

    def is_current_liked(self) -> Optional[bool]:
        uri = self.current_uri()
        if not uri:
            return None
        r = self._api("GET", "/me/library/contains", {"uris": uri})
        return bool(r and r[0])

    def toggle_current_like(self) -> bool:
        uri = self.current_uri()
        if not uri:
            raise RuntimeError("No hay ninguna canción sonando en Spotify")
        r = self._api("GET", "/me/library/contains", {"uris": uri})
        liked = bool(r and r[0])
        self._api("DELETE" if liked else "PUT", "/me/library", {"uris": uri})
        return not liked
