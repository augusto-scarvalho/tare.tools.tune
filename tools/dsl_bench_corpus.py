"""Executed, paired task corpus. Scripts use the public legacy API as independent oracles."""

import contextlib
import copy
import io
import json
import tempfile
from pathlib import Path

import numpy as np

from tare.tools.tune.authoring import build_file
from tare.tools.tune.cli import main as cli
from tare.tools.tune.diagnostics import canonical, digest
from tare.tools.tune.dsl import load
from tare.tools.tune.dsl.adapters import materialized_id
from tare.tools.tune.dsl.compiler import compile_document
from tare.tools.tune.dsl.patch import patch_file

CORPUS = Path(__file__).resolve().parents[1] / "tests/fixtures/dsl/bench/tasks.json"
IMPORTS = (
    "from tare.tools.tune import Sfx,Creature,Voice,capture\n"
    "from tare.tools.tune.score import Score\n"
    "from tare.tools.tune.speech import Speaker\n"
    "from tare.tools.tune.effects import fm_tone\n"
)


def execute(code, namespace):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        exec(compile(code, "<benchmark-request>", "exec"), namespace)
    return {"request": code, "response": stream.getvalue()}


def run(directory, stage="full"):
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    result = {}
    for task in corpus["tasks"]:
        if stage == "M1" and task["id"] not in ("single-recipe", "invalid-repair"):
            continue
        if stage == "M2" and task["id"] not in (
            "single-recipe",
            "invalid-repair",
            "arrangement",
            "high-low-refinement",
        ):
            continue
        root = directory / task["id"]
        root.mkdir()
        namespace = {}
        code = IMPORTS + task["python"] + '\nprint(c.manifest["pcm_id"])'
        python_trace = [execute(code, namespace)]
        expected = namespace["c"]
        legacy_trace = []
        if task.get("legacy"):
            legacy_code = (
                "import json\nfrom pathlib import Path\nfrom tare.tools.tune.authoring import build_file\n"
                f"project={task['legacy']!r}\n"
                f"path=Path({str(root / 'legacy.json')!r})\n"
                'path.write_text(json.dumps(project))\nc=build_file(path)\nprint(c.manifest["pcm_id"])'
            )
            legacy_namespace = {}
            legacy_trace.append(execute(legacy_code, legacy_namespace))
            assert np.array_equal(legacy_namespace["c"].audio, expected.audio), task["id"] + ": legacy PCM"
            legacy_mode = "project_json"
        else:
            # The existing project format cannot express every composition. Count
            # its documented Python fallback in full, rather than inventing syntax.
            legacy_trace = copy.deepcopy(python_trace)
            legacy_mode = "python_fallback"
        path = root / "source.tune.json"
        document = copy.deepcopy(task["dsl"])
        if task.get("refine"):
            guard = materialized_id(compile_document(load(path, data=document)).plan)
            document["sounds"]["main"] = {"edit": document["sounds"]["main"], "expect": guard, "set": task["refine"]}
        path.write_bytes(canonical(document))
        trace = []
        stream, errors = io.StringIO(), io.StringIO()
        argv = ["dsl", "check", str(path), "--json"]
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(errors):
            exit_code = cli(argv)
        assert exit_code == 0, errors.getvalue()
        trace.append({"request": {"write": document, "argv": argv}, "response": stream.getvalue()})
        if task.get("patch"):
            request = {
                "format": "tare.tools.tune.patch",
                "version": 1,
                "expect": load(path).revision,
                "ops": task["patch"],
            }
            response = patch_file(path, request)
            trace.append({"request": {"patch_file": request}, "response": response})
        captured = build_file(path, name="main")
        assert np.array_equal(captured.audio, expected.audio), task["id"] + ": DSL PCM"
        np.testing.assert_allclose(captured.replay(), captured.audio, rtol=0, atol=1e-7)
        trace.append({"request": {"build_file": str(path)}, "response": {"pcm_id": captured.manifest["pcm_id"]}})
        if task["id"] == "invalid-repair":
            revision = load(path).revision
            request = {
                "format": "tare.tools.tune.patch",
                "version": 1,
                "expect": revision,
                "ops": [{"op": "set", "target": "sound:main", "path": "/knobs/ring", "value": 99}],
            }
            from tare.tools.tune.dsl import DSLError

            try:
                patch_file(path, request)
                raise AssertionError("invalid patch accepted")
            except DSLError as exc:
                assert exc.code == "E_KNOB_RANGE" and load(path).revision == revision
                trace.append({"request": {"patch_file": request}, "response": exc.to_dict()})
            # A repaired transaction is executed explicitly, even when restoring
            # the same intended value after the rejected transaction.
            request["ops"][0]["value"] = 0.7
            trace.append({"request": {"patch_file": copy.deepcopy(request)}, "response": patch_file(path, request)})
        if task["id"] == "capability-export":
            from tare.tools.tune.dsl.migrate import freeze

            try:
                freeze(path, root / "unsupported.json", format="voice")
                raise AssertionError("FM was exported as Voice")
            except ValueError as exc:
                trace.append({"request": {"freeze": "voice"}, "response": {"error": str(exc)}})
            report = freeze(path, root / "correct.wav", format="wav")
            assert (root / "correct.wav").stat().st_size > 44
            trace.append({"request": {"freeze": "wav"}, "response": report})
        if task["id"] == "high-low-refinement":
            document["sounds"]["main"]["edit"]["power"] = 0.9
            try:
                compile_document(load(path, data=document))
                raise AssertionError("stale guard accepted")
            except ValueError as exc:
                trace.append({"request": {"compile_document": document}, "response": {"error": str(exc)}})
        if task["id"] == "arrangement":
            score = compile_document(load(path)).plan.source
            events = score.tracks["lead-v1"].events
            assert [e["beat"] for e in events] == list(range(0, 32, 4))
            from tare.tools.tune.midi_export import export_midi

            export_midi(score, root / "song.mid", loop=16)
            assert (root / "song.mid").read_bytes().startswith(b"MThd")
        result[task["id"]] = {
            "instruction": task["instruction"],
            "acceptance": task["acceptance"],
            "pcm_equal": True,
            "pcm_id": captured.manifest["pcm_id"],
            "legacy_mode": legacy_mode,
            "transcripts": {"python": python_trace, "project_json": legacy_trace, "dsl_json": trace},
        }
    return {"corpus_id": digest(corpus), "tasks": result, "task_count": len(result)}


def checkpoint(stage="full"):
    with tempfile.TemporaryDirectory(prefix="tune-dsl-corpus-") as directory:
        return run(Path(directory), stage)
