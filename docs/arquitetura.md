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
| `spec.py` | `Voice`, `Syllable`, `ChipProgram`, `SpeechProgram` + JSON (v3) |
| `render.py` | DSP fonte-filtro |
| `chip.py` | motor Game Boy (2 pulsos + ruído) e leitor dos dados da 1ª geração |
| `creature.py` | API principal (`Creature`) |
| `bake.py` | uso offline: bestiário → WAVs + manifest |
| `runtime.py` | uso em jogo Python: `VoiceBank` |
| `cli.py` | linha de comando |
| `speech/` | fala humana: `g2p_pt.py` e `g2p_en.py` (texto → fonemas), `phonetics.py` (alvos, coarticulação, entonação), `klatt.py` (síntese), `babble.py` (balbucio), `casting.py` (qual motor fala), `neural.py` (Kokoro), `Speaker` |
| `clap.py`, `designer.py`, `analysis.py` | calibração: CLAP (texto ↔ som), busca evolutiva (`design`, `match`), medidas de gravações |
| `sfx/` | efeitos sonoros: `Sfx`, materiais e `Fx` (`__init__.py`), `physical.py` (armas, passos, explosões), `magic.py`, `ambience.py` |
| `layers.py` | DSP dos efeitos: corpos modais, faixas de ruído com filtro móvel, nuvens de eventos |

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

Specs das versões 1 a 3 continuam sendo lidos.

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

**Coeficientes variáveis sem clique:** entre blocos, os filtros carregam o histórico de forma direta I (duas entradas e duas saídas) e recalculam o estado para os coeficientes novos (`render.time_varying`). Reaproveitar o estado do `lfilter` através de uma troca de coeficientes gera um estalo audível a cada transição de fonema.

**Validar uma port:** os fluxos aleatórios devem bater bit a bit (vetores de teste). O áudio não será bit-exato, por ordem de operações em ponto flutuante e convolução por FFT. Para ter material de comparação, rode `creaturesynth bake` com specs: cada entrada do manifest traz o spec e o WAV de referência. Renderize os specs na engine e compare os espectros. Com `space = 0` a diferença deve ser mínima.

## Efeitos sonoros

`Sfx(kind, style, species, size, power)` é o `Creature` dos efeitos. O `kind` escolhe a receita (`@recipe` em `sfx/`), o `style` o material, o elemento ou o lugar. A `species` é a identidade do objeto: os modos desta espada e o tom desta magia ficam fixos (genes por nome, como nas criaturas), enquanto cada take sorteia o resto (onde o golpe pega, o tempo entre os contatos). O design só monta um `Voice`, então `bake`, `VoiceBank`, specs e ports funcionam igual.

**Materiais** (`MATERIALS`): faixa de modos (o mais grave depende do tamanho), número de modos, T60 do mais grave, amortecimento (`T60·(f/f₀)^−d`), dureza do contato, distribuição e uma frequência abaixo da qual o corpo irradia pouco.
- **Distribuições:** `dense` para lâminas e placas de metal, `sparse` para madeira, pedra e vidro, `bell` para sinos com terça menor, `string` para harmônicos com leve rigidez.
- **Irradiação:** é o que faz uma espada soar como "shiiing" agudo e não como sino.

**`AmbiencePlayer`** (runtime): toca o loop do lugar sem parar e agenda eventos com intervalos exponenciais (processo de Poisson com `per_minute`). Cada evento tem alguns takes renderizados em segundo plano e é pulado se não estiver pronto; a saída passa por `tanh`, para um trovão sobre a chuva não estourar.

**Calibração.** Os sons foram desenhados ouvindo o CLAP otimizador e conferidos no fim com o juiz, que não participou de nenhum ajuste, como na calibração das criaturas.
- **Conjunto de rótulos:** cerca de 80 descrições (efeitos, lugares e distratores como fala, música e "8-bit").
- **Teto:** gravações reais do ESC-50 (8 por categoria, só para análise, CC BY-NC) dão a referência do que o CLAP reconhece com esses rótulos: passos 6/8 em primeiro, vidro quebrando 8/8, fogueira 8/8, chuva 6/8, trovão em 1º ou 2º.
- **Comparação de espectrogramas com o real:**
  - o vidro quebrando real é uma explosão de ruído de banda larga, não tons puros (antes soava como "sininhos");
  - o trovão real é um ronco longo até ~1 kHz, e um estalo ou crepitar por cima faz soar como fogo;
  - fogueira pede estalos densos.
- **Passos:** uma busca guiada pelo CLAP sobre sequências de caminhada encontrou a estrutura de cada superfície (`physical.STEPS`).

**Armas: ajuste contra gravações reais.** O CLAP é um juiz ruim para foley de armas, e ouvir os sons mostrou isso.
- **A primeira versão** passava razoavelmente no juiz CLAP (29% em 1º, 45% no top 3). Mesmo assim, a espada soava como um sino de 2 s, o golpe no ar como chiado agudo e o arco puxando como um zumbido.
- **Teste com gravações reais:** o CLAP erra também com elas. O som de arco do Pixabay que serviu de referência fica em 13º lugar ("obturador de câmera" e "zap elétrico"); choques de espada reais vão do 1º ao 62º lugar; flechas acertando madeira, do 1º ao 33º.
- **Método:** as armas passaram a ser ajustadas contra gravações reais de cada evento (prévias do Freesound e o arco do Pixabay, só para análise).
  - Os desenhos (`physical.SWING`, `FLY`, `CLASH`, `HIT`, `FLESH`, `ARROW_HIT`, `RELEASE`, `BOW_DRAW`, `UNSHEATHE`) expõem suas constantes.
  - Uma estratégia evolutiva ajusta as constantes para que duração, decaimento, centroide espectral, planura (ruído × tom), energia em 7 bandas e o envelope em torno do pico caiam na faixa (mediana e intervalo interquartil) das gravações.

| evento | brilho real (centroide) | antes | depois |
|---|---|---|---|
| choque de espadas | 5,2 kHz, ruidoso (planura 0,13) | 2,8 kHz, tonal (0,009) | 5,3 kHz (0,13) |
| golpe no ar | 0,55 kHz | 2,8 kHz | 0,4 kHz |
| espada na carne | 1,9 kHz (0,36) | 0,5 kHz (0,04) | 1,8 kHz (0,37) |
| maça no escudo de madeira | 0,8 kHz | 0,09 kHz | 0,6 kHz |
| flecha acertando madeira | 3,1 kHz (0,31) | 0,1 kHz (0,0006) | 3,2 kHz (0,32) |
| flecha voando | 1,6 kHz | 3,7 kHz | perto de 1,6 kHz (desenho próprio) |

O que as gravações ensinaram:
- **Golpe no ar:** é grave, com a energia abaixo de 500 Hz.
- **Choque de espadas:** é curto, brilhante e ruidoso; os modos da lâmina duram pouco porque a mão amortece.
- **Impactos:** um estalo de banda larga com um corpo curto.
- **Flecha na madeira:** a haste vibra em cliques periódicos (~15–30 Hz), não num tom.
- **Puxar o arco:** estalos irregulares de madeira e corda sobre microestalos densos.
- **Soltar o arco:** um sopro crescente de ~0,25 s, um estalo seco e um baque grave.

**Conferência por semelhança de áudio no CLAP** (e não por texto): a distância do soltar o arco para a referência do Pixabay caiu nos dois modelos (similaridade 0,27 → 0,37 e 0,30 → 0,49). Uma segunda rodada maximizando essa semelhança só melhorou no modelo otimizador, e não foi adotada.

**Magia, explosões, ambientes e passos no juiz CLAP** (2 identidades por estilo, 80 rótulos; o acaso ficaria em ~1% para o 1º lugar):

| família | 1º | top 3 | destaques | fracos |
|---|---|---|---|---|
| magia | 50% | 80% | carga, disparo e trajeto de quase todos os elementos; impacto de fogo, arcano, sombra | impacto do raio, trajeto arcano |
| explosões | — | — | explosão distante em 1º | estouro de perto ouvido como "bola de fogo" |
| ambientes | ~30% | ~40% | loops de chuva, caverna, noite, tempestade e mar em 1º | quase todos os eventos soltos |
| passos | 0% | 0% | — | todos |

Os loops têm 16 s, e o CLAP recorta aleatoriamente áudios com mais de 10 s, então os números dos ambientes variam um pouco entre execuções.

**O que a busca guiada pelo CLAP ensinou:**
- **Vento:** o juiz confirmou o ganho (do 9º–10º para o 3º–4º lugar), e o ajuste foi adotado.
- **Rangido do arco:** a busca deu um zumbido agudo que o juiz aprovou (do 22º para o 6º–9º lugar), mas que soava artificial. Foi substituído pelo desenho ajustado contra gravações reais. Lição: o CLAP aprova sons irreais de foley.
- **Choque e queda da espada:** quando o otimizador gosta e o juiz não, descartamos. A busca levou o otimizador ao 2º–5º lugar e o juiz ficou em 20º–40º.
- **Passos:** a busca sobre sequências de caminhada levou o cascalho ao 1º lugar no otimizador, mas o juiz ficou em 8º–10º; pedra, madeira e grama não chegaram ao top 10. A estrutura encontrada está em `physical.STEPS`. Nossos passos ainda soam como impactos ("bola quicando", "flecha na madeira").

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

*Conclusão.* Dentro da síntese de formantes por regras, nenhum ajuste de parâmetros fecha a distância para a voz natural. O nosso motor continua com o papel em que é bom (procedural, leve, determinístico, balbucio), e as falas importantes ficam com a voz natural (`casting.py`). As ferramentas ficam no repositório para medir qualquer mudança futura nos dois juízes.

**Balbucio** (`speech/babble.py`). Depois do g2p, as sílabas podem ser trocadas antes da prosódia, e por isso o ritmo, as tônicas e o tipo de frase continuam os do texto:
- `gibberish`: cada sílaba vira ataque + vogal sorteados do inventário do idioma, às vezes com coda no fim da palavra; a semente é a fala + o nome do personagem.
- `mumble`: toda sílaba vira "m" + schwa.
- `animalese`: mantém as sílabas, mas a voz fica 1,5× mais aguda, 2,2× mais rápida, com metade da entonação e uma nota aleatória (±5 semitons) por sílaba somada ao contorno.

**Elenco** (`speech/casting.py`). `cast(role, name, lang, gender, creature, voice, style, natural)` devolve um `Cast` (voz + estilo + papel) com `render()` e `voice()`; `voice()` é `None` para vozes naturais, que não têm spec. As regras:
- `main` usa Kokoro quando `natural` (padrão: Kokoro instalado); o nome escolhe a voz entre as do idioma e gênero.
- Nos outros casos, a voz de formantes é sorteada pelo nome; com `gender`, fica a primeira semente com pitch ≥ 165 Hz (f) ou ≤ 150 Hz (m).
- `voice` explícita sempre vence. Uma voz `kokoro:` sem Kokoro vira uma voz de formantes do mesmo gênero.

O bestiário e o `bake` usam o elenco. O manifesto registra `role`, `style` e `engine` de cada personagem.

**Próximos passos da fala:**
- Melhorar o português (nasais, "v", encontros consonantais).
- Mais idiomas: o front-end é plugável (`speech.LANGS`).
- Envelope por contexto (difones aprendidos do professor) ou um vocoder neural pequeno, medidos com `tools/structure_analysis.py` (UTMOS + Whisper).

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
