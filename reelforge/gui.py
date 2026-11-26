"""Interfaz grafica de ReelForge (customtkinter)."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from dataclasses import fields
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox

import customtkinter as ctk

from . import __version__
from .config import (CUT_MODES, ENCODERS, FIT_MODES, FPS_LIST, LOOK_NAMES, ORDER_MODES, OUTLINE_COLORS, OUTLINE_MODES,
                     QUALITIES, RESOLUTIONS, SLOWMO_MODES, STYLE_PRESETS, TITLE_POS, Settings)
from .engine import Engine
from .ffutil import AUDIO_EXT, IMAGE_EXT, VIDEO_EXT, EngineError
from .overlays import user_overlay_dir

ACCENT = "#ff5a1f"
ACCENT_H = "#ff7a45"
BG = "#121216"
CARD = "#1b1b22"
MUTED = "#8b8b99"

PRESET_INFO = {
    "Equilibrado (recomendado)": "Mezcla de cortes, curvas y fuego en los picos. Buen punto de partida.",
    "Cinematico suave": "Cortes lentos, fundidos y light leaks. Ideal para musica melodica.",
    "Energetico / TikTok": "Cortes rapidos, zooms con punch y colores vivos.",
    "Phonk / Agresivo": "Maximo shake, glitch, destellos y arte. Cortes muy rapidos.",
    "Fuego total": "Fuego en casi cada golpe y cortes en cada beat.",
    "Cyberpunk neon": "Colores neon, glitch y efectos artisticos.",
}


def open_path(path):
    try:
        if os.name == "nt":
            os.startfile(str(path))  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


def settings_file():
    d = Path.home() / ".reelforge"
    d.mkdir(parents=True, exist_ok=True)
    return d / "settings.json"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.title("ReelForge %s - Editor automatico de Reels" % __version__)
        self.geometry("1240x820")
        self.minsize(1100, 720)
        self.configure(fg_color=BG)

        self.defaults = Settings()
        self.vars = {}
        self.q = queue.Queue()
        self.engine = None
        self.worker = None
        self.last_output = ""
        self.preview_mode = False
        self._busy = False

        self._build_header()
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self._build_left(body)
        self._build_tabs(body)
        self._build_bottom()

        self._load_settings()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll)
        self._log("Listo. Anade tus videos y un audio, elige un estilo y pulsa GENERAR REEL.")

    # ------------------------------------------------------------ variables
    def var(self, key):
        if key not in self.vars:
            d = getattr(self.defaults, key)
            if isinstance(d, bool):
                v = tk.BooleanVar(value=d)
            elif isinstance(d, (int, float)) and key not in ("seed", "audio_start", "max_duration", "title_seconds",
                                                             "text_size"):
                v = tk.DoubleVar(value=float(d))
            else:
                v = tk.StringVar(value=str(d))
            self.vars[key] = v
        return self.vars[key]

    def collect(self):
        base = Settings()
        for f in fields(Settings):
            k = f.name
            if k in ("videos", "preview"):
                continue
            if k not in self.vars:
                continue
            raw = self.vars[k].get()
            d = getattr(base, k)
            try:
                if isinstance(d, bool):
                    val = bool(raw)
                elif isinstance(d, int):
                    val = int(float(str(raw).replace(",", ".")))
                elif isinstance(d, float):
                    val = float(str(raw).replace(",", "."))
                else:
                    val = str(raw)
            except ValueError:
                val = d
            setattr(base, k, val)
        base.videos = list(self.video_paths())
        return base

    def apply_dict(self, d):
        for k, v in d.items():
            if k in self.vars:
                try:
                    self.vars[k].set(v)
                except Exception:
                    pass

    # ------------------------------------------------------------ widgets helpers
    def _card(self, parent, title=None):
        fr = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12)
        fr.pack(fill="x", pady=(0, 10))
        if title:
            ctk.CTkLabel(fr, text=title, font=ctk.CTkFont(size=14, weight="bold"), text_color=ACCENT,
                         anchor="w").pack(fill="x", padx=12, pady=(10, 4))
        return fr

    def _switch(self, parent, key, text):
        ctk.CTkSwitch(parent, text=text, variable=self.var(key), progress_color=ACCENT,
                      button_hover_color=ACCENT_H).pack(anchor="w", pady=4, padx=4)

    def _slider(self, parent, key, text, lo, hi, steps=None, fmt="{:.0f}", suffix=""):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(row, text=text, anchor="w").pack(side="left")
        val = ctk.CTkLabel(row, text="", width=70, anchor="e", text_color=MUTED)
        val.pack(side="right")
        var = self.var(key)

        def upd(*_):
            try:
                val.configure(text=fmt.format(var.get()) + suffix)
            except Exception:
                pass

        ctk.CTkSlider(parent, from_=lo, to=hi, number_of_steps=steps, variable=var, progress_color=ACCENT,
                      button_color=ACCENT, button_hover_color=ACCENT_H).pack(fill="x", pady=(2, 4))
        var.trace_add("write", upd)
        upd()

    def _option(self, parent, key, text, values, width=230):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=text, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(row, values=list(values), variable=self.var(key), width=width, fg_color="#2a2a33",
                          button_color=ACCENT, button_hover_color=ACCENT_H).pack(side="right")

    def _entry(self, parent, key, text, width=230, placeholder=""):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=text, anchor="w").pack(side="left")
        ctk.CTkEntry(row, textvariable=self.var(key), width=width, placeholder_text=placeholder).pack(side="right")

    def _hint(self, parent, text):
        ctk.CTkLabel(parent, text=text, text_color=MUTED, anchor="w", justify="left", wraplength=620,
                     font=ctk.CTkFont(size=12)).pack(fill="x", padx=4, pady=(0, 6))

    # ------------------------------------------------------------ layout
    def _build_header(self):
        h = ctk.CTkFrame(self, fg_color="transparent")
        h.pack(fill="x", padx=18, pady=(12, 8))
        ctk.CTkLabel(h, text="REEL", font=ctk.CTkFont(size=28, weight="bold")).pack(side="left")
        ctk.CTkLabel(h, text="FORGE", font=ctk.CTkFont(size=28, weight="bold"), text_color=ACCENT).pack(side="left")
        ctk.CTkLabel(h, text="   Edits verticales con curvas de velocidad, fuego y transiciones al ritmo de la musica",
                     text_color=MUTED).pack(side="left", padx=10)
        ctk.CTkButton(h, text="Cargar ajustes", width=110, fg_color="#2a2a33", hover_color="#3a3a46",
                      command=self._load_dialog).pack(side="right", padx=(6, 0))
        ctk.CTkButton(h, text="Guardar ajustes", width=110, fg_color="#2a2a33", hover_color="#3a3a46",
                      command=self._save_dialog).pack(side="right")

    def _build_left(self, body):
        left = ctk.CTkFrame(body, fg_color="transparent", width=400)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 12))

        c = self._card(left, "1. Videos / imagenes base")
        lf = ctk.CTkFrame(c, fg_color="transparent")
        lf.pack(fill="x", padx=12)
        self.listbox = tk.Listbox(lf, height=8, width=46, selectmode="extended", bg="#101015", fg="#eaeaea",
                                  selectbackground=ACCENT, selectforeground="white", borderwidth=0,
                                  highlightthickness=0, activestyle="none", font=("Segoe UI", 9))
        sb = ctk.CTkScrollbar(lf, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._paths = []
        bf = ctk.CTkFrame(c, fg_color="transparent")
        bf.pack(fill="x", padx=12, pady=(8, 12))
        for text, cmd in (("Anadir", self._add_videos), ("Quitar", self._remove_videos),
                          ("Subir", lambda: self._move(-1)), ("Bajar", lambda: self._move(1)),
                          ("Limpiar", self._clear_videos)):
            ctk.CTkButton(bf, text=text, width=64, height=28, fg_color="#2a2a33", hover_color="#3a3a46",
                          command=cmd).pack(side="left", padx=2)

        c = self._card(left, "2. Audio (musica del reel)")
        r = ctk.CTkFrame(c, fg_color="transparent")
        r.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkEntry(r, textvariable=self.var("audio"), width=270).pack(side="left")
        ctk.CTkButton(r, text="Buscar", width=70, fg_color=ACCENT, hover_color=ACCENT_H,
                      command=self._pick_audio).pack(side="left", padx=6)

        c = self._card(left, "3. Guardar como")
        r = ctk.CTkFrame(c, fg_color="transparent")
        r.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkEntry(r, textvariable=self.var("output"), width=270).pack(side="left")
        ctk.CTkButton(r, text="Elegir", width=70, fg_color=ACCENT, hover_color=ACCENT_H,
                      command=self._pick_output).pack(side="left", padx=6)
        self.var("output").set(self._new_output_name())

        c = self._card(left)
        self.btn_analyze = ctk.CTkButton(c, text="Analizar audio (BPM / beats / drops)", height=34,
                                         fg_color="#2a2a33", hover_color="#3a3a46", command=self._analyze)
        self.btn_analyze.pack(fill="x", padx=12, pady=(12, 6))
        self.btn_preview = ctk.CTkButton(c, text="Vista previa rapida (6 s)", height=34, fg_color="#2a2a33",
                                         hover_color="#3a3a46", command=lambda: self._start(True))
        self.btn_preview.pack(fill="x", padx=12, pady=6)
        self.btn_go = ctk.CTkButton(c, text="GENERAR REEL", height=48, fg_color=ACCENT, hover_color=ACCENT_H,
                                    font=ctk.CTkFont(size=16, weight="bold"), command=lambda: self._start(False))
        self.btn_go.pack(fill="x", padx=12, pady=6)
        self.btn_cancel = ctk.CTkButton(c, text="Cancelar", height=30, fg_color="#552222", hover_color="#773333",
                                        command=self._cancel, state="disabled")
        self.btn_cancel.pack(fill="x", padx=12, pady=(6, 12))

    def _build_tabs(self, body):
        tabs = ctk.CTkTabview(body, fg_color=CARD, segmented_button_selected_color=ACCENT,
                              segmented_button_selected_hover_color=ACCENT_H)
        tabs.grid(row=0, column=1, sticky="nsew")

        def tab(name):
            t = tabs.add(name)
            sf = ctk.CTkScrollableFrame(t, fg_color="transparent")
            sf.pack(fill="both", expand=True)
            return sf

        # ---- Estilo y ritmo
        t = tab("Estilo y ritmo")
        self.preset_var = tk.StringVar(value=list(STYLE_PRESETS)[0])
        row = ctk.CTkFrame(t, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text="Estilo de edicion", anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkOptionMenu(row, values=list(STYLE_PRESETS), variable=self.preset_var, width=260, fg_color="#2a2a33",
                          button_color=ACCENT, button_hover_color=ACCENT_H,
                          command=self._apply_preset).pack(side="right")
        self.preset_info = ctk.CTkLabel(t, text="", text_color=MUTED, anchor="w", justify="left", wraplength=620)
        self.preset_info.pack(fill="x", padx=4, pady=(0, 8))
        self._option(t, "cut_mode", "Frecuencia de cortes", CUT_MODES)
        self._slider(t, "cut_density", "Densidad de cortes (modo Auto)", 0, 100, 20, suffix=" %")
        self._option(t, "clip_order", "Orden de los clips", ORDER_MODES)
        self._option(t, "fit_mode", "Formato vertical", FIT_MODES)
        self._entry(t, "max_duration", "Duracion del reel (segundos, 0 = todo el audio)", 90)
        self._entry(t, "audio_start", "Empezar el audio en (segundos)", 90)
        self._switch(t, "auto_best_part", "Elegir automaticamente la mejor parte del audio (si inicio = 0)")
        row = ctk.CTkFrame(t, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text="Semilla (0 = distinta cada vez)", anchor="w").pack(side="left")
        ctk.CTkButton(row, text="Nueva", width=60, fg_color="#2a2a33", hover_color="#3a3a46",
                      command=lambda: self.var("seed").set("0")).pack(side="right", padx=(6, 0))
        ctk.CTkEntry(row, textvariable=self.var("seed"), width=90).pack(side="right")
        self._hint(t, "Si un resultado te gusta, repite la semilla que aparece en el registro para obtener el mismo edit.")

        # ---- Velocidad
        t = tab("Curvas de velocidad")
        self._switch(t, "speed_curves", "Activar curvas de velocidad (speed ramps) en cada corte")
        self._slider(t, "speed_intensity", "Intensidad de las curvas", 0, 100, 20, suffix=" %")
        self._slider(t, "base_speed", "Velocidad media del material", 0.7, 2.2, 15, fmt="{:.2f}", suffix=" x")
        self._option(t, "slowmo_smooth", "Suavizado de camara lenta", SLOWMO_MODES)
        self._hint(t, "Las curvas combinan: lento -> rapido (build), rapido -> lento (impacto), lento-rapido-lento "
                      "(hero) y bullet-time. Se elige segun la energia de la musica en cada corte. "
                      "'Interpolacion' da la camara lenta mas suave pero tarda bastante mas.")

        # ---- Camara
        t = tab("Camara y transiciones")
        self._slider(t, "fx_intensity", "Intensidad general de efectos", 0, 100, 20, suffix=" %")
        self._switch(t, "zoom_punch", "Zoom con 'punch' en cada golpe")
        self._switch(t, "camera_shake", "Sacudida de camara (shake)")
        self._switch(t, "roll_tilt", "Giros / inclinacion de camara (roll)")
        self._switch(t, "rgb_split", "Aberracion cromatica / glitch RGB")
        self._switch(t, "flash", "Destellos (flash) en drops y golpes fuertes")
        self._switch(t, "camera_transitions", "Transiciones de camara en los cortes (zoom-through, whip, roll, glitch, flash)")
        self._switch(t, "xfade_transitions", "Transiciones suaves en zonas tranquilas (fundidos, wipes, slides, circulos...)")
        self._slider(t, "xfade_amount", "Cantidad de transiciones suaves", 0, 100, 20, suffix=" %")
        ctk.CTkLabel(t, text="Efectos extra", font=ctk.CTkFont(size=14, weight="bold"), text_color=ACCENT,
                     anchor="w").pack(fill="x", padx=4, pady=(14, 0))
        self._slider(t, "extra_fx_amount", "Frecuencia de efectos extra", 0, 100, 20, suffix=" %")
        self._switch(t, "ghost_trails", "Estela / ghost trails (rastro de movimiento)")
        self._switch(t, "zoom_blur", "Zoom blur (desenfoque radial) en cortes")
        self._switch(t, "pixel_fx", "Pixelado en transiciones")
        self._switch(t, "slice_glitch", "Glitch por franjas (slice) en transiciones")
        self._switch(t, "strobe_fx", "Strobe (luz estroboscopica) en drops y cortes")
        self._switch(t, "hue_pulse", "Pulso de color (cambio de tono) en golpes")
        self._switch(t, "mirror_fx", "Espejo y caleidoscopio en golpes")

        # ---- Look y arte
        t = tab("Look y arte")
        self._option(t, "look", "Look de color", LOOK_NAMES)
        self._switch(t, "vignette", "Vineta")
        self._switch(t, "grain", "Grano de pelicula")
        self._switch(t, "art_effects", "Efectos artisticos en los golpes (comic, boceto, posterizado, duotono, termico, glow, negativo)")
        self._slider(t, "art_amount", "Frecuencia de efectos artisticos", 0, 100, 20, suffix=" %")
        ctk.CTkLabel(t, text="Bordeado neon de objetos", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=ACCENT, anchor="w").pack(fill="x", padx=4, pady=(14, 0))
        self._option(t, "outline_mode", "Bordeado", OUTLINE_MODES, 160)
        self._option(t, "outline_color", "Color del borde", OUTLINE_COLORS, 160)
        self._slider(t, "outline_strength", "Intensidad del borde", 0, 100, 20, suffix=" %")
        self._hint(t, "Dibuja un contorno neon con glow sobre los bordes mas marcados, con prioridad a la zona "
                      "central (donde suele estar el sujeto), y pulsa con cada golpe de la musica. "
                      "No es un recorte con IA: funciona mejor con sujetos bien contrastados del fondo.")

        # ---- Overlays
        t = tab("Overlays y fuego")
        self._slider(t, "overlay_amount", "Cantidad general de overlays", 0, 100, 20, suffix=" %")
        self._switch(t, "fire", "Fuego en drops y golpes (y 'puentes' de fuego entre cortes)")
        self._slider(t, "fire_amount", "Cantidad de fuego", 0, 100, 20, suffix=" %")
        self._switch(t, "sparks", "Chispas y brasas")
        self._switch(t, "smoke", "Humo (tambien como puente entre cortes)")
        self._switch(t, "flare", "Lens flare (destello de lente con halo)")
        self._switch(t, "shine", "Reflejos / brillos que barren la imagen")
        self._switch(t, "bokeh", "Bokeh (luces desenfocadas)")
        self._switch(t, "light_leaks", "Light leaks (luces de lente de colores)")
        self._switch(t, "dust", "Polvo y particulas de pelicula")
        self._switch(t, "rain", "Lluvia")
        self._switch(t, "user_overlays", "Usar mis overlays (carpeta 'overlays')")
        self._hint(t, "Se reparten segun la energia de la musica: fuego, chispas y flares en los golpes fuertes; "
                      "humo, bokeh y polvo en las partes suaves. Puedes combinar hasta 2 por corte.\n"
                      "Pon en la carpeta 'overlays' tus propios efectos en video (fuego real, humo, glitches...) "
                      "sobre fondo NEGRO: se mezclan en modo 'screen'.")
        ctk.CTkButton(t, text="Abrir carpeta de overlays", fg_color="#2a2a33", hover_color="#3a3a46",
                      command=lambda: open_path(user_overlay_dir())).pack(anchor="w", padx=4, pady=6)

        # ---- Texto
        t = tab("Texto en pantalla")
        self._hint(t, "Todo el texto es opcional. Deja los campos vacios para no mostrar nada.")
        self._entry(t, "title_text", "Titulo inicial", 330, "Ej: MI EDIT 2026")
        self._option(t, "title_pos", "Posicion del titulo", TITLE_POS, 160)
        self._entry(t, "title_seconds", "Segundos que se muestra el titulo", 90)
        self._entry(t, "kinetic_words", "Palabras por corte (separadas por espacios)", 330, "FIRE  EDIT  FLOW")
        self._hint(t, "Las palabras aparecen una por corte, en el ritmo de la musica, con animacion de entrada.")
        row = ctk.CTkFrame(t, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text="Color del texto", anchor="w").pack(side="left")
        ctk.CTkButton(row, text="Elegir color", width=100, fg_color="#2a2a33", hover_color="#3a3a46",
                      command=self._pick_color).pack(side="right", padx=(6, 0))
        ctk.CTkEntry(row, textvariable=self.var("text_color"), width=100).pack(side="right")
        self._slider(t, "text_size", "Tamano del texto", 50, 220, 34, suffix=" px")
        row = ctk.CTkFrame(t, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text="Fuente (.ttf, opcional)", anchor="w").pack(side="left")
        ctk.CTkButton(row, text="Buscar", width=70, fg_color="#2a2a33", hover_color="#3a3a46",
                      command=self._pick_font).pack(side="right", padx=(6, 0))
        ctk.CTkEntry(row, textvariable=self.var("font_path"), width=260,
                     placeholder_text="Auto: Impact / Arial Black").pack(side="right")

        # ---- Salida
        t = tab("Salida")
        self._option(t, "resolution", "Resolucion", RESOLUTIONS, 160)
        self._option(t, "fps", "Fotogramas por segundo", FPS_LIST, 160)
        self._option(t, "quality", "Calidad", QUALITIES, 160)
        self._option(t, "encoder", "Codificador (GPU acelera mucho)", ENCODERS, 200)
        self._hint(t, "Si el codificador de GPU no esta disponible en tu equipo, se usa la CPU automaticamente.")
        self._apply_preset(list(STYLE_PRESETS)[0])

    def _build_bottom(self):
        b = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12)
        b.pack(fill="x", padx=14, pady=(0, 12))
        top = ctk.CTkFrame(b, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 4))
        self.status = ctk.CTkLabel(top, text="En espera", anchor="w")
        self.status.pack(side="left")
        self.pct = ctk.CTkLabel(top, text="0 %", text_color=ACCENT, anchor="e")
        self.pct.pack(side="right")
        self.bar = ctk.CTkProgressBar(b, progress_color=ACCENT)
        self.bar.set(0)
        self.bar.pack(fill="x", padx=12, pady=(0, 6))
        self.log_box = ctk.CTkTextbox(b, height=120, fg_color="#101015", font=ctk.CTkFont(family="Consolas", size=12))
        self.log_box.pack(fill="x", padx=12, pady=(0, 12))

    # ------------------------------------------------------------ acciones de listas
    def video_paths(self):
        return list(self._paths)

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for p in self._paths:
            self.listbox.insert("end", Path(p).name)

    def _add_videos(self):
        exts = " ".join("*" + e for e in sorted(VIDEO_EXT | IMAGE_EXT))
        files = filedialog.askopenfilenames(title="Selecciona videos o imagenes",
                                            filetypes=[("Videos e imagenes", exts), ("Todos", "*.*")])
        for f in files:
            if f not in self._paths:
                self._paths.append(f)
        self._refresh_list()

    def _remove_videos(self):
        for i in sorted(self.listbox.curselection(), reverse=True):
            del self._paths[i]
        self._refresh_list()

    def _clear_videos(self):
        self._paths.clear()
        self._refresh_list()

    def _move(self, d):
        sel = list(self.listbox.curselection())
        if len(sel) != 1:
            return
        i = sel[0]
        j = i + d
        if 0 <= j < len(self._paths):
            self._paths[i], self._paths[j] = self._paths[j], self._paths[i]
            self._refresh_list()
            self.listbox.selection_set(j)

    def _pick_audio(self):
        exts = " ".join("*" + e for e in sorted(AUDIO_EXT | {".mp4", ".mov"}))
        f = filedialog.askopenfilename(title="Selecciona el audio", filetypes=[("Audio", exts), ("Todos", "*.*")])
        if f:
            self.var("audio").set(f)

    def _new_output_name(self):
        base = Path.home() / "Videos"
        if not base.exists():
            base = Path.home()
        return str(base / ("ReelForge_%s.mp4" % time.strftime("%Y%m%d_%H%M%S")))

    def _pick_output(self):
        f = filedialog.asksaveasfilename(title="Guardar reel como", defaultextension=".mp4",
                                         initialfile=Path(self.var("output").get() or "reel.mp4").name,
                                         filetypes=[("MP4", "*.mp4")])
        if f:
            self.var("output").set(f)

    def _pick_color(self):
        c = colorchooser.askcolor(color=self.var("text_color").get(), title="Color del texto")
        if c and c[1]:
            self.var("text_color").set(c[1].upper())

    def _pick_font(self):
        f = filedialog.askopenfilename(title="Fuente TrueType", filetypes=[("Fuentes", "*.ttf *.otf"), ("Todos", "*.*")])
        if f:
            self.var("font_path").set(f)

    def _apply_preset(self, name):
        p = STYLE_PRESETS.get(name)
        if not p:
            return
        self.apply_dict(p)
        self.preset_info.configure(text=PRESET_INFO.get(name, ""))

    # ------------------------------------------------------------ ajustes
    def _save_dialog(self):
        f = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Ajustes", "*.json")],
                                         initialfile="mis_ajustes.json")
        if f:
            Path(f).write_text(self.collect().to_json(), encoding="utf-8")
            self._log("Ajustes guardados en %s" % f)

    def _load_dialog(self):
        f = filedialog.askopenfilename(filetypes=[("Ajustes", "*.json")])
        if f:
            try:
                self._apply_loaded(json.loads(Path(f).read_text(encoding="utf-8")))
                self._log("Ajustes cargados.")
            except Exception as e:
                messagebox.showerror("ReelForge", "No se pudo cargar: %s" % e)

    def _apply_loaded(self, d):
        d = dict(d)
        vids = d.pop("videos", None)
        d.pop("preview", None)
        self.apply_dict(d)
        if isinstance(vids, list):
            self._paths[:] = [v for v in vids if Path(v).exists()]
            self._refresh_list()

    def _load_settings(self):
        try:
            p = settings_file()
            if p.exists():
                d = json.loads(p.read_text(encoding="utf-8"))
                d.pop("output", None)
                self._apply_loaded(d)
        except Exception:
            pass

    def _on_close(self):
        try:
            settings_file().write_text(self.collect().to_json(), encoding="utf-8")
        except Exception:
            pass
        if self.engine:
            self.engine.cancel()
        self.destroy()

    # ------------------------------------------------------------ ejecucion
    def _log(self, msg):
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")

    def _set_busy(self, busy):
        self._busy = busy
        st = "disabled" if busy else "normal"
        for b in (self.btn_go, self.btn_preview, self.btn_analyze):
            b.configure(state=st)
        self.btn_cancel.configure(state="normal" if busy else "disabled")

    def _post(self, *msg):
        self.q.put(msg)

    def _poll(self):
        try:
            while True:
                m = self.q.get_nowait()
                kind = m[0]
                if kind == "log":
                    self._log(m[1])
                elif kind == "progress":
                    self.bar.set(max(0.0, min(1.0, m[1])))
                    self.pct.configure(text="%d %%" % int(m[1] * 100))
                    if m[2]:
                        self.status.configure(text=m[2])
                elif kind == "done":
                    self._set_busy(False)
                    self.status.configure(text="Listo")
                    self._log("TERMINADO: %s" % m[1])
                    if self.preview_mode:
                        open_path(m[1])
                    else:
                        self.last_output = m[1]
                        self.var("output").set(self._new_output_name())
                        if messagebox.askyesno("ReelForge", "Reel terminado.\n\n%s\n\nQuieres verlo ahora?" % m[1]):
                            open_path(m[1])
                elif kind == "error":
                    self._set_busy(False)
                    self.status.configure(text="Error")
                    self._log("ERROR: %s" % m[1])
                    messagebox.showerror("ReelForge", str(m[1])[:1200])
                elif kind == "info":
                    self._set_busy(False)
                    self.status.configure(text="Listo")
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _make_engine(self, preview):
        st = self.collect()
        st.preview = preview
        if preview:
            st.output = str(Path(tempfile.gettempdir()) / "reelforge_preview.mp4")
        return Engine(st, log=lambda m: self._post("log", m),
                      progress=lambda p, m="": self._post("progress", p, m))

    def _start(self, preview):
        if self._busy:
            return
        self.preview_mode = preview
        self.bar.set(0)
        self.pct.configure(text="0 %")
        try:
            self.engine = self._make_engine(preview)
        except EngineError as e:
            messagebox.showerror("ReelForge", str(e))
            return
        self._set_busy(True)
        self._log("--- %s ---" % ("Vista previa" if preview else "Generando reel"))

        def work():
            try:
                out = self.engine.run()
                self._post("done", out)
            except EngineError as e:
                self._post("error", str(e))
            except Exception as e:  # noqa
                import traceback
                self._post("error", "Error inesperado: %s\n%s" % (e, traceback.format_exc()[-900:]))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _analyze(self):
        if self._busy:
            return
        a = self.var("audio").get()
        if not a or not Path(a).exists():
            messagebox.showinfo("ReelForge", "Primero selecciona un audio.")
            return
        try:
            self.engine = self._make_engine(False)
        except EngineError as e:
            messagebox.showerror("ReelForge", str(e))
            return
        self._set_busy(True)
        self.status.configure(text="Analizando audio...")

        def work():
            try:
                info = self.engine.analyze_audio()
                a0, dur = self.engine._choose_window(info)
                self._post("log", "Sugerencia: usar desde %.1fs durante %.1fs" % (a0, dur))
                self._post("info")
            except EngineError as e:
                self._post("error", str(e))
            except Exception as e:  # noqa
                self._post("error", "Error inesperado: %s" % e)

        threading.Thread(target=work, daemon=True).start()

    def _cancel(self):
        if self.engine:
            self.engine.cancel()
            self._log("Cancelando...")


def run():
    app = App()
    app.mainloop()
