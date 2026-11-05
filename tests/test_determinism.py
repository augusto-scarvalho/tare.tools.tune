"""Same recipe, same WAV on any machine: 30 short sounds from every family against 16-bit references made on
Windows with the numpy and scipy of constraints.txt. Elsewhere samples may differ by the smallest step (each OS's
libm rounds a little differently; macOS moved 76 samples of one line); a bigger step is a bug. The printed table is
the measurement for the machine that ran it.

    python tests/test_determinism.py   # on Windows, after a deliberate change to the sound

rewrites only the references that changed and names them: check each was meant to change before committing it.
One file per sound, so the history grows only by the sounds that changed.
"""
import platform
import sys
from pathlib import Path

import numpy as np
import scipy

from tare.tools.tune import Creature, Sfx
from tare.tools.tune.audio_io import to_pcm16
from tare.tools.tune.music import Cue
from tare.tools.tune.render import render
from tare.tools.tune.speech import Speaker

SR = 16_000
REF = Path(__file__).parent / "fixtures" / "determinism"
EN, PT = "Welcome to the forge, traveler! Did you see the dragon?", "Bem-vindo à forja, viajante! Você viu o dragão?"
TOLERANCE = 1   # LSB: rounding flips one step; a real divergence (a moved glottal pulse) is hundreds

wolf = Creature("mammal", species="wolf", size=0.45, aggression=0.5)
hero = Speaker(pitch=120, tract=1.05)
SOUNDS = {
    "creature-wolf-attack": lambda: wolf.render("attack", sr=SR),
    "creature-direwolf-death": lambda: wolf.evolve(size=0.9).render("death", take=2, sr=SR),
    **{f"creature-{a}-{call}": (lambda a=a, call=call: Creature(a, species=3).render(call, sr=SR))
       for a, call in [("bird", "alert"), ("insect", "idle"), ("reptile", "hurt"), ("amphibian", "idle"),
                       ("monster", "attack"), ("slime", "hurt"), ("spirit", "idle"), ("robot", "alert"),
                       ("chip", "death")]},
    **{f"sfx-{kind}-{style}-{event}": (lambda k=kind, s=style, e=event: render(Sfx(k, s).voice(e, 0), SR))
       for kind, style, event in [("blade", "steel", "clash"), ("spell", "lightning", "cast"),
                                  ("ambience", "rain", "accent"), ("footstep", "stone", "walk"),
                                  ("ui", "retro", "click"), ("door", "wood", "open"),
                                  ("explosion", "fire", "blast"), ("water", "big", "splash")]},
    "speech-en-default": lambda: Speaker.preset("default").render(EN, lang="en", sr=SR),
    "speech-pt-elder": lambda: Speaker.preset("elder").render(PT, lang="pt", sr=SR),
    "speech-pt-natural": lambda: Speaker(engine="natural").render(PT, lang="pt", sr=SR),
    "speech-en-emotions": lambda: Speaker.preset("deep").render("[happy] Good to see you! [sad] But I must go...",
                                                                 lang="en", sr=SR),
    "speech-animalese": lambda: Speaker.preset("cute").render(EN, lang="en", sr=SR, style="animalese"),
    "bark-laugh-anime": lambda: hero.emote("laugh", style="anime", sr=SR),
    "bark-hurt-grunt": lambda: hero.emote("hurt_big", style="grunt", sr=SR),
    **{f"music-{cue}-{style}": (lambda c=cue, s=style: Cue(c, s, seed=1, sr=SR).render())
       for cue, style in [("victory", "chip"), ("levelup", "snes"), ("levelup", "orchestral"),
                          ("recruit", "orchestral")]},
}


def pcm(y) -> np.ndarray:
    return np.frombuffer(to_pcm16(np.asarray(y, dtype=np.float32)), dtype="<i2")


def test_same_wav_as_the_reference():
    assert sorted(f.stem for f in REF.glob("*.npy")) == sorted(SOUNDS)
    rows, off = [], []
    for name, make in SOUNDS.items():
        got, want = pcm(make()), np.load(REF / f"{name}.npy")
        if got.shape != want.shape:
            rows.append(f"{name:34} length {len(got)} instead of {len(want)}")
            off.append(name)
            continue
        d = np.abs(got.astype(np.int32) - want)
        n, worst = int(np.count_nonzero(d)), int(d.max(initial=0))
        rows.append(f"{name:34} {n:7} samples differ, at most {worst} LSB")
        if worst > TOLERANCE:
            off.append(name)
    exact = sum(r.endswith(" 0 samples differ, at most 0 LSB") for r in rows)
    print(f"\n{platform.system()} {platform.machine()}, Python {platform.python_version()}, numpy {np.__version__}, "
          f"scipy {scipy.__version__}: {exact} of {len(SOUNDS)} bit-identical", *rows, sep="\n")
    assert not off, f"beyond {TOLERANCE} LSB: {off}"


if __name__ == "__main__":
    if platform.system() != "Windows" and "--force" not in sys.argv:
        sys.exit("the references are made on Windows; pass --force to write them here anyway")
    REF.mkdir(exist_ok=True)
    for name, make in SOUNDS.items():
        path, got = REF / f"{name}.npy", pcm(make())
        if not path.exists() or not np.array_equal(np.load(path), got):
            np.save(path, got)
            print("changed:", name)
    for path in REF.glob("*.npy"):
        if path.stem not in SOUNDS:
            path.unlink()
            print("removed:", path.stem)
