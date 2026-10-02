"""Measure a recording the way the synth thinks: pitch contour, loudness, spectral envelope.

Used to match creatures to reference samples (see designer.py). numpy/scipy only.
"""
import numpy as np
from scipy.signal import medfilt


def trim(y: np.ndarray, sr: int, floor_db: float = 35) -> np.ndarray:
    """Cut leading/trailing silence (anything `floor_db` under the loudest 10 ms)."""
    w = max(sr // 100, 1)
    rms = np.array([np.sqrt(np.mean(y[i:i + w] ** 2)) for i in range(0, max(len(y) - w, 1), w)])
    db = 20 * np.log10(rms + 1e-9)
    on = np.flatnonzero(db > db.max() - floor_db)
    return y[on[0] * w:(on[-1] + 1) * w] if len(on) else y


def yin(y: np.ndarray, sr: int, fmin: float = 60, fmax: float = 1600, frame: float = 0.03, hop: float = 0.005,
        threshold: float = 0.2) -> tuple[np.ndarray, np.ndarray]:
    """f0 per hop (Hz, 0 = unvoiced) and aperiodicity (0 = perfectly periodic), YIN-style."""
    W, H = int(frame * sr), int(hop * sr)
    tmin, tmax = int(sr / fmax), int(sr / fmin)
    starts = range(0, len(y) - W - tmax, H)
    energy = np.array([np.sum(y[i:i + W] ** 2) for i in starts])
    gate = (energy.max() if len(energy) else 0) * 1e-4          # 40 dB under the loudest frame: silence
    f0, aper = [], []
    for i, e in zip(starts, energy, strict=True):
        if e <= gate:
            f0.append(0.0)
            aper.append(1.0)
            continue
        x = y[i:i + W + tmax]
        head = x[:W]
        cum = np.concatenate([[0], np.cumsum(x ** 2)])
        n = 1 << int(np.ceil(np.log2(len(x) + W)))
        acf = np.fft.irfft(np.fft.rfft(x, n) * np.conj(np.fft.rfft(head, n)), n)[:tmax + 1]
        d = np.sum(head ** 2) + cum[W:W + tmax + 1] - cum[:tmax + 1] - 2 * acf
        d[0] = 0
        cmnd = d * np.arange(len(d)) / np.maximum(np.cumsum(d), 1e-12)
        cmnd[0] = 1
        cand = np.flatnonzero(cmnd[tmin:] < threshold)
        if len(cand):
            t = tmin + cand[0]
            while t + 1 < len(cmnd) and cmnd[t + 1] < cmnd[t]:
                t += 1
            a, b, c = cmnd[t - 1], cmnd[t], cmnd[min(t + 1, len(cmnd) - 1)]
            shift = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) else 0.0
            f0.append(sr / (t + shift))
            aper.append(float(b))
        else:
            f0.append(0.0)
            aper.append(float(np.min(cmnd[tmin:])))
    return np.array(f0), np.array(aper)


def clean_f0(f0: np.ndarray) -> np.ndarray:
    """Fold octave/fifth errors toward the track's centre, median-filter, smooth."""
    voiced = f0 > 0
    if voiced.sum() < 5:
        return f0
    st = np.full(len(f0), np.nan)
    st[voiced] = 12 * np.log2(f0[voiced])
    ref = np.median(st[voiced])
    for k in np.flatnonzero(voiced):
        options = st[k] + np.array([0, -12, 12, -7.02, 7.02, -19.02])
        st[k] = options[np.argmin(np.abs(options - ref) + np.array([0, 1, 1, 1.5, 1.5, 2]))]
    filled = np.where(voiced, st, np.interp(np.arange(len(f0)), np.flatnonzero(voiced), st[voiced]))
    med = medfilt(filled, 11)
    bad = voiced & (np.abs(st - med) > 2.5)
    st[bad] = med[bad]
    sm = np.convolve(np.pad(np.where(voiced, st, med), 3, mode="edge"), np.ones(7) / 7, mode="valid")
    out = np.zeros(len(f0))
    out[voiced] = 2 ** (sm[voiced] / 12)
    return out


def segments(f0: np.ndarray, min_gap: int = 6) -> int:
    """Voiced stretches longer than 40 ms, after closing gaps shorter than `min_gap` hops."""
    v = (f0 > 0).astype(int)
    idx = np.flatnonzero(v)
    for a, b in zip(idx, idx[1:], strict=False):
        if 1 < b - a <= min_gap:
            v[a:b] = 1
    edges = np.diff(np.concatenate([[0], v, [0]]))
    return int(np.sum((np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1)) > 8))


def envelope_db(y: np.ndarray, sr: int, bands: int = 40, fmax: float = 8000) -> np.ndarray:
    """Long-term spectral envelope on a mel-like scale, dB under its peak."""
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    freqs = np.fft.rfftfreq(len(y), 1 / sr)
    edges = 700 * (10 ** np.linspace(np.log10(1 + 100 / 700), np.log10(1 + fmax / 700), bands + 1) - 1)
    e = np.array([spec[(freqs >= lo) & (freqs < hi)].mean() + 1e-20 if np.any((freqs >= lo) & (freqs < hi)) else 1e-20
                  for lo, hi in zip(edges, edges[1:], strict=False)])
    db = 10 * np.log10(e)
    return db - db.max()


def features(y: np.ndarray, sr: int, fmax: float = 8000) -> dict:
    """What matching compares: pitch and loudness contours, envelope, duration, noisiness, syllables."""
    y = trim(np.asarray(y, dtype=np.float64), sr)
    f0, aper = yin(y, sr)
    f0 = clean_f0(f0)
    voiced = f0 > 0
    t = np.linspace(0, 1, 16)
    pos = np.linspace(0, 1, max(len(f0), 2))
    if voiced.sum() > 3:
        pitch = np.interp(t, pos[voiced], 12 * np.log2(f0[voiced] / 100))
    else:
        pitch = np.zeros(16)
    w = max(sr // 100, 1)
    rms = np.array([np.sqrt(np.mean(y[i:i + w] ** 2)) for i in range(0, max(len(y) - w, 1), w)])
    loud = np.interp(t, np.linspace(0, 1, len(rms)), 20 * np.log10(rms / (rms.max() + 1e-12) + 1e-6))
    return {"dur": len(y) / sr, "pitch_st": pitch, "loud_db": loud, "env_db": envelope_db(y, sr, fmax=fmax),
            "aper": float(np.median(aper[voiced])) if voiced.any() else 1.0, "voiced": float(voiced.mean()),
            "segments": segments(f0)}


def distance(a: dict, b: dict) -> float:
    """Weighted mismatch between two feature sets (0 = identical)."""
    pitch = np.mean(np.abs(a["pitch_st"] - b["pitch_st"])) if a["voiced"] > 0.2 and b["voiced"] > 0.2 else 0.0
    return (1.0 * pitch                                               # semitones
            + 0.15 * np.mean(np.abs(a["loud_db"] - b["loud_db"]))    # dB
            + 0.25 * np.mean(np.abs(a["env_db"] - b["env_db"]))      # dB
            + 4.0 * abs(np.log(a["dur"] / b["dur"]))
            + 3.0 * abs(a["aper"] - b["aper"]) + 3.0 * abs(a["voiced"] - b["voiced"])
            + 2.0 * abs(a["segments"] - b["segments"]))
