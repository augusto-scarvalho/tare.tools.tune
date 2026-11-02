"""Tracker-like note input compiled to the existing Score API."""
import math

from .score import midi


def parse_pattern(text: str, *, steps_per_beat=4, meter=4):
    if not isinstance(steps_per_beat, int) or not isinstance(meter, int) or \
            steps_per_beat < 1 or meter < 1 or not isinstance(text, str):
        raise ValueError("pattern steps and meter must be positive integers")
    notes = []
    step = 0
    for token in text.split():
        if step > 8192:
            raise ValueError("pattern exceeds 8192 steps")
        if token == "|":
            if step % (steps_per_beat * meter):
                raise ValueError("pattern bar does not match Score.meter")
            continue
        if token == "-":
            if not notes or not math.isclose(notes[-1][1] + notes[-1][2], step / steps_per_beat, abs_tol=1e-9):
                raise ValueError("hold must follow a note or hold")
            notes[-1][2] += 1 / steps_per_beat
        elif token != ".":
            accented = token.endswith("!") or token == "X"
            token = token.rstrip("!")
            pitches = [60] if token in ("x", "X") else token.split("+")
            for pitch in pitches:
                midi(pitch)
            notes.append([pitches if len(pitches) > 1 else pitches[0], step / steps_per_beat,
                          1 / steps_per_beat, 1.0 if accented else 0.8])
        step += 1
    if not step:
        raise ValueError("pattern is empty")
    return [tuple(note) for note in notes], step / steps_per_beat
