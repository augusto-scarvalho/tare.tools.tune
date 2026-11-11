# DSL semântica de áudio — guia auxiliar

A documentação principal e a referência completa são o [guia em inglês](../dsl.md). Esta alternativa resume o fluxo de uso. A versão 1 é **experimental**: equivalência de áudio e testes de integração não comprovam economia de tokens nem qualidade perceptiva.

A DSL permite começar com intenção (`sfx`, `creature`, `say`, `music`), reutilizar definições parametrizadas, compor notas e descer até as oito famílias de primitivas existentes. O formato persistido é JSON. Os construtores Python imutáveis geram esse mesmo formato; arquivos de projeto não executam código Python.

## Primeiro uso

Para iterar sobre o áudio, use o [fluxo de revisão](revisao-dsl.md), com observação
preservada, descrição dos controles e edição testada antes da gravação.

Use o [banco de exemplo](../../examples/dsl-bank.tune.json):

```bash
tare.tools.tune dsl check examples/dsl-bank.tune.json --json
tare.tools.tune capture examples/dsl-bank.tune.json --name confirm -o output/confirm --json
tare.tools.tune studio examples/dsl-bank.tune.json --name confirm -o output/player
```

Abra a URL local impressa pelo player. Salvar o projeto ou um asset declarado inicia uma compilação em processo separado. Falhas mantêm o último áudio válido. A navegação de origem mostra o ponteiro JSON, o alvo de autoria e a cadeia de definições.

O documento usa `format:"tare.tools.tune.dsl"`, `version:1`, `context` opcional, `defs` opcional e um objeto `sounds` obrigatório. Uma gravação para comparar vai em `references` (`{"clash": "refs/clash.wav"}`, uma por som) ou `reference` (`{"file": ...}`, todos os sons): veja [Comparar com uma gravação](revisao-dsl.md#comparar-com-uma-gravação). Com vários sons, selecione `--name`; com um só, a seleção é automática. APIs Python, projetos antigos, Voice JSON e bundles anteriores continuam disponíveis.

## Vocabulário e reutilização

```bash
tare.tools.tune dsl catalog --domain sfx --name ui --json
tare.tools.tune dsl catalog --domain layer --name modal --json
```

O catálogo detalha eventos, estilos, controles, unidades e padrões. Consultas são paginadas; use `--limit`, o cursor `next` e `--fields` para pedir apenas o necessário. Campos desconhecidos geram erro.

Uma definição tem `body` e parâmetros em `params`; `{"param":"power"}` substitui um parâmetro. `{"use":"hit","with":{"power":0.8}}` cria uma instância independente. Tipos incluem números, inteiros, booleanos, strings, enumerações, tempos e expressões de notas/som/camada/speaker/instrumento. Referências cíclicas são recusadas.

IDs de autoria e nomes de definições não entram nas sementes. O `name` de uma track mantém seu papel nas sementes legadas; seu `id` opcional serve como rótulo neutro. Reordenar notas, chamadas ou camadas mantém as consequências de aleatoriedade já existentes.

## Notas, composição e primitivas

Veja os exemplos de [música](../../examples/dsl-music.tune.json), [primitivas](../../examples/dsl-primitives.tune.json) e [construtores Python](../../examples/dsl_builder.py).

`pattern`, `notes`, `chord` e `degrees` produzem notas antes da síntese. `seq`, `repeat` e `overlay` compõem essas notas. O span inclui pausas finais: repetir uma frase de três tempos começa a segunda ocorrência no terceiro tempo, mesmo que a última nota termine antes. `then` aplica, em ordem, `transpose`, `stretch`, `velocity`, `retrograde`, `quantize` ou `humanize` determinístico. Tracks com `clips` preservam chamadas separadas ao instrumento.

Um `chip_voice` é um canal de console de 8 bits, usado onde uma track ou um clip recebe `instrument`: `{"chip_voice":"pulse","duty":12.5,"fade":true}`. `chip_voice` é `pulse` ou `triangle` (o baixo); `duty` é 12.5, 25, 50 ou 75 (padrão 25); `fade` desce o volume em degraus até o silêncio em cada nota; `slide` chega à nota vindo dessa distância em semitons, um a cada 1/60 s; `vibrato` é `[Hz, semitons]`. O canal tem uma voz só: um acorde vira arpejo, com as notas alternando 60 vezes por segundo, e cada nota termina um quadro antes para que a repetição da mesma altura seja ouvida. O [exemplo de chiptune](../../examples/dsl-chiptune.tune.json) é um loop de quatro canais, e `dsl help chiptune --json` traz o ofício. O `review` de qualquer partitura também informa `bars_db` (o nível da mixagem por compasso, em dBFS, até 64 compassos), um `level_db` por track (abaixo da mais forte, antes do barramento) e `rubs` (os semitons que `Score.clashes()` encontra, contados por tipo, com os três primeiros), e `arrangement` (como as partes estão dispostas: notas por ataque, parcela de saltos, quantas tracks tocam e quão cheios estão cada 4 compassos). O review renderiza, e uma partitura orquestral longa passa dos limites dele: `dsl check ARQUIVO --name NOME --layout --json` devolve `arrangement` e `rubs` só a partir das notas, para uma partitura ou uma música de qualquer tamanho. `dsl help arrangement --json` diz o que observar; [como uma batalha orquestral é montada](arranjo-orquestral.md) é o estudo por trás disso.

`voice` agrupa camadas no mesmo bus. As primitivas são `syllable`, `modal`, `noise`, `scatter`, `chip`, `speech_frames`, `vocoded` e `spoken`. Seus tempos continuam em segundos numéricos, frequências em Hz e curvas em coordenadas normalizadas 0..1. Os campos mantêm o significado do motor existente.

`mix` coloca sons renderizados separadamente em um Score. Cada filho preserva seu processamento e sua proveniência. Isso tem significado acústico diferente de agrupar camadas numa Voice. `seq` e `repeat` de sons precisam de `span` explícito nas receitas, por exemplo `"250ms"`; o span agenda a próxima entrada e não corta caudas. Tempos genéricos aceitam `"20ms"`, `"0.5s"`, `"1/3b"`, `"2bar"`. O loop do Score é a duração total; o loop de Voice continua sendo o crossfade legado.

`audio` importa um arquivo local na mesma taxa de amostragem. Pan diferente de zero em áudio estéreo falha explicitamente. Assets fora da pasta do projeto exigem `--asset-root` nas operações compatíveis. Não há download de assets ou reamostragem implícita.

## Refinar e editar

```bash
tare.tools.tune dsl expand examples/dsl-bank.tune.json --name confirm --json
tare.tools.tune dsl query examples/dsl-bank.tune.json --target sound:confirm --json
```

`expand` retorna `materialized_id`. Um wrapper `edit` exige esse ID em `expect` para alterar campos ou adicionar/remover camadas. A mudança da receita invalida a guarda; selecione novamente antes de editar índices gerados. Timing e pitch musicais devem ser alterados nas notas. Mudar camadas sintetizadas invalida a exportação MIDI estrita dessas notas.

Uma edição do arquivo exige `format:"tare.tools.tune.patch"`, `version:1`, `expect` com a revisão de autoria e `ops`. Exemplo de operação: `{"op":"set","target":"sound:confirm","path":"/with/power","value":0.8}`. O alvo deve existir; para adicionar um argumento, escolha uma invocação que já tenha `with` ou substitua o objeto correspondente.

```bash
tare.tools.tune dsl patch projeto.tune.json --patch edit.json --dry-run --json
tare.tools.tune dsl patch projeto.tune.json --patch edit.json --json
```

A transação valida os sons, verifica a revisão sob lock, preserva os bytes anteriores em `.tune-backups` e substitui o arquivo atomicamente. O JSON passa à formatação canônica. Conflitos exigem nova consulta. Alvos `sound:`, `def:`, `/id:` e `/track:` nunca atravessam uma referência para editar uma definição compartilhada sem uma seleção explícita.

## Diagnóstico e exportação

`query`, `expand`, `patch`, `freeze` e `inspect` aceitam `--response compact` (ou `response="compact"` em Python). O padrão continua detalhado. O envelope `tune.compact/1` mantém revisões, guardas, avisos e continuação de resultados truncados. Veja o [relatório de correções e medições](eficiencia-dsl.md).

```bash
tare.tools.tune inspect examples/dsl-bank.tune.json --name confirm --view layers --top 3 --band 2000 6000 --fields id,label,power,target --no-pitch --json
tare.tools.tune dsl capabilities examples/dsl-music.tune.json --json
tare.tools.tune midi examples/dsl-music.tune.json -o output/theme.mid --json
```

As vistas compactas são `summary`, `layers`, `events` e `stages`; `full` retorna o relatório detalhado. `--node` permite escolher um estágio. Energia por banda soma os canais e não confunde cancelamento estéreo com silêncio. Potência de uma camada antes do bus não é atribuição aditiva exata após efeitos compartilhados ou não lineares. Solo/mute diagnóstico congela os ganhos capturados; editar e renderizar novamente pode normalizar de outra forma.

`dsl migrate` cria outro arquivo e exige PCM idêntico nos casos suportados. `dsl freeze` exporta Voice quando representável, bundle ou WAV. O WAV termina onde o som cai 60 dB abaixo dos seus 10 ms mais fortes (loops, caudas de reverb ou eco e `--keep-tail` ficam inteiros) e informa `silence_cut_s`; o bundle guarda o render inteiro. `--track` extrai uma Voice de Score/Cue com aviso sobre o processamento omitido. MIDI representa eventos e aproximações GM, não o timbre sintetizado. Native recebe Voice compatível ou PCM; não executa a DSL.

Há limites de bytes, profundidade, expansão, ocorrências, notas, camadas, duração e memória. Defaults e exceções estão no guia principal. Com `--json`, erros DSL usam `tune.error/1` no modo detalhado e `tune.compact/1` no compacto: saída 2 para entrada inválida, 3 para conflito/guarda obsoleta e 4 para asset/build/timeout. Erros genéricos dos caminhos legados mantêm seu comportamento anterior.

O [relatório versão 2](eficiencia-dsl.md) separa autoria em memória, transações persistidas e preparação/continuação. Os resultados são mistos e não comprovam economia geral. O [relatório anterior](../dsl-benchmarks.md) foi preservado como histórico de outro procedimento. Veja o [guia para agentes](dsl-agentes.md) e o [mapa de aceitação](../dsl-acceptance.md).

O piloto menor autorizado usou a quota existente do Codex, sem API paga e dentro de 15 minutos. Sete sessões não conseguiram gravar artefatos por restrições do sandbox; o resultado é inconclusivo. Todas as tentativas e tokens estão no [registro](../dsl-live-measurements.json). O runner agora testa a gravação no mesmo sandbox antes da inferência e encerra sem consumir quota se esse teste falhar. Não foram iniciadas novas sessões.

Projeções como `--fields fragment.with.power` aceitam até 32 caminhos de objetos, com quatro campos de profundidade. A referência/revisão permanece na resposta. `expand --view full` expõe os campos editáveis de Voice/Score/Cue; a navegação mostra o caminho original, o atual e os campos refinados.

Os limites também incluem 1024 caracteres por fala, velocidade de Speaker entre 0,25 e 4, um bilhão de operações de amostra estimadas e verificação do tamanho PCM pelo cabeçalho antes da leitura. A contagem de partes inclui Cues e capturas filhas repetidas. Cues grandes podem exceder o teto padrão de 1024 partes; os 32 presets foram calibrados a 16 kHz com limites explícitos de 8192 camadas e 2048 notas, mantendo os tetos de memória/trabalho. Consulte os [defaults completos](../dsl-reference.json).
