import numpy as np
import pytest

from tare.tools.tune import Genome, rng


def test_splitmix64_known_answers():
    # Reference SplitMix64 stream seeded with 0: engine ports check themselves against these.
    expected = [0xE220A8397B1DCDAF, 0x6E789E6AA1B965F4, 0x06C45D188009454F]
    assert [rng.fmix((i * rng.GOLDEN) & rng.MASK) for i in (1, 2, 3)] == expected


def test_vector_stream_equals_scalar():
    k = rng.key(42, "noise")
    scalar = [rng.uniform(rng.fmix((k + i * rng.GOLDEN) & rng.MASK)) for i in range(1, 1001)]
    assert np.array_equal(rng.uniforms(k, 1000), np.array(scalar))


def test_key_known_answers():
    # Published FNV-1a 64 vectors, then a pinned key: a hashing change would re-voice every species.
    assert [rng.fnv1a(s) for s in ("", "a", "foobar")] == [0xCBF29CE484222325, 0xAF63DC4C8601EC8C,
                                                          0x85944171F73967E8]
    assert rng.key(7, "f0") == 0xC3353269BDEA1AF4 == rng.key(7, rng.fnv1a("f0"))
    assert rng.seed32("wolf") == rng.key("wolf") & 0xFFFFFFFF


def test_noise_is_white_and_bounded():
    x = rng.noise(1, 200_000)
    assert x.min() >= -1 and x.max() < 1
    assert abs(x.mean()) < 0.01 and abs(np.corrcoef(x[:-1], x[1:])[0, 1]) < 0.01


def test_genes_are_stable_and_order_independent():
    a, b = Genome(7), Genome(7)
    first = [a.u(g) for g in ("f0", "dur", "vowel")]
    assert [b.u(g) for g in ("vowel", "dur", "f0")][::-1] == first
    assert Genome(8).u("f0") != a.u("f0")


def test_individuals_vary_a_little_structure_never():
    values = [Genome(7, individual=i, variation=0.15).u("f0") for i in range(50)]
    assert np.ptp(values) > 0.05
    assert max(abs(v - Genome(7).u("f0")) for v in values) <= 0.15 + 1e-12
    assert len({Genome(7, individual=i, variation=0.5).choice("vowel", "aeiou") for i in range(50)}) == 1


def test_takes_vary_less_than_individuals():
    g = [Genome(7, 0, 0.15, take=t, take_variation=0.05).u("f0") for t in range(30)]
    assert 0 < np.ptp(g) <= 0.1 + 1e-12


def test_overrides_and_helpers():
    g = Genome(1, overrides={"f0": 0.25, "kind": 0.99})
    assert g.u("f0") == 0.25
    assert g.range("f0", 10, 20) == pytest.approx(12.5)
    assert g.lrange("f0", 100, 1600) == pytest.approx(200)
    assert g.choice("kind", ["a", "b", "c"]) == "c"
    assert 3 <= Genome(1).int("n", 3, 5) <= 5
