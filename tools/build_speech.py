"""Build the voice banks of the natural voices (src/tare/tools/tune/speech/data/bank_<lang>_<voice>.npz).

A teacher voice reads a corpus once, here, offline: Kokoro-82M (Apache-2.0), a neural text-to-speech model. Each
recording is analysed with the WORLD vocoder into 5 ms frames (pitch, a 32-band spectral envelope, aperiodicity)
and labelled phone by phone from the teacher's own alignment, mapped to our phone symbols. Only these numbers ship.
In a game nothing neural runs: tare.tools.tune.speech.concat picks pieces of the bank for a new sentence, stretches
them to our timing, lays our intonation on them and our vocoder rebuilds the sound, deterministically.

    pip install kokoro soundfile pyworld          # development only
    python tools/build_speech.py render pt        # the teacher reads the corpus (cached in teacher/)
    python tools/build_speech.py build pt         # analyse -> the banks
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
from corpus_pt import EXTRA_PT, sentences  # noqa: E402
from teacher_calibration import CORPUS  # noqa: E402

from tare.tools.tune.speech.concat import FRAME, fit_durations, fit_intonation, nucleus_features  # noqa: E402
from tare.tools.tune.speech.vocoder import ENV_FLOOR, band_freqs, encode  # noqa: E402

CACHE = ROOT / "teacher"
OUT = ROOT / "src/tare/tools/tune/speech/data"
KOKORO_SR, HOP = 24_000, 600                     # Kokoro: 24 kHz audio, phone durations in 25 ms steps
BANDS = 64                                       # envelope bands: 32 cost 0.25 of predicted naturalness (UTMOS)
LANG_CODES = {"pt": "p", "en": "a"}
# bank name -> (Kokoro voice, the vocal tract we give it)
VOICES = {"pt": {"alex": ("pm_alex", 1.0), "dora": ("pf_dora", 1.15)}}

SENTENCES = {"pt": CORPUS + EXTRA_PT + sentences(760)}


def _fix_espeak_data_path():
    """espeakng-loader 0.2.x ships espeak-ng 1.52, which only honours a data path that also contains an
    `espeak-ng-data` folder (otherwise it looks in its build machine's path)."""
    try:
        import espeakng_loader
        import misaki.espeak  # noqa: F401  (sets the library and the data path it expects)
        from phonemizer.backend.espeak.wrapper import EspeakWrapper
    except ImportError:
        return
    real = espeakng_loader.get_data_path()
    shim = os.path.join(tempfile.gettempdir(), "tare-tools-tune-espeak-ng-data")
    os.makedirs(shim, exist_ok=True)
    for name in os.listdir(real):
        if not os.path.lexists(os.path.join(shim, name)):
            os.symlink(os.path.join(real, name), os.path.join(shim, name))
    if not os.path.lexists(os.path.join(shim, "espeak-ng-data")):
        os.symlink(real, os.path.join(shim, "espeak-ng-data"))
    EspeakWrapper.set_data_path(shim)


def kokoro(lang: str):
    """The teacher (also used by tools/teacher_calibration.py and tools/structure_analysis.py)."""
    _fix_espeak_data_path()
    from kokoro import KPipeline
    return KPipeline(lang_code=LANG_CODES[lang], repo_id="hexgrad/Kokoro-82M")


def render(lang: str):
    """The teacher reads the corpus; sentences already in the cache are kept."""
    pipe = kokoro(lang)
    CACHE.mkdir(exist_ok=True)
    for name, (voice, _tract) in VOICES[lang].items():
        old_items, old_audio = [], {}
        if (CACHE / f"speech_{lang}_{name}.json").exists():
            old_items = json.loads((CACHE / f"speech_{lang}_{name}.json").read_text())
            old_audio = dict(np.load(CACHE / f"speech_{lang}_{name}.npz"))
        cached = {}
        for it in old_items:
            cached.setdefault(it["text"], []).append(it)
        items, audio = [], {}
        for i, text in enumerate(SENTENCES[lang]):
            if text in cached:
                parts = [(it, old_audio[it["key"]]) for it in cached[text]]
            else:
                parts = [({"phonemes": r.phonemes, "dur": [int(d) for d in r.pred_dur.tolist()]},
                          r.audio.numpy().astype(np.float32)) for r in pipe(text, voice=voice)]
            for k, (it, y) in enumerate(parts):
                key = f"{i}__{k}"
                audio[key] = y
                items.append({"key": key, "text": text, "phonemes": it["phonemes"], "dur": it["dur"]})
        np.savez_compressed(CACHE / f"speech_{lang}_{name}.npz", **audio)
        (CACHE / f"speech_{lang}_{name}.json").write_text(json.dumps(items, ensure_ascii=False, indent=1))
        print(f"{lang}/{name}: {len(items)} utterances, {sum(len(a) for a in audio.values()) / KOKORO_SR / 60:.1f} min")


# -- labels: the teacher's tokens (misaki) -> our phone symbols --------------------------------------------------------

PRIMARY, SECONDARY, TILDE = "ˈ", "ˌ", "̃"
PT = {"a": "a", "æ": "6", "ɐ": "6", "e": "e", "ɛ": "E", "i": "i", "o": "o", "ɔ": "O", "u": "u", "ʊ": "U", "ə": "@",
      "y": "I", "ɪ": "I", "p": "p", "b": "b", "t": "t", "d": "d", "k": "k", "ɡ": "g", "f": "f", "v": "v", "s": "s",
      "z": "z", "ʃ": "S", "ʒ": "Z", "ʧ": "tS", "ʤ": "dZ", "m": "m", "n": "n", "ɲ": "J", "ŋ": "N", "l": "l", "ʎ": "L",
      "ɾ": "r", "r": "r", "x": "R", "w": "w", "j": "j"}
DIPHTHONGS = {"A": ("e", "j"), "I": ("a", "j"), "W": ("a", "w"), "O": ("o", "w"), "Y": ("O", "j")}   # misaki
NASAL = {"a": "6~", "6": "6~", "e": "e~", "E": "e~", "i": "i~", "o": "o~", "O": "o~", "u": "u~", "U": "w~", "I": "i~"}
VOWELS = set("a6eEiIoOuU@")


def labels(phonemes: str, dur: list[int], n_frames: int) -> list[tuple]:
    """[(symbol, first frame, end frame, stress, flags)] covering the utterance; flags: 1 word-initial,
    2 word-final; pauses are "_"."""
    edges = np.cumsum([0] + dur) * HOP / KOKORO_SR / FRAME          # token i spans edges[i+1]..edges[i+2]
    toks, i, n, stress, edge = [], 0, len(phonemes), 0, True

    def add(t):
        nonlocal edge
        toks.append(t + [1 if edge else 0])
        edge = False

    def close():
        nonlocal edge
        for t in reversed(toks):
            if t[0] not in (" ", "_"):
                t[4] |= 2
                break
        edge = True

    while i < n:
        ch = phonemes[i]
        if ch in (PRIMARY, SECONDARY):
            stress = 2 if ch == PRIMARY else 1
            i += 1
            continue
        s, e = edges[i + 1], edges[i + 2]
        nasal = i + 1 < n and phonemes[i + 1] == TILDE
        if nasal:
            e = edges[i + 3]
        after_vowel = bool(toks) and not edge and toks[-1][0][0] in VOWELS
        if ch in DIPHTHONGS:
            v, g = DIPHTHONGS[ch]
            if nasal:
                v, g = NASAL.get(v, v), g + "~"
            add([v, s, (s + e) / 2, stress])
            add([g, (s + e) / 2, e, 0])
        elif ch in PT:
            sym = PT[ch]
            if nasal and sym in VOWELS:
                sym = NASAL.get(sym, sym)
            if sym in VOWELS and i + 1 < n and phonemes[i + 1] == "ŋ":   # "oŋ": a nasal vowel before the coda
                sym = NASAL.get(sym, sym)
            if ch in ("y", "ɪ") and after_vowel:                       # offglides: noite [nojtSi], caiu [kaiw]
                sym = "j"
            if ch == "ʊ" and after_vowel:
                sym = "w~" if nasal else "w"
            add([sym, s, e, stress if sym[0] in VOWELS else 0])
        elif ch in " ,.!?;:":
            close()
            toks.append([" " if ch == " " else "_", s, e, 0, 0])
        stress = 0
        i += 2 if nasal else 1
    close()
    res = []                                   # a space is shared by its neighbours, unless long (a pause)
    for k, t in enumerate(toks):
        if t[0] == " ":
            if t[2] - t[1] > 16 and 0 < k < len(toks) - 1:
                res.append(["_", t[1], t[2], 0, 0])
            else:
                mid = (t[1] + t[2]) / 2
                if res:
                    res[-1][2] = mid
                if k + 1 < len(toks):
                    toks[k + 1][1] = mid
            continue
        res.append(t)
    clean = []
    for t in res:
        if clean and t[0] == "_" and clean[-1][0] == "_":
            clean[-1][2] = t[2]
            continue
        if clean and t[1] > clean[-1][2]:
            if t[1] - clean[-1][2] > 16 and clean[-1][0] != "_" and t[0] != "_":
                clean.append(["_", clean[-1][2], t[1], 0, 0])
            else:
                mid = (clean[-1][2] + t[1]) / 2
                clean[-1][2] = t[1] = mid
        clean.append(t)
    if clean[0][0] != "_" and clean[0][1] > 1:
        clean.insert(0, ["_", 0, clean[0][1], 0, 0])
    if clean[-1][0] != "_":
        clean.append(["_", clean[-1][2], n_frames, 0, 0])
    clean[-1][2] = n_frames
    clean[0][1] = 0
    out = [(t[0], int(round(t[1])), int(round(t[2])), t[3], t[4]) for t in clean]
    return [t for t in out if t[2] > t[1]]


def realign(lab, env, search=range(-20, 5)):
    """The teacher's sound runs ahead of its own duration grid (by ~60 ms, measured over the corpus): shift the
    labels by what makes fricatives hiss and vowels outshine stop closures most, then refine each boundary."""
    bf = band_freqs(env.shape[1])
    hiss = env[:, (bf > 4000) & (bf < 11000)].mean(1) - env[:, bf < 1200].mean(1)
    level = env[:, (bf > 200) & (bf < 4000)].mean(1)
    n = len(env)

    def score(d):
        fr, stop, vow = [], [], []
        for sym, a, e, *_ in lab:
            a, e = min(max(a + d, 0), n), min(max(e + d, 0), n)
            if e <= a:
                continue
            if sym in ("s", "S", "f", "z"):
                fr.append(hiss[a:e].mean())
            elif sym in ("p", "t", "k", "b", "d", "g"):
                stop.append(level[a:e].mean())
            elif sym in ("a", "e", "E", "i", "o", "O", "u"):
                vow.append(level[a:e].mean())
        return (np.mean(fr) if fr else 0.0) + (np.mean(vow) - np.mean(stop) if stop and vow else 0.0)

    d = max(search, key=score)
    out = [[sym, min(max(a + d, 0), n), min(max(e + d, 0), n), *rest] for sym, a, e, *rest in lab]
    out[0][1], out[-1][2] = 0, n
    return [tuple(x) for x in out if x[2] > x[1]], d


def refine(lab, env, f0, reach=3):
    """Move each boundary (the teacher's 25 ms grid) to the biggest spectral change within +-reach frames."""
    lab = [list(x) for x in lab]
    change = (np.abs(np.diff(env, axis=0)).mean(1) + 0.5 * np.abs(np.diff(env.mean(1)))
              + 3.0 * np.abs(np.diff((f0 > 0).astype(float))))
    for k in range(1, len(lab)):
        b = lab[k][1]
        lo, hi = max(lab[k - 1][1] + 1, b - reach), min(lab[k][2] - 1, b + reach)
        if hi <= lo or lo < 1:
            continue
        lab[k - 1][2] = lab[k][1] = lo + int(np.argmax(change[lo - 1:hi]))
    return [tuple(x) for x in lab]


def build(lang: str):
    import pyworld as pw
    for name, (voice, tract) in VOICES[lang].items():
        items = json.loads((CACHE / f"speech_{lang}_{name}.json").read_text())
        audio = np.load(CACHE / f"speech_{lang}_{name}.npz")
        f0s, envs, aps, phones, base, shifts = [], [], [], [], 0, []
        for u, it in enumerate(items):
            x = audio[it["key"]].astype(np.float64)
            f0, t = pw.harvest(x, KOKORO_SR, f0_floor=60, f0_ceil=600, frame_period=FRAME * 1000)
            f, env, ap = encode(f0, pw.cheaptrick(x, f0, t, KOKORO_SR), pw.d4c(x, f0, t, KOKORO_SR), KOKORO_SR,
                                BANDS)
            lab, shift = realign(labels(it["phonemes"], it["dur"], len(f)), env)
            shifts.append(shift)
            for sym, a, b, st, flags in refine(lab, env, f):
                phones.append([sym, base + a, base + min(b, len(f)), st, u, flags])
            f0s.append(f)
            envs.append(env)
            aps.append(ap)
            base += len(f)
        voiced = np.concatenate(f0s)
        model = fit_durations(phones)
        meta = {"lang": lang, "name": name, "teacher": f"Kokoro-82M {voice} (Apache-2.0)", "tract": tract,
                "pitch": round(float(np.median(voiced[voiced > 0])), 1), "env_delta": True}
        (OUT / f"bank_{lang}_{name}.json").write_text(json.dumps(
            {"durations": model, "intonation": intonation(lang, items, phones, voiced)}))
        env = np.clip(np.round((np.concatenate(envs) - ENV_FLOOR) * 2), 0, 255).astype(np.uint8)
        env = np.diff(env, axis=0, prepend=np.zeros((1, env.shape[1]), np.uint8))   # frame-to-frame, mod 256
        out = OUT / f"bank_{lang}_{name}.npz"
        np.savez_compressed(out, f0=voiced.astype(np.float16), env=env,
                            ap=np.round(np.concatenate(aps) * 255).astype(np.uint8),
                            phones=np.frombuffer(json.dumps(phones).encode(), dtype=np.uint8),
                            meta=np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8))
        print(f"{lang}/{name}: labels moved {np.median(shifts) * FRAME * 1000:.0f} ms (median), "
              f"{len(phones)} phones, {base * FRAME / 60:.1f} min, duration model r = {model['fit'][0]}, "
              f"-> {out} ({out.stat().st_size / 1e6:.1f} MB)")


def intonation(lang: str, items: list[dict], phones: list, f0: np.ndarray) -> dict:
    """The teacher's pitch at the start and end of each vowel (relative to its sentence's median), by phrase position,
    stress and phrase kind (from our own front-end; sentences split in chunks or phrased differently are left out)."""
    from tare.tools.tune.speech import LANGS
    by_utt: dict[int, list] = {}
    for p in phones:
        by_utt.setdefault(p[4], []).append(p)
    rows, targets = [], []
    for u, it in enumerate(items):
        ph = by_utt.get(u)
        alone = it["key"].endswith("__0") and not (u + 1 < len(items) and items[u + 1]["text"] == it["text"])
        if not ph or not alone:
            continue
        seq = [(p[0], p[3], p[5]) for p in ph]
        kinds = [(p.kind, p.wh) for p in LANGS[lang].text_to_phrases(it["text"])]
        if 1 + sum(s == "_" for s, *_ in seq[1:-1]) != len(kinds):
            continue
        voiced = f0[ph[0][1]:ph[-1][2]]
        median = np.log2(np.median(voiced[voiced > 0]))
        feats, where = nucleus_features(seq, kinds)
        for r, i in zip(feats, where, strict=True):
            fr = f0[ph[i][1]:ph[i][2]]
            third = max(len(fr) // 3, 1)
            first, last = fr[:third], fr[-third:]
            if (first > 0).any() and (last > 0).any():
                rows.append(r)
                targets.append((np.log2(np.median(first[first > 0])) - median,
                                np.log2(np.median(last[last > 0])) - median))
    return fit_intonation(rows, np.array(targets))


def fit(lang: str):
    """Refit the duration and intonation models of the banks (bank_<lang>_<voice>.json, next to the frames), without
    analysing the recordings again or rewriting the banks."""
    for name in VOICES[lang]:
        d = np.load(OUT / f"bank_{lang}_{name}.npz")
        phones = json.loads(bytes(d["phones"]).decode())
        items = json.loads((CACHE / f"speech_{lang}_{name}.json").read_text())
        models = {"durations": fit_durations(phones),
                  "intonation": intonation(lang, items, phones, d["f0"].astype(np.float64))}
        (OUT / f"bank_{lang}_{name}.json").write_text(json.dumps(models))
        print(f"{lang}/{name}: duration model r = {models['durations']['fit'][0]}, "
              f"intonation r = {models['intonation']['fit']}")


if __name__ == "__main__":
    cmd, lang = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "pt"
    {"render": render, "build": build, "fit": fit}[cmd](lang)
