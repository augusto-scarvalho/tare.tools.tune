"""Replay three persisted review tasks; count all sent helper code, without inference.

The composed DSL and Python controls intentionally share a counted transaction
helper. They are fixture-scoped reference programs, not another authoring API.
"""

# Literal requests are measured exactly as sent.
# ruff: noqa: E501

import argparse
import contextlib
import copy
import hashlib
import importlib.metadata
import io
import json
import platform
import time
from pathlib import Path

import numpy as np

from tare.tools.tune import Sfx, capture
from tare.tools.tune.audio_io import read_channels
from tare.tools.tune.bundles import load_bundle
from tare.tools.tune.diagnostics import canonical, digest
from tare.tools.tune.score import Score

EMIT = "import json\ndef emit(v): print(json.dumps(v,allow_nan=False))\n"
COMMON = """import copy,hashlib
from tare.tools.tune.bundles import atomic_json,file_lock,load_bundle,save_bundle
from tare.tools.tune.diagnostics import digest,renderer_id
from tare.tools.tune.dsl.composition import finalize
from tare.tools.tune.dsl.review_data import facts,run_checks,changes,source_changes
def summary(c,b,previous=None):
 m=facts(c)
 r={'bundle':str(b),'audio':'audio.wav','facts':m,'checks':run_checks(c,checks,m),'can_edit':True}
 if previous:
  old=load_bundle(previous)
  r['changes']=changes(c,old,m)
  r['changes']['source']=source_changes(old.manifest['bench']['document'],c.manifest['bench']['document'])
 return r
def observe(data,previous=None):
 compiled=build(data,name)
 c=render(compiled)
 c.manifest['bench']={'document':data,'revision':digest(data),'materialized':identity(compiled)}
 finalize(c)
 b=save_bundle(c,folder/'bundles')
 return summary(c,b,previous)
def inspect_control(bundle,pointer):
 c=load_bundle(bundle)
 node=c.manifest['bench']['document']
 for key in pointer: node=node[key]
 return {'value':node,'can_edit':True}
def edit_observed(bundle,update):
 old=load_bundle(bundle)
 state=old.manifest['bench']
 with file_lock(path.with_name('.'+path.name+'.lock')):
  before=path.read_bytes()
  data=json.loads(before)
  if digest(data)!=state['revision'] or renderer_id()!=old.manifest['renderer']:
   raise ValueError('observed source or renderer changed')
  if identity(build(data,name))!=state['materialized']:
   raise ValueError('observed materialization changed')
  candidate=copy.deepcopy(data)
  update(candidate)
  for sound in candidate['sounds']: build(candidate,sound)
  r=observe(candidate,bundle)
  if r['checks']['status']!='passed': raise ValueError('candidate failed requested checks')
  if path.read_bytes()!=before or renderer_id()!=old.manifest['renderer']:
   raise ValueError('source or code changed during preparation')
  backups=path.parent/'.tune-backups'
  backups.mkdir(exist_ok=True)
  backup=backups/(path.name+'.'+hashlib.sha256(before).hexdigest()+'.bak')
  if not backup.exists(): backup.write_bytes(before)
  atomic_json(path,candidate)
  r['edit']={'status':'applied','affected':[name],'affected_total':1}
  return r
"""
DSL = """from tare.tools.tune.dsl import compile_document,load
from tare.tools.tune.dsl.compiler import capture_compiled
from tare.tools.tune.dsl.adapters import materialized_id
def build(data,name): return compile_document(load(path,data=data),name=name)
def render(compiled): return capture_compiled(compiled)
def identity(compiled): return materialized_id(compiled.plan)
"""
PY_VOICE = """from tare.tools.tune import Sfx,capture
from tare.tools.tune.diagnostics import definition
def build(data,name):
 entry=data['sounds'][name]
 v=Sfx(entry['kind'],entry['style'],**entry['options']).voice(entry['event'])
 for key,value in entry.get('refine',{}).items(): setattr(v,key,value)
 return v
def render(compiled): return capture(compiled,16000)
def identity(compiled): return digest(definition(compiled))
"""
PY_MUSIC = """from tare.tools.tune import capture
from tare.tools.tune.diagnostics import definition
from tare.tools.tune.score import Score
def build(data,name):
 shift=data['sounds'][name]['transpose']
 s=Score(bpm=120,meter=3,sr=16000,hall=.2,seed=17)
 motif=[(60+shift,i*3,1,.8) for i in range(2)]
 s.track('lead-v1',pan=-.3).play('harp',motif)
 s.track('bass-v1',pan=.3).play('marimba',[(p-12,t,d,v) for p,t,d,v in motif])
 return s
def render(compiled): return capture(compiled,loop=3)
def identity(compiled): return digest(definition(compiled))
"""


def fixtures(task):
    crystal = {"sfx": "ui", "style": "crystal", "event": "confirm", "species": 7, "dry": True}
    native = {"kind": "ui", "style": "crystal", "event": "confirm", "options": {"species": 7, "dry": True}}
    dsl = {
        "format": "tare.tools.tune.dsl",
        "version": 1,
        "context": {"sample_rate": 16000},
        "sounds": {"main": crystal},
    }
    python = {"sounds": {"main": native}}
    if task == "transpose":
        dsl = json.loads((Path(__file__).parents[1] / "examples/dsl-music.tune.json").read_text())
        python = {"sounds": {"theme": {"transpose": 0}}}
    elif task == "bank128":
        dsl["defs"] = {
            "hit": {
                "params": {"species": {"type": "integer"}, "power": {"type": "number", "default": 0.5}},
                "body": {**crystal, "species": {"param": "species"}, "power": {"param": "power"}},
            }
        }
        dsl["sounds"] = {f"sound_{i:03}": {"use": "hit", "with": {"species": i}} for i in range(128)}
        python["sounds"] = {
            f"sound_{i:03}": {**native, "options": {"species": i, "power": 0.5, "dry": True}} for i in range(128)
        }
    return dsl, python


def oracle(task, edited, alternate=False):
    if task == "transpose":
        score = Score(bpm=120, meter=3, sr=16000, hall=0.2, seed=17)
        shift = 12 if edited and not alternate else 0
        score.track("lead-v1", pan=-0.3).play("harp", [(60 + shift, 0, 1), (60 + shift, 3, 1)])
        score.track("bass-v1", pan=0.3).play("marimba", [(48 + shift, 0, 1), (48 + shift, 3, 1)])
        return capture(score, loop=3)
    voice = Sfx(
        "ui",
        "crystal",
        species=63 if task == "bank128" else 7,
        power=(0.6 if alternate else 0.65) if edited and task == "bank128" else 0.5,
        dry=True,
    ).voice("confirm")
    if edited and task == "refine":
        voice.lowpass, voice.gain = 1800 if alternate else 2400, 0.25
    return capture(voice, 16000)


def verify(report, wanted):
    retained = load_bundle(report["bundle"])
    np.testing.assert_array_equal(retained.audio, wanted.audio)
    pcm, rate = read_channels(Path(report["bundle"]) / "audio.wav")
    encoded = (np.clip(wanted.audio, -1, 1) * 32767).astype(np.int16).astype(np.float32) / 32767
    np.testing.assert_array_equal(pcm, encoded)
    assert rate == wanted.sr and report["checks"]["status"] == "passed"


def run(task, route, folder, *, response="detailed", edits=1, bind_fixed=False):
    folder = folder.resolve()
    folder.mkdir(parents=True)
    name = "theme" if task == "transpose" else "sound_063" if task == "bank128" else "main"
    dsl, python = fixtures(task)
    initial = python if route == "python" else dsl
    path = folder / "source.json"
    path.write_bytes(canonical(initial))
    checks = {
        "format": "tare.tools.tune.checks",
        "version": 1,
        "sample_rate": 16000,
        "channels": 2 if task == "transpose" else 1,
        "duration_s": {"max": 5},
        "peak_dbfs": {"max": 0},
    }
    env = {"path": path, "folder": folder, "name": name, "checks": checks}
    turns = []

    def step(action, code, fails=False):
        stream = io.StringIO()
        begin = time.perf_counter()
        error = None
        before = path.read_bytes()
        try:
            with contextlib.redirect_stdout(stream):
                exec(compile(code, "<review-benchmark-request>", "exec"), env)
            response = json.loads(stream.getvalue()) if stream.getvalue() else None
        except Exception as exc:
            error = exc
            response = exc.to_dict() if hasattr(exc, "to_dict") else {"error": type(exc).__name__, "message": str(exc)}
        turns.append(
            {
                "action": action,
                "request": code,
                "response": response,
                "seconds": time.perf_counter() - begin,
                "error": error is not None,
                "expected_error": fails,
            }
        )
        assert (error is not None) == fails, (task, route, action, response)
        if fails:
            assert path.read_bytes() == before
        return response

    if route == "review":
        setup = EMIT + "from tare.tools.tune.dsl import review,describe,edit_file\n"
        if bind_fixed:
            setup += (
                "from functools import partial\napply=partial(edit_file,path,output=folder/'bundles',response="
                + repr(response)
                + (",target='def:motif'" if task == "transpose" else "")
                + ")\n"
            )
        step("setup", setup)
        profile = ",response='compact'" if response == "compact" else ""
        first = step(
            "observe",
            "r=review(path,name=name,output=folder/'bundles',checks=checks" + profile + ")\nb=r['bundle']\nemit(r)",
        )
        selection = "target='def:motif'" if task == "transpose" else "fields=['power']"
        step("describe", f"emit(describe(b,{selection}))")
        edit = (
            "refine={'/lowpass':2400,'/gain':.25}"
            if task == "refine"
            else "target='def:motif',set_fields={'/body/then':[{'transpose':12}]}"
            if task == "transpose"
            else "set_fields={'/with/power':.65}"
        )
        if bind_fixed and task == "transpose":
            edit = edit.removeprefix("target='def:motif',")
        request = (
            f"r=apply(from_bundle=b,{edit})\nemit(r)"
            if bind_fixed
            else (f"r=edit_file(path,from_bundle=b,output=folder/'bundles',{edit}{profile})\nemit(r)")
        )
        final = step("edit", request)
        step("stale", request, fails=True)
    else:
        adapter = DSL if route == "composed_dsl" else PY_MUSIC if task == "transpose" else PY_VOICE
        helper = COMMON
        if response == "compact":
            helper = "from tare.tools.tune.dsl.responses import respond\n" + helper.replace(
                " return r\n", " return respond(r,'review','compact')\n", 1
            )
        step("setup", EMIT + helper + adapter)
        first = step("observe", "r=observe(json.loads(path.read_bytes()))\nb=r['bundle']\nemit(r)")
        pointer = ["defs", "motif", "body"] if task == "transpose" and route == "composed_dsl" else ["sounds", name]
        step("describe", f"emit(inspect_control(b,{pointer!r}))")
        if task == "refine":
            update = "def update(data,value):\n data['sounds'][name].setdefault('refine',{}).update({'lowpass':value,'gain':.25})\n"
            if route == "composed_dsl":
                update = "def update(data,value):\n expression=data['sounds'][name]\n if 'edit' not in expression:\n  expression={'edit':expression,'expect':identity(build(data,name)),'set':{}}\n expression['set'].update({'/lowpass':value,'/gain':.25})\n data['sounds'][name]=expression\n"
        elif task == "transpose":
            update = (
                "def update(data,value):\n data['sounds'][name]['transpose']=value\n"
                if route == "python"
                else "def update(data,value):\n data['defs']['motif']['body']['then']=[{'transpose':value}]\n"
            )
        else:
            update = (
                "def update(data,value):\n data['sounds'][name]['options']['power']=value\n"
                if route == "python"
                else "def update(data,value):\n data['sounds'][name]['with']['power']=value\n"
            )
        value = "2400" if task == "refine" else "12" if task == "transpose" else ".65"
        request = f"r=edit_observed(b,lambda data:update(data,{value}))\nemit(r)"
        final = step("edit", update + request)
        step("stale", request, fails=True)

    verify(final, oracle(task, True))
    for index in range(1, edits):
        current = request
        if index % 2:
            current = (
                current.replace("2400", "1800")
                if task == "refine"
                else (current.replace("12", "0") if task == "transpose" else current.replace(".65", ".6"))
            )
        final = step("edit", "b=r['bundle']\n" + current)
        verify(final, oracle(task, True, alternate=bool(index % 2)))

    verify(first, oracle(task, False))
    verify(final, oracle(task, True))
    updated = json.loads(path.read_bytes())
    expected = copy.deepcopy(initial)
    if task == "bank128":
        expected["sounds"][name]["options" if route == "python" else "with"]["power"] = 0.65
    elif task == "transpose":
        if route == "python":
            expected["sounds"][name]["transpose"] = 12
        else:
            expected["defs"]["motif"]["body"]["then"] = [{"transpose": 12}]
    else:
        if route == "python":
            expected["sounds"][name]["refine"] = {"lowpass": 2400, "gain": 0.25}
        else:
            actual = updated["sounds"][name]
            assert actual["edit"] == initial["sounds"][name] and set(actual) == {"edit", "expect", "set"}
            assert actual["set"] == {"/lowpass": 2400, "/gain": 0.25}
            expected["sounds"][name] = actual
    assert updated == expected
    backups = list((folder / ".tune-backups").glob("*.bak"))
    assert 1 <= len(backups) <= edits and any(json.loads(p.read_bytes()) == initial for p in backups)
    if task == "transpose":
        if route == "review":
            code = "from tare.tools.tune.dsl import load,compile_document\ns=compile_document(load(path)).plan.source\n"
        else:
            code = "s=build(json.loads(path.read_bytes()),name)\n" + (
                "s=s.plan.source\n" if route == "composed_dsl" else ""
            )
        step(
            "midi",
            code
            + "from tare.tools.tune.midi_export import export_midi\nexport_midi(s,folder/'theme.mid',loop=3)\nemit({'midi':'theme.mid'})",
        )
        # Independent literal tick checks; MIDI parsing lives in the existing oracle module.
        import sys

        sys.path.insert(0, str(Path(__file__).parents[1] / "tests"))
        from test_authoring_workflows import parse_midi

        midi = parse_midi(folder / "theme.mid")
        assert (2880, 0x90, [72, 102]) in midi[1] and (3840, 0x80, [72, 0]) in midi[1]
    return {
        "turns": turns,
        "success": True,
        "edits": edits,
        "bind_fixed": bind_fixed and route == "review",
        "source_bytes": len(canonical(initial)),
        "oracles": ["initial_float_pcm", "final_float_pcm", "decoded_pcm16", "source_scope", "backup", "stale_refusal"]
        + (["midi_ticks"] if task == "transpose" else []),
        "initial_source": initial,
        "final_source": updated,
    }


def main():
    import tiktoken

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output/review-benchmark.json"))
    parser.add_argument("--artifacts-root", type=Path, default=Path("output/review-bench-runs"))
    parser.add_argument("--response", choices=("detailed", "compact"), default="detailed")
    parser.add_argument("--edits", type=int, choices=(1, 5), default=1)
    parser.add_argument(
        "--bind-fixed", action="store_true", help="bind fixed review arguments with counted functools.partial"
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    import tempfile

    args.artifacts_root.mkdir(parents=True, exist_ok=True)
    artifacts = Path(tempfile.mkdtemp(prefix="review-", dir=args.artifacts_root))
    result = {
        "protocol": "executed-review-workflows/1",
        "artifacts": str(artifacts.resolve()),
        "cases": {},
        "metrics": {},
        "response": args.response,
        "edits": args.edits,
        "bind_fixed": args.bind_fixed,
        "service_contract": "supplied editable bank; observe/playable bundle, selected control, trial-check edit, backup/atomic persistence, stale refusal; MIDI for music",
        "limits": [
            "Three scripted decisions, one execution per arm; no live-agent, billing or sound-quality claim.",
            "Persistent Python tool namespace; supplied paths/name/checks/files are identical external inputs. All sent helper code is charged.",
            "Composed DSL and Python controls share a fully counted fixture-scoped helper. This is API composition, not a stateless legacy CLI comparison.",
            "Fixtures have no external assets. Production asset/concurrent-write boundaries are tested separately.",
            "Review has richer control descriptors/coverage and source-code guards. Warm response costs can increase; built-in integration amortizes setup.",
            "Two proxy encodings; no system/tool envelopes, reasoning, repeated context or quota is measured.",
        ],
    }
    for task in ("refine", "transpose", "bank128"):
        result["cases"][task] = {
            r: run(
                task,
                r,
                artifacts / (task + "-" + r),
                response=args.response,
                edits=args.edits,
                bind_fixed=args.bind_fixed,
            )
            for r in ("composed_dsl", "review", "python")
        }
    for encoding in ("cl100k_base", "o200k_base"):
        tokenizer = tiktoken.get_encoding(encoding)
        rows = {}
        for task, routes in result["cases"].items():
            rows[task] = {}
            for route, run_result in routes.items():
                sent = received = warm = setup = productive = validation = 0
                phases = {}
                for turn in run_result["turns"]:
                    request = len(tokenizer.encode(turn["request"]))
                    response = len(tokenizer.encode(canonical(turn["response"]).decode()))
                    phase = phases.setdefault(turn["action"], {"request_tokens": 0, "response_tokens": 0})
                    phase["request_tokens"] += request
                    phase["response_tokens"] += response
                    sent += request
                    received += response
                    if turn["action"] == "setup":
                        setup += request + response
                    if turn["action"] not in ("setup", "observe", "describe"):
                        warm += request + response
                    if turn["action"] in ("edit", "midi"):
                        productive += request + response
                    if turn["expected_error"]:
                        validation += request + response
                rows[task][route] = {
                    "request_tokens": sent,
                    "response_tokens": received,
                    "content_tokens": sent + received,
                    "setup_tokens": setup,
                    "warm_tokens": warm,
                    "productive_tokens": productive,
                    "validation_tokens": validation,
                    "phases": phases,
                    "tool_calls": len(run_result["turns"]),
                    "seconds": sum(t["seconds"] for t in run_result["turns"]),
                }
        result["metrics"][encoding] = rows
    root = Path(__file__).parents[1]
    result["environment"] = {
        "python": platform.python_version(),
        "tiktoken": importlib.metadata.version("tiktoken"),
        "source_id": digest(
            {
                str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for base in (root / "src", root / "tools")
                for p in sorted(base.rglob("*"))
                if p.suffix in (".py", ".html")
            }
        ),
    }
    result["success"] = True
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps({"success": True, "output": str(args.output), "metrics": result["metrics"]["o200k_base"]}))


if __name__ == "__main__":
    main()
