"""Curation by ear: rounds of sounds to compare, with the tasks that need a human, served on this machine only.

A round is a folder: manifest.json (groups of segments, the tasks for each group) and the audio. The page
(tools/curate.html) plays the segments, switches between them at the same moment, matches their loudness, draws
their spectrograms, their difference to a reference and their average spectra, and saves the answers to
answers.json in the same folder as they are given. Reference recordings and game audio stay on this machine:
the server listens on 127.0.0.1 only.

    python tools/curate.py serve                 # http://127.0.0.1:8765, the rounds under ROOT
    python tools/curate.py answers ROUND         # what was answered, in short

Writing a round from a script:

    sys.path.insert(0, "tools"); from curate import Round
    r = Round("chiado", title="O chiado do vocoder", intro="Qual soa menos robótico?")
    g = r.group("kiai 1", tasks=["pick", "rate:robótico", "marks", "notes"], reference="original")
    g.add("original", "kiai.opus")                       # a file (any format the browser plays) ...
    g.add("nosso", samples, sr=44100, metrics={"hnr_2-4k": 8.1})   # ... or samples
    r.save()

A round made again under the same name keeps its earlier answers aside (answers-<time>.json).

Tasks: "pick" (the best one, or none), "rate:<what>|<what 1 means>|<what 5 means>" (1-5 per segment),
"label:<a>|<b>|..." (a category per segment), "abx:<label A>|<label B>" (blind: is X A or B?), "marks" (moments or
stretches on a spectrogram, with a note), "notes" (free text). A blind round hides the labels and the metrics and
shuffles the order until revealed.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import wave
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import numpy as np

ROOT = Path(os.environ.get("TARE_CURATE_ROOT", Path.home() / "Documents" / "tare-referencias" / "rascunho" /
                           "curadoria"))
PAGE = Path(__file__).resolve().parent / "curate.html"
KINDS = ("pick", "rate", "label", "abx", "marks", "notes")


def task(spec: str) -> dict:
    """"rate:robótico" -> {"id": "rate:robótico", "type": "rate", "what": "robótico"}"""
    kind, _, arg = spec.partition(":")
    if kind not in KINDS:
        raise ValueError(f"unknown task {spec!r}; kinds: {', '.join(KINDS)}")
    out = {"id": spec, "type": kind}
    if kind == "rate":                                  # "rate:robótico|natural|robô": what, what 1 and 5 mean
        what, low, high = (arg.split("|") + ["", "", ""])[:3]
        out.update(what=what or "qualidade", low=low or "pouco", high=high or "muito")
    elif kind in ("label", "abx"):
        out["options"] = [o for o in arg.split("|") if o]
        if kind == "abx" and len(out["options"]) != 2:
            raise ValueError("abx compares two segments: 'abx:<label A>|<label B>'")
    return out


class Group:
    def __init__(self, rnd: "Round", gid: str, title: str, note: str, tasks: list, reference: str | None,
                 targets: dict | None):
        self.round, self.id, self.segments = rnd, gid, []
        self.data = {"id": gid, "title": title, "note": note, "tasks": [task(t) for t in tasks],
                     "reference": reference, "targets": targets or {}, "segments": self.segments}

    def add(self, label: str, audio, sr: int | None = None, metrics: dict | None = None, note: str = "") -> str:
        """A segment: a file (copied in) or mono/stereo samples in -1..1 (written as 16-bit WAV)."""
        sid = f"{self.id}s{len(self.segments) + 1}"
        audio_dir = self.round.dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        if isinstance(audio, str | Path):
            src = Path(audio)
            dest = audio_dir / f"{sid}{src.suffix.lower()}"
            shutil.copyfile(src, dest)
        else:
            if not sr:
                raise ValueError("samples need their sample rate (sr=...)")
            dest = audio_dir / f"{sid}.wav"
            write_wav16(dest, np.asarray(audio, dtype=np.float64), sr)
        self.segments.append({"id": sid, "label": label, "file": f"audio/{dest.name}", "note": note,
                              "metrics": {k: (round(float(v), 3) if v is not None else None)
                                          for k, v in (metrics or {}).items()}})
        return sid


class Round:
    def __init__(self, name: str, title: str = "", intro: str = "", blind: bool = False, root: Path = ROOT):
        self.dir = Path(root) / name
        if self.dir.exists():                           # a fresh round: the old audio goes, old answers kept aside
            shutil.rmtree(self.dir / "audio", ignore_errors=True)
            if (old := self.dir / "answers.json").exists():
                old.replace(self.dir / f"answers-{int(old.stat().st_mtime)}.json")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.groups: list[Group] = []
        self.data = {"name": name, "title": title or name, "intro": intro, "blind": blind, "groups": []}

    def group(self, title: str, note: str = "", tasks=("pick", "notes"), reference: str | None = None,
              targets: dict | None = None) -> Group:
        """A set of segments heard together. `reference`: the label of the segment the others are diffed against;
        `targets`: metric values to compare with (e.g. measured on the real thing)."""
        g = Group(self, f"g{len(self.groups) + 1}", title, note, list(tasks), reference, targets)
        self.groups.append(g)
        return g

    def save(self) -> Path:
        self.data["groups"] = [g.data for g in self.groups]
        for g in self.data["groups"]:
            labels = {s["label"]: s["id"] for s in g["segments"]}
            if g["reference"] is not None:
                g["reference"] = labels.get(g["reference"], g["reference"])
            for t in g["tasks"]:
                if t["type"] == "abx":
                    t["a"], t["b"] = (labels[o] for o in t["options"])
                    t["x"] = t["a"] if _coin(self.data["name"], g["id"]) else t["b"]
        path = self.dir / "manifest.json"
        path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        return path


def _coin(*parts) -> bool:
    return hashlib.sha256("/".join(parts).encode()).digest()[0] % 2 == 0


def write_wav16(path: Path, x: np.ndarray, sr: int):
    x = np.clip(x, -1.0, 1.0)
    ch = 1 if x.ndim == 1 else x.shape[1]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes((x * 32767).astype("<i2").tobytes())


def rounds(root: Path = ROOT) -> list[dict]:
    out = []
    for m in sorted(Path(root).glob("*/manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = json.loads(m.read_text(encoding="utf-8"))
        answers = _answers(m.parent)
        done = sum(1 for g in data["groups"] if any(v not in (None, "", [], {}) for v in answers.get(g["id"], {})
                                                     .values()))
        out.append({"name": m.parent.name, "title": data["title"], "groups": len(data["groups"]), "answered": done})
    return out


def _answers(d: Path) -> dict:
    p = d / "answers.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _inside(base: Path, rel: str) -> Path | None:
    p = (base / rel).resolve()
    return p if p.is_relative_to(base.resolve()) and p.is_file() else None


TYPES = {".wav": "audio/wav", ".opus": "audio/ogg", ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
         ".flac": "audio/flac", ".png": "image/png", ".json": "application/json"}


def handler(root: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body: bytes, kind: str, code: int = 200):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200):
            self._send(json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8", code)

        def _round(self, name: str) -> Path | None:
            d = (root / name).resolve()
            return d if d.parent == root.resolve() and (d / "manifest.json").is_file() else None

        def do_GET(self):
            parts = [unquote(p) for p in urlparse(self.path).path.split("/") if p]
            if not parts:
                return self._send(PAGE.read_bytes(), "text/html; charset=utf-8")
            if parts == ["api", "rounds"]:
                return self._json(rounds(root))
            if len(parts) == 3 and parts[:2] == ["api", "round"] and (d := self._round(parts[2])):
                manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
                return self._json({"manifest": manifest, "answers": _answers(d)})
            if len(parts) >= 3 and parts[0] == "files" and (d := self._round(parts[1])):
                if f := _inside(d, "/".join(parts[2:])):
                    return self._send(f.read_bytes(), TYPES.get(f.suffix.lower(), "application/octet-stream"))
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            parts = [unquote(p) for p in urlparse(self.path).path.split("/") if p]
            if len(parts) == 4 and parts[:2] == ["api", "round"] and parts[3] == "answers" and \
                    (d := self._round(parts[2])):
                answers = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if not isinstance(answers, dict):
                    return self._json({"error": "answers must be an object"}, 400)
                tmp = d / "answers.json.tmp"
                tmp.write_text(json.dumps(answers, ensure_ascii=False, indent=1), encoding="utf-8")
                tmp.replace(d / "answers.json")
                return self._json({"ok": True})
            self._json({"error": "not found"}, 404)

    return Handler


def serve(root: Path = ROOT, port: int = 8765, open_browser: bool = True) -> ThreadingHTTPServer:
    root.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler(root))
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{server.server_address[1]}/")
    return server


def summary(name: str, root: Path = ROOT) -> str:
    d = root / name
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    answers, lines = _answers(d), [manifest["title"]]
    for g in manifest["groups"]:
        labels = {s["id"]: s["label"] for s in g["segments"]}
        lines.append(f"== {g['title']}")
        for t in g["tasks"]:
            v = answers.get(g["id"], {}).get(t["id"])
            if v in (None, "", [], {}):
                continue
            if t["type"] == "pick":
                v = labels.get(v, "nenhum")
            elif t["type"] in ("rate", "label"):
                v = ", ".join(f"{labels.get(s, s)}: {x}" for s, x in v.items())
            elif t["type"] == "marks":
                def when(m):
                    return f"{m['t']:.2f}" + (f"-{m['t2']:.2f}" if m.get("t2") is not None else "")
                v = "; ".join(f"{labels.get(m['seg'], m['seg'])} @ {when(m)}s {m.get('note', '')}" for m in v)
            elif t["type"] == "abx":
                v = f"disse X = {labels.get(v.get('answer'), '?')} (X era {labels.get(t['x'])})"
            lines.append(f"   {t['id']}: {v}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="serve the rounds on 127.0.0.1")
    s.add_argument("--root", type=Path, default=ROOT)
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-open", action="store_true")
    a = sub.add_parser("answers", help="what was answered in a round")
    a.add_argument("name")
    a.add_argument("--root", type=Path, default=ROOT)
    args = ap.parse_args(argv)
    if args.cmd == "answers":
        print(summary(args.name, args.root))
        return
    server = serve(args.root, args.port, not args.no_open)
    print(f"curadoria em http://127.0.0.1:{server.server_address[1]}/  (rodadas em {args.root}; Ctrl+C para parar)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
