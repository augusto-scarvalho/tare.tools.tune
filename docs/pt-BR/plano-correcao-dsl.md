# Plano de correção da eficiência da DSL

A execução deste plano está registrada no [relatório de implementação e medições](eficiencia-dsl.md). O texto abaixo preserva a proposta aprovada.

Proposta de 1º de novembro de 2026. [Plano completo em inglês, referência principal](../plans/2026-11-01-dsl-efficiency/PLAN.md) · [Medições atuais](../dsl-benchmarks.md).

O objetivo é reduzir o custo de operar a DSL e compará-la com Python oferecendo o mesmo serviço. O resultado anterior de 2,34× descreve o procedimento registrado; ele não demonstra um custo inevitável da linguagem. Este documento registra o plano, não uma implementação ou uma medição nova.

## Diagnóstico confirmado

Na tarefa de confirmação simples, a criação custou 113 tokens em Python e 127 na DSL. A diferença grande veio depois: inspeção/seleção custou 151 contra 707; edição/erro/reparo, incluindo preparação, custou 295 contra 711. O total foi 683 contra 1.791.

O roteiro reenviava receitas completas, consultava informações já disponíveis e impunha uma sequência genérica de filtro/erro/reparo a tarefas diferentes. Algumas ações pedidas eram preparadas antes da contagem; a tarefa de exportação FM não executava a recusa de Voice dentro do fluxo registrado. Python mantinha objetos em memória enquanto a DSL operava um arquivo com verificações adicionais. A comparação precisa distinguir essas responsabilidades.

## Sequência de execução

| Etapa | Correção | Critério de conclusão |
|---|---|---|
| P0: experimento | Executar literalmente o que cada tarefa pede; separar uso normal de falhas deliberadas; registrar trabalho preparatório; comparar memória com memória e transação persistida com transação persistida | Cada ação tem uma verificação independente; omitir uma ação necessária faz a aceitação falhar |
| P1: desperdício do fluxo | Reutilizar revisões observadas e capturas válidas, criar o refinamento uma vez, depois alterar apenas o campo; guardar identificadores em variáveis do contexto de ferramentas | Edições seguintes crescem com os campos alterados, sem repetir a receita ou atualizar guardas automaticamente |
| P2: respostas | Acrescentar um perfil explícito `--response compact`, mantendo a saída detalhada atual | Menos saída, com conflitos, avisos, revisões necessárias, impacto compartilhado e paginação utilizáveis |
| P3: abstração semântica | Medir receitas, variantes, motivos reutilizáveis, edição local/compartilhada, primitivas e composição; testar bancos de 8, 32 e 128 sons | PCM/eventos/arquivos e fonte corretos; resultados separados por serviço, início frio e continuação |
| P4: compatibilidade | Testes focados, uma suíte completa sobre o código final, Ruff, pacote isolado, exemplos e documentação | Comportamento preservado e relatório reproduzível com o resultado real |

O experimento terá dois contratos principais: autoria em memória e autoria persistida com revisão, lock, backup, validação e gravação atômica. Python poderá usar funções e compreensões; a DSL poderá usar os construtores, definições, transformações e variantes existentes. Helpers terão seu código e preparação contabilizados nas duas rotas. O uso direto por CLI também será verificado, sem fingir que ele possui uma sessão persistente gratuita.

As respostas compactas manterão o dado necessário para a operação seguinte. Uma inspeção não precisa repetir todos os identificadores de análise; uma edição ainda precisa verificar a revisão observada e a guarda aplicável. A proveniência completa permanece disponível no relatório detalhado e nos artefatos. Erros, avisos, perdas de capacidade e resultados truncados não serão escondidos.

Não será criado um serviço de sessões, registro de handles, nova linguagem textual ou cache persistente. Primeiro serão usados os helpers e o estado já possíveis pela API Python. Também não serão reduzidos hashes, desativadas verificações ou alterados os limites para favorecer uma contagem.

## Como medir

Preservar os relatórios anteriores e gerar um corpus/relatório versão 2 separado. Medir primeiro o procedimento corrigido com respostas atuais; depois acrescentar o perfil compacto; por último medir o uso de helpers reutilizáveis igualmente contabilizados. Isso mostra qual mudança economizou tokens.

Separar construção, pedidos, respostas, preparação, erros/reparos, chamadas, tempo e memória observada. Manter os dois tokenizadores existentes e identificar a contagem de contexto repetido como simulada. Para edições repetidas, publicar o custo após 1, 5 e 20 alterações, incluindo a preparação inicial. Preservar falhas e seus custos.

A meta inicial do perfil compacto é reduzir pelo menos 30% da mediana de tokens de resposta nos comandos predefinidos. Isso é uma hipótese a medir. Para recomendar economia total sobre Python, a mediana e o p90 precisam alcançar ou superar o baseline equivalente naquela família de tarefas. As metas originais de 70% do baseline e 50% de economia em bancos continuam sem comprovação.

Se Python continuar mais econômico, o relatório deve mostrar isso. O projeto poderá manter uma abordagem híbrida sem acrescentar sintaxe para tentar fabricar uma vitória.

## Segurança, testes e orçamento

Revisões de autoria, guardas do material expandido e revisões de captura continuam distintas. Conflitos exigem revisão explícita; nenhuma atualização automática de guarda seguida de nova tentativa. PCM, sementes, agrupamento de chamadas, origem das camadas, MIDI, replay e limites permanecem protegidos.

A execução nativa/Godot só precisa ser repetida se as mudanças afetarem seu contrato; navegador, se houver mudança no Studio. A suíte completa será rodada uma vez quando o código estiver congelado. Os 618 testes anteriores são referência histórica, não validação de código futuro.

Este plano e seus testes locais não iniciam inferência. A autorização anterior de 15 minutos foi consumida. Qualquer novo piloto precisa de outro orçamento explícito e do teste de gravação no sandbox aprovado antes de chamar o modelo. Não há retorno automático às 72 sessões do desenho original.
