# Tokens nas continuações da revisão

[Análise principal em inglês](../dsl-review-token-costs.md) · [Guia auxiliar](revisao-dsl.md)

O excesso vinha principalmente das respostas. A DSL fazia a operação solicitada,
mas devolvia uma revisão abrangente a cada edição: descrição, capacidades,
medições completas, verificações aprovadas e metadados do pedido. Na primeira
edição de primitivas, o diff literal também tratava a receita movida para o
wrapper `edit` como remoções e adições.

O número anterior de **30,4% a mais** tinha uma limitação: a “continuação” continha
uma edição, uma tentativa deliberada com revisão antiga e, no caso musical, MIDI.
Não era uma sequência de edições. Parte do excesso vinha da mensagem de erro mais
estruturada e dos argumentos reenviados nessa verificação de guarda.

Foi implementado `--response compact` em `dsl review` e `dsl edit`, ou
`response="compact"` na API. O formato detalhado continua sendo o padrão.

```bash
tare.tools.tune dsl review examples/dsl-bank.tune.json --name confirm -o output/reviews --response compact --json
tare.tools.tune dsl edit examples/dsl-bank.tune.json --from-bundle BUNDLE -o output/reviews --set /with/power 0.65 --response compact --json
```

O resumo mantém o bundle, áudio, duração, sample rate, canais, pico/RMS, cobertura
das verificações, mudanças medidas e sons afetados (os nomes saem quando o único
afetado é o próprio som revisado; impacto maior os mantém). Verificações que falham ou
não são executadas preservam valores e motivos completos. As aprovadas aparecem
por nome, sem repetir todos os valores. O diff autoral passa a ser uma contagem
estrutural; os detalhes continuam disponíveis ao revisar o mesmo bundle em modo
detalhado, sem regeneração.

As verificações e guardas continuam executando integralmente antes da gravação.
Não foram removidos renderizações, backups, locks ou substituição atômica.

Na nova medição, foram executadas **cinco edições sucessivas por tarefa**, com
alternância de valores e comparação de cada áudio intermediário. A compactação
foi aplicada também ao helper Python:

| Cinco edições | DSL detalhada | DSL compacta |
|---|---:|---:|
| Refinamento de voz | 3.647 | 1.382 |
| Transposição e MIDI | 5.457 | 2.499 |
| Entrada de banco com 128 sons | 3.542 | 1.480 |

A redução mediana do tráfego de continuação da própria DSL foi de **58,2%**.
Incluindo a tentativa inválida, o excesso frente ao Python também compacto caiu
de **21,3% para 7,0%** nesse novo protocolo. Considerando somente edições úteis e
MIDI, a DSL compacta ficou aproximadamente **4,7% acima** do Python compacto.
O protocolo anterior de uma edição não deve ser confundido com este de cinco.

São scripts locais com tokenizadores proxy, sem novas chamadas a modelos ou API
paga. Não medem raciocínio, histórico retransmitido ou cobrança. Passaram
**173 testes da DSL**, além das verificações de áudio, PCM16, MIDI, fonte, backups
e recusa de revisão antiga nos 27 fluxos executados.

Para continuar economizando: descubra controles uma vez, agrupe alterações já
conhecidas, use respostas compactas e peça detalhes somente quando necessários.
Em ferramentas Python persistentes, guarde os caminhos de bundle em variáveis e
vincule os argumentos fixos uma vez. Conflitos continuam exigindo revisão explícita.

Essa vinculação também foi medida usando o `functools.partial` padrão:

```python
from functools import partial
from tare.tools.tune.dsl import edit_file

apply = partial(edit_file, path, output=folder, response="compact")
updated = apply(from_bundle=observed["bundle"], refine={"/lowpass": 2400})
```

Na terceira rodada, incluindo o custo inicial dessa vinculação, as continuações
ficaram próximas do Python: **1,2% acima** na mediana incluindo a tentativa
inválida, e **0,3% acima** contando só edições úteis/MIDI. Isso indica paridade
aproximada nesse replay, sem comprovar vantagem geral; hashes e caminhos
temporários também causam pequenas oscilações. A revisão observada continua sendo
passada explicitamente, sem refresh ou retry automático.
