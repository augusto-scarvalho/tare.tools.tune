"""Archetypes turn (genes, traits, call) into a Voice.

Each archetype is a function ``design(ctx) -> Voice`` registered with ``@archetype``.
``Ctx`` bundles the species genome, the creature's traits and the call, and offers the
helpers every archetype needs so calls behave consistently across all of them.
"""
from collections.abc import Callable

from ..calls import Call, Traits
from ..genome import Genome
from ..spec import Curve, Syllable, Voice

ARCHETYPES: dict[str, Callable[["Ctx"], Voice]] = {}
DESCRIPTIONS: dict[str, str] = {}

VOWELS = {  # first four formants (Hz) of a human-sized vocal tract
    "a": (730, 1090, 2440, 3400), "o": (570, 840, 2410, 3300), "u": (300, 870, 2240, 3200),
    "e": (530, 1840, 2480, 3500), "ae": (660, 1720, 2410, 3400), "i": (270, 2290, 3010, 3700),
}


def archetype(name: str):
    def register(fn: Callable[["Ctx"], Voice]):
        ARCHETYPES[name] = fn
        DESCRIPTIONS[name] = (fn.__doc__ or "").strip().splitlines()[0]
        return fn
    return register


def geo(a: float, b: float, x: float) -> float:
    """Geometric interpolation a -> b as x goes 0 -> 1."""
    return a * (b / a) ** x


def clip01(x: float) -> float:
    return min(max(x, 0.0), 1.0)


class Ctx:
    def __init__(self, genome: Genome, traits: Traits, call: Call):
        self.g = genome
        self.call = call
        self.size = clip01(traits.size)
        self.aggr = clip01(traits.aggression + call.aggression)
        self.intensity = call.intensity

    def dur(self, seconds: float) -> float:
        return seconds * self.call.duration

    def contour(self, points: Curve) -> Curve:
        """Apply the call's transposition and end-of-syllable bend to a pitch curve."""
        return [(t, f * 2 ** ((self.call.pitch + self.call.bend * t) / 12)) for t, f in points]

    def repeats(self, default: int) -> int:
        return self.call.repeats or default

    def attack(self, seconds: float) -> float:
        return seconds * self.call.attack

    def formants(self, vowel: str, tract: float, widths=(90, 110, 160, 250),
                 gains=(1.0, 0.7, 0.35, 0.2)) -> list[tuple[float, float, float]]:
        """A vowel's formants for a vocal tract `tract` times smaller than a human's."""
        return [(f * tract, w * tract, a) for f, w, a in zip(VOWELS[vowel], widths, gains, strict=True)]

    def voice(self, syllables: list[Syllable], **kw) -> Voice:
        kw.setdefault("gain", 10 ** (-14 * (1 - self.intensity) / 20))  # idle ~ -9 dB vs attack
        return Voice(syllables=syllables, **kw)


def design(name: str, genome: Genome, traits: Traits, call: Call) -> Voice:
    try:
        fn = ARCHETYPES[name]
    except KeyError:
        raise ValueError(f"unknown archetype {name!r}; choose from {', '.join(ARCHETYPES)}") from None
    voice = fn(Ctx(genome, traits, call))
    voice.meta.update({"archetype": name, "call": call.name})
    return voice


from . import fantasy, natural, retro  # noqa: E402,F401  (registers the archetypes)

_ORDER = ["mammal", "bird", "insect", "reptile", "amphibian", "monster", "slime", "spirit", "robot", "chip"]
for _name in sorted(ARCHETYPES, key=lambda n: _ORDER.index(n) if n in _ORDER else len(_ORDER)):
    ARCHETYPES[_name] = ARCHETYPES.pop(_name)  # list natural ones first, in a stable order
