"""The march cue keeps to the arrangement it was written from, and spiccato to the strokes it was measured on."""
import numpy as np

from tare.tools.tune.instruments import INSTRUMENTS
from tare.tools.tune.music import Cue
from tare.tools.tune.render import render
from tare.tools.tune.score import Note, hz
from tare.tools.tune.spec import Voice


def test_arrangement_reads_lines_leaps_entries_and_contrast():
    from tare.tools.tune.score import Score, arrangement

    layout = arrangement({"tune": [(0, 60), (1, 62), (2, 64), (3, 72)], "chords": [(16, 48), (16, 52), (16, 55)],
                          "drum": [(b, None) for b in range(16, 32)]})
    assert layout["notes_per_attack"] == 7 / 5 and layout["leaps_share"] == 0.33 and layout["steps_share"] == 0.67
    assert layout["parts_by_block"] == [1, 2] and layout["notes_per_bar_by_block"] == [1.0, 4.8]
    assert layout["parts_growth"] == 2 and layout["density_ratio"] == 4.8 and layout["doubling"] == 1
    score = Score(bpm=120, sr=16_000)
    score.track("a").play("harp", [("C4", 0, 1), (["C4", "E4"], 4, 1)])
    score.track("d").play("snare", [(60, 0, 1)])
    assert score.arrangement(block_bars=1) | {"parts_by_block": 0} == arrangement(
        {"a": [(0, 60.0), (4, 60.0), (4, 64.0)], "d": [(0, None)]}, 4, 1) | {"parts_by_block": 0}

def test_march_is_one_line_per_part_entering_in_stages_with_a_quiet_terrace():
    for seed in (1, 2, 5):
        score = Cue("march", seed=seed, sr=16_000).score
        layout = score.arrangement()
        assert layout["notes_per_attack"] == 1 and layout["leaps_share"] < 0.1      # lines, moving by step
        parts = layout["parts_by_block"]
        assert parts[0] < parts[3] < parts[8] and min(parts) == parts[6] and layout["parts_growth"] >= 3
        assert layout["density_ratio"] >= 4
        assert max(score.tracks.values(), key=lambda track: len(track.events)).name == "snare"
        assert not score.clashes()


def test_spiccato_speaks_fast_and_starts_brighter_than_it_rings():
    def centroid(x):
        spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
        return float((np.fft.rfftfreq(len(x), 1 / 48_000) * spectrum).sum() / spectrum.sum())

    # the basses keep the least of the bite: their stroke is only a little brighter than their ring
    for note, slowest, brighter in (("A4", 0.1, 1.4), ("D3", 0.08, 1.4), ("D2", 0.1, 1.05)):
        layers = INSTRUMENTS["spiccato"](Note(0.0, 0.2, hz(note), 0.85, 7))
        y = render(Voice(syllables=layers, seed=1), 48_000).astype(float)
        step = 96
        env = np.sqrt(np.mean(y[: len(y) // step * step].reshape(-1, step) ** 2, axis=1))
        env = np.convolve(env, np.ones(5) / 5, mode="same")
        start, half = int(np.argmax(env > env.max() * 10 ** -1.5)), int(np.argmax(env > env.max() / 2))
        peak = int(np.argmax(env))
        assert (half - start) * step / 48_000 < slowest
        assert centroid(y[start * step: start * step + 1440]) > brighter * centroid(y[peak * step: peak * step + 2400])
        assert len(y) / 48_000 > 0.3                         # the ring outlasts the written eighth


def test_a_large_cue_is_read_from_its_notes_without_rendering(tmp_path, capsys):
    import json

    from tare.tools.tune.cli import main

    path = tmp_path / "bank.tune.json"
    path.write_text(json.dumps({"format": "tare.tools.tune.dsl", "version": 1, "context": {"sample_rate": 48000},
                                "sounds": {"march": {"music": "march", "seed": 2},
                                           "coin": {"sfx": "ui", "event": "confirm", "dry": True}}}))
    assert main(["dsl", "check", str(path), "--name", "march", "--layout", "--json"]) == 0
    read = json.loads(capsys.readouterr().out)
    assert read["mode"] == "notes only; no synthesis" and read["rubs"] == {"chord": 0, "line": 0, "first": []}
    assert read["arrangement"]["notes_per_attack"] == 1 and read["arrangement"]["parts_growth"] == 4
    assert main(["dsl", "check", str(path), "--name", "coin", "--layout", "--json"]) == 2
    assert json.loads(capsys.readouterr().err)["code"] == "E_CAPABILITY"
