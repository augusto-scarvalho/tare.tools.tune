"""Portable, deterministic randomness.

Everything random in tare.tools.tune (genes, noise, jitter, reverb) comes from SplitMix64,
so an engine-side port (C#, GDScript, C++, JS) can reproduce it exactly. The rules:

- ``key(*parts)`` folds ints/strings into one 64-bit key. Strings are hashed with FNV-1a 64.
- ``uniform(k)`` maps a key to [0, 1) using its top 53 bits.
- ``uniforms(k, n)`` is the SplitMix64 stream seeded with ``k``: element i is
  ``fmix(k + (i + 1) * GOLDEN)``, which is counter-based and therefore vectorisable.
"""
import numpy as np

MASK = (1 << 64) - 1
GOLDEN = 0x9E3779B97F4A7C15
_C1, _C2 = 0xBF58476D1CE4E5B9, 0x94D049BB133111EB
_FNV_OFFSET, _FNV_PRIME = 0xCBF29CE484222325, 0x100000001B3


def fmix(z: int) -> int:
    """SplitMix64 output function."""
    z = ((z ^ (z >> 30)) * _C1) & MASK
    z = ((z ^ (z >> 27)) * _C2) & MASK
    return z ^ (z >> 31)


def fnv1a(text: str) -> int:
    h = _FNV_OFFSET
    for byte in text.encode("utf-8"):
        h = ((h ^ byte) * _FNV_PRIME) & MASK
    return h


def key(*parts: int | str) -> int:
    h = 0
    for part in parts:
        p = fnv1a(part) if isinstance(part, str) else int(part) & MASK
        h = fmix(((h ^ p) + GOLDEN) & MASK)
    return h


def uniform(k: int) -> float:
    return (k >> 11) * 2.0 ** -53


def tri(k: int) -> float:
    """Triangular deviate in (-1, 1), peaked at 0 (cheap stand-in for a Gaussian)."""
    return uniform(key(k, 1)) - uniform(key(k, 2))


def uniforms(k: int, n: int) -> np.ndarray:
    states = np.uint64(k & MASK) + np.arange(1, n + 1, dtype=np.uint64) * np.uint64(GOLDEN)
    z = (states ^ (states >> np.uint64(30))) * np.uint64(_C1)
    z = (z ^ (z >> np.uint64(27))) * np.uint64(_C2)
    z ^= z >> np.uint64(31)
    return (z >> np.uint64(11)).astype(np.float64) * 2.0 ** -53


def noise(k: int, n: int) -> np.ndarray:
    """White noise in [-1, 1)."""
    return uniforms(k, n) * 2.0 - 1.0


def seed32(*parts: int | str) -> int:
    """A seed that fits every target language's integers (JS numbers included)."""
    return key(*parts) & 0xFFFFFFFF
