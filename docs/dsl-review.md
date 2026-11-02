# Review and edit a sound

[Agent workflow](dsl-agent.md) · [DSL reference](dsl.md) · [Português](pt-BR/revisao-dsl.md)

`dsl review`, `describe` and `edit` combine existing compilation, capture bundles,
inspection and source transactions. The saved bundle is the observation used by
the next edit. There is no implicit “latest” revision or separate session service.

## Start with the selected sound

```bash
tare.tools.tune dsl help --json
tare.tools.tune dsl help edit --json
tare.tools.tune dsl review examples/dsl-bank.tune.json --name confirm -o output/reviews --json
```

The `tune.review/1` response includes an absolute `bundle` path, `audio.wav`
relative to that bundle, a factual description, duration, channels, levels,
captured processing stages, track timing/pitches, export capabilities and checks.
Rows are bounded by `--limit` (default 5, maximum 100). Full source, buffers,
identities and provenance remain in the immutable bundle. Playback and listening
remain necessary to judge sound quality.

For routine iterations, add `--response compact` (Python: `response="compact"`)
to `review` and `edit`. The `tune.compact/1` summary retains observed levels,
check coverage/failures, the next bundle and affected-sound scope while reducing
repeated context. Detailed remains the default. See the [token analysis](dsl-review-token-costs.md)
for the exact profile, five-edit measurements and comparison limits.

Pass an existing bundle as SOURCE to review its retained audio without loading
the current source/assets or compiling again. Use `--previous BUNDLE` to compare
PCM identity, measured levels/duration, track summaries and a bounded source
diff. Two DSL bundles must belong to the same source file and selected sound.
Changes describe observed results; they do not assign acoustic causes to fields.

## Discover controls, then batch edits

In the following commands, replace `BUNDLE` with the returned bundle path.

```bash
tare.tools.tune dsl describe BUNDLE --fields power --json
tare.tools.tune dsl describe BUNDLE --find confirm --limit 3 --json
tare.tools.tune dsl edit examples/dsl-bank.tune.json --from-bundle BUNDLE -o output/reviews --set /with/power 0.65 --json
```

`describe` returns `tune.describe/1`: current values, available schema ranges or
choices, exact relative paths, allowed operations, source scope and layer IDs.
`--find` searches explicit authored sound/definition names and recipe labels; it
returns candidates and a revision-bound cursor rather than choosing a match.
Request up to 32 exact field names with `--fields`. Lists and large values are
summarized; existing `dsl query`/`expand` remain available for deeper inspection.

For an invocation, parameters use `/with/NAME`. For a definition, defaults use
`/params/NAME/default`; the description reports affected sounds. `--set` accepts
authored RFC 6901 paths relative to `--target` (default: the reviewed sound).
Missing object parents are created, while arrays must already exist or be set
explicitly. JSON values follow each path; repeat `--set` to make one atomic batch.

Only the observed sound, its descendants and definitions it uses can be edited
from that observation. A shared definition edit validates compilation of all
sounds, but renders/checks only the selected sound; affected names are reported.
Review other affected sounds when their audio matters.

## Refine generated audio while keeping its recipe

```bash
tare.tools.tune dsl edit bank.tune.json --from-bundle BUNDLE -o output/reviews --refine /lowpass 2400 --refine /gain 0.4 --json
tare.tools.tune dsl describe BUNDLE --layer n0/p0 --fields hardness --json
tare.tools.tune dsl edit bank.tune.json --from-bundle BUNDLE -o output/reviews --layer n0/p0 --refine /hardness 1200 --json
```

Use a fresh returned bundle for each subsequent edit. Refinement creates or
updates one guarded `edit` wrapper and preserves its other overrides, removals
and appended layers. Selected original root Voice layers map back to their
original materialized paths, including after removals. Appended layers and
Score/Cue child layers require authored editing or the existing `expand`/`patch`
workflow. Musical transposition belongs in Notes, before materialization.
`--set` and `--refine` are separate scopes and cannot be mixed in one batch.

The editor verifies saved-bundle integrity, authored revision, compiler/renderer
identity, materialized base and asset hashes under the existing source lock. It
trial-renders and checks the candidate before backing up and atomically replacing
the source. A stale observation fails; it is never silently refreshed. A failed
render/check leaves the source unchanged. External writes during preparation
are detected before commit.

`--dry-run` retains a read-only candidate bundle and leaves source bytes unchanged.
Failed candidates are also read-only. An orphan candidate can remain after a
failed commit; it does not publish a current revision. Ordinary older capture
bundles remain readable, but only a source review can authorize this edit API.
In Python, edits require a saved bundle path, not a mutable `Capture` object.

## Declare measurable checks

```json
{
  "format": "tare.tools.tune.checks",
  "version": 1,
  "duration_s": {"min": 0.01, "max": 1},
  "peak_dbfs": {"max": -6},
  "sample_rate": 16000,
  "channels": 1,
  "capabilities": ["pcm", "voice_json"]
}
```

```bash
tare.tools.tune dsl review examples/dsl-bank.tune.json --name confirm -o output/reviews --checks examples/dsl-review.checks.json --json
```

Checks are optional, versioned data with fixed fields. Duration and peak accept
`min`/`max`; sample rate/channels require equality; capabilities require supported
`pcm`, `voice_json`, `native_voice` or `midi` exports. They evaluate retained float
PCM before PCM16 conversion. Silence has a null dB value and is compared in linear
amplitude. No executable expressions are accepted. Checks do not affect synthesis,
random seeds or the meaning of the existing `edit.expect` materialization guard.

Results distinguish `passed`, `failed`, `not_run` and `not_requested`. Coverage
separately reports capture integrity, perceptual quality and pitch. No declared
checks means `not_requested`; perceptual quality is always `not_run`. A generic
capture without a DSL capability record cannot prove those export capabilities.

Source review returns a failed observation so it can be corrected. CLI failure
exits **5** and, with `--json`, puts the review in the diagnostic `details` field.
Requested-check failure during an edit also exits 5 and prevents source commit.
Source/dependency conflicts retain the existing exit code **3**. Checks are
inherited from the observed review unless explicitly replaced with `--checks`.

## Ask a listener

Checks cannot judge timbre: `perceptual_quality` stays `not_run`. When the next
decision needs an ear, render candidates as dry runs from one observation, put
them in a listening round, and read the answer as data:

```bash
tare.tools.tune dsl edit bank.tune.json --from-bundle A -o output/reviews --set /power 0.9 --dry-run --response compact --json   # -> B
tare.tools.tune dsl edit bank.tune.json --from-bundle A -o output/reviews --set /power 0.2 --dry-run --response compact --json   # -> C
python tools/curate.py compare power A B C --open --question "Which sounds firmer?" --root output/rounds
python tools/curate.py serve --root output/rounds        # the listener answers in the browser
python tools/curate.py answers power --json --root output/rounds
```

```json
{"round": "power", "revision": "…", "groups": [{"id": "g1", "title": "Compare revisions",
  "answers": {"pick": "C", "rate:qualidade|ruim|ótimo": {"A": 2, "C": 5},
              "marks": [{"seg": "B", "t": 0.1, "note": "click"}]},
  "segments": {"A": "…/reviews/<A>", "B": "…/reviews/<B>", "C": "…/reviews/<C>"}}]}
```

Only answered tasks appear. Labels follow the order given to `compare`; marks are
seconds into that candidate's audio. Dry runs leave the source at A's revision, so
the pick is committed by repeating its edit from A; the committed render is
identical to the candidate the listener heard (the test compares PCM identities).
Committing a non-dry candidate and then choosing an older one is a stale edit
and is refused, as usual. A blind round (the default without `--open`) hides
labels, notes and measurements from the listener only; `answers --json` always
maps back to the bundles. Its cards are numbered by shuffled position (#1, #2…)
and show the labels A, B, C only after the listener reveals names: take the
choice from `answers --json`, never from a card number mentioned in chat.

Use the path `describe` returned: `/power` fits the direct recipe built in
[Python and builders](#python-and-builders); a `use` such as
`examples/dsl-bank.tune.json` needs `/with/power`. In Git Bash, prefix commands
with `MSYS_NO_PATHCONV=1`, or `/with/power` arrives as a Windows path. Two bundles default to blind ABX, more to pick/1–5
rating; `--task` accepts the curator's task specs. The page matches loudness by
default: pass `--keep-levels` when level (power, volume) is what is judged, so
the round opens with matching off.

## Hold a sound against a recording

A recording of the sound you are after (a game's, a foley take) can stand next to
the render, as numbers and by ear. First ask what it is made of:

```bash
tare.tools.tune study refs/clash.wav                  # KIND, the ear's lines, IN TUNE
tare.tools.tune study refs/line.wav --domain speech   # a pitched sound: speech, creature or sfx
tare.tools.tune study refs/clash.wav --search sfx:blade   # the 3 nearest renders of one kind
```

`study` ends with the fields that reach each part, as pxl's study ends "IN PXL":
an op to start from, a value where the relation is direct (`knobs.length` from the
active length, `speaker.pitch` from the median pitch less the 12% intonation adds),
a direction where it is not (brightness, register, ring, range, rate, size), and
what a recording cannot tell (kind, style, event, archetype, words: the ear picks
them). `--search sfx:KIND` renders every style and event of that kind and lists
the 3 nearest by DSP distance (pitch and loudness contours, envelope, length,
noisiness, syllables); `--search creature` does the same over archetypes, calls
and sizes in about 25 s. Each row is a sound to paste into the bank and listen to:
near in numbers is a place to start, not a match. Then name it per sound at the top of the bank; the document-wide
`"reference": {"file": ...}` still serves every sound without one:

```json
{"format": "tare.tools.tune.dsl", "version": 1,
 "references": {"clash": "refs/clash.wav"},
 "sounds": {"clash": {"sfx": "blade", "style": "steel", "event": "clash", "dry": true}}}
```

`review` then holds the sound against it. The compact response adds `ref`, each
pair `[recording, sound]`:

```json
"ref": {"active_s": [0.42, 0.36], "attack_ms": [0, 34], "centroid_hz": [4654, 5079], "f0_hz": "unvoiced", "env_db": 5.2}
```

Each signal is measured from its own onset and against its own peak, so recording
gain, leading silence and sample rate do not count. `active_s` runs to 40 dB under
the peak (or 6 dB over the noisier floor, one end for both); `attack_ms` to 3 dB
under the loudest millisecond; `centroid_hz` is brightness, in the band both rates
hold; `f0_hz` the median pitch (a ring above 1600 Hz, beyond the pitch
tracker, by its own frequency; `unvoiced` when there is none); `env_db` the mean
spectral difference in dB. The detailed response adds `end_60_s` (what an export
keeps, `not_measurable` over a noisy floor or when the file ends first), the
difference in loudness shape and
the band that differs most. The numbers aim; they never say the sound is alike: a
recording carries room, microphone and mastering the synth lacks, and two
different sounds can share a length and a brightness.

Tolerances go in the checks file (`reference` in
[the example](../examples/dsl-review.checks.json)): `active_s` as a `ratio`,
`attack_ms` as a `max_delta`, `centroid_hz` and `f0_hz` in `semitones`, `env_db`
as a `max`. A sound without a recording is `absent`, not failed; a requested
measure that could not be taken is `not_run` and fails like any unmet check;
recording and sound both unpitched pass `f0_hz`, one pitched and one not fail it.
To let the ear decide, put the recording beside the candidates:

```bash
python tools/curate.py compare clash A B --reference refs/clash.wav --root output/rounds
```

REF plays first, the others diff against it (key D), its measures become the
targets, and the round opens, since a blind round would hide it. A bundle keeps
the recording's PCM: keep bundles and rounds on this machine; `freeze` and
`export` carry only the sound. `dsl help reference --json` lists these rules.

## Hear it as text

An agent cannot hear a WAV, but it reads text exactly. `ear` prints a sound the
way an ear divides it: 20 auditory (ERB) bands, 80 Hz to 8 kHz, by time from the
sound's onset, each cell a digit for 6 dB under the sound's loudest cell (9 is the
loudest, `.` 54 dB under), A-weighted so lows read as quiet as they sound:

```bash
tare.tools.tune ear output/reviews/<bundle>               # against its reference, if it has one
tare.tools.tune ear output/reviews/<B> --vs output/reviews/<A> --brief   # what an edit changed
tare.tools.tune ear recording.wav --vs none --lines       # facts only, about 400 tokens
```

```
SOUND peaks: 3000 Hz +0 dB rings 280 ms
...
DIFF SOUND vs REF 0..500 ms, 10 ms/col: + SOUND louder by over 6 dB, - quieter, = within 6, blank both 40 dB under
 3700|+=+-===--==---------------------------------------|
 2200|=-=========++===++=++=++=+=++=++==+++ ++          |
SOUND louder in 110 of 420 cells (most: 5200 Hz 40-330 ms, 2200 Hz 110-400 ms); quieter in 119 (most: 3700 Hz 30-500 ms, ...)
```

Lines come first: the envelope (attack, when it falls 20, 40 and 60 dB, or that
the file ends first), up to four spectral peaks in Hz with how long each rings
(harmonics of a voiced pitch are named once), pitch with its range and glide,
brightness early and late, stereo balance. Then the grids: an attack zoom at 2 ms
per column for sharp sounds, the whole sound at a step that fits it in 50
columns, the seam of a loop (its last 30 ms then its first 30), a row of `^`
under later onsets, and the pitch every 5 columns when the sound is voiced. With
another sound there is a DIFF grid and a summary line. A full first look costs
about 2.5k tokens, `--brief` (lines and DIFF) about 1k; `--at START,LEN` puts one
grid where you need it, `--weight none` shows raw energy, `--align peak` starts
at the loudest moment for a slow onset, `--json` returns the same as data.

Every output ends with what it does not show: phase, detail finer than a column
or a band, roughness and masking. A DIFF cell is 6 dB and one band, so `=` is not
"the same". The text says where a sound differs, never how it sounds; the
[listening round](#ask-a-listener) is where that is decided. The pitch tracker
reads 60 to 1600 Hz: a ring above that is named as a ring, and the tracker's
subharmonic is reported as such, not as a pitch.

Whether a reading predicts the listener is measured, not assumed. Before the
page is served, record what the text says the listener will answer; after, hold
it against the answers:

```bash
python tools/curate.py predict clash predictions.json --root output/rounds   # {"g1": {"pick": "B", "rate": {"A": 2, "B": 4}}}
python tools/curate.py agree clash --root output/rounds   # or several rounds, summed
```

`predict` is refused once the round has an answer, and `agree` refuses a
prediction written or changed after the first one. `agree` sets the reading
beside chance, a fixed rule (the candidate nearest the reference by the `ref`
numbers) and the listener's own consistency (the same sounds picked again in
another round), and says how often a guesser would do as well: 5 right of 8
picks among 3 comes by luck 1 time in 11, so a few picks are a clue, not a licence.
Until 20 picks or more say otherwise, the listener decides.

## Python and builders

```python
from tare.tools.tune.dsl import builders as t
from tare.tools.tune.dsl import describe, edit_file, review

t.Project(context={"sample_rate": 16000}, sounds={
    "confirm": t.sfx("ui", style="crystal", event="confirm", dry=True)
}).write("bank.tune.json")

observed = review("bank.tune.json", name="confirm", output="output/reviews")
controls = describe(observed["bundle"], fields=["power"])
updated = edit_file("bank.tune.json", from_bundle=observed["bundle"],
                    output="output/reviews", set_fields={"/power": 0.65})
```

Builders, including `creature`, are also exported from `tare.tools.tune.dsl`.
Builder-assisted initialization produces normal validated JSON; that JSON is the
subsequent editing source. This workflow does not execute Python from project
data or synchronize edits back into a separate Python authoring program.

These operations reduce integration work and unnecessary regeneration. Their
responses intentionally include more facts than a tiny acknowledgement. Measure
the complete requested workflow, including help, helpers and failures, before
claiming token savings over competent Python. The original and version-2 token
measurements remain historical records of their respective protocols.

[Implementation and three-task token replay](dsl-review-implementation.md)
records the delivered scope, validation and remaining warm-response overhead.
