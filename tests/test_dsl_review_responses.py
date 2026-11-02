"""Summary transport must preserve decisions, measured effects and guarded edits."""

import copy
import json
from pathlib import Path

import numpy as np
import pytest
from test_dsl_review import source

from tare.tools.tune.bundles import load_bundle
from tare.tools.tune.cli import main
from tare.tools.tune.dsl import DSLError, edit_file, review
from tare.tools.tune.dsl.responses import respond


def recorded_edit(task):
    records = json.loads((Path(__file__).parents[1] / "docs/dsl-review-measurements.json").read_text())
    return next(t["response"] for t in records["cases"][task]["review"]["turns"] if t["action"] == "edit")


@pytest.mark.parametrize("task", ["refine", "transpose", "bank128"])
def test_summary_keeps_artifact_edit_scope_measurements_and_check_coverage(task):
    detail = recorded_edit(task)
    before = copy.deepcopy(detail)
    compact = respond(detail, "review", "compact")
    assert detail == before and respond(detail, "review") is detail
    assert compact["schema"] == "tune.compact/1"
    for key in ("bundle", "audio", "can_edit"):
        assert compact[key] == detail[key]
    for key in ("status", "affected_total"):
        assert compact["edit"][key] == detail["edit"][key]
    # names that only repeat the reviewed sound are omitted; any other affected sound keeps them
    redundant = detail["edit"]["affected"] == [detail["sound"]] and detail["edit"]["affected_total"] == 1
    assert compact["edit"].get("affected", [detail["sound"]] if redundant else None) == detail["edit"]["affected"]
    assert compact["checks"]["coverage"] == detail["checks"]["coverage"]
    assert compact["checks"]["passed"] == [r["check"] for r in detail["checks"]["results"]]
    assert compact["facts"]["peak_dbfs"] == [r["peak_dbfs"] for r in detail["facts"]["levels"]]
    assert compact["facts"]["rms_dbfs"] == [r["rms_dbfs"] for r in detail["facts"]["levels"]]
    assert compact["changes"]["source_changes"] == detail["changes"]["source"]["total"]
    assert "description" not in compact and "capabilities" not in compact
    assert "processing" not in compact["facts"] and "tracks" not in compact["facts"]
    if task == "transpose":
        assert compact["changes"]["tracks"] == detail["changes"]["tracks"]


def test_summary_never_hides_warning_failures_unknown_checks_or_truncation():
    detail = recorded_edit("bank128")
    detail["warnings"] = ["other sounds still need audio review"]
    detail["facts"]["tracks_truncated"] = True
    detail["edit"].update(affected=["sound_063"], affected_total=128)
    failed = {"check": "peak_dbfs", "status": "failed", "actual": -2, "expected": {"max": -6}}
    unknown = {"check": "capability:midi", "status": "not_run", "actual": None, "reason": "no capability record"}
    detail["checks"].update(status="failed", results=[failed, unknown])
    result = respond(detail, "review", "compact")
    assert result["warnings"] == detail["warnings"]
    assert result["checks"]["status"] == "failed" and result["checks"]["results"] == [failed, unknown]
    assert "passed" not in result["checks"] and result["facts"]["tracks_truncated"]
    assert result["edit"]["affected_total"] > len(result["edit"]["affected"])


def test_generic_projection_of_a_review_retains_observation_and_decision_context():
    from tare.tools.tune.dsl.query import project_fields

    compact = respond(recorded_edit("bank128"), "review", "compact")
    projected = project_fields(compact, ["facts.duration_s"])
    for key in ("bundle", "audio", "can_edit", "checks", "edit"):
        assert projected[key] == compact[key]
    assert projected["facts"] == {"duration_s": compact["facts"]["duration_s"]}


def test_compact_source_review_reuses_the_same_bundle_and_no_checks_stays_not_requested(tmp_path, monkeypatch):
    from tare.tools.tune.dsl import workflow

    path = source(tmp_path)
    detailed = review(path, output=tmp_path / "bundles")
    compact = review(path, output=tmp_path / "bundles", response="compact")
    assert compact == respond(detailed, "review", "compact")
    assert compact["bundle"] == detailed["bundle"] and compact["checks"]["status"] == "not_requested"

    def forbidden(*args, **kwargs):
        raise AssertionError("compact review of a bundle must not regenerate")

    path.unlink()
    monkeypatch.setattr(workflow, "compile_document", forbidden)
    monkeypatch.setattr(workflow, "capture_compiled", forbidden)
    assert review(compact["bundle"], response="compact") == compact


def test_compact_dry_run_commit_and_followup_keep_identical_audio_and_the_recipe(tmp_path):
    path = source(tmp_path)
    first = review(path, output=tmp_path / "bundles", response="compact")
    options = dict(from_bundle=first["bundle"], output=tmp_path / "bundles", refine={"/lowpass": 2400})
    before = path.read_bytes()
    detailed = edit_file(path, **options, dry_run=True)
    compact = edit_file(path, **options, dry_run=True, response="compact")
    assert compact == respond(detailed, "review", "compact") and path.read_bytes() == before
    assert not compact["can_edit"] and compact["edit"]["status"] == "preview"
    committed = edit_file(path, **options, response="compact")
    np.testing.assert_array_equal(load_bundle(committed["bundle"]).audio, load_bundle(compact["bundle"]).audio)
    next_edit = edit_file(
        path, from_bundle=committed["bundle"], output=tmp_path / "bundles", refine={"/gain": 0.25}, response="compact"
    )
    assert next_edit["edit"]["status"] == "applied"
    expression = json.loads(path.read_bytes())["sounds"]["a"]
    assert expression["set"] == {"/lowpass": 2400, "/gain": 0.25} and "sfx" in expression["edit"]
    before = path.read_bytes()
    with pytest.raises(DSLError) as stale:
        edit_file(path, **options, response="compact")
    assert stale.value.exit_code == 3 and path.read_bytes() == before


def test_compact_failed_candidate_carries_actionable_check_values_without_committing(tmp_path, capsys):
    path = source(tmp_path)
    first = review(path, output=tmp_path / "bundles", response="compact")
    checks = {"format": "tare.tools.tune.checks", "version": 1, "peak_dbfs": {"max": -100}}
    before = path.read_bytes()
    with pytest.raises(DSLError) as failure:
        edit_file(
            path,
            from_bundle=first["bundle"],
            output=tmp_path / "bundles",
            refine={"/gain": 1},
            checks=checks,
            response="compact",
        )
    report = failure.value.details
    assert failure.value.exit_code == 5 and report["schema"] == "tune.compact/1" and not report["can_edit"]
    assert report["checks"]["results"][0]["expected"] == {"max": -100}
    assert report["checks"]["results"][0]["actual"] > -100 and path.read_bytes() == before
    check_file = tmp_path / "checks.json"
    check_file.write_text(json.dumps(checks))
    assert (
        main(
            [
                "dsl",
                "review",
                str(path),
                "-o",
                str(tmp_path / "bundles"),
                "--checks",
                str(check_file),
                "--response",
                "compact",
                "--json",
            ]
        )
        == 5
    )
    assert json.loads(capsys.readouterr().err)["details"]["checks"]["results"][0]["status"] == "failed"


def test_invalid_response_is_rejected_before_rendering_or_writing(tmp_path):
    path = source(tmp_path)
    before = path.read_bytes()
    with pytest.raises(DSLError, match="response"):
        review(path, output=tmp_path / "bundles", response="invalid")
    assert not (tmp_path / "bundles").exists()
    first = review(path, output=tmp_path / "bundles")
    with pytest.raises(DSLError, match="response"):
        edit_file(
            path, from_bundle=first["bundle"], output=tmp_path / "bundles", refine={"/gain": 0.25}, response="invalid"
        )
    assert path.read_bytes() == before and not (tmp_path / ".tune-backups").exists()


def test_compact_cli_edit_and_silent_pcm_keep_json_finite(tmp_path, capsys):
    path = source(tmp_path)
    first = review(path, output=tmp_path / "bundles")
    assert (
        main(
            [
                "dsl",
                "edit",
                str(path),
                "--from-bundle",
                first["bundle"],
                "-o",
                str(tmp_path / "bundles"),
                "--refine",
                "/gain",
                "0.25",
                "--response",
                "compact",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["schema"] == "tune.compact/1" and result["edit"]["status"] == "applied"
    silent = source(tmp_path, {"rest": "10ms"})
    report = review(silent, output=tmp_path / "bundles", response="compact")
    assert report["facts"]["peak_dbfs"] == [None] and report["facts"]["rms_dbfs"] == [None]
    json.dumps(report, allow_nan=False)
