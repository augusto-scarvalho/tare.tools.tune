"""Deterministic note transformations with explicit ordering and legacy-neutral seeds."""

from fractions import Fraction

from .. import rng
from ..score import midi
from .model import DSLError, NoteSequence
from .notes import fraction
from .units import quantity
from .validate import known, number, seed


def apply(sequence, transforms, context, at, warnings):
    result = NoteSequence([list(e) for e in sequence.events], sequence.span, list(sequence.origins))
    for transform in transforms:
        known(transform, {"transpose", "stretch", "velocity", "retrograde", "quantize", "humanize"}, at)
        if len(transform) != 1:
            raise DSLError("E_TRANSFORM", "each transform needs one operation", at)
        op, value = next(iter(transform.items()))
        if op in ("transpose", "stretch", "velocity"):
            number(value, at, 1e-12 if op == "stretch" else 0 if op == "velocity" else None)
        if op == "stretch":
            factor = fraction(value)
            result.events = [[p, a * factor, h * factor, v] for p, a, h, v in result.events]
            result.span *= factor
        elif op == "transpose":
            result.events = [
                [([midi(n) + value for n in p] if isinstance(p, list | tuple) else midi(p) + value), a, h, v]
                for p, a, h, v in result.events
            ]
        elif op == "velocity":
            result.events = [[p, a, h, number(v * value, at, 0, 1)] for p, a, h, v in result.events]
        elif op == "retrograde":
            if value is not True:
                raise DSLError("E_TRANSFORM", "retrograde must be true", at)
            result.events = [[p, result.span - a - h, h, v] for p, a, h, v in result.events]
            ordered = sorted(zip(result.events, result.origins, strict=True), key=lambda pair: pair[0][1])
            result.events, result.origins = [e for e, _ in ordered], [o for _, o in ordered]
        elif op == "quantize":
            grid = quantity(value, context, beats=True, pointer=at)
            if grid <= 0:
                raise DSLError("E_UNIT", "quantize needs a positive grid", at)
            result.events = [[p, int(a / grid + Fraction(1, 2)) * grid, h, v] for p, a, h, v in result.events]
        else:
            known(value, {"time", "velocity", "seed"}, at)
            key = seed(value.get("seed", 0), at)
            time = quantity(value.get("time", "0ms"), context, beats=True, pointer=at)
            depth = number(value.get("velocity", 0), at, 0, 1)
            output = []
            for i, (pitch, start, hold, vel) in enumerate(result.events):
                delta = Fraction(str(2 * rng.uniform(rng.key(key, "dsl-humanize-1", i, "time")) - 1)) * time
                new_start = max(Fraction(0), start + delta)
                new_vel = min(
                    1, max(0, vel + (2 * rng.uniform(rng.key(key, "dsl-humanize-1", i, "velocity")) - 1) * depth)
                )
                if start + delta < 0 or new_vel in (0, 1) and new_vel != vel:
                    warnings.append({"code": "W_HUMANIZE_CLAMP", "pointer": at, "event": i})
                output.append([pitch, new_start, hold, new_vel])
            result.events = output
            result.span = max(result.span, max((e[1] + e[2] for e in output), default=0))
        if any(start < 0 or start + hold > result.span for _, start, hold, _ in result.events):
            raise DSLError("E_SPAN", "transform moves a held note outside its phrase span", at)
    return result
