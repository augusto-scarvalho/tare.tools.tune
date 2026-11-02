"""Facts, explicit artifact checks and bounded diffs over retained captures; no synthesis."""

import copy
import math

from ..analysis import against
from ..inspection import inspect_audio
from .model import DSLError
from .query import bounded
from .validate import choice, known, number, obj

CHECK_FORMAT = "tare.tools.tune.checks"
# A tolerance per measure, each in the unit its difference comes in (analysis.against).
TOLERANCES = {"active_s": ("ratio", 1, 10), "attack_ms": ("max_delta", 0, 1000), "centroid_hz": ("semitones", 0, 48),
              "f0_hz": ("semitones", 0, 48), "env_db": ("max", 0, 120)}


def check_spec(value=None):
    value = copy.deepcopy(value) if value is not None else {"format": CHECK_FORMAT, "version": 1}
    known(value, {"format", "version", "duration_s", "peak_dbfs", "sample_rate", "channels", "capabilities",
                  "reference"})
    if value.get("format") != CHECK_FORMAT or type(value.get("version")) is not int or value["version"] != 1:
        raise DSLError("E_CHECK", "expected tare.tools.tune.checks version 1")
    for name, low, high in (("duration_s", 0, 180), ("peak_dbfs", -200, 24)):
        if name not in value:
            continue
        bounds = value[name]
        known(bounds, {"min", "max"}, "/" + name)
        if not bounds:
            raise DSLError("E_CHECK", "provide a min or max bound", "/" + name)
        for key, limit in bounds.items():
            number(limit, "/" + name + "/" + key, low, high)
        if bounds.get("min", low) > bounds.get("max", high):
            raise DSLError("E_CHECK", "min cannot exceed max", "/" + name)
    if "sample_rate" in value:
        number(value["sample_rate"], "/sample_rate", 1000, 192000, integer=True)
    if "channels" in value:
        number(value["channels"], "/channels", 1, 2, integer=True)
    if "capabilities" in value:
        capabilities = value["capabilities"]
        if (
            not isinstance(capabilities, list)
            or len(capabilities) > 4
            or any(c not in ("pcm", "voice_json", "native_voice", "midi") for c in capabilities)
            or len(set(capabilities)) != len(capabilities)
        ):
            raise DSLError("E_CHECK", "capabilities are unique pcm/voice_json/native_voice/midi names", "/capabilities")
    for name, tolerance in obj(value.get("reference", {}), "/reference").items():
        choice(name, TOLERANCES, "/reference")
        unit, low, high = TOLERANCES[name]
        known(tolerance, {unit}, "/reference/" + name)
        if unit not in tolerance:
            raise DSLError("E_CHECK", f"{name} takes a {unit}", "/reference/" + name)
        number(tolerance[unit], f"/reference/{name}/{unit}", low, high)
    return value


def facts(captured, limit=5, reference=True):
    audio = inspect_audio(captured.audio, captured.sr, pitch=False)
    nodes = captured.manifest["nodes"]
    tracks = []
    stages = []
    count = 0
    for node in nodes:
        count += len(node["parts"])
        if len(stages) < limit:
            shared = {
                k: small(node["params"][k]) if isinstance(node["params"][k], dict | list) else node["params"][k]
                for k in ("gain", "lowpass", "drive", "hall", "echo", "effects", "room", "space")
                if node["params"].get(k)
            }
            factors = {k: v for k, v in node["factors"].items() if isinstance(v, int | float) and math.isfinite(v)}
            stages.append({"id": node["id"], "kind": node["kind"], "shared_processing": shared, "factors": factors})
        if "track" in node:
            track = node["track"]
            events = track["events"]
            tracks.append(
                {
                    "name": track["name"][:160],
                    "events": len(events),
                    "first_start_s": min((e["start"] for e in events), default=None),
                    "last_end_s": max((e["start"] + e["duration"] for e in events), default=None),
                    "pitches": sorted({e["pitch"] for e in events})[:12],
                }
            )
    result = {
        "duration_s": audio["duration"],
        "frames": audio["frames"],
        "sample_rate": captured.sr,
        "channels": audio["channels"],
        "levels": audio["levels"],
        "stages": len(nodes),
        "parts": count,
        "processing": stages,
        "processing_truncated": len(nodes) > limit,
        "tracks": tracks[:limit],
        "tracks_truncated": len(tracks) > limit,
    }
    if reference and "reference" in captured.arrays:
        about = captured.manifest["reference"]
        result["reference"] = {
            "file": about.get("file"),
            "pcm_id": about["pcm_id"],
            **against(captured.arrays["reference"], about["sample_rate"], captured.audio, captured.sr),
        }
    return result


def reference_checks(spec, measured):
    """One row per tolerance in spec["reference"]: none when the sound has no reference (it is `absent`, not failed);
    `not_run` with the reason when a requested measure could not be taken."""
    block = measured.get("reference")
    if block is None:
        return []
    rows = []
    for name, tolerance in spec.get("reference", {}).items():
        unit, limit = next(iter(tolerance.items()))
        entry = block["measures"].get(name, {"status": block["status"], "reason": block.get("reason")})
        if entry["status"] in ("unvoiced", "voicing_differs"):  # f0: both unpitched agree, one pitched does not
            agree = entry["status"] == "unvoiced"
            rows.append({"check": "reference:" + name, "status": "passed" if agree else "failed",
                         "actual": [entry["reference"], entry["sound"]], "expected": tolerance})
            continue
        if entry["status"] != "measured":
            rows.append({"check": "reference:" + name, "status": "not_run", "expected": tolerance,
                         "reason": entry.get("reason") or entry["status"]})
            continue
        actual = entry[{"active_s": "ratio", "attack_ms": "delta", "env_db": "mean_abs_db"}.get(name, "semitones")]
        passed = 1 / limit <= actual <= limit if unit == "ratio" else abs(actual) <= limit
        rows.append({"check": "reference:" + name, "status": "passed" if passed else "failed", "actual": actual,
                     "expected": tolerance})
    return rows


def run_checks(captured, spec, measured):
    results = []
    for name in ("duration_s", "sample_rate", "channels", "peak_dbfs"):
        if name not in spec:
            continue
        if name == "peak_dbfs":
            peak = max((level["peak"] for level in measured["levels"]), default=0)
            actual = 20 * math.log10(peak) if peak else None
            passed = all(
                peak <= 10 ** (v / 20) if k == "max" else peak >= 10 ** (v / 20) for k, v in spec[name].items()
            )
        else:
            actual = measured[name]
            wanted = spec[name]
            passed = (
                all(actual <= v if k == "max" else actual >= v for k, v in wanted.items())
                if isinstance(wanted, dict)
                else actual == wanted
            )
        results.append(
            {"check": name, "status": "passed" if passed else "failed", "actual": actual, "expected": spec[name]}
        )
    capabilities = captured.manifest.get("dsl", {}).get("capabilities")
    for name in spec.get("capabilities", []):
        actual = capabilities.get(name) if capabilities else None
        results.append(
            {
                "check": "capability:" + name,
                "status": "not_run" if actual is None else "passed" if actual else "failed",
                "actual": actual,
                **({"reason": "capture has no DSL capability record"} if actual is None else {}),
            }
        )
    results += reference_checks(spec, measured)
    status = (
        "not_requested"
        if not results
        else "passed"
        if all(r["status"] == "passed" for r in results)
        else "failed"
        if any(r["status"] == "failed" for r in results)
        else "not_run"
    )
    coverage = {"capture_integrity": "passed", "perceptual_quality": "not_run", "pitch": "not_requested"}
    if "reference" in measured:
        coverage["reference"] = measured["reference"]["status"]
    elif spec.get("reference"):
        coverage["reference"] = "absent"  # tolerances asked, but this sound has no recording to be held against
    return {
        "status": status,
        "results": results,
        "coverage": coverage,
        "basis": "retained float PCM, before PCM16 conversion",
    }


def source_changes(before, after, limit=8):
    rows = []
    total = 0

    def short(value):
        if isinstance(value, dict | list):
            return {"type": type(value).__name__, "items": len(value)}
        return value[:160] if isinstance(value, str) else value

    def visit(old, new, path):
        nonlocal total
        if old == new:
            return
        if isinstance(old, dict) and isinstance(new, dict):
            for key in sorted(old.keys() | new.keys()):
                at = path + "/" + key.replace("~", "~0").replace("/", "~1")
                value = new[key] if key in new else old[key]
                if key in old and key in new:
                    visit(old[key], new[key], at)
                elif isinstance(value, dict) and value:  # a new or dropped object: each of its fields is a change
                    visit(old.get(key, {}), new.get(key, {}), at)
                else:
                    total += 1
                    if len(rows) < limit:
                        rows.append(
                            {
                                "pointer": at,
                                "change": "added" if key in new else "removed",
                                "value": short(value),
                            }
                        )
            return
        total += 1
        if len(rows) < limit:
            rows.append({"pointer": path, "before": short(old), "after": short(new)})

    visit(before, after, "")
    return {"items": rows, "total": total, "truncated": total > len(rows)}


def changes(current, previous, current_facts, limit=8):
    old = facts(previous, limit, reference=False)
    result = {
        "previous_revision": previous.manifest["revision"],
        "pcm_changed": current.manifest["pcm_id"] != previous.manifest["pcm_id"],
        "duration_delta_s": current_facts["duration_s"] - old["duration_s"],
        "channels": {"before": old["channels"], "after": current_facts["channels"]},
        "sample_rate": {"before": old["sample_rate"], "after": current_facts["sample_rate"]},
        "peak_dbfs": {
            "before": [v["peak_dbfs"] for v in old["levels"]],
            "after": [v["peak_dbfs"] for v in current_facts["levels"]],
        },
    }
    left, right = previous.manifest.get("dsl"), current.manifest.get("dsl")
    if left and right:
        result["source"] = source_changes(left["document"], right["document"], limit)
    result["tracks"] = {"before": old["tracks"], "after": current_facts["tracks"]}
    return result


def small(value, limit=5):
    result, omitted = bounded(value, limit=limit, depth=4)
    return {"value": result, **({"omitted": omitted} if omitted else {})}
