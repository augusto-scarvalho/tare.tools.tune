# DSL implementation planning brief

Requested on October 31, 2026. This brief describes the task and current observations; it does not prescribe an architecture.

## User request

The user wants a DSL an AI coding agent can use with fewer tokens and a higher-level semantic vocabulary, while retaining primitives for detailed low-level sound work. The user then explicitly requested a complete implementation plan from **Astra, xhigh** for the implementing agent.

Original wording: "Mas em termos de uma DSL que você consiga usar e poupar tokens e ter um domínio semântico de maior grau de abstração, mas ao mesmo tempo te entregue primitivas que te permitam a fazer trabalhos de mais baixo nível, como está nossa implementação?" Follow-up: "Coloca o astra xhigh pra pensar em um plano de implementação bem completo pra você".

Earlier context: the user objected when a simplification dropped too much of an earlier plan. Avoid both speculative infrastructure and silently removing requested capability. Explain concrete deferrals and tradeoffs.

## Current implementation observations

- High-level semantic APIs exist: `Creature`, `Sfx`, `Speaker`, `Cue`. Sfx recipes expose named controls and knob metadata. Score supports note/instrument arrangement, chords/scales, custom instrument callables, and placed Voice/PCM audio.
- Low-level data primitives include `Voice`, `Syllable`, `Modal`, `Noise`, `Scatter`, `ChipProgram`, speech layers, envelopes, and curves. FM and optional Score chorus/limiting are separate Python PCM/Score functionality, not new native Voice fields.
- `patterns.py` parses notes/chords, rests, holds, accents, and bar checks. General reusable expression composition and transformations are not exposed by this parser.
- `authoring.py` accepts a JSON source or sound bank, dispatches supported source types, and builds captures. It has no shared definition/reference mechanism or general composition between recipe sources and primitive sources. Python can already combine levels directly.
- `Track.play()` expands notes immediately and keeps event provenance; its legacy random stream depends on layer counts and iteration order. Rendering groups layer kinds and has additional existing seed conventions. Authored semantic names and diagnostic node IDs must not accidentally redefine those conventions.
- Existing authoring infrastructure includes observational captures, immutable bundles, separate source/render/PCM/playback/analysis identities, captured bus factors, gain-frozen diagnostic replay, clean background workers, content watching, last-good recovery, revision-bound notes, blind comparisons, MIDI, and web sprites.
- Inspector JSON includes full planned/source structures and layer metadata. In a previously saved example, compact full JSON measured 29,960 UTF-8 bytes; a manual top-three projection measured 426 bytes. These are **byte counts, not tokenizer measurements**, and that projection is **not an existing CLI feature**. Use them only as motivation to measure actual end-to-end token cost properly.
- The latest implementation verification record reports a full Windows run of 490 passed/48 native availability skips, a later focused run of 24 passed, and WSL native/Godot checks of 51 passed/no skips. These are previous recorded results, not checks rerun for this planning task.
- There is no `.git` directory in this workspace. Existing source and local generated artifacts must be preserved.

## Planning expectations

Inspect the actual source and tests, distinguish existing behavior from proposals, and choose a coherent implementation direction. Evaluate alternatives rather than assuming that a fluent Python API, a custom text parser, or JSON is necessarily the right primary authoring surface.

The plan should be concrete enough for another agent to implement: syntax/API examples; semantics; representation and compilation; compatibility; reuse and parameterization; transformations and incremental edits; semantic-to-primitive composition; timing/units; deterministic variation; selectors/provenance; compact discoverable diagnostics; validation/errors/limits; integration; real token-efficiency evaluation; phased file-level tasks and meaningful acceptance tests.

English (en-US) is primary project documentation; Brazilian Portuguese is auxiliary. The conversation and concise user-facing summary should remain Portuguese. Produce planning documentation only; implementation has not been requested in this turn.

## Starting references

- `src/tare/tools/tune/authoring.py`, `patterns.py`, `score.py`, `spec.py`
- `src/tare/tools/tune/creature.py`, `sfx/__init__.py`, `sfx/knobs.py`, `instruments.py`, `music.py`, `speech/speaker.py` (locate the actual speaker module if needed)
- `src/tare/tools/tune/diagnostics.py`, `inspection.py`, `bundles.py`, `studio.py`, `cli.py`, `midi_export.py`, `effects.py`, `exports.py`
- `tests/test_authoring.py`, `tests/test_authoring_workflows.py`, `tests/test_curate.py`, `tests/test_score.py`, `tests/test_native.py`, `tests/test_godot.py`, `tests/fixtures/authoring/`
- `examples/authoring.json`, `examples/sound-bank.json`, `examples/dsp_listening.py`
- `docs/authoring.md`, `docs/authoring-verification.md`
- the Astra audit report (not published) for established rendering/provenance/compatibility constraints, not as a prescribed DSL design.
