# Plano: estudar referências e cobrar o som renderizado contra elas

2 de novembro de 2026. Revisão crítica, somente leitura e sem inferência, do rascunho da sessão principal
("referência por som, comparação em `review`, tolerâncias, `CURATE compare --reference`, `TUNE study`, CER, regra na
skill"). Pergunta do usuário: antes do DSL estudávamos áudio de jogo e fala (gravações de referência, "professor" de voz,
inteligibilidade); dá para continuar, como isso entra no DSL e dá para amarrar ao check do áudio produzido, como o pxl
tem `study` e `check`? Formato segue `docs/plans/2026-11-01-skill/PLAN.md`.

**Decisões do usuário (2 de novembro):** as recomendações da §9, com uma mudança na 2: um som **sem** referência
fica `absent` e não reprova (um banco costuma ter referência em poucos sons); só uma medida pedida que não pôde ser
feita fica `not_run` e reprova. Feito: fases 0–4 e 6. Depois: fase 5 (`study`, com `--search` mais adiante) e a
avaliação (fase 7), só com aprovação. Mudanças na implementação: o fim da parte ativa é −40 dB ou 6 dB acima do
ruído mais alto (o mesmo para todos os sinais comparados juntos); o envelope compara bandas com piso de −40 dB
(o ruído de uma gravação preenchia os vales: 21,8 dB de diferença num mesmo som, 1,9 com o piso); `f0_hz` com os dois
sem altura passa, com um só reprova.

Restrições que valem para tudo abaixo: núcleo determinístico, CPU, sem dependência nova obrigatória; gravações de jogo
só para análise local (nunca em repo, testes, fixtures, exports ou bundles entregues; `curate serve` em 127.0.0.1);
testes com sinais sintéticos, `pytest --basetemp output/pt`; nunca navegador headless na página de curadoria; CLAP e
Whisper grandes só pelo `gpu run` no nó `aaaaa`.

## 0. Fatos conferidos no código

Confirmados (com o que faltava dizer):

- **`TUNE inspect FILE.wav --json`** (`cli.py:517`, `inspection.py`): `read_channels` (WAV 16-bit mono/estéreo pela
  stdlib; outros formatos via soundfile, que está no `.venv`), limite 180 s. Dá níveis por canal, `clipped_samples`,
  quadros de F0 com candidatos e `status` (`estimated`/`ambiguous`/`unvoiced`), parcial dominante, energia por banda,
  degrau do loop. Não dá: duração ativa, ataque, cauda, centróide, envelope espectral.
- **`analysis.py`** (numpy/scipy): `trim` (35 dB), `yin` + `clean_f0`, `segments` (sílabas), `envelope_db` (40 bandas
  mel-ish até 8 kHz, dB sob o próprio pico), `features` (duração aparada, contorno de pitch em 16 pontos, contorno de
  loudness em 16 pontos, envelope, aperiodicidade, fração vozeada, sílabas) e `distance` (soma ponderada).
  **Funciona sem CLAP**; `tests/test_designer.py` já o testa com um `FakeClap`. Medido aqui: `features` de 1,5 s a
  48 kHz leva 76 ms; de 60 ms, 2 ms; `inspect_audio` de 1,5 s, 50 ms.
- **`match`/`design`** (`designer.py`): o comando exige `[clap]` (torch/transformers, não instalados), mas `_search`
  aceita qualquer função de score: uma busca só por DSP (`-distance(features(render), alvo)`) são ~10 linhas.
- **Fala, só para desenvolvedor** (`tools/`): `intelligibility.py` (CER por Whisper, extra `[asr]`, não instalado;
  o docstring avisa: "Whisper recompensa palavras plausíveis; sinal de regressão, não verdade"); `teacher_calibration.py`
  e `structure_analysis.py` (Kokoro como professor, distância espectral por classe de fone, UTMOS; extra `[teacher]`,
  `pyworld` e `soundfile` instalados, `kokoro` não); `real_prosody.py` experimental. São ferramentas de **calibração
  do motor**, não checks por frase.
- **Estudos em docs:** `docs/rpg-sounds.md` ("1. medir gravações, 2. modelar, 3. ouvir em contexto"), `tactics-sounds.md`,
  e os comentários numéricos nas receitas (`sfx/physical.py:489`: "swing sem corte é um whoom escuro, centróide
  0,4–1 kHz, tom grave 150–270 Hz"). Ou seja: as receitas **já foram desenhadas a partir de números**; o que falta é
  medir os mesmos números no render e mostrá-los ao lado.
- **`reference` no topo do documento** (um WAV por arquivo): `validate.py:183/268` (só a chave `file`, caminho via
  `asset()`, restrito à pasta do documento ou `--asset-root`); `compiler.py:563-578` lê com `read_channels`, guarda o
  PCM em `captured.arrays["reference"]`, `manifest["reference"] = {sample_rate, pcm_id}` e o sha256 do arquivo nas
  dependências; `workflow.py:28` recalcula o hash e qualquer mudança no arquivo dá `E_REVISION_CONFLICT` (exit 3);
  `studio.py:270` toca o modo `reference`; `inspect_capture` copia `manifest.reference`. **Nada mede o som contra ela.**
  Detalhe importante: `save_bundle` grava todos os `arrays`, logo **todo bundle de um documento com referência carrega
  o PCM da gravação** (`buffers.npz`). Bundles ficam em `output/` e `freeze`/`export` não os carregam, mas é uma regra a
  escrever: bundle não se compartilha.
- **Checks** (`review_data.py:86-130`, `dsl help checks`): `duration_s`, `peak_dbfs` (min/max), `sample_rate`,
  `channels`, `capabilities`. `coverage` = `{capture_integrity, perceptual_quality: not_run, pitch: not_requested}`.
  Regra já existente que importa: no CLI, `status` `failed` **ou `not_run`** vira `E_CHECK_FAILED` (exit 5), e um edit
  com candidato nesse estado não grava (`workflow_cli.py:150`, `workflow.py:prepare`).
- **Curadoria:** `Round.group(..., reference=LABEL, targets={medida: alvo})` já existe; a página desenha a diferença de
  espectrograma contra a referência (tecla D, ±15 dB), o espectro médio alinhado em 200 Hz–4 kHz e uma tabela de medidas
  com coluna "alvo" que destaca o cartão mais próximo (excluindo a referência). `compare_bundles` já usa
  `reference="A"` e só aceita bundles (`load_bundle`). Em rodada **cega a referência também fica escondida**
  (`curate.html:423`, `455`): um `--reference` tem de abrir a rodada.
- **SKILL.md:** 10.948 bytes (`tests/test_skill.py` cobra `len < 11000` chars); não cita `inspect`, `reference` nem estudo.
- **Resposta compacta medida agora** (`o200k_base`): `dsl review --response compact` de `confirm` = **186 tokens** (o plano
  da skill mediu 155 com um caminho de bundle mais curto). Um bloco de referência mínimo (`[ref, som]` para 4 medidas +
  distância + status) = **48 tokens**; um bloco verboso com `basis` e `status` por medida = 94.
- **`.venv`:** soundfile, pyworld, tiktoken, matplotlib instalados; torch, transformers, faster_whisper, kokoro não.
- **Avaliação anterior:** `FEEDBACK.md` guarda as três tarefas-piloto de 2026-11-01 (fala pt-BR natural; conjunto
  pequeno bark + moeda + morte de criatura; `ui confirm` mais firme) e o benchmark de review tem três tarefas
  roteirizadas (refinar Voice, transpor + MIDI, editar uma entrada de banco). A sonda de disparo foi áudio vs pixel art.

Correções ao que a sessão principal escreveu:

| Afirmação | Correção |
|---|---|
| "`match` e `design` precisam do extra `[clap]`" | Os comandos sim; `analysis.features`/`distance` não, e `designer._search` aceita qualquer score. A metade DSP de `match` está disponível hoje |
| "`inspect` dá F0, parcial dominante…"; implica que serve de estudo | Serve de matéria-prima; ataque, cauda, duração ativa e centróide **não existem** em lugar nenhum (o centróide só em `tools/teacher_calibration.py`, para fricativas) |
| "`Round.group(reference=...)` desenha a diferença": faltou dizer que `targets` e a coluna "alvo" já existem | Item 4 do rascunho é quase só fiação: um cartão REF + `targets` |
| Rascunho pede "F0 mediana **e contorno**" e "pico e RMS" contra a referência | Contorno só faz sentido vozeado (criatura/fala); pico/RMS de uma gravação são masterização, não alvo. Ver §3 |
| "SKILL.md: 10.947" | 10.948 bytes; sobra ~50 caracteres: qualquer linha nova exige corte |
| "Exports cortam a cauda a 60 dB": verdade, e o `duration_s` de `review` é o PCM retido, **sem** corte | A comparação tem de nomear a extensão: ver "base de comparação" em §3 |

## 1. O que `study`, `compare` e `check` do pxl fazem, e o que transfere

Lido em `src/core/study.ts`, `src/core/render.ts:265` (`compareSilhouettes`), `src/node/check.ts`, `README.md`,
`SKILL.md:16,180`, `docs/getting-started.md:226-241`.

- **`study`** lê a imagem (grade 1x, paleta, rampas, técnicas, folha, objetos, valores, perspectiva, movimento, peças)
  e termina com uma seção **"IN PXL"**: para cada achado, o construto que o reproduz (`use("x.hex")`, `outline:`,
  `dither()`, `anim(name, {frames, fps})`, `light: [..]`). Grava uma folha PNG e a paleta `.hex`. Primeiro decide o
  **tipo** ("Kind: pixel art a 4x" vs "foto: lida pelas massas, traduzida em poucas cores") e lê cada tipo de um jeito.
- **`compare`**: silhueta linha a linha (extensões opacas de cada linha no asset e na referência) e um resumo honesto:
  "N linhas em ambos: mais largo em X (até +a esq, +b dir), mais estreito em Y, igual em Z". Nada de "parecido".
- **`check`**: avisos por cena e quadro, notas "LOOK" para o olho, regras `expect` e uma linha de **cobertura**
  (`ran: …; not run: …`) "para que 'sem avisos' não seja lido como 'checado'". `--fix` muda **um número** que faz uma
  regra valer, só quando a relação é direta (um gap, uma ordem).

O que transfere para áudio:

| Do pxl | No tune |
|---|---|
| "Kind:" antes de tudo | `study` abre com o tipo: vozeado/ruidoso, one-shot/loop, mono/estéreo, taxa, piso de ruído, clipping |
| "IN PXL" | seção `in_tune`: op provável, campos com mapeamento direto (pitch de `speaker`, `length`), direções de knob com a evidência, e o que **não** dá para inferir (kind/estilo/arquétipo: busca ou ouvido) |
| Resumo de `compare` em contagens | envelope: "mais forte que a referência em 12 de 40 bandas, maior desvio +9 dB em 2,0–2,6 kHz" |
| Linha de cobertura | `coverage.reference`: `measured` / `absent`; cada medida com `status` (`measured`, `unreliable`, `not_measurable` + razão) |
| `blind` | já existe (ABX em `curate`) |
| Folha PNG | opcional: `plot.py` (matplotlib é extra) desenha envelope e espectro dos dois; a página de curadoria já faz isso melhor |

O que **não** transfere:

- A certeza pixel a pixel. Uma gravação traz sala, microfone, distância, compressão e masterização que a síntese não
  tem: nenhum número absoluto (pico, RMS, cauda a −60 dB) é alvo; só formas relativas ao próprio pico e ao próprio
  onset. Daí os status por medida e tolerâncias frouxas por padrão.
- Paleta/rampas: não há equivalente discreto. Perspectiva e movimento: não há.
- `--fix`: só honesto onde o knob é monótono e direto (`length` ↔ duração ativa; `speaker.pitch` ↔ F0 mediana). Não
  construir; `in_tune` sugere a direção e o agente edita (o `dsl edit` já devolve a nova observação).

## 2. Crítica do rascunho

| # | Gravidade | Problema | Correção |
|---|---|---|---|
| 1 | alta | Medidas propostas (ataque, −60 dB, centróide) não existem; o rascunho fala como se fossem reaproveitamento | Fase 0 escreve `analysis.measures()` (uma função, ~60 linhas) usada por `review`, `curate` e `study` |
| 2 | alta | Comparar pico/RMS e "fim a −60 dB" com uma gravação: piso de ruído de sala fica a −40/−50 dB do pico, o −60 nunca chega | Primário: onset (−35 dB) → fim a −40 dB nos dois; `end_60_s` só quando o piso da referência permite, senão `not_measurable` com a razão |
| 3 | alta | "Referência por som dentro do som" mexe no vocabulário de todo op (validação de campos, catálogo, `dsl-reference.json --check`, pointers) | Mapa no topo: `"references": {"clash": "refs/clash.wav"}`; o compilador reaproveita o bloco de `reference` existente (mesmo `arrays["reference"]`, mesmo manifesto, studio e guarda intactos) |
| 4 | média | CER do Whisper como check de `review` (item 6): extra pesado, quase sempre `not_run`, e `not_run` **falha** o review (exit 5) | Fica fora do review. Depois, opcional: `tools/intelligibility.py --wav F --text T` para quem tiver `[asr]` |
| 5 | média | "Qual receita/arquétipo chega mais perto (CLAP opcional)" no `study` | CLAP fora. Busca só por DSP, **limitada** (`--search sfx:blade` ou `--search creature`), fase opcional; `distance` distingue envelope/duração/pitch, não "espada vs machado" |
| 6 | média | F0 contorno na comparação de SFX | Contorno só no detalhado e só vozeado (fração ≥ 0,2); SFX reporta `unvoiced` |
| 7 | média | Custo compacto não quantificado | Medido: +48 tokens só quando há referência (186 → ~235) |
| 8 | média | Tolerâncias "duração ±20%" sem dizer que extensão | Tolerância sobre `active_s` (onset→−40 dB) como razão; ver §4.3 |
| 9 | baixa | Rodada cega com referência: a página esconde a referência também | `--reference` implica `--open`; dizer na help |
| 10 | baixa | Bundle carrega o PCM da referência (já hoje) | Regra em docs/skill: bundles não se compartilham; teste garante que `freeze`/`export` não carregam `reference` |
| 11 | baixa | "Como o `study` fala ao agente" não estava definido | §4.5: `tune.study/1` com `kind`, `facts`, `in_tune` |

Ordem corrigida: fase 0 (medidas) → 1 (`references`) → 2 (bloco em `review`) → 3 (tolerâncias) → 4 (`curate`) →
5 (`study`) → 6 (skill + docs) → 7 (avaliação, com aprovação). O rascunho punha `curate` antes das tolerâncias; invertido
porque `curate` e `study` reaproveitam a mesma função de medidas e a mesma forma de resposta da fase 2.

## 3. As medidas

Uma função, `analysis.measures(y, sr, *, f0=True)` → dict de medidas com `status`, usada em todos os comandos. Entrada
mono float64 (estéreo: média dos canais, dito no `basis`); quando duas taxas diferem, banda comum
`[100 Hz, min(8000, Nyquist − 100)]` nos dois (senão um render a 16 kHz é sempre "mais escuro").

| Medida | Como | Robusta para | Pouco útil para |
|---|---|---|---|
| `active_s` | do onset (1ª janela de 10 ms a −35 dB do pico, `analysis.trim`) ao fim a −40 dB | tudo | loops (reportar `loop`) |
| `end_60_s` | fim a −60 dB após o onset: **igual ao que `freeze`/`export` entregam** (`trim_tail`) | render; gravação limpa | gravação com piso > −55 dB → `not_measurable` |
| `attack_ms` | onset → primeira janela de 1 ms a −3 dB do pico (±1 ms) | impactos, UI, barks | ambiências |
| `noise_floor_db` | percentil 10 das janelas de 10 ms, re pico | diz se a gravação permite `end_60_s`; > −45 dB também marca `centroid_hz` como `unreliable` | |
| `centroid_hz` | média ponderada do espectro de longo prazo no trecho ativo, banda comum; delta em **semitons** | brilho de SFX, barks | fala (depende do fone) |
| `env_db` | `envelope_db` (40 bandas) → média do \|Δ\|, bandas mais fortes/fracas, maior desvio com faixa Hz | forma geral; é o que `distance` já pesa | referência com sala/microfone: piso típico 4–8 dB (não zera) |
| `loud_db` | contorno de loudness em 16 pontos de tempo normalizado (`features`) → média do \|Δ\| | forma do envelope independente de duração e ganho | compressão na gravação |
| `f0` | `yin` + `clean_f0`: mediana Hz, p10/p90 em semitons, `voiced`, `aper`, `segments` | criatura, fala, barks | SFX: `voiced < 0,2` → `unvoiced`; `aper > 0,5` → `unreliable` |
| `clipped` | de `inspect_audio` | sinaliza referência clipada | |

Cortados: pico/RMS da referência (masterização), fator de crista (compressão na gravação), tempo/tom de música
(DSP novo; música fica fora desta rodada: só `active_s`, loop e `env_db`), flatness (o `aper` cobre o que importa).

**Alinhamento:** cada sinal é aparado no seu próprio onset; dB sempre relativos ao próprio pico (ganho e nível de
gravação não contam); contornos em tempo normalizado (a duração é comparada à parte). Cap de 20 s de trecho ativo para
F0 (acima: `f0.status = skipped`), dito no `basis`.

**Base de comparação (obrigatória na resposta):** `basis`: "render = PCM float retido (antes do corte de exportação);
os dois sinais aparados ao próprio onset (−35 dB) e fim (−40 dB); dB re próprio pico; espectro na banda comum; estéreo
em média mono". `end_60_s` do render é o comprimento que o WAV exportado terá (salvo loop, `hall`/`echo`, `--keep-tail`).

**Relevância por domínio e o que mapeia para controles (teto da honestidade):**

| Domínio | Medidas que importam | Mapeia direto | Só direção | Não inferível de números |
|---|---|---|---|---|
| SFX (arma, UI, porta…) | `active_s`, `attack_ms`, `end_60_s`, `centroid_hz`, `env_db`, `loud_db` | `knobs.length` ↔ razão de `active_s` (estica tudo, pitch mantido) | `brightness` ↔ Δ centróide; `ring` ↔ cauda; `register` ↔ envelope deslocado em log-f; `tempo` ↔ `segments`; `power` (em `ui` é só ganho: FEEDBACK.md) | kind, style, event, species |
| Criatura | `f0` (mediana, faixa, `aper`, `segments`), `active_s`, `loud_db` | nada | `size` ↔ F0 mais grave; `aggression` ↔ `aper`/contorno; `call` ↔ sílabas e duração | arquétipo, genes (`--search` ou `match`) |
| Fala / bark | `f0` mediana e faixa, `segments`/s, `active_s`, `aper` | `speaker.pitch` (Hz) ↔ F0 mediana; `range` ↔ faixa em st | `rate` ↔ sílabas/s contra um render; `breath`/`rough` ↔ `aper` | `tract`, engine, inteligibilidade (ASR) |
| Música | `active_s`, loop, `env_db` | nada | nada | bpm, tom, seed |

Dois sons diferentes podem ter a mesma duração e o mesmo centróide: cada número diz uma coisa só, e a resposta diz qual.

## 4. Desenho

### 4.1 `references` no documento

```json
{"format": "tare.tools.tune.dsl", "version": 1,
 "references": {"clash": "refs/clash.wav", "roar": "refs/roar.wav"},
 "sounds": {"clash": {"use": "hit"}, "roar": {"creature": "monster", "size": 0.8}}}
```

- `validate`: chave conhecida no topo; cada chave é nome de som existente (`E_REFERENCE` com sugestões), valor via
  `asset()` (mesmas raízes de hoje). `reference` (documento inteiro) continua valendo como fallback.
- `compile_document(name)`: `references.get(name) or reference` → o bloco de `compiler.py:563` como está (mesmos
  `arrays["reference"]`, `manifest["reference"]`, dependência sha256). `workflow._dependencies` idem. Studio, inspect e
  guardas não mudam.
- Não há `dsl edit` para `/references/x`: trocar a referência é editar o JSON e revisar de novo (a guarda já recusa
  o bundle velho).

### 4.2 `review`: bloco `reference`

Detalhado (só quando o som tem referência):

```json
"reference": {"file": "refs/clash.wav", "pcm_id": "…", "sample_rate": 44100, "channels": 2, "basis": "…",
  "noise_floor_db": -48.2, "clipped": 0,
  "measures": {
    "active_s":   {"reference": 0.37, "sound": 0.42, "delta": 0.05, "status": "measured"},
    "attack_ms":  {"reference": 9, "sound": 12, "delta": 3, "status": "measured"},
    "end_60_s":   {"reference": null, "sound": 0.61, "status": "not_measurable", "reason": "reference noise floor -48 dB"},
    "centroid_hz":{"reference": 2400, "sound": 1850, "delta_semitones": -4.5, "status": "measured"},
    "f0":         {"status": "unvoiced", "voiced": [0.03, 0.02]},
    "env_db":     {"mean_abs_delta": 6.1, "louder_bands": 12, "quieter_bands": 20, "largest": {"hz": [2000, 2600], "delta_db": 9.0}},
    "loud_db":    {"mean_abs_delta": 3.2}},
  "checks": [{"check": "reference:centroid_hz", "status": "failed", "actual": -4.5, "expected": {"semitones": 3}}]}
```

Compacto (`review_summary`): `"ref": {"active_s": [0.37, 0.42], "attack_ms": [9, 12], "centroid_hz": [2400, 1850],
"f0_hz": "unvoiced", "env_db": 6.1, "status": "failed:centroid_hz"}`; ordem fixa `[referência, som]`, documentada em
`dsl help reference`. Custo medido: ~48 tokens, só com referência. `coverage.reference`: `measured` | `absent`.
`changes` (com `--previous`) não ganha campo novo: `ref` aparece nas duas observações e o agente vê se aproximou.

`review` de bundle (sem regenerar) usa `arrays["reference"]` do próprio bundle: funciona offline e bate com o que o
studio toca.

### 4.3 Tolerâncias em `checks.json`

```json
{"format": "tare.tools.tune.checks", "version": 1,
 "reference": {"active_s": {"ratio": 1.2}, "attack_ms": {"max_delta": 10},
               "centroid_hz": {"semitones": 3}, "f0_hz": {"semitones": 2}, "env_db": {"max": 8}}}
```

- Uma chave por medida, uma unidade natural cada; `ratio` = som/ref dentro de [1/r, r]. Sem `env_db` no exemplo
  padrão: com gravação real o piso é 4–8 dB e o número confunde mais do que guia.
- Resultado por linha: `reference:MEDIDA` com `passed`/`failed`/`not_run` (+`reason`). Som sem referência ou medida
  `not_measurable`/`unvoiced` → `not_run` → o review sai com 5 e o edit não grava, **como já acontece** com
  capabilities sem registro. É a regra do pxl: "não checado" ≠ "passou". Decisão 2 pergunta se o usuário quer isso.
- Continua check técnico: a linha de `basis` e o `perceptual_quality: not_run` ficam; nenhuma resposta diz "soa como
  a referência".

### 4.4 `CURATE compare --reference ref.wav`

`compare_bundles(name, *bundles, reference=None)`: cartão `REF` primeiro (arquivo copiado para a rodada, como
`Group.add` já faz), `group.reference = "REF"`, `targets` = medidas do REF; todos os cartões ganham `metrics`
`{duration_s, peak_dbfs, rms_dbfs, active_s, attack_ms, centroid_hz, f0_hz}` da mesma `measures()`. `--reference` implica
`--open` (em rodada cega a página esconde a referência). `answers --json` já devolve `segments` com `bundle` ou `file`:
REF aparece com o caminho do WAV. Sem mudança no HTML.

### 4.5 `TUNE study FILE [--domain sfx|creature|speech|music] [--json]`

Camada fina sobre `inspect_audio` + `measures()`; `tune.study/1`:

```json
{"schema": "tune.study/1", "file": "ref.wav", "kind": {"voiced": 0.03, "tonal": false, "loop": false, "channels": 2,
   "sample_rate": 44100, "noise_floor_db": -48, "clipped": 0},
 "facts": {"active_s": 0.37, "attack_ms": 9, "end_60_s": null, "centroid_hz": 2400, "f0": {"status": "unvoiced"},
           "env_db": [0, -3, …], "loud_db": [-18, -2, 0, …], "segments": 1},
 "in_tune": [
   {"use": "sfx", "why": "unvoiced, one burst of 0.37 s with a 9 ms attack"},
   {"field": "knobs.length", "value": "active_s / your render's active_s", "why": "length stretches the whole sound, pitch kept"},
   {"field": "knobs.brightness", "direction": "+ if your render's centroid is below 2400 Hz", "why": "centroid; direction only"},
   {"cannot": "kind, style or event: pick from the catalog by ear, or --search sfx:KIND"}],
 "basis": "…"}
```

- `in_tune` por domínio (§3): fala → `speaker.pitch` em Hz e `range` em st, taxa em sílabas/s; criatura → `size`
  pela F0, `call` pelas sílabas; música → só `active_s` e loop, "bpm e tom: não medidos".
- Texto sem `--json`: seções curtas (KIND, FACTS, IN TUNE), como o pxl.
- `--search sfx:KIND` / `--search creature` (fase opcional): renderiza os eventos×estilos de um kind, ou roda
  `designer._search` com score `-distance`, e lista os 3 mais próximos com a distância e **o que a distância compara**.
  Bounded (um kind; ~20–40 renders; criatura ~2 min CPU). Nunca CLAP aqui.

## 5. SKILL.md

Uma regra nova (~450 caracteres), no passo 2 ou 3 do workflow:

> **Given a recording to match:** `TUNE study ref.wav --json` says what it is made of and what in tune makes each part.
> Put it in the bank's `"references": {"clash": "refs/clash.wav"}`; `review` then shows `ref` as `[recording, sound]`
> pairs and `--checks` can hold tolerances (`TUNE dsl help reference --json`). `CURATE compare … --reference ref.wav`
> puts the recording beside the candidates. Numbers aim; the ear decides. Recordings and bundles stay out of anything you ship.

Cortes equivalentes (escolher ~450 chars): a linha "Ops: every op with its meaning…" de Essentials (a tabela de lookup
já cobre); a linha `bestiary.json` de Examples; a frase do `studio` no passo 5 encurtada; "`--sr 48000`: the rate" já
está em Habits. `tests/test_skill.py` continua cobrando: `TUNE study` e `dsl help reference` passam a ser conferidos
automaticamente (comando existe, flags no `--help`, tópico no `HELP`).

Docs mínimos: seção "Hold a sound against a recording" em `docs/dsl-review.md` (+ `pt-BR/revisao-dsl.md`); a chave
`references` em `docs/dsl.md` (+ pt-BR); uma linha em README "Listening curation" para `--reference`; `dsl help reference`
no `HELP` (usage, meaning, ordem `[reference, sound]`, regras: status por medida, `not_run` falha, bundles carregam o
PCM, nada diz que soa igual). Rodar `tools/dsl_reference.py --check` se o vocabulário gerado incluir chaves do topo.

## 6. Fases, aceite e testes

Testes sempre com sinais sintéticos: um tom decaindo + rajada de ruído (impacto), um "roar" de `creature` renderizado
pelo próprio tune a 16 kHz, uma frase `say` curta, e versões **degradadas** da mesma coisa (ruído a −45 dB, cauda de
sala por convolução com ruído decaindo, reamostrada a 44,1 kHz, estéreo) para provar o alinhamento.

### Fase 0: `analysis.measures()` (MVP)
Uma função; `end_60_s` do render tem de bater com `len(trim_tail(y)) / sr` (±1 janela). Testes: sinal contra ele
mesmo → deltas 0; versão degradada → `active_s` e `centroid_hz` dentro de 10 % / 1 st, `end_60_s = not_measurable`
com razão, `noise_floor_db` ≈ −45; estéreo → `basis` diz "mono mean"; 60 ms → não quebra; 25 s → `f0.status = skipped`;
mesma entrada, mesmos números (determinismo).
Aceite: `pytest tests/test_analysis.py --basetemp output/pt` verde; < 0,3 s por chamada em sons ≤ 3 s.

### Fase 1: `references` (MVP)
`validate` (+ nome inexistente → `E_REFERENCE` com sugestões; fora das raízes → `E_ASSET`), `compile_document`,
`workflow._dependencies`. Testes (estender `tests/test_dsl_review.py::test_reference_dependency…`): o som certo recebe o
PCM certo; alterar o WAV de `roar` invalida só bundles de `roar`; `freeze --format wav` e `export` não carregam
`reference`; `dsl check` aceita.
Aceite: exemplo com duas referências sintéticas (geradas no teste, não commitadas) passa em `check` e `review`.

### Fase 2: bloco `reference` em `review` (MVP)
`review_data.reference_facts(captured)` → `_report` → `review_summary`. Testes: som cuja referência é o próprio render
→ todos `measured`, deltas 0; referência deslocada (−3 st de brilho, 1,3× mais longa) → sinais certos; sem referência →
chave ausente e `coverage.reference = absent`; compacto cresce menos de 300 caracteres (sem tiktoken no teste);
`tests/test_dsl_review_responses.py` cobre a forma `[ref, som]`.
Aceite: `dsl review … --response compact --json` mostra `ref` só com referência; `dsl help reference --json` existe.

### Fase 3: tolerâncias (MVP)
`check_spec` aceita `reference`; `run_checks` gera `reference:MEDIDA`. Testes: passa/falha/`not_run` (sem referência,
`unvoiced`, `not_measurable`); CLI sai com 5; `edit` com candidato fora da tolerância não grava e devolve `details`;
checks herdados do bundle continuam.
Aceite: `examples/dsl-review.checks.json` ganha o bloco `reference` comentado em docs; `checks` do manifesto guardam a spec.

### Fase 4: `CURATE compare --reference` (MVP)
Testes em `tests/test_curate.py`, via manifesto e servidor em thread (como hoje, sem navegador): `REF` é
`g["reference"]`, `targets` preenchido, `metrics` em todos os cartões, `match` mantido, rodada aberta mesmo sem `--open`,
`answers --json` mapeia REF ao arquivo.
Aceite: `python tools/curate.py compare clash A B --reference ref.wav --root output/rounds` imprime o manifesto.

### Fase 5: `TUNE study` (depois do MVP)
`cli.py` + `study.py` (~80 linhas); `--search` opcional e separado. Testes: impacto sintético → `in_tune` sugere `sfx`
e `knobs.length`; `say` renderizado → `speaker.pitch` ≈ pitch pedido (±5 %); `--json` validado; `--search sfx:ui`
encontra o próprio evento renderizado no top 3.
Aceite: `TUNE study tests/…` em < 2 s sem `--search`.

### Fase 6: skill + docs (MVP)
§5. Aceite: `tests/test_skill.py` verde, `< 11000`.

### Fase 7: avaliação (só com aprovação e orçamento)
§7.

## 7. Avaliação: o loop ajuda o agente?

Sem gravações de jogo: os **alvos são renders do próprio tune, escondidos** (o agente recebe só o WAV, como se fosse
gravação), em duas versões: limpa e degradada (sala + ruído −45 dB + 44,1 kHz estéreo).

Tarefas (as três do piloto de 2026-11-01, com alvo):
1. SFX: "faça um `clash` como este" (alvo: `blade steel clash` com `brightness 0.6`, `length 1.4`, `species 3`).
2. Criatura: "um rugido como este" (alvo: `monster`, `size 0.8`, `aggression 0.7`, `call attack`).
3. Fala: "uma fala pt-BR com esta voz" (alvo: `natural:pt/dora`, `pitch 190`, `rate 1.1`).

Braços, uma rodada cada, mesmo modelo e esforço, sessões novas: **A** skill atual + WAV + `inspect` (hoje);
**B** skill com a regra + `references` + `review` com `ref` + checks de tolerância + `curate --reference`.

Medir (nenhum número exige gravação de jogo):
- **Aproximação:** `measures()` do render final contra o alvo (`active_s`, `centroid_hz`, `f0`, `env_db`) e, por edit,
  se a distância caiu (prova de que os números são acionáveis). Como o braço B otimiza as medidas que medimos, juiz
  **independente**: ABX cego na página de curadoria com o usuário ("qual está mais perto de REF?") e, se houver
  orçamento, o CLAP juiz (`larger_clap_general`) uma vez, via `gpu run --task tune-eval` no `aaaaa`.
- **Custo:** tokens de conteúdo por tarefa (transcripts, `o200k_base`, como em `docs/dsl-review-token-costs.md`),
  turnos, tempo de parede.
- **Uso do loop:** o agente chamou `study`/`references`/`--reference`? (sonda de disparo).
- **Falsa confiança:** contagem de frases do agente que afirmam semelhança de ouvido sem rodada; meta: zero.
- **Reportar o que não foi medido:** n = 1 por célula; sem claim estatístico; `FEEDBACK.md` lido e corrigido.

## 8. Riscos

| Risco | Mitigação |
|---|---|
| O agente persegue centróide e duração e piora o som de ouvido | Tolerâncias frouxas por padrão, `env_db` fora dos checks padrão, regra "numbers aim; the ear decides", rodada sempre oferecida |
| Sala/microfone: `env_db` nunca abaixo de 4–8 dB com gravação real | Dito no `basis` e na help; `env_db` é informativo |
| Piso de ruído inviabiliza `end_60_s` | `status: not_measurable` + razão; primário é −40 dB |
| `not_run` falha o review (exit 5) para sons sem referência num checks compartilhado | Documentado; checks são herdados por bundle (por som na prática); decisão 2 |
| Bundle carrega o PCM da gravação | Regra em skill/docs; teste de `freeze`/`export`; `output/` ignorado |
| Custo de compilação em sons longos | F0 só ≤ 20 s; espectro em rfft único; medido 76 ms/1,5 s |
| Token: resposta compacta cresce | +48 tokens, só com referência; nada no compacto sem referência |
| SKILL.md estoura 11.000 | Cortes de §5; teste cobra |
| YIN em SFX dá F0 espúria | `voiced < 0,2` → `unvoiced`; `aper > 0,5` → `unreliable` |
| `--search` demora ou vira "o tune escolheu" | Um kind por vez, top 3 com a distância e o que ela compara; nunca padrão |
| Classificador do Claude Code bloqueia `curate.py compare` (visto no plano da skill) | Decisão já aberta lá; não muda aqui |

## 9. Decisões do usuário

| Decisão | Recomendação |
|---|---|
| 1. Onde fica a referência por som: mapa `references` no topo, ou chave dentro de cada som | Mapa no topo (menor diff; não toca o vocabulário dos ops) |
| 2. Checks de referência num som sem referência (ou medida impossível): `not_run` que falha (exit 5) ou ignorar | `not_run` (coerente com capabilities e com o pxl: "não checado" não é "passou") |
| 3. Tolerâncias padrão no exemplo (`active_s` 1,2×, `centroid` 3 st, `f0` 2 st, `attack` 10 ms) ou nenhuma | Essas, sem `env_db` |
| 4. `--reference` em `curate` abre a rodada (nomes visíveis) | Sim; cego com referência exigiria mudar a página |
| 5. Bundle continua carregando o PCM da referência (hoje) ou só hash + medidas | Continuar (review offline e studio tocam); regra de não compartilhar bundle |
| 6. `study --search` agora ou depois | Depois (fase 5b), só DSP |
| 7. Quais ~450 caracteres cortar do SKILL.md | Linha "Ops" de Essentials + `bestiary.json` + encurtar `studio` |
| 8. Avaliação (fase 7): rodar, e o usuário ouve o ABX final | Só com aprovação; com o ABX, senão a aproximação fica só nos nossos números |
| 9. Fala: CER/Whisper | Ferramenta de desenvolvedor; opcional `--wav/--text` depois; nunca em `review` |

## 10. O que não construir (e por quê)

- **CER no `review`**: extra pesado, quase sempre `not_run`, e Whisper recompensa palavras plausíveis.
- **CLAP no `study`/`review`**: não instalado, GPU, não determinístico entre modelos; `match`/`design` continuam como estão.
- **Tempo e tom de música**: DSP novo sem consumidor claro no DSL (`music` é por seed).
- **`--fix` de tolerância**: só `length` e `speaker.pitch` seriam honestos; `in_tune` já dá o valor e `dsl edit` o aplica.
- **Mudança na página de curadoria**: a diferença, o espectro médio e a tabela com alvo já existem.
- **Folha PNG do `study`**: a página de curadoria mostra mais; matplotlib é extra.
- **Comparação de pico/RMS/fator de crista com a gravação**: masterização, não alvo.
- **Contorno de F0 no compacto**: 16 números por turno sem decisão que dependa deles.
