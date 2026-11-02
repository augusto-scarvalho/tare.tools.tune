"""Music for a tactics RPG: the battles (a skirmish, a tense standoff, a boss, the final one), getting ready, the
briefing, the world map, the story's scenes (sorrow, intrigue, triumph, comedy) and the jingle for a new recruit.

The style is the martial, modal orchestra of Hitoshi Sakimoto's tactics scores, measured on FFTA2's 37 music
sequences (the user's own copy; analysis only: numbers, no melody):

    battles      125-170 bpm, in Dorian, harmonic minor, Phrygian, Mixolydian or minor, rarely plain major
    slow scenes  50-80 bpm, in minor, Phrygian, harmonic minor or Lydian
    the map      100-150 bpm, in Lydian and Mixolydian
    the orchestra up to 16 tracks at once, 6-17 notes a beat; the bass very low (its mean between B0 and A2)
    the tune     steps most of the time, but leaps (a 4th or more) on 10-30% of its notes, over half in the darkest
    the loops    long: 60-270 beats

Every cue here is generated from its seed like the others (music.py): the key, the chords, the rhythms and the tune.
"""
from .music import (
    CALM,
    CUES,
    DRIVING,
    LIVELY,
    WALTZ,
    Cue,
    _colour,
    _loop,
    _snap,
    bass_note,
    color_melody,
    open_voicing,
)
from .score import SCALES

MARCH = [(0, 0.8), (0.75, 0.35), (1, 0.6), (1.5, 0.4), (1.75, 0.35), (2, 0.75), (2.75, 0.35), (3, 0.6), (3.5, 0.45)]
PALETTES_FOR = {"dorian": ["dorian", "aeolian"], "harmonic": ["aeolian", "chromatic"],
                "phrygian": ["chromatic", "half_step"], "minor": ["aeolian", "dorian"],
                "mixolydian": ["mixolydian", "heroic"], "lydian": ["lydian", "mediant"], "major": ["heroic", "lydian"]}


def _snare(c: Cue, b: float, roll: bool = False, soft: float = 1.0):
    """A march figure on the snare; `roll`: the last beat becomes a crescendo roll into the next phrase."""
    hits = [(60, b + x, 0.25, g * soft) for x, g in MARCH if not (roll and x >= 3)]
    if roll:
        hits += [(60, b + 3 + k / 8, 0.125, (0.3 + 0.08 * k) * soft) for k in range(8)]
    c.part("snare", hits)


def _ostinato(c: Cue, role: str, root: int, scale: set, b: float, pattern: list, vel: float = 0.6, step: float = 0.25):
    """Strings driving a figure on the chord's root: its 5th, octave and the mode's own neighbour (the b6 of Aeolian
    and Phrygian, the 6 of Dorian), in sixteenths (or `step`)."""
    nb = _snap(root + 8, scale)
    notes = {"r": root, "5": root + 7, "8": root + 12, "n": nb}
    n = int(4 / step)
    c.part(role, [(notes[pattern[j % len(pattern)]], b + step * j, step * 0.9, vel + 0.2 * (j % 4 == 0))
                  for j in range(n)], 0.6)


def _pcs(tonic: int, mode: str) -> set:
    return {(tonic + i) % 12 for i in SCALES[mode]}


def skirmish(c: Cue):
    """A tactics battle: strings racing in a sixteenth-note ostinato, a march snare rolling into each phrase, timpani
    and a low bass, horns holding the harmony; the brass carries the tune, then the flute, leaping like Sakimoto's."""
    c.new_score(bpm=136 + 26 * c.r.u(), hall=2.0)
    mode = c.r.pick(["dorian", "harmonic", "phrygian", "minor"])
    tonic, chords = _colour(c, mode, PALETTES_FOR[mode], bars=32)
    scale = _pcs(tonic, mode)
    pattern = c.r.pick([list("r5858n85"), list("r8585n58"), list("rr5rnr5r"), list("r585r5n5")])
    prev = None
    for bar, ch in enumerate(chords):
        b = 4 * bar
        v = open_voicing(tonic, ch, prev)
        prev = v
        root = bass_note(tonic, ch, 33)
        _ostinato(c, "strings", root + 12, scale, b, pattern)
        c.part("low_strings", [(root, b, 0.5, 0.9), (root, b + 1.5, 0.5, 0.7), (root, b + 2.5, 1.5, 0.8)])
        c.part("horns", [(v, b, 4)], 0.5)
        c.part("timpani", [(bass_note(tonic, ch, 41), b, 0.5, 0.85), (bass_note(tonic, ch, 41), b + 2.5, 0.5, 0.6)])
        _snare(c, b, roll=bar % 4 == 3)
        c.part("kick", [(36, b, 0.5, 0.7), (36, b + 2, 0.5, 0.55)])
        if bar % 8 == 0:
            c.part("crash", [(60, b, 2, 0.65)])
    tune = color_melody(c.r, tonic + 12, mode, chords[:16], DRIVING + LIVELY[:2], low=62, high=84, color=0.15,
                        leap=0.3)
    c.part("brass", tune, 0.85)
    c.part("lead", [(n + 12, b + 64, ln) for n, b, ln in color_melody(c.r, tonic + 12, mode, chords[16:], LIVELY,
                                                                       low=62, high=84, color=0.2, leap=0.25)], 0.75)
    c.part("brass", [(n - 12, b + 64, ln, 0.5) for n, b, ln in tune[::2]], 0.5)       # the brass answers below
    _loop(c, len(chords))


def tense(c: Cue):
    """A standoff: Phrygian, the low strings pulsing on the tonic with the flat second leaning on it, the violins
    trembling on a note that creeps up a half step every two bars, a timpani heartbeat, brass stabs; no tune."""
    c.new_score(bpm=104 + 18 * c.r.u(), hall=2.2)
    tonic = 50 + int(c.r.u() * 8)
    chords = [(0, "m"), (0, "m"), (1, ""), (0, "m")] * 2 + [(0, "m"), (8, ""), (1, ""), (7, "7sus4")] * 2
    for bar, ch in enumerate(chords):
        b = 4 * bar
        root = bass_note(tonic, ch, 33)
        c.part("low_strings", [(root + (1 if j == 7 else 0), b + 0.5 * j, 0.45, 0.85 if j % 4 == 0 else 0.6)
                               for j in range(8)])
        top = tonic + 12 + (bar // 2) % 8                        # creeping up: the tension builds
        c.part("strings", [(top, b + 0.125 * j, 0.12, 0.35 + 0.2 * (bar % 8) / 7) for j in range(32)], 0.45)
        c.part("timpani", [(bass_note(tonic, (0, ""), 41), b, 0.5, 0.75), (bass_note(tonic, (0, ""), 41), b + 0.6, 0.5,
                                                                            0.5)])
        if bar % 2 == 1:
            c.part("horns", [(open_voicing(tonic, ch), b + 2.5, 0.4, 0.8)])
        if bar % 8 == 7:
            c.part("snare", [(60, b + k / 8, 0.125, 0.15 + 0.6 * k / 32) for k in range(32)])
        if ch[0] in (1, 8):
            c.part("choir", [(open_voicing(tonic, ch), b, 4)], 0.35)
    _loop(c, len(chords))


def boss(c: Cue):
    """A boss: harmonic minor or Phrygian at 152-174 bpm, a choir chanting the chords, brass stabs and a tune full of
    leaps (FFTA2's darkest leaps on over half its notes), the bass walking down by half steps, drums on every beat,
    strings racing in sixteenths."""
    c.new_score(bpm=152 + 22 * c.r.u(), hall=1.9)
    mode = c.r.pick(["harmonic", "phrygian"])
    tonic, chords = _colour(c, mode, ["chromatic", "half_step"], bars=32)
    prev = None
    for bar, ch in enumerate(chords):
        b = 4 * bar
        v = open_voicing(tonic, ch, prev)
        prev = v
        root = bass_note(tonic, ch, 33)
        notes = sorted(v)
        c.part("strings", [(notes[(j * 2 + j // 4) % len(notes)] + 12, b + 0.25 * j, 0.22, 0.55) for j in range(16)],
               0.55)
        c.part("choir", [(v, b, 1.5, 0.85), (v, b + 2, 1.5, 0.75)], 0.6)
        c.part("low_strings", [(root - k * (bar % 2), b + k, 1, 0.85) for k in range(4)])     # walking down
        c.part("horns", [(v, b + 1.5, 0.4, 0.9), (v, b + 3.5, 0.4, 0.8)])
        c.part("kick", [(36, b + k, 0.5, 0.8) for k in range(4)])
        c.part("snare", [(60, b + 1, 0.5, 0.8), (60, b + 3, 0.5, 0.85)] +
               ([(60, b + 3 + k / 4, 0.25, 0.5 + 0.1 * k) for k in range(4)] if bar % 4 == 3 else []))
        c.part("timpani", [(bass_note(tonic, ch, 41), b, 0.5, 0.9), (bass_note(tonic, ch, 41), b + 2, 0.5, 0.75)])
        if bar % 4 == 0:
            c.part("crash", [(60, b, 2, 0.75)])
    c.part("brass", color_melody(c.r, tonic + 12, mode, chords, DRIVING, low=60, high=84, color=0.1, leap=0.5), 0.9)
    _loop(c, len(chords))


def final(c: Cue):
    """The last battle: harmonic minor, 120-140 bpm, the full orchestra and choir: the choir sings the tune in long
    notes and the brass answers it, the strings turn in triplets, timpani rolls end each phrase, a gong opens every
    eight bars; the second half climbs a whole step."""
    c.new_score(bpm=120 + 20 * c.r.u(), hall=2.6)
    tonic, half = _colour(c, "harmonic", ["aeolian", "chromatic"], bars=16)
    prev = None
    for lift, chords in ((0, half), (2, half)):
        t = tonic + lift
        start = 16 * (lift // 2)
        for i, ch in enumerate(chords):
            bar = start + i
            b = 4 * bar
            v = open_voicing(t, ch, prev)
            prev = v
            root = bass_note(t, ch, 31)
            notes = sorted(v)
            c.part("strings", [(notes[j % len(notes)] + 12 * (j % 6 >= 3), b + j / 3, 0.3, 0.5) for j in range(12)],
                   0.55)
            c.part("low_strings", [(root, b, 4)], 0.75)
            c.part("horns", [(v, b, 2), (v, b + 2, 2)], 0.6)
            c.part("kick", [(36, b, 1, 0.75), (36, b + 2, 1, 0.6)])
            if i % 4 == 3:
                c.part("timpani", [(bass_note(t, ch, 41), b + 2 + k / 8, 0.125, 0.4 + 0.03 * k) for k in range(16)])
            else:
                c.part("timpani", [(bass_note(t, ch, 41), b, 1, 0.85)])
            if i % 8 == 0:
                c.part("gong", [(48, b, 8, 0.7)])
                c.part("crash", [(60, b, 2, 0.6)])
        tune = color_melody(c.r, t + 12, "harmonic", chords, CALM[:4], low=60, high=79, color=0.2, leap=0.2)
        c.part("choir", [(n, b + 4 * start, ln) for n, b, ln in tune], 0.7)
        c.part("brass", [(n, b + 4 * start + 2, max(ln - 1, 0.5), 0.6) for n, b, ln in tune[1::3]], 0.75)
    _loop(c, 32)


def prepare(c: Cue):
    """Getting ready (the formation, choosing who goes): a steady march at 104-118 bpm in Mixolydian or Dorian, a
    snare cadence and the bass drum, low strings in dotted rhythm, the harp on the chords, horns with a calm tune."""
    c.new_score(bpm=104 + 14 * c.r.u(), hall=2.0)
    mode = c.r.pick(["mixolydian", "dorian"])
    tonic, chords = _colour(c, mode, PALETTES_FOR[mode])
    prev = None
    for bar, ch in enumerate(chords):
        b = 4 * bar
        v = open_voicing(tonic, ch, prev)
        prev = v
        root = bass_note(tonic, ch, 33)
        c.part("low_strings", [(root, b, 0.75, 0.8), (root, b + 0.75, 0.25, 0.5), (root + 7, b + 1, 1, 0.65),
                               (root, b + 2, 0.75, 0.8), (root, b + 2.75, 0.25, 0.5), (root + 12, b + 3, 1, 0.6)])
        c.part("arp", [(n, b + 0.5 * j, 1.0) for j, n in enumerate(sorted(v) + sorted(v)[::-1])], 0.45)
        c.part("pad", [(v, b, 4)], 0.35)
        _snare(c, b, roll=bar % 8 == 7, soft=0.6)
        c.part("kick", [(36, b, 0.5, 0.6), (36, b + 2, 0.5, 0.5)])
    c.part("horns", color_melody(c.r, tonic + 12, mode, chords, CALM + LIVELY[:2], low=55, high=74, color=0.2,
                                 leap=0.1), 0.75)
    _loop(c, len(chords))


def briefing(c: Cue):
    """The map and the plan: thoughtful, 84-98 bpm, Dorian or minor: a pizzicato bass walking in quarters, the harp
    and strings holding open chords, a low flute tune, now and then a soft snare on the backbeat."""
    c.new_score(bpm=84 + 14 * c.r.u(), hall=2.2)
    mode = c.r.pick(["dorian", "minor"])
    tonic, chords = _colour(c, mode, PALETTES_FOR[mode])
    scale = _pcs(tonic, mode)
    prev = None
    for bar, ch in enumerate(chords):
        b = 4 * bar
        v = open_voicing(tonic, ch, prev)
        prev = v
        root = bass_note(tonic, ch, 33)
        walk = [root, _snap(root + 3, scale), root + 7, _snap(root + 10, scale)]
        c.part("bass", [(n, b + k, 0.9, 0.75) for k, n in enumerate(walk)])
        c.part("pad", [(v, b, 4)], 0.4)
        c.part("arp", [(n, b + 0.75 * j, 1.5) for j, n in enumerate(sorted(v))], 0.4)
        if bar % 4 in (1, 3):
            c.part("snare", [(60, b + 1, 0.25, 0.25), (60, b + 3, 0.25, 0.3)])
    c.part("lead", color_melody(c.r, tonic, mode, chords, CALM, low=60, high=77, color=0.3, leap=0.15), 0.6)
    _loop(c, len(chords))


def worldmap(c: Cue):
    """The world map: a journey at 104-124 bpm in Lydian or Mixolydian (FFTA2's travelling pieces): horns carry a broad
    tune with leaps, strings run in eighths, the harp, a light snare, timpani on the downbeats."""
    c.new_score(bpm=104 + 20 * c.r.u(), hall=2.3)
    mode = c.r.pick(["lydian", "mixolydian"])
    tonic, chords = _colour(c, mode, PALETTES_FOR[mode], bars=32)
    prev = None
    for bar, ch in enumerate(chords):
        b = 4 * bar
        v = open_voicing(tonic, ch, prev)
        prev = v
        root = bass_note(tonic, ch, 33)
        notes = sorted(v)
        c.part("strings", [(notes[j % len(notes)] + (12 if j >= 4 else 0), b + 0.5 * j, 0.45, 0.5) for j in range(8)],
               0.5)
        c.part("low_strings", [(root, b, 2), (root + 7, b + 2, 2)], 0.6)
        c.part("arp", [(notes[j % len(notes)] + 12 * (j >= 4), b + 0.5 * j, 1.0) for j in range(8)], 0.4)
        c.part("timpani", [(bass_note(tonic, ch, 41), b, 1, 0.6)])
        c.part("snare", [(60, b + x, 0.25, g) for x, g in ((1, 0.3), (2.5, 0.25), (3, 0.35), (3.5, 0.25))])
        if bar % 8 == 0:
            c.part("crash", [(60, b, 2, 0.45)])
    c.part("horns", color_melody(c.r, tonic + 12, mode, chords[:16], CALM + LIVELY[:2], low=55, high=77, color=0.25,
                                 leap=0.3), 0.8)
    c.part("lead", [(n + 12, b + 64, ln) for n, b, ln in
                    color_melody(c.r, tonic + 12, mode, chords[16:], CALM + LIVELY[:3], low=62, high=84, color=0.3,
                                 leap=0.25)], 0.65)
    _loop(c, len(chords))


def sorrow(c: Cue):
    """Grief: 56-68 bpm, minor (FFTA2's slowest pieces): the strings sing over the harp's slow arpeggios and held low
    strings, the choir comes in for the second half; no drums."""
    c.new_score(bpm=56 + 12 * c.r.u(), hall=2.8)
    tonic, chords = _colour(c, "minor", ["aeolian"])
    prev = None
    for bar, ch in enumerate(chords):
        b = 4 * bar
        v = open_voicing(tonic, ch, prev)
        prev = v
        root = bass_note(tonic, ch, 33)
        arp = [root + 12] + sorted(v)
        c.part("arp", [(arp[j % len(arp)], b + 0.5 * j, 2.0) for j in range(8)], 0.45)
        c.part("low_strings", [(root, b, 4)], 0.5)
        if bar >= 8:
            c.part("choir", [(v, b, 4)], 0.35)
    c.part("strings", color_melody(c.r, tonic + 12, "minor", chords, CALM[:3], low=62, high=82, color=0.3,
                                   leap=0.1), 0.65)
    _loop(c, len(chords))


def intrigue(c: Cue):
    """Scheming: 72-88 bpm, Phrygian or harmonic minor: a creeping pizzicato figure (tonic, flat second, fifth), a low
    flute in short phrases, held cellos, a soft hand drum, the harp's high notes like a held breath."""
    c.new_score(bpm=72 + 16 * c.r.u(), hall=2.2)
    mode = c.r.pick(["phrygian", "harmonic"])
    tonic = 52 + int(c.r.u() * 9)
    chords = [(0, "m"), (1, "maj7"), (0, "m"), (7, "7sus4")] * 2 + [(0, "m7"), (8, "maj7"), (1, "maj7"), (0, "m")] * 2
    for bar, ch in enumerate(chords):
        b = 4 * bar
        root = bass_note(tonic, ch, 34)
        c.part("bass", [(n, b + x, 0.4, g) for n, x, g in ((root, 0, 0.8), (root + 1, 0.75, 0.5), (root, 1.5, 0.6),
                                                              (root + 7, 2.5, 0.6), (root + 6, 3.25, 0.5))])
        c.part("low_strings", [(root - 12, b, 4)], 0.45)
        c.part("strings", [(root + 12 + (1 if j % 4 == 3 else 0), b + 0.25 * j, 0.2, 0.25 + 0.1 * (j % 4 == 0))
                           for j in range(16)], 0.35)                    # a whisper of sixteenths, leaning on b2
        c.part("hand_drum", [(57, b, 0.5, 0.5), (64, b + 2.5, 0.5, 0.35)])
        if bar % 2 == 1:
            c.part("arp", [(tonic + 24 + (6 if bar % 4 == 3 else 7), b + 3, 1, 0.4)])         # a tritone, then the 5th
    c.part("lead", [(n, b, ln) for n, b, ln in color_melody(c.r, tonic, mode, chords, CALM[:2] + [[(0, 3), (3, 1)]],
                                                            low=58, high=74, color=0.2, leap=0.2) if (b // 8) % 2 == 0],
           0.55)
    _loop(c, len(chords))


def triumph(c: Cue):
    """A triumph (a town freed, a war won): 96-112 bpm, major or Lydian, a brass chorale over the strings, snare and
    timpani in a slow march, bells and harp on top, a cymbal at each phrase."""
    c.new_score(bpm=96 + 16 * c.r.u(), hall=2.4)
    mode = c.r.pick(["major", "lydian"])
    tonic, chords = _colour(c, mode, PALETTES_FOR[mode])
    prev = None
    for bar, ch in enumerate(chords):
        b = 4 * bar
        v = open_voicing(tonic, ch, prev)
        prev = v
        root = bass_note(tonic, ch, 33)
        c.part("horns", [(v, b, 2), (v, b + 2, 2)], 0.6)
        c.part("strings", [(sorted(v)[j % len(v)] + 12, b + 0.5 * j, 0.45, 0.45) for j in range(8)], 0.45)
        c.part("low_strings", [(root, b, 4)], 0.65)
        c.part("timpani", [(bass_note(tonic, ch, 41), b, 1, 0.7), (bass_note(tonic, ch, 41), b + 3, 1, 0.5)])
        _snare(c, b, roll=bar % 4 == 3, soft=0.55)
        if bar % 4 == 0:
            c.part("crash", [(60, b, 2, 0.5)])
            c.part("bells", [(n + 12, b + 0.25 * j, 1.0) for j, n in enumerate(sorted(v))], 0.4)
    c.part("brass", color_melody(c.r, tonic + 12, mode, chords, CALM, low=60, high=81, color=0.15, leap=0.25), 0.85)
    _loop(c, len(chords))


def comedy(c: Cue):
    """A comic scene: 120-140 bpm, major, oom-pah (the pizzicato bass on the beat, the harp off it), a staccato
    marimba tune that slides in half steps, the flute answering, a log drum and a tambourine, a hold before the
    punchline at the end of each phrase."""
    c.new_score(bpm=120 + 20 * c.r.u(), hall=1.6)
    key_t = 55 + int(c.r.u() * 12)
    chords = [(0, ""), (7, "7"), (7, "7"), (0, ""), (5, ""), (0, ""), (7, "7"), (0, "")] * 2
    for bar, ch in enumerate(chords):
        b = 4 * bar
        v = open_voicing(key_t, ch)
        root = bass_note(key_t, ch, 36)
        held = bar % 8 == 6                                    # the hold before the punchline
        if not held:
            c.part("bass", [(root, b, 0.5, 0.8), (root + 7 - 12 * (root + 7 > 52), b + 2, 0.5, 0.7)])
            c.part("arp", [(v, b + 1, 0.4, 0.55), (v, b + 3, 0.4, 0.5)])
            c.part("block", [(72, b + x, 0.25, g) for x, g in ((0, 0.7), (1.5, 0.5), (2, 0.7), (3.5, 0.6))])
        else:
            c.part("pad", [(v, b, 2)], 0.4)
        if bar % 4 == 3:
            c.part("tambourine", [(70, b + 3, 1, 0.7)])
    tune = color_melody(c.r, key_t + 12, "major", chords, LIVELY + WALTZ[:1], low=62, high=84, color=0.1, leap=0.2)
    tune = [(n, b, min(ln, 0.5)) for n, b, ln in tune if (b // 4) % 8 != 6]
    c.part("mallet", [(n - 1, b - 0.125, 0.12, 0.4) for n, b, ln in tune[::4] if b >= 0.125] + tune, 0.7)
    c.part("lead", [(n + 12, b + 2, 0.4) for n, b, ln in tune[2::5]], 0.5)
    _loop(c, len(chords))


def recruit(c: Cue):
    """Someone joins the party: horns rise over a held major chord, the harp rolls up, a triangle and the bells."""
    c.new_score(bpm=96 + 16 * c.r.u(), hall=2.4)
    key = c.key("major")
    line = c.r.pick([[0, 2, 4, 7], [4, 5, 7, 9], [0, 4, 7, 11]])
    c.part("horns", [(key.note(d), j * 0.75, 0.75 if j < 3 else 3) for j, d in enumerate(line)], 0.8)
    chord = [key.note(t) for t in (0, 2, 4)]
    c.part("strings", [(chord, 0, 5)], 0.5)
    c.part("low_strings", [(key.note(-14), 0, 5)], 0.6)
    c.part("arp", [(key.note(d), 2.25 + 0.08 * j, 2.5) for j, d in enumerate(range(0, 12))], 0.5)
    c.part("triangle", [(84, 2.25, 2)], 0.5)
    c.part("bells", [(key.note(d) + 12, 2.25 + 0.25 * j, 0.5) for j, d in enumerate((0, 4, 7))], 0.45)
    c.end = c.score.beats(5.25)


TACTICS_CUES = ("skirmish", "tense", "boss", "final", "prepare", "briefing", "worldmap", "sorrow", "intrigue",
                "triumph", "comedy", "recruit")
CUES.update({name: globals()[name] for name in TACTICS_CUES})
