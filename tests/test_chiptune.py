"""8-bit music by hand: a console channel as an instrument, in Python and in the DSL, and a score read by numbers."""
import json
from pathlib import Path

import pytest
from test_dsl_loading import project

from tare.tools.tune.dsl import DSLError, review
from tare.tools.tune.instruments import chip_voice
from tare.tools.tune.patterns import parse_pattern
from tare.tools.tune.score import Note, Score, chord, hz

EXAMPLE = Path(__file__).parents[1] / "examples" / "dsl-chiptune.tune.json"


def test_a_chord_is_one_arpeggio_and_other_instruments_keep_one_layer_per_note():
    score = Score(bpm=120, hall=0, sr=16000)
    chip = score.track("chip", send=0).play(chip_voice(duty=50), [(chord("C", 4), 0, 2)])
    harp = score.track("harp", send=0).play("harp", [(chord("C", 4), 0, 2)])
    assert len(chip.layers) == 1 and len(chip.events) == 3 and len(harp.layers) == 3
    assert [e["layers"] for e in chip.events] == [[0], [], []]
    heard = [f for _, f in chip.layers[0].pitch]
    cycle = [round(hz(n), 3) for n in ("C4", "E4", "G4")]
    assert heard[:6] == [cycle[0], cycle[0], cycle[1], cycle[1], cycle[2], cycle[2]]
    steps = (len(chip.layers[0].pitch) - 2) / 2 + 1                 # one per frame of the note
    assert steps == pytest.approx(60 * chip.layers[0].dur, abs=1)
    assert score.render().any()


def test_fade_slide_and_the_channels_limits():
    note = Note(0.0, 0.5, 440.0, 0.8, 1)
    faded = chip_voice(fade=True)(note)[0]
    assert faded.amp[0][1] == 1 and faded.amp[-1][1] == 0 and len({a for _, a in faded.amp}) == 16
    slid = chip_voice(slide=-2)(note)[0]
    assert slid.pitch[0][1] == pytest.approx(440 * 2 ** (-2 / 12), abs=0.01) and slid.pitch[-1][1] == 440
    assert chip_voice()(note)[0].pitch == [(0.0, 440.0), (1.0, 440.0)]
    assert chip_voice()(note)[0].gain == 12 / 15                     # velocity lands on one of 16 levels
    assert chip_voice("triangle")(note)[0].brightness == 0
    with pytest.raises(ValueError, match="duty"):
        chip_voice(duty=33)


def test_a_miscounted_bar_is_named():
    with pytest.raises(ValueError, match=r"bar 2 has 3 steps, not 8 \(4 beats x 2 steps\)"):
        parse_pattern("C4 - . . E4 - . . | C4 - . | G4", steps_per_beat=2)


def test_the_example_reviews_with_a_level_per_bar_and_per_track(tmp_path):
    facts = review(EXAMPLE, name="overworld", output=tmp_path, response="compact")["facts"]
    assert len(facts["bars_db"]) == 4 and max(facts["bars_db"]) - min(facts["bars_db"]) <= 2
    levels = {track["name"]: track["level_db"] for track in facts["tracks"]}
    assert levels["pulse1"] == max(levels.values()) == 0 and levels["pulse2"] < 0
    assert "rubs" not in facts


def test_review_counts_rubs_and_the_dsl_checks_the_channel(tmp_path):
    def score(instrument):
        return {"score": {"hall": 0, "bpm": 120, "tracks": [
            {"name": "a", "instrument": instrument, "notes": {"notes": [["C4", 0, 4]]}},
            {"name": "b", "instrument": {"chip_voice": "triangle"}, "notes": {"notes": [["C#5", 0, 4]]}}]}}

    path = tmp_path / "rub.json"
    path.write_text(json.dumps(project(score({"chip_voice": "pulse", "duty": 12.5, "fade": True}))))
    rubs = review(path, name="a", output=tmp_path / "out", response="compact")["facts"]["rubs"]
    assert rubs["chord"] == 1 and rubs["line"] == 0 and rubs["first"][0]["bar"] == 1
    path.write_text(json.dumps(project(score({"chip_voice": "pulse", "duty": 33}))))
    with pytest.raises(DSLError) as error:
        review(path, name="a", output=tmp_path / "out", response="compact")
    assert error.value.code == "E_ENUM" and error.value.pointer.endswith("/instrument/duty")
