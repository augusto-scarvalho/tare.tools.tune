"""Physical sounds: weapons, footsteps, explosions.

Struck bodies are modal (Fx.strike): the material sets the modes, size their pitch and decay,
power how hard the contact is. Air and debris are moving noise bands and scattered events.
"""
from dataclasses import replace

import numpy as np

from ..spec import Modal, Noise, Scatter, Syllable
from . import Fx, bell_curve, decay_curve, recipe

TARGETS = {"hit_flesh": "flesh", "hit_wood": "wood", "hit_metal": "iron", "hit_stone": "stone"}


# --- building blocks --------------------------------------------------------------------------------------------------

def whoosh(fx: Fx, start: float, dur: float, peak_hz: float, q: float = 1.5, gain: float = 1.0,
           whistle: float = 0.0, prefix: str = "") -> list[Noise]:
    """Air pushed by a moving object: a noise band sweeping up to `peak_hz` and back."""
    peak = 0.4 + 0.25 * fx.rand(prefix + "peak")
    freq = [(0.0, peak_hz / 4), (peak, peak_hz), (1.0, peak_hz / 3)]
    out = [Noise(start, round(dur, 3), freq, "band", q, amp=bell_curve(peak, 2.5), attack=0.0, release=0.0,
                 wobble=(25.0, 0.25), gain=gain)]
    if whistle:  # an edge or fletching sings at a narrow band
        out.append(Noise(start, round(dur, 3), [(t, f * 1.8) for t, f in freq], "band", 14.0,
                         amp=bell_curve(peak, 4), attack=0.0, release=0.0, gain=gain * whistle))
    return out


def thud(start: float, dur: float, hz: float, gain: float = 1.0) -> Noise:
    """Mass meeting mass: a short low noise burst, its pitch dropping."""
    return Noise(start, round(dur, 3), [(0.0, hz), (1.0, hz * 0.5)], "low", 1.2, amp=decay_curve(6),
                 attack=0.002, release=0.02, gain=gain)


def burst(start: float, dur: float, hz: float, gain: float = 1.0, kind: str = "high", q: float = 0.7) -> Noise:
    return Noise(start, round(dur, 3), [(0.0, hz), (1.0, hz)], kind, q, amp=decay_curve(5), attack=0.001,
                 release=0.01, gain=gain)


def flesh(fx: Fx, start: float, sharp: float, gain: float = 1.0) -> list:
    """Body hit: thump + wet squish, a crunch when hard, a slice for edges."""
    s = fx.size
    out = [thud(start, 0.12 + 0.12 * s, 220 - 100 * s, gain),
           Noise(start + 0.005, 0.14, [(0, 1800), (1, 1100)], "band", 1.8, amp=decay_curve(4), attack=0.003,
                 wobble=(40.0, 0.9), gain=0.45 * gain)]
    if fx.power > 0.5:
        out.append(Scatter(start, 0.06 + 0.06 * fx.power, [(0, 700), (1, 100)], "pop", (300, 1600),
                           (0.001, 0.004), (0.3, 1.0), 0.5 * gain * fx.power))
    if sharp:
        out.append(burst(start, 0.07, 3500, 0.5 * sharp * gain))
    return out


def splits(layers: list) -> dict:
    """Group spec elements by type into Voice keyword arguments."""
    out = {"modal": [], "noise": [], "scatter": [], "syllables": []}
    for e in layers:
        out[{Modal: "modal", Noise: "noise", Scatter: "scatter", Syllable: "syllables"}[type(e)]].append(e)
    return out


def impact(fx: Fx, weapon: str, target: str, edge: float, gain: float = 1.0) -> list:
    """`weapon` material hits `target`; `edge` 0 (blunt) .. 1 (blade)."""
    hard = 0.6 + 0.4 * fx.power
    out = []
    if target == "flesh":
        out += flesh(fx, 0.0, edge, gain)
        if weapon in ("steel", "iron", "bronze"):
            out.append(fx.strike(weapon, gain=0.08 * gain, prefix="w", dur=0.6))
        return out
    t_size = {"wood": 0.55, "iron": 0.55, "stone": 0.5}[target] + 0.2 * (fx.rand("target") - 0.5)
    out.append(fx.strike(target, size=t_size, hits=[(0.0, 1.0, 0.0015 / hard)], gain=gain, prefix="t"))
    if weapon != target or weapon in ("steel", "iron", "bronze"):
        out.append(fx.strike(weapon, hits=[(0.0, 1.0, 0.001 / hard)], gain=(0.6 if weapon != "wood" else 0.3) * gain,
                             prefix="w"))
    out.append(thud(0.0, 0.09 + 0.1 * fx.size, 300 - 120 * fx.size, 0.5 * gain * (1 - 0.5 * edge)))
    if target == "stone":
        out.append(Scatter(0.0, 0.15, [(0, 400), (1, 0)], "pop", (900, 6000), (0.0008, 0.003), (0.2, 1.0), 0.4 * gain))
        if weapon in ("steel", "iron"):  # sparks
            out.append(Scatter(0.0, 0.12, [(0, 120), (1, 0)], "ping", (6000, 11000), (0.004, 0.012),
                               (0.2, 1.0), 0.25 * gain))
    return out


def bounces(fx: Fx, count: int = 5, first: float = 0.22, e: float = 0.55, ends: int = 2) -> list:
    """A dropped object: bounces closing in, each one a clatter of `ends` contacts (a blade lands on both)."""
    t, gap, hits = 0.0, first * (0.8 + 0.4 * fx.rand("gap")), []
    for k in range(count):
        for j in range(ends):
            dt = j * (0.006 + 0.03 * fx.rand(f"end{k}{j}"))
            hits.append((round(t + dt, 4), round(0.7 ** k * (0.5 + 0.5 * fx.rand(f"b{k}{j}")), 3), 0.001))
        t += gap
        gap *= e
    return hits


# --- creaks -----------------------------------------------------------------------------------------------------------
#
# Modelled on a recording of a bow being drawn, measured at millisecond scale: stick-slip events
# ~70 per second in locally regular trains whose rate drifts, each one swelling over 1-2 ms and
# ringing ~10 ms in the wood (broad bands near 1.7, 2.9, 5.5 and 7.9 kHz, a main bending note near
# 1.2-1.7 kHz), getting louder as the tension grows, over faint friction noise.

WOOD_BANDS = [(1700, 1000, -5.0), (2900, 1900, -3.6), (5550, 1500, -8.0), (7900, 1600, -10.0),
              (10400, 2300, -12.8), (750, 500, -12.0)]   # centre Hz, width Hz, level dB


def wood_modes(fx: Fx, scale: float, t60: float, per_khz: int = 12) -> list:
    """Wood rings in many close, damped modes: a dense random set inside each measured band (fixed per species)."""
    out, k = [], 0
    for centre, width, db in WOOD_BANDS:
        n = max(int(width / 1000 * per_khz), 3)
        for _ in range(n):
            f = (centre + (fx.g.base(f"wm{k}") - 0.5) * width) * scale
            g = 10 ** (db / 20) / n ** 0.5 * (0.5 + fx.g.base(f"wg{k}"))
            decay = t60 * (0.6 + 0.8 * fx.g.base(f"wt{k}")) * (1700 / f) ** 0.3
            out.append((round(f, 1), round(decay, 4), round(g, 4)))
            k += 1
    for j in range(5):  # the main bending modes ring a little longer: the note of the creak
        f = (1150 + 600 * fx.g.base(f"main{j}")) * scale
        out.append((round(f, 1), round(2.3 * t60, 4), round(0.8 / (1 + 0.3 * j), 4)))
    return out


def stick_slip(fx: Fx, dur: float, ioi: float, spread: float = 0.25, drift: float = 0.6) -> list:
    """Hits for a creak: trains of slips whose rate drifts, louder as tension grows, a few big ones."""
    ctrl = [2 * fx.rand(f"drift{j}") - 1 for j in range(12)]
    t, hits, k = 0.02, [], 0
    while t < dur:
        u1, u2, u3, u4 = (fx.rand(f"slip{k}.{j}") for j in range(4))
        z = (-2 * np.log(max(u1, 1e-9))) ** 0.5 * np.cos(2 * np.pi * u2)
        prog = t / dur
        wander = 2 ** (drift * np.interp(prog * 11, np.arange(12), ctrl))
        tension = 0.3 + 0.7 * prog
        gain = tension * (0.3 + 0.7 * u3 ** 1.5) * (2.2 if u4 < 0.15 else 1.0)
        hits.append((round(t, 5), round(float(gain), 4), 0.0022))
        t += max(ioi * wander * np.exp(spread * z), 0.004)
        k += 1
    return hits


def creak(fx: Fx, dur: float) -> list:
    """Wood under growing strain (a bow drawn, a door, a ship's timber). Bigger means lower, slower, longer ringing."""
    scale = 0.72 * 2 ** (-0.8 * (fx.size - 0.5))
    ioi = 0.015 * (0.8 + 0.4 * fx.size)
    body = Modal(0.0, round(dur + 0.15, 3), wood_modes(fx, scale, 0.03 * (0.8 + 0.4 * fx.size) / 0.7),
                 stick_slip(fx, dur, ioi), hardness=4500, click=0.05)
    friction = Noise(0.0, round(dur, 3), [(0, 1500 * scale), (1, 1700 * scale)], "band", 1.2,
                     amp=[(0, 0.2), (0.5, 0.6), (1, 1.0)], attack=0.05, release=0.03, wobble=(30.0, 0.6), gain=0.03)
    return [body, friction]


def bow_release(fx: Fx, cross: bool = False) -> list:
    """Letting go, modelled on a measured recording (chosen by ear among three variants):
    a short fwip as the fingers open; the string grinding past the arrow, a rough buzz (~170 Hz)
    whose resonance glides down from ~800 to ~300 Hz while it swells ~20 dB; the slap, ringing the
    bow's own wood (the same body as the draw) and its low stop; then the string and limbs thrum
    (~57 Hz and harmonics) with a lingering ~1.1 kHz partial, while the arrow flies off (heard from the archer)."""
    k = 2 ** (-0.8 * (fx.size - 0.5))          # bigger bows are lower
    rush = 0.18 * (0.8 + 0.4 * fx.size) * (0.85 + 0.3 * fx.rand("rush")) * (0.5 if cross else 1.0)
    t = round(0.065 + rush, 4)
    tune = k * (1 + 0.04 * (fx.rand("tune") - 0.5))
    lo, hi = 780 * k, 320 * k
    return [
        Noise(0.0, 0.065, [(0, 6000), (1, 6000)], "band", 0.35, amp=[(0, 0.0), (0.45, 1.0), (1, 0.0)], attack=0.0,
              release=0.0, gain=0.6),
        Syllable(0.06, round(rush + 0.01, 4), [(0, 187 * k), (1, 153 * k)], "pulse", 0.3, 1.0, jitter=1.5,
                 rough=(0.5, 37.0), breath=0.6,
                 formants=[(lo, 200, 1.0), (lo * 1.35, 260, 0.7), (lo * 1.7, 300, 0.5), (5500, 3000, 1.2),
                           (8100, 2500, 0.8)],
                 mouth=[(0, 1.0), (1, hi / lo)], attack=0.005, release=0.004,
                 amp=[(0, 0.08), (0.5, 0.25), (0.85, 0.6), (1, 1.0)], gain=1.3 * (0.7 + 0.6 * fx.power)),
        Noise(t, 0.3, [(0, 3000), (1, 2500)], "high", 0.6, amp=decay_curve(7), attack=0.0005, release=0.03, gain=0.6),
        Modal(t, 0.3, wood_modes(fx, 0.72 * k, 0.03), [(0.0, 1.0, 0.002)], hardness=5000, click=0.3, gain=0.8),
        Modal(t, 0.25, [(196 * tune, 0.10, 1.0), (84 * tune, 0.15, 0.6), (345 * tune, 0.06, 0.35),
                        (790 * tune, 0.04, 0.2)], [(0.0, 1.0, 0.003)], hardness=3000, click=0.0),
        Modal(t, 0.8, [(57 * tune, 0.6, 1.0), (116 * tune, 0.5, 0.9), (148 * tune, 0.3, 0.35), (170 * tune, 0.3, 0.3),
                       (1100 * tune, 0.4, 0.12)], [(0.0, 1.0, 0.004)], hardness=2500, gain=0.6 if not cross else 0.35),
        *fletching(t, *departure(90.0 if cross else 60.0), gain=DEPARTURE_GAIN),
    ]


# --- arrows -----------------------------------------------------------------------------------------------------------
#
# Modelled on recordings of arrows flying past and hitting a target: the fletching hisses in a broad
# band near 3 kHz and flutters the air ~90 times a second. Passing a listener it swells ~40 dB (linear
# in dB), then drops ~30 dB in 0.15 s while its band falls (Doppler). Leaving the archer it fades as 1/r,
# already lower (c / (c + v)) and darker with distance. Stuck in a target the shaft rings near 160 Hz
# (with harmonics), pulsing ~26 times a second as it bends, for over a second.

DEPARTURE_GAIN = 1.2    # the arrow leaving, under the release: picks up where the string's buzz ends


def fletching(start: float, db: list, freq: list, gain: float = 1.0, flutter: tuple = (90.0, 0.45)) -> list[Noise]:
    """An arrow's flight along (seconds, dB) and (seconds, Hz) breakpoints: a fluttering band and its low body."""
    dur = db[-1][0]
    amp = [(round(t / dur, 4), round(10 ** (d / 20), 5)) for t, d in db]
    fq = [(round(t / dur, 4), round(f, 1)) for t, f in freq]
    return [Noise(start, round(dur, 3), fq, "band", 0.45, amp=amp, attack=0.0, release=0.01, wobble=flutter,
                  gain=gain),
            Noise(start, round(dur, 3), [(t, round(f * 0.35, 1)) for t, f in fq], "low", 0.7, amp=amp, attack=0.0,
                  release=0.01, gain=0.5 * gain)]


def departure(speed: float, dur: float = 0.55, near: float = 2.0, centre: float = 2800.0) -> tuple[list, list]:
    """Leaving the archer at `speed` m/s: level falls as 1/r (r = near + speed * t), pitch down and darkening."""
    ts = np.linspace(0, dur, 12)
    db = [(round(float(t), 4), round(float(-20 * np.log10(1 + speed * t / near)), 2)) for t in ts]
    hz = centre * 343 / (343 + speed)
    return db, [(0.0, hz), (dur, hz * 0.55)]


def flyby(approach: float, leave: float = 0.15, centre: float = 2800.0) -> tuple[list, list]:
    """Passing a listener: 40 dB swell to the pass, then 30 dB down in `leave` seconds as the band falls."""
    db = [(0.0, -40.0), (approach, 0.0), (approach + leave, -30.0)]
    freq = [(0.0, centre * 0.9), (approach, centre * 1.1), (approach + 0.3 * leave, centre * 0.45),
            (approach + leave, centre * 0.12)]
    return db, freq


def arrow_in_wood(fx: Fx, cross: bool = False) -> list:
    """An arrow striking a target: a crack, the target's dull body (~140-240 Hz) and the shaft left ringing."""
    k = 2 ** (-0.6 * (fx.size - 0.5)) * (1.5 if cross else 1.0)     # longer shafts ring lower, bolts higher
    tune = k * (1 + 0.06 * (fx.rand("tune") - 0.5))
    ring_hz, t60 = 158 * tune, 2.0 * (0.6 if cross else 1.0) * (0.8 + 0.4 * fx.rand("hold"))
    ring = [(ring_hz, t60, 1.0), (ring_hz * 1.17, t60 * 0.6, 0.3), (ring_hz * 1.335, t60 * 0.5, 0.4),
            (ring_hz * 0.835, t60 * 0.7, 0.35), (ring_hz * 0.33, t60 * 0.6, 0.15),
            (ring_hz + 26.0, t60, 0.8)]         # two close modes beat: the shaft's ~26 Hz quiver
    ring += [(ring_hz * h, t60 / h ** 0.7, 0.5 / h) for h in (2, 3, 4, 5, 6, 8)]
    body = [(f * (1 + 0.06 * (fx.rand("tune") - 0.5)), d, g) for f, d, g in
            ((139, 0.08, 0.8), (154, 0.09, 1.0), (187, 0.07, 0.7), (206, 0.07, 0.8), (223, 0.06, 0.7),
             (241, 0.05, 0.6), (500, 0.03, 0.3), (800, 0.02, 0.2))]
    crack = 0.7 + 0.4 * fx.power
    return [Noise(0.0, 0.03, [(0, 1500), (1, 1200)], "band", 0.4, amp=decay_curve(6), attack=0.0005, release=0.005,
                  gain=0.9 * crack),
            Noise(0.0, 0.012, [(0, 4000), (1, 4000)], "high", 0.6, amp=decay_curve(5), attack=0.0003, release=0.003,
                  gain=0.6 * crack),
            Modal(0.0, 0.25, [(round(f, 1), d, g) for f, d, g in body], [(0.0, 1.0, 0.002)], hardness=3500, click=0.3),
            Modal(0.0, round(t60 * 1.3, 3), [(round(f, 1), round(d, 4), round(g, 4)) for f, d, g in ring],
                  [(0.0, 1.0, 0.003)], hardness=4000, gain=1.1)]



def arrow_in_flesh(fx: Fx, cross: bool = False) -> list:
    """An arrow into a body or a soft target, from recordings: a dull thud near 195 Hz (-20 dB in ~50 ms),
    a short wet tear near 2.8 kHz, a pierce tick, and the shaft's quiver, damped by the flesh."""
    tune = (1.3 if cross else 1.0) * (1 + 0.06 * (fx.rand("tune") - 0.5))
    thud = 195 * (0.9 + 0.2 * fx.g.base("thud"))
    body = [(round(thud, 1), 0.18, 1.0), (round(thud * 2, 1), 0.06, 0.3), (round(thud * 0.62, 1), 0.1, 0.4)]
    return [Modal(0.0, 0.4, body, [(0.0, 1.0, 0.004)], hardness=1500, click=0.0),
            Noise(0.0, 0.04, [(0, 2800), (1, 2200)], "band", 1.2, amp=decay_curve(4), attack=0.001, release=0.01,
                  wobble=(60.0, 0.7), gain=0.45 * (0.7 + 0.6 * fx.power)),
            Noise(0.0, 0.003, [(0, 4000), (1, 4000)], "high", 0.7, amp=decay_curve(4), attack=0.0002, release=0.001,
                  gain=0.3),
            Modal(0.0, 0.5, [(round(158 * tune, 1), 0.25, 1.0), (round(158 * tune + 26, 1), 0.25, 0.8),
                             (round(316 * tune, 1), 0.12, 0.3)], [(0.005, 1.0, 0.003)], hardness=3000, gain=0.25)]


def arrow_on_stone(fx: Fx, cross: bool = False) -> list:
    """An arrow glancing off stone, from a recording of arrows clattering: a hard crack, the head and shaft
    ringing short and high (1.3-10 kHz, ~40 ms), and the arrow falling and bouncing (the next contacts
    ~0.39 s and ~0.23 s apart, -14 and -18 dB); sometimes the shaft snaps."""
    tune = (1.15 if cross else 1.0) * (0.9 + 0.2 * fx.g.base("head"))
    gap = 0.39 * (0.75 + 0.5 * fx.rand("gap"))
    hits = [(0.0, 1.0, 0.0005), (round(gap, 4), 0.35, 0.0005), (round(gap * 1.59, 4), 0.22, 0.0005)]
    if fx.rand("more") < 0.6:
        hits.append((round(gap * 1.95, 4), 0.1, 0.0005))
    ring = [(1265, 0.04, 0.25), (1781, 0.05, 0.6), (3351, 0.04, 0.4), (5460, 0.05, 1.0), (6421, 0.04, 0.9),
            (9281, 0.03, 0.45), (10400, 0.03, 0.3)]
    stone = [(round(f * (0.8 + 0.4 * fx.g.base(f"s{i}")), 1), d, g) for i, (f, d, g) in
             enumerate(((1100, 0.2, 0.6), (2000, 0.07, 0.9), (3100, 0.16, 1.0), (5100, 0.17, 0.4)))]
    out = [Noise(0.0, 0.003, [(0, 3000), (1, 3000)], "high", 0.7, amp=decay_curve(4), attack=0.0002, release=0.001),
           Modal(0.0, round(hits[-1][0] + 0.2, 3), [(round(f * tune * (0.95 + 0.1 * fx.rand(f"r{i}")), 1), d, g)
                                                     for i, (f, d, g) in enumerate(ring)], hits, hardness=14000,
                 click=0.3),
           Modal(0.0, 0.4, stone, [(0.0, 1.0, 0.0005)], hardness=12000, click=0.3, gain=0.25),
           Scatter(0.002, 0.05, [(0, 600), (1, 0)], "pop", (1500, 7000), (0.0003, 0.0012), (0.2, 1.0), 0.2)]
    if fx.rand("snap") < 0.35:   # the shaft breaks
        out.append(fx.strike("wood", size=0.1, hits=[(0.004, 0.8, 0.001)], gain=0.35, prefix="snap"))
    return out

# --- blades -----------------------------------------------------------------------------------------------------------
#
# Modelled on recordings of sword clashes and swings. A clash is short and bright: a contact, the
# blades grinding along each other for 30-80 ms, often a second touch ~30 or ~170 ms later, and a
# ring of dense modes (strongest near 6 kHz, little below 1.5 kHz) falling 40 dB in 0.2-0.6 s.
# A swing lasts ~0.25 s: mostly the slow pressure push of the passing blade (below 300 Hz), with
# a swish centred near 1.4 kHz rising ~30 dB in ~55 ms and falling in ~170 ms.

BLADE_RING = [(500, -34), (1000, -27), (1600, -18), (2500, -12.5), (3150, -8), (4000, -8.6), (5000, -6),
              (6300, -4.4), (8000, -8), (10000, -11), (12500, -23), (16000, -27)]   # measured, dB per 1/3 octave
BLADE_MODES = [(500, -32.4), (1000, -25.4), (1600, -16.4), (2500, -24.0), (3150, -18.1), (4000, -14.8),
               (5000, -6.5), (6300, -1.8), (8000, -4.6), (10000, -8.8), (12500, -12.5), (16000, -16.5)]
# BLADE_MODES: each mode's level, found by rendering and comparing until the ring matched BLADE_RING


def _db_at(table: list, f: float) -> float:
    return float(np.interp(np.log(f), np.log([c for c, _ in table]), [d for _, d in table]))


def blade_modes(fx: Fx, prefix: str, shift: float = 1.0, ring: float = 1.0, n: int = 60) -> list:
    """A blade's ring: dense modes spread log-evenly over 1.2-12.5 kHz (fixed per species), struck
    differently every take, decaying in 0.2-0.6 s, plus three longer modes lower down."""
    out = []
    for i in range(n):
        f = 1200 * (12500 / 1200) ** ((i + fx.g.base(f"{prefix}f{i}")) / n)
        g = 10 ** (_db_at(BLADE_MODES, f) / 20) * (0.4 + 1.2 * fx.rand(f"{prefix}s{i}"))
        d = (0.2 + 0.4 * fx.g.base(f"{prefix}d{i}")) * (f / 4000) ** -0.1
        out.append((round(f * shift, 1), round(d * ring, 4), round(g, 4)))
    for j in range(3):
        f = 600 + 3400 * fx.g.base(f"{prefix}L{j}")
        out.append((round(f * shift, 1), round((0.6 + 0.8 * fx.g.base(f"{prefix}Ld{j}")) * ring, 4),
                    round(10 ** (_db_at(BLADE_RING, f) / 20), 4)))
    return out


def blade_clash(fx: Fx, shift: float, ring: float, slide: tuple, grind: float, thud: float) -> list:
    """Two blades meet: contact, grinding slide, maybe a second touch, both ringing."""
    sl = slide[0] + (slide[1] - slide[0]) * fx.rand("slide")
    lag = 0.001 + 0.003 * fx.rand("lag")
    hits = [(0.0, 1.0, 0.0006)]
    u = fx.rand("rehit")
    if u < 0.35:
        hits.append((round(0.025 + 0.015 * fx.rand("rt"), 4), 0.6, 0.0006))
    elif u < 0.7:
        hits.append((round(0.16 + 0.03 * fx.rand("rt"), 4), 0.45, 0.0006))
    dur = round(min(2.2 * ring + 0.1, 3.0), 3)
    foe = shift * (0.85 + 0.3 * fx.rand("foe"))
    scrape = (0.002, round(sl, 4), grind, 0.0)
    out = [Modal(0.0, dur, blade_modes(fx, "a", shift, ring), hits, scrape, 16000, 0.05),
           Modal(round(lag, 4), dur, blade_modes(fx, "b", foe, ring), hits, scrape, 16000, 0.05, gain=0.8),
           Noise(0.0, 0.006, [(0, 4000), (1, 4000)], "high", 0.7, amp=decay_curve(4), attack=0.0002, release=0.002,
                 gain=0.6),
           Noise(0.0, round(sl + 0.03, 3), [(0, 7000), (1, 5500)], "band", 1.0, amp=[(0, 1), (0.6, 0.6), (1, 0)],
                 attack=0.001, release=0.02, gain=0.25 * grind)]
    if thud:   # heavy blades: the hands and arms take a blow
        out.append(Noise(0.0, 0.08, [(0, 420), (1, 200)], "low", 1.0, amp=decay_curve(5), attack=0.001, release=0.02,
                         gain=thud))
    return out


def blade_swing(fx: Fx, rise: float, fall: float, centre: float, whistle: float, vwoom: float,
                vwoom_hz: float = 120.0) -> list:
    """The swish (dB-linear rise from -30 dB, darker as it slows), the blade's pressure push at the peak,
    a fuller's whistle when fast, a low 'vwoom' when heavy."""
    rise *= 0.85 + 0.3 * fx.rand("rise")
    fall *= 0.85 + 0.3 * fx.rand("fall")
    lead = 0.04
    dur = round(lead + rise + fall, 3)
    p = (lead + rise) / dur
    amp = [(0.0, 0.01), (round(lead / dur, 4), 0.0316), (round(p, 4), 1.0), (round(p + 0.45 * (1 - p), 4), 0.1),
           (1.0, 0.0251)]
    freq = [(0, centre * 0.65), (round(p, 4), centre * 1.3), (1, centre * 0.5)]
    out = [Noise(0.0, dur, freq, "low", 0.8, amp=amp, attack=0.0, release=0.01, wobble=(40.0, 0.25), gain=0.55),
           Noise(0.0, dur, [(t, f * 4) for t, f in freq], "high", 0.7, amp=[(t, round(a ** 1.6, 5)) for t, a in amp],
                 attack=0.0, release=0.01, gain=0.04),
           Modal(round(lead + rise - 0.03, 4), 0.25, [(38, 0.08, 1.0), (75, 0.05, 0.35)], [(0.0, 1.0, 0.03)],
                 hardness=200, click=0.0)]
    if whistle:
        out.append(Noise(0.0, dur, [(0, 700), (round(p, 4), 1900), (1, 1000)], "band", 14.0,
                         amp=[(t, round(a ** 1.3, 5)) for t, a in amp], attack=0.0, release=0.01, gain=whistle))
    if vwoom:
        k = vwoom_hz / 120
        out.append(Noise(0.0, dur, [(0, 105 * k), (round(p, 4), 135 * k), (1, 115 * k)], "band", 9.0, amp=amp,
                         attack=0.0, release=0.02, gain=vwoom))
    return out


# Hits, from recordings of blades striking each target (weight: heavier blade, drama: cinematic):
#   wood    a dry knock: the plank's few low modes (~470, ~1080, ~1550 Hz), gone in ~0.1 s; the blade bites in
#   stone   a hard bright crack, the blade ringing only briefly, grit flying off for ~60 ms
#   armour  a clang: the plate's dense modes (650 Hz-6.5 kHz, strongest 2.5-5 kHz), the body's thud beneath
#   flesh   the body's thump (~90 Hz, often the loudest part), a wet jittering slice above 2 kHz, wet pops

def _crack(gain: float = 1.0, hz: float = 2500.0, dur: float = 0.004) -> Noise:
    return Noise(0.0, dur, [(0, hz), (1, hz)], "high", 0.7, amp=decay_curve(4), attack=0.0002, release=0.001,
                 gain=gain)


def _near(fx: Fx, name: str, spread: float = 0.12) -> float:
    return 1 + spread * (2 * fx.g.base(name) - 1)


def blade_hit(fx: Fx, target: str, shift: float, ring: float, weight: float, drama: float) -> list:
    """A blade striking wood, stone, armour or flesh."""
    if target == "wood":
        k = 1 - 0.25 * weight
        body = [(470 * _near(fx, "w0"), 0.15, 1.0), (1080 * _near(fx, "w1"), 0.2, 0.55),
                (1550 * _near(fx, "w2"), 0.08, 0.5), (2100 * _near(fx, "w3"), 0.12, 0.3),
                (720 * _near(fx, "w4"), 0.1, 0.4), (3900 * _near(fx, "w5"), 0.1, 0.25)]
        body = [(round(f * k, 1), round(d * (1 + 0.5 * weight), 4), g) for f, d, g in body]
        return [_crack(1.0 + 0.3 * drama),
                Modal(0.0, 0.5, body, [(0.0, 1.0, 0.0008)], hardness=7000, click=0.25),
                Noise(0.0, round(0.05 + 0.04 * weight, 3), [(0, 300), (1, 150)], "low", 1.0, amp=decay_curve(5),
                      attack=0.001, release=0.01, gain=0.35 + 0.5 * weight),
                Modal(0.0, 1.0, blade_modes(fx, "a", shift, (0.45 + 0.8 * drama) * ring), [(0.0, 1.0, 0.0006)],
                      hardness=16000, click=0.0, gain=0.3 + 0.25 * drama)]
    if target == "stone":
        stone = [(round(f * _near(fx, f"s{i}", 0.2), 1), d, g) for i, (f, d, g) in
                 enumerate(((1100, 0.2, 0.6), (2000, 0.07, 0.9), (3100, 0.16, 1.0), (4100, 0.03, 0.4),
                            (5100, 0.17, 0.4)))]
        return [_crack(1.0, 3000.0, 0.003),
                Modal(0.0, 0.4, stone, [(0.0, 1.0, 0.0005)], hardness=14000, click=0.5, gain=0.7),
                Modal(0.0, 1.2, blade_modes(fx, "a", shift, (0.3 + 0.9 * drama) * ring), [(0.0, 1.0, 0.0005)],
                      hardness=16000, click=0.0, gain=0.25 + 0.4 * drama),
                Scatter(0.002, round(0.07 + 0.06 * weight, 3), [(0, 900 + 600 * weight), (1, 0)], "pop",
                        (1500, 7000), (0.0003, 0.0015), (0.2, 1.0), 0.25 + 0.3 * weight),
                Noise(0.0, 0.04, [(0, 600), (1, 300)], "low", 1.0, amp=decay_curve(6), attack=0.001, release=0.01,
                      gain=0.35 + 0.5 * weight)]
    if target == "iron":   # plate armour
        plate = []
        for i in range(30):
            f = 650 * (6500 / 650) ** ((i + fx.g.base(f"p{i}")) / 30)
            lvl = np.interp(np.log(f), np.log([650, 1300, 2500, 5000, 6500]), [-10, -6, -2, 0, -6])
            g = 10 ** (lvl / 20) * (0.4 + 1.2 * fx.rand(f"ps{i}"))
            d = (0.15 + 0.35 * fx.g.base(f"pd{i}")) * (f / 2500) ** -0.4
            plate.append((round(f * (1 - 0.2 * weight), 1), round(d * (1 + 1.5 * drama), 4), round(float(g), 4)))
        return [_crack(0.8, 3000.0),
                Modal(0.0, 1.6, plate, [(0.0, 1.0, 0.0006)], hardness=14000, click=0.1),
                Modal(0.0, 1.2, blade_modes(fx, "a", shift, (0.6 + 0.8 * drama) * ring), [(0.0, 1.0, 0.0006)],
                      hardness=16000, click=0.0, gain=0.45),
                Noise(0.0, round(0.06 + 0.04 * weight, 3), [(0, 260), (1, 130)], "low", 1.0, amp=decay_curve(5),
                      attack=0.001, release=0.01, gain=0.25 + 0.6 * weight)]
    # flesh
    sl = 0.06 + 0.09 * fx.rand("slice")
    out = [Modal(0.0, 0.5, [(round(90 * _near(fx, "th"), 1), round(0.2 + 0.1 * weight, 4), 1.0),
                            (round(175 * _near(fx, "th2"), 1), 0.07, 0.35)],
                 [(0.0, 1.0, 0.012)], hardness=400, click=0.0, gain=0.6 + 0.4 * weight),
           Noise(0.0, round(sl, 3), [(0, 5000), (1, 3500)], "high", 0.7, amp=[(0, 1), (0.3, 0.6), (1, 0.05)],
                 attack=0.002, release=0.02, wobble=(70.0, 0.8), gain=0.75 + 0.25 * drama),
           Noise(0.003, round(sl + 0.03, 3), [(0, 1100), (1, 750)], "band", 1.5, amp=decay_curve(3), attack=0.004,
                 release=0.02, wobble=(35.0, 0.9), gain=0.3),
           Scatter(0.0, round(sl, 3), [(0, 220), (1, 40)], "pop", (300, 1800), (0.001, 0.004), (0.3, 1.0), 0.3)]
    if weight:   # bone
        out.append(Scatter(0.005, 0.05, [(0, 500), (1, 100)], "pop", (150, 900), (0.002, 0.006), (0.4, 1.0),
                           0.5 * weight))
    if drama:    # the edge's bite
        out.append(Noise(0.0, 0.02, [(0, 7000), (1, 5000)], "high", 0.7, amp=decay_curve(5), attack=0.0005,
                         release=0.005, gain=0.5 * drama))
    return out


def blade_draw(fx: Fx, shift: float, ring: float, dur: float) -> list:
    """Out of the scabbard, from recordings: a scrape swelling ~25 dB in its first 70-170 ms and held,
    broad and bright (2.5-6 kHz), sometimes a tick as the guard leaves the throat; then the blade, freed,
    rings on (-20 dB after ~0.3 s, -35 dB after 0.5-1.2 s), strongest 1-4 kHz."""
    hits = [(round(dur, 4), 0.6, 0.001)]
    if fx.rand("throat") < 0.5:
        hits.insert(0, (0.0, 0.5, 0.0006))
    amp = [(0.0, 0.056), (0.15, 0.3), (0.3, 0.8), (0.4, 1.0), (0.85, 0.9), (1.0, 0.7)]
    return [Noise(0.0, round(dur, 3), [(0, 2600), (0.7, 3600), (1, 4200)], "band", 0.9, amp=amp, attack=0.01,
                  release=0.015, wobble=(14.0, 0.35)),
            Noise(0.0, round(dur, 3), [(0, 6000), (1, 7500)], "high", 0.7, amp=amp, attack=0.01, release=0.015,
                  gain=0.3),
            Modal(0.0, round(dur + 2.4 * ring, 3), blade_modes(fx, "a", shift, 2.2 * ring), hits,
                  (0.0, round(dur, 4), 0.7, 0.0), 3500, 0.0, 0.8)]


def blade_drop(fx: Fx, shift: float, ring: float) -> list:
    """Dropped on stone, from recordings: the hilt lands, 30-45 ms later the blade slaps down (the loudest),
    then rattles against the floor for ~0.15 s as it rings, and bounces once more ~0.27 s on, smaller; under it
    the floor's own knock and a heavy thud."""
    slap = round(0.03 + 0.015 * fx.rand("slap"), 4)
    bounce = round(slap + 0.24 + 0.06 * fx.rand("bounce"), 4)

    def rattle(t0: float, n: int, gain: float, name: str) -> list:   # the ringing blade chattering on the floor
        out, t = [], t0
        for k in range(n):
            t += 0.009 * 1.18 ** k * (0.7 + 0.6 * fx.rand(f"{name}{k}"))
            out.append((round(t, 4), round(gain * 0.8 ** k * (0.6 + 0.8 * fx.rand(f"{name}g{k}")), 4), 0.0008))
        return out

    main = [(0.0, 0.55, 0.001), (slap, 1.0, 0.0008), (bounce, 0.45, 0.0008)]
    hits = main + rattle(slap, 12, 0.8, "r") + rattle(bounce, 5, 0.35, "b")
    out = [Modal(0.0, round(bounce + 2.0 * ring, 3), blade_modes(fx, "a", shift, 1.3 * ring), sorted(hits),
                 hardness=9000, click=0.1),
           fx.strike("stone", size=0.75, hits=[(t, g, 0.002) for t, g, _ in main], gain=0.5, prefix="g", click=0.2)]
    out += [Noise(t, 0.09, [(0, 320), (1, 120)], "low", 1.0, amp=decay_curve(5), attack=0.001, release=0.015,
                  gain=1.0 * g) for t, g, _ in main]
    return out



# --- blunt weapons ----------------------------------------------------------------------------------------------------
#
# From recordings of clubs, hammers, pipes and rocks striking each target, and of heavy swings. A blunt swing is a
# dark "whoom": most energy below 1 kHz (centroid 0.4-1 kHz), often a low tone near 150-270 Hz. A hit is the
# target's body more than the weapon: flesh a deep thump (110-370 Hz) under a skin slap; wood a short knock
# (main mode ~350 Hz, gone in 30-170 ms); metal a clang lower and longer than a blade's (0.5-7 kHz, strongest
# 1.6-4 kHz, 40 dB in 0.2-0.6 s); stone a broad crack with grit.

BLUNT_HEADS = {   # the weapon head's own modes (Hz, T60 s, gain), heard faintly under the target
    "wood": [(350, 0.25, 1.0), (700, 0.09, 0.5), (1430, 0.08, 0.4), (1800, 0.06, 0.4), (2250, 0.06, 0.3)],
    "iron": [(820, 0.3, 0.6), (1220, 0.2, 1.0), (1650, 0.25, 0.6), (2860, 0.3, 0.8), (3260, 0.5, 0.5),
             (4270, 0.4, 0.4)],
    "stone": [(1100, 0.07, 0.8), (1660, 0.16, 0.6), (4830, 0.3, 0.5), (5860, 0.2, 0.4)],
}
BLUNT_WOOD = [(351, 0.2, 1.0), (656, 0.12, 0.6), (937, 0.07, 0.5), (1804, 0.07, 0.6), (2226, 0.06, 0.5),
              (2343, 0.06, 0.4), (2718, 0.06, 0.25), (3351, 0.05, 0.15)]   # a plank knocked by a blunt head
BLUNT_STONE = [(351, 0.25, 1.0), (520, 0.15, 0.8), (1195, 0.3, 1.0), (1453, 0.25, 0.9), (2039, 0.3, 0.7),
               (4289, 0.2, 0.4), (5203, 0.15, 0.3)]


def _jittered(fx: Fx, modes: list, prefix: str, spread: float = 0.1, scale: float = 1.0, ring: float = 1.0) -> list:
    return [(round(f * scale * (1 + spread * (2 * fx.g.base(f"{prefix}{i}") - 1)), 1), round(d * ring, 4), g)
            for i, (f, d, g) in enumerate(modes)]


def blunt_hit(fx: Fx, head: str, target: str, weight: float, drama: float) -> list:
    """A blunt head striking flesh, wood, metal (armour, a shield) or stone."""
    heavy = 2 ** (-0.6 * weight)                         # bigger heads, lower bodies
    hard = {"wood": 4000, "iron": 8000, "stone": 7000}[head]
    mass = round((0.03 if target == "wood" else 0.05) + 0.06 * weight, 3)
    out = [Modal(0.0, 0.8, _jittered(fx, BLUNT_HEADS[head], "h", scale=heavy, ring=0.5 + 0.5 * drama),
                 [(0.0, 1.0, 0.002)], hardness=hard, click=0.0, gain={"metal": 0.35, "wood": 0.12}.get(target, 0.25)),
           Noise(0.0, mass, [(0, 260 * heavy), (1, 110 * heavy)], "low", 1.0, amp=decay_curve(5), attack=0.001,
                 release=0.015, gain=(0.3 if target == "metal" else 0.6) + 0.6 * weight)]   # the mass behind it
    if target == "flesh":
        body = 150 * (0.8 + 0.4 * fx.g.base("body")) * heavy
        out += [Modal(0.0, 0.7, [(round(body, 1), 0.3 + 0.1 * weight, 1.0), (round(body * 2, 1), 0.15, 0.5)],
                      [(0.0, 1.0, 0.006)], hardness=900, click=0.0),
                Noise(0.0, 0.025, [(0, 2200), (1, 1600)], "band", 0.8, amp=decay_curve(4), attack=0.0008,
                      release=0.008, gain=0.75 + 0.3 * drama)]   # the skin's slap
        if weight:
            out.append(Scatter(0.004, 0.05, [(0, 450), (1, 80)], "pop", (150, 900), (0.002, 0.006), (0.4, 1.0),
                               0.45 * weight))   # bone
    elif target == "wood":
        out += [Modal(0.0, 0.5, _jittered(fx, BLUNT_WOOD, "w", scale=0.85 + 0.3 * fx.g.base("plank")),
                      [(0.0, 1.0, 0.0015)], hardness=6000, click=0.2),
                Noise(0.0, 0.006, [(0, 2000), (1, 2000)], "band", 0.7, amp=decay_curve(4), attack=0.0003,
                      release=0.002, gain=0.4)]
    elif target == "metal":
        plate = []
        for i in range(30):
            f = 450 * (10000 / 450) ** ((i + fx.g.base(f"p{i}")) / 30)
            lvl = np.interp(np.log(f), np.log([450, 900, 1600, 3200, 5000, 7000, 10000]), [-12, -9, -2, 0, -2, -4, -8])
            g = 10 ** (lvl / 20) * (0.4 + 1.2 * fx.rand(f"ps{i}"))
            d = (0.25 + 0.6 * fx.g.base(f"pd{i}")) * (f / 2000) ** -0.3
            plate.append((round(f * heavy ** 0.5, 1), round(d * (1 + 1.5 * drama), 4), round(float(g), 4)))
        out += [Modal(0.0, 2.0, plate, [(0.0, 1.0, 0.0012)], hardness=hard * 1.5, click=0.1),
                _crack(0.8, 3000.0)]
    else:   # stone
        out += [_crack(1.0, 3500.0, 0.005),
                Modal(0.0, 0.6, _jittered(fx, BLUNT_STONE, "s", 0.15), [(0.0, 1.0, 0.0012)], hardness=9000, click=0.6,
                      gain=0.7),
                Scatter(0.002, round(0.08 + 0.08 * weight, 3), [(0, 900 + 900 * weight), (1, 0)], "pop", (1500, 10000),
                        (0.0004, 0.002), (0.2, 1.0), 0.4 + 0.3 * weight)]
    return out


def blunt_drop(fx: Fx, head: str, weight: float) -> list:
    """Dropped on stone: the head lands heavily, the haft slaps down 50-100 ms later, a small bounce."""
    haft = round(0.05 + 0.05 * fx.rand("haft"), 4)
    bounce = round(haft + 0.12 + 0.06 * fx.rand("bounce"), 4)
    hits = [(0.0, 1.0, 0.002), (haft, 0.45, 0.0015), (bounce, 0.2, 0.002)]
    heavy = 2 ** (-0.6 * weight)
    return [Modal(0.0, 1.2, _jittered(fx, BLUNT_HEADS[head], "h", scale=heavy, ring=0.6), hits,
                  hardness={"wood": 4000, "iron": 8000, "stone": 7000}[head], click=0.2),
            fx.strike("wood", size=0.4, hits=[hits[1]], gain=0.35, prefix="haft"),
            fx.strike("stone", size=0.75, hits=[(t, g, 0.002) for t, g, _ in hits], gain=0.5, prefix="g", click=0.2),
            *[Noise(t, 0.1, [(0, 260 * heavy), (1, 100 * heavy)], "low", 1.0, amp=decay_curve(5), attack=0.001,
                    release=0.015, gain=g * (0.8 + 0.6 * weight)) for t, g, _ in hits]]


# --- shields ----------------------------------------------------------------------------------------------------------
#
# From recordings of swords, clubs and bashes on shields. A sword on a wooden shield is fast and mid-bright: no lows
# to speak of (-20 dB below 500 Hz), the panel's modes near 0.85-0.95, 1.6-1.7, 2.2 and 3.3-3.8 kHz ringing
# 0.13-0.4 s with the blade's own ring, 40 dB down in 130-200 ms. A club on a shield also moves the whole panel:
# a low body near 120-400 Hz. A metal shield rings denser and longer (0.23-3.4 kHz, 40 dB in ~0.3 s).

SHIELD_PANELS = {
    "wood": [(420, 0.35, 0.5), (515, 0.45, 0.3), (843, 0.2, 0.9), (960, 0.25, 0.8), (1593, 0.27, 0.9),
             (1700, 0.25, 1.0), (2200, 0.25, 0.6), (3300, 0.25, 0.5), (3700, 0.3, 0.45), (4400, 0.16, 0.25),
             (5580, 0.17, 0.35), (6490, 0.2, 0.3), (8300, 0.15, 0.25)],
    "metal": [(234, 0.43, 1.0), (585, 0.48, 0.67), (679, 0.3, 0.66), (796, 0.33, 0.9), (1007, 0.53, 0.6),
              (1125, 0.17, 0.7), (1851, 0.32, 0.4), (2132, 0.5, 0.55), (2320, 0.28, 0.4), (3398, 0.29, 0.43),
              (4150, 0.25, 0.3), (5200, 0.2, 0.3), (6400, 0.15, 0.3), (7500, 0.15, 0.25), (9000, 0.12, 0.2)],
}


def shield_hit(fx: Fx, style: str, by: str, weight: float, drama: float) -> list:
    """A shield taking a blade, a blunt weapon or an arrow, or bashing into a body."""
    big = 2 ** (-0.5 * weight)                          # bigger shields, lower panels
    ring = (1 + 1.2 * drama) * {"bash": 0.4, "blunt": 1.3}.get(by, 1.0)
    panel = _jittered(fx, SHIELD_PANELS[style], "sp", 0.08, big, ring)
    if by == "blade":
        panel = [(f, d, g * (0.25 if f < 600 else 1.0)) for f, d, g in panel]   # a sharp edge barely moves the panel
    out = [Modal(0.0, 1.6, panel, [(0.0, 1.0, 0.0008 if by in ("blade", "arrow") else 0.003)],
                 hardness=12000 if by in ("blade", "arrow") else 9000, click=0.15)]
    if by == "blade":
        out += [_crack(0.9, 3000.0), Modal(0.0, 1.2, blade_modes(fx, "a", 1.0, 0.6 + 0.6 * drama),
                                           [(0.0, 1.0, 0.0006)], hardness=16000, click=0.0, gain=0.5)]
    elif by == "arrow":
        out += [_crack(0.6, 2500.0), *arrow_in_wood(fx)[3:]]   # the shaft left quivering
    else:   # a blunt blow or a bash moves the whole shield: the panel's body and the mass behind it
        body = 150 * (0.8 + 0.4 * fx.g.base("panel")) * big
        out += [_crack(0.7 if by == "blunt" else 0.2, 4000.0),
                Modal(0.0, 0.5, [(round(body, 1), 0.12, 1.0), (round(body * 2.3, 1), 0.08, 0.5)], [(0.0, 1.0, 0.004)],
                      hardness=1500, click=0.0, gain=0.8 + 0.3 * weight),
                Noise(0.0, round(0.06 + 0.05 * weight, 3), [(0, 280), (1, 110)], "low", 1.0, amp=decay_curve(5),
                      attack=0.001, release=0.015, gain=0.6 + 0.5 * weight)]
        if by == "bash":   # straps, rim and boss rattle against each other
            out.append(Scatter(0.01, 0.12, [(0, 160), (1, 20)], "pop", (900, 5000), (0.001, 0.004), (0.2, 1.0),
                               0.35))
    return out


# --- gear in motion ---------------------------------------------------------------------------------------------------
#
# From recordings of chainmail, plate armour and leather moving. Chainmail is a swell of tiny rings jingling, strongest
# at 8-12 kHz; plate armour a few separate clanks (1.6-8 kHz, strongest 4-6 kHz) over rubbing; leather a creak of
# dense stick-slip (70-100 per second) low down (strongest 250-500 Hz, -20 dB above 2.5 kHz) over a soft rustle.

def gear_move(fx: Fx, style: str, dur: float, energy: float) -> list:
    """One movement (a step, a turn, a swing of the arms) of a body wearing this gear."""
    swell = bell_curve(0.35 + 0.2 * fx.rand("peak"), 1.5)
    if style == "chainmail":
        return [Scatter(0.0, round(dur, 3), [(t, round(a * 1800 * energy, 1)) for t, a in swell], "ping", (4000, 12000),
                        (0.0005, 0.003), (0.2, 1.0)),
                Noise(0.0, round(dur, 3), [(0, 7000), (1, 9000)], "band", 0.6, amp=swell, attack=0.02, release=0.05,
                      wobble=(18.0, 0.6), gain=0.3)]
    if style == "plate":
        n = 2 + int(3 * energy * fx.rand("clanks") + 0.5)
        hits = sorted((round(dur * (0.15 + 0.7 * fx.rand(f"c{k}")), 4), round(0.4 + 0.6 * fx.rand(f"cg{k}"), 3), 0.0008)
                      for k in range(n))
        plate = []
        for i in range(24):
            f = 1500 * (11000 / 1500) ** ((i + fx.g.base(f"pl{i}")) / 24)
            lvl = np.interp(np.log(f), np.log([1500, 3000, 5000, 8000, 11000]), [-8, -3, 0, -2, -8])
            plate.append((round(f, 1), round(0.06 + 0.1 * fx.g.base(f"pld{i}"), 4), round(10 ** (lvl / 20), 4)))
        return [Modal(0.0, round(dur + 0.3, 3), plate, hits, (0.0, round(dur, 3), 0.25, 0.0), 12000, 0.2),
                Noise(0.0, round(dur, 3), [(0, 900), (1, 700)], "band", 0.7, amp=swell, attack=0.02, release=0.05,
                      wobble=(12.0, 0.5), gain=0.2)]
    # leather: a low creak and a rustle
    hits = stick_slip(fx, dur, 0.012, 0.35, 0.8)
    body = Modal(0.0, round(dur + 0.1, 3), wood_modes(fx, 0.15, 0.02, 8), hits, hardness=1600, click=0.02)
    return [body, Noise(0.0, round(dur, 3), [(0, 600), (1, 750)], "low", 0.9, amp=swell, attack=0.02, release=0.05,
                        wobble=(20.0, 0.7), gain=0.35)]


# --- bodies -----------------------------------------------------------------------------------------------------------
#
# From recordings of body falls: not one thud but 3-6 low impacts over 0.2-0.5 s (knees, hips, the torso - the
# loudest - then an arm or the head, 60-150 ms apart, 4-14 dB under the torso), each a thump near 110-180 Hz;
# strongest 250-500 Hz, ~-14 dB at 2.5 kHz, ~-20 dB at 8 kHz; cloth rustling throughout.

def body_fall(fx: Fx, floor: str, weight: float, dead: bool = False) -> list:
    """A body collapsing (knees, hips, torso, arm) or dropped dead weight (torso, a small bounce)."""
    parts = [(0.0, 1.0), (0.09, 0.3)] if dead else [(0.0, 0.5), (0.1, 0.7), (0.21, 1.0), (0.33, 0.3), (0.43, 0.18)]
    slow = 1 + 0.4 * weight
    hits = [(round(t * slow * (0.85 + 0.3 * fx.rand(f"t{k}")), 4), round(g * (0.8 + 0.4 * fx.rand(f"g{k}")), 3))
            for k, (t, g) in enumerate(parts)]
    thump = 145 * (0.75 + 0.5 * fx.g.base("frame")) * 2 ** (-0.5 * weight)
    out = [Modal(0.0, round(hits[-1][0] + 0.5, 3), [(round(thump, 1), 0.14, 1.0), (round(thump * 1.9, 1), 0.08, 0.5),
                                                    (round(thump * 3.1, 1), 0.05, 0.25)],
                 [(t, g, 0.008) for t, g in hits], hardness=900, click=0.0)]
    out += [Noise(t, 0.08, [(0, 420), (1, 200)], "low", 0.9, amp=decay_curve(5), attack=0.002, release=0.015,
                  gain=0.7 * g) for t, g in hits]
    end = hits[-1][0] + 0.15
    out.append(Noise(0.0, round(end, 3), [(0, 1500), (1, 1100)], "band", 0.8, amp=bell_curve(0.4, 1.2), attack=0.02,
                     wobble=(25.0, 0.7), gain=0.18))   # cloth
    if floor == "wood":
        out.append(fx.strike("wood", size=0.8, hits=[(t, g, 0.006) for t, g in hits], hardness=1500, gain=0.4,
                             prefix="floor", click=0.0))
    elif floor == "stone":
        out.append(Noise(0.0, round(end, 3), [(0, 2500), (1, 2000)], "band", 0.9, amp=decay_curve(3), attack=0.002,
                         gain=0.07))
    else:   # dirt: a little grit and dust
        out.append(Scatter(0.0, round(end, 3), [(0, 250), (1, 0)], "pop", (600, 4000), (0.0008, 0.003), (0.2, 1.0),
                           0.15))
    return out


# --- doors and chests -------------------------------------------------------------------------------------------------
#
# From recordings of doors, chests, locks and knocks. A hinge squeaks: stick-slip at a steady rate (a harmonic tone,
# 600-1500 Hz) gliding as the swing speeds up and slows. A door slamming is low (strongest at 250 Hz; panel modes
# 250-870 Hz ringing 0.25-0.4 s; -40 dB in 0.1-0.5 s). A locked door rattles 2-5 times, 60-130 ms apart, bright
# (strongest 1.6-4 kHz). A key turns the tumblers with clicks 50-130 ms apart and the bolt last, loudest.
# Knuckles on a door are dull (strongest 250-1000 Hz, modes 140-1050 Hz, -20 dB in 25-80 ms), 0.15-0.25 s apart.

PANELS = {   # (Hz, T60 s, gain): a door, an iron gate, a chest's box and lid
    "door": [(118, 0.25, 0.8), (257, 0.27, 1.0), (421, 0.38, 1.0), (632, 0.36, 0.6), (867, 0.26, 0.5),
             (2100, 0.3, 0.12)],
    "gate": [(180, 0.6, 0.6), (420, 0.9, 1.0), (760, 0.8, 0.8), (1250, 0.7, 0.6), (2100, 0.5, 0.4), (3400, 0.4, 0.3)],
    "chest": [(240, 0.15, 0.7), (398, 0.25, 1.0), (585, 0.12, 0.8), (750, 0.11, 0.7), (1007, 0.08, 0.5),
              (1523, 0.08, 0.3)],
}


def squeak(fx: Fx, start: float, dur: float, lo: float, hi: float, gain: float = 1.0, name: str = "sq") -> Syllable:
    """A hinge: stick-slip at a steady rate, its pitch rising as the swing speeds up and sinking as it slows."""
    peak = 0.3 + 0.4 * fx.rand(name + "p")
    # stick-slip is not steady: the squeak catches and lets go, its loudness stuttering
    amp = [(0, 0.2)] + [(round(i / 8, 3), round(0.25 + 0.75 * fx.rand(f"{name}a{i}") * (1 - abs(i / 8 - peak)), 3))
                        for i in range(1, 8)] + [(1, 0.2)]
    return Syllable(round(start, 4), round(dur, 4), [(0, lo), (round(peak, 3), hi), (1, lo * 0.9)], "pulse", 0.15,
                    0.8, jitter=1.2, rough=(0.55, 11.0), breath=0.25, shimmer=0.4,
                    formants=[(1500, 700, 1.0), (3000, 1000, 0.6), (5200, 1600, 0.35)], attack=0.03, release=0.04,
                    amp=amp, gain=gain)


def latch(fx: Fx, start: float, gain: float = 0.6, name: str = "latch") -> Modal:
    """A latch or handle: a small metal click and its release a moment later."""
    return fx.strike("iron", size=0.05, start=round(start, 4), gain=gain, prefix=name, dur=0.25,
                     hits=[(0.0, 1.0, 0.0006), (round(0.02 + 0.02 * fx.rand(name), 4), 0.5, 0.0006)])


def panel(fx: Fx, kind: str, hits: list, gain: float = 1.0, ring: float = 1.0) -> Modal:
    modes = _jittered(fx, PANELS[kind], kind, 0.1, ring=ring)
    return Modal(0.0, round(hits[-1][0] + 1.2 * ring + 0.1, 3), modes, hits,
                 hardness=2500 if kind != "gate" else 6000, click=0.1, gain=gain)


def closure(fx: Fx, kind: str, event: str, iron: bool, size: float) -> list:
    """Doors, gates and chests: open, close, locked, unlock, knock."""
    body = "gate" if iron and kind == "door" else kind
    k = 2 ** (-0.6 * (size - 0.5))
    if event == "open":
        swing = (0.7 if kind == "door" else 0.45) * (0.8 + 0.4 * fx.rand("swing")) * (1 + 0.3 * size)
        lo, hi = 650 * k * (0.8 + 0.4 * fx.g.base("hinge")), 1300 * k * (0.8 + 0.4 * fx.g.base("hinge"))
        out = [latch(fx, 0.0), squeak(fx, 0.08, swing, lo, hi, 0.6)]
        if kind == "chest":   # the lid comes to rest against its stop
            out.append(panel(fx, body, [(round(0.08 + swing, 4), 0.5, 0.004)], 0.6))
        return out
    if event == "close":
        swing = (0.35 if kind == "door" else 0.2) * (0.8 + 0.4 * fx.rand("swing"))
        lo = 700 * k * (0.8 + 0.4 * fx.g.base("hinge"))
        slam = round(swing + 0.03, 4)
        return [squeak(fx, 0.0, swing, lo, lo * 1.4, 0.3),
                panel(fx, body, [(slam, 1.0, 0.004), (round(slam + 0.012, 4), 0.4, 0.002)]),
                Noise(slam, 0.12, [(0, 220 * k), (1, 90 * k)], "low", 0.9, amp=decay_curve(5), attack=0.002,
                      release=0.02, gain=0.9),
                latch(fx, slam + 0.005, 0.5)]
    if event == "locked":   # the handle tried, the bolt holding
        n = 2 + int(3.99 * fx.rand("tries"))
        t, out = 0.0, []
        for j in range(n):
            g = 1.0 if j == int(fx.rand("hard") * n) else 0.35 + 0.4 * fx.rand(f"tg{j}")
            out.append(latch(fx, t, 0.7 * g, f"try{j}"))
            out.append(panel(fx, body, [(round(t, 4), 0.5 * g, 0.003)], 0.4 * g, 0.4))
            t += 0.06 + 0.07 * fx.rand(f"tt{j}")
        return out
    if event == "unlock":   # the key goes in, the tumblers click, the bolt slides
        out = [Modal(0.0, 0.3, [(2600, 0.04, 1.0), (4100, 0.03, 0.7), (6900, 0.02, 0.5)], [(0.0, 0.2, 0.0005)],
                     (0.0, 0.18, 0.4, 0.0), 9000, 0.3, 0.4)]
        t = 0.25
        for j in range(2 + int(2.99 * fx.rand("pins"))):
            out.append(latch(fx, t, 0.25 + 0.15 * fx.rand(f"pg{j}"), f"pin{j}"))
            t += 0.05 + 0.08 * fx.rand(f"pt{j}")
        out += [fx.strike("iron", size=0.3, start=round(t + 0.05, 4), hits=[(0.0, 1.0, 0.002)], gain=0.9, prefix="bolt",
                          dur=0.4, ring=0.4),
                panel(fx, body, [(round(t + 0.05, 4), 0.35, 0.003)], 0.5, 0.5)]
        return out
    # knock: two or three knuckle raps, dull: knuckles wake the panel's middle (~400-1200 Hz), not its lowest modes
    n = 2 + int(1.99 * fx.rand("raps"))
    hits, t = [], 0.0
    for j in range(n):
        hits.append((round(t, 4), round(0.75 + 0.25 * fx.rand(f"rg{j}"), 3), 0.004))
        t += 0.16 + 0.08 * fx.rand(f"r{j}")
    knock = PANELS["gate"] if body == "gate" else [(140, 0.3, 0.3), (398, 0.25, 1.0), (562, 0.12, 0.7),
                                                   (750, 0.1, 0.8), (1007, 0.08, 0.6), (1218, 0.05, 0.3)]
    return [Modal(0.0, round(t + 0.4, 3), _jittered(fx, knock, "kn", 0.1), hits, hardness=3500, click=0.05)] + [
        Noise(h[0], 0.03, [(0, 900), (1, 600)], "band", 0.8, amp=decay_curve(5), attack=0.001, release=0.01,
              gain=0.35 * h[1]) for h in hits]


# --- items ------------------------------------------------------------------------------------------------------------
#
# From recordings: coins clink very high (strongest 8-13 kHz; small coins' modes 8.4-13.7 kHz ringing 0.06-0.46 s,
# thicker coins 1.5-5 kHz), several clinks 20-100 ms apart; a dropped coin bounces (~0.1 s apart) and then spins,
# its rattle speeding up until it settles. A cork pops low (the bottle's neck resonating at 500-1150 Hz, ~0.15 s).
# A swallow is low (strongest 250-500 Hz, a resonance near 1-1.3 kHz) in bursts of 2-3 gulps 40-50 ms apart.
# A page turning crackles across 1-6 kHz for 0.3-0.6 s and ends in a soft flap.

COIN = [(8437, 0.1, 0.8), (9445, 0.26, 0.6), (9867, 0.12, 1.0), (10125, 0.11, 0.6), (11953, 0.3, 0.9),
        (12703, 0.19, 0.6), (13101, 0.13, 0.5), (14500, 0.1, 0.5), (15600, 0.08, 0.4), (6700, 0.12, 0.5),
        (2929, 0.5, 0.25), (3914, 0.45, 0.3), (5156, 0.4, 0.3)]


def coins(fx: Fx, n: int, spread: float) -> list:
    """A handful of coins clinking against each other."""
    out = []
    for c in range(2):
        hits = [(round(spread * fx.rand(f"c{c}t{k}"), 4), round(0.3 + 0.7 * fx.rand(f"c{c}g{k}"), 3), 0.0004)
                for k in range(n)]
        out.append(Modal(0.0, round(spread + 0.6, 3), _jittered(fx, COIN, f"coin{c}", 0.08), sorted(hits),
                         hardness=16000, click=0.1, gain=1.0 - 0.3 * c))
    return out


def coin_drop(fx: Fx) -> list:
    """One coin dropped: it lands, bounces, then spins faster and faster until it lies still."""
    hits, t, g = [(0.0, 1.0, 0.0004)], 0.0, 1.0
    for k in range(2 + int(2 * fx.rand("bounces"))):
        t += 0.1 + 0.04 * fx.rand(f"b{k}")
        g *= 0.6
        hits.append((round(t, 4), round(g, 3), 0.0004))
    gap = 0.05
    while gap > 0.008:   # the spin: contacts closing in, quieter
        t, gap, g = t + gap, gap * 0.82, g * 0.93
        hits.append((round(t, 4), round(g * 0.6, 3), 0.0004))
    hits.append((round(t + 0.02, 4), round(g, 3), 0.0004))
    return [Modal(0.0, round(t + 0.5, 3), _jittered(fx, COIN, "coin0", 0.08), hits, hardness=16000, click=0.1),
            fx.strike("wood", size=0.3, hits=[(h[0], h[1], 0.001) for h in hits[:3]], gain=0.25, prefix="table",
                      click=0.0)]


def gulps(fx: Fx, start: float, n: int) -> list:
    """Swallowing: low gulps, each a burst of 2-3 clicks of the throat 40-50 ms apart."""
    out, t = [], start
    for k in range(n):
        sub = [(round(t + j * (0.04 + 0.01 * fx.rand(f"g{k}{j}")), 4), round(1.0 - 0.3 * j, 2), 0.006)
               for j in range(2 + int(fx.rand(f"gn{k}") * 1.99))]
        throat = round(330 * (0.85 + 0.3 * fx.rand(f"gf{k}")), 1)
        out.append(Modal(0.0, round(sub[-1][0] + 0.2, 3), [(throat, 0.06, 1.0), (1150, 0.04, 0.4)], sub, hardness=1800,
                         click=0.0))
        t += 0.38 + 0.12 * fx.rand(f"gt{k}")
    return out


def paper(fx: Fx, dur: float, flap: bool = True) -> list:
    """Paper handled: crackles across 1-6 kHz and, at the end, a soft flap."""
    out = [Scatter(0.0, round(dur, 3), [(0, 40), (0.5, 90), (1, 30)], "pop", (1000, 6000), (0.001, 0.006), (0.2, 1.0)),
           Noise(0.0, round(dur, 3), [(0, 2500), (1, 3500)], "band", 0.6, amp=bell_curve(0.6, 1.5), attack=0.02,
                 wobble=(30.0, 0.8), gain=0.5)]
    if flap:
        out.append(Noise(round(dur * 0.9, 3), 0.07, [(0, 700), (1, 450)], "band", 0.8, amp=decay_curve(4),
                         attack=0.004, gain=0.6))
    return out


def item(fx: Fx, style: str, event: str) -> list:
    if style == "coins":
        if event == "pickup":
            return coins(fx, 5 + int(4 * fx.rand("n")), 0.35)
        if event == "use":   # paid out: a few coins set down on a counter, one by one
            out = coins(fx, 3, 0.25)
            return out + [fx.strike("wood", size=0.3, hits=[(round(0.1 * k, 3), 0.4, 0.001) for k in range(3)],
                                    gain=0.3, prefix="counter", click=0.0)]
        return coin_drop(fx)
    if style == "potion":
        glass = fx.strike("glass", size=0.35, hits=[(0.0, 1.0, 0.0008)], gain=0.6, prefix="bottle", ring=0.6)
        if event == "pickup":
            return [glass, Noise(0.0, 0.08, [(0, 900), (1, 700)], "band", 0.8, amp=decay_curve(4), gain=0.2)]
        if event == "use":   # uncork, drink, breathe out
            neck = 500 + 650 * fx.g.base("neck")
            return [squeak(fx, 0.0, 0.18, 1800, 2600, 0.15, "cork"),
                    Modal(0.2, 0.3, [(round(neck, 1), 0.15, 1.0), (round(neck * 2.1, 1), 0.06, 0.3)],
                          [(0.0, 1.0, 0.002)], hardness=4000, click=0.3),
                    *gulps(fx, 0.6, 3),
                    Noise(1.9, 0.35, [(0, 900), (1, 500)], "band", 0.7, amp=bell_curve(0.2, 1.5), attack=0.03,
                          gain=0.25)]
        # dropped: the bottle breaks
        return [glass, Scatter(0.0, 0.4, [(0, 400), (1, 0)], "ping", (2500, 9000), (0.002, 0.02), (0.2, 1.0), 0.7),
                Noise(0.0, 0.25, [(0, 5000), (1, 3000)], "high", 0.7, amp=decay_curve(5), attack=0.001, gain=0.5),
                Scatter(0.05, 0.3, [(0, 120), (1, 0)], "drop", (600, 2500), (0.003, 0.01), (0.2, 1.0), 0.4)]
    if style == "scroll":
        if event == "pickup":
            return paper(fx, 0.25)
        if event == "use":
            return paper(fx, 0.45 + 0.2 * fx.rand("pages"))
        return paper(fx, 0.12) + [Noise(0.1, 0.08, [(0, 500), (1, 300)], "low", 0.8, amp=decay_curve(5), gain=0.5)]
    # gem: a crystal that rings
    ring = 1.5 if event == "use" else 1.0
    gem = fx.strike("glass", size=0.1, hits=[(0.0, 1.0, 0.0006)], ring=ring * 2, prefix="gem", click=0.05)
    if event == "use":
        return [gem, Scatter(0.0, 0.8, [(0, 30), (1, 0)], "ping", (3000, 9000), (0.05, 0.2), (0.2, 0.8), 0.4)]
    if event == "drop":
        return [gem, fx.strike("stone", size=0.6, hits=[(0.0, 1.0, 0.001)], gain=0.3, prefix="g", click=0.2)]
    return [gem]


# --- breakables -------------------------------------------------------------------------------------------------------
#
# From recordings of crates, clay jars, pots and glass breaking. A wooden crate splinters: low-mid (strongest
# 250-1600 Hz), 9-18 cracks in the first half second, pieces still falling up to ~1 s. Clay and ceramic burst short
# and mid-bright (strongest ~1.6 kHz, -40 dB in 130-180 ms): a crack and a few shards. Glass is bright and long
# (strong up to 16 kHz, -40 dB in 0.3-0.9 s): a burst and many shards ringing as they fall.

BREAK_BODIES = {   # the intact object's own modes (Hz, T60 s, gain)
    "crate": [(160, 0.08, 0.6), (290, 0.07, 1.0), (450, 0.06, 0.8), (720, 0.05, 0.6), (1100, 0.04, 0.4)],
    "barrel": [(130, 0.12, 0.8), (240, 0.1, 1.0), (410, 0.08, 0.7), (650, 0.06, 0.5), (1600, 0.3, 0.3),
               (2700, 0.25, 0.25)],
    "pot": [(1250, 0.16, 0.8), (1700, 0.14, 1.0), (2600, 0.1, 0.7), (3600, 0.1, 0.7), (5200, 0.08, 0.8),
            (7400, 0.06, 0.7), (9800, 0.04, 0.5)],
    "glass": [(2200, 0.4, 1.0), (3500, 0.3, 0.8), (5300, 0.25, 0.6), (7800, 0.2, 0.4), (10500, 0.15, 0.3)],
}


def breakable(fx: Fx, style: str, broken: bool, size: float) -> list:
    k = 2 ** (-0.6 * (size - 0.5))
    body = _jittered(fx, BREAK_BODIES[style], style, 0.1, k)
    hard = {"crate": 3500, "barrel": 4000, "pot": 9000, "glass": 14000}[style]
    out = [Modal(0.0, 1.0, body, [(0.0, 1.0, 0.003 if style in ("crate", "barrel") else 0.001)], hardness=hard,
                 click=0.3),
           Noise(0.0, 0.06, [(0, 300 * k), (1, 150 * k)], "low", 0.9, amp=decay_curve(5), attack=0.001, release=0.01,
                 gain=0.6 if style in ("crate", "barrel") else 0.25)]
    if not broken:
        return out
    if style in ("crate", "barrel"):   # planks splinter and snap, then the pieces land
        snaps = [(round(0.02 + 0.35 * fx.rand(f"s{j}") ** 1.6, 4), round(0.3 + 0.7 * fx.rand(f"sg{j}"), 3), 0.002)
                 for j in range(9 + int(9 * fx.rand("snaps")))]
        out += [Modal(0.0, 0.6, wood_modes(fx, 0.45 * k, 0.025, 6), sorted(snaps), hardness=5000, click=0.2, gain=0.8),
                Scatter(0.0, 0.45, [(0, 200), (0.4, 120), (1, 0)], "pop", (400, 3000), (0.002, 0.008), (0.2, 1.0),
                        0.6),
                Scatter(0.15, 0.8, [(0, 25), (1, 0)], "pop", (200, 1200), (0.004, 0.012), (0.3, 1.0), 0.45),
                Noise(0.0, 0.3, [(0, 4000), (1, 3000)], "high", 0.7, amp=[(0, 1), (0.1, 0.3), (1, 0)], attack=0.0005,
                      wobble=(60.0, 0.9), gain=0.12)]   # fibres tearing
        if style == "barrel":   # the iron hoops ring and clatter
            out.append(fx.strike("iron", size=0.6, hits=[(0.0, 0.6, 0.001), (round(0.3 + 0.2 * fx.rand("hoop"), 3),
                                                                             0.4, 0.001)], gain=0.4, prefix="hoop"))
        return out
    if style == "pot":   # a short burst and a few shards
        return out + [Noise(0.0, 0.03, [(0, 2500), (1, 1800)], "band", 0.7, amp=decay_curve(4), attack=0.0005,
                            gain=0.8),
                      Noise(0.0, 0.02, [(0, 4500), (1, 4000)], "high", 0.7, amp=decay_curve(4), attack=0.0005,
                            gain=0.6),
                      Scatter(0.01, 0.3, [(0, 60), (1, 0)], "pop", (2000, 10000), (0.002, 0.008), (0.3, 1.0), 0.7),
                      Scatter(0.05, 0.3, [(0, 15), (1, 0)], "ping", (2500, 6000), (0.01, 0.04), (0.2, 0.7), 0.35)]
    out[1] = replace(out[1], gain=1.3)   # glass breaks with a thump of whatever broke it
    return out + [Noise(0.0, 0.08, [(0, 800), (1, 700)], "high", 0.7, amp=decay_curve(5), attack=0.0005, gain=0.9),
                  Scatter(0.0, round(0.6 + 0.4 * size, 3), [(0, 220), (0.3, 80), (1, 0)], "ping", (2500, 12000),
                          (0.005, 0.03), (0.2, 1.0), 0.8),
                  Scatter(0.1, 0.9, [(0, 30), (1, 0)], "ping", (3000, 9000), (0.02, 0.08), (0.1, 0.6), 0.4)]

# --- weapons ----------------------------------------------------------------------------------------------------------

@recipe("blade", ("swing", "clash", "hit_flesh", "hit_wood", "hit_metal", "hit_stone", "draw", "drop"),
        ("steel", "iron", "glass", "wood"))
def blade(fx: Fx):
    """Swords, daggers, axes: swing, clash, hits on flesh/wood/armor/stone, draw, drop."""
    mat, s, p, e = fx.style, fx.size, fx.power, fx.event
    # chosen by ear: size 0.5 / power 0.5 is the measured sword, size 1 the heavy one, power 1 the cinematic one
    # (swing, clash and hits; glass and wooden blades keep the generic clash and hits)
    big, small, hard = max(s - 0.5, 0) * 2, max(0.5 - s, 0) * 2, max(p - 0.5, 0) * 2
    if e == "swing":
        layers = blade_swing(fx, 0.055 + 0.025 * big - 0.015 * small, 0.17 + 0.08 * big - 0.05 * small,
                             1400 - 400 * big + 600 * small, 0.25 * hard, 0.5 * big)
        return fx.voice(fx.level(0.5), **splits(layers))   # half the clash, as in the mix chosen by ear
    shift = 2 ** (-0.83 * (s - 0.5)) * (0.8 if mat == "iron" else 1.0)
    if e == "clash" and mat in ("steel", "iron"):
        ring = (1 - 0.3 * big) * (1 + 1.2 * hard) * (0.5 if mat == "iron" else 1.0)
        slide = (0.03 - 0.01 * big + 0.05 * hard, 0.08 - 0.03 * big + 0.07 * hard)
        return fx.voice(fx.level(0.95), **splits(blade_clash(fx, shift, ring, slide, 1 + 0.3 * hard, 0.5 * big)))
    if e in TARGETS and mat in ("steel", "iron"):
        layers = blade_hit(fx, TARGETS[e], shift, 0.5 if mat == "iron" else 1.0, big, hard)
        return fx.voice(fx.level(0.95), **splits(layers))
    if e == "draw" and mat in ("steel", "iron"):
        dur = (0.3 + 0.25 * s) * (0.85 + 0.3 * fx.rand("pull")) * (1 - 0.3 * hard)
        ring = (1 + 1.2 * hard) * (0.5 if mat == "iron" else 1.0)
        return fx.voice(fx.level(0.6), **splits(blade_draw(fx, shift, ring, dur)))
    if e == "drop" and mat in ("steel", "iron"):
        return fx.voice(fx.level(0.95), **splits(blade_drop(fx, shift, 0.5 if mat == "iron" else 1.0)))
    if e == "clash":
        lag = 0.002 + 0.006 * fx.rand("lag")
        slide = (0.0, 0.04 + 0.16 * fx.rand("slide"), 0.5 + 0.5 * p, 60 + 80 * fx.rand("judder"))
        a = fx.strike(mat, hits=[(0.0, 1.0, 0.0008)], scrape=slide, prefix="a")
        b = fx.strike(mat, start=lag, size=min(max(s + 0.3 * (fx.rand("foe") - 0.5), 0), 1),
                      hits=[(0.0, 1.0, 0.0008)], scrape=slide, gain=0.8, prefix="b")
        return fx.voice(modal=[a, b], noise=[burst(0.0, 0.04, 5000, 0.5)], space=0.6, wet=0.12)
    if e in TARGETS:
        return fx.voice(**splits(impact(fx, mat, TARGETS[e], edge=1.0)), space=0.4, wet=0.1)
    if e == "draw":
        dur = 0.35 + 0.3 * s
        ring = fx.strike(mat, hits=[(dur, 0.25, 0.001)], scrape=(0.0, dur, 1.0, 180 + 120 * fx.rand("judder")),
                         prefix="a", dur=dur + 0.8 if mat != "wood" else dur + 0.1)
        hiss = Noise(0.0, round(dur, 3), [(0, 3000), (1, 7000)], "band", 2.0, amp=[(0, 0.4), (0.85, 1), (1, 0)],
                     attack=0.03, release=0.02, gain=0.8)
        return fx.voice(modal=[ring], noise=[hiss])
    # drop: falls, bounces and clatters on stone, the floor muffling its ring
    hits = bounces(fx, 6, 0.2, 0.5, 3)
    ground = fx.strike("stone", size=0.75, hits=hits, gain=1.0, prefix="g")
    return fx.voice(modal=[fx.strike(mat, hits=hits, prefix="a", dur=1.5, ring=0.3, click=1.0), ground])


@recipe("blunt", ("swing", "hit_flesh", "hit_wood", "hit_metal", "hit_stone", "drop"), ("wood", "iron", "stone"))
def blunt(fx: Fx):
    """Clubs, maces, hammers, staves: heavy swings and hits."""
    head, s, p, e = fx.style, fx.size, fx.power, fx.event
    big, hard = max(s - 0.5, 0) * 2, max(p - 0.5, 0) * 2    # size 1: heavier head, power 1: cinematic
    if e == "swing":
        layers = blade_swing(fx, 0.06 + 0.03 * s, 0.13 + 0.08 * s, 450 * 2 ** (-0.5 * (s - 0.5)), 0.0,
                             0.35 + 0.4 * big, 200 * 2 ** (-0.6 * (s - 0.5)))
        return fx.voice(fx.level(0.5), **splits(layers))
    if e in TARGETS:
        target = {"iron": "metal"}.get(TARGETS[e], TARGETS[e])
        return fx.voice(fx.level(0.95), **splits(blunt_hit(fx, head, target, big, hard)))
    return fx.voice(fx.level(0.95), **splits(blunt_drop(fx, head, big)))


@recipe("shield", ("block_blade", "block_blunt", "block_arrow", "bash"), ("wood", "metal"))
def shield(fx: Fx):
    """Shields, wooden or metal: blocking a blade, a blunt weapon or an arrow, and bashing."""
    s, p = fx.size, fx.power
    by = fx.event.removeprefix("block_")
    layers = shield_hit(fx, fx.style, by, max(s - 0.5, 0) * 2, max(p - 0.5, 0) * 2)
    return fx.voice(fx.level(0.95), **splits(layers))


@recipe("gear", ("move", "run", "equip"), ("chainmail", "plate", "leather"))
def gear(fx: Fx):
    """Armour and clothing moving: chainmail jingling, plate clanking, leather creaking."""
    s, p, e = fx.size, fx.power, fx.event
    if e == "equip":   # putting it on: two movements and a buckle or a latch
        a = gear_move(fx, fx.style, 0.6 + 0.3 * s, 0.8)
        b = [replace(x, start=round(x.start + 0.75, 3)) for x in gear_move(fx, fx.style, 0.45, 0.6)]
        latch = fx.strike("iron", size=0.05, start=1.3, hits=[(0.0, 1.0, 0.0006)], gain=0.5, prefix="latch")
        return fx.voice(fx.level(0.7), **splits([*a, *b, latch]))
    dur = (0.5 + 0.3 * s) * (0.55 if e == "run" else 1.0) * (0.85 + 0.3 * fx.rand("dur"))
    return fx.voice(fx.level(0.5 + 0.2 * (e == "run")), **splits(gear_move(fx, fx.style, dur, 0.6 + 0.4 * p)))


@recipe("body", ("fall", "drop"), ("stone", "wood", "dirt"))
def body(fx: Fx):
    """A body falling to the floor: collapsing (fall) or dropped as dead weight (drop)."""
    weight = max(fx.size - 0.5, 0) * 2
    return fx.voice(fx.level(0.9), **splits(body_fall(fx, fx.style, weight, dead=fx.event == "drop")))


@recipe("door", ("open", "close", "locked", "unlock", "knock"), ("wood", "iron"))
def door(fx: Fx):
    """Doors and gates, wooden or iron: open (squeaking), close (slam), locked (rattle), unlock, knock."""
    layers = closure(fx, "door", fx.event, fx.style == "iron", fx.size)
    return fx.voice(fx.level(0.9), **splits(layers))


@recipe("chest", ("open", "close", "locked", "unlock"), ("wood", "iron"))
def chest(fx: Fx):
    """Chests: open (latch and creaking lid), close, locked (rattle), unlock."""
    layers = closure(fx, "chest", fx.event, fx.style == "iron", fx.size)
    return fx.voice(fx.level(0.8), **splits(layers))


@recipe("item", ("pickup", "use", "drop"), ("coins", "potion", "scroll", "gem"))
def item_recipe(fx: Fx):
    """Inventory items: coins, a potion, a scroll or book, a gem; picked up, used (paid, drunk, read), dropped."""
    return fx.voice(fx.level(0.7), **splits(item(fx, fx.style, fx.event)))


@recipe("breakable", ("hit", "break"), ("crate", "barrel", "pot", "glass"))
def breakable_recipe(fx: Fx):
    """Things to smash: wooden crates and barrels, clay pots, glass. Hit (it holds) or break."""
    return fx.voice(fx.level(0.95), **splits(breakable(fx, fx.style, fx.event == "break", fx.size)))


@recipe("bow", ("draw", "release", "fly", "hit_wood", "hit_flesh", "hit_stone"), ("longbow", "crossbow"))
def bow(fx: Fx):
    """Bows and crossbows: draw, release, the arrow's flight and where it lands."""
    s, p, e, cross = fx.size, fx.power, fx.event, fx.style == "crossbow"
    # levels at full power, as in the mix chosen by ear: draw 0.7, release 0.5, fly-by 0.8, strike 0.95
    if e == "draw":
        dur = 0.5 + 0.5 * s
        if cross:  # a ratchet: regular clicks, then the latch
            clicks = [(round(i / 11 + 0.004 * fx.rand(f"c{i}"), 4), 0.8, 0.0006) for i in range(int(dur * 11))]
            return fx.voice(modal=[fx.strike("iron", size=0.05, hits=clicks, prefix="pawl", dur=dur + 0.2),
                                   fx.strike("wood", size=0.3, hits=[(dur, 1.0, 0.002)], prefix="lock")])
        return fx.voice(fx.level(0.7), **splits(creak(fx, 0.9 * (0.8 + 0.4 * s))))
    if e == "release":
        layers = bow_release(fx, cross)
        if cross:
            layers.append(fx.strike("iron", size=0.1, hits=[(0.0, 1.0, 0.0006)], gain=0.6, prefix="click"))
        return fx.voice(fx.level(0.5), **splits(layers))
    if e == "fly":  # passing the listener (the release already carries it away from the archer)
        approach = 0.45 * (0.8 + 0.4 * fx.rand("approach")) * (1.15 - 0.3 * p) * (0.7 if cross else 1.0)
        return fx.voice(fx.level(0.8), noise=fletching(0.0, *flyby(approach, centre=3400.0 if cross else 2800.0)))
    hit = {"wood": arrow_in_wood, "flesh": arrow_in_flesh, "stone": arrow_on_stone}[TARGETS[e]]
    return fx.voice(fx.level(0.95), **splits(hit(fx, cross)))


# --- footsteps --------------------------------------------------------------------------------------------------------

# Measured on recordings of walking on each surface (single steps cut from sequences, median of 16-46 steps):
#   stone   low-mid knock (strongest 250-500 Hz), a hard sole click, -20 dB in ~33 ms
#   wood    lower and longer (strongest 250 Hz, -20 dB in ~51 ms), the heel and toe ~60 ms apart, a creak now and then
#   gravel  little low (-21 dB below 300 Hz), a crunch strongest at 1-1.6 kHz, ~150 ms of grains
#   grass   bright: a rustle centred near 8 kHz lasting ~0.35 s, a soft low thump
#   snow    a strong low thump (250 Hz) under a squeaky crunch at 1-2.5 kHz
#   metal   (plate floors and stairs, mostly muffled) low and ringing: strongest below 300 Hz for ~0.24 s
#   dirt    low-mid, short (-20 dB in ~24 ms), with fine grit
#   water   no low at all: splashes strongest at 2.5-5 kHz
STEPS = {  # thump (Hz, s, Q, gain), sole contact (Hz, gain), click (Hz, gain), floor (material, gain), heel-toe gap s,
    #        toe level, grains (rate/s, Hz range, decay range, s, gain), rustle (Hz, s, gain)
    # Gains balanced by rendering until each surface's median step spectrum matched the recordings (±5 dB per band).
    "stone": dict(thump=(350, 0.05, 0.9, 1.0), sole=(1200, 0.85), click=(2500, 0.24), floor=("stone", 0.23), gap=0.03,
                  toe=0.35, grains=(90, (1500, 6000), (0.0005, 0.002), 0.15, 0.11)),
    "wood": dict(thump=(240, 0.08, 1.2, 1.0), sole=(1200, 0.85), click=(2500, 0.12), floor=("wood", 1.27), gap=0.06,
                 toe=0.5, grains=(40, (600, 2500), (0.002, 0.006), 0.18, 0.17), creak=0.25),
    "gravel": dict(thump=(380, 0.05, 1.0, 0.5), sole=(1200, 3.36), click=None, floor=None, gap=0.035, toe=0.6,
                   grains=(700, (500, 3500), (0.001, 0.004), 0.15, 0.7)),
    "grass": dict(thump=(300, 0.07, 0.8, 1.6), click=None, floor=None, gap=0.045, toe=0.5,
                  grains=(120, (2000, 9000), (0.0005, 0.002), 0.25, 0.15), rustle=(8000, 0.33, 0.6)),
    "snow": dict(thump=(240, 0.1, 1.0, 1.6), sole=(1200, 2.39), click=None, floor=None, gap=0.045, toe=0.5,
                 grains=(600, (900, 3000), (0.0008, 0.003), 0.16, 0.45)),
    "metal": dict(thump=(180, 0.14, 1.2, 1.0), sole=(1200, 0.85), click=None, floor=("iron", 0.4), gap=0.05, toe=0.5,
                  grains=None),
    "dirt": dict(thump=(330, 0.045, 1.0, 1.0), sole=(1200, 0.85), click=None, floor=None, gap=0.04, toe=0.4,
                 grains=(300, (400, 2500), (0.0008, 0.003), 0.18, 0.12)),
    "water": dict(thump=(300, 0.04, 1.0, 0.1), click=None, floor=None, gap=0.03, toe=0.6, grains=None, splash=1.0),
}


@recipe("footstep", ("walk", "run", "land", "scuff"), tuple(STEPS))
def footstep(fx: Fx):
    """Footsteps on a surface: walk, run, land (after a jump), scuff."""
    surf, s, e = fx.style, fx.size, fx.event
    st = STEPS[surf]
    force = {"walk": 0.5, "run": 0.8, "land": 1.0, "scuff": 0.4}[e] * (0.6 + 0.4 * fx.power)
    gap = st["gap"] * {"walk": 1.0, "run": 0.6, "land": 0.0, "scuff": 1.5}[e] * (0.8 + 0.4 * fx.rand("gap"))
    weight = 1.4 - 0.8 * s                                    # heavier walkers sound lower
    contacts = [(0.0, force)] + ([(round(gap, 4), st["toe"] * force)] if gap else [])
    hz, length, q, thump = st["thump"]
    layers = []
    for t, g in contacts:
        layers.append(Noise(t, round(length * (1 + 0.6 * (e == "land")), 4), [(0, hz * weight), (1, hz * weight * 0.6)],
                            "low", q, amp=decay_curve(5), attack=0.002, gain=thump * g))   # 12 dB/octave above
        if st.get("sole"):   # the sole meeting the floor: a short broad contact
            layers.append(Noise(t, 0.015, [(0, st["sole"][0]), (1, st["sole"][0] * 0.8)], "band", 0.6,
                                amp=decay_curve(5), attack=0.0005, gain=st["sole"][1] * g))
        if st["click"]:
            layers.append(Noise(t, 0.008, [(0, st["click"][0]), (1, st["click"][0])], "high", 0.7, amp=decay_curve(5),
                                attack=0.0005, gain=st["click"][1] * g * (1 + 0.5 * (e == "run"))))
    if st["floor"]:
        mat, g = st["floor"]
        layers.append(fx.strike(mat, size=0.5 + 0.35 * s, hits=[(t, c, 0.003) for t, c in contacts], hardness=3000,
                                gain=g * force, prefix="floor", click=0.15))
    if st["grains"]:
        rate, band, decay, dur, g = st["grains"]
        dur = round(dur + gap + 0.08 * (e == "land") + 0.15 * (e == "scuff"), 4)
        layers.append(Scatter(0.0, dur, [(0, rate * force), (0.4, rate * force * 0.7), (1, 0)], "pop", band, decay,
                              (0.2, 1.0), g * force))
    if "rustle" in st:
        hz_r, dur, g = st["rustle"]
        for k in (1.0, 0.2):   # the blades' hiss and the stems' swish
            layers.append(Noise(0.0, round(dur * (1 + 0.5 * (e == "scuff")), 4), [(0, hz_r * k * 0.8), (1, hz_r * k)],
                                "band", 0.7, amp=[(0, 1.0), (0.3, 0.6), (1, 0.0)], attack=0.01, wobble=(30.0, 0.7),
                                gain=g * force * (1.0 if k == 1 else 0.6)))
    roll_hz, roll_dur, roll = st.get("roll", (2500, 0.2, 0.04))
    if e == "scuff":   # the sole dragging: friction noise
        roll_dur, roll = 0.3, max(roll * 3, 0.5)
    # the sole rolling from heel to toe and the cloth moving: quiet friction that keeps the highs alive ~0.15-0.35 s
    layers.append(Noise(0.003, round(roll_dur + gap, 4), [(0, roll_hz), (1, roll_hz * 0.8)], "band", 0.7,
                        amp=[(0, 1.0), (0.35, 0.7), (1, 0.0)], attack=0.01, wobble=(25.0, 0.6), gain=roll * force))
    if st.get("creak") and fx.rand("creak") < st["creak"]:
        layers += [replace(c, start=0.02, gain=c.gain * 0.25) for c in creak(fx, 0.18)]
    if st.get("splash"):
        layers += [Scatter(0.0, 0.25, [(0, 300), (1, 0)], "drop", (900, 4000), (0.002, 0.008), (0.2, 1.0),
                           0.6 * force),
                   Noise(0.0, 0.18, [(0, 3500), (1, 2500)], "band", 0.8, amp=decay_curve(4), attack=0.003,
                         wobble=(40.0, 0.6), gain=st["splash"] * force)]
    return fx.voice(**splits(layers), gain=0.4 + 0.6 * force)


# --- explosions -------------------------------------------------------------------------------------------------------

@recipe("explosion", ("blast", "distant", "debris"), ("fire", "stone", "magic"))
def explosion(fx: Fx):
    """Explosions: the blast up close, a distant rumble, falling debris."""
    s, p, e = fx.size, fx.power, fx.event
    # Measured on recordings: up close strongest at 63-250 Hz (-9 dB at 1 kHz, -14 at 4 kHz), building over ~0.1 s,
    # -20 dB after ~0.8 s; far away almost only the lowest rumble (strongest at 31 Hz, -34 dB at 2 kHz)
    length = 1.2 + 2.0 * s
    boom = Noise(0.0, round(length, 3), [(0, 140 - 60 * s), (1, 45)], "low", 0.9, "brown", decay_curve(4),
                 attack=0.05, release=0.2, wobble=(4.0, 0.3), gain=1.0)
    body = Noise(0.0, round(length * 0.6, 3), [(0, 260 - 80 * s), (1, 120)], "band", 0.8, "brown", decay_curve(4),
                 attack=0.06, release=0.2, wobble=(6.0, 0.4), gain=0.8)
    roar = Noise(0.0, round(length * 0.6, 3), [(0, 600), (0.3, 350), (1, 150)], "band", 0.7, amp=decay_curve(3.5),
                 attack=0.08, release=0.2, wobble=(9.0, 0.6), gain=0.3 + 0.2 * p)
    if e == "distant":
        boom.start = body.start = roar.start = 0.05
        boom.amp = body.amp = decay_curve(6)
        body.gain, roar.gain = 0.3, 0.15   # distance leaves mostly the lowest rumble
        return fx.voice(noise=[boom, body, roar], lowpass=450, space=2.5, wet=0.35, gain=0.6)
    debris = Scatter(0.05, round(length, 3), [(0, 80 + 120 * p), (0.3, 40), (1, 0)], "pop", (400, 5000),
                     (0.001, 0.006), (0.1, 1.0), 0.35)
    if e == "debris":
        rocks = [fx.strike("stone", start=round(0.1 + 1.5 * fx.rand(f"r{k}") ** 1.5, 3), size=fx.rand(f"rs{k}"),
                           gain=0.3 + 0.6 * fx.rand(f"rg{k}"), prefix=f"r{k}") for k in range(8)]
        debris.start, debris.rate = 0.0, [(0, 120), (0.5, 60), (1, 0)]
        return fx.voice(modal=rocks, scatter=[debris], space=1.0, wet=0.15, gain=0.6)
    crack = burst(0.0, 0.05, 1500, 0.6 + 0.2 * p, "high", 0.5)
    layers = [boom, body, roar, crack, debris]
    if fx.style == "fire":
        layers.append(Noise(0.1, round(length, 3), [(0, 1200), (1, 600)], "band", 0.8, amp=decay_curve(2),
                            wobble=(14.0, 0.8), gain=0.3))
    elif fx.style == "magic":
        layers.append(Scatter(0.0, round(length * 0.6, 3), [(0, 60), (1, 0)], "ping", (2000, 9000), (0.05, 0.2),
                              (0.2, 1.0), 0.4))
    return fx.voice(**splits(layers), space=1.5 + s, wet=0.25)
