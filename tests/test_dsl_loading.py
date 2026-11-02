import copy
import json

import pytest

from tare.tools.tune.dsl import DSLError, compile_document, load
from tare.tools.tune.dsl.validate import parse


def project(sound=None, **extra):
    return {
        "format": "tare.tools.tune.dsl",
        "version": 1,
        "context": {"sample_rate": 16000},
        "sounds": {"a": sound or {"sfx": "ui", "style": "crystal", "event": "confirm", "dry": True}},
        **extra,
    }


def test_strict_json_and_legacy_isolation():
    for text in ('{"x":1,"x":2}', '{"x":NaN}', "[" * 65 + "0" + "]" * 65, '{"x":1e999}'):
        with pytest.raises(DSLError):
            parse(text.encode())
    for edit in ({"version": True}, {"version": 2}, {"surprise": 1}):
        with pytest.raises(DSLError):
            load(data=project(**edit))
    from tare.tools.tune.spec import Voice

    assert Voice.from_dict({"typo": 1}).gain == 1  # Legacy permissiveness is unchanged.


def test_definition_parameters_are_lexical_and_instances_independent():
    data = project(
        {"use": "sound", "with": {"power": 0.8}},
        defs={
            "sound": {
                "params": {"power": {"type": "number", "default": 0.4, "min": 0, "max": 1}},
                "body": {"sfx": "ui", "style": "crystal", "event": "confirm", "power": {"param": "power"}, "dry": True},
            }
        },
    )
    before = copy.deepcopy(data)
    a = compile_document(load(data=data))
    assert a.plan.source.meta["power"] == 0.8 and data == before
    data["sounds"]["a"]["with"]["power"] = 0.1
    b = compile_document(load(data=data))
    assert a.plan.source.meta["power"] == 0.8 and b.plan.source.meta["power"] == 0.1
    data["sounds"]["a"]["with"]["power"] = 3
    with pytest.raises(DSLError, match="expected finite"):
        compile_document(load(data=data))


def test_cycles_and_expansion_bombs_fail_before_recipe_calls(monkeypatch):
    import tare.tools.tune.dsl.adapters as adapters

    calls = []
    monkeypatch.setattr(adapters, "leaf", lambda *args: calls.append(args))
    cyclic = project({"use": "x"}, defs={"x": {"body": {"use": "y"}}, "y": {"body": {"use": "x"}}})
    with pytest.raises(DSLError, match="cycle"):
        load(data=cyclic)
    bomb = project({"repeat": 256, "of": {"repeat": 256, "of": {"sfx": "ui"}}})
    with pytest.raises(DSLError, match="occurrences"):
        compile_document(load(data=bomb))
    assert calls == []


def test_bad_fields_types_ids_and_rate_are_explicit():
    cases = [
        project({"sfx": "ui", "powre": 0.5}),
        project({"seq": []}),
        project({"score": {"tracks": [{"name": "a"}, {"name": "a"}]}}),
        project({"seq": [{"pattern": "C4"}, {"sfx": "ui"}]}),
        project({"fm": {"duration": 181}}),
    ]
    for data in cases:
        with pytest.raises(DSLError):
            compile_document(load(data=data))
    with pytest.raises(DSLError):
        compile_document(load(data=project({"sfx": "ui", "seed": 2**60})))


def test_asset_roots_and_missing_sources(tmp_path):
    from tare.tools.tune.dsl.validate import asset

    path = tmp_path / "sub" / "project.tune.json"
    path.parent.mkdir()
    path.write_text(json.dumps(project()))
    other = tmp_path / "outside.wav"
    other.write_bytes(b"not audio")
    with pytest.raises(DSLError, match="outside"):
        asset(load(path), "../outside.wav")
    assert asset(load(path, asset_roots=[tmp_path]), "../outside.wav") == other
