"""Compact transport must retain enough evidence for safe follow-up operations."""

import copy
import json

import pytest
from test_dsl_loading import project

from tare.tools.tune import Voice, capture
from tare.tools.tune.cli import main
from tare.tools.tune.dsl import DSLError, compile_document, load
from tare.tools.tune.dsl.migrate import freeze
from tare.tools.tune.dsl.patch import patch_file
from tare.tools.tune.dsl.query import authored, expansion, inspection, project_fields
from tare.tools.tune.spec import Noise


@pytest.fixture
def captured():
    return capture(Voice(noise=[Noise(0, 0.04, [(0, 1000 + i * 300)]) for i in range(4)]), 16000)


def test_detailed_inspection_contract_and_compact_revision_stage_and_rows(captured):
    detailed = inspection(captured, view="layers", fields=["id", "power"])
    assert inspection(captured, view="layers", fields=["id", "power"], response="detailed") == detailed
    compact = inspection(captured, view="layers", fields=["id", "power"], response="compact")
    assert compact["schema"] == "tune.compact/1"
    for key in ("items", "revision", "stage", "window_s", "band_hz", "measure"):
        assert compact[key] == detailed[key]
    assert "query_id" not in compact and "analysis_id" not in compact
    assert len(compact["revision"]) == 64


def test_compact_cursor_keeps_full_scope_and_refuses_another_query(captured):
    first = inspection(captured, view="layers", limit=1, fields=["id"], response="compact")
    detailed = inspection(captured, view="layers", limit=1, fields=["id"])
    assert first["next"] == detailed["next"] and first["truncated"] and first["total"] == 4
    second = inspection(captured, view="layers", limit=1, fields=["id"], cursor=first["next"], response="compact")
    assert second["items"] != first["items"]
    with pytest.raises(DSLError, match="cursor"):
        inspection(
            captured, view="layers", limit=1, fields=["id"], start=0.01, cursor=first["next"], response="compact"
        )


def test_compact_summary_projection_retains_the_audio_scope(captured):
    result = inspection(captured, response="compact", fields=["duration"])
    assert result["root_stage"] == captured.manifest["root"]
    assert result["revision"] == captured.manifest["revision"] and result["duration"] > 0


def test_compact_authored_projection_and_materialized_guard_remain_actionable():
    data = project({"use": "hit"}, defs={"hit": {"body": {"sfx": "ui", "dry": True}}})
    data["sounds"]["second"] = {"use": "hit"}
    document = load(data=data)
    compact = authored(document, "def:hit", response="compact")
    assert set(compact["affected"]) == {"a", "second"}
    projected = project_fields(compact, ["fragment.body.sfx"])
    assert projected["authored_revision"] == compact["authored_revision"]
    assert projected["target"] == "def:hit" and projected["affected_total"] == 2
    result = compile_document(document, name="a")
    expanded = expansion(result, limit=1, fields=["kind", "path"], response="compact")
    assert expanded["materialized_id"] == expansion(result)["materialized_id"]
    assert expanded["authored_revision"] == document.revision


def test_compact_patch_never_refreshes_an_observed_revision(tmp_path):
    path = tmp_path / "source.json"
    path.write_text(json.dumps(project({"sfx": "ui", "power": 0.5, "dry": True})))
    revision = load(path).revision
    patch = {
        "format": "tare.tools.tune.patch",
        "version": 1,
        "expect": revision,
        "ops": [{"op": "set", "target": "sound:a", "path": "/power", "value": 0.7}],
    }
    result = patch_file(path, patch, response="compact")
    assert result["authored_revision"] != revision and result["changed"] == ["sound:a"]
    assert "affected" not in result and result["affected_total"] == 1  # names would only repeat `changed`
    before = path.read_bytes()
    with pytest.raises(DSLError) as conflict:
        patch_file(path, patch, response="compact")
    assert conflict.value.code == "E_REVISION_CONFLICT" and path.read_bytes() == before
    patch["expect"] = result["authored_revision"]
    patch["ops"][0]["value"] = "bad"
    with pytest.raises(DSLError):
        patch_file(path, patch, response="compact")
    assert path.read_bytes() == before
    with pytest.raises(DSLError):
        patch_file(path, patch, response="unknown")
    assert path.read_bytes() == before


def test_compact_export_preserves_audio_identity_and_track_omission_warning(tmp_path):
    path = tmp_path / "music.json"
    path.write_text(
        json.dumps(
            project(
                {"score": {"hall": 0.1, "tracks": [{"name": "lead", "instrument": "harp", "notes": {"pattern": "C4"}}]}}
            )
        )
    )
    result = freeze(path, tmp_path / "lead.json", format="voice", track="lead", response="compact")
    assert result["warnings"] and "omitted" in result["warnings"][0]
    assert len(result["pcm_id"]) == len(result["source_revision"]) == 64
    assert result["frames"] > 0 and result["sample_rate"] == 16000
    a = freeze(path, tmp_path / "a.wav", format="wav")
    b = freeze(path, tmp_path / "b.wav", format="wav", response="compact")
    assert (tmp_path / "a.wav").read_bytes() == (tmp_path / "b.wav").read_bytes()
    assert a["pcm_id"] == b["pcm_id"] and a["source_revision"] == b["source_revision"]


def test_compact_envelope_preserves_truncation_and_does_not_mutate_details():
    from tare.tools.tune.dsl.responses import respond

    detail = {
        "schema": "tune.query/1",
        "authored_revision": "a" * 64,
        "changed": ["def:hit"],
        "affected": ["a"],
        "affected_total": 200,
        "warnings": ["some loss"],
        "dry_run": True,
    }
    before = copy.deepcopy(detail)
    compact = respond(detail, "patch", "compact")
    assert compact["dry_run"] and compact["truncated"] and compact["warnings"] == detail["warnings"]
    assert detail == before
    shared = dict(detail, affected=["a", "b"], affected_total=2)
    assert respond(shared, "patch", "compact")["affected"] == ["a", "b"]  # a definition's impact stays named


def test_cli_compact_serialization_and_conflicts(tmp_path, capsys):
    path = tmp_path / "bank.json"
    path.write_text(json.dumps(project()))
    assert (
        main(
            [
                "dsl",
                "query",
                str(path),
                "--target",
                "sound:a",
                "--fields",
                "fragment.sfx",
                "--response",
                "compact",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["schema"] == "tune.compact/1" and result["target"] == "sound:a"
    assert main(["inspect", str(path), "--response", "compact", "--no-pitch", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["schema"] == "tune.compact/1"
    assert main(["inspect", str(path), "--view", "full", "--response", "compact", "--json"]) == 2
    failed = capsys.readouterr()
    assert not failed.out and json.loads(failed.err)["code"] == "E_OPTION"
    patch = tmp_path / "patch.json"
    patch.write_text(json.dumps({"format": "tare.tools.tune.patch", "version": 1, "expect": "old", "ops": []}))
    assert main(["dsl", "patch", str(path), "--patch", str(patch), "--response", "compact", "--json"]) == 3
    failed = capsys.readouterr()
    assert not failed.out and json.loads(failed.err)["schema"] == "tune.compact/1"
