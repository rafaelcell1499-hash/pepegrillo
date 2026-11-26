"""Utilidades para localizar y ejecutar FFmpeg / FFprobe (Windows, Linux, macOS)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mpg", ".mpeg", ".wmv", ".flv", ".gif"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}


class EngineError(RuntimeError):
    pass


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def find_tool(name: str):
    exe = name + (".exe" if os.name == "nt" else "")
    cands = []
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base:
            cands += [Path(base) / "bin", Path(base)]
        cands += [Path(sys.executable).resolve().parent / "bin", Path(sys.executable).resolve().parent]
    cands += [app_dir() / "bin", app_dir()]
    for c in cands:
        p = c / exe
        if p.exists():
            return str(p)
    return shutil.which(name)


class ProcessRegistry:
    """Mantiene los procesos vivos para poder cancelarlos desde la interfaz."""

    def __init__(self):
        self._procs = set()
        self._lock = threading.Lock()
        self.cancelled = False

    def add(self, p):
        with self._lock:
            self._procs.add(p)

    def remove(self, p):
        with self._lock:
            self._procs.discard(p)

    def cancel(self):
        self.cancelled = True
        with self._lock:
            for p in list(self._procs):
                try:
                    p.kill()
                except Exception:
                    pass


def run(cmd, cwd=None, registry=None, binary_stdout=False):
    """Ejecuta un comando. Devuelve (returncode, stdout, stderr_text)."""
    if registry is not None and registry.cancelled:
        raise EngineError("Cancelado por el usuario")
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
    if registry is not None:
        registry.add(p)
    try:
        out, err = p.communicate()
    finally:
        if registry is not None:
            registry.remove(p)
    if registry is not None and registry.cancelled:
        raise EngineError("Cancelado por el usuario")
    err_t = err.decode("utf-8", "replace") if err else ""
    if binary_stdout:
        return p.returncode, out, err_t
    return p.returncode, (out.decode("utf-8", "replace") if out else ""), err_t


def probe(ffprobe, path):
    """Devuelve duracion, tamano y fps de un medio."""
    ext = Path(path).suffix.lower()
    is_image = ext in IMAGE_EXT
    info = {"path": path, "is_image": is_image, "duration": 5.0, "w": 0, "h": 0, "fps": 30.0}
    code, out, err = run([ffprobe, "-v", "error", "-show_entries",
                          "format=duration:stream=codec_type,width,height,r_frame_rate,duration",
                          "-of", "json", path])
    if code != 0:
        raise EngineError("No se pudo leer '%s': %s" % (Path(path).name, err.strip()[-300:]))
    data = json.loads(out or "{}")
    dur = None
    try:
        dur = float(data.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        pass
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            info["w"], info["h"] = int(s.get("width", 0)), int(s.get("height", 0))
            try:
                n, d = s.get("r_frame_rate", "30/1").split("/")
                info["fps"] = float(n) / float(d) if float(d) else 30.0
            except Exception:
                pass
            if dur is None:
                try:
                    dur = float(s.get("duration"))
                except (TypeError, ValueError):
                    pass
            break
    if is_image:
        info["duration"] = 3600.0
    else:
        info["duration"] = dur if dur and dur > 0 else 5.0
    return info


def list_xfade(ffmpeg):
    code, out, err = run([ffmpeg, "-hide_banner", "-h", "filter=xfade"])
    names = re.findall(r"^\s{3,}([a-z0-9]+)\s+\d+\s", out + err, flags=re.M)
    return [n for n in names if n != "custom"]


def available_filters(ffmpeg):
    code, out, err = run([ffmpeg, "-hide_banner", "-filters"])
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and len(parts[0]) <= 3:
            names.add(parts[1])
    return names
