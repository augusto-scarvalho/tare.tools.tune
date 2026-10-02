"""Optional natural-sounding speech: Kokoro-82M (Apache-2.0), pt-BR and English.

    pip install "creaturesynth[neural]"     # kokoro + soundfile (pulls PyTorch)

Unlike the formant voices this is not procedural or portable: it renders audio directly
(no voice spec) and needs PyTorch. It shares the `render(text, lang, sr)` interface, so
bake, VoiceBank and the CLI accept it anywhere a Speaker goes ("kokoro:<voice>").
"""
import os
import tempfile
from dataclasses import dataclass
from functools import cache
from math import gcd

import numpy as np
from scipy.signal import resample_poly

from .. import rng
from ..render import DEFAULT_SR, PEAK, _crush, _reverb

KOKORO_SR = 24_000
LANG_CODES = {"pt": "p", "en": "a"}
DEFAULT_VOICES = {"pt": "pf_dora", "en": "af_heart"}
VOICES = {"pt": ["pf_dora", "pm_alex", "pm_santa"],
          "en": ["af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky", "am_adam", "am_echo", "am_eric",
                 "am_liam", "am_michael", "am_onyx", "am_puck"]}


def available() -> bool:
    try:
        import kokoro  # noqa: F401
        return True
    except ImportError:
        return False


def _fix_espeak_data_path():
    """espeakng-loader 0.2.x ships espeak-ng 1.52, which only honours a data path that also
    contains an `espeak-ng-data` folder (otherwise it looks in its build machine's path)."""
    try:
        import espeakng_loader
        import misaki.espeak  # noqa: F401  (sets the library and the data path it expects)
        from phonemizer.backend.espeak.wrapper import EspeakWrapper
    except ImportError:
        return
    real = espeakng_loader.get_data_path()
    shim = os.path.join(tempfile.gettempdir(), "creaturesynth-espeak-ng-data")
    os.makedirs(shim, exist_ok=True)
    for name in os.listdir(real):
        if not os.path.lexists(os.path.join(shim, name)):
            os.symlink(os.path.join(real, name), os.path.join(shim, name))
    if not os.path.lexists(os.path.join(shim, "espeak-ng-data")):
        os.symlink(real, os.path.join(shim, "espeak-ng-data"))
    EspeakWrapper.set_data_path(shim)


@cache
def _pipeline(lang: str):
    if not available():
        raise ImportError('natural voices need Kokoro: pip install "creaturesynth[neural]"')
    if lang not in LANG_CODES:
        raise ValueError(f"unsupported language {lang!r}; choose from {', '.join(LANG_CODES)}")
    _fix_espeak_data_path()
    from kokoro import KPipeline
    return KPipeline(lang_code=LANG_CODES[lang], repo_id="hexgrad/Kokoro-82M")


@dataclass(frozen=True)
class NeuralSpeaker:
    voice: str = ""           # Kokoro voice id; empty = the language's default
    speed: float = 1.0
    space: float = 0.0        # reverb, seconds (same effects as the procedural voices)
    drive: float = 0.0
    crush: float = 0.0
    name: str = ""

    def render(self, text: str, lang: str = "pt", sr: int = DEFAULT_SR) -> np.ndarray:
        voice = self.voice or DEFAULT_VOICES[lang]
        parts = [r.audio.numpy() for r in _pipeline(lang)(text, voice=voice, speed=self.speed) if r.audio is not None]
        if not parts:
            raise ValueError("nothing to say")
        y = np.concatenate(parts).astype(np.float64)
        g = gcd(sr, KOKORO_SR)
        y = resample_poly(y, sr // g, KOKORO_SR // g)
        y /= np.max(np.abs(y)) + 1e-12
        if self.crush:
            y = _crush(y, self.crush)
        if self.drive:
            y = np.tanh(self.drive * y) / np.tanh(self.drive)
        if self.space:
            y = _reverb(y, sr, self.space, 0.18, rng.key(rng.fnv1a(text), "space"))
        return (PEAK * y / (np.max(np.abs(y)) + 1e-12)).astype(np.float32)
