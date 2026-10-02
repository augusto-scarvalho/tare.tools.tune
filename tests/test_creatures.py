import numpy as np
import pytest

from tare.tools.tune import ARCHETYPES, CALLS, Creature, Voice, render

SR = 22_050  # faster tests; the synthesis is sample-rate independent


@pytest.mark.parametrize("archetype", list(ARCHETYPES))
def test_every_archetype_and_call_renders_sane_audio(archetype):
    for species in (1, 2, 3):
        for size, aggression in ((0.05, 0.0), (0.5, 0.4), (0.97, 1.0)):
            c = Creature(archetype, species=species, size=size, aggression=aggression)
            for call in CALLS:
                audio = c.render(call, sr=SR)
                assert audio.dtype == np.float32
                assert np.isfinite(audio).all(), (archetype, species, size, call)
                assert 0.05 < len(audio) / SR < 9, (archetype, species, size, call)
                assert 0.2 < np.abs(audio).max() <= 0.9


@pytest.mark.parametrize("archetype", list(ARCHETYPES))
def test_spec_round_trip_renders_identically(archetype):
    voice = Creature(archetype, species=5, size=0.6, aggression=0.7).voice("attack")
    again = Voice.from_json(voice.to_json())
    assert again == voice
    assert np.array_equal(render(again, SR), render(voice, SR))


def test_deterministic():
    c = Creature("monster", species=11, size=0.8, aggression=0.6)
    assert np.array_equal(c.render("hurt", sr=SR), Creature("monster", 11, 0.8, 0.6).render("hurt", sr=SR))


def test_takes_and_individuals_differ():
    c = Creature("mammal", species=4)
    a, b = c.render("idle", take=0, sr=SR), c.render("idle", take=1, sr=SR)
    assert not np.array_equal(a, b)
    assert c.voice("idle") != c.member(3).voice("idle")


def test_calls_shape_the_sound():
    c = Creature("mammal", species=9, size=0.5, aggression=0.3)
    v = {call: c.voice(call) for call in CALLS}
    assert v["idle"].gain < v["attack"].gain
    assert v["hurt"].duration < v["idle"].duration < v["death"].duration
    assert len(v["alert"].syllables) == 2
    death = v["death"].syllables[0].pitch
    assert death[-1][1] < death[0][1]  # dying calls fall in pitch


def test_evolution_is_bigger_and_lower():
    cub = Creature("mammal", species=7, size=0.15, aggression=0.1)
    adult = cub.evolve(size=0.7, aggression=0.6)
    assert adult.species == cub.species and adult.size == pytest.approx(0.85)
    f_cub = cub.voice("idle").syllables[0].pitch[0][1]
    f_adult = adult.voice("idle").syllables[0].pitch[0][1]
    assert f_adult < f_cub / 4
    assert adult.voice("idle").space > cub.voice("idle").space


def test_random_creatures_cover_archetypes():
    zoo = [Creature.random(s) for s in range(200)]
    assert {c.archetype for c in zoo} == set(ARCHETYPES)
    assert Creature.random(5) == Creature.random(5)
    assert Creature.random(5, "robot").archetype == "robot"


def test_genes_can_be_pinned():
    brute = Creature("monster", species=1, genes={"kind": 0.0})
    screecher = Creature("monster", species=1, genes={"kind": 0.5})
    assert brute.voice().syllables[0].pitch[0][1] < screecher.voice().syllables[0].pitch[0][1]
    assert brute == Creature.from_dict(brute.to_dict())


def test_errors():
    with pytest.raises(ValueError):
        Creature("dragon")
    with pytest.raises(ValueError):
        Creature("mammal").voice("sing")
    with pytest.raises(ValueError):
        render(Voice(), SR)
    with pytest.raises(ValueError):
        Voice.from_dict({"format": "something-else"})
