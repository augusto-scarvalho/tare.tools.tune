"""Explicit response envelopes; validation and identity checks stay in the operations."""

from .model import DSLError

SCHEMA = "tune.compact/1"
CONTROL_FIELDS = {
    "schema",
    "bundle",
    "audio",
    "can_edit",
    "checks",
    "edit",
    "authored_revision",
    "materialized_id",
    "revision",
    "target",
    "pointer",
    "stage",
    "root_stage",
    "window_s",
    "band_hz",
    "measure",
    "truncated",
    "next",
    "total",
    "omitted",
    "affected",
    "affected_total",
    "warnings",
    "dry_run",
    "source_revision",
    "pcm_id",
}
FIELDS = {
    "query": {
        "authored_revision",
        "target",
        "pointer",
        "fragment",
        "omitted",
        "truncated",
        "affected",
        "affected_total",
    },
    "expand": {"authored_revision", "materialized_id", "type", "items", "truncated", "next", "total"},
    "inspect": {
        "revision",
        "stage",
        "items",
        "window_s",
        "band_hz",
        "measure",
        "truncated",
        "next",
        "total",
        "status",
        "duration",
        "frames",
        "channels",
        "sample_rate",
        "levels",
        "root_stage",
        "stage_count",
        "capabilities",
        "attribution",
    },
    "patch": {"authored_revision", "changed", "affected", "affected_total", "dry_run", "warnings"},
    "freeze": {"output", "kind", "frames", "sample_rate", "warnings", "regeneration", "source_revision", "pcm_id",
               "silence_cut_s"},
}


def validate_response(response, view=None):
    if response not in ("detailed", "compact"):
        raise DSLError("E_ENUM", "response must be detailed or compact")
    if response == "compact" and view == "full":
        raise DSLError("E_OPTION", "full view requires a detailed response")


def respond(result, kind, response="detailed"):
    validate_response(response)
    if response == "detailed" or result.get("schema") == SCHEMA:
        return result
    if kind == "export":
        kind = "freeze"
    if kind == "error":
        return dict(result, schema=SCHEMA)
    if kind == "review":
        return review_summary(result)
    if kind not in FIELDS:
        raise DSLError("E_OPTION", "this operation has no compact response profile")
    keys = FIELDS[kind] | {"warnings"}
    compact = {"schema": SCHEMA}
    for key, value in result.items():
        if key not in keys:
            continue
        if key in ("truncated", "dry_run") and not value:
            continue
        if key == "total" and not result.get("truncated"):
            continue
        if key not in ("items", "changed", "band_hz") and (value is None or value == [] or value == {}):
            continue
        compact[key] = value
    if result.get("affected_total", 0) > len(result.get("affected", [])):
        compact["truncated"] = True
    elif kind == "patch" and set(compact.get("affected", ())) == {
        t.removeprefix("sound:") for t in result.get("changed", ()) if t.startswith("sound:")
    }:
        compact.pop("affected", None)  # names only repeat the edited sounds; the count stays, wider impact is kept
    return compact


def reference_pairs(block):
    """[recording, sound] per measure, a measure's status when it could not be taken, env_db as one difference."""
    if block["status"] != "measured":
        return block["status"]
    pairs = {}
    for key in ("active_s", "attack_ms", "centroid_hz", "f0_hz"):
        entry = block["measures"][key]
        shown = entry["status"] in ("measured", "voicing_differs")
        pairs[key] = [entry["reference"], entry["sound"]] if shown else entry["status"]
    pairs["env_db"] = block["measures"]["env_db"]["mean_abs_db"]
    return pairs


def review_summary(result):
    """Summarize observations, never the checks or guards that authorize a write."""
    compact = {"schema": SCHEMA}
    for key in ("bundle", "audio", "can_edit", "warnings"):
        if key in result:
            compact[key] = result[key]
    if "edit" in result:
        compact["edit"] = {key: result["edit"][key] for key in ("status", "affected", "affected_total")}
        if compact["edit"]["affected"] == [result.get("sound")] and compact["edit"]["affected_total"] == 1:
            del compact["edit"]["affected"]  # only the reviewed sound itself; shared impact keeps its names
    checks = result["checks"]
    summary = {"status": checks["status"], "coverage": checks["coverage"]}
    passed = [row["check"] for row in checks["results"] if row["status"] == "passed"]
    if passed:
        summary["passed"] = passed
    remaining = [row for row in checks["results"] if row["status"] != "passed"]
    if remaining:
        summary["results"] = remaining
    compact["checks"] = summary
    facts = result["facts"]
    compact["facts"] = {key: facts[key] for key in ("duration_s", "sample_rate", "channels")}
    for key in ("peak_dbfs", "rms_dbfs"):
        compact["facts"][key] = [level[key] for level in facts["levels"]]
    if facts.get("tracks_truncated"):
        compact["facts"]["tracks_truncated"] = True
    for key in ("bars_db", "rubs", "arrangement"):
        if key in facts:
            compact["facts"][key] = facts[key]
    if "reference" in facts:
        compact["ref"] = reference_pairs(facts["reference"])
    if "changes" not in result:
        if facts.get("tracks"):
            compact["facts"]["tracks"] = facts["tracks"]
        return compact
    changes = result["changes"]
    delta = {"pcm_changed": changes["pcm_changed"]}
    if changes["duration_delta_s"]:
        delta["duration_delta_s"] = changes["duration_delta_s"]
    for key in ("channels", "sample_rate", "peak_dbfs"):
        values = changes[key]
        if values["before"] != values["after"]:
            delta[key] = values
    if "source" in changes:
        delta["source_changes"] = changes["source"]["total"]
    tracks = changes["tracks"]
    if tracks["before"] or tracks["after"]:
        delta["tracks"] = tracks
    compact["changes"] = delta
    return compact
