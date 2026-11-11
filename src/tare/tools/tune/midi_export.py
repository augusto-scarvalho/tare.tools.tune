"""Explicit MIDI subset exported from recorded musical events, never inferred from audio."""
import struct
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .diagnostics import digest

PPQ = 960
PROGRAMS = {"harp": 46, "guitar": 24, "lute": 24, "pizzicato": 45, "marimba": 12,
            "glockenspiel": 9, "xylophone": 13, "celesta": 8, "music_box": 10,
            "tubular_bell": 14, "strings": 48, "cellos": 42, "flute": 73,
            "horn": 60, "trumpet": 56, "choir": 52, "bass": 33, "e_piano": 4,
            "pulse": 80, "square": 80, "thin_pulse": 80, "sine": 79, "spiccato": 48}
DRUMS = {"bass_drum": 36, "snare": 38, "hihat": 42, "open_hat": 46, "crash": 49,
         "tambourine": 54, "triangle": 81, "hand_drum": 64, "log_drum": 77, "taiko": 41, "gong": 51,
         "chip_kick": 36, "chip_snare": 38, "chip_hat": 42}


def vlq(value):
    if not 0 <= value <= 0x0fffffff:
        raise ValueError("MIDI delta exceeds the supported range")
    result = [value & 127]
    while value >> 7:
        value >>= 7
        result.insert(0, (value & 127) | 128)
    return bytes(result)


def chunk(kind, data):
    return kind + struct.pack(">I", len(data)) + data


def export_midi(score, path, *, approximate=False, programs=None, loop=None):
    programs = PROGRAMS | (programs or {})
    warnings = []
    if not np.isfinite(score.bpm) or not 4 <= score.bpm <= 1000 or \
            not isinstance(score.meter, int) or not 1 <= score.meter <= 255:
        raise ValueError("MIDI requires tempo 4..1000 BPM and a quarter-note meter of 1..255 beats")
    groups = {}
    for track in score.tracks.values():
        for event in track.events:
            if event.get("layer_hashes") != [digest(asdict(track.layers[i])) for i in event["layers"]
                                             if i < len(track.layers)]:
                raise ValueError("expanded layers changed after note recording; rebuild before MIDI export")
            if event["bpm"] != score.bpm:
                raise ValueError("Score tempo changed after note expansion; rebuild the score before MIDI export")
            pitch = event["pitch"]
            instrument = event["instrument"]
            if instrument not in programs and instrument not in DRUMS:
                if not approximate:
                    raise ValueError(f"MIDI instrument mapping required for {instrument!r}")
                warnings.append(f"{instrument}: approximated by GM piano")
            if pitch != round(pitch):
                if not approximate:
                    raise ValueError("fractional MIDI pitch requires approximation or an explicit bend/channel policy")
                warnings.append(f"{event['id']}: fractional pitch rounded")
            if any(getattr(track.layers[index], "bend", None) for index in event["layers"]):
                if not approximate:
                    raise ValueError("note bends require approximation in this MIDI subset")
                warnings.append(f"{event['id']}: synthesis bend omitted")
            key = DRUMS.get(instrument, int(round(pitch)))
            if not 0 <= key <= 127 or not 0 <= event["velocity"] <= 1:
                raise ValueError("MIDI pitch/velocity outside supported range")
            if event["velocity"] == 0:
                continue
            start, duration = event["offset"] + event["beat"], event["beats"]
            if start < 0 or duration <= 0:
                raise ValueError("MIDI events need nonnegative starts and positive held durations")
            if loop is not None:
                boundary = loop * score.bpm / 60
                if start >= boundary:
                    continue
                duration = min(duration, boundary - start)
            on, off = round(start * PPQ), round((start + duration) * PPQ)
            if off <= on:
                raise ValueError("note shorter than the MIDI tick resolution")
            group = groups.setdefault((track.name, instrument), [])
            if any(note[2] == key and on < note[1] and off > note[0] for note in group):
                raise ValueError("overlapping same-pitch notes require separate channels in this MIDI subset")
            group.append((on, off, key, max(1, round(event["velocity"] * 127))))
        covered = {index for event in track.events for index in event["layers"]}
        if len(covered) != len(track.layers):
            if not approximate:
                raise ValueError("direct synthesis layers have no MIDI event representation")
            warnings.append(f"{track.name}: direct synthesis layers omitted")
    if score.sounds:
        if not approximate:
            raise ValueError("placed audio has no MIDI representation; enable approximation to omit it")
        warnings.append("placed audio omitted")
    name = Path(path).stem.encode("utf-8")
    tempo = round(60_000_000 / score.bpm)
    meta = b"\0\xff\x03" + vlq(len(name)) + name + b"\0\xff\x51\x03" + tempo.to_bytes(3, "big")
    meta += b"\0\xff\x58\x04" + bytes([score.meter, 2, 24, 8]) + b"\0\xff\x2f\0"
    tracks = [chunk(b"MTrk", meta)]
    channels = iter([ch for ch in range(16) if ch != 9])
    percussion = {}
    for (track_name, instrument), notes in groups.items():
        if instrument in DRUMS:
            channel = 9
            for on, off, key, _ in notes:
                previous_notes = percussion.setdefault(key, [])
                if any(on < end and off > begin for begin, end in previous_notes):
                    raise ValueError("overlapping percussion notes share MIDI channel 10; separate or shorten them")
                previous_notes.append((on, off))
        else:
            channel = next(channels, None)
            if channel is None:
                raise ValueError("more than 15 melodic instrument groups need an explicit channel allocation")
        events = []
        if channel != 9:
            program = programs.get(instrument, 0)
            if not isinstance(program, int) or not 0 <= program <= 127:
                raise ValueError("GM programs must be integers 0..127")
            events.append((0, 0, bytes([0xc0 | channel, program])))
        for on, off, key, velocity in notes:
            events.extend([(on, 2, bytes([0x90 | channel, key, velocity])),
                           (off, 1, bytes([0x80 | channel, key, 0]))])
        label = f"{track_name}: {instrument}".encode()
        data = b"\0\xff\x03" + vlq(len(label)) + label
        previous = 0
        for at, _, message in sorted(events):
            data += vlq(at - previous) + message
            previous = at
        data += b"\0\xff\x2f\0"
        tracks.append(chunk(b"MTrk", data))
    output = chunk(b"MThd", struct.pack(">HHH", 1, len(tracks), PPQ)) + b"".join(tracks)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(output)
    return {"file": str(path), "tick_resolution": PPQ, "beat_unit": "quarter_note", "meter": [score.meter, 4],
            "tracks": len(groups), "warnings": sorted(set(warnings)),
            "scope": "note timing/pitch/velocity and GM approximation; synthesis timbre/effects are not embedded"}
