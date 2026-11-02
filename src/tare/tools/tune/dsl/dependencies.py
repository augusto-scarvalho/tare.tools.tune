"""Declared selected-source dependencies, including paths that do not exist yet."""

import re
from pathlib import Path

from .compiler import Compiler
from .model import DSLError, Expr, pointer
from .validate import load, parse


def paths_for(path, *, name=None, asset_roots=()):
    document = load(path, asset_roots=asset_roots)
    name, sound = document.select(name)
    compiler = Compiler(document)
    root = compiler.prepare(sound, document.context, pointer("/sounds", name), "sound:" + name)
    result = {document.path}
    natural = False
    data = Path(__file__).parent.parent / "speech" / "data"

    def local(value):
        if not isinstance(value, str) or "://" in value:
            raise DSLError("E_ASSET", "dependency must be a local path")
        resolved = (document.path.parent / value).resolve()
        if not any(resolved.is_relative_to(root_) for root_ in (document.path.parent, *document.asset_roots)):
            raise DSLError("E_ASSET", "dependency is outside the authorized roots")
        result.add(resolved)
        return resolved

    def voice_assets(value):
        if not isinstance(value, dict):
            return
        spoken = value.get("spoken", [])
        if not isinstance(spoken, list):
            return
        for layer in spoken:
            bank = layer.get("bank") if isinstance(layer, dict) else None
            if isinstance(bank, str) and re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", bank):
                stem = "bank_" + bank.replace("/", "_")
                result.update((data / (stem + ".npz"), data / (stem + ".json")))
        if value.get("vocoded"):
            result.update((data / "barks.npz", data / "barks_audio.npz"))

    def visit(value):
        nonlocal natural
        if isinstance(value, Expr):
            if value.op == "audio":
                local(value.data["audio"])
            elif value.op == "spec" and isinstance(value.data["spec"], dict) and "file" in value.data["spec"]:
                spec_path = local(value.data["spec"]["file"])
                if spec_path.exists() and spec_path.stat().st_size <= document.limits.source_bytes:
                    try:
                        voice_assets(parse(spec_path.read_bytes(), document.limits))
                    except (OSError, DSLError):
                        pass
            elif value.op == "spec":
                voice_assets(value.data["spec"])
            elif value.op == "spoken":
                voice_assets({"spoken": [value.data["spoken"]]})
            elif value.op == "vocoded":
                voice_assets({"vocoded": [value.data["vocoded"]]})
            elif value.op == "speaker" and value.data.get("engine") == "natural":
                natural = True
                if value.data.get("bank"):
                    bank = value.data["bank"].replace("/", "_")
                    result.update((data / f"bank_{bank}.npz", data / f"bank_{bank}.json"))
            visit(value.children)
        elif isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list | tuple):
            for child in value:
                visit(child)

    visit(root)
    if natural:
        result.update(data.glob("bank_*.npz"))
        result.update(data.glob("bank_*.json"))
    if "reference" in document.data:
        local(document.data["reference"]["file"])
    for file in document.data.get("references", {}).values():
        local(file)
    return result
