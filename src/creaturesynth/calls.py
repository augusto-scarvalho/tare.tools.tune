"""Traits (who is calling) and calls (why it is calling).

A game creature needs a family of sounds that share one identity: the same wolf idles,
alerts, attacks, gets hurt and dies. Calls are modifiers every archetype understands.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Traits:
    size: float = 0.5          # 0 tiny .. 1 huge: pitch, formants, duration, reverb
    aggression: float = 0.3    # 0 calm .. 1 furious: roughness, subharmonics, distortion


@dataclass(frozen=True)
class Call:
    name: str
    intensity: float           # 0..1: loudness and effort
    aggression: float = 0.0    # added to the creature's aggression
    pitch: float = 0.0         # semitones
    bend: float = 0.0          # semitones reached by the end of each syllable (contour tilt)
    duration: float = 1.0      # duration multiplier
    repeats: int = 0           # syllable count override (0 = archetype decides)
    attack: float = 1.0        # attack-time multiplier


CALLS: dict[str, Call] = {c.name: c for c in [
    Call("idle", intensity=0.35, aggression=-0.25, duration=0.85, attack=1.6),
    Call("alert", intensity=0.7, aggression=0.05, pitch=3.0, bend=3.0, duration=0.65, repeats=2, attack=0.6),
    Call("attack", intensity=1.0, aggression=0.45, pitch=-1.0, bend=-2.0, duration=1.15, repeats=1, attack=0.5),
    Call("hurt", intensity=0.85, aggression=0.2, pitch=6.0, bend=-6.0, duration=0.45, repeats=1, attack=0.2),
    Call("death", intensity=0.6, aggression=0.0, pitch=1.0, bend=-12.0, duration=2.0, repeats=1, attack=1.2),
]}


def get_call(call: "str | Call") -> Call:
    if isinstance(call, Call):
        return call
    try:
        return CALLS[call]
    except KeyError:
        raise ValueError(f"unknown call {call!r}; choose from {', '.join(CALLS)}") from None
