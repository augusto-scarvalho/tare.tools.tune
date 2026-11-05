# What tare.tools.tune runs, fetches and sends

**It sends nothing.** There is no telemetry and no account, and nothing is uploaded. Rendering is plain Python on
your CPU and needs no network.

## What it runs

- The package itself, with numpy and scipy, on your machine.
- The listening and studio pages (`tools/curate.py serve`, `tare.tools.tune studio`). They are served on `127.0.0.1` only, so no
  other machine can open them. They save your answers next to the round, on your disk.
- Optionally, the native core and the Godot extension that you build yourself (`tools/build_native.py`).

## What it fetches, and only when you ask

| When | From |
|---|---|
| `pip install` | the package from GitHub, and numpy and scipy from PyPI (or your configured index) |
| the optional `clap` extra (`design`, `match`, `judge`) | the LAION CLAP models from Hugging Face, on first use |
| the optional `teacher` and `asr` extras (calibration tools only) | the Kokoro voice and Whisper models, from Hugging Face |
| `tools/build_barks.py --download` (contributors' full test suite) | CC0 recordings from OpenGameArt and Freesound |
| `tools/build_native.py godot` | godot-cpp, from GitHub |

## Your recordings

A recording you give it as a reference (`study`, `references` in a bank, a listening round) stays where you put it.
Its numbers go into your bank. **A review bundle keeps a copy of the reference recording**, so don't share bundles. Share the
`.tune.json` and the command instead.

Your agent, if you use the `tune-game-audio` skill, sends what it reads to its own model, like any other file it opens.
