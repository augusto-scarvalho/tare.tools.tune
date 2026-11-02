"""Selected-target editing guidance from archived source and explicit schemas."""

import copy
import re
from urllib.parse import quote, unquote

from .model import DSLError
from .model import pointer as child_pointer
from .patch import get, target_pointer
from .query import page
from .registry import COLLECTIONS, FIELDS, LAYERS, TRACK_FIELDS, catalog, layer_schema
from .review_data import small
from .validate import load


def archived_document(captured):
    metadata = captured.manifest.get("dsl")
    if not metadata:
        raise DSLError("E_CAPABILITY", "capture has no editable DSL source")
    return load(metadata["path"], data=metadata["document"])


def _op(node):
    return next((key for key in FIELDS if key in node), None) if isinstance(node, dict) else None


def _uses(node):
    if isinstance(node, dict):
        if isinstance(node.get("use"), str):
            yield node["use"]
        for item in node.values():
            yield from _uses(item)
    elif isinstance(node, list):
        for item in node:
            yield from _uses(item)


def affected(data, definition):
    def refers(node, seen):
        for name in _uses(node):
            if name == definition:
                return True
            if name not in seen and name in data.get("defs", {}):
                if refers(data["defs"][name], seen | {name}):
                    return True
        return False

    return [name for name, node in data["sounds"].items() if refers(node, set())]


def candidates(captured, words, *, limit=10, cursor=None):
    document = archived_document(captured)
    terms = words.casefold().split()
    if not terms or len(words) > 256:
        raise DSLError("E_TARGET", "find needs 1..256 characters")
    found = []
    for group, prefix in (("sounds", "sound"), ("defs", "def")):
        for name, node in document.data.get(group, {}).items():
            body = node.get("body", {}) if group == "defs" else node
            op = _op(body)
            labels = [name, op or "", *[v for v in body.values() if isinstance(v, str)]]
            labels += [v for d in body.values() if isinstance(d, dict) for v in d.values() if isinstance(v, str)]
            if op == "use":
                base = document.data.get("defs", {}).get(body["use"], {}).get("body", {})
                labels += [v for v in base.values() if isinstance(v, str)]
            if all(term in " ".join(labels).casefold() for term in terms):
                found.append(
                    {"target": prefix + ":" + quote(name, safe=""), "kind": op, "name": name, "source": small(body, 3)}
                )
    return page(found, {"revision": captured.manifest["revision"], "find": words}, limit=limit, cursor=cursor)


def _root_parts(captured):
    root = next(node for node in captured.manifest["nodes"] if node["id"] == captured.manifest["root"])
    return root, root["parts"]


def layer_selection(captured, layer):
    root, parts = _root_parts(captured)
    match = next((part for node in captured.manifest["nodes"] for part in node["parts"] if part["id"] == layer), None)
    if match is None:
        raise DSLError("E_TARGET", "unknown captured layer")
    label = re.fullmatch(r"(\w+)\[(\d+)\]", match["label"])
    current = "/" + label[1] + "/" + label[2] if label else None
    origin = match.get("dsl_origin", {})
    original = origin.get("original_path", current)
    supported = root["kind"] == "voice" and any(p["id"] == layer for p in parts) and original is not None
    kind = next((k for k, v in COLLECTIONS.items() if label and v == label[1]), None)
    return match, {
        "id": layer,
        "kind": kind,
        "current_path": current,
        "original_path": original,
        "can_refine": supported,
        **(
            {
                "reason": "review refinement needs an original root Voice layer; "
                "use authored append or expand/patch otherwise"
            }
            if not supported
            else {}
        ),
    }


def describe(captured, *, target=None, find=None, layer=None, fields=None, limit=8, cursor=None):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise DSLError("E_LIMIT", "description limit must be 1..100")
    if sum(value is not None for value in (target, find, layer)) > 1:
        raise DSLError("E_SELECTION", "choose one target, find query or layer")
    result = {"schema": "tune.describe/1", "revision": captured.manifest["revision"]}
    metadata = captured.manifest.get("dsl", {})
    context = metadata.get("review", {})
    writable = bool(context.get("materialized_id")) and not context.get("draft", False)
    result["can_edit"] = writable
    if not writable:
        result["read_only_reason"] = "create a fresh source review; archived or draft captures cannot authorize edits"
    if find is not None:
        result["matches"] = candidates(captured, find, limit=limit, cursor=cursor)
        return result
    if not metadata:
        result["reason"] = "capture has no DSL source"
        return result
    document = archived_document(captured)
    if layer:
        part, selected = layer_selection(captured, layer)
        descriptors = layer_schema(selected["kind"], LAYERS[selected["kind"]]) if selected["kind"] else {}
        values = part["params"]
        rows = [
            {"name": name, "path": "/" + name, **copy.deepcopy(spec), "current": small(values.get(name))}
            for name, spec in descriptors.items()
        ]
        result.update(
            layer=selected,
            source=small(part.get("dsl_origin", {})),
            operations=["refine"] if writable and selected["can_refine"] else [],
        )
    else:
        target = target or "sound:" + quote(metadata["sound"], safe="")
        pointer = target_pointer(document.data, target)
        node = get(document.data, pointer)
        base = target.split("/", 1)[0]
        if base != "sound:" + quote(metadata["sound"], safe="") and (
            not base.startswith("def:")
            or metadata["sound"] not in affected(document.data, unquote(base.partition(":")[2]))
        ):
            writable = result["can_edit"] = False
            result["read_only_reason"] = "review a sound affected by this target before editing"
        rows = []
        scope = "authored"
        if target.startswith("def:") and "body" in node:
            for name, spec in node.get("params", {}).items():
                rows.append(
                    {
                        "name": name,
                        "path": child_pointer("/params", name) + "/default",
                        **copy.deepcopy(spec),
                        "current": small(spec.get("default")),
                    }
                )
            scope = "shared_definition"
            names = affected(document.data, unquote(target.partition(":")[2]))
            result.update(affected=names[:limit], affected_total=len(names))
        elif _op(node) == "use":
            definition = document.data["defs"][node["use"]]
            for name, spec in definition.get("params", {}).items():
                rows.append(
                    {
                        "name": name,
                        "path": child_pointer("/with", name),
                        **copy.deepcopy(spec),
                        "current": small(node.get("with", {}).get(name, spec.get("default"))),
                    }
                )
            scope = "invocation"
            result["definition"] = node["use"]
        else:
            op = _op(node)
            schemas = catalog("op", op)[0]["fields"] if op else {}
            if op == "score":
                schemas = schemas.get("score", {}).get("properties", {})
                values, prefix = node["score"], "/score"
            else:
                values, prefix = node, ""
            names = (
                sorted((set(values) | set(schemas)) - {op, "id", "then", "span"})
                if op
                else sorted(TRACK_FIELDS & set(values))
            )
            for name in names:
                spec = schemas.get(name, {})
                rows.append(
                    {
                        "name": name,
                        "path": prefix + "/" + name,
                        **copy.deepcopy(spec),
                        "current": small(values.get(name, spec.get("default"))),
                    }
                )
            if op == "sfx":
                knobs = catalog("sfx", node["sfx"])[0]["knobs"]
                for name, spec in knobs.items():
                    rows.append(
                        {
                            "name": "knobs." + name,
                            "path": "/knobs/" + name,
                            **spec,
                            "current": small(node.get("knobs", {}).get(name, spec.get("default"))),
                        }
                    )
            voice = values.get("speaker") if op in ("say", "emote") else None
            if isinstance(voice, dict):  # its fields as speaker.NAME, current as the preset or the override has it
                from ..speech import PRESETS, Speaker

                preset = Speaker.preset(voice["speaker"]) if voice.get("speaker") in PRESETS else None
                for name, spec in catalog("op", "speaker")[0]["fields"].items():
                    if name not in ("then", "span"):
                        rows.append(
                            {
                                "name": "speaker." + name,
                                "path": "/speaker/" + name,
                                **copy.deepcopy(spec),
                                "current": small(voice.get(name, getattr(preset, name, spec.get("default")))),
                            }
                        )
        result.update(target=target, pointer=pointer, scope=scope, operations=["set"] if writable else [])
        root, parts = _root_parts(captured)
        if target == "sound:" + quote(metadata["sound"], safe=""):
            if writable and root["kind"] == "voice":
                result["operations"].append("refine")
            result["layers"] = [{"id": p["id"], "label": p["label"]} for p in parts[:limit]]
            result["layer_total"] = len(parts)
    if fields:
        if not isinstance(fields, list | tuple) or len(fields) > 32 or any(not isinstance(f, str) for f in fields):
            raise DSLError("E_FIELD", "select at most 32 field names")
        wanted = set(fields)
        available = {row["name"] for row in rows}
        if wanted - available:
            near = sorted(n for n in available if n.rpartition(".")[2] in wanted)  # engine -> speaker.engine
            raise DSLError("E_FIELD", "unknown selected fields", suggestions=(near or sorted(available))[:3])
        rows = [row for row in rows if row["name"] in wanted]
    result["fields"] = rows[:limit]
    result["field_total"] = len(rows)
    result["truncated"] = len(rows) > limit
    return result
