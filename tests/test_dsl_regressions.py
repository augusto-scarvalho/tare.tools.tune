import json
from pathlib import Path

import numpy as np
import pytest
from test_dsl_loading import project

from tare.tools.tune.bundles import load_bundle
from tare.tools.tune.cli import main
from tare.tools.tune.dsl import DSLError, compile_document, load
from tare.tools.tune.dsl.adapters import materialized_id
from tare.tools.tune.dsl.validate import parse


def test_historical_schema_one_replays_without_regeneration():
    fixture = Path(__file__).parent / "fixtures/dsl/historical-schema1"
    provenance = json.loads((fixture / "provenance.json").read_text())
    loaded = load_bundle(fixture / provenance["revision"])
    assert loaded.manifest["schema"] == 1
    assert loaded.manifest["pcm_id"] == provenance["expected_pcm_id"]
    np.testing.assert_allclose(loaded.replay(), loaded.audio, rtol=0, atol=1e-7)


def test_encoding_and_duplicate_composition_ids_are_structured_errors():
    with pytest.raises(DSLError, match="UTF-8"):
        parse(b"\xff")
    with pytest.raises(DSLError, match="duplicate sibling"):
        load(data=project({"mix": [{"id": "a", "sound": {"sfx": "ui"}}] * 2}))


@pytest.mark.parametrize(
    "expression",
    [
        {"sfx": []},
        {"sfx": "ui", "style": {}},
        {"say": "Hello", "emotion": []},
        {"voice": [{"noise": {"start": "0s", "dur": 0.1, "freq": [[0, 200]]}}]},
        {"voice": [{"syllable": {"start": 0, "dur": 0.1, "pitch": True}}]},
    ],
)
def test_wrong_payload_types_produce_structured_failures(expression):
    with pytest.raises(DSLError):
        compile_document(load(data=project(expression)))


@pytest.mark.parametrize(
    "change",
    [{"remove": ["/noise/NaN"]}, {"remove": ["/noise/0", "/noise/0"]}, {"append": []}, {"set": {"/lowpass": "NaN"}}],
)
def test_malformed_guarded_edits_fail_without_render(change):
    original = {"sfx": "ui", "dry": True}
    guard = materialized_id(compile_document(load(data=project(original))).plan)
    with pytest.raises(DSLError):
        compile_document(load(data=project({"edit": original, "expect": guard} | change)))


def test_query_projection_and_definition_lineage(tmp_path, capsys):
    data = project({"use": "base"}, defs={"base": {"body": {"sfx": "ui", "dry": True}}})
    path = tmp_path / "bank.tune.json"
    path.write_text(json.dumps(data))
    assert main(["dsl", "query", str(path), "--fields", "target", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert set(result) == {"schema", "authored_revision", "target"}
    plan = compile_document(load(path)).plan
    assert plan.origins["chain"][0]["definition"] == "base"
    assert plan.origins["definition_pointer"] == "/defs/base/body"


def test_string_parameters_can_select_recipe_names():
    data = project(
        {"use": "recipe"},
        defs={
            "recipe": {
                "params": {"kind": {"type": "string", "default": "ui"}},
                "body": {"sfx": {"param": "kind"}, "dry": True},
            }
        },
    )
    assert compile_document(load(data=data)).plan.source.meta["kind"] == "ui"


def test_declared_primitive_banks_are_watched_before_first_success(tmp_path):
    from tare.tools.tune.dsl.dependencies import paths_for

    path = tmp_path / "banks.tune.json"
    expression = {
        "voice": [
            {"spoken": {"bank": "en/not_installed", "pieces": [[0, 1, 1]], "f0": [100]}},
            {"vocoded": {"clip": "attack/not_installed/take"}},
        ]
    }
    path.write_text(json.dumps(project(expression)))
    watched = {p.name for p in paths_for(path)}
    assert {"bank_en_not_installed.npz", "bank_en_not_installed.json", "barks.npz", "barks_audio.npz"} <= watched


@pytest.mark.parametrize(
    "sound, at, hint",
    [
        ({"emote": "hup"}, "/sounds/a/emote", "huh"),
        ({"emote": "jump", "style": "growl"}, "/sounds/a/style", "grunt"),
        ({"say": "Oi", "lang": "pt", "speaker": "natural:pt/alex"}, "/sounds/a/speaker", None),
        ({"say": "Oi", "speaker": {"speaker": "deeep"}}, "/sounds/a/speaker/speaker", "deep"),
        ({"say": "Oi", "speaker": {"speaker": "default", "engine": "natral"}}, "/sounds/a/speaker/engine", "natural"),
        ({"say": "Oi", "style": "babble"}, "/sounds/a/style", "gibberish"),
    ],
)
def test_check_rejects_unknown_voice_names_before_compiling(sound, at, hint):
    with pytest.raises(DSLError) as error:
        load(data=project(sound))
    assert error.value.code == "E_ENUM" and error.value.pointer == at
    message = str(error.value)  # close names in suggestions; otherwise a short list in the message
    assert hint is None and "engine" in message or hint in error.value.suggestions or hint in message
    natural = {"speaker": "default", "engine": "natural", "bank": "pt/alex"}
    load(data=project({"say": "Oi", "lang": "pt", "speaker": natural, "style": "mumble"}))
    load(data=project({"emote": {"param": "kind"}}, defs={}))  # parameter slots wait for compilation

