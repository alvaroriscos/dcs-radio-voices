"""Herramienta de desarrollo: mide la inteligibilidad (WER con Whisper) de cada voz tras el filtro
de radio y clasifica el género (F0) de los hablantes de los modelos multi-hablante.

Ejecutar con un intérprete que tenga faster-whisper + las dependencias de la app:
    python tools/voice_eval.py salida.json [--multi-sample 120]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dcsradio import effects as fx  # noqa: E402
from dcsradio.engines import TTSManager, KOKORO_VOICES, PIPER_SINGLE, PIPER_MULTI, models_dir  # noqa: E402
from dcsradio.textnorm import normalize  # noqa: E402

SENTENCES = [
    "Talud One-One, Ground, taxi to holding point runway 24 via Charlie, QNH 1014.",
    "Cougar 1-1, climb Angels 20, contact 251.000, squawk 4219, heading 090.",
    "Magic, Enfield 1-1, fuel 1.3, Grid 37S DM 521 784, request picture.",
]


def f0_median(x, sr):
    # autocorrelación por tramos sencilla
    from scipy.signal import butter, sosfilt
    x = sosfilt(butter(4, [60, 500], btype="band", fs=sr, output="sos"), x)
    hop, win = int(0.02 * sr), int(0.04 * sr)
    f0s = []
    for i in range(0, len(x) - win, hop):
        seg = x[i:i + win]
        if np.sqrt(np.mean(seg ** 2)) < 0.02:
            continue
        ac = np.correlate(seg, seg, "full")[win - 1:]
        lo, hi = int(sr / 400), int(sr / 70)
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] > 0.3 * ac[0]:
            f0s.append(sr / k)
    return float(np.median(f0s)) if f0s else 0.0


def main():
    out = Path(sys.argv[1])
    sample = int(sys.argv[sys.argv.index("--multi-sample") + 1]) if "--multi-sample" in sys.argv else 120
    from faster_whisper import WhisperModel
    from scipy.signal import resample_poly
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
    from verify_output import wer
    asr = WhisperModel("small.en", device="cpu", compute_type="int8")
    tts = TTSManager()
    only_multi = "--only-multi" in sys.argv
    voices = [] if only_multi else [f"kokoro:{v}" for v in KOKORO_VOICES] + [
        f"piper:{v}" for v in PIPER_SINGLE if (models_dir() / "piper" / f"{v}.onnx").exists()]
    rng = np.random.default_rng(1)
    for model in PIPER_MULTI:
        if not (models_dir() / "piper" / f"{model}.onnx").exists():
            continue
        cfg = json.loads((models_dir() / "piper" / f"{model}.onnx.json").read_text())
        ns = cfg["num_speakers"]
        ids = sorted(rng.choice(ns, size=min(sample, ns), replace=False).tolist())
        voices += [f"piper:{model}#{i}" for i in ids]
    results = {}
    for vi, vid in enumerate(voices):
        ws, f0 = [], []
        for si, s in enumerate(SENTENCES):
            spoken = normalize(s)
            a, sr = tts.synthesize(spoken, vid, 1.0)
            a = fx.to_sr(fx.trim_silence(a, sr), sr)
            f0.append(f0_median(a, fx.SR))
            y = fx.apply_radio(a, fx.PROFILES["AIR"], 1000 + si)
            y16 = resample_poly(y, 160, 441).astype(np.float32)
            segs, _ = asr.transcribe(y16, beam_size=5, language="en", condition_on_previous_text=False)
            hyp = " ".join(x.text for x in segs)
            ws.append(wer(spoken, hyp))
        results[vid] = {"wer": round(float(np.mean(ws)), 4), "f0": round(float(np.median(f0)), 1)}
        print(vi, len(voices), vid, results[vid], flush=True)
        out.write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
