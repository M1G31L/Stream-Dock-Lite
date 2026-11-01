"""
Stream Dock Lite - controlador estilo Elgato Stream Deck para el
Stream Dock N3E (N3E_1B05), con integración de Spotify.

Se abre con el acceso directo «Stream Dock Lite» que crea el instalador.
"""

from __future__ import annotations

import copy
import json
import os
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

import actions
import background
import dock
import gallery
import icons
import playlists
import reactions
import sounds
import render
import spotify
import theme
import tray
import updater
from version import VERSION

APP_NAME = "Stream Dock Lite"
APP_VERSION = VERSION
APP_ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "StreamDockLite")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
CONFIG_VERSION = 2
LONG_PRESS_S = 0.6
VOL_STEP = 0.04  # 4 % por "clic" de perilla

# ---- paleta (estilo Stream Deck) ---------------------------------------------
BG = "#16161a"
PANEL = "#202026"
PANEL2 = "#2a2a31"
LINE = "#34343c"
FG = "#e8e8ec"
MUTED = "#8b8b96"
ACCENT = "#3d7bfd"
GREEN = render.SPOTIFY_GREEN
# (theme.py sustituye estos colores según el tema elegido antes de crear la ventana)
ACCENT_HOVER = "#5a8ffd"
ACCENT_FG = "#ffffff"
SELECT_FG = "#ffffff"
DANGER = "#e0675b"
LINK_ON = "#1f3d2b"
MODE = "dark"

# =============================================================================
# Catálogo de acciones
# =============================================================================
# tipo -> (etiqueta, categoría, valor que necesita: None | path | text | media | page, descripción)
TYPES = {
    "ninguna": ("Ninguna", "", None, ""),
    "sp_now": ("Ahora suena", "Spotify", None, "Muestra solo la portada de la canción. Pulsar = play/pausa."),
    "sp_play": ("Play / Pausa", "Spotify", None, "El icono cambia según el estado."),
    "sp_next": ("Siguiente", "Spotify", None, "Salta a la siguiente canción."),
    "sp_prev": ("Anterior", "Spotify", None, "Vuelve a la canción anterior."),
    "sp_like": ("Me gusta", "Spotify", None, "Guarda/quita de Tus Me gusta (requiere conectar cuenta)."),
    "sp_shuffle": ("Aleatorio", "Spotify", None, "Activa o desactiva el modo aleatorio."),
    "sp_repeat": ("Repetir", "Spotify", None, "No repetir → lista → canción."),
    "sp_progress": ("Progreso", "Spotify", None, "Tiempo y barra de la canción. Pulsar = play/pausa."),
    "sp_volume": ("Volumen de Spotify", "Spotify", None, "Muestra el volumen de Spotify. Pulsar = silenciar."),
    "sp_vol_up": ("Subir volumen de Spotify", "Spotify", None, "Solo Spotify, no el resto del PC."),
    "sp_vol_down": ("Bajar volumen de Spotify", "Spotify", None, "Solo Spotify, no el resto del PC."),
    "sp_mute": ("Silenciar Spotify", "Spotify", None, "Solo Spotify."),
    "sp_open": ("Abrir Spotify", "Spotify", None, "Abre la app de Spotify."),
    "sp_playlist": ("Playlist / álbum", "Spotify", "text",
                    "Pega el enlace (en Spotify: Compartir → Copiar enlace). La tecla muestra su portada; "
                    "al pulsar empieza a sonar."),
    "abrir": ("Abrir app / archivo / web", "Sistema", "path", "Programa, archivo, carpeta o dirección web."),
    "atajo": ("Atajo de teclado", "Sistema", "text", "Ej.: ctrl+shift+m · win+shift+s · alt+f4"),
    "texto": ("Escribir texto", "Sistema", "text", "Escribe el texto donde esté el cursor."),
    "comando": ("Ejecutar comando", "Sistema", "text", "Comando de Windows (cmd)."),
    "multimedia": ("Multimedia (sistema)", "Sistema", "media", "Teclas multimedia de Windows."),
    "pagina": ("Cambiar de página", "Navegación", "page", "Muestra otra página de teclas."),
}
DIALS = {  # preajustes para perillas
    "dial_sp_vol": ("Volumen de Spotify", {"left": "sp_vol_down", "right": "sp_vol_up", "press": "sp_mute"}),
    "dial_sp_track": ("Pistas de Spotify", {"left": "sp_prev", "right": "sp_next", "press": "sp_play"}),
    "dial_sys_vol": ("Volumen del sistema", {"left": ("multimedia", "vol_down"),
                                             "right": ("multimedia", "vol_up"), "press": ("multimedia", "mute")}),
}


def A(t="ninguna", v=""):
    return {"type": t, "value": v}


def action_label(a: dict) -> str:
    t = (a or {}).get("type", "ninguna")
    lbl = TYPES.get(t, (t,))[0]
    cat = TYPES.get(t, ("", ""))[1]
    return f"{cat} · {lbl}" if cat else lbl


# =============================================================================
# Configuración
# =============================================================================
def K(t, title="", color=render.DARK, value=""):
    return {"title": title, "title_pos": "bottom", "color": color, "text_color": "#FFFFFF",
            "icon": "", "action": A(t, value), "long_action": A()}


def B(t="ninguna", title="", value=""):
    return {"title": title, "action": A(t, value), "long_action": A()}


def dial(preset: str) -> dict:
    name, parts = DIALS[preset]
    d = {"title": name}
    for k, v in parts.items():
        d[k] = A(*v) if isinstance(v, tuple) else A(v)
    return d


def default_config() -> dict:
    return {
        "version": CONFIG_VERSION,
        "brightness": 70,
        "protocol": "auto",
        "start_minimized": False,
        "claude_link": False,
        "close_to_tray": True,
        "saver": {"mode": "portada", "minutes": 5},
        "screen": {"size": 0, "rotation": -1, "clear_bg": True},   # 0 / -1 = automático
        "appearance": dict(theme.DEFAULT_APPEARANCE),
        "current_page": "Spotify",
        "pages": {
            "Spotify": {
                "keys": [K("sp_now"), K("sp_like"), K("sp_shuffle"),
                         K("sp_prev"), K("sp_play"), K("sp_next")],
                "buttons": [B("sp_repeat", "Repetir"), B("sp_open", "Abrir Spotify"),
                            B("pagina", "→ Sistema", "Sistema")],
            },
            "Sistema": {
                "keys": [K("abrir", "Navegador", value="https://www.google.com"),
                         K("abrir", "Archivos", value="explorer.exe"),
                         K("abrir", "Calculadora", value="calc.exe"),
                         K("atajo", "Captura", value="win+shift+s"),
                         K("atajo", "Tareas", value="ctrl+shift+esc"),
                         K("sp_progress")],
                "buttons": [B("pagina", "← Spotify", "Spotify"), B("multimedia", "Silenciar PC", "mute"),
                            B("atajo", "Escritorio", "win+d")],
            },
        },
        "knobs": [dial("dial_sp_vol"), dial("dial_sp_track"), dial("dial_sys_vol")],
    }


def blank_page() -> dict:
    return {"keys": [K("ninguna") for _ in range(dock.KEY_COUNT)],
            "buttons": [B() for _ in range(dock.BUTTON_COUNT)]}


def load_config() -> dict:
    for path in (CONFIG_PATH, CONFIG_PATH + ".bak"):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if data.get("version") != CONFIG_VERSION:
            # configuración de la versión anterior: la guardamos aparte y empezamos limpio
            try:
                shutil.copyfile(path, path + ".v1")
            except Exception:
                pass
            break
        cfg = default_config()
        cfg.update(data)
        if cfg["current_page"] not in cfg["pages"]:
            cfg["current_page"] = next(iter(cfg["pages"]))
        return cfg
    return default_config()


def save_config(cfg: dict):
    os.makedirs(APP_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    if os.path.exists(CONFIG_PATH):
        shutil.copyfile(CONFIG_PATH, CONFIG_PATH + ".bak")
    os.replace(tmp, CONFIG_PATH)


# =============================================================================
# Editor de una acción (combo + valor)
# =============================================================================
class ActionEditor(tk.Frame):
    def __init__(self, master, title, on_change, allow_none=True):
        super().__init__(master, bg=PANEL)
        self.on_change = on_change
        self.pages: list = []
        self.types = [t for t in TYPES if allow_none or t != "ninguna"]
        tk.Label(self, text=title, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
        self.cb = ttk.Combobox(self, state="readonly", width=34,
                               values=[action_label(A(t)) for t in self.types])
        self.cb.grid(row=1, column=0, columnspan=2, sticky="we", pady=(2, 3))
        self.cb.bind("<<ComboboxSelected>>", lambda e: (self._layout(), self._fire()))
        self.var = tk.StringVar()
        self.var.trace_add("write", lambda *_: self._fire())
        self.entry = ttk.Entry(self, textvariable=self.var)
        self.browse = ttk.Button(self, text="…", width=3, command=self._browse)
        self.choice = ttk.Combobox(self, state="readonly")
        self.choice.bind("<<ComboboxSelected>>", lambda e: self._fire())
        self.hint = tk.Label(self, bg=PANEL, fg=MUTED, font=("Segoe UI", 8), justify="left", wraplength=300)
        self.columnconfigure(0, weight=1)
        self._mute = False

    def _type(self) -> str:
        i = self.cb.current()
        return self.types[i] if i >= 0 else "ninguna"

    def _layout(self):
        for w in (self.entry, self.browse, self.choice, self.hint):
            w.grid_forget()
        t = self._type()
        need = TYPES[t][2]
        if need in ("path", "text"):
            self.entry.grid(row=2, column=0, sticky="we")
            if need == "path":
                self.browse.grid(row=2, column=1, padx=(3, 0))
        elif need == "media":
            self.choice["values"] = [actions.MEDIA_LABELS[m] for m in actions.MEDIA]
            self.choice.grid(row=2, column=0, columnspan=2, sticky="we")
        elif need == "page":
            self.choice["values"] = self.pages
            self.choice.grid(row=2, column=0, columnspan=2, sticky="we")
        if TYPES[t][3]:
            self.hint.config(text=TYPES[t][3])
            self.hint.grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))

    def _browse(self):
        p = filedialog.askopenfilename(title="Elegir programa o archivo")
        if p:
            self.var.set(os.path.normpath(p))

    def _fire(self):
        if not self._mute:
            self.on_change()

    def set(self, a: dict, pages):
        self._mute = True
        self.pages = list(pages)
        a = a or A()
        t = a.get("type", "ninguna")
        self.cb.current(self.types.index(t) if t in self.types else 0)
        v = a.get("value", "")
        self.var.set(v)
        self._layout()
        need = TYPES.get(t, ("", "", None))[2]
        if need == "media":
            self.choice.set(actions.MEDIA_LABELS.get(v, ""))
        elif need == "page":
            self.choice.set(v)
        self._mute = False

    def get(self) -> dict:
        t = self._type()
        need = TYPES[t][2]
        if need == "media":
            lbl = self.choice.get()
            v = next((m for m, l in actions.MEDIA_LABELS.items() if l == lbl), "play_pause")
        elif need == "page":
            v = self.choice.get()
        elif need:
            v = self.var.get()
        else:
            v = ""
        return A(t, v)


# =============================================================================
# Aplicación
# =============================================================================
KEY_PX = 104      # tamaño de tecla en pantalla
GAP = 18


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = load_config()
        self.q: "queue.Queue" = queue.Queue()
        self.selected = ("key", 0)
        self.clipboard = None
        self.loading = False
        self.press_t: dict = {}
        self.tk_imgs: dict = {}
        self.sigs: dict = {}
        self.logs: list = []
        self._save_job = None
        self.drag = None
        self.ghost = None
        self._seen_updates: set = set()
        self._asking_update = False

        # escritura al dispositivo en un hilo propio
        self.dirty: set = set()
        self.dirty_cv = threading.Condition()

        root.title(f"{APP_NAME}  {APP_VERSION}")
        root.configure(bg=BG)
        try:
            root.iconbitmap(default=APP_ICON)  # icono en ventana y diálogos
        except Exception:
            pass
        root.geometry("1180x780")
        root.minsize(1040, 700)
        self._style()
        self._build()

        self.sp = spotify.SpotifyLink(lambda st: self.q.put(("spotify", st)), APP_DIR)
        self.sp.start()
        self.last_input = time.time()
        self.saver_on = False
        self.press_at = {}
        try:
            sounds.ensure(APP_DIR)
        except Exception:
            pass
        self._tray_hint_shown = False
        self.tray = tray.Tray(lambda c: self.q.put(("tray", c)))
        self.tray.start()
        self.backdrop = background.Backdrop(
            root, [self.top_cv, self.body_cv, self.cv, self.bar_cv],
            self.cfg.get("appearance") or {}, veil_color=BG, log=lambda m: self.q.put(("log", m)))
        root.after(400, lambda: self.backdrop.render(force=True))

        proto = None if self.cfg["protocol"] == "auto" else int(self.cfg["protocol"])
        self.mgr = dock.DockManager(lambda ev: self.q.put(("dock", ev)), protocol_override=proto)
        self.mgr.on_connect = self._on_connect
        self.mgr.start()
        threading.Thread(target=self._writer, daemon=True, name="dock-writer").start()

        self.refresh_pages()
        self.redraw_device()
        self.select(("key", 0))
        if not spotify.SMTC_OK:
            self.log("Spotify: faltan componentes de Windows. Reinstala Stream Dock Lite.")
        root.after(30, self._pump)
        root.after(1000, self._tick)
        root.after(125, self._animate)
        threading.Thread(target=self._watch_inbox, daemon=True, name="claude-inbox").start()
        self._update_link_button()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind("<Map>", lambda e: self._on_map() if e.widget is root else None, add="+")
        if self.cfg.get("start_minimized") or "--min" in sys.argv:
            if self.tray.available:
                root.withdraw()   # arranca escondida junto al reloj
            else:
                root.iconify()
        self._refresh_playlist_covers()
        self._update_level_need()

    # ------------------------------------------------------------------ estilo
    def _style(self):
        s = ttk.Style(self.root)
        s.theme_use("clam")
        base = dict(background=PANEL, foreground=FG, fieldbackground=PANEL2, bordercolor=LINE,
                    lightcolor=PANEL2, darkcolor=PANEL2, arrowcolor=FG, insertcolor=FG)
        s.configure(".", **base, font=("Segoe UI", 9))
        s.configure("TButton", background=PANEL2, padding=(10, 4), relief="flat")
        s.map("TButton", background=[("active", LINE)])
        s.configure("Accent.TButton", background=ACCENT, foreground=ACCENT_FG)
        s.map("Accent.TButton", background=[("active", ACCENT_HOVER)])
        s.configure("Green.TButton", background=GREEN, foreground="#000")
        s.map("Green.TButton", background=[("active", "#3be477")])
        s.configure("TEntry", padding=4)
        s.configure("TCombobox", padding=3)
        s.map("TCombobox", fieldbackground=[("readonly", PANEL2)], foreground=[("readonly", FG)],
              selectbackground=[("readonly", PANEL2)], selectforeground=[("readonly", FG)])
        self.root.option_add("*TCombobox*Listbox.background", PANEL2)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG,
                    rowheight=30, borderwidth=0, font=("Segoe UI", 10))
        s.map("Treeview", background=[("selected", PANEL2)], foreground=[("selected", SELECT_FG)])
        s.configure("Treeview.Heading", background=PANEL, foreground=MUTED)
        s.configure("Horizontal.TScale", background=PANEL, troughcolor=PANEL2)
        s.configure("TCheckbutton", background=PANEL, foreground=FG)
        s.map("TCheckbutton", background=[("active", PANEL)])
        s.configure("TRadiobutton", background=PANEL, foreground=FG)
        s.map("TRadiobutton", background=[("active", PANEL)])
        s.configure("Vertical.TScrollbar", background=PANEL2, troughcolor=PANEL, arrowcolor=MUTED)

    # ------------------------------------------------------------------ layout
    def _build(self):
        r = self.root
        # --- barra superior ---
        # Las zonas de fondo son lienzos (Canvas): ahí se dibuja la imagen/video de fondo.
        top = self.top_cv = tk.Canvas(r, bg=BG, highlightthickness=0, height=52)
        top.pack(fill="x")
        tk.Label(top, text="Página", bg=PANEL, fg=MUTED, padx=8, pady=3).pack(side="left", padx=(14, 0), pady=10)
        self.page_cb = ttk.Combobox(top, state="readonly", width=20)
        self.page_cb.pack(side="left", padx=6)
        self.page_cb.bind("<<ComboboxSelected>>", lambda e: self.switch_page(self.page_cb.get()))
        for txt, cmd in (("＋", self.add_page), ("✎", self.rename_page), ("🗑", self.delete_page)):
            ttk.Button(top, text=txt, width=3, command=cmd).pack(side="left", padx=1)
        ttk.Button(top, text="⚙  Ajustes", command=self.open_settings).pack(side="right", padx=(0, 14))
        ttk.Button(top, text="🎨  Apariencia", command=self.open_appearance).pack(side="right", padx=(0, 6))
        self.link_btn = tk.Button(top, relief="flat", bd=0, padx=10, pady=3, cursor="hand2",
                                  font=("Segoe UI", 9, "bold"), command=self.toggle_link)
        self.link_btn.pack(side="right", padx=8)
        self.bright = tk.IntVar(value=self.cfg["brightness"])
        ttk.Scale(top, from_=5, to=100, variable=self.bright, length=130,
                  command=lambda v: self._brightness()).pack(side="right", padx=(6, 18))
        tk.Label(top, text="☀", bg=PANEL, fg=MUTED, font=("Segoe UI", 11), padx=6).pack(side="right")
        self.sp_badge = tk.Label(top, text="", bg=PANEL, fg=MUTED, font=("Segoe UI", 9), padx=8, pady=3)
        self.sp_badge.pack(side="right", padx=10)
        self.dev_badge = tk.Label(top, text="● Buscando N3E…", bg=PANEL, fg=DANGER,
                                  font=("Segoe UI", 9, "bold"), padx=8, pady=3)
        self.dev_badge.pack(side="right", padx=4)

        body = self.body_cv = tk.Canvas(r, bg=BG, highlightthickness=0)
        body.pack(fill="both", expand=True)

        # --- biblioteca de acciones (derecha) ---
        lib = tk.Frame(body, bg=PANEL, width=290)
        lib.pack(side="right", fill="y", padx=(12, 14), pady=(0, 6))
        lib.pack_propagate(False)
        tk.Label(lib, text="Acciones", bg=PANEL, fg=FG, font=("Segoe UI", 12, "bold")
                 ).pack(anchor="w", padx=12, pady=(12, 4))
        self.search = tk.StringVar()
        se = ttk.Entry(lib, textvariable=self.search)
        se.pack(fill="x", padx=12, pady=(0, 8))
        self.search.trace_add("write", lambda *_: self.fill_library())
        self.tree = ttk.Treeview(lib, show="tree", selectmode="browse")
        self.tree.pack(fill="both", expand=True, padx=6)
        self.tree.tag_configure("cat", foreground=MUTED, font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("sp", foreground=FG)
        tk.Label(lib, text="Arrastra una acción a una tecla, botón o perilla.\n"
                           "Doble clic = asignar al control seleccionado.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 8), justify="left").pack(anchor="w", padx=12, pady=8)
        self.tree.bind("<ButtonPress-1>", self._lib_press)
        self.tree.bind("<B1-Motion>", self._drag_motion)
        self.tree.bind("<ButtonRelease-1>", self._drag_release)
        self.tree.bind("<Double-1>", self._lib_double)
        self.fill_library()

        # --- dispositivo (centro) ---
        self.cv = tk.Canvas(body, bg=BG, highlightthickness=0, height=430)
        self.cv.pack(side="top", fill="both", expand=True, padx=(14, 0))
        self.cv.bind("<Configure>", lambda e: self.redraw_device())
        self.cv.bind("<ButtonPress-1>", self._cv_press)
        self.cv.bind("<B1-Motion>", self._drag_motion)
        self.cv.bind("<ButtonRelease-1>", self._drag_release)
        self.cv.bind("<Button-3>", self._cv_menu)

        # --- inspector (abajo) ---
        self.insp = tk.Frame(body, bg=PANEL, padx=14, pady=12)
        self.insp.pack(side="bottom", fill="x", padx=(14, 0), pady=(6, 6))
        self._build_inspector()

        # --- barra de estado ---
        bar = self.bar_cv = tk.Canvas(r, bg=BG, highlightthickness=0, height=30)
        bar.pack(fill="x", side="bottom", before=body)
        self.status = tk.Label(bar, text="", bg=PANEL, fg=MUTED, font=("Segoe UI", 8), anchor="w", padx=8)
        self.status.pack(side="left", padx=(14, 0), pady=4)
        tk.Button(bar, text="Ver registro", bg=PANEL, fg=MUTED, bd=0, activebackground=PANEL2, padx=8,
                  activeforeground=FG, command=self.show_log, cursor="hand2").pack(side="right", padx=14, pady=4)

    def _build_inspector(self):
        f = self.insp
        self.preview = tk.Label(f, bg=PANEL)
        self.preview.grid(row=0, column=0, rowspan=4, sticky="n", padx=(0, 14))
        self.insp_title = tk.Label(f, bg=PANEL, fg=FG, font=("Segoe UI", 12, "bold"), anchor="w")
        self.insp_title.grid(row=0, column=1, columnspan=3, sticky="we")

        # columna de apariencia (solo teclas)
        self.look = tk.Frame(f, bg=PANEL)
        self.look.grid(row=1, column=1, sticky="nw", padx=(0, 18))
        tk.Label(self.look, text="Título", bg=PANEL, fg=MUTED).grid(row=0, column=0, sticky="w")
        self.title_txt = tk.Text(self.look, width=22, height=2, bg=PANEL2, fg=FG, insertbackground=FG,
                                 relief="flat", font=("Segoe UI", 10), padx=6, pady=4)
        self.title_txt.grid(row=1, column=0, columnspan=3, sticky="we", pady=(2, 6))
        self.title_txt.bind("<KeyRelease>", lambda e: self._changed())
        self.pos_cb = ttk.Combobox(self.look, state="readonly", width=8, values=["Arriba", "Centro", "Abajo"])
        self.pos_cb.grid(row=2, column=0, sticky="w")
        self.pos_cb.bind("<<ComboboxSelected>>", lambda e: self._changed())
        self.bg_btn = tk.Button(self.look, text="Fondo", width=7, relief="flat",
                                command=lambda: self._pick_color("color"))
        self.bg_btn.grid(row=2, column=1, padx=4)
        self.fg_btn = tk.Button(self.look, text="Texto", width=7, relief="flat",
                                command=lambda: self._pick_color("text_color"))
        self.fg_btn.grid(row=2, column=2)
        icons = tk.Frame(self.look, bg=PANEL)
        icons.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Button(icons, text="🖼  Iconos…", command=self._pick_icon).pack(side="left")
        ttk.Button(icons, text="Quitar icono", command=self._clear_icon).pack(side="left", padx=4)

        # estilo de la tecla «Ahora suena»
        self.now_frame = tk.Frame(f, bg=PANEL)
        tk.Label(self.now_frame, text="Estilo de la portada", bg=PANEL, fg=FG,
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Button(self.now_frame, text="✨ Ver estilos…", style="Green.TButton",
                   command=self.open_style_gallery).grid(row=0, column=2, sticky="e")
        self.now_cbs = {}
        rows = (("now_style", "Estilo", render.NOW_STYLES, lambda v: v[0]),
                ("pause_style", "Al pausar", render.PAUSE_STYLES, lambda v: v),
                ("transition", "Al cambiar canción", render.TRANSITIONS, lambda v: v),
                ("cover_crop", "Recorte", render.CROP_MODES, lambda v: v))
        for r, (fld, lbl, options, name) in enumerate(rows, start=1):
            tk.Label(self.now_frame, text=lbl, bg=PANEL, fg=MUTED).grid(row=r, column=0, sticky="w", pady=2)
            cb = ttk.Combobox(self.now_frame, state="readonly", width=34,
                              values=[name(v) for v in options.values()])
            cb.grid(row=r, column=1, columnspan=2, sticky="w", padx=6, pady=2)
            cb.bind("<<ComboboxSelected>>", lambda e: self._changed())
            self.now_cbs[fld] = (cb, list(options))
        self.crop_pct = tk.IntVar(value=15)
        self.crop_row = tk.Frame(self.now_frame, bg=PANEL)
        tk.Label(self.crop_row, text="Quitar de abajo", bg=PANEL, fg=MUTED).pack(side="left")
        ttk.Scale(self.crop_row, from_=0, to=35, variable=self.crop_pct, length=150,
                  command=lambda v: self._changed()).pack(side="left", padx=6)
        self.crop_lbl = tk.Label(self.crop_row, bg=PANEL, fg=FG, width=5)
        self.crop_lbl.pack(side="left")

        # reacción al pulsar / sonido / música (todas las teclas menos «Ahora suena»)
        self.react_frame = tk.Frame(f, bg=PANEL)
        tk.Label(self.react_frame, text="Reacción", bg=PANEL, fg=FG,
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        self.react_cbs = {}
        self.react_rows = {}
        for r, (fld, lbl, opts) in enumerate((("press_fx", "Al pulsar", reactions.PRESS_FX),
                                               ("press_sound", "Sonido", {}),
                                               ("music_fx", "Con la música", reactions.MUSIC_FX)), start=1):
            l = tk.Label(self.react_frame, text=lbl, bg=PANEL, fg=MUTED)
            cb = ttk.Combobox(self.react_frame, state="readonly", width=24, values=list(opts.values()))
            cb.bind("<<ComboboxSelected>>", lambda e: self._changed())
            self.react_cbs[fld] = (cb, list(opts))
            self.react_rows[fld] = (l, cb, r)
        ttk.Button(self.react_frame, text="▶", width=3, command=self._preview_sound).grid(row=2, column=2, padx=(4, 0))
        tools_r = tk.Frame(self.react_frame, bg=PANEL)
        tools_r.grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Button(tools_r, text="Aplicar a todas", command=self._react_to_all).pack(side="left")
        ttk.Button(tools_r, text="Carpeta de sonidos", command=lambda: (
            sounds.ensure(APP_DIR), actions.run_action(A("abrir", sounds.folder(APP_DIR))))).pack(side="left", padx=4)

        # título simple para botones / perillas
        self.name_frame = tk.Frame(f, bg=PANEL)
        tk.Label(self.name_frame, text="Nombre", bg=PANEL, fg=MUTED).pack(anchor="w")
        self.name_var = tk.StringVar()
        ttk.Entry(self.name_frame, textvariable=self.name_var, width=24).pack(anchor="w", pady=2)
        self.name_var.trace_add("write", lambda *_: self._changed())

        # acciones
        self.acts = tk.Frame(f, bg=PANEL)
        self.acts.grid(row=1, column=2, sticky="nw")
        self.ae = {
            "action": ActionEditor(self.acts, "Al pulsar", self._changed),
            "long_action": ActionEditor(self.acts, "Al mantener pulsado (0,6 s)", self._changed),
            "left": ActionEditor(self.acts, "Girar a la izquierda", self._changed),
            "right": ActionEditor(self.acts, "Girar a la derecha", self._changed),
            "press": ActionEditor(self.acts, "Pulsar la perilla", self._changed),
        }
        tools = tk.Frame(f, bg=PANEL)
        tools.grid(row=2, column=1, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(tools, text="▶ Probar", command=self._test).pack(side="left")
        ttk.Button(tools, text="Copiar", command=self.copy_sel).pack(side="left", padx=4)
        ttk.Button(tools, text="Pegar", command=self.paste_sel).pack(side="left")
        ttk.Button(tools, text="Vaciar", command=self.clear_sel).pack(side="left", padx=4)
        self.saved_lbl = tk.Label(tools, text="", bg=PANEL, fg=MUTED, font=("Segoe UI", 8))
        self.saved_lbl.pack(side="left", padx=10)
        f.columnconfigure(3, weight=1)

    # ------------------------------------------------------------- biblioteca
    def fill_library(self):
        self.tree.delete(*self.tree.get_children())
        q = self.search.get().strip().lower()
        cats: dict = {}
        for t, (lbl, cat, _, desc) in TYPES.items():
            if t == "ninguna" or (q and q not in (lbl + cat + desc).lower()):
                continue
            cats.setdefault(cat, []).append((t, lbl))
        for pid, (lbl, _) in DIALS.items():
            if not q or q in (lbl + "perilla").lower():
                cats.setdefault("Perillas", []).append((pid, lbl))
        icons = {"Spotify": "🎵", "Sistema": "🖥", "Navegación": "📁", "Perillas": "🎛"}
        for cat in ("Spotify", "Perillas", "Sistema", "Navegación"):
            if cat not in cats:
                continue
            node = self.tree.insert("", "end", text=f"{icons[cat]}  {cat.upper()}", open=True, tags=("cat",))
            for iid, lbl in cats[cat]:
                self.tree.insert(node, "end", iid=iid, text="     " + lbl, tags=("sp",))

    def _lib_press(self, e):
        iid = self.tree.identify_row(e.y)
        self.drag = {"src": "lib", "id": iid, "x": e.x_root, "y": e.y_root, "moved": False} \
            if iid in TYPES or iid in DIALS else None

    def _lib_double(self, e):
        iid = self.tree.identify_row(e.y)
        if iid in TYPES or iid in DIALS:
            self.assign(iid, self.selected)

    # ------------------------------------------------------- arrastrar y soltar
    def _drag_motion(self, e):
        if not self.drag:
            return
        if not self.drag["moved"] and abs(e.x_root - self.drag["x"]) + abs(e.y_root - self.drag["y"]) < 8:
            return
        self.drag["moved"] = True
        if self.ghost is None:
            self.ghost = tk.Toplevel(self.root)
            self.ghost.overrideredirect(True)
            self.ghost.attributes("-alpha", 0.85)
            if self.drag["src"] == "lib":
                txt = (TYPES.get(self.drag["id"]) or DIALS.get(self.drag["id"]))[0]
            else:
                txt = "Mover / intercambiar"
            tk.Label(self.ghost, text="  " + txt + "  ", bg=ACCENT, fg=ACCENT_FG,
                     font=("Segoe UI", 9, "bold"), pady=4).pack()
        self.ghost.geometry(f"+{e.x_root + 14}+{e.y_root + 10}")
        self._hover(self._target_at(e.x_root, e.y_root))

    def _drag_release(self, e):
        d, self.drag = self.drag, None
        if self.ghost:
            self.ghost.destroy()
            self.ghost = None
        self._hover(None)
        if not d or not d["moved"]:
            return
        target = self._target_at(e.x_root, e.y_root)
        if not target:
            return
        if d["src"] == "lib":
            self.assign(d["id"], target)
        elif d["src"] == "cv" and target != d["ctl"]:
            self.swap(d["ctl"], target)

    def _target_at(self, xr, yr):
        w = self.root.winfo_containing(xr, yr)
        if w is not self.cv:
            return None
        x, y = xr - self.cv.winfo_rootx(), yr - self.cv.winfo_rooty()
        for it in reversed(self.cv.find_overlapping(x, y, x, y)):
            for tag in self.cv.gettags(it):
                if tag.startswith("ctl:"):
                    _, kind, i = tag.split(":")
                    return (kind, int(i))
        return None

    def _hover(self, target):
        self.cv.delete("hover")
        if target and target in self.boxes:
            x0, y0, x1, y1 = self.boxes[target]
            self.cv.create_rectangle(x0 - 4, y0 - 4, x1 + 4, y1 + 4, outline=GREEN, width=3,
                                     dash=(6, 3), tags="hover")

    # --------------------------------------------------------- asignar acciones
    def assign(self, item_id: str, target):
        kind, i = target
        if item_id in DIALS:
            if kind != "knob":
                self.log("Los preajustes de perilla se sueltan sobre una perilla.")
                return
            self.cfg["knobs"][i] = dial(item_id)
        else:
            a = A(item_id, self._default_value(item_id))
            it = self.item(target)
            if kind == "knob":
                it["press"] = a
            else:
                it["action"] = a
                if kind == "key":
                    it["title"] = "" if item_id.startswith("sp_") else TYPES[item_id][0]
                    it["icon"] = ""
                else:
                    it["title"] = TYPES[item_id][0]
        self.selected = target
        self.after_edit(all_keys=False, which=target)
        self.select(target)

    def _default_value(self, t):
        need = TYPES[t][2]
        if need == "media":
            return "play_pause"
        if need == "page":
            return next((p for p in self.cfg["pages"] if p != self.cfg["current_page"]), "")
        return ""

    def swap(self, a, b):
        if a[0] != b[0]:
            self.log("Solo se pueden intercambiar controles del mismo tipo.")
            return
        ia, ib = self.item(a), self.item(b)
        self.set_item(a, ib)
        self.set_item(b, ia)
        self.selected = b
        self.after_edit(all_keys=True)
        self.select(b)

    def set_item(self, sel, value):
        kind, i = sel
        if kind == "key":
            self.page["keys"][i] = value
        elif kind == "button":
            self.page["buttons"][i] = value
        else:
            self.cfg["knobs"][i] = value

    # -------------------------------------------------------------- dispositivo
    def redraw_device(self):
        cv = self.cv
        cv.delete("all")
        W = max(cv.winfo_width(), 560)
        H = max(cv.winfo_height(), 430)
        gw = 3 * KEY_PX + 2 * GAP
        bw, bh = gw + 70, 470
        sc = min(1.0, (H - 10) / bh)
        x0 = (W - bw) / 2
        y0 = max(4, (H - bh * sc) / 2)
        self.boxes = {}
        # cuerpo
        r = 26
        x1, y1 = x0 + bw, y0 + bh * sc
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
               x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        cv.create_polygon(pts, smooth=True, fill="#0d0d10", outline="#2c2c33", width=2)
        cv.create_text(x0 + bw / 2, y1 - 14, text="STREAM DOCK  N3E", fill="#45454f",
                       font=("Segoe UI", 8, "bold"))
        gx = x0 + 35
        # perillas
        ky = y0 + 52
        for i in range(dock.ENCODER_COUNT):
            cx = gx + i * (KEY_PX + GAP) + KEY_PX / 2
            rr = 30
            tag = f"ctl:knob:{i}"
            sel = self.selected == ("knob", i)
            cv.create_oval(cx - rr, ky - rr, cx + rr, ky + rr, fill="#24242a",
                           outline=ACCENT if sel else "#3a3a44", width=3 if sel else 2, tags=(tag, f"knob{i}"))
            cv.create_oval(cx - rr + 9, ky - rr + 9, cx + rr - 9, ky + rr - 9, fill="#2e2e36", outline="", tags=tag)
            cv.create_line(cx, ky - rr + 11, cx, ky - rr + 20, fill=FG, width=3, tags=tag)
            name = self.cfg["knobs"][i].get("title") or f"Perilla {i + 1}"
            cv.create_text(cx, ky + rr + 12, text=name, fill=MUTED, font=("Segoe UI", 8), tags=tag)
            self.boxes[("knob", i)] = (cx - rr, ky - rr, cx + rr, ky + rr)
        # teclas
        top = ky + 30 + 34
        for i in range(dock.KEY_COUNT):
            x = gx + (i % 3) * (KEY_PX + GAP)
            y = top + (i // 3) * (KEY_PX + GAP)
            tag = f"ctl:key:{i}"
            sel = self.selected == ("key", i)
            cv.create_rectangle(x - 3, y - 3, x + KEY_PX + 3, y + KEY_PX + 3,
                                outline=ACCENT if sel else "#2b2b33", width=3 if sel else 1,
                                tags=(tag, f"keybox{i}"))
            cv.create_image(x, y, anchor="nw", tags=(tag, f"keyimg{i}"))
            self.boxes[("key", i)] = (x, y, x + KEY_PX, y + KEY_PX)
        # botones
        by = top + 2 * (KEY_PX + GAP) + 8
        for i in range(dock.BUTTON_COUNT):
            x = gx + i * (KEY_PX + GAP) + 10
            tag = f"ctl:button:{i}"
            sel = self.selected == ("button", i)
            bt = self.page["buttons"][i]
            cv.create_rectangle(x, by, x + KEY_PX - 20, by + 30, fill="#24242a",
                                outline=ACCENT if sel else "#3a3a44", width=3 if sel else 1,
                                tags=(tag, f"btn{i}"))
            cv.create_text(x + (KEY_PX - 20) / 2, by + 15, text=bt.get("title") or "·", fill=FG,
                           font=("Segoe UI", 8), width=KEY_PX - 26, tags=tag)
            self.boxes[("button", i)] = (x, by, x + KEY_PX - 20, by + 30)
        self.sigs.clear()
        self.update_keys(force=True)
        if hasattr(self, "backdrop"):
            self.backdrop.attach(self.cv)

    def update_keys(self, force=False, only=None):
        """Redibuja la vista previa de las teclas y marca para enviar al N3E."""
        st = self.sp.state if hasattr(self, "sp") else None
        changed = []
        visible = self.window_visible()
        for i, key in enumerate(self.page["keys"]):
            if only is not None and i not in only:
                continue
            sig = render.key_signature(key, st)
            if not force and only is None and (sig is None or self.sigs.get(i) == sig):
                continue
            self.sigs[i] = sig
            changed.append(i)
            if not visible:      # la ventana está junto al reloj: solo se actualiza el N3E
                self._preview_stale = True
                continue
            pil = self.key_image(i, key, st, KEY_PX)
            im = self.tk_imgs.get(i)
            if im is not None and (im.width(), im.height()) == pil.size:
                im.paste(pil)    # reutiliza la imagen de Tk
            else:
                im = ImageTk.PhotoImage(pil)
                self.tk_imgs[i] = im
            self.cv.itemconfig(f"keyimg{i}", image=im)
        if changed:
            self.mark_dirty(changed)

    def flash(self, sel):
        kind, i = sel
        tag = {"key": f"keybox{i}", "button": f"btn{i}", "knob": f"knob{i}"}[kind]
        self.cv.itemconfig(tag, outline=GREEN, width=4)
        self.root.after(160, self._restore_outline)

    def _restore_outline(self):
        for (kind, i) in self.boxes:
            tag = {"key": f"keybox{i}", "button": f"btn{i}", "knob": f"knob{i}"}[kind]
            sel = self.selected == (kind, i)
            base = "#2b2b33" if kind == "key" else "#3a3a44"
            self.cv.itemconfig(tag, outline=ACCENT if sel else base, width=3 if sel else (1 if kind != "knob" else 2))

    def _cv_press(self, e):
        t = self._target_at(e.x_root, e.y_root)
        if t:
            self.select(t)
            self.drag = {"src": "cv", "ctl": t, "x": e.x_root, "y": e.y_root, "moved": False}

    def _cv_menu(self, e):
        t = self._target_at(e.x_root, e.y_root)
        if not t:
            return
        self.select(t)
        m = tk.Menu(self.root, tearoff=0, bg=PANEL2, fg=FG, activebackground=ACCENT)
        m.add_command(label="Copiar", command=self.copy_sel)
        m.add_command(label="Pegar", command=self.paste_sel, state="normal" if self.clipboard else "disabled")
        m.add_command(label="Vaciar", command=self.clear_sel)
        m.tk_popup(e.x_root, e.y_root)

    # -------------------------------------------------------------- inspector
    @property
    def page(self) -> dict:
        return self.cfg["pages"][self.cfg["current_page"]]

    def item(self, sel=None) -> dict:
        kind, i = sel or self.selected
        if kind == "key":
            return self.page["keys"][i]
        if kind == "button":
            return self.page["buttons"][i]
        return self.cfg["knobs"][i]

    def select(self, sel):
        self.selected = sel
        self.loading = True
        kind, i = sel
        it = self.item()
        names = {"key": f"Tecla {i + 1}", "button": f"Botón {i + 1}", "knob": f"Perilla {i + 1}"}
        sub = "  ·  igual en todas las páginas" if kind == "knob" else f"  ·  página «{self.cfg['current_page']}»"
        self.insp_title.config(text=names[kind] + sub)
        for ae in self.ae.values():
            ae.grid_forget()
        if kind == "key":
            self.name_frame.grid_forget()
            self.look.grid(row=1, column=1, sticky="nw", padx=(0, 18))
            self.title_txt.delete("1.0", "end")
            self.title_txt.insert("1.0", it.get("title", ""))
            self.pos_cb.current({"top": 0, "middle": 1}.get(it.get("title_pos"), 2))
            self.bg_btn.config(bg=it.get("color", render.DARK), fg=it.get("text_color", "#fff"),
                               activebackground=it.get("color", render.DARK))
            self.fg_btn.config(bg=it.get("text_color", "#fff"), fg=it.get("color", render.DARK),
                               activebackground=it.get("text_color", "#fff"))
        else:
            self.look.grid_forget()
            self.name_frame.grid(row=1, column=1, sticky="nw", padx=(0, 18))
            self.name_var.set(it.get("title", ""))
        fields = ("left", "right", "press") if kind == "knob" else ("action", "long_action")
        for row, fld in enumerate(fields):
            self.ae[fld].set(it.get(fld), self.cfg["pages"].keys())
            self.ae[fld].grid(row=row, column=0, sticky="we", pady=(0, 8))
        self._load_now_style(it)
        self._load_react(it)
        self._preview()
        self._restore_outline()
        self.loading = False

    NOW_DEFAULTS = {"now_style": "portada", "pause_style": "nada", "transition": "fundido", "cover_crop": "auto"}

    def _is_now_key(self, it=None) -> bool:
        it = it or self.item()
        return self.selected[0] == "key" and (it.get("action") or {}).get("type") == "sp_now"

    def _load_now_style(self, it):
        if not self._is_now_key(it):
            self.now_frame.grid_forget()
            return
        self.now_frame.grid(row=1, column=3, sticky="nw", padx=(18, 0))
        for fld, (cb, keys) in self.now_cbs.items():
            v = it.get(fld, self.NOW_DEFAULTS[fld])
            cb.current(keys.index(v) if v in keys else 0)
        self.crop_pct.set(int(it.get("cover_crop_pct", 15)))
        self._crop_row_visibility(it)

    def _crop_row_visibility(self, it):
        if it.get("cover_crop") == "manual":
            self.crop_row.grid(row=5, column=0, columnspan=3, sticky="w", pady=2)
            self.crop_lbl.config(text=f"{int(it.get('cover_crop_pct', 15))} %")
        else:
            self.crop_row.grid_forget()

    def open_style_gallery(self):
        if not self._is_now_key():
            return
        sel = self.selected

        def chosen(style):
            if self.selected == sel:
                self.select(sel)
            self.after_edit(which=sel)
            self.log(f"Estilo de portada: {render.NOW_STYLES[style][0]}")
        self.open_once("estilos", lambda: gallery.StyleGallery(self.root, self.item(), lambda: self.sp.state, chosen),
                       same=self.item())

    def window_visible(self) -> bool:
        try:
            return self.root.state() not in ("withdrawn", "iconic")
        except Exception:
            return True

    def _on_map(self, e=None):
        """Al volver a mostrar la ventana, pone al día la vista previa."""
        if getattr(self, "_preview_stale", False):
            self._preview_stale = False
            self.update_keys(force=True)
            self._preview()

    # ---------------------------------------------------------------- reacción
    REACT_DEFAULTS = {"press_fx": reactions.DEFAULT_PRESS, "press_sound": "ninguno", "music_fx": "ninguno"}

    def _load_react(self, it):
        kind = self.selected[0]
        if kind == "knob" or (kind == "key" and reactions.excluded(it)):
            self.react_frame.grid_forget()
            return
        self.react_frame.grid(row=1, column=3, sticky="nw", padx=(18, 0))
        snd = sounds.available(APP_DIR)
        cb, _ = self.react_cbs["press_sound"]
        cb["values"] = list(snd.values())
        self.react_cbs["press_sound"] = (cb, list(snd))
        for fld, (l, cb, r) in self.react_rows.items():
            show = kind == "key" or fld == "press_sound"  # los botones no tienen pantalla
            if show:
                l.grid(row=r, column=0, sticky="w", pady=2)
                cb.grid(row=r, column=1, sticky="w", padx=6, pady=2)
            else:
                l.grid_forget()
                cb.grid_forget()
            keys = self.react_cbs[fld][1]
            default = self.REACT_DEFAULTS[fld] if kind == "key" else "ninguno"
            v = it.get(fld, default)
            cb.current(keys.index(v) if v in keys else 0)

    def _preview_sound(self):
        cb, keys = self.react_cbs["press_sound"]
        n = cb.current()
        if n > 0:
            sounds.play(APP_DIR, keys[n])

    def _react_to_all(self):
        it = self.item()
        vals = {f: it.get(f, self.REACT_DEFAULTS[f]) for f in self.REACT_DEFAULTS}
        n = 0
        for page in self.cfg["pages"].values():
            for key in page["keys"]:
                if not reactions.excluded(key):
                    key.update(vals)
                    n += 1
            for b in page["buttons"]:
                b["press_sound"] = vals["press_sound"]
        self.log(f"Reacción aplicada a {n} teclas y a los botones de todas las páginas")
        self._update_level_need()
        self.after_edit(all_keys=True)

    def _update_level_need(self):
        """El medidor de sonido solo funciona si alguna tecla de esta página lo usa."""
        need = any(k.get("music_fx", "ninguno") != "ninguno" and not reactions.excluded(k)
                   for k in self.page["keys"])
        self.sp.want_level(need)

    def react_trigger(self, kind, i):
        """Efecto + sonido al pulsar (en el N3E o con «Probar»)."""
        it = self.item((kind, i))
        snd = it.get("press_sound", "ninguno")
        if snd != "ninguno":
            try:
                sounds.play(APP_DIR, snd)
            except Exception as e:
                self.log(f"No se pudo reproducir el sonido: {e}")
        if kind == "key" and not reactions.excluded(it) and it.get("press_fx", reactions.DEFAULT_PRESS) != "ninguno":
            self.press_at[i] = time.time()
            self.update_keys(only=[i])

    def _preview(self):
        kind, i = self.selected
        if not self.window_visible():
            return
        if kind == "key":
            pil = render.render_key(self.item(), self.sp.state if hasattr(self, "sp") else None, 96)
            im = getattr(self.preview, "image", None)
            if im is not None and hasattr(im, "paste") and (im.width(), im.height()) == pil.size:
                im.paste(pil)   # reutiliza la imagen de Tk
            else:
                im = ImageTk.PhotoImage(pil)
                self.preview.image = im
            self.preview.config(image=im, text="", width=96, height=96)
        else:
            self.preview.config(image="", text="🎛" if kind == "knob" else "⏺", fg=MUTED,
                                font=("Segoe UI", 40), width=3, height=1)

    def _changed(self):
        if self.loading:
            return
        kind, i = self.selected
        it = self.item()
        if kind == "key":
            it["title"] = self.title_txt.get("1.0", "end-1c")
            it["title_pos"] = ("top", "middle", "bottom")[max(0, self.pos_cb.current())]
            fields = ("action", "long_action")
        else:
            it["title"] = self.name_var.get()
            fields = ("left", "right", "press") if kind == "knob" else ("action", "long_action")
        for fld in fields:
            it[fld] = self.ae[fld].get()
        if kind == "key":
            if self._is_now_key(it) and self.now_frame.winfo_ismapped():
                for fld, (cb, keys) in self.now_cbs.items():
                    n = cb.current()
                    it[fld] = keys[n] if n >= 0 else self.NOW_DEFAULTS[fld]
                it["cover_crop_pct"] = int(float(self.crop_pct.get()))
                self._crop_row_visibility(it)
            self.loading = True
            self._load_now_style(it)   # aparece/desaparece si cambió la acción
            self.loading = False
        if kind in ("key", "button") and self.react_frame.winfo_ismapped():
            for fld, (cb, keys) in self.react_cbs.items():
                n = cb.current()
                if n >= 0 and (kind == "key" or fld == "press_sound"):  # botones: solo sonido
                    it[fld] = keys[n]
            self.loading = True
            self._load_react(it)
            self.loading = False
        self._update_level_need()
        self.after_edit(which=self.selected)

    def after_edit(self, all_keys=False, which=None):
        """Tras cualquier cambio: refresca vista, dispositivo y guarda."""
        if which and which[0] == "key":
            self._maybe_fetch_playlist(self.item(which))
        if which and which[0] == "key" and not all_keys:
            self.update_keys(only=[which[1]])
        else:
            self.redraw_device()  # botones/perillas muestran su nombre en la maqueta
        self._preview()
        self.schedule_save()

    def _pick_color(self, field):
        it = self.item()
        c = colorchooser.askcolor(it.get(field) or render.DARK, parent=self.root)[1]
        if c:
            it[field] = c
            self.select(self.selected)
            self.after_edit(which=self.selected)

    def _pick_icon(self):
        sel = self.selected

        def chosen(path):
            if self.selected == sel:
                self._set_icon(path)
        self.open_once("iconos", lambda: IconPicker(self, chosen), same=self.item())

    def _set_icon(self, path):
        if self.selected[0] != "key":
            return
        self.item()["icon"] = path
        self.after_edit(which=self.selected)

    def _clear_icon(self):
        self.item()["icon"] = ""
        self.after_edit(which=self.selected)

    def _test(self):
        kind, i = self.selected
        if kind in ("key", "button"):
            self.react_trigger(kind, i)
        self.run(self.item().get("press" if kind == "knob" else "action"))

    def copy_sel(self):
        self.clipboard = (self.selected[0], copy.deepcopy(self.item()))
        self.log("Copiado")

    def paste_sel(self):
        if not self.clipboard:
            return
        kind, data = self.clipboard
        if kind != self.selected[0]:
            self.log("Solo se puede pegar en un control del mismo tipo.")
            return
        self.set_item(self.selected, copy.deepcopy(data))
        self.after_edit(all_keys=True)
        self.select(self.selected)

    def clear_sel(self):
        kind, _ = self.selected
        blank = K("ninguna") if kind == "key" else B() if kind == "button" else \
            {"title": "", "left": A(), "right": A(), "press": A()}
        self.set_item(self.selected, blank)
        self.after_edit(all_keys=True)
        self.select(self.selected)

    # ----------------------------------------------------------------- páginas
    def refresh_pages(self):
        self.page_cb["values"] = list(self.cfg["pages"])
        self.page_cb.set(self.cfg["current_page"])

    def switch_page(self, name):
        if name not in self.cfg["pages"]:
            self.log(f"La página «{name}» no existe")
            return
        self.cfg["current_page"] = name
        self.press_at.clear()
        self._update_level_need()
        self.refresh_pages()
        self.redraw_device()
        self.select(self.selected)
        self.schedule_save()

    def add_page(self):
        name = simpledialog.askstring("Nueva página", "Nombre de la página:", parent=self.root)
        if name and name not in self.cfg["pages"]:
            self.cfg["pages"][name] = blank_page()
            self.switch_page(name)

    def rename_page(self):
        old = self.cfg["current_page"]
        new = simpledialog.askstring("Renombrar página", "Nuevo nombre:", initialvalue=old, parent=self.root)
        if not new or new == old or new in self.cfg["pages"]:
            return
        self.cfg["pages"] = {(new if k == old else k): v for k, v in self.cfg["pages"].items()}
        for p in self.cfg["pages"].values():
            for it in p["keys"] + p["buttons"]:
                for fld in ("action", "long_action"):
                    a = it.get(fld) or {}
                    if a.get("type") == "pagina" and a.get("value") == old:
                        a["value"] = new
        self.cfg["current_page"] = new
        self.switch_page(new)

    def delete_page(self):
        if len(self.cfg["pages"]) <= 1:
            messagebox.showinfo(APP_NAME, "Debe quedar al menos una página.", parent=self.root)
            return
        name = self.cfg["current_page"]
        if messagebox.askyesno(APP_NAME, f"¿Eliminar la página «{name}»?", parent=self.root):
            del self.cfg["pages"][name]
            self.switch_page(next(iter(self.cfg["pages"])))

    # ------------------------------------------------------- escritura al N3E
    def mark_dirty(self, keys):
        with self.dirty_cv:
            self.dirty.update(keys)
            self.dirty_cv.notify()

    def _writer(self):
        while True:
            with self.dirty_cv:
                while not self.dirty:
                    self.dirty_cv.wait()
                keys, self.dirty = sorted(self.dirty), set()
            dev = self.mgr.device
            if not dev:
                continue
            try:
                page = self.page
                st = self.sp.state
                sent = False
                for i in keys:
                    sent |= dev.set_key_image(i, self.key_image(i, page["keys"][i], st, 128), flush=False)
                if sent:
                    dev.flush()
            except Exception as e:
                self.q.put(("log", f"No se pudo actualizar la pantalla: {e}"))

    def _on_connect(self, dev):
        self.apply_screen(dev)
        dev.set_brightness(self.cfg["brightness"])
        self.mark_dirty(range(dock.KEY_COUNT))

    def apply_screen(self, dev=None, clear=None):
        """Tamaño/giro de las imágenes y borrado del fondo que dejó el software oficial."""
        dev = dev or self.mgr.device
        if not dev:
            return
        sc = self.cfg.get("screen") or {}
        size = int(sc.get("size") or 0) or None
        rot = int(sc.get("rotation", -1))
        dev.configure_screen(size, None if rot < 0 else rot, (sc.get("ox", 0), sc.get("oy", 0)))
        if sc.get("clear_bg", True) if clear is None else clear:
            try:
                dev.clear(0xFF)   # pantallas en negro: desaparece el fondo guardado
            except Exception as e:
                self.q.put(("log", f"No se pudo borrar el fondo: {e}"))

    def show_test_pattern(self, seconds=40, quiet=False):
        self.pattern_until = time.time() + seconds
        self.update_keys(force=True)
        if not quiet:
            self.log("Patrón de prueba: el marco blanco debe tocar los 4 bordes de cada tecla. "
                     "Toca el N3E para terminar.")

    def end_test_pattern(self):
        if getattr(self, "pattern_until", 0):
            self.pattern_until = 0
            self.update_keys(force=True)

    def _brightness(self):
        if self.saver_on:
            self.wake_saver()
        self.last_input = time.time()
        self.cfg["brightness"] = int(self.bright.get())
        dev = self.mgr.device
        if dev:
            try:
                dev.set_brightness(self.cfg["brightness"])
            except Exception:
                pass
        self.schedule_save()

    # ----------------------------------------------------------------- eventos
    def _pump(self):
        try:
            for _ in range(200):
                kind, payload = self.q.get_nowait()
                if kind == "dock":
                    self._dock_event(payload)
                elif kind == "spotify":
                    self._spotify_event(payload)
                elif kind == "update":
                    self._offer_update(payload)
                elif kind == "tray":
                    self._tray_cmd(payload)
                elif kind == "pl_info":
                    self._playlist_info(*payload)
                elif kind == "log":
                    self.log(payload)
        except queue.Empty:
            pass
        self.root.after(30, self._pump)

    ANIM_MS = 125  # ~8 cuadros por segundo: fluido en el N3E sin saturar el USB

    def _animate(self):
        try:
            st = self.sp.state
            now = time.time()
            playing = bool(st.running and st.playing)
            keys = [] if self.saver_on or getattr(self, "pattern_until", 0) else \
                [i for i, k in enumerate(self.page["keys"])
                 if render.is_animated(k, st, now) or reactions.is_active(k, self.press_at.get(i), playing, now)]
            if keys:
                self.update_keys(only=keys)
                if self.selected[0] == "key" and self.selected[1] in keys:
                    self._preview()
        except Exception:
            pass
        self.root.after(self.ANIM_MS, self._animate)

    def _tick(self):
        if getattr(self, "pattern_until", 0) and time.time() >= self.pattern_until:
            self.end_test_pattern()
        self._check_saver()
        st = self.sp.state
        if st.running and st.playing:
            self.update_keys()  # avanza la barra de progreso
        self.root.after(1000, self._tick)

    def _spotify_event(self, st):
        if st.cover is not None and hasattr(self, "backdrop"):
            self.backdrop.set_cover(render.cover_for(st, {}))
        if self.saver_on and self.cfg["saver"].get("mode") == "portada":
            self.root.after(50, lambda: self.update_keys(force=True))
        self.tray.set_tooltip(f"Stream Dock Lite — {st.title} · {st.artist}" if st.running and st.title
                              else "Stream Dock Lite")
        if st.cover is not None:
            render.note_cover(st.cover)
        if st.running:
            icon = "▶" if st.playing else "⏸"
            text = f"{icon}  {st.title} — {st.artist}" if st.title else "Spotify abierto"
            self.sp_badge.config(text=text[:60], fg=GREEN)
        else:
            self.sp_badge.config(text="Spotify cerrado", fg=MUTED)
        self.update_keys()
        if self.selected[0] == "key" and render.is_live(self.item()):
            self._preview()

    def _dock_event(self, ev: dock.DockEvent):
        if ev.kind == "status":
            ok = ev.text.startswith("Conectado")
            self.dev_badge.config(text=("● N3E conectado" if ok else "● N3E desconectado"),
                                  fg=GREEN if ok else DANGER)
            self.log(ev.text)
            return
        if ev.kind == "error":
            self.log("⚠ " + ev.text)
            return
        if ev.kind == "raw":
            self.log(f"Entrada no reconocida {ev.text} · {ev.raw.hex(' ')}")
            return
        if ev.kind in ("key", "button", "knob_turn", "knob_press"):
            self.last_input = time.time()
            if getattr(self, "pattern_until", 0):
                if ev.value == 1 or ev.kind == "knob_turn":
                    self.end_test_pattern()
                return
            if self.saver_on:
                if ev.value == 1 or ev.kind == "knob_turn":
                    self.wake_saver()     # el toque solo despierta, no ejecuta nada
                return
        if ev.kind in ("key", "button"):
            sel = (ev.kind, ev.index)
            it = self.item(sel)
            has_long = (it.get("long_action") or {}).get("type", "ninguna") != "ninguna"
            both = bool(self.mgr.device and self.mgr.device.both_states)
            if ev.value == 1:
                self.flash(sel)
                self.react_trigger(*sel)
                self.press_t[sel] = time.time()
                if not (has_long and both):
                    self.run(it.get("action"))
            else:
                t0 = self.press_t.pop(sel, None)
                if has_long and both and t0 is not None:
                    self.run(it.get("long_action") if time.time() - t0 >= LONG_PRESS_S else it.get("action"))
        elif ev.kind == "knob_turn":
            self.flash(("knob", ev.index))
            self.run(self.cfg["knobs"][ev.index].get("right" if ev.value > 0 else "left"), quiet=True)
        elif ev.kind == "knob_press" and ev.value == 1:
            self.flash(("knob", ev.index))
            self.run(self.cfg["knobs"][ev.index].get("press"))

    # -------------------------------------------------------- ejecutar acciones
    def run(self, a, quiet=False):
        t = (a or {}).get("type", "ninguna")
        if t == "ninguna":
            return
        if t == "pagina":
            self.switch_page(a.get("value", ""))
            return
        if t == "sp_playlist":
            link = a.get("value", "")
            if not link:
                self.log("Pega un enlace de Spotify en esta tecla (Compartir → Copiar enlace).")
                return

            def play():
                try:
                    self.q.put(("log", playlists.play(link, self.sp.web)))
                except Exception as e:
                    self.q.put(("log", f"No se pudo reproducir: {e}"))
            threading.Thread(target=play, daemon=True).start()
            return
        if t.startswith("sp_"):
            self._run_spotify(t)
            return

        def work():
            try:
                msg = actions.run_action(a)
                if msg and not quiet:
                    self.q.put(("log", msg))
            except Exception as e:
                self.q.put(("log", f"La acción falló: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def _run_spotify(self, t):
        sp = self.sp
        if not sp.available and t not in ("sp_open",):
            # sin SMTC: usamos las teclas multimedia como respaldo
            fallback = {"sp_play": "play_pause", "sp_now": "play_pause", "sp_progress": "play_pause",
                        "sp_next": "next", "sp_prev": "prev"}
            if t in fallback:
                self.run(A("multimedia", fallback[t]), quiet=True)
                return
        if t in ("sp_play", "sp_now", "sp_progress"):
            if t == "sp_now" and not sp.state.running:
                sp.open()
            else:
                sp.play_pause()
        elif t == "sp_next":
            sp.next()
        elif t == "sp_prev":
            sp.previous()
        elif t == "sp_shuffle":
            sp.toggle_shuffle()
        elif t == "sp_repeat":
            sp.cycle_repeat()
        elif t == "sp_open":
            sp.open()
        elif t in ("sp_volume", "sp_mute"):
            sp.toggle_mute() or self.log("Volumen por app no disponible: reinstala Stream Dock Lite")
        elif t == "sp_vol_up":
            sp.volume_step(VOL_STEP)
        elif t == "sp_vol_down":
            sp.volume_step(-VOL_STEP)
        elif t == "sp_like":
            def work():
                try:
                    self.q.put(("log", sp.toggle_like()))
                except Exception as e:
                    self.q.put(("log", f"Me gusta falló: {e}"))
            threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ ajustes
    def open_settings(self):
        self.open_once("ajustes", lambda: SettingsDialog(self))

    def open_once(self, name, factory, same=None):
        """Abre una ventana solo una vez: si ya está abierta, la trae al frente
        en vez de crear otra. `same` = dato que debe coincidir para reutilizarla
        (p. ej. la tecla de la galería de estilos); si cambia, se reabre."""
        wins = self.__dict__.setdefault("_wins", {})
        prev = wins.get(name)
        if prev is not None:
            top, tag = prev
            try:
                if top.winfo_exists():
                    if same is None or tag is same:
                        top.deiconify()
                        top.lift()
                        top.focus_force()
                        return None
                    top.destroy()
            except tk.TclError:
                pass
        obj = factory()
        top = getattr(obj, "w", obj)
        wins[name] = (top, same)
        theme.titlebar(top, MODE == "dark")
        return obj

    def open_appearance(self):
        self.open_once("apariencia", lambda: AppearanceDialog(self))

    def _startup_path(self):
        return os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup",
                            "StreamDockLite.cmd")

    def set_startup(self, on: bool):
        p = self._startup_path()
        if on:
            launcher = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "StreamDockLite.exe")
            with open(p, "w", encoding="utf-8") as f:
                if os.path.exists(launcher):   # instalado con StreamDockLite-Setup.exe
                    f.write(f'@start "" "{launcher}" --min\r\n')
                else:
                    exe = sys.executable.replace("python.exe", "pythonw.exe")
                    f.write(f'@start "" "{exe}" "{os.path.abspath(__file__)}" --min\r\n')
        elif os.path.exists(p):
            os.remove(p)

    # --------------------------------------------------------- registro/guardar
    def log(self, text):
        line = time.strftime("%H:%M:%S  ") + text
        self.logs.append(line)
        del self.logs[:-500]
        self.status.config(text=text)
        if getattr(self, "log_win", None) and self.log_win.winfo_exists():
            self.log_txt.config(state="normal")
            self.log_txt.insert("end", line + "\n")
            self.log_txt.see("end")
            self.log_txt.config(state="disabled")

    def show_log(self):
        if getattr(self, "log_win", None) and self.log_win.winfo_exists():
            self.log_win.deiconify()
            self.log_win.lift()
            self.log_win.focus_force()
            return
        self.log_win = tk.Toplevel(self.root, bg=BG)
        theme.titlebar(self.log_win, MODE == "dark")
        self.log_win.title("Registro")
        self.log_win.geometry("700x360")
        self.log_txt = tk.Text(self.log_win, bg=PANEL, fg=FG, font=("Consolas", 9), relief="flat")
        self.log_txt.pack(fill="both", expand=True, padx=8, pady=8)
        self.log_txt.insert("end", "\n".join(self.logs) + "\n")
        self.log_txt.see("end")
        self.log_txt.config(state="disabled")

    def schedule_save(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self.saved_lbl.config(text="Guardando…")
        self._save_job = self.root.after(600, self._save)

    def _save(self):
        try:
            save_config(self.cfg)
            self.saved_lbl.config(text="✓ Guardado")
        except Exception as e:
            self.saved_lbl.config(text="Error al guardar")
            self.log(f"⚠ No se pudo guardar: {e}")

    # ------------------------------------------------ conexión con Claude
    def _update_link_button(self):
        on = self.cfg.get("claude_link", False)
        self.link_btn.config(text=("🔗 Claude: conectado" if on else "🔗 Claude: desconectado"),
                             bg=LINK_ON if on else PANEL2, fg=GREEN if on else MUTED,
                             activebackground=LINE, activeforeground=FG)

    def toggle_link(self):
        if self.cfg.get("claude_link"):
            self.cfg["claude_link"] = False
            self.log("Conexión con Claude desactivada: no se aceptarán actualizaciones.")
        else:
            ok = messagebox.askyesno(
                "Conexión con Claude",
                "Al activarla, Claude podrá ENVIARTE actualizaciones de la app.\n\n"
                "• Nunca se instala nada sin que pulses «Sí».\n"
                "• Antes de cada actualización se guarda una copia para volver atrás.\n"
                "• Claude solo puede dejar archivos si además le das acceso a la carpeta de "
                "conexión en la app de escritorio de Claude («+» → «Add folder»).\n"
                "• Puedes desactivarla cuando quieras con este mismo botón.\n\n"
                "¿Activar la conexión?", parent=self.root)
            if not ok:
                return
            updater.ensure_inbox()
            self.cfg["claude_link"] = True
            self.log(f"Conexión con Claude activada. Carpeta: {updater.INBOX}")
            if messagebox.askyesno("Conexión con Claude",
                                   "¿Abrir la carpeta de conexión para dársela a Claude?\n\n"
                                   "En la app de escritorio de Claude: «+» → «Add folder» → elige esta carpeta.",
                                   parent=self.root):
                actions.run_action(A("abrir", updater.INBOX))
        self._update_link_button()
        self.schedule_save()

    def _watch_inbox(self):
        while True:
            time.sleep(4)
            if not self.cfg.get("claude_link") or self._asking_update:
                continue
            try:
                for p in updater.pending():
                    if p not in self._seen_updates:
                        self._seen_updates.add(p)
                        self.q.put(("update", p))
                        break  # de una en una
            except Exception:
                pass

    def _offer_update(self, path, from_claude=True):
        self._asking_update = True
        try:
            try:
                info = updater.inspect(path)
            except Exception as e:
                self.log(f"Actualización rechazada (no válida): {e}")
                if from_claude:
                    updater.archive(path, False)
                return
            cur = updater.current_version()
            older = updater.vtuple(info.version) <= updater.vtuple(cur)
            msg = (f"{'Claude te envió' if from_claude else 'Archivo'}: versión {info.version}"
                   f"  (tienes la {cur})\n\n{info.notes or 'Sin notas.'}\n\n"
                   + ("⚠ No es más nueva que la que tienes.\n" if older else "")
                   + ("Se instalarán componentes nuevos (tarda un poco).\n" if info.needs_deps else "")
                   + f"Huella SHA-256: {info.sha256[:16]}…\n\n¿Instalar ahora? La app se reiniciará.")
            if not messagebox.askyesno("Actualización disponible", msg, parent=self.root):
                self.log(f"Actualización {info.version} rechazada por ti.")
                if from_claude:
                    updater.archive(path, False)
                return
            self.log(f"Instalando la versión {info.version}…")
            self.root.update()
            try:
                updater.apply(info, log=self.log)
            except Exception as e:
                messagebox.showerror("Actualización", f"No se pudo instalar: {e}\n"
                                     "Se dejó la versión anterior.", parent=self.root)
                return
            if from_claude:
                updater.archive(path, True)
            messagebox.showinfo("Actualización", f"Listo: versión {info.version} instalada.\n"
                                "La app se reiniciará.", parent=self.root)
            updater.restart()
            self.quit()
        finally:
            self._asking_update = False

    def update_from_file(self):
        p = filedialog.askopenfilename(parent=self.root, title="Paquete de actualización",
                                       filetypes=[("Actualización", "*.zip")])
        if p:
            self._offer_update(p, from_claude=False)

    def rollback(self):
        bks = updater.list_backups()
        if not bks:
            messagebox.showinfo("Versión anterior", "Todavía no hay copias guardadas.", parent=self.root)
            return
        last = bks[0]
        if messagebox.askyesno("Versión anterior",
                               f"¿Volver a la copia «{last}»? La app se reiniciará.", parent=self.root):
            try:
                updater.restore(last)
            except Exception as e:
                messagebox.showerror("Versión anterior", str(e), parent=self.root)
                return
            updater.restart()
            self.quit()

    # ------------------------------------------------------------ bandeja (1)
    def on_close(self):
        if self.cfg.get("close_to_tray", True) and self.tray.available:
            self.root.withdraw()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray.notify("Sigo funcionando aquí, junto al reloj. Clic derecho en el icono para salir.")
        else:
            self.quit()

    def show_window(self):
        self.root.deiconify()
        self.root.after(50, self._on_map)
        self.root.state("normal")
        self.root.lift()
        try:
            self.root.focus_force()
        except Exception:
            pass

    def _tray_cmd(self, cmd):
        if cmd == "show":
            self.show_window()
        elif cmd == "play":
            self._run_spotify("sp_play")
        elif cmd == "next":
            self._run_spotify("sp_next")
        elif cmd == "prev":
            self._run_spotify("sp_prev")
        elif cmd == "quit":
            self.quit()

    # ------------------------------------------------------------ playlists (2)
    def _maybe_fetch_playlist(self, key):
        a = key.get("action") or {}
        if a.get("type") != "sp_playlist":
            return
        link = (a.get("value") or "").strip()
        if not link or (key.get("pl_link") == link and key.get("pl_cover") and os.path.exists(key["pl_cover"])):
            return
        if not playlists.parse(link):
            key["pl_cover"], key["pl_name"], key["pl_link"] = "", "Enlace no válido", ""
            return
        if getattr(self, "_fetching", set()) and link in self._fetching:
            return
        self._fetching = getattr(self, "_fetching", set()) | {link}

        def work():
            try:
                info = playlists.fetch_info(link, APP_DIR)
                self.q.put(("pl_info", (link, info, None)))
            except Exception as e:
                self.q.put(("pl_info", (link, None, e)))
        threading.Thread(target=work, daemon=True).start()

    def _playlist_info(self, link, info, err):
        self._fetching = getattr(self, "_fetching", set()) - {link}
        if err:
            self.log(f"No se pudo cargar la portada de la playlist: {err}")
            return
        for page in self.cfg["pages"].values():
            for key in page["keys"]:
                a = key.get("action") or {}
                if a.get("type") == "sp_playlist" and (a.get("value") or "").strip() == link:
                    key.update(pl_cover=info["cover"], pl_name=info["name"], pl_link=link)
        self.log(f"Playlist lista: {info['name']}")
        self.update_keys(force=True)
        self._preview()
        self.schedule_save()

    def _refresh_playlist_covers(self):
        for page in self.cfg["pages"].values():
            for key in page["keys"]:
                self._maybe_fetch_playlist(key)

    # ------------------------------------------------------------ protector de pantalla (8)
    def key_image(self, i, key, st, size):
        if time.time() < getattr(self, "pattern_until", 0):
            dev = self.mgr.device
            label = f"{dev.image_size}px  {dev.offset[0]:+d},{dev.offset[1]:+d}" if dev else ""
            return render.test_pattern(i, label, size)
        if self.saver_on and self.cfg["saver"].get("mode") == "portada" and st and st.running \
                and st.cover is not None:
            return render.saver_tile(render.cover_for(st, {}), i, size)
        img = render.render_key(key, st, size)
        if reactions.excluded(key):
            return img
        now = time.time()
        playing = bool(st and st.running and st.playing)
        return reactions.apply(img, key, self.press_at.get(i), now, ACCENT,
                               level=self.sp.level, beat_age=now - self.sp.beat_t, music_on=playing)

    def _check_saver(self):
        sv = self.cfg.get("saver") or {}
        if self.saver_on or sv.get("mode", "off") == "off" or not self.mgr.device:
            return
        if time.time() - self.last_input >= max(1, int(sv.get("minutes", 5))) * 60:
            self.start_saver()

    def start_saver(self):
        mode = self.cfg["saver"].get("mode", "portada")
        st = self.sp.state
        if mode == "portada" and not (st.running and st.cover is not None):
            mode = "atenuar"  # sin música no hay portada que mostrar
        self.saver_on = True
        dev = self.mgr.device
        try:
            if dev and mode == "atenuar":
                dev.set_brightness(min(10, self.cfg["brightness"]))
            elif dev and mode == "apagar":
                dev.set_brightness(0)
        except Exception:
            pass
        self.update_keys(force=True)
        self.log("Protector de pantalla activado (toca cualquier control para despertar)")

    def wake_saver(self):
        if not self.saver_on:
            return
        self.saver_on = False
        self.last_input = time.time()
        dev = self.mgr.device
        try:
            if dev:
                dev.set_brightness(self.cfg["brightness"])
        except Exception:
            pass
        self.update_keys(force=True)
        self.log("Protector de pantalla desactivado")

    def quit(self):
        try:
            save_config(self.cfg)
        except Exception:
            pass
        self.tray.stop()
        self.backdrop.stop()
        self.sp.stop()
        self.mgr.stop()
        self.root.destroy()


# =============================================================================
# Biblioteca de iconos
# =============================================================================
class IconPicker:
    THUMB = 64
    COLS = 8

    def __init__(self, app: "App", on_pick):
        self.app, self.on_pick = app, on_pick
        self.thumbs: dict = {}
        w = self.w = tk.Toplevel(app.root, bg=PANEL)
        w.title("Biblioteca de iconos")
        w.transient(app.root)
        w.geometry("700x560")
        bar = tk.Frame(w, bg=PANEL, padx=10, pady=8)
        bar.pack(fill="x")
        self.q = tk.StringVar()
        ttk.Entry(bar, textvariable=self.q, width=26).pack(side="left")
        self.q.trace_add("write", lambda *_: self.fill())
        ttk.Button(bar, text="Importar iconos / .zip / .rar…", style="Accent.TButton",
                   command=self.import_files).pack(side="left", padx=6)
        ttk.Button(bar, text="Importar carpeta…", command=self.import_folder).pack(side="left")
        ttk.Button(bar, text="Abrir carpeta", command=self.open_folder).pack(side="right")
        self.count = tk.Label(w, bg=PANEL, fg=MUTED, anchor="w", padx=12)
        self.count.pack(fill="x")
        body = tk.Frame(w, bg=PANEL)
        body.pack(fill="both", expand=True, padx=8, pady=8)
        self.cv = tk.Canvas(body, bg=PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(body, orient="vertical", command=self.cv.yview)
        self.cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.cv.pack(side="left", fill="both", expand=True)
        self.grid = tk.Frame(self.cv, bg=PANEL)
        self.cv.create_window((0, 0), window=self.grid, anchor="nw")
        self.grid.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cv.bind_all("<MouseWheel>", self._wheel)
        w.bind("<Destroy>", lambda e: self.cv.unbind_all("<MouseWheel>") if e.widget is w else None)
        self.fill()

    def _wheel(self, e):
        try:
            self.cv.yview_scroll(int(-e.delta / 120), "units")
        except Exception:
            pass

    def _thumb(self, path):
        if path not in self.thumbs:
            try:
                im = Image.open(path).convert("RGBA")
                im.thumbnail((self.THUMB - 8, self.THUMB - 8), Image.LANCZOS)
                tile = Image.new("RGBA", (self.THUMB, self.THUMB), render.DARK)
                tile.paste(im, ((self.THUMB - im.width) // 2, (self.THUMB - im.height) // 2), im)
                self.thumbs[path] = ImageTk.PhotoImage(tile.convert("RGB"))
            except Exception:
                self.thumbs[path] = None
        return self.thumbs[path]

    def fill(self):
        for c in self.grid.winfo_children():
            c.destroy()
        q = self.q.get().strip().lower()
        paths = [p for p in icons.list_icons(APP_DIR)
                 if not q or q in icons.display_name(p, APP_DIR).lower()]
        shown = paths[:600]
        self.count.config(text=f"{len(paths)} iconos" + (" (mostrando 600, usa el buscador)" if len(paths) > 600 else "")
                          if paths else "No hay iconos todavía: pulsa «Importar iconos / .zip / .rar…»")
        for n, p in enumerate(shown):
            im = self._thumb(p)
            if im is None:
                continue
            b = tk.Label(self.grid, image=im, bg=PANEL2, bd=0, cursor="hand2", padx=3, pady=3)
            b.grid(row=n // self.COLS, column=n % self.COLS, padx=4, pady=4)
            b.bind("<Button-1>", lambda e, p=p: self.pick(p))
            b.bind("<Enter>", lambda e, b=b, p=p: (b.config(bg=ACCENT),
                                                   self.count.config(text=icons.display_name(p, APP_DIR))))
            b.bind("<Leave>", lambda e, b=b: b.config(bg=PANEL2))
        self.cv.yview_moveto(0)

    def pick(self, path):
        self.on_pick(path)
        self.w.destroy()

    def _import(self, paths):
        if not paths:
            return
        try:
            n, dest = icons.import_icons(list(paths), APP_DIR)
            self.app.log(f"{n} iconos importados en {dest}")
            messagebox.showinfo("Iconos", f"{n} iconos importados.", parent=self.w)
        except Exception as e:
            messagebox.showerror("Iconos", str(e), parent=self.w)
        self.fill()

    def import_files(self):
        self._import(filedialog.askopenfilenames(parent=self.w, title="Iconos o archivo comprimido", filetypes=[
            ("Iconos y comprimidos", "*.png *.jpg *.jpeg *.ico *.bmp *.gif *.webp *.zip *.rar *.7z"),
            ("Todos", "*.*")]))

    def import_folder(self):
        d = filedialog.askdirectory(parent=self.w, title="Carpeta con iconos")
        if d:
            self._import([d])

    def open_folder(self):
        d = os.path.join(APP_DIR, "iconos")
        os.makedirs(d, exist_ok=True)
        actions.run_action(A("abrir", d))


# =============================================================================
# Apariencia: tema, color de acento y fondo (imagen / video / portada) con efectos
# =============================================================================
class AppearanceDialog:
    def __init__(self, app: "App"):
        self.app = app
        self.a = dict(theme.DEFAULT_APPEARANCE, **(app.cfg.get("appearance") or {}))
        self.orig_theme = (self.a["theme"], self.a["accent"])
        w = self.w = tk.Toplevel(app.root, bg=PANEL, padx=18, pady=14)
        w.title("Apariencia")
        w.transient(app.root)
        w.resizable(False, False)
        self._job = None

        def h(text, row):
            tk.Label(w, text=text, bg=PANEL, fg=FG, font=("Segoe UI", 11, "bold")
                     ).grid(row=row, column=0, columnspan=4, sticky="w", pady=(12, 4))

        # --- tema ---
        h("Tema", 0)
        self.theme_v = tk.StringVar(value=self.a["theme"])
        tf = tk.Frame(w, bg=PANEL)
        tf.grid(row=1, column=0, columnspan=4, sticky="w")
        for key, name in theme.THEMES.items():
            ttk.Radiobutton(tf, text=name, value=key, variable=self.theme_v,
                            command=self._theme_changed).pack(side="left", padx=(0, 14))

        # --- color de acento ---
        h("Color de acento", 2)
        af = tk.Frame(w, bg=PANEL)
        af.grid(row=3, column=0, columnspan=4, sticky="w")
        self.swatches = {}
        for col, name in theme.ACCENTS.items():
            b = tk.Label(af, bg=col, width=3, height=1, cursor="hand2", bd=3, relief="flat")
            b.pack(side="left", padx=3)
            b.bind("<Button-1>", lambda e, c=col: self._accent(c))
            self.swatches[col] = b
        self._mark_accent()
        self.restart_lbl = tk.Label(w, text="", bg=PANEL, fg=ACCENT, font=("Segoe UI", 8))
        self.restart_lbl.grid(row=4, column=0, columnspan=3, sticky="w")
        self.restart_btn = ttk.Button(w, text="Aplicar (reinicia la app)", style="Accent.TButton",
                                      command=self._restart)

        # --- fondo ---
        h("Fondo de la ventana", 5)
        self.mode_v = tk.StringVar(value=self.a["bg_mode"])
        mf = tk.Frame(w, bg=PANEL)
        mf.grid(row=6, column=0, columnspan=4, sticky="w")
        for key, name in (("none", "Ninguno"), ("cover", "Portada de la canción"),
                          ("image", "Imagen"), ("video", "Video o GIF")):
            ttk.Radiobutton(mf, text=name, value=key, variable=self.mode_v,
                            command=self._mode_changed).pack(side="left", padx=(0, 12))
        ff = tk.Frame(w, bg=PANEL)
        ff.grid(row=7, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Button(ff, text="Elegir archivo…", command=self._pick_file).pack(side="left")
        self.file_lbl = tk.Label(ff, bg=PANEL, fg=MUTED, font=("Segoe UI", 8))
        self.file_lbl.pack(side="left", padx=8)

        # --- efectos ---
        h("Efectos", 8)
        self.vars = {}
        for r, (key, name, lo, hi) in enumerate((("blur", "Desenfoque", 0, 40),
                                                 ("veil", "Velo (oscurece / aclara)", 0, 90),
                                                 ("saturation", "Saturación", 0, 200)), start=9):
            tk.Label(w, text=name, bg=PANEL, fg=MUTED).grid(row=r, column=0, sticky="w")
            v = tk.IntVar(value=int(self.a[key]))
            ttk.Scale(w, from_=lo, to=hi, variable=v, length=230,
                      command=lambda _=None: self._changed()).grid(row=r, column=1, columnspan=2, sticky="w", padx=6)
            lbl = tk.Label(w, bg=PANEL, fg=FG, width=5)
            lbl.grid(row=r, column=3, sticky="w")
            self.vars[key] = (v, lbl)
        self.vig = tk.BooleanVar(value=self.a["vignette"])
        self.motion = tk.BooleanVar(value=self.a["motion"])
        ttk.Checkbutton(w, text="Viñeta (bordes más oscuros)", variable=self.vig,
                        command=self._changed).grid(row=12, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Checkbutton(w, text="Movimiento lento", variable=self.motion,
                        command=self._changed).grid(row=12, column=2, columnspan=2, sticky="w", pady=(4, 0))
        tk.Label(w, text="Cuadros por segundo (video)", bg=PANEL, fg=MUTED).grid(row=13, column=0, sticky="w")
        self.fps = ttk.Combobox(w, state="readonly", width=6, values=["10", "15", "20", "24", "30"])
        self.fps.set(str(self.a["fps"]))
        self.fps.grid(row=13, column=1, sticky="w", padx=6, pady=4)
        self.fps.bind("<<ComboboxSelected>>", lambda e: self._changed())
        tk.Label(w, text="Los cambios del fondo se ven al momento. Con video, menos cuadros por segundo "
                         "= menos uso del procesador. El fondo se pausa cuando la ventana está oculta.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 8), wraplength=430, justify="left"
                 ).grid(row=14, column=0, columnspan=4, sticky="w", pady=(6, 0))
        bt = tk.Frame(w, bg=PANEL)
        bt.grid(row=15, column=0, columnspan=4, sticky="we", pady=(12, 0))
        ttk.Button(bt, text="Restablecer", command=self._reset).pack(side="left")
        ttk.Button(bt, text="Cerrar", command=w.destroy).pack(side="right")
        self._labels()

    # ---------------------------------------------------------------- helpers
    def _labels(self):
        for key, (v, lbl) in self.vars.items():
            lbl.config(text=f"{int(float(v.get()))}{'%' if key != 'blur' else ''}")
        f = self.a.get("bg_file") or ""
        mode = self.mode_v.get()
        if mode == "cover":
            txt = "Se usa la portada de lo que suena en Spotify."
        elif mode in ("image", "video"):
            txt = os.path.basename(f) if f else "Elige un archivo"
        else:
            txt = ""
        if mode == "video" and f and not f.lower().endswith(".gif") and not background.CV2_OK:
            txt += "  ·  falta el componente de video: reinstala la app (o usa un GIF)"
        self.file_lbl.config(text=txt)

    def _collect(self):
        for key, (v, _) in self.vars.items():
            self.a[key] = int(float(v.get()))
        self.a["vignette"] = self.vig.get()
        self.a["motion"] = self.motion.get()
        self.a["fps"] = int(self.fps.get() or 15)
        self.a["bg_mode"] = self.mode_v.get()

    def _changed(self):
        self._collect()
        self._labels()
        if self._job:
            self.w.after_cancel(self._job)
        self._job = self.w.after(150, self._apply_bg)  # espera a que dejes de mover el deslizador

    def _apply_bg(self):
        self._job = None
        self.app.cfg["appearance"] = dict(self.a)
        self.app.backdrop.configure(self.a)
        if self.a["bg_mode"] in ("image", "video") and self.app.backdrop.a.get("bg_mode") == "none":
            self.file_lbl.config(text="No se pudo usar ese archivo. Prueba con otro (MP4 o GIF).", fg=DANGER)
        else:
            self.file_lbl.config(fg=MUTED)
        self.app.schedule_save()

    def _mode_changed(self):
        mode = self.mode_v.get()
        f = self.a.get("bg_file") or ""
        ok = (mode == "image" and f.lower().endswith(background.IMAGE_EXT)) or \
             (mode == "video" and f.lower().endswith(background.VIDEO_EXT + background.GIF_EXT))
        if mode in ("image", "video") and not ok:
            self.a["bg_file"] = ""
            if not self._pick_file():
                return
        self._changed()

    def _pick_file(self) -> bool:
        mode = self.mode_v.get()
        if mode not in ("image", "video"):
            mode = "image"
            self.mode_v.set("image")
        if mode == "image":
            types = [("Imágenes", "*.png *.jpg *.jpeg *.webp *.bmp")]
        else:
            types = [("Videos y GIF", "*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.wmv *.gif")]
        p = filedialog.askopenfilename(parent=self.w, title="Elegir fondo", filetypes=types + [("Todos", "*.*")])
        if not p:
            return False
        if mode == "image":  # copia para que no se pierda si mueves el original
            try:
                d = os.path.join(APP_DIR, "fondos")
                os.makedirs(d, exist_ok=True)
                dst = os.path.join(d, os.path.basename(p))
                shutil.copyfile(p, dst)
                p = dst
            except Exception:
                pass
        self.a["bg_file"] = p
        self._changed()
        return True

    def _theme_changed(self):
        self.a["theme"] = self.theme_v.get()
        self._needs_restart()

    def _accent(self, col):
        self.a["accent"] = col
        self._mark_accent()
        self._needs_restart()

    def _mark_accent(self):
        for col, b in self.swatches.items():
            b.config(relief="solid" if col == self.a["accent"] else "flat",
                     highlightthickness=2 if col == self.a["accent"] else 0,
                     highlightbackground=FG)

    def _needs_restart(self):
        changed = (self.a["theme"], self.a["accent"]) != self.orig_theme
        self.app.cfg["appearance"] = dict(self.a)
        self.app.schedule_save()
        if changed:
            self.restart_lbl.config(text="El tema y el color se aplican al reiniciar la app.")
            self.restart_btn.grid(row=4, column=3, sticky="e")
        else:
            self.restart_lbl.config(text="")
            self.restart_btn.grid_forget()

    def _restart(self):
        self.app.cfg["appearance"] = dict(self.a)
        save_config(self.app.cfg)
        updater.restart()
        self.app.quit()

    def _reset(self):
        keep = (self.a["theme"], self.a["accent"])
        self.a = dict(theme.DEFAULT_APPEARANCE, theme=keep[0], accent=keep[1])
        self.mode_v.set(self.a["bg_mode"])
        for key, (v, _) in self.vars.items():
            v.set(self.a[key])
        self.vig.set(self.a["vignette"])
        self.motion.set(self.a["motion"])
        self.fps.set(str(self.a["fps"]))
        self._changed()


# =============================================================================
# Ventana de ajustes
# =============================================================================
class SettingsDialog:
    def __init__(self, app: App):
        self.app = app
        top = self.w = tk.Toplevel(app.root, bg=PANEL)
        top.title("Ajustes")
        top.transient(app.root)
        hgt = min(820, top.winfo_screenheight() - 120)
        top.geometry(f"640x{hgt}")
        cv = tk.Canvas(top, bg=PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(top, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        w = tk.Frame(cv, bg=PANEL, padx=18, pady=14)
        cv.create_window((0, 0), window=w, anchor="nw")
        w.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))

        def wheel(e):
            try:
                cv.yview_scroll(int(-e.delta / 120), "units")
            except Exception:
                pass
        top.bind("<MouseWheel>", wheel)
        top.bind_all("<MouseWheel>", wheel)
        top.bind("<Destroy>", lambda e: top.unbind_all("<MouseWheel>") if e.widget is top else None)

        def h(text, row):
            tk.Label(w, text=text, bg=PANEL, fg=FG, font=("Segoe UI", 11, "bold")
                     ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(10, 4))

        def hint(text, row):
            tk.Label(w, text=text, bg=PANEL, fg=MUTED, font=("Segoe UI", 8), justify="left",
                     wraplength=470).grid(row=row, column=0, columnspan=3, sticky="w")

        # --- Spotify ---
        h("Spotify", 0)
        sp = app.sp
        ok = lambda b: "✓" if b else "✗"
        tk.Label(w, bg=PANEL, fg=FG, justify="left", text=(
            f"{ok(sp.available)} Control y portada (controles de Windows)\n"
            f"{ok(sp.volume_available)} Volumen solo de Spotify\n"
            f"{ok(sp.web.connected)} Cuenta conectada (para «Me gusta»)")
        ).grid(row=1, column=0, columnspan=3, sticky="w")
        hint("Lo básico funciona sin iniciar sesión con la app de escritorio de Spotify. "
             "«Me gusta» necesita la API de Spotify: crea una app gratis en developer.spotify.com, "
             "añade esta Redirect URI y pega aquí el Client ID. (Spotify exige que el dueño de la app "
             "tenga Premium.)", 2)
        uri = tk.Entry(w, bg=PANEL2, fg=FG, relief="flat", readonlybackground=PANEL2, width=40)
        uri.insert(0, spotify.REDIRECT_URI)
        uri.config(state="readonly")
        uri.grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Button(w, text="Copiar", command=lambda: (w.clipboard_clear(), w.clipboard_append(
            spotify.REDIRECT_URI))).grid(row=3, column=2, sticky="w")
        tk.Label(w, text="Client ID", bg=PANEL, fg=MUTED).grid(row=4, column=0, sticky="w")
        self.cid = tk.StringVar(value=sp.web.client_id)
        ttk.Entry(w, textvariable=self.cid, width=36).grid(row=4, column=1, sticky="w", padx=6)
        bt = tk.Frame(w, bg=PANEL)
        bt.grid(row=5, column=0, columnspan=3, sticky="w", pady=6)
        ttk.Button(bt, text="Conectar cuenta", style="Green.TButton", command=self.connect).pack(side="left")
        ttk.Button(bt, text="Desconectar", command=self.disconnect).pack(side="left", padx=6)
        ttk.Button(bt, text="Abrir developer.spotify.com",
                   command=lambda: actions.run_action(A("abrir", "https://developer.spotify.com/dashboard"))
                   ).pack(side="left")

        # --- Dispositivo ---
        h("Stream Dock N3E", 6)
        tk.Label(w, text="Protocolo", bg=PANEL, fg=MUTED).grid(row=7, column=0, sticky="w")
        self.proto = ttk.Combobox(w, values=["auto", "2", "3"], state="readonly", width=8)
        self.proto.set(str(app.cfg["protocol"]))
        self.proto.grid(row=7, column=1, sticky="w", padx=6)
        hint("Si las imágenes salen giradas, cortadas o no aparecen, prueba 3 y luego 2.", 8)
        ttk.Button(w, text="Buscar el N3E ahora", command=self.scan).grid(row=9, column=0, sticky="w", pady=6)
        ttk.Button(w, text="Reconectar", command=self.reconnect).grid(row=9, column=1, sticky="w")

        # --- Actualizaciones ---
        h(f"Actualizaciones  ·  versión {VERSION}", 20)
        tk.Label(w, bg=PANEL, fg=FG, justify="left", text=(
            ("🔗 Conexión con Claude: ACTIVADA" if app.cfg.get("claude_link") else
             "🔗 Conexión con Claude: desactivada (actívala con el botón de arriba)"))
        ).grid(row=21, column=0, columnspan=3, sticky="w")
        hint(f"Carpeta de conexión: {updater.INBOX}", 22)
        bt3 = tk.Frame(w, bg=PANEL)
        bt3.grid(row=23, column=0, columnspan=3, sticky="w", pady=6)
        ttk.Button(bt3, text="Abrir carpeta de conexión",
                   command=lambda: (updater.ensure_inbox(), actions.run_action(A("abrir", updater.INBOX)))
                   ).pack(side="left")
        ttk.Button(bt3, text="Actualizar desde archivo…",
                   command=lambda: (self.w.destroy(), app.update_from_file())).pack(side="left", padx=6)
        ttk.Button(bt3, text="Volver a la versión anterior",
                   command=lambda: (self.w.destroy(), app.rollback())).pack(side="left")

        # --- Pantallas de las teclas ---
        h("Pantallas de las teclas", 24)
        sc = app.cfg.get("screen") or {}
        self.scr_size = int(sc.get("size") or 0)       # 0 = automático
        self.scr_ox, self.scr_oy = int(sc.get("ox", 0)), int(sc.get("oy", 0))
        cal = tk.Frame(w, bg=PANEL2, padx=12, pady=10)
        cal.grid(row=25, column=0, columnspan=3, sticky="we", pady=4)
        tk.Label(cal, text="Tamaño", bg=PANEL2, fg=MUTED).grid(row=0, column=0, sticky="w")
        ttk.Button(cal, text="−", width=3, command=lambda: self.nudge_size(-1)).grid(row=0, column=1)
        self.size_lbl = tk.Label(cal, bg=PANEL2, fg=FG, width=12, font=("Segoe UI", 10, "bold"))
        self.size_lbl.grid(row=0, column=2)
        ttk.Button(cal, text="+", width=3, command=lambda: self.nudge_size(+1)).grid(row=0, column=3)
        tk.Label(cal, text="Mover la imagen", bg=PANEL2, fg=MUTED).grid(row=1, column=0, sticky="w", pady=(10, 0))
        pad = tk.Frame(cal, bg=PANEL2)
        pad.grid(row=1, column=1, columnspan=3, pady=(10, 0))
        ttk.Button(pad, text="▲", width=3, command=lambda: self.nudge(0, -1)).grid(row=0, column=1)
        ttk.Button(pad, text="◀", width=3, command=lambda: self.nudge(-1, 0)).grid(row=1, column=0)
        ttk.Button(pad, text="●", width=3, command=lambda: self.nudge(None, None)).grid(row=1, column=1)
        ttk.Button(pad, text="▶", width=3, command=lambda: self.nudge(+1, 0)).grid(row=1, column=2)
        ttk.Button(pad, text="▼", width=3, command=lambda: self.nudge(0, +1)).grid(row=2, column=1)
        self.off_lbl = tk.Label(cal, bg=PANEL2, fg=FG, font=("Segoe UI", 10, "bold"))
        self.off_lbl.grid(row=1, column=4, padx=10, pady=(10, 0))
        tk.Label(cal, text="Giro", bg=PANEL2, fg=MUTED).grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.rots = ["Automático", "0°", "90°", "180°", "270°"]
        self.rot_cb = ttk.Combobox(cal, state="readonly", width=12, values=self.rots)
        r = int(sc.get("rotation", -1))
        self.rot_cb.set(self.rots[0] if r < 0 else f"{r}°")
        self.rot_cb.grid(row=2, column=1, columnspan=3, sticky="w", pady=(10, 0))
        self.rot_cb.bind("<<ComboboxSelected>>", lambda e: self.live_screen())
        ttk.Button(cal, text="Ver patrón", style="Green.TButton", command=self.try_screen).grid(
            row=0, column=4, padx=10)
        self._screen_labels()
        self.clear_bg = tk.BooleanVar(value=sc.get("clear_bg", True))
        ttk.Checkbutton(w, text="Borrar el fondo que dejó el software oficial (al conectar)",
                        variable=self.clear_bg).grid(row=27, column=0, columnspan=3, sticky="w", pady=(4, 0))
        hint("Pulsa «Ver patrón» y mira el N3E. Con − / + ajusta el tamaño hasta que el marco blanco "
             "llegue a los bordes, y con las flechas mueve la imagen hasta que quede centrada "
             "(● la devuelve al centro). Los cambios se ven al momento en el dispositivo.", 28)

        # --- General ---
        h("General", 10)
        self.startup = tk.BooleanVar(value=os.path.exists(app._startup_path()))
        self.minim = tk.BooleanVar(value=app.cfg.get("start_minimized", False))
        ttk.Checkbutton(w, text="Iniciar con Windows", variable=self.startup).grid(row=11, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(w, text="Iniciar minimizado (junto al reloj)", variable=self.minim).grid(
            row=12, column=0, columnspan=2, sticky="w")
        self.to_tray = tk.BooleanVar(value=app.cfg.get("close_to_tray", True))
        ttk.Checkbutton(w, text="Al cerrar la ventana, seguir funcionando junto al reloj",
                        variable=self.to_tray).grid(row=12, column=2, sticky="w")

        # --- Protector de pantalla ---
        h("Protector de pantalla del N3E", 14)
        self.saver_modes = {"off": "Desactivado", "portada": "Portada gigante en las 6 teclas",
                            "atenuar": "Bajar el brillo", "apagar": "Apagar las pantallas"}
        sv = app.cfg.get("saver") or {}
        tk.Label(w, text="Modo", bg=PANEL, fg=MUTED).grid(row=15, column=0, sticky="w")
        self.saver_cb = ttk.Combobox(w, state="readonly", width=32, values=list(self.saver_modes.values()))
        self.saver_cb.set(self.saver_modes.get(sv.get("mode", "portada"), "Desactivado"))
        self.saver_cb.grid(row=15, column=1, columnspan=2, sticky="w", padx=6)
        tk.Label(w, text="Tras (minutos)", bg=PANEL, fg=MUTED).grid(row=16, column=0, sticky="w")
        self.saver_min = ttk.Combobox(w, state="readonly", width=6, values=["1", "2", "5", "10", "15", "30", "60"])
        self.saver_min.set(str(sv.get("minutes", 5)))
        self.saver_min.grid(row=16, column=1, sticky="w", padx=6, pady=2)
        ttk.Button(w, text="Probar ahora", command=lambda: (self.save(), app.start_saver())).grid(
            row=16, column=2, sticky="w")
        hint("Se activa si no tocas el N3E en ese tiempo. Cualquier tecla o perilla lo despierta "
             "(ese primer toque no ejecuta ninguna acción). Sin música, «Portada gigante» baja el brillo.", 17)
        bt2 = tk.Frame(w, bg=PANEL)
        bt2.grid(row=13, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Button(bt2, text="Exportar perfil", command=self.export).pack(side="left")
        ttk.Button(bt2, text="Importar perfil", command=self.import_).pack(side="left", padx=6)
        ttk.Button(bt2, text="Restaurar perfil por defecto", command=self.reset).pack(side="left")
        ttk.Button(w, text="Guardar", style="Accent.TButton", command=self.save).grid(
            row=30, column=2, sticky="e", pady=(14, 0))

    def connect(self):
        cid = self.cid.get().strip()
        if len(cid) < 20:
            messagebox.showerror("Spotify", "Pega el Client ID de tu app de Spotify.", parent=self.w)
            return
        self.app.log("Abriendo Spotify en el navegador para autorizar…")

        def work():
            try:
                self.app.q.put(("log", self.app.sp.web.connect(cid)))
            except Exception as e:
                self.app.q.put(("log", f"No se pudo conectar Spotify: {e}"))
        threading.Thread(target=work, daemon=True).start()
        self.w.destroy()

    def disconnect(self):
        self.app.sp.web.disconnect()
        self.app.log("Cuenta de Spotify desconectada")
        self.w.destroy()

    def scan(self):
        c = dock.find_candidates()
        if c:
            self.app.log(f"N3E encontrado: {c[0].vidpid} ({c[0].reason})")
        else:
            self.app.log("No se encontró el N3E_1B05. Revisa el cable y cierra el software oficial.")

    def reconnect(self):
        self.app.mgr.reconnect()
        self.app.log("Reconectando…")

    def export(self):
        p = filedialog.asksaveasfilename(parent=self.w, defaultextension=".json",
                                         initialfile="perfil_streamdock.json", filetypes=[("Perfil", "*.json")])
        if p:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self.app.cfg, f, ensure_ascii=False, indent=2)
            self.app.log(f"Perfil exportado: {p}")

    def import_(self):
        p = filedialog.askopenfilename(parent=self.w, filetypes=[("Perfil", "*.json")])
        if not p:
            return
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            assert data.get("version") == CONFIG_VERSION and "pages" in data
        except Exception:
            messagebox.showerror(APP_NAME, "Ese archivo no es un perfil válido.", parent=self.w)
            return
        self._replace_cfg(data)

    def reset(self):
        if messagebox.askyesno(APP_NAME, "¿Volver al perfil por defecto (Spotify + Sistema)?", parent=self.w):
            self._replace_cfg(default_config())

    def _replace_cfg(self, data):
        app = self.app
        keep = {k: app.cfg.get(k) for k in ("brightness", "protocol", "start_minimized", "claude_link",
                                           "close_to_tray", "saver", "screen", "appearance")}
        app.cfg = default_config()
        app.cfg.update(data)
        app.cfg.update(keep)
        if app.cfg["current_page"] not in app.cfg["pages"]:
            app.cfg["current_page"] = next(iter(app.cfg["pages"]))
        app.refresh_pages()
        app.redraw_device()
        app.select(("key", 0))
        app.schedule_save()

    def _screen_labels(self):
        dev = self.app.mgr.device
        auto = dev.image_size if dev and not self.scr_size else 64
        self.size_lbl.config(text=f"{self.scr_size} px" if self.scr_size else f"Auto ({auto} px)")
        self.off_lbl.config(text=f"X {self.scr_ox:+d}   Y {self.scr_oy:+d}")

    def _screen_cfg(self):
        rv = self.rot_cb.get().rstrip("°")
        rot = int(rv) if rv.isdigit() else -1
        return {"size": self.scr_size, "rotation": rot, "clear_bg": self.clear_bg.get(),
                "ox": self.scr_ox, "oy": self.scr_oy}

    def nudge_size(self, d):
        dev = self.app.mgr.device
        cur = self.scr_size or (dev.image_size if dev else 64)
        self.scr_size = max(48, min(140, cur + d))
        self.live_screen()

    def nudge(self, dx, dy):
        if dx is None:
            self.scr_ox = self.scr_oy = 0
        else:
            self.scr_ox = max(-40, min(40, self.scr_ox + dx))
            self.scr_oy = max(-40, min(40, self.scr_oy + dy))
        self.live_screen()

    def live_screen(self):
        """Aplica al momento en el N3E y deja el patrón visible para ver el efecto."""
        app = self.app
        app.cfg["screen"] = self._screen_cfg()
        self._screen_labels()
        if app.mgr.device:
            app.apply_screen(clear=False)
            app.show_test_pattern(quiet=True)
        app.schedule_save()

    def try_screen(self):
        app = self.app
        app.cfg["screen"] = self._screen_cfg()
        if not app.mgr.device:
            messagebox.showinfo("Pantallas", "Conecta el N3E para ver el patrón.", parent=self.w)
            return
        app.apply_screen(clear=True)
        app.show_test_pattern()
        app.schedule_save()

    def save(self):
        app = self.app
        new_screen = self._screen_cfg()
        if new_screen != app.cfg.get("screen"):
            app.cfg["screen"] = new_screen
            app.apply_screen(clear=new_screen["clear_bg"])
            app.update_keys(force=True)
        app.cfg["start_minimized"] = self.minim.get()
        app.cfg["close_to_tray"] = self.to_tray.get()
        mode = next((k for k, v in self.saver_modes.items() if v == self.saver_cb.get()), "off")
        app.cfg["saver"] = {"mode": mode, "minutes": int(self.saver_min.get() or 5)}
        if mode == "off" and app.saver_on:
            app.wake_saver()
        try:
            app.set_startup(self.startup.get())
        except Exception as e:
            app.log(f"No se pudo cambiar el inicio con Windows: {e}")
        if self.proto.get() != str(app.cfg["protocol"]):
            app.cfg["protocol"] = self.proto.get()
            app.mgr.protocol_override = None if app.cfg["protocol"] == "auto" else int(app.cfg["protocol"])
            app.mgr.reconnect()
        app.schedule_save()
        self.w.destroy()


# =============================================================================
def single_instance(wait_s: float = 0) -> bool:
    """Solo una copia abierta. Tras actualizar, espera a que se cierre la anterior."""
    if sys.platform != "win32":
        return True
    import ctypes
    k32 = ctypes.windll.kernel32
    t0 = time.time()
    while True:
        h = k32.CreateMutexW(None, False, "StreamDockLite_Mutex")
        if k32.GetLastError() != 183:
            return True
        k32.CloseHandle(h)
        if time.time() - t0 >= wait_s:
            return False
        time.sleep(0.5)


def main():
    if not single_instance(15 if "--restart" in sys.argv else 0):
        messagebox.showinfo(APP_NAME, "Stream Dock Lite ya está abierto.")
        return
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            # identidad propia en la barra de tareas (si no, sale el icono de Python)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("StreamDockLite.App")
        except Exception:
            pass
    theme.apply_to_modules(load_config().get("appearance"), sys.modules[__name__], gallery)
    root = tk.Tk()
    try:
        root.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico"))
    except Exception:
        pass
    App(root)
    theme.titlebar(root, MODE == "dark")
    root.mainloop()


if __name__ == "__main__":
    main()
