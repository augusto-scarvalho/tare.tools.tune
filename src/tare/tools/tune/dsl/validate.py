"""Strict DSL loading and physical-field validation, isolated from legacy readers."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import MISSING, fields
from difflib import get_close_matches
from pathlib import Path
from typing import get_args, get_origin

from ..diagnostics import canonical
from .model import FORMAT, MAX_INT, VERSION, Budgets, Document, DSLError, pointer
from .registry import FIELDS, LAYERS, META, OPS, PLACEMENT_FIELDS, SCORE_FIELDS, TRACK_FIELDS, VOICE_BUS


def obj(value, at=""):
    if not isinstance(value, dict):
        raise DSLError("E_TYPE", "expected an object", at)
    return value


def array(value, at="", maximum=None):
    if not isinstance(value, list) or maximum is not None and len(value) > maximum:
        raise DSLError("E_TYPE" if not isinstance(value, list) else "E_LIMIT", "invalid list or list limit", at)
    return value


def known(value, allowed, at=""):
    obj(value, at)
    extra = set(value) - set(allowed)
    if extra:
        key = sorted(extra)[0]
        raise DSLError(
            "E_FIELD",
            f"unknown field {key!r}",
            pointer(at, key),
            suggestions=get_close_matches(key, sorted(allowed), n=3),
        )


def number(value, at="", low=None, high=None, *, integer=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or integer
        and not isinstance(value, int)
        or low is not None
        and value < low
        or high is not None
        and value > high
    ):
        kind = "integer" if integer else "finite number"
        raise DSLError(
            "E_RANGE",
            f"expected {kind} in {low if low is not None else '-inf'}..{high if high is not None else 'inf'}",
            at,
        )
    return value


def choice(value, options, at=""):
    try:
        valid = value in options
    except TypeError:
        valid = False
    if not valid:
        options = list(options)
        close = get_close_matches(str(value), [str(o) for o in options], n=3)
        # Nothing alike: a short list is cheaper to show than to make the caller look it up.
        hint = "" if close or len(options) > 40 else "; one of: " + ", ".join(map(str, options))
        raise DSLError("E_ENUM", f"unknown value {value!r}{hint}", at, suggestions=close)
    return value


def seed(value, at="", nonnegative=False):
    return number(value, at, 0 if nonnegative else -MAX_INT, MAX_INT, integer=True)


def operation(value, at=""):
    obj(value, at)
    found = set(value) & OPS
    candidates = [op for op in found if not set(value) - (FIELDS[op] | META | {op})]
    if len(candidates) == 1:
        found = set(candidates)
    if len(found) != 1:
        raise DSLError("E_OPERATION", "expression must have exactly one operation", at)
    op = next(iter(found))
    known(value, FIELDS[op] | META | {op}, at)
    if "id" in value and (not isinstance(value["id"], str) or not value["id"]):
        raise DSLError("E_ID", "id must be a nonempty string", pointer(at, "id"))
    return op


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise DSLError("E_DUPLICATE", f"duplicate object key {key!r}")
        out[key] = value
    return out


def parse(raw, limits=None):
    limits = limits or Budgets()
    if len(raw) > limits.source_bytes:
        raise DSLError("E_LIMIT", "source exceeds the byte limit")
    # Scan structural depth before invoking the recursive stdlib decoder.
    depth, quoted, escaped = 0, False, False
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise DSLError("E_JSON", "source must be UTF-8 JSON") from None
    for c in decoded:
        if quoted:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
        elif c in "[{":
            depth += 1
            if depth > limits.depth:
                raise DSLError("E_LIMIT", "JSON depth exceeds the limit")
        elif c in "]}":
            depth -= 1
    try:
        value = json.loads(
            decoded,
            object_pairs_hook=_pairs,
            parse_constant=lambda x: (_ for _ in ()).throw(DSLError("E_FINITE", f"invalid {x}")),
        )
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, DSLError):
            raise
        raise DSLError("E_JSON", str(exc)) from None
    count = 0

    def walk(item, level=0):
        nonlocal count
        count += 1
        if count > limits.scalars or level > limits.depth:
            raise DSLError("E_LIMIT", "JSON structure/scalar limit exceeded")
        if isinstance(item, float) and not math.isfinite(item):
            raise DSLError("E_FINITE", "numbers must be finite")
        if isinstance(item, dict):
            for child in item.values():
                walk(child, level + 1)
        elif isinstance(item, list):
            for child in item:
                walk(child, level + 1)

    walk(value)
    return value


def load(path=None, *, data=None, asset_roots=(), limits=None):
    limits = limits or Budgets()
    path = Path(path or "project.tune.json").resolve()
    if data is None:
        if path.stat().st_size > limits.source_bytes:
            raise DSLError("E_LIMIT", "source exceeds the byte limit")
        raw = path.read_bytes()
    else:
        try:
            raw = canonical(data)
        except (ValueError, TypeError, RecursionError):
            raise DSLError("E_JSON", "source must be finite, acyclic JSON data") from None
    document = Document(
        parse(raw, limits), path, hashlib.sha256(raw).hexdigest(), limits, tuple(Path(p).resolve() for p in asset_roots)
    )
    validate(document)
    return document


def validate(document):
    data, limits = document.data, document.limits
    known(data, {"format", "version", "context", "defs", "sounds", "reference", "references"})
    if data.get("format") != FORMAT or type(data.get("version")) is not int or data["version"] != VERSION:
        raise DSLError("E_VERSION", f"expected {FORMAT} version {VERSION}")
    known(data.get("context", {}), {"sample_rate", "bpm", "meter"}, "/context")
    context = document.context
    number(context["sample_rate"], "/context/sample_rate", 1000, 192000, integer=True)
    number(context["bpm"], "/context/bpm", 4, 1000)
    number(context["meter"], "/context/meter", 1, 255, integer=True)
    definitions = obj(data.get("defs", {}), "/defs")
    sounds = obj(data.get("sounds"), "/sounds")
    if not sounds or len(sounds) > limits.sounds or len(definitions) > limits.definitions:
        raise DSLError("E_LIMIT", "invalid definition/sound count")
    for key in (*definitions, *sounds):
        if not key or len(key) > 256:
            raise DSLError("E_ID", "names must contain 1..256 characters")
    for name, definition in definitions.items():
        at = pointer("/defs", name)
        known(definition, {"body", "params"}, at)
        if "body" not in definition:
            raise DSLError("E_REQUIRED", "definition needs a body", at)
        for key, parameter in obj(definition.get("params", {}), at + "/params").items():
            loc = pointer(at + "/params", key)
            known(parameter, {"type", "default", "min", "max", "choices"}, loc)
            for bound in ("min", "max"):
                if bound in parameter:
                    number(parameter[bound], loc + "/" + bound)
            if "min" in parameter and "max" in parameter and parameter["min"] > parameter["max"]:
                raise DSLError("E_RANGE", "parameter minimum exceeds maximum", loc)
            if "choices" in parameter:
                array(parameter["choices"], loc + "/choices", 256)
            choice(
                parameter.get("type"),
                {
                    "number",
                    "integer",
                    "boolean",
                    "string",
                    "enum",
                    "time",
                    "notes",
                    "sound",
                    "layer",
                    "speaker",
                    "instrument",
                },
                loc + "/type",
            )
            if "default" in parameter:
                parameter_value(parameter["default"], parameter, loc)
        expression(definition["body"], at + "/body", limits)
    for name, sound in sounds.items():
        expression(sound, pointer("/sounds", name), limits)

    # Definition graph checking is separate from rendering and includes unused definitions.
    def references(value):
        if isinstance(value, dict):
            if "use" in value:
                yield value["use"]
            for key, child in value.items():
                if key not in ("spec", "meta"):
                    yield from references(child)
        elif isinstance(value, list):
            for child in value:
                yield from references(child)

    visited = set()

    def visit(name, stack):
        if name not in definitions:
            raise DSLError("E_REFERENCE", f"unknown definition {name!r}", suggestions=list(definitions)[:3])
        if name in stack:
            raise DSLError("E_CYCLE", "definition cycle: " + " -> ".join((*stack, name)))
        if len(stack) >= limits.expansion_depth:
            raise DSLError("E_LIMIT", "definition expansion depth exceeded")
        if name in visited:
            return
        for child in references(definitions[name]["body"]):
            visit(child, (*stack, name))
        visited.add(name)

    for name in definitions:
        visit(name, ())
    for name in references(sounds):
        if name not in definitions:
            raise DSLError("E_REFERENCE", f"unknown definition {name!r}")
    if "reference" in data:
        known(data["reference"], {"file"}, "/reference")
    for name, file in obj(data.get("references", {}), "/references").items():
        choice(name, sounds, "/references")
        asset(document, file, pointer("/references", name))


def sibling_ids(items, at):
    ids = []
    for item in items:
        if "id" in item:
            if not isinstance(item["id"], str) or not item["id"]:
                raise DSLError("E_ID", "id must be a nonempty string", at)
            ids.append(item["id"])
    if len(ids) != len(set(ids)):
        raise DSLError("E_ID", "duplicate sibling id", at)


def expression(value, at, limits):
    if isinstance(value, dict) and set(value) == {"param"}:
        if not isinstance(value["param"], str) or not value["param"]:
            raise DSLError("E_PARAMETER", "parameter slot needs a nonempty string name", at)
        return
    op = operation(value, at)
    payload = value[op]
    if op in ("sfx", "creature", "say", "emote", "speaker", "music", "pattern", "chord", "chip_voice"):
        slot = isinstance(payload, dict) and set(payload) == {"param"} and isinstance(payload["param"], str)
        if not slot and (not isinstance(payload, str) or not payload):
            raise DSLError("E_TYPE", "operation needs a nonempty string", pointer(at, op))
    if op in ("say", "emote", "speaker"):
        voice_names(value, op, at, limits)
    if "then" in value:
        array(value["then"], at + "/then", 32)
    if op in ("seq", "overlay", "voice"):
        for index, child in enumerate(array(payload, pointer(at, op), limits.occurrences)):
            expression(child, pointer(pointer(at, op), index), limits)
        sibling_ids(payload, pointer(at, op))
    elif op == "repeat":
        if not isinstance(payload, dict) or set(payload) != {"param"}:
            number(payload, at + "/repeat", 1, limits.repeat, integer=True)
        if "of" not in value:
            raise DSLError("E_REQUIRED", "repeat needs of", at)
        expression(value["of"], at + "/of", limits)
    elif op == "mix":
        for index, placement in enumerate(array(payload, at + "/mix", limits.occurrences)):
            loc = pointer(at + "/mix", index)
            known(placement, PLACEMENT_FIELDS, loc)
            expression(placement.get("sound"), loc + "/sound", limits)
        sibling_ids(payload, at + "/mix")
    elif op == "score":
        known(payload, SCORE_FIELDS, at + "/score")
        tracks = array(payload.get("tracks", []), at + "/score/tracks", limits.tracks)
        names = []
        for index, track in enumerate(tracks):
            loc = pointer(at + "/score/tracks", index)
            known(track, TRACK_FIELDS, loc)
            if not isinstance(track.get("name"), str) or not track["name"]:
                raise DSLError("E_REQUIRED", "track needs a synthesis name", loc)
            names.append(track["name"])
            if "notes" in track and "clips" in track:
                raise DSLError("E_FIELD", "use notes or clips, not both", loc)
            if "notes" in track:
                expression(track["notes"], loc + "/notes", limits)
            for i, clip in enumerate(array(track.get("clips", []), loc + "/clips", limits.notes)):
                known(clip, {"id", "instrument", "notes", "at"}, pointer(loc + "/clips", i))
                expression(clip.get("notes"), pointer(loc + "/clips", i) + "/notes", limits)
            for i, layer in enumerate(array(track.get("layers", []), loc + "/layers", limits.layers)):
                expression(layer, pointer(loc + "/layers", i), limits)
            sibling_ids(track.get("clips", []), loc + "/clips")
            sibling_ids(track.get("layers", []), loc + "/layers")
        sibling_ids(tracks, at + "/score/tracks")
        if len(names) != len(set(names)):
            raise DSLError("E_ID", "duplicate track synthesis name", at + "/score/tracks")
        for i, placement in enumerate(array(payload.get("sounds", []), at + "/score/sounds", limits.occurrences)):
            loc = pointer(at + "/score/sounds", i)
            known(placement, PLACEMENT_FIELDS, loc)
            expression(placement.get("sound"), loc + "/sound", limits)
        sibling_ids(payload.get("sounds", []), at + "/score/sounds")
    elif op == "edit":
        expression(payload, at + "/edit", limits)
    elif op == "instrument":
        for i, layer in enumerate(array(payload, at + "/instrument", limits.layers)):
            expression(layer, pointer(at + "/instrument", i), limits)
    elif op == "use":
        if not isinstance(payload, str):
            raise DSLError("E_TYPE", "use needs a definition name", at + "/use")
        obj(value.get("with", {}), at + "/with")
    elif op in LAYERS:
        known(payload, {f.name for f in fields(LAYERS[op])}, pointer(at, op))
    if "bus" in value:
        known(value["bus"], VOICE_BUS, at + "/bus")


def voice_names(value, op, at, limits):
    """Literal speech, emote and speaker names against the engine's own lists; parameter slots wait for compilation."""
    from ..speech.babble import STYLES as SPEECH_STYLES
    from ..speech.emote import EMOTES
    from ..speech.emote import STYLES as EMOTE_STYLES

    payload = value[op]
    if op == "speaker":
        if isinstance(payload, str):
            speaker_preset(payload, pointer(at, op))
        if isinstance(value.get("engine"), str):
            choice(value["engine"], ("formant", "natural"), at + "/engine")
        return
    if op == "emote" and isinstance(payload, str):
        choice(payload, EMOTES, pointer(at, op))
    if isinstance(value.get("style"), str):
        choice(value["style"], EMOTE_STYLES if op == "emote" else SPEECH_STYLES, at + "/style")
    nested = value.get("speaker")
    if isinstance(nested, str):
        speaker_preset(nested, at + "/speaker")
    elif isinstance(nested, dict) and set(nested) != {"param"}:
        expression(nested, at + "/speaker", limits)


def speaker_preset(name, at):
    from ..speech import PRESETS

    if name not in PRESETS and name.split(":")[0] in ("natural", "npc"):
        raise DSLError(
            "E_ENUM",
            f"{name!r} is a command-line voice name; in a project use a preset with overrides, e.g. "
            '{"speaker": "default", "engine": "natural", "bank": "pt/alex"}',
            at,
        )
    choice(name, PRESETS, at)


def parameter_value(value, parameter, at):
    kind = parameter["type"]
    if kind in ("number", "integer"):
        number(value, at, parameter.get("min"), parameter.get("max"), integer=kind == "integer")
    elif kind == "boolean" and type(value) is not bool or kind in ("string", "time") and not isinstance(value, str):
        raise DSLError("E_TYPE", f"expected {kind}", at)
    elif kind == "enum":
        choice(value, parameter.get("choices", []), at)
    elif kind in ("notes", "sound", "layer", "speaker", "instrument"):
        obj(value, at)
    return value


def reference_file(data, sound):
    """The recording `sound` is held against: its own in `references`, else the document's `reference`; and where."""
    if sound in data.get("references", {}):
        return data["references"][sound], pointer("/references", sound)
    if "reference" in data:
        return data["reference"]["file"], "/reference/file"
    return None, None


def asset(document, name, at=""):
    if not isinstance(name, str) or "://" in name:
        raise DSLError("E_ASSET", "asset must name a local file", at)
    path = (document.path.parent / name).resolve()
    if not any(path.is_relative_to(root) for root in (document.path.parent, *document.asset_roots)):
        raise DSLError("E_ASSET", "asset lies outside the authorized local roots", at)
    if not path.is_file():
        raise DSLError("E_ASSET", f"missing asset: {name}", at)
    return path


def curve(value, at, *, positive=False, optional=False):
    array(value, at, 4096)
    if not value and not optional:
        raise DSLError("E_REQUIRED", "curve cannot be empty", at)
    previous = -1
    for pair in value:
        if not isinstance(pair, list | tuple) or len(pair) != 2:
            raise DSLError("E_CURVE", "curve points need normalized time and value", at)
        number(pair[0], at, 0, 1)
        number(pair[1], at, 1e-9 if positive else None)
        if pair[0] < previous:
            raise DSLError("E_CURVE", "curve times must be ordered", at)
        previous = pair[0]


def layer_fields(kind, values, at="", *, sr=48000):
    cls = LAYERS[kind]
    allowed = {f.name for f in fields(cls)}
    known(values, allowed, at)
    for item in fields(cls):
        if item.default is MISSING and item.default_factory is MISSING and item.name not in values:
            raise DSLError("E_REQUIRED", f"missing {item.name}", at)
        if item.name not in values:
            continue
        value, expected = values[item.name], get_origin(item.type) or item.type
        location = pointer(at, item.name)
        if expected in (int, float):
            number(value, location, integer=expected is int)
        elif expected in (list, tuple):
            if not isinstance(value, list | tuple):
                raise DSLError("E_TYPE", "expected an array", location)
            if expected is tuple:
                arguments = get_args(item.type)
                if len(value) != len(arguments):
                    raise DSLError("E_TUPLE", "tuple has incorrect length", location)
                for scalar in value:
                    number(scalar, location)
        elif expected in (str, bool, dict) and not isinstance(value, expected):
            raise DSLError("E_TYPE", f"expected {expected.__name__}", location)
    for name in ("start", "attack", "release", "damp", "decay", "duration"):
        if name in values and isinstance(values[name], int | float):
            number(values[name], pointer(at, name), 0)
    for name in ("dur", "frame_rate", "q", "hardness", "warp", "stretch", "pulse_width"):
        if name in values:
            number(values[name], pointer(at, name), 1e-9)
    for name in ("gain", "brightness", "breath", "tilt", "jitter", "sub", "rough", "shimmer"):
        if name in values and not isinstance(values[name], list | tuple):
            number(values[name], pointer(at, name))
    for name in ("pitch", "freq", "amp", "mouth", "rate", "bend"):
        value = values.get(name)
        if isinstance(value, list) and (not value or isinstance(value[0], list | tuple)):
            curve(value, pointer(at, name), positive=name in ("pitch", "freq", "mouth"), optional=name == "bend")
            if name == "rate" and any(point[1] < 0 for point in value):
                raise DSLError("E_RANGE", "scatter event rates must be nonnegative", pointer(at, name))
    for name in ("source", "filter", "color", "event"):
        options = {
            "source": ("glottal", "sine", "pulse", "noise"),
            "filter": ("band", "low", "high"),
            "color": ("white", "brown"),
            "event": ("pop", "drop", "ping"),
        }[name]
        if name in values:
            choice(values[name], options, pointer(at, name))
    for name in ("modes", "formants", "hits"):
        if name in values:
            rows = array(values[name], pointer(at, name), 256 if name == "modes" else 4096)
            for row in rows:
                if not isinstance(row, list | tuple) or len(row) != 3:
                    raise DSLError("E_TUPLE", f"{name} needs triples", pointer(at, name))
                for item in row:
                    number(item, pointer(at, name))
                if name != "hits" and (row[0] <= 0 or row[1] <= 0):
                    raise DSLError("E_RANGE", "frequency and decay/bandwidth must be positive", pointer(at, name))
                if name == "hits" and (row[0] < 0 or row[2] < 0):
                    raise DSLError("E_RANGE", "contact start and length must be nonnegative", pointer(at, name))
    if kind == "speech_frames":
        frames = obj(values["frames"], at + "/frames")
        lengths = {len(array(v, at + "/frames", 72000)) for v in frames.values()}
        required = {"f0", "av", "ah", "af", "ab", "fnp", "fnz", "fa", "wa", "ga", "fb", "wb", "gb"}
        required |= {f"{name}{i}" for name in ("f", "b") for i in range(1, 6)}
        if not required <= set(frames) or len(lengths) != 1 or not next(iter(lengths), 0):
            raise DSLError("E_FRAMES", "speech frames must include f0 and have equal nonempty lengths", at)
        for values_ in frames.values():
            for value in values_:
                number(value, at + "/frames")
    for name, length in (("vibrato", 2), ("rough", 2), ("ring", 2), ("pulses", 3), ("scrape", 4), ("wobble", 2)):
        if name in values and isinstance(values[name], list | tuple):
            if len(values[name]) != length:
                raise DSLError("E_TUPLE", f"{name} needs {length} values", at)
            for value in values[name]:
                number(value, at + "/" + name)
    if kind == "spoken":
        import re

        if not isinstance(values["bank"], str) or not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", values["bank"]):
            raise DSLError("E_ASSET", "spoken bank needs a registered language/name", at)
        pieces = array(values["pieces"], at + "/pieces", 72000)
        if not pieces:
            raise DSLError("E_FRAMES", "spoken pieces cannot be empty", at)
        for piece in pieces:
            if not isinstance(piece, list | tuple) or len(piece) != 3:
                raise DSLError("E_FRAMES", "spoken pieces need from/to/output frames", at)
            number(piece[0], at, 0)
            number(piece[1], at, piece[0])
            number(piece[2], at, 1, 72000, integer=True)
        if len(values.get("f0", [])) != sum(piece[2] for piece in pieces):
            raise DSLError("E_FRAMES", "spoken pitch length must match output frame count", at)
    if kind == "chip":
        if "length" in values:
            number(values["length"], at + "/length", -128, 127, integer=True)
        if "pitch" in values:
            seed(values["pitch"], at + "/pitch")
        for channel in ("pulse1", "pulse2", "noise"):
            for command in array(values[channel], at + "/" + channel, 8192):
                if not isinstance(command, dict) or set(command) not in ({"duty"}, {"note"}):
                    raise DSLError("E_CHIP", "chip commands need duty or note", at)
                if "duty" in command:
                    number(command["duty"], at, 0, 255, integer=True)
                else:
                    note = array(command["note"], at, 4)
                    if len(note) != 4:
                        raise DSLError("E_CHIP", "chip note needs four integer registers", at)
                    for value, lo, hi in zip(
                        note, (0, 0, -7, 0), (255, 15, 7, 255 if channel == "noise" else 2047), strict=True
                    ):
                        number(value, at, lo, hi, integer=True)


def voice_fields(values, sr, at=""):
    from ..spec import Voice

    known(values, {f.name for f in fields(Voice)} | {"format", "version"}, at)
    for name in ("gain", "drive", "crush", "space", "wet", "air", "room", "lowpass", "loop"):
        if name in values:
            number(
                values[name],
                pointer(at, name),
                None if name == "gain" else 0,
                1 if name in ("crush", "wet", "air", "room") else None,
            )
    if "bits" in values:
        number(values["bits"], at + "/bits", 0, 24, integer=True)
    if "seed" in values:
        seed(values["seed"], at + "/seed")
    if values.get("space") and sr <= 10000 or values.get("air") and sr <= 2000:
        raise DSLError("E_SAMPLE_RATE", "sample rate is too low for the selected Voice filters", at)
    if values.get("speech") and sr <= 2400:
        raise DSLError("E_SAMPLE_RATE", "formant speech requires sample rate above 2400 Hz", at)


def effect_fields(effects, at=""):
    array(effects, at, 16)
    for index, effect in enumerate(effects):
        loc = pointer(at, index)
        kind = obj(effect, loc).get("type")
        choice(kind, ("chorus", "limiter"), loc + "/type")
        allowed = {"type", "rate", "depth", "mix", "voices"} if kind == "chorus" else {"type", "ceiling", "release"}
        known(effect, allowed, loc)
        if kind == "chorus":
            for key, default, lo, hi in (("rate", 0.8, 1e-9, 10), ("depth", 0.004, 0, 0.02), ("mix", 0.4, 0, 1)):
                number(effect.get(key, default), loc + "/" + key, lo, hi)
            number(effect.get("voices", 2), loc + "/voices", 1, 4, integer=True)
        else:
            number(effect.get("ceiling", 0.95), loc + "/ceiling", 1e-9, 1)
            number(effect.get("release", 0.05), loc + "/release", 0.001, 5)
            if index != len(effects) - 1:
                raise DSLError("E_EFFECT", "limiter must be the last effect", loc)
