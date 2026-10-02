"""The voice spec: a plain-data description of one sound.

Archetypes *design* a Voice; the renderer turns it into audio. Because the spec is plain
JSON, it is also the hand-off format for engine-side runtimes (see docs/arquitetura.md).
"""
import json
from dataclasses import MISSING, asdict, dataclass, field, fields

FORMAT = "creaturesynth.voice"
VERSION = 3   # 2: added `speech`; 3: realism (air, room, lowpass, shimmer)

Curve = list[tuple[float, float]]  # (normalised time 0..1, value) breakpoints


@dataclass
class Syllable:
    """One continuous vocal gesture: source -> formants -> envelope."""

    start: float                      # seconds from the start of the voice
    dur: float                        # seconds
    pitch: Curve                      # Hz over time (interpolated in log space)
    source: str = "glottal"           # glottal | sine | pulse | noise
    pulse_width: float = 0.5          # for source="pulse"
    brightness: float = 0.5           # 0 dark .. 1 bright (source spectral tilt)
    vibrato: tuple[float, float] = (0.0, 0.0)   # rate Hz, depth semitones
    jitter: float = 0.0               # random pitch wander, semitones
    sub: float = 0.0                  # subharmonic (period-doubling) amount
    rough: tuple[float, float] = (0.0, 30.0)    # growl AM depth, rate Hz
    breath: float = 0.0               # noise mixed into the source (0..1)
    ring: tuple[float, float] = (0.0, 0.0)      # ring modulator Hz, mix (metallic/robotic)
    formants: list[tuple[float, float, float]] = field(default_factory=list)  # Hz, bandwidth Hz, gain
    mouth: Curve = field(default_factory=lambda: [(0.0, 1.0), (1.0, 1.0)])   # formant scale over time
    pulses: tuple[float, float, float] = (0.0, 0.0, 2.0)  # rate Hz, depth, sharpness (trills, croaks)
    attack: float = 0.01              # seconds
    release: float = 0.05             # seconds
    amp: Curve = field(default_factory=lambda: [(0.0, 1.0), (1.0, 1.0)])     # loudness over time
    gain: float = 1.0                 # peak level relative to the other syllables
    shimmer: float = 0.0              # random cycle-scale loudness wobble (natural voices are not steady)


@dataclass
class ChipProgram:
    """A Game Boy-style 2 pulse + noise program (the Gen 1 cry engine)."""

    pulse1: list[dict]                # {"duty": byte} | {"note": [len-1, vol, fade, freq 0..2047]}
    pulse2: list[dict]
    noise: list[dict]                 # {"note": [len-1, vol, fade, NR43 param]}
    pitch: int = 0                    # added to every frequency register (Gen 1 "pitch")
    length: int = 0                   # -128..127, scales note lengths by (length + 256) / 256
    start: float = 0.0
    gain: float = 1.0
    hardware_noise: bool = True       # False reproduces the old web app's 7-bit noise bug


@dataclass
class SpeechProgram:
    """Human speech as formant-synthesiser frame tracks (see speech/klatt.py).

    `frames` maps track name -> values at `frame_rate`: f0, av (voicing), ah (aspiration),
    af/ab (frication: resonant/flat), f1..f5 + b1..b5 (cascade formants), fnp/fnz (nasal
    pole/zero), fa/wa/ga + fb/wb/gb (two frication resonances: Hz, bandwidth, gain).
    """

    frames: dict[str, list[float]]
    frame_rate: float = 400.0
    start: float = 0.0
    gain: float = 1.0
    tilt: float = 3000.0              # glottal source spectral tilt (low-pass), Hz
    jitter: float = 0.1               # random pitch wander, semitones
    rough: tuple[float, float] = (0.0, 30.0)    # growl AM depth, rate Hz
    sub: float = 0.0                  # subharmonics (monster voices)
    text: str = ""
    lang: str = ""
    phonemes: str = ""                # informational transcription

    @property
    def duration(self) -> float:
        return len(self.frames["f0"]) / self.frame_rate


@dataclass
class Voice:
    syllables: list[Syllable] = field(default_factory=list)
    chips: list[ChipProgram] = field(default_factory=list)
    speech: list[SpeechProgram] = field(default_factory=list)
    drive: float = 0.0                # tanh saturation amount
    crush: float = 0.0                # 0..1 sample-rate/bit-depth reduction
    space: float = 0.0                # reverb tail length, seconds (engines may use their own reverb)
    wet: float = 0.2                  # reverb mix
    gain: float = 1.0                 # final peak level (calls: idle is quieter than attack)
    air: float = 0.0                  # recording noise floor, 0..1 (-70 .. -30 dB under the peak)
    room: float = 0.0                 # short early reflections, 0..1 mix (a real space, not a tail)
    lowpass: float = 0.0              # Hz, 0 = off: distance/microphone loss of highs
    seed: int = 0                     # drives every random stream of the renderer
    meta: dict = field(default_factory=dict)  # informational: archetype, call, traits...

    @property
    def duration(self) -> float:
        """Dry duration in seconds (without the reverb tail)."""
        from .chip import program_duration  # chip imports this module
        ends = [s.start + s.dur for s in self.syllables]
        ends += [c.start + program_duration(c) for c in self.chips]
        ends += [p.start + p.duration for p in self.speech]
        return max(ends, default=0.0)

    def to_dict(self) -> dict:
        def compact(obj):
            defaults = type(obj)(**_required(obj))
            return {k: v for k, v in asdict(obj).items()
                    if k in _required(obj) or v != getattr(defaults, k)}
        out = {"format": FORMAT, "version": VERSION}
        out.update(compact(self))
        out["syllables"] = [compact(s) for s in self.syllables]
        out["chips"] = [compact(c) for c in self.chips]
        out["speech"] = [compact(p) for p in self.speech]
        return json.loads(json.dumps(out))  # tuples -> lists: exactly what JSON round-trips to

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "Voice":
        if data.get("format", FORMAT) != FORMAT:
            raise ValueError(f"not a {FORMAT} document")
        if data.get("version", VERSION) > VERSION:
            raise ValueError(f"spec version {data['version']} is newer than supported ({VERSION})")
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        kwargs["syllables"] = [_syllable(s) for s in data.get("syllables", [])]
        kwargs["chips"] = [ChipProgram(**c) for c in data.get("chips", [])]
        kwargs["speech"] = [SpeechProgram(**{**sp, "rough": tuple(sp.get("rough", (0.0, 30.0)))})
                            for sp in data.get("speech", [])]
        return cls(**kwargs)

    @classmethod
    def from_json(cls, text: str) -> "Voice":
        return cls.from_dict(json.loads(text))


_TUPLES = {"vibrato", "rough", "ring", "pulses"}
_CURVES = {"pitch", "mouth", "amp", "formants"}


def _required(obj) -> dict:
    """Fields without defaults, so a default instance can be built for comparison."""
    return {f.name: getattr(obj, f.name) for f in fields(obj)
            if f.default is MISSING and f.default_factory is MISSING}


def _syllable(d: dict) -> Syllable:
    d = dict(d)
    for k in _TUPLES & d.keys():
        d[k] = tuple(d[k])
    for k in _CURVES & d.keys():
        d[k] = [tuple(p) for p in d[k]]
    return Syllable(**d)
