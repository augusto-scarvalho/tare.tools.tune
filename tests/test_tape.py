"""A bark that moves little plays its own (third-party, CC0) recording like tape, when asked (TARE_TOOLS_TUNE_TAPE=1).
The recordings never ship: these skip until python tools/build_barks.py --download output/barks --audio."""
from dataclasses import replace

import numpy as np
import pytest

from tare.tools.tune.spec import Vocoded, Voice
from tare.tools.tune.speech import Speaker
from tare.tools.tune.speech.emote import emote
from tare.tools.tune.speech.vocoder import (
    AUDIO,
    AUDIO_SR,
    TAPE_ENV,
    _recordings,
    recording,
    render_vocoded,
    tape,
    template,
)

pytestmark = pytest.mark.skipif(not AUDIO.exists(), reason="no recordings: tools/build_barks.py --download DIR --audio")


@pytest.fixture(autouse=True)
def tape_on(monkeypatch):
    monkeypatch.setenv(TAPE_ENV, "1")
    _recordings.cache_clear()
    yield
    _recordings.cache_clear()


def test_a_bark_that_moves_little_plays_its_recording():
    v = emote(Speaker(pitch=115, tract=1.02), "attack", "kiai", 0.75, 0)
    x = recording(v.clip)
    assert tape(v) and abs(len(render_vocoded(v, AUDIO_SR, 1)) - len(x) / v.pitch) < 3   # faster: shorter, higher
    still = render_vocoded(replace(v, pitch=1.0, warp=1.0, stretch=1.0, tilt=0.0), AUDIO_SR, 1)
    assert np.allclose(still, x / np.abs(x).max(), atol=1e-6)                             # the recording itself
    assert not tape(replace(v, breath=1.0)) and not tape(replace(v, rough=0.5))           # whispers, hoarse: vocoder


def test_on_tape_a_bark_lasts_its_recording_over_the_pitch():
    v = Voice(vocoded=[Vocoded("laugh/male/536811", 0.1, pitch=1.2, warp=1.1, stretch=0.9, breath=-0.2)], seed=3)
    assert v.duration == pytest.approx(0.1 + template("laugh/male/536811").duration / 1.2)
    short = Voice(vocoded=[Vocoded("laugh/male/536811", pitch=1.2, warp=1.1, stretch=0.5)])   # too short for tape
    assert short.duration == pytest.approx(template("laugh/male/536811").duration * 0.5)
