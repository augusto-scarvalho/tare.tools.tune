"""Non-verbal speech for the formant voices: invented language, Animalese chirps, mumbling.

All three keep the text's rhythm and punctuation (so questions still rise and sentences
end), and are deterministic: the same line always babbles the same way.
"""
from .. import rng
from .units import Phrase, Syllable, Word

STYLES = ("speech", "gibberish", "animalese", "mumble")

INVENTORY = {  # (onsets, vowels) for invented words that still sound like the language
    "pt": (["p", "b", "t", "d", "k", "g", "m", "n", "l", "r", "s", "f", "v", "z", "S", "Z", "J", "", ""],
           ["a", "a", "e", "E", "i", "o", "O", "u", "6~", "e~", "o~"]),
    "en": (["p", "b", "t", "d", "k", "g", "m", "n", "l", "r\\", "s", "f", "v", "z", "S", "h", "w", "j", ""],
           ["{", "A", "E", "I", "i", "V", "@", "u", "o", "e"]),
}


def _pick(options, *key):
    return options[int(rng.uniform(rng.key(*key)) * len(options)) % len(options)]


def gibberish(phrases: list[Phrase], lang: str, seed: int = 0) -> list[Phrase]:
    """Same words count, syllable counts, stress and punctuation; invented sounds."""
    onsets, vowels = INVENTORY.get(lang, INVENTORY["en"])
    out = []
    for pi, p in enumerate(phrases):
        words = []
        for wi, w in enumerate(p.words):
            sylls = []
            for si, s in enumerate(w.syllables):
                key = (seed, "gib", w.text, si)
                phones = [x for x in (_pick(onsets, *key, "c"), _pick(vowels, *key, "v")) if x]
                if si == len(w.syllables) - 1 and rng.uniform(rng.key(*key, "coda")) < 0.25:
                    phones.append(_pick(["n", "s", "l", "r"] if lang == "pt" else ["n", "s", "l", "t", "k"], *key, "k"))
                sylls.append(Syllable(phones, stressed=s.stressed))
            words.append(Word(f"{w.text}~{pi}.{wi}", sylls, clitic=w.clitic))
        out.append(Phrase(words, p.kind, p.wh))
    return out


def mumble(phrases: list[Phrase]) -> list[Phrase]:
    """Every syllable hummed: m + schwa, keeping stress and phrasing."""
    return [Phrase([Word(w.text, [Syllable(["m", "@"], s.stressed) for s in w.syllables], w.clitic)
                    for w in p.words], p.kind, p.wh) for p in phrases]


def melody(phrases: list[Phrase], seed: int, depth: float = 5.0) -> list[float]:
    """Animalese: a random note (semitones) for every syllable, repeatable per line."""
    notes, i = [], 0
    for p in phrases:
        for w in p.words:
            for _s in w.syllables:
                notes.append(depth * (2 * rng.uniform(rng.key(seed, "note", i)) - 1))
                i += 1
    return notes

