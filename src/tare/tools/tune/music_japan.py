"""Japanese music: a shrine, a village, a festival, a battle dance (kagura), an elegy.

The ruler is Utawarerumono's best-loved tracks, measured on the user's own copies (numbers only, no melody): from 63
to 162 bpm by mood; warm (the spectrum's centre at 260-650 Hz) and level (1.6-8 dB between loud and quiet); the sacred
pieces with almost no pulse, the festival and the kagura beating hard. And the language of the music itself:

    the scales   in (miyako-bushi: 0 1 5 7 8, the koto's solemn one, its half step falling to the tonic),
                 yo (0 2 5 7 9, the folk songs'), ryukyu (0 4 5 7 11, the southern islands')
    ma           space: each phrase ends on a long note and a breath before the next
    heterophony  the koto plays the shakuhachi's tune with it, plucked, ornamented and an octave down, not in harmony
    the drums    the festival's don-don-doko on the taiko, the hyoshigi clapping, the rin opening a sacred piece

The instruments (koto, shakuhachi, taiko, hyoshigi, rin) are measured (instruments.py); Utawarerumono blends them with
the orchestra, so the strings, the choir and the low strings carry the harmony underneath in open fifths and fourths.
"""
from .music import CUES, Cue, Rand, _loop
from .score import SCALES

SCALES_JP = {name: SCALES[name] for name in ("in", "yo", "ryukyu")}
PHRASES = [   # two bars of four beats: the notes, the held end, then the breath (ma)
    [(0, 1), (1, 1), (2, 2), (4, 1), (5, 2.5)],
    [(0, 1.5), (1.5, 0.5), (2, 1), (3, 1), (4, 3)],
    [(0, 2), (2, 1), (3, 1), (4, 3)],
    [(0, 0.5), (0.5, 0.5), (1, 1), (2, 2), (4, 1), (5, 2.5)],
    [(0, 1), (1, 0.5), (1.5, 0.5), (2, 1.5), (4, 3.5)],
]
SLOW = [      # the sacred and the sad: fewer, longer notes
    [(0, 3), (3, 1), (4, 3.5)],
    [(0, 2), (2, 2), (4, 3)],
    [(0, 4), (4, 1), (5, 2.5)],
]


def pentatonic(r: Rand, tonic: int, scale: tuple, bars: int, rhythms: list, low: int = 62, high: int = 86) -> list:
    """(midi, beat, beats). Phrases of two bars, each ending on a long note followed by a breath; mostly steps between
    neighbouring notes of the scale, now and then a leap; each phrase rises then falls; the first of a pair ends on the
    5th or the 4th (a question), the second on the tonic (the answer)."""
    notes = sorted(n for n in range(low, high + 1) if (n - tonic) % 12 in scale)
    i = min(range(len(notes)), key=lambda k: abs(notes[k] - (tonic + 12)))
    out = []
    for p in range(bars // 2):
        rhythm = r.pick(rhythms)
        for j, (b, ln) in enumerate(rhythm):
            if j == len(rhythm) - 1:                      # the phrase's end: the tonic, or a 5th / 4th
                goal = {0} if p % 2 else {7, 5}
                i = min((k for k in range(len(notes)) if (notes[k] - tonic) % 12 in goal), key=lambda k: abs(k - i))
            else:
                up = 1 if j < len(rhythm) / 2 else -1
                if r.u() < 0.25:
                    up = -up
                i += up * (1 if r.u() < 0.7 else 2 if r.u() < 0.7 else 3)
                i = min(max(i, 0), len(notes) - 1)
            out.append((notes[i], 8 * p + b, ln))
    return out


def _open(tonic: int, step: int, low: int = 48) -> list[int]:
    """An open chord on a scale note: root, 5th, octave (and the 4th above for colour), no third."""
    root = low + (tonic + step - low) % 12
    return [root, root + 7, root + 12, root + 17]


def _heterophony(c: Cue, tune: list, vel: float = 0.6):
    """The koto with the shakuhachi: the same tune an octave down, plucked; a long note gets its octave plucked again
    half a beat later (the koto keeps a held note alive)."""
    notes = []
    for n, b, ln in tune:
        notes.append((n - 12, b, ln, vel))
        if ln >= 1.5:
            notes.append((n - 24, b + 0.5, ln - 0.5, vel * 0.7))
    c.part("koto", notes)


def _key(c: Cue) -> int:
    return 57 + int(c.r.u() * 9)                         # A3..F4: the koto's and the shakuhachi's comfortable middle


def _forward(c: Cue, role: str, gain: float):
    """A track louder in this cue than the style's default (the drums of a festival, the low end of a mix)."""
    inst, _, pan, send, voice, *echo = c.roles[role]
    c.score.track(role, gain, pan, send, echo[0] if echo else 0.0, **voice)


def _warm(c: Cue):
    """Utawarerumono's mix: warm, its spectrum centred at 260-650 Hz because the low end is strong (63-250 Hz within
    ~9 dB of the loudest band): the low strings and the bass well forward."""
    for role in ("low_strings", "bass"):
        _forward(c, role, 1.1)


def shrine(c: Cue):
    """A shrine or a sacred moment: the in scale at 66-80 bpm with almost no pulse; the rin opens each half, the
    shakuhachi sings long notes with space around them, the koto answers in open fifths, a low drone of strings, a far
    taiko stroke now and then, the choir in the second half."""
    c.new_score(bpm=66 + 14 * c.r.u(), hall=2.8)
    _warm(c)
    t = _key(c)
    scale = SCALES_JP["in"]
    tune = pentatonic(c.r, t, scale, 16, SLOW, low=64, high=86)
    c.part("shakuhachi", tune, 0.7)
    for bar in range(16):
        b = 4 * bar
        if bar % 8 == 0:
            c.part("rin", [(t + 24, b, 4, 0.7)])
        c.part("low_strings", [([t - 24, t - 17, t - 12], b, 4)], 0.7)
        if bar % 2 == 1:
            c.part("koto", [(n, b + 0.4 * k, 2, 0.5) for k, n in enumerate(_open(t, (0, 7)[bar // 4 % 2], 50)[:3])])
        if bar % 4 == 2:
            c.part("taiko", [(41, b, 2, 0.5)])
        if bar >= 8:
            c.part("choir", [(_open(t, 0, 55)[:3], b, 4)], 0.3)
    _loop(c, 16)


def village(c: Cue):
    """A village, an evening, friends: the yo scale at 88-112 bpm; the koto turning a figure in eighths, the
    shakuhachi's tune over it (the koto joins in heterophony in the second half), a warm string pad in fourths and
    fifths, a pizzicato bass on the tonic and the 5th, a hand drum on every beat and a shaker in eighths."""
    c.new_score(bpm=88 + 24 * c.r.u(), hall=1.8)
    _warm(c)
    _forward(c, "hand_drum", 0.9)                        # a clear pulse, as in Utawarerumono's everyday tracks
    _forward(c, "shakuhachi", 0.3)                       # (0.81-0.83): the tune over the village, not in front of it
    t = _key(c)
    scale = SCALES_JP["yo"]
    figure = c.r.pick([[0, 7, 12, 14, 12, 7, 9, 7], [0, 5, 7, 12, 9, 7, 5, 7], [0, 7, 9, 12, 14, 12, 9, 7]])
    for bar in range(16):
        b = 4 * bar
        root = (0, 0, 5, 7)[bar % 4] if bar < 8 else (5, 0, 7, 0)[bar % 4]
        c.part("koto", [(t - 12 + root + figure[j], b + 0.5 * j, 0.6, 0.3 + 0.15 * (j % 2 == 0) + 0.1 * (j == 0))
                        for j in range(8)])
        c.part("pad", [(_open(t, root, 48)[:3], b, 4)], 0.5)
        c.part("low_strings", [(t - 24 + root, b, 4)], 0.55)
        c.part("bass", [(t - 24 + root, b, 1, 0.8), (t - 24 + root + 7, b + 2, 1, 0.7)])
        c.part("hand_drum", [(57, b, 0.5, 0.7), (64, b + 1, 0.5, 0.4), (57, b + 2, 0.5, 0.55), (64, b + 3, 0.5, 0.4),
                             (64, b + 3.5, 0.5, 0.3)])
        c.part("shaker", [(70, b + 0.5 * j, 0.25, 0.5 + 0.2 * (j % 2)) for j in range(8)])
    tune = pentatonic(c.r, t, scale, 16, PHRASES, low=62, high=84)
    c.part("shakuhachi", tune, 0.7)
    _heterophony(c, [x for x in tune if x[1] >= 32], 0.4)
    _loop(c, 16)


def festival(c: Cue):
    """A festival (matsuri): the yo scale at 118-144 bpm; the taiko's don-don-doko, the hyoshigi clapping the
    off-beats, the koto in a running sixteenth-note figure, the shakuhachi up high where a festival flute would be, a
    bass on the tonic."""
    c.new_score(bpm=118 + 26 * c.r.u(), hall=1.8)
    _warm(c)
    _forward(c, "taiko", 1.6)                            # the pulse is the drums (Utawarerumono: 0.6-0.7)
    _forward(c, "hyoshigi", 0.7)
    _forward(c, "shakuhachi", 0.3)                       # the flute high over the drums, not in front of them
    t = _key(c)
    scale = SCALES_JP["yo"]
    run = c.r.pick([[0, 2, 7, 9, 12, 9, 7, 2], [0, 7, 9, 12, 14, 12, 9, 7], [0, 5, 7, 9, 12, 9, 7, 5]])
    for bar in range(16):
        b = 4 * bar
        c.part("taiko", [(41, b, 0.5, 1.0), (41, b + 1, 0.5, 0.85), (41, b + 2, 0.25, 0.7), (41, b + 2.5, 0.25, 0.65),
                         (41, b + 3, 0.5, 0.9)] + ([(41, b + 3.5 + k / 8, 0.125, 0.5 + 0.1 * k) for k in range(4)]
                                                    if bar % 4 == 3 else []))
        c.part("hyoshigi", [(88, b + x, 0.25, 0.6) for x in (0.5, 1.5, 2.5, 3.5)])
        c.part("koto", [(t - 12 + run[j % 8], b + 0.25 * j, 0.3, 0.3 + 0.12 * (j % 4 == 0)) for j in range(16)])
        c.part("bass", [(t - 24, b, 1, 0.9), (t - 17, b + 2, 1, 0.75)])
        c.part("low_strings", [([t - 24, t - 17], b, 4)], 0.5)
    c.part("shakuhachi", [(n + 12, b, ln, 0.8) for n, b, ln in pentatonic(c.r, t, scale, 16, PHRASES, 62, 81)])
    _loop(c, 16)


def kagura(c: Cue):
    """A battle danced like a kagura: the in scale at 126-160 bpm; the taiko driving in eighths with rolls into each
    phrase, the low strings pulsing on the tonic with the half step above leaning on it, horns stabbing open fifths,
    the shakuhachi fierce (its breath bursting), the koto in tremolo bursts, the choir and a gong in the second half."""
    c.new_score(bpm=126 + 34 * c.r.u(), hall=2.2)
    _warm(c)
    _forward(c, "taiko", 1.6)
    t = _key(c)
    scale = SCALES_JP["in"]
    for bar in range(32):
        b = 4 * bar
        root = (0, 0, 8, 7)[bar % 4]
        low = t - 24 + root
        c.part("low_strings", [(low + (1 if j == 7 else 0), b + 0.5 * j, 0.45, 0.85 if j % 4 == 0 else 0.6)
                               for j in range(8)])
        c.part("taiko", [(41, b + 0.5 * j, 0.5, (1.0, 0.45, 0.7, 0.45, 0.9, 0.45, 0.75, 0.55)[j]) for j in range(8)]
               + ([(41, b + 3 + k / 8, 0.125, 0.4 + 0.07 * k) for k in range(8)] if bar % 4 == 3 else []))
        if bar % 2 == 0:
            c.part("horns", [(_open(t, root, 50)[:3], b + 1.5, 0.5, 0.85), (_open(t, root, 50)[:3], b + 3.5, 0.4, 0.8)])
        if bar % 4 == 1:
            c.part("koto", [(t + root + (0, 12)[k % 2], b + 2 + k / 8, 0.12, 0.5) for k in range(12)])   # tremolo
        if bar >= 16:
            c.part("choir", [(_open(t, root, 52)[:3], b, 4)], 0.4)
            if bar % 8 == 0:
                c.part("gong", [(48, b, 8, 0.6)])
    c.part("shakuhachi", [(n, b, ln, 0.9) for n, b, ln in pentatonic(c.r, t, scale, 32, PHRASES, 64, 86)])
    _loop(c, 32)


def elegy(c: Cue):
    """A lament: the in scale at 60-76 bpm; the koto alone with the tune (its long notes trembling), the strings
    holding open chords underneath, the shakuhachi answering in the second half, the rin to close."""
    c.new_score(bpm=60 + 16 * c.r.u(), hall=2.8)
    _warm(c)
    t = _key(c)
    scale = SCALES_JP["in"]
    tune = pentatonic(c.r, t, scale, 16, SLOW + PHRASES[:2], low=57, high=79)
    c.part("koto", [(n, b, ln, 0.5) for n, b, ln in tune if b < 32])
    c.part("shakuhachi", [(n, b, ln, 0.65) for n, b, ln in tune if b >= 32])   # a long flute (2.4), down to A3
    _heterophony(c, [x for x in tune if x[1] >= 32], 0.35)
    for bar in range(16):
        root = (0, 8, 5, 0)[bar % 4]
        swell = 0.6 if bar < 8 else 1.0                      # the koto's half intimate (laments: 7.6-13 dB)
        c.part("strings", [(_open(t, root, 48)[:3], 4 * bar, 4)], 0.65 * swell)
        c.part("low_strings", [(t - 24 + root, 4 * bar, 4)], 0.7 * swell)
    c.part("rin", [(t + 24, 60, 4, 0.6)])
    _loop(c, 16)


JAPAN_CUES = ("shrine", "village", "festival", "kagura", "elegy")
CUES.update({name: globals()[name] for name in JAPAN_CUES})
