# Audio review loop: implementation and local evidence

[Usage](dsl-review.md) · [Executed payloads](dsl-review-measurements.json) · [Português](pt-BR/revisao-dsl.md)

This implements the first bounded adaptation from the PXL study: a coherent
audio observation/edit loop using existing capture bundles and transactions.
It adds no synthesizer, textual language, project evaluator, server or parallel
revision store. The generated JSON remains the authoring source of truth.

This record describes the initial detailed-response delivery. The subsequent
[continuation analysis and opt-in compact profile](dsl-review-token-costs.md)
preserve its measurements and add a controlled five-edit comparison.

## Delivered behavior

| Area | Implementation |
|---|---|
| Observation | `dsl review` renders one selection, saves its existing bundle and returns playable audio, measured facts, capabilities and declared checks. Retained bundles can be reviewed without regeneration. |
| Comparison | Explicit previous bundle; PCM identity, measured levels/duration, bounded source differences and retained track timing/pitches. |
| Selected controls | `dsl describe`, exact field selection, authored names search with bounded pages, parameter/default paths, definition impact, layer paths and allowed scopes. |
| Transaction | `dsl edit` batches authored fields or root Voice refinement. The candidate renders/checks before backup and atomic source replacement under the existing source lock. |
| Guards | Saved-bundle integrity, observed source revision, compiler/renderer identity, materialized identity and dependency hashes; outside writes are checked again after candidate preparation. |
| Primitive escape hatch | Recipe-preserving guarded wrappers, original layer paths after removals; explicit refusal for appended/non-root refinement. Existing expansion/patch APIs cover remaining scopes. |
| Checks | Separate `tare.tools.tune.checks` v1 data: duration, channel peaks, sample rate, channels and required export support; explicit not-requested/not-run coverage. |
| Discovery/builders | Five progressive help topics; consistent `builders as t`; previously missing top-level `creature` export corrected. |

Source reviews with failed requested checks remain observations that can be
corrected. Failed edit candidates and dry runs are read-only. Check failure exits
5; source/dependency conflicts retain exit 3. All-source compilation validation
does not imply all-source acoustic checking: only the selected sound is rendered.

Family/variant sugar remains deferred: existing typed definitions, builders and
`dsl variants` already provide reuse. This measurement does not justify another
authoring abstraction. Generated acoustic-role metadata, Python-primary source
mapping and a general constraint solver are also outside this slice.

## Verification

- DSL-focused suite: **163 passed**.
- Full repository suite: **656 passed, 49 skipped** in 819.79 seconds. The skipped
  native/Godot cases require a configured engine and built native artifacts.
- Ruff passed; the generated vocabulary matches its checked-in reference.
- Nine executed workflow arms (three tasks × three routes) passed independent
  initial/final float PCM, decoded PCM16, source scope, backup and stale-observation
  oracles. Musical transposition also passed independent literal MIDI tick checks.
- The wheel includes all **25 DSL modules**, every package Python source and the
  unchanged Studio HTML byte-for-byte. An isolated extracted-wheel process passed
  help, review, describe, edit, inherited checks, stale refusal, dry-run and failed
  candidate checks without importing the working source tree.
- Existing fixtures, earlier v1/v2 measurements, synthesis modules and Studio
  assets retained their pre-change snapshot hashes. The four changed existing
  package files are DSL exports, DSL CLI registration, diagnostic exit mapping and
  the existing patch transaction's internal preparation hooks. Four new DSL
  modules contain the workflow, affordances, fact/check projection and CLI facade.

The new tests additionally cover deleted source with retained observations,
changed assets/reference/renderer, failed render, an external source writer during
preparation, missing invocation parents, shared impact, repeated refinement,
original paths after removals, appended-layer refusal, tampered bundle metadata,
invalid check files, silent peaks and CLI error contracts.

Native/Godot engines and serialized Voice contracts were not changed. Their
earlier results are historical; this slice's audio equivalence is established by
the Python PCM/MIDI oracles and repository suite, not a new native-engine run.

## Token traffic: integration savings, larger warm replies

Run from the source checkout with the development/tokenizer extras installed:

```bash
python tools/bench_review.py --output docs/dsl-review-measurements.json
```

The supplied persisted tasks are: refine one confirmation, transpose a shared
musical motif while retaining rests/MIDI, and change one invocation in a
128-sound bank. Each route observes/playbacks a bundle, reads a selected control,
trial-checks and persists the edit, retains a backup and rejects a stale edit.
MIDI export adds one action to the music case.

The controls compose existing DSL services or direct Python audio APIs with the
same fully counted, fixture-scoped transaction helper. The new route uses the
public review facade. All sent setup/helper code and actual responses are
retained. Inputs and file paths are provisioned to all arms. This compares API
composition in persistent Python tool namespaces; it is not a stateless CLI
benchmark or a universal language comparison. The facade returns richer control
descriptors, capabilities and edit acknowledgement metadata than the controls.

For `o200k_base`, total content tokens including setup:

| Task | Composed DSL services | Review facade | Direct Python with helper |
|---|---:|---:|---:|
| Voice refinement | 1,806 | 1,578 | 1,650 |
| Musical transposition + MIDI | 2,232 | 2,011 | 2,306 |
| Local edit in 128-sound bank | 1,619 | 1,484 | 1,653 |

The facade's median total is **0.898× Python** (about 10.2% lower) and
**0.901× composed DSL services**. Its import/setup costs 31 tokens, versus
607–698 tokens of sent integration code in the controls. This is the benefit of
shipping the reusable workflow inside the library.

After setup, observation and control discovery, the warm continuation includes
the edit, stale refusal and any MIDI export:

| Task | Composed DSL services | Review facade | Direct Python with helper |
|---|---:|---:|---:|
| Voice refinement | 766 | 858 | 586 |
| Musical transposition + MIDI | 996 | 1,181 | 988 |
| Local edit in 128-sound bank | 583 | 755 | 579 |

The facade's median warm cost is **1.304× Python**. Its small requests are
outweighed by richer responses: facts/checks are included again with changes,
capabilities and acknowledgements. Thus this implementation improves initial
integration while leaving an explicit response-projection opportunity for long
editing sessions. It does not establish a general token advantage over an
already loaded competent helper.

All routes used five recorded actions per voice/bank task and six per music task;
this replay does not demonstrate fewer interactions. The second proxy encoding,
exact requests/responses, per-action timing, source documents and source identity
are in the JSON evidence. A single execution per arm does not establish runtime
performance or agent task-solving success. System/tool envelopes, reasoning,
context retransmission, listening quality and billed usage were not measured.
No inference quota, paid API or new live-agent pilot was used.

Source/tools identity:
`2c78f2758cbdab3747709eb7a0a7e439056c7704bc50c079e8a34cdff7eda147`.

Verified wheel SHA-256:
`e320a3f6b01018400ba6ebe69a8bdeb5d4f3ee2717130b3ca5692ebda0968f29`.
