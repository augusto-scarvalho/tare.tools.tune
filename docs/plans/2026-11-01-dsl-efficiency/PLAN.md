# DSL efficiency correction plan

Implementation and measured outcomes are recorded in the [version-2 report](../../dsl-efficiency.md). The proposal below is retained as the approved baseline.

Status: proposed implementation sequence, November 1, 2026. This document plans corrections; it does not report new implementation or measurements.

[Original Astra roadmap](../2026-10-31-dsl/PLAN.md) · [Current measurements](../../dsl-benchmarks.md) · [Recorded payloads](../../dsl-measurements.json) · [Portuguese companion](../../pt-BR/plano-correcao-dsl.md)

## 1. Outcome and scope

Make the existing semantic DSL economical to operate, and measure it against Python with equivalent responsibilities. Preserve its current audio, low-level access, provenance, validation and conflict protection. Implement the smallest corrections first; decide further work from measured residual costs.

There are three distinct questions:

1. Does the DSL produce the correct sound and reject invalid changes?
2. How much conversation does a particular tool interface require?
3. Does semantic reuse reduce the complete task cost against competent Python?

Existing correctness evidence primarily answers the first. The current scripted benchmark partially answers the second, with important procedure asymmetries. Its 2.34x median is valid for that recorded procedure; it is not an inherent cost multiplier of the language or a live-agent success result.

This correction does not introduce a textual DSL, a persistent session service, a handle registry, a new evaluator, a compiler cache or DSP changes. Existing Python APIs and immutable builders remain first-class authoring routes.

## 2. Confirmed diagnosis

The current single-recipe task has these `o200k_base` content counts, including shared instructions:

| Phase | Python | DSL |
|---|---:|---:|
| Construction | 113 | 127 |
| Inspection and target selection | 151 | 707 |
| Edit, intentional error and repair, including preparation | 295 | 711 |
| Export | 65 | 175 |
| Initial instructions | 59 | 71 |
| Total | 683 | 1,791 |

The initial abstraction is nearly equal in cost. Most excess is in protocol and interaction design:

- Inspection returns several full identities, pagination bookkeeping and explanatory metadata, while the Python route prints only requested rows. Its single-recipe response is 253 versus 71 tokens.
- `run_route()` replaces the whole guarded expression on subsequent edits. It computes a narrow `/set/~1lowpass` path but still submits root replacement. This repeats recipes and materialized guards unnecessarily.
- The generic procedure adds lowpass editing, an invalid value and repair to every task. Repair repeats the already valid value after a rejected edit, so it is often a no-op rather than a meaningful recovery.
- Some named task actions happen before recorded construction: the localized power patch and initial refinement/guard setup are prepared by the harness. The FM path does not perform the requested Voice-export refusal in its recorded task sequence. These mismatches must be corrected before interpreting task-level totals.
- Python's primary route retains mutable objects in memory. The DSL route retains a revision-checked file and performs additional source/expansion queries. They do not offer exactly the same service.
- Python already exposes semantic recipes, comprehensions, functions and Score helpers. JSON serialization alone does not establish a higher abstraction level.

The 128-sound bank comparison is closer to transactional parity: 716 DSL tokens versus 548 Python tokens. It remains a loss for the current DSL workflow, although smaller than the eight-task median. Existing reports and their payloads remain preserved as historical evidence.

## 3. Invariants

- Unchanged synthesis parameters must keep existing PCM, seeds, call grouping and Note timing. A convenience operation cannot regroup layers or replace separate child buses with one Voice bus.
- Authored revisions, materialized guards and capture revisions remain different identities. Full identities stay available internally and in detailed reports; no hash truncation to improve token counts.
- A write checks the revision associated with the user's observed source. A materialized edit checks its selected base. Never refresh a stale revision/guard and retry automatically.
- Keep locks, backups, atomic replacement, complete project validation, dependency policy and resource ceilings. Invalid edits and conflicts leave the last valid source/audio intact.
- Compact responses must reveal failures, warnings, capability losses, affected shared targets and truncation when relevant. Pagination must remain usable and bound to the exact query/revision.
- Source/primitive lineage, historical bundles and strict MIDI/native boundaries retain their current meaning. Diagnostic mute/solo remains different from rebuilding an edited source.
- No inference calls are part of planning or local correction tests. The prior 15-minute pilot authorization is spent; a future live batch needs a fresh explicit allowance.

## 4. P0: repair the experiment before changing the interface

Primary files: `tools/dsl_bench_paired.py`, `tools/dsl_bench_bank.py`, `tools/bench_dsl.py`, a new version-2 corpus under `tests/fixtures/dsl/bench/`, and `tests/test_dsl_benchmark_protocol.py`.

1. Preserve the current reports, original corpus and a source snapshot. Write version-2 results to a separate artifact such as `docs/dsl-measurements-v2.json`. Do not overwrite historical counts or silently rename the old protocol as corrected.
2. Define each task's requested actions and observable acceptance before writing route programs. Execute those actions in order through recorded public operations. Oracle construction and artifact checking stay outside model-visible traffic and must not perform the requested edit on the route's behalf.
3. Remove the mandatory generic filter/error/repair sequence. A creation task creates and exports; a refinement task refines the specified field; a capability task actually attempts the unsupported export; a recovery task deliberately fails, verifies preservation, then applies a different valid correction. Record robustness scenarios separately from ordinary use.
4. Make error cases comparable: same invalid intent, last-good-state guarantee and final result. For stale tests, construct both the accepted baseline and changed materialization consistently rather than comparing structurally different objects for unrelated reasons.
5. Record acquisition of required revisions/guards. If a counted reusable helper derives them internally, its code/setup is counted and equivalent helper access is allowed to Python. Nothing becomes free merely because it runs inside the benchmark harness.
6. Give both routes equally competent source: Python can retain reusable recipe functions/comprehensions; DSL can use builders, definitions, transforms and variants. Do not compare handwritten optimized Python against needlessly expanded DSL or vice versa.

Required comparison tracks:

| Track | Python responsibility | DSL responsibility |
|---|---|---|
| In-memory authoring | Retain editable recipe/program and current capture; validate before replacing valid state | Retain document/Project and current capture; validate before replacing valid state |
| Persisted transactional authoring | Retain editable source; revision check, lock, backup, validation, atomic replacement and recovery | The same responsibilities through existing DSL patch operations |

Use existing project JSON plus fully counted Python helpers where it represents the task. Where it cannot, count the complete trusted Python recipe/persistence helper or label that baseline unsupported. Do not invent a production persistence framework just to create a benchmark route. Retain legacy JSON as a reference where meaningful, with counted fallbacks.

For each track, report cold setup separately from warm continuation. Charge imports, helper definitions and initial source once; show amortized cost after 1, 5 and 20 requested edits for the reusable-edit subset. No free preinstalled bespoke helper for just one route. Direct CLI usage must also be exercised in focused command tests; a persistent Python helper result cannot be labeled a stateless CLI result.

**Gate:** each instruction has an executed-action assertion and independent artifact/state oracle. Removing a required step must fail acceptance. Every transcript identifies its service contract, setup, requests, responses, intentional failures and actual artifact result. Publish a corrected control run with the current response format before claiming an optimization win.

## 5. P1: remove unnecessary work using existing APIs

Primary files: the benchmark route helpers, `docs/dsl-agent.md`, `docs/pt-BR/dsl-agentes.md`, and focused query/patch/workflow tests.

- Reuse the observed authored revision from the loaded document/capture when it belongs to the exact selected source. Query again only if information is missing or there is a conflict requiring review.
- Compute materialized guards from the actual selected CompileResult when needed. A known bus edit does not require selecting an arbitrary generated layer or requesting a one-row page just to get the guard.
- Wrap a recipe once for guarded refinement. Subsequent edits update its existing `set` member through the exact authored pointer. Do not resend or nest the complete expression. Existing set entries and append/remove operations remain intact; ambiguous cases use the explicit existing API.
- Keep revisions/guards in ordinary variables inside the equally available persistent tool context. Use existing public APIs and a small fully counted helper. Do not add a public Session class, a daemon or sidecar session store in this correction.
- Keep the successful capture. Inspect and export it or its saved bundle until the source/dependencies change. Never claim lower tokens solely from avoiding a render; report token and compute effects separately.
- Use present field projection, stage/window filters and bounded rows consistently. Avoid discovery for already known recipe data, and count discovery for tasks that genuinely require it.

**Gate:** after initial wrapper creation, patch content grows with changed fields, not recipe size. A large recipe plus three field edits must not contain three full recipe copies in requests. Source/guard changes still conflict; rejected edits do not advance observed state. Report the corrected workflow with unchanged verbose responses to isolate this benefit.

## 6. P2: add one explicit compact response profile

Primary files: `src/tare/tools/tune/dsl/query.py`, `dsl/cli.py`, `dsl/migrate.py`, the root `cli.py` inspection entry point, plus query/CLI regression tests.

Add one opt-in `--response compact` profile and matching Python keyword. Preserve current output as `--response detailed` and as the default for compatibility. `--view` continues to select data; `--response` selects the envelope. Compact support initially covers authored queries, expansion, inspection, patch acknowledgements and export acknowledgements. Existing command/data schemas remain available.

Use a small centralized response adapter and a separately identified compact schema, for example `tune.compact/1`. It transforms already computed results; it must not weaken validation or change the underlying operation.

| Response | Required compact information |
|---|---|
| Authored query | Selected target/pointer, requested fragment and authored revision; shared-definition impact when relevant |
| Materialized expansion | Authored revision, base materialized guard, requested paths/fields, actual truncation/continuation |
| Inspection | Capture revision, selected stage, requested rows; effective window/band when defaulting or clamping changes the request; truncation/continuation and applicable attribution caveat |
| Patch acknowledgement | Success/new authored revision, changed targets and bounded shared-impact/warnings |
| Export acknowledgement | Output location, format and essential audio dimensions; warnings/capability loss; detailed provenance retained with the artifact |
| Error | Code, useful message, exact target/pointer and bounded recovery details; conflict remains explicit |

Omit redundant analysis/query identities, empty bookkeeping and repeated descriptions where they are not required for the next safe operation. Do not remove the only version reference a caller needs. Retain full pagination validation internally; a compact cursor must work with the same query/revision. Do not introduce a new cursor codec or shorten hashes in this pass. An explicit `--view full` remains detailed; reject a contradictory compact/full request clearly.

Identities held in tool variables are still used for checks even when they are not printed. On mutation success, advance only to the revision returned by that mutation. On error, preserve the previous binding. The direct CLI must retain enough explicit identity for standalone follow-up operations.

**Gate:** detailed output remains compatible; compact and detailed calls refer to identical artifacts/targets; every stale/error/warning/truncation case remains actionable. Aim for at least 30% lower median response tokens across predeclared focused commands. Treat the number as a measured target, not permission to drop required evidence. Attribute envelope savings separately from workflow changes.

## 7. P3: measure actual semantic leverage

Use the corrected tracks with independent current-API PCM, event/MIDI and source-state oracles:

| Task family | Required behavior |
|---|---|
| Small semantic recipe | Create/export one sound with no unrelated refinement or synthetic error |
| Variants | Create deterministic takes, then change one shared parameter while preserving explicit takes |
| Reusable arrangement | Reuse a motif with held notes/trailing rests, transpose one clip and export valid MIDI |
| Local bank edit | Banks of 8, 32 and 128 entries; change one invocation and preserve unrelated source |
| Shared-definition change | Change a definition, report its affected invocations and preserve unrelated definitions |
| Primitive refinement | Refine one generated field, make another narrow edit, then test a real stale base without retargeting |
| Composition | Creature/speech/Cue/local PCM with correct child buses and capability boundaries |
| Recovery | Dedicated invalid-value, missing-asset, unsupported-export and stale-revision scenarios |

Use short, bounded fixtures and retain actual outputs. Increase reuse within existing budgets; do not raise safety limits just to make the DSL appear favorable. Python may use functions, loops and comprehensions. DSL may use existing builders/definitions/transforms/variants. Measure both initial representation and subsequent operations.

Publish three ablations on identical version-2 tasks: corrected procedure with detailed output; corrected procedure with compact output; compact output with equally counted reusable helper/state management. Avoid a large combinatorial benchmark framework.

The report must separate source size, model-visible request tokens, response tokens, setup, errors/repairs, tool calls, local time and tracked allocations. Use both existing real tokenizers. Label repeated-context arithmetic as simulated, cached usage only when observed, and local content counts as proxies rather than provider billing. Report medians and p90 by service contract and cold/warm condition; never mix them into one favorable headline. Preserve unsuccessful tasks and their costs.

**Gate:** all required actions/artifacts succeed before making a savings claim. A practical improvement claim requires a matched version-2 control and explicit scope. A recommendation that the DSL saves total tokens over Python requires median and p90 at most the equivalent baseline in that declared task family. The original 70%-of-baseline and 50%-bank-saving targets remain unachieved hypotheses until demonstrated. If Python still wins, publish that result and keep the hybrid workflow; do not add syntax to force a passing number.

## 8. P4: regression, packaging and documentation

1. Run focused benchmark-protocol, query, patch, refinement and authoring/workflow tests after their changes. Test actual CLI serialization as well as direct API helpers.
2. Verify detailed output compatibility and compact conflict/truncation/warning behavior. Preserve the independent legacy PCM/schema-1 fixtures and schema-2 replay.
3. Once production code is frozen, run one full suite and Ruff. Rebuild/inspect the wheel and execute documented examples from an isolated import. The previous full run was 618 passed/49 skipped in 18:02; it is a historical reference, not a result for changed code.
4. Repeat real native/Godot jobs only if an export/synthesis/capture change touches their contract. Repeat browser QA only if Studio integration changes. Response formatting alone does not justify those expensive reruns.
5. Update primary English guides first, then pt-BR companions, acceptance status and the new measurement report. Keep the original Astra plan and old reports intact, and label the old ratio with its measured procedure limitations.

No new live pilot is required to complete these local corrections. Before proposing one, the existing no-model sandbox preflight must pass in the actual task directory and environment. A new live run requires a fresh user-approved time/quota allowance, includes all failures and stops on preflight/accounting failure. There is no automatic return to the 72-session design.

## 9. Order and completion criteria

`P0 → P1 → P2 → P3 → P4`

Save checkpoints after P0 and P1 so improvements can be attributed. Do not begin a new authoring framework before those cheaper fixes are measured. No sub-agent or external audit is required by this plan.

The correction is complete when task semantics and service parity are explicit; repeated-expression/query waste is removed; compact responses preserve required evidence; comparisons are reproducible with independent artifacts; compatibility/package checks pass; and the docs state the measured outcome without promising an unsupported savings rate. A favorable token result is desirable, but an honest unfavorable result is preferable to a distorted benchmark.
