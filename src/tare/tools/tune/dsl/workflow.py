"""Review, describe and guarded edits over existing immutable capture bundles."""

import copy
import hashlib
from pathlib import Path
from urllib.parse import quote, unquote

from ..bundles import load_bundle, save_bundle
from ..diagnostics import Capture, renderer_id
from .adapters import materialized_id
from .affordances import affected, layer_selection
from .affordances import describe as describe_capture
from .compiler import capture_compiled, compile_document
from .composition import finalize
from .model import DSLError
from .patch import _patch_file, apply_operations, get, parts, target_pointer
from .responses import respond, validate_response
from .review_data import changes, check_spec, facts, run_checks
from .validate import asset, load, reference_file


def _capture(value):
    return value if isinstance(value, Capture) else load_bundle(value)


def _dependencies(result):
    expected = dict(result.dependencies)
    file, at = reference_file(result.document.data, result.name)
    if file:
        path = asset(result.document, file, at)
        expected[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return expected


def _unchanged(dependencies):
    for name, expected in dependencies.items():
        path = Path(name)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise DSLError("E_REVISION_CONFLICT", "observed asset changed; review again")


def _report(captured, bundle, spec, *, previous=None, limit=5, measured=None):
    measured = facts(captured, limit) if measured is None else measured
    name = captured.manifest.get("dsl", {}).get("sound", "recording")
    result = {
        "schema": "tune.review/1",
        "sound": name,
        "audio": "audio.wav",
        "description": f"{name}: {measured['duration_s']:.3f} s, {measured['channels']} channel(s), "
        f"{measured['sample_rate']} Hz; {measured['parts']} captured parts",
        "facts": measured,
        "checks": run_checks(captured, spec, measured),
        "capabilities": captured.manifest.get("dsl", {}).get("capabilities"),
        "source_state": "archived; freshness is checked before editing",
    }
    if bundle is not None:
        result["bundle"] = str(Path(bundle).resolve())
    context = captured.manifest.get("dsl", {}).get("review", {})
    result["can_edit"] = bundle is not None and bool(context.get("materialized_id")) and not context.get("draft", False)
    if previous is not None:
        old = _capture(previous)
        old_meta, new_meta = old.manifest.get("dsl"), captured.manifest.get("dsl")
        if old_meta and new_meta and (old_meta["path"], old_meta["sound"]) != (new_meta["path"], new_meta["sound"]):
            raise DSLError("E_SELECTION", "previous capture belongs to a different source or sound")
        result["changes"] = changes(captured, old, measured, limit)
    warnings = captured.manifest.get("dsl", {}).get("warnings", [])
    if warnings:
        result["warnings"] = warnings[:limit]
    return result


def _publish(result, output, spec, *, previous=None, limit=5, draft=False, candidate=False):
    dependencies = _dependencies(result)
    captured = capture_compiled(result)
    _unchanged(dependencies)
    measured = facts(captured, limit)
    checks = run_checks(captured, spec, measured)
    captured.manifest["dsl"]["review"] = {
        "version": 1,
        "materialized_id": materialized_id(result.plan),
        "draft": draft or candidate and checks["status"] in ("failed", "not_run"),
        "checks": spec,
    }
    finalize(captured)
    bundle = save_bundle(captured, output)
    return _report(captured, bundle, spec, previous=previous, limit=limit, measured=measured)


def review(source, *, output=None, name=None, previous=None, checks=None, asset_roots=(), limit=5, response="detailed"):
    """Render a selected DSL sound once, or review a retained bundle without regeneration."""
    validate_response(response)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise DSLError("E_LIMIT", "review limit must be 1..100")
    spec = check_spec(checks)
    if isinstance(source, Capture) or Path(source).is_dir():
        captured = _capture(source)
        if name is not None and name != captured.manifest.get("dsl", {}).get("sound"):
            raise DSLError("E_SELECTION", "bundle contains another sound")
        if checks is None:
            spec = check_spec(captured.manifest.get("dsl", {}).get("review", {}).get("checks"))
        report = _report(
            captured, None if isinstance(source, Capture) else source, spec, previous=previous, limit=limit
        )
        return respond(report, "review", response)
    if output is None:
        raise DSLError("E_REQUIRED", "source review needs an output bundle directory")
    document = load(source, asset_roots=asset_roots)
    result = compile_document(document, name=name)
    if previous is not None:
        old = _capture(previous)
        metadata = old.manifest.get("dsl", {})
        if metadata and (metadata["path"], metadata["sound"]) != (str(document.path), result.name):
            raise DSLError("E_SELECTION", "previous capture belongs to a different source or sound")
    return respond(_publish(result, output, spec, previous=previous, limit=limit), "review", response)


def describe(bundle, **options):
    """Describe an immutable observed capture; does not read current source or assets."""
    return describe_capture(_capture(bundle), **options)


def _pairs(values, kind):
    if not isinstance(values, dict) or not 1 <= len(values) <= 32:
        raise DSLError("E_PATCH", kind + " needs 1..32 distinct field paths")
    paths = list(values)
    for path in paths:
        if not parts(path):
            raise DSLError("E_PATCH", "field edits cannot replace the whole source")
    if any(a != b and b.startswith(a + "/") for a in paths for b in paths):
        raise DSLError("E_PATCH", "field paths overlap")


def _set_ops(document, target, values):
    data = copy.deepcopy(document.data)
    base = target_pointer(data, target)
    operations = []
    for path, value in values.items():
        tokens = parts(path)
        for index in range(1, len(tokens)):
            relative = "/" + "/".join(t.replace("~", "~0").replace("/", "~1") for t in tokens[:index])
            try:
                get(data, base + relative)
            except DSLError:
                if tokens[index].isdecimal():
                    raise DSLError("E_POINTER", "create an array explicitly before editing its elements") from None
                operation = {"op": "set", "target": target, "path": relative, "value": {}}
                data, _ = apply_operations(data, [operation])
                operations.append(operation)
        operation = {"op": "set", "target": target, "path": path, "value": value}
        data, _ = apply_operations(data, [operation])
        operations.append(operation)
    return operations


def _refine_ops(document, target, values, observed, layer):
    metadata = observed.manifest["dsl"]
    root = next(n for n in observed.manifest["nodes"] if n["id"] == observed.manifest["root"])
    if root["kind"] != "voice" or target != "sound:" + quote(metadata["sound"], safe=""):
        raise DSLError("E_CAPABILITY", "review refinement requires the selected root Voice; use expand/patch otherwise")
    pointer = target_pointer(document.data, target)
    expression = copy.deepcopy(get(document.data, pointer))
    selected = None
    if layer:
        _, selected = layer_selection(observed, layer)
        if not selected["can_refine"]:
            raise DSLError("E_CAPABILITY", selected["reason"])
    if "edit" in expression:
        if (
            not layer
            and (expression.get("remove") or expression.get("append"))
            and any(p.count("/") > 1 for p in values)
        ):
            raise DSLError("E_SELECTION", "select a captured layer to map its original path after structural edits")
        wrapped = expression
    else:
        wrapped = {"edit": expression, "expect": metadata["review"]["materialized_id"], "set": {}}
    updates = dict(wrapped.get("set", {}))
    for path, value in values.items():
        updates[(selected["original_path"] if selected else "") + path] = value
    wrapped["set"] = updates
    return [{"op": "set", "target": target, "path": "", "value": wrapped}]


def edit_file(
    source,
    *,
    from_bundle,
    output,
    target=None,
    set_fields=None,
    refine=None,
    layer=None,
    checks=None,
    dry_run=False,
    asset_roots=(),
    limit=5,
    response="detailed",
):
    """Trial-render and validate before committing through the existing patch transaction."""
    validate_response(response)
    if isinstance(from_bundle, Capture):
        raise DSLError("E_SELECTION", "edits require a saved bundle path so its integrity can be verified")
    observed = _capture(from_bundle)
    metadata = observed.manifest.get("dsl", {})
    context = metadata.get("review", {})
    if not context.get("materialized_id") or context.get("draft"):
        raise DSLError("E_SELECTION", "edits need a non-draft bundle from a source review")
    source = Path(source).resolve()
    if str(source) != metadata["path"]:
        raise DSLError("E_REVISION_CONFLICT", "bundle belongs to another source file")
    if (set_fields is None) == (refine is None):
        raise DSLError("E_PATCH", "choose authored set fields or materialized refinement")
    if layer and refine is None:
        raise DSLError("E_SELECTION", "layer selection requires materialized refinement")
    values = refine if refine is not None else set_fields
    _pairs(values, "refine" if refine is not None else "set")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise DSLError("E_LIMIT", "edit limit must be 1..100")
    spec = check_spec(context.get("checks") if checks is None else checks)
    document = load(source, asset_roots=asset_roots)
    if document.revision != metadata["authored_revision"]:
        raise DSLError("E_REVISION_CONFLICT", "authored source changed; review before editing")
    target = target or "sound:" + quote(metadata["sound"], safe="")
    if target.split("/", 1)[0] != "sound:" + quote(metadata["sound"], safe=""):
        name = unquote(target.split("/", 1)[0].partition(":")[2]) if target.startswith("def:") else None
        if name is None or metadata["sound"] not in affected(document.data, name):
            raise DSLError("E_SELECTION", "review the sound affected by this target before editing")

    def observe(current):
        actual = load(source, asset_roots=asset_roots)
        if actual.revision != metadata["authored_revision"]:
            raise DSLError("E_REVISION_CONFLICT", "source changed outside the patch transaction")
        if renderer_id() != observed.manifest["renderer"]:
            raise DSLError("E_REVISION_CONFLICT", "renderer changed; create a fresh source review")
        compiled = compile_document(current, name=metadata["sound"])
        if compiled.compiler_id != metadata["compiler_id"]:
            raise DSLError("E_REVISION_CONFLICT", "compiler changed; create a fresh source review")
        if materialized_id(compiled.plan) != context["materialized_id"]:
            raise DSLError("E_OVERRIDE_STALE", "selected materialization changed; review before refining")
        dependencies = _dependencies(compiled)
        if dependencies != metadata["dependencies"]:
            raise DSLError("E_REVISION_CONFLICT", "observed dependencies changed; create a fresh review")
        _unchanged(dependencies)

    operations = (
        _refine_ops(document, target, values, observed, layer)
        if refine is not None
        else _set_ops(document, target, values)
    )
    envelope = {
        "format": "tare.tools.tune.patch",
        "version": 1,
        "expect": metadata["authored_revision"],
        "ops": operations,
    }

    def prepare(candidate):
        compiled = compile_document(candidate, name=metadata["sound"])
        report = _publish(compiled, output, spec, previous=observed, limit=limit, draft=dry_run, candidate=True)
        if report["checks"]["status"] in ("failed", "not_run"):
            raise DSLError(
                "E_CHECK_FAILED",
                "candidate failed requested checks; source was not written",
                details=respond(report, "review", response),
            )
        return report

    acknowledgement, report = _patch_file(
        source, envelope, dry_run=dry_run, asset_roots=asset_roots, observe=observe, prepare=prepare
    )
    report["edit"] = {
        "status": "preview" if dry_run else "applied",
        "target": target,
        "mode": "refine" if refine is not None else "set",
        "fields": list(values),
        "affected": acknowledgement["affected"][:limit],
        "affected_total": acknowledgement["affected_total"],
    }
    return respond(report, "review", response)
