import numpy as np
import pytest

from tare.tools.tune.render import render
from tare.tools.tune.spec import Voice
from tare.tools.tune.speech import Speaker, g2p_en, g2p_pt
from tare.tools.tune.speech.emotion import EMOTIONS, Emotion, emotion, split

SR = 16_000


@pytest.mark.parametrize("text, kinds", [
    ("Você viu o dragão?", [("?", False)]), ("Onde fica a taverna?", [("?", True)]),
    ("O que você quer?", [("?", True)]), ("Sério?!", [("?!", False)]), ("Eu não sei...", [("…", False)]),
    ("Bem… talvez.", [("…", False), (".", False)]), ("Que lindo!", [("!", False)]),
])
def test_phrase_kinds_pt(text, kinds):
    assert [(p.kind, p.wh) for p in g2p_pt.text_to_phrases(text)] == kinds


def test_phrase_kinds_en():
    assert [(p.kind, p.wh) for p in g2p_en.text_to_phrases("What?! Really... where is it?")] == \
        [("?!", True), ("…", False), ("?", True)]


def tail(sp, text, n=100):
    f = np.array(sp.spoken(text, "pt").f0)
    return f[f > 0][-n:]


def test_brazilian_question_tunes():
    sp = Speaker(pitch=120, engine="natural")
    statement, question = tail(sp, "Você comprou a espada."), tail(sp, "Você comprou a espada?")
    peak = int(np.argmax(question))
    assert question.max() > 1.3 * statement.max()              # the last stressed vowel rises...
    assert question[-1] < 0.8 * question.max() and 5 < peak < len(question) - 5   # ...and what follows falls
    oxytone = tail(sp, "Você viu o dragão?")
    assert oxytone[-1] > 1.3 * np.median(oxytone[:10])          # ends high
    wh = tail(sp, "Onde você comprou a espada?")
    assert wh[-1] < 0.8 * wh[0]                                  # a wh-question falls
    surprise = tail(sp, "Você comprou a espada?!")
    assert surprise.max() > 1.15 * question.max()
    hanging = sp.spoken("Você comprou a espada...", "pt")
    assert hanging.duration > sp.spoken("Você comprou a espada.", "pt").duration
    h = tail(sp, "Você comprou a espada...", 20)
    assert h.min() > 0.85 * h.max()                              # level, left hanging


def test_tags_split_a_line():
    parts = split("[alegria] Que bom! [tristeza:0.5] Pena... sem tag")
    assert [t for _, t in parts] == ["Que bom!", "Pena... sem tag"]
    assert parts[0][0] == EMOTIONS["alegria"].scaled(0.8) and parts[1][0] == EMOTIONS["tristeza"].scaled(0.5)
    assert split("Oi", "feliz")[0][0] == emotion("alegria") and split("Oi")[0][0] == Emotion()
    with pytest.raises(ValueError):
        split("[eufórico] Oi")


@pytest.mark.parametrize("engine", ["natural", "formant"])
def test_emotions_move_the_voice(engine):
    sp = Speaker(pitch=120, engine=engine)
    text = "Ele voltou para a vila ontem."

    def pitch(e):
        v = sp.voice(text, "pt", emotion=e)
        layer = (v.spoken or v.speech)[0]
        f0 = np.array(layer.f0 if engine == "natural" else layer.frames["f0"])
        return np.median(f0[f0 > 0]), (v.spoken or v.speech)[0].duration
    neutral, happy, sad = pitch(None), pitch("alegria"), pitch("tristeza")
    assert happy[0] > 1.3 * neutral[0] and sad[1] > neutral[1]
    v = sp.voice("[alegria] Que bom te ver! [tristeza] Mas eu preciso ir.", "pt")
    layers = v.spoken or v.speech
    assert len(layers) == 2 and layers[1].start >= layers[0].duration
    assert Voice.from_json(v.to_json()) == v and np.isfinite(render(v, SR)).all()


def test_whisper_and_less_air():
    sp = Speaker(engine="natural")
    assert sp.voice("Fique quieto.", "pt", emotion="sussurro").spoken[0].breath >= 0.8
    assert sp.voice("Que bom!", "pt", emotion="alegria").spoken[0].breath < 0


@pytest.mark.parametrize("pitch, tract", [(120, 1.0), (180, 1.15)])
def test_sung_exclamations_keep_their_voice(pitch, tract):
    """A high "Sério?!" must not take its vowels from where the teacher's voice faded to breath (a hiss)."""
    from tare.tools.tune.speech import concat
    sp = Speaker(pitch=pitch, tract=tract, engine="natural")
    for text in ("Sério?!", "É sério?", "Jura?!", "Ah, é?"):
        layer = sp.spoken(text, "pt")
        _, _, voiced = concat.frames(concat.bank(layer.bank), layer.pieces, layer.joins)
        phones, k, quiet, total = layer.phonemes.split(), 0, 0, 0
        for i, p in enumerate(phones):
            n = layer.pieces[2 * i][2] + layer.pieces[2 * i + 1][2]
            if p.rstrip("'") in concat.SONORANT:
                quiet, total = quiet + int((~voiced[k:k + n]).sum()), total + n
            k += n
        assert quiet < 0.05 * total, text


def test_pauses_are_silent():
    """The teacher reads through most commas: a pause must come from a real silence, not murmur."""
    from tare.tools.tune.speech import concat
    layer = Speaker(pitch=120, engine="natural").spoken("Olá, viajante! Eu vendo pão, queijo e vinho.", "pt")
    _, _, voiced = concat.frames(concat.bank(layer.bank), layer.pieces, layer.joins)
    k, inside = 0, []
    for i, p in enumerate(layer.phonemes.split()):
        n = layer.pieces[2 * i][2] + layer.pieces[2 * i + 1][2]
        if p == "_":
            inside.append(voiced[k + n // 4:k + 3 * n // 4].mean())   # the middle; the edges belong to the joins
        k += n
    assert len(inside) >= 4 and max(inside) < 0.2
