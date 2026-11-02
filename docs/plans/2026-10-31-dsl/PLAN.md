# Implementation plan: a semantic authoring DSL for Tune

Date: October 31, 2026. Status: proposed implementation contract, not implemented functionality or approval of sound quality. Requested planning route: fresh Astra session, xhigh reasoning. Primary language: en-US. [Portuguese companion](../../pt-BR/plano-dsl.md). [Task brief](BRIEF.md). [Source fingerprints](INPUTS.json).

## 1. Decision and intended outcome

Build a **versioned declarative data language**, serialized as JSON, with compact semantic constructors, reusable parameterized definitions, typed composition, and explicit access to existing synthesis primitives. Add a **thin Python construction API that produces exactly the same data**. Keep the existing tracker notation as a specialized notation for notes. Do not introduce a general textual parser, execute Python from project files, replace the renderer, or create a second music engine.

The product is the complete agent loop: discover a small vocabulary, author a sound, render and inspect selected evidence, apply a small revision-checked edit, and hear/export the result. Short source syntax alone is not the success criterion. Compact catalog responses, bounded inspection, actionable errors, and patches belong in the first usable delivery.

The DSL should make these tasks ordinary:

- Create a crystal confirmation, a particular creature call, a spoken line, or a generated music cue with a few semantic controls.
- Reuse a motif, sound, speaker, or instrument definition; vary parameters without copying its body.
- Sequence and layer semantic sources, hand-authored primitives, and imported/algorithmic PCM while showing the actual processing boundaries.
- Change one sound's power, one phrase's transposition, or one generated layer's hardness without re-emitting an entire project or losing its recipe.
- Diagnose a selected time/frequency region and receive a few relevant authored targets rather than an entire render manifest.

### Alternatives considered

| Surface | Strength | Material drawback | Decision |
|---|---|---|---|
| Embedded/fluent Python as the primary project | Existing APIs and arbitrary algorithms; potentially terse | Projects would become executable; clean worker/source inspection guarantees weaken; AST editing and portable serialization become separate problems | Retain current Python for trusted programmatic work; new builders only emit data |
| Compact JSON data language | Existing loader/tooling; precise patches; inspectable, bounded, non-executable; composition can be validated before rendering | Punctuation and wrappers have a token cost; no comments; notation can become verbose | Primary surface, with a deliberately small vocabulary and a real benchmark gate |
| Custom text language | Potentially concise phrases and comments | New grammar, recovery, escaping, formatter, spans, editor behavior, and a second patch target; savings unmeasured | Defer until task-level evidence shows a material remaining benefit |
| YAML/TOML as another surface | Familiar for configuration | Multiple representations and parser semantics before the core contract is stable; TOML is awkward for nested expressions | Do not add in v1 |

This choice is an engineering judgment, not a claim that JSON has the fewest tokens. The benchmark in section 15 can overturn the surface choice before v1 is stabilized. Avoid golfing away domain meaning with positional recipe arguments or one-letter keys.

## 2. Evidence and boundaries of this planning run

### Confirmed from current source

| Observation | Consequence for implementation |
|---|---|
| `authoring.materialize()` supports individual `voice`, `sfx`, `creature`, `speech`, `music`, `score`, `audio`, and `fm` sources; `build_file()` selects one source/sound | Reuse the adapters, but add a shared expression compiler; the current loader is not a reusable composition language |
| `patterns.parse_pattern()` returns notes **and total span**; `authoring.materialize()` currently discards the span | Preserve trailing rests and phrase length in the new note representation |
| `Track.play()` expands notes immediately, using `rng.key(score.seed, track.name, len(layers), i, j)`; render groups layer types and seeds them by within-type index | Preserve call boundaries, order, track synthesis names, and layer grouping; diagnostic/authored IDs must not become seeds |
| `Voice`, `Track`, and `Score` have separate normalization/processing stages | Mixing finished voices is not equivalent to concatenating their primitive lists; no optimizer may exchange them |
| `Score.add(Voice)` renders immediately; `Score.add(array)` converts to float64 | A new composition adapter must retain child captures and exact conversion/gain semantics; calling the current method before capture loses child diagnostics |
| `Cue.render()` applies loop handling or post-Score truncation/fading | A Cue cannot be replaced by `cue.score.render()` without changing its result |
| `Voice.to_dict()` chooses the oldest supported feature version, currently 6–8; `Voice.from_dict()` ignores unknown top-level fields | DSL versioning is independent; validate new data strictly before constructing a Voice; keep legacy loading behavior |
| `Score.track()` returns an existing same-name track without applying newly supplied settings | Reject duplicate track synthesis names in the new language; do not silently merge them |
| `sfx.knobs` has useful metadata, but its transforms cover selected layer types rather than every Voice feature | Reuse recipe knobs through Sfx; do not advertise them as universal transformations for speech/chip/PCM |
| `effects.apply_effects()` supports chorus and limiter, sorting limiters last; FM produces PCM | Expose those exact capabilities and order; do not invent native Voice effect fields |
| MIDI checks retained events and hashes and rejects materialized layer changes | Musical transforms must happen before `Track.play()`; low-level edits need honest MIDI restrictions |
| Bundle loading currently accepts schema 1 and a fixed pair of payload files | Additive metadata is possible; replay topology extensions need explicit compatibility handling |
| Studio watches JSON `file` keys, Python source, and captured speech assets; its worker timeout is 120 seconds | New dependencies must be enumerated by the loader; workers/publication can be reused |

Read the named production modules and relevant authoring, Score, and workflow tests. This plan also used the earlier Chirp report for established constraints, not as proof that its old findings remain unresolved.

**Bounded probes actually performed:** all **85** files recorded in `INPUTS.json` matched their hashes; a 40 ms Voice placed into a Score before capture produced one `score` node and a placed part with `child: null`, confirming the eager-capture boundary. Registry inspection found 43 registered instruments, the actual creature archetypes, Sfx events, speaker presets, and Cue kinds/styles used below. These probes took about two seconds in the local environment. No full test suite, native job, listening evaluation, or tokenizer benchmark was run for this plan.

**Historical evidence only:** `docs/authoring-verification.md` reports 490 passed/48 availability skips on Windows, a later 24-test focused pass, and 51 native/Godot checks without skips. Those are recorded earlier results. The 29,960 versus 426 comparison in the brief counts UTF-8 **bytes**, from saved full output and a manual projection; it neither measures tokens nor describes an existing compact CLI feature. The parent session found no installed `tiktoken`; no tokenizer needs to be installed merely to write this plan.

**Known limits to preserve:** materialized playback/replay is stronger than historical source regeneration; F0 remains uncertain on some inputs; band energy is not additive causal attribution; the limiter is a sample-peak limiter. No new production DSP, native renderer rewrite, automatic source execution, or external service is required.

## 3. File format and minimum language

Use a new discriminator, `"format": "tare.tools.tune.dsl", "version": 1`, normally in `*.tune.json`. Do not reinterpret existing `tare.tools.tune.project` or Voice documents. Route by the discriminator, not filename alone. Unknown DSL versions fail before expansion.

```json
{
  "format": "tare.tools.tune.dsl",
  "version": 1,
  "context": {"sample_rate": 16000, "bpm": 120, "meter": 4},
  "defs": {
    "confirm": {
      "params": {"power": {"type": "number", "default": 0.5, "min": 0, "max": 1}},
      "body": {
        "sfx": "ui", "style": "crystal", "event": "confirm",
        "species": 7, "power": {"param": "power"}, "dry": true
      }
    }
  },
  "sounds": {
    "confirm": {"use": "confirm"},
    "confirm_strong": {"use": "confirm", "with": {"power": 0.85}}
  }
}
```

Defaults: context rate 48000 Hz, tempo 100 BPM, meter four quarter-note beats per bar. `defs` and `context` may be omitted; `sounds` is required and nonempty. Do not add a second single-sound root spelling in v1. A one-sound file does not need `--name`; a bank requires it for a single build. Bank enumeration/export remains explicit and bounded.

Allow the existing optional top-level reference shape, `"reference":{"file":"reference.wav"}`, resolved as a local dependency and retained with its own sample rate/PCM identity for listening. It is comparison material, not an implicit sound in the composition. Keep reference identity separate from the rendered sound and charge its retained bytes to the capture budget.

Each expression has **one operation key**, plus that operation's documented fields and common metadata: optional `id`, `span`, and, for note expressions, `then`. The registry specifies allowed fields and result type. A string is a literal, not a reference or interpolated template. References are `{"use":"name","with":{...}}`; parameter slots are `{"param":"name"}`. Conflicting operations, unknown keys, and unknown arguments are errors.

### Types and constructors

| Result type | Proposed forms | Lowering |
|---|---|---|
| Sound, portable Voice candidate | `sfx`, `creature`, `say`, `emote`, `voice`, `spec` | Existing Sfx/Creature/Speaker/Voice APIs |
| Sound, Score/Cue | `score`, `music`, sound `seq`, sound `repeat`, `mix` | Existing Score/Cue processing, with a composition/capture adapter |
| Sound, PCM | `audio`, `fm`, `rest` | File input, existing `fm_tone`, or bounded silence |
| Notes | `pattern`, `notes`, `chord`, `degrees`, note `seq`, note `repeat`, `overlay` | Note sequence preserving span and origin, then existing `Track.play()` |
| Layer | `syllable`, `modal`, `noise`, `scatter`, `chip`, `speech_frames`, `vocoded`, `spoken` | Corresponding current dataclass, with metadata kept out of the dataclass |
| Speaker descriptor | `speaker` | Validated `speaker_from()`/Speaker configuration |
| Instrument descriptor | `instrument` | Bounded layer template evaluated once per existing `Note`; later milestone |
| Same supported materialized sound type | `edit` | Guarded edits after recipe expansion and before rendering |

This is not an unrestricted expression evaluator. There are no loops other than bounded `repeat`, user functions, imports, environment interpolation, regex selectors, filesystem expressions, network references, or `eval`. The only string grammar initially reused is the existing pattern parser and a small unit literal parser.

## 4. Definitions, parameters, variants, and identity

Definitions always have `body` and optionally `params`; use this one shape even for parameterless definitions. Supported parameter types: `number`, `integer`, `boolean`, `string`, `enum`, `time`, `notes`, `sound`, `layer`, `speaker`, and `instrument`. Scalar parameters can have finite bounds/enum choices. Required parameters have no default. Structured expression arguments are allowed only for their declared type, not as arbitrary JSON injection. Parameter references resolve lexically within the definition; caller slots are resolved before binding. Defaults are literals, not references to other parameters. Unknown arguments and type mismatches fail at the call site with the definition location attached.

Definitions form an acyclic graph. No inheritance hierarchy, implicit merge, ambient mutable scope, or evaluated string substitution. `use` creates an instance with its own provenance; implementation may memoize immutable expansion/render artifacts, but never share a mutable Voice between instances.

Variants are ordinary named invocations with different arguments. For a small bank, write those invocations explicitly. Later add a **CLI generator** for a bounded parameter/take list; it writes ordinary `sounds` entries with reviewable names and values. Do not add Cartesian-product semantics to the language. `repeat` repeats the same take; varying takes requires explicit arguments/instances. This distinction prevents accidental nondeterminism.

### Three identities that must stay separate

1. **Authored address:** definition/sound keys and optional `id` fields. Example: `sound:intro/id:impact`, `def:confirm`, `sound:theme/track:melody`. These are edit/provenance targets. IDs must be unique within their container; composed instance addresses include the invocation path. Repeated occurrences add a derived occurrence index; that index is not a durable authored identity.
2. **Synthesis identity:** existing `species`, `individual`, `take`, Voice/Score/Cue seeds, instrument Note seeds, and **Score track `name`**. These remain the actual inputs to legacy algorithms.
3. **Diagnostic identity:** revision-scoped `n0`, `n0/p0`, event IDs, materialized hashes, and render/analysis identities. These identify evidence and buffers, never random streams.

Track declarations therefore have a required `name` (passed unchanged to Score, and seed-relevant) and an optional `id` (editable identity, seed-neutral). Changing `id`, definition keys with references updated, or unrelated labels must leave PCM unchanged. Changing `name` may change timbre and is reported as seed-affecting. Do not silently derive track names from authored IDs or definition paths.

For a file without explicit IDs, pointers remain usable only with the expected authored revision. The patch command can add an ID explicitly; it must not silently inject IDs during reading/building. Avoid promising stable identities for generated recipe internals that have no declared handles today.

## 5. Exact semantic and primitive examples

Everything in this section is **proposed DSL syntax**, except the existing APIs named in the explanations. Examples are intended as executable fixtures once their milestone lands.

### Sfx, creature, speech, and generated music

These expressions can be individual `sounds` values:

```json
{"sfx":"blade","style":"steel","event":"clash","species":"excalibur","size":0.65,"power":0.8,"knobs":{"ring":0.7,"brightness":-0.2}}
```

```json
{"creature":"monster","call":"attack","species":21,"individual":2,"take":3,"size":0.8,"aggression":0.7}
```

```json
{"say":"Alto lá!","lang":"pt","speaker":{"speaker":"deep","pitch":105,"rate":0.9},"seed":17,"emotion":"raiva"}
```

```json
{"emote":"hurt","speaker":{"speaker":"deep"},"style":"grunt","intensity":0.7,"take":2}
```

```json
{"music":"victory","style":"orchestral","seed":12}
```

Sfx fields map to `Sfx(...)` and `.voice(event,take)`; Creature fields map to `Creature(...)` and `.voice(call,take)`. No universal `seed` alias substitutes for their existing species/individual/take semantics. Speech uses the actual implementation in `speech/__init__.py`, not a nonexistent `speaker.py`. `speaker` accepts a current preset name plus validated Speaker overrides; a descriptor can be stored in `defs` and referenced by `say`/`emote`. Support `engine:"natural"` and explicit `bank` with dependency checks; do not silently fall back to another engine. Preserve the existing language values `pt` and `en`; documentation can call `pt` Brazilian Portuguese.

`species` accepts an integer **or a string identity** where the existing recipe supports it; named species such as `"wolf"`/`"excalibur"` are documented existing usage. Pass the string unchanged to the current RNG key path; do not turn it into a different integer seed, coerce `"7"` to `7`, or apply Unicode normalization. Registry conformance tests must cover named and numbered species. Some current composite recipes directly perform arithmetic on species, so support is not inferred solely from the dataclass annotation or broad README wording: flag an affected recipe's numeric-only limitation explicitly until separately corrected. This DSL must not silently promise or repair universal named-species support.

`say` supports current `style`, `emotion`, and explicit optional seed. Its default seed remains the current text/lang/Speaker/style/emotion derivation, including existing Speaker.name behavior. Authored IDs must not be written into Speaker.name. `music` passes through Cue, including its final fade/loop. Optional fields must be cataloged from explicit adapters rather than arbitrary constructor reflection.

### A portable Voice with named hand-authored layers

```json
{
  "voice": [
    {"id":"tone","syllable":{"start":0,"dur":0.18,"pitch":[[0,660],[1,440]],"source":"sine","attack":0.005,"release":0.04,"gain":0.8}},
    {"id":"body","modal":{"start":0.01,"dur":0.3,"modes":[[880,0.2,1],[1320,0.12,0.3]],"hits":[[0,1,0.001]],"hardness":5000,"gain":0.4}},
    {"id":"air","noise":{"start":0,"dur":0.08,"freq":[[0,3000],[1,1200]],"filter":"band","q":0.8,"gain":0.12}},
    {"id":"sparks","scatter":{"start":0.03,"dur":0.2,"rate":[[0,30],[1,0]],"event":"ping","freq":[1800,4000],"decay":[0.002,0.015],"gain":0.08}}
  ],
  "bus":{"seed":13,"drive":0.3,"lowpass":6000,"gain":0.5}
}
```

The `voice` operand is a list of Layer expressions; `bus` contains current non-layer Voice fields. Layer `id` is a sidecar handle, never serialized into Modal/Noise/etc. The compiler groups layer kinds exactly as the current renderer does, preserving order within each kind. The list is not a claim that cross-kind rendering order changes.

Layer parameter objects use the existing spec's physical units: start/dur/attack/release/T60 in seconds, frequency in Hz, curve positions normalized to 0..1, rough/vibrato/pulse tuples with their present meanings. This is deliberately a low-level escape hatch, without a second renamed version of every field. `chip` wraps `ChipProgram` and validates its command/register structure; `speech_frames`, `vocoded`, and `spoken` wrap their current dataclasses and carry their asset dependencies. Large frame arrays may be imported from a **local validated Voice JSON** with `{"spec":{"file":"voices/guard.voice.json"}}`; inline `{"spec":{...existing Voice document...}}` is also supported. `spec.file` is data, never Python.

All eight existing layer families are reachable. They need not all be editable with every high-level transform. Primitive documentation should be generated from a maintained field/type/unit registry, including curve interpolation and enum constraints, not merely a dataclass dump.

### Finished sounds and PCM are a different composition boundary

```json
{
  "mix": [
    {"id":"metal","at":"0s","sound":{"sfx":"blade","style":"steel","event":"clash","species":9},"gain":0.8,"pan":-0.2},
    {"id":"low","at":"20ms","sound":{"fm":{"freq":110,"duration":0.25,"ratio":1,"index":2,"decay":0.12,"gain":0.3}},"gain":0.25},
    {"id":"foley","at":"0s","sound":{"audio":"audio/contact.wav"},"gain":0.15}
  ],
  "hall":0,"gain":0.7
}
```

This uses a stereo Score mixing boundary with no hall by default. Each Sfx/Voice is already normalized/processed before placement; the parent applies current Score normalization. A `voice` expression sums primitives into **one** Voice bus. The compiler must never merge independent voices into one Voice to save work. FM and imported audio remain PCM; native Voice export of this mix fails with a capability explanation and a PCM export alternative.

`audio` paths are project-relative local files, retain channel layout, and must match project sample rate. No silent resampling or downmixing. Mono pan uses the current equal-power law. Existing Score leaves stereo sources' channels intact and ignores pan for them: the new language rejects **nonzero pan on a stereo child** rather than claiming it worked. Send/echo behavior remains current Score behavior, including stereo-to-mono averaging for sends.

## 6. Composition, music, time, and transforms

### Sequencing and spans

```json
{
  "seq":[
    {"use":"confirm","span":"0.4s"},
    {"rest":"0.1s"},
    {"say":"Ready.","lang":"en","speaker":{"speaker":"deep"},"span":"0.9s"}
  ],
  "gap":"0s",
  "gain":0.6
}
```

`span` is **scheduling duration**, not a crop, stretch, rendered tail length, or note hold duration. Sequence advances by child span plus the explicit gap; no final gap is added. Audio beyond a span overlaps subsequent children. The result retains tails unless an explicit Score loop folds them. A standalone sound does not need a span. To place it in a sequence/repeat, an unknown span is an `E_SPAN_REQUIRED` error with an exact insertion location.

Infer spans only when semantics are exact: patterns include all steps/rests, explicit Notes have declared span or maximum held-note end, `rest` has its duration, and PCM input has its decoded sample count. Recipes/Voices/Cues require an explicit span in timing-dependent composition in v1. Do not synthesize audio merely to guess a musical phrase's length. This is a conscious tradeoff: explicit intention is preferable to schedules changing when a reverb tail or speech bank changes. An `expand` report may suggest measured duration after a build, clearly labeled.

`seq` and `repeat` work on homogeneous Notes or Sound values; mixed types fail with a suggestion to use a Score track for Notes. `repeat:N` with `of` and optional `gap` creates N occurrences and requires positive bounded N. Audio occurrences reuse the same rendered take; no implicit randomization. Notes repeat before note expansion and therefore use the current per-note randomness when played. `mix` accepts placed Sound children with `at`, relative gain, pan, send, and echo; it does not require spans to render a root mix. A parent sequence needs the mix's explicit span when it cannot be inferred. `overlay` combines Notes at their existing positions and uses maximum span.

For sound `seq`, `repeat`, and `mix`, lower one composition node to one Score with hall 0, echo off, lowpass off, seed 0, and final gain 1 unless explicitly supplied. Nesting a sound composition creates a real additional bus; document it and preserve it. Do not flatten across buses. A `rest` is bounded silence, not an empty Score. Empty compositions fail; all-silent nonempty compositions remain valid.

### Musical definitions and arrangement

```json
{
  "format":"tare.tools.tune.dsl","version":1,
  "context":{"sample_rate":16000,"bpm":120,"meter":4},
  "defs":{
    "motif":{"body":{"pattern":"C4 - E4 - G4 - . .","steps":2}},
    "answer":{"body":{"use":"motif","then":[{"transpose":12},{"velocity":0.8}]}},
    "confirm":{"body":{"sfx":"ui","style":"crystal","event":"confirm","species":7,"dry":true}}
  },
  "sounds":{
    "theme":{"score":{
      "bpm":120,"meter":4,"seed":17,"hall":0.3,"loop":"2bar","gain":0.8,
      "tracks":[
        {"id":"melody","name":"lead-v1","instrument":"harp","pan":-0.3,"send":0.2,
         "notes":{"seq":[{"use":"motif"},{"use":"answer"}]}},
        {"id":"bass","name":"bass-v1","instrument":"marimba","pan":0.25,
         "notes":{"repeat":2,"of":{"use":"motif","then":[{"transpose":-12}]}}}
      ],
      "sounds":[{"id":"confirmation","at":"1bar","sound":{"use":"confirm"},"gain":0.2}],
      "effects":[{"type":"chorus","rate":0.8,"depth":0.004,"mix":0.15,"voices":2},
                 {"type":"limiter","ceiling":0.8,"release":0.05}]
    }}
  }
}
```

Track `notes` is one Notes expression and is lowered with one `Track.play()` call, preserving that documented call boundary. For multiple instrument phrases on one track, use an exclusive alternative `clips` list of `{id,instrument,notes,at}` records; each clip is one `Track.play(..., offset=...)` call in **authored list order**, not time-sorted order. This preserves the legacy significance of i/j/layer count. Reject both `notes` and `clips` on one track. Direct track layers use an optional `layers` list, appended **after** clips; explicit user ordering across note calls and direct layers can wait for evidence of need. A separate track or Voice placement already gives control without inventing a mutable command language.

Additional Notes constructors:

```json
{"notes":[["A3",0,1,0.8],[["C4","E4"],1,2,0.7]],"span":"4b"}
```

```json
{"chord":"Am7","octave":3,"at":"0b","dur":"2b","velocity":0.7,"span":"4b"}
```

```json
{"degrees":[[0,0,1],[2,1,1],[4,2,2]],"root":"A","mode":"minor","octave":3,"span":"4b"}
```

Use `score.chord`, `scale`, `midi`, and `hz`. Degrees are zero-based integers; octave extension uses quotient/remainder over the scale length, including negative degrees. Explicit note tuples keep the existing `(pitch, beat, held_beats[, velocity])` contract; numbers in those two positions are beats. Chord pitches remain grouped so one event/chord origin can map to multiple generated layers.

### Notes transformations

Apply `then` left-to-right before instruments expand:

| Transform | Exact v1 rule |
|---|---|
| `{"transpose":n}` | Add finite semitones to every pitch; fractional pitches supported internally, MIDI may reject |
| `{"stretch":k}` | Positive factor scales onsets, held durations, and span; it does not resample audio or change tempo |
| `{"velocity":k}` | Multiply velocities; reject a result outside 0..1 rather than silently clip |
| `{"retrograde":true}` | Within finite span L, replace onset with L − (onset + held duration); preserve duration/pitch; reject notes extending beyond L |
| `{"quantize":"1/4b"}` | Quantize onsets to nearest grid, ties toward the later grid point; keep held durations; reject invalid out-of-span results unless span is explicitly enlarged |
| `{"humanize":{"time":"10ms","velocity":0.04,"seed":31}}` | Bounded uniform signed onset/velocity perturbations; convert time in the local tempo; clamp onset to 0 and velocity to 0..1, disclose clamps; preserve holds and update inferred span |

Keep canonical event order deterministic; simultaneous notes retain authored/expansion order. Humanize uses a specified namespace `dsl-humanize-1`, the explicit seed, flattened event ordinal, and dimension. It never uses an authored or diagnostic ID. The requested random transform is new DSL behavior; it does not replace existing Note/Voice seeds. Applying humanize after repeat yields distinct offsets per repeated event; applying it before repeat repeats the same offsets. Golden vectors pin the helper. Other transforms do not consume randomness.

Do not apply note transforms to PCM, chip registers, or arbitrary Speech frames. Errors identify the unsupported type and the available recipe knob/primitive field alternative. Sfx `knobs.tempo` means **gap multiplier** (2 is slower), as in current code; it is not BPM. Do not rename it silently or use it as a generic tempo operator.

### Timing, units, rounding, and looping contract

- Beats are quarter notes. Meter is a positive integer beats-per-bar, not a fraction such as 6/8. Constant tempo per Score; tempo maps are deferred. Nested Score/Cue audio may have its own tempo; placement `at` uses the parent's context, internal notes use the child's.
- Generic timeline quantities use unit strings: `"120ms"`, `"0.5s"`, `"2b"`, `"1/3b"`, `"2bar"`. Parse finite nonnegative decimal/rational literals; no arithmetic expressions. BPM is finite and positive, validated to the supported authoring range. Primitive spec fields retain their documented numeric seconds/Hz/normalized coordinates. No contextual guess that 500 means ms.
- Normalize note timing with rational values where possible and preserve the authored literal. Convert to floats only at the existing Score boundary. Use the renderer's current placement rule `int(seconds * sr)` and loop length rule `round(seconds * sr)`. Do not introduce a different global rounding rule to make arithmetic look cleaner. Report actual sample placements.
- Absolute source span, note held duration, Voice dry duration, rendered duration including tails, and loop duration are separate fields in expansion/inspection.
- `score.loop` and composition `loop` are exact output periods using existing Score tail folding. `voice.bus.loop` and raw Voice `loop` retain their different meaning: crossfade seconds, with period derived from dry duration minus crossfade. Name both meanings explicitly in discovery and reject nonpositive resulting periods.
- Cue's own loop/fade policy is retained; overriding a Cue period is not a generic wrapper field. Compose or freeze it explicitly. A scheduling span does not crop it.
- Effect order is inherited: Voice processing first, child output, Score sends/hall/echo/lowpass, loop fold/trim, Score peak normalization and final gain, then optional effects. Require chorus before a single optional final limiter in new DSL data, instead of relying on the old helper's silent limiter reordering. Old Python effects lists keep working unchanged.
- Root Sound composition gain and Score gain are final output gains before Score effects; placement and layer gains are relative inputs to normalizing buses. A −6 dB change to one layer is not guaranteed to reduce final peak by 6 dB. v1 uses numeric linear gains; a future dB convenience can convert at the authoring boundary without another signal stage.

## 7. Low-level refinement without losing the semantic recipe

There are two distinct operations: change authored semantic parameters, or apply a guarded materialized override. Do not convert every recipe to a giant frozen spec merely to adjust one field.

First inspect the selected expansion:

```text
tare.tools.tune dsl expand bank.tune.json --name confirm --view layers --limit 5 --json
```

Proposed bounded response (hash strings abbreviated only in this document):

```json
{"schema":"tune.query/1","authored_revision":"abc…","materialized_id":"def…","type":"voice","items":[{"path":"/modal/0","kind":"modal","fields":{"hardness":8000,"dur":0.4}}],"total":3,"next":null}
```

`/modal/0` is an illustrative **structural** path to a layer actually present in that expansion, not a promised role of every confirmation recipe. The implementation fixture must obtain the real path/value from the chosen recipe. No existing metadata promises handles such as `attack`, `body`, or `sparkle` for arbitrary recipes.

Wrap only the affected instance:

```json
{
  "edit":{"use":"confirm"},
  "expect":"<materialized-id-returned-by-expand>",
  "set":{"/lowpass":2400,"/modal/0/hardness":3000}
}
```

`edit` expands its child once, hashes the unedited materialized view, checks `expect`, copies it, applies validated nonoverlapping field replacements, and renders the edited copy. Missing targets, type changes, overlaps such as `/modal` and `/modal/0`, and stale hashes fail. No best-effort index matching. This keeps the reusable recipe and its explicit deviation together. A recipe/parameter/compiler change that alters the expansion forces deliberate re-selection. The tool offers the current compact target list; it never automatically accepts the new hash.

The first override implementation supports Voice field replacements only. The full roadmap adds bounded `append` at a Voice layer collection and `remove` of an explicit generated layer, under the same guard, with original-to-edited lineage. Insertion/removal can change surviving within-kind seeds; report that and do not call it a diagnostic mute. Existing stable authored layer IDs in a `voice` expression should be edited at their authored fields instead of through a materialized index.

Later extend `edit` to materialized Score/Cue fields with a documented expansion view: actual track names, per-track Voice layers, gains, and bus settings. Preserve Cue wrapper behavior. Permit synthesis/bus edits; reject changing tempo, meter, or recorded note timing after expansion with `E_EDIT_REQUIRES_NOTES`. Those changes belong in note expressions or recipe inputs. Do not reconstruct Cue note calls from recorded events as if they retained the original call grouping; current provenance does not provide a lossless editable recipe reconstruction.

MIDI remains strict after edits to note-generated layers. Do not replace stored `layer_hashes` to pretend the edit came from the original notes. Offer the original note arrangement as a separately labeled approximate export only if an explicit new adapter reports every affected event; the first release can simply reject such export. Portable Voice extraction is allowed for Voice results; materialized Cue/Score tracks can be exported individually with their loss of arrangement/wrapper clearly stated.

## 8. Small semantic patches and concurrency

Add `dsl query` and `dsl patch`. Patch targets refer to authored definitions/instances/IDs, never raw diagnostic node IDs. Patch envelopes are data files or stdin, avoiding shell-specific JSON escaping:

```json
{
  "format":"tare.tools.tune.patch","version":1,
  "expect":"<authored-revision-from-query>",
  "ops":[{"op":"set","target":"sound:confirm_strong","path":"/with/power","value":0.65}]
}
```

```text
tare.tools.tune dsl patch bank.tune.json --patch edit.json --json
```

`target` has a small fixed grammar: `sound:<key>`, `def:<key>`, optionally followed by `/id:<id>` or `/track:<id>` segments scoped to that authored subtree. IDs/keys are escaped using documented percent encoding, not an implicit regex. An exact RFC 6901 `pointer` is an alternative when no authored ID exists, mutually exclusive with `target`; it always requires the same whole-file precondition. `path` is an RFC 6901 pointer relative to the selected authored object. `set` creates/replaces an object member but never silently grows arrays; replacing an existing array item requires its valid index. Array structural edits use explicit `insert`, `remove`, and `move` operations with exact parent/position. `rename` is a semantic operation for definition keys and updates all local references atomically; a simple set does not perform hidden reference rewriting.

Changing a definition intentionally affects all its uses. Query/patch preview returns affected sound names/counts, capped with pagination. To affect one invocation, set its `with` argument or wrap that invocation in `edit`. Do not implement magic copy-on-write definitions that hide new names. Changing a field not exposed as a parameter requires editing the definition or explicit materialized refinement.

Transaction: lock the project, read fresh bytes, compare expected **authored revision**, apply operations on a copy, validate the complete document and affected expansion graph under limits, serialize to a same-directory temporary file, fsync, recheck original bytes immediately before replace, and atomically replace. Return old/new revision, changed authored targets, affected sounds, and bounded warnings. On parse/type/reference/precondition failure, write nothing. A second writer with an old revision receives `E_REVISION_CONFLICT`; never rebase silently.

The authored revision is the digest of the parsed authored document with canonical object-key ordering and preserved array order, not the capture revision. Also retain a raw-file hash for detecting outside writes during the transaction. Whitespace-only edits do not require semantic rebasing, but must not be overwritten unnoticed during a patch. Since ordinary editors do not honor our lock, the recheck narrows but cannot eliminate the final external-writer race; document that limit and preserve the previous bytes in a transaction backup. Do not claim a lock is a universal filesystem compare-and-swap.

Patch initially reformats JSON deterministically; it preserves every unrelated data field and array order, not byte-for-byte whitespace. Report this. Add a format-preserving JSON editor only if measurements justify its complexity. Build-time validation is bounded and produces no PCM unless explicitly requested. The watcher handles rebuilding; patch does not publish a render revision itself. A valid source edit followed by a render failure remains in the source file while Studio keeps the previous good audio.

## 9. Determinism, compilation, and the smallest coherent representation

Use one normalized expression model and a small typed result union; do not create a general compiler framework or persist a parallel editable graph database.

```text
DSL JSON or Python builders
    -> strict loader + source locations + dependency list
    -> typed expressions / definition bindings / estimated cost
    -> Notes(span, events, origin chains) or Layer/Speaker/Instrument descriptors
    -> leaf Voice / existing Score / Cue / PCM plans
    -> existing synthesis and Score composition, with child captures
    -> Capture + authored/compiler metadata -> existing immutable bundle
```

Suggested internal records:

- `Expr(op, fields, children, source_location, authored_id)`; immutable, not a dynamically evaluated AST.
- `NoteSequence(events, span, context, origins)`, where events retain grouped chord pitches, held beats, velocity, and transform/occurrence lineage. This is the only essential new musical intermediate representation.
- `SoundPlan(kind, payload, placements, span, capabilities, origins, dependencies)`. Kinds are existing Voice, Score, Cue, PCM, and composition; no new DSP node graph. Generated layer lists remain authoritative existing dataclasses.
- `CompileResult(plan, authored_revision, compiler_id, dependencies, source_map, cost, warnings)`. Runtime objects are not the serialization format. An optional expansion report is evidence, not another source of truth.

Stages: parse and validate structure; resolve reachable definitions and argument types; compute spans/transforms and budget; materialize each semantic leaf once; apply guarded edits; assemble plan; render/capture; attach provenance and finalize hashes. `check` offers syntax/type-only validation and `--expand` for bounded materialization without DSP, with the distinction explicit. Some speech planning and asset duration checks are real work even without DSP; account for them. Cache immutable expansions within a single build only after keys include resolved parameters/context/dependencies. Do not share stateful existing Python callables or replay them to reconstruct provenance.

### Seed policy: preserve `legacy-1`

- The new language has no root global seed that silently overrides all sources. Each source keeps its existing seed inputs/defaults. Record resolved seeds so agents can query them.
- Recipe identities and takes map directly to existing APIs. Voice/Cue/Score defaults remain current defaults. Numeric authored seeds use the exact JSON-safe integer range specified in section 11; named species remain strings. Freeze vectors rather than relying on accidental coercion or Python's unlimited integers.
- Notes use existing `Track.play()` seed derivation, in declared clip order. Adding a note or primitive can change subsequent timbres. Source annotations explain the affected track; no promise of edit-local audio invariance.
- Rendering still groups layers and uses the original within-kind index seeds. Removing a generated layer may change downstream seeds in that kind. Diagnostic mute/solo instead uses captured buffers and frozen factors, preserving surviving samples.
- Repeated immutable audio can reuse buffers, but each placement gets a distinct provenance occurrence. Equivalent spec plus different provenance is not the same source revision.
- A future opt-in stable musical randomness mode would need an explicit new behavior/version contract and separate listening/compatibility tests. It is not necessary for v1 and must not leak into old projects.

### Composition capture without a renderer rewrite

Render each child through existing `capture()` once. Build the parent Score from the **captured child audio**, using current `Score.add` semantics. Capture that Score normally. Then attach retained child capture graphs to the corresponding placed parts, remapping revision-local node/part/buffer IDs and combining assets/source maps. Parent part gain, input conversion, and child link must be explicit; root selection remains the parent, not the last imported child.

This needs a narrow replay extension: placed children were converted to float64 before multiplication, whereas a child capture's output is often float32. Record the input conversion and placement multiplier and reproduce them **before** parent mixing. Preserve the existing special Track gain/PEAK path unchanged. Add graph validation and cycle rejection; do not infer child links from matching PCM hashes alone. Reused child buffers can be stored once, but occurrence paths must remain distinct; initially copying bounded graph records is simpler than a shared-node DAG with ambiguous parent coordinates.

The adapter merges every child dependency/asset, including speech banks, rather than relying only on the parent's nodes being discovered during its render. Preflight and cumulative limits cover all subcaptures, parent arrays, and temporary working buffers. A nested tree must not receive a fresh 256 MiB allowance at every node.

This approach reuses DSP and makes the boundary explicit. It requires tests for exact replay and source mapping before composition is released. If post-assembly linking proves brittle, the acceptable alternative is a narrow recorder context/placement API around the same existing render calls. It is **not** a reason to write a new mixer. Compare both against the parent Score PCM baseline before choosing internal mechanics.

## 10. Provenance, persistence, portability, and capability reporting

Every materialized layer/event/placement should trace to: authored file and pointer; definition location; invocation chain and resolved parameters; repeat/transform occurrence; recipe/type and resolved seed inputs; generated structural path; optional explicit authored handle; and any guarded materialized override. Store this as a source map and references, not repeated copies of the entire definition in every row. Retain existing Python caller information for legacy users.

The inspector must be able to return both **why this exists** and **where to edit**. A generated layer can point to an editable recipe parameter when the mapping is factual; otherwise return its containing expression plus guarded materialized path. Never invent a one-to-one causal parameter mapping. Stable recipe part roles are a useful future capability: add them only to selected recipes with explicit design-time metadata and tests, without putting labels into the Voice wire schema or seed inputs.

Keep identities separate:

- `authored_revision`: canonical authored data; `raw_file_hash`: exact source bytes; dependency hashes recorded separately.
- Existing `source_id`: materialized definition plus authored provenance, selection, resolved bindings, and compiler identity as appropriate to the new source contract.
- Existing `render_id`: source/materialized inputs, rate, renderer contract/build/environment, content hashes of all dependencies, captured buffers. Do not redefine historical IDs in old bundles.
- Existing `pcm_id`, `playback_id`, revision/bundle identity, and `analysis_id` retain their distinct meanings. A compact projection gets a `query_id`/projection version; it must not pretend to be a different audio render.

Persist the authored document, normalized source map, compiler/language version, dependency content hashes, and effective settings with the capture. Preserve exact PCM/playback and materialized buffers as today. Hashing a missing/changed historical bank does not make regeneration possible: report `regeneration:"verified_inputs_available"`, `"inputs_missing"`, or `"materialized_only"` only when the corresponding checks justify it. Archive user-owned source/dependency bytes under an explicit future packaging command if needed; do not silently duplicate arbitrary large assets during every render.

New graph/replay metadata should use **bundle/capture schema 2** if an old schema-1 replay implementation would ignore required conversion/topology semantics. New readers accept both schemas; legacy sources can continue producing schema 1 until the compatibility matrix requires otherwise. Validate schema-2 edges, factors, conversions, all buffer references, and source-map indexes. Unsupported older readers must fail cleanly instead of producing misleading replay. Keep the payload pair `buffers.npz`/`audio.wav` initially; store authored metadata in the manifest to avoid an unnecessary bundle file-format redesign.

### Native and export capabilities

DSL format/version, bundle schema, Voice feature version, and renderer behavior version are four different contracts. Never raise `Voice.VERSION` for an authoring-only feature. `Voice.to_dict()` remains the native handoff for a single Voice-capable result. Native support is the actual tested feature matrix, not every Python Voice field; chip/native limitations and asset-dependent speech must be checked and reported.

`dsl capabilities`/`check` returns, for the selected sound: `voice_json`, `native_voice`, `pcm`, `midi`, required assets, and reasons/approximations. A Score/Cue, PCM/FM, parent mix, or Score effect cannot be squeezed into a Voice document. Offer PCM bake/export or individual portable voices; never silently omit processing. Existing runtime banks and bake behavior stay unchanged. No native runtime needs to interpret the DSL in v1.

## 11. Validation, limits, and failure behavior

Keep the strict DSL validator separate from permissive legacy deserializers. Reuse finite/range checks already present in FM/effects/Sfx where sound, but validate structure, units, resource cost, and unknown fields before calling them. Dataclass reflection supplies field inventories, not semantic ranges, enum values, or safety checks by itself.

Validation has four stages: JSON/document shape, typed definitions/units, bounded semantic expansion, and render/capability checks. An error has a stable code, concise message, authored target/pointer, related definition location, expected type/range, and at most three suggestions. Include the expansion stack only on request, bounded to its actual depth. Do not leak a Python traceback into the default agent response; `--debug` retains one for developers. Do not catch arbitrary programming bugs and mislabel them as user validation errors.

Example:

```json
{"schema":"tune.error/1","code":"E_KNOB_RANGE","target":"def:confirm","pointer":"/defs/confirm/body/knobs/ring","message":"ring must be 0.1..4 (multiplier)","value":8,"suggestions":[{"path":"/knobs/ring","range":[0.1,4]}]}
```

Default limits should start conservatively and be configuration of the build request, not author-controllable fields that defeat the limits:

| Budget | Initial default | Enforcement |
|---|---:|---|
| Main source bytes | 1 MiB | Before parsing, matching current authoring scale |
| JSON structural depth | 64 | Bounded scan/decoder guard; reject before recursive compilation |
| Definitions / named sounds | 256 each | Schema validation |
| Definition expansion depth | 32 | DFS with explicit recursion/cycle detection |
| Expanded expression occurrences | 4096 | Charge before cloning/expanding; memoization does not erase logical cost |
| One repeat count | 256 | Integer validation plus multiplicative aggregate cost |
| Tracks / notes per track | 64 / 512 | Validate after transforms/repeats and chord expansion accounting; define notes as emitted pitch events for this new limit |
| Captured parts/layers | 1024 | Same default as current capture, cumulative across all nested stages; include parent placements, not just synthesis layers |
| Total output duration | 180 seconds | Include placements, tails, loop support, Cue fade support, and nested children |
| Captured array bytes | 256 MiB | One shared budget across children and parent, checked before copies |
| Worker wall time | 120 seconds | Existing worker timeout; structured timeout result and last-good preservation |
| Audio channels | Mono or stereo | Header and decoded-array checks |
| Query rows / errors | 10 default, 100 maximum / 8 default | Pagination and explicit truncation metadata |

Also bound array/scalar counts inside curves, modal modes, chip commands, speech frames, and asset headers using **weighted work estimates**, not only JSON byte size. Start with configurable internal ceilings of 4096 points per curve, 256 modes per Modal, 8192 chip commands per program, and 72,000 frames per speech track, with a total scalar/operation budget. Duration and global memory limits may reject far smaller combinations. These are proposed initial safety budgets, to calibrate against legitimate fixtures; no claim is made that the largest permitted cross-product is cheap.

Preflight computes conservative output/temporary sizes, including float64 work arrays, convolution tails, FM's four-times oversampling, and captured copies. A 256 MiB capture limit alone does not bound peak process memory: use a separate initial **512 MiB estimated working-memory budget** and the timeout. Check after each bounded expansion/materialization stage. Kernel/platform hard memory enforcement may be added where available, but do not advertise a strict RSS guarantee before it exists. Bank export charges the aggregate retained captures because the current exporter holds them together; reject over-budget banks or explicitly split batches rather than allocate unbounded memory. Streaming export is a later optimization.

Range/type rules include positive durations and tempo, nonnegative positions, finite values, 0..1 velocities, valid gain/pan/send ranges, known enum strings, ordered normalized curve points, valid mode/hit tuples, supported note values, legal chip commands, and matching speech frame dimensions. Do not silently accept duplicate JSON object keys, NaN, Infinity, booleans as integers, unknown layer fields, unknown format versions, or a reference cycle. Preserve intentional empty optional curves where the spec defines them; reject empty required pitch/frequency curves. A layer may extend beyond the phrase span by design, but negative starts and a nonpositive loop period are invalid.

Do not reuse semantic-intensity validation for low-level amplitudes. Sfx power/size, selected mix fractions, and note velocity have their named bounded meanings; primitive layer gains, mode/formant/hit amplitude coefficients, amplitude curves, placement/track/final gains, and linear send coefficients accept finite **signed** values, including magnitudes above one where the underlying function supports them. Negative coefficients are necessary for polarity/cancellation experiments. Validate physical fields such as frequencies, decay times, and filter bandwidths separately. FM retains its existing 0..1 gain restriction. Detect non-finite intermediate/output audio and fail publication rather than silently clipping signed coefficients. Include a +1/−1 same-signal cancellation fixture and a negative-gain PCM placement fixture.

Authored seed/species/individual **numeric** values must be integers in the exactly representable JSON integer range, `-(2^53-1)..2^53-1`; takes are nonnegative integers in that range. `species` additionally accepts the strings described in section 5. Pass integers unchanged to the existing integer-masking RNG. Internally generated 64-bit Note keys remain untouched; compact diagnostics may encode them as hex strings to avoid browser rounding, without changing the current retained event representation. Values outside the new authored numeric range remain usable through legacy APIs/files; migration reports the limitation instead of truncating.

Sample rates retain the current outer 1000..192000 Hz range, but validate **feature-specific minima** before synthesis. For example, current hall/Voice reverb filters use a fixed 5 kHz cutoff and need a rate above 10 kHz; air's fixed filter has its own constraint. Do not claim every source works at the outer minimum or quietly change DSP filters as part of this DSL. Validate imported sample rates and metadata before large decode allocations; then check actual decoded shape, length, and finiteness.

Local asset paths are resolved relative to the owning project, with canonical resolved paths and content hashes. Default new DSL resolution stays inside the project directory; explicit CLI `--asset-root` may authorize additional local roots. Recheck resolved symlink/junction targets. Never fetch URLs or import modules. This is path/dependency control, not a claim that a non-executable file is a complete security sandbox. No multi-file definition imports in v1; Voice JSON and PCM assets are sufficient initially. Missing files, missing natural banks, and changed assets have precise errors/dependency states.

## 12. Compact discovery, queries, errors, and existing workflow integration

Add a small `dsl` command group; keep rendering/playback/export in the existing commands where practical:

```text
tare.tools.tune dsl catalog --domain sfx --name ui --json
tare.tools.tune dsl check bank.tune.json --name confirm --expand --json
tare.tools.tune dsl query bank.tune.json --target sound:confirm_strong --json
tare.tools.tune dsl expand bank.tune.json --name confirm --view layers --limit 5 --json
tare.tools.tune dsl patch bank.tune.json --patch edit.json --json
tare.tools.tune capture bank.tune.json --name confirm -o output/dsl
tare.tools.tune inspect <bundle-directory> --view layers --top 3 --start 0 --end 0.15 --band 2000 6000 --no-pitch --json
tare.tools.tune studio bank.tune.json --name confirm -o output/dsl-live
tare.tools.tune midi music.tune.json --name theme -o output/theme.mid
tare.tools.tune export bank.tune.json -o output/bank --ogg
```

The `dsl` group also hosts `capabilities`, `migrate`, `freeze`, and a bounded variant generator when those milestones land. It does not need a REPL/server protocol, a new binary, or aliases for every existing command. Add `--name` to MIDI through the shared loader; current MIDI bypasses `build_file` and cannot be assumed to understand new banks automatically.

### Query/projection contract

All new machine responses use strict JSON with an explicit schema identifier. stdout contains exactly the requested machine payload, stderr contains structured errors in JSON mode, and logs/debug output cannot pollute stdout. Exit 0 success, 2 invalid input/capability, 3 revision conflict, 4 build/dependency failure; reserve unexpected failures for ordinary nonzero internal-error handling. Existing command output remains compatible unless a new option is selected.

`catalog` uses an explicit, tested allowlist registry. It returns operation/recipe name, concise meaning, result type, defaults, ranges/units, events/styles, capability flags, and one small example. Domain/name filters precede pagination; default lists contain names and summaries, not the complete schema of all 43 instruments and every Sfx recipe. `--fields` accepts a documented field allowlist; it is not a general query language. Exact names and enum suggestions are ranked deterministically.

`query` inspects **authored data** without rendering and returns authored revision, selected target, effective parameter bindings if requested, dependency/impact counts, and a bounded fragment. `expand` inspects the compiled/materialized view without DSP where possible, and explicitly says when asset-backed planning occurred. Inspection of audio uses a saved bundle whenever available; it must not rebuild just to project fields.

Add `inspect --view summary|layers|events|full`, `--top`, `--limit`, `--cursor`, `--fields`, and existing stage/time/band selectors. With no new view option, preserve current `--json` output. Suggested new-view defaults: summary contains identities, status, duration/channels/rate, selected levels, capability/attribution caveats, and links/targets; layers contains only the selected stage's ranked rows, **without** full `planned`, `layer_catalog`, raw parameter arrays, or pitch frames. Detailed data remains opt-in.

Example compact layer result:

```json
{
  "schema":"tune.query/1","revision":"<capture-revision>",
  "analysis_id":"<analysis-id>","query_id":"<projection-id>",
  "stage":"n1","window_s":[0,0.15],"band_hz":[2000,6000],
  "measure":"channel-sum energy before parent bus; not additive attribution",
  "items":[{"id":"n1/p0","target":"sound:impact/id:metal","generated_path":"/modal/0","kind":"modal","power":0.012}],
  "total":9,"returned":1,"truncated":true,"next":"<revision-bound-cursor>"
}
```

The values above illustrate shape, not measured findings. Keep absolute sample/time coordinates and selected stage explicit. A user can request source fields for one row, follow the authored target, and use its returned materialized guard. All cursors bind revision, view, filters, sort, and offset. A stale cursor fails; never page across revisions. Default summaries omit speech text/full source; a requested source view gives the relevant bounded excerpt. A byte ceiling protects transport but is not called a token budget. A `max_tokens` feature would require an explicitly selected tokenizer and is not needed in v1.

Refactor expensive analysis so selection and pitch-off behavior happen **before** unnecessary report construction; do not serialize a huge report and only then slice the JSON. Preserve the analyzer's identity contract for the full semantic result, and identify projection separately. Do not alter legacy analysis IDs during this refactor without versioning the analyzer. Quantify output size and latency separately.

### Capture, workers, player, and exports

- `authoring.build_file()` becomes the shared legacy/DSL dispatcher; a loader returns selected source, context, dependencies, and provenance. Keep `materialize()` as the legacy adapter. Existing Python capture APIs remain available.
- `studio_worker` uses the same dispatcher and returns structured bounded errors along with a machine result. The HTTP controller still publishes only a fully verified immutable bundle and rejects stale generations. Do not run builders or arbitrary `.py` in workers.
- Replace ad-hoc new-format file scanning with loader-reported dependencies. Watch main JSON, external Voice specs/PCM, referenced banks, and relevant compiler/renderer code. Missing dependencies remain watched so creating/fixing them triggers recovery. Include assets needed by the selected sound; named sound enumeration should not render every bank entry.
- Studio accepts new metadata, compact inspection, and source links. A source target from a historical bundle always includes that revision and authored source snapshot; it must not silently edit today's unrelated object. Initially patches remain CLI operations; browser source editing is not required to complete the authoring loop.
- Keep existing revision-bound notes, answer-version conflicts, exact playback identity, blind comparisons, and last-good behavior. New authored identities help navigation; they never transfer listening annotations to new audio automatically.
- MIDI receives the compiled Score with final transformed events and original per-note layer hashes. Retain quarter-note meter, 960 PPQ, current overlap/channel constraints, and explicit approximation behavior. New data instrument templates require a declared mapping or an error. A root containing placed audio is not exact MIDI; report omitted placements only with explicit approximation. Mixed-tempo nested Scores/Cues remain PCM placements unless a future exporter explicitly models tempo maps.
- Existing sprite/WAV/Vorbis export consumes completed captures, preserves sample coordinates, and verifies decoded output as before. Extend bank discovery through the shared loader; do not duplicate source dispatch in CLI. Failure must not replace prior exports. Neither JSON compactness nor a new authored ID can change codec padding/endpoint contracts.

## 13. Python builders and reusable instruments

The Python API is a convenience layer over the declarative model, not an independent execution route:

```python
from tare.tools.tune.dsl import (
    Project, definition, param, use, sfx, pattern, transpose, velocity,
)

confirm = definition(
    sfx("ui", style="crystal", event="confirm", species=7,
        power=param("power"), dry=True),
    params={"power": {"type": "number", "default": 0.5, "min": 0, "max": 1}},
)
motif = definition(pattern("C4 - E4 - G4 - . .", steps=2))
project = Project(
    context={"sample_rate": 16000, "bpm": 120, "meter": 4},
    defs={"confirm": confirm, "motif": motif},
    sounds={"confirm": use("confirm", power=0.65)},
)
answer = use("motif").then(transpose(12), velocity(0.8))
project.write("bank.tune.json")
assert Project.from_dict(project.to_dict()).to_dict() == project.to_dict()
```

Every builder is immutable and emits exactly the documented JSON shape. `use(..., power=...)` emits `with`; `.then(...)` emits the ordered Notes transform list. Builders do not synthesize, assign hidden random seeds, add global registries, or serialize arbitrary callables. Both builder and file inputs call the same validator/compiler. Passing numpy audio or an arbitrary function to a serializable builder fails with an actionable message; existing `Score.add(array)` and `Track.play(callable, ...)` remain the trusted Python escape hatch and can still be captured observationally.

Do not ship dozens of overloaded magic methods or mutate existing `Creature`, `Sfx`, `Speaker`, and `Score` APIs into fluent DSL objects. Provide constructors for the documented operations, `to_dict`, `from_dict`, `write`, and the shared compile/build entry point. No operator precedence puzzle is necessary for a small token saving.

### Declarative instrument templates: complete roadmap capability

A new instrument is a bounded Layer template with local Note slots, evaluated by a compiler-owned callable exactly once per Note through `Track.play()`:

```json
{
  "params":{"tail":{"type":"number","default":0.05,"min":0,"max":0.2}},
  "body":{"instrument":[
    {"id":"fundamental","syllable":{
      "start":{"note":"start"},
      "dur":{"note":"dur","offset":0.05},
      "pitch":[[0,{"note":"f"}],[1,{"note":"f"}]],
      "source":"sine","release":{"param":"tail"},"gain":{"note":"vel"}
    }},
    {"id":"upper","syllable":{
      "start":{"note":"start"},"dur":{"note":"dur"},
      "pitch":[[0,{"note":"f","scale":2}],[1,{"note":"f","scale":2}]],
      "source":"sine","gain":{"rand":"upper-level","min":0.03,"max":0.07}
    }}
  ],"midi_program":79}
}
```

Store that definition as `defs.glass_sine`, then use `"instrument":{"use":"glass_sine","with":{"tail":0.08}}` on a track/clip. Note slots correspond to current `Note.start`/`dur` in seconds, `f` in Hz, and `vel`. Optional `scale` and `offset` apply the fixed affine rule `value * scale + offset` to numeric slots; finite bounds are checked after substitution. There is no general expression evaluator. `rand` is permitted only in instrument templates, maps to `min + (max-min) * note.rand("dsl:" + name)`, and has explicit finite bounds. The template cannot choose arbitrary code, files, or recursive instruments. Its resulting Layer count and duration are charged before expensive synthesis.

The expansion records a declared instrument identity and template/materialization hash as provenance; it leaves Note.seed and existing render seeding untouched. Template/definition renames must not alter PCM. `midi_program` means an explicit GM approximation of timbre, not preservation of synthesis; the exported event pitch/timing/velocity must still match. Instruments returning unsupported layer types for a Track fail before rendering—current `Track.render()` supports Syllable/Chip/Modal/Noise/Scatter, not every Voice layer. Speech-containing templates can be authored as sound placements; extending Track's supported types is a separate justified change, not assumed by this plan.

## 14. Representative end-to-end workflows

### A. Small semantic edit with a useful first release

1. `dsl catalog --domain sfx --name ui --json` discovers real events/styles/knob ranges without listing the entire engine.
2. Write the compact parameterized confirmation bank from section 3; `dsl check --expand` validates it and returns capabilities/costs.
3. Capture the selected sound and open it in the existing Studio player. Inspect the saved bundle with top three rows for the troublesome band/time range.
4. `dsl query --target sound:confirm_strong` returns that invocation and authored revision. Submit the section 8 patch changing `/with/power` to 0.65.
5. The file is atomically updated, the watcher publishes a new verified bundle, and the prior revision and its listening notes remain available. Compare ordinary rebuilt audio or a separate frozen-factor diagnostic intervention as appropriate.

Acceptance: the agent sends only a small patch after the initial file, receives bounded responses, and reaches a valid render/export without needing full-source re-emission. Measure tokens for the whole interaction, including catalog/error traffic and repairs.

### B. Semantic recipe refined at primitive level

1. Build and inspect `Sfx("ui","crystal")` confirmation. Ask `expand --view layers` for the actual generated structure and its guard.
2. Keep the shared definition unchanged; wrap only `sounds.confirm_strong` in the section 7 guarded `edit`, selecting an actual Modal hardness field and Voice lowpass.
3. Rebuild. The source map shows both the definition and materialized override. Compare against the previous captured revision; native/Voice export remains available only if the result's actual features are supported.
4. Change recipe parameters later. If the underlying expansion changes, receive `E_OVERRIDE_STALE` with the current small expansion summary. Choose a new target/guard explicitly; do not apply the old index to a different layer.

An independent custom Noise/FM/PCM accent is placed with `mix`, which has separate normalization. If the goal is a shared Voice bus, append a low-level layer through the guarded Voice override capability or author the Voice explicitly. The tool never treats those two requests as equivalent.

### C. Reusable music with pauses and a local transposition

Use a three-beat meter at 120 BPM and a phrase `{"pattern":"C4 - . . . .","steps":2}`. Its span is **three beats**, although its note ends at beat one. Repeating it twice starts the next C4 at beat three, not beat one or at the instrument's ring tail. A two-bar loop has six beats/three seconds at this tempo.

Put the motif behind a definition and one track/clip invocation. Patch that invocation's `then` list to add `{"transpose":-12}`; the rest of the arrangement need not be re-emitted. Compile from notes before `Track.play()`, inspect retained event pitches/times, and export MIDI. Independently parse the MIDI and verify the held durations, rests, meter, and repeated onset. Do not assert identical subsequent seeds after inserting/removing events: legacy order still applies.

### D. Creature/speech/music scene with PCM boundaries

Create a parameterized creature call, a named Speaker descriptor, a spoken line, and a Cue as ordinary definitions. Sequence them with explicit scheduling spans, mix a local WAV contact at a sample-aligned `at`, and add the existing optional Score limiter. The source map must retain all invocation/asset/Cue wrapper lineage. PCM export and listening work; a request for one portable Voice or exact all-material MIDI returns a capability error explaining which nodes require PCM. A missing natural bank fails the new build while last-good audio remains accessible.

### E. Deterministic variations and reusable low-level instrument

Generate four named sound invocations with explicit takes 0–3 and a common species. Rebuild twice and compare PCM/bundle identities under the same environment. Changing a name/ID is source-only; changing take is an intentional variation. Separately use the section 13 instrument template on two note phrases, verify one template invocation per Note and deterministic `Note.rand` values, and export timing/pitch with a declared GM mapping. No arbitrary Python is needed in either project.

## 15. Measure end-to-end token and task efficiency

The principal hypothesis is that semantic reuse plus compact responses and small edits reduces the **total tokens needed for a correct audio task**. It is currently unmeasured. Define the protocol and baseline before optimizing syntax.

Use a committed task corpus with at least these families: single recipe; four parameter/take variants; creature plus speech scene; eight-bar musical arrangement with repeated motifs; high-to-low refinement; a localized edit in a larger bank; a diagnosis/repair of invalid input; and a capability/export failure followed by the correct path. Include two-turn/three-turn edits, trailing rests, a stale override, a missing asset, and an intentionally ambiguous request requiring discovery. Provide exact semantic and artifact acceptance predicates; use listening judgments for subjective quality separately from structural correctness.

Compare three implemented paths: current Python APIs, current JSON project + existing CLI, and new DSL + compact CLI. For construction-only subtasks also compare the thin Python builders. A **small mocked textual candidate** may be measured offline on the same authored examples, but cannot be claimed as a task-success result until it actually parses, edits, errors, and renders. Do not compare an optimized DSL success against an artificially verbose legacy prompt or omit legacy's reusable Python variables.

For each task/run, retain prompts, actual tool requests/responses, source/patch bytes, diagnostics/errors, repair turns, final artifacts, and independent pass/fail results. Count tokens with the exact model's tokenizer and version where available, and record model token usage when the execution API supplies it. If only a proxy tokenizer is available, label it explicitly and report at least two relevant tokenizers rather than asserting a model-specific saving. UTF-8 bytes, tokens, wall time, and billable/reasoning usage are separate columns.

Report both (a) unique authored/tool content tokens and (b) summed per-request input/output tokens, including repeated conversation context, cached-input accounting where exposed, errors, repairs, and mandatory documentation overhead. Do not multiply one static file ratio into a total-cost claim. Count the compact catalog loaded at the start; include first-use and warmed-familiarity tasks separately. Include truncated-output follow-up requests so aggressive projection cannot win by hiding necessary evidence.

Hold model/version/effort/tool access/task instructions constant, randomize order, use fresh sessions for cold tasks, and pair task seeds/inputs. Start with a cheap deterministic replay corpus and explicit tokenizer measurements. A live-agent pilot then uses at least three runs per task/path, increasing only where variance makes the result inconclusive. Record success rate, total tokens per successful task, tokens wasted in failures, tool calls, repair turns, end-to-end time, compile/render time, peak memory estimate/measurement, and artifact correctness. Pin package/compiler/renderer/source versions. No costly model benchmark is authorized by this planning turn; its runtime/quota budget must be specified when implementation reaches that gate.

**Proposed release targets, not achieved results:** no material task-success regression; median total tokens per successful task at most 70% of the better current route on the multi-step corpus; at least 50% reduction for the large-bank local-edit subset; p90 total tokens no worse than the baseline; deterministic and export acceptance unchanged. A small pilot cannot prove a tiny success-rate difference, so publish uncertainty and task-level paired results, not spurious statistical certainty. Failure to hit targets blocks the claim “token efficient” and triggers investigation; it need not discard useful semantics if they are clearly labeled experimental.

If syntax punctuation dominates after output/patch improvements, prototype a small text surface **over the same model** and rerun the protocol. If discovery/errors dominate, fix registry/query ergonomics first. If rendering dominates time, report that separately; a token-saving feature is not necessarily a faster renderer. Do not add persistent caching, new DSL operators, or a parser solely to improve a synthetic character-count score.

## 16. Dependency-ordered implementation sequence

Deliver in small reviewable changes with behavior gates. Filenames below are proposed; existing files are modified only where the named integration requires it. Implementation is not authorized by this planning document itself.

### M0 — Freeze contracts and the comparison corpus

**Files:** `docs/dsl.md`, `docs/pt-BR/dsl.md`, `tests/fixtures/dsl/`, `tools/bench_dsl.py` (initial protocol/corpus mode), existing authoring fixture references.

Tasks: write a normative schema/registry draft from this plan; freeze representative legacy source/Voice/PCM fixtures without regenerating “expected” audio from modified code; record the current pattern spans, note-call seeds, Score.add conversions, Cue wrapper, and supported native matrix. Add the three-beat/trailing-rest case. Define benchmark tasks and retain honest current-route examples. Confirm defaults/ranges from actual adapters, including feature-rate constraints. Capture Python/numpy/scipy/platform identity and source hashes. With no Git in this workspace, take an external snapshot before production edits and retain a file-level change manifest; do not rely on an unavailable rollback command.

**Gate:** contracts are executable as fixtures, historical baselines are immutable, and source/library changes are detectable. No whole renderer refactor is bundled here. Reuse the existing frozen authoring corpus rather than creating redundant giant recordings.

### M1 — Strict loader, registry, semantic leaves, definitions, and compact workflow

**New modules:** `src/tare/tools/tune/dsl/__init__.py`, `model.py`, `registry.py`, `validate.py`, `compiler.py`, `query.py`, `patch.py`.

**Integrations:** `authoring.py`, `cli.py`, `inspection.py`, narrowly `studio_worker.py`/`studio.py` for recognized sources/errors. **Tests:** `tests/test_dsl_loading.py`, `test_dsl_recipes.py`, `test_dsl_queries.py`, `test_dsl_patch.py`.

Tasks: discriminator dispatch and strict new schema; leaf Sfx/Creature/Speaker/Cue/Voice-spec/PCM/FM adapters; scalar parameters and acyclic `use`; named sounds; source maps and authored revisions; catalog/check/query; bounded inspection views preserving old output defaults; semantic `set` with preconditions and atomic publication of the source file. Primitive `voice` construction may begin with Syllable/Modal/Noise/Scatter, but reject unsupported constructors explicitly until M2. Preserve raw `spec` access to existing Voice families from the outset. Route existing capture/Studio through the shared dispatcher.

**Early complete usable slice:** author/reuse a parameterized Sfx or creature, render/capture it, inspect a bounded result, patch one invocation, rebuild in Studio, compare retained revisions, and export PCM or a supported Voice. This is a real vertical workflow, not only a parser. Composition and music transformations are not yet advertised as delivered.

**Gate:** direct API and DSL leaf PCM/spec/seed equality; query includes exact edit target/revision; 2,000-row source/report is not required for one edit; invalid/stale patch writes nothing; valid source plus failed render preserves previous audio; existing legacy projects/tests remain unchanged. Run the relevant authoring/curator/recipe subsets once; do not rerun native jobs for catalog-only edits.

**Early efficiency checkpoint:** run a cheap local tokenizer comparison on three deterministic, actually executable transcripts: initial construction, one local parameter edit, and diagnosis/repair of an invalid value. Include catalog/query/error output and full required source/patch input for both old and new routes. Record tokenizer/version, content tokens, tool-call counts, and artifact success; this is a transcript-size checkpoint, not a live-agent task-success or billable-cost claim. Resolve obvious input/output verbosity regressions now, before widening the language. No paid model run is required for this checkpoint.

### M2 — Layer coverage, units, note sequences, and reusable musical composition

**New modules:** `dsl/units.py`, `dsl/notes.py`, `dsl/transforms.py`. **Integrations:** `dsl/compiler.py`, `patterns.py` only for bounded diagnostics/spans without changing existing parse semantics, `score.py` only for necessary provenance hooks. **Tests:** `test_dsl_notes.py`, `test_dsl_primitives.py`, `test_dsl_limits.py`.

Tasks: all current Layer adapters; Voice grouping and stable authored handles; typed Notes parameters; pattern/notes/chord/degrees; span-preserving seq/repeat/overlay; transpose/stretch/velocity/retrograde/quantize/humanize; Score tracks/clips and current bus/effects settings; exact call-order lowering; units and structural budget preflight. Plain Score notes can ship before mixed-sound placements; reject unavailable composition forms rather than treating them as ignored fields.

**Gate:** independent expected event vectors for non-four-beat meter, leading/trailing rests, chords, fractional pitches, holds, offsets, nested repeat, and transform ordering; randomized bounded expression tests compare a simple independent timeline oracle; one invocation per instrument note; seed vectors pin legacy order. Reject type mixes and all expansion bombs before allocation. Voice primitive/export serialization equals equivalent direct construction; no diagnostic metadata enters Voice fields.

**Expanded efficiency checkpoint:** extend the local transcript corpus to a repeated musical motif, a three-beat trailing-rest edit, and a primitive/units error with repair. Compare the new notation and queries against equivalent current Score/Python and project workflows using actual tokenizers. Fix recurring verbosity or confusing schemas before M3–M6. The full fresh-session, authorized live-agent qualification and aggregate targets remain at M7.

### M3 — Sound composition, subcapture lineage, and schema-2 replay

**New module:** `dsl/composition.py`; small source-map/merge helpers may stay there until a second caller warrants a module. **Integrations:** `diagnostics.py`, `bundles.py`, `inspection.py`, `authoring.py`; existing Score DSP functions stay unchanged. **Tests:** `test_dsl_composition.py`, `test_dsl_replay.py`, additions to existing authoring workflow tests.

Tasks: typed sound seq/repeat/mix/rest; PCM/Voice/Cue/Score placements; exact child conversion/gain and nested capture links; cumulative budgets; dependency/asset union; graph validation; schema-1/2 readers; transformations into artifact coordinates for placement, loop, and Cue fade; proper stage-scoped ranking and replay.

**Gate:** compare each composition with an explicitly equivalent current Python Score pipeline; exact unchanged PCM with capture on/off and replay of the original; mute/solo retains lengths, surviving buffers/seeds, factors, and limiter envelopes. Cover nested normalization, zero/silent sources, stereo anti-phase, stereo pan rejection, looped tails, Cue truncation/fade, repeated occurrences, changed bank contents, and missing assets. Saved/reloaded bundle replay matches the original. Schema-1 fixtures continue loading; old readers must reject required schema-2 behavior.

### M4 — Guarded refinement, structural patches, and semantic impact queries

**New module:** `dsl/overrides.py`. **Integrations:** `dsl/query.py`, `patch.py`, `compiler.py`, inspector source navigation. **Tests:** `test_dsl_overrides.py`, patch concurrency/rename/impact cases.

Tasks: expansion views/materialized hashes; Voice field `edit`; typed append/remove with lineage; authored ID/pointer selectors; insert/remove/move/rename and instance-vs-definition impact; exact guard errors. Add materialized Score/Cue synthesis/bus overrides after Voice semantics pass; reject post-expansion timing mutation. Keep ordinary rerender and diagnostic mute separate. Do not add a broad CSS/JSONPath selector engine.

**Gate:** demonstrate section 14B without freezing/copying the recipe; old guard cannot target a changed generated layer; rename authored IDs/definitions preserves audio; layer insertion documents changed downstream seeds; no false MIDI regeneration claim; conflicting patch operations and concurrent writers cannot silently lose data through supported tool paths. Historical source links never edit current source without a new authored revision check.

### M5 — Thin Python builders, typed composition parameters, and declarative instruments

**New module:** `dsl/builders.py`; template support in `dsl/instruments.py` if its scope warrants separation. **Integrations:** `__init__.py` exports only stable names; `midi_export.py` receives explicit new-instrument mappings through the adapter. **Tests:** `test_dsl_builders.py`, `test_dsl_instruments.py`.

Tasks: immutable data builders and round-trip equality; sound/notes/layer/speaker/instrument parameter types; affine Note slots and bounded Note.rand templates; explicit MIDI program metadata; reject Python callables in serializable data; variant CLI generator writing ordinary invocations. Maintain the existing trusted Python callable path.

**Gate:** equivalent builders/JSON yield the same normalized source, seeds, PCM, and capabilities; templates run once per Note and cannot access code/files; all four inherited contexts (beat/seconds/parameters/seed) are explicit; output limits apply after substitution; template renames are audio-neutral. Compare helper readability/token costs before adding more sugar.

### M6 — Complete product integrations, migration, and portable export

**Integrations:** `authoring.py`, `cli.py`, `studio.py`, `studio_worker.py`, `ui/studio.html`, `midi_export.py`, `exports.py`; **new** `dsl/migrate.py`. **Tests:** `test_dsl_workflows.py`, independent MIDI parsing, sprite decoding, browser workflow checks where UI changed.

Tasks: shared selection/dependency resolution everywhere; MIDI `--name`; source/asset watching including missing dependency recovery; structured worker errors; compact source navigation; bounded bank export; Voice export/capability checks; opt-in migration/freeze tools. Add examples `examples/dsl-bank.tune.json`, `dsl-music.tune.json`, `dsl-primitives.tune.json`, and a builder example. Update primary guides and pt-BR companions together.

**Gate:** sections 14A–E work end to end through CLI and player; old tabs/stale workers/conflicting notes retain existing protections; exports parse/decode correctly; schema-1 historical bundles still replay; migration equivalence report is explicit. Execute actual supported native/Godot checks for exported Voice fixtures before claiming portability; skips are not a pass.

### M7 — Efficiency benchmark, compatibility release, and stabilization

**Files:** `tools/bench_dsl.py`, `tests/fixtures/dsl/bench/`, `docs/dsl-benchmarks.md`, release/verification notes with exact commands and environment.

Tasks: complete deterministic corpus/tokenizer accounting; run the bounded authorized live-agent comparison; inspect failures and repair costs; tune catalog/queries or syntax based on evidence; run focused suites after fixes, then one full suite and actual required native/Godot jobs for the release candidate. Perform targeted listening/blind comparisons for behaviors that intentionally change sound, without interpreting structural test passes as acoustic approval. Freeze version-1 grammar/defaults only after the results are reviewable.

**Gate:** correctness/compatibility gates pass, known limitations are documented, benchmark data supports any efficiency claim, docs/examples execute, and package/wheel includes new data/modules. If token targets fail, keep experimental labeling and an honest report; do not claim success from source-byte reduction. No need to repeat expensive full/native suites after documentation-only refinements.

Dependency graph: `M0 -> M1 -> M2 -> M3 -> M4`; M5 depends on the M2 type/Notes contracts and joins M4 before M6; M6 plus the benchmark corpus feed M7. A single implementing agent can follow the linear M0–M7 order. This plan does not require parallel agents or a distributed implementation process.

## 17. Migration and release compatibility

Old JSON/Python APIs remain supported and retain their existing parsing/audio behavior. Do not silently migrate files on read or change the meaning of `type`, `options`, `settings`, `bars`, or raw Voice `loop`. New DSL files use a different discriminator. Preserve existing sound names and selection behavior through the shared dispatcher.

`dsl migrate old.json --output new.tune.json` is opt-in and writes a new file. It maps direct leaves, current Score settings/tracks, and sound banks; preserves resolved recipe parameters, sample rate, Score track names, event/call order, primitive data, reference asset links, and loop meaning. For `bars`, emit an explicit Score loop duration in bars. Preserve pattern text/steps and now retain span, but do not add a repeat/sequence that changes the old source's schedule. Never infer missing semantic definitions from coincidentally identical source fragments; extraction of reuse is a separate optional edit.

Migration returns field-level warnings and an equivalence report. Duplicate legacy track names, ignored unknown fields, unsupported out-of-range authored seed numbers, implicit defaults that depend on runtime registry versions, and arbitrary Python objects cannot be assumed lossless. For each, either emit a faithfully frozen result with its loss of editability/capability stated or refuse automatic migration and keep the legacy file working. Do not let strict new validation silently “repair” old sound behavior. A valid old project is not retroactively invalid because the new DSL is stricter.

For supported cases, compare materialized Voice/Score structure, call grouping, resolved seeds, PCM shape/dtype/samples, and export semantics in the pinned environment. Source/revision hashes necessarily change on migration; PCM should not for equivalence cases. Store both provenance revisions and the report. An equivalence failure prevents a claim of lossless migration; it does not overwrite the source.

`dsl freeze` explicitly exports a portable Voice where possible or a retained PCM/bundle otherwise. Freezing gives reproducible materialized playback and loses some editable recipe intent; include the source link. It must not serialize arbitrary Python callable names and call that a regenerable program. Source regeneration additionally requires compatible compiler/renderer and the exact assets. Version-1 DSL unknown fields fail; future syntax is introduced by versioned adapters/migrations, not by permissive field dropping.

## 18. Failure matrix and meaningful acceptance tests

These are behavior tests, not tests that merely restate private helper implementations:

| Failure/ambiguity | Required observable result | Evidence/test |
|---|---|---|
| Misspelled knob/field or two operation keys | Exact pointer, finite suggestions, no render | CLI structured-error assertion; verify no output bundle |
| A uses B uses A, or nested 256x repeat | Cycle/cost error before materialization/allocation | Instrumented leaf call counter remains zero |
| Pattern ending in silence in 3-beat meter | Second repetition starts at phrase span | Independent event and MIDI vectors from section 14C |
| Rename authored ID/definition | Same audio/seeds, changed provenance as applicable | PCM equality and source-map comparison |
| Add/remove earlier note/layer | Current legacy downstream seed effects retained | Frozen Note/layer seed vectors, not a new ID-seeded oracle |
| Copy/reuse mutable recipe | Editing instance A does not mutate B | Two independent instances and baseline PCM/spec comparison |
| Parent normalizes a quiet child | Report actual stages; no absolute-gain promise | Compare to manual current Score pipeline |
| Solo/mute versus ordinary edit | Frozen replay and rerender remain distinct operations | Surviving-buffer equality, length/factor checks, nonlinear case |
| Generated layer moved by recipe change | Guard failure; no silent override retarget | Changed params/recipe fixture with stale materialized ID |
| Stereo PCM pan request or rate mismatch | Explicit capability/input error | Right-only and anti-phase signals; no silent conversion |
| Asset replaced under same filename | Dependency/render/revision changes | Content-hash fixture with identical path |
| Old tab/worker/patch | Conflict/stale discard; old audio/notes preserved | Existing concurrency tests extended to authored revision |
| Cue with end fade inside mix | Correct final duration/fade and mapped query coordinates | Manual Cue.render baseline plus nested replay |
| Low-level note layer edit followed by MIDI | Reject or explicitly approximated original notes | Never rewrite hashes to pass export |
| Unsupported native/FM/effects export | Capability list identifies exact boundary | Actual native supported fixtures and negative cases |
| Oversized imported PCM or dense modal/frame data | Reject before excess retained allocation | Header-first/budget spy and bounded process test |
| Compact output omits needed evidence | Explicit truncation/cursor and next query | Agent benchmark counts follow-up tokens, not just first page |
| Old Voice/project/bundle | Existing behavior remains available | Independent frozen legacy samples/schema-1 bundle fixtures |

Use property-based or table-generated bounded tests for transformation algebra where they test real semantics: transpose twice equals summed transposition; repeat preserves trailing rests; stretch scales onset/hold/span; builder serialization round-trips; stable source labels cannot enter seeds. No new production test dependency is necessary initially—deterministic generated cases suffice. For ambiguous rounding, use hand-calculated independent expected sample/tick coordinates. Do not compare only two routes through the same new compiler.

## 19. Deliberate deferrals and overengineering to avoid

| Deferred capability | Reason and available path |
|---|---|
| General custom textual language | Parser/editor/error cost is unproven; benchmark after JSON+queries+patches |
| Arbitrary expressions, scripts, imports, functions in data | Breaks inspectability and bounded execution; trusted existing Python remains available |
| Persistent content-addressed compiler/render cache | Identity correctness and asset invalidation first; per-build immutable memoization is enough |
| Graph database, plugin marketplace, network package manager | Not required for named local definitions and current registries |
| Stable randomness under every musical edit | Changes legacy audio; future explicit behavior mode, independently tested |
| DAW-style tempo maps, automation lanes, MPE, arbitrary time signatures | Current Score/MIDI model does not support them; constant-tempo notes and explicit primitive curves cover initial use |
| Pitch/time transforms on arbitrary PCM | Requires new DSP and quality assessment; use recipe controls or existing vocoded fields where supported |
| Redesigning normalization, absolute loudness, buses, effects | Separate sound-engine behavior project; expose current boundaries honestly |
| Automatic semantic layer roles for every recipe | Current designs lack trustworthy metadata; adopt opt-in tags for selected recipes only when justified |
| Lossless reconstruction of editable Cue recipes from captured events | Original call grouping/generative intent is not retained; keep recipe or guarded materialized refinement |
| Browser source editor and format-preserving JSON patch engine | CLI patches plus watcher complete the workflow; measure demand before more UI/parser infrastructure |
| Multi-file definition libraries and remote assets | Adds import resolution/versioning/cycle/watch complexity; one file plus local Voice/PCM assets first |
| Streaming very large bank export | Current capture/export has bounded in-memory assumptions; reject/split batches until a real need justifies streaming |
| Native execution of the DSL | Compile to existing supported Voice or bake PCM; no native engine rewrite |

These are explicit scope boundaries, not omissions of the requested semantic-to-primitive workflow. The full roadmap still includes all present source families, reusable definitions/parameters/variants, note transformations, both Voice and PCM composition, guarded low-level edits, declarative instrument templates, compact discovery/diagnosis, incremental patches, integrations, and end-to-end efficiency evidence.

## 20. Remaining uncertainties and the tests that decide them

- **Hypothesis: JSON plus semantic primitives is token-efficient enough.** Resolve with the paired task corpus, real tokenizer counts, repair turns, and output traffic. Do not claim it from examples.
- **Hypothesis: child capture linking is a small integration.** Resolve in M3 with exact dtype/gain/replay and coordinate tests before broad composition release. The fallback remains a narrow capture placement API around unchanged DSP.
- **Unknown: safe cost ceilings for unusual legitimate voices.** Resolve with existing examples/assets and measured memory/time; change documented limits before v1 freeze, never disable them to pass an example.
- **Unknown: registry metadata completeness across all recipes/instruments.** Resolve with enumeration tests and adapter-specific schemas. Missing metadata yields a precise unsupported field/capability, not broad reflective invocation.
- **Unknown: which generated layer roles are valuable and stable.** Resolve from actual override tasks; start with structural guarded paths and hand-authored IDs.
- **Unknown: perceptual usefulness of particular recipes/edits.** Resolve with listening in retained revisions/blind comparisons. A deterministic valid render is not evidence of good sound.

The implementation can proceed without leaving the main architecture or language semantics undecided. Review these uncertainties at their named gates; avoid converting them into speculative infrastructure before there is evidence.

