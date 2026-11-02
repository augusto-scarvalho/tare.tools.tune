"""Executed public-API programs with explicit semantic actions and service parity.

No inference. Helpers are sent and counted in each fresh tool namespace. Only the
common paths and supplied input files are provisioned outside recorded actions.
"""

# Literal tool requests retain their exact layout for content-token measurement.
# ruff: noqa: E501

import ast
import contextlib
import copy
import hashlib
import importlib.metadata
import io
import json
import math
import platform
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path

import numpy as np

from tare.tools.tune import Creature, Sfx, capture
from tare.tools.tune.audio_io import read_channels, write_wav
from tare.tools.tune.diagnostics import canonical, digest
from tare.tools.tune.score import Score

CORPUS = Path(__file__).resolve().parents[1] / "tests/fixtures/dsl/bench/tasks-v2.json"
PRIMER = (
    "Use supplied paths and public APIs. Preserve editable source and last-good state. Perform only requested actions."
)
EMIT = "import json,copy\ndef emit(value): print(json.dumps(value,allow_nan=False))\n"
PYTHON_MEMORY = """from tare.tools.tune import Sfx,Creature,capture
from tare.tools.tune.score import Score
from tare.tools.tune.speech import Speaker
from tare.tools.tune.music import Cue
from tare.tools.tune.audio_io import read_channels,write_wav
from tare.tools.tune.diagnostics import digest
"""
DSL_MEMORY = """from tare.tools.tune.dsl import load,compile_document
from tare.tools.tune.dsl.compiler import capture_compiled
from tare.tools.tune.dsl.adapters import materialized_id
from tare.tools.tune.dsl.patch import apply_operations
from tare.tools.tune.dsl.query import inspection,expansion
from tare.tools.tune.audio_io import write_wav
def render(data):
 p=compile_document(load(path,data=data),name='main')
 return p,capture_compiled(p)
def change(pointer,value):
 global d,p,c
 candidate,_=apply_operations(d,[{'op':'set','pointer':pointer,'value':value}])
 result,audio=render(candidate)
 d,p,c=candidate,result,audio
"""
PYTHON_PERSISTED = """import hashlib
from tare.tools.tune.authoring import materialize,build_file
from tare.tools.tune.bundles import atomic_json,file_lock
from tare.tools.tune.diagnostics import digest
from tare.tools.tune.audio_io import write_wav
from tare.tools.tune.spec import Voice
def query():
 data=json.loads(path.read_text())
 return {'authored_revision':digest(data),'fragment':data['sounds'][target]}
def change(expected,key,value):
 with file_lock(path.with_name('.'+path.name+'.lock')):
  before=path.read_bytes()
  data=json.loads(before)
  if digest(data)!=expected: raise ValueError('authored revision changed')
  data['sounds'][target]['options'][key]=value
  for sound in data['sounds'].values(): materialize(sound,16000,path.parent)
  backups=path.parent/'.tune-backups'
  backups.mkdir(exist_ok=True)
  backup=backups/(path.name+'.'+hashlib.sha256(before).hexdigest()+'.bak')
  if not backup.exists(): backup.write_bytes(before)
  if path.read_bytes()!=before: raise ValueError('source changed outside transaction')
  atomic_json(path,data)
  return {'authored_revision':digest(data),'changed':['sound:'+target],'affected_total':1}
"""
DSL_PERSISTED = """from tare.tools.tune.dsl import load
from tare.tools.tune.dsl.query import authored,project_fields
from tare.tools.tune.dsl.patch import patch_file
from tare.tools.tune.dsl.migrate import freeze
from tare.tools.tune.authoring import build_file
from tare.tools.tune.audio_io import write_wav
def query(): return authored(load(path),'sound:'+target)
def change(expected,key,value):
 return patch_file(path,{'format':'tare.tools.tune.patch','version':1,'expect':expected,
  'ops':[{'op':'set','target':'sound:'+target,'path':'/with/'+key,'value':value}]})
"""


class Session:
    def __init__(self, folder, task):
        self.task, self.folder, self.turns = task, folder, []
        self.namespace = {
            "path": folder / "source.json",
            "output": folder / "audio.wav",
            "asset": folder / "contact.wav",
            "target": "sound_000",
        }

    def step(self, action, code, *, fails=False):
        previous_data = copy.deepcopy(self.namespace.get("d"))
        previous_capture = self.namespace.get("c")
        previous_base = self.namespace.get("base")
        previous_spec = previous_base.to_dict() if previous_base is not None else None
        stream = io.StringIO()
        begin = time.perf_counter()
        error = None
        try:
            with contextlib.redirect_stdout(stream):
                exec(compile(code, "<semantic-benchmark-request>", "exec"), self.namespace)
        except Exception as exc:
            error = exc
        response = stream.getvalue()
        if error:
            response = (
                error.to_dict() if hasattr(error, "to_dict") else {"error": type(error).__name__, "message": str(error)}
            )
        elif response:
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                pass
        else:
            response = None
        self.turns.append(
            {
                "action": action,
                "request": {"python": code},
                "response": response,
                "error": error is not None,
                "expected_error": fails,
                "seconds": time.perf_counter() - begin,
            }
        )
        assert (error is not None) == fails, f"{action}: {error}"
        if action == "create":
            expected = expected_audio(self.task, self.namespace["asset"], initial=True)
            assert np.array_equal(self.namespace["c"].audio, expected.audio)
            self.turns[-1]["initial_artifact_verified"] = True
        if fails:
            assert isinstance(error, (ValueError, TypeError, OSError)), f"unexpected failure: {error}"
            if hasattr(error, "code"):
                wanted = {
                    "invalid": "E_KNOB_RANGE",
                    "missing": "E_ASSET",
                    "voice_refusal": "E_CAPABILITY",
                    "stale_revision": "E_REVISION_CONFLICT",
                    "stale_materialization": "E_OVERRIDE_STALE",
                }
                assert error.code == wanted[action], error.to_dict()
            elif action in ("stale_revision", "stale_materialization"):
                assert "revision changed" in str(error) or "materialized source changed" in str(error)
            assert previous_data is None or self.namespace.get("d") == previous_data
            assert self.namespace.get("c") is previous_capture
            assert previous_base is None or self.namespace["base"].to_dict() == previous_spec
            self.turns[-1]["last_good_state_preserved"] = True
        return response


def setup_code(code, needed):
    """Send only imports/helpers used by this task, rather than a generic kitchen sink."""
    tree = ast.parse(code)
    tree.body = [node for node in tree.body if not isinstance(node, ast.FunctionDef) or node.name in needed]
    used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | set(needed)
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            node.names = [alias for alias in node.names if (alias.asname or alias.name.split(".")[0]) in used]
    tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom)) or node.names]
    return ast.unparse(tree)


def document(body, definitions=None, sounds=None):
    return {
        "format": "tare.tools.tune.dsl",
        "version": 1,
        "context": {"sample_rate": 16000},
        **({"defs": definitions} if definitions else {}),
        "sounds": sounds or {"main": body},
    }


def crystal(**fields):
    return {"sfx": "ui", "style": "crystal", "event": "confirm", "species": 7, "dry": True, **fields}


def variants_document(shared=False):
    definition = {
        "params": {"power": {"type": "number", "default": 0.5}, "take": {"type": "integer", "default": 0}},
        "body": crystal(power={"param": "power"}, take={"param": "take"}),
    }
    if shared:
        return document(
            None,
            {"hit": definition},
            {
                "main": {"use": "hit"},
                "second": {"use": "hit", "with": {"take": 1}},
                "other": {"sfx": "ui", "event": "error", "dry": True},
            },
        )
    return document(
        {"mix": [{"at": f"{i * 250}ms", "sound": {"use": "hit", "with": {"take": i}}} for i in range(4)]},
        {"hit": definition},
    )


def create(session, route, data, python, builder=None):
    code = ((builder or f"d={data!r}") + "\np,c=render(d)") if route == "dsl" else python
    session.step("create", code + "\nemit({'status':'ready','frames':len(c.audio),'sample_rate':c.sr})")


def memory_case(session, route, workflow, response):
    task = session.task["id"]
    setup = EMIT + (DSL_MEMORY if route == "dsl" else PYTHON_MEMORY)
    if route == "dsl" and response == "compact":
        setup += "from tare.tools.tune.dsl.responses import respond\n"
    needed = {"emit", "render", "capture", "write_wav", "read_channels"}
    if route == "dsl":
        needed |= {"change"} if task in ("variants", "shared-definition", "refinement", "invalid-repair") else set()
        if task == "refinement":
            needed |= {"inspection", "expansion", "materialized_id", "copy"}
    else:
        if task not in ("arrangement", "scene", "missing-asset"):
            needed.add("Sfx")
        if task in ("arrangement", "scene", "variants"):
            needed.add("Score")
        if task == "scene":
            needed |= {"Creature", "Speaker", "Cue"}
        if task == "refinement":
            needed |= {"copy", "digest"}
    session.step("setup", setup_code(setup, needed))
    if task == "missing-asset":
        data = document({"audio": "contact.wav"})
        session.step(
            "missing", f"d={data!r}\np,c=render(d)" if route == "dsl" else "y,sr=read_channels(asset)", fails=True
        )
        session.step(
            "create_asset",
            "import numpy as np\nwrite_wav(asset,np.full(160,.125,np.float32),16000)\nemit({'created':True})",
        )
        session.step("recover", "p,c=render(d)" if route == "dsl" else "y,sr=read_channels(asset)\nc=capture(y,sr)")
    elif task == "discovery":
        if route == "dsl":
            session.step(
                "discover",
                "from tare.tools.tune.dsl.registry import catalog\nemit([{'name':r['name'],'meaning':r['meaning']} for r in catalog('sfx')])",
            )
            session.step("select_recipe", "r=catalog('sfx','ui')[0]\nemit({k:r[k] for k in ('events','styles')})")
        else:
            session.step(
                "discover",
                "from tare.tools.tune.sfx import RECIPES\nemit([{'name':k,'meaning':v.description} for k,v in sorted(RECIPES.items())])",
            )
            session.step("select_recipe", "emit({'events':RECIPES['ui'].events,'styles':RECIPES['ui'].styles})")
        create(
            session,
            route,
            document(crystal()),
            "c=capture(Sfx('ui','crystal',species=7,dry=True).voice('confirm'),16000)",
        )
    elif task in ("variants", "shared-definition"):
        if task == "variants":
            python = """def make(power=.5):
 s=Score(sr=16000,hall=0)
 for take in range(4): s.add(capture(Sfx('ui','crystal',species=7,power=power,dry=True).voice('confirm',take=take),16000).audio,at=take*.25)
 return capture(s)
c=make()"""
        else:
            python = """def make(power=.5):
 return [capture(Sfx('ui','crystal',species=7,power=power,dry=True).voice('confirm',take=k),16000) for k in range(2)]
children=make()
c=children[0]
other=capture(Sfx('ui',dry=True).voice('error'),16000)"""
        builder = """from tare.tools.tune.dsl import Project,definition,sfx,param,mix,use
hit=definition(sfx('ui',style='crystal',event='confirm',species=7,dry=True,power=param('power'),take=param('take')),
 params={'power':{'type':'number','default':.5},'take':{'type':'integer','default':0}})
"""
        if task == "variants":
            builder += "d=Project(context={'sample_rate':16000},defs={'hit':hit},sounds={'main':mix(*[{'at':f'{i*250}ms','sound':use('hit',take=i)} for i in range(4)])}).to_dict()"
        else:
            builder += "d=Project(context={'sample_rate':16000},defs={'hit':hit},sounds={'main':use('hit'),'second':use('hit',take=1),'other':sfx('ui',event='error',dry=True)}).to_dict()"
        create(session, route, variants_document(task == "shared-definition"), python, builder)
        code = (
            "change('/defs/hit/params/power/default',.8)"
            if route == "dsl"
            else ("c=make(.8)" if task == "variants" else "children=make(.8)\nc=children[0]")
        )
        session.step("shared_edit", code + "\nemit({'changed':'power','value':.8})")
    elif task == "arrangement":
        body = {
            "score": {
                "bpm": 120,
                "hall": 0,
                "loop": "8bar",
                "tracks": [
                    {
                        "name": "lead-v1",
                        "instrument": "harp",
                        "notes": {"repeat": 8, "of": {"pattern": "C4 . . .", "steps": 1}},
                    }
                ],
            }
        }
        python = """def make(shift=0):
 s=Score(sr=16000,bpm=120,hall=0)
 motif=[(60,0,1,.8)]
 s.track('lead-v1').play('harp',[(n+shift,t+bar*4,d,v) for bar in range(8) for n,t,d,v in motif])
 return s,capture(s,loop=16)
score,c=make()"""
        builder = """from tare.tools.tune.dsl import Project,score,repeat,pattern
d=Project(context={'sample_rate':16000,'bpm':120},sounds={'main':score(hall=0,loop='8bar',
 tracks=[{'name':'lead-v1','instrument':'harp','notes':repeat(8,pattern('C4 . . .',steps=1))}])}).to_dict()"""
        create(session, route, document(body), python, builder)
        session.step(
            "transpose",
            "d['sounds']['main']['score']['tracks'][0]['notes']['then']=[{'transpose':-12}]\np,c=render(d)"
            if route == "dsl"
            else "score,c=make(-12)",
        )
        session.step(
            "midi",
            "from tare.tools.tune.midi_export import export_midi\nexport_midi("
            + ("p.plan.source" if route == "dsl" else "score")
            + ",output.with_suffix('.mid'),loop=16)\nemit({'midi':'audio.mid'})",
        )
    elif task == "scene":
        body = {
            "mix": [
                {"sound": {"creature": "mammal", "species": "wolf", "call": "attack"}},
                {"at": "100ms", "sound": {"say": "Ready!", "lang": "en", "seed": 17, "speaker": {"speaker": "deep"}}},
                {"at": "200ms", "sound": {"music": "levelup", "seed": 4}},
                {"at": "300ms", "sound": {"audio": "contact.wav"}},
            ],
            "effects": [{"type": "limiter", "ceiling": 0.5}],
        }
        python = """s=Score(sr=16000,hall=0,effects=[{'type':'limiter','ceiling':.5}])
s.add(capture(Creature('mammal',species='wolf').voice('attack'),16000).audio)
s.add(capture(Speaker.preset('deep').voice('Ready!','en',seed=17),16000).audio,at=.1)
s.add(capture(Cue('levelup',seed=4,sr=16000),16000).audio,at=.2)
y,sr=read_channels(asset)
s.add(y,at=.3)
c=capture(s)"""
        builder = """from tare.tools.tune.dsl.builders import Project,mix,creature,say,speaker,music,audio
d=Project(context={'sample_rate':16000},sounds={'main':mix(
 {'sound':creature('mammal',species='wolf',call='attack')},
 {'at':'100ms','sound':say('Ready!',lang='en',seed=17,speaker=speaker('deep'))},
 {'at':'200ms','sound':music('levelup',seed=4)},
 {'at':'300ms','sound':audio('contact.wav')},effects=[{'type':'limiter','ceiling':.5}])}).to_dict()"""
        create(session, route, document(body), python, builder)
    else:
        ring = 0.3 if task == "invalid-repair" else 0.7
        data = document(crystal(**({"knobs": {"ring": ring}} if task == "invalid-repair" else {})))
        python = (
            """def make(power=.5,ring=None):
 return Sfx('ui','crystal',species=7,power=power,dry=True,**({'knobs':{'ring':ring}} if ring is not None else {})).voice('confirm')
base=make(ring="""
            + (".3" if task == "invalid-repair" else "None")
            + ")\nc=capture(base,16000)"
        )
        create(session, route, data, python)
        if task == "invalid-repair":
            for action, value in (("invalid", 99), ("repair", 0.7)):
                session.step(
                    action,
                    f"change('/sounds/main/knobs/ring',{value})"
                    if route == "dsl"
                    else f"candidate=make(ring={value})\nnext_capture=capture(candidate,16000)\nbase,c=candidate,next_capture",
                    fails=action == "invalid",
                )
        elif task == "refinement":
            refinement(session, route, workflow, response)
    if task == "shared-definition":
        if route == "dsl":
            session.step(
                "export",
                "from tare.tools.tune.dsl.compiler import capture_compiled\nsecond=capture_compiled(compile_document(load(path,data=d),name='second'))\nwrite_wav(output.with_name('second.wav'),second.audio,second.sr)\nwrite_wav(output,c.audio,c.sr)\nemit({'outputs':['audio.wav','second.wav']})",
            )
        else:
            session.step(
                "export",
                "write_wav(output.with_name('second.wav'),children[1].audio,c.sr)\nwrite_wav(output,c.audio,c.sr)\nemit({'outputs':['audio.wav','second.wav']})",
            )
    else:
        session.step(
            "export",
            "write_wav(output,c.audio,c.sr)\nemit({'output':'audio.wav','frames':len(c.audio),'sample_rate':c.sr})",
        )


def refinement(session, route, workflow, response):
    if route == "python":
        session.step(
            "inspect",
            "from tare.tools.tune.inspection import inspect_capture\nr=inspect_capture(c,band=(2000,6000),pitch=False)\nemit([{k:r[k] for k in ('id','power')} for r in r['layers'][:3]])\nexpected=digest(base.to_dict())",
        )
        for action, field, value in (
            ("hardness", "modal", 1234),
            ("filter", "lowpass", 1800),
            ("filter_again", "lowpass", 2400),
        ):
            assignment = "candidate.modal[0].hardness=1234" if field == "modal" else f"candidate.lowpass={value}"
            session.step(
                action,
                "candidate=copy.deepcopy(base)\n"
                + assignment
                + "\nnext_capture=capture(candidate,16000)\nbase,c=candidate,next_capture\nemit({'updated':True})",
            )
        session.step(
            "stale_materialization",
            "changed=make(power=.9)\nif digest(changed.to_dict())!=expected: raise ValueError('materialized source changed')",
            fails=True,
        )
        return
    inspect_code = (
        "r=inspection(c,view='layers',top=3,fields=['id','power'],band=(2000,6000)"
        + (",response='compact'" if response == "compact" else "")
        + ")\nemit(r)"
    )
    if workflow == "control":
        inspect_code += "\nq=expansion(p,limit=1,fields=['path','kind'])\nemit(q)\nguard=q['materialized_id']"
    else:
        inspect_code += "\nguard=materialized_id(p.plan)"
    session.step("inspect", inspect_code)
    base = copy.deepcopy(session.namespace["d"]["sounds"]["main"])
    sets = {}
    for action, field, value in (
        ("hardness", "/modal/0/hardness", 1234),
        ("filter", "/lowpass", 1800),
        ("filter_again", "/lowpass", 2400),
    ):
        if workflow == "control":
            sets[field] = value
            wrapped = {"edit": base, "expect": session.namespace["guard"], "set": copy.deepcopy(sets)}
            code = f"change('/sounds/main',{wrapped!r})"
        elif not sets:
            sets[field] = value
            code = (
                "wrapped={'edit':d['sounds']['main'],'expect':guard,'set':"
                + repr(sets)
                + "}\nchange('/sounds/main',wrapped)"
            )
        else:
            escaped = field.replace("~", "~0").replace("/", "~1")
            if field not in sets:
                code = f"v=dict(d['sounds']['main']['set']);v[{field!r}]={value}\nchange('/sounds/main/set',v)"
            else:
                code = f"change('/sounds/main/set/{escaped}',{value})"
            sets[field] = value
        session.step(action, code + "\nemit({'updated':True})")
    session.step(
        "stale_materialization",
        "candidate=copy.deepcopy(d)\ncandidate['sounds']['main']['edit']['power']=.9\nrender(candidate)",
        fails=True,
    )


def bank_documents(size):
    legacy = {
        "sample_rate": 16000,
        "sounds": {
            f"sound_{i:03}": {
                "type": "sfx",
                "kind": "ui",
                "style": "crystal",
                "event": "confirm",
                "options": {"species": i, "power": 0.5, "dry": True, "knobs": {"ring": 0.3}},
            }
            for i in range(size)
        },
    }
    definition = {
        "params": {
            "species": {"type": "integer"},
            "power": {"type": "number", "default": 0.5},
            "ring": {"type": "number", "default": 0.3},
        },
        "body": crystal(species={"param": "species"}, power={"param": "power"}, knobs={"ring": {"param": "ring"}}),
    }
    dsl = document(
        None,
        {"hit": definition},
        {f"sound_{i:03}": {"use": "hit", "with": {"species": i, "power": 0.5, "ring": 0.3}} for i in range(size)},
    )
    return legacy, dsl


def persisted_case(session, route, response, workflow):
    task = session.task
    setup = EMIT + (DSL_PERSISTED if route == "dsl" else PYTHON_PERSISTED)
    if route == "dsl" and response == "compact":
        setup = setup.replace("'value':value}]})", "'value':value}]},response='compact')")
    needed = {"emit", "query", "change", "build_file", "write_wav"}
    if task["id"] == "capability":
        needed = (needed - {"change"}) | {"freeze", "materialize", "Voice"}
    if route == "dsl":
        needed |= {"authored", "load", "project_fields"}
    session.step("setup", setup_code(setup, needed))
    query = "q=query();revision=q['authored_revision'];initial=revision\nemit(q)"
    if route == "dsl" and response == "compact":
        query = "q=authored(load(path),'sound:'+target,response='compact');revision=q['authored_revision'];initial=revision\nemit(q)"
    session.step("observe", query)
    if task["id"] == "capability":
        if route == "dsl":
            session.step(
                "voice_refusal", "freeze(path,output.with_suffix('.voice.json'),name=target,format='voice')", fails=True
            )
            session.step(
                "export",
                "c=build_file(path,name=target)\nr=freeze(path,output,name=target,format='wav'"
                + (",response='compact'" if response == "compact" else "")
                + ")\nemit(r)",
            )
        else:
            session.step(
                "voice_refusal",
                "data=json.loads(path.read_text())\nsource,loop=materialize(data['sounds'][target],16000,path.parent)\nif not isinstance(source,Voice): raise ValueError('this result requires PCM/bundle export')\noutput.with_suffix('.voice.json').write_text(json.dumps(source.to_dict()))",
                fails=True,
            )
            session.step(
                "export",
                "c=build_file(path,name=target)\nwrite_wav(output,c.audio,c.sr)\nemit({'output':str(output),'kind':'wav','frames':len(c.audio),'sample_rate':c.sr})",
            )
        return
    values = [("edit", "power", 0.65, False)]
    if task["id"] == "bank-recovery":
        values = [
            ("invalid", "ring", 99, True),
            ("repair", "ring", 0.7, False),
            ("edit", "power", 0.65, False),
            ("stale_revision", "power", 0.8, True),
        ]
    elif task["id"] == "repeated-edit":
        values = [("edits", "power", 0.6 + i * 0.01, False) for i in range(task["count"])]
    for action, key, value, fails in values:
        expected = "initial" if action == "stale_revision" else "revision"
        legacy_key, replacement = ("knobs", {"ring": value}) if route == "python" and key == "ring" else (key, value)
        code = f"r=change({expected},{legacy_key!r},{replacement!r})\nrevision=r['authored_revision']\n"
        if route == "dsl" and response == "compact":
            code += "emit(r)"
        elif route == "dsl" and workflow == "narrow":
            code += "emit(project_fields(r,['authored_revision','changed','affected_total']))"
        else:
            code += "emit(r)"
        before = session.namespace["path"].read_bytes()
        previous = session.namespace["revision"]
        session.step(action, code, fails=fails)
        if fails:
            assert session.namespace["path"].read_bytes() == before and session.namespace["revision"] == previous
    session.step(
        "export",
        "c=build_file(path,name=target)\nwrite_wav(output,c.audio,c.sr)\nemit({'output':'audio.wav','frames':len(c.audio),'sample_rate':c.sr})",
    )


def cases():
    corpus = json.loads(CORPUS.read_text())
    result = []
    for row in corpus["tasks"]:
        for variant in row.get("sizes", row.get("counts", [None])):
            task = copy.deepcopy(row)
            if variant is not None:
                task["size" if "sizes" in row else "count"] = variant
            task["case"] = row["id"] + (f"-{variant}" if variant is not None else "")
            result.append(task)
    return result


def expected_audio(task, asset, *, initial=False):
    """Independent manual existing-API oracle, never used to prepare route state."""
    kind = task["id"]
    if kind in (
        "single",
        "discovery",
        "refinement",
        "invalid-repair",
        "bank",
        "bank-recovery",
        "repeated-edit",
        "shared-definition",
    ):
        power = (
            0.8
            if kind == "shared-definition"
            else 0.65
            if kind in ("bank", "bank-recovery")
            else 0.6 + (task["count"] - 1) * 0.01
            if kind == "repeated-edit"
            else 0.5
        )
        ring = 0.7 if kind in ("invalid-repair", "bank-recovery") else 0.3 if task["track"] == "persisted" else None
        if initial:
            power, ring = 0.5, 0.3 if kind == "invalid-repair" else None
        voice = Sfx(
            "ui",
            "crystal",
            species=0 if task["track"] == "persisted" else 7,
            power=power,
            dry=True,
            **({"knobs": {"ring": ring}} if ring is not None else {}),
        ).voice("confirm")
        if kind == "refinement" and not initial:
            voice.modal[0].hardness, voice.lowpass = 1234, 2400
        return capture(voice, 16000)
    if kind == "variants":
        score = Score(sr=16000, hall=0)
        for take in range(4):
            score.add(
                capture(
                    Sfx("ui", "crystal", species=7, power=0.5 if initial else 0.8, dry=True).voice(
                        "confirm", take=take
                    ),
                    16000,
                ).audio,
                at=take * 0.25,
            )
        return capture(score)
    if kind == "arrangement":
        score = Score(sr=16000, hall=0, bpm=120)
        score.track("lead-v1").play("harp", [(60 if initial else 48, i * 4, 1, 0.8) for i in range(8)])
        return capture(score, loop=16)
    if kind == "missing-asset":
        y, sr = read_channels(asset)
        return capture(y, sr)
    if kind == "capability":
        from tare.tools.tune.effects import fm_tone

        return capture(fm_tone(duration=0.1, sr=16000), 16000)
    from tare.tools.tune.music import Cue
    from tare.tools.tune.speech import Speaker

    score = Score(sr=16000, hall=0, effects=[{"type": "limiter", "ceiling": 0.5}])
    for at, child in (
        (0, Creature("mammal", species="wolf").voice("attack")),
        (0.1, Speaker.preset("deep").voice("Ready!", "en", seed=17)),
        (0.2, Cue("levelup", seed=4, sr=16000)),
    ):
        score.add(capture(child, 16000).audio, at=at)
    y, _ = read_channels(asset)
    score.add(y, at=0.3)
    return capture(score)


def verify_wav(path, captured):
    exported, sr = read_channels(path)
    assert sr == captured.sr and exported.shape == captured.audio.shape
    quantized = (np.clip(captured.audio, -1, 1) * 32767).astype("<i2").astype(np.float32) / 32767
    np.testing.assert_array_equal(exported, quantized)


def midi_notes(path):
    """Independent reader for exported SMF channel notes and tick coordinates."""
    data = path.read_bytes()
    assert data[:4] == b"MThd" and int.from_bytes(data[12:14], "big") == 960
    notes, cursor = [], 14

    def number(buf, offset):
        value = 0
        while True:
            byte = buf[offset]
            offset += 1
            value = value * 128 + (byte & 127)
            if not byte & 128:
                return value, offset

    while cursor < len(data):
        assert data[cursor : cursor + 4] == b"MTrk"
        size = int.from_bytes(data[cursor + 4 : cursor + 8], "big")
        buf = data[cursor + 8 : cursor + 8 + size]
        offset, tick = 0, 0
        while offset < len(buf):
            delta, offset = number(buf, offset)
            tick += delta
            status = buf[offset]
            offset += 1
            if status == 255:
                length, offset = number(buf, offset + 1)
                offset += length
            else:
                length = 1 if status & 0xF0 in (0xC0, 0xD0) else 2
                if status & 0xF0 in (0x80, 0x90):
                    notes.append((tick, status & 0xF0, buf[offset], buf[offset + 1]))
                offset += length
        cursor += 8 + size
    return notes


def verify(session, original):
    task, namespace = session.task, session.namespace
    observed = list(dict.fromkeys(t["action"] for t in session.turns if t["action"] != "setup"))
    assert observed == task["actions"], (observed, task["actions"])
    captured = namespace["c"]
    expected = expected_audio(task, namespace["asset"])
    assert np.array_equal(captured.audio, expected.audio), task["case"]
    verify_wav(namespace["output"], captured)
    if task["track"] == "persisted":
        updated = json.loads(namespace["path"].read_text())
        target = namespace["target"]
        expected_doc = copy.deepcopy(original)
        if task["id"] != "capability":
            values = expected_doc["sounds"][target]["with" if "format" in original else "options"]
            values["power"] = 0.6 + (task["count"] - 1) * 0.01 if task["id"] == "repeated-edit" else 0.65
            if task["id"] == "bank-recovery":
                values["ring" if "format" in original else "knobs"] = 0.7 if "format" in original else {"ring": 0.7}
        assert updated == expected_doc
        if task["id"] != "capability":
            assert list((session.folder / ".tune-backups").glob("*.bak"))
    if task["id"] == "arrangement":
        score = namespace["p"].plan.source if "p" in namespace else namespace["score"]
        assert [(e["pitch"], e["beat"], e["beats"]) for e in score.tracks["lead-v1"].events] == [
            (48, i * 4, 1) for i in range(8)
        ]
        notes = midi_notes(namespace["output"].with_suffix(".mid"))
        assert [(tick, pitch) for tick, status, pitch, velocity in notes if status == 0x90 and velocity] == [
            (i * 4 * 960, 48) for i in range(8)
        ]
        assert [(tick, pitch) for tick, status, pitch, velocity in notes if status == 0x80] == [
            ((i * 4 + 1) * 960, 48) for i in range(8)
        ]
    if task["id"] == "shared-definition":
        wanted = capture(Sfx("ui", "crystal", species=7, power=0.8, dry=True).voice("confirm", take=1), 16000)
        verify_wav(session.folder / "second.wav", wanted)
        if "d" in namespace:
            assert namespace["d"]["sounds"]["other"] == {"sfx": "ui", "event": "error", "dry": True}
            other = capture_compiled_for_name(namespace["path"], namespace["d"], "other")
        else:
            other = namespace["other"]
        wanted_other = capture(Sfx("ui", dry=True).voice("error"), 16000)
        assert np.array_equal(other.audio, wanted_other.audio)
    return {
        "pcm_equal": True,
        "wav_verified": True,
        "actions_verified": observed,
        "pcm_id": captured.manifest["pcm_id"],
    }


def run_case(task, route, folder, workflow="control", response="detailed"):
    folder.mkdir(parents=True)
    session = Session(folder, task)
    original = None
    if task["id"] == "scene":
        write_wav(folder / "contact.wav", np.tile([0.125, -0.125], (160, 1)).astype(np.float32), 16000)
    if task["track"] == "persisted":
        if task["id"] == "capability":
            legacy = {"sample_rate": 16000, "sounds": {"sound_000": {"type": "fm", "options": {"duration": 0.1}}}}
            dsl = document(None, sounds={"sound_000": {"fm": {"duration": 0.1}}})
        else:
            legacy, dsl = bank_documents(task["size"])
        original = dsl if route == "dsl" else legacy
        (folder / "source.json").write_bytes(canonical(original))
    tracemalloc.start()
    begin = time.perf_counter()
    try:
        if task["track"] == "memory":
            memory_case(session, route, workflow, response)
        else:
            persisted_case(session, route, response, workflow)
        acceptance = verify(session, original)
        success, error = True, None
    except Exception as exc:
        acceptance, success, error = {}, False, f"{type(exc).__name__}: {exc}"
    finally:
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    return {
        "success": success,
        "error": error,
        "acceptance": acceptance,
        "turns": session.turns,
        "seconds": time.perf_counter() - begin,
        "tool_seconds": sum(t["seconds"] for t in session.turns),
        "tracked_peak_bytes": peak,
        "initial_source_bytes": len(canonical(original)) if original else None,
    }


def capture_compiled_for_name(path, data, name):
    from tare.tools.tune.dsl import compile_document, load
    from tare.tools.tune.dsl.compiler import capture_compiled

    return capture_compiled(compile_document(load(path, data=data), name=name))


def metrics(result, tiktoken):
    for encoding in ("cl100k_base", "o200k_base"):
        token = tiktoken.get_encoding(encoding)

        def count(value, token=token):
            return len(token.encode(value if isinstance(value, str) else canonical(value).decode()))

        rows, groups = {}, {}
        for name, case in result["cases"].items():
            rows[name] = {}
            for route, run in case["routes"].items():
                phases = {}
                request = response = 0
                context = count(PRIMER) + count(case["instruction"]) + count(case.get("inputs", {}))
                total = context
                repeated = 0
                for turn in run["turns"]:
                    sent, received = count(turn["request"]), count(turn["response"])
                    request += sent
                    response += received
                    total += sent + received
                    repeated += context + sent + received
                    context += sent + received
                    phases[turn["action"]] = phases.get(turn["action"], 0) + sent + received
                bootstrap = {
                    "setup",
                    "create",
                    "observe",
                    "discover",
                    "select_recipe",
                    "missing",
                    "create_asset",
                    "recover",
                }
                cold = (
                    context
                    if not run["turns"]
                    else count(PRIMER) + count(case["instruction"]) + count(case.get("inputs", {}))
                )
                cold += sum(v for k, v in phases.items() if k in bootstrap)
                edit_actions = {
                    "shared_edit",
                    "transpose",
                    "hardness",
                    "filter",
                    "filter_again",
                    "invalid",
                    "repair",
                    "edits",
                    "edit",
                    "stale_revision",
                    "stale_materialization",
                }
                edits = sum(v for k, v in phases.items() if k in edit_actions)
                rows[name][route] = {
                    "content_tokens": total,
                    "request_tokens": request,
                    "response_tokens": response,
                    "setup_tokens": phases.get("setup", 0),
                    "cold_bootstrap_tokens": cold,
                    "warm_continuation_tokens": total - cold if edits else None,
                    "edit_tokens": edits,
                    "amortized_tokens_per_edit": total / case["inputs"]["edit_count"]
                    if case.get("inputs", {}).get("edit_count")
                    else None,
                    "phases": phases,
                    "summed_context_tokens_simulated": repeated,
                    "tool_calls": len(run["turns"]),
                    "expected_failures": sum(t["expected_error"] for t in run["turns"]),
                }
            if all(run["success"] for run in case["routes"].values()):
                groups.setdefault(case["track"], []).append(name)
        aggregates = {}
        for track, names in groups.items():
            warm = [
                n
                for n in names
                if rows[n]["python"]["warm_continuation_tokens"] and rows[n]["dsl"]["warm_continuation_tokens"]
            ]
            aggregates[track] = {
                "successful_pairs": len(names),
                "median_dsl_to_python": statistics.median(
                    rows[n]["dsl"]["content_tokens"] / rows[n]["python"]["content_tokens"] for n in names
                ),
                "warm_pairs": len(warm),
                "median_warm_dsl_to_python": statistics.median(
                    rows[n]["dsl"]["warm_continuation_tokens"] / rows[n]["python"]["warm_continuation_tokens"]
                    for n in warm
                )
                if warm
                else None,
                "p90_warm_tokens": {
                    r: sorted(rows[n][r]["warm_continuation_tokens"] for n in warm)[math.ceil(0.9 * len(warm)) - 1]
                    for r in ("python", "dsl")
                }
                if warm
                else None,
                "attempted_pairs": sum(c["track"] == track for c in result["cases"].values()),
                "p90_content_tokens": {
                    r: sorted(rows[n][r]["content_tokens"] for n in names)[math.ceil(0.9 * len(names)) - 1]
                    for r in ("python", "dsl")
                },
            }
        result.setdefault("metrics", {})[encoding] = {"cases": rows, "by_service_contract": aggregates}


def checkpoint(*, workflow="control", response="detailed", only=None, artifacts=None):
    result = {
        "protocol": "executed-semantic-workflows/2",
        "workflow": workflow,
        "response": response,
        "cases": {},
        "corpus_id": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
        "primer": PRIMER,
        "limits": [
            "Scripted decisions; no live-agent success or billing claim.",
            "Existing public APIs; all helper setup counted. Common paths and supplied input files are provisioned equally.",
            "Persisted cases start with supplied source; initial source bytes are recorded, not charged as unrequested reading.",
            "Proxy tokenizers; repeated context simulated; tracemalloc is not process RSS.",
        ],
    }
    if artifacts is not None:
        artifacts.mkdir(parents=True, exist_ok=True)
    with contextlib.ExitStack() as stack:
        temporary = (
            tempfile.mkdtemp(prefix="run-", dir=artifacts)
            if artifacts is not None
            else stack.enter_context(tempfile.TemporaryDirectory(prefix="tune-semantic-v2-"))
        )
        result["artifact_directory"] = str(temporary) if artifacts is not None else None
        for task in cases():
            if only and task["id"] not in only and task["case"] not in only:
                continue
            rows = {}
            for route in ("python", "dsl"):
                rows[route] = run_case(task, route, Path(temporary) / (task["case"] + "-" + route), workflow, response)
            result["cases"][task["case"]] = {
                "track": task["track"],
                "instruction": task["instruction"],
                "required_actions": task["actions"],
                "inputs": {
                    "sample_rate": 16000,
                    "bank_size": task.get("size"),
                    "edit_count": task.get("count"),
                    "power_values": [0.6 + i * 0.01 for i in range(task["count"])] if "count" in task else None,
                },
                "routes": rows,
                "dsl_representation": "existing builders"
                if task["id"] in ("variants", "arrangement", "scene", "shared-definition")
                else "DSL data",
            }
    root = CORPUS.parents[4]
    result["environment"] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {p: importlib.metadata.version(p) for p in ("numpy", "scipy", "tiktoken")},
        "source_id": digest(
            {
                str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for folder in (root / "src", root / "tools")
                for p in sorted(folder.rglob("*"))
                if p.suffix in (".py", ".html")
            }
        ),
    }
    result["success"] = bool(result["cases"]) and all(
        r["success"] for c in result["cases"].values() for r in c["routes"].values()
    )
    return result
