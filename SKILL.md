---
name: tune-game-audio
description: Makes game audio with tare.tools.tune, a deterministic procedural synthesizer (Python, no AI at runtime) - creature cries and calls, NPC speech lines (Brazilian Portuguese and English) and wordless barks (grunts, laughs, gasps), sound effects (weapons, footsteps, doors, chests, UI, spells, ambience loops), music jingles and loops - exported as WAV, OGG sprite banks, Voice JSON for Godot or MIDI. Use when asked to create, tune, compare or iterate on sounds, voices, SFX or music cues for a game. Not for editing existing recordings, music production in a DAW, or pixel art.
---

# tune: game audio as data

You describe sounds in a `.tune.json`; tune renders them deterministically and measures them; the user judges
them by ear in a local page. `TUNE` below means `<this skill's directory>/.venv/bin/python -m tare.tools.tune`;
`CURATE`, that Python running `<this skill's directory>/tools/curate.py`. On Windows the Python is
`.venv/Scripts/python`; in Git Bash prefix `MSYS_NO_PATHCONV=1` (it keeps `/with/power` from turning into a
path) and write the directory as `C:/...`, never `/c/...`. `TUNE --help` lists every command.

Work in the user's project (renders under `output/`), never in this skill's directory, where `examples/`
and `docs/` live. Copy an example before editing it: `dsl edit` rewrites its source.

## Workflow

1. **One finished sound, nothing to iterate:** a quick command, then stop.
   - `TUNE sfx blade steel --event clash --species excalibur --dry -o clash.wav`
   - `TUNE say "[happy] Hello there!" --lang en --voice npc:7 -o line.wav` (pt-BR: `--lang pt --voice natural:f`)
   - `TUNE render monster --species ogre --size 0.9 --aggression 0.8 --call attack -o ogre.wav`
   - `TUNE music victory --seed 3 -o victory.wav`

   `--take N`: another take; `--sr 48000`: the rate.
   A bark (`emote`) has no quick command: write it in a `.tune.json` and freeze it to a WAV (step 6).
2. **Anything you will iterate, compare by ear or ship as a set:** a `.tune.json` in the project, from the
   template below or the closest example. `TUNE dsl check bank.tune.json --json` validates every sound and
   its names without rendering; an unknown name comes back with the valid ones.
3. **Look with one call:** `TUNE dsl review bank.tune.json --name clash -o output/reviews --response compact --json`
   returns the bundle path (every edit needs it), its `audio.wav`, duration, peak, RMS and the
   checks that ran. `--checks checks.json` adds duration/peak/rate/export limits (`TUNE dsl help checks --json`).
   - **A recording to match:** `TUNE study FILE` says what it is made of and which fields reach it. Name it in
     the bank's `"references": {"clash": "refs/clash.wav"}`: review adds `ref` (`[recording, sound]` pairs), checks
     take tolerances (`TUNE dsl help reference --json`). `CURATE compare clash A B --reference refs/clash.wav
     --root output/rounds` plays it beside the candidates. Numbers aim; the ear decides. Never share bundles: they
     keep the recording.
   - **Hear it as text:** `TUNE ear BUNDLE` prints bands by time in 6 dB digits, peaks in Hz and pitch, held
     against its reference if it has one; `--vs A` shows what an edit changed; then `--brief` (~1k tokens). It
     shows structure, never how it sounds.
4. **Find the controls, then fix everything one look showed in one call:**
   `TUNE dsl describe BUNDLE --fields power,knobs --json` gives each field's path, range and value
   (`--find WORD` lists candidates). Then
   `TUNE dsl edit bank.tune.json --from-bundle BUNDLE -o output/reviews --set /with/power 0.65 --set /with/knobs/ring 0.6 --response compact --json`.
   - Use the path `describe` returned: `/with/NAME` on a `use`, `/NAME` on a direct recipe,
     `/params/NAME/default` on a definition (that validates every sound using it but renders only this one:
     review the others when their audio matters).
   - The result is the next observation. A stale bundle fails (exit 3): review again; never retry against a
     fresh revision.
   - Knob names and ranges come from the catalog (`--domain sfx --name KIND --fields knobs`), not `describe`.
     To vary a knob fixed inside a definition, make it a `param` first.
   - `--refine /lowpass 2400` keeps the recipe and overrides its generated layers (`--layer n0/p0` for one).
   - Adding or removing sounds, renaming a definition: edit the JSON yourself (after a `dsl edit` it is
     canonical JSON: re-read it), then review.
5. **The ear decides.** Checks never judge timbre (`perceptual_quality` is always `not_run`): report what was
   measured, never that it sounds right. When a choice needs an ear, render 2-9 candidates with `--dry-run`
   from one bundle (the source stays put), then:
   - `CURATE compare confirm A B C --open --question "Which confirm sounds firmer?" --root output/rounds`.
     Make A the current sound: `--open` notes list each candidate's changes against A. The page matches
     loudness, so candidates that differ only in level (on `ui`, `power` is mostly level) sound alike: vary
     timbre knobs, or pass `--keep-levels` when level is the question.
   - `CURATE serve --root output/rounds` in the background: it opens the user's browser at
     http://127.0.0.1:8765/ and blocks. Give the URL, stop it when done, never use a headless browser.
   - `CURATE answers confirm --json --root output/rounds`: the pick, ratings and marks by label, with each
     bundle path. Commit the pick by repeating its edit from the first bundle: the result is the PCM the user
     heard. Blind rounds (no `--open`) number their cards #1, #2 by shuffled position: take the choice from
     `answers`, never from a number said in chat. Rules: `TUNE dsl help listener --json`.
   - Nobody to listen now: deliver, say nothing was judged by ear, leave the round ready.

6. **Hand over.** A WAV ends 60 dB under its peak, but loops and reverb or echo tails (a creature's, `hall`,
   `echo`) stay whole; `--keep-tail` keeps a dry ring too:
   - One WAV per sound: `TUNE dsl freeze bank.tune.json --name clash --format wav -o clash.wav`.
   - `TUNE export bank.tune.json -o output/sprites --ogg`: a stereo WAV/OGG bank with a sample-accurate
     manifest, Howler adapter and test page, in a folder named by revision; `current.json` names the latest.
   - `TUNE dsl freeze bank.tune.json --name clash --format voice -o clash.voice.json`: for the Godot/native
     runtime; speech, barks, chip and cues ship as PCM instead. `TUNE dsl capabilities bank.tune.json --name clash --json`
     says what a sound supports.
   - `TUNE midi bank.tune.json -o theme.mid`: scores only.

## Looking things up

What you read early is paid again every later turn: ask for one name, never a whole file.
`TUNE dsl catalog --domain D --name N --fields F --json` is the vocabulary (pages: `--limit`, `--cursor`);
`TUNE dsl help TOPIC --json` the loop's rules (review, describe, edit, checks, builders, listener).
Never open `docs/dsl-reference.json` (65k tokens) or `docs/architecture.md` (33k).

| Making | Read (tokens) |
|---|---|
| weapon, door, chest, item, UI, spell, footstep, ambience | `--domain sfx --name ui --fields name,styles,events,knobs` (500); every kind: `--domain sfx --fields name,styles,events --limit 100` (1.2k) |
| a creature call | `--domain op --name creature --fields fields` (370); archetypes and calls: `TUNE list` (210) |
| an NPC line | `--domain op --name say --fields fields` (260); a voice: `--domain op --name speaker --fields fields` (500); presets: `TUNE voices` (360) |
| a bark, grunt, laugh, gasp | `--domain op --name emote --fields fields`: every emote and style (300) |
| a jingle or loop from a seed | `--domain music --fields name --limit 100` (240); `--domain op --name music --fields fields` (190) |
| a composed phrase | `examples/dsl-music.tune.json`; `--domain transform --fields name,meaning --limit 100` (170); `--domain instrument --fields name --limit 100` (300) |
| raw synthesis layers | `examples/dsl-primitives.tune.json`; `--domain layer --name modal --fields fields` (500) |
| a family with variants | `TUNE dsl help builders --json`; `TUNE dsl variants --help` |

## Template

```json
{
  "format": "tare.tools.tune.dsl", "version": 1,
  "context": {"sample_rate": 48000},
  "defs": {
    "hit": {"params": {"power": {"type": "number", "min": 0, "max": 1, "default": 0.5}},
            "body": {"sfx": "blade", "style": "steel", "event": "clash", "species": "excalibur",
                     "power": {"param": "power"}, "dry": true}}
  },
  "sounds": {
    "clash": {"use": "hit"},
    "clash_heavy": {"use": "hit", "with": {"power": 0.9}},
    "confirm": {"sfx": "ui", "style": "crystal", "event": "confirm", "era": "hd", "dry": true, "knobs": {"register": -1}},
    "wolf_attack": {"creature": "mammal", "species": "wolf", "size": 0.45, "aggression": 0.5, "call": "attack", "take": 2},
    "greet": {"say": "Bem-vindo à forja!", "lang": "pt", "speaker": {"speaker": "default", "engine": "natural", "bank": "pt/alex"}},
    "hurt": {"emote": "hurt", "style": "grunt", "speaker": {"speaker": "default", "pitch": 135}, "take": 1},
    "fanfare": {"music": "victory", "seed": 3}
  }
}
```

## Essentials

- **Reuse:** `defs` with typed `params`; `{"param": "name"}` is the only substitution; each sound `use`s a
  definition `with` its values. No arithmetic, imports or recursion.
- **Units:** primitives in seconds and Hz; scheduling as `"250ms"`, `"0.5s"`, `"1/3b"`, `"2bar"`; `context` sets
  `sample_rate`, `bpm` and `meter`.
- **Identity:** `species` (a name or a number) is this object; `take` another repetition; `individual` and `genes`
  art-direct a creature. Ids and definition names never seed the sound.
- **Limits and errors:** 180 s per sound, 1 MiB source, 256 sounds, 64 tracks. Errors are one JSON object with
  `code` and `pointer`; exit 2 bad input, 3 stale, 4 build failed, 5 checks failed.

## Examples

- `examples/dsl-bank.tune.json` (a `power` param, two `use`s), `examples/dsl-review.checks.json`,
  `examples/dsl_builder.py` (a bank written from Python).

## Habits that give better audio

- Author at the rate you ship (`"sample_rate": 48000`); the examples use 16000.
- `dry: true` when the game adds its own reverb per map; `era: "hd"` or `"16bit"` to match a generation.
- Vary within a recipe (`knobs`, `power`, `size`, `take`) before switching style or kind.
- Natural voices exist for pt-BR only, written as in the template's `greet` (`bank` `pt/alex` or `pt/dora`;
  the CLI's `--voice natural:pt/alex`); in English they fall back to formant synthesis: tell the user. Keep each
  character on one `speaker`.

## When tune gets in your way

If something cost you a rebuild or a workaround, append one line to `FEEDBACK.md` in this skill's directory:
the date, the kind of sound, what happened in tune, what would have helped. Tune's side only.
