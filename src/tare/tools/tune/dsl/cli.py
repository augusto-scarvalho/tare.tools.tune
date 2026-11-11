"""Agent-oriented commands; machine output contains one bounded JSON document."""

import json
import sys
from pathlib import Path

from ..diagnostics import canonical
from .compiler import Compiler, compile_document
from .model import DSLError, pointer
from .query import authored, expansion, page, project_fields
from .registry import catalog
from .responses import respond, validate_response
from .validate import load, parse


def register(sub):
    group = sub.add_parser("dsl", help="semantic authoring, compact queries, and revision-checked edits")
    commands = group.add_subparsers(dest="dsl_command", required=True)
    for name in ("catalog", "check", "query", "expand", "patch", "capabilities", "migrate", "freeze", "variants"):
        p = commands.add_parser(name)
        p.set_defaults(fn=run)
        p.add_argument("--json", action="store_true")
        p.add_argument("--debug", action="store_true")
        p.add_argument("--limit", type=int, default=10)
        p.add_argument("--cursor")
        p.add_argument("--fields", help="comma-separated projected fields")
        if name in ("query", "expand", "patch", "freeze"):
            p.add_argument("--response", choices=("detailed", "compact"), default="detailed")
        if name == "catalog":
            p.add_argument(
                "--domain", choices=("op", "sfx", "creature", "speaker", "music", "layer", "instrument", "transform")
            )
            p.add_argument("--name")
        else:
            p.add_argument("source")
            p.add_argument("--name")
            p.add_argument("--asset-root", action="append", default=[])
        if name == "check":
            p.add_argument("--expand", action="store_true")
            p.add_argument("--layout", action="store_true", help="a score's or cue's arrangement and rubs, read "
                           "from its notes: nothing is rendered, so a piece too large to review can be read")
        if name == "query":
            p.add_argument("--target")
            p.add_argument("--pointer")
        if name == "expand":
            p.add_argument("--view", choices=("layers", "events", "full"), default="layers")
        if name == "patch":
            p.add_argument("--patch", required=True, help="patch JSON file or - for stdin")
            p.add_argument("--dry-run", action="store_true")
        if name in ("migrate", "freeze", "variants"):
            p.add_argument("-o", "--output", required=True)
        if name == "freeze":
            p.add_argument("--format", choices=("voice", "bundle", "wav"), default="bundle")
            p.add_argument("--track", help="extract one root Score/Cue track before score mixing")
            p.add_argument("--keep-tail", action="store_true", help="wav: keep the whole render (loops and sounds "
                           "through a reverb or echo always do): no cut where it falls 60 dB under its peak")
        if name == "variants":
            p.add_argument("--definition", required=True)
            p.add_argument("--parameter", default="take")
            p.add_argument("--values", required=True, help="JSON array of explicit values")
    from .workflow_cli import register as register_workflow
    register_workflow(commands)


def fields(value):
    return value.split(",") if value else None


def run(args):
    command = args.dsl_command
    projected = fields(args.fields)
    response = getattr(args, "response", "detailed")
    validate_response(response, getattr(args, "view", None))
    if not 1 <= args.limit <= 100:
        raise DSLError("E_LIMIT", "query limit must be 1..100")
    if command == "catalog":
        entries = catalog(args.domain, args.name)
        if args.name is None and projected is None:
            entries = [
                {k: item[k] for k in ("domain", "name", "result_type", "meaning") if k in item} for item in entries
            ]
        result = page(
            entries,
            {"catalog": 1, "domain": args.domain, "name": args.name},
            limit=args.limit,
            cursor=args.cursor,
            fields=projected,
        )
    elif command in ("migrate", "freeze", "variants"):
        from .migrate import freeze, migrate, variants

        if command == "migrate":
            result = migrate(args.source, args.output, name=args.name, asset_roots=args.asset_root)
        elif command == "freeze":
            result = freeze(
                args.source,
                args.output,
                name=args.name,
                format=args.format,
                asset_roots=args.asset_root,
                track=args.track,
                response=response,
                keep_tail=args.keep_tail,
            )
        else:
            result = variants(args.source, args.output, args.definition, args.parameter, parse(args.values.encode()))
    elif command == "patch":
        from .patch import patch_file

        raw = sys.stdin.buffer.read(1024 * 1024 + 1) if args.patch == "-" else Path(args.patch).read_bytes()
        result = patch_file(args.source, parse(raw), dry_run=args.dry_run, asset_roots=args.asset_root)
    elif command == "check" and args.layout:
        from .model import Budgets
        from .review_data import rub_summary

        # Nothing is rendered here, so the limits that bound a render's memory and time do not apply.
        roomy = Budgets(layers=65536, notes=8192, capture_bytes=2**44, work_bytes=2**44, weighted_work=10**15)
        compiled = compile_document(load(args.source, asset_roots=args.asset_root, limits=roomy), name=args.name)
        if compiled.plan.kind not in ("score", "cue"):
            raise DSLError("E_CAPABILITY", "layout reads a score or a music cue", "/sounds/" + compiled.name)
        score = compiled.plan.source.score if compiled.plan.kind == "cue" else compiled.plan.source
        layout, rubs = score.arrangement(), score.clashes()
        layout.update({key: layout[key][:64] for key in ("parts_by_block", "notes_per_bar_by_block")})
        result = {"schema": "tune.query/1", "sound": compiled.name, "mode": "notes only; no synthesis",
                  "bpm": score.bpm, "meter": score.meter, "arrangement": layout,
                  "rubs": rub_summary(rubs) if rubs else {"chord": 0, "line": 0, "first": []}}
    else:
        document = load(args.source, asset_roots=args.asset_root)
        if command == "query":
            result = authored(document, args.target, pointer=args.pointer, limit=args.limit)
        elif command == "check" and not args.expand:
            compiler = Compiler(document)
            for name, sound in document.data["sounds"].items():
                node = compiler.prepare(sound, document.context, pointer("/sounds", name), "sound:" + name)
                if node.kind != "sound":
                    raise DSLError("E_TYPE", "named sounds must produce Sound expressions", node.origin["pointer"])
            result = {
                "schema": "tune.query/1",
                "authored_revision": document.revision,
                "status": "valid",
                "mode": "syntax/types; no synthesis",
                "sounds": list(document.data["sounds"])[: args.limit],
                "total": len(document.data["sounds"]),
            }
        else:
            compiled = compile_document(document, name=args.name)
            if command in ("check", "capabilities"):
                result = compiled.summary()
            else:
                result = expansion(compiled, view=args.view, limit=args.limit, cursor=args.cursor, fields=projected)
    result = respond(result, command, response)
    if command not in ("catalog", "expand"):
        result = project_fields(result, projected)
    print(
        canonical(result).decode() if args.json else json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)
    )
