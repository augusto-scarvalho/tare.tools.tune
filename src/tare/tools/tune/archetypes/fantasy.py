"""Archetypes for creatures that do not exist (yet)."""
from ..spec import Syllable
from . import Ctx, archetype, geo


@archetype("monster")
def monster(c: Ctx):
    """Fantasy beast: deep brute roar, piercing screech or wet gurgling growl."""
    g = c.g
    kind = g.choice("kind", ["brute", "screecher", "gurgler"])
    tract = 2 ** (1.8 * (0.45 - c.size)) * g.lrange("tract", 0.85, 1.15)
    dur = c.dur((0.5 + 1.3 * c.size) * g.range("dur", 0.8, 1.3))
    if kind == "brute":
        f0 = geo(200, 32, c.size) * g.lrange("f0", 0.8, 1.25)
        peak = g.range("peak_t", 0.1, 0.35)
        contour = c.contour([(0, f0 * 0.8), (peak, f0 * g.range("rise", 1.1, 1.5)), (1, f0 * 0.6)])
        mouth = [(0, 0.6), (peak, 1.25), (1, 0.75)]
        formants = c.formants(g.choice("vowel", ["a", "o", "ae"]), tract)
        return c.voice([
            Syllable(start=0, dur=dur, pitch=contour, brightness=0.45 + 0.4 * c.aggr,
                     sub=0.6 + 0.6 * c.aggr, rough=(0.5 + 0.4 * c.aggr, geo(45, 18, c.size)),
                     jitter=0.8 + 1.5 * c.aggr, breath=0.25, formants=formants, mouth=mouth,
                     attack=c.attack(0.05 + 0.1 * c.size), release=0.3 * c.call.duration),
            Syllable(start=0, dur=dur, pitch=[(0, 100), (1, 100)], source="noise",  # air through the throat
                     formants=formants, mouth=mouth, attack=c.attack(0.08), release=0.35, gain=0.45),
        ], drive=2 + 3 * c.aggr, space=0.8 + 1.6 * c.size, wet=0.2 + 0.15 * c.size)
    if kind == "screecher":
        f0 = geo(1500, 380, c.size) * g.lrange("f0", 0.85, 1.2)
        contour = c.contour([(0, f0 * 0.7), (0.15, f0 * g.range("rise", 1.2, 1.6)), (1, f0 * 0.75)])
        return c.voice([Syllable(
            start=0, dur=dur * 0.8, pitch=contour, brightness=1.0, jitter=1.5 + 1.5 * c.aggr,
            vibrato=(g.range("vib", 7, 14), 0.8), rough=(0.35 + 0.3 * c.aggr, g.range("rr", 60, 110)),
            sub=0.3 * c.aggr, breath=0.15, ring=(f0 * g.range("ring", 0.4, 0.7), 0.25 + 0.2 * c.aggr),
            formants=c.formants(g.choice("vowel", ["i", "e", "ae"]), tract * 1.1),
            mouth=[(0, 0.8), (0.15, 1.2), (1, 0.9)], attack=c.attack(0.02), release=0.2)],
            drive=1.5 + 2.5 * c.aggr, space=0.7 + c.size, wet=0.2)
    f0 = geo(160, 38, c.size) * g.lrange("f0", 0.85, 1.2)  # gurgler: pulsed growl + bubbles
    syllables = [Syllable(
        start=0, dur=dur, pitch=c.contour([(0, f0), (0.5, f0 * 1.1), (1, f0 * 0.8)]), brightness=0.35,
        pulses=(g.range("rate", 9, 20), 0.85, 1.5), sub=0.5 + 0.5 * c.aggr, jitter=1.5, breath=0.35,
        rough=(0.4 + 0.4 * c.aggr, 30), formants=c.formants("u", tract),
        mouth=[(0, 0.7), (0.4, 1.1), (1, 0.8)], attack=c.attack(0.04), release=0.25)]
    syllables += _bubbles(c, dur, rate=g.range("bubble_rate", 8, 18), size=c.size, gain=0.5)
    return c.voice(syllables, drive=1.5 + 2 * c.aggr, space=0.6 + c.size, wet=0.2)


def _bubbles(c: Ctx, dur: float, rate: float, size: float, gain: float) -> list[Syllable]:
    """Short rising sine blips at random times: liquid, slimy, wet."""
    g, out, t, i = c.g, [], 0.0, 0
    while t < dur:
        f = geo(2200, 260, size) * 2 ** (1.4 * (g.u(f"bubble_f{i}") - 0.5)) * 2 ** (c.call.pitch / 12)
        d = geo(0.018, 0.07, size) * (0.6 + 0.8 * g.u(f"bubble_d{i}"))
        out.append(Syllable(start=t, dur=d, pitch=[(0, f), (1, f * g.range(f"bubble_rise{i}", 1.3, 2.4))],
                            source="sine", attack=0.002, release=d * 0.7,
                            gain=gain * (0.4 + 0.6 * g.u(f"bubble_a{i}"))))
        t += (0.3 + 1.4 * g.u(f"bubble_gap{i}")) / rate
        i += 1
    return out


@archetype("slime")
def slime(c: Ctx):
    """Gooey blob: bubbling pops over a soft wet gurgle."""
    g = c.g
    dur = c.dur(g.range("dur", 0.4, 0.9) * (0.7 + 0.8 * c.size))
    rate = g.range("rate", 14, 40) * (1 + c.aggr) / (0.6 + 0.8 * c.size)
    syllables = _bubbles(c, dur, rate, c.size, gain=1.0)
    if c.size > 0.3 or c.aggr > 0.5:
        f0 = geo(220, 60, c.size)
        syllables.append(Syllable(
            start=0, dur=dur, pitch=c.contour([(0, f0), (1, f0 * 0.85)]), brightness=0.2,
            pulses=(g.range("glug", 6, 14), 0.9, 2.0), breath=0.4, jitter=1.0,
            formants=c.formants("u", 2 ** (1.2 * (0.5 - c.size))),
            attack=c.attack(0.05), release=0.15, gain=0.35 + 0.4 * c.aggr))
    return c.voice(syllables, drive=0.3 + c.aggr, space=0.4, wet=0.15)


@archetype("spirit")
def spirit(c: Ctx):
    """Ghostly moan: breath through a slowly morphing mouth, with an eerie whistle."""
    g = c.g
    dur = c.dur(g.range("dur", 1.2, 2.4) * (0.8 + 0.5 * c.size))
    tract = 2 ** (1.2 * (0.5 - c.size)) * g.lrange("tract", 0.9, 1.1)
    f0 = geo(900, 160, c.size) * g.lrange("f0", 0.85, 1.2) * (1 + 0.5 * c.aggr)
    wah = g.range("wah", 1.2, 1.6)
    mouth = [(0, 0.8), (g.range("wah_t", 0.3, 0.6), wah), (1, 0.75)]
    syllables = [
        Syllable(start=0, dur=dur, pitch=[(0, 100), (1, 100)], source="noise",
                 formants=c.formants(g.choice("vowel", ["o", "u", "a"]), tract, widths=(60, 80, 120, 200)),
                 mouth=mouth, amp=[(0, 0.5), (0.4, 1.0), (1, 0.6)], attack=c.attack(0.3), release=0.5),
        Syllable(start=dur * 0.1, dur=dur * 0.85, pitch=c.contour([(0, f0), (0.5, f0 * g.range("glide", 1.05, 1.4)),
                                                                  (1, f0 * 0.8)]),
                 source="sine", vibrato=(g.range("vib", 3, 6), 0.4 + 1.2 * c.aggr), jitter=0.3,
                 ring=(f0 * 0.5, 0.4 * c.aggr), attack=c.attack(0.4), release=0.5, gain=0.35 + 0.3 * c.aggr),
    ]
    return c.voice(syllables, drive=0.3 + c.aggr, space=2.5 + c.size, wet=0.45)


@archetype("robot")
def robot(c: Ctx):
    """Construct or droid: stepped pitches, ring-modulated metallic resonances, bit crush."""
    g = c.g
    base = geo(700, 90, c.size) * g.lrange("f0", 0.8, 1.25)
    n = c.repeats(g.int("n_syl", 1, 3))
    steps = g.int("steps", 3, 7)
    sdur = c.dur(g.range("sdur", 0.25, 0.6) * (0.7 + 0.6 * c.size))
    scale = [0, 3, 5, 7, 10, 12, -2, -5]  # semitones; the species picks a melody from it
    metal = [(base * r, 30 + 40 * c.size, a) for r, a in ((2.0, 1.0), (5.4, 0.6), (8.9, 0.4))]
    syllables = []
    for k in range(n):
        pitch, eps = [], 1e-3
        for j in range(steps):
            f = base * 2 ** (scale[int(g.u(f"note{j}") * len(scale)) % len(scale)] / 12)
            pitch += [(j / steps + (eps if j else 0), f), ((j + 1) / steps, f)]
        syllables.append(Syllable(
            start=k * sdur * 1.3, dur=sdur, pitch=c.contour(pitch), source="pulse",
            pulse_width=g.range("width", 0.15, 0.5), brightness=0.9,
            ring=(g.lrange("ring", 30, 400), 0.4 + 0.5 * c.aggr), formants=metal,
            attack=c.attack(0.005), release=0.03))
    return c.voice(syllables, crush=0.25 + 0.5 * g.u("crush"), drive=0.5 + 2 * c.aggr, space=0.4, wet=0.15)
