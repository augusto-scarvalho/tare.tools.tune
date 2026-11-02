"""Small, revision-checked authored edits with explicit targets and atomic file replacement."""

from __future__ import annotations

import copy
import hashlib
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote

from ..bundles import file_lock
from ..diagnostics import canonical
from .model import DSLError
from .validate import known, load, parse


def parts(path):
    if path == "":
        return []
    if not isinstance(path, str) or not path.startswith("/"):
        raise DSLError("E_POINTER", "expected an RFC 6901 pointer")
    result = []
    for value in path[1:].split("/"):
        if re.search(r"~(?![01])", value):
            raise DSLError("E_POINTER", "invalid pointer escape", path)
        result.append(value.replace("~1", "/").replace("~0", "~"))
    return result


def get(data, path):
    value = data
    try:
        for key in parts(path):
            value = value[int(key)] if isinstance(value, list) and key.isdecimal() else value[key]
        return value
    except (KeyError, IndexError, TypeError, ValueError):
        raise DSLError("E_POINTER", "pointer does not resolve", path) from None


def parent(data, path):
    keys = parts(path)
    if not keys:
        raise DSLError("E_POINTER", "operation needs a non-root path", path)
    before = path.rsplit("/", 1)[0]
    container = get(data, before)
    key = keys[-1]
    if isinstance(container, list):
        if not key.isdecimal() or key != str(int(key)):
            raise DSLError("E_POINTER", "array index must be a canonical nonnegative integer", path)
        key = int(key)
    if not isinstance(container, dict | list):
        raise DSLError("E_POINTER", "pointer parent is not a container", path)
    return container, key


def replace(data, path, value, *, existing=False):
    container, key = parent(data, path)
    if isinstance(container, list):
        if not 0 <= key < len(container):
            raise DSLError("E_POINTER", "set cannot grow an array", path)
    elif existing and key not in container:
        raise DSLError("E_POINTER", "field does not exist", path)
    container[key] = copy.deepcopy(value)


def target_pointer(data, target):
    if not isinstance(target, str):
        raise DSLError("E_TARGET", "authored target must be a string")
    sections = target.split("/")
    root, separator, encoded = sections[0].partition(":")
    if not separator or root not in ("sound", "def"):
        raise DSLError("E_TARGET", "target starts with sound: or def:")

    def decode(value):
        try:
            decoded = unquote(value, errors="strict")
        except UnicodeDecodeError:
            raise DSLError("E_TARGET", "invalid percent encoding") from None
        if quote(decoded, safe="") != value:
            raise DSLError("E_TARGET", "target components require canonical percent encoding")
        return decoded

    key = decode(encoded)
    path = "/" + ("sounds" if root == "sound" else "defs") + "/" + key.replace("~", "~0").replace("/", "~1")
    value = get(data, path)
    for section in sections[1:]:
        kind, sep, name = section.partition(":")
        if not sep or kind not in ("id", "track"):
            raise DSLError("E_TARGET", "unknown target segment")
        name = decode(name)
        matches = []

        def search(node, pointer, in_track=False, name=name, kind=kind, matches=matches):
            if isinstance(node, dict):
                selected = node.get("id", node.get("name")) if kind == "track" and in_track else node.get("id")
                if selected == name and (kind == "id" or in_track):
                    matches.append(pointer)
                    return
                for k, child in node.items():
                    search(child, pointer + "/" + k.replace("~", "~0").replace("/", "~1"), k == "tracks")
            elif isinstance(node, list):
                for i, child in enumerate(node):
                    search(child, pointer + "/" + str(i), in_track)

        search(value, path)
        if len(matches) != 1:
            raise DSLError("E_TARGET", "target is missing or ambiguous; select the definition explicitly", path)
        path, value = matches[0], get(data, matches[0])
    return path


def apply_operations(data, operations):
    value = copy.deepcopy(data)
    changed = []
    for item in operations:
        known(item, {"op", "target", "pointer", "path", "value", "from", "name"})
        if ("target" in item) == ("pointer" in item):
            raise DSLError("E_TARGET", "provide exactly one target or pointer")
        base = target_pointer(value, item["target"]) if "target" in item else item["pointer"]
        parts(base)
        parts(item.get("path", ""))
        path = base + item.get("path", "")
        op = item.get("op")
        if op == "set":
            if "value" not in item:
                raise DSLError("E_REQUIRED", "set needs value", path)
            replace(value, path, item["value"])
        elif op == "remove":
            container, key = parent(value, path)
            try:
                if isinstance(container, list):
                    container.pop(key)
                else:
                    del container[key]
            except (KeyError, IndexError):
                raise DSLError("E_POINTER", "remove target does not exist", path) from None
        elif op == "insert":
            container, key = parent(value, path)
            if not isinstance(container, list) or not 0 <= key <= len(container) or "value" not in item:
                raise DSLError("E_POINTER", "insert needs an array position and value", path)
            container.insert(key, copy.deepcopy(item["value"]))
        elif op == "move":
            parts(item.get("from", ""))
            source_path = base + item.get("from", "")
            source, source_key = parent(value, source_path)
            if path == source_path or path.startswith(source_path + "/"):
                raise DSLError("E_POINTER", "move cannot place an ancestor inside itself", path)
            moved = copy.deepcopy(get(value, source_path))
            if isinstance(source, list):
                source.pop(source_key)
            else:
                del source[source_key]
            container, key = parent(value, path)
            if isinstance(container, list):
                if not 0 <= key <= len(container):
                    raise DSLError("E_POINTER", "move destination is out of bounds", path)
                container.insert(key, moved)
            else:
                container[key] = moved
        elif op == "rename":
            if not base.startswith("/defs/") or "/" in base[len("/defs/") :]:
                raise DSLError("E_TARGET", "rename selects a definition", base)
            old = parts(base)[-1]
            new = item.get("name")
            if not isinstance(new, str) or not new or new in value["defs"]:
                raise DSLError("E_ID", "new definition name is empty or already exists", base)
            value["defs"][new] = value["defs"].pop(old)

            def rewrite(node, old=old, new=new):
                if isinstance(node, dict):
                    if node.get("use") == old:
                        node["use"] = new
                    for k, child in node.items():
                        if k not in ("meta", "spec"):
                            rewrite(child)
                elif isinstance(node, list):
                    for child in node:
                        rewrite(child)

            rewrite(value)
        else:
            raise DSLError("E_PATCH", "unknown patch operation", path)
        changed.append(item.get("target", item.get("pointer")))
    return value, changed


def patch_file(path, envelope, *, dry_run=False, asset_roots=(), response="detailed"):
    result, _ = _patch_file(path, envelope, dry_run=dry_run, asset_roots=asset_roots, response=response)
    return result


def _patch_file(path, envelope, *, dry_run=False, asset_roots=(), response="detailed", observe=None, prepare=None):
    """Shared transaction; workflow hooks are trusted package code, never project data."""
    from .compiler import compile_document
    from .responses import respond, validate_response

    validate_response(response)
    path = Path(path).resolve()
    if isinstance(envelope, bytes):
        envelope = parse(envelope)
    known(envelope, {"format", "version", "expect", "ops"})
    if (
        envelope.get("format") != "tare.tools.tune.patch"
        or type(envelope.get("version")) is not int
        or envelope["version"] != 1
        or not isinstance(envelope.get("ops"), list)
        or len(envelope["ops"]) > 100
    ):
        raise DSLError("E_PATCH", "expected patch version 1 with at most 100 operations")
    with file_lock(path.with_name("." + path.name + ".lock")):
        document = load(path, asset_roots=asset_roots)
        if envelope.get("expect") != document.revision:
            raise DSLError("E_REVISION_CONFLICT", "authored revision changed; query before patching")
        if observe is not None:
            observe(document)
        before = path.read_bytes()
        updated, changed = apply_operations(document.data, envelope["ops"])
        candidate = load(path, data=updated, asset_roots=asset_roots)
        for name in candidate.data["sounds"]:
            compile_document(candidate, name=name)
        old_revision, new_revision = document.revision, candidate.revision
        from .query import impact

        affected = []
        for target in changed:
            if target.startswith(("sound:", "def:")):
                affected.extend(impact(candidate, target))
                affected.extend(impact(document, target))
            else:
                affected.extend(candidate.data["sounds"])
        prepared = prepare(candidate) if prepare is not None else None
        if observe is not None:
            observe(document)
        if not dry_run:
            directory = path.parent / ".tune-backups"
            directory.mkdir(exist_ok=True)
            backup = directory / (path.name + "." + hashlib.sha256(before).hexdigest() + ".bak")
            if not backup.exists():
                backup.write_bytes(before)
            descriptor, temporary = tempfile.mkstemp(prefix=".tune-patch-", dir=path.parent)
            temporary = Path(temporary)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(canonical(updated) + b"\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                if path.read_bytes() != before:
                    raise DSLError("E_REVISION_CONFLICT", "source changed outside the patch transaction")
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        result = {
            "schema": "tune.query/1",
            "old_revision": old_revision,
            "authored_revision": new_revision,
            "changed": changed,
            "affected": sorted(set(affected))[:100],
            "affected_total": len(set(affected)),
            "dry_run": dry_run,
            "formatted": "canonical JSON; unrelated values preserved",
        }
        return respond(result, "patch", response), prepared
