"""Ambience: seamless loops of a place, plus its characteristic one-shot ("accent").

    loop    16 s bed that loops without a seam (rain, wind, fire, a stream, a cave...)
    accent  the event a game scatters over the loop: thunder, a gust, a bird, an owl, a drip

Power is intensity (drizzle .. downpour, breeze .. gale); size is the space (bigger, further,
more reverberant). Forests and nights borrow their birds and crickets from the creature
archetypes, so they sing with the same voices as the bestiary.
"""
from ..archetypes import VOWELS
from ..creature import Creature
from ..spec import Noise, Scatter, Syllable, Voice
from . import Fx, bell_curve, decay_curve, recipe
from .magic import thunder
from .physical import splits

LENGTH = 16.0       # loop length, seconds
XFADE = 1.0         # loop crossfade


def band(hz, q=0.7, gain=1.0, wobble=(0.3, 0.3), color="white", kind="band", dur=LENGTH + XFADE, start=0.0,
         amp=None, hz_end=None):
    return Noise(round(start, 3), round(dur, 3), [(0, hz), (1, hz_end or hz)], kind, q, color,
                 amp or [(0, 1), (1, 1)], attack=0.05, release=0.05, wobble=wobble, gain=gain)


def drops(rate, hz, decay, gain=1.0, dur=LENGTH + XFADE, start=0.0, event="drop", level=(0.1, 1.0)):
    rate = rate if isinstance(rate, list) else [(0, rate), (1, rate)]
    return Scatter(round(start, 3), round(dur, 3), rate, event, hz, decay, level, gain)


def gusts(fx: Fx, n: int, floor: float = 0.35) -> list[tuple[float, float]]:
    """Slow swells over the loop, starting and ending at the same level so the loop is seamless."""
    pts = [(0.0, floor)]
    for k in range(n):
        t = (k + 0.3 + 0.4 * fx.g.u(f"gust{k}")) / n
        pts.append((round(t, 3), round(floor + (1 - floor) * (0.5 + 0.5 * fx.g.u(f"gl{k}")), 3)))
    pts.append((1.0, floor))
    return pts


def place(voice: Voice, at: float, gain: float = 1.0, end: float = LENGTH + XFADE) -> list[Syllable]:
    """A creature's call as syllables placed at `at` seconds in a bigger scene, finishing before `end`."""
    at = max(min(at, end - voice.duration), 0.0)
    out = []
    for s in voice.syllables:
        s.start = round(s.start + at, 4)
        s.gain *= gain
        out.append(s)
    return out


def owl(start: float, pitch: float) -> list[Syllable]:
    """Hoo, hoo-hoo: soft sine hoots through an 'u' mouth."""
    f = [(hz, bw, g) for hz, bw, g in zip(VOWELS["u"][:2], (120, 200), (1.0, 0.3), strict=True)]
    out, t = [], start
    for k, d in enumerate((0.45, 0.2, 0.55)):
        out.append(Syllable(round(t, 3), d, [(0, pitch * 1.03), (0.3, pitch), (1, pitch * 0.92)], "sine",
                            breath=0.15, formants=f, attack=0.06, release=0.12, gain=0.8 if k else 1.0))
        t += d + (0.35 if k == 0 else 0.08)
    return out


@recipe("ambience", ("loop", "accent"),
        ("rain", "wind", "fire", "stream", "cave", "forest", "night", "storm", "sea", "dungeon"), loops=("loop",))
def ambience(fx: Fx):
    """Places: rain, wind, fire, stream, cave, forest, night, storm, sea, dungeon (loop + accent)."""
    st, s, p, e = fx.style, fx.size, fx.power, fx.event
    L, extra = [], {}
    loop = e == "loop"

    if st in ("rain", "storm"):
        heavy = p if st == "rain" else max(p, 0.7)
        if loop:
            bed = 1.0 if st == "rain" else 0.45   # in a storm the thunder takes over
            L = [band(3500, 0.5, bed, (0.25, 0.15)), band(900, 0.6, 1.2 * bed, (0.3, 0.2)),
                 band(400, 0.7, bed, (0.2, 0.2), "brown", "low"),
                 drops(300 + 1200 * heavy, (1500, 6000), (0.003, 0.01), 0.7),
                 drops(150 + 600 * heavy, (2000, 9000), (0.0005, 0.002), 0.5, event="pop"),
                 drops(2 + 6 * heavy, (600, 2500), (0.004, 0.012), 0.6, event="pop", level=(0.5, 1.0))]   # big drops
            if st == "storm":
                L += [band(500, 3.0, 0.35, (0.15, 0.6), amp=gusts(fx, 3)),
                      band(150, 0.7, 3.0, (0.3, 0.7), "brown", "low", amp=gusts(fx, 6, 0.05))]   # thunder rolling
        elif st == "rain":   # drips off a roof into a puddle
            L = [drops([(0, 6), (1, 2)], (700, 2200), (0.015, 0.04), 1.0, 2.5, level=(0.4, 1.0))]
            extra = {"space": 0.8, "wet": 0.2}
        else:
            L = thunder(fx, 4.0 + 3 * s)
            extra = {"space": 2.5, "wet": 0.3, "lowpass": 3000 + 6000 * (1 - s)}

    elif st == "wind":
        if loop:
            # a narrow, whistling band sweeping up through each gust (CLAP-guided search, confirmed by the judge)
            hz = (700 + 600 * p) * (0.85 + 0.3 * fx.g.u("pitch"))
            L = [band(hz, 6.0, 0.25, (1.5, 0.68), amp=gusts(fx, 2, 0.6), hz_end=hz * 1.67),
                 band(hz * 2.5, 5.4, 0.03, (0.2, 0.7), amp=gusts(fx, 3, 0.4)),
                 band(250, 0.8, 1.0, (0.4, 0.4), "brown", amp=gusts(fx, 2, 0.6)),
                 band(500, 0.9, 0.35, (0.6, 0.4), amp=gusts(fx, 3, 0.6))]
        else:
            L = [band(400, 2.0, 1.0, (0.3, 0.4), dur=3.5, amp=bell_curve(0.4, 1.5), hz_end=900),
                 band(1100, 8.0, 0.5, (0.4, 0.6), dur=3.5, amp=bell_curve(0.45, 2.5), hz_end=1600)]

    elif st == "fire":
        if loop:
            L = [band(500, 0.5, 0.08, (8.0, 0.5)), band(120, 0.8, 0.6, (3.0, 0.5), "brown", "low"),
                 band(6000, 0.7, 0.1, (6.0, 0.6)),
                 drops(8 + 14 * p, (800, 7000), (0.0005, 0.003), 2.0, event="pop", level=(0.05, 1.0)),
                 drops(2 + 4 * p, (300, 1500), (0.004, 0.015), 0.5, event="pop"),
                 band(5000, 0.7, 0.04, (2.0, 0.5), kind="high")]
        else:  # a log settles
            L = [fx.strike("wood", start=0.0, size=0.5, gain=0.6, prefix="log"),
                 fx.strike("wood", start=0.12, size=0.3, gain=0.4, prefix="log2"),
                 drops([(0, 200), (1, 0)], (1000, 7000), (0.0003, 0.002), 0.8, 1.5, event="pop"),
                 band(600, 0.6, 0.7, (8.0, 0.6), dur=1.8, amp=decay_curve(2))]

    elif st == "stream":
        if loop:
            L = [drops(400 + 800 * p, (300, 2500), (0.005, 0.02), 1.0), band(1500, 0.4, 0.6, (1.5, 0.3)),
                 band(300, 0.7, 0.4, (0.8, 0.3), "brown", "low")]
        else:  # something jumps in
            L = [drops([(0, 400), (1, 0)], (300, 2000), (0.005, 0.03), 1.0, 0.8),
                 Noise(0.0, 0.5, [(0, 1200), (1, 3000)], "band", 0.8, amp=decay_curve(5), attack=0.005, gain=0.8)]

    elif st == "cave":
        if loop:
            L = [band(120, 0.8, 0.05, (0.1, 0.3), "brown", "low"), band(1200, 1.0, 0.04, (0.1, 0.5)),
                 band(400, 0.8, 0.06, (0.1, 0.4)), band(8000, 0.7, 0.03, (0.1, 0.4)),
                 drops([(0, 3.5), (1, 3.5)], (900, 2600), (0.02, 0.05), 1.0, level=(0.2, 1.0))]
            extra = {"space": 3.0, "wet": 0.4}
        else:
            L = [drops([(0, 3), (1, 3)], (900, 2600), (0.02, 0.05), 1.0, 1.0, level=(0.6, 1.0))]
            extra = {"space": 3.0, "wet": 0.45}

    elif st == "forest":
        birds = [Creature("bird", species=fx.sfx.species * 7 + k, size=0.15 + 0.3 * fx.g.u(f"bs{k}")) for k in range(3)]
        if loop:
            L = [band(3500, 0.6, 0.5, (0.15, 0.6), amp=gusts(fx, 3)), band(200, 0.7, 0.06, (0.1, 0.4), "brown", "low"),
                 band(800, 0.7, 0.12, (0.15, 0.5), amp=gusts(fx, 3)),
                 drops([(0, 30), (1, 30)], (2500, 9000), (0.0005, 0.002), 0.25, event="pop")]
            for k in range(int(5 + 6 * p)):
                b = birds[k % len(birds)]
                at = LENGTH * fx.g.u(f"bird{k}")
                L += place(b.voice("idle", take=k), at, 0.35 + 0.4 * fx.g.u(f"bv{k}"))
        else:
            L = place(birds[int(fx.rand("who") * 3)].voice("alert", take=fx.take), 0.0)
        extra = {"space": 1.2, "wet": 0.15}

    elif st == "night":
        cricket = Creature("insect", species=fx.sfx.species * 7 + 1, size=0.15, genes={"kind": 0.1})
        if loop:
            L = [band(250, 0.7, 0.05, (0.1, 0.4), "brown", "low"), band(3000, 0.5, 0.04, (0.1, 0.5)),
                 band(9500, 3.0, 0.35, (22.0, 0.9)), band(12000, 4.0, 0.2, (35.0, 0.9)),   # far insects trilling
                 band(800, 0.6, 0.05, (0.1, 0.4))]
            for k in range(int(10 + 10 * p)):    # a chorus of crickets, each one at its own place in time
                c = cricket.member(k % 4)
                L += place(c.voice("idle", take=k), LENGTH * k / (10 + 10 * p) + 0.3 * fx.g.u(f"c{k}"),
                           0.25 + 0.35 * fx.g.u(f"cv{k}"))
        else:
            L = owl(0.0, 330 + 120 * (1 - s))
        extra = {"space": 1.5, "wet": 0.2}

    elif st == "sea":
        if loop:
            period = 6.0 + 3 * s
            waves = int(LENGTH // period) or 1
            period = LENGTH / waves
            for k in range(waves):     # each wave overlaps the next by the crossfade, the last one wraps
                t0 = k * period
                L += [Noise(round(t0, 3), round(period + XFADE, 3), [(0, 300), (0.55, 1200), (0.65, 3000), (1, 800)],
                            "low", 0.7, amp=[(0, 0.15), (0.55, 0.7), (0.62, 1.0), (1, 0.15)], attack=0.3, release=0.3,
                            wobble=(1.5, 0.3), gain=1.0),
                      Scatter(round(t0 + 0.62 * period, 3), round(0.38 * period + XFADE, 3), [(0, 1500), (1, 100)],
                              "pop", (2000, 10_000), (0.0005, 0.002), (0.1, 1.0), 0.5)]
            L.append(band(150, 0.8, 0.5, (0.1, 0.3), "brown", "low"))
        else:   # a big wave breaks
            L = [Noise(0.0, 4.0, [(0, 400), (0.4, 2500), (1, 700)], "low", 0.7, amp=bell_curve(0.35, 1.2), attack=0.5,
                       release=0.5, wobble=(2.0, 0.3)),
                 Scatter(1.4, 2.6, [(0, 2500), (1, 50)], "pop", (2000, 10_000), (0.0005, 0.002), (0.1, 1.0), 0.6)]

    else:   # dungeon
        if loop:
            root = 38 + 10 * fx.g.u("root")
            L = [Syllable(0.0, round(LENGTH + XFADE, 3), [(0, f), (1, f)], "glottal", brightness=0.15, sub=0.4,
                          jitter=0.2, attack=1.0, release=1.0, gain=0.35) for f in (root, root * 1.01, root * 1.5)]
            L += [band(450, 6.0, 0.25, (0.08, 0.7), amp=gusts(fx, 2, 0.2)),
                  drops([(0, 0.3), (1, 0.3)], (800, 2200), (0.02, 0.05), 0.6, level=(0.3, 1.0))]
            extra = {"space": 3.5, "wet": 0.45}
        else:   # chains
            hits = [(round(0.05 * k + 0.04 * fx.rand(f"h{k}"), 3), round(0.3 + 0.7 * fx.rand(f"g{k}"), 3), 0.0008)
                    for k in range(14)]
            L = [fx.strike("iron", size=0.05, hits=hits, gain=0.8, prefix="link", dur=1.5),
                 fx.strike("iron", size=0.2, hits=hits[::2], gain=0.5, prefix="link2", dur=1.5)]
            extra = {"space": 2.5, "wet": 0.35}

    if loop:
        extra["loop"] = XFADE
        extra.setdefault("space", 0.0)
    gain = 10 ** (-12 * (1 - p) / 20) if loop else 1.0
    return fx.voice(gain=gain, **splits(L), **extra)
