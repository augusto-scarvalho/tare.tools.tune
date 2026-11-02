# Plano: um "ouvido" para o modelo (`TUNE ear`)

2 de novembro de 2026. Planejamento, somente leitura, sem inferência paga. Pergunta do usuário: "e se você também
pudesse ver o som, num formato otimizado, como o pxl faz?" O assistente não recebe áudio (o `Read` mostra imagens e lê
texto, PDF e notebooks); o pxl dá um "olho" por formatos feitos para o modelo (`shot`, `ascii`, `describe`, `blind`).
Hoje a sessão principal testou dois protótipos no scratchpad (`look.py` → espectrograma PNG; `ascii_ear.py` → cocleograma
em texto) sobre um par `clash` (gravação simulada × nosso render). Este plano critica o protótipo, desenha o formato,
mede o custo em tokens, integra com `references`, candidatos, curadoria, skill e help, e propõe a calibração: a
leitura do modelo prevê o ouvido do usuário? Formato segue `docs/plans/2026-11-02-reference-study/PLAN.md`.

Restrições que valem para tudo abaixo: núcleo determinístico, CPU, numpy/scipy, sem dependência nova obrigatória;
GPU só via `gpu run` no nó `aaaaa`; gravações de jogo ficam nesta máquina e na rede local (nunca em repo, testes ou
bundles entregues); testes com sinais sintéticos ou renders do próprio tune, `pytest --basetemp output/pt`; nunca
navegador headless na página de curadoria; nenhuma saída afirma que algo "soa bem" ou "soa igual".

**Decisões do usuário (2 de novembro):** as recomendações da §10, com o exemplo do `TUNE music` mantido na skill (cortadas a linha do studio, a da tabela "tactics RPG", a dica do `--response compact`; Examples fundidas). Feito: fases 0–3 (`TUNE ear`, zooms, emenda de loop, `onsets`, `dsl help ear`, skill e docs). No `BACKLOG.md`: fases 4–6. Mudanças na implementação: o ataque de `measures` olha só os primeiros 250 ms (numa fanfarra, o pico era o acorde final); `common_end_db` fica abaixo de −10 dB (num som contínuo, o "piso" era o próprio som e a medida quebrava); os picos só viram "harmônicos" quando há energia na própria fundamental (um zumbido de 3 kHz, acima dos 1600 Hz do rastreador, virava uma sub-harmônica de 1.499 Hz); um limite de −20/−40/−60 dB que só cai no fim do arquivo é dito "não atingido".

## 0. Fatos conferidos

Protótipo (`ascii_ear.py`, `ear.txt`, `look.py`, `look_clash.png` no scratchpad), lidos e remedidos:

- **`ear.txt`: 2.085 tokens** (`o200k_base`, 6.504 caracteres), seis grades: ataque REF 362, OURS 359, DIFF 359; som
  inteiro REF 423, OURS 336, DIFF 246. "~350 por grade" confere (246–423).
- **20 bandas ERB de 80 Hz a 8 kHz, dígitos 1–9 em passos de 6 dB sob a célula mais forte do próprio sinal** (9 = os
  6 dB de cima, `.` = mais de 54 dB abaixo), colunas a partir do onset de cada sinal (primeira janela de 10 ms a −35 dB
  do pico: a mesma regra de `analysis.measures`), réguas a cada 5 colunas **sem números**, dois zooms (0–60 ms a 2 ms;
  0–750 ms a 15 ms), DIFF `+`/`-`/`=`/vazio. Confere.
- **Como é calculado:** cada coluna é **uma FFT do próprio trecho da coluna** (Hann, zero-padding a 4096), somas
  retangulares por banda, sem ponderação de loudness. Consequência que a sessão não viu: no zoom de ataque a janela tem
  2 ms (32 amostras a 16 kHz, forçadas a 64 = 4 ms), logo a resolução em frequência é 250–500 Hz, e as seis linhas
  abaixo de ~700 Hz (bandas de 60–130 Hz de largura) mostram **vazamento espectral, não energia**. O zero-padding não
  cria resolução. As leituras "graves da referência somem aos 40 ms" e "nosso 400 Hz–1,2 kHz segue até 60 ms" eram
  parcialmente artefato nas linhas baixas; com janela por banda (§3.2) a referência some abaixo de 830 Hz aos ~45 ms e
  o nosso mantém 530 Hz–1 kHz até 60 ms: a conclusão se sustenta, os números mudam.
- **PNG (`look_clash.png`): 720×416 px ≈ 400 tokens de imagem** (regra w×h/750). O `shot` do pxl mede ~550 de imagem
  por chamada (`docs/agents.md`, "What it costs") e amplia até 1.568 px (`--scale`, `src/node/shot.ts`) para o modelo
  ler ao natural; `agents.md` diz que `ascii` é "mais barato que uma imagem" para pixels exatos.
- **Tempo de cálculo:** o protótipo inteiro (6 grades) leva 0,24 s; uma grade com janela por banda (§3.2), em laço
  Python, 0,08 s; a linha de picos ingênua que testei, 1,3 s (uma STFT de 65.536 pontos por pico; vetorizada fica em
  ~0,05 s). Alvo do comando inteiro: < 0,5 s para sons ≤ 3 s.
- **O que existe no código (árvore de trabalho, não commitado):** `analysis.measures/against/common_end_db/BASIS`
  (`analysis.py:135-272`), `references` no topo do documento, bloco `facts.reference` e `ref` compacto
  (`review_data.py:99-106`, `responses.py:113-123`), `TOLERANCES`/`reference_checks` com `absent`
  (`review_data.py:14, 109-132, 179-182`), `CURATE compare --reference` (`curate.py:415-466`), `dsl help reference`
  (`workflow_cli.py:76-103`). `curate.answers_json` devolve pick, notas 1–5, `abx` com `correct`, marcas e notas, com
  o caminho do bundle por rótulo (`curate.py:374-401`). `inspection.py` dá níveis, quadros de F0 e energia por banda;
  `plot.spectrogram` usa matplotlib (instalado); `analysis.yin/clean_f0/envelope_db/segments` existem.
  `designer` com CLAP exige `[clap]` (não instalado). `scipy.signal.gammatone` existe na scipy 1.18 do `.venv`.
- **SKILL.md: 10.998 caracteres** (10.999 bytes: o "à" de "forja"); `tests/test_skill.py` cobra `len < 11000` e que
  todo `TUNE …`/`CURATE …` citado exista com suas flags e todo tópico de `dsl help` esteja em `HELP`. Sobra 1 caractere.
- **Custo da review compacta:** a sessão principal mediu ~200 tokens sem referência e ~259 com `ref`; não remedi.
- **`dsl describe` já existe** (controles de um bundle: campos, caminhos, faixas). O nome `describe` está tomado.

Correções ao que a sessão principal escreveu:

| Afirmação | Correção |
|---|---|
| "`pxl shot`: ampliação nearest-neighbour, réguas, …" | As réguas x/y são do `pxl ascii` (`render.ts:44`); `shot` amplia (`--scale`, padrão até 1.568 px), recorta (`--at`), `--grey`, `--vs --diff`, sem réguas |
| "a referência tem um ring dominante perto de 3,7 kHz que dura os 750 ms inteiros" | O pico de 3.730 Hz cai 20 dB aos 420 ms e está a −45 dB aos 750 ms: "dura os 750 ms" só a um nível que uma mixagem de jogo enterra. A linha `peaks` (§3.4) diz isso com número |
| Leituras do zoom de ataque abaixo de ~700 Hz | Vazamento (janela de 2–4 ms); ver acima |
| "Os scripts são protótipos: STFT por coluna…" (implícito: a estrutura serve) | A estrutura (bandas × tempo, dígitos, DIFF, dois zooms) serve e foi o que funcionou; a análise por trás muda (§3.2) |
| "`ascii_ear.py` → cocleograma" | É um espectrograma por bandas ERB; um cocleograma tem resolução temporal por banda. A versão de §3.2 chega perto disso sem filtro IIR |

## 1. O que o pxl faz pelo olho, e o que transfere para o ouvido

Lido em `README.md` "## Commands", `SKILL.md`, `docs/agents.md` ("How the agent works", "What it costs"),
`src/core/render.ts:44` (`ascii`), `src/node/shot.ts`, `src/node/cli.ts:750-800` (`blind`).

| pxl | O que faz para o modelo | No tune |
|---|---|---|
| `shot` | um asset como imagem: ampliado ao tamanho que o modelo vê a 1x (1.568 px), quadros lado a lado, `--at` recorta e amplia, `--grey` só valores, `--vs HEAD --diff` o anterior em cima e os pixels mudados em vermelho; o texto diz o que mudou desde o último shot | `ear`: grades REF em cima, OURS embaixo, DIFF; `--at` um trecho ampliado; `--vs` outro bundle = o "HEAD" |
| `ascii` | pixels exatos como chaves de paleta com réguas numeradas | as grades de dígitos com réguas em ms e rótulos em Hz |
| `describe --brief` | a cena em texto, ~2k tokens; responde perguntas de layout "melhor que olhar" | as linhas sob a grade (`peaks`, `dB`, `f0`, `stereo`) e `--lines` (§5) |
| `blind` | um leitor que não conhece os rótulos checa o que os rótulos afirmam | já existe: rodada cega/ABX em `curate`; a calibração (§6) é o `blind` do ouvido |
| `check` com linha de cobertura | "não checado" ≠ "passou" | a linha fixa "Not shown: …" em toda saída |
| "um olhar por chamada, todos os fixes num turno" | custo: uma `shot` = 70–200 tokens de texto + ~550 de imagem | `ear` completo ~2,4k; `--brief` ~1k; a skill pede brief depois do primeiro olhar |

O que **não** transfere: o pixel exato (uma célula de 6 dB × 1,5 ERB × 15 ms é o "pixel"; abaixo disso nada é
mostrado); o `--diff` em vermelho sobre imagem (o DIFF é texto); `compare` por silhueta (o análogo é a linha-resumo
do DIFF: contagens e as bandas com a maior extensão de `+`/`-`); `--fix`.

## 2. Crítica do protótipo

| # | Gravidade | Problema | Correção |
|---|---|---|---|
| 1 | alta | Janela = coluna: no zoom de 2 ms as linhas sob ~700 Hz são vazamento | Janela por banda ≈ 2/ERB(fc), de 3 a 40 ms, centrada na coluna (§3.2) |
| 2 | alta | Nada diz o que a grade não mostra; o leitor pode concluir "soa parecido" | Linha fixa "Not shown: phase, detail finer than a column or a band, roughness, masking; cells are A-weighted band energy, not loudness"; regra na skill |
| 3 | média | Graves com o mesmo peso dos agudos: 104 Hz a "9" lê como proeminente; o ouvido o ouve ~19 dB mais fraco | Ponderação A por banda (uma fórmula; `--weight none` desliga). O DIFF não muda |
| 4 | média | Réguas sem números: "até ~450 ms" é contagem de colunas | Régua `ms` com o valor a cada 5 colunas; linha `dB` por coluna (a curva de loudness) |
| 5 | média | O ring em 3,7 kHz foi lido pela linha da banda (1,5 ERB de largura); o Hz e a duração são estimativas | Linha `peaks`: os 4 picos do espectro de longo prazo, Hz, dB re o mais forte, tempo até −20 dB |
| 6 | média | Zooms fixos (60 ms, 750 ms) | Automáticos a partir de `measures` (ataque só quando `attack_ms` < 30; inteiro até o fim comum a −40 dB; loop: período + emenda) e `--at` |
| 7 | média | DIFF sem resumo: 1.000 células para contar à mão | Linha-resumo como o `compare` do pxl: "ours louder in 103 of 300 cells (most: 5.2k Hz 45–345 ms, 2.2k Hz 60–420 ms); quieter in 75 (3.7k Hz 0–585 ms …); last column over −40 dB: REF 585 ms, ours 420 ms" |
| 8 | baixa | Estéreo colapsado em silêncio | Linha `stereo:` (L−R em dB, side sob mid em dB) quando há 2 canais; a grade segue mono |
| 9 | baixa | Som vozeado sem altura na grade | Linha `f0` com o Hz a cada 5 colunas quando ≥ 20 % vozeado (criatura, fala, bark) |
| 10 | baixa | 8 kHz corta o "ar" da gravação a 44,1 kHz que nosso 16 kHz não tem | Uma linha, não uma linha de grade: "REF has energy above 8 kHz (−12 dB re peak); ours cannot (16 kHz)" |
| 11 | baixa | Rótulos "7351" sugerem precisão de 1 Hz | Centro da banda arredondado (7400, 830); medido: 2 significativos custam **menos** tokens que "7.4k" |

Comparadas por `scipy.signal.gammatone` + `lfilter` (um cocleograma de verdade) contra a STFT com janela por banda:
a STFT ganha por ser centrada (o gammatone atrasa os graves em ~10 ms, e o leitor concluiria "os graves começam
depois"), por numérica estável a 44,1 kHz/100 Hz (polos do IIR de 8ª ordem colados no círculo unitário) e por
vetorizável numa chamada de `rfft` por comprimento de janela. Diferença de leitura entre as duas: nenhuma que
importe a 6 dB por passo.

## 3. O formato

### 3.1 Bandas

**ERB, 20 bandas, 80 Hz–8 kHz** (1,5 ERB por banda), agudos em cima. Bark e mel dão o mesmo desenho; ERB é a escala do
ouvido e cabe numa fórmula. Medido com o par `clash` (completo, dois zooms, com linhas): 16 bandas = −15 % de tokens,
24 = +15 %. 40 bandas (as do `envelope_db`) dobrariam a grade sem leitura nova. `--bands 16|24` para quem quiser;
`--hi HZ` muda o teto (um render a 48 kHz contra uma gravação a 48 kHz pode ver 12 kHz); o teto padrão é
`min(8000, Nyquist − 100)` dos dois sinais, como em `against`.

### 3.2 Tempo e análise

Por banda, uma STFT Hann com **janela ≈ 2/ERB(fc), limitada a 3–40 ms**, centrada no meio da coluna (100 Hz: 40 ms;
1 kHz: 15 ms; 4 kHz: 4 ms), energia somada nos bins da banda, dividida pelo comprimento da janela. É a resolução
temporal do próprio ouvido por banda, sem atraso de grupo. Implementação: para cada comprimento de janela distinto,
quadros por `stride_tricks` → um `rfft` → matriz bandas×bins pré-computada → grade bandas×colunas. Custo: ~0,02 s por
grade vetorizada.

Colunas: 50 por grade (medido: 40 = −11 %, 60 = +9 %), 30 no zoom de ataque (2 ms × 30 = 60 ms, como no protótipo:
50 colunas de 1,2 ms custam 30 % a mais e não lêem melhor). Tempo zero = onset de cada sinal (a regra de `measures`);
`--align peak` alinha pelos 10 ms mais fortes quando o onset é suave (respiração antes de um rugido).

### 3.3 Nível

**Dígitos 1–9 em passos de 6 dB sob a célula mais forte do próprio sinal, ponderação A por banda, `.` abaixo de
−54 dB.** 6 dB é "o dobro da amplitude", um passo com que o modelo raciocina; 9 níveis cobrem 54 dB, acima do piso de
−40 dB das gravações. Símbolos (` .:-=+*#%@`) economizam 2 % e perdem a aritmética; letras com 3 dB (18 níveis) são
ilegíveis ao comparar. Relativo ao próprio pico, nunca a uma escala comum: o ganho de uma gravação é arbitrário
(`BASIS` já diz isso). Modelo de loudness (Zwicker/ISO 532): não; a ponderação A é o que torna os graves honestos, o
DIFF é indiferente à ponderação, e o relativo entre dois sons é o que se lê.

### 3.4 As grades e as linhas (a saída de `TUNE ear SOUND --vs OTHER`)

Cabeçalho (uma linha por sinal): `REF refs/clash.wav 44100 Hz stereo 1.21 s, onset 0.18 s, noise floor −41 dB` e
`OURS output/reviews/…/audio.wav 16000 Hz mono 0.62 s, onset 0.00 s`. Depois, por zoom: grade REF, grade OURS, DIFF.
Sob cada grade: linha `dB` (nível de banda larga por coluna, mesma codificação) e régua `ms` com valores a cada
5 colunas; linha `f0` (Hz a cada 5 colunas) quando ≥ 20 % vozeado. Ao fim: `peaks` de cada sinal, `stereo:` quando
há dois canais, a linha "above 8 kHz" quando se aplica, e a linha fixa "Not shown". Trecho medido do par `clash`
(som inteiro; a grade OURS e o zoom de ataque omitidos aqui):

```
REF 0..750 ms, 15 ms/col
 7400|788975666455444443333222221111.1.111111111.1222121|
 6200|8998878776665454434333222221112111111.111.2.11.111|
 3700|77877767776666566555555554444444343333322222212222|
 1800|6788677755554553343333223322212.11.1..1..1.1.111.1|
  830|4551..............................................|
  110|.11...............................................|
   dB|89998887777766665555555554444443333333333232332222|
   ms 0    75   150  225  300  375  450  525  600  675
DIFF ours vs REF 0..750 ms, 15 ms/col: + ours louder by over 6 dB, - quieter, = within 6, blank both under -40
 6200|=-===+=+=+===+=+=+=+++++                          |
 5200|===+++=+++++=++++++++++                           |
 3700|--==--==--=----------------------------           |
 2200|=-==+===++=+=++=+++++++=++ +                      |
 1000|--++++++++                                        |
   ms 0    75   150  225  300  375  450  525  600  675
ours louder in 103 of 300 cells (most: 5200 Hz 45-345 ms, 2200 Hz 60-420 ms); quieter in 75 (most: 3700 Hz 0-585 ms, 2600 Hz 0-420 ms)
last column over -40 dB: REF 585 ms, ours 420 ms
REF peaks: 3730 Hz +0 dB rings 420 ms; 3050 Hz -6 dB rings 350 ms; 2450 Hz -8 dB rings 320 ms
OURS peaks: 6480 Hz +0 dB rings 170 ms; 5530 Hz -0 dB rings 170 ms; 1750 Hz -2 dB rings 250 ms
Not shown: phase, detail finer than a column or a band, roughness, masking. Cells are A-weighted band energy in 6 dB steps re each sound's own loudest cell, not loudness.
```

Leitura que isso permite e o protótipo não: o ring da referência em 3.730 Hz a −20 dB aos 420 ms (nosso nada ali:
a linha 3700 é `-` até 585 ms); nossa energia em 5–6 kHz de 45 a 345 ms; nosso som acaba 165 ms antes a −40 dB.

**Linhas extras, fase 2:** `onsets` (`^` sob a coluna em que o nível de banda larga sobe ≥ 10 dB em 10 ms após uma
queda: passos, risadas, um jingle de 3 notas). **Fase 3, só se a calibração mostrar falta:** `modulation:` (taxa de AM
20–150 Hz por banda: aspereza como fato, não como julgamento).

### 3.5 Zooms automáticos

| Som | Grades | Regra |
|---|---|---|
| impacto, UI, bark (`attack_ms` < 30, `active_s` < 3 s) | ataque 0–60 ms a 2 ms (30 col.) + inteiro | o inteiro vai do onset ao fim comum (`common_end_db`) do mais longo, passo arredondado para 5/10/15/20/25/50/100/200/500 ms × 50 colunas |
| criatura, fala, música curta | só o inteiro (+ `f0`) | idem |
| loop (`capabilities`/`loop_boundary` do manifesto) | um período + emenda: 30 colunas de 2 ms centradas na fronteira | o clique da emenda aparece como coluna isolada; `loop_boundary.sample_step` já existe |
| > 5 s (ambiência, música) | inteiro a ≥ 100 ms/coluna | o cabeçalho diz "fine structure under the column: use --at" |
| `--at START[,LEN]` (ms) | uma grade de 50 colunas no trecho | substitui as automáticas, como o `--at` do `shot` |

### 3.6 DIFF com sons desalinhados ou de comprimentos diferentes

Cada grade é normalizada ao próprio pico e cortada no próprio onset antes da diferença; o DIFF cobre o mais longo:
onde só um tem energia acima de −40 dB aparece `+`/`-` (o outro é "silêncio"), onde nenhum tem, vazio. A linha-resumo
e "last column over −40 dB" dizem o que a cauda do DIFF significa. Sem esticar o tempo: a diferença de duração é o
fato acionável (`knobs.length`), e `ref.loud_db` já compara formas em tempo normalizado. Sem correlação cruzada para
alinhar: `--align peak` cobre o caso do onset suave; se a calibração mostrar desalinhamentos, é a hora.

### 3.7 Texto × PNG

**Sem PNG para o modelo.** Medido hoje: o PNG (400 tokens) deu estrutura grossa; o texto deu detalhe acionável. Uma
imagem legível por célula precisa do tamanho do `shot` (1.568 px ≈ 550–1.250 tokens), custa mais que a grade e o
modelo não endereça nem conta células numa imagem; o próprio pxl diz que `ascii` é mais barato que imagem para
pixels exatos. Para o humano a página de curadoria já desenha espectrogramas, diferença e espectro médio. Se um dia
fizer falta (sons longos), `--png` seria esta mesma grade em 9 cores discretas, 8 px por célula, rótulos, 1.568 px de
largura, custo conhecido (~1k tokens): não agora.

### 3.8 Comando e opções

```
TUNE ear SOUND [--vs OTHER | --vs ref | --vs none] [--brief] [--lines] [--at START[,LEN]] [--cols 50] [--bands 20]
         [--hi HZ] [--weight a|none] [--align onset|peak] [--json]
```

- `SOUND`/`OTHER`: um bundle (`audio.wav` retido) ou um WAV (uma gravação, um `freeze`). Nunca renderiza: `review`
  antes. `--vs ref` = a referência que o próprio bundle carrega (`arrays["reference"]`), **padrão quando ela existe**;
  `--vs none` para o som sozinho.
- `--brief`: só DIFF + linhas (~1k tokens); `--lines`: só as linhas (§5, ~200 tokens). `--json`: `tune.ear/1` com as
  grades como strings, `peaks`/`stereo`/`kind` como dados, `basis`.
- Por que `TUNE ear` e não `dsl ear`: não toca o DSL (sem fonte, sem revisão), aceita WAV, é da família de `inspect`;
  `dsl help ear` existe como tópico (como `listener` e `reference`, que também não são subcomandos `dsl`).
  Alternativas: `hear`, `look`, `shot`. `ear` é a palavra do usuário e tem três letras.
- Arquivo: `src/tare/tools/tune/ear.py` (~150 linhas: `cochleagram`, `grid_text`, `diff_text`, `peaks`, `render`)
  + `cmd_ear` em `cli.py`, reaproveitando `read_channels`, `load_bundle`, `measures` (onset, `active_s`, `attack_ms`,
  `f0`), `common_end_db`, `yin`/`clean_f0`.

### 3.9 Custos medidos (`o200k_base`, par `clash`, 20 bandas)

| Saída | Tokens |
|---|---|
| Protótipo de hoje (6 grades) | 2.085 |
| **`ear --vs` completo** (ataque 30×2 ms + inteiro 50 col., REF/OURS/DIFF, linhas `dB`/`ms`, resumo, `peaks`, Not shown) | **2.404** (rótulos inteiros; 2.562 com "7.4k") |
| **`--brief`** (DIFF dos dois zooms + linhas) | **987** |
| som sozinho (OURS nos dois zooms + linhas) | 852 |
| um só zoom, completo / brief | 1.412 / 570 |
| 16 / 24 bandas (completo) | 2.456 / 3.343 (geometria de 50 col. nos dois zooms: 2.916 na base) |
| só as linhas (`--lines`) | ~200 (estimado; medir na fase 0) |

Numa sessão de 10 turnos: primeiro olhar completo (2,4k) + 9 `--brief` (9k) ≈ 11k tokens, metade de um `describe` do
pxl por turno. A skill pede exatamente isso.

## 4. Integração

| Com | Como |
|---|---|
| `references` | `TUNE ear BUNDLE` de um som com referência compara com ela sem flag (`--vs ref` implícito); cabeçalho nomeia o arquivo; `--vs none` desliga |
| candidatos de `--dry-run` | `TUNE ear CAND --vs A` (A = o bundle de onde os candidatos saíram) é o `shot --vs HEAD --diff`: o que a edição mudou no ouvido; com referência, `--vs ref` é o alvo e `--vs A` a mudança; o agente escolhe qual lhe serve |
| rodadas de curadoria | nada muda na página; o manifesto guarda o bundle de cada cartão, logo `TUNE ear` roda sobre eles; §6 acrescenta `curate.py predict`/`agree` (~40 linhas) |
| `review` | **nunca inline**: nem no compacto nem no detalhado (2,4k por turno sem decisão que dependa disso); a skill diz quando chamar `ear`; um ponteiro `"ear": "TUNE ear BUNDLE"` custaria 10 tokens por turno para repetir a skill: não |
| `dsl help ear` | tópico em `HELP`: usage, meaning ("the sound as text: bands by time, 6 dB digits, peaks; never how it sounds"), example, rules (o que mostra, o que não mostra, `--brief` depois do primeiro olhar, `--vs ref` padrão) |
| SKILL.md | §4.1 |
| docs | seção "Hear it as text" em `docs/dsl-review.md` após "Hold a sound against a recording" (+ `pt-BR/revisao-dsl.md`); uma linha em README "Authoring and diagnostics"; `docs/README.md` índice |

### 4.1 SKILL.md: 305 caracteres a acrescentar e ~308 a cortar

Acréscimo, no passo 3, sob "A recording to match":

> `   - **Hear it:** `TUNE ear BUNDLE` prints the sound as text, bands by time in 6 dB digits, with its peaks in Hz;
> `--vs REF|BUNDLE` adds the other and a DIFF, `--brief` the DIFF only (~1k tokens). Read attack, ring and tail from
> it; it never says how it sounds (no phase, roughness or masking).`

Cortes (medidos, com a quebra de linha): a linha "Live view of your edits: `TUNE studio …`" do passo 5 (105; o studio
segue em `TUNE --help`), a linha da tabela "the sound list of a whole tactics RPG" (83; `docs/tactics-sounds.md` fica
nos docs), a linha `TUNE music victory --seed 3` do passo 1 (50; `fanfare` está no template) e fundir as duas linhas
de Examples numa (~70). Total ≈ 308. `tests/test_skill.py` passa a conferir `TUNE ear` e suas flags sozinho.

## 5. O som em palavras (`--lines`): o que o DSP determinístico pode afirmar

Não é um comando novo (`describe` está tomado por controles): são as linhas que `ear` já imprime, sem grade. ~200
tokens. Só do que `measures` e os picos dão:

| Linha | Diz | Nunca diz |
|---|---|---|
| `kind` | canais, taxa, duração, onset, `active_s`, piso de ruído, clipping, vozeado/não, loop | o que é ("espada", "metal"), estilo |
| `envelope` | `attack_ms`, tempo até −20 e −40 dB, fim a −60 quando o piso permite | "seco", "pesado" |
| `peaks` | até 4 picos: Hz, dB re o mais forte, ring até −20 dB; "none over 8 dB prominence (noise-like)" | "metálico", "tonal bonito" |
| `pitch` | mediana Hz, faixa p10–p90 em st, glide (st entre o primeiro e o último terço vozeado, sinal), sílabas | "agressivo", "natural" |
| `brightness` | centróide no primeiro e no último terço (Hz) e a diferença em st ("darkens 7 st over 400 ms") | "brilhante demais" |
| `stereo` | L−R dB, side sob mid dB | "largo", "imersivo" |
| `Not shown` | fase, estrutura fina sob coluna/banda, aspereza, mascaramento, loudness | |

`TUNE study` (fase 5 do plano de referências) reutiliza estas linhas como seus `facts` e acrescenta `in_tune`; não
há duas descrições.

## 6. Calibração: a leitura do modelo prevê o ouvido do usuário?

**Pergunta:** quando o assistente lê `ear` de 3 candidatos contra REF e escolhe o mais próximo, acerta o que o usuário
escolhe? Mais do que o acaso, mais do que os números de `ref` sozinhos, perto da consistência do próprio usuário?

**Material:** 4 referências (as duas de hoje, `clash` e `wolf`, mais uma UI e um passo/porta da biblioteca do
usuário, só nesta máquina); por referência, candidatos = `--dry-run` de um bundle, um knob por grupo (`brightness`,
`length`, `ring`/`register`, `species`/`take`).

**Tarefas por rodada (uma referência por rodada):**
- 3 grupos `pick` + `rate:perto da referência` com REF + 3 candidatos (`CURATE compare … --reference`);
- 1 par ABX sem REF, candidatos com DIFF pequeno (≤ 10 % de células `+`/`-`): o modelo prevê se o usuário **distingue**
  (calibra o limiar "dentro de 6 dB = igual");
- 2 grupos `pick` repetidos (de uma rodada anterior; na primeira, desta mesma) com ordem embaralhada: a
  **consistência do usuário** (o teto).

**Cego, sem vazamento:** no mesmo turno em que cria a rodada, o agente roda `TUNE ear CAND --vs ref --brief` por
candidato e grava `curate.py predict ROUND predictions.json` (pick, nota 1–5, "distinguível" sim/não, uma linha de
evidência: as células) **antes** de servir a página; `predict` recusa se já houver resposta; `agree` recusa
predições gravadas depois da primeira resposta (mtime de `evaluations/<rev>.json`). O agente não abre a página nem lê
`answers.json` até o `agree`. Isso fica escrito no protocolo e na help do `predict`.

**Baselines, calculados por `curate.py agree ROUND` (~40 linhas, com `answers_json`):** acaso (1/3 no pick, 1/2 no
ABX); regra numérica fixa (o candidato com a menor soma de |Δ| de `ref` em unidades normalizadas: log da razão de
`active_s`, centróide em st/3, `env_db`/8, `attack_ms`/10); o assistente lendo `ear`. Saída: acerto no pick (n),
Spearman das notas, acerto na distinguibilidade, e a consistência do usuário nos repetidos. n = 20 picks (12 novos +
8 repetidos) + 4 ABX, somados por `agree R1 R2 R3 R4`, que diz também com que frequência um chute acertaria tanto
(revisto em 2026-11-02: com os 8 picks do primeiro desenho, 5 acertos saem do acaso 1 vez em 11, e 4 repetidos não
medem a consistência de ninguém; com 20, 11 acertos já ficam abaixo de 5%). Escrita em
`FEEDBACK.md`/`docs/ear-calibration.md` só com aprovação.

**Custo:** usuário: ~22 cartões por rodada, ~10 s por cartão (3 escutas + REF) + decisões ≈ 7–8 min por rodada,
**~30 min no total**, em sessões separadas. Agente: por grupo 3 × ~1k (`--brief`) + raciocínio ≈ 5k; 24 grupos ≈
**120k tokens** no total. Sem GPU, sem modelo externo.

**Quando o assistente pode decidir sozinho (depois da calibração):** só com pelo menos 20 picks somados, um chute
fazendo o mesmo menos de 5% das vezes (a linha do `agree`), e só entre candidatos de **um knob**, quando o DIFF
é unilateral (toda banda que difere tem o mesmo sinal) e o acerto medido ficou ≥ consistência do usuário − 15 pontos e
acima da regra numérica; menos que isso é uma pista, não uma licença; mesmo assim diz "escolhido pela leitura, não por escuta". **Sempre pergunta** quando: o DIFF é
misto, a pergunta usa palavras de timbre (áspero, metálico, natural), é fala (inteligibilidade), ou o som vai ser
entregue. Antes da calibração: sempre pergunta.

## 7. Ouvidos semânticos opcionais

| Ouvido | Custo | Privacidade | Determinismo | Veredito |
|---|---|---|---|---|
| CLAP zero-shot no `aaaaa` ("metallic/wooden/bright") | `gpu run`, minutos; extra `[clap]` | local | fixo por arquivo de modelo, não entre versões | **Fora deste plano.** Já é o juiz opcional da fase 7 do plano de referências; só como 4º braço do §6 se a leitura falhar em palavras de timbre |
| Whisper CER / UTMOS (fala) | extras `[asr]`/`[teacher]`, GPU | local | não (Whisper premia palavras plausíveis) | Ferramentas de desenvolvedor existentes; `ear` não mostra inteligibilidade e diz isso; um grupo de fala no §6 com CER como baseline, depois |
| Audio-LM local (p.ex. Qwen2-Audio) no `aaaaa` | horas de setup + GPU | local | não | Diria "a metallic clash": o julgamento que proibimos na saída; como **braço juiz** da calibração seria legítimo. Não agora |
| Gemini audio (AGY), só renders | inferência paga, aprovação por envio | externo; a referência nunca sai → só perguntas de atributo | não | Não neste plano; possível braço de atributo depois, com aprovação |

Nenhum entra nas fases. O protocolo do §6 aceita braços novos sem mudar.

## 8. Fases, aceite e testes

Sinais de teste: clique + senóide de 3 kHz decaindo + rajada de ruído (impacto), chirp de 200→400 Hz (glide), senóide
pura, silêncio, 40 ms de som, estéreo com L 6 dB acima, versão degradada (ruído −45 dB, 44,1 kHz) do mesmo impacto, um
loop renderizado pelo tune, um jingle de 3 notas.

### Fase 0: `ear.py` (MVP)
`cochleagram`, `grid_text`, `diff_text`, `peaks`, linhas, `render`. Testes (`tests/test_ear.py`): determinismo (mesmo
texto duas vezes); senóide de 3 kHz → `9` na linha 3100 e ≤ `3` duas bandas acima/abaixo; clique → todas as linhas
≥ 1 kHz chegam a `9` em ≤ 2 colunas do ataque; som contra ele mesmo → DIFF só `=`/vazio, resumo "0 of N"; versão
degradada → DIFF com ≤ 5 % de `+`/`-` e "last column" igual ±1 coluna; chirp → linha `f0` sobe; senóide → `peaks`
com o Hz ±1 bin e "rings past the end"; ruído → "noise-like"; 40 ms → não quebra; estéreo → `stereo: L−R +6 dB`;
tamanho do texto do par sintético < 9.000 caracteres (completo) e < 3.600 (`--brief`), sem tiktoken no teste.
Aceite: < 0,5 s por chamada em sons ≤ 3 s; `pytest tests/test_ear.py --basetemp output/pt` verde.

### Fase 1: `TUNE ear` + `--vs ref` + `--json` + `dsl help ear` (MVP)
`cmd_ear` em `cli.py`; bundle com referência → `--vs ref` implícito e cabeçalho com o arquivo; WAV × WAV; `--vs none`;
`--brief`, `--lines`, `--weight`, `--align`, `--json` validado. Testes: CLI sobre um bundle de `review` de um
documento com referência sintética (`tests/test_reference.py` já monta um); `dsl help ear --json` existe.
Aceite: `TUNE ear BUNDLE --brief` imprime DIFF + linhas; `--json` tem `schema: tune.ear/1` e `basis`.

### Fase 2: zooms automáticos, `--at`, loop, `onsets`
Regras de §3.5; `loop_boundary`; linha `onsets`. Testes: loop → grade de emenda centrada na fronteira; jingle → 3 `^`;
som de 8 s → passo ≥ 100 ms e o aviso; `--at 100,60` → uma grade.

### Fase 3: skill + docs (MVP)
§4.1 e docs. Aceite: `tests/test_skill.py` verde, `< 11000`.

### Fase 4: `curate.py predict` / `agree`
~40 linhas; testes em `tests/test_curate.py` com respostas sintéticas: `predict` recusa com resposta existente; `agree`
recusa predição tardia; acerto, Spearman, baseline numérica e consistência calculados sobre um manifesto montado no
teste. Aceite: `python tools/curate.py agree ROUND --root output/rounds` imprime a tabela.

### Fase 5: as rodadas de calibração (só com aprovação: ~30 min do usuário, ~120k tokens)
§6. Resultado em `FEEDBACK.md` e, se valer, `docs/ear-calibration.md`.

### Fase 6 (depois, por evidência): `modulation:`, `--channel L|R|side`, `--png`, braços semânticos.

## 9. Riscos

| Risco | Mitigação |
|---|---|
| O modelo lê padrão em ruído (flicker de 1 nível entre colunas) e "corrige" o que não existe | Passo de 6 dB; DIFF só acima de 6 dB; a linha-resumo conta células; regra na skill: "a DIFF cell is 6 dB and 1.5 ERB: smaller is not shown" |
| "Pelo `ear` soa parecido" vira frase do agente | Linha "Not shown" em toda saída; regra da skill "it never says how it sounds"; a calibração mede exatamente isso |
| Custo: 2,4k por olhar completo, 10 olhares = 24k | `--brief` depois do primeiro, dito na skill; um só zoom quando o som não tem ataque |
| Onset em gravação com piso acima de −35 dB cai no ruído | Mesma regra de `measures` (−35 dB) + `--align peak`; o cabeçalho imprime o onset em s para o leitor conferir |
| Ponderação A esconde um grave de verdade (um boom, um passo pesado) | `--weight none`; a linha `peaks` não é ponderada |
| Linhas de grave com janela de 40 ms borram o ataque de um kick | Dito na help: "rows under 500 Hz average 20–40 ms"; o `attack_ms` de `measures` é de banda larga e vale |
| Estéreo colapsado esconde um problema de fase (cancelamento em mono) | `stereo:` reporta side sob mid; `inspection` já preserva canais; `--channel` fica para a fase 6 |
| Sons longos (ambiência 20 s) a 400 ms por coluna não dizem nada | Aviso + `--at`; a grade não é a ferramenta: `measures` e a página |
| Expectativa de paridade com o pxl (`blind`, `compare`, `--fix`) | `blind` já existe como ABX; `compare` é a linha-resumo; `--fix` não (plano de referências, §1) |
| Calibração com n pequeno vira "provado" | Reportar n, baseline e consistência; nenhuma regra de decisão sozinha antes do §6 |
| `peaks` em fala/criatura lista harmônicos, não "rings" | Em som vozeado a linha `peaks` sai como "harmonics of f0" (múltiplos de `median_hz` ±3 %) e só lista picos não harmônicos |

## 10. Decisões do usuário

| Decisão | Recomendação |
|---|---|
| 1. Nome: `TUNE ear`, `dsl ear` ou `hear` | `TUNE ear` (não mexe no DSL, aceita WAV, é da família do `inspect`) |
| 2. Som com referência: comparar com ela sem pedir | Sim (`--vs ref` implícito; `--vs none` desliga) |
| 3. Tamanho padrão: completo (2,4k) ou só o DIFF (1k) | Completo no primeiro olhar, `--brief` depois; a skill diz isso |
| 4. Ponderação A ligada (os graves aparecem como se ouvem, ~19 dB mais fracos a 100 Hz) | Sim; `--weight none` mostra a energia crua |
| 5. 20 bandas (16 = −15 %, 24 = +15 %) | 20 |
| 6. O que cortar da skill (305 caracteres) | A linha do studio no passo 5, a linha "tactics RPG" da tabela, o `TUNE music` do passo 1, fundir as duas linhas de Examples |
| 7. PNG para o modelo | Não (texto leu melhor e custa menos; a página já desenha para você) |
| 8. Rodar a calibração (4 rodadas, ~30 min de escuta no total, ~120k tokens; 20 picks, revisto em 2026-11-02) | Sim, depois das fases 0–3: é o que diz se o assistente pode escolher sozinho |
| 9. Ouvidos semânticos (CLAP, Whisper, audio-LM, Gemini) | Nenhum agora; CLAP como braço da calibração só se as palavras de timbre falharem |
| 10. O assistente escolher sozinho entre candidatos | Só depois da calibração, só com um knob e DIFF unilateral, sempre dizendo que foi por leitura; o resto pergunta |

## 11. O que não construir (e por quê)

- **PNG/espectrograma para o modelo:** mais caro que o texto no tamanho legível; não endereçável; a página já tem.
- **Modelo de loudness (Zwicker, ISO 532):** o relativo entre dois sons é o que se lê; a ponderação A basta.
- **Banco de filtros gammatone IIR:** atraso por banda confunde a leitura; numérica frágil a 44,1 kHz; a STFT por banda
  dá a mesma resolução temporal sem isso.
- **Grades por canal por padrão:** SFX de jogo são mono; uma linha `stereo:` cobre; `--channel` só se pedirem.
- **DIFF com tempo esticado ou alinhamento por correlação:** a duração é o fato acionável; `loud_db` já compara formas.
- **`ear` dentro de `review`:** 2,4k por turno sem decisão que dependa disso.
- **Mudança na página de curadoria:** nada a mostrar ao humano que ela não mostre.
- **Comando `describe` para som:** o nome é dos controles; as linhas vivem em `ear --lines` e em `study`.
- **CLAP, Whisper, audio-LM ou Gemini no loop:** não determinísticos, GPU ou externos; o §6 mede primeiro se a leitura
  determinística já basta.
- **Passos de 3 dB / letras, símbolos no lugar de dígitos:** menos legível, 2 % mais barato.
- **`ear` automático em cada candidato de `compare`:** 3–9 × 1k tokens sem o agente pedir; ele chama quando precisa.
- **`--fix` a partir da grade:** só `length` seria honesto, e `in_tune` do `study` já dá o valor.
