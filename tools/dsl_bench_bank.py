"""Cold, revision-checked local edits in a real 128-sound bank, with competent baselines."""

import contextlib
import copy
import os
import tempfile
from pathlib import Path

import numpy as np
from dsl_bench_paired import Session

from tare.tools.tune import Sfx, capture
from tare.tools.tune.authoring import build_file
from tare.tools.tune.diagnostics import canonical, digest
from tare.tools.tune.dsl import load
from tare.tools.tune.dsl.patch import patch_file
from tare.tools.tune.dsl.query import authored, project_fields

TARGET = "sound_047"
LEGACY_HELPER = """import json
from pathlib import Path
from tare.tools.tune.authoring import materialize
from tare.tools.tune.bundles import atomic_json,file_lock
from tare.tools.tune.diagnostics import digest
path=Path('bank.json')
def query():
 d=json.loads(path.read_text())
 return {'authored_revision':digest(d),'power':d['sounds']['sound_047']['options']['power']}
def change(expected,key,value):
 with file_lock(path.with_suffix('.lock')):
  before=path.read_bytes()
  candidate=json.loads(before)
  if digest(candidate)!=expected: raise ValueError('authored revision changed')
  candidate['sounds']['sound_047']['options'][key]=value
  materialize(candidate['sounds']['sound_047'],16000,path.parent)
  if path.read_bytes()!=before: raise ValueError('source changed outside transaction')
  atomic_json(path,candidate)
  return digest(candidate)
print(query())
"""


@contextlib.contextmanager
def working_directory(directory):
    previous = Path.cwd()
    os.chdir(directory)
    try:
        yield
    finally:
        os.chdir(previous)


def documents(size):
    legacy = {
        "sample_rate": 16000,
        "sounds": {
            f"sound_{i:03}": {
                "type": "sfx",
                "kind": "ui",
                "style": "crystal",
                "event": "confirm",
                "options": {"species": i, "power": 0.5, "dry": True, "knobs": {"ring": 0.7}},
            }
            for i in range(size)
        },
    }
    parameters = {
        "species": {"type": "integer", "default": 0},
        "power": {"type": "number", "default": 0.5},
        "ring": {"type": "number", "default": 0.7},
    }
    dsl = {
        "format": "tare.tools.tune.dsl",
        "version": 1,
        "context": {"sample_rate": 16000},
        "defs": {
            "hit": {
                "params": parameters,
                "body": {
                    "sfx": "ui",
                    "style": "crystal",
                    "event": "confirm",
                    "species": {"param": "species"},
                    "power": {"param": "power"},
                    "dry": True,
                    "knobs": {"ring": {"param": "ring"}},
                },
            }
        },
        "sounds": {
            f"sound_{i:03}": {"use": "hit", "with": {"species": i, "power": 0.5, "ring": 0.7}} for i in range(size)
        },
    }
    return legacy, dsl


def run(size=128):
    assert size > 47
    legacy, dsl = documents(size)
    rows = {}
    with tempfile.TemporaryDirectory(prefix="tune-large-bank-") as folder:
        for route in ("python", "project_json", "dsl_json"):
            directory = Path(folder) / route
            directory.mkdir()
            data = dsl if route == "dsl_json" else legacy
            path = directory / "bank.json"
            path.write_bytes(canonical(data))
            original = copy.deepcopy(data)
            session = Session(directory)
            if route == "dsl_json":
                query, error = session.call(
                    "select",
                    {
                        "argv": [
                            "dsl",
                            "query",
                            "bank.json",
                            "--target",
                            "sound:" + TARGET,
                            "--fields",
                            "fragment.with.power",
                            "--json",
                        ]
                    },
                    lambda path=path: project_fields(authored(load(path), "sound:" + TARGET), ["fragment.with.power"]),
                )
                assert error is None
                revision = query["authored_revision"]
                for phase, key, value in (
                    ("edit", "power", 0.65),
                    ("invalid", "knobs", {"ring": 99}),
                    ("repair", "ring", 0.8),
                    ("stale", "power", 0.6),
                ):
                    # Definition parameters expose ring directly on this invocation.
                    argument = "ring" if key == "knobs" else key
                    replacement = value["ring"] if key == "knobs" else value
                    request = {
                        "format": "tare.tools.tune.patch",
                        "version": 1,
                        "expect": query["authored_revision"] if phase == "stale" else revision,
                        "ops": [
                            {
                                "op": "set",
                                "target": "sound:" + TARGET,
                                "path": "/with/" + argument,
                                "value": replacement,
                            }
                        ],
                    }
                    response, error = session.call(
                        phase,
                        {"call": "patch_file", "source": "bank.json", "patch": request},
                        lambda request=request, path=path: project_fields(
                            patch_file(path, request), ["authored_revision"]
                        ),
                    )
                    assert (error is not None) == (phase in ("invalid", "stale"))
                    if error is None:
                        revision = response["authored_revision"]
                expected_doc = copy.deepcopy(original)
                expected_doc["sounds"][TARGET]["with"].update(power=0.65, ring=0.8)
            else:
                # The same existing helper is allowed to both competent baseline routes.
                with working_directory(directory):
                    _, error = session.python(
                        "select", LEGACY_HELPER + '\ninitial=query()["authored_revision"]\nrevision=initial'
                    )
                    assert error is None
                    for phase, key, value in (
                        ("edit", "power", 0.65),
                        ("invalid", "knobs", {"ring": 99}),
                        ("repair", "knobs", {"ring": 0.8}),
                        ("stale", "power", 0.6),
                    ):
                        expected = "initial" if phase == "stale" else "revision"
                        _, error = session.python(
                            phase, f"revision=change({expected},{key!r},{value!r})\nprint(revision)"
                        )
                        assert (error is not None) == (phase in ("invalid", "stale"))
                expected_doc = copy.deepcopy(original)
                expected_doc["sounds"][TARGET]["options"].update(power=0.65, knobs={"ring": 0.8})
            import json

            assert json.loads(path.read_text()) == expected_doc
            captured = build_file(path, name=TARGET)
            expected = capture(
                Sfx("ui", "crystal", species=47, power=0.65, dry=True, knobs={"ring": 0.8}).voice("confirm"), 16000
            )
            assert np.array_equal(captured.audio, expected.audio)
            rows[route] = {
                "turns": session.turns,
                "pcm_id": captured.manifest["pcm_id"],
                "unrelated_preserved": True,
                "mode": "existing Python helper" if route != "dsl_json" else "DSL compact query+patch",
            }
    full_query = authored(load(data=dsl), pointer="/sounds", limit=128)
    minimal = project_fields(authored(load(data=dsl), "sound:" + TARGET), ["fragment.with.power"])
    return {
        "bank_size": size,
        "instruction": "Edit only sound_047 in the provided 128-sound bank: power .65, reject invalid ring 99, "
        "repair ring .8, reject a stale revision, preserve unrelated source and render the target.",
        "target": TARGET,
        "routes": rows,
        "input_id": digest({"legacy": legacy, "dsl": dsl}),
        "ablation": {
            "full_source": dsl,
            "broad_query": full_query,
            "targeted_query": minimal,
            "updated_source": expected_doc,
        },
        "limits": [
            "Preexisting bank is provided equally to each route; its unrequested contents are not counted.",
            "Baseline helper is fully counted, uses existing atomic writes/locks and is reusable after first use.",
        ],
    }
