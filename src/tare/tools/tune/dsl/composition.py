"""Compose existing captures without flattening their buses or changing their samples."""

import copy
import hashlib
import json
from dataclasses import replace

import numpy as np

from ..diagnostics import Limits, canonical, capture, digest, pcm_id
from .model import Budgets, DSLError


def finalize(captured):
    manifest = captured.manifest
    for key in ("files", "playback_id", "bundle_id", "revision"):
        manifest.pop(key, None)
    limits = manifest["limits"]
    if sum(value.nbytes for value in captured.arrays.values()) > limits["bytes"]:
        raise DSLError("E_LIMIT", "cumulative capture memory limit exceeded")
    if sum(len(node["parts"]) for node in manifest["nodes"]) > limits["layers"]:
        raise DSLError("E_LIMIT", "cumulative captured part limit exceeded")
    manifest["buffers"] = {
        key: {
            "shape": list(value.shape),
            "dtype": value.dtype.str,
            "sha256": hashlib.sha256(value.tobytes()).hexdigest(),
        }
        for key, value in captured.arrays.items()
    }
    manifest["pcm_id"] = pcm_id(captured.audio, captured.sr)
    manifest["source_id"] = digest(
        {"source": manifest["source"], "dsl": manifest.get("dsl"), "graph": manifest["nodes"]}
    )
    manifest["render_id"] = digest(
        {key: manifest.get(key) for key in ("source_id", "sample_rate", "renderer", "assets", "buffers")}
    )
    captured.manifest = json.loads(canonical(manifest))
    captured.manifest["revision"] = digest(captured.manifest)
    return captured


def _attach(parent, part, child, origin, scale):
    nodes = {n["id"]: f"n{len(parent.manifest['nodes']) + i}" for i, n in enumerate(child.manifest["nodes"])}
    arrays = {key: f"a{len(parent.arrays) + i}" for i, key in enumerate(child.arrays)}
    parent.arrays.update({arrays[key]: value for key, value in child.arrays.items()})
    for original in child.manifest["nodes"]:
        node = copy.deepcopy(original)
        node["id"] = nodes[original["id"]]
        node["audio"] = arrays[node["audio"]]
        node["parent"] = nodes.get(node["parent"]) if node["parent"] else part["node_parent"]
        if node.get("child"):
            node["child"] = nodes[node["child"]]
        for key, value in node["factors"].items():
            if key.startswith("effect_") and key.endswith("_gain"):
                node["factors"][key] = arrays[value]
        for i, layer in enumerate(node["parts"]):
            layer["id"] = f"{node['id']}/p{i}"
            layer["audio"] = arrays[layer["audio"]]
            if layer.get("child"):
                layer["child"] = nodes[layer["child"]]
            previous = layer.get("dsl_origin", {})
            layer["dsl_origin"] = previous | {
                "placements": [
                    *previous.get("placements", []),
                    {"target": origin.get("target"), "occurrence": origin.get("occurrence")},
                ]
            }
        parent.manifest["nodes"].append(node)
    part.update(child=nodes[child.manifest["root"]], child_conversion="float64", child_scale=scale, dsl_origin=origin)
    part.pop("node_parent", None)
    parent.manifest["assets"].update(child.manifest["assets"])
    parent.manifest["schema"] = 2


def capture_plan(plan, *, limits=None, _cache=None):
    limits = limits or Budgets()
    cache = {} if _cache is None else _cache
    if id(plan) in cache:
        return cache[id(plan)]
    capture_limits = Limits(seconds=limits.seconds, layers=limits.layers, bytes=limits.capture_bytes)
    children = []
    source = plan.source
    if plan.kind == "fm":
        from ..effects import fm_tone

        source = fm_tone(sr=plan.sr, **source)
    elif plan.kind == "rest":
        source = np.zeros(round(source * plan.sr), np.float32)
    if plan.placements:
        source = copy.copy(source)
        source.sounds = list(source.sounds)
        source.placed_origins = list(source.placed_origins)
        retained = 0
        for entry in plan.placements:
            remaining = limits.capture_bytes - retained
            if remaining <= 0:
                raise DSLError("E_LIMIT", "composition exceeds cumulative capture budget")
            child = capture_plan(entry["plan"], limits=replace(limits, capture_bytes=remaining), _cache=cache)
            retained += sum(a.nbytes for a in child.arrays.values()) + child.audio.size * 8
            if retained > limits.capture_bytes or retained > limits.work_bytes:
                raise DSLError("E_LIMIT", "composition exceeds cumulative capture/work budget")
            if child.audio.ndim == 2 and entry["pan"]:
                raise DSLError("E_PAN", "nonzero pan on stereo audio is unsupported", entry["plan"].origins["pointer"])
            settings = {key: entry[key] for key in ("at", "gain", "pan", "send", "echo")}
            source.add(child.audio, **settings)
            source.placed_origins[-1]["dsl_origin"] = entry["plan"].origins
            children.append((entry, child))
        frames = max((int(e["at"] * plan.sr) + len(c.audio) for e, c in children), default=0)
        frames += round(source.hall * plan.sr)
        if frames / plan.sr > limits.seconds or retained + frames * 2 * 16 > limits.capture_bytes:
            raise DSLError("E_LIMIT", "composition exceeds cumulative duration/capture budget")
    result = capture(source, plan.sr, loop=plan.loop, gain=plan.gain, limits=capture_limits)
    root = next(n for n in result.manifest["nodes"] if n["id"] == result.manifest["root"])
    if children:
        for (entry, child), part in zip(children, root["parts"][-len(children) :], strict=True):
            part["node_parent"] = root["id"]
            _attach(result, part, child, entry["plan"].origins | {"occurrence": entry["occurrence"]}, entry["gain"])
    for node in result.manifest["nodes"]:
        if "track" in node:
            for part in node["parts"]:
                event = next((e for e in node["track"]["events"] if e["id"] == part["event"]), None)
                if event and "dsl_origin" in event:
                    part["dsl_origin"] = event["dsl_origin"]
        if node["id"] == result.manifest["root"] and plan.layer_origins:
            from .registry import COLLECTIONS

            ordered = [
                item["origin"]
                for collection in ("syllables", "chips", "speech", "vocoded", "spoken", "modal", "noise", "scatter")
                for item in plan.layer_origins
                if COLLECTIONS[item["collection"]] == collection
            ]
            for part, origin in zip(node["parts"], ordered, strict=True):
                part["dsl_origin"] = origin
        for part in node["parts"]:
            part.setdefault("dsl_origin", plan.origins)
    cache[id(plan)] = result
    return finalize(result)
