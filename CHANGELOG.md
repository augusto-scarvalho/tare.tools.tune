# Changelog

Notable changes, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change
that alters rendered samples says so, since the same recipe is meant to give the same sound.

## Unreleased

### Added

- **Music in `bake`.** A bestiary's `music` section bakes cues to `mix.wav`, with the loop in a sampler chunk and
  `bpm`, `meter` and `bars` in the manifest.
- **Adaptive layers.** With `"layers": true`, a loop also comes as `base`, `rhythm` and `lead` stems that add up to the
  mix (`Cue.layers()`, `Score.render_layers()`).
- **Loudness.** Every baked sound reports its loudness in LUFS (ITU-R BS.1770) and its true peak. A music entry may set
  a `"lufs"` target, which only lowers the level and never passes −1 dBTP.
- **Notes that rub.** `Score.clashes()` finds minor seconds and ninths held together in a score, without rendering,
  and says whether each is built into a chord or is a line over one. A test keeps each of the 96 cues from gaining
  rubs. The kind matters more than the count: the `boss` cue, heard as harsh, rubs mostly inside held chords.
- **Listen.** 25 sounds picked by ear are rendered by `examples/listen.py`. They can be played on a
  [GitHub Pages page](https://augusto-scarvalho.github.io/tare.tools.tune/) or downloaded from the `listen-1` release.
- **CI** on Windows, Linux (x86 and ARM) and macOS (ARM), with Python 3.10. It builds the native core on Linux and
  checks determinism: 30 sounds from every family are compared with 16-bit references made on Windows.
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
