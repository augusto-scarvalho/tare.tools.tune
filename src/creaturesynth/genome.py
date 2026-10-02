"""Species genes: stable per species, nudged per individual and per take.

Genes are looked up by name, so adding a gene to an archetype never reshuffles the
others: a species keeps its voice as the archetypes evolve.
"""
from collections.abc import Mapping, Sequence
from typing import TypeVar

from .rng import fnv1a, key, tri, uniform

T = TypeVar("T")


class Genome:
    def __init__(self, species: int, individual: int = 0, variation: float = 0.0,
                 take: int = 0, take_variation: float = 0.0, overrides: Mapping[str, float] | None = None):
        self.species = species
        self.individual = individual
        self.variation = variation
        self.take = take
        self.take_variation = take_variation
        self.overrides = dict(overrides or {})

    def base(self, gene: str) -> float:
        """The species' value, before individual/take variation."""
        return uniform(key(self.species, fnv1a(gene)))

    def u(self, gene: str) -> float:
        """Gene value in [0, 1]."""
        if gene in self.overrides:
            return min(max(float(self.overrides[gene]), 0.0), 1.0)
        g = fnv1a(gene)
        v = self.base(gene)
        if self.variation:
            v += self.variation * tri(key(self.species, g, self.individual, 1))
        if self.take_variation:
            v += self.take_variation * tri(key(self.species, g, self.individual, self.take, 2))
        return min(max(v, 0.0), 1.0)

    def range(self, gene: str, lo: float, hi: float) -> float:
        return lo + (hi - lo) * self.u(gene)

    def lrange(self, gene: str, lo: float, hi: float) -> float:
        """Geometric interpolation, for frequencies and other ratio-like values."""
        return lo * (hi / lo) ** self.u(gene)

    def chance(self, gene: str, p: float) -> bool:
        return self.u(gene) < p

    def choice(self, gene: str, options: Sequence[T]) -> T:
        """Structural choice: fixed for the species (never varies per individual)."""
        if gene in self.overrides:
            v = min(max(float(self.overrides[gene]), 0.0), 1.0)
        else:
            v = self.base(gene)
        return options[min(int(v * len(options)), len(options) - 1)]

    def int(self, gene: str, lo: int, hi: int) -> int:
        return self.choice(gene, list(range(lo, hi + 1)))
