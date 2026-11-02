import json
import threading
import time
import urllib.request

import numpy as np
from test_dsl_loading import project

from tare.tools.tune.audio_io import write_wav
from tare.tools.tune.dsl import build_file, compile_document, load
from tare.tools.tune.dsl.composition import capture_plan
from tare.tools.tune.dsl.migrate import freeze
from tare.tools.tune.studio import make_server


def test_nested_cue_loop_effects_survive_serialization(tmp_path):
    from tare.tools.tune.bundles import load_bundle, save_bundle

    expression = {
        "mix": [
            {"sound": {"music": "levelup", "seed": 4}, "gain": 0.5},
            {"sound": {"fm": {"duration": 0.2}}, "at": "0.1s", "gain": 0.1},
        ],
        "loop": "1s",
        "effects": [{"type": "limiter", "ceiling": 0.4}],
    }
    captured = capture_plan(compile_document(load(data=project(expression))).plan)
    assert captured.audio.shape == (16000, 2)
    np.testing.assert_allclose(captured.replay(), captured.audio, rtol=0, atol=1e-7)
    loaded = load_bundle(save_bundle(captured, tmp_path))
    np.testing.assert_allclose(loaded.replay(), captured.audio, rtol=0, atol=1e-7)


def test_worker_recovers_missing_declared_asset_and_source_errors(tmp_path):
    path = tmp_path / "scene.tune.json"
    path.write_text(json.dumps(project({"audio": "missing.wav"})))
    server = make_server(path, tmp_path / "store", port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def wait(phase, different=None):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = json.loads(urllib.request.urlopen(base + "/api/state").read())
            if state["phase"] == phase and (different is None or state["revision"] != different):
                return state
            time.sleep(0.1)
        raise AssertionError(state)

    try:
        failed = wait("error")
        assert failed["diagnostic"]["code"] == "E_ASSET"
        write_wav(tmp_path / "missing.wav", np.ones(800, np.float32) * 0.1, 16000)
        ready = wait("ready")
        revision = ready["revision"]
        view = json.loads(urllib.request.urlopen(base + f"/api/inspect?revision={revision}&view=layers&top=1").read())
        assert len(view["items"]) == 1
        path.write_text(json.dumps(project({"sfx": "ui", "knobs": {"ring": 99}})))
        failed = wait("error")
        assert failed["revision"] == revision and failed["diagnostic"]["code"] == "E_KNOB_RANGE"
        path.write_text(json.dumps(project({"sfx": "ui", "dry": True})))
        assert wait("ready", revision)["revision"] != revision
    finally:
        server.shutdown()
        server.server_close()


def test_explicit_track_freeze_identifies_omitted_score_processing(tmp_path):
    from pathlib import Path

    from tare.tools.tune import Voice, render

    source = Path(__file__).parent.parent / "examples/dsl-music.tune.json"
    output = tmp_path / "lead.voice.json"
    report = freeze(source, output, format="voice", track="lead-v1")
    assert report["warnings"] and "pan" in report["warnings"][0]
    captured = build_file(source)
    node = next(n for n in captured.manifest["nodes"] if n.get("track", {}).get("name") == "lead-v1")
    voice = Voice.from_dict(json.loads(output.read_text()))
    assert np.array_equal(render(voice, 16000), captured.arrays[node["audio"]])
