"""Ajustes del proyecto y presets de estilo."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields

CUT_MODES = ["Auto (segun energia)", "Cada 1/2 beat", "Cada beat", "Cada 2 beats", "Cada 4 beats"]
SLOWMO_MODES = ["Off", "Blend (rapido)", "Interpolacion (lento)"]
FIT_MODES = ["Rellenar (recorte)", "Fondo desenfocado"]
ORDER_MODES = ["Aleatorio sin repetir", "Secuencial"]
RESOLUTIONS = ["1080x1920", "720x1280", "1440x2560"]
FPS_LIST = ["30", "60", "24"]
ENCODERS = ["CPU (x264)", "NVIDIA (NVENC)", "AMD (AMF)", "Intel (QSV)"]
QUALITIES = ["Alta", "Maxima", "Media (rapida)"]
TITLE_POS = ["Centro", "Arriba", "Abajo"]
LOOK_NAMES = ["Ninguno", "Cine (teal & orange)", "Noir contraste", "Neon cyberpunk", "Anime vivido",
              "Retro VHS", "Dorado calido", "Frio helado", "Sueno (glow)", "Comic / Arte", "Boceto tinta",
              "Vintage 35mm", "Matrix verde", "Atardecer magenta", "Infrarrojo", "Pastel suave"]
OUTLINE_MODES = ["Off", "En golpes", "Siempre"]
OUTLINE_COLORS = ["Auto (cicla)", "Cian", "Magenta", "Naranja", "Lima", "Blanco"]


@dataclass
class Settings:
    # entradas
    videos: list = field(default_factory=list)
    audio: str = ""
    output: str = ""
    # tiempo
    audio_start: float = 0.0
    max_duration: float = 20.0
    auto_best_part: bool = True
    cut_mode: str = CUT_MODES[0]
    cut_density: int = 55
    clip_order: str = ORDER_MODES[0]
    # velocidad
    speed_curves: bool = True
    speed_intensity: int = 70
    base_speed: float = 1.15
    slowmo_smooth: str = SLOWMO_MODES[1]
    # camara
    fx_intensity: int = 70
    zoom_punch: bool = True
    camera_shake: bool = True
    roll_tilt: bool = True
    rgb_split: bool = True
    flash: bool = True
    camera_transitions: bool = True
    xfade_transitions: bool = True
    xfade_amount: int = 35
    # look / arte
    look: str = LOOK_NAMES[1]
    grain: bool = True
    vignette: bool = True
    art_effects: bool = True
    art_amount: int = 35
    # fuego / overlays
    fire: bool = True
    fire_amount: int = 55
    light_leaks: bool = True
    user_overlays: bool = True
    overlay_amount: int = 60
    sparks: bool = True
    smoke: bool = True
    flare: bool = True
    shine: bool = True
    bokeh: bool = True
    dust: bool = True
    rain: bool = False
    # efectos extra de camara
    extra_fx_amount: int = 45
    ghost_trails: bool = True
    mirror_fx: bool = True
    pixel_fx: bool = True
    slice_glitch: bool = True
    zoom_blur: bool = True
    strobe_fx: bool = True
    hue_pulse: bool = True
    # bordeado neon
    outline_mode: str = OUTLINE_MODES[1]
    outline_color: str = OUTLINE_COLORS[0]
    outline_strength: int = 70
    # texto
    title_text: str = ""
    title_pos: str = TITLE_POS[0]
    title_seconds: float = 2.5
    kinetic_words: str = ""
    text_color: str = "#FFFFFF"
    text_size: int = 120
    font_path: str = ""
    # salida
    resolution: str = RESOLUTIONS[0]
    fps: str = FPS_LIST[0]
    fit_mode: str = FIT_MODES[0]
    encoder: str = ENCODERS[0]
    quality: str = QUALITIES[0]
    seed: int = 0
    preview: bool = False

    def to_json(self):
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d):
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


# Cada preset sobrescribe solo estos campos
STYLE_PRESETS = {
    "Equilibrado (recomendado)": dict(
        overlay_amount=55, extra_fx_amount=45, outline_mode="En golpes", outline_strength=65, sparks=True, smoke=True, flare=True, shine=True, bokeh=True, dust=True, rain=False, strobe_fx=False, slice_glitch=True, pixel_fx=True, zoom_blur=True, ghost_trails=True, mirror_fx=True, hue_pulse=True,
        cut_mode=CUT_MODES[0], cut_density=55, speed_intensity=70, base_speed=1.15, fx_intensity=70,
        look="Cine (teal & orange)", fire=True, fire_amount=45, art_effects=True, art_amount=30,
        xfade_transitions=True, xfade_amount=30, light_leaks=True, flash=True, camera_shake=True),
    "Cinematico suave": dict(
        overlay_amount=60, extra_fx_amount=15, outline_mode="Off", outline_strength=50, sparks=False, smoke=True, flare=True, shine=True, bokeh=True, dust=True, rain=False, strobe_fx=False, slice_glitch=False, pixel_fx=False, zoom_blur=True, ghost_trails=True, mirror_fx=False, hue_pulse=False,
        cut_mode=CUT_MODES[3], cut_density=25, speed_intensity=45, base_speed=1.0, fx_intensity=40,
        look="Dorado calido", fire=False, fire_amount=0, art_effects=False, art_amount=0,
        xfade_transitions=True, xfade_amount=65, light_leaks=True, flash=False, camera_shake=False),
    "Energetico / TikTok": dict(
        overlay_amount=60, extra_fx_amount=60, outline_mode="En golpes", outline_strength=75, sparks=True, smoke=False, flare=True, shine=True, bokeh=True, dust=False, rain=False, strobe_fx=True, slice_glitch=True, pixel_fx=True, zoom_blur=True, ghost_trails=True, mirror_fx=True, hue_pulse=True,
        cut_mode=CUT_MODES[0], cut_density=75, speed_intensity=85, base_speed=1.25, fx_intensity=85,
        look="Anime vivido", fire=True, fire_amount=40, art_effects=True, art_amount=35,
        xfade_transitions=True, xfade_amount=15, light_leaks=True, flash=True, camera_shake=True),
    "Phonk / Agresivo": dict(
        overlay_amount=70, extra_fx_amount=85, outline_mode="Siempre", outline_strength=70, sparks=True, smoke=True, flare=False, shine=False, bokeh=False, dust=True, rain=False, strobe_fx=True, slice_glitch=True, pixel_fx=True, zoom_blur=True, ghost_trails=True, mirror_fx=True, hue_pulse=True,
        cut_mode=CUT_MODES[0], cut_density=90, speed_intensity=100, base_speed=1.35, fx_intensity=100,
        look="Noir contraste", fire=True, fire_amount=70, art_effects=True, art_amount=55,
        xfade_transitions=False, xfade_amount=0, light_leaks=False, flash=True, camera_shake=True),
    "Fuego total": dict(
        overlay_amount=75, extra_fx_amount=55, outline_mode="En golpes", outline_color="Naranja", outline_strength=80, sparks=True, smoke=True, flare=True, shine=False, bokeh=False, dust=True, rain=False, strobe_fx=False, slice_glitch=False, pixel_fx=False, zoom_blur=True, ghost_trails=True, mirror_fx=False, hue_pulse=False,
        cut_mode=CUT_MODES[2], cut_density=80, speed_intensity=90, base_speed=1.2, fx_intensity=95,
        look="Dorado calido", fire=True, fire_amount=100, art_effects=True, art_amount=40,
        xfade_transitions=False, xfade_amount=0, light_leaks=False, flash=True, camera_shake=True),
    "Cyberpunk neon": dict(
        overlay_amount=60, extra_fx_amount=75, outline_mode="Siempre", outline_color="Auto (cicla)", outline_strength=85, sparks=False, smoke=True, flare=True, shine=True, bokeh=True, dust=False, rain=True, strobe_fx=True, slice_glitch=True, pixel_fx=True, zoom_blur=True, ghost_trails=True, mirror_fx=True, hue_pulse=True,
        cut_mode=CUT_MODES[0], cut_density=70, speed_intensity=80, base_speed=1.2, fx_intensity=85,
        look="Neon cyberpunk", fire=False, fire_amount=0, art_effects=True, art_amount=60,
        xfade_transitions=True, xfade_amount=25, light_leaks=True, flash=True, camera_shake=True),
}
