"""EXPERIMENTAL, still being built: intonation learned from real Brazilian Portuguese speech (real/prosody_pt.json).

The voice banks' teacher (Kokoro) reads well but does not intone like a Brazilian: its yes/no questions fall like
statements and its statements end far too low. Here the intonation model is fitted on real people instead, from two
open corpora downloaded here once (analysis only: no recording, and no number that could rebuild one, ships).
It predicts real people's pitch better (2.8 semitones of error against 3.5), but by ear its questions fade (an
average of many readers' rises is a small rise) and the banks' pieces, recorded with the teacher's melody, bend less
well to it; so it is not shipped. To hear it: TARE_TOOLS_TUNE_PROSODY=real python ...

    TTS-Portuguese Corpus (Casanova et al. 2022; CC BY 4.0): one Brazilian man, 10.5 h of read sentences
    CML-TTS (Oliveira et al. 2023; CC BY 4.0), Portuguese part: LibriVox audiobooks. Kept: the utterances with
        questions, exclamations or trailing dots, and 5% of the rest, from the readers who sound Brazilian.

Every sentence goes through our own front-end (the phones the engine would say); the Montreal Forced Aligner (a
classical HMM aligner, offline) places them on the recording; WORLD (dio) gives the pitch; the model is fitted to
the pitch at the start and the end of every syllable nucleus, relative to its sentence's median, as for the banks.

    conda install -c conda-forge montreal-forced-aligner   # development only (its Portuguese model is fetched here)
    pip install soundfile pyworld pyarrow
    python tools/real_prosody.py fetch       # the corpora, at 16 kHz, in real/ (about 3 GB)
    python tools/real_prosody.py align       # our transcription aligned by MFA, and the pitch
    python tools/real_prosody.py fit         # -> real/prosody_pt.json, checked on held-out sentences
"""
import collections
import glob
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import unicodedata
import zipfile
from multiprocessing import Pool
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from tare.tools.tune.speech import g2p_pt  # noqa: E402
from tare.tools.tune.speech.concat import NUCLEI, bank, fit_intonation, nucleus_features, sequence, tunes  # noqa: E402

CACHE = ROOT / "real"
OUT = ROOT / "real/prosody_pt.json"   # not shipped (see above)
TTS_PT = "https://www.dropbox.com/s/ohpc7epowv9ct7o/TTS-Portuguese-Corpus.zip?dl=1"
CML = "https://huggingface.co/datasets/ylacombe/cml-tts/resolve/main/"
MFA_MODELS = "https://github.com/MontrealCorpusTools/mfa-models/releases/download/"
MFA_ACOUSTIC = MFA_MODELS + "acoustic-portuguese_mfa-v2.0.0a/portuguese_mfa.zip"   # CC BY 4.0
FRAME = 0.005
# our phones -> the MFA Portuguese model's (decomposed, as MFA writes them); [ŋ] and the tap's schwa it has not
TO_MFA = {k: v and unicodedata.normalize("NFD", v) for k, v in {
    "a": "a", "6": "ɐ", "e": "e", "E": "ɛ", "i": "i", "I": "i", "o": "o", "O": "ɔ", "u": "u", "U": "u",
    "6~": "ɐ̃", "e~": "ẽ", "i~": "ĩ", "o~": "õ", "u~": "ũ", "w~": "w̃", "j~": "j̃", "j": "j", "w": "w",
    "p": "p", "b": "b", "t": "t", "d": "d", "k": "k", "g": "ɡ", "f": "f", "v": "v", "s": "s", "z": "z",
    "S": "ʃ", "Z": "ʒ", "tS": "tʃ", "dZ": "dʒ", "m": "m", "n": "n", "J": "ɲ", "l": "l", "L": "ʎ", "r": "ɾ",
    "R": "x", "N": None, "@": None}.items()}
MFA_DICTS = {"br": MFA_MODELS + "dictionary-portuguese_brazil_mfa-v2.0.0a/portuguese_brazil_mfa.dict",
             "pt": MFA_MODELS + "dictionary-portuguese_portugal_mfa-v2.0.0a/portuguese_portugal_mfa.dict"}


# -- fetch ------------------------------------------------------------------------------------------------------------

def _write16(path: Path, x: np.ndarray, sr: int):
    import soundfile as sf
    from scipy.signal import resample_poly
    if x.ndim > 1:
        x = x.mean(1)
    g = np.gcd(16000, sr)
    sf.write(path, np.clip(resample_poly(x, 16000 // g, sr // g), -1, 1), 16000, subtype="PCM_16")


def fetch():
    import pyarrow.parquet as pq
    import soundfile as sf
    (CACHE / "tts/wav").mkdir(parents=True, exist_ok=True)
    zpath = CACHE / "tts.zip"
    if not zpath.exists():
        subprocess.run(["curl", "-sSL", "--retry", "4", "-o", str(zpath), TTS_PT], check=True)
    with zipfile.ZipFile(zpath) as z:
        rows = [line.split("==") for line in z.read("TTS-Portuguese-Corpus/texts.csv").decode().splitlines()]
        count = collections.Counter(r[0] for r in rows)        # a few files are listed twice, with different texts
        meta = []
        for r in rows:
            if len(r) < 2 or count[r[0]] > 1:
                continue
            key = Path(r[0]).stem
            if not (CACHE / f"tts/wav/{key}.wav").exists():
                x, sr = sf.read(io.BytesIO(z.read("TTS-Portuguese-Corpus/" + r[0])), dtype="float32")
                _write16(CACHE / f"tts/wav/{key}.wav", x, sr)
            meta.append({"key": key, "text": r[-1].strip(), "speaker": "tts"})
    (CACHE / "tts/meta.json").write_text(json.dumps(meta, ensure_ascii=False))
    zpath.unlink()

    (CACHE / "cml/wav").mkdir(parents=True, exist_ok=True)
    tree = "https://huggingface.co/api/datasets/ylacombe/cml-tts/tree/main/portuguese"
    listing = subprocess.run(["curl", "-sS", tree], capture_output=True, check=True).stdout
    shards = [x["path"] for x in json.loads(listing) if x["path"].endswith(".parquet")]
    meta, rnd = [], random.Random(7)
    for name in shards:
        path = CACHE / "shard.parquet"
        subprocess.run(["curl", "-sSL", "--retry", "4", "-o", str(path), CML + name], check=True)
        for batch in pq.ParquetFile(path).iter_batches(batch_size=64, columns=["audio", "text", "speaker_id"]):
            for a, text, spk in zip(*(batch.column(c).to_pylist() for c in ("audio", "text", "speaker_id")),
                                    strict=True):
                marked = bool(text) and (any(c in text for c in "?!…") or "..." in text)
                if not text or (not marked and rnd.random() > 0.05):
                    continue
                key = Path(a["path"]).stem
                x, sr = sf.read(io.BytesIO(a["bytes"]), dtype="float32")
                _write16(CACHE / f"cml/wav/{key}.wav", x, sr)
                meta.append({"key": key, "text": text, "speaker": str(spk)})
        path.unlink()
        print(name, len(meta), flush=True)
    (CACHE / "cml/meta.json").write_text(json.dumps(meta, ensure_ascii=False))


# -- align ------------------------------------------------------------------------------------------------------------

def words_of(seq) -> list[list[int]]:
    """The phones of each word of a sequence [[symbol, duration, stress, flags]] (pauses left out)."""
    out, cur = [], []
    for i, (sym, _d, _st, fl) in enumerate(seq):
        if sym == "_" or (fl & 1 and cur):
            if cur:
                out.append(cur)
            cur = []
        if sym == "_":
            continue
        cur.append(i)
        if fl & 2:
            out.append(cur)
            cur = []
    return out + ([cur] if cur else [])


def prepare(corpus: str):
    """MFA input over OUR transcription: every word occurrence is its own dictionary entry, so each aligned vowel
    is one of the nuclei the intonation model speaks of."""
    base = CACHE / corpus
    shutil.rmtree(base / "mfa", ignore_errors=True)
    lexicon, items = [], {}
    for m in json.loads((base / "meta.json").read_text()):
        try:
            phrases = g2p_pt.text_to_phrases(m["text"])
            seq = sequence(phrases, "pt")[2]
        except (ValueError, KeyError, IndexError):
            continue
        tokens = []
        for k, idx in enumerate(words_of(seq)):
            phones = [TO_MFA[seq[i][0]] for i in idx if TO_MFA.get(seq[i][0])]
            if phones:
                tokens.append(re.sub(r"[^a-z0-9]", "", f"{m['key']}x{k}".lower()))
                lexicon.append(f"{tokens[-1]}\t{' '.join(phones)}")
        folder = base / "mfa/corpus" / m["speaker"]
        folder.mkdir(parents=True, exist_ok=True)
        os.symlink(base / f"wav/{m['key']}.wav", folder / f"{m['key']}.wav")
        (folder / f"{m['key']}.lab").write_text(" ".join(tokens))
        items[m["key"]] = {"text": m["text"], "speaker": m["speaker"], "seq": [[s[0], s[2], s[3]] for s in seq],
                           "kinds": [[p.kind, p.wh] for p in phrases]}
    (base / "mfa/dict.txt").write_text("\n".join(lexicon) + "\n")
    (base / "items.json").write_text(json.dumps(items, ensure_ascii=False))


def _pitch(path):
    import pyworld as pw
    import soundfile as sf
    x, sr = sf.read(path, dtype="float64")
    f0, t = pw.dio(x, sr, f0_floor=60, f0_ceil=700, frame_period=FRAME * 1000)
    f0 = pw.stonemask(x, f0, t, sr)
    if (f0 > 0).sum() > 10:                  # octave slips: outside 0.55..1.8 x the sentence's median is no voice
        m = np.median(f0[f0 > 0])
        f0[(f0 < 0.55 * m) | (f0 > 1.8 * m)] = 0.0
    return Path(path).stem, f0.astype(np.float32)


def _mfa(corpus: Path, dictionary: Path, out: Path, root: Path, *extra: str):
    model = CACHE / "portuguese_mfa.zip"
    if not model.exists():
        subprocess.run(["curl", "-sSL", "--retry", "4", "-o", str(model), MFA_ACOUSTIC], check=True)
    subprocess.run([os.environ.get("MFA", "mfa"), "align", str(corpus), str(dictionary), str(model), str(out),
                    "--clean", "-j", str(os.cpu_count() or 2), "--beam", "100", "--retry_beam", "400", "--use_mp",
                    *extra], check=True, env={**os.environ, "MFA_ROOT_DIR": str(root)})


def _goodness(root: Path) -> dict[str, tuple[str, float]]:
    """file -> (speaker, the mean log-likelihood of its phones) from an MFA run's database."""
    import csv
    import sqlite3
    con = sqlite3.connect(next(root.glob("corpus/*.db")))
    who = {u: (f, s) for u, f, s in con.execute("select u.id, f.name, s.name from utterance u "
                                                "join file f on u.file_id=f.id join speaker s on u.speaker_id=s.id")}
    total, length = collections.Counter(), collections.Counter()
    for r in csv.DictReader(open(root / "corpus/alignment/phone_intervals.csv")):
        if r["phone_goodness"]:
            d = float(r["end"]) - float(r["begin"])
            total[int(r["utterance_id"])] += float(r["phone_goodness"]) * d
            length[int(r["utterance_id"])] += d
    return {who[u][0]: (who[u][1], total[u] / length[u]) for u in total if length[u] > 0}


def dialect():
    """Brazilian or from Portugal? 30 utterances of every reader aligned twice, with MFA's Brazilian and European
    pronunciation dictionaries (cut to the words both have): per reader, how much better the Brazilian one fits."""
    base = CACHE / "dialect"
    shutil.rmtree(base, ignore_errors=True)
    rnd, words = random.Random(3), {}
    for name, url in MFA_DICTS.items():
        path = CACHE / f"{name}.dict"
        if not path.exists():
            subprocess.run(["curl", "-sSL", "--retry", "4", "-o", str(path), url], check=True)
        words[name] = {line.split("\t")[0]: line for line in path.read_text().splitlines()}
    common = words["br"].keys() & words["pt"].keys()
    for name in words:
        (base / f"{name}.dict").parent.mkdir(parents=True, exist_ok=True)
        (base / f"{name}.dict").write_text("\n".join(words[name][w] for w in sorted(common)) + "\n")
    for corpus in ("tts", "cml"):
        items = json.loads((CACHE / corpus / "items.json").read_text())
        by = collections.defaultdict(list)
        for k, it in sorted(items.items()):
            by[it["speaker"]].append(k)
        for spk, keys in by.items():
            rnd.shuffle(keys)
            folder = base / "corpus" / f"{corpus}:{spk}".replace(":", "_")
            folder.mkdir(parents=True)
            for k in keys[:30]:
                os.symlink((CACHE / corpus / f"wav/{k}.wav").resolve(), folder / f"{k}.wav")
                (folder / f"{k}.lab").write_text(re.sub(r"[^\w\s'-]", " ", items[k]["text"].lower()))
    fits = {}
    for name in words:
        _mfa(base / "corpus", base / f"{name}.dict", base / f"out_{name}", base / f"root_{name}")
        fits[name] = _goodness(base / f"root_{name}")
    diff = collections.defaultdict(list)
    for f, (spk, g) in fits["br"].items():
        if f in fits["pt"]:
            diff[spk.replace("_", ":", 1)].append(g - fits["pt"][f][1])
    (CACHE / "dialect.json").write_text(json.dumps(
        {s: [float(np.mean(v)), float(np.std(v) / np.sqrt(len(v)))] for s, v in diff.items() if len(v) >= 6}))


def align():
    for corpus in ("tts", "cml"):
        prepare(corpus)
        base = CACHE / corpus
        _mfa(base / "mfa/corpus", base / "mfa/dict.txt", base / "mfa/out", base / "mfa/root",
             *(["--single_speaker"] if corpus == "tts" else []))
        wavs = sorted(glob.glob(str(base / "wav/*.wav")))
        with Pool(os.cpu_count()) as p:
            np.savez_compressed(base / "f0.npz", **dict(p.imap_unordered(_pitch, wavs, chunksize=8)))
    dialect()


# -- fit --------------------------------------------------------------------------------------------------------------

def textgrid(path) -> dict[str, list[tuple[float, float, str]]]:
    tiers, name, xmin, xmax = {}, None, 0.0, 0.0
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line.startswith("name ="):
            name = line.split("=", 1)[1].strip().strip('"')
            tiers[name] = []
        elif line.startswith("xmin ="):
            xmin = float(line.split("=")[1])
        elif line.startswith("xmax ="):
            xmax = float(line.split("=")[1])
        elif line.startswith("text =") and name:
            tiers[name].append((xmin, xmax, line.split("=", 1)[1].strip().strip('"')))
    return tiers


def phone_times(item, tg) -> list | None:
    """(start, end) in seconds of each phone of the item's sequence (None for pauses and phones MFA did not get)."""
    seq = [[s[0], 0, s[1], s[2]] for s in item["seq"]]
    words = [w for w in tg.get("words", []) if w[2]]
    phones = [p for p in tg.get("phones", []) if p[2] and p[2] not in ("sil", "sp", "spn")]
    times, wi = [None] * len(seq), 0
    for k, idx in enumerate(words_of(seq)):
        mapped = [i for i in idx if TO_MFA.get(seq[i][0])]
        if not mapped:
            continue
        if wi >= len(words) or not words[wi][2].endswith(f"x{k}"):
            return None
        a, e, _w = words[wi]
        wi += 1
        inside = [p for p in phones if p[0] >= a - 1e-6 and p[1] <= e + 1e-6]
        if len(inside) != len(mapped):
            return None
        for i, (pa, pe, _p) in zip(mapped, inside, strict=True):
            times[i] = (pa, pe)
    return times


def targets(item, times, f0) -> dict[int, tuple[float, float]]:
    """Pitch at the start and the end (their first and last thirds) of each nucleus, log2 from the sentence's median."""
    spans = [t for t in times if t]
    voiced = f0[int(spans[0][0] / FRAME):int(spans[-1][1] / FRAME)]
    voiced = voiced[voiced > 0]
    if len(voiced) < 20:
        return {}
    median, out = np.log2(np.median(voiced)), {}
    for i, s in enumerate(item["seq"]):
        if s[0] in NUCLEI and times[i]:
            fr = f0[int(times[i][0] / FRAME):int(times[i][1] / FRAME)]
            third = max(len(fr) // 3, 1)
            first, last = fr[:third], fr[-third:]
            if (first > 0).any() and (last > 0).any():
                out[i] = (float(np.log2(np.median(first[first > 0])) - median),
                          float(np.log2(np.median(last[last > 0])) - median))
    return out


def load():
    """[(speaker, item, nucleus rows, where, targets)] of every aligned sentence from a Brazilian reader: one the
    Brazilian dictionary fits at least as well as the European one (within 0.02, and not clearly worse)."""
    fits, out = json.loads((CACHE / "dialect.json").read_text()), []
    for corpus in ("tts", "cml"):
        base = CACHE / corpus
        items = json.loads((base / "items.json").read_text())
        f0s = np.load(base / "f0.npz")
        aligned = {}
        for path in glob.glob(str(base / "mfa/out/**/*.TextGrid"), recursive=True):
            key = Path(path).stem
            if key in items and key in f0s:
                times = phone_times(items[key], textgrid(path))
                if times:
                    aligned[key] = times
        readers = {f"{corpus}:{it['speaker']}" for it in items.values()}
        brazilian = {s for s in readers if s in fits and fits[s][0] >= -0.02 and fits[s][0] + 2 * fits[s][1] >= 0}
        print(f"{corpus}: {len(aligned)} sentences aligned; readers kept {len(brazilian)} of {len(readers)}")
        for key, times in aligned.items():
            it = items[key]
            if f"{corpus}:{it['speaker']}" not in brazilian:
                continue
            have = targets(it, times, f0s[key])
            rows, where = nucleus_features([tuple(s) for s in it["seq"]], [tuple(k) for k in it["kinds"]])
            if have:
                out.append((f"{corpus}:{it['speaker']}", it, rows, where, have))
    return out


def _predict(model, rows):
    index = {k: i for i, k in enumerate(model["names"])}
    coef = np.asarray(model["coef"])
    x = np.zeros((len(rows), len(coef)))
    x[:, -1] = 1.0
    for i, r in enumerate(rows):
        for k, v in r.items():
            if k in index:
                x[i, index[k]] = v
    return (x @ coef).reshape(-1, 2)


def _group(row) -> str:
    return next(k for k in row if ":" in k and not k.split(":")[1].startswith("end"))


def fit():
    data = load()
    speakers = sorted({d[0] for d in data})
    held = set(speakers[::5]) if len(speakers) > 5 else set()   # unseen readers, and every 5th sentence of the rest
    test = [d for n, d in enumerate(data) if d[0] in held or n % 5 == 0]
    train = [d for n, d in enumerate(data) if d[0] not in held and n % 5 != 0]

    def examples(part):
        rows, ys = [], []
        for _s, _it, feats, where, have in part:
            for n, i in enumerate(where):
                if i in have:
                    rows.append(feats[n])
                    ys.append(have[i])
        return rows, np.array(ys)
    model = fit_intonation(*examples(train))
    errors = {"now": collections.defaultdict(list), "real": collections.defaultdict(list)}
    teacher = bank("pt/alex").meta["intonation"]
    for _s, it, feats, where, have in test:
        seq = [[s[0], 0.1, s[1], s[2]] for s in it["seq"]]
        phrases = [SimpleNamespace(kind=k, wh=w) for k, w in it["kinds"]]
        now = tunes((_predict(teacher, feats), where), seq, phrases)[0]
        real = _predict(model, feats)
        for n, i in enumerate(where):
            if i in have:
                for name, p in (("now", now), ("real", real)):
                    errors[name][_group(feats[n])].append(12 * (p[n] - np.array(have[i])))
    print(f"{len(train)} sentences fitted, {len(test)} held out ({len(held)} readers unseen); r = {model['fit']}")
    print("rms error, semitones      the teacher + hand-written tunes   learned from real speech")
    for g in sorted(errors["real"], key=lambda g: (g.split(":")[0], g)):
        if len(errors["real"][g]) >= 20:
            rms = {k: np.sqrt(np.mean(np.square(v[g]))) for k, v in errors.items()}
            print(f"    {g:12s} {len(errors['real'][g]):6d}   {rms['now']:6.2f}   {rms['real']:6.2f}")
    every = {k: np.sqrt(np.mean(np.square(np.concatenate([np.array(x) for x in v.values()]))))
             for k, v in errors.items()}
    print(f"    all                   {every['now']:6.2f}   {every['real']:6.2f}")
    rows, ys = examples(data)
    model = fit_intonation(rows, ys)                 # what ships is fitted on everything
    kinds = collections.Counter(_group(r).split(":")[0] for r in rows)
    OUT.write_text(json.dumps({"intonation": model, "kinds": dict(kinds), "speakers": len(speakers),
                               "sentences": len(data), "nuclei": len(ys),
                               "sources": ["TTS-Portuguese Corpus (CC BY 4.0)", "CML-TTS Portuguese (CC BY 4.0)"]}))
    print(f"-> {OUT}")


if __name__ == "__main__":
    {"fetch": fetch, "align": align, "fit": fit}[sys.argv[1]]()
