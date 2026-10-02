"""Brazilian Portuguese text -> phonemes, by rule.

Portuguese spelling is regular enough that a few dozen context rules get most words right:
digraphs, glides, nasal vowels, t/d palatalisation, the s/r/x/l alternations, vowel
reduction in final syllables, and stress from accents or word endings.

Phoneme symbols (X-SAMPA-like):
    vowels   a 6 e E i I o O u U   nasal: 6~ e~ i~ o~ u~   glides: j w j~ w~
    stops    p b t d k g           affricates: tS dZ
    fric.    f v s z S Z R(=h)     nasals: m n J    liquids: l L r(tap)
"""
import re
from dataclasses import dataclass

from .units import Phrase, Syllable, Word, is_vowel, transcription

VOWEL_LETTERS = set("aeiouáéíóúâêôãõàü")
ACUTE_OR_CIRC = set("áéíóúâêô")
FRONT = set("eéêiíy")
OBSTRUENTS = set("pbtdcgfvkG")
VOICED_C = set("bdgvzjmnlr") | {"lh", "nh", "Z"}
OPEN_MID = True  # stressed unaccented e/o open before a coda r/l (porta, certo) and in -a paroxytones (nossa)
CLOSED_MID = {"mesa", "boca", "moça", "toda", "todas", "força", "forças", "verde", "verdes", "cerca", "cercas",
              "pessoa", "pessoas", "esposa", "esposas", "seda", "medo", "pelo", "pela", "pelas", "perda", "cedo"}
CODA_R = "R"   # r at the end of a syllable: "R" fricative (Rio, A/B-tuned) or "r" tap (São Paulo)
KW_WORDS = {"cinquenta", "frequente", "frequência", "tranquilo", "tranquila", "linguiça", "aguentar", "aguenta",
            "consequência", "sequência", "pinguim", "bilíngue", "eloquente", "delinquente", "quinquênio",
            "arguir", "unguento", "sagui", "equino", "equestre", "quiproquó"}
CLITICS = {"o", "a", "os", "as", "um", "uns", "de", "da", "do", "das", "dos", "e", "que", "se", "em", "me",
           "te", "lhe", "nos", "vos", "por", "com", "na", "no", "nas", "ao", "aos", "à", "às", "pra", "pro",
           "lhes", "sem", "mas", "nem", "num", "numa"}


# --- numbers -----------------------------------------------------------------------------------

_UNITS = "zero um dois três quatro cinco seis sete oito nove dez onze doze treze catorze quinze dezesseis " \
         "dezessete dezoito dezenove".split()
_TENS = "_ _ vinte trinta quarenta cinquenta sessenta setenta oitenta noventa".split()
_HUNDREDS = "_ cento duzentos trezentos quatrocentos quinhentos seiscentos setecentos oitocentos novecentos".split()


def number_to_words(n: int) -> str:
    if n < 20:
        return _UNITS[n]
    if n < 100:
        t, u = divmod(n, 10)
        return _TENS[t] + (f" e {_UNITS[u]}" if u else "")
    if n < 1000:
        if n == 100:
            return "cem"
        h, r = divmod(n, 100)
        return _HUNDREDS[h] + (f" e {number_to_words(r)}" if r else "")
    if n < 1_000_000:
        k, r = divmod(n, 1000)
        head = "mil" if k == 1 else f"{number_to_words(k)} mil"
        if not r:
            return head
        return head + (" e " if r < 100 or r % 100 == 0 else " ") + number_to_words(r)
    return " ".join(number_to_words(int(d)) for d in str(n))


# --- text -> phrases of words --------------------------------------------------------------------

def normalize(text: str) -> list[tuple[list[str], str]]:
    text = re.sub(r"\d+", lambda m: f" {number_to_words(int(m.group()))} ", text.lower())
    text = text.replace("-", " ").replace("—", ",").replace("…", ".")
    phrases, words = [], []
    for token in re.findall(r"[a-zçáéíóúâêôãõàüy]+|[.!?,;:]", text):
        if token in ".!?,;:":
            if words:
                phrases.append((words, {";": ",", ":": ","}.get(token, token)))
                words = []
        else:
            words.append(token)
    if words:
        phrases.append((words, "."))
    return phrases


# --- one word ---------------------------------------------------------------------------------------

@dataclass
class _Unit:
    kind: str     # V vowel, G glide, C consonant
    g: str        # grapheme(s)
    ph: str = ""  # resolved phoneme


def _units(w: str) -> list[_Unit]:
    out, i, kw = [], 0, w in KW_WORDS
    while i < len(w):
        two, nxt = w[i:i + 2], w[i + 2:i + 3]
        if two in ("ch", "lh", "nh"):
            out.append(_Unit("C", two))
            i += 2
        elif two == "rr":
            out.append(_Unit("C", "rr"))
            i += 2
        elif two == "ss":
            out.append(_Unit("C", "ss"))
            i += 2
        elif two in ("qu", "gu", "qü", "gü") and nxt and nxt in VOWEL_LETTERS:
            out.append(_Unit("C", "k" if two[0] == "q" else "G"))
            if two[1] == "ü" or kw or nxt not in FRONT:
                out.append(_Unit("G", "u"))
            i += 2
        elif two in ("sc", "xc", "sç") and nxt and (nxt in FRONT or two == "sç"):
            out.append(_Unit("C", "ss"))
            i += 2
        elif w[i] in VOWEL_LETTERS:
            out.append(_Unit("V", w[i]))
            i += 1
        elif w[i] == "h":
            i += 1
        else:
            out.append(_Unit("C", w[i]))
            i += 1
    return out


def _mark_glides(u: list[_Unit]):
    for k, unit in enumerate(u):
        if unit.kind != "V" or unit.g not in "iuy" or k == 0:
            continue
        prev = u[k - 1]
        if prev.kind != "V":
            continue
        nxt = u[k + 1] if k + 1 < len(u) else None
        after = u[k + 2] if k + 2 < len(u) else None
        if nxt and nxt.g == "nh":
            continue  # ra-i-nha
        if nxt and nxt.kind == "C" and nxt.g in ("r", "l", "z", "m", "n") and (after is None or after.kind == "C"):
            continue  # sa-ir, ju-iz, ru-im
        if prev.kind == "V" and prev.g in "iu" and prev.g == unit.g:
            continue
        unit.kind = "G"
    for k in range(1, len(u)):  # ão, ãe, õe: the second vowel is a nasal glide
        if u[k - 1].g in "ãõ" and u[k].kind == "V" and u[k].g in "oe":
            u[k].kind = "G"
            u[k].g = "u" if u[k].g == "o" else "i"


def _syllabify(u: list[_Unit]) -> list[list[int]]:
    nuclei = [k for k, x in enumerate(u) if x.kind == "V"]
    if not nuclei:
        return [list(range(len(u)))]
    bounds = [0]
    for a, b in zip(nuclei, nuclei[1:], strict=False):
        between = list(range(a + 1, b))
        glides_after = [k for k in between if u[k].kind == "G" and k == a + 1]
        cons = [k for k in between if k not in glides_after]
        if not cons:
            bounds.append(b if not (between and u[between[-1]].kind == "G" and len(between) > 1) else between[-1])
            continue
        cs = [u[k] for k in cons]
        if len(cons) == 1:
            start = cons[0]
        elif cs[-1].kind == "G":  # rising glide after a consonant: á-gua, qua-tro
            start = cons[-3] if len(cs) > 2 and cs[-3].g in OBSTRUENTS and cs[-2].g in ("r", "l") else cons[-2]
        elif cs[-2].g in OBSTRUENTS and cs[-1].g in ("r", "l"):
            start = cons[-2]
        else:
            start = cons[-1]
        if u[start - 1].kind == "G" and start - 1 > a + 1:
            start -= 1
        bounds.append(start)
    bounds.append(len(u))
    return [list(range(s, e)) for s, e in zip(bounds, bounds[1:], strict=False)]


def _stress_index(word: str, sylls: list[list[int]], u: list[_Unit]) -> int:
    for i, syl in enumerate(sylls):
        if any(u[k].g in ACUTE_OR_CIRC for k in syl):
            return i
    for i, syl in enumerate(sylls):
        if any(u[k].g in "ãõ" for k in syl):
            return i
    if len(sylls) == 1:
        return 0
    if re.search(r"([aeo]s?|am|em|ens)$", word):
        return len(sylls) - 2
    return len(sylls) - 1


def _vowel(g: str, stressed: bool, final_syl: bool, post_tonic: bool) -> str:
    base = {"á": "a", "à": "a", "â": "6", "é": "E", "ê": "e", "í": "i", "ó": "O", "ô": "o", "ú": "u",
            "ã": "6~", "õ": "o~", "ü": "u", "y": "i"}.get(g, g)
    if stressed or g in "áàâéêíóôúãõ":
        return base
    if post_tonic and final_syl:
        return {"a": "6", "e": "I", "o": "U"}.get(base, base)
    if post_tonic:
        return {"e": "I", "o": "U"}.get(base, base)
    return base


def word_to_phonemes(word: str, clitic: bool = False) -> Word:
    u = _units(word)
    _mark_glides(u)
    sylls = _syllabify(u)
    stress = -1 if clitic else _stress_index(word, sylls, u)
    syl_of = {k: i for i, s in enumerate(sylls) for k in s}
    n = len(u)

    def nxt(k, off=1):
        return u[k + off] if 0 <= k + off < n else None

    for k, x in enumerate(u):
        si = syl_of[k]
        st, final, post = si == stress, si == len(sylls) - 1, stress >= 0 and si > stress
        if clitic and final:
            post = True  # unstressed function words reduce like post-tonic syllables
        if x.kind == "V":
            x.ph = _vowel(x.g, st, final, post)
            if OPEN_MID and st and x.g in "eo" and word not in CLOSED_MID and not re.search(r"(e[sz]a|oa)s?$", word):
                after, after2 = nxt(k), nxt(k, 2)
                # coda r/l inside the word (porta, certo) or final l (papel, sol); final -er/-or stay closed (fazer)
                coda_rl = after is not None and ((after.g in ("r", "l") and after2 is not None and after2.kind == "C")
                                                 or (after.g == "l" and after2 is None))
                if coda_rl or (si == len(sylls) - 2 and re.search(r"as?$", word)):
                    x.ph = "E" if x.g == "e" else "O"
            following = nxt(k)
            # nasal vowel before a coda m/n (the consonant disappears)
            if following and following.g in ("m", "n") and (nxt(k, 2) is None or nxt(k, 2).kind == "C"):
                x.ph = {"a": "6~", "6": "6~", "E": "e~", "e": "e~", "I": "i~", "i": "i~", "O": "o~", "o": "o~",
                        "U": "u~", "u": "u~"}.get(x.ph, x.ph)
                following.ph = "-"
                if nxt(k, 2) is None or (nxt(k, 2).g == "s" and nxt(k, 3) is None):
                    if x.g in "eéê" and following.g == "m" or (following.g == "n" and nxt(k, 2) is not None):
                        x.ph = "e~"
                    if x.ph == "e~":
                        following.ph = "j~"      # -em, -ens
                    elif x.ph == "6~" and x.g == "a":
                        following.ph = "w~"      # -am
        elif x.kind == "G":
            nasal = k > 0 and u[k - 1].g in "ãõ"
            x.ph = ("j" if x.g in "iey" else "w") + ("~" if nasal else "")
    for k, x in enumerate(u):
        if x.kind != "C" or x.ph:
            continue
        prev, after = nxt(k, -1), nxt(k)
        prev_is_v = prev is not None and prev.kind in ("V", "G")
        after_is_v = after is not None and after.kind in ("V", "G")
        g = x.g
        if g in ("p", "b", "f", "v", "m", "n", "k"):
            x.ph = g
        elif g == "G":
            x.ph = "g"
        elif g in ("t", "d"):
            x.ph = g + ("S" if g == "t" else "Z") if after is not None and after.ph in ("i", "I", "i~") else g
        elif g == "c":
            x.ph = "s" if after is not None and after.g in FRONT else "k"
        elif g == "ç" or g == "ss":
            x.ph = "s"
        elif g == "g":
            x.ph = "Z" if after is not None and after.g in FRONT and after.kind == "V" else "g"
        elif g == "j":
            x.ph = "Z"
        elif g == "ch":
            x.ph = "S"
        elif g == "lh":
            x.ph = "L"
        elif g == "nh":
            x.ph = "J"
        elif g == "rr":
            x.ph = "R"
        elif g == "r":
            coda = not after_is_v and not (prev is not None and prev.kind == "C")
            strong = k == 0 or (prev is not None and prev.g in ("n", "l", "s")) or (coda and CODA_R == "R")
            x.ph = "R" if strong else "r"
        elif g == "l":
            x.ph = "l" if after_is_v else "w"
        elif g == "s":
            if k == 0:
                x.ph = "s"
            elif prev_is_v and after_is_v:
                x.ph = "z"
            elif after is not None and after.kind == "C" and after.g in VOICED_C:
                x.ph = "z"
            else:
                x.ph = "s"
        elif g == "z":
            x.ph = "s" if after is None else "z"
        elif g == "x":
            if k == 0 or (prev is not None and prev.kind == "G"):
                x.ph = "S"
            elif k == 1 and prev is not None and prev.g == "e":
                x.ph = "z" if after_is_v else "s"
            elif after is None:
                x.ph = "ks"
            elif after_is_v:
                x.ph = "S"
            else:
                x.ph = "s"
        elif g == "w":
            x.ph = "w"
        elif g == "y":
            x.ph = "j"
        else:
            x.ph = g  # unknown letters pass through (filtered later)

    out = []
    for si, syl in enumerate(sylls):
        phones = []
        for k in syl:
            ph = u[k].ph
            if ph and ph != "-":
                phones.extend(["k", "s"] if ph == "ks" else [ph])
        out.append(Syllable(phones, stressed=si == stress))
    return Word(word, [s for s in out if s.phones], clitic=clitic)


def text_to_phrases(text: str) -> list[Phrase]:
    phrases = []
    for words, kind in normalize(text):
        ws = [word_to_phonemes(w, clitic=w in CLITICS and len(words) > 1) for w in words]
        for a, b in zip(ws, ws[1:], strict=False):  # final s before a vowel-initial word sounds like z
            if a.syllables and b.syllables and a.syllables[-1].phones[-1] == "s" and \
                    is_vowel(b.syllables[0].phones[0]):
                a.syllables[-1].phones[-1] = "z"
        phrases.append(Phrase([w for w in ws if w.syllables], kind))
    return [p for p in phrases if p.words]


def transcribe(text: str) -> str:
    return transcription(text_to_phrases(text))
