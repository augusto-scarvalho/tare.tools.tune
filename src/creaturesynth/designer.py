"""Design creatures from a text prompt (CLAP) or from a reference recording (CLAP + analysis).

The search runs over archetype, genes and traits; the result is an ordinary Creature with
pinned genes, so it keeps every procedural property (calls, individuals, evolution).
"""
from collections.abc import Sequence

import numpy as np

from . import rng
from .analysis import distance, features
from .archetypes import ARCHETYPES, Ctx
from .calls import CALLS, Traits
from .creature import Creature
from .genome import Genome
from .render import DEFAULT_SR


def gene_names(archetype: str) -> list[str]:
    """Every gene an archetype reads (probed over species, traits and calls, since branches differ)."""
    seen: list[str] = []

    class Spy(Genome):
        def u(self, gene):
            if gene not in seen:
                seen.append(gene)
            return super().u(gene)

        def choice(self, gene, options):
            if gene not in seen:
                seen.append(gene)
            return super().choice(gene, options)

    for species in range(12):
        for size, aggression in ((0.1, 0.1), (0.5, 0.5), (0.9, 0.95)):
            for call in CALLS.values():
                ARCHETYPES[archetype](Ctx(Spy(species), Traits(size, aggression), call))
    return seen


def _creature(archetype: str, genes: list[str], v: np.ndarray, species: int) -> Creature:
    return Creature(archetype, species=species, size=round(float(v[-2]), 3), aggression=round(float(v[-1]), 3),
                    genes={g: round(float(x), 4) for g, x in zip(genes, v[:-2], strict=True)})


def _evolve(objective, x0: np.ndarray, iters: int, rng_: np.random.Generator, step: float = 0.25):
    """(1+1)-ES with the 1/5th success rule, inside the unit cube; maximises."""
    best, best_f = x0, objective(x0)
    for _ in range(iters):
        cand = np.clip(best + rng_.normal(0, step, len(best)), 0, 1)
        f = objective(cand)
        if f > best_f:
            best, best_f, step = cand, f, min(step * 1.5, 0.5)
        else:
            step = max(step * 0.9, 0.02)
    return best, best_f


def _search(score, archetypes: Sequence[str] | None, iters: int, screen: int, seed: int, species: int, call: str,
            sr: int) -> tuple[Creature, float]:
    archetypes = list(archetypes or ARCHETYPES)
    r = np.random.default_rng(seed)
    genes = {a: gene_names(a) for a in archetypes}

    def objective_for(a):
        return lambda v: score(_creature(a, genes[a], v, species).render(call, sr=sr))

    starts = []
    for a in archetypes:                       # screening: a few random members of each archetype
        obj = objective_for(a)
        for _ in range(screen):
            v = r.uniform(0, 1, len(genes[a]) + 2)
            starts.append((obj(v), a, v))
    starts.sort(key=lambda s: -s[0])
    best = None
    for _, a, v in starts[:2]:                 # refine the two most promising
        x, f = _evolve(objective_for(a), v, iters, r)
        if best is None or f > best[0]:
            best = (f, a, x)
    f, a, x = best
    return _creature(a, genes[a], x, species), float(f)


def design(prompt: str, archetypes: Sequence[str] | None = None, call: str = "idle", iters: int = 60,
           screen: int = 6, seed: int = 0, clap=None, sr: int = DEFAULT_SR) -> tuple[Creature, float]:
    """The creature CLAP finds closest to `prompt` (cosine similarity, higher is better)."""
    if clap is None:
        from .clap import load
        clap = load()
    text = clap.text([prompt])[0]

    def score(audio):
        return float(clap.audio([audio], sr)[0] @ text)

    return _search(score, archetypes, iters, screen, seed, rng.seed32("prompt", prompt), call, sr)


def match(sample: np.ndarray, sample_sr: int, archetypes: Sequence[str] | None = None, call: str = "idle",
          iters: int = 80, screen: int = 6, seed: int = 0, clap=None, sr: int = DEFAULT_SR,
          feature_weight: float = 0.02) -> tuple[Creature, float]:
    """The creature closest to a recording: CLAP audio similarity minus a feature mismatch."""
    if clap is None:
        from .clap import load
        clap = load()
    fmax = min(8000, sample_sr / 2 - 100)
    target = features(sample, sample_sr, fmax=fmax)
    emb = clap.audio([sample], sample_sr)[0]

    def score(audio):
        return float(clap.audio([audio], sr)[0] @ emb) - feature_weight * distance(features(audio, sr, fmax), target)

    return _search(score, archetypes, iters, screen, seed, rng.seed32("sample", len(sample), sample_sr), call, sr)
