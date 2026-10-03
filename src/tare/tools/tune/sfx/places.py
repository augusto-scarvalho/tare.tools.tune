"""The places a tactics story moves through: a battlefield, a camp, a castle hall, a market town, a tavern, a dining
hall, the plains, the desert, the snowy mountains, a swamp, temple ruins, a ship's deck. Each is an ambience style:
a seamless 16 s loop and a characteristic one-shot (accent).

Measured on Triangle Strategy's ambience loops and Tactics Ogre: Reborn's weather (the user's own copies; analysis
only, nothing of them is kept), octave bands relative to the strongest:

    a battle far off   strongest at 0.5-1 kHz, -6 dB at 2 kHz, -16 at 4k, -21 at 8k; the level moves ~11 dB
    a crowd talking    (a bar, soldiers, five people) strongest at 500 Hz, -3 to -5 dB at 1 kHz, -8 to -13 at 2k,
                       -16 to -22 at 4k, swelling 2-3 times a second
    a dinner           bright: strongest at 4 kHz (the cutlery, ~2 clinks a second), the talk 15-20 dB under it
    plains             wind and birds: 250 Hz-8 kHz within ~6 dB, the level moving ~15 dB
    a ship at a wharf  waves strongest at 500 Hz, within ~9 dB from 250 Hz to 8 kHz; gulls strongest near 1 kHz
    a bonfire          a low roar (strongest at 63-125 Hz), the crackle flat above 500 Hz, ~12 dB under it
    strong wind        (Tactics Ogre) strongest at 250 Hz, -7 to -12 dB from 1 to 4 kHz

Desert, snow, swamp and ruins have no recording: they are built from the measured wind, water and creature voices.

Crowds are voices without words: each talker's phrase is one syllable stream (the mouth opening and closing 4-6 times a
second as its vowel drifts, the pitch rising a little and falling to the end), so a whole room is a few dozen layers.
"""
from dataclasses import replace

from ..archetypes import VOWELS
from ..creature import Creature
from ..spec import Modal, Noise, Scatter, Syllable
from . import RECIPES, Fx, bell_curve, decay_curve
from .ambience import LENGTH, XFADE, band, drops, gust_curve, gusts, place, songbird
from .physical import creak, thud

END = LENGTH + XFADE
WIDTHS, LEVELS = (90, 110, 160, 250), (1.0, 0.7, 0.35, 0.2)


def borrow(fx: Fx, kind: str, style: str, event: str = "loop", gain: float = 1.0, at: float = 0.0,
           fit: bool = False, light: bool = False, **traits) -> list:
    """Another sound's layers inside this scene (a camp's fire, a ship's bell), scaled and moved to `at`; `fit`
    pulls a one-shot earlier so it ends inside the loop; `light` leaves out its brown-noise body (the deep rumble
    under wind and sea: the measured plains and wharves have little under 125 Hz)."""
    sfx = replace(fx.sfx, kind=kind, style=style, knobs=(), era="", **traits)
    v = RECIPES[kind].design(Fx(sfx, event, fx.take))
    layers = [*v.syllables, *v.noise, *v.scatter, *v.modal]
    if light:
        layers = [x for x in layers if getattr(x, "color", "white") != "brown"]
    if fit:
        at = max(0.0, min(at, END - 0.05 - max(x.start + x.dur for x in layers)))
    return [replace(x, start=round(x.start + at, 4), gain=round(x.gain * gain, 5)) for x in layers if x.gain]


def _formants(vowel: str, tract: float, levels: tuple = LEVELS) -> list:
    return [(round(f * tract), round(w * tract), g) for f, w, g in zip(VOWELS[vowel], WIDTHS, levels, strict=True)]


def walla(fx: Fx, name: str, talkers: int, level: float = 1.0, shout: float = 0.0, busy: float = 0.5,
          women: float = 0.45, start: float = 0.0, end: float = END) -> list[Syllable]:
    """People talking without words. `busy`: how little they pause; `shout`: raised voices (higher, brighter, shorter
    phrases); `women`: the share of women's voices."""
    u = lambda key: fx.g.u(name + key)  # noqa: E731
    out = []
    for k in range(talkers):
        woman = u(f"w{k}") < women
        f = (210 if woman else 108) * (0.85 + 0.3 * u(f"f{k}")) * (1 + shout)
        tract = (1.17 if woman else 1.0) * (0.93 + 0.14 * u(f"tr{k}"))
        gain = level * (0.25 + 0.75 * u(f"g{k}") ** 1.5)          # some near, most further off
        t, j = start + (end - start) * 0.6 * u(f"t{k}"), 0
        while True:
            key = f"{k}.{j}"
            dur = 0.4 + 0.8 * u("d" + key) if shout else 0.9 + 2.3 * u("d" + key)
            if t + dur > end - 0.05:
                break
            n = max(2, int(dur * (4.2 + 1.8 * u("r" + key))))   # syllables
            mouth, amp = [(0.0, 0.8)], [(0.0, 0.3)]
            for i in range(n):
                mouth += [(round(i / n + 0.01, 4), round(0.78 + 0.4 * u(f"m{key}.{i}"), 3)),
                          (round((i + 0.55) / n, 4), 0.7)]
                amp += [(round((i + 0.12) / n, 4), round(0.6 + 0.4 * u(f"a{key}.{i}"), 3)),
                        (round((i + 0.8) / n, 4), 0.35)]
            rise = 1.0 + 0.15 * u("q" + key)
            fall = 0.82 if u("e" + key) < 0.8 else 1.15             # most phrases fall, some ask
            vowels = ("a", "ae", "e", "o") if shout else tuple(VOWELS)     # shouting opens the mouth
            vowel = vowels[int(u("v" + key) * len(vowels)) % len(vowels)]
            out.append(Syllable(round(t, 4), round(dur, 4), [(0, round(f * rise, 1)), (0.3, round(f * rise * 1.06, 1)),
                                                              (1, round(f * fall, 1))],
                                brightness=round(0.5 + 0.4 * shout, 3), jitter=0.8, rough=(0.25 * shout, 40.0),
                                breath=0.2, formants=_formants(vowel, tract, (1.0, 0.85, 0.5, 0.3)),
                                mouth=mouth + [(1.0, 0.75)],
                                amp=amp + [(1.0, 0.2)], attack=0.03, release=0.08, gain=round(gain, 4)))
            t += dur + (0.25 + 2.5 * u("p" + key)) * (1.2 - busy)
            j += 1
    return out


def laugh(t: float, woman: bool, f: float, n: int, gain: float = 1.0) -> list[Syllable]:
    """Ha-ha-ha: breathy pulses ~5.5 a second on an open vowel, the pitch running down."""
    f *= 230 if woman else 140
    return [Syllable(round(t, 4), round(0.18 * n, 4), [(0, round(f * 1.3, 1)), (1, round(f * 0.85, 1))],
                     brightness=0.6, breath=0.45, pulses=(5.5, 0.95, 2.5),
                     formants=_formants("a", 1.17 if woman else 1),
                     attack=0.02, release=0.15, gain=gain)]


def cry(t: float, f: float, vowels: str, gain: float = 1.0) -> list[Syllable]:
    """A vendor calling out his wares: two or three sung notes falling a third, the last one held."""
    out, steps = [], (1.0, 1.0, 0.84)[-len(vowels):]
    for k, (v, s) in enumerate(zip(vowels, steps, strict=True)):
        last = k == len(vowels) - 1
        d = 0.7 if last else 0.22
        out.append(Syllable(round(t, 4), d, [(0, round(f * s * 1.02, 1)), (1, round(f * s * (0.94 if last else 1), 1))],
                            brightness=0.7, jitter=0.4, breath=0.15, formants=_formants(v, 1.0), attack=0.02,
                            release=0.15 if last else 0.03, gain=gain))
        t += d + 0.03
    return out


def gull(t: float, f: float, gain: float) -> list[Syllable]:
    """A gull: three nasal 'kyow's ~0.36 s apart, each rising then falling (TS: strongest near 1 kHz)."""
    return [Syllable(round(t + 0.36 * k, 4), 0.28, [(0, round(f * 1.15, 1)), (0.2, round(f * 1.25, 1)),
                                                     (1, round(f * 0.8, 1))],
                     brightness=0.7, breath=0.15, rough=(0.3, 60.0), formants=[(1000, 300, 1.0), (2200, 400, 0.5),
                                                                              (3300, 500, 0.2)],
                     attack=0.02, release=0.08, gain=round(gain * (1 - 0.15 * k), 4)) for k in range(3)]


def horn(t: float, f: float, gain: float = 1.0) -> list[Syllable]:
    """A war horn far off: a long low note and a fourth above it, brassy."""
    brass = [(500, 150, 1.0), (1100, 200, 0.8), (2300, 300, 0.4), (3200, 400, 0.2)]
    return [Syllable(round(t + at, 4), d, [(0, round(g * 0.97, 1)), (0.1, round(g, 1)), (1, round(g * 0.98, 1))],
                     brightness=0.75, rough=(0.1, 30.0), formants=brass, attack=0.15, release=0.6,
                     amp=[(0, 0.6), (0.2, 1.0), (0.8, 0.9), (1, 0.6)], gain=gain)
            for at, d, g in ((0.0, 1.0, f), (1.1, 1.8, f * 4 / 3))]


def scattered(fx: Fx, name: str, rate: float, end: float = END - 0.8, low: float = 0.3) -> list:
    """Hits (s, gain, contact) at random over the loop, `rate` a second."""
    return sorted((round(end * fx.g.u(f"{name}{k}"), 3), round(low + (1 - low) * fx.g.u(f"{name}g{k}"), 3), 0.0008)
                  for k in range(max(1, int(rate * end))))


def _wind(fx: Fx, power: float, light: bool = False) -> tuple[list, list]:
    """The measured wind at `power`, and its gust curve (for what the gusts carry: sand, snow, a howl)."""
    n = int(2 + 3 * power + fx.g.u("gusty") * 1.99)             # as ambience("wind") draws it
    return borrow(fx, "ambience", "wind", power=power, light=light), gust_curve(fx, n, 0.3 - 0.12 * power)


# --- the places -------------------------------------------------------------------------------------------------------

def battlefield(fx: Fx, loop: bool):
    p = fx.power
    if loop:     # an army shouting, steel and shields clashing, feet and hooves, war drums; heard from a distance
        L = walla(fx, "army", 14 + int(10 * p), level=0.6, shout=1.0, busy=0.85, women=0.1)
        L += [fx.strike("steel", size=0.4, hits=scattered(fx, "clash", 2 + 3 * p), gain=0.8, prefix="clash", dur=END,
                        ring=0.6),
              fx.strike("iron", size=0.6, hits=scattered(fx, "shield", 1 + 2 * p), gain=0.4, prefix="shield", dur=END,
                        ring=0.5),
              fx.strike("wood", size=1.0, hits=[(round(0.8 * k, 2), 0.8 if k % 2 == 0 else 0.55, 0.004)
                                                for k in range(int(LENGTH / 0.8) + 1)],
                        gain=0.12, prefix="drum", dur=END, ring=2.0),            # 20 beats: seamless over 16 s
              band(110, 0.7, 0.1, (0.3, 0.4), "brown", "low", amp=gusts(fx, 4, 0.5)),
              band(900, 0.8, 0.2, (0.4, 0.4), amp=gusts(fx, 3, 0.4))]
        return L, {"space": 2.0, "wet": 0.3, "lowpass": 7000}
    if fx.rand("which") < 0.5:     # a war horn across the field
        return horn(0.0, 110 * 2 ** (0.3 * fx.rand("f")), 1.0), {"space": 2.5, "wet": 0.35, "lowpass": 5000}
    f = 260 * (0.9 + 0.2 * fx.rand("f"))      # close by: steel on steel and a war cry
    L = [fx.strike("steel", size=0.4, gain=0.8, prefix="clash"), fx.strike("steel", start=0.35, size=0.45, gain=0.6,
                                                                           prefix="clash2"),
         Syllable(0.1, 0.9, [(0, f), (0.2, f * 1.1), (1, f * 0.85)], brightness=0.85, rough=(0.4, 40.0), breath=0.2,
                  formants=_formants("a", 1.0), attack=0.04, release=0.2)]
    return L, {"space": 1.5, "wet": 0.25}


def camp(fx: Fx, loop: bool):
    if loop:     # a fire, soldiers talking low, mail and buckles, crickets beyond the tents, a horse
        L = borrow(fx, "ambience", "fire", gain=0.7, power=0.5)
        L += walla(fx, "soldiers", 5, level=0.3, busy=0.35, women=0.1)
        L += borrow(fx, "ambience", "night", gain=0.07)
        L.append(Scatter(0.0, END, [(0, 0.8), (1, 0.8)], "ping", (3500, 9000), (0.05, 0.15), (0.2, 1.0), 0.05))
        L += borrow(fx, "horse", "steed", "snort", gain=0.25, at=round(4 + 8 * fx.g.u("snort"), 2), fit=True)
        return L, {"space": 1.0, "wet": 0.15}
    L = []      # a blade on a whetstone: three strokes, then the steel rings
    for k in range(3):
        L += [Noise(round(0.55 * k, 3), 0.4, [(0, 3500), (1, 5500)], "band", 2.0, amp=[(0, 0.2), (0.5, 1.0), (1, 0.1)],
                    attack=0.03, release=0.05, wobble=(60.0, 0.5), gain=0.8),
              Noise(round(0.55 * k, 3), 0.4, [(0, 9000), (1, 9000)], "band", 1.0, amp=bell_curve(0.5, 1.5),
                    attack=0.03, gain=0.2)]
    L.append(fx.strike("steel", start=1.65, size=0.5, gain=0.3, prefix="blade", ring=0.6))
    return L, {"space": 0.6, "wet": 0.1}


def castle(fx: Fx, loop: bool):
    if loop:     # a great stone hall: its low air, a draught, torches, far voices, a guard crossing
        L = [band(70, 0.7, 0.4, (0.1, 0.3), "brown", "low"), band(250, 0.8, 0.08, (0.1, 0.4)),
             band(600, 3.0, 0.06, (0.2, 0.6), amp=gust_curve(fx, 2, 0.2))]
        L += borrow(fx, "ambience", "fire", gain=0.2, power=0.3)
        L += walla(fx, "court", 3, level=0.12, busy=0.3)
        t0 = round(1 + 9 * fx.g.u("guard"), 2)
        for j in range(6):
            L += borrow(fx, "footstep", "stone", "walk", gain=0.25 * (0.6 + 0.4 * (j % 2)), at=t0 + 0.55 * j)
        return L, {"space": 3.0, "wet": 0.45}
    L = [thud(0.0, 0.8, 60, 1.0), fx.strike("wood", size=1.0, gain=0.6, prefix="door", ring=0.8),
         Noise(0.0, 2.0, [(0, 120), (1, 80)], "low", 0.8, "brown", decay_curve(3), attack=0.01, gain=0.5)]
    return L, {"space": 3.5, "wet": 0.5, "lowpass": 2500}       # a heavy door shutting somewhere in the castle


def town(fx: Fx, loop: bool):
    if loop:     # a market: people, vendors calling, a cart on the cobbles, a far bell, sparrows
        L = walla(fx, "market", 12 + int(8 * fx.power), level=0.55, busy=0.7)
        for k in range(3):
            f = 200 * (0.9 + 0.5 * fx.g.u(f"vend{k}"))
            L += cry(round(1 + 13 * fx.g.u(f"cry{k}"), 2), f, ("e", "a", "o")[k % 3] + "ao"[k % 2], 0.45)
        t0 = round(2 + 9 * fx.g.u("cart"), 2)
        L += [Noise(t0, 4.0, [(0, 140), (1, 120)], "band", 0.8, amp=bell_curve(0.5, 1.5), attack=0.3, release=0.3,
                    wobble=(6.0, 0.4), gain=0.35),
              Scatter(t0, 4.0, [(0, 5), (0.5, 60), (1, 5)], "pop", (800, 3500), (0.001, 0.004), (0.2, 1.0), 0.3)]
        L += borrow(fx, "hoof", "stone", "walk", gain=0.3, at=t0 + 0.8)
        L += borrow(fx, "bell", "church", "toll", gain=0.12, at=9.0, fit=True)
        for k in range(2):
            L += songbird(fx, round(2 + 12 * fx.g.u(f"sparrow{k}"), 2), "sparrow", 0.12)
        return L, {"space": 1.2, "wet": 0.15}
    f = 200 * (0.9 + 0.5 * fx.rand("f"))
    return cry(0.0, f, ("ea", "oa", "ao")[int(3 * fx.rand("v")) % 3] + "o", 1.0), {"space": 1.0, "wet": 0.15}


def tavern(fx: Fx, loop: bool):
    if loop:     # talk at the next table and across the room, laughter, mugs and plates, the hearth
        L = walla(fx, "near", 9, level=0.5, busy=0.6) + walla(fx, "room", 14, level=0.3, busy=0.75)
        for k in range(2):
            L += laugh(round(2 + 12 * fx.g.u(f"laugh{k}"), 2), fx.g.u(f"lw{k}") < 0.5, 0.9 + 0.2 * fx.g.u(f"lf{k}"),
                       4 + int(4 * fx.g.u(f"ln{k}")), 0.5)
        L += [fx.strike("iron", size=0.3, hits=scattered(fx, "mugs", 0.5), gain=0.35, prefix="mugs", dur=END),
              fx.strike("glass", size=0.5, hits=scattered(fx, "plates", 0.4), gain=0.25, prefix="plates", dur=END),
              fx.strike("steel", size=0.05, hits=scattered(fx, "forks", 0.8), gain=0.2, prefix="forks", dur=END)]
        L += borrow(fx, "ambience", "fire", gain=0.15, power=0.4)
        return L, {"space": 0.9, "wet": 0.2}
    L = laugh(0.0, fx.rand("w") < 0.5, 0.9 + 0.2 * fx.rand("f"), 6) + laugh(0.15, fx.rand("w2") < 0.5, 1.0, 5, 0.7)
    L.append(fx.strike("iron", start=0.05, size=0.3, hits=[(0.0, 1.0, 0.001), (0.02, 0.8, 0.001), (0.05, 0.7, 0.001)],
                       gain=0.6, prefix="toast"))
    return L, {"space": 0.9, "wet": 0.2}


CUTLERY = [(2900.0, 0.15, 1.0), (4100.0, 0.12, 0.8), (5600.0, 0.1, 0.7), (7300.0, 0.08, 0.6), (9600.0, 0.06, 0.5),
           (12_400.0, 0.04, 0.4)]                                                                    # forks on china
CHINA = [(1800.0, 0.25, 0.6), (2900.0, 0.2, 1.0), (4400.0, 0.15, 0.7), (6200.0, 0.1, 0.4)]
GLASSES = [(2600.0, 0.6, 1.0), (5300.0, 0.4, 0.5)]


def dinner(fx: Fx, loop: bool):
    if loop:     # TS: a quiet meal in a hall: the cutlery and china ~2 times a second, the talk 15-20 dB under it
        L = walla(fx, "table", 5, level=0.02, busy=0.45)
        L += [Modal(0.0, END, CUTLERY, scattered(fx, "cutlery", 2.0), hardness=16_000, click=0.4, gain=1.0),
              Modal(0.0, END, CHINA, scattered(fx, "china", 0.5), hardness=9000, click=0.1, gain=0.4),
              Modal(0.0, END, GLASSES, scattered(fx, "glasses", 0.15), hardness=14_000, click=0.05, gain=0.3)]
        return L, {"space": 1.2, "wet": 0.2}
    L = [fx.strike("glass", start=0.04 * k, size=0.15 + 0.1 * k, gain=0.7 - 0.15 * k, prefix=f"toast{k}")
         for k in range(3)]                                          # a toast: glasses touching
    L += laugh(0.5, fx.rand("w") < 0.5, 1.0, 4, 0.25)
    return L, {"space": 1.2, "wet": 0.2}


def plains(fx: Fx, loop: bool):
    if loop:     # wind over open grass, larks high up, grasshoppers
        wind, g = _wind(fx, 0.35, light=True)
        L = wind + [band(5000, 0.7, 0.18, (0.6, 0.5), amp=gusts(fx, 4, 0.3)),
                    band(320, 0.8, 0.6, (0.4, 0.3), amp=g)]                  # the breeze's body, no deep rumble
        for k in range(4):
            L += songbird(fx, round(1 + 13 * fx.g.u(f"lark{k}"), 2), "lark", 0.12)
        bursts = [(0.0, 0.0)]
        for k in range(6):                                           # grasshoppers rasp in bursts
            c = (k + 0.2 + 0.6 * fx.g.u(f"hop{k}")) / 6
            bursts += [(round(c - 0.02, 3), 0.0), (round(c, 3), 400.0), (round(c + 0.03, 3), 0.0)]
        L.append(Scatter(0.0, END, bursts + [(1.0, 0.0)], "pop", (5000, 9000), (0.0003, 0.001), (0.3, 1.0), 0.12))
        return L, {"space": 0.8, "wet": 0.1}
    f = 2600 * (0.9 + 0.2 * fx.rand("f"))      # a hawk's cry far above
    L = [Syllable(0.0, 1.1, [(0, f), (0.15, f * 1.18), (1, f * 0.8)], brightness=0.8, breath=0.5, rough=(0.4, 70.0),
                  formants=[(3000, 800, 1.0)], attack=0.03, release=0.3)]
    return L, {"space": 1.5, "wet": 0.2}


def desert(fx: Fx, loop: bool):
    if loop:     # a hot dry wind, sand hissing with every gust, nothing else
        wind, g = _wind(fx, 0.6)
        L = wind + [Scatter(0.0, END, [(t, round(300 + 2500 * a, 1)) for t, a in g], "pop", (3000, 11_000),
                            (0.0003, 0.001), (0.1, 1.0), 0.35),
                    band(7000, 0.7, 0.12, (1.0, 0.5), amp=[(t, round(a ** 2, 3)) for t, a in g])]
        return L, {}
    L = [Noise(0.0, 3.0, [(0, 1000), (0.4, 5000), (1, 2000)], "band", 0.8, amp=bell_curve(0.4, 1.5), attack=0.2,
               release=0.4, wobble=(3.0, 0.5), gain=0.8),                    # a sand devil whirling past
         Scatter(0.0, 3.0, [(0, 300), (0.4, 4000), (1, 200)], "pop", (2500, 11_000), (0.0003, 0.001), (0.1, 1.0), 0.5)]
    return L, {}


def snow(fx: Fx, loop: bool):
    if loop:     # a strong cold wind howling in the crags, snow ticking
        wind, g = _wind(fx, 0.85)
        L = wind + [Noise(0.0, END, [(t, round(520 * (0.75 + 0.6 * a), 1)) for t, a in g], "band", 10.0,
                          amp=[(t, round(a ** 2, 3)) for t, a in g], attack=0.05, release=0.05, wobble=(0.5, 0.2),
                          gain=0.35),
                    Scatter(0.0, END, [(t, round(40 + 200 * a, 1)) for t, a in g], "pop", (5000, 12_000),
                            (0.0003, 0.001), (0.1, 0.6), 0.1)]
        return L, {}
    L = [Noise(0.0, 5.0, [(0, 160), (1, 90)], "low", 0.8, "brown", bell_curve(0.25, 1.2), attack=0.3, release=0.8,
               wobble=(4.0, 0.5), gain=1.0),                              # an avalanche on another slope
         fx.strike("glass", size=0.9, gain=0.4, prefix="ice", ring=0.5)]
    return L, {"space": 2.5, "wet": 0.3, "lowpass": 3000}


def swamp(fx: Fx, loop: bool):
    sp = fx.sfx.species
    if loop:     # frogs, a bullfrog or two, mud bubbling, midges, far insects
        L = [band(800, 0.8, 0.04, (0.2, 0.3)), band(200, 0.7, 0.05, (0.1, 0.3), "brown", "low"),
             band(620, 8.0, 0.03, (14.0, 0.8)), band(9500, 3.0, 0.04, (22.0, 0.9)),
             drops([(0, 0.7), (1, 0.7)], (120, 500), (0.02, 0.07), 0.6, level=(0.3, 1.0))]
        frog, bull = Creature("amphibian", species=sp * 5 + 2, size=0.25), Creature("amphibian", species=sp * 5 + 3,
                                                                                     size=0.95)
        n = int(8 + 8 * fx.power)
        for k in range(n):
            L += place(frog.member(k % 4).voice("idle", take=k), END * k / n + 0.4 * fx.g.u(f"fr{k}"),
                       0.2 + 0.3 * fx.g.u(f"fv{k}"))
        for k in range(2):
            L += place(bull.voice("idle", take=k), 2 + 11 * fx.g.u(f"bull{k}"), 0.4)
        return L, {"space": 1.0, "wet": 0.15}
    L = place(Creature("amphibian", species=sp * 5 + 3, size=0.95).voice("alert", take=fx.take), 0.0)
    L.append(drops([(0, 6), (1, 0)], (120, 400), (0.04, 0.09), 0.8, 0.8, level=(0.5, 1.0)))
    return L, {"space": 1.0, "wet": 0.15}


def ruins(fx: Fx, loop: bool):
    if loop:     # wind singing through broken stone, a low wind, drips, chimes left by the faithful
        k = 0.9 + 0.2 * fx.g.u("tone")
        L = [Noise(0.0, END, [(0, round(330 * k)), (1, round(330 * k))], "band", 14.0, amp=gust_curve(fx, 2, 0.1),
                   attack=0.05, release=0.05, wobble=(0.3, 0.1), gain=0.3),
             Noise(0.0, END, [(0, round(495 * k)), (1, round(495 * k))], "band", 14.0, amp=gust_curve(fx, 3, 0.1),
                   attack=0.05, release=0.05, wobble=(0.3, 0.1), gain=0.2),
             band(180, 0.7, 0.35, (0.15, 0.4), "brown", "low", amp=gusts(fx, 3, 0.4)),
             band(1500, 0.7, 0.05, (0.3, 0.4)),
             drops([(0, 0.25), (1, 0.25)], (900, 2600), (0.02, 0.05), 0.5, level=(0.3, 1.0)),
             Scatter(0.0, END, [(0, 0.35), (1, 0.35)], "ping", (1800, 5500), (0.4, 1.2), (0.2, 0.8), 0.25)]
        return L, {"space": 3.0, "wet": 0.4}
    L = [thud(0.0, 0.4, 90, 0.8),                                     # stones giving way
         Scatter(0.05, 1.6, [(0, 150), (0.3, 60), (1, 0)], "pop", (300, 3000), (0.002, 0.008), (0.2, 1.0), 0.7),
         Noise(0.0, 1.2, [(0, 1200), (1, 600)], "band", 0.8, amp=decay_curve(3), attack=0.01, gain=0.3)]
    return L, {"space": 3.0, "wet": 0.4}


def deck(fx: Fx, loop: bool):
    if loop:     # the sea along the hull, wind in the rigging, timbers creaking, the sail flapping, gulls
        L = borrow(fx, "ambience", "sea", gain=0.8, light=True) + borrow(fx, "ambience", "wind", gain=0.35,
                                                                       power=0.4, light=True)
        for k in range(4):
            t = round(1 + 13.5 * fx.g.u(f"creak{k}"), 2)
            L += [replace(x, start=round(x.start + t, 4), gain=round(x.gain * 0.5, 4))
                  for x in creak(fx, 0.4 + 0.5 * fx.g.u(f"cd{k}"))]
        for k in range(2):
            t = round(2 + 12 * fx.g.u(f"sail{k}"), 2)
            L.append(Noise(t, 0.8, [(0, 250), (1, 200)], "band", 0.8, amp=[(0, 0.0), (0.1, 1.0), (0.2, 0.3), (0.3, 0.9),
                                                                             (0.4, 0.2), (0.55, 0.7), (0.7, 0.1),
                                                                             (1, 0.0)],
                           attack=0.02, release=0.05, gain=0.3))
        for k in range(2):
            L += gull(round(1 + 13 * fx.g.u(f"gull{k}"), 2), 750 * (0.9 + 0.2 * fx.g.u(f"gf{k}")), 0.25)
        return L, {"space": 0.8, "wet": 0.1}
    L = borrow(fx, "bell", "ship", "ring") + borrow(fx, "bell", "ship", "ring", gain=0.8, at=0.6)   # ding-ding
    return L, {"space": 1.0, "wet": 0.15}


PLACES = {"battlefield": battlefield, "camp": camp, "castle": castle, "town": town, "tavern": tavern,
          "dinner": dinner, "plains": plains, "desert": desert, "snow": snow, "swamp": swamp, "ruins": ruins,
          "deck": deck}
