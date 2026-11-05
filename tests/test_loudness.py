import numpy as np
import pytest

from tare.tools.tune.loudness import integrated_lufs, k_weighting, true_peak_db


def sine(db, seconds, sr, hz=1000.0):
    return 10 ** (db / 20) * np.sin(2 * np.pi * hz * np.arange(int(seconds * sr)) / sr)


def test_k_weighting_is_the_standards_table_at_48khz():
    table = [[1.53512485958697, -2.69169618940638, 1.19839281085285, 1, -1.69065929318241, 0.73248077421585],
             [1, -2, 1, 1, -1.99004745483398, 0.99007225036621]]
    np.testing.assert_allclose(k_weighting(48_000), table, atol=1e-12)


@pytest.mark.parametrize("sr", [48_000, 16_000])
def test_reference_levels(sr):
    assert integrated_lufs(sine(0, 5, sr, 997), sr) == pytest.approx(-3.01, abs=0.05)    # BS.1770: one channel
    tone = np.stack([sine(-23, 10, sr)] * 2, axis=1)                                     # EBU Tech 3341, case 1
    assert integrated_lufs(tone, sr) == pytest.approx(-23.0, abs=0.1)
    quiet, loud = sine(-36, 10, sr), sine(-23, 30, sr)                                    # case 3: the gate drops
    gated = np.concatenate([quiet, loud, quiet])                                          # the quiet ends
    assert integrated_lufs(np.stack([gated] * 2, axis=1), sr) == pytest.approx(-23.0, abs=0.1)


def test_short_or_silent_sounds_have_no_loudness_and_peaks_count_between_samples():
    assert integrated_lufs(sine(0, 0.3, 48_000), 48_000) is None
    assert integrated_lufs(np.zeros(48_000), 48_000) is None
    between = np.sin(2 * np.pi * 12_000 * np.arange(4800) / 48_000 + np.pi / 4)   # samples at 0.707, wave at 1
    assert 20 * np.log10(np.abs(between).max()) == pytest.approx(-3.01, abs=0.01)
    assert true_peak_db(between) == pytest.approx(0.0, abs=0.2)
