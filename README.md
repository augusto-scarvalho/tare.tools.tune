# tare.tools.tune

Áudio procedural para jogos: **criaturas**, **fala humana** (português e inglês) e **efeitos sonoros** (armas, passos, explosões, magia, ambientes). Para criaturas, você descreve **quem** chama (espécie, tamanho, agressividade) e **por quê** (idle, alerta, ataque, dor, morte). Para pessoas, você escolhe uma voz e escreve o texto. Para efeitos, você escolhe o objeto (uma espada de aço, uma bola de fogo, uma tempestade) e o evento (golpe, choque, impacto, loop). A mesma entrada sempre gera o mesmo som, e cada indivíduo e cada repetição varia um pouco.

Nasceu como `creaturesynth`, um fork do [sintetizador de gritos da 1ª geração de Pokémon](https://github.com/ardean/pokemon-gen1-cry-synthesizer). A ideia do jogo, que tira 151 gritos de 38 moldes mais tom e duração, virou o modelo geral aqui: **espécie = genes estáveis; indivíduo = pequenas variações; traços = evolução**. O motor original continua disponível como arquétipo `chip` e como reprodução fiel dos 151 gritos.

```python
from tare.tools.tune import Creature, write_wav

lobo = Creature("mammal", species="lobo", size=0.45, aggression=0.5)
write_wav("lobo_ataque.wav", lobo.render("attack"), 48000)

lobo_terrivel = lobo.evolve(size=0.45, aggression=0.35)   # mesma espécie, maior e mais feroz
write_wav("lobo_terrivel_morte.wav", lobo_terrivel.render("death", take=2), 48000)

from tare.tools.tune.speech import Speaker

ferreiro = Speaker.preset("deep")
write_wav("ferreiro.wav", ferreiro.render("Bem-vindo à forja, viajante!", lang="pt"), 48000)
npc = Speaker.random(42)                                   # uma voz única e repetível por NPC
write_wav("npc.wav", npc.render("Did you see the dragon?", lang="en"), 48000)

from tare.tools.tune import Sfx

excalibur = Sfx("blade", "steel", species="excalibur")
write_wav("choque.wav", excalibur.render("clash", take=3), 48000)   # cada take é um choque diferente
write_wav("bola_de_fogo.wav", Sfx("spell", "fire", power=0.8).render("impact"), 48000)
```

## Instalação

```bash
pip install -e .            # numpy + scipy
pip install -e ".[dev]"     # + pytest, ruff, matplotlib (espectrogramas)
```

Requer Python 3.10 ou mais novo. No código, `import tare.tools.tune` (os pacotes `tare` e `tare.tools` são namespaces); na linha de comando, `tare.tools.tune`; onde o nome não aceita pontos, `tare-tools-tune` (é como o pip normaliza o nome do pacote).

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

Texto em **português brasileiro** ou **inglês** vira fala. A frente é a mesma para os dois motores:

1. **Texto → fonemas.** No português, por regras: dígrafos, nasais, "t/d" antes de "i", "r"/"s"/"x" (com listas para o "x" de "próximo" e de "táxi"), sílaba tônica e números por extenso. No inglês, pelo dicionário CMUdict (~126 mil palavras), com regras para palavras que não estão nele, como nomes inventados.
2. **Entonação.** Afirmação cai no fim, pergunta sim/não sobe, pergunta com "where/what" cai, exclamação tem pico mais alto, vírgula deixa a frase em suspenso.
3. **Som**, por um de dois motores (`Speaker(engine=...)`):
   - `"formant"` (padrão): cada fonema tem duração e alvos de formantes, a coarticulação suaviza a passagem e um sintetizador em cascata/paralelo no estilo Klatt gera o áudio. Soa robótico e retrô, mas é minúsculo e estica para qualquer voz, de fada a gigante.
   - `"natural"`: a frase é montada com pedaços de um **banco de voz**, a leitura de 1000 frases (~45 min) por um professor, guardada só como números (tom, envelope espectral e sopro a cada 5 ms; ~21 MB por voz). Para cada par de fonemas escolhe-se o melhor pedaço do banco (seleção de unidades por Viterbi, emendando de preferência em consoantes), os pedaços são esticados para o ritmo e recebem a entonação que o professor usaria (modelos aprendidos dele, por regressão), e o nosso vocoder refaz o som, levado para a altura e o trato vocal do personagem.

**Nada de IA em tempo de execução.** Os dois motores são determinísticos e procedurais: tabela, programação dinâmica e aritmética. O professor dos bancos é o [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0), usado uma vez, offline, por `tools/build_speech.py`; o pacote não depende dele nem do PyTorch. Os dois motores dão um spec portável (`SpeechProgram` ou `Spoken`).

```python
from tare.tools.tune.speech import Speaker

guarda = Speaker.preset("deep")                                   # formantes
rei = Speaker(pitch=105, tract=0.97, engine="natural")            # banco de voz, levado para esta voz
audio = rei.render("Bem-vindo ao meu reino, viajante.", lang="pt")
npc = Speaker.random(42).but(engine="natural")                    # uma voz natural única por NPC
```

**Vozes prontas (formantes):** `default`, `deep`, `high`, `child`, `cute`, `fairy`, `elder`, `giant`, `monster`, `robot` e `whisper`. Use `Speaker.random(seed)` para dar uma voz humana única a cada NPC, e `Speaker.from_creature(criatura)` para uma criatura falar com voz compatível com o corpo dela. Dá para ajustar `pitch`, `tract` (tamanho do trato vocal), `rate`, `range` (entonação), `breath`, `rough` e outros.

**Vozes naturais:** `natural`, `natural:m`, `natural:f` ou um banco (`natural:pt/alex`, `natural:pt/dora`), na linha de comando, no bestiário e em `speaker_from`. Qualquer `pitch` e `tract` funcionam: o banco mais próximo do trato é escolhido e o vocoder leva o resto (formantes de 0,75× a 1,35×). Soa mais natural perto do tom dos bancos (130 Hz o masculino, 173 Hz o feminino): levar a voz muito acima afina o som. `breath`, `whisper`, `tilt`, `rate`, `range`, `jitter`, `drive`, `crush` e `space` também valem. Por enquanto só há bancos em português; em inglês, o motor natural cai para o de formantes.

**Inteligibilidade** medida com o Whisper (`tools/intelligibility.py`, mais 16 frases novas, nenhuma do corpus do professor):

| | português (CER) |
|---|---|
| formantes | 0,23 |
| natural, voz masculina / feminina / NPCs sorteados | 0,045 / 0,042 / 0,033–0,037 |
| o professor (Kokoro) | 0,003 |

No inglês, os formantes ficam entre 0,04 e 0,06 conforme a voz.

### Interjeições (jogos sem dublagem completa)

Muitos jogos não são dublados: o personagem só solta um "hyah!", um "ugh", um "hm?" ou uma risada, e o texto faz o resto. `Speaker.emote` gera essas interjeições sem palavras **na voz do próprio personagem**.

Elas partem de performances reais: gravações CC0 de atores, analisadas uma vez em números (tom, envelope espectral e ar a cada 5 ms; 183 moldes, 951 kB). No jogo, um vocoder nosso, em numpy, refaz o som e o leva para a altura, o trato vocal, o brilho e o sopro do personagem. Não roda nenhum modelo nem IA, e o resultado é determinístico: o mesmo personagem, tipo, estilo e take dão sempre as mesmas amostras.

```python
from tare.tools.tune.speech import Speaker

heroi = Speaker(pitch=135, tract=1.06, breath=0.12)
write_wav("golpe.wav", heroi.emote("attack", style="grunt", take=2), 48000)   # cada take é um pouco diferente
garota = Speaker.random(42)
write_wav("risada.wav", garota.emote("laugh", style="anime", intensity=0.9), 48000)
```

- **Combate:** `attack`, `attack_big`, `hurt`, `hurt_big`, `death`, `jump`, `tired`.
- **Expressões:**
  - risos: `laugh`, `giggle`, `chuckle`;
  - respiração: `sigh`, `gasp`, `relief`;
  - reações: `surprise`, `hmm`, `huh`;
  - respostas: `yes`, `no`;
  - humor: `cheer`, `angry`.
- **Estilos**, inspirados nos jogos que usam esses sons (os sons não vêm desses jogos):

  | estilo | jeito | inspirado em |
  |---|---|---|
  | `grunt` | sem palavras e cheio de ar, curto | o herói de *Zelda* |
  | `anime` | brilhante, mais voz e menos ar, contorno mais vivo | *Rune Factory* |
  | `tactics` | contido: mais curto, mais grave e mais escuro | *Fire Emblem* |
  | `mmo` | gritos cheios, mais longos e fortes | *Final Fantasy XIV* |
- `intensity` (0 a 1) controla quanto esforço vai no som.
- O spec guarda o molde e as transformações (`Vocoded`, v5); uma port precisa levar os moldes junto.

As performances vêm de pacotes CC0 do OpenGameArt (aventureiro, vozes femininas de RPG, gritos) e de risadas, suspiros, sustos e "hm" do Freesound. O molde escolhido é o que menos precisa ser mexido para chegar à voz do personagem, sobretudo nas formantes: uma heroína pega intérpretes mulheres; um herói, homens. Os esforços mudam de voz pelo registro do grito, medido nas mesmas gravações: um grito de ataque sobe muito acima da fala, homens 17 a 23 semitons (95 Hz → ~345 Hz), mulheres cerca de 10. Detalhes em [`docs/arquitetura.md`](docs/arquitetura.md).

### Quem fala com qual motor

Cada motor tem seu ponto forte, e `speech.casting.cast` faz a escolha pelo papel do personagem:

| papel (`role`) | para quê | voz |
|---|---|---|
| `main` | falas importantes de NPC | natural, voz única por nome |
| `minor` | o resto dos NPCs | formantes, voz única por nome |
| `crowd` | burburinho de fundo | formantes, língua inventada |
| `creature` | criaturas que falam | a voz da criatura, balbuciando |
| `robot` | máquinas, golems | formantes robóticos, palavras reais |

A voz natural soa humana e leva um banco de alguns MB por idioma. A de formantes é minúscula, estica para qualquer criatura e é a melhor para **balbuciar** (`style`; os estilos também funcionam na natural). Os três estilos de balbucio mantêm o ritmo, as tônicas e a pontuação do texto, então perguntas continuam subindo:
- `gibberish`: língua inventada com os sons do idioma, como os Sims;
- `animalese`: uma nota por sílaba, rápida e aguda, como Animal Crossing;
- `mumble`: tudo em "mm".

```python
from tare.tools.tune.speech.casting import cast

rei = cast("main", "rei", gender="m")              # voz natural
povo = cast("crowd", "povo")                       # balbucio
rato = cast("creature", creature=rato_criatura)    # pequeno: animalese
audio = rei.render("Salve o reino!")
```

## Efeitos sonoros

`Sfx` funciona como `Creature`: um **tipo** (receita), um **estilo** (material, elemento ou lugar), uma **identidade** (`species`: esta espada, não espadas em geral), **tamanho** e **força**, e **eventos** que tocam como os chamados. Cada take varia: o golpe pega num ponto diferente da lâmina, o fogo crepita de outro jeito.

| tipo | estilos | eventos |
|---|---|---|
| `blade` (espadas, adagas, machados) | steel, iron, glass, wood | swing, clash, hit_flesh, hit_wood, hit_metal, hit_stone, draw, drop |
| `blunt` (clavas, maças, martelos) | wood, iron, stone | swing, hit_flesh, hit_wood, hit_metal, hit_stone, drop |
| `bow` | longbow, crossbow | draw, release, fly, hit_wood, hit_flesh, hit_stone |
| `shield` (escudos) | wood, metal | block_blade, block_blunt, block_arrow, bash |
| `gear` (armaduras e roupas) | chainmail, plate, leather | move, run, equip |
| `body` (corpo caindo) | stone, wood, dirt | fall, drop |
| `door` (portas e portões) | wood, iron | open, close, locked, unlock, knock |
| `chest` (baús) | wood, iron | open, close, locked, unlock |
| `item` (itens) | coins, potion, scroll, gem | pickup, use, drop |
| `breakable` (coisas para quebrar) | crate, barrel, pot, glass | hit, break |
| `ui` (interface) | fantasy, retro | click, open, close, levelup, quest, error |
| `lever` (alavancas) | iron, wood | pull, push |
| `trap` (armadilhas) | darts, spikes, blade | trigger, fire |
| `torch` (fogo) | torch, brazier | ignite, extinguish |
| `water` (água) | small, big | splash, dive, drip |
| `footstep` | stone, wood, metal, gravel, dirt, grass, snow, water | walk, run, land, scuff |
| `explosion` | fire, stone, magic | blast, distant, debris |
| `spell` | fire, ice, lightning, arcane, holy, shadow, nature, heal | charge, cast, travel (loop), impact |
| `ambience` | rain, wind, fire, stream, cave, forest, night, storm, sea, dungeon | loop (16 s, sem emenda), accent |

Cada família usa a técnica certa para o tipo de som:
- **Corpos batidos** (metal, madeira, pedra, vidro, sinos, corda de arco) usam **síntese modal**: um impacto ou uma raspagem faz soar um conjunto de modos. O material define os modos, o tamanho a altura e o decaimento, a força a dureza do contato.
- **Ar e massa** (golpes no ar, rugido de fogo, vento, estrondos) usam **ruído com filtro em movimento**.
- **Texturas** (gotas, crepitar, faíscas, cascalho, estilhaços) usam **nuvens de eventos minúsculos**.
- **Magia** soma tudo isso com os blocos das vozes: coral com vogais, zumbido elétrico, sinos.
- **Ambientes** de floresta e noite usam os pássaros e grilos dos arquétipos de criaturas.

```bash
tare.tools.tune sounds                                         # tipos, estilos e eventos
tare.tools.tune sfx blade steel --event clash --species excalibur -o choque.wav
tare.tools.tune sfx spell lightning --event impact --power 0.9 -o raio.wav
tare.tools.tune sfx ambience rain --event loop -o chuva_loop.wav
```

No bestiário, os efeitos entram numa seção `sounds` (o `bake` gera os takes, e os loops saem com um take só e `"loop": true` no manifesto):

```json
"sounds": {
  "excalibur": {"kind": "blade", "style": "steel", "species": "excalibur", "power": 0.7},
  "fireball":  {"kind": "spell", "style": "fire", "power": 0.8},
  "storm":     {"kind": "ambience", "style": "storm", "events": ["loop", "accent"]}
}
```

Dentro do jogo, o `VoiceBank` aceita efeitos como aceita criaturas (`bank.get(espada, "clash")` nunca repete o mesmo take duas vezes seguidas). O `AmbiencePlayer` toca um lugar sem fim: o loop, mais os eventos soltos (trovões, pássaros, gotas) em momentos sorteados, e qualquer outro som que você acrescentar:

```python
from tare.tools.tune.runtime import AmbiencePlayer

floresta = AmbiencePlayer(Sfx("ambience", "forest"), accents_per_minute=6)
floresta.add(Creature("bird", species=4), "alert", per_minute=2)
bloco = floresta.read(1024)        # float32 para o stream de áudio da engine
```

O demo do pygame tem espada (Q/W), bola de fogo (E), raio (R) e tempestade (A).

**O arco** (puxar, soltar, voo e flecha cravando na madeira) foi modelado a partir de gravações de referência. Primeiro mediu-se o mecanismo: os escorregões de atrito da madeira, a corda raspando na flecha antes da pancada, as penas vibrando no ar e a haste zumbindo no alvo. Depois escolheu-se de ouvido entre variantes, ouvindo o disparo inteiro. É o método que vamos seguir com as outras armas.

Cada evento é um ponto de escuta:
- `release` é o que ouve quem atira, e já traz a flecha se afastando;
- `fly` é a flecha passando perto de quem ouve, com Doppler;
- `hit_wood`, `hit_flesh` e `hit_stone` são a flecha cravando no alvo, entrando num corpo ou ricocheteando na pedra.

**A espada** (golpe no ar, choque de lâminas e golpes em madeira, pedra, armadura e carne, em aço e ferro) seguiu o mesmo método. O tamanho e a força escolhem entre as três versões aprovadas:

| | tamanho 0,5 | tamanho 1 |
|---|---|---|
| **força 0,5** | a medida nas gravações | pesada: mais grave, mais baque, golpe lento com "vum", osso na carne |
| **força 1** | cinema: raspa mais, soa mais, golpe com assobio, corte afiado | as duas coisas |


**Os outros sons de RPG** seguem o mesmo método, um por um. A lista e o estado de cada um estão em [`docs/sons-rpg.md`](docs/sons-rpg.md).

**Como soavam, segundo o CLAP** (a primeira versão, desenhada sem gravações). Medimos com o modelo juiz, que não participou de nenhum ajuste, contra 80 descrições em inglês (efeitos, lugares e distratores como fala, música e "som 8-bit"). O acaso ficaria em ~1% para o 1º lugar.

| família | descrição certa em 1º | entre as 3 primeiras |
|---|---|---|
| magia (8 elementos × 4 eventos) | 50% | 80% |
| armas, arco e explosões | 29% | 45% |
| ambientes (loop + evento) | ~30% | ~40% |
| passos | 0% | 0% |

- **Fortes:** golpes em carne e em madeira, golpes no ar, flechas voando e acertando, explosão distante, a maioria das magias, e os loops de chuva, caverna, noite, tempestade e mar (todos em 1º).
- **Fracos:**
  - choque de espadas: o juiz ouve "espada acertando armadura", perto mas não igual;
  - sacar e derrubar a espada, maça em metal ou pedra, disparo do arco;
  - quase todos os eventos soltos dos ambientes;
  - **passos**. Gravações reais de passos são reconhecidas (6 de 8 em 1º), as nossas não, mesmo depois de uma busca guiada pelo CLAP.

O caminho para melhorar é o mesmo usado aqui: comparar com gravações reais e ajustar a estrutura, sempre conferindo no juiz. Detalhes em [`docs/arquitetura.md`](docs/arquitetura.md).

## Música e composição

Três peças, uma sobre a outra:
- **`Score`** (`tare.tools.tune.score`): uma linha do tempo em compassos e segundos. Põe notas e sons prontos (efeitos, criaturas, falas) em camadas, com volume, posição no estéreo e um eco (sala) compartilhado. Renderiza em estéreo, e `render(loop=...)` devolve um loop sem emenda.
- **Instrumentos** (`tare.tools.tune.instruments`): 38 instrumentos medidos em notas gravadas, com os números de cada um no código:
  - cordas pinçadas: harpa, violão, alaúde, pizzicato;
  - teclados de percussão: glockenspiel, marimba, xilofone, celesta, caixinha de música;
  - sinos tubulares;
  - tambores: tímpanos, tambores de mão e de tronco, bumbo, caixa;
  - metais de percussão: triângulo, prato, gongo, pandeiro, chocalho;
  - sustentados: violinos, violoncelos, flauta, trompa, trompete, coro;
  - banda: baixo elétrico, piano elétrico, chimbal fechado e aberto;
  - chiptune: pulsos, baixo e ruídos de console.
- **`Cue`** (`tare.tools.tune.music`): músicas compostas a partir de uma semente.
  - Jingles: `victory`, `levelup`, `quest`, `gameover`.
  - Loops: `town`, `explore`, `tavern`, `dungeon`, `battle`.
  - Loops de "harmonia de cor", no jeito das trilhas de RPG de 16 bits (como as de Yasunori Mitsuda): `reverie`, `pastoral`, `timeless`, `grove`, `heroic`, `showdown`. Acordes escolhidos pela cor, não pela função: 7ª e 9ª deslizando em paralelo, trocas por meio tom e por terças, a tônica como pedal, modos dórico, lídio e mixolídio, nunca V → I. A melodia apoia nas 9ª e 13ª e repete o motivo em sequência.
  - Estilos: `orchestral`, `snes` (16-bit: o eco do console indo de um lado ao outro, agudos mais escuros) e `chip` (8-bit).
  - A semente escolhe tom, progressão, ritmos e motivo: a mesma semente é sempre a mesma música, e cada semente é outra.

```python
from tare.tools.tune import Sfx, write_wav
from tare.tools.tune.music import Cue
from tare.tools.tune.score import Score, chord

write_wav("vitoria.wav", Cue("victory", seed=3).render(), 48000)            # estéreo
taverna = Cue("tavern", seed=7)
write_wav("taverna_loop.wav", taverna.render(), 48000)                      # exatamente taverna.length segundos
write_wav("batalha_8bit.wav", Cue("battle", style="chip", seed=2).render(), 48000)
write_wav("bosque_16bit.wav", Cue("grove", style="snes", seed=5).render(), 48000)

cena = Score(bpm=96)
cena.track("harpa", pan=-0.3, send=0.3).play("harp", [("A3", 0, 1), ("C4", 1, 1), ("E4", 2, 2)])
cena.track("cordas", send=0.4).play("strings", [(chord("Am", 3), 0, 4), (chord("F", 3), 4, 4)])
cena.add(Sfx("blade", "steel").render("clash"), at=cena.beats(4), pan=0.5, send=0.2)
write_wav("cena.wav", cena.render(), 48000)
```

Para cenas inteiras (efeitos, criaturas, uma fala e música sobre um ambiente, em estéreo), veja [`examples/scenes.py`](examples/scenes.py): uma luta na masmorra, um tesouro numa caverna e um duelo de magia.

Notas são `(nota, tempo, duração[, intensidade])`. A nota pode ser um nome (`"C#5"`), um número MIDI ou uma lista (um acorde). A intensidade muda o timbre, não só o volume: o trompete forte abre os agudos, e uma batida suave é mais escura.

As medidas vêm de notas soltas da orquestra [VSCO-2 Community Edition](https://github.com/sgossner/VSCO-2-CE) (CC0) e de notas de violão CC0 do Freesound. Elas foram usadas só para medir e não estão no repositório. Detalhes em [`docs/arquitetura.md`](docs/arquitetura.md#música-e-composição).

## Calibração com CLAP

O [CLAP](https://huggingface.co/laion/clap-htsat-unfused) é um modelo que põe som e texto no mesmo espaço: dá para perguntar "isto soa como um gato miando?". O tare.tools.tune usa dois modelos: um para otimizar (`laion/clap-htsat-unfused`) e outro, que nunca é usado na otimização, como juiz (`laion/larger_clap_general`). Assim o ajuste não "decora" o gosto de um modelo só.

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[clap]"
tare.tools.tune design "a small cat meowing" -o gato.json --wav gato.wav   # criatura a partir de um texto
tare.tools.tune match miado.wav --archetype mammal -o gato.json            # criatura parecida com uma gravação
tare.tools.tune judge                                                      # o que o juiz ouve em cada arquétipo
```

- `design` testa todos os arquétipos (ou só os de `--archetype`), refina os 2 melhores com uma estratégia evolutiva e devolve a entrada pronta para o bestiário (`-o`). Leva cerca de 1 minuto em CPU.
- `match` combina o CLAP com medidas da gravação (curva de tom, envelope, espectro, duração, número de sílabas).
- O resultado é sempre uma criatura procedural comum: as variações por indivíduo e por take continuam valendo.

**O que o juiz disse.** Ele acerta o arquétipo em 32% dos casos, contra 10% do acaso, e chama 56% dos sons não-chip de "som 8-bit de videogame". Para atacar isso, há uma camada de realismo opcional: ruído de fundo, reflexões curtas de sala, perda de agudos, oscilação de volume e sopro. O ajuste com o otimizador baixou o "8-bit" para 46% no juiz, mas não melhorou o acerto de arquétipo. Por isso a camada fica desligada por padrão. Para ligar: `tare.tools.tune.archetypes.REALISM.update(REALISM_CLAP)`.

## Duas formas de usar

### 1. Offline: gerar assets para qualquer engine

Um arquivo de bestiário vira pacotes de WAV, mais um `manifest.json` e o spec JSON de cada som:

```bash
tare.tools.tune bake examples/bestiary.json -o baked     # 19 criaturas x 5 chamados x 3 takes
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

`extends` herda de outra entrada (evoluções, variantes) e `random` sorteia uma criatura nova. Falas de NPC entram numa seção `speakers`, com o papel ou a voz e as falas de cada um:

```json
"speakers": {
  "rei":      {"role": "main", "gender": "m", "lines": {"missao": "Salve o reino!"}},
  "ferreiro": {"voice": "deep", "lang": "pt", "lines": {"oi": "Bem-vindo à forja, viajante!"}},
  "guarda":   {"voice": "npc:12", "lines": {"alto": "Alto lá! Quem vem?"}},
  "povo":     {"role": "crowd", "lines": {"conversa": "Que dia bonito hoje."}},
  "lobo":     {"creature": "wolf", "lines": {"oi": "Olá, viajante."}}
}
```

`"natural_voices": false` no topo do arquivo (ou `bake --no-natural`) deixa todas as falas no motor de formantes.

Importe `baked/` na Unity, Godot, Unreal, FMOD ou Wwise e sorteie um take por chamado.

### 2. Runtime: gerar dentro do jogo

- **Jogos em Python** (pygame, pyglet, Arcade, Panda3D, Ren'Py): `VoiceBank` renderiza em threads, mantém cache e nunca repete o mesmo take duas vezes seguidas. Veja [`examples/pygame_demo.py`](examples/pygame_demo.py).

  ```python
  from tare.tools.tune.runtime import VoiceBank

  bank = VoiceBank(sample_rate=44100, takes=4)
  bank.warm(lobo)                                     # durante o loading
  audio = bank.get(lobo, "attack", block=False)       # None se ainda não ficou pronto
  fala = bank.line(Speaker.preset("child"), "Oi!")    # falas também, com cache
  ```

- **Outras engines:** o som é descrito por um **spec JSON** portável. A aleatoriedade é SplitMix64 + FNV-1a, com vetores de teste, e o renderizador usa só blocos simples (PolyBLEP, biquads, one-pole). Um renderizador nativo em C#, GDScript ou C++ pode tocar specs gerados aqui ou, portando também os arquétipos, inventar criaturas novas em tempo real. O contrato de portabilidade está em [`docs/arquitetura.md`](docs/arquitetura.md).

## Linha de comando

```bash
tare.tools.tune list                                                    # arquétipos e chamados
tare.tools.tune render monster --species ogro --size .9 --aggression .8 --call attack -o ogro.wav --png
tare.tools.tune spec chip --species 3 --call hurt -o pixel_hurt.json    # spec JSON para engines
tare.tools.tune from-spec pixel_hurt.json -o pixel_hurt.wav
tare.tools.tune zoo -n 30 -o zoo                                        # 30 criaturas inéditas
tare.tools.tune gen1 pikachu                                            # reprodução da 1ª geração
tare.tools.tune gen1 all -o gen1/
tare.tools.tune say "Olá, viajante!" --voice child -o ola.wav --phonemes  # fala
tare.tools.tune say "Hello there!" --lang en --voice npc:7 --pitch 140
tare.tools.tune say "Que dia bonito!" --role crowd --name povo            # balbucio de multidão
tare.tools.tune say "Oi, tudo bem?" --voice cute --style animalese
tare.tools.tune sounds                                                  # efeitos: tipos, estilos, eventos
tare.tools.tune sfx blade steel --event clash --species excalibur -o choque.wav
tare.tools.tune sfx ambience storm --event loop -o tempestade.wav       # loop sem emenda
tare.tools.tune voices                                                  # vozes prontas
```

## Reprodução da 1ª geração

`tare.tools.tune.chip` reimplementa o motor de gritos de Pokémon Red/Blue: 2 canais de pulso e 1 de ruído, a 1.048.576 Hz, com filtro anti-aliasing na decimação. Ele foi verificado contra o motor TypeScript original do fork, congelado em `tests/fixtures/gen1`, nos 151 gritos:
- durações idênticas;
- ruído bit a bit;
- pulsos iguais, exceto bordas isoladas deslocadas em 1 amostra (~1 µs), que vêm do arredondamento de ponto flutuante do código antigo.

Por padrão, o ruído de 7 bits segue o hardware real, o que corrige um bug do app antigo. `--legacy-noise` reproduz o comportamento antigo.

Os dados dos gritos (`data/gen1/cries.json`) são dados de jogo de terceiros. Ficam no repositório só como referência e para testes, e **não fazem parte do pacote**. Para usar a partir de um pacote instalado, aponte `TARE_TOOLS_TUNE_GEN1_DATA` para o arquivo.

## Desenvolvimento

```bash
pytest -q          # ~350 testes, incluindo os 151 gritos contra a referência
ruff check .

pip install -e ".[asr]"
python tools/intelligibility.py -v    # a fala, transcrita pelo Whisper (taxa de erro por caractere)

pip install -e ".[teacher]"                    # Kokoro, soundfile e pyworld: só para as ferramentas
python tools/build_speech.py render pt        # o professor lê o corpus (cache em teacher/)
python tools/build_speech.py build pt         # análise -> bancos de voz em src/tare/tools/tune/speech/data
python tools/teacher_calibration.py render    # fala natural do Kokoro como "professor" do português
python tools/teacher_calibration.py measure   # formantes, durações e fricativas medidos por fonema
python tools/structure_analysis.py compare    # espectros quadro a quadro contra o professor, por classe de fonema
python tools/structure_analysis.py mos        # naturalidade prevista (UTMOS): professor 3,5, nosso motor 2,2
python tools/structure_analysis.py transplant # qual parte da nossa fala custa naturalidade
python tools/structure_analysis.py compare --set klatt.FRIC_GAIN=2 --speaker tilt=4000   # testar uma mudança

python tools/build_barks.py --freesound DIR --oga DIR   # refaz os moldes das interjeições (precisa das gravações e do pyworld)
```

O que essas ferramentas mostraram está em [`docs/arquitetura.md`](docs/arquitetura.md): a distância para a voz natural está no envelope espectral quadro a quadro, e nenhum ajuste de parâmetros do motor de formantes a fecha. Por isso o motor natural pega o envelope de gravações (os bancos de voz) e deixa para as regras o resto: fonemas, ritmo e entonação.

O desempenho neste ambiente de desenvolvimento (4 núcleos), a 48 kHz: cada som leva de 20 a 250 ms para gerar, e `bake` produz cerca de 40 sons por segundo.

## Créditos

A pronúncia do inglês vem do [CMU Pronouncing Dictionary](https://github.com/cmusphinx/cmudict) (licença BSD, incluída em `src/tare/tools/tune/speech/data/LICENSE-cmudict`). O sintetizador de fala segue o desenho cascata/paralelo de Dennis Klatt.

Os bancos de voz natural vêm de leituras do [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0), feitas offline; o pacote leva só os números medidos nelas.

As interjeições partem de gravações CC0 do OpenGameArt ("Voice Clip Pack - Male Adventurer RPG", "Female RPG Voice Starter Pack" de Cici Fyre, "Male Grunt/Yelling sounds") e do Freesound (os ids estão em `tools/build_barks.py`). O pacote leva só os números medidos nelas; a síntese segue o desenho do vocoder [WORLD](https://github.com/mmorise/World), de Masanori Morise.

Os instrumentos foram medidos nas notas da [VSCO-2 Community Edition](https://github.com/sgossner/VSCO-2-CE), da Versilian Studios (CC0). As gravações serviram só para medir e não acompanham o pacote.

O motor de gritos da 1ª geração é baseado no [sintetizador original de dotsarecool](http://dotsarecool.com/rgme/tech/gen1cries.html) ([vídeo](https://www.youtube.com/watch?v=gDLpbFXnpeY)) e no [port em TypeScript de ardean](https://github.com/ardean/pokemon-gen1-cry-synthesizer), de onde este repositório foi forkado.
