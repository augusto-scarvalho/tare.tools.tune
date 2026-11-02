"""Shared data contracts for the bounded, non-executable authoring language."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..diagnostics import canonical, digest

FORMAT = "tare.tools.tune.dsl"
VERSION = 1
MAX_INT = 2**53 - 1


class DSLError(ValueError):
    def __init__(self, code, message, pointer="", *, target=None, suggestions=None, details=None):
        super().__init__(message)
        self.code, self.pointer, self.target = code, pointer, target
        self.suggestions = (suggestions or [])[:3]
        self.details = details

    def to_dict(self):
        result = {"schema": "tune.error/1", "code": self.code, "message": str(self), "pointer": self.pointer}
        if self.target:
            result["target"] = self.target
        if self.suggestions:
            result["suggestions"] = self.suggestions
        if self.details is not None:
            result["details"] = self.details
        return result

    @property
    def exit_code(self):
        if self.code == "E_CHECK_FAILED":
            return 5
        return (
            3
            if self.code in ("E_REVISION_CONFLICT", "E_OVERRIDE_STALE")
            else 4
            if self.code in ("E_ASSET", "E_BUILD", "E_TIMEOUT")
            else 2
        )


@dataclass(frozen=True)
class Budgets:
    source_bytes: int = 1024 * 1024
    depth: int = 64
    definitions: int = 256
    sounds: int = 256
    expansion_depth: int = 32
    occurrences: int = 4096
    expansion_bytes: int = 64 * 1024 * 1024
    repeat: int = 256
    tracks: int = 64
    notes: int = 512
    layers: int = 1024
    seconds: float = 180
    capture_bytes: int = 256 * 1024 * 1024
    work_bytes: int = 512 * 1024 * 1024
    weighted_work: int = 1_000_000_000
    speech_chars: int = 1024
    scalars: int = 500_000


@dataclass
class Budget:
    limits: Budgets = field(default_factory=Budgets)
    occurrences: int = 0
    expansion_bytes: int = 0
    layers: int = 0
    capture_bytes: int = 0
    weighted_work: int = 0

    def charge(self, kind, amount, pointer=""):
        current = getattr(self, kind) + amount
        if current > getattr(self.limits, kind):
            raise DSLError("E_LIMIT", f"{kind} budget exceeded", pointer)
        setattr(self, kind, current)

    def audio(self, frames, rate, channels=2, *, layers=1, pointer=""):
        if frames < 0 or frames / rate > self.limits.seconds:
            raise DSLError("E_LIMIT", "audio duration exceeds the build limit", pointer)
        estimate = frames * channels * 8 * max(4, layers * 2)
        if estimate > self.limits.work_bytes:
            raise DSLError("E_LIMIT", "estimated working memory exceeds the build limit", pointer)


@dataclass
class Document:
    data: dict
    path: Path
    raw_hash: str
    limits: Budgets = field(default_factory=Budgets)
    asset_roots: tuple[Path, ...] = ()

    @property
    def revision(self):
        return digest(self.data)

    @property
    def context(self):
        return {"sample_rate": 48000, "bpm": 100, "meter": 4} | self.data.get("context", {})

    def select(self, name=None):
        names = self.data["sounds"]
        if name is None and len(names) == 1:
            name = next(iter(names))
        if name not in names:
            raise DSLError("E_SELECTION", "choose a sound with --name", "/sounds", suggestions=list(names)[:3])
        return name, copy.deepcopy(names[name])


@dataclass
class NoteSequence:
    events: list
    span: Fraction
    origins: list = field(default_factory=list)


@dataclass
class LayerValue:
    value: Any
    origin: dict


@dataclass
class Expr:
    op: str
    data: dict
    children: dict
    origin: dict
    context: dict
    kind: str = "sound"


@dataclass
class SoundPlan:
    kind: str
    source: Any
    sr: int
    span: Fraction | None = None
    loop: float | None = None
    gain: float = 1
    placements: list = field(default_factory=list)
    origins: dict = field(default_factory=dict)
    layer_origins: list = field(default_factory=list)
    edited: bool = False
    dependencies: dict = field(default_factory=dict)

    def materialized(self):
        from ..diagnostics import definition, pcm_id

        if self.kind in ("fm", "rest"):
            return {"kind": self.kind, "settings": self.source, "sample_rate": self.sr}
        if self.kind == "pcm":
            return {"kind": "pcm", "pcm_id": pcm_id(self.source, self.sr)}
        result = definition(self.source)

        def structural(value):
            if value.get("kind") == "cue":
                value["score"] = structural(value["score"])
            elif value.get("kind") == "score":
                for track in value["tracks"]:
                    track.pop("origins", None)
                    track["events"] = [
                        {key: item for key, item in event.items() if key not in ("source", "project", "dsl_origin")}
                        for event in track["events"]
                    ]
                for placed in value["sounds"]:
                    placed.pop("origin", None)
            return value

        # Wrapping the same source in edit changes authoring pointers, not its
        # expansion. Guards must describe the structure selected by expand.
        result = structural(result)
        if self.kind in ("score", "cue"):
            result = result | {"render": {"loop": self.loop, "gain": self.gain}}
        if self.placements:
            result = result | {
                "placements": [
                    {k: v for k, v in p.items() if k != "plan"} | {"child": p["plan"].materialized()}
                    for p in self.placements
                ]
            }
        return result


@dataclass
class CompileResult:
    document: Document
    name: str
    plan: SoundPlan
    dependencies: dict
    source_map: list
    warnings: list
    cost: dict

    @property
    def compiler_id(self):
        import hashlib

        files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob("*.py"))}
        return digest({"language": VERSION, "files": files})

    def summary(self):
        from .compiler import capabilities

        return {
            "schema": "tune.query/1",
            "authored_revision": self.document.revision,
            "sound": self.name,
            "type": self.plan.kind,
            "compiler_id": self.compiler_id,
            "capabilities": capabilities(self.plan),
            "cost": self.cost,
            "warnings": self.warnings,
            "dependencies": list(self.dependencies),
        }


def pointer(parent, key):
    return parent + "/" + str(key).replace("~", "~0").replace("/", "~1")


def clone(value):
    import json

    return json.loads(canonical(value))
