"""Allowlisted adapters from language data to the existing sound engine."""

import copy
from dataclasses import fields

from ..diagnostics import digest
from ..spec import Voice
from .model import DSLError, LayerValue, SoundPlan
from .registry import COLLECTIONS, LAYERS, VOICE_BUS
from .validate import asset, choice, known, layer_fields, number, obj, seed, voice_fields


def make_layer(op, values, origin, sr):
    layer_fields(op, values, origin["pointer"], sr=sr)
    voice = Voice.from_dict({COLLECTIONS[op]: [values]})
    return LayerValue(getattr(voice, COLLECTIONS[op])[0], origin)


def make_voice(layers, bus, sr, at):
    known(bus, VOICE_BUS, at)
    voice_fields(bus, sr, at)
    groups = {}
    by_type = {cls: COLLECTIONS[name] for name, cls in LAYERS.items()}
    for layer in layers:
        if not isinstance(layer, LayerValue):
            raise DSLError("E_TYPE", "voice accepts Layer expressions", at)
        groups.setdefault(by_type[type(layer.value)], []).append(layer.value)
    if not groups:
        raise DSLError("E_REQUIRED", "voice needs at least one layer", at)
    return Voice(**groups, **bus)


def speaker(data, at):
    from ..speech import PRESETS, Speaker

    fields_ = {f.name for f in fields(Speaker)}
    known(data, fields_ | {"speaker", "id", "span"}, at)
    preset = data["speaker"]
    choice(preset, PRESETS, at + "/speaker")
    overrides = {key: value for key, value in data.items() if key in fields_}
    for key, value in overrides.items():
        if key not in ("name", "bank", "engine"):
            number(value, at + "/" + key, 1e-9 if key in ("pitch", "tract", "rate", "tilt") else None)
    choice(overrides.get("engine", "formant"), ("natural", "formant"), at + "/engine")
    if "rate" in overrides:
        number(overrides["rate"], at + "/rate", 0.25, 4)
    bank = overrides.get("bank", "")
    if bank and (not isinstance(bank, str) or len(bank.split("/")) != 2 or ".." in bank or "\\" in bank):
        raise DSLError("E_ASSET", "bank must be a registered language/name", at + "/bank")
    return Speaker.preset(preset).but(**overrides)


def leaf(node, document, dependencies, child=None):
    from .. import Creature, Sfx
    from ..audio_io import read_channels
    from ..music import Cue
    from ..speech import concat

    op, data, at = node.op, node.data, node.origin["pointer"]
    value, rate = data[op], node.context["sample_rate"]
    if op == "sfx":
        from ..sfx import RECIPES

        choice(value, RECIPES, at + "/sfx")
        options = {
            k: copy.deepcopy(v)
            for k, v in data.items()
            if k not in ("sfx", "event", "take", "style", "id", "span", "then")
        }
        knobs = obj(options.get("knobs", {}), at + "/knobs")
        for name, setting in knobs.items():
            if name not in RECIPES[value].knobs:
                raise DSLError("E_KNOB", f"unknown knob {name!r}", at + "/knobs/" + name)
            info = RECIPES[value].knobs[name]
            try:
                number(setting, at + "/knobs/" + name, info.lo, info.hi)
            except DSLError:
                raise DSLError(
                    "E_KNOB_RANGE", f"{name} must be {info.lo}..{info.hi} ({info.unit})", at + "/knobs/" + name
                ) from None
        fx = Sfx(value, data.get("style", ""), **options)
        source = fx.voice(data.get("event"), take=data.get("take", 0))
    elif op == "creature":
        options = {
            k: copy.deepcopy(v) for k, v in data.items() if k not in ("creature", "call", "take", "id", "span", "then")
        }
        source = Creature(value, **options).voice(data.get("call", "idle"), take=data.get("take", 0))
    elif op in ("say", "emote"):
        spk = child if child is not None else speaker({"speaker": "default"}, at)
        if op == "say":
            if isinstance(value, str) and len(value) > document.limits.speech_chars:
                raise DSLError(
                    "E_LIMIT", "speech text exceeds the per-line character budget; split it into phrases", at
                )
            lang = choice(data.get("lang", "en"), ("pt", "en"), at + "/lang")
            if spk.engine == "natural":
                if not concat.banks(lang) or spk.bank and not spk.bank.startswith(lang + "/"):
                    raise DSLError("E_ASSET", "natural voice bank does not support this language", at)
                if spk.bank and spk.bank not in concat.banks(lang):
                    raise DSLError("E_ASSET", "missing natural voice bank", at)
            if not isinstance(value, str) or not value.strip():
                raise DSLError("E_TYPE", "say needs nonempty text", at)
            source = spk.voice(
                value, lang=lang, seed=data.get("seed"), style=data.get("style", "speech"), emotion=data.get("emotion")
            )
        else:
            number(data.get("intensity", 0.7), at + "/intensity", 0, 1)
            source = spk.emote_voice(
                value, style=data.get("style", "grunt"), intensity=data.get("intensity", 0.7), take=data.get("take", 0)
            )
    elif op == "music":
        source = Cue(value, style=data.get("style", "orchestral"), seed=data.get("seed", 0), sr=rate)
        return SoundPlan("cue", source, rate)
    elif op == "spec":
        if isinstance(value, dict) and set(value) == {"file"}:
            import hashlib

            from .validate import parse

            path = asset(document, value["file"], at)
            if path.stat().st_size > document.limits.source_bytes:
                raise DSLError("E_LIMIT", "Voice asset exceeds source byte limit", at)
            raw = path.read_bytes()
            dependencies[str(path)] = hashlib.sha256(raw).hexdigest()
            value = parse(raw, document.limits)
        voice_fields(value, rate, at)
        for op_, collection in COLLECTIONS.items():
            for layer in value.get(collection, []):
                layer_fields(op_, layer, at + "/" + collection, sr=rate)
        source = Voice.from_dict(value)
        if not any(getattr(source, collection) for collection in COLLECTIONS.values()):
            raise DSLError("E_REQUIRED", "Voice spec needs layers", at)
    elif op == "audio":
        import hashlib

        path = asset(document, value, at)
        try:
            source, actual = read_channels(
                path,
                document.limits.seconds,
                max_bytes=min(document.limits.capture_bytes // 2, document.limits.work_bytes // 3),
            )
        except ValueError as exc:
            if "decoded byte limit" in str(exc):
                raise DSLError("E_LIMIT", str(exc), at) from None
            raise
        if actual != rate:
            raise DSLError("E_SAMPLE_RATE", "audio rate must match the project; no implicit resampling", at)
        dependencies[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return SoundPlan("pcm", source, rate)
    elif op == "rest":
        from .units import quantity

        duration = quantity(value, node.context, pointer=at)
        if duration <= 0 or duration > document.limits.seconds:
            raise DSLError("E_LIMIT", "rest must have a positive bounded duration", at)
        return SoundPlan("rest", float(duration), rate, duration)
    elif op == "fm":
        known(value, {"freq", "duration", "ratio", "index", "decay", "gain"}, at)
        for key, setting in value.items():
            number(setting, at + "/" + key)
        freq, duration, ratio, index = (
            value.get(k, d) for k, d in (("freq", 440), ("duration", 0.6), ("ratio", 3.5), ("index", 4))
        )
        if (
            not 0 < duration <= document.limits.seconds
            or not 0 < freq < rate * 0.45
            or not 0 < ratio <= 16
            or not 0 <= index <= 16
            or value.get("decay", 0.3) < 0
            or not 0 <= value.get("gain", 0.3) <= 1
            or freq * (1 + ratio * (index + 2)) >= 2 * rate
        ):
            raise DSLError("E_RANGE", "FM parameters exceed the supported range", at)
        return SoundPlan("fm", value, rate)
    else:
        raise DSLError("E_OPERATION", f"unsupported sound operation {op}", at)
    if isinstance(source, Voice):
        voice_fields(source.to_dict(), rate, at)
    return SoundPlan("voice", source, rate)


def validate_identity(data, at):
    for key in ("style", "event", "call", "era", "lang", "name"):
        if key in data and not isinstance(data[key], str):
            raise DSLError("E_TYPE", f"{key} must be a string", at + "/" + key)
    if data.get("emotion") is not None and not isinstance(data["emotion"], str):
        raise DSLError("E_TYPE", "emotion must be a string or null", at + "/emotion")
    for key in ("seed", "individual", "take"):
        if key in data:
            seed(data[key], at + "/" + key, nonnegative=key == "take")
    if "species" in data:
        if not isinstance(data["species"], str):
            seed(data["species"], at + "/species")
    for key in ("power", "size", "aggression", "variation", "take_variation"):
        if key in data:
            number(data[key], at + "/" + key, 0, 1)
    if "dry" in data and type(data["dry"]) is not bool:
        raise DSLError("E_TYPE", "dry must be boolean", at + "/dry")
    if "genes" in data:
        for key, value in obj(data["genes"], at + "/genes").items():
            number(value, at + "/genes/" + key, 0, 1)


def capabilities(plan):
    result = {
        "pcm": True,
        "voice_json": plan.kind == "voice",
        "native_voice": False,
        "midi": False,
        "reasons": [],
    }
    if plan.kind == "voice":
        unsupported = [key for key in ("chips", "speech", "vocoded") if getattr(plan.source, key)]
        result["native_voice"] = not unsupported
        if unsupported:
            result["reasons"].append({"capability": "native_voice", "features": unsupported})
    else:
        result["reasons"].append({"capability": "voice_json", "feature": plan.kind, "alternative": "PCM export"})
    if plan.kind in ("score", "cue"):
        score = plan.source.score if plan.kind == "cue" else plan.source
        import tempfile
        from pathlib import Path

        from ..midi_export import export_midi

        programs = {
            name: program
            for track in score.tracks.values()
            for name, program in getattr(track, "dsl_programs", {}).items()
            if program is not None
        }
        # Use the exporter as the authority for its channel/timing/bend subset.
        # This writes only a small temporary MIDI file and never synthesizes audio.
        try:
            if plan.placements:
                raise ValueError("placed audio has no MIDI representation")
            with tempfile.TemporaryDirectory(prefix="tune-midi-capability-") as directory:
                export_midi(score, Path(directory) / "probe.mid", programs=programs, loop=plan.loop)
            result["midi"] = True
        except ValueError as exc:
            result["reasons"].append({"capability": "midi", "feature": str(exc)})
        if score.effects:
            result["reasons"].append({"capability": "midi_timbre", "feature": "effects not embedded"})
    if not result["midi"] and not any(item["capability"] == "midi" for item in result["reasons"]):
        result["reasons"].append({"capability": "midi", "feature": "unsupported or audio-only material"})
    return result


def materialized_id(plan):
    return digest(plan.materialized())
