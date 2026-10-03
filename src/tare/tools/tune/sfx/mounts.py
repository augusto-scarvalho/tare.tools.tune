"""Mounts, flight and the march: horses' hooves and voices, wings, troops on the move, teleports.

Measured on Triangle Strategy's effects, FFTA2 and Tactics Ogre: Reborn (the user's own copies) and a CC0 pack;
analysis only, nothing of them is kept:

    hooves      each step is a pair of hooves ~68 ms apart (the front or the hind pair), ~0.21 s in all;
                grass: a dull thump (strongest 125-250 Hz, its peak near 130 Hz), little above 1 kHz;
                stone: a hollow knock (strongest 0.5-1 kHz, centre ~0.9 kHz) and the shoe's click up to 8 kHz;
                shallow water: a splash centred near 2.3 kHz
    charge      ~1.8 s: a rush of air swelling for ~0.7 s, centred near 2 kHz, then dying away;
                the blow it lands: a low thud (125 Hz-1 kHz, ~0.4 s), then ~1.5 s of bright dust (8 kHz)
    hurt        ~1.6 s: ~1 s high (f0 ~550 Hz, the energy at ~2 kHz), then a low blow (~250 Hz)
    snort       ~1 s of unvoiced breath, strongest near 1 kHz
    wings       a beat is ~0.4 s, strongest at 250-500 Hz, feathers up to ~13 kHz, often two strokes ~0.1 s apart;
                a bird taking off beats ~10 times in 1.6 s and is brighter (centre ~2 kHz)
    teleport    vanishing: ~1.2 s swelling for ~0.8 s, rising ~15 semitones; appearing: ~1 s, falling ~17 semitones;
                Tactics Ogre's: ~0.4 s each, darker

Gaits, hovering and the march are seamless loops: the last hoof (beat, step) of each loop dies away before the loop
point, so the loop needs no crossfade at all.
"""
from dataclasses import replace

from ..spec import Modal, Noise, Scatter, Syllable
from . import Fx, bell_curve, decay_curve, recipe
from .physical import gear_move, splits, thud, whoosh

SEAM = 0.005            # the loops' crossfade: the tail is silent, this only keeps the renderer's fold well defined


def _loop(fx: Fx, layers: list, length: float, gain: float, **extra):
    """A seamless loop `length` s long, every layer of which has died away before the loop point."""
    assert max(x.start + x.dur for x in layers) <= length + 1e-6
    anchor = Noise(0.0, round(length + SEAM, 4), [(0, 1000.0), (1, 1000.0)], gain=0.0)   # sets the loop's length
    return fx.voice(gain, **splits(layers + [anchor]), loop=SEAM, **extra)


def _shift(layers: list, dt: float) -> list:
    return [replace(x, start=round(x.start + dt, 4)) for x in layers]


# --- hooves -----------------------------------------------------------------------------------------------------------

# thump (Hz, s, gain): the hoof's weight; knock (Hz, gain): the hollow hoof wall and its shoe on a hard ground;
# click (Hz, gain): the shoe's edge; grains (rate/s, Hz range, decay range, s, gain); rustle (Hz, s, gain)
# Balanced by rendering until each surface's step matched TS's octave bands (grass, stone, water: ±5 dB to 8 kHz).
HOOVES = {
    "dirt": dict(thump=(170, 0.08, 1.0), knock=(650, 0.25), click=(3200, 0.05),
                 grains=(260, (500, 3000), (0.0008, 0.003), 0.12, 0.25)),
    "grass": dict(thump=(260, 0.09, 1.0), knock=(560, 0.15), click=None, soft=True,            # TS: 125-250 Hz
                  grains=(160, (1500, 9000), (0.0005, 0.002), 0.12, 0.1), rustle=(4000, 0.15, 0.06)),
    "stone": dict(thump=(330, 0.05, 0.3), knock=(620, 1.0), click=(6500, 0.7),                 # TS: 0.5-1 kHz
                  grains=(160, (2000, 9000), (0.0005, 0.002), 0.16, 0.18)),
    "wood": dict(thump=(200, 0.08, 0.9), knock=(480, 0.9), click=(2800, 0.1), boards=0.5),    # a bridge, a deck
    "water": dict(thump=(230, 0.12, 1.5), knock=None, click=None, splash=0.3),               # TS: 0.25-1 kHz, ~2.3k
    "snow": dict(thump=(170, 0.1, 1.0), knock=None, click=None, soft=True,
                 grains=(600, (900, 3000), (0.0008, 0.003), 0.14, 0.45)),
}
# Gaits: stride (s, at size 0.5), the hooves' places in it (fraction, gain), strides per loop. Real horses: a walk is
# four even beats; a trot two (the diagonal pairs, a hair apart); a canter three and a lift; a gallop four quick ones
# (hind, hind, fore, fore) and then all four hooves in the air.
GAITS = {
    "walk": (1.1, [(0.0, 0.9), (0.25, 1.0), (0.5, 0.85), (0.75, 1.0)], 2),
    "trot": (0.72, [(0.0, 1.0), (0.017, 0.75), (0.5, 0.95), (0.517, 0.7)], 4),
    "canter": (0.62, [(0.0, 0.85), (0.2, 1.0), (0.225, 0.8), (0.42, 1.0)], 4),
    "gallop": (0.44, [(0.0, 0.8), (0.13, 0.9), (0.33, 0.95), (0.46, 1.0)], 6),
}
FORCE = {"step": 0.7, "walk": 0.6, "trot": 0.75, "canter": 0.85, "gallop": 1.0, "halt": 0.9, "land": 1.0}


def hoof(fx: Fx, t: float, g: float, key: str) -> list:
    """One hoof meeting the ground at `t`: every layer is over within 0.17 s."""
    st = HOOVES[fx.style]
    low = 2 ** (-0.5 * (fx.size - 0.5)) * (0.94 + 0.12 * fx.rand(key + "f"))
    hz, dur, gain = st["thump"]
    soft = st.get("soft", False)                # soft ground: a resonant low-pass, nothing much above ~1 kHz
    out = [Noise(round(t, 4), dur, [(0, round(hz * low, 1)), (1, round(hz * low * 0.7, 1))], "low" if soft else "band",
                 2.0 if soft else 0.9, amp=decay_curve(5), attack=0.002, gain=round(gain * g, 4))]
    if st["knock"]:
        k, kg = st["knock"]
        k *= low
        out.append(Modal(round(t, 4), 0.15, [(round(k, 1), 0.07, 1.0), (round(k * 1.62, 1), 0.05, 0.7),
                                             (round(k * 2.55, 1), 0.035, 0.45), (round(k * 3.7, 1), 0.02, 0.3)],
                         hardness=5000, click=0.15, gain=round(kg * g, 4)))
    if st["click"]:
        c, cg = st["click"]
        out.append(Noise(round(t, 4), 0.012, [(0, c), (1, c)], "band", 0.8, amp=decay_curve(5), attack=0.0005,
                         gain=round(cg * g, 4)))
    if st.get("grains"):
        rate, band, decay, d, gg = st["grains"]
        out.append(Scatter(round(t, 4), d, [(0, rate * g), (0.4, rate * g * 0.6), (1, 0)], "pop", band, decay,
                           (0.2, 1.0), round(gg * g, 4)))
    if st.get("rustle"):
        r, d, rg = st["rustle"]
        out.append(Noise(round(t, 4), d, [(0, r * 0.8), (1, r)], "band", 0.7, amp=[(0, 1.0), (0.3, 0.6), (1, 0.0)],
                         attack=0.008, wobble=(30.0, 0.7), gain=round(rg * g, 4)))
    if st.get("boards"):
        out.append(fx.strike("wood", start=round(t, 4), size=0.7, ring=0.4, dur=0.17, gain=round(st["boards"] * g, 4),
                             prefix="boards"))
    if st.get("splash"):
        out += [Scatter(round(t, 4), 0.17, [(0, 280 * g), (1, 0)], "drop", (600, 2500), (0.002, 0.008), (0.2, 1.0),
                        round(0.5 * g, 4)),
                Noise(round(t, 4), 0.15, [(0, 1700), (1, 1300)], "band", 0.8, amp=decay_curve(4), attack=0.003,
                      wobble=(40.0, 0.6), gain=round(st["splash"] * g, 4))]
    return out


def _pair(fx: Fx, t: float, force: float, key: str) -> list:
    """The front or the hind pair, ~68 ms apart (TS)."""
    gap = 0.068 * (0.85 + 0.3 * fx.rand(key + "gap"))
    return hoof(fx, t, force, key + "a") + hoof(fx, t + gap, 0.8 * force, key + "b")


@recipe("hoof", ("step", "walk", "trot", "canter", "gallop", "halt", "land"), tuple(HOOVES),
        loops=("walk", "trot", "canter", "gallop"))
def hooves(fx: Fx):
    """A horse's hooves on a surface: a step (one pair), the gaits as loops (walk, trot, canter, gallop), a sliding
    halt, landing from a jump. Size: a pony to a destrier."""
    e, s = fx.event, fx.size
    force = FORCE[e] * (0.6 + 0.4 * fx.power)
    if e in GAITS:
        stride, beats, strides = GAITS[e]
        stride *= 0.85 + 0.3 * s
        layers = []
        for k in range(strides):
            for j, (at, g) in enumerate(beats):
                jitter = 0.006 * (fx.rand(f"j{k}{j}") - 0.5)
                layers += hoof(fx, 0.012 + (k + at) * stride + jitter, force * g * (0.88 + 0.24 * fx.rand(f"g{k}{j}")),
                               f"{k}.{j}")
        return _loop(fx, layers, strides * stride, fx.level(0.8))
    if e == "step":
        return fx.voice(fx.level(0.7), **splits(_pair(fx, 0.0, force, "s")))
    if e == "land":         # the front pair takes the weight, the hind pair follows harder, the body settles
        layers = _pair(fx, 0.0, force, "f") + _pair(fx, 0.16, force * 1.1, "h")
        layers.append(thud(0.17, 0.25, 110 * 2 ** (-0.5 * (s - 0.5)), 0.7))
        return fx.voice(fx.level(0.9), **splits(layers))
    # halt: slowing hooves, the hind legs skidding under, a last settling pair
    layers = []
    for k, (t, g) in enumerate([(0.0, 1.0), (0.13, 0.95), (0.3, 0.9)]):
        layers += hoof(fx, t, force * g, f"h{k}")
    skid = 2200 if fx.style in ("stone", "wood") else 1300
    layers.append(Noise(0.32, 0.38, [(0, skid), (1, skid * 0.7)], "band", 1.2, amp=[(0, 1.0), (0.6, 0.7), (1, 0.0)],
                        attack=0.01, wobble=(35.0, 0.6), gain=0.45 * force))
    layers.append(Scatter(0.32, 0.4, [(0, 500), (1, 0)], "pop", (600, 4000), (0.0008, 0.003), (0.2, 1.0), 0.3))
    layers += _pair(fx, 0.78, force * 0.6, "end")
    return fx.voice(fx.level(0.85), **splits(layers))


# --- the horse's voice, the charge ------------------------------------------------------------------------------------

def _blow(start: float, f: float, gain: float) -> list:
    """The low end of a neigh: three breathy pulses (~250 Hz in TS) and the nostrils."""
    return [Syllable(round(start, 4), 0.5, [(0, round(f, 1)), (1, round(f * 0.75, 1))], brightness=0.3, breath=0.6,
                     pulses=(7.5, 0.9, 2.5), formants=[(500, 150, 1.0), (1300, 250, 0.5), (2400, 400, 0.2)],
                     attack=0.03, release=0.12, gain=gain),
            Noise(round(start, 4), 0.5, [(0, 900), (1, 700)], "band", 1.0, amp=bell_curve(0.3, 1.5), attack=0.02,
                  wobble=(20.0, 0.5), gain=round(0.3 * gain, 4))]


def _whinny(start: float, dur: float, contour: list, k: float, rough: float, gain: float = 1.0) -> Syllable:
    """The high part: a nasal voice (most of its energy near 2 kHz) quavering ~11 times a second."""
    return Syllable(round(start, 4), round(dur, 4), [(t, round(f, 1)) for t, f in contour], brightness=0.9,
                    vibrato=(11.0, 1.3), jitter=0.4, rough=(rough, 38.0), breath=0.25, pulses=(10.5, 0.55, 2.0),
                    formants=[(round(950 * k), 220, 0.3), (round(2050 * k), 300, 1.0), (round(3100 * k), 420, 0.55),
                              (round(4300 * k), 600, 0.2)],
                    attack=0.04, release=0.15, amp=[(0, 0.7), (0.12, 1.0), (0.7, 0.9), (1, 0.6)], gain=gain)


@recipe("horse", ("neigh", "snort", "nicker", "hurt", "charge", "trample"), ("steed", "warhorse"))
def horse(fx: Fx):
    """A horse: neigh, snort, nicker (a soft greeting), hurt; the cavalry charge and the blow it lands. Warhorses are
    bigger, lower and wear barding."""
    e, s = fx.event, fx.size
    war = fx.style == "warhorse"
    low = 2 ** (-0.7 * (s - 0.5)) * (0.85 if war else 1.0) * (0.95 + 0.1 * fx.rand("f0"))
    k = 2 ** (-0.4 * (s - 0.5)) * (0.92 if war else 1.0)                  # the head's size: formants
    if e == "neigh":        # the whinny: rising into a high quaver, falling ~1.3 s, then the blow
        f = 640 * low
        layers = [_whinny(0.0, 1.3, [(0, f), (0.1, f * 1.3), (0.45, f * 1.05), (1, f * 0.6)], k, 0.3)]
        layers += _blow(1.3, 240 * low, 0.6)
        return fx.voice(fx.level(0.9), **splits(layers), space=0.6, wet=0.12)
    if e == "hurt":         # TS: ~1 s high and steady (f0 ~550 Hz), harsher, then the low blow
        f = 550 * low
        layers = [_whinny(0.0, 1.0, [(0, f * 0.9), (0.1, f * 1.05), (0.8, f), (1, f * 0.8)], k, 0.6)]
        layers += _blow(1.05, 250 * low, 0.7)
        return fx.voice(fx.level(0.95), **splits(layers), drive=1.0, space=0.5, wet=0.1)
    if e == "snort":        # ~1 s of breath blown through the nostrils, fluttering, strongest near 1 kHz
        layers = [Syllable(0.0, 1.0, [(0, 100.0), (1, 100.0)], "noise", pulses=(24.0, 0.85, 1.5),
                           formants=[(round(900 * k), 450, 1.0), (round(500 * k), 300, 0.4),
                                     (round(2300 * k), 700, 0.15)],
                           attack=0.02,
                           release=0.25, amp=[(0, 1.0), (0.6, 0.8), (1, 0.2)]),
                  Noise(0.0, 0.12, [(0, 1800), (1, 1200)], "band", 0.8, amp=decay_curve(4), attack=0.003, gain=0.4)]
        return fx.voice(fx.level(0.7), **splits(layers))
    if e == "nicker":       # a low, soft "huhuhu" through a closed mouth
        layers = [Syllable(0.0, 0.7, [(0, round(150 * low, 1)), (1, round(118 * low, 1))], brightness=0.25,
                           breath=0.45, pulses=(9.0, 0.95, 3.0),
                           formants=[(round(450 * k), 120, 1.0), (round(1100 * k), 200, 0.5),
                                     (round(2300 * k), 350, 0.15)],
                           attack=0.03, release=0.15)]
        return fx.voice(fx.level(0.55), **splits(layers))
    if e == "charge":       # TS: the air rushing, swelling for ~0.7 s (centre ~2 kHz) over a galloping approach
        stride = 0.42 * (0.85 + 0.3 * s)
        layers = []
        for n in range(4):
            for j, (at, g) in enumerate(GAITS["gallop"][1]):
                t = 0.02 + n * stride * (1 - 0.06 * n) + at * stride
                layers += [replace(x, gain=round(x.gain * (0.04 + 0.025 * n), 4)) for x in
                           hoof(replace_style(fx, "dirt"), t, g, f"c{n}{j}")]
            if war:         # the barding shaking with every stride
                layers += _shift(gear_move(fx, "chainmail", 0.3, 0.5 + 0.15 * n), 0.02 + n * stride)
        layers.append(Noise(0.0, 1.8, [(0, 1300), (0.4, 2100), (1, 1600)], "band", 2.0, amp=bell_curve(0.4, 1.6),
                            attack=0.1, release=0.3, wobble=(12.0, 0.4), gain=0.9))
        layers += whoosh(fx, 0.4, 0.5, 2100, 2.0, 0.3)
        return fx.voice(fx.level(0.9), **splits(layers), space=0.8, wet=0.12)
    # trample: the front hooves come down on a body, the thud, then dust (TS: 125 Hz-1 kHz for ~0.4 s, then 8 kHz)
    layers = (hoof(replace_style(fx, "dirt"), 0.0, 1.2, "t1") + hoof(replace_style(fx, "dirt"), 0.09, 1.1, "t2") +
              [thud(0.0, 0.4, 120 * low, 1.0), thud(0.09, 0.35, 160 * low, 0.8),
               Noise(0.0, 0.4, [(0, 600), (1, 400)], "band", 0.8, amp=decay_curve(3), attack=0.01, gain=0.5),
               Noise(0.15, 1.4, [(0, 7000), (1, 8500)], "band", 0.8, amp=[(0, 0.0), (0.1, 1.0), (1, 0.0)],
                     attack=0.05, release=0.2, wobble=(25.0, 0.5), gain=0.1),
               Scatter(0.05, 0.6, [(0, 400), (1, 0)], "pop", (500, 5000), (0.0008, 0.004), (0.2, 1.0), 0.4)])
    if war:
        layers += _shift(gear_move(fx, "chainmail", 0.4, 1.0), 0.05)
    return fx.voice(fx.level(0.95), **splits(layers))


def replace_style(fx: Fx, style: str) -> Fx:
    """The same take, heard on another surface (a horse's hooves inside its voice's events)."""
    return Fx(replace(fx.sfx, kind="hoof", style=style), fx.event, fx.take)


# --- wings ------------------------------------------------------------------------------------------------------------

def beat(fx: Fx, t: float, g: float, key: str, dur: float | None = None) -> list:
    """One wingbeat at `t`: a soft upstroke, then the downstroke pushing air (strongest 250-500 Hz);
    feathers rustle up to ~13 kHz, a leather membrane snaps taut instead."""
    leather = fx.style == "leather"
    low = 2 ** (-0.8 * (fx.size - 0.5)) * (0.92 + 0.16 * fx.rand(key + "f"))
    dur = dur or 0.32 * (1.25 if leather else 1.0) * (0.85 + 0.3 * fx.size)
    down = t + 0.06
    out = [Noise(round(t, 4), 0.1, [(0, round(900 * low)), (1, round(1300 * low))], "band", 1.0,
                 amp=bell_curve(0.5, 1.5), attack=0.02, release=0.03, gain=round(0.15 * g, 4)),
           Noise(round(down, 4), round(dur, 4), [(0, round(230 * low)), (0.3, round(300 * low)), (1, round(160 * low))],
                 "band", 0.8, amp=bell_curve(0.18, 1.6), attack=0.02, release=0.05, wobble=(14.0, 0.3),
                 gain=round(g, 4))]
    if leather:
        out += [thud(round(down + dur * 0.2, 4), 0.12, round(150 * low), round(0.5 * g, 4)),
                Noise(round(down + dur * 0.3, 4), 0.05, [(0, round(1400 * low)), (1, round(900 * low))], "band", 1.5,
                      amp=decay_curve(5), attack=0.003, gain=round(0.35 * g, 4))]
    else:
        out += [Noise(round(down, 4), round(dur * 0.9, 4), [(0, 5000), (1, 3500)], "band", 0.7,
                      amp=bell_curve(0.3, 1.4), attack=0.02, wobble=(40.0, 0.6), gain=round(0.22 * g, 4)),
                Scatter(round(down, 4), round(dur * 0.7, 4), [(0, 160), (0.4, 220), (1, 0)], "pop", (2500, 11000),
                        (0.0003, 0.0012), (0.2, 1.0), round(0.12 * g, 4))]
    return out


@recipe("wings", ("flap", "hover", "takeoff", "land", "swoop"), ("feather", "leather"), loops=("hover",))
def wings(fx: Fx):
    """Wings: one beat, hovering (a loop), taking off, landing, a swoop past. Feathers (a griffin, a hawkman, a bird)
    or leather (a wyvern, a dragon, a bat); size: a bird to a dragon."""
    e, s = fx.event, fx.size
    leather = fx.style == "leather"
    period = 0.7 * (0.8 + 0.4 * s) if leather else 0.42 * (0.55 + 0.9 * s)      # small birds beat fast
    if e == "flap":
        return fx.voice(fx.level(0.75), **splits(beat(fx, 0.0, 1.0, "b")))
    if e == "hover":
        n = 4 if leather else 6
        dur = min(0.32 * (1.25 if leather else 1.0) * (0.85 + 0.3 * s), period - 0.11)
        layers = []
        for k in range(n):
            layers += beat(fx, 0.012 + k * period, 0.85 + 0.25 * fx.rand(f"h{k}"), f"h{k}", dur)
        return _loop(fx, layers, n * period, fx.level(0.75))
    if e == "takeoff":      # a push off the ground, beats quickening and fading as it climbs (TS: ~10 in 1.6 s)
        layers = [thud(0.0, 0.15, 160 * 2 ** (-0.5 * (s - 0.5)), 0.8)]
        t, gap = 0.05, period * 0.75
        for k in range(9 if not leather else 5):
            layers += beat(fx, t, 1.0 * 0.85 ** k, f"t{k}", 0.24 if not leather else None)
            t += gap
            gap *= 0.93
        layers.append(Noise(0.1, t + 0.2, [(0, 1500), (1, 3000)], "band", 0.8, amp=bell_curve(0.4, 1.5),
                            attack=0.05, release=0.2, wobble=(10.0, 0.5), gain=0.3))
        return fx.voice(fx.level(0.8), **splits(layers), space=0.6, wet=0.1)
    if e == "land":         # braking: wide, louder beats slowing down, the feet (talons) taking the weight, a shake
        layers, t = [], 0.0
        for k, g in enumerate((0.7, 0.9, 1.0)):
            layers += beat(fx, t, g, f"l{k}")
            t += period * (1.0 + 0.25 * k)
        layers += [thud(t, 0.2, 140 * 2 ** (-0.5 * (s - 0.5)), 0.9), thud(t + 0.07, 0.18, 170, 0.6)]
        layers.append(Noise(t + 0.25, 0.35, [(0, 4500), (1, 3500)], "band", 0.7, amp=bell_curve(0.3, 1.4),
                            attack=0.02, wobble=(45.0, 0.7), gain=0.15 if leather else 0.3))
        return fx.voice(fx.level(0.8), **splits(layers))
    # swoop: diving past, wings tucked (the air), then one beat to pull up
    layers = whoosh(fx, 0.0, 0.9, 1100 * 2 ** (-0.5 * (s - 0.5)), 1.0, 1.0, whistle=0.1) + beat(fx, 0.75, 1.0, "w")
    return fx.voice(fx.level(0.8), **splits(layers))


# --- the march --------------------------------------------------------------------------------------------------------

def _tread(fx: Fx, t: float, g: float, key: str) -> list:
    """One step of a whole company: many boots a little apart (a smeared thump, a dense crunch), the gear shaking."""
    heavy = fx.style == "heavy"
    low = 2 ** (-0.4 * (fx.size - 0.5))
    crowd = 0.6 + 0.8 * fx.size
    out = [Noise(round(t, 4), 0.12, [(0, round(240 * low)), (1, round(150 * low))], "low", 1.0, amp=decay_curve(4),
                 attack=0.015, gain=round(g, 4)),
           Scatter(round(t, 4), 0.1, [(0, 900 * crowd), (0.5, 600 * crowd), (1, 0)], "pop", (400, 3000),
                   (0.0008, 0.003), (0.2, 1.0), round(0.45 * g, 4))]
    out += _shift(gear_move(fx, "plate" if heavy else "chainmail", 0.14, 0.6 * g), t)
    return out


@recipe("march", ("loop", "move", "halt"), ("infantry", "heavy"), loops=("loop",))
def march(fx: Fx):
    """Troops marching in step (the loop), a short move on the map, the halt (two stamps, the gear settling).
    Infantry in mail or heavy troops in plate; size: a squad to a company."""
    e = fx.event
    beat_s = 0.52 * (0.95 + 0.1 * fx.rand("tempo"))
    if e == "loop":
        layers = []
        for k in range(8):
            layers += _tread(fx, 0.012 + k * beat_s, (1.0 if k % 2 == 0 else 0.82) * (0.9 + 0.2 * fx.rand(f"g{k}")),
                             f"m{k}")
        return _loop(fx, layers, 8 * beat_s, fx.level(0.75))
    if e == "move":         # six steps fading in and out: a unit moving a few tiles
        layers = []
        for k, g in enumerate((0.45, 0.75, 1.0, 0.95, 0.75, 0.45)):
            layers += _tread(fx, k * beat_s, g * (1.0 if k % 2 == 0 else 0.85), f"v{k}")
        return fx.voice(fx.level(0.75), **splits(layers))
    layers = _tread(fx, 0.0, 1.0, "a") + _tread(fx, 0.26, 1.1, "b")
    layers += _shift(gear_move(fx, "plate" if fx.style == "heavy" else "chainmail", 0.5, 0.7), 0.3)
    return fx.voice(fx.level(0.8), **splits(layers))


# --- teleport ---------------------------------------------------------------------------------------------------------

@recipe("warp", ("out", "in"), ("arcane", "retro"))
def warp(fx: Fx):
    """Teleporting: vanishing (out) and appearing (in). Arcane: shimmering sweeps (FFTA2); retro: a short pulse-wave
    staircase (Tactics Ogre)."""
    e, s = fx.event, fx.size
    root = 600 * 2 ** (-0.6 * (s - 0.5)) * (0.94 + 0.12 * fx.rand("root"))
    out = e == "out"
    if fx.style == "retro":     # TO: ~0.4 s, dark (strongest ~125 Hz): a pulse wave stepping an octave up or down
        steps = [0, 2, 4, 5, 7, 9, 10, 12] if out else [12, 10, 9, 7, 5, 4, 2, 0]
        dur, step = (0.37, 0.042) if out else (0.45, 0.05)
        pitch = []
        for k, n in enumerate(steps):
            f = round(root * 0.3 * 2 ** (n / 12), 1)
            pitch += [(round(k * step / dur, 4), f), (round(min((k + 1) * step / dur - 0.001, 1.0), 4), f)]
        layers = [Syllable(0.0, dur, pitch, "pulse", pulse_width=0.125, attack=0.005, release=0.06,
                           amp=[(0, 1.0), (1, 0.6 if out else 1.0)]),
                  Noise(0.0, dur, [(0, 1200), (1, 3000)] if out else [(0, 3000), (1, 1200)], "band", 1.0,
                        amp=bell_curve(0.5, 1.5), attack=0.01, gain=1.0), thud(0.0, 0.3, 120, 1.2),
                  Syllable(0.0, dur, [(0, round(root * 0.19, 1)), (1, round(root * 0.19 * (1.5 if out else 0.75), 1))],
                           "sine", attack=0.01, release=0.08, gain=0.9)]                  # the low hum under it
        return fx.voice(fx.level(0.75), **splits(layers), space=0.4, wet=0.15)
    # arcane. out: ~1.2 s swelling for ~0.8 s, rising ~15 semitones, gone at the top; in: ~1 s, falling ~17 semitones
    dur, peak, span = (1.2, 0.65, 15) if out else (1.0, 0.45, -17)
    amp = [(0, 0.15), (peak, 1.0), (min(peak + 0.12, 1.0), 0.25), (1, 0.0)] if out else \
        [(0, 0.3), (peak, 1.0), (1, 0.0)]
    start = root if out else root * 2 ** (-span / 12)
    layers = [Syllable(0.0, dur, [(0, round(start * m, 1)), (1, round(start * m * 2 ** (span / 12), 1))], "sine",
                       vibrato=(16.0, 0.3), attack=0.05, release=0.15, amp=amp, gain=g)
              for m, g in ((0.5, 0.45), (1.0, 1.0), (1.5, 0.6), (2.25, 0.35))]
    layers += [Noise(0.0, dur, [(0, 800), (1, 4000)] if out else [(0, 4000), (1, 700)], "band", 0.8, amp=amp,
                     attack=0.05, release=0.15, wobble=(20.0, 0.4), gain=0.6),
               Noise(0.0, dur, [(0, 220), (1, 330)] if out else [(0, 330), (1, 200)], "band", 0.8, amp=amp,
                     attack=0.05, release=0.15, wobble=(8.0, 0.4), gain=0.5),          # the air rushing in or out
               Scatter(0.0, dur, [(0, 10), (peak, 60), (1, 0)] if out else [(0, 60), (peak, 30), (1, 0)], "ping",
                       (3000, 9000), (0.05, 0.2), (0.2, 0.6), 0.3)]
    if not out:             # set down on the ground
        layers.append(thud(round(dur * peak, 4), 0.2, 150, 0.4))
    return fx.voice(fx.level(0.8), **splits(layers), space=1.2, wet=0.2)
