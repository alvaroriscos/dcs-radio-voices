"""Verifica una carpeta de salida: huecos, duraciones, nombres y (opcional) inteligibilidad por ASR.

Uso: python tests/verify_output.py CARPETA_SALIDA [--asr] [--gap 2.5]
(--asr requiere faster-whisper instalado; solo para pruebas de desarrollo)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

NAME_RE = re.compile(r"^[A-Z0-9]+ (\d{2}-)?\d{1,4}[A-Z]? [A-Z0-9]{1,14} \d+s( \(\d+\))?\.ogg$")


def wer(ref: str, hyp: str) -> float:
    r = norm_words(ref)
    h = norm_words(hyp)
    d = np.zeros((len(r) + 1, len(h) + 1), dtype=int)
    d[:, 0] = range(len(r) + 1)
    d[0, :] = range(len(h) + 1)
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + (r[i - 1] != h[j - 1]))
    return d[len(r), len(h)] / max(1, len(r))


WORD2D = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
          "seven": "7", "eight": "8", "nine": "9", "niner": "9", "to": "2", "too": "2", "for": "4", "won": "1"}
EQUIV = {"alpha": "alfa", "ok": "okay", "juliet": "juliett", "xray": "x-ray", "talad": "talud",
         "eight-iss": "atis", "eightiss": "atis", "a-wacks": "awacs"}


def norm_words(s: str) -> list[str]:
    """Forma canónica para comparar texto locutado y transcripción: números en cifras,
    siglas letra a letra, sin puntuación."""
    s = s.lower()
    s = re.sub(r"(\d),(\d{3})", r"\1\2", s)                 # 5,000 -> 5000
    s = re.sub(r"(\d)-(\d)", r"\1 \2", s)
    s = re.sub(r"(\d)-?e?r\b", r"\1", s)                    # 9-er, 1009r -> 9
    s = s.replace("-", " ")
    s = re.sub(r"[^a-z0-9' ]", " ", s)
    toks = [EQUIV.get(w, w) for w in s.split()]
    out: list[str] = []
    i = 0
    while i < len(toks):
        w = toks[i]
        # "two thousand five hundred" -> 2500
        if w in WORD2D and i + 1 < len(toks) and toks[i + 1] in ("thousand", "hundred"):
            val = int(WORD2D[w]) * (1000 if toks[i + 1] == "thousand" else 100)
            i += 2
            if i + 1 < len(toks) and toks[i] in WORD2D and toks[i + 1] == "hundred":
                val += int(WORD2D[toks[i]]) * 100
                i += 2
            out.extend(list(str(val)))
            continue
        if w.isdigit():
            out.extend(list(w))
        elif w in WORD2D and w not in ("to", "too", "for", "won"):
            out.append(WORD2D[w])
        elif w in ("to", "too", "for", "won") and ((out and out[-1].isdigit()) or (
                i + 1 < len(toks) and (toks[i + 1].isdigit() or toks[i + 1] in WORD2D))):
            out.append(WORD2D[w])
        elif len(w) == 1 and w.isalpha():
            out.append(w)
        else:
            out.append(w)
        i += 1
    # siglas: "r t b" y "rtb" -> r t b
    final = []
    for w in out:
        if len(w) <= 4 and w.isalpha() and w in ("rtb", "qnh", "ils", "vfr", "bda", "agl", "lz", "iff", "bra"):
            final.extend(list(w))
        else:
            final.append(w)
    # homófonos que ningún reconocedor distingue: two/to/too, four/for, one/won
    homo = {"2": "to", "too": "to", "4": "for", "1": "one", "won": "one", "readback": "read", "read": "read"}
    final = [homo.get(w, w) for w in final]
    return [w for w in final if w != "back"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--asr", action="store_true")
    ap.add_argument("--gap", type=float, default=2.5)
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    out = Path(a.out)
    manifest = next(out.glob("* - manifiesto.csv"))
    rows = list(csv.DictReader(open(manifest, encoding="utf-8-sig")))
    combined = out / rows[0]["archivo_unico"]
    sr = int(rows[0]["frecuencia_muestreo"])
    big, sr2 = sf.read(str(combined), dtype="float32")
    assert sr2 == sr
    problems = []
    gap_n = int(round(a.gap * sr))

    # 1. nombres
    for r in rows:
        if not NAME_RE.match(r["archivo"]):
            problems.append(f"Nombre no cumple formato: {r['archivo']}")
        m = re.search(r" (\d+)s(?: \(\d+\))?\.ogg$", r["archivo"])
        if m and int(m.group(1)) < float(r["duracion_s"]) - 1e-6:
            problems.append(f"Duración del nombre menor que la real: {r['archivo']} {r['duracion_s']}")

    # 2. duraciones de archivos individuales vs manifiesto
    max_diff = 0
    for r in rows:
        f = out / "lineas" / r["archivo"]
        x, s = sf.read(str(f), dtype="float32")
        n = int(r["fin_muestra"]) - int(r["inicio_muestra"])
        diff = abs(len(x) - n)
        max_diff = max(max_diff, diff)
        if diff > 0:
            problems.append(f"Duración archivo != manifiesto: {r['archivo']} {len(x)} vs {n} muestras")
        if abs(float(r["duracion_s"]) - len(x) / s) > 0.0015:
            problems.append(f"duracion_s no coincide: {r['archivo']}")
        # el trozo del archivo único debe ser el mismo audio
        seg = big[int(r["inicio_muestra"]):int(r["fin_muestra"])]
        if len(seg) == len(x):
            corr = float(np.corrcoef(seg, x)[0, 1]) if len(x) > 10 else 1
            if corr < 0.98:
                problems.append(f"Audio en archivo único no coincide con {r['archivo']} (corr {corr:.3f})")

    # 3. huecos exactos y silenciosos
    gaps = []
    for r0, r1 in zip(rows, rows[1:]):
        g = int(r1["inicio_muestra"]) - int(r0["fin_muestra"])
        gaps.append(g)
        if g != gap_n:
            problems.append(f"Hueco de {g} muestras ({g / sr:.4f} s) entre {r0['archivo']} y {r1['archivo']}")
        seg = big[int(r0["fin_muestra"]) + int(0.02 * sr): int(r1["inicio_muestra"]) - int(0.02 * sr)]
        if len(seg) and np.abs(seg).max() > 10 ** (-60 / 20):
            problems.append(f"Hueco no silencioso tras {r0['archivo']}: pico {20 * np.log10(np.abs(seg).max()):.1f} dB")
    if len(big) != int(rows[-1]["fin_muestra"]):
        problems.append(f"Longitud archivo único {len(big)} != fin último {rows[-1]['fin_muestra']}")
    # silencio real medido en el archivo único (umbral -50 dB)
    measured = []
    thr = 10 ** (-50 / 20)
    for r0, r1 in zip(rows, rows[1:]):
        a0, b1 = int(r0["inicio_muestra"]), int(r1["fin_muestra"])
        e0 = int(r0["fin_muestra"]); s1 = int(r1["inicio_muestra"])
        # extiende hacia fuera mientras sea silencio
        i = e0
        while i > a0 and abs(big[i - 1]) < thr:
            i -= 1
        j = s1
        while j < b1 and abs(big[j]) < thr:
            j += 1
        measured.append((j - i) / sr)

    report = {
        "lineas": len(rows), "problemas": problems, "max_diff_muestras": max_diff,
        "huecos_manifiesto_s": sorted(set(round(g / sr, 6) for g in gaps)),
        "hueco_medido_min_s": round(min(measured), 4) if measured else None,
        "hueco_medido_max_s": round(max(measured), 4) if measured else None,
        "duracion_total_s": round(len(big) / sr, 3),
    }

    if a.asr:
        from faster_whisper import WhisperModel
        from scipy.signal import resample_poly
        model = WhisperModel("small.en", device="cpu", compute_type="int8")
        wers = []
        tags = set()
        for r in rows:
            for t in re.split(r"[,\s]+", r["tono"]):
                if len(t) > 3:
                    tags.add(t.lower())
        for r in rows:
            x, s = sf.read(str(out / "lineas" / r["archivo"]), dtype="float32")
            x16 = resample_poly(x, 160, 441).astype(np.float32)
            segs, _ = model.transcribe(x16, beam_size=5, language="en", condition_on_previous_text=False)
            hyp = " ".join(sg.text for sg in segs).strip()
            w = wer(r["texto_locutado"], hyp)
            hw = set(norm_words(hyp))
            ref = set(norm_words(r["texto_locutado"])) | set(norm_words(r["texto"]))
            leaked = sorted((hw - ref) & (tags | {"thread", "player", "seconds", "tono", "effect"}))
            wers.append({"archivo": r["archivo"], "wer": round(w, 3), "ref": r["texto_locutado"],
                         "asr": hyp, "fugas": leaked, "voz": r["voz"]})
            if leaked:
                problems.append(f"Posible etiqueta leída en {r['archivo']}: {leaked}")
        report["wer_medio"] = round(float(np.mean([w["wer"] for w in wers])), 4)
        report["wer_detalle"] = wers
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1, ensure_ascii=False), "utf-8")
    short = {k: v for k, v in report.items() if k != "wer_detalle"}
    print(json.dumps(short, indent=1, ensure_ascii=False))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
