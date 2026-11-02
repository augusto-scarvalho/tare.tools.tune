"""Local authoring player: clean workers, immutable revisions, and guarded evaluations."""
from __future__ import annotations

import hashlib
import io
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .bundles import RevisionStore
from .diagnostics import canonical
from .inspection import inspect_capture


def encode_wav(audio, sr):
    from .audio_io import to_pcm16
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1 if audio.ndim == 1 else audio.shape[1])
        stream.setsampwidth(2)
        stream.setframerate(sr)
        stream.writeframes(to_pcm16(audio))
    return output.getvalue()


class Controller:
    def __init__(self, project, root, name=None, watch=True, asset_roots=()):
        self.project = Path(project).resolve()
        self.store = RevisionStore(root)
        self.name = name
        self.asset_roots = tuple(str(Path(p).resolve()) for p in asset_roots)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.clients = set()
        self.workers = set()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tune-build")
        self.status = {"phase": "loading", "error": None, "revision": self.store.state()["revision"],
                       "requested": 0, "name": name}
        self.fingerprint = self.inputs()
        self.request()
        if watch:
            threading.Thread(target=self.watch, daemon=True).start()

    def inputs(self):
        paths = {self.project, *Path(__file__).parent.rglob("*.py")}
        try:
            document = json.loads(self.project.read_text(encoding="utf-8"))
            def scan(value):
                if isinstance(value, dict):
                    for key, item in value.items():
                        if key == "file" and isinstance(item, str):
                            paths.add((self.project.parent / item).resolve())
                        else:
                            scan(item)
                elif isinstance(value, list):
                    for item in value:
                        scan(item)
            scan(document)
            names = list(document.get("sounds", {}))
            with self.lock:
                self.status["sounds"] = names
            if document.get("format") == "tare.tools.tune.dsl":
                from .dsl.dependencies import paths_for
                paths.update(paths_for(self.project, name=self.name, asset_roots=self.asset_roots))
        except (OSError, ValueError, AttributeError):
            pass
        revision = self.store.state()["revision"]
        if revision:
            try:
                capture = self.store.load(revision)
                for asset in capture.manifest["assets"]:
                    paths.add(Path(__file__).parent / "speech" / "data" / asset)
                for dependency in capture.manifest.get("dsl", {}).get("dependencies", {}):
                    paths.add(Path(dependency))
            except (OSError, ValueError):
                pass
        hashes = {}
        for path in paths:
            try:
                hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                hashes[str(path)] = None
        return hashes

    def watch(self):
        while not self.stop.wait(0.6):
            fingerprint = self.inputs()
            if fingerprint != self.fingerprint:
                self.fingerprint = fingerprint
                self.request()

    def notify(self):
        with self.lock:
            for client in self.clients:
                try:
                    client.put_nowait(dict(self.status))
                except queue.Full:
                    try:
                        client.get_nowait()
                        client.put_nowait(dict(self.status))
                    except (queue.Empty, queue.Full):
                        pass

    def request(self, name=None):
        with self.lock:
            if self.stop.is_set():
                raise ValueError("authoring server is closing")
            if name is not None:
                self.name = name
            generation = self.store.request()
            self.status.update(phase="building", requested=generation, error=None, name=self.name)
            self.status.pop("diagnostic", None)
            self.pool.submit(self.build, generation, self.name)
            self.notify()
            return generation

    def build(self, generation, name):
        if self.store.state()["requested"] != generation or self.stop.is_set():
            return
        command = [sys.executable, "-m", "tare.tools.tune.studio_worker", str(self.project),
                   str(self.store.root / "revisions")]
        if name:
            command += ["--name", name]
        for root in self.asset_roots:
            command += ["--asset-root", root]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = (str(Path(__file__).resolve().parents[3]) + os.pathsep
                                     + environment.get("PYTHONPATH", ""))
        try:
            with self.lock:
                if self.stop.is_set():
                    return
                worker = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding="utf-8", errors="replace", env=environment,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                self.workers.add(worker)
            try:
                try:
                    stdout, stderr = worker.communicate(timeout=120)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.communicate()
                    raise
            finally:
                with self.lock:
                    self.workers.discard(worker)
            if worker.returncode:
                try:
                    diagnostic = json.loads(stderr.strip().splitlines()[-1])
                except (ValueError, IndexError):
                    diagnostic = None
                if isinstance(diagnostic, dict) and diagnostic.get("schema") == "tune.error/1":
                    with self.lock:
                        if self.store.state()["requested"] == generation:
                            self.status["diagnostic"] = diagnostic
                    raise ValueError(diagnostic["message"])
                raise ValueError(stderr.strip().splitlines()[-1] if stderr.strip() else "build failed")
            revision = json.loads(stdout.strip().splitlines()[-1])["revision"]
            captured = self.store.load(revision)
            with self.lock:
                if self.stop.is_set():
                    return
                if not self.store.publish(captured, generation):
                    return
                self.status.update(phase="ready", revision=revision, error=None)
                self.notify()
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            with self.lock:
                if self.store.state()["requested"] == generation:
                    self.status.update(phase="error", error=str(exc))
                    self.notify()

    def close(self):
        self.stop.set()
        with self.lock:
            for worker in self.workers:
                if worker.poll() is None:
                    worker.kill()
        self.pool.shutdown(wait=True, cancel_futures=True)


def make_server(project, root, port=8765, *, name=None, watch=True, asset_roots=()):
    controller = Controller(project, root, name, watch, asset_roots)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, body, kind="application/json", status=200):
            if not isinstance(body, bytes):
                body = canonical(body)
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            args = {key: value[0] for key, value in parse_qs(url.query).items()}
            try:
                if url.path == "/":
                    return self.send((Path(__file__).parent / "ui" / "studio.html").read_bytes(),
                                     "text/html; charset=utf-8")
                if url.path == "/favicon.ico":
                    return self.send(b"", "image/x-icon", status=204)
                if url.path == "/api/state":
                    with controller.lock:
                        return self.send(controller.status)
                if url.path == "/api/revisions":
                    return self.send([p.name for p in sorted((controller.store.root / "revisions").glob("*"),
                                                             key=lambda p: p.stat().st_mtime, reverse=True)
                                      if p.is_dir() and (p / "manifest.json").exists()])
                if url.path == "/api/events":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    client = queue.Queue(maxsize=1)
                    with controller.lock:
                        if len(controller.clients) >= 16:
                            return
                        controller.clients.add(client)
                        client.put_nowait(dict(controller.status))
                    try:
                        while not controller.stop.is_set():
                            try:
                                state = client.get(timeout=2)
                                self.wfile.write(b"data: " + canonical(state) + b"\n\n")
                            except queue.Empty:
                                self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                    finally:
                        with controller.lock:
                            controller.clients.discard(client)
                    return
                revision = args.get("revision") or controller.store.state()["revision"]
                if not revision:
                    return self.send({"error": "No completed render yet. Wait for the build."}, status=409)
                if url.path == "/api/answers":
                    return self.send(controller.store.answers(revision))
                captured = controller.store.load(revision)
                if url.path == "/api/inspect":
                    band = [float(args["low"]), float(args["high"])] if "low" in args else None
                    if "view" in args:
                        from .dsl.query import inspection
                        return self.send(inspection(captured, view=args["view"], start=float(args.get("start", 0)),
                            end=float(args["end"]) if "end" in args else None, band=band, node_id=args.get("node"),
                            top=int(args["top"]) if "top" in args else None, limit=int(args.get("limit", 10)),
                            cursor=args.get("cursor"), fields=args["fields"].split(",") if "fields" in args else None))
                    return self.send(inspect_capture(captured, start=float(args.get("start", 0)),
                                                     end=float(args["end"]) if "end" in args else None,
                                                     band=band, pitch=False, node_id=args.get("node")))
                if url.path == "/api/audio":
                    mode, layer = args.get("mode", "full"), args.get("layer")
                    if mode not in ("full", "mute", "solo", "reference"):
                        raise ValueError("unknown playback mode")
                    if mode == "full":
                        audio = (controller.store.root / "revisions" / revision / "audio.wav").read_bytes()
                    elif mode == "reference":
                        if "reference" not in captured.arrays:
                            raise ValueError("this revision has no reference recording")
                        audio = encode_wav(captured.arrays["reference"], captured.manifest["reference"]["sample_rate"])
                    else:
                        y = captured.replay(mute=[layer] if mode == "mute" else (),
                                            solo=[layer] if mode == "solo" else None)
                        audio = encode_wav(y, captured.sr)
                    playback_id = hashlib.sha256(audio).hexdigest()
                    directory = controller.store.root / "playbacks"
                    directory.mkdir(exist_ok=True)
                    playback = directory / f"{playback_id}.wav"
                    if not playback.exists():
                        temporary = directory / (playback_id + f".{threading.get_ident()}.tmp")
                        temporary.write_bytes(audio)
                        os.replace(temporary, playback)
                    return self.send(audio, "audio/wav")
                return self.send({"error": "not found"}, status=404)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.send({"error": str(exc)}, status=400)

        def do_POST(self):
            try:
                size = int(self.headers.get("Content-Length", 0))
                if size < 0 or size > 1024 * 1024:
                    return self.send({"error": "request exceeds 1 MiB"}, status=413)
                body = json.loads(self.rfile.read(size) or b"{}")
                canonical(body)
                if not isinstance(body, dict):
                    raise ValueError("request must be a JSON object")
                if self.path == "/api/build":
                    return self.send({"generation": controller.request(body.get("name"))})
                if self.path == "/api/answers":
                    return self.send(controller.store.save_answers(body["revision"], body["version"],
                                                                   body["answers"], body.get("listening", {})))
                return self.send({"error": "not found"}, status=404)
            except (ValueError, KeyError, TypeError) as exc:
                self.send({"error": str(exc)}, status=409)

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = os.name != "nt"

        def server_bind(self):
            if os.name == "nt":
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

        def server_close(self):
            controller.close()
            super().server_close()

    try:
        server = Server(("127.0.0.1", port), Handler)
    except OSError:
        controller.close()
        raise
    server.controller = controller
    return server


def run(project, root, port=8765, *, name=None, asset_roots=()):
    server = make_server(project, root, port, name=name, asset_roots=asset_roots)
    print(f"Authoring player: http://127.0.0.1:{server.server_address[1]}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
