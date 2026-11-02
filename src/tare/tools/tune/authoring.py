"""Declarative authoring files used by one-shot builds and the live player."""
import hashlib
import json
from pathlib import Path

from .diagnostics import capture, digest


def materialize(document, sr=48000, base=Path(".")):
    from . import Creature, Sfx, Voice
    from .audio_io import read_channels
    from .music import Cue
    from .patterns import parse_pattern
    from .score import Score
    from .speech import speaker_from

    kind = document.get("type", "voice")
    if kind == "voice":
        return Voice.from_dict(document.get("spec", document)), None
    if kind in ("sfx", "creature"):
        options = dict(document.get("options", {}))
        obj = Sfx(document["kind"], document.get("style"), **options) if kind == "sfx" \
            else Creature(document["archetype"], **options)
        return obj.voice(document.get("event", "idle" if kind == "creature" else obj.events[0]),
                         take=document.get("take", 0)), None
    if kind == "speech":
        voice = speaker_from(document.get("voice", "default"))
        return voice.voice(document["text"], lang=document.get("lang", "en")), None
    if kind == "music":
        cue = Cue(document["kind"], style=document.get("style", "orchestral"), seed=document.get("seed", 0), sr=sr)
        return cue, None
    if kind == "score":
        settings = dict(document.get("settings", {}))
        settings["sr"] = sr
        score = Score(**settings)
        tracks = document.get("tracks", [])
        if len(tracks) > 64:
            raise ValueError("project supports at most 64 tracks")
        for entry in tracks:
            entry = dict(entry)
            instrument, name = entry.pop("instrument"), entry.pop("name")
            notes = entry.pop("notes", None)
            if notes is None:
                notes, _ = parse_pattern(entry.pop("pattern"), meter=score.meter,
                                         steps_per_beat=entry.pop("steps", 4))
            if len(notes) > 512:
                raise ValueError("project supports at most 512 notes per track")
            score.track(name, **entry).play(instrument, notes)
        return score, score.bar(document["bars"]) if document.get("bars") else None
    if kind == "audio":
        y, actual = read_channels(base / document["file"])
        if actual != sr:
            raise ValueError("imported audio sample rate must match the project")
        return y, None
    if kind == "fm":
        from .effects import fm_tone
        return fm_tone(sr=sr, **document.get("options", {})), None
    raise ValueError(f"unknown project source type: {kind}")


def build_file(path, *, sr=None, name=None, asset_roots=()):
    path = Path(path).resolve()
    raw = path.read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError("project file exceeds 1 MiB")
    document = json.loads(raw)
    if isinstance(document, dict) and document.get("format") == "tare.tools.tune.dsl":
        from .dsl.compiler import build_file as build_dsl
        return build_dsl(path, sr=sr, name=name, asset_roots=asset_roots)
    if not isinstance(document, dict):
        raise ValueError("project must be a JSON object")
    rate = int(sr or document.get("sample_rate", 48000))
    if not 1000 <= rate <= 192000:
        raise ValueError("project sample rate must be 1000..192000 Hz")
    source = document.get("source", document)
    pointer = "/source" if "source" in document else ""
    if document.get("sounds") is not None:
        if name is None or name not in document["sounds"]:
            raise ValueError("choose a project sound with --name")
        source = document["sounds"][name]
        pointer = "/sounds/" + name.replace("~", "~0").replace("/", "~1")
    source_json = source
    source, loop = materialize(source, rate, path.parent)
    if hasattr(source, "tracks"):
        for index, entry in enumerate(source_json.get("tracks", [])):
            track = source.tracks[entry["name"]]
            location = {"file": str(path), "json_pointer": f"{pointer}/tracks/{index}/" +
                        ("pattern" if "pattern" in entry else "notes")}
            for event in track.events:
                event["project"] = location
            for item in track.origins:
                item["project"] = location
    result = capture(source, rate, loop=loop)
    for node in result.manifest["nodes"]:
        for part in node["parts"]:
            if not part.get("origin"):
                part["origin"] = {"project": {"file": str(path), "json_pointer": pointer},
                                   "definition": part["label"]}
    if document.get("reference"):
        from .audio_io import read_channels
        from .diagnostics import pcm_id
        reference, reference_rate = read_channels(path.parent / document["reference"]["file"])
        if result.manifest["limits"]["bytes"] < sum(a.nbytes for a in result.arrays.values()) + reference.nbytes:
            raise ValueError("reference exceeds capture memory limit")
        result.arrays["reference"] = reference
        result.manifest["buffers"]["reference"] = {"dtype": reference.dtype.str, "shape": list(reference.shape),
            "sha256": hashlib.sha256(reference.tobytes()).hexdigest()}
        result.manifest["reference"] = {"sample_rate": reference_rate, "pcm_id": pcm_id(reference, reference_rate)}
    result.manifest["project"] = {"path": str(path), "content": document, "sound": name}
    result.manifest["source_id"] = digest({"definition": result.manifest["source"],
                                           "project": result.manifest["project"]})
    result.manifest["render_id"] = digest({"capture": result.manifest["render_id"],
                                           "source": result.manifest["source_id"]})
    result.manifest["revision"] = digest({k: v for k, v in result.manifest.items() if k != "revision"})
    return result
