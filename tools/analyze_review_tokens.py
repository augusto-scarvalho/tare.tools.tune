"""Attribute retained review traffic and compare executed response profiles locally."""

import argparse
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path

import tiktoken

from tare.tools.tune.diagnostics import canonical
from tare.tools.tune.dsl.responses import respond

ENCODINGS = ("cl100k_base", "o200k_base")
STATIC = ("description", "capabilities", "sound", "source_state")


def costs(record, tokenizer):
    def count(value):
        return len(tokenizer.encode(value if isinstance(value, str) else canonical(value).decode()))

    return {"request": count(record["request"]), "response": count(record["response"])}


def without(data, path):
    result = copy.deepcopy(data)
    node = result
    for key in path.split(".")[:-1]:
        if key not in node or not isinstance(node[key], dict):
            return result
        node = node[key]
    node.pop(path.split(".")[-1], None)
    return result


def attribution(baseline, tokenizer):
    def count(value):
        return len(tokenizer.encode(canonical(value).decode()))

    result = {}
    for task, routes in baseline["cases"].items():
        result[task] = {}
        for route, run in routes.items():
            rows = []
            for turn in run["turns"]:
                if turn["action"] in ("setup", "observe", "describe"):
                    continue
                row = {"action": turn["action"], **costs(turn, tokenizer)}
                response = turn["response"]
                if isinstance(response, dict):
                    row["field_removal_marginals"] = {
                        key: count(response) - count(without(response, key))
                        for key in list(response)
                        + ["facts.processing", "facts.tracks", "changes.source", "changes.tracks", "checks.results"]
                    }
                if turn["action"] == "edit":
                    slim = {k: v for k, v in response.items() if k not in STATIC}
                    checks = respond(response, "review", "compact")["checks"]
                    check_summary = dict(slim, checks=checks)
                    summary = respond(response, "review", "compact")
                    row["response_ablations"] = {
                        "detailed": count(response),
                        "without_static_context": count(slim),
                        "plus_passed_check_summary": count(check_summary),
                        "compact": count(summary),
                    }
                rows.append(row)
            result[task][route] = rows
    return result


def comparison(detailed, compact, encoding):
    result = {}
    for task in detailed["cases"]:
        result[task] = {}
        for route in detailed["cases"][task]:
            old = detailed["metrics"][encoding][task][route]
            new = compact["metrics"][encoding][task][route]
            old_case, new_case = detailed["cases"][task][route], compact["cases"][task][route]
            assert old_case["success"] and new_case["success"]
            assert old_case["edits"] == new_case["edits"]
            assert old_case["initial_source"] == new_case["initial_source"]
            # Guards include package provenance; both arms execute the same frozen package.
            assert old_case["final_source"] == new_case["final_source"]
            result[task][route] = {
                "edits": old_case["edits"],
                "detailed": old,
                "compact": new,
                "warm_reduction": 1 - new["warm_tokens"] / old["warm_tokens"],
                "productive_reduction": 1 - new["productive_tokens"] / old["productive_tokens"],
            }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=Path("docs/dsl-review-measurements.json"))
    parser.add_argument("--detailed", type=Path, default=Path("output/review-detailed-five.json"))
    parser.add_argument("--compact", type=Path, default=Path("output/review-compact-five.json"))
    parser.add_argument("--bound", type=Path, default=Path("output/review-compact-bound-five.json"))
    parser.add_argument("--output", type=Path, default=Path("docs/dsl-review-token-analysis.json"))
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_bytes())
    detailed, compact, bound = (json.loads(path.read_bytes()) for path in (args.detailed, args.compact, args.bound))
    assert (
        detailed["environment"]["source_id"] == compact["environment"]["source_id"] == bound["environment"]["source_id"]
    )
    result = {
        "protocol": "review-response-attribution/1",
        "baseline": str(args.baseline),
        "baseline_sha256": hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        "tokenizer_version": importlib.metadata.version("tiktoken"),
        "environment": compact["environment"],
        "method": [
            "Original recorded warm phase: edit, deliberate stale refusal, optional MIDI; not a repeated-edit study.",
            "Original-field removal is an offline payload ablation; marginals overlap and must not be summed.",
            "Executed comparison: five alternating edits, detailed/compact applied to all three routes.",
            "Controls reuse their authored updater and report the same commit/affected-sound acknowledgement.",
            "Bound arm counts functools.partial setup and explicitly passes each observed bundle; "
            "controls already bind paths in their helpers.",
            "All requests, helper code, output, deliberate failures and MIDI are retained and counted.",
            "Artifact/source/check/guard oracles run in each arm. No inference, billing or timing claim.",
        ],
        "attribution": {},
        "comparison": {},
        "binding": {},
        "executed": {"detailed": detailed, "compact": compact, "bound": bound},
    }
    for encoding in ENCODINGS:
        tokenizer = tiktoken.get_encoding(encoding)
        result["attribution"][encoding] = attribution(baseline, tokenizer)
        result["comparison"][encoding] = comparison(detailed, compact, encoding)
        result["binding"][encoding] = comparison(compact, bound, encoding)
    args.output.write_bytes(canonical(result) + b"\n")
    rows = result["comparison"]["o200k_base"]
    print(
        json.dumps(
            {
                "output": str(args.output),
                "cases": {
                    task: {
                        route: {
                            "before": r["detailed"]["warm_tokens"],
                            "after": r["compact"]["warm_tokens"],
                            "productive_before": r["detailed"]["productive_tokens"],
                            "productive_after": r["compact"]["productive_tokens"],
                        }
                        for route, r in routes.items()
                    }
                    for task, routes in rows.items()
                },
            }
        )
    )


if __name__ == "__main__":
    main()
