"""Constructor de filtros FFmpeg para un segmento: velocidad, camara, looks, arte, fuego, texto."""
from __future__ import annotations


def f(x):
    s = ("%.5f" % float(x)).rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def neg(x):
    return "(%s)" % f(x)


class Graph:
    """Cadena lineal de filtros con etiquetas automaticas (permite ramas split/blend)."""

    def __init__(self, src):
        self.parts = []
        self.cur = src
        self.n = 0

    def _new(self):
        self.n += 1
        return "v%d" % self.n

    def add(self, flt):
        out = self._new()
        self.parts.append("[%s]%s[%s]" % (self.cur, flt, out))
        self.cur = out

    def branch_blend(self, branch, mode, opacity=1.0, pre="", post=""):
        """cur -> split -> (rama procesada) -> blend con el original."""
        a, b, c, o = self._new(), self._new(), self._new(), self._new()
        self.parts.append("[%s]split[%s][%s]" % (self.cur, a, b))
        self.parts.append("[%s]%s[%s]" % (b, branch, c))
        pa = a
        if pre:
            pa2 = self._new()
            self.parts.append("[%s]%s[%s]" % (a, pre, pa2))
            pa = pa2
        self.parts.append("[%s][%s]blend=all_mode=%s:all_opacity=%s%s[%s]"
                          % (pa, c, mode, f(opacity), post, o))
        self.cur = o

    def branch_overlay(self, branch, enable):
        """Muestra una version procesada del fotograma solo mientras `enable` sea verdadero."""
        a, b, c, o = self._new(), self._new(), self._new(), self._new()
        self.parts.append("[%s]split[%s][%s]" % (self.cur, a, b))
        self.parts.append("[%s]%s[%s]" % (b, branch, c))
        self.parts.append("[%s][%s]overlay=0:0:enable='%s'[%s]" % (a, c, enable, o))
        self.cur = o

    def raw(self, text, out):
        self.parts.append(text)
        self.cur = out

    def render(self):
        return ";".join(self.parts)


def hex_to_ff(color):
    c = (color or "#FFFFFF").strip().lstrip("#")
    if len(c) != 6:
        c = "FFFFFF"
    return "0x" + c.upper()


# ---------------------------------------------------------------- looks
LOOK_CHAINS = {
    "Cine (teal & orange)": "colorbalance=rs=-0.08:gs=-0.02:bs=0.12:rm=0.04:bm=-0.04:rh=0.12:gh=0.03:bh=-0.10,"
                            "eq=contrast=1.12:saturation=1.18:gamma=0.97",
    "Noir contraste": "hue=s=0,eq=contrast=1.45:brightness=-0.03:gamma=0.95",
    "Neon cyberpunk": "colorbalance=rs=0.10:gs=-0.08:bs=0.18:rh=0.18:gh=-0.06:bh=0.12,eq=saturation=1.55:contrast=1.15",
    "Anime vivido": "eq=saturation=1.65:contrast=1.14:gamma=0.95,unsharp=5:5:0.9:5:5:0.0",
    "Retro VHS": "curves=preset=vintage,eq=saturation=1.25:contrast=1.08,chromashift=crh=3:cbh=-3,noise=alls=14:allf=t",
    "Dorado calido": "colorbalance=rs=0.14:gs=0.04:bs=-0.12:rm=0.08:bm=-0.06,eq=saturation=1.3:contrast=1.08",
    "Frio helado": "colorbalance=rs=-0.12:bs=0.16:rm=-0.05:bm=0.10,eq=saturation=1.1:contrast=1.1",
    "Vintage 35mm": "curves=preset=vintage,eq=saturation=0.85:contrast=1.05,colorbalance=rs=0.05:bs=-0.05,"
                    "noise=alls=10:allf=t",
    "Matrix verde": "hue=s=0.35,colorbalance=rs=-0.2:gs=0.25:bs=-0.2:rm=-0.1:gm=0.2:bm=-0.1,eq=contrast=1.25:saturation=1.2",
    "Atardecer magenta": "colorbalance=rs=0.2:gs=-0.1:bs=0.16:rm=0.12:bm=0.05,eq=saturation=1.35:contrast=1.08",
    "Infrarrojo": "colorchannelmixer=rr=0:rb=1:br=1:bb=0,hue=h=-35:s=1.3",
    "Pastel suave": "eq=saturation=0.8:brightness=0.06:contrast=0.9:gamma=1.1,colorbalance=bs=0.05:rs=0.03",
}

ART_KINDS = ["comic", "sketch", "posterize", "duotone", "thermal", "glow", "negative"]
ART_MIRROR = ["mirror", "kaleido"]


def _apply_art(g, kind, R):
    q = "trunc(val/44)*44+20"
    if kind == "comic":
        g.branch_blend("edgedetect=low=0.08:high=0.24,negate,format=gbrp", "multiply", 1.0,
                       pre="eq=saturation=1.8:contrast=1.15,format=gbrp,lutrgb=r='%s':g='%s':b='%s'" % (q, q, q))
    elif kind == "sketch":
        g.branch_blend("edgedetect=low=0.06:high=0.2,negate,format=gbrp", "multiply", 1.0,
                       pre="hue=s=0,eq=contrast=1.15,format=gbrp")
        g.add("eq=contrast=1.25")
    elif kind == "posterize":
        g.add("eq=saturation=1.9:contrast=1.15,format=gbrp,lutrgb=r='%s':g='%s':b='%s'" % (q, q, q))
    elif kind == "duotone":
        g.add("hue=s=0,curves=r='0/0.12 0.5/0.6 1/1':g='0/0 0.5/0.2 1/0.55':b='0/0.35 0.5/0.35 1/0.2'")
    elif kind == "thermal":
        g.add("eq=contrast=1.2,pseudocolor=preset=magma")
    elif kind == "glow":
        g.branch_blend("gblur=sigma=20,eq=brightness=-0.04", "screen", 0.55)
    elif kind == "negative":
        g.add("negate=enable='lt(t,0.12)'")
    elif kind == "mirror":
        a, b, c, o = g._new(), g._new(), g._new(), g._new()
        g.parts.append("[%s]crop=iw/2:ih:0:0,split[%s][%s]" % (g.cur, a, b))
        g.parts.append("[%s]hflip[%s]" % (b, c))
        g.parts.append("[%s][%s]hstack[%s]" % (a, c, o))
        g.cur = o
    elif kind == "kaleido":
        a, b, c, o, p, q = g._new(), g._new(), g._new(), g._new(), g._new(), g._new()
        g.parts.append("[%s]crop=iw/2:ih:0:0,split[%s][%s]" % (g.cur, a, b))
        g.parts.append("[%s]hflip[%s]" % (b, c))
        g.parts.append("[%s][%s]hstack[%s]" % (a, c, o))
        g.parts.append("[%s]crop=iw:ih/2:0:0,split[%s][%s]" % (o, p, q))
        g.parts.append("[%s]vflip[%sv]" % (q, q))
        g.parts.append("[%s][%sv]vstack[%sk]" % (p, q, p))
        g.cur = "%sk" % p


def _even(x):
    return max(2, int(x) // 2 * 2)


def _outline(g, color, strength, W, H):
    """Bordeado neon: contornos fuertes (zona central) con halo oscuro, brillo y glow. Pulsa en cada corte."""
    c = (color or "00E5FF").lstrip("#")
    if len(c) != 6:
        c = "00E5FF"
    r, gg, b = [min(2.0, int(c[i:i + 2], 16) / 255.0 * 1.6) for i in (0, 2, 4)]
    st_ = max(0.0, min(1.0, strength))
    n = [g._new() for _ in range(12)]
    a, bb, m1, m2, cc, dd, ee, col, a2, a3, dk, o = n
    g.parts.append("[%s]split[%s][%s]" % (g.cur, a, bb))
    g.parts.append("[%s]scale=trunc(iw/4)*2:trunc(ih/4)*2,gblur=sigma=1.2,edgedetect=low=0.08:high=0.22,"
                   "gblur=sigma=2.4,curves=all='0/0 0.025/0.9 1/1',vignette=angle=PI/2.4,"
                   "eq=brightness='-0.12*(1-exp(-7*t))':eval=frame,scale=%d:%d:flags=bicubic,split[%s][%s]"
                   % (bb, W, H, m1, m2))
    g.parts.append("[%s]format=gbrp,lutrgb=r='clip(val*%s,0,255)':g='clip(val*%s,0,255)':b='clip(val*%s,0,255)',"
                   "split[%s][%s]" % (m1, f(r), f(gg), f(b), cc, dd))
    g.parts.append("[%s]gblur=sigma=11[%s]" % (dd, ee))
    g.parts.append("[%s][%s]blend=all_mode=lighten[%s]" % (cc, ee, col))
    g.parts.append("[%s]gblur=sigma=5,negate,format=gbrp[%s]" % (m2, dk))
    g.parts.append("[%s]format=gbrp[%s]" % (a, a2))
    g.parts.append("[%s][%s]blend=all_mode=multiply:all_opacity=%s[%s]" % (a2, dk, f(0.35 + 0.5 * st_), a3))
    g.parts.append("[%s][%s]blend=all_mode=screen:all_opacity=%s[%s]" % (a3, col, f(0.55 + 0.45 * st_), o))
    g.cur = o
    g.add("format=yuv420p")


def _win_effect(g, kind, en, W, H):
    """Efectos de transicion limitados a una ventana de tiempo `en` (expresion de enable)."""
    if kind == "pixel":
        g.branch_overlay("scale=%d:%d:flags=neighbor,scale=%d:%d:flags=neighbor"
                         % (_even(W / 26), _even(H / 26), W, H), en)
    elif kind == "slice":
        bh = max(8, H // 16)
        sh = "(%s*sin(floor(Y/%d)*12.9898+floor(T*30)*78.233)*gt(sin(floor(Y/%d)*3.7+floor(T*30)*9.1),0.1))" % (
            f(W * 0.05), bh, bh)
        g.add("format=gbrp,geq=r='r(mod(X+%s+%d,%d),Y)':g='g(mod(X+%s*0.8+%d,%d),Y)':b='b(mod(X+%s*1.2+%d,%d),Y)':"
              "enable='%s',format=yuv420p" % (sh, W, W, sh, W, W, sh, W, W, en))
    elif kind == "zblur":
        g.branch_blend("scale=%d:%d:flags=bilinear,crop=%d:%d" % (_even(W * 1.09), _even(H * 1.09), W, H),
                       "average", 1.0, post=":enable='%s'" % en)
    elif kind == "strobe":
        g.add("eq=brightness='if(lt(mod(t,0.07),0.035),0.3,-0.12)':contrast=1.2:eval=frame:enable='%s'" % en)


WINDOW_KINDS = ("pixel", "slice", "zblur", "strobe")


# ---------------------------------------------------------------- camara
def _camera_expressions(seg, W, H, fps):
    """Devuelve expresiones (zoom, pan, shake_x, shake_y, angulo) para zoompan y rotate."""
    R = seg.R
    tw = max(0.06, seg.tail_len)

    def build(tv):
        z = ["1"]
        pan = []
        ang = []
        if seg.punch > 0:
            z.append("%s*exp(-%s*%s)" % (f(seg.punch), f(seg.punch_k), tv))
        if seg.push > 0:
            z.append("%s*%s/%s" % (f(seg.push), tv, f(R)))
        if seg.head == "zoom":
            z.append("0.32*exp(-9*%s)" % tv)
        elif seg.head == "whip":
            z.append("0.30*exp(-10*%s)" % tv)
            pan.append("%s*exp(-10*%s)" % (neg(seg.head_dir), tv))
        elif seg.head == "roll":
            ang.append("%s*0.26*exp(-9*%s)" % (neg(-seg.head_dir), tv))
        if seg.tail in ("zoom", "whip", "roll"):
            ramp = "pow(max(0,(%s-(%s))/%s),2)" % (tv, f(R - tw), f(tw))
            if seg.tail == "zoom":
                z.append("0.32*%s" % ramp)
            elif seg.tail == "whip":
                z.append("0.30*%s" % ramp)
                pan.append("%s*%s" % (neg(seg.tail_dir), ramp))
            else:
                ang.append("%s*0.26*%s" % (neg(seg.tail_dir), ramp))
        if seg.roll > 0:
            ang.append("%s*exp(-7*%s)*sin(46*%s)" % (f(seg.roll), tv, tv))
        zexpr = "+".join(z)
        pexpr = "+".join(pan) if pan else "0"
        aexpr = "+".join(ang) if ang else ""
        return zexpr, pexpr, aexpr

    return build


def _flash_window(seg, R):
    return R


def build_segment(seg, st, W, H, fps, safe=False, has_overlay=False, text_file=None, font_file=None):
    """Devuelve (filter_complex, etiqueta_salida) para un segmento."""
    g = Graph("0:v")
    R = seg.R
    g.add("setpts=PTS-STARTPTS")

    # --- encuadre vertical
    if st.fit_mode.startswith("Fondo"):
        bw, bh = max(2, (W // 6) // 2 * 2), max(2, (H // 6) // 2 * 2)
        g.raw("[%s]split[bga][fga]" % g.cur, "fga")
        g.raw("[bga]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,gblur=sigma=5,"
              "scale=%d:%d,eq=brightness=-0.12:saturation=1.2[bgb]" % (bw, bh, bw, bh, W, H), "bgb")
        g.raw("[fga]scale=%d:%d:force_original_aspect_ratio=decrease:flags=bicubic[fgb]" % (W, H), "fgb")
        g.raw("[bgb][fgb]overlay=(W-w)/2:(H-h)/2[fitted]", "fitted")
    else:
        g.add("scale=%d:%d:force_original_aspect_ratio=increase:flags=bicubic,crop=%d:%d" % (W, H, W, H))
    g.add("setsar=1")

    # --- curva de velocidad (remapeo de tiempo)
    S = seg.S
    if seg.k == 0 or abs(seg.a) < 1e-3 or safe:
        g.add("setpts='(%s*T)/TB'" % f(R / S))
    else:
        g.add("setpts='(%s*(T/%s+%s*sin(%d*PI*T/%s)/(%d*PI)))/TB'"
              % (f(R), f(S), neg(seg.a), seg.k, f(S), seg.k))
    if seg.smooth == "blend" and not safe:
        g.add("minterpolate=fps=%d:mi_mode=blend" % fps)
    elif seg.smooth == "mci" and not safe:
        g.add("minterpolate=fps=%d:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1" % fps)
    else:
        g.add("fps=%d" % fps)

    if not safe:
        # --- camara: rotacion + zoom/pan/shake en un solo zoompan
        build = _camera_expressions(seg, W, H, fps)
        tv_z = "(on/%d)" % fps
        zexpr, pexpr, aexpr = build(tv_z)
        has_cam = (seg.punch > 0 or seg.push > 0 or seg.shake > 0 or seg.roll > 0
                   or seg.head in ("zoom", "whip", "roll") or seg.tail in ("zoom", "whip", "roll"))
        if has_cam:
            if aexpr:
                _, _, a_t = build("t")
                g.add("rotate=a='%s':ow=iw:oh=ih:c=black:bilinear=1" % a_t)
                comp = "(abs(cos(%s))+%s*abs(sin(%s)))" % (aexpr, f(H / W), aexpr)
                zexpr = "(%s)*%s" % (zexpr, comp)
            sx = sy = "0"
            if seg.shake > 0:
                sx = "%s*exp(-6*%s)*sin(60*%s)" % (f(seg.shake), tv_z, tv_z)
                sy = "%s*exp(-6*%s)*cos(52*%s+1)" % (f(seg.shake * 0.7), tv_z, tv_z)
            g.add("zoompan=z='%s':x='(iw-iw/zoom)/2*(1+%s)+%s':y='(ih-ih/zoom)/2+%s':d=1:s=%dx%d:fps=%d"
                  % (zexpr, pexpr, sx, sy, W, H, fps))

        # --- estela / ghost trails
        if seg.ghost:
            g.add("tmix=frames=4:weights='1 0.75 0.5 0.3'")

        # --- aberracion cromatica / glitch
        if seg.rgb > 0:
            g.add("rgbashift=rh=%d:bh=%d:gv=%d:enable='lt(t,0.14)'" % (-seg.rgb, seg.rgb, seg.rgb // 3))
        if seg.head == "glitch":
            g.add("rgbashift=rh=-22:bh=22:gv=7:enable='lt(t,0.16)'")
        if seg.tail == "glitch":
            g.add("rgbashift=rh=-22:bh=22:gv=7:enable='gt(t,%s)'" % f(R - 0.14))

        # --- desenfoque de movimiento en transiciones
        if seg.head == "whip":
            g.add("avgblur=sizeX=70:sizeY=1:enable='lt(t,0.09)'")
        elif seg.head in ("zoom", "roll"):
            g.add("gblur=sigma=9:enable='lt(t,0.08)'")
        if seg.tail == "whip":
            g.add("avgblur=sizeX=70:sizeY=1:enable='gt(t,%s)'" % f(R - seg.tail_len * 0.6))
        elif seg.tail in ("zoom", "roll"):
            g.add("gblur=sigma=9:enable='gt(t,%s)'" % f(R - seg.tail_len * 0.5))

        # --- transiciones tipo ventana (pixel, slice, zoom blur, strobe) al inicio y/o final del corte
        if seg.head in WINDOW_KINDS:
            _win_effect(g, seg.head, "lt(t,0.12)", W, H)
        if seg.tail in WINDOW_KINDS:
            _win_effect(g, seg.tail, "gt(t,%s)" % f(R - 0.12), W, H)
        if seg.strobe > 0:
            _win_effect(g, "strobe", "lt(t,%s)" % f(seg.strobe), W, H)
        if seg.hue:
            g.add("hue=h='140*sin(t*24)*exp(-4*t)':s=1.5:enable='lt(t,0.6)'")

        # --- arte
        if seg.art:
            _apply_art(g, seg.art, R)

    # --- look de color
    look = st.look
    if look in LOOK_CHAINS:
        g.add(LOOK_CHAINS[look])
    elif look == "Sueno (glow)":
        g.branch_blend("gblur=sigma=24,eq=brightness=-0.04", "screen", 0.4)
    elif look == "Comic / Arte":
        _apply_art(g, "comic", R)
    elif look == "Boceto tinta":
        _apply_art(g, "sketch", R)
    if seg.outline and not safe:
        _outline(g, seg.outline, seg.outline_s, W, H)
    if st.vignette:
        g.add("vignette=angle=PI/5")
    if st.grain:
        g.add("noise=alls=8:allf=t")

    # --- overlays (fuego, humo, chispas, reflejos, flares...): mezcla "screen", uno o dos por corte
    if has_overlay and seg.ovs and not safe:
        g.add("format=gbrp")
        for k, ov in enumerate(seg.ovs):
            d = max(0.15, min(ov.d, R))
            if ov.mode == "start":
                fades = ",fade=t=out:st=0.03:d=%s" % f(d)
            elif ov.mode == "end":
                fades = ",fade=t=in:st=%s:d=%s" % (f(max(0.0, R - d)), f(d))
            else:
                fades = ",fade=t=in:st=0:d=0.2,fade=t=out:st=%s:d=0.25" % f(max(0.0, R - 0.25))
            flip = ",hflip" if ov.flip else ""
            g.parts.append("[%d:v]scale=%d:%d:flags=bilinear,fps=%d,format=gbrp%s%s[ovl%d]"
                           % (k + 1, W, H, fps, flip, fades, k))
            g.raw("[%s][ovl%d]blend=all_mode=screen:all_opacity=%s:shortest=1[ovb%d]"
                  % (g.cur, k, f(ov.opacity), k), "ovb%d" % k)
        g.add("format=yuv420p")

    # --- destello / pulso de brillo, contraste y saturacion
    if not safe:
        br, ct, sa = [], [], []
        if seg.flash > 0:
            br.append("%s*exp(-14*t)" % f(seg.flash))
            ct.append("0.2*%s*exp(-10*t)" % f(seg.flash))
            sa.append("0.8*%s*exp(-8*t)" % f(seg.flash))
        if seg.head == "flash":
            br.append("0.55*exp(-12*t)")
        if seg.tail == "flash":
            br.append("0.55*pow(max(0,(t-%s)/0.1),2)" % f(R - 0.1))
        if br or ct or sa:
            g.add("format=yuv420p,eq=brightness='%s':contrast='1+%s':saturation='1+%s':eval=frame"
                  % ("+".join(br) or "0", "+".join(ct) or "0", "+".join(sa) or "0"))

    # --- texto cinetico (una palabra por corte)
    if text_file and font_file and seg.word:
        size = int(st.text_size * (H / 1920.0))
        g.add("drawtext=fontfile=%s:textfile=%s:expansion=none:fontcolor=%s:fontsize=%d:borderw=%d:"
              "bordercolor=black@0.9:shadowx=3:shadowy=3:x=(w-text_w)/2:y='h*0.68+%d*exp(-13*t)':"
              "alpha='min(1,t*16)':enable='between(t,0.02,%s)'"
              % (font_file, text_file, hex_to_ff(st.text_color), size, max(3, size // 20),
                 max(20, size // 2), f(max(0.1, R - 0.04))))

    g.add("format=yuv420p")
    return g.render(), g.cur
