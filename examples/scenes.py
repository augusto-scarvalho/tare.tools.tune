"""Scenes: effects, creatures, a voice and music placed on a Score over a place's ambience, panned in stereo.

    python examples/scenes.py [out_dir]

1. dungeon_fight: footsteps coming closer through a dungeon, a guard's challenge, swords drawn, a fight with an
   ogre, the ogre falls, coins spill; the battle music under it all, then the victory jingle.
2. treasure: a cave, a lever, a trapped corridor, the chest unlocked and opened, coins, gems, level up.
3. spell_duel: a storm on a hill, fire against ice, a shield blocks a bolt, lightning ends it.
"""
import sys
from pathlib import Path

import numpy as np

from tare.tools.tune import Creature, Sfx, write_wav
from tare.tools.tune.music import Cue
from tare.tools.tune.score import Score
from tare.tools.tune.speech import Speaker

SR = 48_000


def bed(place: str, seconds: float, power: float = 0.4) -> np.ndarray:
    """A place's seamless ambience loop, repeated to `seconds`."""
    loop = Sfx("ambience", place, power=power).render("loop", 0, SR)
    return np.tile(loop, int(seconds * SR) // len(loop) + 1)[: int(seconds * SR)]


def steps(score: Score, floor: str, start: float, n: int, every: float, pan=(-0.6, 0.0), gain=0.5, run=False):
    """`n` footsteps from one side towards the other, a different take each time."""
    feet = Sfx("footstep", floor, species=2, power=0.6)
    for k in range(n):
        p = pan[0] + (pan[1] - pan[0]) * k / max(n - 1, 1)
        score.add(feet.render("run" if run else "walk", k, SR), at=start + k * every, gain=gain, pan=p, send=0.25)


def dungeon_fight() -> np.ndarray:
    s = Score(bpm=100, hall=2.5, sr=SR)
    s.add(bed("dungeon", 26.0), gain=0.35, send=0.0)
    battle = Cue("battle", seed=4, sr=SR)
    music = battle.render()
    s.add(np.tile(music, (2, 1))[: int(14 * SR)] * np.linspace(0, 1, int(14 * SR))[:, None] ** 0.5, at=6.0,
          gain=0.25)
    steps(s, "stone", 0.5, 6, 0.55, pan=(0.7, 0.2))
    s.add(Speaker.preset("deep").render("Quem está aí?", lang="pt", sr=SR), at=3.0, gain=0.6, pan=-0.3, send=0.3)
    sword = Sfx("blade", "steel", species=3, power=0.8)
    s.add(sword.render("draw", 0, SR), at=4.0, gain=0.7, pan=-0.2, send=0.2)
    ogre = Creature("monster", species=13, size=0.9, aggression=0.8)
    s.add(ogre.render("alert", sr=SR), at=5.0, gain=0.8, pan=0.5, send=0.4)
    t = 6.2
    for k, (ev, who) in enumerate([("swing", -0.2), ("clash", 0.1), ("swing", -0.2), ("hit_flesh", 0.4),
                                   ("clash", 0.1), ("swing", -0.2), ("hit_flesh", 0.4)]):
        s.add(sword.render(ev, k, SR), at=t, gain=0.8, pan=who, send=0.2)
        if ev == "hit_flesh":
            s.add(ogre.render("hurt", take=k, sr=SR), at=t + 0.08, gain=0.6, pan=0.45, send=0.35)
        t += 0.55 if ev == "swing" else 0.9
    club = Sfx("blunt", "wood", species=5, power=0.9)
    s.add(club.render("swing", 0, SR), at=t, gain=0.7, pan=0.4, send=0.2)
    s.add(Sfx("shield", "metal", species=2).render("block_blunt", 0, SR), at=t + 0.25, gain=0.8, pan=0.0, send=0.25)
    t += 1.0
    s.add(sword.render("hit_flesh", 9, SR), at=t, gain=0.9, pan=0.3, send=0.2)
    s.add(ogre.render("death", sr=SR), at=t + 0.1, gain=0.8, pan=0.45, send=0.45)
    s.add(Sfx("body", "stone", size=0.9).render("fall", 0, SR), at=t + 1.4, gain=0.9, pan=0.45, send=0.3)
    s.add(Sfx("item", "coins").render("drop", 0, SR), at=t + 2.2, gain=0.6, pan=0.5, send=0.25)
    s.add(Cue("victory", seed=4, sr=SR).render(), at=t + 2.8, gain=0.7)
    return s.render()


def treasure() -> np.ndarray:
    s = Score(bpm=90, hall=3.0, sr=SR)
    s.add(bed("cave", 20.0), gain=0.4)
    steps(s, "gravel", 0.3, 5, 0.6, pan=(-0.7, -0.1))
    s.add(Sfx("lever", "iron").render("pull", 0, SR), at=3.6, gain=0.7, pan=0.3, send=0.35)
    s.add(Sfx("trap", "spikes").render("fire", 0, SR), at=4.6, gain=0.7, pan=-0.5, send=0.3)
    steps(s, "gravel", 5.6, 4, 0.35, pan=(-0.1, 0.2), run=True)
    chest = Sfx("chest", "iron", species=1)
    s.add(chest.render("locked", 0, SR), at=7.4, gain=0.7, pan=0.2, send=0.25)
    s.add(chest.render("unlock", 0, SR), at=8.6, gain=0.7, pan=0.2, send=0.25)
    s.add(chest.render("open", 0, SR), at=9.6, gain=0.8, pan=0.2, send=0.3)
    s.add(Sfx("item", "coins").render("pickup", 0, SR), at=11.2, gain=0.7, pan=0.1, send=0.2)
    s.add(Sfx("item", "gem").render("pickup", 0, SR), at=12.0, gain=0.7, pan=0.0, send=0.25)
    s.add(Cue("levelup", seed=2, sr=SR).render(), at=12.8, gain=0.6)
    return s.render()


def spell_duel() -> np.ndarray:
    s = Score(bpm=120, hall=2.0, sr=SR)
    s.add(bed("storm", 16.0, power=0.3), gain=0.45)
    fire, ice = Sfx("spell", "fire", species=3, power=0.8), Sfx("spell", "ice", species=5, power=0.8)
    s.add(fire.render("charge", 0, SR), at=0.5, gain=0.6, pan=-0.6, send=0.2)
    s.add(ice.render("charge", 0, SR), at=1.0, gain=0.6, pan=0.6, send=0.2)
    s.add(fire.render("cast", 0, SR), at=2.2, gain=0.8, pan=-0.6, send=0.2)
    s.add(fire.render("travel", 0, SR)[: int(0.9 * SR)], at=2.5, gain=0.5, pan=0.0, send=0.2)
    s.add(Sfx("shield", "metal").render("block_blunt", 0, SR), at=3.4, gain=0.6, pan=0.6, send=0.25)
    s.add(fire.render("impact", 0, SR), at=3.4, gain=0.7, pan=0.6, send=0.3)
    s.add(ice.render("cast", 0, SR), at=5.0, gain=0.8, pan=0.6, send=0.2)
    s.add(ice.render("impact", 0, SR), at=5.8, gain=0.8, pan=-0.6, send=0.3)
    bolt = Sfx("spell", "lightning", species=1, power=1.0)
    s.add(bolt.render("charge", 0, SR), at=7.5, gain=0.6, pan=-0.6, send=0.2)
    s.add(bolt.render("impact", 0, SR), at=9.0, gain=1.0, pan=0.5, send=0.35)
    s.add(Cue("gameover", seed=1, sr=SR).render(), at=10.5, gain=0.35)
    return s.render()


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "scenes")
    for name, fn in (("dungeon_fight", dungeon_fight), ("treasure", treasure), ("spell_duel", spell_duel)):
        print(write_wav(out / f"{name}.wav", fn(), SR))
