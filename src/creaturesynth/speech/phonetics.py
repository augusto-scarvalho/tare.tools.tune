"""Phrases of phones -> frame tracks for the formant synthesiser ("synthesis by rule").

Each phone has acoustic targets (formants, voicing, frication spectrum) and a duration.
The timeline is laid out on a 1 ms grid, formant targets are smoothed so neighbouring
sounds coarticulate (the transitions carry most of the consonant cues), and an intonation
model draws the pitch. Formant values are for an adult with a long vocal tract; the
speaker's `tract` factor scales them.

Levels, timings and the regional choices below were tuned by ear-proxy: Whisper transcribing
the output (tools/intelligibility.py), A/B against a fixed set of game-dialogue sentences.
"""
from dataclasses import dataclass, field

import numpy as np

from .units import Phrase, is_vowel

FRAME_RATE = 400.0     # frames per second in the spec (2.5 ms)
GRID = 1000            # internal resolution, points per second
NASAL_POLE = 270.0
FORMANT_MS = 28        # coarticulation smoothing of formant targets
GLIDE_MS = 80          # glides/liquids glide slowly (w vs m)
FRIC_RISE_MS = 14      # fricatives fade in; bursts stay sharp
OBSTRUENT_DAMPING = (80, 400, 500)
VOICED_FRIC_AV = 0.3
VOT = {"pt": 0.016, "en": 0.025, "en_stressed": 0.055}   # voiceless stop aspiration, seconds
VELAR_VOT = 1.8        # velars release slower than labials/alveolars (multiplier)
STOP_ASPIRATION = 0.3
BURST_SCALE = 0.4      # bursts relative to the frication gain (fricatives need more level than bursts)
R_STYLE = "x"          # pt strong r (rato, carro): "x" velar fricative or "h" glottal (regional accents)
PT_STRESS = (1.35, 0.8, 0.7)     # pt vowel duration: stressed, unstressed, reduced final (A/B-tuned)
NASAL_DAMPING = (80, 200, 300)


@dataclass(frozen=True)
class Phone:
    kind: str                                 # vowel glide liquid tap nasal stop affricate fric h
    dur: float                                # ms
    F: tuple[float, float, float] = (500, 1500, 2500)   # formants, or locus for obstruents
    voiced: bool = True
    av: float = 1.0                           # voicing amplitude in the steady part
    af: float = 0.0                           # frication amplitude
    fric: tuple = ()                          # ((Hz, bandwidth, gain), ...) frication / burst spectrum
    ab: float = 0.0                           # flat (bypass) frication
    nasal: float = 0.0                        # 0 oral .. 1 full nasal murmur
    place: str = ""                           # lab alv pal vel dent glot


def _v(f1, f2, f3, dur, nasal=0.0):
    return Phone("vowel", dur, (f1, f2, f3), nasal=nasal)


S_SPEC = ((5200, 1000, 0.55), (7000, 1800, 1.0))
SH_SPEC = ((2700, 500, 0.8), (4000, 1200, 1.0))
F_SPEC = ((7500, 3000, 0.35),)

PHONES: dict[str, Phone] = {
    # vowels (pt + en)
    "i": _v(290, 2250, 2950, 110), "I": _v(390, 1990, 2600, 70), "e": _v(400, 2050, 2650, 110),
    "E": _v(560, 1800, 2550, 100), "{": _v(650, 1750, 2500, 130), "a": _v(720, 1300, 2550, 120),
    "A": _v(750, 1150, 2550, 120), "6": _v(560, 1350, 2550, 80), "V": _v(620, 1200, 2550, 85),
    "@": _v(500, 1450, 2500, 55), "3`": _v(470, 1350, 1700, 110), "O": _v(580, 900, 2450, 115),
    "o": _v(420, 850, 2400, 110), "U": _v(410, 1050, 2400, 70), "u": _v(310, 800, 2300, 105),
    "6~": _v(600, 1350, 2600, 130, 0.7), "e~": _v(420, 1950, 2650, 125, 0.7), "i~": _v(290, 2200, 2950, 120, 0.7),
    "o~": _v(430, 880, 2400, 125, 0.7), "u~": _v(320, 800, 2300, 120, 0.7),
    # glides and liquids
    "j": Phone("glide", 60, (260, 2250, 3000), av=0.85), "w": Phone("glide", 60, (290, 620, 2300), av=0.85),
    "j~": Phone("glide", 60, (280, 2150, 2950), av=0.85, nasal=0.7),
    "w~": Phone("glide", 60, (320, 700, 2300), av=0.85, nasal=0.7),
    "l": Phone("liquid", 60, (360, 1150, 2700), av=0.8, place="alv"),
    "L": Phone("liquid", 75, (300, 2100, 2900), av=0.8, place="pal"),
    "r\\": Phone("liquid", 65, (350, 1150, 1600), av=0.85, place="alv"),
    "r": Phone("tap", 25, (300, 1650, 2450), av=0.25, place="alv"),
    # nasals
    "m": Phone("nasal", 70, (250, 1000, 2200), av=0.7, nasal=1.0, place="lab"),
    "n": Phone("nasal", 65, (250, 1550, 2650), av=0.7, nasal=1.0, place="alv"),
    "J": Phone("nasal", 80, (250, 2050, 2850), av=0.7, nasal=1.0, place="pal"),
    "N": Phone("nasal", 70, (250, 1900, 2500), av=0.7, nasal=1.0, place="vel"),
    # stops: F is the locus; the burst spectrum is in `fric`
    "p": Phone("stop", 75, (200, 900, 2200), voiced=False, af=0.25, ab=1.0, place="lab"),
    "b": Phone("stop", 60, (200, 900, 2200), af=0.18, ab=1.0, place="lab"),
    "t": Phone("stop", 70, (200, 1700, 2650), voiced=False, af=0.6, fric=((4500, 1500, 1.0), (3000, 1000, 0.4)),
               place="alv"),
    "d": Phone("stop", 55, (200, 1700, 2650), af=0.4, fric=((4500, 1500, 1.0), (3000, 1000, 0.4)), place="alv"),
    "k": Phone("stop", 75, (200, 1800, 2500), voiced=False, af=1.1, fric=((2000, 500, 1.0), (3000, 800, 0.3)),
               place="vel"),
    "g": Phone("stop", 60, (200, 1800, 2500), af=0.75, fric=((2000, 500, 1.0), (3000, 800, 0.3)), place="vel"),
    "tS": Phone("affricate", 100, (200, 2100, 2800), voiced=False, af=0.55, fric=SH_SPEC, place="pal"),
    "dZ": Phone("affricate", 85, (200, 2100, 2800), af=0.4, fric=SH_SPEC, place="pal"),
    # fricatives
    "s": Phone("fric", 95, (300, 1700, 2650), voiced=False, af=0.5, fric=S_SPEC, place="alv"),
    "z": Phone("fric", 70, (250, 1700, 2650), af=0.35, fric=S_SPEC, place="alv"),
    "S": Phone("fric", 95, (300, 2100, 2800), voiced=False, af=0.6, fric=SH_SPEC, place="pal"),
    "Z": Phone("fric", 70, (250, 2100, 2800), af=0.4, fric=SH_SPEC, place="pal"),
    "f": Phone("fric", 90, (300, 1000, 2200), voiced=False, af=0.15, ab=0.8, fric=F_SPEC, place="lab"),
    "v": Phone("fric", 70, (250, 1000, 2200), af=0.45, ab=0.8, fric=F_SPEC, place="lab"),
    "T": Phone("fric", 85, (300, 1500, 2600), voiced=False, af=0.14, ab=0.6, fric=F_SPEC, place="dent"),
    "D": Phone("fric", 50, (250, 1500, 2600), af=0.08, ab=0.6, fric=F_SPEC, place="dent"),
    "h": Phone("h", 65, voiced=False, place="glot"),
    "R": Phone("h", 80, voiced=False, place="glot"),
}
PAUSES = {",": 0.18, ".": 0.38, "!": 0.38, "?": 0.38}

# Per-language adjustments on top of PHONES: {lang: {phone: {field: value}}}
LANG_PHONES: dict[str, dict[str, dict]] = {"pt": {}}
R_FRIC_HZ = 1700.0     # pt strong r [x]: upper limit of its frication centre


def phone_table(lang: str) -> dict[str, Phone]:
    from dataclasses import replace
    table = dict(PHONES)
    for ph, changes in LANG_PHONES.get(lang, {}).items():
        table[ph] = replace(table[ph], **changes)
    return table
NASAL_ZERO = {"m": 450, "n": 450, "J": 450, "N": 450}     # nasal murmur antiresonance (A/B-tuned)
NASAL_VOWEL_ZERO = 600
HOMORGANIC_NASAL = {"p": "m", "b": "m", "t": "n", "d": "n", "tS": "n", "dZ": "n", "k": "N", "g": "N"}


@dataclass
class _Seg:
    phone: str
    dur: float                      # seconds
    F: tuple
    av: float = 0.0
    ah: float = 0.0
    af: float = 0.0
    ab: float = 0.0
    fric: tuple = ()
    nasal: float = 0.0
    fnz: float = NASAL_POLE         # nasal antiresonance; equal to the pole = oral sound
    B: tuple = ()
    vowel_of: int = -1              # syllable index when this segment is the syllable's nucleus
    burst: bool = False             # stop release: keep its edges sharp
    meta: dict = field(default_factory=dict)


def _bandwidths(F, kind=""):
    if kind == "nasal" and NASAL_DAMPING:  # the murmur: a strong low resonance, damped upper formants
        return NASAL_DAMPING
    if kind in ("stop", "affricate", "fric") and OBSTRUENT_DAMPING:  # voice bar: only F1 rings
        return OBSTRUENT_DAMPING
    return (60 + 0.05 * F[0], 70 + 0.03 * F[1], 110 + 0.03 * F[2])


def _velar_locus(next_vowel):
    """Velar pinch: F2 and F3 meet just above the next vowel's F2."""
    f2 = min(max((next_vowel.F[1] if next_vowel else 1500) * 1.1 + 200, 1100), 2500)
    return (200, f2, max(next_vowel.F[2] if next_vowel else 2500, f2 + 450))


def segments(phrases: list[Phrase], lang: str, rate: float = 1.0) -> tuple[list[_Seg], list[dict]]:
    """Lay out segments; also return per-syllable info for the intonation model."""
    segs: list[_Seg] = [_Seg("_", 0.03, (500, 1500, 2500))]
    sylls: list[dict] = []
    table = phone_table(lang)
    where: list = [None, 0]           # the phone being laid out and its first segment: segments get word positions

    def mark(info=None):
        if where[0] is not None:
            for seg in segs[where[1]:]:
                seg.meta.update(where[0])
        where[0], where[1] = info, len(segs)

    for pi, phrase in enumerate(phrases):
        flat = [(w, si, s) for w in phrase.words for si, s in enumerate(w.syllables)]
        for fi, (word, si, syl) in enumerate(flat):
            last_syl = fi == len(flat) - 1
            stressed = syl.stressed and not word.clitic
            info = {"phrase": pi, "kind": phrase.kind, "wh": phrase.wh, "accent": stressed, "last": last_syl}
            sylls.append(info)
            phones = syl.phones
            for k, ph in enumerate(phones):
                mark({"word_initial": si == 0 and k == 0, "word_final": si == len(word.syllables) - 1
                      and k == len(phones) - 1, "syllable": len(sylls) - 1})
                spec = table.get(ph)
                if spec is None:
                    continue
                prev = phones[k - 1] if k else (flat[fi - 1][2].phones[-1] if fi else None)
                nxt_v = next((table[p] for p in phones[k + 1:] if is_vowel(p)), None)
                if nxt_v is None and fi + 1 < len(flat):
                    nxt_v = next((table[p] for p in flat[fi + 1][2].phones if is_vowel(p)), None)
                scale = 1.0
                if spec.kind == "vowel":
                    if lang == "pt":
                        scale = PT_STRESS[0] if stressed else (PT_STRESS[2] if ph in ("I", "U", "6") else PT_STRESS[1])
                    else:
                        scale = 1.35 if stressed else (1.0 if ph == "@" else 0.8)
                    if last_syl:
                        scale *= 1.45
                    if word.clitic:
                        scale *= 0.85
                elif last_syl and k > syl.nucleus:
                    scale = 1.2
                dur = spec.dur * scale / 1000 / rate
                F = _velar_locus(nxt_v) if spec.place == "vel" and spec.kind == "stop" else spec.F
                if spec.kind in ("vowel", "glide", "liquid", "tap", "nasal"):
                    if ph == "l" and lang == "en" and k > syl.nucleus:
                        F = (450, 900, 2600)  # dark l in the coda
                    if spec.kind == "glide" and k == 0 and fi == 0:
                        dur *= 1.5            # phrase-initial w/j: slow onset, or it sounds like m/n
                    seg = _Seg(ph, dur, F, av=spec.av, nasal=spec.nasal)
                    if spec.kind == "glide" and k == 0 and fi == 0:
                        seg.av = 0.4
                    if spec.kind == "nasal":
                        seg.fnz = NASAL_ZERO[ph]
                    elif spec.nasal:
                        seg.fnz = NASAL_POLE + (NASAL_VOWEL_ZERO - NASAL_POLE) * spec.nasal
                    if spec.kind == "vowel":
                        seg.vowel_of = len(sylls) - 1
                    segs.append(seg)
                    # pt nasal vowel before a stop: a short homorganic nasal (ponte -> pon-tchi)
                    nxt_ph = phones[k + 1] if k + 1 < len(phones) else (
                        flat[fi + 1][2].phones[0] if fi + 1 < len(flat) and flat[fi + 1][0] is word else None)
                    if lang == "pt" and spec.kind == "vowel" and spec.nasal and nxt_ph in HOMORGANIC_NASAL:
                        nas = HOMORGANIC_NASAL[nxt_ph]
                        segs.append(_Seg(nas, 0.04 / rate, table[nas].F, av=0.6, nasal=1.0, fnz=NASAL_ZERO[nas]))
                elif spec.kind == "h":
                    target = nxt_v.F if nxt_v else segs[-1].F
                    if ph == "R" and R_STYLE == "h":
                        segs.append(_Seg(ph, dur, target, ah=0.9))
                    elif ph == "R":  # pt strong r as a velar fricative [x]: noise at the next vowel's F2/F3
                        f2 = min(target[1] * 0.8 + 300, R_FRIC_HZ)  # much higher would sound like "ch"
                        segs.append(_Seg(ph, dur, target, ah=0.4, af=0.3, fric=((f2, 700, 1.0), (target[2], 900, 0.4))))
                    else:
                        segs.append(_Seg(ph, dur, target, ah=0.6))
                elif spec.kind == "fric":
                    av = (0.2 if ph == "v" else VOICED_FRIC_AV) if spec.voiced else 0.0
                    segs.append(_Seg(ph, dur, F, av=av, af=spec.af, ab=spec.ab, fric=spec.fric))
                else:  # stops and affricates: closure, release, aspiration/frication
                    closure = dur * (0.55 if spec.kind == "affricate" else 1.0)
                    segs.append(_Seg(ph, closure, F, av=0.3 if spec.voiced else 0.0))
                    if spec.kind == "affricate":
                        segs.append(_Seg(ph, dur * 0.6, F, av=0.4 if spec.voiced else 0.0, af=spec.af,
                                         fric=spec.fric))
                        continue
                    fric = spec.fric
                    if spec.place == "vel":  # compact burst right at the pinched F2/F3
                        fric = ((F[1] * 1.05, 450, 1.0), (F[2] * 1.1, 700, 0.35))
                    segs.append(_Seg(ph, 0.016 if spec.place == "vel" else 0.008, F, av=0.3 if spec.voiced else 0.0,
                                     af=spec.af * BURST_SCALE, ab=spec.ab, fric=fric, burst=True))
                    if not spec.voiced:
                        onset_of_stressed = k < syl.nucleus and stressed and prev != "s"
                        vot = VOT["en_stressed"] if lang == "en" and onset_of_stressed else VOT[lang]
                        if spec.place == "vel":
                            vot *= VELAR_VOT
                        mid = tuple((a + b) / 2 for a, b in zip(F, nxt_v.F if nxt_v else F, strict=True))
                        segs.append(_Seg(ph, vot / rate, mid, ah=STOP_ASPIRATION))
        mark()
        segs.append(_Seg("_", PAUSES[phrase.kind] / rate if pi < len(phrases) - 1 else 0.08, segs[-1].F))
    for s in segs:
        s.B = _bandwidths(s.F, PHONES[s.phone].kind if s.phone in PHONES else "")
    return segs, sylls


def _smooth(x: np.ndarray, ms: float) -> np.ndarray:
    n = max(int(ms * GRID / 1000), 1)
    if n < 2:
        return x
    w = np.hanning(n + 2)[1:-1]
    w /= w.sum()
    pad = np.concatenate([np.full(n, x[0]), x, np.full(n, x[-1])])
    return np.convolve(pad, w, mode="same")[n:-n]


def _intonation(segs: list[_Seg], sylls: list[dict], t: np.ndarray, pitch: float, rng_: float, lang: str,
                melody: list[float] | None = None):
    """Pitch keypoints per syllable nucleus -> smooth f0 curve over the grid."""
    starts = np.cumsum([0.0] + [s.dur for s in segs])
    nuclei = {s.vowel_of: (starts[i], starts[i + 1]) for i, s in enumerate(segs) if s.vowel_of >= 0}
    xs, ys = [0.0], [pitch]
    by_phrase: dict[int, list[int]] = {}
    for i, info in enumerate(sylls):
        if i in nuclei:
            by_phrase.setdefault(info["phrase"], []).append(i)
    R = rng_
    for idx in by_phrase.values():
        t0, t1 = nuclei[idx[0]][0], nuclei[idx[-1]][1]
        span = max(t1 - t0, 1e-3)
        accents = [i for i in idx if sylls[i]["accent"]] or [idx[-1]]
        nuclear = accents[-1]
        kind = sylls[idx[0]]["kind"]
        if kind == "?" and sylls[idx[0]]["wh"]:
            kind = "."
        nuclear_end = pitch
        for i in idx:
            a, b = nuclei[i]
            base = pitch * (1.08 - 0.18 * (a - t0) / span)
            if i < nuclear:
                if i in accents:
                    pts = [(a, base * (1 + 0.08 * R)), (b, base * (1 + 0.22 * R))]
                else:
                    pts = [(a, base), (b, base)]
            elif i == nuclear:
                pts = {
                    ".": [(a, base * (1 + 0.24 * R)), (b, base * (1 - 0.04 * R))],
                    "!": [(a, base * (1 + 0.42 * R)), (b, base * (1 + 0.05 * R))],
                    ",": [(a, base * (1 + 0.12 * R)), (b, base * (1 + 0.1 * R))],
                    "?": ([(a, base * (1 + 0.1 * R)), (b, pitch * (1 + 0.5 * R))] if lang == "pt"
                          else [(a, base * (1 - 0.05 * R)), (b, base * (1 + 0.25 * R))]),
                }[kind]
                nuclear_end = pts[-1][1]
            else:  # after the nucleus: fall for statements, keep rising for English questions
                frac = (b - nuclei[nuclear][1]) / max(t1 - nuclei[nuclear][1], 1e-3)
                end = {".": 1 - 0.24 * R, "!": 1 - 0.2 * R, ",": 1 + 0.15 * R,
                       "?": (1 + 0.2 * R) if lang == "pt" else (1 + 0.55 * R)}[kind]
                v = nuclear_end + (pitch * end - nuclear_end) * frac
                pts = [(a, v), (b, v)]
            if melody is not None:  # babble: one note per syllable on top of the contour
                pts = [(x, y * 2 ** (melody[i % len(melody)] / 12)) for x, y in pts]
            xs += [p[0] for p in pts]
            ys += [p[1] for p in pts]
    xs.append(starts[-1])
    ys.append(ys[-1])
    order = np.argsort(xs, kind="stable")
    f0 = np.interp(t, np.asarray(xs)[order], np.asarray(ys)[order])
    return _smooth(f0, 60)


def frames(phrases: list[Phrase], lang: str, pitch: float = 120.0, tract: float = 1.0, range_: float = 1.0,
           rate: float = 1.0, breath: float = 0.05, melody: list[float] | None = None) -> dict[str, list[float]]:
    """Frame tracks at FRAME_RATE for the formant synthesiser."""
    segs, sylls = segments(phrases, lang, rate)
    starts = np.cumsum([0.0] + [s.dur for s in segs])
    n = int(starts[-1] * GRID) + 1
    t = np.arange(n) / GRID
    idx = np.clip(np.searchsorted(starts, t, side="right") - 1, 0, len(segs) - 1)

    def col(get):
        return np.array([get(s) for s in segs], dtype=float)[idx]

    tracks = {}
    slow = _smooth(col(lambda s: 1.0 if PHONES.get(s.phone, PHONES["@"]).kind in ("glide", "liquid") else 0.0), 40)
    for j in range(3):
        target = col(lambda s, j=j: s.F[j])
        tracks[f"f{j + 1}"] = (_smooth(target, FORMANT_MS) * (1 - slow) + _smooth(target, GLIDE_MS) * slow) * tract
        tracks[f"b{j + 1}"] = _smooth(col(lambda s, j=j: s.B[j]), 10) * tract ** 0.5
    is_nasal = _smooth(col(lambda s: 1.0 if s.fnz > 1.5 * NASAL_POLE else 0.0), 4)
    # nasal release: F1 jumps instead of gliding
    raw_f1 = _smooth(col(lambda s: s.F[0]), 6) * tract
    raw_b1 = _smooth(col(lambda s: s.B[0]), 4) * tract ** 0.5
    tracks["f1"] = tracks["f1"] * (1 - is_nasal) + raw_f1 * is_nasal
    tracks["b1"] = tracks["b1"] * (1 - is_nasal) + raw_b1 * is_nasal
    tracks["f4"] = np.full(n, 3500.0 * tract)
    tracks["f5"] = np.full(n, 4500.0 * tract)
    tracks["b4"] = np.full(n, 250.0 * tract ** 0.5)
    tracks["b5"] = np.full(n, 300.0 * tract ** 0.5)
    nasal = _smooth(col(lambda s: s.nasal), 8)
    tracks["fnp"] = np.full(n, NASAL_POLE * tract)
    tracks["fnz"] = _smooth(col(lambda s: s.fnz), 8) * tract  # zero leaves the pole: nasal resonance
    tracks["b1"] = tracks["b1"] * (1 + 0.8 * nasal)
    av = _smooth(col(lambda s: s.av), 6)
    tracks["av"] = av
    tracks["ah"] = _smooth(col(lambda s: s.ah), 6) + breath * av
    tracks["af"] = (_smooth(col(lambda s: 0.0 if s.burst else s.af), FRIC_RISE_MS)
                    + _smooth(col(lambda s: s.af if s.burst else 0.0), 2))
    tracks["ab"] = col(lambda s: s.ab)
    for name, j, default in (("fa", 0, 3000), ("wa", 1, 1000), ("ga", 2, 0.0)):
        tracks[name] = col(lambda s, j=j, d=default: s.fric[0][j] if s.fric else d) * (tract if j < 2 else 1)
    for name, j, default in (("fb", 0, 5000), ("wb", 1, 1500), ("gb", 2, 0.0)):
        tracks[name] = col(lambda s, j=j, d=default: s.fric[1][j] if len(s.fric) > 1 else d) * (tract if j < 2 else 1)
    tracks["f0"] = _intonation(segs, sylls, t, pitch, range_, lang, melody)

    step = GRID / FRAME_RATE
    picks = np.arange(0, n, step)
    out = {}
    for name, arr in tracks.items():
        v = np.interp(picks, np.arange(n), arr)
        out[name] = [round(float(x), 1 if name[0] in "fbw" else 4) for x in v]
    return out
