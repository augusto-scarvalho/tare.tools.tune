"""Command line: tare.tools.tune <command> (see tare.tools.tune --help)."""
import argparse
import json
import sys
from pathlib import Path

from . import rng
from .archetypes import ARCHETYPES, DESCRIPTIONS
from .audio_io import trim_tail, write_wav
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


KEEP_TAIL = ("keep the whole render (loops and sounds through a reverb or echo always do): "
             "no cut where it falls 60 dB under its peak")


def _write(source, path, sr, png=False, keep_tail=False):
    """Render a Voice or a Cue to a WAV, its silent tail cut unless it loops or rings out through a reverb or echo."""
    if isinstance(source, Voice):
        audio, loop, rings = render(source, sr), source.loop > 0, source.space > 0
    else:
        audio, loop, rings = source.render(), source.length > 0, source.score.hall > 0 or bool(source.score.echo)
    full, audio = len(audio), audio if loop or rings or keep_tail else trim_tail(audio, sr)
    write_wav(path, audio, sr, loop=loop)
    cut = f", {(full - len(audio)) / sr:.2f}s of silence cut" if full > len(audio) else ""
    print(f"{path}  ({len(audio) / sr:.2f}s{', seamless loop' if loop else ''}{cut})")
    if png:
        from .plot import spectrogram  # optional dependency: pip install tare.tools.tune[plot]
        spectrogram(audio, sr, Path(path).with_suffix(".png"))


def _cast(a):
    from dataclasses import replace

    from .speech.casting import cast
    voice = a.voice if a.voice or a.role or a.gender else "default"
    who = cast(a.role or "minor", a.name or "", a.lang, a.gender, voice=voice, style=a.style)
    overrides = {k: getattr(a, k) for k in ("pitch", "tract", "rate", "range", "breath") if getattr(a, k) is not None}
    return replace(who, speaker=who.speaker.but(**overrides))


def cmd_say(a):
    who = _cast(a)
    engine = "natural" if who.speaker.natural(a.lang) else "formant"
    print(f"{who.role}: {engine} voice, {who.style}", file=sys.stderr)
    if a.phonemes:
        print(who.speaker.phonemes(a.text, a.lang))
    voice = who.voice(a.text, a.lang)
    if a.spec:
        Path(a.spec).write_text(voice.to_json(), encoding="utf-8")
    _write(voice, a.output or "fala.wav", a.sr, a.png, a.keep_tail)


def cmd_doctor(a):
    """Is this install ready, and is it the one every render was verified with? Fails only when it cannot render."""
    import importlib.util
    import platform
    import time

    import numpy
    import scipy

    root = Path(__file__).resolve().parents[4]                  # a clone: constraints.txt sits next to pyproject.toml
    pins = {}
    if (root / "constraints.txt").exists():
        pins = dict(line.split("==") for line in (root / "constraints.txt").read_text().split() if "==" in line)

    def row(good, what, note=""):
        print(f"{'ok' if good else '!!'}  {what}{f'  ({note})' if note else ''}")
        return good

    ready = row(sys.version_info >= (3, 10), f"Python {platform.python_version()}",
                "3.10+; 3.12+ for the pinned numpy and scipy")
    for name, module in (("numpy", numpy), ("scipy", scipy)):
        want = pins.get(name)
        note = ("no constraints.txt here to compare with" if want is None else
                "the version every render was verified with" if want == module.__version__ else
                f"renders were verified with {want}: pip install -e . -c constraints.txt")
        row(want in (None, module.__version__), f"{name} {module.__version__}", note)
    banks = sorted((Path(__file__).parent / "speech" / "data").glob("bank_*.npz"))
    ready &= row(bool(banks), f"natural voice banks: {', '.join(b.stem[5:] for b in banks) or 'none'}")
    ogg = importlib.util.find_spec("soundfile") is not None
    row(True, f"OGG export: {'yes' if ogg else 'no'}", "" if ogg else "optional: pip install -e '.[export]'")
    try:
        t = time.perf_counter()
        y = Creature("mammal", 7).render("attack", sr=16_000)
        ready &= row(bool(len(y)) and bool(numpy.isfinite(y).all()),
                     f"render: a creature call in {time.perf_counter() - t:.2f} s")
    except Exception as e:  # noqa: BLE001 - reporting it is the whole point
        ready = row(False, f"render failed: {type(e).__name__}: {e}")
    if not ready:
        raise ValueError("this install cannot render: see the !! lines above")


def cmd_voices(a):
    from .speech import PRESETS, concat
    print("formant voices:")
    for name, sp in PRESETS.items():
        print(f"  {name:8s} pitch {sp.pitch:5.0f} Hz  tract {sp.tract:.2f}  rate {sp.rate:.2f}")
    print("  npc:<seed>  a unique human voice per seed (Speaker.random)")
    print("natural voices (voice banks; any pitch and tract with --pitch/--tract):")
    print("  natural, natural:m, natural:f   a man's or a woman's register, nearest bank per language")
    for name in concat.banks():
        b = concat.bank(name)
        print(f"  natural:{name:10s} pitch {b.pitch:5.0f} Hz  tract {b.tract:.2f}  ({b.meta['teacher']})")


def _save_designed(creature, score, a):
    print(f"{creature.archetype}  size {creature.size:.2f}  aggression {creature.aggression:.2f}  score {score:.3f}")
    entry = json.dumps({k: v for k, v in creature.to_dict().items() if k not in ("name", "individual")})
    print(f"bestiary entry: {entry}")
    if a.output:
        Path(a.output).write_text(json.dumps(creature.to_dict(), indent=1), encoding="utf-8")
    if a.wav:
        _write(creature.voice(a.call), a.wav, DEFAULT_SR)


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
        Path(a.spec).write_text(voice.to_json(indent=1), encoding="utf-8")
    _write(voice, a.output or f"{a.archetype}_{a.call}.wav", a.sr, a.png, a.keep_tail)


def cmd_spec(a):
    text = _creature(a).voice(a.call, a.take).to_json(indent=1)
    if a.output:
        Path(a.output).write_text(text, encoding="utf-8")
    else:
        print(text)


def cmd_from_spec(a):
    voice = Voice.from_json(Path(a.spec).read_text(encoding="utf-8"))
    _write(voice, a.output or Path(a.spec).with_suffix(".wav"), a.sr, a.png, a.keep_tail)


def cmd_bake(a):
    from .bake import bake, load_bestiary
    creatures, settings = load_bestiary(a.bestiary, natural=False if a.no_natural else None)
    calls = a.calls.split(",") if a.calls else settings.get("calls")
    takes = a.takes or settings.get("takes", 4)
    sr = a.sr or settings.get("sample_rate", DEFAULT_SR)
    speakers = settings.get("speakers", {})
    manifest = bake(creatures, a.output, calls, takes, sr, specs=not a.no_specs, workers=a.workers,
                    speakers=speakers, sounds=settings.get("sounds"), keep_tail=a.keep_tail,
                    music=settings.get("music"))
    n = sum(len(t) for c in manifest["creatures"].values() for t in c["calls"].values())
    lines = sum(len(s["lines"]) for s in manifest.get("speakers", {}).values())
    fx = sum(len(t) for s in manifest.get("sounds", {}).values() for t in s["events"].values())
    print(f"{n} calls for {len(creatures)} creatures, {lines} spoken lines, {fx} sound effects,"
          f" {len(manifest.get('music', {}))} cues -> {a.output}/manifest.json")


def _sfx(a):
    from .sfx import Sfx
    genes = {name: float(value) for name, value in (g.split("=", 1) for g in a.gene)}
    knobs = {name: float(value) for name, value in (k.split("=", 1) for k in a.knob)}
    return Sfx(a.kind, a.style or "", a.species, a.size, a.power, genes=genes, era=a.era, knobs=knobs, dry=a.dry)


def cmd_sfx(a):
    sx = _sfx(a)
    event = a.event or sx.events[0]
    voice = sx.voice(event, a.take)
    if a.spec:
        Path(a.spec).write_text(voice.to_json(indent=1), encoding="utf-8")
    out = a.output or f"{a.kind}_{sx.style}_{event}.wav"
    _write(voice, out, a.sr, a.png, a.keep_tail)


def cmd_music(a):
    from .music import Cue
    cue = Cue(a.kind, a.style, a.seed, a.sr)
    out = a.output or f"{a.kind}_{a.style}_{a.seed}.wav"
    _write(cue, out, a.sr, a.png, a.keep_tail)


def cmd_sounds(a):
    from .sfx import KNOBS, RECIPES
    for kind, r in RECIPES.items():
        print(f"{kind:10s} {r.description}")
        print(f"{'':10s} styles: {', '.join(r.styles)}")
        print(f"{'':10s} events: {', '.join(e + (' (loop)' if e in r.loops else '') for e in r.events)}")
        own = [n for n in r.knobs if n not in KNOBS]
        if own:
            print(f"{'':10s} knobs: the general ones, and {', '.join(own)}")
    if a.knobs:
        shown = {}
        for r in RECIPES.values():
            shown.update(r.knobs)
        print()
        print("knobs (--knob NAME=VALUE; every sound has the general ones):")
        for name, k in shown.items():
            default = "from the species" if k.default is None else f"{k.default:g}"
            span = f"{k.lo:g} .. {k.hi:g} {k.unit}"
            print(f"  {name:11s} {span:22s} default {default:17s} {k.description}")


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
        _write(voice, out / f"{name}.wav" if a.name == "all" or out.suffix != ".wav" else out, sr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tare.tools.tune", description="Procedural creature voices for games.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    from .dsl.cli import register
    register(sub)

    p = sub.add_parser("capture", help="capture a Voice/project JSON as an immutable render bundle")
    p.add_argument("source")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--sr", type=int)
    p.add_argument("--name")
    p.set_defaults(fn=cmd_capture)
    p.add_argument("--asset-root", action="append", default=[])
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("inspect", help="inspect a captured bundle, Voice/project JSON, or WAV")
    p.add_argument("source")
    p.add_argument("--json", action="store_true")
    p.add_argument("--start", type=float, default=0)
    p.add_argument("--end", type=float)
    p.add_argument("--band", type=float, nargs=2, metavar=("LOW_HZ", "HIGH_HZ"))
    p.add_argument("--no-pitch", action="store_true")
    p.add_argument("--name")
    p.set_defaults(fn=cmd_inspect)
    p.add_argument("--node", help="inspect one captured processing stage, e.g. n1")

    p.add_argument("--view", choices=("summary", "layers", "events", "stages", "full"))
    p.add_argument("--top", type=int)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--cursor")
    p.add_argument("--fields")
    p.add_argument("--response", choices=("detailed", "compact"), default="detailed")
    p.add_argument("--asset-root", action="append", default=[])

    p = sub.add_parser("ear", help="the sound as text for an agent: bands by time in 6 dB digits, peaks, a DIFF")
    p.add_argument("sound", help="a review bundle or an audio file")
    p.add_argument("--vs", help="another bundle or file, 'ref' (the bundle's reference recording; the default when "
                   "it has one) or 'none'")
    p.add_argument("--brief", action="store_true", help="the DIFF and the lines only (~1k tokens): after a first look")
    p.add_argument("--lines", action="store_true", help="the lines only: envelope, peaks, pitch, brightness")
    p.add_argument("--at", metavar="START[,LEN]", help="one grid from START ms, LEN ms long (default 100)")
    p.add_argument("--weight", choices=("a", "none"), default="a", help="A-weighting (the ear's) or raw energy")
    p.add_argument("--align", choices=("onset", "peak"), default="onset", help="time zero (peak for a soft onset)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_ear)

    p = sub.add_parser("study", help="what a recording is made of, and what in tune makes each part")
    p.add_argument("file", help="an audio file (or a review bundle)")
    p.add_argument("--domain", choices=("sfx", "creature", "speech", "music"),
                   help="which fields to suggest (a pitched sound could be any of the first three)")
    p.add_argument("--search", metavar="sfx:KIND|creature", help="the 3 renders nearest it by DSP distance: every "
                   "style and event of one sfx kind (seconds), or every creature archetype and call (about 25 s)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_study)
    p = sub.add_parser("studio", help="live player with immutable revisions and layer diagnostics")
    p.add_argument("project")
    p.add_argument("-o", "--output", default="authoring-out")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--name")
    p.set_defaults(fn=cmd_studio)
    p.add_argument("--asset-root", action="append", default=[])

    p = sub.add_parser("midi", help="export recorded Score/project events as MIDI")
    p.add_argument("source")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--approximate", action="store_true", help="report and permit documented MIDI approximations")
    p.set_defaults(fn=cmd_midi)
    p.add_argument("--name")
    p.add_argument("--asset-root", action="append", default=[])
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("export", help="export a project as WAV/OGG audio sprites with verified sample coordinates")
    p.add_argument("source")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--ogg", action="store_true")
    p.add_argument("--gap", type=float, default=0.1)
    p.add_argument("--keep-tail", action="store_true", help=KEEP_TAIL)
    p.set_defaults(fn=cmd_export)
    p.add_argument("--asset-root", action="append", default=[])

    sub.add_parser("list", help="archetypes and calls").set_defaults(fn=cmd_list)

    p = sub.add_parser("render", help="render one creature call to WAV")
    _creature_args(p)
    p.add_argument("-o", "--output")
    p.add_argument("--spec", help="also save the voice spec (JSON)")
    p.add_argument("--png", action="store_true", help="also save a spectrogram (needs matplotlib)")
    p.add_argument("--keep-tail", action="store_true", help=KEEP_TAIL)
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
    p.add_argument("--keep-tail", action="store_true", help=KEEP_TAIL)
    p.add_argument("--sr", type=int, default=DEFAULT_SR)
    p.set_defaults(fn=cmd_from_spec)

    p = sub.add_parser("say", help="speak text with a procedural human voice (pt or en)")
    p.add_argument("text")
    p.add_argument("--lang", choices=["pt", "en"], default="pt")
    p.add_argument("--voice", help="preset (see 'voices'), npc:<seed> or natural[:m|f|<bank>]")
    p.add_argument("--role", choices=[r for r in ROLES if r != "creature"],
                   help="let the cast pick the engine: main = natural voice")
    p.add_argument("--gender", choices=["f", "m"])
    p.add_argument("--name", help="character name (seeds its unique voice)")
    p.add_argument("--style", choices=STYLES, help="speech, or babble: gibberish, animalese, mumble")
    for knob in ("pitch", "tract", "rate", "range", "breath"):
        p.add_argument(f"--{knob}", type=float)
    p.add_argument("--phonemes", action="store_true", help="print the phonetic transcription")
    p.add_argument("-o", "--output")
    p.add_argument("--spec", help="also save the voice spec (JSON)")
    p.add_argument("--png", action="store_true")
    p.add_argument("--keep-tail", action="store_true", help=KEEP_TAIL)
    p.add_argument("--sr", type=int, default=DEFAULT_SR)
    p.set_defaults(fn=cmd_say)

    sub.add_parser("voices", help="speech voice presets").set_defaults(fn=cmd_voices)
    p = sub.add_parser("doctor", help="check this install: Python, the pinned numpy and scipy, voice banks, a render")
    p.set_defaults(fn=cmd_doctor)

    from .sfx import RECIPES
    p = sub.add_parser("sfx", help="render a sound effect: weapons, footsteps, explosions, magic, ambience")
    p.add_argument("--era", default="", choices=["", "hd", "16bit"],
                   help="dress it as a generation: hd (HD-2D, wide and reverberant) or 16bit (PSP/DS samples)")
    p.add_argument("--dry", action="store_true",
                   help="no room and no tail, for a game that puts its own reverb on each map")
    p.add_argument("kind", choices=list(RECIPES))
    p.add_argument("style", nargs="?", help="material, element or place (see 'sounds')")
    p.add_argument("--event", help="swing, clash, cast, impact, loop... (default: the first)")
    p.add_argument("--species", type=_species, default=0, help="the object's identity: number or any name")
    p.add_argument("--size", type=float, default=0.5)
    p.add_argument("--power", type=float, default=0.5)
    p.add_argument("--take", type=int, default=0)
    p.add_argument("--gene", action="append", default=[], metavar="NAME=VALUE")
    p.add_argument("--knob", action="append", default=[], metavar="NAME=VALUE",
                   help="register, tempo, length, ring, brightness, sparkle, key... (see 'sounds --knobs')")
    p.add_argument("-o", "--output")
    p.add_argument("--spec", help="also save the voice spec (JSON)")
    p.add_argument("--png", action="store_true")
    p.add_argument("--keep-tail", action="store_true", help=KEEP_TAIL)
    p.add_argument("--sr", type=int, default=DEFAULT_SR)
    p.set_defaults(fn=cmd_sfx)

    from .music import CUES
    from .music import STYLES as MUSIC_STYLES
    p = sub.add_parser("music", help="compose a cue from a seed: a jingle, or a loop that repeats without a seam")
    p.add_argument("kind", choices=list(CUES))
    p.add_argument("--style", default="orchestral", choices=list(MUSIC_STYLES),
                   help="orchestral, snes (16-bit) or chip")
    p.add_argument("--seed", type=int, default=0, help="which piece: the same seed is always the same music")
    p.add_argument("-o", "--output")
    p.add_argument("--png", action="store_true")
    p.add_argument("--keep-tail", action="store_true", help=KEEP_TAIL)
    p.add_argument("--sr", type=int, default=DEFAULT_SR)
    p.set_defaults(fn=cmd_music)

    p = sub.add_parser("sounds", help="sound effect kinds, styles and events")
    p.add_argument("--knobs", action="store_true", help="also list the knobs, their ranges and what they do")
    p.set_defaults(fn=cmd_sounds)

    for name, fn, what, helptext in (("design", cmd_design, "prompt", "creature from a text prompt (CLAP)"),
                                     ("match", cmd_match, "sample", "creature closest to a recording (CLAP)")):
        p = sub.add_parser(name, help=helptext + ' - needs pip install "tare.tools.tune[clap]"')
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
    p.add_argument("--keep-tail", action="store_true", help=KEEP_TAIL)
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
    except (ValueError, OSError, ImportError, json.JSONDecodeError) as e:
        from .dsl.model import DSLError
        if isinstance(e, DSLError):
            if getattr(a, "debug", False):
                raise
            from .dsl.responses import respond
            profile = getattr(a, "response", "detailed")
            report = respond(e.to_dict(), "error", profile)
            machine = getattr(a, "json", False) or profile == "compact"
            hint = f" (did you mean {', '.join(map(str, e.suggestions))}?)" if e.suggestions else ""
            print(json.dumps(report, ensure_ascii=False, allow_nan=False) if machine else f"{e.code}: {e}{hint}",
                  file=sys.stderr)
            return e.exit_code
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_capture(a):
    from .authoring import build_file
    from .bundles import save_bundle
    result = build_file(a.source, sr=a.sr, name=a.name, asset_roots=a.asset_root)
    path = save_bundle(result, a.output)
    summary = {"schema": "tune.query/1", "bundle": str(path), "revision": path.name,
               "pcm_id": result.manifest["pcm_id"],
               "authored_revision": result.manifest.get("dsl", {}).get("authored_revision")}
    print(json.dumps(summary) if a.json else path)


def cmd_studio(a):
    from .studio import run
    run(a.project, a.output, a.port, name=a.name, asset_roots=a.asset_root)


def cmd_midi(a):
    from .authoring import materialize
    from .midi_export import export_midi
    path = Path(a.source)
    document = json.loads(path.read_text(encoding="utf-8"))
    programs = {}
    if document.get("format") == "tare.tools.tune.dsl":
        from .dsl import compile_document, load
        from .dsl.model import DSLError
        compiled = compile_document(load(path, asset_roots=a.asset_root), name=a.name)
        if compiled.plan.kind not in ("score", "cue"):
            raise DSLError("E_CAPABILITY", "MIDI requires a musical Score or Cue; use PCM export")
        if compiled.plan.placements and not a.approximate:
            raise DSLError("E_CAPABILITY", "placed sounds require approximate MIDI export or PCM")
        source, loop = compiled.plan.source, compiled.plan.loop
        for track in getattr(source, "tracks", {}).values():
            programs.update({k: v for k, v in getattr(track, "dsl_programs", {}).items() if v is not None})
        if compiled.plan.placements:
            from .dsl.composition import capture_plan
            for placement in compiled.plan.placements:
                source.add(capture_plan(placement["plan"]).audio, at=placement["at"])
    else:
        selected = document.get("sounds", {}).get(a.name) if "sounds" in document else document.get("source", document)
        if selected is None:
            raise ValueError("choose a project sound with --name")
        source, loop = materialize(selected, document.get("sample_rate", 48000), path.parent)
    if hasattr(source, "score") and not hasattr(source, "tracks"):
        loop, source = source.loop or None, source.score
    if not hasattr(source, "tracks"):
        raise ValueError("MIDI export requires a Score or music source")
    report = export_midi(source, a.output, approximate=a.approximate, loop=loop, programs=programs)
    print(json.dumps(report, allow_nan=False))


def cmd_export(a):
    from .authoring import build_file
    from .exports import export_sprite
    document = json.loads(Path(a.source).read_text(encoding="utf-8"))
    names = list(document["sounds"]) if "sounds" in document else [None]
    sounds = {}
    for name in names:
        captured = build_file(a.source, name=name, asset_roots=a.asset_root)
        retained = sum(value.nbytes for item in sounds.values() for value in item.arrays.values())
        if retained + sum(value.nbytes for value in captured.arrays.values()) > 256 * 1024 * 1024:
            raise ValueError("bank exceeds cumulative capture budget; export smaller banks")
        sounds[name or Path(a.source).stem] = captured
    print(export_sprite(sounds, a.output, ogg=a.ogg, gap=a.gap, keep_tail=a.keep_tail))


def cmd_ear(a):
    from .ear import hear, load, text
    audio, sr, loop, reference, label = load(a.sound)
    vs = None
    if a.vs == "ref" or a.vs is None and reference:
        if reference is None:
            raise SystemExit("this sound has no reference recording: --vs FILE|BUNDLE, or none")
        vs = ("REF", reference[2], reference[0], reference[1], False)
    elif a.vs not in (None, "none"):
        other, other_sr, other_loop, _, other_label = load(a.vs)
        vs = ("VS", other_label, other, other_sr, other_loop)
    at = [float(v) for v in a.at.split(",")] if a.at else None
    report = hear(("SOUND", label, audio, sr, loop), vs, brief=a.brief, lines_only=a.lines,
                  at=(at[0], at[1] if len(at) > 1 else 100) if at else None, weight=a.weight == "a", align=a.align)
    print(json.dumps(report, ensure_ascii=False) if a.json else text(report))


def cmd_study(a):
    from .study import study, text
    report = study(a.file, a.domain, a.search)
    print(json.dumps(report, ensure_ascii=False) if a.json else text(report))


def cmd_inspect(a):
    from .audio_io import read_channels
    from .authoring import build_file
    from .bundles import load_bundle
    from .dsl.responses import validate_response
    from .inspection import inspect_audio, inspect_capture
    validate_response(a.response, a.view)
    view = a.view or ("summary" if a.response == "compact" else None)
    path = Path(a.source)
    captured = None
    options = {"start": a.start, "end": a.end, "band": a.band, "pitch": not a.no_pitch}
    if path.is_dir():
        captured = load_bundle(path)
        report = None if view else inspect_capture(captured, node_id=a.node, **options)
    elif path.suffix.lower() == ".json":
        captured = build_file(path, name=a.name, asset_roots=a.asset_root)
        report = None if view else inspect_capture(captured, node_id=a.node, **options)
    else:
        audio, sr = read_channels(path)
        report = inspect_audio(audio, sr, **options)
        if view:
            from .diagnostics import capture
            captured = capture(audio, sr)
    if view:
        from .dsl.query import inspection
        report = inspection(captured, view=view, node_id=a.node, start=a.start, end=a.end, band=a.band,
                            pitch=not a.no_pitch, top=a.top, limit=a.limit, cursor=a.cursor,
                            fields=a.fields.split(",") if a.fields else None, response=a.response)
        print(json.dumps(report, ensure_ascii=False, allow_nan=False))
        return
    if a.json:
        print(json.dumps(report, ensure_ascii=False, allow_nan=False))
    else:
        print(f"{report['status']}: {report['duration']:.3f}s, "
              f"{report['channels']} channels, {report['sample_rate']} Hz")
        for i, level in enumerate(report["levels"]):
            print(f"channel {i}: peak {level['peak_dbfs']} dBFS, "
                  f"RMS {level['rms_dbfs']} dBFS, clipped {level['clipped_samples']}")
        print(f"fundamental: {report['fundamental']['status']}; analysis {report['analysis_id']}")


if __name__ == "__main__":
    sys.exit(main())
