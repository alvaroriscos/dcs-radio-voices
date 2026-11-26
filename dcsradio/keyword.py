"""Palabra clave automática para el nombre de cada archivo."""
from __future__ import annotations

import re
import unicodedata

# (expresión, CLAVE) por orden de prioridad: lo más específico primero.
PATTERNS: list[tuple[str, str]] = [
    (r"\binformation\s+[a-z]+\b.*\b(runway|wind|qnh|altimeter)", "ATIS"),
    (r"\bradio check\b", "RADIOCHECK"),
    (r"\bgood aircraft\b", "GOODAIRCRAFT"),
    (r"\bcleared for take ?off\b|\btake ?off\b", "TAKEOFF"),
    (r"\bcleared to land\b|\brequest landing\b|\blanding\b", "LANDING"),
    (r"\bshort final\b", "FINAL"),
    (r"\bmissile\b|\blaunch\b", "LAUNCH"),
    (r"\bspike\b|\bdefending\b|\bnotching\b|\bchaff\b", "DEFENDING"),
    (r"\bcleared hot\b|\bin hot\b", "CLEAREDHOT"),
    (r"\btroops in contact\b|\btic\b", "TIC"),
    (r"\bgood hits\b|\bbda\b", "BDA"),
    (r"\btype (one|two|three|1|2|3) control\b|\btarget\b|\bnine-?line\b|\b9[ -]?line\b", "TARGET"),
    (r"\bpre-?contact\b|\bdisconnect\b|\bfuel flowing\b|\bcleared contact\b|\bthe gas\b", "REFUEL"),
    (r"\bpicture\b", "PICTURE"),
    (r"\bbandits?\b|\bbogeys?\b|\bhostile\b", "BANDITS"),
    (r"\bcommitting\b|\bcommit\b", "COMMIT"),
    (r"\bbullseye\b", "BULLSEYE"),
    (r"\bflares?\b", "FLARES"),
    (r"\bbreak (left|right|south|north|east|west)\b", "BREAK"),
    (r"\bmanpads\b|\bthreat\b|\bsam\b", "THREAT"),
    (r"\bcasualty\b|\bcasevac\b|\bmedevac\b|\bstretcher\b|\bwounded\b", "CASEVAC"),
    (r"\bdenied\b", "DENIED"),
    (r"\boverride\b", "OVERRIDE"),
    (r"\bfuel\b|\bbingo\b|\bjoker\b", "FUEL"),
    (r"\bfence (in|out)\b|\bfenced\b", "FENCE"),
    (r"\bweapons? (safe|hot|free|tight)\b", "WEAPONS"),
    (r"\bshut ?down\b", "SHUTDOWN"),
    (r"\bdebrief\b", "DEBRIEF"),
    (r"\bcoffee\b", "COFFEE"),
    (r"\bpax\b|\bpassengers?\b|\boff-?load\b|\bcargo\b|\bloads?\b", "CARGO"),
    (r"\breadback correct\b", "READBACK"),
    (r"\bradar contact\b", "RADAR"),
    (r"\bchecking in\b|\bcheck in\b", "CHECKIN"),
    (r"\bsquawk\b", "SQUAWK"),
    (r"\btraffic\b|\btally\b|\bvisual\b|\bin sight\b|\bno joy\b", "TRAFFIC"),
    (r"\brejoin\b", "REJOIN"),
    (r"\bhold position\b", "HOLD"),
    (r"\bon station\b", "ONSTATION"),
    (r"\brunway\b.*\bclosed\b", "RUNWAYCLOSED"),
    (r"\bcontact\b", "FREQ"),
    (r"\btaxi\b|\bholding point\b|\bhold short\b", "TAXI"),
    (r"\bdeparture\b|\bdepart\b", "DEPARTURE"),
    (r"\bapproach\b|\binbound\b|\bfive miles\b|\bten miles\b", "INBOUND"),
    (r"\brtb\b|\breturn(ing)? to base\b|\bR T B\b", "RTB"),
    (r"\bclimb\b|\bdescend\b|\bmaintain\b", "ALTITUDE"),
    (r"\bheading\b|\bproceed\b|\bdirect\b", "HEADING"),
    (r"\bpush\b|\bswitch\b|\bfrequency\b|\bcontact\b", "FREQ"),
    (r"\brolling\b|\blifting\b|\bairborne\b", "ROLLING"),
    (r"\bready\b", "READY"),
    (r"\bstand ?by\b", "STANDBY"),
    (r"\bsay again\b", "SAYAGAIN"),
    (r"\bstatus\b", "STATUS"),
    (r"\bno damage\b|\bclear\b", "CLEAR"),
    (r"\baffirm(ative)?\b", "AFFIRM"),
    (r"\bnegative\b", "NEGATIVE"),
    (r"\bwilco\b", "WILCO"),
    (r"\b(roger|copy|copies)\b", "COPY"),
    (r"\bup\b", "UP"),
]

STOP = set("""a an the and or but to of on in at for with from by is are be been it this that these those
you your we our i me my he him his she her they them their there here so if then than as up down out
over all any some no not yes go ahead lead two one three four five six seven eight nine niner zero ten
flight good morning day sir please now just get got do does did have has had will would can could
call ready""".split())


def _ascii(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def sanitize(s: str, maxlen: int = 14) -> str:
    s = _ascii(s).upper()
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s[:maxlen] or "LINE"


_NUMW = r"(?:\d|one|two|three|four|five|six|seven|eight|nine|niner|zero|flight\b)"


def find_callsigns(texts: list[str]) -> set[str]:
    """Palabras que funcionan como indicativo: 'Cougar11', 'Talud One-One', 'Cougar flight'..."""
    found: dict[str, int] = {}
    for t in texts:
        for m in re.finditer(r"\b([A-Z][a-z]{2,})\s*-?\s*(?=" + _NUMW + ")", _ascii(t), flags=0):
            w = m.group(1).lower()
            found[w] = found.get(w, 0) + 1
        m = re.match(r"\s*([A-Z][a-z]{2,}),", _ascii(t))  # "Cougar, radio check."
        if m:
            w = m.group(1).lower()
            found[w] = found.get(w, 0) + 1
    generic = {"runway", "heading", "angels", "flight", "climb", "descend", "fuel", "squawk", "grid", "push",
               "time", "wind", "type", "parking", "track", "contact", "tower", "ground", "magic", "lead"}
    return {w for w, c in found.items() if c >= 2 and w not in generic}


def extract_keyword(text: str, override: str = "", callsign_words: set[str] | None = None) -> str:
    if override:
        return sanitize(override)
    low = _ascii(text).lower()
    for pat, key in PATTERNS:
        if re.search(pat, low, flags=re.I):
            return key
    callsign_words = {w.lower() for w in (callsign_words or set())}
    for w in re.findall(r"[A-Za-z][A-Za-z'-]+", _ascii(text)):
        lw = w.lower()
        if lw in STOP or lw in callsign_words or len(lw) < 3:
            continue
        return sanitize(w)
    words = re.findall(r"[A-Za-z]+", _ascii(text))
    return sanitize(words[0]) if words else "LINE"
