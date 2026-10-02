"""creaturesynth: procedural creature voices for games.

    >>> from creaturesynth import Creature, write_wav
    >>> wolf = Creature("mammal", species=7, size=0.45, aggression=0.5)
    >>> write_wav("wolf_attack.wav", wolf.render("attack"), 48000)
    >>> dire_wolf = wolf.evolve(size=0.4, aggression=0.3)
"""
from .archetypes import ARCHETYPES, DESCRIPTIONS
from .audio_io import read_wav, to_pcm16, write_wav
from .calls import CALLS, Call, Traits
from .chip import gen1_voice
from .creature import Creature
from .genome import Genome
from .render import DEFAULT_SR, render
from .spec import ChipProgram, Syllable, Voice

__version__ = "0.1.0"

__all__ = [
    "ARCHETYPES", "CALLS", "DEFAULT_SR", "DESCRIPTIONS", "Call", "ChipProgram", "Creature", "Genome",
    "Syllable", "Traits", "Voice", "gen1_voice", "read_wav", "render", "to_pcm16", "write_wav",
]
