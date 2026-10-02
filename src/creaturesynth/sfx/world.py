"""World interactions: levers, traps, torches, water.

Measured on recordings: a lever ratchets (clicks every 40-70 ms over 0.3-0.5 s, mid 0.5-3 kHz, mechanism modes
~330-1000 Hz) and ends in a clunk; a torch catches with a scratch and a flaring whoosh that settles into crackling
(broad 1-6 kHz, ~1 s); a splash is bright (strongest 2.5-8 kHz, 0.2-1 s) with a low plop and droplets; a spike trap
slides out with a metallic shing (modes 5-8 kHz) over its mechanism.
"""
from ..spec import Modal, Noise, Scatter
from . import Fx, bell_curve, decay_curve, recipe
from .physical import blade_swing, fletching, flyby, splits


@recipe("lever", ("pull", "push"), ("iron", "wood"))
def lever(fx: Fx):
    """A lever or crank: ratcheting clicks, a clunk at the end, a mechanism rumbling somewhere."""
    iron, s = fx.style == "iron", fx.size
    n = 5 + int(4 * fx.rand("teeth"))
    clicks, t = [], 0.0
    for k in range(n):
        clicks.append((round(t, 4), round(0.4 + 0.4 * fx.rand(f"c{k}"), 3), 0.0008))
        t += 0.04 + 0.03 * fx.rand(f"ct{k}")
    end = round(t + 0.05, 4)
    pawl = fx.strike("iron" if iron else "wood", size=0.1, hits=clicks, gain=0.6, prefix="pawl", dur=end + 0.2)
    clunk = fx.strike("iron" if iron else "wood", size=0.6 + 0.3 * s, start=end, hits=[(0.0, 1.0, 0.003)], gain=1.0,
                      prefix="clunk", ring=0.5)
    body = Modal(0.0, round(end + 0.4, 3), [(330, 0.15, 1.0), (490, 0.15, 0.8), (940, 0.07, 0.5), (1030, 0.15, 0.4)],
                 [*clicks, (end, 1.0, 0.004)], hardness=3000, click=0.0, gain=0.5)
    ticks = [Noise(t, 0.004, [(0, 3500), (1, 3500)], "high", 0.7, amp=decay_curve(4), attack=0.0003, release=0.001,
                   gain=0.5 * g) for t, g, _ in clicks]   # the pawl snapping over each tooth
    layers = [pawl, clunk, body, *ticks]
    if fx.event == "pull":   # what it moves: a chain and gears grinding for a moment
        layers += [Noise(end, 0.9, [(0, 140), (1, 110)], "low", 1.0, amp=bell_curve(0.3, 1.2), attack=0.05,
                         wobble=(9.0, 0.6), gain=0.5),
                   Scatter(end, 0.9, [(0, 30), (0.5, 40), (1, 0)], "pop", (300, 1500), (0.003, 0.01), (0.3, 1.0), 0.4)]
    return fx.voice(fx.level(0.8), **splits(layers))


@recipe("trap", ("trigger", "fire"), ("darts", "spikes", "blade"))
def trap(fx: Fx):
    """Dungeon traps: the pressure plate clicks (trigger), then darts fly, spikes shoot up or a blade swings (fire)."""
    style = fx.style
    if fx.event == "trigger":   # a stone slab sinks, a catch releases
        slab = fx.strike("stone", size=0.8, hits=[(0.0, 1.0, 0.004)], gain=0.8, prefix="slab", ring=0.5, click=0.2)
        catch = fx.strike("iron", size=0.05, start=0.06, hits=[(0.0, 1.0, 0.0006), (0.03, 0.5, 0.0006)], gain=0.6,
                          prefix="catch")
        return fx.voice(fx.level(0.7), modal=[slab, catch],
                        noise=[Noise(0.0, 0.08, [(0, 300), (1, 150)], "low", 0.9, amp=decay_curve(5), gain=0.5)])
    if style == "darts":   # several short fly-bys and the darts striking the far wall
        layers = []
        for k in range(3 + int(3 * fx.rand("darts"))):
            t = 0.03 * k + 0.05 * fx.rand(f"d{k}")
            layers += [n for n in fletching(t, *flyby(0.12 + 0.05 * fx.rand(f"a{k}"), 0.08, 3800.0),
                                            gain=0.5 + 0.3 * fx.rand(f"g{k}"))]
            layers.append(fx.strike("wood", size=0.2, start=round(t + 0.22, 4), hits=[(0.0, 0.6, 0.001)], gain=0.4,
                                    prefix=f"thunk{k}"))
        return fx.voice(fx.level(0.8), **splits(layers))
    if style == "spikes":   # iron spikes slide out of their sleeves: a shing, then the clank at full height
        shing = Modal(0.0, 0.5, [(5226, 0.38, 1.0), (6445, 0.3, 0.6), (7664, 0.09, 0.7), (7757, 0.15, 0.9),
                                 (3773, 0.23, 0.5)], [(0.12, 0.5, 0.0008)], (0.0, 0.12, 1.0, 0.0), 12000, 0.1)
        clank = fx.strike("iron", size=0.4, start=0.12, hits=[(0.0, 1.0, 0.001)], gain=0.8, prefix="clank", ring=0.6)
        return fx.voice(fx.level(0.9), modal=[shing, clank],
                        noise=[Noise(0.0, 0.13, [(0, 5000), (1, 7000)], "high", 0.7, amp=[(0, 0.3), (1, 1)],
                                     attack=0.005, release=0.01, gain=0.5),
                               Noise(0.0, 0.25, [(0, 500), (1, 300)], "low", 0.9, amp=[(0, 0.5), (0.45, 1), (1, 0)],
                                     attack=0.01, wobble=(20.0, 0.5), gain=0.7)])   # the mechanism driving them
    # a swinging blade: a heavy, slow swing, the pivot creaking
    layers = blade_swing(fx, 0.18, 0.3, 700.0, 0.0, 0.6, 140.0)
    layers.append(fx.strike("iron", size=0.5, hits=[(0.0, 0.4, 0.002)], gain=0.4, prefix="pivot", ring=0.5))
    return fx.voice(fx.level(0.8), **splits(layers))


@recipe("torch", ("ignite", "extinguish"), ("torch", "brazier"))
def torch(fx: Fx):
    """Fire caught (a scratch, a flaring whoosh settling into crackle) or put out (a hiss, sizzling)."""
    big = 1.0 if fx.style == "brazier" else 0.0
    if fx.event == "ignite":
        layers = [Noise(0.0, 0.1, [(0, 4000), (1, 6000)], "band", 0.8, amp=bell_curve(0.5, 1.5), attack=0.005,
                        wobble=(80.0, 0.9), gain=0.4),   # the strike
                  Noise(0.08, round(0.5 + 0.3 * big, 3), [(0, 300), (0.3, 1500 + 500 * big), (1, 800)], "low", 0.8,
                        amp=[(0, 0.2), (0.25, 1.0), (1, 0.15)], attack=0.03, wobble=(14.0, 0.5),
                        gain=0.9),   # the flare
                  Scatter(0.15, round(1.0 + 0.5 * big, 3), [(0, 20), (0.4, 90 + 60 * big), (1, 60)], "pop",
                          (1000, 6000), (0.0005, 0.003), (0.2, 1.0), 0.5)]
        return fx.voice(fx.level(0.8), **splits(layers))
    layers = [Noise(0.0, 0.7, [(0, 6000), (1, 2500)], "band", 0.7, amp=[(0, 1.0), (0.3, 0.6), (1, 0.0)], attack=0.01,
                    wobble=(30.0, 0.5), gain=0.8),   # hiss
              Scatter(0.0, 0.6, [(0, 120), (1, 0)], "pop", (2000, 8000), (0.0005, 0.002), (0.2, 1.0), 0.4)]
    return fx.voice(fx.level(0.7), **splits(layers))


@recipe("water", ("splash", "dive", "drip"), ("small", "big"))
def water(fx: Fx):
    """Water: something splashing in, a body diving, a drip. A low plop, a bright spray, droplets, bubbles."""
    big = 1.0 if fx.style == "big" else 0.0
    if fx.event == "drip":
        f0 = 900 + 900 * fx.rand("drip")
        return fx.voice(fx.level(0.5), scatter=[Scatter(0.0, 0.05, [(0, 40), (1, 40)], "drop", (f0, f0 * 1.2),
                                                        (0.008, 0.015), (1.0, 1.0))])
    dive = fx.event == "dive"
    plop = (150 if dive else 350) * (1 - 0.3 * big) * (0.85 + 0.3 * fx.rand("plop"))
    spray = (0.25 + 0.4 * dive) * (1 + 0.5 * big)
    layers = [Modal(0.0, 0.3, [(round(plop, 1), 0.07, 1.0), (round(plop * 2.3, 1), 0.04, 0.4)], [(0.0, 1.0, 0.006)],
                    hardness=1500, click=0.0, gain=0.7 + 0.2 * dive),
              Noise(0.005, round(spray, 3), [(0, 4500), (1, 3000)], "band", 0.6, amp=decay_curve(4), attack=0.004,
                    wobble=(45.0, 0.7), gain=1.0),
              Scatter(0.02, round(spray + 0.4, 3), [(0, 150 + 150 * big), (1, 0)], "drop", (600, 3000),
                      (0.003, 0.01), (0.2, 1.0), 0.6)]
    if dive:   # bubbles rising after the body goes under
        layers.append(Scatter(0.3, 0.9, [(0, 60), (1, 10)], "drop", (300, 1200), (0.01, 0.03), (0.2, 0.7), 0.35))
    return fx.voice(fx.level(0.8), **splits(layers))
