"""Build the bark templates (src/tare/tools/tune/speech/data/barks.npz) from CC0 recordings of real voices.

Each recording is analysed once with the WORLD vocoder (pip install pyworld; development only, it never runs in a
game): pitch every 5 ms, the spectral envelope (kept as 32 mel-spaced bands, dB) and the aperiodicity (5 bands).
At run time tare.tools.tune.speech.vocoder rebuilds the sound with its own deterministic synthesis, moved to each
character's pitch and vocal tract. The recordings themselves are kept too (barks_audio.npz, 24 kHz): a bark that
moves little is played from its recording like tape, which by ear sounds like the recording (the vocoder does not).

Sources (all CC0; the recordings are not in the repository):
  OpenGameArt  "Voice Clip Pack - Male Adventurer RPG"   (oga-adventurer)
               "Female RPG Voice Starter Pack" by Cici Fyre, three voices (oga-female1..3)
               "Male Grunt/Yelling sounds", three voices (oga-yell1..3; CC0 / OGA-BY dual licence, used as CC0)
  Freesound    CC0 clips, by sound id (laughs, sighs, gasps, hums, cheers, pain grunts...)

    python tools/build_barks.py --freesound DIR --oga DIR           # the templates (barks.npz)
    python tools/build_barks.py --freesound DIR --oga DIR --audio   # the recordings, cut as the templates were
DIR for Freesound holds <id>.mp3 (any sub-folder); DIR for OpenGameArt holds the unzipped packs.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from tare.tools.tune.speech.vocoder import (  # noqa: E402
    AP_BANDS,
    AUDIO,
    AUDIO_SR,
    BANDS,
    DATA,
    ENV_FLOOR,
    FRAME,
    encode,
)

SR = 48_000
MAX_SECONDS = 3.0
ADVENTURER = "RPG Male Adventurer"
FEMALE = "RPG Voice Starter Pack/Type {}"
YELLS = "yelling sounds"

# kind -> [(source, file or id, voice, tract)]: voice tags let a style prefer a kind of performer
M, F, CUTE = 1.0, 1.15, 1.27


def _oga_adv(names, kind_voice="adventurer"):
    return [("oga", f"{ADVENTURER}/{n}.wav", kind_voice, M) for n in names]


def _oga_fem(names):
    out = []
    for t, tract, voice in ((1, CUTE, "cute"), (2, F, "female"), (3, 1.1, "mature")):
        out += [("oga", f"{FEMALE.format(t)}/{n}.wav", voice, tract) for n in names]
    return out


def _fs(ids, voice, tract):
    return [("freesound", str(i), voice, tract) for i in ids]


MANIFEST = {
    "attack": _oga_adv([f"attack{i}" for i in range(9)]) + _oga_fem(["attack1", "attack2", "attack3"])
    + [("oga", f"{YELLS}/1yell{i}.wav", "yell", M) for i in (6, 7, 8, 9, 15)]
    + [("oga", f"{YELLS}/3grunt{i}.wav", "yell", M) for i in (1, 3, 4)]
    + _fs([464485, 343950], "male", M) + _fs([242622, 242623], "female", F),
    "attack_big": _oga_adv([f"attackbig{i}" for i in range(6)])
    + [("oga", f"{YELLS}/{n}.wav", "yell", M) for n in ("2yell3", "2yell8", "2yell10", "1yell12")],
    "hurt": _oga_adv([f"hurt{i}" for i in range(7)]) + _oga_fem(["damaged1", "damaged2", "damaged3"])
    + _fs([413186, 719053, 790832, 849029], "male", M) + _fs([203976], "female", F),
    "hurt_big": _fs([670857, 667697, 863709], "male", M) + _fs([232469], "female", F)
    + [("oga", f"{YELLS}/{n}.wav", "yell", M) for n in ("1yell10", "1yell3")],
    "death": _oga_adv(["death0", "death1"]) + _fs([396801, 345456, 432057, 432058, 691754], "male", M)
    + [("oga", f"{YELLS}/{n}.wav", "yell", M) for n in ("3yell2", "3yell9", "2yell11")] + _fs([222545], "female", F),
    "jump": _oga_adv(["jump0", "jump1", "jump2", "jump3"]) + _oga_fem(["jump1", "jump2", "jump3"])
    + _fs([808213, 808215, 808216, 680314, 422868, 580968], "male", M),
    "tired": _fs([422342, 516696], "male", M),
    "laugh": _fs([529818, 720133, 536811, 166141, 800973], "male", M)
    + _fs([93775, 433921, 343942, 343941, 241518, 241529], "female", F),
    "giggle": _fs([351170, 343991, 235168, 252218, 235165, 235166, 235167, 343992, 252234], "female", CUTE),
    "chuckle": _fs([458101, 344066, 234950], "male", M) + _fs([687262, 785089], "female", F),
    "sigh": _fs([449449, 449526, 252222, 275055], "male", M) + _fs([403936, 403937, 673671, 449478], "female", F),
    "gasp": _fs([536757, 677888, 253776], "male", M) + _fs([740310, 812418, 686364, 826714], "female", F),
    "surprise": _fs([801180, 504654], "male", M) + _fs([242677, 333412], "female", F),
    "hmm": _fs([394231, 165011, 445934, 445872, 801415], "male", M) + _fs([170768, 429923], "female", F),
    "huh": _fs([166129, 19262], "male", M) + _fs([170768], "female", F),
    "yes": _oga_adv(["yes0", "yes1"]) + _fs([340363], "male", M),
    "no": _oga_adv(["no0", "no1"]),
    "cheer": _oga_adv(["victory0", "victory1"]) + _fs([557125, 384981], "male", M)
    + _fs([235053, 235054, 235083, 235085, 241487, 563845, 801291, 468898], "female", F) + _fs([620397], "cute", CUTE),
    "relief": _fs([801147], "female", F) + _oga_fem(["healed1", "healed2", "healed3"]),
    "angry": _fs([691913], "male", M) + _fs([699945, 495298, 495297], "female", F),
}


def load(path: Path) -> np.ndarray:
    import soundfile as sf
    from scipy.signal import resample_poly
    y, sr = sf.read(str(path), always_2d=True)
    y = y.mean(axis=1)
    if sr != SR:
        from math import gcd
        g = gcd(SR, sr)
        y = resample_poly(y, SR // g, sr // g)
    y = y / (np.abs(y).max() + 1e-12)
    n = int(0.005 * SR)
    e = np.array([np.sqrt(np.mean(y[i:i + n] ** 2)) for i in range(0, len(y) - n, n)])
    on = np.flatnonzero(20 * np.log10(e / e.max() + 1e-9) > -40)
    y = y[max(on[0] - 2, 0) * n: (on[-1] + 2) * n]
    return y[: int(MAX_SECONDS * SR)]


def audio(find):
    """The recordings behind barks.npz, in its order and cut exactly as they were analysed, as 16-bit at 24 kHz."""
    from math import gcd

    from scipy.signal import resample_poly
    meta = json.loads(bytes(np.load(DATA)["meta"]).decode())
    clips, out = [], []
    g = gcd(AUDIO_SR, SR)
    for m in meta:
        y = resample_poly(load(find(m["source"], m["ref"])), AUDIO_SR // g, SR // g)
        out.append(dict(start=sum(len(c) for c in clips), samples=len(y)))
        clips.append(np.round(np.clip(y / (np.abs(y).max() + 1e-12) * 0.99, -1, 1) * 32767).astype(np.int16))
    np.savez_compressed(AUDIO, audio=np.concatenate(clips), meta=np.frombuffer(json.dumps(out).encode(), np.uint8))
    print(f"{len(clips)} recordings, {sum(len(c) for c in clips) / AUDIO_SR:.0f} s -> {AUDIO} "
          f"({AUDIO.stat().st_size / 1e6:.1f} MB)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freesound", type=Path, required=True)
    ap.add_argument("--oga", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=DATA)
    ap.add_argument("--audio", action="store_true", help="store the recordings (barks_audio.npz), not the templates")
    args = ap.parse_args()
    fs_files = {p.stem: p for p in args.freesound.rglob("*.mp3")}
    oga_files = {p.relative_to(args.oga).as_posix(): p for p in args.oga.rglob("*.wav")}

    def find(source, ref):
        return fs_files.get(ref) if source == "freesound" else next(
            (p for k, p in oga_files.items() if k.endswith(ref)), None)
    if args.audio:
        return audio(find)
    import pyworld as pw
    f0s, envs, aps, meta = [], [], [], []
    for kind, items in MANIFEST.items():
        for source, ref, voice, tract in items:
            path = find(source, ref)
            if path is None:
                print("missing", source, ref)
                continue
            y = load(path)
            x = y.astype(np.float64)
            f0, t = pw.harvest(x, SR, f0_floor=60, f0_ceil=1200, frame_period=FRAME * 1000)
            sp = pw.cheaptrick(x, f0, t, SR)
            aper = pw.d4c(x, f0, t, SR)
            f, env, apb = encode(f0, sp, aper, SR)
            voiced = f[f > 0]
            meta.append(dict(kind=kind, voice=voice, tract=tract, start=sum(len(a) for a in f0s), frames=len(f),
                             pitch=round(float(np.median(voiced)), 1) if len(voiced) else 0.0,
                             source=source, ref=ref, license="CC0"))
            f0s.append(f)
            envs.append(env)
            aps.append(apb)
            print(f"{kind:10s} {voice:10s} {ref[-28:]:28s} {len(f) * FRAME:4.2f}s pitch {meta[-1]['pitch']:5.0f}")
    env = np.clip(np.round((np.concatenate(envs) - ENV_FLOOR) * 2), 0, 255).astype(np.uint8)   # 0.5 dB steps
    np.savez_compressed(args.out, f0=np.concatenate(f0s).astype(np.float16), env=env,
                        ap=np.round(np.concatenate(aps) * 255).astype(np.uint8),
                        meta=np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8))
    print(f"{len(meta)} templates, {sum(m['frames'] for m in meta) * FRAME:.0f} s -> {args.out} "
          f"({args.out.stat().st_size / 1e3:.0f} kB); {BANDS} envelope bands, {AP_BANDS} aperiodicity bands")


if __name__ == "__main__":
    main()
