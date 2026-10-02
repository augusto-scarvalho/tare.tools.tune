"""Magic: eight elements, each with a charge, a cast, a travelling loop and an impact.

Every element is a small palette of layers (fire roars and crackles, ice rings like glass,
lightning buzzes and cracks, holy sings...). Size lowers and lengthens a spell, power makes
it louder, brighter and denser. The species seed is the spell's identity: its key, its
chord, the shape of its sparkle.
"""
from ..archetypes import VOWELS
from ..spec import Noise, Scatter, Syllable
from . import Fx, decay_curve, recipe
from .physical import burst, splits, whoosh

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


def choir(start, dur, root, chord=(0, 4, 7, 12), vowel="a", gain=0.6, attack=0.4, amp=None, breath=0.25):
    """Sustained voices: glottal sources through vowel formants, gently detuned and vibrating."""
    out = []
    for i, st in enumerate(chord):
        f = root * 2 ** (st / 12) * (1 + 0.004 * (i - 1.5))
        out.append(Syllable(round(start, 3), round(dur, 3), [(0, f), (1, f)], "glottal", brightness=0.35,
                            vibrato=(4.8 + 0.4 * i, 0.12), jitter=0.05, breath=breath,
                            formants=[(hz, bw * 1.5, g) for hz, bw, g in zip(VOWELS[vowel], (90, 110, 160, 250),
                                                                             (1.0, 0.6, 0.3, 0.15), strict=True)],
                            attack=attack, release=min(0.5, dur / 3), amp=amp or [(0, 1), (1, 1)], gain=gain))
    return out


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


def thunder(fx: Fx, length: float) -> list:
    """Thunder rolls: a low-mid rumble up to ~1 kHz swelling and fading a few times."""
    rolls = [(0.0, 0.0), (0.05, 1.0)]
    t = 0.05
    for k in range(4):
        t += 0.12 + 0.2 * fx.rand(f"roll{k}")
        rolls.append((round(min(t, 0.95), 3), round(0.35 + 0.6 * fx.rand(f"lvl{k}") * (1 - 0.18 * k), 3)))
    rolls.append((1.0, 0.0))
    # a sharp crack or crackle on top reads as fire to listeners (and CLAP): thunder is the rumble
    return [Noise(0.03, round(length, 3), [(0, 1200), (0.3, 600), (1, 250)], "low", 0.7, "brown", rolls,
                  attack=0.02, release=0.5, wobble=(3.0, 0.5), gain=1.0),
            Noise(0.03, round(length, 3), [(0, 120), (1, 60)], "low", 0.8, "brown", rolls, attack=0.05, release=0.5,
                  gain=0.8)]


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
        elif e == "travel":
            L = [bed(0, trip + LOOP, 700 * low, 0.6, 1.0, (13, 0.8)), bed(0, trip + LOOP, 110 * low, 0.9, 0.6, (6, 0.5),
                                                                       "brown", "low"),
                 crackle(0, trip + LOOP, [(0, 70), (1, 70)])]
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
            L = [*thunder(fx, 2.0 + 1.5 * s), buzz(0, 0.25, 0.8, 0.5), burst(0.0, 0.15, 3000, 1.0, q=0.5),
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

    elif el == "holy":
        if e == "charge":
            L = [*choir(0, charge, root, amp=[(0, 0), (1, 1)], attack=0.3),
                 sparkle(0, charge, [(0, 3), (1, 25)], (3000, 9000), (0.2, 0.6), 0.4)]
        elif e == "cast":
            L = [*bells(fx, 0.0, [root * 4], 0.0, 0.9), *choir(0, 1.2, root * 2, (0, 4, 7), "a", 0.7, 0.03,
                                                                  decay_curve(2)),
                 *whoosh(fx, 0.0, 0.5, 3000, 1.2, gain=0.4)]
        elif e == "travel":
            L = [*choir(0, trip + LOOP, root * 2, (0, 7, 12), "o", 0.6, 0.3),
                 sparkle(0, trip + LOOP, [(0, 10), (1, 10)], (3000, 9000), (0.2, 0.6), 0.4)]
        else:
            L = [*bells(fx, 0.0, [root * 2, root * 3], 0.03, 1.0), *choir(0, 2.0, root * 2, (0, 4, 7, 12), "a", 0.8,
                                                                          0.02, decay_curve(1.5)),
                 sparkle(0, 1.5, [(0, 120), (1, 0)], (3000, 10_000), (0.1, 0.5))]
            extra = {"space": 2.5, "wet": 0.3}

    elif el == "shadow":
        def drone(start, dur, gain, rise=1.0):
            return [tone(start, dur, f, f * rise, gain / 2, "glottal", brightness=0.2, sub=0.6, rough=(0.4, 9.0),
                         jitter=0.3, attack=0.3, release=0.3) for f in (48 * low, 48 * low * 1.06)]
        def whispers(start, dur, gain):
            return Syllable(round(start, 3), round(dur, 3), [(0, 100), (1, 100)], "noise",
                            formants=[(hz, 150, g) for hz, g in zip(VOWELS["o"][:3], (1.0, 0.7, 0.4), strict=True)],
                            mouth=[(0, 0.8), (0.3, 1.3), (0.6, 0.9), (1, 1.2)], attack=0.2, release=0.3,
                            pulses=(3.0, 0.6, 2.0), gain=gain)
        if e == "charge":
            L = [*drone(0, charge, 0.9, 1.3), whispers(0, charge, 0.4),
                 swell(0, charge, 150, 600, gain=0.6, wobble=(5, 0.5), color="brown")]
        elif e == "cast":
            L = [swell(0, 0.5, 300, 1500, q=0.7, gain=1.0, wobble=(8, 0.3), amp=[(0, 0), (0.95, 1), (1, 0)]),
                 boom(0.45, 1.0, 90, 0.9), whispers(0.4, 0.8, 0.3)]
        elif e == "travel":
            L = [*drone(0, trip + LOOP, 0.8), whispers(0, trip + LOOP, 0.4)]
        else:
            L = [boom(0, 2.0 + s, 80 * low), burst(0.0, 0.08, 600, 0.8, "low"), *drone(0, 1.5, 0.6, 0.7),
                 whispers(0.1, 1.5, 0.4)]
            extra = {"space": 2.0, "wet": 0.3, "drive": 1.5}

    elif el == "nature":
        def bubbles(start, dur, rate, gain=0.7):
            return Scatter(round(start, 3), round(dur, 3), rate, "drop", (250 * low, 1200 * low), (0.008, 0.03),
                           (0.2, 1.0), gain)
        def rustle(start, dur, rate, gain=0.5):
            return Scatter(round(start, 3), round(dur, 3), rate, "pop", (2000, 9000), (0.0005, 0.002), (0.1, 1.0), gain)
        if e == "charge":
            L = [rustle(0, charge, [(0, 100), (1, 600)]), bubbles(0, charge, [(0, 5), (1, 40)]),
                 tone(0, charge, 30, 60, 0.4, "pulse", pulse_width=0.1, brightness=0.3,
                      formants=[(600, 250, 1.0), (1400, 400, 0.5)], jitter=1.0)]
        elif e == "cast":
            L = [*whoosh(fx, 0.0, 0.6, 1600, 1.0, gain=0.8), rustle(0, 0.6, [(0, 900), (1, 0)]),
                 bed(0.05, 0.8, 6000, 1.0, 0.4, (20, 0.5), kind="high")]
        elif e == "travel":
            L = [bubbles(0, trip + LOOP, [(0, 30), (1, 30)]),
                 bed(0, trip + LOOP, 5500, 1.2, 0.4, (3, 0.4), kind="high"),
                 rustle(0, trip + LOOP, [(0, 150), (1, 150)], 0.3)]
        else:
            L = [bubbles(0, 1.2, [(0, 300), (1, 0)], 0.9), burst(0.0, 0.25, 1200, 0.8, "band", 0.7),
                 Noise(0.0, 0.3, [(0, 1600), (1, 900)], "band", 1.5, amp=decay_curve(4), wobble=(35, 0.9), gain=0.6),
                 bed(0.1, 1.5, 6000, 1.0, 0.4, (6, 0.5), kind="high")]
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
