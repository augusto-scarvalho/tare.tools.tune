"""The main entry point: a creature is an archetype + species + traits."""
from dataclasses import asdict, dataclass, field, replace

import numpy as np

from . import rng
from .archetypes import ARCHETYPES, design
from .calls import Call, Traits, get_call
from .genome import Genome
from .render import DEFAULT_SR, render
from .spec import Voice


@dataclass(frozen=True)
class Creature:
    """Everything needed to (re)generate a creature's voice, deterministically.

    - ``species``: seed for the genes every member shares (contour, vowel, rhythm...).
    - ``individual``: which member of the species; ``variation`` says how different members are.
    - ``take``: (per call) which rendition; ``take_variation`` keeps repeated calls from sounding identical.
    - ``genes``: pin gene values (0..1) by name to art-direct a species.
    """

    archetype: str
    species: int = 0
    size: float = 0.5
    aggression: float = 0.3
    individual: int = 0
    variation: float = 0.15
    take_variation: float = 0.06
    genes: tuple[tuple[str, float], ...] = field(default=())
    name: str = ""

    def __post_init__(self):
        if self.archetype not in ARCHETYPES:
            raise ValueError(f"unknown archetype {self.archetype!r}; choose from {', '.join(ARCHETYPES)}")
        if isinstance(self.genes, dict):
            object.__setattr__(self, "genes", tuple(sorted(self.genes.items())))
        else:
            object.__setattr__(self, "genes", tuple(tuple(kv) for kv in self.genes))

    def genome(self, take: int = 0) -> Genome:
        return Genome(self.species, self.individual, self.variation, take, self.take_variation, dict(self.genes))

    def voice(self, call: str | Call = "idle", take: int = 0) -> Voice:
        c = get_call(call)
        v = design(self.archetype, self.genome(take), Traits(self.size, self.aggression), c)
        v.seed = rng.seed32(self.archetype, self.species, self.individual, take, c.name)
        v.meta.update({"species": self.species, "individual": self.individual, "take": take,
                       "size": self.size, "aggression": self.aggression})
        if self.name:
            v.meta["name"] = self.name
        return v

    def render(self, call: str | Call = "idle", take: int = 0, sr: int = DEFAULT_SR) -> np.ndarray:
        return render(self.voice(call, take), sr)

    def evolve(self, size: float = 0.3, aggression: float = 0.2, name: str = "") -> "Creature":
        """Same species, bigger and fiercer: the next evolution stage."""
        return replace(self, size=min(max(self.size + size, 0.0), 1.0),
                       aggression=min(max(self.aggression + aggression, 0.0), 1.0), name=name)

    def member(self, individual: int) -> "Creature":
        """Another individual of the same species."""
        return replace(self, individual=individual)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["genes"] = dict(self.genes)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Creature":
        return cls(**d)

    @classmethod
    def random(cls, seed: int, archetype: str | None = None) -> "Creature":
        """A brand-new creature: archetype, species and traits all drawn from `seed`."""
        names = sorted(ARCHETYPES)
        arch = archetype or names[int(rng.uniform(rng.key(seed, "archetype")) * len(names))]
        return cls(arch, species=rng.seed32(seed, "species"),
                   size=round(rng.uniform(rng.key(seed, "size")), 3),
                   aggression=round(rng.uniform(rng.key(seed, "aggression")), 3))
