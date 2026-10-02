"""Command line: creaturesynth <command> (see creaturesynth --help)."""
import argparse
import json
import sys
from pathlib import Path

from . import rng
from .archetypes import ARCHETYPES, DESCRIPTIONS
from .audio_io import write_wav
from .calls import CALLS
from .chip import gen1_voice, load_gen1
from .creature import Creature
from .render import DEFAULT_SR, render
from .spec import Voice
from .speech.babble import STYLES
from .speech.casting import ROLES


def _species(value: str) -> int:
    return int(value) if value.lstrip("-").isdigit() else rng.seed32(value)


def _creature_args(p: argparse.ArgumentParser):
    p.add_argument("archetype", choices=sorted(ARCHETYPES))
    p.add_argument("--species", type=_species, default=0, help="number or any name (hashed)")
    p.add_argument("--size", type=float, default=0.5, help="0 tiny .. 1 huge")
    p.add_argument("--aggression", type=float, default=0.3, help="0 calm .. 1 furious")
    p.add_argument("--individual", type=int, default=0)
    p.add_argument("--variation", type=float, default=0.15)
    p.add_argument("--gene", action="append", default=[], metavar="NAME=VALUE", help="pin a gene (0..1)")
    p.add_argument("--call", choices=list(CALLS), default="idle")
    p.add_argument("--take", type=int, default=0)


def _creature(a) -> Creature:
    genes = {}
    for g in a.gene:
        name, _, value = g.partition("=")
        genes[name] = float(value)
    return Creature(a.archetype, species=a.species, size=a.size, aggression=a.aggression,
                    individual=a.individual, variation=a.variation, genes=genes)


def _write(audio, path, sr, png=False):
    write_wav(path, audio, sr)
    print(f"{path}  ({len(audio) / sr:.2f}s)")
    if png:
        from .plot import spectrogram  # optional dependency: pip install creaturesynth[plot]
        spectrogram(audio, sr, Path(path).with_suffix(".png"))


def _cast(a):
    from dataclasses import replace

    from .speech.casting import cast
    voice = a.voice if a.voice or a.role or a.gender else "default"
    who = cast(a.role or "minor", a.name or "", a.lang, a.gender, voice=voice, style=a.style)
    overrides = {k: getattr(a, k) for k in ("pitch", "tract", "rate", "range", "breath") if getattr(a, k) is not None}
    if who.natural:
        if set(overrides) - {"rate"}:
            raise ValueError("natural (kokoro) voices only take --rate")
        return replace(who, speaker=replace(who.speaker, speed=overrides.get("rate", who.speaker.speed)))
    return replace(who, speaker=who.speaker.but(**overrides))


def cmd_say(a):
    who = _cast(a)
    print(f"{who.role}: {'natural (kokoro)' if who.natural else 'formant'} voice, {who.style}", file=sys.stderr)
    if who.natural:  # natural voice: audio only, no spec or phonemes
        _write(who.render(a.text, a.lang, a.sr), a.output or "fala.wav", a.sr, a.png)
        return
    if a.phonemes:
        print(who.speaker.phonemes(a.text, a.lang))
    voice = who.voice(a.text, a.lang)
    if a.spec:
        Path(a.spec).write_text(voice.to_json())
    _write(render(voice, a.sr), a.output or "fala.wav", a.sr, a.png)


def cmd_voices(a):
    from .speech import PRESETS, neural
    for name, sp in PRESETS.items():
        print(f"  {name:8s} pitch {sp.pitch:5.0f} Hz  tract {sp.tract:.2f}  rate {sp.rate:.2f}")
    print("  npc:<seed>  a unique human voice per seed (Speaker.random)")
    state = "installed" if neural.available() else 'not installed: pip install "creaturesynth[neural]"'
    print(f"natural voices (Kokoro, {state}):")
    for lang, ids in neural.VOICES.items():
        print(f"  {lang}: " + ", ".join(f"kokoro:{v}" for v in ids))


def _save_designed(creature, score, a):
    print(f"{creature.archetype}  size {creature.size:.2f}  aggression {creature.aggression:.2f}  score {score:.3f}")
    entry = json.dumps({k: v for k, v in creature.to_dict().items() if k not in ("name", "individual")})
    print(f"bestiary entry: {entry}")
    if a.output:
        Path(a.output).write_text(json.dumps(creature.to_dict(), indent=1))
    if a.wav:
        _write(creature.render(a.call), a.wav, DEFAULT_SR)


def cmd_design(a):
    from .designer import design
    creature, score = design(a.prompt, a.archetype or None, a.call, a.iters, seed=a.seed)
    _save_designed(creature, score, a)


def cmd_match(a):
    from .audio_io import load_audio
    from .designer import match
    sample, sr = load_audio(a.sample)
    creature, score = match(sample, sr, a.archetype or None, a.call, a.iters, seed=a.seed)
    _save_designed(creature, score, a)


def cmd_judge(a):
    from .clap import JUDGE, LABELS, load
    clap = load(a.model or JUDGE)
    labels = list(LABELS)
    for name in ARCHETYPES:
        clips = [Creature(name, sp, size, 0.25 + 0.5 * size).render(call)
                 for sp in (1, 2) for size in (0.2, 0.8) for call in ("idle", "attack")]
        heard = clap.classify(clips, labels)
        ok = sum(name in LABELS[h] for h in heard)
        print(f"  {name:10s} {ok}/{len(heard)} recognised   heard: {', '.join(sorted(set(heard)))}")


def cmd_list(a):
    print("archetypes:")
    for name in ARCHETYPES:
        print(f"  {name:10s} {DESCRIPTIONS[name]}")
    print("calls:", ", ".join(CALLS))


def cmd_render(a):
    voice = _creature(a).voice(a.call, a.take)
    if a.spec:
        Path(a.spec).write_text(voice.to_json(indent=1))
    _write(render(voice, a.sr), a.output or f"{a.archetype}_{a.call}.wav", a.sr, a.png)


def cmd_spec(a):
    text = _creature(a).voice(a.call, a.take).to_json(indent=1)
    if a.output:
        Path(a.output).write_text(text)
    else:
        print(text)


def cmd_from_spec(a):
    voice = Voice.from_json(Path(a.spec).read_text())
    _write(render(voice, a.sr), a.output or Path(a.spec).with_suffix(".wav"), a.sr, a.png)


def cmd_bake(a):
    from .bake import bake, load_bestiary
    creatures, settings = load_bestiary(a.bestiary, natural=False if a.no_natural else None)
    calls = a.calls.split(",") if a.calls else settings.get("calls")
    takes = a.takes or settings.get("takes", 4)
    sr = a.sr or settings.get("sample_rate", DEFAULT_SR)
    speakers = settings.get("speakers", {})
    manifest = bake(creatures, a.output, calls, takes, sr, specs=not a.no_specs, workers=a.workers,
                    speakers=speakers)
    n = sum(len(t) for c in manifest["creatures"].values() for t in c["calls"].values())
    lines = sum(len(s["lines"]) for s in manifest.get("speakers", {}).values())
    print(f"{n} sounds for {len(creatures)} creatures, {lines} spoken lines -> {a.output}/manifest.json")


def cmd_zoo(a):
    from .bake import bake
    creatures = {}
    for i in range(a.count):
        c = Creature.random(a.seed * 100_003 + i, a.archetype)
        creatures[f"{i:03d}_{c.archetype}"] = c
    bake(creatures, a.output, a.calls.split(","), a.takes, a.sr or DEFAULT_SR, workers=a.workers)
    print(f"{len(creatures)} random creatures -> {a.output}/manifest.json")


def cmd_gen1(a):
    sr = a.sr or DEFAULT_SR
    species = load_gen1()["species"]
    targets = range(1, len(species) + 1) if a.name == "all" else [a.name]
    out = Path(a.output)
    for t in targets:
        voice = gen1_voice(t, hardware_noise=not a.legacy_noise)
        name = voice.meta["name"].lower()
        _write(render(voice, sr), out / f"{name}.wav" if a.name == "all" or out.suffix != ".wav" else out, sr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="creaturesynth", description="Procedural creature voices for games.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="archetypes and calls").set_defaults(fn=cmd_list)

    p = sub.add_parser("render", help="render one creature call to WAV")
    _creature_args(p)
    p.add_argument("-o", "--output")
    p.add_argument("--spec", help="also save the voice spec (JSON)")
    p.add_argument("--png", action="store_true", help="also save a spectrogram (needs matplotlib)")
    p.add_argument("--sr", type=int, default=DEFAULT_SR)
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("spec", help="print a creature call's voice spec (JSON) for engine runtimes")
    _creature_args(p)
    p.add_argument("-o", "--output")
    p.set_defaults(fn=cmd_spec)

    p = sub.add_parser("from-spec", help="render a voice spec (JSON) to WAV")
    p.add_argument("spec")
    p.add_argument("-o", "--output")
    p.add_argument("--png", action="store_true")
    p.add_argument("--sr", type=int, default=DEFAULT_SR)
    p.set_defaults(fn=cmd_from_spec)

    p = sub.add_parser("say", help="speak text with a procedural human voice (pt or en)")
    p.add_argument("text")
    p.add_argument("--lang", choices=["pt", "en"], default="pt")
    p.add_argument("--voice", help="preset (see 'voices'), npc:<seed> or kokoro:<voice id>")
    p.add_argument("--role", choices=[r for r in ROLES if r != "creature"],
                   help="let the cast pick the engine: main = natural voice when installed")
    p.add_argument("--gender", choices=["f", "m"])
    p.add_argument("--name", help="character name (seeds its unique voice)")
    p.add_argument("--style", choices=STYLES, help="speech, or babble: gibberish, animalese, mumble")
    for knob in ("pitch", "tract", "rate", "range", "breath"):
        p.add_argument(f"--{knob}", type=float)
    p.add_argument("--phonemes", action="store_true", help="print the phonetic transcription")
    p.add_argument("-o", "--output")
    p.add_argument("--spec", help="also save the voice spec (JSON)")
    p.add_argument("--png", action="store_true")
    p.add_argument("--sr", type=int, default=DEFAULT_SR)
    p.set_defaults(fn=cmd_say)

    sub.add_parser("voices", help="speech voice presets").set_defaults(fn=cmd_voices)

    for name, fn, what, helptext in (("design", cmd_design, "prompt", "creature from a text prompt (CLAP)"),
                                     ("match", cmd_match, "sample", "creature closest to a recording (CLAP)")):
        p = sub.add_parser(name, help=helptext + ' - needs pip install "creaturesynth[clap]"')
        p.add_argument(what)
        p.add_argument("--archetype", action="append", choices=sorted(ARCHETYPES), help="limit the search (repeatable)")
        p.add_argument("--call", choices=list(CALLS), default="idle")
        p.add_argument("--iters", type=int, default=60)
        p.add_argument("--seed", type=int, default=0)
        p.add_argument("-o", "--output", help="save the creature (JSON)")
        p.add_argument("--wav", help="also render it")
        p.set_defaults(fn=fn)

    p = sub.add_parser("judge", help="what CLAP hears in each archetype")
    p.add_argument("--model", help="CLAP model id (default: the held-out judge)")
    p.set_defaults(fn=cmd_judge)

    p = sub.add_parser("bake", help="bestiary JSON -> WAV packs + manifest")
    p.add_argument("bestiary")
    p.add_argument("-o", "--output", default="baked")
    p.add_argument("--calls", help="comma-separated (default: bestiary or all)")
    p.add_argument("--takes", type=int)
    p.add_argument("--sr", type=int)
    p.add_argument("--workers", type=int)
    p.add_argument("--no-specs", action="store_true", help="skip the per-sound JSON specs")
    p.add_argument("--no-natural", action="store_true", help="formant voices only, even for 'main' speakers")
    p.set_defaults(fn=cmd_bake)

    p = sub.add_parser("zoo", help="bake N brand-new random creatures")
    p.add_argument("-n", "--count", type=int, default=20)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--archetype", choices=sorted(ARCHETYPES))
    p.add_argument("--calls", default="idle,attack")
    p.add_argument("--takes", type=int, default=1)
    p.add_argument("--sr", type=int)
    p.add_argument("--workers", type=int)
    p.add_argument("-o", "--output", default="zoo")
    p.set_defaults(fn=cmd_zoo)

    p = sub.add_parser("gen1", help="reproduce a Gen 1 cry (name, Pokedex number or 'all')")
    p.add_argument("name")
    p.add_argument("-o", "--output", default="gen1")
    p.add_argument("--sr", type=int)
    p.add_argument("--legacy-noise", action="store_true", help="old web app's 7-bit noise (bug-compatible)")
    p.set_defaults(fn=cmd_gen1)

    a = parser.parse_args(argv)
    try:
        a.fn(a)
    except (ValueError, FileNotFoundError, ImportError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
