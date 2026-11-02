# Why review continuations cost more, and how to reduce them

[Review guide](dsl-review.md) · [Retained evidence](dsl-review-token-analysis.json) · [Português](pt-BR/tokens-revisao-dsl.md)

The excess comes mainly from feedback serialization. Both routes execute the
requested sound operation; Python library work inside a tool does not itself
become model-context tokens. The review facade was returning a broad observation
after every edit, even when the next decision needed only a few measured results.

## What the original 30.4% figure measured

The [original replay](dsl-review-measurements.json) defined “warm continuation”
as **one edit, one deliberate stale-observation refusal, and optional MIDI**.
It was not a sequence of real edits. With `o200k_base`, the complete warm costs
were 858/586, 1,181/988 and 755/579 tokens for review/Python respectively. Their
median ratio was 1.304. This is an exact property of that recorded protocol,
not a general estimate for a long editing session.

Splitting those same payloads:

| Task | Review edit request / reply | Python edit request / reply | Extra warm traffic |
|---|---:|---:|---:|
| Voice refinement | 36 / 761 | 37 / 527 | 272 |
| Transposition | 41 / 1,010 | 26 / 887 | 193, including refusal and MIDI |
| Local bank edit | 31 / 668 | 29 / 528 | 176 |

Four sources account for the difference:

1. **Repeated context and acknowledgement.** Description, capabilities, schema,
   sound name, static freshness explanation and full edit acknowledgement add
   roughly 125–130 tokens per successful reply compared with the original helper.
   Actual affected-sound scope is useful; echoing the submitted target, mode and
   fields on every success is usually unnecessary.
2. **Structural source noise.** The first primitive refinement wraps the recipe
   in `edit`. A literal JSON diff describes removed/added fields when the recipe
   merely moved inside that wrapper. In the original voice case, the source-diff
   field alone cost about 99 tokens more than Python's simple override insertion.
3. **Full observations repeat large blocks.** Facts and approved-check rows cost
   roughly 290–490 tokens per reply in both routes. Track summaries appear in
   current facts and again in the before/after diff. These are major absolute
   costs, although they do not alone explain the review/Python difference.
4. **The validation exercise has its own cost.** Stale refusals consumed 56–66
   tokens in review and 22 in the original Python route, including requests.
   Review returns structured diagnostics, and the replay resubmitted the edit
   arguments. Between 34 and 44 excess tokens came from this deliberate failure.

These estimates use actual retained JSON. Field-removal marginals overlap because
tokenization is not additive; the evidence labels them accordingly. Full paths
and 64-character bundle IDs also cost roughly 75–85 tokens per reply in all arms.
They identify the observation required by the next edit and remain in CLI output.

## Implemented response optimization

The default detailed contract is unchanged. Opt into the existing compact response
convention for review and edit:

```bash
tare.tools.tune dsl review examples/dsl-bank.tune.json --name confirm -o output/reviews --response compact --json
tare.tools.tune dsl edit examples/dsl-bank.tune.json --from-bundle BUNDLE -o output/reviews --set /with/power 0.65 --response compact --json
```

```python
observed = review(path, name=name, output=folder, response="compact")
updated = edit_file(path, from_bundle=observed["bundle"], output=folder,
                    set_fields={"/with/power": 0.65}, response="compact")
```

The `tune.compact/1` profile retains:

- The bundle path, playable audio location, editability and any warnings.
- Actual duration, sample rate, channels and per-channel peak/RMS in dBFS, with
  full measured precision. Silence remains JSON null.
- Check status, names of approved checks, full failed/not-run rows and check
  coverage. Perceptual quality remains explicitly `not_run`.
- PCM change, nonzero duration delta, changed rate/channel/peak comparisons,
  structural source-change count and retained track before/after summaries.
- Applied/preview status and actual affected sounds/count, including truncation
  evidence when the count exceeds the returned names. Names are omitted when the
  only affected sound is the reviewed one; any wider impact keeps them.

It omits static prose/capability inventory, processing internals, repeated passed
check values, literal source-diff rows and repeated submitted edit arguments.
Current tracks are not duplicated when already present in the comparison. This
is an explicit summary profile; absence of a field is not proof that nothing
changed. Track truncation remains visible. Request a detailed review of the same
saved bundle, optionally with `previous=...`, for deeper evidence without
regeneration. Declared check specs remain in the saved manifest.

All checks still execute against the full candidate before source commit. Bundle
integrity, revision/materialization/code/asset guards, locks, backups and atomic
replacement are unchanged. Errors retain their codes and actionable details.
An unsupported response mode is rejected before rendering or mutation.

## Five actual edits, with both routes optimized

The new replay performs five alternating changes per task and verifies each
intermediate PCM artifact. The three routes are composed DSL services, the public
review facade, and direct Python with a counted reusable helper. Both control
helpers now reuse their updater and report commit/affected-sound acknowledgement.
Detailed and compact profiles are applied to **every route**. The same source,
render/check/backup contract and final documents are verified across profiles.

For the review facade, `o200k_base` content tokens after setup/observation/control
discovery, including the one deliberate stale refusal and optional MIDI:

| Task: five edits | Detailed | Compact | Reduction |
|---|---:|---:|---:|
| Voice refinement | 3,647 | 1,382 | 62.1% |
| Musical transposition + MIDI | 5,457 | 2,499 | 54.2% |
| One bank entry | 3,542 | 1,480 | 58.2% |

Median reduction: **58.2%**. Counting only productive edits and MIDI, excluding
the deliberate refusal, the median reduction is **59.4%**.

The equivalent optimized Python helper also benefits. Review/Python medians in
this five-edit protocol change from **1.213×** with detailed output to **1.070×**
with both compact. Excluding the deliberate validation error, the compact ratio
is **1.047×**. Most remaining excess is request spelling and the richer structured
failure; successful reply sizes are close. This still does not establish a
general advantage over Python. The original one-edit and new five-edit ratios
must not be presented as the same experimental cohort.

The action count is unchanged: nine calls for voice/bank, ten with MIDI. No
rendering/validation step was removed to obtain the reduction. These are executed
scripted traffic measurements, one execution per arm and two proxy tokenizers;
they exclude reasoning, system/tool envelopes and retransmitted model context.
No model/API calls were made. Per-action timings are retained but not used as
performance evidence; arms ran concurrently.

## Use this efficiently

Use compact feedback for ordinary iterations; ask for the relevant detailed
observation or existing inspector view when the next decision needs it. Discover
controls once and batch fields known from that observation. In a persistent
Python tool namespace, retain returned bundle paths in variables and bind fixed
source/output arguments once. Only advance to a successfully applied observation;
never refresh a conflict silently. The same techniques are available to Python
controls and should be counted for both.

For a persistent Python tool namespace, standard `functools.partial` avoids
repeating fixed arguments without introducing a new DSL helper or session service:

```python
from functools import partial
from tare.tools.tune.dsl import edit_file

apply = partial(edit_file, path, output=folder, response="compact")
updated = apply(from_bundle=observed["bundle"], refine={"/lowpass": 2400})
observed = updated  # advance after a successful applied edit; keep the old observation for previews
```

The third executed arm counts this binding, including the fixed definition target
for the musical task. The controls already bind their source/target in their
counted helpers. Across five edits, review edit requests fell from 220 to 150
tokens for voice, 245 to 135 for music, and 195 to 120 for the bank. Binding added
23–30 setup tokens, paid once per namespace.

| Five edits, compact with fixed arguments bound | Review warm tokens | Python warm tokens |
|---|---:|---:|
| Voice refinement | 1,343 | 1,307 |
| Musical transposition + MIDI | 2,371 | 2,343 |
| One bank entry | 1,393 | 1,398 |

The median ratio is **1.012×** including the deliberate stale refusal and
**1.003×** for productive edits/MIDI. Treat that as approximate parity in this
replay, not a language advantage: random bundle IDs and temporary path spelling
also cause small token differences. No retry or fresh revision lookup is hidden
inside the binding; each call still supplies the observed bundle explicitly.

A host that already retains and plays the bundle can keep its long artifact path
outside model-visible prose. That needs an explicit persistent-tool contract; the
CLI compact profile continues to return the full path. No handle registry,
session service, new language or general constraint system was added.

## Reproduce and verify

```bash
python tools/bench_review.py --edits 5 --response detailed --output output/review-detailed-five.json
python tools/bench_review.py --edits 5 --response compact --output output/review-compact-five.json
python tools/bench_review.py --edits 5 --response compact --bind-fixed --output output/review-compact-bound-five.json
python tools/analyze_review_tokens.py
```

The JSON evidence includes the original file hash, request/reply attribution,
offline payload ablations, all 27 executed arms and both token encodings. Initial,
intermediate and final float PCM, decoded PCM16, source scope, backups, stale
refusal and musical MIDI tick oracles passed. DSL regression suite: **173 passed**.
Tests cover default compatibility, identical bundle/audio across profiles,
repeated edits, dry runs, invalid profiles, silence, warnings, failed/not-run
checks and observation/edit context retained through generic field projection.
The wheel matches all 87 package Python modules and unchanged Studio HTML.
An isolated extracted-wheel process passed compact CLI/API edits, partial binding,
stale refusal, dry runs, failed-check rollback and detailed-response compatibility.
Wheel SHA-256:
`12003020a7c9eaa23b2a0ab565461619272c2a6a3b7d083eb0adc4c3767d4207`.

Source/tools identity:
`b54120075044af7573e68211cdbd759f168f8ca33c01f9d3433e565bc121746c`.
