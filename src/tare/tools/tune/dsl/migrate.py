"""Explicit migration and freezing; originals are never silently rewritten."""

import copy
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from ..bundles import atomic_json, save_bundle
from ..spec import Voice
from .adapters import capabilities
from .compiler import capture_compiled, compile_document
from .model import FORMAT, DSLError
from .validate import load


def _new_output(path, source):
    path = Path(path).resolve()
    if path == Path(source).resolve() or path.exists():
        raise DSLError("E_MIGRATION", "choose a new output path; existing files are preserved")
    return path


def _legacy_expression(source, old_rate):
    kind = source.get("type", "voice")
    if kind == "voice":
        raw = source.get("spec", {k: v for k, v in source.items() if k != "type"})
        allowed = set(asdict(Voice())) | {"format", "version"}
        if set(raw) - allowed:
            raise DSLError("E_MIGRATION", "legacy spec contains ignored fields; use explicit freeze instead")
        return {"spec": raw}
    if kind in ("sfx", "creature"):
        options = copy.deepcopy(source.get("options", {}))
        if kind == "sfx":
            return {
                "sfx": source["kind"],
                **({"style": source["style"]} if source.get("style") else {}),
                **({"event": source["event"]} if "event" in source else {}),
                "take": source.get("take", 0),
                **options,
            }
        return {
            "creature": source["archetype"],
            "call": source.get("event", "idle"),
            "take": source.get("take", 0),
            **options,
        }
    if kind == "speech":
        from ..speech import speaker_from

        descriptor = {"speaker": "default", **asdict(speaker_from(source.get("voice", "default")))}
        return {"say": source["text"], "lang": source.get("lang", "en"), "speaker": descriptor}
    if kind == "music":
        return {"music": source["kind"], "style": source.get("style", "orchestral"), "seed": source.get("seed", 0)}
    if kind == "audio":
        return {"audio": source["file"]}
    if kind == "fm":
        return {"fm": copy.deepcopy(source.get("options", {}))}
    if kind == "score":
        settings = {"bpm": 100, "meter": 4, "hall": 2.2, **copy.deepcopy(source.get("settings", {}))}
        settings.pop("sr", None)
        tracks = []
        for entry in source.get("tracks", []):
            entry = copy.deepcopy(entry)
            track = {k: entry[k] for k in ("name", "instrument", "gain", "pan", "send", "echo") if k in entry}
            if "notes" in entry:
                track["notes"] = {"notes": entry["notes"]}
            else:
                track["notes"] = {"pattern": entry["pattern"], "steps": entry.get("steps", 4)}
            bus = {
                k: v
                for k, v in entry.items()
                if k not in {"name", "instrument", "gain", "pan", "send", "echo", "notes", "pattern", "steps"}
            }
            if bus:
                track["voice"] = bus
            tracks.append(track)
        settings["tracks"] = tracks
        if source.get("bars"):
            settings["loop"] = f"{source['bars']}bar"
        return {"score": settings}
    raise DSLError("E_MIGRATION", f"unsupported legacy source {kind}")


def migrate(source, output, *, name=None, asset_roots=()):
    from ..authoring import build_file

    source = Path(source).resolve()
    output = _new_output(output, source)
    original = json.loads(source.read_text(encoding="utf-8"))
    if original.get("format") == FORMAT:
        raise DSLError("E_MIGRATION", "source is already a DSL project")
    rate = original.get("sample_rate", 48000)
    names = list(original["sounds"]) if "sounds" in original else [None]
    if name is not None:
        if name not in names:
            raise DSLError("E_SELECTION", "unknown legacy sound")
        names = [name]
    sounds = {}
    for key in names:
        selected = original["sounds"][key] if key is not None else original.get("source", original)
        expr = _legacy_expression(selected, rate)
        if "audio" in expr:
            import os

            expr["audio"] = os.path.relpath(source.parent / expr["audio"], output.parent).replace("\\", "/")
        sounds[key or source.stem] = expr
    data = {"format": FORMAT, "version": 1, "context": {"sample_rate": rate}, "sounds": sounds}
    if "reference" in original:
        import os

        data["reference"] = {
            "file": os.path.relpath(source.parent / original["reference"]["file"], output.parent).replace("\\", "/")
        }
    roots = (*asset_roots, source.parent)
    candidate = load(output, data=data, asset_roots=roots)
    reports = []
    for old_name, new_name in zip(names, sounds, strict=True):
        old = build_file(source, name=old_name)
        result = compile_document(candidate, name=new_name)
        new = capture_compiled(result)
        equal = (
            old.audio.dtype == new.audio.dtype
            and old.audio.shape == new.audio.shape
            and np.array_equal(old.audio, new.audio)
        )
        reports.append(
            {
                "sound": new_name,
                "pcm_equal": equal,
                "old_pcm": old.manifest["pcm_id"],
                "new_pcm": new.manifest["pcm_id"],
                "capabilities": capabilities(result.plan),
            }
        )
        if not equal:
            raise DSLError("E_MIGRATION_EQUIVALENCE", "migration changed PCM; original and output are preserved")
    atomic_json(output, data)
    return {
        "schema": "tune.query/1",
        "output": str(output),
        "authored_revision": candidate.revision,
        "equivalent": True,
        "sounds": reports,
        "asset_roots_required": [str(source.parent)] if output.parent != source.parent else [],
    }


def freeze(source, output, *, name=None, format="bundle", asset_roots=(), track=None, response="detailed",
           keep_tail=False):
    from ..audio_io import trim_tail, write_wav
    from ..authoring import build_file
    from ..diagnostics import pcm_id
    from ..exports import looped, rings
    from .responses import respond, validate_response

    validate_response(response)
    source = Path(source)
    captured = build_file(source, name=name, asset_roots=asset_roots)
    exported_pcm_id = captured.manifest["pcm_id"]
    frames = len(captured.audio)
    warnings, cut = [], 0
    if format == "bundle":
        path = save_bundle(captured, output)
    elif format == "wav":
        path = _new_output(output, source)
        keep = keep_tail or looped(captured) or rings(captured)
        audio = captured.audio if keep else trim_tail(captured.audio, captured.sr)
        if len(audio) < frames:  # the silent tail is cut: the file is no longer the captured PCM
            cut = round((frames - len(audio)) / captured.sr, 3)
            exported_pcm_id, frames = pcm_id(audio, captured.sr), len(audio)
        write_wav(path, audio, captured.sr)
    else:
        nodes = {node["id"]: node for node in captured.manifest["nodes"]}
        root = nodes[captured.manifest["root"]]
        if root["kind"] == "cue":
            root = nodes[root["child"]]
        if track is not None:
            matches = [
                node
                for node in nodes.values()
                if node.get("track", {}).get("name") == track and node["parent"] == root["id"]
            ]
            if len(matches) != 1:
                raise DSLError("E_SELECTION", "choose an existing root Score/Cue track")
            root = matches[0]
            warnings.append("track Voice only: Score gain, pan, sends, effects, loop and Cue fade are omitted")
        if root["kind"] != "voice":
            raise DSLError("E_CAPABILITY", "this result requires PCM/bundle export or an explicit --track")
        voice = Voice.from_dict(root["params"])
        exported_pcm_id = pcm_id(captured.arrays[root["audio"]], captured.sr)
        frames = len(captured.arrays[root["audio"]])
        path = _new_output(output, source)
        atomic_json(path, voice.to_dict())
    result = {
        "schema": "tune.query/1",
        "output": str(path),
        "pcm_id": exported_pcm_id,
        "source_revision": captured.manifest["revision"],
        "kind": format,
        "regeneration": "materialized_only",
        "warnings": warnings,
    }
    if cut:
        result["silence_cut_s"] = cut
    if response == "compact":
        result.update(frames=frames, sample_rate=captured.sr)
    return respond(result, "freeze", response)


def variants(source, output, definition, parameter, values):
    document = load(source)
    output = _new_output(output, source)
    if not isinstance(values, list) or not 1 <= len(values) <= 256:
        raise DSLError("E_LIMIT", "variants needs 1..256 explicit values")
    if definition not in document.data.get("defs", {}):
        raise DSLError("E_REFERENCE", "unknown definition")
    data = copy.deepcopy(document.data)
    generated = []
    for index, value in enumerate(values):
        name = f"{definition}_{index}"
        if name in data["sounds"]:
            raise DSLError("E_ID", "generated sound name already exists")
        data["sounds"][name] = {"use": definition, "with": {parameter: value}}
        generated.append(name)
    candidate = load(output, data=data)
    for name in generated:
        compile_document(candidate, name=name)
    atomic_json(output, data)
    return {
        "schema": "tune.query/1",
        "output": str(output),
        "sounds": generated,
        "authored_revision": candidate.revision,
    }
