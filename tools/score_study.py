"""Read MusicXML scores as arrangements: who plays, where, how busy, in which register, with whom.

    python tools/score_study.py SCORE.mxl             # one score: the piece, each part, every 4 bars
    python tools/score_study.py FOLDER -o stats.json  # every .mxl, .mxl.zip, .musicxml and .xml in it, a row each

Statistics only: counts, shares and percentiles per part and per stretch, never a sequence of notes. Scores of
other people's music stay out of the repository (keep them under private/); what a study keeps is these numbers.
The piece's own numbers are `tare.tools.tune.score.arrangement`, the same reading `Score.arrangement()` and
`dsl review` give our scores, so a reference and a piece of ours are held to one ruler.
"""
import argparse
import json
import statistics as st
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from tare.tools.tune.score import arrangement  # noqa: E402

STEP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def name(midi) -> str:
    return f"{NAMES[int(midi) % 12]}{int(midi) // 12 - 1}"


def percentile(values, q):
    values = sorted(values)
    return values[min(int(q / 100 * len(values)), len(values) - 1)]


def xml_of(path: Path) -> bytes:
    """The score inside a file: MusicXML as it is, or the largest XML of a .mxl archive (never extracted)."""
    if not zipfile.is_zipfile(path):
        return path.read_bytes()
    with zipfile.ZipFile(path) as z:
        members = [i for i in z.infolist() if not i.filename.startswith("META-INF")
                   and i.filename.endswith((".xml", ".musicxml"))]
        if not members:
            raise ValueError(f"no score in {path.name}")
        return z.read(max(members, key=lambda i: i.file_size))


def read(data: bytes):
    """Parts as lists of notes ({bar, beat, dur, pitch or None}), and the piece's tempo, meter and length."""
    root = ET.fromstring(data)
    parts, tempos, bar_beats, bars = {}, [], 4.0, 0
    labels = {sp.get("id"): " ".join((sp.findtext("part-name") or "").split()) for sp in root.iter("score-part")}
    for part in root.iter("part"):
        notes, staccato, divisions, beat = [], 0, 1, 0.0
        for bar, measure in enumerate(part.iter("measure")):
            pos = last = 0.0
            for el in measure:
                if el.tag == "attributes":
                    divisions = int(el.findtext("divisions") or divisions)
                    if el.find("time") is not None:
                        bar_beats = int(el.findtext("time/beats")) * 4 / int(el.findtext("time/beat-type"))
                elif el.tag == "direction" and el.find("sound") is not None and el.find("sound").get("tempo"):
                    tempos.append(float(el.find("sound").get("tempo")))
                elif el.tag in ("backup", "forward"):
                    pos += (-1 if el.tag == "backup" else 1) * int(el.findtext("duration")) / divisions
                elif el.tag == "note" and el.find("grace") is None:
                    dur = int(el.findtext("duration") or 0) / divisions
                    start = last if el.find("chord") is not None else pos
                    if el.find("chord") is None:
                        last, pos = pos, pos + dur
                    if el.find("rest") is not None:
                        continue
                    staccato += el.find("notations/articulations/staccato") is not None
                    pitch = el.find("pitch")
                    midi = None if pitch is None else (12 * (int(pitch.findtext("octave")) + 1) +
                                                       STEP[pitch.findtext("step")] +
                                                       int(float(pitch.findtext("alter") or 0)))
                    if any(t.get("type") == "stop" for t in el.findall("tie")) and notes and \
                            notes[-1]["pitch"] == midi:
                        notes[-1]["dur"] += dur                 # a tie is one note
                        continue
                    notes.append({"bar": bar, "beat": beat + start, "dur": dur, "pitch": midi})
            beat += bar_beats
            bars = max(bars, bar + 1)
        if notes:
            key = labels.get(part.get("id")) or part.get("id")
            while key in parts:
                key += " 2"
            parts[key] = {"notes": notes, "staccato": staccato}
    return parts, {"bars": bars, "bar_beats": bar_beats, "bpm": tempos[0] if tempos else None,
                   "tempo_changes": len(set(tempos)) > 1}


def study(path: Path) -> dict:
    parts, info = read(xml_of(path))
    rows = {}
    for label, part in parts.items():
        notes = part["notes"]
        pitches = [n["pitch"] for n in notes if n["pitch"] is not None]
        active = {n["bar"] for n in notes}
        rows[label] = {
            "notes": len(notes), "bars_active_share": round(len(active) / info["bars"], 2),
            "first_bar": min(active) + 1, "notes_per_active_bar": round(len(notes) / len(active), 1),
            "median_beats": st.median(n["dur"] for n in notes),
            "sixteenth_or_shorter_share": round(sum(n["dur"] <= 0.25 for n in notes) / len(notes), 2),
            "long_share": round(sum(n["dur"] >= 2 for n in notes) / len(notes), 2),
            "staccato_share": round(part["staccato"] / len(notes), 2),
            "register": [name(percentile(pitches, 10)), name(st.median(pitches)), name(percentile(pitches, 90))]
            if pitches else None,
        }
    layout = arrangement({label: [(n["beat"], n["pitch"]) for n in part["notes"]] for label, part in parts.items()},
                         info["bar_beats"])
    busiest = max(rows, key=lambda k: rows[k]["notes_per_active_bar"] * rows[k]["bars_active_share"])
    seconds = info["bars"] * info["bar_beats"] * 60 / info["bpm"] if info["bpm"] else None
    return {"piece": path.name.split(".")[0], **info, "seconds_at_first_tempo": round(seconds, 1) if seconds else None,
            "busiest_part": busiest, "busiest_is_percussion": rows[busiest]["register"] is None, **layout,
            "by_part": rows}


def show(d: dict, parts: bool):
    line = (f"{d['piece'][:40]:40} {d['bars']:4} bars {d['bpm'] or 0:4.0f} bpm{'*' if d['tempo_changes'] else ' '} "
            f"{d['parts']:2} parts | per attack {d['notes_per_attack']:.2f}, leaps {d['leaps_share']:.2f}, "
            f"doubling {d['doubling']:.1f}, distinct/bar {d['distinct_notes_per_bar']:5.1f} | parts x"
            f"{d['parts_growth']}, density x{d['density_ratio']} | busiest: {d['busiest_part'][:18]}")
    print(line)
    if parts:
        print(f"\n{'part':24} notes active first n/bar  beats  16th  long  stac  register")
        for label, r in d["by_part"].items():
            print(f"{label[:24]:24} {r['notes']:5} {r['bars_active_share']:6.2f} {r['first_bar']:5} "
                  f"{r['notes_per_active_bar']:5.1f} {r['median_beats']:6.2f} {r['sixteenth_or_shorter_share']:5.2f} "
                  f"{r['long_share']:5.2f} {r['staccato_share']:5.2f}  {'/'.join(r['register'] or ['percussion'])}")
        print("\nparts per 4 bars:", d["parts_by_block"], "\nnotes per bar:   ", d["notes_per_bar_by_block"])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    files = [args.path] if args.path.is_file() else sorted(
        p for p in args.path.iterdir() if p.name.endswith((".mxl", ".mxl.zip", ".musicxml", ".xml")))
    rows = [study(p) for p in files]
    for row in rows:
        show(row, parts=len(rows) == 1)
    if len(rows) > 1:
        print("* the tempo changes: seconds use the first marking")
        print("shared:", dict(Counter({
            "one note per attack (<= 1.4)": sum(r["notes_per_attack"] <= 1.4 for r in rows),
            "leaps <= 0.2": sum(r["leaps_share"] <= 0.2 for r in rows),
            "parts grow >= 1.5x": sum(r["parts_growth"] >= 1.5 for r in rows),
            "density >= 2x": sum(r["density_ratio"] >= 2 for r in rows),
            "busiest part is percussion": sum(r["busiest_is_percussion"] for r in rows)})), "of", len(rows))
    if args.output:
        args.output.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")


def demo():
    """Two bars: a violin line by step with one leap, a snare on every eighth of bar 2."""
    def note(step, octave, dur=1):
        return (f"<note><pitch><step>{step}</step><octave>{octave}</octave></pitch>"
                f"<duration>{dur}</duration></note>")

    drum = "<note><unpitched/><duration>1</duration></note>" * 4
    xml = f"""<score-partwise><part-list><score-part id="P1"><part-name>Violin</part-name></score-part>
        <score-part id="P2"><part-name>Snare</part-name></score-part></part-list>
        <part id="P1"><measure><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type>
        </time></attributes><direction><sound tempo="120"/></direction>{note('C', 4)}{note('D', 4)}{note('E', 4)}
        {note('C', 5)}</measure><measure>{note('C', 5, 4)}</measure></part>
        <part id="P2"><measure><attributes><divisions>1</divisions></attributes>
        <note><rest/><duration>4</duration></note></measure><measure>{drum}</measure></part></score-partwise>"""
    parts, info = read(xml.encode())
    assert info == {"bars": 2, "bar_beats": 4.0, "bpm": 120.0, "tempo_changes": False}, info
    assert [n["pitch"] for n in parts["Violin"]["notes"]] == [60, 62, 64, 72, 72]
    assert [n["beat"] for n in parts["Snare"]["notes"]] == [4.0, 5.0, 6.0, 7.0]
    layout = arrangement({k: [(n["beat"], n["pitch"]) for n in v["notes"]] for k, v in parts.items()}, 4, 1)
    assert layout["leaps_share"] == 0.25 and layout["parts_by_block"] == [1, 2], layout


if __name__ == "__main__":
    demo() if sys.argv[1:] == ["demo"] else main()
