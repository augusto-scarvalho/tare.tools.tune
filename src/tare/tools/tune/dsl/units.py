"""Exact scheduling quantities; primitive fields keep their original physical units."""

import re
from fractions import Fraction

from .model import DSLError

TIME = re.compile(r"(\d+/\d+|\d+(?:\.\d*)?|\.\d+)(ms|bar|s|b)")


def quantity(value, context, *, beats=False, pointer=""):
    if not isinstance(value, str) or not (match := TIME.fullmatch(value)):
        raise DSLError("E_UNIT", "use a quantity such as '20ms', '0.5s', '1/3b', or '2bar'", pointer)
    try:
        number = Fraction(match[1])
    except (ValueError, ZeroDivisionError):
        raise DSLError("E_UNIT", "quantity must be a finite nonnegative rational", pointer) from None
    unit = match[2]
    tempo = Fraction(str(context["bpm"]))
    seconds = (
        number
        * {"ms": Fraction(1, 1000), "s": Fraction(1), "b": 60 / tempo, "bar": context["meter"] * 60 / tempo}[unit]
    )
    return seconds * tempo / 60 if beats else seconds
