"""A clean, bounded process per authoring build; never run user Python files."""

import argparse
import json
import sys

from .authoring import build_file
from .bundles import save_bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("out")
    parser.add_argument("--name")
    parser.add_argument("--asset-root", action="append", default=[])
    args = parser.parse_args()
    from .dsl.model import DSLError

    try:
        result = build_file(args.project, name=args.name, asset_roots=args.asset_root)
    except DSLError as exc:
        print(json.dumps(exc.to_dict(), ensure_ascii=False), file=sys.stderr)
        raise SystemExit(exc.exit_code) from None
    saved = save_bundle(result, args.out)
    print(json.dumps({"revision": saved.name}))


if __name__ == "__main__":
    main()
