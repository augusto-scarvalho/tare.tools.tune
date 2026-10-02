"""Which engine says what.

    role       for                        voice
    main       important NPC lines        a natural voice (a voice bank), unique per name
    minor      everyone else              a unique formant voice per NPC (seeded by name)
    crowd      background walla           formant voice, invented language ("gibberish")
    creature   talking creatures          the creature's own formant voice, babbling
    robot      machines, constructs       the robot formant voice, real words

Both engines are deterministic and give a portable spec. Natural voices sound human and carry a few MB of voice
bank per language; formant voices are tiny, stretch to any creature and babble best.
"""
from dataclasses import dataclass, replace

import numpy as np

from .. import rng
from ..render import DEFAULT_SR
from ..spec import Voice

ROLES = ("main", "minor", "crowd", "creature", "robot")


@dataclass(frozen=True)
class Cast:
    speaker: object          # Speaker
    style: str = "speech"    # speech | gibberish | animalese | mumble
    role: str = "minor"
    name: str = ""

    @property
    def natural(self) -> bool:
        return self.speaker.engine == "natural"

    def voice(self, text: str, lang: str = "pt") -> Voice:
        """The portable spec."""
        return self.speaker.voice(text, lang, style=self.style)

    def render(self, text: str, lang: str = "pt", sr: int = DEFAULT_SR) -> np.ndarray:
        return self.speaker.render(text, lang, sr, style=self.style)


def _gendered_random(name: str, gender: str | None):
    from . import Speaker
    for attempt in range(64):  # deterministic: the first seed whose voice fits the requested register
        sp = Speaker.random(rng.seed32("npc", name, attempt), name=name)
        if gender is None or (gender == "f" and sp.pitch >= 165) or (gender == "m" and sp.pitch <= 150):
            return sp
    return sp


def cast(role: str = "minor", name: str = "", lang: str = "pt", gender: str | None = None, creature=None,
         voice=None, style: str | None = None, natural: bool | None = None) -> Cast:
    """Pick engine, voice and style for a character. `voice` (preset, npc:<seed>, natural[:m|f|<bank>]) overrides;
    `natural=False` keeps the main roles on the formant engine too."""
    from . import Speaker, speaker_from
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}; choose from {', '.join(ROLES)}")
    if gender not in (None, "f", "m"):
        raise ValueError("gender is 'f', 'm' or omitted")
    natural = True if natural is None else natural

    if voice is not None:
        sp = speaker_from(voice)
        if sp.engine == "natural" and not natural:     # asked for a natural voice, but not here: same register
            sp = _gendered_random(name, gender or ("f" if sp.tract > 1.07 else "m"))
    elif role == "main":
        sp = _gendered_random(name, gender)
        if natural:
            sp = sp.but(engine="natural")
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
