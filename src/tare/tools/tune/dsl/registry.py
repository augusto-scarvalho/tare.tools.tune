"""Explicit expression vocabulary and adapter inventories; never reflectively invoke user names."""

from dataclasses import MISSING, fields

from .. import spec
from ..speech import Speaker

LAYERS = {
    "syllable": spec.Syllable,
    "modal": spec.Modal,
    "noise": spec.Noise,
    "scatter": spec.Scatter,
    "chip": spec.ChipProgram,
    "speech_frames": spec.SpeechProgram,
    "vocoded": spec.Vocoded,
    "spoken": spec.Spoken,
}
COLLECTIONS = {
    "syllable": "syllables",
    "modal": "modal",
    "noise": "noise",
    "scatter": "scatter",
    "chip": "chips",
    "speech_frames": "speech",
    "vocoded": "vocoded",
    "spoken": "spoken",
}
META = {"id", "span", "then"}
FIELDS = {
    "sfx": {"style", "event", "species", "size", "power", "take", "take_variation", "genes", "knobs", "era", "dry"},
    "creature": {
        "call",
        "species",
        "size",
        "aggression",
        "individual",
        "variation",
        "take_variation",
        "take",
        "genes",
        "name",
    },
    "say": {"lang", "speaker", "seed", "style", "emotion"},
    "emote": {"speaker", "style", "intensity", "take"},
    "speaker": {f.name for f in fields(Speaker)},
    "music": {"style", "seed"},
    "voice": {"bus"},
    "spec": set(),
    "audio": set(),
    "fm": set(),
    "pattern": {"steps"},
    "notes": set(),
    "chord": {"octave", "at", "dur", "velocity"},
    "degrees": {"root", "mode", "octave"},
    "seq": {"gap", "hall", "echo", "lowpass", "seed", "gain", "effects", "loop"},
    "repeat": {"of", "gap", "hall", "echo", "lowpass", "seed", "gain", "effects", "loop"},
    "overlay": set(),
    "mix": {"hall", "echo", "lowpass", "seed", "gain", "effects", "loop"},
    "rest": set(),
    "score": set(),
    "instrument": {"midi_program"},
    "chip_voice": {"duty", "vibrato", "slide", "fade"},
    "edit": {"expect", "set", "append", "remove"},
    "use": {"with"},
} | {name: set() for name in LAYERS}
OPS = set(FIELDS)
NOTE_OPS = {"pattern", "notes", "chord", "degrees", "overlay"}
VOICE_BUS = {f.name for f in fields(spec.Voice)} - set(COLLECTIONS.values()) - {"meta"}
SCORE_FIELDS = {"bpm", "meter", "seed", "hall", "echo", "lowpass", "loop", "gain", "tracks", "sounds", "effects"}
TRACK_FIELDS = {"id", "name", "instrument", "notes", "clips", "layers", "gain", "pan", "send", "echo", "voice"}
PLACEMENT_FIELDS = {"id", "at", "sound", "gain", "pan", "send", "echo"}

# Primitive coordinates deliberately retain the engine's physical units.
UNITS = {
    "start": "seconds",
    "dur": "seconds",
    "attack": "seconds",
    "release": "seconds",
    "gain": "signed linear amplitude",
    "pitch": "Hz",
    "freq": "Hz",
    "rate": "events/second",
    "mouth": "formant ratio",
    "amp": "signed linear amplitude",
    "bend": "semitones",
    "frame_rate": "frames/second",
    "tilt": "Hz",
    "hardness": "Hz",
    "damp": "seconds",
    "formants": ["Hz", "bandwidth Hz", "gain"],
    "modes": ["Hz", "T60 seconds", "gain"],
    "hits": ["seconds", "gain", "contact seconds"],
    "vibrato": ["Hz", "semitones"],
    "ring": ["Hz", "mix"],
    "wobble": ["Hz", "depth"],
    "scrape": ["seconds", "seconds", "gain", "Hz"],
}
ENUMS = {
    "source": ["glottal", "sine", "pulse", "noise"],
    "filter": ["band", "low", "high"],
    "color": ["white", "brown"],
    "event": ["pop", "drop", "ping"],
}


def layer_schema(kind, cls):
    result = {}
    for field in fields(cls):
        type_ = getattr(field.type, "__name__", str(field.type))  # "float", not "<class 'float'>"
        item = {"type": type_, "required": field.default is MISSING and field.default_factory is MISSING}
        if field.default is not MISSING:
            item["default"] = field.default
        elif field.default_factory is not MISSING:
            item["default"] = field.default_factory()
        if field.name in UNITS:
            item["unit"] = UNITS[field.name]
        if field.name in ENUMS:
            item["choices"] = ENUMS[field.name]
        if field.name in ("pitch", "freq", "mouth", "amp", "rate", "bend") and "list" in str(field.type):
            item.update(
                coordinates="normalized time 0..1, nondecreasing",
                max_points=4096,
                interpolation="log" if field.name in ("pitch", "freq") else "linear",
            )
        if field.name in ("start", "dur", "attack", "release", "damp"):
            item["min"] = 0
        if field.name in ("dur", "frame_rate", "q", "hardness", "warp", "stretch", "pulse_width"):
            item.update(min=0, exclusive_min=0)
        if field.name == "modes":
            item.update(max_items=256, constraint="positive frequency and decay")
        if kind in ("vocoded", "spoken") and field.name in ("pitch", "warp", "stretch"):
            item["unit"] = "ratio"
        if kind in ("vocoded", "spoken") and field.name == "tilt":
            item["unit"] = "dB/octave around 1 kHz"
        if kind == "chip" and field.name == "pitch":
            item["unit"] = "frequency register offset"
        if kind == "speech_frames" and field.name == "frames":
            item["constraint"] = "equal nonempty arrays, required Klatt tracks, max 72000 frames"
        result[field.name] = item
    return result


def catalog(domain=None, name=None):
    from dataclasses import asdict

    from ..archetypes import ARCHETYPES, DESCRIPTIONS
    from ..instruments import INSTRUMENTS
    from ..music import CUES, STYLES
    from ..sfx import RECIPES
    from ..speech import PRESETS
    from .vocabulary import TRANSFORMS, enrich

    result = []
    if domain in (None, "sfx"):
        for key, recipe in sorted(RECIPES.items()):
            result.append(
                {
                    "domain": "sfx",
                    "name": key,
                    "meaning": recipe.description,
                    "events": list(recipe.events),
                    "styles": list(recipe.styles),
                    "knobs": {n: asdict(k) for n, k in recipe.knobs.items()},
                }
            )
    if domain in (None, "creature"):
        result += [
            {"domain": "creature", "name": key, "meaning": DESCRIPTIONS.get(key, key)} for key in sorted(ARCHETYPES)
        ]
    if domain in (None, "speaker"):
        result += [{"domain": "speaker", "name": key, "fields": sorted(FIELDS["speaker"])} for key in sorted(PRESETS)]
    if domain in (None, "music"):
        result += [{"domain": "music", "name": key, "styles": list(STYLES)} for key in sorted(CUES)]
    if domain in (None, "instrument"):
        result += [{"domain": "instrument", "name": key} for key in sorted(INSTRUMENTS)]
    if domain in (None, "layer"):
        result += [{"domain": "layer", "name": key, "fields": layer_schema(key, cls)} for key, cls in LAYERS.items()]
    if domain in (None, "op"):
        result += [{"domain": "op", "name": key, "fields": sorted(FIELDS[key] | META)} for key in sorted(OPS)]
    result = [enrich(entry) for entry in result if name is None or entry["name"] == name]
    if domain in (None, "transform"):
        result += [
            {
                "domain": "transform",
                "name": key,
                "meaning": meaning,
                "result_type": "Notes",
                "fields": {key: fields_},
                "defaults": {},
                "capabilities": {"before_synthesis": True},
                "example": {"notes": [[60, 1, 0.5]], "span": "4b", "then": [{key: example}]},
            }
            for key, (meaning, fields_, example) in TRANSFORMS.items()
        ]
    return [entry for entry in result if name is None or entry["name"] == name]
