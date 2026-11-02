# DSL token measurements and evaluation protocol

**Historical version-1 procedure.** See [version-2 corrections and evidence](dsl-efficiency.md) for equivalent service contracts, task-specific actions, narrow edits and the opt-in compact envelope. The original counts and payload record below are preserved.

[Agent workflow](dsl-agent.md) · [Language guide](dsl.md) · [Acceptance map](dsl-acceptance.md) · [Portuguese](pt-BR/dsl-agentes.md)

**Experimental. Complete scripted workflows do not meet the token-saving targets. The authorized live pilot is inconclusive because its sandbox prevented artifact writes.** Correctness and smaller query output are measured separately from task-solving efficiency.

The [efficiency correction plan](plans/2026-11-01-dsl-efficiency/PLAN.md) records a subsequent payload audit: generic extra steps, repeated recipe replacement, preparatory actions outside the recorded workflow, and in-memory versus persisted-service differences limit interpretation of the 2.34x ratio. The tables below remain the historical measurements of that procedure; a corrected comparison must use a separate version-2 report.

## Reproduce the executed comparison

```bash
pip install -e ".[bench]"
python tools/dsl_reference.py --check
python tools/bench_dsl.py --paired --output output/dsl-completion-paired.json --summary docs/dsl-measurements.json
```

The [measurement record](dsl-measurements.json) retains actual requests/responses, phase counts, source/corpus identities, package versions, PCM identities and timings. Full local output also retains large inspection ablations. `--stage M1|M2` preserves early checkpoints; `--checkpoint` explicitly selects the superseded unpaired full prototype. The older [checkpoint record](dsl-benchmark-results.json) is historical.

Eight tasks cover a single recipe, four variants, creature/speech composition, repeated music, guarded primitive refinement, localized editing, invalid input/repair and capability refusal/WAV export. Each route executes construction, top-three inspection, refinement, invalid edit, repair and export. The refinement case also exercises a stale guard. Independent existing-API programs provide PCM oracles. Additional probes cover ambiguous discovery, missing-asset recovery and raw primitive unit errors. A separate **128-sound preexisting bank** measures localized editing, invalid input/repair and stale revisions, asserting that unrelated entries remain unchanged.

Python uses minimal imports and persistent variables within each task; each task starts fresh. The old JSON format uses its counted Python fallback where needed. The bank baseline uses a reusable transactional helper with existing lock/atomic-write APIs. The DSL retains source on disk and uses scoped commands. Decisions are scripted. These routes have different representations and validation overhead; they provide an engineering comparison, not live success-rate estimates.

## Results

The current `o200k_base` content-token measurements appear below. Both it and `cl100k_base` are real `tiktoken` encodings used as proxies, not model billing estimates. Counts include shared phase instructions, requests, responses, primers, failures and repairs. The record separates cold primer and warm-without-primer counts. Repeated-context totals are explicitly **simulated** from retained messages; they omit provider/system/tool framing and model reasoning.

| Task | Python | Old JSON / fallback | DSL |
|---|---:|---:|---:|
| arrangement | 684 | 775 | 1382 |
| capability-export | 679 | 694 | 1270 |
| creature-speech-scene | 706 | 711 | 1346 |
| four-variants | 717 | 722 | 1477 |
| high-low-refinement | 782 | 787 | 2342 |
| invalid-repair | 672 | 677 | 1795 |
| localized-bank-edit | 682 | 687 | 1854 |
| single-recipe | 683 | 724 | 1791 |

Median per-task DSL / better baseline: **2.34x**. p90 content tokens: Python **782**, DSL **2342**.

The complete 128-sound bank edit/error/repair/stale workflow used **716 DSL tokens vs 548 Python tokens**. Its targeted query response used **61 tokens vs 3568 for the full source (98.3% less output)**.

| Inspection output only | Compact | Full | Reduction |
|---|---:|---:|---:|
| arrangement | 212 | 9789 | 97.8% |
| creature-speech-scene | 236 | 20879 | 98.9% |
| capability-export | 210 | 633 | 66.8% |

The targets are median successful-task tokens at most 70% of the better baseline, at least 50% savings for large-bank edits, p90 no worse and no material success regression. Scripted total-token targets fail. Keep version 1 experimental and the existing Python API available.

Useful savings come from requesting less irrelevant evidence: targeted source queries, nested field projection, bounded layer rows, stage/window selection and saved capture bundles. These are output ablations, not savings relative to a competent Python helper. Builder counts cover construction only. Timings are local tool-call wall times; `tracemalloc` measures tracked allocations, not process peak RSS. Exact PCM does not imply subjective listening approval.

## Authorized Codex pilot

The user authorized a smaller pilot on existing Codex quota, **up to 15 minutes, with no paid API**. The [live ledger](dsl-live-measurements.json) records every attempt, including failures. Seven fresh CLI sessions requested `gpt-6.1-sol`, effort `xhigh`, through ChatGPT authentication; the backend snapshot was not independently reported. Execution finished within the authorized window. No API key or paid API route was used.

The initial session had commands rejected by the native Windows sandbox. A scoped `workspace-write` retry still received `PermissionError` saving project/audio artifacts. All seven failed independent artifact validation. A later **no-model** write/read/unlink probe under the same sandbox also failed. Reported in-memory checks cannot replace artifacts checked by the harness. No route efficiency or success-rate conclusion is supported.

Actual CLI-reported usage: **1,986,316 input tokens**, including **1,746,432 cached input tokens**, and **24,884 output tokens**. Cached input is already part of input. The ledger reports 2,011,200 input-plus-output tokens, without assigning dollars or quota-unit prices. Command counts include completed `command_execution` items and exclude other tool kinds and requests denied before item creation.

`tools/codex_dsl_runner.py` now runs the same-sandbox task-directory write/read/unlink preflight **before inference**. A denied probe returns zero provider requests, and the parent stops the batch. Fake-CLI tests verify this without quota. No ACL widening or full-access bypass was used. No further inference sessions were launched.

## Future evaluation, only with a new explicit budget

```bash
python tools/pilot_dsl.py --config my-pilot.json --plan-only
```

The [example config](../tests/fixtures/dsl/bench/pilot.example.json) is illustrative, not authorization. The full design is eight tasks × three routes × three repetitions (72 sessions). `--exploratory` permits a smaller single-repetition batch, and `--task` filters tasks. Runs/traces remain in `output/pilot-*`. Include the realistic bank case and inspect route compliance, requested edits and non-PCM exports as well as audio.

The runner receives JSON with task/route/model/effort, scoped workspace, output `.npy`, remaining token allowance and deadline. It returns actual completed-turn usage, cached usage separately, transcript and failure state. The parent independently checks float PCM and retains failures. Wall-clock/process-tree limits are hard; the CLI adapter reports usage after a turn, so its token allowance is **soft** and can be exceeded within one turn. Missing/incomplete usage stops the comparison. This adapter does not promise a hard provider token ceiling.

Hold inputs, model snapshot, effort and tool availability constant; randomize route order; count all messages, failures and repairs; publish successful tasks, tokens per success, waste, time, memory, p90 and task-level uncertainty. Fix and verify the sandbox before spending any new inference quota. Current evidence supports experimental status.
