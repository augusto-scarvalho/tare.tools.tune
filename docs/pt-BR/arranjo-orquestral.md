# Como uma batalha orquestral é montada

[English](../orchestral-arrangement.md)

O que um estudo de música orquestral de jogos encontrou, como foi medido, o que um ouvinte escolheu depois e o que
isso mudou no tune. Só os números ficam: nenhuma gravação, partitura ou transcrição do estudo está no repositório.

## Três coisas de que uma peça é feita

| Camada | O que guarda | Onde foi lida |
|---|---|---|
| A partitura | que parte toca o quê e quando: papéis, registros, entradas, forma | partituras (MusicXML) |
| Timbre | como cada instrumento soa: parciais, ataque, decaimento | notas gravadas isoladas |
| Mixagem e execução | quanto cada parte pesa: nível por seção, graves, percussão | a gravação |

O áudio responde a segunda e a terceira. Para a primeira, a partitura foi a única fonte que se sustentou.

## O que foi medido

**Um álbum de trilha, 71 faixas** (*Triangle Strategy*; `tools/music_study.py`). Andamento, tamanho do loop, nível
ao longo do tempo, parcela de graves e de agudos, parcela percussiva. Comparadas com as nossas `battle` e
`skirmish`, as batalhas dele são mais longas (loops de cerca de dois minutos; os nossos, de 25 a 50 s), variam mais
de nível (4,4 dB contra 2,1), abrem abaixo do próprio nível mediano (3,5 dB contra 0,3) e têm mais grave (39 % da
energia abaixo de 200 Hz contra 11 %) e mais percussão (19 % contra 7 %). O andamento medido pode sair pela metade
(a nossa `skirmish`, de 155 bpm, foi lida como 77), e a estimativa de tom não merece confiança quando a margem é
pequena.

**Quais instrumentos, por modelos** (as 13 batalhas, numa GPU). Etiquetas sem treino específico (CLAP) acertam a
família (metais em 94 % dos trechos de 10 s, orquestra de cordas em 71 %) e nada mais fino. Um separador de camadas
treinado em pop (Demucs) põe cordas médias e graves em "violão" e o bumbo em "baixo". A proximidade com notas reais
isoladas (VSCO-2, CC0) resolveu duas dúvidas que as etiquetas deixaram: o "violão" são violas e violoncelos, e uma
das batalhas tem piano.

**Um transcritor** (YourMT3+), conferido contra a partitura da mesma peça: na gravação real ele encontra de 55 a
67 % das notas afinadas (de 18 a 27 % por acaso), de um terço a metade do que ele reporta está na partitura, a
percussão fica no nível do acaso, e quase toda nota volta como "conjunto". Serve para conferir, não para substituir
uma partitura.

**22 partituras** de música de jogos e de tela, arranjos de fãs para orquestra (`tools/score_study.py`):

| O que têm em comum | Partituras |
|---|---|
| Uma nota por ataque em cada parte (1,4 ou menos): linhas, não acordes em bloco | 22 de 22 |
| Saltos maiores que uma quarta em um quinto dos movimentos ou menos | 20 de 22 |
| O número de partes tocando cresce 1,5 vez ou mais | 21 de 22 |
| Os 4 compassos mais cheios têm o dobro de notas dos mais vazios, ou mais | 21 de 22 |
| A parte mais ocupada é percussão | 7 de 22 |

A quantidade de notas não é o que as distingue: contando cada nota uma vez, por mais partes que a dobrem, batalhas
e peças de ação vão de 4 a 45 notas por segundo, e as nossas ficam dentro disso.

## As nossas na mesma régua

`Score.arrangement()` lê uma partitura nossa com a mesma função que lê aquelas
(`tare.tools.tune.score.arrangement`).

| | notas por ataque | saltos | partes crescem | razão de densidade |
|---|---|---|---|---|
| As 22 partituras, mediana | 1,1 | 0,10 | 3,7x | 6,9x |
| `battle` (semente 1) | 1,22 | 0,35 | 1,0x | 1,0x |
| `skirmish` (semente 1) | 1,14 | 0,49 | 1,3x | 1,2x |
| `march` (sementes 1 a 3) | 1,00 | 0,03 | 4,0x | 8,2x a 8,8x |

## O que um ouvinte escolheu

Um ouvinte sem treino, rodadas cegas, escolha forçada. Poucas escolhas: são pistas, não provas.

- **Uma melodia, dois arranjos, mesmo andamento e duração.** O arranjo pelas quatro regras foi escolhido em vez do
  jeito da `battle` (trompas em acordes de três notas, cordas em arpejos com saltos, todos desde o compasso 1).
- **`march` por semente contra `battle`, três pares.** A `battle` foi escolhida em dois. As notas: dois pratos
  soltos em 48 compassos soaram como erro; a 120 bpm pareceu parada; o `march` que ganhou era o mais rápido.
- **Notas curtas das cordas.** O dedilhado foi escolhido em vez do arco lento e do spiccato medido; um spiccato com
  metade do ataque gravado, em que a altura aparece antes, foi escolhido em vez do dedilhado.
- **As previsões do assistente** a partir desses números acertaram 1 de 5. Os números de arranjo não preveem este
  ouvinte; andamento e um detalhe estranho pesaram mais.

## O que mudou no tune

- **`march`**: batalha por semente montada pelas quatro regras, as notas rápidas na caixa, um prato em cada frase
  forte, de 126 a 142 bpm.
- **`spiccato`**: o golpe saltado de um naipe de cordas, medido em 186 notas gravadas, com metade do ataque gravado.
- **`snare`**: reafinada pelas gravações (era quase só esteira); isso altera toda música que a toca. Tímpano e bumbo
  foram medidos do mesmo jeito e já batiam.
- **`Score.arrangement()`**, e na DSL `dsl check ARQUIVO --name NOME --layout`, que lê o arranjo e os choques
  a partir das notas, sem renderizar, de modo que uma peça grande demais para o review ainda pode ser lida (o
  `dsl review` acrescenta o mesmo `arrangement` aos fatos quando a peça cabe). `dsl help arrangement` guarda
  as regras para o agente que compõe.

## Para repetir

```bash
python tools/music_study.py PASTA_DE_GRAVACOES -o study.json   # andamento, loop, mapa de nível, equilíbrio
python tools/score_study.py PASTA_DE_PARTITURAS -o scores.json # partes, registros, entradas, as regras comuns
python tools/score_study.py UMA_PARTITURA.mxl                  # uma peça, parte por parte
```

Mantenha gravações e partituras fora do repositório (`private/` é ignorado). O que ainda pede um ouvido: se o
`march` agora se sustenta contra a `battle`, a abertura baixa dele (de 6 a 8 dB abaixo do nível mediano, quando o
usual é de 2 a 5) e o baque que falta à caixa abaixo de 150 Hz.
