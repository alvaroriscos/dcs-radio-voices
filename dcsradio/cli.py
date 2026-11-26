"""Modo línea de comandos (pruebas y uso por lotes).

    DCSRadioVoicesCLI.exe guion.txt carpeta_salida [--gap 2.5] [--no-fx] [--only N]
"""
from __future__ import annotations

import argparse
import sys
import time

from .config import Settings, settings_dir
from .parser import parse_file
from .pipeline import generate_all


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="DCSRadioVoicesCLI", description="Genera audio de radio desde un guion .txt")
    ap.add_argument("script")
    ap.add_argument("out_dir")
    ap.add_argument("--gap", type=float, default=None, help="segundos de silencio entre líneas")
    ap.add_argument("--no-fx", action="store_true", help="sin efectos de radio")
    ap.add_argument("--only", type=int, default=0, help="generar solo las N primeras líneas")
    ap.add_argument("--parse-only", action="store_true", help="solo analizar y mostrar las líneas")
    ap.add_argument("--fresh", action="store_true", help="ignorar ajustes guardados")
    a = ap.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    script = parse_file(a.script)
    print(f"Guion: {len(script.lines)} líneas, {len(script.speakers)} hablantes, {len(script.threads)} hilos")
    for w in script.warnings:
        print("AVISO:", w)
    if a.parse_only:
        for l in script.lines:
            print(f"{l.speaker:10s} {l.number:5s} take={l.take or '-'} tag={l.effect_tag or '-':6s} "
                  f"tono={l.tone_text!r} ~{l.est_duration}s | {l.text}")
        return 0
    s = Settings() if a.fresh else Settings.load()
    if a.fresh:
        s.speakers = {}
    if a.gap is not None:
        s.gap_seconds = a.gap
    if a.no_fx:
        s.no_effects = True
    if a.only:
        script.lines = script.lines[: a.only]
    t0 = time.time()

    def prog(i, n, m):
        print(f"[{i}/{n}] {m}", flush=True)

    def log(lvl, m):
        print(f"{lvl.upper()}: {m}", flush=True)

    res = generate_all(script, s, a.out_dir, progress=prog, log=log)
    print(f"OK: {res.get('lines')} líneas, {res.get('errors')} errores, {time.time() - t0:.1f} s")
    if not a.fresh:
        s.save()
    return 1 if res.get("errors") else 0


if __name__ == "__main__":
    sys.exit(main())
