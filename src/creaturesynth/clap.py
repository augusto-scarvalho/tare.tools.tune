"""CLAP as an ear for creatures (optional: pip install "creaturesynth[clap]").

CLAP embeds audio and text in one space, so it can say how much a sound "is" a description.
We use it to check that archetypes sound like what they claim (zero-shot labels) and to
design creatures from a text prompt or a reference sample by searching genes and traits.
Optimise against one CLAP model and judge with another, or the search learns to fool one.
"""
from functools import cache

import numpy as np

SR = 48_000                                   # CLAP works on 48 kHz audio
OPTIMISER = "laion/clap-htsat-unfused"         # Apache-2.0
JUDGE = "laion/larger_clap_general"            # Apache-2.0, held out from optimisation

LABELS = {  # zero-shot label -> archetypes it is a correct answer for
    "a dog barking": {"mammal"}, "a wolf howling": {"mammal"}, "a cat meowing": {"mammal"},
    "a lion roaring": {"mammal", "monster"}, "a small animal squeaking": {"mammal"},
    "a bird singing": {"bird"}, "a crow cawing": {"bird"}, "a cricket chirping": {"insect"},
    "a fly buzzing": {"insect"}, "cicadas singing": {"insect"}, "a snake hissing": {"reptile"},
    "a frog croaking": {"amphibian"}, "a monster roaring": {"monster"}, "a monster screeching": {"monster"},
    "slime bubbling": {"slime"}, "water bubbling": {"slime"}, "a ghost moaning": {"spirit"},
    "a robot beeping": {"robot"}, "an 8-bit video game sound effect": {"chip"},
    "a person speaking": set(), "music": set(), "white noise": set(),
}


class Clap:
    def __init__(self, model_id: str = OPTIMISER):
        try:
            import torch
            from transformers import ClapModel, ClapProcessor
        except ImportError:
            raise ImportError('CLAP needs transformers + torch: pip install "creaturesynth[clap]"') from None
        self.torch = torch
        self.model = ClapModel.from_pretrained(model_id).eval()
        self.processor = ClapProcessor.from_pretrained(model_id)
        self._text_cache: dict[str, np.ndarray] = {}

    def audio(self, clips: list[np.ndarray], sr: int = SR) -> np.ndarray:
        if sr != SR:
            from math import gcd

            from scipy.signal import resample_poly
            g = gcd(sr, SR)
            clips = [resample_poly(c, SR // g, sr // g) for c in clips]
        inputs = self.processor(audio=[np.asarray(c, dtype=np.float32) for c in clips], sampling_rate=SR,
                                return_tensors="pt")
        with self.torch.no_grad():
            emb = self.model.get_audio_features(**inputs)
        emb = getattr(emb, "pooler_output", emb)
        emb = emb.numpy()
        return emb / np.linalg.norm(emb, axis=1, keepdims=True)

    def text(self, texts: list[str]) -> np.ndarray:
        missing = [t for t in texts if t not in self._text_cache]
        if missing:
            inputs = self.processor(text=missing, return_tensors="pt", padding=True)
            with self.torch.no_grad():
                emb = self.model.get_text_features(**inputs)
            emb = getattr(emb, "pooler_output", emb).numpy()
            for t, e in zip(missing, emb / np.linalg.norm(emb, axis=1, keepdims=True), strict=True):
                self._text_cache[t] = e
        return np.stack([self._text_cache[t] for t in texts])

    def similarity(self, clips: list[np.ndarray], texts: list[str], sr: int = SR) -> np.ndarray:
        """Cosine similarity, clips x texts."""
        return self.audio(clips, sr) @ self.text(texts).T

    def classify(self, clips: list[np.ndarray], labels: list[str] | None = None, sr: int = SR) -> list[str]:
        labels = labels or list(LABELS)
        return [labels[i] for i in np.argmax(self.similarity(clips, labels, sr), axis=1)]


@cache
def load(model_id: str = OPTIMISER) -> Clap:
    return Clap(model_id)
