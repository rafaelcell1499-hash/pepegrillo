"""Overlays procedurales (fuego, humo, chispas, reflejos, flares...) generados con FFmpeg + overlays del usuario."""
from __future__ import annotations

import tempfile
from pathlib import Path

from .ffutil import EngineError, VIDEO_EXT, app_dir, run

CACHE_VERSION = "v3"

# nombre -> (fuente lavfi, cadena de filtros). Todos con fondo NEGRO (se mezclan en modo "screen").
GENERATORS = {
    "fire": (
        "nullsrc=s=108x192:r=30:d=5,format=gray,geq=lum='random(1)*255'",
        "scroll=v=0.05,gblur=sigma=2.2:sigmaV=6,tmix=frames=2,eq=contrast=3.2:brightness=-0.12,"
        "split[a][b];[b]geq=lum='clip(255*pow(Y/H,1.05)*2.3-30,0,255)'[m];[a][m]blend=all_mode=multiply,"
        "eq=gamma=0.7:contrast=1.5,format=gbrp,"
        "lutrgb=r='clip((val-25)*5,0,255)':g='clip((val-85)*3.4,0,255)':b='clip((val-170)*3,0,255)',"
        "scale=540:960:flags=bicubic,gblur=sigma=3,format=yuv420p"),
    "leak": (
        "gradients=s=108x192:r=30:d=5:speed=0.05:c0=0xff7a00:c1=0xff2a6d:c2=0x1a0033:c3=0xffd166:nb_colors=4",
        "gblur=sigma=3,scale=540:960:flags=bicubic,eq=contrast=1.5:brightness=-0.2:saturation=1.3,format=yuv420p"),
    "smoke": (
        "nullsrc=s=30x54:r=30:d=5,format=gray,geq=lum='random(1)*255'",
        "tmix=frames=40,eq=contrast=5:brightness=-0.12,scroll=v=0.01:h=0.003,scale=540:960:flags=bicubic,"
        "gblur=sigma=18,eq=contrast=1.5:brightness=-0.22,format=gbrp,"
        "lutrgb=r='val*0.82':g='val*0.88':b='val*0.98',format=yuv420p"),
    "sparks": (
        "nullsrc=s=135x240:r=30:d=5,format=gray,geq=lum='if(gt(random(1),0.994),255,0)'",
        "loop=loop=-1:size=1:start=0,scroll=v=0.014:h=0.004,scale=540:960:flags=neighbor,"
        "gblur=sigma=1.4:sigmaV=7,format=gbrp,"
        "lutrgb=r='clip(val*14,0,255)':g='clip(val*7,0,255)':b='clip(val*1.6,0,255)',format=yuv420p"),
    "shine": (
        "nullsrc=s=108x192:r=30:d=5,format=gray,geq=lum='255*exp(-pow(((X/W)*0.55+(Y/H)*0.45-mod(T*0.55,1.7)+0.35)/0.05,2))"
        "+110*exp(-pow(((X/W)*0.55+(Y/H)*0.45-mod(T*0.55,1.7)+0.52)/0.012,2))'",
        "scale=540:960:flags=bicubic,gblur=sigma=4,format=gbrp,"
        "lutrgb=r='clip(val*1.0,0,255)':g='clip(val*0.97,0,255)':b='clip(val*0.88,0,255)',format=yuv420p"),
    "flare": (
        "nullsrc=s=135x240:r=30:d=5,format=gray,geq=lum='clip(255*exp(-pow(hypot(X-W*(0.15+0.7*mod(T/4,1)),"
        "Y-H*(0.28+0.1*sin(T)))/(W*0.045),2))+130*exp(-pow((hypot(X-W*(0.15+0.7*mod(T/4,1)),"
        "Y-H*(0.28+0.1*sin(T)))-W*0.16)/(W*0.02),2))+210*exp(-pow((Y-H*(0.28+0.1*sin(T)))/(H*0.006),2))"
        "*exp(-pow((X-W*(0.15+0.7*mod(T/4,1)))/(W*0.55),2)),0,255)'",
        "scale=540:960:flags=bicubic,gblur=sigma=3,format=gbrp,"
        "lutrgb=r='clip(val*1.0,0,255)':g='clip(val*0.8,0,255)':b='clip(val*0.55,0,255)',format=yuv420p"),
    "bokeh": (
        "nullsrc=s=54x96:r=30:d=5,format=gray,geq=lum='if(gt(random(1),0.985),255,0)'",
        "loop=loop=-1:size=1:start=0,scroll=v=0.006:h=0.003,scale=540:960:flags=bicubic,gblur=sigma=5,"
        "lutrgb=y='clip(val*3.2,0,255)',format=gbrp,"
        "lutrgb=r='clip(val*1.0,0,255)':g='clip(val*0.8,0,255)':b='clip(val*0.7,0,255)',format=yuv420p"),
    "dust": (
        "nullsrc=s=270x480:r=30:d=5,format=gray,geq=lum='if(gt(random(1),0.994),190+random(1)*65,0)'",
        "scale=540:960:flags=neighbor,gblur=sigma=0.9,eq=contrast=1.5,format=yuv420p"),
    "rain": (
        "nullsrc=s=135x240:r=30:d=5,format=gray,geq=lum='if(gt(random(1),0.992),255,0)'",
        "loop=loop=-1:size=1:start=0,scroll=v=0.07:h=-0.012,scale=540:960:flags=neighbor,"
        "gblur=sigma=0.7:sigmaV=14,format=gbrp,"
        "lutrgb=r='clip(val*9,0,255)':g='clip(val*11,0,255)':b='clip(val*14,0,255)',format=yuv420p"),
}

KIND_LABELS = {"fire": "fuego", "leak": "light leaks", "smoke": "humo", "sparks": "chispas/brasas",
               "shine": "reflejos", "flare": "lens flare", "bokeh": "bokeh", "dust": "polvo de pelicula",
               "rain": "lluvia"}


def cache_dir():
    d = Path(tempfile.gettempdir()) / "reelforge_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure(ffmpeg, kind, registry=None):
    """Genera (o reutiliza de la cache) el overlay `kind`. Devuelve la ruta."""
    out = cache_dir() / ("%s_%s.mp4" % (kind, CACHE_VERSION))
    if out.exists() and out.stat().st_size > 5000:
        return str(out)
    src, vf = GENERATORS[kind]
    cmd = [ffmpeg, "-v", "error", "-y", "-nostdin", "-f", "lavfi", "-i", src, "-vf", vf, "-t", "5",
           "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", str(out)]
    code, _, err = run(cmd, registry=registry)
    if code != 0 or not out.exists():
        raise EngineError("No se pudo generar el overlay '%s': %s" % (kind, err.strip()[-300:]))
    return str(out)


def ensure_fire(ffmpeg, registry=None):
    return ensure(ffmpeg, "fire", registry)


def ensure_leak(ffmpeg, registry=None):
    return ensure(ffmpeg, "leak", registry)


def user_overlay_dir():
    d = app_dir() / "overlays"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def list_user_overlays():
    d = user_overlay_dir()
    if not d.exists():
        return []
    return sorted(str(p) for p in d.iterdir() if p.suffix.lower() in VIDEO_EXT and p.is_file())
