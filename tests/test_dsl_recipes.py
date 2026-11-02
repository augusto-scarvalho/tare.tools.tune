import numpy as np
import pytest
from test_dsl_loading import project

from tare.tools.tune import Creature, Sfx, capture
from tare.tools.tune.dsl import compile_document, load
from tare.tools.tune.dsl.composition import capture_plan
from tare.tools.tune.music import Cue
from tare.tools.tune.speech import Speaker


@pytest.mark.parametrize(
    "expression,source",
    [
        (
            {"sfx": "blade", "style": "steel", "event": "clash", "species": "excalibur", "power": 0.8},
            Sfx("blade", "steel", species="excalibur", power=0.8).voice("clash"),
        ),
        (
            {"creature": "mammal", "species": "wolf", "call": "attack", "size": 0.7},
            Creature("mammal", species="wolf", size=0.7).voice("attack"),
        ),
        (
            {"say": "Ready!", "lang": "en", "speaker": {"speaker": "deep"}, "seed": 17},
            Speaker.preset("deep").voice("Ready!", "en", seed=17),
        ),
        ({"music": "levelup", "seed": 17}, Cue("levelup", seed=17, sr=16000)),
    ],
)
def test_semantic_leaves_match_existing_api_exactly(expression, source):
    compiled = compile_document(load(data=project(expression)))
    actual = capture_plan(compiled.plan)
    expected = capture(source, 16000)
    assert np.array_equal(actual.audio, expected.audio)
    np.testing.assert_allclose(actual.replay(), actual.audio, rtol=0, atol=1e-7)


def test_authored_ids_do_not_change_audio():
    expression = {"sfx": "ui", "style": "crystal", "event": "confirm", "species": 7, "id": "first"}
    a = capture_plan(compile_document(load(data=project(expression))).plan)
    expression["id"] = "renamed"
    b = capture_plan(compile_document(load(data=project(expression))).plan)
    assert np.array_equal(a.audio, b.audio)
