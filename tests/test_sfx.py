import json
import time

import numpy as np
import pytest

from creaturesynth import RECIPES, Creature, Sfx, Voice, render
from creaturesynth.bake import bake, load_bestiary
from creaturesynth.cli import main
from creaturesynth.layers import event_times, render_modal, render_noise, render_scatter
from creaturesynth.runtime import AmbiencePlayer, VoiceBank
from creaturesynth.spec import Modal, Noise, Scatter

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
        "excalibur": {"kind": "blade", "species": "excalibur", "events": ["clash"]},
        "rain": {"kind": "ambience", "style": "cave", "events": ["loop"]}}})
    m = bake({}, tmp_path, sr=SR, takes=2, workers=1, sounds=settings["sounds"])
    clash, loop = m["sounds"]["excalibur"]["events"]["clash"], m["sounds"]["rain"]["events"]["loop"]
    assert len(clash) == 2 and len(loop) == 1 and loop[0]["loop"] and "loop" not in clash[0]
    assert m["sounds"]["excalibur"]["sfx"]["kind"] == "blade" and (tmp_path / clash[1]["file"]).exists()
    with pytest.raises(ValueError):
        load_bestiary({"sounds": {"x": {"kind": "blade", "events": ["fly"]}}})
    with pytest.raises(ValueError):
        load_bestiary({"sounds": {"x": {"kind": "blade", "colour": "red"}}})


def test_cli_sfx(tmp_path, capsys):
    out, spec = tmp_path / "hit.wav", tmp_path / "hit.json"
    assert main(["sfx", "blunt", "iron", "--event", "hit_metal", "--species", "mace", "-o", str(out),
                 "--spec", str(spec), "--sr", str(SR)]) == 0
    assert out.exists() and Voice.from_json(spec.read_text()).modal
    assert main(["sounds"]) == 0 and "ambience" in capsys.readouterr().out
    assert main(["sfx", "blade", "plasma"]) == 1
