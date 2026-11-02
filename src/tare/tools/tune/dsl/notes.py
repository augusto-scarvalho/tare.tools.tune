"""Beat-domain construction and span-preserving operations before instrument expansion."""

from fractions import Fraction

from ..patterns import parse_pattern
from ..score import chord, midi, scale
from .model import DSLError, NoteSequence
from .units import quantity
from .validate import array, number


def fraction(value, at=""):
    number(value, at)
    return Fraction(str(value))


def leaf(expr, op, context, origin):
    at = origin["pointer"]
    if op == "pattern":
        events, span = parse_pattern(expr[op], steps_per_beat=expr.get("steps", 4), meter=context["meter"])
        events = [[pitch, fraction(start), fraction(hold), velocity] for pitch, start, hold, velocity in events]
        span = fraction(span)
    elif op == "chord":
        pitch = chord(expr[op], expr.get("octave", 4))
        start = quantity(expr.get("at", "0b"), context, beats=True, pointer=at + "/at")
        hold = quantity(expr.get("dur", "1b"), context, beats=True, pointer=at + "/dur")
        events = [[pitch, start, hold, expr.get("velocity", 0.8)]]
        span = start + hold
    else:
        events = []
        pitches = (
            scale(expr.get("root", "C"), expr.get("mode", "major"), expr.get("octave", 4)) if op == "degrees" else None
        )
        for item in array(expr[op], at):
            if not isinstance(item, list | tuple) or len(item) not in (3, 4):
                raise DSLError("E_NOTES", "note tuples need pitch, beat, held beats, and optional velocity", at)
            pitch, start, hold, *velocity = item
            if pitches is not None:
                number(pitch, at, integer=True)
                octave, degree = divmod(pitch, len(pitches))
                pitch = pitches[degree] + octave * 12
            events.append([pitch, fraction(start, at), fraction(hold, at), velocity[0] if velocity else 0.8])
        span = max((start + hold for _, start, hold, _ in events), default=Fraction(0))
    for pitch, start, hold, velocity in events:
        if isinstance(pitch, list | tuple) and not pitch:
            raise DSLError("E_NOTES", "a chord cannot be empty", at)
        for note in pitch if isinstance(pitch, list | tuple) else [pitch]:
            number(midi(note), at)
        if start < 0 or hold <= 0:
            raise DSLError("E_NOTES", "onset must be nonnegative and held duration positive", at)
        number(velocity, at, 0, 1)
    if "span" in expr:
        span = quantity(expr["span"], context, beats=True, pointer=at + "/span")
    if span < max((e[1] + e[2] for e in events), default=0):
        raise DSLError("E_SPAN", "held note extends beyond the declared phrase span", at)
    return NoteSequence(events, span, [origin.copy() for _ in events])


def combine(sequences, *, gap=Fraction(0), overlay=False):
    events, origins, offset = [], [], Fraction(0)
    for sequence in sequences:
        events += [
            [pitch, start + (0 if overlay else offset), hold, velocity]
            for pitch, start, hold, velocity in sequence.events
        ]
        origins += sequence.origins
        offset = max(offset, sequence.span) if overlay else offset + sequence.span + gap
    return NoteSequence(events, offset if overlay else max(Fraction(0), offset - gap), origins)
