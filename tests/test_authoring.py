import json
from pathlib import Path

import numpy as np
import pytest

from tare.tools.tune import Voice, render
from tare.tools.tune.bundles import RevisionStore, load_bundle, save_bundle
from tare.tools.tune.diagnostics import Limits, capture, pcm_id
from tare.tools.tune.inspection import inspect_audio, inspect_capture
from tare.tools.tune.score import Score
from tare.tools.tune.spec import Syllable

FIXTURES = Path(__file__).parent / "fixtures" / "authoring"


def legacy_score():
    s = Score(bpm=120, meter=3, sr=16000, hall=0.2, seed=42, echo=(0.12, 0.2, 2300))
    s.track("harp", pan=-0.6, send=0.2, echo=0.1).play("harp", [("C4", 0, 0.5), ("E4", 0.5, 0.5)])
    s.track("bars", pan=0.7, send=0.1).play("marimba", [(["G4", "B4"], 1, 0.5, 0.4)])
    return s


def test_frozen_audio_and_observation_are_unchanged():
    voices = json.loads((FIXTURES / "voices.json").read_text())
    with np.load(FIXTURES / "legacy.npz") as reference:
        for name, document in voices.items():
            voice = Voice.from_dict(document)
            serialized = voice.to_json()
            actual = render(voice, 16000)
            observed = capture(voice, 16000)
            assert actual.shape == reference[name].shape
            np.testing.assert_allclose(actual, reference[name], atol=1e-6, rtol=0)
            assert np.array_equal(actual, observed.audio)
            np.testing.assert_allclose(observed.replay(), actual, atol=1e-7, rtol=0)
            assert voice.to_json() == serialized
        score = legacy_score()
        actual = score.render(loop=score.bar(1))
        observed = capture(score, loop=score.bar(1))
        np.testing.assert_allclose(actual, reference["score"], atol=1e-6, rtol=0)
        assert np.array_equal(actual, observed.audio)
        np.testing.assert_allclose(observed.replay(), actual, atol=1e-7, rtol=0)


def test_events_consume_generators_and_custom_instruments_once():
    calls = []
    def instrument(note):
        calls.append(note)
        return [Syllable(note.start, note.dur, [(0, note.f)], source="sine")]
    s = Score(sr=16000, hall=0)
    track = s.track("custom", send=0).play(instrument, (("C4", i, 0.1) for i in range(2)))
    captured = capture(s)
    captured.replay(mute=[captured.manifest["nodes"][1]["parts"][0]["id"]])
    assert len(calls) == len(track.events) == 2
    assert track.events[1]["layers"] == [1]
    assert track.events[1]["source"]["file"].endswith("test_authoring.py")


def test_channel_identity_and_invalid_inputs():
    a = np.zeros((100, 2), dtype=np.float32)
    b = a.copy()
    b[1, 1] = 0.1
    assert pcm_id(a, 16000) != pcm_id(b, 16000)
    for y in (np.zeros(0), np.zeros(1), np.zeros(100), a):
        json.dumps(inspect_audio(y, 16000), allow_nan=False)
    with pytest.raises(ValueError, match="finite"):
        inspect_audio(np.array([np.nan]), 16000)
    with pytest.raises(ValueError, match="limit"):
        capture(np.zeros(32000), 16000, limits=Limits(seconds=0.1))


def test_band_attribution_and_raw_octave_changes():
    v = Voice(syllables=[Syllable(0, 0.4, [(0, 200)], source="sine", gain=0.8),
                         Syllable(0, 0.4, [(0, 5000)], source="sine", gain=0.1)])
    observed = capture(v, 16000)
    report = inspect_capture(observed, start=0.1, end=0.2, band=(4000, 6000), pitch=False)
    assert report["layers"][0]["label"] == "syllables[1]"
    sr = 16000
    t = np.arange(sr) / sr
    fundamental = 0.2 * np.sin(2 * np.pi * 220 * t) + 0.7 * np.sin(2 * np.pi * 440 * t)
    frames = inspect_audio(fundamental, sr)["fundamental"]["frames"]
    assert all(frame["hz"] is None or abs(frame["hz"] - 220) < 4 for frame in frames)
    transition = np.r_[np.sin(2 * np.pi * 220 * t[:8000]), np.sin(2 * np.pi * 440 * t[:8000])]
    frames = inspect_audio(transition, sr)["fundamental"]["frames"]
    assert np.median([f["hz"] for f in frames if f["time"] > 0.65 and f["hz"]]) == pytest.approx(440, abs=3)
    anti = np.column_stack([fundamental, -fundamental])
    assert inspect_audio(anti, sr, band=(200, 500), pitch=False)["query"]["channel_sum_power"] > 0.1


def test_bundle_integrity_revision_races_and_answer_conflicts(tmp_path):
    a = capture(np.ones((100, 2), dtype=np.float32) * 0.1, 16000)
    path = save_bundle(a, tmp_path / "bundles")
    assert np.array_equal(load_bundle(path).audio, a.audio)
    store = RevisionStore(tmp_path / "store")
    first, second = store.request(), store.request()
    assert not store.publish(a, first)
    assert store.state()["revision"] is None
    assert store.publish(a, second)
    revision = a.manifest["revision"]
    saved = store.save_answers(revision, 0, {"note": "keep"}, {"loudness_match": False})
    assert saved["version"] == 1 and saved["playback_id"]
    with pytest.raises(ValueError, match="conflict"):
        store.save_answers(revision, 0, {}, {})
    (path / "audio.wav").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        load_bundle(path)
