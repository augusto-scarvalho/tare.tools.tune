"""Execute the frozen DSL corpus and count real content tokens, without model/API calls."""

import argparse
import importlib.metadata
import json
import math
import platform
import sys
from pathlib import Path

from dsl_bench_corpus import checkpoint

from tare.tools.tune.diagnostics import canonical, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("M1", "M2", "full"), default="full")
    parser.add_argument("--output", type=Path, default=Path("output/dsl-benchmark.json"))
    parser.add_argument("--v2", action="store_true", help="execute corrected semantic tasks with service parity")
    parser.add_argument("--workflow", choices=("control", "narrow"), default="control")
    parser.add_argument("--response", choices=("detailed", "compact"), default="detailed")
    parser.add_argument("--task", action="append", help="version-2 task ID or case name")
    parser.add_argument("--checkpoint", action="store_true", help="reproduce the superseded unpaired prototype")
    parser.add_argument(
        "--summary", type=Path, help="retain transcripts with hashes instead of large diagnostic ablations"
    )
    parser.add_argument(
        "--paired", action="store_true", help="execute matched multi-step tasks and output-policy ablations"
    )
    args = parser.parse_args()
    try:
        import tiktoken
    except ImportError:
        sys.exit("Install the bench extra: pip install -e '.[bench]'")
    if args.v2:
        from dsl_bench_v2 import checkpoint as checkpoint_v2
        from dsl_bench_v2 import metrics as metrics_v2

        result = checkpoint_v2(
            workflow=args.workflow,
            response=args.response,
            only=args.task,
            artifacts=args.output.parent / (args.output.stem + "-artifacts"),
        )
        metrics_v2(result, tiktoken)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(canonical(result) + b"\n")
        if args.summary:
            args.summary.parent.mkdir(parents=True, exist_ok=True)
            args.summary.write_bytes(canonical(result) + b"\n")
        failures = {
            name: {r: v["error"] for r, v in case["routes"].items() if not v["success"]}
            for name, case in result["cases"].items()
            if not all(v["success"] for v in case["routes"].values())
        }
        print(json.dumps({"output": str(args.output), "success": result["success"], "failures": failures}))
        if not result["success"]:
            sys.exit(1)
        return
    if args.paired or args.stage == "full" and not args.checkpoint:
        from dsl_bench_paired import paired_checkpoint

        result = paired_checkpoint()
        paired_metrics(result, tiktoken)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(canonical(result))
        if args.summary:
            import copy

            compact = copy.deepcopy(result)
            for task in compact["tasks"].values():
                for route in task["routes"].values():
                    for key in ("full_inspection", "compact_inspection"):
                        value = route.pop(key)
                        if value is not None:
                            route[key + "_identity"] = {"sha256": digest(value), "utf8_bytes": len(canonical(value))}
            compact["large_bank"]["ablation"] = {
                key: {"sha256": digest(value), "utf8_bytes": len(canonical(value))}
                for key, value in compact["large_bank"]["ablation"].items()
            }
            args.summary.write_bytes(canonical(compact) + b"\n")
        print(json.dumps({"output": str(args.output), "tasks": len(result["tasks"]), "success": result["success"]}))
        return
    result = checkpoint(args.stage)
    metrics = {}
    for encoding in ("cl100k_base", "o200k_base"):
        tokenizer = tiktoken.get_encoding(encoding)
        rows = {}
        for task, record in result["tasks"].items():
            rows[task] = {}
            for route, trace in record["transcripts"].items():
                counts = {}
                for part in ("request", "response"):
                    counts[part + "_tokens"] = sum(
                        len(
                            tokenizer.encode(
                                value if isinstance(value := turn[part], str) else canonical(value).decode()
                            )
                        )
                        for turn in trace
                    )
                rows[task][route] = counts | {"total_content_tokens": sum(counts.values()), "tool_calls": len(trace)}
        metrics[encoding] = rows
    source_root = Path(__file__).resolve().parents[1]
    source_id = digest(
        {
            str(path.relative_to(source_root)): digest(path.read_bytes().hex())
            for path in sorted((source_root / "src/tare/tools/tune").rglob("*.py"))
        }
    )
    result.update(
        kind="executed_scripted_corpus",
        stage=args.stage,
        metrics=metrics,
        environment={"python": platform.python_version(), "platform": platform.platform(), "source_id": source_id},
        tokenizer={
            "package": "tiktoken",
            "version": importlib.metadata.version("tiktoken"),
            "status": "proxy encodings; no model-specific savings claim",
        },
        limitations=[
            "Handwritten final Python solutions versus DSL construction and additional diagnostic transactions.",
            "Task paths have different operation counts; totals are not a task-success efficiency comparison.",
            "Content tokens exclude tool wrappers, system instructions and repeated model context.",
            "Persistent Python namespace within a task; fresh task namespaces; no live-agent quality judgments.",
            "Legacy format falls back to Python where it cannot express the task; identified per task.",
            "Absolute temporary paths and source provenance make small count variations possible.",
        ],
        release_status="experimental; live-agent qualification not run; token-efficiency target unproven",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(result))
    print(
        json.dumps(
            {
                "output": str(args.output),
                "tasks": result["task_count"],
                "pcm_equal": True,
                "release_status": result["release_status"],
            },
            indent=2,
        )
    )


def paired_metrics(result, tiktoken):
    import statistics

    result["tokenizers"] = {
        "package": "tiktoken",
        "version": importlib.metadata.version("tiktoken"),
        "kind": "two proxy encodings; no provider billing claim",
    }
    metrics = {}
    for encoding in ("cl100k_base", "o200k_base"):
        tokenizer = tiktoken.get_encoding(encoding)

        def count(value, tokenizer=tokenizer):
            return len(tokenizer.encode(value if isinstance(value, str) else canonical(value).decode()))

        rows, ratios = {}, []
        for task, task_result in result["tasks"].items():
            rows[task] = {}
            for route, run in task_result["routes"].items():
                context = count(result["primers"][route])
                unique, summed = context, 0
                phase_counts = {}
                for turn in run["turns"]:
                    request, response = (
                        count(turn["request"]) + count(turn.get("user_prompt", "")),
                        count(turn["response"]),
                    )
                    unique += request + response
                    summed += context + request + response
                    context += request + response
                    phase_counts[turn["phase"]] = phase_counts.get(turn["phase"], 0) + request + response
                row = {
                    "unique_content_tokens": unique,
                    "summed_context_tokens_simulated": summed,
                    "tool_calls": len(run["turns"]),
                    "repair_turns": sum(t["error"] for t in run["turns"]),
                    "phases": phase_counts,
                    "primer_tokens": count(result["primers"][route]),
                    "warm_no_primer_tokens": unique - count(result["primers"][route]),
                }
                if route == "dsl_json":
                    full, compact = count(run["full_inspection"]), count(run["compact_inspection"])
                    row["inspection_ablation"] = {
                        "full_tokens": full,
                        "compact_tokens": compact,
                        "reduction": 1 - compact / full,
                    }
                rows[task][route] = row
            better = min(rows[task][r]["unique_content_tokens"] for r in ("python", "project_json"))
            ratios.append(rows[task]["dsl_json"]["unique_content_tokens"] / better)
        metrics[encoding] = {
            "tasks": rows,
            "median_dsl_to_better_baseline": statistics.median(ratios),
            "unique_content_target_70pct_passed": statistics.median(ratios) <= 0.7,
            "p90_content_tokens": {
                route: sorted(rows[task][route]["unique_content_tokens"] for task in rows)[
                    max(0, math.ceil(0.9 * len(rows)) - 1)
                ]
                for route in ("python", "project_json", "dsl_json")
            },
        }
    result["metrics"] = metrics
    for encoding, metric in metrics.items():
        tokenizer = tiktoken.get_encoding(encoding)
        bank = result["large_bank"]

        def count(value, tokenizer=tokenizer):
            return len(tokenizer.encode(value if isinstance(value, str) else canonical(value).decode()))

        totals = {
            route: count(bank.get("instruction", ""))
            + sum(
                count(turn["request"]) + count(turn["response"]) + count(turn.get("user_prompt", ""))
                for turn in run["turns"]
            )
            for route, run in bank["routes"].items()
        }
        metric["large_bank"] = {
            "content_tokens": totals,
            "dsl_to_better_baseline": totals["dsl_json"] / min(totals["python"], totals["project_json"]),
            "ablation_tokens": {key: count(value) for key, value in bank["ablation"].items()},
        }
        metric["probes"] = {
            route: sum(
                count(turn["request"]) + count(turn["response"]) + count(turn.get("user_prompt", ""))
                for turn in run["turns"]
            )
            for route, run in result.get("probes", {}).items()
        }
        metric["builders_construction_only"] = {
            task: count(row["request"]) + count({"pcm_id": row["pcm_id"]})
            for task, row in result.get("builders", {}).items()
        }
    result["qualification"] = (
        "Scripted paired tasks only; live-agent task-success/billing qualification remains separate."
    )


if __name__ == "__main__":
    main()
