"""Observational render capture. IDs describe buffers; they never seed the synthesizer."""
from __future__ import annotations

import contextvars
import hashlib
import inspect
import json
import platform
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import scipy

SCHEMA = 1
BEHAVIOR = "legacy-1"
_active: contextvars.ContextVar[Recorder | None] = contextvars.ContextVar("tune_capture", default=None)


def _json_value(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"unsupported diagnostic value: {type(value).__name__}")


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False, default=_json_value).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def pcm_id(audio, sr: int) -> str:
    y = np.asarray(audio, dtype="<f4")
    if y.ndim not in (1, 2) or (y.ndim == 2 and y.shape[1] not in (1, 2)) or sr < 1:
        raise ValueError("audio must be mono/stereo samples with a positive sample rate")
    if not np.isfinite(y).all():
        raise ValueError("audio contains non-finite samples")
    h = hashlib.sha256(canonical({"shape": list(y.shape), "rate": sr, "dtype": "<f4"}))
    h.update(np.ascontiguousarray(y).tobytes())
    return h.hexdigest()


def origin() -> dict:
    """Caller location for authoring only; never evaluated as executable source."""
    frame = inspect.currentframe()
    try:
        frame = frame.f_back.f_back
        return {"file": frame.f_code.co_filename, "line": frame.f_lineno}
    finally:
        del frame


@dataclass(frozen=True)
class Limits:
    seconds: float = 180
    layers: int = 1024
    bytes: int = 256 * 1024 * 1024


def current() -> Recorder | None:
    return _active.get()


def definition(source) -> dict:
    from .spec import Voice
    if isinstance(source, Voice):
        return {"kind": "voice", "spec": source.to_dict()}
    if hasattr(source, "score") and not hasattr(source, "tracks"):
        return {"kind": "cue", "cue": {k: getattr(source, k) for k in ("kind", "style", "seed", "loop", "end")},
                "score": definition(source.score)}
    if hasattr(source, "tracks"):
        return {"kind": "score", "settings": {k: getattr(source, k) for k in
                ("bpm", "meter", "hall", "echo", "lowpass", "seed", "sr")},
                "effects": getattr(source, "effects", []),
                "tracks": [{"name": t.name, "gain": t.gain, "pan": t.pan, "send": t.send,
                            "echo": t.echo, "voice": t.voice, "events": t.events,
                            "origins": t.origins, "layers": [asdict(x) for x in t.layers]}
                           for t in source.tracks.values()],
                "sounds": [{"at": at, "pcm": pcm_id(y, source.sr), "gain": g, "pan": pan,
                            "send": send, "echo": echo, "origin": source.placed_origins[i]}
                           for i, (at, y, g, pan, send, echo) in enumerate(source.sounds)]}
    return {"kind": "audio", "origin": "unknown"}


def renderer_id() -> dict:
    base = Path(__file__).parent
    files = {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(base.rglob("*.py"))}
    return {"behavior": BEHAVIOR, "code": digest(files), "python": platform.python_version(),
            "numpy": np.__version__, "scipy": scipy.__version__, "platform": platform.machine()}


@dataclass
class Recorder:
    sr: int
    limits: Limits
    nodes: list = field(default_factory=list)
    stack: list = field(default_factory=list)
    arrays: dict = field(default_factory=dict)
    used: int = 0
    layer_count: int = 0
    last: str | None = None

    def put(self, audio) -> str:
        y = np.asarray(audio)
        if len(y) / self.sr > self.limits.seconds or self.used + y.nbytes > self.limits.bytes:
            raise ValueError("capture duration/memory limit exceeded")
        if not np.isfinite(y).all():
            raise ValueError("capture contains non-finite samples")
        key = f"a{len(self.arrays)}"
        self.arrays[key] = y.copy()
        self.used += y.nbytes
        return key

    def begin(self, kind, params) -> dict:
        node = {"id": f"n{len(self.nodes)}", "kind": kind, "params": params,
                "parent": self.stack[-1]["id"] if self.stack else None, "parts": [], "factors": {}}
        self.nodes.append(node)
        self.stack.append(node)
        return node

    def factor(self, name, value):
        if self.stack:
            self.stack[-1]["factors"][name] = value

    def part(self, node, audio, start, label, *, seed=None, params=None, child=None, event=None):
        self.layer_count += 1
        if self.layer_count > self.limits.layers:
            raise ValueError("capture layer-count limit exceeded")
        node["parts"].append({"id": f"{node['id']}/p{len(node['parts'])}", "audio": self.put(audio),
                              "start": int(start), "label": label, "seed": seed,
                              "params": params, "child": child, "event": event,
                              "stage": "layer_output_before_voice_bus" if node["kind"] == "voice"
                              else "imported_pcm" if node["kind"] == "audio"
                              else "part_output_before_score_bus"})

    def end(self, node, audio):
        node["audio"] = self.put(audio)
        assert self.stack.pop() is node
        self.last = node["id"]


@dataclass
class Capture:
    audio: np.ndarray
    sr: int
    manifest: dict
    arrays: dict

    def replay(self, *, mute=(), solo=None) -> np.ndarray:
        """Diagnostic intervention with original time support and frozen bus factors."""
        from .render import process_voice
        from .score import Score, _pan
        nodes = {n["id"]: n for n in self.manifest["nodes"]}
        valid = {p["id"] for n in nodes.values() for p in n["parts"]}
        selected = set(mute) | (set(solo) if solo is not None else set())
        if not selected <= valid:
            raise ValueError("unknown diagnostic layer ID")

        def visit(node_id, inherited=False):
            n = nodes[node_id]
            original = self.arrays[n["audio"]]
            if n["kind"] == "cue":
                y = visit(n["child"], inherited).copy()
                end, fade = n["params"]["end_samples"], n["params"]["fade_samples"]
                y = y[:end]
                if fade:
                    y[-fade:] *= np.linspace(1, 0, fade)[:, None] ** 2
                return y
            pieces = []
            for p in n["parts"]:
                y = visit(p["child"], inherited or (solo is not None and p["id"] in solo)) if p["child"] \
                    else self.arrays[p["audio"]].copy()
                if p["child"]:
                    from .render import PEAK
                    y = y.astype(np.float64) / PEAK * p["track_gain"] if "track_gain" in p \
                        else y.astype(np.float64) * p.get("child_scale", 1) if p.get("child_conversion") == "float64" \
                        else y * p.get("child_scale", 1)
                # Selecting a descendant retains its ancestors. Selecting a parent retains its descendants.
                descendants = set()
                def ids(child, descendants=descendants):
                    for entry in nodes[child]["parts"]:
                        descendants.add(entry["id"])
                        if entry["child"]:
                            ids(entry["child"])
                if p["child"]:
                    ids(p["child"])
                allowed = inherited or solo is None or p["id"] in solo or bool(descendants & set(solo))
                if p["id"] in mute or not allowed:
                    y = np.zeros_like(y)
                pieces.append((p, y))
            if n["kind"] == "voice":
                from .spec import Voice
                out = np.zeros(n["input_length"])
                for p, y in pieces:
                    out[p["start"]:p["start"] + len(y)] += y
                return process_voice(out, Voice.from_dict(n["params"]), self.sr, fixed=n["factors"])
            if n["kind"] == "audio":
                return pieces[0][1] if pieces else original.copy()
            s = Score(**n["params"])
            dry, bus, ebus = np.zeros((n["input_length"], 2)), np.zeros(n["input_length"]), np.zeros(n["input_length"])
            for p, y in pieces:
                k = p["start"]
                settings = p["params"]
                stereo = y if y.ndim == 2 else y[:, None] * _pan(settings["pan"])
                mono = y if y.ndim == 1 else y.mean(axis=1)
                dry[k:k + len(y)] += stereo
                bus[k:k + len(y)] += settings["send"] * mono
                ebus[k:k + len(y)] += settings["echo"] * mono
            factors = {key: self.arrays[value] if key.startswith("effect_") and key.endswith("_gain") else value
                       for key, value in n["factors"].items()}
            return s.finish(dry, bus, ebus, loop=n["loop"], gain=n["gain"], fixed=factors)

        return visit(self.manifest["root"])


def capture(source, sr: int | None = None, *, loop=None, gain=1.0, limits: Limits | None = None) -> Capture:
    from .render import DEFAULT_SR, render
    from .spec import Voice
    rate = int(sr or getattr(source, "sr", DEFAULT_SR))
    if rate < 1000 or rate > 192000:
        raise ValueError("capture sample rate must be 1000..192000 Hz")
    rec = Recorder(rate, limits or Limits())
    if hasattr(source, "tracks") and sum(len(t.layers) for t in source.tracks.values()) > rec.limits.layers:
        raise ValueError("capture layer-count limit exceeded")
    if hasattr(source, "tracks"):
        ends = [layer.start + getattr(layer, "dur", 0) for t in source.tracks.values() for layer in t.layers]
        ends += [at + len(y) / rate for at, y, *_ in source.sounds]
        if ends and max(ends) + source.hall > rec.limits.seconds:
            raise ValueError("capture duration limit exceeded")
    before = json.loads(canonical(definition(source)))
    if isinstance(source, Voice) and source.duration > rec.limits.seconds:
        raise ValueError("capture duration limit exceeded")
    token = _active.set(rec)
    try:
        if isinstance(source, Voice):
            y = render(source, rate)
        elif hasattr(source, "tracks"):
            if rate != source.sr:
                raise ValueError("capture rate must match Score.sr")
            y = source.render(loop=loop, gain=gain)
        elif hasattr(source, "render"):
            if rate != source.sr:
                raise ValueError("capture rate must match Cue.sr")
            y = source.render()
        else:
            y = np.asarray(source, dtype=np.float32)
            node = rec.begin("audio", {"origin": "unknown"})
            rec.part(node, y, 0, "imported audio")
            rec.end(node, y)
    finally:
        _active.reset(token)
    assets = {}
    data = Path(__file__).parent / "speech" / "data"
    for node in rec.nodes:
        if node["kind"] != "voice":
            continue
        names = ["barks.npz", "barks_audio.npz"] if node["params"].get("vocoded") else []
        for spoken in node["params"].get("spoken", []):
            bank = spoken["bank"].replace("/", "_")
            names.extend([f"bank_{bank}.npz", f"bank_{bank}.json"])
        for name in names:
            path = data / name
            assets[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    manifest = {"schema": SCHEMA, "source": before, "source_id": digest(before), "sample_rate": rate,
                "renderer": renderer_id(), "assets": assets, "nodes": rec.nodes, "root": rec.last,
                "replay": "materialized_buffers", "source_regeneration": "not_guaranteed",
                "limits": asdict(rec.limits), "pcm_id": pcm_id(y, rate)}
    buffers = {key: {"sha256": hashlib.sha256(value.tobytes()).hexdigest(),
                     "dtype": value.dtype.str, "shape": list(value.shape)} for key, value in rec.arrays.items()}
    manifest["buffers"] = buffers
    manifest["render_id"] = digest({k: manifest[k] for k in
                                   ("source_id", "sample_rate", "renderer", "assets") } | {"buffers": buffers})
    manifest = json.loads(canonical(manifest))
    manifest["revision"] = digest(manifest)
    return Capture(y, rate, manifest, rec.arrays)
