# Uso compacto da DSL por agentes

[Referência principal em inglês](../dsl-agent.md) · [Guia auxiliar](dsl.md) · [Medições corrigidas](eficiencia-dsl.md)

A DSL serve para autoria persistida, reutilização e edições com guarda. Compare preparação inicial, continuação e transações em arquivo separadamente. Os resultados corrigidos não estabelecem uma vantagem universal sobre Python.

Para renderizar, ouvir e editar, use o [fluxo de revisão](revisao-dsl.md):
`dsl review` retorna um bundle; `dsl describe` mostra seus controles; `dsl edit
--from-bundle` testa e grava um lote de alterações. Cada edição retorna o bundle
para a próxima. Os comandos abaixo continuam úteis para consultas e patches
isolados. `dsl help edit --json` traz as regras e os exemplos específicos.

Use `--response compact` também em `review`/`edit`; reserve respostas detalhadas
para decisões que precisam delas. Veja a [análise das continuações](tokens-revisao-dsl.md).
Em uma ferramenta Python persistente, vincule argumentos fixos com
`functools.partial`, mantendo `from_bundle` explícito em cada chamada. A análise
também conta a preparação e testa esse padrão.

- Descubra um domínio/nome e peça somente os campos necessários: `dsl catalog --domain sfx --name ui --fields name,example,knobs.ring --json`.
- Escreva o projeto inicial uma vez. Reutilize definições e gere variantes com os construtores ou `dsl variants`.
- Consulte um alvo: `dsl query bank.tune.json --target sound:confirm_strong --fields fragment.with.power --response compact --json`. A revisão permanece na resposta.
- Envie somente o patch necessário: `dsl patch ... --response compact --json`. Preserve a revisão usada na decisão; não contorne conflitos buscando outra revisão automaticamente.
- Expanda camadas para descobrir campos. Se o CompileResult observado já estiver em uma variável, obtenha a guarda por `materialized_id(compiled.plan)`. Encapsule a receita em `edit` uma vez; para alterar novamente o override `/lowpass`, use o caminho de autoria `/set/~1lowpass`, preservando os outros campos. A mudança da base exige revisão explícita da guarda.
- Para diagnosticar, use `inspect ... --view layers --top 3 --fields id,power --band 2000 6000 --no-pitch --response compact --json`. Analise um bundle salvo quando o áudio já estiver capturado.
- Peça `source` ou `parameters` apenas quando forem necessários. Use `--view stages` e `--node` para escolher um estágio. Siga os cursores quando houver truncamento.

As projeções aceitam até 32 caminhos de dicionário, com quatro campos de profundidade. Não aceitam índices, curingas ou expressões. `--pointer` seleciona um objeto mais profundo. IDs e guardas de segurança não são removidos para melhorar uma contagem.

Os [payloads anteriores](../dsl-measurements.json) foram preservados como histórico de outro procedimento. O [relatório versão 2](eficiencia-dsl.md) compara serviços equivalentes, perfis de resposta e a amortização da preparação em edições repetidas. Helpers são contabilizados nas duas rotas; um contexto persistente não equivale a uma CLI sem estado gratuita.

Economia de resposta não equivale automaticamente a economia da tarefa inteira. As medições incluem consultas, erros, reparos e patches; o relatório distingue contagem local, contexto simulado e uso real de modelo.
