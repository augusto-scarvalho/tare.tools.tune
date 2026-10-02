import numpy as np
import pytest

from creaturesynth import Creature
from creaturesynth.bake import bake, load_bestiary
from creaturesynth.cli import main
from creaturesynth.speech import Speaker, g2p_pt
from creaturesynth.speech.babble import gibberish, melody, mumble
from creaturesynth.speech.casting import ROLES, cast

SR = 16_000


def shape(phrases):
    return [(p.kind, [[s.stressed for s in w.syllables] for w in p.words]) for p in phrases]


def test_gibberish_keeps_rhythm_and_punctuation():
    phrases = g2p_pt.text_to_phrases("Você viu o dragão? Corre!")
    fake = gibberish(phrases, "pt", seed=1)
    assert shape(fake) == shape(phrases)
    assert [s.phones for p in fake for w in p.words for s in w.syllables] != \
           [s.phones for p in phrases for w in p.words for s in w.syllables]
    assert shape(gibberish(phrases, "pt", 1)) == shape(fake) and gibberish(phrases, "pt", 1) == fake
    assert gibberish(phrases, "pt", 2) != fake
    assert all(s.phones == ["m", "@"] for p in mumble(phrases) for w in p.words for s in w.syllables)
    notes = melody(phrases, seed=3)
    assert len(notes) == sum(len(w.syllables) for p in phrases for w in p.words) and max(map(abs, notes)) <= 5


def test_babble_styles_render():
    sp = Speaker.preset("cute")
    text = "Olá, viajante! Tudo bem?"
    lengths = {style: len(sp.render(text, "pt", SR, style=style)) for style in ("speech", "gibberish", "animalese")}
    assert lengths["animalese"] < 0.7 * lengths["speech"]             # Animalese chatters fast
    assert sp.voice(text, style="gibberish").speech[0].phonemes != sp.voice(text).speech[0].phonemes
    assert sp.voice(text, style="mumble") == sp.voice(text, style="mumble")
    with pytest.raises(ValueError):
        sp.speech(text, style="klingon")


def test_cast_divides_the_work():
    king = cast("main", "rei", gender="m", natural=False)
    assert not king.natural and isinstance(king.speaker, Speaker) and king.speaker.pitch <= 150
    assert cast("main", "rei", gender="m", natural=False) == king                # repeatable per name
    queen = cast("main", "rainha", gender="f")                                  # natural by default
    assert queen.natural and queen.speaker.pitch >= 165 and queen.voice("Olá").spoken
    assert queen.speaker.but(engine="formant") == cast("main", "rainha", gender="f", natural=False).speaker
    assert cast("minor", "ana", gender="f").speaker.pitch >= 165
    assert cast("minor", "ana") != cast("minor", "bia")
    assert cast("crowd", "povo").style == "gibberish"
    assert cast("robot").speaker.crush > 0 and cast("robot").style == "speech"
    small, big = Creature("mammal", 1, size=0.2), Creature("monster", 1, size=0.9, aggression=0.8)
    assert cast("creature", creature=small).style == "animalese"
    assert cast("creature", creature=big).style == "gibberish" and cast("creature", creature=big).speaker.rough > 0
    assert cast("creature", creature=big, style="speech").style == "speech"
    fallback = cast("main", "rei", voice="natural:m", natural=False)          # formant only: same register
    assert not fallback.natural and fallback.speaker.pitch <= 150
    assert cast("main", "rei", voice="kokoro:pm_alex").speaker.bank == "pt/alex"   # old names: natural voices
    assert cast(voice="deep", name="ferreiro").speaker == Speaker.preset("deep").but(name="ferreiro")
    with pytest.raises(ValueError):
        cast("hero")
    with pytest.raises(ValueError):
        cast("creature")
    with pytest.raises(ValueError):
        cast(gender="x")
    assert set(ROLES) == {"main", "minor", "crowd", "creature", "robot"}


def test_bestiary_roles_bake(tmp_path):
    data = {"natural_voices": False, "lang": "pt",
            "creatures": {"rato": {"archetype": "mammal", "species": "rato", "size": 0.15}},
            "speakers": {"rei": {"role": "main", "gender": "m", "lines": {"oi": "Salve o reino!"}},
                         "povo": {"role": "crowd", "lines": {"oi": "Que dia bonito."}},
                         "rato": {"creature": "rato", "lines": {"oi": "Oi, amigo!"}},
                         "guarda": {"voice": "deep", "style": "mumble", "lines": {"oi": "Hum."}}}}
    creatures, settings = load_bestiary(data)
    m = bake(creatures, tmp_path, calls=["idle"], takes=1, sr=SR, workers=1, speakers=settings["speakers"])
    s = m["speakers"]
    assert s["rei"]["engine"] == "formant" and s["rei"]["role"] == "main" and "spec" in s["rei"]["lines"]["oi"]
    assert s["povo"]["style"] == "gibberish" and s["rato"]["style"] == "animalese" and s["rato"]["role"] == "creature"
    assert s["guarda"]["style"] == "mumble" and s["guarda"]["speaker"]["pitch"] == Speaker.preset("deep").pitch
    _, natural = load_bestiary({**data, "natural_voices": True})
    assert natural["speakers"]["rei"][0].natural
    _, forced = load_bestiary({**data, "natural_voices": True}, natural=False)
    assert not forced["speakers"]["rei"][0].natural
    for bad in ({"rato": {"creature": "gato"}}, {"rei": {"roll": "main"}}):
        with pytest.raises(ValueError):
            load_bestiary({**data, "speakers": bad})


def test_bake_still_takes_plain_speakers(tmp_path):
    m = bake({}, tmp_path, sr=SR, workers=1, speakers={"x": (Speaker.preset("child"), "pt", {"oi": "Oi!"})})
    assert m["speakers"]["x"]["engine"] == "formant" and m["speakers"]["x"]["style"] == "speech"


def test_cli_say_roles(tmp_path, capsys):
    out = tmp_path / "x.wav"
    assert main(["say", "Que dia bonito!", "--role", "crowd", "--name", "povo", "-o", str(out), "--sr", str(SR)]) == 0
    assert "crowd: formant voice, gibberish" in capsys.readouterr().err and out.exists()
    assert main(["say", "Oi!", "--gender", "f", "--style", "animalese", "-o", str(out), "--sr", str(SR)]) == 0
    assert np.isfinite(np.frombuffer(out.read_bytes()[44:], dtype=np.int16)).all()
