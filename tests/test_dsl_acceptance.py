"""Independent acceptance predicates for the reviewed DSL milestones."""

import copy
import json
import random
from fractions import Fraction as F

import numpy as np
import pytest
from test_dsl_loading import project

from tare.tools.tune import Sfx
from tare.tools.tune.dsl import DSLError, compile_document, load
from tare.tools.tune.dsl.compiler import Compiler
from tare.tools.tune.dsl.composition import capture_plan
from tare.tools.tune.dsl.patch import patch_file, target_pointer
from tare.tools.tune.dsl.query import expansion, inspection
from tare.tools.tune.dsl.registry import OPS, catalog
from tare.tools.tune.spec import Syllable


def test_every_catalog_entry_has_a_typed_example_and_discovery_contract():
    rows = catalog()
    assert {row["name"] for row in rows if row["domain"] == "op"} == OPS
    for row in rows:
        assert {"meaning", "result_type", "defaults", "fields", "capabilities", "example"} <= row.keys(), row
        assert row["meaning"] and isinstance(row["fields"], dict)
        example = row["example"]
        data = project(
            {"sfx": "ui"},
            defs={
                "hit": {
                    "params": {"power": {"type": "number", "default": 0.5}},
                    "body": {"sfx": "ui", "power": {"param": "power"}},
                }
            },
        )
        document = load(data=data)
        compiler = Compiler(document)
        # Discovery must not synthesize or require installation of example assets.
        compiler.prepare(example, document.context, "/example", "sound:example")
    assert catalog("transform", "quantize")[0]["fields"]["quantize"]["type"] == "quantity"
    for name in ("ui", "blade"):
        entry = catalog("sfx", name)[0]
        defaults = entry["defaults"]
        assert isinstance(defaults["genes"], dict) and isinstance(defaults["knobs"], dict)
        assert compile_document(load(data=project({"sfx": name} | defaults))).plan.kind == "voice"


def test_default_cue_registry_fits_the_calibrated_16khz_preflight_budget():
    from tare.tools.tune.music import CUES

    for name in CUES:
        from tare.tools.tune.dsl import Budgets

        result = compile_document(load(data=project({"music": name}), limits=Budgets(layers=8192, notes=2048)))
        assert result.plan.kind == "cue" and result.cost["weighted_work"] > 0


def generated_phrase(r, depth):
    if depth == 0:
        events = [[r.choice([48, 60, 60.5, [60, 64]]), F(i, 2), F(1, 4), 0.5] for i in range(r.randint(1, 3))]
        span = F(2)
        expression = {"notes": [[p, float(a), float(h), v] for p, a, h, v in events], "span": "2b"}
    else:
        operation = r.choice(["seq", "repeat", "overlay"])
        first, a, span_a = generated_phrase(r, depth - 1)
        second, b, span_b = generated_phrase(r, depth - 1)
        if operation == "repeat":
            expression = {"repeat": 2, "of": first}
            events = a + [[p, start + span_a, hold, vel] for p, start, hold, vel in a]
            span = span_a * 2
        elif operation == "seq":
            expression = {"seq": [first, second], "gap": "1/4b"}
            events = a + [[p, start + span_a + F(1, 4), hold, vel] for p, start, hold, vel in b]
            span = span_a + span_b + F(1, 4)
        else:
            expression = {"overlay": [first, second]}
            events, span = a + b, max(span_a, span_b)
    transpose, stretch = r.choice([-12, 0, 7, 0.5]), r.choice([F(1, 2), F(1), F(2)])
    expression["then"] = [{"transpose": transpose}, {"stretch": float(stretch)}, {"velocity": 0.8}]
    shifted = []
    for p, a, h, v in events:
        shifted.append(
            [[n + transpose for n in p] if isinstance(p, list) else p + transpose, a * stretch, h * stretch, v * 0.8]
        )
    return expression, shifted, span * stretch


@pytest.mark.parametrize("seed", range(40))
def test_bounded_random_phrases_match_independent_timeline_and_one_call_per_note(seed, monkeypatch):
    from tare.tools.tune.instruments import INSTRUMENTS

    invoked = []

    def oracle_instrument(note):
        invoked.append((note.start, note.dur, note.vel))
        return [Syllable(note.start, note.dur, [(0, note.f)], source="sine")]

    monkeypatch.setitem(INSTRUMENTS, "oracle", oracle_instrument)
    expression, expected, span = generated_phrase(random.Random(seed), 2)
    document = load(
        data=project(
            {
                "score": {
                    "bpm": 120,
                    "meter": 3,
                    "tracks": [{"name": "oracle", "instrument": "oracle", "notes": expression}],
                }
            }
        )
    )
    compiled = compile_document(document)
    actual = compiled.plan.source.tracks["oracle"].events
    flattened = [
        (p, float(a), float(h), v)
        for pitch, a, h, v in expected
        for p in (pitch if isinstance(pitch, list) else [pitch])
    ]
    assert [(e["pitch"], e["beat"], e["beats"], e["velocity"]) for e in actual] == flattened
    assert len(invoked) == len(flattened)
    assert np.allclose(invoked, [(a * 0.5, h * 0.5, v) for _, a, h, v in flattened], rtol=0, atol=1e-12)
    compiler = Compiler(document)
    phrase = compiler.build(compiler.prepare(expression, document.context, "/phrase", "sound:main"))
    assert phrase.span == span


def test_track_clip_and_leaf_definition_targets_preserve_actual_lineage(tmp_path):
    expression = {
        "score": {
            "tracks": [
                {
                    "name": "lead-v1",
                    "clips": [{"id": "phrase", "instrument": "harp", "notes": {"seq": [{"use": "a"}, {"use": "b"}]}}],
                }
            ]
        }
    }
    data = project(
        expression,
        defs={name: {"body": {"notes": [[pitch, 0, 0.25]], "span": "1b"}} for name, pitch in (("a", 60), ("b", 64))},
    )
    path = tmp_path / "song.tune.json"
    path.write_text(json.dumps(data))
    assert target_pointer(data, "sound:a/track:lead-v1/id:phrase") == "/sounds/a/score/tracks/0/clips/0"
    result = compile_document(load(path))
    events = result.plan.source.tracks["lead-v1"].events
    assert [e["dsl_origin"]["chain"][0]["definition"] for e in events] == ["a", "b"]
    assert all(e["dsl_origin"]["target"].endswith("/track:lead-v1/id:phrase") for e in events)
    revision = load(path).revision
    response = patch_file(
        path,
        {
            "format": "tare.tools.tune.patch",
            "version": 1,
            "expect": revision,
            "ops": [{"op": "set", "target": "def:a", "path": "/body/then", "value": [{"transpose": -12}]}],
        },
    )
    assert response["affected"] == ["a"]
    assert compile_document(load(path)).plan.source.tracks["lead-v1"].events[0]["pitch"] == 48


def test_refinement_retains_recipe_and_original_to_edited_layer_lineage():
    original = {"sfx": "ui", "style": "crystal", "event": "confirm", "dry": True}
    plan = compile_document(load(data=project(original)))
    guard = expansion(plan)["materialized_id"]
    count = len(plan.plan.source.modal)
    assert count > 1
    expression = {
        "edit": original,
        "expect": guard,
        "set": {"/modal/1/hardness": 3000},
        "remove": ["/modal/0"],
        "append": {"noise": []},
    }
    expression["append"] = {"/noise": [{"start": 0, "dur": 0.02, "freq": [[0, 2000]], "gain": 0.01}]}
    changed = compile_document(load(data=project(expression)))
    assert changed.plan.source.modal[0].hardness == 3000
    captured = capture_plan(changed.plan)
    parts = captured.manifest["nodes"][0]["parts"]
    assert parts[0]["dsl_origin"]["original_path"] == "/modal/1"
    assert parts[0]["dsl_origin"]["override_paths"] == ["/modal/1/hardness"]
    assert parts[-1]["dsl_origin"]["original_path"] is None
    assert changed.plan.origins["override"]["seed_order_warning"]
    stale = copy.deepcopy(expression)
    stale["edit"]["power"] = 0.9
    with pytest.raises(DSLError) as failed:
        compile_document(load(data=project(stale)))
    details = failed.value.to_dict()["details"]
    assert details["current_materialized_id"] != guard and len(details["targets"]) <= 3
    assert Sfx("ui", "crystal", dry=True).voice("confirm").modal[1].hardness != 3000


def test_stage_drilldown_is_bounded_and_query_identity_is_stable():
    plan = compile_document(
        load(
            data=project(
                {
                    "mix": [
                        {
                            "at": "100ms",
                            "sound": {
                                "voice": [
                                    {"syllable": {"start": 0, "dur": 0.05, "source": "sine", "pitch": [[0, 440]]}}
                                ]
                            },
                        }
                    ]
                }
            )
        )
    )
    captured = capture_plan(plan.plan)
    stages = inspection(captured, view="stages")["items"]
    child = next(row["id"] for row in stages if row["parent"])
    rows = inspection(captured, view="layers", node_id=child, start=0.1, end=len(captured.audio) / captured.sr)
    assert len(rows["items"]) == 1 and rows["items"][0]["power"] > 0


def test_complete_scene_workflow_matches_manual_processing_and_exports(tmp_path):
    from tare.tools.tune import Creature, capture
    from tare.tools.tune.audio_io import read_channels, write_wav
    from tare.tools.tune.bundles import load_bundle, save_bundle
    from tare.tools.tune.dsl.adapters import capabilities
    from tare.tools.tune.dsl.migrate import freeze, variants
    from tare.tools.tune.music import Cue
    from tare.tools.tune.score import Score
    from tare.tools.tune.speech import Speaker

    write_wav(tmp_path / "contact.wav", np.sin(np.arange(160) * 0.2).astype(np.float32) * 0.05, 16000)
    definitions = {
        "wolf": {
            "params": {"take": {"type": "integer", "default": 0}},
            "body": {"creature": "mammal", "species": "wolf", "call": "attack", "take": {"param": "take"}},
        },
        "narrator": {"body": {"speaker": "deep"}},
        "line": {"body": {"say": "Ready!", "lang": "en", "seed": 17, "speaker": {"use": "narrator"}}},
        "cue": {"body": {"music": "levelup", "seed": 4}},
    }
    sources = [{"use": "wolf"}, {"use": "line"}, {"use": "cue"}, {"audio": "contact.wav"}]
    source = tmp_path / "scene.tune.json"
    data = project(
        {
            "mix": [{"id": f"part{i}", "at": f"{i * 100}ms", "sound": child} for i, child in enumerate(sources)],
            "effects": [{"type": "limiter", "ceiling": 0.5}],
        },
        defs=definitions,
    )
    source.write_text(json.dumps(data))
    compiled = compile_document(load(source))
    captured = capture_plan(compiled.plan)
    manual = Score(sr=16000, hall=0, effects=[{"type": "limiter", "ceiling": 0.5}])
    leaf_sources = [
        Creature("mammal", species="wolf").voice("attack"),
        Speaker.preset("deep").voice("Ready!", "en", seed=17),
        Cue("levelup", seed=4, sr=16000),
    ]
    for i, leaf in enumerate(leaf_sources):
        manual.add(capture(leaf, 16000).audio, at=i / 10)
    audio, _ = read_channels(tmp_path / "contact.wav")
    manual.add(audio, at=0.3)
    assert np.array_equal(captured.audio, manual.render())
    loaded = load_bundle(save_bundle(captured, tmp_path / "bundles"))
    np.testing.assert_allclose(loaded.replay(), captured.audio, rtol=0, atol=1e-7)
    assert not capabilities(compiled.plan)["midi"] and not capabilities(compiled.plan)["voice_json"]
    with pytest.raises(DSLError):
        freeze(source, tmp_path / "unsupported.voice.json", format="voice")
    # the scene rings out through the wolf's reverb, so its WAV keeps the whole captured PCM
    assert freeze(source, tmp_path / "scene.wav", format="wav")["pcm_id"] == captured.manifest["pcm_id"]
    result = variants(source, tmp_path / "variants.tune.json", "wolf", "take", [0, 1, 2, 3])
    assert len(result["sounds"]) == 4
    first = compile_document(load(tmp_path / "variants.tune.json"), name="wolf_0")
    second = compile_document(load(tmp_path / "variants.tune.json"), name="wolf_0")
    assert np.array_equal(capture_plan(first.plan).audio, capture_plan(second.plan).audio)
