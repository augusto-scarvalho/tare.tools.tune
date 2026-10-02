# Arquitetura

## Pipeline

```
Creature(archetype, species, size, aggression, individual, ...)
   │ .voice(call, take)
   ▼
Genome(species, individual, take) + Traits(size, aggression) + Call
   │ arquétipo (design: só aritmética, < 3 ms)
   ▼
Voice  ── o "spec": JSON puro, versionado ──►  render(voice, sr)  ──►  áudio mono float32
```

O sistema separa duas etapas de propósito:

- **Design** (genes, traços e chamado viram spec): barato, determinístico, sem DSP.
- **Render** (spec vira áudio): todo o processamento de sinal fica aqui.

O spec é o ponto de entrega entre as duas. Pode ser salvo junto de um asset, mandado para uma engine ou editado à mão.

| módulo | papel |
|---|---|
| `rng.py` | aleatoriedade portável: SplitMix64 + FNV-1a |
| `genome.py` | genes por nome: estáveis por espécie, variação por indivíduo e por take |
| `calls.py` | `Traits` (tamanho, agressividade) e `Call` (idle, alert, attack, hurt, death) |
| `archetypes/` | `natural.py`, `fantasy.py`, `retro.py`: cada arquétipo é `design(ctx) -> Voice` |
| `spec.py` | `Voice` e suas camadas (`Syllable`, `ChipProgram`, `SpeechProgram`, `Modal`, `Noise`, `Scatter`, `Vocoded`) + JSON (v5) |
| `render.py` | DSP fonte-filtro |
| `chip.py` | motor Game Boy (2 pulsos + ruído) e leitor dos dados da 1ª geração |
| `creature.py` | API principal (`Creature`) |
| `bake.py` | uso offline: bestiário → WAVs + manifest |
| `runtime.py` | uso em jogo Python: `VoiceBank` |
| `cli.py` | linha de comando |
| `speech/` | fala humana: `g2p_pt.py` e `g2p_en.py` (texto → fonemas), `phonetics.py` (alvos, coarticulação, entonação), `klatt.py` (síntese), `babble.py` (balbucio), `casting.py` (qual motor fala), `concat.py` (motor natural: bancos de voz), `vocoder.py` (síntese a partir de quadros medidos), `emote.py` (interjeições), `Speaker` |
| `clap.py`, `designer.py`, `analysis.py` | calibração: CLAP (texto ↔ som), busca evolutiva (`design`, `match`), medidas de gravações |
| `sfx/` | efeitos sonoros: `Sfx`, materiais e `Fx` (`__init__.py`), `physical.py` (armas, passos, explosões), `magic.py`, `ambience.py` |
| `layers.py` | DSP dos efeitos: corpos modais, faixas de ruído com filtro móvel, nuvens de eventos |
| `score.py` | composição: `Score` (faixas, sons posicionados, pan, sala estéreo compartilhada, loops), nomes de notas, acordes e escalas |
| `instruments.py` | 38 instrumentos medidos em notas gravadas (cada um: `Note` → camadas do spec) |
| `music.py` | músicas por semente: `Cue` (jingles e loops, orquestra ou chip) |

## Determinismo

Tudo que é aleatório vem de `rng.py`, para que uma port reproduza exatamente:

- `fmix(z)`: função de saída do SplitMix64 (constantes `0xBF58476D1CE4E5B9` e `0x94D049BB133111EB`, shifts 30/27/31).
- `fnv1a(texto)`: FNV-1a 64 dos bytes UTF-8.
- `key(p1, p2, ...)`: começa em `h = 0` e, para cada parte, faz `h = fmix((h ^ p) + GOLDEN)`. Strings entram como `fnv1a(s)`. Tudo é módulo 2^64, com `GOLDEN = 0x9E3779B97F4A7C15`.
- `uniform(k) = (k >> 11) * 2^-53`. O fluxo `uniforms(k, n)[i] = uniform(fmix(k + (i+1)·GOLDEN))` é o SplitMix64 semeado com `k`.
- `tri(k) = uniform(key(k, 1)) - uniform(key(k, 2))`.

Vetores de teste para conferir uma port estão em `tests/test_rng_genome.py`. O SplitMix64 semeado com 0 começa em `0xE220A8397B1DCDAF`.

**Genes:**
- `u(gene) = clip(base + variation·tri(key(species, fnv1a(gene), individual, 1)) + take_variation·tri(key(species, fnv1a(gene), individual, take, 2)))`, com `base = uniform(key(species, fnv1a(gene)))`.
- `choice` usa só `base`, então a **estrutura** (vogal, tipo de monstro, forma do canto) é fixa por espécie.
- Como os genes são buscados por nome, adicionar um gene novo não embaralha os outros.

**Sementes do render:**
- A seed da voz é `seed32(archetype, species, individual, take, call)`, com 32 bits para caber em qualquer linguagem.
- A sílaba `i` usa `key(seed, "syllable", i)`. Dela saem os fluxos `"source"`, `"breath"`, `"jitter"` e `"rough"`.
- O reverb usa `key(seed, "space")`.

**Atenção:** mudar a fórmula de um arquétipo muda a voz das espécies que já existem. Assets "bakeados" não sofrem com isso, porque guardam o WAV e o spec.

## Spec (versão 4)

Os campos com valor padrão são omitidos no JSON (`Voice.to_dict`).

**Voice**

| campo | significado |
|---|---|
| `syllables` | lista de `Syllable` |
| `chips` | lista de `ChipProgram` (motor Game Boy) |
| `speech` | lista de `SpeechProgram` (fala humana, v2) |
| `drive` | saturação `tanh` |
| `crush` | 0..1, reduz taxa de amostragem e bits |
| `space`, `wet` | cauda de reverb em segundos e mix. A engine pode trocar pelo reverb dela |
| `gain` | pico final relativo a -1 dBFS (o idle sai ~9 dB abaixo do ataque) |
| `lowpass` | Hz, 0 = desligado: perda de agudos (distância, microfone) (v3) |
| `room` | 0..1, mix de reflexões curtas de sala (v3) |
| `air` | 0..1, ruído de fundo de gravação, de -70 a -30 dB do pico (v3) |
| `modal`, `noise`, `scatter` | listas de `Modal`, `Noise` e `Scatter` (efeitos sonoros, v4) |
| `vocoded` | lista de `Vocoded` (performances refeitas pelo vocoder, v5) |
| `spoken` | lista de `Spoken` (fala do motor natural, v5) |
| `loop` | segundos de crossfade; > 0 gera um loop sem emenda de `duração − loop` segundos (v4) |
| `seed` | semente de todos os fluxos aleatórios |
| `meta` | informativo (arquétipo, chamado, traços) |

**Syllable**: `start` e `dur` (s); `pitch` (curva em Hz); `source` (`glottal`, `sine`, `pulse` ou `noise`); `pulse_width`; `brightness`; `vibrato` [Hz, semitons]; `jitter` (semitons); `sub`; `rough` [profundidade, Hz]; `breath`; `ring` [Hz, mix]; `formants` [[Hz, largura, ganho], ...]; `mouth` (curva de escala dos formantes); `pulses` [Hz, profundidade, nitidez]; `attack` e `release` (s); `amp` (curva); `gain`; `shimmer` (oscilação aleatória de volume, v3).

Uma curva é `[[t, valor], ...]` com `t` de 0 a 1. O tom é interpolado em escala log; o resto, linear.

**ChipProgram**: `pulse1`, `pulse2` e `noise` são comandos `{"duty": byte}` ou `{"note": [dur-1, volume, fade, frequência ou parâmetro NR43]}`; `pitch`; `length` (-128..127); `start`; `gain`; `hardware_noise`.

**SpeechProgram** (versão 2 do spec): `frames` é um dicionário de trilhas a `frame_rate` (400 por segundo):
- `f0`: tom;
- `av`, `ah`: vozeamento e aspiração;
- `af`, `ab`: fricção ressonante e plana;
- `f1`…`f5` e `b1`…`b5`: formantes da cascata;
- `fnp`, `fnz`: polo e zero nasais;
- `fa`/`wa`/`ga` e `fb`/`wb`/`gb`: duas ressonâncias de fricção (Hz, largura, ganho).

Também guarda `tilt`, `jitter`, `rough`, `sub`, e `text`, `lang` e `phonemes` como informação.

**Modal** (v4), um corpo batido ou raspado: `start`, `dur`; `modes` [[Hz, T60 em s, ganho], ...]; `hits` [[s, ganho, duração do contato em s], ...]; `scrape` [início s, duração s, ganho, trepidação Hz]; `hardness` (passa-baixa da excitação, Hz); `click` (o ruído do contato, misturado); `gain`.

**Noise** (v4), uma faixa de ruído: `start`, `dur`; `freq` (curva em Hz); `filter` (`band`, `low` ou `high`); `q`; `color` (`white` ou `brown`); `amp` (curva); `attack`, `release`; `wobble` [Hz, profundidade]; `gain`.

**Scatter** (v4), uma nuvem de eventos: `start`, `dur`; `rate` (curva em eventos por segundo); `event` (`pop`, `drop` ou `ping`); `freq`, `decay` e `level` (faixas [mín, máx]); `gain`.

**Vocoded** (v5), uma performance curta refeita pelo vocoder (`speech/vocoder.py`) a partir de um molde: `clip` (nome do molde, `<tipo>/<intérprete>/<take>`, por exemplo `attack/adventurer/attack3`); `start`; `pitch` (razão de tom); `warp` (razão das formantes: trato mais curto, formantes mais altas); `stretch` (razão de duração); `breath` (−1..1: menos ar, até voz pura, ou mais ar, até sussurro); `tilt` (dB por oitava em torno de 1 kHz); `swing` (largura do contorno de tom: 1 = como foi gravado, 0 = monótono); `gain`. Os moldes ficam em `speech/data/barks.npz` e uma port precisa levá-los junto (ver o algoritmo abaixo).

**Spoken** (v5), fala do motor natural (`speech/concat.py`): `bank` (`<idioma>/<voz>`, por exemplo `pt/alex`); `pieces` [[quadro inicial, quadro final, quadros de saída], ...] (trechos do banco, em quadros de 5 ms, esticados sobre a saída); `joins` (índices dos trechos que entram com crossfade); `f0` (tom por quadro de saída, Hz, usado onde o banco tem voz); `start`; `warp`, `breath` e `tilt` (como em `Vocoded`); `gain`; e `text`, `lang` e `phonemes` como informação. Os bancos ficam em `speech/data/bank_<idioma>_<voz>.npz`, no mesmo formato dos moldes das interjeições.

Specs das versões 1 a 4 continuam sendo lidos.

## Algoritmo do render (para ports)

Por sílaba, com `n = max(floor(dur·sr), 16)` e `t = i/sr`:

1. **Tom**: interpolação log de `pitch` em `n` pontos de 0 a 1. Depois, `f0 *= 2^((vib_depth·sin(2π·vib_rate·t) + jitter·smooth(key(k,"jitter"), 25/s)) / 12)` e limite em `[1, 0.49·sr]`.
   - `smooth(k, n, sr, rate)`: `P = max(2, floor(n/sr·rate)+2)` pontos de controle `noise(k, P)` (uniformes em [-1, 1)), interpolados linearmente.
2. **Fonte**: `ciclos = cumsum(f0/sr)`, `fase = frac(ciclos)`, `dt = min(f0/sr, 0.5)`.
   - `glottal`: serra `2·fase − 1 − polyblep(fase, dt)`.
   - `pulse`: `±1` com largura `w`, mais `polyblep(fase) − polyblep((fase − w) mod 1)`.
   - Nos dois casos acima, passa-baixa de 1ª ordem (Butterworth bilinear) em `min(mediana(f0)·(1.5 + 40·brightness²), 0.45·sr)`.
   - `sine`: `sin(2π·ciclos) + 0.12·sin(4π·ciclos)`.
   - `noise`: `0.8·noise(key(k,"source"), n)`.
   - Em seguida, na ordem:
     - `sub`: `x *= 1 + sub·cos(π·ciclos)`;
     - `breath`: `x = x·(1−b) + 0.7·b·noise(key(k,"breath"), n)`;
     - `ring`: `x *= 1 − mix + mix·sin(2π·hz·t)`.
3. **Formantes**: band-passes RBJ em paralelo (pico de 0 dB), com coeficientes atualizados a cada 64 amostras e o estado do filtro preservado entre blocos.
   - Bloco `b`: `s = mouth` interpolado em log no ponto `b` de `ceil(n/64)` pontos de 0 a 1.
   - `f = min(hz·s, 0.45·sr)`, `w0 = 2πf/sr` e `α = sin(w0)·min(bw·s, f)/(2f)`.
   - Coeficientes: `b = [α, 0, −α]/(1+α)` e `a = [1, −2cos(w0)/(1+α), (1−α)/(1+α)]`.
   - Saída: `Σ ganho·y`. Sem formantes, o sinal passa direto.
4. **Envelope**: `amp` interpolado linearmente.
   - Ataque de `A = clamp(floor(attack·sr), 1, n)` amostras, multiplicado por `linspace(0,1,A)²`. O release é igual, invertido.
   - `rough`: `env *= 1 − d·(0.5 + 0.5·sin(2π·rate·t + 3·smooth(key(k,"rough"), 8/s)))`.
   - `shimmer`: `env *= max(0, 1 + shimmer·smooth(key(k,"shimmer"), 60/s))`.
   - `pulses`: `env *= 1 − d + d·(0.5 − 0.5·cos(2π·rate·t))^nitidez`.
5. A sílaba é `x·env`, normalizada para pico = `gain`.

Na voz inteira:
1. Soma, em `floor(start·sr)`, as sílabas, os chips (normalizados para pico = `gain`), a fala e as camadas de efeito (abaixo).
2. Passa-alta Butterworth de 2ª ordem em 40 Hz, depois normaliza para pico 1.
3. `crush`: sample-and-hold de `1 + floor(11·crush)` amostras, quantizado em `2^(14 − 10·crush)` níveis.
4. `drive`: `tanh(d·x)/tanh(d)`.
5. Realismo (v3), na ordem:
   - `lowpass`: Butterworth de 2ª ordem em `min(lowpass, 0.45·sr)`;
   - `room`: IR de 60 ms com 1 na amostra 0 e 40 reflexões em `floor(uniforms(key(key(seed,"room"),"taps"), 40)·(N−1))`, ganhos `noise(key(key(seed,"room"),"gains"), 40)·e^(−3·tap/N)`; saída `(1−room)·x + room·molhado·pico(x)/pico(molhado)`;
   - `air`: `noise(key(seed,"air"), n)` passado por passa-baixa de 1ª ordem em 1 kHz, normalizado para pico 1 e somado com ganho `10^((−70 + 40·air)/20)`.
6. Reverb:
   - IR: `noise(key(seed,"space"), N)·exp(−6.9·i/N)`, com `N = space·sr`, passada por um passa-baixa Butterworth de 2ª ordem em 5 kHz.
   - Saída: `(1−wet)·seco + wet·cauda·pico(seco)/pico(cauda)`.
7. Com `loop`: o trecho depois de `T = (duração − loop)·sr` amostras volta para o início. Os primeiros `L = loop·sr` são cruzados em potência constante, `início·sin(πw/2) + fim·cos(πw/2)` com `w` de 0 a 1, e o resto (cauda de reverb) é somado em `(L + i) mod T`. Sem `loop`: fade de 4 ms no fim.
8. Normalização para pico `0.89·gain`.

**Camadas de efeito (`layers.py`, v4)**, cada uma normalizada para pico = `gain`, com `k = key(seed, tipo, índice)`:
- **Modal:**
  - A excitação soma, para cada `hit` `i`, `noise(key(k,"hit",i), L)·hann(L)·ganho` com `L = max(contato·sr, 2)`.
  - A raspagem soma `0.3·ganho·noise(key(k,"scrape"), L)·sin²(π·j/L)`, vezes `1 + 0.8·sin(2π·trepidação·t)` quando há trepidação.
  - Tudo passa por um passa-baixa de 1ª ordem em `hardness`.
  - Cada modo (20 Hz ≤ f < 0.45·sr) é um ressonador `b = [sin w]`, `a = [1, −2r·cos w, r²]`, com `w = 2πf/sr` e `r = 10^(−3/(T60·sr))`: resposta ao impulso de amplitude 1, −60 dB em T60.
  - Saída: `click·excitação + Σ ganho·modo`.
- **Noise:**
  - Fonte `noise(key(k,"noise"), n)`; a `brown` passa por `1/(1 − 0.997·z⁻¹)` e é normalizada.
  - Filtro RBJ (band-pass com largura `f/q`, passa-baixa ou passa-alta com Q = `q`), coeficientes a cada 64 amostras pela forma direta I do `time_varying`, frequência pela curva em log.
  - Envelope como o das sílabas, vezes `max(0, 1 + profundidade·smooth(key(k,"wobble"), Hz))`.
- **Scatter:**
  - `M = ceil(máx(rate)·dur)` tempos candidatos `sort(uniforms(key(k,"times"), M))·dur`, mantidos onde `uniforms(key(k,"keep"), M)·máx(rate) < rate(t)`.
  - Por evento `i`: `f` log-uniforme, decaimento e nível uniformes (streams `freq`, `decay`, `level`), comprimento `max(5·decaimento·sr, 8)`, envelope `e^(−t/decaimento)`.
  - `pop`: `noise(key(k,"ev",i))` por um Butterworth de 2ª ordem em banda `[f/1.5, 1.5f]`.
  - `drop`: `sin(2πf(t + t²/(4·decaimento)))`.
  - `ping`: `(sin(2πft) + 0.4·sin(2π·2.76ft)·env)·env`.

**Fala (`speech/klatt.py`)**, com trilhas interpoladas: amplitudes e `f0` por amostra, coeficientes a cada 48 amostras.
1. **Fonte:** serra PolyBLEP em `f0` (com jitter), passa-baixa de 1ª ordem em `tilt`, opcionalmente `sub`. Soma-se `av·fonte` com `ah·ruído`; o ruído pulsa com o ciclo glotal quando há vozeamento.
2. **Cascata:**
   - polo nasal (`fnp`, largura 100) → zero nasal (`fnz`, largura 100) → R1…R5 (`fK`, `bK`);
   - ressonadores de Klatt com ganho DC unitário: `C = −e^(−2π·bw/sr)`, `B = 2e^(−π·bw/sr)·cos(2πf/sr)`, `A = 1 − B − C`;
   - o antirressonador usa `[1/A, −B/A, −C/A]`.
3. **Paralelo:** `af·ruído` passa por dois band-pass (`fa`/`wa`·`ga` e `fb`/`wb`·`gb`), mais `ab·ruído` com passa-alta em 1,2 kHz, tudo vezes `FRIC_GAIN`.
4. **Saída:** soma, `rough` (AM), passa-alta em 60 Hz e normalização para `gain`.

**Vocoder (`speech/vocoder.py`)**, o mesmo desenho de síntese do WORLD (M. Morise), em numpy e determinístico:
- **Moldes** (`barks.npz`, um zip de arrays `.npy`): a cada 5 ms, `f0` (float16, 0 = sem voz), `env` (uint8: envelope espectral em 32 faixas mel de 40 Hz a 20 kHz, `valor/2 − 107.5` dB) e `ap` (uint8: aperiodicidade em 5 faixas log de 500 Hz a 16 kHz, `valor/255`); `meta` é JSON com tipo, intérprete, trato, tom mediano, início e número de quadros de cada molde, e a fonte (licença CC0).
- **Transformações**, quadro a quadro: `stretch` reamostra os quadros (interpolação linear; `f0` só entre quadros com voz); `swing` faz `f0 = tom·(f0/tom)^swing`; `pitch` multiplica `f0`; `breath ≥ 0` faz `ap += breath·(1 − ap)`, `breath < 0` faz `ap *= 1 + breath`.
- **Filtros por quadro** (`nfft` 2048 acima de 32 kHz, senão 1024): o envelope é lido em `f/warp` (interpolação linear em Hz, `ap` em log de Hz), mais `tilt·log2(f/1000)` dB. Abaixo do tom gravado (500 Hz onde não há voz) o envelope não mede nada: fica no valor do tom, caindo 3 dB por oitava. Voz: fase mínima de `√(P·(1−ap))`; ar: fase mínima de `√(P·ap)` (ou `√P` sem voz). Fase mínima pelo cepstro real dobrado.
- **Pulsos:** um por período glotal (`f0` do quadro, ou 500 Hz sem voz). Em cada pulso no tempo `t` (fracionário), com `n` amostras até o próximo:
  - ar: `noise(key(seed,"breath", i), n)` menos a média, por FFT de `nfft` vezes o filtro de ar, vezes √3 (ruído uniforme com variância 1);
  - voz: a resposta de fase mínima com atraso fracionário (`e^(−2πif·frac/sr)`), menos o DC (subtraído com uma janela de Hann na primeira metade), vezes `√n`;
  - os dois somados a partir da amostra `floor(t·sr)`.
- No fim, corta-se a cauda abaixo de −80 dB do pico, e a camada é normalizada para `gain`.

**Fala natural (`speech/concat.py`)**, a partir de um `Spoken`:
- **Quadros:** cada trecho `[a, b, n]` dá `n` quadros nas posições `a + (j + 0,5)/n · (b − a)` do banco, com envelope e aperiodicidade interpolados linearmente entre quadros vizinhos; a voz (sim/não) vem do quadro mais próximo (`f0 > 0`).
- **Junções:** em cada trecho listado em `joins`, os ±3 quadros em volta do começo dele misturam os dois trechos, cada um continuando além do corte no próprio passo, com peso linear de 0 a 1 (a voz segue quem pesa mais).
- **Tom:** `f0` do spec onde há voz, 0 no resto.
- **Som:** o vocoder acima, com `warp`, `breath` e `tilt`; semente `key(seed, "spoken")`; normalizado para `gain`.

**Coeficientes variáveis sem clique:** entre blocos, os filtros carregam o histórico de forma direta I (duas entradas e duas saídas) e recalculam o estado para os coeficientes novos (`render.time_varying`). Reaproveitar o estado do `lfilter` através de uma troca de coeficientes gera um estalo audível a cada transição de fonema.

**Validar uma port:** os fluxos aleatórios devem bater bit a bit (vetores de teste). O áudio não será bit-exato, por ordem de operações em ponto flutuante e convolução por FFT. Para ter material de comparação, rode `creaturesynth bake` com specs: cada entrada do manifest traz o spec e o WAV de referência. Renderize os specs na engine e compare os espectros. Com `space = 0` a diferença deve ser mínima.

## Efeitos sonoros

`Sfx(kind, style, species, size, power)` é o `Creature` dos efeitos. O `kind` escolhe a receita (`@recipe` em `sfx/`), o `style` o material, o elemento ou o lugar. A `species` é a identidade do objeto: os modos desta espada e o tom desta magia ficam fixos (genes por nome, como nas criaturas), enquanto cada take sorteia o resto (onde o golpe pega, o tempo entre os contatos). O design só monta um `Voice`, então `bake`, `VoiceBank`, specs e ports funcionam igual.

**Materiais** (`MATERIALS`): faixa de modos (o mais grave depende do tamanho), número de modos, T60 do mais grave, amortecimento (`T60·(f/f₀)^−d`), dureza do contato, distribuição e uma frequência abaixo da qual o corpo irradia pouco.
- **Distribuições:** `dense` para lâminas e placas de metal, `sparse` para madeira, pedra e vidro, `bell` para sinos com terça menor, `string` para harmônicos com leve rigidez.
- **Irradiação:** é o que faz uma espada soar como "shiiing" agudo e não como sino.

**`AmbiencePlayer`** (runtime): toca o loop do lugar sem parar e agenda eventos com intervalos exponenciais (processo de Poisson com `per_minute`). Cada evento tem alguns takes renderizados em segundo plano e é pulado se não estiver pronto; a saída passa por `tanh`, para um trovão sobre a chuva não estourar.

**Arco: modelado a partir de uma gravação.** Otimizar números (CLAP ou estatísticas de gravações) nivelou o caráter das armas, e uma tentativa nesse sentido foi desfeita depois de ouvida. O arco segue outro método:
- medir o mecanismo numa gravação de referência, na escala de milissegundos;
- construir cada parte com esses números;
- escolher de ouvido entre variantes.

As partes:
- **Puxar (`creak`):** ~60–70 escorregões de atrito por segundo, em trens quase regulares cujo ritmo deriva.
  - Cada escorregão cresce em ~2 ms e ressoa ~10 ms numa nuvem densa de modos de madeira, dentro das faixas medidas (1,7, 2,9, 5,5 e 7,9 kHz), mais uma nota de flexão um pouco mais longa.
  - A força cresce com a tensão, sobre um atrito de fundo baixo.
  - `creak()` serve para qualquer madeira sob esforço.
- **Soltar (`bow_release`):**
  - um "fwip" curto;
  - a corda raspando na flecha: um zumbido áspero (~170 Hz) cuja ressonância desce de ~800 para ~300 Hz enquanto cresce ~20 dB (como ruído liso, soava como uma vassoura);
  - a pancada, que faz soar a mesma madeira do puxar (os dois precisam soar como o mesmo arco) e o batente grave;
  - a vibração de corda e braços (~57 Hz e harmônicos), com um parcial de ~1,1 kHz que fica soando;
  - a flecha indo embora, ouvida de quem atira: começa no volume em que o zumbido termina, cai como 1/r (r = 2 m + v·t, v ≈ 60 m/s, 90 m/s na besta), já mais grave (c/(c+v)) e escurecendo com a distância.
- **Voo (`fletching`, `flyby`):** as penas sopram uma faixa larga perto de 3 kHz e fazem o ar vibrar ~90 vezes por segundo.
  - Passando por quem ouve, sobe ~40 dB (linear em dB) até a passagem e cai ~30 dB em 0,15 s, com a faixa descendo (Doppler).
  - Na primeira montagem havia uma pausa entre o soltar e o voo, e o voo recomeçava de longe: soava como "começa, para e volta". Por isso o soltar carrega a saída da flecha, e o `fly` é só a passagem perto do ouvinte.
- **Flecha na madeira (`arrow_in_wood`):**
  - um estalo (~15 ms, banda larga);
  - o corpo do alvo (modos de ~140 a ~240 Hz, ~60 ms);
  - a haste cravada zumbindo perto de 160 Hz, com harmônicos, por mais de um segundo. Ela pulsa ~26 vezes por segundo enquanto balança (dois modos próximos batendo).
- **Flecha na carne (`arrow_in_flesh`):** um baque surdo perto de 195 Hz (−20 dB em ~50 ms), um rasgo úmido curto perto de 2,8 kHz, o tique da perfuração e a haste vibrando, abafada pela carne.
- **Flecha na pedra (`arrow_on_stone`):** um estalo duro; a ponta e a haste soam curto e agudo (1,3–10 kHz, ~40 ms); a flecha cai e quica, com os próximos contatos a ~0,39 s e ~0,23 s, em −14 e −18 dB. Às vezes a haste quebra.
- **Níveis:** o voo e o impacto ficam ~4 e ~6 dB acima do soltar, como na mistura escolhida de ouvido.

**Espada: medida em gravações de golpes e choques.**
- **Choque (`blade_clash`):** curto e agudo, não um sino.
  - Medidas: 40 dB de queda em 0,2–0,6 s; energia concentrada perto de 6 kHz; quase nada abaixo de 1,5 kHz (média de terço de oitava de seis gravações, `BLADE_RING`).
  - Três partes: o contato; as lâminas raspando uma na outra por 30–80 ms; muitas vezes um segundo toque ~30 ms ou ~170 ms depois.
  - Cada lâmina tem ~60 modos densos entre 1,2 e 12,5 kHz, fixos pela espécie. Os níveis de cada modo (`BLADE_MODES`) foram ajustados renderizando e comparando até o anel bater com a média medida (±3 dB por faixa). O golpe re-pondera os modos a cada take. Três modos mais graves soam mais tempo.
- **Golpe no ar (`blade_swing`):** ~0,25 s.
  - O que mais pesa é o empurrão de pressão da lâmina passando (abaixo de 300 Hz). Com ele vem um chiado centrado em ~1,4 kHz, que sobe ~30 dB em ~55 ms, cai em ~170 ms e escurece ao desacelerar.
- **Golpes (`blade_hit`):** cada alvo medido em gravações de lâmina batendo nele.
  - Madeira: um "toc" seco. A tábua soa em poucas notas graves (~470, ~1080, ~1550 Hz) e some em ~0,1 s (40 dB em 100–220 ms). A lâmina quase não ressoa, porque crava.
  - Pedra: um estalo duro e claro. A lâmina ressoa só um instante (40 dB em ~100 ms), com alguns modos curtos da pedra (1–5 kHz) e fragmentos espirrando por ~60 ms.
  - Armadura: um "clang". A chapa tem modos densos de 650 Hz a 6,5 kHz, mais fortes entre 2,5 e 5 kHz; os agudos morrem em ~0,2 s e alguns graves seguem ~0,6 s. A lâmina ressoa por baixo, com o baque abafado do corpo.
  - Carne: o baque do corpo (~90 Hz, ~0,1 s) costuma ser o mais forte. Por cima vem um chiado úmido e trêmulo acima de 2 kHz (60–150 ms), um "squelch" mais fraco perto de 900 Hz e estalinhos molhados.
- **Sacar (`blade_draw`):** um raspado largo e brilhante (2,5–6 kHz) que sobe ~25 dB em 70–170 ms e se mantém. Às vezes há um tique da guarda saindo da boca da bainha. Depois a lâmina livre segue soando: −20 dB em ~0,3 s, −35 dB em 0,5–1,2 s.
- **Cair no chão (`blade_drop`):** o punho bate primeiro; 30–45 ms depois a lâmina cai deitada, que é a pancada mais forte. Ela chacoalha contra o chão por ~0,15 s enquanto soa, e quica de novo ~0,27 s depois. Por baixo ficam a batida do chão e um baque grave. Na primeira versão, sem o chacoalhar e com pouco grave, o som saiu fraco.
- **Variantes escolhidas de ouvido**, ligadas aos traços:
  - tamanho 1 = lâmina pesada: modos 25% mais graves, anel mais curto, pancada grave nos braços, golpe mais lento com um "vum" de ~120 Hz; nos golpes, mais baque, mais fragmentos na pedra, osso na carne;
  - força 1 = cinema: raspa até 150 ms, anel 2,2× mais longo, golpe rápido com assobio do sulco da lâmina; nos golpes, a lâmina e a armadura soam mais, e a carne ganha um corte afiado.
- **Níveis:** o golpe fica com metade do pico do choque, como na mistura ouvida. `Fx.level(x)` dá o pico de cada evento na força máxima, e assim a mistura entre os eventos de uma receita se mantém em qualquer força.

**Maça e martelo (`blunt`): medidos em gravações** de porretes, martelos, canos e pedras batendo em cada alvo, e de golpes pesados no ar.
- **Golpe no ar:** um "vum" escuro. Quase toda a energia fica abaixo de 1 kHz (centroide 0,4–1 kHz) e muitas vezes há um tom grave perto de 150–270 Hz.
- **Acerto:** quem soa é mais o alvo do que a arma. A cabeça da arma (madeira, ferro ou pedra) soa baixinho por baixo, junto com o baque da massa:
  - carne: um baque fundo (110–370 Hz, 40 dB em 0,16–0,38 s) sob o estalo da pele;
  - madeira: uma batida curta, com o modo principal em ~350 Hz, que some em 30–170 ms;
  - metal: um "clang" mais grave e mais longo que o de uma lâmina (0,5–7 kHz, mais forte entre 1,6 e 4 kHz, 40 dB em 0,2–0,6 s);
  - pedra: um estalo largo com fragmentos.
- **Cair no chão:** a cabeça bate pesada, o cabo cai 50–100 ms depois, e há um quique pequeno.
- **Variantes:** como na espada, tamanho 1 é a arma mais pesada (mais grave, mais baque, osso na carne, mais fragmentos) e força 1 é a de cinema (mais anel no metal, estalo da pele mais forte).

**Escudo (`shield`): medido em gravações** de espadas, porretes e empurrões em escudos.
- **Espada em escudo de madeira:** rápido e de agudo médio. Quase não tem grave (−20 dB abaixo de 500 Hz). O painel soa perto de 0,85–0,95, 1,6–1,7, 2,2 e 3,3–3,8 kHz por 0,13–0,4 s, junto com o anel da lâmina; 40 dB em 130–200 ms.
- **Porrete no escudo:** move o painel inteiro, com um corpo grave entre 120 e 400 Hz.
- **Escudo de metal:** soa mais denso e mais longo (0,23–3,4 kHz, 40 dB em ~0,3 s).
- **Flecha no escudo:** deixa a haste vibrando.
- **Empurrão:** abafado pelo corpo do outro, com alças, borda e umbo chacoalhando.

**Equipamento em movimento (`gear`): medido em gravações** de cota de malha, armadura de placas e couro.
- **Cota de malha:** um crescendo de anéis pequenos tilintando, mais forte em 8–12 kHz.
- **Placas:** algumas batidas separadas (1,6–8 kHz, mais fortes em 4–6 kHz) sobre um roçar.
- **Couro:** um rangido de escorregões densos (70–100 por segundo) lá embaixo (mais forte em 250–500 Hz, −20 dB acima de 2,5 kHz) sobre um farfalhar suave. É o mesmo mecanismo do arco sendo puxado, mais grave e mais amortecido.
- **Eventos:** `move` para um passo ou um gesto, `run` para um movimento mais curto e forte, `equip` para vestir (dois movimentos e uma fivela).

**Corpo caindo (`body`): medido em gravações.** Não é um baque só.
- **Queda (`fall`):** 3 a 6 batidas graves em 0,2–0,5 s: joelhos, quadril, o tronco (a mais forte) e depois um braço ou a cabeça, separadas por 60–150 ms e 4–14 dB abaixo do tronco. Cada uma é um baque perto de 110–180 Hz. O som é mais forte em 250–500 Hz, cai ~14 dB em 2,5 kHz e ~20 dB em 8 kHz, com a roupa farfalhando o tempo todo.
- **Peso morto (`drop`):** só o tronco e um quique pequeno.

**Portas e baús (`door`, `chest`): medidos em gravações** de portas, baús, fechaduras e batidas na porta.
- **Dobradiça:** range por escorregões num ritmo constante, um tom harmônico de 600 a 1500 Hz. A altura sobe quando o movimento acelera e desce quando ele freia. Como os escorregões prendem e soltam, o volume gagueja.
- **Porta batendo:** grave (mais forte em 250 Hz), com os modos do painel em 250–870 Hz soando por 0,25–0,4 s.
- **Porta trancada:** chacoalha 2 a 5 vezes, com 60–130 ms entre uma e outra, e é aguda (mais forte em 1,6–4 kHz).
- **Chave:** gira os pinos com cliques a cada 50–130 ms; o ferrolho vem por último e é o mais forte.
- **Batida com os nós dos dedos:** abafada, mais forte em 250–1000 Hz, com 0,15–0,25 s entre as batidas.
- **Portão de ferro:** ressoa mais longo.

**Itens (`item`): medidos em gravações** de moedas, rolhas, goles e páginas.
- **Moedas:** tilintam muito agudo (mais forte em 8–13 kHz). As moedas pequenas soam em 8,4–13,7 kHz por 0,06–0,46 s e as grossas em 1,5–5 kHz, em vários toques a 20–100 ms uns dos outros.
- **Moeda caindo:** quica (~0,1 s entre os quiques) e depois gira, chacoalhando cada vez mais rápido até parar.
- **Rolha:** estoura grave, com o gargalo ressoando em 500–1150 Hz por ~0,15 s.
- **Gole:** grave (mais forte em 250–500 Hz, com uma ressonância perto de 1–1,3 kHz), em rajadas de 2–3 estalos da garganta a 40–50 ms.
- **Página virando:** estala em 1–6 kHz por 0,3–0,6 s e termina num abano suave.
- **Gema:** soa como cristal.

**Quebrar (`breakable`): medido em gravações** de caixas, potes de barro, cerâmica e vidro quebrando.
- **Caixa de madeira:** lasca. É grave-média (mais forte em 250–1600 Hz), com 9 a 18 estalos no primeiro meio segundo e pedaços caindo até ~1 s. O barril ainda tem os aros de ferro.
- **Barro e cerâmica:** estouram curto, com agudo médio (mais forte perto de 1,6 kHz, 40 dB em 130–180 ms): um estalo e alguns cacos. Nosso vaso ainda tem menos agudo que as gravações acima de 4 kHz.
- **Vidro:** agudo e longo (forte até 16 kHz, 40 dB em 0,3–0,9 s): um estouro e muitos cacos tilintando ao cair.
- **`hit`:** a pancada sem quebrar.

**Interface (`ui`, em `sfx/ui.py`): medida em sons de interface de jogos.**
- **Clique:** dura de 8 a 170 ms, um tique ou um baque suave.
- **Abrir a bolsa:** um farfalhar de 0,4 a 1 s.
- **Subir de nível:** um arpejo maior subindo, com as notas a 60–150 ms umas das outras, que termina numa nota longa e brilhante com brilhos por cima; 1,6–3,4 s no total.
- **Missão cumprida:** sobe o acorde mais devagar (~0,2 s por nota) e repousa na nota de cima.
- **Erro:** curto (0,14–0,6 s) e grave (por volta de Ré#3–Lá3), um zumbido ou dois tons descendo.
- **Estilos:** `fantasy`, com sinos de barra (modos 1 : 2,76 : 5,40 : 8,93), pano e madeira; `retro`, com notas de onda quadrada como num console de 8 bits.
- **Tom:** cada espécie (cada jogo) fica num tom perto de Dó5.

**Mundo (`lever`, `trap`, `torch`, `water`, em `sfx/world.py`): medido em gravações.**
- **Alavanca:** uma catraca de cliques a cada 40–70 ms por 0,3–0,5 s, médios (0,5–3 kHz, modos do mecanismo em ~330–1000 Hz), que termina num baque. Ao puxar, um mecanismo ronca em algum lugar.
- **Tocha:** acende com um raspado e uma labareda que vira crepitar (larga, 1–6 kHz, ~1 s). Apagar é um chiado.
- **Água:** um respingo é agudo (mais forte em 2,5–8 kHz, 0,2–1 s), com um "ploc" grave e gotas. O mergulho tem bolhas subindo depois.
- **Armadilha de espinhos:** sai com um "shing" metálico (modos de 5–8 kHz) sobre o mecanismo. Os dardos são voos curtos de flecha batendo na parede; a lâmina é um golpe pesado e lento.
- **Placa de pressão:** a pedra afunda e uma trava solta.

**Ambientes (`ambience`): comparados com gravações reais** (ESC-50, 8 clipes por lugar, só para análise). Comparamos o espectro por oitava, a variação lenta e rápida de volume, os eventos por segundo e o fator de crista. Os loops da primeira versão erravam assim:
- **Chuva:** faltava o chiado grave-médio da água batendo nas superfícies (250–1000 Hz estava 8–16 dB abaixo).
- **Vento:** estava agudo demais, centrado no assobio de 1 kHz. O vento gravado é sobretudo grave (mais forte em 250 Hz, −20 dB em 4 kHz).
- **Fogo:** faltava o ronco grave (63–125 Hz). Os estalos eram muitos e fracos; agora são menos e mais fortes, e o fator de crista foi de 19,5 para 27 dB (real: 28).
- **Caverna:** o ronco grave estava ~20 dB alto demais, e as gotas eram poucas (1,4 por segundo; real: 3,8).
- **Noite:** faltavam os insetos agudos (8–12,5 kHz).
- **Tempestade:** ganhou um trovão grave rolando sob a chuva. Os clipes reais são quase só trovão; o nosso loop continua sendo chuva com trovão.
- **Vento (refeito sem a busca do CLAP):** em gravações CC0 de vento, o corpo é mais forte perto de 250 Hz, as rajadas vêm a cada 3–10 s e sobem 4–11 dB, e o assobio é leve (3–9 dB acima do espectro). A versão guiada pelo CLAP tinha um assobio estreito e quase não variava (1–2 dB). Agora as rajadas sobem e voltam, e o assobio acompanha a altura da rajada.
- **Trovão (`magic.thunder`, refeito com gravações):** um ronco mais forte perto de 250 Hz (−12 dB em 1 kHz, −25 em 2 kHz) que dura 2,5–5 s e rola, com uma rajada nova a cada ~0,3 s, 6–12 dB acima do fundo. Um raio caindo perto rasga antes com alguns estalos secos. A versão anterior tinha tirado os estalos porque o CLAP os ouvia como fogo, e rolava só 4 vezes.

O mar e a floresta já estavam perto. Com amostras CC0 do Freesound (só para análise), também foram refeitos:
- **Riacho:** largo em 0,5–8 kHz (mais forte em 1–4 kHz), com pouco grave e bolhas destacadas sobre o chiado (crista ~21 dB).
- **Masmorra:** o fundo respira, com o volume subindo e descendo 3–8 dB.
- **Coruja:** cinco pios quase puros (corujão-orelhudo, 340–400 Hz): dois curtos e três longos.
- **Passarinhos:** em vez da voz de criatura, frases de 3–8 elementos entre 2 e 7 kHz: assobios, varreduras de uma oitava em 20–60 ms e trinados. Cada espécie tem seu registro.
- **Gotas na caverna:** 0,75–5,4 kHz, soando 10–35 ms.
- **Correntes:** elos pequenos tilintando 3–15 vezes por segundo, mais fortes em 8–12,5 kHz. Antes eram ferro grave.
- **Fogueira, evento solto:** o que se destaca nas fogueiras CC0 é uma bolsa de seiva estourando: 20–140 ms, mais forte em 2–12 kHz (−8 a −14 dB em 0,5–1 kHz) e 20–30 dB acima do fundo, às vezes com faíscas. O antigo "tronco assentando" durava 1,5 s e era mais forte em 1–2 kHz. Agora o evento é o estalo; em ~30% das vezes vem junto uma tora mudando de lugar, com uma batida grave.
- **Grilos da noite:** conferidos com o ESC-50. Portadoras de 3–10 kHz e pulsos de 8–62 Hz em trinados de 2–4 por segundo; os nossos (4,2–4,8 kHz, ~35 Hz, ~3 por segundo) já estavam dentro da faixa.

**Explosões (`explosion`): comparadas com gravações.**
- **De perto:** mais fortes em 63–250 Hz (−9 dB em 1 kHz, −14 em 4 kHz). Crescem por ~0,1 s e caem 20 dB em ~0,8 s. A primeira versão tinha um buraco em 125–250 Hz e um rugido alto demais perto de 1 kHz; ganhou um "corpo" grave e o crescimento inicial.
- **De longe:** quase só o ronco mais grave (mais forte em 31 Hz, −34 dB em 2 kHz).
- **Destroços (refeitos sem o CLAP):** em quedas de pedra CC0, a chuva de pedras dura 3–10 s, com 5–19 impactos por segundo, mais densa no começo e rareando sem parar de vez. As pedras grandes batem grave (63–250 Hz). A versão antiga era uma nuvem curta de estalos; agora são 14–24 pedras de tamanhos sorteados, cada uma com seu baque, por cima de uma chuva de cascalho (12–15 impactos/s medidos).

**Magias (`spell`): comparadas com efeitos de magia de jogos** (não existem gravações reais de magia, então a régua são sons desenhados por outros).
- **Fogo:** a bola de fogo de referência é sobretudo grave (centroide ~280 Hz). A nossa era um chiado médio-agudo; ganhou o ronco grave ao sair da mão e no impacto.
  Em viagem, loops de chama CC0 são mais fortes em 63 Hz (−20 a −30 dB em 1–4 kHz). O nosso tinha o pico em 500 Hz; agora é um ronco grave com o crepitar por cima.
- **Gelo:** tinha só agudo. O lançar ganhou corpo nos médios (a geada se formando); o impacto ganhou o baque do bloco, com menos cacos lá em cima.
- **Raio:** o impacto era só trovão grave (centroide ~100 Hz). Agora o raio cai primeiro, com estalo brilhante e crepitar, e o trovão rola depois.
- **Cura:** os sinos tinham um ronco grave por baixo (a nota "hum" do sino). Agora são carrilhões de vidro sobre um coro baixinho.
- **Arcano:** a queda de tom ia até 40–55 Hz e deixava um buraco nos médios, onde as magias genéricas concentram energia. Agora termina mais alto, com o acorde cintilando junto.
- **Sagrado (refeito sem o CLAP):** nas fanfarras angelicais CC0, vozes puras entram uma a uma subindo um acorde maior (dó, mi, sol, dó), 0,3–0,5 s uma da outra. A nota mais nova lidera e o acorde se sustenta por 2,5–3,5 s, com −17 a −19 dB em 2 kHz. Os "brilhos" são um cacho de sininhos em 2–3 kHz batidos de novo e de novo. A versão antiga durava 1 s e tinha o ronco grave de um sino; agora o lançar sobe o acorde, o impacto soa o acorde inteiro com vozes mais altas subindo por cima, e os sininhos cintilam acima.
- **Sombra (refeita sem o CLAP):** nas magias sombrias CC0, a energia fica em 250–500 Hz (63 Hz a −27 dB), e uma voz pula entre as notas de um acorde diminuto (fundamental, terça menor, trítono) umas 10 vezes por segundo. O eco junta tudo num cacho que bate. A versão antiga era quase toda sub‑grave (mais forte em 63 Hz, buraco em 125–250 Hz).
- **Natureza (refeita sem o CLAP):** não há magia de natureza gravada, então a régua são gravações reais do que ela mexe:
  - folhagem farfalhando: mais forte em 2–8 kHz, −9 a −14 dB em 125–500 Hz;
  - árvores rangendo: atrito de ~90 Hz passando por ressonâncias da madeira em 0,8–1,8 kHz;
  - raízes arrancadas: ronco terroso em 63–250 Hz.

  A versão antiga tinha bolhas d'água e um coaxar; agora é folhagem com rajadas, troncos rangendo e, no impacto, a terra se abrindo.
- **Carregar e viajar:** cargas abertas (32 sons de "charge up", risers) variam demais para servir de régua. Umas crescem até o fim, outras têm pico no meio e somem, e o brilho sobe de −3 a +5 oitavas. As nossas cargas ficam dentro dessa variação e foram mantidas. Os loops de projétil mágico também variam muito; só o fogo tinha um erro claro.

**Passos (`footstep`): medidos em gravações de caminhada.** Cada passo foi recortado das sequências, e cada chão tem a mediana de 16 a 46 passos.
- **Pedra:** um toque grave-médio (mais forte em 250–500 Hz) com o clique da sola dura; −20 dB em ~33 ms.
- **Madeira:** mais grave e mais longa (mais forte em 250 Hz, −20 dB em ~51 ms). O calcanhar e a ponta do pé ficam ~60 ms separados, e às vezes o chão range.
- **Cascalho:** quase sem grave (−21 dB abaixo de 300 Hz), com uma crocância mais forte em 1–1,6 kHz e ~150 ms de grãos.
- **Grama:** aguda, um farfalhar centrado perto de 8 kHz que dura ~0,35 s, com um baque grave suave.
- **Neve:** um baque grave forte (250 Hz) sob uma crocância que range, em 1–2,5 kHz.
- **Metal** (chapas e escadas, quase sempre abafados): grave e ressoando, mais forte abaixo de 300 Hz.
- **Terra:** grave-médio, curta (−20 dB em ~24 ms), com grãos finos.
- **Água:** nenhum grave; os respingos são mais fortes em 2,5–5 kHz.

As camadas (baque, contato da sola, clique, chão, grãos, farfalhar, respingos) são as mesmas para todos os chãos. Os ganhos foram ajustados renderizando e comparando até o espectro mediano de cada chão bater com as gravações (±5 dB por faixa de terço de oitava). A versão anterior, guiada pelo CLAP, era aguda demais (+8 a +20 dB acima de 2 kHz) e durava três a seis vezes mais. Um atrito baixinho da sola rolando mantém os agudos vivos por mais tempo, como nas gravações.

Mesmo com o espectro batendo, o juiz CLAP ainda não reconhece nossos passos: ouve "bola quicando" e "pau batendo em madeira". Acrescentar sala ou reverberação não mudou isso. As gravações reais ele reconhece (6 de 8).

**Calibração da primeira versão (histórico).** Os primeiros efeitos foram desenhados ouvindo o CLAP otimizador e conferidos com o juiz. O CLAP saiu do processo: os efeitos agora são medidos e imitados a partir de gravações reais e amostras abertas, e julgados de ouvido. O que segue registra a primeira versão; as partes guiadas pelo CLAP (vento, trovão, passos) já foram refeitas.
- **Conjunto de rótulos:** cerca de 80 descrições (efeitos, lugares e distratores como fala, música e "8-bit").
- **Teto:** gravações reais do ESC-50 (8 por categoria, só para análise, CC BY-NC) dão a referência do que o CLAP reconhece com esses rótulos: passos 6/8 em primeiro, vidro quebrando 8/8, fogueira 8/8, chuva 6/8, trovão em 1º ou 2º.
- **Comparação de espectrogramas com o real:**
  - o vidro quebrando real é uma explosão de ruído de banda larga, não tons puros (antes soava como "sininhos");
  - o trovão real é um ronco longo até ~1 kHz, e um estalo ou crepitar por cima faz soar como fogo;
  - fogueira pede estalos densos.
- **Passos:** uma busca guiada pelo CLAP encontrou a primeira estrutura de cada superfície. Foi substituída pela medição de gravações (veja "Passos").

**Resultado no juiz** (2 identidades por estilo, 80 rótulos; o acaso ficaria em ~1% para o 1º lugar):

| família | 1º | top 3 | destaques | fracos |
|---|---|---|---|---|
| magia | 50% | 80% | carga, disparo e trajeto de quase todos os elementos; impacto de fogo, arcano, sombra | impacto do raio, trajeto arcano |
| armas, arco, explosões | 29% | 45% | golpes em carne e madeira, golpes no ar, flechas, explosão distante | choque de espadas ("espada acertando armadura"), sacar e derrubar a espada, maça em metal/pedra, disparo do arco |
| ambientes | ~30% | ~40% | loops de chuva, caverna, noite, tempestade e mar em 1º | quase todos os eventos soltos |
| passos | 0% | 0% | — | todos |

Os loops têm 16 s, e o CLAP recorta aleatoriamente áudios com mais de 10 s, então os números dos ambientes variam um pouco entre execuções.

**O que a busca guiada pelo CLAP ensinou:**
- **Quando o juiz confirma, adotamos:** rangido do arco (do 22º para 6º–9º lugar no juiz) e vento (do 9º–10º para 3º–4º).
- **Quando o otimizador gosta e o juiz não, descartamos.** No choque de espadas e na queda da espada, a busca levou o otimizador ao 2º–5º lugar, mas o juiz ficou em 20º–40º. Os dois modelos discordam sobre impactos metálicos, que eles separam mal ("espadas se chocando" × "espada acertando armadura").
- **Passos:** a busca sobre sequências de caminhada levou o cascalho ao 1º lugar no otimizador, mas o juiz ficou em 8º–10º; pedra, madeira e grama não chegaram ao top 10. A estrutura encontrada está em `physical.STEPS`. Nossos passos ainda soam como impactos ("bola quicando", "flecha na madeira").

## Música e composição

**`Score`.**
- Cada faixa é uma `Voice`: suas notas são camadas do spec renderizadas juntas e sem eco.
- O `Score` põe cada faixa e cada som pronto no estéreo com a lei de potência constante (centro a −3 dB em cada lado).
- Uma parte de cada um (`send`) vai para uma sala compartilhada: duas caudas de ruído decorrelacionadas, uma por ouvido, escurecidas acima de 5 kHz, com energia unitária e 12 ms de silêncio antes das primeiras reflexões.
- `render(loop=...)` corta no comprimento exato e soma o que soa além dele (notas e cauda da sala) de volta no começo: o loop repete sem emenda.

**Instrumentos: medidos em notas soltas da VSCO-2 CE** (CC0, só para análise). Para cada nota gravada:
- os parciais como razões da nota, com nível e T60 (ajuste da queda em dB do pico até −30 dB);
- o tempo até −20 e −40 dB.

Para os sustentados:
- os 8 primeiros harmônicos na parte estável;
- vibrato (taxa e profundidade);
- tempo de ataque.

O som nosso é medido do mesmo jeito.

*Barras e sinos (`Modal`).* Cada um ganhou só os modos medidos.
- **Glockenspiel:** barra livre 1 : 2,9 : 5,5 : 9,0 (as razões teóricas são 1 : 2,76 : 5,40 : 8,93). A nota soa 9 s em sol5 e ~2 s em dó8; os parciais morrem em menos de 1 s. A versão antiga (`ui.chime`) soava só ~1 s.
- **Marimba:** afinada 1 : 4 : 10. Soa 8,6 s em dó3 e 0,5 s em dó7. O décimo parcial é o mais forte no ataque das notas graves, e a baqueta de lã corta acima de ~2 kHz.
- **Xilofone:** 1 : 3.
- **Sinos tubulares:** modos de viga (1,22 : 2 : 2,93 : 4,06 : 5,31…). A nota ouvida fica uma oitava abaixo dos modos 4–6, que estão em 2 : 3 : 4.

Para que cada modo comece exatamente no seu ganho, um contato menor que 3 amostras virou um impulso ideal (`Modal.hits`).

*Cordas pinçadas.* Parciais harmônicos com queda dupla: uma parte rápida e um som residual 14 dB abaixo (o outro plano de vibração da corda), que mantém o grave soando.
- **Harpa:** 1/√h, perdendo os agudos acima de ~500 Hz. A fundamental soa 15 s em lá2 e ~1,5 s em lá6.
- **Violão:** harmônicos quase iguais até o 10º, com entalhes pela posição do dedo; −20 dB em ~0,3 s.
- **Alaúde:** pares de cordas (ordens) desafinados 2–4 cents.

*Percussão*, com as medidas e o que o nosso dá:

| instrumento | gravado | nosso |
|---|---|---|
| tímpano: modo afinado com 1,5, 1,98 e 2,44 por cima | −20 dB em 0,17–0,22 s | 0,10–0,26 s |
| tambores de mão | −20 dB em 0,15–0,27 s | 0,16–0,18 s |
| bumbo de concerto | 63–125 Hz, −20 dB em ~0,09 s | 0,105 s |
| caixa com esteira | pico em 250 Hz, plano até 4 kHz, −20 dB em 65–75 ms | 85 ms |
| prato | 2–8 kHz, −20 dB em 0,5–0,6 s, −40 em ~2 s | 0,6 s e 1,7 s |
| pandeiro | 4–12 kHz, −20 dB em 0,2–0,27 s | 0,2 s |

*Sustentados.* Uma fonte glotal passa pelas ressonâncias do corpo. Essas ressonâncias foram ajustadas por análise-por-síntese para que os 8 primeiros harmônicos das nossas notas batam com os gravados em toda a extensão. Os limites são físicos: 150–8000 Hz, largura ≥ 150 Hz, ganho ≤ 3. Sem limites, o otimizador inventava ressonâncias de 25 Hz que só serviam para as notas medidas. Erro médio por harmônico:

| instrumento | erro | outras medidas |
|---|---|---|
| violinos | 1,8 dB | naipe de 3 vozes a ±8 cents, cada uma com seu vibrato (~5 Hz) |
| violoncelos | 3,8 dB | |
| flauta | 5,2 dB | quase pura no agudo, rica no grave, vibrato 5 Hz ±7 cents |
| trompa | 6,3 dB | |
| trompete suave | 2,8 dB | |
| trompete forte | 4,3 dB | |

No trompete, o brilho segue a intensidade, interpolando entre os dois ajustes: uma ressonância perto de 670 Hz quando suave, abrindo para 1,2 e 2 kHz quando forte.

Para não refiltrar bloco a bloco, ressonâncias fixas (boca parada) usam um filtro só por formante.

**Composição (`Cue`).**
- A semente escolhe tom (sol3 a fá♯4) e modo, a progressão (I–IV–V–I, i–VI–VII–i…), os ritmos e o motivo.
- A melodia segue regras simples:
  - notas do acorde nos tempos fortes, perto da nota anterior e sem repetir;
  - passos nos fracos, subindo no começo da frase e descendo no fim, rebatendo nas bordas da extensão;
  - o ritmo de abertura volta a cada dois compassos;
  - toda frase de 4 compassos termina numa nota longa, e a última na tônica;
  - sobre a dominante, em tom menor, a sétima sobe (menor harmônica).
- Os acordes do acompanhamento mudam com o menor movimento possível de voz.
- O arranjo é escrito em papéis (melodia, metais, cordas, harpa, baixo, tímpano, caixa…). O estilo transforma cada papel num instrumento medido ou num canal de console (pulsos com `crush`, baixo senoidal, ruído).
- Os jingles deixam o último acorde soar 3 s e somem em 1,5 s; os loops têm comprimento exato em compassos.

**Banda (medida em notas CC0 do Freesound).**
- **Baixo elétrico:** os dois primeiros harmônicos iguais, o 3º fraco (−17 a −34 dB, o dedo perto do nó dele) e o 4º forte de novo. Soa longo (−20 dB em 1,6–3 s), e a mão o abafa quando a nota acaba: `Modal.damp` derruba 60 dB em 0,1 s.
- **Piano elétrico:** o 1º e o 2º harmônicos próximos (−2 e 0 dB), o 3º 10–12 dB abaixo e o "sino" da lâmina perto do 8º. Tocado forte, os harmônicos de cima sobem.
- **Chimbal:** fechado, cai 20 dB em 65–130 ms; aberto, em ~0,5 s; mais forte em 4–12 kHz.

**Harmonia de cor (as músicas no jeito das trilhas de 16 bits).** O tema veio de uma análise de *Chrono Trigger* ("Nonfunctional Harmony in Chrono Trigger", 8-bit Music Theory): acordes escolhidos pela cor, não pela função.
- As paletas tocam um acorde por compasso, nenhuma apoiada em V → I:
  - I–II maj9 (o 4º grau sobe, lídio);
  - mediantes cromáticas (I–♭VI–♭III);
  - maj9 descendo meio tom até i m9;
  - i–♭VII–♭VI–v (eólio, sem dominante);
  - i m9–IV9 (dórico);
  - I–♭VII–IV (mixolídio);
  - I–♭VI–♭VII–I (heroico);
  - i–♭II–i–♭VII (cromático, para batalha).
- **Voicing aberto:** a fundamental no grave, 3ª e 7ª perto do dó central, 5ª e extensões em cima, tudo deslocado por oitavas para ficar perto do acorde anterior. Com `planed`, a mesma forma desliza em paralelo para a nova fundamental.
- **Melodia:**
  - cada frase de 8 compassos faz um arco (sobe até o meio, assenta no fim);
  - nos tempos fortes vão notas do acorde ou de cor (9ª, 11ª, 13ª); nos fracos, passos na escala, nunca meio tom acima de uma nota do acorde;
  - os compassos 2–3 repetem o motivo em sequência, movido com a harmonia, ou um tom acima quando o acorde não muda;
  - o compasso 6 traz o motivo de volta, e o 7 repousa numa nota de cor.
- **Som de 16 bits (`snes`):** sala pequena, agudos escurecidos acima de 9 kHz e o eco do console. As repetições vêm a cada ~210 ms, perdem 45% e ficam mais escuras a cada volta, indo de um ouvido ao outro (`Score(echo=...)`, envio por faixa).
- As composições são originais: usam as técnicas, não as melodias do jogo.

## Calibração com CLAP

`clap.py` carrega dois modelos CLAP pelo `transformers`: o **otimizador** (`laion/clap-htsat-unfused`) e o **juiz** (`laion/larger_clap_general`), que fica fora de toda otimização. `LABELS` liga 22 descrições em inglês ("a cat meowing", "a monster growling", "an 8-bit video game sound effect"...) aos arquétipos que deveriam ganhá-las.

**Busca** (`designer.py`). Os genes de um arquétipo são descobertos rodando o design com um `Genome` espião (12 espécies × 3 traços × todos os chamados). A busca é uma estratégia evolutiva (1+1) com a regra de 1/5 sobre genes, tamanho e agressividade:
- `design(prompt)`: maximiza a similaridade CLAP com o texto. Primeiro avalia `screen` candidatos por arquétipo, depois refina os 2 melhores.
- `match(amostra)`: similaridade CLAP com a gravação menos `feature_weight ×` a distância de `analysis.features`. As medidas são tom (YIN com correção de oitava/quinta), envelope de loudness, espectro de longo prazo, duração, aperiodicidade, fração vozeada e número de segmentos.
- Os genes encontrados viram genes fixos da espécie (`genes`). Fixar um gene muda o valor base, mas a variação por indivíduo e por take continua.

**Resultado com o juiz** (120 sons: por arquétipo, 2 espécies fora da calibração × 3 tamanhos × 2 chamados):
- **Acerto do arquétipo:** 32% (acaso: cerca de 10%). `chip` 100%, `reptile` 58%, `slime` 50%; mamífero, pássaro, inseto e robô ficam abaixo de 10%.
- **"Som 8-bit de videogame":** 56% dos sons não-chip recebem esse rótulo. O alvo, então, era soar menos sintético.
- **Camada de realismo** (`lowpass`, `room`, `air`, `shimmer` + mais jitter e sopro), ajustada pelo otimizador em 70 iterações: no conjunto de calibração, o acerto foi de 30% para 45%. No juiz, o "8-bit" caiu de 56% para 46%, mas o acerto ficou em 32% e a probabilidade média do rótulo certo caiu de 0,33 para 0,30. Inseto, monstro, réptil e robô melhoraram; slime, espírito e anfíbio pioraram.
- **Decisão:** a camada fica disponível (`REALISM_CLAP`), mas desligada por padrão. Para o juiz, o problema de reconhecimento está no desenho dos arquétipos, não na falta de "gravação".

## As duas formas de uso

**Offline (assets).** `creaturesynth bake bestiario.json -o pasta` gera:

```
pasta/manifest.json
pasta/<criatura>/<chamado>_<take>.wav   (+ .json com o spec)
```

```json
{"format": "creaturesynth.bake", "version": 1, "sample_rate": 48000, "takes": 3,
 "calls": ["idle", "alert", "attack", "hurt", "death"],
 "creatures": {"wolf": {"creature": {"archetype": "mammal", "species": 2183285651, "size": 0.45, ...},
                        "calls": {"hurt": [{"file": "wolf/hurt_00.wav", "duration": 1.1447,
                                            "peak": 0.6989, "spec": "wolf/hurt_00.json"}, ...]}}}}
```

Na engine, cada chamado vira um "random container" (FMOD/Wwise) ou um array de clips sorteado sem repetir o último.

**Runtime.** Há três níveis, do mais simples ao mais procedural:

1. **Jogo em Python:** `VoiceBank` gera on-demand com cache e threads. Use `warm()` no loading.
2. **Engine nativa tocando specs:** o design fica no Python (specs vão junto do jogo, são pequenos) e a engine só porta o `render`, cerca de 170 linhas de DSP simples.
3. **Engine nativa 100% procedural:** porta também `rng`, `genome`, `calls` e os arquétipos, que são só aritmética. Aí o jogo inventa criaturas novas em tempo real (spawn procedural, mutações, evoluções), com o mesmo spec que o Python geraria.

## Fala humana

```
texto ─► g2p (pt: regras | en: CMUdict + regras) ─► frases/palavras/sílabas de fonemas
      ─► phonetics.segments: duração por fonema (tônica, fim de frase, velocidade),
         oclusivas = fechamento + explosão + aspiração, fricativas, nasais...
      ─► grade de 1 ms: alvos por segmento, suavizados (coarticulação):
         formantes 28 ms, semivogais/líquidas 80 ms, F1 abrupto na soltura de nasais
      ─► entonação: declinação + acentos nas tônicas + contorno final por tipo de frase
      ─► SpeechProgram (trilhas a 400 Hz) ─► klatt.render_speech
```

**Escolhas regionais** (constantes do módulo):
- **"r" em final de sílaba** (`g2p_pt.CODA_R`): `"R"`, fricativo como no Rio (padrão), ou `"r"`, tap como em São Paulo.
- **"r" forte** (`phonetics.R_STYLE`): `"x"`, velar (padrão), ou `"h"`, glotal.
- **Inglês:** americano geral, com flap em "water" e "l" escuro no fim de sílaba.

**Como foi afinado:** com o Whisper como "ouvido" (`tools/intelligibility.py`), comparando versões A/B num conjunto fixo de frases de jogo. Um teste mostrou que a fricção estava ~10 dB abaixo do natural; outro achou o clique de troca de coeficientes. Execuções idênticas do Whisper variam cerca de ±0,03 de CER, então diferenças menores que isso não significam nada.

**Professor natural (Kokoro).** `tools/teacher_calibration.py` gera 60 frases pt-BR com o Kokoro (vozes masculina e feminina, ~5 minutos). As frases são diferentes das frases de teste. Como o Kokoro informa a duração prevista de cada fonema (quadros de 25 ms), o alinhamento sai de graça. A ferramenta mede:
- formantes de vogais tônicas longas;
- durações por tonicidade;
- o espectro do trecho ruidoso das fricativas.

O que se aprendeu, sempre conferindo com o Whisper em A/B:
- **Fricativas:** confirmaram os valores que já usávamos ("s" ~6,3 kHz, "f" ~7,5 kHz). "Ch"/"j" ficaram em ~3,15 kHz e o [x] em ~2,1 kHz, mas aplicar esses valores não mudou a inteligibilidade além do ruído.
- **Vogais:** copiar os formantes medidos piorou (CER 0,24 → 0,34). Na fala corrida a vogal não alcança o alvo, e nosso sintetizador já suaviza os alvos; copiar as medidas encurtaria a vogal duas vezes. O ritmo mais rápido do Kokoro também piorou.
- **O ganho real veio do texto, não da acústica.** Comparando as transcrições do professor com as nossas, apareceu um erro sistemático: o "e"/"o" tônico sem acento era sempre fechado. Agora ele abre:
  - antes de "r"/"l" no meio da palavra (porta, certo);
  - em "-el"/"-ol" finais (papel, sol);
  - em paroxítonas terminadas em "-a" (nossa, janela, guerra);
  - ficam de fora uma lista de exceções e os sufixos "-esa"/"-eza"/"-oa".
- **Teto:** o Whisper transcreve o próprio Kokoro com CER 0,003. A distância que resta para o nosso motor está na estrutura (fonte glotal, explosões, coarticulação), não nos valores das tabelas.

`phonetics.LANG_PHONES` guarda ajustes por idioma sobre a tabela comum. Está vazio para o português, porque nenhum ajuste acústico passou no A/B.

**Estrutura: comparação quadro a quadro com o Kokoro** (`tools/structure_analysis.py`). O alvo era a naturalidade. A mesma frase é dita pelo nosso motor e pelo professor (vozes `pm_alex` e `pf_dora`, com pitch e trato equivalentes). Os quadros de 10 ms são alinhados por DTW sobre mel-cepstro, e então se compara o espectro de cada classe de fonema. São dois juízes independentes:
- **Whisper:** inteligibilidade, nas 16 frases de `tools/intelligibility.py`;
- **UTMOS:** preditor de MOS do VoiceMOS 2022, licença MIT, que dá uma nota de naturalidade de 1 a 5.

As frases se dividem em treino e validação (uma em cada três fica fora). No UTMOS, o professor tira 3,5 e o nosso motor 2,2.

*Diagnóstico.* A cascata de 5 formantes vem do desenho original de Klatt, pensado para 10 kHz. Acima do F5 cada ressonador derruba 12 dB/oitava, então nossas vogais ficam de 25 a 75 dB abaixo do professor acima de 3,5 kHz. Fora isso:
- nasais ficam ~10 dB fracas nos médios;
- fricativas sonoras, ~10 dB fortes;
- explosões, ~6 dB fortes;
- os formantes mudam em degraus, enquanto os do professor se movem o tempo todo.

*Ajuste estrutural pelo espectro.* Uma estratégia evolutiva ajustou 13 constantes estruturais para minimizar a distância espectral: formantes fixos acima do F5 até 11,5 kHz, larguras de banda, coarticulação, níveis de fricção e explosão, sopro e tilt. A distância espectral fora do treino caiu de 54,5 para 29,4. Mesmo assim, os dois juízes pioraram:

| | distância espectral | UTMOS | CER pt (Whisper) |
|---|---|---|---|
| atual | 54,5 | 2,20 | 0,27 |
| ajuste espectral | 29,4 | 1,51 | 0,35 |

Na ablação, a queda do UTMOS vem dos formantes superiores (−0,24), das bandas largas (−0,16) e da coarticulação mais rápida (−0,13). Ficar parecido com o espectro do professor deixa o som mais claro e móvel, e isso expõe os defeitos que sobram.

*Alvos de formantes por análise por síntese.* Em cada rodada, medimos F1-F3 com o mesmo rastreador LPC no que renderizamos e nos quadros do professor alinhados a eles, e movemos os alvos da tabela. Assim o viés do rastreador se cancela e o undershoot da nossa coarticulação entra na conta. Em 4 rodadas, a diferença fora do treino caiu de 0,088 para 0,039 (log). O UTMOS não mudou (2,18) e o Whisper piorou (0,27 → 0,30). Foi a mesma conclusão de copiar medidas: a geometria de formantes do professor não serve ao nosso motor.

*Otimizando direto para o UTMOS* (14 constantes globais, incluindo prosódia e velocidade): o treino foi de 2,32 para 2,33, e a validação caiu de 2,18 para 2,14. Nenhum ajuste global move a naturalidade; é um platô.

*Onde está a distância* (`structure_analysis.py transplant`). O professor é vocodado com WORLD, e uma peça nossa de cada vez entra no lugar da dele, alinhada por DTW:

| condição | UTMOS |
|---|---|
| professor / vocodado | 3,51 / 3,28 |
| + nossa curva de tom | 2,97 |
| + nossa aperiodicidade | 3,20 |
| **+ nosso envelope espectral** | **1,72** |
| nosso envelope só nas vogais e soantes / só nas obstruintes | 1,78 / 2,15 |
| só a forma média de longo prazo do nosso envelope | 3,06 |
| nosso motor (vocodado / original) | 2,11 / 2,19 |

A distância está no envelope espectral quadro a quadro, nas vogais e nas consoantes. Não está na forma média, nem na fonte, nem na entonação, que custa ~0,3.

*Teste de viabilidade.* Trocamos a cascata por envelopes aprendidos do professor: um molde por fonema e terço de segmento, interpolado no nosso ritmo e na nossa entonação, sintetizado com WORLD. O UTMOS deu 1,25-1,28, com a segmentação por DTW e também com a segmentação do próprio Kokoro. Moldes médios por fonema saem borrados. Esse caminho exigiria modelos por contexto (difones) ou um modelo neural pequeno, ou seja, outro motor.

*Conclusão.* Dentro da síntese de formantes por regras, nenhum ajuste de parâmetros fecha a distância para a voz natural. O motor de formantes continua com o papel em que é bom (minúsculo, estica para qualquer criatura, balbucio). Para a voz natural sem IA em tempo de execução, veio o motor natural, abaixo.

### Motor natural (`speech/concat.py`, `tools/build_speech.py`)

Síntese concatenativa com o nosso vocoder: o envelope espectral vem de gravações, as regras dão o resto (fonemas, ritmo, entonação). O Kokoro é só o professor: lê um corpus uma vez, offline, e o que fica são números.

**Banco de voz.** 240 frases por voz (as 60 de calibração + 180 de diálogo de jogo, foneticamente variadas, nenhuma das frases de teste), ~10,5 min. Cada leitura passa pelo WORLD (5 ms: tom, envelope em 32 faixas, aperiodicidade em 5) e é rotulada fonema a fonema pelo alinhamento do próprio Kokoro (passos de 25 ms), mapeado para os nossos símbolos: ditongos do misaki ("A" = [ej], "I" = [aj], "W" = [aw], "O" = [ow]) partidos em dois, vogal antes de [ŋ] nasal, [y]/[ɪ]/[ʊ] depois de vogal como semivogal. Cada fronteira anda até a maior mudança espectral em ±15 ms. Dois bancos em português: `pt/alex` (masculino, trato 1,0) e `pt/dora` (feminino, 1,15), ~3,4 MB cada.

**Montagem de uma frase nova:**
1. A nossa frente (g2p + `phonetics.segments`, que agora marca começo e fim de palavra) dá fonemas, tônicas e a entonação.
2. **Sotaque do professor** (`accent_pt`): alinhando a nossa transcrição com a do professor nas 240 frases, as diferenças caíram de 988 para 438 em 7.137 fonemas (94% iguais) com regras como: "r" de fim de sílaba vira tap, com um schwa curto antes de consoante dentro da palavra; "em" vira [ẽj] + [ŋ]; "lh" vira [lj]; "a" reduzido só na última sílaba de palavra longa ("a", "da", "na" ficam [a]); "a" tônico antes de m/n/nh nasaliza ("cama" [ˈkɐ̃mɐ]); "s" antes de consoante sonora vira [z]; [ŋ] depois de vogal nasal antes de fricativa ("cansado") e no fim de "sim", "um".
3. **Durações do professor:** regressão ridge em log da duração, com fonema, tônica, começo e fim de palavra, última palavra antes de pausa, vizinhos e interações (r = 0,50 no banco; o alinhamento de 25 ms limita).
4. **Seleção de unidades:** um pedaço do banco por difone (do meio de um fonema ao meio do seguinte). Custo de alvo: fonema certo ou substituto (tabela de grupos: [a]/[ɐ] 0,3, [e]/[ɛ] 0,3, [u]/[w] 0,1...), tônica, vizinhos e duração. Custo de junção: 0 se os pedaços são contíguos no banco; senão, a distância espectral média no meio do fonema (dB/10) + 0,2. Viterbi com os 25 melhores por difone. Quando o banco não tem o difone, junta meios de lugares diferentes.
5. **Junções:** o ponto de corte dentro do fonema é o par de quadros (entre 25% e 75% de cada pedaço) com espectros mais próximos; em volta dele, crossfade de ±15 ms em que cada pedaço continua com a própria dinâmica.
6. O tom da nossa entonação onde o banco tem voz; o vocoder refaz o som com `warp = trato do personagem / trato do professor`.

**Medidas** (Whisper, CER, frases fora do corpus):

| | CER |
|---|---|
| ressíntese direta de frases do professor pelo nosso vocoder, 32 faixas | 0,011 |
| primeira montagem, 60 frases no banco | 0,22 (masc.) / 0,34 (fem.) |
| 240 frases no banco | 0,17 / 0,18 |
| + sotaque do professor + durações por regressão | **0,11 / 0,11** |
| o mesmo, pelo `Speaker` (com jitter); NPCs sorteados (`Speaker.random(7)`, `(12)`) | 0,08 / 0,11; 0,12 e 0,10 |
| motor de formantes | 0,23 |

Onde ainda se perde (16 frases do corpus, deixando a própria frase fora do banco): com fonemas, durações e tom do professor, 0,046; com as durações do professor e o **nosso** tom, 0,035 (a entonação não atrapalha); com durações médias, 0,06-0,09; com a nossa transcrição, 0,13. O que falta está nas durações e nas diferenças de transcrição que sobraram (vogais abertas e fechadas, [u]/[w]).

**Balbucio** (`speech/babble.py`). Depois do g2p, as sílabas podem ser trocadas antes da prosódia, e por isso o ritmo, as tônicas e o tipo de frase continuam os do texto:
- `gibberish`: cada sílaba vira ataque + vogal sorteados do inventário do idioma, às vezes com coda no fim da palavra; a semente é a fala + o nome do personagem.
- `mumble`: toda sílaba vira "m" + schwa.
- `animalese`: mantém as sílabas, mas a voz fica 1,5× mais aguda, 2,2× mais rápida, com metade da entonação e uma nota aleatória (±5 semitons) por sílaba somada ao contorno.

**Elenco** (`speech/casting.py`). `cast(role, name, lang, gender, creature, voice, style, natural)` devolve um `Cast` (voz + estilo + papel) com `render()` e `voice()` (o spec). As regras:
- A voz é sorteada pelo nome; com `gender`, fica a primeira semente com pitch ≥ 165 Hz (f) ou ≤ 150 Hz (m).
- `main` usa o motor natural com essa voz (a não ser com `natural=False`); os outros papéis, o de formantes.
- `voice` explícita sempre vence. Os nomes antigos `kokoro:<id>` viram vozes naturais do mesmo registro (`pm_alex` → `pt/alex`, `pf_dora` → `pt/dora`).

O bestiário e o `bake` usam o elenco. O manifesto registra `role`, `style` e `engine` de cada personagem.

**Próximos passos da fala:**
- Bancos de voz em inglês (o mapeamento dos símbolos do misaki para o inglês ainda falta).
- Durações: um alinhamento mais fino que 25 ms deixaria a regressão melhor.
- Micro-prosódia: somar ao nosso tom o desvio do professor em cada pedaço.
- Mais idiomas: o front-end é plugável (`speech.LANGS`).

### Interjeições (`speech/emote.py`, `speech/vocoder.py`)

**Primeira versão: formantes.** As interjeições eram frames do sintetizador de formantes montados de segmentos (respiro, vogal, zumbido, chiado, explosão), medidos nas gravações abaixo. Soavam artificiais e robóticas: o mesmo limite da fala por formantes.

**Agora: performances reais, refeitas por nós.** Cada gravação CC0 é analisada uma vez, no desenvolvimento, com o vocoder WORLD (`tools/build_barks.py`, `pip install pyworld`). Ficam só números, a cada 5 ms: tom, envelope espectral e quanto é ar. São 183 moldes, 146 s de performance, 951 kB. No jogo, `vocoder.py` refaz o som com a nossa própria síntese em numpy (sem modelo nenhum, sem o WORLD) e o leva para a voz do personagem. É determinístico: o mesmo personagem, tipo, estilo e take dão as mesmas amostras.

**Fontes** (CC0; as gravações não estão no repositório):
- OpenGameArt: "Voice Clip Pack - Male Adventurer RPG", "Female RPG Voice Starter Pack" de Cici Fyre (três vozes) e "Male Grunt/Yelling sounds" (três vozes);
- Freesound: risadas, risadinhas, suspiros, sustos, "hm", "hã?", comemorações e gemidos de dor, por id (a lista está no `MANIFEST` de `tools/build_barks.py`; cada molde guarda a sua fonte).

**A síntese bate com a do WORLD.** Em 21 moldes, a energia por faixa fica em média a ±1 dB da síntese do próprio WORLD de 200 Hz a 24 kHz; num molde ou outro, uma faixa abaixo de 1,2 kHz chega a 9 dB de diferença. O vozeamento medido (harvest) é parecido: 0,71 contra 0,75 em média. Três detalhes fizeram diferença:
- o pulso cai entre amostras (atraso fracionário): sem isso, numa voz de 700 Hz o arredondamento vira 1,5% de jitter;
- o ar é ruído entre um pulso e o próximo, sem média, filtrado pelo envelope: abaixo do tom ele some, como no WORLD;
- abaixo do tom gravado, o envelope do CheapTrick não mede nada (lá chegou a ficar 20 dB acima das formantes). Ele é trocado pelo valor no tom, caindo 3 dB por oitava. Sem isso, uma voz levada para baixo ganhava um primeiro harmônico estourado, e cada começo de som, um baque grave.

**Levar para a voz do personagem.**
- Esforços (ataque, dor, morte, pulo, comemoração) mudam de voz pelo registro do grito: `pitch = grito(fala do personagem, trato dele) / grito(fala do intérprete, trato do intérprete)`. Os outros (risos, suspiros, "hm") mudam pela fala: `pitch = fala do personagem / fala do intérprete`. A fala de cada intérprete é estimada pelo trato que demos a ele: 115 Hz (homem, trato 1,0), 190 Hz (madura, 1,1), 210 Hz (mulher, 1,15), 260 Hz (fofa, 1,27).
- `warp = trato do personagem / trato do intérprete`, limitado a 0,75–1,35. `pitch` fica entre 0,4 e 2,5.
- A escolha do molde minimiza `|ln pitch| + 3·|ln warp|`, menos a preferência do estilo pelo intérprete. Mexer muito nas formantes é o que mais denuncia uma voz convertida, mais do que o tom. Por isso uma heroína sempre pega intérpretes mulheres e um herói, homens.
- Quando nenhum intérprete do tipo é próximo, entra um tipo parente, esticado e transposto, com custo +0,25. Exemplos: não há mulher com ataque forte (vira ataque × 1,5) e não há homem com risadinha (vira risada × 0,75, +4 st).
- O take sorteia entre os moldes a até 0,25 do melhor (no máximo 4), mais ±0,6 st de tom e ±6% de duração.
- A voz do `Speaker` entra também: `breath` e `whisper` viram ar; `tilt` (Hz) vira inclinação, `3·log2(tilt/3000)` dB/oitava; `range` vira `swing` (`range^0,7`, então o robô fala monótono); `rate` encurta. `crush`, `drive` e `space` passam para o `Voice`.

**Estilos:**

| estilo | tom | formantes | duração | ar | brilho (dB/oit) | contorno | prefere |
|---|---|---|---|---|---|---|---|
| `grunt` | 0 | 1,0 | 0,92 | +0,08 | 0 | 1,0 | aventureiro, gritos |
| `anime` | +1 st | 1,04 | 1,0 | −0,25 | +1 | 1,15 | voz fofa |
| `tactics` | −1 st | 0,98 | 0,88 | 0 | −0,8 | 0,85 | voz madura, takes curtos |
| `mmo` | +0,5 st | 1,0 | 1,12 | 0 | +0,5 | 1,1 | gritos |

`intensity` (0 a 1, base 0,7), nos esforços: de −2,1 a +0,9 st de tom, de −1,4 a +0,6 dB/oitava de brilho, de 0,79× a 1,09× de duração, e um pouco menos de ar quanto mais forte. Nos outros tipos, metade disso no tom e no brilho, e de 0,86× a 1,06× de duração.

**Medidas** das mesmas gravações, da primeira versão (continuam valendo para o registro do grito):

| interjeição | duração | tom | voz × ar | outras medidas |
|---|---|---|---|---|
| ataque | 0,15–0,35 s | homens +17 a +23 st sobre a fala, mulheres ~+10; reto, caindo no fim | 10–60% voz | 50–190 ms de respiro até o pico |
| dor | 0,2–0,4 s | sobe +1,5 a +3 st e desce | — | ataque rápido |
| morte | 1–2 s | alto, caindo devagar | 80–95% voz | — |
| pulo | 0,17–0,3 s | — | — | — |
| risada | — | — | — | pulsos de 4,5–5/s (homens), 5–6/s (mulheres); risadinha 6–8/s |
| suspiro | — | cai 2,5–3,5 st | quase só ar | — |
| "hm" | 0,9–2,8 s | sobe ~4 st na dúvida | nasal | — |
| "yay" | — | começa 2–3 st acima e cai | — | — |

**Registro do grito.** O tom de um esforço vai da fala em direção a um registro que depende do trato: f0 = fala^(1−e) · R^e, com R = 420 Hz · trato^1,8 e e ≈ 0,85 (0,55 no pulo). Calibrado nas gravações: um homem de 95 Hz grita a ~345 Hz; mulheres que falam a 230, 280 e 550 Hz gritam a ~430, ~530 e ~600 Hz.

## Motor da 1ª geração

`chip.py` emula os canais do Game Boy como o motor de gritos de Pokémon Red/Blue os usa:
- Notas em frames de 17.556 amostras a 1.048.576 Hz e envelope de volume de 4 bits.
- Byte de duty que gira 2 bits por frame.
- LFSR de 15 ou 7 bits, com ciclo detectado e cacheado.
- O ajuste de tom do ruído termina junto com os pulsos, e o ruído ignora o tempo (quirks do motor).

A decimação tem dois estágios (÷16, depois a razão exata), com filtros FIR em cache. Isso mantém qualquer taxa de saída rápida.

A verificação contra o motor TypeScript original está em `tests/test_chip.py`, com fixtures em `tests/fixtures/gen1`, geradas antes da remoção do código TS. O arquétipo `chip` usa o mesmo motor para criar gritos inéditos sem nenhum dado do jogo.

## Próximos passos

- Renderizador nativo: C# (Unity), GDExtension/C++ (Godot) ou JS/WebAudio (editor web), validado pelos goldens do `bake`.
- Editor visual: sliders de genes e traços, espectrograma e "evoluir" ao vivo.
- Qualidade: fonte glotal LF, IRs de reverb reais, normalização por loudness (LUFS) nos pacotes.
- Mais arquétipos (aquático, dragão dedicado, enxame) e mistura entre arquétipos (híbridos).
- Redesenhar os arquétipos que o juiz CLAP não reconhece (mamífero, pássaro, inseto, robô), medindo com `creaturesynth judge`.
- Efeitos fracos no juiz: passos, choque de espadas, eventos soltos dos ambientes. Comparar com gravações reais, como foi feito com vidro, trovão e fogueira.
- Levar `design`/`match` (CLAP) também para os efeitos sonoros, buscando genes por receita.
