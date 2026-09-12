# Arquitetura — dgVoodoo Config Engine (projeto documental, sem implementação)

> **Estado da fase:** documental/arquitetural. Nenhum código implementado; nenhum módulo de produção, template, DLL, perfil, AUTO ou heurística foi alterado. Entrega única: este arquivo.
>
> **Alvo:** futuro engine/schema para **ler, validar, resolver camadas e serializar** `dgVoodoo.conf`, preservando 100% do comportamento atual validado (dgVoodoo2 2.87.4, D3D9 x86 → D3D11 FL11.0).

## 1. Fontes obrigatórias (lidas integralmente)

| Fonte | Papel |
|---|---|
| `PROMPT_PROXIMA_ETAPA_ARQUITETURA.md` | Escopo, regras, arquitetura conceitual, requisitos mínimos, personalizações a considerar, entrega. |
| `README.md` | Regras vigentes do módulo (vendor ativo, DX11, watermark=false, UTF-8 sem BOM, congelamento). |
| `RELATORIO_FINAL_DgVoodoo2874_FieldValidated.md` | Validação funcional aprovada e correção do BOM (leitura tolerante; escrita sem BOM). |
| `Mapa_dgVoodoo_2.87.4_Aika.md` | Catálogo de 94 chaves ativas + `LogToFile` comentada; domínios, equivalências CPL, dependências, classes 1–6, lacunas. |
| `Overlay_AIKA_dgVoodoo_2.87.4_Auditado_codigo.md` | Auditoria do código: 14 chaves explicitamente controladas (12 fixas + 2 de perfil) e 80 herdadas; leitura/escrita; AUTO; invariantes; serialização. |

Referências de comportamento atual citam estas fontes como verdade documental. Linhas `S:nnn`/`U:nnn` referem-se ao snapshot auditado no Overlay.

**Terminologia de proveniência:** este documento adota **"template dgVoodoo2 2.87.4 adotado/validado pelo projeto"** para o arquivo base (hash `3c7da2fa…`) e evita afirmar "bytes oficiais": a autenticidade junto ao fornecedor não foi comprovada por fonte independente. O vínculo comprovado é a adoção pelo projeto (hashes internos do template/DLL + validação funcional de campo registrada no RELATORIO).

## 2. Objetivo, princípios e fronteiras

### 2.1 Objetivo

Projetar um engine futuro com responsabilidades explícitas e testáveis:

1. **Ler** `dgVoodoo.conf` de forma tolerante, preservando o que não entende.
2. **Validar** sintaxe, domínio, dependências e invariantes do AIKA.
3. **Resolver** camadas (vendor → overlay fixo → perfil → personalização futura) com origem rastreável.
4. **Serializar** de forma conservadora (UTF-8 sem BOM; CRLF; mínima perturbação).
5. **Comparar** (`diff`) e **provar paridade** com o gerador atual antes de integrar.

### 2.2 Princípios (derivados do mapa e do overlay)

- **Comportamento atual é a especificação.** Nenhuma melhoria pode alterar o conf efetivo validado em campo.
- **Identidade é seção + chave.** Nomes repetidos em seções distintas (ex.: `General.Color` vs. Glide/DirectX; `GeneralExt.ColorSpace` vs. `DirectXExt.Default3DRenderFormat`) são campos distintos.
- **Quatro níveis de valor não são "default".** Separar: literal do template do vendor; default interno comprovado (ou desconhecido) da DLL; regra fixa do AIKA; override de perfil/usuário.
- **Evidência ≠ fato.** Domínio provado em comentário, aceitação pelo CPL/DLL e efeito no Aika são coisas diferentes e coexistem como metadados.
- **Vazio, ausente e comentado são estados distintos.** `DesktopResolution=` (vazio), chave inexistente e `;LogToFile = false` (comentada) não podem ser colapsados.
- **Não inventar limites ou gramática.** Ranges de cor, IDs, gramática de resolução, máscaras e limites de memória com lacuna permanecem "desconhecido" até evidência.
- **Escrita conservadora e round-trip controlado.** Uma mudança por vez em cópia isolada; nunca no conf validado desta fase.
- **Conhecido + desconhecido coexistem.** O engine preserva campos/ordem/comentários desconhecidos para não quebrar chaves futuras do vendor nem o arquivo vigente.

### 2.3 Fronteiras (não-objetivos desta fase)

- Não implementar engine/schema.
- Não expor controles avançados.
- Não decidir unilateralmente itens em aberto (seção 13); decisões são propostas para validação.
- Não reconstruir a semântica interna da DLL ofuscada a partir de suposição.

## 3. Modelo de camadas e pipeline conceitual

```
Vendor Template (dgVoodoo2 2.87.4 adotado/validado pelo projeto)
   ↓
Schema/Catálogo (metadados por seção+chave; não altera valores)
   ↓
Overlay fixo AIKA (12 fixas + base: PRESET_CONF)
   ↓
Perfil (2 chaves: Filtering/Antialiasing — PERFIS_CONF)
   ↓
AUTO (somente resolução de perfil; fora do engine — não é chave INI)
   ↓
Personalizações avançadas futuras (camada nova, opcional, conceitual)
   ↓
Configuração efetiva (bytes finais validados, sem BOM, prontos para instalar)
```

### 3.1 Papéis de cada camada

| Camada | Papel | Exemplo atual (comprovado no Overlay) |
|---|---|---|
| **Vendor Template** | Fonte byte a byte (template dgVoodoo2 2.87.4 **adotado/validado pelo projeto**); origem das 80 chaves herdadas + literais | `third_party/dgvoodoo2/dgVoodoo.conf` (hash `3c7da2fa…`) |
| **Schema/Catálogo** | Metadados (tipo, domínio, dependências, classe, lacuna, evidência) por `seção+chave`; **não grava** | Base documental do Mapa (94 ativas + LogToFile) |
| **Overlay fixo AIKA** | Regras estruturais obrigatórias do produto | PRESET_CONF (S:257–272 do snapshot): 12 fixas + base Balanced (Filtering/Antialiasing na ativação) |
| **Perfil** | Diferenciais de `Filtering`/`Antialiasing` | performance (`trilinear`/`appdriven`), balanced (`16`/`2x`), quality (`16`/`4x`) |
| **AUTO** | Resolve **perfil** por hardware (RTX 4050 ~6 GiB → Quality/ALTA); não grava chave "auto" | `hardware_detector` + `U:657–660`; validação `S:1100–1111` |
| **Personalização futura** | Overrides opcionais de usuário sobre chaves elegíveis | candidatos da seção 11 (conceitual) |
| **Configuração efetiva** | Resultado final serializado | conf sem BOM instalado no cliente |

### 3.2 Regras estruturais do pipeline

- Template sempre lido como origem da geração (nunca o conf instalado): geração = template + PRESET_CONF + PERFIS_CONF (S:473–480); ativação copia template e reescreve a base (S:892–895).
- O engine futuro deve **reproduzir exatamente** essa ordem e rejeitar perfil/estado desconhecido como o serviço atual (sem fallback silencioso no gerador; normalização apenas para exibição legada).
- `AUTO` nunca emite token no INI; não deve ser modelado como valor de chave.

## 4. Modelo documental (lossless) e schema semântico

### 4.0 Duas representações complementares

O engine opera sobre **duas representações distintas e complementares**. O schema semântico **não substitui** o modelo documental; ele indexa/valida **sobre** ele.

**A) Document Model / Lossless Model** — o que permite round-trip fiel:

| Elemento | Contém/preserva |
|---|---|
| Nós ordenados | sequência ordenada de linhas do arquivo |
| Seções | cabeçalho `[Seção]` e sua posição |
| Chave/valor | linha `chave = valor` e sua posição |
| Linhas vazias | preservadas na ordem |
| Comentários | linhas `;` (e blocos), preservados |
| Texto bruto | representação textual integral de cada linha |
| Duplicatas | preservadas e contadas (sem deduplicar) |
| Desconhecidas | linhas/seções não catalogadas, preservadas |
| Terminadores | CRLF/LF por linha, newline final observado |
| BOM/encoding | BOM presente/ausente e encoding observado na entrada |
| Finalidade | fidelidade para **lossless round-trip** e diff estrutural |

**B) Semantic Schema / Index** — o que permite validar e resolver camadas:

| Campo | Descrição |
|---|---|
| `section`/`key` | índice por `[Seção].chave` (chave global: `section=None, key="Version"`) |
| `tipo` | B/E/I/S/L/composto + estados (4.2) |
| `domínio` | domínio comprovado + lacunas |
| `regra AIKA` | fixa/overlay ou ausente |
| `perfil` | par aplicável por perfil |
| `dependências` | relações (tipos na 6.4) |
| `origem` | camada produtora do valor efetivo (9.3) |
| `permissões` | quais camadas podem escrever a chave |
| `evidência` | fonte/confiança documental de cada campo |

Regras:

- Toda operação de **leitura/serialização/round-trip** atua no Document Model; o índice semântico apenas consulta/valida sem reordenar nem reescrever linhas.
- O índice semântico pode apontar para o nó do Document Model (origem da linha), mas nunca descarta linhas que não compreende.
- `diff()` estrutural e byte a byte opera no Document Model; validação/`origem`/conflito operam no índice semântico.

### 4.1 Identidade e registro por campo

Identidade canônica: **`[Seção].chave`** (ex.: `[General].OutputAPI`, `[DirectX].dgVoodooWatermark`).

**Exceção — chave global `Version`:** `Version` não pertence a nenhuma seção do arquivo (vive no topo, antes de `[General]`). Representação interna conceitual inequívoca: **`section=None, key="Version"`**. A notação documental **`[GLOBAL].Version`** é permitida apenas em documentação/tabelas; o engine **não deve criar nem escrever** uma seção `[GLOBAL]` no `dgVoodoo.conf`.

Registro conceitual de campo:

| Campo | Descrição |
|---|---|
| `identidade` | `[Seção].chave` |
| `tipo` | B/E/I/S/L/composto + estados vazio/ausência (4.2) |
| `domínio_evidência` | Fonte da verdade: comentário do template F, CPL U, manual G, código S, campo C, DLL D |
| `domínio` | Conjunto aceito/observado; lacunas `?`/`D` |
| `valor_template` | Literal do template do vendor (V) |
| `default_interno` | Default da DLL quando ausente — só se comprovado; senão `desconhecido` |
| `regra_aika` | Fixa (overlay) ou ausente |
| `perfil` | Par aplicável por perfil (Filtering/Antialiasing) ou ausente |
| `personalização_futura` | Reservado p/ camada futura (seção 11) |
| `permissões` | Camadas que podem escrever a chave (4.0 B / 7.2) |
| `dependências` | Relações entre chaves tipadas (6.4) |
| `classe_exposição` | Classes do Mapa (1 fixo, 2 perfil, 3 seguro, 4 experimental, 5 irrelevante, 6 investigação) |
| `lacuna` | Códigos E/D/S/X conforme Overlay §5 |
| `congelado` | Boolean — todas as 94 ativas são congeladas hoje |

### 4.2 Tipos e sua modelagem

| Tipo | Definição conceitual | Exemplos no catálogo |
|---|---|---|
| **B — booleano** | Domínio textual `true`/`false` (não assumir `0/1`, `yes/no`, case) | `dgVoodooWatermark`, `FullScreenMode`, `DisableAndPassThru` |
| **E — enum textual** | Conjunto nomeado; não reduzir o INI ao dropdown do CPL (nem o contrário) | `OutputAPI`, `ScalingMode`, `Filtering` (`appdriven…trilinear`, `1..16`), `Antialiasing` (Off/appdriven/2x/4x/8x D9; 16x ?) |
| **I — inteiro** | Numérico com unidade/limites quando comprovados | `VRAM` (MB ou `2GB`), `DeframerSize` 0..16, `Brightness/Color/Contrast` (100; range ?) |
| **S — string estruturada** | Gramática própria, validada por padrão | `Resolution` (gramática R), `DisplayROI`, `DesktopResolution` |
| **L — lista** | Separador e itens; cardinalidade | `WindowedAttributes`, `ExtraEnumeratedResolutions` (≤16), `SystemHookFlags` |
| **Compostos** | Máscaras/IDs/hex ≠ ordinais | `DisplayOutputEnableMask`, `Version` (`0x287`), IDs de adaptador |
| **vazio** | Presente após `=` sem conteúdo; ≠ ausente | `DesktopResolution=`, `AdapterIDType=` |
| **ausente** | Chave/linha não existe | política própria (4.3) |
| **comentado** | Linha iniciada por `;` | `;LogToFile = false`; não é chave ativa |

### 4.3 Estados e políticas por presença

| Estado | Política conceitual |
|---|---|
| Chave presente, valor válido | Valor candidato; validar domínio/dependências |
| Chave presente vazia (`=`) | Estado `vazio`; não colapsar em `false`/`0`/ausência |
| Chave ausente no template | Não inserir automaticamente (Overlay S:405–431); fixa ausente = erro de invariante; herdada ausente = tolerar/registrar |
| Linha comentada | Preservada; nunca chave ativa |
| Comentário inline | Modelado à parte (4.5) |
| Desconhecida | Preservada; marcada `desconhecida` (4.6) |
| Duplicata | Detectada e registrada (4.7) |

### 4.4 Catálogo: classes atuais (sem alterar valores)

O schema cataloga o que o Overlay já provou:

- 1 chave global (`Version`; identidade interna `section=None, key="Version"`, notação documental `[GLOBAL].Version`); seções ativas: General 15, GeneralExt 16, Glide 16, GlideExt 3, DirectX 16, DirectXExt 23, Debug 4 → **93 em seções + 1 global = 94 ativas** (+ `;LogToFile` comentada).
- **14 explicitamente atribuídas** (12 fixas + 2 de perfil) — tabela A do Overlay; origem PRESET_CONF/PERFIS_CONF.
- **80 herdadas** do template (incluindo DirectX `ForceVerticalSync`, `Mipmapping`, `Resolution` não constantes do PRESET_CONF) — **todas congeladas**.
- Glide/GlideExt/Debug: **classe 5** no caminho D3D9 — preservar texto, não expor.

### 4.5 Comentários

| Tipo | Regra conceitual |
|---|---|
| Comentário em linha própria (início `;`) | Preservado; não corresponde a chave ativa |
| Comentário inline após valor em linha sobrescrita | Comportamento atual: **não preservado** na linha alterada (Overlay §9.5). Engine futuro: manter paridade **ou** melhoria controlada declarada — nunca mudança silenciosa |
| Blocos de comentário/ordem | Conteúdo e ordem relativa preservados |

### 4.6 Chaves e seções desconhecidas / futuras do vendor

- Leitura tolerante preserva linhas e blocos não catalogados (não eliminar extensões de vendor).
- Validação não bloqueia leitura por desconhecido; marca `desconhecido` e aplica política por camada (herdada: manter; fixa: só se existir; personalização sobre desconhecido: exigir confirmação de catálogo).
- `Version = 0x287` **não identifica patch**; proveniência usa hash do arquivo + metadados (4.8).

### 4.7 Duplicatas

- Parser atual pode alterar todas as correspondências; leitor de validação retorna a primeira (Overlay §9.6).
- Engine futuro: **detectar e reportar**; política inequívoca (primeira vence na leitura efetiva? erro de validação?). Item em aberto (seção 13). Hoje o template adotado (2.87.4) não contém duplicatas.

### 4.8 Proveniência e hash do template

- Registrar por geração: `template_hash` (SHA-256), caminho do template, tamanho, primeiros bytes (sem BOM) e identificação do componente quando disponível (DLL: hash `db1c445f…`, ProductVersion `2.8.7.4`, x86).
- `Version=0x287` é literal estrutural preservado (classe 1), **não** substituto de proveniência.
- Metadados de proveniência do estado do serviço ficam fora do INI (evolução futura documentada, não implementada).

## 5. Leitura tolerante — políticas de parsing

Objetivo: reproduzir e **superar de forma provada** o leitor atual (`S:385–402`, `S:434–458`, `S:461–480`) sem alterar comportamento do conf efetivo.

| Tema | Política conceitual |
|---|---|
| Encoding na leitura | Tolerante a BOM inicial (`utf-8-sig`); **sem** fallback automático ANSI/UTF-16 (comportamento atual); erro explícito se decodificação falhar |
| Encoding na escrita | **UTF-8 sem BOM** obrigatório na saída **ativa** (modo B da 8.0; regra validada — RELATORIO); cópia de restauração preserva bytes originais; modo lossless (A) preserva o encoding/BOM de entrada |
| Quebras de linha | Entrada: `splitlines`; saída: **CRLF** (comportamento atual S:411/431). Newline final: hoje não garantido; política futura em aberto (13) — registrar presença/ausência e decidir com paridade |
| Nome de seção/chave | Case preservado; correspondência atual por strip sem normalização de case (S:405–431). Não assumir case-insensitivity do parser do wrapper |
| Comentários | Linhas `;` ignoradas como chave, preservadas como texto |
| Inline | Não confundir texto após `=` com comentário; política de preservação por campo (4.5) |
| Ordem | Ordem de linhas e seções do template preservada; nova camada só altera valores de chaves existentes (não insere seções/chaves) |
| Desconhecidas | Preservadas; reportadas |
| Duplicatas | Detectadas; política inequívoca (4.7) |
| Erros | `OSError`/`UnicodeError` tratados como erro de leitura explícito (sem troca de encoding automática) |

### 5.1 Pré-condições de arquivo (registro, não imposição hoje)

Antes de ler, registrar: tamanho, SHA-256, primeiros bytes (confirmar `3B` = `;`, ausência de `EF BB BF`), presença/ausência de newline final, contagem CRLF/LF. Serve para diagnóstico e para a prova de paridade (seção 12).

## 6. Validação em camadas

Separar níveis (Mapa §8 item 10), cada um com saída e política próprias:

| Nível | Objeto | Falha típica → política conceitual |
|---|---|---|
| **Sintaxe** | Linhas, `seção`, `chave=valor`, encoding, quebras | Arquivo ilegível/estrutura inválida → erro explícito (nunca "consertar" silenciosamente) |
| **Semântica** | Tipo do campo (B/E/I/S/L/composto) | Valor não converte/tipo errado → erro por campo com identidade e linha |
| **Domínio** | Valor dentro do domínio conhecido | Escrita de camada (overlay/perfil/personalização) fora do domínio comprovado → **erro bloqueante**; valor herdado do template desconhecido do schema → **preservar + `unknown_to_schema`** (6.3); não estender lista silenciosamente |
| **Dependências** | Relações entre chaves, tipadas (6.4) | Política por tipo: `hard_constraint` → erro; `conditional_effect` → sem efeito ≠ inválido; `compatibility_warning` → aviso |
| **Invariantes AIKA** | Regras fixas obrigatórias | Invariante violada → **erro bloqueante**, nunca override |
| **Leitura efetiva pelo wrapper** | Se o dgVoodoo realmente consome o valor (fora do alcance estático) | Não validável por leitura → validação visual/desempenho em campo (fora desta fase) |

### 6.1 Categorias de erro (conceitual)

- **bloqueante**: impede gerar/instalar (ex.: invariante, template inválido, tipo/domínio crítico).
- **reportável**: valor válido porém com lacuna/desconhecido/duplicata — gera aviso estruturado, não bloqueia.
- **ignorável com registro**: linhas desconhecidas preservadas (mantém compatibilidade futura).

### 6.2 Consequência: nunca transformar erro em correção automática

Regra derivada do RELATORIO (BOM): um arquivo que o wrapper considera inválido é pulado e o wrapper cai em defaults. Portanto **toda serialização ativa deve ser validada antes da instalação** (primeiros bytes, conteúdo efetivo, invariantes), e qualquer divergência deve **parar** a operação — jamais "corrigir" gerando um arquivo diferente do esperado.

### 6.3 Domínio desconhecido: escrita vs. herança

A política depende de **quem está escrevendo** o valor:

| Situação | Política |
|---|---|
| Camada que escreve (overlay fixo, perfil ou personalização futura) tenta gravar valor **fora do domínio comprovado** da chave | **Erro bloqueante** — a camada nunca inventa valor fora do catálogo |
| Valor **já presente/herdado do template do vendor** (linha intacta) mas **desconhecido para o schema** (ex.: token de patch futuro) | **Preservar + registrar** `unknown_to_schema` (aviso estruturado); **sem rejeição automática** e sem sobrescrever |
| Camada futura tenta escrever chave desconhecida do schema | Exigir confirmação de catálogo antes (4.6) |

Essa assimetria é obrigatória para **compatibilidade conservadora com patches futuros**: o que o vendor traz e o schema ainda não conhece não pode ser tratado como erro — apenas como desconhecido registrado. O que as camadas do AIKA pretendem produzir, sim, precisa passar pelo domínio comprovado.

### 6.4 Dependências: tipos de relação

Nem toda relação entre chaves é erro. Classificar de forma conceitual:

| Tipo | Significado | Exemplo |
|---|---|---|
| **hard_constraint** | A chave/valor só é coerente se a condição for verdadeira; violação = erro | `D3D12BoundsChecking` só tem efeito em backend D3D12 — em backend D3D11 é **irrelevante/inativo**, não configuração inválida |
| **conditional_effect** | A chave só tem efeito quando outra condição/caminho estiver ativo; sem efeito ≠ inválido | `KeepFilterIfPointSampled` é **condicional ao `Filtering` forçado** (só atua quando há filtro forçado e textura point-sampled) |
| **compatibility_warning** | Relação de risco/compatibilidade que gera aviso, sem bloquear | `RTTexturesForceScaleAndMSAA` com resolução/MSAA forçada pode alterar efeitos em render targets; `SuppressAMDBlacklist` em GPU NVIDIA |

O campo `dependências` do registro de campo (4.1) deve listar relações já tipadas (6.4), e a validação deve aplicar a política do tipo — nunca transformar toda relação em erro.

## 7. Resolução de camadas, conflitos e invariantes

### 7.1 Precedência

```
Vendor Template (linha original)
  <  Overlay fixo AIKA (12 fixas + base Balanced na ativação)
  <  Perfil (Filtering/Antialiasing)  [AUTO resolve o perfil, fora do engine]
  <  Personalização avançada futura (camada nova, seção 11)
```

- Só valores de chaves **existentes no template** são alterados (o helper atual não insere chaves/seções — Overlay §4).
- A base `Balanced` é materializada na ativação/Reaplicar (`preset="Aika Recomendado"`); perfis aplicam seus pares; AUTO apenas escolhe o perfil.

### 7.2 Conflitos entre camadas

| Conflito | Política conceitual |
|---|---|
| Perfil tenta alterar chave fixa (não-Filtering/Antialiasing) | Rejeição em schema (catálogo marca quais chaves cada camada pode tocar) |
| Personalização futura vs. invariante AIKA | Invariante vence; personalização rejeitada com mensagem |
| Personalização futura vs. perfil | Política em aberto (Mapa §8 item 11): alterar perfil? sobrepor? remover no Reaplicar? — **decisão de produto, não desta fase** |
| Chave fixa ausente do template | Erro de invariante (o serviço atual só substitui linha existente — Overlay §12 nota) |
| Duplicata com valores distintos | Detectada → primeira vence na leitura efetiva ou erro, conforme política 4.7 |

### 7.3 Invariantes AIKA (fonte: Overlay §12; congeladas)

| Invariante | Como o engine deve representar |
|---|---|
| `[General].OutputAPI = d3d11_fl11_0` | Fixa obrigatória (DX11, nunca DX12) |
| `[DirectX].dgVoodooWatermark = false` | Fixa obrigatória; nenhuma camada/perfil pode variar |
| Saída ativa **UTF-8 sem BOM** | Invariante de serialização (não é chave) |
| `Adapters=1`, `FullScreenMode=false`, `DisableScreenSaver=true`, `VRAM=1024`, `FastVideoMemoryAccess=true`, `KeepFilterIfPointSampled=true`, `VideoCard=internal3D`, `DisableAndPassThru=false`, `AppControlledScreenMode=true`, `DisableAltEnterToToggleScreenMode=true` | Fixas do overlay (12 ao total com as duas acima) |
| Perfis só tocam `Filtering`/`Antialiasing` | Regra de camada no schema |
| Templates/DLL nunca são destinos de escrita pública | Regra de fluxo (origem vs. destino) |
| Restauração preserva bytes do original | Regra de fluxo (fora do engine de geração) |

O serviço atual implementa esses valores por mapas + substituição de linha; o engine futuro **centraliza** a regra no schema e **valida o resultado**, sem mudar o conf efetivo.

## 8. Escrita conservadora e round-trip

Referência de comportamento atual (Overlay §9): o serviço lê por `utf-8-sig`, reescreve o arquivo inteiro via substituição de linhas, junta com CRLF, preserva linhas não mapeadas e comentários de linha própria, **não** preserva comentário inline em linha sobrescrita, não insere chaves/seções ausentes e não deduplica.

### 8.0 Dois modos de serialização

Distinguir explicitamente **dois modos**, com invariantes e usos diferentes:

**A) Lossless Round-Trip**
- Objetivo: reproduzir os **bytes de entrada** sempre que tecnicamente representáveis, sem alteração semântica.
- Preserva BOM observado (se houver), terminadores originais, newline final, ordem, duplicatas, desconhecidas e comentários.
- Uso: prova do engine (estágio 1–4 da seção 12) e diff estrutural.
- **Não** normaliza o arquivo; qualquer diferença não representável (ex.: codificação não suportada) é declarada como limitação, nunca "corrigida".

**B) Active AIKA Serialization**
- Objetivo: produzir a **saída destinada ao cliente** (configuração efetiva instalável).
- Invariantes vigentes: **UTF-8 sem BOM**, **CRLF**, demais regras ativas (invariantes AIKA, seção 7.3).
- Uso: Ativar/Reaplicar e aplicação de perfil (somente após estágio 5 da migração).
- Preservação seletiva: mantém linhas herdadas não mapeadas e comentários de linha própria; segue as políticas de 8.1.

**Não confundir** prova de round-trip com normalização do arquivo ativo: o modo A prova fidelidade do modelo; o modo B normaliza segundo as invariantes do produto. Um teste de round-trip **não** é teste do serializador ativo, e vice-versa.

### 8.1 Regras conceituais de escrita (modo ativo e restauração)

| Regra | Política |
|---|---|
| Destino | Sempre uma **cópia** (cliente/backup/temporário); nunca o template (`S:473,888,893`) |
| Atomicidade | Escrita atômica por arquivo (tmp+flush+fsync+`os.replace`) — não garante atomicidade do ciclo DLL/conf/estado como um todo (Overlay §9.9) |
| Encoding | UTF-8 **sem BOM** na saída ativa |
| Terminadores | CRLF na saída (comportamento atual); newline final: registrar e decidir com paridade (em aberto, seção 13) |
| Formatação | Preservar prefixo até o whitespace após `=`; substituir apenas o valor (Overlay §9.5) |
| Linhas não mapeadas | Preservadas (texto e ordem) |
| Comentários | Linha própria: preservada; inline em linha alterada: política 4.5 |
| Chaves/seções ausentes | Não inserir automaticamente |
| Duplicatas | Não deduplicar silenciosamente; reportar (4.7) |
| Restauração | Cópia binária do backup original (não transcodificar) |

### 8.2 Round-trip conservador (modo A / lossless — procedimento conceitual)

1. Ler bytes do arquivo → **Document Model** (registrar hash/pré-condições, BOM e terminadores observados).
2. Serializar **sem nenhuma alteração** (modo lossless) → comparar bytes/texto com o original.
3. Aplicar **uma** alteração controlada em cópia isolada → serializar → comparar: só a linha alvo mudou (valor) e o restante permanece byte a byte (ou com diferenças declaradas: newline final, encoding).
4. Registrar mudanças colaterais (ex.: comentário inline perdido) como relatório, nunca como silêncio.

O round-trip NUNCA é executado contra o conf validado de produção nesta fase; é pré-requisito de prova do engine futuro (seção 12).

### 8.3 Diferença entre "round-trip do engine" e "reparo do arquivo"

O engine não "conserta" arquivos instalados arbitrariamente. Ele gera a configuração a partir do template + camadas. O arquivo do cliente fora do esperado é tratado pelos fluxos existentes (backup/estado/modificação externa), não por reescrita automática.

## 9. `diff()` e origem do valor efetivo

### 9.1 Objetivo

Prover, para qualquer chave ou para o arquivo inteiro:

- **diferenças** entre dois artefatos (template × overlay × perfil × efetivo; atual × futuro; bytes × texto);
- **origem do valor efetivo** (qual camada produziu o valor final de `[Seção].chave`).

### 9.2 Comparação textual (conceitual)

`diff(a, b)` deve operar sobre linhas **preservando ordem**, reportando:

| Tipo de diferença | Exemplo |
|---|---|
| Valor alterado | `[DirectX].Antialiasing: 2x → 4x` |
| Chave inserida/removida | apareceu/sumiu linha (bloqueado hoje na geração) |
| Seção inserida/removida | bloco novo/ausente |
| Apenas formatação | espaçamento, CRLF, newline final (reportar separado, sem "sujar" o diff de valor) |
| Comentário | linha de comentário alterada/adicionada/removida |
| Ordem | mesma linha em posição diferente (reportar como movimento) |
| Encoding/bytes | presença/ausência de BOM, hash de arquivo |

### 9.3 Origem do valor efetivo

Para cada `[Seção].chave` do efetivo, o engine deve expor um registro de origem:

- `origem ∈ {template, overlay_fixo, perfil, personalizacao_futura, estado}`;
- `valor_efetivo` e `linha_origem` (linha no template de onde veio a linha);
- `camada_que_alterou_por_ultimo` e `camadas_que_tentaram` (para conflitos);
- `template_hash` e `template_version` associados à geração.

Exemplos esperados (comportamento atual congelado):
- `[DirectX].dgVoodooWatermark` → origem `overlay_fixo`, valor `false` (invariante).
- `[DirectX].Antialiasing` → origem `perfil` (após aplicar perfil) ou `overlay/base` (ativação Balanced = `2x`); `AUTO` registra perfil resolvido fora do engine.
- 80 herdadas → origem `template`, valor igual ao literal V/A.

### 9.4 Uso na prova de paridade

Na comparação (estágios 3–4 da seção 12):

- **bytes e valores efetivos** do engine novo são comparados diretamente à saída do **gerador atual** (que continua sendo a referência de comportamento);
- os **metadados de origem do engine novo não podem ser comparados ao gerador antigo**, pois ele não os produz — origem não é referência produzida pelo gerador atual;
- a **origem** deve ser validada contra a **baseline documental auditada** (Overlay): **12 fixas + 2 de perfil + 80 herdadas**, com os valores efetivos esperados (ex.: `dgVoodooWatermark=false` origem `overlay_fixo`; `Antialiasing` origem `perfil`/base; herdadas origem `template`).

A comparação é feita em modo shadow (seção 12), sem tocar produção.

## 10. Superfícies públicas e fronteiras de integração (conceitual)

Sem implementação. Define onde o engine futuro se encaixaria sem alterar a página/serviço hoje:

| Área | Fronteira conceitual |
|---|---|
| Serviço (`dgvoodoo_service.py`) | Continuaria dono dos fluxos (detectar/ativar/perfil/restaurar/estado). O engine entraria como biblioteca de leitura/validação/geração/diff substituindo o substituidor textual **somente após** prova de paridade |
| Página (`dgvoodoo_page.py`) | Não conhece schema; consumiria apenas resultados (perfil efetivo, origem, avisos) via API futura |
| Hardware/AUTO | Continua resolvendo perfil; engine não decide hardware |
| Templates/DLL | Imutáveis como hoje; engine lê, não grava |
| Estado (`estado.json`) | Pode receber metadados de proveniência/versão do template em evolução futura (fora do INI) |
| Testes | Suíte atual 812/812 permanece como **porta de regressão**; paridade exigida antes de qualquer substituição |

Regra de ouro: enquanto não houver paridade determinística comprovada em shadow, **nada é trocado** — o substituidor atual continua sendo o produtor de referência do conf.

## 11. Personalizações avançadas futuras (somente conceitual)

Nenhuma é implementada nem exposta nesta fase. Lista derivada do Mapa §7 e do Overlay §14 (registro separado). `DirectX.KeepFilterIfPointSampled` **já pertence ao overlay atual** (fixo `true`) e não é tratado como recurso ausente.

### 11.1 Candidatas consideradas conceitualmente

| Chave | Situação atual | Gate antes de qualquer exposição futura |
|---|---|---|
| `GeneralExt.FPSLimit` | Herdado `0` | Confirmar domínio/sintaxe racional/teto; testar com VSync/limitador do jogo/driver |
| `General.CaptureMouse` | Herdado `true` | Testar foco, Alt-Tab, multimonitor |
| `DirectX.ForceVerticalSync` | Herdado `false` | Descrever como "não forçar"; testar janela/fullscreen; combinar com FPSLimit |
| `General.Brightness/Color/Contrast` | Herdados `100` | Confirmar range/passos; neutro 100; restaurável |
| `GeneralExt.CursorScaleFactor` | Herdado `0` | Provar efeito no cursor do Aika |
| `GeneralExt.Resampling` | Herdado `bilinear` | Exigir caminho de escala do wrapper ativo |
| `General.KeepWindowAspectRatio` | Herdado `true` | Validar utilidade na janela atual |

### 11.2 Regras conceituais para a futura camada de personalização

- Cada chave elegível precisa: catálogo com tipo/domínio comprovado, dependências mapeadas, classe ≥ segura, validação de campo isolada e teste visual/desempenho no Aika antes da exposição.
- A personalização é uma **camada** entre perfil e configuração efetiva (seção 7.1) — nunca altera o template, o overlay fixo nem as invariantes.
- Interação com perfil (mudar perfil? sobrepor? remover ao Reaplicar?) permanece **decisão de produto em aberto** (Mapa §8 item 11); nenhuma decisão foi tomada.
- Chaves proibidas na 1ª versão de avançado (Mapa §7): resolução forçada, HDR/swapchain/ColorSpace, falsificação de GPU, tesselação, profundidade e hooks.

## 12. Migração segura — 6 estágios

Critério transversal em todos os estágios: **nunca alterar o produtor atual antes da paridade provada**; suíte 812/812 como porta de regressão a cada estágio.

| # | Estágio | Descrição | Critério de saída / gate |
|---|---|---|---|
| 1 | **Engine somente leitura** | Novo módulo/schema parseia o template e o conf instalado, produz modelo + relatório (sem gravar nada) | Round-trip vazio byte a byte (ou diferenças declaradas) sobre o template adotado (2.87.4) e o conf Quality (A); hashes `3c7da2fa…`/`ab8f2fcc…` reproduzidos |
| 2 | **Geração paralela/shadow** | Engine gera confs em memória/pasta temporária para os fluxos Ativar, Reaplicar, Performance, Balanced, Quality | Geração determinística; arquivos shadow jamais instalados |
| 3 | **Comparação com gerador atual** | `diff()` valor a valor e byte a byte entre saída do substituidor atual e do engine para mesma entrada (template + camadas) | `diff` vazio para **bytes e valores efetivos** em todos os cenários; **origem validada contra a baseline documental auditada** (12 fixas + 2 de perfil + 80 herdadas), não contra o gerador antigo (que não produz origem); divergência = falha bloqueante do estágio |
| 4 | **Paridade determinística comprovada** | Repetir estágio 3 em matriz (template adotado 2.87.4; perfis 3; AUTO→3 resolvidos; ativação/Reaplicar; com/sem BOM artificial para leitura) e gravar evidência reproduzível | Paridade 100% documentada e automatizada (bytes/valores efetivos vs. gerador atual; origem vs. baseline auditada); 812/812 PASS mantida |
| 5 | **Integração gradual ao serviço** | Trocar pontos de geração um a um, sempre com teste shadow ao lado; página/hardware/AUTO intactos | Cada troca mantém suíte verde e paridade; rollback trivial (função antiga preservada) |
| 6 | **Somente depois: controles avançados** | Expor camada de personalização (seção 11) após decisões de produto e validação Aika | Controles liberados individualmente, com gates da seção 11 |

Notas:
- O estágio 4 usa a comparação de `diff()`/origem da seção 9 como evidência, incluindo a matriz de perfis já validada em campo (RELATORIO).
- Origem do engine novo **nunca** é comparada byte a byte com o gerador antigo: é validada contra a baseline documental auditada (12 fixas + 2 de perfil + 80 herdadas); bytes/valores efetivos é que são comparados ao gerador atual.
- Qualquer incompatibilidade encontrada **para** o processo e exige decisão explícita — nunca ajuste silencioso do engine para "bater" com o atual se isso mudar semântica.

## 13. Riscos, limitações, lacunas e decisões em aberto

### 13.1 Riscos e limitações reconhecidas

- **DLL ofuscada:** defaults internos reais, parser interno do wrapper e aceitação de gramática não são extraíveis por leitura (Mapa §10).
- **Evidência de campo ≠ prova por chave:** um conf que funcionou não prova que cada chave foi consumida ou causou ganho (Overlay §3/N).
- **Semântica incompleta:** VRAM/FastVideoMemoryAccess (fixas), Bilinear2DOperations/Phong/DisableD3DTnLDevice/PrimarySurfaceBatchedUpdate e domínios de cor/escala/duração permanecem com lacunas — valores atuais continuam congelados.
- **Glide/Debug:** preservados textualmente; não participam do caminho D3D9.
- **BOM/parser do wrapper:** a falha real ocorreu no consumo pelo dgVoodoo; o engine valida a serialização, mas não substitui a validação visual/jogo.
- **Round-trip atual imperfeito:** comentário inline em linha alterada é perdido e não há garantia de newline final — o engine deve tornar isso explícito, não silencioso.

### 13.2 Decisões em aberto (não resolvidas nesta fase)

| Item | Pergunta em aberto |
|---|---|
| Duplicatas | Primeira vence na leitura efetiva ou erro de validação? (4.7) |
| Newline final | Gerar sempre com newline final ou preservar a ausência do template? (5, 8) |
| Case de nomes | Normalizar case na comparação ou manter correspondência exata? (5) |
| Comentário inline | Preservar em linha alterada (melhoria) ou manter paridade com perda atual? (4.5) |
| Default interno real da DLL | Desconhecido para a maioria das chaves quando ausentes (requer ensaio separado) |
| AUTO × personalização | Ajuste manual altera perfil, sobrepõe ou é removido no Reaplicar? (11.2) |
| Proveniência persistente | Onde gravar metadados de template/versão (estado) sem tocar o INI? |
| Extensão do schema a seções futuras | Como catalogar seções novas do vendor sem quebrar a leitura |

### 13.3 Condição para avançar além desta fase

Nenhuma destas decisões é requisito para a fase documental; são **pré-requisitos** dos estágios 4–6 da seção 12. Todas exigem evidência (ensaio/CPL/round-trip) antes de virarem regra.

## 14. Referências e vínculo com os documentos-fonte

| Assunto | Origem documental |
|---|---|
| Catálogo completo, classes 1–6, domínios, dependências, gramática R, lacunas | `Mapa_dgVoodoo_2.87.4_Aika.md` (§2–§9) |
| 94 chaves ativas; 14 controladas (12 fixas + 2 perfil); 80 herdadas; pontos de leitura/escrita; invariantes; serialização | `Overlay_AIKA_dgVoodoo_2.87.4_Auditado_codigo.md` (§4–§9, §11–§12) |
| AUTO/hardware_detector (coleta, heurística, confiança) | Overlay §7, §H |
| Watermark/UTF-8 sem BOM e correção validada | `RELATORIO_FINAL_DgVoodoo2874_FieldValidated.md` |
| Regras vigentes do módulo | `README.md` |
| Escopo, regras e requisitos desta fase | `PROMPT_PROXIMA_ETAPA_ARQUITETURA.md` |

### Notas finais

- Este documento é a **única entrega** desta fase (`docs/renderizador/dgvoodoo2/ARQUITETURA_DGVOODOO_CONFIG_ENGINE.md`). Nenhum código, template, DLL, perfil, AUTO ou heurística foi alterado.
- O conteúdo é **projeto conceitual**: define responsabilidades, modelo de dados, políticas de leitura/validação/escrita, resolução de camadas, `diff()`/origem e o caminho de migração segura em 6 estágios.
- A implementação do engine **não** foi iniciada e só deve ocorrer em fase própria, iniciando pelo estágio 1 (somente leitura) com paridade determinística como pré-condição para qualquer integração.

---

*Fim do documento de arquitetura (fase documental).*
