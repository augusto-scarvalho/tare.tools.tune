"""A small source-filter vocoder for voice clips taken from real performances (see tools/build_barks.py).

A template is what a recording leaves once analysed: every 5 ms its pitch (0 = no voice), its spectral envelope
(mel-spaced bands, dB: 32 for the barks, 64 for the voice banks) and how much of it is breath rather than voice
(5 bands, 0..1). Synthesis rebuilds it the
way the WORLD vocoder does (M. Morise, 2016), here in plain numpy and deterministic. At every glottal pulse
(every 2 ms where there is no voice):

    voiced   a minimum-phase response shaped by envelope x (1 - aperiodicity), at the exact time between samples
    breath   the noise up to the next pulse (SplitMix64, see rng.py), through envelope x aperiodicity

and can move it to another voice on the way: `pitch` scales the pitch, `warp` the formants (a shorter vocal tract
moves them up), `stretch` the length, `breath` adds air (or takes it away), `tilt` brightens or darkens (dB per
octave), `swing` widens or flattens the pitch contour.

No model runs here: the templates are measured numbers, the synthesis is arithmetic on them and seeded noise.
"""
import math
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
AUDIO = DATA.with_name("barks_audio.npz")   # the recordings themselves, cut as analysed (16-bit, AUDIO_SR)
AUDIO_SR = 24_000
TAPE = 0.4                    # how far a bark may move to be played like tape: its formants off its pitch (both move
                              # together on tape); by ear tape still beat the vocoder in 10 of 12 pairs moving up to
                              # 40 % (round "fita-fronteira")
TAPE_LENGTH = 0.25            # and its length off what the style asks (a style fitting a length keeps the vocoder)
ENV_FLOOR = -107.5            # envelopes are stored in 0.5 dB steps from here (uint8)
BREATH = 3 ** 0.5             # uniform noise in -1..1 to unit variance, as WORLD's
UNVOICED = 500.0              # Hz: the pulse rate where there is no voice (breath only), as WORLD's
ROUGH_CENTS, ROUGH_DB = 45.0, 1.7   # at rough = 1: each period off by ~45 cents, each pulse by ~1.7 dB (std); by
                                    # ear (round "rouquidao") the natural voice breaks past ~50 cents
SUB_DIP, SUB_SHIFT = 0.8, 0.04      # at sub = 1: every other pulse 80 % weaker and 4 % sooner (period doubling)
SQRT12 = math.sqrt(12)              # a uniform deviate in -0.5..0.5 to unit variance


def band_freqs(n: int = BANDS) -> np.ndarray:
    mel = 1127 * np.log(1 + np.array([LO, HI]) / 700)
    return 700 * (np.exp(np.linspace(mel[0], mel[1], n) / 1127) - 1)


def ap_freqs(n: int = AP_BANDS) -> np.ndarray:
    return np.geomspace(500, 16_000, n)


def encode(f0: np.ndarray, sp: np.ndarray, ap: np.ndarray, fs: int, bands: int = BANDS):
    """WORLD's per-bin power envelope and aperiodicity -> the compact bands stored in a template."""
    fr = np.arange(sp.shape[1]) * fs / (2 * (sp.shape[1] - 1))
    bf, af = band_freqs(bands), ap_freqs()
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
               breath: float = 0.0, tilt: float = 0.0, swing: float = 1.0, seed: int = 0, rough: float = 0.0,
               sub: float = 0.0) -> np.ndarray:
    """The template's sound, moved to another voice, deterministic for a seed. `rough` (0..1): every glottal
    period and pulse a little off at random, a hoarse, growling voice; `sub` (0..1): every other pulse weaker and
    sooner, a voice doubled an octave below, as a creature's."""
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
    bf, logaf = band_freqs(env.shape[1]), np.log(ap_freqs())   # as many bands as the template has
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
        period, amp = 1 / f, 1.0
        if f0[k] > 0 and (rough or sub):
            if rough:
                period *= 2 ** (ROUGH_CENTS * rough * (rng.uniform(rng.key(key, "rough", i)) - 0.5) * SQRT12 / 1200)
                amp = 10 ** (ROUGH_DB * rough * (rng.uniform(rng.key(key, "shimmer", i)) - 0.5) * SQRT12 / 20)
            if sub:
                if i % 2:
                    amp *= 1 - SUB_DIP * sub
                    period *= 1 - SUB_SHIFT * sub
                else:
                    period *= 1 + SUB_SHIFT * sub
        n = max(int((when + period) * sr) - s, 1)
        if k not in cache:
            cache[k] = filters(k)
        voice, air = cache[k]
        noise = rng.noise(rng.key(key, i), n)      # breath: the noise up to the next pulse, through the envelope
        y = np.fft.irfft(np.fft.rfft(noise - noise.mean(), nfft) * air, nfft) * BREATH
        if voice is not None:                       # voice: a minimum-phase pulse, between samples, without DC
            h = np.fft.irfft(voice * np.exp(delay * (pos - s)), nfft)
            h[:nfft // 2] -= h.sum() * dc
            y += h * (np.sqrt(n) * amp)
        out[s:s + nfft] += y
        when += period
        i += 1
    end = np.flatnonzero(np.abs(out) > 1e-4 * (np.abs(out).max() + 1e-12))
    return out[: end[-1] + 1] if len(end) else out[: int(FRAME * sr)]


@lru_cache(maxsize=1)
def _recordings() -> dict[str, np.ndarray]:
    import json
    if not AUDIO.exists():
        return {}
    d = np.load(AUDIO)
    meta, audio = json.loads(bytes(d["meta"]).decode()), d["audio"]
    return {t.name: audio[m["start"]: m["start"] + m["samples"]] for t, m in zip(templates(), meta, strict=True)}


def recording(name: str) -> np.ndarray | None:
    """The clip's own recording (-1..1, AUDIO_SR), if it is kept."""
    x = _recordings().get(name)
    return None if x is None else x.astype(np.float64) / 32767


def tape(v) -> bool:
    """Whether a Vocoded bark plays from its recording, like tape a little faster or slower: pitch, formants and length
    moving together, nothing cut or rebuilt (by ear it sounds as the recording does; the vocoder and PSOLA did not).
    Only when it moves that way anyway: not whispered, not rough or doubled, its formants within TAPE and its length
    within TAPE_LENGTH of where tape takes them."""
    return (v.clip in _recordings() and abs(v.breath) <= 0.3 and not v.rough and not v.sub
            and abs(v.stretch * v.pitch - 1) <= TAPE_LENGTH and abs(v.warp / v.pitch - 1) <= TAPE)


def duration(v) -> float:
    t = template(v.clip)
    return t.duration / v.pitch if tape(v) else t.duration * v.stretch


def _tape(v, sr: int) -> np.ndarray:
    from fractions import Fraction

    from scipy.signal import resample_poly
    ratio = Fraction(sr / (AUDIO_SR * v.pitch)).limit_denominator(1000)     # faster = higher, shorter
    y = resample_poly(recording(v.clip), ratio.numerator, ratio.denominator)
    if v.tilt:
        spec = np.fft.rfft(y)
        spec *= 10 ** (v.tilt * np.log2(np.maximum(np.fft.rfftfreq(len(y), 1 / sr), 50) / 1000) / 20)
        y = np.fft.irfft(spec, len(y))
    return y


def render_vocoded(v, sr: int, seed: int) -> np.ndarray:
    """A spec.Vocoded layer, peak-normalised to its gain: from its recording like tape when it moves little, rebuilt by
    the vocoder otherwise."""
    if tape(v):
        y = _tape(v, sr)
    else:
        y = synthesize(template(v.clip), sr, pitch=v.pitch, warp=v.warp, stretch=v.stretch, breath=v.breath,
                       tilt=v.tilt, swing=v.swing, seed=seed, rough=v.rough, sub=v.sub)
    return v.gain * y / (np.max(np.abs(y)) + 1e-12)
