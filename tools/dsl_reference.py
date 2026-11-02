"""Generate/check the versioned discovery reference from the maintained runtime registry."""

import argparse
from dataclasses import asdict
from pathlib import Path

from tare.tools.tune.diagnostics import canonical
from tare.tools.tune.dsl import FORMAT, VERSION, Budgets
from tare.tools.tune.dsl.registry import PLACEMENT_FIELDS, SCORE_FIELDS, TRACK_FIELDS, catalog


def reference():
    return {
        "schema": "tare.tools.tune.vocabulary/1",
        "format": FORMAT,
        "version": VERSION,
        "root": {
            "required": ["format", "version", "sounds"],
            "optional": ["context", "defs", "reference"],
            "context_defaults": {"sample_rate": 48000, "bpm": 100, "meter": 4},
        },
        "parameter_types": [
            "number",
            "integer",
            "boolean",
            "string",
            "enum",
            "time",
            "notes",
            "sound",
            "layer",
            "speaker",
            "instrument",
        ],
        "score_fields": sorted(SCORE_FIELDS),
        "track_fields": sorted(TRACK_FIELDS),
        "placement_fields": sorted(PLACEMENT_FIELDS),
        "budgets": asdict(Budgets()),
        "entries": catalog(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/dsl-reference.json"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = canonical(reference()) + b"\n"
    if args.check:
        if not args.output.exists() or args.output.read_bytes() != data:
            parser.exit(1, "Discovery reference is stale; regenerate tools/dsl_reference.py\n")
    else:
        args.output.write_bytes(data)
    print(str(args.output))


if __name__ == "__main__":
    main()
