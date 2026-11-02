"""Guarded materialized refinements, distinct from gain-frozen diagnostic interventions."""

import copy
from dataclasses import asdict

from ..diagnostics import digest
from ..spec import Voice
from .adapters import materialized_id
from .model import DSLError, clone
from .patch import get, parent, replace
from .registry import COLLECTIONS, LAYERS, VOICE_BUS
from .validate import array, effect_fields, known, layer_fields, number, obj, seed, voice_fields


def apply(plan, data, at):
    current_guard = materialized_id(plan)
    if data.get("expect") != current_guard:
        targets = (
            [
                {"path": f"/{collection}/{index}", "kind": op}
                for op, collection in COLLECTIONS.items()
                for index, _ in enumerate(getattr(plan.source, collection, []))
            ]
            if plan.kind == "voice"
            else []
        )
        raise DSLError(
            "E_OVERRIDE_STALE",
            "materialized source changed; expand and select again",
            at,
            details={
                "current_materialized_id": current_guard,
                "targets": targets[:3],
                "total": len(targets),
                "truncated": len(targets) > 3,
            },
        )
    result = copy.deepcopy(plan)
    changes = data.get("set", {})
    obj(changes, at + "/set")
    additions_by_path = obj(data.get("append", {}), at + "/append")
    removals = array(data.get("remove", []), at + "/remove")
    paths = list(changes) + list(additions_by_path) + removals
    if any(not isinstance(path, str) or not path.startswith("/") for path in paths):
        raise DSLError("E_POINTER", "override paths must be JSON pointers", at)
    if len(paths) != len(set(paths)):
        raise DSLError("E_OVERRIDE", "duplicate override paths are ambiguous", at)
    if any(a != b and (a.startswith(b + "/") or b.startswith(a + "/")) for a in paths for b in paths):
        raise DSLError("E_OVERRIDE", "overlapping override paths are ambiguous", at)
    if plan.kind == "voice":
        value = clone(asdict(plan.source))
        original_origins = {}
        for op, collection in COLLECTIONS.items():
            matching = [item["origin"] for item in plan.layer_origins if item["collection"] == op]
            original_origins[collection] = [
                copy.deepcopy(matching[index] if index < len(matching) else plan.origins)
                | {"materialized_before": current_guard, "original_path": f"/{collection}/{index}"}
                for index, _ in enumerate(value[collection])
            ]
        for path, replacement in changes.items():
            replace(value, path, replacement, existing=True)
        for path, additions in additions_by_path.items():
            collection = get(value, path)
            if path.count("/") != 1 or path[1:] not in COLLECTIONS.values() or not isinstance(additions, list):
                raise DSLError("E_OVERRIDE", "append needs a Voice layer collection", at)
            collection.extend(copy.deepcopy(additions))
            original_origins[path[1:]].extend(
                [
                    copy.deepcopy(plan.origins) | {"original_path": None, "override_path": f"/append{path}/{index}"}
                    for index, _ in enumerate(additions)
                ]
            )
        for path in removals:
            pieces = path.split("/")
            if len(pieces) != 3 or pieces[1] not in COLLECTIONS.values() or not pieces[2].isdecimal():
                raise DSLError("E_OVERRIDE", "remove needs an explicit Voice layer index", at)
        for path in sorted(removals, key=lambda p: (p.rsplit("/", 1)[0], int(p.rsplit("/", 1)[1])), reverse=True):
            collection, index = parent(value, path)
            if not isinstance(collection, list) or path.split("/")[1] not in COLLECTIONS.values():
                raise DSLError("E_OVERRIDE", "remove needs an explicit Voice layer index", at)
            get(value, path)
            collection.pop(index)
            original_origins[path.split("/")[1]].pop(index)
        voice_fields(value, plan.sr, at)
        for op, name in COLLECTIONS.items():
            for layer in value.get(name, []):
                layer_fields(op, layer, at + "/" + name, sr=plan.sr)
        result.source = Voice.from_dict(value)
        result.layer_origins = [
            {
                "collection": op,
                "origin": origin
                | {
                    "edited_path": f"/{collection}/{index}",
                    "override_paths": [
                        path
                        for path in changes
                        if origin["original_path"] is not None
                        and (path == origin["original_path"] or path.startswith(origin["original_path"] + "/"))
                    ],
                },
            }
            for op, collection in COLLECTIONS.items()
            for index, origin in enumerate(original_origins[collection])
        ]
    elif plan.kind in ("score", "cue"):
        score = result.source.score if plan.kind == "cue" else result.source
        value = {
            "bus": {k: getattr(score, k) for k in ("hall", "echo", "lowpass", "effects", "seed")},
            "tracks": {
                name: {
                    "gain": t.gain,
                    "pan": t.pan,
                    "send": t.send,
                    "echo": t.echo,
                    "voice": t.voice,
                    "layers": [asdict(layer) for layer in t.layers],
                }
                for name, t in score.tracks.items()
            },
        }
        for path, replacement in changes.items():
            if any(key in path.split("/") for key in ("bpm", "meter", "start", "dur", "beat", "beats", "pitch")):
                raise DSLError("E_EDIT_REQUIRES_NOTES", "change musical timing/pitch before expansion", at)
            replace(value, path, replacement, existing=True)
        if data.get("append") or data.get("remove"):
            raise DSLError("E_OVERRIDE", "Score structural overrides require editing notes or a Voice", at)
        bus = value["bus"]
        number(bus["hall"], at + "/bus/hall", 0, 180)
        number(bus["lowpass"], at + "/bus/lowpass", 0)
        seed(bus["seed"], at + "/bus/seed")
        effect_fields(bus["effects"], at + "/bus/effects")
        if bus["echo"] is not None:
            echo = bus["echo"]
            if not isinstance(echo, list | tuple) or len(echo) != 3:
                raise DSLError("E_TYPE", "echo needs delay, feedback, and tone", at)
            for val, low, high in zip(echo, (1e-9, 0, 1e-9), (180, 0.95, None), strict=True):
                number(val, at + "/bus/echo", low, high)
        for key, replacement in value["bus"].items():
            setattr(score, key, replacement)
        reverse = {cls: op for op, cls in LAYERS.items()}
        for name, settings in value["tracks"].items():
            for key in ("gain", "pan", "send", "echo"):
                number(settings[key], at, -1 if key == "pan" else None, 1 if key == "pan" else None)
            known(settings["voice"], VOICE_BUS - {"seed"}, at + "/voice")
            voice_fields(settings["voice"], plan.sr, at + "/voice")
            track = score.tracks[name]
            for key in ("gain", "pan", "send", "echo", "voice"):
                setattr(track, key, settings[key])
            for index, fields_ in enumerate(settings["layers"]):
                cls = type(track.layers[index])
                layer_fields(reverse[cls], fields_, at, sr=plan.sr)
                track.layers[index] = cls(**fields_)
            # Preserve old recorded hashes: MIDI correctly rejects synthesis-layer edits.
    else:
        raise DSLError("E_CAPABILITY", "materialized refinement requires Voice, Score, or Cue", at)
    result.edited = True
    result.origins = result.origins | {
        "override": {
            "expected": data["expect"],
            "paths": paths,
            "materialized_before": digest(plan.materialized()),
            "seed_order_warning": bool(additions_by_path or removals),
        }
    }
    return result
