import json

import numpy as np
import pytest
from test_dsl_loading import project

from tare.tools.tune import Sfx, capture
from tare.tools.tune.bundles import load_bundle, save_bundle
from tare.tools.tune.dsl import DSLError, compile_document, load
from tare.tools.tune.dsl.composition import capture_plan
from tare.tools.tune.score import Score


def test_mix_preserves_exact_dtype_gain_and_replay(tmp_path):
    sound = {"sfx": "ui", "style": "crystal", "event": "confirm", "species": 7, "dry": True}
    expression = {
        "mix": [
            {"id": "one", "at": "0s", "sound": sound, "gain": 0.137, "pan": -0.3},
            {"id": "two", "at": "50ms", "sound": sound, "gain": -0.041},
        ],
        "gain": 0.7,
    }
    actual = capture_plan(compile_document(load(data=project(expression))).plan)
    voice = Sfx("ui", "crystal", species=7, dry=True).voice("confirm")
    score = Score(sr=16000, hall=0)
    y = capture(voice, 16000).audio
    score.add(y, gain=0.137, pan=-0.3)
    score.add(y, at=0.05, gain=-0.041)
    assert np.array_equal(actual.audio, score.render(gain=0.7))
    assert actual.manifest["schema"] == 2
    assert len(actual.manifest["nodes"]) == 3
    np.testing.assert_allclose(actual.replay(), actual.audio, rtol=0, atol=1e-7)
    bundle = save_bundle(actual, tmp_path)
    loaded = load_bundle(bundle)
    np.testing.assert_allclose(loaded.replay(), actual.audio, rtol=0, atol=1e-7)
    ids = [p["id"] for n in loaded.manifest["nodes"] for p in n["parts"] if n["kind"] == "voice"]
    muted = loaded.replay(mute=[ids[0]])
    assert muted.shape == actual.audio.shape and np.isfinite(muted).all()


def test_sequence_needs_explicit_recipe_span_and_keeps_tails():
    source = {"sfx": "ui", "style": "crystal", "event": "confirm", "dry": True}
    with pytest.raises(DSLError, match="span"):
        compile_document(load(data=project({"repeat": 2, "of": source})))
    source["span"] = "100ms"
    plan = compile_document(load(data=project({"repeat": 2, "of": source}))).plan
    assert plan.placements[1]["at"] == 0.1 and float(plan.span) == 0.2
    result = capture_plan(plan)
    assert len(result.audio) > 3200


def test_negative_pcm_cancellation_and_graph_validation(tmp_path):
    expression = {
        "mix": [{"sound": {"fm": {"duration": 0.1}}, "gain": 1}, {"sound": {"fm": {"duration": 0.1}}, "gain": -1}]
    }
    result = capture_plan(compile_document(load(data=project(expression))).plan)
    assert not result.audio.any()
    saved = save_bundle(result, tmp_path)
    manifest = json.loads((saved / "manifest.json").read_text())
    manifest["nodes"][0]["parts"][0]["child"] = manifest["root"]
    from tare.tools.tune.bundles import validate_graph

    with pytest.raises(ValueError, match="graph|cyclic|parent"):
        validate_graph(manifest, result.arrays)
