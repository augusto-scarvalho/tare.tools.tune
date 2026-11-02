"""Optional authoring DSP. These PCM/Score effects do not change portable Voice behavior."""
import numpy as np
from scipy.signal import resample_poly

from .diagnostics import current


def fm_tone(freq=440, duration=0.6, sr=48000, *, ratio=3.5, index=4.0, decay=0.3, gain=0.3):
    """Oversampled two-operator FM with a decaying index; duration includes its final fade."""
    values = (freq, duration, ratio, index, decay, gain)
    if not all(np.isfinite(v) for v in values) or not 0 < duration <= 180 or not 0 < freq < sr * 0.45:
        raise ValueError("FM needs finite parameters, positive frequency, and duration <= 180 seconds")
    if not 0 < ratio <= 16 or not 0 <= index <= 16 or decay < 0 or not 0 <= gain <= 1:
        raise ValueError("FM ratio/index/decay/gain is outside its supported range")
    if freq * (1 + ratio * (index + 2)) >= 2 * sr:
        raise ValueError("FM sidebands exceed the supported oversampling range")
    n = max(1, round(duration * sr))
    t = np.arange(n * 4) / (sr * 4)
    modulation = index * np.exp(-t / decay) if decay else index
    y = np.sin(2 * np.pi * freq * t + modulation * np.sin(2 * np.pi * freq * ratio * t))
    y = resample_poly(y, 1, 4)[:n]
    attack, release = min(n, round(sr * 0.005)), min(n, round(sr * 0.03))
    if attack:
        y[:attack] *= np.linspace(0, 1, attack)
    if release:
        y[-release:] *= np.linspace(1, 0, release)
    return (y * gain).astype(np.float32)


def apply_effects(audio, sr, effects, *, loop=False, fixed=None):
    original_ndim = np.asarray(audio).ndim
    y = np.asarray(audio, dtype=np.float64).copy()
    if y.ndim == 1:
        y = y[:, None]
    if not np.isfinite(y).all():
        raise ValueError("effects require finite samples")
    ordered = sorted(effects, key=lambda e: e.get("type") == "limiter")
    for i, effect in enumerate(ordered):
        kind = effect.get("type")
        allowed = {"chorus": {"type", "rate", "depth", "mix", "voices"},
                   "limiter": {"type", "ceiling", "release"}}
        if kind not in allowed or set(effect) - allowed[kind]:
            raise ValueError("unknown effect or option")
        if not all(np.isfinite(v) for k, v in effect.items() if k != "type"):
            raise ValueError("effect parameters must be finite")
        if kind == "chorus":
            rate, depth, mix, voices = (effect.get(k, d) for k, d in
                                        (("rate", 0.8), ("depth", 0.004), ("mix", 0.4), ("voices", 2)))
            if not 0 < rate <= 10 or not 0 <= depth <= 0.02 or not 0 <= mix <= 1 or voices not in (1, 2, 3, 4):
                raise ValueError("chorus parameters are outside their supported ranges")
            if loop and len(y):
                rate = max(1, round(rate * len(y) / sr)) / (len(y) / sr)
            dry, wet = y.copy(), np.zeros_like(y)
            t = np.arange(len(y))
            for ch in range(y.shape[1]):
                for voice in range(voices):
                    delay = (0.02 + (0.5 + 0.5 * np.sin(2 * np.pi * rate * t / sr
                             + 2 * np.pi * (voice / voices + ch * 0.25))) * depth) * sr
                    positions = t - delay
                    if loop and len(y):
                        positions %= len(y)
                        wet[:, ch] += np.interp(positions, np.arange(len(y) + 1), np.r_[dry[:, ch], dry[0, ch]])
                    else:
                        wet[:, ch] += np.interp(positions, t, dry[:, ch], left=0, right=0)
            y = dry * (1 - mix) + wet * (mix / voices)
        else:
            ceiling, release = effect.get("ceiling", 0.95), effect.get("release", 0.05)
            if not 0 < ceiling <= 1 or not 0.001 <= release <= 5:
                raise ValueError("limiter ceiling/release is outside its supported range")
            key = f"effect_{i}_gain"
            if fixed is not None and key in fixed:
                gains = fixed[key]
            else:
                peaks = np.max(np.abs(y), axis=1)
                wanted = np.minimum(1, ceiling / np.maximum(peaks, 1e-20))
                decay_factor = np.exp(-1 / (release * sr))
                reduction = float(np.max((1 - wanted) * decay_factor ** np.arange(len(y) - 1, -1, -1))) \
                    if loop and len(y) else 0.0
                gains = np.empty(len(y))
                for sample, want in enumerate(wanted):
                    reduction = max(1 - want, reduction * decay_factor)
                    gains[sample] = 1 - reduction
                if (rec := current()) is not None:
                    rec.factor(key, rec.put(gains))
            y *= gains[:, None]
    result = y[:, 0] if original_ndim == 1 else y
    return result.astype(np.float32)
