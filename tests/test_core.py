"""Pruebas unitarias rápidas (sin motor de voz)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dcsradio.parser import parse_text, parse_file  # noqa: E402
from dcsradio.textnorm import normalize  # noqa: E402
from dcsradio.keyword import extract_keyword  # noqa: E402
from dcsradio.config import role_of, base_name, Settings, assign_default_voices  # noqa: E402
from dcsradio.pipeline import analyze_tone, resolve_profile  # noqa: E402

EXAMPLE = """== THREAD: Ramp & start-up · Cougar11 · 143.200 · S1 (flag RAMP_GO) ==
[01] LEAD   (firm, calm) · 3 s : Cougar, radio check.
[02] WING 2 (calm)       · 2 s : Two.
[05] PLAYER (calm)       · 2 s : Four.
"""


class ParserTests(unittest.TestCase):
    def test_example(self):
        s = parse_text(EXAMPLE)
        self.assertEqual([(l.speaker, l.number, l.text) for l in s.lines],
                         [("LEAD", "01", "Cougar, radio check."), ("WING 2", "02", "Two."), ("PLAYER", "05", "Four.")])
        self.assertEqual(s.lines[0].tones, ["firm", "calm"])
        self.assertEqual(s.lines[0].est_duration, 3)
        self.assertEqual(len(s.threads), 1)

    def test_variations(self):
        txt = """
# comentario
// otro
==thread 3 — Tower==
  [7]   tower  ( Calm ,  FORMAL )  —  4,5 seg  :   Cougar11, cleared to land.
GROUND 012 (flat) [ground] ~3s: Taxi via Alpha.
ATIS 001 (plano) [TOWER] ~28s : Information Sierra. Time: zero three.
PLAYER 078A (firme) [AIR] ~7s : Affirm.
PLAYER 078B (firme) [AIR] ~7s : Negative.
LEAD 09 (calm) take A · 2 s : Rejoin.
LEAD 09 (calm) take B · 2 s : Rejoin on me.
WING 3 010 (calm) ~2s : Three.
WING 3 010 (calm) ~2s : Three, copy.
esto no es una línea
VIPER 1-1 020 (stressed) ~4s : Viper 1-1, spike! (gritando)
"""
        s = parse_text(txt)
        L = s.lines
        self.assertEqual(L[0].speaker, "TOWER")
        self.assertEqual(L[0].number, "7")
        self.assertEqual(L[0].est_duration, 4.5)
        self.assertEqual(L[0].tones, ["Calm", "FORMAL"])
        self.assertEqual(L[1].effect_tag, "GROUND")
        self.assertEqual(L[2].text, "Information Sierra. Time: zero three.")
        self.assertEqual((L[3].number, L[3].take), ("078A", "A"))
        self.assertEqual((L[4].number, L[4].take), ("078B", "B"))
        self.assertEqual((L[5].take, L[6].take), ("A", "B"))
        self.assertEqual((L[7].speaker, L[7].take, L[8].take), ("WING 3", "A", "B"))
        self.assertEqual(L[9].speaker, "VIPER 1-1")
        self.assertEqual(L[9].text, "Viper 1-1, spike!")  # acotación eliminada
        self.assertTrue(any("ignorada" in w for w in s.warnings))

    def test_no_labels_in_text(self):
        for f in (ROOT / "samples").glob("*.txt"):
            s = parse_file(f)
            for l in s.lines:
                for bad in ("THREAD", "~", "[", "]", "(", ")", " s :"):
                    self.assertNotIn(bad, l.text, f"{f.name}: {l.text}")
                self.assertFalse(l.text.startswith(l.speaker + " "), l.text)

    def test_user_sample_counts(self):
        s = parse_file(ROOT / "samples" / "Levante_M02_EJEMPLO_guion_voces.txt")
        self.assertEqual(len(s.lines), 121)
        self.assertEqual(len(s.threads), 9)
        self.assertEqual(s.warnings, [])
        nums = [l.number for l in s.lines]
        self.assertEqual(len(nums), len(set(nums)))

    def test_60_lines(self):
        s = parse_file(ROOT / "samples" / "prueba_60_lineas.txt")
        self.assertEqual(len(s.lines), 62)  # 60 + 2 tomas extra
        roles = {role_of(x) for x in s.speakers}
        for r in ("PLAYER", "ATC", "AWACS", "TANKER", "FLIGHT", "GROUNDTEAM", "EXTERNAL"):
            self.assertIn(r, roles)


class NormTests(unittest.TestCase):
    def check(self, src, exp):
        self.assertEqual(normalize(src), exp)

    def test_cases(self):
        self.check("Angels 20", "Angels two zero")
        self.check("contact 143.200", "contact one four three decimal two")
        self.check("tune 251.000", "tune two five one decimal zero")
        self.check("climb FL250", "climb flight level two five zero")
        self.check("squawk 4219", "squawk four two one niner")
        self.check("Cougar11", "Cougar one one")
        self.check("Enfield 1-1", "Enfield one one")
        self.check("Talud One-One", "Talud One One")
        self.check("1500 feet", "one thousand five hundred feet")
        self.check("2,500 ft", "two thousand five hundred feet")
        self.check("12000 feet", "one two thousand feet")
        self.check("time 0330Z", "time zero three three zero zulu")
        self.check("BRA 090/25", "bra zero niner zero, two five")
        self.check("Grid 37S DM 521 784", "Grid three seven sierra, delta mike, five two one, seven eight four")
        self.check("9 o'clock", "nine o'clock")
        self.check("nine o'clock, squawk four two one nine", "nine o'clock, squawk four two one niner")
        self.check("fuel 1.3", "fuel one point three")
        self.check("heading 270", "heading two seven zero")
        self.check("QNH 1014", "Q N H one zero one four")
        self.check("TACAN 41X", "TACAN four one x-ray")
        self.check("ATIS and AWACS", "Eight-iss and A-wacks")

    def test_no_digits_left(self):
        for f in (ROOT / "samples").glob("*.txt"):
            for l in parse_file(f).lines:
                self.assertNotRegex(normalize(l.text), r"\d", l.text)


class KeywordTests(unittest.TestCase):
    def test_keywords(self):
        self.assertEqual(extract_keyword("Cougar, radio check."), "RADIOCHECK")
        self.assertEqual(extract_keyword("Rene Mouawad information Sierra. Runway in use two four."), "ATIS")
        self.assertEqual(extract_keyword("Two."), "TWO")
        self.assertEqual(extract_keyword("Talud, break right, flares, flares."), "FLARES")
        self.assertEqual(extract_keyword("anything", "atis"), "ATIS")


class RoleTests(unittest.TestCase):
    def test_roles(self):
        self.assertEqual(role_of("PLAYER"), "PLAYER")
        self.assertEqual(role_of("TOWER2"), "ATC")
        self.assertEqual(role_of("DEP"), "ATC")
        self.assertEqual(role_of("MAGIC"), "AWACS")
        self.assertEqual(role_of("TEXACO"), "TANKER")
        self.assertEqual(role_of("WING 2"), "FLIGHT")
        self.assertEqual(role_of("LOBO6"), "GROUNDTEAM")
        self.assertEqual(role_of("ENFIELD 1-1"), "EXTERNAL")
        self.assertEqual(base_name("TOWER2"), "TOWER")

    def test_assign(self):
        s = Settings()
        s.speakers = {}
        avail = {"kokoro:am_michael", "kokoro:bm_george", "kokoro:am_puck", "kokoro:am_fenrir",
                 "kokoro:af_nicole", "piper:en_US-joe-medium", "kokoro:bm_fable"}
        assign_default_voices(s, ["PLAYER", "TOWER", "TOWER2", "LEAD", "WING 2"], avail)
        self.assertEqual(s.speakers["PLAYER"].voice, "kokoro:am_michael")
        self.assertEqual(s.speakers["TOWER2"].voice, s.speakers["TOWER"].voice)
        self.assertNotEqual(s.speakers["LEAD"].voice, s.speakers["WING 2"].voice)

    def test_tone(self):
        self.assertGreaterEqual(analyze_tone(["urgente", "voz tensa"]).stress, 0.8)
        self.assertTrue(analyze_tone(["tranquilo"]).calm)
        self.assertLess(analyze_tone(["firme", "recuperando la calma"]).stress, 0.5)

    def test_player_always_radio(self):
        s = Settings()
        l = parse_text("PLAYER 001 (calm) [CLEAN] ~2s : Two.").lines[0]
        self.assertEqual(resolve_profile(l, s), "AIR")
        s.no_effects = True
        self.assertEqual(resolve_profile(l, s), "CLEAN")


if __name__ == "__main__":
    unittest.main()
