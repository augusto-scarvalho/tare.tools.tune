# Autoria, inspeção e revisões

Esta é a documentação auxiliar em português. A [referência principal em inglês](../authoring.md) descreve os contratos completos e acompanha a implementação.

## Player local

```bash
pip install -e ".[dev,export]"
tare.tools.tune studio examples/authoring.json -o authoring-out
```

Abra a URL indicada, edite o JSON e salve. Cada compilação roda em um processo Python separado, com limite de 120 segundos. O observador compara o conteúdo do projeto, dos arquivos importados, dos bancos utilizados e dos módulos Python; não varre os diretórios gerados. Uma edição inválida mantém o último áudio válido. Pedidos ultrapassados não podem substituir a revisão atual. Reinicie o servidor depois de alterar seu código HTTP/UI; mudanças no sintetizador entram no próximo worker.

Escolha o som do banco, use **Previous revision** para comparar e **Follow latest** para acompanhar novos resultados. Notas pendentes mantêm a revisão selecionada; rascunhos sobrevivem à troca de revisão durante a sessão. Salve a avaliação antes de fechar a página. Salvamentos concorrentes retornam conflito, preservando as notas na página para reconciliação.

Arraste no espectrograma ou preencha os campos de tempo/frequência pelo teclado. Selecione o estágio medido para comparar camadas do mesmo barramento. Solo e mute usam os buffers capturados, preservando sementes, duração e ganhos de normalização. O processamento compartilhado atua sobre o material restante; não é uma renderização isolada com novo ganho.

Inclua `"reference": {"file": "reference.wav"}` no projeto para preservar uma referência. Os arquivos são relativos ao JSON. Reprodução estéreo, referências, revisões, notas e configurações de escuta ficam nesta máquina; o servidor escuta em `127.0.0.1`. O JSON não é executado como código Python.

## Captura e inspeção

```python
from tare.tools.tune import Creature, capture
from tare.tools.tune.bundles import save_bundle, load_bundle
from tare.tools.tune.inspection import inspect_capture

captura = capture(Creature("mammal", species=31).voice("attack"), 16000)
caminho = save_bundle(captura, "authoring-out/bundles")
preservada = load_bundle(caminho)
relatorio = inspect_capture(preservada, start=0.05, end=0.15, band=(1000, 4000))
```

```bash
tare.tools.tune capture examples/authoring.json -o authoring-out/bundles
tare.tools.tune inspect authoring-out/bundles/REVISAO --json --no-pitch
tare.tools.tune inspect examples/authoring.json --json --start 0.1 --end 0.3 --band 1000 4000 --node n1
tare.tools.tune inspect gravacao.wav --json
```

`capture` aceita Voice, Score, Cue e amostras mono/estéreo finitas. Score/Cue usam sua própria taxa. `Limits` limita duração (180 s), número de camadas (1024) e memória dos buffers (256 MiB); a inspeção também limita a entrada a 180 segundos. Dados sem receita são identificados como origem desconhecida. O schema diagnóstico 1 é separado das versões 6–8 de Voice e do comportamento `legacy-1`.

O inspetor aceita diretório de bundle, Voice JSON, projeto JSON e WAV; o extra `export` permite outros formatos suportados pelo soundfile. `--name` escolhe uma entrada de banco. O relatório mantém identidades independentes de fonte, pedido de renderização, PCM, arquivo reproduzido e análise. Uma alteração só no canal direito é detectada. Arquivos de banco são identificados pelo conteúdo.

`layers` classifica somente o estágio selecionado; `layer_catalog` lista todas as camadas para solo/mute. A consulta respeita tempo, faixa de frequência, colocação no arranjo, voltas do loop e fade. Efeitos compartilhados, cancelamento e distorção impedem atribuição causal aditiva; energia não é uma porcentagem de culpa. Não se misturam camadas normalizadas em estágios diferentes.

Os frames de fundamental têm tempo absoluto e estados explícitos para silêncio, ambiguidade e material insuficiente. Valores indefinidos são `null`, nunca NaN/Infinity. A estimativa monofônica conservadora não resolve F0 polifônico. O parcial dominante, a fundamental estimada e as notas planejadas são informações distintas; não se aplica limpeza que esconda saltos reais de oitava.

O bundle guarda `manifest.json`, `buffers.npz` sem pickle e o `audio.wav` exato. O carregamento verifica identidades de arquivos, buffers, PCM e proveniência. `current.json` publica a revisão de forma atômica. `revisions`, `answers` e `playbacks` mantêm histórico e avaliações vinculadas ao áudio ouvido. Reprodução e replay dos buffers são garantidos; regenerar receitas Python arbitrárias ou bancos históricos ausentes não é. Não há exclusão automática.

## Padrões, MIDI e bancos web

`examples/authoring.json` demonstra um compasso de três tempos com harpa e marimba. As fontes aceitas são `voice`, `creature`, `sfx`, `speech`, `music`, `score`, `audio` e `fm`. Um projeto com vários sons usa `sounds`; veja `examples/sound-bank.json`.

Os padrões aceitam notas/acordes (`C4+E4`), pausa (`.`), sustentação (`-`), acento (`C4!`) e disparos (`x`/`X`). `|` verifica o compasso conforme `meter` e `steps`. Também é possível editar as tuplas `notes` já usadas por Score. Alterar o JSON e recompilar é a forma de editar o arranjo; alterar o BPM depois da expansão não reposiciona as camadas.

```bash
tare.tools.tune midi examples/authoring.json -o authoring-out/composition.mid
tare.tools.tune export examples/sound-bank.json -o authoring-out/web --ogg
python tools/curate.py compare comparacao BUNDLE_A BUNDLE_B --root authoring-out/rounds
python tools/curate.py serve --root authoring-out/rounds
```

MIDI tipo 1 usa 960 ticks por semínima, arredondamento ao tick mais próximo, `meter=3` como 3/4, canais separados por par trilha/instrumento e canal GM 10 para percussão. A duração é a nota sustentada, não a cauda sonora. Loops cortam sustentações no fim. Transposição e intensidade são preservadas. Timbre GM é uma aproximação explícita. Sobreposição da mesma nota no mesmo grupo, excesso de canais, microtons, bends, instrumentos sem mapeamento e áudio sem eventos têm restrições explícitas; `--approximate` autoriza somente aproximações documentadas e imprime avisos. Camadas ou BPM alterados depois da expansão exigem reconstruir o Score.

O exportador gera WAV, Vorbis opcional, manifesto, adaptador Howler e player Web Audio. Sirva o diretório por HTTP e abra `index.html`. Início/fim são coordenadas inteiras de amostras, com fim exclusivo. Lacunas são amostras silenciosas separadas. Um clipe sem loop termina onde cai 60 dB abaixo dos seus 10 ms mais fortes, com fade de 10 ms no corte; `silence_cut_frames` registra o que saiu, e `pcm_id` passa a ser o do clipe. Loops e clipes que soam por um reverb ou eco (o `space` de uma Voice, que toda criatura tem, ou `hall`/`echo` de uma Score) mantêm o comprimento inteiro, assim como todos com `--keep-tail`. O WAV é PCM16; Vorbis é com perdas. O manifesto registra clipping. Antes de publicar, o Vorbis é decodificado para conferir comprimento, canais, taxa e valores finitos. Howler usa milissegundos fracionários; o player incluso deriva segundos das coordenadas originais mesmo com reamostragem pelo navegador. A tolerância de endpoints no navegador é 2 ms, separada da conferência exata do comprimento decodificado.

O Vorbis recebe 4096 amostras extras de silêncio no final, registradas em `codec_padding_samples` e excluídas das coordenadas dos clipes. Isso protege o último clipe contra o descarte de cauda observado no Chromium. A conferência pelo libsndfile usa o comprimento com padding; o player verifica a cobertura de todos os clipes e usa WAV se o Vorbis estiver incompleto ou não for suportado.

Comparações cegas copiam o WAV preservado, junto de suas identidades, para o curador existente. ABX, notas, classificações, espectros e equalização de volume continuam disponíveis. Refazer uma rodada preserva as revisões anteriores e suas avaliações. O API histórico aceita `?revision=ID`; escritas incluem `revision`, `version`, `answers` e `listening`.

## DSP opcional e compatibilidade

Na exportação MIDI, notas de intensidade zero são omitidas; intensidades positivas usam 1–127. A verificação de sobreposição da mesma tecla também considera trilhas diferentes que compartilham o canal de percussão.

`effects.fm_tone` gera FM com sobreamostragem. `Score(effects=[{"type": "chorus", "mix": 0.3}, {"type": "limiter", "ceiling": 0.4}])` adiciona chorus e limitador de pico de amostra ligado entre os canais. O limitador atua depois da dobra do loop e do ganho final; no replay diagnóstico, sua envoltória de ganho fica congelada. Loops usam modulação periódica e leitura circular do delay. Todos são desativados por padrão. Não há promessa de limiter true-peak ou FM sem aliasing para parâmetros arbitrários.

```bash
python examples/dsp_listening.py --out authoring-out/listening
python tools/curate.py serve --root authoring-out/listening/rounds
```

O exemplo cria comparações cegas das três opções. Determinismo e limites são verificáveis automaticamente; qualidade acústica continua dependendo de escuta. Não há mudança automática da normalização nem dos sons existentes.

O novo DSP pertence ao PCM/Score Python e não acrescenta campos ao Voice portátil. A matriz do núcleo C++/Godot continua a existente; Score/Cue não viraram APIs nativas novas. Fixtures congeladas antes da refatoração verificam comportamento histórico, além dos testes atuais de paridade. Testes nativos/Godot precisam realmente executar em ambiente compatível; um skip no Windows não comprova paridade. Os comandos e resultados estão no [registro de verificação em inglês](../authoring-verification.md).
