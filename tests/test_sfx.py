import json
import time
from dataclasses import replace

import numpy as np
import pytest

from tare.tools.tune import RECIPES, Creature, Sfx, Voice, render
from tare.tools.tune.bake import bake, load_bestiary
from tare.tools.tune.cli import main
from tare.tools.tune.layers import event_times, render_modal, render_noise, render_scatter
from tare.tools.tune.runtime import AmbiencePlayer, VoiceBank
from tare.tools.tune.spec import Modal, Noise, Scatter, Syllable

SR = 22_050


def test_modal_rings_and_decays():
    m = Modal(0.0, 1.0, [(1000.0, 0.5, 1.0)], click=0.0)
    y = render_modal(m, SR, 1)
    spec = np.abs(np.fft.rfft(y))
    assert abs(np.fft.rfftfreq(len(y), 1 / SR)[np.argmax(spec)] - 1000) < 5
    level = lambda t: np.sqrt(np.mean(y[int(t * SR):int(t * SR) + 200] ** 2))  # noqa: E731
    assert 45 < 20 * np.log10(level(0.02) / level(0.52)) < 75          # ~60 dB per T60 (0.5 s)


def test_noise_band_follows_its_filter():
    def centroid(hz):
        y = render_noise(Noise(0.0, 0.5, [(0, hz), (1, hz)], "band", 4.0), SR, 2)
        p = np.abs(np.fft.rfft(y)) ** 2
        return np.sum(np.fft.rfftfreq(len(y), 1 / SR) * p) / np.sum(p)
    assert centroid(500) < 900 < 2000 < centroid(4000)


def test_scatter_rate_and_determinism():
    t = event_times([(0, 100), (1, 100)], 2.0, 7)
    assert 160 < len(t) < 240 and np.all(np.diff(t) >= 0)
    sparse = event_times([(0, 0), (1, 100)], 2.0, 7)
    assert np.sum(sparse < 1.0) < np.sum(sparse >= 1.0)                 # rate ramps up
    s = Scatter(0.0, 1.0, [(0, 50), (1, 50)], "drop", (800, 2000))
    assert np.array_equal(render_scatter(s, SR, 3), render_scatter(s, SR, 3))
    for event in ("pop", "ping"):
        assert np.isfinite(render_scatter(Scatter(0.0, 0.5, [(0, 80), (1, 80)], event), SR, 3)).all()


def test_loop_is_seamless():
    v = Voice(noise=[Noise(0.0, 3.0, [(0, 800), (1, 800)], wobble=(2.0, 0.5))], loop=0.5, seed=4)
    y = render(v, SR)
    assert len(y) == int(round(2.5 * SR))
    step = np.median(np.abs(np.diff(y)))
    assert abs(float(y[0]) - float(y[-1])) < 6 * step                  # the wrap is no bigger than any other step


@pytest.mark.parametrize("kind", list(RECIPES))
def test_every_recipe_style_and_event_renders(kind):
    r = RECIPES[kind]
    for style in r.styles:
        sx = Sfx(kind, style, species=1, size=0.3, power=0.8)
        for event in r.events:
            if kind == "ambience" and event == "loop" and style not in ("wind", "cave"):
                continue                                                 # long beds: two are enough here
            v = sx.voice(event)
            assert Voice.from_json(v.to_json()) == v
            y = render(v, SR)
            assert np.isfinite(y).all() and 0.3 < np.abs(y).max() <= 0.9, (kind, style, event)
            assert v.meta["event"] == event and v.meta["style"] == style


def notes(v: Voice) -> list[tuple[float, float]]:
    """(start, Hz) of each note of a ui voice: a struck body's lowest mode, a blip's first pitch."""
    out = [(m.start, m.modes[0][0]) for m in v.modal] + [(s.start, s.pitch[0][1]) for s in v.syllables]
    return sorted(out)


@pytest.mark.parametrize("style", RECIPES["ui"].styles)
def test_tactics_ui_follows_the_measured_shapes(style):
    ui = Sfx("ui", style, species=2)
    up = [f for _, f in notes(ui.voice("confirm"))]
    assert len(up) >= 4 and all(b > a for a, b in zip(up, up[1:], strict=False))       # climbs (60 ms a note)
    assert max(f for _, f in notes(ui.voice("cancel"))) < min(f for _, f in notes(ui.voice("select")))
    mean = lambda e: np.mean([np.log2(f) for _, f in notes(ui.voice(e))])  # noqa: E731
    assert mean("enemy_turn") < mean("turn")
    cursor = [ui.render("cursor", take, SR) for take in range(4)]
    assert all(len(y) < 0.1 * SR for y in cursor)                                      # a tick
    assert not any(np.array_equal(cursor[0], y) for y in cursor[1:])                   # never quite the same
    scroll = [notes(ui.voice("scroll", take))[0][1] for take in range(4)]
    assert scroll[0] < scroll[1] < scroll[2] > scroll[3]                              # a cycle down a list
    letters = lambda size: np.mean([notes(ui.but(size=size).voice("text", k))[0][1] for k in range(12)])  # noqa: E731
    assert letters(1.0) < letters(0.0)                                                 # big speakers, low blips


@pytest.mark.parametrize("style", RECIPES["ui"].styles)
def test_hit_results_rise_and_fall_as_measured(style):
    ui = Sfx("ui", style, species=2)
    pitch = lambda e: [f for _, f in notes(ui.voice(e))]  # noqa: E731
    assert pitch("ko")[0] > pitch("ko")[-1] and pitch("revive")[0] < max(pitch("revive"))
    assert np.mean(np.log2(pitch("heal"))) > np.mean(np.log2(pitch("damage")))
    assert ui.voice("damage").duration < 0.15 < ui.voice("critical").duration


@pytest.mark.parametrize("style", RECIPES["status"].styles)
def test_status_effects_go_the_right_way(style):
    st = Sfx("status", style, species=2)
    mean = lambda e: np.mean([np.log2(f) for _, f in notes(st.voice(e))])  # noqa: E731
    assert mean("buff") > mean("debuff")

    def clock(e):   # the gaps between a clock's ticks (the shortest layers)
        v = st.voice(e)
        t = sorted([m.start for m in v.modal if m.dur <= 0.06] + [s.start for s in v.syllables if s.dur <= 0.02])
        return np.diff(t)
    assert clock("haste")[0] > clock("haste")[-1] and clock("slow")[0] < clock("slow")[-1]
    assert all(st.voice(e).duration < 3.0 for e in st.events)                 # a tactics battle does not wait


def test_eras_dress_any_sound_as_the_originals_measured():
    def band99(y):                      # where 99 % of the energy lies below
        p = np.abs(np.fft.rfft(y)) ** 2
        return np.fft.rfftfreq(len(y), 1 / 48000)[np.searchsorted(np.cumsum(p) / p.sum(), 0.99)]
    plain, hd, old = (Sfx("ui", "crystal", species=3, power=0.8, era=e) for e in ("", "hd", "16bit"))
    assert band99(old.render("cursor", 0, 48000)) < 9000 < band99(plain.render("cursor", 0, 48000))  # PSP/DS: 3-8 kHz
    assert len(hd.render("confirm", 0, SR)) > len(plain.render("confirm", 0, SR)) + SR // 2           # HD: a tail
    v = old.voice("cursor")
    assert v.bits == 4 and v.space == 0 and v.meta["era"] == "16bit" and Voice.from_json(v.to_json()) == v
    assert Sfx.from_dict(json.loads(json.dumps(old.to_dict()))) == old
    with pytest.raises(ValueError):
        Sfx("ui", era="ps5")


def test_the_grain_follows_the_level():
    tone = lambda gain: Voice(syllables=[Syllable(0.0, 0.5, [(0, 440), (1, 440)], "sine", gain=gain)],  # noqa: E731
                              gain=gain, bits=4)
    for gain in (1.0, 0.1):
        y = render(tone(gain), SR)
        clean = render(replace(tone(gain), bits=0), SR)
        err = np.sqrt(np.mean((y - clean) ** 2)) / np.sqrt(np.mean(clean ** 2))
        assert 0.01 < err < 0.2                                     # 4 bits: a hiss 14-40 dB down, at any level


def test_knobs_vary_a_sound_within_its_character():
    base = Sfx("ui", "crystal", species=3)
    assert np.array_equal(base.render("confirm", 0, SR),                                  # defaults: untouched
                          base.but(knobs={"tempo": 1.0, "register": 0}).render("confirm", 0, SR))
    starts = lambda s: sorted(m.start for m in s.voice("confirm").modal)  # noqa: E731
    assert starts(base.but(knobs={"tempo": 2}))[-1] == pytest.approx(2 * starts(base)[-1], rel=0.01)
    pitch = lambda s, e="confirm": np.mean([np.log2(f) for _, f in notes(s.voice(e))])  # noqa: E731
    assert pitch(base.but(knobs={"register": -1})) == pytest.approx(pitch(base) - 1, abs=0.01)
    assert base.but(knobs={"ring": 0.5}).voice("confirm").duration < base.voice("confirm").duration
    assert base.but(knobs={"length": 2}).voice("confirm").duration == pytest.approx(
        2 * base.voice("confirm").duration, rel=0.02)
    learn = Sfx("ui", "fantasy", species=3)
    assert any(s.event == "ping" for s in learn.voice("learn").scatter)
    assert not any(s.event == "ping" for s in learn.but(knobs={"sparkle": 0}).voice("learn").scatter)
    assert base.but(knobs={"brightness": -1}).voice("confirm").lowpass == 2000
    keyed = [Sfx("ui", "crystal", species=n, knobs={"key": 60}) for n in range(4)]          # one key, any species
    assert all(abs(12 * (pitch(s, "hover") - np.log2(440 * 2 ** ((67 - 69) / 12)))) < 0.2 for s in keyed)
    assert Sfx.from_dict(json.loads(json.dumps(keyed[0].to_dict()))) == keyed[0]
    assert keyed[0].voice("hover").meta["knobs"] == {"key": 60.0}
    for bad in ({"tempo": 9}, {"pitch": 1}):
        with pytest.raises(ValueError):
            Sfx("ui", knobs=bad)
    with pytest.raises(ValueError):
        Sfx("blade", knobs={"key": 60})                                                    # only interface, status


@pytest.mark.parametrize("kind", list(RECIPES))
def test_every_recipe_takes_the_knobs(kind):
    r = RECIPES[kind]
    for knobs in ({"register": -2, "tempo": 4, "ring": 4, "sparkle": 3, "brightness": 1},
                  {"register": 1, "tempo": 0.25, "length": 0.25, "ring": 0.1, "brightness": -1, "sparkle": 0}):
        y = Sfx(kind, r.styles[-1], species=1, power=0.8, knobs=knobs).render(r.events[-1], 0, SR)
        assert np.isfinite(y).all() and np.abs(y).max() > 0.3, (kind, knobs)


def test_identity_takes_and_validation():
    sword = Sfx("blade", "steel", species=3)
    assert np.array_equal(sword.render("clash", 0, SR), sword.render("clash", 0, SR))
    assert not np.array_equal(sword.render("clash", 0, SR), sword.render("clash", 1, SR))
    assert sword.voice("clash").modal[0].modes != Sfx("blade", "steel", species=4).voice("clash").modal[0].modes
    assert Sfx("spell").style == "fire" and Sfx.from_dict(json.loads(json.dumps(sword.to_dict()))) == sword
    assert Sfx.random(5).kind in RECIPES
    big = Sfx("explosion", "stone", size=1.0).voice("blast").duration
    assert big > Sfx("explosion", "stone", size=0.0).voice("blast").duration
    for bad in (lambda: Sfx("laser"), lambda: Sfx("blade", "plasma"), lambda: sword.voice("explode")):
        with pytest.raises(ValueError):
            bad()


def test_runtime_bank_and_ambience_player():
    sword = Sfx("blade", "steel", species=3)
    with VoiceBank(sample_rate=SR, takes=2) as bank:
        a, b = bank.get(sword, "swing"), bank.get(sword, "swing")
        assert not np.array_equal(a, b)                                  # alternates takes
        with pytest.raises(ValueError):
            bank.get(sword, "idle")
    player = AmbiencePlayer(Sfx("ambience", "cave"), SR, accents_per_minute=600, takes=1, seed=1)
    player.add(Creature("bird", species=2), "idle", per_minute=300)
    while not player.ready or not all(f.done() for layer in player._layers for f in layer["takes"]):
        time.sleep(0.01)
    y = np.concatenate([player.read(1000) for _ in range(200)])           # ~9 s
    assert y.shape == (200_000,) and np.isfinite(y).all() and np.abs(y).max() < 1.0
    assert np.std(y) > 0
    player.close()


def test_bake_sounds_section(tmp_path):
    _, settings = load_bestiary({"creatures": {}, "sounds": {
        "excalibur": {"kind": "blade", "species": "excalibur", "events": ["clash"], "knobs": {"register": -1}},
        "rain": {"kind": "ambience", "style": "cave", "events": ["loop"]}}})
    m = bake({}, tmp_path, sr=SR, takes=2, workers=1, sounds=settings["sounds"])
    clash, loop = m["sounds"]["excalibur"]["events"]["clash"], m["sounds"]["rain"]["events"]["loop"]
    assert len(clash) == 2 and len(loop) == 1 and loop[0]["loop"] and "loop" not in clash[0]
    assert m["sounds"]["excalibur"]["sfx"]["kind"] == "blade" and (tmp_path / clash[1]["file"]).exists()
    assert m["sounds"]["excalibur"]["sfx"]["knobs"] == {"register": -1.0}
    with pytest.raises(ValueError):
        load_bestiary({"sounds": {"x": {"kind": "blade", "events": ["fly"]}}})
    with pytest.raises(ValueError):
        load_bestiary({"sounds": {"x": {"kind": "blade", "colour": "red"}}})


def test_cli_sfx(tmp_path, capsys):
    out, spec = tmp_path / "hit.wav", tmp_path / "hit.json"
    assert main(["sfx", "blunt", "iron", "--event", "hit_metal", "--species", "mace", "-o", str(out),
                 "--spec", str(spec), "--sr", str(SR)]) == 0
    assert out.exists() and Voice.from_json(spec.read_text(encoding="utf-8")).modal
    assert main(["sounds"]) == 0 and "ambience" in capsys.readouterr().out
    assert main(["sfx", "blade", "plasma"]) == 1
