"""Language-independent result of text analysis: phrases of words of syllables of phones."""
from dataclasses import dataclass, field

VOWELS = {"a", "6", "e", "E", "i", "I", "o", "O", "u", "U", "A", "{", "V", "@", "3`",
          "6~", "e~", "i~", "o~", "u~"}


def is_vowel(phone: str) -> bool:
    return phone in VOWELS


@dataclass
class Syllable:
    phones: list[str] = field(default_factory=list)
    stressed: bool = False

    @property
    def nucleus(self) -> int:
        return next((i for i, p in enumerate(self.phones) if is_vowel(p)), 0)


@dataclass
class Word:
    text: str
    syllables: list[Syllable]
    clitic: bool = False      # unstressed function word ("de", "the"...)


@dataclass
class Phrase:
    words: list[Word]
    kind: str                 # "." statement, "?" question, "!" exclamation, "," continuation,
                              # "?!" surprise ("Sério?!", "O quê?!"), "…" trailing off ("Eu não sei...")
    wh: bool = False          # question that starts with a question word (falls instead of rising)


KINDS = (".", "?", "!", ",", "?!", "…")


def phrase_kind(punctuation: str) -> str:
    """The kind of phrase a run of punctuation ends: "?!" or "!?" surprise, "..." or "…" trailing off, ";" and ":"
    a continuation, doubled marks as single ones."""
    if "?" in punctuation and "!" in punctuation:
        return "?!"
    if "…" in punctuation or punctuation.count(".") >= 2:
        return "…"
    return {";": ",", ":": ","}.get(punctuation[0], punctuation[0])


def transcription(phrases: list[Phrase]) -> str:
    """Readable form, e.g. "o.'la | vi.a.'Z6~.tSI ." (debugging and tests)."""
    out = []
    for p in phrases:
        words = [".".join(("'" if s.stressed else "") + "".join(s.phones) for s in w.syllables) for w in p.words]
        out.append(" ".join(words) + f" {p.kind}")
    return " | ".join(out)
