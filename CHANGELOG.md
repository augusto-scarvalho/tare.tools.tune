# Changelog

Notable changes, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change
that alters rendered samples says so, since the same recipe is meant to give the same sound.

## Unreleased

### Added

- **8-bit music you compose.** `chip_voice` is one channel of a console, in the DSL
  (`"instrument": {"chip_voice": "pulse", "duty": 12.5, "fade": true}`) and in Python
  (`instruments.chip_voice(...)`): a pulse in four duties or the triangle bass, with `fade`, `slide` and `vibrato`.
  It has one voice, so a chord plays as an arpeggio at 60 notes a second. `examples/dsl-chiptune.tune.json` is a
  four-channel loop; `dsl help chiptune` holds the craft.
- **Spiccato.** A string section's short bounced stroke, measured on the VSCO-2 sections (186 notes): half amplitude
  40-80 ms after the start, a free ring after it, and a stroke about twice as bright as the note it leaves. Our bowed
  strings start dull and, in the cellos, rise twice as slowly, so short notes did not speak. The instrument keeps
  half of the recorded bite: in a blind round of four the listener picked that over the measured stroke and
  over pizzicato.
- **`march`, a battle arranged like a score.** A 48-bar loop from a seed, written to what 22 scores of game music
  share: one line per part, lines moving by step, parts entering in stages, the fast notes in the snare, a quiet
  terrace before the return. By ear, one untrained listener: with the tune held the same, this arrangement was
  picked over the `battle` cue's way of arranging it; as a seeded cue against `battle` it was picked in one pair
  of three (the slowest seed read as sluggish, two lone crashes as mistakes: tempo is now 126-142 and every loud
  phrase has its crash), and its short strings were preferred plucked to the measured spiccato, then the clearer
  spiccato to plucked. A lead, not a proof.
- **A score read without ears.** `dsl review` of a score adds `bars_db` (the mix's level bar by bar), each track's
  `level_db` under the loudest one, `rubs` (what `Score.clashes()` finds) and `arrangement`.
- **A layout read from the notes.** `Score.arrangement()` gives notes per attack, the share of leaps, how many
  parts play and how full each 4 bars are, without rendering. `dsl check --layout` returns it with the rubs for
  a score or cue of any size (a review renders, and refuses a long orchestral score); `dsl help arrangement`
  says what to look for. `tools/score_study.py` reads MusicXML scores with the same function,
  `tools/music_study.py` measures recordings, and [the study](docs/orchestral-arrangement.md) says what they
  found in a soundtrack and 22 scores.

### Changed

- **The snare has its shell back. This alters rendered samples:** every cue and score that plays `snare` sounds
  different. Against the VSCO-2 hits with the snares on, ours put over half its energy above 1.2 kHz where the
  recording has a sixth (centroid 2.4 kHz against 0.9); the wires now sit 10 dB lower under the head and its
  overtones, each band from 150 Hz up within about 2 dB of the recording. Still missing: the thump under 150 Hz.
  The 30 determinism references do not play a snare and are unchanged. Timpani and bass drum were measured the
  same way and left alone: their decay and bands already match.
- A pattern whose bar is miscounted says which bar and how many steps it has.
- `chip_kick`, `chip_snare` and `chip_hat` export to MIDI as drums.

## 0.2.0 (2026-11-05)

### Added

- **Music in `bake`.** A bestiary's `music` section bakes cues to `mix.wav`, with the loop in a sampler chunk and
  `bpm`, `meter` and `bars` in the manifest.
- **Adaptive layers.** With `"layers": true`, a loop also comes as `base`, `rhythm` and `lead` stems that add up to the
  mix (`Cue.layers()`, `Score.render_layers()`).
- **Loudness.** Every baked sound reports its loudness in LUFS (ITU-R BS.1770) and its true peak. A music entry may set
  a `"lufs"` target, which only lowers the level and never passes −1 dBTP.
- **Notes that rub.** `Score.clashes()` finds minor seconds and ninths held together in a score, without rendering,
  and says whether each is built into a chord or is a line over one. A test keeps each of the 96 cues from gaining
  rubs. The count alone says nothing: in a blind round, an untrained listener rated worst the excerpts with rubs
  within one section, and best those whose rubs were lines over chords.
- **Listen.** 25 sounds picked by ear are rendered by `examples/listen.py`. They can be played on a
  [GitHub Pages page](https://augusto-scarvalho.github.io/tare.tools.tune/) or downloaded from the `listen-1` release.
- **CI** on Windows, Linux (x86 and ARM) and macOS (ARM), with Python 3.10. It builds the native core on Linux and
  checks determinism: 30 sounds from every family are compared with 16-bit references made on Windows.
- **Install as an agent plugin.** In Claude Code, `/plugin install tare-tools-tune --marketplace
  augusto-scarvalho/tare.tools.tune`; for Codex and other agents, `npx skills add augusto-scarvalho/tare.tools.tune`.
  Either copies the files only: on first use the agent makes the skill's Python environment (Python 3.12+, a minute
  or two and 200 MB), and again after each update, which comes in a new folder.
- **`tare.tools.tune doctor`** checks an install: Python, the pinned numpy and scipy, the voice banks, one render.
- **`constraints.txt`**, which pins the numpy and scipy that every render was verified with.

### Changed

- **Renderer behavior `legacy-2`.** A `Score` is now normalized by its true peak instead of its sample peak, so music no
  longer passes −1 dBTP between samples. **This changes samples.** Music is up to 1.2 dB quieter on chip cues and less
  on the other styles; the waveform is otherwise the same. Voice rendering and the native core are unchanged.

### Fixed

- **Speech is the same on every CPU.** `np.convolve` and `@` ran on OpenBLAS, whose kernel depends on the processor, and
  a laptop and a desktop rendered 3 of 960 test sounds differently. **This changes samples** at float rounding, except
  one glottal pulse moved by one sample in the `elder` preset.
- **`export --ogg` no longer crashes on long banks.** libsndfile 1.2.2 killed the process, with no error, when a single
  write held about 20 s of stereo audio. The OGG file is now written in blocks.
- `SKILL.md` was back under its size budget, and a doc no longer carried a home folder path.

## 0.1.0 (2026-11-02)

First public release: creature cries, NPC speech in Brazilian Portuguese and English, barks, 34 kinds of sound
effects and 32 music cues, all deterministic and synthesized from code. It also includes the native core and Godot
extension, the semantic DSL with its review loop, and the `tune-game-audio` agent skill.
