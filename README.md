<div align="center">

# tare.tools.tune

**Game audio from code.** Creature cries, NPC voices, sound effects and music,<br>
synthesized on the spot: no recordings shipped, no AI at runtime, and the same recipe always gives the same sound.

[![License: Apache 2.0](https://img.shields.io/badge/license-Apache_2.0-blue)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
![Dependencies: numpy + scipy](https://img.shields.io/badge/deps-numpy_%2B_scipy-013243?logo=numpy&logoColor=white)
![AI at runtime: none](https://img.shields.io/badge/AI_at_runtime-none-2ea043)
[![Godot 4](https://img.shields.io/badge/Godot_4-native_extension-478CBF?logo=godotengine&logoColor=white)](docs/guide.md#2-runtime-generate-inside-the-game)
[![Agent skill](https://img.shields.io/badge/agent_skill-Claude_Code_%C2%B7_Codex-D97757)](SKILL.md)

**English** · [Português](README.pt-BR.md) · [Full guide](docs/guide.md) · [Docs](docs/README.md)

<img src="docs/media/hero.png" alt="Spectrograms of four sounds made by tare.tools.tune, each under the line of code that made it: a wolf's alert call, an NPC line, a steel sword clash and a victory jingle" width="100%">

</div>

## Why

- 🧬 **Describe who and why, not waveforms.** A big, angry wolf attacking. A deep-voiced blacksmith greeting you. A steel sword clashing. The sound follows.
- 🎲 **Deterministic, never copy-pasted.** Same input, same sound. On the same setup the samples are identical. Between Windows and Linux, 954 of 960 test WAVs matched bit for bit, and the other 6 differ in one sample by the smallest step. Each individual and each take varies a little, so repeats don't sound identical.
- 🪶 **Tiny.** Only numpy and scipy. A sound is a 1–10 KB JSON spec that your game can render on demand.
- 🗣️ **Speech in Brazilian Portuguese and English**, plus wordless barks (*hyah!*, *ugh*, *hm?*) in each character's own voice.
- 🎮 **Engine-ready.** WAV packs for any engine, OGG sprite banks for the web, MIDI, and a C++ renderer for Godot that matches Python sample for sample.
- 🤖 **Built for agents too.** It ships as the [`tune-game-audio` skill](SKILL.md), and the review loop lets an agent read a sound as text.

> It began as a Pokémon Gen 1 cry synthesizer. That game made 151 cries from 38 templates plus pitch and duration, and the idea became the model for everything here: **species = genes, individual = small variations, take = a new performance**.

## Quick start

```bash
pip install git+https://github.com/augusto-scarvalho/tare.tools.tune
```

```python
from tare.tools.tune import Creature, Sfx, write_wav
from tare.tools.tune.music import Cue
from tare.tools.tune.speech import Speaker

wolf = Creature("mammal", species="wolf", size=0.45, aggression=0.5)
write_wav("wolf_attack.wav", wolf.render("attack"), 48000)
dire_wolf = wolf.evolve(size=0.9)                    # same species, bigger
write_wav("dire_wolf_death.wav", dire_wolf.render("death", take=2), 48000)

smith = Speaker.preset("deep")
hello = smith.render("Welcome to the forge, traveler!", lang="en")
write_wav("smith.wav", hello, 48000)
write_wav("smith_laugh.wav", smith.emote("laugh"), 48000)   # a bark, same voice

sword = Sfx("blade", "steel", species="excalibur")
write_wav("clash.wav", sword.render("clash", take=3), 48000)
write_wav("victory.wav", Cue("victory", seed=3).render(), 48000)
```

Or from the command line:

```bash
tare.tools.tune sfx spell lightning --event impact -o lightning.wav
tare.tools.tune sfx ambience rain --event loop -o rain.wav   # 16 s, seamless
tare.tools.tune say "Hello there!" --lang en --voice npc:7 -o hello.wav
# a whole bestiary: 19 creatures × 5 calls × 3 takes, as WAV packs
tare.tools.tune bake examples/bestiary.json -o baked
```

## What it makes

| | Range | Highlights |
|---|---|---|
| 🐺 **[Creatures](docs/guide.md#archetypes)** | 10 archetypes × 5 calls | mammals, birds, insects, monsters, slimes, spirits, robots and more. A creature can `evolve()` and keep its species |
| 🗣️ **[Speech](docs/guide.md#human-speech)** | Portuguese and English | a formant voice or a natural voice bank; intonation from punctuation; emotions; a unique voice per NPC; gibberish and animalese |
| 😤 **[Barks](docs/guide.md#vocalizations-games-without-full-voice-acting)** | 20 vocalizations, 6 styles | attacks, pain, laughs, sighs and gasps in the character's voice, styled after action, anime, tactics and MMO games |
| ⚔️ **[Sound effects](docs/guide.md#sound-effects)** | 34 kinds | weapons, doors, chests, UI, status effects, spells, summons, footsteps, horses and seamless ambience loops; `era="16bit"`, knobs |
| 🎼 **[Music](docs/guide.md#music-and-composition)** | 43 instruments, 32 cues | jingles and loops in orchestral, 16-bit and 8-bit styles; a `Score` to lay out whole scenes |
| 👾 **[Gen 1 cries](docs/guide.md#generation-1-reproduction)** | a Game Boy cry engine | the `chip` archetype, plus a faithful reproduction of all 151 cries (bring your own data) |

## How it works

```mermaid
flowchart LR
    R["<b>Recipe</b><br/>who + why<br/>Python · JSON · DSL"] --> T["<b>tare.tools.tune</b><br/>deterministic synthesis"]
    T --> F["<b>Files</b><br/>WAV packs · OGG sprites · MIDI"]
    T --> S["<b>Spec</b><br/>1–10 KB JSON"]
    S --> G["<b>In the game</b><br/>Godot / C++ core<br/>same samples as Python"]
```

Struck bodies ring through modal synthesis, wind and fire are filtered noise, and crackles are clouds of tiny events. Voices are rebuilt by a small vocoder. Recordings and the offline teacher voice were only ever **measured**, and just the numbers ship: speech, barks and instruments alike. The [architecture](docs/architecture.md) explains each technique and the measurements behind it.

## Use it your way

- **Offline:** `bake` a bestiary into WAV packs with a manifest, then import them into Unity, Godot, Unreal, FMOD or Wwise. [How →](docs/guide.md#1-offline-generate-assets-for-any-engine)
- **Python games:** `VoiceBank` renders in threads, caches, and never plays the same take twice in a row. `AmbiencePlayer` keeps a place alive. [How →](docs/guide.md#2-runtime-generate-inside-the-game)
- **Godot:** the `tare_tune` extension turns small specs into sound inside the game. [How →](docs/guide.md#2-runtime-generate-inside-the-game)
- **With an AI agent:** link the repo as the `tune-game-audio` skill for Claude Code or Codex. [SKILL.md →](SKILL.md)

## Learn more

| Read | What's inside |
|---|---|
| 📖 [Full guide](docs/guide.md) | every archetype, voice, effect and cue, the knobs, engines, CLI and development |
| 🎛️ [Authoring](docs/authoring.md) | live studio, capture, inspection, MIDI and web sprites |
| 🔁 [Review loop](docs/dsl-review.md) | measured changes, checks and atomic edits, and the sound as text |
| 🧩 [Semantic DSL](docs/dsl.md) | reusable recipes, variants and guarded refinements (experimental) |
| 🏗️ [Architecture](docs/architecture.md) | how each sound is built, portability, and what listening tests found |
| 🗡️ [RPG sounds](docs/rpg-sounds.md) · [Tactical RPG sounds](docs/tactics-sounds.md) | coverage and status, sound by sound |
| 🗂️ [Documentation index](docs/README.md) | everything else, in English and Portuguese |

## Credits and license

The project stands on the Gen 1 cry synthesizer by [dotsarecool](http://dotsarecool.com/rgme/tech/gen1cries.html) and [ardean](https://github.com/ardean/pokemon-gen1-cry-synthesizer). It also builds on the [CMU Pronouncing Dictionary](https://github.com/cmusphinx/cmudict), [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) as an offline teacher, the emotion measurements of [emoUERJ](https://doi.org/10.5281/zenodo.5427549), the [VSCO-2 CE](https://github.com/sgossner/VSCO-2-CE) orchestra, CC0 performers from OpenGameArt and Freesound, and the [WORLD](https://github.com/mmorise/World) vocoder design. Every source and its license is listed in the [full credits](docs/guide.md#credits).

[Apache License 2.0](LICENSE) © 2026 Augusto da Silva Carvalho.
