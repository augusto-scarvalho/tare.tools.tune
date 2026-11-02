"""Bounded expression expansion, then lowering to the existing engine objects."""

from __future__ import annotations

import copy
import hashlib
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote

from ..diagnostics import canonical, digest
from ..score import Score
from . import adapters, transforms
from .adapters import capabilities
from .model import Budget, CompileResult, DSLError, Expr, NoteSequence, SoundPlan, pointer
from .notes import combine as combine_notes
from .notes import leaf as note_leaf
from .registry import LAYERS, META, NOTE_OPS, TRACK_FIELDS
from .units import quantity
from .validate import effect_fields, expression, known, load, number, operation, parameter_value, seed, voice_fields


def substitute(value, bindings, at="", budget=None):
    if isinstance(value, dict):
        if set(value) == {"param"}:
            name = value["param"]
            if not isinstance(name, str):
                raise DSLError("E_PARAMETER", "parameter slot needs a string name", at)
            if name not in bindings:
                raise DSLError("E_PARAMETER", f"unbound parameter {name!r}", at)
            if budget is not None:
                budget.charge("expansion_bytes", len(canonical(bindings[name])), at)
            return copy.deepcopy(bindings[name])
        return {key: substitute(child, bindings, pointer(at, key), budget) for key, child in value.items()}
    if isinstance(value, list):
        return [substitute(child, bindings, pointer(at, i), budget) for i, child in enumerate(value)]
    return value


class Compiler:
    def __init__(self, document):
        self.document = document
        self.budget = Budget(document.limits)
        self.dependencies, self.source_map, self.warnings = {}, [], []

    def prepare(self, value, context, at, target, *, stack=(), weight=1, chain=()):
        self.budget.charge("occurrences", weight, at)
        self.budget.charge("expansion_bytes", len(canonical(value)) * weight, at)
        op = operation(value, at)
        adapters.validate_identity(value, at)
        origin = {"file": str(self.document.path), "pointer": at, "target": target, "chain": list(chain)}
        if "id" in value:
            origin["target"] += "/id:" + quote(value["id"], safe="")
        children = {}
        data = copy.deepcopy(value)
        if op == "use":
            name = data[op]
            definition = self.document.data.get("defs", {}).get(name)
            if definition is None:
                raise DSLError("E_REFERENCE", f"unknown definition {name!r}", at)
            if name in stack or len(stack) >= self.document.limits.expansion_depth:
                raise DSLError("E_CYCLE", "recursive or excessively deep definition", at)
            supplied, params = data.get("with", {}), definition.get("params", {})
            known(supplied, params, at + "/with")
            bindings = {}
            for key, spec in params.items():
                if key not in supplied and "default" not in spec:
                    raise DSLError("E_PARAMETER", f"required parameter {key!r}", at + "/with")
                bindings[key] = parameter_value(supplied.get(key, spec.get("default")), spec, at + "/with/" + key)
            body = substitute(definition["body"], bindings, at, self.budget)
            expression(body, pointer("/defs", name) + "/body", self.document.limits)
            children["body"] = self.prepare(
                body,
                context,
                pointer("/defs", name) + "/body",
                origin["target"],
                stack=(*stack, name),
                weight=weight,
                chain=(
                    *chain,
                    {
                        "definition": name,
                        "invocation": at,
                        "bindings": {
                            key: binding
                            if not isinstance(binding, dict | list)
                            else {"type": params[key]["type"], "value_id": digest(binding)}
                            for key, binding in bindings.items()
                        },
                    },
                ),
            )
            origin["chain"] = children["body"].origin["chain"]
            origin["definition_pointer"] = children["body"].origin["pointer"]
        elif op in ("seq", "overlay", "voice", "instrument"):
            children["items"] = [
                self.prepare(
                    child,
                    context,
                    pointer(pointer(at, op), i),
                    origin["target"],
                    stack=stack,
                    weight=weight,
                    chain=chain,
                )
                for i, child in enumerate(data[op])
            ]
            if not children["items"]:
                raise DSLError("E_REQUIRED", "composition cannot be empty", at)
        elif op == "repeat":
            count = number(data[op], at + "/repeat", 1, self.document.limits.repeat, integer=True)
            children["body"] = self.prepare(
                data["of"], context, at + "/of", origin["target"], stack=stack, weight=weight * count, chain=chain
            )
        elif op == "mix":
            children["placements"] = [
                self.prepare(
                    p["sound"],
                    context,
                    pointer(at + "/mix", i) + "/sound",
                    origin["target"] + ("/id:" + quote(p["id"], safe="") if "id" in p else ""),
                    stack=stack,
                    weight=weight,
                    chain=chain,
                )
                for i, p in enumerate(data[op])
            ]
            if not children["placements"]:
                raise DSLError("E_REQUIRED", "mix cannot be empty", at)
        elif op in ("say", "emote") and "speaker" in data:
            descriptor = data["speaker"]
            if isinstance(descriptor, str):
                descriptor = {"speaker": descriptor}
            children["speaker"] = self.prepare(
                descriptor, context, at + "/speaker", origin["target"], stack=stack, weight=weight, chain=chain
            )
        elif op == "edit":
            children["body"] = self.prepare(
                data[op], context, at + "/edit", origin["target"], stack=stack, weight=weight, chain=chain
            )
        elif op == "score":
            settings = data[op]
            context = context | {k: settings[k] for k in ("bpm", "meter") if k in settings}
            number(context["bpm"], at, 4, 1000)
            number(context["meter"], at, 1, 255, integer=True)
            children["tracks"] = []
            for i, track in enumerate(settings.get("tracks", [])):
                loc = pointer(at + "/score/tracks", i)
                track_target = origin["target"] + "/track:" + quote(track.get("id", track["name"]), safe="")
                prepared = {"clips": [], "layers": []}
                clips = track.get(
                    "clips",
                    [{"instrument": track.get("instrument"), "notes": track["notes"]}] if "notes" in track else [],
                )
                for j, clip in enumerate(clips):
                    clip_at = loc + "/notes" if "notes" in track else pointer(loc + "/clips", j) + "/notes"
                    clip_target = track_target + ("/id:" + quote(clip["id"], safe="") if "id" in clip else "")
                    pitch = self.prepare(
                        clip["notes"], context, clip_at, clip_target, stack=stack, weight=weight, chain=chain
                    )
                    inst = clip.get("instrument", track.get("instrument"))
                    instrument = (
                        self.prepare(
                            inst,
                            context,
                            (pointer(loc + "/clips", j) if "instrument" in clip and "clips" in track else loc)
                            + "/instrument",
                            clip_target,
                            stack=stack,
                            weight=weight,
                            chain=chain,
                        )
                        if isinstance(inst, dict)
                        else inst
                    )
                    prepared["clips"].append((clip, pitch, instrument))
                prepared["layers"] = [
                    self.prepare(
                        layer,
                        context,
                        pointer(loc + "/layers", j),
                        track_target,
                        stack=stack,
                        weight=weight,
                        chain=chain,
                    )
                    for j, layer in enumerate(track.get("layers", []))
                ]
                children["tracks"].append(prepared)
            children["placements"] = [
                self.prepare(
                    p["sound"],
                    context,
                    pointer(at + "/score/sounds", i) + "/sound",
                    origin["target"] + ("/id:" + quote(p["id"], safe="") if "id" in p else ""),
                    stack=stack,
                    weight=weight,
                    chain=chain,
                )
                for i, p in enumerate(settings.get("sounds", []))
            ]
        kind = (
            "notes"
            if op in NOTE_OPS
            else "layer"
            if op in LAYERS
            else op
            if op in ("speaker", "instrument")
            else children["body"].kind
            if op in ("use", "edit", "repeat")
            else children["items"][0].kind
            if op == "seq"
            else "sound"
        )
        node = Expr(op, data, children, origin, context, kind)
        self._types(node)
        self.source_map.append(origin)
        return node

    def _types(self, node):
        op, at, children = node.op, node.origin["pointer"], node.children
        required = "layer" if op in ("voice", "instrument") else "notes" if op == "overlay" else None
        if op in ("voice", "instrument", "seq", "overlay"):
            kinds = {child.kind for child in children["items"]}
            if (
                len(kinds) != 1
                or required
                and kinds != {required}
                or op == "seq"
                and node.kind not in ("sound", "notes")
            ):
                raise DSLError("E_TYPE", "composition operands have incompatible types", at)
        if op in ("mix", "score"):
            if any(child.kind != "sound" for child in children["placements"]):
                raise DSLError("E_TYPE", "placed expressions must produce sounds", at)
        if op == "score":
            for track in children["tracks"]:
                if any(pitch.kind != "notes" for _, pitch, _ in track["clips"]) or any(
                    layer.kind != "layer" for layer in track["layers"]
                ):
                    raise DSLError("E_TYPE", "track needs Notes and/or supported Layers", at)
                if any(isinstance(inst, Expr) and inst.kind != "instrument" for _, _, inst in track["clips"]):
                    raise DSLError("E_TYPE", "instrument descriptor required", at)
        if "then" in node.data and node.kind != "notes":
            raise DSLError("E_TYPE", "then transforms apply only to Notes", at + "/then")
        if "speaker" in children and children["speaker"].kind != "speaker":
            raise DSLError("E_TYPE", "speaker descriptor required", at + "/speaker")
        if op == "edit" and node.kind != "sound":
            raise DSLError("E_TYPE", "edit requires a materialized sound", at)

    def build(self, node):
        at, data, context = node.origin["pointer"], node.data, node.context
        try:
            adapters.validate_identity(data, at)
            result = self._build(node)
            if isinstance(result, NoteSequence):
                if "span" in data:
                    result.span = quantity(data["span"], context, beats=True, pointer=at + "/span")
                result = transforms.apply(result, data.get("then", []), context, at + "/then", self.warnings)
                if (
                    sum(len(e[0]) if isinstance(e[0], list | tuple) else 1 for e in result.events)
                    > self.document.limits.notes
                ):
                    raise DSLError("E_LIMIT", "notes exceed the per-track event budget", at)
            elif isinstance(result, SoundPlan):
                if "span" in data:
                    result.span = quantity(data["span"], context, pointer=at + "/span")
                result.origins = result.origins | copy.deepcopy(node.origin)
                self.sound_budget(result, at)
            return result
        except DSLError as exc:
            if exc.target is None:
                exc.target = node.origin["target"]
            raise
        except (ValueError, OSError) as exc:
            raise DSLError("E_ASSET" if isinstance(exc, OSError) else "E_VALUE", str(exc), at) from None

    def _build(self, node):
        op, data, at, context = node.op, node.data, node.origin["pointer"], node.context
        rate = context["sample_rate"]
        if op == "use":
            return self.build(node.children["body"])
        if op in LAYERS:
            self.budget.charge("layers", 1, at)
            return adapters.make_layer(op, data[op], node.origin, rate)
        if op == "speaker":
            return adapters.speaker(data, at)
        if op == "instrument":
            from .instruments import Template

            return Template(node, self)
        if op in NOTE_OPS - {"overlay"}:
            return note_leaf(data, op, context, node.origin)
        if op == "voice":
            layers = [self.build(child) for child in node.children["items"]]
            result = SoundPlan("voice", adapters.make_voice(layers, data.get("bus", {}), rate, at), rate)
            result.layer_origins = [
                {"collection": next(k for k, cls in LAYERS.items() if type(layer.value) is cls), "origin": layer.origin}
                for layer in layers
            ]
            return result
        if op == "edit":
            from .overrides import apply

            return apply(self.build(node.children["body"]), data, at)
        if op in ("seq", "repeat", "overlay") and node.kind == "notes":
            if op == "repeat":
                base = self.build(node.children["body"])
                values = [copy.deepcopy(base) for _ in range(data["repeat"])]
            else:
                values = [self.build(child) for child in node.children["items"]]
            return combine_notes(
                values, gap=quantity(data.get("gap", "0b"), context, beats=True, pointer=at), overlay=op == "overlay"
            )
        if op in ("score", "mix", "seq", "repeat"):
            return self.score(node)
        if op == "fm":
            duration = number(data[op].get("duration", 0.6), at, 1e-9, self.document.limits.seconds)
            self.budget.audio(round(duration * rate), rate, layers=3, pointer=at)
        if op == "audio":
            # Header bounds are enforced by read_channels before PCM allocation.
            pass
        if op in ("say", "emote"):
            child = self.build(node.children["speaker"]) if "speaker" in node.children else None
        else:
            child = None
        try:
            result = adapters.leaf(node, self.document, self.dependencies, child)
            if result.kind == "voice":
                from .registry import COLLECTIONS

                self.budget.charge("layers", sum(len(getattr(result.source, key)) for key in COLLECTIONS.values()), at)
                self.budget.charge("expansion_bytes", len(canonical(result.source.to_dict())), at)
            return result
        except TypeError:
            if op == "sfx" and isinstance(data.get("species"), str):
                raise DSLError("E_CAPABILITY", "this legacy composite recipe requires numeric species", at) from None
            raise

    def sound_budget(self, plan, at):
        if plan.kind in ("fm", "rest"):
            duration = plan.source.get("duration", 0.6) if plan.kind == "fm" else plan.source
            self.budget.audio(round(duration * plan.sr), plan.sr, layers=3, pointer=at)
            if plan.span is None:
                plan.span = Fraction(str(duration))
        elif plan.kind == "pcm":
            frames = len(plan.source)
            self.budget.audio(frames, plan.sr, pointer=at)
            if plan.span is None and frames:
                plan.span = Fraction(frames, plan.sr)
        elif plan.kind == "voice":
            source = plan.source
            if source.duration <= 0:
                raise DSLError("E_SPAN", "Voice needs positive dry duration", at)
            voice_fields(source.to_dict(), plan.sr, at)
            if source.loop and source.duration <= source.loop:
                raise DSLError("E_SPAN", "Voice crossfade must be shorter than dry duration", at)
            if source.chips:
                from ..chip import GB_RATE, program_duration

                work = max(program_duration(chip) for chip in source.chips) * GB_RATE * 8 * 12
                if work > self.document.limits.work_bytes:
                    raise DSLError("E_LIMIT", "estimated Game Boy working memory exceeds the build limit", at)
            self.budget.audio(
                round((source.duration + source.space) * plan.sr),
                plan.sr,
                layers=max(
                    1,
                    sum(
                        len(getattr(source, name))
                        for name in ("syllables", "chips", "noise", "modal", "scatter", "speech", "vocoded", "spoken")
                    ),
                ),
                pointer=at,
            )
        elif plan.kind in ("score", "cue"):
            score = plan.source.score if plan.kind == "cue" else plan.source
            if score.hall and plan.sr <= 10000:
                raise DSLError("E_SAMPLE_RATE", "hall requires sample rate above 10000 Hz", at)

    def score(self, node):
        data, op, context, at = node.data, node.op, node.context, node.origin["pointer"]
        settings = data[op] if op == "score" else {k: v for k, v in data.items() if k not in META | {op, "gap", "of"}}
        settings = copy.deepcopy(settings)
        score_settings = {
            k: settings[k] for k in ("bpm", "meter", "seed", "hall", "echo", "lowpass", "effects") if k in settings
        }
        score_settings = {"bpm": context["bpm"], "meter": context["meter"], "hall": 0} | score_settings
        number(score_settings.get("hall", 0), at + "/hall", 0, self.document.limits.seconds)
        for key in ("gain", "lowpass"):
            if key in settings:
                number(settings[key], at + "/" + key, 0 if key == "lowpass" else None)
        if "seed" in settings:
            seed(settings["seed"], at + "/seed")
        effects = score_settings.get("effects", [])
        effect_fields(effects, at + "/effects")
        if score_settings.get("echo") is not None:
            echo = score_settings["echo"]
            if not isinstance(echo, list | tuple) or len(echo) != 3:
                raise DSLError("E_TYPE", "echo needs delay, feedback, and tone", at + "/echo")
            for val, low, high in zip(echo, (1e-9, 0, 1e-9), (self.document.limits.seconds, 0.95, None), strict=True):
                number(val, at + "/echo", low, high)
        if effects:
            kinds = [e.get("type") for e in effects]
            if kinds.count("limiter") > 1 or "limiter" in kinds and kinds[-1] != "limiter":
                raise DSLError("E_EFFECT", "a single limiter must be last", at + "/effects")
        score = Score(sr=context["sample_rate"], **score_settings)
        placements = []
        if op == "score":
            for track, prepared in zip(settings.get("tracks", []), node.children["tracks"], strict=True):
                known(track, TRACK_FIELDS, at)
                bus = track.get("voice", {})
                from .registry import VOICE_BUS

                known(bus, VOICE_BUS - {"seed"}, at + "/voice")
                voice_fields(bus, score.sr, at)
                values = {
                    k: number(track[k], at, -1 if k == "pan" else None, 1 if k == "pan" else None)
                    for k in ("gain", "pan", "send", "echo")
                    if k in track
                }
                target = score.track(track["name"], **values, **bus)
                played = 0
                for clip, pitch, instrument in prepared["clips"]:
                    sequence = self.build(pitch)
                    played += sum(len(e[0]) if isinstance(e[0], list | tuple) else 1 for e in sequence.events)
                    if played > self.document.limits.notes:
                        raise DSLError("E_LIMIT", "aggregate notes exceed the per-track budget", at)
                    fn = self.build(instrument) if isinstance(instrument, Expr) else instrument
                    if fn is None:
                        raise DSLError("E_REQUIRED", "track/clip needs an instrument", at)
                    offset = quantity(clip.get("at", "0b"), context, beats=True, pointer=at)
                    before = len(target.events)
                    before_layers = len(target.layers)
                    target.play(
                        fn, [[p, float(a), float(h), v] for p, a, h, v in sequence.events], offset=float(offset)
                    )
                    if isinstance(fn, str):
                        self.budget.charge("layers", len(target.layers) - before_layers, at)
                    event_origins = [
                        origin
                        for event, origin in zip(sequence.events, sequence.origins, strict=True)
                        for _ in (event[0] if isinstance(event[0], list | tuple) else [event[0]])
                    ]
                    for event, origin in zip(target.events[before:], event_origins, strict=True):
                        event["dsl_origin"] = copy.deepcopy(origin)
                    if hasattr(fn, "midi_program"):
                        target.dsl_programs = (
                            getattr(target, "dsl_programs", {}) | {target.events[-1]["instrument"]: fn.midi_program}
                            if target.events
                            else {}
                        )
                for child in prepared["layers"]:
                    layer = self.build(child)
                    if type(layer.value).__name__ not in ("Syllable", "Modal", "Noise", "Scatter", "ChipProgram"):
                        raise DSLError("E_CAPABILITY", "Track does not support this layer; place it as a Voice", at)
                    target.add(layer.value)
                    target.origins[-1]["dsl_origin"] = layer.origin
            entries = settings.get("sounds", [])
            values = [self.build(child) for child in node.children["placements"]]
        elif op == "mix":
            entries = data[op]
            values = [self.build(child) for child in node.children["placements"]]
        else:
            if op == "repeat":
                base = self.build(node.children["body"])
                values = [base] * data[op]
            else:
                values = [self.build(child) for child in node.children["items"]]
            offset, gap, entries = Fraction(0), quantity(data.get("gap", "0s"), context, pointer=at), []
            for child in values:
                if child.span is None:
                    raise DSLError("E_SPAN_REQUIRED", "sequence/repeat needs an explicit scheduling span", at)
                entries.append({"at": float(offset)})
                offset += child.span + gap
            span = offset - gap
        for index, (entry, child) in enumerate(zip(entries, values, strict=True)):
            when = entry.get("at", "0s")
            seconds = float(quantity(when, context, pointer=at)) if isinstance(when, str) else when
            values_ = {
                k: number(entry.get(k, default), at, -1 if k == "pan" else None, 1 if k == "pan" else None)
                for k, default in (("gain", 1), ("pan", 0), ("send", 0), ("echo", 0))
            }
            placements.append({"plan": child, "at": seconds, "occurrence": index, **values_})
        loop = float(quantity(settings["loop"], context, pointer=at)) if "loop" in settings else None
        if loop is not None and loop <= 0:
            raise DSLError("E_SPAN", "loop period must be positive", at)
        return SoundPlan(
            "score",
            score,
            score.sr,
            span if op in ("seq", "repeat") else None,
            loop,
            settings.get("gain", 1),
            placements,
        )


def compile_document(document, *, name=None):
    if not hasattr(document, "select"):
        document = load(data=document)
    name, value = document.select(name)
    compiler = Compiler(document)
    node = compiler.prepare(value, document.context, pointer("/sounds", name), "sound:" + quote(name, safe=""))
    if node.kind != "sound":
        raise DSLError("E_TYPE", "named sounds must produce Sound expressions", node.origin["pointer"])
    plan = compiler.build(node)
    from .costs import preflight

    projected_cost = preflight(plan, compiler.budget)
    for path in compiler.dependencies:
        compiler.dependencies[path] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return CompileResult(
        document,
        name,
        plan,
        compiler.dependencies,
        compiler.source_map,
        compiler.warnings,
        {
            "occurrences": compiler.budget.occurrences,
            "layers": max(compiler.budget.layers, projected_cost["actual_layers"]),
            "weighted_work": compiler.budget.weighted_work,
            **projected_cost,
        },
    )


def build_file(path, *, name=None, sr=None, asset_roots=(), limits=None):

    document = load(path, asset_roots=asset_roots, limits=limits)
    if sr is not None:
        number(sr, "/context/sample_rate", 1000, 192000, integer=True)
        document.data.setdefault("context", {})["sample_rate"] = sr
    result = compile_document(document, name=name)
    return capture_compiled(result)


def capture_compiled(result):
    from .composition import capture_plan

    document = result.document
    try:
        captured = capture_plan(result.plan, limits=document.limits)
    except DSLError:
        raise
    except (ValueError, OSError) as exc:
        raise DSLError("E_BUILD", str(exc), result.plan.origins.get("pointer", "")) from None
    manifest = captured.manifest
    manifest["dsl"] = {
        "format": "tare.tools.tune.dsl",
        "version": 1,
        "authored_revision": document.revision,
        "compiler_id": result.compiler_id,
        "document": document.data,
        "source_map": result.source_map,
        "dependencies": result.dependencies,
        "capabilities": capabilities(result.plan),
        "warnings": result.warnings,
        "path": str(document.path),
        "sound": result.name,
    }
    from .validate import reference_file

    file, at = reference_file(document.data, result.name)
    if file:
        from ..audio_io import read_channels
        from ..diagnostics import pcm_id
        from .validate import asset

        path = asset(document, file, at)
        remaining = document.limits.capture_bytes - sum(value.nbytes for value in captured.arrays.values())
        try:
            y, rate = read_channels(path, document.limits.seconds, max_bytes=remaining)
        except ValueError as exc:
            if "decoded byte limit" in str(exc):
                raise DSLError("E_LIMIT", str(exc), at) from None
            raise
        captured.arrays["reference"] = y
        manifest["reference"] = {"file": file, "sample_rate": rate, "pcm_id": pcm_id(y, rate)}
        manifest["dsl"]["dependencies"][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    from .composition import finalize

    return finalize(captured)
