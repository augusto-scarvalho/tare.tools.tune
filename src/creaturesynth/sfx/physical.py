"""Physical sounds: weapons, footsteps, explosions.

Struck bodies are modal (Fx.strike): the material sets the modes, size their pitch and decay,
power how hard the contact is. Air and debris are moving noise bands and scattered events.
"""
import numpy as np

from ..spec import Modal, Noise, Scatter, Syllable
from . import Fx, bell_curve, decay_curve, recipe

TARGETS = {"hit_flesh": "flesh", "hit_wood": "wood", "hit_metal": "iron", "hit_stone": "stone"}


# --- building blocks ------------------------------------------------------------------------------------------------

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


# --- creaks ---------------------------------------------------------------------------------------------------------
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


# --- arrows ---------------------------------------------------------------------------------------------------------
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


# --- blades ---------------------------------------------------------------------------------------------------------
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


def blade_swing(fx: Fx, rise: float, fall: float, centre: float, whistle: float, vwoom: float) -> list:
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
        out.append(Noise(0.0, dur, [(0, 105), (round(p, 4), 135), (1, 115)], "band", 9.0, amp=amp, attack=0.0,
                         release=0.02, gain=vwoom))
    return out


# --- weapons --------------------------------------------------------------------------------------------------------

@recipe("blade", ("swing", "clash", "hit_flesh", "hit_wood", "hit_metal", "hit_stone", "draw", "drop"),
        ("steel", "iron", "glass", "wood"))
def blade(fx: Fx):
    """Swords, daggers, axes: swing, clash, hits on flesh/wood/armor/stone, draw, drop."""
    mat, s, p, e = fx.style, fx.size, fx.power, fx.event
    # chosen by ear: size 0.5 / power 0.5 is the measured sword, size 1 the heavy one, power 1 the cinematic one
    big, small, hard = max(s - 0.5, 0) * 2, max(0.5 - s, 0) * 2, max(p - 0.5, 0) * 2
    if e == "swing":
        layers = blade_swing(fx, 0.055 + 0.025 * big - 0.015 * small, 0.17 + 0.08 * big - 0.05 * small,
                             1400 - 400 * big + 600 * small, 0.25 * hard, 0.5 * big)
        return fx.voice(fx.level(0.5), **splits(layers))   # half the clash, as in the mix chosen by ear
    if e == "clash" and mat in ("steel", "iron"):
        shift = 2 ** (-0.83 * (s - 0.5)) * (0.8 if mat == "iron" else 1.0)
        ring = (1 - 0.3 * big) * (1 + 1.2 * hard) * (0.5 if mat == "iron" else 1.0)
        slide = (0.03 - 0.01 * big + 0.05 * hard, 0.08 - 0.03 * big + 0.07 * hard)
        return fx.voice(fx.level(0.95), **splits(blade_clash(fx, shift, ring, slide, 1 + 0.3 * hard, 0.5 * big)))
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
    mat, s, p, e = fx.style, fx.size, fx.power, fx.event
    if e == "swing":
        dur = (0.3 + 0.4 * s) * (1.15 - 0.3 * p)
        layers = whoosh(fx, 0.0, dur, (600 + 1200 * p) * (1 - 0.5 * s), 1.1)
        layers[0].wobble = (12.0 + 10 * fx.rand("flutter"), 0.5)    # tumbling mass: a fluttering push
        return fx.voice(noise=layers)
    if e in TARGETS:
        layers = impact(fx, mat, TARGETS[e], edge=0.0)
        layers.append(thud(0.0, 0.2 + 0.2 * s, 140 - 60 * s, 0.9))
        return fx.voice(**splits(layers), space=0.5, wet=0.1)
    hits = bounces(fx, 4, 0.14, 0.5)
    return fx.voice(modal=[fx.strike(mat, hits=hits, prefix="a", dur=1.5),
                           fx.strike("stone", size=0.6, hits=hits, gain=0.6, prefix="g")])


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
    target = TARGETS[e]
    if target == "wood":
        return fx.voice(fx.level(0.95), **splits(arrow_in_wood(fx, cross)))
    if target == "flesh":
        return fx.voice(**splits(flesh(fx, 0.0, 0.6, 0.8)))
    layers = [fx.strike(target, size=0.5, hits=[(0.0, 1.0, 0.0012)], prefix="t"),
              thud(0.0, 0.08, 400, 0.4),
              fx.strike("wood", size=0.1, hits=[(0.01, 0.8, 0.001)], gain=0.6, prefix="snap")]   # it breaks
    return fx.voice(**splits(layers), space=0.3, wet=0.1)


# --- footsteps ------------------------------------------------------------------------------------------------------

STEPS = {  # surface: heel/toe thump Hz, thump length s, thump Q, sole click Hz, click gain, floor material,
    #          heel-toe gap s, toe level, roll (sole friction) Hz, roll gain,
    #          texture (rate/s, Hz range, decay range, gain)
    # Structure found by a CLAP-guided search over walking sequences (docs/arquitetura.md, efeitos sonoros).
    "stone": (495, 0.055, 0.8, 1000, 1.2, "stone", 0.12, 0.25, 2800, 0.3, (700, (800, 6000), (0.0005, 0.002), 0.35)),
    "wood": (480, 0.17, 3.0, 4000, 0.85, "wood", 0.2, 0.64, 1860, 0.2, (120, (600, 2500), (0.002, 0.006), 0.8)),
    "metal": (480, 0.06, 1.0, 2500, 1.0, "iron", 0.12, 0.3, 2800, 0.3, None),
    "gravel": (405, 0.125, 2.0, 5700, 0.0, None, 0.18, 0.2, 3700, 0.55, (850, (600, 5000), (0.001, 0.005), 0.85)),
    "dirt": (300, 0.12, 1.5, 2000, 0.3, None, 0.15, 0.3, 1500, 0.4, (300, (300, 2000), (0.001, 0.004), 0.6)),
    "grass": (420, 0.095, 1.9, 3000, 0.9, None, 0.15, 0.23, 2400, 0.45, (900, (1500, 8000), (0.0005, 0.002), 0.4)),
    "snow": (350, 0.12, 1.5, 3000, 0.2, None, 0.16, 0.4, 2000, 0.3, (1500, (800, 3500), (0.0006, 0.003), 0.9)),
    "water": (300, 0.12, 1.0, 2000, 0.0, None, 0.15, 0.3, 1500, 0.0, None),
}


@recipe("footstep", ("walk", "run", "land", "scuff"), tuple(STEPS))
def footstep(fx: Fx):
    """Footsteps on a surface: walk, run, land (after a jump), scuff."""
    surf, s, e = fx.style, fx.size, fx.event
    thump_hz, thump_len, thump_q, click_hz, click, floor, gap, toe, roll_hz, roll, texture = STEPS[surf]
    force = {"walk": 0.5, "run": 0.8, "land": 1.0, "scuff": 0.4}[e] * (0.6 + 0.4 * fx.power)
    gap *= {"walk": 1.0, "run": 0.5, "land": 0.0, "scuff": 1.5}[e] * (0.85 + 0.3 * fx.rand("gap"))
    weight = 1.4 - 0.8 * s                                    # heavier walkers sound lower
    contacts = [(0.0, force)] + ([(round(gap, 4), toe * force)] if gap else [])
    layers = []
    for t, g in contacts:
        layers.append(Noise(t, round(thump_len * (1 + 0.5 * (e == "land")), 4), [(0, thump_hz * weight),
                                                                                (1, thump_hz * weight * 0.6)],
                            "band", thump_q, amp=decay_curve(5), attack=0.002, gain=g))
        if click:
            layers.append(Noise(t, 0.035, [(0, click_hz), (1, click_hz)], "high", 0.7, amp=decay_curve(6),
                                attack=0.0005, gain=g * click))
    if floor:
        layers.append(fx.strike(floor, size=0.5 + 0.35 * s, hits=[(t, g, 0.003) for t, g in contacts], hardness=4000,
                                gain=0.5 * force, prefix="floor"))
    if roll:
        layers.append(Noise(0.005, round(gap + 0.04 + 0.2 * (e == "scuff"), 4), [(0, roll_hz), (1, roll_hz * 0.7)],
                            "band", 1.0, amp=bell_curve(0.4), gain=roll * (2 if e == "scuff" else 1)))
    if texture:
        rate, hz, decay, gain = texture
        dur = round(0.12 + gap + 0.1 * (e == "land"), 4)
        layers.append(Scatter(0.0, dur, [(0, rate * force), (1, 0)], "pop", hz, decay, (0.2, 1.0), gain * force))
    if surf == "water":
        layers += [Scatter(0.0, 0.3, [(0, 250), (1, 0)], "drop", (400, 1800), (0.004, 0.012), (0.2, 1.0), 0.8 * force),
                   Noise(0.0, 0.25, [(0, 1500), (1, 3000)], "band", 1.0, amp=decay_curve(4), attack=0.005,
                         gain=0.5 * force)]
    return fx.voice(**splits(layers), gain=0.4 + 0.6 * force)


# --- explosions -----------------------------------------------------------------------------------------------------

@recipe("explosion", ("blast", "distant", "debris"), ("fire", "stone", "magic"))
def explosion(fx: Fx):
    """Explosions: the blast up close, a distant rumble, falling debris."""
    s, p, e = fx.size, fx.power, fx.event
    length = 1.5 + 2.5 * s
    boom = Noise(0.0, round(length, 3), [(0, 140 - 60 * s), (1, 45)], "low", 0.9, "brown", decay_curve(4),
                 attack=0.004, release=0.2, wobble=(4.0, 0.3), gain=1.0)
    roar = Noise(0.0, round(length * 0.7, 3), [(0, 900), (0.3, 400), (1, 150)], "band", 0.7, amp=decay_curve(3),
                 attack=0.01, release=0.2, wobble=(9.0, 0.6), gain=0.5 + 0.3 * p)
    if e == "distant":
        boom.start = roar.start = 0.05
        return fx.voice(noise=[boom, roar], lowpass=700, space=2.5, wet=0.35, gain=0.6)
    debris = Scatter(0.05, round(length, 3), [(0, 80 + 120 * p), (0.3, 40), (1, 0)], "pop", (400, 5000),
                     (0.001, 0.006), (0.1, 1.0), 0.35)
    if e == "debris":
        rocks = [fx.strike("stone", start=round(0.1 + 1.5 * fx.rand(f"r{k}") ** 1.5, 3), size=fx.rand(f"rs{k}"),
                           gain=0.3 + 0.6 * fx.rand(f"rg{k}"), prefix=f"r{k}") for k in range(8)]
        debris.start, debris.rate = 0.0, [(0, 120), (0.5, 60), (1, 0)]
        return fx.voice(modal=rocks, scatter=[debris], space=1.0, wet=0.15, gain=0.6)
    crack = burst(0.0, 0.05, 1500, 0.8 + 0.2 * p, "high", 0.5)
    layers = [boom, roar, crack, debris]
    if fx.style == "fire":
        layers.append(Noise(0.1, round(length, 3), [(0, 1200), (1, 600)], "band", 0.8, amp=decay_curve(2),
                            wobble=(14.0, 0.8), gain=0.3))
    elif fx.style == "magic":
        layers.append(Scatter(0.0, round(length * 0.6, 3), [(0, 60), (1, 0)], "ping", (2000, 9000), (0.05, 0.2),
                              (0.2, 1.0), 0.4))
    return fx.voice(**splits(layers), space=1.5 + s, wet=0.25)
