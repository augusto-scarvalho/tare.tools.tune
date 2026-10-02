import numpy as np
import pytest

from creaturesynth import Sfx
from creaturesynth.audio_io import write_wav
from creaturesynth.instruments import INSTRUMENTS
from creaturesynth.score import Note, Score, chord, hz, midi, scale

SR = 16_000


def test_note_names():
    assert midi("A4") == 69 and midi("C4") == 60 and midi("C#5") == 73 and midi("Eb3") == 51
    assert hz("A4") == pytest.approx(440.0) and hz(57) == pytest.approx(220.0)
    with pytest.raises(ValueError):
        midi("H2")


def test_chords_and_scales():
    assert chord("Am", 3) == [57, 60, 64]
    assert chord("G7") == [67, 71, 74, 77]
    assert scale("A", "minor pentatonic", 3) == [57, 60, 62, 64, 67]
    with pytest.raises(ValueError):
        chord("Cweird")


def test_beats_and_bars():
    s = Score(bpm=120)
    assert s.beats(2) == pytest.approx(1.0) and s.bar(1) == pytest.approx(2.0) and s.bar(1, 1) == pytest.approx(2.5)


def test_render_is_stereo_panned_and_deterministic():
    def build():
        s = Score(bpm=120, sr=SR, hall=0.5)
        s.track("left", pan=-1.0, send=0.0).play("marimba", [("C4", 0, 1), ("E4", 1, 1)])
        s.track("right", pan=1.0, send=0.0).play("glockenspiel", [("G5", 0, 1)])
        return s.render()
    a, b = build(), build()
    assert a.ndim == 2 and a.shape[1] == 2 and a.dtype == np.float32
    assert np.array_equal(a, b)
    assert np.max(np.abs(a)) == pytest.approx(0.89, abs=1e-3)


def test_pan_law_puts_a_hard_left_track_on_the_left():
    s = Score(sr=SR, hall=0.0)
    s.track("l", pan=-1.0, send=0.0).play("harp", [("A3", 0, 1)])
    y = s.render()
    assert np.max(np.abs(y[:, 1])) < 1e-6 < np.max(np.abs(y[:, 0]))


def test_loop_wraps_the_tail_to_exact_length():
    s = Score(bpm=120, sr=SR, hall=1.0)
    s.track("t", send=0.3).play("harp", [("C4", 3, 1)])   # rings past the end of the 2 s loop
    y = s.render(loop=s.bar(1))
    assert len(y) == int(round(2.0 * SR))
    assert np.max(np.abs(y[: SR // 4])) > 0.01             # the ring and the hall came back around


def test_placed_sounds_and_chords():
    s = Score(bpm=100, sr=SR)
    s.track("pad").play("marimba", [(["C4", "E4", "G4"], 0, 2), (chord("F"), 2, 2)])
    s.add(Sfx("blade", "steel").render("clash", 0, SR), at=0.5, pan=0.4, send=0.2)
    y = s.render()
    assert y.shape[1] == 2 and len(y) > SR


def test_every_instrument_renders_a_note(tmp_path):
    s = Score(bpm=120, sr=SR, hall=0.3)
    for i, name in enumerate(INSTRUMENTS):
        s.track(name, pan=-0.8 + 1.6 * i / len(INSTRUMENTS)).play(name, [("A3", 0.5 * i, 0.5, 0.7)])
    y = s.render()
    assert np.isfinite(y).all() and write_wav(tmp_path / "all.wav", y, SR).stat().st_size > 1000


def test_instruments_are_seeded_per_note():
    a = INSTRUMENTS["crash"](Note(0.0, 1.0, 440.0, 0.8, 1))
    b = INSTRUMENTS["crash"](Note(0.0, 1.0, 440.0, 0.8, 2))
    assert a[0].modes != b[0].modes and a == INSTRUMENTS["crash"](Note(0.0, 1.0, 440.0, 0.8, 1))


def test_empty_score_refuses():
    with pytest.raises(ValueError):
        Score().render()
