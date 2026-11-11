"""Measure music recordings the way a score is planned: tempo, key, how busy, how loud where, and how it loops.

    python tools/music_study.py FOLDER -o study.json     # every audio file under FOLDER, one row each

Numbers only, for studying references: recordings stay out of the repository (keep them under private/).
Every measure is a plain DSP estimate. Tempo can be off by a factor of 2 or 3/2 and key by a relative or a fifth:
`pulse` and `key_margin` say how far to trust each.
"""
import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile
from scipy.ndimage import median_filter, uniform_filter1d
from scipy.signal import find_peaks, resample_poly, stft

SR, WIN, HOP = 22_050, 2048, 512
FPS = SR / HOP
NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])   # Krumhansl-Kessler
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def db(x):
    return 10 * np.log10(np.maximum(x, 1e-12))


def tempo(flux):
    """BPM from the autocorrelation of the onset envelope, 60-200, weighted towards 110; and how clear the pulse is."""
    x = flux - uniform_filter1d(flux, int(FPS))
    spec = np.abs(np.fft.rfft(x, 2 * len(x))) ** 2
    ac = np.fft.irfft(spec)[: len(x)]
    ac /= ac[0] + 1e-12
    lags = np.arange(int(FPS * 60 / 200), int(FPS * 60 / 60))
    bpm = 60 * FPS / lags
    score = ac[lags] * np.exp(-0.5 * (np.log2(bpm / 110) / 0.9) ** 2)
    best = lags[np.argmax(score)]
    fine = float(best)
    for k in (2, 4, 8):   # a frame is too coarse a ruler for one beat: read the same pulse 2, 4 and 8 beats on
        centre = int(round(fine * k))
        if centre + 3 < len(ac):
            fine = (centre - 2 + int(np.argmax(ac[centre - 2 : centre + 3]))) / k
    return round(60 * FPS / fine, 1), round(float(ac[best]), 2)


def key(chroma):
    mean = chroma.mean(axis=1)
    scores = {f"{NAMES[k]}{mode}": float(np.corrcoef(np.roll(profile, k), mean)[0, 1])
              for k in range(12) for mode, profile in (("", MAJOR), ("m", MINOR))}
    first, second = sorted(scores, key=scores.get, reverse=True)[:2]
    return first, round(scores[first] - scores[second], 2)


def loop_seconds(chroma, flux):
    """The lag (15 s to 60 % of the track) at which the music best matches itself: a game cue played twice."""
    feat = np.vstack([chroma / (np.linalg.norm(chroma, axis=0) + 1e-9), flux / (flux.max() + 1e-9)])
    step = max(int(FPS / 4), 1)
    feat = feat[:, : feat.shape[1] // step * step].reshape(13, -1, step).mean(axis=2)
    feat -= feat.mean(axis=1, keepdims=True)
    n = feat.shape[1]
    lo, hi = int(15 * FPS / step), int(0.6 * n)
    if hi <= lo + 4:
        return None, 0.0
    sim = np.array([np.sum(feat[:, :-lag] * feat[:, lag:]) / (np.linalg.norm(feat[:, :-lag]) *
                                                              np.linalg.norm(feat[:, lag:]) + 1e-9)
                    for lag in range(lo, hi)])
    best = int(np.argmax(sim))
    return round((lo + best) * step / FPS, 1), round(float(sim[best]), 2)


def measure(path):
    audio, sr = soundfile.read(path, dtype="float32", always_2d=True)
    mid, side = audio.mean(axis=1), (audio[:, 0] - audio[:, -1]) / 2
    x = resample_poly(mid, SR, sr) if sr != SR else mid
    freqs, _, z = stft(x, SR, nperseg=WIN, noverlap=WIN - HOP, boundary=None)
    mag = np.abs(z)
    power = mag ** 2
    flux = np.maximum(np.diff(np.log1p(100 * mag), axis=1), 0).sum(axis=0)
    peaks, _ = find_peaks(flux, height=np.median(flux) + flux.std(), distance=int(0.06 * FPS))
    pitched = (freqs > 55) & (freqs < 2000)
    pitch_class = np.round(12 * np.log2(freqs[pitched] / 440) + 9).astype(int) % 12
    chroma = np.stack([power[pitched][pitch_class == k].sum(axis=0) for k in range(12)])
    # harmonic/percussive: what is steady along time against what is broad along frequency (median filters)
    small = mag[:, ::2]
    steady, broad = median_filter(small, (1, 9)), median_filter(small, (17, 1))
    percussive = float(np.sum(small ** 2 * (broad > steady)) / (np.sum(small ** 2) + 1e-12))
    level = db(uniform_filter1d(x ** 2, 4 * SR)[2 * SR :: 2 * SR])          # 4 s windows, every 2 s
    level = level[level > level.max() - 50]
    total = power.sum()
    bpm, pulse = tempo(flux)
    name, margin = key(chroma)
    loop, alike = loop_seconds(chroma[:, 1:], flux)
    return {
        "track": Path(path).stem, "seconds": round(len(mid) / sr, 1), "bpm": bpm, "pulse": pulse,
        "key": name, "key_margin": margin, "onsets_per_s": round(len(peaks) / (len(x) / SR), 2),
        "rms_db": round(float(db(np.mean(x ** 2))), 1),
        "level_range_db": round(float(np.percentile(level, 95) - np.percentile(level, 10)), 1),
        "opening_db": round(float(level[0] - np.median(level)), 1),
        "low_share": round(float(power[freqs < 200].sum() / total), 2),
        "high_share": round(float(power[freqs > 2000].sum() / total), 3),
        "centroid_hz": round(float((freqs[:, None] * power).sum() / total)),
        "percussive_share": round(percussive, 2),
        "side_db": round(float(db(np.mean(side ** 2)) - db(np.mean(mid ** 2))), 1),
        "loop_s": loop, "loop_alike": alike,
        "loop_bars_4": round(loop * bpm / 240, 1) if loop else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--jobs", type=int, default=6)
    args = parser.parse_args()
    files = sorted(str(p) for p in args.folder.rglob("*") if p.suffix.lower() in (".flac", ".wav", ".ogg", ".mp3"))
    with ProcessPoolExecutor(args.jobs) as pool:
        rows = list(pool.map(measure, files))
    if args.output:
        args.output.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))


def demo():
    """A 120 bpm click under Am, Dm, E, Am, 4 s each, played twice: tempo, key and the 16 s loop come back."""
    t = np.arange(32 * SR) / SR
    chords = ((220, 261.63, 329.63), (293.66, 349.23, 440), (329.63, 415.3, 493.88), (220, 261.63, 329.63))
    x = sum(np.sin(2 * np.pi * np.array(chords)[(t // 4).astype(int) % 4, i] * t) for i in range(3)) * 0.3
    x[(t % 0.5) < 0.01] += 1.0
    soundfile.write("demo.wav", x.astype("float32") / 4, SR)
    row = measure("demo.wav")
    Path("demo.wav").unlink()
    assert abs(row["bpm"] - 120) < 2 and row["key"] == "Am" and abs(row["loop_s"] - 16) <= 0.5, row


if __name__ == "__main__":
    demo() if sys.argv[1:] == ["demo"] else main()
