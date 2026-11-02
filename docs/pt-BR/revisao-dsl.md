# Revisar e editar um som

[Referência principal em inglês](../dsl-review.md) · [Guia para agentes](dsl-agentes.md)

O fluxo `dsl review` → `describe` → `edit` usa os bundles existentes como registro
do áudio observado. Não existe uma revisão “mais recente” escolhida implicitamente.

```bash
tare.tools.tune dsl help edit --json
tare.tools.tune dsl review examples/dsl-bank.tune.json --name confirm -o output/reviews --json
tare.tools.tune dsl describe BUNDLE --fields power --json
tare.tools.tune dsl edit examples/dsl-bank.tune.json --from-bundle BUNDLE -o output/reviews --set /with/power 0.65 --json
```

Substitua `BUNDLE` pelo caminho retornado. A resposta da revisão reúne o caminho
do bundle, `audio.wav` relativo a ele, duração, canais, níveis, processamento,
tempos/notas das faixas, capacidades de exportação e verificações solicitadas.
Use `--previous BUNDLE` para comparar com uma observação explícita da mesma fonte
e do mesmo som. Revisar um bundle preservado não recompila nem consulta os assets
atuais. As listas são limitadas por `--limit` (padrão 5, máximo 100).

`describe` mostra valores, caminhos e operações disponíveis. `--find confirm`
retorna candidatos por nomes e rótulos explícitos, sem decidir automaticamente
entre eles. `--fields` seleciona até 32 nomes exatos. Parâmetros de uma invocação
usam `/with/NOME`; defaults compartilhados usam `/params/NOME/default`.

`--set` altera a fonte autoral. `--refine /lowpass 2400` preserva a receita e cria
ou atualiza um único wrapper `edit` com guard de materialização. Com `--layer ID`,
o refinamento de uma camada original da Voice raiz usa seu caminho original,
mesmo após remoções. Camadas adicionadas e camadas internas de Score/Cue continuam
usando edição autoral ou `expand`/`patch`. Transposição musical pertence às Notes.
Não misture `--set` e `--refine` no mesmo lote.

Cada edição exige o bundle observado salvo em disco e verifica integridade,
revisão da fonte, compilador, renderizador, materialização e hashes de assets.
O candidato é renderizado e verificado antes do backup e da troca atômica da
fonte. Fonte, dependências ou código alterados exigem nova revisão; não há retry
com revisão substituída silenciosamente. `--dry-run` e candidatos reprovados
produzem bundles somente para leitura. Falhas preservam a fonte anterior.

## Pedir uma escuta

As verificações não julgam timbre: `perceptual_quality` continua `not_run`. Quando
a próxima decisão precisa de ouvido, gere candidatos com `--dry-run` a partir de
uma mesma observação, monte uma rodada de curadoria e leia a resposta como dados:

```bash
tare.tools.tune dsl edit bank.tune.json --from-bundle A -o output/reviews --set /power 0.9 --dry-run --response compact --json   # -> B
tare.tools.tune dsl edit bank.tune.json --from-bundle A -o output/reviews --set /power 0.2 --dry-run --response compact --json   # -> C
python tools/curate.py compare power A B C --open --question "Qual soa mais firme?" --root output/rounds
python tools/curate.py serve --root output/rounds        # quem ouve responde no navegador
python tools/curate.py answers power --json --root output/rounds
```

Só as tarefas respondidas aparecem, por rótulo (A, B, C… na ordem dada ao
`compare`), com o caminho do bundle de cada rótulo; marcas são segundos no áudio
daquele candidato. Os dry runs deixam a fonte na revisão de A, então o escolhido é
confirmado repetindo a sua edição a partir de A: o áudio gravado é idêntico ao que
foi ouvido (o teste compara a identidade do PCM). Uma rodada cega (o padrão, sem
`--open`) esconde rótulos, notas e medidas só de quem ouve; `answers --json` sempre
aponta para os bundles. Os cartões dela são numerados pela posição embaralhada
(#1, #2…) e só mostram os rótulos A, B, C depois de "revelar nomes": leia a escolha
em `answers --json`, nunca pelo número de cartão citado no chat.

Use o caminho que o `describe` devolveu: `/power` serve para a receita direta do
banco criado pelos builders; um `use`, como em `examples/dsl-bank.tune.json`, pede
`/with/power`. No Git Bash, prefixe os comandos com `MSYS_NO_PATHCONV=1`, senão
`/with/power` chega como um caminho do Windows. Dois bundles viram ABX cego; mais, o melhor e notas 1–5;
`--task` aceita as tarefas da curadoria. A página iguala o volume por padrão:
passe `--keep-levels` quando o nível (força, volume) é o que se julga, e a rodada
abre com o igualar desligado.

## Comparar com uma gravação

Uma gravação do som que se quer (de um jogo, de uma captação) pode ficar ao lado
do render, em números e no ouvido. Primeiro, pergunte do que ela é feita:

```bash
tare.tools.tune study refs/clash.wav                   # KIND, as linhas do ear, IN TUNE
tare.tools.tune study refs/fala.wav --domain speech    # som com altura: fala, criatura ou sfx
tare.tools.tune study refs/clash.wav --search sfx:blade  # os 3 renders mais próximos de um kind
```

O `study` termina com os campos que chegam a cada parte, como o study do pxl
termina em "IN PXL": um op para começar, um valor onde a relação é direta
(`knobs.length` pela duração ativa, `speaker.pitch` pela altura mediana menos os
12% que a entonação acrescenta), uma direção onde não é (brilho, registro, cauda,
range, velocidade, tamanho) e o que uma gravação não diz (kind, estilo, evento,
arquétipo, palavras: isso o ouvido escolhe). O `--search sfx:KIND` renderiza todo
estilo e evento daquele kind e lista os 3 mais próximos por distância de DSP
(contornos de altura e volume, envelope, duração, ruído, sílabas); o `--search
creature` faz o mesmo com arquétipos, chamados e tamanhos, em cerca de 25 s. Cada
linha é um som para colar no banco e ouvir: perto nos números é um ponto de
partida, não uma igualdade. Depois, declare-a por som no topo do
banco; o `"reference": {"file": ...}` do documento inteiro continua valendo para os
sons sem uma própria:

```json
{"format": "tare.tools.tune.dsl", "version": 1,
 "references": {"clash": "refs/clash.wav"},
 "sounds": {"clash": {"sfx": "blade", "style": "steel", "event": "clash", "dry": true}}}
```

O `review` passa a medir o som contra ela. A resposta compacta ganha `ref`, cada
par `[gravação, som]`:

```json
"ref": {"active_s": [0.42, 0.36], "attack_ms": [0, 34], "centroid_hz": [4654, 5079], "f0_hz": "unvoiced", "env_db": 5.2}
```

Cada sinal é medido a partir do próprio início e contra o próprio pico, então o
volume da gravação, o silêncio inicial e a taxa de amostragem não contam.
`active_s` vai até 40 dB abaixo do pico (ou 6 dB acima do ruído de fundo mais
alto, o mesmo fim para os dois); `attack_ms`, até 3 dB abaixo do milissegundo mais
forte; `centroid_hz` é o brilho, na banda que as duas taxas cobrem; `f0_hz`, a
altura mediana (um zumbido acima de 1600 Hz, fora do alcance do rastreador, pela
própria frequência; `unvoiced` quando não há); `env_db`, a diferença espectral média em
dB. A resposta detalhada acrescenta `end_60_s` (o que a exportação mantém;
`not_measurable` sobre ruído alto ou quando o arquivo acaba antes), a diferença
na forma do volume e a banda que
mais difere. Os números orientam; nunca dizem que o som ficou igual: a gravação
traz sala, microfone e masterização que a síntese não tem, e dois sons diferentes
podem ter a mesma duração e o mesmo brilho.

As tolerâncias ficam no arquivo de checks (`reference` no
[exemplo](../../examples/dsl-review.checks.json)): `active_s` como `ratio`,
`attack_ms` como `max_delta`, `centroid_hz` e `f0_hz` em `semitones`, `env_db` como
`max`. Um som sem gravação fica `absent`, não reprova; uma medida pedida que não
pôde ser feita fica `not_run` e reprova como qualquer check não cumprido; gravação e
som ambos sem altura passam em `f0_hz`, um com e outro sem reprovam. Para o ouvido
decidir, ponha a gravação ao lado dos candidatos:

```bash
python tools/curate.py compare clash A B --reference refs/clash.wav --root output/rounds
```

O REF toca primeiro, os outros mostram a diferença para ele (tecla D), as medidas
dele viram o alvo e a rodada abre, porque uma rodada cega o esconderia. Um bundle
guarda o PCM da gravação: bundles e rodadas ficam nesta máquina; `freeze` e
`export` levam só o som. `dsl help reference --json` lista essas regras.

## Ouvir em texto

Um agente não ouve um WAV, mas lê texto com exatidão. O `ear` imprime o som do
jeito que o ouvido o divide: 20 faixas auditivas (ERB), de 80 Hz a 8 kHz, pelo
tempo a partir do início do som, cada célula um dígito de 6 em 6 dB abaixo da
célula mais forte (9 é a mais forte, `.` 54 dB abaixo), com ponderação A para os
graves aparecerem tão fracos quanto soam:

```bash
tare.tools.tune ear output/reviews/<bundle>               # contra a referência, se houver
tare.tools.tune ear output/reviews/<B> --vs output/reviews/<A> --brief   # o que uma edição mudou
tare.tools.tune ear gravacao.wav --vs none --lines        # só os fatos, cerca de 400 tokens
```

Primeiro vêm as linhas: o envelope (ataque, quando cai 20, 40 e 60 dB, ou que o
arquivo acaba antes), até quatro picos do espectro em Hz com quanto tempo cada um
soa (os harmônicos de uma voz aparecem uma vez só), a altura com faixa e glide, o
brilho no começo e no fim, o equilíbrio estéreo. Depois as grades: um zoom de
ataque a 2 ms por coluna para sons secos, o som inteiro num passo que caiba em 50
colunas, a emenda de um loop (os últimos 30 ms e depois os primeiros 30), uma
linha de `^` sob ataques posteriores e a altura a cada 5 colunas quando há voz.
Com outro som, uma grade DIFF e uma linha de resumo. O primeiro olhar completo
custa cerca de 2,5 mil tokens; o `--brief` (linhas e DIFF), cerca de mil. `--at
INÍCIO,DURAÇÃO` põe uma grade onde precisar, `--weight none` mostra a energia
crua, `--align peak` começa no momento mais forte para um início lento, e `--json`
devolve o mesmo como dados.

Toda saída termina com o que não mostra: fase, detalhe mais fino que uma coluna ou
uma faixa, aspereza e mascaramento. Uma célula do DIFF vale 6 dB e uma faixa,
então `=` não é "igual". O texto diz onde um som difere, nunca como ele soa; isso
se decide na [escuta](#pedir-uma-escuta). O rastreador de altura lê de 60 a
1600 Hz: um zumbido acima disso aparece como zumbido, e a sub-harmônica que o
rastreador acha é dita como tal, não como altura.

Se a leitura prevê o ouvinte é algo que se mede, não se supõe. Antes de servir a
página, grave o que o texto diz que o ouvinte vai responder; depois, compare com
as respostas:

```bash
python tools/curate.py predict clash previsoes.json --root output/rounds   # {"g1": {"pick": "B", "rate": {"A": 2, "B": 4}}}
python tools/curate.py agree clash --root output/rounds   # ou várias rodadas, somadas
```

O `predict` é recusado quando a rodada já tem resposta, e o `agree` recusa uma
previsão escrita ou alterada depois da primeira. O `agree` põe a leitura ao lado
do acaso, de uma regra fixa (o candidato mais perto da referência pelos números
do `ref`) e da consistência do próprio ouvinte (os mesmos sons escolhidos de novo
em outra rodada), e diz com que frequência um chute acertaria tanto: 5 acertos em
8 escolhas entre 3 saem do acaso 1 vez em 11, então poucas escolhas são uma pista,
não uma licença. Até 20 escolhas ou mais dizerem o contrário, quem decide é o
ouvinte.

Uma definição compartilhada pode afetar vários sons. A edição valida a compilação
de todos, mas renderiza e verifica somente o som selecionado; os demais exigem
suas próprias revisões quando o áudio deles importar.

As verificações opcionais ficam em um JSON separado, como
[este exemplo](../../examples/dsl-review.checks.json). Use `--checks ARQUIVO` para
limites de duração/pico, igualdade de sample rate/canais e capacidades obrigatórias
de exportação. São medições do PCM float retido, anteriores à conversão PCM16.
Não alteram áudio ou sementes, nem substituem o guard `edit.expect`.

Os resultados distinguem aprovação, reprovação, ausência de execução e ausência
de solicitação. Qualidade perceptual não é aprovada automaticamente: é necessário
ouvir. Uma revisão reprovada ainda pode servir para corrigir a fonte. Na CLI,
reprovação sai com código **5** e inclui a revisão em `details` quando há `--json`.
Conflitos continuam saindo com código **3**. Edições herdam as verificações do
bundle, a menos que recebam outro `--checks`.

A API pública oferece `review`, `describe` e `edit_file`. Para inicializar com
builders, use `from tare.tools.tune.dsl import builders as t`; `creature` também
está disponível no namespace principal da DSL. O JSON gerado permanece a fonte
editável, sem avaliação de Python no projeto e sem sincronização bidirecional.

O benefício desta etapa é reunir operações e evitar trabalho repetido. Respostas
com mais fatos também custam tokens; o custo total precisa incluir descoberta,
helpers, falhas e persistência antes de afirmar vantagem sobre Python.

Para reduzir o tráfego das iterações, use `--response compact` em `review`/`edit`.
A [análise das continuações](tokens-revisao-dsl.md) explica o perfil e a nova
medição com cinco edições sucessivas, aplicada também ao Python.

Na [medição inicial de três tarefas](../dsl-review-implementation.md), com respostas detalhadas, o custo total
da fachada ficou cerca de 10,2% abaixo do helper Python na mediana, incluindo a
preparação. A continuação com o helper já carregado custou cerca de 30,4% a mais,
porque a fachada devolve mais fatos e verificações. São scripts com tokenizadores
proxy, sem inferência ou cobrança; não demonstram economia geral em tarefas reais.
