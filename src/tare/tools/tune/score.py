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
from dataclasses import asdict, dataclass, field

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

from . import rng
from .diagnostics import current, digest, origin, pcm_id
from .loudness import true_peak
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
    chord: tuple = ()     # semitones from `f` of every note of the chord, for an instrument that arpeggiates

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
    events: list = field(default_factory=list)
    origins: list = field(default_factory=list)

    def add(self, *layers) -> "Track":
        """Spec layers (Syllable, Modal, Noise, Scatter, ChipProgram) at their own start times, in seconds."""
        for layer in layers:
            self.origins.append({"layer": len(self.layers), "event": None, "source": origin()})
            self.layers.append(layer)
        return self

    def play(self, instrument: str | Instrument, notes: Iterable, velocity: float = 0.8, transpose: float = 0.0,
             offset: float = 0.0) -> "Track":
        """`notes`: (note, beat, beats[, velocity]) with note a name, a MIDI number or a list of them (a chord);
        beats count from `offset` beats. An instrument marked `arp` (a chip's one-voice channel) gets each chord
        whole, in its first note."""
        from .instruments import INSTRUMENTS
        fn = INSTRUMENTS[instrument] if isinstance(instrument, str) else instrument
        arp = getattr(fn, "arp", False)
        where = origin()
        for i, item in enumerate(notes):
            note, beat, beats, *vel = item
            pitches = note if isinstance(note, list | tuple) else [note]
            spread = tuple(midi(p) - midi(pitches[0]) for p in pitches) if arp and len(pitches) > 1 else ()
            for j, n in enumerate(pitches):
                k = rng.key(self.score.seed, self.name, len(self.layers), i, j)
                event_id = f"{self.name}/e{len(self.events)}"
                first = len(self.layers)
                effective = vel[0] if vel else velocity
                if not (spread and j):
                    self.layers += fn(Note(self.score.beats(offset + beat), self.score.beats(beats),
                                           hz(midi(n) + transpose), effective, k, spread))
                module = getattr(instrument, "__module__", "?")
                qualname = getattr(instrument, "__qualname__", type(instrument).__name__)
                instrument_name = instrument if isinstance(instrument, str) else f"{module}.{qualname}"
                self.events.append({"id": event_id, "instrument": instrument_name,
                                    "custom": not isinstance(instrument, str), "note": n, "pitch": midi(n) + transpose,
                                    "beat": float(beat), "offset": float(offset), "beats": float(beats),
                                    "bpm": self.score.bpm, "start": self.score.beats(offset + beat),
                                    "duration": self.score.beats(beats), "velocity": float(effective),
                                    "transpose": float(transpose), "seed": k, "source": where,
                                    "layers": list(range(first, len(self.layers)))})
                self.events[-1]["layer_hashes"] = [digest(asdict(layer)) for layer in self.layers[first:]]
                self.origins.extend({"layer": index, "event": event_id, "source": where}
                                    for index in range(first, len(self.layers)))
        return self

    def render(self, sr: int) -> np.ndarray:
        kinds = {Syllable: "syllables", Modal: "modal", Noise: "noise", Scatter: "scatter", ChipProgram: "chips"}
        groups: dict[str, list] = {}
        for layer in self.layers:
            groups.setdefault(kinds[type(layer)], []).append(layer)
        y = render(Voice(**groups, seed=rng.key(self.score.seed, self.name) & 0x7FFFFFFF, **self.voice), sr)
        if (rec := current()) is not None:
            node = rec.nodes[-1]
            node["track"] = {"name": self.name, "events": self.events, "origins": self.origins}
            ordered = [(index, layer) for kind in (Syllable, ChipProgram, Modal, Noise, Scatter)
                       for index, layer in enumerate(self.layers) if type(layer) is kind]
            # render() groups effect layers after chips in its documented order.
            for part, (index, _) in zip(node["parts"], ordered, strict=True):
                part["event"] = next((e["id"] for e in self.events if index in e["layers"]), None)
                part["origin"] = next((entry for entry in self.origins if entry["layer"] == index),
                                      {"source": "unknown", "layer": index})
        return y.astype(np.float64) / PEAK


UNPITCHED = {"bass_drum", "snare", "hihat", "open_hat", "crash", "tambourine", "triangle", "hand_drum", "log_drum",
             "taiko", "gong", "shaker", "hyoshigi", "chip_kick", "chip_snare", "chip_hat"}


def arrangement(parts: dict, bar_beats: float = 4, block_bars: int = 4) -> dict:
    """How a piece is laid out, read from its notes: `parts` maps each part to its (beat, pitch) notes, pitch None
    for unpitched percussion. What 22 orchestral scores of game music shared, and what these numbers look for: one
    note per attack in a part (lines, not block chords), few leaps over a fourth, parts that come in a few at a
    time and a busiest stretch several times fuller than the emptiest. Numbers for comparing layouts, never for
    how a piece sounds. Blocks are `block_bars` bars; a short last block is left out of the two ratios."""
    pitched = {name: sorted((b, p) for b, p in notes if p is not None) for name, notes in parts.items()}
    pitched = {name: notes for name, notes in pitched.items() if notes}
    written = sum(len(notes) for notes in pitched.values())
    attacks, moves = 0, []
    for notes in pitched.values():
        tops: dict[float, float] = {}
        for b, p in notes:
            tops[round(b, 3)] = max(p, tops.get(round(b, 3), p))
        attacks += len(tops)
        line = [tops[b] for b in sorted(tops)]
        moves += [abs(b - a) for a, b in zip(line, line[1:], strict=False)]
    distinct = {(round(b, 3), p) for notes in pitched.values() for b, p in notes}
    end = max((b for notes in parts.values() for b, _ in notes), default=0.0)
    size = bar_beats * block_bars
    blocks = int(end // size) + 1
    who = [sum(any(i * size <= b < (i + 1) * size for b, _ in notes) for notes in parts.values())
           for i in range(blocks)]
    density = [sum(sum(i * size <= b < (i + 1) * size for b, _ in notes) for notes in parts.values()) / block_bars
               for i in range(blocks)]
    full = slice(0, blocks - 1) if blocks > 1 and end - (blocks - 1) * size < size / 2 else slice(None)
    bars = max(int(end // bar_beats) + 1, 1)
    return {
        "parts": len(parts), "notes": sum(len(notes) for notes in parts.values()),
        "notes_per_attack": round(written / max(attacks, 1), 2),
        "steps_share": round(sum(0 < m <= 2 for m in moves) / max(len(moves), 1), 2),
        "leaps_share": round(sum(m > 5 for m in moves) / max(len(moves), 1), 2),
        "doubling": round(written / max(len(distinct), 1), 2),
        "distinct_notes_per_bar": round(len(distinct) / bars, 1),
        "parts_by_block": who, "notes_per_bar_by_block": [round(d, 1) for d in density],
        "parts_growth": round(max(who[full]) / max(min(who[full]), 1), 1),
        "density_ratio": round(max(density[full]) / max(min(density[full]), 0.25), 1),
    }


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
    placed_origins: list = field(default_factory=list)
    effects: list = field(default_factory=list)

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
        self.placed_origins.append({"source": origin(), "kind": "voice" if isinstance(sound, Voice) else "audio",
                                    "spec": sound.to_dict() if isinstance(sound, Voice) else None,
                                    "pcm": pcm_id(y, self.sr), "regeneration": "materialized_only"})
        return self

    def render(self, loop: float | None = None, gain: float = 1.0) -> np.ndarray:
        """Stereo float32, shape (n, 2), true peak at -1 dBTP times `gain` (before `effects`). With `loop`
        (seconds, e.g. ``score.bar(8)``) the result is exactly that long and loops seamlessly: what rings past the
        end, the hall's tail included, wraps onto the start."""
        sr = self.sr
        rec = current()
        settings = {k: getattr(self, k) for k in ("bpm", "meter", "hall", "echo", "lowpass", "seed", "sr", "effects")}
        node = rec.begin("score", settings) if rec is not None else None
        parts = []
        children = []
        labels = []
        for t in self.tracks.values():
            if t.layers:
                parts.append((0.0, t.render(sr) * t.gain, t.pan, t.send, t.echo))
                children.append((rec.last, t.gain / PEAK) if rec is not None else (None, 1))
                labels.append(t.name)
        parts += [(at, y * g, pan, send, echo) for at, y, g, pan, send, echo in self.sounds]
        children += [(None, 1)] * len(self.sounds)
        labels += [f"placed[{i}]" for i in range(len(self.sounds))]
        if not parts:
            raise ValueError("the score is empty")
        n = self._length(parts)
        if rec is not None:
            node.update(input_length=n, loop=loop, gain=gain)
            for (at, y, pan, send, echo), (child, scale), label in zip(parts, children, labels, strict=True):
                rec.part(node, y, int(at * sr), label, child=child,
                         params={"pan": pan, "send": send, "echo": echo})
                node["parts"][-1]["child_scale"] = scale
                if child:
                    node["parts"][-1]["track_gain"] = self.tracks[label].gain
        result = self.finish(*self._buses(parts, n), loop=loop, gain=gain)
        if rec is not None:
            rec.end(node, result)
        return result

    def clashes(self, overlap: float = 0.5, held: float = 0.75) -> list[dict]:
        """Pitched notes a minor second (or a ninth, or more octaves) apart that sound together for at least
        `overlap` beats, one of them held at least `held` beats: what an ear hears as a rub, found in the score
        without rendering. Percussion is left out. Each: {"bar", "beat", "beats", "notes": [(track, MIDI), ...],
        "kind", "same_track", "interval"}. A "chord" rub starts with both notes, so it is built into the harmony;
        a "line" rub is a note entering over another (passing, leaning, or a tune that ignores its chord). In a
        blind round, an untrained listener rated worst the cues with rubs within one track and best those with
        lines over chords; the count alone said nothing."""
        notes = [(t.name, e["pitch"], e["offset"] + e["beat"], e["beats"]) for t in self.tracks.values()
                 for e in t.events if e["instrument"] not in UNPITCHED]
        if len(notes) < 2:
            return []
        name, p, s, d = zip(*notes, strict=True)
        p, s, d = np.array(p), np.array(s), np.array(d)
        e = s + d
        both = np.minimum(e[:, None], e) - np.maximum(s[:, None], s)      # ponytail: all pairs, fine to a few 1000
        rub = (np.round(np.abs(p[:, None] - p)) % 12 == 1) & (both >= overlap) & (np.maximum(d[:, None], d) >= held)
        return [{"bar": int(max(s[i], s[j]) // self.meter) + 1, "beat": round(float(max(s[i], s[j])), 3),
                 "beats": round(float(both[i, j]), 3), "notes": [(name[i], float(p[i])), (name[j], float(p[j]))],
                 "kind": "chord" if abs(s[i] - s[j]) < 0.05 else "line", "same_track": name[i] == name[j],
                 "interval": int(round(abs(p[i] - p[j])))}
                for i, j in zip(*np.nonzero(np.triu(rub, 1)), strict=True)]

    def arrangement(self, block_bars: int = 4) -> dict:
        """The score's layout by its notes, without rendering (see `arrangement`): notes per attack, leaps, how
        many tracks play in each `block_bars` bars and how full each is. A chord counts as its notes."""
        return arrangement({t.name: [(e["offset"] + e["beat"], None if e["instrument"] in UNPITCHED else e["pitch"])
                                     for e in t.events] for t in self.tracks.values() if t.events},
                           self.meter, block_bars)

    def render_layers(self, groups: dict[str, list[str]], loop: float, gain: float = 1.0) -> dict[str, np.ndarray]:
        """A loop split into stems that add up to ``render(loop, gain)``: each group of tracks goes through the same
        hall, echo, lowpass and fold, scaled by the whole mix's peak. Adaptive music starts every stem together and
        fades groups in and out. Every track belongs to one group; placed sounds and effects cannot be split."""
        rendered = {name: t for name, t in self.tracks.items() if t.layers}
        if sorted(n for names in groups.values() for n in names) != sorted(rendered):
            raise ValueError(f"each track must be in exactly one group: {', '.join(rendered)}")
        if self.sounds or self.effects or not loop:
            raise ValueError("only a loop of tracks, without placed sounds or effects, splits into layers")
        parts = {name: (0.0, t.render(self.sr) * t.gain, t.pan, t.send, t.echo) for name, t in rendered.items()}
        n = self._length(list(parts.values()))
        mixes = {g: self._premix(*self._buses([parts[t] for t in names], n), loop) for g, names in groups.items()}
        peak = true_peak(sum(mixes.values()))
        return {g: (PEAK * gain * out / (peak + 1e-12)).astype(np.float32) for g, out in mixes.items()}

    def _length(self, parts) -> int:
        """Samples the parts need, plus the hall's or the echo's tail."""
        tail = self.hall
        if self.echo:
            delay, fb, _ = self.echo
            tail = max(tail, delay * (1 + np.log(1e-3) / np.log(max(min(fb, 0.95), 0.01))))
        return max(int(at * self.sr) + len(y) for at, y, *_ in parts) + int(tail * self.sr)

    def _buses(self, parts, n: int):
        """The parts placed and panned: the dry stereo mix and the mono sends to the hall and the echo."""
        dry, bus, ebus = np.zeros((n, 2)), np.zeros(n), np.zeros(n)
        for at, y, pan, send, echo in parts:
            k = int(at * self.sr)
            stereo = y if y.ndim == 2 else y[:, None] * _pan(pan)
            mono = y if y.ndim == 1 else y.mean(axis=1)
            dry[k:k + len(y)] += stereo
            bus[k:k + len(y)] += send * mono
            ebus[k:k + len(y)] += echo * mono
        return dry, bus, ebus

    def _premix(self, dry, bus, ebus, loop=None):
        """Hall, echo, lowpass and the loop's fold: all linear, so stems mixed apart add up to the mix."""
        sr = self.sr
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
        return out

    def finish(self, dry, bus, ebus, *, loop=None, gain=1.0, fixed=None):
        """Legacy mix processing, shared with captured interventions at fixed gains/length."""
        sr = self.sr
        out = self._premix(dry, bus, ebus, loop)
        if not loop:
            end = np.nonzero(np.abs(out).max(axis=1) > 1e-4)[0]
            out = out[: end[-1] + 1] if len(end) else out
        if fixed is not None:
            length = fixed["length"]
            out = np.pad(out[:length], ((0, max(0, length - len(out))), (0, 0)))
        peak = true_peak(out) if fixed is None else fixed["output_peak"]   # between samples too: encoders clip there
        if (rec := current()) is not None:
            rec.factor("output_peak", float(peak))
            rec.factor("length", len(out))
        result = (PEAK * gain * out / (peak + 1e-12)).astype(np.float32)
        if self.effects:
            from .effects import apply_effects
            result = apply_effects(result, sr, self.effects, loop=bool(loop), fixed=fixed)
        return result

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
