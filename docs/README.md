# Documentation

English (en-US) is the primary documentation language and the reference for this project. Brazilian Portuguese (pt-BR) is available as an alternative.

| Guide | English (primary) | Português brasileiro (alternativa) |
|---|---|---|
| Overview, installation, API examples, CLI, and development | [README](../README.md) | [README em português](../README.pt-BR.md) |
| Architecture, rendering, portability, and calibration | [Architecture](architecture.md) | [Arquitetura](pt-BR/arquitetura.md) |
| Essential action and adventure RPG sounds | [RPG sounds](rpg-sounds.md) | [Sons essenciais de RPG](pt-BR/sons-rpg.md) |
| Tactical RPG sound coverage and priorities | [Tactical RPG sounds](tactics-sounds.md) | [Sons de tactics RPG](pt-BR/sons-tactics.md) |
| Capture, inspection, live authoring, MIDI, sprites, and optional DSP | [Authoring](authoring.md) | [Autoria](pt-BR/autoria.md) |
| Semantic DSL, reusable definitions, Notes, guarded edits, and compact queries (experimental) | [DSL](dsl.md) | [DSL: guia auxiliar](pt-BR/dsl.md) |
| Agent skill: workflow, lookups, template and habits for AI agents | [SKILL.md](../SKILL.md) | — (English only) |
| Review audio, discover controls and trial-check atomic edits | [Review loop](dsl-review.md) | [Revisar e editar](pt-BR/revisao-dsl.md) |
| Continuation token attribution and compact feedback | [Token analysis](dsl-review-token-costs.md) | [Tokens nas continuações](pt-BR/tokens-revisao-dsl.md) |

For documentation changes, update the English version first and keep the corresponding pt-BR version aligned. New primary guides belong directly in `docs/`; their Portuguese alternatives belong in `docs/pt-BR/`. The alternative project overview is `README.pt-BR.md` at the repository root. Each translated guide links to its counterpart.

Portuguese speech samples, phonetic examples, language codes, voice bank names, and supported API identifiers retain their original spelling where required to demonstrate Brazilian Portuguese synthesis. Source code and third-party documentation retain their own paths.

## Implementation plans

- [Backlog](../BACKLOG.md) — what is left, in the order it makes sense to take it.
- [An ear for the model](plans/2026-11-02-ear/PLAN.md) — `TUNE ear`, the sound as text (bands by time in 6 dB digits, peaks, DIFF); calibration against the listener later (Portuguese working plan).
- [Holding sounds against reference recordings](plans/2026-11-02-reference-study/PLAN.md) — measures, `references`, review tolerances and the REF card in curation; `study` and the agent evaluation later (Portuguese working plan).
- [tare.tools.tune as an agent skill](plans/2026-11-01-skill/PLAN.md) — critique of the first proposal, text audit, skill structure and phases (Portuguese working plan).

- [DSL efficiency correction plan](plans/2026-11-01-dsl-efficiency/PLAN.md) — measurement parity, smaller incremental edits and compact responses. [Resumo em português](pt-BR/plano-correcao-dsl.md).

- [DSL efficiency implementation and version-2 evidence](dsl-efficiency.md) — opt-in compact responses, independent semantic actions and equivalent service contracts. [Relatório auxiliar em português](pt-BR/eficiencia-dsl.md).

- DSL: [compact agent workflow](dsl-agent.md), [generated vocabulary](dsl-reference.json), [acceptance map](dsl-acceptance.md), [paired token measurements and live-pilot limits](dsl-benchmarks.md). [Guia auxiliar para agentes](pt-BR/dsl-agentes.md).

- [Semantic DSL and compact agent workflows](plans/2026-10-31-dsl/PLAN.md) — reviewed Astra xhigh plan, preserved as the implementation baseline. [Implementation record](dsl-implementation.md), [benchmark evidence](dsl-benchmarks.md), [resumo auxiliar em português](pt-BR/plano-dsl.md).

## Verification

- [Authoring implementation and verification](authoring-verification.md) — delivered plan areas, tests, browser codec correction, and remaining limits.
