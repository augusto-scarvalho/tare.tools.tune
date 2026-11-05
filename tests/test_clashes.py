"""Notes that rub (a minor second or ninth held together) in the generated music, found in the score without
rendering. Most cues have a few on purpose (passing tones, a Phrygian half step); this holds each cue to the count it
has now, so a change to a generator cannot add rubs unnoticed. A fix that removes some passes and says so.

    python tests/test_clashes.py   # rewrite the counts after a deliberate change to the music
"""
import json
from pathlib import Path

from tare.tools.tune.music import CUES, Cue
from tare.tools.tune.score import Score

COUNTS = Path(__file__).parent / "fixtures" / "clashes.json"
STYLES = ("orchestral", "snes", "chip")


def counts() -> dict[str, int]:
    return {f"{kind}/{style}": len(Cue(kind, style, seed=1, sr=16_000).score.clashes()) for kind in CUES
            for style in STYLES}


def test_a_held_minor_ninth_rubs_and_drums_do_not():
    s = Score(bpm=120, sr=16_000)
    s.track("pad").play("strings", [("C4", 0, 2), ("E4", 0, 2)])
    s.track("lead").play("flute", [("C#5", 1, 1)])           # a minor ninth over the held C4
    s.track("bells").play("glockenspiel", [("C#5", 3, 1)])   # after the pad: nothing to rub against
    s.track("drums").play("snare", [(61, 0, 2)])              # percussion is never pitched
    s.track("choir").play("choir", [(["E4", "F4"], 4, 2)])   # a half step built into a held chord
    line, chord = s.clashes()
    assert sorted(line["notes"]) == [("lead", 73.0), ("pad", 60.0)] and line["bar"] == 1 and line["beats"] == 1.0
    assert line["kind"] == "line" and not line["same_track"] and line["interval"] == 13
    assert chord["kind"] == "chord" and chord["same_track"] and chord["interval"] == 1 and chord["bar"] == 2


def test_no_cue_gains_clashes():
    now, before = counts(), json.loads(COUNTS.read_text(encoding="utf-8"))
    assert set(now) == set(before)
    worse = {k: (before[k], n) for k, n in now.items() if n > before[k]}
    better = {k: (before[k], n) for k, n in now.items() if n < before[k]}
    print(f"\n{sum(now.values())} clashes in {len(now)} cues" + (f"; fewer than recorded in {better}: rewrite the"
                                                                   " counts" if better else ""))
    assert not worse, f"more clashes than recorded (before, now): {worse}"


if __name__ == "__main__":
    data = counts()
    COUNTS.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(COUNTS, sum(data.values()), "clashes")
