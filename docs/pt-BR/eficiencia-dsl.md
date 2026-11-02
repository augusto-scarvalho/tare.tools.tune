# Correção da eficiência da DSL

[Relatório principal em inglês](../dsl-efficiency.md) · [Plano aprovado](plano-correcao-dsl.md) · [Guia para agentes](dsl-agentes.md).

O benchmark foi corrigido para executar o que cada tarefa pede e comparar responsabilidades equivalentes. Criação simples não recebe mais um filtro, erro e reparo artificiais. Os testes de recuperação ficam separados, verificam o estado anterior e aplicam uma correção diferente. A recusa de exportar FM como Voice é realmente executada.

São 17 casos pareados: nove de autoria em memória e oito de transações em arquivo. O baseline Python persistido também usa revisão, lock, backup, validação do banco e substituição atômica. Os builders existentes da DSL são usados nos exemplos compostos; Python pode usar funções e compreensões. Imports e helpers são contabilizados nas duas rotas.

As receitas refinadas são encapsuladas uma vez. As próximas edições mudam apenas os campos necessários. Revisões e guardas podem ficar em variáveis do contexto de ferramentas, sem criar um serviço de sessões. Conflitos continuam exigindo revisão explícita; não há atualização automática de guarda seguida de nova tentativa.

## Perfil compacto

```bash
tare.tools.tune dsl query examples/dsl-bank.tune.json --target sound:confirm_strong --fields fragment.with.power --response compact --json
tare.tools.tune inspect examples/dsl-bank.tune.json --name confirm --view layers --top 3 --fields id,power --no-pitch --response compact --json
```

`query`, `expand`, `patch`, `freeze` e `inspect` aceitam `--response compact`. A API Python aceita `response="compact"`. O padrão continua detalhado. As respostas compactas usam `tune.compact/1`, preservando as revisões necessárias, guardas completas, avisos, impacto compartilhado e continuação de resultados truncados. Um patch omite os nomes afetados quando eles só repetem os sons alterados; a contagem permanece. Nenhum hash foi encurtado. `--view full` exige a resposta detalhada.

O exportador compacto preserva a revisão da captura e o hash do PCM de origem, além de dimensões e avisos. Um WAV isolado não contém toda a proveniência; use bundle quando precisar do grafo completo. O perfil não cria um novo arquivo auxiliar de proveniência.

## Medições

[Payloads finais](../dsl-measurements-v2.json) · [Comparação por etapa](../dsl-comparison-v2.json) · [Respostas isoladas](../dsl-response-measurements-v2.json)

Razões DSL/Python com `o200k_base`: abaixo de 1 favorece a DSL naquele escopo. Total inclui a preparação; continuação considera somente tarefas com edições.

| Serviço | Variante | Mediana total | Mediana continuação | p90 total: Python / DSL |
|---|---|---:|---:|---:|
| memory | control | 1.174x | 1.223x | 1511 / 1606 |
| persisted | control | 0.968x | 1.510x | 2388 / 3659 |
| memory | narrow | 1.174x | 1.223x | 1511 / 1606 |
| persisted | narrow | 0.881x | 1.168x | 2388 / 2643 |
| memory | compact | 1.174x | 1.223x | 1511 / 1606 |
| persisted | compact | 0.872x | 1.147x | 2388 / 2590 |

O p90 de continuação também está no registro. Os casos de muitas edições permanecem no p90 persistido.

| Alterações | Python total | DSL total | Python por alteração, amortizado | DSL por alteração, amortizado |
|---|---:|---:|---:|---:|
| 1 | 664 | 541 | 664.0 | 541.0 |
| 5 | 1026 | 965 | 205.2 | 193.0 |
| 20 | 2388 | 2590 | 119.4 | 129.5 |

Medição apenas da resposta, sobre os mesmos resultados:

| Comando | Tokens detalhados | Tokens compactos | Redução |
|---|---:|---:|---:|
| expand | 206 | 149 | 27.7% |
| freeze | 136 | 145 | -6.6% |
| inspect | 246 | 152 | 38.2% |
| patch | 129 | 72 | 44.2% |
| query | 107 | 99 | 7.5% |

A mediana de redução das cinco respostas foi **27.7%**, abaixo da meta de 30%. No WAV, a resposta compacta inclui dimensões e preserva identidades, ficando um pouco maior. Ela também pode ser maior que uma projeção detalhada já muito enxuta.

Escolha a interface pelo serviço e pela continuação medidos. As metas originais de 70%/50% e uma economia geral continuam sem comprovação; medianas favoráveis não substituem o p90 e o custo inicial.

Os três experimentos finais usam os mesmos casos, fonte e verificações: controle detalhado, fluxo com alterações pequenas e perfil compacto. O custo inicial inclui helpers e criação/observação. A continuação inclui as inspeções, edições, falhas e exportação pedidas após essa preparação. As séries de 1, 5 e 20 alterações mostram a amortização do custo inicial.

Contagens são proxies de conteúdo com dois tokenizadores reais; contexto repetido é simulado. Não houve nova sessão de modelo ou API paga. Os 2,34× antigos descrevem outro procedimento e não formam uma comparação direta de antes/depois. Economia de resposta e economia da tarefa inteira continuam sendo resultados separados.

## Validação

- Suíte completa: **636 aprovados e 49 skips no Windows**, em 14:16. Os skips são de disponibilidade; não representam uma nova execução nativa/Godot.
- Os **17 pares passaram nas três variantes finais**: 102 execuções de rotas, com verificações de ações, PCM inicial/final, WAV, MIDI e preservação da fonte. Erros e conflitos esperados foram contabilizados.
- Ruff, referência gerada, pacote com **21 módulos da DSL** e CLI isolada passaram. O código do pacote é comparado byte a byte com a fonte. Não houve mudança no DSP, no motor nativo ou na interface do Studio que justificasse repetir esses jobs.
- Não foram iniciadas sessões de inferência ou chamadas de API paga.

O resultado é misto: a mediana total das transações favoreceu a DSL ao incluir a preparação dos helpers; autoria em memória e a mediana de continuação ainda favoreceram Python. Com 20 alterações, foram **2.388 tokens em Python contra 2.590 na DSL**. A interface melhorou, mas não há comprovação de economia geral nem motivo para retirar o rótulo experimental.

Os relatórios antigos foram preservados. Os payloads, falhas esperadas, verificações de PCM/WAV/MIDI, identidades e caminhos dos artefatos estão nos relatórios. A DSL permanece experimental; uma recomendação de economia vale somente para o serviço e as condições realmente medidos.

## Complemento: nomes afetados nas confirmações de patch

A confirmação compacta de um patch agora omite os nomes em `affected` quando eles só repetem os sons alterados; `affected_total` continua, e uma mudança de definição ou um impacto truncado ainda lista os nomes. Reexecutando a variante persistida compacta no mesmo corpus ([payloads](../dsl-measurements-v2-affected.json)):

| Persistido, compacto | Antes | Depois |
|---|---:|---:|
| Mediana total DSL/Python | 0,872x | 0,859x |
| Mediana de continuação DSL/Python | 1,147x | 1,092x |
| p90 total da DSL (Python 2.388) | 2.590 | 2.450 |
| 20 escritas, tokens da DSL por escrita (Python 119,4) | 129,5 | 122,5 |

Os casos em memória não usam confirmação de patch e não mudam. O Python ainda vence sessões longas; quase toda a diferença restante por escrita é o rótulo `schema` de cada confirmação compacta. A razão da fachada de review em cinco edições foi de 1,012x para 1,009x, dentro do ruído entre execuções (IDs de bundle e caminhos temporários), então nenhum ganho é alegado ali.
