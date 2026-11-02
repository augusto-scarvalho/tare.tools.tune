"""Maintained discovery contracts and executable examples for the fixed DSL vocabulary."""

from dataclasses import MISSING, asdict, fields

from .registry import COLLECTIONS, FIELDS, LAYERS, META, layer_schema


def field(type_, default=MISSING, **constraints):
    return {"type": type_, **({"default": default} if default is not MISSING else {}), **constraints}


TIME = field("quantity", examples=["20ms", "1/3b", "2bar"], min=0)
IDENTITY = field("integer|string", 0, meaning="Synthesis identity; authored labels never replace this seed.")
SEED = field("integer", 0, min=-(2**53 - 1), max=2**53 - 1)
UNIT = field("number", min=0, max=1)
MEANINGS = {
    "sfx": ("Sound", "Design an object/event sound with the registered recipe."),
    "creature": ("Sound", "Design a creature call from identity and traits."),
    "speaker": ("Speaker", "Choose a registered speaker and override explicit voice fields."),
    "say": ("Sound", "Speak text using a Speaker descriptor and language."),
    "emote": ("Sound", "Render a nonverbal performance with the existing speech engine."),
    "music": ("Sound", "Compose a deterministic Cue with its original wrapper and duration."),
    "voice": ("Sound", "Group primitive layers through one shared Voice bus."),
    "spec": ("Sound", "Read an embedded Voice or a local Voice JSON file."),
    "audio": ("Sound", "Import local mono/stereo PCM at the project sample rate."),
    "fm": ("Sound", "Render the existing bounded oversampled FM tone."),
    "rest": ("Sound", "Explicit silence with a scheduling span."),
    "notes": ("Notes", "Pitch/onset/held-beat/velocity tuples, in authored order."),
    "pattern": ("Notes", "Pattern notation retaining leading and trailing rests."),
    "chord": ("Notes", "A named chord held at the requested beat and duration."),
    "degrees": ("Notes", "Zero-based scale-degree events in a named key/mode."),
    "seq": ("Notes|Sound", "Schedule homogeneous expressions by span, preserving tails."),
    "repeat": ("Notes|Sound", "Repeat one expression by its complete scheduling span."),
    "overlay": ("Notes", "Combine phrases at beat zero, using the longest span."),
    "mix": ("Sound", "Place separately processed Sounds through one stereo Score bus."),
    "score": ("Sound", "Musical tracks, separate play-call clips and Sound placements."),
    "instrument": ("Instrument", "Finite primitive templates evaluated once per Note."),
    "use": ("Same as definition", "Invoke a local definition with lexical typed parameters."),
    "edit": ("Sound", "Refine a copied materialization under an exact expansion guard."),
}
EXAMPLES = {
    "sfx": {"sfx": "ui", "event": "confirm", "dry": True},
    "creature": {"creature": "mammal", "species": "wolf", "call": "attack"},
    "speaker": {"speaker": "deep"},
    "say": {"say": "Ready!", "lang": "en"},
    "emote": {"emote": "attack"},
    "music": {"music": "levelup", "seed": 7},
    "voice": {"voice": [{"noise": {"start": 0, "dur": 0.1, "freq": [[0, 1000]]}}]},
    "spec": {"spec": {"file": "lead.voice.json"}},
    "audio": {"audio": "contact.wav"},
    "fm": {"fm": {"duration": 0.1}},
    "rest": {"rest": "250ms"},
    "notes": {"notes": [["C4", 0, 0.5, 0.8]], "span": "3b"},
    "pattern": {"pattern": "C4 - . . . .", "steps": 2},
    "chord": {"chord": "Cm", "dur": "1b"},
    "degrees": {"degrees": [[0, 0, 1], [2, 1, 1]], "root": "C", "mode": "major"},
    "seq": {"seq": [{"rest": "10ms"}, {"fm": {"duration": 0.1}}]},
    "repeat": {"repeat": 2, "of": {"pattern": "C4 . .", "steps": 1}},
    "overlay": {"overlay": [{"notes": [[60, 0, 1]]}, {"notes": [[64, 0, 1]]}]},
    "mix": {"mix": [{"sound": {"sfx": "ui", "dry": True}, "at": "0s"}]},
    "score": {"score": {"tracks": [{"name": "lead", "instrument": "harp", "notes": {"pattern": "C4 ."}}]}},
    "instrument": {
        "instrument": [
            {
                "syllable": {
                    "start": {"note": "start"},
                    "dur": {"note": "dur"},
                    "pitch": [[0, {"note": "f"}]],
                    "source": "sine",
                }
            }
        ]
    },
    "use": {"use": "hit", "with": {"power": 0.65}},
    "edit": {"edit": {"sfx": "ui"}, "expect": "FROM_DSL_EXPAND", "set": {"/lowpass": 2400}},
    "syllable": {"syllable": {"start": 0, "dur": 0.1, "pitch": [[0, 440]], "source": "sine"}},
    "modal": {"modal": {"start": 0, "dur": 0.1, "modes": [[440, 0.1, 1]]}},
    "noise": {"noise": {"start": 0, "dur": 0.1, "freq": [[0, 1000]]}},
    "scatter": {"scatter": {"start": 0, "dur": 0.1, "rate": [[0, 20]]}},
    "chip": {"chip": {"pulse1": [{"note": [1, 8, 0, 1000]}], "pulse2": [], "noise": []}},
    "speech_frames": {
        "speech_frames": {
            "frames": {
                key: [100]
                for key in (
                    "f0",
                    "av",
                    "ah",
                    "af",
                    "ab",
                    "fnp",
                    "fnz",
                    "fa",
                    "wa",
                    "ga",
                    "fb",
                    "wb",
                    "gb",
                    "f1",
                    "f2",
                    "f3",
                    "f4",
                    "f5",
                    "b1",
                    "b2",
                    "b3",
                    "b4",
                    "b5",
                )
            }
        }
    },
    "spoken": {"spoken": {"bank": "en/voice", "pieces": [[0, 1, 1]], "f0": [100]}},
    "vocoded": {"vocoded": {"clip": "attack/performer/take"}},
}
TRANSFORMS = {
    "transpose": ("Shift pitches in semitones before instrument expansion.", field("number", unit="semitones"), -12),
    "stretch": ("Scale onset, hold and span together.", field("number", exclusive_min=0), 2),
    "velocity": ("Multiply velocity, rejecting results outside 0..1.", field("number", min=0), 0.8),
    "retrograde": ("Reverse held notes inside the complete phrase span.", field("boolean", const=True), True),
    "quantize": ("Round onsets to a beat grid; ties move later.", TIME | {"exclusive_min": 0}, "1/4b"),
    "humanize": (
        "Deterministic onset/velocity deviations with explicit seed.",
        field(
            "object", properties={"time": TIME | {"default": "0ms"}, "velocity": UNIT | {"default": 0}, "seed": SEED}
        ),
        {"time": "10ms", "velocity": 0.02, "seed": 17},
    ),
}


def operation_fields(op):
    result = {name: field("JSON", meaning="See the operation-specific constraint.") for name in FIELDS[op] | META}
    result.update(
        id=field("string", meaning="Nonempty authoring label; seed-neutral."),
        span=TIME,
        then=field("Transform[]", meaning="Notes only; evaluated left to right."),
    )
    descriptions = {
        "style": field("string", meaning="One of the selected recipe/preset styles."),
        "event": field("string", meaning="Registered recipe event; defaults to the first event."),
        "call": field("string", "idle", meaning="Registered creature call."),
        "era": field("enum", "", choices=["", "hd", "16bit"]),
        "name": field("string", "", meaning="Informational recipe label."),
        "genes": field("object", {}, values=UNIT),
        "knobs": field("object", {}, meaning="Selected recipe's numeric knobs."),
        "dry": field("boolean", False),
        "speaker": field("Speaker|string", "default"),
        "root": field("string", "C"),
        "mode": field("string", "major"),
        "octave": field("integer", 4),
        "midi_program": field("integer", min=0, max=127),
        "set": field("object", {}, meaning="Nonoverlapping materialized pointer/value replacements."),
        "append": field("object", {}, meaning="Voice layer collection pointer to new layers."),
        "remove": field("string[]", [], meaning="Explicit layer pointers to remove in descending index order."),
        "hall": field("number", 0, min=0, max=180, unit="seconds"),
        "lowpass": field("number", 0, min=0, unit="Hz; zero disables"),
        "gain": field("number", 1, unit="signed linear amplitude"),
        "echo": field("tuple|null", None, coordinates=["delay seconds >0", "feedback 0..0.95", "tone Hz >0"]),
        "effects": field("Effect[]", [], choices=["chorus", "limiter"], meaning="At most one limiter, last."),
        "emotion": field("string|null", None, meaning="Registered speech emotion or alias."),
        "lang": field("enum", "en", choices=["en", "pt"]),
    }
    result.update({key: value for key, value in descriptions.items() if key in FIELDS[op]})
    for name in ("power", "size", "aggression", "variation", "take_variation", "intensity", "velocity"):
        if name in result:
            result[name] = UNIT.copy()
    for name in ("seed", "individual", "take"):
        if name in result:
            result[name] = SEED | ({"min": 0} if name == "take" else {})
    if "species" in result:
        result["species"] = IDENTITY
    for name in ("at", "dur", "gap", "loop"):
        if name in result:
            result[name] = TIME
    if op in LAYERS:
        result[op] = field("object", required=True, properties=layer_schema(op, LAYERS[op]))
    else:
        result[op] = field(
            {
                "voice": "Layer[]",
                "instrument": "Layer[]",
                "seq": "Expression[]",
                "overlay": "Notes[]",
                "repeat": "integer",
                "mix": "Placement[]",
                "score": "Score",
                "notes": "NoteTuple[]",
                "degrees": "DegreeTuple[]",
                "fm": "FM",
                "edit": "Sound",
                "spec": "Voice|file",
            }.get(op, "string"),
            required=True,
        )
    if op == "repeat":
        result[op].update(min=1, max=256)
        result["of"] = field("Notes|Sound", required=True)
    if op in ("seq", "repeat"):
        result["gap"] = TIME | {"default": "0b or 0s according to operand type"}
    if op == "voice":
        from ..spec import Voice

        bus = layer_schema("voice", Voice)
        result["bus"] = field(
            "VoiceBus",
            default={},
            properties={key: value for key, value in bus.items() if key not in {*COLLECTIONS.values(), "meta"}},
            meaning="One normalization/filter/effect bus for all layers.",
        )
    if op == "pattern":
        result["steps"] = field("number", 4, exclusive_min=0, unit="steps/beat")
    if op == "score":
        result[op]["defaults"] = {
            "bpm": "context.bpm (100)",
            "meter": "context.meter (4)",
            "hall": 0,
            "seed": 0,
            "gain": 1,
            "tracks": [],
            "sounds": [],
            "effects": [],
        }
        result[op]["properties"] = {key: descriptions[key] for key in ("hall", "echo", "lowpass", "gain", "effects")}
        result[op]["properties"].update(
            bpm=field("number", "context.bpm", min=4, max=1000),
            meter=field("integer", "context.meter", min=1, max=255),
            seed=SEED,
            loop=TIME,
            tracks=field(
                "Track[]",
                [],
                meaning="name is seed-relevant; id is authoring-only; notes or ordered clips, plus layers.",
            ),
            sounds=field(
                "Placement[]", [], meaning="sound, unit-bearing at, gain, pan -1..1, send, echo, optional id."
            ),
        )
    if op == "fm":
        result[op]["properties"] = {
            name: field("number", default, unit=unit, min=low, max=high)
            for name, default, unit, low, high in (
                ("freq", 440, "Hz", 0, "0.45*sample_rate"),
                ("duration", 0.6, "seconds", 0, 180),
                ("ratio", 3.5, "ratio", 0, 16),
                ("index", 4, "modulation index", 0, 16),
                ("decay", 0.3, "seconds", 0, None),
                ("gain", 0.3, "linear amplitude", 0, 1),
            )
        }
    if op in ("say", "emote", "speaker"):
        from ..speech import PRESETS, Speaker, concat
        from ..speech.babble import STYLES as SPEECH_STYLES
        from ..speech.emote import EMOTES
        from ..speech.emote import STYLES as EMOTE_STYLES

        voice = field("Speaker|string", "default", meaning="A preset name, or a speaker object with overrides.")
    if op == "say":
        result["lang"] = field("enum", "en", choices=["en", "pt"])
        result["speaker"] = voice
        result["style"] = field("enum", "speech", choices=list(SPEECH_STYLES))
    if op == "emote":
        result["emote"] = field("enum", required=True, choices=list(EMOTES))
        result["speaker"] = voice
        result["style"] = field("enum", "grunt", choices=list(EMOTE_STYLES))
        result["intensity"] = UNIT | {"default": 0.7}
    if op == "speaker":
        result.update(layer_schema("speaker", Speaker))
        result["speaker"] = field("enum", required=True, choices=sorted(PRESETS), meaning="Registered preset name.")
        result["engine"] = field("enum", "formant", choices=["formant", "natural"])
        result["bank"] = field("enum", "", choices=["", *concat.banks()], meaning="natural: '' picks the nearest bank.")
        result["rate"] = field("number", 1, min=.25, max=4, unit="speaking-rate ratio")
    if op in ("sfx", "creature"):
        from ..creature import Creature
        from ..sfx import Sfx

        cls = Sfx if op == "sfx" else Creature
        for item in fields(cls):
            if item.name in result and item.default is not MISSING:
                default = {} if item.name in ("genes", "knobs") else item.default
                result[item.name] = result[item.name] | {"default": default}
    if op in ("edit", "use"):
        result["expect" if op == "edit" else "with"] = field(
            "materialized_id" if op == "edit" else "object", **({"required": True} if op == "edit" else {"default": {}})
        )
    return result


def enrich(entry):
    from ..creature import Creature
    from ..midi_export import DRUMS, PROGRAMS
    from ..sfx import Sfx
    from ..speech import Speaker

    domain, name = entry["domain"], entry["name"]
    if domain in ("op", "layer"):
        type_, meaning = MEANINGS.get(name, ("Layer", f"Construct the existing {name} primitive in physical units."))
        schema = operation_fields(name)
        return entry | {
            "result_type": type_,
            "meaning": meaning,
            "fields": schema,
            "defaults": {key: item["default"] for key, item in schema.items() if "default" in item},
            "example": EXAMPLES[name],
            "capabilities": {
                "serializable": True,
                "native_execution": False,
                "native_voice": False
                if name in ("chip", "speech_frames", "vocoded", "audio", "fm", "music", "score", "mix")
                else "requires bank assets"
                if name == "spoken"
                else "inspect expanded features",
                "portable_voice": "depends on expanded features" if type_ == "Sound" else "compile through Voice/Score",
            },
        }
    if domain == "sfx":
        defaults = {key: value for key, value in asdict(Sfx(name)).items() if key in FIELDS["sfx"]}
        defaults.update({key: dict(defaults[key]) for key in ("genes", "knobs") if key in defaults})
        defaults["event"] = entry["events"][0]
        return entry | {
            "result_type": "Sound",
            "defaults": defaults,
            "fields": operation_fields("sfx"),
            "example": {"sfx": name, "event": entry["events"][0]},
            "capabilities": {"pcm": True, "voice_json": True, "native_voice": "inspect expanded features"},
        }
    if domain == "creature":
        from ..calls import CALLS

        return entry | {
            "result_type": "Sound",
            "fields": operation_fields("creature"),
            "defaults": asdict(Creature(name)) | {"genes": {}},
            "events": list(CALLS),
            "example": {"creature": name, "call": "idle"},
            "capabilities": {
                "pcm": True,
                "voice_json": True,
                "native_voice": False if name == "chip" else "inspect expanded features",
            },
        }
    if domain == "speaker":
        value = Speaker.preset(name)
        return entry | {
            "meaning": "Registered speaker preset.",
            "result_type": "Speaker",
            "defaults": asdict(value),
            "fields": operation_fields("speaker"),
            "example": {"speaker": name},
            "capabilities": {"formant": True, "natural": "requires an installed language bank"},
        }
    if domain == "music":
        return entry | {
            "meaning": "Deterministic Cue recipe with its original wrapper.",
            "result_type": "Sound",
            "fields": operation_fields("music"),
            "defaults": {"style": "orchestral", "seed": 0},
            "example": {"music": name, "seed": 7},
            "capabilities": {"pcm": True, "voice_json": False, "midi": "inspect expanded events"},
        }
    return entry | {
        "meaning": "Existing Note-to-layers instrument.",
        "result_type": "Layer[]",
        "fields": {
            "note": field(
                "Note",
                required=True,
                properties={
                    "start": field("number", unit="seconds"),
                    "dur": field("number", unit="seconds"),
                    "f": field("number", unit="Hz"),
                    "vel": UNIT,
                    "seed": SEED,
                },
            )
        },
        "defaults": {},
        "example": {"score": {"tracks": [{"name": "lead", "instrument": name, "notes": {"notes": [[60, 0, 1]]}}]}},
        "capabilities": {"midi": name in PROGRAMS or name in DRUMS, "native_voice": "inspect expanded Voice"},
    }
