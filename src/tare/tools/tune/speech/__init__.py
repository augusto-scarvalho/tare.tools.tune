"""Human speech: Brazilian Portuguese ("pt") and English ("en"), with two engines.

    >>> from tare.tools.tune.speech import Speaker
    >>> guard = Speaker.preset("deep")
    >>> audio = guard.render("Alto lá! Quem vem?", lang="pt")
    >>> npc = Speaker.random(42)                 # a unique, repeatable voice per NPC
    >>> audio = npc.render("Welcome, traveler!", lang="en")
    >>> king = Speaker(pitch=105, tract=0.97, engine="natural")
    >>> audio = king.render("Bem-vindo ao meu reino.", lang="pt")

Text -> phonemes (g2p_pt rules / g2p_en CMUdict) -> timed targets + intonation (phonetics), then
    formant   frame tracks in a SpeechProgram -> Klatt-style synthesiser (klatt)
    natural   pieces of a voice bank (a teacher's analysed recordings) -> our vocoder (concat, vocoder)
Both are deterministic and procedural at run time; nothing neural runs in either.
"""
from dataclasses import dataclass, replace

import numpy as np

from .. import rng
from ..render import DEFAULT_SR, render
from ..spec import SpeechProgram, Spoken, Voice
from . import babble, g2p_en, g2p_pt
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
    engine: str = "formant"   # "formant" (Klatt rules: light, babbles, any voice) or "natural" (a voice bank)
    bank: str = ""            # natural: "pt/alex", "pt/dora"... ("" = the bank nearest this vocal tract)

    def phonemes(self, text: str, lang: str = "pt") -> str:
        return transcription(_frontend(lang).text_to_phrases(text))

    def _plan(self, text: str, lang: str, style: str):
        from .emotion import TAG
        g2p = _frontend(lang)
        phrases = g2p.text_to_phrases(TAG.sub(" ", text))           # emotion tags are handled by voice()
        if not phrases:
            raise ValueError("nothing to say")
        if style not in babble.STYLES:
            raise ValueError(f"unknown style {style!r}; choose from {', '.join(babble.STYLES)}")
        seed = rng.seed32("babble", text, self.name)
        pitch, rate, range_, notes = self.pitch, self.rate, self.range, None
        if style == "gibberish":
            phrases = babble.gibberish(phrases, lang, seed)
        elif style == "mumble":
            phrases = babble.mumble(phrases)
        elif style == "animalese":  # fast, high and sing-song
            pitch, rate, range_ = pitch * 1.5, rate * 2.2, range_ * 0.5
            notes = babble.melody(phrases, seed)
        return phrases, pitch, rate, range_, notes

    def natural(self, lang: str) -> bool:
        """Whether this voice speaks `lang` with the natural engine (there is a voice bank for it)."""
        from . import concat
        return self.engine == "natural" and bool(concat.banks(lang))

    def speech(self, text: str, lang: str = "pt", style: str = "speech") -> SpeechProgram:
        """The formant engine's program. `style`: "speech" (the words), or non-verbal "gibberish", "animalese",
        "mumble" (see babble.py)."""
        phrases, pitch, rate, range_, notes = self._plan(text, lang, style)
        tracks = frames(phrases, lang, pitch=pitch, tract=self.tract, range_=range_, rate=rate,
                        breath=max(self.breath, 0.0), melody=notes)
        if self.whisper:
            av = np.asarray(tracks["av"])
            tracks["ah"] = [round(float(x), 4) for x in np.asarray(tracks["ah"]) + self.whisper * av * 0.9]
            tracks["av"] = [round(float(x), 4) for x in av * (1 - self.whisper)]
        return SpeechProgram(frames=tracks, frame_rate=FRAME_RATE, tilt=self.tilt, jitter=self.jitter,
                             rough=(self.rough, 32.0), sub=self.sub, text=text, lang=lang,
                             phonemes=transcription(phrases))

    def spoken(self, text: str, lang: str = "pt", style: str = "speech", final: float = 0.0,
               pause: float = 1.0) -> Spoken:
        """The natural engine's layer: pieces of the nearest voice bank, our timing and intonation, this voice.
        `final`: semitones at the end of statements; `pause`: x the pauses between phrases (see emotion.py)."""
        from . import concat
        phrases, pitch, rate, range_, notes = self._plan(text, lang, style)
        name = self.bank if self.bank.startswith(lang + "/") else concat.closest(lang, self.tract)
        b = concat.bank(name)
        parts, joins, f0, phones = concat.plan(phrases, lang, name, pitch, range_, rate, notes, jitter=self.jitter,
                                               seed=rng.seed32("spoken", text, repr(self)), final=final, pause=pause)
        return Spoken(name, parts, joins, f0, warp=round(float(np.clip(self.tract / b.tract, 0.75, 1.35)), 4),
                      breath=round(float(np.clip(max(1.5 * (self.breath - 0.05), self.whisper or -1.0), -1, 1)), 4),
                      tilt=round(3 * float(np.log2(self.tilt / 3000)), 3), text=text, lang=lang, phonemes=phones)

    def voice(self, text: str, lang: str = "pt", seed: int | None = None, style: str = "speech",
              emotion=None) -> Voice:
        """The spec of a line. `emotion` ("alegria", "raiva", "tristeza", "medo", "surpresa", "sussurro"...; see
        emotion.py) colours all of it; [emotion] or [emotion:0.5] tags in the text change it as the line goes on."""
        from .emotion import apply, split
        seed = rng.seed32("speech", text, lang, repr(self), style, str(emotion)) if seed is None else seed
        segments = split(text, emotion)
        if not segments:
            raise ValueError("nothing to say")
        natural, layers, start = self.natural(lang), [], 0.0
        for e, part in segments:           # one layer per stretch of feeling, one after the other
            spk = apply(self, e)
            layer = spk.spoken(part, lang, style, e.final, e.pause) if natural else spk.speech(part, lang, style)
            layer.start = round(start, 4)
            start += layer.duration + (0.3 * e.pause if part[-1] in ".!?…" else 0.05)
            layers.append(layer)
        return Voice(**{"spoken" if natural else "speech": layers}, crush=self.crush, drive=self.drive,
                     space=self.space, wet=0.18, seed=seed,
                     meta={"speaker": self.name, "text": text, "lang": lang, "style": style, "engine": self.engine,
                           **({"emotion": str(emotion)} if emotion else {})})

    def render(self, text: str, lang: str = "pt", sr: int = DEFAULT_SR, style: str = "speech",
               emotion=None) -> np.ndarray:
        return render(self.voice(text, lang, style=style, emotion=emotion), sr)

    def emote(self, kind: str, style: str = "grunt", intensity: float = 0.7, take: int = 0,
              sr: int = DEFAULT_SR) -> np.ndarray:
        """A wordless bark in this voice: "attack", "hurt", "death", "jump", "laugh", "sigh", "hmm", "cheer"... (see
        emote.EMOTES), in a style: "grunt", "anime", "tactics", "mmo", "gasp", "kiai". Each `take` is a little
        different."""
        return render(self.emote_voice(kind, style, intensity, take), sr)

    def emote_voice(self, kind: str, style: str = "grunt", intensity: float = 0.7, take: int = 0) -> Voice:
        from .emote import emote
        seed = rng.seed32("emote", kind, style, repr(self), take)
        return Voice(vocoded=[emote(self, kind, style, intensity, take)], crush=self.crush, drive=self.drive,
                     space=self.space, wet=0.18, seed=seed,
                     meta={"speaker": self.name, "emote": kind, "style": style, "intensity": intensity})

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


KOKORO_GENDER = {"pm_alex": ("pt/alex", "m"), "pf_dora": ("pt/dora", "f"), "pm_santa": ("pt/alex", "m")}


def natural(gender: str = "m", bank: str = "", name: str = "") -> Speaker:
    """A natural-engine voice: a man's (gender "m") or a woman's ("f") register, or a given bank's own voice."""
    if bank:
        from . import concat
        b = concat.bank(bank)
        return Speaker(pitch=b.pitch, tract=b.tract, engine="natural", bank=bank, name=name or bank)
    # near the banks' own voices: moving far above them thins the sound (measured on pt/dora: 173 Hz -> 210 Hz costs
    # ~0.4 of predicted naturalness)
    return Speaker(pitch=120.0 if gender == "m" else 180.0, tract=1.0 if gender == "m" else 1.15,
                   engine="natural", name=name)


def speaker_from(voice) -> Speaker:
    """Resolve a voice description: a Speaker, a preset name, "npc:<seed>", "natural[:m|f|<bank>]", or a dict
    ({"preset": ..., overrides}). The old "kokoro[:<voice id>]" names map to natural voices of the same register."""
    if isinstance(voice, Speaker):
        return voice
    if isinstance(voice, dict):
        voice = dict(voice)
        engine = voice.pop("engine", "formant")
        if engine == "kokoro":
            return speaker_from(f"kokoro:{voice.get('voice', '')}")
        base = Speaker.preset(voice.pop("preset")) if "preset" in voice else Speaker()
        return base.but(**voice, **({"engine": engine} if engine != "formant" else {}))
    voice = str(voice)
    if voice.startswith("npc:"):
        return Speaker.random(int(voice[4:]))
    kind, _, arg = voice.partition(":")
    if kind == "natural":
        return natural(arg) if arg in ("", "m", "f") else natural(bank=arg)
    if kind == "kokoro":
        if arg in KOKORO_GENDER:
            return natural(bank=KOKORO_GENDER[arg][0])
        return natural("f" if arg[1:2] == "f" or not arg else "m")
    return Speaker.preset(voice)


def say(text: str, voice="default", lang: str = "pt", sr: int = DEFAULT_SR) -> np.ndarray:
    return speaker_from(voice).render(text, lang, sr)


__all__ = ["LANGS", "PRESETS", "Speaker", "natural", "say", "speaker_from"]
