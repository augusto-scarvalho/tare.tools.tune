import numpy as np
import pytest

from tare.tools.tune import Sfx
from tare.tools.tune.audio_io import write_wav
from tare.tools.tune.instruments import INSTRUMENTS
from tare.tools.tune.score import Note, Score, chord, hz, midi, scale

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


def test_echo_bounces_between_the_ears():
    s = Score(sr=SR, hall=0.0, echo=(0.2, 0.5, 3000.0))
    s.track("t", pan=0.0, send=0.0, echo=1.0).play("xylophone", [("C6", 0, 0.25)])
    y = s.render()
    a, b = int(0.2 * SR), int(0.4 * SR)
    left, right = np.abs(y[a + 50:a + 800, 0]).max(), np.abs(y[a + 50:a + 800, 1]).max()
    assert len(y) > 0.8 * SR and abs(left - right) > 0.01            # the first repeat is on one side
    assert np.abs(y[b + 50:b + 800]).max() > 1e-3                     # and a second one follows


def test_damped_note_stops():
    from tare.tools.tune.layers import render_modal
    from tare.tools.tune.spec import Modal
    m = Modal(0.0, 1.0, [(220.0, 4.0, 1.0)], [(0.0, 1.0, 0.0)], damp=0.3)
    y = render_modal(m, SR, 1)
    assert np.abs(y[int(0.45 * SR):]).max() < 1e-3 < np.abs(y[int(0.2 * SR):int(0.3 * SR)]).max()


def test_a_body_bends_and_the_koto_trembles():
    from tare.tools.tune import Voice, render
    from tare.tools.tune.analysis import yin
    from tare.tools.tune.spec import Modal
    sr = 44100
    m = Modal(0.0, 1.5, [(330.0, 3.0, 1.0), (660.0, 2.0, 0.5)], bend=[(0, 0), (0.15, 0), (0.3, 2), (1, 2)])
    f, _ = yin(render(Voice(modal=[m]), sr).astype(float), sr, 200, 600)
    assert abs(np.median(f[20:40]) - 330) < 3 and abs(np.median(f[150:250]) - 330 * 2 ** (2 / 12)) < 3   # +2 semitones
    long = INSTRUMENTS["koto"](Note(0.0, 2.0, 330.0, 0.5, 5))[0]
    f, _ = yin(render(Voice(modal=[long]), sr).astype(float), sr, 250, 450, frame=0.04, hop=0.005)
    c = 1200 * np.log2(f[f > 0][80:300] / 330)
    assert 18 < (np.percentile(c, 95) - np.percentile(c, 5)) / 2 < 40          # yuri: ~28 cents at mf (đàn tranh)
    assert not INSTRUMENTS["koto"](Note(0.0, 0.3, 330.0, 0.5, 6))[0].bend       # a short note just rings
    shaku = INSTRUMENTS["shakuhachi"](Note(0.0, 2.0, 587.0, 0.8, 2))
    pitch = shaku[0].pitch
    assert pitch[0][1] < 587 < pitch[-1][1]                                     # in from below, out lifting
    tone = [x for x in shaku if not hasattr(x, "filter")]
    assert len(tone) == 8 and tone[3].pitch[5][1] == round(4 * pitch[5][1], 2)  # harmonics locked to one curve
    assert len(shaku) == 10                                                    # the breath, and the muraiki
    y = render(Voice(syllables=tone), sr).astype(float)[int(0.8 * sr):int(0.8 * sr) + 8192]
    sp = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    fr = np.fft.rfftfreq(len(y), 1 / sr)
    h1, h2 = (sp[np.abs(fr - k * 587) < 30].max() for k in (1, 2))
    assert -21 < 20 * np.log10(h2 / h1) < -11                                   # recorded: -16 at C5
