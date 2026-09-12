# Próxima etapa — Arquitetura do dgVoodoo Config Engine

Use os documentos desta pasta como fontes obrigatórias.

## Objetivo

Projetar, **sem implementar**, a arquitetura de um futuro engine/schema para ler, validar, resolver camadas e serializar `dgVoodoo.conf`, preservando 100% do comportamento atual já validado.

## Regras

- NÃO modificar código de produção.
- NÃO modificar `dgvoodoo_service.py`.
- NÃO modificar `dgvoodoo_page.py`.
- NÃO modificar `hardware_detector.py`.
- NÃO modificar templates ou DLL.
- NÃO mudar perfis.
- NÃO mudar AUTO.
- NÃO mudar heurísticas.
- NÃO criar opções avançadas ainda.

## Arquitetura conceitual a projetar

Vendor Template
→ Schema/Catálogo
→ Overlay fixo AIKA
→ Perfil
→ AUTO (somente resolução de perfil)
→ Personalizações avançadas futuras
→ Configuração efetiva

## Requisitos mínimos

Definir tratamento de:

- seção + chave como identidade;
- booleanos, enums, inteiros, strings estruturadas e listas;
- valores vazios e chaves ausentes;
- comentários e comentários inline;
- ordem das linhas e seções;
- duplicatas;
- chaves e seções desconhecidas;
- futuras chaves do vendor;
- proveniência e hash do template;
- UTF-8 sem BOM;
- CRLF e newline final;
- leitura tolerante;
- escrita conservadora;
- validação sintática, semântica, de domínio e dependências;
- invariantes do AIKA;
- conflitos entre camadas;
- round-trip conservador;
- `diff()` e origem do valor efetivo.

## Personalizações futuras a considerar apenas conceitualmente

- `GeneralExt.FPSLimit`
- `General.CaptureMouse`
- `DirectX.ForceVerticalSync`
- `General.Brightness`
- `General.Color`
- `General.Contrast`
- `GeneralExt.CursorScaleFactor`
- `GeneralExt.Resampling`
- `General.KeepWindowAspectRatio`

`DirectX.KeepFilterIfPointSampled` já pertence ao overlay atual e não deve ser tratado como recurso ausente.

## Migração segura desejada

1. engine somente leitura;
2. geração paralela/shadow;
3. comparação com gerador atual;
4. paridade determinística comprovada;
5. integração gradual ao serviço;
6. somente depois, controles avançados.

## Entrega

Criar somente:

`docs/renderizador/dgvoodoo2/ARQUITETURA_DGVOODOO_CONFIG_ENGINE.md`

Ainda NÃO implementar o engine.
