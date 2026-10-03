import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from tare.tools.tune import Creature, read_wav
from tare.tools.tune.bake import bake, load_bestiary
from tare.tools.tune.cli import main
from tare.tools.tune.runtime import VoiceBank

EXAMPLE = Path(__file__).parents[1] / "examples" / "bestiary.json"
SR = 22_050


def test_bestiary_extends_random_and_named_species():
    creatures, settings = load_bestiary(EXAMPLE)
    assert settings["takes"] == 3
    cub, wolf, dire = creatures["cub"], creatures["wolf"], creatures["dire_wolf"]
    assert cub.species == wolf.species == dire.species  # one species, three evolution stages
    assert (cub.size, wolf.size, dire.size) == (0.15, 0.45, 0.9)
    assert dire.archetype == "mammal" and dire.name == "dire_wolf"
    assert creatures["mystery"] == replace(Creature.random(7), name="mystery")


def test_bestiary_errors():
    with pytest.raises(ValueError, match="unknown creature"):
        load_bestiary({"creatures": {"a": {"extends": "b"}}})
    with pytest.raises(ValueError, match="circular"):
        load_bestiary({"creatures": {"a": {"extends": "b"}, "b": {"extends": "a"}}})
    with pytest.raises(ValueError, match="'a'"):
        load_bestiary({"creatures": {"a": {"archetype": "mammal", "colour": "red"}}})


def test_bake_writes_packs_and_manifest(tmp_path):
    creatures = {"wolf": Creature("mammal", 7), "bot": Creature("robot", 2)}
    manifest = bake(creatures, tmp_path, calls=["idle", "hurt"], takes=2, sr=SR, workers=2)
    on_disk = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk == manifest and on_disk["sample_rate"] == SR
    for name in creatures:
        for call in ("idle", "hurt"):
            entries = manifest["creatures"][name]["calls"][call]
            assert len(entries) == 2
            for e in entries:
                audio, sr = read_wav(tmp_path / e["file"])
                assert sr == SR and abs(len(audio) / sr - e["duration"]) < 1e-3
                assert (tmp_path / e["spec"]).exists()


def test_voice_bank_rotates_takes():
    c = Creature("bird", 3)
    with VoiceBank(sample_rate=SR, takes=3, seed=0) as bank:
        assert bank.get(c, "idle", block=False) is None  # not rendered yet: never stalls
        for f in bank.warm(c, ["idle"]):
            f.result()
        assert bank.ready(c, "idle")
        picks = []
        for _ in range(20):
            audio = bank.get(c, "idle")
            assert isinstance(audio, np.ndarray)
            picks.append(bank._last[(c, "idle")])
        assert all(a != b for a, b in zip(picks, picks[1:], strict=False)) and len(set(picks)) == 3


def test_cli(tmp_path, capsys):
    wav, spec = tmp_path / "roar.wav", tmp_path / "roar.json"
    assert main(["render", "monster", "--species", "ogre", "--size", "0.9", "--call", "attack",
                 "--gene", "kind=0.1", "-o", str(wav), "--spec", str(spec), "--sr", str(SR)]) == 0
    assert main(["from-spec", str(spec), "-o", str(tmp_path / "again.wav"), "--sr", str(SR)]) == 0
    assert wav.read_bytes() == (tmp_path / "again.wav").read_bytes()
    assert main(["gen1", "25", "-o", str(tmp_path / "p.wav"), "--sr", str(SR)]) == 0
    assert main(["zoo", "-n", "3", "-o", str(tmp_path / "zoo"), "--workers", "1", "--sr", str(SR)]) == 0
    assert main(["list"]) == 0
    assert "mammal" in capsys.readouterr().out
    assert main(["bake", str(tmp_path / "missing.json")]) == 1
