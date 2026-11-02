"""The ear: the sound as text an agent reads. Synthetic signals only."""

import json

import numpy as np
from scipy.signal import get_window, resample_poly, stft
from test_reference import bank

from tare.tools.tune.cli import main
from tare.tools.tune.dsl import review
from tare.tools.tune.ear import band_energy, hear, text

SR = 16000
T = np.arange(int(0.6 * SR)) / SR


def impact():
    """A click, a 3 kHz ring and a noise burst."""
    burst = np.random.default_rng(0).standard_normal(len(T)) * np.exp(-T / 0.01)
    y = np.sin(2 * np.pi * 3000 * T) * np.exp(-T / 0.12) + burst
    y[0] = 3
    return np.concatenate([y, np.zeros(SR // 2)]) * 0.3


def heard(y, sr=SR, name="SOUND", loop=False, **options):
    return hear((name, "test", y, sr, loop), **options)


def rows(report, zoom, of="SOUND"):
    grid = next(g["rows"] for g in report["grids"] if g["zoom"] == zoom)
    start = next(i for i, r in enumerate(grid) if r.startswith(of + " "))
    out = {}
    for line in grid[start + 1:]:
        label, _, rest = line.partition("|")
        if not rest or label.strip() in ("dB", "on"):
            break
        out[int(label)] = rest.rstrip("|")
    return out


def test_an_impact_reads_as_a_ring_in_its_band_and_a_click_across_the_highs():
    report = heard(impact())
    assert text(report) == text(heard(impact()))
    whole = rows(report, "whole")
    ring = min(whole, key=lambda hz: abs(hz - 3000))
    assert "9" in whole[ring]
    order = sorted(whole)
    i = order.index(ring)
    after = slice(3, 10)  # past the click and the burst, a pure ring stays in its band
    assert set(whole[order[i - 2]][after] + whole[order[i + 2]][after]) == {"."} and "." not in whole[ring][after]
    attack = rows(report, "attack")
    assert all(max(attack[hz][:3]) == max(attack[hz]) for hz in attack if hz >= 1000)  # the click tops each high band
    assert "3000 Hz +0 dB" in next(line for line in report["lines"] if "peaks" in line).replace("2999", "3000")


def test_band_energy_is_the_stft_at_those_bins_only():
    y = np.random.default_rng(3).standard_normal(5003)
    _, _, z = stft(y, SR, nperseg=640, noverlap=480, nfft=4096)  # scipy scales by the window's sum
    expected = np.abs(z[[0, 10, 11, 2048]] * get_window("hann", 640).sum()) ** 2
    np.testing.assert_allclose(band_energy(y, SR, 640, 160, 4096, [0, 10, 11, 2048], block=7), expected, rtol=1e-9)


def test_a_sound_against_itself_or_a_noisy_resampled_copy_differs_by_little():
    same = text(heard(impact(), vs=("REF", "same", impact(), SR, False)))
    assert "SOUND louder in 0 of" in same and "quieter in 0 (" in same
    copy = resample_poly(impact(), 441, 160)
    copy = copy + np.random.default_rng(1).standard_normal(len(copy)) * 10 ** (-45 / 20) * np.abs(copy).max()
    report = heard(impact(), vs=("REF", "copy", copy, 44100, False), brief=True)
    summary = [line for g in report["grids"] for line in g["rows"] if line.startswith("SOUND louder")]
    for line in summary:
        louder, cells, quieter = [int(w) for w in line.replace("(", " ").split() if w.isdigit()][:3]
        assert louder + quieter <= 0.05 * cells, line
    assert all(not r.startswith("REF 0") for g in report["grids"] for r in g["rows"])  # brief: the DIFF only


def test_lines_name_pitch_noise_and_stereo():
    chirp = 0.5 * np.sin(2 * np.pi * np.cumsum(np.linspace(200, 300, len(T))) / SR)
    report = heard(chirp)
    pitch = next(line for line in report["lines"] if "pitch" in line)
    assert "median" in pitch and float(pitch.split("glide ")[1].split()[0]) > 3  # about 4.6 st, thirds apart
    f0 = next(r for g in report["grids"] if g["zoom"] == "whole" for r in g["rows"] if r.startswith("   f0"))
    values = [float(v) for v in f0.split()[1:] if v != "."]
    assert values == sorted(values) and values[-1] > values[0] * 1.3
    phase = 2 * np.pi * np.cumsum(250 * 2 ** (np.sin(2 * np.pi * 6 * T) / 4)) / SR  # a cry: vibrato, harmonics
    cry = heard(sum(np.sin(k * phase) / k for k in range(1, 8)) * 0.3)["lines"]
    assert any("harmonics of" in line for line in cry) and any("pitch: median" in line for line in cry)
    noise = np.random.default_rng(2).standard_normal(SR // 2) * 0.2
    assert any("noise-like" in line for line in heard(noise)["lines"])
    sine = 0.3 * np.sin(2 * np.pi * 1000 * T)
    stereo = heard(np.stack([sine * 2, sine], axis=1))
    assert any("L-R +6.0 dB" in line for line in stereo["lines"])
    assert heard(sine[: int(0.04 * SR)])["grids"]  # 40 ms still reads
    assert heard(sine[: int(0.03 * SR)])["lines"]  # and so does a click shorter than the 40 ms window


def test_zooms_follow_the_sound_loops_notes_and_long_ones():
    loop = 0.3 * np.sin(2 * np.pi * 440 * np.arange(SR) / SR)
    assert [g["zoom"] for g in heard(loop, loop=True)["grids"]][-1] == "seam"
    note = np.sin(2 * np.pi * 660 * np.arange(int(0.15 * SR)) / SR) * np.exp(-np.arange(int(0.15 * SR)) / 800)
    jingle = np.concatenate([note, np.zeros(SR // 10)] * 3 + [np.zeros(SR // 4)]) * 0.3
    marks = next(r for g in heard(jingle)["grids"] for r in g["rows"] if r.startswith("  on"))
    assert marks.count("^") == 3
    long = np.random.default_rng(3).standard_normal(8 * 8000) * np.linspace(1, 0.5, 8 * 8000) * 0.1
    report = hear(("SOUND", "long", long, 8000, False))
    assert report["grids"][-1]["step_ms"] >= 100 and any("use --at" in line for line in report["lines"])
    at = heard(impact(), at=(100, 60))
    assert [(g["zoom"], g["start_ms"], g["step_ms"]) for g in at["grids"]] == [("at", 100, 1.2)]
    full = text(heard(impact(), vs=("REF", "r", impact()[::-1].copy(), SR, False)))
    brief = text(heard(impact(), vs=("REF", "r", impact()[::-1].copy(), SR, False), brief=True))
    assert len(full) < 9000 and len(brief) < 4000


def test_the_cli_holds_a_reviewed_sound_against_its_reference(tmp_path, capsys):
    path = bank(tmp_path)
    bundle = review(path, output=tmp_path / "b", name="clash")["bundle"]
    assert main(["ear", bundle, "--brief"]) in (None, 0)
    out = capsys.readouterr().out
    assert out.startswith("REF clash.wav") and "DIFF SOUND vs REF" in out and "Not shown" in out
    main(["ear", bundle, "--vs", "none", "--json"])
    report = json.loads(capsys.readouterr().out)
    assert report["schema"] == "tune.ear/1" and report["basis"] and not any("DIFF" in r for g in report["grids"]
                                                                            for r in g["rows"])
    main(["dsl", "help", "ear", "--json"])
    assert "6 dB" in json.loads(capsys.readouterr().out)["meaning"]
