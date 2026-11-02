"""Immutable captured render bundles and guarded, atomic revision publication."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import numpy as np

from .audio_io import write_wav
from .diagnostics import Capture, canonical, digest, pcm_id


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("wb") as stream:
            stream.write(canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


@contextlib.contextmanager
def file_lock(path):
    """Cross-process lock for short publication/answer transactions."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            # Windows permits byte locks beyond EOF. Initialize only while locked:
            # a racing writer must not flush into a byte another process has locked.
            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b"0")
                stream.flush()
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_bundle(captured: Capture, root) -> Path:
    if pcm_id(captured.audio, captured.sr) != captured.manifest["pcm_id"]:
        raise ValueError("captured audio was modified after revision creation")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    revision = captured.manifest["revision"]
    if not isinstance(revision, str) or len(revision) != 64 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("invalid revision")
    destination = root / revision
    if destination.exists():
        load_bundle(destination)
        return destination
    stage = Path(tempfile.mkdtemp(prefix=".bundle-", dir=root))
    try:
        np.savez_compressed(stage / "buffers.npz", **captured.arrays)
        write_wav(stage / "audio.wav", captured.audio, captured.sr)
        manifest = json.loads(canonical(captured.manifest))
        manifest["files"] = {name: _hash(stage / name) for name in ("buffers.npz", "audio.wav")}
        manifest["playback_id"] = manifest["files"]["audio.wav"]
        manifest["bundle_id"] = digest({"revision": revision, "files": manifest["files"]})
        atomic_json(stage / "manifest.json", manifest)
        load_bundle(stage)
        with file_lock(root / ".publish.lock"):
            if not destination.exists():
                os.replace(stage, destination)
        load_bundle(destination)
        return destination
    finally:
        if stage.exists():
            assert stage.resolve().parent == root.resolve() and stage.name.startswith(".bundle-")
            shutil.rmtree(stage)


def load_bundle(path) -> Capture:
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") not in (1, 2) or set(manifest.get("files", {})) != {"buffers.npz", "audio.wav"}:
        raise ValueError("unsupported or incomplete render bundle")
    for name, expected in manifest["files"].items():
        if _hash(path / name) != expected:
            raise ValueError(f"bundle integrity check failed: {name}")
    if (path / "buffers.npz").stat().st_size > 300 * 1024 * 1024:
        raise ValueError("bundle size limit exceeded")
    import zipfile
    with zipfile.ZipFile(path / "buffers.npz") as archive:
        if sum(entry.file_size for entry in archive.infolist()) > 300 * 1024 * 1024:
            raise ValueError("uncompressed bundle size limit exceeded")
    with np.load(path / "buffers.npz", allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    validate_graph(manifest, arrays)
    if set(arrays) != set(manifest["buffers"]):
        raise ValueError("bundle buffer catalog mismatch")
    root = next(node for node in manifest["nodes"] if node["id"] == manifest["root"])
    audio = arrays[root["audio"]]
    for key, expected in manifest["buffers"].items():
        value = arrays[key]
        if value.dtype.str != expected["dtype"] or list(value.shape) != expected["shape"] or \
                hashlib.sha256(value.tobytes()).hexdigest() != expected["sha256"]:
            raise ValueError("bundle buffer identity mismatch")
    base = {k: v for k, v in manifest.items() if k not in ("revision", "files", "playback_id", "bundle_id")}
    if digest(base) != manifest["revision"]:
        raise ValueError("bundle provenance identity mismatch")
    if manifest["playback_id"] != manifest["files"]["audio.wav"] or manifest["bundle_id"] != digest({
            "revision": manifest["revision"], "files": manifest["files"]}):
        raise ValueError("bundle artifact identity mismatch")
    if pcm_id(audio, manifest["sample_rate"]) != manifest["pcm_id"]:
        raise ValueError("bundle PCM identity mismatch")
    return Capture(audio, manifest["sample_rate"], manifest, arrays)


def validate_graph(manifest, arrays):
    """Validate replay topology before dereferencing edges or allocating replay buses."""
    try:
        nodes = {node["id"]: node for node in manifest["nodes"]}
        if len(nodes) != len(manifest["nodes"]) or manifest["root"] not in nodes:
            raise ValueError("duplicate node or missing root")
        visited, active = set(), set()
        def visit(key, parent=None):
            if key in active or key in visited:
                raise ValueError("cyclic or shared-parent replay graph")
            if len(active) >= 128:
                raise ValueError("replay graph depth exceeded")
            node = nodes[key]
            if node["kind"] not in ("audio", "voice", "score", "cue") or node["parent"] != parent:
                raise ValueError("invalid node kind or parent")
            active.add(key)
            if node["audio"] not in arrays:
                raise ValueError("missing node buffer")
            audio = arrays[node["audio"]]
            if audio.ndim not in (1, 2) or audio.ndim == 2 and audio.shape[1] not in (1, 2):
                raise ValueError("invalid replay channel shape")
            ids = set()
            for part in node["parts"]:
                if part["id"] in ids or part["audio"] not in arrays or \
                        type(part["start"]) is not int or part["start"] < 0:
                    raise ValueError("invalid replay part")
                ids.add(part["id"])
                if part.get("child_conversion") and (manifest["schema"] != 2 or part["child_conversion"] != "float64"):
                    raise ValueError("unsupported replay input conversion")
                if part["child"]:
                    visit(part["child"], key)
            if node.get("child"):
                visit(node["child"], key)
            for factor, value in node["factors"].items():
                if factor.startswith("effect_") and factor.endswith("_gain") and value not in arrays:
                    raise ValueError("missing gain envelope")
            active.remove(key)
            visited.add(key)
        visit(manifest["root"])
        if set(nodes) != visited:
            raise ValueError("unreachable replay nodes")
        if any(not np.isfinite(value).all() for value in arrays.values()):
            raise ValueError("non-finite replay buffer")
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError("invalid replay graph") from exc


class RevisionStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def request(self):
        with file_lock(self.root / ".state.lock"):
            state = self.state()
            state["requested"] += 1
            atomic_json(self.root / "current.json", state)
            return state["requested"]

    def state(self):
        path = self.root / "current.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"requested": 0, "revision": None}

    def publish(self, captured, generation):
        bundle = save_bundle(captured, self.root / "revisions")
        with file_lock(self.root / ".state.lock"):
            state = self.state()
            if state["requested"] != generation:
                return False
            state.update(revision=bundle.name, published=generation)
            atomic_json(self.root / "current.json", state)
            return True

    def load(self, revision=None):
        revision = revision or self.state()["revision"]
        if not isinstance(revision, str) or len(revision) != 64 or any(c not in "0123456789abcdef" for c in revision):
            raise ValueError("invalid revision")
        return load_bundle(self.root / "revisions" / revision)

    def answers(self, revision):
        self.load(revision)
        path = self.root / "answers" / f"{revision}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
            "revision": revision, "version": 0, "answers": {}, "listening": {}}

    def save_answers(self, revision, version, answers, listening):
        with file_lock(self.root / ".answers.lock"):
            state = self.answers(revision)
            if state["version"] != version:
                raise ValueError("answer version conflict; reload before saving")
            if not isinstance(answers, dict) or not isinstance(listening, dict):
                raise ValueError("answers and listening settings must be objects")
            state.update(version=version + 1, answers=answers, listening=listening)
            capture = self.load(revision)
            playback = listening.get("playback_id") or capture.manifest["playback_id"]
            if playback != capture.manifest["playback_id"]:
                if not isinstance(playback, str) or len(playback) != 64 or \
                        any(c not in "0123456789abcdef" for c in playback):
                    raise ValueError("invalid playback identity")
                recorded = self.root / "playbacks" / f"{playback}.wav"
                if not recorded.is_file() or _hash(recorded) != playback:
                    raise ValueError("playback artifact was not retained")
            state["playback_id"] = playback
            atomic_json(self.root / "answers" / f"{revision}.json", state)
            return state
