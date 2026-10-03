"""The Godot extension (native/godot) renders voice specs (lines, sound effects) as the Python reference does. Needs
Godot (on the PATH, or TARE_TOOLS_TUNE_GODOT) and the extension built: python tools/build_native.py godot."""
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tare.tools.tune import Creature, Sfx
from tare.tools.tune.render import render
from tare.tools.tune.sfx.knobs import apply as apply_knobs
from tare.tools.tune.speech import Speaker, tvb

DEMO = Path(__file__).parent.parent / "native" / "godot" / "demo"
LIBRARY = {"Windows": "tare_tune.windows.template_debug.x86_64.dll",
           "Linux": "libtare_tune.linux.template_debug.x86_64.so"}.get(platform.system(), "")
GODOT = os.environ.get("TARE_TOOLS_TUNE_GODOT") or shutil.which("godot")
if GODOT and platform.system() == "Windows":      # the console build prints, and runs headless without crashing
    console = Path(os.path.realpath(GODOT)).with_name(Path(os.path.realpath(GODOT)).stem + "_console.exe")
    GODOT = str(console) if console.exists() else GODOT
pytestmark = pytest.mark.skipif(not GODOT or not LIBRARY or not (DEMO / "bin" / LIBRARY).exists(),
                                reason="needs Godot and the extension built")


def test_godot_renders_like_python(tmp_path):
    banks = [tvb.export(name, tmp_path / f"{name.replace('/', '_')}.tvb") for name in ("pt/alex", "pt/dora")]
    voices = {"ferreiro": Speaker(pitch=110, engine="natural").voice("Bem-vindo à forja, viajante!", "pt"),
              "viajante": Speaker(pitch=200, tract=1.15, crush=0.1, engine="natural").voice(
                  "[alegria] Que bom te ver! [tristeza] Mas eu preciso partir...", "pt"),
              "confirm": Sfx("ui", "crystal", species=2).voice("confirm"),
              "clash": Sfx("blade", "steel", species=3).voice("clash"),
              "rain": Sfx("ambience", "rain").voice("loop"),
              "wolf": Creature("mammal", species=7).voice("attack"),
              "shell": Sfx("status", "fantasy", species=4, era="16bit").voice("shell")}
    knobs = {"shell": {"register": -0.5, "tempo": 1.5, "sparkle": 0}}           # turned in the game, over the spec
    (tmp_path / "shell.knobs.json").write_text(json.dumps(knobs["shell"]), encoding="utf-8")
    for name, voice in voices.items():
        (tmp_path / f"{name}.json").write_text(voice.to_json(), encoding="utf-8")
    subprocess.run([GODOT, "--headless", "--path", str(DEMO), "--import"], check=True, timeout=600)
    subprocess.run([GODOT, "--headless", "--path", str(DEMO), "--script", "res://tests/render.gd", "--",
                    str(tmp_path), "48000", *map(str, banks), *(str(tmp_path / f"{n}.json") for n in voices)],
                   check=True, timeout=600)
    for name, voice in voices.items():
        expected = render(apply_knobs(voice, knobs.get(name, {})), 48000)
        for path in (tmp_path / f"{name}.f32", tmp_path / f"{name}.text.f32"):
            got = np.fromfile(path, np.float32)
            assert len(got) == len(expected), path.name
            assert np.max(np.abs(got - expected)) < 1e-5, path.name
