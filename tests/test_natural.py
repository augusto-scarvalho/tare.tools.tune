import numpy as np
import pytest

from tare.tools.tune.render import render
from tare.tools.tune.spec import Spoken, Voice
from tare.tools.tune.speech import Speaker, natural, speaker_from
from tare.tools.tune.speech.concat import accent_pt, bank, banks, closest, fit_durations, select

SR = 16_000


def test_banks_ship_numbers_only():
    assert {"pt/alex", "pt/dora"} <= set(banks("pt"))
    b = bank("pt/alex")
    assert b.env.shape == (len(b.f0), 64) and len(b.ph) > 30000 and "Kokoro" in b.meta["teacher"]
    assert closest("pt", 1.0) == "pt/alex" and closest("pt", 1.2) == "pt/dora"
    with pytest.raises(ValueError):
        bank("xx/nobody")


def test_bank_labels_sit_on_the_sounds():
    """The teacher's sound runs ~60 ms ahead of its duration grid; the builder realigns. A labelled [s] must hiss
    and a labelled vowel must outshine a stop closure."""
    from tare.tools.tune.speech.vocoder import band_freqs
    for name in ("pt/alex", "pt/dora"):
        b = bank(name)
        bf = band_freqs(b.env.shape[1])
        hiss = b.env[:, (bf > 4000) & (bf < 11000)].mean(1) - b.env[:, bf < 1200].mean(1)
        level = b.env[:, (bf > 200) & (bf < 4000)].mean(1)

        def mean(feature, syms, b=b):
            return np.mean([feature[p[1]:p[2]].mean() for p in b.ph if p[0] in syms and p[2] > p[1]])
        assert mean(hiss, {"s", "S"}) > 8 and mean(level, {"a", "E", "O"}) - mean(level, {"p", "t", "k"}) > 20
        # the teacher gives its stress marks time (the stressed vowel's start): never a pause inside a word, and
        # a pause inside a sentence is a silence, not a comma read through
        inner = [k for k in range(1, len(b.ph) - 1) if b.ph[k][0] == "_" and b.ph[k - 1][4] == b.ph[k + 1][4]]
        assert all(b.ph[k - 1][5] & 2 or b.ph[k + 1][5] & 1 for k in inner)
        assert np.mean([b.ph_voiced[k] for k in inner]) < 0.3


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


def _select_reference(b, seq, pitch=None):
    """select() as it was first written, one candidate at a time: the vectorised one must choose exactly the same
    pieces (and a port to another language can be checked against this)."""
    from tare.tools.tune.speech.concat import (
        F0_JOIN,
        F0_TARGET,
        FRAME,
        JOIN,
        JOIN_CLASS,
        N_BEST,
        SONORANT,
        VOICING,
        VOWEL,
        klass,
        substitution,
    )
    n = len(seq)
    pitch = pitch or [0.0] * n
    cands, costs = [], []
    for i in range(n - 1):
        a, c = seq[i], seq[i + 1]
        left = b.matches(a[0])
        opts = []
        for cost_a, k in left:
            if k + 1 >= len(b.ph) or b.ph[k + 1][4] != b.ph[k][4]:
                continue
            cost_c = substitution(c[0], b.ph[k + 1][0])
            if not np.isfinite(cost_c):
                continue
            cost = cost_a + cost_c
            if a[0] in VOWEL and (b.ph[k][3] > 0) != (a[2] > 0):
                cost += 0.15
            if c[0] in VOWEL and (b.ph[k + 1][3] > 0) != (c[2] > 0):
                cost += 0.15
            if i > 0 and k > 0:
                cost += 0.1 * min(substitution(seq[i - 1][0], b.ph[k - 1][0]), 1.0)
            if i + 2 < n and k + 2 < len(b.ph):
                cost += 0.1 * min(substitution(seq[i + 2][0], b.ph[k + 2][0]), 1.0)
            for want, kk, f in ((a, k, pitch[i]), (c, k + 1, pitch[i + 1])):
                have = b.ph[kk]
                cost += 0.15 * abs(np.log(max(have[2] - have[1], 1) * FRAME / max(want[1], 0.01)))
                if f > 0 and b.ph_f0[kk] > 0:
                    cost += F0_TARGET * abs(np.log2(b.ph_f0[kk] / f))
                if want[0] in SONORANT:
                    cost += VOICING * (1.0 - b.ph_voiced[kk])
                elif want[0] == "_":
                    cost += VOICING * b.ph_voiced[kk]
            opts.append((cost, k, k + 1))
        if not opts:
            right = sorted(b.matches(c[0]))[:6]
            opts = [(1.0 + c1 + c2, k1, k2) for c1, k1 in sorted(left)[:6] for c2, k2 in right]
        opts.sort()
        opts = opts[:N_BEST]
        cands.append([(l_, r_) for _, l_, r_ in opts])
        costs.append(np.array([c_ for c_, _, _ in opts]))
    acc, back = costs[0], []
    for i in range(1, len(cands)):
        prev_r = np.array([r for _, r in cands[i - 1]])
        cur_l = np.array([l_ for l_, _ in cands[i]])
        d = np.abs(b.mid_env[prev_r][:, None, :] - b.mid_env[cur_l][None, :, :]).mean(-1) / 10 + JOIN
        fa, fb = b.ph_f0[prev_r][:, None], b.ph_f0[cur_l][None, :]
        both = (fa > 0) & (fb > 0)
        d = d + F0_JOIN * np.where(both, np.abs(np.log2(np.maximum(fa, 1) / np.maximum(fb, 1))), 0.0)
        d = d * JOIN_CLASS.get(klass(seq[i][0]), 1.0)
        d[prev_r[:, None] == cur_l[None, :]] = 0.0
        total = acc[:, None] + d
        back.append(np.argmin(total, 0))
        acc = total.min(0) + costs[i]
    path = [int(np.argmin(acc))]
    for bp in reversed(back):
        path.append(int(bp[path[-1]]))
    path.reverse()
    return [cands[i][j] for i, j in enumerate(path)]


@pytest.mark.parametrize("pitch, tract", [(120, 1.0), (180, 1.15)])
def test_fast_selection_chooses_exactly_what_the_reference_does(pitch, tract, monkeypatch):
    from tare.tools.tune.speech import concat
    seen, fast = [], concat.select

    def spy(b, seq, pitch=None):
        seen.append((b, [list(p) for p in seq], list(pitch) if pitch else None))
        return fast(b, seq, pitch)
    monkeypatch.setattr(concat, "select", spy)
    sp = Speaker(pitch=pitch, tract=tract, engine="natural")
    for text in ("Bem-vindo à forja, viajante!", "Você trouxe o minério que eu pedi?", "Onde fica a taverna?",
                 "Sério?!", "Eu não sei...", "Custa 350 moedas.", "Cuidado, o chão da ponte está podre.",
                 "[raiva] Saiam daqui agora!", "Nhenhém, lhama, xícara, quilombo, pneu."):
        sp.spoken(text, "pt")
    assert len(seen) == 9
    for b, seq, f0 in seen:
        assert fast(b, seq, f0) == _select_reference(b, seq, f0), " ".join(p[0] for p in seq)


def test_learned_intonation_rises_for_questions_and_falls_for_statements():
    sp = Speaker(pitch=120, engine="natural")
    q = np.array(sp.spoken("Você viu o dragão?", "pt").f0)
    st = np.array(sp.spoken("Você viu o dragão.", "pt").f0)
    assert bank("pt/alex").meta["intonation"]["fit"][1] > 0.6
    tail = slice(-25, -5)
    assert np.mean(q[tail]) > 1.1 * np.mean(st[tail])
    assert np.mean(st[tail]) < np.median(st)          # a statement ends low
