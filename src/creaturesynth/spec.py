"""The voice spec: a plain-data description of one sound.

Archetypes *design* a Voice; the renderer turns it into audio. Because the spec is plain
JSON, it is also the hand-off format for engine-side runtimes (see docs/arquitetura.md).
"""
import json
from dataclasses import MISSING, asdict, dataclass, field, fields

FORMAT = "creaturesynth.voice"
VERSION = 5   # 2: speech; 3: realism (air, room, lowpass, shimmer); 4: sound effects (modal, noise, scatter, loop);
              # 5: vocoded clips

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
class Modal:
    """A struck or scraped resonant body (steel, wood, stone, glass): an excitation rings a bank of modes."""

    start: float                      # seconds from the start of the voice
    dur: float                        # seconds
    modes: list[tuple[float, float, float]]                    # Hz, T60 decay seconds, gain
    hits: list[tuple[float, float, float]] = field(default_factory=lambda: [(0.0, 1.0, 0.001)])  # s, gain, contact s
    # (a contact under 3 samples is an ideal impulse: each mode starts at exactly its gain)
    scrape: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # start s, dur s, gain, judder Hz
    hardness: float = 8000.0          # excitation low-pass, Hz: soft (mallet, flesh) .. hard (steel on steel)
    click: float = 0.0                # the contact noise itself, mixed in
    gain: float = 1.0
    damp: float = 0.0                 # s after start when a hand or a damper stops it (-60 dB in 0.1 s); 0 = free


@dataclass
class Noise:
    """A band of filtered noise whose filter moves: whooshes, wind, roar, rumble, hiss."""

    start: float
    dur: float
    freq: Curve                       # filter frequency over time, Hz (interpolated in log space)
    filter: str = "band"              # band | low | high
    q: float = 1.0                    # band: centre / bandwidth; low, high: resonance (0.707 = flat)
    color: str = "white"              # white | brown (deep rumble)
    amp: Curve = field(default_factory=lambda: [(0.0, 1.0), (1.0, 1.0)])
    attack: float = 0.01
    release: float = 0.05
    wobble: tuple[float, float] = (0.0, 0.0)    # rate Hz, depth: turbulence, gusts, flicker
    gain: float = 1.0


@dataclass
class Scatter:
    """Many tiny random events: rain drops, crackle, sparks, debris, bubbles."""

    start: float
    dur: float
    rate: Curve                       # events per second over time
    event: str = "pop"                # pop (noise tick) | drop (rising blip: water) | ping (glassy ring)
    freq: tuple[float, float] = (1000.0, 4000.0)    # Hz range, log-uniform
    decay: tuple[float, float] = (0.002, 0.01)      # seconds range
    level: tuple[float, float] = (0.2, 1.0)         # amplitude range
    gain: float = 1.0


@dataclass
class Vocoded:
    """A short performance rebuilt by the vocoder (speech/vocoder.py) from an analysed clip, moved to another voice."""

    clip: str                         # template name, "<kind>/<performer>/<take>", e.g. "attack/adventurer/attack3"
    start: float = 0.0
    pitch: float = 1.0                # pitch ratio
    warp: float = 1.0                 # formant ratio: a shorter vocal tract moves them up
    stretch: float = 1.0              # length ratio
    breath: float = 0.0               # -1..1: less (towards fully voiced) or more air (1 = whispered)
    tilt: float = 0.0                 # brighter (+) or darker (-), dB per octave around 1 kHz
    swing: float = 1.0                # pitch contour: wider (> 1), flatter (< 1), 0 = monotone
    gain: float = 1.0

    @property
    def duration(self) -> float:
        from .speech.vocoder import template  # the vocoder builds on the renderer
        return template(self.clip).duration * self.stretch


@dataclass
class Voice:
    syllables: list[Syllable] = field(default_factory=list)
    chips: list[ChipProgram] = field(default_factory=list)
    speech: list[SpeechProgram] = field(default_factory=list)
    modal: list[Modal] = field(default_factory=list)
    noise: list[Noise] = field(default_factory=list)
    scatter: list[Scatter] = field(default_factory=list)
    vocoded: list[Vocoded] = field(default_factory=list)
    drive: float = 0.0                # tanh saturation amount
    crush: float = 0.0                # 0..1 sample-rate/bit-depth reduction
    space: float = 0.0                # reverb tail length, seconds (engines may use their own reverb)
    wet: float = 0.2                  # reverb mix
    gain: float = 1.0                 # final peak level (calls: idle is quieter than attack)
    air: float = 0.0                  # recording noise floor, 0..1 (-70 .. -30 dB under the peak)
    room: float = 0.0                 # short early reflections, 0..1 mix (a real space, not a tail)
    lowpass: float = 0.0              # Hz, 0 = off: distance/microphone loss of highs
    loop: float = 0.0                 # seconds of crossfade: > 0 renders a seamless loop (ambience beds)
    seed: int = 0                     # drives every random stream of the renderer
    meta: dict = field(default_factory=dict)  # informational: archetype, call, traits...

    @property
    def duration(self) -> float:
        """Dry duration in seconds (without the reverb tail)."""
        from .chip import program_duration  # chip imports this module
        ends = [s.start + s.dur for s in self.syllables]
        ends += [c.start + program_duration(c) for c in self.chips]
        ends += [p.start + p.duration for p in (*self.speech, *self.vocoded)]
        ends += [e.start + e.dur for e in (*self.modal, *self.noise, *self.scatter)]
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
        for name in ("modal", "noise", "scatter", "vocoded"):
            out[name] = [compact(e) for e in getattr(self, name)]
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
        for name, kind in (("modal", Modal), ("noise", Noise), ("scatter", Scatter)):
            kwargs[name] = [_element(kind, e) for e in data.get(name, [])]
        kwargs["vocoded"] = [Vocoded(**v) for v in data.get("vocoded", [])]
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


_ELEMENT_TUPLES = {"Modal": {"scrape"}, "Noise": {"wobble"}, "Scatter": {"freq", "decay", "level"}}


def _element(kind, d: dict):
    """JSON lists back to the tuples and lists of points the dataclasses use."""
    d = dict(d)
    for k, v in d.items():
        if k in _ELEMENT_TUPLES[kind.__name__]:
            d[k] = tuple(v)
        elif isinstance(v, list):
            d[k] = [tuple(p) for p in v]
    return kind(**d)


def _syllable(d: dict) -> Syllable:
    d = dict(d)
    for k in _TUPLES & d.keys():
        d[k] = tuple(d[k])
    for k in _CURVES & d.keys():
        d[k] = [tuple(p) for p in d[k]]
    return Syllable(**d)
