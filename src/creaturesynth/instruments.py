"""Instruments for scores: each one turns a Note (start, dur, Hz, velocity, seed) into spec layers.

Measured on single notes of the VSCO-2 Community Edition orchestra (CC0, analysis only): the partials of each
instrument as ratios to the note, their levels and decay times, and how both change across the range.

    struck bars   glockenspiel (free bar: 1, 2.9, 5.5, 9.0), marimba (tuned 1 : 4 : 10), xylophone (1 : 3)
    bells         tubular bells (beam modes; the strike note is an octave under the 4th-6th modes, 2 : 3 : 4)
    plucked       harp (harmonic; the low strings ring 7 s and are rich, the top ones nearly pure), pizzicato
    drums         timpani (the pitched mode with 1.5 / 2 / 2.44 over it), hand drums, concert bass drum, snare
    metals        triangle, crash cymbal, gong, tambourine
"""
import numpy as np

from .score import Note
from .spec import Modal, Noise, Scatter, Syllable


def _db(x: float) -> float:
    return 10 ** (x / 20)


def _modes(n: Note, partials, cap: float = 8.0, spread: float = 0.002):
    """(ratio, dB, T60) -> Modal modes at the note, each slightly detuned per note (no two strikes alike)."""
    out = []
    for i, (r, db, t60) in enumerate(partials):
        f = n.f * r * (1 + spread * (n.rand(f"d{i}") - 0.5))
        if 20 < f < 18_000:
            out.append((round(f, 2), round(min(t60, cap), 3), round(_db(db), 5)))
    return out


def _ring(n: Note, partials, hardness: float, click: float, contact: float, cap: float = 8.0, gain: float = 1.0,
          dur: float | None = None, spread: float = 0.002) -> Modal:
    modes = _modes(n, partials, cap, spread)
    ring = dur or min(max(t for _, t, _ in modes), cap)
    return Modal(round(n.start, 4), round(ring + 0.05, 3), modes, [(0.0, 1.0, contact)],
                 hardness=round(hardness * (0.35 + 0.8 * n.vel), 1), click=click, gain=round(gain * n.vel, 4))


def _soft(f: float, cut: float, order: float = 4) -> float:
    """A mallet or a body losing the highs: dB at frequency f for a corner at `cut`."""
    return -10 * np.log10(1 + (f / cut) ** order)


# -- struck bars ------------------------------------------------------------------------------------------------------

def glockenspiel(n: Note) -> list:
    """Steel bars: the note rings 9 s at G5, ~2 s at C8; the overtones (2.9, 5.5, 9.0) die within a second."""
    t1 = min(9.0 * (785 / n.f) ** 0.8, 10.0)
    return [_ring(n, [(1, 0, t1), (2.9, -3, 0.8), (5.5, -10, 0.5), (9.0, -12, 0.6)], 16_000, 0.04, 0.0, cap=8.0)]


def marimba(n: Note) -> list:
    """Rosewood bars tuned 1 : 4 : 10 over resonator tubes: 8.6 s of ring at C3, 0.5 s at C7; the yarn mallet loses
    everything above ~2 kHz (softer when played gently)."""
    cut = 2000 * (0.6 + 0.5 * n.vel)
    t1 = min(max(8.6 * 129 / n.f, 0.4), 9.0)
    return [_ring(n, [(1, 0, t1), (3.99, -12 + _soft(n.f * 4, cut), max(0.3 * t1, 0.3)),
                      (9.9, 6 + _soft(n.f * 9.9, cut), min(0.45, t1))], 16_000, 0.02, 0.0, cap=6.0)]


def xylophone(n: Note) -> list:
    """Hard bars tuned 1 : 3, short (2.4 s at C5, 0.6 s at C7), with a sharp mallet click."""
    t1 = min(2.4 * 527 / n.f, 3.0)
    return [_ring(n, [(1, 0, t1), (3.0, -25, 0.5), (6.6, -28, 0.4)], 16_000, 0.12, 0.0)]


def celesta(n: Note) -> list:
    """Hammered steel bars over wooden resonators: a softer, shorter glockenspiel."""
    t1 = min(4.0 * (785 / n.f) ** 0.8, 5.0)
    return [_ring(n, [(1, 0, t1), (2.9, -14, 0.5), (5.5, -26, 0.3)], 6000, 0.01, 0.002, cap=4.0)]


def music_box(n: Note) -> list:
    """A comb tine (a clamped bar: 1, 6.27, 17.55) plucked by a pin: bright tick, clear ring."""
    t1 = min(3.0 * (1000 / n.f) ** 0.6, 4.0)
    return [_ring(n, [(1, 0, t1), (2.0, -24, 0.6 * t1), (6.27, -18, 0.3), (17.55, -30, 0.1)], 16_000, 0.06, 0.0005)]


# -- bells ------------------------------------------------------------------------------------------------------------

TUBULAR = [(1.22, -22, 12.0), (2.0, -5, 20.0), (2.93, 0, 15.0), (4.06, -4, 10.0), (5.31, -2, 6.0), (6.7, -3, 3.7),
           (8.2, -1, 2.6), (9.8, -4, 1.6), (11.5, -8, 1.1), (13.3, -19, 0.9)]


def tubular_bell(n: Note) -> list:
    """Orchestral chimes: a tube's beam modes; the ear hears the note an octave under the 2 : 3 : 4 of modes 4-6."""
    return [_ring(n, TUBULAR, 7000, 0.03, 0.0, cap=12.0)]


# -- plucked strings --------------------------------------------------------------------------------------------------

def harp(n: Note) -> list:
    """Harmonic partials, the h-th falling as 1/sqrt(h) and losing the highs above ~500 Hz (the low strings are rich,
    the top notes nearly pure); the first one rings 15 s at A2 and ~1.5 s at A6, the h-th h^0.7 times shorter."""
    t1 = 15.0 * (110 / n.f) ** 0.85
    parts = []
    for h in range(1, 11):   # a string decays twice: fast at first, then a quieter aftersound (its other plane)
        db, t = -10 * np.log10(h) + _soft(n.f * h, 500), t1 * h ** -0.7
        fast = 0.35 + 0.3 * min(max((300 - n.f) / 200, 0.0), 1.0)    # the bass strings sustain longer
        parts += [(h, db, fast * t), (h * 1.0004, db - 14, t)]
    return [_ring(n, parts, 16_000, 0.04, 0.0, cap=8.0, spread=0.001)]


def pizzicato(n: Note) -> list:
    """A plucked string section: harmonic, damped by the bow hand and the body (-20 dB after 0.2-0.4 s)."""
    t1 = min(1.3 * (264 / n.f) ** 0.5, 2.0)
    parts = [(h, -20 * np.log10(h) + 0.5 * _soft(n.f * h, 1500), t1 * h ** -0.5) for h in range(1, 9)]
    return [_ring(n, parts, 5000, 0.05, 0.004, spread=0.004)]


def guitar(n: Note) -> list:
    """A nylon-string guitar, from CC0 single notes: harmonics of nearly equal strength up to the 10th, a few
    notched by where the finger plucks (near the bridge); -20 dB after ~0.3 s, then a quieter aftersound."""
    t1 = 2.0 * (100 / n.f) ** 0.3
    pos = 0.12 + 0.06 * n.rand("pos")
    parts = []
    for h in range(1, 13):
        db = 20 * np.log10(abs(np.sin(np.pi * h * pos)) + 0.05) - 3 * np.log2(h) + _soft(n.f * h, 1500, 3)
        t = t1 * h ** -0.4
        parts += [(h, db, 0.45 * t), (h * 1.0003, db - 12, t)]
    return [_ring(n, parts, 16_000, 0.05, 0.0, cap=4.0, spread=0.0005)]


def lute(n: Note) -> list:
    """A lute: gut strings in pairs (courses) a few cents apart, plucked near the bridge: brighter, shorter, and
    shimmering where the two strings of a course beat."""
    t1 = 1.5 * (100 / n.f) ** 0.3
    twin = 1 + (2 + 2 * n.rand("course")) / 1200
    parts = []
    for h in range(1, 13):
        db = 20 * np.log10(abs(np.sin(np.pi * h * 0.1)) + 0.05) - 2 * np.log2(h) + _soft(n.f * h, 3500, 2)
        t = t1 * h ** -0.4
        parts += [(h, db, 0.4 * t), (h * twin, db - 2, 0.4 * t), (h * 1.0003, db - 12, t)]
    return [_ring(n, parts, 16_000, 0.08, 0.0, cap=3.0, spread=0.0005)]


# -- drums ------------------------------------------------------------------------------------------------------------

def timpani(n: Note) -> list:
    """The kettle's pitched mode with its overtones at 1.5, 1.98, 2.44 (2-6 s), a felt mallet's thud underneath
    that dies within 0.2 s."""
    body = _ring(n, [(0.85, 6, 0.25), (1, 0, 0.8), (1.0003, -8, 2.5), (1.5, -2, 4.0), (1.98, -15, 4.0),
                     (2.44, -14, 1.5), (2.9, -18, 1.2), (3.4, -20, 1.0), (4.0, -24, 0.8), (5.1, -26, 0.6),
                     (6.6, -30, 0.5), (9.2, -30, 0.4)], 3000, 0.0, 0.0, cap=4.0)
    thud = Noise(round(n.start, 4), 0.1, [(0, 400), (1, 150)], "low", 0.8, amp=[(0, 1), (1, 0)], attack=0.001,
                 release=0.02, gain=round(1.0 * n.vel, 4))
    return [body, thud]


def hand_drum(n: Note) -> list:
    """Conga, tumba, quinto: the head's note with a fifth-ish overtone (1.5-1.6), gone in half a second, and the
    slap of the palm."""
    head = _ring(n, [(1, 0, 0.35), (1.0004, -10, 1.0), (1.57, -14, 0.6), (2.4, -22, 0.4), (3.2, -30, 0.3)], 4000,
                 0.0, 0.0, cap=1.5)
    slap = Noise(round(n.start, 4), 0.03, [(0, 2500), (1, 2000)], "band", 0.6, amp=[(0, 1), (1, 0)], attack=0.0005,
                 release=0.005, gain=round(0.5 * n.vel, 4))
    return [head, slap]


def log_drum(n: Note) -> list:
    """A slit drum: a hollow log's one clear mode, a woody knock."""
    return [_ring(n, [(1, 0, 1.1), (1.26, -30, 0.4), (2.93, -38, 0.5)], 6000, 0.04, 0.0)]


def bass_drum(n: Note) -> list:
    """A concert bass drum (pitch ~55 Hz): the beater's boom, strongest at 63-125 Hz, -20 dB within 0.09 s, then
    the low ring for half a second more."""
    head = _ring(n, [(1, 0, 0.35), (1.0004, -12, 1.2), (1.6, -2, 0.3), (2.2, -6, 0.25), (2.8, -12, 0.2),
                     (3.6, -18, 0.15)], 2000, 0.0, 0.0, cap=1.5)
    boom = Noise(round(n.start, 4), 0.08, [(0, 250), (1, 90)], "low", 0.9, amp=[(0, 1), (1, 0)], attack=0.001,
                 release=0.02, gain=round(1.0 * n.vel, 4))
    return [head, boom]


def snare(n: Note) -> list:
    """The head's note (~220 Hz) and the wires rattling: broadband to 8 kHz, -20 dB after 70 ms."""
    head = _ring(n, [(1, 0, 0.25), (1.6, -8, 0.2), (2.3, -12, 0.15)], 4000, 0.0, 0.0, cap=0.6)
    wires = [Noise(round(n.start, 4), 0.2, [(0, 2500), (1, 2200)], "band", 0.3, amp=[(0, 1), (0.2, 0.15), (1, 0)],
                   attack=0.001, release=0.03, gain=round(0.6 + 0.6 * n.vel, 4)),
             Noise(round(n.start, 4), 0.15, [(0, 700), (1, 600)], "band", 0.6, amp=[(0, 1), (0.2, 0.15), (1, 0)],
                   attack=0.001, release=0.03, gain=round(0.6 * n.vel + 0.2, 4))]
    return [head, *wires]


# -- metals -----------------------------------------------------------------------------------------------------------

TRIANGLE = [(1, -9, 2.5), (1.2, -10, 1.9), (1.38, -11, 2.3), (1.48, -8, 2.5), (2.0, -9, 0.6), (2.46, -3, 0.9),
            (2.77, -6, 1.7), (4.41, -7, 0.7), (5.26, -12, 0.7), (5.82, -2, 0.5), (8.2, -10, 1.8), (8.27, 0, 0.5),
            (8.91, -13, 0.6), (9.86, -12, 0.55), (10.9, -10, 0.6)]


def triangle(n: Note) -> list:
    """A bent steel rod: a cluster of inharmonic modes from 1 to 6 times its lowest, ringing for seconds."""
    return [_ring(n, TRIANGLE, 16_000, 0.05, 0.0, cap=4.0)]


GONG = [(1, 0, 30.0), (2.0, -10, 3.5), (2.35, -12, 20.0), (2.61, -14, 7.6), (2.96, -14, 15.0), (3.26, -8, 7.9),
        (4.04, -12, 16.0), (6.22, -23, 12.0), (7.22, -25, 11.0), (8.52, -30, 13.0), (9.96, -30, 14.0),
        (11.61, -34, 15.0)]


def gong(n: Note) -> list:
    """A tam-tam struck with a soft beater: a dense, long cluster (tens of seconds; kept to 8 here) that blooms."""
    body = _ring(n, GONG, 1500, 0.0, 0.0, cap=12.0, spread=0.01)
    bloom = Noise(round(n.start, 4), 4.0, [(0, 1500), (1, 600)], "band", 0.7, amp=[(0, 0.2), (0.1, 1), (1, 0)],
                  attack=0.2, release=1.0, wobble=(3.0, 0.3), gain=round(0.25 * n.vel, 4))
    return [body, bloom]


def crash(n: Note) -> list:
    """A crash cymbal: dense modes from 400 Hz to 12 kHz over a wash of noise (strongest 2-8 kHz), -20 dB after
    0.3-0.6 s and -40 dB after ~2 s. `n.f` only shifts the cluster a little (smaller cymbals are brighter)."""
    shift = (n.f / 440) ** 0.3
    modes = [(round(300 * shift * 40 ** (n.rand(f"m{i}") ** 0.9), 1), round(0.5 + 2.0 * n.rand(f"t{i}"), 3),
              round(0.3 + 0.7 * n.rand(f"g{i}"), 3)) for i in range(48)]
    shimmer = Modal(round(n.start, 4), 2.6, modes, [(0.0, 1.0, 0.0)], hardness=round(9000 + 7000 * n.vel), click=0.2,
                    gain=round(0.8 * n.vel, 4))
    wash = Noise(round(n.start, 4), 2.0, [(0, 4000), (1, 3000)], "band", 0.35, amp=[(0, 1), (0.1, 0.25), (0.4, 0.06),
                                                                                    (1, 0)],
                 attack=0.001, release=0.3, wobble=(6.0, 0.2), gain=round(0.8 * n.vel, 4))
    return [shimmer, wash]


def tambourine(n: Note) -> list:
    """A hand on the skin and the jingles answering: small metal discs ringing at 4-12 kHz for a quarter second."""
    modes = [(round(4000 * 2.8 ** n.rand(f"j{i}"), 1), round(0.2 + 0.5 * n.rand(f"jt{i}"), 3),
              round(0.4 + 0.6 * n.rand(f"jg{i}"), 3)) for i in range(16)]
    hits = [(0.0, 1.0, 0.0)] + [(round(0.008 * k + 0.01 * n.rand(f"h{k}"), 4), round(0.7 ** k, 3), 0.0)
                                for k in range(1, 6)]   # the jingles knock together a few more times
    jingles = Modal(round(n.start, 4), 0.8, modes, hits, hardness=16_000, click=0.1, gain=round(n.vel, 4))
    skin = Noise(round(n.start, 4), 0.04, [(0, 400), (1, 300)], "band", 0.8, amp=[(0, 1), (1, 0)], attack=0.001,
                 release=0.01, gain=round(0.08 * n.vel, 4))
    return [jingles, skin]


def shaker(n: Note) -> list:
    """Seeds in a shell: a short burst of grains (4-12 kHz), as long as the note."""
    d = max(min(n.dur, 0.25), 0.06)
    return [Scatter(round(n.start, 4), round(d, 3), [(0, 300), (0.4, 900), (1, 100)], "pop", (3000, 12_000),
                    (0.0004, 0.0015), (0.2, 1.0), round(0.8 * n.vel, 4))]


# -- sustained: bowed, blown, sung ----------------------------------------------------------------------------------

def _sustain(n: Note, formants, brightness: float, vibrato=(5.0, 5.0), attack: float = 0.05, release: float = 0.15,
             breath: float = 0.0, voices: int = 1, spread: float = 0.0, jitter: float = 0.03, source: str = "glottal",
             amp=None, gain: float = 1.0, shimmer: float = 0.02) -> list:
    """Held notes: a bright source through the instrument's body resonances (fitted to the recordings' harmonics),
    vibrato (`vibrato` = Hz, cents), a section as `voices` players `spread` cents apart, each with its own vibrato."""
    out = []
    for v in range(voices):
        cents = (spread * (2 * v / (voices - 1) - 1) if voices > 1 else 0.0) + spread * 0.3 * (n.rand(f"dt{v}") - 0.5)
        f = n.f * 2 ** (cents / 1200)
        rate = vibrato[0] * (0.9 + 0.2 * n.rand(f"vr{v}"))
        out.append(Syllable(round(n.start + 0.012 * v * n.rand(f"on{v}"), 4), round(n.dur + release, 4),
                            [(0, f), (1, f)], source, brightness=brightness, vibrato=(round(rate, 3), vibrato[1] / 100),
                            jitter=jitter, breath=breath, formants=formants, attack=attack, release=release,
                            amp=amp or [(0, 1), (1, 1)], gain=round(gain * n.vel / voices ** 0.5, 4), shimmer=shimmer))
    return out


# Body resonances fitted (bounded: 150-8000 Hz, bandwidth >= 150 Hz) so that our notes' first 8 harmonics match
# the recordings' across the range; rms error per harmonic in brackets.
VIOLINS = (0.466, [(558.0, 150.0, 1.0), (806.0, 6000.0, 1.36), (2004.0, 744.0, 1.09)])       # [1.8 dB]
CELLOS = (0.335, [(360.0, 150.0, 1.0), (795.0, 359.0, 0.6), (1576.0, 6000.0, 0.35)])         # [3.8 dB]
FLUTE = (0.0, [(1329.0, 2493.0, 1.2)])                                                        # [5.2 dB]
HORN = (0.424, [(555.0, 150.0, 1.0), (865.0, 150.0, 0.05)])                                   # [6.3 dB]
TRUMPET_SOFT = (0.0, [(670.0, 607.0, 1.0)])                                                   # [2.8 dB]
TRUMPET_LOUD = (0.283, [(1216.0, 816.0, 1.0), (2040.0, 169.0, 0.43)])                         # [4.3 dB]


def violins(n: Note) -> list:
    """A violin section: three players a few cents apart, each with their own vibrato (5 Hz, +-5 cents); the bow
    takes 0.1-0.4 s to speak (slower when soft)."""
    b, forms = VIOLINS
    return _sustain(n, forms, b, (5.2, 8.0), attack=0.1 + 0.3 * (1 - n.vel), release=0.3, breath=0.04, voices=3,
                    spread=8.0)


def cellos(n: Note) -> list:
    """A cello section (also the basses, an octave down): rounder, the same slow bow."""
    b, forms = CELLOS
    return _sustain(n, forms, b, (5.0, 7.0), attack=0.12 + 0.3 * (1 - n.vel), release=0.35, breath=0.04, voices=3,
                    spread=7.0)


def strings(n: Note) -> list:
    """The string section by register: cellos below G3, violins above."""
    return cellos(n) if n.f < 196 else violins(n)


def flute(n: Note) -> list:
    """A flute: nearly pure on top, richer low down, breathy, vibrato ~5 Hz +-7 cents; speaks in 40-120 ms."""
    b, forms = FLUTE
    return _sustain(n, forms, b, (5.2, 7.0), attack=0.04 + 0.08 * (1 - n.vel), release=0.12, breath=0.08)


def horn(n: Note) -> list:
    """A French horn: dark, its second harmonic strongest, almost no vibrato; 80-250 ms to bloom."""
    b, forms = HORN
    return _sustain(n, forms, b, (3.3, 1.5), attack=0.08 + 0.12 * (1 - n.vel), release=0.15, voices=2, spread=4.0)


def trumpet(n: Note) -> list:
    """A trumpet, whose brightness follows how hard it is played: soft notes have one resonance near 670 Hz, loud
    ones open up to 1.2 and 2 kHz (fitted on both dynamics); 20-35 ms attack, a straight tone."""
    t = min(max((n.vel - 0.4) / 0.5, 0.0), 1.0)
    (bs, soft), (bl, loud) = TRUMPET_SOFT, TRUMPET_LOUD
    f1 = soft[0][0] * (loud[0][0] / soft[0][0]) ** t
    bw1 = soft[0][1] + (loud[0][1] - soft[0][1]) * t
    forms = [(round(f1, 1), round(bw1, 1), 1.0), (2040.0, 169.0 + 300 * (1 - t), round(0.05 + 0.38 * t, 3))]
    return _sustain(n, forms, bs + (bl - bs) * t, (3.2, 2.5), attack=0.025, release=0.1)


def choir(n: Note) -> list:
    """Voices on "ah": glottal sources through the vowel's formants, three singers per note."""
    from .archetypes import VOWELS
    forms = [(hz, bw * 1.5, g) for hz, bw, g in zip(VOWELS["a"], (90, 110, 160, 250), (1.0, 0.6, 0.3, 0.15),
                                                     strict=True)]
    return _sustain(n, forms, 0.35, (4.8, 12.0), attack=0.25 + 0.2 * (1 - n.vel), release=0.4, breath=0.25,
                    voices=3, spread=10.0, jitter=0.05)


# -- chiptune: the Game Boy's two pulse channels, its wave channel and its noise --------------------------------------

def _pulse(width: float):
    def play(n: Note) -> list:
        return [Syllable(round(n.start, 4), round(n.dur * 0.92, 4), [(0, n.f), (1, n.f)], "pulse", pulse_width=width,
                         brightness=1.0, attack=0.002, release=0.01, amp=[(0, 1), (1, 0.75)], gain=round(n.vel, 4))]
    play.__doc__ = f"A {int(width * 1000) / 10}% pulse wave, gated like a sound chip's envelope."
    return play


def chip_bass(n: Note) -> list:
    """The wave channel playing a soft, round bass."""
    return [Syllable(round(n.start, 4), round(n.dur * 0.9, 4), [(0, n.f), (1, n.f)], "sine", attack=0.002,
                     release=0.01, gain=round(n.vel, 4))]


def chip_kick(n: Note) -> list:
    """A pitch dropping fast: the chip's kick."""
    return [Syllable(round(n.start, 4), 0.09, [(0, 180), (0.3, 70), (1, 45)], "pulse", pulse_width=0.5,
                     brightness=0.4, attack=0.001, release=0.02, amp=[(0, 1), (1, 0)], gain=round(n.vel, 4))]


def chip_snare(n: Note) -> list:
    """A burst of the noise channel."""
    return [Noise(round(n.start, 4), 0.12, [(0, 5000), (1, 3000)], "high", 0.6, amp=[(0, 1), (1, 0)], attack=0.001,
                  release=0.01, gain=round(n.vel, 4))]


def chip_hat(n: Note) -> list:
    """A short, bright tick of noise."""
    return [Noise(round(n.start, 4), 0.03, [(0, 9000), (1, 9000)], "high", 0.7, amp=[(0, 1), (1, 0)], attack=0.0005,
                  release=0.005, gain=round(0.7 * n.vel, 4))]


INSTRUMENTS = {
    "glockenspiel": glockenspiel, "marimba": marimba, "xylophone": xylophone, "celesta": celesta,
    "music_box": music_box, "tubular_bell": tubular_bell, "harp": harp, "pizzicato": pizzicato, "guitar": guitar,
    "lute": lute, "timpani": timpani, "hand_drum": hand_drum, "log_drum": log_drum, "bass_drum": bass_drum,
    "snare": snare, "triangle": triangle,
    "gong": gong, "crash": crash, "tambourine": tambourine, "shaker": shaker,
    "violins": violins, "cellos": cellos, "strings": strings, "flute": flute, "horn": horn, "trumpet": trumpet,
    "choir": choir,
    "square": _pulse(0.5), "pulse": _pulse(0.25), "thin_pulse": _pulse(0.125), "chip_bass": chip_bass,
    "chip_kick": chip_kick, "chip_snare": chip_snare, "chip_hat": chip_hat,
}
