"""Motor de render: analiza el audio, planifica el edit y lo renderiza con FFmpeg."""
from __future__ import annotations

import os
import random
import shutil
import tempfile
import textwrap
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from . import audio as audio_mod
from . import fx, overlays, planner
from .config import Settings
from .ffutil import (EngineError, ProcessRegistry, available_filters, find_tool, list_xfade, probe, run)

FONT_CANDIDATES = [
    "C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
    "/System/Library/Fonts/Supplemental/Impact.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]


def _f(x):
    return fx.f(x)


class Engine:
    def __init__(self, st: Settings, log=None, progress=None):
        self.st = st
        self._log = log or (lambda m: None)
        self._progress = progress or (lambda p, m="": None)
        self.reg = ProcessRegistry()
        self.ffmpeg = find_tool("ffmpeg")
        self.ffprobe = find_tool("ffprobe")
        if not self.ffmpeg or not self.ffprobe:
            raise EngineError("No se encontro FFmpeg/FFprobe. Coloca ffmpeg.exe y ffprobe.exe en la carpeta 'bin'.")
        self.audio_info = None
        self.filters = set()

    # ------------------------------------------------------------ utilidades
    def log(self, m):
        self._log(m)

    def cancel(self):
        self.reg.cancel()

    def _pick_font(self):
        cands = ([self.st.font_path] if self.st.font_path else []) + FONT_CANDIDATES
        for c in cands:
            if c and Path(c).exists():
                return c
        return None

    def _validate(self):
        st = self.st
        if not st.videos:
            raise EngineError("Anade al menos un video o imagen.")
        if not st.audio or not Path(st.audio).exists():
            raise EngineError("Selecciona un archivo de audio.")
        if not st.output:
            raise EngineError("Elige donde guardar el video final.")
        if not self.filters:
            self.filters = available_filters(self.ffmpeg)

    # ------------------------------------------------------------ analisis
    def analyze_audio(self):
        self.audio_info = audio_mod.analyze(self.ffmpeg, self.st.audio, self.reg, self.log)
        return self.audio_info

    def _choose_window(self, info):
        st = self.st
        total = info.duration
        want = st.max_duration if st.max_duration > 0 else total
        if st.preview:
            want = min(want, 6.0)
        want = min(want, total)
        start = max(0.0, min(st.audio_start, max(0.0, total - want)))
        if st.auto_best_part and st.audio_start <= 0.01 and total > want + 1.5:
            best, best_s = 0.0, -1.0
            cand = info.beats[(info.beats + want) <= total]
            step = max(1, len(cand) // 160)
            for t in cand[::step]:
                sc = info.mean_energy(t, t + want)
                if any(t + want * 0.1 <= d <= t + want * 0.75 for d in info.drops):
                    sc += 0.35
                if sc > best_s:
                    best, best_s = float(t), sc
            start = best
            self.log("Mejor seccion del audio elegida: desde %.1fs" % start)
        if len(info.beats):  # alinear el inicio con un beat
            start = float(info.beats[np.argmin(np.abs(info.beats - start))])
            start = max(0.0, min(start, max(0.0, total - want)))
        return start, min(want, total - start)

    # ------------------------------------------------------------ render
    def run(self):
        st = self.st
        self._validate()
        rng_seed = st.seed if st.seed else random.randrange(1, 10 ** 6)
        rng = random.Random(rng_seed)
        self.log("Semilla del edit: %d (usa la misma para repetir el resultado)" % rng_seed)

        W, H = [int(x) for x in st.resolution.split("x")]
        fps = int(st.fps)
        if st.preview:
            W, H, fps = 540, 960, 30
        work = Path(tempfile.mkdtemp(prefix="reelforge_"))
        try:
            return self._run(st, rng, W, H, fps, work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _run(self, st, rng, W, H, fps, work):
        self._progress(0.01, "Analizando audio...")
        info = self.audio_info or self.analyze_audio()
        a0, dur = self._choose_window(info)
        self.log("Ventana de audio: %.1fs -> %.1fs (%.1fs de video)" % (a0, a0 + dur, dur))

        self._progress(0.05, "Leyendo videos...")
        clips = []
        for p in st.videos:
            try:
                c = probe(self.ffprobe, p)
                clips.append(c)
            except EngineError as e:
                self.log("AVISO: se omite %s (%s)" % (Path(p).name, e))
        if not clips:
            raise EngineError("Ninguno de los videos se pudo leer.")

        font = self._pick_font()
        need_text = bool(st.kinetic_words.strip() or st.title_text.strip())
        if need_text and (not font or "drawtext" not in self.filters):
            self.log("AVISO: el texto en pantalla no esta disponible (fuente o filtro drawtext ausente).")
            need_text = False
        if font and need_text:
            shutil.copy(font, work / "font.ttf")

        # overlays procedurales (se generan una vez y quedan en cache)
        ov = {}
        wanted = [k for k, on in (("fire", st.fire), ("leak", st.light_leaks), ("smoke", st.smoke),
                                  ("sparks", st.sparks), ("shine", st.shine), ("flare", st.flare),
                                  ("bokeh", st.bokeh), ("dust", st.dust), ("rain", st.rain)) if on]
        if wanted and st.overlay_amount > 0 or st.fire:
            self._progress(0.06, "Preparando overlays...")
        for k in wanted:
            try:
                ov[k] = overlays.ensure(self.ffmpeg, k, self.reg)
            except EngineError as e:
                self.log("AVISO: %s" % e)
        if st.user_overlays:
            ov["user"] = overlays.list_user_overlays()
            if ov["user"]:
                self.log("Overlays propios encontrados: %d" % len(ov["user"]))

        xfade_ok = list_xfade(self.ffmpeg) if st.xfade_transitions else []
        segs = planner.plan(info, st, clips, a0, dur, ov, rng, xfade_ok, fps=fps, log=self.log)

        # texto cinetico: un archivo por segmento
        use_words = need_text and bool(st.kinetic_words.strip())
        if use_words:
            for sg in segs:
                (work / ("w%d.txt" % sg.i)).write_text(sg.word, encoding="utf-8")

        # ---- render de segmentos en paralelo
        files = [None] * len(segs)
        workers = max(1, min(4, (os.cpu_count() or 4) // 3 or 1))
        done = [0]
        lock = threading.Lock()
        self.log("Renderizando %d segmentos (%d en paralelo)..." % (len(segs), workers))

        def job(sg):
            out = work / ("seg_%03d.mp4" % sg.i)
            self._render_segment(sg, clips, W, H, fps, out, work, use_words)
            return sg.i, str(out)

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(job, sg) for sg in segs]
            for fu in as_completed(futs):
                i, path = fu.result()
                files[i] = path
                with lock:
                    done[0] += 1
                    self._progress(0.08 + 0.62 * done[0] / len(segs),
                                   "Segmento %d/%d" % (done[0], len(segs)))

        # ---- ensamblado por grupos
        self.log("Ensamblando transiciones...")
        groups = [segs[k:k + planner.GROUP_SIZE] for k in range(0, len(segs), planner.GROUP_SIZE)]
        gfiles = []
        for gi, grp in enumerate(groups):
            out = work / ("group_%02d.mp4" % gi)
            self._assemble_group([files[s.i] for s in grp], grp, fps, out)
            gfiles.append(str(out))
            self._progress(0.70 + 0.10 * (gi + 1) / len(groups), "Ensamblando %d/%d" % (gi + 1, len(groups)))

        # ---- mezcla final: titulo + audio
        self._progress(0.82, "Codificando video final...")
        self._final(gfiles, a0, dur, W, H, fps, work, need_text and bool(st.title_text.strip()))
        self._progress(1.0, "Listo")
        self.log("Video guardado en: %s" % st.output)
        return st.output

    # ------------------------------------------------------------ segmento
    def _render_segment(self, sg, clips, W, H, fps, out, work, use_words):
        clip = clips[sg.clip]
        st = self.st
        last_err = ""
        for safe in (False, True):
            cmd = [self.ffmpeg, "-v", "error", "-y", "-nostdin"]
            if clip["is_image"]:
                cmd += ["-loop", "1", "-framerate", str(fps), "-t", _f(sg.R + 1), "-i", clip["path"]]
            else:
                cmd += ["-ss", _f(sg.src_start), "-t", _f(sg.S + 0.05), "-i", clip["path"]]
            has_ov = bool(sg.ovs) and not safe
            if has_ov:
                for ov in sg.ovs:
                    cmd += ["-stream_loop", "-1", "-ss", _f(ov.ss), "-i", ov.path]
            fc, label = fx.build_segment(
                sg, st, W, H, fps, safe=safe, has_overlay=has_ov,
                text_file=("w%d.txt" % sg.i) if (use_words and sg.word and not safe) else None,
                font_file="font.ttf" if (use_words and not safe) else None)
            fc += ";[%s]tpad=stop_mode=clone:stop_duration=0.6[out]" % label
            cmd += ["-filter_complex", fc, "-map", "[out]", "-frames:v", str(sg.nframes), "-r", str(fps),
                    "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p", str(out)]
            code, _, err = run(cmd, cwd=str(work), registry=self.reg)
            if code == 0 and Path(out).exists():
                if safe:
                    self.log("AVISO: segmento %d renderizado en modo seguro (sin efectos)." % sg.i)
                return
            last_err = err.strip()[-600:]
            if not safe:
                self.log("AVISO: segmento %d fallo con efectos, reintentando simple... (%s)"
                         % (sg.i, last_err.splitlines()[-1] if last_err else "?"))
        raise EngineError("Fallo al renderizar el segmento %d:\n%s" % (sg.i, last_err))

    # ------------------------------------------------------------ ensamblado
    def _assemble_group(self, files, grp, fps, out):
        if len(files) == 1:
            shutil.copy(files[0], out)
            return
        cmd = [self.ffmpeg, "-v", "error", "-y", "-nostdin"]
        parts = []
        for j, fl in enumerate(files):
            cmd += ["-i", fl]
            parts.append("[%d:v]fps=%d,format=yuv420p,setsar=1[s%d]" % (j, fps, j))
        acc, acc_len = "s0", grp[0].R
        for j in range(1, len(files)):
            prev = grp[j - 1]
            if prev.xfade:
                d = prev.xfade_d
                parts.append("[%s][s%d]xfade=transition=%s:duration=%s:offset=%s[y%d];[y%d]fps=%d,setsar=1[x%d]"
                             % (acc, j, prev.xfade, _f(d), _f(acc_len - d), j, j, fps, j))
                acc_len += grp[j].R - d
            else:
                parts.append("[%s][s%d]concat=n=2:v=1:a=0[c%d];[c%d]fps=%d,setsar=1[x%d]" % (acc, j, j, j, fps, j))
                acc_len += grp[j].R
            acc = "x%d" % j
        cmd += ["-filter_complex", ";".join(parts), "-map", "[%s]" % acc, "-an", "-c:v", "libx264",
                "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p", str(out)]
        code, _, err = run(cmd, registry=self.reg)
        if code != 0:
            raise EngineError("Fallo al ensamblar transiciones:\n%s" % err.strip()[-600:])

    # ------------------------------------------------------------ final
    def _encoder_args(self, enc):
        q = self.st.quality
        crf = {"Maxima": 15, "Alta": 18, "Media (rapida)": 22}.get(q, 18)
        preset = {"Maxima": "slow", "Alta": "medium", "Media (rapida)": "veryfast"}.get(q, "medium")
        if enc.startswith("NVIDIA"):
            return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(crf + 1), "-b:v", "0"]
        if enc.startswith("AMD"):
            return ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", str(crf + 2),
                    "-qp_p", str(crf + 2)]
        if enc.startswith("Intel"):
            return ["-c:v", "h264_qsv", "-global_quality", str(crf + 2)]
        return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-profile:v", "high"]

    def _final(self, gfiles, a0, dur, W, H, fps, work, with_title):
        st = self.st
        cmd = [self.ffmpeg, "-v", "error", "-y", "-nostdin"]
        for g in gfiles:
            cmd += ["-i", g]
        cmd += ["-ss", _f(a0), "-t", _f(dur), "-i", st.audio]
        n = len(gfiles)
        if n > 1:
            chain = "".join("[%d:v]" % i for i in range(n)) + "concat=n=%d:v=1:a=0[vc]" % n
        else:
            chain = "[0:v]null[vc]"
        label = "vc"
        if with_title:
            size = int(st.text_size * (H / 1920.0))
            chars = max(5, int(W * 0.78 / (size * 0.66)))
            txt = "\n".join(textwrap.fill(line, chars) for line in st.title_text.strip().splitlines())
            (Path(work) / "title.txt").write_text(txt, encoding="utf-8")
            T = max(0.8, min(st.title_seconds, dur - 0.2))
            ypos = {"Arriba": "h*0.12", "Abajo": "h*0.80-text_h"}.get(st.title_pos, "(h-text_h)/2")
            chain += (";[vc]drawtext=fontfile=font.ttf:textfile=title.txt:expansion=none:fontcolor=%s:fontsize=%d:"
                      "borderw=%d:bordercolor=black@0.9:shadowx=4:shadowy=4:line_spacing=%d:x=(w-text_w)/2:y=%s:"
                      "alpha='if(lt(t,0.45),(t-0.15)/0.3,if(gt(t,%s),(%s-t)/0.4,1))':enable='between(t,0.15,%s)'[vt]"
                      % (fx.hex_to_ff(st.text_color), size, max(3, size // 18), size // 10, ypos,
                         _f(T - 0.4), _f(T), _f(T)))
            label = "vt"
        af = "afade=t=in:st=0:d=0.05,afade=t=out:st=%s:d=%s" % (_f(max(0.0, dur - 1.2)), _f(min(1.2, dur)))
        chain += ";[%d:a]%s[aout]" % (n, af)
        Path(st.output).parent.mkdir(parents=True, exist_ok=True)

        encs = [st.encoder] + ([] if st.encoder.startswith("CPU") else ["CPU (x264)"])
        last = ""
        for enc in encs:
            c = list(cmd) + ["-filter_complex", chain, "-map", "[%s]" % label, "-map", "[aout]"]
            c += self._encoder_args(enc)
            c += ["-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-t", _f(dur),
                  "-movflags", "+faststart", str(st.output)]
            code, _, err = run(c, cwd=str(work), registry=self.reg)
            if code == 0:
                return
            last = err.strip()[-600:]
            self.log("AVISO: el codificador '%s' fallo; probando CPU." % enc)
        raise EngineError("Fallo en la codificacion final:\n%s" % last)
