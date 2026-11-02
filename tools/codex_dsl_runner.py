"""Fresh Codex CLI pilot adapter; model calls occur only when deliberately invoked."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from dsl_bench_paired import PRIMERS

ROOT = Path(__file__).resolve().parents[1]
POLICIES = {
    "python": "Use existing Python APIs (Sfx,Creature,Speaker,Score,capture). "
    "Do not use DSL JSON, its dispatcher or package. "
    "Translate the shared specification into these existing APIs.",
    "project_json": "Use legacy project JSON with the authoring loader/CLI. Use existing Python API helpers "
    "where the old format lacks composition; retain that code. Do not use the new dsl package.",
    "dsl_json": "Use the new DSL JSON, builders or compact CLI. Retain editable recipes and definitions. "
    "Use scoped queries/patches and guarded materialized edits where applicable.",
}


def parse_events(events):
    usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    commands, messages, completed = [], [], False
    for event in events:
        if event.get("type") == "turn.completed":
            completed = True
            for key in usage:
                value = event.get("usage", {}).get(key, 0)
                if type(value) is not int or value < 0:
                    raise ValueError("invalid Codex usage event")
                usage[key] += value
        if event.get("type") == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "command_execution":
                commands.append(item)
            if item.get("type") == "agent_message":
                messages.append(item.get("text", ""))
    return {
        "usage": usage,
        "usage_complete": completed,
        "tool_calls": len(commands),
        "repair_turns": sum(item.get("exit_code", 0) != 0 for item in commands),
        "repair_metric": "failed commands, not inferred agent reasoning turns",
        "messages": messages,
    }


def terminate_tree(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
    else:
        import signal

        os.killpg(process.pid, signal.SIGKILL)


def run(packet, executable=None):
    directory = Path(packet["workspace"]).resolve()
    artifact = Path(packet["artifact"]).resolve()
    if not directory.is_dir() or not artifact.is_relative_to(directory):
        raise ValueError("artifact must stay inside the existing pilot workspace")
    if packet["route"] not in POLICIES or packet["max_seconds"] <= 0:
        raise ValueError("invalid route/deadline")
    executable = executable or shutil.which("codex")
    if executable is None:
        raise ValueError("Codex CLI is not installed")
    if os.name == "nt" and not isinstance(executable, list):
        probe = [
            str(executable),
            "sandbox",
            "-P",
            ":workspace",
            "-C",
            str(directory),
            "-c",
            'windows.sandbox="unelevated"',
            "-c",
            "sandbox_workspace_write.writable_roots=" + json.dumps([directory.as_posix()]),
            "--",
            sys.executable,
            "-c",
            "from pathlib import Path; "
            "p=Path('.pilot-write-probe');p.write_text('ok');assert p.read_text()=='ok';p.unlink()",
        ]
        checked = subprocess.run(probe, capture_output=True, text=True, timeout=min(20, packet["max_seconds"]))
        if checked.returncode:
            return {
                "protocol": "tare.tools.tune.pilot/1",
                "model": packet["model"],
                "effort": packet["effort"],
                "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
                "usage_complete": True,
                "provider_requests": 0,
                "preflight_failed": True,
                "tool_calls": 0,
                "repair_turns": 0,
                "messages": ["Sandbox preflight: workspace write access denied before any model request."],
                "transcript": {"preflight_argv": probe, "stdout": checked.stdout, "stderr": checked.stderr},
            }
    seconds = min(float(packet["max_seconds"]), 600)
    task = packet["task"]
    prompt = (
        "Run one isolated audio benchmark task. Work only in this workspace; read only the installed Tune package "
        "and the supplied reference guides when necessary. Do not read benchmark oracles, tests, prior runs, "
        "Codex history, credentials or other projects. Do not use networking or delegate to other agents. "
        "Do not change the Tune package.\n"
        f"Python: {sys.executable}\nPackage source: {ROOT / 'src'}\n"
        f"Route: {packet['route']}\n{POLICIES[packet['route']]}\n"
        f"Task: {json.dumps(task, ensure_ascii=False)}\n"
        f"Shared input specification: {json.dumps(packet['input_specification'], ensure_ascii=False)}\n"
        "Preserve sample rate, synthesis track names, note/play-call ordering, species and takes "
        "from the specification. "
        "Final audio is checked against the existing API; do not add normalization or resampling.\n"
        f"Write final float32 audio with numpy.save to {artifact}, at {packet['sample_rate']} Hz. "
        "Retain the authored source/program in the workspace. Report only artifact path, checks and limitations. "
        f"Time limit: {seconds:.0f} seconds. Stop promptly.\n"
    )
    guide = ROOT / "docs" / ("dsl-agent.md" if packet["route"] == "dsl_json" else "authoring.md")
    prompt += "Route primer:\n" + PRIMERS[packet["route"]] + "\n"
    if guide.exists():
        prompt += f"Optional reference guide (read only the needed section): {guide}\n"
    command = (list(executable) if isinstance(executable, list) else [str(executable)]) + [
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--add-dir",
        str(directory),
        "-c",
        "sandbox_workspace_write.writable_roots=" + json.dumps([directory.as_posix()]),
        "--model",
        packet["model"],
        "-c",
        "model_reasoning_effort=" + json.dumps(packet["effort"]),
        "-c",
        'approval_policy="never"',
        *(["-c", 'windows.sandbox="unelevated"'] if os.name == "nt" else []),
        "--cd",
        str(directory),
        "-",
    ]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    stderr_path = directory / "runner-stderr.txt"
    events, timed_out, oversized = [], threading.Event(), False
    begin = time.monotonic()
    with stderr_path.open("w", encoding="utf-8") as errors:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
            encoding="utf-8",
            env=environment,
            cwd=directory,
            start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        def timeout():
            timed_out.set()
            terminate_tree(process)

        timer = threading.Timer(seconds, timeout)
        timer.daemon = True
        timer.start()
        size = 0
        try:
            process.stdin.write(prompt)
            process.stdin.close()
            for line in process.stdout:
                size += len(line.encode("utf-8"))
                if size > 16 * 1024 * 1024:
                    oversized = True
                    terminate_tree(process)
                    break
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    events.append({"type": "unparsed_output", "text": line[:1000]})
            process.wait(timeout=5)
        finally:
            timer.cancel()
            terminate_tree(process)
    metrics = parse_events(events)
    forbidden = ("tune.dsl", "tune dsl ", "tune.exe dsl ", "import dsl")
    violation = packet["route"] != "dsl_json" and any(
        any(word in str(event.get("item", {}).get("command", "")) for word in forbidden)
        for event in events
        if event.get("type") == "item.completed"
    )
    return {
        "protocol": "tare.tools.tune.pilot/1",
        "model": packet["model"],
        "effort": packet["effort"],
        "model_identity": "requested CLI model; backend snapshot is not independently reported",
        "provider_requests": "Codex internal turns; see actual turn.completed usage",
        **metrics,
        "seconds": time.monotonic() - begin,
        "exit_code": process.returncode,
        "route_violation": violation,
        "timed_out": timed_out.is_set(),
        "oversized": oversized,
        "transcript": {"prompt": prompt, "events": events},
        "budget_semantics": "Hard wall-clock/process-tree bound; token accounting is available after a completed turn. "
        "Codex CLI does not provide a verified hard token ceiling through this adapter.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-executable")
    args = parser.parse_args()
    packet = json.load(sys.stdin)
    print(json.dumps(run(packet, args.codex_executable), ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
