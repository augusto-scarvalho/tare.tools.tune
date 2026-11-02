"""Runner accounting and timeout tests use a fake process, never a model service."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def module(name):
    tools = Path(__file__).parent.parent / "tools"
    spec = importlib.util.spec_from_file_location(name, tools / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(tools))
    try:
        spec.loader.exec_module(result)
    finally:
        sys.path.pop(0)
    return result


def test_cli_usage_counts_cached_tokens_once_and_only_completed_commands():
    runner = module("codex_dsl_runner")
    events = [
        {"type": "item.started", "item": {"type": "command_execution", "id": "one"}},
        {"type": "item.completed", "item": {"type": "command_execution", "id": "one", "exit_code": 1}},
        {"type": "turn.completed", "usage": {"input_tokens": 200, "cached_input_tokens": 100, "output_tokens": 30}},
    ]
    result = runner.parse_events(events)
    assert result["usage"] == {"input_tokens": 200, "cached_input_tokens": 100, "output_tokens": 30}
    assert result["tool_calls"] == result["repair_turns"] == 1 and result["usage_complete"]
    with pytest.raises(ValueError):
        runner.parse_events([{"type": "turn.completed", "usage": {"input_tokens": -1}}])


def packet(tmp_path, seconds=5):
    return {
        "workspace": str(tmp_path),
        "artifact": str(tmp_path / "audio.npy"),
        "max_seconds": seconds,
        "max_tokens": 2000,
        "model": "fake-no-inference",
        "effort": "low",
        "route": "dsl_json",
        "task": {"id": "transport", "instruction": "No model calls"},
        "input_specification": {},
        "sample_rate": 16000,
    }


def test_codex_adapter_transport_and_artifact_scope_without_model_calls(tmp_path):
    runner = module("codex_dsl_runner")
    fake = tmp_path / "fake.py"
    fake.write_text(
        "import sys,json\nsys.stdin.read()\nprint(json.dumps({'type':'turn.completed',"
        "'usage':{'input_tokens':10,'output_tokens':3,'cached_input_tokens':0}}))\n"
    )
    result = runner.run(packet(tmp_path), [sys.executable, str(fake)])
    assert result["usage_complete"] and result["exit_code"] == 0 and not result["timed_out"]
    request = packet(tmp_path)
    request["artifact"] = str(tmp_path.parent / "outside.npy")
    with pytest.raises(ValueError, match="inside"):
        runner.run(request, [sys.executable, str(fake)])


def test_codex_adapter_timeout_reports_incomplete_usage(tmp_path):
    runner = module("codex_dsl_runner")
    fake = tmp_path / "slow.py"
    fake.write_text("import sys,time\nsys.stdin.read()\ntime.sleep(30)\n")
    result = runner.run(packet(tmp_path, 0.3), [sys.executable, str(fake)])
    assert result["timed_out"] and not result["usage_complete"] and result["exit_code"] is not None


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows sandbox preflight")
def test_failed_native_preflight_never_starts_an_inference_process(tmp_path, monkeypatch):
    import subprocess

    runner = module("codex_dsl_runner")
    monkeypatch.setattr(
        runner.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 1, "", "PermissionError")
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("must not start model process after failed preflight")

    monkeypatch.setattr(runner.subprocess, "Popen", forbidden)
    result = runner.run(packet(tmp_path), "fake-codex.exe")
    assert result["preflight_failed"] and result["provider_requests"] == 0
    assert result["usage"]["input_tokens"] == result["usage"]["output_tokens"] == 0


def test_repeated_context_accounting_includes_primer_errors_and_repair():
    bench = module("bench_dsl")
    tiktoken = pytest.importorskip("tiktoken")

    run = {
        "turns": [
            {"phase": "construct", "request": "a", "response": "b", "error": False},
            {"phase": "repair", "request": "c", "response": "d", "error": True},
        ],
        "full_inspection": {"long": list(range(40))},
        "compact_inspection": {"id": 1},
    }
    routes = {key: run for key in ("python", "project_json", "dsl_json")}
    result = {
        "primers": {key: "primer" for key in routes},
        "tasks": {"fixture": {"routes": routes}},
        "large_bank": {"routes": routes, "ablation": {"full_source": {"a": 1}, "targeted_query": {"a": 1}}},
    }
    bench.paired_metrics(result, tiktoken)
    row = result["metrics"]["o200k_base"]["tasks"]["fixture"]["python"]
    assert row["unique_content_tokens"] == 5 and row["summed_context_tokens_simulated"] == 8
    assert row["tool_calls"] == 2 and row["repair_turns"] == 1
    json.dumps(result, allow_nan=False)
