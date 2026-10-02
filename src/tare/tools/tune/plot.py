"""Spectrograms for sound design (optional: pip install tare.tools.tune[plot])."""
from pathlib import Path

import numpy as np


def spectrogram(audio: np.ndarray, sr: int, path: str | Path, max_hz: float = 10_000, title: str = "") -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 3))
    with np.errstate(divide="ignore"):
        ax.specgram(audio, NFFT=1024, Fs=sr, noverlap=768, cmap="magma", vmin=-110)
    ax.set_ylim(0, max_hz)
    ax.set_xlabel("s")
    ax.set_ylabel("Hz")
    ax.set_title(title or Path(path).stem, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=80)
    plt.close(fig)
    return Path(path)
