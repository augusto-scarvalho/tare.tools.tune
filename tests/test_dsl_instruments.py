import copy

import numpy as np
import pytest
from test_dsl_loading import project

from tare.tools.tune.dsl import DSLError, compile_document, load
from tare.tools.tune.dsl.composition import capture_plan
from tare.tools.tune.midi_export import export_midi


def instrument_project():
    template = {
        "instrument": [
            {
                "id": "tone",
                "syllable": {
                    "start": {"note": "start"},
                    "dur": {"note": "dur"},
                    "pitch": [[0, {"note": "f"}]],
                    "source": "sine",
                    "gain": {"rand": "level", "min": 0.4, "max": 0.5},
                },
            }
        ],
        "midi_program": 79,
    }
    return project(
        {
            "score": {
                "hall": 0,
                "tracks": [
                    {
                        "name": "lead",
                        "instrument": {"use": "glass"},
                        "notes": {"notes": [["C4", 0, 0.5], ["G4", 1, 0.5]]},
                    }
                ],
            }
        },
        defs={"glass": {"body": template}},
    )


def test_declarative_templates_and_renames_are_deterministic(tmp_path):
    data = instrument_project()
    first = compile_document(load(data=data))
    a = capture_plan(first.plan)
    changed = copy.deepcopy(data)
    changed["defs"]["renamed"] = changed["defs"].pop("glass")
    changed["sounds"]["a"]["score"]["tracks"][0]["instrument"]["use"] = "renamed"
    b = capture_plan(compile_document(load(data=changed)).plan)
    assert np.array_equal(a.audio, b.audio)
    track = first.plan.source.tracks["lead"]
    assert len(track.layers) == len(track.events) == 2
    assert track.layers[0].gain != track.layers[1].gain
    export_midi(first.plan.source, tmp_path / "glass.mid", programs=track.dsl_programs)
    assert (tmp_path / "glass.mid").read_bytes().startswith(b"MThd")
    data["defs"]["glass"]["body"]["instrument"][0]["syllable"]["start"] = {"note": "missing"}
    with pytest.raises(DSLError, match="Note slot"):
        compile_document(load(data=data))
