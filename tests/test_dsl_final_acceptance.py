import copy
import json

import numpy as np
import pytest
from test_dsl_loading import project

from tare.tools.tune.audio_io import write_wav
from tare.tools.tune.dsl import DSLError, build_file, compile_document, load
from tare.tools.tune.dsl.composition import capture_plan
from tare.tools.tune.dsl.patch import patch_file
from tare.tools.tune.dsl.query import inspection
from tare.tools.tune.score import Score


def test_leading_rest_chord_fractional_pitch_and_retrograde_have_hand_calculated_times():
    notes = {
        "notes": [[[60, 64.5], 0.5, 0.5, 0.75], [67, 2, 0.25, 0.5]],
        "span": "3b",
        "then": [{"retrograde": True}, {"stretch": 2}, {"transpose": -12}],
    }
    result = compile_document(
        load(
            data=project(
                {"score": {"bpm": 120, "meter": 3, "tracks": [{"name": "lead", "instrument": "harp", "notes": notes}]}}
            )
        )
    )
    events = result.plan.source.tracks["lead"].events
    assert [(e["pitch"], e["beat"], e["beats"], e["velocity"]) for e in events] == [
        (55, 1.5, 0.5, 0.5),
        (48, 4, 1, 0.75),
        (52.5, 4, 1, 0.75),
    ]
    assert not result.summary()["capabilities"]["midi"]


def test_antiphase_import_loop_coordinates_asset_replacement_and_pan_rejection(tmp_path):
    path = tmp_path / "scene.tune.json"
    audio = tmp_path / "contact.wav"
    data = project({"mix": [{"at": "10ms", "sound": {"audio": "contact.wav"}}], "loop": "20ms"})
    path.write_text(json.dumps(data))
    wave = np.tile([0.125, -0.125], (640, 1)).astype(np.float32)
    write_wav(audio, wave, 16000)
    first = build_file(path)
    assert not first.audio.mean(axis=1).any() and first.audio.any()
    child = next(node["id"] for node in first.manifest["nodes"] if node["kind"] == "audio")
    rows = inspection(first, view="layers", node_id=child, start=0, end=0.02)
    # PCM16 stores int(.125*32767)=4095. Two folds and two channels:
    expected_power = 8 * float(np.float32(4095) / np.float32(32767)) ** 2
    assert rows["items"][0]["power"] == pytest.approx(expected_power, abs=1e-12)
    write_wav(audio, wave * 2, 16000)
    second = build_file(path)
    assert first.manifest["revision"] != second.manifest["revision"]
    dependency = str(audio.resolve())
    assert first.manifest["dsl"]["dependencies"][dependency] != second.manifest["dsl"]["dependencies"][dependency]
    data["sounds"]["a"]["mix"][0]["pan"] = 0.2
    path.write_text(json.dumps(data))
    with pytest.raises(DSLError) as failure:
        build_file(path)
    assert failure.value.code == "E_PAN"


def test_nested_mute_reuses_surviving_buffers_and_limiter_envelope():
    voice = {"voice": [{"syllable": {"start": 0, "dur": 0.1, "pitch": [[0, 440]], "source": "sine"}}]}
    result = capture_plan(
        compile_document(
            load(
                data=project(
                    {
                        "mix": [{"sound": voice, "gain": 1}, {"at": "10ms", "sound": voice, "gain": 0.13}],
                        "effects": [{"type": "limiter", "ceiling": 0.3}],
                    }
                )
            )
        ).plan
    )
    saved = {key: value.copy() for key, value in result.arrays.items()}
    root = next(node for node in result.manifest["nodes"] if node["id"] == result.manifest["root"])
    parts = root["parts"]
    survivor = parts[1]
    dry = np.zeros((root["input_length"], 2))
    y = result.arrays[survivor["audio"]]
    start = survivor["start"]
    dry[start : start + len(y)] = y[:, None] / np.sqrt(2)
    factors = {
        key: result.arrays[value] if key.startswith("effect_") and key.endswith("_gain") else value
        for key, value in root["factors"].items()
    }
    expected = Score(**root["params"]).finish(
        dry, np.zeros(len(dry)), np.zeros(len(dry)), loop=root["loop"], gain=root["gain"], fixed=factors
    )
    muted = result.replay(mute=[parts[0]["id"]])
    np.testing.assert_allclose(muted, expected, rtol=0, atol=1e-7)
    assert muted.shape == result.audio.shape
    assert all(np.array_equal(value, saved[key]) for key, value in result.arrays.items())


def test_structural_patch_changes_only_selected_instance_and_definition_impact_is_exact(tmp_path):
    data = project(
        {
            "voice": [
                {"id": "a", "noise": {"start": 0, "dur": 0.1, "freq": [[0, 1000]]}},
                {"id": "b", "noise": {"start": 0, "dur": 0.1, "freq": [[0, 2000]]}},
            ]
        },
        defs={"shared": {"body": {"sfx": "ui", "dry": True}}},
    )
    data["sounds"]["uses_shared"] = {"use": "shared"}
    path = tmp_path / "bank.tune.json"
    path.write_text(json.dumps(data))

    def transaction(ops):
        return patch_file(
            path, {"format": "tare.tools.tune.patch", "version": 1, "expect": load(path).revision, "ops": ops}
        )

    transaction(
        [
            {"op": "move", "target": "sound:a", "from": "/voice/1", "path": "/voice/0"},
            {"op": "set", "target": "sound:a/id:a", "path": "/noise/gain", "value": 0.3},
        ]
    )
    updated = load(path).data
    assert [node["id"] for node in updated["sounds"]["a"]["voice"]] == ["b", "a"]
    assert updated["sounds"]["a"]["voice"][1]["noise"]["gain"] == 0.3
    assert updated["sounds"]["uses_shared"] == data["sounds"]["uses_shared"]
    before = copy.deepcopy(updated["sounds"]["a"])
    changed = transaction([{"op": "rename", "target": "def:shared", "name": "new_name"}])
    assert changed["affected"] == ["uses_shared"]
    assert load(path).data["sounds"]["a"] == before


def test_score_expansion_exposes_guarded_bus_and_primitive_paths_without_falsifying_midi(tmp_path):
    from tare.tools.tune.dsl.query import expansion
    from tare.tools.tune.midi_export import export_midi

    source = {
        "score": {"hall": 0, "tracks": [{"name": "lead", "instrument": "harp", "notes": {"notes": [[60, 0, 0.5]]}}]}
    }
    original = compile_document(load(data=project(source)))
    expanded = expansion(original, view="full")
    paths = {row["path"] for row in expanded["items"]}
    assert {"/bus", "/tracks/lead", "/tracks/lead/layers/0"} <= paths
    edited = compile_document(
        load(
            data=project(
                {
                    "edit": source,
                    "expect": expanded["materialized_id"],
                    "set": {"/bus/lowpass": 1800, "/tracks/lead/layers/0/gain": 0.3},
                }
            )
        )
    )
    assert edited.plan.source.lowpass == 1800
    assert not edited.summary()["capabilities"]["midi"]
    with pytest.raises(ValueError, match="layers changed"):
        export_midi(edited.plan.source, tmp_path / "edited.mid")
    manual = Score(sr=16000, hall=0, lowpass=1800)
    manual.track("lead").play("harp", [[60, 0, 0.5]])
    manual.tracks["lead"].layers[0].gain = 0.3
    assert np.array_equal(capture_plan(edited.plan).audio, manual.render())


def test_appended_and_generated_cue_parts_hit_the_same_pre_render_limit():
    from tare.tools.tune.dsl import Budgets

    tiny = {"syllable": {"start": 0, "dur": 0.01, "pitch": [[0, 440]], "source": "sine"}}
    primitive = compile_document(load(data=project({"voice": [tiny]})))
    from tare.tools.tune.dsl.adapters import materialized_id

    edited = {
        "edit": {"voice": [tiny]},
        "expect": materialized_id(primitive.plan),
        "append": {"/syllables": [tiny["syllable"]] * 3},
    }
    with pytest.raises(DSLError, match="capture part/layer"):
        compile_document(load(data=project(edited), limits=Budgets(layers=3)))
    with pytest.raises(DSLError, match="capture part/layer"):
        compile_document(load(data=project({"music": "boss"})))
