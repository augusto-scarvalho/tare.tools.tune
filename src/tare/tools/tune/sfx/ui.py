"""Interface sounds: clicks, opening the inventory, level up, quest complete, error.

Measured on game UI sounds: a click lasts 8-170 ms, a tick or a soft thump; opening a bag is a 0.4-1 s rustle;
level up is a rising major arpeggio (notes 60-150 ms apart) ending on a long bright note with sparkle, 1.6-3.4 s;
quest complete climbs the chord more slowly (~0.2 s per note) and rests on the top note; an error is short (0.14-0.6 s)
and low (around D#3-A3), a buzz or two falling tones. Two styles: "fantasy" (struck chimes, cloth and wood) and
"retro" (square-wave blips, like an 8-bit console).
"""
from ..spec import Modal, Noise, Scatter, Syllable
from . import Fx, bell_curve, decay_curve, recipe
from .physical import splits

BAR = (1.0, 2.756, 5.404, 8.933)   # a free bar's modes: glockenspiel, celesta


def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def chime(start: float, midi: float, ring: float = 1.0, gain: float = 1.0) -> Modal:
    """A struck metal bar at a note."""
    return bar(start, hz(midi), ring, gain)


def bar(start: float, f: float, ring: float = 1.0, gain: float = 1.0) -> Modal:
    """A struck metal bar whose lowest mode is `f`."""
    modes = [(round(f * r, 1), round(ring * 1.2 / (1 + 1.5 * i), 4), round(1 / (1 + i) ** 0.6, 4))
             for i, r in enumerate(BAR) if f * r < 18000]
    return Modal(round(start, 4), round(ring * 1.4 + 0.1, 3), modes, [(0.0, 1.0, 0.0006)], hardness=12000,
                 click=0.02, gain=gain)


def blip(start: float, midi: float, dur: float, gain: float = 1.0, glide: float = 0.0) -> Syllable:
    """A square-wave note."""
    f = hz(midi)
    return Syllable(round(start, 4), round(dur, 4), [(0, f), (1, f * 2 ** (glide / 12))], "pulse", 0.5, 0.7,
                    attack=0.002, release=min(0.03, dur / 3), gain=gain)


def arpeggio(fx: Fx, notes: list, step: float, hold: float, retro: bool) -> list:
    out = []
    for k, n in enumerate(notes):
        last = k == len(notes) - 1
        if retro:
            out.append(blip(k * step, n, hold if last else step * 0.9, 0.8 if last else 0.6))
        else:
            out.append(chime(k * step, n, hold if last else 0.6, 1.0 if last else 0.7))
    return out


@recipe("ui", ("click", "open", "close", "levelup", "quest", "error"), ("fantasy", "retro"))
def ui(fx: Fx):
    """Interface: menu click, opening and closing the inventory, level up, quest complete, error."""
    retro, e = fx.style == "retro", fx.event
    key = 72 + int(round(6 * (fx.g.base("key") - 0.5)))      # each game its own key, near C5
    if e == "click":
        if retro:
            return fx.voice(fx.level(0.5), syllables=[blip(0.0, key + 12, 0.025)])
        tick = Modal(0.0, 0.08, [(round(hz(key + 19) * (0.95 + 0.1 * fx.rand("t")), 1), 0.03, 1.0),
                                 (round(hz(key + 7), 1), 0.02, 0.4)], [(0.0, 1.0, 0.001)], hardness=6000, click=0.2)
        return fx.voice(fx.level(0.5), modal=[tick])
    if e in ("open", "close"):
        if retro:
            notes = [key, key + 7] if e == "open" else [key + 7, key]
            return fx.voice(fx.level(0.6), syllables=[blip(0.0, notes[0], 0.05, 0.6), blip(0.05, notes[1], 0.08, 0.6)])
        dur = 0.45 if e == "open" else 0.3
        layers = [Noise(0.0, dur, [(0, 900), (1, 1400)], "band", 0.7, amp=bell_curve(0.35, 1.3), attack=0.02,
                        wobble=(22.0, 0.7), gain=0.8),
                  Scatter(0.0, dur, [(0, 60), (0.5, 90), (1, 0)], "pop", (800, 4000), (0.001, 0.004), (0.2, 1.0), 0.3),
                  Modal(round(dur * (0.8 if e == "open" else 0.9), 3), 0.25, [(2600, 0.05, 1.0), (4100, 0.04, 0.6)],
                        [(0.0, 1.0, 0.0006)], hardness=12000, click=0.1, gain=0.35)]   # a buckle
        return fx.voice(fx.level(0.6), **splits(layers))
    if e == "levelup":   # the major chord climbing, the top note held, sparkle
        notes = [key, key + 4, key + 7, key + 12, key + 16, key + 19]
        layers = arpeggio(fx, notes, 0.075, 1.6, retro)
        if retro:
            layers.append(blip(len(notes) * 0.075, key + 24, 0.5, 0.7, 0.0))
        else:
            layers.append(Scatter(0.3, 1.6, [(0, 40), (1, 0)], "ping", (hz(key + 24), hz(key + 36)), (0.04, 0.15),
                                  (0.2, 0.7), 0.5))
        return fx.voice(fx.level(0.8), **splits(layers))
    if e == "quest":     # slower, resting on the top note over its root
        notes = [key - 2, key + 2, key + 5, key + 10]
        layers = arpeggio(fx, notes, 0.2, 2.0, retro)
        if not retro:
            layers.append(Syllable(0.6, 1.8, [(0, hz(key - 14)), (1, hz(key - 14))], "sine", 0.5, 0.3,
                                   attack=0.15, release=0.6, gain=0.35))   # a soft root underneath
        return fx.voice(fx.level(0.8), **splits(layers))
    # error: two falling tones, low and buzzy (retro) or a dull knock under a low tone (fantasy)
    low = key - 27
    if retro:
        return fx.voice(fx.level(0.6), syllables=[blip(0.0, low + 3, 0.1, 0.8), blip(0.12, low, 0.18, 0.8)])
    knock = Modal(0.0, 0.3, [(180, 0.08, 1.0), (420, 0.05, 0.5), (760, 0.04, 0.3)], [(0.0, 1.0, 0.004),
                                                                                    (0.13, 0.8, 0.004)],
                  hardness=2500, click=0.0)
    tone = Syllable(0.0, 0.32, [(0, hz(low + 3)), (0.45, hz(low + 3)), (0.5, hz(low)), (1, hz(low))], "glottal",
                    0.5, 0.4, attack=0.01, release=0.08, gain=0.6)
    return fx.voice(fx.level(0.6), modal=[knock], syllables=[tone],
                    noise=[Noise(0.0, 0.3, [(0, 300), (1, 250)], "low", 0.8, amp=decay_curve(3), gain=0.2)])
