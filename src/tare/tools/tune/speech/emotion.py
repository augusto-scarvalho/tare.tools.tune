"""Feelings while speaking: how an emotion moves a voice, and tags that change it mid-line.

    >>> rei.render("[alegria] Que bom te ver! [tristeza] Mas eu preciso partir...")
    >>> rei.render("Saia daqui!", emotion="raiva")
    >>> rei.render("[medo:0.5] Você ouviu isso?")          # intensity 0..1 (default 0.8)

Measured on emoUERJ (Bastos Germano, Pompeu Tcheou, da Rocha Henriques and Pinto Gomes Junior, UERJ 2021,
CC BY 4.0; eight Brazilian actors, 377 recordings; analysis only, the recordings are not in the repository):
each emotion against the same actor's neutral reading, averaged over the actors.

                pitch     pitch range   rate    brightness   breath   end of statements
    alegria     +6.3 st   x1.27         x0.98   +3.5 dB      x0.89    falls 1.4 st further
    raiva       +4.6 st   x1.27         x1.05   +3.7 dB      x1.0     falls 3.5 st further
    tristeza    -0.2 st   x0.97         x0.92   +0.8 dB      x1.13    falls 1.5 st less, more pauses

(brightness: energy at 2-5 kHz against 0.1-1 kHz; about 3.3 octaves apart, so +3.5 dB is ~+1 dB per octave.)
emoUERJ has no fear or surprise: those follow the directions of Murray & Arnott (1993), at the size of the
measured ones (fear higher, faster, breathier, trembling; surprise higher and much wider).
"""
import re
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Emotion:
    pitch: float = 0.0        # semitones
    range: float = 1.0        # x the intonation's movements
    rate: float = 1.0         # x the speaking rate
    tilt: float = 0.0         # brighter (+) or darker (-), dB per octave
    breath: float = 0.0       # more air (+) or less (-), as Vocoded.breath; 1 = whispered
    final: float = 0.0        # semitones at the end of statements: further down (-) or less (+)
    jitter: float = 0.0       # semitones of extra pitch wander (a trembling voice)
    pause: float = 1.0        # x the pauses between phrases

    def scaled(self, k: float) -> "Emotion":
        """The emotion at intensity k (0 = neutral, 1 = as the actors performed it)."""
        return Emotion(self.pitch * k, 1 + (self.range - 1) * k, 1 + (self.rate - 1) * k, self.tilt * k,
                       self.breath * k, self.final * k, self.jitter * k, 1 + (self.pause - 1) * k)


EMOTIONS = {
    "neutro": Emotion(),
    "alegria": Emotion(pitch=6.3, range=1.27, rate=0.98, tilt=1.05, breath=-0.11, final=-1.4),
    "raiva": Emotion(pitch=4.6, range=1.27, rate=1.05, tilt=1.1, final=-3.5),
    "tristeza": Emotion(pitch=-0.2, range=0.97, rate=0.92, tilt=0.25, breath=0.13, final=1.5, pause=1.3),
    "medo": Emotion(pitch=5.0, range=1.15, rate=1.12, tilt=0.4, breath=0.15, jitter=0.35),
    "surpresa": Emotion(pitch=4.0, range=1.5, rate=0.97, tilt=0.6),
    "sussurro": Emotion(pitch=-1.0, range=0.7, rate=0.9, breath=1.0, pause=1.2),
}
ALIASES = {"feliz": "alegria", "alegre": "alegria", "happy": "alegria", "joy": "alegria",
           "bravo": "raiva", "brava": "raiva", "irritado": "raiva", "angry": "raiva", "anger": "raiva",
           "triste": "tristeza", "sad": "tristeza", "sadness": "tristeza",
           "assustado": "medo", "assustada": "medo", "fear": "medo", "scared": "medo",
           "surpreso": "surpresa", "surprise": "surpresa", "surprised": "surpresa",
           "neutral": "neutro", "normal": "neutro", "whisper": "sussurro", "sussurrando": "sussurro"}
INTENSITY = 0.8                   # the actors were theatrical: a little less by default
TAG = re.compile(r"\[\s*([^\]:\s]+)\s*(?::\s*([0-9.]+)\s*)?\]")


def emotion(name: str | Emotion | None, intensity: float = INTENSITY) -> Emotion:
    if name is None:
        return Emotion()
    if isinstance(name, Emotion):
        return name
    key = ALIASES.get(name.lower(), name.lower())
    if key not in EMOTIONS:
        raise ValueError(f"unknown emotion {name!r}; choose from {', '.join(EMOTIONS)} (or {', '.join(ALIASES)})")
    return EMOTIONS[key].scaled(intensity)


def split(text: str, default: str | Emotion | None = None) -> list[tuple[Emotion, str]]:
    """Text with [emotion] or [emotion:intensity] tags -> [(emotion, the text it covers)]."""
    out, current, pos = [], emotion(default), 0
    for m in TAG.finditer(text):
        if text[pos:m.start()].strip():
            out.append((current, text[pos:m.start()].strip()))
        current = emotion(m.group(1), float(m.group(2)) if m.group(2) else INTENSITY)
        pos = m.end()
    if text[pos:].strip():
        out.append((current, text[pos:].strip()))
    return out


def apply(speaker, e: Emotion):
    """The speaker as it sounds with this emotion (pitch, range, rate, brightness, breath, tremor)."""
    if e == Emotion():
        return speaker
    return replace(speaker, pitch=round(speaker.pitch * 2 ** (e.pitch / 12), 2), range=speaker.range * e.range,
                   rate=speaker.rate * e.rate, tilt=round(speaker.tilt * 2 ** (e.tilt / 3), 1),
                   breath=speaker.breath + e.breath / 1.5, jitter=speaker.jitter + e.jitter,
                   whisper=max(speaker.whisper, 1.0 if e.breath >= 1 else 0.0))
