# Frozen renderer baseline

`legacy.npz` contains float32 outputs saved **before** the authoring renderer refactor on October 31, 2026. `voices.json` stores their Voice specs; `environment.json` stores the original environment and source hashes. The Score recipe is retained in `tests/test_authoring.py::legacy_score`.

The cases cover a mammal attack, steel blade clash, short rain loop, English formant speech, a Generation 1 chip cry, and a stereo three-beat Score with two instruments, hall, echo, and loop folding. Tests preserve channels, lengths, dtype, default samples, seeds, and serialization. Capture-on/off equality is exact; platform comparisons allow small numerical tolerances. Native comparison uses the mammal, blade, and rain fixtures, since formant/chip and whole Score rendering are outside the native Voice subset.

Do not regenerate these fixtures from the current renderer to make a failing test pass. A deliberate future behavior change needs an independently reviewed compatibility decision and separate new expectations. Diagnostic schema, Voice feature versions, and renderer behavior are distinct contracts.

**`legacy-2` (November 5, 2026).** A Score is normalized to its true peak (4x oversampled) instead of its sample peak,
so music no longer passes -1 dBTP between samples, where encoders clip (82 of the 96 cues did, up to +0.17 dBTP). The
baseline stays as it was: the Score case must equal its frozen output times one gain (at most 1.2 dB lower, on chip
music). Voice rendering is unchanged.
