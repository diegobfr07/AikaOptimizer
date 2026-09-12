# CORREÇÕES CIRÚRGICAS PÓS-AUDITORIA — AIKA OPTIMIZER V4.1

- **Data:** 2026-09-09
- **Escopo:** AUD-01 (P1), AUD-02 (P2), AUD-03 (P2). AUD-04 e P3 **adiados**
  deliberadamente.
- **Checkpoint pré-correção:** `V4.1_PreAuditFixes_20260909-023324`
  (`AIKA_Optimizer_Repo_V4.1_PreAuditFixes_20260909-023324.zip`,
  SHA-256 `f45029aa8449935d26a48f2cbe560b5463e60f3e9b956fe40df3f5b5e7d21335`).
- **Baseline antes das correções:** 933/933 PASS.
- **Arquivos alterados (exatos):** `Aika_Optimizer_V4.1.spec`, `requirements.txt`,
  `config.py`, `seguranca.py` (justificado — ver AUD-03), `tests/test_pre_release_fixes.py` (novo).
- Nenhum cliente Aika foi tocado; nenhuma configuração do Windows foi alterada;
  nenhum teste de campo foi executado.

---

## 1. AUD-01 — Packaging dgVoodoo (P1)

### Antes
`datas` do spec: `assets`, `itemlist6_color_profile.json`, `icone.ico`, `aika.ico` —
sem `third_party/dgvoodoo2/` (`D3D9.dll`, `dgVoodoo.conf`). No build frozen o
resolvedor (`dgvoodoo_service._resolver_template`, linhas 61–78) não encontraria
os templates e o Renderizador ficaria indisponível.

### Depois
`Aika_Optimizer_V4.1.spec` (linha 8) passou a incluir:

```python
('third_party/dgvoodoo2', 'third_party/dgvoodoo2')
```

- Destino relativo igual a `dgvoodoo_service.TEMPLATE_REL_PATH`
  (`third_party/dgvoodoo2`) — compatível com o resolvedor.
- Em PyInstaller onedir (6.x) os `datas` são entregues sob `sys._MEIPASS`
  (= `dist\Aika_Optimizer_V4.1\_internal`), exatamente onde o resolvedor procura.
- Arquivos vendor **inalterados**: hashes originais preservados.

### Evidência
- Testes novos `tests/test_pre_release_fixes.py` (TestAud01Packaging, 4 testes):
  spec referencia a pasta; arquivos-fonte existem com hashes oficiais; destino é
  compatível com `TEMPLATE_REL_PATH`; resolvedor encontra os arquivos no layout
  frozen simulado (`sys.frozen`/`_MEIPASS`).
- Prova física de layout frozen em
  `AIKA_Optimizer_Checkpoints\EVIDENCIA_AUD01_LAYOUT_FROZEN\`:
  árvore `dist\Aika_Optimizer_V4.1\_internal\third_party\dgvoodoo2\` criada com os
  dois arquivos; execução de `resolver_sim_frozen.py` retornou:
  - `dll`: `...\_internal\third_party/dgvoodoo2\D3D9.dll` → existe, SHA
    `DB1C445F7BCF699DF1E175E974C779BDC7E19A468680A44884B1AB7078888D04`
  - `conf`: `...\_internal\third_party/dgvoodoo2\dgVoodoo.conf` → existe, SHA
    `3C7DA2FAC3EAAD369DF468E80C9BA9C4DB632C419799B32BBC31279D10985801`
- **Limitação documentada:** PyInstaller **não está instalado** no `.venv`;
  portanto não foi executado um build real. A validação foi feita por (a) teste
  automatizado do spec/destino, (b) simulação física do layout onedir/`_internal`
  com o resolvedor real, e (c) conferência de hashes. Um build real de release
  deve rodar na fase de release e repetir a conferência da árvore.

**Status AUD-01: CORRIGIDO** (evidência acima; build real pendente de execução
na fase de release).

## 2. AUD-02 — requirements UTF-16 (P2)

### Antes
`requirements.txt` em UTF-16 LE (BOM `FF FE`) — risco de falha em
`pip install -r` e diffs opacos.

### Depois
Convertido para **UTF-8 sem BOM** preservando exatamente as 10 linhas:

```
customtkinter==6.0.0
darkdetect==0.8.0
packaging==26.3
psutil==7.2.2
PySide6==6.11.2
PySide6_Addons==6.11.2
PySide6_Essentials==6.11.2
pywin32==312
shiboken6==6.11.2
winshell==0.6
```

Mesmas dependências, mesmas versões, mesma ordem. Nenhum pacote alterado.

### Evidência
- `test_utf8_sem_bom`, `test_conteudo_preservado`,
  `test_pip_consegue_interpretar` (parser interno do pip: 10 requirements
  interpretados, nomes `customtkinter` e `winshell` presentes).
- Validação offline pelo parser do pip (sem alterar o venv; `pip install
  --dry-run` não foi usado por exigir rede — documentado).

**Status AUD-02: CORRIGIDO.**

## 3. AUD-03 — side effects no import de `config.py` (P2)

### Antes
`import config` executava `os.makedirs(PASTA_BACKUP, exist_ok=True)` e criava o
`RotatingFileHandler` (abria/criava `aika_optimizer.log`) — escrita em disco ao
importar; falha possível em ambiente sem `C:\CBMgames`/permissão.

### Depois (mínimo e sem mudança de caminhos públicos)
`config.py`:
- Removido o `os.makedirs(PASTA_BACKUP, ...)` em tempo de import.
- Logging migrado para inicialização **lazy e idempotente**:
  - `_garantir_pasta_backup()` — cria `PASTA_BACKUP` apenas quando chamado.
  - `_garantir_log_arquivo()` — cria a pasta e adiciona **um único**
    `RotatingFileHandler` na primeira necessidade; guardado por `_log_lock`;
    se a pasta padrão não puder ser criada, registra em stderr
    (`StreamHandler`) sem derrubar a aplicação.
  - `log()` chama `_garantir_log_arquivo()` antes de gravar.
- Caminhos públicos (`PASTA_BACKUP`, `PASTA_BACKUP_REG`, `ARQUIVO_ESTADO`, etc.)
  **inalterados**.

`seguranca.py` (justificativa): o único escritor de nível raiz que dependia da
criação no import era `salvar_snapshot_sistema()` (grava `ARQUIVO_ESTADO` sob
`PASTA_BACKUP`). Recebeu um `os.makedirs(PASTA_BACKUP, exist_ok=True)` lazy no
início do fluxo — criação **somente quando a funcionalidade é executada**.

### Evidência
Testes novos (TestAud03ConfigSemSideEffect, 4 testes):
1. `import config` **não** chama `os.makedirs` nem instancia
   `RotatingFileHandler` (subprocesso com spies) — nenhuma escrita no import.
2. Caminhos públicos continuam iguais aos anteriores.
3. Inicialização repetida do log é idempotente (1 único `RotatingFileHandler`) e
   funcional (mensagem gravada em diretório temporário).
4. `salvar_snapshot_sistema()` cria o diretório quando executado (tempdir).

Nenhum teste escreve em `C:\CBMgames`.

**Status AUD-03: CORRIGIDO.**

## 4. Arquivos alterados

| Arquivo | Motivo |
|---|---|
| `Aika_Optimizer_V4.1.spec` | AUD-01 — incluir `third_party/dgvoodoo2` no `datas` |
| `requirements.txt` | AUD-02 — conversão UTF-8 sem BOM |
| `config.py` | AUD-03 — remoção de side effect no import + logging lazy/idempotente |
| `seguranca.py` | AUD-03 (justificado) — criação lazy do diretório em `salvar_snapshot_sistema` |
| `tests/test_pre_release_fixes.py` | Testes automatizados dos 3 achados |

Não foram alterados: `dgvoodoo_service.py`, `dgvoodoo_page.py`,
`dgvoodoo_config_engine.py`, `dgvoodoo_config_schema.py`, `hardware_detector.py`,
`stone_color_service.py`, `main.py`, `third_party/*`, perfis, versão.

## 5. Testes adicionados

11 testes em `tests/test_pre_release_fixes.py` (TestAud01Packaging: 4;
TestAud02Requirements: 3; TestAud03ConfigSemSideEffect: 4).

## 6. Resultado do build / árvore dgVoodoo

Ver §1. Build PyInstaller real **não executado** (pacote ausente no venv);
validação por teste + simulação física do layout frozen com o resolvedor real.

## 7. Suíte final

**944/944 PASS** (933 + 11 novos), incluindo suíte dgVoodoo/pedras/restore/sistema.

## 8. Itens deliberadamente adiados

- AUD-04 (ponto de restauração vitalício) — mantido documentado.
- P3 (AUD-05…AUD-09) — mantidos como dívida técnica registrada no relatório de auditoria.

## 9. Riscos restantes

- Build real de PyInstaller a executar na fase de release (instalar PyInstaller
  ou ambiente de build dedicado) e conferir a árvore `_internal\third_party\dgvoodoo2`.
- Instalações fora do padrão do cliente continuam dependendo de `C:\CBMgames`
  para backups/log — mitigado para não derrubar o app (stderr fallback), mas a
  realocação dos dados do usuário permanece como melhoria futura (AUD-03 parcial).

