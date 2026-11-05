# Authoring implementation verification

Verified locally on October 31, 2026, against the corrected dependency order of an independent review (Astra, not published). Usage is in the [authoring guide](authoring.md); [Portuguese alternative](pt-BR/autoria.md).

## Delivered behavior

| Plan area | Implementation |
|---|---|
| Identities, stages, historical behavior | Separate source/render/PCM/playback/analysis identities; content-hashed assets; stage/factor manifests; frozen pre-refactor samples |
| Observational provenance | Recorded musical events, callable/generator execution once, source/JSON locations, original seeds, captured layer buffers |
| One-shot workflow | `capture`, immutable verified bundles, `inspect --json`, channel-aware band ranking, explicit raw-pitch uncertainty |
| Revisions/evaluations | Atomic publication with requested-generation guards, preserved historical audio, answer version preconditions, retained exact playbacks |
| Continuous authoring/curator | Clean background workers, content watcher, last-good recovery, revision selection, source lookup, reference/solo/mute, range notes, blind bundle comparisons |
| Composition/exports | Editable patterns, explicit MIDI subset with parsed verification, WAV/Vorbis sprites with sample coordinates, Howler adapter and Web Audio player |
| Optional DSP | Oversampled FM, loop-aware chorus, final-stage stereo-linked limiting, blind listening example generator; disabled by default |

## Automated checks

- Full Windows suite: **490 passed, 48 skipped**, 1180.67 seconds. Skips were native/Godot availability checks. A unique explicit `--basetemp` avoided an existing Windows pytest cleanup permission problem outside this repository.
- Final authoring/curator regression suite: **24 passed**. It covers frozen samples/capture equality, one-shot inputs, gain-frozen interventions, mono/stereo/empty/silence, band queries, genuine octaves, ambiguous chords, asset-content changes, loop projection, immutable integrity, stale publication, old tabs, concurrent saves, references, failed-edit recovery, independently parsed MIDI, unsupported/edited events, and encoded sprites. Three of these tests were added after the full-suite collection; focused checks also cover subsequent fixes.
- WSL native + actual headless Godot: **51 passed, no skips**, 503.17 seconds. This includes comparing three supported native voices to the independent frozen outputs, and the existing unsupported-feature checks. The Godot executable and extension were present and actually executed.
- Ruff: **all checks passed**. Vendored `native/godot/godot-cpp` is excluded; its source was not reformatted.
- Editable installation and wheel build succeeded. The wheel includes both HTML players and the package data. CLI capture, band inspection, MIDI export, Vorbis sprite export, and all three listening-round generators were exercised.

Windows commands (use a fresh directory for `--basetemp`):

```powershell
$testRun = Join-Path $env:TEMP ('tare-tune-check-' + [guid]::NewGuid().ToString('N'))
python -m pytest -q --basetemp $testRun --disable-warnings
python -m pytest -q tests/test_authoring.py tests/test_authoring_workflows.py tests/test_curate.py --basetemp ANOTHER_FRESH_DIRECTORY
ruff check .
python -m pip wheel . --no-deps -w output/wheels
```

Native/Godot command used in WSL (dependency and executable paths are specific to this machine):

```bash
PYTHONPATH=/tmp/tare-tune-native-check-20261031:$PWD/src \
TARE_TOOLS_TUNE_GODOT=~/tools/godot/Godot_v4.7.2-stable_linux.x86_64 \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python3 -m pytest -q tests/test_native.py tests/test_godot.py \
  --basetemp /tmp/tare-tune-native-complete-20261031 --disable-warnings
```

## Browser checks

Chromium was driven through the Playwright CLI. Verified range/stage selection, layer solo/mute, reference playback, exact-playback annotation persistence, previous/latest navigation, preservation of an unfinished old-revision draft across rebuilding, and source lookup. Desktop and 390-pixel layouts were inspected. Source summaries show the file, JSON location, and note/event; large synthesis parameters stay in the expandable technical report.

The browser test caught an actual codec difference: a 4800-frame Vorbis stream decoded to 4544 frames in Chromium while libsndfile retained all 4800. The exporter now adds 4096 trailing silent codec samples without moving clip coordinates; the player verifies coverage and falls back to WAV if necessary.

A zero-gap two-clip marker fixture then passed in Chromium: 16000 Hz Vorbis decoded to 7040 frames for 3200 content frames plus codec padding. At 48000 Hz playback, all four 100 ms loop cycles placed the left marker at frame 240 and the right marker at frame 4500, exactly their expected positions. Steady-cycle maximum difference was approximately `1.46e-11` after resampling startup. This checks the included player's exclusive endpoints and resampling behavior; it does not certify every browser/Howler configuration.

Local, ignored artifacts are under `output/playwright/`, including screenshots, the browser timing probe, test output, generated bundles, listening rounds, sprites, and the wheel. No game/reference recordings were uploaded.

## Deliberate limits

Raw F0 remains conservative and can be unavailable; it is not general polyphonic transcription. Shared effects do not have fabricated additive layer percentages. Preserved material guarantees playback/replay, not regeneration of arbitrary historical Python callables or missing banks. New effects are Python PCM/Score features rather than native Voice format additions. The limiter measures sample peaks, not intersample true peaks. Listening examples are available, but acoustic quality has **not** been approved by automated tests.
