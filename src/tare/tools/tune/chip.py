"""Game Boy cry engine: 2 pulse channels + noise, as used by Pokemon Red/Blue cries.

Runs at the Game Boy's native 1,048,576 Hz (vectorised per note) and decimates with a
polyphase anti-aliasing filter. Verified against the original web app's TypeScript engine
for all 151 cries (see tests/test_chip.py).
"""
import json
import os
from functools import cache, lru_cache
from math import gcd
from pathlib import Path

import numpy as np
from scipy.signal import firwin, resample_poly

from .spec import ChipProgram, Voice

GB_RATE = 1_048_576
FRAME = 17_556           # samples per video frame (~59.7 Hz): envelope and duty clock
MAX_NOTE = 2_500_000     # cap for a last note that never fades out (same as the original)

_DUTY = np.zeros((4, 8), dtype=bool)   # 4 duty patterns x 8 steps
_DUTY[0, 4] = True
_DUTY[1, 4:6] = True
_DUTY[2, 2:6] = True
_DUTY[3] = ~_DUTY[1]


def _note_samples(note_len: int, length: int, leftovers: int) -> tuple[int, int]:
    subframes = (length + 0x100) * (note_len + 1) + leftovers
    return FRAME * (subframes >> 8), subframes & 0xFF


def _envelope(volume: int, fade: int, n: int) -> np.ndarray:
    """4-bit volume stepped every |fade| frames (negative fade rises)."""
    if fade == 0:
        return np.full(n, volume)
    steps = np.arange(n) // (FRAME * abs(fade))
    return np.clip(volume + (1 if fade < 0 else -1) * steps, 0, 15)


def _run_length(volume: int, fade: int, count: int, is_last: bool) -> int:
    """Samples a note plays for: the last note keeps sounding until it fades out."""
    if not is_last or (volume == 0 and fade >= 0):
        return min(count, MAX_NOTE)
    if fade == 0:
        return MAX_NOTE
    if fade < 0:
        return min(count, MAX_NOTE) if volume == 0 and count < FRAME * -fade else MAX_NOTE
    return min(max(count, volume * FRAME * fade), MAX_NOTE)


def _out(bits: np.ndarray, volume: np.ndarray) -> np.ndarray:
    return (2.0 * bits - 1.0) * (-volume / 16.0)


def _rotate(duty: int, times: int) -> int:
    for _ in range(times % 4):
        duty = ((duty & 0x3F) << 2) | ((duty & 0xC0) >> 6)
    return duty


def pulse_channel(commands: list[dict], pitch: int, length: int) -> np.ndarray:
    chunks, duty, phase, pos, leftovers = [], 0, 0.0, 0, 0
    for k, cmd in enumerate(commands):
        if "duty" in cmd:
            duty = cmd["duty"]
            continue
        note_len, volume, fade, freq = cmd["note"]
        count, leftovers = _note_samples(note_len, length, leftovers)
        n = _run_length(volume, fade, count, k == len(commands) - 1)
        g = pos + np.arange(n)
        # the duty byte rotates left 2 bits at every frame boundary inside the note
        rot = np.minimum(g, pos + count) // FRAME - pos // FRAME
        low2 = (duty >> (2 * ((4 - rot % 4) % 4))) & 3
        period = 8 * (2048 - ((freq + pitch) & 0x7FF))
        steps = (((phase + np.arange(n) / period) % 1.0) * 8).astype(np.int64)
        chunks.append(_out(_DUTY[low2, steps], _envelope(volume, fade, n)))
        duty = _rotate(duty, (pos + min(n, count)) // FRAME - pos // FRAME)
        phase = (phase + n / period) % 1.0
        pos += n
    return np.concatenate(chunks) if chunks else np.zeros(0)


@cache
def _lfsr_cycle(short: bool, legacy: bool) -> tuple[np.ndarray, int, int]:
    """Output bits from reset (0x7FFF) until the state repeats: (bits, mu, lam)."""
    reg, seen, bits = 0x7FFF, {}, []
    while reg not in seen:
        seen[reg] = len(bits)
        bits.append(reg & 1)
        x = (reg ^ (reg >> 1)) & 1
        reg = (reg >> 1) | (x << 14)
        if short:
            # hardware also writes the feedback into bit 6; the old web app shifted twice instead
            reg = ((reg >> 1) | (x << 6)) if legacy else ((reg & ~0x40) | (x << 6))
    mu = seen[reg]
    return np.array(bits, dtype=np.int8), mu, len(bits) - mu


def _lfsr_bits(clocks: np.ndarray, short: bool, legacy: bool) -> np.ndarray:
    bits, mu, lam = _lfsr_cycle(short, legacy)
    return bits[np.where(clocks < mu, clocks, mu + (clocks - mu) % lam)]


def noise_channel(commands: list[dict], pitch: int, cutoff: int, legacy: bool = False) -> np.ndarray:
    chunks, pos, leftovers = [], 0, 0
    for k, cmd in enumerate(commands):
        note_len, volume, fade, param = cmd["note"]
        count, leftovers = _note_samples(note_len, 0, leftovers)  # noise ignores the tempo
        n = _run_length(volume, fade, count, k == len(commands) - 1)
        param = (param + (0 if pos >= cutoff else pitch)) & 0xFF   # pitch shift ends with the pulses
        shift = (param >> 4) & 0xF
        shift = shift & 0xD if shift > 0xD else shift
        divider = param & 7
        clock = int(2 * (divider or 0.5) * (1 << (shift + 1)))
        g = pos + np.arange(n)
        bits = _lfsr_bits(g // clock - pos // clock, bool(param & 8), legacy)
        chunks.append(_out(1 - bits, _envelope(volume, fade, n)))
        pos += n
    return np.concatenate(chunks) if chunks else np.zeros(0)


def channels(p: ChipProgram) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Raw 1 MHz channels (pulse1, pulse2, noise)."""
    def nominal(cmds):
        total, left = 0, 0
        for c in cmds:
            if "note" in c:
                s, left = _note_samples(c["note"][0], p.length, left)
                total += s
        return total
    cutoff = max(nominal(p.pulse1), nominal(p.pulse2)) - FRAME
    return (pulse_channel(p.pulse1, p.pitch, p.length),
            pulse_channel(p.pulse2, p.pitch, p.length),
            noise_channel(p.noise, p.pitch, cutoff, legacy=not p.hardware_noise))


def program_duration(p: ChipProgram) -> float:
    """Seconds the program sounds for, without rendering it."""
    def samples(cmds, length):
        total, left = 0, 0
        for k, c in enumerate(cmds):
            if "note" in c:
                count, left = _note_samples(c["note"][0], length, left)
                total += _run_length(c["note"][1], c["note"][2], count, k == len(cmds) - 1)
        return total
    return max(samples(p.pulse1, p.length), samples(p.pulse2, p.length), samples(p.noise, 0)) / GB_RATE


@lru_cache(maxsize=16)
def _antialias(up: int, down: int) -> np.ndarray:
    """scipy's default resample_poly filter, designed once per ratio."""
    m = max(up, down)
    return firwin(20 * m + 1, 1.0 / m, window=("kaiser", 5.0))  # resample_poly applies the gain


def _resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    g = gcd(src, dst)
    up, down = dst // g, src // g
    return resample_poly(x, up, down, window=_antialias(up, down).copy())  # never let scipy touch the cache


def render_program(p: ChipProgram, sr: int) -> np.ndarray:
    chans = channels(p)
    mix = np.zeros(max(len(c) for c in chans))
    for c in chans:
        mix[: len(c)] += c / 3
    # two stages keep the filters short at any output rate (44.1 kHz shares only a factor 4 with 2^20)
    return _resample(_resample(mix, GB_RATE, GB_RATE // 16), GB_RATE // 16, sr)


# --- Gen 1 data (third-party game data: kept in the repo for reference, not in the package) ---

def _default_data_path() -> Path:
    env = os.environ.get("TARE_TOOLS_TUNE_GEN1_DATA")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[4] / "data" / "gen1" / "cries.json"


@lru_cache(maxsize=4)
def load_gen1(path: str | None = None) -> dict:
    p = Path(path) if path else _default_data_path()
    if not p.exists():
        raise FileNotFoundError(
            f"Gen 1 cry data not found at {p}. It lives in the repository (data/gen1/cries.json); "
            "point TARE_TOOLS_TUNE_GEN1_DATA at it when running from an installed package.")
    return json.loads(p.read_text(encoding="utf-8"))


def gen1_species(name_or_number: str | int, path: str | None = None) -> dict:
    species = load_gen1(path)["species"]
    if isinstance(name_or_number, int) or str(name_or_number).isdigit():
        return species[int(name_or_number) - 1]  # Pokedex numbers start at 1
    for s in species:
        if s["name"].lower() == str(name_or_number).lower():
            return s
    raise ValueError(f"unknown Gen 1 species {name_or_number!r}")


def gen1_program(name_or_number: str | int, path: str | None = None, hardware_noise: bool = True) -> ChipProgram:
    s = gen1_species(name_or_number, path)
    cry = load_gen1(path)["cry_types"][s["cry"]]
    return ChipProgram(pulse1=cry["pulse1"], pulse2=cry["pulse2"], noise=cry["noise"],
                       pitch=s["pitch"], length=s["length"] - 0x80, hardware_noise=hardware_noise)


def gen1_voice(name_or_number: str | int, path: str | None = None, hardware_noise: bool = True) -> Voice:
    s = gen1_species(name_or_number, path)
    return Voice(chips=[gen1_program(name_or_number, path, hardware_noise)],
                 meta={"source": "gen1", "name": s["name"]})
