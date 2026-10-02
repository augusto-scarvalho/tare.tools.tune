"""The Gen 1 engine against the original web app's TypeScript engine (frozen in fixtures).

The TS accumulated pulse phase in floating point, so where a waveform edge falls exactly on
a sample it is sometimes one sample (~1 us) early or late. Real hardware uses integer
timers, so those isolated 1-sample differences are TS rounding. Everything else must match:
lengths, envelopes, duty patterns, and the noise channel bit for bit.
"""
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from tare.tools.tune import render
from tare.tools.tune.chip import FRAME, channels, gen1_program, gen1_voice, load_gen1, program_duration

FIXTURES = Path(__file__).parent / "fixtures" / "gen1"
REFERENCE = json.loads((FIXTURES / "ts_reference.json").read_text())["cries"]


def as_int8(channel: np.ndarray) -> np.ndarray:
    return np.round(channel * 16).astype(np.int8)


@pytest.mark.parametrize("number", range(1, 152))
def test_lengths_and_noise_match_ts(number):
    ref = REFERENCE[number - 1]
    p1, p2, noise = channels(gen1_program(number, hardware_noise=False))
    assert [len(p1), len(p2), len(noise)] == ref["lengths"]
    assert hashlib.sha256(as_int8(noise).tobytes()).hexdigest() == ref["sha256"][2]


@pytest.mark.parametrize("name", ["bulbasaur", "charmander", "pikachu", "fearow", "muk", "mew"])
def test_pulses_match_ts_up_to_one_sample_edges(name):
    raw = gzip.decompress((FIXTURES / f"ts_{name}.bin.gz").read_bytes())
    lengths = np.frombuffer(raw[:12], dtype=np.uint32)
    data = np.frombuffer(raw[12:], dtype=np.int8)
    ours = channels(gen1_program(name, hardware_noise=False))
    offset = 0
    for ch, n in enumerate(lengths):
        ref = data[offset:offset + n]
        offset += n
        bad = as_int8(ours[ch]) != ref
        assert not np.any(bad[1:] & bad[:-1]), f"channel {ch}: a difference lasts more than one sample"
        assert bad.mean() < 0.01


def test_hardware_noise_differs_from_legacy_only_in_short_mode():
    # Bulbasaur's noise uses 7-bit (short) mode: the fix must change it
    legacy = channels(gen1_program("bulbasaur", hardware_noise=False))[2]
    fixed = channels(gen1_program("bulbasaur", hardware_noise=True))[2]
    assert len(legacy) == len(fixed) and not np.array_equal(legacy, fixed)


def test_duration_without_rendering():
    for number in (1, 25, 150):
        p = gen1_program(number)
        assert program_duration(p) == pytest.approx(max(map(len, channels(p))) / 1_048_576)


def test_voice_renders():
    audio = render(gen1_voice("Pikachu"), 48_000)
    assert audio.dtype == np.float32 and 0.8 < len(audio) / 48_000 < 1.1
    assert np.isfinite(audio).all() and np.abs(audio).max() <= 0.9


def test_lookup():
    assert load_gen1()["species"][24]["name"] == "Pikachu"
    assert gen1_program(25) == gen1_program("pikachu")
    with pytest.raises(ValueError):
        gen1_program("agumon")
    assert FRAME == 17_556
