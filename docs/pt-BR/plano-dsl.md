# Plano da DSL semântica para o Tune

**Registro histórico da proposta.** A implementação e os testes posteriores estão no [mapa de aceitação](../dsl-acceptance.md) e no [relatório de medições](../dsl-benchmarks.md). A DSL segue experimental: Python foi mais econômico nos fluxos completos e o piloto real foi inconclusivo por bloqueio de gravação no sandbox. O texto abaixo preserva o contexto do planejamento.

31 de outubro de 2026. Este documento resume uma proposta de implementação; a DSL descrita ainda não está implementada. O contrato completo e a sequência de trabalho estão no [plano principal em inglês](../plans/2026-10-31-dsl/PLAN.md), preparado em uma sessão nova de Astra com esforço xhigh. O plano principal prevalece em caso de dúvida sobre sintaxe ou comportamento.

## A decisão

A proposta é uma **DSL declarativa e versionada em JSON**, com operações compactas do domínio de áudio, definições reutilizáveis e parâmetros. Um construtor Python fino produzirá exatamente os mesmos dados. A notação atual de padrões musicais continuará sendo usada para notas; não haverá uma nova linguagem textual geral nesta primeira versão.

O objetivo é economizar tokens no trabalho completo: descobrir opções, criar, ouvir, diagnosticar, corrigir e exportar. Por isso, catálogo compacto, consultas limitadas, erros úteis e alterações pequenas fazem parte da primeira entrega utilizável. Reduzir apenas o tamanho do arquivo não basta.

O Python atual permanece disponível para programação confiável, instrumentos arbitrários e trabalho com arrays. Arquivos de projeto continuarão sem executar Python, importar módulos ou avaliar expressões livres. A DSL compilará para os objetos e renderizadores existentes, sem outro motor de áudio.

## Como será a autoria

Um banco simples poderá declarar uma receita uma vez e criar variantes por parâmetros:

```json
{
  "format":"tare.tools.tune.dsl","version":1,
  "defs":{
    "confirm":{
      "params":{"power":{"type":"number","default":0.5,"min":0,"max":1}},
      "body":{"sfx":"ui","style":"crystal","event":"confirm","species":7,
              "power":{"param":"power"},"dry":true}
    }
  },
  "sounds":{
    "confirm":{"use":"confirm"},
    "confirm_strong":{"use":"confirm","with":{"power":0.85}}
  }
}
```

O vocabulário abrangerá Sfx, Creature, fala/emotes, Cue, Score, áudio importado, FM e todas as famílias atuais de primitivas. Definições também poderão representar motivos musicais, descritores de Speaker e instrumentos declarativos limitados. Estes últimos preencherão primitivas a partir de `Note`, com parâmetros e variação determinística, sem código arbitrário dentro do JSON.

Composição terá fronteiras explícitas:

- `voice` reúne primitivas em um único processamento de Voice.
- `mix`, `seq` e `repeat` de sons compõem saídas já processadas através do Score.
- Operações sobre notas acontecem antes da expansão dos instrumentos: transposição, escala de tempo, velocidade, retrogradação, quantização e humanização com seed explícito.
- FM, áudio importado e efeitos do Score continuam sendo recursos de PCM/Python. Não passam a ser campos do Voice nativo.

Essas fronteiras importam porque o motor normaliza Voice, trilhas e mix em etapas diferentes. Juntar camadas dentro de um Voice não produz necessariamente o mesmo resultado que misturar dois Voices prontos. Ganhos relativos não serão apresentados como controle garantido do pico final. Ganhos e coeficientes primitivos assinados continuarão disponíveis para inversão de polaridade e cancelamento.

## Edição pequena e refinamento de alto para baixo nível

Uma consulta devolverá o alvo de autoria e a revisão esperada. Para mudar só a força de uma variante, o agente enviará um patch pequeno:

```json
{
  "format":"tare.tools.tune.patch","version":1,
  "expect":"<revisao-da-consulta>",
  "ops":[{"op":"set","target":"sound:confirm_strong","path":"/with/power","value":0.65}]
}
```

O comando validará o documento, verificará conflito e gravará atomicamente. Uma edição inválida não altera o arquivo. Se a fonte válida falhar durante a renderização, o player preservará o último áudio válido, como já faz hoje. Alterar uma definição afetará seus usos de forma explícita; alterar um parâmetro da invocação afetará só aquela variante.

Para ajustar uma camada gerada, o agente pedirá uma expansão limitada, receberá caminhos reais como `/modal/0/hardness` e um hash do material expandido. Um operador `edit` conservará a receita e registrará apenas a substituição, protegida por esse hash. Se a receita mudar, o override falhará até que o alvo seja escolhido novamente. O plano não inventa papéis como “ataque” ou “corpo” para receitas que ainda não fornecem esses metadados.

IDs de autoria servem para editar; IDs de diagnóstico servem para localizar evidência. Nenhum deles passa a gerar aleatoriedade. Permanecem os seeds atuais e a influência da ordem das camadas/notas. O `name` da trilha do Score continua relevante para o seed; um `id` separado será neutro para o áudio. Espécies nomeadas, como `"excalibur"`, serão preservadas onde as receitas atuais as suportam, sem convertê-las silenciosamente para números.

## Tempo, pausas e reprodução

O plano diferencia duração de agendamento (`span`), duração sustentada da nota, duração seca, cauda renderizada e período do loop. Uma sequência avança pelo `span`; a cauda pode sobrepor o próximo som. Receitas sem duração de agendamento dedutível precisarão de um `span` explícito quando usadas em sequências/repetições.

Pausas finais de padrões serão preservadas. Em compasso de três tempos, `C4 - . . . .`, com duas posições por tempo, ocupa três tempos mesmo que a nota termine no primeiro. Repetir esse motivo deve iniciar a segunda ocorrência no tempo três, sem depender da reverberação.

Beats continuam sendo semínimas; o metro é um número inteiro de tempos por compasso. O loop do Score mantém o período exato com dobra das caudas. O `loop` bruto de Voice mantém seu significado atual de duração do crossfade. O plano documenta essa diferença em vez de unificar campos que produzem comportamentos distintos.

## O que foi confirmado nesta análise

A leitura do código mostrou que o JSON atual materializa uma fonte por som, sem composição geral nem definições compartilhadas. Também mostrou que `Track.play()` expande imediatamente as notas e que sua aleatoriedade depende de ordem e quantidade de camadas.

Um probe curto confirmou um ponto importante para a implementação: `Score.add(Voice)` renderiza antes de `capture`, deixando o som colocado sem subcaptura detalhada. O plano resolve isso com capturas dos filhos ligadas aos placements, preservando a conversão para float64, os ganhos e os fatores congelados do replay. Não propõe outro mixer. Essa integração precisa passar por testes de igualdade e proveniência antes de liberar a composição geral.

Os 85 fingerprints de código/documentação fornecidos no início continuavam iguais. Não foram executados novamente a suíte completa, o job nativo, testes de escuta ou benchmark de tokens. Os resultados anteriores de testes continuam sendo evidência histórica, e a comparação de 29.960 contra 426 fornecida no contexto continua sendo uma comparação de **bytes**, não de tokens.

## Sequência de implementação

| Marco | Entrega e principal portão |
|---|---|
| M0 | Fixar contratos, corpus de comparação e baselines legados independentes. Preservar o workspace sem Git com snapshot externo antes de implementar. |
| M1 | Loader estrito, receitas, parâmetros, referências, catálogo/consulta compactos, patch simples e integração com captura/player. Primeiro fluxo completo utilizável. |
| M2 | Todas as primitivas, unidades, padrões com spans, composição de notas, transforms e Score. Verificar compassos, pausas, seeds e limites de expansão. |
| M3 | Composição de sons, subcapturas, proveniência e replay com esquema 2. Preservar PCM, conversões, fatores e leitura de bundles antigos. |
| M4 | Overrides protegidos, patches estruturais, renomeação e consultas de impacto. Rejeitar guards obsoletos e mutações de tempo após expansão. |
| M5 | Construtores Python, parâmetros tipados de composição, instrumentos declarativos e geração limitada de variantes. Garantir execução uma vez por nota. |
| M6 | Completar MIDI, sprites, watcher, navegação da fonte, migração e exportação portátil. Executar os checks nativos aplicáveis sem tratar skips como aprovação. |
| M7 | Benchmark real de tokens/tarefas, compatibilidade final e estabilização da versão 1. Publicar resultados e limitações. |

A primeira entrega já permitirá criar uma receita parametrizada, renderizá-la, receber um diagnóstico curto, alterar uma variante com patch e comparar revisões. Os marcos seguintes continuam necessários para cumprir o plano completo; essa primeira fatia não será anunciada como se composição e edição musical já estivessem prontas.

## Como comprovar a economia

O benchmark comparará as rotas atuais de Python e JSON com a nova DSL, usando tarefas equivalentes e critérios de sucesso independentes. Contará prompts, ferramentas, catálogos, diagnósticos, erros, correções e contexto repetido com o tokenizer/modelo identificado. Bytes, tokens, tempo e custo faturado serão métricas separadas.

Já em M1 haverá uma checagem local barata com tokenizer para construção, edição pequena e diagnóstico/correção; M2 ampliará esse corpus para música e primitivas. Isso permite corrigir verbosidade antes de implementar todo o roadmap. A qualificação completa com agentes em sessões novas fica em M7, com orçamento previamente definido; nenhum benchmark pago foi executado nesta análise.

Os objetivos propostos são uma mediana de tokens por tarefa correta de até 70% da melhor rota atual, redução de pelo menos 50% na edição localizada de bancos maiores e ausência de regressão relevante de sucesso. Ainda não são resultados. Se não forem atingidos, a linguagem permanece experimental e o relatório identifica a causa. Uma gramática textual poderá ser avaliada depois, sobre o mesmo modelo, caso a pontuação JSON ainda seja um custo importante.

## Limites e compatibilidade

Arquivos antigos continuam no loader legado. Migração será explícita, para outro arquivo, com relatório de equivalência; não descartará campos ou “corrigirá” sem aviso comportamentos antigos. O formato da DSL, o esquema de captura, a versão do Voice e a versão de comportamento do renderer são contratos distintos. Exportar Voice nativo exigirá uma capacidade realmente suportada; misturas, FM e efeitos do Score poderão exigir PCM.

Validação cobrirá campos desconhecidos, ciclos, unidades, assets, valores não finitos, cardinalidade e custo de expansão. Limites de duração, camadas, arrays e memória acumulada valerão para toda a composição. O plano distingue estimativa de memória de uma garantia rígida de RSS que ainda não existe.

Ficam adiados: parser textual geral, cache persistente, módulos remotos, editor de fonte no navegador, mapas de tempo, transformação arbitrária de PCM, nova normalização e execução nativa da DSL. O fluxo solicitado de semântica até primitivas, composição, refinamento incremental e diagnóstico compacto permanece no roadmap. Qualidade perceptiva continuará exigindo escuta; validade estrutural e determinismo não a comprovam.
