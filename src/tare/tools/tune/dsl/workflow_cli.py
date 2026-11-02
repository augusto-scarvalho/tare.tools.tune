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
