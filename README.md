# creaturesynth

Vozes procedurais de criaturas para jogos. Você descreve **quem** chama (espécie, tamanho, agressividade) e **por quê** (idle, alerta, ataque, dor, morte), e o creaturesynth gera o som. A mesma entrada sempre gera o mesmo som, e cada indivíduo e cada repetição varia um pouco.

Nasceu de um fork do [sintetizador de gritos da 1ª geração de Pokémon](https://github.com/ardean/pokemon-gen1-cry-synthesizer). A ideia do jogo, que tira 151 gritos de 38 moldes mais tom e duração, virou o modelo geral aqui: **espécie = genes estáveis; indivíduo = pequenas variações; traços = evolução**. O motor original continua disponível como arquétipo `chip` e como reprodução fiel dos 151 gritos.

```python
from creaturesynth import Creature, write_wav

lobo = Creature("mammal", species="lobo", size=0.45, aggression=0.5)
write_wav("lobo_ataque.wav", lobo.render("attack"), 48000)

lobo_terrivel = lobo.evolve(size=0.45, aggression=0.35)   # mesma espécie, maior e mais feroz
write_wav("lobo_terrivel_morte.wav", lobo_terrivel.render("death", take=2), 48000)
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

`extends` herda de outra entrada (evoluções, variantes) e `random` sorteia uma criatura nova. Importe `baked/` na Unity, Godot, Unreal, FMOD ou Wwise e sorteie um take por chamado.

### 2. Runtime: gerar dentro do jogo

- **Jogos em Python** (pygame, pyglet, Arcade, Panda3D, Ren'Py): `VoiceBank` renderiza em threads, mantém cache e nunca repete o mesmo take duas vezes seguidas. Veja [`examples/pygame_demo.py`](examples/pygame_demo.py).

  ```python
  from creaturesynth.runtime import VoiceBank

  bank = VoiceBank(sample_rate=44100, takes=4)
  bank.warm(lobo)                                     # durante o loading
  audio = bank.get(lobo, "attack", block=False)       # None se ainda não ficou pronto
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
pytest -q          # ~200 testes, incluindo os 151 gritos contra a referência
ruff check .
```

O desempenho neste ambiente de desenvolvimento (4 núcleos), a 48 kHz: cada som leva de 20 a 250 ms para gerar, e `bake` produz cerca de 40 sons por segundo.

## Créditos

O motor de gritos da 1ª geração é baseado no [sintetizador original de dotsarecool](http://dotsarecool.com/rgme/tech/gen1cries.html) ([vídeo](https://www.youtube.com/watch?v=gDLpbFXnpeY)) e no [port em TypeScript de ardean](https://github.com/ardean/pokemon-gen1-cry-synthesizer), de onde este repositório foi forkado.
