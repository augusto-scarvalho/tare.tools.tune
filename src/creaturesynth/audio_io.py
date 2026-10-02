"""WAV I/O (stdlib only) and PCM helpers for game engines and audio libraries."""
import wave
from pathlib import Path

import numpy as np


def to_pcm16(audio: np.ndarray) -> bytes:
    return (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def write_wav(path: str | Path, audio: np.ndarray, sr: int) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(to_pcm16(audio))
    return path


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
