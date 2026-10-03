"""The everyday sounds of a story: books and pages, cups, plates and cutlery, furniture, bells.

Measured on Triangle Strategy's story scenes (the user's analysis copy; nothing of it is kept), FFTA2's (the user's
own cartridge) and Kenney's CC0 RPG and impact sounds:

    page       one page turned: 0.35-0.9 s of paper, strongest 2-8 kHz, two or three crackles
    open       a book opened: 0.14-0.48 s, the cover's thump low (63-500 Hz) under paper
    close      a book shut: a short slap (~0.18 s), strongest 250-500 Hz
    place      set down: a ~0.17 s thump near 250 Hz
    clink      glasses touching: nearly pure tones at 1-2 kHz, ~0.11 s (longer in fine glass)
    set        a cup put down: 0.3-0.5 s, its ring near 1 kHz over the table's knock
    break      a dish breaking: ~0.9 s, bright (strongest 4-8 kHz) and noisy
    cutlery    light metal ticks at 1-4 kHz, a meal of them close together
    chair      dragged: ~0.4 s of scraping near 0.9 kHz; a desk thumped: ~0.36 s near 250 Hz
    bed        lain on: ~0.6 s of creaks and rustle, low
    bells      a church or wedding bell: ~7 s, 125 Hz-1 kHz; a small shop bell ~0.6 s near 2 kHz
"""
from dataclasses import replace

from ..score import Note
from ..spec import Modal, Noise, Scatter
from . import BELL_RATIOS, Fx, bell_curve, decay_curve, recipe
from .physical import breakable, creak, gulps, paper, splits, stick_slip, thud, wood_modes
from .ui import glass


def cover(fx: Fx, start: float, f: float, gain: float = 1.0, ring: float = 0.08) -> Modal:
    """A book's board cover meeting the pages or the table: a few low modes, quickly damped."""
    f *= 0.9 + 0.2 * fx.rand(f"cv{start}")
    modes = [(round(f, 1), ring, 1.0), (round(f * 1.9, 1), ring * 0.6, 0.5), (round(f * 3.1, 1), ring * 0.4, 0.3)]
    return Modal(round(start, 4), round(ring * 3 + 0.05, 3), modes, [(0.0, 1.0, 0.004)], hardness=1800, click=0.1,
                 gain=gain)


@recipe("book", ("open", "close", "page", "flip", "place", "write"), ("tome", "notebook", "scroll"))
def book(fx: Fx):
    """Books and scrolls: opened, shut, a page turned, pages riffled, set down, written in with a quill."""
    e, style = fx.event, fx.style
    heavy = {"tome": 1.0, "notebook": 0.3, "scroll": 0.0}[style] * (0.6 + 0.8 * fx.size)
    if e == "open":
        if style == "scroll":   # unrolled: paper crackling as it gives, a soft tap of the rod
            layers = paper(fx, 0.6, flap=False) + [cover(fx, 0.55, 600, 0.4)]
        else:
            layers = [cover(fx, 0.12, 180 - 60 * heavy, 0.9), thud(0.12, 0.12, 200, 0.5 * heavy)]
            layers += [replace(x, gain=round(x.gain * 0.6, 3)) for x in paper(fx, 0.2, flap=False)]
            layers += [Modal(0.0, 0.15, wood_modes(fx, 0.2, 0.02, 6), stick_slip(fx, 0.1, 0.012, 0.3, 0.5),
                             hardness=1500, click=0.02, gain=0.3)]                 # the spine giving
        return fx.voice(fx.level(0.6), **splits(layers))
    if e == "close":
        if style == "scroll":   # rolled back up
            layers = paper(fx, 0.45, flap=False) + [cover(fx, 0.45, 500, 0.5)]
        else:                   # a slap near 250-500 Hz and the air pushed out
            layers = [cover(fx, 0.0, 300 - 80 * heavy, 1.0, 0.06), thud(0.0, 0.1, 280, 0.6 * heavy),
                      Noise(0.0, 0.06, [(0, 900), (1, 500)], "band", 0.7, amp=decay_curve(5), attack=0.001,
                            release=0.01, gain=0.3)]
        return fx.voice(fx.level(0.65), **splits(layers))
    if e == "page":             # 0.35-0.9 s, 2-8 kHz, two or three crackles and the flap
        dur = 0.35 + 0.2 * fx.rand("page") + 0.15 * heavy
        layers = [replace(x, freq=[(t, f * 1.6) for t, f in x.freq]) if isinstance(x, Noise) and x.dur > 0.1 else x
                  for x in paper(fx, dur)]
        return fx.voice(fx.level(0.5), **splits(layers))
    if e == "flip":             # many pages riffled under a thumb
        dur = 0.7 + 0.3 * fx.rand("flip")
        layers = [Scatter(0.0, round(dur, 3), [(0, 70), (0.6, 40), (1, 5)], "pop", (2000, 8000), (0.002, 0.008),
                          (0.3, 1.0), 1.0),
                  Noise(0.0, round(dur, 3), [(0, 4000), (1, 3000)], "band", 0.6, amp=[(0, 1), (0.7, 0.6), (1, 0)],
                        attack=0.02, release=0.05, wobble=(35.0, 0.8), gain=0.5)]
        return fx.voice(fx.level(0.55), **splits(layers))
    if e == "place":            # set down: a ~0.17 s thump near 250 Hz, the table answering
        layers = [cover(fx, 0.0, 240, 1.0, 0.05), thud(0.0, 0.12, 250, 0.6 + 0.3 * heavy),
                  fx.strike("wood", size=0.5, gain=0.3, prefix="table", ring=0.5)]
        return fx.voice(fx.level(0.6), **splits(layers))
    # write: a quill scratching in strokes, dipped once
    strokes, t, layers = 5 + int(4 * fx.rand("strokes")), 0.0, []
    for k in range(strokes):
        d = 0.12 + 0.18 * fx.rand(f"s{k}")
        layers.append(Noise(round(t, 3), round(d, 3), [(0, 4500), (1, 3500 + 1500 * fx.rand(f"f{k}"))], "band", 2.0,
                            amp=bell_curve(0.4, 1.0), attack=0.01, release=0.02, wobble=(70.0, 0.9),
                            gain=round(0.5 + 0.4 * fx.rand(f"g{k}"), 3)))
        t += d + 0.04 + 0.12 * fx.rand(f"p{k}")
    layers.append(glass(Note(round(t + 0.1, 3), 0.3, 1800.0, 0.4, 0))[0])           # the nib tapped on the ink pot
    return fx.voice(fx.level(0.45), **splits(layers))


VESSELS = {   # material -> (the vessel's modes when struck: ratios, T60 s, gains), its base pitch Hz
    "glass": ([(1.0, 0.5, 1.0), (1.03, 0.4, 0.55), (2.26, 0.18, 0.22)], 1500.0),
    "ceramic": ([(1.0, 0.12, 1.0), (1.6, 0.08, 0.7), (2.4, 0.06, 0.5), (3.3, 0.05, 0.3)], 1700.0),
    "pewter": ([(1.0, 0.6, 1.0), (1.5, 0.45, 0.6), (2.3, 0.3, 0.5), (3.1, 0.2, 0.3)], 1100.0),
    "wood": ([(1.0, 0.05, 1.0), (2.7, 0.03, 0.4)], 600.0),
}


def vessel(fx: Fx, start: float, gain: float = 1.0, name: str = "v", ring: float = 1.0) -> Modal:
    modes, f0 = VESSELS[fx.style]
    f0 *= 2 ** (-0.8 * (fx.size - 0.5)) * (0.94 + 0.12 * fx.g.base("cup")) * (1 + 0.02 * (fx.rand(name) - 0.5))
    return Modal(round(start, 4), round(max(t for _, t, _ in modes) * ring * 1.2 + 0.05, 3),
                 [(round(f0 * r, 1), round(t * ring, 4), g) for r, t, g in modes], [(0.0, 1.0, 0.0006)],
                 hardness=14000 if fx.style != "wood" else 4000, click=0.05, gain=gain)


@recipe("tableware", ("clink", "set", "pour", "drink", "cutlery", "stir", "break"),
        ("glass", "ceramic", "pewter", "wood"))
def tableware(fx: Fx):
    """Cups, mugs and plates at a table: a toast, set down, poured into, drunk from, cutlery on a plate, a spoon
    stirring, a dish breaking."""
    e = fx.event
    if e == "clink":            # two touching: nearly pure tones, ~0.11 s (fine glass rings on)
        return fx.voice(fx.level(0.6), modal=[vessel(fx, 0.0, 1.0, "a"), vessel(fx, 0.004, 0.8, "b")])
    if e == "set":              # put down: its own ring over the table's knock
        return fx.voice(fx.level(0.6), **splits([vessel(fx, 0.0, 0.7, "a", 0.5),
                                                 fx.strike("wood", size=0.55, gain=0.6, prefix="table", ring=0.4),
                                                 thud(0.0, 0.08, 260, 0.4)]))
    if e == "pour":             # liquid pouring in: the vessel's air column rising as it fills, bubbling
        dur = 1.4 + 0.6 * fx.rand("pour")
        _, f0 = VESSELS[fx.style]
        return fx.voice(fx.level(0.55), **splits([
            Noise(0.0, round(dur, 3), [(0, f0 * 0.25), (1, f0 * 0.9)], "band", 2.5, amp=[(0, 0.3), (0.1, 1), (0.9, 1),
                                                                                        (1, 0)],
                  attack=0.05, release=0.1, wobble=(22.0, 0.6), gain=0.8),
            Noise(0.0, round(dur, 3), [(0, 3500), (1, 3000)], "band", 0.7, attack=0.05, release=0.1,
                  wobble=(30.0, 0.8), gain=0.35),
            Scatter(0.0, round(dur, 3), [(0, 40), (1, 25)], "drop", (500, 2000), (0.005, 0.02), (0.2, 1.0), 0.4)]))
    if e == "drink":
        layers = gulps(fx, 0.15, 2 + int(2 * fx.rand("gulps"))) + [vessel(fx, 0.0, 0.2, "lip", 0.3)]
        return fx.voice(fx.level(0.55), **splits(layers))
    if e == "cutlery":          # fork and knife on a plate: light metal ticks, close together
        n, t, layers = 5 + int(5 * fx.rand("n")), 0.0, []
        for k in range(n):
            layers.append(fx.strike("steel", start=round(t, 4), size=0.0, gain=round(0.3 + 0.5 * fx.rand(f"c{k}"), 3),
                                    prefix=f"c{k}", dur=0.15, ring=0.12))
            if fx.rand(f"p{k}") < 0.5:   # the plate under it answering
                layers.append(vessel(fx, t, 0.3, f"p{k}", 0.3))
            t += 0.05 + 0.2 * fx.rand(f"t{k}")
        return fx.voice(fx.level(0.5), **splits(layers))
    if e == "stir":             # a spoon going round a cup: a tinkle at each turn, ~4 a second
        layers = [vessel(fx, round(0.25 * k + 0.03 * fx.rand(f"s{k}"), 4), round(0.4 + 0.3 * fx.rand(f"g{k}"), 3),
                         f"s{k}", 0.4) for k in range(5)]
        layers.append(Noise(0.0, 1.3, [(0, 1200), (1, 1300)], "band", 1.5, amp=[(0, 0.5), (1, 0.5)], attack=0.05,
                            release=0.1, wobble=(4.0, 0.9), gain=0.2))
        return fx.voice(fx.level(0.5), **splits(layers))
    # break: a dish or a glass breaking on the floor: ~0.9 s, bright, noisy
    style = "glass" if fx.style == "glass" else "pot" if fx.style in ("ceramic", "pewter") else "crate"
    return fx.voice(fx.level(0.9), **splits(breakable(fx, style, True, 0.3 + 0.4 * fx.size)))


@recipe("furniture", ("chair", "sit", "desk", "drawer_open", "drawer_close", "bed"), ("wood", "oak"))
def furniture(fx: Fx):
    """Furniture: a chair dragged back, sat on, a fist on the desk, a drawer opened and shut, lying down in bed."""
    e = fx.event
    heavy = 1.0 if fx.style == "oak" else 0.0
    if e == "chair":            # ~0.4 s of scraping near 0.9 kHz, the joints creaking
        dur = 0.35 + 0.1 * fx.rand("drag") + 0.1 * heavy
        layers = [Modal(0.0, round(dur + 0.1, 3), wood_modes(fx, 0.25 + 0.1 * heavy, 0.03, 10),
                        stick_slip(fx, dur, 0.009, 0.3, 0.7), hardness=3000, click=0.05),
                  Noise(0.0, round(dur, 3), [(0, 900), (1, 800)], "band", 1.0, amp=bell_curve(0.4, 1.0), attack=0.02,
                        release=0.03, wobble=(40.0, 0.8), gain=0.5)]
        return fx.voice(fx.level(0.55), **splits(layers + creak(fx, 0.25)))
    if e == "sit":
        return fx.voice(fx.level(0.5), **splits(creak(fx, 0.4) + [thud(0.0, 0.15, 180, 0.6)]))
    if e == "desk":             # a fist on the desk: ~0.36 s near 250 Hz, what is on it jumping
        layers = [thud(0.0, 0.25, 250, 1.0), fx.strike("wood", size=0.7 + 0.2 * heavy, gain=0.7, prefix="top"),
                  Scatter(0.03, 0.2, [(0, 30), (1, 0)], "pop", (800, 3000), (0.002, 0.006), (0.2, 1.0), 0.3)]
        return fx.voice(fx.level(0.75), **splits(layers))
    if e in ("drawer_open", "drawer_close"):   # wood sliding on wood, the contents rattling, the stop
        dur = 0.4 if e == "drawer_open" else 0.25
        layers = [Modal(0.0, round(dur + 0.1, 3), wood_modes(fx, 0.3, 0.03, 8), stick_slip(fx, dur, 0.015, 0.4, 0.5),
                        hardness=2500, click=0.05, gain=0.7),
                  Noise(0.0, round(dur, 3), [(0, 600), (1, 700)], "band", 1.0, amp=bell_curve(0.5, 1.0), attack=0.03,
                        release=0.03, wobble=(25.0, 0.7), gain=0.5),
                  fx.strike("wood", start=round(dur, 4), size=0.4, gain=0.6 if e == "drawer_close" else 0.35,
                            prefix="stop"),
                  Scatter(round(dur * 0.6, 3), 0.25, [(0, 40), (1, 0)], "pop", (1500, 6000), (0.002, 0.006),
                          (0.2, 1.0), 0.35)]
        return fx.voice(fx.level(0.6), **splits(layers))
    # bed: ~0.6 s of creaks and rustle, low
    rustle = Noise(0.0, 0.6, [(0, 700), (1, 500)], "band", 0.6, amp=bell_curve(0.3, 1.0), attack=0.05, release=0.1,
                   wobble=(15.0, 0.7), gain=0.6)
    return fx.voice(fx.level(0.55), **splits([thud(0.0, 0.2, 130, 0.9), rustle] + creak(fx, 0.5)))


@recipe("bell", ("ring", "toll"), ("church", "hand", "shop", "ship"))
def bell(fx: Fx):
    """Bells: a church or wedding bell (~7 s, 125 Hz-1 kHz), a hand bell, a shop's door bell (~0.6 s near 2 kHz),
    a ship's bell; struck once (ring) or tolled."""
    style, e = fx.style, fx.event
    root = {"church": 130.0, "hand": 900.0, "shop": 2100.0, "ship": 520.0}[style]
    root *= 2 ** (-0.6 * (fx.size - 0.5)) * (0.95 + 0.1 * fx.g.base("bell"))
    t60 = {"church": 6.0, "hand": 1.2, "shop": 0.45, "ship": 2.5}[style]
    modes = [(round(root * r * (1 + 0.004 * (fx.g.base(f"b{i}") - 0.5)), 1), round(t60 / (1 + 0.6 * i) ** 0.7, 3),
              round(1 / (1 + i) ** 0.4, 3)) for i, r in enumerate(BELL_RATIOS) if root * r < 16000]
    if style == "shop":         # a little bell on a spring, jingling
        hits = [(round(0.07 * k * (0.8 + 0.4 * fx.rand(f"j{k}")), 4), round(0.9 ** k, 3), 0.0005) for k in range(6)]
        strikes = 1
    elif style == "hand":       # a clapper swung a few times
        hits = [(round(0.18 * k, 4), round(0.85 ** k, 3), 0.001) for k in range(4)]
        strikes = 1
    else:
        hits = [(0.0, 1.0, 0.002)]
        strikes = 3 if e == "toll" else 1
    gap = {"church": 2.0, "ship": 0.5}.get(style, 1.0)
    if style == "ship" and e == "toll":
        gap = 0.45
    layers = []
    for k in range(strikes):
        at = k * gap + (0.8 if style == "ship" and k >= 2 else 0.0)            # a ship's bell rings in pairs
        layers.append(Modal(round(at, 4), round(max(t for _, t, _ in modes) * 1.1 + 0.2, 3), modes, hits,
                            hardness=5000 if style == "church" else 9000, click=0.02,
                            gain=round(1.0 - 0.1 * k, 3)))
    extra = {"space": 3.0, "wet": 0.3} if style == "church" else {}
    return fx.voice(fx.level(0.8), **splits(layers), **extra)
