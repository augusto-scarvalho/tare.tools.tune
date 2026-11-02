import json
from pathlib import Path

import numpy as np
import pytest
from test_authoring_workflows import parse_midi
from test_dsl_loading import project

from tare.tools.tune.dsl import DSLError, compile_document, load
from tare.tools.tune.dsl.composition import capture_plan
from tare.tools.tune.midi_export import export_midi
from tare.tools.tune.score import Score


def test_three_beat_trailing_rest_and_midi_are_independently_correct(tmp_path):
    path = Path(__file__).parent.parent / "examples" / "dsl-music.tune.json"
    compiled = compile_document(load(path))
    score = compiled.plan.source
    events = score.tracks["lead-v1"].events
    assert [(e["beat"], e["beats"], e["pitch"]) for e in events] == [(0, 1, 60), (3, 1, 60)]
    assert [(e["beat"], e["pitch"]) for e in score.tracks["bass-v1"].events] == [(0, 48), (3, 48)]
    assert compiled.plan.loop == 3
    midi = tmp_path / "theme.mid"
    export_midi(score, midi, loop=compiled.plan.loop)
    parsed = parse_midi(midi)
    assert (0, "meter", [3, 2, 24, 8]) in parsed[0]
    assert (2880, 0x90, [60, 102]) in parsed[1]
    assert (3840, 0x80, [60, 0]) in parsed[1]


def test_score_call_boundaries_preserve_frozen_note_seeds():
    notes = {
        "score": {
            "seed": 17,
            "bpm": 120,
            "meter": 3,
            "hall": 0,
            "tracks": [
                {
                    "name": "lead-v1",
                    "clips": [
                        {
                            "instrument": "harp",
                            "at": "0.5b",
                            "notes": {"notes": [[["C4", "E4"], 0, 1], ["G4", 2, 0.5]]},
                        },
                        {"instrument": "marimba", "at": "3b", "notes": {"notes": [["C5", 0, 0.5]]}},
                    ],
                }
            ],
        }
    }
    compiled = compile_document(load(data=project(notes)))
    reference = json.loads((Path(__file__).parent / "fixtures/dsl/legacy-seeds.json").read_text())
    for actual, expected in zip(compiled.plan.source.tracks["lead-v1"].events, reference["events"], strict=True):
        assert (actual["seed"], actual["start"], actual["duration"], actual["layers"]) == (
            expected["seed"],
            expected["start"],
            expected["duration"],
            expected["layers"],
        )
    manual = Score(bpm=120, meter=3, sr=16000, hall=0, seed=17)
    track = manual.track("lead-v1").play("harp", [(["C4", "E4"], 0, 1), ("G4", 2, 0.5)], offset=0.5)
    track.play("marimba", [("C5", 0, 0.5)], offset=3)
    assert np.array_equal(capture_plan(compiled.plan).audio, manual.render())


def test_transform_order_quantize_and_humanize():
    phrase = {
        "notes": [["C4", 0.1, 0.5], ["G4", 1.1, 0.5]],
        "span": "3b",
        "then": [{"transpose": 12}, {"stretch": 2}, {"quantize": "1/2b"}],
    }
    source = {"score": {"hall": 0, "tracks": [{"name": "test", "instrument": "harp", "notes": phrase}]}}
    a = compile_document(load(data=project(source))).plan.source.tracks["test"].events
    assert [(e["pitch"], e["beat"], e["beats"]) for e in a] == [(72, 0, 1), (79, 2, 1)]
    phrase["then"] = [{"humanize": {"time": "10ms", "velocity": 0.02, "seed": 31}}]
    a = compile_document(load(data=project(source))).plan.source.tracks["test"].events
    b = compile_document(load(data=project(source))).plan.source.tracks["test"].events
    assert a == b
    assert abs(a[0]["beat"] - 0.1) <= 1 / 60
    phrase["then"] = [{"velocity": 3}]
    with pytest.raises(DSLError):
        compile_document(load(data=project(source)))
