"""Independent negative controls for semantic benchmark acceptance; no inference."""

import copy
import json

import pytest
from test_dsl_benchmark_protocol import module


def task(bench, name):
    return next(t for t in bench.cases() if t["case"] == name)


@pytest.mark.parametrize("route", ["python", "dsl"])
def test_creation_task_has_no_unrequested_filter_or_error_pipeline(tmp_path, route):
    bench = module("dsl_bench_v2")
    result = bench.run_case(task(bench, "single"), route, tmp_path / route)
    assert result["success"], result["error"]
    assert [t["action"] for t in result["turns"]] == ["setup", "create", "export"]
    assert (tmp_path / route / "audio.wav").is_file()


@pytest.mark.parametrize("route", ["python", "dsl"])
def test_omitting_requested_transpose_cannot_pass_artifact_acceptance(tmp_path, monkeypatch, route):
    bench = module("dsl_bench_v2")
    execute = bench.Session.step

    def omit(self, action, code, **options):
        return execute(self, action, "emit({'omitted':True})" if action == "transpose" else code, **options)

    monkeypatch.setattr(bench.Session, "step", omit)
    result = bench.run_case(task(bench, "arrangement"), route, tmp_path / route)
    assert not result["success"] and "AssertionError" in result["error"]


@pytest.mark.parametrize("route", ["python", "dsl"])
def test_recovery_changes_value_and_preserves_last_good_state(tmp_path, route):
    bench = module("dsl_bench_v2")
    result = bench.run_case(task(bench, "invalid-repair"), route, tmp_path / route)
    assert result["success"], result["error"]
    rejected = next(t for t in result["turns"] if t["action"] == "invalid")
    assert rejected["error"] and rejected["last_good_state_preserved"]
    assert [t["action"] for t in result["turns"] if t["expected_error"]] == ["invalid"]


def test_required_capability_refusal_is_executed_and_no_voice_artifact_exists(tmp_path):
    bench = module("dsl_bench_v2")
    for route in ("python", "dsl"):
        result = bench.run_case(task(bench, "capability"), route, tmp_path / route)
        assert result["success"], result["error"]
        refusal = next(t for t in result["turns"] if t["action"] == "voice_refusal")
        assert refusal["error"] and not (tmp_path / route / "audio.voice.json").exists()


def test_persisted_conflict_and_invalid_edit_are_real_unchanged_byte_failures(tmp_path):
    bench = module("dsl_bench_v2")
    for route in ("python", "dsl"):
        result = bench.run_case(task(bench, "bank-recovery"), route, tmp_path / route)
        assert result["success"], result["error"]
        assert [t["action"] for t in result["turns"] if t["error"]] == ["invalid", "stale_revision"]
        source = json.loads((tmp_path / route / "source.json").read_text())
        assert len(source["sounds"]) == 8


def test_narrow_refinement_keeps_existing_fields_without_reemitting_recipe(tmp_path):
    bench = module("dsl_bench_v2")
    result = bench.run_case(task(bench, "refinement"), "dsl", tmp_path / "dsl", workflow="narrow")
    assert result["success"], result["error"]
    edits = {t["action"]: t["request"]["python"] for t in result["turns"]}
    assert "/set/~1lowpass" in edits["filter_again"]
    assert "'sfx'" not in edits["filter"] + edits["filter_again"]


def test_v2_accounting_separates_service_contracts_and_counts_failed_turns():
    bench = module("dsl_bench_v2")
    tokenizers = pytest.importorskip("tiktoken")
    run = {
        "success": True,
        "turns": [
            {"action": "setup", "request": "a", "response": "b", "expected_error": False},
            {"action": "invalid", "request": "c", "response": "d", "expected_error": True},
        ],
    }
    result = {
        "cases": {
            "memory": {
                "track": "memory",
                "instruction": "x",
                "routes": {r: copy.deepcopy(run) for r in ("python", "dsl")},
            },
            "file": {
                "track": "persisted",
                "instruction": "y",
                "routes": {r: copy.deepcopy(run) for r in ("python", "dsl")},
            },
        }
    }
    bench.metrics(result, tokenizers)
    measured = result["metrics"]["o200k_base"]
    assert set(measured["by_service_contract"]) == {"memory", "persisted"}
    row = measured["cases"]["memory"]["dsl"]
    assert row["expected_failures"] == 1 and row["request_tokens"] == row["response_tokens"] == 2
    assert row["setup_tokens"] == row["warm_continuation_tokens"] == 2
    assert row["summed_context_tokens_simulated"] > row["content_tokens"]
