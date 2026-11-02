"""Channel-preserving diagnostics, separate from the matching engine's normalized features."""
from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks

from .diagnostics import Capture, digest, pcm_id

ANALYZER = "inspection-1"


def samples(audio):
    y = np.asarray(audio, dtype=np.float64)
    if y.ndim == 1:
        y = y[:, None]
    if y.ndim != 2 or y.shape[1] not in (1, 2) or not np.isfinite(y).all():
        raise ValueError("inspection requires finite mono/stereo samples")
    return y


def db(value):
    return float(20 * np.log10(value)) if value > 0 else None


def band_power(audio, sr, start=0.0, end=None, band=None):
    """Windowed mean-square power summed across channels; never downmix before squaring."""
    y = samples(audio)
    end = len(y) / sr if end is None else float(end)
    if not 0 <= start <= end <= len(y) / sr + 1e-9:
        raise ValueError("query time range must lie within the audio")
    a, b = int(round(start * sr)), min(len(y), int(round(end * sr)))
    x = y[a:b]
    if not len(x):
        return 0.0
    if band is None:
        return float(np.mean(np.sum(x * x, axis=1)))
    low, high = band
    if not 0 <= low < high <= sr / 2:
        raise ValueError("frequency band must satisfy 0 <= low < high <= Nyquist")
    window = np.hanning(len(x)) if len(x) > 2 else np.ones(len(x))
    spectrum = np.abs(np.fft.rfft(x * window[:, None], axis=0)) ** 2
    weights = np.full(len(spectrum), 2.0)
    weights[0] = 1
    if len(x) % 2 == 0:
        weights[-1] = 1
    freq = np.fft.rfftfreq(len(x), 1 / sr)
    mask = (freq >= low) & (freq <= high)
    return float(np.sum(spectrum[mask] * weights[mask, None]) / (len(x) * np.sum(window ** 2)))


def pitch_frames(audio, sr, *, fmin=60, fmax=1600, max_frames=1200):
    """Raw periodic candidates with octave alternatives. No global pitch folding or probabilities."""
    y = samples(audio)
    width = max(int(0.04 * sr), int(3 * sr / fmin))
    lagmax = int(sr / fmin)
    if not len(y) or len(y) < width + lagmax:
        return {"status": "insufficient_data", "method": "period_difference_candidates", "frames": []}
    hop = max(int(sr * 0.02), int(np.ceil(len(y) / max_frames)))
    frames = []
    for start in range(0, len(y) - width - lagmax + 1, hop):
        clip = y[start:start + width + lagmax]
        x = clip[:, int(np.argmax(np.sum(clip * clip, axis=0)))]
        energy = float(np.mean(x[:width] ** 2))
        frame = {"time": start / sr, "hz": None, "candidates": [], "periodicity_error": None,
                 "status": "unvoiced", "dominant_partial_hz": None}
        if energy < 1e-12:
            frame["status"] = "silence"
            frames.append(frame)
            continue
        win = x[:width] * np.hanning(width)
        mag = np.abs(np.fft.rfft(win))
        index = int(np.argmax(mag[1:]) + 1)
        frame["dominant_partial_hz"] = index * sr / width
        sums = np.r_[0, np.cumsum(x * x)]
        nfft = 1 << int(np.ceil(np.log2(len(x) + width)))
        acf = np.fft.irfft(np.fft.rfft(x, nfft) * np.conj(np.fft.rfft(x[:width], nfft)), nfft)[:lagmax + 1]
        diff = sums[width] + sums[width:width + lagmax + 1] - sums[:lagmax + 1] - 2 * acf
        diff[0] = 0
        cmnd = np.maximum(0, diff) * np.arange(len(diff)) / np.maximum(np.cumsum(np.maximum(0, diff)), 1e-20)
        cmnd[0] = 1
        first = max(2, int(sr / min(fmax, sr / 2)))
        candidates = find_peaks(-cmnd)[0]
        candidates = candidates[(candidates >= first) & (cmnd[candidates] < 0.2)]
        if len(candidates):
            best_error = float(np.min(cmnd[candidates]))
            good = candidates[cmnd[candidates] <= best_error + 0.025]
            chosen = int(good[0])
            left, center, right = cmnd[chosen - 1:chosen + 2] if chosen < lagmax else (1, 1, 1)
            den = left - 2 * center + right
            offset = 0.5 * (left - right) / den if den else 0
            estimate = sr / (chosen + offset)
            frame["candidates"] = [float(sr / lag) for lag in candidates[:8]]
            frame["periodicity_error"] = float(cmnd[chosen])
            fundamental_bin = int(round(estimate * width / sr))
            fundamental = float(np.max(mag[max(0, fundamental_bin - 1):fundamental_bin + 2]))
            # A missing/very weak fundamental or discordant strong peaks needs interpretation, not certainty.
            peaks = find_peaks(mag, height=float(mag.max()) * 0.18)[0]
            harmonic = all(abs((p * sr / width) / estimate - round((p * sr / width) / estimate)) < 0.1
                           for p in peaks)
            ambiguous = fundamental < float(mag.max()) * 0.12 or not harmonic or cmnd[chosen] > 0.1
            frame.update(hz=None if ambiguous else float(estimate), status="ambiguous" if ambiguous else "estimated")
        frames.append(frame)
    return {"status": "measured", "method": "period_difference_candidates", "fmin": fmin, "fmax": fmax,
            "hop_seconds": hop / sr, "window_seconds": width / sr, "cleanup": "none", "frames": frames}


def inspect_audio(audio, sr: int, *, start=0.0, end=None, band=None, pitch=True):
    if not isinstance(sr, int) or not 1000 <= sr <= 192000:
        raise ValueError("sample rate must be 1000..192000 Hz")
    y = samples(audio)
    duration = len(y) / sr
    if duration > 180:
        raise ValueError("inspection duration limit is 180 seconds")
    powers = band_power(y, sr, start, end, band)
    levels = []
    for channel in y.T:
        peak = float(np.max(np.abs(channel))) if len(channel) else 0
        rms = float(np.sqrt(np.mean(channel * channel))) if len(channel) else 0
        levels.append({"peak": peak, "peak_dbfs": db(peak), "rms": rms, "rms_dbfs": db(rms),
                       "clipped_samples": int(np.sum(np.abs(channel) > 1))})
    summary = {"analyzer": ANALYZER, "status": "empty" if not len(y) else "silence" if not y.any() else "measured",
               "sample_rate": sr, "frames": len(y), "channels": y.shape[1], "duration": duration,
               "pcm_id": pcm_id(np.asarray(audio), sr), "levels": levels,
               "query": {"start": start, "end": duration if end is None else end, "band": band,
                         "channel_sum_power": powers},
               "fundamental": pitch_frames(y, sr) if pitch else {"status": "not_requested", "frames": []}}
    if len(y) > 1:
        summary["loop_boundary"] = {"sample_step": np.abs(y[0] - y[-1]).tolist(),
                                    "interpretation": "boundary step, not an audibility verdict"}
    summary["analysis_id"] = digest(summary)
    return summary


def _project_layer(captured, node, part):
    """Project a pre-bus buffer through placement/loop/fade timing, excluding shared DSP."""
    from .render import _fold_loop
    from .score import _pan
    nodes = {n["id"]: n for n in captured.manifest["nodes"]}
    y = samples(captured.arrays[part["audio"]])
    offset = part["start"]
    if node["kind"] == "score" and y.shape[1] == 1:
        y = y * _pan(part["params"]["pan"])
    while True:
        size = max(node.get("input_length", len(captured.arrays[node["audio"]])), offset + len(y))
        placed = np.zeros((size, y.shape[1]))
        placed[offset:offset + len(y)] = y
        length = len(captured.arrays[node["audio"]])
        if node["kind"] == "voice" and node["params"].get("loop"):
            crossfade = int(node["params"]["loop"] * captured.sr)
            placed = np.pad(placed, ((0, max(0, length + crossfade - len(placed))), (0, 0)))
            y = np.column_stack([_fold_loop(ch, crossfade, length) for ch in placed.T])
        elif node["kind"] == "score" and node.get("loop"):
            y = np.zeros((length, placed.shape[1]))
            for begin in range(0, len(placed), length):
                chunk = placed[begin:begin + length]
                y[:len(chunk)] += chunk
        else:
            y = np.pad(placed[:length], ((0, max(0, length - len(placed))), (0, 0)))
            fade = node["params"].get("fade_samples", 0) if node["kind"] == "cue" else \
                min(int(0.004 * captured.sr), length) if node["kind"] == "voice" else 0
            if fade:
                y[-fade:] *= np.linspace(1, 0, fade)[:, None] ** (2 if node["kind"] == "cue" else 1)
        if node["parent"] is None:
            return y
        parent = nodes[node["parent"]]
        link = next((p for p in parent["parts"] if p["child"] == node["id"]), None)
        offset = link["start"] if link else 0
        if link and y.shape[1] == 1:
            y = y * _pan(link["params"]["pan"])
        node = parent


def inspect_capture(captured: Capture, *, start=0.0, end=None, band=None, pitch=True, node_id=None):
    result = inspect_audio(captured.audio, captured.sr, start=start, end=end, band=band, pitch=pitch)
    result.update(revision=captured.manifest["revision"], source_id=captured.manifest["source_id"],
                  planned=captured.manifest["source"], replay=captured.manifest["replay"],
                  reference=captured.manifest.get("reference"))
    nodes = {n["id"]: n for n in captured.manifest["nodes"]}
    chosen = node_id or captured.manifest["root"]
    if chosen not in nodes:
        raise ValueError("unknown inspection stage")
    if nodes[chosen]["kind"] == "cue":
        chosen = nodes[chosen]["child"]
    ranking, catalog = [], []
    for node in nodes.values():
        for part in node["parts"]:
            entry = {"id": part["id"], "label": part["label"], "stage": part["stage"],
                     "node": node["id"], "event": part["event"],
                     "source": part.get("dsl_origin") or part.get("origin"),
                     "parameters": part["params"], "seed": part["seed"],
                     "time_coordinate": "artifact time after placement/loop/fade; shared bus processing excluded"}
            catalog.append(entry)
            if node["id"] == chosen:
                y = _project_layer(captured, node, part)
                power = band_power(y, captured.sr, start, end, band)
                ranking.append(entry | {"power": power})
    result["layers"] = sorted(ranking, key=lambda item: item["power"], reverse=True)
    result["layer_catalog"] = catalog
    result["selected_stage"] = chosen
    result["attribution"] = "windowed layer energy before parent bus; shared effects/cancellation are not additive"
    result["stages"] = [{"id": n["id"], "kind": n["kind"], "track": n.get("track", {}).get("name"),
                         "factors": n["factors"],
                         "shared": [key for key in ("air", "room", "space", "drive", "crush", "bits",
                                                    "lowpass", "hall", "echo", "effects")
                                    if n["params"].get(key)]} for n in captured.manifest["nodes"]]
    result["analysis_id"] = digest({k: v for k, v in result.items() if k != "analysis_id"})
    return result
