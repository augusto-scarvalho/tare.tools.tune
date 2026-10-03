"""Knobs: named controls over a designed sound, for a person or an agent to vary it within a recipe's character.

Every recipe has the general knobs (KNOBS); some add their own (the interface and status sounds: the game's key).
Each knob has a default that leaves the sound exactly as designed, a range and a plain description, so a tool can
list them (Sfx.knob_info, `tare.tools.tune sounds --knobs`) and pick: "the confirm lower and slower, the shell with
no sparkle". The general knobs work on the spec's layers after the recipe has designed them, so they mean the same
thing for a menu tick, a sword or a fire spell.
"""
from dataclasses import dataclass, replace

from ..spec import Modal, Noise, Syllable, Voice


@dataclass(frozen=True)
class Knob:
    default: float | None           # None: the recipe decides (from the species)
    lo: float
    hi: float
    unit: str
    description: str


KNOBS = {
    "register": Knob(0.0, -2.0, 2.0, "octaves",
                     "everything up or down (notes, rings, noise bands, sparkle); 1 = an octave up"),
    "tempo": Knob(1.0, 0.25, 4.0, "x", "the gaps between the parts (the notes of a run, the hits of a roll): "
                                       "2 = twice as slow, 0.5 = twice as quick; each part keeps its length"),
    "length": Knob(1.0, 0.25, 4.0, "x", "the whole sound stretched or squeezed in time, its pitch kept"),
    "ring": Knob(1.0, 0.1, 4.0, "x", "how long struck notes, bars and bells ring, and short blips last"),
    "brightness": Knob(0.0, -1.0, 1.0, "", "darker (-1: the highs cut from ~2 kHz) to brighter (+1: harder "
                                           "strikes, stronger upper partials)"),
    "sparkle": Knob(1.0, 0.0, 3.0, "x", "the glittering pings over a sound; 0 = none"),
}
KEY = {"key": Knob(None, 48.0, 96.0, "MIDI note",
                   "the game's key, the note its interface and status sounds are built on (72 = C5); "
                   "default: from the species, C5 give or take three semitones")}


def _scale_curve(curve, k):
    return [(t, v * k) for t, v in curve]


# No rounding below: native/src/voice.cpp turns the same knobs over a ready spec in a game, with the same arithmetic.

def _register(e, r):
    if isinstance(e, Modal):
        return replace(e, modes=[(f * r, t, g) for f, t, g in e.modes], hardness=e.hardness * r)
    if isinstance(e, Syllable):
        return replace(e, pitch=_scale_curve(e.pitch, r))
    if isinstance(e, Noise):
        return replace(e, freq=_scale_curve(e.freq, r))
    return replace(e, freq=(e.freq[0] * r, e.freq[1] * r))


def _tempo(e, k):
    e = replace(e, start=e.start * k)
    if isinstance(e, Modal) and len(e.hits) > 1:      # a double knock keeps its rhythm
        last = max(t for t, _, _ in e.hits)
        e = replace(e, hits=[(t * k, g, c) for t, g, c in e.hits], dur=e.dur + max(last * (k - 1), 0))
    return e


def _length(e, k):
    e = replace(e, start=e.start * k, dur=e.dur * k)
    if isinstance(e, Modal):
        return replace(e, modes=[(f, t * k, g) for f, t, g in e.modes], hits=[(t * k, g, c) for t, g, c in e.hits],
                       scrape=(e.scrape[0] * k, e.scrape[1] * k, e.scrape[2], e.scrape[3] / k), damp=e.damp * k)
    if isinstance(e, Syllable):
        return replace(e, attack=e.attack * k, release=e.release * k, vibrato=(e.vibrato[0] / k, e.vibrato[1]),
                       pulses=(e.pulses[0] / k, e.pulses[1], e.pulses[2]), rough=(e.rough[0], e.rough[1] / k))
    if isinstance(e, Noise):
        return replace(e, attack=e.attack * k, release=e.release * k, wobble=(e.wobble[0] / k, e.wobble[1]))
    return replace(e, rate=_scale_curve(e.rate, 1 / k))


def _ring(e, k):
    if isinstance(e, Modal):
        return replace(e, modes=[(f, t * k, g) for f, t, g in e.modes], dur=e.dur * k, damp=e.damp * k)
    if isinstance(e, Syllable) and e.source == "pulse" and e.dur <= 0.5:     # a blip
        return replace(e, dur=max(e.dur * k, 0.008), release=min(e.release, e.dur * k / 3))
    return e


def _bright(e, b):
    if isinstance(e, Modal):
        low = min(f for f, _, _ in e.modes) if e.modes else 1.0
        return replace(e, hardness=e.hardness * 2 ** (2 * b), modes=[(f, t, g * (f / low) ** (0.5 * b))
                                                                       for f, t, g in e.modes])
    if isinstance(e, Syllable):
        return replace(e, brightness=min(e.brightness + 0.5 * b, 1.0))
    return e


def apply(v: Voice, values: dict) -> Voice:
    """The general knobs over a designed voice; at their defaults it comes back untouched."""
    knobs = {n: values.get(n, KNOBS[n].default) for n in KNOBS}
    if all(knobs[n] == KNOBS[n].default for n in KNOBS):
        return v
    layers = {"modal": v.modal, "noise": v.noise, "scatter": v.scatter, "syllables": v.syllables}
    if knobs["sparkle"] != 1.0:
        s = knobs["sparkle"]
        layers["scatter"] = [e if e.event != "ping" else replace(e, gain=e.gain * s)
                             for e in layers["scatter"] if e.event != "ping" or s > 0]
    steps = [("register", lambda e, x: _register(e, 2 ** x)), ("tempo", _tempo), ("length", _length),
             ("ring", _ring)]
    for name, fn in steps:
        if knobs[name] != KNOBS[name].default:
            layers = {k: [fn(e, knobs[name]) for e in es] for k, es in layers.items()}
    b = knobs["brightness"]
    out = replace(v, **layers)
    if b > 0:
        out = replace(out, **{k: [_bright(e, b) for e in es] for k, es in layers.items()})
    elif b < 0:
        cut = 16000 * 2 ** (3 * b)
        out = replace(out, lowpass=min(out.lowpass or cut, cut))
    if knobs["length"] != 1.0 and out.loop:
        out = replace(out, loop=out.loop * knobs["length"])
    return out
