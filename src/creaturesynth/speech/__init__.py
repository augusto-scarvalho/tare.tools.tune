"""Human speech by formant synthesis: Brazilian Portuguese ("pt") and English ("en").

    >>> from creaturesynth.speech import Speaker
    >>> guard = Speaker.preset("deep")
    >>> audio = guard.render("Alto lá! Quem vem?", lang="pt")
    >>> npc = Speaker.random(42)                 # a unique, repeatable voice per NPC
    >>> audio = npc.render("Welcome, traveler!", lang="en")

Text -> phonemes (g2p_pt rules / g2p_en CMUdict) -> timed targets + intonation (phonetics)
-> frame tracks in a SpeechProgram -> Klatt-style synthesiser (klatt).
"""
from dataclasses import dataclass, replace

import numpy as np

from .. import rng
from ..render import DEFAULT_SR, render
from ..spec import SpeechProgram, Voice
from . import g2p_en, g2p_pt
from .phonetics import FRAME_RATE, frames
from .units import transcription

LANGS = {"pt": g2p_pt, "en": g2p_en}


@dataclass(frozen=True)
class Speaker:
    pitch: float = 120.0      # average f0, Hz
    tract: float = 1.0        # formant scale: ~1.0 long adult tract, ~1.17 short adult, ~1.3 child
    range: float = 1.0        # intonation range (0 = monotone)
    rate: float = 1.0         # speaking rate
    breath: float = 0.05      # breathy voice
    whisper: float = 0.0      # 1 = whispered (no voicing)
    tilt: float = 3000.0      # source brightness (low-pass of the glottal pulse), Hz
    jitter: float = 0.12      # pitch wander, semitones
    rough: float = 0.0        # growl
    sub: float = 0.0          # subharmonics
    crush: float = 0.0        # bit crush (robots)
    drive: float = 0.0        # saturation
    space: float = 0.0        # reverb, seconds
    name: str = ""

    def phonemes(self, text: str, lang: str = "pt") -> str:
        return transcription(_frontend(lang).text_to_phrases(text))

    def speech(self, text: str, lang: str = "pt") -> SpeechProgram:
        g2p = _frontend(lang)
        phrases = g2p.text_to_phrases(text)
        if not phrases:
            raise ValueError("nothing to say")
        tracks = frames(phrases, lang, pitch=self.pitch, tract=self.tract, range_=self.range, rate=self.rate,
                        breath=self.breath)
        if self.whisper:
            av = np.asarray(tracks["av"])
            tracks["ah"] = [round(float(x), 4) for x in np.asarray(tracks["ah"]) + self.whisper * av * 0.9]
            tracks["av"] = [round(float(x), 4) for x in av * (1 - self.whisper)]
        return SpeechProgram(frames=tracks, frame_rate=FRAME_RATE, tilt=self.tilt, jitter=self.jitter,
                             rough=(self.rough, 32.0), sub=self.sub, text=text, lang=lang,
                             phonemes=transcription(phrases))

    def voice(self, text: str, lang: str = "pt", seed: int | None = None) -> Voice:
        seed = rng.seed32("speech", text, lang, repr(self)) if seed is None else seed
        return Voice(speech=[self.speech(text, lang)], crush=self.crush, drive=self.drive, space=self.space,
                     wet=0.18, seed=seed, meta={"speaker": self.name, "text": text, "lang": lang})

    def render(self, text: str, lang: str = "pt", sr: int = DEFAULT_SR) -> np.ndarray:
        return render(self.voice(text, lang), sr)

    def but(self, **changes) -> "Speaker":
        return replace(self, **changes)

    @classmethod
    def preset(cls, name: str) -> "Speaker":
        try:
            return replace(PRESETS[name], name=name)
        except KeyError:
            raise ValueError(f"unknown voice {name!r}; choose from {', '.join(PRESETS)}") from None

    @classmethod
    def random(cls, seed: int, name: str = "") -> "Speaker":
        """A human voice drawn from `seed`: same seed, same voice (one per NPC)."""
        def u(gene):
            return rng.uniform(rng.key(seed, gene))
        height = u("height")                   # 0 long tract / low voice .. 1 short tract / high voice
        return cls(pitch=round(85 * (250 / 85) ** (0.8 * height + 0.2 * u("pitch")), 1),
                   tract=round(0.95 + 0.25 * height + 0.04 * (u("tract") - 0.5), 3),
                   range=round(0.7 + 0.6 * u("range"), 2), rate=round(0.88 + 0.24 * u("rate"), 2),
                   breath=round(0.02 + 0.12 * u("breath"), 3), tilt=round(2200 + 2000 * u("tilt")),
                   jitter=round(0.06 + 0.2 * u("jitter"), 3), name=name or f"npc-{seed}")

    @classmethod
    def from_creature(cls, creature) -> "Speaker":
        """A talking creature: its size and temper shape a human-like voice."""
        s, a = creature.size, creature.aggression
        return cls(pitch=round(340 * (60 / 340) ** s, 1), tract=round(2 ** (0.9 * (0.5 - s)) * 1.08, 3),
                   rough=round(0.7 * max(0.0, a - 0.3), 3), sub=round(0.9 * max(0.0, a - 0.5), 3),
                   drive=round(3 * max(0.0, a - 0.4), 2), space=round(0.2 + 1.2 * s, 2),
                   range=round(1.3 - 0.5 * s, 2), name=creature.name or creature.archetype)


PRESETS: dict[str, Speaker] = {
    "default": Speaker(),
    "deep": Speaker(pitch=95, tract=0.95, range=0.9, tilt=2600),
    "high": Speaker(pitch=210, tract=1.17, breath=0.08, range=1.1),
    "child": Speaker(pitch=270, tract=1.3, breath=0.1, range=1.2, rate=0.95),
    "cute": Speaker(pitch=300, tract=1.32, breath=0.12, range=1.3, tilt=3800),
    "fairy": Speaker(pitch=330, tract=1.4, breath=0.15, range=1.3, rate=1.08, space=1.0, tilt=4200),
    "elder": Speaker(pitch=135, tract=1.02, jitter=0.5, breath=0.18, rate=0.85, range=0.8),
    "giant": Speaker(pitch=62, tract=0.76, rate=0.8, rough=0.25, sub=0.3, space=1.4, range=0.8, tilt=2200),
    "monster": Speaker(pitch=75, tract=0.8, rough=0.5, sub=0.7, drive=2.5, space=0.8, jitter=0.6, tilt=2500),
    "robot": Speaker(pitch=110, range=0.0, jitter=0.0, crush=0.45, tilt=6000),
    "whisper": Speaker(pitch=150, tract=1.1, whisper=1.0, range=0.6),
}


def _frontend(lang: str):
    try:
        return LANGS[lang]
    except KeyError:
        raise ValueError(f"unsupported language {lang!r}; choose from {', '.join(LANGS)}") from None


def say(text: str, voice: str | Speaker = "default", lang: str = "pt", sr: int = DEFAULT_SR) -> np.ndarray:
    speaker = Speaker.preset(voice) if isinstance(voice, str) else voice
    return speaker.render(text, lang, sr)


__all__ = ["LANGS", "PRESETS", "Speaker", "say"]
