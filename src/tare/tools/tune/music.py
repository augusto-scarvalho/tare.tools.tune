"""Music cues composed from a seed: short jingles and seamless loops, orchestral, 16-bit or chiptune.

    >>> from tare.tools.tune import write_wav
    >>> from tare.tools.tune.music import Cue
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

The "colour" cues (reverie, pastoral, timeless, grove, heroic, showdown) follow the harmony of 16-bit RPG scores
such as Yasunori Mitsuda's: chords picked for their colour rather than their function (major and minor 7ths and
9ths sliding in parallel, half-step and mediant moves, the tonic held as a pedal under them, Dorian, Lydian and
Mixolydian instead of plain major and minor, no V -> I), open voicings (the root low, 3rd and 7th in the middle,
the extensions on top), melodies leaning on the 9ths and 13ths, short motifs repeated as sequences. The "snes"
style plays them like the console did: sampled instruments, a darker top, an echo bouncing between the ears.
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
EXTRA = {   # roles the colour cues add (orchestral and chip get sensible stand-ins)
    "orchestral": {"keys": ("e_piano", 0.4, -0.2, 0.25, {}), "mallet": ("marimba", 0.45, 0.25, 0.25, {}),
                   "music_box": ("music_box", 0.35, 0.3, 0.4, {}), "hat": ("hihat", 0.18, 0.3, 0.05, {}),
                   "open_hat": ("open_hat", 0.15, 0.3, 0.1, {}), "e_bass": ("bass", 0.6, 0.0, 0.05, {}),
                   "guitar": ("guitar", 0.45, -0.3, 0.25, {}), "block": ("log_drum", 0.4, 0.3, 0.15, {})},
    "chip": {"keys": ("square", 0.25, -0.2, 0.1, {"crush": 0.25}), "mallet": ("thin_pulse", 0.3, 0.2, 0.1,
                                                                             {"crush": 0.25}),
             "music_box": ("thin_pulse", 0.25, 0.3, 0.1, {"crush": 0.25}), "hat": ("chip_hat", 0.15, 0.2, 0.0, {}),
             "open_hat": ("chip_hat", 0.15, 0.2, 0.0, {}), "e_bass": ("chip_bass", 0.5, 0.0, 0.0, {"crush": 0.25}),
             "guitar": ("square", 0.3, -0.3, 0.1, {"crush": 0.25}), "block": ("chip_hat", 0.2, 0.3, 0.0, {})},
}
ORCHESTRAL.update(EXTRA["orchestral"])
CHIP.update(EXTRA["chip"])
# 16-bit: the same sampled instruments, an echo send (6th field) on the melodic ones
SNES = {role: (*v, 0.0) for role, v in ORCHESTRAL.items()}
SNES.update({
    "lead": ("flute", 0.55, 0.15, 0.15, {}, 0.3), "brass": ("trumpet", 0.8, 0.1, 0.15, {}, 0.2),
    "arp": ("harp", 0.45, -0.35, 0.2, {}, 0.3), "music_box": ("music_box", 0.35, 0.3, 0.2, {}, 0.35),
    "bells": ("glockenspiel", 0.3, 0.35, 0.2, {}, 0.35), "celesta": ("celesta", 0.35, 0.35, 0.2, {}, 0.35),
    "keys": ("e_piano", 0.4, -0.2, 0.15, {}, 0.2), "mallet": ("marimba", 0.45, 0.25, 0.15, {}, 0.25),
    "guitar": ("guitar", 0.45, -0.3, 0.15, {}, 0.2), "pad": ("strings", 0.36, 0.0, 0.25, {}, 0.1),
    "choir": ("choir", 0.38, 0.0, 0.3, {}, 0.1), "e_bass": ("bass", 0.42, 0.0, 0.05, {}, 0.0),
})
STYLES = {"orchestral": ORCHESTRAL, "chip": CHIP, "snes": SNES}

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
        if self.style == "snes":    # a small room, the echo unit (~210 ms, darker each repeat), a dull top
            self.score = Score(bpm=bpm, meter=meter, hall=min(hall, 1.4), seed=self.seed, sr=self.sr,
                               echo=(0.21, 0.45, 2500.0), lowpass=9000.0)
        else:
            self.score = Score(bpm=bpm, meter=meter, hall=hall if self.style != "chip" else 0.6, seed=self.seed,
                               sr=self.sr)
        return self.score

    def key(self, mode: str) -> Key:
        return Key(55 + int(self.r.u() * 12), mode)        # G3..F#4

    def part(self, role: str, notes, velocity: float = 0.8, octave: int = 0):
        inst, gain, pan, send, voice, *echo = self.roles[role]
        self.score.track(role, gain, pan, send, echo[0] if echo else 0.0, **voice).play(inst, notes, velocity,
                                                                                         transpose=12 * octave)

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


# -- colour harmony ---------------------------------------------------------------------------------------------------

COLOR = {"maj7": (0, 4, 7, 11), "maj9": (0, 4, 7, 11, 14), "maj7#11": (0, 4, 7, 11, 18), "6/9": (0, 4, 7, 9, 14),
         "m7": (0, 3, 7, 10), "m9": (0, 3, 7, 10, 14), "m11": (0, 3, 7, 10, 14, 17), "7": (0, 4, 7, 10),
         "9": (0, 4, 7, 10, 14), "7sus4": (0, 5, 7, 10, 14), "sus2": (0, 2, 7, 14), "add9": (0, 4, 7, 14),
         "madd9": (0, 3, 7, 14), "": (0, 4, 7), "m": (0, 3, 7)}

# One chord per bar: (semitones above the tonic, quality). None of these leans on a V -> I.
PALETTES = {
    "lydian": [[(0, "maj9"), (2, "maj9"), (0, "maj9"), (2, "maj9")],          # I - II: the raised 4th shimmering
               [(0, "maj9"), (2, "maj9"), (4, "m9"), (2, "maj9")]],
    "mediant": [[(0, "maj9"), (8, "maj9"), (3, "maj9"), (5, "m9")],           # chromatic mediants
                [(0, "maj7"), (4, "m7"), (8, "maj7"), (7, "7sus4")]],
    "half_step": [[(1, "maj9"), (0, "m9"), (1, "maj9"), (0, "m9")],          # a maj9 sliding a half step onto i m9
                  [(0, "m9"), (1, "maj7"), (10, "m9"), (8, "maj9")]],
    "aeolian": [[(0, "m9"), (10, "maj7"), (8, "maj7"), (7, "m7")],            # i - bVII - bVI - v, no dominant
                [(0, "m9"), (8, "maj9"), (5, "m9"), (10, "7sus4")]],
    "dorian": [[(0, "m9"), (5, "9"), (0, "m9"), (5, "9")],                     # i - IV: the Dorian vamp
               [(0, "m11"), (10, "add9"), (5, "9"), (0, "m11")]],
    "mixolydian": [[(0, "add9"), (10, ""), (5, "add9"), (0, "add9")],         # I - bVII - IV - I
                   [(0, ""), (10, "add9"), (8, ""), (10, "")]],
    "heroic": [[(0, ""), (8, ""), (10, ""), (0, "")],                          # I - bVI - bVII - I
               [(0, ""), (4, ""), (5, ""), (0, "")], [(0, "add9"), (10, ""), (5, "add9"), (7, "7sus4")]],
    "chromatic": [[(0, "m7"), (1, "maj7"), (0, "m7"), (10, "7")],             # i - bII - i - bVII
                  [(0, "m7"), (8, "maj7"), (1, "maj7"), (7, "7sus4")]],
}
SIX8 = [[(0, 3), (3, 3)], [(0, 2), (2, 1), (3, 2), (5, 1)], [(0, 1), (1, 1), (2, 1), (3, 3)],
        [(0, 3), (3, 1), (4, 1), (5, 1)], [(0, 1.5), (1.5, 0.5), (2, 1), (3, 3)]]


def tones(tonic: int, chord) -> list[int]:
    step, quality = chord
    return [tonic + step + i for i in COLOR[quality]]


def open_voicing(tonic: int, chord, prev: list[int] | None = None, center: float = 64.0) -> list[int]:
    """Upper voices of a chord, open: the 3rd and 7th around middle C, the 5th and extensions above; the whole
    shape moved by octaves to stay near the last one."""
    step, quality = chord
    root = tonic + step
    upper = []
    for i in COLOR[quality][1:]:
        target = 60 if i % 12 in (3, 4, 10, 11) else 67
        pc = (root + i) % 12
        upper.append(min((n for n in range(48, 84) if n % 12 == pc), key=lambda n: abs(n - target)))
    upper = sorted(set(upper))
    ref = np.mean(prev) if prev else center
    shift = min((-12, 0, 12), key=lambda o: abs(np.mean(upper) + o - ref))
    return [n + shift for n in upper]


def planed(shape: list[int], frm: int, to: int) -> list[int]:
    """The same voicing moved in parallel to another root (planing), kept near the middle."""
    moved = [n + (to - frm) for n in shape]
    shift = min((-12, 0, 12), key=lambda o: abs(np.mean(moved) + o - 64))
    return [n + shift for n in moved]


def bass_note(tonic: int, chord, low: int = 36) -> int:
    return low + (tonic + chord[0] - low) % 12


def _snap(n: int, ok: set) -> int:
    """The nearest note (within a whole step) whose pitch class is allowed."""
    return min((m for m in range(n - 2, n + 3) if m % 12 in ok), key=lambda m: abs(m - n), default=n)


def color_melody(r: Rand, tonic: int, mode: str, chords: list, rhythms: list, beats: int = 4, low: int = 62,
                 high: int = 84, color: float = 0.35, leap: float = 0.1) -> list:
    """(midi, beat, length). Each 8-bar phrase arches (rises to a peak around its middle, settles at the end); strong
    beats take chord tones or colour tones (9ths, 11ths, 13ths) near that line, weak beats step along the scale
    towards the next one (never a half step above a chord tone); bars 2-3 replay bars 0-1 as a sequence, moved with
    the harmony (or a step up when the chord stays), bar 6 brings the motif back, bar 7 rests on a colour tone."""
    scale = {(tonic + i) % 12 for i in SCALES[mode]}
    mid = (low + high) / 2
    arch = [r.u() * 2 - 1 + a for a in (-3, -1, 1, 3, 5, 3, 0, -3)]
    out, cur, motif = [], None, []
    for bar, ch in enumerate(chords):
        ct = {n % 12 for n in tones(tonic, ch)}
        colors = {(tonic + ch[0] + i) % 12 for i in COLOR[ch[1]] if i >= 9}
        colors |= {pc for pc in ((tonic + ch[0] + 14) % 12, (tonic + ch[0] + 21) % 12) if pc in scale}
        ok = ct | colors | {pc for pc in scale if all((pc - t) % 12 != 1 for t in ct)}
        phrase = bar % 8
        target = mid + arch[phrase]
        if cur is None:
            cur = min((n for n in range(low, high) if n % 12 in ct), key=lambda n: abs(n - target))
        if phrase in (2, 3, 6) and motif:                 # sequence: the motif again, moved with the harmony
            src = phrase - 2 if phrase < 6 else phrase - 6
            shift = (ch[0] - chords[bar - (phrase - src)][0] + 6) % 12 - 6
            if phrase < 6 and shift == 0:
                shift = 2                                  # the same chord: climb a step instead of repeating
            for b, ln, n in motif:
                if int(b // beats) == src:
                    cur = _snap(n + shift, ok)
                    out.append((cur, bar * beats + b % beats, ln))
            continue
        pattern = r.pick(rhythms)
        closing = phrase == 7 or bar == len(chords) - 1
        if closing:
            pattern = [(0, 1), (1, beats - 1)] if r.u() < 0.6 else [(0, beats)]
        for j, (b, ln) in enumerate(pattern):
            last = j == len(pattern) - 1
            strong = b % (3 if beats in (3, 6) else 2) == 0
            if closing and last:
                pool = [n for n in range(low, high + 1) if n % 12 in (colors | ct) - {(tonic + ch[0]) % 12}]
                cur = min(pool, key=lambda n: abs(n - target) + 0.5 * abs(n - cur)) if pool else cur
            elif strong:
                want = colors if (colors and r.u() < color) else ct
                pool = [n for n in range(low, high + 1) if n % 12 in want and n != cur]
                pool.sort(key=lambda n: abs(n - target) + 0.6 * abs(n - cur))
                cur = pool[0 if r.u() < 0.65 else min(1, len(pool) - 1)] if pool else cur
            else:
                up = 1 if target > cur + 1 else -1 if target < cur - 1 else r.pick([-1, 1])
                if r.u() < leap:
                    cur = _snap(cur + up * 5, ok)
                else:
                    nxt = [n for n in range(cur + up, cur + 5 * up, up) if n % 12 in ok]
                    cur = nxt[0] if nxt else cur
            if cur < low or cur > high:
                cur += 12 if cur < low else -12
            out.append((cur, bar * beats + b, ln))
            if phrase in (0, 1):
                motif.append((b + phrase * beats, ln, cur))
    return out


def _colour(c: Cue, mode: str, palettes: list[str], bars: int = 16) -> tuple[int, list]:
    """A key and `bars` chords: two palettes (or one twice) from the list, each 4-bar pattern played twice."""
    tonic = 55 + int(c.r.u() * 12)
    chords = []
    while len(chords) < bars:
        pattern = c.r.pick(PALETTES[c.r.pick(palettes)])
        chords += pattern * 2
    return tonic, chords[:bars]


def _pad(c: Cue, role: str, tonic: int, chords: list, beats: int, vel: float, parallel: bool = False,
         hold: float | None = None) -> list:
    shapes, prev = [], None
    for bar, ch in enumerate(chords):
        v = planed(shapes[0], tonic + chords[0][0], tonic + ch[0]) if parallel and shapes else \
            open_voicing(tonic, ch, prev)
        shapes.append(v)
        prev = v
        c.part(role, [(v, bar * beats, hold or beats)], vel)
    return shapes


def reverie(c: Cue):
    """Slow and suspended: a music box turning over open maj9 chords that slide in parallel above a held tonic,
    strings underneath, an electric piano, and in the second half a flute leaning on the 9ths."""
    c.new_score(bpm=68 + 10 * c.r.u(), hall=2.6)
    tonic, chords = _colour(c, "lydian", ["lydian", "mediant"])
    mode = "lydian" if any(ch[0] == 2 for ch in chords) else "major"
    shapes = _pad(c, "pad", tonic, chords, 4, 0.45, parallel=c.r.u() < 0.5)
    for bar, (ch, v) in enumerate(zip(chords, shapes, strict=True)):
        notes = sorted(v) + [v[0] + 12]
        order = [0, 1, 2, 3, 4, 3, 2, 1] if len(notes) >= 5 else [0, 1, 2, 3, 2, 1, 2, 3]
        c.part("music_box", [(notes[order[j] % len(notes)] + 12, 4 * bar + 0.5 * j, 0.5) for j in range(8)], 0.5)
        c.part("keys", [(v, 4 * bar, 2, 0.45), (v, 4 * bar + 2.5, 1.5, 0.35)])
        pedal = tonic - 12 if bar < 8 else bass_note(tonic, ch, 40)
        c.part("low_strings", [(pedal, 4 * bar, 4)], 0.45)
    mel = color_melody(c.r, tonic + 12, mode, chords[8:], CALM, low=67, high=88, color=0.45)
    c.part("lead", [(n, b + 32, ln) for n, b, ln in mel], 0.6)
    c.part("celesta", [(n + 12, b + 32.5, ln) for n, b, ln in mel[::3]], 0.35)
    c.part("bells", [(tonic + 24 + 7, 0, 2), (tonic + 24 + 14, 32, 2)], 0.4)
    _loop(c, len(chords))


def pastoral(c: Cue):
    """In six-eight, open air: a flute tune over harp arpeggios and a Mixolydian lilt (I - bVII - IV), the bass
    holding the tonic as a drone for the first phrase."""
    c.new_score(bpm=170 + 30 * c.r.u(), meter=6, hall=2.2)
    tonic, chords = _colour(c, "mixolydian", ["mixolydian", "lydian"])
    mode = "mixolydian" if any(ch[0] == 10 for ch in chords) else "lydian"
    prev = None
    for bar, ch in enumerate(chords):
        v = open_voicing(tonic, ch, prev)
        prev = v
        b = 6 * bar
        root = bass_note(tonic, ch, 43)
        arp = [root, root + 7, root + 12] + sorted(v)[:3]
        c.part("arp", [(arp[j % len(arp)], b + j, 1.5) for j in range(6)], 0.55)
        c.part("pad", [(v, b, 6)], 0.35)
        bass = tonic - 12 if bar < 4 else bass_note(tonic, ch, 36)
        c.part("e_bass", [(bass, b, 2.5), (bass + 7, b + 3, 2.5)], 0.6)
        c.part("tambourine", [(70, b + 3, 1, 0.35)])
    c.part("lead", color_melody(c.r, tonic + 12, mode, chords, SIX8, beats=6, low=67, high=88, color=0.3), 0.7)
    _loop(c, len(chords))


def timeless(c: Cue):
    """Mysterious and turning: a sixteenth-note ostinato (marimba, electric piano) through Lydian or Dorian colours,
    hand drums, a choir, the bass holding the tonic and its fifth, a bell melody in long notes."""
    c.new_score(bpm=92 + 14 * c.r.u(), hall=2.4)
    tonic, chords = _colour(c, "lydian", ["lydian", "dorian", "half_step"])
    mode = "dorian" if any(ch[1].startswith("m") for ch in chords[:1]) else "lydian"
    prev = None
    pattern = c.r.pick([[0, 2, 1, 3, 2, 1, 4, 3], [0, 1, 2, 4, 3, 2, 1, 2], [0, 2, 4, 2, 1, 3, 2, 3]])
    for bar, ch in enumerate(chords):
        v = open_voicing(tonic, ch, prev)
        prev = v
        notes = sorted(v) + [v[0] + 12, v[1] + 12]
        c.part("mallet", [(notes[pattern[j % 8] % len(notes)], 4 * bar + 0.25 * j, 0.3, 0.55 + 0.2 * (j % 4 == 0))
                          for j in range(16)], 0.6)
        c.part("choir", [(v, 4 * bar, 4)], 0.4)
        c.part("low_strings", [([tonic - 12, tonic - 5], 4 * bar, 4)], 0.45)
        c.part("hand_drum", [(52, 4 * bar, 0.5, 0.8), (59, 4 * bar + 1.5, 0.5, 0.5), (52, 4 * bar + 2.5, 0.5, 0.6),
                             (59, 4 * bar + 3, 0.5, 0.5), (64, 4 * bar + 3.5, 0.5, 0.4)])
        c.part("shaker", [(60, 4 * bar + 0.25 * j, 0.2, 0.2 + 0.25 * (j % 2)) for j in range(16)])
    mel = color_melody(c.r, tonic + 12, mode, chords, CALM[:3], low=67, high=86, color=0.5)
    c.part("lead", mel, 0.6)
    c.part("bells", [(n + 12, b, ln) for n, b, ln in mel], 0.45)
    _loop(c, len(chords))


def grove(c: Cue):
    """A Dorian groove: syncopated electric bass, hi-hats, electric piano comping off the beat, a marimba tune and
    then the flute, through an i - IV vamp and an Aeolian slide (i - bVII - bVI - v)."""
    c.new_score(bpm=98 + 14 * c.r.u(), hall=1.8)
    tonic = 55 + int(c.r.u() * 12)
    chords = c.r.pick(PALETTES["dorian"]) * 2 + c.r.pick(PALETTES["aeolian"]) * 2
    prev = None
    for bar, ch in enumerate(chords):
        v = open_voicing(tonic, ch, prev)
        prev = v
        b, root = 4 * bar, bass_note(tonic, ch, 36)
        c.part("e_bass", [(root, b, 0.7), (root + 12, b + 0.75, 0.25), (root + 7, b + 1.5, 0.5), (root, b + 2, 0.5),
                          (root + 10, b + 2.75, 0.5), (root + 12, b + 3.5, 0.5)], 0.75)
        c.part("keys", [(v, b + 0.5, 0.4, 0.5), (v, b + 1.75, 0.5, 0.45), (v, b + 3, 0.6, 0.5)])
        c.part("hat", [(70, b + 0.5 * j, 0.25, 0.35 + 0.25 * (j % 2 == 0)) for j in range(8) if j != 7])
        c.part("open_hat", [(70, b + 3.5, 0.5, 0.4)])
        c.part("kick", [(36, b, 0.5, 0.7), (36, b + 2.5, 0.5, 0.5)])
        c.part("hand_drum", [(57, b + 1, 0.5, 0.6), (57, b + 3, 0.5, 0.7)])
    c.part("mallet", color_melody(c.r, tonic + 12, "dorian", chords[:8], LIVELY, low=67, high=86), 0.75)
    flute = color_melody(c.r, tonic + 12, "minor", chords[8:], CALM + LIVELY[:2], low=67, high=86)
    c.part("lead", [(n, b + 32, ln) for n, b, ln in flute], 0.7)
    _loop(c, len(chords))


def heroic(c: Cue):
    """A march for the hero: brass melody with wide leaps over I - bVI - bVII - I and I - bVII - IV, strings driving
    in eighths, horns holding the harmony, snare, timpani and a cymbal at each phrase."""
    c.new_score(bpm=138 + 14 * c.r.u(), hall=2.2)
    tonic, chords = _colour(c, "major", ["heroic", "mixolydian"])
    prev = None
    for bar, ch in enumerate(chords):
        v = open_voicing(tonic, ch, prev)
        prev = v
        b, root = 4 * bar, bass_note(tonic, ch, 40)
        c.part("strings", [(root + (0, 7, 12, 7)[j % 4], b + 0.5 * j, 0.45) for j in range(8)], 0.6)
        c.part("horns", [(v, b, 4)], 0.6)
        c.part("low_strings", [(root, b, 4)], 0.6)
        c.part("snare", [(60, b + x, 0.25, g) for x, g in ((0, 0.7), (1, 0.5), (1.75, 0.35), (2, 0.6), (3, 0.5),
                                                            (3.5, 0.4), (3.75, 0.45))])
        c.part("timpani", [(bass_note(tonic, ch, 40), b, 1, 0.8)])
        c.part("kick", [(36, b, 0.5, 0.6), (36, b + 2, 0.5, 0.5)])
        if bar % 4 == 0:
            c.part("crash", [(60, b, 2, 0.6)])
    c.part("brass", color_melody(c.r, tonic + 12, "mixolydian" if any(ch[0] == 10 for ch in chords) else "major",
                                 chords, DRIVING + LIVELY[:2], low=62, high=84, color=0.15, leap=0.3), 0.85)
    _loop(c, len(chords))


def showdown(c: Cue):
    """A 16-bit battle: minor with chromatic planing (i - bII - i - bVII), an octave-jumping bass, a full kit,
    brass stabs off the beat, strings in sixteenths, a lead that leaps."""
    c.new_score(bpm=158 + 14 * c.r.u(), hall=1.6)
    tonic, chords = _colour(c, "minor", ["chromatic", "half_step", "aeolian"])
    prev = None
    for bar, ch in enumerate(chords):
        v = open_voicing(tonic, ch, prev)
        prev = v
        b, root = 4 * bar, bass_note(tonic, ch, 36)
        c.part("e_bass", [(root + (0, 12)[j % 2], b + 0.5 * j, 0.4, 0.8 - 0.2 * (j % 2)) for j in range(8)], 0.8)
        notes = sorted(v)
        c.part("strings", [(notes[(j * 2 + j // 4) % len(notes)] + 12, b + 0.25 * j, 0.22, 0.5) for j in range(16)],
               0.55)
        c.part("horns", [(v, b, 0.4, 0.85), (v, b + 1.5, 0.4, 0.75), (v, b + 3, 0.4, 0.8)])
        c.part("kick", [(36, b, 0.5, 0.9), (36, b + 1.5, 0.5, 0.6), (36, b + 2.5, 0.5, 0.8)])
        c.part("snare", [(60, b + 1, 0.5, 0.8), (60, b + 3, 0.5, 0.85)])
        c.part("hat", [(70, b + 0.5 * j, 0.25, 0.4 + 0.2 * (j % 2 == 0)) for j in range(8)])
        if bar % 4 == 0:
            c.part("crash", [(60, b, 2, 0.7)])
    c.part("brass", color_melody(c.r, tonic + 12, "harmonic", chords, DRIVING, low=62, high=84, color=0.2,
                                 leap=0.3), 0.9)
    _loop(c, len(chords))


COLOR_CUES = ("reverie", "pastoral", "timeless", "grove", "heroic", "showdown")

CUES: dict[str, Callable[[Cue], None]] = {
    "victory": victory, "levelup": levelup, "quest": quest, "gameover": gameover,
    "town": town, "explore": explore, "tavern": tavern, "dungeon": dungeon, "battle": battle,
    "reverie": reverie, "pastoral": pastoral, "timeless": timeless, "grove": grove, "heroic": heroic,
    "showdown": showdown,
}

from . import music_tactics  # noqa: E402,F401  (the tactics cues register themselves)
