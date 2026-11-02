"""Bounded, revision-bound projections for agent discovery and diagnosis."""

import base64
import copy
import json
from dataclasses import asdict

from ..diagnostics import digest
from .model import DSLError
from .patch import get, target_pointer
from .responses import CONTROL_FIELDS, SCHEMA, respond, validate_response


def projection(rows, fields):
    """Bounded dictionary-only projection; no indexing, wildcards or expressions."""
    paths = [path.split(".") for path in fields]
    if len(paths) > 32 or any(not 1 <= len(path) <= 4 or any(not key for key in path) for path in paths):
        raise DSLError("E_FIELD", "project at most 32 dictionary paths, each up to four fields deep")
    valid = set()
    projected = []
    for row in rows:
        selected = {}
        for original, path in zip(fields, paths, strict=True):
            value = row
            for key in path:
                if not isinstance(value, dict) or key not in value:
                    break
                value = value[key]
            else:
                valid.add(original)
                target = selected
                for key in path[:-1]:
                    target = target.setdefault(key, {})
                target[path[-1]] = copy.deepcopy(value)
        projected.append(selected)
    if rows and set(fields) - valid:
        raise DSLError("E_FIELD", "unknown projected fields", suggestions=sorted(rows[0])[:3])
    return projected


def project_fields(result, fields):
    """Project object views while retaining identity needed for safe follow-up edits."""
    if not fields:
        return result
    retained = {"schema", "authored_revision", "materialized_id", "revision", "query_id", "analysis_id"}
    if result.get("schema") == SCHEMA:
        retained |= CONTROL_FIELDS
    return {key: value for key, value in result.items() if key in retained} | projection([result], fields)[0]


def page(items, identity, *, limit=10, cursor=None, fields=None):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise DSLError("E_LIMIT", "query limit must be 1..100")
    scope = digest({"identity": identity, "fields": fields, "limit": limit})
    offset = 0
    if cursor:
        try:
            decoded = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
            if decoded["scope"] != scope or type(decoded["offset"]) is not int or decoded["offset"] < 0:
                raise ValueError()
            offset = decoded["offset"]
        except (ValueError, KeyError, TypeError):
            raise DSLError("E_CURSOR", "cursor does not match this revision/view/query") from None
    selected = items[offset : offset + limit]
    if fields:
        # Validate against the query's full row shape, not just this page.
        selected = projection(items, fields)[offset : offset + limit]
    more = offset + len(selected) < len(items)
    next_ = (
        base64.urlsafe_b64encode(json.dumps({"scope": scope, "offset": offset + limit}).encode()).decode().rstrip("=")
        if more
        else None
    )
    return {
        "schema": "tune.query/1",
        "query_id": scope,
        "items": selected,
        "total": len(items),
        "returned": len(selected),
        "truncated": more,
        "next": next_,
    }


def bounded(value, *, limit=10, depth=5):
    omitted = []

    def visit(item, at="", level=0):
        if level >= depth and isinstance(item, dict | list):
            omitted.append(at)
            return {"omitted": len(item)}
        if isinstance(item, list):
            if len(item) > limit:
                omitted.append(at)
            return [visit(child, at + "/" + str(i), level + 1) for i, child in enumerate(item[:limit])]
        if isinstance(item, dict):
            if len(item) > 32:
                omitted.append(at)
            return {key: visit(child, at + "/" + key, level + 1) for key, child in list(item.items())[:32]}
        if isinstance(item, str) and len(item) > 1000:
            omitted.append(at)
            return item[:1000]
        return item

    return visit(value), omitted[:100]


def impact(document, selected):
    from urllib.parse import unquote

    from .compiler import Compiler
    from .model import pointer

    if selected.startswith("sound:"):
        return [unquote(selected.split("/", 1)[0].partition(":")[2])]
    name = unquote(selected.split("/", 1)[0].partition(":")[2])
    affected = []
    for sound, body in document.data["sounds"].items():
        compiler = Compiler(document)
        compiler.prepare(body, document.context, pointer("/sounds", sound), "sound:" + sound)
        if any(item.get("definition") == name for origin in compiler.source_map for item in origin["chain"]):
            affected.append(sound)
    return affected


def authored(document, target=None, *, pointer=None, limit=10, response="detailed"):
    validate_response(response)
    if target is not None and pointer is not None:
        raise DSLError("E_TARGET", "choose target or pointer")
    pointer = target_pointer(document.data, target) if target else pointer or "/sounds"
    value = get(document.data, pointer)
    fragment, omitted = bounded(value, limit=limit)
    result = {
        "schema": "tune.query/1",
        "authored_revision": document.revision,
        "target": target,
        "pointer": pointer,
        "fragment": fragment,
        "omitted": omitted,
        "truncated": bool(omitted),
    }
    if target:
        affected = impact(document, target)
        result.update(affected=affected[:limit], affected_total=len(affected))
    return respond(result, "query", response)


def expansion(result, *, view="layers", limit=10, cursor=None, fields=None, response="detailed"):
    from .adapters import materialized_id

    validate_response(response, view)
    plan = result.plan
    if view not in ("layers", "events", "full"):
        raise DSLError("E_ENUM", "unknown expansion view")
    items = []
    if view == "events" and plan.kind not in ("score", "cue"):
        pass
    elif plan.kind == "voice":
        if view == "full":
            from .registry import VOICE_BUS

            items.append(
                {
                    "path": "",
                    "kind": "voice_bus",
                    "fields": {key: getattr(plan.source, key) for key in sorted(VOICE_BUS)},
                }
            )
        for name in ("syllables", "chips", "speech", "vocoded", "spoken", "modal", "noise", "scatter"):
            for index, layer in enumerate(getattr(plan.source, name)):
                values, omitted = bounded(asdict(layer), limit=limit, depth=2)
                items.append({"path": f"/{name}/{index}", "kind": name, "fields": values, "omitted": omitted})
    elif plan.kind in ("score", "cue"):
        score = plan.source.score if plan.kind == "cue" else plan.source
        if view == "events":
            items = [
                {"track": track.name}
                | {
                    key: event[key]
                    for key in (
                        "id",
                        "instrument",
                        "note",
                        "pitch",
                        "beat",
                        "beats",
                        "offset",
                        "velocity",
                        "start",
                        "duration",
                    )
                }
                for track in score.tracks.values()
                for event in track.events
            ]
        else:
            from .model import pointer
            from .registry import LAYERS

            if view == "full":
                items.append(
                    {
                        "path": "/bus",
                        "kind": "score_bus",
                        "fields": {key: getattr(score, key) for key in ("hall", "echo", "lowpass", "effects", "seed")},
                    }
                )
            kinds = {cls: name for name, cls in LAYERS.items()}
            for track in score.tracks.values():
                base = pointer("/tracks", track.name)
                if view == "full":
                    items.append(
                        {
                            "path": base,
                            "kind": "track",
                            "fields": {key: getattr(track, key) for key in ("gain", "pan", "send", "echo", "voice")},
                        }
                    )
                for index, layer in enumerate(track.layers):
                    values, omitted = bounded(asdict(layer), limit=limit, depth=2)
                    items.append(
                        {
                            "path": f"{base}/layers/{index}",
                            "kind": kinds[type(layer)],
                            "track": track.name,
                            "fields": values,
                            "omitted": omitted,
                        }
                    )
    else:
        items = [{"kind": plan.kind, "span_s": float(plan.span) if plan.span is not None else None}]
    identity = {"revision": result.document.revision, "materialized": materialized_id(plan), "view": view}
    detail = page(items, identity, limit=limit, cursor=cursor, fields=fields) | {
        "authored_revision": result.document.revision,
        "materialized_id": identity["materialized"],
        "type": plan.kind,
    }
    return respond(detail, "expand", response)


def inspection(
    captured,
    *,
    view="summary",
    start=0,
    end=None,
    band=None,
    node_id=None,
    top=None,
    limit=10,
    cursor=None,
    fields=None,
    pitch=False,
    response="detailed",
):
    from ..inspection import ANALYZER, _project_layer, band_power, inspect_audio

    validate_response(response, view)
    if view not in ("summary", "layers", "events", "stages", "full"):
        raise DSLError("E_ENUM", "unknown inspection view")
    if view == "full":
        from ..inspection import inspect_capture

        return inspect_capture(captured, start=start, end=end, band=band, node_id=node_id, pitch=pitch)
    manifest = captured.manifest
    nodes = {node["id"]: node for node in manifest["nodes"]}
    chosen = node_id or manifest["root"]
    if chosen not in nodes:
        raise DSLError("E_TARGET", "unknown processing stage")
    node = nodes[chosen]
    if node["kind"] == "cue":
        node = nodes[node["child"]]
    identity = {
        "analyzer": ANALYZER + "/projection-1",
        "pcm_id": manifest["pcm_id"],
        "revision": manifest["revision"],
        "node": node["id"],
        "start": start,
        "end": len(captured.audio) / captured.sr if end is None else end,
        "band": band,
        "pitch": pitch,
    }
    # Validate the selected query even for silence/empty input, without building planned/source reports.
    band_power(captured.audio, captured.sr, start, end, band)
    if view == "summary":
        audio = inspect_audio(captured.audio, captured.sr, start=start, end=end, band=band, pitch=pitch)
        result = {
            "schema": "tune.query/1",
            "analysis_id": digest(identity),
            "query_id": digest(identity | {"view": view}),
            **{key: audio[key] for key in ("status", "duration", "frames", "channels", "sample_rate", "levels")},
            "revision": manifest["revision"],
            "pcm_id": manifest["pcm_id"],
            "root_stage": manifest["root"],
            "stage_count": len(nodes),
            "capabilities": manifest.get("dsl", {}).get("capabilities"),
            "attribution": "channel-sum power; shared effects and cancellation are not additive",
        }
        return project_fields(respond(result, "inspect", response), fields)
    if view == "stages":
        items = [
            {
                "id": stage["id"],
                "kind": stage["kind"],
                "parent": stage["parent"],
                "parts": len(stage["parts"]),
                "name": stage.get("track", {}).get("name"),
            }
            for stage in nodes.values()
        ]
    elif view == "events":
        items = [
            {key: event[key] for key in ("id", "instrument", "pitch", "start", "duration", "velocity")}
            | {"track": stage["track"]["name"], "source": event.get("dsl_origin")}
            for stage in nodes.values()
            if "track" in stage
            for event in stage["track"]["events"]
        ]
    else:
        items = []
        for part in node["parts"]:
            source = part.get("dsl_origin") or part.get("origin")
            item = {
                "id": part["id"],
                "label": part["label"],
                "kind": part["label"].split("[")[0],
                "power": band_power(_project_layer(captured, node, part), captured.sr, start, end, band),
                "stage": part["stage"],
                "event": part["event"],
                "target": source.get("target") if isinstance(source, dict) else None,
            }
            if fields and "source" in fields:
                item["source"] = copy.deepcopy(source)
            if part.get("child"):
                item["child"] = part["child"]
            if fields and "parameters" in fields:
                item["parameters"], item["omitted"] = bounded(part["params"])
            items.append(item)
        items.sort(key=lambda item: item["power"], reverse=True)
        if top is not None:
            if type(top) is not int or not 1 <= top <= 100:
                raise DSLError("E_LIMIT", "top must be 1..100")
            items = items[:top]
    result = page(items, identity | {"view": view, "top": top}, limit=limit, cursor=cursor, fields=fields) | {
        "analysis_id": digest(identity),
        "revision": manifest["revision"],
        "stage": node["id"],
        "window_s": [start, identity["end"]],
        "band_hz": band,
        "measure": "channel-sum energy before parent bus; not additive attribution",
    }
    return respond(result, "inspect", response)
