# Backlog

O que ficou para depois, na ordem em que faz sentido atacar. Cada item aponta para o plano que o detalha.
Tudo o que sobrou roda um modelo ou pede a sua escuta, então só começa com a sua aprovação.

## Ouvido do modelo (`docs/plans/2026-11-02-ear/PLAN.md`)

1. **As rodadas de calibração** (fase 5): 4 rodadas, ~30 min de escuta do usuário, ~120k tokens. Só com
   aprovação. Com 20 escolhas somadas pelo `agree`; a primeira rodada sozinha é uma pista, não uma licença para o
   assistente escolher sozinho.
2. **Por evidência da calibração** (fase 6): linha `modulation:` (aspereza), `--channel L|R|side`, `--png`, opções
   `--bands/--cols/--hi`, a linha "energia acima de 8 kHz" (o "ar" de uma gravação a 44,1 kHz) e os ouvidos
   semânticos (CLAP, Whisper, modelo de áudio no `aaaaa` via `gpu`; Gemini só para renders do tune).

## Referências (`docs/plans/2026-11-02-reference-study/PLAN.md`)

3. **Avaliação com agentes** (fase 7): com e sem o ciclo de referência, alvos escondidos renderizados pelo tune, ABX
   final com o usuário. Só com aprovação.

## Skill e exportação

4. **AGY lê a skill:** numa conversa nova (2026-11-02), o `agy` escolheu a skill certa (som → tune, pixel art → pxl),
   mas sem tela ele não pôde ler o `SKILL.md` do tune (`read_file` negado), enquanto o do pxl passou. Conferir numa
   sessão interativa se ele pede a permissão uma vez e segue; senão, uma regra `read_file` para a pasta, com o seu ok.
   Claude Code (3 de 3, inclusive "editar uma gravação" sem abrir o tune) e Codex (2 de 2) acertaram.

## Desempenho

5. **Música mais rápida:** o `town` leva 30 s para 36 s de áudio (16 kHz), e `test_every_cue_renders[orchestral]`
   leva 6,5 min. Os ressonadores do `render_modal` por convolução FFT (são lineares e partilham a excitação) e os
   filtros dos `pop` do `render_scatter` (um `butter` por evento, ~1 ms cada) calculados juntos dariam ~3x na
   música. Muda o áudio abaixo do audível e afasta o código da recorrência simples que os ports (C++, Godot) seguem.

## Abrir o código

6. **Mac:** a suíte passou inteira no Linux (Ubuntu no WSL, de um clone limpo, em 2026-11-02); ninguém testou
   no Mac ainda.
