# tare.tools.tune: user guide

Everything in one page: every archetype, voice, effect and cue, the knobs, the engines and the tools. [Project README](../README.md) · [Documentation index](README.md) · [Português brasileiro (alternative)](pt-BR/guia.md)

Procedural game audio: **creatures**, **human speech** (Portuguese and English), and **sound effects** (weapons, footsteps, explosions, magic, and environments). For creatures, describe **who** is calling (species, size, aggression) and **why** (idle, alert, attack, hurt, death). For people, choose a voice and write the text. For effects, choose the object (a steel sword, a fireball, a storm) and the event (swing, clash, impact, loop). The same input always produces the same sound, with small variations for each individual and repetition.

The project began as `creaturesynth`, based on ardean's [Pokémon Generation 1 cry synthesizer](https://github.com/ardean/pokemon-gen1-cry-synthesizer). The game's approach, producing 151 cries from 38 templates plus pitch and duration, became the general model here: **species = stable genes; individual = small variations; traits = evolution**. The original engine remains available as the `chip` archetype and as a faithful reproduction of all 151 cries.

```python
from tare.tools.tune import Creature, write_wav

wolf = Creature("mammal", species="wolf", size=0.45, aggression=0.5)
write_wav("wolf_attack.wav", wolf.render("attack"), 48000)

dire_wolf = wolf.evolve(size=0.45, aggression=0.35)   # same species, larger and fiercer
write_wav("dire_wolf_death.wav", dire_wolf.render("death", take=2), 48000)

from tare.tools.tune.speech import Speaker

blacksmith = Speaker.preset("deep")
write_wav("blacksmith.wav", blacksmith.render("Welcome to the forge, traveler!", lang="en"), 48000)
npc = Speaker.random(42)                            # a unique, repeatable voice per NPC
write_wav("npc.wav", npc.render("Did you see the dragon?", lang="en"), 48000)

from tare.tools.tune import Sfx

excalibur = Sfx("blade", "steel", species="excalibur")
write_wav("clash.wav", excalibur.render("clash", take=3), 48000)   # each take is a different clash
write_wav("fireball.wav", Sfx("spell", "fire", power=0.8).render("impact"), 48000)
```

## Installation

```bash
git clone https://github.com/augusto-scarvalho/tare.tools.tune
cd tare.tools.tune
pip install -e .            # numpy + scipy
pip install -e ".[dev]" -c constraints.txt   # + pytest, ruff, matplotlib (spectrograms)
```

Requires Python 3.10 or newer. Floating point can change between numpy and scipy versions, so a team, a build server or the tests should add `-c constraints.txt`: it pins the versions every render was verified with (Python 3.12 or newer). With those versions, two different Intel CPUs on Windows gave bit-identical WAVs for all 960 test sounds. The operating system still matters a little: Windows and Linux matched on 954, and the other 6 differ in one sample by the smallest step. On every push, CI holds 30 of them against the Windows references on Windows, Linux (x86 and ARM) and macOS (ARM): only macOS has differed, by the smallest step in 76 samples of one speech line. In code, use `import tare.tools.tune` (`tare` and `tare.tools` are namespace packages); on the command line, use `tare.tools.tune`; where dots are not allowed, use `tare-tools-tune` (the name pip normalizes the package to).

As an agent skill (`tune-game-audio`, [SKILL.md](../SKILL.md)), the clone is the skill folder once it has its own `.venv` (`python -m venv .venv`, then `.venv/bin/pip install -e . -c constraints.txt`, or `.venv\Scripts\pip` on Windows): link it as `~/.claude/skills/tune-game-audio` (Claude Code) or `~/.codex/skills/tune-game-audio` (Codex; a junction on Windows). Antigravity's `agy` does not follow a link there: name the folder holding the clone in `~/.gemini/config/skills.json` instead, `{"entries": [{"path": "<the folder holding your clone>", "include_only": ["<your clone's folder name>"]}]}`.

## Authoring and diagnostics

AI agents: the [tune-game-audio skill](../SKILL.md) is the entry point (install by linking this folder into the agent's skills directory).

The [audio review loop](dsl-review.md) combines a playable capture, measured
changes and declared checks with selected-target controls and trial-checked
atomic edits: `tare.tools.tune dsl help review --json`. Use the returned bundle
as the observation for subsequent `describe`/`edit` operations.

The experimental [semantic DSL](dsl.md) adds reusable recipes, parameterized variants, Notes transformations, primitive synthesis, guarded refinements and compact agent queries. JSON and immutable Python builders compile to the existing engine. The [agent workflow](dsl-agent.md) covers narrow edits and opt-in `--response compact`; [version-2 measurements](dsl-efficiency.md) distinguish memory/persisted services and cold/warm costs. See the [acceptance map](dsl-acceptance.md). Start with `tare.tools.tune studio examples/dsl-bank.tune.json --name confirm -o output/player`; [Portuguese auxiliary guide](pt-BR/dsl.md).

Run `tare.tools.tune studio examples/authoring.json -o authoring-out` and open the printed local URL. Edit the JSON file to rebuild in a clean background worker. The player keeps completed revisions, references, range notes, and the exact audio evaluated; it supports previous-version playback and diagnostic layer solo/mute with captured processing gains. A failed build keeps the last successful audio available.

```bash
tare.tools.tune capture examples/authoring.json -o authoring-out/bundles
tare.tools.tune inspect examples/authoring.json --json --start 0.1 --end 0.3 --band 1000 4000
tare.tools.tune ear output/reviews/<bundle> --brief   # the sound as text an agent reads (docs/dsl-review.md#hear-it-as-text)
tare.tools.tune study refs/clash.wav                  # what a recording is made of and which fields reach it
tare.tools.tune midi examples/authoring.json -o authoring-out/composition.mid
pip install -e ".[export]"    # optional Vorbis and additional input formats
tare.tools.tune export examples/sound-bank.json -o authoring-out/web --ogg
```

The [authoring guide](authoring.md) covers the Python capture API, inspector schema, editable patterns, immutable bundles, blind listening rounds, MIDI limitations, web sprites, and optional FM/chorus/limiting. Existing rendering remains the default; the optional DSP does not extend the native Voice format.

## Archetypes

| Archetype | What it produces |
|---|---|
| `mammal` | squeak → bark → howl → roar, depending on size and aggression |
| `bird` | whistled phrases of swept syllables; aggressive birds squawk |
| `insect` | cricket, fly/bee buzz, or cicada |
| `reptile` | hiss, rattle; large, aggressive reptiles also growl underneath |
| `amphibian` | pulsed croak ("rib-bit") |
| `monster` | fantasy beast: raw roar, piercing screech, or gurgle |
| `slime` | popping bubbles over a wet gurgle |
| `spirit` | ghostly wail with whistling and long reverb |
| `robot` | stepped tones, metallic resonances, ring modulation, bitcrushing |
| `chip` | original Game Boy style 8-bit cries (2 pulse channels + noise) |

**Calls:** `idle`, `alert`, `attack`, `hurt`, `death`. Every archetype responds to them: alert repeats and rises, attack is louder and rougher, hurt is short and high, death is long and falls in pitch, and idle is quieter.

**Creature controls:**

- `species`: a number or any name (hashed). Sets the species' genes.
- `size`: from 0 (tiny) to 1 (huge). Affects pitch, formants, duration, and reverb.
- `aggression`: from 0 (calm) to 1 (furious). Affects roughness, subharmonics, and saturation.
- `individual` and `variation`: how much members of the species differ.
- `take` and `take_variation`: how much repetitions of the same call differ.
- `genes={"name": 0..1}`: fixes genes for art direction. For example, `{"kind": 0.1}` forces the "brute" monster.

## Human speech

Text in **Brazilian Portuguese** or **English** becomes speech. Both engines share the same front end:

1. **Text → phonemes.** Portuguese uses rules: digraphs, nasals, "t/d" before "i", "r"/"s"/"x" (with word lists for the "x" in "próximo" and "táxi"), stress, and numbers written out as words. English uses CMUdict (~126,000 words), with fallback rules for words absent from the dictionary, such as invented names.
2. **Intonation.** Statements fall at the end, yes/no questions rise, "where/what" questions fall, exclamations have higher peaks, and commas leave the phrase hanging.
3. **Sound**, through one of two engines (`Speaker(engine=...)`):
   - `"formant"` (default): each phoneme has a duration and formant targets, coarticulation smooths transitions, and a Klatt style cascade/parallel synthesizer produces the audio. It sounds robotic and retro, but is tiny and stretches to any voice, from fairy to giant.
   - `"natural"`: the phrase is assembled from pieces of a **voice bank**, a teacher's reading of 1,000 sentences (~45 minutes), stored only as numbers (pitch, spectral envelope, and breath every 5 ms; ~21 MB per voice). For each phoneme pair, it selects the best bank segment (Viterbi unit selection, preferring joins in consonants), stretches the pieces to the rhythm, and gives them the intonation the teacher would use (regression models learned from the teacher). Our vocoder reconstructs the sound at the character's pitch and vocal tract size.

**No AI at runtime.** Both engines are deterministic and procedural: tables, dynamic programming, and arithmetic. The bank teacher is [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0), used once, offline, by `tools/build_speech.py`; the package depends on neither Kokoro nor PyTorch. Both engines produce a portable spec (`SpeechProgram` or `Spoken`).

The natural engine currently has Portuguese voice banks, so this example deliberately uses Portuguese dialogue:

```python
from tare.tools.tune.speech import Speaker

guard = Speaker.preset("deep")                              # formant synthesis
king = Speaker(pitch=105, tract=0.97, engine="natural")      # voice bank, shifted to this voice
audio = king.render("Bem-vindo ao meu reino, viajante.", lang="pt")
npc = Speaker.random(42).but(engine="natural")              # a unique natural voice per NPC
```

**Voice presets (formant):** `default`, `deep`, `high`, `child`, `cute`, `fairy`, `elder`, `giant`, `monster`, `robot`, and `whisper`. Use `Speaker.random(seed)` to give each NPC a unique human voice, and `Speaker.from_creature(creature)` to make a creature speak with a voice that matches its body. You can adjust `pitch`, `tract` (vocal tract size), `rate`, `range` (intonation), `breath`, `rough`, and more.

**Natural voices:** `natural`, `natural:m`, `natural:f`, or a bank (`natural:pt/alex`, `natural:pt/dora`), in the CLI, bestiary, and `speaker_from`. Any `pitch` and `tract` work: the bank closest in tract size is selected and the vocoder handles the rest (formants from 0.75× to 1.35×). It sounds most natural near the banks' pitches (130 Hz male, 173 Hz female): shifting too far up makes the sound thin. `breath`, `whisper`, `tilt`, `rate`, `range`, `jitter`, `rough` (hoarseness), `sub` (a doubled creature voice), `drive`, `crush`, and `space` also apply. Only Portuguese banks are available for now; in English, the natural engine falls back to formant synthesis.

**Intelligibility** measured with Whisper (`tools/intelligibility.py`, plus 16 new sentences, none from the teacher's corpus):

| | Portuguese (CER) |
|---|---|
| formant | 0.23 |
| natural, male / female / randomly generated NPC voices | 0.045 / 0.042 / 0.033–0.037 |
| teacher (Kokoro) | 0.003 |

In English, formant synthesis scores between 0.04 and 0.06 depending on the voice.

### Intonation and emotions

Phrase endings follow punctuation, using Brazilian Portuguese intonation patterns. The Portuguese words below illustrate stress and pronunciation:

- `.` statement: falls at the end;
- `?` yes/no question: rises on the last stressed syllable and falls afterward ("Você comprou a es**pa**da?"); if stress is on the final syllable, it ends high ("Você viu o dra**gão**?");
- questions with "quem", "onde", "o que", "por que" (who, where, what, why), etc.: fall like statements, with a higher question word;
- `?!` surprise ("Sério?!", "O quê?!", meaning "Really?!", "What?!"): the question contour, higher and longer;
- `!` exclamation: wider pitch movements;
- `...` or `…` ellipsis: hanging, slow, with a longer pause;
- `,` continuation.

**Emotions** change the whole voice or a section of speech, in either engine:

```python
king.render("Get out of here!", lang="en", emotion="angry")
king.render("[happy] Good to see you! [sad] But I have to leave...", lang="en")
king.render("[fear:0.5] Did you hear that?", lang="en")   # intensity 0–1 (default 0.8)
```

Supported names include `alegria`, `raiva`, `tristeza`, `medo`, `surpresa`, `sussurro`, and `neutro` (also `feliz`, `triste`, `bravo`, `assustado`, `happy`, `angry`, `sad`, etc.). These are API identifiers; English aliases are available. Happiness, anger, and sadness were measured in Brazilian actors from [emoUERJ](https://doi.org/10.5281/zenodo.5427549) (CC BY 4.0): happiness raises pitch by 6.3 semitones and widens the melody by 27%; anger raises pitch by 4.6, brightens the timbre, and falls further at the end; sadness is 8% slower and breathier, with a smaller final fall and more pauses.

### Vocalizations (games without full voice acting)

Many games are not fully voiced: the character just makes a "hyah!", "ugh", "hm?", or laugh, and text does the rest. `Speaker.emote` produces these wordless vocalizations **in the character's own voice**.

They start from real performances: CC0 actor recordings (183 clips, 145 s), measured once as numbers (pitch, spectral envelope, and air every 5 ms; 951 kB). Only the numbers ship, never the recordings: our numpy vocoder rebuilds each sound from them at the character's pitch, tract size, brightness, and breathiness. No model or AI runs, and the result is deterministic: the same character, type, style, and take always produce the same samples. Each character keeps one performer. (Optional: `python tools/build_barks.py --download output/barks --audio` downloads the recordings from their sites, with no account, and stores them locally; with `TARE_TOOLS_TUNE_TAPE=1` a shout that needs little adjustment, up to 40% in formants, about 5 semitones, and 25% in duration, then plays its recording like tape. It is off by default because the native core and Godot always use the vocoder, so the same recipe sounds and lasts the same everywhere. In listening tests tape sounded like the recording, roboticness 2.5 out of 5, and the vocoder did not, 3.4.)

```python
from tare.tools.tune.speech import Speaker

hero = Speaker(pitch=135, tract=1.06, breath=0.12)
write_wav("attack.wav", hero.emote("attack", style="grunt", take=2), 48000)   # each take differs slightly

girl = Speaker.random(42)
write_wav("laugh.wav", girl.emote("laugh", style="anime", intensity=0.9), 48000)
```

- **Combat:** `attack`, `attack_big`, `hurt`, `hurt_big`, `death`, `jump`, `tired`.
- **Expressions:**
  - laughter: `laugh`, `giggle`, `chuckle`;
  - breathing: `sigh`, `gasp`, `relief`;
  - reactions: `surprise`, `hmm`, `huh`;
  - responses: `yes`, `no`;
  - mood: `cheer`, `angry`.
- **Styles**, inspired by games that use these sounds (the sounds do not come from those games):

  | Style | Character | Inspired by |
  |---|---|---|
  | `grunt` | wordless, breathy, short | the hero of *Zelda* |
  | `anime` | bright, more voice and less air, livelier contour | *Rune Factory* |
  | `tactics` | restrained: shorter, lower, darker | *Fire Emblem* |
  | `mmo` | full, longer, stronger shouts | *Final Fantasy XIV* |
  | `gasp` | more air than voice, near speaking pitch, longer (measured in the game itself) | *Tactics Ogre* |
  | `kiai` | a full shout, the performer's longest takes without stretching; darker and breathier pain (measured in the game itself) | *Utawarerumono* |
- `intensity` (0–1) controls how much effort goes into the sound.
- The spec stores the template and transformations (`Vocoded`, v5); a port must include the templates.

The performances come from OpenGameArt CC0 packs (adventurer, female RPG voices, shouts) and Freesound laughs, sighs, gasps, and "hm" clips. Template selection minimizes the adjustment needed to match the character, especially in formants: a heroine uses female performers; a hero uses male performers. Effort sounds change voice through the shout register measured in those recordings: attack shouts rise far above speech, by 17–23 semitones in men (95 Hz → ~345 Hz) and about 10 in women. Details are in [Architecture](architecture.md).

### Choosing an engine for each speaker

Each engine has its strengths, and `speech.casting.cast` chooses based on the character's role:

| Role (`role`) | Purpose | Voice |
|---|---|---|
| `main` | important NPC dialogue | natural, unique voice per name |
| `minor` | other NPCs | formant, unique voice per name |
| `crowd` | background chatter | formant, invented language |
| `creature` | talking creatures | the creature's voice, babbling |
| `robot` | machines, golems | robotic formant voice, real words |

The natural voice sounds human and requires a bank of several MB per language. The formant voice is tiny, stretches to any creature, and works best for **babbling** (`style`; these styles also work with the natural engine). All three babbling styles preserve the text's rhythm, stress, and punctuation, so questions still rise:

- `gibberish`: an invented language using the language's sounds, like The Sims;
- `animalese`: one fast, high note per syllable, like Animal Crossing;
- `mumble`: everything becomes "mm".

```python
from tare.tools.tune.speech.casting import cast

king = cast("main", "king", gender="m")                  # natural voice
crowd = cast("crowd", "crowd")                           # babbling
rat = cast("creature", creature=Creature("mammal", size=0.1))   # small: animalese
audio = king.render("Salve o reino!")                    # Portuguese: "Save the kingdom!"
```

## Sound effects

`Sfx` works like `Creature`: a **kind** (recipe), a **style** (material, element, or place), an **identity** (`species`: this sword, rather than swords in general), **size** and **power**, and **events** that play like calls. Each take varies: the strike lands on a different part of the blade, the fire crackles differently.

| Kind | Styles | Events |
|---|---|---|
| `blade` (swords, daggers, axes) | steel, iron, glass, wood | swing, clash, hit_flesh, hit_wood, hit_metal, hit_stone, draw, drop, quickdraw (the katana's draw-and-cut) |
| `spear` (spears and halberds) | spear, halberd | thrust, swing, hit_flesh, hit_metal, jump and land (the dragoon's jump) |
| `fist` (unarmed) | bare, gauntlet | swing, kick, hit_flesh, hit_heavy, hit_armor, block |
| `gun` (firearms) | pistol, musket, cannon | shot, click, reload, impact |
| `thrown` (thrown weapons) | knife, shuriken, bomb | throw, fly, hit_wood, hit_flesh, fuse, blast |
| `blunt` (clubs, maces, hammers) | wood, iron, stone | swing, hit_flesh, hit_wood, hit_metal, hit_stone, drop |
| `bow` | longbow, crossbow | draw, release, fly, hit_wood, hit_flesh, hit_stone |
| `shield` | wood, metal | block_blade, block_blunt, block_arrow, bash |
| `gear` (armor and clothing) | chainmail, plate, leather, cloth | move, run, equip |
| `body` (falling body) | stone, wood, dirt | fall, drop |
| `door` (doors and gates) | wood, iron | open, close, locked, unlock, knock, slam, break |
| `chest` | wood, iron | open, close, locked, unlock |
| `item` | coins, potion, scroll, gem, letter | pickup, use, drop |
| `book` (books and scrolls) | tome, notebook, scroll | open, close, page, flip, place, write |
| `tableware` (glasses, mugs, plates, cutlery) | glass, ceramic, pewter, wood | clink, set, pour, drink, cutlery, stir, break |
| `furniture` | wood, oak | chair, sit, desk, drawer_open, drawer_close, bed |
| `bell` | church, hand, shop, ship | ring, toll |
| `breakable` | crate, barrel, pot, glass | hit, break |
| `ui` (interface) | fantasy, crystal, wood, retro | click, open, close, levelup, quest, error; for tactics: cursor, hover, target, select, confirm, cancel, scroll, range, text, advance, turn, enemy_turn, learn, battle; hit outcomes: critical, miss, damage, heal, mp, ko, revive |
| `status` (status effects) | fantasy, retro | buff, debuff, protect, shell, haste, slow, stop, sleep, poison, silence, blind, confuse, charm, berserk, doom, stone, toad, zombie, paralysis, regen, expire, cure |
| `lever` | iron, wood | pull, push |
| `trap` | darts, spikes, blade | trigger, fire |
| `torch` (fire) | torch, brazier | ignite, extinguish |
| `water` | small, big | splash, dive, drip |
| `footstep` | stone, wood, metal, gravel, dirt, grass, snow, water | walk, run, land, scuff |
| `hoof` (horse hooves) | dirt, grass, stone, wood, water, snow | step (one pair), walk, trot, canter and gallop (seamless loops), halt, land |
| `horse` | steed, warhorse | neigh, snort, nicker, hurt, charge (cavalry charge), trample |
| `wings` | feather, leather | flap, hover (loop), takeoff, land, swoop |
| `march` (marching troops) | infantry, heavy | loop, move, halt |
| `warp` (teleportation) | arcane, retro | out (disappear), in (appear) |
| `explosion` | fire, stone, magic | blast, distant, debris |
| `spell` | fire, ice, lightning, arcane, holy, shadow, nature, heal, water, wind, earth, poison, gravity, meteor | charge, cast, travel (loop), impact |
| `summon` | fire, ice, thunder, earth, holy, dark, dragon | arrive, strike, leave |
| `ambience` | rain, wind, fire, stream, cave, forest, night, storm, sea, dungeon; story locations: battlefield, camp, castle, town, tavern, dinner, plains, desert, snow, swamp, ruins, deck | loop (16 s, seamless), accent |

**Era (`era`).** Any effect can take on the sound of a game generation, measured in the games themselves:

| `era` | Sound | Measured in |
|---|---|---|
| `""` | as originally designed | — |
| `"hd"` | full bandwidth, a room, and a tail: sounds keep ringing (UI lasts 0.8–1 s) | *Triangle Strategy*, *Octopath Traveler* |
| `"16bit"` | nothing above ~5–8 kHz, the grain of 4-bit ADPCM samples, dry (UI lasts 0.2–0.4 s) | *Tactics Ogre* (PSP), *FFTA2* (DS) |

```python
Sfx("ui", "crystal", era="hd").render("confirm")
Sfx("blade", "steel", era="16bit").render("clash")   # tare.tools.tune sfx blade steel --era 16bit
```

The 8-bit retro timbre remains the `retro` style of `ui` and `status`.

**Dry (`dry`).** `"hd"` and several recipes (spells, summons, cave, castle) bake a room and a tail into the sound: the echo stays the same everywhere, multiple tails add up, and engine reverb doubles it. In a game with different maps, request dry sound and let the engine provide each map's space (in Godot, an `AudioEffectReverb` on the map's audio bus):

```python
Sfx("ui", "crystal", era="hd", dry=True).render("confirm")   # HD timbre without room or tail
```

In the bestiary, set `"dry": true` on the sound entry; in the CLI, use `--dry`. `"16bit"` is already dry.

**Knobs (`knobs`).** Within a recipe's character, any sound can be varied through controls with names, ranges, and descriptions that a person or agent can list (`tare.tools.tune sounds --knobs`, `Sfx.knob_info()`) and combine. At the defaults, the sound is exactly as designed.

| Knob | Range | Effect |
|---|---|---|
| `register` | −2 to 2 octaves | raises or lowers everything: notes, ringing, noise bands, brightness |
| `tempo` | 0.25 to 4× | spacing between parts (arpeggio notes, roll hits); each part keeps its duration |
| `length` | 0.25 to 4× | stretches or compresses the entire sound in time without changing pitch |
| `ring` | 0.1 to 4× | how long struck notes, bars, and bells ring; beep duration |
| `brightness` | −1 to 1 | darker (−1: cuts highs above ~2 kHz) to brighter (+1: harder hits, stronger upper partials) |
| `sparkle` | 0 to 3× | sparkles on top; 0 removes them |
| `key` | MIDI note 48 to 96 | `ui` and `status` only: the game's key (72 = C5); derived from species by default |

```python
Sfx("ui", "crystal", era="hd", knobs={"register": -1, "tempo": 1.5}).render("confirm")   # lower and slower
Sfx("status", "fantasy", knobs={"sparkle": 0}).render("shell")   # magic shield without sparkles
```

In the CLI: `tare.tools.tune sfx ui crystal --event confirm --knob register=-1 --knob tempo=1.5`. In a `bake` bestiary: `"knobs": {"register": -1}`.

General knobs also work **inside the game**, on a finished spec, with the same arithmetic as Python: in Godot, `sound.render(spec, 48000, {"register": -1, "tempo": 1.5})`. `key` is chosen during design; in the game, transpose with `register` (one semitone = 1/12).

Each family uses the technique suited to its sound:

- **Struck bodies** (metal, wood, stone, glass, bells, bowstrings) use **modal synthesis**: an impact or scrape excites a set of modes. Material defines modes, size defines pitch and decay, and power defines contact hardness.
- **Air and mass** (swings, roaring fire, wind, booms) use **noise with a moving filter**.
- **Textures** (drops, crackles, sparks, gravel, shards) use **clouds of tiny events**.
- **Magic** combines these with voice building blocks: vowel choir, electrical hum, bells.
- **Forest and night ambience** use birds and crickets from the creature archetypes.

```bash
tare.tools.tune sounds                                         # kinds, styles, and events
tare.tools.tune sfx blade steel --event clash --species excalibur -o clash.wav
tare.tools.tune sfx spell lightning --event impact --power 0.9 -o lightning.wav
tare.tools.tune sfx ambience rain --event loop -o rain_loop.wav
```

In the bestiary, effects go in a `sounds` section (`bake` generates takes; loops get one take and `"loop": true` in the manifest):

```json
"sounds": {
  "excalibur": {"kind": "blade", "style": "steel", "species": "excalibur", "power": 0.7},
  "fireball":  {"kind": "spell", "style": "fire", "power": 0.8},
  "storm":     {"kind": "ambience", "style": "storm", "events": ["loop", "accent"]}
}
```

In the game, `VoiceBank` accepts effects just like creatures (`bank.get(sword, "clash")` never repeats the same take twice in a row). `AmbiencePlayer` plays a place indefinitely: the loop plus occasional events (thunder, birds, drops) at random times, and any other sound you add:

```python
from tare.tools.tune.runtime import AmbiencePlayer

forest = AmbiencePlayer(Sfx("ambience", "forest"), accents_per_minute=6)
forest.add(Creature("bird", species=4), "alert", per_minute=2)
block = forest.read(1024)        # float32 for the engine's audio stream
```

The pygame demo includes a sword (Q/W), fireball (E), lightning (R), and storm (A).

**The bow** (draw, release, flight, and arrow hitting wood) was modeled from reference recordings. First, the mechanism was measured: friction slips in wood, the string scraping along the arrow before the impact, feathers vibrating in the air, and the shaft buzzing in the target. Variants were then selected by ear, listening to the entire shot. This is the method we will follow for other weapons.

Each event represents a listening position:

- `release` is what the archer hears, including the departing arrow;
- `fly` is the arrow passing close to the listener, with Doppler shift;
- `hit_wood`, `hit_flesh`, and `hit_stone` are the arrow embedding in a target, entering a body, or ricocheting off stone.

**The sword** (swing, blade clash, and hits on wood, stone, armor, and flesh, in steel and iron) followed the same method. Size and power choose among the three approved variants:

| | Size 0.5 | Size 1 |
|---|---|---|
| **Power 0.5** | as measured in recordings | heavy: lower, more thump, slow swing with a "whoom", bone in flesh hits |
| **Power 1** | cinematic: more scrape and ring, whistling swing, sharp cut | both |

**Other RPG sounds** follow the same method, one by one. Their list and status are in [RPG sounds](rpg-sounds.md). Missing sounds for tactical RPGs (in the spirit of Final Fantasy Tactics, Tactics Ogre, Unicorn Overlord, and Triangle Strategy) are covered in [Tactical RPG sounds](tactics-sounds.md).

**How they sounded according to CLAP** (the first version, designed without recordings). We measured with the judge model, excluded from all tuning, against 80 English descriptions (effects, places, and distractors such as speech, music, and "8-bit sound"). Chance would be ~1% for first place.

| Family | Correct description ranked first | Top 3 |
|---|---|---|
| magic (8 elements × 4 events) | 50% | 80% |
| weapons, bow, and explosions | 29% | 45% |
| ambience (loop + event) | ~30% | ~40% |
| footsteps | 0% | 0% |

- **Strong:** flesh and wood hits, swings, arrows flying and hitting, distant explosions, most spells, and rain, cave, night, storm, and sea loops (all ranked first).
- **Weak:**
  - sword clashes: the judge hears "sword hitting armor", close but different;
  - drawing and dropping a sword, mace hitting metal or stone, bow release;
  - almost all occasional ambience events;
  - **footsteps**. Real footstep recordings are recognized (6 of 8 ranked first); ours are not, even after a CLAP guided search.

The path to improvement is the same one used here: compare with real recordings and adjust the structure, checking with the judge throughout. Details are in [Architecture](architecture.md).

## Music and composition

Three pieces, layered together:

- **`Score`** (`tare.tools.tune.score`): a timeline in measures and seconds. Layers notes and finished sounds (effects, creatures, speech), with volume, stereo position, and a shared room echo. Renders in stereo, and `render(loop=...)` returns a seamless loop.
- **Instruments** (`tare.tools.tune.instruments`): 43 instruments measured from recorded notes, with their measurements in code:
  - plucked strings: harp, guitar, lute, pizzicato;
  - percussion keyboards: glockenspiel, marimba, xylophone, celesta, music box;
  - tubular bells;
  - drums: timpani, hand drums, log drums, bass drum, snare;
  - metal percussion: triangle, cymbal, gong, tambourine, shaker;
  - sustained: violins, cellos, flute, horn, trumpet, choir;
  - band: electric bass, electric piano, closed and open hi-hat;
  - Japanese: koto (with *yuri*, string vibrato, and *oshide*, pressing the string up to a note), shakuhachi, taiko, hyoshigi, rin;
  - chiptune: console pulse waves, bass, and noise.
- **`Cue`** (`tare.tools.tune.music`): music composed from a seed.
  - Jingles: `victory`, `levelup`, `quest`, `gameover`.
  - Loops: `town`, `explore`, `tavern`, `dungeon`, `battle`.
  - Color harmony loops in the style of 16-bit RPG soundtracks (such as Yasunori Mitsuda's): `reverie`, `pastoral`, `timeless`, `grove`, `heroic`, `showdown`. Chords chosen for color rather than function: parallel seventh and ninth chords, shifts by semitone and third, tonic pedals, Dorian, Lydian, and Mixolydian modes, never V → I. The melody rests on ninths and thirteenths and repeats the motif in sequence.
  - Tactical RPG music in the martial, modal style of Hitoshi Sakimoto's scores (measured in FFTA2's 37 tracks): battles `skirmish`, `tense`, `boss`, `final`; `prepare` (formation), `briefing` (map and plan), `worldmap`; scenes `sorrow`, `intrigue`, `triumph`, `comedy`; and the `recruit` jingle (someone joins the party).
  - Japanese music with koto, shakuhachi, taiko, hyoshigi, and rin, benchmarked against the most praised *Utawarerumono* tracks: `shrine` (a sanctuary, almost no pulse), `village` (a village at dusk), `festival` (a matsuri), `kagura` (a battle danced like kagura), `elegy` (a lament). In, yo, and ryukyu scales, phrases with breathing space (*ma*), koto doubling the shakuhachi melody (heterophony), orchestra underneath in fifths and fourths.
  - Styles: `orchestral`, `snes` (16-bit: console echo alternating between channels, darker highs), and `chip` (8-bit).
  - The seed chooses key, progression, rhythms, and motif: the same seed always produces the same music, and every seed is different.

```python
from tare.tools.tune import Sfx, write_wav
from tare.tools.tune.music import Cue
from tare.tools.tune.score import Score, chord

write_wav("victory.wav", Cue("victory", seed=3).render(), 48000)   # stereo

tavern = Cue("tavern", seed=7)
write_wav("tavern_loop.wav", tavern.render(), 48000)              # exactly tavern.length seconds
write_wav("battle_8bit.wav", Cue("battle", style="chip", seed=2).render(), 48000)
write_wav("grove_16bit.wav", Cue("grove", style="snes", seed=5).render(), 48000)

scene = Score(bpm=96)
scene.track("harp", pan=-0.3, send=0.3).play("harp", [("A3", 0, 1), ("C4", 1, 1), ("E4", 2, 2)])
scene.track("strings", send=0.4).play("strings", [(chord("Am", 3), 0, 4), (chord("F", 3), 4, 4)])
scene.add(Sfx("blade", "steel").render("clash"), at=scene.beats(4), pan=0.5, send=0.2)
write_wav("scene.wav", scene.render(), 48000)
```

For complete stereo scenes (effects, creatures, speech, and music over ambience), see [`examples/scenes.py`](../examples/scenes.py): a dungeon fight, treasure in a cave, and a magic duel.

**Adaptive layers.** A loop also comes as stems that add up to it: `tavern.layers()` returns `base` (harmony and bass), `rhythm` (percussion) and `lead` (the melody), leaving out a group the cue does not play. Start them together and fade groups in and out as play heats up (Godot's `AudioStreamSynchronized`, FMOD or Wwise layers). `Score.render_layers({"group": [track names]}, loop=...)` splits your own score the same way. In a bestiary, cues go in a `music` section, and `bake` writes `mix.wav` (and each layer) with the loop in a sampler chunk, plus `bpm`, `meter` and `bars` in the manifest:

```json
"music": {
  "town":    {"cue": "town", "style": "snes", "seed": 2, "layers": true},
  "fanfare": {"cue": "victory", "seed": 3, "lufs": -16}
}
```

With layers, `mix.wav` is exactly their sum; as 16-bit files, the layers add up to it within one step per layer. `"lufs"` brings a cue down to that loudness (BS.1770) and `gain_db` in the manifest says by how much. It only lowers: a cue already peaks near −1 dB, and it never goes past a true peak of −1 dBTP, so a quieter cue stays as it is and the manifest's `lufs` says where it is. The 96 cues (32 × 3 styles) measure −19 to −9 LUFS: −16 reaches 86 of them, −18 reaches 94. Only music takes a target: loudness is measured over 400 ms blocks, so a click or a hit has none (`null`) and keeps its peak.

Notes are `(note, time, duration[, intensity])`. A note can be a name (`"C#5"`), MIDI number, or list (a chord). Intensity changes timbre as well as volume: a loud trumpet opens up the highs, and a soft strike is darker.

Measurements come from isolated notes in the [VSCO-2 Community Edition](https://github.com/sgossner/VSCO-2-CE) orchestra (CC0) and CC0 guitar notes from Freesound. They were used only for measurement and are not in the repository. Details are in [Architecture: Music and composition](architecture.md#music-and-composition).

## CLAP calibration

[CLAP](https://huggingface.co/laion/clap-htsat-unfused) puts sound and text in the same space, letting you ask "does this sound like a cat meowing?". tare.tools.tune uses two models: one for optimization (`laion/clap-htsat-unfused`) and another, never used for optimization, as the judge (`laion/larger_clap_general`). This keeps tuning from memorizing a single model's preferences.

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[clap]"

tare.tools.tune design "a small cat meowing" -o cat.json --wav cat.wav   # creature from text
tare.tools.tune match meow.wav --archetype mammal -o cat.json            # creature matching a recording
tare.tools.tune judge                                                  # what the judge hears in each archetype
```

- `design` tests all archetypes (or only those in `--archetype`), refines the best 2 with an evolutionary strategy, and returns a ready bestiary entry (`-o`). Takes about 1 minute on CPU.
- `match` combines CLAP with recording measurements (pitch contour, envelope, spectrum, duration, syllable count).
- The result is always a normal procedural creature: variation per individual and take still applies.

**What the judge reported.** It identifies the archetype correctly in 32% of cases versus 10% by chance, and labels 56% of non-chip sounds "8-bit video game sound". To address this, an optional realism layer adds background noise, short room reflections, high frequency loss, amplitude fluctuations, and breath. Tuning with the optimizer reduced the judge's "8-bit" rate to 46% but did not improve archetype accuracy. The layer is therefore off by default. Enable it with `tare.tools.tune.archetypes.REALISM.update(REALISM_CLAP)`.

## Two ways to use it

### 1. Offline: generate assets for any engine

A bestiary file becomes WAV packs, plus a `manifest.json` (each sound's duration, peak, loudness in LUFS and true peak) and a JSON spec for each sound:

```bash
tare.tools.tune bake examples/bestiary.json -o baked     # 19 creatures × 5 calls × 3 takes
```

```json
{
  "takes": 3,
  "creatures": {
    "cub":       {"archetype": "mammal", "species": "wolf", "size": 0.15, "aggression": 0.15},
    "wolf":      {"extends": "cub", "size": 0.45, "aggression": 0.5},
    "dire_wolf": {"extends": "wolf", "size": 0.9, "aggression": 0.85},
    "mystery":   {"random": 7}
  }
}
```

`extends` inherits from another entry (evolutions, variants), and `random` generates a new random creature. NPC dialogue goes in a `speakers` section, with each speaker's role or voice and lines. This example uses Portuguese, including for the natural voice bank:

```json
"speakers": {
  "king":       {"role": "main", "gender": "m", "lines": {"quest": "Salve o reino!"}},
  "blacksmith": {"voice": "deep", "lang": "pt", "lines": {"greet": "Bem-vindo à forja, viajante!"}},
  "guard":      {"voice": "npc:12", "lines": {"halt": "Alto lá! Quem vem?"}},
  "crowd":      {"role": "crowd", "lines": {"chat": "Que dia bonito hoje."}},
  "wolf":       {"creature": "wolf", "lines": {"greet": "Olá, viajante."}}
}
```

Set `"natural_voices": false` at the top of the file (or `bake --no-natural`) to use formant synthesis for all speech.

Import `baked/` into Unity, Godot, Unreal, FMOD, or Wwise and pick a random take per call.

### 2. Runtime: generate inside the game

- **Python games** (pygame, pyglet, Arcade, Panda3D, Ren'Py): `VoiceBank` renders in threads, caches results, and never repeats the same take twice in a row. See [`examples/pygame_demo.py`](../examples/pygame_demo.py).

  ```python
  from tare.tools.tune.runtime import VoiceBank

  bank = VoiceBank(sample_rate=44100, takes=4)
  bank.warm(wolf)                                     # during loading
  audio = bank.get(wolf, "attack", block=False)        # None if it is not ready yet
  line = bank.line(Speaker.preset("child"), "Hi!", "en")   # cached speech too
  ```

- **Godot** (`native/godot`): the `tare_tune` extension provides the C++ renderer. Python designs sounds as small specs (`Sfx(...).voice("confirm").to_json()`, `Speaker.voice(text).to_json()`: 1–10 KB), and the game turns them into sound on demand, matching Python to within 10⁻⁶ (speech 10⁻⁵), far below hearing. Speech uses exported voice banks (`tare.tools.tune.speech.tvb.export`, ~21 MB per voice):

  ```gdscript
  var sound := TareSound.new()
  $Click.stream = sound.render(FileAccess.get_file_as_string("res://sounds/confirm.json"))
  $Low.stream = sound.render(FileAccess.get_file_as_string("res://sounds/confirm.json"), 48000,
                            {"register": -1, "tempo": 1.5})   # adjust knobs on demand
  var bank := TareVoiceBank.new()
  bank.load("res://voices/pt_alex.tvb")
  sound.add_bank(bank)
  $Speech.stream = sound.render(FileAccess.get_file_as_string("res://lines/00.json"))
  ```

  Godot supports effects, creatures, natural speech, and ambience loops. Still pending: the `chip` archetype and Generation 1, vocalizations, and music mixing, which currently use WAVs from `bake`. A 3 s line renders in ~0.13 s; the example project (`native/godot/demo`) generates the next line in a thread while the current one plays. Build with `python tools/build_native.py godot` and `python tools/build_native.py demo`. On Windows with Smart App Control enabled, a newly compiled, unsigned DLL is blocked; the Godot test then runs in WSL, using the Linux extension (the same `python tools/build_native.py godot` command, inside WSL) and Godot for Linux: `TARE_TOOLS_TUNE_GODOT=~/tools/godot/Godot_v4.7.2-stable_linux.x86_64 python -m pytest tests/test_godot.py`. Dialogue text is planned in Python beforehand; C++ planning (new text inside the game) will follow once voice tuning settles.

- **Other engines:** sound is described by a portable **JSON spec**. Randomness uses SplitMix64 + FNV-1a, with test vectors, and the renderer uses simple building blocks (PolyBLEP, biquads, one-pole filters). A native renderer in C#, GDScript, or C++ can play specs generated here or, by porting the archetypes too, invent new creatures in real time. The portability contract is in [Architecture](architecture.md).

## Command line

```bash
tare.tools.tune list                                                    # archetypes and calls
tare.tools.tune render monster --species ogre --size .9 --aggression .8 --call attack -o ogre.wav --png
tare.tools.tune spec chip --species 3 --call hurt -o pixel_hurt.json     # JSON spec for engines
tare.tools.tune from-spec pixel_hurt.json -o pixel_hurt.wav
tare.tools.tune zoo -n 30 -o zoo                                        # 30 original creatures
tare.tools.tune gen1 pikachu                                            # Generation 1 reproduction
tare.tools.tune gen1 all -o gen1/
tare.tools.tune say "Olá, viajante!" --voice child -o hello_pt.wav --phonemes   # Portuguese speech
tare.tools.tune say "Hello there!" --lang en --voice npc:7 --pitch 140
tare.tools.tune say "What a lovely day!" --lang en --role crowd --name crowd   # crowd babbling
tare.tools.tune say "Hi, how are you?" --lang en --voice cute --style animalese
tare.tools.tune sounds                                                  # effects: kinds, styles, events
tare.tools.tune sfx blade steel --event clash --species excalibur -o clash.wav
tare.tools.tune sfx ambience storm --event loop -o storm.wav              # seamless loop
tare.tools.tune voices                                                  # voice presets
```

## Generation 1 reproduction

`tare.tools.tune.chip` reimplements the Pokémon Red/Blue cry engine: 2 pulse channels and 1 noise channel, at 1,048,576 Hz, with antialiasing during decimation. It was checked against the fork's original TypeScript engine across all 151 cries (its frozen renders, like the game data, stay out of the repository):

- identical durations;
- bit for bit noise;
- matching pulses except for isolated edges displaced by 1 sample (~1 µs), caused by floating point rounding in the old code.

By default, 7-bit noise follows the real hardware, fixing a bug in the old app. `--legacy-noise` reproduces the old behavior.

Cry data (`data/gen1/cries.json`) is third-party game data and **is not in the repository or the package**. With your own copy, put it at that path or point `TARE_TOOLS_TUNE_GEN1_DATA` to it; the engine's checks against that data are not published either.

## Development

```bash
pytest -q          # ~620 tests; the native and Godot ones skip until built, the tape ones until downloaded
ruff check .

pip install -e ".[asr]"
python tools/intelligibility.py -v    # speech transcribed by Whisper (character error rate)

pip install -e ".[teacher]"                    # Kokoro, soundfile, pyworld: tools only
python tools/build_speech.py render pt        # teacher reads the corpus (cached in teacher/)
python tools/build_speech.py build pt         # analysis -> voice banks in src/tare/tools/tune/speech/data
python tools/build_speech.py label pt         # rebuild bank labels and models without new analysis
python tools/real_prosody.py fetch|align|fit   # experimental: intonation learned from real Brazilian readers
python tools/build_native.py build           # C++ vocoder (native/) for Godot; tests/test_native.py compares it
python tools/teacher_calibration.py render   # natural Kokoro speech as the Portuguese teacher
python tools/teacher_calibration.py measure  # formants, durations, and fricatives measured per phoneme
python tools/structure_analysis.py compare   # frame by frame spectra against the teacher, per phoneme class
python tools/structure_analysis.py mos       # predicted naturalness (UTMOS): teacher 3.5, our engine 2.2
python tools/structure_analysis.py transplant # which part of our speech costs naturalness
python tools/structure_analysis.py compare --set klatt.FRIC_GAIN=2 --speaker tilt=4000   # try a change

python tools/build_barks.py --download output/barks --audio   # download the CC0 recordings (tape mode and its tests)
python tools/build_barks.py --freesound DIR --oga DIR   # rebuild vocalization templates (requires recordings and pyworld)
```

**Listening curation** (`tools/curate.py`): sound comparison rounds, served only on this machine (127.0.0.1), because game references stay on it. The page plays each version and switches at the same position (keys 1–9), plays at ½× or ¼× like tape to find artifacts (S), matches loudness, and draws the spectrogram, difference from a reference, and average spectrum, alongside measurements. It also saves answers to `answers.json` as they are given: best choice, 1–5 ratings, a category per sound, blind ABX, moments and regions marked on the spectrogram (Shift+click, Shift+drag), and freeform notes. A blind round hides names and shuffles order.

```bash
python tools/curate.py serve          # opens http://127.0.0.1:8765 with the rounds
python tools/curate.py answers NAME   # answers submitted in a round (--json: as data, per bundle)
python tools/curate.py compare NAME BUNDLE_A BUNDLE_B  # exact retained audio, blind A/B/X
python tools/curate.py compare NAME A B C --open --question "Which sounds firmer?"  # 2–9 bundles: pick and 1–5
python tools/curate.py compare NAME A B --reference ref.wav  # a recording first as REF, its measures the targets
```

`compare` takes 2–9 `dsl review`/`edit` bundles, labelled A, B, C… in the given order. `--open` shows each candidate's source changes against A and its measurements; `--task` replaces the default tasks; `--keep-levels` opens without loudness matching, for questions about level; `--reference` puts a recording first as REF ([the numbers beside it](dsl-review.md#hold-a-sound-against-a-recording)). `answers --json` returns only answered tasks, keyed by label, with each label's bundle path, so the listener's choice feeds the next `dsl edit` directly ([how](dsl-review.md#ask-a-listener)).

Rebuilding a round preserves its audio and evaluations under revision-specific paths. Answer saves require a revision and answer version, so old tabs cannot overwrite newer evaluations. The live player is also available through `python tools/curate.py studio examples/authoring.json`.

The tools' findings are in [Architecture](architecture.md): the gap to natural speech lies in the spectral envelope from frame to frame, and no formant engine parameter adjustment closes it. The natural engine therefore takes the envelope from recordings (voice banks) and leaves phonemes, rhythm, and intonation to rules.

Performance in this development environment (4 cores), at 48 kHz: each sound takes 20–250 ms to generate, and `bake` produces about 40 sounds per second.

## Credits

English pronunciation comes from the [CMU Pronouncing Dictionary](https://github.com/cmusphinx/cmudict) (BSD license, included in `src/tare/tools/tune/speech/data/LICENSE-cmudict`). The speech synthesizer follows Dennis Klatt's cascade/parallel design.

Emotion measurements come from emoUERJ, by Rodrigo G. Bastos Germano, Michel Pompeu Tcheou, Felipe da Rocha Henriques, and Sergio Pinto Gomes Junior (UERJ, 2021, [CC BY 4.0](https://doi.org/10.5281/zenodo.5427549)); recordings were used only for measurement.

Natural voice banks come from [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) readings (Apache-2.0), generated offline; the package includes only the numbers measured from them.

The native core (`native/`) uses [pocketfft](https://gitlab.mpcdf.mpg.de/mtr/pocketfft), by Martin Reinecke and Peter Bell (Max-Planck-Society, BSD-3), the same FFT used by numpy.

The experimental intonation tool (`tools/real_prosody.py`) measures real speech from the [TTS-Portuguese Corpus](https://github.com/Edresson/TTS-Portuguese-Corpus), by Edresson Casanova and colleagues (CC BY 4.0), and the Portuguese part of [CML-TTS](https://www.openslr.org/146/), by Frederico S. Oliveira and colleagues, based on LibriVox audiobooks (CC BY 4.0), aligned with the [Montreal Forced Aligner](https://montreal-forced-aligner.readthedocs.io/) and its Portuguese model (CC BY 4.0). None of these are included in the package.

Vocalizations start from CC0 recordings from OpenGameArt ("Voice Clip Pack - Male Adventurer RPG", Cici Fyre's "Female RPG Voice Starter Pack", "Male Grunt/Yelling sounds") and Freesound (IDs are in `tools/build_barks.py`). The package includes only the numbers measured from them, not the recordings (the adventurer pack's author appreciates credit to Brandon Song); synthesis follows the [WORLD](https://github.com/mmorise/World) vocoder design by Masanori Morise.

Instruments were measured from [VSCO-2 Community Edition](https://github.com/sgossner/VSCO-2-CE) notes by Versilian Studios (CC0). Recordings were used only for measurement and are not included in the package.

The Generation 1 cry engine is based on [dotsarecool's original synthesizer](http://dotsarecool.com/rgme/tech/gen1cries.html) ([video](https://www.youtube.com/watch?v=gDLpbFXnpeY)) and [ardean's TypeScript port](https://github.com/ardean/pokemon-gen1-cry-synthesizer), where this project began.

## License

Apache License 2.0 ([LICENSE](../LICENSE)), copyright 2026 Augusto da Silva Carvalho.
