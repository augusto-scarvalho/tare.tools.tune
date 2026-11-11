# Architecture

[Documentation index](README.md) · [Project README](../README.md) · [Português brasileiro (alternative)](pt-BR/arquitetura.md)

## Pipeline

The authoring layer wraps this existing pipeline observationally: see [capture, inspection, revisions, and exports](authoring.md). Its diagnostic schema is separate from Voice serialization and default synthesis. [Verification results](authoring-verification.md) include historical fixtures and actual native/Godot execution.

```
Creature(archetype, species, size, aggression, individual, ...)
   │ .voice(call, take)
   ▼
Genome(species, individual, take) + Traits(size, aggression) + Call
   │ archetype (design: arithmetic only, < 3 ms)
   ▼
Voice  ── the "spec": plain, versioned JSON ──►  render(voice, sr)  ──►  mono float32 audio
```

The system deliberately separates two stages:

- **Design** (genes, traits, and a call become a spec): cheap, deterministic, no DSP.
- **Render** (spec becomes audio): all signal processing happens here.

The spec is the handoff between them. It can be saved alongside an asset, sent to an engine, or edited by hand.

| Module | Role |
|---|---|
| `rng.py` | portable randomness: SplitMix64 + FNV-1a |
| `genome.py` | named genes: stable per species, variation per individual and take |
| `calls.py` | `Traits` (size, aggression) and `Call` (idle, alert, attack, hurt, death) |
| `archetypes/` | `natural.py`, `fantasy.py`, `retro.py`: each archetype is `design(ctx) -> Voice` |
| `spec.py` | `Voice` and its layers (`Syllable`, `ChipProgram`, `SpeechProgram`, `Modal`, `Noise`, `Scatter`, `Vocoded`) + JSON (v5) |
| `render.py` | source/filter DSP |
| `chip.py` | Game Boy engine (2 pulse channels + noise) and Generation 1 data reader |
| `creature.py` | main API (`Creature`) |
| `bake.py` | offline use: bestiary → WAVs + manifest |
| `runtime.py` | Python game runtime: `VoiceBank` |
| `cli.py` | command line |
| `speech/` | human speech: `g2p_pt.py` and `g2p_en.py` (text → phonemes), `phonetics.py` (targets, coarticulation, intonation), `klatt.py` (synthesis), `babble.py` (babbling), `casting.py` (engine selection), `concat.py` (natural engine: voice banks), `vocoder.py` (synthesis from measured frames), `emote.py` (vocalizations), `Speaker` |
| `clap.py`, `designer.py`, `analysis.py` | calibration: CLAP (text ↔ sound), evolutionary search (`design`, `match`), recording measurements |
| `sfx/` | sound effects: `Sfx`, materials, and `Fx` (`__init__.py`), `physical.py` (weapons, footsteps, explosions), `arms.py`, `magic.py`, `status.py`, `ui.py`, `home.py` (everyday life), `mounts.py` (cavalry, wings, marching, teleportation), `ambience.py` and `places.py` (locations) |
| `layers.py` | effects DSP: modal bodies, noise bands with moving filters, event clouds |
| `score.py` | composition: `Score` (tracks, positioned sounds, pan, shared stereo room, loops), note names, chords, scales |
| `instruments.py` | 44 instruments measured from recorded notes (each: `Note` → spec layers) |
| `music.py` | music from seeds: `Cue` (jingles and loops, orchestral or chip) |
| `music_tactics.py` | tactical RPG cues: battles, preparation, map, scenes, recruitment |
| `music_japan.py` | Japanese cues: shrine, village, festival, kagura, elegy |

## Determinism

All randomness comes from `rng.py`, so a port can reproduce it exactly:

- `fmix(z)`: SplitMix64 output function (constants `0xBF58476D1CE4E5B9` and `0x94D049BB133111EB`, shifts 30/27/31).
- `fnv1a(text)`: 64-bit FNV-1a of UTF-8 bytes.
- `key(p1, p2, ...)`: starts at `h = 0` and, for each part, computes `h = fmix((h ^ p) + GOLDEN)`. Strings enter as `fnv1a(s)`. Everything is modulo 2^64, with `GOLDEN = 0x9E3779B97F4A7C15`.
- `uniform(k) = (k >> 11) * 2^-53`. The stream `uniforms(k, n)[i] = uniform(fmix(k + (i+1)·GOLDEN))` is SplitMix64 seeded with `k`.
- `tri(k) = uniform(key(k, 1)) - uniform(key(k, 2))`.

Test vectors for checking a port are in `tests/test_rng_genome.py`. SplitMix64 seeded with 0 starts with `0xE220A8397B1DCDAF`.

**Genes:**

- `u(gene) = clip(base + variation·tri(key(species, fnv1a(gene), individual, 1)) + take_variation·tri(key(species, fnv1a(gene), individual, take, 2)))`, with `base = uniform(key(species, fnv1a(gene)))`.
- `choice` uses only `base`, so the **structure** (vowel, monster type, call shape) is fixed per species.
- Because genes are looked up by name, adding a gene does not reshuffle the others.

**Render seeds:**

- The voice seed is `seed32(archetype, species, individual, take, call)`, using 32 bits to fit any language.
- Syllable `i` uses `key(seed, "syllable", i)`, which produces the `"source"`, `"breath"`, `"jitter"`, and `"rough"` streams.
- Reverb uses `key(seed, "space")`.

**Note:** changing an archetype's formula changes the voices of existing species. Baked assets are unaffected because they store the WAV and spec.

## Spec (version 4)

Fields with default values are omitted from JSON (`Voice.to_dict`).

**Voice**

| Field | Meaning |
|---|---|
| `syllables` | list of `Syllable` |
| `chips` | list of `ChipProgram` (Game Boy engine) |
| `speech` | list of `SpeechProgram` (human speech, v2) |
| `drive` | `tanh` saturation |
| `crush` | 0..1, reduces sample rate and bit depth |
| `space`, `wet` | reverb tail in seconds and mix. The engine can substitute its own reverb |
| `gain` | final peak relative to -1 dBFS (idle is ~9 dB below attack) |
| `lowpass` | Hz, 0 = off: high frequency loss (distance, microphone) (v3) |
| `room` | 0..1, short room reflection mix (v3) |
| `air` | 0..1, recording background noise, -70 to -30 dB relative to peak (v3) |
| `modal`, `noise`, `scatter` | lists of `Modal`, `Noise`, and `Scatter` (sound effects, v4) |
| `vocoded` | list of `Vocoded` (performances reconstructed by the vocoder, v5) |
| `spoken` | list of `Spoken` (natural engine speech, v5) |
| `loop` | crossfade seconds; > 0 produces a seamless loop of `duration − loop` seconds (v4) |
| `bits` | 0 = off; adaptive quantizer bits: 4 gives the grain of DS and PSP samples (v6) |
| `seed` | seed for all random streams |
| `meta` | informational (archetype, call, traits) |

**Syllable**: `start` and `dur` (s); `pitch` (Hz curve); `source` (`glottal`, `sine`, `pulse`, or `noise`); `pulse_width`; `brightness`; `vibrato` [Hz, semitones]; `jitter` (semitones); `sub`; `rough` [depth, Hz]; `breath`; `ring` [Hz, mix]; `formants` [[Hz, bandwidth, gain], ...]; `mouth` (formant scale curve); `pulses` [Hz, depth, sharpness]; `attack` and `release` (s); `amp` (curve); `gain`; `shimmer` (random volume fluctuation, v3).

A curve is `[[t, value], ...]` with `t` from 0 to 1. Pitch is interpolated logarithmically; everything else, linearly.

**ChipProgram**: `pulse1`, `pulse2`, and `noise` contain commands `{"duty": byte}` or `{"note": [dur-1, volume, fade, frequency or NR43 parameter]}`; `pitch`; `length` (-128..127); `start`; `gain`; `hardware_noise`.

**SpeechProgram** (spec version 2): `frames` is a dictionary of tracks at `frame_rate` (400 per second):

- `f0`: pitch;
- `av`, `ah`: voicing and aspiration;
- `af`, `ab`: resonant and flat frication;
- `f1`…`f5` and `b1`…`b5`: cascade formants;
- `fnp`, `fnz`: nasal pole and zero;
- `fa`/`wa`/`ga` and `fb`/`wb`/`gb`: two frication resonances (Hz, bandwidth, gain).

Also stores `tilt`, `jitter`, `rough`, `sub`, and informational `text`, `lang`, and `phonemes`.

**Modal** (v4), a struck or scraped body: `start`, `dur`; `modes` [[Hz, T60 in s, gain], ...]; `hits` [[s, gain, contact duration in s], ...]; `scrape` [start s, duration s, gain, chatter Hz]; `hardness` (excitation lowpass, Hz); `click` (contact noise mixed in); `gain`.

**Noise** (v4), a noise band: `start`, `dur`; `freq` (Hz curve); `filter` (`band`, `low`, or `high`); `q`; `color` (`white` or `brown`); `amp` (curve); `attack`, `release`; `wobble` [Hz, depth]; `gain`.

**Scatter** (v4), an event cloud: `start`, `dur`; `rate` (events per second curve); `event` (`pop`, `drop`, or `ping`); `freq`, `decay`, and `level` (ranges [min, max]); `gain`.

**Vocoded** (v5), a short performance reconstructed by the vocoder (`speech/vocoder.py`) from a template: `clip` (template name, `<type>/<performer>/<take>`, e.g. `attack/adventurer/attack3`); `start`; `pitch` (pitch ratio); `warp` (formant ratio: shorter tract, higher formants); `stretch` (duration ratio); `breath` (−1..1: less air, down to pure voice, or more air, up to whisper); `tilt` (dB per octave around 1 kHz); `swing` (pitch contour width: 1 = as recorded, 0 = monotone); `gain`. Templates are in `speech/data/barks.npz`; a port must include them (see the algorithm below).

**Spoken** (v5), natural engine speech (`speech/concat.py`): `bank` (`<language>/<voice>`, e.g. `pt/alex`); `pieces` [[start frame, end frame, output frames], ...] (bank segments in 5 ms frames, stretched over the output); `joins` (indices of pieces entering with a crossfade); `f0` (pitch per output frame, Hz, used where the bank is voiced); `start`; `warp`, `breath`, and `tilt` (as in `Vocoded`); `gain`; and informational `text`, `lang`, and `phonemes`. Banks are in `speech/data/bank_<language>_<voice>.npz`, in the same format as vocalization templates.

Specs from versions 1 through 4 remain readable.

## Rendering algorithm (for ports)

Per syllable, with `n = max(floor(dur·sr), 16)` and `t = i/sr`:

1. **Pitch**: logarithmic interpolation of `pitch` at `n` points from 0 to 1. Then `f0 *= 2^((vib_depth·sin(2π·vib_rate·t) + jitter·smooth(key(k,"jitter"), 25/s)) / 12)`, clamped to `[1, 0.49·sr]`.
   - `smooth(k, n, sr, rate)`: `P = max(2, floor(n/sr·rate)+2)` control points `noise(k, P)` (uniform in [-1, 1)), interpolated linearly.
2. **Source**: `cycles = cumsum(f0/sr)`, `phase = frac(cycles)`, `dt = min(f0/sr, 0.5)`.
   - `glottal`: sawtooth `2·phase − 1 − polyblep(phase, dt)`.
   - `pulse`: `±1` with width `w`, plus `polyblep(phase) − polyblep((phase − w) mod 1)`.
   - In both cases above, first-order lowpass (bilinear Butterworth) at `min(median(f0)·(1.5 + 40·brightness²), 0.45·sr)`.
   - `sine`: `sin(2π·cycles) + 0.12·sin(4π·cycles)`.
   - `noise`: `0.8·noise(key(k,"source"), n)`.
   - Then, in order:
     - `sub`: `x *= 1 + sub·cos(π·cycles)`;
     - `breath`: `x = x·(1−b) + 0.7·b·noise(key(k,"breath"), n)`;
     - `ring`: `x *= 1 − mix + mix·sin(2π·hz·t)`.
3. **Formants**: parallel RBJ bandpass filters (0 dB peak), coefficients updated every 64 samples and filter state preserved between blocks.
   - Block `b`: `s = mouth` interpolated logarithmically at point `b` of `ceil(n/64)` points from 0 to 1.
   - `f = min(hz·s, 0.45·sr)`, `w0 = 2πf/sr`, and `α = sin(w0)·min(bw·s, f)/(2f)`.
   - Coefficients: `b = [α, 0, −α]/(1+α)` and `a = [1, −2cos(w0)/(1+α), (1−α)/(1+α)]`.
   - Output: `Σ gain·y`. Without formants, the signal passes through.
4. **Envelope**: `amp` interpolated linearly.
   - Attack of `A = clamp(floor(attack·sr), 1, n)` samples, multiplied by `linspace(0,1,A)²`. Release is the same, reversed.
   - `rough`: `env *= 1 − d·(0.5 + 0.5·sin(2π·rate·t + 3·smooth(key(k,"rough"), 8/s)))`.
   - `shimmer`: `env *= max(0, 1 + shimmer·smooth(key(k,"shimmer"), 60/s))`.
   - `pulses`: `env *= 1 − d + d·(0.5 − 0.5·cos(2π·rate·t))^sharpness`.
5. The syllable is `x·env`, normalized to peak = `gain`.

For the whole voice:

1. Sum, at `floor(start·sr)`, the syllables, chips (normalized to peak = `gain`), speech, and effect layers (below).
2. Second-order Butterworth highpass at 40 Hz, then normalize to peak 1.
3. `crush`: sample-and-hold for `1 + floor(11·crush)` samples, quantized to `2^(14 − 10·crush)` levels.
4. `drive`: `tanh(d·x)/tanh(d)`.
   `bits` (v6): an adaptive quantizer, the grain of 4-bit ADPCM samples: `env` = one-pole filter over `|x|` (`a = 1 − e^(−1/(0.005·sr))`, `lfilter([a], [1, a − 1])`), step `q = max(env·2^(1 − bits), 2^−15)`, output `round(x/q)·q` (ties to even).
5. Realism (v3), in order:
   - `lowpass`: second-order Butterworth at `min(lowpass, 0.45·sr)`;
   - `room`: 60 ms IR with 1 at sample 0 and 40 reflections at `floor(uniforms(key(key(seed,"room"),"taps"), 40)·(N−1))`, gains `noise(key(key(seed,"room"),"gains"), 40)·e^(−3·tap/N)`; output `(1−room)·x + room·wet_signal·peak(x)/peak(wet_signal)`;
   - `air`: `noise(key(seed,"air"), n)` through a first-order lowpass at 1 kHz, normalized to peak 1 and added with gain `10^((−70 + 40·air)/20)`.
6. Reverb:
   - IR: `noise(key(seed,"space"), N)·exp(−6.9·i/N)`, with `N = space·sr`, through a second-order Butterworth lowpass at 5 kHz.
   - Output: `(1−wet)·dry_signal + wet·tail·peak(dry_signal)/peak(tail)`.
7. With `loop`: the segment after `T = (duration − loop)·sr` samples wraps to the beginning. The first `L = loop·sr` samples are crossfaded at constant power, `beginning·sin(πw/2) + ending·cos(πw/2)` with `w` from 0 to 1; the rest (reverb tail) is added at `(L + i) mod T`. Without `loop`: 4 ms fade at the end.
8. Normalize to peak `0.89·gain`.

**Effect layers (`layers.py`, v4)**, each normalized to peak = `gain`, with `k = key(seed, type, index)`:

- **Modal:**
  - Excitation sums, for each `hit` `i`, `noise(key(k,"hit",i), L)·hann(L)·gain` with `L = max(contact·sr, 2)`.
  - Scraping adds `0.3·gain·noise(key(k,"scrape"), L)·sin²(π·j/L)`, times `1 + 0.8·sin(2π·chatter·t)` when chatter is present.
  - Everything passes through a first-order lowpass at `hardness`.
  - Each mode (20 Hz ≤ f < 0.45·sr) is a resonator `b = [sin w]`, `a = [1, −2r·cos w, r²]`, with `w = 2πf/sr` and `r = 10^(−3/(T60·sr))`: unit amplitude impulse response, −60 dB at T60.
  - Output: `click·excitation + Σ gain·mode`.
- **Noise:**
  - Source `noise(key(k,"noise"), n)`; `brown` passes through `1/(1 − 0.997·z⁻¹)` and is normalized.
  - RBJ filter (bandpass with bandwidth `f/q`, lowpass or highpass with Q = `q`), coefficients every 64 samples via `time_varying` direct form I, frequency from the logarithmic curve.
  - Envelope as for syllables, times `max(0, 1 + depth·smooth(key(k,"wobble"), Hz))`.
- **Scatter:**
  - `M = ceil(max(rate)·dur)` candidate times `sort(uniforms(key(k,"times"), M))·dur`, retained where `uniforms(key(k,"keep"), M)·max(rate) < rate(t)`.
  - Per event `i`: log-uniform `f`, uniform decay and level (`freq`, `decay`, `level` streams), length `max(5·decay·sr, 8)`, envelope `e^(−t/decay)`.
  - `pop`: `noise(key(k,"ev",i))` through a second-order Butterworth bandpass `[f/1.5, 1.5f]`.
  - `drop`: `sin(2πf(t + t²/(4·decay)))`.
  - `ping`: `(sin(2πft) + 0.4·sin(2π·2.76ft)·env)·env`.

**Speech (`speech/klatt.py`)**, with interpolated tracks: amplitudes and `f0` per sample, coefficients every 48 samples.

1. **Source:** PolyBLEP sawtooth at `f0` (with jitter), first-order lowpass at `tilt`, optionally `sub`. Sum `av·source` and `ah·noise`; noise pulses with the glottal cycle when voiced.
2. **Cascade:**
   - nasal pole (`fnp`, bandwidth 100) → nasal zero (`fnz`, bandwidth 100) → R1…R5 (`fK`, `bK`);
   - Klatt resonators with unit DC gain: `C = −e^(−2π·bw/sr)`, `B = 2e^(−π·bw/sr)·cos(2πf/sr)`, `A = 1 − B − C`;
   - the antiresonator uses `[1/A, −B/A, −C/A]`.
3. **Parallel:** `af·noise` through two bandpass filters (`fa`/`wa`·`ga` and `fb`/`wb`·`gb`), plus `ab·noise` highpassed at 1.2 kHz, all multiplied by `FRIC_GAIN`.
4. **Output:** sum, `rough` (AM), highpass at 60 Hz, and normalization to `gain`.

**Vocoder (`speech/vocoder.py`)**, the same synthesis design as WORLD (M. Morise), in numpy and deterministic:

- **Templates** (`barks.npz`, a ZIP of `.npy` arrays): every 5 ms, `f0` (float16, 0 = unvoiced), `env` (uint8: spectral envelope in 32 mel bands from 40 Hz to 20 kHz, `value/2 − 107.5` dB), and `ap` (uint8: aperiodicity in 5 logarithmic bands from 500 Hz to 16 kHz, `value/255`); `meta` is JSON with type, performer, tract, median pitch, start and frame count of each template, and source (CC0 license).
- **Transformations**, frame by frame: `stretch` resamples frames (linear interpolation; `f0` only between voiced frames); `swing` computes `f0 = pitch_center·(f0/pitch_center)^swing`; `pitch` multiplies `f0`; `breath ≥ 0` gives `ap += breath·(1 − ap)`, `breath < 0` gives `ap *= 1 + breath`.
- **Per-frame filters** (`nfft` 2048 above 32 kHz, otherwise 1024): read the envelope at `f/warp` (linear interpolation in Hz, `ap` in log Hz), plus `tilt·log2(f/1000)` dB. Below the recorded pitch (500 Hz when unvoiced), the envelope measures nothing: hold its value at the pitch, falling 3 dB per octave. Voice: minimum phase of `√(P·(1−ap))`; air: minimum phase of `√(P·ap)` (or `√P` when unvoiced). Minimum phase comes from the doubled real cepstrum.
- **Pulses:** one per glottal period (frame `f0`, or 500 Hz when unvoiced). At each pulse at fractional time `t`, with `n` samples until the next:
  - air: `noise(key(seed,"breath", i), n)` minus its mean, via an `nfft` FFT times the air filter, times √3 (uniform noise with variance 1);
  - voice: minimum phase response with fractional delay (`e^(−2πif·frac/sr)`), minus DC (subtracted with a Hann window in the first half), times `√n`;
  - add both starting at sample `floor(t·sr)`.
- Finally, trim the tail below −80 dB relative to peak and normalize the layer to `gain`.

**Natural speech (`speech/concat.py`)**, from a `Spoken`:

- **Frames:** each piece `[a, b, n]` produces `n` frames at bank positions `a + (j + 0.5)/n · (b − a)`, with envelope and aperiodicity linearly interpolated between neighboring frames; voicing comes from the nearest frame (`f0 > 0`).
- **Joins:** at each piece listed in `joins`, the ±3 frames around its start blend both pieces, each continuing beyond the cut at its own pace, with linear weight from 0 to 1 (voicing follows the higher weight).
- **Pitch:** spec `f0` where voiced, 0 elsewhere.
- **Sound:** the vocoder above, with `warp`, `breath`, and `tilt`; seed `key(seed, "spoken")`; normalized to `gain`.

**Variable coefficients without clicks:** between blocks, filters carry direct form I history (two inputs and two outputs) and recalculate state for the new coefficients (`render.time_varying`). Reusing `lfilter` state across a coefficient change produces an audible click at every phoneme transition.

**Validating a port:** random streams must match bit for bit (test vectors). Audio will not be bit exact because of floating point operation order and FFT convolution. For comparison material, run `tare.tools.tune bake` with specs: each manifest entry includes the spec and reference WAV. Render the specs in the engine and compare spectra. With `space = 0`, the difference should be minimal.

## Sound effects

`Sfx(kind, style, species, size, power)` is `Creature` for effects. `kind` chooses the recipe (`@recipe` in `sfx/`); `style` chooses the material, element, or place. `species` is the object's identity: this sword's modes and this spell's pitch stay fixed (named genes, as with creatures), while each take randomizes the rest (strike position, spacing between contacts). Design only builds a `Voice`, so `bake`, `VoiceBank`, specs, and ports work the same way.

**Materials** (`MATERIALS`): mode range (lowest mode depends on size), mode count, lowest mode T60, damping (`T60·(f/f₀)^−d`), contact hardness, distribution, and a frequency below which the body radiates little.

- **Distributions:** `dense` for metal blades and plates, `sparse` for wood, stone, and glass, `bell` for bells with a minor third, `string` for harmonics with slight stiffness.
- **Radiation:** what makes a sword sound like a high "shiiing" rather than a bell.

**`AmbiencePlayer`** (runtime): plays the location loop continuously and schedules events at exponential intervals (Poisson process with `per_minute`). Each event has a few takes rendered in the background and is skipped if unready; output passes through `tanh` so thunder over rain does not clip.

**Bow: modeled from a recording.** Optimizing numbers (CLAP or recording statistics) flattened weapon character; one such attempt was reverted after listening. The bow follows another method:

- measure the mechanism in a reference recording at millisecond scale;
- build each part using those numbers;
- select variants by ear.

The parts:

- **Draw (`creak`):** ~60–70 friction slips per second, in nearly regular trains with a drifting rhythm.
  - Each slip rises in ~2 ms and resonates for ~10 ms in a dense cloud of wood modes within the measured bands (1.7, 2.9, 5.5, and 7.9 kHz), plus a slightly longer bending note.
  - Force grows with tension, over low background friction.
  - `creak()` works for any wood under strain.
- **Release (`bow_release`):**
  - a short "fwip";
  - the string scraping along the arrow: a rough buzz (~170 Hz) whose resonance falls from ~800 to ~300 Hz while rising ~20 dB (smooth noise sounded like a broom);
  - the impact, exciting the same wood as the draw (both must sound like the same bow) and the low stop;
  - string and limb vibration (~57 Hz and harmonics), with a lingering ~1.1 kHz partial;
  - the arrow departing, heard by the archer: starts at the buzz's ending level, falls as 1/r (r = 2 m + v·t, v ≈ 60 m/s, 90 m/s for crossbows), already lower in pitch (c/(c+v)) and darkening with distance.
- **Flight (`fletching`, `flyby`):** feathers blow a broad band near 3 kHz and make the air vibrate ~90 times per second.
  - Passing the listener, it rises ~40 dB (linear in dB) until the pass, then falls ~30 dB in 0.15 s, with the band dropping (Doppler).
  - The first assembly had a pause between release and flight, and flight restarted from far away: it sounded like "starts, stops, comes back". Release therefore includes the departing arrow, while `fly` is only the close pass.
- **Arrow in wood (`arrow_in_wood`):**
  - a crack (~15 ms, broadband);
  - the target body (modes ~140–240 Hz, ~60 ms);
  - the embedded shaft buzzing near 160 Hz, with harmonics, for over a second. It pulses ~26 times per second as it wobbles (two nearby modes beating).
- **Arrow in flesh (`arrow_in_flesh`):** a muffled thump near 195 Hz (−20 dB in ~50 ms), a short wet tear near 2.8 kHz, a puncture tick, and shaft vibration damped by flesh.
- **Arrow on stone (`arrow_on_stone`):** a hard crack; tip and shaft ring briefly and high (1.3–10 kHz, ~40 ms); the arrow falls and bounces, with subsequent contacts at ~0.39 s and ~0.23 s, at −14 and −18 dB. Sometimes the shaft breaks.
- **Levels:** flight and impact are ~4 and ~6 dB above release, as in the mix chosen by ear.

**Sword: measured from swing and clash recordings.**

- **Clash (`blade_clash`):** short and high, not a bell.
  - Measurements: 40 dB decay in 0.2–0.6 s; energy concentrated near 6 kHz; almost nothing below 1.5 kHz (third-octave average of six recordings, `BLADE_RING`).
  - Three parts: contact; blades scraping for 30–80 ms; often a second touch ~30 ms or ~170 ms later.
  - Each blade has ~60 dense modes between 1.2 and 12.5 kHz, fixed by species. Mode levels (`BLADE_MODES`) were tuned by rendering and comparing until the ring matched the measured average (±3 dB per band). The strike reweights modes per take. Three lower modes ring longer.
- **Swing (`blade_swing`):** ~0.25 s.
  - The blade's passing pressure push dominates (below 300 Hz). Alongside it, hiss centered at ~1.4 kHz rises ~30 dB in ~55 ms, falls in ~170 ms, and darkens as it slows.
- **Hits (`blade_hit`):** each target measured from recordings of a blade striking it.
  - Wood: a dry "tok". The board rings in a few low notes (~470, ~1080, ~1550 Hz) and vanishes in ~0.1 s (40 dB in 100–220 ms). The embedded blade barely resonates.
  - Stone: a hard, bright crack. The blade rings briefly (40 dB in ~100 ms), with short stone modes (1–5 kHz) and fragments scattering for ~60 ms.
  - Armor: a "clang". The plate has dense modes from 650 Hz to 6.5 kHz, strongest between 2.5 and 5 kHz; highs die in ~0.2 s while some lows last ~0.6 s. The blade rings underneath, with the body's muffled thump.
  - Flesh: the body thump (~90 Hz, ~0.1 s) is usually strongest. Above it are trembling wet hiss above 2 kHz (60–150 ms), a weaker squelch near 900 Hz, and small wet cracks.
- **Draw (`blade_draw`):** a broad, bright scrape (2.5–6 kHz) rising ~25 dB in 70–170 ms and holding. Sometimes the guard ticks against the scabbard mouth. The freed blade then keeps ringing: −20 dB in ~0.3 s, −35 dB in 0.5–1.2 s.
- **Drop (`blade_drop`):** the hilt hits first; 30–45 ms later the blade falls flat, the loudest impact. It rattles against the ground for ~0.15 s while ringing, then bounces again ~0.27 s later. Ground impact and a low thump sit underneath. The first version, without rattling and with little bass, sounded weak.
- **Variants selected by ear**, linked to traits:
  - size 1 = heavy blade: modes 25% lower, shorter ring, low impact in the arms, slower swing with a ~120 Hz "whoom"; hits have more thump, more stone fragments, and bone in flesh;
  - power 1 = cinematic: scraping up to 150 ms, ring 2.2× longer, fast swing with a blade groove whistle; hits have more blade and armor ring, and a sharp cut in flesh.
- **Levels:** swing has half the clash peak, as in the auditioned mix. `Fx.level(x)` gives each event's peak at maximum power, preserving the recipe's event balance at any power.

**Mace and hammer (`blunt`): measured from recordings** of clubs, hammers, pipes, and stones striking each target, and heavy swings.

- **Swing:** a dark "whoom". Almost all energy is below 1 kHz (centroid 0.4–1 kHz), often with a low tone near 150–270 Hz.
- **Hit:** the target sounds more than the weapon. The head (wood, iron, or stone) rings quietly underneath, alongside the mass thump:
  - flesh: a deep thump (110–370 Hz, 40 dB in 0.16–0.38 s) under the skin crack;
  - wood: a short knock, main mode ~350 Hz, disappearing in 30–170 ms;
  - metal: a lower, longer clang than a blade's (0.5–7 kHz, strongest at 1.6–4 kHz, 40 dB in 0.2–0.6 s);
  - stone: a broad crack with fragments.
- **Drop:** the head hits heavily, the handle falls 50–100 ms later, and there is a small bounce.
- **Variants:** as with swords, size 1 is heavier (lower, more thump, bone in flesh, more fragments) and power 1 is cinematic (more metal ring, stronger skin crack).

**Shield (`shield`): measured from recordings** of swords, clubs, and bashes against shields.

- **Sword on wooden shield:** fast, upper midrange. Almost no bass (−20 dB below 500 Hz). The panel rings near 0.85–0.95, 1.6–1.7, 2.2, and 3.3–3.8 kHz for 0.13–0.4 s, alongside blade ring; 40 dB in 130–200 ms.
- **Club on shield:** moves the whole panel, with low body at 120–400 Hz.
- **Metal shield:** denser and longer (0.23–3.4 kHz, 40 dB in ~0.3 s).
- **Arrow on shield:** leaves the shaft vibrating.
- **Bash:** muffled by the other person's body, with straps, rim, and boss rattling.

**Moving equipment (`gear`): measured from recordings** of chainmail, plate armor, and leather.

- **Chainmail:** a swell of small jingling rings, strongest at 8–12 kHz.
- **Plate:** separate knocks (1.6–8 kHz, strongest at 4–6 kHz) over rubbing.
- **Leather:** a creak of dense slips (70–100 per second), low down (strongest at 250–500 Hz, −20 dB above 2.5 kHz), over soft rustling. The same mechanism as drawing a bow, lower and more damped.
- **Events:** `move` for a step or gesture, `run` for a shorter, stronger movement, `equip` for putting it on (two movements and a buckle).

**Falling body (`body`): measured from recordings.** More than a single thump.

- **Fall (`fall`):** 3–6 low impacts in 0.2–0.5 s: knees, hip, torso (strongest), then an arm or head, separated by 60–150 ms and 4–14 dB below the torso. Each is a thump near 110–180 Hz. Strongest at 250–500 Hz, down ~14 dB at 2.5 kHz and ~20 dB at 8 kHz, with clothes rustling throughout.
- **Dead weight (`drop`):** only the torso and a small bounce.

**Doors and chests (`door`, `chest`): measured from recordings** of doors, chests, locks, and knocks.

- **Hinge:** creaks through slips at a steady rhythm, a harmonic tone at 600–1500 Hz. Pitch rises as motion accelerates and falls as it slows. Stick/slip makes the volume stutter.
- **Closing door:** low (strongest at 250 Hz), panel modes at 250–870 Hz ringing for 0.25–0.4 s.
- **Locked door:** rattles 2–5 times, 60–130 ms apart, high (strongest at 1.6–4 kHz).
- **Key:** turns pins with clicks every 50–130 ms; the bolt comes last and loudest.
- **Knuckle knock:** muffled, strongest at 250–1000 Hz, 0.15–0.25 s between knocks.
- **Iron gate:** resonates longer.

**Items (`item`): measured from recordings** of coins, corks, gulps, and pages.

- **Coins:** very high jingles (strongest at 8–13 kHz). Small coins ring at 8.4–13.7 kHz for 0.06–0.46 s, thick ones at 1.5–5 kHz, with multiple contacts 20–100 ms apart.
- **Dropped coin:** bounces (~0.1 s apart), then spins, rattling faster until it stops.
- **Cork:** low pop, bottle neck resonating at 500–1150 Hz for ~0.15 s.
- **Gulp:** low (strongest at 250–500 Hz, resonance near 1–1.3 kHz), bursts of 2–3 throat clicks 40–50 ms apart.
- **Page turn:** crackles at 1–6 kHz for 0.3–0.6 s, ending in a soft flutter.
- **Gem:** rings like crystal.

**Breaking (`breakable`): measured from recordings** of crates, clay pots, ceramics, and glass breaking.

- **Wooden crate:** splinters. Low to midrange (strongest at 250–1600 Hz), 9–18 cracks in the first half second and pieces falling until ~1 s. The barrel also has iron hoops.
- **Clay and ceramic:** short, upper midrange burst (strongest near 1.6 kHz, 40 dB in 130–180 ms): a crack and some shards. Our pot still has less high frequency energy than recordings above 4 kHz.
- **Glass:** high and long (strong up to 16 kHz, 40 dB in 0.3–0.9 s): a burst and many shards jingling as they fall.
- **`hit`:** impact without breaking.

**Interface (`ui`, in `sfx/ui.py`): measured from game UI sounds.**

- **Click:** 8–170 ms, a tick or soft thump.
- **Open bag:** 0.4–1 s rustle.
- **Level up:** ascending major arpeggio, notes 60–150 ms apart, ending on a long bright note with sparkles above; 1.6–3.4 s overall.
- **Quest complete:** climbs the chord more slowly (~0.2 s per note), resting on the top note.
- **Error:** short (0.14–0.6 s), low (around D♯3–A3), a buzz or two descending tones.
- **Styles:** `fantasy`, with bar bells (modes 1 : 2.76 : 5.40 : 8.93), cloth, and wood; `retro`, with square wave notes like an 8-bit console.
- **Key:** each species (each game) stays in a key near C5.

**Tactical RPG interface (the same `ui`, 14 additional events).** Measured from 200 CC0 UI sounds (Kenney's Interface Sounds, UI Audio, and RPG Audio packs; analysis only): duration to −40 dB, attack, decay, dominant frequency and whether it rises or falls, partials (their ratios identify the material), and tonal versus noise content.

| Measured category | Description | Event |
|---|---|---|
| tick | 10–54 ms, click with harmonic ring (800 Hz × 3, 4, 5, 6, 7, 12) or a cluster at 3.6 kHz | `cursor` (moving between tiles), `scroll` (list scrolling: same tick, cycling through 4 pitches across takes) |
| rollover | 52–174 ms, soft, 600–1400 Hz | `hover` (unit under cursor); `target` (enemy: low note rubbing against the semitone above) |
| select | 34–186 ms, bright struck tone (1–3 kHz) with octave, falling slightly | `select` |
| confirmation | 280–500 ms, pure notes rising by fifth and octave (1, 1.5, 2, 3), 60 ms each | `confirm` |
| back | ~60 ms, low (110–260 Hz), short thump | `cancel` (falls a fourth) |
| question | three ~100 ms notes, descending (G, F♯, E) or ascending | `turn` (unit's turn: ascending major triad), `enemy_turn` (lower, falls a semitone then a third) |
| maximize, minimize | pure tone gliding 10–13 semitones in ~250 ms | `open`, `close` in `crystal`; `range` (range display: fast ascending pentatonic scale with sparkle) |
| bookFlip | ~380 ms rustling at 1.6–7 kHz | `advance` (next dialogue page) |
| glass | nearly pure ring (~2 kHz) beating against a partner 2–4% higher | `crystal` timbre |

Plus `text` (one letter appearing: 35 ms on a pentatonic scale; `size` deepens the voice), `learn` (ability learned, class unlocked: chord rising to the twelfth, sparkling, ~1 s), and `battle` (battle start, ~1.6 s: roll swelling for 0.6 s and a struck chord over a low impact).

Four timbres for different game tastes: `fantasy` (glockenspiel measured from VSCO-2), `crystal` (glass, like the measured "glass"), `wood` (soft marimba and woodblocks), and `retro` (square wave). Notes use measured music instruments, damped after their intended duration. Battle start uses snare, timpani, trumpets, and horns in `fantasy`; triangle, tubular bell, and celesta in `crystal`; hand drum, slit drum, and marimba in `wood`; chip instruments in `retro`. Each take varies a few cents, up to 1.5 dB, and a few milliseconds, to avoid fatigue from a cursor heard hundreds of times per battle. Event level follows frequency of use: cursor, scrolling, and text quieter; confirmation and unit turn in the middle; battle start loudest.

**Hit outcomes (`ui`, 7 more events) and status effects (`status`, `sfx/status.py`).** Measured from RPG healing and buff sounds (leohpaz's "8 Heals and Buffs SFX", CC BY 4.0), RPG packs by artisticdude (CC0) and Reemax (CC BY 3.0), and Juhani Junkala's 512 retro sounds (CC0); analysis only:

| Measurement | Description | Event |
|---|---|---|
| retro hit | 40–110 ms, low noise (80–700 Hz), instant attack, falling | `damage` (number appearing: short thump under a low tick) |
| smite | bright flash (3.5–6.6 kHz) for ~0.3 s, then low ring (100–1400 Hz); falls ~33 semitones | `critical`, over the weapon hit |
| swing | 75–355 ms air, 450–1000 Hz | `miss` (air where the target was, plus two low notes) |
| heal | rises in 0.25 s to sparkle moving from 5 to 13 kHz, ~1 s | `heal`; `mp` is cooler, a fifth lower, and slower |
| revive | ~17 semitones rising over seconds of sparkle | `revive` (chord rising two octaves, ~0.11 s per note, over a soft chord) |
| negative, curse | fall 10–37 semitones | `ko` (three descending notes and a tone sinking an octave and a half) |
| atk buff | rises an octave in 0.15 s, then pure ring (~3 kHz) fading in 1.5 s | `buff` |
| debuff | low voice falling ~180 to ~75 Hz in 0.25 s, oscillating there for 2 s | `debuff` |
| def buff | three low pulses (120–300 Hz) ~0.75 s apart, 12 dB above steady ring near 1.2 kHz | `protect` |
| sleep | steady high tone (~4.3 kHz) over slowly descending notes (~0.25 s each, 1.9 → 0.9 kHz) | `sleep` |
| speed up | rising voice ~10 semitones, pulsing | `haste` (clock accelerating and rising); `slow` is the reverse |
| retro power-ups | 0.2–0.8 s, square wave rising 8–18 semitones (sometimes 44), steady level, then cutoff | `retro` timbre of `buff` and related events |

Designed without recordings, following the classics: `shell` (glass climbing a chord, breath), `stop` (ticking, then frozen: glass and an ice crack), `poison` (bubbles and a queasy tone beating against itself), `silence` ("shh" muffled at the end), `blind` (air darkening from 4.5 kHz to 250 Hz), `confuse` (two widely oscillating tones, circling birds), `charm` (heartbeat and a sweet sixth), `berserk` (rising saturated growl), `doom` (low reverberant bell), `stone` (grinding faster, then solid), `toad` (a puff and croak, twice), `zombie` (sinking moan), and `cure` (fast ascending chord). Tactical battles are quick: everything is shorter than the references (0.5–2.5 s). Two timbres: `fantasy` and `retro`. Key matches `ui` for the same species.

**Inside the games.** The numbers above came from generic RPG sounds. The games themselves were then measured: *Tactics Ogre: Reborn*, *FFTA2*, *Triangle Strategy*, *Octopath Traveler*, and *Unicorn Overlord* voices. Analysis only: none of their game assets are in the repository, only numbers.

- *Tactics Ogre: Reborn* has 247 named effects and pain/death voices (218 + 588).
- *FFTA2* (DS) has 573 named effects.
- *Triangle Strategy* names every sound (`SE_BTL_CMN_STATUS_SLEEP_HIT`...); *Octopath Traveler* uses only numbers.

What separates the generations (medians):

| | UI: duration, onset, bandwidth (99% of energy below) | Battle: duration, onset, bandwidth |
|---|---|---|
| *Octopath Traveler* (HD-2D) | 0.78 s, 0.10 s, 11.9 kHz | 1.46 s, 0.23 s, 11.8 kHz |
| *Triangle Strategy* (HD-2D) | 1.01 s, 0.10 s, 14.2 kHz | 1.27 s, 0.15 s, 13.1 kHz |
| *Tactics Ogre* (PSP, remade) | 0.40 s, 0.03 s, 9.4 kHz | 0.63 s, 0.14 s, 7.8 kHz |
| *FFTA2* (DS) | 0.18 s, 0.04 s, 3.3 kHz | — |

Hence era (`Sfx(era=...)`): `hd` adds room and a tail (1.2 s); `16bit` cuts above 5 kHz (gentle filter: 99% of energy remains below 4–9 kHz), adds 4-bit grain (`bits`, a quantizer whose step follows level in ~5 ms, like ADPCM), and removes reverb. The 8-bit sound remains the `retro` style.

**Knobs (`sfx/knobs.py`).** To vary a sound within its recipe's character, each `Recipe` has controls with defaults, ranges, units, and descriptions: general knobs (`register`, `tempo`, `length`, `ring`, `brightness`, `sparkle`), which act on spec layers after recipe design (thus meaning the same thing for a menu tick, sword, or spell), and recipe-specific knobs (`key` in `ui` and `status`). Defaults return the voice intact. `tempo` multiplies layer starts (and internal strikes in a struck body); `length` stretches starts, durations, decays, and rates without changing pitch; `register` multiplies frequencies, modes, bands, and hardness; `ring` multiplies body decays and beep durations; `brightness` hardens hits and boosts upper partials (positive) or cuts highs with `lowpass` (negative); `sparkle` scales or removes sparkle layers (`ping` `Scatter`). Knobs travel with `Sfx` (`to_dict`, `bake`) and into spec `meta`. The native core applies the same general knobs to a finished spec (`tt_render_voice(json, knobs, ...)`, `TareSound.render(spec, rate, knobs)` in Godot), in the same order and with the same arithmetic (so Python does not round the values they compute); `tests/test_native.py` compares both ends (maximum difference below 10⁻⁶), and `tests/test_godot.py` adjusts knobs inside Godot. Eras only change voice finishing, knobs only layers, so order does not matter: applying knobs in game to a `16bit` spec gives the same sound as designing with them. `key` belongs to design (chooses notes); in game, transpose through `register` (one semitone = 1/12).

What the games corrected in the events:

- `critical`: in TO, ~38 semitones rising in 0.67 s, almost entirely bright noise. Previously a falling flash; now rises and lands on a doubled note.
- `miss`: in TO and FFTA2, two short notes, second lower (~0.17 s), rather than breath (breath is the weapon swing).
- `buff`: swells in ~0.5 s in both games (TO 1.5 s, TS 2.4 s). `debuff`: falls ~19 semitones in both.
- `poison`: in TO, low bubbling (all below 1 kHz, a dozen bubbles, falling an octave).
- In TS: `sleep` is a low pure tone (~400 Hz) pulsing ~11 times per second and falling ~9 semitones; `silence` falls ~32 semitones; `blind` enters slowly (~0.4 s) and low (~600 Hz). Three new statuses: `paralysis` (bright crackling, centered ~7 kHz, falling ~9 semitones), `regen` (very high sparkle, ~9 kHz), and `expire` (status ending: bright tone entering in 0.3 s and sliding ~16 semitones down).
- Shouts: TO pain voices are ~0.4 s gasps, voiced for only a quarter to a third of their duration and near speaking pitch (men ~160 Hz, women ~380 Hz); death voices last 0.65–0.85 s, span 13–20 semitones, and fall ~5. Octopath battle shouts are only ~7 semitones above speech. Hence `emote`'s `gasp` style: type-specific duration (pain 0.42 s, death 0.75 s) and effort 0.4 (the performer shouted at full effort; the new voice does not).

**Previously missing weapons (`sfx/arms.py`: `spear`, `fist`, `gun`, `thrown`; plus `blade` quickdraw).** Measured in the games (*Tactics Ogre: Reborn* and *FFTA2* from the user's copies, *Triangle Strategy* effects) and Kenney's CC0 impacts; analysis only:

| Measurement | Description | Event |
|---|---|---|
| spear thrust (TO) | 0.28 s, 25 ms onset, air centered near 0.9 kHz, falling ~36 semitones | `spear` thrust |
| piercing (TO) | 15 ms onset, 0.44 s, noisy, rising tear | `spear` hit_flesh |
| dragoon jump (TS) | ~2.5 s and about eight events: push off, air rising and falling, crash | `spear` jump, land |
| fist through air (TO) and punch (Kenney) | ~70 ms air; on impact, low thump (center ~115 Hz, all below ~450 Hz), 0.28 s | `fist` swing, hit_flesh |
| gunshot (FFTA2, TO) | 0.6–0.8 s, 5–22 ms onset, burst centered at 0.7–1.1 kHz over a low tail | `gun` shot (flint and priming pan first, for flintlocks) |
| reload (FFTA2) | four bright clicks in ~0.26 s | `gun` reload |
| bullet impact (TO) | 0.29 s, noisy, ~1.9 kHz | `gun` impact |
| throw (FFTA2, TO) | short bright whistle, 0.13–0.14 s | `thrown` throw |
| grenade (FFTA2) | ~0.64 s and about four events | `thrown` fuse, blast |
| katana (TO, TS) | 0.34–0.63 s cut falling 30–46 semitones | `blade` quickdraw: draws in 0.12 s and cuts, edge singing downward |

**Previously missing spells (`spell`: water, wind, earth, poison, gravity, meteor; `summon`).** Measured from *Triangle Strategy* effects and *FFTA2* summons (user's copy); analysis only:

| Measurement | Description | Event |
|---|---|---|
| water (TS) | ~2.1 s, swelling in ~0.25 s, strongest at 1–4 kHz, rising slightly | `water`: plop, wave of foam, drops falling afterward |
| wind (TS) | ~2 s, gust swelling for ~0.5 s, broad (0.5–2 kHz) | `wind`: whistling gusts; while traveling, a whirlwind (rotating band) |
| earth (TS) | ~1.7 s, rock cracking loudest (~2 kHz), falling ~11 semitones | `earth`: descending cracks, stones, tremor |
| poison (TS) | ~0.9 s, ~40 ms onset, strongest near 4 kHz | `poison`: acidic hiss, bubbles underneath |
| summon arrival (FFTA2) | 4.6–8.4 s, swelling for ~2.3 s, low (63 Hz–1 kHz) | `summon` arrive: ground, rising air, voices, flash; dragon flaps and roars |
| summon strike (FFTA2) | ~2–5 s, weight at 125–500 Hz | `summon` strike: larger, lower elemental spell impact after a charge |

Designed without recordings, following the classics: `gravity` (sinking low tone, slow pulse, crushing) and `meteor` (whistle falling from the sky, descending roar, explosion, shower of stones). Summon departure (`leave`) rises: thinning voices, sparkle, air pulled upward.

**Everyday story sounds (`sfx/home.py`: `book`, `tableware`, `furniture`, `bell`; plus `door` slam/break, `item` letter, `gear` cloth).** Measured from *Triangle Strategy* scenes, *FFTA2* (user's copy), and Kenney's CC0 RPG/impact sounds; analysis only:

| Measurement | Description | Event |
|---|---|---|
| page | 0.35–0.9 s paper, strongest at 2–8 kHz, two or three crackles | `book` page; `flip` turns many |
| book opened, closed, set down | 0.14–0.48 s with low cover thump; closing is a slap (~0.18 s) at 250–500 Hz; setting down, ~0.17 s near 250 Hz | `book` open, close, place |
| drinking glasses | nearly pure, 1–2 kHz, ~0.11 s (fine crystal rings longer) | `tableware` clink |
| glass set down | 0.3–0.5 s, ring near 1 kHz over table impact | `tableware` set |
| plate breaking | ~0.9 s, bright (4–8 kHz) and noisy | `tableware` break |
| cutlery | light metal ticks at 1–4 kHz | `tableware` cutlery |
| chair dragged, fist on desk | ~0.4 s scrape near 0.9 kHz; ~0.36 s near 250 Hz | `furniture` chair, desk |
| bed | ~0.6 s creaking and clothing, low | `furniture` bed |
| bells | church and wedding: ~7 s, 125 Hz–1 kHz; little shop bell: ~0.6 s near 2 kHz | `bell` |
| doors slammed/broken down | ~0.8 s, weight at 63 Hz | `door` slam, break |
| letters passed | ~0.3 s paper, bright (8 kHz and above) | `item` letter |
| clothing (kneeling, bowing) | ~0.4 s, strongest near 500 Hz | `gear` cloth |

Without recordings: pouring (`pour`: air in the glass rises in pitch as it fills, bubbles), stirring (`stir`: a clink per spoon rotation), writing (`write`: quill scratching in strokes, dipped once in ink), drawer, and sitting.

**Cavalry, flight, marching, and teleportation (`sfx/mounts.py`: `hoof`, `horse`, `wings`, `march`, `warp`).** Measured from *Triangle Strategy*, *FFTA2*, and *Tactics Ogre: Reborn* effects (user's copies) and a CC0 pack; analysis only:

| Measurement | Description | Event |
|---|---|---|
| hooves | each step is a hoof pair ~68 ms apart (front or rear legs), ~0.21 s; grass: muffled thump, strongest at 125–250 Hz; stone: hollow impact at 0.5–1 kHz (center ~0.9 kHz), horseshoe up to 8 kHz; shallow water: splash with body at 250 Hz–1 kHz | `hoof` step; grass, stone, and water within ±5 dB of TS per octave up to 8 kHz |
| charge | ~1.8 s air swelling for ~0.7 s, center near 2 kHz | `horse` charge (quiet hooves underneath) |
| charge impact | low thump (125 Hz–1 kHz, ~0.4 s) followed by ~1.5 s bright dust (8 kHz) | `horse` trample |
| pain neigh | ~1.6 s: ~1 s high and steady (f0 ~550 Hz, energy near 2 kHz), then low breath (~250 Hz) | `horse` hurt |
| snort | ~1 s unvoiced breath, strongest near 1 kHz | `horse` snort |
| wings | one beat lasts ~0.4 s, strongest at 250–500 Hz, feathers up to ~13 kHz, often two hits ~0.1 s apart; a bird taking off beats ~10 times in 1.6 s, brighter (center ~2 kHz) | `wings` flap, takeoff |
| teleportation | disappear: ~1.2 s, swelling for ~0.8 s and rising ~15 semitones; appear: ~1 s, falling ~17; *Tactics Ogre* version lasts ~0.4 s, dark (strongest at 125 Hz) | `warp` arcane, retro |

Without recordings: gaits (walk in four equal beats, trot in two, canter in three plus suspension, gallop in four quick beats then all feet airborne), normal neigh, quiet nicker, wing landing and hovering, troop marching. Gaits, hovering, and marching are seamless loops: each loop's last hoof/wingbeat/step dies before the wrap point, so no crossfade is needed.

**Story locations (`sfx/places.py`, `ambience` styles: battlefield, camp, castle, town, tavern, dinner, plains, desert, snow, swamp, ruins, deck).** Measured from *Triangle Strategy* ambience loops and *Tactics Ogre: Reborn* weather (user's copies); analysis only. Octave bands relative to the strongest:

| Measurement | Description | Style |
|---|---|---|
| distant battle | strongest at 0.5–1 kHz, -6 dB at 2 kHz, -16 at 4k, -21 at 8k; level varies ~11 dB | `battlefield`: shouting army (higher, more open voices), steel and shields, feet, war drums; within ±7 dB of TS |
| people talking | (bar, soldiers, five people) strongest at 500 Hz, -3 to -5 dB at 1 kHz, -8 to -13 at 2k, -16 to -22 at 4k | `tavern`, `town`, `camp`: within ±5 dB of TS |
| dinner | bright: strongest at 4 kHz (cutlery, ~2 per second), conversation 15–20 dB below | `dinner` |
| plains | wind and birds: 250 Hz to 8 kHz within ~6 dB, level varies ~15 dB | `plains`: within ±4 dB of TS |
| ship at dock | waves strongest at 500 Hz, seagulls near 1 kHz | `deck` |
| campfire | low roar (63–125 Hz), crackles ~12 dB lower, flat above 500 Hz | `camp` campfire, `tavern` fireplace |

Crowds use wordless voices: each person's phrase is one syllable, the mouth opening and closing 4–6 times per second as the vowel changes, pitch rising slightly then falling at the end (some ask questions); a busy tavern uses about 70 layers. Locations reuse existing sounds: measured fire, wind, and sea, bestiary crickets and frogs, hooves, horse snort, ship bell, wood creaks. Without recordings: desert (warm wind, sand hissing in gusts), snow (wind howling through rocks), swamp (frogs, bullfrogs, bubbling mud, mosquitoes), and ruins (wind singing through broken stone, drops, little bells).

**World (`lever`, `trap`, `torch`, `water`, in `sfx/world.py`): measured from recordings.**

- **Lever:** ratchet clicks every 40–70 ms for 0.3–0.5 s, midrange (0.5–3 kHz, mechanism modes ~330–1000 Hz), ending in a thump. Pulling triggers a mechanism rumble somewhere.
- **Torch:** lights with a scrape and flare turning into crackles (broad, 1–6 kHz, ~1 s). Extinguishing is a hiss.
- **Water:** splashes are high (strongest at 2.5–8 kHz, 0.2–1 s), with a low plop and drops. Diving has rising bubbles afterward.
- **Spike trap:** emerges with a metallic "shing" (5–8 kHz modes) over the mechanism. Darts are short arrow flights hitting a wall; blade traps are slow, heavy swings.
- **Pressure plate:** stone sinks and a catch releases.

**Ambience (`ambience`): compared with real recordings** (ESC-50, 8 clips per location, analysis only). We compare octave spectra, slow and fast volume variation, events per second, and crest factor. The first version's loops had these errors:

- **Rain:** missing low/mid hiss of water hitting surfaces (250–1000 Hz was 8–16 dB too low).
- **Wind:** too high, centered on a 1 kHz whistle. Recorded wind is mostly low (strongest at 250 Hz, −20 dB at 4 kHz).
- **Fire:** missing low rumble (63–125 Hz). Crackles were too numerous and weak; now fewer and stronger, with crest factor rising from 19.5 to 27 dB (real: 28).
- **Cave:** low rumble ~20 dB too loud, too few drops (1.4 per second; real: 3.8).
- **Night:** missing high insects (8–12.5 kHz).
- **Storm:** gained low rolling thunder under rain. Real clips are almost all thunder; our loop remains rain with thunder.
- **Wind (rebuilt without CLAP search):** CC0 wind recordings have body strongest near 250 Hz, gusts every 3–10 s rising 4–11 dB, and a light whistle (3–9 dB above the spectrum). The CLAP guided version had a narrow whistle and barely varied (1–2 dB). Gusts now rise and recede, with whistle pitch following gust strength.
- **Thunder (`magic.thunder`, rebuilt from recordings):** rumble strongest near 250 Hz (−12 dB at 1 kHz, −25 at 2 kHz), lasting 2.5–5 s and rolling, with a new burst every ~0.3 s, 6–12 dB above background. Nearby lightning first tears with dry cracks. The previous version removed cracks because CLAP heard fire, and rolled only 4 times.

Sea and forest were already close. CC0 Freesound samples (analysis only) also informed rebuilds of:

- **Stream:** broad at 0.5–8 kHz (strongest at 1–4 kHz), little bass, prominent bubbles above hiss (crest ~21 dB).
- **Dungeon:** breathing background, level rising and falling 3–8 dB.
- **Owl:** five nearly pure hoots (great horned owl, 340–400 Hz): two short, three long.
- **Small birds:** instead of a creature voice, phrases of 3–8 elements at 2–7 kHz: whistles, octave sweeps in 20–60 ms, and trills. Each species has its register.
- **Cave drops:** 0.75–5.4 kHz, ringing for 10–35 ms.
- **Chains:** small links jingling 3–15 times per second, strongest at 8–12.5 kHz. Previously low iron.
- **Campfire accent:** CC0 campfires feature a sap pocket popping: 20–140 ms, strongest at 2–12 kHz (−8 to −14 dB at 0.5–1 kHz), 20–30 dB above background, sometimes with sparks. The old "settling log" lasted 1.5 s and peaked at 1–2 kHz. The event is now a crack; ~30% of the time a shifting log adds a low knock.
- **Night crickets:** checked against ESC-50. Carriers at 3–10 kHz, pulses at 8–62 Hz, trills 2–4 times per second; ours (4.2–4.8 kHz, ~35 Hz, ~3 per second) were already in range.

**Explosions (`explosion`): compared with recordings.**

- **Nearby:** strongest at 63–250 Hz (−9 dB at 1 kHz, −14 at 4 kHz). Rise for ~0.1 s and fall 20 dB in ~0.8 s. The first version had a 125–250 Hz hole and too much roar near 1 kHz; it gained low body and an initial rise.
- **Distant:** almost entirely the lowest rumble (strongest at 31 Hz, −34 dB at 2 kHz).
- **Debris (rebuilt without CLAP):** in CC0 rockfalls, falling stones last 3–10 s, with 5–19 impacts per second, dense initially and thinning without stopping abruptly. Large stones hit low (63–250 Hz). The old version was a short crackle cloud; now 14–24 randomly sized stones each have a thump, over gravel rain (12–15 impacts/s measured).

**Spells (`spell`): compared with game magic effects** (there are no real magic recordings, so sounds designed by others are the benchmark).

- **Fire:** the reference fireball is mostly low (centroid ~280 Hz). Ours was upper midrange hiss; it gained low roar leaving the hand and on impact.
  In flight, CC0 flame loops are strongest at 63 Hz (−20 to −30 dB at 1–4 kHz). Ours peaked at 500 Hz; now low rumble with crackling above.
- **Ice:** previously only highs. Casting gained midrange body (frost forming); impact gained the block's thump, with fewer high shards.
- **Lightning:** impact was only low thunder (centroid ~100 Hz). Lightning now strikes first, with bright crack and crackling, then thunder rolls.
- **Healing:** bells had low rumble beneath (the bell's hum note). Now glass chimes over a quiet choir.
- **Arcane:** pitch fell to 40–55 Hz, leaving a midrange hole where generic magic concentrates energy. It now ends higher, alongside a shimmering chord.
- **Holy (rebuilt without CLAP):** in CC0 angelic fanfares, pure voices enter one at a time up a major chord (C, E, G, C), 0.3–0.5 s apart. The newest note leads; the chord holds for 2.5–3.5 s, with −17 to −19 dB at 2 kHz. Sparkles are a cluster of small bells at 2–3 kHz struck repeatedly. The old version lasted 1 s and had a bell's low hum; casting now climbs the chord, impact plays the full chord with higher voices rising above, and little bells shimmer on top.
- **Shadow (rebuilt without CLAP):** CC0 dark magic concentrates energy at 250–500 Hz (63 Hz at −27 dB), with a voice jumping between diminished chord notes (root, minor third, tritone) about 10 times per second. Echo blends them into a beating cluster. The old version was almost all sub-bass (strongest at 63 Hz, hole at 125–250 Hz).
- **Nature (rebuilt without CLAP):** no recorded nature magic exists, so real recordings of what it moves are the benchmark:
  - rustling foliage: strongest at 2–8 kHz, −9 to −14 dB at 125–500 Hz;
  - creaking trees: ~90 Hz friction through wood resonances at 0.8–1.8 kHz;
  - uprooted roots: earthy rumble at 63–250 Hz.

  The old version had water bubbles and a croak; now foliage in gusts, creaking trunks, and earth splitting on impact.
- **Charge and travel:** open charge-up recordings (32 "charge up" sounds, risers) vary too much to be a benchmark. Some grow to the end, others peak midway and fade, and brightness shifts −3 to +5 octaves. Our charges fit that range and were kept. Magic projectile loops also vary widely; only fire had a clear error.

**Footsteps (`footstep`): measured from walking recordings.** Each step was cut from sequences; each surface uses the median of 16–46 steps.

- **Stone:** low/mid tap (strongest at 250–500 Hz) with hard sole click; −20 dB in ~33 ms.
- **Wood:** lower and longer (strongest at 250 Hz, −20 dB in ~51 ms). Heel and toe ~60 ms apart, sometimes floor creak.
- **Gravel:** almost no bass (−21 dB below 300 Hz), crunch strongest at 1–1.6 kHz, ~150 ms of grains.
- **Grass:** high rustle centered near 8 kHz, ~0.35 s, with a soft low thump.
- **Snow:** strong low thump (250 Hz) beneath squeaky crunch at 1–2.5 kHz.
- **Metal** (plates and stairs, usually damped): low, ringing, strongest below 300 Hz.
- **Dirt:** low/mid, short (−20 dB in ~24 ms), fine grains.
- **Water:** no bass; splashes strongest at 2.5–5 kHz.

Layers (thump, sole contact, click, floor, grains, rustle, splashes) are shared across surfaces. Gains were adjusted by rendering and comparing until each surface's median spectrum matched recordings (±5 dB per third-octave band). The previous CLAP guided version was too high (+8 to +20 dB above 2 kHz) and three to six times longer. Quiet rolling sole friction keeps highs alive longer, as in recordings.

Even with matching spectra, the CLAP judge still does not recognize our footsteps: it hears "bouncing ball" and "stick hitting wood". Adding room or reverb did not change that. It recognizes real recordings (6 of 8).

**First version calibration (history).** Initial effects were designed with the CLAP optimizer and checked with the judge. CLAP has since left the effects process: effects are now measured and imitated from real recordings and open samples, then judged by ear. The following records the first version; CLAP guided parts (wind, thunder, footsteps) have already been rebuilt.

- **Label set:** about 80 descriptions (effects, locations, distractors such as speech, music, "8-bit").
- **Ceiling:** real ESC-50 recordings (8 per category, analysis only, CC BY-NC) show what CLAP recognizes with these labels: footsteps 6/8 first, breaking glass 8/8, campfire 8/8, rain 6/8, thunder first or second.
- **Spectrogram comparison with real sounds:**
  - real breaking glass is a broadband noise burst, not pure tones (previously sounded like little bells);
  - real thunder is a long rumble up to ~1 kHz; adding a crack or crackle makes it sound like fire;
  - campfire needs dense crackles.
- **Footsteps:** CLAP guided search found the first structure for each surface. It was replaced by recording measurements (see "Footsteps").

**Judge results** (2 identities per style, 80 labels; chance ~1% for first place):

| Family | First | Top 3 | Strengths | Weaknesses |
|---|---|---|---|---|
| magic | 50% | 80% | charge, cast, travel for most elements; fire, arcane, shadow impact | lightning impact, arcane travel |
| weapons, bow, explosions | 29% | 45% | flesh/wood hits, swings, arrows, distant explosion | sword clash ("sword hitting armor"), sword draw/drop, mace on metal/stone, bow release |
| ambience | ~30% | ~40% | rain, cave, night, storm, sea loops first | almost all occasional events |
| footsteps | 0% | 0% | — | all |

Loops last 16 s, and CLAP randomly crops audio longer than 10 s, so ambience numbers vary slightly between runs.

**Lessons from CLAP guided search:**

- **When the judge confirms, adopt:** bow creak (22nd → 6th–9th in the judge) and wind (9th–10th → 3rd–4th).
- **When the optimizer likes it but the judge does not, discard.** Sword clash and drop searches reached 2nd–5th with the optimizer, but remained 20th–40th with the judge. The models disagree on metallic impacts, which they distinguish poorly ("swords clashing" versus "sword hitting armor").
- **Footsteps:** walking sequence search brought gravel to first in the optimizer but 8th–10th in the judge; stone, wood, and grass did not reach the top 10. The structure found is in `physical.STEPS`. Our footsteps still sound like impacts ("bouncing ball", "arrow in wood").

## Music and composition

**Japanese music (`music_japan.py`), benchmarked against the most praised *Utawarerumono* tracks** (user's copies; numbers only, no melodies):

| Measurement | In *Utawarerumono* | In our cues |
|---|---|---|
| tempo | 63–162 bpm, depending on mood | `shrine` 66–80, `village` 88–112, `festival` 118–144, `kagura` 126–160, `elegy` 60–76 |
| pulse | sacred pieces nearly pulseless (0.09–0.29); everyday life and festivals marking time (0.81–0.85); laments 0.34–0.46; battles 0.54–0.77 ("Ikusa Kagura": 0.60) | `shrine` 0.11–0.12; `village` 0.70–0.82; `festival` 0.80–0.84; `elegy` 0.34–0.46; `kagura` 0.60–0.69. Melody sits a step behind rhythm: with shakuhachi leading, its vibrato blurred `village`'s pulse (0.42) |
| timbre | warm: spectral center 260–650 Hz because bass is strong (63–250 Hz within 9 dB of the strongest band); laments 386–612; battles ~500 | `village` 424–498, `elegy` 481–624 (long flute shakuhachi, 2.4, down to A2), `kagura` 506–589, `festival` 539–618, `shrine` 655–716 |
| dynamics | even: 1.6–8 dB between loud and soft; laments 7.6–13 | 1.5–5.4 dB; `elegy` 9–12.6 (intimate koto half; strings swell when shakuhachi enters) |

The musical language: in (miyako-bushi: 0 1 5 7 8, solemn koto scale, semitone falling to tonic), yo (0 2 5 7 9, folk songs), and ryukyu (0 4 5 7 11, southern islands); *ma*, space: each phrase ends with a long note and a breath; heterophony: koto doubles the shakuhachi melody, plucked, ornamented, and an octave lower, rather than harmonizing; orchestra beneath in open fifths and fourths, without thirds.

**Tactical RPG music (`music_tactics.py`), measured from *FFTA2*'s 37 music sequences** (user's copy; DS music is a score, so notes can be read). Numbers only, no melodies:

| Measurement | In FFTA2 | In our cues |
|---|---|---|
| tempo | battles 125–170 bpm; slow scenes 50–80; map 100–150 | `skirmish` 136–162, `boss` 152–174, `tense` 104–122, `final` 120–140; `sorrow` 56–68, `intrigue` 72–88; `worldmap` 104–124 |
| mode | battles in Dorian, harmonic minor, Phrygian, Mixolydian, or minor (almost never plain major); slow scenes in minor, Phrygian, harmonic minor, or Lydian; travel in Lydian and Mixolydian | same, selected by seed |
| density | up to 16 tracks, 6–17 notes per beat | battles 6–10.5; scenes 2–6 |
| bass | very low: average between B0 and A2 (MIDI 30–45) | 35–45 |
| melody | moves stepwise but leaps (fourth or more) in 10–30% of notes, over half in darker tracks | `skirmish` ~25%, `boss` ~42%, `final` ~19% |
| loops | long: 60–270 beats | 64–128 beats |

Style ingredients: sixteenth-note string ostinato on root, fifth, octave, and modal note (minor sixth in Aeolian/Phrygian, major sixth in Dorian); marching snare figures with rolls swelling into each phrase; timpani and very low bass; horns holding harmony; theme in brass, then flute. Boss music adds choir chords and semitone-descending bass; final battle rises a whole tone in the second half.

**`Score`.**

- Each track is a `Voice`: its notes are spec layers rendered together without echo.
- `Score` positions each track and finished sound in stereo with constant power panning (center −3 dB per channel).
- A portion of each (`send`) feeds a shared room: two decorrelated noise tails, one per ear, darkened above 5 kHz, with unit energy and 12 ms silence before first reflections.
- `render(loop=...)` cuts at exact length and wraps anything beyond it (notes and room tail) to the beginning: a seamless loop.

**Instruments: measured from isolated VSCO-2 CE notes** (CC0, analysis only). For each recorded note:

- partials as ratios to the note, with level and T60 (fitting dB decay from peak to −30 dB);
- time to −20 and −40 dB.

For sustained instruments:

- first 8 harmonics in the steady portion;
- vibrato rate and depth;
- attack time.

Our sound is measured the same way.

*Bars and bells (`Modal`).* Each received only the measured modes.

- **Glockenspiel:** free bar 1 : 2.9 : 5.5 : 9.0 (theoretical ratios 1 : 2.76 : 5.40 : 8.93). Rings 9 s at G5 and ~2 s at C8; partials die within 1 s. The old version (`ui.chime`) rang only ~1 s.
- **Marimba:** tuned 1 : 4 : 10. Rings 8.6 s at C3 and 0.5 s at C7. The tenth partial dominates low-note attacks; yarn mallet cuts above ~2 kHz.
- **Xylophone:** 1 : 3.
- **Tubular bells:** beam modes (1.22 : 2 : 2.93 : 4.06 : 5.31…). Perceived pitch is an octave below modes 4–6, which stand at 2 : 3 : 4.

To start each mode exactly at its gain, contact shorter than 3 samples became an ideal impulse (`Modal.hits`).

*Plucked strings.* Harmonic partials with double decay: a fast component and a residual sound 14 dB lower (the string's other vibration plane), keeping the lows ringing.

- **Harp:** 1/√h, losing highs above ~500 Hz. Fundamental rings 15 s at A2 and ~1.5 s at A6.
- **Guitar:** nearly equal harmonics through the tenth, with notches from finger position; −20 dB in ~0.3 s.
- **Lute:** string pairs (courses) detuned by 2–4 cents.

*Percussion*, measured and synthesized results:

| Instrument | Recorded | Ours |
|---|---|---|
| timpani: tuned mode with 1.5, 1.98, and 2.44 above | −20 dB in 0.17–0.22 s | 0.10–0.26 s |
| hand drums | −20 dB in 0.15–0.27 s | 0.16–0.18 s |
| concert bass drum | 63–125 Hz, −20 dB in ~0.09 s | 0.105 s |
| snare with wires | peak at 250 Hz, flat to 4 kHz, −20 dB in 65–75 ms | 85 ms |
| cymbal | 2–8 kHz, −20 dB in 0.5–0.6 s, −40 in ~2 s | 0.6 s and 1.7 s |
| tambourine | 4–12 kHz, −20 dB in 0.2–0.27 s | 0.2 s |

*Sustained instruments.* A glottal source passes through body resonances. Resonances were fitted by analysis through synthesis so the first 8 harmonics match recordings across the range. Physical limits: 150–8000 Hz, bandwidth ≥ 150 Hz, gain ≤ 3. Without limits, the optimizer invented 25 Hz resonances fitting only measured notes. Mean error per harmonic:

| Instrument | Error | Other measurements |
|---|---|---|
| violins | 1.8 dB | 3 voices at ±8 cents, each with its own vibrato (~5 Hz) |
| cellos | 3.8 dB | |
| flute | 5.2 dB | nearly pure high notes, rich low notes, 5 Hz vibrato ±7 cents |
| horn | 6.3 dB | |
| soft trumpet | 2.8 dB | |
| loud trumpet | 4.3 dB | |

Trumpet brightness follows intensity, interpolating between the two fits: resonance near 670 Hz when soft, opening to 1.2 and 2 kHz when loud.

To avoid filtering block by block, fixed resonances (stationary mouth) use one filter per formant.

*Japanese instruments.* Measured from đàn tranh and percussion in VCSL (Versilian Community Sample Library, CC0, VSCO-2's sister library), Wikimedia Commons recordings (koto: CC BY and CC BY-SA; shakuhachi: "Shika no Tōne", Araki Kodō III, public domain), and Freesound (modern shakuhachi: synthtodd, CC0; UncleSigmund, CC BY 4.0); analysis only.

| Measurement | Description | Instrument |
|---|---|---|
| đàn tranh, Vietnamese zither related to koto (48 notes, B2–B5) | low: weak fundamental, harmonics 2–4 up to 10 dB higher; middle/high: fundamental dominates; −20 dB in 0.3–0.9 s, faster and brighter with force; left-hand vibrato (*yuri*) at 6.4–7.1 Hz, 20–63 cents (28 at mf, 39 at ff), beginning ~0.15 s later | `koto` body and *yuri* |
| real koto (2 recordings) | harmonics 2–6 stronger than fundamental (+6 to +10 dB: played near bridge), −20 dB in 0.52–0.58 s (silk and tetron decay faster than steel), 7–19% of notes rise after attack (*oshide*) | `koto` within ~3 dB per harmonic, falls −20 dB in 0.46 s |
| shakuhachi ("Shika no Tōne") | long notes (2.6–3.5 s, up to 11 s), entering from below (~15 cents; sometimes 2.5–5.6 semitones), leaving upward (~25 cents, sometimes 2.7 semitones), slow vibrato (5.8 Hz, ~16 cents) entering late | `shakuhachi` gestures plus *muraiki* (breath at attack) |
| modern shakuhachi (2 recordings; the 1930 recording is a 78 rpm disc hiding frequencies above 2–3 kHz) | rich lows (at ~260 Hz, middle C, second/third harmonics only 6–8 dB below first); nearly sinusoidal highs (second at −16..−18 dB, third at −21..−26, fourth another 12–15 dB down); breath 25–33 dB below tone between harmonics | additive `shakuhachi` timbre: 8 measured harmonics, each a sine on the same pitch curve (locked together) with its own tremor, plus breath; within ~2 dB per harmonic (old second harmonic at −3 dB: 13 dB too strong, the "synthetic" quality) |
| bass drum (VCSL) | membrane modes: 59, 62, 75, 86, 108 Hz, ringing ~2 s | `taiko` modes, with wooden sticks (*bachi*) |
| woodblock (VCSL) | clusters at 1.27–1.46 kHz and 2.7–3.5 kHz, T60 0.3–0.6 s, −20 dB in 0.07–0.1 s | `hyoshigi` |
| Nepalese handbells (VCSL) | modes at 1 : 2.7 : 3.84 : 4.87, ringing 1–3 s | `rin` (longer, like a bowl, with slow beating) |

*Oshide* and *yuri* require pitch to change after the strike: a `Modal` body accepts a `bend` curve (semitones over the note). The ring is read faster or slower like tape, all modes rising together as in a string under changing tension; the C++ core uses the same calculation. A spec requests version 7 only when a note bends; others remain version 6, which an older core (an old Godot extension copy in a game) can still play.

*Battle voices.* 420 lines from the three games (user's copies), transcribed once by a Japanese speech recognizer solely to group them by content: wordless shouts (*kiai*: "ha!", "nuryaa!", "dee!"), strikes ("todome!", "ochiro!"), pain, victory, defeat. Lines containing names (such as the mount "Kokopo"), forms of address, or conversation are excluded to avoid measuring names in place of intonation. No text or audio is kept, only numbers:

| Measurement | Shout (*kiai*, 82) | Pain (11) |
|---|---|---|
| duration | 0.48 s (0.22–1.26) | 0.59 s |
| rise to peak / decay | 125 ms / 190 ms | 80 ms / 160 ms |
| voiced | ~23% of shout (rest is air and roughness) | ~25% |
| pitch | ~440 Hz, peak near 60% of shout | ~420 Hz, ending below starting pitch |
| brightness (1–4 kHz versus lows) | −1.9 dB | −7.3 dB |

Hence `emote`'s `kiai` style: shouts use the character performer's longest takes (~0.33 s; `grunt`, 0.26), without stretching beyond ~1.1×, because stretched voices sound robotic; pain is darker (−8 dB) and breathier. Also, corrections and findings applying across styles:

- **One voice per character.** Each take previously chose its cheapest template independently, so a hero alternated between the adventurer and men from the shouting pack. Characters now keep the performer requiring the least shift to their voice, falling back only when that performer lacks the sound.
- **Cycle tremor, tried and removed.** Random period variation of 12 cents brought fine pitch fluctuation to 7.5 cents (game shouts: 7.1), but a blind test (round "tremor-do-ciclo": 4 natural lines and 4 shouts, with/without) gave identical ratings in all 8 groups. Removed.
- **Hoarseness and voice doubling (`rough`, `sub`), now in natural speech and shouts too.** The vocoder randomly, deterministically offsets each period and pulse (`rough` 1: ~45 cents and ~1.7 dB), and weakens/advances alternate pulses (`sub`: a creature voice doubled an octave below); the C++ core does the same. Scale came from listening (round "rouquidao"): speech deviations up to ~40 cents still sound natural, above ~50 break the voice, so `rough` reaches the edge; high `sub` (0.75–1) sounds hoarse, worn, and shouted; together in the `monster` preset they sound monstrous in natural speech, where formant speech sounded broken.
- **Shouts can play the recording itself, like tape** (opt-in: `tools/build_barks.py --download DIR --audio` stores the recordings locally and `TARE_TOOLS_TUNE_TAPE=1` turns it on; the package ships only the numbers and the native core never plays tape, so by default every shout is the vocoder's and a recipe sounds the same in Python and in the game). In listening tests, CC0 recordings shifted as tape (faster/higher or slower/lower) sounded like themselves (roboticness 2.5/5, tied), while the vocoder did not (3.4); PSOLA (2.9) left a bright square in the spectrogram where the defect was heard: energy below the fundamental (+15–20 dB versus tape, peaking precisely in marked regions). Tape beat the vocoder in 10 of 12 pairs shifting formants up to 40% (about 5 semitones), so it applies within that range and up to 25% duration change (styles fitting shouts to a duration, such as `gasp`, stay on the vocoder, as do whispers, rough, and doubled voices). Recordings stored at 24 kHz sounded identical to 48 kHz (4 pairs).
- **Measured but inaudible.** The vocoder also adds breath below the fundamental (median 4 dB above recordings): rolling air off at 24 dB/octave there improves the measurement, but a blind test (3 lines, 3 shouts) found no audible difference, so it was excluded. Also identical by ear: `monster` with 22 or 40 cents of roughness.
- **Natural voice listening review** (round "voz-natural", 16 blind pairs; accent from 1 = Brazilian to 5 = foreign: 3.9 before, 2.75 after, none worse): word-final r before a vowel becomes a tap and links to it ("por este" sounded like "por heste"); bank selection substitutes open/closed vowels (e/é, o/ó) or the nasal i in "-ões" with n only as a last resort (cost 1.5, previously 0.3 and 0.6: "novo" came from "nove", "poções" from "monstro"); yes/no questions rise to +8 and stay high, "o que" questions rise slightly at the end, exclamations peak on stress and fall; comma pause is 0.08 s (previously 0.18), without rushing clauses or lists.

*Remaining vocoder hiss, judged by ear* (round "O chiado do vocoder", `tools/curate.py`; roboticness 1 = natural to 5 = robot). Four real kiai reconstructed: originals scored 1–2; full WORLD, the technique at its best, 1–3 (3 for three of four); our vocoder with current templates (32 envelope bands, 5 air bands), 2–5, and with 64/16 bands, 2–4, nearly the same. Template resolution is not the problem: roboticness comes from analyzing and reconstructing voice as pulses and noise; shouts (rough voice, irregular cycles) are a weak case for this technique. Three changes bringing measurements closer to real shouts also made no audible difference in ours: squared aperiodicity (as WORLD uses it), air blown at each glottal opening, and phase-spread highs. They were excluded.

The original Portuguese round names and pronunciation examples above identify the listening evidence and language-specific issues.

**Composition (`Cue`).**

- Seed chooses key (G3 to F♯4), mode, progression (I–IV–V–I, i–VI–VII–i…), rhythms, and motif.
- Melody follows simple rules:
  - chord tones on strong beats, near the previous note without repeating;
  - steps on weak beats, rising at phrase start and falling at the end, bouncing at range boundaries;
  - opening rhythm returns every two measures;
  - each 4-measure phrase ends with a long note, the last on tonic;
  - over the dominant in minor, the seventh rises (harmonic minor).
- Accompaniment chords use minimum voice movement.
- Arrangement uses roles (melody, brass, strings, harp, bass, timpani, snare…). Style maps each role to a measured instrument or console channel (pulse waves with `crush`, sine bass, noise).
- Jingles let the final chord ring 3 s and fade in 1.5 s; loops have exact measure lengths.

**Band (measured from CC0 Freesound notes).**

- **Electric bass:** first two harmonics equal, third weak (−17 to −34 dB, finger near its node), fourth strong again. Rings long (−20 dB in 1.6–3 s), damped by the hand when the note ends: `Modal.damp` drops 60 dB in 0.1 s.
- **Electric piano:** first and second harmonics close (−2 and 0 dB), third 10–12 dB lower, tine "bell" near eighth. Harder playing raises upper harmonics.
- **Hi-hat:** closed, drops 20 dB in 65–130 ms; open, ~0.5 s; strongest at 4–12 kHz.

**Color harmony (music in the style of 16-bit soundtracks).** The idea came from a *Chrono Trigger* analysis ("Nonfunctional Harmony in Chrono Trigger", 8-bit Music Theory): chords chosen for color rather than function.

- Palettes play one chord per measure, none relying on V → I:
  - I–II maj9 (raised fourth, Lydian);
  - chromatic mediants (I–♭VI–♭III);
  - maj9 descending a semitone to i m9;
  - i–♭VII–♭VI–v (Aeolian, no dominant);
  - i m9–IV9 (Dorian);
  - I–♭VII–IV (Mixolydian);
  - I–♭VI–♭VII–I (heroic);
  - i–♭II–i–♭VII (chromatic, battle).
- **Open voicing:** root in bass, third and seventh near middle C, fifth and extensions above, all shifted by octaves to remain close to the previous chord. With `planed`, the same shape slides in parallel to the new root.
- **Melody:**
  - each 8-measure phrase arcs up to the middle and settles at the end;
  - strong beats use chord tones or color notes (ninth, eleventh, thirteenth); weak beats use scale steps, never a semitone above a chord tone;
  - measures 2–3 repeat the motif in sequence, moved with harmony, or a whole tone up if the chord stays;
  - measure 6 brings the motif back, and 7 rests on a color note.
- **16-bit sound (`snes`):** small room, highs darkened above 9 kHz, console echo. Repetitions every ~210 ms lose 45% and darken with each return, alternating ears (`Score(echo=...)`, per-track send).
- Compositions are original: they use techniques, not the game's melodies.

## CLAP calibration

`clap.py` loads two CLAP models through `transformers`: the **optimizer** (`laion/clap-htsat-unfused`) and **judge** (`laion/larger_clap_general`), excluded from all optimization. `LABELS` maps 22 English descriptions ("a cat meowing", "a monster growling", "an 8-bit video game sound effect"...) to archetypes expected to match them.

**Search** (`designer.py`). Archetype genes are discovered by running design with a spy `Genome` (12 species × 3 traits × all calls). Search is a (1+1) evolutionary strategy with the 1/5 rule over genes, size, and aggression:

- `design(prompt)`: maximizes CLAP similarity to text. First evaluates `screen` candidates per archetype, then refines the best 2.
- `match(sample)`: CLAP recording similarity minus `feature_weight ×` the `analysis.features` distance. Measurements: pitch (YIN with octave/fifth correction), loudness envelope, long-term spectrum, duration, aperiodicity, voiced fraction, segment count.
- Found genes become fixed species genes (`genes`). Fixing a gene changes its base, preserving individual and take variation.

**Judge results** (120 sounds: per archetype, 2 species outside calibration × 3 sizes × 2 calls):

- **Archetype accuracy:** 32% (chance ~10%). `chip` 100%, `reptile` 58%, `slime` 50%; mammal, bird, insect, and robot below 10%.
- **"8-bit video game sound":** 56% of non-chip sounds get this label. The goal was therefore to sound less synthetic.
- **Realism layer** (`lowpass`, `room`, `air`, `shimmer` + more jitter and breath), fitted by the optimizer in 70 iterations: calibration accuracy rose from 30% to 45%. With the judge, "8-bit" fell from 56% to 46%, but accuracy stayed at 32% and mean probability of the correct label fell 0.33 → 0.30. Insect, monster, reptile, and robot improved; slime, spirit, and amphibian worsened.
- **Decision:** layer remains available (`REALISM_CLAP`) but off by default. For the judge, recognition problems lie in archetype design rather than missing recording texture.

## Two ways to use it

**Offline (assets).** `tare.tools.tune bake bestiary.json -o output` generates:

```
output/manifest.json
output/<creature>/<call>_<take>.wav   (+ .json with the spec)
```

```json
{"format": "tare.tools.tune.bake", "version": 1, "sample_rate": 48000, "takes": 3,
 "calls": ["idle", "alert", "attack", "hurt", "death"],
 "creatures": {"wolf": {"creature": {"archetype": "mammal", "species": 2183285651, "size": 0.45, ...},
                        "calls": {"hurt": [{"file": "wolf/hurt_00.wav", "duration": 1.1447,
                                            "peak": 0.6989, "spec": "wolf/hurt_00.json"}, ...]}}}}
```

In the engine, each call becomes a random container (FMOD/Wwise) or an array of clips selected randomly without repeating the last.

**Runtime.** Three levels, from simplest to most procedural:

1. **Python game:** `VoiceBank` generates on demand with cache and threads. Use `warm()` during loading.
2. **Native engine playing specs:** design stays in Python (small specs ship with the game), while the engine runs only `render`, already implemented in C++ (native core below).
3. **100% procedural native engine:** also port `rng`, `genome`, `calls`, and archetypes, all arithmetic. The game then invents creatures in real time (procedural spawning, mutations, evolutions), using the same spec Python would generate.

### Native core (`native/`, `tools/build_native.py`)

A C++17 renderer for engines that do not run Python (Godot first). Python designs sound as a JSON spec (effect recipe, creature call, planned speech: text → phonemes → melody → bank pieces); the core turns it into audio matching `render.render`. Design stays in Python, where most tuning happens (measurements, question melodies, voicing); porting now would double each adjustment. DSP rarely changes, so it is the part moved to C++.

- C interface (`native/include/tare_tune.h`), no file access: spec text and banks in, audio out. Reading files is the wrapper's responsibility (GDExtension, tests).
- `tt_render_voice(json, knobs, banks, names, n, rate)` renders a complete spec (`voice.cpp`): syllables, struck bodies (`Modal`), noise bands, scattered events (`Scatter`), natural speech (`Spoken`, through supplied banks), and all finishing: 40 Hz highpass, crush, drive, `lowpass`, `room`, `air`, `space` (FFT convolution), seamless loop, −1 dBFS peak. Still pending: chip programs (Generation 1 and `chip` archetype), formant speech (`speech`), and vocalizations (`vocoded`, needing templates in an engine format); code 4 and `tt_last_error()` identify unsupported layers. `tt_render_spoken` reproduces one `Spoken` layer alone.
- Scipy filters are recreated using the same formulas: `butter` goes from prototype through bilinear transformation in poles/zeros (`lp2lp`, `lp2hp`, `lp2bp`), and `lfilter`/`sosfilt` follow the same operation order. JSON uses a minimal reader (`json.hpp`); numbers pass through `from_chars`, returning exactly the float Python wrote, independent of machine locale.
- FFT uses pocketfft (BSD-3), as numpy does; randomness is SplitMix64 + FNV-1a (`rng.hpp`), matching `rng.py`. Constants (envelope and breath bands, window removing DC from each pulse) are emitted by Python in exact hexadecimal to `native/src/tables.hpp` (`build_native.py tables`; a test checks they still match Python within 10⁻¹², since numpy may vary in the last bit across processors).
- `tests/test_native.py` loads the library with ctypes and compares against Python: random keys, each speech layer (two voices, 48 and 22.05 kHz), a whole voice, every recipe event, creatures, and music tracks. Outside the test, all 316 effects (every style × event), 50 creature × call combinations, and tracks from all music were compared: largest sample difference 6·10⁻⁸ (peak 1), one output float32 step. Generates 1 s of speech in ~44 ms (numpy ~75). Short effects are ~5× faster in C++; long notes (60 s tracks) tie because time goes into per-sample sines and powers, vectorized by numpy.
- On Windows with Smart App Control enabled, unsigned compilers (MinGW) cannot run; build and test the core in WSL (Linux) or with Visual Studio build tools.

**Engine banks (`.tvb`, `speech/tvb.py`).** `.npz` is a ZIP of numpy arrays, awkward outside Python. `tvb.export("pt/alex", path)` writes `TVB1`, JSON header length (name, tract, frames, bands, sections), header, and three zlib-compressed sections (Godot opens them with `PackedByteArray.decompress(..., COMPRESSION_DEFLATE)`): pitch (float32), envelope (uint8, each frame a delta from the previous, as in `.npz`), aperiodicity (uint8). ~20.7 MB per voice; frames only, no labels (planning stays in Python).

**Godot (`native/godot`).** A GDExtension over the core, using `godot-cpp` 4.5 (runs on Godot 4.5 and later; downloaded by `build_native.py godot` into `native/godot/godot-cpp`, built with exceptions required by pocketfft):

- `TareVoiceBank.load(path)`: reads `.tvb` with Godot's `FileAccess`.
- `TareSound.add_bank(bank)` and `TareSound.render(spec, rate, knobs) -> AudioStreamWAV` (or `render_samples`, float output): any spec supported by the core, as JSON text (`Voice.to_json()`, simplest) or parsed `Dictionary` (Godot JSON reads all numbers as float64; tare.tools.tune seeds fit in 32 bits, so nothing is lost). A spec with `loop` returns a looping `AudioStreamWAV`. Core errors appear in the Godot console.
- Music renders track by track in the core, but score mixing (pan, hall, echo: `Score.render`) has not been ported. For now, music is pregenerated (`bake`): it is long and does not change during play.
- The example project (`native/godot/demo`, populated by `build_native.py demo`) plays five dialogue lines with emotions, generating the next in a thread while the current one plays; the advance click is also a spec, rendered on opening. `tests/test_godot.py` runs headless Godot on `demo/tests/render.gd` (speech, UI sound, sword clash, looping rain, creature; from text and `Dictionary`) and compares against Python (skipped without Godot or a compiled extension).

## Human speech

```
text ─► g2p (pt: rules | en: CMUdict + rules) ─► phoneme phrases/words/syllables
     ─► phonetics.segments: duration per phoneme (stress, phrase end, speed),
        stops = closure + burst + aspiration, fricatives, nasals...
     ─► 1 ms grid: smoothed segment targets (coarticulation):
        formants 28 ms, glides/liquids 80 ms, abrupt F1 at nasal release
     ─► intonation: declination + stressed accents + final contour by phrase type
     ─► SpeechProgram (tracks at 400 Hz) ─► klatt.render_speech
```

**Regional choices** (module constants):

- **Syllable-final "r"** (`g2p_pt.CODA_R`): `"R"`, Rio style fricative (default), or `"r"`, São Paulo style tap.
- **Strong "r"** (`phonetics.R_STYLE`): `"x"`, velar (default), or `"h"`, glottal.
- **English:** General American, with flap in "water" and dark syllable-final "l".

**How it was tuned:** Whisper as the ear (`tools/intelligibility.py`), comparing A/B versions on fixed game sentences. One test showed frication ~10 dB below natural speech; another found the coefficient-change click. Identical Whisper runs vary by about ±0.03 CER, so smaller differences are meaningless.

**Natural teacher (Kokoro).** `tools/teacher_calibration.py` generates 60 pt-BR sentences with Kokoro (male/female voices, ~5 minutes), distinct from test sentences. Kokoro supplies predicted phoneme durations (25 ms frames), giving alignment for free. (We later found sound occurs ~60 ms before this grid; measurements below predate that correction; see the natural engine.) The tool measures:

- formants of long stressed vowels;
- durations by stress;
- spectra of noisy fricative regions.

Findings, always checked in Whisper A/B tests:

- **Fricatives:** confirmed existing values ("s" ~6.3 kHz, "f" ~7.5 kHz). "Ch"/"j" measured ~3.15 kHz, [x] ~2.1 kHz, but using these values did not improve intelligibility beyond noise.
- **Vowels:** copying measured formants worsened CER (0.24 → 0.34). In running speech vowels undershoot targets, while our synthesizer already smooths targets; copying measurements would undershoot twice. Kokoro's faster rhythm also worsened results.
- **The real gain came from text rather than acoustics.** Comparing teacher transcriptions with ours revealed a systematic error: stressed "e"/"o" without a written accent were always closed. They now open:
  - before word-medial "r"/"l" (porta, certo);
  - in final "-el"/"-ol" (papel, sol);
  - in penultimate-stressed words ending in "-a" (nossa, janela, guerra);
  - excluding an exception list and suffixes "-esa"/"-eza"/"-oa".
- **Ceiling:** Whisper transcribes Kokoro itself at CER 0.003. Our remaining gap lies in structure (glottal source, bursts, coarticulation), rather than table values.

`phonetics.LANG_PHONES` stores language-specific overrides of the shared table. It is empty for Portuguese because no acoustic change passed A/B testing.

**Structure: frame by frame comparison with Kokoro** (`tools/structure_analysis.py`). The goal was naturalness. Our engine and teacher say the same phrase (`pm_alex` and `pf_dora` voices, equivalent pitch/tract). DTW aligns 10 ms frames on mel cepstra; spectra are then compared by phoneme class. Two independent judges:

- **Whisper:** intelligibility on the 16 sentences in `tools/intelligibility.py`;
- **UTMOS:** VoiceMOS 2022 MOS predictor, MIT license, rating naturalness 1–5.

Sentences split into training and validation (every third sentence held out). Teacher UTMOS is 3.5, ours 2.2.

*Diagnosis.* The five-formant cascade comes from Klatt's original 10 kHz design. Above F5, each resonator drops 12 dB/octave, leaving our vowels 25–75 dB below the teacher above 3.5 kHz. Also:

- nasals ~10 dB too weak in the midrange;
- voiced fricatives ~10 dB too strong;
- bursts ~6 dB too strong;
- formants change in steps, while the teacher's move continuously.

*Structural spectral fitting.* An evolutionary strategy fitted 13 structural constants to minimize spectral distance: fixed formants above F5 up to 11.5 kHz, bandwidths, coarticulation, frication/burst levels, breath, tilt. Held-out spectral distance fell 54.5 → 29.4. Both judges nevertheless worsened:

| | Spectral distance | UTMOS | Portuguese CER (Whisper) |
|---|---|---|---|
| current | 54.5 | 2.20 | 0.27 |
| spectral fit | 29.4 | 1.51 | 0.35 |

Ablation attributes UTMOS loss to upper formants (−0.24), wide bandwidths (−0.16), and faster coarticulation (−0.13). Matching the teacher's spectrum makes sound brighter and more mobile, exposing remaining defects.

*Formant targets by analysis through synthesis.* Each round measures F1–F3 using the same LPC tracker on rendered audio and aligned teacher frames, then moves table targets. This cancels tracker bias and accounts for coarticulation undershoot. In 4 rounds, held-out difference fell 0.088 → 0.039 (log). UTMOS stayed 2.18 and Whisper worsened (0.27 → 0.30). Same conclusion as copying measurements: the teacher's formant geometry does not suit our engine.

*Direct UTMOS optimization* (14 global constants, including prosody and speed): training 2.32 → 2.33, validation 2.18 → 2.14. Global adjustments do not move naturalness; a plateau.

*Where the gap lies* (`structure_analysis.py transplant`). Teacher speech is vocoded with WORLD; one of our components at a time replaces its counterpart, aligned by DTW:

| Condition | UTMOS |
|---|---|
| teacher / vocoded | 3.51 / 3.28 |
| + our pitch contour | 2.97 |
| + our aperiodicity | 3.20 |
| **+ our spectral envelope** | **1.72** |
| our envelope only in vowels/sonorants / only in obstruents | 1.78 / 2.15 |
| only our envelope's long-term average shape | 3.06 |
| our engine (vocoded / original) | 2.11 / 2.19 |

The gap lies in the spectral envelope from frame to frame, in vowels and consonants. It is not in the average shape, source, or intonation, which costs ~0.3.

*Feasibility test.* We replaced the cascade with teacher-learned envelopes: one template per phoneme and segment third, interpolated to our rhythm/intonation, synthesized by WORLD. UTMOS was 1.25–1.28, with both DTW and Kokoro's own segmentation. Average phoneme templates blur. This route would need context models (diphones) or a small neural model: another engine.

*Conclusion.* Within rule-based formant synthesis, no parameter adjustment closes the gap to natural voice. The formant engine keeps its strengths (tiny, stretches to any creature, babbling). The natural engine below provides natural voice without runtime AI.

### Natural engine (`speech/concat.py`, `tools/build_speech.py`)

Concatenative synthesis with our vocoder: recordings supply the spectral envelope; rules supply phonemes, rhythm, and intonation. Kokoro is only the teacher: it reads a corpus once, offline, leaving numbers.

**Voice bank.** 1,000 sentences per voice, ~45 minutes: 60 calibration sentences, 180 handwritten game dialogue sentences, and 760 from a small deterministic game dialogue grammar (`tools/corpus_pt.py`), none from the test set. Each reading passes through WORLD (5 ms: pitch, envelope in 64 bands, aperiodicity in 5) and receives phoneme labels from Kokoro's own alignment (25 ms steps), mapped to our symbols: misaki diphthongs ("A" = [ej], "I" = [aj], "W" = [aw], "O" = [ow]) split in two, vowel before [ŋ] nasalized, postvocalic [y]/[ɪ]/[ʊ] treated as glides. **Kokoro audio comes ~60 ms before its duration grid** (median 65 ms male, 60 female; 55–75 ms across sentences). Without correction, an [s] label mostly covered the following vowel: "próxima" became "pró-fi-ma". Each sentence's labels therefore shift to maximize fricative hiss and vowel energy relative to stop closures (search −100 to +20 ms). Each boundary then moves to the largest spectral change within ±15 ms. Within [s]/[ʃ] labels, energy above 4 kHz went from 13 dB below to 14 dB above energy below 1.2 kHz. **Kokoro also assigns time to stress markers** ("ˈ" before stressed vowels: 14% of all speech, sometimes 100 ms or more). That time begins the stressed vowel: aligning it there raises the score above from 41.0 to 42.9; assigning it to the preceding consonant drops it to 33.1. Previously it was discarded, leaving a pause inside the word whenever it reached 100 ms (785 such male-voice pauses, e.g. "cuid_ado"); shorter gaps pushed the consonant boundary into the vowel. Pauses: a mid-sentence pause where the teacher keeps voicing is not a pause (it reads through most commas); its time goes to neighbors. Of ~1,400 internal "pauses" per voice, ~100 are real. Silence beginning a vowel or other voiced sound after a pause (3 in 4, average 39 ms, ~67 dB below voice) moves into the pause; breathy endings before pauses (8 dB down) stay with the phoneme. Correct labels improved duration model correlation r = 0.59 → 0.70 and, on 32 test sentences, Whisper error 0.027 → 0.016 (male), 0.033 → 0.021 (female). Two Portuguese banks: `pt/alex` (male, tract 1.0, 130 Hz) and `pt/dora` (female, 1.15, 173 Hz), ~21 MB each (envelope stored as frame deltas for better compression). Labels and duration/intonation models live alongside them in `bank_<language>_<voice>.json` (~0.9 MB, 0.27 MB compressed): rebuilding them (`build_speech.py label`) does not rewrite frames. Older banks still include labels alongside frames; `.json` labels take precedence.

**Assembling a new phrase:**

1. Our front end (g2p + `phonetics.segments`, now marking word boundaries) supplies phonemes, stress, and intonation.
2. **Teacher accent** (`accent_pt`): aligning our transcription with the teacher on 240 sentences reduced differences from 988 to 438 in 7,137 phonemes (94% identical), with rules such as: syllable-final r becomes a tap, with short schwa before a word-internal consonant; "em" becomes [ẽj] + [ŋ]; "lh" becomes [lj]; post-stress unstressed i before a vowel becomes a glide ("sério" [ˈsɛɾju], "história" [isˈtɔɾjɐ]: teacher uses diphthong 237 times, hiatus 32); reduced a only in a long word's last syllable ("a", "da", "na" remain [a]); stressed a before m/n/nh nasalizes ("cama" [ˈkɐ̃mɐ]); s before a voiced consonant becomes [z]; [ŋ] follows nasal vowels before fricatives ("cansado") and at the end of "sim", "um".
3. **Teacher durations:** ridge regression of log duration, using phoneme, stress, word start/end, last word before pause, neighbors, and interactions (r = 0.70 in bank; 25 ms alignment limits it).
4. **Teacher intonation:** another regression predicts pitch at each vowel's beginning/end (log2 relative to phrase median), using phrase position counted from both ends, stress, position relative to nuclear accent, phrase type (statement, question, who/where question, exclamation, comma), and utterance position (r = 0.71 at vowel start, 0.82 at end). Targets connect linearly in log space and are smoothed (50 ms); `range` scales deviations, and `animalese` adds a note per syllable. Replaces our intonation rules in the natural engine (formant engine keeps them).
5. **Unit selection:** one bank piece per diphone (midpoint of one phoneme to midpoint of the next). Target cost: correct/substitute phoneme (group table: [a]/[ɐ] 0.3, [e]/[ɛ] 0.3, [u]/[w] 0.1...), stress, neighbors, duration, 0.5 per octave between piece pitch and target pitch, and for vowels, glides, nasals, liquids, 2 times the piece's unvoiced fraction. Without the last term, a high "Sério?!" selected [ɛ]/[i] from phrase endings where the teacher had faded to breath (whispered "cemitério"; 5% of bank vowels, 60% phrase-final), producing hiss. Pause cost is reversed: 2 times voiced fraction. Before label correction above, 92% of mid-sentence "pause" frames were voiced; commas rendered from them became murmurs ("Olá, o viajante"), and "É sério?" began with "Pen-". The term remains a guard. Join cost: 0 for contiguous bank pieces; otherwise mean spectral distance at phoneme midpoint (dB/10) + 0.2 + 0.5 per octave between pitches, multiplied by the join phoneme class weight (vowel 3, glide 2, liquid 1.5, nasal 1, fricative 0.4, stop 0.2, pause 0.05): joins inside vowels are more audible than in [p] silence. Viterbi uses the best 25 per diphone. Missing diphones combine halves from separate places. All diphone candidate costs are computed together in numpy, summed in the same order as the single-candidate reference retained in tests (identical choices checked on 300 sentences): ~15 ms per sentence versus ~440. The entire plan takes 14–32 ms per line; the vocoder accounts for ~90% of time (a line renders in about one tenth of its duration).
6. **Joins:** select the frame pair (between 25% and 75% of each piece) with closest spectra within the phoneme; crossfade ±15 ms around it, each piece continuing its own dynamics.
7. Apply pitch where the bank is voiced; vocoder reconstructs with `warp = character tract / teacher tract`.

**Measurements** (Whisper, CER, sentences outside corpus):

| | CER |
|---|---|
| direct teacher sentence resynthesis through our vocoder, 32 bands | 0.011 |
| first assembly, 60 sentences in bank | 0.22 (male) / 0.34 (female) |
| 240 sentences in bank | 0.17 / 0.18 |
| + teacher accent + regression durations | 0.11 / 0.11 |
| same through `Speaker` (with jitter); random NPCs (`Speaker.random(7)`, `(12)`) | 0.08 / 0.11; 0.12 and 0.10 |
| + realigned labels (−60 ms) and "x" in "próximo"/"táxi" in g2p | 0.045 / 0.042; 0.033 and 0.037 |
| + 1,000-sentence bank, 64 bands, consonant joins, learned intonation | 0.058 / 0.038 |
| formant engine | 0.23 |

Losses before realignment (16 corpus sentences, each excluded from its own bank): teacher phonemes, durations, pitch, 0.046; teacher durations with **our** pitch, 0.035 (intonation does not hurt); mean durations, 0.06–0.09; our transcription, 0.13. Remaining gaps are durations and transcription differences (open/closed vowels, [u]/[w]).

**Naturalness: where it is lost.** UTMOS (MOS predictor, 1–5) was diagnostic only, using a ladder of 16 corpus sentences excluding their own recordings from the bank, male voice:

| | 240-sentence bank, 32 bands | 1,000-sentence bank, 64 bands |
|---|---|---|
| teacher (Kokoro) | 3.46 | 3.46 |
| direct resynthesis by our vocoder | 3.02 | 3.20 |
| assembled pieces, teacher phonemes/durations/pitch | 2.26 | 2.65 |
| + our rule-based intonation | 2.17 | 2.45 |
| + our durations | 2.18 | 2.51 |
| + our transcription (whole system) | 2.23 | 2.55 |

Findings:

- **Vocoder:** full-resolution synthesis ties WORLD (3.30). Storing envelope in 32 bands cost 0.25; with 64, 0.08. Aperiodicity in 5 versus 16 bands makes no difference.
- **Assembly:** using a sentence's own pieces (no joins) scores like resynthesis (3.02): all loss comes from joins between recordings (12–15 per sentence). Larger banks: 60 → 120 → 240 sentences yielded 2.06 → 2.22 → 2.35; 1,000 yielded 2.65. Ramped level/spectral corrections at joins did not help; preferring consonants and similar pitches helped slightly (+0.09).
- **Intonation:** with the larger bank, our rule-based contour became the largest loss after joins (−0.20). Learned teacher intonation gives 2.66 versus 2.68 with teacher pitch. Adding pieces' microprosody (fast pitch deviations) to our contour changed nothing and was removed.
- **Pitch:** UTMOS falls as voice moves away from bank pitch (female: 2.61 at 173 Hz, 2.38 at 190, 2.22 at 210).

Whole system, 32 sentences outside corpus: male (115 Hz), UTMOS 2.37 → 2.71, CER 0.045 → 0.058; female at 210 Hz, 2.00 → 2.20, CER 0.042 → 0.038 (at bank pitch, 173 Hz, 2.61 on 16 test sentences).

### Phrase endings and emotions (`speech/concat.py`, `speech/emotion.py`)

**Phrase types.** The front end (both languages) recognizes `.`, `?`, `!`, `,` (also `;` and `:`), `?!`/`!?` (surprise), and `...`/`…` (ellipsis), and marks questions with interrogative words (Portuguese "quem", "onde", "quando", "como", "qual", "quanto", "que", "o que", "por que", "pra onde", etc.: who, where, when, how, which, how much, what, why, where to).

**The teacher does not produce Brazilian Portuguese questions.** Measured from its corpus (pitch of the final three vowels, semitones relative to phrase median, beginning/end of each):

| | n | Third-to-last | Penultimate | Last |
|---|---|---|---|---|
| statement | 404 | −0.1 / −2.1 | −4.2 / −7.0 | −8.5 / −8.0 |
| yes/no question | 40 | 0.2 / −1.7 | −4.1 / −7.0 | −8.7 / −6.4 |
| who/where question | 151 | 0.4 / −1.4 | −2.1 / −4.5 | −8.7 / −7.2 |
| exclamation | 29 | 3.3 / 0.0 | −5.0 / −8.3 | −8.1 / −6.5 |

Its yes/no questions fall like statements; regression learned that. After regression, the last stressed syllable and following material therefore receive contours described for Brazilian Portuguese (Moraes 2008; Frota et al. 2015), in semitones relative to median:

| | Stressed (start → end) | Following | Final stress | Ending duration |
|---|---|---|---|---|
| `?` yes/no (L+H\* L%) | −1.5 → +6 | +3.5 → −2 | −1.5 → +5.5 | ×1.1 |
| `?!` surprise | 0 → +9 | +6 → 0 | 0 → +8.5 | ×1.3 |
| `…` ellipsis | −0.5 → −1 | −1 → −1.5 | −0.5 → −1 | ×1.45 |

Peaks were lowered from initial values (+7 and +11): shifting far above bank pitch makes sound thin and scratchy. Interrogative-word questions retain regression's falling contour, with first vowel raised 1.5 semitones; exclamations widen phrase movements 25%. The intonation model now distinguishes interrogative-word questions (`?wh`). Pauses: `?!` 0.42 s, `…` 0.6 s. The formant engine treats `?!` as a question with 60% more range, `…` as a comma.

**Experimental: intonation learned from real speech** (`tools/real_prosody.py`; off by default). Instead of Kokoro, intonation is fitted to real Brazilian readers: TTS-Portuguese Corpus (one speaker, 10.5 h; CC BY 4.0) and Portuguese CML-TTS lines containing questions, exclamations, or ellipses (LibriVox audiobooks; CC BY 4.0). Audio is used only for measurement, outside the repository. Each phrase passes through our front end; Montreal Forced Aligner (classic HMM, offline) aligns our phonemes to recordings, using one dictionary entry per word occurrence so each aligned vowel is a model nucleus; WORLD (dio) supplies pitch. CML-TTS mixes Brazilian and Portuguese readers, whose question contours differ. Thus 30 utterances per reader are aligned twice, using MFA Brazilian and European dictionaries restricted to shared words; retain readers explained as well or better by the Brazilian dictionary: 12 of 46. The reader contributing half the lines was Portuguese (European won 30/30). Retained: 5,024 sentences, 172,000 vowels, ~720 questions, ~650 exclamations.

On held-out sentences (and 3 unseen readers), vowel pitch prediction error falls 3.5 → 2.8 semitones (statement end 5.9 → 2.9; yes/no stress 4.6 → 3.6; exclamation 5.4 → 3.5). Kokoro sinks final statement stress ~7 semitones beyond real people (H+L\* L%: high pretonic, stress near middle, only posttonic falls). Listening is worse, however: questions rise only ~2 semitones on stress (averaging rises peaking at different locations yields a small rise) and disappear; bank pieces recorded with Kokoro contours accept new ones less well (male UTMOS 2.78 → 2.69, female 2.38 → 2.19). Kokoro melody with handwritten question contours remains. To hear the experiment, set `TARE_TOOLS_TUNE_PROSODY=real`, the directory where the tool writes `prosody_pt.json`. Surprise and ellipsis had only 2 examples each: experimentally, surprise uses question movements 1.6× wider and ellipsis a lengthened comma contour.

**Emotions** (`emotion.py`). Measured in emoUERJ (UERJ, 2021, CC BY 4.0; 8 actors, 377 recordings; analysis only): each emotion against the same actor's neutral reading, averaged over actors. Pitch/range via WORLD (harvest); speed via syllabic nuclei (voiced energy peaks) per speech second; brightness = energy 2–5 kHz minus 0.1–1 kHz; breath = voiced aperiodicity 1–4 kHz; ending = pitch slope over last 300 ms of voice.

| | Pitch | Range | Speed | Brightness | Breath | Ending |
|---|---|---|---|---|---|---|
| happiness | +6.3 st | ×1.27 | ×0.98 | +3.5 dB | ×0.89 | −1.4 st |
| anger | +4.6 st | ×1.27 | ×1.05 | +3.7 dB | ×1.0 | −3.5 st |
| sadness | −0.2 st | ×0.97 | ×0.92 | +0.8 dB | ×1.13 | +1.5 st |

emoUERJ lacks fear and surprise: these follow Murray and Arnott (1993), scaled to the measurements (fear: +5 st, range ×1.15, speed ×1.12, more breath, tremor; surprise: +4 st, range ×1.5). `sussurro` (whisper) is all breath. Emotions become `Speaker` changes (pitch, `range`, `rate`, `tilt`: +1 dB/octave = `tilt` × 2^(1/3), `breath`, `jitter`), plus natural-engine statement endings (`final`) and pauses. Intensity (0–1, default 0.8 because actors were theatrical) scales everything from neutral.

**Text markers.** `[emotion]` or `[emotion:0.5]` change emotion from that point onward; each segment becomes a spec layer (`Spoken` or `SpeechProgram`), sequentially, with 0.3 s between segments ending in punctuation. Whisper understands emotional speech almost as well as neutral (8 sentences, male: neutral 0.056, sadness 0.038, whisper 0.038, happiness 0.073, surprise 0.074, anger 0.084, fear 0.100).

**Babbling** (`speech/babble.py`). Syllables can be replaced after g2p, before prosody, preserving text rhythm, stress, and phrase type:

- `gibberish`: each syllable becomes random onset + vowel from the language inventory, sometimes with word-final coda; seed is utterance + character name.
- `mumble`: every syllable becomes m + schwa.
- `animalese`: retains syllables but voice becomes 1.5× higher, 2.2× faster, with half intonation and a random note (±5 semitones) per syllable added to the contour.

**Casting** (`speech/casting.py`). `cast(role, name, lang, gender, creature, voice, style, natural)` returns a `Cast` (voice + style + role) with `render()` and `voice()` (spec). Rules:

- Voice is generated from name; `gender` selects the first seed with pitch ≥ 165 Hz (f) or ≤ 150 Hz (m).
- `main` uses that voice in the natural engine (unless `natural=False`); other roles use formant synthesis.
- Explicit `voice` always wins. Old `kokoro:<id>` names map to natural voices in the same register (`pm_alex` → `pt/alex`, `pf_dora` → `pt/dora`).

Bestiary and `bake` use casting. Manifest records each character's `role`, `style`, and `engine`.

**Speech next steps:**

- English voice banks (misaki-to-English symbol mapping is still missing).
- Durations: alignment finer than 25 ms would improve regression.
- Microprosody: add teacher deviations within each piece to our pitch.
- More languages: front end is pluggable (`speech.LANGS`).

### Vocalizations (`speech/emote.py`, `speech/vocoder.py`)

**First version: formants.** Vocalizations were formant synthesizer frames assembled from segments (breath, vowel, hum, hiss, burst), measured from the recordings below. They sounded artificial and robotic, the same limitation as formant speech.

**Now: real performances, reconstructed by us.** Each CC0 recording is analyzed once during development with WORLD (`tools/build_barks.py`, `pip install pyworld`). Only numbers remain every 5 ms: pitch, spectral envelope, air content. There are 183 templates, 146 s of performance, 951 kB. In game, `vocoder.py` reconstructs sound with our numpy synthesis (no model, no WORLD), shifting it to the character's voice. Deterministic: same character, type, style, take, same samples.

**Sources** (CC0; source recordings are not in the repository):

- OpenGameArt: "Voice Clip Pack - Male Adventurer RPG", Cici Fyre's "Female RPG Voice Starter Pack" (three voices), "Male Grunt/Yelling sounds" (three voices);
- Freesound: laughs, giggles, sighs, gasps, "hm", "huh?", cheers, pain moans, by ID (list in `tools/build_barks.py`'s `MANIFEST`; each template stores its source).

**Synthesis matches WORLD.** Across 21 templates, band energy averages within ±1 dB of WORLD's own synthesis from 200 Hz to 24 kHz; occasional bands below 1.2 kHz differ by up to 9 dB. Measured voicing (harvest) is similar: mean 0.71 versus 0.75. Three details mattered:

- pulses land between samples (fractional delay): without it, rounding a 700 Hz voice causes 1.5% jitter;
- air is zero-mean noise between pulses, filtered by the envelope: it disappears below pitch, as in WORLD;
- below recorded pitch, CheapTrick's envelope measures nothing (it sometimes reached 20 dB above formants). Replace it with the value at pitch, falling 3 dB/octave. Otherwise, downshifted voices gained an excessive first harmonic, every sound onset a low thump.

**Shifting to the character's voice.**

- Efforts (attack, pain, death, jump, cheer) use shout register: `pitch = shout(character speech, character tract) / shout(performer speech, performer tract)`. Others (laugh, sigh, "hm") use speaking register: `pitch = character speech / performer speech`. Performer speech is estimated from assigned tract: 115 Hz (male, tract 1.0), 190 Hz (mature, 1.1), 210 Hz (female, 1.15), 260 Hz (cute, 1.27).
- `warp = character tract / performer tract`, clamped to 0.75–1.35. `pitch` stays between 0.4 and 2.5.
- Template selection minimizes `|ln pitch| + 3·|ln warp|`, minus the style's performer preference. Large formant shifts reveal converted voices more than pitch shifts. Heroines therefore use female performers, heroes male.
- When no performer for the type is close, use a related type, stretched/transposed, with +0.25 cost. Examples: no female heavy attack (attack ×1.5), no male giggle (laugh ×0.75, +4 st).
- Take selects among templates within 0.25 of best (at most 4), plus ±0.6 st pitch and ±6% duration.
- `Speaker` voice also applies: `breath`/`whisper` become air; `tilt` (Hz) becomes slope, `3·log2(tilt/3000)` dB/octave; `range` becomes `swing` (`range^0.7`, so robots are monotone); `rate` shortens. `crush`, `drive`, `space` pass to `Voice`.

**Styles:**

| Style | Pitch | Formants | Duration | Air | Brightness (dB/oct) | Contour | Prefers |
|---|---|---|---|---|---|---|---|
| `grunt` | 0 | 1.0 | 0.92 | +0.08 | 0 | 1.0 | adventurer, shouts |
| `anime` | +1 st | 1.04 | 1.0 | −0.25 | +1 | 1.15 | cute voice |
| `tactics` | −1 st | 0.98 | 0.88 | 0 | −0.8 | 0.85 | mature voice, short takes |
| `mmo` | +0.5 st | 1.0 | 1.12 | 0 | +0.5 | 1.1 | shouts |

`intensity` (0–1, baseline 0.7) for efforts: −2.1 to +0.9 st pitch, −1.4 to +0.6 dB/octave brightness, 0.79× to 1.09× duration, slightly less air with more effort. Other types use half the pitch/brightness change, duration 0.86× to 1.06×.

**Measurements** from the same recordings, first version (still applicable to shout register):

| Vocalization | Duration | Pitch | Voice versus air | Other measurements |
|---|---|---|---|---|
| attack | 0.15–0.35 s | men +17 to +23 st above speech, women ~+10; steady, falling at end | 10–60% voiced | 50–190 ms breath to peak |
| pain | 0.2–0.4 s | rises +1.5 to +3 st, then falls | — | fast onset |
| death | 1–2 s | high, slowly falling | 80–95% voiced | — |
| jump | 0.17–0.3 s | — | — | — |
| laugh | — | — | — | pulses 4.5–5/s (men), 5–6/s (women); giggle 6–8/s |
| sigh | — | falls 2.5–3.5 st | almost all air | — |
| "hm" | 0.9–2.8 s | rises ~4 st in doubt | nasal | — |
| "yay" | — | starts 2–3 st higher, falls | — | — |

**Shout register.** Effort pitch moves from speech toward a tract-dependent register: f0 = speech^(1−e) · R^e, with R = 420 Hz · tract^1.8 and e ≈ 0.85 (0.55 for jump). Calibrated from recordings: a 95 Hz man shouts at ~345 Hz; women speaking at 230, 280, 550 Hz shout at ~430, ~530, ~600 Hz.

## Generation 1 engine

`chip.py` emulates Game Boy channels as used by Pokémon Red/Blue's cry engine:

- Notes in frames of 17,556 samples at 1,048,576 Hz, 4-bit volume envelope.
- Duty byte rotates 2 bits per frame.
- 15- or 7-bit LFSR, with detected/cached cycle.
- Noise pitch adjustment ends with pulses, and noise ignores tempo (engine quirks).

Decimation has two stages (÷16, then exact ratio), with cached FIR filters. This keeps any output sample rate fast.

The engine was verified against the original TypeScript engine with fixtures generated before the TS code was removed; that test, its fixtures and the cry data are game data and stay out of the repository. The `chip` archetype uses the same engine to create original cries without game data.

## Next steps

- Native core: chip programs, vocalizations (templates in an engine format), score mixing, Godot streaming (`AudioStreamGenerator`) for long ambience/music; then C++ speech planning once voice tuning settles. Unity (native plugin over the same core) and JS/WebAudio (web editor) follow.
- Visual editor: gene/trait sliders, spectrogram, live evolution.
- Quality: LF glottal source, real reverb IRs, loudness normalization (LUFS) in packs.
- More archetypes (aquatic, dedicated dragon, swarm), mixing archetypes (hybrids).
- Redesign archetypes the CLAP judge misses (mammal, bird, insect, robot), measuring with `tare.tools.tune judge`.
- Weak effects in the judge: footsteps, sword clashes, occasional ambience events. Compare with real recordings, as done for glass, thunder, campfire.
- Extend `design`/`match` (CLAP) to sound effects, searching genes per recipe.
