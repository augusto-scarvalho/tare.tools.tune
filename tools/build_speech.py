"""Build the voice banks of the natural voices (src/creaturesynth/speech/data/bank_<lang>_<voice>.npz).

A teacher voice reads a corpus once, here, offline: Kokoro-82M (Apache-2.0), a neural text-to-speech model. Each
recording is analysed with the WORLD vocoder into 5 ms frames (pitch, a 32-band spectral envelope, aperiodicity)
and labelled phone by phone from the teacher's own alignment, mapped to our phone symbols. Only these numbers ship.
In a game nothing neural runs: creaturesynth.speech.concat picks pieces of the bank for a new sentence, stretches
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
from teacher_calibration import CORPUS  # noqa: E402

from creaturesynth.speech.concat import FRAME, fit_durations  # noqa: E402
from creaturesynth.speech.vocoder import ENV_FLOOR, encode  # noqa: E402

CACHE = ROOT / "teacher"
OUT = ROOT / "src/creaturesynth/speech/data"
KOKORO_SR, HOP = 24_000, 600                     # Kokoro: 24 kHz audio, phone durations in 25 ms steps
LANG_CODES = {"pt": "p", "en": "a"}
# bank name -> (Kokoro voice, the vocal tract we give it)
VOICES = {"pt": {"alex": ("pm_alex", 1.0), "dora": ("pf_dora", 1.15)}}

EXTRA_PT = [
    "Bom dia, senhor! O que deseja comprar hoje?", "As maçãs vermelhas custam duas moedas cada.",
    "O capitão mandou fechar os portões da cidade.", "Minha mãe sempre dizia para ter coragem.",
    "Os irmãos trabalham juntos na fazenda do avô.", "Ninguém volta vivo daquela torre maldita.",
    "Esse pergaminho fala de um tesouro escondido.", "A lenda diz que o herói voltará um dia.",
    "Atravesse o rio pela ponte de pedra.", "Os lobos uivam quando a lua aparece.",
    "Compre três flechas e um arco novo.", "O alquimista transformou chumbo em prata.",
    "Por que você está tão preocupado?", "Eles fugiram antes do amanhecer.",
    "O velho sábio mora no alto da colina.", "Guarde bem esta pedra brilhante.",
    "As crianças brincam na praça principal.", "O trem chegou atrasado à estação.",
    "Quantos dragões você já derrotou?", "Ele quebrou o braço lutando contra o troll.",
    "Já está na hora de partir, amigos.", "A floresta proibida fica ao sul do vilarejo.",
    "O cozinheiro preparou uma sopa de legumes.", "Ela perdeu o colar de pérolas no jardim.",
    "Não confie no mercador de olhos verdes.", "O inverno chegou cedo neste ano.",
    "Os guardas trocam de turno à meia-noite.", "Precisamos atravessar o deserto em dois dias.",
    "O monstro dorme no fundo do lago gelado.", "Que bom ver você de novo, minha filha!",
    "Ouvi dizer que o rei ficou doente.", "A biblioteca guarda livros muito raros.",
    "O sacerdote abençoou as armas dos soldados.", "Dez cavaleiros partiram, só um voltou.",
    "A cigana leu a minha sorte nas cartas.", "Cuidado com as armadilhas no corredor.",
    "O ouro do reino desapareceu do cofre.", "Quero um quarto para passar a noite.",
    "O vulcão acordou depois de cem anos.", "Os anões cavam túneis debaixo da montanha.",
    "A elfa atirou uma flecha certeira.", "Traga lenha seca para a fogueira.",
    "O barqueiro cobra uma moeda de prata.", "Escondi o mapa embaixo da cama.",
    "Ele jurou proteger a princesa para sempre.", "Ganhei esta cicatriz numa batalha antiga.",
    "Vocês ouviram aquele grito na floresta?", "Siga a trilha até encontrar o moinho velho.",
    "O pão de hoje saiu quentinho do forno.", "As velas iluminam o salão do trono.",
    "A tropa marchou durante a noite inteira.", "Um corvo negro pousou na janela.",
    "A espada mágica brilha perto dos inimigos.", "Bebam água fresca da fonte sagrada.",
    "O bardo cantou uma canção muito triste.", "Ela tem medo de aranhas gigantes.",
    "A ilha dos piratas aparece no nevoeiro.", "O príncipe chegou montado num cavalo branco.",
    "Desculpe, mas a loja já está fechada.", "Quem roubou as joias da coroa?",
    "Os sinos tocam quando alguém se casa.", "O caçador seguiu as pegadas do urso.",
    "Ainda falta muito para chegar à capital?", "Vamos dividir o tesouro em partes iguais.",
    "A magia do gelo congela qualquer inimigo.", "O mestre ensinou o golpe secreto.",
    "Meus pés doem depois de tanto andar.", "Nunca vi uma tempestade tão forte.",
    "As joaninhas vivem perto das flores.", "O feiticeiro lançou uma maldição terrível.",
    "Sente-se perto do fogo e descanse.", "Há um portal escondido atrás da cachoeira.",
    "Os mineiros encontraram cristais azuis.", "Meu escudo rachou com o último golpe.",
    "A taberneira serve vinho e cerveja.", "O exército inimigo cercou o castelo.",
    "Leia o livro antes de usar a varinha.", "A estátua de bronze parece se mover.",
    "O nevoeiro esconde o caminho da serra.", "Fique quieto, os guardas estão chegando.",
    "Os peixes pulam no rio ao entardecer.", "Ele tropeçou e caiu na lama.",
    "Uma serpente enorme saiu da gruta.", "O prefeito prometeu reconstruir a muralha.",
    "Tenho uma missão importante para você.", "A cura custa vinte peças de ouro.",
    "Lembre-se de mim quando estiver longe.", "O dia está lindo para viajar.",
    "Os gnomos consertam relógios quebrados.", "A neve cobriu todas as estradas.",
    "Encontre o cristal e traga-o para mim.", "O jovem ferreiro sonha em ser cavaleiro.",
    "As abóboras cresceram muito este ano.", "O fantasma assombra o porão da casa.",
    "Pegue o machado e corte aquela corda.", "Quem é você e o que faz aqui?",
    "O navio pirata afundou perto dos recifes.", "A velha rainha guarda um segredo.",
    "Os camponeses pediram ajuda ao conselho.", "O céu ficou vermelho antes da guerra.",
    "Tome cuidado com o chefe dos bandidos.", "Ele aprendeu a ler com o monge.",
    "As ruínas antigas escondem passagens.", "O cachorro latiu a noite toda.",
    "Uma chave dourada abre a porta norte.", "A guilda dos ladrões tem novos membros.",
    "Os pássaros cantam no alto das árvores.", "Esse queijo tem um cheiro muito forte.",
    "O gelo da caverna nunca derrete.", "A carroça quebrou no meio da estrada.",
    "Conte-me tudo o que aconteceu ontem.", "O dragão vermelho cospe fogo e fumaça.",
    "Minha espada precisa de uma lâmina nova.", "Ela nasceu numa aldeia de pescadores.",
    "Os cogumelos azuis são venenosos.", "O torneio começa amanhã ao meio-dia.",
    "A ponte levadiça está emperrada.", "Não toque nesse ovo de dragão!",
    "O general planeja atacar ao amanhecer.", "A poção vermelha recupera a energia.",
    "Um gigante bloqueia a passagem do vale.", "As montanhas brilham sob o sol da manhã.",
    "Ele vendeu a fazenda para pagar dívidas.", "Os ventos do norte trazem chuva.",
    "A feiticeira mora numa torre de cristal.", "Preciso de um guia para atravessar o pântano.",
    "As crianças contam histórias de assombração.", "O padre acendeu as velas do altar.",
    "Lutamos juntos contra o exército das sombras.", "Que tal uma partida de xadrez?",
    "A maré sobe muito rápido nesta praia.", "O lenço bordado era da minha avó.",
    "Um cavaleiro sem cabeça cavalga à noite.", "O sapateiro consertou as minhas botas.",
    "A chama azul indica magia antiga.", "Ela canta melhor do que qualquer bardo.",
    "Os orcs destruíram a ponte do rio.", "O médico receitou chá de gengibre.",
    "A coroa pertence ao herdeiro legítimo.", "Ouço passos vindo do corredor escuro.",
    "Bem que eu avisei sobre aquele lugar.", "O moleiro mói o trigo todas as manhãs.",
    "Seu nome está escrito no livro antigo.", "Os mercenários exigem pagamento adiantado.",
    "O jardim do palácio tem rosas negras.", "Ninguém consegue abrir aquele baú.",
    "Volte quando tiver dinheiro suficiente.", "A estrela cadente caiu perto daqui.",
    "Ele guarda rancor desde a infância.", "A neblina sobe do pântano ao anoitecer.",
    "O rato roeu a roupa do rei de Roma.", "Três pratos de trigo para três tigres tristes.",
    "O sabiá sabia assobiar.", "A aranha arranha a jarra.",
    "Lhama, ilha, palha, olho, filho, velho.", "Banho, sonho, ninho, linha, vinho, caminho.",
    "Pão, mão, cão, chão, irmão, coração.", "Mãe, pães, cães, alemães, capitães.",
    "Põe, leões, dragões, botões, canções.", "Sim, fim, jardim, ruim, assim.",
    "Um, algum, nenhum, comum, atum.", "Bem, tem, também, ninguém, alguém.",
    "Tio, tia, dia, diabo, tipo, divino.", "Leite, noite, parte, verde, tarde.",
    "Carro, terra, ferro, guerra, morro.", "Rato, rosa, rua, rede, rio, rei.",
    "Mar, amor, calor, flor, cantar, partir.", "Sal, mel, sol, azul, papel, anel.",
    "Gato, gente, guerra, gigante, gostar.", "Casa, mesa, rosa, coisa, pesado.",
    "Chave, chuva, peixe, caixa, xícara.", "Janela, jogo, gelo, hoje, viagem.",
    "Prato, preto, primo, prova, pluma.", "Braço, branco, bruxa, blusa, bloco.",
    "Trono, trigo, trevo, atlas, atleta.", "Dragão, drama, cravo, crime, clima.",
    "Grito, grande, gruta, globo, glória.", "Fraco, frio, fruta, flecha, floresta.",
    "Vrum, livro, palavra, nevrálgico.", "Ótimo, ótica, órfão, ópera, ônibus.",
]
SENTENCES = {"pt": CORPUS + EXTRA_PT}


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
    shim = os.path.join(tempfile.gettempdir(), "creaturesynth-espeak-ng-data")
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
    pipe = kokoro(lang)
    CACHE.mkdir(exist_ok=True)
    for name, (voice, _tract) in VOICES[lang].items():
        items, audio = [], {}
        for i, text in enumerate(SENTENCES[lang]):
            for k, r in enumerate(pipe(text, voice=voice)):
                key = f"{i}__{k}"
                audio[key] = r.audio.numpy().astype(np.float32)
                items.append({"key": key, "text": text, "phonemes": r.phonemes,
                              "dur": [int(d) for d in r.pred_dur.tolist()]})
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
        f0s, envs, aps, phones, base = [], [], [], [], 0
        for u, it in enumerate(items):
            x = audio[it["key"]].astype(np.float64)
            f0, t = pw.harvest(x, KOKORO_SR, f0_floor=60, f0_ceil=600, frame_period=FRAME * 1000)
            f, env, ap = encode(f0, pw.cheaptrick(x, f0, t, KOKORO_SR), pw.d4c(x, f0, t, KOKORO_SR), KOKORO_SR)
            for sym, a, b, st, flags in refine(labels(it["phonemes"], it["dur"], len(f)), env, f):
                phones.append([sym, base + a, base + min(b, len(f)), st, u, flags])
            f0s.append(f)
            envs.append(env)
            aps.append(ap)
            base += len(f)
        voiced = np.concatenate(f0s)
        model = fit_durations(phones)
        meta = {"lang": lang, "name": name, "teacher": f"Kokoro-82M {voice} (Apache-2.0)", "tract": tract,
                "pitch": round(float(np.median(voiced[voiced > 0])), 1), "durations": model}
        env = np.clip(np.round((np.concatenate(envs) - ENV_FLOOR) * 2), 0, 255).astype(np.uint8)
        out = OUT / f"bank_{lang}_{name}.npz"
        np.savez_compressed(out, f0=voiced.astype(np.float16), env=env,
                            ap=np.round(np.concatenate(aps) * 255).astype(np.uint8),
                            phones=np.frombuffer(json.dumps(phones).encode(), dtype=np.uint8),
                            meta=np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8))
        print(f"{lang}/{name}: {len(phones)} phones, {base * FRAME / 60:.1f} min, duration model r = "
              f"{model['fit'][0]} -> {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    cmd, lang = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "pt"
    {"render": render, "build": build}[cmd](lang)
