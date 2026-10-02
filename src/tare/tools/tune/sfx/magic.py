"""Magic: eight elements, each with a charge, a cast, a travelling loop and an impact.

Every element is a small palette of layers (fire roars and crackles, ice rings like glass,
lightning buzzes and cracks, holy sings...). Size lowers and lengthens a spell, power makes
it louder, brighter and denser. The species seed is the spell's identity: its key, its
chord, the shape of its sparkle.
"""
from ..archetypes import VOWELS
from ..spec import Noise, Scatter, Syllable
from . import Fx, bell_curve, decay_curve, recipe
from .physical import TRUNK, burst, splits, squeak, whoosh
from .ui import bar

ELEMENTS = ("fire", "ice", "lightning", "arcane", "holy", "shadow", "nature", "heal")
SCALE = (0, 2, 4, 7, 9, 12, 14, 16, 19)          # major pentatonic, two octaves
LOOP = 0.4                                        # crossfade of the travelling loop, seconds


def swell(start, dur, f0, f1, q=0.8, gain=1.0, wobble=(10.0, 0.5), amp=None, color="white", kind="band"):
    return Noise(round(start, 3), round(dur, 3), [(0, f0), (1, f1)], kind, q, color,
                 amp or [(0, 0.0), (1, 1.0)], attack=0.02, release=0.05, wobble=wobble, gain=gain)


def bed(start, dur, hz, q=0.7, gain=1.0, wobble=(10.0, 0.5), color="white", kind="band"):
    """A steady noise layer (for loops)."""
    return Noise(round(start, 3), round(dur, 3), [(0, hz), (1, hz)], kind, q, color, attack=0.05, release=0.05,
                 wobble=wobble, gain=gain)


def sparkle(start, dur, rate, hz=(3000, 10_000), decay=(0.04, 0.25), gain=0.6):
    return Scatter(round(start, 3), round(dur, 3), rate, "ping", hz, decay, (0.15, 1.0), gain)


def crackle(start, dur, rate, hz=(1500, 7000), gain=0.6):
    return Scatter(round(start, 3), round(dur, 3), rate, "pop", hz, (0.0004, 0.003), (0.1, 1.0), gain)


def tone(start, dur, f0, f1, gain=1.0, source="sine", **kw):
    return Syllable(round(start, 3), round(dur, 3), [(0, f0), (1, f1)], source, gain=gain, **kw)


def boom(start, length, hz=110, gain=1.0):
    return Noise(round(start, 3), round(length, 3), [(0, hz), (1, hz * 0.4)], "low", 0.9, "brown", decay_curve(4),
                 attack=0.004, release=0.2, wobble=(4.0, 0.3), gain=gain)


def choir(start, dur, root, chord=(0, 4, 7, 12), vowel="a", gain=0.6, attack=0.4, amp=None, breath=0.25,
          stagger=0.0, brightness=0.35):
    """Sustained voices: glottal sources through vowel formants, gently detuned and vibrating. With `stagger` the
    voices come in one after the other, up the chord, each stepping back when the next one enters (the newest note
    leads, as in a fanfare), and all end together."""
    out = []
    for i, st in enumerate(chord):
        f = root * 2 ** (st / 12) * (1 + 0.004 * (i - 1.5))
        d = dur - i * stagger
        a = amp or [(0, 1), (1, 1)]
        if stagger and i < len(chord) - 1:
            a = times(a, [(0, 1), (stagger / d, 1), (min(2 * stagger / d, 0.9), 0.35), (1, 0.35)])
        out.append(Syllable(round(start + i * stagger, 3), round(d, 3), [(0, f), (1, f)], "glottal",
                            brightness=brightness, vibrato=(4.8 + 0.4 * i, 0.12), jitter=0.05, breath=breath,
                            formants=[(hz, bw * 1.5, g) for hz, bw, g in zip(VOWELS[vowel], (90, 110, 160, 250),
                                                                             (1.0, 0.6, 0.3, 0.15), strict=True)],
                            attack=attack, release=min(0.5, dur / 3), amp=a, gain=gain))
    return out


def times(a, b):
    """The product of two breakpoint curves."""
    def at(c, x):
        for (x0, y0), (x1, y1) in zip(c, c[1:], strict=False):
            if x <= x1:
                return y0 + (y1 - y0) * (x - x0) / max(x1 - x0, 1e-9)
        return c[-1][1]
    return [(round(x, 4), round(at(a, x) * at(b, x), 4)) for x in sorted({x for x, _ in a} | {x for x, _ in b})]


def bells(fx: Fx, start, notes_hz, gap, gain=0.7, material="bell"):
    """A run of struck bells (arpeggios, chimes)."""
    out = []
    for k, hz in enumerate(notes_hz):
        size = min(max(1 - (hz - 220) / 1500, 0.0), 1.0)   # the material's lowest mode lands near `hz`
        out.append(fx.strike(material, start=round(start + k * gap, 3), size=size, gain=gain, prefix=f"bell{k}",
                             hits=[(0.0, 1.0, 0.002)], hardness=5000, dur=1.6))
    return out


def shatter(fx: Fx, size: float, power: float) -> list:
    """Glass or ice breaking: a broadband crash, then a rain of shards (mostly noisy ticks, a few rings)."""
    return [Noise(0.0, round(0.4 + 0.4 * size, 3), [(0, 1500), (1, 2500)], "high", 0.6, amp=decay_curve(4),
                  attack=0.001, release=0.05, wobble=(40.0, 0.5), gain=1.0),
            fx.strike("glass", size=size, gain=0.5, prefix="pane"),
            Scatter(0.0, round(0.8 + size, 3), [(0, 400 + 400 * power), (0.2, 150), (1, 0)], "pop", (2000, 12_000),
                    (0.0005, 0.003), (0.1, 1.0), 0.8),
            Scatter(0.05, round(0.8 + size, 3), [(0, 60), (1, 0)], "ping", (3000, 10_000), (0.01, 0.05), (0.1, 0.7),
                    0.3)]


def thunder(fx: Fx, length: float, near: float = 0.0) -> list:
    """Thunder, from recordings: a rumble strongest near 250 Hz (-12 dB at 1 kHz, -25 at 2 kHz) lasting 2.5-5 s,
    rolling: a new burst every ~0.3 s, each 6-12 dB over the bed. A strike close by (`near`) tears first with a few
    sharp broadband cracks."""
    bed = [(0.0, 0.0), (0.03, 1.0), (0.4, 0.45), (1.0, 0.0)]
    out = [Noise(0.0, round(length, 3), [(0, 320), (1, 220)], "band", 0.45, "brown", bed, attack=0.03, release=0.4,
                 wobble=(3.0, 0.4), gain=0.5)]
    t, k = 0.02, 0
    while t < length * 0.85:
        fade = 1 - t / length
        dur = 0.25 + 0.3 * fx.rand(f"rd{k}")
        g = (0.35 + 0.65 * fx.rand(f"rg{k}")) * fade ** 0.7
        hz = 240 + 120 * fx.rand(f"rh{k}")
        out.append(Noise(round(t, 3), round(dur, 3), [(0, hz), (1, hz * 0.8)], "band", 0.5, "brown", decay_curve(4),
                         attack=0.01, release=0.05, gain=round(g, 3)))
        t += 0.2 + 0.25 * fx.rand(f"rt{k}")
        k += 1
    for j in range(int(round(near * (1 + 2 * fx.rand("cracks"))))):   # the air tearing close to the bolt
        out.append(Noise(round(0.01 + 0.12 * j * fx.rand(f"ct{j}"), 3), 0.06, [(0, 2500), (1, 1500)], "high", 0.6,
                         amp=decay_curve(5), attack=0.0005, release=0.01, gain=round(0.6 * near, 3)))
    return out


@recipe("spell", ("charge", "cast", "travel", "impact"), ELEMENTS, loops=("travel",))
def spell(fx: Fx):
    """Spells by element (fire, ice, lightning, arcane, holy, shadow, nature, heal): charge, cast, travel, impact."""
    el, s, p, e = fx.style, fx.size, fx.power, fx.event
    low = 2 ** (-1.2 * s)                               # bigger spells sit lower
    charge = (1.0 + 0.8 * s) * (0.8 + 0.4 * fx.g.u("charge_len"))
    trip = 2.0 + 1.0 * s
    root = 220 * low * 2 ** (SCALE[int(fx.g.u("key") * 5)] / 12)
    L, extra = [], {}

    if el == "fire":
        if e == "charge":
            L = [swell(0, charge, 250 * low, 1300 * low, gain=1.0, wobble=(12, 0.7)),
                 crackle(0, charge, [(0, 10), (1, 60 + 120 * p)]),
                 tone(0, charge, 55 * low, 80 * low, 0.35, "glottal", rough=(0.5, 18.0), attack=0.3)]
        elif e == "cast":
            L = [*whoosh(fx, 0.0, 0.7, 900 * low, 0.9, gain=0.5), burst(0.0, 0.08, 2500, 0.3),
                 swell(0.02, 0.8, 500 * low, 200 * low, gain=0.5, wobble=(14, 0.8), amp=decay_curve(3)),
                 boom(0.0, 0.9, 140 * low, 1.6),   # the roar of the fire leaving the hand
                 crackle(0.05, 0.8, [(0, 150), (1, 0)], gain=0.4)]
        elif e == "travel":   # flame loops roar lowest (strongest at 63 Hz, -20 to -30 dB at 1-4 kHz), crackling on top
            L = [bed(0, trip + LOOP, 110 * low, 0.9, 1.0, (6, 0.5), "brown", "low"),
                 bed(0, trip + LOOP, 500 * low, 0.6, 0.25, (13, 0.8), "brown"),
                 crackle(0, trip + LOOP, [(0, 70), (1, 70)], gain=0.4)]
        else:
            L = [boom(0, 2.0 + s, 120 * low, 1.2), burst(0.0, 0.06, 1500, 0.5),
                 swell(0.0, 1.5 + s, 700 * low, 250 * low, gain=0.5, wobble=(14, 0.8), amp=decay_curve(3)),
                 crackle(0.05, 1.8 + s, [(0, 200), (0.3, 60), (1, 0)], gain=0.4)]
            extra = {"space": 1.5, "wet": 0.2}

    elif el == "ice":
        if e == "charge":
            L = [swell(0, charge, 2500, 5500, q=2.5, gain=0.7, wobble=(3, 0.4)),
                 sparkle(0, charge, [(0, 4), (1, 30 + 30 * p)], (2500 * low, 9000), (0.08, 0.4)),
                 crackle(0, charge, [(0, 0), (1, 40)], (4000, 10_000), 0.4)]
        elif e == "cast":
            L = [*whoosh(fx, 0.0, 0.5, 2500, 1.2, gain=0.8), burst(0.0, 0.05, 5000, 0.3),
                 sparkle(0, 0.5, [(0, 120), (1, 0)], (3000, 10_000), gain=0.4),
                 swell(0.0, 0.5, 900, 1800, q=0.9, gain=0.5, wobble=(20, 0.6), amp=decay_curve(3)),
                 boom(0.0, 0.5, 300 * low, 0.3)]
        elif e == "travel":
            L = [bed(0, trip + LOOP, 4200, 2.5, 0.6, (2.5, 0.5)),
                 sparkle(0, trip + LOOP, [(0, 18), (1, 18)], (2500 * low, 9000), (0.08, 0.4))]
        else:   # the ice block lands and bursts: a thump and a crunch under the shards
            crash, pane, shards, rings = shatter(fx, 0.3 + 0.4 * s, p)
            crash.gain, shards.gain, rings.gain, pane.gain = 0.5, 0.3, 0.15, 0.3
            L = [crash, pane, shards, rings,
                 Noise(0.0, 0.3, [(0, 300 * low), (1, 200 * low)], "band", 0.8, amp=decay_curve(5), attack=0.002,
                       gain=0.5),
                 Noise(0.0, 0.25, [(0, 1400), (1, 800)], "band", 0.8, amp=decay_curve(4), attack=0.002,
                       wobble=(50, 0.8), gain=0.7)]
            extra = {"space": 1.2, "wet": 0.18}

    elif el == "lightning":
        buzz_hz = 55 * (1.2 if fx.g.u("mains") > 0.5 else 1.0)
        def buzz(start, dur, gain, rise=1.0):
            return tone(start, dur, buzz_hz, buzz_hz * rise, gain, "pulse", pulse_width=0.15, brightness=1.0,
                        rough=(0.6, 31.0), ring=(1700.0, 0.3), jitter=0.4, attack=0.05)
        if e == "charge":
            L = [buzz(0, charge, 0.6, 1.5), crackle(0, charge, [(0, 20), (1, 200 + 200 * p)], (2000, 11_000)),
                 swell(0, charge, 2000, 6000, q=1.2, gain=0.4, wobble=(30, 0.8))]
        elif e == "cast":
            L = [buzz(0, 0.35, 0.7, 0.6), burst(0.0, 0.12, 1800, 1.0, q=0.5),
                 crackle(0, 0.5, [(0, 1200), (0.4, 300), (1, 0)], (1500, 11_000), 1.0)]
        elif e == "travel":
            L = [buzz(0, trip + LOOP, 0.6), crackle(0, trip + LOOP, [(0, 150), (1, 150)], (2000, 11_000), 0.7),
                 bed(0, trip + LOOP, 3500, 1.0, 0.3, (25, 0.9))]
        else:   # the bolt strikes (a bright zap, crackle) and the thunder rolls after it
            L = [*thunder(fx, 2.5 + 1.5 * s, near=1.0), buzz(0, 0.25, 0.8, 0.5), burst(0.0, 0.15, 3000, 1.0, q=0.5),
                 crackle(0, 0.6, [(0, 1500), (0.3, 400), (1, 0)], (2000, 11_000), 1.0)]
            extra = {"space": 2.0, "wet": 0.25}

    elif el == "arcane":
        chord = [root * r for r in (1, 1.5, 2.005)]
        def shimmer(start, dur, rise, gain):
            return [tone(start, dur, f, f * rise, gain / 3, "sine", vibrato=(5.5 + i, 0.25), ring=(f * 1.41, 0.25),
                         attack=0.2, release=0.2) for i, f in enumerate(chord)]
        if e == "charge":
            L = [*shimmer(0, charge, 2.0, 0.8), sparkle(0, charge, [(0, 5), (1, 60)]),
                 swell(0, charge, 1500, 6000, q=3, gain=0.4, wobble=(6, 0.3))]
        elif e == "cast":
            L = [tone(0, 0.5, 500 * low, 150 * low, 0.6, "sine", attack=0.005, release=0.2),
                 *shimmer(0, 0.7, 1.5, 0.8), *whoosh(fx, 0.0, 0.6, 1500, 1.2, gain=0.6),
                 sparkle(0, 0.6, [(0, 150), (1, 0)])]
        elif e == "travel":
            L = [*shimmer(0, trip + LOOP, 1.0, 0.7), sparkle(0, trip + LOOP, [(0, 25), (1, 25)]),
                 bed(0, trip + LOOP, 2000, 2.0, 0.25, (4, 0.5))]
        else:
            L = [burst(0.0, 0.1, 1200, 0.9, q=0.6), tone(0, 0.8, 300 * low, 120 * low, 0.5, "sine", attack=0.002),
                 *shimmer(0, 1.2, 0.7, 0.7),
                 *bells(fx, 0.0, [c * 2 for c in chord], 0.0, 0.5, "glass"),
                 sparkle(0, 1.5, [(0, 200), (1, 0)])]
            extra = {"space": 2.0, "wet": 0.25}

    elif el == "holy":   # angelic fanfares: pure voices come in up a major chord, 0.3-0.5 s apart, held for 3 s;
        top = [root * 8 * 2 ** (st / 12) for st in (0, 4, 7, 12)]   # glimmers: a cluster of chimes at 2-3 kHz above
        def glimmer(start, dur, gain):
            out = []
            for k in range(int(dur / 0.12)):   # the chord's top notes struck over and over, softer and softer
                t = start + 0.12 * k + 0.08 * fx.rand(f"gt{k}")
                out.append(bar(round(t, 3), top[int(fx.rand(f"gn{k}") * 4) % 4], 0.8,
                               round(gain * (0.4 + 0.6 * fx.rand(f"gg{k}")) * (1 - k * 0.12 / dur), 3)))
            return out
        if e == "charge":
            L = [*choir(0, charge, root, amp=[(0, 0), (1, 1)], attack=0.3),
                 sparkle(0, charge, [(0, 3), (1, 25)], (3000, 9000), (0.2, 0.6), 0.4)]
        elif e == "cast":
            L = [*choir(0, 2.6, root * 2, (0, 4, 7, 12), "o", 0.7, 0.12, [(0, 0.7), (0.5, 1), (0.7, 0.8), (1, 0)],
                        stagger=0.3, brightness=0.25),
                 *glimmer(0.0, 1.4, 0.35), sparkle(0.0, 1.8, [(0, 60), (1, 0)], (3000, 10_000), (0.1, 0.5), 0.4),
                 *whoosh(fx, 0.0, 0.5, 3000, 1.2, gain=0.25)]
            extra = {"space": 2.0, "wet": 0.25}
        elif e == "travel":
            L = [*choir(0, trip + LOOP, root * 2, (0, 7, 12), "o", 0.6, 0.3),
                 sparkle(0, trip + LOOP, [(0, 10), (1, 10)], (3000, 9000), (0.2, 0.6), 0.4)]
        else:   # the whole chord at once, then higher voices climbing on top of it
            fade = [(0, 1), (0.6, 0.9), (1, 0)]
            L = [*choir(0, 3.2, root * 2, (0, 4, 7), "o", 0.8, 0.03, fade, brightness=0.25),
                 *choir(0.5, 2.7, root * 2, (12, 16, 19), "o", 0.7, 0.1, fade, stagger=0.4, brightness=0.25),
                 *[bar(0.0, f, 1.2, 0.5) for f in top[:3]], *glimmer(0.1, 2.0, 0.35),
                 sparkle(0, 2.0, [(0, 120), (1, 0)], (3000, 10_000), (0.1, 0.5)),
                 burst(0.0, 0.08, 3000, 0.3)]
            extra = {"space": 2.5, "wet": 0.3}

    elif el == "shadow":   # dark-magic sounds: most energy at 250-500 Hz (not sub-bass), a voice hopping between
        # the notes of a diminished chord about ten times a second, smeared by the reverb into a beating cluster
        def drone(start, dur, gain, rise=1.0):
            return [tone(start, dur, f, f * rise, gain / 2, "glottal", brightness=0.2, sub=0.3, rough=(0.4, 9.0),
                         jitter=0.3, attack=0.3, release=0.3) for f in (110 * low, 110 * low * 1.06)]
        def hexing(start, dur, f, gain, key, rate=9.0):
            n, eps = max(int(dur * rate), 2), min(0.012 / dur, 0.02)
            pts = []
            for k in range(n):
                hz = round(f * 2 ** ((0, 3, 6, 9)[int(fx.rand(f"{key}{k}") * 4) % 4] / 12), 1)
                pts += [(round(k / n, 4), hz), (round((k + 1) / n - eps, 4), hz)]
            return Syllable(round(start, 3), round(dur, 3), pts, "glottal", brightness=0.45, jitter=0.1,
                            rough=(0.2, 9.0), attack=0.01, release=0.2, amp=[(0, 1), (0.3, 0.8), (1, 0)],
                            gain=gain)
        def whispers(start, dur, gain):
            return Syllable(round(start, 3), round(dur, 3), [(0, 100), (1, 100)], "noise",
                            formants=[(hz, 150, g) for hz, g in zip(VOWELS["o"][:3], (1.0, 0.7, 0.4), strict=True)],
                            mouth=[(0, 0.8), (0.3, 1.3), (0.6, 0.9), (1, 1.2)], attack=0.2, release=0.3,
                            pulses=(3.0, 0.6, 2.0), gain=gain)
        if e == "charge":
            L = [*drone(0, charge, 0.9, 1.3), whispers(0, charge, 0.4),
                 swell(0, charge, 150, 600, gain=0.6, wobble=(5, 0.5), color="brown")]
        elif e == "cast":
            L = [swell(0, 0.25, 300, 1200, q=0.7, gain=0.6, wobble=(8, 0.3), amp=[(0, 0), (0.95, 1), (1, 0)]),
                 hexing(0.2, 1.2, 420 * low, 1.0, "hc"), hexing(0.2, 1.2, 210 * low, 0.4, "hl"),
                 whispers(0.2, 0.9, 0.5)]
            extra = {"space": 1.5, "wet": 0.3}
        elif e == "travel":
            L = [*drone(0, trip + LOOP, 0.8), whispers(0, trip + LOOP, 0.4)]
        else:
            L = [hexing(0, 1.6, 420 * low, 1.0, "hi"), hexing(0, 1.6, 210 * low, 0.5, "hl"),
                 *drone(0, 1.5, 0.6, 0.7), boom(0, 1.5, 160 * low, 0.5), burst(0.0, 0.08, 600, 0.6, "low"),
                 whispers(0.1, 1.5, 0.6)]
            extra = {"space": 2.0, "wet": 0.3, "drive": 1.5}

    elif el == "nature":   # from recordings of what it moves: foliage rustling (strongest 2-8 kHz, -9 to -14 dB
        # at 125-500 Hz), trees creaking (stick-slip near 90 Hz through wood resonances at 0.8-1.8 kHz) and roots
        # tearing out of the ground (a low, earthy 63-250 Hz rumble)
        def foliage(start, dur, gain, amp=None, rate=(0, 120)):
            t, d, amp = round(start, 3), round(dur, 3), amp or bell_curve(0.4, 1.2)
            return [Noise(t, d, [(0, 3500), (1, 3000)], "band", 0.35, amp=amp, attack=0.05, release=0.1,
                          wobble=(11.0, 0.8), gain=gain),
                    Noise(t, d, [(0, 900), (1, 800)], "band", 0.6, amp=amp, attack=0.05, release=0.1,
                          wobble=(7.0, 0.7), gain=gain * 0.6),
                    Noise(t, d, [(0, 400), (1, 400)], "low", 0.7, "brown", amp, attack=0.05, release=0.1,
                          wobble=(5.0, 0.7), gain=gain * 0.4),   # the branches themselves moving
                    Scatter(round(start, 3), round(dur, 3), [(0, rate[0]), (0.4, rate[1]), (1, rate[0])], "pop",
                            (2000, 9000), (0.0005, 0.002), (0.1, 1.0), gain * 0.5)]
        def creak(start, dur, gain, name, rise=1.25):
            f = 75 + 25 * fx.g.u("trunk")
            return squeak(fx, round(start, 3), round(dur, 3), f, f * rise, gain, name, TRUNK)
        if e == "charge":   # the undergrowth stirring, a trunk slowly bending
            L = [*foliage(0, charge, 0.8, [(0, 0.1), (1, 1)], (10, 80 + 80 * p)),
                 creak(charge * 0.3, charge * 0.7, 0.4, "cc")]
        elif e == "cast":   # a gust through the leaves, branches whipping
            L = [*foliage(0, 0.9, 1.0, rate=(20, 200)), creak(0.05, 0.5, 0.5, "c1", 1.4),
                 *whoosh(fx, 0.0, 0.6, 1600, 1.0, gain=0.4)]
        elif e == "travel":
            L = [*foliage(0, trip + LOOP, 0.7, [(0, 1), (1, 1)], (60, 60)), creak(0.3, 0.9, 0.25, "ct")]
        else:   # roots and vines burst out of the ground: an earthy rumble, trunks groaning, leaves thrashing
            L = [Noise(0.0, round(0.5 + 0.3 * s, 3), [(0, 300 * low), (1, 120 * low)], "low", 0.8, "brown",
                       decay_curve(4), attack=0.005, release=0.05, wobble=(9.0, 0.6), gain=1.0),
                 Scatter(0.0, 0.6, [(0, 40), (1, 0)], "pop", (300, 2000), (0.003, 0.01), (0.3, 1.0), 0.5),
                 creak(0.05, 0.8, 0.6, "c1", 1.3), creak(0.35, 0.9, 0.5, "c2", 0.8),
                 *foliage(0.0, 1.5 + 0.5 * s, 0.9, decay_curve(2), (30, 250))]
            extra = {"space": 1.0, "wet": 0.15}

    else:  # heal
        notes = [root * 2 * 2 ** (SCALE[(i + int(fx.g.u("mode") * 3)) % len(SCALE)] / 12) for i in range(5)]
        if e == "charge":
            L = [*choir(0, charge, root, (0, 7, 12), "o", 0.5, 0.4, [(0, 0), (1, 1)], 0.4),
                 sparkle(0, charge, [(0, 5), (1, 30)], (3000, 8000), (0.2, 0.6), 0.4)]
        elif e == "cast":
            L = [*bells(fx, 0.0, notes, 0.08 + 0.04 * fx.g.u("tempo"), 0.6, "glass"),
                 *choir(0, 1.1, root * 2, (0, 7), "o", 0.2, 0.05, decay_curve(2), 0.4),
                 sparkle(0.1, 1.0, [(0, 60), (1, 0)], (4000, 10_000), (0.1, 0.4), 0.4),
                 bed(0.0, 1.2, 7000, 2.0, 0.15, (3, 0.3))]
        elif e == "travel":
            L = [*choir(0, trip + LOOP, root * 2, (0, 4, 7), "o", 0.5, 0.4, breath=0.4),
                 sparkle(0, trip + LOOP, [(0, 12), (1, 12)], (3000, 9000), (0.2, 0.6), 0.4)]
        else:
            L = [*bells(fx, 0.0, [notes[0], notes[2], notes[4]], 0.0, 0.7, "glass"),
                 bed(0.0, 1.8, 7000, 2.0, 0.25, (3, 0.3)),
                 sparkle(0.0, 1.6, [(0, 100), (1, 0)], (4000, 10_000), (0.1, 0.5), 0.5),
                 *choir(0, 1.6, root * 2, (0, 4, 7), "o", 0.4, 0.05, decay_curve(2), 0.4)]
            extra = {"space": 2.0, "wet": 0.25}

    if e == "travel":
        extra["loop"] = LOOP
    gain = 10 ** (-12 * (1 - p) / 20) * (0.7 if e == "charge" else 1.0)
    return fx.voice(gain=gain, **splits(L), **extra)
