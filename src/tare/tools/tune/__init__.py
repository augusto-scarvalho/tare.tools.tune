"""tare.tools.tune: procedural creature voices, speech and sound effects for games.

    >>> from tare.tools.tune import Creature, Sfx, write_wav
    >>> wolf = Creature("mammal", species=7, size=0.45, aggression=0.5)
    >>> write_wav("wolf_attack.wav", wolf.render("attack"), 48000)
    >>> dire_wolf = wolf.evolve(size=0.4, aggression=0.3)
    >>> write_wav("clash.wav", Sfx("blade", "steel").render("clash"), 48000)
"""
from .archetypes import ARCHETYPES, DESCRIPTIONS
from .audio_io import read_wav, to_pcm16, write_wav
from .calls import CALLS, Call, Traits
from .chip import gen1_voice
from .creature import Creature
from .genome import Genome
from .render import DEFAULT_SR, render
from .sfx import RECIPES, Sfx
from .spec import ChipProgram, Modal, Noise, Scatter, Syllable, Voice

__version__ = "0.1.0"

__all__ = [
    "ARCHETYPES", "CALLS", "DEFAULT_SR", "DESCRIPTIONS", "RECIPES", "Call", "ChipProgram", "Creature", "Genome",
    "Modal", "Noise", "Scatter", "Sfx", "Syllable", "Traits", "Voice", "gen1_voice", "read_wav", "render", "to_pcm16",
    "write_wav",
]
