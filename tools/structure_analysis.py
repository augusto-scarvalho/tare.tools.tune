"""Compare the formant voices with a natural teacher (Kokoro) frame by frame, and judge naturalness.

    pip install -e ".[neural]" pyworld
    python tools/teacher_calibration.py render      # teacher/corpus.{npz,json}: the teacher speaking pt-BR
    python tools/structure_analysis.py compare      # spectral distance + spectra per phone class (DTW-aligned)
    python tools/structure_analysis.py mos          # predicted naturalness (UTMOS 1..5): teacher vs ours
    python tools/structure_analysis.py transplant   # which part of our speech costs naturalness (WORLD + UTMOS)
    python tools/structure_analysis.py formants     # analysis-by-synthesis of vowel formant targets

Try a change without editing the code: --set klatt.FRIC_GAIN=2 --set phonetics.FORMANT_MS=20 --speaker tilt=4000.
Held-out sentences are every third one (1, 4, 7...); `formants` trains on the others. UTMOS
(VoiceMOS 2022 strong learner, MIT) comes from the Hugging Face hub: Blinorot/UTMOS-PyTorch.
"""
import argparse
import json
import sys
from collections import defaultdict
from functools import cache
from math import gcd
from pathlib import Path

import numpy as np
from scipy.fft import dct
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
from creaturesynth.speech import Speaker, g2p_pt, klatt, phonetics  # noqa: E402
from creaturesynth.speech.phonetics import PHONES, segments  # noqa: E402

SR, HOP, WIN, NFFT = 24_000, 240, 600, 1024          # teacher rate; 10 ms hop, 25 ms window
VOICES = {"pm_alex": (133.0, 1.0), "pf_dora": (178.0, 1.17)}  # teacher median f0 -> our pitch, tract
BANDS = [(60, 300), (300, 800), (800, 1500), (1500, 2500), (2500, 3500), (3500, 5000), (5000, 7000), (7000, 10000)]


# --- corpus and features ---------------------------------------------------------------------------------------

def corpus(path="teacher/corpus", held_out=True):
    items = json.loads(Path(f"{path}.json").read_text())
    audio = np.load(f"{path}.npz")
    keep = []
    for m in items:
        if (int(m["key"].split("/")[1]) % 3 == 1) == held_out:
            m["audio"] = audio[m["key"].replace("/", "__")].astype(np.float64)
            keep.append(m)
    return keep


def ours(m, speaker_changes):
    pitch, tract = VOICES[m["voice"]]
    return Speaker(pitch=pitch, tract=tract).but(**speaker_changes).render(m["text"], "pt", SR).astype(np.float64)


def _mel_bank(n_mels=48, fmin=60, fmax=10_000):
    def mel(f):
        return 2595 * np.log10(1 + f / 700)
    pts = 700 * (10 ** (np.linspace(mel(fmin), mel(fmax), n_mels + 2) / 2595) - 1)
    f = np.fft.rfftfreq(NFFT, 1 / SR)
    bank = np.array([np.clip(np.minimum((f - lo) / (c - lo), (hi - f) / (hi - c)), 0, None)
                     for lo, c, hi in zip(pts, pts[1:], pts[2:], strict=False)])
    return bank, pts[1:-1]


BANK, MEL_HZ = _mel_bank()


def logmel(y):
    y = y / (np.sqrt(np.mean(y ** 2)) + 1e-12) * 0.1
    n = 1 + max(len(y) - WIN, 0) // HOP
    frames = np.pad(y, (0, WIN))[np.arange(WIN)[None, :] + HOP * np.arange(n)[:, None]] * np.hanning(WIN)
    return 10 * np.log10(np.abs(np.fft.rfft(frames, NFFT)) ** 2 @ BANK.T + 1e-10)


def active(lm, floor=45):
    e = 10 * np.log10(np.mean(10 ** (lm / 10), axis=1) + 1e-12)
    return np.flatnonzero(e > e.max() - floor)


def mfcc(lm, n=20):
    c = dct(lm, type=2, norm="ortho", axis=1)[:, 1:n + 1]
    return c - c.mean(axis=0)


def dtw(a, b):
    """Alignment path between frame sequences and its length-normalised cost."""
    cost = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1))
    n, m = cost.shape
    D = np.full((n + 1, m + 1), np.inf)
    D[0, 0] = 0
    for i in range(1, n + 1):
        row, c, prev = np.minimum(D[i - 1, :-1], D[i - 1, 1:]) + cost[i - 1], cost[i - 1], np.inf
        for j in range(m):
            prev = min(row[j], prev + c[j])
            D[i, j + 1] = prev
    i, j, path = n, m, []
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        k = np.argmin([D[i - 1, j - 1], D[i - 1, j], D[i, j - 1]])
        i, j = (i - 1, j - 1) if k == 0 else (i - 1, j) if k == 1 else (i, j - 1)
    return path[::-1], D[n, m] / (n + m)


def phone_class(seg):
    kind = PHONES[seg.phone].kind if seg.phone in PHONES else "_"
    if kind in ("vowel", "nasal"):
        return kind
    if kind in ("glide", "liquid", "tap"):
        return "sonorant"
    if kind == "fric" or seg.phone == "R":
        return "fricative" if seg.av == 0 else "voiced fricative"
    if kind in ("stop", "affricate"):
        return "burst" if seg.af > 0 else "closure"
    return "aspiration" if kind == "h" else None


def frame_classes(text, n_frames):
    segs, _ = segments(g2p_pt.text_to_phrases(text), "pt")
    starts = np.cumsum([0] + [s.dur for s in segs])
    centres = (np.arange(n_frames) * HOP + WIN / 2) / SR
    idx = np.clip(np.searchsorted(starts, centres, side="right") - 1, 0, len(segs) - 1)
    labels = [phone_class(s) for s in segs]
    return [labels[i] for i in idx]


# --- commands ----------------------------------------------------------------------------------------------------

def compare(items, spk):
    """DTW-MFCC distance, and each phone class's spectrum minus the teacher's, in dB per band (vowel-referenced)."""
    dist, per = [], defaultdict(lambda: ([], []))
    ref = (MEL_HZ >= 300) & (MEL_HZ < 3000)
    for m in items:
        lo, lk = logmel(ours(m, spk)), logmel(m["audio"])
        io, ik = active(lo), active(lk)
        path, d = dtw(mfcc(lo[io]), mfcc(lk[ik]))
        dist.append(d)
        lab = frame_classes(m["text"], len(lo))
        vow = [(a, b) for a, b in path if lab[io[a]] == "vowel"]
        ro = 10 * np.log10(np.mean(10 ** (lo[io[[a for a, _ in vow]]][:, ref] / 10)))
        rk = 10 * np.log10(np.mean(10 ** (lk[ik[[b for _, b in vow]]][:, ref] / 10)))
        for a, b in path:
            if lab[io[a]]:
                per[lab[io[a]]][0].append(lo[io[a]] - ro)
                per[lab[io[a]]][1].append(lk[ik[b]] - rk)
    print(f"spectral distance (DTW, mel-cepstrum): {np.mean(dist):.2f}")
    print(f"{'ours - teacher, dB':18s}" + "".join(f"{f'{a}-{b}':>11s}" for a, b in BANDS))
    for c, (o, k) in sorted(per.items(), key=lambda kv: -len(kv[1][0])):
        diff = np.mean(o, 0) - np.mean(k, 0)
        print(f"{c:18s}" + "".join(f"{np.mean(diff[(MEL_HZ >= a) & (MEL_HZ < b)]):11.1f}" for a, b in BANDS))


@cache
def _utmos():
    import torch
    from huggingface_hub import hf_hub_download
    return torch.jit.load(hf_hub_download("Blinorot/UTMOS-PyTorch", "utmos_scripted.pt"), map_location="cpu").eval()


def utmos(y, sr=SR):
    import torch
    g = gcd(sr, 16_000)
    y = resample_poly(np.asarray(y, np.float64), 16_000 // g, sr // g)
    x = torch.from_numpy((y / (np.abs(y).max() + 1e-12) * 0.9).astype(np.float32)).unsqueeze(0)
    with torch.no_grad():
        return float(_utmos()(x).squeeze())


def mos(items, spk):
    for v in VOICES:
        sel = [m for m in items if m["voice"] == v]
        t, o = np.mean([utmos(m["audio"]) for m in sel]), np.mean([utmos(ours(m, spk)) for m in sel])
        print(f"{v}: teacher {t:.2f}   ours {o:.2f}   ({len(sel)} sentences)")


def transplant(items, spk, n=8):
    """Vocode the teacher with WORLD and swap in one of our components (DTW-aligned) at a time."""
    import pyworld as pw

    def world(y):
        f0, t = pw.harvest(np.ascontiguousarray(y), SR, frame_period=5.0, f0_floor=60, f0_ceil=500)
        return f0, pw.cheaptrick(y, f0, t, SR), pw.d4c(y, f0, t, SR)

    def mcep(sp):
        c = pw.code_spectral_envelope(sp, SR, 25)[:, 1:]
        return c - c.mean(0)

    def syn(f0, sp, ap):
        return pw.synthesize(*(np.ascontiguousarray(a) for a in (f0, sp, ap)), SR, 5.0)

    res = defaultdict(list)
    for v in VOICES:
        for m in [m for m in items if m["voice"] == v][:n]:
            mine = ours(m, spk)
            f0k, spk_, apk = world(m["audio"])
            f0o, spo, apo = world(mine)
            idx = np.zeros(len(f0k), int)            # for each teacher frame, an aligned frame of ours
            for a, b in dtw(mcep(spk_), mcep(spo))[0]:
                idx[a] = b
            voiced = f0o > 0
            filled = np.interp(np.arange(len(f0o)), np.flatnonzero(voiced), f0o[voiced])[idx]
            contour = np.where(f0k > 0, filled * np.median(f0k[f0k > 0]) / np.median(filled[f0k > 0]), 0.0)
            for name, y in {"teacher": m["audio"], "teacher, vocoded": syn(f0k, spk_, apk),
                            "+ our pitch contour": syn(contour, spk_, apk),
                            "+ our spectral envelope": syn(f0k, spo[idx], apk),
                            "+ our aperiodicity": syn(f0k, spk_, apo[idx]),
                            "ours, vocoded": syn(f0o, spo, apo), "ours": mine}.items():
                res[name].append(utmos(y))
    for name, s in res.items():
        print(f"{name:26s} UTMOS {np.mean(s):.2f} ±{np.std(s) / np.sqrt(len(s)):.2f}")


def formants(spk, rounds=3, eta=0.6):
    """Move vowel/glide/liquid targets until the F1-F3 we render match the teacher's on aligned frames.

    The same LPC tracker measures both sides, so its bias cancels, and our coarticulation
    undershoot is part of what gets compensated. Prints the table for phonetics.LANG_PHONES.
    """
    from teacher_calibration import formants as lpc
    train, held = corpus(held_out=False), corpus()
    table, tract = {}, {v: t for v, (_, t) in VOICES.items()}

    def gaps(items):
        r = defaultdict(list)
        for m in items:
            pitch, _ = VOICES[m["voice"]]
            mine = Speaker(pitch=pitch, tract=tract[m["voice"]]).but(**spk).render(m["text"], "pt", SR).astype(float)
            lo, lk = logmel(mine), logmel(m["audio"])
            io, ik = active(lo), active(lk)
            to_k = defaultdict(list)
            for a, b in dtw(mfcc(lo[io]), mfcc(lk[ik]))[0]:
                to_k[io[a]].append(ik[b])
            segs, _ = segments(g2p_pt.text_to_phrases(m["text"]), "pt")
            t = np.cumsum([0] + [s.dur for s in segs])
            for i, s in enumerate(segs):
                p = PHONES.get(s.phone)
                if p is None or p.kind not in ("vowel", "glide", "liquid") or p.nasal or s.dur < 0.05:
                    continue
                a, b = t[i] + 0.3 * s.dur, t[i] + 0.7 * s.dur
                ks = [k for f in range(int(a * SR / HOP), int(b * SR / HOP) + 1) for k in to_k.get(f, [])]
                if not ks:
                    continue
                ka, kb = min(ks) * HOP, (max(ks) + 1) * HOP + WIN      # the teacher frames aligned to our core
                if kb - ka >= 0.04 * SR:
                    fo, fk = lpc(mine[int(a * SR):int(b * SR) + WIN]), lpc(m["audio"][ka:kb])
                    if fo is not None and fk is not None:
                        r[(m["voice"], s.phone)].append(np.log(np.asarray(fk) / np.asarray(fo)))
        out = {k: np.median(v, axis=0) for k, v in r.items() if len(v) >= 3}
        glob = {v: float(np.median(np.concatenate([x for (vv, _), x in out.items() if vv == v]))) for v in VOICES}
        return out, glob, float(np.mean([np.mean(np.abs(x - glob[v])) for (v, _), x in out.items()]))

    for rnd in range(rounds + 1):
        phonetics.LANG_PHONES["pt"] = {p: {"F": tuple(round(f) for f in F)} for p, F in table.items()}
        out, glob, err = gaps(train)
        print(f"round {rnd}: formant gap {err:.3f} (train)  {gaps(held)[2]:.3f} (held-out), log units", flush=True)
        if rnd == rounds:
            break
        for v in tract:                      # the voice's overall scale belongs to the speaker, not the table
            tract[v] *= float(np.exp(glob[v]))
        corr = defaultdict(list)
        for (v, p), x in out.items():
            corr[p].append(x - glob[v])
        for p, cs in corr.items():
            step = np.exp(eta * np.mean(cs, 0))
            table[p] = tuple(f * x for f, x in zip(table.get(p, PHONES[p].F), step, strict=True))
    print(json.dumps({p: {"F": [round(f) for f in F]} for p, F in sorted(table.items())}))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["compare", "mos", "transplant", "formants"])
    ap.add_argument("--set", action="append", default=[], metavar="MODULE.NAME=VALUE",
                    help="override a klatt/phonetics constant for this run")
    ap.add_argument("--speaker", action="append", default=[], metavar="KNOB=VALUE", help="Speaker knob, e.g. tilt=4000")
    a = ap.parse_args()
    for s in a.set:
        name, value = s.split("=", 1)
        mod, attr = name.split(".")
        value = json.loads(value.replace("(", "[").replace(")", "]"))
        setattr({"klatt": klatt, "phonetics": phonetics}[mod], attr, tuple(value) if isinstance(value, list) else value)
    spk = {k: float(v) for k, v in (s.split("=") for s in a.speaker)}
    if a.command == "formants":
        formants(spk)
    else:
        {"compare": compare, "mos": mos, "transplant": transplant}[a.command](corpus(), spk)


if __name__ == "__main__":
    main()
