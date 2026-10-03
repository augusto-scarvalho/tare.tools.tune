# Sons de tactics RPG

O que um tactics RPG no espírito de Final Fantasy Tactics, FFTA, FFTA2, Tactics Ogre, Unicorn Overlord e Triangle Strategy precisa, o que o tare.tools.tune já faz e o que falta. Cada som novo segue o método de [`sons-rpg.md`](sons-rpg.md): medir gravações reais, modelar, ouvir no contexto, integrar.

**Hoje:**
- **tem:** já sai, com a receita entre crases;
- **medido:** feito a partir de gravações medidas, falta ouvir e aprovar;
- **desenhado:** feito sem gravação de referência, pelo que os clássicos fazem; falta ouvir e aprovar;
- **parcial:** algo parecido existe, mas não é o som certo;
- **falta:** ainda não existe.

**Prioridade:** quanto o jogador ouve o som.
- **A:** a cada ação;
- **B:** a cada batalha;
- **C:** de vez em quando.

Siglas: FFT, FFTA (inclui o FFTA2), TO (Tactics Ogre), UO (Unicorn Overlord), TS (Triangle Strategy), OT (Octopath Traveler).

**Época.** Todo som pode sair em três épocas (`Sfx(..., era=...)`), medidas nos próprios jogos: `hd` (TS, OT), `16bit` (TO, FFTA2) e o desenho como está. O 8 bits é o estilo `retro`.

**Botões.** Dentro de cada som, `knobs` variam registro, andamento, duração, anel, brilho, cintilância e o tom do jogo (`tare.tools.tune sounds --knobs`).

## 1. Grade e menus

O que mais se ouve num tactics: o cursor passa por dezenas de casas a cada turno, então precisa de variações discretas que não cansem. Os quatro timbres de `ui` (fantasy, crystal, wood, retro) foram aprovados de ouvido e ficam à escolha de quem monta o jogo.

| Som | Jogos | Hoje | Prioridade |
|---|---|---|---|
| Cursor andando de casa em casa | todos | tem: `ui` cursor | A |
| Cursor sobre uma unidade (aliada, inimiga) | todos | tem: `ui` hover, target | A |
| Selecionar unidade, confirmar, cancelar | todos | tem: `ui` select, confirm, cancel | A |
| Ação impossível (fora do alcance, sem MP) | todos | tem: `ui` error | A |
| Abrir e fechar menu, rolar lista, trocar aba | todos | tem: `ui` open, close, scroll | A |
| Mostrar o alcance de movimento ou de ataque no chão | todos | tem: `ui` range | A |
| Texto aparecendo letra a letra, com a cor da voz de quem fala | FFTA, TO | tem: `ui` text (`size` engrossa a voz); balbucio `animalese` | A |
| Avançar o diálogo | todos | tem: `ui` advance | A |
| Escolher para onde a unidade fica virada | FFT, FFTA, TO | falta | B |
| Comprar e vender, equipar, trocar de classe | todos | parcial: `item` coins, letter, `gear` equip | B |
| Salvar e carregar | todos | falta | C |

## 2. Ritmo da batalha

| Som | Jogos | Hoje | Prioridade |
|---|---|---|---|
| Fase ou turno do jogador, do inimigo, de aliados | FFTA, TO, UO, TS | tem: `ui` turn, enemy_turn | A |
| Vez de uma unidade, contagem do CT | FFT, TO | tem: `ui` turn, enemy_turn | A |
| Início da batalha | todos | tem: `ui` battle | B |
| Vitória, derrota, subir de nível, objetivo cumprido | todos | tem: `Cue` victory, gameover, levelup, quest | B |
| Aprender habilidade, liberar classe nova | FFT, FFTA, TO | tem: `ui` learn | B |
| Reforços chegando | todos | falta | C |
| Item raro, tesouro, o cristal de quem caiu | FFT, TO | parcial: `item` gem, `chest` | C |
| Contagem regressiva de unidade caída | FFT, TO | falta | C |

## 3. Resultado de cada golpe

| Som | Jogos | Hoje | Prioridade |
|---|---|---|---|
| Acerto normal (carne, armadura, madeira, pedra) | todos | tem: `blade`, `blunt`, `bow` hit_* | A |
| Acerto crítico: mais peso e um brilho | todos | medido no TO: `ui` critical, por cima do golpe da arma | A |
| Errou, esquivou | todos | medido no TO e no FFTA2: `ui` miss | A |
| Bloquear com escudo, aparar com a arma | todos | tem: `shield`, `blade` clash | A |
| Número de dano aparecendo, número de cura | todos | medido: `ui` damage, heal | A |
| Estados: veneno, sono, silêncio, cegueira, parar, lentidão e pressa, fúria, charme, confusão, morte anunciada, pedra, sapo, zumbi, paralisia, regeneração; o fim e a cura deles | todos | medido nos jogos: `status` poison (TO), sleep, silence, blind, stop, paralysis, regen, expire (TS); desenhado: os outros | A |
| Atributo subindo e descendo, proteção, escudo mágico | todos | medido: `status` buff, debuff, protect; desenhado: shell | A |
| Unidade caindo, reviver | todos | medido: `body` fall com `ui` ko; `ui` revive | A |
| Contra-ataque, ataque em conjunto | FFT, TS, UO | parcial | B |
| MP recuperado | todos | desenhado: `ui` mp | B |

## 4. Armas por classe

| Som | Jogos | Hoje | Prioridade |
|---|---|---|---|
| Espadas, adagas, machados | todos | tem: `blade` | A |
| Maças, martelos, cajados | todos | tem: `blunt` | A |
| Arcos e bestas | todos | tem: `bow` | A |
| Lanças e alabardas: estocada; o salto do dragoon (sobe, cai) | todos | medido nos jogos: `spear` | A |
| Mãos nuas: soco, chute | FFT, FFTA | medido: `fist` | A |
| Katana: sacar e cortar num golpe só | FFT, FFTA | medido nos jogos: `blade` quickdraw | B |
| Armas de fogo: tiro, recarregar | FFT, FFTA | medido nos jogos: `gun` | B |
| Arremesso: shuriken, facas, bombas | FFT, FFTA | medido nos jogos: `thrown` | B |
| Chicote, livro, instrumento do bardo, dança, cartas e dados | FFT, FFTA | falta | C |
| Cerco: catapulta, balista, aríete | TO, UO, TS | falta | C |

## 5. Magias

| Som | Jogos | Hoje | Prioridade |
|---|---|---|---|
| Fogo, gelo, raio, arcano, sagrado, sombra, natureza, cura | todos | tem: `spell` | A |
| Água, vento, terra e terremoto, veneno | todos | medido nos jogos: `spell` water, wind, earth, poison | A |
| Níveis da mesma magia (Fire, Fira, Firaga) | FFT, FFTA | parcial: `power` | A |
| Tempo: pressa, lentidão, parar, gravidade, meteoro | FFT, FFTA | tem: `status` haste, slow, stop; desenhado: `spell` gravity, meteor | B |
| Invocações: chegada, golpe, saída | FFT, FFTA | medido no FFTA2: `summon` | B |
| Conjuração carregando por turnos | FFT, TO | parcial: `spell` charge | B |
| Terreno reagindo: óleo pegando fogo, água eletrificada, gelo, vento empurrando | TS | parcial: `spell`, `torch`, `water` | B |
| Geomancia, canções, danças | FFT, FFTA | falta | C |

## 6. Unidades e movimento

| Som | Jogos | Hoje | Prioridade |
|---|---|---|---|
| Passos em 8 chãos, saltos de altura, armadura | todos | tem: `footstep`, `gear` | A |
| Cavalaria: cavalo andando, galopando, investida, relincho | TO, UO, TS | medido no TS: `hoof` (6 chãos, 4 andaduras em loop), `horse` | A |
| Voadores: asas (grifo, wyvern, homem-falcão), pouso | TO, UO, FFTA | medido no TS e no FFTA2: `wings` feather, leather | B |
| Tropas marchando no mapa | UO | desenhado: `march` (loop, move, halt) | B |
| Chocobo e outras montarias | FFT, FFTA | parcial: criatura `bird` | C |
| Teletransporte | FFT, FFTA | medido no FFTA2 e no TO: `warp` arcane, retro | C |

## 7. Monstros

| Som | Jogos | Hoje | Prioridade |
|---|---|---|---|
| Feras, pássaros, insetos, répteis, anfíbios, monstros, gosmas, espíritos | todos | tem: arquétipos de `Creature` | A |
| Mortos-vivos: ossos chacoalhando, lamento | todos | parcial: `spirit` | B |
| Dragão: rugido, sopro | todos | falta | B |
| Golem, construto de pedra | todos | parcial: `robot` | C |
| Planta (morbol), bomba (inflar e explodir) | FFT, FFTA | parcial: `slime`, `explosion` | C |

## 8. Vozes

| Som | Jogos | Hoje | Prioridade |
|---|---|---|---|
| Gritos de golpe, dor, morte, comemoração | todos | tem: `emote`, estilos `tactics` e `gasp` (medido no TO) | A |
| Frases curtas de batalha e diálogos de história em português | todos | tem: voz natural | A |
| As mesmas falas em inglês | todos | falta: bancos em inglês | B |
| Monstros e personagens que "falam" sem palavras | FFTA | parcial: balbucio | C |

## 9. Ambientes

| Som | Jogos | Hoje | Prioridade |
|---|---|---|---|
| Chuva, vento, fogo, riacho, caverna, floresta, noite, tempestade, mar, masmorra | todos | tem: `ambience` | B |
| Campo de batalha, acampamento, salão de castelo, cidade e mercado, planície, deserto, neve e montanha, pântano, ruínas e templo, convés de navio | todos | medido no TS e no TO: `ambience` battlefield, camp, castle, town, plains, deck; desenhado: desert, snow, swamp, ruins | B |

## 10. Música

| Som | Jogos | Hoje | Prioridade |
|---|---|---|---|
| Vitória, nível, missão, derrota, cidade, exploração, taverna, masmorra, batalha, 6 loops de "cor" | todos | tem: `Cue` | B |
| Várias batalhas (normal, tensa, chefe, final), preparação, briefing no mapa, mapa-múndi, cenas (tristeza, intriga, triunfo, comédia), recrutamento | todos | tem (medido no FFTA2, aprovado de ouvido): `Cue` skirmish, tense, boss, final, prepare, briefing, worldmap, sorrow, intrigue, triumph, comedy, recruit | B |
| O estilo: orquestra marcial e medieval (metais, cordas, caixa clara, modos), como Sakimoto (FFT, FFTA, TO, UO) e Senju (TS) | todos | tem (aprovado de ouvido, na orquestra e no 16-bit): os cues de tactics (`music_tactics.py`) | B |

## 11. Mecânicas de cada jogo

| Som | Jogos | Hoje | Prioridade |
|---|---|---|---|
| Juiz: apito, cartão amarelo e vermelho | FFTA | falta | C |
| Cartas de tarô; voltar o tempo | TO | falta | C |
| Encontro de tropas, captura de fortaleza, libertação de cidade | UO | falta | C |
| Balança da Convicção: votação, convicção ganha | TS | falta | C |

## 12. Cenas de história (o dia a dia)

| Som | Jogos | Hoje | Prioridade |
|---|---|---|---|
| Portas: abrir, fechar, trancada, bater, tranco, arrombar | todos | medido: `door` (slam e break nos jogos) | A |
| Livros e páginas: abrir, fechar, virar, folhear, pousar, escrever | todos | medido: `book` | A |
| Copos, canecas e pratos: brinde, pousar, servir, beber, talheres, mexer, quebrar | todos | medido: `tableware` | A |
| Móveis: cadeira, sentar, mesa, gaveta, cama | todos | medido: `furniture` | B |
| Sinos: igreja e casamento, mão, loja, navio | todos | medido: `bell` | B |
| Cartas e encomendas passadas de mão em mão; roupa (ajoelhar, reverência) | TS | medido: `item` letter, `gear` cloth | B |
| Um salão de jantar, uma taverna cheia | TS | medido no TS: `ambience` dinner, tavern | C |

## Ordem proposta

1. **Grade, menus e o ritmo da batalha** (seções 1 e 2): o que se ouve a cada segundo, e o que mais dá cara de tactics.
2. **Resultado de cada golpe** (seção 3): crítico, erro, dano, cura, estados, atributos.
3. **Armas que faltam** (seção 4): estocada, mãos nuas, armas de fogo, arremesso.
4. **Magias que faltam** (seção 5): água, vento, terra, veneno, tempo, invocações.
5. **Cavalaria e voadores** (seção 6).
6. **Ambientes e música de tactics** (seções 9 e 10).
7. **Monstros e as mecânicas de cada jogo** (seções 7 e 11).
