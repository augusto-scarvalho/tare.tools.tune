import json
from pathlib import Path

import numpy as np
import pytest
from test_dsl_loading import project

from tare.tools.tune import Sfx, capture
from tare.tools.tune.audio_io import write_wav
from tare.tools.tune.bundles import load_bundle, save_bundle
from tare.tools.tune.cli import main
from tare.tools.tune.dsl import DSLError, creature, describe, edit_file, load, review
from tare.tools.tune.dsl.adapters import materialized_id
from tare.tools.tune.dsl.compiler import compile_document


def source(tmp_path, body=None, **fields):
    path = tmp_path / "source.json"
    path.write_text(
        json.dumps(
            project(body or {"sfx": "ui", "style": "crystal", "event": "confirm", "species": 7, "dry": True}, **fields)
        )
    )
    return path


def test_review_preserves_audio_and_reuses_archived_capture_without_compiling(tmp_path, monkeypatch):
    from tare.tools.tune.dsl import workflow

    path = source(tmp_path)
    report = review(path, output=tmp_path / "bundles")
    observed = load_bundle(report["bundle"])
    wanted = capture(Sfx("ui", "crystal", species=7, dry=True).voice("confirm"), 16000)
    np.testing.assert_array_equal(observed.audio, wanted.audio)
    assert report["checks"]["status"] == "not_requested" and report["can_edit"]
    assert report["checks"]["coverage"]["perceptual_quality"] == "not_run"

    def forbidden(*args, **kwargs):
        raise AssertionError("must not regenerate retained captures")

    monkeypatch.setattr(workflow, "compile_document", forbidden)
    monkeypatch.setattr(workflow, "capture_compiled", forbidden)
    path.unlink()
    assert review(report["bundle"])["facts"]["frames"] == len(wanted.audio)
    detail = describe(report["bundle"], fields=["power", "knobs.ring"])
    assert detail["operations"] == ["set", "refine"]
    assert {f["path"] for f in detail["fields"]} == {"/power", "/knobs/ring"}


def test_invocation_edit_creates_missing_parent_preserves_definition_and_other_sound(tmp_path):
    path = source(
        tmp_path,
        {"use": "hit"},
        defs={
            "hit": {
                "params": {"power": {"type": "number", "default": 0.5}},
                "body": {"sfx": "ui", "style": "crystal", "event": "confirm", "dry": True, "power": {"param": "power"}},
            }
        },
    )
    data = json.loads(path.read_text())
    data["sounds"]["other"] = {"sfx": "ui", "event": "error", "dry": True}
    path.write_text(json.dumps(data))
    first = review(path, name="a", output=tmp_path / "bundles")
    result = edit_file(path, from_bundle=first["bundle"], output=tmp_path / "bundles", set_fields={"/with/power": 0.7})
    updated = json.loads(path.read_text())
    assert updated["defs"] == data["defs"] and updated["sounds"]["other"] == data["sounds"]["other"]
    assert updated["sounds"]["a"]["with"]["power"] == 0.7
    assert result["edit"]["affected"] == ["a"] and result["changes"]["source"]["total"] == 1
    from tare.tools.tune.dsl.review_data import source_changes
    knobs = {"ring": 0.3, "register": 1, "brightness": 0}
    knobs = source_changes({"sfx": "ui"}, {"sfx": "ui", "power": 1, "knobs": knobs})
    assert knobs["total"] == 4 and knobs["items"][0] == {"pointer": "/knobs/brightness", "change": "added", "value": 0}
    assert list((tmp_path / ".tune-backups").glob("*.bak"))
    before = path.read_bytes()
    with pytest.raises(DSLError) as stale:
        edit_file(path, from_bundle=first["bundle"], output=tmp_path / "bundles", set_fields={"/with/power": 0.8})
    assert stale.value.code == "E_REVISION_CONFLICT" and path.read_bytes() == before


def test_layer_refinement_maps_original_path_and_keeps_existing_override(tmp_path):
    body = {"sfx": "ui", "style": "crystal", "event": "confirm", "species": 7, "dry": True}
    guard = materialized_id(compile_document(load(data=project(body))).plan)
    path = source(tmp_path, {"edit": body, "expect": guard, "remove": ["/modal/0"], "set": {"/lowpass": 1800}})
    first = review(path, output=tmp_path / "bundles")
    detail = describe(first["bundle"], layer="n0/p0", fields=["hardness"])
    assert detail["layer"]["current_path"] == "/modal/0" and detail["layer"]["original_path"] == "/modal/1"
    result = edit_file(
        path, from_bundle=first["bundle"], output=tmp_path / "bundles", layer="n0/p0", refine={"/hardness": 1234}
    )
    current = json.loads(path.read_text())["sounds"]["a"]
    assert current["set"] == {"/lowpass": 1800, "/modal/1/hardness": 1234}
    assert current["remove"] == ["/modal/0"] and current["expect"] == guard
    assert "edit" not in current["edit"]
    captured = load_bundle(result["bundle"])
    wanted = Sfx("ui", "crystal", species=7, dry=True).voice("confirm")
    wanted.modal.pop(0)
    wanted.modal[0].hardness = 1234
    wanted.lowpass = 1800
    np.testing.assert_array_equal(captured.audio, capture(wanted, 16000).audio)


def test_dry_run_is_read_only_and_check_failure_never_commits(tmp_path):
    path = source(tmp_path)
    first = review(path, output=tmp_path / "bundles")
    before = path.read_bytes()
    preview = edit_file(
        path, from_bundle=first["bundle"], output=tmp_path / "bundles", refine={"/gain": 0.25}, dry_run=True
    )
    assert path.read_bytes() == before and not preview["can_edit"] and preview["edit"]["status"] == "preview"
    with pytest.raises(DSLError):
        edit_file(path, from_bundle=preview["bundle"], output=tmp_path / "bundles", refine={"/gain": 0.5})
    checks = {"format": "tare.tools.tune.checks", "version": 1, "peak_dbfs": {"max": -10}}
    with pytest.raises(DSLError) as failure:
        edit_file(
            path, from_bundle=first["bundle"], output=tmp_path / "bundles", set_fields={"/power": 0.8}, checks=checks
        )
    assert failure.value.code == "E_CHECK_FAILED" and failure.value.exit_code == 5
    assert path.read_bytes() == before and not list((tmp_path / ".tune-backups").glob("*.bak"))
    assert not failure.value.details["can_edit"]
    applied = edit_file(
        path, from_bundle=first["bundle"], output=tmp_path / "bundles", refine={"/gain": 0.25}, checks=checks
    )
    assert applied["checks"]["status"] == "passed"


def test_changed_asset_or_renderer_refuses_without_writing(tmp_path, monkeypatch):
    from tare.tools.tune.dsl import workflow

    audio = tmp_path / "contact.wav"
    write_wav(audio, np.full(160, 0.125, np.float32), 16000)
    path = source(tmp_path, {"audio": "contact.wav"})
    first = review(path, output=tmp_path / "bundles")
    before = path.read_bytes()
    write_wav(audio, np.full(160, 0.25, np.float32), 16000)
    with pytest.raises(DSLError) as stale:
        edit_file(path, from_bundle=first["bundle"], output=tmp_path / "bundles", set_fields={"/id": "new"})
    assert stale.value.exit_code == 3 and path.read_bytes() == before
    fresh = review(path, output=tmp_path / "bundles")
    monkeypatch.setattr(workflow, "renderer_id", lambda: {"code": "changed"})
    with pytest.raises(DSLError) as stale:
        edit_file(path, from_bundle=fresh["bundle"], output=tmp_path / "bundles", set_fields={"/id": "new"})
    assert stale.value.code == "E_REVISION_CONFLICT" and path.read_bytes() == before


def test_failed_render_and_external_writer_preserve_last_good_source(tmp_path, monkeypatch):
    from tare.tools.tune.dsl import workflow

    path = source(tmp_path)
    first = review(path, output=tmp_path / "bundles")
    before = path.read_bytes()

    def broken(*args, **kwargs):
        raise DSLError("E_BUILD", "render failed")

    original = workflow.capture_compiled
    monkeypatch.setattr(workflow, "capture_compiled", broken)
    with pytest.raises(DSLError):
        edit_file(path, from_bundle=first["bundle"], output=tmp_path / "bundles", set_fields={"/power": 0.8})
    assert path.read_bytes() == before
    external = json.loads(before)
    external["sounds"]["a"]["power"] = 0.4

    def competing(result):
        captured = original(result)
        path.write_text(json.dumps(external))
        return captured

    monkeypatch.setattr(workflow, "capture_compiled", competing)
    with pytest.raises(DSLError) as failure:
        edit_file(path, from_bundle=first["bundle"], output=tmp_path / "bundles", set_fields={"/power": 0.8})
    assert failure.value.code == "E_REVISION_CONFLICT" and json.loads(path.read_text()) == external
    np.testing.assert_array_equal(
        load_bundle(first["bundle"]).audio,
        capture(Sfx("ui", "crystal", species=7, dry=True).voice("confirm"), 16000).audio,
    )


def test_find_does_not_silently_select_shared_targets_and_identity_edit_is_audio_neutral(tmp_path):
    path = source(
        tmp_path,
        {"use": "hit"},
        defs={
            "hit": {
                "params": {"power": {"type": "number", "default": 0.5}},
                "body": {"sfx": "ui", "event": "confirm", "dry": True, "power": {"param": "power"}},
            }
        },
    )
    data = json.loads(path.read_text())
    data["sounds"]["second"] = {"use": "hit"}
    path.write_text(json.dumps(data))
    first = review(path, name="a", output=tmp_path / "bundles")
    matches = describe(first["bundle"], find="confirm")["matches"]
    assert matches["total"] == 3 and "target" not in describe(first["bundle"], find="confirm")
    shared = describe(first["bundle"], target="def:hit", fields=["power"])
    assert shared["affected_total"] == 2 and shared["scope"] == "shared_definition"
    result = edit_file(path, from_bundle=first["bundle"], output=tmp_path / "bundles", set_fields={"/id": "label"})
    assert not result["changes"]["pcm_changed"] and result["changes"]["source"]["total"] == 1


def test_legacy_capture_is_read_only_and_silence_checks_are_finite(tmp_path):
    old = capture(np.zeros(160, dtype=np.float32), 16000)
    bundle = save_bundle(old, tmp_path / "bundles")
    assert not describe(bundle)["can_edit"]
    with pytest.raises(DSLError):
        edit_file(tmp_path / "other.json", from_bundle=bundle, output=tmp_path / "bundles", set_fields={"/id": "x"})
    path = source(tmp_path, {"rest": "10ms"})
    checks = {
        "format": "tare.tools.tune.checks",
        "version": 1,
        "peak_dbfs": {"max": -30},
        "duration_s": {"min": 0.001, "max": 0.1},
    }
    report = review(path, output=tmp_path / "bundles", checks=checks)
    assert report["checks"]["status"] == "passed"
    json.dumps(report, allow_nan=False)
    checks["peak_dbfs"] = {"min": -30}
    assert review(path, output=tmp_path / "bundles", checks=checks)["checks"]["status"] == "failed"


def test_cli_help_review_describe_and_atomic_batch(tmp_path, capsys):
    path = source(tmp_path)
    assert creature("mammal").to_dict()["creature"] == "mammal"
    assert main(["dsl", "help", "edit", "--json"]) == 0
    assert "Trial-render" in json.loads(capsys.readouterr().out)["meaning"]
    assert main(["dsl", "help", "listener", "--json"]) == 0
    assert "--dry-run" in json.loads(capsys.readouterr().out)["rules"][0]
    assert main(["dsl", "review", str(path), "-o", str(tmp_path / "bundles"), "--json"]) == 0
    bundle = json.loads(capsys.readouterr().out)["bundle"]
    assert main(["dsl", "describe", bundle, "--fields", "power", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["fields"][0]["path"] == "/power"
    assert (
        main(
            [
                "dsl",
                "edit",
                str(path),
                "--from-bundle",
                bundle,
                "-o",
                str(tmp_path / "bundles"),
                "--set",
                "/power",
                "0.7",
                "--set",
                "/knobs/ring",
                "0.6",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["edit"]["status"] == "applied"
    before = path.read_bytes()
    assert (
        main(
            [
                "dsl",
                "edit",
                str(path),
                "--from-bundle",
                bundle,
                "-o",
                str(tmp_path / "bundles"),
                "--set",
                "/power",
                "0.8",
                "--json",
            ]
        )
        == 3
    )
    assert json.loads(capsys.readouterr().err)["code"] == "E_REVISION_CONFLICT" and path.read_bytes() == before


def test_saved_bundle_integrity_is_required_for_writes(tmp_path):
    path = source(tmp_path)
    first = review(path, output=tmp_path / "bundles")
    observed = load_bundle(first["bundle"])
    before = path.read_bytes()
    with pytest.raises(DSLError, match="saved bundle"):
        edit_file(path, from_bundle=observed, output=tmp_path / "bundles", set_fields={"/power": 0.6})
    manifest = Path(first["bundle"]) / "manifest.json"
    data = json.loads(manifest.read_text())
    data["dsl"]["review"]["materialized_id"] = "0" * 64
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="provenance"):
        edit_file(path, from_bundle=first["bundle"], output=tmp_path / "bundles", set_fields={"/power": 0.6})
    assert path.read_bytes() == before


def test_failed_review_can_be_fixed_and_repeated_refinement_keeps_one_recipe(tmp_path, capsys):
    path = source(tmp_path)
    checks = {"format": "tare.tools.tune.checks", "version": 1, "peak_dbfs": {"max": -15}}
    check_path = tmp_path / "checks.json"
    check_path.write_text(json.dumps(checks))
    assert (
        main(["dsl", "review", str(path), "-o", str(tmp_path / "bundles"), "--checks", str(check_path), "--json"]) == 5
    )
    failed = json.loads(capsys.readouterr().err)["details"]
    assert failed["can_edit"] and failed["checks"]["status"] == "failed"
    fixed = edit_file(path, from_bundle=failed["bundle"], output=tmp_path / "bundles", refine={"/gain": 0.1})
    second = edit_file(path, from_bundle=fixed["bundle"], output=tmp_path / "bundles", refine={"/lowpass": 2400})
    expression = json.loads(path.read_text())["sounds"]["a"]
    assert expression["set"] == {"/gain": 0.1, "/lowpass": 2400}
    assert "sfx" in expression["edit"] and "edit" not in expression["edit"]
    assert second["checks"]["status"] == "passed"


@pytest.mark.parametrize(
    "checks",
    [
        {"format": "tare.tools.tune.checks", "version": True},
        {"format": "tare.tools.tune.checks", "version": 1, "duration_s": {"min": 2, "max": 1}},
        {"format": "tare.tools.tune.checks", "version": 1, "peak_dbfs": {"max": float("nan")}},
        {"format": "tare.tools.tune.checks", "version": 1, "capabilities": ["midi", "midi"]},
        {"format": "tare.tools.tune.checks", "version": 1, "capabilities": [{"eval": "no"}]},
        {"format": "tare.tools.tune.checks", "version": 1, "perceptual_quality": True},
    ],
)
def test_invalid_checks_do_not_publish(tmp_path, checks):
    path = source(tmp_path)
    with pytest.raises(DSLError):
        review(path, output=tmp_path / "bundles", checks=checks)
    assert not (tmp_path / "bundles").exists()


def test_reference_dependency_and_previous_selection_are_checked(tmp_path):
    reference = tmp_path / "reference.wav"
    write_wav(reference, np.zeros(160, np.float32), 16000)
    path = source(tmp_path, reference={"file": "reference.wav"})
    first = review(path, output=tmp_path / "bundles")
    before = path.read_bytes()
    write_wav(reference, np.ones(160, np.float32) * 0.1, 16000)
    with pytest.raises(DSLError) as stale:
        edit_file(path, from_bundle=first["bundle"], output=tmp_path / "bundles", set_fields={"/power": 0.6})
    assert stale.value.exit_code == 3 and path.read_bytes() == before
    other = tmp_path / "other.json"
    other.write_bytes(before)
    with pytest.raises(DSLError, match="different source"):
        review(other, output=tmp_path / "other-bundles", previous=first["bundle"])
    assert not (tmp_path / "other-bundles").exists()


def test_transpose_preserves_rests_seed_and_midi_timing(tmp_path):
    from test_authoring_workflows import parse_midi

    from tare.tools.tune.midi_export import export_midi
    from tare.tools.tune.score import Score

    path = tmp_path / "music.json"
    data = json.loads((Path(__file__).parents[1] / "examples/dsl-music.tune.json").read_text())
    path.write_text(json.dumps(data))
    first = review(
        path,
        output=tmp_path / "bundles",
        checks={
            "format": "tare.tools.tune.checks",
            "version": 1,
            "capabilities": ["midi"],
            "channels": 2,
        },
    )
    result = edit_file(
        path,
        from_bundle=first["bundle"],
        output=tmp_path / "bundles",
        target="def:motif",
        set_fields={"/body/then": [{"transpose": 12}]},
    )
    assert result["edit"]["affected"] == ["theme"] and result["checks"]["status"] == "passed"
    current = compile_document(load(path))
    score = current.plan.source
    assert [(e["beat"], e["beats"], e["pitch"]) for e in score.tracks["lead-v1"].events] == [(0, 1, 72), (3, 1, 72)]
    assert [(e["beat"], e["pitch"]) for e in score.tracks["bass-v1"].events] == [(0, 60), (3, 60)]
    wanted = Score(bpm=120, meter=3, sr=16000, hall=0.2, seed=17)
    wanted.track("lead-v1", pan=-0.3).play("harp", [(72, 0, 1), (72, 3, 1)])
    wanted.track("bass-v1", pan=0.3).play("marimba", [(60, 0, 1), (60, 3, 1)])
    np.testing.assert_array_equal(load_bundle(result["bundle"]).audio, wanted.render(loop=3))
    midi = tmp_path / "theme.mid"
    export_midi(score, midi, loop=current.plan.loop)
    tracks = parse_midi(midi)
    assert (2880, 0x90, [72, 102]) in tracks[1] and (3840, 0x80, [72, 0]) in tracks[1]
    assert json.loads(path.read_text())["sounds"] == data["sounds"]


def test_appended_layer_and_unobserved_sound_need_explicit_selection(tmp_path):
    body = {"sfx": "ui", "style": "crystal", "event": "confirm", "species": 7, "dry": True}
    base = compile_document(load(data=project(body))).plan
    path = source(
        tmp_path,
        {
            "edit": body,
            "expect": materialized_id(base),
            "append": {"/noise": [{"start": 0, "dur": 0.1, "freq": [[0, 1000], [1, 1000]]}]},
        },
    )
    data = json.loads(path.read_text())
    data["sounds"]["other"] = body
    path.write_text(json.dumps(data))
    first = review(path, name="a", output=tmp_path / "bundles")
    observed = load_bundle(first["bundle"])
    part = next(p for n in observed.manifest["nodes"] for p in n["parts"] if p["dsl_origin"].get("override_path"))
    assert describe(first["bundle"], layer=part["id"])["operations"] == []
    assert describe(first["bundle"], target="sound:other")["operations"] == []
    before = path.read_bytes()
    with pytest.raises(DSLError, match="original root"):
        edit_file(
            path, from_bundle=first["bundle"], output=tmp_path / "bundles", layer=part["id"], refine={"/gain": 0.5}
        )
    with pytest.raises(DSLError, match="affected by this target"):
        edit_file(
            path,
            from_bundle=first["bundle"],
            output=tmp_path / "bundles",
            target="sound:other",
            set_fields={"/power": 0.5},
        )
    assert path.read_bytes() == before


def test_describe_lists_a_speaker_objects_fields(tmp_path, capsys):
    path = tmp_path / "line.tune.json"
    line = {"say": "Oi.", "lang": "pt", "speaker": {"speaker": "default", "pitch": 140, "engine": "formant"}}
    path.write_text(json.dumps({"format": "tare.tools.tune.dsl", "version": 1, "context": {"sample_rate": 16000},
                                "sounds": {"hello": line}}))
    bundle = review(path, output=tmp_path / "b")["bundle"]
    asked = ["speaker.pitch", "speaker.engine", "speaker.tract"]
    rows = {f["name"]: f for f in describe(bundle, fields=asked)["fields"]}
    assert rows["speaker.pitch"]["current"] == {"value": 140} and rows["speaker.pitch"]["path"] == "/speaker/pitch"
    assert rows["speaker.engine"]["current"] == {"value": "formant"}
    assert rows["speaker.tract"]["current"] == {"value": 1.0}  # what the preset has, not overridden
    with pytest.raises(DSLError) as wrong:
        describe(bundle, fields=["engine"])
    assert wrong.value.suggestions == ["speaker.engine"]
    assert main(["dsl", "describe", str(bundle), "--fields", "engine"]) != 0
    assert "did you mean speaker.engine?" in capsys.readouterr().err
    assert describe(bundle, find="formant")["matches"]["total"] == 1
    edited = edit_file(path, from_bundle=bundle, output=tmp_path / "b", set_fields={"/speaker/pitch": 160})
    assert edited["changes"]["source"]["total"] == 1
    assert json.loads(path.read_text())["sounds"]["hello"]["speaker"]["pitch"] == 160
