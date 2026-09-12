# Documentação do Renderizador — dgVoodoo2 2.87.4

Esta pasta reúne a documentação técnica consolidada do módulo **Renderizador** do AIKA Optimizer V4.1.

## Arquivos

### `Mapa_dgVoodoo_2.87.4_Aika.md`
Mapa técnico do `dgVoodoo.conf`, incluindo seções, chaves, equivalências com o dgVoodooCpl, classificação, dependências, riscos e candidatos futuros.

### `Overlay_AIKA_dgVoodoo_2.87.4_Auditado_codigo.md`
Auditoria do comportamento real do projeto. Registra:

- 94 chaves ativas no conf;
- 14 chaves explicitamente controladas pelo Optimizer;
- 12 fixas + 2 controladas por perfil;
- 80 chaves herdadas do template;
- integração AUTO;
- auditoria do `hardware_detector.py`;
- leitura, escrita, preservação e serialização do conf.

### `RELATORIO_FINAL_DgVoodoo2874_FieldValidated.md`
Registro resumido da validação funcional de campo da versão 2.87.4 e da correção do problema de BOM/watermark.

### `PROMPT_PROXIMA_ETAPA_ARQUITETURA.md`
Prompt-base para a próxima fase documental: projetar o futuro `dgvoodoo_config_engine` / schema sem modificar o comportamento de produção.

## Regras atuais importantes

- Vendor ativo: **dgVoodoo2 2.87.4 x86 / D3D9**.
- Backend validado: `d3d11_fl11_0`.
- `dgVoodooWatermark=false` é obrigatório.
- O conf ativo gerado pelo Optimizer deve ser **UTF-8 sem BOM**.
- Performance / Balanced / Quality e AUTO estão validados.
- O Renderizador atual deve permanecer congelado salvo bug real.

## Estrutura do projeto

Esta pasta é apenas documentação. Não duplicar nela a DLL ou o template oficial.

Os componentes de runtime continuam em:

`third_party/dgvoodoo2/`

## Próxima etapa

Projetar documentalmente o futuro engine/schema antes de qualquer alteração no código de produção.
