# AUDITORIA TÉCNICA INTEGRAL — AIKA OPTIMIZER V4.1 (PRÉ-RELEASE)

- **Data:** 2026-09-09
- **Modo:** somente leitura — nenhum código de produção/teste foi alterado.
- **Baseline:** 933/933 PASS (antes e depois da auditoria).
- **Checkpoint pré-auditoria:** `V4.1_PreFullProjectAudit_20260909-021825`
  (`AIKA_Optimizer_Repo_V4.1_PreFullProjectAudit_20260909-021825.zip`, SHA-256 `d914a732a3dd56a5336cbef5d69918dea966a589bc02ec2862dc10e885a6ba21`).
- **Estado de entrada:** `V4.1_RepositoryClean_PreAudit_20260909-021047` aprovado.

---

## 1. Resumo executivo

O projeto está arquiteturalmente maduro e com boa proteção automatizada. A frente
Renderizador/dgVoodoo Config Engine está validada (paridade, determinismo,
integração 5A/5B e campo 5C). Fluxos de sistema (backup/restauração, transações,
workers, shutdown, single-instance, elevação UAC) seguem padrões defensivos
consistentes e são cobertos por dezenas de testes.

Foram encontrados **1 achado P1**, **3 P2** e **5 P3**. O único bloqueador real de
release é de **packaging**: os templates `third_party/dgvoodoo2/` **não constam no
`datas` do PyInstaller spec** e não há cópia manual documentada — no executável
empacotado a página Renderizador não encontrará `D3D9.dll` nem `dgVoodoo.conf`
(resolvedor em `dgvoodoo_service._resolver_template`, linhas 61–78). Nenhum
achado P0 (perda de dados/corrupção/segurança) foi comprovado.

**Decisão:** correções necessárias antes do release — em especial AUD-01
(packaging) e AUD-02/03; após aplicadas, candidato a polimento visual.

---

## 2. Escopo auditado

- Leitura integral/estrutural de **todos os 60 módulos `.py`** do repositório
  (24 módulos de produção na raiz + 36 arquivos de teste), total ~35.7 mil linhas,
  2.176 funções, 284 classes.
- Leitura dos metadados: `README.md`, `requirements.txt`, `Aika_Optimizer_V4.1.spec`,
  `Projeto Brutal.iss`, `.gitignore`, `config.json`, `assets/`, `docs/renderizador/dgvoodoo2/`,
  `third_party/dgvoodoo2/` (DLL + conf).
- Varredura estática assistida por AST (imports, funções, classes) + varredura de
  riscos (caminhos pessoais, `os.remove`/`rmtree`, `winreg.SetValueEx`, `subprocess`,
  `ctypes`, `pass`, TODO/FIXME, rótulos de versão) com registro linha a linha.
- Arquivos **não** auditados linha a linha por inviabilidade (sinalizado com
  transparência): `main.py` (6.044 linhas — auditado por estrutura/métodos/fluxos
  críticos), `set_injector.py`/`automod.py`/`extractor_sets.py` (auditados por
  arquitetura, funções de risco e pelos testes dedicados que os exercitam).

---

## 3. Baseline

- Suíte completa **933/933 PASS** executada antes da auditoria (confere com o
  checkpoint de entrada).
- `git status`: preservado integralmente o conjunto pré-existente de modificações
  e arquivos untracked de desenvolvimento (nada foi alterado nesta fase).
- Nenhum cliente Aika foi tocado; nenhuma configuração do Windows foi alterada;
  nenhum teste de campo foi executado.

---

## 4. Mapa arquitetural

```
main.py (AikaOptimizerPro, 12 classes/236 métodos)
 ├─ entrada: elevação UAC, single-instance (QLocalServer), modos --jit-silent,
 │   --jit-inject, --dds-inject, --startup; watchdog de boost; tray; shutdown
 │   coordenado (workers cooperativos + aboutToQuit com espera ≤8s)
 ├─ telas/páginas: dgvoodoo_page (Renderizador), stone_color_page (Pedras),
 │   restore_list (Restauração), jit/aba texturas, aba SETs (set_injector)
 ├─ executor de UI→worker: executar_em_background / TarefaWorker(QThread)
 │   e _executor_dgvoodoo (adapter para a página Renderizador)
 └─ fachada de domínio: optimizer.py → importa * de config/seguranca/automod/
    audio/textura/game_booster/performance/sistema
Renderizador (validado): dgvoodoo_service → dgvoodoo_config_engine +
    dgvoodoo_config_schema (+ hardware_detector p/ AUTO; parity guard 5A/5B)
Pedras: stone_color_service (estado A–E, transações) + itemlist6_color_engine
    + stone_color_page
Sistema/booster: game_booster, performance, sistema, seguranca (backup .reg,
    snapshot DNS/power, transação com rollback, escrita atômica), config
Sets/mods: extractor_sets, textura, set_injector, automod, jit_integration
Ferramenta standalone (fora do runtime): listadeset.py (tkinter); monitor.py (legado)
Dados: backup/estado sob C:\CBMgames\AikaOptimizer_Backups\<clientes>\ (identidade
    por hash do caminho real); config do usuário em config.json (dev) ou
    %LOCALAPPDATA%\AIKA Optimizer\config.json (frozen)
```

Pontos fortes confirmados: fonte única de executáveis (`config.AIKA_GAME_EXES`),
`caminho_seguro()` reutilizado nos serviços, escrita atômica via
tmp+fsync+`os.replace`, identidade de cliente por hash do caminho real
(namespace de backup isolado), padrão de transação com rollback em
`seguranca.py`, shutdown cooperativo no `main.py`.

## 5. Inventário de módulos (produção)

| Módulo | Linhas | Funções | Classes | Papel | Status |
|---|---|---|---|---|---|
| main.py | 6044 | 236 | 12 | App PySide6, janelas, workers, shutdown, watchdog | ATIVO |
| dgvoodoo_service.py | 1427 | 40 | 3 | Renderizador: ativar/perfil/restaurar/estado + engine/guard | ATIVO (validado 5A–5C) |
| dgvoodoo_page.py | 1073 | 49 | 2 | UI Renderizador | ATIVO (validado) |
| dgvoodoo_config_engine.py | 683 | 41 | 9 | Engine de parsing/serialização/geração (puro) | ATIVO (validado) |
| dgvoodoo_config_schema.py | 294 | 5 | 1 | Catálogo/overlay/perfis do engine | ATIVO (validado) |
| hardware_detector.py | 552 | 17 | 2 | Detecção GPU/VRAM → AUTO | ATIVO (validado/auditado) |
| stone_color_service.py | 996 | 38 | 10 | Pedras: estado/transação/aplicação | ATIVO |
| stone_color_page.py | 987 | 54 | 6 | UI Pedras | ATIVO |
| itemlist6_color_engine.py | 843 | 26 | 16 | Motor puro de perfil de cores | ATIVO |
| restore_list.py | 542 | 37 | 5 | UI Restauração | ATIVO |
| set_injector.py | 1806 | 36 | 1 | Injeção de mods SET (transações) | ATIVO |
| automod.py | 1037 | 36 | 0 | AutoMod: backup/remoção/rollback | ATIVO |
| extractor_sets.py | 1142 | 22 | 0 | Organizador/Conversor de SETs | ATIVO |
| jit_integration.py | 610 | 33 | 0 | Associação .JIT/.dds + modos silenciosos | ATIVO |
| game_booster.py | 1412 | 37 | 1 | Boost: categorias/processos/prioridade | ATIVO |
| performance.py | 129 | 7 | 0 | Timer/MPO/cache/multimídia/afinidade | ATIVO |
| sistema.py | 421 | 22 | 0 | DNS/GameDVR/TCP/power/QoS/limpeza | ATIVO |
| seguranca.py | 455 | 18 | 1 | Backup/restore/transação/snapshot | ATIVO |
| config.py | 452 | 28 | 0 | Fonte de config/caminhos/executáveis | ATIVO |
| textura.py | 404 | 11 | 0 | Extração de texturas JIT | ATIVO |
| audio.py | 176 | 9 | 0 | Áudio do jogo | ATIVO (via fachada) |
| optimizer.py | 11 | 0 | 0 | Fachada (importa * dos módulos) | ATIVO |
| listadeset.py | 430 | 13 | 1 | Ferramenta standalone tkinter | LEGADO MAS NECESSÁRIO (documentado) |
| monitor.py | 79 | 5 | 0 | — | POSSIVELMENTE MORTO (documentado legacy) |

## 6. Achados P0

**Nenhum achado P0.** Não foi encontrada evidência concreta de risco de perda de
dados, corrupção ou segurança nos fluxos auditados (escrita atômica + backup
validado por SHA-256 + `caminho_seguro` nos pontos de mutação de arquivos;
operações de registro protegidas por backup `.reg`; remoção de arquivos do jogo
somente com backup prévio e rollback).

## 7. Achados P1

### AUD-01 — P1 · Templates dgVoodoo não empacotados no build (COMPROVADO)
- **Arquivo:** `Aika_Optimizer_V4.1.spec` (linha 8), `dgvoodoo_service.py` (58, 61–78), `Projeto Brutal.iss` (50).
- **Descrição:** o `datas` do spec inclui apenas `assets`, `itemlist6_color_profile.json`,
  `icone.ico`, `aika.ico`. `third_party/dgvoodoo2/` (D3D9.dll + dgVoodoo.conf) não é
  incluído. O resolvedor de templates em build frozen procura `<exe>/third_party/dgvoodoo2/`
  e `sys._MEIPASS/third_party/dgvoodoo2/` — nenhum dos dois existirá no onedir gerado.
  O instalador (iss) copia somente `dist\Aika_Optimizer_V4.1\*`.
- **Evidência:** verificação direta do spec; nenhuma instrução de cópia de
  `third_party` no README/iss/build.
- **Cenário de falha:** usuário instala o release → abre Renderizador →
  `validar_templates()` retorna "Template ausente" → Ativar/Reaplicar/perfis
  ficam indisponíveis (funcionalidade central do V4.1).
- **Impacto:** bloqueia a entrega estável do Renderizador.
- **Correção conceitual:** adicionar `('third_party/dgvoodoo2', 'third_party/dgvoodoo2')`
  ao `datas` do spec (ou etapa de build que copie a pasta para junto do executável)
  e adicionar teste de packaging que valide a presença dos dois arquivos na árvore
  do build.
- **Testes que cobrem:** nenhum (testes de engine usam caminho de desenvolvimento;
  não há teste de árvore do PyInstaller).
- **Confiança:** COMPROVADO (ausência factual; comportamento do resolvedor lido).

## 8. Achados P2

### AUD-02 — P2 · `requirements.txt` em UTF-16 LE (COMPROVADO)
- **Arquivo:** `requirements.txt`.
- **Descrição:** arquivo codificado em UTF-16 LE (BOM FF FE); leitura em UTF-8
  expõe `\u0000` entre caracteres. `pip install -r requirements.txt` pode falhar
  em ambientes cujo locale/decoder não detecte UTF-16; diffs de texto ficam opacos.
- **Evidência:** leitura binária/UTF-8 do arquivo (todos os caracteres intercalados
  por `\u0000`).
- **Impacto:** reprodutibilidade do build por fontes (colaboradores/CI); baixo
  risco para o instalador final (que não depende de pip).
- **Correção conceitual:** reescrever o arquivo em UTF-8 (sem BOM) com o mesmo conteúdo.
- **Testes que cobrem:** nenhum.
- **Confiança:** COMPROVADO (formato). Severidade mantida P2 (build-time, não runtime).

### AUD-03 — P2 · Efeito colateral de `config.py` no import: cria `C:\CBMgames\AikaOptimizer_Backups` e abre log (PROVÁVEL)
- **Arquivo:** `config.py` (30–31, 57, 380–386).
- **Descrição:** em tempo de import, `os.makedirs(PASTA_BACKUP, exist_ok=True)` e a
  criação de `RotatingFileHandler` apontam para `C:\CBMgames\AikaOptimizer_Backups`
  (fixo), independentemente do cliente configurado e do modo frozen. Em máquina sem
  `C:\CBMgames` e sem privilégio para criá-la (instalação do jogo fora do padrão),
  o `import config` pode falhar e impedir a inicialização do app. Além disso, toda
  execução de testes/imports grava `aika_optimizer.log` fora de diretório temporário
  (testes escrevem fora de `temp` — item 15 da auditoria).
- **Evidência:** linhas citadas; nenhum `try/except` envolve `makedirs`; handler sem
  `delay=True`; suíte/imports confirmam gravação do log.
- **Cenário de falha:** usuário com cliente custom e sem pasta `C:\CBMgames` inicia
  o app (não elevado) → exceção de permissão em import.
- **Impacto:** falha de inicialização em instalações fora do padrão; poluição fora
  de `temp` em testes.
- **Correção conceitual:** decidir pasta de dados do usuário por runtime (dev vs
  frozen), criar com proteção e falha tratada, e usar `delay=True` no handler.
- **Testes que cobrem:** nenhum para este cenário.
- **Confiança:** PROVÁVEL (depende do ambiente do usuário).

### AUD-04 — P2 · Ponto de restauração criado uma única vez para limpeza profunda (COMPROVADO)
- **Arquivo:** `seguranca.py` `criar_ponto_restauracao()` (marcador permanente
  `ponto_restauracao_criado.txt`), chamado por `sistema.limpar_profundo()`.
- **Descrição:** após a primeira criação bem-sucedida, chamadas futuras de
  `limpar_profundo(esvaziar_lixeira=True)` não criam novo ponto de restauração —
  o esvaziamento da lixeira em momento posterior pode ficar sem ponto de
  restauração recente (e sem outro snapshot).
- **Evidência:** `if os.path.exists(marcador): return True` antes de criar.
- **Impacto:** reversibilidade limitada de uma ação destrutiva (lixeira) em usos
  posteriores; o marcador impede repetição mesmo após dias/meses.
- **Correção conceitual:** criar ponto de restauração por operação (ou por janela
  de tempo) antes de ações destrutivas, sem marcador único vitalício.
- **Testes que cobrem:** `test_correcao_system_restore.py` (parcial — valida o
  fluxo existente, não a recorrência).
- **Confiança:** COMPROVADO (lógica do marcador).

## 9. Achados P3

### AUD-05 — P3 · `limpar_profundo`/`apagar_arquivos_pasta` mascaram falhas parciais (COMPROVADO)
`sistema.py` (5–26): `apagar_arquivos_pasta` engole toda exceção e
`limpar_profundo` sempre retorna `True` quando não há exceção externa. Arquivos
bloqueados (em uso) não são reportados ao usuário. Correção conceitual: retornar
contagem de falhas e mensagem honesta.

### AUD-06 — P3 · Duplicação de constantes de perfil/invariantes (INFORMATIVO)
`Filtering/Antialiasing/watermark/OutputAPI` e invariantes existem tanto em
`dgvoodoo_service.py` (`PRESET_CONF`/`PERFIS_CONF`) quanto em
`dgvoodoo_config_schema.py` (`OVERLAY_FIXO`/`BASE_AIKA`/`PERFIS_MAP`); hashes
congelados estão repetidos em 6 arquivos de teste e em manifests/docs. Hoje a
suíte de paridade (933) garante sincronia; a duplicação é dívida controlada.

### AUD-07 — P3 · Rótulos de versão "V4.0"/"V4.1.0-dev" espalhados (ver §17)
Sem impacto funcional; lista de locais para padronizar antes do release.

### AUD-08 — P3 · `listadeset.py` (standalone) atualiza tkinter a partir de thread (INFORMATIVO)
`listadeset.py` (312) inicia `threading.Thread` que manipula a interface. Fora do
runtime principal e documentado como ferramenta standalone; risco clássico de
thread+tkinter se for executado.

### AUD-09 — P3 · `requirements.txt`: entradas redundantes/indiretas (INFORMATIVO)
`PySide6_Addons`/`PySide6_Essentials` são instalados pelo meta-pacote `PySide6`;
`packaging` e `darkdetect` não são importados diretamente pelo código do app
(dependências transitivas). Manutenção: considerar manter apenas dependências
diretas + documentar transitivas. `config.json` na raiz é **configuração local de
desenvolvimento** (contém caminho pessoal `OneDrive/Desktop/...`) e **não deve ser
distribuída** — correto: está no `.gitignore` e fora do `datas` do spec (validado).

## 10. Módulos possivelmente legados

| Módulo | Classificação | Evidência |
|---|---|---|
| monitor.py | POSSIVELMENTE MORTO (mantido por decisão documentada) | Não importado em produção/testes; README:228 declara legacy e fora do runtime/build. Manter. |
| listadeset.py | LEGADO MAS AINDA NECESSÁRIO | Ferramenta standalone tkinter preservada; `extractor_sets.py` diz extrair dela a lógica pura. Não entra no build PyInstaller. Manter. |
| optimizer.py | ATIVO | Fachada; `main.py:41 import optimizer as opt`. |
| extractor_sets.py / textura.py / automod.py / set_injector.py / audio.py | ATIVO | Importados por main/fachada/testes (test_validacao05/06/07, test_correcao*). |
| `ARQUIVO_INDEX` legado (automod) | LEGADO MAS NECESSÁRIO | `_ARQUIVO_INDEX_META = ARQUIVO_INDEX + ".meta"  # legado; novos índices são por cliente` — compatibilidade. Manter. |

## 11. Caminhos hardcoded encontrados

- `C:\CBMgames\AikaOnlineBrasil` — **padrão legítimo do cliente Aika**: `config.py`
  (28–30) default + fallback por registro de desinstalação (`descobrir_pasta_jogo`). Legítimo.
- `C:\CBMgames\AikaOptimizer_Backups` (backups/estado/log) — padrão do projeto, mas
  **não se adapta** a cliente em outro volume/modo frozen (ver AUD-03).
- `C:\Users\diego\OneDrive\Desktop\...` — presente **somente** em `config.json`
  (dev local, gitignored, fora do spec). Não vaza para release. Validado.
- `C:\CBMgames\...` e `Downloads\AikaOnlineBrasil` não aparecem em código de
  produção além do default legítimo acima (verificado por varredura de módulos e testes).
- Falsos positivos de varredura: `DesktopResolution`, `DesktopBitDepth`,
  `onedrive.exe`/`dropbox.exe` etc. em `game_booster.py` (lista de processos a
  encerrar — nominal, não caminho) e menções "monitor" em docs/UI (conceito, não caminho).

## 12. Auditoria de backup/restauração

- Padrão geral confirmado em `seguranca.py`: backup atômico com verificação de
  tamanho **e** SHA-256 antes do `os.replace`; restauração também atômica com
  verificação pós-escrita; exclusão com `.old`/`.backup` validado; transação com
  rollback ordenado (`TransacaoSistema`); snapshot de sistema (plano de energia +
  DNS) gravado/restaurado pelo mesmo filtro de adaptadores físicos ativos
  (`filtro_adaptadores_ativos_ps`), mantendo escopo idêntico entre captura/restore.
- dgVoodoo: `pending → backup → DLL → conf(engine) → active`; proteção
  MODIFICADO_EXTERNAMENTE e JOGO_ABERTO; estado com namespace por identidade de
  cliente; Restaurar com preflight e mutação só após validação integral. Validado
  (estágios 5A–5C + testes).
- Pedras/automod/set_injector: estados A–E e lotes com backup pré-validado antes da
  primeira substituição (verificado nos testes dedicados `test_pedras_*`,
  `test_validacao05/07`).
- Risco registrado: ponto de restauração único vitalício (AUD-04) e sucesso
  mascarado na limpeza de temp (AUD-05).

## 13. Auditoria de threads / PySide6

- `main.py`: `TarefaWorker(QThread)` com sinais `resultado/erro`, exceção capturada
  e emitida; `deleteLater`; `limpar_execucao`; **execução serializada** com
  `tarefa_lock` (uma tarefa por vez); shutdown cooperativo via
  `fechar_app → cancel → _tentar_finalizar_shutdown → _finalizar_shutdown_seguro`
  e `aboutToQuit` aguardando cleanup (≤8 s). `closeEvent` respeita tray/force_exit.
- Página Renderizador: executor injetado (`main._executor_dgvoodoo`) roda operações
  em background; refresh da página temporariamente no-op durante a operação e
  restaurado no callback na UI thread — evita tocar UI fora da thread principal.
- Pedras: `request_shutdown`/`active_thread` integrados ao shutdown do main.
- Página Renderizador sem executor roda síncrono (testável). Sem executor real não
  há freeze (opções do usuário são via botões desabilitados enquanto `_busy`).
- Ponto registrado: `listadeset.py` (standalone) manipula tkinter de uma
  `threading.Thread` (AUD-08) — fora do runtime.

## 14. Auditoria de packaging

**Resposta à pergunta central:** *"O instalador/release atual contém tudo que o
programa precisa?"* → **NÃO, atualmente não**: faltam `third_party/dgvoodoo2/`
(`D3D9.dll`, `dgVoodoo.conf`) no `datas` do PyInstaller (AUD-01). Sem eles o
Renderizador não funciona no release.

Situação dos demais recursos:
- `assets/` (SVGs), `itemlist6_color_profile.json`, `icone.ico`, `aika.ico` — **incluídos**.
- Páginas usam `_resource_path`/`sys._MEIPASS` corretamente (`dgvoodoo_page.py:53–55`,
  `stone_color_page.py:71–75`).
- Config do usuário em frozen → `%LOCALAPPDATA%\AIKA Optimizer\config.json`; migração
  de `config.json` legado do diretório do exe implementada (`config.py:211–224`).
- Inno Setup: copia o onedir inteiro; `PrivilegesRequired=admin`; `MinVersion=10.0`;
  limpeza de resquícios V3; registry de uninstall cobre HKCU Run/ProgID JIT/verbo
  DDS/Capabilities/OpenWithProgids. Cobertura boa.
- Falta também um **teste de packaging** (verificar a árvore do build onedir antes
  do Inno).

## 15. Dependências

| Pacote (requirements) | Uso real | Classificação |
|---|---|---|
| PySide6 / PySide6_Addons / PySide6_Essentials | main, páginas, restore_list | Usada e declarada (Addons/Essentials redundantes ao meta, ver AUD-09) |
| customtkinter==6.0.0 | listadeset.py (standalone) | Usada e declarada (somente ferramenta standalone) |
| psutil==7.2.2 | config, main, game_booster, sistema, monitor | Usada e declarada |
| pywin32==312 | winshell (sistema.py) via win32com | Usada indiretamente e declarada |
| winshell==0.6 | sistema.py (lixeira/limpeza) | Usada e declarada |
| darkdetect | customtkinter (transitiva) | Declarada, uso indireto |
| packaging==26.3 | transitiva de ferramentas | Declarada, sem import direto no app |
| shiboken6==6.11.2 | PySide6 (transitiva obrigatória) | Declarada corretamente para pip |

Nenhuma dependência **usada e não declarada** foi encontrada entre as libs
externas relevantes (stdlib `winreg`, `ctypes`, `winshell` etc. verificados).
Versões do venv batem com os pins.

## 16. Cobertura de testes (mapa aproximado)

| Componente | Testes | Observação |
|---|---|---|
| dgVoodoo engine/schema | test_dgvoodoo_config_engine (+stage2–4) | Parsing/lossless/paridade/determinismo |
| dgVoodoo service/page/integração | vendor_2874, service, page, integration, stage5a, stage5b | Muito forte; stage5a/5b usam dirs temporários |
| hardware_detector | test_hardware_detector | Alto (mocks de registry/PowerShell) |
| Pedras (service/page/processo/estado) | test_pedras_functional/service/processflow/statesync | Forte |
| Restauração/UI | test_restore_table, test_correcao_system_restore | Forte |
| automod/textura/set_injector/extractor | test_validacao05/06/07 + test_correcao06–09 | Forte |
| main/UI/dgvoodoo/fluxos de confirmação | test_dgvoodoo_integration/page, test_correcao07a–08c etc. | Forte |
| sistema/game_booster/performance/config | test_correcao02–04, 10b/c | Boa |
| **Gaps relevantes** | — | jit_integration (verbos/modos silenciosos) sem suíte dedicada; audio pouco coberto; `monitor.py` sem teste (morto); **nenhum teste de packaging (árvore do build)**; requisitos sem teste de encoding; limpeza profunda/DNS/QoS dependem de mocks |

Observações de higiene da suíte: os testes usam diretórios temporários e mocks de
`config.obter_pasta_jogo_atual`; nenhum teste referencia clientes reais. Única
exceção ambiental: `import config` cria pasta/log em `C:\CBMgames\AikaOptimizer_Backups`
(AUD-03), fora de `temp` — efeito colateral herdado do módulo, não dos testes.

## 17. Consistência de versão/nomes — locais a revisar no release

| Local | Valor atual |
|---|---|
| `main.py:65` | `VERSION_LABEL = "V4.1.0-dev"` |
| `README.md:1,11,13,257` | título/estado "V4.1.0-dev"; "não publicada"; versão de teste |
| `stone_color_service.py:2` | docstring "V4.1.0-dev" |
| `dgvoodoo_page.py:2` | docstring "V4.1" |
| `extractor_sets.py:151,356` | cabeçalho gravado no OBJ **"AIKA Optimizer V4.0"** |
| `game_booster.py:19,586,1234,1380` / `optimizer.py:1` / `config.py:60` | comentários/docstrings "V4.0" (internos) |
| `jit_integration.py:27–28` | nome registrado "V4.1" + legado "V4.0" (migração intencional) |
| `Projeto Brutal.iss` | `MyAppVersion 4.1.0.0`, `AppVerName ... V4.1`, `AppId` preservado da V3 (atualização) |
| `Aika_Optimizer_V4.1.spec` / executável / `OutputBaseFilename` | `Aika_Optimizer_V4.1` |

## 18. Pontos de polimento visual (próxima fase)

- Nenhum problema funcional de UI bloqueante foi comprovado. Itens abertos para a
  fase de polimento: textos/estado em ações de sistema (honestidade de sucesso da
  limpeza profunda — AUD-05), badge/recomendações da página Renderizador já
  existentes e revalidação de acessibilidade de contraste nos cards (sem evidência
  de bug, apenas candidatos de revisão).

## 19. Itens validados sem problema

- **Renderizador completo** (service/página/engine/schema/hardware): integração
  com parity guard, hashes certificados, backup/restauração e campo 5C — sem novos
  achados nesta auditoria (não se reabrem decisões congeladas).
- **Transação/backup** (`seguranca.py`), **atomicidade** e **`caminho_seguro`** nos
  fluxos de arquivo; **snapshot DNS/power** com escopo idêntico de captura/restore.
- **Threads/shutdown** (`main.py`): workers com sinais, serialização, cancelamento
  cooperativo e espera no encerramento.
- **Single-instance/elevação/modos silenciosos** (`main.py:5957+`) antes da GUI.
- **Inno Setup** cobre desinstalação dos artefatos próprios do app (Run/JIT/DDS/Capabilities).
- **Namespaces de backup por identidade de cliente** e estado `estado.json` por
  cliente (`config.identidade_cliente`).
- **Config local de desenvolvimento** (`config.json` raiz) corretamente fora do release.
- Templates/DLL/engine/schema/página/serviço com hashes intactos (nada alterado nesta fase).

## 20. Tabela final de recomendações

| ID | Prioridade | Tema | Confiança |
|---|---|---|---|
| AUD-01 | P1 | Empacotar `third_party/dgvoodoo2` no PyInstaller + teste de árvore do build | COMPROVADO |
| AUD-02 | P2 | Normalizar `requirements.txt` para UTF-8 | COMPROVADO |
| AUD-03 | P2 | Remover efeito colateral de import de `config.py` (pasta/log) p/ instalações fora do padrão | PROVÁVEL |
| AUD-04 | P2 | Ponto de restauração por operação (não único vitalício) | COMPROVADO |
| AUD-05 | P3 | Reportar falhas parciais na limpeza profunda | COMPROVADO |
| AUD-06 | P3 | Reduzir duplicação perfis/invariantes (dívida controlada por testes) | INFORMATIVO |
| AUD-07 | P3 | Padronizar rótulos de versão (V4.0/V4.1.0-dev) | INFORMATIVO |
| AUD-08 | P3 | listadeset standalone: thread+tkinter | INFORMATIVO |
| AUD-09 | P3 | requirements: entradas redundantes/indiretas | INFORMATIVO |

## 21. Decisão

**CORREÇÕES NECESSÁRIAS ANTES DO RELEASE** (nenhuma P0; prioridade: AUD-01
obrigatório antes do build estável; AUD-02/AUD-03 recomendados na mesma fase).
Após aplicação das correções, o projeto estará **APTO PARA POLIMENTO/RELEASE**.

---

## Metodologia e limites (transparência)

- Ferramentas: leitura de código-fonte, AST (mapa de imports/funções/classes),
  varredura de padrões de risco com evidência linha a linha, consulta a
  git/arquivos de build/instalação e execução da suíte existente.
- Não foram lidas integralmente as 6.044 linhas de `main.py` (auditado por
  estrutura/fluxos críticos/rotinas de worker-shutdown) nem todos os caminhos de
  `set_injector`/`automod`/`extractor_sets` (auditados por arquitetura e pelos
  testes dedicados que os exercitam).
- Achados rotulados por nível de confiança; nada foi corrigido.




