"""Sound-effect layers of the voice spec: modal bodies, moving noise bands, scattered events.

    Modal    excitation (hits + scrape, low-passed by hardness) -> bank of decaying resonators
    Noise    white/brown noise -> time-varying band/low/high-pass -> envelope (+ turbulence)
    Scatter  seeded random event times (thinning of the rate curve) -> pop | drop | ping each

Like the rest of the renderer, each block is a simple recurrence or a seeded SplitMix64
stream, so engine ports can reproduce it (docs/arquitetura.md).
"""
import numpy as np
from scipy.signal import butter, lfilter

from . import rng
from .spec import Modal, Noise, Scatter

BLOCK = 64


def _envelope(amp, attack: float, release: float, n: int, sr: int) -> np.ndarray:
    from .render import curve
    env = curve(amp, n)
    a, r = min(max(int(attack * sr), 1), n), min(max(int(release * sr), 1), n)
    env[:a] *= np.linspace(0, 1, a) ** 2
    env[n - r:] *= np.linspace(1, 0, r) ** 2
    return env


def resonator(x: np.ndarray, hz: float, t60: float, sr: int) -> np.ndarray:
    """One mode: impulse response r^n sin((n+1)w), unit initial amplitude, -60 dB after t60 seconds."""
    r = 10 ** (-3 / (max(t60, 1e-4) * sr))
    w = 2 * np.pi * hz / sr
    return lfilter([np.sin(w)], [1.0, -2 * r * np.cos(w), r * r], x)


def render_modal(m: Modal, sr: int, k: int) -> np.ndarray:
    n = max(int(m.dur * sr), 16)
    exc = np.zeros(n)
    for i, (t, gain, length) in enumerate(m.hits):
        a, L = int(t * sr), int(length * sr)
        if a >= n:
            continue
        if L < 3:              # an ideal strike: a unit impulse, every mode excited at its own gain
            exc[a] += gain
            continue
        burst = rng.noise(rng.key(k, "hit", i), L) * np.hanning(L) * gain
        exc[a:a + L] += burst[: n - a]
    t0, dur, gain, judder = m.scrape
    if gain and dur:
        a, L = int(t0 * sr), max(int(dur * sr), 2)
        tt = np.arange(L) / sr
        s = rng.noise(rng.key(k, "scrape"), L) * np.sin(np.pi * np.arange(L) / L) ** 2 * gain * 0.3
        if judder:
            s *= 1 + 0.8 * np.sin(2 * np.pi * judder * tt)       # stick-slip chatter
        exc[a:a + L] += s[: max(n - a, 0)]
    exc = lfilter(*butter(1, min(m.hardness, 0.45 * sr) / (sr / 2)), exc)
    out = m.click * exc
    for hz, t60, gain in m.modes:
        if 20 <= hz < 0.45 * sr:
            out = out + gain * resonator(exc, hz, t60, sr)
    if 0 < m.damp < m.dur:                 # damped: -60 dB over the next 0.1 s
        a = int(m.damp * sr)
        out[a:] *= 10 ** (-3 * np.arange(n - a) / (0.1 * sr))
    return m.gain * out / (np.max(np.abs(out)) + 1e-12)


def _filter_coeffs(kind: str, f: float, q: float, sr: int):
    from .render import bandpass_coeffs
    f = min(max(f, 10.0), 0.45 * sr)
    if kind == "band":
        return bandpass_coeffs(f, f / max(q, 0.05), sr)
    w0 = 2 * np.pi * f / sr
    cos, alpha = np.cos(w0), np.sin(w0) / (2 * max(q, 0.05))
    a0 = 1 + alpha
    if kind == "low":
        b = [(1 - cos) / 2, 1 - cos, (1 - cos) / 2]
    elif kind == "high":
        b = [(1 + cos) / 2, -(1 + cos), (1 + cos) / 2]
    else:
        raise ValueError(f"unknown filter {kind!r}")
    return [x / a0 for x in b], [1.0, -2 * cos / a0, (1 - alpha) / a0]


def render_noise(p: Noise, sr: int, k: int) -> np.ndarray:
    from .render import curve, smooth_noise, time_varying
    n = max(int(p.dur * sr), 16)
    x = rng.noise(rng.key(k, "noise"), n)
    if p.color == "brown":
        x = lfilter([1.0], [1.0, -0.997], x)
        x /= np.max(np.abs(x)) + 1e-12
    elif p.color != "white":
        raise ValueError(f"unknown noise color {p.color!r}")
    blocks = (n + BLOCK - 1) // BLOCK
    y = time_varying(x, (_filter_coeffs(p.filter, f, p.q, sr) for f in curve(p.freq, blocks, log=True)), BLOCK)
    env = _envelope(p.amp, p.attack, p.release, n, sr)
    rate, depth = p.wobble
    if depth:
        env *= np.clip(1 + depth * smooth_noise(rng.key(k, "wobble"), n, sr, rate), 0, None)
    y = y * env
    return p.gain * y / (np.max(np.abs(y)) + 1e-12)


def event_times(rate, dur: float, k: int) -> np.ndarray:
    """Seeded event times (seconds) following a rate curve (events/s), by thinning a uniform stream."""
    peak = max(r for _, r in rate)
    m = int(np.ceil(peak * dur))
    if m <= 0:
        return np.zeros(0)
    t = np.sort(rng.uniforms(rng.key(k, "times"), m)) * dur
    keep = rng.uniforms(rng.key(k, "keep"), m) * peak < np.interp(t / dur, *zip(*rate, strict=True))
    return t[keep]


def render_scatter(s: Scatter, sr: int, k: int) -> np.ndarray:
    n = max(int(s.dur * sr), 16)
    out = np.zeros(n)
    times = event_times(s.rate, s.dur, k)
    if not len(times):
        return out
    m = len(times)
    u = [rng.uniforms(rng.key(k, name), m) for name in ("freq", "decay", "level")]
    freq = s.freq[0] * (s.freq[1] / s.freq[0]) ** u[0]
    decay = s.decay[0] + (s.decay[1] - s.decay[0]) * u[1]
    level = s.level[0] + (s.level[1] - s.level[0]) * u[2]
    for i, (t0, f, d, a) in enumerate(zip(times, freq, decay, level, strict=True)):
        start = int(t0 * sr)
        L = min(max(int(5 * d * sr), 8), n - start)
        if L <= 0:
            continue
        tt = np.arange(L) / sr
        env = np.exp(-tt / d)
        if s.event == "pop":         # (at low sample rates a band past Nyquist folds down to just under it)
            f = min(f, 0.29 * sr)
            ev = lfilter(*butter(2, [f / 1.5, min(f * 1.5, 0.45 * sr)], btype="band", fs=sr),
                         rng.noise(rng.key(k, "ev", i), L)) * env
        elif s.event == "drop":      # a bubble: pitch rises as it shrinks
            ev = np.sin(2 * np.pi * f * (tt + tt * tt / (4 * d))) * env
        elif s.event == "ping":      # glassy: two inharmonic partials
            ev = (np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(2 * np.pi * 2.76 * f * tt) * env) * env
        else:
            raise ValueError(f"unknown scatter event {s.event!r}")
        out[start:start + L] += a * ev
    return s.gain * out / (np.max(np.abs(out)) + 1e-12)
