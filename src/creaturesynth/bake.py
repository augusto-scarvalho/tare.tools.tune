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

Spoken lines go in an optional ``speakers`` section::

      "speakers": {
        "king":       {"role": "main", "gender": "m", "lines": {"quest": "Salve o reino!"}},
        "blacksmith": {"voice": "deep", "lang": "pt", "lines": {"greet": "Bem-vindo à forja!"}},
        "guard":      {"voice": "npc:12", "lines": {"halt": "Alto lá!"}},
        "villager":   {"role": "crowd", "lines": {"chat": "Que dia bonito hoje."}},
        "wolf":       {"creature": "wolf", "lines": {"hi": "Olá, viajante."}},
        "fairy":      {"voice": {"preset": "fairy", "rate": 1.2}, "lang": "en", "lines": {"hi": "Hi there!"}}
      }

``role`` picks the engine (see speech/casting.py): ``main`` lines get a natural voice (a voice
bank), everyone else a formant voice; ``crowd`` and ``creature`` babble.
``style`` (speech, gibberish, animalese, mumble), ``gender`` (f, m) and ``voice`` override.
A top-level ``"natural_voices": false`` keeps every line on the formant engine.

Sound effects go in an optional ``sounds`` section (see creaturesynth.sfx; ``events``
defaults to all of the kind's events, loops get one take)::

      "sounds": {
        "excalibur": {"kind": "blade", "style": "steel", "species": "excalibur", "events": ["swing", "clash"]},
        "fireball":  {"kind": "spell", "style": "fire", "power": 0.8},
        "rain":      {"kind": "ambience", "style": "rain", "power": 0.4}
      }
"""
import json
import os
from collections.abc import Iterable, Mapping
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

import numpy as np

from . import __version__, rng
from .audio_io import write_wav
from .calls import CALLS
from .creature import Creature
from .render import DEFAULT_SR, render
from .sfx import RECIPES, Sfx
from .speech import Speaker
from .speech.casting import Cast, cast

MANIFEST = "manifest.json"
SPEAKER_KEYS = {"voice", "role", "gender", "creature", "style", "lang", "lines"}


def speaker_from_entry(name: str, entry: Mapping, creatures: Mapping[str, Creature] | None = None,
                       lang: str = "pt", natural: bool | None = None) -> Cast:
    if unknown := set(entry) - SPEAKER_KEYS:
        raise ValueError(f"speaker {name!r}: unknown field(s) {', '.join(sorted(unknown))}")
    creature = None
    if "creature" in entry:
        if entry["creature"] not in (creatures or {}):
            raise ValueError(f"speaker {name!r}: unknown creature {entry['creature']!r}")
        creature = creatures[entry["creature"]]
    role = entry.get("role", "creature" if creature else "minor")
    voice = entry.get("voice", None if "role" in entry or "gender" in entry or creature else "default")
    try:
        return cast(role, name, entry.get("lang", lang), entry.get("gender"), creature, voice,
                    entry.get("style"), natural)
    except TypeError as e:
        raise ValueError(f"speaker {name!r}: {e}") from None


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


def sound_from_entry(name: str, entry: Mapping) -> tuple[Sfx, list[str]]:
    entry = dict(entry)
    events = entry.pop("events", None)
    if isinstance(entry.get("species"), str):
        entry["species"] = rng.seed32(entry["species"])
    try:
        sfx = Sfx(name=name, **entry)
    except TypeError as e:
        raise ValueError(f"sound {name!r}: {e}") from None
    for ev in events or ():
        if ev not in sfx.events:
            raise ValueError(f"sound {name!r}: {sfx.kind} has no event {ev!r}")
    return sfx, list(events or sfx.events)


def load_bestiary(source: str | Path | Mapping, natural: bool | None = None) -> tuple[dict[str, Creature], dict]:
    """Returns (creatures by name, settings). `natural` (default: the file's "natural_voices", else
    true) decides if "main" speakers get natural voices."""
    data = source if isinstance(source, Mapping) else json.loads(Path(source).read_text())
    entries = data.get("creatures", {})
    creatures = {name: creature_from_entry(name, e, entries) for name, e in entries.items()}
    settings = {k: data[k] for k in ("sample_rate", "takes", "calls") if k in data}
    natural = data.get("natural_voices") if natural is None else natural
    if data.get("speakers"):
        lang = data.get("lang", "pt")
        settings["speakers"] = {name: (speaker_from_entry(name, e, creatures, lang, natural),
                                       e.get("lang", lang), dict(e.get("lines", {})))
                                for name, e in data["speakers"].items()}
    if data.get("sounds"):
        settings["sounds"] = {name: sound_from_entry(name, e) for name, e in data["sounds"].items()}
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


def _bake_sound(job):
    name, sfx, event, take, sr, out_dir, specs = job
    stem = f"{name}/{event}_{take:02d}"
    voice = sfx.voice(event, take)
    audio = render(voice, sr)
    write_wav(Path(out_dir) / f"{stem}.wav", audio, sr)
    entry = {"file": f"{stem}.wav", "duration": round(len(audio) / sr, 4),
             "peak": round(float(np.max(np.abs(audio))), 4)}
    if voice.loop:
        entry["loop"] = True
    if specs:
        (Path(out_dir) / f"{stem}.json").write_text(voice.to_json(indent=1))
        entry["spec"] = f"{stem}.json"
    return name, event, take, entry


def _bake_line(job):
    name, who, lang, line_id, text, sr, out_dir, specs = job
    stem = f"{name}/{line_id}"
    voice = who.voice(text, lang)
    audio = render(voice, sr)
    write_wav(Path(out_dir) / f"{stem}.wav", audio, sr)
    entry = {"file": f"{stem}.wav", "text": text, "duration": round(len(audio) / sr, 4)}
    if specs and voice:
        (Path(out_dir) / f"{stem}.json").write_text(voice.to_json())
        entry["spec"] = f"{stem}.json"
    return name, line_id, entry


def bake(creatures: Mapping[str, Creature], out_dir: str | Path, calls: Iterable[str] | None = None,
         takes: int = 4, sr: int = DEFAULT_SR, specs: bool = True, workers: int | None = None,
         speakers: Mapping[str, tuple["Cast | Speaker", str, Mapping[str, str]]] | None = None,
         sounds: Mapping[str, "Sfx | tuple[Sfx, list[str]]"] | None = None) -> dict:
    """Render every creature x call x take, speaker line and sound effect to ``out_dir``; write ``manifest.json``."""
    out_dir = Path(out_dir)
    speakers = {name: (who if isinstance(who, Cast) else Cast(who, name=name), lang, lines)
                for name, (who, lang, lines) in (speakers or {}).items()}
    calls = list(calls or CALLS)
    for call in calls:
        if call not in CALLS:
            raise ValueError(f"unknown call {call!r}")
    jobs = [(name, c, call, take, sr, str(out_dir), specs)
            for name, c in creatures.items() for call in calls for take in range(takes)]
    line_jobs = [(name, sp, lang, line_id, text, sr, str(out_dir), specs)
                 for name, (sp, lang, lines) in speakers.items() for line_id, text in lines.items()]
    sounds = {name: s if isinstance(s, tuple) else (s, list(s.events)) for name, s in (sounds or {}).items()}
    sound_jobs = [(name, sx, ev, t, sr, str(out_dir), specs) for name, (sx, events) in sounds.items()
                  for ev in events for t in range(1 if ev in RECIPES[sx.kind].loops else takes)]
    workers = workers or min(os.cpu_count() or 1, 8)
    if workers > 1 and len(jobs) + len(line_jobs) + len(sound_jobs) > 1:
        with ProcessPoolExecutor(workers) as pool:
            results = list(pool.map(_bake_one, jobs))
            line_results = list(pool.map(_bake_line, line_jobs))
            sound_results = list(pool.map(_bake_sound, sound_jobs))
    else:
        results = [_bake_one(j) for j in jobs]
        line_results = [_bake_line(j) for j in line_jobs]
        sound_results = [_bake_sound(j) for j in sound_jobs]

    manifest = {"format": "creaturesynth.bake", "version": 1, "generator": f"creaturesynth {__version__}",
                "sample_rate": sr, "takes": takes, "calls": calls,
                "creatures": {name: {"creature": c.to_dict(), "calls": {call: [None] * takes for call in calls}}
                              for name, c in creatures.items()}}
    for name, call, take, entry in results:
        manifest["creatures"][name]["calls"][call][take] = entry
    if speakers:
        manifest["speakers"] = {name: {"speaker": asdict(who.speaker), "lang": lang, "role": who.role,
                                       "style": who.style,
                                       "engine": "natural" if who.speaker.natural(lang) else "formant",
                                       "lines": {}}
                                for name, (who, lang, _) in speakers.items()}
        for name, line_id, entry in line_results:
            manifest["speakers"][name]["lines"][line_id] = entry
    if sounds:
        manifest["sounds"] = {name: {"sfx": sx.to_dict(), "events": {ev: [] for ev in events}}
                              for name, (sx, events) in sounds.items()}
        for name, event, _take, entry in sorted(sound_results, key=lambda r: r[:3]):
            manifest["sounds"][name]["events"][event].append(entry)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / MANIFEST).write_text(json.dumps(manifest, indent=1))
    return manifest
