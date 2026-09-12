# VALIDAÇÃO FUNCIONAL CONTROLADA DGVOODOO2 2.87.4 — APROVADA

## Resumo completo da jornada

**1ª rodada (campo): REPROVADA** — a watermark "dgVoodoo" apareceu na tela de loading do Aika com `dgVoodooWatermark=false` no conf.

**Investigação:** causa raiz confirmada: o `dgVoodoo.conf` gerado pelo Optimizer iniciava com **BOM UTF-8** (`EF BB BF`, proveniente de `encode("utf-8-sig")`). O dgVoodoo 2.87.4 ignorava o conf inválido e usava a configuração padrão, na qual a watermark estava ligada.

**Prova funcional:** conf sem BOM → jogo abriu sem watermark.

## Correção aplicada

- `dgvoodoo_service.py`: gravação do conf alterada para **`utf-8` sem BOM** nos dois pontos de geração.
- Leituras continuam tolerantes com `utf-8-sig`.
- Testes de regressão: conf gerado e instalado não podem iniciar com `EF BB BF`.
- Suíte: **812/812 PASS**.

## 2ª rodada de campo

Todas as fases aprovadas.

| Cenário | Perfil | watermark=false no conf | Watermark apareceu |
|---|---|---|---|
| Ativação inicial | Balanced (Aika Recomendado) | SIM | NÃO |
| Performance | Performance | SIM | NÃO |
| Quality | Quality | SIM | NÃO |
| AUTO | AUTO → Quality | SIM | NÃO |
| Reaplicar | Aika Recomendado (Balanced) | SIM | NÃO |

## Critérios de aprovação

Todos cumpridos:

- DLL 2.87.4 x86 instalada;
- Aika inicia e entra no mapa;
- Balanced estável;
- Performance, Quality, AUTO e Reaplicar funcionam;
- nenhum perfil altera a DLL;
- DX11 preservado (`OutputAPI=d3d11_fl11_0`);
- watermark `false` em todos;
- nenhuma watermark apareceu;
- persistência OK;
- restauração OK;
- cliente de teste voltou a ORIGINAL;
- configuração global restaurada para `C:\CBMgames\AikaOnlineBrasil`.

## Artefatos registrados

- Checkpoint final: `V4.1_DgVoodoo2874_FieldValidated_20260908-204905`
- ZIP SHA-256 informado no relatório original: `FDB6D0DE…BAD49`
- Registro da falha/laudo: `Campo2874_FASE4_WATERMARK_FALHA\`

## Estado final da máquina

- Cliente de teste: **ORIGINAL**
- Cliente principal: **intocado**
- `config.json` → principal
- nenhum processo do jogo/Optimizer aberto

## Produção alterada nesta etapa

- `dgvoodoo_service.py` — gravação sem BOM
- `tests/test_dgvoodoo_vendor_2874.py` — regressão

Templates 2.87.4 e demais módulos permaneceram intactos.

## Classificação final

**DGVOODOO2 2.87.4 — VALIDAÇÃO FUNCIONAL DE CAMPO APROVADA**

**VENDOR 2.87.4 PROMOVIDO**, com a correção "sem BOM" integrada.

DGVOODOO2 2.87.3 mantido apenas nos checkpoints de rollback.
