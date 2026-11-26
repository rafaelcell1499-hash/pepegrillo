"""Prueba de humo del motor (sin interfaz): genera material sintetico y renderiza un reel corto."""
import sys, tempfile, wave
from pathlib import Path

import numpy as np
from .config import Settings
from .engine import Engine
from .ffutil import find_tool, run


def make_audio(path, bpm=128, dur=16.0, sr=44100):
    n = int(sr * dur); y = np.zeros(n, dtype=np.float32); beat = 60 / bpm
    t = np.arange(int(sr * 0.25)) / sr
    kick = np.sin(2 * np.pi * (55 + 120 * np.exp(-t * 30)) * t) * np.exp(-t * 12)
    hat = np.random.RandomState(1).randn(len(t)) * np.exp(-t * 60) * 0.25
    b = 0
    while b * beat < dur:
        s = int(b * beat * sr); drop = b * beat >= 6.0
        k = kick[:max(0, min(len(kick), n - s))]
        y[s:s + len(k)] += k * (1.0 if drop else 0.6)
        if drop:
            h = int((b + 0.5) * beat * sr)
            if h + len(hat) < n: y[h:h + len(hat)] += hat
        b += 1
    y = np.clip(y / max(1e-6, np.abs(y).max()) * 0.9, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((y * 32767).astype(np.int16).tobytes())


def main():
    ff = find_tool("ffmpeg")
    d = Path(tempfile.mkdtemp(prefix="rf_selftest_"))
    make_audio(d / "a.wav")
    srcs = ["testsrc2=s=1280x720:r=30:d=8", "gradients=s=1280x720:r=30:d=8:speed=0.03", "rgbtestsrc=s=720x1280:r=30:d=8"]
    vids = []
    for i, s in enumerate(srcs):
        out = d / ("v%d.mp4" % i)
        code, _, err = run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", s, "-c:v", "libx264", "-preset", "ultrafast",
                            "-pix_fmt", "yuv420p", str(out)])
        if code: print(err); return 1
        vids.append(str(out))
    st = Settings(videos=vids, audio=str(d / "a.wav"), output=str(d / "out.mp4"), max_duration=10,
                  resolution="720x1280", title_text="REELFORGE TEST", kinetic_words="FIRE EDIT FLOW", seed=7,
                  auto_best_part=False, quality="Media (rapida)")
    eng = Engine(st, log=print, progress=lambda p, m="": None)
    out = eng.run()
    print("OK", out, Path(out).stat().st_size, "bytes")
    return 0
