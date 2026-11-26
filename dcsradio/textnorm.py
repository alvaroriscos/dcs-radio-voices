"""Normalización de texto con fraseología aeronáutica (inglés).

Convierte cifras y abreviaturas a como se dicen por radio:
  "143.200"     -> "one four three decimal two"
  "FL250"       -> "flight level two five zero"
  "Angels 20"   -> "angels two zero"
  "1500 feet"   -> "one thousand five hundred feet"
  "Cougar11"    -> "Cougar one one"
  "0330Z"       -> "zero three three zero zulu"
  "9"           -> "niner"
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

DIGITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
NATO = {
    "A": "alfa", "B": "bravo", "C": "charlie", "D": "delta", "E": "echo", "F": "foxtrot",
    "G": "golf", "H": "hotel", "I": "india", "J": "juliett", "K": "kilo", "L": "lima",
    "M": "mike", "N": "november", "O": "oscar", "P": "papa", "Q": "quebec", "R": "romeo",
    "S": "sierra", "T": "tango", "U": "uniform", "V": "victor", "W": "whiskey",
    "X": "x-ray", "Y": "yankee", "Z": "zulu",
}

# Diccionario por defecto (editable por el usuario en la app).
# Clave: palabra tal como aparece (sensible a mayúsculas si está en mayúsculas).
DEFAULT_LEXICON: dict[str, str] = {
    "PRI": "primary",
    "AUX": "aux",
    "ATIS": "Eight-iss",
    "AWACS": "A-wacks",
    "JOC": "jock",
    "SAM": "sam",
    "RTB": "R T B",
    "IFF": "I F F",
    "RWR": "R W R",
    "AGL": "A G L",
    "MSL": "M S L",
    "QNH": "Q N H",
    "QFE": "Q F E",
    "LZ": "L Z",
    "PZ": "P Z",
    "ILS": "I L S",
    "VOR": "V O R",
    "NDB": "N D B",
    "IP": "I P",
    "CAS": "C A S",
    "CAP": "cap",
    "BRA": "bra",
    "BDA": "B D A",
    "FAC": "fack",
    "ETA": "E T A",
    "kt": "knots",
    "kts": "knots",
    "nm": "miles",
    "NM": "miles",
    "km": "kilometers",
}


@dataclass
class NormOptions:
    niner: bool = True              # 9 -> "niner"
    nine_words_to_niner: bool = True  # "nine" escrito -> "niner" (salvo "nine o'clock")
    decimal_word: str = "decimal"   # frecuencias: "decimal" o "point"
    lexicon: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_LEXICON))


def _d(ch: str, o: NormOptions) -> str:
    if ch == "9" and o.niner:
        return "niner"
    return DIGITS[int(ch)]


def digits(s: str, o: NormOptions) -> str:
    return " ".join(_d(c, o) for c in s if c.isdigit())


def icao_altitude(n: int, o: NormOptions) -> str:
    """1500 -> one thousand five hundred; 12000 -> one two thousand; 250 -> two hundred fifty? no: two five zero."""
    if n >= 1000 and n % 100 == 0:
        th, rest = divmod(n, 1000)
        parts = [digits(str(th), o), "thousand"]
        if rest:
            parts += [_d(str(rest // 100), o), "hundred"]
        return " ".join(parts)
    if 100 <= n < 1000 and n % 100 == 0:
        return f"{_d(str(n // 100), o)} hundred"
    return digits(str(n), o)


def _freq(intpart: str, dec: str, o: NormOptions) -> str:
    dec = dec.rstrip("0") or "0"
    return f"{digits(intpart, o)} {o.decimal_word} {digits(dec, o)}"


def normalize(text: str, o: NormOptions | None = None) -> str:
    o = o or NormOptions()
    t = text
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"[‐-―−]", "-", t)
    t = t.replace("…", "...")

    # Diccionario (palabras completas). Primero entradas con mayúsculas exactas.
    for k in sorted(o.lexicon, key=len, reverse=True):
        v = o.lexicon[k]
        if not k:
            continue
        flags = 0 if any(c.isupper() for c in k) else re.I
        t = re.sub(r"(?<![\w-])" + re.escape(k) + r"(?![\w-])", lambda m, v=v: v, t, flags=flags)

    # Posiciones horarias: "9 o'clock" -> "nine o'clock" (se dicen como palabras)
    CLOCK = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]
    t = re.sub(r"\b(1[0-2]|0?[1-9])\s*(o'?clock)\b", lambda m: CLOCK[int(m.group(1))] + " " + m.group(2), t, flags=re.I)
    # "9 line" / "9-line" (formato de CAS) se dice "nine-line"
    t = re.sub(r"\b9[\s-]?line\b", "nine-line", t, flags=re.I)
    # MGRS / Grid: "grid 37S DM 521 784", "grid 37 S DM 521784", "grid KN 123 456"
    def grid(m):
        zone, band, sq, e, n = m.group("zone"), m.group("band"), m.group("sq"), m.group("e"), m.group("n")
        out = [m.group("kw")]
        if zone:
            out.append(digits(zone, o) + " " + NATO[band.upper()] + ",")
        out.append(" ".join(NATO[c.upper()] for c in sq) + ",")
        if n is None and len(e) % 2 == 0:
            e, n = e[: len(e) // 2], e[len(e) // 2:]
        out.append(digits(e, o) + ("," if n else ""))
        if n:
            out.append(digits(n, o))
        return " ".join(out)
    t = re.sub(r"(?P<kw>\bgrid)\s+(?:(?P<zone>\d{1,2})\s?(?P<band>[C-HJ-NP-X])\s?)?(?P<sq>[A-HJ-NP-Z]{2})\s?(?P<e>\d{2,10})(?:\s+(?P<n>\d{2,5}))?\b",
               grid, t, flags=re.I)

    # Flight level
    t = re.sub(r"\bFL\s?(\d{2,3})\b", lambda m: "flight level " + digits(m.group(1), o), t, flags=re.I)
    t = re.sub(r"\bflight level\s+(\d{2,3})\b", lambda m: "flight level " + digits(m.group(1), o), t, flags=re.I)
    # Angels / cherubs
    t = re.sub(r"\b(angels|cherubs)\s+(\d{1,2})\b", lambda m: m.group(1) + " " + digits(m.group(2), o), t, flags=re.I)
    # Hora zulú: 0330Z, 03:30Z
    t = re.sub(r"\b(\d{2}):?(\d{2})\s?(Z|zulu)\b", lambda m: digits(m.group(1) + m.group(2), o) + " zulu", t, flags=re.I)
    t = re.sub(r"\b(\d{1,2}):(\d{2})\b", lambda m: digits(m.group(1).zfill(2) + m.group(2), o), t)
    # Rumbo/distancia: 090/25, 270/08
    t = re.sub(r"\b(\d{3})\s?/\s?(\d{1,3})\b", lambda m: digits(m.group(1), o) + ", " + digits(m.group(2), o), t)
    # Altitudes en pies (ICAO): 1500 feet, 2,500 ft
    t = re.sub(r"\b(\d{1,2})[,.]?(\d{3})\s?(feet|foot|ft)\b",
               lambda m: icao_altitude(int(m.group(1) + m.group(2)), o) + " feet", t, flags=re.I)
    t = re.sub(r"\b(\d{3})\s?(feet|ft)\b", lambda m: icao_altitude(int(m.group(1)), o) + " feet", t, flags=re.I)
    # Frecuencias (3 dígitos . decimales) y radiales
    t = re.sub(r"\b([1-3]\d{2})[.,](\d{1,3})\b", lambda m: _freq(m.group(1), m.group(2), o), t)
    # Frecuencias FM/HF de 2 dígitos con unidad
    t = re.sub(r"\b(\d{1,2})[.,](\d{1,3})\s?(MHz|megahertz|FM|AM)\b",
               lambda m: _freq(m.group(1), m.group(2), o) + " " + m.group(3), t, flags=re.I)
    t = re.sub(r"\bMHz\b", "megahertz", t, flags=re.I)
    # Otros decimales: 1.3 -> one point three
    t = re.sub(r"\b(\d+)[.,](\d+)\b", lambda m: digits(m.group(1), o) + " point " + digits(m.group(2), o), t)
    # Callsign con cifras pegadas: Cougar11 -> Cougar one one ; Enfield1-1
    t = re.sub(r"\b([A-Za-z]{3,})(\d{1,3})(?:-(\d{1,2}))?\b",
               lambda m: m.group(1) + " " + digits(m.group(2) + (m.group(3) or ""), o), t)
    # 1-1, 2-1 (callsign/elemento)
    t = re.sub(r"\b(\d{1,2})-(\d{1,2})\b", lambda m: digits(m.group(1), o) + " " + digits(m.group(2), o), t)
    # Número de ala: #2 -> number two
    t = re.sub(r"#(\d+)", lambda m: "number " + digits(m.group(1), o), t)
    # Grados: 270° -> two seven zero degrees
    t = re.sub(r"(\d+)\s?°", lambda m: digits(m.group(1), o) + " degrees", t)
    # Canal TACAN: 77X -> seven seven x-ray
    t = re.sub(r"\b(\d{1,3})([XY])\b", lambda m: digits(m.group(1), o) + " " + NATO[m.group(2)], t)
    # Cualquier otro número: dígito a dígito
    t = re.sub(r"\d+", lambda m: digits(m.group(0), o), t)
    # Números escritos con guion: One-One -> One One
    num_words = "zero|one|two|three|four|five|six|seven|eight|nine|niner"
    t = re.sub(rf"\b({num_words})-(?=({num_words})\b)", r"\1 ", t, flags=re.I)
    if o.nine_words_to_niner:
        t = re.sub(r"\bnine\b(?!\s+o'?clock|-line)", lambda m: "Niner" if m.group(0)[0].isupper() else "niner", t, flags=re.I)
    # Siglas sueltas en mayúsculas de 2-4 letras que no estén en el diccionario: deletrear
    def spell(m):
        w = m.group(0)
        return " ".join(w)
    t = re.sub(r"\b(?:[B-DF-HJ-NP-TV-Z]{2,4})\b", spell, t)  # sin vocales -> siglas seguras
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+([,.!?;])", r"\1", t)
    return t
