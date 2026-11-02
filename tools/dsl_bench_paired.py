"""Paired, executed construction/inspection/refinement/error/repair/export transcripts."""

import ast
import contextlib
import copy
import io
import json
import random
import tempfile
import time
import tracemalloc
from pathlib import Path

import numpy as np
from dsl_bench_corpus import CORPUS, IMPORTS

from tare.tools.tune.authoring import build_file
from tare.tools.tune.diagnostics import canonical, digest
from tare.tools.tune.dsl import compile_document, load
from tare.tools.tune.dsl.adapters import materialized_id
from tare.tools.tune.dsl.patch import patch_file
from tare.tools.tune.dsl.query import authored, expansion, inspection
from tare.tools.tune.inspection import inspect_capture

PRIMERS = {
    "python": "Use the existing Python API in a persistent task namespace. Bind the source and Capture. "
    "Keep original recipe construction in the recorded program. Inspect with inspect_capture, "
    "project only requested fields. Clone before testing an invalid edit. Capture the repaired source "
    "and write WAV. Keep existing note call grouping and seeds.",
    "project_json": "Use the existing project JSON and public authoring loader. A file has sample_rate and "
    "source or sounds. Recipes use type/options. Musical tracks use settings, instrument and notes. "
    "Use Python helpers for projections and capabilities the old format cannot express; count "
    "their complete code. Preserve the recipe program when freezing materialized Voice JSON.",
    "dsl_json": "Use version-1 tare.tools.tune.dsl JSON. Query only the target and needed fields. "
    "Patch with the exact authored_revision; no full bank re-emission after construction. "
    "Refine generated layers with edit and the current materialized_id. Retain recipe definitions. "
    "Inspect top-three id/power rows and export WAV. Re-query a stale guard explicitly.",
}


def bind_source(program):
    tree = ast.parse(program)
    last = tree.body[-1]
    assert isinstance(last, ast.Assign) and isinstance(last.value, ast.Call)
    call = last.value
    source = call.args[0]
    call.args[0] = ast.Name(id="source", ctx=ast.Load())
    tree.body.insert(-1, ast.Assign(targets=[ast.Name(id="source", ctx=ast.Store())], value=source))
    return ast.unparse(ast.fix_missing_locations(tree)), ast.unparse(call)


def imports_for(program):
    tree = ast.parse(IMPORTS + program)
    used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    for statement in tree.body:
        if isinstance(statement, ast.ImportFrom):
            statement.names = [name for name in statement.names if (name.asname or name.name) in used]
    tree.body = [statement for statement in tree.body if not isinstance(statement, ast.ImportFrom) or statement.names]
    return ast.unparse(tree)


class Session:
    def __init__(self, directory):
        self.directory, self.namespace, self.turns = directory, {}, []
        self.task_prompt = ""

    def call(self, phase, request, operation):
        begin = time.perf_counter()
        stream = io.StringIO()
        error = None
        with contextlib.redirect_stdout(stream):
            try:
                response = operation()
            except (ValueError, TypeError, AttributeError, OSError, AssertionError) as exc:
                error = exc
                response = (
                    exc.to_dict() if hasattr(exc, "to_dict") else {"error": type(exc).__name__, "message": str(exc)}
                )
        if stream.getvalue():
            response = stream.getvalue()
        # Freeze requests now: later repairs must not rewrite the recorded failure.
        self.turns.append(
            {
                "phase": phase,
                "user_prompt": self.task_prompt
                if phase == "construct"
                else {
                    "inspect": "Return top-three layer IDs/powers in the 2000..6000 Hz band; skip pitch analysis.",
                    "refine": "Apply the requested refinement while retaining the original recipe/program.",
                    "invalid": "Reject the specified invalid value and preserve the last valid source/state.",
                    "repair": "Apply the corrected value and produce the valid audio.",
                    "export": "Export the final audio as WAV.",
                    "ambiguous_discovery": "Find a bright metallic confirmation; discover the recipe/events.",
                    "missing_asset": "Report the missing local asset without substituting another sound.",
                    "invalid_units": "Validate the primitive time field and explain its unit error.",
                }.get(phase, ""),
                "request": copy.deepcopy(request),
                "response": response,
                "seconds": time.perf_counter() - begin,
                "error": error is not None,
            }
        )
        return response, error

    def python(self, phase, code):
        def execute():
            exec(compile(code, "<paired-task-request>", "exec"), self.namespace)

        return self.call(phase, {"python": code}, execute)


def run_route(task, route, directory):
    directory.mkdir()
    session = Session(directory)
    session.task_prompt = task["instruction"]
    source_path = directory / "source.json"
    program, recapture = bind_source(task["python"])
    namespace = session.namespace
    mode = route
    tracemalloc.start()
    begin = time.perf_counter()
    if route == "python" or route == "project_json" and not task.get("legacy"):
        if route == "project_json":
            mode = "python_fallback"
        session.python("construct", imports_for(program) + '\nprint(c.manifest["pcm_id"])')
    elif route == "project_json":
        data = task["legacy"]
        source_path.write_bytes(canonical(data))
        request = {
            "write": data,
            "python": "from tare.tools.tune.authoring import build_file,materialize\n"
            "source,loop=materialize(project['source'],16000)\nc=build_file(path)\nprint(c.manifest['pcm_id'])",
        }
        namespace.update(project=data, path=source_path)
        code = request["python"]
        session.call("construct", request, lambda: exec(compile(code, "<project-request>", "exec"), namespace))
        recapture = "capture(source,16000,loop=loop)"
    else:
        data = copy.deepcopy(task["dsl"])
        if task.get("patch"):
            from tare.tools.tune.dsl.patch import apply_operations

            data, _ = apply_operations(data, task["patch"])
        if task.get("refine"):
            guard = materialized_id(compile_document(load(source_path, data=data), name="main").plan)
            data["sounds"]["main"] = {"edit": data["sounds"]["main"], "expect": guard, "set": task["refine"]}
        source_path.write_bytes(canonical(data))
        session.call(
            "construct",
            {"write": data, "call": "build_file", "args": ["source.json"], "kwargs": {"name": "main"}},
            lambda: {"pcm_id": build_file(source_path, name="main").manifest["pcm_id"]},
        )

    def current():
        return build_file(source_path, name="main") if route == "dsl_json" else namespace["c"]

    initial = current()
    if route == "dsl_json":
        session.call(
            "inspect",
            {
                "call": "inspection",
                "kwargs": {"view": "layers", "top": 3, "fields": ["id", "power"], "band": [2000, 6000], "pitch": False},
            },
            lambda: inspection(current(), view="layers", top=3, fields=["id", "power"], band=(2000, 6000)),
        )
        # Measure a real output-policy ablation on the same captured artifact/query.
        full = inspect_capture(initial, band=(2000, 6000), pitch=False)
        compact = session.turns[-1]["response"]
    else:
        session.python(
            "inspect",
            "from tare.tools.tune.inspection import inspect_capture\n"
            "r=inspect_capture(c,band=(2000,6000),pitch=False)\n"
            "print([{k:row[k] for k in ('id','power')} for row in r['layers'][:3]])",
        )
        full, compact = None, None
    fm = task["id"] == "capability-export"
    if route == "dsl_json":
        query, failed = session.call(
            "select",
            {"call": "authored", "args": ["source.json", "sound:main"]},
            lambda: authored(load(source_path), "sound:main", limit=3),
        )
        assert failed is None
        source = load(source_path).data["sounds"]["main"]
        original_expression = copy.deepcopy(source)
        if fm:
            path = "/fm/index"
        elif "score" in source:
            path = "/score/lowpass"
        elif any(op in source for op in ("mix", "seq", "repeat")):
            path = "/lowpass"
        else:
            expanded, failed = session.call(
                "select",
                {"call": "expansion", "args": ["source.json"], "limit": 1},
                lambda: expansion(compile_document(load(source_path), name="main"), limit=1, fields=["path", "kind"]),
            )
            assert failed is None
            source = {"edit": source, "expect": expanded["materialized_id"], "set": {"/lowpass": 1800}}
            path = "/set/~1lowpass"
        revisions = [query["authored_revision"]]

        def edit(value):
            if "edit" in source and "set" in source:
                operation = {
                    "op": "set",
                    "target": "sound:main",
                    "path": "",
                    "value": source | {"set": {"/lowpass": value}},
                }
            else:
                operation = {"op": "set", "target": "sound:main", "path": path, "value": value}
            patch = {"format": "tare.tools.tune.patch", "version": 1, "expect": revisions[-1], "ops": [operation]}
            response = patch_file(source_path, patch)
            revisions.append(response["authored_revision"])
            captured = build_file(source_path, name="main")
            return {"authored_revision": response["authored_revision"], "pcm_id": captured.manifest["pcm_id"]}

        for phase, value in (("refine", 2 if fm else 1800), ("invalid", "bad"), ("repair", 2 if fm else 1800)):
            # Each request retains complete protocol overhead and real revision/guard values.
            request_source = source | {"set": {"/lowpass": value}} if "edit" in source else None
            op = {
                "op": "set",
                "target": "sound:main",
                "path": "" if request_source else path,
                "value": request_source if request_source else value,
            }
            request = {
                "call": "patch_file+build_file",
                "source": "source.json",
                "patch": {"format": "tare.tools.tune.patch", "version": 1, "expect": revisions[-1], "ops": [op]},
            }
            _, error = session.call(phase, request, lambda value=value: edit(value))
            assert (error is not None) == (phase == "invalid")
        if task["id"] == "high-low-refinement":
            stale = copy.deepcopy(source)
            stale["edit"]["edit"]["power"] = 0.9
            _, error = session.call(
                "stale_guard",
                {"call": "compile_document", "sound": stale},
                lambda: compile_document(load(data=task["dsl"] | {"sounds": {"main": stale}})),
            )
            assert error is not None
        del original_expression
    else:
        session.python(
            "prepare_edit",
            "from tare.tools.tune import capture\n"
            + ("from tare.tools.tune.effects import fm_tone" if fm else "import copy"),
        )
        for phase, value in (("refine", 2 if fm else 1800), ("invalid", "bad"), ("repair", 2 if fm else 1800)):
            if fm:
                code = f"candidate=fm_tone(duration=.1,index={value!r},sr=16000)\nnext_capture=capture(candidate,16000)"
            else:
                code = f"candidate=copy.deepcopy(source)\ncandidate.lowpass={value!r}\n"
                code += "next_capture=" + recapture.replace("source", "candidate")
            code += '\nsource=candidate\nc=next_capture\nprint(c.manifest["pcm_id"])'
            _, error = session.python(phase, code)
            assert (error is not None) == (phase == "invalid")
        if task["id"] == "high-low-refinement":
            session.python(
                "guard_setup", "from tare.tools.tune.diagnostics import digest\nexpected=digest(source.to_dict())"
            )
            _, error = session.python(
                "stale_guard",
                "changed=Sfx('ui','crystal',power=.9,dry=True).voice('confirm')\n"
                "assert digest(changed.to_dict())==expected,'materialized source changed'",
            )
            # AssertionError is deliberately a tested precondition, not a harness failure.
            assert error is not None
    captured = current()
    if route == "dsl_json":
        from tare.tools.tune.dsl.migrate import freeze

        _, error = session.call(
            "export",
            {"call": "freeze", "source": "source.json", "name": "main", "format": "wav", "output": "audio.wav"},
            lambda: freeze(source_path, directory / "audio.wav", name="main", format="wav"),
        )
        assert error is None
    else:
        session.namespace["output_path"] = directory / "audio.wav"
        session.python(
            "export",
            "from tare.tools.tune.audio_io import write_wav\n"
            "write_wav(output_path,c.audio,c.sr)\nprint({'frames':len(c.audio),'sample_rate':c.sr})",
        )
    from tare.tools.tune.audio_io import read_channels

    exported, rate = read_channels(directory / "audio.wav")
    actual = captured.audio[:, None] if captured.audio.ndim == 1 else captured.audio
    assert rate == captured.sr and exported.shape == captured.audio.shape
    np.testing.assert_allclose(exported.reshape(actual.shape), actual, rtol=0, atol=1 / 32768)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return {
        "mode": mode,
        "turns": session.turns,
        "seconds": time.perf_counter() - begin,
        "tracked_peak_bytes": peak,
        "pcm_id": captured.manifest["pcm_id"],
        "initial_pcm_id": initial.manifest["pcm_id"],
        "full_inspection": full,
        "compact_inspection": compact,
    }, captured.audio


def paired_checkpoint():
    import hashlib
    import importlib.metadata
    import platform

    from dsl_bench_bank import run as bank_checkpoint

    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    result = {}
    with tempfile.TemporaryDirectory(prefix="tune-paired-") as folder:
        for task in corpus["tasks"]:
            rows, audio = {}, {}
            routes = ["python", "project_json", "dsl_json"]
            random.Random(task["id"]).shuffle(routes)
            for route in routes:
                rows[route], audio[route] = run_route(task, route, Path(folder) / (task["id"] + "-" + route))
            assert all(np.array_equal(audio["python"], samples) for samples in audio.values()), task["id"]
            assert len({row["initial_pcm_id"] for row in rows.values()}) == 1
            result[task["id"]] = {
                "routes": rows,
                "artifact_equal": True,
                "required_phases": ["construct", "inspect", "refine", "invalid", "repair", "export"],
            }
    return {
        "protocol": "executed-paired-workflows/1",
        "corpus_id": digest(corpus),
        "primers": PRIMERS,
        "tasks": result,
        "large_bank": bank_checkpoint(),
        "probes": probes(),
        "builders": builder_checkpoint(),
        "success": True,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "tiktoken")},
            "source_id": digest(
                {
                    str(path.relative_to(CORPUS.parents[4])): hashlib.sha256(path.read_bytes()).hexdigest()
                    for folder in (CORPUS.parents[4] / "src", CORPUS.parents[4] / "tools")
                    for path in sorted(folder.rglob("*"))
                    if path.is_file() and path.suffix in (".py", ".html")
                }
            ),
        },
        "limits": [
            "Scripted decisions; not live-agent success evidence.",
            "Task namespaces are fresh; Python variables persist between turns within a task.",
            "Legacy unsupported operations use the fully counted Python fallback.",
            "tracemalloc measures tracked allocations, not total process peak RSS.",
        ],
    }


def builder_checkpoint():
    programs = {
        "single-recipe": """from tare.tools.tune.dsl import Project,sfx
from tare.tools.tune.dsl.compiler import capture_compiled
p=Project(context={'sample_rate':16000},sounds={'main':sfx('ui',style='crystal',event='confirm',species=7,dry=True)})
c=capture_compiled(p.compile())""",
        "arrangement": """from tare.tools.tune.dsl import Project,score,repeat,pattern,transpose
from tare.tools.tune.dsl.compiler import capture_compiled
p=Project(context={'sample_rate':16000,'bpm':120},sounds={'main':score(hall=0,loop='8bar',tracks=[
 {'name':'lead-v1','instrument':'harp','notes':repeat(8,pattern('C4 . . .',steps=1)).then(transpose(-12))}])})
c=capture_compiled(p.compile())""",
        "four-variants": """from tare.tools.tune.dsl import Project,mix,sfx
from tare.tools.tune.dsl.compiler import capture_compiled
p=Project(context={'sample_rate':16000},sounds={'main':mix(*[
 {'at':f'{i*250}ms','sound':sfx('ui',style='crystal',event='confirm',species=7,dry=True,take=i)} for i in range(4)])})
c=capture_compiled(p.compile())""",
    }
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    result = {}
    for task in corpus["tasks"]:
        if task["id"] not in programs:
            continue
        baseline, builder = {}, {}
        exec(compile(IMPORTS + task["python"], "<builder-oracle>", "exec"), baseline)
        exec(compile(programs[task["id"]], "<builder-request>", "exec"), builder)
        assert np.array_equal(baseline["c"].audio, builder["c"].audio)
        result[task["id"]] = {
            "request": programs[task["id"]],
            "pcm_id": builder["c"].manifest["pcm_id"],
            "pcm_equal": True,
            "scope": "construction only",
        }
    return result


def probes():
    """Discovery, missing assets and physical-unit repairs, paired across routes."""
    result = {}
    with tempfile.TemporaryDirectory(prefix="tune-paired-probes-") as folder:
        for route in ("python", "project_json", "dsl_json"):
            directory = Path(folder) / route
            directory.mkdir()
            session = Session(directory)
            if route == "dsl_json":
                from tare.tools.tune.dsl.query import page
                from tare.tools.tune.dsl.registry import catalog

                session.call(
                    "ambiguous_discovery",
                    {"argv": ["dsl", "catalog", "--domain", "sfx", "--fields", "name,meaning", "--limit", "100"]},
                    lambda: page(catalog("sfx"), "discovery", limit=100, fields=["name", "meaning"]),
                )
                session.call(
                    "select_recipe",
                    {"argv": ["dsl", "catalog", "--domain", "sfx", "--name", "ui", "--fields", "events,styles"]},
                    lambda: page(catalog("sfx", "ui"), "selected", fields=["events", "styles"]),
                )
            else:
                session.python(
                    "ambiguous_discovery",
                    "from tare.tools.tune.sfx import RECIPES\n"
                    "print([{'name':k,'meaning':v.description} for k,v in sorted(RECIPES.items())])",
                )
                session.python("select_recipe", "print({'events':RECIPES['ui'].events,'styles':RECIPES['ui'].styles})")
            missing = directory / "missing.wav"
            if route == "dsl_json":
                data = {
                    "format": "tare.tools.tune.dsl",
                    "version": 1,
                    "context": {"sample_rate": 16000},
                    "sounds": {"main": {"audio": "missing.wav"}},
                }
            else:
                data = {"sample_rate": 16000, "source": {"type": "audio", "file": "missing.wav"}}
            path = directory / "source.json"
            path.write_bytes(canonical(data))
            _, failed = session.call(
                "missing_asset",
                {"write": data, "call": "build_file", "source": "source.json"},
                lambda path=path, route=route: build_file(path, name="main" if route == "dsl_json" else None),
            )
            assert failed is not None
            session.namespace["missing_path"] = missing
            session.python(
                "create_asset",
                "import numpy as np\nfrom tare.tools.tune.audio_io import write_wav\n"
                "write_wav(missing_path,np.full(160,.125,np.float32),16000)\nprint('created')",
            )
            captured, failure = session.call(
                "recover_asset",
                {"call": "build_file", "source": "source.json"},
                lambda path=path, route=route: build_file(path, name="main" if route == "dsl_json" else None),
            )
            assert failure is None
            # Captures are retained as acceptance artifacts, not serialized as a huge response.
            session.turns[-1]["response"] = {"pcm_id": captured.manifest["pcm_id"]}
            if route == "dsl_json":
                bad = {
                    "format": "tare.tools.tune.dsl",
                    "version": 1,
                    "context": {"sample_rate": 16000},
                    "sounds": {"main": {"voice": [{"noise": {"start": "10ms", "dur": 0.1, "freq": [[0, 1000]]}}]}},
                }
                _, failure = session.call(
                    "invalid_units",
                    {"call": "compile_document", "document": bad},
                    lambda bad=bad: compile_document(load(data=bad)),
                )
                assert failure is not None
                repaired = copy.deepcopy(bad)
                repaired["sounds"]["main"]["voice"][0]["noise"]["start"] = 0.01
                compiled, failure = session.call(
                    "repair_units",
                    {"call": "compile_document", "document": repaired},
                    lambda repaired=repaired: compile_document(load(data=repaired)),
                )
                assert failure is None
                session.turns[-1]["response"] = {"status": "valid", "layers": compiled.cost["layers"]}
            else:
                code = "from tare.tools.tune import Voice,capture\nfrom tare.tools.tune.spec import Noise\n"
                _, failure = session.python(
                    "invalid_units", code + "c=capture(Voice(noise=[Noise('10ms',.1,[(0,1000)])]),16000)"
                )
                assert failure is not None
                _, failure = session.python(
                    "repair_units", "c=capture(Voice(noise=[Noise(.01,.1,[(0,1000)])]),16000)\nprint('valid')"
                )
                assert failure is None
            result[route] = {"turns": session.turns, "asset_pcm_id": captured.manifest["pcm_id"], "success": True}
    assert len({row["asset_pcm_id"] for row in result.values()}) == 1
    return result
