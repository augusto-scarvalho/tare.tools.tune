"""Archetypes modelled on real animal vocalisation."""
from ..spec import Syllable
from . import VOWELS, Ctx, archetype, geo


@archetype("mammal")
def mammal(c: Ctx):
    """Squeak, bark, howl or roar, depending on size and aggression."""
    g = c.g
    f0 = geo(1100, 55, c.size) * g.lrange("f0", 0.8, 1.25)
    dur = c.dur((0.22 + 1.0 * c.size) * g.range("dur", 0.75, 1.35))
    tract = 2 ** (1.7 * (0.5 - c.size)) * g.lrange("tract", 0.88, 1.12)
    formants = c.formants(g.choice("vowel", ["a", "o", "u", "e", "ae"]), tract)
    peak = g.range("peak_t", 0.12, 0.5)
    contour = c.contour([(0, f0 * g.range("c0", 0.7, 0.95)), (peak, f0 * g.range("c1", 1.05, 1.45)),
                         (1, f0 * g.range("c2", 0.45, 0.85) * (1 - 0.15 * c.aggr))])
    open_t = g.range("open_t", 0.1, 0.45)
    n = c.repeats(1 if c.size > 0.65 else g.int("n_syl", 1, 3))
    gap = g.range("gap", 1.05, 1.4)
    syllables = []
    for k in range(n):
        d = dur * 0.85 ** k
        syllables.append(Syllable(
            start=sum(dur * 0.85 ** j * gap for j in range(k)), dur=d,
            pitch=[(t, f * 0.94 ** k) for t, f in contour],
            brightness=0.3 + 0.55 * c.aggr,
            vibrato=(g.range("vib_rate", 4, 7), 0.6 * (1 - c.aggr) * g.u("vib")),
            jitter=0.15 + 1.2 * c.aggr * g.range("jit", 0.5, 1),
            sub=1.3 * max(0.0, c.aggr - 0.3) * (0.3 + 0.7 * c.size),
            rough=(0.85 * c.aggr * g.range("rough", 0.6, 1), geo(70, 22, c.size) * g.range("rr", 0.8, 1.25)),
            breath=0.05 + 0.35 * c.aggr * g.u("breath"),
            formants=formants,
            mouth=[(0, 0.7), (open_t, 1.15), (1, g.range("close", 0.65, 0.9))],
            attack=c.attack(0.008 + 0.12 * c.size * g.u("att")), release=0.04 + 0.35 * c.size * c.call.duration,
            amp=[(0, 0.8), (peak, 1.0), (1, 0.7)],
        ))
    return c.voice(syllables, drive=0.5 + 3.5 * c.aggr, space=0.25 + 1.4 * c.size, wet=0.12 + 0.18 * c.size)


@archetype("bird")
def bird(c: Ctx):
    """Whistled song of sweeping syllables; aggressive birds squawk instead."""
    g = c.g
    if c.aggr > 0.6 or g.choice("voice", ["song", "song", "song", "squawk"]) == "squawk":
        f0 = geo(900, 320, c.size) * g.lrange("f0", 0.85, 1.2)
        d = c.dur(0.22 * g.range("dur", 0.8, 1.3))
        n = c.repeats(g.int("n_calls", 2, 4))
        tract = 2 ** (1.2 * (0.4 - c.size))
        syllables = [Syllable(
            start=k * d * 1.45, dur=d, pitch=c.contour([(0, f0), (0.3, f0 * 1.15), (1, f0 * 0.8)]),
            brightness=0.85, jitter=0.6 + c.aggr, rough=(0.3 + 0.3 * c.aggr, 45), breath=0.2, sub=0.5 * c.aggr,
            formants=[(1500 * tract, 300, 1.0), (2600 * tract, 400, 0.6), (3600 * tract, 500, 0.3)],
            mouth=[(0, 0.9), (0.3, 1.1), (1, 0.85)], attack=c.attack(0.01), release=0.08) for k in range(n)]
        return c.voice(syllables, drive=1 + 2 * c.aggr, space=0.6, wet=0.15)

    base = geo(6500, 1600, c.size) * g.lrange("f0", 0.85, 1.15)
    shape = g.choice("shape", ["down", "up", "arch", "trill"])
    # an alarm/attack call is a few urgent notes, not the whole song
    n = c.call.repeats + 1 if c.call.repeats else g.int("n_syl", 4, 9)
    sdur, gap = c.dur(g.range("sdur", 0.05, 0.14)), g.range("gap", 0.03, 0.1) * c.call.duration
    drift, sweep = g.range("drift", 0.93, 1.04), g.range("sweep", 1.25, 2.0)
    syllables = []
    for k in range(n):
        f = base * drift ** k
        pitch = {"down": [(0, f * sweep), (1, f / sweep ** 0.3)],
                 "up": [(0, f / sweep ** 0.5), (1, f * sweep ** 0.5)],
                 "arch": [(0, f), (0.4, f * sweep), (1, f * 0.9)],
                 "trill": [(0, f), (1, f * 0.95)]}[shape]
        syllables.append(Syllable(
            start=k * (sdur + gap), dur=sdur, pitch=c.contour(pitch), source="sine",
            vibrato=(g.range("trill_rate", 25, 55), 1.5) if shape == "trill" else (0.0, 0.0),
            jitter=0.1 + 0.4 * c.aggr, rough=(0.4 * c.aggr, 60), attack=c.attack(0.005), release=sdur * 0.4,
            amp=[(0, 0.7), (0.3, 1.0), (1, 0.6)]))
    return c.voice(syllables, space=0.9, wet=0.18)


@archetype("insect")
def insect(c: Ctx):
    """Cricket chirps, fly/bee buzz or cicada drone."""
    g = c.g
    kind = g.choice("kind", ["cricket", "buzz", "cicada"])
    if kind == "cricket":  # a pure carrier chopped into pulses, grouped into chirps
        f = geo(5000, 2600, c.size) * g.lrange("f", 0.9, 1.1)
        rate, n_pulse = g.range("rate", 25, 40) * (1 + 0.3 * c.aggr), g.int("n_pulse", 3, 5)
        n = c.repeats(g.int("n_chirp", 3, 5)) + (1 if c.call.repeats else 0)
        period = g.range("gap", 0.25, 0.45) * c.call.duration
        syllables = [Syllable(start=k * period, dur=n_pulse / rate, pitch=c.contour([(0, f), (1, f * 0.98)]),
                              source="sine", pulses=(rate, 1.0, 3.0), attack=0.003, release=0.01)
                     for k in range(n)]
        return c.voice(syllables, space=0.4, wet=0.1)
    if kind == "buzz":  # thin pulse wave at the wing-beat rate, with a doppler wobble
        f0 = geo(260, 120, c.size) * g.lrange("f0", 0.9, 1.1)
        return c.voice([Syllable(
            start=0, dur=c.dur(g.range("dur", 0.9, 1.6)), pitch=c.contour([(0, f0), (1, f0 * 0.97)]),
            source="pulse", pulse_width=0.15, brightness=0.9, vibrato=(g.range("wob", 2, 5), 1.2 + c.aggr),
            jitter=0.4, rough=(0.3 * c.aggr, 35),
            formants=[(1400, 600, 0.6), (3200, 900, 1.0), (5500, 1500, 0.5)],
            amp=[(0, 0.6), (0.3, 1.0), (0.7, 0.8), (1, 0.5)], attack=c.attack(0.08), release=0.25)],
            space=0.3, wet=0.08)
    rate, hz = g.range("rate", 90, 180), geo(6000, 3500, c.size)  # cicada: noise through narrow bands
    return c.voice([Syllable(
        start=0, dur=c.dur(g.range("dur", 1.2, 2.2)), pitch=[(0, 100), (1, 100)], source="noise",
        pulses=(rate * 2 ** (c.call.pitch / 12), 0.9, 2.0),
        formants=[(hz * 2 ** (c.call.pitch / 12), 600, 1.0), (hz * 1.5, 900, 0.5)],
        mouth=[(0, 1.0), (1, 2 ** (c.call.bend / 12))],
        amp=[(0, 0.4), (0.2, 1.0), (0.8, 1.0), (1, 0.5)], attack=c.attack(0.15), release=0.3)],
        space=0.3, wet=0.1)


@archetype("reptile")
def reptile(c: Ctx):
    """Breathy hiss, maybe a rattle; big angry ones add a low growl underneath."""
    g = c.g
    k = 1 / (0.7 + 0.6 * c.size) * 2 ** (c.call.pitch / 24)
    dur = c.dur(g.range("dur", 0.6, 1.3) * (0.8 + 0.6 * c.size))
    rattle = g.chance("rattle", 0.4)
    syllables = [Syllable(
        start=0, dur=dur, pitch=[(0, 100), (1, 100)], source="noise",
        formants=[(2600 * k, 900, 0.6), (4800 * k, 1600, 1.0), (7500 * k, 2500, 0.5)],
        mouth=[(0, 0.9), (0.3, 1.05), (1, 0.95 * 2 ** (c.call.bend / 24))],
        pulses=(g.range("rattle_rate", 35, 60), 0.8, 1.5) if rattle else (0.0, 0.0, 2.0),
        amp=[(0, 0.5), (0.25, 1.0), (1, 0.6)], attack=c.attack(0.12 * c.size + 0.03), release=0.25)]
    if c.aggr > 0.5 and c.size > 0.4:
        f0 = geo(140, 45, c.size)
        syllables.append(Syllable(
            start=0.05, dur=dur * 0.9, pitch=c.contour([(0, f0), (1, f0 * 0.7)]),
            brightness=0.4, sub=0.9, rough=(0.7, 25), jitter=1.0, breath=0.3,
            formants=c.formants("o", 0.55, gains=(1.0, 0.6, 0.3, 0.1)),
            attack=0.1, release=0.3, gain=0.8 * c.aggr))
    return c.voice(syllables, drive=1 + 2 * c.aggr, space=0.3 + c.size, wet=0.15)


@archetype("amphibian")
def amphibian(c: Ctx):
    """Pulsed croak ('rrr'), often in two parts ('rib-bit')."""
    g = c.g
    f0 = geo(450, 90, c.size) * g.lrange("f0", 0.85, 1.2)
    rate = g.range("rate", 14, 32) * (1.2 - 0.4 * c.size)
    vowel = VOWELS[g.choice("vowel", ["o", "u", "a"])]
    tract = 2 ** (1.2 * (0.5 - c.size))
    formants = [(f * tract, 100 * tract, a) for f, a in zip(vowel[:3], (1.0, 0.6, 0.25), strict=True)]
    d1 = c.dur(g.range("d1", 0.12, 0.3) * (0.8 + 0.6 * c.size))
    syllables = [Syllable(start=0, dur=d1, pitch=c.contour([(0, f0), (1, f0 * 0.9)]), pulses=(rate, 0.95, 2.5),
                          brightness=0.5 + 0.3 * c.aggr, jitter=0.4, rough=(0.4 * c.aggr, 30), formants=formants,
                          mouth=[(0, 0.8), (0.5, 1.1), (1, 0.9)], attack=c.attack(0.01), release=0.04)]
    if g.chance("two_part", 0.65) and c.call.name not in ("hurt", "death"):
        syllables.append(Syllable(start=d1 * 1.25, dur=d1 * 0.6, pitch=c.contour([(0, f0 * 1.2), (1, f0 * 1.1)]),
                                  pulses=(rate * 1.3, 0.9, 2.5), brightness=0.6, jitter=0.4,
                                  formants=formants, mouth=[(0, 0.9), (1, 1.15)], attack=0.01, release=0.03))
    return c.voice(syllables, drive=0.5 + c.aggr, space=0.5, wet=0.15)
