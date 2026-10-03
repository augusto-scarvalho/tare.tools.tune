"""Natural voices: speech built from pieces of a teacher's recordings, rebuilt by our vocoder.

A voice bank (data/bank_<lang>_<voice>.npz, made offline by tools/build_speech.py) is a teacher's reading of a few
hundred sentences, kept only as numbers: every 5 ms the pitch, a 32-band spectral envelope and the breathiness, with
the phones labelled. To say a new sentence:

    our front-end    text -> phones, stress, word positions (g2p), intonation (phonetics)
    the teacher's    accent rules (how it pronounces what we transcribe) and durations (a regression on the bank)
    unit selection   one piece of the bank per diphone (middle of a phone to the middle of the next), chosen by
                     Viterbi: the right phones in the right context, few joins, joins where the spectra meet
    assembly         the pieces stretched to our durations, cross-faded at the joins, our pitch on the bank's voicing
    vocoder          speech/vocoder.py rebuilds the sound, moved to the speaker's vocal tract and pitch

Nothing neural runs here: it is table look-up, dynamic programming and arithmetic, deterministic for a seed.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from .. import rng
from .vocoder import ENV_FLOOR, FRAME, Template, synthesize

DATA = Path(__file__).parent / "data"
VOWEL = set("a6eEiIoOuU@") | {"6~", "e~", "i~", "o~", "u~", "w~", "j~"}
VOICED = {"b", "d", "g", "v", "z", "Z", "dZ", "m", "n", "J", "l", "L", "r", "R"}
FRICATIVES = {"s", "z", "S", "Z", "f", "v"}
CLASSES = {"vowel": VOWEL, "stop": {"p", "b", "t", "d", "k", "g"}, "affricate": {"tS", "dZ"},
           "fric": {"f", "v", "s", "z", "S", "Z", "R", "h", "x"}, "nasal": {"m", "n", "N", "J"},
           "liquid": {"l", "L", "r"}, "glide": {"j", "w", "j~", "w~"}, "pause": {"_"}}
# phones that may stand in for each other, and what it costs (0 = the same)
GROUPS = [({"a", "6"}, 0.3), ({"e", "E"}, 0.3), ({"o", "O"}, 0.3), ({"i", "I", "j"}, 0.35), ({"u", "U", "w"}, 0.35),
          ({"U", "w"}, 0.1), ({"I", "j"}, 0.15), ({"6~", "a", "6"}, 0.6), ({"e~", "e", "E"}, 0.6),
          ({"i~", "i", "j~", "j"}, 0.6), ({"o~", "o", "O"}, 0.6), ({"u~", "u", "U", "w~", "w"}, 0.6),
          ({"m", "n", "N", "J"}, 0.7), ({"6", "@"}, 0.4), ({"R", "h", "x"}, 0.3), ({"l", "L"}, 0.5),
          ({"J", "j~"}, 0.6), ({"N", "w~", "j~"}, 0.6)]
N_BEST = 25                       # candidates kept per diphone
JOIN = 0.2                        # the cost of any join, on top of the spectral distance (dB / 10)
SMOOTH = 3                        # frames cross-faded on each side of a join
# a join inside a vowel is heard most, inside a stop closure or a pause least: the join cost is scaled by the class
# of the phone it falls in, so the selection breaks between pieces at consonants
JOIN_CLASS = {"vowel": 3.0, "glide": 2.0, "liquid": 1.5, "nasal": 1.0, "fric": 0.4, "affricate": 0.4, "stop": 0.2,
              "pause": 0.05}
F0_TARGET = 0.5                   # per octave between a piece's own pitch and the pitch it will be given
F0_JOIN = 0.5                     # per octave between the pitches of two pieces that meet


def substitution(a: str, b: str) -> float:
    if a == b:
        return 0.0
    return min((c for g, c in GROUPS if a in g and b in g), default=np.inf)


def klass(sym: str) -> str:
    return next((k for k, v in CLASSES.items() if sym in v), "fric")


# -- durations: what the teacher does, as a regression ----------------------------------------------------------------

def features(seq: list[tuple[str, int, int]]) -> list[dict]:
    """Per phone of [(symbol, stress, flags)] (flags: 1 word-initial, 2 word-final): the duration model's inputs."""
    rows = []
    for i, (sym, st, fl) in enumerate(seq):
        prev = seq[i - 1][0] if i else "_"
        nxt = seq[i + 1][0] if i + 1 < len(seq) else "_"
        j = i
        while j + 1 < len(seq) and not seq[j][2] & 2 and seq[j + 1][0] != "_":
            j += 1
        last_word = j + 1 >= len(seq) or seq[j + 1][0] == "_"      # pre-pausal lengthening
        vowel = sym in VOWEL
        rows.append({f"ph={sym}": 1.0, f"prev={klass(prev)}": 1.0, f"next={klass(nxt)}": 1.0,
                     "stress": float(st > 0), "initial": float(fl & 1 > 0), "final": float(fl & 2 > 0),
                     "last_word": float(last_word), "stress*last": float(st > 0 and last_word),
                     "vowel*last": float(vowel and last_word), "vowel*final": float(vowel and fl & 2 > 0),
                     "pause_next": float(nxt == "_"), f"ph={sym}*stress": float(st > 0)})
    return rows


def fit_durations(phones: list, ridge: float = 2.0) -> dict:
    """log duration ~ phone, stress, word position, neighbours: ridge regression over a bank's labels."""
    rows, ys, seq, durs, utt = [], [], [], [], None
    for p in [*phones, ["_", 0, 0, 0, -1, 0]]:
        if p[4] != utt and seq:
            for r, d, q in zip(features(seq), durs, seq, strict=True):
                if q[0] != "_":
                    rows.append(r)
                    ys.append(np.log(max(d, 0.01)))
            seq, durs = [], []
        utt = p[4]
        seq.append((p[0], p[3], p[5]))
        durs.append((p[2] - p[1]) * FRAME)
    names = sorted({k for r in rows for k in r})
    index = {k: i for i, k in enumerate(names)}
    x = np.zeros((len(rows), len(names) + 1))
    x[:, -1] = 1.0
    for i, r in enumerate(rows):
        for k, v in r.items():
            x[i, index[k]] = v
    y = np.array(ys)
    reg = ridge * np.eye(x.shape[1])
    reg[-1, -1] = 0.0
    coef = np.linalg.solve(x.T @ x + reg, x.T @ y)
    pred = x @ coef
    return {"names": names, "coef": [round(float(c), 5) for c in coef],
            "fit": [round(float(np.corrcoef(pred, y)[0, 1]), 3), round(float(np.std(y - pred)), 3)]}


# -- intonation: what the teacher does, as a regression ---------------------------------------------------------------

NUCLEI = set("a6eEiIoOuU") | {"6~", "e~", "i~", "o~", "u~"}


def nucleus_features(seq: list[tuple[str, int, int]], kinds: list[tuple[str, bool]]) -> tuple[list[dict], list[int]]:
    """For each syllable nucleus of [(symbol, stress, flags)] (pauses "_" split the phrases; `kinds`: (".", "?",
    "!", ","; a wh-question) per phrase): the intonation model's inputs, and where the nucleus is in `seq`."""
    phrases, cur = [], []
    for i, (sym, _st, _fl) in enumerate(seq):
        if sym == "_":
            if cur:
                phrases.append(cur)
            cur = []
        elif sym in NUCLEI:
            cur.append(i)
    if cur:
        phrases.append(cur)
    rows, where = [], []
    for pi, idx in enumerate(phrases):
        kind, wh = kinds[min(pi, len(kinds) - 1)] if kinds else (".", False)
        kind = "?wh" if kind == "?" and wh else kind
        accents = [i for i in idx if seq[i][1] > 0] or [idx[-1]]
        nuclear, first = accents[-1], accents[0]
        for k, i in enumerate(idx):
            from_end, stressed = len(idx) - 1 - k, seq[i][1] > 0
            place = "nuc" if i == nuclear else "post" if i > nuclear else "pre_acc" if stressed else "pre"
            rows.append({f"end={min(from_end, 4)}": 1.0, f"start={min(k, 2)}": 1.0, "stress": float(stressed),
                         f"place={place}": 1.0, f"{kind}:{place}": 1.0, f"{kind}:end={min(from_end, 2)}": 1.0,
                         "first_accent": float(i == first and stressed), "rel": k / max(len(idx) - 1, 1),
                         "first_phrase": float(pi == 0), "last_phrase": float(pi == len(phrases) - 1),
                         "word_final": float(seq[i][2] & 2 > 0), f"kind={kind}": 1.0})
            where.append(i)
    return rows, where


def fit_intonation(rows: list[dict], targets: np.ndarray, ridge: float = 3.0) -> dict:
    """Log2 pitch at the start and the end of each nucleus, relative to the sentence's median: ridge regression."""
    names = sorted({k for r in rows for k in r})
    index = {k: i for i, k in enumerate(names)}
    x = np.zeros((len(rows), len(names) + 1))
    x[:, -1] = 1.0
    for i, r in enumerate(rows):
        for k, v in r.items():
            x[i, index[k]] = v
    reg = ridge * np.eye(x.shape[1])
    reg[-1, -1] = 0.0
    coef = np.linalg.solve(x.T @ x + reg, x.T @ targets)
    pred = x @ coef
    return {"names": names, "coef": np.round(coef, 5).tolist(),
            "fit": [round(float(np.corrcoef(pred[:, j], targets[:, j])[0, 1]), 3) for j in range(2)]}


# -- the banks --------------------------------------------------------------------------------------------------------

class Bank:
    def __init__(self, path: Path):
        d = np.load(path)
        self.meta = json.loads(bytes(d["meta"]).decode())
        models = path.with_suffix(".json")          # duration and intonation models, refitted without the frames
        if models.exists():
            self.meta.update(json.loads(models.read_text()))
        self.name = f"{self.meta['lang']}/{self.meta['name']}"
        self.tract, self.pitch = self.meta["tract"], self.meta["pitch"]
        self.f0 = d["f0"].astype(np.float64)
        env = d["env"]
        if self.meta.get("env_delta"):                 # stored frame-to-frame (mod 256): it compresses better
            env = np.cumsum(env, axis=0, dtype=np.uint8)
        self._env8 = env                               # kept as stored (0.5 dB steps); rows are decoded on demand
        self.ap = d["ap"].astype(np.float32) / 255
        self.ph = json.loads(bytes(d["phones"]).decode())
        self.by_sym: dict[str, list[int]] = {}
        for k, p in enumerate(self.ph):
            self.by_sym.setdefault(p[0], []).append(k)
        bounds = np.array([p[1:3] for p in self.ph])
        self.mid_env = self.rows((bounds[:, 0] + bounds[:, 1]) // 2)
        voiced = self.f0 > 0                           # each phone's pitch: the mean of its voiced frames
        starts = np.minimum(bounds[:, 0], len(self.f0) - 1)
        sums = np.add.reduceat(np.where(voiced, self.f0, 0.0), starts)
        counts = np.add.reduceat(voiced.astype(float), starts)
        self.ph_f0 = np.where(counts > 0, sums / np.maximum(counts, 1), 0.0)   # phones tile the bank in order
        model = self.meta["durations"]
        self._index = {k: i for i, k in enumerate(model["names"])}
        self._coef = np.asarray(model["coef"])

    def intonation(self, seq: list[tuple[str, int, int]], kinds: list[tuple[str, bool]]):
        """(log2 pitch at the start and end of each nucleus relative to the sentence's median, where they are), or
        None when the bank has no intonation model."""
        model = self.meta.get("intonation")
        if not model:
            return None
        index = {k: i for i, k in enumerate(model["names"])}
        coef = np.asarray(model["coef"])
        rows, where = nucleus_features(seq, kinds)
        x = np.zeros((len(rows), len(coef)))
        x[:, -1] = 1.0
        for i, r in enumerate(rows):
            for k, v in r.items():
                if k in index:
                    x[i, index[k]] = v
        return x @ coef, where

    def rows(self, idx) -> np.ndarray:
        """Envelope frames (dB) at the given indices."""
        return self._env8[idx].astype(np.float64) / 2 + ENV_FLOOR

    @property
    def env(self) -> np.ndarray:
        """The whole envelope in dB (analysis; the engine decodes rows as it needs them)."""
        return self.rows(slice(None))

    def durations(self, seq: list[tuple[str, int, int]]) -> list[float]:
        out = []
        for r in features(seq):
            x = np.zeros(len(self._coef))
            x[-1] = 1.0
            for k, v in r.items():
                if k in self._index:
                    x[self._index[k]] = v
            out.append(float(np.exp(x @ self._coef)))
        return out

    def matches(self, sym: str) -> list[tuple[float, int]]:
        out = []
        for s, ks in self.by_sym.items():
            c = substitution(sym, s)
            if np.isfinite(c):
                out += [(c, k) for k in ks]
        return out


def banks(lang: str | None = None) -> list[str]:
    names = sorted(p.stem[5:].replace("_", "/", 1) for p in DATA.glob("bank_*.npz"))
    return [n for n in names if lang is None or n.startswith(lang + "/")]


@lru_cache(maxsize=8)
def bank(name: str) -> Bank:
    path = DATA / f"bank_{name.replace('/', '_')}.npz"
    if not path.exists():
        raise ValueError(f"unknown voice bank {name!r}; choose from {', '.join(banks())}")
    return Bank(path)


def closest(lang: str, tract: float) -> str:
    """The bank whose teacher's vocal tract is nearest (a man's bank for long tracts, a woman's for short ones)."""
    options = banks(lang)
    if not options:
        raise ValueError(f"no natural voice for {lang!r}; available: {', '.join(banks()) or 'none'}")
    return min(options, key=lambda n: (abs(np.log(tract / bank(n).tract)), n))


# -- from our transcription to the teacher's ---------------------------------------------------------------------------

def accent_pt(seq: list[list]) -> list[list]:
    """Our pt transcription -> the teacher's accent, found by aligning both over the teacher's corpus (94% of phones
    then agree). Entries: [symbol, our duration, stress, flags (1 word-initial, 2 word-final)]."""
    def rest_of_word(i):
        out = []
        while i < len(seq) and not seq[i][3] & 2 and seq[i][0] != "_":
            i += 1
            if i < len(seq) and seq[i][0] != "_" and not seq[i][3] & 1:
                out.append(seq[i][0])
            else:
                break
        return out

    def start_of_word(i):
        out = []
        while i > 0 and not seq[i][3] & 1:
            i -= 1
            out.append(seq[i][0])
        return out

    out, i = [], 0
    while i < len(seq):
        sym, dur, st, fl = seq[i]
        nxt = seq[i + 1] if i + 1 < len(seq) else ["_", 0.0, 0, 0]
        rest = rest_of_word(i)
        inside = bool(rest)
        i += 1
        if sym == "R" and nxt[0] not in VOWEL:                 # coda r: a tap, a short schwa inside the word
            out.append(["r", dur, 0, fl])
            if inside:
                out.append(["@", 0.0, 0, 0])
            continue
        if sym == "e~":                                         # em, en: [ẽj]
            out += [["e", dur, st, fl & 1], ["j", 0.0, 0, 0 if inside else fl & 2]]
            if nxt[0] == "j~":
                out.append(["N", nxt[1], 0, nxt[3] & 2])
                i += 1
            continue
        if sym == "L":                                          # lh: [lj]
            out += [["l", dur / 2, 0, fl & 1], ["j", dur / 2, 0, fl & 2]]
            continue
        if sym == "6" and (any(r in VOWEL for r in rest) or not any(b in VOWEL for b in start_of_word(i - 1))):
            sym = "a"                     # reduced only in the last syllable of a longer word: a, da, na are [a]
        if sym in ("a", "6") and inside and nxt[0] in ("m", "n", "J"):
            sym = "6~" if st or nxt[0] == "J" else "6"         # cama [kɐ̃mɐ], banho; unstressed [ɐ]
        if sym == "I" and inside and nxt[0] in VOWEL:
            sym = "j"                                           # dia, tio: a glide before the vowel
        if sym in ("m", "n") and out and out[-1][0].endswith("~") and nxt[0] not in VOWEL:
            sym = "m" if nxt[0] in ("p", "b") else "N"
        if sym == "s" and nxt[0] in VOICED:                     # os dragões [uz]
            sym = "z"
        out.append([sym, dur, st, fl])
        if sym in ("6~", "o~", "i~", "u~") and ((nxt[0] in FRICATIVES and inside) or (fl & 2 and sym in ("i~", "u~"))):
            out.append(["N", 0.0, 0, fl & 2])                   # cansado [kɐ̃ŋsadu], sim, um [ũŋ]
            out[-2][3] &= ~2
    return out


ACCENTS = {"pt": accent_pt}


# -- unit selection ---------------------------------------------------------------------------------------------------

def select(b: Bank, seq: list[list], pitch: list[float] | None = None) -> list[tuple[int, int]]:
    """For each diphone of `seq`: (bank phone giving the first phone's second half, bank phone giving the second
    phone's first half). Contiguous in the bank when possible; Viterbi over target and join costs. `pitch`: the
    pitch each phone will get (Hz, 0 = unknown), so pieces spoken near it are preferred."""
    n = len(seq)
    pitch = pitch or [0.0] * n
    cands, costs = [], []
    for i in range(n - 1):
        a, c = seq[i], seq[i + 1]
        left = b.matches(a[0])
        opts = []
        for cost_a, k in left:
            if k + 1 >= len(b.ph) or b.ph[k + 1][4] != b.ph[k][4]:
                continue
            cost_c = substitution(c[0], b.ph[k + 1][0])
            if not np.isfinite(cost_c):
                continue
            cost = cost_a + cost_c
            if a[0] in VOWEL and (b.ph[k][3] > 0) != (a[2] > 0):
                cost += 0.15
            if c[0] in VOWEL and (b.ph[k + 1][3] > 0) != (c[2] > 0):
                cost += 0.15
            if i > 0 and k > 0:
                cost += 0.1 * min(substitution(seq[i - 1][0], b.ph[k - 1][0]), 1.0)
            if i + 2 < n and k + 2 < len(b.ph):
                cost += 0.1 * min(substitution(seq[i + 2][0], b.ph[k + 2][0]), 1.0)
            for want, kk, f in ((a, k, pitch[i]), (c, k + 1, pitch[i + 1])):
                have = b.ph[kk]
                cost += 0.15 * abs(np.log(max(have[2] - have[1], 1) * FRAME / max(want[1], 0.01)))
                if f > 0 and b.ph_f0[kk] > 0:
                    cost += F0_TARGET * abs(np.log2(b.ph_f0[kk] / f))
            opts.append((cost, k, k + 1))
        if not opts:                       # no such diphone in the bank: halves from different places
            right = sorted(b.matches(c[0]))[:6]
            opts = [(1.0 + c1 + c2, k1, k2) for c1, k1 in sorted(left)[:6] for c2, k2 in right]
            if not opts:
                raise ValueError(f"the voice bank {b.name} cannot say {a[0]!r} {c[0]!r}")
        opts.sort()
        opts = opts[:N_BEST]
        cands.append([(l_, r_) for _, l_, r_ in opts])
        costs.append(np.array([c_ for c_, _, _ in opts]))
    acc, back = costs[0], []
    for i in range(1, len(cands)):
        prev_r = np.array([r for _, r in cands[i - 1]])
        cur_l = np.array([l_ for l_, _ in cands[i]])
        d = np.abs(b.mid_env[prev_r][:, None, :] - b.mid_env[cur_l][None, :, :]).mean(-1) / 10 + JOIN
        fa, fb = b.ph_f0[prev_r][:, None], b.ph_f0[cur_l][None, :]
        both = (fa > 0) & (fb > 0)
        d = d + F0_JOIN * np.where(both, np.abs(np.log2(np.maximum(fa, 1) / np.maximum(fb, 1))), 0.0)
        d = d * JOIN_CLASS.get(klass(seq[i][0]), 1.0)
        d[prev_r[:, None] == cur_l[None, :]] = 0.0
        total = acc[:, None] + d
        back.append(np.argmin(total, 0))
        acc = total.min(0) + costs[i]
    path = [int(np.argmin(acc))]
    for bp in reversed(back):
        path.append(int(bp[path[-1]]))
    path.reverse()
    return [cands[i][j] for i, j in enumerate(path)]


def _couple(b: Bank, k1: int, k2: int, lo: float = 0.25, hi: float = 0.75) -> tuple[float, float]:
    """Optimal coupling: where in bank phone k1 to leave and in k2 to enter, so the spectra meet best."""
    (a1, b1), (a2, b2) = b.ph[k1][1:3], b.ph[k2][1:3]
    i1 = np.arange(int(a1 + lo * (b1 - a1)), max(int(a1 + hi * (b1 - a1)), int(a1 + lo * (b1 - a1)) + 1))
    i2 = np.arange(int(a2 + lo * (b2 - a2)), max(int(a2 + hi * (b2 - a2)), int(a2 + lo * (b2 - a2)) + 1))
    d = np.abs(b.rows(i1)[:, None, :] - b.rows(i2)[None, :, :]).mean(-1)
    j1, j2 = np.unravel_index(np.argmin(d), d.shape)
    return float(i1[j1]), float(i2[j2])


def pieces(b: Bank, seq: list[list], units: list[tuple[int, int]]) -> tuple[list[tuple], list[int]]:
    """Each target phone is two pieces of the bank (its first half, its second half), each laid over the output
    frames its duration asks for: [[bank frame from, bank frame to, output frames], ...] and the pieces that start
    a join."""
    out, joins = [], []
    for i, (_sym, dur, *_r) in enumerate(seq):
        first = units[i - 1][1] if i > 0 else units[0][0]
        second = units[i][0] if i < len(units) else units[-1][1]
        (a, e), (a2, e2) = b.ph[first][1:3], b.ph[second][1:3]
        m1, m2 = ((a + e) / 2, (a2 + e2) / 2) if first == second else _couple(b, first, second)
        half = max(int(round(dur / 2 / FRAME)), 1)
        out.append((round(float(a), 2), round(float(m1), 2), half))
        if first != second:
            joins.append(len(out))
        out.append((round(float(m2), 2), round(float(e2), 2), half))
    return out, joins


def frames(b: Bank, parts: list[list], joins: list[int], smooth: int = SMOOTH):
    """The bank's frames along the pieces; joins cross-fade both pieces, each carried on past its cut."""
    src = np.concatenate([s + (np.arange(n) + 0.5) / n * (e - s) for s, e, n in parts])
    rate = np.concatenate([np.full(n, (e - s) / n) for s, e, n in parts])
    starts = np.cumsum([0] + [n for _, _, n in parts])
    last = len(b.f0) - 1

    def at(x):
        lo = np.clip(np.floor(x).astype(int), 0, last)
        hi = np.minimum(lo + 1, last)
        w = np.clip(x - lo, 0.0, 1.0)[:, None]
        return (b.rows(lo) * (1 - w) + b.rows(hi) * w, b.ap[lo] * (1 - w) + b.ap[hi] * w,
                b.f0[np.clip(np.round(x).astype(int), 0, last)] > 0)

    env, ap, voiced = at(src)
    for p in joins:
        j = int(starts[p])
        o = np.arange(max(j - smooth, 1), min(j + smooth, len(src) - 1))
        if not len(o):
            continue
        ea, aa, va = at(src[j - 1] + (o - (j - 1)) * rate[j - 1])
        eb, ab, vb = at(src[j] + (o - j) * rate[j])
        w = ((o - o[0] + 0.5) / len(o))[:, None]
        env[o] = ea * (1 - w) + eb * w
        ap[o] = aa * (1 - w) + ab * w
        voiced[o] = np.where(w[:, 0] < 0.5, va, vb)
    return env, ap, voiced


# -- the spec layer ---------------------------------------------------------------------------------------------------

def render_spoken(sp, sr: int, seed: int) -> np.ndarray:
    """A spec.Spoken layer, peak-normalised to its gain."""
    b = bank(sp.bank)
    env, ap, voiced = frames(b, sp.pieces, sp.joins)
    f0 = np.interp(np.arange(len(env)), np.linspace(0, len(env) - 1, len(sp.f0)), sp.f0)
    f0 = np.where(voiced, f0, 0.0)
    t = Template(sp.bank, "speech", b.name, b.tract, float(np.median(f0[f0 > 0])) if (f0 > 0).any() else 0.0,
                 f0, env, ap)
    y = synthesize(t, sr, warp=sp.warp, breath=sp.breath, tilt=sp.tilt, seed=rng.key(seed, "spoken"))
    return sp.gain * y / (np.max(np.abs(y)) + 1e-12)


# -- phrase-final tunes ------------------------------------------------------------------------------------------------
# The teacher does not make Brazilian Portuguese question tunes: measured over its corpus, its yes/no questions end
# like statements (last two vowels -8.7 and -6.4 semitones from the sentence's median, statements -8.5 and -8.0).
# These replace what the regression learned for the last stressed vowel and what follows it, in semitones from the
# median, after descriptions of Brazilian Portuguese intonation (Moraes 2008; Frota et al. 2015):
#   ?    yes/no question, L+H* L%: the last stressed vowel rises from low to high, what follows falls back down;
#        a last stressed syllable at the very end keeps the rise
#   ?!   surprise ("Sério?!", "O quê?!"): the same, higher and longer
#   …    trailing off: left hanging, level and slow
# A wh-question ("Onde...?") falls like a statement (the regression has it), with the question word raised.
TUNES = {
    "?": {"nuc": (-1.5, 7.0), "post": (4.0, -2.0), "end": 6.0, "stretch": 1.1},
    "?!": {"nuc": (0.0, 11.0), "post": (7.0, 0.0), "end": 10.0, "stretch": 1.3},
    "…": {"nuc": (-0.5, -1.0), "post": (-1.0, -1.5), "end": -1.0, "stretch": 1.45},
}
WH_RAISE = 1.5                    # semitones on a wh-question's first vowel (the regression already starts high)
EXCLAIM = 1.25                    # an exclamation's pitch movements, wider


def phrase_nuclei(seq: list) -> list[tuple[list[int], int]]:
    """Per phrase of `seq` (split at pauses): the indices of its syllable nuclei and of its last stressed one."""
    out, cur = [], []
    for i, p in enumerate([*seq, ["_", 0, 0, 0]]):
        if p[0] == "_":
            if cur:
                stressed = [k for k in cur if seq[k][2] > 0]
                out.append((cur, stressed[-1] if stressed else cur[-1]))
            cur = []
        elif p[0] in NUCLEI:
            cur.append(i)
    return out


def stretch_finals(seq: list, phrases) -> None:
    """Lengthen, in place, the end of the phrases whose tune asks for it (from the last stressed vowel on)."""
    for (idx, nuclear), ph in zip(phrase_nuclei(seq), phrases, strict=False):
        factor = TUNES.get(ph.kind, {}).get("stretch", 1.0)
        if factor != 1.0:
            last = idx[-1]
            while last + 1 < len(seq) and seq[last + 1][0] != "_":
                last += 1
            for k in range(nuclear, last + 1):
                seq[k][1] *= factor


def tunes(learned, seq: list, phrases, final: float = 0.0):
    """The learned targets with the phrase-final tunes laid over them (log2 units). `final`: semitones added to
    the last vowels of statements and exclamations (an emotion's end: anger falls further, sadness less)."""
    targets, where = learned
    targets = np.array(targets, dtype=float)
    pos = {i: k for k, i in enumerate(where)}
    for (idx, nuclear), ph in zip(phrase_nuclei(seq), phrases, strict=False):
        tune = TUNES.get(ph.kind)
        if ph.kind == "?" and ph.wh:
            tune = None                                      # wh-questions fall: keep the learned tune
            targets[pos[idx[0]]] += WH_RAISE / 12
        if ph.kind == "!":
            mean = targets[[pos[i] for i in idx]].mean()
            for i in idx:
                targets[pos[i]] = mean + EXCLAIM * (targets[pos[i]] - mean)
        if tune:
            post = [i for i in idx if i > nuclear]
            if post:
                targets[pos[nuclear]] = np.array(tune["nuc"]) / 12
                ends = np.linspace(tune["post"][0], tune["post"][1], 2 * len(post))
                for k, i in enumerate(post):
                    targets[pos[i]] = ends[2 * k:2 * k + 2] / 12
            else:
                targets[pos[nuclear]] = np.array([tune["nuc"][0], tune["end"]]) / 12
        elif final and ph.kind in (".", "!", ","):
            tail = [i for i in idx if i >= nuclear]
            for k, i in enumerate(tail):
                w = (k + 1) / len(tail)
                targets[pos[i]] += np.array([w * 0.5, w]) * final / 12
    return targets, where


def _contour(learned, edges, n: int, pitch: float, range_: float, melody) -> np.ndarray:
    """Nucleus targets (start and end of each vowel, a quarter in) -> pitch per output frame, smoothed (50 ms)."""
    targets, where = learned
    xs, ys = [0.0], [0.0]
    for k, ((start, end), i) in enumerate(zip(targets, where, strict=True)):
        a, e = edges[i], edges[i + 1]
        note = melody[k % len(melody)] / 12 if melody else 0.0
        xs += [a + 0.25 * (e - a), e - 0.25 * (e - a)]
        ys += [range_ * start + note, range_ * end + note]
    if len(xs) > 1:
        ys[0] = ys[1]
    lf = np.interp(np.arange(n), xs, ys)
    kernel = np.hanning(12)[1:-1]
    kernel /= kernel.sum()
    lf = np.convolve(np.pad(lf, 5, mode="edge"), kernel, mode="same")[5:-5]
    return pitch * 2 ** lf


def plan(phrases, lang: str, name: str, pitch: float, range_: float = 1.0, rate: float = 1.0,
         melody: list[float] | None = None, jitter: float = 0.0, seed: int = 0, final: float = 0.0,
         pause: float = 1.0) -> tuple[list, list, list, str]:
    """Phrases (from a g2p front-end) -> (pieces, joins, f0 per output frame, the teacher-accent transcription)."""
    from .phonetics import _intonation, segments
    b = bank(name)
    segs, sylls = segments(phrases, lang, rate)
    seq, meta = [], None
    for s in segs:                     # our segments (a stop is closure + burst + aspiration) -> phones
        fl = (1 if s.meta.get("word_initial") else 0) | (2 if s.meta.get("word_final") else 0)
        st = 2 if s.vowel_of >= 0 and sylls[s.vowel_of]["accent"] else 0
        if seq and seq[-1][0] == s.phone and s.phone != "_" and s.meta == meta:
            seq[-1][1] += s.dur
        else:
            seq.append([s.phone, s.dur, st, fl])
        meta = s.meta
    ends = np.cumsum([0.0] + [s.dur for s in segs])
    t_ours = np.arange(int(ends[-1] / FRAME) + 1) * FRAME
    f0_ours = _intonation(segs, sylls, t_ours, pitch, range_, lang, melody)
    if lang in ACCENTS:
        seq = ACCENTS[lang](seq)
    ours = np.cumsum([0.0] + [p[1] for p in seq])
    for p, d in zip(seq, b.durations([(p[0], p[2], p[3]) for p in seq]), strict=True):
        if p[0] != "_":
            p[1] = d / rate
    stretch_finals(seq, phrases)
    for i in range(1, len(seq) - 1):
        if seq[i][0] == "_":
            seq[i][1] *= pause
    new = np.cumsum([0.0] + [2 * max(int(round(p[1] / 2 / FRAME)), 1) * FRAME for p in seq])
    n = int(round(new[-1] / FRAME))
    f0 = np.interp(np.interp(np.arange(n) * FRAME, new, ours), t_ours, f0_ours)
    learned = b.intonation([(p[0], p[2], p[3]) for p in seq], [(ph.kind, ph.wh) for ph in phrases])
    if learned is not None:            # the teacher's intonation, for our phones, timing and pitch
        f0 = _contour(tunes(learned, seq, phrases, final), new / FRAME, n, pitch, range_, melody)
    middles = np.clip(((new[:-1] + new[1:]) / 2 / FRAME).astype(int), 0, n - 1)
    units = select(b, seq, [float(f0[m]) if p[0] in VOWEL or p[0] in VOICED else 0.0
                            for p, m in zip(seq, middles, strict=True)])
    parts, joins = pieces(b, seq, units)
    if jitter:                         # a slow random wander, as a voice has
        from ..render import smooth_noise
        f0 = f0 * 2 ** (jitter * smooth_noise(rng.key(seed, "jitter"), n, int(1 / FRAME), 6) / 12)
    phones = " ".join(p[0] + ("'" if p[2] else "") for p in seq)
    return parts, joins, [round(float(x), 1) for x in f0], phones
