import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest

from tare.tools.tune import Voice
from tare.tools.tune.bundles import RevisionStore, load_bundle, save_bundle
from tare.tools.tune.diagnostics import capture
from tare.tools.tune.effects import apply_effects, fm_tone
from tare.tools.tune.exports import export_sprite
from tare.tools.tune.inspection import inspect_capture
from tare.tools.tune.midi_export import export_midi
from tare.tools.tune.music import Cue
from tare.tools.tune.patterns import parse_pattern
from tare.tools.tune.score import Score
from tare.tools.tune.spec import Syllable
from tare.tools.tune.studio import make_server


def tone(freq=220, gain=0.8):
    return Syllable(0, 0.2, [(0, freq)], source="sine", gain=gain)


def test_capture_is_frozen_and_different_origins_do_not_collapse():
    a = Voice(syllables=[tone()], meta={"source": "first"})
    first = capture(a, 16000)
    a.meta["source"] = "second"
    second = capture(a, 16000)
    assert first.manifest["source"]["spec"]["meta"]["source"] == "first"
    assert first.manifest["pcm_id"] == second.manifest["pcm_id"]
    assert first.manifest["source_id"] != second.manifest["source_id"]
    assert first.manifest["revision"] != second.manifest["revision"]


def test_mute_does_not_renormalize_or_change_surviving_seeds():
    v = Voice(syllables=[tone(220, 0.9), tone(700, 0.02)], drive=1.2, room=0.1, space=0.1)
    c = capture(v, 16000)
    before = json.dumps(c.manifest, sort_keys=True)
    muted = c.replay(mute=[c.manifest["nodes"][0]["parts"][0]["id"]])
    assert len(muted) == len(c.audio)
    assert np.max(np.abs(muted)) < np.max(np.abs(c.audio)) * 0.2
    assert json.dumps(c.manifest, sort_keys=True) == before
    np.testing.assert_allclose(c.replay(), c.audio, atol=1e-7, rtol=0)


def test_cue_and_placed_stereo_replay(tmp_path):
    cue = Cue("levelup", seed=3, sr=16000)
    c = capture(cue)
    assert np.array_equal(c.audio, cue.render())
    np.testing.assert_allclose(c.replay(), c.audio, atol=1e-7, rtol=0)
    score = Score(sr=16000, hall=0)
    score.add(np.column_stack([np.ones(100) * 0.1, np.ones(100) * -0.1]))
    captured = capture(score)
    assert captured.manifest["source"]["sounds"][0]["origin"]["kind"] == "audio"
    np.testing.assert_allclose(captured.replay(), captured.audio, atol=1e-7, rtol=0)
    bundle = save_bundle(captured, tmp_path)
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["source"]["settings"]["bpm"] = 101
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="provenance"):
        load_bundle(bundle)


def test_shared_processing_is_reported_and_analysis_settings_are_distinct():
    c = capture(Voice(syllables=[tone(1800)], drive=4, air=0.1), 16000)
    a = inspect_capture(c, pitch=False)
    b = inspect_capture(c, band=(3000, 7000), pitch=False)
    assert a["analysis_id"] != b["analysis_id"]
    assert "drive" in a["stages"][0]["shared"] and "air" in a["stages"][0]["shared"]
    assert "not additive" in a["attribution"]


def test_simultaneous_evaluations_conflict_instead_of_losing_data(tmp_path):
    c = capture(Voice(syllables=[tone()]), 16000)
    store = RevisionStore(tmp_path)
    assert store.publish(c, store.request())
    def save(value):
        try:
            return store.save_answers(c.manifest["revision"], 0, {"note": value}, {})["version"]
        except ValueError:
            return "conflict"
    with ThreadPoolExecutor(2) as pool:
        result = list(pool.map(save, ["first", "second"]))
    assert sorted(map(str, result)) == ["1", "conflict"]
    assert store.answers(c.manifest["revision"])["answers"]["note"] in ("first", "second")


def parse_midi(path):
    """Independent reader for channel messages in exported standard MIDI tracks."""
    data = Path(path).read_bytes()
    assert data[:4] == b"MThd" and int.from_bytes(data[12:14], "big") == 960
    cursor = 14
    tracks = []
    def number(buf, offset):
        value = 0
        while True:
            byte = buf[offset]
            offset += 1
            value = value * 128 + (byte & 127)
            if not byte & 128:
                return value, offset
    while cursor < len(data):
        assert data[cursor:cursor + 4] == b"MTrk"
        size = int.from_bytes(data[cursor + 4:cursor + 8], "big")
        buf = data[cursor + 8:cursor + 8 + size]
        offset, tick, events = 0, 0, []
        while offset < len(buf):
            delta, offset = number(buf, offset)
            tick += delta
            status = buf[offset]
            offset += 1
            if status == 255:
                kind = buf[offset]
                length, offset = number(buf, offset + 1)
                if kind == 0x58:
                    events.append((tick, "meter", list(buf[offset:offset + length])))
                offset += length
            else:
                length = 1 if status & 0xf0 in (0xc0, 0xd0) else 2
                events.append((tick, status, list(buf[offset:offset + length])))
                offset += length
        tracks.append(events)
        cursor += 8 + size
    return tracks


def test_midi_uses_retained_held_events_offsets_meter_and_instrument_groups(tmp_path):
    score = Score(bpm=120, meter=3, sr=16000)
    track = score.track("mixed")
    track.play("harp", [(["C4", "E4"], 0.5, 1.25, 0.5)], offset=1)
    track.play("marimba", [("G4", 0, 0.5, 1)])
    path = tmp_path / "composition.mid"
    report = export_midi(score, path)
    tracks = parse_midi(path)
    assert report["tracks"] == 2
    assert (0, "meter", [3, 2, 24, 8]) in tracks[0]
    assert (1440, 0x90, [60, 64]) in tracks[1]
    assert (2640, 0x80, [60, 0]) in tracks[1]
    assert (0, 0x91, [67, 127]) in tracks[2]
    assert (0, 0xc0, [46]) in tracks[1] and (0, 0xc1, [12]) in tracks[2]
    score.bpm = 90
    with pytest.raises(ValueError, match="tempo changed"):
        export_midi(score, path)


def test_midi_rejects_unrepresented_material_and_reports_approximations(tmp_path):
    score = Score()
    score.track("micro").play("harp", [(60.5, 0, 1)])
    with pytest.raises(ValueError, match="fractional"):
        export_midi(score, tmp_path / "micro.mid")
    report = export_midi(score, tmp_path / "approx.mid", approximate=True)
    assert "fractional" in report["warnings"][0]
    score = Score()
    score.track("overlap").play("harp", [(60, 0, 2), (60, 1, 2)])
    with pytest.raises(ValueError, match="overlapping"):
        export_midi(score, tmp_path / "overlap.mid")


def test_patterns_follow_meter_holds_and_chords():
    notes, length = parse_pattern("C4+E4 - . G4 . . | C5 - - . . .", steps_per_beat=2, meter=3)
    assert length == 6 and notes[0] == (["C4", "E4"], 0, 1, 0.8)
    with pytest.raises(ValueError, match="bar"):
        parse_pattern("C4 . |", meter=3)
    with pytest.raises(ValueError, match="hold"):
        parse_pattern(". -")


def test_optional_dsp_is_deterministic_and_limiter_sees_final_gain():
    a = fm_tone(sr=16000)
    assert np.array_equal(a, fm_tone(sr=16000)) and np.isfinite(a).all()
    y = np.column_stack([np.ones(1000) * 2, np.ones(1000) * -2])
    result = apply_effects(y, 16000, [{"type": "limiter", "ceiling": 0.5}])
    assert np.max(np.abs(result)) <= 0.5
    score = Score(sr=16000, hall=0, effects=[{"type": "chorus", "mix": 0.2},
                                           {"type": "limiter", "ceiling": 0.4}])
    score.track("bars", send=0).play("marimba", [("C4", 0, 1)])
    c = capture(score, loop=0.5)
    np.testing.assert_allclose(c.replay(), c.audio, atol=1e-7, rtol=0)
    assert np.max(np.abs(c.audio)) <= 0.400001


def test_sprite_decodes_to_authoritative_sample_coordinates(tmp_path):
    sf = pytest.importorskip("soundfile")
    a = np.zeros((1600, 2), dtype=np.float32)
    a[80, 0], a[1500, 1] = 0.8, 0.7
    b = np.zeros_like(a)
    b[160, 0] = 0.9
    sounds = {"a": capture(a, 16000), "b": capture(b, 16000)}
    out = export_sprite(sounds, tmp_path, ogg=True, gap=0.05)
    manifest = json.loads((out / "manifest.json").read_text())
    decoded, sr = sf.read(out / "bank.ogg", always_2d=True)
    assert decoded.shape == (3520 + manifest["codec_padding_samples"]["bank.ogg"], 2) and sr == 16000
    assert manifest["entries"]["b"]["start_sample"] == 2400
    # b's silent tail is cut after its last loud 10 ms; a sounds until its last window, so it stays whole
    assert [manifest["entries"][k]["silence_cut_frames"] for k in "ab"] == [0, 1280]
    assert abs(int(np.argmax(np.abs(decoded[:1600, 0]))) - 80) <= 16
    assert abs(int(np.argmax(np.abs(decoded[2400:4000, 0]))) - 160) <= 16
    howler = json.loads((out / "howler.json").read_text())
    assert howler["sprite"]["b"] == [150, 20]
    assert hashlib.sha256((out / "bank.ogg").read_bytes()).hexdigest() == manifest["files"]["bank.ogg"]


def test_trim_tail_cuts_only_a_silent_tail_and_fades_into_the_cut():
    from tare.tools.tune.audio_io import trim_tail

    tone = np.sin(np.arange(4800) / 5) * np.exp(-np.arange(4800) / 300)  # -60 dB after ~2150 samples
    cut = trim_tail(np.concatenate([tone, np.zeros(8000)]), 16000)
    assert 1920 <= len(cut) <= 2240 and cut[-1] == 0 and np.array_equal(cut[:1700], tone[:1700])
    stereo = trim_tail(np.stack([np.r_[tone, np.zeros(800)], np.zeros(5600)], axis=1), 16000)
    assert stereo.shape == (len(cut), 2)
    for whole in (np.zeros(800), np.ones(800), np.zeros(0)):
        assert trim_tail(whole, 16000) is whole


def test_freeze_cuts_a_dry_tail_but_keeps_reverb_loops_and_keep_tail(tmp_path):
    from tare.tools.tune.dsl.migrate import freeze

    source = tmp_path / "bank.tune.json"
    source.write_text(json.dumps({"format": "tare.tools.tune.dsl", "version": 1, "context": {"sample_rate": 16000},
                                  "sounds": {"clash": {"sfx": "blade", "style": "steel", "event": "clash", "dry": True},
                                             "wolf": {"creature": "mammal", "species": "wolf", "call": "attack"}}}))
    def cut(name, **options):
        return freeze(source, tmp_path / f"{name}{len(options)}.wav", name=name, format="wav", **options)
    assert cut("clash")["silence_cut_s"] > 1  # a dry ring decays far below hearing long before its render ends
    assert "silence_cut_s" not in cut("wolf")  # a creature rings out through its reverb (`space`)
    assert "silence_cut_s" not in cut("clash", keep_tail=True)


def test_live_worker_retains_last_good_revision_after_invalid_edit(tmp_path):
    path = tmp_path / "project.json"
    source = {"sample_rate": 16000, "source": {"type": "voice", "spec": Voice(syllables=[tone()]).to_dict()}}
    path.write_text(json.dumps(source))
    server = make_server(path, tmp_path / "store", port=0, watch=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    def wait_for(phase):
        until = time.monotonic() + 25
        while time.monotonic() < until:
            state = json.loads(urllib.request.urlopen(base + "/api/state").read())
            if state["phase"] == phase:
                return state
            time.sleep(0.05)
        raise AssertionError(state)
    try:
        ready = wait_for("ready")
        revision = ready["revision"]
        with pytest.raises(OSError):
            make_server(path, tmp_path / "duplicate", port=server.server_address[1], watch=False)
        assert urllib.request.urlopen(base + f"/api/audio?revision={revision}").read()[:4] == b"RIFF"
        path.write_text("invalid JSON")
        failed = wait_for("error")
        assert failed["revision"] == revision
        assert urllib.request.urlopen(base + f"/api/audio?revision={revision}").read()[:4] == b"RIFF"
        source["source"]["spec"]["syllables"][0]["pitch"] = [[0, 880]]
        path.write_text(json.dumps(source))
        assert wait_for("ready")["revision"] != revision
    finally:
        server.shutdown()
        server.server_close()


def test_inspection_projects_looped_layers_without_mixing_bus_stages():
    score = Score(bpm=120, hall=0, sr=16000)
    score.track("late", send=0).play("harp", [("C4", 0.9, 0.3)])
    captured = capture(score, loop=0.5)
    root = inspect_capture(captured, start=0, end=0.1, pitch=False)
    voice = inspect_capture(captured, start=0, end=0.1, pitch=False, node_id="n1")
    assert {layer["node"] for layer in root["layers"]} == {"n0"}
    assert {layer["node"] for layer in voice["layers"]} == {"n1"}
    assert root["layers"][0]["power"] > 0 and voice["layers"][0]["power"] > 0
    cancelled = capture(Voice(syllables=[tone(gain=1), tone(gain=-1)]), 16000)
    report = inspect_capture(cancelled, pitch=False)
    assert report["query"]["channel_sum_power"] == 0
    assert all(layer["power"] > 0 for layer in report["layers"])


def test_modified_capture_is_rejected_before_publication_and_midi_rejects_layer_edits(tmp_path):
    c = capture(Voice(syllables=[tone()]), 16000)
    c.arrays[c.manifest["nodes"][0]["parts"][0]["audio"]][0] += 0.01
    with pytest.raises(ValueError, match="identity"):
        save_bundle(c, tmp_path / "bundles")
    assert not (tmp_path / "bundles" / c.manifest["revision"]).exists()
    score = Score()
    track = score.track("edited").play("harp", [("C4", 0, 1)])
    track.layers[0].gain *= 0.5
    with pytest.raises(ValueError, match="layers changed"):
        export_midi(score, tmp_path / "edited.mid")


def test_reference_identity_and_sprite_reuse_integrity(tmp_path):
    from tare.tools.tune.audio_io import write_wav
    from tare.tools.tune.authoring import build_file
    write_wav(tmp_path / "reference.wav", np.zeros((800, 2), dtype=np.float32), 16000)
    project = tmp_path / "source.json"
    document = {"sample_rate": 16000, "source": {"type": "fm", "options": {"duration": 0.1}},
                "reference": {"file": "reference.wav"}}
    project.write_text(json.dumps(document))
    first = build_file(project)
    path = save_bundle(first, tmp_path / "bundles")
    assert np.array_equal(load_bundle(path).arrays["reference"], first.arrays["reference"])
    write_wav(tmp_path / "reference.wav", np.ones((800, 2), dtype=np.float32) * 0.1, 16000)
    second = build_file(project)
    assert first.manifest["pcm_id"] == second.manifest["pcm_id"]
    assert first.manifest["reference"]["pcm_id"] != second.manifest["reference"]["pcm_id"]
    assert first.manifest["revision"] != second.manifest["revision"]
    sounds = {"sound": first}
    exported = export_sprite(sounds, tmp_path / "exports")
    assert export_sprite(sounds, tmp_path / "exports") == exported
    (exported / "bank.wav").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integrity"):
        export_sprite(sounds, tmp_path / "exports")


def test_midi_silent_notes_and_shared_percussion_channel(tmp_path):
    silent = Score()
    silent.track("silent").play("harp", [("C4", 0, 1, 0)])
    assert export_midi(silent, tmp_path / "silent.mid")["tracks"] == 0
    drums = Score()
    drums.track("one").play("bass_drum", [(60, 0, 1)])
    drums.track("two").play("bass_drum", [(60, 0.5, 1)])
    with pytest.raises(ValueError, match="percussion"):
        export_midi(drums, tmp_path / "overlapping-drums.mid")


def test_named_asset_bytes_change_render_identity_without_renaming(tmp_path, monkeypatch):
    from tare.tools.tune import diagnostics
    from tare.tools.tune.spec import Spoken
    from tare.tools.tune.speech import concat
    data = tmp_path / "speech" / "data"
    data.mkdir(parents=True)
    bank = data / "bank_test_bank.npz"
    bank.write_bytes(b"1")
    # Controlled asset-backed renderer; tests the capture dependency pipeline without editing shipped banks.
    def controlled_renderer(layer, sr, seed):
        frequency = int(bank.read_bytes()) * 220
        return np.sin(2 * np.pi * frequency * np.arange(800) / sr)
    monkeypatch.setattr(concat, "render_spoken", controlled_renderer)
    monkeypatch.setattr(diagnostics, "__file__", str(tmp_path / "diagnostics.py"))
    voice = Voice(spoken=[Spoken("test/bank", [(0, 1, 10)])])
    first = capture(voice, 16000)
    bank.write_bytes(b"2")
    second = capture(voice, 16000)
    assert first.manifest["source_id"] == second.manifest["source_id"]
    for key in ("assets", "render_id", "pcm_id", "revision"):
        assert first.manifest[key] != second.manifest[key]


def test_raw_pitch_retains_uncertainty_and_absolute_time():
    from tare.tools.tune.inspection import inspect_audio
    t = np.arange(8000) / 16000
    chord = sum(np.sin(2 * np.pi * f * t) for f in (261.63, 329.63, 392)) / 3
    frames = inspect_audio(chord, 16000)["fundamental"]["frames"]
    assert sum(frame["hz"] is None for frame in frames) > len(frames) * 0.8
    harmonic = 0.2 * np.sin(2 * np.pi * 220 * t) + 0.7 * np.sin(2 * np.pi * 440 * t)
    frames = inspect_audio(np.r_[np.zeros(3200), harmonic], 16000)["fundamental"]["frames"]
    assert all(frame["hz"] is None for frame in frames if frame["time"] < 0.1)
    pitched = [frame for frame in frames if frame["time"] > 0.25]
    assert all(frame["dominant_partial_hz"] == pytest.approx(440, abs=20) for frame in pitched)


def test_long_ogg_is_written_in_blocks(tmp_path):
    sf = pytest.importorskip("soundfile")
    from tare.tools.tune.exports import write_ogg
    noise = 0.3 * np.random.default_rng(0).standard_normal((30 * 48_000, 2))   # one write of this killed Python
    write_ogg(tmp_path / "long.ogg", noise, 48_000)
    assert sf.read(str(tmp_path / "long.ogg"))[0].shape == noise.shape
