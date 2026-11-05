"""Loudness as people hear it (ITU-R BS.1770: integrated LUFS) and the true peak, at any sample rate.

LUFS is what streaming services and game audio specs set targets in; it is gated in 400 ms blocks, so a sound shorter
than that has none (``None``): measure UI clicks and hits by their peak instead.
"""
import numpy as np
from scipy.signal import resample_poly, sosfilt

BLOCK, STEP = 0.4, 0.1          # seconds: 400 ms blocks, 75 % overlap
ABSOLUTE_GATE, RELATIVE_GATE = -70.0, -10.0


def k_weighting(sr: int) -> np.ndarray:
    """The K-weighting filter as second-order sections for `sr`: a +4 dB shelf above ~1.7 kHz (the head) and a
    high-pass at ~38 Hz. Designed per rate (libebur128's derivation), so it equals the standard's 48 kHz table."""
    k = np.tan(np.pi * 1681.974450955533 / sr)
    q = 0.7071752369554196
    vh = 10 ** (3.999843853973347 / 20)
    vb = vh ** 0.4996667741545416
    a0 = 1 + k / q + k * k
    shelf = [(vh + vb * k / q + k * k) / a0, 2 * (k * k - vh) / a0, (vh - vb * k / q + k * k) / a0,
             1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0]
    k = np.tan(np.pi * 38.13547087602444 / sr)
    q = 0.5003270373238773
    a0 = 1 + k / q + k * k
    highpass = [1.0, -2.0, 1.0, 1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0]
    return np.array([shelf, highpass])


def integrated_lufs(audio: np.ndarray, sr: int) -> float | None:
    """Integrated loudness in LUFS (mono or stereo, every channel weighted 1), or None under 400 ms or in silence."""
    x = np.asarray(audio, dtype=np.float64)
    x = x[:, None] if x.ndim == 1 else x
    block, step = round(BLOCK * sr), round(STEP * sr)
    if len(x) < block:
        return None
    power = sosfilt(k_weighting(sr), x, axis=0) ** 2
    cum = np.concatenate([np.zeros((1, x.shape[1])), np.cumsum(power, axis=0)])
    starts = np.arange(0, len(x) - block + 1, step)
    z = ((cum[starts + block] - cum[starts]) / block).sum(axis=1)     # mean square per block, channels summed
    with np.errstate(divide="ignore"):
        loud = -0.691 + 10 * np.log10(z)
    kept = z[loud > ABSOLUTE_GATE]
    if not len(kept):
        return None
    relative = -0.691 + 10 * np.log10(kept.mean()) + RELATIVE_GATE
    kept = z[(loud > ABSOLUTE_GATE) & (loud > relative)]
    return float(-0.691 + 10 * np.log10(kept.mean()))


def true_peak_db(audio: np.ndarray) -> float:
    """The peak between samples too (4x oversampled), in dBTP: what a converter or an encoder may clip."""
    x = np.asarray(audio, dtype=np.float64)
    peak = np.max(np.abs(resample_poly(x, 4, 1, axis=0))) if len(x) else 0.0
    return float(20 * np.log10(max(peak, 1e-12)))


def measure(audio: np.ndarray, sr: int) -> dict:
    """The two numbers a manifest carries, rounded: {"lufs": ... or None, "true_peak_db": ...}."""
    lufs = integrated_lufs(audio, sr)
    return {"lufs": None if lufs is None else round(lufs, 2), "true_peak_db": round(true_peak_db(audio), 2)}
