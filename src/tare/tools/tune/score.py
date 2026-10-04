"""Scores: notes and finished sounds placed in time, panned and mixed to stereo through one shared hall.

    >>> from tare.tools.tune import Sfx, write_wav
    >>> from tare.tools.tune.score import Score
    >>> score = Score(bpm=96)
    >>> harp = score.track("harp", pan=-0.3, send=0.3)
    >>> harp.play("harp", [("A4", 0, 1), ("C5", 1, 1), ("E5", 2, 2)])   # (note, beat, beats[, velocity])
    >>> score.add(Sfx("blade", "steel").render("clash"), at=score.beats(4), pan=0.5)
    >>> write_wav("cue.wav", score.render(), score.sr)                   # (n, 2) float32

A track is one Voice: its notes share the track's processing (drive, crush, lowpass, room) and are rendered
together, dry; the score then pans every track and every placed sound, and sends a share of each to a stereo
hall (two decorrelated tails, one per ear) and, if the score has one, to an echo (repeats bouncing between the
ears, darker each time, like a 16-bit console's echo unit). ``render(loop=...)`` wraps whatever rings past the
loop point back onto the start, so a music loop repeats without a seam.
"""
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

from . import rng
from .render import DEFAULT_SR, PEAK, render
from .spec import ChipProgram, Modal, Noise, Scatter, Syllable, Voice

NOTE = re.compile(r"^([A-Ga-g])([#b]*)(-?\d+)$")
LETTER = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
CHORDS = {"": (0, 4, 7), "m": (0, 3, 7), "dim": (0, 3, 6), "aug": (0, 4, 8), "sus2": (0, 2, 7), "sus4": (0, 5, 7),
          "7": (0, 4, 7, 10), "maj7": (0, 4, 7, 11), "m7": (0, 3, 7, 10), "dim7": (0, 3, 6, 9),
          "m7b5": (0, 3, 6, 10), "add9": (0, 4, 7, 14), "madd9": (0, 3, 7, 14), "6": (0, 4, 7, 9), "m6": (0, 3, 7, 9),
          "5": (0, 7)}
SCALES = {"major": (0, 2, 4, 5, 7, 9, 11), "minor": (0, 2, 3, 5, 7, 8, 10), "dorian": (0, 2, 3, 5, 7, 9, 10),
          "phrygian": (0, 1, 3, 5, 7, 8, 10), "lydian": (0, 2, 4, 6, 7, 9, 11), "mixolydian": (0, 2, 4, 5, 7, 9, 10),
          "harmonic": (0, 2, 3, 5, 7, 8, 11), "pentatonic": (0, 2, 4, 7, 9), "minor pentatonic": (0, 3, 5, 7, 10),
          "blues": (0, 3, 5, 6, 7, 10),
          "in": (0, 1, 5, 7, 8), "yo": (0, 2, 5, 7, 9), "ryukyu": (0, 4, 5, 7, 11)}   # Japan's pentatonic scales


def midi(note: str | int | float) -> float:
    """A note name ("A4", "C#5", "Eb3") or a MIDI number -> MIDI number (A4 = 69)."""
    if not isinstance(note, str):
        return float(note)
    m = NOTE.match(note.strip())
    if not m:
        raise ValueError(f"not a note: {note!r} (try 'A4', 'C#5', 'Eb3')")
    letter, acc, octave = m.groups()
    return float(12 * (int(octave) + 1) + LETTER[letter.upper()] + acc.count("#") - acc.count("b"))


def hz(note: str | int | float) -> float:
    return 440.0 * 2 ** ((midi(note) - 69) / 12)


def chord(name: str, octave: int = 4) -> list[float]:
    """A chord symbol ("Am", "F", "G7", "Cmaj7", "Bdim", "Dsus4") -> MIDI notes, root in `octave`."""
    m = re.match(r"^([A-Ga-g][#b]?)(.*)$", name.strip())
    if not m or m.group(2) not in CHORDS:
        raise ValueError(f"unknown chord {name!r}; qualities: {', '.join(repr(q) for q in CHORDS)}")
    root = midi(f"{m.group(1)}{octave}")
    return [root + i for i in CHORDS[m.group(2)]]


def scale(root: str, mode: str = "major", octave: int = 4) -> list[float]:
    """One octave of a scale from `root` -> MIDI notes."""
    if mode not in SCALES:
        raise ValueError(f"unknown scale {mode!r}; choose from {', '.join(SCALES)}")
    base = midi(f"{root}{octave}")
    return [base + i for i in SCALES[mode]]


@dataclass(frozen=True)
class Note:
    """What an instrument gets for each note: when, how long, which pitch, how hard, and its own random stream."""

    start: float          # seconds
    dur: float            # seconds the note is held (struck instruments ring on past it)
    f: float              # Hz
    vel: float            # 0..1
    seed: int

    def rand(self, name: str) -> float:
        return rng.uniform(rng.key(self.seed, name))


Instrument = Callable[[Note], list]


@dataclass
class Track:
    """Notes and spec layers rendered together as one Voice, then panned and sent to the hall."""

    score: "Score"
    name: str
    gain: float = 1.0
    pan: float = 0.0                  # -1 left .. 1 right
    send: float = 0.2                 # share sent to the score's hall
    voice: dict = field(default_factory=dict)   # Voice processing: drive, crush, lowpass, room, air
    echo: float = 0.0                 # share sent to the score's echo
    layers: list = field(default_factory=list)

    def add(self, *layers) -> "Track":
        """Spec layers (Syllable, Modal, Noise, Scatter, ChipProgram) at their own start times, in seconds."""
        self.layers.extend(layers)
        return self

    def play(self, instrument: str | Instrument, notes: Iterable, velocity: float = 0.8, transpose: float = 0.0,
             offset: float = 0.0) -> "Track":
        """`notes`: (note, beat, beats[, velocity]) with note a name, a MIDI number or a list of them (a chord);
        beats count from `offset` beats."""
        from .instruments import INSTRUMENTS
        fn = INSTRUMENTS[instrument] if isinstance(instrument, str) else instrument
        for i, item in enumerate(notes):
            note, beat, beats, *vel = item
            for j, n in enumerate(note if isinstance(note, list | tuple) else [note]):
                k = rng.key(self.score.seed, self.name, len(self.layers), i, j)
                self.layers += fn(Note(self.score.beats(offset + beat), self.score.beats(beats),
                                       hz(midi(n) + transpose), vel[0] if vel else velocity, k))
        return self

    def render(self, sr: int) -> np.ndarray:
        kinds = {Syllable: "syllables", Modal: "modal", Noise: "noise", Scatter: "scatter", ChipProgram: "chips"}
        groups: dict[str, list] = {}
        for layer in self.layers:
            groups.setdefault(kinds[type(layer)], []).append(layer)
        y = render(Voice(**groups, seed=rng.key(self.score.seed, self.name) & 0x7FFFFFFF, **self.voice), sr)
        return y.astype(np.float64) / PEAK


@dataclass
class Score:
    """A timeline in beats and seconds: tracks of notes, finished sounds, one stereo hall."""

    bpm: float = 100.0
    meter: int = 4                    # beats per bar
    hall: float = 2.2                 # reverb tail of the shared hall, seconds
    echo: tuple | None = None         # (delay s, feedback, tone Hz): repeats alternating left/right
    lowpass: float = 0.0              # Hz, 0 = off: the whole mix darkened (an old console's sample playback)
    seed: int = 0
    sr: int = DEFAULT_SR
    tracks: dict = field(default_factory=dict)
    sounds: list = field(default_factory=list)

    def beats(self, n: float) -> float:
        """`n` beats in seconds."""
        return n * 60.0 / self.bpm

    def bar(self, n: float, beat: float = 0.0) -> float:
        """The start of bar `n` (from 0), plus `beat` beats, in seconds."""
        return self.beats(n * self.meter + beat)

    def track(self, name: str, gain: float = 1.0, pan: float = 0.0, send: float = 0.2, echo: float = 0.0,
              **voice) -> Track:
        """A new track, or the existing one of that name."""
        if name not in self.tracks:
            self.tracks[name] = Track(self, name, gain, pan, send, voice, echo=echo)
        return self.tracks[name]

    def add(self, sound: np.ndarray | Voice, at: float = 0.0, gain: float = 1.0, pan: float = 0.0,
            send: float = 0.0, echo: float = 0.0) -> "Score":
        """A finished sound (mono or stereo samples at the score's rate, or a Voice) at `at` seconds. It keeps its
        own level: an Sfx rendered gently stays quieter than one rendered at full power."""
        y = render(sound, self.sr) if isinstance(sound, Voice) else np.asarray(sound, dtype=np.float64)
        self.sounds.append((at, y, gain, pan, send, echo))
        return self

    def render(self, loop: float | None = None, gain: float = 1.0) -> np.ndarray:
        """Stereo float32, shape (n, 2), peak at -1 dBFS times `gain`. With `loop` (seconds, e.g.
        ``score.bar(8)``) the result is exactly that long and loops seamlessly: what rings past the end, the hall's
        tail included, wraps onto the start."""
        sr = self.sr
        parts = [(0.0, t.render(sr) * t.gain, t.pan, t.send, t.echo) for t in self.tracks.values() if t.layers]
        parts += [(at, y * g, pan, send, echo) for at, y, g, pan, send, echo in self.sounds]
        if not parts:
            raise ValueError("the score is empty")
        tail = self.hall
        if self.echo:
            delay, fb, _ = self.echo
            tail = max(tail, delay * (1 + np.log(1e-3) / np.log(max(min(fb, 0.95), 0.01))))
        n = max(int(at * sr) + len(y) for at, y, *_ in parts) + int(tail * sr)
        dry, bus, ebus = np.zeros((n, 2)), np.zeros(n), np.zeros(n)
        for at, y, pan, send, echo in parts:
            k = int(at * sr)
            stereo = y if y.ndim == 2 else y[:, None] * _pan(pan)
            mono = y if y.ndim == 1 else y.mean(axis=1)
            dry[k:k + len(y)] += stereo
            bus[k:k + len(y)] += send * mono
            ebus[k:k + len(y)] += echo * mono
        out = dry + self._hall(bus) if self.hall and bus.any() else dry
        if self.echo and ebus.any():
            out = out + self._echo(ebus)
        if self.lowpass:
            out = sosfilt(butter(2, min(self.lowpass, 0.45 * sr) / (sr / 2), output="sos"), out, axis=0)
        if loop:
            length = int(round(loop * sr))
            folded = np.zeros((length, 2))
            for start in range(0, len(out), length):
                chunk = out[start:start + length]
                folded[:len(chunk)] += chunk
            out = folded
        else:
            end = np.nonzero(np.abs(out).max(axis=1) > 1e-4)[0]
            out = out[: end[-1] + 1] if len(end) else out
        return (PEAK * gain * out / (np.max(np.abs(out)) + 1e-12)).astype(np.float32)

    def _hall(self, x: np.ndarray) -> np.ndarray:
        """Two decorrelated noise tails, one per ear, darkened above 5 kHz, at unit energy."""
        n = int(self.hall * self.sr)
        decay = np.exp(-6.9 * np.arange(n) / n)
        sos = butter(2, 5000 / (self.sr / 2), output="sos")
        wet = []
        for side in ("left", "right"):
            ir = sosfilt(sos, rng.noise(rng.key(self.seed, "hall", side), n) * decay)
            ir[: int(0.012 * self.sr)] = 0.0                      # a short gap before the first reflections
            wet.append(fftconvolve(x, ir / np.sqrt(np.sum(ir ** 2)))[: len(x)])
        return np.stack(wet, axis=1)


    def _echo(self, x: np.ndarray) -> np.ndarray:
        """Repeats every `delay` seconds, `feedback` times quieter and once more low-passed each time, bouncing
        between left and right."""
        delay, fb, tone = self.echo
        d = max(int(delay * self.sr), 1)
        sos = butter(1, min(tone, 0.45 * self.sr) / (self.sr / 2), output="sos")
        out, y, k, g = np.zeros((len(x), 2)), x, 1, 1.0
        while k * d < len(x) and g > 1e-3:
            y = sosfilt(sos, y)
            out[k * d:, (k - 1) % 2] += g * y[: len(x) - k * d]
            k, g = k + 1, g * fb
        return out


def _pan(pan: float) -> np.ndarray:
    """Equal-power pan law: -1 left, 0 centre (-3 dB each side), 1 right."""
    a = (min(max(pan, -1.0), 1.0) + 1) * np.pi / 4
    return np.array([np.cos(a), np.sin(a)])
