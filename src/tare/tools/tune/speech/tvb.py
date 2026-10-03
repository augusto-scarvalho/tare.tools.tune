"""Voice banks as a plain binary file (.tvb), for the native vocoder (native/) in engines that cannot read numpy.

    from tare.tools.tune.speech import tvb
    tvb.export("pt/alex", "pt_alex.tvb")         # ~21 MB; the game ships it next to the extension

Layout (little-endian): b"TVB1", a uint32 with the length of a UTF-8 JSON header, the header, then its sections,
each zlib-compressed (Godot: PackedByteArray.decompress(size, FileAccess.COMPRESSION_DEFLATE)):

    {"format": "tare.tools.tune.tvb", "version": 1, "name": "pt/alex", "lang": "pt", "tract": 1.0, "pitch": 130.0,
     "frames": 554350, "bands": 64, "ap_bands": 5,
     "sections": [{"name": "f0",  "type": "float32", "size": ..., "packed": ...},     pitch per frame, Hz
                  {"name": "env", "type": "uint8 delta", ...},   frames x bands, 0.5 dB steps above -107.5 dB,
                                                                 each frame stored as its difference to the last
                  {"name": "ap",  "type": "uint8", ...}]}        frames x 5, aperiodicity x 255

Only the frames go in: what renders a planned line (concat.Spoken). Planning stays in Python, with the labels.
"""
import json
import struct
import zlib
from pathlib import Path

import numpy as np

from . import concat

MAGIC = b"TVB1"


def export(name: str, path: str | Path) -> Path:
    b = concat.bank(name)
    env = np.ascontiguousarray(b._env8, np.uint8)
    sections = {"f0": ("float32", np.ascontiguousarray(b.f0, "<f4")),         # stored as float16: exact
                "env": ("uint8 delta", np.diff(env, axis=0, prepend=np.zeros((1, env.shape[1]), np.uint8))),
                "ap": ("uint8", np.ascontiguousarray(np.round(b.ap * 255), np.uint8))}
    packed = {k: zlib.compress(a.tobytes()) for k, (_t, a) in sections.items()}   # level 9: as small, slower
    header = {"format": "tare.tools.tune.tvb", "version": 1, "name": b.name, "lang": b.meta["lang"],
              "tract": b.tract, "pitch": b.pitch, "frames": len(b.f0), "bands": int(env.shape[1]), "ap_bands": 5,
              "sections": [{"name": k, "type": t, "size": a.nbytes, "packed": len(packed[k])}
                           for k, (t, a) in sections.items()]}
    head = json.dumps(header).encode("utf-8")
    path = Path(path)
    with open(path, "wb") as f:
        f.write(MAGIC + struct.pack("<I", len(head)) + head)
        for k in sections:
            f.write(packed[k])
    return path


def read(path: str | Path) -> tuple[dict, dict[str, np.ndarray]]:
    """(header, {"f0", "env" (decoded), "ap"}), as an engine would read it."""
    data = Path(path).read_bytes()
    if data[:4] != MAGIC:
        raise ValueError(f"{path} is not a voice bank (.tvb)")
    (n,) = struct.unpack("<I", data[4:8])
    header, pos, out = json.loads(data[8:8 + n].decode("utf-8")), 8 + n, {}
    frames, bands = header["frames"], header["bands"]
    for s in header["sections"]:
        raw = zlib.decompress(data[pos:pos + s["packed"]])
        pos += s["packed"]
        if s["type"] == "float32":
            out[s["name"]] = np.frombuffer(raw, "<f4")
        elif s["type"] == "uint8 delta":
            out[s["name"]] = np.cumsum(np.frombuffer(raw, np.uint8).reshape(frames, bands), axis=0, dtype=np.uint8)
        else:
            out[s["name"]] = np.frombuffer(raw, np.uint8).reshape(frames, -1)
    return header, out
