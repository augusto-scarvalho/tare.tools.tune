"""Which engine says what: the practical division between natural and procedural voices.

    role       for                        voice
    main       important NPC lines        natural (Kokoro) when installed, else a formant voice
    minor      everyone else              a unique formant voice per NPC (seeded by name)
    crowd      background walla           formant voice, invented language ("gibberish")
    creature   talking creatures          the creature's own formant voice, babbling
    robot      machines, constructs       the robot formant voice, real words

Natural voices sound human but are heavy, not procedural and cannot become a portable spec;
formant voices are light, deterministic, endlessly variable and can babble.
"""
from dataclasses import dataclass, replace

import numpy as np

from .. import rng
from ..render import DEFAULT_SR
from ..spec import Voice

ROLES = ("main", "minor", "crowd", "creature", "robot")


@dataclass(frozen=True)
class Cast:
    speaker: object          # Speaker (formant) or NeuralSpeaker
    style: str = "speech"    # speech | gibberish | animalese | mumble (formant voices only)
    role: str = "minor"
    name: str = ""

    @property
    def natural(self) -> bool:
        from .neural import NeuralSpeaker
        return isinstance(self.speaker, NeuralSpeaker)

    def voice(self, text: str, lang: str = "pt") -> Voice | None:
        """The portable spec (formant voices), or None for natural voices."""
        return None if self.natural else self.speaker.voice(text, lang, style=self.style)

    def render(self, text: str, lang: str = "pt", sr: int = DEFAULT_SR) -> np.ndarray:
        if self.natural:
            return self.speaker.render(text, lang, sr)
        return self.speaker.render(text, lang, sr, style=self.style)


def _gendered_random(name: str, gender: str | None):
    from . import Speaker
    for attempt in range(64):  # deterministic: the first seed whose voice fits the requested register
        sp = Speaker.random(rng.seed32("npc", name, attempt), name=name)
        if gender is None or (gender == "f" and sp.pitch >= 165) or (gender == "m" and sp.pitch <= 150):
            return sp
    return sp


def _natural_voice(name: str, lang: str, gender: str | None) -> str:
    from .neural import VOICES
    options = [v for v in VOICES[lang] if gender is None or v[1] == gender] or VOICES[lang]
    return options[int(rng.uniform(rng.key("cast", name)) * len(options)) % len(options)]


def cast(role: str = "minor", name: str = "", lang: str = "pt", gender: str | None = None, creature=None,
         voice=None, style: str | None = None, natural: bool | None = None) -> Cast:
    """Pick engine, voice and style for a character. `voice` (preset, npc:<seed>, kokoro:<id>) overrides."""
    from . import Speaker, speaker_from
    from .neural import available
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}; choose from {', '.join(ROLES)}")
    if gender not in (None, "f", "m"):
        raise ValueError("gender is 'f', 'm' or omitted")
    natural = available() if natural is None else natural

    if voice is not None:
        sp = speaker_from(voice)
        from .neural import NeuralSpeaker
        if isinstance(sp, NeuralSpeaker) and not natural:  # asked for a natural voice we cannot run
            g = gender or (sp.voice[1] if len(sp.voice) > 1 and sp.voice[1] in "fm" else None)
            sp = _gendered_random(name, g)
    elif role == "main":
        sp = speaker_from(f"kokoro:{_natural_voice(name, lang, gender)}") if natural else _gendered_random(name, gender)
    elif role == "creature":
        if creature is None:
            raise ValueError("role 'creature' needs the creature")
        sp = Speaker.from_creature(creature)
    elif role == "robot":
        sp = Speaker.preset("robot")
    else:  # minor, crowd
        sp = _gendered_random(name, gender)

    if style is None:
        small = creature is not None and creature.size < 0.5
        style = {"crowd": "gibberish", "creature": "animalese" if small else "gibberish"}.get(role, "speech")
    return Cast(replace(sp, name=name or sp.name), style, role, name)
