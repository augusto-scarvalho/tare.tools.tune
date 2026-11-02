"""Generate blind listening rounds for optional DSP; no acoustic approval is implied."""
import argparse
import sys
from pathlib import Path

from tare.tools.tune import capture
from tare.tools.tune.bundles import save_bundle
from tare.tools.tune.effects import fm_tone
from tare.tools.tune.score import Score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from curate import compare_bundles  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("authoring-out/listening"))
    args = parser.parse_args()
    sr = 48000
    base = Score(bpm=120, sr=sr, hall=0.3)
    base.track("harp").play("harp", [("C4", 0, 1), ("E4", 1, 1), ("G4", 2, 2)])
    original = save_bundle(capture(base, loop=2), args.out / "bundles")
    base.effects = [{"type": "chorus", "mix": 0.3}]
    chorus = save_bundle(capture(base, loop=2), args.out / "bundles")
    print(compare_bundles("chorus", original, chorus, root=args.out / "rounds"))
    base.effects = [{"type": "limiter", "ceiling": 0.35}]
    limiter = save_bundle(capture(base, loop=2), args.out / "bundles")
    print(compare_bundles("limiter", original, limiter, root=args.out / "rounds"))
    clean = save_bundle(capture(fm_tone(sr=sr, index=0), sr), args.out / "bundles")
    fm = save_bundle(capture(fm_tone(sr=sr, index=3), sr), args.out / "bundles")
    print(compare_bundles("fm", clean, fm, root=args.out / "rounds"))


if __name__ == "__main__":
    main()
