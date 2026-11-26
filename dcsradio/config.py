"""Ajustes persistentes, roles de hablante y asignación de voces por defecto."""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .textnorm import DEFAULT_LEXICON

APP_NAME = "DCS Radio Voices"
APP_VERSION = "1.0.0"
PLAYER_VOICE = "kokoro:am_michael"


def settings_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = Path(os.environ.get("DCSRADIO_SETTINGS_DIR", base / "DCSRadioVoices"))
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class SpeakerSettings:
    voice: str = ""
    speed: float = 1.0      # multiplicador
    pitch: float = 0.0      # semitonos (-4..+4)
    volume: float = 1.0
    profile: str = "AUTO"   # AUTO | AIR | GROUND | TOWER | STRESS | CLEAN


@dataclass
class Settings:
    gap_seconds: float = 2.5
    no_effects: bool = False
    force_player_radio: bool = True
    fx_intensity: float = 1.0      # 0..2
    variation: float = 0.35        # 0..1
    mic_clicks: bool = True
    breathing: bool = True
    seed: int = 0
    ogg_quality: float = 0.6       # 0..1 (1 = máxima)
    out_combined: bool = True
    out_individual: bool = True
    out_manifest: bool = True
    niner: bool = True
    decimal_word: str = "decimal"
    last_script: str = ""
    last_output: str = ""
    speakers: dict[str, SpeakerSettings] = field(default_factory=dict)
    lexicon: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_LEXICON))

    # ---------------------------------------------------------------
    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or settings_dir() / "settings.json"
        s = cls()
        if path.exists():
            try:
                data = json.loads(path.read_text("utf-8"))
                for k, v in data.items():
                    if k == "speakers":
                        s.speakers = {n: SpeakerSettings(**{kk: vv for kk, vv in d.items()
                                                            if kk in SpeakerSettings.__dataclass_fields__})
                                      for n, d in v.items()}
                    elif k in cls.__dataclass_fields__:
                        setattr(s, k, v)
            except Exception:
                pass
        s.speakers.setdefault("PLAYER", SpeakerSettings(voice=PLAYER_VOICE, speed=default_speed(PLAYER_VOICE, "PLAYER")))
        if not s.speakers["PLAYER"].voice:
            s.speakers["PLAYER"].voice = PLAYER_VOICE
        return s

    def save(self, path: Path | None = None):
        path = path or settings_dir() / "settings.json"
        d = asdict(self)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False), "utf-8")
        os.replace(tmp, path)


# -------------------------------------------------------------------
# Roles
ROLE_PATTERNS = [
    ("PLAYER", r"^(PLAYER|JUGADOR|ME|YO)$"),
    ("ATC", r"ATIS|TOWER|TWR|TORRE|GROUND|GND|APPROACH|APP|DEPARTURE|DEP|ARRIVAL|ARR|CENTER|CENTRE|"
            r"RADAR|DELIVERY|CLEARANCE|CLR|INFORMATION|CONTROLLER"),
    ("AWACS", r"AWACS|MAGIC|DARKSTAR|OVERLORD|WIZARD|FOCUS|CHALICE|DISCO|SENTRY|E-?3|E-?2"),
    ("TANKER", r"TANKER|TEXACO|ARCO|SHELL|KC-?135|KC-?130"),
    ("FLIGHT", r"^(LEAD|LIDER|LÍDER|WING|WINGMAN|PUNTO|DASH|#?\d)\b|^(TWO|THREE|FOUR)$"),
    ("GROUNDTEAM", r"JTAC|FAC|LOBO|MEDIC|SANITARIO|SOLDIER|TROOP|INFANTRY|SQUAD|TEAM|PLATOON|SECCION|SECCIÓN|"
                   r"PATROL|CONVOY|BASE|FOB|COMMAND|HQ"),
]

ROLE_LABELS = {
    "PLAYER": "Jugador", "ATC": "Control (ATC)", "AWACS": "AWACS", "TANKER": "Cisterna",
    "FLIGHT": "Escuadrilla", "GROUNDTEAM": "Personal en tierra", "EXTERNAL": "Aeronave/otro",
}

ROLE_PROFILE = {
    "PLAYER": "AIR", "ATC": "TOWER", "AWACS": "AIR", "TANKER": "AIR", "FLIGHT": "AIR",
    "GROUNDTEAM": "GROUND", "EXTERNAL": "AIR",
}


def base_name(speaker: str) -> str:
    return re.sub(r"[\s_-]*\d+$", "", speaker).strip()


def role_of(speaker: str) -> str:
    s = speaker.upper().strip()
    for role, pat in ROLE_PATTERNS:
        if re.search(pat, s):
            return role
    return "EXTERNAL"


# Voces por defecto por rol (en orden de preferencia; se evita repetir voz en un guion).
# Las listas se eligieron midiendo inteligibilidad con reconocimiento de voz tras el filtro de radio.
ROLE_POOLS = {
    "ATC": ["kokoro:bm_george", "kokoro:af_heart", "piper:en_US-john-medium", "kokoro:bf_emma",
            "kokoro:am_puck", "kokoro:af_sarah", "kokoro:bm_fable",
            "kokoro:af_bella"],
    "AWACS": ["kokoro:af_bella", "kokoro:am_fenrir", "kokoro:bm_fable", "kokoro:bf_emma"],
    "TANKER": ["piper:en_US-bryce-medium", "kokoro:bm_lewis", "kokoro:am_echo"],
    "FLIGHT": ["kokoro:am_puck", "piper:en_US-joe-medium", "kokoro:am_fenrir", "kokoro:am_liam",
               "kokoro:am_eric", "piper:en_US-ryan-medium"],
    "GROUNDTEAM": ["piper:en_GB-northern_english_male-medium", "kokoro:am_onyx", "piper:en_US-bryce-medium",
                   "kokoro:am_eric", "kokoro:bm_daniel"],
    "EXTERNAL": ["kokoro:am_fenrir", "kokoro:bm_fable", "piper:en_US-joe-medium", "kokoro:bm_lewis",
                 "piper:en_US-libritts_r-medium#55", "kokoro:am_echo", "piper:en_US-libritts_r-medium#104",
                 "kokoro:am_liam", "piper:en_US-libritts_r-medium#117", "kokoro:bm_daniel",
                 "piper:en_US-ryan-medium", "piper:en_US-libritts_r-medium#231", "kokoro:am_eric",
                 "piper:en_US-libritts_r-medium#286", "piper:en_US-libritts_r-medium#291",
                 "piper:en_US-libritts_r-medium#264", "piper:en_US-libritts_r-medium#212"],
}
FALLBACK_POOL = ["kokoro:am_fenrir", "kokoro:am_puck", "kokoro:bm_george", "kokoro:bm_fable",
                 "kokoro:am_liam", "kokoro:am_eric", "kokoro:am_echo", "kokoro:am_onyx",
                 "kokoro:bm_lewis", "kokoro:bm_daniel", "kokoro:bf_emma",
                 "kokoro:af_sarah", "kokoro:af_kore", "kokoro:af_aoede", "kokoro:bf_isabella"]


# Palabras por segundo medidas para cada voz a velocidad 1.0 (tools: medición propia con dos frases de radio).
VOICE_RATE = {
 "kokoro:am_michael": 2.374,
 "kokoro:am_fenrir": 2.628,
 "kokoro:am_puck": 2.584,
 "kokoro:am_echo": 2.808,
 "kokoro:am_eric": 3.154,
 "kokoro:am_liam": 3.051,
 "kokoro:am_onyx": 2.761,
 "kokoro:am_adam": 2.785,
 "kokoro:am_santa": 2.489,
 "kokoro:bm_george": 2.523,
 "kokoro:bm_fable": 2.711,
 "kokoro:bm_lewis": 2.503,
 "kokoro:bm_daniel": 2.934,
 "kokoro:af_heart": 2.623,
 "kokoro:af_bella": 2.494,
 "kokoro:af_nicole": 1.668,
 "kokoro:af_aoede": 2.743,
 "kokoro:af_kore": 2.584,
 "kokoro:af_sarah": 2.7,
 "kokoro:af_nova": 2.971,
 "kokoro:af_alloy": 2.888,
 "kokoro:af_sky": 2.764,
 "kokoro:af_jessica": 3.206,
 "kokoro:af_river": 3.136,
 "kokoro:bf_emma": 2.857,
 "kokoro:bf_isabella": 2.834,
 "kokoro:bf_alice": 2.815,
 "kokoro:bf_lily": 2.859,
 "piper:en_US-joe-medium": 2.855,
 "piper:en_US-john-medium": 2.579,
 "piper:en_US-bryce-medium": 2.118,
 "piper:en_US-ryan-medium": 2.83,
 "piper:en_GB-northern_english_male-medium": 3.681,
 "piper:en_US-libritts_r-medium#55": 3.403,
 "piper:en_US-libritts_r-medium#104": 3.463,
 "piper:en_US-libritts_r-medium#117": 3.403,
 "piper:en_US-libritts_r-medium#231": 3.369,
 "piper:en_US-libritts_r-medium#286": 3.287,
 "piper:en_US-libritts_r-medium#291": 3.536,
 "piper:en_US-libritts_r-medium#264": 4.318,
 "piper:en_US-libritts_r-medium#212": 3.166,
 "piper:en_US-libritts_r-medium#220": 3.585,
 "piper:en_US-libritts_r-medium#29": 3.4,
 "piper:en_US-libritts_r-medium#23": 3.163,
 "piper:en_US-libritts_r-medium#73": 3.169,
 "piper:en_US-libritts_r-medium#108": 3.485,
 "piper:en_US-libritts_r-medium#354": 3.184
}
TARGET_RATE = 2.75          # ritmo de radio objetivo (palabras/s)
ROLE_TEMPO = {"ATC": 1.05, "AWACS": 1.0, "TANKER": 0.97, "FLIGHT": 1.0, "GROUNDTEAM": 1.0, "EXTERNAL": 1.0,
              "PLAYER": 1.0}


def default_speed(voice: str, role: str) -> float:
    r = VOICE_RATE.get(voice)
    sp = TARGET_RATE / r if r else 1.0
    sp *= ROLE_TEMPO.get(role, 1.0)
    return round(min(1.18, max(0.9, sp)), 2)


def assign_default_voices(settings: Settings, speakers: list[str], available: set[str]) -> list[str]:
    """Asigna voz a los hablantes que aún no la tienen. Devuelve los nuevos."""
    new = []
    speakers = sorted(speakers, key=lambda s: (base_name(s) != s and base_name(s) in speakers))
    used = {settings.speakers[s].voice for s in speakers if s in settings.speakers and settings.speakers[s].voice}
    for spk in speakers:
        if spk in settings.speakers and settings.speakers[spk].voice in available:
            continue
        if spk == "PLAYER":
            settings.speakers[spk] = SpeakerSettings(voice=PLAYER_VOICE, speed=default_speed(PLAYER_VOICE, "PLAYER"))
            continue
        b = base_name(spk)
        if b and b != spk and b in settings.speakers and settings.speakers[b].voice in available:
            src = settings.speakers[b]
            settings.speakers[spk] = SpeakerSettings(**asdict(src))
            new.append(spk)
            continue
        role = role_of(spk)
        pool = [v for v in ROLE_POOLS.get(role, []) + FALLBACK_POOL if v in available and v != PLAYER_VOICE]
        choice = next((v for v in pool if v not in used), None)
        pitch = 0.0
        if choice is None:  # se acabaron: repetir con otro tono para diferenciar
            choice = pool[len(used) % len(pool)] if pool else PLAYER_VOICE
            pitch = [-1.5, 1.5, -2.5, 2.5][len(used) % 4]
        used.add(choice)
        settings.speakers[spk] = SpeakerSettings(voice=choice, pitch=pitch, speed=default_speed(choice, role))
        new.append(spk)
    return new
