"""WAV I/O (stdlib only) and PCM helpers for game engines and audio libraries."""
import struct
import wave
from pathlib import Path

import numpy as np


def to_pcm16(audio: np.ndarray) -> bytes:
    return (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def write_wav(path: str | Path, audio: np.ndarray, sr: int, loop: bool = False) -> Path:
    """Mono samples, or stereo as shape (n, 2) (a Score's render), to a 16-bit WAV. `loop`: the whole file is a
    seamless loop: a sampler chunk says so, and engines that read it (Godot's "Detect From WAV", samplers, Wwise,
    FMOD) loop it from the first sample to the last with no setup."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1 if audio.ndim == 1 else audio.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(to_pcm16(audio))
    if loop:
        _add_loop(path, len(audio), sr)
    return path


def _add_loop(path: Path, frames: int, sr: int) -> None:
    """Append a 'smpl' chunk with one forward loop over every frame, and fix the RIFF size."""
    chunk = struct.pack("<9I", 0, 0, round(1e9 / sr), 60, 0, 0, 0, 1, 0)       # maker, product, period ns, note...
    chunk += struct.pack("<6I", 0, 0, 0, frames - 1, 0, 0)                     # id, forward, start, end (inclusive)
    with open(path, "r+b") as f:
        f.seek(0, 2)
        f.write(b"smpl" + struct.pack("<I", len(chunk)) + chunk)
        size = f.tell()
        f.seek(4)
        f.write(struct.pack("<I", size - 8))


def wav_loop(path: str | Path) -> tuple[int, int] | None:
    """The first loop (start, end frame, inclusive) a WAV's sampler chunk declares, if any."""
    data = Path(path).read_bytes()
    i = 12
    while i + 8 <= len(data):
        tag, size = data[i:i + 4], struct.unpack("<I", data[i + 4:i + 8])[0]
        if tag == b"smpl" and size >= 60 and struct.unpack("<I", data[i + 36:i + 40])[0] >= 1:
            start, end = struct.unpack("<2I", data[i + 52:i + 60])
            return start, end
        i += 8 + size + (size & 1)
    return None


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError("only mono 16-bit WAV is supported")
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
        return data.astype(np.float32) / 32767, w.getframerate()


def load_audio(path: str | Path) -> tuple[np.ndarray, int]:
    """Any mono/stereo WAV (16-bit via the stdlib) or, with soundfile installed, FLAC/OGG/etc. Mixed to mono."""
    try:
        return read_wav(path)
    except (ValueError, wave.Error):
        pass
    try:
        import soundfile
    except ImportError:
        raise ValueError(f"{path}: only mono 16-bit WAV without soundfile (pip install soundfile)") from None
    data, sr = soundfile.read(str(path), dtype="float32", always_2d=True)
    return data.mean(axis=1), sr
