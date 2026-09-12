# Overlay AIKA Optimizer atual × dgVoodoo2 2.87.4 oficial

Auditoria documental do código recebido — 09/09/2026.

## 1. Resultado e escopo

Os dois módulos recebidos foram lidos integralmente: serviço, 1.257 linhas; página, 1.073 linhas. O overlay tem **14 chaves explicitamente atribuídas**, das quais **12 são fixas e duas variam por perfil**. As outras **80 chaves ativas**, incluindo Version global, são preservadas do template utilizado pelo serviço. Não foi localizada outra atribuição de chave dgVoodoo nesses dois módulos.

Esta versão substitui documentalmente o overlay “Pendente_codigo”: todas as células de valor/origem das 28 chaves daquele inventário estão resolvidas nesta versão. O inventário foi ampliado para as 94 chaves ativas do conf e a opção comentada LogToFile. O documento anterior permanece como registro da etapa preliminar.

**Pendência do detector encerrada:** `hardware_detector.py` foi recebido e lido integralmente no complemento final. A seção H documenta coleta, normalização, recomendação e confiança. Permanecem os demais limites de evidência desta auditoria, inclusive a distinção entre leitura estática e validação funcional de campo.

Não foram executados/importados os módulos, gerados confs, alterados templates, DLLs ou código. A análise usa leitura estática, comparação dos anexos e referências de linha. Não propõe correções nem mudanças de comportamento. O futuro schema não foi implementado ou desenvolvido nesta etapa.

## 2. Fontes e identidade

As referências `S:linha`, `U:linha`, `V:linha` e `A:linha` apontam para os arquivos abaixo, com numeração iniciando em 1. São localizações no material efetivamente recebido; nomes com `(1)`/`(2)` são os nomes dos anexos.

| Ref. | Arquivo | SHA-256 |
|---|---|---|
| S | dgvoodoo_service(1).py | `b3e8885d13916fd63336f2c7ff634f6b32a4d4e58b38af5d5cc6fc38533f3689` |
| U | dgvoodoo_page(1).py | `6f4901085d0afbcd60559288ccb6f42d2f91647b211c82293486ea242e082ecf` |
| V | dgVoodoo(1).conf, vendor recebido na primeira etapa | `3c7da2fac3eaad369df468e80c9ba9c4db632c419799b32bbc31279d10985801` |
| A | dgVoodoo(2).conf, recebido nesta etapa | `ab8f2fcc04fa94d5c5b90d3858d725de83a5946073cc29fc7a0528ae102700dd` |
| D | d3d9(1).dll | `db1c445f7bcf699df1e175e974c779bdc7e19a468680a44884b1ab7078888d04` |

A DLL tem o mesmo hash da amostra já inspecionada na primeira etapa. A identificação x86 e os metadados 2.87.4 daquela inspeção continuam aplicáveis à amostra idêntica.

**O conf A não é byte a byte o vendor V.** Ele contém as dez diferenças de valor correspondentes ao overlay Quality: OutputAPI, Adapters, FullScreenMode, DisableScreenSaver, VRAM, Filtering, KeepFilterIfPointSampled, Antialiasing, watermark e FastVideoMemoryAccess. Nele, AA é `4x`. As outras 84 chaves têm o mesmo valor de V. A não possui BOM UTF-8 inicial e termina sem newline, compatível com a serialização encontrada.

Isso comprova uma configuração de conteúdo equivalente ao perfil Quality, mas não distingue seleção manual de AUTO → Quality. Também não comprova que A seja exatamente o arquivo acessado em `third_party/dgvoodoo2/dgVoodoo.conf` no computador do usuário: o anexo não traz esse vínculo de caminho. A auditoria registra o literal de A e o caminho de template do código separadamente. **As 80 chaves herdadas têm os mesmos valores em A e V**, de modo que essa distinção não deixa seus valores documentais pendentes entre essas duas amostras.

## 3. Validação funcional e congelamento

**C — validação de conjunto relatada:** o usuário informou execução aprovada de Performance, Balanced, Quality, AUTO e Reaplicar após remover o BOM. O comentário S:250–255 também afirma a preservação da configuração de campo. Código e comentários não substituem logs de execução.

**W — resultado específico relatado:** watermark ausente após correção de codificação, nos fluxos informados.

**N — efeito individual não demonstrado:** não houve teste isolado desta auditoria comprovando que cada chave foi consumida pelo wrapper ou que causou ganho de desempenho. Para todas as linhas herdadas, C significa apenas presença na configuração completa, condicionada ao template da execução; não equivale a uso da funcionalidade. Em particular, Glide/Debug podem estar presentes sem participação no caminho D3D9 regular.

Não foi anexado registro ligando cada rodada de campo aos hashes dos fontes e confs desta entrega. Portanto, C/W continuam sendo evidência relatada; a auditoria estática confirma valores e caminhos, não reproduz os resultados.

**Congelamento de todas as linhas: SIM.** Preservar tanto as atribuições explícitas como a herança e o comportamento atual dos fluxos. Semântica incompleta não significa chave incorreta, nem autoriza retorno ao vendor. Este documento não recomenda mudar sequer o comportamento de Reaplicar descrito adiante.

## 4. A) Chaves explicitamente controladas — lista completa

Para todas as linhas: a atribuição atua sobre linhas já existentes pelo mecanismo S:405–431. A escrita física é do arquivo completo, via S:443 na ativação ou S:1160 na aplicação de perfil. “Explícita” significa decisão de valor no código, não escrita isolada de uma linha no disco. O helper não insere chaves/seções ausentes.

| Seção/chave | Vendor V | Valor efetivo AIKA | Local exato da atribuição | Origem e escrita | Campo | Congelar | Lacuna semântica restante |
|---|---|---|---|---|---|---|---|
| General.OutputAPI | `bestavailable` (V:27) | `d3d11_fl11_0` | S:257 | FIXO AIKA; explícita | C/N | Sim | Combinações de hardware não validadas universalmente; finalidade do token conhecida |
| General.Adapters | `all` (V:28) | `1` | S:258 | FIXO AIKA; explícita | C/N | Sim | Ordinal não identifica persistentemente GPU; AUTO não o modifica |
| General.FullScreenMode | `true` (V:30) | `false` | S:259 | FIXO AIKA; explícita | C/N | Sim | Precedência no wrapper com AppControlledScreenMode e atributos ainda não integralmente comprovada |
| General.DisableScreenSaver | `false` (V:43) | `true` | S:260 | FIXO AIKA; explícita | C/N | Sim | Finalidade documentada; efeito individual não ensaiado |
| DirectX.DisableAndPassThru | `false` (V:199) | `false` | S:263 | FIXO AIKA; explícita, mesmo valor do vendor | C/N | Sim | Mecanismo exato por API não aprofundado |
| DirectX.VideoCard | `internal3D` (V:201) | `internal3D` | S:264 | FIXO AIKA; explícita, mesmo valor do vendor | C/N | Sim | Capacidades internas específicas em D3D9 não inteiramente mapeadas |
| DirectX.VRAM | `256` (V:202) | `1024` | S:265 | FIXO AIKA; explícita em todos os perfis | C/N | Sim | Semântica/efeito D3D9 incompletos; não é derivado dos ~6 GB detectados |
| DirectX.Filtering | `appdriven` (V:203) | Ativar/Reaplicar: `16`; Performance: `trilinear`; Balanced/Quality: `16` | S:266; S:310,316,322 | Base AIKA + PERFIL; AUTO seleciona o perfil; explícita | C/N | Sim | Custo/benefício isolado e efeitos por textura no Aika não medidos |
| DirectX.Antialiasing | `appdriven` (V:207) | Ativar/Reaplicar: `2x`; Performance: `appdriven`; Balanced: `2x`; Quality: `4x` | S:267; S:309,315,321 | Base AIKA + PERFIL; AUTO seleciona o perfil; explícita | C/N | Sim | Appdriven não significa off necessariamente; dependências de GPU/formato/RT |
| DirectX.KeepFilterIfPointSampled | `false` (V:205) | `true` | S:268 | FIXO AIKA; explícita | C/N | Sim | Significado documentado; benefício específico no HUD não demonstrado isoladamente |
| DirectX.AppControlledScreenMode | `true` (V:209) | `true` | S:269 | FIXO AIKA; explícita, mesmo valor do vendor | C/N | Sim | Matriz completa de precedência do wrapper com modos de janela |
| DirectX.DisableAltEnterToToggleScreenMode | `true` (V:210) | `true` | S:270 | FIXO AIKA; explícita, mesmo valor do vendor | C/N | Sim | Interações específicas do input/jogo não isoladas |
| DirectX.FastVideoMemoryAccess | `false` (V:216) | `true` | S:271 | FIXO AIKA; explícita | C/N | Sim | Mecanismo, alcance D3D9 e benefício continuam incompletos; true deve ser preservado |
| DirectX.dgVoodooWatermark | `true` (V:215) | `false` | S:272 | FIXO AIKA; explícita obrigatória | C/W | Sim | Causa interna da rejeição do BOM não reconstruída; desligamento conhecido |

PRESET_CONF contém 14 entradas, e PERFIS_CONF reutiliza duas delas. Logo, não há 16 chaves distintas: **12 fixas + 2 de perfil = 14**. Nenhuma das 14 estava ausente das 28 linhas preliminares; a auditoria corrigiu suas origens pendentes e distinguiu as 14 linhas restantes daquele inventário como herança.

## 5. B) Chaves herdadas do template — lista completa

**Regra comum a cada linha desta lista:** origem = TEMPLATE/PRESERVADO; sem atribuição explícita de valor nos dois módulos. Código responsável pela herança: S:892–895 na ativação; S:473–480 na geração por perfil; S:405–431 preserva linhas não mapeadas. Valor AIKA = valor lido do template efetivamente resolvido. A coluna “V = A = herança” registra o valor comum das duas amostras recebidas. Referência `linha` aplica-se tanto a V como a A.

**Campo de cada linha: C/N conforme seção 3; congelamento de cada linha: SIM.** Não há override de usuário preservado do conf instalado na aplicação de perfil; o que se preserva é o conteúdo do template. Na restauração, em contraste, o backup original é copiado em bytes.

Códigos de lacuna nesta tabela: **E** = efeito/aplicabilidade individual no Aika não demonstrado; **D** = domínio/gramática ainda incompleto; **S** = semântica interna ou alcance em D3D9 incompleto; **X** = fora do caminho D3D9/D3D11 regular definido. Esses códigos descrevem lacunas, não erros ou autorização de mudança. Detalhes técnicos permanecem no mapa aprovado.

### Global — 1

| Chave | V = A = herança | Linha | Lacuna |
|---|---|---|---|
| Version | `0x287` | 7 | S: identificador não distingue patch; não validado pelo serviço |

### General — 11

| Chave | V = A = herança | Linha | Lacuna |
|---|---|---|---|
| FullScreenOutput | `default` | 29 | E |
| ScalingMode | `unspecified` | 31 | E: caminho efetivo de scaling |
| ProgressiveScanlineOrder | `false` | 32 | E |
| EnumerateRefreshRates | `false` | 33 | E |
| Brightness | `100` | 35 | D: limites/passos; E |
| Color | `100` | 36 | D: limites/passos; E |
| Contrast | `100` | 37 | D: limites/passos; E |
| InheritColorProfileInFullScreenMode | `true` | 38 | E |
| KeepWindowAspectRatio | `true` | 40 | E |
| CaptureMouse | `true` | 41 | E |
| CenterAppWindow | `false` | 42 | E: momento/recorrência |

### GeneralExt — 16

`vazio` é ausência de conteúdo após `=`, não um token literal nem uma chave ausente.

| Chave | V = A = herança | Linha | Lacuna |
|---|---|---|---|
| DesktopResolution | vazio | 113 | D/E |
| DesktopBitDepth | vazio | 114 | E |
| DeframerSize | `1` | 115 | E |
| ImageScaleFactor | `1` | 116 | D: teto; E |
| CursorScaleFactor | `0` | 117 | E: cursor Aika elegível? |
| DisplayROI | vazio | 118 | D: limites/coordenadas; E |
| Resampling | `bilinear` | 119 | E: depende de scaling pelo wrapper |
| PresentationModel | `auto` | 120 | E: combinações backend/OS |
| ColorSpace | `appdriven` | 121 | E: formatos efetivos |
| WatermarkDisplayDuration | `0` | 122 | D; sem utilidade com marca DirectX desligada |
| FreeMouse | `false` | 123 | S/E: relação detalhada com CaptureMouse |
| WindowedAttributes | vazio | 124 | E: precedências |
| FullscreenAttributes | vazio | 125 | E: precedências |
| FPSLimit | `0` | 126 | D: sintaxe racional/teto; E |
| Environment | vazio | 127 | X no ambiente nativo descrito |
| SystemHookFlags | vazio | 128 | D/S: sintaxe e necessidade concreta |

### Glide — 16

Estas chaves são preservadas textualmente, mas não configuram o caminho de entrada D3D9 informado. Sua presença não comprova execução Glide.

| Chave | V = A = herança | Linha | Lacuna |
|---|---|---|---|
| VideoCard | `voodoo_2` | 151 | X |
| OnboardRAM | `8` | 152 | X/D: domínio por placa |
| MemorySizeOfTMU | `4096` | 153 | X/D |
| NumberOfTMUs | `2` | 154 | X/D |
| TMUFiltering | `appdriven` | 155 | X |
| DisableMipmapping | `false` | 156 | X/S |
| Resolution | `unforced` | 157 | X/D |
| Antialiasing | `appdriven` | 158 | X |
| EnableGlideGammaRamp | `true` | 160 | X/S |
| ForceVerticalSync | `true` | 161 | X |
| ForceEmulatingTruePCIAccess | `false` | 162 | X/S |
| 16BitDepthBuffer | `false` | 163 | X/S |
| 3DfxWatermark | `true` | 164 | X; não é dgVoodooWatermark de DirectX |
| 3DfxSplashScreen | `false` | 165 | X/S |
| PointcastPalette | `false` | 166 | X/S |
| EnableInactiveAppState | `false` | 167 | X/S |

### GlideExt — 3

| Chave | V = A = herança | Linha | Lacuna |
|---|---|---|---|
| DitheringEffect | `pure32bit` | 180 | X/S |
| Dithering | `forcealways` | 181 | X/S |
| DitherOrderedMatrixSizeScale | `0` | 182 | X/D |

### DirectX — 6

Estas seis são importantes para corrigir a diferença entre “mantido na baseline” e “explicitamente fixado no código”.

| Chave | V = A = herança | Linha | Lacuna |
|---|---|---|---|
| Mipmapping | `appdriven` | 204 | S/E: autogeração e alcance |
| Resolution | `unforced` | 206 | D/E: gramática e interação com HUD/RT |
| Bilinear2DOperations | `false` | 212 | S: alcance DD/CPU em D3D9 |
| PhongShadingWhenPossible | `false` | 213 | S: condições e alcance |
| ForceVerticalSync | `false` | 214 | E: não forçar não equivale a desligamento global |
| DisableD3DTnLDevice | `false` | 217 | S: comentário aparentemente invertido e alcance D3D9 |

### DirectXExt — 23

| Chave | V = A = herança | Linha | Lacuna |
|---|---|---|---|
| AdapterIDType | vazio | 308 | E |
| VendorID | vazio | 309 | D: base/range; E |
| DeviceID | vazio | 310 | D/E |
| SubsystemID | vazio | 311 | D/E |
| RevisionID | vazio | 312 | D/E |
| DefaultEnumeratedResolutions | `all` | 314 | D: lista classics; E |
| ExtraEnumeratedResolutions | vazio | 315 | D/E |
| EnumeratedResolutionBitdepths | `all` | 316 | D: separador; E |
| DitheringEffect | `high_quality` | 318 | S: algoritmo; E |
| Dithering | `forcealways` | 319 | S/E |
| DitherOrderedMatrixSizeScale | `0` | 320 | D: teto; E |
| DepthBuffersBitDepth | `appdriven` | 321 | E |
| Default3DRenderFormat | `auto` | 322 | E |
| MaxVSConstRegisters | `256` | 324 | E |
| D3D12BoundsChecking | `false` | 325 | X com backend D3D11 |
| NPatchTesselationLevel | `0` | 327 | E |
| DisplayOutputEnableMask | `0xffffffff` | 329 | E: topologia |
| MSD3DDeviceNames | `false` | 331 | S: alcance preciso D3D9 |
| RTTexturesForceScaleAndMSAA | `true` | 332 | E: efeitos específicos |
| SmoothedDepthSampling | `true` | 333 | S: algoritmo/custo; E |
| DeferredScreenModeSwitch | `false` | 334 | E |
| PrimarySurfaceBatchedUpdate | `false` | 335 | S: caminho D3D9 elegível? |
| SuppressAMDBlacklist | `false` | 336 | S: lista de GPUs/drivers; E |

### Debug — 4

| Chave | V = A = herança | Linha | Lacuna |
|---|---|---|---|
| Info | `enable` | 358 | X em build regular; F do mapa limita a debug/spec |
| Warning | `enable` | 359 | X, mesma condição |
| Error | `enable` | 360 | X, mesma condição |
| MaxTraceLevel | `0` | 361 | X, mesma condição |

Adicional **não ativo**: `;LogToFile = false`, V/A:363. Permanece comentário, não recebe atribuição no código. O comentário vendor o declara não implementado. Não entra na contagem 94 e não produz promessa de dgVoodoo.log.

## 6. C) Valores controlados por perfil

| Operação/perfil | Filtering | Antialiasing | Origem comprovada |
|---|---|---|---|
| Ativar | `16` | `2x` | PRESET_CONF S:266–267; chamado S:895 |
| Reaplicar | `16` | `2x` | Mesmo caminho de Ativar: U:415,676–682,628–630 |
| Aplicar Performance | `trilinear` | `appdriven` | S:307–311 |
| Aplicar Balanced | `16` | `2x` | S:313–317 |
| Aplicar Quality | `16` | `4x` | S:319–323 |
| Aplicar AUTO | Par do perfil recebido em resolved_profile | Par do perfil recebido em resolved_profile | U:645–663; S:1100–1114,1159 |

A geração de perfil lê o template, aplica PRESET_CONF e depois PERFIS_CONF (S:473–480). Balanced possui overrides explícitos; não é um dicionário vazio. Filtering e Antialiasing recebem o valor da base e em seguida o valor do perfil, mesmo quando são iguais.

Reaplicar **não** usa o perfil selecionado, o último perfil aplicado ou a recomendação de hardware. Reconstrói a base e persiste `preset="Aika Recomendado"`, equivalente a Balanced pela normalização S:327–337. O novo estado de ativação não inclui resolved_profile (S:799–818). Essa é uma constatação documental, não sugestão para mudar o fluxo.

## 7. D) Decisões do AUTO e normalizações

### Integração auditada

| Etapa | Comportamento efetivo | Local |
|---|---|---|
| Entrada na página | Agenda refresh; primeira exibição elegível dispara detecção, uma vez por instância | U:1057–1070 |
| Coleta/recomendação | Chama `hd.detectar_hardware()`; exceção vira None e sinaliza resultado | U:636–643; import U:34 |
| Cache | Resultado mantido em memória na página; escolher AUTO reaproveita cache, se houver | U:197–201,694–706,726–729 |
| Reanalisar | Limpa cache e dispara nova detecção; não aplica perfil/conf | U:718–723 |
| Resolver para aplicar | Usa recommended_profile válido do cache; senão resolved_profile válido no estado persistido; senão None | U:779–791 |
| Sem resolução válida | Botão AUTO não habilita aplicação; chamada direta da ação emite aviso e retorna | U:998–1003,648–654 |
| Aplicar | Encaminha `perfil="auto"` e resolved_profile ao serviço | U:657–660 |
| Validação no serviço | Rejeita AUTO sem resolved válido, inclusive resolved="auto"; não detecta GPU internamente | S:1100–1111 |
| Persistência | Salva preset=auto, resolved_profile real e hash do conf | S:1182–1191 |
| Voltar a manual | Aplica perfil informado e remove resolved_profile antigo | S:1112–1114,1187–1189 |
| UI de perfil aplicado | Lê escolha/efetivo do estado; não deduz perfil analisando AA/Filtering do conf | U:908–917; S:354–382 |

O fallback para resolved_profile persistido em U:786–790 não exige que o preset persistido seja auto. Já S:_perfil_efetivo_estado só usa resolved_profile quando preset é auto. São regras distintas em dois contextos.

### Fallbacks de exibição não são todos fallbacks de aplicação

- S:327–337: perfil legado, desconhecido ou ausente normaliza para Balanced; não há strip/lower dos perfis nessa função.
- S:340–351: resolved_profile fora dos três perfis é descartado.
- S:354–366: preserva escolha auto para exibição; estado ausente vira Balanced.
- S:369–382: estado auto com resolved ausente/inválido é exibido como efetivo Balanced.
- S:470–471: gerador rejeita perfil desconhecido; não normaliza para Balanced.
- S:1092–1109: chamada pública rejeita perfil inválido ou AUTO sem resolução válida; não aplica fallback silencioso.
- U:843–845: recomendação inválida é mostrada como Balanced, mas o objeto de hardware não é corrigido ali. U:779–791 ainda pode recorrer ao estado ou retornar None.
- U:859–864: confiança baixa mostra texto “Equilibrado (por segurança)”; não muda recommended_profile nem aplica esse perfil. A seleção para aplicar consulta recommended_profile, não confidence. A correspondência entre confiança baixa e recomendação Balanced no detector recebido está documentada na seção H.
- U:875–882: falha de detecção exibe Equilibrado/Baixa; isso não cria uma recomendação válida por si. Se não há resolved persistido, AUTO segue sem valor aplicável.

### GPU e VRAM mostradas

U:794–801 escolhe, para exibição, a GPU dedicada de maior vram_mb quando houver; senão a GPU de maior vram_mb entre todas. O docstring diz “senão a 1ª”, mas o código usa `max` também nesse caso. Nenhuma GPU identificável resulta em None. VRAM é convertida com int, valores inválidos/não positivos mostram “não informada”; os demais são divididos por 1024, com uma casa decimal (U:804–812).

Essas rotinas não escrevem Adapters nem DirectX.VRAM. Nos módulos auditados, esses valores continuam `1` e `1024`, respectivamente, independentemente da recomendação.

**Complemento concluído na seção H:** APIs de coleta, heurística dedicada/integrada, limiares, cálculo de confiança, falhas e fallbacks do detector foram auditados no código recebido. O relato RTX 4050 → Quality/Alta continua sendo validação contextual; as condições implementadas que podem produzir esse resultado agora estão documentadas.

## 8. Todos os pontos de leitura, escrita e preservação do conf

| Ponto | Operação e consequência | Referência |
|---|---|---|
| Resolver template | Em frozen, tenta pasta do executável, depois _MEIPASS; fallback pasta do módulo. Arquivo relativo third_party/dgvoodoo2/dgVoodoo.conf | S:51–81 |
| Validar templates | Verifica somente existência e tamanho >0 de DLL e conf; não valida versão, semântica ou hash oficial do conf | S:84–92 |
| Leitura de chave | Abre conf com utf-8-sig, lê linhas, retorna primeira correspondência exata de seção/chave e valor com strip | S:385–402 |
| Leitura para preset | Abre cópia do cliente com utf-8-sig, passa texto ao substituidor | S:434–458 |
| Leitura para perfil | Abre template com utf-8-sig; não usa conf atual como base | S:461–480 |
| Hash binário | Lê bytes de arquivo; usado para identificar conf atual, backups e conf final | S:113–118; chamadas S:697,702,712,857,923–925,987–997,1148,1182 |
| Cópia binária | Lê origem em rb, escreve atomicamente, verifica hash destino/origem; usada para template e restauração | S:640–657 |
| Backup | Delega cópia do original a seguranca.fazer_backup_rapido; valida existência/hash e reutiliza backup idêntico | S:680–718; chamada S:851–874 |
| Instalação | Copia conf template para cliente, depois reescreve preset; são duas escritas distintas | S:892–895 |
| Falha de instalação | Tenta remover conf já presente e registra failed | S:900–918 |
| Aplicar perfil | Gera bytes do template + base + perfil e substitui conf; lê AA/Filtering para validar | S:1158–1180 |
| Restaurar | Preflight de conf e DLL por hash; depois remove ou copia backup bruto conforme plano | S:978–1038 |
| Diagnóstico | Verifica existência de conf, não lê seu conteúdo nem confere seu hash no detectar_estado | S:550–596; diagnosticar S:1216–1218 |

_remover_arquivo_seguro (S:660–677) é helper genérico definido, mas não chamado pelos fluxos destes módulos. Não é um ponto adicional de remoção efetivamente usado aqui.

A página não abre/escreve conf diretamente; chama as APIs do serviço. Seus acessos a recursos visuais não são acessos ao dgVoodoo.conf. `estado.json` usa leitura/gravação própria S:159–176, distinta do conf; seus campos preset/backend/resolved_profile não são chaves do vendor.

## 9. Serialização, UTF-8 sem BOM e normalização

1. **Leitura permissiva quanto a BOM inicial:** utf-8-sig em S:388,437,473 aceita UTF-8 com ou sem BOM inicial. Não há fallback implementado para ANSI/UTF-16.
2. **Saída ativa gerada sem BOM:** encode("utf-8") em S:443 e S:480. Nenhuma dessas chamadas usa utf-8-sig para escrever.
3. **Quebras de linha:** S:411 usa splitlines e S:431 faz join com CRLF. Portanto não preserva literalmente todo o arquivo em bytes e não garante newline final. Não há uma rotina específica de preservar a terminação original.
4. **Substituição por seção/chave exatas:** strip reconhece delimitadores e nome; não normaliza case. Só altera entradas cujo mapeamento retorna valor não None. Não insere chaves nem seções que faltam.
5. **Formatação:** preserva prefixo até o whitespace após `=` da linha alterada; o resto é substituído pelo valor. Comentários em linhas separadas permanecem. Comentário inline após um valor sobrescrito não é preservado. Linhas não mapeadas mantêm conteúdo, mas suas quebras passam pelo join.
6. **Duplicatas:** o substituidor percorre e pode alterar todas as correspondências; o leitor de validação retorna a primeira. Não há deduplicação nem diagnóstico específico.
7. **Comentários:** nomes comentados como `;LogToFile` não correspondem a uma chave ativa; são preservados. Não há parser geral de comentários inline no leitor de chave; o texto após `=` é retornado integralmente com strip.
8. **Retorno “alteradas”:** S:444–449 lista todos os valores não None do mapeamento, não verifica se cada chave foi realmente encontrada/substituída. O retorno não é prova individual de alteração.
9. **Escrita atômica individual:** S:121–156 usa temporário no diretório de destino, wb, flush, fsync, chmod best-effort e os.replace; limpa temporário restante. Isso não torna todo o ciclo DLL/conf/estado uma única operação atômica.
10. **Restauração preserva bytes originais:** não transcodifica backup. A regra “UTF-8 sem BOM” rege o conf ativo produzido pelo preset/perfil, não a identidade de um original restaurado. A cópia inicial do template também é binária, antes da aplicação do preset.
11. **Erros de leitura:** helpers de leitura de conf capturam OSError, não UnicodeError localmente. Fluxos externos podem capturar exceções; não existe troca automática de encoding.

Não foi gerada configuração para ensaiar essas regras; são consequências diretas das instruções do código. O conf A sem BOM é evidência adicional consistente, não teste novo do gerador.

## 10. Proteções, estados e limites comprovados

Estes pontos delimitam a implementação; não são uma lista de mudanças sugeridas.

- **Cliente efetivo:** detectar/ativar/restaurar/aplicar usam config.obter_pasta_jogo_atual, embora aceitem pasta_jogo como parâmetro (S:520,756,947,1081). Nesses corpos o parâmetro não determina o cliente. O client_provider da página é armazenado, mas as chamadas aqui usam o serviço sem fornecer caminho.
- **Processo aberto:** S:487–509 tenta detector de Pedras; fallback config.jogo_esta_aberto; se ambas as vias falham, retorna False. O comentário chama o fallback de conservador, mas a exceção final não bloqueia por si.
- **Diagnóstico ATIVO:** depende da DLL reconhecida e conf existente; não comprova conteúdo íntegro do conf (S:585–596). U:898–915 mostra DX11 e perfil a partir desse estado e metadados, não de leitura da OutputAPI real.
- **Aplicar perfil:** exige status active, template disponível, conf existente e checagem de processo. Se installed_sha256 do conf estiver presente, divergência aborta; se ausente, a comparação não é feita (S:1144–1156). Não valida ali o hash da DLL instalada. A descrição em docstring é mais ampla que essas condições literais.
- **Validação pós-perfil:** compara somente as duas entradas de PERFIS_CONF/DirectX (S:1168–1180). Não valida independentemente os 12 fixos, Version ou BOM após a escrita. A ausência de BOM resulta da serialização, não de um teste explícito posterior.
- **Estado pós-perfil:** atualiza hash/preset/resolved/profile_applied_at; não recaptura backup nem reinstala DLL (S:1182–1191). Falha marca failed; não há rollback automático do conf anterior nesse caminho.
- **Ativar/Reaplicar:** faz novo estado pending, trata backups, copia DLL/template, aplica base e marca active (S:797–926). O conf externo divergente pode ser capturado como original do novo ciclo em S:851–874; não generalizar a proteção de aplicar_perfil para esse fluxo. A DLL desconhecida/conflitante é bloqueada previamente.
- **Restaurar:** exige status active; realiza preflight sobre ambos os componentes antes das mutações. Arquivo ausente é ação nada, mesmo havendo registro de original; arquivo igual ao original também é nada; conteúdo externo divergente aborta. Copia backup validado quando elegível ou remove o instalado sem original (S:978–1038).
- **Backup delegado:** a implementação interna de config, seguranca e stone_color_service não foi anexada. Foram auditadas chamadas, condições e verificações locais, não seu código interno.
- **Versão em estado:** `_versao_metadados_template` devolve basename da DLL, com fallback d3d9.dll (S:729–739). Não extrai ProductVersion, apesar do nome do helper. format_version=1 refere-se ao JSON do serviço, não ao vendor (S:800).

## 11. Divergências com o histórico e resolução das células anteriores

| Registro preliminar/histórico | Evidência atual que prevalece | Resultado documental |
|---|---|---|
| Adapters=1 descrito como herança de template | PRESET_CONF S:258 | Agora explicitamente fixo |
| FullScreenMode de origem pendente | PRESET_CONF S:259 | false explicitamente fixo |
| DisableScreenSaver sem valor comprovado | PRESET_CONF S:260; A:43 | true explicitamente fixo |
| FastVideoMemoryAccess “valores atuais”, sem literal | PRESET_CONF S:271; A:216 | true explicitamente fixo; semântica incompleta não altera decisão |
| VRAM e KeepFilterIfPointSampled históricos | S:265,268; A:202,205 | 1024 e true explicitamente fixos |
| Balanced descrito como zero overrides | PERFIS_CONF S:313–317 | Dois overrides explícitos, equivalentes à base |
| VSync/FPSLimit/Mipmapping/Resolution chamados “fixos” na especificação | Ausentes de PRESET_CONF e PERFIS_CONF; V/A:214,126,204,206 | Herança preservada, sem atribuição explícita; continuam congelados |
| Opções DirectXExt descritas como mantidas fixas | Nenhuma seção DirectXExt nos mapas S:245–325 | Todas herdadas, inclusive RTTexturesForceScaleAndMSAA e SmoothedDepthSampling |
| Hardware detector/AUTO futuros no histórico | U:34,636–663; S:1100–1111; complemento HD na seção H | Integração AUTO implementada; detector agora auditado |
| Hipótese histórica para watermark | S:443,480 e relato atual de correção BOM | Regra UTF-8 sem BOM presente; hipótese histórica não usada como explicação atual |
| Conf anexado novo poderia ser confundido com vendor | Diff V/A e A:207=4x | A documentado como amostra equivalente a Quality, distinto do vendor |

Não há novas chaves explicitamente controladas além das 14 já contidas no inventário preliminar. A ampliação documental acrescenta as **66 chaves ativas antes não listadas no overlay de 28**, todas herdadas. Junto às 14 herdadas já citadas, totalizam 80.

## 12. E) Invariantes obrigatórias

Separar regras de projeto de mecanismos efetivos de imposição:

| Invariante | Evidência/forma atual de manutenção |
|---|---|
| OutputAPI=d3d11_fl11_0 | PRESET_CONF S:257; comentário obrigatório S:247; aplicado por substituição de linha existente |
| dgVoodooWatermark=false | PRESET_CONF S:272; comentário S:248; relato funcional W |
| Conf ativo gerado em UTF-8 sem BOM | S:443,480; restauração mantém bytes do original |
| Overlay validado preservado | As 12 fixas e os pares de perfil S:245–325; semântica incompleta não autoriza mudança |
| AUTO resolve um dos três perfis | Validação S:1100–1111; não existe token AUTO emitido no INI |
| Templates não são alvo dos fluxos públicos de escrita | Caminhos resolvidos usados como origem em S:473,888,893; destinos são cliente/backup/estado |
| Personalização por chave não existe na página recebida | UI oferece seleção de perfil e ações U:399–475,645–669 |
| Preservar identidade do original em restauração elegível | Backup/hash/cópia binária; limites descritos na seção 10 |

O serviço implementa esses valores por mapas e caminhos, não por um schema central com enforcement completo. Por exemplo, uma chave obrigatória ausente do template não é inserida pelo helper. Isso não foi convertido em proposta de alteração nesta auditoria.

## 13. F) Chaves ainda com semântica incompleta

**Controle atual comprovado, significado/efeito ainda incompletos:** DirectX.VRAM=1024 e DirectX.FastVideoMemoryAccess=true. Ambas permanecem congeladas.

**Herdadas com lacunas centrais já identificadas:** DirectX.Bilinear2DOperations, DirectX.PhongShadingWhenPossible, DirectX.DisableD3DTnLDevice, DirectXExt.PrimarySurfaceBatchedUpdate. Os valores atuais estão na seção 5; nenhuma passa a ser incorreta por isso.

**Demais lacunas de alcance, algoritmo ou domínio:** Version; FreeMouse/SystemHookFlags; IDs e formatos compostos; dithering; MSD3DDeviceNames; SmoothedDepthSampling; lista AMD afetada; domínios de cor/escala/duração; opções Glide marcadas S/D. A seção 5 atribui lacuna individual a cada entrada. Para todas as chaves, a cobertura funcional de conjunto não comprova ganho isolado.

## 14. G) Candidatos futuros para Avançado — registro separado

Lista mantida apenas para atender à classificação solicitada, sem proposta de valor, implementação ou mudança nesta etapa.

| Candidato já mencionado no mapa | Origem atual auditada | Situação nesta etapa |
|---|---|---|
| GeneralExt.FPSLimit | Herdado 0 | Congelado; candidatura documental |
| DirectX.KeepFilterIfPointSampled | Fixo true | Congelado; já faz parte do overlay, não é recurso ausente |
| General.CaptureMouse | Herdado true | Congelado; candidatura documental |
| DirectX.ForceVerticalSync | Herdado false | Congelado; candidatura documental |
| General.Brightness/Color/Contrast | Herdados 100 | Congelados; candidatura documental |
| GeneralExt.CursorScaleFactor | Herdado 0 | Congelado; aplicabilidade do cursor pendente |
| GeneralExt.Resampling | Herdado bilinear | Congelado; depende do caminho de escala |
| General.DisableScreenSaver | Fixo true | Congelado; já ativo no overlay |
| General.KeepWindowAspectRatio | Herdado true | Congelado; candidatura documental |

Filtering e Antialiasing permanecem controles de perfil existentes. Nenhum controle avançado foi acrescentado. A pendência específica de **hardware_detector.py** foi encerrada pela auditoria da seção H, com fonte no código atual, sem usar o histórico para preencher heurísticas.

## H) AUTO — hardware_detector auditado

### H.1. Identidade, escopo e ausência de alterações

**HD** = `hardware_detector.py`, 552 linhas, SHA-256 `3c91f4261531650294302fe5d707bc0df951faffacce7d12a84e7ddab672caa6`. Referências HD:linha apontam para o anexo, numerado a partir de 1. Foram lidos o arquivo completo, seus scripts de consulta e todas as funções. Não foi importado/executado nem modificado.

Esta seção encerra exclusivamente a pendência do detector. Mantém os valores, as conclusões do serviço/página, as lacunas semânticas do dgVoodoo e a classificação de evidência de campo das seções anteriores. Não altera heurísticas nem propõe mudanças.

### H.2. Fontes e APIs realmente usadas

| Fonte | Consulta/campos | Uso e localização |
|---|---|---|
| PowerShell/CIM | `Get-CimInstance Win32_VideoController` | Base da lista de GPUs; HD:186–196 |
| Dados CIM | Name, PNPDeviceID, AdapterRAM, DriverVersion, Status, VideoModeDescription | JSON compacto via ConvertTo-Json -Compress -Depth 3. DriverVersion é coletado, mas não armazenado em GpuInfo nem usado na decisão; HD:236–256 |
| Executor do projeto | `sistema._executar_powershell_oculto`, timeout=30 | HD:24,266. O corpo desse helper externo não está neste arquivo; a chamada e o script foram auditados |
| Registry Windows | winreg.OpenKey, EnumKey, QueryValueEx, CloseKey | Leitura complementar da memória; HD:303–355 |
| Chave Registry | `HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}` | Enumera subchaves acessíveis sem filtro pelo nome numérico 0000 etc.; HD:297–300,318–329 |
| Valores Registry | DriverDesc e HardwareInformation.qwMemorySize | Descrição para associação; tamanho em bytes convertido com int; HD:330–344 |

Não há chamadas diretas a DXGI, NVML, NVAPI, nvidia-smi, DirectX ou bibliotecas de fabricante neste módulo. O Registry **enriquece** GPUs já obtidas por CIM; se a lista CIM estiver vazia, o fluxo retorna antes de consultar o Registry (HD:411–419). Não há descoberta independente de GPUs pelo Registry como fallback de inventário.

Embora os comentários usem “WMI”, a consulta concreta usa **CIM pelo PowerShell**. O cabeçalho que diz “sem tocar Registro/driver” deve ser lido à luz do código: há leitura do Registry, sem gravação. Não se auditou o corpo do helper externo de sistema nem os efeitos do import desse módulo; a ausência de escritas descrita aqui refere-se às instruções e chamadas de consulta presentes em HD.

### H.3. Fabricante, integrada e dedicada

**Fabricante:** HD:94–114 procura `VEN_` seguido de quatro dígitos hexadecimais no PNPDeviceID. Mapeia 10de → nvidia, 1002 → amd, 8086 → intel (HD:87–91). O prefixo VEN_ é procurado com essa caixa; os dígitos capturados são convertidos para minúsculas. Um VEN reconhecido pelo padrão mas não pelo mapa retorna unknown imediatamente.

Sem correspondência VEN_, procura nvidia, amd/ati ou intel **no próprio argumento PNPDeviceID**, convertido para minúsculas. Apesar do docstring mencionar fallback pelo nome, a chamada em HD:249 passa apenas pnp; não passa Name. O campo vendor não participa das decisões de perfil/confiança em HD:430–507.

**Tipo:** depende exclusivamente dos padrões sobre o nome, case-insensitive (HD:149–179), não do fabricante normalizado, de uma API de memória dedicada, do Registry ou da VRAM:

| Grupo | Padrões implementados |
|---|---|
| Integrada | Intel(R) seguido de HD/UHD/Iris; Intel HD/UHD Graphics; Radeon(TM) Graphics; AMD Radeon Graphics; palavra integrated ou sequência Intel Graphics, conforme regex HD:149–156 |
| Dedicada | Palavras nvidia, geforce, gtx, rtx, quadro; Radeon RX/Pro/Vega; Intel Arc; e o trecho literal `\brates?`, conforme HD:158–163 |

O trecho `\brates?` corresponde a fronteira de palavra + `rate` + `s` opcional, sem fronteira final. Está registrado literalmente como parte da heurística, sem correção ou interpretação como intenção de outro padrão. O marcador nvidia também é suficiente para classificar dedicada se não houver marcador integrado simultâneo.

- Só padrão integrado: integrated=True, dedicated=False.
- Só padrão dedicado: integrated=False, dedicated=True.
- Ambos ou nenhum, ou nome vazio: ambos None.

São classificações heurísticas por texto, não certificações físicas da GPU. A lista de famílias e a cobertura de nomes são exatamente as regex; não há tabela de idade, arquitetura, potência ou desempenho de GPUs.

### H.4. VRAM — obtenção, unidades e normalização

1. AdapterRAM CIM é passado a `_normalizar_vram_mb` (HD:121–142,246). A função também é usada para qwMemorySize do Registry (HD:342).
2. None, strings vazias/não numéricas, conversões com TypeError/ValueError e valores <=0 resultam em None. Strings são stripadas e verificadas com `lstrip("-").isdigit()` antes do int. Strings decimais como “6144.0” ou com unidade não são aceitas. Outros tipos aceitos por int são convertidos; não há validador estrito de tipo inteiro.
3. Divide bytes por 1.048.576. Apesar do identificador `_mb` e dos textos “MB/GB”, as unidades de cálculo são **MiB/GiB**.
4. Faixa plausível inclusiva: **256 a 65.536 MiB**, verificada antes do retorno int. Fora da faixa vira None. Dentro da faixa, a parte fracionária é descartada.
5. Valor válido CIM recebe vram_source="wmi"; inválido fica None (HD:246–251).
6. Registro associado com VRAM válida substitui a VRAM CIM e passa vram_source="system" (HD:395–408), mesmo quando a VRAM CIM já era plausível. Não há comparação de concordância ou escolha do maior valor entre as fontes.

O código lê o valor de qwMemorySize com QueryValueEx(...)[0] e int. Não verifica o tipo retornado pelo Registry como REG_QWORD, nem reconstrói valores binários. O termo “64-bit real” está nos comentários; o que o código comprova é a preferência por esse valor do driver quando disponível, plausível e associado. Não é prova independente de capacidade física em qualquer máquina.

### H.5. Associação Registry ↔ CIM e ambiguidades

HD:366–373 normaliza ambos os nomes: minúsculas; remove trechos entre parênteses; remove palavras laptop/gpu/graphics; remove tudo que não seja a–z ou 0–9.

HD:376–408 agrupa entradas do Registry pelo nome normalizado e, para cada GPU CIM:

| Condição | Resultado |
|---|---|
| Exatamente uma candidata de nome igual com VRAM válida | Substitui valor CIM; fonte system |
| Exatamente uma candidata de nome igual, VRAM inválida | Mantém CIM; não tenta outro fallback |
| Mais de uma candidata de mesmo nome | Mantém CIM por ambiguidade, mesmo que só uma tenha VRAM válida |
| Nenhuma candidata de nome igual, exatamente uma GPU CIM e uma entrada Registry | Aceita VRAM válida da única entrada, mesmo com nomes diferentes |
| Nenhuma candidata e contagens diferentes | Mantém CIM |

Não usa PNPDeviceID, LUID, PCI bus/device ou ordinal para correlacionar as fontes. A unicidade testada é das candidatas **do Registry**: se duas GPUs CIM tiverem o mesmo nome e houver uma única entrada Registry correspondente, ambas podem receber esse mesmo valor. Não há consumo de candidata nem verificação de associação um-para-um. O fallback por contagem é uma decisão implementada, não uma confirmação independente de identidade.

### H.6. AdapterRAM truncado e ajuste nominal

HD:208–217 identifica suspeita de teto quando **4090 <= VRAM <= 4100 MiB**. Não descarta o valor nem tenta inferir a capacidade real da GPU a partir do nome. A recuperação usa a fonte Registry, quando associada como descrito acima.

Na recomendação da dedicada selecionada, primeiro verifica plausibilidade e depois aplica `_vram_nominal_mb` (HD:450–456): calcula `round(vram/256)*256` e adota o múltiplo quando ele é >=256 e a diferença absoluta é <=8 MiB (HD:220–233). O ajuste pode subir **ou descer**. Não altera o campo vram_mb guardado em GpuInfo; altera apenas a variável usada na decisão e no texto reason.

O comentário “VRAM dedicada é sempre múltipla de 256 MiB” é a premissa da heurística, não uma afirmação universal comprovada nesta auditoria. A regra concreta é aproximação a um múltiplo próximo.

A suspeita de teto é avaliada **depois** desse ajuste nominal e somente quando vram_source="wmi" (HD:459,477). Portanto, um valor que entre na faixa após aproximação também é tratado como suspeito. O resultado com valor perto de 4 GiB permanece Balanced e recebe confiança MEDIA e aviso de possível truncamento no reason. Fonte system perto de 4 GiB não recebe essa redução específica.

Não há detector geral de todo truncamento/wrap de AdapterRAM: um valor WMI plausível longe dessa faixa pode ser aceito sem alerta. Isso documenta o alcance atual da regra, sem sugerir alteração.

### H.7. Limiares e critérios exatos dos perfis

As regras abaixo são aplicadas em ordem, após o filtro de status e a seleção de GPU descritos em H.9 (HD:430–507).

| Condição | Perfil |
|---|---|
| Lista vazia | Balanced |
| Há dedicada utilizável; VRAM selecionada desconhecida/implausível | Balanced |
| Há dedicada utilizável; VRAM nominal válida <=2.048 MiB | Performance |
| Há dedicada utilizável; VRAM nominal válida >2.048 e <6.144 MiB | Balanced |
| Há dedicada utilizável; VRAM nominal válida >=6.144 MiB | Quality |
| Não há dedicada utilizável; há pelo menos uma integrada utilizável | Performance, independentemente da VRAM |
| Nenhuma das condições anteriores | Balanced |

Não é “4 GB ou mais → Quality”. O limiar presente é **6 GiB nominal** (HD:49–50,461–489). Não exige GPU recente, fabricante específico, versão de driver, resolução do monitor, feature level ou benchmark.

| Limite/fator | Valor exato | Local |
|---|---|---|
| Bytes por MiB | 1.048.576 | HD:139 |
| Plausibilidade mínima | 256 MiB, inclusive | HD:45,140 |
| Plausibilidade máxima | 65.536 MiB, inclusive | HD:46,140 |
| Teto Performance dedicada | 2.048 MiB, inclusive | HD:49,468 |
| Piso Quality dedicada | 6.144 MiB, inclusive | HD:50,461 |
| Suspeita de teto WMI | 4090–4100 MiB, inclusive, sobre valor de decisão | HD:217,459,477 |
| Passo nominal | 256 MiB | HD:230 |
| Tolerância nominal | até 8 MiB, inclusive | HD:231 |

Exemplos deduzidos do código, **não testes executados**: 6141 MiB vira 6144 na decisão → Quality; 2056 vira 2048 → Performance; 2057 permanece 2057 → Balanced; 6135 permanece Balanced, enquanto 6136 vira 6144 → Quality. Esses exemplos pressupõem GPU dedicada escolhida e valor plausível.

### H.8. Confiança ALTA / MEDIA / BAIXA

| Situação | Confiança | Referência |
|---|---|---|
| Sem GPUs | BAIXA | HD:436–441 |
| Dedicada escolhida com VRAM válida e exatamente uma GPU na lista original | ALTA, salvo suspeita WMI de teto | HD:444,457–460 |
| Dedicada escolhida com VRAM válida e mais de uma GPU na lista original | MEDIA | HD:444,457 |
| Dedicada escolhida com VRAM WMI suspeita de teto | MEDIA, mesmo com apenas uma GPU | HD:459–460 |
| Dedicada escolhida com VRAM indisponível/implausível | MEDIA; perfil Balanced | HD:485–490 |
| Sem dedicada utilizável; há integrada e todas as utilizáveis são integradas | ALTA; perfil Performance | HD:492–500 |
| Sem dedicada utilizável; há integrada e também utilizável de tipo desconhecido | MEDIA; perfil Performance | HD:492–500 |
| Nenhuma utilizável reconhecida como dedicada/integrada | BAIXA; perfil Balanced | HD:503–507 |

ALTA não é garantia de desempenho ou validação do dgVoodoo. Não exige explicitamente fonte system: uma WMI válida longe do teto pode resultar ALTA. Status desconhecido também não reduz por si a confiança. Na função pública recomendar_perfil, objetos fornecidos externamente com vram_source=None também não sofrem a regra específica do teto WMI.

O sinal “híbrido” é apenas `len(gpus)>1`, calculado sobre a lista **original**, incluindo GPUs descartadas por status. Não exige um par integrada+dedicada e não é usado para reduzir confiança no ramo de integradas.

Todos os retornos BAIXA deste detector produzem Balanced, encerrando a pendência sobre a coerência com a mensagem de confiança baixa na UI. O que já foi auditado na página continua verdadeiro: ela não converte o perfil com base na confiança; recebe um par perfil/confiança coerente desses retornos.

### H.9. Múltiplos adaptadores e GPU escolhida

1. Status CIM é True apenas para string OK após strip/upper; None permanece desconhecido; outros valores viram False (HD:199–205).
2. `_gpus_utilizaveis` exclui somente status_ok **is False**. Status desconhecido permanece elegível (HD:425–427).
3. Havendo dedicadas elegíveis, ordena por `vram_mb or 0`, decrescente, e escolhe a primeira (HD:446–450). Empate preserva ordem da lista; não existe desempate por fabricante, modelo ou status OK contra desconhecido.
4. A ordenação usa VRAM enriquecida, mas **antes** do ajuste nominal e da segunda verificação de plausibilidade. Na coleta normal, a plausibilidade já foi filtrada. Para objetos arbitrários passados a recomendar_perfil, um valor implausivelmente alto pode vencer a ordenação e só depois cair em VRAM desconhecida; a função não passa à segunda dedicada nesse caso.
5. Se existe dedicada elegível com VRAM desconhecida, ela ainda tem precedência sobre integradas; o resultado é Balanced/MEDIA. Sem dedicada, qualquer integrada elegível leva a Performance. O ramo integrado não seleciona um modelo individual para fundamentar o reason.

**GPU usada na recomendação não é seleção da GPU de renderização.** Nenhuma instrução converte a escolha em General.Adapters. Há ainda diferença entre detector e exibição já auditada: U:_gpu_principal escolhe dedicada de maior VRAM sobre a lista original, sem filtro de status. HD usa somente utilizáveis. Assim, a GPU exibida pode diferir da considerada pelo detector em presença de dispositivos com status False. Esta é uma consequência da integração existente, sem alteração de sua conclusão anterior.

### H.10. Falhas e limites dos fallbacks

| Ocorrência | Comportamento concreto |
|---|---|
| Exceção no executor CIM | Lista vazia → Balanced/BAIXA na API detectar_hardware; HD:265–268,436–441 |
| stdout vazio ou JSON inválido | Lista vazia; JSON dict é convertido em lista de um item; outros tipos raiz são descartados; HD:269–278 |
| Item não dict ou sem Name não vazio | Item ignorado; HD:236–242 |
| Registry indisponível, raiz inacessível ou falha global | Enriquecimento vazio; valores WMI permanecem; HD:308–316,358–363 |
| Falha ao abrir subchave | Pula subchave; HD:325–329 |
| Falha ao enumerar subchaves | Encerra enumeração e retorna o que acumulou; HD:319–324 |
| DriverDesc/valor ausentes por OSError | Descrição vazia e/ou bytes=0; entrada só adicionada se descrição existir ou memória válida; HD:330–344 |
| Falha de conversão no Registry não coberta pelo except OSError interno | Propaga ao wrapper _vram_system_enriquecer, que retorna lista vazia; pode perder enriquecimento parcial dessa chamada |
| Associação ambígua | Mantém VRAM WMI, não reduz confiança diretamente; efeito na confiança depende das regras posteriores |
| Todas GPUs com status False | Nenhuma utilizável → Balanced/BAIXA |
| Nenhum tipo reconhecido | Balanced/BAIXA, ainda que alguma VRAM seja válida |

Os docstrings “nunca levanta” são mais amplos que alguns corpos: `_coletar_gpus_via_wmi` não envolve o loop de parsing em um catch geral, e `_vram_system_adaptadores` não captura toda conversão localmente. `_normalizar_vram_mb` captura TypeError/ValueError, não toda exceção possível de int. As APIs detectar_gpus/detectar_hardware não possuem catch geral (HD:514–522). Na integração recebida, U:638–641 captura Exception de detectar_hardware e converte para resultado None; o fallback de exibição/aplicação nesse caso permanece o da seção 7.

Assim, “erro comum de coleta → Balanced/BAIXA” e “exceção propagada ao chamador → UI recebe None” são caminhos distintos. Não foram ensaiados dados malformados ou falhas reais nesta auditoria.

### H.11. CPU/RAM e ausência de escrita no dgVoodoo

**CPU e RAM do sistema não interferem na decisão.** Não são coletadas nem consultadas neste arquivo. DriverVersion, video_mode e vendor tampouco participam dos critérios de perfil. Entram na decisão a lista de GPUs, status, classificação por nome, VRAM, origem da VRAM para o teto e quantidade original de adaptadores para confiança.

O módulo não contém abertura/escrita de dgVoodoo.conf ou estado.json, nem chamada ao serviço do Renderizador para aplicar perfil. As operações winreg são de leitura, com OpenKey sem acesso de escrita e consultas/fechamento; não há SetValueEx/DeleteValue/CreateKey. O script PowerShell contém consulta CIM e serialização JSON, sem comandos de alteração.

A única mutação de enriquecimento é **em memória**, nos objetos GpuInfo: vram_mb e vram_source (HD:398–399,407–408). recomendar_perfil retorna HardwareProfile; detectar_hardware coleta e retorna recomendação (HD:519–522). Não aplica essa recomendação.

Portanto, no código auditado:

- **General.Adapters permanece sob controle do serviço: `1` (S:258).**
- **DirectX.VRAM permanece sob controle do serviço: `1024` (S:265).**
- **Nenhum dgVoodoo.conf é alterado diretamente pelo detector.**
- A recomendação só repercute no conf quando a página encaminha a ação explícita ao serviço, usando os pares de Filtering/Antialiasing já documentados.

### H.12. Encerramento da pendência

O caminho implementado permite explicar o relato RTX 4050 Laptop com aproximadamente 6 GiB → Quality/ALTA: nome satisfaz dedicada; VRAM válida próxima de 6144 MiB é ajustada ao nominal; lista com uma GPU permite ALTA, fora da exceção de teto WMI. Isso descreve condições suficientes do código; sem captura da coleta daquela execução não certifica qual fonte de VRAM ou inventário exato foi usado naquele momento.

A pendência documental de hardware_detector.py está encerrada. Permanecem intactas as demais conclusões auditadas e as limitações de validação de campo, dependências externas e semântica dgVoodoo. Nenhuma mudança de comportamento foi realizada ou proposta neste complemento.
