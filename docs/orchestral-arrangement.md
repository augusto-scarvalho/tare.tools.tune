# How an orchestral battle is laid out

[Português](pt-BR/arranjo-orquestral.md)

What a study of orchestral game music found, how it was measured, what a listener then picked, and what it
changed in tune. Only numbers are kept: no recording, score or transcription from the study is in the repository.

## Three things a piece is made of

| Layer | What it holds | Where it was read |
|---|---|---|
| The score | which part plays what and when: roles, registers, entries, form | scores (MusicXML) |
| Timbre | how each instrument sounds: partials, attack, decay | single recorded notes |
| Mix and performance | how much each part weighs: level by section, low end, percussion | the recording |

Audio answers the second and third. For the first, a score is the only source that held up.

## What was measured

**A soundtrack album, 71 tracks** (*Triangle Strategy*; `tools/music_study.py`). Tempo, loop length, level over
time, low and high shares, percussive share. Against our `battle` and `skirmish` cues its battles are longer (loops
of about two minutes, ours 25 to 50 s), vary more in level (4.4 dB against 2.1), open under their own middle level
(3.5 dB against 0.3) and carry more low end (39 % of the energy under 200 Hz against 11 %) and more percussion
(19 % against 7 %). The tool's tempo can read half the real one (our `skirmish`, 155 bpm, read as 77), and its key
estimate is not to be trusted where the margin is small.

**Which instruments, by models** (the 13 battles, on a GPU). Zero-shot tags (CLAP) agree on families (brass in 94 %
of the 10 s windows, a string orchestra in 71 %) and not on anything finer. A stem separator trained on pop
(Demucs) files mid and low strings under "guitar" and the bass drum under "bass". Nearness to real single notes
(VSCO-2, CC0) settled two doubts the tags left: that "guitar" is violas and cellos, and one battle has a piano.

**A transcriber** (YourMT3+), held against a score of the same piece: on the real recording it finds 55 to 67 % of
the pitched notes (18 to 27 % by chance), about a third to a half of what it reports is in the score, percussion is
at chance, and nearly every note comes back as "ensemble". Good for checking, not for replacing a score.

**22 scores** of game and screen music, fan arrangements for orchestra (`tools/score_study.py`):

| What they share | Scores |
|---|---|
| One note per attack in a part (1.4 or fewer): lines, not block chords | 22 of 22 |
| Leaps over a fourth in a fifth of the moves or fewer | 20 of 22 |
| The number of parts playing grows 1.5 times or more | 21 of 22 |
| The fullest 4 bars hold twice the notes of the emptiest, or more | 21 of 22 |
| The busiest part is percussion | 7 of 22 |

How many notes sound is not what sets them apart: counting each note once however many parts double it, battles and
action pieces run from 4 to 45 notes a second, and ours sit inside that.

## Ours on the same ruler

`Score.arrangement()` reads a score of ours with the function that reads those (`tare.tools.tune.score.arrangement`).

| | notes per attack | leaps | parts grow | density ratio |
|---|---|---|---|---|
| The 22 scores, median | 1.1 | 0.10 | 3.7x | 6.9x |
| `battle` (seed 1) | 1.22 | 0.35 | 1.0x | 1.0x |
| `skirmish` (seed 1) | 1.14 | 0.49 | 1.3x | 1.2x |
| `march` (seeds 1 to 3) | 1.00 | 0.03 | 4.0x | 8.2x to 8.8x |

## What a listener picked

One untrained listener, blind rounds, forced choices. Few picks: leads, not proofs.

- **One tune, two arrangements, same tempo and length.** The arrangement by the four rules was picked over the
  `battle` cue's way (horns in three-note chords, strings in leaping arpeggios, everyone from bar 1).
- **`march` from a seed against `battle`, three pairs.** `battle` was picked in two. The notes: two lone crashes in
  48 bars read as mistakes; at 120 bpm it read as standing still; the march that won was the fastest.
- **Short string notes.** Plucked was picked over the slow bow and over the measured spiccato; a spiccato with half
  the recorded bite, where the pitch reads sooner, was picked over plucked.
- **The assistant's predictions** from these numbers were right in 1 of 5. The layout numbers do not predict this
  listener; tempo and one odd detail decided more.

## What changed in tune

- **`march`**: a battle from a seed laid out by the four rules, the fast notes in the snare, a crash on every loud
  phrase, 126 to 142 bpm.
- **`spiccato`**: a string section's bounced stroke, measured on 186 recorded notes, with half the recorded bite.
- **`snare`**: retuned to the recorded hits (it was mostly wire); this alters every cue that plays it. Timpani and
  bass drum were measured the same way and already matched.
- **`Score.arrangement()`**, and in the DSL `dsl check FILE --name NAME --layout`, which reads the layout and the
  rubs from the notes without rendering, so a piece too large to review can still be read (`dsl review` adds
  the same `arrangement` to its facts when the piece fits). `dsl help arrangement` holds the rules for an agent
  that composes.

## Doing it again

```bash
python tools/music_study.py FOLDER_OF_RECORDINGS -o study.json   # tempo, loop, level map, balance
python tools/score_study.py FOLDER_OF_SCORES -o scores.json      # parts, registers, entries, the shared rules
python tools/score_study.py ONE_SCORE.mxl                        # one piece, part by part
```

Keep the recordings and scores outside the repository (`private/` is ignored). What still asks for an ear: whether
`march` now holds against `battle`, its quiet opening (6 to 8 dB under its middle level, where 2 to 5 is usual) and
the snare's missing thump under 150 Hz.
