# DSL efficiency corrections and version-2 evidence

[Correction plan](plans/2026-11-01-dsl-efficiency/PLAN.md) · [Agent workflow](dsl-agent.md) · [Portuguese companion](pt-BR/eficiencia-dsl.md) · [Historical measurements](dsl-benchmarks.md)

This correction separates protocol overhead, task procedure and semantic authoring. Version 1 remains experimental. The earlier 2.34x median describes its recorded generic procedure; it cannot serve as a before/after measure for a new task set or an equivalent-service claim.

## Delivered corrections

- A version-2 corpus performs the actions each instruction requests. Creation has no unrelated filter edit or injected error. Recovery cases actually fail, preserve last-good state and apply a different valid value. FM Voice export is actually attempted and refused. Initial and final PCM have independent existing-API oracles; musical events and MIDI note/tick vectors are checked independently; WAV decoding is compared to exact PCM16 quantization.
- Separate contracts cover in-memory recipe/document authoring and persisted revision-checked source. Persisted Python uses a fully counted helper with locks, backups, validation of the complete bank and atomic writes. Both routes get the same supplied inputs. Legacy project JSON is used by the persisted Python baseline; unsupported legacy scene syntax is not invented.
- Generated recipes are wrapped once for refinement. Later edits update existing override fields. Revisions and guards can stay in ordinary tool variables; no session service, public Session class or handle registry was introduced. Reuse a retained capture for inspection/export until a rebuild is requested.
- Existing builders express variants, arrangements and composition. Python can use functions/comprehensions. Imports and helpers used by each task are counted once; no bespoke helper is free for either route.
- An opt-in compact response profile removes redundant envelope fields. Detailed responses remain the default. Guard checks, full identities, backups, validation, limits, warnings and usable pagination remain in place.

The new production code is response serialization and CLI integration. Synthesis, native rendering, capture schemas and export sample conversion are unchanged.

## Response contract

```bash
tare.tools.tune dsl query examples/dsl-bank.tune.json --target sound:confirm_strong --fields fragment.with.power --response compact --json
tare.tools.tune inspect examples/dsl-bank.tune.json --name confirm --view layers --top 3 --fields id,power --no-pitch --response compact --json
tare.tools.tune dsl expand examples/dsl-bank.tune.json --name confirm --view layers --limit 3 --response compact --json
tare.tools.tune dsl patch bank.tune.json --patch edit.json --response compact --json
tare.tools.tune dsl freeze bank.tune.json --name confirm --format wav -o output/confirm.wav --response compact --json
```

`query`, `expand`, `patch`, `freeze` and root `inspect` accept `--response detailed|compact`. Their Python APIs accept the same `response=` keyword. Compact responses and structured DSL errors identify themselves as `tune.compact/1`; errors keep their codes/exit statuses and bounded recovery information. Unrelated generic/legacy IO errors retain their existing exit-1 stderr behavior. Detailed behavior and `tune.query/1` / `tune.error/1` remain available. An explicit `--view full --response compact` fails with `E_OPTION` before loading/rendering. Bare `inspect --response compact` selects summary; detailed bare inspection keeps its existing behavior.

| Operation | Information retained by compact mode |
|---|---|
| Authored query | Observed authored revision, selected target/pointer and requested fragment; bounded shared impact |
| Expansion | Full authored revision and materialized guard, paths/data and continuation when truncated |
| Inspection | Capture revision, selected stage/root scope, rows, effective window/band and the attribution caveat |
| Patch | New authored revision, changed targets, affected targets/count, dry-run marker when applicable; affected names are omitted when they only repeat changed sounds |
| Export | Output path, format, frames/sample rate, source capture revision, source PCM identity, regeneration boundary and nonempty warnings |
| Error | Code/message, pointer/target, suggestions and relevant stale/conflict details |

Absence of `truncated` means the compact result is complete. When it is true, retain `next` for row pagination or the bounded omitted/impact information for object responses. Cursors keep their original full query/revision binding and cannot be reused with a changed query. Field projection does not remove compact control fields needed for safe follow-up. Empty bookkeeping and redundant analysis/query identities are omitted; no hashes are shortened.

WAV export retains both source identity fields because a standalone WAV does not contain the complete capture provenance. Request a bundle for the full graph/arrays/source history. Compact export does not create a new provenance sidecar or silently claim that materialized audio is regenerable source.

## Use existing state without bypassing conflicts

In a persistent Python tool context, load/compile the selected source and keep its `authored_revision`, `materialized_id` and capture in variables. The actual guard acquisition and helper setup are part of the task, even if hashes are not printed to the model. Derive guards from that observed CompileResult, rather than expanding an arbitrary first layer just to obtain a hash.

Wrap the selected recipe once. An existing `set` entry for `/lowpass` is subsequently addressed by authored path `/set/~1lowpass`; adding another override preserves earlier entries. The benchmark's narrow workflow demonstrates both cases. It never nests another `edit` to change the same override. Generated layer paths still require review against the selected base; ambiguous structural changes use the explicit existing primitive/patch API.

Advance the observed revision only after a successful write. Reject stale revisions/materializations; do not substitute a newly queried value and retry. Reusing a capture means analyzing that retained revision, not claiming it reflects externally changed source/assets. A stateless CLI client still receives explicit identities; results from a persistent Python namespace are not labeled stateless CLI costs.

## Reproduce and interpret the comparison

```bash
pip install -e ".[bench]"
python tools/bench_dsl.py --v2 --workflow control --response detailed --output output/dsl-v2-final-control.json
python tools/bench_dsl.py --v2 --workflow narrow --response detailed --output output/dsl-v2-final-narrow.json
python tools/bench_dsl.py --v2 --workflow narrow --response compact --output output/dsl-v2-final-compact.json --summary docs/dsl-measurements-v2.json
```

The corpus has 17 paired cases: nine memory cases and eight persisted cases, including banks of 8/32/128 entries and 1/5/20 repeated edits. Each case records code sent to the persistent tool context, actual output/errors, helper setup, action acceptance, artifact identities, timings and allocation measurements. Supplied paths/input files are common inputs; their initial byte size is recorded. Editable DSL data/builders and Python recipes are retained in the transcript. WAV/MIDI/input artifacts are retained in local run directories named in the report.

The two existing `tiktoken` encodings measure content proxies, not provider billing. Common instructions/parameters, request code, responses, failures and setup are counted. Repeated-context arithmetic is explicitly simulated. Cold totals include construction/initial observation and helper setup. Warm continuation starts after bootstrap, includes requested inspections/edits/failures/export, and is reported only for tasks with edits. Repeated-edit rows also show total cost amortized over 1/5/20 writes. `tool_seconds` excludes independent acceptance-oracle work; total seconds and tracked peak allocations include the harness/oracles and are not process RSS.

The three final runs use the same corpus, builders, source version and acceptance. The first isolates the old verbose workflow, the second narrow edits/projection/state reuse, and the third changes response envelopes. Earlier P0/P1 checkpoints remain separate. There is no direct percentage-improvement claim against the old eight-task procedure.

[Final payloads](dsl-measurements-v2.json) · [Stage comparison](dsl-comparison-v2.json) · [Response-only ablation](dsl-response-measurements-v2.json)

Current `o200k_base` content ratios below compare DSL/Python. Values below 1 favor the DSL for that scope. Total includes cold setup; warm continuation applies only to the declared edit subset.

| Service | Variant | Total median ratio | Warm median ratio | Total p90: Python / DSL |
|---|---|---:|---:|---:|
| memory | control | 1.174x | 1.223x | 1511 / 1606 |
| persisted | control | 0.968x | 1.510x | 2388 / 3659 |
| memory | narrow | 1.174x | 1.223x | 1511 / 1606 |
| persisted | narrow | 0.881x | 1.168x | 2388 / 2643 |
| memory | compact | 1.174x | 1.223x | 1511 / 1606 |
| persisted | compact | 0.872x | 1.147x | 2388 / 2590 |

Warm p90 is also retained in the comparison record. The large repeated-edit cases are included in the persisted p90; they are not dropped when their overhead is unfavorable.

| Repeated writes | Python total | DSL total | Python per write, amortized | DSL per write, amortized |
|---|---:|---:|---:|---:|
| 1 | 664 | 541 | 664.0 | 541.0 |
| 5 | 1026 | 965 | 205.2 | 193.0 |
| 20 | 2388 | 2590 | 119.4 | 129.5 |

Response-only measurements on matched actual results:

| Command | Detailed tokens | Compact tokens | Reduction |
|---|---:|---:|---:|
| expand | 206 | 149 | 27.7% |
| freeze | 136 | 145 | -6.6% |
| inspect | 246 | 152 | 38.2% |
| patch | 129 | 72 | 44.2% |
| query | 107 | 99 | 7.5% |

The five-command median response reduction is **27.7%**; the 30% target was **not reached**. WAV export adds dimensions while retaining source identities, so its compact receipt is slightly larger. Do not assume compact mode beats an already carefully projected detailed result.

Use the service/continuation tables to choose the interface. General token efficiency and original 70%/50% targets remain unqualified; p90 and setup must accompany favorable median or warm results.

The original median-70%, bank-50% and p90 targets remain hypotheses until the appropriate matched results support them. A smaller inspection response is not proof of total-task savings. Scripted tasks do not measure an agent's discovery quality, reasoning or actual success distribution. No new model sessions or paid API calls were run for this correction; the previous environment-blocked live pilot remains a separate historical record.

## Verification and preserved evidence

- Final complete Windows suite: **636 passed, 49 skipped in 856.27 seconds (14:16)**. Full production source was frozen before this run; the final benchmark additionally validates its corrected example programs.
- Focused DSL/authoring compatibility run: **164 passed in 78.92 seconds**. The final protocol/response run passed **18 tests**; the added summary-scope check passed with all **eight response tests**. The full suite above includes these checks.
- All **17 pairs succeeded in each of three final variants** (102 route executions), with requested actions and initial/final PCM, WAV, MIDI and source-state assertions. Ordinary creation, invalid/stale preservation, actual export refusal and missing-asset recovery are exercised. The 1/5/20-write runs retain failures and setup.
- Ruff passed. The generated vocabulary remained current. The wheel includes all **21 DSL modules**, the changed root CLI and the unchanged Studio HTML; source bytes are checked against the archive. Isolated wheel import/CLI accepted compact queries. SHA256: `8e4df57aee9b25499f942a761b018741720fb6249b563f90ed24f1eda8982577`.
- Actual CLI query and inspection outputs were retained in local `output/dsl-v2-cli-query.json` and `output/dsl-v2-cli-inspect.json`. The compact/full-view conflict, warnings and stale-write statuses have CLI/API regression coverage.
- Native/Godot and browser jobs were not repeated: this correction changes response envelopes, workflow examples and benchmark accounting; DSP, engine code, serialized Voice/audio and Studio UI are unchanged. The original engine/browser evidence remains in the [original verification record](dsl-implementation.md).
- Local logs: `output/dsl-v2-release-full.log`, `output/dsl-v2-all-dsl.log`, `output/dsl-v2-protocol-final.log`, `output/dsl-v2-final-*.log`, `output/dsl-v2-wheel.log`. Final benchmark source identity: `0ae30fdf8a50b6b54f06a32a28882fde3d43f38a30fddae1af969d4c3a4dc756`.

The practical result is mixed: total persisted-workflow median favors the DSL after including helper setup, while memory authoring and the median warm continuation still favor Python. In the 20-write case, Python uses 2,388 content tokens and the DSL 2,590. The smaller interface is useful, but it does not justify a general token-efficiency claim or grammar/default stabilization.

The original `docs/dsl-measurements.json`, live ledger and version-1 corpus were preserved. Before this correction, the 198-file snapshot and SHA256 manifest were saved at the path recorded in local `output/dsl-efficiency-backup.json`. P0/P1 source checkpoints are `output/dsl-v2-p0-source.zip` and `output/dsl-v2-p1-source.zip`; their original reports are [control checkpoint](dsl-measurements-v2-control.json) and [narrow checkpoint](dsl-measurements-v2-narrow.json). The [approved correction plan](plans/2026-11-01-dsl-efficiency/PLAN.md) documents the intended order and scope.

## Follow-up: affected names in patch acknowledgements

A compact patch acknowledgement now omits `affected` names when they only repeat the changed sound targets; `affected_total` stays, and a definition change or truncated impact still lists names. Rerunning the persisted compact variant on the same corpus ([payloads](dsl-measurements-v2-affected.json)):

| Persisted, compact | Before | After |
|---|---:|---:|
| Total median DSL/Python | 0.872x | 0.859x |
| Warm median DSL/Python | 1.147x | 1.092x |
| DSL total p90 (Python 2,388) | 2,590 | 2,450 |
| 20 writes, DSL tokens per write (Python 119.4) | 129.5 | 122.5 |

Memory cases do not use patch acknowledgements and are unchanged. Python still wins long warm sessions; most of the remaining per-write difference is the `schema` label each compact acknowledgement carries. The review facade's five-edit ratio moved from 1.012x to 1.009x, within the run-to-run noise of bundle IDs and temporary paths, so no change is claimed there.
