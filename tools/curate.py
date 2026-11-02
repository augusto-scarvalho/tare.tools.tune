"""Curation by ear: rounds of sounds to compare, with the tasks that need a human, served on this machine only.

A round is a folder: manifest.json (groups of segments, the tasks for each group) and the audio. The page
(tools/curate.html) plays the segments, switches between them at the same moment, matches their loudness, draws
their spectrograms, their difference to a reference and their average spectra, and saves the answers to
answers.json in the same folder as they are given. Reference recordings and game audio stay on this machine:
the server listens on 127.0.0.1 only.

    python tools/curate.py serve                 # http://127.0.0.1:8765, the rounds under ROOT
    python tools/curate.py answers ROUND         # what was answered, in short (--json: as data, per bundle)
    python tools/curate.py compare ROUND B1 B2 [B3 ...] --question "..."   # dsl review bundles, for the ear
    python tools/curate.py predict ROUND predictions.json   # the assistant's reading, before the listening
    python tools/curate.py agree R1 R2 ...       # those readings against the answers, summed over the rounds

Writing a round from a script:

    sys.path.insert(0, "tools"); from curate import Round
    r = Round("chiado", title="O chiado do vocoder", intro="Qual soa menos robótico?")
    g = r.group("kiai 1", tasks=["pick", "rate:robótico", "marks", "notes"], reference="original")
    g.add("original", "kiai.opus")                       # a file (any format the browser plays) ...
    g.add("nosso", samples, sr=44100, metrics={"hnr_2-4k": 8.1})   # ... or samples
    r.save()

A round made again under the same name retains immutable revisions and revision-bound evaluations.

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
import socket
import sys
import tempfile
import wave
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from tare.tools.tune.bundles import atomic_json, file_lock  # noqa: E402
from tare.tools.tune.diagnostics import canonical, digest  # noqa: E402

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

    def add(self, label: str, audio, sr: int | None = None, metrics: dict | None = None, note: str = "",
            provenance: dict | None = None) -> str:
        """A segment: a file (copied in) or mono/stereo samples in -1..1 (written as 16-bit WAV)."""
        if self.round.finished:
            raise ValueError("published rounds are immutable; create a new Round")
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
                              "provenance": provenance or {},
                              "metrics": {k: (round(float(v), 3) if v is not None else None)
                                          for k, v in (metrics or {}).items()}})
        return sid


class Round:
    def __init__(self, name: str, title: str = "", intro: str = "", blind: bool = False, root: Path = ROOT,
                 match: bool = True):
        if Path(name).name != name or name in (".", ".."):
            raise ValueError("round name must be one directory name")
        self.home = Path(root) / name
        self.home.mkdir(parents=True, exist_ok=True)
        self.finished = False
        with file_lock(self.home / ".round.lock"):
            requested = self.home / "requested.json"
            self.generation = json.loads(requested.read_text())["generation"] + 1 if requested.exists() else 1
            atomic_json(requested, {"generation": self.generation})
        self.dir = Path(tempfile.mkdtemp(prefix=".round-", dir=self.home))
        self.groups: list[Group] = []
        self.data = {"name": name, "title": title or name, "intro": intro, "blind": blind, "groups": []}
        if not match:                                   # the page opens with loudness matching off: level is judged
            self.data["match"] = False

    def group(self, title: str, note: str = "", tasks=("pick", "notes"), reference: str | None = None,
              targets: dict | None = None) -> Group:
        """A set of segments heard together. `reference`: the label of the segment the others are diffed against;
        `targets`: metric values to compare with (e.g. measured on the real thing)."""
        if self.finished:
            raise ValueError("published rounds are immutable; create a new Round")
        g = Group(self, f"g{len(self.groups) + 1}", title, note, list(tasks), reference, targets)
        self.groups.append(g)
        return g

    def save(self) -> Path:
        if self.finished:
            raise ValueError("published rounds are immutable; create a new Round")
        self.data["groups"] = [g.data for g in self.groups]
        for g in self.data["groups"]:
            labels = {s["label"]: s["id"] for s in g["segments"]}
            if g["reference"] is not None:
                g["reference"] = labels.get(g["reference"], g["reference"])
            for t in g["tasks"]:
                if t["type"] == "abx":
                    t["a"], t["b"] = (labels[o] for o in t["options"])
                    t["x"] = t["a"] if _coin(self.data["name"], g["id"]) else t["b"]
        assets = {s["file"]: hashlib.sha256((self.dir / s["file"]).read_bytes()).hexdigest()
                  for g in self.groups for s in g.segments}
        self.data["assets"] = assets
        revision = digest(self.data)
        self.data["revision"] = revision
        atomic_json(self.dir / "manifest.json", self.data)
        with file_lock(self.home / ".round.lock"):
            old = self.home / "manifest.json"
            if old.exists():
                previous = json.loads(old.read_text(encoding="utf-8"))
                old_revision = previous.get("revision", digest(previous))
                archive = self.home / "revisions" / old_revision
                if not archive.exists():
                    archive.mkdir(parents=True)
                    for group in previous["groups"]:
                        for seg in group["segments"]:
                            src = _inside(self.home, seg["file"])
                            if src:
                                dst = archive / seg["file"]
                                dst.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copyfile(src, dst)
                    previous["revision"] = old_revision
                    atomic_json(archive / "manifest.json", previous)
                answers = self.home / "answers.json"
                if answers.exists() and not (archive / "answers.json").exists():
                    shutil.copyfile(answers, archive / "answers.json")
            destination = self.home / "revisions" / revision
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                os.replace(self.dir, destination)
            else:
                assert self.dir.resolve().parent == self.home.resolve() and self.dir.name.startswith(".round-")
                shutil.rmtree(self.dir)
            self.finished = True
            self.dir = destination
            if json.loads((self.home / "requested.json").read_text())["generation"] != self.generation:
                raise ValueError("stale round retained in history; newer generation requested")
            public = _public_manifest(self.home, revision)
            atomic_json(self.home / "manifest.json", public)
            atomic_json(self.home / "answers.json", _answer_state(self.home, revision)["answers"])
        return self.home / "manifest.json"


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


def _public_manifest(home, revision):
    if not isinstance(revision, str) or len(revision) != 64 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("invalid round revision")
    manifest = json.loads((home / "revisions" / revision / "manifest.json").read_text(encoding="utf-8"))
    for group in manifest["groups"]:
        for seg in group["segments"]:
            seg["file"] = f"revisions/{revision}/{seg['file']}"
    return manifest


def _answer_state(home, revision):
    path = home / "evaluations" / f"{revision}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    historical = home / "revisions" / revision / "answers.json"
    return {"revision": revision, "version": 0, "answers": _answers(historical.parent), "listening": {}}


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
                revision = parse_qs(urlparse(self.path).query).get("revision", [manifest.get("revision")])[0]
                if revision:
                    try:
                        manifest = _public_manifest(d, revision)
                    except (ValueError, FileNotFoundError):
                        return self._json({"error": "revision not found"}, 404)
                    state = _answer_state(d, revision)
                else:
                    state = {"answers": _answers(d), "version": 0, "listening": {}}
                return self._json({"manifest": manifest, "answers": state["answers"],
                                   "answer_version": state["version"], "listening": state["listening"],
                                   "revisions": [p.name for p in (d / "revisions").glob("*") if p.is_dir()]})
            if len(parts) >= 3 and parts[0] == "files" and (d := self._round(parts[1])):
                if f := _inside(d, "/".join(parts[2:])):
                    return self._send(f.read_bytes(), TYPES.get(f.suffix.lower(), "application/octet-stream"))
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            parts = [unquote(p) for p in urlparse(self.path).path.split("/") if p]
            if len(parts) == 4 and parts[:2] == ["api", "round"] and parts[3] == "answers" and \
                    (d := self._round(parts[2])):
                length = int(self.headers.get("Content-Length", 0))
                if length > 1024 * 1024:
                    return self._json({"error": "answer document is too large"}, 413)
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                    canonical(body)
                except (ValueError, json.JSONDecodeError):
                    return self._json({"error": "invalid answer JSON"}, 400)
                if not isinstance(body, dict):
                    return self._json({"error": "answers must be an object"}, 400)
                with file_lock(d / ".round.lock"):
                    latest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
                    revision = body.get("revision")
                    if revision is None:
                        # One initial legacy write is accepted; subsequent clients must send preconditions.
                        revision = latest.get("revision")
                        if not revision or len(list((d / "revisions").glob("*"))) != 1 or \
                                (d / "evaluations" / f"{revision}.json").exists():
                            return self._json({"error": "reload this revision before saving"}, 409)
                        answers, version, listening = body, 0, {}
                    else:
                        answers, version = body.get("answers"), body.get("version")
                        listening = body.get("listening", {})
                    try:
                        _public_manifest(d, revision)
                    except (ValueError, TypeError, FileNotFoundError):
                        return self._json({"error": "revision not found"}, 409)
                    state = _answer_state(d, revision)
                    if version != state["version"]:
                        return self._json({"error": "answers changed elsewhere; reload before saving"}, 409)
                    if not isinstance(answers, dict) or not isinstance(listening, dict):
                        return self._json({"error": "answers and listening settings must be objects"}, 400)
                    state.update(answers=answers, version=version + 1, listening=listening)
                    if "predicted" not in state and _given(answers):  # the prediction as the first answer found it
                        made = d / "predictions" / f"{revision}.json"
                        state["predicted"] = hashlib.sha256(made.read_bytes()).hexdigest() if made.exists() else None
                    atomic_json(d / "evaluations" / f"{revision}.json", state)
                    if revision == latest.get("revision"):
                        atomic_json(d / "answers.json", answers)
                return self._json({"ok": True, "version": state["version"]})
            self._json({"error": "not found"}, 404)

    return Handler


def serve(root: Path = ROOT, port: int = 8765, open_browser: bool = True) -> ThreadingHTTPServer:
    root.mkdir(parents=True, exist_ok=True)
    class LocalServer(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = os.name != "nt"

        def server_bind(self):
            if os.name == "nt":
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()
    server = LocalServer(("127.0.0.1", port), handler(root))
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


def answers_json(name: str, root: Path = ROOT) -> dict:
    """The answers as data for an agent: answered tasks only, segments keyed by label with their retained bundle."""
    d = Path(root) / name
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    answers, groups = _answers(d), []
    for g in manifest["groups"]:
        key = {s["id"]: s["label"] for s in g["segments"]}
        if len(set(key.values())) < len(key):           # duplicate labels: fall back to the unique segment ids
            key = {s["id"]: s["id"] for s in g["segments"]}
        got = {}
        for t in g["tasks"]:
            v = answers.get(g["id"], {}).get(t["id"])
            if v in (None, "", [], {}):
                continue
            if t["type"] == "pick":
                v = key.get(v, v)                           # "none" stays "none"
            elif t["type"] in ("rate", "label"):
                v = {key.get(s, s): x for s, x in v.items() if x is not None}
            elif t["type"] == "marks":
                v = [dict(m, seg=key.get(m["seg"], m["seg"])) for m in v]
            elif t["type"] == "abx":
                v = {"answer": key.get(v.get("answer")), "x": key.get(t["x"]), "correct": v.get("answer") == t["x"]}
            got[t["id"]] = v
        groups.append({"id": g["id"], "title": g["title"], "answers": got,
                       "segments": {key[s["id"]]: s.get("provenance", {}).get("bundle") or
                                    s.get("provenance", {}).get("file", s["file"])
                                    for s in g["segments"]}})
    return {"round": name, "revision": manifest.get("revision"), "groups": groups}


def _measures(audio, sr, fmax, end_db):
    """The cards' shared numbers (analysis.measures): one band and one end for all, so a 16 kHz render is not
    "darker" and a recording's noise does not lengthen only the recording."""
    from tare.tools.tune.analysis import measures
    m = measures(audio, sr, fmax, end_db=end_db)
    if m["status"] != "measured":
        return {}
    f0 = m["f0"].get("median_hz") if m["f0"]["status"] in ("measured", "unreliable", "ring") else None
    return {"active_s": m["active_s"], "attack_ms": m["attack_ms"], "centroid_hz": m["centroid_hz"], "f0_hz": f0}


def compare_bundles(name, *bundles, root=ROOT, blind=True, tasks=None, question="", keep_levels=False,
                    reference=None):
    """A round over the exact retained playback artifacts of 2-9 bundles, labelled A, B, ... in the given order.

    Two bundles default to blind ABX; more default to pick/rate. Each segment keeps its bundle path, so the answers
    (answers_json) point straight back at the observation a `dsl edit --from-bundle` needs. `reference`: a recording
    played first as REF, the card the others are diffed against, its measures the targets; the round is then open
    (a blind round hides the reference too)."""
    from tare.tools.tune.audio_io import read_channels
    from tare.tools.tune.bundles import load_bundle
    from tare.tools.tune.dsl.review_data import source_changes
    from tare.tools.tune.inspection import inspect_audio
    if not 2 <= len(bundles) <= 9:
        raise ValueError("compare 2 to 9 bundles (keys 1-9 play them)")
    captures = [load_bundle(path) for path in bundles]
    recording = read_channels(reference) if reference else None
    from tare.tools.tune.analysis import common_end_db
    signals = [(c.audio, c.sr) for c in captures] + ([recording] if recording else [])
    fmax, end_db = min(8000, *(sr / 2 - 100 for _, sr in signals)), common_end_db(*signals)
    if reference:
        blind = False
        tasks = tasks or ["pick", "rate:perto da referência|longe|igual", "marks", "notes"]
        question = question or "Which is closest to REF?"
    tasks = tasks or (["abx:A|B", "marks", "notes"] if len(bundles) == 2 else
                      ["pick", "rate:qualidade|ruim|ótimo", "marks", "notes"])
    rnd = Round(name, title=name, blind=blind, root=root, match=not keep_levels)
    targets = _measures(*recording, fmax, end_db) if recording else None
    group = rnd.group("Compare revisions", note=question, tasks=tasks, reference="REF" if reference else "A",
                      targets=targets)
    if reference:
        group.add("REF", Path(reference), note="the reference recording", metrics=targets,
                  provenance={"file": str(Path(reference).resolve())})
    first = None
    for label, path, captured in zip("ABCDEFGHI"[:len(bundles)], bundles, captures, strict=True):
        meta = captured.manifest.get("dsl", {})
        measured = inspect_audio(captured.audio, captured.sr, pitch=False)
        loudest = max(measured["levels"], key=lambda v: v["peak"])
        note = meta.get("sound", "")
        if first is None:
            first = meta
        elif meta and first:                              # what this candidate changed in the source, against A
            diff, inside = source_changes(first["document"], meta["document"], limit=3), f"/sounds/{note}"
            note += "".join(f"\n{r['pointer'].removeprefix(inside)}: " +
                            (f"{r['change']} {r['value']}" if "change" in r else f"{r['before']} → {r['after']}")
                            for r in diff["items"])
            note += f"\n(+{diff['total'] - len(diff['items'])})" if diff["truncated"] else ""
        group.add(label, Path(path) / "audio.wav", note=note.strip(),
                  metrics={"duration_s": measured["duration"], "peak_dbfs": loudest["peak_dbfs"],
                           "rms_dbfs": loudest["rms_dbfs"], **_measures(captured.audio, captured.sr, fmax, end_db)},
                  provenance={"bundle": str(Path(path).resolve()),
                              **{k: captured.manifest[k] for k in ("revision", "source_id", "pcm_id", "playback_id")}})
    return rnd.save()


def _given(answers: dict) -> bool:
    return any(v not in (None, "", [], {}) for g in answers.values() if isinstance(g, dict) for v in g.values())


def predict(name: str, predictions: dict, root: Path = ROOT) -> Path:
    """The assistant's reading of a round, recorded before anyone listens: per group id, "pick" (a label or "none"),
    "rate" ({label: 1-5}), "distinguishable" (an abx group: true or false) and "evidence" (one line: what it read).
    Refused once the round has an answer. Until `agree`, the assistant opens neither the page nor answers.json."""
    d = Path(root) / name
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    if _given(_answers(d)) or _given(_answer_state(d, manifest["revision"])["answers"]):
        raise ValueError(f"{name} already has answers: a prediction comes before the listening")
    groups = {g["id"]: g for g in manifest["groups"]}
    for gid, p in predictions.items():
        if gid not in groups or not isinstance(p, dict):
            raise ValueError(f"no group {gid!r} in {name}; groups: {', '.join(groups)}")
        labels = {s["label"] for s in groups[gid]["segments"]}
        rate = p.get("rate", {})
        if p.get("pick", "none") not in labels | {"none"} or not isinstance(rate, dict) or not set(rate) <= labels \
                or any(x not in range(1, 6) for x in rate.values()) \
                or not isinstance(p.get("distinguishable", True), bool):
            raise ValueError(f"{gid}: pick is a label or none, rate is {{label: 1-5}}, distinguishable true or false; "
                             f"labels {sorted(labels)}")
    path = d / "predictions" / f"{manifest['revision']}.json"
    path.parent.mkdir(exist_ok=True)
    atomic_json(path, {"revision": manifest["revision"], "groups": predictions})
    return path


def _picks(root: Path) -> list:
    """Every answered pick under `root`: (round, group, the group's sounds by content, the picked sound)."""
    out = []
    for m in Path(root).glob("*/manifest.json"):
        manifest, answers = json.loads(m.read_text(encoding="utf-8")), _answers(m.parent)
        assets, prefix = manifest.get("assets", {}), f"revisions/{manifest.get('revision')}/"
        for g in manifest["groups"]:
            pick = next((answers.get(g["id"], {}).get(t["id"]) for t in g["tasks"] if t["type"] == "pick"), None)
            sounds = {s["id"]: assets.get(s["file"].removeprefix(prefix)) for s in g["segments"]}
            if pick and None not in sounds.values():
                out.append((m.parent.name, g["id"], frozenset(sounds.values()), sounds.get(pick, "none")))
    return out


def lucky(hits: int, odds: list) -> float | None:
    """How often a guesser does at least as well: the chance of `hits` or more right when guess k is right with
    probability odds[k] (exact, a Poisson binomial)."""
    if not odds:
        return None
    dist = np.ones(1)
    for p in odds:
        dist = np.convolve(dist, [1 - p, p])
    return round(float(dist[hits:].sum()), 4)


def agree(names, root: Path = ROOT) -> dict:
    """The recorded predictions of one or more rounds against the listener's answers, summed, beside chance (with how
    often a guesser would do as well), a fixed numeric rule (in a group with targets, the candidate nearest the
    reference: |log active_s ratio| + |centroid st|/3 + env_db/8 + |attack ms|/10) and the listener's own
    consistency (the same sounds picked in another group or round). A few picks are a clue, never a licence."""
    from scipy.stats import spearmanr

    from tare.tools.tune.analysis import against
    from tare.tools.tune.audio_io import read_channels
    names = [names] if isinstance(names, str) else list(names)
    picks, rule, chance, abx, rates, same, rows, revisions = [], [], [], [], [], [], [], {}
    everyone = _picks(root)
    for name in names:
        d = Path(root) / name
        manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        revision = revisions[name] = manifest["revision"]
        path = d / "predictions" / f"{revision}.json"
        if not path.exists():
            raise ValueError(f"no prediction for this revision of {name}: curate.py predict comes before the listening")
        made, state = json.loads(path.read_text(encoding="utf-8")), _answer_state(d, revision)
        if "predicted" in state and state["predicted"] != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError(f"the prediction for {name} was recorded or changed after the first answer: it does not "
                             "count")
        for g in manifest["groups"]:
            p, a, label = made["groups"].get(g["id"], {}), state["answers"].get(g["id"], {}), {"none": "none"}
            label |= {s["id"]: s["label"] for s in g["segments"]}
            first = {}
            for t in g["tasks"]:
                first.setdefault(t["type"], t)
            pick = a.get(first["pick"]["id"]) if "pick" in first else None
            if pick:
                row = {"round": name, "group": g["id"], "listener": label.get(pick, pick), "assistant": p.get("pick")}
                candidates = [s for s in g["segments"] if s["id"] != g.get("reference")]
                if "pick" in p:
                    picks.append(p["pick"] == row["listener"])
                    chance.append(1 / len(candidates))
                ref = next((s for s in g["segments"] if s["id"] == g.get("reference")), None)
                if g.get("targets") and ref:
                    recording = read_channels(d / ref["file"])

                    def far(s, d=d, recording=recording):
                        m = against(*recording, *read_channels(d / s["file"])).get("measures", {})
                        if "env_db" not in m:
                            return float("inf")
                        return (abs(np.log(m["active_s"].get("ratio", 1)))
                                + abs(m["centroid_hz"].get("semitones", 0)) / 3
                                + m["env_db"]["mean_abs_db"] / 8 + abs(m["attack_ms"].get("delta", 0)) / 10)
                    row["rule"] = min(candidates, key=far)["label"]
                    rule.append(row["rule"] == row["listener"])
                mine = next((x for x in everyone if x[:2] == (name, g["id"])), None)
                earlier = [x[3] for x in everyone if mine and x[2] == mine[2] and x[:2] != mine[:2]]
                if earlier:
                    same.append(earlier[0] == mine[3])
                rows.append(row)
            x = a.get(first["abx"]["id"]) if "abx" in first else None
            if x and "distinguishable" in p:
                abx.append(p["distinguishable"] == (x.get("answer") == first["abx"]["x"]))
            if "rate" in first and "rate" in p:
                rates += [(p["rate"][label[s]], v) for s, v in (a.get(first["rate"]["id"]) or {}).items()
                          if v is not None and label.get(s) in p["rate"]]
    rho = float(spearmanr(*zip(*rates, strict=True))[0]) if len(rates) >= 3 else float("nan")
    return {"rounds": revisions, "groups": rows,
            "pick": {"n": len(picks), "assistant": sum(picks), "numeric_rule": [sum(rule), len(rule)],
                     "chance": round(sum(chance), 2), "lucky": lucky(sum(picks), chance)},
            "rate": {"n": len(rates), "spearman": None if np.isnan(rho) else round(rho, 2)},
            "abx": {"n": len(abx), "assistant": sum(abx), "chance": len(abx) / 2,
                    "lucky": lucky(sum(abx), [0.5] * len(abx))},
            "listener_repeats": {"n": len(same), "same_pick": sum(same)}}


def agree_text(r: dict) -> str:
    pick, rate, abx, again = r["pick"], r["rate"], r["abx"], r["listener_repeats"]

    def luck(block):
        return "" if block["lucky"] is None else f"; a guesser does as well {block['lucky']:.1%} of the time"
    out = [", ".join(f"{name} ({rev[:8]})" for name, rev in r["rounds"].items()),
           f"pick      assistant {pick['assistant']}/{pick['n']}, numeric rule {pick['numeric_rule'][0]}/"
           f"{pick['numeric_rule'][1]}, chance {pick['chance']}/{pick['n']}{luck(pick)}",
           f"rate      Spearman {rate['spearman']} over {rate['n']} ratings",
           f"abx       assistant {abx['assistant']}/{abx['n']} said whether the listener tells them apart, "
           f"chance {abx['chance']}/{abx['n']}{luck(abx)}",
           f"listener  same pick as in another group of the same sounds {again['same_pick']}/{again['n']}",
           "A few picks are a clue: under 20 picks, or a guesser doing as well 5% of the time or more, "
           "decides nothing."]
    out += [f"  {g['round']} {g['group']}: listener {g['listener']}, assistant {g['assistant']}" +
            (f", rule {g['rule']}" if "rule" in g else "") for g in r["groups"]]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="serve the rounds on 127.0.0.1")
    s.add_argument("--root", type=Path, default=ROOT)
    s.add_argument("--port", type=int, default=8765, help="default 8765: http://127.0.0.1:8765/")
    s.add_argument("--no-open", action="store_true")
    a = sub.add_parser("answers", help="what was answered in a round")
    a.add_argument("name")
    a.add_argument("--root", type=Path, default=ROOT)
    a.add_argument("--json", action="store_true", help="answers as data, keyed by label, with each bundle path")
    compare = sub.add_parser("compare", help="make a round from 2-9 retained render bundles (blind unless --open)")
    compare.add_argument("name")
    compare.add_argument("bundles", nargs="+", type=Path)
    compare.add_argument("--root", type=Path, default=ROOT)
    compare.add_argument("--open", action="store_true", help="show labels, measures and source changes")
    compare.add_argument("--task", action="append", dest="tasks", help="task spec (repeatable), e.g. rate:áspero")
    compare.add_argument("--question", default="", help="what the listener should judge")
    compare.add_argument("--keep-levels", action="store_true",
                         help="open with loudness matching off: the question is about level (power, volume)")
    compare.add_argument("--reference", type=Path, help="a recording played first as REF, its measures the targets; "
                         "opens the round (a blind round hides it); it stays on this machine")
    pr = sub.add_parser("predict", help="record the assistant's reading of a round before the listening: refused "
                        "once it has an answer; open neither the page nor answers.json until agree")
    pr.add_argument("name")
    pr.add_argument("predictions", type=Path, help='JSON per group id: {"g1": {"pick": "B", "rate": {"A": 2, "B": 4}, '
                    '"evidence": "B: +2200 Hz 110-400 ms"}, "g2": {"distinguishable": false}}')
    pr.add_argument("--root", type=Path, default=ROOT)
    ag = sub.add_parser("agree", help="the predictions of one or more rounds against the answers, summed, beside "
                        "chance, a numeric rule and the listener")
    ag.add_argument("names", nargs="+")
    ag.add_argument("--root", type=Path, default=ROOT)
    ag.add_argument("--json", action="store_true")
    live = sub.add_parser("studio", help="edit and inspect a procedural audio project with immutable revisions")
    live.add_argument("project", type=Path)
    live.add_argument("--root", type=Path, default=ROOT / "studio")
    live.add_argument("--port", type=int, default=8765)
    live.add_argument("--name")
    args = ap.parse_args(argv)
    if args.cmd == "compare":
        print(compare_bundles(args.name, *args.bundles, root=args.root, blind=not args.open, tasks=args.tasks,
                              question=args.question, keep_levels=args.keep_levels, reference=args.reference))
        return
    if args.cmd == "studio":
        from tare.tools.tune.studio import run
        run(args.project, args.root, args.port, name=args.name)
        return
    if args.cmd == "predict":
        print(predict(args.name, json.loads(args.predictions.read_text(encoding="utf-8")), args.root))
        return
    if args.cmd == "agree":
        report = agree(args.names, args.root)
        print(json.dumps(report, ensure_ascii=False) if args.json else agree_text(report))
        return
    if args.cmd == "answers":
        print(json.dumps(answers_json(args.name, args.root), ensure_ascii=False) if args.json else
              summary(args.name, args.root))
        return
    server = serve(args.root, args.port, not args.no_open)
    print(f"curadoria em http://127.0.0.1:{server.server_address[1]}/  (rodadas em {args.root}; Ctrl+C para parar)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
