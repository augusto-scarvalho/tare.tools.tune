"""Wordless voice clips for games (barks): combat efforts, pain, death, laughs, sighs, surprise, "hmm"...

Many games are not fully voiced: their characters say a short "hyah!", "ugh", "hm?" or a laugh, in their own voice,
and the text carries the rest. These are built straight as formant-synthesiser frames from a speaker's voice (its
pitch, tract, breathiness, roughness), so every NPC barks in the voice it talks with.

Measured on CC0 recordings (OpenGameArt "RPG Male Adventurer", "Female RPG Voice Starter Pack" (three voices),
"Male Grunt/Yelling sounds"; Freesound CC0 laughs, giggles, sighs, gasps, "hmm", "huh", "yay"; analysis only):
- an attack shout lasts 0.15-0.35 s, opens on breath (50-190 ms to the peak), is mostly air (voiced 10-60%),
  bright, and is pitched far above the speaking voice: men +17 to +23 semitones (95 Hz -> 250-380 Hz), women about
  +10; it holds level and falls at the end. A big attack can strain low first, then jump up and climb.
- pain: 0.2-0.4 s, a fast onset, rising then falling (+1.5 to +3 semitones, peak at 30-80%);
- death: 1-2 s, mostly voiced (80-95%), high, falling slowly;
- jump: 0.17-0.3 s, a short "hup", less pitch rise;
- laughs pulse 4.5-5 times a second (men), 5-6 (women), giggles 6-8, chuckles 5-6, mostly breath;
- a sigh is breath (voiced 0-50%), dark, falling 2.5-3.5 semitones; a "hmm" is nasal, dark, 0.9-2.8 s, rising
  ~4 semitones when it doubts; "huh" rises 2-3 semitones; "yay" starts 2-3 semitones high and falls.

Styles, after the games that use these clips (the clips themselves are original):
    grunt     wordless and breathy, short and quick (Zelda's hero)
    anime     bright, voiced, cute syllables: "ya!", "kya!", "e?!", "fufu" (Rune Factory)
    tactics   restrained and pressed: "hmph", "hah", "heh" (Fire Emblem)
    mmo       full shouts, longer and stronger: "haaah!", "ugh!" (Final Fantasy XIV)
"""
from dataclasses import dataclass

import numpy as np

from .. import rng
from ..spec import SpeechProgram
from .phonetics import F_SPEC, FRAME_RATE, NASAL_POLE, NASAL_ZERO, PHONES, S_SPEC

EMOTES = ("attack", "attack_big", "hurt", "hurt_big", "death", "jump", "tired", "laugh", "giggle", "chuckle",
          "sigh", "gasp", "surprise", "hmm", "huh", "yes", "no", "cheer", "relief", "angry")
STYLES = ("grunt", "anime", "tactics", "mmo")
# how far the voice goes towards its shouting register, how breathy, how long, per style
STYLE = {
    "grunt": dict(effort=0.85, air=1.4, length=0.85, bright=1.0),
    "anime": dict(effort=0.9, air=0.6, length=1.0, bright=1.35),
    "tactics": dict(effort=0.7, air=1.0, length=0.9, bright=0.85),
    "mmo": dict(effort=0.92, air=0.9, length=1.25, bright=1.15),
}


@dataclass
class Seg:
    """A stretch of one sound: `ph` gives the formants (a vowel, "m"/"n" for a hum, "h" breathes through the next
    vowel, "s"/"f" hiss, "k"/"p" burst); f0 in semitones over the base pitch, av voicing, ah breath (point lists)."""
    dur: float
    ph: str = "a"
    f0: tuple = (0.0,)
    av: tuple = (1.0,)
    ah: tuple = (0.1,)
    af: tuple = (0.0,)


def shout_pitch(pitch: float, tract: float, effort: float) -> float:
    """The pitch of an effortful voice: from the speaking pitch towards a shouting register that depends on the tract
    (~420 Hz for an adult male tract, higher for shorter ones). Fitted on the recordings: a 95 Hz man shouts at
    ~345 Hz (+22 st), women speaking at 230 / 280 / 550 Hz at ~430 / 530 / 600 Hz."""
    register = 420.0 * tract ** 1.8
    return pitch ** (1 - effort) * max(register, pitch * 1.3) ** effort


class _R:
    def __init__(self, *key):
        self.k, self.i = rng.key(*key), 0

    def u(self) -> float:
        self.i += 1
        return rng.uniform(rng.key(self.k, self.i))

    def pick(self, items):
        return items[int(self.u() * len(items)) % len(items)]


def _curve(points, n: int) -> np.ndarray:
    pts = list(points)
    if len(pts) == 1:
        return np.full(n, float(pts[0]))
    return np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(pts)), pts)


def _smooth(x: np.ndarray, frames: int) -> np.ndarray:
    if frames <= 1:
        return x
    k = np.ones(frames) / frames
    return np.convolve(np.pad(x, (frames // 2, frames - 1 - frames // 2), mode="edge"), k, mode="valid")


HUM = (400, 1400, 2600)   # a hummed "mm": a closed tract is far darker than a recorded hum, so a little opened


def build(segs: list[Seg], base: float, tract: float, breath: float, open_: float = 0.0) -> dict[str, list[float]]:
    """Frame tracks for the formant synthesiser from segments. `open_` (0..1): a shouting mouth, F1 up to +25%."""
    cols: dict[str, list[np.ndarray]] = {k: [] for k in ("f0", "av", "ah", "af", "f1", "f2", "f3", "fnz", "fa", "wa",
                                                          "ga", "fb", "wb", "gb", "ab")}
    for i, s in enumerate(segs):
        n = max(int(round(s.dur * FRAME_RATE)), 2)
        ph = s.ph
        if ph == "h":     # breath shaped by the vowel that follows
            ph = next((t.ph for t in segs[i + 1:] if t.ph in PHONES and PHONES[t.ph].kind == "vowel"), "a")
        p = PHONES.get(ph, PHONES["a"])
        F = HUM if ph in ("m", "n") else p.F if p.kind in ("vowel", "glide", "liquid") else PHONES["@"].F
        cols["f0"].append(base * 2 ** (_curve(s.f0, n) / 12))
        cols["av"].append(_curve(s.av, n))
        cols["ah"].append(_curve(s.ah, n) + breath * _curve(s.av, n))
        cols["af"].append(_curve(s.af, n))
        for j in range(3):
            lift = 1 + 0.25 * open_ if j == 0 and p.kind == "vowel" else 1.0
            cols[f"f{j + 1}"].append(np.full(n, F[j] * tract * lift))
        cols["fnz"].append(np.full(n, (NASAL_ZERO.get(ph, NASAL_POLE)) * tract))
        fric = {"s": S_SPEC, "f": F_SPEC, "k": ((2000, 500, 1.0), (3000, 800, 0.3)),
                "p": ((1500, 2000, 0.6), (4000, 3000, 0.4))}.get(s.ph, ((3000, 1000, 0.0), (5000, 1500, 0.0)))
        fric = list(fric) + [(5000, 1500, 0.0)] * (2 - len(fric))
        for name, val in (("fa", fric[0][0] * tract), ("wa", fric[0][1]), ("ga", fric[0][2]),
                          ("fb", fric[1][0] * tract), ("wb", fric[1][1]), ("gb", fric[1][2]),
                          ("ab", 0.8 if s.ph in ("f", "p") else 0.0)):
            cols[name].append(np.full(n, val))
    tr = {k: np.concatenate(v) for k, v in cols.items()}
    for k in ("f1", "f2", "f3", "fnz"):
        tr[k] = _smooth(tr[k], 8)                       # 20 ms coarticulation between segments
    for k in ("av", "ah", "af"):
        tr[k] = _smooth(tr[k], 2)
    tr["f0"] = _smooth(tr["f0"], 6)
    n = len(tr["f0"])
    tr["b1"] = 60 + 0.05 * tr["f1"]
    tr["b2"] = 70 + 0.03 * tr["f2"]
    tr["b3"] = 110 + 0.03 * tr["f3"]
    nasal = tr["fnz"] > NASAL_POLE * tract * 1.2
    tr["b1"] = np.where(nasal, 80 * tract ** 0.5, tr["b1"])
    tr["f4"], tr["f5"] = np.full(n, 3500.0 * tract), np.full(n, 4500.0 * tract)
    tr["b4"], tr["b5"] = np.full(n, 250.0 * tract ** 0.5), np.full(n, 300.0 * tract ** 0.5)
    tr["fnp"] = np.full(n, NASAL_POLE * tract)
    return {k: [round(float(x), 1 if k[0] in "fbw" else 4) for x in v] for k, v in tr.items()}


# -- the emotes -------------------------------------------------------------------------------------------------------

def _vowel(r: _R, style: str, kind: str) -> str:
    table = {
        # shouted vowels are open (the recordings' "hah", "agh", "eh"); closed ones would be far too dark
        "grunt": {"attack": ["a", "{", "E"], "hurt": ["a", "{", "V"], "death": ["a", "{"], "jump": ["V", "a"]},
        "anime": {"attack": ["a", "e", "a"], "hurt": ["a", "e", "a"], "death": ["a", "e"], "jump": ["a", "o"]},
        "tactics": {"attack": ["a", "V", "E"], "hurt": ["V", "a", "E"], "death": ["a", "V"], "jump": ["V", "@"]},
        "mmo": {"attack": ["a", "a", "E"], "hurt": ["a", "V", "{"], "death": ["a", "{", "V"], "jump": ["V", "a"]},
    }
    return r.pick(table[style].get(kind, ["a"]))


def recipe(kind: str, style: str, intensity: float, r: _R) -> tuple[list[Seg], dict]:
    """Segments, plus {"shout": 0..1 (how far towards the shouting register), "tilt": x, "rough": +, "jitter": +}."""
    st, inten = STYLE[style], intensity
    L, air = st["length"] * (0.85 + 0.3 * r.u()), st["air"]
    anime = style == "anime"
    v = _vowel(r, style, "hurt" if kind.startswith("hurt") else "attack" if kind.startswith("attack") else kind)
    jit = 2 * (r.u() - 0.5)                                            # this take's pitch, +-1 semitone
    if kind == "attack":      # "hah!" / "hyah!" / "ya!": breath in, a held shout, falling off
        onset = "j" if anime or r.u() < 0.3 else "h"
        segs = [Seg(0.05 * L, "h", (jit,), (0.0,), (0.6 * air,)),
                Seg(0.03 * L, onset, (jit,), (0.3, 0.9), (0.4 * air,)) if onset == "j"
                else Seg(0.01, "h", (jit,), (0.2,), (0.5 * air,)),
                Seg((0.11 + 0.08 * inten) * L, v, (jit + 0.3, jit + 0.4, jit - 0.8), (0.8, 0.75, 0.5),
                    (0.65 * air, 0.6 * air, 0.5 * air)),
                Seg(0.06 * L, v, (jit - 0.8, jit - 2.5), (0.4, 0.0), (0.5 * air, 0.0))]
        return segs, dict(shout=st["effort"] * (0.85 + 0.15 * inten), tilt=3.0 * st["bright"], rough=0.2,
                          jitter=0.25)
    if kind == "attack_big":  # strain low ("hnn"), then the shout jumps up and climbs, cut off at the top
        segs = [Seg(0.04 * L, "h", (-14 + jit,), (0.0,), (0.4 * air,)),
                Seg((0.15 + 0.1 * inten) * L, "V", (-14 + jit, -13 + jit), (0.5, 0.7), (0.25 * air,)),
                Seg(0.03 * L, "h", (-2 + jit,), (0.2,), (0.6 * air,)),
                Seg((0.25 + 0.2 * inten) * L, v, (jit - 1, jit + 1.5, jit + 3.5), (0.8, 0.9, 0.9), (0.55 * air,)),
                Seg(0.07 * L, v, (jit + 3.5, jit + 1), (0.7, 0.0), (0.5 * air, 0.0))]
        return segs, dict(shout=st["effort"] * (0.9 + 0.1 * inten), tilt=3.2 * st["bright"], rough=0.25,
                          jitter=0.25)
    if kind in ("hurt", "hurt_big"):   # "ugh!" / "kya!": fast onset, up then down, often a glottal catch
        big = kind == "hurt_big"
        k = anime and r.u() < 0.6
        segs = ([Seg(0.015, "k", (jit,), (0.0,), (0.2,), (0.9,))] if k
                else [Seg(0.02, "h", (jit,), (0.0,), (0.7 * air,))])
        if k:
            segs.append(Seg(0.03, "j", (jit,), (0.4, 1.0), (0.2,)))
        segs += [Seg((0.16 + 0.12 * big + 0.06 * inten) * L, v, (jit, jit + 2.5 + big, jit + 1), (0.75, 0.85, 0.7),
                     (0.55 * air,)),
                 Seg((0.08 + 0.15 * big) * L, v, (jit + 1, jit - 2 - 2 * big), (0.5, 0.0), (0.5 * air, 0.05))]
        return segs, dict(shout=min(st["effort"] * (0.85 + 0.15 * inten) * (1.05 if big else 1.0), 1.0),
                          tilt=2.8 * st["bright"],
                          rough=0.3 + 0.2 * big, jitter=0.35)
    if kind == "death":       # a long cry, high, falling, the voice giving out into breath
        segs = [Seg(0.03, "h", (jit + 1,), (0.0,), (0.5 * air,)),
                Seg((0.5 + 0.4 * inten) * L, v, (jit + 1.5, jit + 2.5, jit, jit - 3), (0.9, 1.0, 0.8, 0.6),
                    (0.25 * air,)),
                Seg((0.45 + 0.3 * inten) * L, v, (jit - 3, jit - 8, jit - 12), (0.5, 0.25, 0.0), (0.3 * air, 0.4, 0.0))]
        return segs, dict(shout=st["effort"] * (0.85 + 0.15 * inten), tilt=2.4 * st["bright"], rough=0.35,
                          jitter=0.4)
    if kind == "jump":        # "hup!" / "hop!": short, cut by the lips
        segs = [Seg(0.035 * L, "h", (jit,), (0.0,), (0.6 * air,)),
                Seg((0.08 + 0.03 * inten) * L, v, (jit - 0.5, jit + 0.5), (0.7, 0.6), (0.55 * air,)),
                Seg(0.03, "p", (jit,), (0.0,), (0.0,), (0.0,)),
                Seg(0.02, "p", (jit,), (0.0,), (0.0,), (0.3,))]
        return segs, dict(shout=st["effort"] * 0.65, tilt=2.6 * st["bright"], rough=0.1, jitter=0.15)
    if kind == "tired":       # panting: breaths in and out, a little voice on the out-breath
        segs = []
        for _ in range(3 + int(2 * inten)):
            segs += [Seg(0.16 * L, "h", (jit,), (0.0,), (0.0, 0.5 * air, 0.0)),
                     Seg(0.2 * L, "@", (jit - 1, jit - 2), (0.15, 0.0), (0.0, 0.7 * air, 0.0)),
                     Seg(0.05 * L, "@", (0,), (0.0,), (0.0,))]
        return segs, dict(shout=0.25, tilt=0.9, rough=0.1, jitter=0.2)
    if kind in ("laugh", "giggle", "chuckle"):   # pulses of breath with voice in each, falling through the run
        rate = {"laugh": 4.8, "giggle": 7.0, "chuckle": 5.5}[kind] * (0.9 + 0.2 * r.u())
        n = {"laugh": 5, "giggle": 5, "chuckle": 3}[kind] + int(2 * inten)
        vv = {"laugh": "a", "giggle": "i" if anime else "E", "chuckle": "E" if style != "anime" else "u"}[kind]
        top = {"laugh": 5.0, "giggle": 9.0, "chuckle": 1.0}[kind]
        segs = []
        for i in range(n):
            drop = -6 * i / n
            ons = "f" if anime and kind == "chuckle" else "h"
            segs += [Seg(0.35 / rate, ons, (top + drop + jit,), (0.0,), (0.7 * air,), (0.4 if ons == "f" else 0.0,)),
                     Seg(0.45 / rate, vv, (top + drop + jit + 0.8, top + drop + jit - 1), (0.75 + 0.2 * (i == 0), 0.3),
                         (0.45 * air,)),
                     Seg(0.2 / rate, vv, (top + drop + jit - 1,), (0.0,), (0.1,))]
        return segs, dict(shout=0.15 if kind != "giggle" else 0.3, tilt=1.6 * st["bright"], rough=0.0, jitter=0.15)
    if kind == "sigh":        # a long, dark out-breath with a little voice sinking in it
        segs = [Seg(0.08 * L, "h", (2 + jit,), (0.0,), (0.0, 0.6)),
                Seg((0.6 + 0.3 * inten) * L, "a" if anime else "@", (2 + jit, jit, jit - 3.5), (0.3, 0.25, 0.0),
                    (0.7, 0.6, 0.0))]
        return segs, dict(shout=0.0, tilt=0.55, rough=0.0, jitter=0.2)
    if kind == "gasp":        # an inhaled "hah!": breath sucked in, a voiced catch
        segs = [Seg(0.12 * L, "h", (3 + jit,), (0.0,), (0.2, 1.0)),
                Seg(0.07 * L, "a" if style != "anime" else "e", (4 + jit, 5 + jit), (0.6, 0.0), (0.6, 0.0))]
        return segs, dict(shout=0.35, tilt=1.3 * st["bright"], rough=0.0, jitter=0.1)
    if kind == "surprise":    # "oh!" / "e?!": starting high, a quick lift
        vv = "e" if anime else r.pick(["a", "a", "O"])
        segs = [Seg(0.02, "h", (2 + jit,), (0.0,), (0.4 * air,)),
                Seg((0.22 + 0.1 * inten) * L, vv, (2 + jit, 4 + jit, 3 + jit), (0.9, 1.0, 0.7), (0.15 * air,)),
                Seg(0.06 * L, vv, (3 + jit, 1 + jit), (0.5, 0.0), (0.1,))]
        return segs, dict(shout=0.3 + 0.2 * inten, tilt=2.2 * st["bright"], rough=0.0, jitter=0.1)
    if kind == "hmm":         # a nasal hum, dark; rising when it doubts
        segs = [Seg((0.5 + 0.4 * inten) * L, "m", (jit, jit - 0.5, jit + 3.5), (0.6, 0.8, 0.7), (0.05,)),
                Seg(0.1 * L, "m", (jit + 3.5, jit + 3), (0.6, 0.0), (0.05,))]
        return segs, dict(shout=0.0, tilt=1.6, rough=0.0, jitter=0.1)
    if kind == "huh":         # "hm?" / "huh?" / "e?": up
        vv = "e" if anime else "V"
        segs = [Seg(0.03, "h", (jit,), (0.0,), (0.5 * air,)),
                Seg(0.22 * L, vv, (jit - 0.5, jit + 0.5, jit + 3.5), (0.8, 0.9, 0.8), (0.15 * air,)),
                Seg(0.05, vv, (jit + 3.5,), (0.4, 0.0), (0.1,))]
        return segs, dict(shout=0.1, tilt=1.6, rough=0.0, jitter=0.1)
    if kind == "yes":         # "mm-hm!" / "un!": two hums, the second higher
        segs = [Seg(0.13 * L, "m" if not anime else "n", (jit, jit - 0.5), (0.8, 0.7), (0.05,)),
                Seg(0.05, "h", (jit,), (0.0,), (0.5,)),
                Seg(0.18 * L, "m" if not anime else "n", (jit + 2, jit + 3.5), (0.9, 0.0), (0.05,))]
        return segs, dict(shout=0.05, tilt=1.6, rough=0.0, jitter=0.08)
    if kind == "no":          # "mm-mm" / "n-n": two hums, falling, the second lower
        segs = [Seg(0.14 * L, "m" if not anime else "n", (jit + 2, jit), (0.8, 0.6), (0.05,)),
                Seg(0.07, "m" if not anime else "n", (jit,), (0.0,), (0.0,)),
                Seg(0.18 * L, "m" if not anime else "n", (jit + 0.5, jit - 2.5), (0.8, 0.0), (0.05,))]
        return segs, dict(shout=0.05, tilt=1.6, rough=0.0, jitter=0.08)
    if kind == "cheer":       # "yay!" / "yeah!": high and falling, voiced and bright
        segs = [Seg(0.05 * L, "j", (3 + jit,), (0.5, 0.9), (0.1,)),
                Seg((0.3 + 0.15 * inten) * L, "e" if anime else "{", (3 + jit, 3.5 + jit, 1 + jit), (1.0, 0.95, 0.8),
                    (0.1 * air,)),
                Seg(0.15 * L, "i", (1 + jit, -1.5 + jit), (0.7, 0.0), (0.1,))]
        return segs, dict(shout=0.55 + 0.25 * inten, tilt=2.2 * st["bright"], rough=0.0, jitter=0.1)
    if kind == "relief":      # "phew": the lips blow, then a falling "ew"
        segs = [Seg(0.08 * L, "f", (2 + jit,), (0.0,), (0.2,), (0.6,)),
                Seg(0.05 * L, "j", (3 + jit,), (0.4,), (0.3,)),
                Seg(0.35 * L, "u", (3.5 + jit, -1 + jit, -8 + jit), (0.6, 0.4, 0.0), (0.5, 0.4, 0.0))]
        return segs, dict(shout=0.1, tilt=0.6, rough=0.0, jitter=0.15)
    if kind == "angry":       # "hmph!" / "tch": a hum blown out through the nose and lips
        segs = [Seg(0.12 * L, "m", (jit + 1, jit), (0.8, 0.9), (0.1,)),
                Seg(0.08 * L, "f", (jit,), (0.0,), (0.3,), (0.8, 0.0))]
        return segs, dict(shout=0.25, tilt=1.8, rough=0.2, jitter=0.15)
    raise ValueError(f"unknown emote {kind!r}; choose from {', '.join(EMOTES)}")


def emote(speaker, kind: str, style: str = "grunt", intensity: float = 0.7, take: int = 0) -> SpeechProgram:
    """The frame program of one bark in `speaker`'s voice."""
    if kind not in EMOTES:
        raise ValueError(f"unknown emote {kind!r}; choose from {', '.join(EMOTES)}")
    if style not in STYLES:
        raise ValueError(f"unknown style {style!r}; choose from {', '.join(STYLES)}")
    r = _R("emote", kind, style, repr(speaker), take)
    segs, how = recipe(kind, style, float(np.clip(intensity, 0, 1)), r)
    base = shout_pitch(speaker.pitch, speaker.tract, how["shout"])
    tracks = build(segs, base, speaker.tract, speaker.breath, open_=how["shout"])
    if speaker.whisper:
        av = np.asarray(tracks["av"])
        tracks["ah"] = [round(float(x), 4) for x in np.asarray(tracks["ah"]) + speaker.whisper * av * 0.9]
        tracks["av"] = [round(float(x), 4) for x in av * (1 - speaker.whisper)]
    return SpeechProgram(frames=tracks, frame_rate=FRAME_RATE, tilt=speaker.tilt * how["tilt"],
                         jitter=speaker.jitter + how["jitter"], rough=(min(speaker.rough + how["rough"], 0.9), 32.0),
                         sub=speaker.sub, text=f"<{kind}>", lang="", phonemes=kind)
