"""Voice spec -> audio.

Signal flow per syllable:
    source (glottal saw | sine | pulse | noise) with pitch contour, vibrato, jitter
    -> subharmonics, breath, ring modulation
    -> time-varying formant bank (parallel band-passes, coefficients updated every 64 samples)
    -> envelope (attack/release, amp curve, growl AM, pulse trains)
Then for the whole voice: sum syllables + chip programs -> 40 Hz high-pass -> crush
-> saturation -> reverb -> normalise to `gain`.

Every block is a simple per-sample recurrence (one-pole, biquad, PolyBLEP) or a seeded
SplitMix64 stream, so engine ports can reproduce it.
"""
import numpy as np
from scipy.signal import butter, fftconvolve, lfilter, sosfilt

from . import rng
from .chip import render_program
from .spec import Curve, Syllable, Voice

DEFAULT_SR = 48_000
BLOCK = 64          # formant coefficient update interval, samples
PEAK = 0.89         # -1 dBFS


def curve(points: Curve, n: int, log: bool = False) -> np.ndarray:
    t = np.linspace(0.0, 1.0, n)
    xs, ys = zip(*points, strict=True)
    ys = np.log(np.maximum(ys, 1e-9)) if log else np.asarray(ys, float)
    out = np.interp(t, xs, ys)
    return np.exp(out) if log else out


def smooth_noise(k: int, n: int, sr: int, rate: float) -> np.ndarray:
    """Random wander in [-1, 1] with about `rate` control points per second."""
    points = max(2, int(n / sr * rate) + 2)
    return np.interp(np.linspace(0, points - 1, n), np.arange(points), rng.noise(k, points))


def _polyblep(t: np.ndarray, dt: np.ndarray) -> np.ndarray:
    out = np.zeros_like(t)
    m = t < dt
    x = t[m] / dt[m]
    out[m] = 2 * x - x * x - 1
    m = t > 1 - dt
    x = (t[m] - 1) / dt[m]
    out[m] = x * x + 2 * x + 1
    return out


def _source(s: Syllable, f0: np.ndarray, sr: int, k: int) -> np.ndarray:
    n = len(f0)
    cycles = np.cumsum(f0 / sr)
    t, dt = cycles % 1.0, np.minimum(f0 / sr, 0.5)
    if s.source == "sine":
        x = np.sin(2 * np.pi * cycles) + 0.12 * np.sin(4 * np.pi * cycles)
    elif s.source == "pulse":
        w = s.pulse_width
        x = np.where(t < w, 1.0, -1.0) + _polyblep(t, dt) - _polyblep((t - w) % 1.0, dt)
    elif s.source == "noise":
        x = rng.noise(rng.key(k, "source"), n) * 0.8
    elif s.source == "glottal":  # band-limited saw, darkened by a one-pole tilt filter
        x = 2 * t - 1 - _polyblep(t, dt)
    else:
        raise ValueError(f"unknown source {s.source!r}")
    if s.source in ("glottal", "pulse"):
        fc = min(float(np.median(f0)) * (1.5 + 40 * s.brightness ** 2), 0.45 * sr)
        x = lfilter(*butter(1, fc / (sr / 2)), x)
    if s.sub:
        x = x * (1 + s.sub * np.cos(np.pi * cycles))  # energy at f0/2: growly period doubling
    if s.breath:
        x = x * (1 - s.breath) + s.breath * rng.noise(rng.key(k, "breath"), n) * 0.7
    hz, mix = s.ring
    if mix:
        x = x * (1 - mix + mix * np.sin(2 * np.pi * hz * np.arange(n) / sr))
    return x


def time_varying(x: np.ndarray, coeffs, block: int) -> np.ndarray:
    """Second-order filter whose (b, a) coefficients change every `block` samples.

    Between blocks we carry the Direct Form I history (last two inputs and outputs) and
    rebuild lfilter's state for the new coefficients; reusing lfilter's own state across a
    coefficient change would click.
    """
    y = np.empty_like(x)
    x1 = x2 = y1 = y2 = 0.0
    for i, (b, a) in enumerate(coeffs):
        k = i * block
        seg = x[k:k + block]
        if not len(seg):
            break
        b0, b1, b2 = (list(b) + [0.0, 0.0])[:3]
        _, a1, a2 = (list(a) + [0.0, 0.0])[:3]
        zi = [b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2, b2 * x1 - a2 * y1]
        out, _ = lfilter([b0, b1, b2], [1.0, a1, a2], seg, zi=zi)
        y[k:k + len(seg)] = out
        if len(seg) >= 2:
            x1, x2, y1, y2 = seg[-1], seg[-2], out[-1], out[-2]
        else:
            x1, x2, y1, y2 = seg[-1], x1, out[-1], y1
    return y


def bandpass_coeffs(f: float, bw: float, sr: int):
    """RBJ band-pass with 0 dB peak gain."""
    f = min(f, 0.45 * sr)
    w0 = 2 * np.pi * f / sr
    alpha = np.sin(w0) * min(bw, f) / (2 * f)
    a0 = 1 + alpha
    return [alpha / a0, 0.0, -alpha / a0], [1.0, -2 * np.cos(w0) / a0, (1 - alpha) / a0]


def _formants(x: np.ndarray, s: Syllable, sr: int) -> np.ndarray:
    if not s.formants:
        return x
    n = len(x)
    blocks = (n + BLOCK - 1) // BLOCK
    scale = curve(s.mouth, blocks, log=True)
    out = np.zeros(n)
    for hz, bw, gain in s.formants:  # constant-Q as the mouth moves
        out += gain * time_varying(x, (bandpass_coeffs(hz * m, bw * m, sr) for m in scale), BLOCK)
    return out


def render_syllable(s: Syllable, sr: int, k: int) -> np.ndarray:
    n = max(int(s.dur * sr), 16)
    t = np.arange(n) / sr
    f0 = curve(s.pitch, n, log=True)
    rate, depth = s.vibrato
    wander = s.jitter * smooth_noise(rng.key(k, "jitter"), n, sr, 25) if s.jitter else 0.0
    f0 = np.clip(f0 * 2 ** ((depth * np.sin(2 * np.pi * rate * t) + wander) / 12), 1.0, 0.49 * sr)
    x = _formants(_source(s, f0, sr, k), s, sr)

    env = curve(s.amp, n)
    a, r = min(max(int(s.attack * sr), 1), n), min(max(int(s.release * sr), 1), n)
    env[:a] *= np.linspace(0, 1, a) ** 2
    env[n - r:] *= np.linspace(1, 0, r) ** 2
    depth, rate = s.rough
    if depth:
        wobble = np.sin(2 * np.pi * rate * t + 3 * smooth_noise(rng.key(k, "rough"), n, sr, 8))
        env *= 1 - depth * (0.5 + 0.5 * wobble)
    rate, depth, sharp = s.pulses
    if depth:
        env *= 1 - depth + depth * (0.5 - 0.5 * np.cos(2 * np.pi * rate * t)) ** sharp
    x = x * env
    return s.gain * x / (np.max(np.abs(x)) + 1e-12)


def _crush(x: np.ndarray, amount: float) -> np.ndarray:
    hold = 1 + int(amount * 11)
    x = np.repeat(x[::hold], hold)[: len(x)]
    levels = 2 ** (14 - 10 * amount)
    return np.round(x * levels) / levels


def _reverb(x: np.ndarray, sr: int, seconds: float, wet: float, k: int) -> np.ndarray:
    n = int(seconds * sr)
    ir = rng.noise(k, n) * np.exp(-6.9 * np.arange(n) / n)
    ir = sosfilt(butter(2, 5000 / (sr / 2), output="sos"), ir)
    dry = np.concatenate([x, np.zeros(n)])
    tail = fftconvolve(dry, ir)[: len(dry)]
    return (1 - wet) * dry + wet * tail * (np.max(np.abs(x)) / (np.max(np.abs(tail)) + 1e-12))


def render(voice: Voice, sr: int = DEFAULT_SR) -> np.ndarray:
    """Render a voice to mono float32 in [-1, 1]."""
    parts = []
    for i, s in enumerate(voice.syllables):
        parts.append((int(s.start * sr), render_syllable(s, sr, rng.key(voice.seed, "syllable", i))))
    for c in voice.chips:
        y = render_program(c, sr)
        parts.append((int(c.start * sr), c.gain * y / (np.max(np.abs(y)) + 1e-12)))
    if voice.speech:
        from .speech.klatt import render_speech  # the speech module builds on this one
        for i, p in enumerate(voice.speech):
            parts.append((int(p.start * sr), render_speech(p, sr, rng.key(voice.seed, "speech", i))))
    if not parts:
        raise ValueError("voice has no syllables, chip programs or speech")
    out = np.zeros(max(k + len(y) for k, y in parts))
    for k, y in parts:
        out[k:k + len(y)] += y
    out = sosfilt(butter(2, 40 / (sr / 2), btype="high", output="sos"), out)
    out /= np.max(np.abs(out)) + 1e-12
    if voice.crush:
        out = _crush(out, voice.crush)
    if voice.drive:
        out = np.tanh(voice.drive * out) / np.tanh(voice.drive)
    if voice.space:
        out = _reverb(out, sr, voice.space, voice.wet, rng.key(voice.seed, "space"))
    fade = min(int(0.004 * sr), len(out))
    out[len(out) - fade:] *= np.linspace(1, 0, fade)
    return (PEAK * voice.gain * out / (np.max(np.abs(out)) + 1e-12)).astype(np.float32)
