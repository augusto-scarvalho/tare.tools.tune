"""Voice resolution (always) and the optional Kokoro backend (only where it is installed)."""
import numpy as np
import pytest

from creaturesynth.bake import bake, load_bestiary
from creaturesynth.speech import NeuralSpeaker, Speaker, neural, speaker_from


def test_speaker_from_resolves_every_form():
    assert speaker_from("child") == Speaker.preset("child")
    assert speaker_from("npc:4") == Speaker.random(4)
    assert speaker_from("kokoro:pm_alex") == NeuralSpeaker(voice="pm_alex")
    assert speaker_from("kokoro") == NeuralSpeaker()
    assert speaker_from({"preset": "fairy", "rate": 1.2}).rate == 1.2
    assert speaker_from({"engine": "kokoro", "voice": "pf_dora", "speed": 0.9}) == NeuralSpeaker("pf_dora", 0.9)
    s = Speaker(pitch=99)
    assert speaker_from(s) is s
    with pytest.raises(ValueError):
        speaker_from("nobody")
    with pytest.raises(TypeError):
        speaker_from({"preset": "deep", "colour": "blue"})


def test_neural_voice_lists():
    assert set(neural.VOICES) == set(neural.LANG_CODES) == {"pt", "en"}
    assert all(v in neural.VOICES[lang] for lang, v in neural.DEFAULT_VOICES.items())


@pytest.mark.skipif(neural.available(), reason="Kokoro is installed")
def test_missing_kokoro_is_a_clear_error():
    with pytest.raises(ImportError, match="creaturesynth\\[neural\\]"):
        NeuralSpeaker().render("Olá", "pt")


requires_kokoro = pytest.mark.skipif(not neural.available(), reason="natural voices are optional (Kokoro)")


@requires_kokoro
@pytest.mark.parametrize("lang, text", [("pt", "Feliz aniversário, Laíse!"), ("en", "Hello there, traveler!")])
def test_kokoro_speaks(lang, text):
    y = NeuralSpeaker().render(text, lang, sr=22_050)
    assert y.dtype == np.float32 and np.isfinite(y).all()
    assert 0.8 < len(y) / 22_050 < 6 and 0.5 < np.abs(y).max() <= 0.9


@requires_kokoro
def test_kokoro_lines_bake_without_spec(tmp_path):
    creatures, settings = load_bestiary({"creatures": {}, "speakers": {
        "narrador": {"voice": "kokoro:pm_alex", "lines": {"oi": "Olá!"}},
        "guarda": {"voice": "deep", "lines": {"oi": "Olá!"}}}})
    m = bake(creatures, tmp_path, sr=22_050, workers=1, speakers=settings["speakers"])
    assert m["speakers"]["narrador"]["engine"] == "kokoro" and "spec" not in m["speakers"]["narrador"]["lines"]["oi"]
    assert m["speakers"]["guarda"]["engine"] == "formant" and "spec" in m["speakers"]["guarda"]["lines"]["oi"]
