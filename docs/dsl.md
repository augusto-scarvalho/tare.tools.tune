# Semantic audio DSL (experimental)

[Português brasileiro, auxiliary guide](pt-BR/dsl.md) · [Examples](../examples/dsl-bank.tune.json) · [Measurements](dsl-benchmarks.md)

For routine agent use, start with the [compact workflow](dsl-agent.md). The generated [vocabulary reference](dsl-reference.json) records operation types, fields, defaults, capability boundaries and examples; regenerate it with `python tools/dsl_reference.py` and verify with `--check`.

For an audio iteration, use the [review loop](dsl-review.md): saved observation,
selected controls and trial-checked atomic edits. Its [implementation evidence](dsl-review-implementation.md)
separates integration savings from warm-response overhead.

The DSL describes intent with recipes and reusable definitions, then exposes the existing synthesis primitives for detailed work. JSON is the stored format. Immutable Python builders emit the same JSON; projects never execute Python code. Existing Python APIs, Voice JSON, project JSON and captured bundles remain supported.

Version 1 is **experimental**. Correctness and compatibility tests are separate from token efficiency and listening quality. The measured corpus does not establish the plan's token-saving targets. See the [implementation record](dsl-implementation.md) and [Astra plan](plans/2026-10-31-dsl/PLAN.md).

## Create and hear a sound

Save this as `confirm.tune.json`:

```json
{
  "format": "tare.tools.tune.dsl",
  "version": 1,
  "context": {"sample_rate": 16000},
  "sounds": {
    "confirm": {"sfx": "ui", "style": "crystal", "event": "confirm", "species": 7, "dry": true}
  }
}
```

```bash
tare.tools.tune dsl check confirm.tune.json --json
tare.tools.tune capture confirm.tune.json -o output/confirm --json
tare.tools.tune studio confirm.tune.json -o output/player
```

The player prints a local URL, watches the source and declared assets, and rebuilds in a clean worker. Failed builds retain the last successful revision. Layer source navigation shows the authored pointer, target and definition chain. Diagnostic solo/mute uses captured seeds, timelines and gains; an ordinary source edit renders again and may normalize differently.

For a bank, select with `--name confirm`. A single named sound is selected automatically. `capture`, `inspect`, `studio`, `midi` and `export` share the format dispatcher. Use `--asset-root DIRECTORY` on supported commands to allow additional local asset roots. A recording to hold a sound against goes in the top-level `references` (`{"clash": "refs/clash.wav"}`, one per sound) or `reference` (`{"file": ...}`, every sound): see [Hold a sound against a recording](dsl-review.md#hold-a-sound-against-a-recording).

## Discover the vocabulary

```bash
tare.tools.tune dsl catalog --domain op --limit 10 --json
tare.tools.tune dsl catalog --domain sfx --name ui --json
tare.tools.tune dsl catalog --domain layer --name modal --json
```

Catalog pages have `items`, `total`, `truncated` and a query-bound `next` cursor. Pass it back as `--cursor`. Name-specific recipe entries include events, styles, knob units, defaults and ranges; primitive entries include field types, defaults, physical units and constraints. `--fields name,meaning` projects rows. Object views project envelope fields while retaining revision identities needed for subsequent edits. Unknown fields fail rather than disappearing.

`--fields knobs.ring` or `--fields fragment.with.power` selects nested dictionary fields, up to four levels and 32 paths. This is projection only. `--domain transform` discovers each Notes transform. Native/MIDI flags that say "inspect expanded features" require the actual `dsl capabilities` result.

| Expression | Result / use |
|---|---|
| `sfx`, `creature` | Existing Sfx/Creature recipe, including identity, take and recipe controls |
| `speaker` | Speaker descriptor, usable by `say` and `emote` |
| `say`, `emote` | Speech/performance Voice; installed speech assets may be required |
| `music` | Existing Cue recipe, preserving its loop/fade behavior |
| `voice` | Primitive layers sharing one Voice bus |
| `spec` | Embedded or local Voice JSON |
| `audio`, `fm`, `rest` | Local PCM, existing FM renderer, or explicit silence |
| `notes`, `pattern`, `chord`, `degrees` | Notes before instrument expansion |
| `seq`, `repeat`, `overlay` | Notes sequencing/repetition/overlay; `seq` and `repeat` also compose Sounds |
| `mix`, `score` | Independently rendered Sounds on a Score bus, or musical tracks and sound placements |
| `instrument` | Finite declarative Note-to-layer template |
| `use`, `edit` | Definition invocation, or guarded materialized refinement |

## Reuse intent and parameterize variants

Definitions have a `body` and optional typed `params`. The only parameter substitution form is `{"param":"name"}`. References are lexical; each use receives an independent value. Unused definitions are checked for cycles too.

```json
{
  "format": "tare.tools.tune.dsl", "version": 1,
  "context": {"sample_rate": 16000},
  "defs": {
    "hit": {
      "params": {"power": {"type":"number", "min":0, "max":1, "default":0.5}},
      "body": {"sfx":"ui", "event":"confirm", "dry":true, "power":{"param":"power"}}
    }
  },
  "sounds": {
    "normal": {"use":"hit"},
    "strong": {"use":"hit", "with":{"power":0.85}}
  }
}
```

Parameter types are `number`, `integer`, `boolean`, `string`, `enum`, `time`, `notes`, `sound`, `layer`, `speaker` and `instrument`. Numeric constraints use `min`/`max`; enums use `choices`. Expression parameters are checked again after substitution. Required parameters have no default. This is bounded data substitution, with no arithmetic evaluator, imports or recursive definitions.

Authoring `id` and definition names are labels and do not enter synthesis seeds. Score track `name` **does** enter existing Note/render seeds. Use a track's optional `id` for a neutral editing label. Reordering notes, play calls or layers retains legacy seed consequences; the DSL does not promise unchanged sound under those edits.

Generate explicit named variants into a new file:

```bash
tare.tools.tune dsl variants examples/dsl-bank.tune.json --definition confirm --parameter power --values '[0.2,0.5,0.8]' -o output/variants.tune.json --json
```

## Compose notes before synthesis

The [music example](../examples/dsl-music.tune.json) demonstrates tracks and shared motifs. A compact track can be written as:

```json
{
  "score": {
    "bpm":120, "meter":3, "hall":0, "loop":"2bar",
    "tracks":[{
      "name":"lead-v1", "id":"lead", "instrument":"harp",
      "notes":{
        "repeat":2,
        "of":{"pattern":"C4 - . . . .", "steps":2},
        "then":[{"transpose":-12}]
      }
    }]
  }
}
```

`-` holds the previous pattern event; `.` is a rest. Here each phrase spans three beats even though its note ends earlier. Repetition begins at beats 0 and 3. Span belongs to the phrase and includes trailing silence. Explicit notes use `[pitch, onset_beats, held_beats, optional_velocity]`; a pitch array is a chord. `chord` accepts a chord symbol and optional `octave`, `at`, `dur`, `velocity`; `degrees` uses zero-based scale degrees with `root`, `mode` and `octave`.

`then` runs from left to right before `Track.play`:

| Transform | Value / semantics |
|---|---|
| `transpose` | Semitones; fractional pitches may prevent MIDI export |
| `stretch` | Positive factor for onset, hold and span |
| `velocity` | Factor; resulting velocities must remain 0..1 |
| `retrograde` | `true`; reverse held events inside phrase span |
| `quantize` | Positive grid such as `"1/4b"`; onset ties round later |
| `humanize` | Object with `time`, `velocity`, `seed`; deterministic DSL-specific streams |

Humanization can clamp negative onsets/velocity and reports warnings. It extends span if required. Arbitrary transforms on already rendered PCM are outside this version. If separate legacy play calls matter, author a track's `clips` array, with per-clip `instrument`, `notes` and optional beat-domain `at`; calls execute in authored order. Direct track `layers` follow those calls.

## Work with physical primitives

All existing layer families are available: `syllable`, `modal`, `noise`, `scatter`, `chip`, `speech_frames`, `vocoded`, `spoken`. The [primitive example](../examples/dsl-primitives.tune.json) uses the first three.

```json
{
  "voice":[
    {"id":"body", "syllable":{"start":0,"dur":0.2,"pitch":[[0,440],[1,220]],"source":"sine"}},
    {"id":"air", "noise":{"start":0,"dur":0.08,"freq":[[0,3000],[1,800]],"gain":0.1}}
  ],
  "bus":{"drive":0.1,"lowpass":6000,"seed":7}
}
```

Primitive times are numeric **seconds**, frequencies are **Hz**, and curve coordinates are normalized 0..1. Pitch/frequency curves interpolate in log space; other scalar curves interpolate linearly. Raw fields retain engine meaning, including signed gains and Voice `loop` as crossfade duration. Generic scheduling quantities are unit strings such as `"20ms"`, `"0.5s"`, `"1/3b"`, `"2bar"`. A Score `loop` is its total output duration. Score defaults in the DSL explicitly use `hall:0`; legacy Score's default hall remains unchanged.

Grouping layers into a Voice shares its normalization, saturation, filters and reverb. Placing two Sounds in `mix` preserves their independent Voice/Cue processing and then applies the Score bus. Those operations can produce different sound. Nested captures retain child processing stages and exact gain/dtype conversion with capture schema 2; schema-1 bundles still load and replay.

For Sound `seq`/`repeat`, give recipe children an explicit `span` such as `"250ms"`. Span schedules the next onset; it does not truncate reverb or release tails. Notes patterns already have a span. `mix` placements use `sound`, `at`, optional `id`, `gain`, `pan`, `send`, `echo`. Stereo placement supports centered pan; nonzero pan fails explicitly. Imported audio must match the project sample rate; it is not silently resampled.

## Refine generated layers with a guard

```bash
tare.tools.tune dsl expand confirm.tune.json --view layers --limit 5 --json
```

The response supplies a `materialized_id` and structural paths. Wrap the recipe with `edit`, copying that ID into `expect`:

```json
{
  "edit":{"sfx":"ui","event":"confirm","dry":true},
  "expect":"COPY_THE_MATERIALIZED_ID_FROM_EXPAND",
  "set":{"/lowpass":2400},
  "append":{"/noise":[{"start":0,"dur":0.04,"freq":[[0,4000]],"gain":0.03}]},
  "remove":[]
}
```

Guards prevent a recipe update from silently redirecting a layer index. Stale guards return `E_OVERRIDE_STALE`, the current guard and at most three target hints; expand again and review the new structure. Overlapping/duplicate override paths fail. Voice edits support field replacement and explicit layer append/remove. Score/Cue `expand --view layers` returns actual `/tracks/NAME/layers/INDEX` paths; `--view full` also exposes editable bus/track settings. Edit musical onset, hold and pitch in Notes before expansion. Changing expanded synthesis layers invalidates strict MIDI export. Ordinary bus edits do not falsify recorded Note hashes. Source navigation retains original/current layer paths, edited fields and appended-layer origins.

## Edit the authored source transactionally

```bash
tare.tools.tune dsl query confirm.tune.json --target sound:confirm --json
```

Save the returned `authored_revision` into a patch file:

```json
{
  "format":"tare.tools.tune.patch", "version":1,
  "expect":"COPY_THE_AUTHORED_REVISION_FROM_QUERY",
  "ops":[{"op":"set","target":"sound:confirm","path":"/power","value":0.8}]
}
```

```bash
tare.tools.tune dsl patch confirm.tune.json --patch edit.json --dry-run --json
tare.tools.tune dsl patch confirm.tune.json --patch edit.json --json
```

Operations are `set`, `insert`, `remove`, `move`, and definition `rename` with reference rewriting. Targets start with `sound:name` or `def:name`, followed by `/id:label` or `/track:label` where applicable; percent-encode components. Use `--pointer` for authored queries or a patch operation's `pointer` for exact RFC 6901 addressing. A target never silently dereferences `use` into a shared definition. Edit invocation arguments or explicitly choose `def:name`.

A transaction validates all sounds, checks the expected revision under a cooperating-process lock, backs up original bytes in `.tune-backups`, checks for external writes and atomically replaces the file. Output uses canonical JSON; formatting/comments are not preserved. Conflicts require a new query and reviewed patch. Editors that ignore the lock are not part of an atomic multi-writer protocol.

## Inspect with bounded output

`query`, `expand`, `patch`, `freeze` and root `inspect` offer opt-in `--response compact` (`response="compact"` in Python). Detailed output remains the default. The compact `tune.compact/1` envelope preserves required revisions, guards, warnings, scope and continuation while omitting redundant bookkeeping. A bare compact inspection selects summary; an explicit full view requires detailed output. See [response contract and corrected measurements](dsl-efficiency.md).

```bash
tare.tools.tune inspect confirm.tune.json --view summary --json
tare.tools.tune inspect confirm.tune.json --view layers --band 2000 6000 --top 3 --fields id,label,power,target --no-pitch --json
tare.tools.tune inspect confirm.tune.json --view stages --json
```

Views are `summary`, `layers`, `events`, `stages`, `full`. Drill into a stage with `--node`; rows can identify their child stage. Detailed source and parameter fields are opt-in. Use returned cursors with identical revision/view/window/projection/limit. `analysis_id` stays independent of row projection; `query_id` identifies the projection. Band power sums channels rather than averaging waveforms, so anti-phase stereo is not mistaken for silence. Layer power before a parent bus is not additive attribution through nonlinear/shared effects. `full` deliberately returns the legacy detailed report.

## Python builders and instruments

```python
from tare.tools.tune.dsl import Project, definition, param, sfx, use

project = Project(
    context={"sample_rate":16000},
    defs={"hit":definition(sfx("ui", power=param("power"), dry=True),
                           params={"power":{"type":"number","default":0.5}})},
    sounds={"normal":use("hit"), "strong":use("hit", power=0.8)},
)
project.write("output/builder.tune.json")
compiled = project.compile(name="normal")
```

Builders are immutable value wrappers. `to_dict()` returns an independent copy. `Node.then(...)`, `.with_id(...)` and `.with_span(...)` return new nodes. Arbitrary arrays, callables and executable Python objects are rejected. See the [builder example](../examples/dsl_builder.py).

An `instrument` is a list of track-supported primitive templates. Numeric fields can contain `{"note":"start"}`, `dur`, `f` or `vel`, optionally with numeric `scale` and `offset`. `{"rand":"level","min":0.4,"max":0.5}` uses deterministic `Note.rand`. For example, a sine layer can use `start:{"note":"start"}`, `dur:{"note":"dur"}`, `pitch:[[0,{"note":"f"}]]`. The compiler evaluates it once per Note, with output budgets. Optional `midi_program` is a GM integer 0..127; templates do not become native executable programs.

A `chip_voice` is one channel of an 8-bit console, used wherever a track or clip takes an `instrument`: `{"chip_voice":"pulse","duty":12.5,"fade":true}`. `chip_voice` is `pulse` or `triangle` (the bass); `duty` is 12.5, 25, 50 or 75 (default 25); `fade` steps the volume down to silence over each note; `slide` scoops into each note from that many semitones away, one per 1/60 s; `vibrato` is `[Hz, semitones]`. The channel has one voice: a chord given to it plays as an arpeggio, its notes cycled 60 times a second, and each note ends one frame early so a repeated pitch strikes again. The [chiptune example](../examples/dsl-chiptune.tune.json) is a four-channel loop, and `dsl help chiptune --json` lists the craft. Reviewing any score also reports `bars_db` (the mix's level per bar, dBFS, up to 64 bars), a `level_db` per track (under the loudest track, before the bus) and `rubs` (the half steps `Score.clashes()` finds, counted by kind, with the first three), and `arrangement` (how the parts are laid out: notes per attack, the share of leaps, how many tracks play and how full each 4 bars are). A review renders, and a long orchestral score passes its limits: `dsl check FILE --name NAME --layout --json` returns `arrangement` and `rubs` from the notes alone, for a score or a music cue of any size. `dsl help arrangement --json` says what to look for; [how an orchestral battle is laid out](orchestral-arrangement.md) is the study behind it.

## Export, migration and limits

```bash
tare.tools.tune dsl capabilities examples/dsl-music.tune.json --json
tare.tools.tune midi examples/dsl-music.tune.json -o output/theme.mid --json
tare.tools.tune export examples/dsl-bank.tune.json -o output/sprites --ogg
tare.tools.tune dsl freeze confirm.tune.json --format voice -o output/confirm.voice.json --json
tare.tools.tune dsl migrate examples/authoring.json -o output/migrated.tune.json --json
```

Migration writes a new file only after supported sounds match legacy PCM exactly. Unsupported/ignored legacy fields are refused rather than silently repaired. Cross-directory assets may require the reported additional root. `freeze` supports `voice`, `bundle`, `wav`; a `wav` ends where the sound falls 60 dB under its loudest 10 ms (loops, reverb or echo tails and `--keep-tail` stay whole) and reports `silence_cut_s`, its `pcm_id` then the file's, while the bundle keeps the full render; Score/Cue track extraction uses `--track NAME` and reports omitted Score gain, pan, sends, effects, loop and Cue fade. A bundle retains captured playback and provenance; recipe regeneration also needs compatible source/renderer/assets. Native Voice support excludes chip/formant-speech/vocoded features; use PCM for unsupported material. MIDI reports timing/pitch/velocity and a GM approximation, not synthesized timbre. Capability checks use the strict exporter for its actual supported subset.

Defaults bound source to 1 MiB, JSON depth 64, 256 definitions/sounds, reference depth 32, 4096 expanded occurrences, 64 MiB expanded data, repeat 256, 64 tracks, 512 Note events per track, 1024 capture parts/layers, 180 seconds, 256 MiB retained captures and 512 MiB estimated work. Curves have at most 4096 points, Modal at most 256 modes, chip programs at most 8192 commands per channel, and speech at most 72000 frames per track. `say` accepts at most 1024 characters and Speaker rate is 0.25..4. Weighted DSP work is capped at 1 billion estimated sample operations, including modes/formants/scatter. Imported/reference PCM is checked against decoded byte limits from its header before sample reads.

Capture-part preflight includes generated Cue layers, track nodes and repeated child captures. Large Cue presets can exceed the standard 1024-part cap even though ordinary API rendering works. All 33 Cue defaults were calibrated at 16 kHz with explicit `Budgets(layers=8192, notes=2048)`, retaining the work/memory ceilings. Trusted Python callers can pass reviewed `Budgets`, or bake/import PCM for large material; CLI limits are intentionally bounded. Cross-products can hit limits earlier, and worker deadlines remain an additional bound. See [generated defaults/reference](dsl-reference.json). No persistent cache, remote assets, arbitrary evaluator or native DSL runtime is introduced.

With `--json`, DSL failures emit one `tune.error/1` object in detailed mode or `tune.compact/1` in compact mode to stderr with `code`, `message`, `pointer` and up to three suggestions. Exit codes: 2 input/validation, 3 revision/guard conflict, 4 asset/build/timeout; unrelated generic/legacy errors retain their existing behavior. `dsl check` checks syntax and expression types without synthesis; `--expand` also materializes recipes and validates physical fields. Some asset-dependent validation requires installed assets. Use `--debug` for a traceback.
