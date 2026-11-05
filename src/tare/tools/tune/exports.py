"""Validated Vorbis and audio-sprite output with authoritative decoded sample coordinates."""
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np

from .audio_io import trim_tail, write_wav
from .bundles import atomic_json, file_lock
from .diagnostics import digest, pcm_id


def write_ogg(path, audio: np.ndarray, sr: int, block: int = 65_536) -> None:
    """Ogg Vorbis, written in blocks: libsndfile 1.2.2 kills the process, with no error, when one write holds about
    20 s of stereo audio."""
    import soundfile as sf
    audio = np.asarray(audio, dtype=np.float32)
    with sf.SoundFile(str(path), "w", sr, 1 if audio.ndim == 1 else audio.shape[1], format="OGG",
                      subtype="VORBIS") as f:
        for start in range(0, len(audio), block):
            f.write(audio[start:start + block])


def _validate_export(path, identity):
    manifest = json.loads((path / "manifest.json").read_text())
    if manifest["bank_id"] != identity:
        raise ValueError("sprite identity mismatch")
    for name, expected in manifest["files"].items():
        if name not in ("bank.wav", "bank.ogg", "howler.json", "index.html") or \
                hashlib.sha256((path / name).read_bytes()).hexdigest() != expected:
            raise ValueError("sprite file integrity mismatch")


def looped(captured):
    """Whether a capture loops: its length is the loop, so its tail is never trimmed."""
    return any(n.get("loop") or n["kind"] == "voice" and n["params"].get("loop") for n in captured.manifest["nodes"])


def rings(captured):
    """Whether a capture rings out through a reverb or an echo (a Voice's `space`, a Score's `hall` or `echo`, a
    creature's by default): that tail is the sound, so it is never trimmed either."""
    return any(n["kind"] == "voice" and n["params"].get("space") or
               n["kind"] == "score" and (n["params"].get("hall") or n["params"].get("echo"))
               for n in captured.manifest["nodes"])


def export_sprite(sounds, out, *, ogg=False, gap=0.1, keep_tail=False):
    if not sounds or not np.isfinite(gap) or not 0 <= gap <= 10:
        raise ValueError("a bank needs sounds and a finite gap between 0 and 10 seconds")
    rate = next(iter(sounds.values())).sr
    if any(c.sr != rate for c in sounds.values()):
        raise ValueError("sprite inputs must have the same sample rate")
    if any(not len(c.audio) for c in sounds.values()):
        raise ValueError("sprite clips must have at least one sample")
    clips = {name: c.audio if keep_tail or looped(c) or rings(c) else trim_tail(c.audio, rate)
             for name, c in sounds.items()}
    total = sum(len(y) + round(gap * rate) for y in clips.values())
    if total / rate > 180:
        raise ValueError("sprite bank exceeds 180 seconds")
    samples = np.zeros((total, 2), dtype=np.float32)
    entries, sprite, offset = {}, {}, 0
    for name, captured in sounds.items():
        y, loop = clips[name], looped(captured)
        samples[offset:offset + len(y)] = y[:, None] if y.ndim == 1 else y
        cut = len(captured.audio) - len(y)
        entries[name] = {"start_sample": offset, "end_sample": offset + len(y), "frames": len(y),
                         "silence_cut_frames": cut, "loop": loop, "revision": captured.manifest["revision"],
                         "pcm_id": pcm_id(y, rate) if cut else captured.manifest["pcm_id"]}
        sprite[name] = [offset * 1000 / rate, len(y) * 1000 / rate] + ([True] if loop else [])
        offset += len(y) + round(gap * rate)
    padding = 4096 if ogg else 0
    identity = digest({"entries": entries, "rate": rate, "ogg": ogg, "gap": gap,
                       "codec_padding": padding, "format": "sprite-1"})
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    destination = out / identity
    if destination.exists():
        _validate_export(destination, identity)
        atomic_json(out / "current.json", {"revision": identity})
        return destination
    stage = Path(tempfile.mkdtemp(prefix=".sprite-", dir=out))
    try:
        write_wav(stage / "bank.wav", samples, rate)
        sources = ["bank.wav"]
        checks = []
        if ogg:
            try:
                import soundfile as sf
            except ImportError:
                raise ValueError("OGG export needs the export extra: pip install -e '.[export]'") from None
            encoded = np.pad(np.clip(samples, -1, 1), ((0, padding), (0, 0)))
            write_ogg(stage / "bank.ogg", encoded, rate)
            decoded, actual_rate = sf.read(str(stage / "bank.ogg"), dtype="float32", always_2d=True)
            if actual_rate != rate or decoded.shape != encoded.shape or not np.isfinite(decoded).all():
                raise ValueError("encoded Vorbis bank failed decoded rate/length/channel verification")
            checks.append({"codec": "Vorbis", "decoded_frames": len(decoded), "sample_rate": actual_rate,
                           "timing_tolerance_samples": 0, "scope": "decoded coordinates, not lossless audio"})
            sources.insert(0, "bank.ogg")
        import wave
        with wave.open(str(stage / "bank.wav")) as stream:
            if stream.getnframes() != total or stream.getnchannels() != 2 or stream.getframerate() != rate:
                raise ValueError("WAV bank failed independent header verification")
        atomic_json(stage / "howler.json", {"src": sources, "sprite": sprite})
        player = (Path(__file__).parent / "ui" / "sprite.html").read_bytes()
        (stage / "index.html").write_bytes(player)
        files = {name: hashlib.sha256((stage / name).read_bytes()).hexdigest()
                 for name in [*sources, "howler.json", "index.html"]}
        atomic_json(stage / "manifest.json", {"format": "tare.tools.tune.sprite", "version": 1,
                    "bank_id": identity, "encoding": {"peak_before_clip": float(np.max(np.abs(samples))),
                    "clipped_samples": int(np.sum(np.abs(samples) > 1)), "wav": "PCM16",
                    "ogg": "Vorbis" if ogg else None},
                    "sample_rate": rate, "channels": 2, "frames": total, "gap_samples": round(gap * rate),
                    "codec_padding_samples": {"bank.wav": 0, "bank.ogg": padding} if ogg else {"bank.wav": 0},
                    "entries": entries, "files": files, "checks": checks,
                    "loop_end": "exclusive", "browser_adapter": "Web Audio seconds from sample coordinates",
                    "browser_timing_tolerance_seconds": 0.002})
        _validate_export(stage, identity)
        with file_lock(out / ".exports.lock"):
            if not destination.exists():
                os.replace(stage, destination)
        atomic_json(out / "current.json", {"revision": identity})
        return destination
    finally:
        if stage.exists():
            assert stage.resolve().parent == out.resolve() and stage.name.startswith(".sprite-")
            shutil.rmtree(stage)
