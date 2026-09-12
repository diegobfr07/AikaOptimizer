# Certificação da Paridade Determinística — dgVoodoo Config Engine (Stage 4)

**Projeto:** AIKA Optimizer V4.1.0-dev — Módulo Renderizador (dgVoodoo2)
**Vendor:** dgVoodoo2 **2.87.4** (D3D9 x86 → D3D11 FL11.0), adotado/validado pelo projeto
**Fase:** Estágio 4 da arquitetura aprovada (`ARQUITETURA_DGVOODOO_CONFIG_ENGINE.md`)
**Data:** 2026-09-08

---

## 1. Objeto

Certificar e **congelar** a paridade determinística entre:

- **Gerador legado** (`dgvoodoo_service.py` — PRESET_CONF/PERFIS_CONF/`_aplicar_chaves_texto`/`_gerar_conf_perfil`), usado **somente como oráculo de teste**;
- **Engine novo** (`dgvoodoo_config_engine.py` + `dgvoodoo_config_schema.py`), **não integrado** à produção.

Esta fase **não** integra o engine. O gerador legado continua o **produtor oficial**.

## 2. Identidade dos artefatos (hashes completos)

| Artefato | SHA-256 |
|---|---|
| Template `third_party/dgvoodoo2/dgVoodoo.conf` | `3c7da2fac3eaad369df468e80c9ba9c4db632c419799b32bbc31279d10985801` |
| `third_party/dgvoodoo2/D3D9.dll` | `db1c445f7bcf699df1e175e974c779bdc7e19a468680a44884b1ab7078888d04` |

## 3. Baseline de testes

- Baseline pré-Stage 4: **887/887 PASS**.
- Testes novos do Estágio 4: **11/11 PASS**.
- Suíte completa pós-Estágio 4: **898/898 PASS** — zero regressões (inclui Stages 1–3).

## 4. Matriz oficial — 8 cenários (5 repetições independentes)

Para cada cenário: OLD e NEW gerados 5× em diretórios temporários distintos;
**todos os hashes idênticos entre repetições**; nenhum arquivo criado no diretório
temporário; **BYTE_EQUAL = TRUE** e **SEMANTIC_EQUAL = TRUE**.

| Cenário | OLD_SHA256 == NEW_SHA256 (completo) | OLD_SIZE = NEW_SIZE | Byte | Semântico |
|---|---|---|---|---|
| Ativação inicial | `3ca4b70641ee1348e9da7b4f3a5d27979bfefe82a3c89d19c80ad61b9d4e0e12` | 21891 | ✅ | ✅ |
| Reaplicar | `3ca4b70641ee1348e9da7b4f3a5d27979bfefe82a3c89d19c80ad61b9d4e0e12` | 21891 | ✅ | ✅ |
| Performance | `0337905f4b82adec730c21292f527904bf3355c26ca74952b2e18c9b0134aeb5` | 21905 | ✅ | ✅ |
| Balanced | `3ca4b70641ee1348e9da7b4f3a5d27979bfefe82a3c89d19c80ad61b9d4e0e12` | 21891 | ✅ | ✅ |
| Quality | `ab8f2fcc04fa94d5c5b90d3858d725de83a5946073cc29fc7a0528ae102700dd` | 21891 | ✅ | ✅ |
| AUTO→Performance | `0337905f4b82adec730c21292f527904bf3355c26ca74952b2e18c9b0134aeb5` | 21905 | ✅ | ✅ |
| AUTO→Balanced | `3ca4b70641ee1348e9da7b4f3a5d27979bfefe82a3c89d19c80ad61b9d4e0e12` | 21891 | ✅ | ✅ |
| AUTO→Quality | `ab8f2fcc04fa94d5c5b90d3858d725de83a5946073cc29fc7a0528ae102700dd` | 21891 | ✅ | ✅ |

Propriedades comuns da saída ativa (OLD e NEW): **UTF-8 sem BOM**, **CRLF**,
sem newline final, 7 seções, 94 chaves ativas, ordem/valores/comentários
preservados, `diff()` semântico vazio.

## 5. Independência de ordem e de estado

- Sequências testadas: `Performance→Quality`, `Quality→Performance`,
  `Balanced→Quality`, `AUTO→Quality→Performance`, `Performance→AUTO→Balanced`.
- Cada cenário executado **isolado** produz o **mesmo hash** do mesmo cenário
  executado **após outro perfil** (nenhuma contaminação por estado anterior/cache).
- Resultado em diretórios temporários diferentes: idêntico (sem timestamp,
  random ou caminho incorporado aos bytes).

## 6. Matriz sintética A–J (determinística; sem divergência)

A chave desconhecida · B seção desconhecida · C valor vazio · D comentário
adicional · E LF na entrada · F CRLF na entrada · G BOM UTF-8 na entrada ·
H sem newline final · I duplicata não controlada · J duplicata controlada

Resultado: **10/10 OLD == NEW** (byte e semântico) e **determinísticos**
(3 repetições cada; 1 hash único por caso). Nenhuma política nova criada.

## 7. Duplicatas (comportamento observado)

Em chave controlada duplicada (`dgVoodooWatermark`), legado e engine
substituem **todas as ocorrências** para `false` e preservam as 2 linhas
(sem deduplicar). Em chave não controlada duplicada, ambas as ocorrências
são preservadas intactas. **Política de produto permanece em aberto** (não
foi criada regra nova; nenhuma divergência legado×engine).

## 8. Provenance (validação do engine contra baseline documental)

| Origem | Quantidade |
|---|---|
| `overlay_fixo` (12 invariantes) | 12 |
| `overlay_base` (Filtering/Antialiasing — Ativar/Reaplicar) | 2 |
| `perfil` (Filtering/Antialiasing — perfil manual e AUTO resolvido) | 2 |
| `template` (herdadas) | 80 |
| **Total** | **94** |

A provenance não é comparada ao legado (que não a produz) — apenas à
baseline auditada.

## 9. Lossless (Stage 1) — integridade

`parse_bytes(template).serialize_lossless() == template` (byte a byte),
independente da existência do modo ativo. Sem alteração no comportamento
do round-trip lossless.

## 10. Não-integração e integridade

- `dgvoodoo_service.py`, `dgvoodoo_page.py`, `main.py`, `config.py`,
  `hardware_detector.py` **não importam** `dgvoodoo_config_engine` nem
  `dgvoodoo_config_schema` (verificado por teste e varredura).
- Nenhum cliente Aika recebeu arquivo; engine não referencia caminhos de
  clientes; geração não cria arquivos.
- Template, DLL e `estado.json` intactos.

## 11. Riscos e pendências

- Política de duplicatas (produto) e interação AUTO × personalização
  permanecem **decisões em aberto** (sem divergência legado×engine; não
  bloqueiam a futura integração).
- A integração (Estágio 5) só pode começar com esta certificação aceita.

## 12. Conclusão

A paridade determinística entre gerador legado e engine está **certificada
e congelada**: 8/8 oficiais (byte + semântico), 5 repetições idênticas,
hashes completos idênticos ao baseline do Stage 3, 10/10 sintéticos,
independência de ordem/estado/diretório comprovada, provenance e lossless
íntegros, suíte **898/898 PASS**, produção e clientes intocados.

**Recomendação: APROVAR ESTÁGIO 4.** Estágio 5 (integração gradual) não
iniciado.
