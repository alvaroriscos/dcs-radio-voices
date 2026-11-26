"""Analizador tolerante de guiones de radio para misiones de DCS World.

Formatos admitidos (con variaciones de espacios, mayúsculas, guiones, etc.):

    == THREAD: Ramp & start-up · Cougar11 · 143.200 · S1 (flag RAMP_GO) ==
    [01] LEAD   (firm, calm) · 3 s : Cougar, radio check.
    ATIS 001 (plano, procedimental) [TOWER] ~28s : Rene Mouawad information...
    PLAYER 078A (firme) [AIR] ~7s : Atalaya, Talud One-One, affirm.

Solo el texto que va tras los dos puntos se convierte en voz.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

EFFECT_TAGS = {
    "AIR": "AIR", "AIRCRAFT": "AIR", "AIRE": "AIR", "COCKPIT": "AIR", "CABINA": "AIR",
    "GROUND": "GROUND", "TIERRA": "GROUND", "FIELD": "GROUND",
    "TOWER": "TOWER", "ATC": "TOWER", "TORRE": "TOWER", "CONTROL": "TOWER",
    "CLEAN": "CLEAN", "LIMPIO": "CLEAN", "NONE": "CLEAN", "DRY": "CLEAN", "NOFX": "CLEAN",
    "STRESS": "STRESS", "STRESSED": "STRESS", "ESTRES": "STRESS", "URGENT": "STRESS",
}

COMMENT_PREFIXES = ("#", "//", ";", "--", "%", "rem ")

_DASHES = "‐‑‒–—―−"
_SEPARATORS = "·•|¦" + _DASHES


@dataclass
class ScriptLine:
    index: int                 # orden en el guion (0..n-1)
    line_no: int               # nº de línea del archivo
    speaker: str               # p. ej. "PLAYER", "WING 2"
    number: str                # tal como viene: "001", "05", "078A"
    take: str                  # "", "A", "B"...
    tones: list[str]           # ["firme", "tranquilo"]
    effect_tag: str            # "", "AIR", "GROUND", "TOWER", "CLEAN", "STRESS"
    est_duration: float | None
    text: str                  # texto original a locutar (sin etiquetas)
    keyword_override: str = ""
    thread_index: int = 0
    thread_title: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def tone_text(self) -> str:
        return ", ".join(self.tones)


@dataclass
class Thread:
    index: int
    title: str
    line_no: int


@dataclass
class ParsedScript:
    path: str
    lines: list[ScriptLine]
    threads: list[Thread]
    warnings: list[str]

    @property
    def speakers(self) -> list[str]:
        seen: list[str] = []
        for ln in self.lines:
            if ln.speaker not in seen:
                seen.append(ln.speaker)
        return seen


def read_text_file(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-16"):
        try:
            if enc == "utf-16" and not raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                continue
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _clean(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.replace(" ", " ").replace("\t", " ").replace("​", "")
    s = s.replace("：", ":")  # dos puntos de ancho completo
    return s


_THREAD_RE = re.compile(r"^\s*={2,}\s*(?:THREAD|HILO)\b\s*[:#.\-·]?\s*(?P<title>.*?)\s*={0,}\s*$", re.I)
_THREAD_NUM_RE = re.compile(r"^\s*(\d{1,3})\b")
_DUR_RE = re.compile(r"(?:^|[\s·•|~≈(])~?\s*(\d+(?:[.,]\d+)?)\s*(?:s|seg|secs?|sec|segundos?|seconds?)\.?(?=$|[\s·•|)\]])", re.I)
_PAREN_RE = re.compile(r"\(([^()]*)\)")
_BRACKET_RE = re.compile(r"\[([^\[\]]*)\]")
_NUM_TOKEN_RE = re.compile(r"^#?(\d{1,4})([A-Za-z]?)$")
_TAKE_RE = re.compile(r"\b(?:take|toma)\s*[:#]?\s*([A-Za-z0-9])\b", re.I)
_KEY_RE = re.compile(r"\{\s*([^{}]+?)\s*\}")
_INLINE_COMMENT_RE = re.compile(r"\s+(?://|#\s).*$")


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _is_comment(s: str) -> bool:
    low = s.lstrip().lower()
    return any(low.startswith(p) for p in COMMENT_PREFIXES)


def _split_meta_text(s: str) -> tuple[str, str] | None:
    """Separa metadatos y texto por el primer ':' que no esté dentro de () o []."""
    depth = 0
    for i, ch in enumerate(s):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        elif ch == ":" and depth == 0:
            meta, text = s[:i], s[i + 1:]
            if meta.strip() and text.strip():
                return meta, text
            return None
    return None


def _parse_meta(meta: str):
    tones: list[str] = []
    effect = ""
    number = ""
    take = ""
    keyword = ""
    warnings: list[str] = []

    for m in _KEY_RE.finditer(meta):
        keyword = m.group(1)
    meta = _KEY_RE.sub(" ", meta)

    m = _TAKE_RE.search(meta)
    if m:
        take = m.group(1).upper()
        meta = meta[:m.start()] + " " + meta[m.end():]

    for m in _PAREN_RE.finditer(meta):
        inner = m.group(1)
        tm = _TAKE_RE.search(inner)
        if tm:
            take = tm.group(1).upper()
            inner = _TAKE_RE.sub("", inner)
        tones += [t.strip() for t in re.split(r"[,/;+]", inner) if t.strip()]
    meta = _PAREN_RE.sub(" ", meta)

    for m in _BRACKET_RE.finditer(meta):
        inner = m.group(1).strip()
        nm = _NUM_TOKEN_RE.match(inner)
        if nm:
            number = nm.group(1) + nm.group(2).upper()
            continue
        key = _strip_accents(inner).upper().replace(" ", "").replace("-", "")
        if key in EFFECT_TAGS:
            effect = EFFECT_TAGS[key]
        elif inner:
            tones.append(inner)  # etiqueta desconocida: se trata como tono
            warnings.append(f"Etiqueta desconocida [{inner}] tratada como tono")
    meta = _BRACKET_RE.sub(" ", meta)

    dur = None
    dm = _DUR_RE.search(meta)
    if dm:
        dur = float(dm.group(1).replace(",", "."))
        meta = meta[:dm.start()] + " " + meta[dm.end():]

    for ch in _SEPARATORS + "~≈":
        meta = meta.replace(ch, " ")
    tokens = meta.split()

    if not number and tokens:
        # Número de línea: último token numérico (o con sufijo de toma)
        for i in range(len(tokens) - 1, -1, -1):
            nm = _NUM_TOKEN_RE.match(tokens[i])
            if nm and i > 0:
                number = nm.group(1) + nm.group(2).upper()
                del tokens[i]
                break
            if nm and i == 0 and len(tokens) > 1:
                number = nm.group(1) + nm.group(2).upper()
                del tokens[0]
                break
    speaker = " ".join(tokens).strip().upper()
    if number and number[-1].isalpha() and not take:
        take = number[-1]
    return speaker, number, take, tones, effect, dur, keyword, warnings


def parse_text(content: str, path: str = "") -> ParsedScript:
    lines: list[ScriptLine] = []
    threads: list[Thread] = []
    warnings: list[str] = []
    cur_thread = Thread(0, "", 0)
    auto_num = 0

    for ln_no, raw in enumerate(content.splitlines(), start=1):
        s = _clean(raw).strip()
        if not s:
            continue
        tm = _THREAD_RE.match(s)
        if tm:
            title = tm.group("title").strip().strip("=").strip()
            cur_thread = Thread(len(threads) + 1, title, ln_no)
            threads.append(cur_thread)
            continue
        if s.startswith("==") or re.fullmatch(r"[=\-_*#~]{3,}", s):
            continue
        if _is_comment(s):
            continue
        split = _split_meta_text(s)
        if not split:
            warnings.append(f"Línea {ln_no} ignorada (no tiene formato 'HABLANTE ... : texto'): {s[:70]}")
            continue
        meta, text = split
        speaker, number, take, tones, effect, dur, kw, w = _parse_meta(meta)
        if not speaker:
            warnings.append(f"Línea {ln_no} ignorada (sin hablante): {s[:70]}")
            continue
        if len(speaker) > 40 or len(speaker.split()) > 4:
            warnings.append(f"Línea {ln_no} ignorada (hablante no reconocible '{speaker[:30]}...'): {s[:60]}")
            continue
        text = _INLINE_COMMENT_RE.sub("", text).strip()
        for m in _KEY_RE.finditer(text):
            kw = m.group(1)
        text = _KEY_RE.sub(" ", text)
        # Nunca leer acotaciones entre paréntesis/corchetes dentro del texto
        stripped = _BRACKET_RE.sub(" ", _PAREN_RE.sub(" ", text))
        if stripped != text:
            w.append("Se quitaron acotaciones entre paréntesis/corchetes del texto")
        text = re.sub(r"\s+", " ", stripped).strip().strip('"“”').strip()
        if not re.search(r"[A-Za-z0-9]", text):
            warnings.append(f"Línea {ln_no} ignorada (texto vacío)")
            continue
        auto_num += 1
        if not number:
            number = f"{auto_num:03d}"
            w.append("Sin número en el guion: numerada automáticamente")
        sl = ScriptLine(
            index=len(lines), line_no=ln_no, speaker=speaker, number=number, take=take,
            tones=tones, effect_tag=effect, est_duration=dur, text=text,
            keyword_override=kw, thread_index=cur_thread.index, thread_title=cur_thread.title,
            warnings=w,
        )
        lines.append(sl)
        for x in w:
            warnings.append(f"Línea {ln_no}: {x}")

    # Tomas repetidas (mismo hablante y número sin letra) -> A, B, C...
    groups: dict[tuple[int, str, str], list[ScriptLine]] = {}
    for l in lines:
        groups.setdefault((l.thread_index, l.speaker, l.number), []).append(l)
    for (_, _, _), grp in groups.items():
        if len(grp) > 1 and all(not g.take for g in grp):
            for i, g in enumerate(grp):
                g.take = chr(ord("A") + i)
    return ParsedScript(path=str(path), lines=lines, threads=threads, warnings=warnings)


def parse_file(path: str | Path) -> ParsedScript:
    return parse_text(read_text_file(path), str(path))


def thread_number(title: str, idx: int) -> int:
    m = _THREAD_NUM_RE.match(title or "")
    return int(m.group(1)) if m else idx
