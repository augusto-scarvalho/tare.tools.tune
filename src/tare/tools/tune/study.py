"""What a recording is made of and what in tune makes each part (`TUNE study`), the way pxl's study ends "IN PXL".
The facts are measured (analysis.measures, the ear's lines). A hint names a field only where the relation is direct
and gives a direction, not a value the ear has not confirmed; what a recording cannot tell is said as such."""

import json

from .analysis import BASIS, _mono, distance, features, measures
from .calls import CALLS
from .ear import hear, load

DOMAINS = ("sfx", "creature", "speech", "music")
LIFT = 1.12  # median f0 / speaker.pitch of formant lines at range 1 (1.09-1.19 measured): intonation rises over pitch


def hints(m: dict, domain: str | None) -> list[dict]:
    f0, active, pitched = m["f0"], m["active_s"], m["f0"]["status"] in ("measured", "unreliable")
    shape = f"{active} s from onset to 40 dB under the peak, a {m['attack_ms']} ms attack"
    out = []
    if domain is None and pitched:
        out.append({"cannot": "whether this is speech, a creature or a tonal sfx: --domain speech|creature|sfx"})
    domain = domain or ("sfx" if not pitched else None)
    stretches = f0.get("segments", 0)
    if domain == "sfx":
        tone = "pitched, " if pitched else "unpitched, "
        tone = f"a {f0['median_hz']:.0f} Hz ring, " if f0["status"] == "ring" else tone
        out += [{"use": "sfx", "why": tone + shape},
                {"field": "knobs.length", "value": f"{active} / your render's active_s",
                 "why": "length stretches the whole sound, pitch kept"},
                {"field": "knobs.brightness",
                 "direction": f"+ if your render's centroid is under {m['centroid_hz']} Hz",
                 "why": "the spectral centroid; a direction, not a value"},
                {"field": "knobs.register", "direction": "+1 per octave your render's main peak sits under the "
                 "recording's (the peaks line)", "why": "register moves the whole spectrum in octaves"}]
        if m["end_60_s"]:
            out.append({"field": "knobs.ring", "direction": f"+ if your render falls 60 dB before {m['end_60_s']} s",
                        "why": "ring scales the tail"})
        out.append({"cannot": "kind, style and event: choose them from TUNE sounds by ear, then hold the render "
                              "against this file (references)"})
    elif domain == "speech":
        out += [{"use": "say", "why": f"pitched, {stretches} voiced stretch(es); " + shape}]
        if pitched:
            low, high = f0["range_st"]
            out += [{"field": "speaker.pitch", "value": round(f0["median_hz"] / LIFT),
                     "why": f"the median f0 is {f0['median_hz']} Hz; intonation (range 1) lifts it about 12% "
                            "over pitch"},
                    {"field": "speaker.range",
                     "direction": f"+ if your render's pitch spans less than {low}..{high} st",
                     "why": "10th to 90th percentile around the median; range is a multiplier, so a direction"},
                    {"field": "speaker.rate", "direction": f"+ if your render has fewer than "
                     f"{stretches / active:.1f} voiced stretches per second", "why": "syllable pace, roughly"}]
        out.append({"cannot": "the words, the accent and the voice's timbre: the text is yours; listen for the rest"})
    elif domain == "creature":
        calls = ", ".join(f"{c.name} x{c.duration}" + (f" ({c.repeats} syllables)" if c.repeats > 1 else "")
                          for c in CALLS.values())
        out += [{"use": "creature", "why": f"{stretches} voiced stretch(es); " + shape},
                {"field": "call", "direction": f"{stretches} syllable(s): calls by length {calls}",
                 "why": "the call sets the length and syllables"}]
        if pitched:
            out.append({"field": "size", "direction": f"+ (bigger, lower) if your render's median f0 is over "
                        f"{f0['median_hz']} Hz", "why": "size lowers the pitch; a direction only"})
        out.append({"cannot": "archetype and species: choose them by ear (TUNE design, zoo), then hold the render "
                              "against this file"})
    elif domain == "music":
        out += [{"use": "music", "why": shape},
                {"cannot": "tempo, key and instruments are not measured: set them by ear"}]
    return out


COMPARES = ("analysis.distance, 0 = identical: pitch contour (when both are voiced), loudness contour and 40-band "
            "envelope in dB, duration, noisiness, voicing and syllables, weighted; never how it sounds")


def search(audio, sr: int, what: str) -> dict:
    """The renders nearest a recording by analysis.distance (no CLAP): every style and event of one sfx kind (take 0),
    or every archetype x call at three sizes and the 8 nearest at every tenth of size (230 renders, about 25 s).
    Each row is a sound the DSL writes as is."""
    from . import Creature, Sfx, render
    from .creature import ARCHETYPES
    from .dsl.registry import catalog

    rate = 16000
    fmax = min(rate / 2 - 100, sr / 2 - 100)
    target = features(_mono(audio), sr, fmax)
    rows = []
    if what.startswith("sfx:"):
        entry = catalog("sfx", what[4:])
        if not entry:
            raise ValueError(f"unknown sfx kind {what[4:]!r}: TUNE sounds lists them")
        for style in entry[0]["styles"]:
            for event in entry[0]["events"]:
                y = render(Sfx(what[4:], style).voice(event, 0), rate)
                rows.append({"sound": {"sfx": what[4:], "style": style, "event": event},
                             "distance": round(float(distance(features(y, rate, fmax), target)), 2)})
    elif what == "creature":  # species 0: the archetype's own voice; species and genes are the ear's to vary
        def row(archetype, call, size):
            y = Creature(archetype, size=size).render(call, sr=rate)
            return {"sound": {"creature": archetype, "call": call, "size": size},
                    "distance": round(float(distance(features(y, rate, fmax), target)), 2)}

        rows = [row(a, c, s) for a in ARCHETYPES for c in CALLS for s in (0.25, 0.5, 0.75)]
        pairs = {}
        for r in sorted(rows, key=lambda r: r["distance"]):
            pairs.setdefault((r["sound"]["creature"], r["sound"]["call"]), r)
        for a, c in list(pairs)[:8]:  # size reshapes a call (syllables, length): the 8 nearest pairs at every tenth
            rows += [row(a, c, s / 10) for s in range(11) if s != 5]
    else:
        raise ValueError("search sfx:KIND or creature")
    rows.sort(key=lambda r: r["distance"])
    return {"what": what, "nearest": rows[:3], "of": len(rows), "compares": COMPARES}


def study(source, domain: str | None = None, find: str | None = None) -> dict:
    audio, sr, loop, _, label = load(source)
    m = measures(audio, sr)
    out = {"schema": "tune.study/1", "file": label, "basis": BASIS}
    if m["status"] != "measured":
        return out | {"kind": {"status": "silent"}, "lines": [f"REC {label}: silent"], "in_tune": []}
    f0 = m["f0"]
    out["kind"] = {"pitched": f0["status"] in ("measured", "unreliable"), "voiced": f0.get("voiced", 0.0),
                   "loop": loop, "channels": m["channels"], "sample_rate": sr,
                   "noise_floor_db": m["noise_floor_db"], "clipped": m["clipped"]}
    out["facts"] = {k: m[k] for k in ("active_s", "attack_ms", "end_60_s", "centroid_hz", "f0")}
    out["lines"] = hear(("REC", label, audio, sr, loop), lines_only=True)["lines"]
    out["in_tune"] = hints(m, domain)
    if find:
        out["search"] = search(audio, sr, find)
    return out


def text(report: dict) -> str:
    rows = [f"STUDY {report['file']}", *report["lines"], "IN TUNE"]
    for h in report["in_tune"]:
        if "use" in h:
            rows.append(f"  use {h['use']}: {h['why']}")
        elif "field" in h:
            rows.append(f"  {h['field']}" + (f" = {h['value']}" if "value" in h else f": {h['direction']}") +
                        f" ({h['why']})")
        else:
            rows.append(f"  cannot: {h['cannot']}")
    if "search" in report:
        found = report["search"]
        rows.append(f"NEAREST of {found['of']} renders ({found['compares']})")
        rows += [f"  {r['distance']:6.2f}  {json.dumps(r['sound'], ensure_ascii=False)}" for r in found["nearest"]]
    return "\n".join(rows)
