import numpy as np
import pytest

from creaturesynth.render import render
from creaturesynth.spec import Spoken, Voice
from creaturesynth.speech import Speaker, natural, speaker_from
from creaturesynth.speech.concat import accent_pt, bank, banks, closest, fit_durations, select

SR = 16_000


def test_banks_ship_numbers_only():
    assert {"pt/alex", "pt/dora"} <= set(banks("pt"))
    b = bank("pt/alex")
    assert b.env.shape == (len(b.f0), 32) and len(b.ph) > 5000 and "Kokoro" in b.meta["teacher"]
    assert closest("pt", 1.0) == "pt/alex" and closest("pt", 1.2) == "pt/dora"
    with pytest.raises(ValueError):
        bank("xx/nobody")


def test_natural_voice_is_a_portable_deterministic_spec():
    sp = Speaker(pitch=110, tract=1.02, engine="natural")
    v = sp.voice("Você viu o dragão perto da montanha?", "pt")
    layer = v.spoken[0]
    assert not v.speech and layer.bank == "pt/alex" and len(layer.f0) == sum(n for _, _, n in layer.pieces)
    w = Voice.from_json(v.to_json())
    assert w == v and np.array_equal(render(w, SR), render(v, SR))
    y = render(v, SR)
    assert np.isfinite(y).all() and 1.2 < len(y) / SR < 4.0 and np.array_equal(y, sp.render(
        "Você viu o dragão perto da montanha?", "pt", SR))


def test_natural_voice_follows_the_speaker():
    low = Speaker(pitch=95, tract=0.95, engine="natural").spoken("Bom dia!", "pt")
    high = Speaker(pitch=260, tract=1.3, engine="natural").spoken("Bom dia!", "pt")
    assert low.bank == "pt/alex" and high.bank == "pt/dora" and high.warp > 1.05 > 0.98 > low.warp
    assert np.median([f for f in high.f0 if f > 0]) > 2 * np.median([f for f in low.f0 if f > 0])
    slow = Speaker(engine="natural", rate=0.7).spoken("Bom dia, viajante!", "pt")
    fast = Speaker(engine="natural", rate=1.3).spoken("Bom dia, viajante!", "pt")
    assert slow.duration > 1.4 * fast.duration
    assert Speaker(engine="natural", whisper=1.0).spoken("Oi", "pt").breath == 1.0


def test_babble_styles_work_on_the_natural_engine():
    sp = Speaker(engine="natural")
    a, b = sp.spoken("Olá, viajante!", "pt", "gibberish"), sp.spoken("Olá, viajante!", "pt")
    assert a.phonemes != b.phonemes and sp.spoken("Olá, viajante!", "pt", "animalese").duration < b.duration


def test_voice_names():
    assert speaker_from("natural").engine == "natural" and speaker_from("natural:f").tract > 1.1
    assert speaker_from("natural:pt/dora") == natural(bank="pt/dora")
    assert speaker_from("kokoro:pf_dora").bank == "pt/dora" and speaker_from("kokoro:am_adam").tract == 1.0
    assert speaker_from({"preset": "deep", "engine": "natural"}).engine == "natural"


def test_no_bank_for_a_language_falls_back_to_formants():
    sp = Speaker(engine="natural")
    if not banks("en"):
        assert not sp.natural("en") and sp.voice("Hello there!", "en").speech


def test_teacher_accent_rules():
    def run(seq):
        return [p[0] for p in accent_pt([[s, 0.08, st, fl] for s, st, fl in seq])]
    # "a casa": the article keeps [a], the final unstressed a reduces
    assert run([("6", 0, 3), ("k", 0, 1), ("a", 2, 0), ("z", 0, 0), ("6", 0, 2)]) == ["a", "k", "a", "z", "6"]
    # "bem" -> [bẽj] + velar nasal
    assert run([("b", 0, 1), ("e~", 2, 0), ("j~", 0, 2)]) == ["b", "e", "j", "N"]
    # "mar azul": a coda r before a vowel stays; "porta": a tap and a short schwa before the consonant
    assert run([("p", 0, 1), ("O", 2, 0), ("R", 0, 0), ("t", 0, 0), ("6", 0, 2)]) == ["p", "O", "r", "@", "t", "6"]


def test_duration_model_learns_stress_and_final_lengthening():
    phones = []
    for u in range(30):
        phones += [["_", 0, 2, 0, u, 0], ["t", 2, 14, 0, u, 1], ["a", 14, 26 + 10 * (u % 2), 2, u, 0],
                   ["t", 0, 12, 0, u, 0], ["6", 0, 14, 0, u, 2], ["_", 0, 40, 0, u, 0]]
    model = fit_durations(phones)
    assert model["fit"][0] > 0 and len(model["coef"]) == len(model["names"]) + 1


def test_selection_prefers_contiguous_pieces():
    b = bank("pt/alex")
    utt = [p for p in b.ph if p[4] == 3]
    seq = [[p[0], (p[2] - p[1]) * 0.005, p[3], p[5]] for p in utt]
    units = select(b, seq)
    joins = sum(units[i - 1][1] != units[i][0] for i in range(1, len(units)))
    assert joins <= 2                      # a sentence of the bank is found almost whole
    assert isinstance(Spoken("pt/alex", [(0, 4, 4)]).duration, float)
