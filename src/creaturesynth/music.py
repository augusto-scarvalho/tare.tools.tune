"""Music cues composed from a seed: short jingles and seamless loops, orchestral or chiptune.

    >>> from creaturesynth import write_wav
    >>> from creaturesynth.music import Cue
    >>> write_wav("victory.wav", Cue("victory", seed=3).render(), 48000)
    >>> town = Cue("town", seed=7)                 # a loop: exactly `town.length` seconds, repeats without a seam
    >>> write_wav("battle_8bit.wav", Cue("battle", style="chip", seed=2).render(), 48000)

Each cue is a little music theory on a Score (score.py):
- a key and mode, a chord progression in that mood;
- a melody on the chords: chord tones on the strong beats, steps between them, the opening motif coming back,
  a cadence at the end of each phrase;
- an arrangement in roles (lead, pad, arpeggio, bass, drums...) that the style turns into instruments
  (instruments.py, measured on recordings) or into a sound chip's pulse, wave and noise channels.

The seed picks the key, the progression, the rhythms and the motif: the same seed is the same piece.
"""
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from . import rng
from .render import DEFAULT_SR
from .score import SCALES, Score

# role -> (instrument, gain, pan, send, track voice settings)
ORCHESTRAL = {
    "lead": ("flute", 0.55, 0.15, 0.3, {}), "brass": ("trumpet", 0.85, 0.1, 0.25, {}),
    "horns": ("horn", 0.4, -0.25, 0.3, {}), "strings": ("strings", 0.42, -0.1, 0.35, {}),
    "low_strings": ("cellos", 0.45, 0.2, 0.3, {}), "pad": ("strings", 0.38, 0.0, 0.4, {}),
    "choir": ("choir", 0.4, 0.0, 0.45, {}), "arp": ("harp", 0.45, -0.35, 0.35, {}),
    "pluck": ("lute", 0.5, -0.3, 0.2, {}), "bass": ("pizzicato", 0.7, 0.05, 0.15, {}),
    "bells": ("glockenspiel", 0.3, 0.35, 0.4, {}), "chime": ("tubular_bell", 0.35, 0.3, 0.45, {}),
    "celesta": ("celesta", 0.35, 0.35, 0.45, {}), "timpani": ("timpani", 0.55, -0.15, 0.3, {}),
    "kick": ("bass_drum", 0.55, 0.0, 0.2, {}), "snare": ("snare", 0.35, 0.1, 0.2, {}),
    "crash": ("crash", 0.3, 0.3, 0.3, {}), "tambourine": ("tambourine", 0.25, 0.4, 0.15, {}),
    "hand_drum": ("hand_drum", 0.45, -0.3, 0.15, {}), "shaker": ("shaker", 0.2, 0.35, 0.1, {}),
    "triangle": ("triangle", 0.25, 0.45, 0.3, {}), "gong": ("gong", 0.4, -0.2, 0.4, {}),
}
CHIP = {
    "lead": ("pulse", 0.5, 0.15, 0.1, {"crush": 0.25}), "brass": ("pulse", 0.5, 0.15, 0.1, {"crush": 0.25}),
    "horns": ("square", 0.35, -0.2, 0.1, {"crush": 0.25}), "strings": ("thin_pulse", 0.3, -0.2, 0.1, {"crush": 0.25}),
    "low_strings": ("square", 0.3, -0.1, 0.1, {"crush": 0.25}), "pad": ("thin_pulse", 0.25, 0.0, 0.1, {"crush": 0.25}),
    "choir": ("thin_pulse", 0.25, 0.0, 0.1, {"crush": 0.25}), "arp": ("square", 0.3, -0.3, 0.1, {"crush": 0.25}),
    "pluck": ("square", 0.3, -0.3, 0.1, {"crush": 0.25}), "bass": ("chip_bass", 0.5, 0.0, 0.0, {"crush": 0.25}),
    "bells": ("thin_pulse", 0.25, 0.35, 0.1, {"crush": 0.25}), "chime": ("square", 0.3, 0.3, 0.1, {"crush": 0.25}),
    "celesta": ("thin_pulse", 0.25, 0.3, 0.1, {"crush": 0.25}), "timpani": ("chip_kick", 0.45, 0.0, 0.0, {}),
    "kick": ("chip_kick", 0.5, 0.0, 0.0, {}), "snare": ("chip_snare", 0.3, 0.0, 0.0, {}),
    "crash": ("chip_snare", 0.3, 0.0, 0.0, {}), "tambourine": ("chip_hat", 0.2, 0.2, 0.0, {}),
    "hand_drum": ("chip_kick", 0.3, -0.2, 0.0, {}), "shaker": ("chip_hat", 0.15, 0.2, 0.0, {}),
    "triangle": ("chip_hat", 0.15, 0.3, 0.0, {}), "gong": ("chip_snare", 0.3, 0.0, 0.0, {}),
}
STYLES = {"orchestral": ORCHESTRAL, "chip": CHIP}

# Rhythms of one bar: (beat, length) in beats
CALM = [[(0, 2), (2, 2)], [(0, 1), (1, 1), (2, 2)], [(0, 3), (3, 1)], [(0, 1.5), (1.5, 0.5), (2, 2)],
        [(0, 1), (1, 1), (2, 1), (3, 1)], [(0, 2), (2, 1), (3, 1)]]
LIVELY = [[(0, 0.5), (0.5, 0.5), (1, 1), (2, 1), (3, 1)], [(0, 1), (1, 0.5), (1.5, 0.5), (2, 2)],
          [(0, 0.75), (0.75, 0.25), (1, 1), (2, 0.5), (2.5, 0.5), (3, 1)], [(0, 1.5), (1.5, 0.5), (2, 1), (3, 1)],
          [(0, 0.5), (0.5, 0.5), (1, 0.5), (1.5, 0.5), (2, 2)], [(0, 1), (1, 1), (2, 0.5), (2.5, 0.5), (3, 1)]]
WALTZ = [[(0, 1), (1, 1), (2, 1)], [(0, 2), (2, 1)], [(0, 1.5), (1.5, 0.5), (2, 1)], [(0, 0.5), (0.5, 0.5), (1, 1),
                                                                                         (2, 1)], [(0, 3)]]
DRIVING = [[(0, 1.5), (1.5, 1.5), (3, 1)], [(0, 0.5), (0.5, 0.5), (1, 0.5), (1.5, 0.5), (2, 2)],
           [(0, 1), (1, 0.5), (1.5, 0.5), (2, 1), (3, 0.5), (3.5, 0.5)], [(0, 0.75), (0.75, 0.75), (1.5, 0.5),
                                                                          (2, 2)]]

MAJOR_PROGRESSIONS = [[0, 3, 4, 0], [0, 5, 3, 4], [0, 4, 5, 3], [0, 3, 0, 4], [5, 3, 0, 4], [0, 1, 4, 0]]
MINOR_PROGRESSIONS = [[0, 5, 6, 0], [0, 3, 4, 0], [0, 5, 2, 6], [0, 3, 6, 2], [0, 6, 5, 4], [0, 5, 3, 4]]


@dataclass
class Key:
    tonic: int                        # MIDI note of the tonic
    mode: str = "major"

    @property
    def steps(self) -> tuple:
        return SCALES[self.mode]

    def note(self, degree: int, chord: int | None = None) -> int:
        """Scale degree (0 = tonic, 7 = an octave up, negative below) -> MIDI. Over a dominant chord in a minor key
        the seventh degree is raised (harmonic minor), as a cadence wants it."""
        octave, i = divmod(degree, 7)
        n = self.tonic + 12 * octave + self.steps[i]
        if self.mode in ("minor", "harmonic", "dorian") and i == 6 and chord is not None and chord % 7 == 4:
            n += 1
        return n

    def chord(self, degree: int) -> list[int]:
        """The triad's degrees on `degree`."""
        return [degree, degree + 2, degree + 4]


class Rand:
    def __init__(self, seed: int, name: str):
        self.k = rng.key(seed, "music", name)
        self.i = 0

    def u(self) -> float:
        self.i += 1
        return rng.uniform(rng.key(self.k, self.i))

    def pick(self, items):
        return items[int(self.u() * len(items)) % len(items)]


def melody(r: Rand, key: Key, chords: list[int], rhythms: list, beats: int = 4, low: int = 2, high: int = 11,
           start: int = 4, motif_every: int = 2) -> list:
    """(midi, beat, length) per note over `chords` (one per bar). Bars 0, 2, 4... reuse the opening rhythm (the
    motif comes back), strong beats take chord tones near the last note, weak ones step towards the next; every
    fourth bar ends a phrase on a long note, the last one on the tonic."""
    motif = r.pick(rhythms)
    out, d = [], start
    for bar, ch in enumerate(chords):
        pattern = motif if bar % motif_every == 0 and bar != len(chords) - 1 else r.pick(rhythms)
        if bar % 4 == 3 or bar == len(chords) - 1:       # a phrase ends: settle on a long note
            pattern = [(0, 1), (1, beats - 1)] if r.u() < 0.6 else [(0, beats)]
        tones = [t + 7 * o for t in key.chord(ch) for o in (-2, -1, 0, 1, 2) if low <= t + 7 * o <= high]
        for j, (beat, length) in enumerate(pattern):
            last = j == len(pattern) - 1
            if bar == len(chords) - 1 and last:          # the final note: the tonic nearest to where we are
                d = min((7 * o for o in range(-1, 3)), key=lambda t: abs(t - d))
            elif bar % 4 == 3 and last:                  # a half cadence or a rest on a chord tone
                d = min(tones, key=lambda t: abs(t - d) + (0 if t % 7 in (ch % 7, (ch + 4) % 7) else 2))
            elif beat % (2 if beats == 4 else beats) == 0:   # strong beat: a chord tone close by, not the same note
                near = [t for t in sorted(tones, key=lambda t: (abs(t - d), t)) if t != d][:2]
                d = near[0] if r.u() < 0.6 else near[1]
            else:                                        # weak beat: a step, rising early in the phrase, falling late
                up = 1 if (bar % 4 < 2) == (r.u() < 0.7) else -1
                d += up * r.pick([1, 1, 1, 2])
            if d < low or d > high:                      # bounce off the edges of the range instead of sticking
                d = 2 * low - d if d < low else 2 * high - d
            out.append((key.note(d, ch), bar * beats + beat, length))
    return out


def voicing(key: Key, ch: int, prev: list[int] | None, low: int, high: int) -> list[int]:
    """The chord's tones as MIDI notes in [low, high], moving as little as possible from the last chord."""
    pcs = [key.note(t, ch) % 12 for t in key.chord(ch)]
    cands = []
    for base in range(low, high - 6):
        notes = []
        for pc in pcs:
            n = base + (pc - base) % 12
            notes.append(n)
        notes = sorted(notes)
        if notes[-1] <= high:
            cands.append(notes)
    if not prev:
        return cands[len(cands) // 2]
    return min(cands, key=lambda c: sum(abs(a - b) for a, b in zip(c, prev, strict=False)))


@dataclass
class Cue:
    """A piece of game music: `kind` (see CUES), `style` ("orchestral", "chip"), `seed` (which piece)."""

    kind: str
    style: str = "orchestral"
    seed: int = 0
    sr: int = DEFAULT_SR
    score: Score = field(init=False)
    loop: float = field(init=False, default=0.0)
    end: float = field(init=False, default=0.0)      # jingles: where the music stops (the ring then fades)

    def __post_init__(self):
        if self.kind not in CUES:
            raise ValueError(f"unknown cue {self.kind!r}; choose from {', '.join(CUES)}")
        if self.style not in STYLES:
            raise ValueError(f"unknown style {self.style!r}; choose from {', '.join(STYLES)}")
        self.r = Rand(self.seed, self.kind)
        self.roles = STYLES[self.style]
        CUES[self.kind](self)

    def new_score(self, bpm: float, meter: int = 4, hall: float = 2.2) -> Score:
        self.score = Score(bpm=bpm, meter=meter, hall=hall if self.style != "chip" else 0.6, seed=self.seed,
                           sr=self.sr)
        return self.score

    def key(self, mode: str) -> Key:
        return Key(55 + int(self.r.u() * 12), mode)        # G3..F#4

    def part(self, role: str, notes, velocity: float = 0.8, octave: int = 0):
        inst, gain, pan, send, voice = self.roles[role]
        self.score.track(role, gain, pan, send, **voice).play(inst, notes, velocity, transpose=12 * octave)

    @property
    def length(self) -> float:
        """Loops: their exact length in seconds (0 for jingles, which simply end)."""
        return self.loop

    def render(self) -> np.ndarray:
        """Stereo, shape (n, 2). A jingle lets its last chord ring 3 s and fades over the final 1.5; a loop is
        exactly `length` seconds."""
        y = self.score.render(loop=self.loop or None)
        if self.end:
            n = min(len(y), int((self.end + 3.0) * self.sr))
            y = y[:n].copy()
            fade = min(int(1.5 * self.sr), n)
            y[n - fade:] *= np.linspace(1, 0, fade)[:, None] ** 2
        return y


# -- jingles ----------------------------------------------------------------------------------------------------------

FANFARES = [   # (degree, beat, beats): the classic brass call, a pickup then the long chord
    [(4, 0, 1 / 3), (4, 1 / 3, 1 / 3), (4, 2 / 3, 1 / 3), (7, 1, 1.5), (4, 2.5, 0.5), (7, 3, 1), (9, 4, 0.5),
     (8, 4.5, 0.5), (9, 5, 3)],
    [(0, 0, 0.5), (2, 0.5, 0.5), (4, 1, 0.5), (7, 1.5, 1.5), (5, 3, 0.5), (7, 3.5, 0.5), (9, 4, 4)],
    [(4, 0, 1 / 3), (4, 1 / 3, 1 / 3), (4, 2 / 3, 1 / 3), (4, 1, 1), (2, 2, 1), (4, 3, 1), (7, 4, 4)],
]


def victory(c: Cue):
    """Brass call over a held chord, timpani and a snare roll into the last chord, a cymbal, the glockenspiel and the
    harp climbing on top."""
    c.new_score(bpm=110 + 20 * c.r.u())
    key = c.key("major")
    call = c.r.pick(FANFARES)
    end = max(b + d for _, b, d in call)
    c.part("brass", [(key.note(d), b, ln) for d, b, ln in call], 0.9, octave=1 if key.tonic < 62 else 0)
    c.part("horns", [(key.note(d - 2 if d % 7 != 0 else d - 3), b, ln) for d, b, ln in call], 0.75)
    last = call[-1][1]
    c.part("strings", [([key.note(t) for t in key.chord(0)], 0, last), ([key.note(t) for t in key.chord(4)], last - 1,
                                                                       1),
                       ([key.note(t) for t in key.chord(0)] + [key.note(7)], last, end - last + 1)], 0.7)
    c.part("low_strings", [(key.note(-7), 0, last - 1), (key.note(-3), last - 1, 1), (key.note(-7), last, end - last)],
           0.8)
    c.part("timpani", [(key.note(-7), 0, 1), (key.note(-3), last - 1, 0.5)]
           + [(key.note(-7), last - 1 + k / 8, 1 / 8, 0.4 + 0.05 * k) for k in range(8)]
           + [(key.note(-7), last, 2, 1.0)])
    c.part("snare", [(60, last - 1 + k / 8, 1 / 8, 0.3 + 0.07 * k) for k in range(8)])
    c.part("crash", [(60, last, 2)], 0.9)
    c.part("bells", [(key.note(d) + 12, last + 0.25 * j, 0.5) for j, d in enumerate((0, 2, 4, 7))], 0.6)
    c.part("arp", [(key.note(d), last + 0.08 * j, 2) for j, d in enumerate(range(0, 15))], 0.5)
    c.end = c.score.beats(end)


def levelup(c: Cue):
    """Harp and glockenspiel run up two octaves of the chord, the strings swell, a triangle rings it in."""
    c.new_score(bpm=120 + 20 * c.r.u())
    key = c.key("major")
    run = [0, 2, 4, 7, 9, 11, 14] if c.r.u() < 0.5 else [0, 4, 7, 9, 11, 14]
    c.part("arp", [(key.note(d), 0.25 * j, 1.5) for j, d in enumerate(run)], 0.7)
    c.part("bells", [(key.note(d) + 12, 0.25 * j, 0.5) for j, d in enumerate(run)], 0.5)
    top = 0.25 * len(run)
    c.part("strings", [([key.note(t) for t in key.chord(0)] + [key.note(7)], 0, top + 1.5)], 0.6)
    c.part("triangle", [(84, top, 2)], 0.6)
    c.part("celesta", [(key.note(14) + 12, top, 2), (key.note(11) + 12, top + 0.5, 1.5)], 0.5)
    c.end = c.score.beats(top + 1.5)


def quest(c: Cue):
    """Horns sing a cadence (I - IV - V - I) over the strings, the harp rolls each chord, a bell on the arrival."""
    c.new_score(bpm=88 + 16 * c.r.u())
    key = c.key("major")
    prog = [0, 3, 4, 0]
    line = c.r.pick([[4, 5, 4, 7], [2, 3, 1, 0], [4, 3, 1, 2], [7, 5, 6, 7]])
    c.part("horns", [(key.note(d, ch), 2 * i, 2 if i < 3 else 4) for i, (d, ch) in enumerate(zip(line, prog,
                                                                                                strict=True))], 0.8)
    prev = None
    for i, ch in enumerate(prog):
        prev = voicing(key, ch, prev, 52, 72)
        c.part("strings", [(prev, 2 * i, 2 if i < 3 else 4)], 0.6)
        c.part("arp", [(n, 2 * i + 0.1 * j, 2) for j, n in enumerate(prev + [prev[0] + 12])], 0.5)
        c.part("low_strings", [(key.note(ch - 14, ch), 2 * i, 2 if i < 3 else 4)], 0.7)
    c.part("chime", [(key.note(7), 6, 4)], 0.6)
    c.end = c.score.beats(10)


def gameover(c: Cue):
    """Slow strings sinking in a minor key over a choir, soft low timpani, the last chord left to fade."""
    c.new_score(bpm=58 + 8 * c.r.u())
    key = c.key("minor")
    prog = [0, 5, 3, 4, 0]
    line = c.r.pick([[4, 2, 0, -1, 0], [7, 5, 3, 1, 0], [2, 0, -2, -3, -7]])
    c.part("strings", [(key.note(d + 7, ch), 2 * i, 2 if i < 4 else 4) for i, (d, ch) in
                       enumerate(zip(line, prog, strict=True))], 0.6)
    prev = None
    for i, ch in enumerate(prog):
        prev = voicing(key, ch, prev, 50, 67)
        c.part("choir", [(prev, 2 * i, 2 if i < 4 else 5)], 0.5)
        c.part("low_strings", [(key.note(ch - 14, ch), 2 * i, 2 if i < 4 else 5)], 0.6)
    c.part("timpani", [(key.note(-7), 0, 1, 0.4), (key.note(-7), 8, 2, 0.5)])
    c.part("arp", [(key.note(-7), 8, 4, 0.6)])
    c.end = c.score.beats(13)


# -- loops ------------------------------------------------------------------------------------------------------------

def _loop(c: Cue, bars: int):
    c.loop = c.score.bar(bars)


def town(c: Cue):
    """A walking-pace major tune: flute melody, harp arpeggios, string pads, a pizzicato bass, a shaker."""
    c.new_score(bpm=92 + 16 * c.r.u())
    key = c.key("major")
    prog = c.r.pick(MAJOR_PROGRESSIONS) * 2 + c.r.pick(MAJOR_PROGRESSIONS) * 2
    c.part("lead", melody(c.r, key, prog, CALM + LIVELY[:2]), 0.75, octave=1)
    _accompany(c, key, prog, arp=True, pad=True, shaker=True)
    _loop(c, len(prog))


def explore(c: Cue):
    """Open and wandering: strings, harp, a celesta melody, no drums."""
    c.new_score(bpm=76 + 14 * c.r.u())
    key = c.key(c.r.pick(["major", "lydian", "dorian"]))
    prog = c.r.pick(MAJOR_PROGRESSIONS) * 2 + c.r.pick(MAJOR_PROGRESSIONS) * 2
    c.part("celesta", melody(c.r, key, prog, CALM), 0.6, octave=1)
    c.part("lead", [(n, b, ln) for n, b, ln in melody(c.r, key, prog[8:], CALM)], 0.5)
    _accompany(c, key, prog, arp=True, pad=True)
    _loop(c, len(prog))


def tavern(c: Cue):
    """A lively folk tune in three: lute arpeggios, flute (or fiddle) melody, hand drum and tambourine."""
    c.new_score(bpm=150 + 30 * c.r.u(), meter=3)
    key = c.key(c.r.pick(["major", "mixolydian", "dorian"]))
    prog = c.r.pick(MAJOR_PROGRESSIONS) * 2 + c.r.pick(MAJOR_PROGRESSIONS) * 2
    c.part("lead", melody(c.r, key, prog, WALTZ, beats=3, start=4), 0.8, octave=1)
    prev = None
    for bar, ch in enumerate(prog):
        prev = voicing(key, ch, prev, 50, 66)
        c.part("pluck", [(prev[j % 3] + (12 if j == 3 else 0), 3 * bar + 0.5 * j, 0.6) for j in range(6)], 0.6)
        c.part("bass", [(key.note(ch - 14, ch), 3 * bar, 1)], 0.8)
        c.part("hand_drum", [(57, 3 * bar, 0.5, 0.9), (64, 3 * bar + 1.5, 0.5, 0.5), (64, 3 * bar + 2, 0.5, 0.6)])
        c.part("tambourine", [(70, 3 * bar + 1, 0.5, 0.6), (70, 3 * bar + 2, 0.5, 0.5)])
    _loop(c, len(prog))


def dungeon(c: Cue):
    """Slow and minor: a low drone, a choir moving through dark chords, a few high bell notes, a far gong."""
    c.new_score(bpm=60 + 10 * c.r.u())
    key = c.key("minor")
    prog = c.r.pick(MINOR_PROGRESSIONS) * 2
    bars = len(prog) * 2
    c.part("low_strings", [([key.note(-14), key.note(-10)], 0, bars * 4)], 0.5)
    prev = None
    for i, ch in enumerate(prog):
        prev = voicing(key, ch, prev, 50, 67)
        c.part("choir", [(prev, 8 * i, 8)], 0.45)
    pent = [key.note(d) + 12 for d in (0, 2, 3, 4, 6, 7)]
    c.part("bells", [(c.r.pick(pent), 4 * b + c.r.pick([0, 1, 2, 2.5]), 2, 0.4 + 0.3 * c.r.u())
                     for b in range(bars) if c.r.u() < 0.55], 0.5)
    c.part("timpani", [(key.note(-7), 4 * b, 2, 0.35) for b in range(0, bars, 4)])
    c.part("gong", [(48, 0, 8, 0.4)])
    _loop(c, bars)


def battle(c: Cue):
    """Fast and minor: string ostinato, brass melody and stabs, timpani and drums driving, a crash every phrase."""
    c.new_score(bpm=138 + 24 * c.r.u())
    key = c.key("minor")
    prog = c.r.pick(MINOR_PROGRESSIONS) * 2 + c.r.pick(MINOR_PROGRESSIONS) * 2
    c.part("brass", melody(c.r, key, prog, DRIVING, start=4), 0.85, octave=1 if key.tonic < 60 else 0)
    prev = None
    for bar, ch in enumerate(prog):
        root = key.note(ch - 7, ch)
        c.part("strings", [(root + (0, 12, 7, 12)[j % 4], 4 * bar + 0.5 * j, 0.45) for j in range(8)], 0.7)
        prev = voicing(key, ch, prev, 50, 64)
        c.part("horns", [(prev, 4 * bar, 0.5), (prev, 4 * bar + 1.5, 0.5)], 0.8)
        c.part("low_strings", [(root - 12, 4 * bar, 4)], 0.7)
        c.part("timpani", [(key.note(-7), 4 * bar, 0.5, 0.9), (key.note(-3), 4 * bar + 1.5, 0.5, 0.6),
                           (key.note(-7), 4 * bar + 2.5, 0.5, 0.7)])
        c.part("kick", [(36, 4 * bar, 0.5, 0.9), (36, 4 * bar + 2, 0.5, 0.8)])
        c.part("snare", [(60, 4 * bar + 1, 0.5, 0.7), (60, 4 * bar + 3, 0.5, 0.8)])
        if bar % 4 == 0:
            c.part("crash", [(60, 4 * bar, 2, 0.7)])
    _loop(c, len(prog))


def _accompany(c: Cue, key: Key, prog: list, arp=False, pad=False, shaker=False):
    prev = None
    for bar, ch in enumerate(prog):
        b = 4 * bar
        prev = voicing(key, ch, prev, 52, 69)
        if pad:
            c.part("pad", [(prev, b, 4)], 0.5)
        if arp:
            notes = prev + [prev[0] + 12, prev[1] + 12]
            order = [0, 1, 2, 3, 4, 3, 2, 1]
            c.part("arp", [(notes[order[j]], b + 0.5 * j, 1.0) for j in range(8)], 0.55)
        c.part("bass", [(key.note(ch - 14, ch), b, 1), (key.note(ch - 10, ch), b + 2, 1)], 0.7)
        if shaker:
            c.part("shaker", [(60, b + 0.5 * j, 0.25, 0.4 + 0.3 * (j % 2)) for j in range(8)])


CUES: dict[str, Callable[[Cue], None]] = {
    "victory": victory, "levelup": levelup, "quest": quest, "gameover": gameover,
    "town": town, "explore": explore, "tavern": tavern, "dungeon": dungeon, "battle": battle,
}
