import json

import pytest
from test_dsl_loading import project

from tare.tools.tune.cli import main
from tare.tools.tune.dsl import DSLError, compile_document, load
from tare.tools.tune.dsl.composition import capture_plan
from tare.tools.tune.dsl.query import inspection, page, project_fields


def test_compact_inspection_is_bounded_and_analysis_identity_is_projection_independent():
    value = {
        "voice": [
            {"syllable": {"start": 0, "dur": 0.2, "source": "sine", "pitch": [[0, f]], "gain": g}}
            for f, g in ((200, 0.8), (5000, 0.1))
        ]
    }
    captured = capture_plan(compile_document(load(data=project(value))).plan)
    a = inspection(captured, view="layers", band=(4000, 6000), top=1)
    b = inspection(captured, view="layers", band=(4000, 6000), top=2, fields=["id", "power"])
    assert a["items"][0]["label"] == "syllables[1]"
    assert a["analysis_id"] == b["analysis_id"] and a["query_id"] != b["query_id"]
    assert "planned" not in a and "parameters" not in a["items"][0]
    assert len(json.dumps(a)) < 1800


def test_cursors_bind_the_query_and_revision():
    a = page([{"id": i} for i in range(4)], "first", limit=2)
    assert page([{"id": i} for i in range(4)], "first", limit=2, cursor=a["next"])["items"][0]["id"] == 2
    with pytest.raises(DSLError, match="cursor"):
        page([{"id": i} for i in range(4)], "changed", limit=2, cursor=a["next"])


def test_nested_projection_keeps_edit_identity_and_rejects_query_expressions():
    result = {"schema": "tune.query/1", "authored_revision": "abc", "fragment": {"with": {"power": 0.5, "species": 7}}}
    assert project_fields(result, ["fragment.with.power"]) == {
        "schema": "tune.query/1",
        "authored_revision": "abc",
        "fragment": {"with": {"power": 0.5}},
    }
    for bad in ("fragment.with.*", "fragment.with.power.extra", "fragment..power"):
        with pytest.raises(DSLError):
            project_fields(result, [bad])
    rows = page([{"fields": {"power": {"min": 0, "max": 1}}}], "catalog", fields=["fields.power.min"])
    assert rows["items"] == [{"fields": {"power": {"min": 0}}}]


def test_cli_outputs_one_json_document_and_error_codes(tmp_path, capsys):
    path = tmp_path / "bank.tune.json"
    path.write_text(json.dumps(project()))
    assert main(["dsl", "check", str(path), "--expand", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["capabilities"]["voice_json"]
    assert main(["dsl", "query", str(path), "--target", "sound:a", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["target"] == "sound:a"
    value = project({"sfx": "ui", "powre": 0.1})
    path.write_text(json.dumps(value))
    assert main(["dsl", "check", str(path), "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and json.loads(captured.err)["code"] == "E_FIELD"
