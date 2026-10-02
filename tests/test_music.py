import numpy as np
import pytest

from tare.tools.tune.music import CALM, CUES, Cue, Key, Rand, melody, voicing

SR = 16_000


@pytest.mark.parametrize("style", ["orchestral", "chip"])
def test_every_cue_renders(style):
    for kind in CUES:
        c = Cue(kind, style, seed=1, sr=SR)
        y = c.render()
        assert y.ndim == 2 and y.shape[1] == 2 and np.isfinite(y).all() and np.abs(y).max() <= 0.9
        if c.length:
            assert len(y) == int(round(c.length * SR))     # a loop is exactly its length
        else:
            assert 1.0 < len(y) / SR < 20.0


def test_cues_are_seeded():
    a = Cue("victory", seed=4, sr=SR).render()
    assert np.array_equal(a, Cue("victory", seed=4, sr=SR).render())
    assert not np.array_equal(a[: min(len(a), 20_000)], Cue("victory", seed=5, sr=SR).render()[:20_000])


def test_unknown_cue_or_style():
    with pytest.raises(ValueError):
        Cue("disco")
    with pytest.raises(ValueError):
        Cue("town", style="kazoo")


def test_keys_and_harmonic_minor():
    assert Key(57, "minor").note(0) == 57 and Key(57, "minor").note(7) == 69
    assert Key(57, "minor").note(6) == 67 and Key(57, "minor").note(6, chord=4) == 68   # G#, the leading tone on V


def test_melody_stays_in_key_and_lands_on_the_tonic():
    key = Key(60, "major")
    notes = melody(Rand(3, "t"), key, [0, 3, 4, 0, 5, 3, 4, 0], CALM)
    assert all((n - 60) % 12 in key.steps for n, _, _ in notes)
    assert (notes[-1][0] - 60) % 12 == 0
    beats = [b for _, b, _ in notes]
    assert beats == sorted(beats) and max(b + ln for _, b, ln in notes) <= 32


def test_voicing_moves_little():
    key = Key(60, "major")
    c = voicing(key, 0, None, 52, 72)
    f = voicing(key, 3, c, 52, 72)
    assert sorted(n % 12 for n in f) == [0, 5, 9] and sum(abs(a - b) for a, b in zip(c, f, strict=True)) <= 4


def test_colour_cues_in_16bit_style():
    from tare.tools.tune.music import COLOR_CUES
    for kind in COLOR_CUES + ("town",):
        c = Cue(kind, "snes", seed=2, sr=SR)
        y = c.render()
        assert y.shape[1] == 2 and len(y) == int(round(c.length * SR)) and np.isfinite(y).all()
        assert c.score.echo and c.score.lowpass


def test_colour_melody_uses_chord_and_colour_tones():
    from tare.tools.tune.music import COLOR, PALETTES, color_melody
    from tare.tools.tune.score import SCALES
    tonic, chords = 62, PALETTES["lydian"][0] * 2
    mel = color_melody(Rand(1, "m"), tonic, "lydian", chords, CALM)
    for n, b, _ in mel:
        step, q = chords[int(b // 4)]
        allowed = {(tonic + i) % 12 for i in SCALES["lydian"]} | {(tonic + step + i) % 12 for i in COLOR[q]}
        assert n % 12 in allowed or (n % 12) in {(tonic + step + 14) % 12, (tonic + step + 21) % 12}
    assert len({n for n, _, _ in mel}) >= 6                  # it moves


def test_planing_keeps_the_shape():
    from tare.tools.tune.music import open_voicing, planed
    v = open_voicing(60, (0, "maj9"))
    w = planed(v, 60, 62)
    assert np.diff(v).tolist() == np.diff(w).tolist() and {(n - 62) % 12 for n in w} <= {0, 2, 4, 7, 11}
