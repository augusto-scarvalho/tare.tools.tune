"""Opt-in live pilot protocol for a configured, budget-enforcing external runner."""

import argparse
import json
import random
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from dsl_bench_corpus import CORPUS, IMPORTS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("output/dsl-live-pilot.json"))
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--exploratory", action="store_true", help="one repetition; never a qualification result")
    parser.add_argument("--task", action="append", help="select corpus task IDs for a bounded pilot")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    required = {"runner", "model", "effort", "runs_per_task", "max_total_tokens", "max_seconds", "per_run_seconds"}
    if set(config) != required or not isinstance(config["runner"], list) or not config["runner"]:
        parser.error("config must specify runner argv, model, effort, repeat count and all three budgets")
    for key in ("runs_per_task", "max_total_tokens", "max_seconds", "per_run_seconds"):
        if type(config[key]) is not int or config[key] <= 0:
            parser.error(key + " must be a positive integer")
    if config["runs_per_task"] < 3:
        parser.error("qualification requires at least three fresh runs per task and route")
    if any(not isinstance(word, str) for word in config["runner"]):
        parser.error("runner must be an argument array; no shell command is accepted")
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    jobs = [
        (task, route, repeat)
        for task in corpus["tasks"]
        for route in ("python", "project_json", "dsl_json")
        for repeat in range(1 if args.exploratory else config["runs_per_task"])
        if args.task is None or task["id"] in args.task
    ]
    if args.task and set(args.task) - {task["id"] for task in corpus["tasks"]}:
        parser.error("unknown task ID")
    random.Random(17).shuffle(jobs)
    if args.exploratory:
        # Finish each randomized route triplet before spending quota on another task.
        order = list(dict.fromkeys(task["id"] for task, _, _ in jobs))
        jobs.sort(key=lambda job: order.index(job[0]["id"]))
    if args.plan_only:
        print(
            json.dumps(
                {"jobs": len(jobs), "config": config, "model_calls": 0, "exploratory": args.exploratory}, indent=2
            )
        )
        return
    started, tokens, results = time.monotonic(), 0, []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for task, route, repeat in jobs:
        remaining_seconds = config["max_seconds"] - (time.monotonic() - started)
        remaining_tokens = config["max_total_tokens"] - tokens
        if remaining_seconds <= 0 or remaining_tokens <= 0:
            break
        folder = tempfile.mkdtemp(prefix=f"pilot-{task['id']}-{route}-{repeat}-", dir=args.output.parent)
        if folder:
            directory = Path(folder)
            packet = {
                "protocol": "tare.tools.tune.pilot/1",
                "fresh_session": True,
                "model": config["model"],
                "effort": config["effort"],
                "route": route,
                "task": {key: task[key] for key in ("id", "instruction", "acceptance")},
                "input_specification": task["dsl"],
                "workspace": folder,
                "artifact": str(directory / "audio.npy"),
                "sample_rate": 16000,
                "max_tokens": remaining_tokens,
                "max_seconds": min(config["per_run_seconds"], remaining_seconds),
                "requirements": "Runner enforces budgets, cleans child processes and reports actual provider usage.",
            }
            provided_bank = None
            if task["id"] == "localized-bank-edit":
                import copy

                provided_bank = copy.deepcopy(task["dsl"])
                provided_bank["sounds"] = {"main": provided_bank["sounds"]["main"]} | {
                    f"sound_{i:03}": copy.deepcopy(provided_bank["sounds"]["main"]) for i in range(127)
                }
                if route != "dsl_json":
                    provided_bank = {
                        "sample_rate": 16000,
                        "sounds": {
                            key: {
                                "type": "sfx",
                                "kind": "ui",
                                "style": "crystal",
                                "event": "confirm",
                                "options": {"species": 7, "power": 0.5, "dry": True},
                            }
                            for key in provided_bank["sounds"]
                        },
                    }
                (directory / "bank.json").write_text(json.dumps(provided_bank), encoding="utf-8")
                packet["input_specification"] = {
                    "provided_file": "bank.json",
                    "bank_size": 128,
                    "target": "main",
                    "current_power": 0.5,
                    "final_power": 0.8,
                    "sample_rate": 16000,
                    "requirement": "Edit only this target in the provided file; "
                    "preserve every other value. Render main.",
                }
            begin = time.monotonic()
            row = {"task": task["id"], "route": route, "repeat": repeat, "success": False}
            try:
                completed = subprocess.run(
                    config["runner"],
                    input=json.dumps(packet),
                    capture_output=True,
                    text=True,
                    timeout=packet["max_seconds"],
                    check=True,
                )
                if len(completed.stdout) > 32 * 1024 * 1024:
                    raise ValueError("runner response exceeds 32 MiB")
                report = json.loads(completed.stdout)
                row.update(
                    transcript=report.get("transcript"),
                    artifact_directory=folder,
                    runner_metrics={key: value for key, value in report.items() if key != "transcript"},
                )
                if report["model"] != config["model"] or report["effort"] != config["effort"]:
                    raise ValueError("runner changed the configured model or effort")
                usage = report["usage"]
                if any(type(usage[key]) is not int or usage[key] < 0 for key in ("input_tokens", "output_tokens")):
                    raise ValueError("runner must report actual nonnegative provider token usage")
                spent = usage["input_tokens"] + usage["output_tokens"]
                tokens += spent
                row["usage"] = usage
                if report.get("preflight_failed"):
                    raise ValueError("native sandbox cannot write workspace; no model requests made")
                if report.get("usage_complete") is False:
                    raise ValueError("runner usage is incomplete; stop rather than assume unreported tokens were free")
                if spent > remaining_tokens:
                    raise ValueError("runner exceeded the assigned remaining token budget")
                artifact = directory / "audio.npy"
                if artifact.stat().st_size > 64 * 1024 * 1024:
                    raise ValueError("artifact exceeds 64 MiB")
                actual = np.load(artifact, allow_pickle=False, mmap_mode="r")
                namespace = {}
                exec(compile(IMPORTS + task["python"], "<independent-oracle>", "exec"), namespace)
                expected = namespace["c"].audio
                bank_preserved = True
                if provided_bank is not None:
                    expected_bank = copy.deepcopy(provided_bank)
                    expected_bank["sounds"]["main"]["with" if route == "dsl_json" else "options"]["power"] = 0.8
                    bank_preserved = json.loads((directory / "bank.json").read_text()) == expected_bank
                row.update(
                    usage=usage,
                    tool_calls=report["tool_calls"],
                    repair_turns=report["repair_turns"],
                    transcript=report["transcript"],
                    bank_preserved=bank_preserved,
                    success=bank_preserved
                    and actual.shape == expected.shape
                    and np.array_equal(actual, expected)
                    and not report.get("route_violation", False),
                )
            except (ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
                row["error"] = str(exc)
                runner_messages = " ".join(row.get("runner_metrics", {}).get("messages", []))
                environment_blocked = row.get("runner_metrics", {}).get("preflight_failed", False) or any(
                    word in runner_messages.lower()
                    for word in (
                        "permissionerror",
                        "permission denied",
                        "writes returned",
                        "write denied",
                        "write access",
                        "writes are denied",
                        "read-only",
                        "writes were denied",
                    )
                )
                if environment_blocked:
                    row["failure_kind"] = "environment_write_denied"
                # Missing/invalid usage makes further budget accounting unsafe.
                results.append(row | {"seconds": time.monotonic() - begin})
                if (
                    environment_blocked
                    or "usage" not in row
                    or report.get("usage_complete") is False
                    or tokens >= config["max_total_tokens"]
                ):
                    break
                args.output.write_text(
                    json.dumps(
                        {
                            "config": config,
                            "results": results,
                            "tokens": tokens,
                            "seconds": time.monotonic() - started,
                            "complete": False,
                            "exploratory": args.exploratory,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                continue
            results.append(row | {"seconds": time.monotonic() - begin})
        args.output.write_text(
            json.dumps(
                {
                    "config": config,
                    "results": results,
                    "tokens": tokens,
                    "seconds": time.monotonic() - started,
                    "complete": len(results) == len(jobs),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    args.output.write_text(
        json.dumps(
            {
                "config": config,
                "results": results,
                "tokens": tokens,
                "seconds": time.monotonic() - started,
                "complete": len(results) == len(jobs),
                "exploratory": args.exploratory,
                "claim": "No automatic qualification; inspect paired success, tokens per success, failures and p90.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(str(args.output))


if __name__ == "__main__":
    main()
