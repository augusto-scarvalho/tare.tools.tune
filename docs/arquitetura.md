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
| `spec.py` | `Voice`, `Syllable`, `ChipProgram` + JSON (v1) |
| `render.py` | DSP fonte-filtro |
| `chip.py` | motor Game Boy (2 pulsos + ruído) e leitor dos dados da 1ª geração |
| `creature.py` | API principal (`Creature`) |
| `bake.py` | uso offline: bestiário → WAVs + manifest |
| `runtime.py` | uso em jogo Python: `VoiceBank` |
| `cli.py` | linha de comando |

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

## Spec v1

Os campos com valor padrão são omitidos no JSON (`Voice.to_dict`).

**Voice**

| campo | significado |
|---|---|
| `syllables` | lista de `Syllable` |
| `chips` | lista de `ChipProgram` (motor Game Boy) |
| `drive` | saturação `tanh` |
| `crush` | 0..1, reduz taxa de amostragem e bits |
| `space`, `wet` | cauda de reverb em segundos e mix. A engine pode trocar pelo reverb dela |
| `gain` | pico final relativo a -1 dBFS (o idle sai ~9 dB abaixo do ataque) |
| `seed` | semente de todos os fluxos aleatórios |
| `meta` | informativo (arquétipo, chamado, traços) |

**Syllable**: `start` e `dur` (s); `pitch` (curva em Hz); `source` (`glottal`, `sine`, `pulse` ou `noise`); `pulse_width`; `brightness`; `vibrato` [Hz, semitons]; `jitter` (semitons); `sub`; `rough` [profundidade, Hz]; `breath`; `ring` [Hz, mix]; `formants` [[Hz, largura, ganho], ...]; `mouth` (curva de escala dos formantes); `pulses` [Hz, profundidade, nitidez]; `attack` e `release` (s); `amp` (curva); `gain`.

Uma curva é `[[t, valor], ...]` com `t` de 0 a 1. O tom é interpolado em escala log; o resto, linear.

**ChipProgram**: `pulse1`, `pulse2` e `noise` são comandos `{"duty": byte}` ou `{"note": [dur-1, volume, fade, frequência ou parâmetro NR43]}`; `pitch`; `length` (-128..127); `start`; `gain`; `hardware_noise`.

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
   - `pulses`: `env *= 1 − d + d·(0.5 − 0.5·cos(2π·rate·t))^nitidez`.
5. A sílaba é `x·env`, normalizada para pico = `gain`.

Na voz inteira:
1. Soma as sílabas em `floor(start·sr)` e os chips, que vêm do motor Game Boy normalizados para pico = `gain`.
2. Passa-alta Butterworth de 2ª ordem em 40 Hz, depois normaliza para pico 1.
3. `crush`: sample-and-hold de `1 + floor(11·crush)` amostras, quantizado em `2^(14 − 10·crush)` níveis.
4. `drive`: `tanh(d·x)/tanh(d)`.
5. Reverb:
   - IR: `noise(key(seed,"space"), N)·exp(−6.9·i/N)`, com `N = space·sr`, passada por um passa-baixa Butterworth de 2ª ordem em 5 kHz.
   - Saída: `(1−wet)·seco + wet·cauda·pico(seco)/pico(cauda)`.
6. Fade de 4 ms no fim e normalização para pico `0.89·gain`.

**Validar uma port:** os fluxos aleatórios devem bater bit a bit (vetores de teste). O áudio não será bit-exato, por ordem de operações em ponto flutuante e convolução por FFT. Para ter material de comparação, rode `creaturesynth bake` com specs: cada entrada do manifest traz o spec e o WAV de referência. Renderize os specs na engine e compare os espectros. Com `space = 0` a diferença deve ser mínima.

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
