# Plano: tare.tools.tune como skill de agente

1º de novembro de 2026. Revisão crítica feita por um agente Fable (esforço xhigh), somente leitura e sem inferência,
sobre o plano inicial da sessão principal. Este arquivo é o plano de trabalho, em português; a skill em si será em
inglês. Fatos conferidos pela sessão principal: porta padrão 8765 compartilhada por `studio` e `curate serve`;
reescrita de `/with/power` pelo Git Bash (resolvida por `MSYS_NO_PATHCONV=1`); o README cita um histórico git que esta
pasta não tem.

## 0. Fatos medidos (o200k_base)

| Texto / saída | tokens |
|---|---:|
| `README.md` | 12.370 |
| `docs/dsl.md` / `dsl-review.md` / `dsl-agent.md` / `authoring.md` | 4.277 / 2.348 / 964 / 3.263 |
| `docs/architecture.md` | 33.195 |
| `docs/tactics-sounds.md` / `rpg-sounds.md` | 3.338 / 703 |
| `docs/dsl-reference.json` | 65.401 |
| `SKILL.md` do pxl (193 linhas, 13.791 chars) | 4.306 |
| `dsl review --response compact --json` / detalhado | 155 / 363 |
| `dsl describe BUNDLE --fields power --json` | 200 |
| `dsl help review --json` | 110 |
| `TUNE --help` / `TUNE dsl --help` | 460 / 162 |
| `TUNE list` / `voices` / `sounds` / `sounds --knobs` | 213 / 361 / 1.948 / 2.236 |
| `dsl catalog --domain sfx --fields name,styles,events --limit 100 --json` | 1.213 |
| `dsl catalog --domain op --fields name,meaning --limit 100 --json` | 574 |
| `dsl catalog --domain op --name creature --fields name,example,fields --json` | 397 |

**Conclusão que muda o plano:** as respostas do CLI já são pequenas (100–400 tokens). O custo por turno vem do próprio
`SKILL.md`, carregado em toda sessão que dispara, e de leituras de docs inteiros. Falta texto escrito para agente, não
um leitor de seções.

Outros fatos:

- **Git Bash reescreve pointers:** `--set /with/power 0.65` chega como `C:/Program Files/Git/with/power`.
  `MSYS_NO_PATHCONV=1` resolve; `//with/power` não. Afeta `--set`, `--refine`, `--pointer`, `/params/x/default`.
- Em `examples/dsl-bank.tune.json` o caminho é `/with/power` (o som é um `use`); `/power` dá `E_FIELD`. O bloco
  "Ask a listener" de `docs/dsl-review.md` usa `/power`, que vale para o banco do fim do doc (sfx direto) mas é uma
  armadilha para quem copia para o exemplo do repo.
- `dsl review` exige `-o`. `dsl check FILE --json` valida todos os sons sem síntese; `--expand` exige `--name`.
- `tools/curate.py`: `--root` padrão fora do projeto (`~/Documents/tare-referencias/...`); `serve` abre o navegador
  sozinho salvo `--no-open`; UI e mensagens em português.
- Não há `uv.lock`. O `.venv` tem extras instalados via pip (tiktoken, soundfile, matplotlib, pytest, ruff).
  `uv run --project` criaria um lock e faria `uv sync` exato, removendo esses extras.
- O pacote está instalado como editable no `.venv`, então `.venv/Scripts/python -m tare.tools.tune` funciona de
  qualquer cwd, inclusive pela junction.
- `~/.codex/skills` e `~/.gemini/config` existem na máquina.
- `TUNE dsl --help` não tem texto de ajuda para 9 subcomandos (`catalog, check, query, expand, patch, capabilities,
  migrate, freeze, variants`).
- O classificador do Claude Code bloqueou `python tools/curate.py compare ...` como "Expose Local Services" (o
  subcomando não abre socket). Um agente em auto mode pode travar ali.
- Um template `.tune.json` com 7 formas (use/with, sfx+era+knobs, creature, say+speaker+emotion, emote, music) passou
  em `dsl check` e em `--expand --name` para cada som (seção 3).

## 1. Crítica do plano inicial

| # | Gravidade | Problema | Correção |
|---|---|---|---|
| 1 | alta | O leitor de seções é a abstração errada: o `help` do pxl funciona porque os guias dele foram escritos em seções para agentes; os docs do tune são prosa para humanos, com ressalvas de medição | Não escrever leitor. Acrescentar o tópico `listener` (e talvez `export`) ao dict `HELP` existente; usar `dsl catalog` como help por nome; a tabela de lookup do SKILL.md aponta para os dois |
| 2 | alta | Sem `MSYS_NO_PATHCONV`, todo `dsl edit --set /path` falha no Bash tool | Launcher no SKILL.md já com o prefixo, e uma linha explicando |
| 3 | alta | `uv run --project` desinstala extras do `.venv` | Um launcher só: `.venv/Scripts/python` |
| 4 | alta | A validação proposta só existia com inferência | `tests/test_skill.py`, no estilo do `test/docs.test.ts` do pxl (fase 3) |
| 5 | média | O equivalente ao `shot` do pxl é `dsl edit` (que já devolve o delta contra a observação), não `review --previous` | Loop: observar uma vez com `review`; cada `edit` é a próxima observação |
| 6 | média | Faltavam peças do pxl: template, essentials, tabela de lookup, índice de exemplos, hábitos, tarefa grande, regras de custo, `FEEDBACK.md` | Todas no SKILL.md da seção 3 |
| 7 | média | Comandos rápidos | Incluir, com regra de corte: som único e pronto → comando rápido; iterar, comparar de ouvido ou entregar conjunto → `.tune.json` + `review` (`curate compare` só aceita bundles) |
| 8 | média | `studio` e `curate serve` colidem na porta 8765 | `studio --port 8766` na skill |
| 9 | média | Classificador bloqueia `curate.py compare` | Decisão do usuário: regra de permissão no projeto de trabalho, ou aprovar na hora. Não vai na skill |
| 10 | média | Junction sobre repo sem git | `git init` + commit base antes; procurar antes o clone original (o README cita histórico git); sem push até decidir LFS para os ~53 MB de bancos de voz; regra: nunca `dsl edit` um exemplo dentro da pasta da skill |
| 11 | baixa | Descrição vaga | Listar o que o usuário diz e excluir o que não é (seção 3) |
| 12 | baixa | `dsl --help` sem textos em 9 subcomandos | 9 strings `help=` em `dsl/cli.py` (opcional) |
| 13 | baixa | `curate serve` abre o navegador | Regra: background, parar no fim, nunca headless |
| 14 | baixa | `dsl edit` reescreve o arquivo como JSON canônico | Regra: reler antes de editar à mão |
| 15 | baixa | Exemplos a 16 kHz | Hábito: autorar na taxa de entrega (48000) |

Ordem corrigida: git → SKILL.md + tópico `listener` → teste → junction → docs (uma frase) → avaliação ao vivo
(opcional, com aprovação).

## 2. Análise dos textos

| Fonte | Veredito |
|---|---|
| `README.md`: abertura, arquétipos, tabela de sfx, era/dry/knobs, vocalizações, emoções, vozes, casting, música, bestiário, CLI | Não copiar. Tudo sai de `TUNE list/voices/sounds/music --help` e `dsl catalog`; a skill lista os comandos com o custo |
| `README.md`: história, inteligibilidade, CLAP, Gen 1, desenvolvimento, créditos | Só humanos; nunca linkar da skill |
| `README.md` §Authoring and diagnostics | Trocar por uma frase: "For AI agents, the skill is [SKILL.md](SKILL.md)." (mesma em `README.pt-BR.md`) |
| `README.md` §Listening curation | Manter; a essência vai para a skill e para `dsl help listener` |
| `docs/dsl-review.md` | Fonte principal dos passos 3–5. Fora do caminho do agente: o parágrafo final de ressalvas e os links de medição. Corrigir em "Ask a listener": "use the `path` that `describe` returned (`/with/power` on a `use`)" (espelhar em `pt-BR/revisao-dsl.md`) |
| `docs/dsl-agent.md` | Depois: trocar a abertura por um ponteiro para o SKILL.md e cortar as ressalvas (com o par pt-BR). A skill não linka |
| `docs/dsl.md` | Referência humana. Padronizar o import em `builders as t` (hoje há dois estilos) |
| `docs/authoring.md` | Humanos; o player vira uma linha na skill |
| `docs/dsl-efficiency.md`, `dsl-review-token-costs.md`, `dsl-benchmarks.md`, implementação, aceitação, `audits/`, `plans/`, JSONs de medição | Humanos; nunca linkar. Duas regras escondidas ali viram linhas da skill: avançar a observação só depois de um edit aplicado, nunca repetir um conflito com revisão nova; compacto na rotina, detalhado quando a decisão exigir |
| `docs/architecture.md` (33k), `docs/dsl-reference.json` (65k) | Proibir explicitamente na skill; `dsl catalog` é o índice |
| `docs/tactics-sounds.md` | Uma linha de lookup ("áudio de um tactics RPG inteiro": ler inteiro) |
| `docs/rpg-sounds.md` | Redundante com `TUNE sounds` |
| `docs/README.md` | +1 linha apontando o SKILL.md |
| `examples/dsl-*.tune.json`, `dsl-review.checks.json`, `dsl_builder.py` | Manter e indexar na skill |
| `examples/bestiary.json`, `sound-bank.json`, `authoring.json` | Uma linha (`bake`, `dsl migrate`) |
| `workflow_cli.py` `HELP` | Acrescentar `listener` |
| `docs/pt-BR/*` | Mudar só o que a mudança em inglês tocar |

Duplicação: a frase "review → describe → edit, o bundle é a observação" aparece em 6 lugares. Depois da skill, o
SKILL.md é a fonte para agentes e os docs apontam para ele. Contradições: dois estilos de import dos builders; `/power`
vs `/with/power`; o README manda começar pelo `studio` e `dsl-review.md` pelo `review` (a skill decide: `review`).

## 3. Estrutura da skill

| Arquivo | Alvo | Papel |
|---|---|---|
| `SKILL.md` (raiz) | ≤ 11.000 chars (~2,5k tokens) | Mapa: workflow, lookup, template, essentials, exemplos, hábitos, feedback |
| `src/tare/tools/tune/dsl/workflow_cli.py` | +~15 linhas | Tópico `listener` no `HELP` |
| `tests/test_skill.py` | ~60 linhas | Mantém a skill honesta |
| `FEEDBACK.md` | criado pelo agente, fora do git | Como no pxl |

Sem `reference.md` próprio: seria a terceira cópia do registro, que `dsl catalog` já consulta sem desatualizar.

Frontmatter:

```yaml
---
name: tune-game-audio
description: Makes game audio with tare.tools.tune, a deterministic procedural synthesizer (Python, no AI at runtime): creature cries and calls, NPC speech lines (Brazilian Portuguese and English) and wordless barks (grunts, laughs, gasps), sound effects (weapons, footsteps, doors, chests, UI, spells, ambience loops), music jingles and loops; exported as WAV, OGG sprite banks, Voice JSON for Godot or MIDI. Use when asked to create, tune, compare or iterate on sounds, voices, SFX or music cues for a game. Not for editing existing recordings, music production in a DAW, or pixel art.
---
```

### Rascunho do SKILL.md

`TUNE` = `MSYS_NO_PATHCONV=1 <skill dir>/.venv/Scripts/python -m tare.tools.tune` (no PowerShell, sem o prefixo).
`CURATE` = `<skill dir>/.venv/Scripts/python <skill dir>/tools/curate.py`. Escrever sempre no projeto em que se
trabalha (`output/`), nunca na pasta da skill; copiar um exemplo antes de editá-lo.

**Workflow**

1. Um som, sem iteração: comando rápido.
   `TUNE sfx blade steel --event clash --species excalibur --dry -o clash.wav`;
   `TUNE say "Hello there!" --lang en --voice npc:7 -o line.wav` (pt-BR: `--lang pt --voice natural:f`);
   `TUNE render monster --species ogre --size .9 --aggression .8 --call attack -o ogre.wav`;
   `TUNE music victory --seed 3 -o victory.wav`. Nomes: `TUNE sounds` (~2k), `TUNE list`, `TUNE voices`,
   `TUNE music --help`. `--take N` outra tomada; `--sr 48000` a taxa.
2. Algo que será iterado, comparado de ouvido ou entregue em conjunto: `.tune.json` no projeto (template abaixo).
   `TUNE dsl check bank.tune.json --json` valida tudo sem renderizar.
3. Olhar com uma chamada: `TUNE dsl review bank.tune.json --name clash -o output/reviews --response compact --json`
   → bundle (a observação que todo edit exige), `audio.wav`, duração, pico, rms, checks. `--checks checks.json`
   (`TUNE dsl help checks --json`).
4. Achar os controles e corrigir tudo o que uma olhada mostrou numa chamada só:
   `TUNE dsl describe BUNDLE --fields power,knobs --json` (`--find WORD` lista candidatos), depois
   `TUNE dsl edit bank.tune.json --from-bundle BUNDLE -o output/reviews --set /with/power 0.65 --set /with/knobs/ring 0.6 --response compact --json`.
   Usar o caminho que o `describe` devolveu: `/with/NAME` num `use`, `/NAME` numa receita direta,
   `/params/NAME/default` numa definição (valida todos os sons que a usam, renderiza só este). O resultado é a
   próxima observação. Bundle velho falha (exit 3): revisar de novo, nunca repetir com revisão nova.
   `--refine /lowpass 2400` mantém a receita (`--layer n0/p0` para uma camada). Adicionar/remover sons ou renomear
   definição: editar o JSON (depois de um `dsl edit` o arquivo é JSON canônico: reler antes), depois `review`.
5. O ouvido decide. Checks não julgam timbre (`perceptual_quality` sempre `not_run`): dizer o que foi medido, nunca
   que soa bem. Para escolher de ouvido: 2–9 candidatos com `--dry-run` a partir de um bundle, depois
   `CURATE compare power A B C --open --question "Which sounds firmer?" --root output/rounds`,
   `CURATE serve --root output/rounds` (background; abre o navegador do usuário e bloqueia; passar a URL, parar no
   fim; nunca headless), `CURATE answers power --json --root output/rounds`. Confirmar o escolhido repetindo o edit a
   partir de A (PCM idêntico ao ouvido). Para o usuário acompanhar: `TUNE studio bank.tune.json -o output/studio --port 8766`
   em background.
6. Entregar: `TUNE export bank.tune.json -o output/sprites --ogg`;
   `TUNE dsl freeze bank.tune.json --name clash --format voice -o clash.voice.json` (Godot/nativo; não cobre fala,
   vocalizações, chip nem cues, que vão como PCM); `TUNE midi bank.tune.json -o theme.mid` (só scores);
   `TUNE dsl capabilities bank.tune.json --name X --json`. Bestiário em pacotes WAV: `TUNE bake bestiary.json -o baked`.

**Looking things up.** O que se lê cedo é pago de novo em todo turno: pedir um nome, nunca um arquivo inteiro.
`TUNE dsl catalog --domain D [--name N] --fields F --json` é o vocabulário; `TUNE dsl help TOPIC --json` as regras
do loop (review, describe, edit, checks, builders, listener). Nunca abrir `docs/dsl-reference.json` nem
`docs/architecture.md`.

| Fazendo | Ler |
|---|---|
| arma, porta, baú, item, UI, magia, passo, ambiente | `--domain sfx --name ui --fields name,styles,events,knobs` (~300); todos os 34: `--domain sfx --fields name,styles,events --limit 100` (~1,2k) |
| grito de criatura | `--domain op --name creature --fields fields` (~400); arquétipos `TUNE list` (~200) |
| fala de NPC | `--domain op --name say`; voz `--domain op --name speaker`; presets `TUNE voices` (~360); emoções `[happy] ...` |
| grunhido, risada, suspiro | `--domain op --name emote` (tipos e estilos) |
| jingle ou loop por seed | `--domain music --fields name`; `--domain op --name music` |
| frase composta | `examples/dsl-music.tune.json`; `--domain transform`; `--domain instrument --fields name` |
| camadas de síntese crua | `examples/dsl-primitives.tune.json`; `--domain layer --name modal` |
| família parametrizada e variantes | `TUNE dsl help builders --json`; `TUNE dsl variants ...` |
| a lista de sons de um tactics RPG | `docs/tactics-sounds.md`, inteiro (~3,3k) |

**Template** (validado com `dsl check` e `--expand --name` em cada som):

```json
{
  "format": "tare.tools.tune.dsl", "version": 1,
  "context": {"sample_rate": 48000},
  "defs": {
    "hit": {"params": {"power": {"type": "number", "min": 0, "max": 1, "default": 0.5}},
            "body": {"sfx": "blade", "style": "steel", "event": "clash", "species": "excalibur",
                     "power": {"param": "power"}, "dry": true}}
  },
  "sounds": {
    "clash": {"use": "hit"},
    "clash_heavy": {"use": "hit", "with": {"power": 0.9}},
    "confirm": {"sfx": "ui", "style": "crystal", "event": "confirm", "era": "hd", "dry": true, "knobs": {"register": -1}},
    "wolf_attack": {"creature": "mammal", "species": "wolf", "size": 0.45, "aggression": 0.5, "call": "attack", "take": 2},
    "greet": {"say": "Welcome to the forge, traveler!", "lang": "en", "speaker": {"speaker": "deep"}, "emotion": "happy"},
    "hurt": {"emote": "hurt", "style": "grunt", "speaker": {"speaker": "default", "pitch": 135}, "take": 1},
    "fanfare": {"music": "victory", "seed": 3}
  }
}
```

**Essentials** (uma linha cada): ops (`sfx`, `creature`, `say`, `emote`, `speaker`, `music`, `score`, `voice`,
`spec`, `audio`, `fm`, `rest`, `notes`, `pattern`, `chord`, `degrees`, `seq`, `repeat`, `overlay`, `mix`,
`instrument`, `use`/`with`, `edit`); reuso por `defs` com `params` tipados e `{"param": "name"}`, sem aritmética,
imports ou recursão; unidades (segundos e Hz nas primitivas; `"250ms"`, `"1/3b"`, `"2bar"`; `context` com
`sample_rate`, `bpm`, `meter`); identidade (`species` é este objeto, `take` outra repetição, `individual` e `genes`
dirigem uma criatura; ids e nomes de definição nunca semeiam, o `name` de uma faixa sim); mesma entrada, mesmas
amostras; Python `from tare.tools.tune.dsl import builders as t`; limites (180 s por som, 1 MiB de fonte, 256 sons,
64 faixas; erros em JSON com `code`, `pointer`; exit 2 entrada, 3 velho, 4 build, 5 checks).

**Examples:** `dsl-bank.tune.json` (definição com `power` e dois `use`), `dsl-music.tune.json` (motivo, `repeat`,
`transpose`), `dsl-primitives.tune.json` (`syllable` + `modal` + `noise`), `dsl-review.checks.json`,
`dsl_builder.py`, `bestiary.json` (`bake`). Rodar `review`/`edit` numa cópia: `edit` reescreve a fonte.

**Habits:** autorar a 48000 (os exemplos usam 16000 para rodar rápido); `dry: true` quando o jogo põe reverb por
mapa; `era` para casar a geração; variar dentro da receita (`knobs`, `power`, `size`, `take`) antes de trocar de
estilo; vozes naturais só em pt-BR (`natural:pt/alex`, `natural:pt/dora`), em inglês caem no formant: avisar o
usuário; um personagem, um `speaker`; uma observação, todos os seus edits, uma chamada; compacto na rotina.

**When tune gets in your way:** uma linha em `FEEDBACK.md` na pasta da skill (data, tipo de som, o que aconteceu no
tune, o que teria ajudado); só o lado do tune.

Primeiro turno típico: SKILL.md (2,5k) + uma consulta ao catálogo (0,3–1,2k) + um `review` compacto (0,15k) < 4k tokens.

## 4. Fases

### Fase 0: pré-requisitos (MVP)
Procurar o clone original com `.git` (o README cita o histórico); se existir, aproveitar o `.git` dele. Senão,
`git init` + commit base (os bancos de voz entram; sem push). `.gitignore`: `FEEDBACK.md`.
Aceite: `git status` limpo, um commit.

### Fase 1: `SKILL.md` (MVP)
Conteúdo da seção 3, traduzido em instruções imperativas em inglês. Uma ideia por bullet; todo comando copiável e
verificado; nenhum número de benchmark nem ressalva; linkar só `docs/tactics-sounds.md` e `examples/`.
Aceite: < 11.000 chars; frontmatter com `name`/`description`; passa na fase 3.

### Fase 2: `dsl help listener` (MVP; `export` opcional)
No dict `HELP` de `workflow_cli.py`, formato `tune.help/1` já existente:
- `usage`: `tools/curate.py compare NAME B1 B2 [..B9] --root ROUNDS [--open] [--question TEXT] [--task SPEC]; serve --root ROUNDS; answers NAME --json --root ROUNDS`
- `meaning`: put dry-run candidates from one observation in front of a human ear; read the pick as data keyed by
  label with each bundle path.
- `rules`: candidatos são `--dry-run` de um bundle, confirmar repetindo o edit a partir dele (PCM idêntico); 2
  bundles viram ABX cego, 3–9 pick + nota 1–5, cego salvo `--open`; na rodada cega a página numera os cartões pela
  posição embaralhada (#1, #2…) e só mostra A, B, C depois de "revelar nomes", então a escolha vem de
  `answers --json`, nunca de um número citado no chat; `serve` abre o navegador e bloqueia (background,
  parar depois, nunca headless); sempre `--root`; `--keep-levels` quando o nível (força, volume) é o que se julga.
- Opcional: 9 strings `help=` em `dsl/cli.py`.
Teste: um assert em `tests/test_dsl_review.py::test_cli_help_review_describe_and_atomic_batch`.
Aceite: `dsl help --json` lista 6 tópicos.

### Fase 3: `tests/test_skill.py` (MVP, sem inferência)
1. Frontmatter (`name: tune-game-audio`, `description:`), `len < 11000`.
2. Todo comando citado (`TUNE ...`, `CURATE ...`): o subcomando existe e cada `--flag` está no `--help` dele
   (argparse via `main([..., "--help"])` com `capsys`; `curate.main` importado como em `tests/test_curate.py`).
3. Todo `TUNE dsl help X` citado existe em `HELP`; todo `--domain D` está nas `choices`.
4. O bloco Template passa em `dsl check` (7 sons) e em `--expand --name` para `greet`, `hurt`, `wolf_attack`,
   `fanfare` (se passar de 20 s, só `check` para fala e vocalização).
5. Todo `examples/...` e `docs/...` citado existe.
Limite em chars, não em tokens (o tiktoken é extra de benchmark).

### Fase 4: instalação (MVP)
`cmd /c mklink /J %USERPROFILE%\.claude\skills\tune-game-audio <repo>`.
Aceite: o frontmatter lê pela junction; de outro cwd o python do `.venv` imprime os 6 tópicos; uma sessão nova lista
`tune-game-audio`. Permissão para `tools/curate.py` no projeto de trabalho: decisão do usuário.

### Fase 5: docs mínimos (MVP)
Uma frase no README (en + pt-BR) apontando o SKILL.md; uma linha em `docs/README.md`; nota do path em
"Ask a listener" (en + pt-BR); opcional: padronizar `builders as t` em `docs/dsl.md` e `examples/dsl_builder.py`.

### Fase 6: avaliação ao vivo (depois; exige aprovação explícita e orçamento)
Duas sondas de disparo (áudio de jogo vs pixel art) em sessão nova; as 3 tarefas do benchmark de review com e sem a
skill, em sessões novas, contando tokens pelos transcripts; ler o `FEEDBACK.md` e corrigir. Uma rodada por braço,
mesmo modelo e esforço; relatar o que não foi medido.

### Depois (opcional)
Junction no `~/.codex/skills`; AGY via `~/.gemini/config` (não segue junction, segundo o pxl); encolher
`docs/dsl-agent.md`; `help=` em `sfx --size/--power/--take`.

## 5. Decisões

| Decisão | Recomendação |
|---|---|
| Nome | `tune-game-audio` |
| Agentes | Claude Code agora; Codex depois (uma junction); AGY depois |
| Escopo | DSL + curadoria + comandos rápidos, com a regra de corte |
| Leitor de seções | Não fazer |
| `uv run` | Não |
| git antes da junction | Sim, procurando antes o clone original; sem push até decidir LFS |
| `FEEDBACK.md` | Fora do git |
| Avaliação ao vivo | Só com aprovação, depois das fases 0–5 |
| Permissão para `tools/curate.py` | Decisão do usuário (regra no projeto de trabalho ou aprovar na hora) |
| Exemplo novo com fala/criatura | Não: o template do SKILL.md cobre e é testado |
