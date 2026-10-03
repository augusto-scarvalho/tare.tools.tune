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

Siglas: FFT, FFTA (inclui o FFTA2), TO (Tactics Ogre), UO (Unicorn Overlord), TS (Triangle Strategy).

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
| Comprar e vender, equipar, trocar de classe | todos | parcial: `item` coins, `gear` equip | B |
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
| Acerto crítico: mais peso e um brilho | todos | medido: `ui` critical, por cima do golpe da arma | A |
| Errou, esquivou | todos | medido: `ui` miss | A |
| Bloquear com escudo, aparar com a arma | todos | tem: `shield`, `blade` clash | A |
| Número de dano aparecendo, número de cura | todos | medido: `ui` damage, heal | A |
| Estados: veneno, sono, silêncio, cegueira, parar, lentidão e pressa, fúria, charme, confusão, morte anunciada, pedra, sapo, zumbi; e a cura deles | todos | medido: `status` sleep, haste; desenhado: os outros (`status`) | A |
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
| Lanças e alabardas: estocada; o salto do dragoon (sobe, cai) | todos | falta | A |
| Mãos nuas: soco, chute | FFT, FFTA | falta | A |
| Katana: sacar e cortar num golpe só | FFT, FFTA | parcial: `blade` draw, swing | B |
| Armas de fogo: tiro, recarregar | FFT, FFTA | falta | B |
| Arremesso: shuriken, facas, bombas | FFT, FFTA | falta | B |
| Chicote, livro, instrumento do bardo, dança, cartas e dados | FFT, FFTA | falta | C |
| Cerco: catapulta, balista, aríete | TO, UO, TS | falta | C |

## 5. Magias

| Som | Jogos | Hoje | Prioridade |
|---|---|---|---|
| Fogo, gelo, raio, arcano, sagrado, sombra, natureza, cura | todos | tem: `spell` | A |
| Água, vento, terra e terremoto, veneno | todos | falta | A |
| Níveis da mesma magia (Fire, Fira, Firaga) | FFT, FFTA | parcial: `power` | A |
| Tempo: pressa, lentidão, parar, gravidade, meteoro | FFT, FFTA | parcial: `status` haste, slow, stop | B |
| Invocações: chegada, golpe, saída | FFT, FFTA | falta | B |
| Conjuração carregando por turnos | FFT, TO | parcial: `spell` charge | B |
| Terreno reagindo: óleo pegando fogo, água eletrificada, gelo, vento empurrando | TS | parcial: `spell`, `torch`, `water` | B |
| Geomancia, canções, danças | FFT, FFTA | falta | C |

## 6. Unidades e movimento

| Som | Jogos | Hoje | Prioridade |
|---|---|---|---|
| Passos em 8 chãos, saltos de altura, armadura | todos | tem: `footstep`, `gear` | A |
| Cavalaria: cavalo andando, galopando, investida, relincho | TO, UO, TS | falta | A |
| Voadores: asas (grifo, wyvern, homem-falcão), pouso | TO, UO, FFTA | falta | B |
| Tropas marchando no mapa | UO | falta | B |
| Chocobo e outras montarias | FFT, FFTA | parcial: criatura `bird` | C |
| Teletransporte | FFT, FFTA | falta | C |

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
| Gritos de golpe, dor, morte, comemoração | todos | tem: `emote`, estilo `tactics` | A |
| Frases curtas de batalha e diálogos de história em português | todos | tem: voz natural | A |
| As mesmas falas em inglês | todos | falta: bancos em inglês | B |
| Monstros e personagens que "falam" sem palavras | FFTA | parcial: balbucio | C |

## 9. Ambientes

| Som | Jogos | Hoje | Prioridade |
|---|---|---|---|
| Chuva, vento, fogo, riacho, caverna, floresta, noite, tempestade, mar, masmorra | todos | tem: `ambience` | B |
| Campo de batalha, acampamento, salão de castelo, cidade e mercado, planície, deserto, neve e montanha, pântano, ruínas e templo, convés de navio | todos | falta | B |

## 10. Música

| Som | Jogos | Hoje | Prioridade |
|---|---|---|---|
| Vitória, nível, missão, derrota, cidade, exploração, taverna, masmorra, batalha, 6 loops de "cor" | todos | tem: `Cue` | B |
| Várias batalhas (normal, tensa, chefe, final), preparação, briefing no mapa, mapa-múndi, cenas (tristeza, intriga, triunfo, comédia), recrutamento | todos | falta | B |
| O estilo: orquestra marcial e medieval (metais, cordas, caixa clara, modos), como Sakimoto (FFT, FFTA, TO, UO) e Senju (TS) | todos | parcial: estilo `orchestral` | B |

## 11. Mecânicas de cada jogo

| Som | Jogos | Hoje | Prioridade |
|---|---|---|---|
| Juiz: apito, cartão amarelo e vermelho | FFTA | falta | C |
| Cartas de tarô; voltar o tempo | TO | falta | C |
| Encontro de tropas, captura de fortaleza, libertação de cidade | UO | falta | C |
| Balança da Convicção: votação, convicção ganha | TS | falta | C |

## Ordem proposta

1. **Grade, menus e o ritmo da batalha** (seções 1 e 2): o que se ouve a cada segundo, e o que mais dá cara de tactics.
2. **Resultado de cada golpe** (seção 3): crítico, erro, dano, cura, estados, atributos.
3. **Armas que faltam** (seção 4): estocada, mãos nuas, armas de fogo, arremesso.
4. **Magias que faltam** (seção 5): água, vento, terra, veneno, tempo, invocações.
5. **Cavalaria e voadores** (seção 6).
6. **Ambientes e música de tactics** (seções 9 e 10).
7. **Monstros e as mecânicas de cada jogo** (seções 7 e 11).
