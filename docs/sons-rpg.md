# Sons essenciais de RPG

O que um RPG de ação ou aventura precisa, na ordem em que estamos fazendo. Cada som segue o mesmo método:
1. medir gravações reais;
2. modelar o mecanismo com esses números;
3. ouvir no contexto (golpe e acerto juntos, o disparo inteiro);
4. integrar.

As gravações servem só para medir e não entram no repositório.

**Estados:**
- **aprovado:** medido e escolhido de ouvido.
- **medido:** modelado a partir de gravações, falta ouvir.
- **antigo:** a primeira versão, desenhada sem gravações.
- **falta:** ainda não existe.

| # | Som | Receita e eventos | Estado |
|---|---|---|---|
| 1 | Espada: golpe no ar, choque, acertos (madeira, pedra, armadura, carne) | `blade` swing, clash, hit_* | aprovado |
| 2 | Espada: sacar da bainha, cair no chão | `blade` draw, drop | medido |
| 3 | Arco: puxar, soltar, voo, flecha na madeira | `bow` draw, release, fly, hit_wood | aprovado |
| 4 | Arco: flecha em carne e em pedra | `bow` hit_flesh, hit_stone | medido |
| 5 | Maça e martelo: golpe no ar, acertos, cair no chão | `blunt` | medido |
| 6 | Escudo: bloquear espada, maça e flecha (madeira, metal), empurrão | `shield` block_blade, block_blunt, block_arrow, bash | medido |
| 7 | Passos: 8 chãos × andar, correr, aterrissar, arrastar | `footstep` | medido |
| 8 | Equipamento em movimento: cota de malha, placas, couro | `gear` move, run, equip | medido |
| 9 | Corpo caindo no chão (pedra, madeira, terra) | `body` fall, drop | medido |
| 10 | Baú: abrir, fechar, trancado, destrancar | `chest` open, close, locked, unlock | medido |
| 11 | Porta e portão: abrir rangendo, fechar, trancada, destrancar, bater | `door` open, close, locked, unlock, knock | medido |
| 12 | Itens: moedas, poção, pergaminho, gema × pegar, usar, derrubar | `item` pickup, use, drop | medido |
| 13 | Quebrar: caixa ou barril de madeira, vaso de cerâmica, vidro | `breakable` hit, break | medido |
| 14 | Interface: clique, abrir e fechar inventário, subir de nível, missão cumprida, erro | `ui` (fantasy, retro) | medido |
| 15 | Mundo: alavanca, armadilhas (dardos, espinhos, lâmina), tocha, água (gota, respingo, mergulho) | `lever`, `trap`, `torch`, `water` | medido |
| 16 | Magias: 8 elementos × carregar, lançar, viajar, impacto | `spell` | medido (fogo, gelo, raio, cura, arcano) |
| 17 | Ambientes: 10 lugares em loop, com eventos soltos | `ambience` | medido (8 dos 10 contra gravações) |
| 18 | Explosões: perto, longe, destroços | `explosion` | medido |
