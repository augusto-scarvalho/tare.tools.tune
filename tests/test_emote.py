import numpy as np
import pytest

from tare.tools.tune.render import render
from tare.tools.tune.spec import Vocoded, Voice
from tare.tools.tune.speech import Speaker
from tare.tools.tune.speech.emote import EMOTES, STYLES, emote, shout_pitch
from tare.tools.tune.speech.vocoder import FRAME, Template, band_freqs, synthesize, template, templates

SR = 16_000


def test_every_emote_in_every_style():
    hero = Speaker(pitch=120, tract=1.05)
    for style in STYLES:
        for kind in EMOTES:
            y = hero.emote(kind, style, 0.7, 0, SR)
            assert np.isfinite(y).all() and 0.08 < len(y) / SR < 4.5 and np.abs(y).max() > 0.5


def test_takes_vary_and_repeat():
    s = Speaker.preset("high")
    a, b = s.emote("attack", "mmo", 0.7, 0, SR), s.emote("attack", "mmo", 0.7, 1, SR)
    assert np.array_equal(a, s.emote("attack", "mmo", 0.7, 0, SR))
    assert len(a) != len(b) or not np.array_equal(a, b)


def test_shouting_register_matches_the_recordings():
    assert 300 < shout_pitch(95, 1.0, 0.85) < 380          # a 95 Hz man shouts at ~345 Hz
    assert 470 < shout_pitch(280, 1.17, 0.85) < 590        # a 280 Hz woman at ~530 Hz
    assert shout_pitch(120, 1.0, 0.0) == pytest.approx(120)


def pitch_of(v: Vocoded) -> float:
    return template(v.clip).pitch * v.pitch


def test_gasp_keeps_to_tactics_ogre():
    """Hurt ~0.4 s, death 0.65-0.85 s, both near the speaking voice rather than shouted."""
    for hero in (Speaker(pitch=110, tract=1.0), Speaker(pitch=210, tract=1.15)):
        gasps = [emote(hero, "hurt", "gasp", take=k) for k in range(4)]
        assert all(0.3 < v.duration < 0.55 for v in gasps)
        assert all(0.55 < emote(hero, "death", "gasp", take=k).duration < 1.2 for k in range(4))
        shouts = [emote(hero, "hurt", "tactics", take=k) for k in range(4)]
        assert np.mean([pitch_of(v) for v in gasps]) < 0.8 * np.mean([pitch_of(v) for v in shouts])


def test_kiai_keeps_to_utawarerumono():
    """A shout that holds (the character's longest takes), pain darker and breathier; one performer per character,
    and no performance stretched far to get there (a stretched voice turns robotic)."""
    from tare.tools.tune.speech.emote import performer
    for hero in (Speaker(pitch=110, tract=1.0), Speaker(pitch=210, tract=1.15)):
        shouts = [emote(hero, "attack", "kiai", take=k) for k in range(4)]
        assert all(0.3 < v.duration < 0.8 for v in shouts)
        assert np.mean([v.duration for v in shouts]) > 1.1 * np.mean([emote(hero, "attack", take=k).duration
                                                                     for k in range(4)])
        pain = [emote(hero, "hurt", "kiai", take=k) for k in range(4)]
        assert all(0.3 < v.duration < 0.9 for v in pain)
        assert max(v.tilt for v in pain) < min(v.tilt for v in shouts) and pain[0].breath > shouts[0].breath
        barks = shouts + pain + [emote(hero, "attack_big", "kiai", take=k) for k in range(4)]
        assert len({performer(template(v.clip)) for v in barks}) == 1 and all(v.stretch < 1.25 for v in barks)


def test_barks_follow_the_speakers_voice():
    low, high = Speaker(pitch=90, tract=0.95), Speaker(pitch=300, tract=1.3)
    assert pitch_of(emote(high, "hmm")) > 2.5 * pitch_of(emote(low, "hmm"))
    shouts = [pitch_of(emote(low, "attack", take=i)) for i in range(6)]
    assert np.median(shouts) > 2 * 90                       # an effort is pitched far above speech


def test_a_voice_gets_performers_like_it():
    heroine, hero = Speaker(pitch=215, tract=1.16), Speaker(pitch=125, tract=1.04)
    for kind in ("attack", "attack_big", "hurt", "jump", "laugh", "cheer"):
        for take in range(3):
            assert template(emote(heroine, kind, take=take).clip).tract > 1.05
            assert template(emote(hero, kind, take=take).clip).tract < 1.05
    assert emote(hero, "giggle").clip.startswith("laugh/")   # no man giggles in the recordings: a quick laugh


def test_every_kind_has_performances():
    kinds = {t.kind for t in templates()}
    assert set(EMOTES) <= kinds and len(templates()) > 150
    for t in templates():
        voiced = t.f0[t.f0 > 0]
        assert t.env.shape == (len(t.f0), 32) and ((voiced > 40) & (voiced < 1300)).all()


def test_vocoded_layer_round_trips_in_the_spec():
    v = Voice(vocoded=[Vocoded("laugh/male/536811", 0.1, pitch=1.2, warp=1.1, stretch=0.9, breath=-0.2)], seed=3)
    w = Voice.from_json(v.to_json())
    assert w == v and w.duration == pytest.approx(0.1 + template("laugh/male/536811").duration * 0.9)
    assert np.array_equal(render(v, SR), render(w, SR))
    with pytest.raises(ValueError):
        render(Voice(vocoded=[Vocoded("dance/nobody/0")]), SR)


def steady(f0: float = 200.0, formant: float = 1000.0) -> Template:
    n = 120
    env = np.tile(-60 + 40 * np.exp(-((band_freqs() - formant) / 300) ** 2), (n, 1))
    return Template("test", "test", "test", 1.0, f0, np.full(n, f0), env, np.zeros((n, 5)))


def peak(y: np.ndarray, lo: float, hi: float) -> float:
    y = y[len(y) // 4: 3 * len(y) // 4]
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    f = np.fft.rfftfreq(len(y), 1 / SR)
    band = (f > lo) & (f < hi)
    return float(f[band][np.argmax(spec[band])])


def test_vocoder_moves_pitch_formants_and_length():
    t = steady()
    y = synthesize(t, SR, seed=1)
    assert peak(y, 100, 300) == pytest.approx(200, abs=3)
    assert peak(synthesize(t, SR, pitch=1.5, seed=1), 100, 450) == pytest.approx(300, abs=4)
    centroid = [peak(synthesize(t, SR, warp=w, seed=1), 500, 3000) for w in (1.0, 1.3)]
    assert centroid[1] == pytest.approx(1.3 * centroid[0], rel=0.12)
    assert len(synthesize(t, SR, stretch=2.0, seed=1)) == pytest.approx(2 * len(t.f0) * FRAME * SR, rel=0.1)


def test_vocoder_is_deterministic_and_seeded():
    t = template("sigh/female/403936")
    a = synthesize(t, SR, seed=1)
    assert np.array_equal(a, synthesize(t, SR, seed=1)) and not np.array_equal(a, synthesize(t, SR, seed=2))


def test_unknown_emote_or_style():
    with pytest.raises(ValueError):
        Speaker().emote("dance")
    with pytest.raises(ValueError):
        Speaker().emote("laugh", style="opera")
