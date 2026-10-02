import numpy as np
import pytest

from creaturesynth.speech import Speaker
from creaturesynth.speech.emote import EMOTES, STYLES, emote, shout_pitch

SR = 16_000


def test_every_emote_in_every_style():
    hero = Speaker(pitch=120, tract=1.05)
    for style in STYLES:
        for kind in EMOTES:
            y = hero.emote(kind, style, 0.7, 0, SR)
            assert np.isfinite(y).all() and 0.08 < len(y) / SR < 4.0 and np.abs(y).max() > 0.5


def test_takes_vary_and_repeat():
    s = Speaker.preset("high")
    a, b = s.emote("attack", "mmo", 0.7, 0, SR), s.emote("attack", "mmo", 0.7, 1, SR)
    assert np.array_equal(a, s.emote("attack", "mmo", 0.7, 0, SR))
    assert len(a) != len(b) or not np.array_equal(a, b)


def test_shouting_register_matches_the_recordings():
    assert 300 < shout_pitch(95, 1.0, 0.85) < 380          # a 95 Hz man shouts at ~345 Hz
    assert 470 < shout_pitch(280, 1.17, 0.85) < 590        # a 280 Hz woman at ~530 Hz
    assert shout_pitch(120, 1.0, 0.0) == pytest.approx(120)


def test_barks_follow_the_speakers_voice():
    low, high = Speaker(pitch=90, tract=0.95), Speaker(pitch=300, tract=1.3)
    f_low = np.mean(emote(low, "hmm").frames["f0"])
    f_high = np.mean(emote(high, "hmm").frames["f0"])
    assert f_high > 2.5 * f_low
    assert np.mean(emote(low, "attack").frames["f0"]) > 2.5 * 90   # an effort is pitched far above speech


def test_unknown_emote_or_style():
    with pytest.raises(ValueError):
        Speaker().emote("dance")
    with pytest.raises(ValueError):
        Speaker().emote("laugh", style="opera")
