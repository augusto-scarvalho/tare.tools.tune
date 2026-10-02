"""Formant speech synthesiser in the style of Klatt's cascade/parallel design.

    voicing (band-limited glottal saw, spectral tilt, jitter) + aspiration
        -> nasal pole -> nasal zero -> F1 -> F2 -> F3 -> F4 -> F5      (cascade: vowels, sonorants)
    frication noise -> two band-pass resonances + flat bypass          (parallel: fricatives, bursts)

Parameters arrive as frame tracks (see SpeechProgram); filter coefficients are updated
every BLOCK samples with the filter state carried across, amplitudes per sample.
"""
import numpy as np
from scipy.signal import butter, lfilter, sosfilt

from .. import rng
from ..render import _polyblep, bandpass_coeffs, smooth_noise, time_varying
from ..spec import SpeechProgram

BLOCK = 48
FRIC_GAIN = 2.8   # fricatives ~-13 dB (s) to ~-21 dB (f) under the vowel, as in natural speech


def _resonator_coeffs(f, bw, sr):
    c = -np.exp(-2 * np.pi * bw / sr)
    b = 2 * np.exp(-np.pi * bw / sr) * np.cos(2 * np.pi * f / sr)
    return 1 - b - c, b, c


def _klatt(f, bw, sr, anti):
    a, b, c = _resonator_coeffs(f, bw, sr)
    return ([1 / a, -b / a, -c / a], [1.0]) if anti else ([a], [1.0, -b, -c])


def _cascade_stage(x, f, bw, sr, anti=False):
    """Klatt resonator (unity DC gain) or antiresonator, coefficients per block."""
    return time_varying(x, (_klatt(fi, bi, sr, anti) for fi, bi in zip(f, bw, strict=True)), BLOCK)


def _bandpass(x, f, bw, sr):
    """Peak-normalised band-pass, coefficients per block."""
    return time_varying(x, (bandpass_coeffs(fi, bi, sr) for fi, bi in zip(f, bw, strict=True)), BLOCK)


def render_speech(p: SpeechProgram, sr: int, k: int) -> np.ndarray:
    tr = {name: np.asarray(v, dtype=float) for name, v in p.frames.items()}
    n_frames = len(tr["f0"])
    n = max(int(n_frames / p.frame_rate * sr), BLOCK)
    frame_t = np.arange(n_frames) / p.frame_rate

    def per_sample(name):
        return np.interp(np.arange(n) / sr, frame_t, tr[name])

    blocks = (n + BLOCK - 1) // BLOCK

    def per_block(name):
        return np.interp((np.arange(blocks) * BLOCK + BLOCK / 2) / sr, frame_t, tr[name])

    f0 = per_sample("f0")
    if p.jitter:
        f0 = f0 * 2 ** (p.jitter * smooth_noise(rng.key(k, "jitter"), n, sr, 30) / 12)
    f0 = np.clip(f0, 20.0, 0.45 * sr)
    cycles = np.cumsum(f0 / sr)
    ph, dt = cycles % 1.0, np.minimum(f0 / sr, 0.5)
    voice = 2 * ph - 1 - _polyblep(ph, dt)
    voice = lfilter(*butter(1, min(p.tilt, 0.45 * sr) / (sr / 2)), voice)
    if p.sub:
        voice = voice * (1 + p.sub * np.cos(np.pi * cycles))
    av, ah, af, ab = per_sample("av"), per_sample("ah"), per_sample("af"), per_sample("ab")
    pulse = 0.5 + 0.5 * np.cos(2 * np.pi * ph)            # aspiration/frication swell with each glottal cycle
    voiced = np.clip(av * 2, 0, 1)
    aspiration = rng.noise(rng.key(k, "aspiration"), n) * (1 - 0.6 * voiced + 0.6 * voiced * pulse)
    x = av * voice + ah * aspiration * 0.7

    x = _cascade_stage(x, per_block("fnp"), np.full(blocks, 100.0), sr)
    x = _cascade_stage(x, per_block("fnz"), np.full(blocks, 100.0), sr, anti=True)
    for j in range(1, 6):
        x = _cascade_stage(x, np.minimum(per_block(f"f{j}"), 0.45 * sr), per_block(f"b{j}"), sr)

    noise = rng.noise(rng.key(k, "frication"), n) * (1 - 0.5 * voiced + 0.5 * voiced * pulse)
    fric = af * noise
    par = (per_sample("ga") * _bandpass(fric, per_block("fa"), per_block("wa"), sr)
           + per_sample("gb") * _bandpass(fric, per_block("fb"), per_block("wb"), sr))
    flat = sosfilt(butter(2, 1200 / (sr / 2), btype="high", output="sos"), fric) * ab * 0.5
    out = x + FRIC_GAIN * (par + flat)

    depth, rate = p.rough
    if depth:
        t = np.arange(n) / sr
        out *= 1 - depth * (0.5 + 0.5 * np.sin(2 * np.pi * rate * t + 3 * smooth_noise(rng.key(k, "rough"), n, sr, 8)))
    out = sosfilt(butter(2, 60 / (sr / 2), btype="high", output="sos"), out)
    return p.gain * out / (np.max(np.abs(out)) + 1e-12)
