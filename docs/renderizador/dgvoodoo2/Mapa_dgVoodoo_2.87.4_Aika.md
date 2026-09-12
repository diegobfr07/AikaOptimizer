# Mapa técnico do dgVoodoo.conf — AIKA Optimizer V4.1

Análise documental inicial • 9 de setembro de 2026 • alvo informado: dgVoodoo2 2.87.4, D3D9 x86 → D3D11 FL11.0.

## 1. Escopo e evidências

Este documento analisa o arquivo recebido e as capturas do dgVoodooCpl. Não constitui uma configuração recomendada para substituir a configuração validada. Nenhum código, DLL ou arquivo de configuração foi alterado. Não foram realizados testes de execução no Aika nesta investigação.

Fontes e códigos usados no mapa:

- **F**: `dgVoodoo(1).conf` fornecido pelo usuário, incluindo comentários e valores ativos. Fonte principal para nomes, tipos e domínios.
- **U**: capturas fornecidas das abas General, Glide e DirectX. Comprovam rótulos e opções visíveis, mas não toda a gramática aceita pelo arquivo, nem efeitos internos.
- **B** (como fonte, distinto do tipo booleano nas tabelas): inspeção estática da `D3D9.dll` recebida no complemento. Cabeçalho PE, exportações e strings de versão; sem carregar/executar, modificar ou desempacotar o binário.
- **G**: [manual geral oficial](https://dege.freeweb.hu/dgVoodoo2/ReadmeGeneral/), consultado nesta data; o cabeçalho identifica 2.87.4, relançada em 2/9/2026. Usado para esclarecer o CPL e alguns pontos ausentes do arquivo.
- **C**: contexto e validação de campo relatados pelo usuário; não reproduzidos aqui.
- **H**: hipótese de impacto ou avaliação de risco do analista. Não é medição nem garantia do fornecedor.
- **?**: desconhecido, ambíguo ou ainda não comprovado.

O [índice oficial](https://dege.freeweb.hu/dgVoodoo2/Documentation/) aponta para um manual específico DirectX, mas o endereço retornou 404 nesta consulta. Não foram usados guias de terceiros para preencher as lacunas.

Identidade do material:

| Item | Resultado |
|---|---|
| Nome recebido | `dgVoodoo(1).conf` |
| Tamanho | 21.908 bytes |
| SHA-256 | `3c7da2fac3eaad369df468e80c9ba9c4db632c419799b32bbc31279d10985801` |
| Início dos bytes | `3B 3D 3D 3D…`; sem BOM UTF-8 inicial |
| Identificador no texto | `Version = 0x287` |
| Chaves ativas | 94: uma global e 93 em sete seções |
| Opção adicional comentada | `LogToFile` |
| Proveniência | Apresentado pelo usuário como oficial 2.87.4; não comparado byte a byte ao ZIP do fornecedor |

O conjunto entregue foi considerado completo conforme o complemento do usuário. A captura adicional `ec138b12-4b8f-4009-857b-39daf0177de4.png` fecha a lista de MSAA visível na aba DirectX. A ausência de capturas Ext é uma limitação de cobertura documental, não um bloqueio nem uma exigência de novo envio para concluir esta análise.

**“Default” nas tabelas significa o valor literal presente no arquivo recebido.** Não prova isoladamente o default interno da DLL quando a chave está ausente, malformada ou ignorada. As capturas são estados do CPL; o botão Apply habilitado em algumas delas também impede tratá-las como prova de configuração salva. O caminho exibido nelas é o diretório de Downloads do dgVoodoo, não uma prova do conf carregado pelo Aika.

## 2. Classificação e leitura das tabelas

| Código | Categoria | Critério e exposição futura |
|---|---|---|
| 1 | FIXO DO AIKA | Regra explícita atual, ou requisito estrutural claramente marcado como proposto. Sem controle de usuário. |
| 2 | CONTROLADO POR PERFIL | Valor resolvido pelos perfis existentes. Mostrar o resultado; edição individual somente com uma política futura de personalização. |
| 3 | AVANÇADO SEGURO | Candidato de baixo risco relativo e reversível. **Ainda precisa de validação Aika** antes da exposição. |
| 4 | AVANÇADO EXPERIMENTAL | Pode interferir na apresentação, compatibilidade, recursos ou aparência. Oculto inicialmente. |
| 5 | IRRELEVANTE PARA AIKA | Sem aplicação no caminho de execução definido. Indicar quando depende de backend/build. |
| 6 | NÃO DOCUMENTADO / PRECISA INVESTIGAÇÃO | Falta evidência para semântica, domínio ou aplicabilidade central. Não expor ainda. |

A classificação é uma decisão de produto proposta; não é uma classificação emitida pelo dgVoodoo. Uma opção pode ter semântica documentada e ainda ter efeito desconhecido no Aika. Isso não a torna automaticamente categoria 6: esta categoria é usada quando a lacuna impede uma decisão técnica minimamente fundamentada.

Convenções para todas as linhas:

- **B** = booleano; domínio textual demonstrado `true`/`false`. Não assumir `0/1`, `yes/no`, case-insensitivity ou outras grafias aceitas.
- **E** = enum textual; **I** = inteiro; **S** = texto estruturado; **L** = lista. `∅` representa valor vazio, não a string “∅”.
- **G/P** = impacto gráfico / desempenho. `?` = desconhecido. Todo impacto de desempenho no Aika está **não medido**; tendências acompanhadas de H são hipóteses técnicas.
- **Compat./risco** identifica condições conhecidas e riscos qualitativos H. “Baixo” não significa teste aprovado.
- **Ext não visto** = controle equivalente não demonstrado nas capturas. Não significa que inexista no CPL.
- Quando “dependência não estabelecida” aparece, não significa ausência de dependências.
- Relevância D9 = aplicável ou potencialmente aplicável ao caminho D3D9; não prova que o Aika use a funcionalidade.

## 3. Regras já estabelecidas pelo projeto

| Elemento | Default de F | Regra atual de C | Consequência |
|---|---|---|---|
| `[General].OutputAPI` | `bestavailable` | `d3d11_fl11_0` | Categoria 1. Preservar o backend validado. |
| `[DirectX].dgVoodooWatermark` | `true` | `false` | Categoria 1 obrigatória. Não expor como escolha. |
| Codificação | Arquivo recebido sem BOM inicial | UTF-8 sem BOM | Requisito de serialização, não uma chave do conf. |
| Biblioteca | Não definida pelo conf | D3D9.dll x86/32 bits, vendor 2.87.4 | Metadado de integração externo. |
| Performance | — | AA `appdriven`, Filtering `trilinear` | Categoria 2. |
| Balanced | — | AA `2x`, Filtering `16` | Categoria 2. |
| Quality | — | AA `4x`, Filtering `16` | Categoria 2. |
| AUTO | Não existe como chave/perfil em F | Detector resolve um dos três perfis | Política do Optimizer; não confundir com `auto`, `appdriven` ou `bestavailable`. |

Segundo C, o conf com BOM era ignorado e aparecia a watermark; depois de remover o BOM, os três perfis, AUTO e Reaplicar passaram no teste em campo. Isso fundamenta a regra do projeto. Não demonstra sozinho em qual etapa do parser ocorre a falha. G confirma genericamente que arquivos inválidos são pulados e pode haver fallback para defaults.

## 4. Catálogo completo

### 4.1 Global — 1 chave

| Chave | Default; tipo/domínio | Significado e CPL | Dependências; compat./risco | G/P; relevância | Classe; exposição |
|---|---|---|---|---|---|
| `Version` | `0x287`; literal hexadecimal; outros valores ? | Identificador do formato/configuração; sem controle U. Interpretação exata e política de migração ? (F). | Acoplado à versão suportada pelo leitor; alterar pode tornar o conf ilegível (H). Não identifica o patch 2.87.4 sozinho. | Sem efeito gráfico direto comprovado; P ?; estrutural. | **1 proposta estrutural**: preservar o literal do template do vendor; não editar na UI. |

### 4.2 General — 15 chaves

| Chave | Default; tipo/valores possíveis | Significado; equivalente CPL; evidência | Dependências | G/P | Compatibilidade, risco e relevância D9 | Classe; expor? |
|---|---|---|---|---|---|---|
| `OutputAPI` | `bestavailable`; E: `d3d11warp`, `d3d11_fl10_0`, `d3d11_fl10_1`, `d3d11_fl11_0`, `d3d12_fl11_0`, `d3d12_fl12_0`, `bestavailable` | Backend de saída; General → Output API (F/U). | GPU, driver, OS, PresentationModel; D3D12BoundsChecking só em D3D12. | G/P dependem do backend; não assumir ganho ao trocar. | Alta relevância; troca tem risco alto H. WARP é software, conforme U. | **1**, fixar `d3d11_fl11_0`; não. |
| `Adapters` | `all`; E/I: `all` ou ordinal a partir de 1 | Adaptadores habilitados; Adapter(s) to use / enable (F/U). | Inventário real e FullScreenOutput. | G indireto; P pode variar pela GPU usada H. | D9 relevante; ordinal não deve ser tratado como identidade permanente H. | **4**; só após resolver identidade e testar multigpu. |
| `FullScreenOutput` | `default`; E/I: `default` ou ordinal a partir de 1 | Saídas habilitadas; Full Screen Output (F/U/G). Em DX, default habilita monitores do adaptador. | Adapters; dispositivo escolhido pelo jogo. | Apresentação em monitor; P ?. | D9/multimonitor; risco médio H de saída diferente da esperada. | **4**; não inicialmente. |
| `FullScreenMode` | `true`; B | Escolha Full Screen / Windowed (F/U). | AppControlledScreenMode; WindowedAttributes; FullscreenAttributes. Precedência completa não comprovada aqui. | Modo da janela; P ?. | D9 relevante; risco médio H com modo do jogo. Não equivale sozinho a borderless. | **4**; não isoladamente. |
| `ScalingMode` | `unspecified`; E: `unspecified`, `centered`, `stretched`, `centered_ar`, `stretched_ar`, `stretched_ar_crt`, `stretched_4_3`, `stretched_4_3_crt`, `stretched_4_3_c64` | Escala, proporção e estilos; General → Scaling mode (F/U). | Resolução, escala realizada pelo wrapper ou display; Resampling, ROI. | Pode esticar/centralizar/estilizar; custo e cursor precisam teste H. | D9 relevante; risco médio H de distorção. | **4**; eventual subconjunto, sem CRT/C64 inicialmente. |
| `ProgressiveScanlineOrder` | `false`; B | Restringe modos enumerados a progressivos (G); mesmo rótulo U. | Modos suportados e resolução/Hz. | G/P ? no Aika. | D9 condicionado aos modos; risco médio H de reduzir escolhas. | **4**; oculto. |
| `EnumerateRefreshRates` | `false`; B | Exibir taxas por resolução no CPL e permitir override de taxa (G); mesmo rótulo U. | Resoluções e refresh suportados. | Não é limitador de FPS; P ?. | D9; risco médio H ao forçar taxa. | **4**; oculto até política de resolução/Hz. |
| `Brightness` | `100`; I observado; limites/passos ? | Brilho; slider Brightness (U). | Pipeline de cor; InheritColorProfileInFullScreenMode. | Clareia/escurece; P ?. | D9 visual; baixo risco H, mas range não comprovado. | **3**; candidato depois de confirmar range. |
| `Color` | `100`; I observado; limites/passos ? | Saturação da cor (G), slider Color/Norm (U). | Pipeline de cor. | Intensidade de cor; P ?. | D9 visual; baixo risco H; não tratar como temperatura de cor. | **3**; candidato após confirmar range. |
| `Contrast` | `100`; I observado; limites/passos ? | Contraste; slider Contrast (U). | Pipeline de cor. | Altera contraste; P ?. | D9 visual; baixo risco H; pode perder detalhes por ajuste excessivo H. | **3**; candidato após confirmar range. |
| `InheritColorProfileInFullScreenMode` | `true`; B | Herança do perfil de cor; mesmo rótulo U (F). | Só pode ser desabilitado com D3D11 explicitamente selecionado (F). | Desabilitar visa poupar recursos em hardware antigo (F); efeito Aika ?. | D9/D3D11 pertinente; risco médio H de alterar cores. | **4**; preservar inicialmente. |
| `KeepWindowAspectRatio` | `true`; B | Preserva proporção ao redimensionar janela (G); Keep window aspect ratio (U). | Modo janela/redimensionamento. | Evita deformação nessa ação; P ?. | D9 condicionado; baixo risco H. Não controla todas as formas de scaling. | **3**; candidato se UI permitir redimensionar. |
| `CaptureMouse` | `true`; B | Restringe cursor à janela/área de saída (G); Capture mouse (U). | Janela, foco, monitores; testar com FreeMouse. | Sem efeito de qualidade; P ?. | D9 usabilidade; risco baixo H, requer Alt-Tab/multimonitor. | **3**; candidato. |
| `CenterAppWindow` | `false`; B | Centralizar janela; Center app window (U). Momento/recorrência exatos ?. | Modo janela e comportamento do jogo. | Posição, sem ganho de qualidade; P ?. | D9 usabilidade; risco médio H de conflito de posição/cursor. | **4**; não inicialmente. |
| `DisableScreenSaver` | `false`; B | Desativa protetor de tela e repouso do monitor durante renderização dgVoodoo (F); Disable screen saver (U). | Renderização ativa. | Sem melhoria gráfica; P ?. | D9 usabilidade; baixo risco H. Não documenta desativação geral de suspensão do PC. | **3**; candidato. |

### 4.3 GeneralExt — 16 chaves

Para cada linha desta seção, equivalente CPL: **Ext não visto**. O nome exato do controle e suas restrições de UI permanecem pendentes.

| Chave | Default; tipo/valores possíveis | Significado e evidência | Dependências | G/P | Compatibilidade, risco e relevância | Classe; expor? |
|---|---|---|---|---|---|---|
| `DesktopResolution` | `∅`; S: resolução compacta; ex. `1920x1080`; range ? | Sobrescreve base de resolução desktop usada nos cálculos; vale para todas as saídas (F). | Cálculos de resolução/escala; monitores. | Pode mudar escala calculada; P indireto H. | D9 condicional; risco médio H em multimonitor. | **4**; só correção específica. |
| `DesktopBitDepth` | `∅`; I: `8`, `16`, `32` ou vazio | Profundidade de tela reportada; vazio usa a do desktop (F/G). | Enumeração e decisões do aplicativo. | Não confundir com precisão do render target; G/P efetivos ?. | D9 aplicabilidade exata ?; risco médio H. | **4**; oculto. |
| `DeframerSize` | `1`; I: `0..16` pixels | Borda preta contra artefatos quando resolução é forçada; 0 desativa (F). | Resolution diferente da solicitada pelo jogo. | Moldura/bordas; P ?. | D9 condicional; risco baixo/médio H de afetar bordas úteis. | **4**; vinculado ao estudo de resolução. |
| `ImageScaleFactor` | `1`; I/S: inteiro, `0` máximo; `x:3, y:2`; teto ? | Multiplicação de pixels por nearest point independente de ScalingMode (F). | Resolução de origem/saída; fatores horizontal/vertical. | Pixelização/ampliação; P ?. | D9 condicional; risco médio H de apresentação inadequada. | **4**; oculto. |
| `CursorScaleFactor` | `0`; I: `0..16`; 0 automático, 1 sem escala | Escala do cursor de hardware emulado (F). | Cursor emulado, resolução/escala do wrapper. | Tamanho do cursor; P ?. | D9 se esse cursor for usado; risco baixo H após teste. | **3**; candidato condicional, não assumir cursor Aika compatível. |
| `DisplayROI` | `∅`; S: proporção `16_9` ou tamanho `(320\|200)`, `pos:centered` ou `pos:(10\|10)` | Sub-retângulo mostrado; vazio usa imagem inteira (F). | Scaling feito pelo dgVoodoo; coordenadas/limites precisam confirmação. | Recorta conteúdo; P ?. | D9 condicional; risco alto H de esconder HUD. | **4**; não inicialmente. |
| `Resampling` | `bilinear`; E: `pointsampled`, `bilinear`, `bicubic`, `lanczos-2`, `lanczos-3` | Filtro para reamostrar imagem de saída (F). | Só quando dgVoodoo realiza scaling nesse modo. | Qualidade da imagem escalada; custo varia H, não medido. | D9 condicional; risco baixo/médio H visual. Diferente de Filtering. | **3**; candidato com dependência explícita. |
| `PresentationModel` | `auto`; E: `auto`, `discard`, `seq`, `flip_discard`, `flip_seq` | Swap effect da swapchain (F). | Backend, OS, recursos de apresentação; nem toda combinação suportada (F). | Pode alterar apresentação e desempenho; não há vencedor universal (F). | D9 com backend atual; risco alto H ao forçar. | **4**; preservar auto até ensaio próprio. |
| `ColorSpace` | `appdriven`; E: `appdriven`, `argb8888_srgb`, `argb2101010_sdr`, `argb2101010_sdr_wcg`, `argb16161616_hdr` | Espaço/formato da swapchain. Appdriven pode aceitar argb2101010 em D3D9; nos outros casos legados usa argb8888_srgb (F). | WCG: Win11 22H2; HDR: Win10 1709; display e Default3DRenderFormat (F). | Muda saída de cor/precisão; custo ?. | D9 pertinente; risco alto H de incompatibilidade/cores. | **4**; não expor como simples “melhorar cores”. |
| `WatermarkDisplayDuration` | `0`; duração em segundos; tipo numérico/range exato ?; 0/indefinido infinito | Duração das marcas habilitadas por swapchain (F). | dgVoodooWatermark ou 3DfxWatermark habilitada. | Sem marca habilitada, sem efeito útil; P ?. | Irrelevante com regra watermark=false. | **5**; não. Não usar timer para esconder marca. |
| `FreeMouse` | `false`; B | Libera movimento físico do mouse dentro da janela quando scaling emulado/resolução forçada interfere no tamanho percebido (F). | Escala, resolução, comportamento do jogo; relação exata com CaptureMouse ?. | Cursor/input; P ?. | D9 condicional; risco médio H de desalinhamento. | **4**; só correção testada. |
| `WindowedAttributes` | `∅`; L por vírgula: `borderless`, `alwaysontop`, `fullscreensize` | Atributos de aparência em janela forçada: sem borda, topo, tamanho da tela com escala interna (F). | FullScreenMode, AppControlledScreenMode, tamanho/escala. | Janela/apresentação; P ?. | D9 relevante; risco médio/alto H de conflito com borderless existente. | **4**; futuro controle composto, não três toggles soltos. |
| `FullscreenAttributes` | `∅`; L: `fake` | Força fullscreen falso por janela do tamanho da tela (F). | Modo fullscreen e prioridades entre opções. | Apresentação; P ?. | D9 relevante; risco médio H; não assumir equivalência total com WindowedAttributes. | **4**; estudar junto com modos de janela. |
| `FPSLimit` | `0`; número inteiro ou racional; 0 ilimitado; gramática racional/teto ? | Limite de FPS (F). | Limitador do jogo, VSync, driver; interação precisa teste. | Reduz teto; hipótese de carga/frametime melhores, latência pode variar H. | D9 alta relevância; risco baixo/médio H. Não garante atingir 60/120. | **3**; forte candidato: desligado/60/120 após testar. |
| `Environment` | `∅`; E: vazio/native, `DosBox`, `QEmu` | Ambiente de software em que wrapper opera (F). | Emulador/ambiente real. | G/P no ambiente nativo não demonstrados. | Sem utilidade para Aika Windows nativo definido. | **5**; não. |
| `SystemHookFlags` | `∅`; flags: `gdi`, `cursor`; separador/formato completo ? | Hook GDI para conteúdo como vídeo antigo; cursor para suprimir cursor duplo (F). | Exclusivo x86-DX; operação concreta deve existir. | Vídeos/cursor; custo ?. | Arquitetura Aika elegível, necessidade ?; risco alto H por hook. | **4**; somente diagnóstico de sintoma confirmado. |

### 4.4 Glide — 16 chaves

**Escopo comum obrigatório:** todas as linhas abaixo são categoria **5 — IRRELEVANTE PARA AIKA**, não expor. Para o caminho informado, que usa apenas D3D9.dll, não há chamada Glide a configurar. Impacto gráfico e de desempenho nesse caminho: nenhum esperado pela separação de APIs; sem ensaio de execução aqui. Risco de produto: expor controles sem efeito e confundir chaves de mesmo nome. Compatibilidade em aplicações Glide não foi validada. A classificação não afirma que sejam opções inúteis para outros jogos.

| Chave | Default; tipo/valores possíveis | Significado e CPL (F/U) | Dependências / incertezas fora do Aika |
|---|---|---|---|
| `VideoCard` | `voodoo_2`; E: `voodoo_graphics`, `voodoo_rush`, `voodoo_2`, `voodoo_banshee`, `other_greater` | Placa 3dfx emulada; 3Dfx card. | Memória e TMUs dependem da placa; matriz completa não recebida. |
| `OnboardRAM` | `8`; I em MB; U mostra 8/12 para Voodoo2 | Onboard RAM. | Domínio completo por placa ?. Não usar 8/12 como limite global. |
| `MemorySizeOfTMU` | `4096`; I em kB; U mostra 2048/4096 no estado atual | Memória por unidade de textura; Memory size / TMU. | Depende da placa; domínio completo ?. |
| `NumberOfTMUs` | `2`; I; U mostra somente 2 na Voodoo2 | Quantidade de TMUs; Number of TMUs. | Outros modelos/configuração livre podem mudar domínio; não comprovado. |
| `TMUFiltering` | `appdriven`; E: `appdriven`, `pointsampled`, `bilinear` | Filtro de textura Glide; Filtering. | Interação exata com mipmapping ?. |
| `DisableMipmapping` | `false`; B | Controle Disable mipmapping; comportamento detalhado além do rótulo ?. | Glide/mipmaps; não reutilizar como chave DirectX. |
| `Resolution` | `unforced`; S: ver gramática R adiante | Resolução forçada; Resolution. | GPU/display, scaling e refresh. |
| `Antialiasing` | `appdriven`; E: `off`, `appdriven`, `2x`, `4x`, `8x`, `16x` em F | MSAA; Antialiasing (MSAA). U só mostra até 8x. | GPU deve suportar amostragem escolhida (F); ausência de 16x na captura não apaga valor documentado. |
| `EnableGlideGammaRamp` | `true`; B | Controle Enable Glide Gamma Ramp; detalhes ?. | Rampas de gamma Glide; interação com ajustes gerais ?. |
| `ForceVerticalSync` | `true`; B | Force vSync da aba Glide. | Sincronização Glide; distinto do false em DirectX. |
| `ForceEmulatingTruePCIAccess` | `false`; B | Force emulating true PCI access; semântica interna ?. | Emulação de acesso PCI; efeito específico não comprovado. |
| `16BitDepthBuffer` | `false`; B | Controle 16 bit depth buffer; detalhes ?. | Buffer de profundidade Glide; comportamento exato ?. |
| `3DfxWatermark` | `true`; B | Marca 3Dfx; 3Dfx Watermark. | WatermarkDisplayDuration; não controla marca DirectX. |
| `3DfxSplashScreen` | `false`; B | Controle 3Dfx Splash screen; condições de exibição ?. | Inicialização Glide; sem relação comprovada com loading Aika. |
| `PointcastPalette` | `false`; B | Pointcast Palette driver build; significado técnico não comprovado. | Precisa documentação Glide se um dia entrar no escopo. |
| `EnableInactiveAppState` | `false`; B | Enable inactive app state; semântica técnica não comprovada. | Foco/inatividade sugeridos pelo rótulo, sem assumir política real. |

### 4.5 GlideExt — 3 chaves

Mesmas condições de relevância, impacto, risco e exposição de Glide: **classe 5; não expor; sem efeito esperado no caminho D3D9 definido**. CPL: Ext não visto para as três.

| Chave | Default; tipo/valores possíveis | Significado comprovado e dependências (F) |
|---|---|---|
| `DitheringEffect` | `pure32bit`; E: `pure32bit`, `dither2x2`, `dither4x4` | Seletor do efeito; diferença técnica completa entre modos não explicada em F. Relacionado a Dithering. |
| `Dithering` | `forcealways`; E: `disabled`, `appdriven`, `forcealways` | Política de dithering; condições internas exatas não explicadas em F. |
| `DitherOrderedMatrixSizeScale` | `0`; I: 0 automático, 1 normal, 2 dobro etc.; teto ? | Fator da matriz ordenada; 0 busca aparência retrô (F). Relevância condicionada ao efeito. |

### 4.6 DirectX — 16 chaves

| Chave | Default; tipo/valores possíveis | Significado; equivalente CPL; evidência | Dependências | G/P | Compatibilidade, risco e relevância D9 | Classe; expor? |
|---|---|---|---|---|---|---|
| `DisableAndPassThru` | `false`; B | Disable and passthru to real DirectX (U). Desabilitação/passagem para DirectX real segundo rótulo; mecanismo exato por API ?. | Carregamento do wrapper; outras opções deixam de ter a utilidade esperada se wrapper desativado. | Pode mudar todo caminho de renderização; P ?. | Alta relevância; risco alto H de invalidar modo Renderizador. | **1 proposta estrutural**: false enquanto ativado; desligar via restauração existente, não toggle avançado. |
| `VideoCard` | `internal3D`; E: `svga`, `internal3D`, `geforce_ti_4800`, `ati_radeon_8500`, `matrox_parhelia-512`, `geforce_fx_5700_ultra`, `geforce_9800_gt` | Identidade/modelo emulado; Videocard (F/U). Não é seleção da GPU física. | AdapterIDType/IDs e MaxVSConstRegisters restritos a svga/internal3D (F). | Efeitos de capacidades por modelo ?; P ?. | D9 efeito exato por modelo ?; risco alto H. | **4**; preservar, não copiar lista para Optimizer. |
| `VRAM` | `256`; I/unidade: MB por padrão, ou GB como `2GB`; U: 16,32,64,128,256,512,1024,2048,4096 MB | Campo VRAM da placa emulada (F/U). F comprova unidade; uso exato em D3D9 não explicado. | Modelo emulado e consultas do jogo; limites do parser ?. | G/P ?; não há prova de reserva/alocação física igual ao número. | D9 efeito precisa investigação; não igualar à VRAM detectada da RTX. | **6**; não expor nem derivar automaticamente dos 6 GB. |
| `Filtering` | `appdriven`; E/I: `appdriven`, `pointsampled`, `bilinear`, `pointmip`, `linearmip`, `trilinear`, inteiro 1..16 | Filtro de textura forçado; Texturing → Filtering (F/U). | KeepFilterIfPointSampled, mipmaps, samplers do jogo. | Altera amostragem/nitidez; maior custo possível H. Efeito visual/ganho FPS não medidos aqui. | D9 alta relevância, perfis testados C; compatibilidade não garantida para todo valor. | **2**; pelos perfis atuais. |
| `Mipmapping` | `appdriven`; E: `appdriven`, `disabled`, `autogen_point`, `autogen_bilinear` | Política de mipmaps; Texturing → Mipmapping (F/U). | Texturas/mipmaps do jogo e Filtering; alcance da autogeração ?. | Pode alterar textura à distância; custo/qualidade exatos ?. | D9 potencial; risco médio/alto H; não é ganho garantido de nitidez. | **4**; preservar appdriven até testar. |
| `KeepFilterIfPointSampled` | `false`; B | Forçar filtro só em texturas não point-sampled; Force filter only if not point sampled (F/U). | Só tem utilidade com Filtering forçado e texturas point-sampled. | Preserva essas amostragens; hipótese de proteger HUD/texto H; P ?. | D9 relevante; risco baixo/médio H, exige comparação visual. | **3**; candidato, não habilitar automaticamente agora. |
| `Resolution` | `unforced`; S: gramática R | Resolução forçada; Resolution (F/U). | ScalingMode, desktop, refresh, RTTexturesForceScaleAndMSAA. | Mais pixels podem aumentar custo GPU/memória H; HUD/efeitos podem mudar H. | D9 alta relevância; risco alto H de distorção e desalinhamento. | **4**; manter estudo separado. |
| `Antialiasing` | `appdriven`; E: `off`, `appdriven`, `2x`, `4x`, `8x` mapeados pela família F e pelo dropdown DirectX U; 16x não demonstrado em D9 | MSAA; Antialiasing (MSAA) (U/C). Captura complementar confirma Off, App driven, 2x, 4x e 8x. | GPU, formato, render targets, RTTexturesForceScaleAndMSAA. | Suaviza arestas cobertas; custo GPU/memória tende a subir H. Appdriven não significa desligado. | D9 alta relevância; 2x/4x validados C; 8x disponível no CPL, mas não validado no Aika. | **2**; pelos perfis; 8x fora dos perfis atuais, 16x ainda sem comprovação D9. |
| `AppControlledScreenMode` | `true`; B | Application controlled fullscreen/windowed state (U). | FullScreenMode e atributos; matriz exata de precedências ?. | Quem controla modo; P ?. | D9 alta relevância; risco médio H de conflito com jogo. | **4**; não modificar agora. |
| `DisableAltEnterToToggleScreenMode` | `true`; B | Disable Alt-Enter to toggle screen state (U). | Alternância de modo gerida pelo wrapper e input do jogo. | Modo/input; P ?. | D9 relevante; risco médio H de alternância involuntária. | **4**; preservar até política de janela. |
| `Bilinear2DOperations` | `false`; B | Escala bilinear em DirectDraw Blit e dados escritos por CPU (F); Bilinear DD/CPU operations (U). | Operações DD/CPU abrangidas; fronteira com D3D9 não esclarecida. | Suavização 2D quando aplicável; P ?. | Não concluir que seja otimização D3D9; relevância Aika ?. | **6**; não expor até delimitar alcance. |
| `PhongShadingWhenPossible` | `false`; B | Apply Phong shading when possible (U). O que torna “possible”, alcance D3D9 e implementação ? | Pipeline/recursos elegíveis não documentados em F. | Efeito gráfico e P no Aika desconhecidos. | Relevância ?; risco não delimitado. | **6**; não. Não prometer iluminação melhor. |
| `ForceVerticalSync` | `false`; B | Force vSync (U). Política detalhada de intervalos não fornecida. | Refresh, modo de apresentação, FPSLimit, VSync do jogo/driver. | Hipótese: menos tearing, possível alteração de latência/ritmo H; P ?. | D9 alta relevância; risco médio H, precisa teste combinado. | **3**; candidato após validar; false não prova VSync global desligado. |
| `dgVoodooWatermark` | `true`; B | Marca dgVoodoo; dgVoodoo Watermark (U). | Conf efetivamente lido; WatermarkDisplayDuration só se habilitada. | Liga/desliga marca; P não medido. | Alta relevância; regra false validada C. | **1 obrigatória**; fixar false; não. |
| `FastVideoMemoryAccess` | `false`; B | Fast video memory access (U). Mecanismo e alcance D3D9 não descritos em F. | Tipos de acesso e backend não delimitados. | G/P desconhecidos no Aika; nome não é prova de ganho. | Relevância e risco precisam investigação. | **6**; não. |
| `DisableD3DTnLDevice` | `false`; B | Disable D3D TnL device (U); comentário F diz “if disabled” para não enumerar dispositivo, contradizendo nome/rótulo. | Enumeração e T&L; alcance para D3D9 ?. | G/P ?; não inferir que true libere CPU/GPU. | Semântica ambígua, risco alto H. | **6**; preservar; precisa fonte ou ensaio controlado. |

### 4.7 DirectXExt — 23 chaves

Equivalente CPL para **cada linha**: Ext não visto; rótulo e domínio de UI pendentes. Os domínios abaixo vêm dos comentários F, não de uma interface presumida.

| Chave | Default; tipo/valores possíveis | Significado (F) | Dependências | G/P | Compatibilidade, risco e relevância | Classe; expor? |
|---|---|---|---|---|---|---|
| `AdapterIDType` | `∅`; E: vazio, `nvidia`, `amd`, `intel` | Tipo de IDs de fabricante/versão de driver reportados. | Somente VideoCard svga/internal3D; IDs individuais podem sobrescrever. | Indireto por decisões do jogo; P ?. | D9 potencial; risco alto H de caminho incorreto no jogo. | **4**; oculto. |
| `VendorID` | `∅`; ID numérico, base/range ? | Sobrescreve identificador do fabricante. | svga/internal3D; pode refinar AdapterIDType. | G/P indiretos ?. | D9 potencial; risco alto H; não é fabricante físico detectado necessariamente. | **4**; oculto, domínio precisa confirmação. |
| `DeviceID` | `∅`; ID numérico, base/range ? | Sobrescreve identificador do dispositivo. | svga/internal3D, mesmo mecanismo de override. | G/P indiretos ?. | D9 potencial; risco alto H. | **4**; oculto. |
| `SubsystemID` | `∅`; ID numérico, base/range ? | Sobrescreve identificador de subsistema. | svga/internal3D, overrides. | G/P indiretos ?. | D9 potencial; risco alto H. | **4**; oculto. |
| `RevisionID` | `∅`; ID numérico, base/range ? | Sobrescreve identificador de revisão. | svga/internal3D, overrides. | G/P indiretos ?. | D9 potencial; risco alto H. | **4**; oculto. |
| `DefaultEnumeratedResolutions` | `all`; E: `all`, `classics`, `none` | Seleciona resoluções enumeradas por padrão. | ExtraEnumeratedResolutions e filtros de bitdepth. Lista exata classics ?. | Opções disponíveis ao jogo; P indireto ?. | D9 potencial; risco médio/alto H de tirar modo necessário. | **4**; oculto. |
| `ExtraEnumeratedResolutions` | `∅`; L por vírgula, máximo 16; compacto, `max`, `max@refrate`, `max_4_3`, `max_16_9`, variantes @ | Adiciona modos expostos ao aplicativo. | Jogo aceitar resolução arbitrária; desktop/refresh. | Pode habilitar opções de resolução; custo depende da escolhida H. | D9 potencial; risco médio H; não força uso pelo jogo. | **4**; futuro diagnóstico de modo ausente. |
| `EnumeratedResolutionBitdepths` | `all`; conjunto de `8`,`16`,`32` ou all; separador ? | Filtra profundidades na enumeração. | Enumeração de resoluções e suporte do app. | G/P indiretos ?. | D9 alcance exato ?; risco médio H. | **4**; oculto. |
| `DitheringEffect` | `high_quality`; E: `high_quality`, `ordered2x2`, `ordered4x4` | Efeito de dithering; algoritmo high_quality não detalhado. | Dithering; matriz ordenada nos modos pertinentes. | Mudança visual potencial, efeito Aika ?; P ?. | D9 potencial; risco médio H visual. | **4**; não vender como melhoria universal. |
| `Dithering` | `forcealways`; E: `disabled`, `appdriven`, `forceon16bit`, `forcealways` | Política de dithering; condições internas completas ?. | Formato/bitdepth e DitheringEffect. | G/P no Aika ?. | D9 potencial; risco médio H; default não demonstra degradação. | **4**; preservar até comparação controlada. |
| `DitherOrderedMatrixSizeScale` | `0`; I: 0 automático, 1 normal, 2 dobro etc.; teto ? | Escala da matriz ordenada. | Efeito de dithering ordenado ativo. | Tamanho do padrão; P ?. | D9 condicional; risco baixo/médio H visual. | **4**; sem utilidade inicial comprovada. |
| `DepthBuffersBitDepth` | `appdriven`; E: `appdriven`, `forcemin24bit`, `force32bit` | Profundidade interna dos buffers depth/stencil. | Formatos de profundidade usados no jogo. | Precisão/custo podem mudar H; F não recomenda 32 bits. | D9 potencial; risco alto H de compatibilidade. | **4**; preservar appdriven. |
| `Default3DRenderFormat` | `auto`; E: `auto`, `argb8888`, `argb2101010`, `argb16161616` | Formato padrão da renderização 3D; auto acompanha ColorSpace. | ColorSpace; necessidades de alpha. | Precisão; 2101010 pode corromper imagem por poucos bits alpha (F); P ?. | D9 pertinente; risco alto. | **4**; preservar auto. |
| `MaxVSConstRegisters` | `256`; I: `256`, `512`, `1024` | Máximo de constantes de vertex shader exposto para DX8/9. | svga/internal3D; necessidades reais dos shaders. | Não é clock/número de núcleos; G/P ?. | D9 explícito; risco alto H; não há prova de ganho com 1024. | **4**; preservar 256. |
| `D3D12BoundsChecking` | `false`; B | Verificação de limites ao acessar constantes VS no backend D3D12, DX8/9. | **Somente backend D3D12**. | F cita custo possível e mitigação de GPU crash. Sem efeito esperado em D3D11. | D9 sim, backend atual não. | **5 no escopo atual**; reclassificar 4 se backend mudar. |
| `NPatchTesselationLevel` | `0`; I: `0..8`; 0 appdriven, 1 desativa, 2..8 força | Tesselação N-patch DX8/9. | Forçar >1 limitado ao pipeline fixo/VS1.x; desabilita modo adaptativo D3D9 (F). | Geometria e custo podem mudar; forçar é desaconselhado (F). | D9 explícito; alto risco H. | **4**; preservar 0, oculto. |
| `DisplayOutputEnableMask` | `0xffffffff`; máscara 32 bits, hexadecimal demonstrado | Bits habilitam saídas na enumeração, sequenciais entre adaptadores. | Topologia real; Adapters/FullScreenOutput. | Saídas disponíveis; P ?. | D3D9 multihead explicitamente citado; risco alto H de ocultar monitor. | **4**; não expor máscara bruta. |
| `MSD3DDeviceNames` | `false`; B | Reporta nomes originais de dispositivos Microsoft para apps que os verificam. | Enumeração e verificações do aplicativo. | G/P indiretos ?. | Alcance exato D9 ?; risco médio H. | **4**; só correção comprovada. |
| `RTTexturesForceScaleAndMSAA` | `true`; B | Aplica resolução forçada/MSAA também a texturas render target. | Resolution, Antialiasing; renderizações que exigem precisão de pixel. | Pode mudar efeitos renderizados em textura e custo H. | D9 pertinente; F adverte que false pode facilmente quebrar coisas. Risco alto. | **4**; preservar true até caso específico. |
| `SmoothedDepthSampling` | `true`; B | Suavização extra na amostragem de texturas de profundidade. | Jogo amostrar depth textures. | Efeitos dependentes dessas texturas; algoritmo/custo ?. | D9 condicional; risco médio H visual. | **4**; preservar. |
| `DeferredScreenModeSwitch` | `false`; B | Adia entrada em fullscreen até depois da inicialização do dispositivo DX para apps que falham com mudança precoce. | Inicialização, fullscreen e janela. | Comportamento de inicialização; ganho de FPS não documentado. | D9 potencial; risco médio H. | **4**; apenas correção de falha reproduzida. |
| `PrimarySurfaceBatchedUpdate` | `false`; B | Agrupa mudanças diretas na superfície primária para apresentar; false apresenta cada mudança, descrito como modo de diagnóstico. | Caminho de escrita na superfície primária; aplicabilidade D9 não esclarecida. | Pode mudar ritmo de apresentação nesse caminho; Aika ?. | Relevância D9 ?; risco indeterminado. | **6**; não expor como otimização. |
| `SuppressAMDBlacklist` | `false`; B | Suprime workaround para alguns modelos AMD com problema de texturas de cor sólida, para verificar correção no driver. | Modelos/driver AMD afetados; lista não fornecida. | Pode reintroduzir artefato (F); P ?. | Sem motivo no teste NVIDIA; frota AMD pode ser relevante. Alto risco H. | **4**; diagnóstico somente, não opção global. |

### 4.8 Debug — 4 chaves ativas + 1 comentada

Condição comum F: seção afeta **somente builds debug/spec**. Sem confirmação binária da DLL nesta análise; para uma distribuição regular, classe **5**, sem exposição no Renderizador. Se futuramente houver build de diagnóstico, reclassificar como experimental. CPL de todas: não visto. Não confundir logs do Optimizer com mensagens do wrapper.

| Chave | Default; tipo/valores possíveis | Significado/dependência (F) | G/P, compatibilidade e risco |
|---|---|---|---|
| `Info` | `enable`; E: comentário `Disable`, `Enable`, `EnableBreak`; arquivo usa minúsculas | Mensagens informativas; EnableBreak também interrompe no debugger. | Sem melhoria visual; custo de log possível H; break pode interromper execução. Aceitação geral de caixa não comprovada. |
| `Warning` | `enable`; mesmo domínio | Mensagens de aviso e opção de break. | Mesmas condições; não desligar avisos como “otimização”. |
| `Error` | `enable`; mesmo domínio | Mensagens de erro e opção de break. | Mesmas condições; não corrige a causa do erro. |
| `MaxTraceLevel` | `0`; I: `0`, `1`, `2` | 0 sem trace, 1 funções/métodos API, 2 inclui detalhes internos. | Mais trace pode custar desempenho H em build elegível. |
| `LogToFile` **comentada** | `false` apenas como exemplo comentado; B | Pretenderia gerar dgVoodoo.log se sem debugger; F declara **não implementado**, usa sempre saída debug padrão. | Classe **6** por recurso não implementado. Não gerar/ativar nem prometer arquivo de log. |

## 5. Domínios e equivalências que precisam ser preservados

### Gramática R — resolução

O comentário de F na seção Glide descreve um domínio amplo; a interface U mostra a mesma família principal na aba DirectX. Isso sustenta o mapeamento visual, mas a aceitação de toda a gramática por DirectX ainda merece round-trip no CPL da mesma versão antes de virar validador.

| Família em F | Exemplos | Observação |
|---|---|---|
| Sem override | `unforced` | Valor de ambas as seções no arquivo. |
| Dinâmica | `max`, `max_isf`, `max_fhd`, `max_fhd_isf`, `max_qhd`, `max_qhd_isf`, `desktop` | ISF significa fator inteiro (G). Defaults de cada cálculo não devem ser inventados. |
| Múltiplo | `2x`, `max_2x`, `max_isf_2x`, `desktop_2x` e famílias equivalentes | F usa `%d` como marcador; limites numéricos aceitos não especificados. |
| Subpropriedades | `h:1280, v:1024, refrate:75` | F fornece esse formato explicitamente. |
| Com frequência | `max, refrate:60`, `2x, refrate:59` | Taxa de atualização não equivale ao FPSLimit. |
| Compacta | `1024x768@60`, `512x384` | Formas textuais demonstradas. Não inferir gramática extra. |

Há um provável erro tipográfico em F: `"max_fhd_isf_%d"x`. Registrar como ambiguidade documental, não como forma a emitir. Também não reutilizar automaticamente a sintaxe textual digitada na combo do CPL como sintaxe do INI: o painel pode transformá-la ao salvar.

### Mapeamentos visuais confirmados

| Chave/token | Rótulo U |
|---|---|
| OutputAPI `bestavailable` | Best available one |
| OutputAPI `d3d11warp` | Direct3D 11 MS WARP (software) |
| OutputAPI `d3d11_fl10_0` / `d3d11_fl10_1` / `d3d11_fl11_0` | Direct3D 11 (feature level 10.0 / 10.1 / 11.0) |
| OutputAPI `d3d12_fl11_0` / `d3d12_fl12_0` | Direct3D 12 (feature level 11.0 / 12.0) |
| ScalingMode `unspecified` / `centered` / `stretched` | Unspecified / Centered / Stretched |
| ScalingMode `centered_ar` / `stretched_ar` | Centered, keep Aspect Ratio / Stretched, keep Aspect Ratio |
| ScalingMode `stretched_4_3` | Stretched, 4:3 Aspect Ratio |
| ScalingMode `stretched_ar_crt` / `stretched_4_3_crt` | Respectivas opções CRT-like |
| ScalingMode `stretched_4_3_c64` | Stretched, 4:3 Aspect Ratio (VIC-II, C64-like) |
| DirectX VideoCard `svga` / `internal3D` | dgVoodoo Virtual SVGA Card / dgVoodoo Virtual 3D Accelerated Card |
| DirectX Filtering `pointsampled` / `bilinear` | Force point sampled / Force bilinear |
| DirectX Filtering `pointmip` / `linearmip` / `trilinear` | Force point mip / Force linear mip / Force trilinear |
| DirectX Filtering `2` / `4` / `8` / `16` | Force anisotropic 2x / 4x / 8x / 16x |
| DirectX Mipmapping `disabled` / `appdriven` | Disabled / App driven |
| DirectX Mipmapping `autogen_point` / `autogen_bilinear` | Auto-gen with point filter / Auto-gen with bilinear filter |

**Limites importantes:** F permite anisotropia inteira 1..16; U oferece 2/4/8/16. O schema documental não deve reduzir o domínio do arquivo ao dropdown. O contrário também vale: 16x MSAA aparece no comentário Glide, mas a captura complementar DirectX mostra somente Off/App driven/2x/4x/8x; não estender silenciosamente a lista. Disponibilidade no CPL não comprova suporte a todos os formatos em qualquer GPU.

## 6. Dependências mais importantes para o Aika

| Grupo | Relação comprovada ou lacuna | Consequência para produto |
|---|---|---|
| Perfis | Filtering + Antialiasing são resolvidos por Performance/Balanced/Quality (C). AUTO resolve perfil fora do conf. | Mostrar perfil solicitado e perfil efetivo; não criar chave AUTO. |
| Filtro de textura | KeepFilterIfPointSampled limita onde o Filtering forçado atua (F). | Deve ser contextual, e validado em HUD/texto além do cenário 3D. |
| Saída da imagem | Resampling só participa quando dgVoodoo faz scaling (F). | Não apresentar como alternativa a anisotropia de textura. |
| Resolução e RT | RTTexturesForceScaleAndMSAA aplica overrides também a texturas render target (F). | Testar efeitos, sombras, UI e transições ao mexer em resolução/MSAA. |
| Janela | FullScreenMode, AppControlledScreenMode, WindowedAttributes, FullscreenAttributes e Alt-Enter se cruzam (F/U). | Não duplicar o modo janela tela cheia do Aika/Optimizer. Matriz de precedência ainda pendente. |
| Ritmo de apresentação | FPSLimit existe (F); VSync é outro controle (U). | Testar isoladamente e combinados; sem prometer estabilidade ou latência menor. |
| GPU física e emulada | Adapters seleciona/habilita hardware; VideoCard configura modelo emulado (F/U). | Manter conceitos separados; VRAM do detector não prova valor ideal de VRAM no conf. |
| Backend | D3D12BoundsChecking explicitamente só D3D12 (F). | Não mostrar no caminho D3D11 atual. |
| Cores | Default3DRenderFormat auto acompanha ColorSpace (F). | Não expor ambos como ajustes independentes de qualidade. |
| Watermark | Booleano false é regra C; duração só vale quando habilitada (F). | Ocultar ambos; validar codificação e arquivo efetivamente selecionado. |

## 7. Oportunidades para um “Avançado” pequeno

Esta é uma fila de investigação e validação, não autorização para alterar o produto congelado.

| Prioridade | Controle proposto | Chaves | Por que pode valer a pena | Gate antes da exposição |
|---|---|---|---|---|
| 1 | Limite de FPS: desligado / 60 / 120 | GeneralExt.FPSLimit | Benefício compreensível; poucas escolhas. | Confirmar domínio, leitura efetiva e teste de frametime/input com limitador do jogo, driver e VSync. |
| 1 | Preservar texturas com filtro pontual | DirectX.KeepFilterIfPointSampled | Pode evitar que override altere elementos que pedem point sampling. | Comparar texto, ícones, transparências, terreno e efeitos. Benefício no HUD é hipótese. |
| 1 | Prender cursor à janela | General.CaptureMouse | Preferência de uso especialmente em múltiplos monitores. | Testar foco, Alt-Tab, cliques nas bordas e retorno ao jogo. |
| 2 | VSync | DirectX.ForceVerticalSync | Troca compreensível entre apresentação e possível latência. | Confirmar comportamento real em janela tela cheia; false deve ser descrito como “não forçar”. |
| 2 | Aparência: brilho, saturação, contraste | General.Brightness/Color/Contrast | Preferência visual reversível. | Confirmar mínimos/máximos/passos e neutralidade 100; ação de restaurar valores neutros. |
| 2 | Tamanho do cursor | GeneralExt.CursorScaleFactor | Útil se cursor emulado estiver pequeno com escala. | Provar que afeta o cursor do Aika; só então oferecer. |
| 3 | Filtro da imagem escalada | GeneralExt.Resampling | Útil apenas quando há escala pelo wrapper. | Provar caminho ativo; ocultar/desabilitar fora dele. |
| 3 | Manter monitor ligado durante jogo | General.DisableScreenSaver | Conveniência, sem prometer FPS. | Conferir se há necessidade e conflito com recurso já existente no Optimizer. |

KeepWindowAspectRatio também é candidato seguro relativo, mas pode não ter utilidade numa janela que já ocupa toda a tela. Resolução forçada, HDR, swapchain, falsificação de GPU, tesselação, profundidade e hooks devem ficar fora da primeira versão do Avançado.

## 8. Requisitos documentais para o futuro engine/schema — sem implementação

1. **Identidade por seção + chave.** GeneralExt.ColorSpace e DirectXExt.Default3DRenderFormat não são sinônimos. Glide e DirectX repetem nomes com domínios/defaults distintos.
2. **Separar quatro níveis:** valor do template do vendor; default interno comprovado ou desconhecido; regra fixa do Aika; override de perfil/usuário. Não chamar todos de “default”.
3. **Guardar evidência e confiança por campo.** Domínio comprovado em comentário não é o mesmo que aceitação comprovada pelo CPL/DLL. Impacto H não vira fato após ser colocado numa tabela.
4. **Distinguir vazio, ausência e comentário.** Muitas opções estão presentes com valor vazio; LogToFile está comentada. Não transformar todos em false ou zero.
5. **Modelar tipos compostos.** Resolução, atributos, listas e ROI não são números simples. Máscara de saída não é ordinal de adaptador.
6. **Não resolver desconhecidos inventando limites.** Ranges de cor, IDs, gramática racional, limites de memória e fatores ainda têm lacunas.
7. **Preservar desconhecidos em leitura futura.** Decidir uma política explícita para comentários, ordem, campos desconhecidos e duplicatas; não eliminar automaticamente extensões de vendor.
8. **Versionar template e proveniência.** `0x287` não basta para distinguir patches. Registrar versão do pacote e identidade dos componentes sem inferir a partir dessa chave.
9. **Preservar codificação validada.** UTF-8 sem BOM; verificar bytes iniciais. Regras sobre terminadores e tolerância do parser exigem evidência, não preferência de biblioteca INI.
10. **Separar validações:** sintaxe; domínio conhecido; dependências; política Aika; leitura efetiva pelo wrapper; validação visual e de desempenho. Um conf bem formado não prova comportamento em jogo.
11. **Definir interação AUTO/personalização.** O futuro produto deve deixar claro se ajuste manual muda o perfil, sobrepõe parte dele ou é removido ao Reaplicar. Nenhuma dessas decisões foi tomada aqui.
12. **Preferir round-trip conservador futuro.** Uma chave por vez em cópia isolada, comparar resultado CPL e registrar mudanças colaterais. Não executar esse procedimento no conf validado durante esta fase.

## 9. Lacunas priorizadas e próximos materiais

| Lacuna | Material/ensaio que resolveria |
|---|---|
| Rótulos e controles Ext | Capturas GeneralExt, GlideExt, DirectXExt e Debug, com menus relevantes abertos. G informa acesso por botão direito → Show all sections of the configuration. |
| MSAA DirectX | **Resolvido para o dropdown entregue:** Off, App driven, 2x, 4x e 8x. Aceitação de 16x pelo INI/DLL em D9 continua não comprovada. |
| Intervalos de Brightness/Color/Contrast | Capturas/tooltips com limites ou documentação correspondente; eventual ensaio em cópia descartável, em fase posterior. |
| Semântica VRAM, FastVideoMemoryAccess, Phong e escopo DD/CPU em D9 | Manual DirectX que acompanhe o pacote 2.87.4 ou explicação oficial específica. |
| DisableD3DTnLDevice | Fonte oficial esclarecendo inversão do comentário e aplicabilidade D3D9. |
| Primária agrupada | Confirmação oficial de quais APIs usam PrimarySurfaceBatchedUpdate. |
| Domínio/parser | Evidência para case, duplicatas, valores inválidos, zeros/negativos, vazios e ausência; não experimentar em produção. |
| Defaults reais da DLL | Template oficial autenticado mais documentação/ensaio separado de ausência de chaves; não confundir com estado U. |
| Configuração efetivamente carregada | Evidência de caminho e conteúdo no teste; sem watermark não é prova suficiente para todas as demais chaves. |
| Benefício no Aika | Ensaios separados por opção, repetidos em mesma cena, registrando frametimes, input, HUD, efeitos, troca de mapa e Alt-Tab. |

O mapa cobre as 94 chaves ativas e a opção comentada. As lacunas acima são parte do resultado: não há base para afirmar compreensão completa do comportamento interno de todas as propriedades, nem para declarar ganhos de desempenho no Aika sem teste.

## 10. Apoio técnico da D3D9.dll recebida

| Verificação estática | Resultado observado B | O que permite concluir |
|---|---|---|
| Tamanho | 482.304 bytes | Identifica esta amostra, não todo pacote 2.87.4. |
| SHA-256 | `db1c445f7bcf699df1e175e974c779bdc7e19a468680a44884b1ab7078888d04` | Referência reproduzível para comparar este arquivo. Não houve comparação com hash publicado pelo fornecedor. |
| Formato/arquitetura | PE32, Intel 80386, flag DLL/32 bits | Confirma x86/32-bit como informado. |
| FileDescription | `dgVoodoo 2.87.4 - Direct3D9` | Identificação embutida coerente com o vendor informado. |
| ProductName / ProductVersion | `dgVoodoo` / `2.8.7.4` | Versão de produto embutida consistente com 2.87.4. |
| FileVersion | `4.9.0.904` | Campo distinto de ProductVersion; não usar para concluir que o vendor seja “4.9”. Motivo dessa numeração não investigado. |
| OriginalFilename / InternalName | `D3D9.dll` / `D3D9.dll` | Nome interno coerente. |
| Timestamp do cabeçalho | 2/9/2026, 10:17:12 conforme decodificação do PE | Metadado coerente com período do release; não prova autenticidade ou momento real de compilação. |
| Exportações | 11 nomes, incluindo `Direct3DCreate9` e `Direct3DCreate9Ex` | Interface de entrada D3D9 presente; não comprova que o Aika use D3D9Ex. |
| Chaves do conf como strings simples | Busca ASCII por watermark, VRAM, OutputAPI, FPSLimit, FastVideoMemoryAccess e outras não retornou correspondências | Essa inspeção não revela schema/parser. Ausência de string legível não prova ausência de suporte. |

Outras exportações observadas: `D3DPERF_BeginEvent`, `D3DPERF_EndEvent`, `D3DPERF_GetStatus`, `D3DPERF_QueryRepeatFrame`, `D3DPERF_SetMarker`, `D3DPERF_SetOptions`, `D3DPERF_SetRegion`, `DebugSetMute` e `Direct3DShaderValidatorCreate9`.

Os recursos de versão estavam legíveis. A leitura genérica de todos os recursos por objdump também gerou avisos de interpretação; isso não foi tratado como prova de DLL defeituosa. Não houve execução, disassembly semântico do parser ou tentativa de reconstruir o código. A DLL apoia a identificação do componente, mas **não resolve** os defaults internos, o tratamento de BOM, a semântica ambígua de TnL nem o efeito de VRAM/FastVideoMemoryAccess no Aika.

Em particular, a presença de `DebugSetMute` não identifica esta amostra como build debug/spec. A seção Debug continua condicionada ao tipo de distribuição documentado pelo fornecedor; não foi inferida a partir de um nome exportado.
