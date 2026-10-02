"""8-bit cries: brand-new Game Boy programs in the style of Gen 1 (no game data involved)."""
from ..spec import ChipProgram
from . import Ctx, archetype, geo

CALM_DUTIES = [0x00, 0x55, 0xAA, 0xFF, 0xF0, 0x0F, 0xA0, 0x5F]
HARSH_DUTIES = [0x1B, 0xE4, 0x5A, 0xA5, 0xC6, 0x39]   # rotate through widths every frame: buzzy


def _register(hz: float) -> int:
    """Frequency in Hz -> 11-bit Game Boy frequency register."""
    return min(max(round(2048 - 131072 / min(max(hz, 70.0), 4000.0)), 0), 2047)


@archetype("chip")
def chip(c: Ctx):
    """Retro 8-bit cry on a Game Boy-style 2 pulse + noise engine."""
    g = c.g
    n = g.int("notes", 3, 6) + (1 if c.call.repeats > 1 else 0)
    f_base = geo(1400, 160, c.size) * g.lrange("f", 0.8, 1.25)
    peak = g.int("peak", 0, 2)
    semis, s = [], 0.0
    for k in range(n):
        if k:
            s += g.range(f"up{k}", 1, 7) if k <= peak else -g.range(f"down{k}", 1, 8)
        semis.append(s + c.call.pitch + c.call.bend * k / max(n - 1, 1))
    harsh = c.aggr > 0.6
    duties = HARSH_DUTIES if harsh else CALM_DUTIES
    detune = g.int("detune", 2, 20) + int(24 * c.aggr)

    pulse1, pulse2 = [{"duty": g.choice("duty1", duties)}], [{"duty": g.choice("duty2", duties)}]
    for k, st in enumerate(semis):
        last = k == n - 1
        length = g.int("len_last", 6, 15) if last else g.int(f"len{k}", 1, 8)
        volume = 15 - g.int(f"vol{k}", 0, 3)
        fade = g.int("fade_last", 1, 4) if last else g.int(f"fade{k}", 1, 6)
        x = _register(f_base * 2 ** (st / 12))
        pulse1.append({"note": [length, volume, fade, x]})
        pulse2.append({"note": [length + (1 if k == 0 else 0), max(volume - 3, 1), fade, max(x - detune, 0)]})

    noise = []
    for j in range(g.int("n_noise", 1, 4) if c.aggr > 0.15 or g.chance("noisy", 0.5) else 0):
        shift = min(max(int(1 + 4 * c.size + g.range(f"nshift{j}", -1, 1.5)), 0), 7)
        param = (shift << 4) | (8 if g.chance("short_noise", 0.7) else 0) | g.choice("ndiv", [2, 3, 4, 4, 5])
        noise.append({"note": [g.int(f"nlen{j}", 1, 12), min(8 + g.int(f"nvol{j}", 0, 3) + int(4 * c.aggr), 15),
                               g.int(f"nfade{j}", 1, 4), param]})

    tempo = round(256 * (c.call.duration * (0.7 + 0.8 * c.size) - 1))
    program = ChipProgram(pulse1=pulse1, pulse2=pulse2, noise=noise, length=min(max(tempo, -128), 127))
    return c.voice([], chips=[program])
