"""Measure a recording the way the synth thinks: pitch contour, loudness, spectral envelope.

Used to match creatures to reference samples (see designer.py). numpy/scipy only.
"""
import numpy as np
from scipy.signal import medfilt, welch


def trim(y: np.ndarray, sr: int, floor_db: float = 35) -> np.ndarray:
    """Cut leading/trailing silence (anything `floor_db` under the loudest 10 ms)."""
    w = max(sr // 100, 1)
    rms = np.array([np.sqrt(np.mean(y[i:i + w] ** 2)) for i in range(0, max(len(y) - w, 1), w)])
    db = 20 * np.log10(rms + 1e-9)
    on = np.flatnonzero(db > db.max() - floor_db)
    return y[on[0] * w:(on[-1] + 1) * w] if len(on) else y


def yin(y: np.ndarray, sr: int, fmin: float = 60, fmax: float = 1600, frame: float = 0.03, hop: float = 0.005,
        threshold: float = 0.2) -> tuple[np.ndarray, np.ndarray]:
    """f0 per hop (Hz, 0 = unvoiced) and aperiodicity (0 = perfectly periodic), YIN-style."""
    W, H = int(frame * sr), int(hop * sr)
    tmin, tmax = int(sr / fmax), int(sr / fmin)
    starts = range(0, len(y) - W - tmax, H)
    energy = np.array([np.sum(y[i:i + W] ** 2) for i in starts])
    gate = (energy.max() if len(energy) else 0) * 1e-4          # 40 dB under the loudest frame: silence
    f0, aper = [], []
    for i, e in zip(starts, energy, strict=True):
        if e <= gate:
            f0.append(0.0)
            aper.append(1.0)
            continue
        x = y[i:i + W + tmax]
        head = x[:W]
        cum = np.concatenate([[0], np.cumsum(x ** 2)])
        n = 1 << int(np.ceil(np.log2(len(x) + W)))
        acf = np.fft.irfft(np.fft.rfft(x, n) * np.conj(np.fft.rfft(head, n)), n)[:tmax + 1]
        d = np.sum(head ** 2) + cum[W:W + tmax + 1] - cum[:tmax + 1] - 2 * acf
        d[0] = 0
        cmnd = d * np.arange(len(d)) / np.maximum(np.cumsum(d), 1e-12)
        cmnd[0] = 1
        cand = np.flatnonzero(cmnd[tmin:] < threshold)
        if len(cand):
            t = tmin + cand[0]
            while t + 1 < len(cmnd) and cmnd[t + 1] < cmnd[t]:
                t += 1
            a, b, c = cmnd[t - 1], cmnd[t], cmnd[min(t + 1, len(cmnd) - 1)]
            shift = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) else 0.0
            f0.append(sr / (t + shift))
            aper.append(float(b))
        else:
            f0.append(0.0)
            aper.append(float(np.min(cmnd[tmin:])))
    return np.array(f0), np.array(aper)


def clean_f0(f0: np.ndarray) -> np.ndarray:
    """Fold octave/fifth errors toward the track's centre, median-filter, smooth."""
    voiced = f0 > 0
    if voiced.sum() < 5:
        return f0
    st = np.full(len(f0), np.nan)
    st[voiced] = 12 * np.log2(f0[voiced])
    ref = np.median(st[voiced])
    for k in np.flatnonzero(voiced):
        options = st[k] + np.array([0, -12, 12, -7.02, 7.02, -19.02])
        st[k] = options[np.argmin(np.abs(options - ref) + np.array([0, 1, 1, 1.5, 1.5, 2]))]
    filled = np.where(voiced, st, np.interp(np.arange(len(f0)), np.flatnonzero(voiced), st[voiced]))
    med = medfilt(filled, min(11, len(f0) - 1 + len(f0) % 2))  # odd, and no longer than the track (no zero pad)
    bad = voiced & (np.abs(st - med) > 2.5)
    st[bad] = med[bad]
    sm = np.convolve(np.pad(np.where(voiced, st, med), 3, mode="edge"), np.ones(7) / 7, mode="valid")
    out = np.zeros(len(f0))
    out[voiced] = 2 ** (sm[voiced] / 12)
    return out


def segments(f0: np.ndarray, min_gap: int = 6) -> int:
    """Voiced stretches longer than 40 ms, after closing gaps shorter than `min_gap` hops."""
    v = (f0 > 0).astype(int)
    idx = np.flatnonzero(v)
    for a, b in zip(idx, idx[1:], strict=False):
        if 1 < b - a <= min_gap:
            v[a:b] = 1
    edges = np.diff(np.concatenate([[0], v, [0]]))
    return int(np.sum((np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1)) > 8))


def band_edges(bands: int = 40, fmax: float = 8000) -> np.ndarray:
    """The envelope's band edges in Hz: a mel-like scale from 100 Hz to `fmax`."""
    return 700 * (10 ** np.linspace(np.log10(1 + 100 / 700), np.log10(1 + fmax / 700), bands + 1) - 1)


def envelope_db(y: np.ndarray, sr: int, bands: int = 40, fmax: float = 8000) -> np.ndarray:
    """Long-term spectral envelope on a mel-like scale, dB under its peak."""
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    freqs = np.fft.rfftfreq(len(y), 1 / sr)
    edges = band_edges(bands, fmax)
    e = np.array([spec[(freqs >= lo) & (freqs < hi)].mean() + 1e-20 if np.any((freqs >= lo) & (freqs < hi)) else 1e-20
                  for lo, hi in zip(edges, edges[1:], strict=False)])
    db = 10 * np.log10(e)
    return db - db.max()


def features(y: np.ndarray, sr: int, fmax: float = 8000) -> dict:
    """What matching compares: pitch and loudness contours, envelope, duration, noisiness, syllables."""
    y = trim(np.asarray(y, dtype=np.float64), sr)
    f0, aper = yin(y, sr)
    f0 = clean_f0(f0)
    voiced = f0 > 0
    t = np.linspace(0, 1, 16)
    pos = np.linspace(0, 1, max(len(f0), 2))
    if voiced.sum() > 3:
        pitch = np.interp(t, pos[voiced], 12 * np.log2(f0[voiced] / 100))
    else:
        pitch = np.zeros(16)
    w = max(sr // 100, 1)
    rms = np.array([np.sqrt(np.mean(y[i:i + w] ** 2)) for i in range(0, max(len(y) - w, 1), w)])
    loud = np.interp(t, np.linspace(0, 1, len(rms)), 20 * np.log10(rms / (rms.max() + 1e-12) + 1e-6))
    return {"dur": len(y) / sr, "pitch_st": pitch, "loud_db": loud, "env_db": envelope_db(y, sr, fmax=fmax),
            "aper": float(np.median(aper[voiced])) if voiced.any() else 1.0,
            "voiced": float(voiced.mean()) if len(voiced) else 0.0,  # under one yin frame: no voicing
            "segments": segments(f0)}


def distance(a: dict, b: dict) -> float:
    """Weighted mismatch between two feature sets (0 = identical)."""
    pitch = np.mean(np.abs(a["pitch_st"] - b["pitch_st"])) if a["voiced"] > 0.2 and b["voiced"] > 0.2 else 0.0
    return (1.0 * pitch                                               # semitones
            + 0.15 * np.mean(np.abs(a["loud_db"] - b["loud_db"]))    # dB
            + 0.25 * np.mean(np.abs(a["env_db"] - b["env_db"]))      # dB
            + 4.0 * abs(np.log(a["dur"] / b["dur"]))
            + 3.0 * abs(a["aper"] - b["aper"]) + 3.0 * abs(a["voiced"] - b["voiced"])
            + 2.0 * abs(a["segments"] - b["segments"]))


BASIS = ("mono (channels averaged); each signal from its own onset, its first 10 ms within 35 dB of its loudest 10 ms, "
         "to its end: the last 10 ms over end_db (-40 dB, or 6 dB over the noisier floor); levels in dB under that "
         "peak; spectra of the active part, in the band both sample rates hold, envelope bands more than 40 dB under "
         "the strongest counted at -40")


def _levels(y: np.ndarray, sr: int) -> np.ndarray:
    """Mono `y` in 10 ms windows, dB under the loudest (empty when silent)."""
    w = max(sr // 100, 1)
    n = len(y) // w
    power = (y[:n * w].reshape(n, w) ** 2).mean(axis=1) if n else np.zeros(1)
    return 10 * np.log10(power / power.max() + 1e-12) if power.max() > 0 else np.zeros(0)


def _mono(y) -> np.ndarray:
    y = np.asarray(y, dtype=np.float64)
    return y if y.ndim == 1 else y.mean(axis=1)


def common_end_db(*signals) -> float:
    """One end for signals measured together, (y, sr) each: 40 dB under each one's peak, or 6 dB over the noisiest
    floor (10th percentile of 10 ms windows), so a recording's noise does not stretch only its own length."""
    floors = [np.percentile(db, 10) if len(db) else -120 for db in (_levels(_mono(y), sr) for y, sr in signals)]
    return round(float(min(max(-40.0, max(floors) + 6), -10.0)), 1)  # a steady sound's floor is the sound: -10


def sounds_at(y: np.ndarray, sr: int, hz: float, top: float = 8000) -> bool:
    """Whether anything sounds at `hz`: the Welch spectrum of `y`'s first 3 s within 3% of `hz` comes within 30 dB
    of its loudest bin from 80 Hz to `top`. yin (60..1600 Hz) reads a ring above its range as the ring's subharmonic,
    a pitch where nothing sounds."""
    f, s = _welch_db(y, sr)
    near = np.abs(f - hz) <= max(0.03 * hz, f[1] - f[0])
    return bool(near.any() and s[near].max() >= s[(f >= 80) & (f <= top)].max() - 30)


def loudest_hz(y: np.ndarray, sr: int, top: float = 8000) -> float:
    """The loudest bin of the Welch spectrum of `y`'s first 3 s, 80 Hz to `top`: a high ring's own pitch."""
    f, s = _welch_db(y, sr)
    band = (f >= 80) & (f <= top)
    return float(f[band][np.argmax(s[band])])


def _welch_db(y, sr):
    part = y[:3 * sr]
    f, p = welch(part, sr, nperseg=min(len(part), 1 << int(np.log2(sr * 0.1))))
    return f, 10 * np.log10(p + 1e-30)


def measures(y: np.ndarray, sr: int, fmax: float = 8000, pitch: bool = True, end_db: float = -40) -> dict:
    """The numbers a sound is held against a recording with. Each is relative to the signal's own peak and onset, so
    recording gain, leading silence and sample rate do not count.

    active_s: onset to the last 10 ms over `end_db` (40 dB under the peak by default). end_60_s: to the last within
    60 dB (what an export keeps, see audio_io.trim_tail), or None when the noise floor (10th percentile of 10 ms
    windows) is not 6 dB under -60 or the file ends first; end_60_note then says which.
    attack_ms: onset to the first 1 ms within 3 dB of the loudest 1 ms of the first 250 ms (a first note's attack,
    not a later climax). centroid_hz: of the active part, 100 Hz..fmax.
    env_db: its envelope_db; loud_db: its loudness at 16 points of its own length. f0: the voiced pitch's median and
    10th..90th percentile range, or why not ("unvoiced" under 20% voiced, "unreliable" over 0.5 aperiodicity,
    "skipped" past 20 s). When nothing sounds at the tracked pitch (see sounds_at), yin read a subharmonic: "ring"
    with median_hz the loudest spectral peak when that is above its 1600 Hz range, else "subharmonic" (no pitch)."""
    y = np.asarray(y, dtype=np.float64)
    base = {"channels": 1 if y.ndim == 1 else y.shape[1], "sample_rate": sr,
            "clipped": int(np.sum(np.abs(y) >= 32767 / 32768))}
    y = _mono(y)
    w = max(sr // 100, 1)
    db = _levels(y, sr)
    if not len(db):
        return base | {"status": "silent"}
    on = int(np.argmax(db > -35))
    end40, end60 = (int(np.flatnonzero(db > floor)[-1]) + 1 for floor in (end_db, -60))
    noise = float(np.percentile(db, 10))
    active = y[on * w:end40 * w]
    v = max(sr // 1000, 1)
    fine = (active[:len(active) // v * v].reshape(-1, v) ** 2).mean(axis=1)[:250]
    fine = 10 * np.log10(fine / fine.max() + 1e-12)
    top = min(fmax, sr / 2 - 100)
    spectrum = np.abs(np.fft.rfft(active * np.hanning(len(active)))) ** 2
    freqs = np.fft.rfftfreq(len(active), 1 / sr)
    band = (freqs >= 100) & (freqs <= top)
    weight = spectrum[band].sum()
    loud = db[on:end40]
    if not pitch:
        f0 = {"status": "not_requested"}
    elif len(active) > 20 * sr:
        f0 = {"status": "skipped", "reason": "active part over 20 s"}
    else:
        track, aper = yin(active, sr)
        track = clean_f0(track)
        voiced = track > 0
        share = float(voiced.mean()) if len(track) else 0.0
        if share < 0.2:
            f0 = {"status": "unvoiced", "voiced": round(share, 2)}
        else:
            hz = track[voiced]
            median = float(np.median(hz))
            st = 12 * np.log2(hz / median)
            rough = float(np.median(aper[voiced]))
            f0 = {"status": "unreliable" if rough > 0.5 else "measured", "median_hz": round(median, 1),
                  "range_st": [round(float(np.percentile(st, q)), 1) for q in (10, 90)], "voiced": round(share, 2),
                  "aperiodicity": round(rough, 2), "segments": segments(track)}
            if not sounds_at(active, sr, median, top):  # yin's subharmonic: the ring above 1600 Hz is the pitch
                ring = loudest_hz(active, sr, top)
                f0 = {"status": "ring" if ring >= 1550 else "subharmonic", "tracked_hz": round(median, 1),
                      "voiced": round(share, 2)} | ({"median_hz": round(ring, 1)} if ring >= 1550 else {})
    note = None
    if end60 == len(db):  # the file ends first: a cut, or a floor that never lets it fall (noise_floor_db says)
        note = "still over -60 dB when the file ends"
    elif noise > -66:
        note = f"noise floor {noise:.1f} dB, within 6 dB of -60"
    return base | ({"end_60_note": note} if note else {}) | {
        "status": "measured",
        "active_s": round((end40 - on) * w / sr, 3),
        "end_60_s": None if note else round((end60 - on) * w / sr, 3),
        "noise_floor_db": round(max(noise, -120.0), 1),
        "attack_ms": round(float(np.argmax(fine > -3) - np.argmax(fine > -35)) * v / sr * 1000),
        "centroid_hz": round(float(np.sum(freqs[band] * spectrum[band]) / weight)) if weight > 0 else None,
        "env_db": envelope_db(active, sr, fmax=top),
        "loud_db": np.interp(np.linspace(0, 1, 16), np.linspace(0, 1, len(loud)), loud) if len(loud) > 1
        else np.repeat(loud, 16),
        "f0": f0,
    }


def against(reference: np.ndarray, reference_sr: int, y: np.ndarray, sr: int) -> dict:
    """`y` held against a reference recording, measure by measure: both values, the difference in the unit a
    tolerance takes (a ratio, ms, semitones or dB) and a status. Numbers aim; they never say it sounds alike."""
    top = min(8000, reference_sr / 2 - 100, sr / 2 - 100)
    end_db = common_end_db((reference, reference_sr), (y, sr))
    r, s = measures(reference, reference_sr, top, end_db=end_db), measures(y, sr, top, end_db=end_db)
    out = {"basis": BASIS, "end_db": end_db, "noise_floor_db": [r.get("noise_floor_db"), s.get("noise_floor_db")],
           "clipped": [r["clipped"], s["clipped"]], "measures": {}}
    if "silent" in (r["status"], s["status"]):
        which = "reference" if r["status"] == "silent" else "sound"
        return out | {"status": "not_measurable", "reason": "silent " + which}
    m = out["measures"]

    def pair(key, **difference):
        a, b = r[key], s[key]
        if a is None or b is None:
            reason = "no energy in the band"
            if key == "end_60_s":
                reason = "; ".join(f"{who} {x['end_60_note']}" for who, x in (("reference", r), ("sound", s))
                                   if x[key] is None)
            m[key] = {"reference": a, "sound": b, "status": "not_measurable", "reason": reason}
        else:
            m[key] = {"reference": a, "sound": b, **{k: f(a, b) for k, f in difference.items()}, "status": "measured"}

    pair("active_s", ratio=lambda a, b: round(b / a, 3))
    pair("end_60_s", ratio=lambda a, b: round(b / a, 3))
    pair("attack_ms", delta=lambda a, b: b - a)
    pair("centroid_hz", semitones=lambda a, b: round(12 * float(np.log2(b / a)), 1))
    a, b = r["f0"], s["f0"]
    if {a["status"], b["status"]} <= {"measured", "unreliable", "ring"}:  # a high ring is held by its own Hz
        m["f0_hz"] = {"reference": a["median_hz"], "sound": b["median_hz"],
                      "semitones": round(12 * float(np.log2(b["median_hz"] / a["median_hz"])), 1),
                      "range_st": [a.get("range_st"), b.get("range_st")],
                      "status": "unreliable" if "unreliable" in (a["status"], b["status"]) else "measured"}
        if "ring" in (a["status"], b["status"]):
            m["f0_hz"]["ring"] = [a["status"] == "ring", b["status"] == "ring"]
    else:  # both unpitched agree; one pitched and one not differ; a skipped part says nothing
        states = {a["status"], b["status"]}
        unpitched = {"unvoiced", "subharmonic"}
        m["f0_hz"] = {"reference": a.get("median_hz", a["status"]), "sound": b.get("median_hz", b["status"]),
                      "voiced": [a.get("voiced"), b.get("voiced")],
                      "status": "unvoiced" if states <= unpitched else "voicing_differs"
                      if states <= unpitched | {"measured", "unreliable", "ring"} else "skipped"}
    d = np.maximum(s["env_db"], -40) - np.maximum(r["env_db"], -40)  # a recording's noise fills the deep valleys
    edges = band_edges(len(d), top)
    k = int(np.argmax(np.abs(d)))
    m["env_db"] = {"mean_abs_db": round(float(np.mean(np.abs(d))), 1), "louder_bands": int(np.sum(d > 3)),
                   "quieter_bands": int(np.sum(d < -3)), "of_bands": len(d),
                   "largest": {"hz": [round(float(edges[k])), round(float(edges[k + 1]))], "db": round(float(d[k]), 1)},
                   "status": "measured"}
    m["loud_db"] = {"mean_abs_db": round(float(np.mean(np.abs(s["loud_db"] - r["loud_db"]))), 1), "status": "measured"}
    return out | {"status": "measured"}
