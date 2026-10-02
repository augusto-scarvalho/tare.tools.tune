"""A small source-filter vocoder for voice clips taken from real performances (see tools/build_barks.py).

A template is what a recording leaves once analysed: every 5 ms its pitch (0 = no voice), its spectral envelope
(32 mel-spaced bands, dB) and how much of it is breath rather than voice (5 bands, 0..1). Synthesis rebuilds it the
way the WORLD vocoder does (M. Morise, 2016), here in plain numpy and deterministic. At every glottal pulse
(every 2 ms where there is no voice):

    voiced   a minimum-phase response shaped by envelope x (1 - aperiodicity), at the exact time between samples
    breath   the noise up to the next pulse (SplitMix64, see rng.py), through envelope x aperiodicity

and can move it to another voice on the way: `pitch` scales the pitch, `warp` the formants (a shorter vocal tract
moves them up), `stretch` the length, `breath` adds air (or takes it away), `tilt` brightens or darkens (dB per
octave), `swing` widens or flattens the pitch contour.

No model runs here: the templates are measured numbers, the synthesis is arithmetic on them and seeded noise.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from .. import rng

FRAME = 0.005
BANDS = 32
AP_BANDS = 5
LO, HI = 40.0, 20_000.0
DATA = Path(__file__).parent / "data" / "barks.npz"
ENV_FLOOR = -107.5            # envelopes are stored in 0.5 dB steps from here (uint8)
BREATH = 3 ** 0.5             # uniform noise in -1..1 to unit variance, as WORLD's
UNVOICED = 500.0              # Hz: the pulse rate where there is no voice (breath only), as WORLD's


def band_freqs(n: int = BANDS) -> np.ndarray:
    mel = 1127 * np.log(1 + np.array([LO, HI]) / 700)
    return 700 * (np.exp(np.linspace(mel[0], mel[1], n) / 1127) - 1)


def ap_freqs(n: int = AP_BANDS) -> np.ndarray:
    return np.geomspace(500, 16_000, n)


def encode(f0: np.ndarray, sp: np.ndarray, ap: np.ndarray, fs: int):
    """WORLD's per-bin power envelope and aperiodicity -> the compact bands stored in a template."""
    fr = np.arange(sp.shape[1]) * fs / (2 * (sp.shape[1] - 1))
    bf, af = band_freqs(), ap_freqs()
    env = np.array([np.interp(bf, fr, 10 * np.log10(np.maximum(s, 1e-20))) for s in sp])
    apb = np.array([np.interp(af, fr, a) for a in ap])
    return f0.astype(np.float32), env.astype(np.float32), np.clip(apb, 0, 1).astype(np.float32)


@dataclass(frozen=True)
class Template:
    name: str                 # "<kind>/<performer>/<take>"
    kind: str
    voice: str
    tract: float
    pitch: float              # median pitch of its voiced frames, Hz
    f0: np.ndarray
    env: np.ndarray
    ap: np.ndarray

    @property
    def duration(self) -> float:
        return len(self.f0) * FRAME


@lru_cache(maxsize=1)
def templates() -> tuple[Template, ...]:
    import json
    d = np.load(DATA)
    meta = json.loads(bytes(d["meta"]).decode())
    f0, ap = d["f0"].astype(np.float64), d["ap"].astype(np.float64) / 255
    env = d["env"].astype(np.float64) / 2 + ENV_FLOOR
    out = []
    for m in meta:
        s, n = m["start"], m["frames"]
        name = f"{m['kind']}/{m['voice']}/{Path(m['ref']).stem}"
        out.append(Template(name, m["kind"], m["voice"], m["tract"], m["pitch"], f0[s:s + n], env[s:s + n],
                            ap[s:s + n]))
    return tuple(out)


@lru_cache(maxsize=1)
def _by_name() -> dict[str, Template]:
    return {t.name: t for t in templates()}


def template(name: str) -> Template:
    try:
        return _by_name()[name]
    except KeyError:
        raise ValueError(f"unknown vocoder clip {name!r}") from None


def _min_phase(mag: np.ndarray, nfft: int) -> np.ndarray:
    """A minimum-phase spectrum of the given magnitude (folded real cepstrum)."""
    c = np.fft.irfft(np.log(np.maximum(mag, 1e-12)), nfft)
    c[1:nfft // 2] *= 2
    c[nfft // 2 + 1:] = 0
    return np.exp(np.fft.rfft(c, nfft))


def synthesize(t: Template, sr: int, pitch: float = 1.0, warp: float = 1.0, stretch: float = 1.0,
               breath: float = 0.0, tilt: float = 0.0, swing: float = 1.0, seed: int = 0) -> np.ndarray:
    """The template's sound, moved to another voice, deterministic for a seed."""
    n_frames = max(int(round(len(t.f0) * stretch)), 2)
    src = np.minimum(np.arange(n_frames) / stretch, len(t.f0) - 1)
    lo = np.floor(src).astype(int)
    hi = np.minimum(lo + 1, len(t.f0) - 1)
    w = (src - lo)[:, None]
    env = t.env[lo] * (1 - w) + t.env[hi] * w
    ap = t.ap[lo] * (1 - w) + t.ap[hi] * w
    f0 = np.where((t.f0[lo] > 0) & (t.f0[hi] > 0), t.f0[lo] * (1 - w[:, 0]) + t.f0[hi] * w[:, 0], t.f0[lo])
    performed = f0
    if swing != 1.0 and t.pitch > 0:
        f0 = np.where(f0 > 0, t.pitch * (np.maximum(f0, 1) / t.pitch) ** swing, 0.0)
    f0 = f0 * pitch
    ap = ap + breath * (1 - ap) if breath >= 0 else ap * (1 + breath)

    nfft = 2048 if sr > 32_000 else 1024
    freqs = np.fft.rfftfreq(nfft, 1 / sr)
    src_f = np.maximum(freqs / warp, 1.0)
    bf, logaf = band_freqs(), np.log(ap_freqs())
    slope = tilt * np.log2(np.maximum(freqs, 50) / 1000)

    def filters(k: int):
        # under the performed pitch an envelope measures nothing (no harmonic there; WORLD assumes 500 Hz where
        # there is no voice): hold its level there, gently falling, so a lower voice gets a sound first harmonic
        db = np.interp(src_f, bf, env[k])
        f_low = performed[k] if performed[k] > 0 else UNVOICED
        under = src_f < f_low
        db[under] = np.interp(f_low, bf, env[k])
        power = 10 ** ((db + slope - 3 * np.log2(np.maximum(f_low / src_f, 1.0))) / 10)
        if f0[k] <= 0:
            return None, _min_phase(np.sqrt(power), nfft)
        a = np.clip(np.interp(np.log(src_f), logaf, ap[k]), 0.0, 1.0)
        return _min_phase(np.sqrt(power * (1 - a)), nfft), _min_phase(np.sqrt(power * a), nfft)

    out = np.zeros(int(n_frames * FRAME * sr) + 2 * nfft)
    cache: dict[int, tuple] = {}
    delay = -2j * np.pi * freqs / sr
    dc = np.hanning(nfft // 2)
    dc /= dc.sum()
    key = rng.key(seed, "breath")
    when, i = 0.0, 0
    while True:                     # one pulse per glottal period (every 2 ms where there is no voice)
        k = int(when / FRAME + 1e-9)               # (k + 1) * FRAME / FRAME can fall just short of k + 1
        if k >= n_frames:
            break
        f = f0[k] if f0[k] > 0 else UNVOICED
        pos = when * sr
        s = int(pos)
        n = max(int((when + 1 / f) * sr) - s, 1)
        if k not in cache:
            cache[k] = filters(k)
        voice, air = cache[k]
        noise = rng.noise(rng.key(key, i), n)      # breath: the noise up to the next pulse, through the envelope
        y = np.fft.irfft(np.fft.rfft(noise - noise.mean(), nfft) * air, nfft) * BREATH
        if voice is not None:                       # voice: a minimum-phase pulse, between samples, without DC
            h = np.fft.irfft(voice * np.exp(delay * (pos - s)), nfft)
            h[:nfft // 2] -= h.sum() * dc
            y += h * np.sqrt(n)
        out[s:s + nfft] += y
        when += 1 / f
        i += 1
    end = np.flatnonzero(np.abs(out) > 1e-4 * (np.abs(out).max() + 1e-12))
    return out[: end[-1] + 1] if len(end) else out[: int(FRAME * sr)]


def render_vocoded(v, sr: int, seed: int) -> np.ndarray:
    """A spec.Vocoded layer, peak-normalised to its gain."""
    y = synthesize(template(v.clip), sr, pitch=v.pitch, warp=v.warp, stretch=v.stretch, breath=v.breath,
                   tilt=v.tilt, swing=v.swing, seed=seed)
    return v.gain * y / (np.max(np.abs(y)) + 1e-12)
