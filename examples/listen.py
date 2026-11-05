"""The sounds of the README's Listen section, rendered from code: run it and you get the same WAVs, sample for sample
(OGG copies with --ogg, which needs the export extra).

    python examples/listen.py [out_dir] [--ogg]

Each sound ends as bake and freeze end it: 60 dB under its peak, unless it loops or rings in a room.
"""
import sys
from pathlib import Path

import numpy as np

from tare.tools.tune import Creature, Sfx, rng, write_wav
from tare.tools.tune.audio_io import trim_tail
from tare.tools.tune.exports import write_ogg
from tare.tools.tune.music import Cue
from tare.tools.tune.render import render
from tare.tools.tune.speech import Speaker, speaker_from

SR = 48_000
HERO = Speaker(pitch=120, tract=1.05)
WELCOME_PT = "Bem-vindo à forja, viajante! Você viu o dragão?"
WELCOME_EN = "Welcome to the forge, traveler! Did you see the dragon?"


def voiced(voice):
    audio = render(voice, SR)
    return (audio if voice.loop or voice.space else trim_tail(audio, SR)), voice.loop > 0


def said(voice, text, lang, **style):
    return trim_tail(speaker_from(voice).render(text, lang=lang, sr=SR, **style), SR), False


def cue(kind, style, seed):
    c = Cue(kind, style, seed=seed, sr=SR)
    return c.render(), c.length > 0


SOUNDS = {
    "bird-alert": lambda: voiced(Creature("bird", species=rng.seed32("songbird")).voice("alert", 0)),
    "sword-clash": lambda: voiced(Sfx("blade", "steel", species="excalibur").voice("clash", 3)),
    "fire-spell": lambda: voiced(Sfx("spell", "fire").voice("cast", 0)),
    "rain-loop": lambda: voiced(Sfx("ambience", "rain").voice("loop", 0)),
    "pt-natural-m": lambda: said("natural:m", WELCOME_PT, "pt"),
    "pt-natural-f": lambda: said("natural:f", "Preciso de uma espada nova. A minha quebrou na ponte.", "pt"),
    "pt-deep": lambda: said("deep", WELCOME_PT, "pt"),
    "pt-child": lambda: said("child", "Olha, mãe! Um dragão de verdade!", "pt"),
    "pt-giant": lambda: said("giant", "Quem ousa entrar na minha caverna?", "pt"),
    "en-default": lambda: said("default", WELCOME_EN, "en"),
    "en-emotions": lambda: said("deep", "[happy] Good to see you! [sad] But I must go...", "en"),
    "en-robot": lambda: said("robot", "Intruder detected. Please remain where you are.", "en"),
    "bark-laugh": lambda: (trim_tail(HERO.emote("laugh", style="anime", sr=SR), SR), False),
    "bark-kiai": lambda: (trim_tail(HERO.emote("attack_big", style="kiai", sr=SR), SR), False),
    "bark-hurt": lambda: (trim_tail(HERO.emote("hurt_big", style="grunt", sr=SR), SR), False),
    "bark-cheer": lambda: (trim_tail(HERO.emote("cheer", style="mmo", sr=SR), SR), False),
    "victory": lambda: cue("victory", "orchestral", 3),
    "levelup-16bit": lambda: cue("levelup", "snes", 1),
    "town-16bit": lambda: cue("town", "snes", 7),
    "tavern": lambda: cue("tavern", "orchestral", 7),
    "battle-8bit": lambda: cue("battle", "chip", 2),
    "reverie-16bit": lambda: cue("reverie", "snes", 1),
    "festival": lambda: cue("festival", "orchestral", 3),
    "skirmish": lambda: cue("skirmish", "orchestral", 1),
    "shrine": lambda: cue("shrine", "orchestral", 1),
}

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(args[0] if args else "listen")
    for name, make in SOUNDS.items():
        audio, loop = make()
        write_wav(out / f"{name}.wav", audio, SR, loop=loop)
        if "--ogg" in sys.argv:
            write_ogg(out / f"{name}.ogg", np.clip(audio, -1, 1), SR)
        print(f"{name}: {len(audio) / SR:.1f} s{', loop' if loop else ''}")
