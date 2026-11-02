import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_dsl_loading import project

from tare.tools.tune.dsl import DSLError, compile_document, load
from tare.tools.tune.dsl.adapters import materialized_id
from tare.tools.tune.dsl.patch import patch_file


def envelope(revision, ops):
    return {"format": "tare.tools.tune.patch", "version": 1, "expect": revision, "ops": ops}


def test_patch_conflicts_preserve_source_and_definitions_can_be_renamed(tmp_path):
    path = tmp_path / "bank.tune.json"
    data = project({"use": "base"}, defs={"base": {"body": {"sfx": "ui", "dry": True}}})
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    revision = load(path).revision
    request = envelope(revision, [{"op": "set", "target": "def:base", "path": "/body/power", "value": 0.8}])

    def save(_):
        try:
            return patch_file(path, request)["authored_revision"]
        except DSLError as exc:
            return exc.code

    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(save, range(2)))
    assert results.count("E_REVISION_CONFLICT") == 1
    assert any(p.read_bytes() == before for p in (tmp_path / ".tune-backups").iterdir())
    current = load(path)
    patch_file(path, envelope(current.revision, [{"op": "rename", "target": "def:base", "name": "renamed"}]))
    updated = load(path)
    assert updated.data["sounds"]["a"]["use"] == "renamed"
    assert compile_document(updated).plan.source.meta["power"] == 0.8


def test_invalid_patch_and_stale_override_do_not_apply(tmp_path):
    path = tmp_path / "bank.tune.json"
    path.write_text(json.dumps(project()))
    before = path.read_bytes()
    with pytest.raises(DSLError):
        patch_file(
            path, envelope(load(path).revision, [{"op": "set", "target": "sound:a", "path": "/powre", "value": 1}])
        )
    assert path.read_bytes() == before
    original = compile_document(load(path)).plan
    expression = {
        "edit": load(path).data["sounds"]["a"],
        "expect": materialized_id(original),
        "set": {"/lowpass": 2400},
    }
    result = compile_document(load(data=project(expression)))
    assert result.plan.source.lowpass == 2400
    expression["edit"]["power"] = 0.9
    with pytest.raises(DSLError) as caught:
        compile_document(load(data=project(expression)))
    assert caught.value.code == "E_OVERRIDE_STALE"
