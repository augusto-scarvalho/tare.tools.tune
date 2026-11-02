"""The sound as text, for a reader that cannot hear (an agent): auditory bands by time in 6 dB digits, a DIFF against
another sound, and lines of measured facts. It shows structure (attack, rings, tails, pitch); it never says how a
sound sounds, and NOT_SHOWN says what it leaves out."""

from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy.signal import find_peaks, get_window, welch

from .analysis import _levels, _mono, clean_f0, common_end_db, loudest_hz, measures, segments, sounds_at, yin

BANDS, LOW, HIGH, COLS = 20, 80.0, 8000.0, 50
STEPS_MS = (2, 5, 10, 15, 20, 25, 30, 40, 50, 60, 80, 100, 120, 150, 200, 250, 300, 400, 500, 1000, 2000, 5000)
NOT_SHOWN = ("Not shown: phase, detail finer than a column or a band, roughness, masking. Cells are A-weighted band "
             "energy in 6 dB steps under each sound's own loudest cell, not loudness.")
BASIS = ("time zero at each sound's onset (its first 10 ms within 35 dB of its loudest); 20 ERB bands, 80 Hz to the "
         "band both rates hold; each band through a Hann window of the ear's own time resolution there (2/ERB, 3-40 "
         "ms) centred on its column; digits 1-9 in 6 dB steps under the sound's loudest cell, '.' 54 dB under")


def bands(high=HIGH, n=BANDS):
    """Centres and edges (Hz) of `n` ERB-spaced bands from 80 Hz to `high`."""
    e = np.linspace(*(21.4 * np.log10(1 + 0.00437 * f) for f in (LOW, high)), n + 1)
    edges = (10 ** (e / 21.4) - 1) / 0.00437
    return np.sqrt(edges[:-1] * edges[1:]), edges


def a_weight(f):
    """The A-weighting curve in dB: how much quieter the ear hears each frequency than 1 kHz."""
    f2 = np.asarray(f, dtype=np.float64) ** 2
    r = 12194**2 * f2**2 / ((f2 + 20.6**2) * np.sqrt((f2 + 107.7**2) * (f2 + 737.9**2)) * (f2 + 12194**2))
    return 20 * np.log10(r) + 2.0


def cochleagram(y, sr, start, step, cols, edges):
    """Band energy in dB (not normalised), bands x columns, columns of `step` s from `start` s."""
    out = np.empty((len(edges) - 1, cols))
    centres = np.round((start + (np.arange(cols) + 0.5) * step) * sr).astype(int)
    for b, (lo, hi) in enumerate(zip(edges, edges[1:], strict=False)):
        win = max(int(np.clip(2 / (24.7 * (0.00437 * np.sqrt(lo * hi) + 1)), 0.003, 0.040) * sr) // 2 * 2, 8)
        nfft = max(1 << int(np.ceil(np.log2(win))), 2048)
        pad = np.pad(y, (win - min(centres.min() - win // 2, 0), max(0, centres.max() + win - len(y)) + win))
        frames = pad[(centres - win // 2 + win - min(centres.min() - win // 2, 0))[:, None] + np.arange(win)]
        spec = np.abs(np.fft.rfft(frames * np.hanning(win), nfft)) ** 2
        f = np.fft.rfftfreq(nfft, 1 / sr)
        pick = (f >= lo) & (f < hi)
        pick = pick if pick.any() else np.abs(f - np.sqrt(lo * hi)) == np.abs(f - np.sqrt(lo * hi)).min()
        out[b] = 10 * np.log10(spec[:, pick].sum(axis=1) / win + 1e-20)
    return out


def band_energy(y, sr, win, hop, nfft, bins, block=1024):
    """|STFT|^2 at a few bins only (bins x frames), framed as scipy.signal.stft frames (periodic Hann, zero
    boundary, padded end) and unscaled; a block of frames at a time, so memory stays flat however long the file."""
    x = np.pad(y, (win // 2, win // 2 + -(len(y) + 2 * (win // 2) - win) % hop))
    frames = sliding_window_view(x, win)[::hop]
    basis = get_window("hann", win)[:, None] * np.exp(-2j * np.pi * np.outer(np.arange(win), bins) / nfft)
    return np.concatenate([np.abs(frames[i:i + block] @ basis) ** 2 for i in range(0, len(frames), block)]).T


def _digits(db):
    """dB under the loudest (<= 0) to '1'..'9' in 6 dB steps, '.' at 54 dB under."""
    return "".join("." if v <= -54 else str(int(np.clip(np.floor(v / 6) + 10, 1, 9))) for v in db)


def _hz(f):
    return f"{float(f'{f:.2g}'):.0f}"


def _ruler(cols, step_ms, start_ms):
    return "".join(str(round(start_ms + k * step_ms)).ljust(5) for k in range(0, cols, 5))[:cols]


class Heard:
    """One sound as the ear reads it: mono samples from its time zero, and its facts."""

    def __init__(self, name, source, audio, sr, *, loop=False, align="onset", end_db=-40.0, high=HIGH):
        audio = np.asarray(audio, dtype=np.float64)
        self.name, self.source, self.sr, self.loop, self.raw = name, source, sr, loop, audio
        self.channels = 1 if audio.ndim == 1 else audio.shape[1]
        mono = _mono(audio)
        db = _levels(mono, sr)
        w = max(sr // 100, 1)
        zero = 0 if not len(db) else int(np.argmax(db) if align == "peak" else np.argmax(db > -35))
        self.zero_s, self.y = zero * w / sr, mono[zero * w:]
        self.db = db[zero:]  # 10 ms windows from time zero, dB under the loudest
        self.m = measures(mono, sr, high, pitch=False, end_db=end_db)
        active = self.y[:int(min(self.m.get("active_s", 0), 20) * sr)] if self.m["status"] == "measured" else self.y
        track, self.aper = yin(active, sr) if len(active) else (np.zeros(0), np.zeros(0))
        self.f0 = clean_f0(track)
        self.voiced = float((self.f0 > 0).mean()) if len(self.f0) else 0.0
        self.active, self.subharmonic = active, False

    def until(self, floor):
        """ms from time zero to the last 10 ms over `floor` dB (under the loudest)."""
        over = np.flatnonzero(self.db > floor)
        return int((over[-1] + 1) * 10) if len(over) else 0

    def falls(self, floor):
        """'-40 dB at 420 ms', or that the file ends before the sound falls that far (a noise floor, or a cut)."""
        end = self.until(floor)
        return f"{floor} dB at {end} ms" if end < len(self.db) * 10 else f"{floor} dB not reached by the end"

    def lines(self, high):
        m, name = self.m, self.name
        kind = (f"{name} {self.source}: {self.sr} Hz {'stereo' if self.channels == 2 else 'mono'}, "
                f"{len(self.raw) / self.sr:.2f} s, onset {self.zero_s:.2f} s")
        if m["status"] != "measured":
            return [kind + ", silent"]
        kind += f", floor {m['noise_floor_db']:.0f} dB" if m["noise_floor_db"] > -90 else ""
        kind += ", loop" if self.loop else ""
        falls = ", ".join(self.falls(t) for t in (-20, -40, -60))
        out = [kind, f"{name} envelope: attack {m['attack_ms']} ms; {falls}"]
        out.append(f"{name} " + self.peaks(high))
        if self.voiced < 0.2:
            out.append(f"{name} pitch: unvoiced ({self.voiced:.0%} voiced)")
        elif self.subharmonic:
            ring, tracked = loudest_hz(self.active, self.sr, high), np.median(self.f0[self.f0 > 0])
            out.append(f"{name} pitch: " + (f"the {ring:.0f} Hz ring, above the tracker's 1600 Hz range" if ring >= 1550
                                             else "none") + f" (it reads {tracked:.0f} Hz, where nothing sounds)")
        else:
            hz = self.f0[self.f0 > 0]
            med = float(np.median(hz))
            st = 12 * np.log2(hz / med)
            third = max(len(hz) // 3, 1)
            glide = 12 * np.log2(np.median(hz[-third:]) / np.median(hz[:third]))
            low, high_st = np.percentile(st, 10), np.percentile(st, 90)
            out.append(f"{name} pitch: median {med:.0f} Hz, range {low:+.1f}..{high_st:+.1f} st, glide {glide:+.1f} "
                       f"st first to last voiced third, {segments(self.f0)} syllable(s)")
        thirds = np.array_split(self.active, 3) if len(self.active) >= 3 * 64 else []
        if len(thirds):
            c = [self._centroid(part, high) for part in (thirds[0], thirds[-1])]
            if all(c):
                out.append(f"{name} brightness: centroid {c[0]:.0f} Hz first third, {c[1]:.0f} Hz last third "
                           f"({12 * np.log2(c[1] / c[0]):+.1f} st)")
        if self.channels == 2:
            left, right = self.raw[:, 0], self.raw[:, 1]
            mid, side = (left + right) / 2, (left - right) / 2
            lr = 10 * np.log10((left**2).sum() / max((right**2).sum(), 1e-20) + 1e-20)
            under = 10 * np.log10((mid**2).sum() / max((side**2).sum(), 1e-20))
            out.append(f"{name} stereo: L-R {lr:+.1f} dB, side {min(under, 60):.0f} dB under mid")
        return out

    def _centroid(self, part, high):
        spectrum = np.abs(np.fft.rfft(part * np.hanning(len(part)))) ** 2
        f = np.fft.rfftfreq(len(part), 1 / self.sr)
        pick = (f >= 100) & (f <= high)
        return float((f[pick] * spectrum[pick]).sum() / spectrum[pick].sum()) if spectrum[pick].sum() > 0 else None

    def peaks(self, high, top=4):
        """The strongest spectral peaks of the active part (prominence over 10 dB) and how long each rings, to
        20 dB under its own loudest moment; harmonics of a voiced pitch are named as such, not listed."""
        part = self.active[:3 * self.sr]
        if len(part) < 256:
            return "peaks: too short"
        nper = min(len(part), 1 << int(np.log2(self.sr * 0.1)))
        f, p = welch(part, self.sr, nperseg=nper)
        pick = (f >= LOW) & (f <= high)
        f, s = f[pick], 10 * np.log10(p[pick] + 1e-30)
        idx, _ = find_peaks(s, prominence=10, distance=max(1, int(60 / (f[1] - f[0]))))
        if not len(idx):
            return "peaks: none 10 dB over their surroundings (noise-like)"
        kept = []
        for i in idx[np.argsort(-s[idx])]:  # one per auditory band: a cluster of bins is one ring, not four
            if all(abs(f[i] - f[k]) > 24.7 * (0.00437 * f[k] + 1) for k in kept):
                kept.append(i)
        kept = np.array(kept)
        strongest = s[kept[0]]
        idx = kept[s[kept] >= strongest - 30]  # within 30 dB of the strongest
        head = ""
        if self.voiced >= 0.2:
            f0 = float(np.median(self.f0[self.f0 > 0]))
            if sounds_at(part, self.sr, f0, high):  # the fundamental sounds: a pitch and its harmonics
                harmonic = np.abs(f[idx] / f0 - np.round(f[idx] / f0)) * f0 <= 0.03 * f[idx]
                head, idx = f"harmonics of {f0:.0f} Hz; ", idx[~harmonic]
            else:  # nothing at the tracked pitch: a ring above the tracker's 1600 Hz read as its subharmonic
                self.subharmonic = True
        win = min(max(int(0.04 * self.sr), 64), len(self.y))  # a click shorter than 40 ms: one window as long
        hop = min(max(int(0.01 * self.sr), 1), win // 4)
        nfft = 1 << int(np.ceil(np.log2(4 * win)))
        ff = np.fft.rfftfreq(nfft, 1 / self.sr)
        rows = []
        for i in idx[:top]:
            j = int(np.argmin(np.abs(ff - f[i])))
            e = band_energy(self.y, self.sr, win, hop, nfft, np.arange(max(j - 1, 0), min(j + 2, len(ff)))).sum(axis=0)
            tt = np.arange(len(e)) * hop / self.sr
            e = 10 * np.log10(e / e.max() + 1e-12)
            loudest = int(np.argmax(e))
            below = np.flatnonzero(e[loudest:] < -20)
            ring = (f"rings {round((tt[loudest + below[0]] - tt[loudest]) * 1000)} ms" if len(below)
                    else "rings past the end")
            rows.append(f"{f[i]:.0f} Hz {s[i] - strongest:+.0f} dB {ring}")
        return "peaks: " + head + ("; ".join(rows) if rows else "no other")


def _grid(heard, start, step, cols, centres, edges, weight):
    db = cochleagram(heard.y, heard.sr, start, step, cols, edges) + (a_weight(centres)[:, None] if weight else 0)
    return db - db.max()


def grid_text(name, db, centres, start_ms, step_ms, f0=None):
    rows = [f"{name} {start_ms:g}..{start_ms + step_ms * db.shape[1]:g} ms, {step_ms:g} ms/col"]
    rows += [f"{_hz(centres[i]):>5}|{_digits(db[i])}|" for i in range(len(centres) - 1, -1, -1)]
    broad = 10 * np.log10((10 ** (db / 10)).sum(axis=0))
    rows.append(f"   dB|{_digits(broad - broad.max())}|")
    if f0 is not None:
        rows.append(f"   f0 {f0}")
    rows.append("   ms " + _ruler(db.shape[1], step_ms, start_ms))
    return rows


def _f0_row(heard, start_ms, step_ms, cols):
    if heard.voiced < 0.2:
        return None
    hop = 5  # ms, yin's
    cells = []
    for k in range(0, cols, 5):
        a, b = int((start_ms + k * step_ms) / hop), int((start_ms + (k + 5) * step_ms) / hop)
        v = heard.f0[max(a, 0):max(b, 0)]
        v = v[v > 0]
        cells.append((f"{np.median(v):.0f}" if len(v) else ".").ljust(5))
    return "".join(cells)[:cols]


def diff_text(a, b, an, bn, centres, start_ms, step_ms):
    """`b` against `a`, both under their own loudest: +/- over 6 dB, = within, blank where both are 40 dB under."""
    d, loud = b - a, np.maximum(a, b) > -40
    plus, minus = (d > 6) & loud, (d < -6) & loud
    end_ms = start_ms + step_ms * d.shape[1]
    rows = [f"DIFF {bn} vs {an} {start_ms:g}..{end_ms:g} ms, {step_ms:g} ms/col: + {bn} louder by over 6 dB, "
            "- quieter, = within 6, blank both 40 dB under"]
    for i in range(len(centres) - 1, -1, -1):
        rows.append(f"{_hz(centres[i]):>5}|" + "".join(" " if not loud[i, k] else "+" if plus[i, k] else "-"
                                                      if minus[i, k] else "=" for k in range(d.shape[1])) + "|")
    rows.append("   ms " + _ruler(d.shape[1], step_ms, start_ms))

    def most(mask):
        spans = []
        for i in np.argsort(-mask.sum(axis=1))[:2]:
            if mask[i].any():
                k = np.flatnonzero(mask[i])
                first, last = start_ms + k[0] * step_ms, start_ms + (k[-1] + 1) * step_ms
                spans.append(f"{_hz(centres[i])} Hz {first:g}-{last:g} ms")
        return ", ".join(spans) or "none"

    rows.append(f"{bn} louder in {int(plus.sum())} of {int(loud.sum())} cells (most: {most(plus)}); quieter in "
                f"{int(minus.sum())} (most: {most(minus)})")
    ends = [np.flatnonzero(g.max(axis=0) > -40) for g in (a, b)]
    if all(len(e) for e in ends):
        rows.append(f"last column over -40 dB: {an} {start_ms + (ends[0][-1] + 1) * step_ms:g} ms, "
                    f"{bn} {start_ms + (ends[1][-1] + 1) * step_ms:g} ms")
    return rows


def _onsets(heard, step_ms, cols):
    """'^' under the columns where the level rises 10 dB within 30 ms of a dip: notes, steps, a laugh's bursts."""
    db = heard.db
    rise = {t for t in range(3, len(db)) if db[t] > -30 and db[t] - db[t - 3:t].min() >= 10}
    hits = [0] + [t for t in sorted(rise) if t - 1 not in rise]  # the first window of each rise
    marks = sorted({int(t * 10 // step_ms) for t in hits if t * 10 < cols * step_ms})
    return "".join("^" if k in marks else " " for k in range(cols)) if len(marks) > 1 else None


def hear(sound, vs=None, *, brief=False, lines_only=False, at=None, weight=True, align="onset"):
    """The text report as data (schema tune.ear/1): `sound` and `vs` are (name, source, audio, sr, loop) tuples."""
    raw = [s for s in (vs, sound) if s is not None]
    high = min(HIGH, *(s[3] / 2 - 100 for s in raw))
    end_db = common_end_db(*((s[2], s[3]) for s in raw))
    heard = [Heard(*s[:4], loop=s[4], align=align, end_db=end_db, high=high) for s in raw]
    centres, edges = bands(high)
    report = {"schema": "tune.ear/1", "basis": BASIS, "lines": [line for h in heard for line in h.lines(high)],
              "grids": [], "not_shown": NOT_SHOWN}
    if lines_only or any(h.m["status"] != "measured" for h in heard):
        return report
    if at:
        start, length = at
        plan = [("at", start, length / COLS, COLS)]
    else:
        span = max(h.until(end_db) or 10 for h in heard)
        step = next((s for s in STEPS_MS if s * COLS >= span), STEPS_MS[-1])
        plan = [("whole", 0, step, COLS)]
        if any(h.m["attack_ms"] < 30 for h in heard) and max(h.m["active_s"] for h in heard) < 3:
            plan.insert(0, ("attack", 0, 2, 30))
        if span > 5000:
            report["lines"].append(f"whole sound at {step} ms/col: fine structure under the column, use --at START,LEN")
    for zoom, start, step, cols in plan:
        grids = [_grid(h, start / 1000, step / 1000, cols, centres, edges, weight) for h in heard]
        rows = []
        if not brief or len(heard) == 1:
            for h, g in zip(heard, grids, strict=True):
                rows += grid_text(h.name, g, centres, start, step, _f0_row(h, start, step, cols))
                if zoom == "whole" and (marks := _onsets(h, step, cols)):
                    rows.insert(-1, f"  on |{marks}|")
        if len(heard) == 2:
            rows += diff_text(grids[0], grids[1], heard[0].name, heard[1].name, centres, start, step)
        report["grids"].append({"zoom": zoom, "start_ms": start, "step_ms": step, "rows": rows})
    seam = heard[-1]
    if seam.loop and not at and len(seam.raw) > seam.sr // 10:
        n = int(0.03 * seam.sr)
        mono = _mono(seam.raw)
        wrapped = Heard("SEAM", seam.source, np.concatenate([mono[-n:], mono[:n]]), seam.sr, end_db=end_db, high=high)
        wrapped.y = np.concatenate([mono[-n:], mono[:n]])  # the wrap itself, not from an onset
        g = _grid(wrapped, 0, 0.002, 30, centres, edges, weight)
        rows = grid_text(f"SEAM of {seam.name}, last 30 ms then first 30", g, centres, -30, 2)
        report["grids"].append({"zoom": "seam", "start_ms": -30, "step_ms": 2, "rows": rows})
    return report


def text(report):
    blocks = ["\n".join(report["lines"])] + ["\n".join(g["rows"]) for g in report["grids"]]
    return "\n\n".join(blocks + [report["not_shown"]])


def load(source):
    """(audio, sr, loop, reference, label) from a review bundle (its retained audio and, if it has one, its reference
    recording as (audio, sr, file)) or from an audio file."""
    path = Path(source)
    if path.is_dir():
        from .bundles import load_bundle
        from .exports import looped

        captured = load_bundle(path)
        reference = None
        if "reference" in captured.arrays:
            about = captured.manifest["reference"]
            reference = (captured.arrays["reference"], about["sample_rate"], about.get("file") or "reference")
        label = f"{captured.manifest.get('dsl', {}).get('sound', 'sound')} (bundle {path.name[:8]})"
        return captured.audio, captured.sr, looped(captured), reference, label
    from .audio_io import read_channels, wav_loop

    audio, sr = read_channels(path)
    return audio, sr, path.suffix.lower() == ".wav" and wav_loop(path) is not None, None, str(source)
