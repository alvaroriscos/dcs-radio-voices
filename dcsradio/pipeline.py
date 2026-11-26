"""Generación de audio: línea -> voz -> efectos -> OGG + manifiesto."""
from __future__ import annotations

import csv
import math
import re
import zlib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from . import effects as fx
from .config import Settings, SpeakerSettings, role_of, ROLE_PROFILE, PLAYER_VOICE, assign_default_voices
from .engines import TTSManager, voice_catalog
from .keyword import extract_keyword, sanitize
from .parser import ParsedScript, ScriptLine
from .textnorm import NormOptions, normalize

SR = fx.SR

TONE_RULES = [
    # (palabras, estrés 0..1, mult. velocidad, semitonos, calma)
    (r"urgen|p[aá]nic|grit|shout|scream|alarm|desesper|mayday|emergenc", 0.85, 1.12, 0.8, False),
    (r"stress|estres|nervio|nervous|tens[oa]?\b|tense|agitad|agitat|excit|r[aá]pid|fast|hurr|apurad|insist|alert", 0.6, 1.08, 0.5, False),
    (r"cansad|tired|resign|aburrid|bored|exhaust|agotad", 0.0, 0.94, -0.5, False),
    (r"juvenil|young|espont[aá]ne|divert|fun|amus|ir[oó]nic|ironic|bromist|happy|alegr|aliviad|relieved", 0.0, 1.03, 0.4, False),
    (r"dud|hesit|disgust|a disgusto|reluct", 0.0, 0.96, -0.2, False),
    (r"calm|tranquil|relaj|relax|plano|flat|formal|procedim|profesional|professional|fr[ií]o|cold|concis|seren", 0.0, 1.0, 0.0, True),
    (r"firm|firme|tajante|decid|assert|command|autorit", 0.1, 1.0, 0.0, False),
]


@dataclass
class ToneInfo:
    stress: float = 0.0
    speed: float = 1.0
    pitch: float = 0.0
    calm: bool = False


def analyze_tone(tones: list[str]) -> ToneInfo:
    t = ToneInfo()
    joined = " ".join(tones).lower()
    for pat, stress, speed, pitch, calm in TONE_RULES:
        if re.search(pat, joined):
            t.stress = max(t.stress, stress)
            t.speed *= speed
            t.pitch += pitch
            t.calm = t.calm or calm
    if "recuper" in joined or "recover" in joined:  # "recuperando la calma"
        t.stress = min(t.stress, 0.3)
    if t.stress >= 0.5:
        t.calm = False
    t.speed = min(1.2, max(0.85, t.speed))
    return t


@dataclass
class RenderedLine:
    line: ScriptLine
    audio: np.ndarray
    spoken: str
    voice: str
    profile: str
    filename: str = ""
    keyword: str = ""


def line_seed(line: ScriptLine, settings: Settings) -> int:
    key = f"{settings.seed}|{line.speaker}|{line.number}|{line.take}|{line.text}"
    return zlib.crc32(key.encode("utf-8"))


def speaker_settings(settings: Settings, speaker: str) -> SpeakerSettings:
    sp = settings.speakers.get(speaker)
    if sp is None or not sp.voice:
        sp = SpeakerSettings(voice=PLAYER_VOICE if speaker == "PLAYER" else "kokoro:am_fenrir")
    return sp


def resolve_profile(line: ScriptLine, settings: Settings, override: str = "") -> str:
    if settings.no_effects:
        return "CLEAN"
    if override and override != "AUTO":
        return override
    sp = settings.speakers.get(line.speaker)
    tone = analyze_tone(line.tones)
    if line.effect_tag:
        prof = line.effect_tag
    elif sp and sp.profile != "AUTO":
        prof = sp.profile
    else:
        prof = ROLE_PROFILE.get(role_of(line.speaker), "AIR")
        if tone.stress >= 0.6 and prof in ("AIR", "GROUND"):
            prof = "STRESS"
    if line.speaker == "PLAYER" and settings.force_player_radio and prof == "CLEAN":
        prof = "AIR"
    return prof


def fx_params_for(line: ScriptLine, settings: Settings, profile: str) -> fx.FxParams:
    p = replace(fx.PROFILES.get(profile, fx.PROFILES["AIR"]))
    if not p.enabled:
        return p
    tone = analyze_tone(line.tones)
    if profile != "STRESS" and tone.stress >= 0.5:
        p = replace(p, noise_db=p.noise_db + 4, crackle=p.crackle + 0.12, breath=max(p.breath, 0.35),
                    dropouts=p.dropouts + 0.04)
    if tone.calm and profile in ("AIR", "TOWER", "GROUND"):
        p = replace(p, noise_db=p.noise_db - 3, crackle=p.crackle * 0.5, dropouts=p.dropouts * 0.5)
    k = max(0.0, settings.fx_intensity)
    if k <= 0.01:
        return replace(p, enabled=False)
    p = replace(p, noise_db=p.noise_db + 20 * math.log10(k), hum_db=p.hum_db + 20 * math.log10(k),
                crackle=p.crackle * k, dropouts=p.dropouts * k, drive=1 + (p.drive - 1) * k,
                bitcrush=min(1, p.bitcrush * k), variation=settings.variation)
    if not settings.mic_clicks:
        p = replace(p, click=False, squelch_tail=0)
    if not settings.breathing:
        p = replace(p, breath=0)
    return p


def norm_options(settings: Settings) -> NormOptions:
    return NormOptions(niner=settings.niner, nine_words_to_niner=settings.niner,
                       decimal_word=settings.decimal_word, lexicon=dict(settings.lexicon))


def render_line(tts: TTSManager, line: ScriptLine, settings: Settings, override: str = "") -> RenderedLine:
    sp = speaker_settings(settings, line.speaker)
    spoken = normalize(line.text, norm_options(settings))
    tone = analyze_tone(line.tones)
    rng = np.random.default_rng(line_seed(line, settings))
    v = settings.variation
    pitch_semi = sp.pitch + tone.pitch + rng.uniform(-0.3, 0.3) * v
    pf = 2 ** (pitch_semi / 12)
    speed = sp.speed * tone.speed * (1 + rng.uniform(-0.03, 0.03) * v)
    audio, sr = tts.synthesize(spoken, sp.voice, speed / pf)
    audio = fx.trim_silence(audio, sr)
    audio = fx.to_sr(audio, sr, SR)
    audio = fx.pitch_resample(audio, pf)
    profile = resolve_profile(line, settings, override)
    params = fx_params_for(line, settings, profile)
    out = fx.apply_radio(audio, params, line_seed(line, settings), SR)
    out = np.clip(out * sp.volume, -1, 1).astype(np.float32)
    return RenderedLine(line=line, audio=out, spoken=spoken, voice=sp.voice, profile=profile)


def write_ogg(path: Path, audio: np.ndarray, quality: float):
    # libsndfile: compression_level 0 = máxima calidad, 1 = mínima.
    # Se escribe por bloques: el codificador Vorbis de libsndfile reserva memoria en la pila en
    # proporción al bloque y con bloques grandes revienta en hilos secundarios.
    level = float(min(1, max(0, 1 - quality)))
    tmp = path.with_name(path.name + ".part")
    with sf.SoundFile(str(tmp), "w", SR, 1, format="OGG", subtype="VORBIS",
                      compression_level=level) as f:
        for i in range(0, len(audio), 4096):
            f.write(audio[i:i + 4096])
    tmp.replace(path)


def ogg_frames(path: Path) -> int:
    with sf.SoundFile(str(path)) as f:
        n = f.frames
        if n <= 0 or n > 10**10:
            n = len(f.read(dtype="float32"))
    return n


def callsign_words(script: ParsedScript) -> set[str]:
    from .keyword import find_callsigns
    words = set()
    for s in script.speakers:
        words.update(w for w in re.split(r"\W+", s) if w)
    words |= find_callsigns([l.text for l in script.lines])
    return words


def build_filenames(rendered: list[RenderedLine], script: ParsedScript):
    numbers: dict[tuple[str, str], int] = {}
    for r in rendered:
        k = (r.line.number, r.line.take)
        numbers[k] = numbers.get(k, 0) + 1
    dup = any(c > 1 for c in numbers.values())
    cw = callsign_words(script)
    used: set[str] = set()
    for r in rendered:
        l = r.line
        num = l.number
        if l.take and not num.upper().endswith(l.take.upper()):
            num += l.take
        if dup:
            num = f"{l.thread_index:02d}-{num}"
        kw = extract_keyword(l.text, l.keyword_override, cw)
        dur = len(r.audio) / SR
        spk = sanitize(l.speaker.replace(" ", ""), 20)
        name = f"{spk} {num} {kw} {max(1, math.ceil(dur - 1e-6))}s.ogg"
        base = name
        i = 2
        while name.lower() in used:
            name = base.replace(".ogg", f" ({i}).ogg")
            i += 1
        used.add(name.lower())
        r.filename = name
        r.keyword = kw


ProgressCb = Callable[[int, int, str], None]
LogCb = Callable[[str, str], None]


def generate_all(script: ParsedScript, settings: Settings, out_dir: str | Path,
                 tts: TTSManager | None = None, progress: ProgressCb | None = None,
                 log: LogCb | None = None, cancel: Callable[[], bool] | None = None,
                 overrides: dict[int, str] | None = None) -> dict:
    tts = tts or TTSManager()
    progress = progress or (lambda i, n, m: None)
    log = log or (lambda lvl, m: None)
    cancel = cancel or (lambda: False)
    overrides = overrides or {}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = sanitize(Path(script.path).stem, 60) if script.path else "GUION"
    stem = Path(script.path).stem if script.path else "guion"

    avail = {v.id for v in voice_catalog()}
    for s in assign_default_voices(settings, script.speakers, avail):
        log("info", f"Hablante nuevo '{s}': voz por defecto {settings.speakers[s].voice}")

    n = len(script.lines)
    rendered: list[RenderedLine] = []
    errors = 0
    for i, line in enumerate(script.lines):
        if cancel():
            log("warn", "Generación cancelada por el usuario")
            return {"cancelled": True}
        progress(i, n, f"{line.speaker} {line.number}: {line.text[:50]}")
        try:
            r = render_line(tts, line, settings, overrides.get(line.index, ""))
            rendered.append(r)
        except Exception as e:  # registrar y seguir
            errors += 1
            log("error", f"Línea {line.line_no} ({line.speaker} {line.number}): {e}")
    if not rendered:
        raise RuntimeError("No se generó ninguna línea")

    build_filenames(rendered, script)
    gap = int(round(settings.gap_seconds * SR))
    rows = []
    pos = 0
    pieces = []
    for j, r in enumerate(rendered):
        if j > 0:
            pieces.append(np.zeros(gap, np.float32))
            pos += gap
        start = pos
        pieces.append(r.audio)
        pos += len(r.audio)
        rows.append((r, start, pos))

    result = {"lines": len(rendered), "errors": errors, "out_dir": str(out_dir)}
    lines_dir = out_dir / "lineas"
    if settings.out_individual:
        lines_dir.mkdir(exist_ok=True)
        for k, (r, _, _) in enumerate(rows):
            progress(n + k, n * 2, f"Guardando {r.filename}")
            write_ogg(lines_dir / r.filename, r.audio, settings.ogg_quality)
    combined_name = f"{stem} - COMPLETO.ogg"
    if settings.out_combined:
        progress(2 * n - 1, 2 * n, "Guardando archivo único…")
        write_ogg(out_dir / combined_name, np.concatenate(pieces), settings.ogg_quality)
        result["combined"] = str(out_dir / combined_name)
    if settings.out_manifest:
        mpath = out_dir / f"{stem} - manifiesto.csv"
        with open(mpath, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["archivo", "hablante", "numero", "toma", "hilo", "tono", "efecto", "voz",
                        "palabra_clave", "texto", "texto_locutado", "duracion_s", "inicio_s", "fin_s",
                        "inicio_muestra", "fin_muestra", "frecuencia_muestreo", "archivo_unico"])
            for r, a, b in rows:
                l = r.line
                w.writerow([r.filename, l.speaker, l.number, l.take, l.thread_title, l.tone_text, r.profile,
                            r.voice, r.keyword, l.text, r.spoken, f"{(b - a) / SR:.3f}", f"{a / SR:.3f}",
                            f"{b / SR:.3f}", a, b, SR, combined_name if settings.out_combined else ""])
        result["manifest"] = str(mpath)
    progress(2 * n, 2 * n, "Terminado")
    result["rows"] = [(r.filename, a, b) for r, a, b in rows]
    return result


def preview_line(tts: TTSManager, line: ScriptLine, settings: Settings, path: Path, override: str = "") -> RenderedLine:
    avail = {v.id for v in voice_catalog()}
    assign_default_voices(settings, [line.speaker], avail)
    r = render_line(tts, line, settings, override)
    sf.write(str(path), r.audio, SR, subtype="PCM_16")
    return r
