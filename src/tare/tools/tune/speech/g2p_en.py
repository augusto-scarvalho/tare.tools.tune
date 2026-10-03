"""English (General American) text -> phonemes.

Known words come from the CMU Pronouncing Dictionary (BSD-2, data/LICENSE-cmudict); unknown
words (fantasy names!) fall back to inflection stripping and then to spelling rules.
"""
import gzip
import re
from functools import cache
from importlib.resources import files

from .units import Phrase, Syllable, Word, is_vowel, phrase_kind, transcription

ARPA = {
    "AA": ["A"], "AE": ["{"], "AO": ["O"], "AW": ["a", "w"], "AY": ["a", "j"], "EH": ["E"], "ER": ["3`"],
    "EY": ["e", "j"], "IH": ["I"], "IY": ["i"], "OW": ["o", "w"], "OY": ["O", "j"], "UH": ["U"], "UW": ["u"],
    "B": ["b"], "CH": ["tS"], "D": ["d"], "DH": ["D"], "F": ["f"], "G": ["g"], "HH": ["h"], "JH": ["dZ"],
    "K": ["k"], "L": ["l"], "M": ["m"], "N": ["n"], "NG": ["N"], "P": ["p"], "R": ["r\\"], "S": ["s"],
    "SH": ["S"], "T": ["t"], "TH": ["T"], "V": ["v"], "W": ["w"], "Y": ["j"], "Z": ["z"], "ZH": ["Z"],
}
FUNCTION_WORDS = {"a", "an", "the", "of", "to", "and", "or", "but", "in", "on", "at", "by", "for", "with", "from",
                  "as", "is", "are", "was", "were", "be", "been", "am", "it", "its", "that", "than", "then", "your",
                  "my", "his", "her", "our", "their", "him", "them", "us", "me", "we", "you", "he", "she", "they",
                  "i", "do", "does", "did", "has", "have", "had", "can", "will", "would", "should", "could", "not",
                  "so", "if", "into", "onto", "up", "there", "this", "these", "those", "some", "any"}
WH_WORDS = {"what", "where", "when", "why", "who", "whom", "whose", "which", "how"}
def _legal_onset(cluster: tuple[str, ...]) -> bool:
    if len(cluster) <= 1:
        return not cluster or cluster[0] not in ("N",)
    return " ".join(cluster) in _ONSET_SET


_ONSET_SET = {
    "p r\\", "b r\\", "t r\\", "d r\\", "k r\\", "g r\\", "f r\\", "T r\\", "S r\\",
    "p l", "b l", "k l", "g l", "f l", "s l", "t w", "d w", "k w", "s w", "T w",
    "p j", "b j", "k j", "m j", "f j", "v j", "h j", "s p", "s t", "s k", "s m", "s n", "s f",
    "s p r\\", "s t r\\", "s k r\\", "s p l", "s k l", "s k w", "s p j", "s k j",
}


@cache
def cmudict() -> dict[str, list[str]]:
    raw = gzip.decompress((files(__package__) / "data" / "cmudict.gz").read_bytes()).decode()
    out = {}
    for line in raw.splitlines():
        word, _, phones = line.partition(" ")
        out[word] = phones.split()
    return out


# --- numbers ---------------------------------------------------------------------------------------

_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
         "sixteen seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def number_to_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        t, u = divmod(n, 10)
        return _TENS[t] + (f" {_ONES[u]}" if u else "")
    if n < 1000:
        h, r = divmod(n, 100)
        return f"{_ONES[h]} hundred" + (f" {number_to_words(r)}" if r else "")
    if n < 1_000_000:
        k, r = divmod(n, 1000)
        return f"{number_to_words(k)} thousand" + (f" {number_to_words(r)}" if r else "")
    return " ".join(_ONES[int(d)] for d in str(n))


# --- spelling rules for unknown words -----------------------------------------------------------------

_RULES = [  # (spelling, phones); longest match first, left to right
    ("tion", ["S", "@", "n"]), ("sion", ["Z", "@", "n"]), ("ture", ["tS", "3`"]), ("ough", ["o", "w"]),
    ("eigh", ["e", "j"]), ("igh", ["a", "j"]), ("tch", ["tS"]), ("dge", ["dZ"]), ("sch", ["s", "k"]),
    ("ch", ["tS"]), ("sh", ["S"]), ("th", ["T"]), ("ph", ["f"]), ("wh", ["w"]), ("ck", ["k"]), ("ng", ["N"]),
    ("qu", ["k", "w"]), ("ee", ["i"]), ("ea", ["i"]), ("oo", ["u"]), ("ou", ["a", "w"]), ("ow", ["o", "w"]),
    ("ai", ["e", "j"]), ("ay", ["e", "j"]), ("oi", ["O", "j"]), ("oy", ["O", "j"]), ("au", ["O"]), ("aw", ["O"]),
    ("ie", ["i"]), ("ei", ["e", "j"]), ("ue", ["u"]), ("ew", ["j", "u"]), ("ar", ["A", "r\\"]),
    ("or", ["O", "r\\"]), ("er", ["3`"]), ("ir", ["3`"]), ("ur", ["3`"]), ("ll", ["l"]), ("ss", ["s"]),
    ("tt", ["t"]), ("pp", ["p"]), ("bb", ["b"]), ("dd", ["d"]), ("ff", ["f"]), ("gg", ["g"]), ("mm", ["m"]),
    ("nn", ["n"]), ("rr", ["r\\"]), ("zz", ["z"]), ("x", ["k", "s"]),
    ("a", ["{"]), ("e", ["E"]), ("i", ["I"]), ("o", ["A"]), ("u", ["V"]), ("b", ["b"]), ("d", ["d"]),
    ("f", ["f"]), ("h", ["h"]), ("j", ["dZ"]), ("k", ["k"]), ("l", ["l"]), ("m", ["m"]), ("n", ["n"]),
    ("p", ["p"]), ("r", ["r\\"]), ("t", ["t"]), ("v", ["v"]), ("w", ["w"]), ("z", ["z"]),
]
_LONG = {"a": ["e", "j"], "e": ["i"], "i": ["a", "j"], "o": ["o", "w"], "u": ["j", "u"], "y": ["a", "j"]}


def spell_out(word: str) -> list[tuple[str, int]]:
    """Rough General American guess for a word outside the dictionary: [(phone, stress)]."""
    w = re.sub(r"[^a-z]", "", word)
    magic = re.search(r"([aeiouy])([^aeiouy])e$", w)
    if magic and len(w) > 3:
        w = w[:-1]
    out, i = [], 0
    while i < len(w):
        if magic and i == magic.start(1):
            out += _LONG[w[i]]
            i += 1
            continue
        ch, nxt = w[i], w[i + 1:i + 2]
        if ch == "c":
            out.append("s" if nxt in ("e", "i", "y") else "k")
            i += 1
            continue
        if ch == "g":
            out.append("dZ" if nxt in ("e", "i", "y") and i > 0 else "g")
            i += 1
            continue
        if ch == "y":
            out.append("j" if i == 0 else ("i" if i == len(w) - 1 else "I"))
            i += 1
            continue
        if ch == "s":
            between = 0 < i < len(w) - 1 and w[i - 1] in "aeiou" and nxt in ("a", "e", "i", "o", "u")
            out.append("z" if between or (i == len(w) - 1 and i > 0 and w[i - 1] not in "ptkf") else "s")
            i += 1
            continue
        for spelling, phones in _RULES:
            if w.startswith(spelling, i):
                out += phones
                i += len(spelling)
                break
        else:
            i += 1
    stressed, result = False, []
    for p in out:
        stress = 0
        if is_vowel(p) and not stressed:
            stress, stressed = 1, True
        result.append((p, stress))
    return result


def _lookup(word: str) -> list[tuple[str, int]]:
    d = cmudict()
    if word in d:
        return _from_arpa(d[word])
    for suffix, extra in (("'s", ["Z"]), ("s'", ["Z"]), ("s", ["Z"]), ("es", ["I", "Z"]), ("ed", ["d"]),
                          ("ing", ["I", "N"]), ("ly", ["l", "i"]), ("er", ["3`"]), ("ers", ["3`", "Z"])):
        base = word[: -len(suffix)]
        if word.endswith(suffix) and base in d:
            return _from_arpa(d[base]) + [(p, 0) for p in extra]
    return spell_out(word)


def _from_arpa(arpa: list[str]) -> list[tuple[str, int]]:
    out = []
    for a in arpa:
        base, stress = re.match(r"([A-Z]+)(\d?)", a).groups()
        phones = ["@"] if base == "AH" and stress == "0" else ["V"] if base == "AH" else ARPA[base]
        for i, p in enumerate(phones):
            out.append((p, int(stress) if stress and i == 0 else 0))
    return out


def word_to_phonemes(word: str, clitic: bool = False) -> Word:
    phones = _lookup(word)
    if clitic:
        phones = [("@" if p == "V" else p, 0) for p, _ in phones]
    # American flap: t/d between a vowel (or r) and an unstressed vowel
    for i in range(1, len(phones) - 1):
        p, prev, nxt = phones[i][0], phones[i - 1][0], phones[i + 1]
        if p in ("t", "d") and (is_vowel(prev) or prev == "r\\") and is_vowel(nxt[0]) and nxt[1] == 0:
            phones[i] = ("r", 0)
    nuclei = [i for i, (p, _) in enumerate(phones) if is_vowel(p)]
    if not nuclei:
        return Word(word, [Syllable([p for p, _ in phones])], clitic)
    starts = [0]
    for a, b in zip(nuclei, nuclei[1:], strict=False):
        between = list(range(a + 1, b))
        glides = [k for k in between if phones[k][0] in ("j", "w") and k == a + 1]  # diphthong offglide
        cons = [k for k in between if k not in glides]
        start = b
        for n in range(min(3, len(cons)), 0, -1):
            if _legal_onset(tuple(phones[k][0] for k in cons[-n:])):
                start = cons[-n]
                break
        starts.append(start)
    sylls = []
    for s, e in zip(starts, starts[1:] + [len(phones)], strict=False):
        chunk = phones[s:e]
        sylls.append(Syllable([p for p, _ in chunk], stressed=any(st == 1 for _, st in chunk)))
    return Word(word, sylls, clitic)


def normalize(text: str) -> list[tuple[list[str], str]]:
    text = re.sub(r"\d+", lambda m: f" {number_to_words(int(m.group()))} ", text.lower())
    text = text.replace("-", " ").replace("—", ",").replace("’", "'")
    phrases, words = [], []
    for token in re.findall(r"[a-z]+(?:'[a-z]+)?|[.!?…]{2,}|[.!?,;:…]", text):
        if token[0] in ".!?,;:…":
            if words:
                phrases.append((words, phrase_kind(token)))
                words = []
        else:
            words.append(token)
    if words:
        phrases.append((words, "."))
    return phrases


def text_to_phrases(text: str) -> list[Phrase]:
    phrases = []
    for words, kind in normalize(text):
        ws = [word_to_phonemes(w, clitic=w in FUNCTION_WORDS and len(words) > 1) for w in words]
        phrases.append(Phrase([w for w in ws if w.syllables], kind, wh=kind in ("?", "?!") and words[0] in WH_WORDS))
    return [p for p in phrases if p.words]


def transcribe(text: str) -> str:
    return transcription(text_to_phrases(text))
