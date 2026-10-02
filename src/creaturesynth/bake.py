"""Offline use: a bestiary file -> WAV packs + manifest, ready to import into any engine.

Bestiary format (JSON)::

    {
      "sample_rate": 48000, "takes": 4, "calls": ["idle", "alert", "attack", "hurt", "death"],
      "creatures": {
        "wolf":      {"archetype": "mammal", "species": "wolf", "size": 0.45, "aggression": 0.5},
        "dire_wolf": {"extends": "wolf", "size": 0.85, "aggression": 0.8},
        "mystery":   {"random": 42}
      }
    }

``species`` may be a number or any string (hashed). ``extends`` inherits from another entry
(evolutions, variants). ``random`` draws a whole new creature from a seed.
"""
import json
import os
from collections.abc import Iterable, Mapping
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from . import __version__, rng
from .audio_io import write_wav
from .calls import CALLS
from .creature import Creature
from .render import DEFAULT_SR, render

MANIFEST = "manifest.json"


def creature_from_entry(name: str, entry: Mapping, entries: Mapping[str, Mapping], _seen=()) -> Creature:
    if name in _seen:
        raise ValueError(f"circular 'extends' involving {name!r}")
    entry = dict(entry)
    if "random" in entry:
        base = Creature.random(int(entry.pop("random")), entry.pop("archetype", None)).to_dict()
    elif "extends" in entry:
        parent = entry.pop("extends")
        if parent not in entries:
            raise ValueError(f"{name!r} extends unknown creature {parent!r}")
        base = creature_from_entry(parent, entries[parent], entries, (*_seen, name)).to_dict()
    else:
        base = {}
    base.update(entry)
    if isinstance(base.get("species"), str):
        base["species"] = rng.seed32(base["species"])
    base["name"] = name
    try:
        return Creature.from_dict(base)
    except TypeError as e:  # unknown field in the bestiary entry
        raise ValueError(f"creature {name!r}: {e}") from None


def load_bestiary(source: str | Path | Mapping) -> tuple[dict[str, Creature], dict]:
    """Returns (creatures by name, settings)."""
    data = source if isinstance(source, Mapping) else json.loads(Path(source).read_text())
    entries = data.get("creatures", {})
    creatures = {name: creature_from_entry(name, e, entries) for name, e in entries.items()}
    settings = {k: data[k] for k in ("sample_rate", "takes", "calls") if k in data}
    return creatures, settings


def _bake_one(job):
    name, creature, call, take, sr, out_dir, specs = job
    stem = f"{name}/{call}_{take:02d}"
    voice = creature.voice(call, take)
    audio = render(voice, sr)
    write_wav(Path(out_dir) / f"{stem}.wav", audio, sr)
    entry = {"file": f"{stem}.wav", "duration": round(len(audio) / sr, 4),
             "peak": round(float(np.max(np.abs(audio))), 4)}
    if specs:
        (Path(out_dir) / f"{stem}.json").write_text(voice.to_json(indent=1))
        entry["spec"] = f"{stem}.json"
    return name, call, take, entry


def bake(creatures: Mapping[str, Creature], out_dir: str | Path, calls: Iterable[str] | None = None,
         takes: int = 4, sr: int = DEFAULT_SR, specs: bool = True, workers: int | None = None) -> dict:
    """Render every creature x call x take to ``out_dir`` and write ``manifest.json``."""
    out_dir = Path(out_dir)
    calls = list(calls or CALLS)
    for call in calls:
        if call not in CALLS:
            raise ValueError(f"unknown call {call!r}")
    jobs = [(name, c, call, take, sr, str(out_dir), specs)
            for name, c in creatures.items() for call in calls for take in range(takes)]
    workers = workers or min(os.cpu_count() or 1, 8)
    if workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(workers) as pool:
            results = list(pool.map(_bake_one, jobs))
    else:
        results = [_bake_one(j) for j in jobs]

    manifest = {"format": "creaturesynth.bake", "version": 1, "generator": f"creaturesynth {__version__}",
                "sample_rate": sr, "takes": takes, "calls": calls,
                "creatures": {name: {"creature": c.to_dict(), "calls": {call: [None] * takes for call in calls}}
                              for name, c in creatures.items()}}
    for name, call, take, entry in results:
        manifest["creatures"][name]["calls"][call][take] = entry
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / MANIFEST).write_text(json.dumps(manifest, indent=1))
    return manifest
