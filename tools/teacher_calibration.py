"""Calibrate the formant voices against a natural teacher voice (Kokoro, pt-BR).

    pip install -e ".[teacher]"
    python tools/teacher_calibration.py render      # corpus -> teacher/corpus.{npz,json} (~2 min on CPU)
    python tools/teacher_calibration.py measure     # -> teacher/corpus_stats.json + summary table

Kokoro predicts how long each phoneme lasts (25 ms frames), which gives a free alignment.
We measure, per phone: formants of long stressed vowels (the targets, not the undershoot of
fluent speech), durations by stress, and the spectrum of the noisy part of fricatives.
The resulting numbers were A/B-tested with tools/intelligibility.py before entering
phonetics.LANG_PHONES; noisy measurements (25 ms grid) are a guide, Whisper is the judge.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.linalg import solve_toeplitz
from scipy.signal import resample_poly

OUT = Path("teacher")

# Phonetically varied game-ish sentences, deliberately NOT the intelligibility test sentences.
CORPUS = [
    "A menina abriu a janela da torre.", "O cavaleiro perdeu a espada no pântano.",
    "Minha avó faz bolo de fubá aos domingos.", "Cuidado, o chão da ponte está podre.",
    "O mago guardou o livro num baú de ferro.", "Tem um lobo branco perto do moinho.",
    "Quanto custa aquele escudo dourado?", "Vamos acampar perto do lago esta noite.",
    "O dragão dorme em cima do tesouro.", "Ninguém sabe onde fica a cidade perdida.",
    "A chuva apagou a fogueira do acampamento.", "Ele trouxe três galinhas e um porco.",
    "Você quer comprar uma poção de mana?", "O caminho até a montanha é longo e perigoso.",
    "A rainha mandou chamar o melhor arqueiro.", "Os goblins roubaram o queijo do mercador.",
    "Que barulho estranho vem da caverna!", "O velho pescador conhece todas as ilhas.",
    "Preciso de lenha para aquecer a casa.", "A ferrugem destruiu o portão do castelo.",
    "Já vi muitos fantasmas nesta floresta.", "Meu irmão foi viajar para o deserto.",
    "As estrelas brilham sobre o mar calmo.", "Onde você escondeu a chave do cofre?",
    "O sapo pulou na lagoa e sumiu.", "Hoje a feira está cheia de gente.",
    "A bruxa preparou um chá de ervas amargas.", "O ladrão fugiu pelo telhado vizinho.",
    "Seja bem-vindo ao reino do norte.", "A guarda real protege o palácio dia e noite.",
    "Esse anel tem um poder muito antigo.", "O lenhador cortou a árvore com um machado.",
    "Por favor, me ajude a carregar estas caixas.", "O vento frio sopra das montanhas.",
    "A princesa escreveu uma carta secreta.", "Descanse um pouco antes da batalha.",
    "O ferreiro afiou a lâmina do machado.", "Quem tocou o sino da igreja?",
    "As abelhas fazem mel na colmeia.", "O navio chegou ao porto ao amanhecer.",
    "Meu cavalo está cansado e com fome.", "A tempestade derrubou a cerca do sítio.",
    "Encontrei uma moeda de ouro no rio.", "O padeiro vende pão quente e biscoitos.",
    "Não acorde o gigante que está dormindo.", "A coruja piou três vezes na escuridão.",
    "Os viajantes pararam para beber água.", "Junte vinte cogumelos vermelhos.",
    "A estrada para a capital está fechada.", "Olhe! Um arco-íris depois da chuva.",
    "Sua missão é levar o mapa ao capitão.", "O ninho do pássaro caiu da árvore.",
    "Quem chegar primeiro ganha o prêmio.", "A lua cheia ilumina o cemitério.",
    "Vou trocar minha armadura por um escudo.", "Escute o canto dos grilos lá fora.",
    "Sinto cheiro de fumaça na cozinha.", "Ela desenhou um jacaré na parede.",
    "O professor ensinou magia ao aprendiz.", "Você já ouviu falar do lago encantado?",
]


def render(voices=("pm_alex", "pf_dora")):
    from build_speech import kokoro
    pipe = kokoro("pt")
    OUT.mkdir(exist_ok=True)
    items, audio = [], {}
    for voice in voices:
        for i, text in enumerate(CORPUS):
            for k, r in enumerate(pipe(text, voice=voice)):
                key = f"{voice}__{i}__{k}"
                audio[key] = r.audio.numpy().astype(np.float32)
                items.append({"key": key, "voice": voice, "text": text, "phonemes": r.phonemes,
                              "dur": [int(d) for d in r.pred_dur.tolist()]})
    np.savez_compressed(OUT / "corpus.npz", **audio)
    (OUT / "corpus.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(items)} utterances, {sum(len(a) for a in audio.values()) / 24000 / 60:.1f} min")


SR, HOP = 24_000, 600          # Kokoro: 24 kHz audio, durations in 25 ms frames
TILDE, PRIMARY, SECONDARY = "̃", "ˈ", "ˌ"
TO_OURS = {  # Kokoro/misaki pt-BR token -> our symbol
    "a": "a", "æ": "6", "ɐ": "6", "e": "e", "ɛ": "E", "i": "i", "y": "I", "o": "o", "ɔ": "O", "u": "u",
    "ʊ": "U", "ə": "@", "A": "e", "p": "p", "b": "b", "t": "t", "d": "d", "k": "k", "ɡ": "g", "f": "f",
    "v": "v", "s": "s", "z": "z", "ʃ": "S", "ʒ": "Z", "ʧ": "tS", "ʤ": "dZ", "m": "m", "n": "n", "ɲ": "J",
    "ŋ": "N", "l": "l", "ʎ": "L", "ɾ": "r", "x": "R", "w": "w", "j": "j",
}
VOWELS = set("a6eEiIoOuU@")


def units(phonemes: str, dur: list[int]):
    """[(symbol, start_sample, end_sample, stress, nasal, word_final)] for one utterance."""
    frames = np.cumsum([0] + dur)               # dur[0] is BOS
    out, i, n = [], 0, len(phonemes)
    while i < n:
        ch = phonemes[i]
        start = frames[i + 1]                  # token i occupies frames[i+1]..frames[i+2]
        stress = 0
        if ch in (PRIMARY, SECONDARY):
            stress = 2 if ch == PRIMARY else 1
            i += 1
            if i >= n:
                break
            ch = phonemes[i]
        end = frames[i + 2]
        nasal = i + 1 < n and phonemes[i + 1] == TILDE
        if nasal:
            end = frames[i + 3]
            i += 1
        if ch in TO_OURS:
            sym = TO_OURS[ch]
            nxt = phonemes[i + 1] if i + 1 < n else " "
            if nasal and sym in VOWELS:
                sym = {"a": "6~", "6": "6~", "e": "e~", "E": "e~", "i": "i~", "o": "o~", "O": "o~",
                       "u": "u~", "U": "w~"}.get(sym, sym)
            out.append((sym, start * HOP, end * HOP, stress, nasal, nxt in " .,!?;:"))
        i += 1
    return out


def formants(x, sr=SR, n=3):
    y = resample_poly(x, 1, 2)                 # 12 kHz: enough for F1..F3 of an adult
    fs = sr // 2
    order, W, H = 14, int(0.025 * fs), int(0.01 * fs)
    res = []
    for i in range(0, len(y) - W, H):
        f = np.append(y[i], y[i + 1:i + W] - 0.97 * y[i:i + W - 1]) * np.hamming(W)
        r = np.correlate(f, f, "full")[W - 1:W + order]
        if r[0] < 1e-9:
            continue
        a = solve_toeplitz(r[:order], -r[1:order + 1])
        roots = np.roots(np.concatenate([[1], a]))
        roots = roots[np.imag(roots) > 0]
        fr = np.angle(roots) * fs / (2 * np.pi)
        bw = -np.log(np.abs(roots)) * fs / np.pi
        cand = sorted(fr[(fr > 200) & (bw < 450)])[:n]
        if len(cand) == n:
            res.append(cand)
    return np.median(res, axis=0) if len(res) >= 2 else None


def rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)


def spectral_peak(x, sr=SR):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)), 4096)) ** 2
    f = np.fft.rfftfreq(4096, 1 / sr)
    sm = np.convolve(spec, np.ones(31) / 31, mode="same")
    band = (f > 1000) & (f < 11000)
    centroid = float(np.sum(f[band] * spec[band]) / np.sum(spec[band]))
    return float(f[band][np.argmax(sm[band])]), centroid


def measure(corpus=OUT / "corpus"):
    items = json.load(open(f"{corpus}.json", encoding="utf-8"))
    audio = np.load(f"{corpus}.npz")
    stats = defaultdict(lambda: defaultdict(list))
    for it in items:
        x = audio[it["key"]]
        us = units(it["phonemes"], it["dur"])
        voice = it["voice"]
        for k, (sym, a, b, stress, _nasal, final) in enumerate(us):
            seg = x[a:b]
            if len(seg) < HOP:
                continue
            ms = 1000 * len(seg) / SR
            if sym in VOWELS or sym.endswith("~"):
                kind = "stressed" if stress == 2 else ("final" if final else "unstressed")
                stats[(voice, sym)][f"dur_{kind}"].append(ms)
                if stress == 2 and ms >= 100:            # targets: long stressed vowels, middle 40%
                    core = seg[int(len(seg) * 0.3): int(len(seg) * 0.7)]
                    fm = formants(core)
                    if fm is not None:
                        stats[(voice, sym)]["F"].append(fm)
            else:
                stats[(voice, sym)]["dur"].append(ms)
                neighbours = [x[c:d] for (s2, c, d, *_ ) in (us[k - 1:k] + us[k + 1:k + 2]) if s2 in VOWELS]
                if neighbours:
                    stats[(voice, sym)]["rel_db"].append(rms_db(seg) - max(rms_db(v) for v in neighbours))
                if sym in ("s", "z", "S", "Z", "f", "v", "R", "tS", "dZ"):
                    lo, hi = max(a - HOP, 0), min(b + HOP, len(x))
                    win = x[lo:hi]
                    hp = win - np.convolve(win, np.ones(8) / 8, mode="same")      # crude >3 kHz
                    fr = 120                                                     # 5 ms frames
                    ratio = np.array([np.sum(hp[i:i + fr] ** 2) / (np.sum(win[i:i + fr] ** 2) + 1e-12)
                                      for i in range(0, len(win) - fr, fr)])
                    if len(ratio) >= 3 and ratio.max() > 0.2:
                        noisy = np.flatnonzero(ratio > 0.6 * ratio.max())
                        part = np.concatenate([win[i * fr:(i + 1) * fr] for i in noisy])
                        peak, cen = spectral_peak(part)
                        stats[(voice, sym)]["peak"].append(peak)
                        stats[(voice, sym)]["centroid"].append(cen)
                        stats[(voice, sym)]["noise_ms"].append(len(noisy) * 5)
    out = {}
    for (voice, sym), d in stats.items():
        row = {}
        for key, vals in d.items():
            if key == "F":
                row["F"] = np.median(np.array(vals), axis=0).round().tolist()
                row["nF"] = len(vals)
            elif key.startswith("dur"):
                row[key] = round(float(np.mean(vals)), 1)   # 25 ms quantisation: the mean carries more
            else:
                row[key] = round(float(np.median(vals)), 1)
                row[f"n_{key}"] = len(vals)
        out.setdefault(voice, {})[sym] = row
    json.dump(out, open(f"{corpus}_stats.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return out



def summary(stats):
    alex, dora = stats["pm_alex"], stats["pf_dora"]
    print("vowel targets (pm_alex, long stressed):  F1    F2    F3   n")
    for s in ["i", "e", "E", "a", "O", "o", "u"]:
        r = alex.get(s, {})
        if "F" in r:
            print(f"  {s:3s} {r['F'][0]:6.0f}{r['F'][1]:6.0f}{r['F'][2]:6.0f}  {r['nF']}")
    print("fricatives: noise ms, spectral peak / centroid Hz")
    for s in ["s", "z", "S", "Z", "tS", "dZ", "f", "v", "R"]:
        r = alex.get(s, {})
        if "peak" in r:
            print(f"  {s:3s} {r['noise_ms']:5.0f} {r['peak']:7.0f} {r['centroid']:7.0f}")
    ratios = [np.array(dora[s]["F"]) / np.array(alex[s]["F"]) for s in ["i", "e", "E", "a", "O", "o", "u"]
              if "F" in dora.get(s, {}) and "F" in alex.get(s, {})]
    print("female/male formant ratio:", np.round(np.median(ratios, axis=0), 3))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "measure"
    if cmd == "render":
        render()
    else:
        summary(measure())
