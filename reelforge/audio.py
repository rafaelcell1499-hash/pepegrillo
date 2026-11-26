"""Analisis musical: beats, BPM, energia, onsets y drops (solo NumPy)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .ffutil import EngineError, run

SR = 22050
N_FFT = 1024
HOP = 512
FPS_ENV = SR / HOP


@dataclass
class AudioInfo:
    duration: float
    bpm: float
    beats: np.ndarray                 # tiempos de beat (s)
    strength: np.ndarray              # fuerza 0..1 de cada beat
    drops: list = field(default_factory=list)
    energy: np.ndarray = None         # energia normalizada por frame (0..1)

    def energy_at(self, t):
        i = int(np.clip(t * FPS_ENV, 0, len(self.energy) - 1))
        return float(self.energy[i])

    def mean_energy(self, a, b):
        i = int(max(0, a * FPS_ENV))
        j = int(min(len(self.energy), max(a + 0.1, b) * FPS_ENV))
        return float(self.energy[i:j].mean()) if j > i else 0.0


def decode_mono(ffmpeg, path, registry=None):
    code, out, err = run([ffmpeg, "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], registry=registry, binary_stdout=True)
    if code != 0 or not out:
        raise EngineError("No se pudo leer el audio: %s" % err.strip()[-300:])
    return np.frombuffer(out, dtype=np.float32).copy()


def _band_matrix(n_bins, n_bands=40, fmin=40.0, fmax=10000.0):
    freqs = np.linspace(0, SR / 2, n_bins)
    edges = np.geomspace(fmin, fmax, n_bands + 1)
    m = np.zeros((n_bins, n_bands), dtype=np.float32)
    for b in range(n_bands):
        sel = (freqs >= edges[b]) & (freqs < edges[b + 1])
        if not sel.any():
            sel[np.argmin(np.abs(freqs - (edges[b] + edges[b + 1]) / 2))] = True
        m[sel, b] = 1.0 / sel.sum()
    return m


def _stft_bands(y):
    if len(y) < N_FFT * 4:
        y = np.pad(y, (0, N_FFT * 4 - len(y)))
    win = np.hanning(N_FFT).astype(np.float32)
    n_frames = 1 + (len(y) - N_FFT) // HOP
    out_bands = []
    rms = np.empty(n_frames, dtype=np.float32)
    bm = _band_matrix(N_FFT // 2 + 1)
    chunk = 2000
    for s in range(0, n_frames, chunk):
        e = min(n_frames, s + chunk)
        idx = np.arange(N_FFT)[None, :] + HOP * np.arange(s, e)[:, None]
        fr = y[idx]
        rms[s:e] = np.sqrt((fr ** 2).mean(axis=1))
        mag = np.abs(np.fft.rfft(fr * win, axis=1)).astype(np.float32)
        out_bands.append(mag @ bm)
    return np.concatenate(out_bands, axis=0), rms


def _moving_mean(x, n):
    n = max(1, int(n))
    k = np.ones(n, dtype=np.float32) / n
    return np.convolve(np.pad(x, (n // 2, n - 1 - n // 2), mode="edge"), k, mode="valid")


def _tempo(onset):
    fps = FPS_ENV
    x = onset - onset.mean()
    n = len(x)
    f = np.fft.rfft(x, 2 * n)
    ac = np.fft.irfft(f * np.conj(f))[:n]
    lo, hi = int(fps * 60 / 190), int(fps * 60 / 68)
    hi = min(hi, n - 2)
    if hi <= lo + 2:
        return 120.0
    lags = np.arange(lo, hi)
    bpms = 60.0 * fps / lags
    weight = np.exp(-0.5 * (np.log2(bpms / 122.0) / 0.9) ** 2)
    sc = ac[lo:hi] * weight
    j = int(np.argmax(sc))
    lag = float(lags[j])
    if 0 < j < len(sc) - 1:  # interpolacion parabolica
        a, b, c = sc[j - 1], sc[j], sc[j + 1]
        den = a - 2 * b + c
        if abs(den) > 1e-9:
            lag = lag + 0.5 * (a - c) / den
    return float(60.0 * fps / lag)


def _track_beats(onset, period, tightness=90.0):
    """Seguimiento de beats por programacion dinamica (estilo Ellis)."""
    n = len(onset)
    score = onset / (onset.std() + 1e-9)
    cum = score.copy()
    back = -np.ones(n, dtype=np.int64)
    w = np.arange(-int(round(2 * period)), -int(round(period / 2)) + 1)
    w = w[w < 0]
    txw = -tightness * (np.log(-w / period)) ** 2
    for i in range(n):
        idx = i + w
        ok = idx >= 0
        if not ok.any():
            continue
        cand = cum[idx[ok]] + txw[ok]
        j = int(np.argmax(cand))
        cum[i] = score[i] + cand[j]
        back[i] = idx[ok][j]
    tail_start = max(0, n - int(period) - 1)
    last = int(np.argmax(cum[tail_start:])) + tail_start
    beats = [last]
    while back[beats[-1]] >= 0:
        beats.append(int(back[beats[-1]]))
    return np.array(beats[::-1], dtype=np.int64)


def analyze(ffmpeg, path, registry=None, log=None):
    y = decode_mono(ffmpeg, path, registry)
    dur = len(y) / SR
    if dur < 1.0:
        raise EngineError("El audio es demasiado corto.")
    bands, rms = _stft_bands(y)
    fps = FPS_ENV
    logb = np.log1p(bands * 40.0)
    diff = np.maximum(0, np.diff(logb, axis=0, prepend=logb[:1]))
    flux = diff.sum(axis=1)
    low = diff[:, :12].sum(axis=1)
    onset = 0.6 * flux / (flux.std() + 1e-9) + 0.4 * low / (low.std() + 1e-9)
    onset = np.maximum(0, onset - _moving_mean(onset, fps * 0.6))
    onset = _moving_mean(onset, 2)

    bpm = _tempo(onset)
    period = fps * 60.0 / bpm
    bi = _track_beats(onset, period)
    refined = []
    for b in bi:                       # afinar al pico de onset mas cercano
        a, c = max(0, b - 1), min(len(onset), b + 2)
        refined.append(a + int(np.argmax(onset[a:c])))
    lat = LATENCY
    beats = np.array(refined) * HOP / SR + lat
    p90 = np.percentile(onset, 90) + 1e-9
    strength = np.array([min(1.0, onset[max(0, b - 1):b + 2].max() / p90) for b in refined],
                        dtype=np.float32)

    e = _moving_mean(rms, fps * 0.5)
    e = np.clip(e / (np.percentile(e, 92) + 1e-9), 0, 1.2) / 1.2

    drops = []                          # drops = salto de energia sostenido
    w = int(fps * 2.0)
    if len(e) > 2 * w + 4:
        cs = np.concatenate([[0], np.cumsum(e)])
        score = np.zeros(len(e))
        for i in range(w, len(e) - w):
            score[i] = (cs[i + w] - cs[i]) / w - (cs[i] - cs[i - w]) / w
        thr = max(0.16, 0.5 * score.max()) if score.max() > 0.16 else 9
        i = 0
        while i < len(score):
            if score[i] > thr:
                j = i + int(np.argmax(score[i:i + w]))
                t = j / fps
                if not drops or t - drops[-1] > 6.0:
                    drops.append(float(beats[np.argmin(np.abs(beats - t))]))
                i = j + int(fps * 4)
            else:
                i += 1
    if log:
        log("Audio: %.1fs | %.1f BPM | %d beats | drops: %s" % (
            dur, bpm, len(beats), ", ".join("%.1fs" % d for d in drops) if drops else "ninguno"))
    return AudioInfo(duration=dur, bpm=bpm, beats=beats, strength=strength, drops=drops, energy=e)


LATENCY = 0.011  # calibrado con audio de prueba (ms de adelanto medio)
