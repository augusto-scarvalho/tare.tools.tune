"""Immutable Python conveniences that emit the same declarative data as JSON files."""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..bundles import atomic_json
from ..diagnostics import canonical
from .model import FORMAT, VERSION, DSLError


def data(value):
    if isinstance(value, Node | Project):
        return value.to_dict()
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JSON keys must be strings")
        return {key: data(child) for key, child in value.items()}
    if isinstance(value, list | tuple):
        return [data(child) for child in value]
    if value is None or type(value) in (str, bool, int, float):
        return value
    raise TypeError("not declarative JSON data")


def encode(value):
    try:
        return canonical(data(value))
    except (TypeError, ValueError) as exc:
        raise DSLError("E_SERIALIZATION", "builders accept JSON data, not arrays or Python callables") from exc


@dataclass(frozen=True)
class Node:
    _encoded: bytes

    @classmethod
    def from_dict(cls, value):
        return cls(encode(value))

    def to_dict(self):
        return json.loads(self._encoded)

    def then(self, *transforms):
        value = self.to_dict()
        value["then"] = value.get("then", []) + [data(t) for t in transforms]
        return Node.from_dict(value)

    def with_id(self, name):
        return Node.from_dict(self.to_dict() | {"id": name})

    def with_span(self, span):
        return Node.from_dict(self.to_dict() | {"span": span})


@dataclass(frozen=True, init=False)
class Project:
    _encoded: bytes

    def __init__(self, *, sounds, defs=None, context=None, reference=None):
        value = {"format": FORMAT, "version": VERSION, "sounds": sounds}
        for key, item in (("defs", defs), ("context", context), ("reference", reference)):
            if item is not None:
                value[key] = item
        object.__setattr__(self, "_encoded", encode(value))

    @classmethod
    def from_dict(cls, value):
        from .validate import load

        document = load(data=data(value))
        result = object.__new__(cls)
        object.__setattr__(result, "_encoded", encode(document.data))
        return result

    def to_dict(self):
        return json.loads(self._encoded)

    def write(self, path):
        from .validate import load

        load(path, data=self.to_dict())
        atomic_json(path, self.to_dict())
        return path

    def compile(self, *, name=None, path=None, **options):
        from .compiler import compile_document
        from .validate import load

        return compile_document(load(path, data=self.to_dict(), **options), name=name)


def expression(op, value, **fields):
    return Node.from_dict({op: value, **fields})


def definition(body, *, params=None):
    return {"body": data(body), **({"params": data(params)} if params else {})}


def param(name):
    return {"param": name}


def use(name, **parameters):
    return expression("use", name, **({"with": parameters} if parameters else {}))


def sfx(kind, **options):
    return expression("sfx", kind, **options)


def creature(archetype, **options):
    return expression("creature", archetype, **options)


def speaker(preset="default", **options):
    return expression("speaker", preset, **options)


def say(text, **options):
    return expression("say", text, **options)


def emote(kind, **options):
    return expression("emote", kind, **options)


def music(kind, **options):
    return expression("music", kind, **options)


def pattern(text, **options):
    return expression("pattern", text, **options)


def notes(events, **options):
    return expression("notes", events, **options)


def chord(symbol, **options):
    return expression("chord", symbol, **options)


def degrees(events, **options):
    return expression("degrees", events, **options)


def seq(*children, **options):
    return expression("seq", children, **options)


def overlay(*children):
    return expression("overlay", children)


def repeat(count, of, **options):
    return expression("repeat", count, of=of, **options)


def mix(*placements, **options):
    return expression("mix", placements, **options)


def voice(*layers, **bus):
    return expression("voice", layers, **({"bus": bus} if bus else {}))


def score(**settings):
    return expression("score", settings)


def fm(**settings):
    return expression("fm", settings)


def audio(file):
    return expression("audio", file)


def rest(duration):
    return expression("rest", duration)


def spec(document):
    return expression("spec", document)


def edit(child, *, expect, **changes):
    return expression("edit", child, expect=expect, **changes)


def instrument(*layers, midi_program=None):
    return expression("instrument", layers, **({"midi_program": midi_program} if midi_program is not None else {}))


def chip_voice(wave="pulse", **fields):
    return expression("chip_voice", wave, **fields)


def primitive(kind, **fields):
    from .registry import LAYERS

    if kind not in LAYERS:
        raise DSLError("E_OPERATION", "unknown primitive")
    return expression(kind, fields)


def syllable(**fields):
    return primitive("syllable", **fields)


def modal(**fields):
    return primitive("modal", **fields)


def noise(**fields):
    return primitive("noise", **fields)


def scatter(**fields):
    return primitive("scatter", **fields)


def chip(**fields):
    return primitive("chip", **fields)


def speech_frames(**fields):
    return primitive("speech_frames", **fields)


def vocoded(**fields):
    return primitive("vocoded", **fields)


def spoken(**fields):
    return primitive("spoken", **fields)


def transpose(semitones):
    return {"transpose": semitones}


def stretch(factor):
    return {"stretch": factor}


def velocity(factor):
    return {"velocity": factor}


def retrograde():
    return {"retrograde": True}


def quantize(grid):
    return {"quantize": grid}


def humanize(**settings):
    return {"humanize": settings}
