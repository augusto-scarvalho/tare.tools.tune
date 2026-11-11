"""Small discoverable review loop; project files remain bounded declarative JSON."""

import json
from pathlib import Path

from ..diagnostics import canonical
from .model import DSLError
from .validate import parse
from .workflow import describe, edit_file, review

HELP = {
    "review": {
        "usage": "dsl review SOURCE --name NAME -o BUNDLES [--previous BUNDLE] [--checks CHECKS.json]",
        "meaning": "Render one selected sound, retain WAV/provenance, "
        "describe facts and explicitly compare an earlier capture.",
        "example": "dsl review examples/dsl-bank.tune.json --name confirm -o output/reviews --json",
        "rules": [
            "Use an existing bundle as SOURCE to avoid regeneration.",
            "No requested checks means not_requested; sound quality still needs listening.",
        ],
    },
    "describe": {
        "usage": "dsl describe BUNDLE [--target TARGET | --find WORDS | --layer ID] [--fields names]",
        "meaning": "Read archived names, values, allowed operations and scopes without loading current assets.",
        "example": "dsl describe BUNDLE --target sound:confirm_strong --fields power --json",
        "rules": [
            "Find returns candidates; it never silently selects an ambiguous target.",
            "Generated root Voice layers expose guarded refinement, not guessed acoustic roles.",
        ],
    },
    "edit": {
        "usage": "dsl edit SOURCE --from-bundle BUNDLE -o BUNDLES [--target TARGET] "
        "(--set PATH JSON | --refine PATH JSON)",
        "meaning": "Trial-render, check and commit one atomic batch bound to an observed bundle.",
        "example": "dsl edit bank.tune.json --from-bundle BUNDLE -o output/reviews --set /with/power 0.65 --json",
        "rules": [
            "Repeat --set or --refine for one batch; scopes cannot be mixed.",
            "--refine /lowpass 2400 preserves a recipe under its guard; --layer ID maps original Voice layer paths.",
            "--dry-run retains a read-only candidate bundle without changing source.",
            "Stale source/assets/code fail; requested-check failure exits 5 without committing.",
            "--response compact returns measured levels, check coverage and edit scope; detailed remains the default.",
        ],
    },
    "checks": {
        "usage": "--checks FILE with format=tare.tools.tune.checks and version=1",
        "meaning": "Explicit duration_s/peak_dbfs min/max, sample_rate, channels, required capabilities and "
        "tolerances against a reference recording (see help reference).",
        "example": {
            "format": "tare.tools.tune.checks",
            "version": 1,
            "duration_s": {"max": 1},
            "sample_rate": 16000,
            "capabilities": ["pcm"],
        },
        "rules": [
            "Checks measure retained float PCM; they never change rendering or seeds.",
            "They are distinct from the edit.expect materialization guard.",
            "A failed source review is still an observation; failed/dry edit candidates are read-only.",
        ],
    },
    "listener": {
        "usage": "python tools/curate.py compare NAME B1 B2 [.. B9] --root ROUNDS [--open] [--question TEXT] "
        "[--task SPEC] [--reference WAV]; serve --root ROUNDS; answers NAME --json --root ROUNDS (source checkout)",
        "meaning": "Put dry-run candidates from one observation in front of a human ear; read the pick as data.",
        "example": "python tools/curate.py compare power A B C --open --question 'Which sounds firmer?' "
        "--root output/rounds",
        "rules": [
            "Candidates are --dry-run edits from one bundle; commit the pick by repeating its edit from that bundle.",
            "Two bundles default to blind ABX, 3-9 to pick and a 1-5 rating; blind unless --open.",
            "Blind cards read #1, #2 by shuffled position: take the choice from answers --json, not from chat.",
            "serve opens the user's browser and blocks: run it in the background, stop it afterwards, never headless.",
            "Always pass --root. The page matches loudness: add --keep-levels when level (power, volume) is judged.",
            "--reference WAV plays a recording first as REF (diff view: D), its measures the targets; the round opens.",
        ],
    },
    "ear": {
        "usage": "TUNE ear BUNDLE|FILE [--vs ref|BUNDLE|FILE|none] [--brief] [--lines] [--at START[,LEN]] "
        "[--weight a|none] [--align onset|peak] [--json]",
        "meaning": "The sound as text: 20 auditory bands by time in 6 dB digits (9 loudest), lines of envelope, peaks "
        "in Hz, pitch and brightness, and a DIFF against another sound. Never how it sounds.",
        "example": "TUNE ear output/reviews/BUNDLE --vs output/reviews/A --brief",
        "rules": [
            "A bundle with a reference is held against it unless --vs says otherwise; --vs A shows what an edit "
            "changed. Time zero is each sound's onset.",
            "Look once in full (~2.5k tokens), then --brief (DIFF and lines, ~1k) or --lines (~0.4k).",
            "A DIFF cell is 6 dB and one band: smaller differences are not shown, and = is not 'the same'.",
            "Not shown: phase, detail finer than a column or a band, roughness, masking. Report what the grid shows; "
            "the ear decides how it sounds.",
        ],
    },
    "reference": {
        "usage": 'a bank\'s "references": {"SOUND": "refs/x.wav"} (or "reference": {"file": ...} for every sound); '
        "review then shows ref; --checks with a reference block judges it",
        "meaning": "Hold a sound against a recording: [recording, sound] per measure, each from its own onset and "
        "peak.",
        "example": {
            "references": {"clash": "refs/clash.wav"},
            "checks": {
                "format": "tare.tools.tune.checks",
                "version": 1,
                "reference": {
                    "active_s": {"ratio": 1.2},
                    "attack_ms": {"max_delta": 10},
                    "centroid_hz": {"semitones": 3},
                    "f0_hz": {"semitones": 2},
                },
            },
        },
        "rules": [
            "ref reads [recording, sound]: active_s (onset to 40 dB under the peak, or over the noise), attack_ms, "
            "centroid_hz (brightness), f0_hz (pitch; a ring over 1600 Hz by its own Hz; or unvoiced), env_db (mean "
            "spectral difference, dB).",
            "Tolerances: active_s ratio, attack_ms max_delta, centroid_hz and f0_hz semitones, env_db max. A sound "
            "without a reference is absent, not failed; a requested measure that could not be taken is not_run.",
            "Numbers aim; they never say it sounds alike: a recording carries room, mic and mastering. Put it beside "
            "the candidates (curate compare --reference) and let the ear decide.",
            "A bundle keeps the recording's PCM: never share bundles. freeze and export carry only the sound.",
        ],
    },
    "arrangement": {
        "usage": "dsl check SOURCE --name NAME --layout --json (nothing is rendered: any size of piece); "
        "also facts.arrangement in a review; in Python: Score.arrangement()",
        "meaning": "Lay out an orchestral battle or scene as scores do, and read the layout back as numbers.",
        "example": '{"music": "march", "seed": 2}',
        "rules": [
            "One line per part: notes_per_attack near 1. Harmony comes from stacking parts in their own registers "
            "(basses, cellos, violas, violins), not from chords inside one track.",
            "Lines move by step or repeat the note: leaps_share (over a fourth) under 0.2. Arpeggios that leap "
            "every note read as busy.",
            "Parts come in a few at a time: parts_by_block rising, parts_growth 2 or more. Start with strings and "
            "percussion; bring winds and brass later, on long notes or doubling a line.",
            "Leave a quiet stretch: density_ratio 2 or more between the fullest and the emptiest 4 bars; then "
            "bars_db should show it too, the opening 2-5 dB under the middle level, not 10.",
            "Put the fast notes in the percussion (a snare or a low drum, 9-12 a bar) and keep string parts to 3-4 "
            "eighths a bar; short string notes on spiccato, held ones on strings, violins or cellos.",
            "Keep the tune off half steps from what is held under it: rubs lists them.",
            "A battle slower than about 126 bpm read as sluggish to our listener; a percussion colour used once or "
            "twice in a piece read as a mistake: use it every loud phrase or not at all.",
            "These rules are what 22 scores share and one listener's picks, not a recipe: finish with a listening "
            "round (dsl help listener).",
        ],
    },
    "chiptune": {
        "usage": 'a track or clip "instrument": {"chip_voice": "pulse"|"triangle", "duty": 12.5|25|50|75, '
        '"fade": true, "slide": SEMITONES, "vibrato": [HZ, SEMITONES]}',
        "meaning": "Compose 8-bit music: console channels as score tracks, read back as numbers by review.",
        "example": "dsl review examples/dsl-chiptune.tune.json --name overworld -o output/reviews "
        "--response compact --json",
        "rules": [
            "A console is a band of four tracks: two pulses (the tune; harmony or echo), the triangle (bass) and "
            "drums on chip_kick, chip_snare, chip_hat. More voices stop sounding 8-bit.",
            'A chip_voice has one voice. Give it a chord ({"chord": "Am"}, a pitch array, C4+E4+G4 in a pattern) '
            "and it plays the chip's chord: an arpeggio, 60 notes a second. Notes overlapping in one track are a "
            "second voice: avoid them.",
            "duty is colour and weight: 12.5 thin, 25 the bright lead, 50 hollow (75 sounds as 25). fade makes held "
            "notes and chords pluck and endings die away; slide -2 scoops up into each note; vibrato [6, 0.3] "
            "suits a held lead.",
            'One instrument per clip, so a track\'s clips change colour mid-tune (at: "2bar"). The echo: the tune '
            'again on the other pulse, a clip at "1/2b", duty 12.5, then [{"velocity": 0.4}].',
            "Write patterns bar by bar with | between bars: a miscounted bar fails naming the bar and its steps. "
            "- holds, . rests, X and C4! accent; steps counts per beat. A repeated pitch strikes again.",
            "Read review as ears. facts.bars_db: the mix's level per bar, dBFS; sections want a few dB of contrast, "
            "and a long tune with every bar alike is flat. tracks[].level_db: each track under the loudest; keep "
            "the tune on top, and a part 20 dB under it is barely heard. facts.rubs: half steps held together; a "
            "'chord' rub (both start together) is usually a wrong note, a 'line' rub often passes.",
            "Change gain (track) or velocity (notes) because of a number, then review again.",
            'No composing needed? {"music": "battle", "style": "chip", "seed": 2}. In Python: '
            "Score.track(...).play(tare.tools.tune.instruments.chip_voice(...), notes).",
            "Numbers never say it sounds good: finish with a listening round (dsl help listener).",
        ],
    },
    "builders": {
        "usage": "from tare.tools.tune.dsl import builders as t",
        "meaning": "Trusted Python composition emits ordinary validated DSL JSON; no Python evaluator in project data.",
        "example": "t.Project(context={'sample_rate':16000},sounds={"
        "'confirm':t.sfx('ui',event='confirm',dry=True)}).write('bank.tune.json')",
        "rules": [
            "Use the generated JSON as the editing source of truth.",
            "For recipe fields: dsl catalog --domain sfx --name ui --fields name,example,knobs --json",
        ],
    },
}


def register(commands):
    for command in ("review", "describe", "edit", "help"):
        parser = commands.add_parser(command, help=HELP.get(command, {}).get("meaning", command))
        parser.set_defaults(fn=run)
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--debug", action="store_true")
        parser.add_argument("--limit", type=int, default=5)
        if command == "help":
            parser.add_argument("topic", nargs="?", choices=tuple(HELP))
            continue
        parser.add_argument("source")
        if command == "describe":
            parser.add_argument("--target")
            parser.add_argument("--find")
            parser.add_argument("--layer")
            parser.add_argument("--fields")
            parser.add_argument("--cursor")
        else:
            parser.add_argument("--response", choices=("detailed", "compact"), default="detailed")
            parser.add_argument("-o", "--output", required=command == "edit")
            parser.add_argument("--checks")
            parser.add_argument("--asset-root", action="append", default=[])
            if command == "review":
                parser.add_argument("--name")
                parser.add_argument("--previous")
            else:
                parser.add_argument("--from-bundle", required=True)
                parser.add_argument("--target")
                parser.add_argument(
                    "--set", action="append", nargs=2, default=[], dest="sets", metavar=("PATH", "JSON")
                )
                parser.add_argument("--refine", action="append", nargs=2, default=[], metavar=("PATH", "JSON"))
                parser.add_argument("--layer")
                parser.add_argument("--dry-run", action="store_true")


def _values(rows):
    result = {}
    for path, value in rows:
        if path in result:
            raise DSLError("E_PATCH", "duplicate edited path", path)
        if len(value.encode("utf-8")) > 65536:
            raise DSLError("E_LIMIT", "an edit value must fit in 64 KiB")
        result[path] = parse(value.encode("utf-8"))
    return result or None


def run(args):
    if args.dsl_command == "help":
        result = (
            {"schema": "tune.help/1", "topic": args.topic, **HELP[args.topic]}
            if args.topic
            else {"schema": "tune.help/1", "topics": {name: data["meaning"] for name, data in HELP.items()}}
        )
    elif args.dsl_command == "describe":
        result = describe(
            args.source,
            target=args.target,
            find=args.find,
            layer=args.layer,
            fields=args.fields.split(",") if args.fields else None,
            limit=args.limit,
            cursor=args.cursor,
        )
    else:
        checks = None
        if args.checks:
            path = Path(args.checks)
            if path.stat().st_size > 65536:
                raise DSLError("E_LIMIT", "checks must fit in 64 KiB")
            checks = parse(path.read_bytes())
        if args.dsl_command == "review":
            result = review(
                args.source,
                name=args.name,
                output=args.output,
                previous=args.previous,
                checks=checks,
                asset_roots=args.asset_root,
                limit=args.limit,
                response=args.response,
            )
            if result["checks"]["status"] in ("failed", "not_run"):
                raise DSLError("E_CHECK_FAILED", "review did not satisfy requested checks", details=result)
        else:
            result = edit_file(
                args.source,
                from_bundle=args.from_bundle,
                output=args.output,
                target=args.target,
                set_fields=_values(args.sets),
                refine=_values(args.refine),
                layer=args.layer,
                checks=checks,
                dry_run=args.dry_run,
                asset_roots=args.asset_root,
                limit=args.limit,
                response=args.response,
            )
    print(
        canonical(result).decode() if args.json else json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)
    )
