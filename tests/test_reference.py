"""Holding a sound against a reference recording: the measures, `references` in a bank, review and its tolerances.
Every signal here is synthetic or rendered by tune; no recording is committed."""

import json

import numpy as np
import pytest
from scipy.signal import resample_poly

from tare.tools.tune import Sfx, render
from tare.tools.tune.analysis import against, measures
from tare.tools.tune.audio_io import trim_tail, write_wav
from tare.tools.tune.dsl import DSLError, edit_file, load, review
from tare.tools.tune.dsl.review_data import check_spec

SR = 16000


def hit(seconds=0.8, tail=1.0):
    """A struck tone and a short noise burst, then silence: an impact as a render would make it."""
    t = np.arange(int(seconds * SR)) / SR
    noise = np.random.default_rng(0).standard_normal(len(t))
    y = np.sin(2 * np.pi * 1200 * t) * np.exp(-t / 0.08) + 0.5 * noise * np.exp(-t / 0.01)
    return np.concatenate([y, np.zeros(int(tail * SR))]) * 0.5


def recorded(y):
    """The same sound as a recording would bring it: leading silence, 44.1 kHz stereo, a noise floor near -45 dB."""
    up = np.concatenate([np.zeros(4410), resample_poly(y, 441, 160)])
    peak = np.sqrt(np.max(np.convolve(up**2, np.ones(441) / 441, "valid")))
    up = up + np.random.default_rng(1).standard_normal(len(up)) * peak * 10 ** (-45 / 20)
    return np.stack([up, up * 0.8], axis=1)


def test_a_sound_against_itself_differs_by_nothing_and_measures_repeat():
    block = against(hit(), SR, hit(), SR)
    m = block["measures"]
    assert block["status"] == "measured" and block["end_db"] == -40
    assert m["active_s"]["ratio"] == m["end_60_s"]["ratio"] == 1 and m["attack_ms"]["delta"] == 0
    assert m["centroid_hz"]["semitones"] == 0 and m["env_db"]["mean_abs_db"] == 0 and m["loud_db"]["mean_abs_db"] == 0
    assert json.dumps(block, sort_keys=True) == json.dumps(against(hit(), SR, hit(), SR), sort_keys=True)


def test_a_recording_is_measured_from_its_own_onset_peak_and_band():
    block = against(recorded(hit()), 44100, hit(), SR)
    m = block["measures"]
    assert -50 <= block["noise_floor_db"][0] <= -40 and block["noise_floor_db"][1] == -120
    assert m["end_60_s"]["status"] == "not_measurable" and m["end_60_s"]["reason"].startswith("reference still over")
    assert 0.85 <= m["active_s"]["ratio"] <= 1.15 and abs(m["centroid_hz"]["semitones"]) <= 1
    assert abs(m["attack_ms"]["delta"]) <= 2 and m["env_db"]["mean_abs_db"] <= 3  # noise fills no band over -40 dB
    louder = against(recorded(hit()), 44100, hit() * np.sin(np.arange(len(hit())) / 2) ** 2, SR)
    assert louder["measures"]["centroid_hz"]["semitones"] > 3  # a brighter sound reads brighter, not "alike"


def test_end_60_is_what_an_export_keeps_and_edge_cases_hold():
    y = render(Sfx("blade", "steel").voice("clash"), SR)
    assert measures(y, SR)["end_60_s"] == len(trim_tail(y, SR)) / SR
    assert measures(np.zeros(800), SR) == {"channels": 1, "sample_rate": SR, "clipped": 0, "status": "silent"}
    assert measures(hit(0.06, 0), SR)["status"] == "measured"
    long = np.random.default_rng(2).standard_normal(21 * 8000) * 0.1
    assert measures(long, 8000)["f0"]["status"] == "skipped"
    assert against(hit(), SR, hit(), SR)["measures"]["f0_hz"]["status"] == "measured"  # a struck tone has a pitch
    noise = np.random.default_rng(3).standard_normal(SR) * np.exp(-np.arange(SR) / 1600)
    assert against(noise, SR, noise, SR)["measures"]["f0_hz"]["status"] == "unvoiced"
    assert against(noise, SR, hit(), SR)["measures"]["f0_hz"]["status"] == "voicing_differs"


def test_a_high_ring_is_held_by_its_own_hz_and_end_60_needs_a_quiet_floor_and_the_whole_tail():
    t = np.arange(SR) / SR

    def bell(hz):
        return np.sin(2 * np.pi * hz * t) * np.exp(-t / 0.1) * 0.5

    f0 = measures(bell(3000), SR)["f0"]  # yin (60..1600 Hz) tracks 1500, where nothing sounds: the ring is the pitch
    assert f0["status"] == "ring" and abs(f0["median_hz"] - 3000) < 20 and abs(f0["tracked_hz"] - 1500) < 5
    octave = against(bell(2000), SR, bell(4000), SR)["measures"]["f0_hz"]
    assert octave["status"] == "measured" and octave["semitones"] == 12 and octave["ring"] == [True, True]
    assert against(bell(3000), SR, bell(3000), SR)["measures"]["f0_hz"]["semitones"] == 0
    assert against(bell(3000), SR, hit(), SR)["measures"]["f0_hz"]["status"] == "measured"  # a 1200 Hz tone, held
    noise = np.random.default_rng(5).standard_normal(SR) * np.exp(-np.arange(SR) / 1600)
    assert against(noise, SR, bell(3000), SR)["measures"]["f0_hz"]["status"] == "voicing_differs"
    hum = hit() + np.random.default_rng(4).standard_normal(len(hit())) * 10 ** (-63 / 20) * 0.5
    cut = hit(0.3, 0)  # the file ends 30 dB under the peak
    assert measures(hum, SR)["end_60_s"] is None and measures(cut, SR)["end_60_s"] is None
    reason = against(hum, SR, cut, SR)["measures"]["end_60_s"]["reason"]
    assert reason == "reference noise floor -60.5 dB, within 6 dB of -60; sound still over -60 dB when the file ends"


def bank(tmp_path, **extra):
    write_wav(tmp_path / "clash.wav", recorded(hit()).astype(np.float32), 44100)
    path = tmp_path / "bank.tune.json"
    path.write_text(json.dumps({"format": "tare.tools.tune.dsl", "version": 1, "context": {"sample_rate": SR},
                                "references": {"clash": "clash.wav"},
                                "sounds": {"clash": {"sfx": "blade", "style": "steel", "event": "clash", "dry": True},
                                           "confirm": {"sfx": "ui", "style": "crystal", "event": "confirm"}},
                                **extra}))
    return path


def test_references_name_existing_sounds_and_files(tmp_path):
    path = bank(tmp_path)
    assert load(path).data["references"] == {"clash": "clash.wav"}
    data = json.loads(path.read_text())
    for references, code, hint in (({"clsh": "clash.wav"}, "E_ENUM", "clash"), ({"clash": "nope.wav"}, "E_ASSET", "")):
        path.write_text(json.dumps(data | {"references": references}))
        with pytest.raises(DSLError) as error:
            load(path)
        assert error.value.code == code and hint in error.value.suggestions + [""]


def test_review_holds_only_the_sound_with_a_reference_and_its_tolerances_judge_it(tmp_path):
    path = bank(tmp_path)
    loose = {"format": "tare.tools.tune.checks", "version": 1,
             "reference": {"active_s": {"ratio": 10}, "centroid_hz": {"semitones": 48}}}
    clash = review(path, output=tmp_path / "b", name="clash", checks=loose, response="compact")
    assert set(clash["ref"]) == {"active_s", "attack_ms", "centroid_hz", "f0_hz", "env_db"}
    assert clash["checks"]["status"] == "passed" and clash["checks"]["coverage"]["reference"] == "measured"
    pitched = loose | {"reference": {"f0_hz": {"semitones": 48}}}  # the recording rings at 1200 Hz, the clash not
    row = review(path, output=tmp_path / "b", name="clash", checks=pitched)["checks"]["results"][0]
    assert row["status"] == "failed" and row["actual"][1] == "unvoiced"
    confirm = review(path, output=tmp_path / "b", name="confirm", checks=loose, response="compact")
    assert "ref" not in confirm and confirm["checks"]["coverage"]["reference"] == "absent"
    assert confirm["checks"]["status"] == "not_requested"  # no recording to hold it against: nothing failed
    plain = review(path, output=tmp_path / "b", name="confirm", response="compact")
    assert "reference" not in plain["checks"]["coverage"]  # nothing asked, nothing said
    tight = loose | {"reference": {"active_s": {"ratio": 1.0001}}}
    failed = review(path, output=tmp_path / "b", name="clash", checks=tight)
    assert failed["checks"]["status"] == "failed" and failed["checks"]["results"][0]["check"] == "reference:active_s"
    assert failed["facts"]["reference"]["file"] == "clash.wav"


def test_a_changed_reference_stales_only_its_own_sound(tmp_path):
    path = bank(tmp_path)
    clash = review(path, output=tmp_path / "b", name="clash")
    confirm = review(path, output=tmp_path / "b", name="confirm")
    write_wav(tmp_path / "clash.wav", recorded(hit() * 0.5).astype(np.float32), 44100)
    with pytest.raises(DSLError) as stale:
        edit_file(path, from_bundle=clash["bundle"], output=tmp_path / "b", set_fields={"/power": 0.6})
    assert stale.value.exit_code == 3
    assert edit_file(path, from_bundle=confirm["bundle"], output=tmp_path / "b", set_fields={"/power": 0.6})


def test_tolerances_name_a_measure_and_its_own_unit():
    base = {"format": "tare.tools.tune.checks", "version": 1}
    assert check_spec(base | {"reference": {"attack_ms": {"max_delta": 10}}})
    for wrong, code in (({"atack_ms": {"max_delta": 10}}, "E_ENUM"), ({"attack_ms": {"ratio": 2}}, "E_FIELD"),
                        ({"active_s": {"ratio": 0.5}}, "E_RANGE")):
        with pytest.raises(DSLError) as error:
            check_spec(base | {"reference": wrong})
        assert error.value.code == code, wrong
