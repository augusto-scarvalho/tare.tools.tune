"""The Godot extension (native/godot) voices a planned line as the Python reference does. Needs Godot (on the PATH,
or TARE_TOOLS_TUNE_GODOT) and the extension built: python tools/build_native.py godot."""
import os
import platform
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tare.tools.tune.render import render
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


def test_godot_voices_lines_like_python(tmp_path):
    banks = [tvb.export(name, tmp_path / f"{name.replace('/', '_')}.tvb") for name in ("pt/alex", "pt/dora")]
    voices = {"ferreiro": Speaker(pitch=110, engine="natural").voice("Bem-vindo à forja, viajante!", "pt"),
              "viajante": Speaker(pitch=200, tract=1.15, crush=0.1, engine="natural").voice(
                  "[alegria] Que bom te ver! [tristeza] Mas eu preciso partir...", "pt")}
    for name, voice in voices.items():
        (tmp_path / f"{name}.json").write_text(voice.to_json(), encoding="utf-8")
    subprocess.run([GODOT, "--headless", "--path", str(DEMO), "--import"], check=True, timeout=600)
    subprocess.run([GODOT, "--headless", "--path", str(DEMO), "--script", "res://tests/render.gd", "--",
                    str(tmp_path), "48000", *map(str, banks), *(str(tmp_path / f"{n}.json") for n in voices)],
                   check=True, timeout=600)
    for name, voice in voices.items():
        got, expected = np.fromfile(tmp_path / f"{name}.f32", np.float32), render(voice, 48000)
        assert len(got) == len(expected), name
        assert np.max(np.abs(got - expected)) < 1e-5, name
