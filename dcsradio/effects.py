"""Efectos de radio (DSP en numpy/scipy). Todo determinista con semilla por línea."""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict, replace

import numpy as np
from scipy.signal import butter, sosfilt, resample_poly

SR = 44100  # frecuencia de salida


@dataclass
class FxParams:
    enabled: bool = True
    low_hz: float = 300.0
    high_hz: float = 3400.0
    drive: float = 1.5            # saturación (1 = nada)
    compression: float = 0.5      # 0..1
    noise_db: float = -44.0       # nivel de ruido de fondo (dBFS) mientras se transmite
    hum_db: float = -60.0         # zumbido grave (motor/rotor) dentro de banda
    crackle: float = 0.0          # 0..1 estática/chasquidos
    dropouts: float = 0.0         # 0..1 microcortes
    click: bool = True            # clic de micrófono inicio/fin
    squelch_tail: float = 0.12    # s de "kshh" al soltar
    pre_key: float = 0.10         # s de portadora antes de hablar
    breath: float = 0.0           # 0..1 probabilidad/intensidad de respiración
    bitcrush: float = 0.0         # 0..1 degradación digital
    variation: float = 0.35       # 0..1 cuánta variación aleatoria entre líneas

    def to_dict(self):
        return asdict(self)


PROFILES: dict[str, FxParams] = {
    "CLEAN": FxParams(enabled=False, click=False, noise_db=-120, hum_db=-120, squelch_tail=0, pre_key=0),
    "TOWER": FxParams(low_hz=280, high_hz=3500, drive=1.3, compression=0.45, noise_db=-52, hum_db=-75,
                      crackle=0.02, click=True, squelch_tail=0.08, pre_key=0.08),
    "GROUND": FxParams(low_hz=350, high_hz=3150, drive=1.8, compression=0.6, noise_db=-44, hum_db=-72,
                       crackle=0.08, dropouts=0.03, click=True, squelch_tail=0.14, pre_key=0.1, bitcrush=0.06),
    "AIR": FxParams(low_hz=320, high_hz=3300, drive=1.9, compression=0.6, noise_db=-43, hum_db=-52,
                    crackle=0.05, click=True, squelch_tail=0.12, pre_key=0.1),
    "STRESS": FxParams(low_hz=360, high_hz=3100, drive=2.6, compression=0.75, noise_db=-35, hum_db=-48,
                       crackle=0.3, dropouts=0.12, click=True, squelch_tail=0.16, pre_key=0.07,
                       breath=0.8, bitcrush=0.1),
}

PROFILE_NAMES = {
    "AUTO": "Automático",
    "AIR": "Radio de aeronave",
    "GROUND": "Radio de campo (tierra)",
    "TOWER": "Radio ATC / torre (limpia)",
    "STRESS": "Radio con estrés",
    "CLEAN": "Sin efectos",
}


def db(x: float) -> float:
    return 10 ** (x / 20)


def _band(x, lo, hi, sr, order=4):
    sos = butter(order, [max(20, lo), min(hi, sr / 2 - 100)], btype="band", fs=sr, output="sos")
    return sosfilt(sos, x)


def _rms(x):
    return float(np.sqrt(np.mean(np.square(x)) + 1e-12))


def trim_silence(x: np.ndarray, sr: int, thresh_db: float = -55, pad: float = 0.08) -> np.ndarray:
    if len(x) == 0:
        return x
    win = max(1, int(sr * 0.01))
    env = np.sqrt(np.convolve(np.square(x), np.ones(win) / win, mode="same"))
    peak = env.max() if env.max() > 0 else 1
    idx = np.where(env > peak * db(thresh_db))[0]
    if len(idx) == 0:
        return x
    a = max(0, idx[0] - int(pad * sr))          # margen generoso: no cortar consonantes iniciales (/t/, /k/)
    b = min(len(x), idx[-1] + int(pad * 0.75 * sr))
    y = x[a:b].copy()
    f = min(len(y) // 4, int(0.004 * sr))
    if f > 0:
        y[:f] *= np.linspace(0, 1, f)
        y[-f:] *= np.linspace(1, 0, f)
    return y


def to_sr(x: np.ndarray, sr_in: int, sr_out: int = SR) -> np.ndarray:
    if sr_in == sr_out:
        return x.astype(np.float32)
    g = math.gcd(sr_in, sr_out)
    return resample_poly(x, sr_out // g, sr_in // g).astype(np.float32)


def pitch_resample(x: np.ndarray, factor: float) -> np.ndarray:
    """Sube/baja el tono 'factor' acortando/alargando (se compensa con la velocidad del TTS)."""
    if abs(factor - 1.0) < 1e-3:
        return x
    up = 1000
    down = int(round(1000 * factor))
    g = math.gcd(up, down)
    return resample_poly(x, up // g, down // g).astype(np.float32)


def _compress(x, amount, sr):
    if amount <= 0:
        return x
    att, rel = 0.003, 0.08
    env = np.abs(x)
    # seguidor de envolvente simple (vectorizado por bloques)
    a_att, a_rel = math.exp(-1 / (att * sr)), math.exp(-1 / (rel * sr))
    out_env = np.empty_like(env)
    e = 0.0
    # bucle en bloques de 32 muestras para velocidad razonable
    blk = 32
    for i in range(0, len(env), blk):
        m = env[i:i + blk].max()
        a = a_att if m > e else a_rel
        e = a * e + (1 - a) * m if blk == 1 else (a ** blk) * e + (1 - a ** blk) * m
        out_env[i:i + blk] = e
    thr = db(-24)
    ratio = 1 + 7 * amount
    gain = np.ones_like(out_env)
    over = out_env > thr
    gain[over] = (thr * (out_env[over] / thr) ** (1 / ratio)) / out_env[over]
    y = x * gain
    return y / (np.abs(y).max() + 1e-9) * 0.9


def _pink(n, rng):
    w = rng.standard_normal(n)
    # filtro aproximado de ruido rosa (Paul Kellet economy)
    b = np.array([0.049922035, -0.095993537, 0.050612699, -0.004408786])
    a = np.array([1, -2.494956002, 2.017265875, -0.522189400])
    from scipy.signal import lfilter
    p = lfilter(b, a, w)
    return p / (np.abs(p).max() + 1e-9)


def _click(rng, sr, strength=1.0):
    n = int(sr * 0.012)
    t = np.arange(n) / sr
    c = rng.standard_normal(n) * np.exp(-t / 0.0015)
    c += 0.6 * np.sin(2 * np.pi * rng.uniform(900, 1600) * t) * np.exp(-t / 0.003)
    return (c / (np.abs(c).max() + 1e-9) * 0.5 * strength).astype(np.float32)


def _squelch(rng, sr, dur, level):
    n = int(sr * dur)
    if n <= 0:
        return np.zeros(0, np.float32)
    t = np.arange(n) / sr
    s = rng.standard_normal(n) * np.exp(-t / max(0.02, dur / 3))
    s = _band(s, 500, 4500, sr, 2)
    return (s / (np.abs(s).max() + 1e-9) * level).astype(np.float32)


def _breath(rng, sr, intensity):
    dur = rng.uniform(0.28, 0.45)
    n = int(sr * dur)
    t = np.linspace(0, 1, n)
    env = np.sin(np.pi * t) ** 1.5
    b = _band(rng.standard_normal(n), 700, 2600, sr, 2) * env
    return (b / (np.abs(b).max() + 1e-9) * 0.18 * intensity).astype(np.float32)


TARGET_RMS_DB = -18.0  # sonoridad de la voz (zonas con habla), igual para todas las líneas
PEAK_DB = -1.0


def loudness_normalize(x: np.ndarray, sr: int = SR, target_db: float = TARGET_RMS_DB) -> np.ndarray:
    """Iguala la sonoridad (RMS de los tramos con voz) y limita picos suavemente a -1 dBFS."""
    x = x.astype(np.float64)
    if len(x) == 0 or np.abs(x).max() < 1e-9:
        return x.astype(np.float32)
    win = max(1, int(0.02 * sr))
    n = len(x) // win
    if n >= 3:
        fr = np.sqrt(np.mean(x[: n * win].reshape(n, win) ** 2, axis=1))
        act = fr[fr > fr.max() * db(-30)]
        rms = float(np.sqrt(np.mean(act ** 2))) if len(act) else _rms(x)
    else:
        rms = _rms(x)
    x = x * (db(target_db) / (rms + 1e-12))
    t = db(PEAK_DB - 3)
    lim = db(PEAK_DB)
    a = np.abs(x)
    over = a > t
    if over.any():
        x[over] = np.sign(x[over]) * (t + (lim - t) * np.tanh((a[over] - t) / (lim - t)))
    return x.astype(np.float32)


def vary(p: FxParams, rng: np.random.Generator) -> FxParams:
    v = p.variation
    if v <= 0:
        return p
    return replace(
        p,
        low_hz=p.low_hz * (1 + rng.uniform(-0.12, 0.12) * v),
        high_hz=p.high_hz * (1 + rng.uniform(-0.08, 0.08) * v),
        drive=max(1.0, p.drive * (1 + rng.uniform(-0.2, 0.2) * v)),
        noise_db=p.noise_db + rng.uniform(-4, 4) * v,
        hum_db=p.hum_db + rng.uniform(-5, 5) * v,
        crackle=max(0, p.crackle * (1 + rng.uniform(-0.4, 0.4) * v)),
        squelch_tail=max(0, p.squelch_tail * (1 + rng.uniform(-0.35, 0.35) * v)),
        pre_key=max(0, p.pre_key * (1 + rng.uniform(-0.4, 0.4) * v)),
    )


def apply_radio(voice: np.ndarray, p: FxParams, seed: int, sr: int = SR) -> np.ndarray:
    """voice: float32 mono a SR, ya recortado. Devuelve la transmisión completa."""
    rng = np.random.default_rng(seed)
    x = voice.astype(np.float64)
    x = x / (np.abs(x).max() + 1e-9) * 0.8
    if not p.enabled:
        fade = min(len(x) // 4, int(0.005 * sr))
        if fade > 0:
            x[:fade] *= np.linspace(0, 1, fade)
            x[-fade:] *= np.linspace(1, 0, fade)
        return loudness_normalize(x, sr)

    p = vary(p, rng)
    parts = []
    if p.breath > 0 and rng.random() < p.breath:
        parts.append(_breath(rng, sr, p.breath))
        parts.append(np.zeros(int(sr * rng.uniform(0.03, 0.08)), np.float32))
    x = np.concatenate([*parts, x.astype(np.float32)]) if parts else x

    pre = int(sr * p.pre_key)
    post = int(sr * 0.05)
    body = np.concatenate([np.zeros(pre), x, np.zeros(post)])
    n = len(body)

    # Voz: banda + saturación + compresión
    y = _band(body, p.low_hz * 0.8, p.high_hz * 1.15, sr, 2)
    y = np.tanh(y * p.drive) / np.tanh(p.drive)
    y = _compress(y, p.compression, sr)
    if p.bitcrush > 0:
        # degradación: remuestreo a 8 kHz y cuantización ligera
        lo = resample_poly(y, 80, 441)
        bits = 12 - 6 * p.bitcrush
        q = 2 ** bits
        lo = np.round(lo * q) / q
        y = resample_poly(lo, 441, 80)[:n]
        if len(y) < n:
            y = np.pad(y, (0, n - len(y)))

    # Ruido de portadora + zumbido
    noise = _pink(n, rng) * db(p.noise_db) * 2.5
    t = np.arange(n) / sr
    f0 = rng.uniform(85, 125)
    hum = (np.sin(2 * np.pi * f0 * t) + 0.5 * np.sin(2 * np.pi * 2 * f0 * t + 1)
           + 0.35 * np.sin(2 * np.pi * 3.5 * f0 * t)) * db(p.hum_db)
    hum *= 1 + 0.2 * np.sin(2 * np.pi * rng.uniform(3, 7) * t)  # batido de rotor/motor
    y = y + noise + hum

    # Estática / chasquidos
    if p.crackle > 0:
        k = int(p.crackle * 25 * n / sr)
        for _ in range(k):
            i = rng.integers(0, n - 200)
            L = rng.integers(20, 200)
            y[i:i + L] += rng.standard_normal(L) * rng.uniform(0.05, 0.25) * p.crackle
    # Microcortes
    if p.dropouts > 0:
        k = rng.poisson(p.dropouts * 3 * n / sr / 3)
        for _ in range(k):
            i = rng.integers(pre, max(pre + 1, n - 2000))
            L = int(sr * rng.uniform(0.01, 0.04))
            w = np.ones(L)
            w[: L // 2] = np.linspace(1, 0.15, L // 2)
            w[L // 2:] = np.linspace(0.15, 1, L - L // 2)
            y[i:i + L] *= w[: len(y[i:i + L])]

    y = _band(y, p.low_hz, p.high_hz, sr, 4)

    # Clics y cola de squelch
    head = []
    tail = []
    if p.click:
        head = [_click(rng, sr, rng.uniform(0.7, 1.0))]
        tail = [_click(rng, sr, rng.uniform(0.5, 0.9))]
    sq = _squelch(rng, sr, p.squelch_tail, rng.uniform(0.15, 0.3)) if p.squelch_tail > 0 else np.zeros(0)
    out = np.concatenate([*head, y.astype(np.float32), *tail, sq.astype(np.float32)])
    fade = int(0.003 * sr)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    return loudness_normalize(out, sr)
