"""How intelligible is the speech? Whisper transcribes our output; we report character error rate.

    pip install -e ".[asr]"
    python tools/intelligibility.py                      # all sentences, default voices
    python tools/intelligibility.py --voices child robot --lang en -v

A lower CER is better (0 = perfect). Whisper has a language model, so it also rewards
plausible words; treat the numbers as a regression signal for tuning, not as ground truth.
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from creaturesynth.speech import Speaker  # noqa: E402

SENTENCES = {
    "pt": [
        "Olá, viajante! Bem-vindo à nossa vila.",
        "Você viu o dragão perto da montanha?",
        "Cuidado com os lobos na floresta.",
        "Eu preciso de três poções de cura.",
        "A ponte do norte caiu ontem à noite.",
        "Essa espada custa cinquenta moedas.",
        "O ferreiro mora na casa amarela.",
        "Obrigado pela ajuda, meu amigo.",
        "O rei quer falar com você agora.",
        "Leve esta carta até o castelo.",
        "Não entre na caverna sem uma tocha.",
        "Os soldados estão cansados da guerra.",
        "Eu vendo pão, queijo e vinho.",
        "Onde fica a taverna mais próxima?",
        "A bruxa mora do outro lado do rio.",
        "Feliz aniversário, Laíse!",
    ],
    "en": [
        "Hello, traveler! Welcome to our village.",
        "Did you see the dragon near the mountain?",
        "Watch out for the wolves in the forest.",
        "I need three healing potions.",
        "The north bridge fell down last night.",
        "This sword costs fifty gold coins.",
        "The blacksmith lives in the yellow house.",
        "Thank you for your help, my friend.",
        "The king wants to speak with you now.",
        "Take this letter to the castle.",
        "Do not enter the cave without a torch.",
        "The soldiers are tired of the war.",
        "I sell bread, cheese and wine.",
        "Where is the nearest tavern?",
        "The witch lives across the river.",
        "Happy birthday, Laise!",
    ],
}


def norm(text: str, lang: str = "en") -> str:
    from creaturesynth.speech import g2p_en, g2p_pt
    words = (g2p_pt if lang == "pt" else g2p_en).number_to_words
    text = re.sub(r"\d+", lambda m: f" {words(int(m.group()))} ", text)
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text)).strip()


def cer(ref: str, hyp: str, lang: str = "en") -> float:
    a, b = norm(ref, lang), norm(hyp, lang)
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ca != cb))
    return d[len(b)] / max(len(a), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="small")
    ap.add_argument("--lang", choices=["pt", "en", "both"], default="both")
    ap.add_argument("--voices", nargs="+", default=["default", "high", "child", "deep"])
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    from faster_whisper import WhisperModel
    model = WhisperModel(a.model, device="cpu", compute_type="int8")
    langs = ["pt", "en"] if a.lang == "both" else [a.lang]
    for lang in langs:
        for voice in a.voices:
            speaker = Speaker.preset(voice)
            scores = []
            for text in SENTENCES[lang]:
                y = speaker.render(text, lang, sr=48_000)
                y16 = np.concatenate([np.zeros(8000), resample_poly(y, 1, 3), np.zeros(8000)]).astype(np.float32)
                segs, _ = model.transcribe(y16, language=lang, beam_size=5, vad_filter=False,
                                           condition_on_previous_text=False)
                hyp = " ".join(s.text.strip() for s in segs)
                scores.append(cer(text, hyp, lang))
                if a.verbose:
                    print(f"  [{lang}/{voice}] {scores[-1]:.2f}  {text!r} -> {hyp!r}", flush=True)
            print(f"{lang} {voice:8s} CER {np.mean(scores):.3f}  (median {np.median(scores):.3f})", flush=True)


if __name__ == "__main__":
    main()
