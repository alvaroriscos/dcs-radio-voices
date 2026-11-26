"""Motores de voz offline: Kokoro-82M (ONNX) y Piper.

Cada voz se identifica con un id de texto:
    "kokoro:am_michael"
    "piper:en_US-joe-medium"
    "piper:en_US-libritts_r-medium#123"   (modelo multi-hablante, hablante 123)
"""
from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """Carpeta con modelos/ejemplos: _internal en la app empaquetada, raíz del proyecto en desarrollo."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return app_dir()


def models_dir() -> Path:
    env = os.environ.get("DCSRADIO_MODELS")
    if env:
        return Path(env)
    return resource_dir() / "models"


@dataclass
class VoiceInfo:
    id: str
    label: str        # nombre visible
    engine: str       # kokoro | piper
    gender: str       # M | F
    accent: str       # US | GB
    license: str
    quality: str = ""


KOKORO_VOICES = {
    # id: (etiqueta, género, acento, nota de calidad publicada por el autor)
    "am_michael": ("Michael", "M", "US", "C+"), "am_fenrir": ("Fenrir", "M", "US", "C+"),
    "am_puck": ("Puck", "M", "US", "C+"), "am_echo": ("Echo", "M", "US", "D"),
    "am_eric": ("Eric", "M", "US", "D"), "am_liam": ("Liam", "M", "US", "D"),
    "am_onyx": ("Onyx", "M", "US", "D"), "am_adam": ("Adam", "M", "US", "F+"),
    "am_santa": ("Santa", "M", "US", "D-"),
    "bm_george": ("George", "M", "GB", "C"), "bm_fable": ("Fable", "M", "GB", "C"),
    "bm_lewis": ("Lewis", "M", "GB", "D+"), "bm_daniel": ("Daniel", "M", "GB", "D"),
    "af_heart": ("Heart", "F", "US", "A"), "af_bella": ("Bella", "F", "US", "A-"),
    "af_nicole": ("Nicole, susurrada", "F", "US", "B-"), "af_aoede": ("Aoede", "F", "US", "C+"),
    "af_kore": ("Kore", "F", "US", "C+"), "af_sarah": ("Sarah", "F", "US", "C+"),
    "af_nova": ("Nova", "F", "US", "C"), "af_alloy": ("Alloy", "F", "US", "C"),
    "af_sky": ("Sky", "F", "US", "C-"), "af_jessica": ("Jessica", "F", "US", "D"),
    "af_river": ("River", "F", "US", "D"),
    "bf_emma": ("Emma", "F", "GB", "B-"), "bf_isabella": ("Isabella", "F", "GB", "C"),
    "bf_alice": ("Alice", "F", "GB", "D"), "bf_lily": ("Lily", "F", "GB", "D"),
}

# Voces Piper incluidas (licencias verificadas en su MODEL_CARD).
PIPER_SINGLE = {
    "en_US-joe-medium": ("Joe", "M", "US", "CC0"),
    "en_US-john-medium": ("John", "M", "US", "Dominio público"),
    "en_US-bryce-medium": ("Bryce", "M", "US", "Dominio público"),
    "en_US-ryan-medium": ("Ryan", "M", "US", "CC BY-NC-SA 4.0 (solo uso no comercial)"),
    "en_GB-northern_english_male-medium": ("Northern English male", "M", "GB", "CC BY-SA 4.0"),
}
PIPER_MULTI = {
    "en_US-libritts_r-medium": ("LibriTTS-R", "US", "CC BY 4.0"),
}


def _load_multi_catalog() -> dict[str, list[tuple[int, str]]]:
    """Hablantes seleccionados de los modelos multi-hablante (id, género)."""
    p = models_dir() / "piper" / "multi_speakers.json"
    if p.exists():
        try:
            data = json.loads(p.read_text("utf-8"))
            return {k: [(int(i), g) for i, g in v] for k, v in data.items()}
        except Exception:
            pass
    return {}


_catalog: list[VoiceInfo] | None = None


def voice_catalog() -> list[VoiceInfo]:
    global _catalog
    if _catalog is not None:
        return _catalog
    out: list[VoiceInfo] = []
    md = models_dir()
    if (md / "kokoro-v1.0.onnx").exists() or not md.exists():
        for vid, (lab, g, acc, q) in KOKORO_VOICES.items():
            out.append(VoiceInfo(f"kokoro:{vid}", f"Kokoro · {lab} ({'♂' if g == 'M' else '♀'} {acc})",
                                 "kokoro", g, acc, "Apache 2.0", q))
    for vid, (lab, g, acc, lic) in PIPER_SINGLE.items():
        if (md / "piper" / f"{vid}.onnx").exists():
            out.append(VoiceInfo(f"piper:{vid}", f"Piper · {lab} ({'♂' if g == 'M' else '♀'} {acc})",
                                 "piper", g, acc, lic))
    multi = _load_multi_catalog()
    for model, (lab, acc, lic) in PIPER_MULTI.items():
        if not (md / "piper" / f"{model}.onnx").exists():
            continue
        for sid, g in multi.get(model, []):
            out.append(VoiceInfo(f"piper:{model}#{sid}",
                                 f"Piper · {lab} #{sid} ({'♂' if g == 'M' else '♀'} {acc})",
                                 "piper", g, acc, lic))
    _catalog = out
    return out


def voice_by_id(vid: str) -> VoiceInfo | None:
    for v in voice_catalog():
        if v.id == vid:
            return v
    return None


class TTSManager:
    """Carga perezosa y síntesis thread-safe."""

    def __init__(self):
        self._lock = threading.Lock()
        self._kokoro = None
        self._piper: dict[str, object] = {}

    def _get_kokoro(self):
        if self._kokoro is None:
            from kokoro_onnx import Kokoro
            md = models_dir()
            self._kokoro = Kokoro(str(md / "kokoro-v1.0.onnx"), str(md / "voices-v1.0.bin"))
        return self._kokoro

    def _get_piper(self, model: str):
        if model not in self._piper:
            from piper import PiperVoice
            self._piper[model] = PiperVoice.load(str(models_dir() / "piper" / f"{model}.onnx"))
        return self._piper[model]

    def synthesize(self, text: str, voice_id: str, speed: float = 1.0) -> tuple[np.ndarray, int]:
        """Devuelve (audio float32 mono, sample_rate)."""
        engine, _, name = voice_id.partition(":")
        speed = float(min(2.0, max(0.5, speed)))
        with self._lock:
            if engine == "kokoro":
                k = self._get_kokoro()
                lang = "en-gb" if name.startswith("b") else "en-us"
                audio, sr = k.create(text, voice=name, speed=speed, lang=lang)
                return np.asarray(audio, dtype=np.float32), int(sr)
            if engine == "piper":
                from piper import SynthesisConfig
                model, _, sid = name.partition("#")
                v = self._get_piper(model)
                cfg = SynthesisConfig(speaker_id=int(sid) if sid else None,
                                      length_scale=1.0 / speed, normalize_audio=True)
                chunks = [c.audio_float_array for c in v.synthesize(text, syn_config=cfg)]
                audio = np.concatenate(chunks) if chunks else np.zeros(1, np.float32)
                return audio.astype(np.float32), int(v.config.sample_rate)
        raise ValueError(f"Voz desconocida: {voice_id}")
