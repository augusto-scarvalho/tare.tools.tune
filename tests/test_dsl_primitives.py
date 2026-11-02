import json
from pathlib import Path

import numpy as np
import pytest
from test_dsl_loading import project

from tare.tools.tune import capture
from tare.tools.tune.dsl import DSLError, compile_document, load
from tare.tools.tune.dsl.adapters import materialized_id
from tare.tools.tune.dsl.composition import capture_plan
from tare.tools.tune.dsl.query import expansion
from tare.tools.tune.spec import Voice
from tare.tools.tune.speech import Speaker


def test_existing_voice_families_reach_frozen_audio_through_dsl():
    root = Path(__file__).parent / "fixtures/authoring"
    voices = json.loads((root / "voices.json").read_text())
    with np.load(root / "legacy.npz") as expected:
        for name, voice in voices.items():
            compiled = compile_document(load(data=project({"spec": voice})))
            actual = capture_plan(compiled.plan)
            assert actual.audio.shape == expected[name].shape
            np.testing.assert_allclose(actual.audio, expected[name], atol=1e-6, rtol=0)


@pytest.mark.parametrize("kind", ["spoken", "vocoded", "speech"])
def test_speech_primitives_are_available_and_replay(kind):
    from dataclasses import asdict

    from tare.tools.tune.dsl.registry import COLLECTIONS

    if kind == "spoken":
        voice = Speaker.preset("deep").but(engine="natural").voice("Olá.", lang="pt")
    elif kind == "vocoded":
        voice = Speaker.preset("deep").emote_voice("hurt")
    else:
        voice = Speaker.preset("deep").voice("Hi.", lang="en")
    layer = getattr(voice, kind)[0]
    op = next(key for key, collection in COLLECTIONS.items() if collection == kind)
    expression = {"voice": [{op: asdict(layer)}], "bus": {"seed": voice.seed}}
    actual = capture_plan(compile_document(load(data=project(expression))).plan)
    direct = capture(Voice(**{kind: [layer]}, seed=voice.seed), 16000)
    assert np.array_equal(actual.audio, direct.audio)
    np.testing.assert_allclose(actual.replay(), actual.audio, atol=1e-7, rtol=0)


def test_guarded_append_remove_and_actual_generated_paths():
    expression = {"voice": [{"syllable": {"start": 0, "dur": 0.2, "pitch": [[0, 220]], "source": "sine"}}]}
    original = compile_document(load(data=project(expression)))
    expanded = expansion(original)
    assert expanded["items"][0]["path"] == "/syllables/0"
    edited = {
        "edit": expression,
        "expect": materialized_id(original.plan),
        "append": {"/noise": [{"start": 0, "dur": 0.1, "freq": [[0, 4000]], "gain": -0.1}]},
    }
    plan = compile_document(load(data=project(edited))).plan
    assert plan.source.noise[0].gain == -0.1 and plan.edited
    removal = {"edit": edited, "expect": materialized_id(plan), "remove": ["/noise/0"]}
    result = compile_document(load(data=project(removal))).plan
    assert result.source.to_dict() == original.plan.source.to_dict()
    invalid = {
        "edit": expression,
        "expect": materialized_id(original.plan),
        "set": {"/syllables": [], "/syllables/0/gain": 0.1},
    }
    with pytest.raises(DSLError, match="overlapping"):
        compile_document(load(data=project(invalid)))
