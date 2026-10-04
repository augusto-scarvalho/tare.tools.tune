# tare.tools.tune

Áudio procedural para jogos: **criaturas**, **fala humana** (português e inglês) e **efeitos sonoros** (armas, passos, explosões, magia, ambientes). Para criaturas, você descreve **quem** chama (espécie, tamanho, agressividade) e **por quê** (idle, alerta, ataque, dor, morte). Para pessoas, você escolhe uma voz e escreve o texto. Para efeitos, você escolhe o objeto (uma espada de aço, uma bola de fogo, uma tempestade) e o evento (golpe, choque, impacto, loop). A mesma entrada sempre gera o mesmo som, e cada indivíduo e cada repetição varia um pouco.

Começou como `creaturesynth`, a partir do [sintetizador de gritos da 1ª geração de Pokémon](https://github.com/ardean/pokemon-gen1-cry-synthesizer) de ardean. A ideia do jogo, que tira 151 gritos de 38 moldes mais tom e duração, virou o modelo geral aqui: **espécie = genes estáveis; indivíduo = pequenas variações; traços = evolução**. O motor original continua disponível como arquétipo `chip` e como reprodução fiel dos 151 gritos.

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

### Entonação e emoções

O fim da frase segue a pontuação, com as melodias do português do Brasil:
- `.` afirmação: cai no fim;
- `?` pergunta de sim/não: sobe na última sílaba tônica e cai depois dela ("Você comprou a es**pa**da?"); se a tônica é a última sílaba, termina lá em cima ("Você viu o dra**gão**?");
- pergunta com "quem", "onde", "o que", "por que"...: cai, como uma afirmação, com a palavra interrogativa mais alta;
- `?!` surpresa ("Sério?!", "O quê?!"): a pergunta, mais alta e mais longa;
- `!` exclamação: movimentos de tom mais largos;
- `...` ou `…` reticências: fica suspensa, devagar, com pausa maior;
- `,` continuação.

**Emoções** mudam a voz inteira ou um trecho da fala, nos dois motores:

```python
rei.render("Saia daqui!", emotion="raiva")
rei.render("[alegria] Que bom te ver! [tristeza] Mas eu preciso partir...")
rei.render("[medo:0.5] Você ouviu isso?")      # intensidade de 0 a 1 (padrão 0,8)
```

`alegria`, `raiva`, `tristeza`, `medo`, `surpresa`, `sussurro` e `neutro` (também `feliz`, `triste`, `bravo`, `assustado`, `happy`, `angry`, `sad`...). Alegria, raiva e tristeza foram medidas em atores brasileiros do [emoUERJ](https://doi.org/10.5281/zenodo.5427549) (CC BY 4.0): a alegria sobe 6,3 semitons e alarga a melodia 27%; a raiva sobe 4,6, clareia o timbre e cai mais no fim; a tristeza fica 8% mais lenta, mais soprosa, com o fim menos caído e mais pausas.

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
  | `gasp` | mais ar que voz, perto do tom da fala, mais longo (medido no próprio jogo) | *Tactics Ogre* |
  | `kiai` | um grito cheio, as tomadas mais longas do intérprete, sem esticar; a dor mais escura e com mais ar (medido no próprio jogo) | *Utawarerumono* |
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
| `blade` (espadas, adagas, machados) | steel, iron, glass, wood | swing, clash, hit_flesh, hit_wood, hit_metal, hit_stone, draw, drop, quickdraw (o saque-e-corte da katana) |
| `spear` (lanças e alabardas) | spear, halberd | thrust, swing, hit_flesh, hit_metal, jump e land (o salto do dragoon) |
| `fist` (mãos nuas) | bare, gauntlet | swing, kick, hit_flesh, hit_heavy, hit_armor, block |
| `gun` (armas de fogo) | pistol, musket, cannon | shot, click, reload, impact |
| `thrown` (arremesso) | knife, shuriken, bomb | throw, fly, hit_wood, hit_flesh, fuse, blast |
| `blunt` (clavas, maças, martelos) | wood, iron, stone | swing, hit_flesh, hit_wood, hit_metal, hit_stone, drop |
| `bow` | longbow, crossbow | draw, release, fly, hit_wood, hit_flesh, hit_stone |
| `shield` (escudos) | wood, metal | block_blade, block_blunt, block_arrow, bash |
| `gear` (armaduras e roupas) | chainmail, plate, leather, cloth | move, run, equip |
| `body` (corpo caindo) | stone, wood, dirt | fall, drop |
| `door` (portas e portões) | wood, iron | open, close, locked, unlock, knock, slam, break |
| `chest` (baús) | wood, iron | open, close, locked, unlock |
| `item` (itens) | coins, potion, scroll, gem, letter | pickup, use, drop |
| `book` (livros e pergaminhos) | tome, notebook, scroll | open, close, page, flip, place, write |
| `tableware` (copos, canecas, pratos, talheres) | glass, ceramic, pewter, wood | clink, set, pour, drink, cutlery, stir, break |
| `furniture` (móveis) | wood, oak | chair, sit, desk, drawer_open, drawer_close, bed |
| `bell` (sinos) | church, hand, shop, ship | ring, toll |
| `breakable` (coisas para quebrar) | crate, barrel, pot, glass | hit, break |
| `ui` (interface) | fantasy, crystal, wood, retro | click, open, close, levelup, quest, error; para tactics: cursor, hover, target, select, confirm, cancel, scroll, range, text, advance, turn, enemy_turn, learn, battle; o que cada golpe fez: critical, miss, damage, heal, mp, ko, revive |
| `status` (estados) | fantasy, retro | buff, debuff, protect, shell, haste, slow, stop, sleep, poison, silence, blind, confuse, charm, berserk, doom, stone, toad, zombie, paralysis, regen, expire, cure |
| `lever` (alavancas) | iron, wood | pull, push |
| `trap` (armadilhas) | darts, spikes, blade | trigger, fire |
| `torch` (fogo) | torch, brazier | ignite, extinguish |
| `water` (água) | small, big | splash, dive, drip |
| `footstep` | stone, wood, metal, gravel, dirt, grass, snow, water | walk, run, land, scuff |
| `hoof` (cascos de cavalo) | dirt, grass, stone, wood, water, snow | step (um par), walk, trot, canter e gallop (loops sem emenda), halt, land |
| `horse` (cavalos) | steed, warhorse | neigh, snort, nicker, hurt, charge (a carga de cavalaria), trample |
| `wings` (asas) | feather, leather | flap, hover (loop), takeoff, land, swoop |
| `march` (tropas marchando) | infantry, heavy | loop, move, halt |
| `warp` (teleporte) | arcane, retro | out (some), in (aparece) |
| `explosion` | fire, stone, magic | blast, distant, debris |
| `spell` | fire, ice, lightning, arcane, holy, shadow, nature, heal, water, wind, earth, poison, gravity, meteor | charge, cast, travel (loop), impact |
| `summon` (invocações) | fire, ice, thunder, earth, holy, dark, dragon | arrive, strike, leave |
| `ambience` | rain, wind, fire, stream, cave, forest, night, storm, sea, dungeon; e os lugares de uma história: battlefield, camp, castle, town, tavern, dinner, plains, desert, snow, swamp, ruins, deck | loop (16 s, sem emenda), accent |

**Época (`era`).** Qualquer efeito pode vir vestido como uma geração de jogos, medida nos próprios jogos:

| `era` | como soa | medido em |
|---|---|---|
| `""` | como foi desenhado | — |
| `"hd"` | a banda inteira, uma sala e uma cauda: sons que continuam soando (a interface dura 0,8–1 s) | *Triangle Strategy*, *Octopath Traveler* |
| `"16bit"` | nada acima de ~5–8 kHz, o granulado das amostras ADPCM de 4 bits, seco (a interface dura 0,2–0,4 s) | *Tactics Ogre* (PSP), *FFTA2* (DS) |

```python
Sfx("ui", "crystal", era="hd").render("confirm")
Sfx("blade", "steel", era="16bit").render("clash")      # tare.tools.tune sfx blade steel --era 16bit
```

O timbre retrô de 8 bits continua sendo o estilo `retro` de `ui` e `status`.

**Seco (`dry`).** O `"hd"` e várias receitas (magias, invocações, caverna, castelo) gravam uma sala e uma cauda dentro do som: o eco é o mesmo em qualquer lugar, as caudas de vários sons se somam e, se o motor também puser reverberação, ela dobra. Num jogo com mapas diferentes, peça o som seco e deixe o motor dar o espaço de cada mapa (no Godot, um `AudioEffectReverb` no barramento de áudio do mapa):

```python
Sfx("ui", "crystal", era="hd", dry=True).render("confirm")   # o timbre do hd, sem sala nem cauda
```

No bestiário, `"dry": true` na entrada do som; na linha de comando, `--dry`. O `"16bit"` já é seco.

**Botões (`knobs`).** Dentro do caráter de uma receita, qualquer som varia por botões com nome, faixa e descrição, que uma pessoa ou um agente lista (`tare.tools.tune sounds --knobs`, `Sfx.knob_info()`) e combina. No padrão, o som sai exatamente como foi desenhado.

| botão | faixa | o que faz |
|---|---|---|
| `register` | −2 a 2 oitavas | tudo mais agudo ou mais grave: notas, anéis, faixas de ruído, brilho |
| `tempo` | 0,25 a 4× | o espaço entre as partes (as notas de um arpejo, os golpes de um rufar); cada parte mantém a duração |
| `length` | 0,25 a 4× | o som inteiro esticado ou comprimido no tempo, sem mudar a altura |
| `ring` | 0,1 a 4× | quanto soam as notas batidas, as barras e os sinos; quanto duram os bipes |
| `brightness` | −1 a 1 | mais escuro (−1: agudos cortados a partir de ~2 kHz) a mais brilhante (+1: golpes mais duros, parciais altos mais fortes) |
| `sparkle` | 0 a 3× | os brilhinhos por cima; 0 tira |
| `key` | nota MIDI 48 a 96 | só em `ui` e `status`: o tom do jogo (72 = Dó5); no padrão, vem da espécie |

```python
Sfx("ui", "crystal", era="hd", knobs={"register": -1, "tempo": 1.5}).render("confirm")   # mais grave e mais lento
Sfx("status", "fantasy", knobs={"sparkle": 0}).render("shell")                          # escudo mágico sem brilho
```

Na linha de comando: `tare.tools.tune sfx ui crystal --event confirm --knob register=-1 --knob tempo=1.5`. No bestiário do `bake`: `"knobs": {"register": -1}`.

Os botões gerais também giram **dentro do jogo**, sobre um spec pronto, com as mesmas contas do Python: no Godot, `som.render(spec, 48000, {"register": -1, "tempo": 1.5})`. O `key` se escolhe no desenho; no jogo, o tom muda com `register` (um semitom = 1/12).

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


**Os outros sons de RPG** seguem o mesmo método, um por um. A lista e o estado de cada um estão em [`docs/sons-rpg.md`](docs/sons-rpg.md). O que falta para tactics RPGs (no espírito de Final Fantasy Tactics, Tactics Ogre, Unicorn Overlord e Triangle Strategy) está em [`docs/sons-tactics.md`](docs/sons-tactics.md).

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
- **Instrumentos** (`tare.tools.tune.instruments`): 43 instrumentos medidos em notas gravadas, com os números de cada um no código:
  - cordas pinçadas: harpa, violão, alaúde, pizzicato;
  - teclados de percussão: glockenspiel, marimba, xilofone, celesta, caixinha de música;
  - sinos tubulares;
  - tambores: tímpanos, tambores de mão e de tronco, bumbo, caixa;
  - metais de percussão: triângulo, prato, gongo, pandeiro, chocalho;
  - sustentados: violinos, violoncelos, flauta, trompa, trompete, coro;
  - banda: baixo elétrico, piano elétrico, chimbal fechado e aberto;
  - do Japão: koto (com o *yuri*, a corda tremendo, e o *oshide*, a corda empurrada até a nota), shakuhachi, taiko, hyoshigi, rin;
  - chiptune: pulsos, baixo e ruídos de console.
- **`Cue`** (`tare.tools.tune.music`): músicas compostas a partir de uma semente.
  - Jingles: `victory`, `levelup`, `quest`, `gameover`.
  - Loops: `town`, `explore`, `tavern`, `dungeon`, `battle`.
  - Loops de "harmonia de cor", no jeito das trilhas de RPG de 16 bits (como as de Yasunori Mitsuda): `reverie`, `pastoral`, `timeless`, `grove`, `heroic`, `showdown`. Acordes escolhidos pela cor, não pela função: 7ª e 9ª deslizando em paralelo, trocas por meio tom e por terças, a tônica como pedal, modos dórico, lídio e mixolídio, nunca V → I. A melodia apoia nas 9ª e 13ª e repete o motivo em sequência.
  - Para tactics, no jeito marcial e modal das trilhas de Hitoshi Sakimoto (medido nas 37 músicas do FFTA2): batalhas `skirmish`, `tense`, `boss`, `final`; `prepare` (a formação), `briefing` (o mapa e o plano), `worldmap`; cenas `sorrow`, `intrigue`, `triumph`, `comedy`; e o jingle `recruit` (alguém entra no grupo).
  - Do Japão, com o koto, o shakuhachi, o taiko, o hyoshigi e o rin, na régua das faixas mais elogiadas de *Utawarerumono*: `shrine` (um santuário, quase sem pulso), `village` (uma vila ao entardecer), `festival` (um matsuri), `kagura` (uma batalha dançada como um kagura), `elegy` (um lamento). Escalas in, yo e ryukyu, frases com respiro (*ma*), o koto tocando a melodia do shakuhachi junto (heterofonia), a orquestra por baixo em quintas e quartas.
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

- **Godot** (`native/godot`): a extensão `tare_tune` traz o renderizador em C++. O Python desenha os sons em specs pequenos (`Sfx(...).voice("confirm").to_json()`, `Speaker.voice(texto).to_json()`: de 1 a 10 KB), e o jogo os transforma em som na hora, igual ao Python amostra por amostra. As falas usam os bancos de voz exportados (`tare.tools.tune.speech.tvb.export`, ~21 MB por voz):

  ```gdscript
  var som := TareSound.new()
  $Clique.stream = som.render(FileAccess.get_file_as_string("res://sounds/confirm.json"))
  $Grave.stream = som.render(FileAccess.get_file_as_string("res://sounds/confirm.json"), 48000,
                             {"register": -1, "tempo": 1.5})        # os botões, girados na hora
  var banco := TareVoiceBank.new()
  banco.load("res://voices/pt_alex.tvb")
  som.add_bank(banco)
  $Fala.stream = som.render(FileAccess.get_file_as_string("res://lines/00.json"))
  ```

  Saem no Godot os efeitos, as criaturas, as falas naturais e os ambientes em loop. Ainda não: o arquétipo `chip` e a 1ª geração, as interjeições e a mixagem das músicas, que por ora vão como WAV do `bake`. Uma fala de 3 s sai em ~0,13 s; o projeto de exemplo (`native/godot/demo`) gera a próxima numa thread enquanto a atual toca. Montar: `python tools/build_native.py godot` e `python tools/build_native.py demo`. O texto das falas é planejado no Python, antes; o plano em C++ (texto novo dentro do jogo) vem quando a afinação da voz assentar.

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
python tools/build_speech.py label pt         # refaz os rótulos e os modelos dos bancos, sem nova análise
python tools/real_prosody.py fetch|align|fit # experimental: entonação aprendida de leitores brasileiros reais
python tools/build_native.py build            # o vocoder em C++ (native/), para o Godot; tests/test_native.py o compara
python tools/teacher_calibration.py render    # fala natural do Kokoro como "professor" do português
python tools/teacher_calibration.py measure   # formantes, durações e fricativas medidos por fonema
python tools/structure_analysis.py compare    # espectros quadro a quadro contra o professor, por classe de fonema
python tools/structure_analysis.py mos        # naturalidade prevista (UTMOS): professor 3,5, nosso motor 2,2
python tools/structure_analysis.py transplant # qual parte da nossa fala custa naturalidade
python tools/structure_analysis.py compare --set klatt.FRIC_GAIN=2 --speaker tilt=4000   # testar uma mudança

python tools/build_barks.py --freesound DIR --oga DIR   # refaz os moldes das interjeições (precisa das gravações e do pyworld)
```

**Curadoria por ouvido** (`tools/curate.py`): rodadas de sons para comparar, servidas só nesta máquina (127.0.0.1), porque as referências de jogos não saem dela. A página toca cada versão e troca entre elas no mesmo ponto (teclas 1–9), iguala o volume e desenha o espectrograma, a diferença para uma referência e o espectro médio, além das medidas de cada uma. Ela também guarda as respostas em `answers.json` conforme são dadas: o melhor, notas de 1 a 5, uma categoria por som, ABX cego, momentos marcados no espectrograma e notas livres. Uma rodada cega esconde os nomes e embaralha a ordem.

```bash
python tools/curate.py serve          # abre http://127.0.0.1:8765 com as rodadas
python tools/curate.py answers NOME   # o que foi respondido numa rodada
```

O que essas ferramentas mostraram está em [`docs/arquitetura.md`](docs/arquitetura.md): a distância para a voz natural está no envelope espectral quadro a quadro, e nenhum ajuste de parâmetros do motor de formantes a fecha. Por isso o motor natural pega o envelope de gravações (os bancos de voz) e deixa para as regras o resto: fonemas, ritmo e entonação.

O desempenho neste ambiente de desenvolvimento (4 núcleos), a 48 kHz: cada som leva de 20 a 250 ms para gerar, e `bake` produz cerca de 40 sons por segundo.

## Créditos

A pronúncia do inglês vem do [CMU Pronouncing Dictionary](https://github.com/cmusphinx/cmudict) (licença BSD, incluída em `src/tare/tools/tune/speech/data/LICENSE-cmudict`). O sintetizador de fala segue o desenho cascata/paralelo de Dennis Klatt.

As medidas das emoções vêm do emoUERJ, de Rodrigo G. Bastos Germano, Michel Pompeu Tcheou, Felipe da Rocha Henriques e Sergio Pinto Gomes Junior (UERJ, 2021, [CC BY 4.0](https://doi.org/10.5281/zenodo.5427549)); as gravações serviram só para medir.

Os bancos de voz natural vêm de leituras do [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache-2.0), feitas offline; o pacote leva só os números medidos nelas.

O núcleo nativo (`native/`) usa a [pocketfft](https://gitlab.mpcdf.mpg.de/mtr/pocketfft), de Martin Reinecke e Peter Bell (Max-Planck-Society, BSD-3), a mesma FFT do numpy.

A ferramenta experimental de entonação (`tools/real_prosody.py`) mede fala real do [TTS-Portuguese Corpus](https://github.com/Edresson/TTS-Portuguese-Corpus), de Edresson Casanova e colegas (CC BY 4.0), e da parte em português do [CML-TTS](https://www.openslr.org/146/), de Frederico S. Oliveira e colegas, sobre audiolivros do LibriVox (CC BY 4.0), alinhada com o [Montreal Forced Aligner](https://montreal-forced-aligner.readthedocs.io/) e o modelo português dele (CC BY 4.0). Nada disso vai no pacote.

As interjeições partem de gravações CC0 do OpenGameArt ("Voice Clip Pack - Male Adventurer RPG", "Female RPG Voice Starter Pack" de Cici Fyre, "Male Grunt/Yelling sounds") e do Freesound (os ids estão em `tools/build_barks.py`). O pacote leva só os números medidos nelas; a síntese segue o desenho do vocoder [WORLD](https://github.com/mmorise/World), de Masanori Morise.

Os instrumentos foram medidos nas notas da [VSCO-2 Community Edition](https://github.com/sgossner/VSCO-2-CE), da Versilian Studios (CC0). As gravações serviram só para medir e não acompanham o pacote.

O motor de gritos da 1ª geração é baseado no [sintetizador original de dotsarecool](http://dotsarecool.com/rgme/tech/gen1cries.html) ([vídeo](https://www.youtube.com/watch?v=gDLpbFXnpeY)) e no [port em TypeScript de ardean](https://github.com/ardean/pokemon-gen1-cry-synthesizer), de onde este projeto começou (o histórico do git ainda guarda os commits dele).
