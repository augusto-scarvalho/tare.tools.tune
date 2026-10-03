"""Procedural sound effects: weapons, impacts, footsteps, magic, status effects, explosions, ambience.

    >>> from tare.tools.tune.sfx import Sfx
    >>> sword = Sfx("blade", "steel", species=7, size=0.5)
    >>> audio = sword.render("clash", take=2)          # every take is a little different
    >>> fireball = Sfx("spell", "fire", power=0.8)
    >>> fireball.events                                # ('charge', 'cast', 'travel', 'impact')

An Sfx is to sound effects what a Creature is to voices: a recipe (``kind``) with a
``style`` (material, element, place), a ``species`` seed that is the object's identity
(this sword, not swords in general), ``size`` and ``power``, and events that play like
calls. Recipes design a plain Voice spec, so baking, the runtime bank and engine ports
work the same way.

``era`` dresses any of them as a generation of games sounded (see ERAS): "hd" as today's
HD-2D tactics, "16bit" as the sampled sound of the PSP and DS ones, "" as designed.
``knobs`` vary one within its character (sfx/knobs.py): register, tempo, length, ring,
brightness, sparkle, and the game's key for the interface and status sounds.

    >>> Sfx("ui", "crystal", knobs={"register": -1, "tempo": 1.5}).voice("confirm")
"""
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace

import numpy as np

from .. import rng
from ..genome import Genome
from ..render import DEFAULT_SR, render
from ..spec import Modal, Noise, Scatter, Syllable, Voice
from .knobs import KEY, KNOBS, Knob
from .knobs import apply as apply_knobs


@dataclass(frozen=True)
class Recipe:
    design: Callable[["Fx"], Voice]
    events: tuple[str, ...]
    styles: tuple[str, ...]
    description: str
    loops: tuple[str, ...] = ()     # events rendered as seamless loops
    knobs: dict = field(default_factory=dict)   # name -> Knob: the general ones and the recipe's own


RECIPES: dict[str, Recipe] = {}


def recipe(name: str, events: tuple[str, ...], styles: tuple[str, ...], loops: tuple[str, ...] = (),
           knobs: dict | None = None):
    def register(fn):
        RECIPES[name] = Recipe(fn, events, styles, (fn.__doc__ or "").strip().splitlines()[0], loops,
                               {**KNOBS, **(knobs or {})})
        return fn
    return register


# --- materials: what a struck body rings like ----------------------------------------------------------------------

@dataclass(frozen=True)
class Material:
    low: tuple[float, float]        # lowest mode, Hz, for size 0 .. size 1
    high: float                     # highest mode, Hz
    count: int                      # modes
    t60: tuple[float, float]        # decay of the lowest mode, seconds, size 0 .. 1
    damping: float                  # higher modes die faster: t60 * (f / low) ** -damping
    hardness: float                 # contact brightness, Hz
    spread: str = "dense"           # dense (metal plates/blades) | sparse (wood, stone, glass) | bell | string
    click: float = 0.3
    radiates: float = 300.0         # modes below this radiate weakly (a blade's low bending modes barely sound)


MATERIALS: dict[str, Material] = {
    "steel": Material((1100, 250), 12_000, 36, (0.5, 1.6), 0.55, 14_000, radiates=2500),
    "iron": Material((600, 140), 7_000, 24, (0.18, 0.5), 0.7, 9_000, radiates=700),
    "bronze": Material((450, 110), 6_000, 18, (0.8, 2.5), 0.45, 8_000, radiates=300),
    "glass": Material((2200, 600), 14_000, 9, (0.3, 1.0), 0.5, 16_000, "sparse", radiates=1000),
    "wood": Material((520, 110), 3_200, 7, (0.05, 0.16), 0.5, 4_000, "sparse", 0.5, radiates=100),
    "stone": Material((1600, 500), 9_000, 14, (0.01, 0.03), 0.3, 9_000, "sparse", 1.0, radiates=400),
    "bell": Material((900, 220), 9_000, 9, (1.0, 3.5), 0.4, 6_000, "bell", 0.05, radiates=100),
    "string": Material((260, 70), 4_000, 14, (0.08, 0.25), 0.6, 6_000, "string", 0.0, radiates=50),
}
BELL_RATIOS = (0.5, 1.0, 1.19, 1.5, 2.0, 2.52, 3.0, 4.2, 5.4)   # minor-third bell (hum, prime, tierce...)


class Fx:
    """Design context: genome (object identity + per-take variation), traits, style, event."""

    def __init__(self, sfx: "Sfx", event: str, take: int):
        self.sfx, self.event, self.take = sfx, event, take
        self.style = sfx.style
        self.g = Genome(sfx.species, 0, 0.0, take, sfx.take_variation, dict(sfx.genes))
        self.size, self.power = sfx.size, sfx.power

    def knob(self, name: str) -> float | None:
        """A knob's value: the Sfx's own, else the recipe's default (None: the recipe decides)."""
        return dict(self.sfx.knobs).get(name, RECIPES[self.sfx.kind].knobs[name].default)

    def rand(self, name: str) -> float:
        """Fresh randomness for every take (strike position, timing), independent of the species."""
        return rng.uniform(rng.key(self.sfx.species, self.take, self.event, name))

    def modes(self, material: str, size: float | None = None, prefix: str = "") -> list[tuple[float, float, float]]:
        """A body's modes: fixed by the species (its shape), gains re-weighted per take (where it was struck)."""
        m = MATERIALS[material]
        size = self.size if size is None else size
        g = self.g
        low = m.low[0] * (m.low[1] / m.low[0]) ** size * (0.85 + 0.3 * g.base(prefix + material + "low"))
        t60 = m.t60[0] + (m.t60[1] - m.t60[0]) * size
        out = []
        for i in range(m.count):
            if m.spread == "dense":
                f = low * (m.high / low) ** ((i + 0.6 * g.base(f"{prefix}{material}{i}")) / m.count)
            elif m.spread == "sparse":
                f = low * (1 + i * (1.3 + 1.4 * g.base(f"{prefix}{material}{i}"))) ** 1.15
            elif m.spread == "bell":
                f = low * BELL_RATIOS[i % len(BELL_RATIOS)] * (1 + 0.004 * (g.base(f"{prefix}{material}{i}") - 0.5))
            else:  # string: harmonics, slightly stiff
                f = low * (i + 1) * (1 + 0.0004 * (i + 1) ** 2)
            if f > m.high * 1.2:
                break
            strike = 0.25 + 0.75 * self.rand(f"{prefix}strike{i}")       # where the blow landed
            gain = strike / (1 + i) ** (0.5 if m.spread in ("dense", "bell") else 0.8) / (1 + (m.radiates / f) ** 2)
            if m.spread == "string":
                gain = abs(np.sin(np.pi * (i + 1) * (0.12 + 0.1 * self.rand("pluck")))) / (i + 1)
            out.append((round(f, 1), round(t60 * (f / low) ** -m.damping, 4), round(gain, 4)))
        return out

    def strike(self, material: str, start: float = 0.0, size: float | None = None, hits=None, hardness=None,
               scrape=(0.0, 0.0, 0.0, 0.0), gain: float = 1.0, prefix: str = "", dur: float | None = None,
               ring: float = 1.0, click: float | None = None) -> Modal:
        """`ring` scales every decay (< 1: held, lying on the floor, muffled)."""
        m = MATERIALS[material]
        modes = [(f, round(t * ring, 4), g) for f, t, g in self.modes(material, size, prefix)]
        dur = dur or min(max(t for _, t, _ in modes) * 1.2 + 0.05, 4.0)
        return Modal(start, round(dur, 3), modes, hits or [(0.0, 1.0, 0.0012 if m.hardness > 8000 else 0.003)],
                     scrape, hardness or m.hardness, m.click if click is None else click, gain)

    def level(self, x: float = 1.0) -> float:
        """Peak level: `x` at full power, ~12 dB lower when gentle (`x` sets the mix between a recipe's events)."""
        return min(1.0, x * 10 ** (-12 * (1 - self.power) / 20))

    def voice(self, gain: float | None = None, **layers) -> Voice:
        return Voice(gain=round(self.level() if gain is None else gain, 4), **layers)


def hd(v: Voice) -> Voice:
    """Today's HD-2D tactics (measured on Triangle Strategy): the whole band (to 16-22 kHz), and sounds that keep
    sounding: interface sounds of 0.15-2.7 s, swelling in over 50-150 ms, carried by a room and a tail."""
    v.room = max(v.room, 0.25)
    if not v.space:
        v.space, v.wet = 1.2, 0.18
    return v


def sixteen(v: Voice) -> Voice:
    """The sampled sound of the PSP and DS tactics (measured on Tactics Ogre and FFTA2): samples at 16-33 kHz with
    nothing much above 5-8 kHz, stored as 4-bit ADPCM (a grain that follows the level), and dry."""
    v.lowpass = min(v.lowpass or 5000.0, 5000.0)       # a gentle 12 dB/octave: 5 kHz leaves 99 % of it under ~8
    v.bits = 4
    v.space = v.room = v.air = 0.0
    return v


ERAS = {"": lambda v: v, "hd": hd, "16bit": sixteen}


@dataclass(frozen=True)
class Sfx:
    kind: str
    style: str = ""
    species: int = 0
    size: float = 0.5
    power: float = 0.5
    take_variation: float = 0.12
    genes: tuple[tuple[str, float], ...] = field(default=())
    name: str = ""
    era: str = ""                   # "", "hd" or "16bit" (ERAS)
    knobs: tuple[tuple[str, float], ...] = field(default=())    # name -> value (see knob_info)

    def __post_init__(self):
        if self.kind not in RECIPES:
            raise ValueError(f"unknown sound kind {self.kind!r}; choose from {', '.join(RECIPES)}")
        r = RECIPES[self.kind]
        if not self.style:
            object.__setattr__(self, "style", r.styles[0])
        elif self.style not in r.styles:
            raise ValueError(f"{self.kind} has no style {self.style!r}; choose from {', '.join(r.styles)}")
        if self.era not in ERAS:
            raise ValueError(f"unknown era {self.era!r}; choose from {', '.join(repr(e) for e in ERAS)}")
        knobs = dict(self.knobs.items() if isinstance(self.knobs, dict) else self.knobs)
        for name, value in knobs.items():
            k = r.knobs.get(name)
            if k is None:
                raise ValueError(f"{self.kind} has no knob {name!r}; choose from {', '.join(r.knobs)}")
            if not k.lo <= float(value) <= k.hi:
                raise ValueError(f"knob {name!r} goes from {k.lo:g} to {k.hi:g} ({k.unit}), not {value}")
        object.__setattr__(self, "knobs", tuple(sorted((n, float(v)) for n, v in knobs.items())))
        genes = self.genes.items() if isinstance(self.genes, dict) else self.genes
        object.__setattr__(self, "genes", tuple(sorted(tuple(kv) for kv in genes)))

    @property
    def events(self) -> tuple[str, ...]:
        return RECIPES[self.kind].events

    calls = events  # the runtime bank warms "calls" for creatures and sounds alike

    def voice(self, event: str | None = None, take: int = 0) -> Voice:
        r = RECIPES[self.kind]
        event = event or r.events[0]
        if event not in r.events:
            raise ValueError(f"{self.kind} has no event {event!r}; choose from {', '.join(r.events)}")
        v = ERAS[self.era](apply_knobs(r.design(Fx(self, event, take)), dict(self.knobs)))
        v.seed = rng.seed32(self.kind, self.style, self.species, take, event)
        v.meta.update({"kind": self.kind, "style": self.style, "event": event, "species": self.species,
                       "take": take, "size": self.size, "power": self.power})
        if self.name:
            v.meta["name"] = self.name
        if self.era:
            v.meta["era"] = self.era
        if self.knobs:
            v.meta["knobs"] = dict(self.knobs)
        return v

    def knob_info(self) -> dict[str, Knob]:
        """This sound's knobs: default, range, unit and what each does."""
        return dict(RECIPES[self.kind].knobs)

    def render(self, event: str | None = None, take: int = 0, sr: int = DEFAULT_SR) -> np.ndarray:
        return render(self.voice(event, take), sr)

    def but(self, **changes) -> "Sfx":
        return replace(self, **changes)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["genes"] = dict(self.genes)
        d["knobs"] = dict(self.knobs)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Sfx":
        return cls(**d)

    @classmethod
    def random(cls, seed: int, kind: str | None = None) -> "Sfx":
        kinds = list(RECIPES)
        kind = kind or kinds[int(rng.uniform(rng.key(seed, "kind")) * len(kinds))]
        styles = RECIPES[kind].styles
        return cls(kind, styles[int(rng.uniform(rng.key(seed, "style")) * len(styles))], rng.seed32(seed, "species"),
                   round(rng.uniform(rng.key(seed, "size")), 3), round(rng.uniform(rng.key(seed, "power")), 3))


def bell_curve(peak: float = 0.5, sharp: float = 2.0, points: int = 9):
    """Amp curve rising to 1 at `peak` (0..1) and back to 0: whooshes, swells."""
    out = []
    for t in np.linspace(0, 1, points):
        x = t / peak if t <= peak else (1 - t) / (1 - peak)
        out.append((round(float(t), 3), round(float(np.sin(0.5 * np.pi * x)) ** sharp, 4)))
    return out


def decay_curve(rate: float = 5.0, points: int = 9):
    """Amp curve falling exponentially: rate 5 ends at -43 dB."""
    return [(round(float(t), 3), round(float(np.exp(-rate * t)), 5)) for t in np.linspace(0, 1, points)]


from . import ambience, arms, home, magic, physical, status, ui, world  # noqa: E402,F401  (registers the recipes)

__all__ = ["ERAS", "KEY", "KNOBS", "MATERIALS", "RECIPES", "Fx", "Knob", "Material", "Modal", "Noise", "Recipe",
           "Scatter", "Sfx", "Syllable", "bell_curve", "decay_curve", "recipe"]
