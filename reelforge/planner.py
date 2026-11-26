"""Planificador: decide cortes, curvas de velocidad, efectos y transiciones segun la musica."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np

GROUP_SIZE = 12  # segmentos por grupo de ensamblado (frontera de grupo = corte seco)

XFADE_PREFERRED = ["fade", "fadewhite", "fadeblack", "slideleft", "slideright", "slideup", "smoothleft",
                   "smoothright", "circleopen", "circleclose", "radial", "wipeleft", "wiperight",
                   "zoomin", "distance", "pixelize", "hblur", "horzopen", "diagtl", "dissolve"]


@dataclass
class Ov:
    path: str
    kind: str = "fire"
    mode: str = "full"        # start (se apaga) | end (se enciende) | full
    d: float = 0.7
    opacity: float = 1.0
    flip: bool = False
    ss: float = 0.0


OUTLINE_HEX = {"Cian": "00E5FF", "Magenta": "FF2BD6", "Naranja": "FF7A1A", "Lima": "9DFF2B", "Blanco": "FFFFFF"}
OUTLINE_CYCLE = ["00E5FF", "FF2BD6", "FF7A1A", "9DFF2B"]


@dataclass
class Seg:
    i: int
    t0: float                 # inicio del corte en la linea de tiempo final
    L: float                  # duracion nominal (entre beats)
    I: float = 0.5            # intensidad 0..1
    e: float = 0.5            # energia de la seccion 0..1
    hit: bool = False
    drop: bool = False
    # fuente
    clip: int = 0
    src_start: float = 0.0
    S: float = 1.0
    R: float = 1.0            # duracion renderizada (incluye solapes de xfade)
    h_in: float = 0.0
    h_out: float = 0.0
    # velocidad
    k: int = 0
    a: float = 0.0
    speed: float = 1.0
    smooth: str = ""
    # camara
    punch: float = 0.0
    punch_k: float = 7.0
    push: float = 0.0
    shake: float = 0.0
    roll: float = 0.0
    rgb: int = 0
    flash: float = 0.0
    head: str = "none"
    head_dir: int = 1
    tail: str = "none"
    tail_dir: int = 1
    tail_len: float = 0.16
    art: str = ""
    ghost: bool = False
    hue: bool = False
    strobe: float = 0.0
    outline: str = ""
    outline_s: float = 0.7
    # overlays (hasta 2)
    ovs: list = field(default_factory=list)
    # texto
    word: str = ""
    # union con el siguiente
    xfade: str = ""
    xfade_d: float = 0.0
    nframes: int = 0


def _choose_cuts(info, st, win_start, dur, rng):
    """Devuelve lista de (tiempo_local, fuerza, es_drop) para cada corte, empezando en 0."""
    beats = info.beats
    sel = (beats >= win_start - 0.02) & (beats <= win_start + dur + 0.02)
    b = beats[sel] - win_start
    s = info.strength[sel]
    if len(b) < 2:  # sin beats fiables: rejilla segun BPM
        step = 60.0 / max(60.0, info.bpm)
        b = np.arange(0, dur + step, step)
        s = np.full(len(b), 0.5)
    b = b - b[0]
    drops = [d - win_start for d in info.drops if win_start <= d <= win_start + dur]

    mode = st.cut_mode
    dens = st.cut_density / 100.0
    cuts = [(0.0, float(s[0]), False)]
    i = 0
    n = len(b)
    while i < n - 1:
        t = b[i]
        e = info.energy_at(win_start + t)
        near_drop = any(abs(t - d) < 0.5 for d in drops)
        if mode.startswith("Cada 1/2"):
            step = 0.5
        elif mode == "Cada beat":
            step = 1
        elif mode == "Cada 2 beats":
            step = 2
        elif mode == "Cada 4 beats":
            step = 4
        else:
            ee = float(np.clip(e + (dens - 0.5) * 0.7, 0, 1))
            after_drop = any(0 <= t - d < 6.0 for d in drops)
            if ee < 0.28:
                step = 4
            elif ee < 0.50:
                step = 2
            elif ee < 0.80 or not (after_drop or dens > 0.85):
                step = 1
            else:
                step = 0.5
        if step == 0.5:
            j = min(i + 1, n - 1)
            cuts.append(((b[i] + b[j]) / 2.0, float(s[i]) * 0.6, False))
            nxt = j
            if j > i:
                cuts.append((b[j], float(s[j]), False))
            i = nxt
        else:
            i = min(n - 1, i + int(step))
            cuts.append((float(b[i]), float(s[i]), any(abs(b[i] - d) < 0.35 for d in drops)))
        _ = near_drop
    # quitar cortes demasiado juntos / pasados
    out = [cuts[0]]
    for c in cuts[1:]:
        if c[0] - out[-1][0] >= 0.26 and c[0] < dur - 0.2:
            out.append(c)
    return out, drops


def plan(info, st, clips, win_start, dur, overlays, rng, xfade_ok, fps=30, log=None):
    """Genera la lista de segmentos con todas las decisiones."""
    cuts, drops = _choose_cuts(info, st, win_start, dur, rng)
    q = lambda x: round(x * fps) / float(fps)        # cuantizar a fotogramas: evita desfase acumulado
    times = [q(c[0]) for c in cuts] + [q(dur)]
    keep = [0] + [k for k in range(1, len(times)) if times[k] - times[k - 1] >= 2.0 / fps]
    if keep[-1] != len(times) - 1:
        keep[-1] = len(times) - 1
    cuts = [cuts[k] for k in keep[:-1]]
    times = [times[k] for k in keep]
    segs = []
    F = st.fx_intensity / 100.0
    words = [w for w in st.kinetic_words.replace(",", " ").split() if w]

    for i, (_t, strength, is_drop) in enumerate(cuts):
        t = times[i]
        L = times[i + 1] - t
        e = info.energy_at(win_start + t)
        I = float(np.clip(0.65 * e + 0.35 * strength, 0, 1))
        hit = bool(is_drop or (strength > 0.9 and e > 0.45) or (i == 0))
        sg = Seg(i=i, t0=t, L=L, I=I, e=float(e), hit=hit, drop=is_drop)
        if words:
            sg.word = words[i % len(words)].upper()
        segs.append(sg)
    n = len(segs)

    # ---------- transiciones suaves (xfade) en zonas tranquilas
    xf_names = [x for x in XFADE_PREFERRED if x in xfade_ok] or []
    if st.xfade_transitions and xf_names:
        for i in range(n - 1):
            sg = segs[i]
            if (i + 1) % GROUP_SIZE == 0:
                continue
            nx = segs[i + 1]
            if sg.L >= 0.7 and nx.L >= 0.7 and sg.e < 0.5 and nx.e < 0.55 and not nx.drop and not sg.drop \
                    and rng.random() < st.xfade_amount / 100.0 * (1.25 - sg.e):
                hf = max(2, int(round(min(0.4, 0.45 * min(sg.L, segs[i + 1].L)) * fps / 2.0)))
                h = hf / float(fps)
                sg.xfade = rng.choice(xf_names[:12] if sg.I < 0.35 else xf_names)
                sg.xfade_d = 2 * h
                sg.h_out = h
                segs[i + 1].h_in = h

    # ---------- transiciones de camara (en cortes secos)
    kinds = ["zoom", "whip", "roll", "glitch", "flash", "zoom", "whip"]
    if not st.roll_tilt:
        kinds = [k for k in kinds if k != "roll"]
    if not st.flash:
        kinds = [k for k in kinds if k != "flash"]
    extra_kinds = []
    if st.pixel_fx:
        extra_kinds += ["pixel", "pixel"]
    if st.slice_glitch:
        extra_kinds += ["slice", "slice"]
    if st.zoom_blur:
        extra_kinds += ["zblur", "zblur"]
    if st.strobe_fx:
        extra_kinds += ["strobe"]
    E = st.extra_fx_amount / 100.0
    prev_tail = "none"
    for i, sg in enumerate(segs):
        nxt = segs[i + 1] if i + 1 < n else None
        if st.camera_transitions and nxt is not None and not sg.xfade and F > 0 \
                and rng.random() < 0.15 + 0.7 * F * max(sg.I, nxt.I):
            if extra_kinds and (not kinds or rng.random() < 0.2 + 0.65 * E):
                sg.tail = rng.choice(extra_kinds)
            else:
                sg.tail = rng.choice(kinds or ["zoom"])
            sg.tail_dir = rng.choice([-1, 1])
            sg.tail_len = float(min(0.2, 0.45 * sg.L))
            nxt.head = sg.tail
            nxt.head_dir = sg.tail_dir
        if sg.xfade:
            sg.tail = "none"

    # ---------- efectos por segmento
    for i, sg in enumerate(segs):
        I = sg.I
        has_xin = i > 0 and segs[i - 1].xfade
        if st.zoom_punch and not has_xin and sg.head == "none" and F > 0 \
                and rng.random() < 0.45 + 0.5 * I:
            sg.punch = float(F * (0.05 + 0.17 * I) * (1.4 if sg.hit else 1.0))
            sg.punch_k = 6.0 + 4.0 * I
        elif sg.head in ("zoom", "whip") and st.zoom_punch:
            pass
        if I < 0.45 and sg.L > 0.8 and F > 0:
            sg.push = float(F * 0.09 * (1 - I))
        if st.camera_shake and not has_xin and I > 0.55 and F > 0 and rng.random() < 0.7:
            sg.shake = float(F * (10 + 26 * I) * (1.3 if sg.hit else 1.0))
        if st.roll_tilt and not has_xin and I > 0.6 and sg.head == "none" and F > 0 and rng.random() < 0.35:
            sg.roll = float(F * (0.02 + 0.05 * I))
        if st.rgb_split and not has_xin and F > 0 and (I > 0.45 or sg.hit) and rng.random() < 0.65:
            sg.rgb = int(F * (6 + 16 * I) + 2)
        if st.flash and not has_xin and F > 0 and (sg.drop or (sg.hit and rng.random() < 0.45)):
            sg.flash = float(F * (0.18 + 0.4 * I))
        xin_or_out = bool(sg.xfade) or has_xin
        pool = ["comic", "sketch", "posterize", "duotone", "thermal", "glow", "negative"] if st.art_effects else []
        if pool and st.art_amount > 0 and (sg.hit or I > 0.78) and not sg.xfade \
                and rng.random() < st.art_amount / 100.0 * (0.4 + 0.6 * I):
            sg.art = rng.choice(pool)
        elif st.mirror_fx and not xin_or_out and (sg.hit or I > 0.8) and rng.random() < E * 0.3 * (0.5 + I):
            sg.art = rng.choice(["mirror", "kaleido"])
        if st.ghost_trails and not xin_or_out and (sg.hit or I > 0.7) and rng.random() < E * 0.7:
            sg.ghost = True
        if st.hue_pulse and not xin_or_out and sg.hit and rng.random() < E * 0.5:
            sg.hue = True
        if st.strobe_fx and sg.drop and not has_xin:
            sg.strobe = 0.22
        if st.outline_mode != "Off" and not xin_or_out and F >= 0:
            on = st.outline_mode == "Siempre" or ((sg.hit or I > 0.72) and rng.random() < 0.35 + 0.5 * I)
            if on:
                sg.outline = OUTLINE_HEX.get(st.outline_color) or OUTLINE_CYCLE[(i + (1 if sg.drop else 0)) % 4]
                sg.outline_s = st.outline_strength / 100.0

    # ---------- velocidad
    for i, sg in enumerate(segs):
        I = sg.I
        base = st.base_speed * (0.85 + 0.35 * I) if sg.L < 4 else 1.0
        sg.speed = float(max(0.6, base))
        if st.speed_curves and st.speed_intensity > 0 and sg.L >= 0.35:
            amp = st.speed_intensity / 100.0
            if I < 0.3:
                pool = [(0, 0.0, 2), (2, 0.55, 2), (1, 0.5, 2)]
            elif sg.drop or I > 0.8:
                pool = [(1, -0.88, 4), (2, 0.9, 4), (2, -0.85, 3), (4, 0.8, 2), (1, 0.85, 2), (0, 0.0, 1)]
            else:
                pool = [(2, 0.8, 3), (1, 0.8, 2), (1, -0.8, 2), (2, -0.7, 2), (0, 0.0, 1), (4, 0.7, 1)]
            ws = [p[2] for p in pool]
            k, a, _ = rng.choices(pool, weights=ws, k=1)[0]
            sg.k, sg.a = k, float(np.clip(a * amp, -0.93, 0.93))

    _plan_overlays(segs, st, overlays, rng)

    # ---------- duraciones renderizadas
    for sg in segs:
        sg.nframes = int(round((sg.L + sg.h_in + sg.h_out) * fps))
        sg.R = sg.nframes / float(fps)

    # ---------- eleccion de fuente
    _assign_sources(segs, clips, st, rng)
    # modo de suavizado en slow-mo
    for sg in segs:
        if sg.k and abs(sg.a) > 0.2:
            slowest = 1.0 / (1.0 + abs(sg.a)) * sg.speed
            if slowest < 0.75:
                sg.smooth = {"Blend (rapido)": "blend", "Interpolacion (lento)": "mci"}.get(st.slowmo_smooth, "")
    if log:
        xf = sum(1 for s in segs if s.xfade)
        fire = sum(1 for s in segs if s.ovs)
        log("Plan: %d cortes | %d transiciones suaves | %d con overlays | %d con arte | %d con bordeado | %d con curva"
            % (n, xf, fire, sum(1 for s in segs if s.art), sum(1 for s in segs if s.outline),
               sum(1 for s in segs if s.k)))
    return segs


def _assign_sources(segs, clips, st, rng):
    ncl = len(clips)
    used = [[] for _ in range(ncl)]
    cursor = [0.0] * ncl
    order = list(range(ncl))
    rng.shuffle(order)
    seq = st.clip_order.startswith("Sec")
    for idx, sg in enumerate(segs):
        c = order[idx % ncl] if not seq else (idx // max(1, len(segs) // ncl + 1)) % ncl
        if not seq and ncl > 1 and idx > 0 and c == segs[idx - 1].clip:
            c = order[(idx + 1) % ncl]
        clip = clips[c]
        S = sg.R * sg.speed
        dur = clip["duration"]
        if clip["is_image"]:
            S = sg.R
            sg.k, sg.a = 0, 0.0
            sg.src_start = 0.0
        else:
            if S > dur - 0.1:
                S = max(0.3, dur - 0.1)
            span = max(0.0, dur - S - 0.05)
            if seq:
                start = cursor[c] if cursor[c] <= span else 0.0
                cursor[c] = start + S
            else:
                start = rng.random() * span
                for _ in range(24):
                    cand = rng.random() * span
                    if all(cand + S < u0 or cand > u1 for u0, u1 in used[c]):
                        start = cand
                        break
                else:
                    used[c] = []
                used[c].append((start, start + S))
            sg.src_start = float(start)
        sg.clip = c
        sg.S = float(S)


def _plan_overlays(segs, st, overlays, rng):
    """Reparte overlays (hasta 2 por corte) segun la energia; crea 'puentes' de humo/fuego/luz entre cortes."""
    n = len(segs)
    amt = st.overlay_amount / 100.0
    enabled = {}
    if st.fire and "fire" in overlays:
        enabled["fire"] = st.fire_amount / 100.0
    for k, flag in (("leak", st.light_leaks), ("smoke", st.smoke), ("sparks", st.sparks), ("shine", st.shine),
                    ("flare", st.flare), ("bokeh", st.bokeh), ("dust", st.dust), ("rain", st.rain)):
        if flag and k in overlays:
            enabled[k] = 1.0
    user = overlays.get("user") or []
    if st.user_overlays and user:
        enabled["user"] = 1.0

    W_HI = {"fire": 3.0, "sparks": 2.5, "flare": 2.0, "user": 2.0, "shine": 1.0, "rain": 0.5, "smoke": 0.5, "leak": 0.5}
    W_MID = {"leak": 1.5, "shine": 2.0, "smoke": 1.5, "bokeh": 1.0, "rain": 0.8, "flare": 1.0, "sparks": 1.0,
             "user": 1.0, "dust": 1.0, "fire": 1.0}
    W_LO = {"smoke": 2.5, "bokeh": 2.5, "dust": 2.0, "leak": 2.0, "shine": 1.5, "rain": 1.0, "flare": 0.5}

    def make(kind, sg, mode=None):
        o = Ov(path=overlays[kind] if kind != "user" else rng.choice(user), kind=kind)
        o.flip = rng.random() < 0.5
        o.ss = rng.random() * 2.0
        hit = sg.hit or sg.drop
        if kind == "fire":
            o.mode, o.d, o.opacity = ("start", min(sg.L * 0.9, 0.9), 1.0) if (sg.drop or sg.I > 0.7) \
                else ("end", min(sg.L * 0.8, 0.55), 1.0)
        elif kind == "sparks":
            o.mode, o.d, o.opacity = ("start", min(sg.L, 1.2), 1.0) if hit else ("full", sg.L, 0.9)
        elif kind == "flare":
            o.mode, o.d, o.opacity = ("start", min(sg.L * 0.9, 0.6), 0.95) if hit else ("full", sg.L, 0.8)
        elif kind == "shine":
            o.mode, o.d, o.opacity, o.ss = "full", sg.L, 0.8, 0.35 + rng.random() * 0.5
        elif kind == "smoke":
            o.mode, o.d, o.opacity = "full", sg.L, 0.55
        elif kind == "bokeh":
            o.mode, o.d, o.opacity = "full", sg.L, 0.75
        elif kind == "dust":
            o.mode, o.d, o.opacity = "full", sg.L, 0.7
        elif kind == "rain":
            o.mode, o.d, o.opacity = "full", sg.L, 0.6
        elif kind == "leak":
            o.mode, o.d, o.opacity = "full", sg.L, 0.55
        elif kind == "user":
            o.mode, o.d, o.opacity, o.ss = "full", sg.L, 0.9, 0.0
        if mode:
            o.mode = mode
        return o

    if not enabled:
        return
    for i, sg in enumerate(segs):
        if sg.L < 0.4:
            continue
        nxt = segs[i + 1] if i + 1 < n else None
        base = W_HI if (sg.drop or sg.I > 0.7) else (W_LO if sg.I < 0.4 else W_MID)
        cand = [(k, base.get(k, 0.4) * (enabled[k] if k == "fire" else 1.0)) for k in enabled]
        cand = [(k, w) for k, w in cand if w > 0]
        if not cand:
            continue
        p_any = min(0.95, amt * (0.35 + 0.75 * sg.I))
        if sg.drop and "fire" in enabled:
            first = "fire"
        elif rng.random() < p_any:
            first = rng.choices([c[0] for c in cand], weights=[c[1] for c in cand], k=1)[0]
        else:
            continue
        sg.ovs.append(make(first, sg))
        # puente entre cortes (solo si no hay xfade): el efecto "atraviesa" el corte
        if first in ("fire", "smoke", "flare", "leak") and nxt is not None and not sg.xfade and nxt.L > 0.45 \
                and sg.L > 0.45 and not nxt.ovs and rng.random() < 0.45:
            sg.ovs[0].mode = "end"
            sg.ovs[0].d = min(sg.L * 0.8, 0.55)
            if first == "smoke" or first == "leak":
                sg.ovs[0].opacity = max(sg.ovs[0].opacity, 0.8)
            nov = make(first, nxt, "start")
            nov.d = min(nxt.L * 0.8, 0.6)
            nov.flip = not sg.ovs[0].flip
            nov.opacity = sg.ovs[0].opacity
            nxt.ovs.append(nov)
        # segundo overlay complementario
        if rng.random() < 0.3 * amt:
            comp = {"fire": ["sparks"], "sparks": ["smoke", "dust"], "smoke": ["shine", "dust"],
                    "flare": ["dust"], "shine": ["dust", "bokeh"], "bokeh": ["dust"]}.get(first, ["dust"])
            comp = [c for c in comp if c in enabled and c != first]
            if comp:
                sg.ovs.append(make(rng.choice(comp), sg))
