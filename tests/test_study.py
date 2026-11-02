"""TUNE study: what a recording is made of, and what in tune makes each part. Synthetic or rendered signals only."""

import json

import numpy as np
from test_ear import impact

from tare.tools.tune import Creature, Sfx, render
from tare.tools.tune.audio_io import write_wav
from tare.tools.tune.cli import main
from tare.tools.tune.speech import Speaker
from tare.tools.tune.study import study, text


def test_an_impact_reads_as_an_sfx_with_its_length_and_a_line_reads_its_speaker_pitch(tmp_path, capsys):
    write_wav(tmp_path / "hit.wav", impact(), 16000)
    hit = study(tmp_path / "hit.wav")
    assert hit["schema"] == "tune.study/1" and not hit["kind"]["pitched"]  # a 3 kHz ring has no pitch
    assert hit["in_tune"][0]["use"] == "sfx" and any(h.get("field") == "knobs.length" for h in hit["in_tune"])
    assert "IN TUNE" in text(hit) and "REC peaks" in text(hit)
    write_wav(tmp_path / "line.wav", render(Speaker(pitch=150).voice("O caminho para o norte está fechado.", "pt"),
                                            16000), 16000)
    assert "cannot" in study(tmp_path / "line.wav")["in_tune"][0]  # pitched: speech, creature or tonal sfx?
    line = study(tmp_path / "line.wav", "speech")["in_tune"]
    pitch = next(h["value"] for h in line if h.get("field") == "speaker.pitch")
    assert line[0]["use"] == "say" and abs(pitch - 150) <= 7.5  # within 5% of what the line was rendered with
    assert main(["study", str(tmp_path / "hit.wav"), "--json"]) in (None, 0)
    assert json.loads(capsys.readouterr().out)["facts"]["f0"]["status"] == "ring"
    assert hit["in_tune"][0]["why"].startswith("a 3000 Hz ring")
    write_wav(tmp_path / "quiet.wav", np.zeros(1600), 16000)
    assert study(tmp_path / "quiet.wav")["kind"] == {"status": "silent"}


def test_search_finds_the_render_a_recording_came_from(tmp_path, monkeypatch):
    write_wav(tmp_path / "confirm.wav", render(Sfx("ui", "crystal").voice("confirm", 0), 16000), 16000)
    found = study(tmp_path / "confirm.wav", find="sfx:ui")["search"]
    assert found["nearest"][0] == {"sound": {"sfx": "ui", "style": "crystal", "event": "confirm"}, "distance": 0.0}
    assert found["of"] > 50 and "never how it sounds" in found["compares"]
    monkeypatch.setattr("tare.tools.tune.creature.ARCHETYPES", ("mammal",))  # one archetype keeps it quick
    write_wav(tmp_path / "wolf.wav", Creature("mammal", size=0.6).render("alert", sr=16000), 16000)
    nearest = study(tmp_path / "wolf.wav", "creature", find="creature")["search"]["nearest"][0]
    assert nearest == {"sound": {"creature": "mammal", "call": "alert", "size": 0.6}, "distance": 0.0}
