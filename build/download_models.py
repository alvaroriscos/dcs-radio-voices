"""Descarga los modelos de voz a ./models (solo hace falta al construir; la app funciona offline).

    python build/download_models.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
KOKORO = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
PIPER = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"

PIPER_VOICES = json.loads((ROOT / "build" / "piper_voices.json").read_text("utf-8"))


def fetch(url: str, dest: Path, min_size: int = 1000):
    if dest.exists() and dest.stat().st_size >= min_size:
        print("ya existe", dest.name)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print("descargando", url)
    req = urllib.request.Request(url, headers={"User-Agent": "dcs-radio-voices-build"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            break
        except Exception as e:
            print("  reintento", attempt + 1, e)
            if attempt == 3:
                raise
    if tmp.stat().st_size < min_size:
        raise RuntimeError(f"Descarga demasiado pequeña: {url}")
    tmp.replace(dest)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    fetch(KOKORO + "kokoro-v1.0.onnx", MODELS / "kokoro-v1.0.onnx", 300_000_000)
    fetch(KOKORO + "voices-v1.0.bin", MODELS / "voices-v1.0.bin", 20_000_000)
    for name, rel in PIPER_VOICES.items():
        base = PIPER + rel + "/" + name
        fetch(base + ".onnx", MODELS / "piper" / f"{name}.onnx", 10_000_000)
        fetch(base + ".onnx.json", MODELS / "piper" / f"{name}.onnx.json", 500)
        fetch(PIPER + rel + "/MODEL_CARD", MODELS / "piper" / f"{name}.MODEL_CARD", 50)
    multi = ROOT / "build" / "multi_speakers.json"
    if multi.exists():
        shutil.copy(multi, MODELS / "piper" / "multi_speakers.json")
    expected = json.loads((ROOT / "build" / "model_hashes.json").read_text("utf-8")) \
        if (ROOT / "build" / "model_hashes.json").exists() else {}
    bad = []
    for rel, h in expected.items():
        p = MODELS / rel
        if not p.exists() or sha256(p) != h:
            bad.append(rel)
    if bad:
        print("ERROR: huella SHA-256 distinta en:", bad)
        return 1
    print("Modelos OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
