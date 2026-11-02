# DSL implementation and verification

Subsequent efficiency corrections, the compact response profile and version-2 validation are recorded in [DSL efficiency corrections](dsl-efficiency.md). Results below describe the original implementation release.

Implementation of the [reviewed Astra plan](plans/2026-10-31-dsl/PLAN.md), completed October 31–November 1, 2026. [Acceptance map](dsl-acceptance.md) · [Usage](dsl.md) · [Agent workflow](dsl-agent.md) · [Measurements](dsl-benchmarks.md) · [Portuguese](pt-BR/dsl.md).

The engineering scope M0–M7 is delivered. Version 1 remains **experimental**: complete scripted token totals favor a competent Python baseline, and the authorized live pilot was environment-blocked. General token savings and a stabilized language are not claimed.

## Delivered behavior

| Area | Implementation |
|---|---|
| Frozen compatibility | Independent legacy PCM/seeds/call boundaries; historical schema-1 bundle produced with the original source archive and replayed by current code |
| Semantic core | Strict versioned JSON, lexical typed definitions/parameters, registry examples/defaults, Sfx/Creature/Speaker/Cue/FM/assets |
| Music and primitives | Eight layer families, Voice bus, Notes/pattern/chord/degrees, explicit spans, deterministic transforms, separate clip calls and legacy seeds |
| Composition | Voice/Score/Cue/PCM nesting, capture schema 2, exact placement/gain/dtype behavior, child provenance, frozen-factor replay and cumulative resource preflight |
| Refinement and patches | Materialized guards, set/append/remove, Score/Cue paths, original/current layer and field lineage, bounded stale hints, revision/impact queries, backups and atomic replacement |
| Python authoring | Immutable builders, typed expression parameters, finite affine instrument templates, deterministic named randomness and explicit GM mapping |
| Integrations | CLI/player selection, declared/missing asset watching, last-good revisions/drafts, source navigation, MIDI/sprites, migration/freeze/variants and native-or-PCM boundaries |
| Measurement | Eight executed paired workflows, 128-sound bank, discovery/asset/error probes, two tokenizers, cold/warm/context accounting, bounded live runner with pre-inference sandbox probe |

Completion adds an enumerated [vocabulary](dsl-reference.json), nested field projection, independent/random timeline oracles, full scene comparisons, Score guard/expansion fixes and generated-capture/PCM/speech preflight. No DSP redesign, evaluator, persistent compiler cache, native DSL runtime or plugin framework was added.

## Verification

- Final complete Windows suite: **618 passed, 49 skipped in 1082.80 seconds (18:02)**. Native/Godot availability skips on Windows are covered by the actual WSL run below. This run used the final production source, including the Score guard, generated-capture, speech and header-first PCM fixes.
- Focused final DSL + existing authoring/workflow suites: **147 passed in 52.39 seconds**. The complete run above is authoritative for final source.
- Actual WSL native + headless Godot: **52 passed, zero skips, 179.93 seconds**. Native library/Godot executed, including the DSL-to-native Voice fixture. Subsequent changes concern DSL guards/metadata/budgets/IO preflight; engine/DSP source was unchanged.
- Ruff: all checks passed. Unrelated tools accidentally reformatted during development were restored byte-for-byte from the pre-completion snapshot; existing DSP was not broadly reformatted.
- Every catalog entry has a typed bounded example/defaults/capabilities and is prepared without DSP/asset access. Forty generated trees use an independent Fraction timeline. Final musical vectors include leading/trailing rests, chords, fractional pitches, held duration and retrograde.
- Manual current-API baselines exactly match creature/speech/Cue/local PCM/limiter scenes. Nested replay stays within `1e-7`; surviving captured buffers/limiter factors remain unchanged. All 32 Cue defaults were calibrated at 16 kHz with explicit higher part/note caps and unchanged memory/work ceilings; large Cues can exceed the default 1024-part budget.
- Eight final paired tasks plus bank/probes/builders succeeded with independent PCM checks. Requests/responses, source/corpus identities and timings are in [dsl-measurements.json](dsl-measurements.json). This is scripted evidence, not live-agent qualification.
- Real Playwright browser: refined crystal layer showed definition `hit`, original `/modal/1`, current `/modal/0` and refined `/modal/1/hardness`; solo/mute completed, console had no errors/warnings. Artifacts: local `output/playwright/dsl-completion/`. Previous browser coverage checked failed builds retaining audio, saved/unsaved evaluation revisions and Follow latest.
- CLI examples, strict MIDI parser/timing checks, exact-PCM migration and WAV/Vorbis sprites passed. Sprite export includes decoder/sample-coordinate validation; unsupported exports fail explicitly.
- Final wheel built successfully. All **20 DSL modules** and Studio HTML matched source byte-for-byte. Isolated `python -I` import from the extracted wheel rendered the example bank at 16 kHz (9,976 samples). Checked **112 documentation links and six JSON examples**. Wheel SHA256: `ec52155e1027edc832449d6e387d12ad15c443f74b0c06346af5ce189826c2f2`.
- The live pilot retained all seven failed sessions and actual usage. Its new no-model sandbox preflight and usage/deadline protocol have fake-CLI tests without inference.

## Reproduce

```powershell
$testRun = Join-Path $env:TEMP ('tare-tune-verify-' + [guid]::NewGuid().ToString('N'))
.venv/Scripts/python.exe -m pytest -q --basetemp $testRun --disable-warnings
.venv/Scripts/ruff.exe check .
.venv/Scripts/python.exe tools/dsl_reference.py --check
.venv/Scripts/python.exe tools/bench_dsl.py --paired --output output/dsl-completion-paired.json --summary docs/dsl-measurements.json
.venv/Scripts/python.exe -m pip wheel . --no-deps --wheel-dir output/dsl-wheel
```

Actual Linux engine command used the prepared dependencies and installed Godot (choose a fresh basetemp):

```text
wsl.exe --cd /mnt/c/<repo> --exec env PYTHONPATH=/tmp/tare-tune-native-check-20261031:/mnt/c/<repo>/src TARE_TOOLS_TUNE_GODOT=/home/<user>/tools/godot/Godot_v4.7.2-stable_linux.x86_64 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_native.py tests/test_godot.py --basetemp /tmp/tare-dsl-native-release-UNIQUE --disable-warnings
```

Local logs: `output/dsl-release-full.log`, `output/dsl-release-validation.log`, `output/dsl-completion-engines.log`, `output/dsl-release-benchmark.log`, `output/dsl-release-wheel.log`. [Historical bundle provenance](../tests/fixtures/dsl/historical-schema1/provenance.json) identifies its independent producer. Documentation-only edits do not require extra engine/full runs.

## Snapshots and release limits

Original M0 snapshot: `%TEMP%\tare-tune-before-dsl-wwxtl2_3\source.zip`, with adjacent SHA256 manifest. Completion snapshot: `%TEMP%\tare-dsl-completion-wzjlc96u\source.zip` and manifest. Independent fixture audio was preserved. This workspace has no Git metadata; no commit/remote publication was performed.

Targeted queries/inspections save output traffic, while complete DSL tasks currently cost more tokens than the Python helper. Live route success/efficiency remains unknown because sandbox writes failed; all attempts/costs are disclosed in the [live ledger](dsl-live-measurements.json). Grammar/default freeze, general efficiency and perceptual preference remain unqualified.
