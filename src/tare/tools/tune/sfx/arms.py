"""The weapons a tactics party carries beyond swords, maces and bows: spears and the dragoon's jump, bare fists,
guns, and things thrown (knives, shuriken, bombs).

Measured on the games (Tactics Ogre: Reborn and FFTA2 from the user's own copies, Triangle Strategy's effects;
analysis only, nothing of them is kept) and on Kenney's CC0 impact sounds:

    thrust       a spear's push: 0.28 s, in in 25 ms, the air centred near 0.9 kHz and falling ~36 semitones
    pierce       the point going in: in in 15 ms, 0.44 s, noisy, the tear rising ~20 semitones
    dragoon      the jump: ~2.5 s, eight or so events: the leap, the air rushing up and down, a crash
    punch        the fist in the air: ~70 ms; landing: a low body thump (centre ~115 Hz, all under ~450 Hz), 0.28 s
    gunshot      0.6-0.8 s, in in 5-22 ms, a boom centred near 0.7-1.1 kHz over a long low tail
    reload       four quick bright clicks in ~0.26 s
    throw        a short bright swish, 0.13-0.14 s
    bomb         ~0.64 s and four or so events: the hiss, the bang, its debris

Each style is a different weapon of the kind; size makes it bigger and lower, power harder.
"""
from dataclasses import replace

from ..spec import Modal, Noise, Scatter
from . import Fx, bell_curve, decay_curve, recipe
from .physical import arrow_in_flesh, arrow_in_wood, burst, flesh, gear_move, impact, splits, thud, whoosh


def _air(start, dur, f0, f1, q=1.4, gain=1.0, attack=0.025):
    """A fast push of air whose band falls (a thrust, a jab): from f0 to f1 Hz."""
    return Noise(round(start, 4), round(dur, 4), [(0, f0), (0.25, f0 * 0.8), (1, f1)], "band", q,
                 amp=[(0, 0.0), (0.12, 1.0), (0.45, 0.45), (1, 0.0)], attack=attack, release=0.02,
                 wobble=(30.0, 0.25), gain=gain)


@recipe("spear", ("thrust", "swing", "hit_flesh", "hit_metal", "jump", "land"), ("spear", "halberd"))
def spear(fx: Fx):
    """Spears and halberds: the thrust, a wide swing, the point going into flesh or armour, the dragoon's jump."""
    e, s, p = fx.event, fx.size, fx.power
    heavy = fx.style == "halberd"
    low = 2 ** (-0.6 * (s - 0.5)) * (0.75 if heavy else 1.0)
    if e == "thrust":       # 0.28 s, centred ~0.9 kHz, falling ~36 semitones
        dur = 0.28 * (1.25 if heavy else 1.0) * (0.9 + 0.2 * fx.rand("d"))
        layers = [_air(0.0, dur, 1000 * low, 120 * low, q=1.2, gain=1.0, attack=0.015),
                  thud(0.0, 0.06, 180 * low, 0.25)]
        return fx.voice(fx.level(0.75), **splits(layers))
    if e == "swing":        # a wide arc: slower, lower, the head's mass pushing air
        dur = 0.45 * (1.3 if heavy else 1.0)
        return fx.voice(fx.level(0.75), **splits(whoosh(fx, 0.0, dur, 700 * low, 1.2, 1.0, whistle=0.15) +
                                                 [thud(dur * 0.3, 0.2, 120 * low, 0.3)]))
    if e == "hit_flesh":    # in in 15 ms, 0.44 s: a crack, the tear rising, the body's thump
        layers = flesh(fx, 0.0, 1.0, 0.9)
        layers += [burst(0.0, 0.015, 4500, 0.7),
                   Noise(0.005, 0.4, [(0, 1100), (1, 2000)], "band", 1.4, amp=decay_curve(4), attack=0.003,
                         release=0.03, wobble=(45.0, 0.8), gain=0.55 * (0.7 + 0.6 * p))]
        if heavy:
            layers.append(thud(0.0, 0.25, 110, 0.6))
        return fx.voice(fx.level(0.85), **splits(layers))
    if e == "hit_metal":    # the point on armour: a sharp ring, a scrape off it
        layers = impact(fx, "steel", "iron", 0.8)
        layers.append(Noise(0.02, 0.25, [(0, 3500), (1, 2500)], "band", 2.0, amp=bell_curve(0.2, 1.5),
                            attack=0.005, release=0.03, wobble=(80.0, 0.6), gain=0.35))
        return fx.voice(fx.level(0.85), **splits(layers))
    if e == "jump":         # the dragoon leaps: a crouch, the push off the ground, the air rushing up
        layers = gear_move(fx, "chainmail", 0.25, 0.8) + [thud(0.22, 0.18, 140, 0.9),
                                                         Noise(0.25, 0.9, [(0, 300), (1, 2600)], "band", 1.0,
                                                               amp=bell_curve(0.35, 1.5), attack=0.05, release=0.1,
                                                               wobble=(18.0, 0.5), gain=0.8)]
        return fx.voice(fx.level(0.8), **splits(layers))
    # land: the air rushing down, then the crash: the point into the ground, the ground breaking, the armour
    layers = [Noise(0.0, 0.5, [(0, 2600), (1, 500)], "band", 1.0, amp=[(0, 0.2), (0.85, 1.0), (1, 0.8)],
                    attack=0.02, release=0.02, wobble=(20.0, 0.5), gain=0.8),
              thud(0.5, 0.5, 120, 1.0), burst(0.5, 0.05, 2500, 0.8),
              Noise(0.5, 1.4, [(0, 160), (1, 60)], "low", 0.9, "brown", decay_curve(4), attack=0.01, release=0.2,
                    wobble=(5.0, 0.4), gain=0.7),
              fx.strike("stone", start=0.5, size=0.7, gain=0.5, prefix="ground"),
              Scatter(0.52, 1.2, [(0, 150), (0.3, 50), (1, 0)], "pop", (500, 5000), (0.001, 0.005), (0.2, 1.0), 0.5)]
    layers += [replace(x, start=round(x.start + 0.5, 4)) for x in gear_move(fx, "plate", 0.3, 1.0)]
    return fx.voice(fx.level(0.9), **splits(layers), space=1.2, wet=0.15)


@recipe("fist", ("swing", "kick", "hit_flesh", "hit_heavy", "hit_armor", "block"), ("bare", "gauntlet"))
def fist(fx: Fx):
    """Bare hands and gauntlets: a jab and a kick through the air, landing on a body, hard, on armour, blocked."""
    e, s, p = fx.event, fx.size, fx.power
    iron = fx.style == "gauntlet"
    low = 2 ** (-0.5 * (s - 0.5))
    if e in ("swing", "kick"):   # ~70 ms of air for a jab; a kick is longer and lower
        dur = 0.08 if e == "swing" else 0.2
        layers = [_air(0.0, dur * (0.9 + 0.2 * fx.rand("d")), (1400 if e == "swing" else 800) * low,
                       (500 if e == "swing" else 250) * low, q=1.0, gain=1.0, attack=0.01)]
        if e == "kick":
            layers += gear_move(fx, "leather", dur + 0.05, 0.6)[:1]
        return fx.voice(fx.level(0.6 if e == "swing" else 0.7), **splits(layers))
    if e in ("hit_flesh", "hit_heavy"):   # a low body thump (centre ~115 Hz, all under ~450 Hz), 0.28 s, a slap
        heavy = e == "hit_heavy"
        f = 115 * low * (0.9 + 0.2 * fx.rand("f"))
        layers = [Modal(0.0, 0.4, [(round(f, 1), 0.28 + 0.1 * heavy, 1.0), (round(f * 1.7, 1), 0.12, 0.35),
                                   (round(f * 2.6, 1), 0.06, 0.15)], [(0.0, 1.0, 0.008)], hardness=600, click=0.1),
                  thud(0.0, 0.3 + 0.1 * heavy, 140 * low, 0.8),
                  Noise(0.0, 0.04, [(0, 2000), (1, 1200)], "band", 0.8, amp=decay_curve(5), attack=0.001,
                        release=0.01, gain=0.15 if not iron else 0.1)]          # the slap of skin
        if heavy or p > 0.7:
            layers.append(Scatter(0.0, 0.08, [(0, 500), (1, 0)], "pop", (300, 1500), (0.001, 0.004), (0.3, 1.0),
                                  0.4))
        if iron:
            layers.append(fx.strike("iron", size=0.2, gain=0.15, prefix="g", dur=0.3))
        return fx.voice(fx.level(0.8 if heavy else 0.7), **splits(layers))
    if e == "hit_armor":
        layers = impact(fx, "iron" if iron else "wood", "iron", 0.0, 0.8) + [thud(0.0, 0.15, 160 * low, 0.6)]
        return fx.voice(fx.level(0.8), **splits(layers))
    # block: forearm or gauntlet meets the blow: dull, short, cloth
    layers = [thud(0.0, 0.12, 180 * low, 0.9)] + gear_move(fx, "leather", 0.15, 0.7)[:1]
    if iron:
        layers.append(fx.strike("iron", size=0.35, gain=0.5, prefix="b", dur=0.4))
    return fx.voice(fx.level(0.65), **splits(layers))


@recipe("gun", ("shot", "click", "reload", "impact"), ("pistol", "musket", "cannon"))
def gun(fx: Fx):
    """Flintlocks and cannons: the shot, the hammer cocked, the reload, the ball striking."""
    e, s = fx.event, fx.size
    style = fx.style
    big = {"pistol": 0.0, "musket": 0.5, "cannon": 1.0}[style] * 0.7 + 0.3 * s
    if e == "shot":        # 0.6-0.8 s, in in 5-22 ms: the flint, the pan, the bang, the tail
        length = 0.6 + 0.4 * big + (0.4 if style == "cannon" else 0.0)
        layers = [Noise(0.0, round(length, 3), [(0, 1500 - 700 * big), (0.2, 900 - 400 * big), (1, 400 - 200 * big)],
                        "band", 0.7, amp=decay_curve(6), attack=0.002, release=0.1, wobble=(8.0, 0.08), gain=1.0),
                  Noise(0.0, round(length * 1.2, 3), [(0, 160 - 90 * big), (1, 50)], "low", 0.9, "brown",
                        decay_curve(4), attack=0.004, release=0.2, gain=0.35 + 0.4 * big),
                  burst(0.0, 0.006, 3000, 1.0), burst(0.0, 0.08, 2200, 0.7, "band", 0.6)]
        if style != "cannon":   # the flint strikes and the pan flashes just before
            layers = [replace(x, start=round(x.start + 0.045, 4)) for x in layers]
            layers += [fx.strike("iron", size=0.05, gain=0.35, prefix="flint", dur=0.15),
                       Noise(0.01, 0.04, [(0, 5000), (1, 3000)], "band", 0.7, amp=bell_curve(0.4, 1.5),
                             attack=0.002, release=0.005, gain=0.4)]
        return fx.voice(fx.level(1.0), **splits(layers), space=1.0 + big, wet=0.18)
    if e == "click":       # the hammer cocked: two clicks
        return fx.voice(fx.level(0.5), modal=[fx.strike("iron", start=0.0, size=0.05, gain=0.7, prefix="c1", dur=0.12),
                                              fx.strike("iron", start=0.11 + 0.03 * fx.rand("gap"), size=0.08,
                                                        gain=1.0, prefix="c2", dur=0.15)])
    if e == "reload":      # four quick bright clicks in ~0.26 s (a cannon: the ball rolled in, the rammer)
        if style == "cannon":
            layers = [Noise(0.0, 0.7, [(0, 300), (1, 200)], "band", 1.0, amp=bell_curve(0.5, 1.5), attack=0.05,
                            release=0.1, wobble=(12.0, 0.6), gain=0.7), fx.strike("iron", start=0.7, size=0.9,
                                                                                  gain=0.8, prefix="ball"),
                      thud(1.0, 0.2, 140, 0.8), thud(1.3, 0.2, 140, 0.7)]
            return fx.voice(fx.level(0.7), **splits(layers))
        times = [0.0, 0.07, 0.15, 0.26]
        layers = [fx.strike("steel", start=round(t * (0.9 + 0.2 * fx.rand(f"t{k}")), 4), size=0.0,
                            gain=0.5 + 0.15 * k, prefix=f"r{k}", dur=0.1, ring=0.15) for k, t in enumerate(times)]
        layers += [burst(round(t, 4), 0.01, 5000, 0.4) for t in times]
        if style == "musket":   # the ramrod down the barrel
            layers.append(Noise(0.3, 0.35, [(0, 1500), (1, 2500)], "band", 2.0, amp=bell_curve(0.5, 1.5),
                                attack=0.02, release=0.05, wobble=(60.0, 0.6), gain=0.4))
        return fx.voice(fx.level(0.6), **splits(layers))
    # impact: the ball strikes: a crack, splinters and dust (Tactics Ogre: 0.29 s, noisy, ~1.9 kHz)
    layers = [burst(0.0, 0.03, 1500, 0.8), thud(0.0, 0.15, 250 - 100 * big, 0.8),
              Scatter(0.0, 0.3, [(0, 300), (1, 0)], "pop", (600, 3500), (0.001, 0.005), (0.2, 1.0), 0.5),
              Noise(0.0, 0.3, [(0, 1700), (1, 1300)], "band", 0.9, amp=decay_curve(4), attack=0.002, release=0.02,
                    gain=0.6)]
    return fx.voice(fx.level(0.85), **splits(layers))


@recipe("thrown", ("throw", "fly", "hit_wood", "hit_flesh", "fuse", "blast"), ("knife", "shuriken", "bomb"))
def thrown(fx: Fx):
    """Thrown weapons: the throw, the spin through the air, the hit; a bomb's fuse and its blast."""
    e, s, p = fx.event, fx.size, fx.power
    style = fx.style
    if e == "throw":       # a short bright swish, 0.13-0.14 s
        layers = [_air(0.0, 0.14 * (0.9 + 0.2 * fx.rand("d")), 8000 if style == "shuriken" else 4000, 2000,
                       q=1.2, attack=0.01)]
        return fx.voice(fx.level(0.6), **splits(layers))
    if e == "fly":         # spinning: a shuriken whirrs fast and high, a knife flips, a bomb tumbles
        rate, hz = {"shuriken": (28.0, 5500), "knife": (12.0, 2200), "bomb": (6.0, 700)}[style]
        n = 2 * int(rate * 0.5) + 1                         # the blade comes round: loud, soft, loud...
        amp = [(round(i / (n - 1), 4), 1.0 if i % 2 == 0 else 0.25) for i in range(n)]
        layers = [Noise(0.0, 0.5, [(0, hz), (1, hz * 0.85)], "band", 2.5, amp=amp, attack=0.02, release=0.05,
                        wobble=(rate, 0.3), gain=1.0)]
        return fx.voice(fx.level(0.5), **splits(layers))
    if e in ("hit_wood", "hit_flesh"):
        if style == "bomb":   # a bomb lands with a thud and rolls
            return fx.voice(fx.level(0.6), **splits([thud(0.0, 0.2, 150, 1.0),
                                                     fx.strike("iron", size=0.6, gain=0.3, prefix="shell"),
                                                     Noise(0.1, 0.5, [(0, 600), (1, 400)], "band", 1.5,
                                                           amp=decay_curve(3), attack=0.05, wobble=(9.0, 0.8),
                                                           gain=0.4)]))
        layers = arrow_in_wood(fx, cross=True) if e == "hit_wood" else arrow_in_flesh(fx, cross=True)
        layers.append(fx.strike("steel", size=0.1, gain=0.25, prefix="blade", dur=0.4))
        return fx.voice(fx.level(0.8), **splits(layers))
    if e == "fuse":        # the fuse fizzing, sparks spitting
        layers = [Noise(0.0, 1.2, [(0, 5000), (1, 4500)], "band", 1.0, amp=[(0, 0.6), (1, 1.0)], attack=0.02,
                        release=0.02, wobble=(25.0, 0.7), gain=0.7),
                  Scatter(0.0, 1.2, [(0, 60), (1, 90)], "pop", (2000, 8000), (0.0005, 0.002), (0.2, 1.0), 0.6)]
        return fx.voice(fx.level(0.55), **splits(layers))
    # blast: a small bomb: ~0.64 s, a bang over its debris (bigger with size)
    length = 0.6 + 0.8 * s
    layers = [burst(0.0, 0.04, 2000, 0.9, "high", 0.5),
              Noise(0.0, round(length, 3), [(0, 220), (1, 60)], "low", 0.9, "brown", decay_curve(4), attack=0.01,
                    release=0.1, wobble=(5.0, 0.3), gain=1.0),
              Noise(0.0, round(length * 0.7, 3), [(0, 800), (1, 300)], "band", 0.8, amp=decay_curve(4), attack=0.01,
                    release=0.1, wobble=(9.0, 0.5), gain=0.5),
              Scatter(0.03, round(length, 3), [(0, 120 + 100 * p), (0.3, 40), (1, 0)], "pop", (500, 5000),
                      (0.001, 0.005), (0.2, 1.0), 0.45)]
    return fx.voice(fx.level(0.95), **splits(layers), space=0.8 + s, wet=0.15)
