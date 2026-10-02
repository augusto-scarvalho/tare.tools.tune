"""Physical sounds: weapons, footsteps, explosions.

Struck bodies are modal (Fx.strike): the material sets the modes, size their pitch and decay,
power how hard the contact is. Air and debris are moving noise bands and scattered events.
"""
from dataclasses import replace

from ..spec import Modal, Noise, Scatter, Syllable
from . import MATERIALS, Fx, Material, bell_curve, decay_curve, recipe

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


def splits(layers: list) -> dict:
    """Group spec elements by type into Voice keyword arguments."""
    out = {"modal": [], "noise": [], "scatter": [], "syllables": []}
    for e in layers:
        out[{Modal: "modal", Noise: "noise", Scatter: "scatter", Syllable: "syllables"}[type(e)]].append(e)
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


# --- weapons --------------------------------------------------------------------------------------------------------
#
# The design constants below were fitted so that duration, decay, brightness, noisiness and band
# energies fall inside the spread of real recordings of each event (Freesound/Pixabay previews,
# used for analysis only): a real swing is a low whoosh, a clash is short, bright and noisy, an
# impact is a broadband crack with a short body, an arrow quivers in clicks. See docs/arquitetura.md.

SWING = {"dur": 0.5376, "peak": 0.2987, "sharp": 5.6918, "f0": 113.7, "f1": 216.0, "f2": 144.4, "q": 1.6217,
         "body": 0.6922, "edge": 0.153, "edge_hz": 936.6, "edge_q": 3.9907}
FLY = {"dur": 0.2826, "peak": 0.3719, "sharp": 4.8905, "f0": 150.0, "f1": 780.2, "f2": 215.3, "q": 0.7938,
       "body": 1.083, "edge": 0.2237, "edge_hz": 1068.1, "edge_q": 5.3718}
CLASH = {"low": 3458.2, "ring": 0.1685, "damp": 0.5469, "radiates": 947.0, "scrape": 0.4, "scrape_gain": 0.2854,
         "judder": 34.2, "click": 1.113, "lag": 0.0219, "second": 0.2596, "shimmer": 0.6412, "shimmer_hz": 2478.9,
         "shimmer_len": 0.4053, "thump": 0.1639, "thump_hz": 1200.0}
HIT = {  # target: contact crack, the target's body, the weapon's own ring, the mass behind it
    "wood": {"crack": 0.6855, "crack_hz": 2175.2, "crack_len": 0.0919, "body": 0.2778, "body_ring": 1.922,
             "weapon": 0.782, "weapon_ring": 1.2, "thud": 1.4192, "thud_hz": 133.7, "thud_len": 0.0352},
    "iron": {"crack": 0.5288, "crack_hz": 4829.6, "crack_len": 0.12, "body": 1.6039, "body_ring": 1.6,
             "weapon": 0.1998, "weapon_ring": 1.108, "thud": 0.6384, "thud_hz": 1000.0, "thud_len": 0.1138},
    "stone": {"crack": 1.0, "crack_hz": 2500.0, "crack_len": 0.02, "body": 0.6, "body_ring": 0.8, "weapon": 0.4,
              "weapon_ring": 0.3, "thud": 0.4, "thud_hz": 300.0, "thud_len": 0.05},
}
FLESH = {"thud": 1.1725, "thud_hz": 179.2, "thud_len": 0.0943, "squelch": 0.5458, "squelch_hz": 921.7,
         "squelch_q": 1.3316, "squelch_len": 0.1614, "crunch": 0.5633, "crunch_rate": 199.6, "slice": 0.4569,
         "slice_hz": 2472.4, "slice_len": 0.1543}
ARROW_HIT = {"crack": 3.1043, "crack_hz": 3082.0, "crack_len": 0.1598, "body": 0.2724, "body_ring": 0.6103,
             "quiver": 0.2947, "quiver_rate": 28.6, "quiver_len": 0.5316, "quiver_size": 0.377, "thud": 0.6039,
             "thud_hz": 821.0}
RELEASE = {"swell": 0.2506, "swell_f0": 1406.0, "swell_f1": 6840.6, "swell_q": 0.4783, "swell_gain": 0.3879,
           "crack": 0.75, "crack_hz": 1155.1, "crack_len": 0.047, "string": 0.4677, "string_ring": 0.5087,
           "thump": 0.3629, "thump_hz": 275.6, "thump_len": 0.5096, "nock": 0.2786}
BOW_DRAW = {"dur": 0.8267, "rate": 32.5, "rate_end": 27.7, "lo_hz": 196.5, "hi_hz": 6465.7, "decay": 0.0058,
            "gain": 1.2438, "big": 8.8343, "big_gain": 0.247, "body": 0.2639, "fizz": 0.1105, "fizz_rate": 259.8}
UNSHEATHE = {"dur": 0.2407, "scrape": 3.9605, "judder": 212.9, "ring": 1.2881, "end_hit": 0.506, "hiss": 1.3202,
             "hiss_lo": 625.0, "hiss_hi": 3246.0, "hiss_q": 0.7627, "hiss_start": 0.8238}


def noise_burst(start: float, length: float, hz: float, gain: float, kind: str = "high", q: float = 0.7,
                fall: float = 5.0) -> Noise:
    """A decaying noise burst: contact cracks, slices, shimmers."""
    return Noise(round(start, 4), round(max(length, 0.004), 4), [(0.0, hz), (1.0, hz)], kind, q,
                 amp=decay_curve(fall), attack=0.0005, release=0.005, gain=gain)


def swing(fx: Fx, d: dict = SWING, heavy: float = 0.0, edge: bool = True) -> list:
    """Air pushed by a weapon: a low whoosh (most energy under 500 Hz), an edge singing faintly."""
    s, p = fx.size, fx.power
    scale = 2 ** (-0.8 * (s - 0.5) - 0.6 * heavy) * (0.8 + 0.4 * p)
    dur = d["dur"] * (0.8 + 0.6 * s + 0.3 * heavy) * (1.1 - 0.2 * p) * (0.9 + 0.2 * fx.rand("dur"))
    peak = min(max(d["peak"] + 0.15 * (fx.rand("peak") - 0.5), 0.15), 0.85)
    freq = [(0.0, d["f0"] * scale), (round(peak, 3), d["f1"] * scale), (1.0, d["f2"] * scale)]
    amp = bell_curve(peak, d["sharp"])
    out = [Noise(0.0, round(dur, 3), freq, "band", d["q"], amp=amp, attack=0.0, release=0.0, wobble=(20.0, 0.2)),
           Noise(0.0, round(dur, 3), [(t, f * 0.8) for t, f in freq], "low", 0.7, amp=amp, attack=0.0, release=0.0,
                 gain=d["body"])]
    if edge and d["edge"] > 0.01:
        out.append(Noise(0.0, round(dur, 3), [(t, d["edge_hz"] * f / d["f1"]) for t, f in freq], "band", d["edge_q"],
                         amp=bell_curve(peak, d["sharp"] * 1.5), attack=0.0, release=0.0, gain=d["edge"]))
    return out


def blade_body(fx: Fx, material: str, d: dict = CLASH) -> "str | Material":
    """A blade rings high and briefly (the grip damps it); wooden blades are just wood."""
    if material == "wood":
        return "wood"
    m = MATERIALS[material]
    k = {"steel": 1.0, "iron": 0.75, "glass": 1.3}.get(material, 1.0)
    low = d["low"] * k
    return replace(m, low=(low, low * 0.6), high=18_000, t60=(m.t60[0] * d["ring"], m.t60[1] * d["ring"]),
                   damping=d["damp"], radiates=d["radiates"] * k, hardness=16_000)


def clash(fx: Fx, material: str, d: dict = CLASH) -> list:
    p = fx.power
    body = blade_body(fx, material, d)
    lag = d["lag"] * (0.5 + fx.rand("lag"))
    slide = (0.0, d["scrape"] * (0.5 + fx.rand("slide")), d["scrape_gain"] * p, d["judder"])
    a = fx.strike(body, hits=[(0.0, 1.0, 0.0008)], scrape=slide, click=d["click"], prefix="a")
    b = fx.strike(body, start=round(lag, 4), size=min(max(fx.size + 0.3 * (fx.rand("foe") - 0.5), 0), 1),
                  hits=[(0.0, 1.0, 0.0008)], scrape=slide, click=d["click"], gain=d["second"], prefix="b")
    return [a, b, noise_burst(0.0, d["shimmer_len"], d["shimmer_hz"], d["shimmer"], fall=4.0),
            noise_burst(0.0, 0.08, d["thump_hz"], d["thump"], "low", 1.0, 6.0)]


def hit(fx: Fx, weapon: str, target: str, edge: float) -> list:
    """`weapon` (a material) strikes `target`; `edge` 0 (blunt) .. 1 (blade)."""
    p, s = fx.power, fx.size
    if target == "flesh":
        d = FLESH
        out = [noise_burst(0.0, d["thud_len"] * (1 + s), d["thud_hz"] * (1.3 - 0.6 * s), d["thud"], "low", 1.0, 6.0),
               Noise(0.003, round(d["squelch_len"], 3), [(0, d["squelch_hz"]), (1, d["squelch_hz"] * 0.7)], "band",
                     d["squelch_q"], amp=decay_curve(4), attack=0.003, wobble=(40.0, 0.9), gain=d["squelch"]),
               Scatter(0.0, round(0.05 + 0.1 * p, 3), [(0, d["crunch_rate"] * p), (1, 0)], "pop", (400, 4000),
                       (0.0008, 0.003), (0.3, 1.0), d["crunch"] * p)]
        if edge:
            out.append(noise_burst(0.0, d["slice_len"], d["slice_hz"], d["slice"] * edge, fall=4.0))
        return out
    d = HIT[target]
    hard = 0.6 + 0.4 * p
    t_size = 0.55 + 0.2 * (fx.rand("target") - 0.5)
    out = [noise_burst(0.0, d["crack_len"], d["crack_hz"], d["crack"] * hard, "band", 0.5, 6.0),
           fx.strike(target, size=t_size, hits=[(0.0, 1.0, 0.0012 / hard)], ring=d["body_ring"], gain=d["body"],
                     prefix="t"),
           noise_burst(0.0, d["thud_len"] * (1 + s), d["thud_hz"] * (1.3 - 0.6 * s), d["thud"] * (1 - 0.4 * edge),
                       "low", 1.0, 6.0)]
    if weapon in ("steel", "iron", "bronze", "glass"):
        out.append(fx.strike(blade_body(fx, weapon) if edge else weapon, hits=[(0.0, 1.0, 0.001)],
                             ring=d["weapon_ring"], gain=d["weapon"], prefix="w"))
    if target == "stone" and weapon in ("steel", "iron"):  # sparks
        out.append(Scatter(0.0, 0.12, [(0, 120), (1, 0)], "ping", (6000, 11000), (0.004, 0.012), (0.2, 1.0), 0.2))
    return out


@recipe("blade", ("swing", "clash", "hit_flesh", "hit_wood", "hit_metal", "hit_stone", "draw", "drop"),
        ("steel", "iron", "glass", "wood"))
def blade(fx: Fx):
    """Swords, daggers, axes: swing, clash, hits on flesh/wood/armor/stone, draw, drop."""
    mat, e = fx.style, fx.event
    if e == "swing":
        return fx.voice(noise=swing(fx))
    if e == "clash":
        return fx.voice(**splits(clash(fx, mat)), space=0.4, wet=0.08)
    if e in TARGETS:
        return fx.voice(**splits(hit(fx, mat, TARGETS[e], edge=1.0)), space=0.3, wet=0.06)
    if e == "draw":
        d = UNSHEATHE
        dur = d["dur"] * (0.7 + 0.6 * fx.size)
        body = blade_body(fx, mat)
        ring = fx.strike(body, hits=[(dur, d["end_hit"], 0.001)], scrape=(0.0, dur, d["scrape"], d["judder"]),
                         prefix="a", ring=d["ring"] / CLASH["ring"] if mat != "wood" else 1.0,
                         dur=dur + (0.6 if mat != "wood" else 0.1))
        hiss = Noise(0.0, round(dur, 3), [(0, d["hiss_lo"]), (1, d["hiss_hi"])], "band", d["hiss_q"],
                     amp=[(0, d["hiss_start"]), (0.85, 1), (1, 0)], attack=0.03, release=0.02, gain=d["hiss"])
        return fx.voice(modal=[ring], noise=[hiss])
    # drop: falls, bounces and clatters on stone, the floor muffling its ring
    hits = bounces(fx, 6, 0.2, 0.5, 3)
    ground = fx.strike("stone", size=0.75, hits=hits, gain=1.0, prefix="g")
    return fx.voice(modal=[fx.strike(blade_body(fx, mat), hits=hits, prefix="a", dur=1.0, click=1.0), ground])


@recipe("blunt", ("swing", "hit_flesh", "hit_wood", "hit_metal", "hit_stone", "drop"), ("wood", "iron", "stone"))
def blunt(fx: Fx):
    """Clubs, maces, hammers, staves: heavy swings and hits."""
    mat, e = fx.style, fx.event
    if e == "swing":
        return fx.voice(noise=swing(fx, heavy=0.5, edge=False))
    if e in TARGETS:
        return fx.voice(**splits(hit(fx, mat, TARGETS[e], edge=0.0)), space=0.3, wet=0.06)
    hits = bounces(fx, 4, 0.14, 0.5)
    return fx.voice(modal=[fx.strike(mat, hits=hits, prefix="a", dur=1.0, ring=0.5),
                           fx.strike("stone", size=0.6, hits=hits, gain=0.8, prefix="g")])


def bow_draw(fx: Fx, d: dict = BOW_DRAW) -> list:
    """Drawing a bow: wood and string creak in irregular clicks, a few of them loud and woody."""
    dur = d["dur"] * (0.8 + 0.4 * fx.size)
    n_big = max(int(d["big"] * dur), 1)
    big = sorted((round(dur * (0.15 + 0.8 * fx.rand(f"big{k}")), 4), round(0.5 + 0.5 * fx.rand(f"bg{k}"), 3), 0.0008)
                 for k in range(n_big))
    return [Scatter(0.0, round(dur, 3), [(0, d["rate"]), (1, d["rate_end"])], "pop", (d["lo_hz"], d["hi_hz"]),
                    (d["decay"] / 2, d["decay"] * 2), (0.1, 1.0), d["gain"]),
            Scatter(0.0, round(dur, 3), [(0, d["fizz_rate"]), (1, d["fizz_rate"] * 0.6)], "pop", (1500, 12_000),
                    (0.0003, 0.001), (0.05, 0.4), d["fizz"]),      # the string stretching: dense faint ticks
            fx.strike("wood", size=0.35, hits=big, ring=0.6, gain=d["big_gain"], prefix="limb"),
            *[noise_burst(t, 0.006, 2500, d["big_gain"] * g * d["body"], "high", 0.6, 6.0) for t, g, _ in big]]


def bow_release(fx: Fx, d: dict = RELEASE, cross: bool = False) -> list:
    """Letting go: a rising rush as the string drives the arrow, a sharp slap, the limbs' low thump."""
    t = d["swell"] * (0.6 if cross else 1.0) * (0.85 + 0.3 * fx.rand("swell"))
    return [noise_burst(0.0, 0.012, 3000, d["nock"], "high", 0.6, 6.0),     # the nock leaves the fingers
            Noise(0.0, round(t + 0.01, 4), [(0, d["swell_f0"]), (1, d["swell_f1"])], "band", d["swell_q"],
                  amp=[(0, 0.0), (0.7, 0.4), (1, 1.0)], attack=0.0, release=0.005, gain=d["swell_gain"]),
            noise_burst(t, d["crack_len"], d["crack_hz"], d["crack"], "band", 0.5, 6.0),
            fx.strike("string", start=round(t, 4), size=0.4 + 0.5 * fx.size, hits=[(0.0, 1.0, 0.002)],
                      ring=d["string_ring"], gain=d["string"], prefix="s", dur=0.4),
            noise_burst(t, d["thump_len"], d["thump_hz"], d["thump"], "low", 1.0, 5.0)]


def arrow_hit(fx: Fx, target: str, d: dict = ARROW_HIT) -> list:
    """An arrow strikes: a sharp crack, the target's body, then the shaft quivering in fast clicks."""
    out = [noise_burst(0.0, d["crack_len"], d["crack_hz"], d["crack"], "band", 0.5, 6.0),
           fx.strike(target, size=0.5, hits=[(0.0, 1.0, 0.0012)], ring=d["body_ring"], gain=d["body"], prefix="t"),
           noise_burst(0.0, 0.06, d["thud_hz"], d["thud"], "low", 1.0, 6.0)]
    if target == "wood":
        rate = d["quiver_rate"] * (0.85 + 0.3 * fx.rand("quiver"))
        n = max(int(d["quiver_len"] * rate), 2)
        clicks = [(round((k + 1) / rate, 4), round(0.8 ** k, 3), 0.0006) for k in range(n)]
        out.append(fx.strike("wood", size=d["quiver_size"], hits=clicks, ring=0.3, gain=d["quiver"], prefix="shaft",
                             dur=d["quiver_len"] + 0.2))
    else:  # it breaks
        out.append(fx.strike("wood", size=0.1, hits=[(0.01, 0.8, 0.001)], gain=0.6, prefix="snap"))
    return out


@recipe("bow", ("draw", "release", "fly", "hit_wood", "hit_flesh", "hit_stone"), ("longbow", "crossbow"))
def bow(fx: Fx):
    """Bows and crossbows: draw, release, the arrow's flight and where it lands."""
    e, cross = fx.event, fx.style == "crossbow"
    if e == "draw":
        if cross:  # a ratchet: regular clicks, then the latch
            dur = 0.5 + 0.5 * fx.size
            clicks = [(round(i / 11 + 0.004 * fx.rand(f"c{i}"), 4), 0.8, 0.0006) for i in range(int(dur * 11))]
            return fx.voice(modal=[fx.strike("iron", size=0.05, hits=clicks, prefix="pawl", dur=dur + 0.2, ring=0.4),
                                   fx.strike("wood", size=0.3, hits=[(dur, 1.0, 0.002)], prefix="lock")])
        return fx.voice(**splits(bow_draw(fx)), gain=0.7)
    if e == "release":
        layers = bow_release(fx, cross=cross)
        if cross:
            layers.append(fx.strike("iron", size=0.1, hits=[(0.0, 1.0, 0.0006)], gain=0.6, prefix="click", ring=0.4))
        return fx.voice(**splits(layers))
    if e == "fly":
        return fx.voice(noise=swing(fx, FLY, edge=True))
    target = TARGETS[e]
    if target == "flesh":
        return fx.voice(**splits(hit(fx, "wood", "flesh", edge=0.6)))
    return fx.voice(**splits(arrow_hit(fx, target)), space=0.3, wet=0.08)


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
