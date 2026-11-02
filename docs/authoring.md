# Authoring, inspection, and revisions

English is the primary reference. [Português brasileiro (alternative)](pt-BR/autoria.md).

## Use the live player

```bash
pip install -e ".[dev,export]"
tare.tools.tune studio examples/authoring.json -o authoring-out
# Equivalent: python -m tare.tools.tune studio examples/authoring.json -o authoring-out
```

Open the printed localhost URL. Save an edit to the JSON project, choose a sound if the project has a `sounds` map, and listen to the completed revision. Builds run in clean Python subprocesses with a 120-second timeout. File contents, referenced recordings, used voice banks, and package Python files are watched; output directories are not scanned. Package edits are loaded by the next worker. Restart the server after changing its HTTP/UI logic.

Use **Previous revision** to compare history and **Follow latest** to return. Unfinished notes keep the current revision selected when a new build arrives. Notes remain in the browser while switching revisions; use **Save evaluation** to persist them before closing the page. Concurrent saves report a conflict instead of silently overwriting. Failed builds retain the last successful audio. Builds for superseded requests may remain archived but cannot become current. Rebuilding the selected sound takes priority over queued stale requests; other sounds are built when selected.

Drag on the spectrogram or enter a time and frequency range with the keyboard. Choose **Measured stage** to compare layers from the same bus, then inspect the region. **Solo layer** and **Mute layer** replay captured material with frozen normalization and time support. Shared effects still process the surviving material; this is diagnostic intervention, not a fresh independently normalized instrument render. The full technical report retains source/event locations, planned notes, captured parameters, and gain stages.

Add a top-level `"reference": {"file": "reference.wav"}` to retain a reference recording. Stereo is preserved. Reference audio, diagnostic playbacks, revision IDs, range annotations, playback speed/volume, and listening settings remain local. The server binds to `127.0.0.1`. It does not execute project files as Python.

## Capture and inspect once

```python
from tare.tools.tune import Creature, capture
from tare.tools.tune.bundles import save_bundle, load_bundle
from tare.tools.tune.inspection import inspect_capture

observed = capture(Creature("mammal", species=31).voice("attack"), 16000)
path = save_bundle(observed, "authoring-out/bundles")
frozen = load_bundle(path)
report = inspect_capture(frozen, start=0.05, end=0.15, band=(1000, 4000))
diagnostic = frozen.replay(mute=[report["layer_catalog"][0]["id"]])
```

`capture` accepts `Voice`, `Score`, `Cue`, and finite mono/stereo sample arrays. Scores/Cues use their own sample rate. `loop` is a Score duration in seconds. `Limits(seconds=180, layers=1024, bytes=256*1024*1024)` bounds capture, including retained stems; the inspector accepts at most 180 seconds. PCM arrays without recipes have unknown provenance. Default rendering is still `legacy-1`; diagnostics have schema 1 and do not change Voice feature versions 6–8.

```bash
tare.tools.tune capture examples/authoring.json -o authoring-out/bundles
tare.tools.tune inspect authoring-out/bundles/REVISION --json --no-pitch
tare.tools.tune inspect examples/authoring.json --json --start 0.1 --end 0.3 --band 1000 4000 --node n1
tare.tools.tune inspect recording.wav --json
```

`inspect` accepts a bundle directory, a Voice JSON spec, a project JSON, or audio readable by the WAV reader. Install `.[export]` for soundfile-supported formats. `--name` chooses a bank entry. JSON reports contain `analyzer`, `analysis_id`, PCM identity, channel levels, absolute duration/times, query power, raw `fundamental.frames`, and, for bundles, revision/provenance, `layers`, `layer_catalog`, `selected_stage`, and `stages`. Values are finite; undefined dB/F0 values are `null`. Empty, short, silent, ambiguous, and unvoiced inputs are explicit. F0 is a conservative monophonic estimate, not a solution to general polyphonic pitch tracking. Frame `dominant_partial_hz` is a spectral peak, not the fundamental; planned notes are separate under `planned`.

`layers` ranks only the selected stage; `layer_catalog` includes IDs from every stage for solo/mute. Queries project material through placement, loop wrapping, and cue fades into the final timeline. Shared filtering/nonlinearity/reverb is excluded from per-layer spectra. No additive percentage attribution is promised. A boundary sample step is a measurement, not proof of an audible click.

Bundles contain `manifest.json`, `buffers.npz` (no pickled objects), and the exact `audio.wav`. Loading checks file, buffer, PCM, and provenance identities. `current.json` is the atomic current pointer; `revisions/`, `answers/`, and `playbacks/` retain immutable sound history and versioned evaluations. Historical audio can be replayed without instrument callables or external banks. Full source regeneration is explicitly not guaranteed. There is no automatic deletion policy.

## Editable patterns and MIDI

`examples/authoring.json` demonstrates a three-beat bar with harp and marimba. Supported project source types are `voice`, `creature`, `sfx`, `speech`, `music`, `score`, `audio`, and `fm`. A multi-sound project uses `sounds` instead of `source`; see `examples/sound-bank.json`. References and imported files resolve relative to the project.

```python
from tare.tools.tune.patterns import parse_pattern
from tare.tools.tune.score import Score
from tare.tools.tune.midi_export import export_midi

score = Score(bpm=120, meter=3)
notes, beats = parse_pattern("C4+E4 - . G4 . .", steps_per_beat=2, meter=3)
score.track("harp").play("harp", notes)
export_midi(score, "authoring-out/phrase.mid")
```

Patterns use notes/chords (`C4+E4`), rests (`.`), holds (`-`), accents (`C4!`), and drum triggers (`x`/`X`). `|` validates a bar boundary against the positive integer meter and steps per beat. JSON tracks can instead contain the existing `notes` tuples. Change the project and rebuild to edit an arrangement; changing an already-expanded Score's tempo does not retime its layers.

MIDI is Standard MIDI type 1, 960 ticks per quarter note, rounded to the nearest tick. `meter=3` means 3/4, never inferred 3/8 or 6/8. Each track/instrument pair gets its own melodic channel; percussion uses GM channel 10. Programs are explicit GM approximations, velocity maps to 1–127, and note-off follows held duration rather than the synthesis tail. Loop export omits starts beyond the loop and clips held durations at its endpoint. Layer edits after expansion and tempo changes require rebuilding. Same-pitch overlaps within an instrument group, more than 15 melodic groups, missing GM mappings, fractional pitches, bends, and audio-only material fail explicitly. `--approximate` permits the documented rounding/omission/GM-piano fallback and reports warnings; it does not relax channel or overlap constraints. The Python API accepts a custom `programs` mapping.

## Blind listening and web banks

Zero-velocity MIDI events are omitted; positive velocities map to 1–127. The shared percussion channel also rejects overlapping occurrences of the same key across different Score tracks.

```bash
python tools/curate.py compare comparison BUNDLE_A BUNDLE_B --root authoring-out/rounds
python tools/curate.py serve --root authoring-out/rounds
tare.tools.tune midi examples/authoring.json -o authoring-out/composition.mid
tare.tools.tune export examples/sound-bank.json -o authoring-out/web --ogg
```

Comparisons copy exact retained WAV files with their revision/source/PCM/playback identities. The existing curator keeps ABX, ratings, labels, loudness matching, spectra, and marked ranges. Rebuilding a round retains old audio and answer versions. Old revision API reads use `?revision=ID`; answer writes include `revision`, `version`, `answers`, and `listening`.

Each exported web directory contains a WAV bank, optional Vorbis bank, sample-coordinate manifest, Howler adapter, and standalone Web Audio player. Serve that directory over HTTP and open `index.html`. Clip starts/ends are integers; ends are exclusive. Gaps are separate silent samples. A one-shot clip ends where it falls 60 dB under its loudest 10 ms, with a 10 ms fade into the cut; `silence_cut_frames` records what went, and `pcm_id` is then the clip's own. Loop clips and clips that ring out through a reverb or echo (a Voice `space`, as every creature has, or a Score `hall`/`echo`) keep their full length, as does every clip with `--keep-tail`. Loop flags come from captured loop behavior. WAV clips/quantizes to PCM16 and Vorbis is lossy; clipping counts are reported. Vorbis has 4096 extra trailing silent samples, recorded separately in `codec_padding_samples`: Chromium can omit a codec tail that libsndfile retains. Clip coordinates exclude that padding. Export decodes Vorbis to check the padded frame count, channels, rate, and finiteness. The included player checks that decoded audio covers every clip and falls back to WAV when needed. Hashes verify retained files on reuse. Howler uses fractional milliseconds; the included player divides original sample positions by the original rate, even if the browser resamples the bank. Browser endpoint tolerance is 2 ms, separate from zero-sample libsndfile length tolerance; lossy waveform peaks can move and are not sample-identical.

## Optional DSP and compatibility

`effects.fm_tone` creates an oversampled two-operator FM buffer. `Score(effects=[{"type": "chorus", "mix": 0.3}, {"type": "limiter", "ceiling": 0.4}])` adds chorus and a stereo-linked sample-peak limiter. Effects default to an empty list. Limiting runs after loop folding and final gain; diagnostic replay freezes the recorded gain envelope. Chorus uses periodic modulation and wrapped delay reads for loops. The limiter is not a true-peak/loudness standard implementation, and FM is not promised alias-free for arbitrary parameters.

```bash
python examples/dsp_listening.py --out authoring-out/listening
python tools/curate.py serve --root authoring-out/listening/rounds
```

These examples generate blind comparisons for all three options. Determinism, finite samples, limits, and replay are tested; acoustic quality still requires listening. No normalization redesign or automatic change to existing sounds is included.

| Render path | Compatibility boundary |
|---|---|
| Python Voice | Existing serialization and default synthesis; new capture is observational |
| Native C++ / Godot Voice | Existing supported syllable/noise/modal/scatter/spoken paths; unsupported chip/formant/vocoded features still fail explicitly |
| Python Score/Cue | Arrangement, stereo/shared buses, capture, and optional effects; not a new native Score API |
| FM and optional effects | Python PCM/Score authoring extensions; not new portable Voice fields |

Frozen fixtures in `tests/fixtures/authoring` were saved before the renderer refactor. Tests compare capture on/off and historical samples, in addition to current Python/native comparisons. Windows skips unavailable Linux-native/Godot checks; those must be run in a compatible environment before claiming native validation. See the [implementation verification record](authoring-verification.md) for commands and results.

The authoring layer follows an independent design review (Astra, not published). Diagnostic metadata has its own schema and does not change the Voice feature version or the `legacy-1` renderer behavior. New musical events describe the original expansion; diagnostic identifiers never seed synthesis.

## Contracts

- Source identity hashes the materialized definition and provenance. Render identity additionally includes sample rate, renderer source/build/environment, referenced asset contents, and materialized inputs. PCM identity hashes interleaved little-endian float32 with explicit shape/rate. Encoded playback identity hashes the actual file. Analysis identity includes PCM identity, analyzer version, query, and settings. Equal audio with different origins has different source/revision identities.
- Capture is observational. Instrument callables and note generators execute exactly once. Original beat coordinates, resolved seconds, tempo, effective pitch/velocity, offsets, and event-to-layer mappings are retained. Materialized layers remain authoritative. Mutating the tempo after expansion is rejected by musical exporters.
- Layer buffers are captured after their individual renderer and before the Voice bus. Normalization factors and shared effects belong to named parent stages. Stereo energies sum channel powers, never a potentially cancelling mono downmix. Energy ranking is not additive causal attribution.
- Diagnostic mute/solo replays captured buffers with frozen seeds, lengths, normalization factors, and loop/fade transforms. Ordinary edited renders recompute processing and are a separate operation. Shared nonlinear products and returns are reported as shared processing, not assigned fictional percentages.
- Bundles retain exact PCM, playback audio, provenance, stage buffers, and processing parameters. They guarantee playback and materialized replay. Regenerating arbitrary Python callables or unavailable historical banks is not promised. All bundles state that distinction.
- Inspect accepts a saved bundle, a Voice JSON spec, or a WAV. WAVs have unknown recipe provenance. Empty/short/silent inputs have explicit statuses; JSON contains no NaN/Infinity. Dominant partial, raw estimated fundamental, and planned pitch remain separate. Uncertain/polyphonic F0 may be unavailable. Existing matching/cleanup functions are not silently changed.
- Revision publication writes a complete private bundle before atomically changing its current pointer. Requested generations guard publication. Failed/stale builds cannot replace current audio. Evaluations bind to a revision, exact playback artifact, reference, and listening settings. Saving answers uses revision and answer-version preconditions. Historical rounds are retained; deletion is an explicit manual operation.
- Capture has duration, layer-count, and memory limits. Interactive workers run outside the HTTP request thread and retain the last valid revision. File watchers ignore generated output and include referenced inputs.
- MIDI uses quarter-note beats, a stated tick resolution, recorded held duration (not ring tail), explicit instrument/program/channel mapping, and independently checked events. Unsupported microtones, bends, or audio-only material are rejected or listed as approximations. Pattern bar lengths follow `Score.meter`.
- Audio sprites retain authoritative sample coordinates and half-open loop endpoints. Codec/player adapters document rounding and decoded timing tolerance. Encoding is decoded and verified before publication.
- Optional FM, chorus, and limiting have separate parameters and listening examples. New effects are off by default. Native Voice compatibility and Python-only Score processing are stated separately. Legacy audio fixtures are independent of comparisons against the current Python implementation.

## Implementation sequence

1. Freeze legacy outputs and specify identities, timing, stages, and accepted inspector inputs.
2. Record event/layer mappings and capture existing renders without changing their samples.
3. Save immutable bundles and expose one-shot inspection and diagnostic interventions.
4. Publish revisions and preserve evaluations before automating the curator.
5. Add live browsing, comparisons, annotations, background rebuilds, and solo/mute.
6. Add musical patterns, MIDI, and independently validated audio exports.
7. Add optional DSP and listening material, preserving default and native behavior.

The audit record remains an immutable description of the reviewed proposal. Implementation behavior and verification are documented here and in the tests.
