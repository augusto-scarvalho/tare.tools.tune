# creaturesynth

Vozes procedurais para jogos: **criaturas** e **fala humana** (português e inglês). Para criaturas, você descreve **quem** chama (espécie, tamanho, agressividade) e **por quê** (idle, alerta, ataque, dor, morte). Para pessoas, você escolhe uma voz e escreve o texto. A mesma entrada sempre gera o mesmo som, e cada indivíduo e cada repetição varia um pouco.

Nasceu de um fork do [sintetizador de gritos da 1ª geração de Pokémon](https://github.com/ardean/pokemon-gen1-cry-synthesizer). A ideia do jogo, que tira 151 gritos de 38 moldes mais tom e duração, virou o modelo geral aqui: **espécie = genes estáveis; indivíduo = pequenas variações; traços = evolução**. O motor original continua disponível como arquétipo `chip` e como reprodução fiel dos 151 gritos.

```python
from creaturesynth import Creature, write_wav

lobo = Creature("mammal", species="lobo", size=0.45, aggression=0.5)
write_wav("lobo_ataque.wav", lobo.render("attack"), 48000)

lobo_terrivel = lobo.evolve(size=0.45, aggression=0.35)   # mesma espécie, maior e mais feroz
write_wav("lobo_terrivel_morte.wav", lobo_terrivel.render("death", take=2), 48000)

from creaturesynth.speech import Speaker

ferreiro = Speaker.preset("deep")
write_wav("ferreiro.wav", ferreiro.render("Bem-vindo à forja, viajante!", lang="pt"), 48000)
npc = Speaker.random(42)                                   # uma voz única e repetível por NPC
write_wav("npc.wav", npc.render("Did you see the dragon?", lang="en"), 48000)
```

## Instalação

```bash
pip install -e .            # numpy + scipy
pip install -e ".[dev]"     # + pytest, ruff, matplotlib (espectrogramas)
```

Requer Python 3.10 ou mais novo.

## Arquétipos

| arquétipo   | o que gera |
|-------------|------------|
| `mammal`    | guincho → latido → uivo → rugido, conforme tamanho e agressividade |
| `bird`      | canto assobiado de sílabas varridas; agressivo vira grasnado |
| `insect`    | grilo, zumbido de mosca/abelha ou cigarra |
| `reptile`   | sibilo, chocalho; os grandes e bravos rosnam por baixo |
| `amphibian` | coaxar pulsado ("rib-bit") |
| `monster`   | fera de fantasia: rugido bruto, guincho estridente ou gorgolejo |
| `slime`     | bolhas estourando sobre um gorgolejo úmido |
| `spirit`    | lamento fantasmagórico com assobio e reverb longo |
| `robot`     | tons em degraus, ressonâncias metálicas, ring mod, bitcrush |
| `chip`      | gritos 8-bit inéditos no estilo Game Boy (2 pulsos + ruído) |

**Chamados:** `idle`, `alert`, `attack`, `hurt`, `death`. Todos os arquétipos respondem a eles: alerta repete e sobe, ataque é mais forte e áspero, dor é curta e aguda, morte é longa e cai de tom, idle é mais baixo.

**Controles de uma criatura:**
- `species`: número ou qualquer nome (vira hash). Define os genes da espécie.
- `size`: de 0 (minúsculo) a 1 (enorme). Mexe em tom, formantes, duração e reverb.
- `aggression`: de 0 (calmo) a 1 (furioso). Mexe em aspereza, sub-harmônicos e saturação.
- `individual` e `variation`: o quanto os membros da espécie diferem entre si.
- `take` e `take_variation`: o quanto repetições do mesmo chamado diferem.
- `genes={"nome": 0..1}`: fixa genes para direção de arte. Ex.: `{"kind": 0.1}` força o monstro "brute".

## Fala humana

Texto em **português brasileiro** ou **inglês** vira fala por síntese de formantes, a mesma família de técnica das vozes de computador clássicas. O processo:

1. **Texto → fonemas.** No português, por regras: dígrafos, nasais, "t/d" antes de "i", "r"/"s"/"x", sílaba tônica e números por extenso. No inglês, pelo dicionário CMUdict (~126 mil palavras), com regras para palavras que não estão nele, como nomes inventados.
2. **Fonemas → alvos acústicos.** Cada fonema tem duração e alvos de formantes; a coarticulação suaviza a passagem entre eles.
3. **Entonação.** Afirmação cai no fim, pergunta sim/não sobe, pergunta com "where/what" cai, exclamação tem pico mais alto, vírgula deixa a frase em suspenso.
4. **Síntese.** Um sintetizador em cascata/paralelo no estilo Klatt gera o áudio.

Soa robótico e retrô, mas é 100% procedural, leve, determinístico e portável.

**Vozes prontas:** `default`, `deep`, `high`, `child`, `cute`, `fairy`, `elder`, `giant`, `monster`, `robot` e `whisper`. Use `Speaker.random(seed)` para dar uma voz humana única a cada NPC, e `Speaker.from_creature(criatura)` para uma criatura falar com voz compatível com o corpo dela. Dá para ajustar `pitch`, `tract` (tamanho do trato vocal), `rate`, `range` (entonação), `breath`, `rough` e outros.

**Vozes naturais (opcional).** Quem quiser voz natural em vez de robótica pode usar o [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0), com vozes em português brasileiro (`pf_dora`, `pm_alex`, `pm_santa`) e em inglês. O Whisper acerta essas vozes quase sempre (CER 0,003 nas mesmas frases de teste). O preço: não é procedural, puxa o PyTorch (~1 GB) mais um modelo de ~330 MB, e não vira spec portável para engines; o bake gera WAV normalmente. Os efeitos do motor (reverb, drive, crush) funcionam por cima.

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu   # PyTorch só CPU basta
pip install -e ".[neural]"
creaturesynth say "Bem-vindo à vila!" --voice kokoro:pm_alex
```

No código, use `speaker_from("kokoro:pf_dora")`; no bestiário, `"voice": "kokoro:pm_alex"`. O Kokoro usa o espeak-ng (GPL) para converter o português em fonemas: tudo bem como ferramenta, mas avalie a licença antes de distribuir junto com um jogo.

**Inteligibilidade** medida com o Whisper (`tools/intelligibility.py`) em 16 frases de diálogo de jogo por idioma: no inglês, CER entre 0,04 e 0,06 conforme a voz (a maioria das frases sai perfeita); no português, entre 0,24 e 0,34 (cerca de 70 a 75% dos caracteres certos). O português ainda é o ponto a melhorar.

## Duas formas de usar

### 1. Offline: gerar assets para qualquer engine

Um arquivo de bestiário vira pacotes de WAV, mais um `manifest.json` e o spec JSON de cada som:

```bash
creaturesynth bake examples/bestiary.json -o baked     # 19 criaturas x 5 chamados x 3 takes
```

```json
{
  "takes": 3,
  "creatures": {
    "cub":       {"archetype": "mammal", "species": "wolf", "size": 0.15, "aggression": 0.15},
    "wolf":      {"extends": "cub", "size": 0.45, "aggression": 0.5},
    "dire_wolf": {"extends": "wolf", "size": 0.9, "aggression": 0.85},
    "mystery":   {"random": 7}
  }
}
```

`extends` herda de outra entrada (evoluções, variantes) e `random` sorteia uma criatura nova. Falas de NPC entram numa seção `speakers`, com uma voz e as falas de cada um:

```json
"speakers": {
  "ferreiro": {"voice": "deep", "lang": "pt", "lines": {"oi": "Bem-vindo à forja, viajante!"}},
  "guarda":   {"voice": "npc:12", "lines": {"alto": "Alto lá! Quem vem?"}}
}
```

Importe `baked/` na Unity, Godot, Unreal, FMOD ou Wwise e sorteie um take por chamado.

### 2. Runtime: gerar dentro do jogo

- **Jogos em Python** (pygame, pyglet, Arcade, Panda3D, Ren'Py): `VoiceBank` renderiza em threads, mantém cache e nunca repete o mesmo take duas vezes seguidas. Veja [`examples/pygame_demo.py`](examples/pygame_demo.py).

  ```python
  from creaturesynth.runtime import VoiceBank

  bank = VoiceBank(sample_rate=44100, takes=4)
  bank.warm(lobo)                                     # durante o loading
  audio = bank.get(lobo, "attack", block=False)       # None se ainda não ficou pronto
  fala = bank.line(Speaker.preset("child"), "Oi!")    # falas também, com cache
  ```

- **Outras engines:** o som é descrito por um **spec JSON** portável. A aleatoriedade é SplitMix64 + FNV-1a, com vetores de teste, e o renderizador usa só blocos simples (PolyBLEP, biquads, one-pole). Um renderizador nativo em C#, GDScript ou C++ pode tocar specs gerados aqui ou, portando também os arquétipos, inventar criaturas novas em tempo real. O contrato de portabilidade está em [`docs/arquitetura.md`](docs/arquitetura.md).

## Linha de comando

```bash
creaturesynth list                                                    # arquétipos e chamados
creaturesynth render monster --species ogro --size .9 --aggression .8 --call attack -o ogro.wav --png
creaturesynth spec chip --species 3 --call hurt -o pixel_hurt.json    # spec JSON para engines
creaturesynth from-spec pixel_hurt.json -o pixel_hurt.wav
creaturesynth zoo -n 30 -o zoo                                        # 30 criaturas inéditas
creaturesynth gen1 pikachu                                            # reprodução da 1ª geração
creaturesynth gen1 all -o gen1/
creaturesynth say "Olá, viajante!" --voice child -o ola.wav --phonemes  # fala
creaturesynth say "Hello there!" --lang en --voice npc:7 --pitch 140
creaturesynth voices                                                  # vozes prontas
```

## Reprodução da 1ª geração

`creaturesynth.chip` reimplementa o motor de gritos de Pokémon Red/Blue: 2 canais de pulso e 1 de ruído, a 1.048.576 Hz, com filtro anti-aliasing na decimação. Ele foi verificado contra o motor TypeScript original do fork, congelado em `tests/fixtures/gen1`, nos 151 gritos:
- durações idênticas;
- ruído bit a bit;
- pulsos iguais, exceto bordas isoladas deslocadas em 1 amostra (~1 µs), que vêm do arredondamento de ponto flutuante do código antigo.

Por padrão, o ruído de 7 bits segue o hardware real, o que corrige um bug do app antigo. `--legacy-noise` reproduz o comportamento antigo.

Os dados dos gritos (`data/gen1/cries.json`) são dados de jogo de terceiros. Ficam no repositório só como referência e para testes, e **não fazem parte do pacote**. Para usar a partir de um pacote instalado, aponte `CREATURESYNTH_GEN1_DATA` para o arquivo.

## Desenvolvimento

```bash
pytest -q          # ~270 testes, incluindo os 151 gritos contra a referência
ruff check .

pip install -e ".[asr]"
python tools/intelligibility.py -v    # a fala, transcrita pelo Whisper (taxa de erro por caractere)

pip install -e ".[neural]"
python tools/teacher_calibration.py render    # fala natural do Kokoro como "professor" do português
python tools/teacher_calibration.py measure   # formantes, durações e fricativas medidos por fonema
```

O desempenho neste ambiente de desenvolvimento (4 núcleos), a 48 kHz: cada som leva de 20 a 250 ms para gerar, e `bake` produz cerca de 40 sons por segundo.

## Créditos

A pronúncia do inglês vem do [CMU Pronouncing Dictionary](https://github.com/cmusphinx/cmudict) (licença BSD, incluída em `src/creaturesynth/speech/data/LICENSE-cmudict`). O sintetizador de fala segue o desenho cascata/paralelo de Dennis Klatt.

O motor de gritos da 1ª geração é baseado no [sintetizador original de dotsarecool](http://dotsarecool.com/rgme/tech/gen1cries.html) ([vídeo](https://www.youtube.com/watch?v=gDLpbFXnpeY)) e no [port em TypeScript de ardean](https://github.com/ardean/pokemon-gen1-cry-synthesizer), de onde este repositório foi forkado.
