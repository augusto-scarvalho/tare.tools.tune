import json

import numpy as np
import pytest

from creaturesynth import Creature, Voice, read_wav, render
from creaturesynth.bake import bake, load_bestiary
from creaturesynth.cli import main
from creaturesynth.runtime import VoiceBank
from creaturesynth.speech import PRESETS, Speaker, g2p_en, g2p_pt

SR = 22_050


@pytest.mark.parametrize("word, expected", [
    ("Laíse", "la.'i.zI"), ("viajante", "vi.a.'Z6~.tSI"), ("dragão", "dra.'g6~w~"), ("montanha", "mo~.'ta.J6"),
    ("noite", "'noj.tSI"), ("cidade", "si.'da.dZI"), ("carro", "'ka.RU"), ("caro", "'ka.rU"), ("rato", "'Ra.tU"),
    ("casa", "'ka.z6"), ("guerra", "'ge.R6"), ("água", "'a.gw6"), ("cinquenta", "si~.'kwe~.t6"),
    ("homem", "'o.me~j~"), ("também", "t6~.'be~j~"), ("pão", "'p6~w~"), ("põe", "'po~j~"), ("falam", "'fa.l6~w~"),
    ("Brasil", "bra.'ziw"), ("saída", "sa.'i.d6"), ("rainha", "Ra.'i.J6"), ("sair", "sa.'iR"),
    ("música", "'mu.zi.k6"), ("filho", "'fi.LU"), ("chuva", "'Su.v6"), ("exemplo", "e.'ze~.plU"),
    ("nascer", "na.'seR"), ("quatro", "'kwa.trU"), ("linguiça", "li~.'gwi.s6"),
])
def test_portuguese_words(word, expected):
    assert g2p_pt.transcribe(word) == expected + " ."


def test_portuguese_phrases_and_numbers():
    assert g2p_pt.number_to_words(1984) == "mil novecentos e oitenta e quatro"
    assert g2p_pt.number_to_words(250) == "duzentos e cinquenta"
    phrases = g2p_pt.text_to_phrases("Olá, viajante! Você viu os amigos? 3 moedas.")
    assert [p.kind for p in phrases] == [",", "!", "?", "."]
    assert "'os" not in g2p_pt.transcribe("os amigos")          # clitic: unstressed
    assert g2p_pt.transcribe("os amigos").startswith("Uz")       # final s voiced before a vowel


@pytest.mark.parametrize("text, expected", [
    ("hello", "h@.'low"), ("dragon", "'dr\\{.g@n"), ("water", "'wO.r3`"), ("potions", "'pow.S@nz"),
    ("strength", "'str\\ENkT"), ("Zorblax", "'zOr\\.bl{ks"),
])
def test_english_words(text, expected):
    assert g2p_en.transcribe(text) == expected + " ."


def test_english_phrases():
    assert g2p_en.number_to_words(1984) == "one thousand nine hundred eighty four"
    assert g2p_en.transcribe("the dragon").startswith("D@ ")   # function word reduced
    wh, yn = g2p_en.text_to_phrases("Where is it? Is it here?")
    assert wh.wh and not yn.wh
    assert len(g2p_en.cmudict()) > 100_000


@pytest.mark.parametrize("lang, text", [("pt", "Olá, viajante! Bem-vindo à nossa vila."),
                                        ("en", "Hello, traveler! Welcome to our village.")])
@pytest.mark.parametrize("preset", list(PRESETS))
def test_every_preset_speaks(preset, lang, text):
    audio = Speaker.preset(preset).render(text, lang, sr=SR)
    assert audio.dtype == np.float32 and np.isfinite(audio).all()
    assert 1.0 < len(audio) / SR < 10 and 0.2 < np.abs(audio).max() <= 0.9


def test_deterministic_and_spec_round_trip():
    s = Speaker.random(7)
    v = s.voice("Cuidado com os lobos!", "pt")
    assert np.array_equal(render(v, SR), render(s.voice("Cuidado com os lobos!", "pt"), SR))
    again = Voice.from_json(v.to_json())
    assert again == v and np.array_equal(render(again, SR), render(v, SR))
    assert json.loads(v.to_json())["version"] == 2


def test_spec_v1_documents_still_load():
    v1 = Creature("mammal", 3).voice().to_dict()
    v1["version"] = 1
    assert Voice.from_dict(v1).syllables


def _final_pitch(text, lang):
    """Pitch at the end of the utterance relative to its median."""
    frames = Speaker().speech(text, lang).frames
    f0 = np.array(frames["f0"])[np.array(frames["av"]) > 0.5]
    return f0[-1] / np.median(f0)


def test_intonation():
    assert _final_pitch("Você viu o dragão?", "pt") > 1.15 > 0.9 > _final_pitch("Você viu o dragão.", "pt")
    assert _final_pitch("Você viu a montanha?", "pt") > _final_pitch("Você viu a montanha.", "pt") + 0.2
    assert _final_pitch("Did you see the dragon?", "en") > 1.2
    assert _final_pitch("Where is the dragon?", "en") < 0.9     # wh-questions fall
    assert _final_pitch("I saw the dragon.", "en") < 0.9


def test_speakers_vary_and_follow_creatures():
    a, b = Speaker.random(1), Speaker.random(2)
    assert a != b and a == Speaker.random(1)
    assert all(80 <= Speaker.random(s).pitch <= 260 for s in range(50))
    big = Speaker.from_creature(Creature("monster", 1, size=0.95, aggression=0.9))
    small = Speaker.from_creature(Creature("mammal", 1, size=0.1, aggression=0.1))
    assert big.pitch < small.pitch and big.rough > small.rough
    with pytest.raises(ValueError):
        Speaker.preset("pirate")
    with pytest.raises(ValueError):
        Speaker().speech("hola", "es")


def test_bake_lines_and_runtime(tmp_path):
    creatures, settings = load_bestiary({"creatures": {}, "lang": "pt", "speakers": {
        "ferreiro": {"voice": "deep", "lines": {"oi": "Bem-vindo à forja!"}},
        "guard": {"voice": "npc:12", "lang": "en", "lines": {"halt": "Halt!"}},
        "fada": {"voice": {"preset": "fairy", "rate": 1.2}, "lines": {"oi": "Oi!"}}}})
    manifest = bake(creatures, tmp_path, sr=SR, workers=1, speakers=settings["speakers"])
    line = manifest["speakers"]["guard"]["lines"]["halt"]
    assert manifest["speakers"]["guard"]["lang"] == "en" and manifest["speakers"]["fada"]["speaker"]["rate"] == 1.2
    audio, sr = read_wav(tmp_path / line["file"])
    assert sr == SR and abs(len(audio) / sr - line["duration"]) < 1e-3

    with VoiceBank(sample_rate=SR) as bank:
        a = bank.line(Speaker.preset("child"), "Olá!")
        assert isinstance(a, np.ndarray) and bank.line(Speaker.preset("child"), "Olá!") is a


def test_cli_say(tmp_path, capsys):
    out = tmp_path / "ola.wav"
    assert main(["say", "Olá, mundo!", "--voice", "child", "--phonemes", "-o", str(out), "--sr", str(SR)]) == 0
    assert "o.'la" in capsys.readouterr().out and out.exists()
    assert main(["say", "Hello there", "--lang", "en", "--voice", "npc:3", "--pitch", "150",
                 "-o", str(tmp_path / "hi.wav"), "--sr", str(SR)]) == 0
    assert main(["voices"]) == 0
    assert main(["say", "oi", "--voice", "pirate"]) == 1
