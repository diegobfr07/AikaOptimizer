# AIKA Optimizer V4.1.0

**Ferramenta de otimizacao, modding e extracao de assets para AIKA Online Brasil.**
<img width="1672" height="941" alt="aika-optimizer-v4 1 0-preview" src="https://github.com/user-attachments/assets/fff40254-39a1-4d06-b9b5-e0e49bf4fa1d" />


Desenvolvido em Python com interface PySide6, arquitetura modular e integracao com o Windows. Otimizacao por sessao, AutoMod com backup, extracao de texturas .JIT, organizador de sets, renderizador dgVoodoo2, Cores das Pedras e Central de Ajuda.

---

## Sobre o projeto

O AIKA Optimizer V4.1.0 e uma suite integrada para jogadores de AIKA Online que desejam melhorar a fluidez do jogo, gerenciar mods com seguranca e explorar os assets do cliente. O projeto e estruturado em modulos independentes — cada um com responsabilidade bem definida — e oferece uma interface grafica completa em PySide6.

**Estado atual:** V4.1.0 — release final (validada em Windows 10/11: instalacao limpa, upgrade V4.0 -> V4.1 e desinstalacao aprovados).
**Plataforma:** Windows 10 / Windows 11 (64-bit).
**Licenca:** MIT.
**Compatibilidade:** a V4.1 mantem compatibilidade com configuracoes e backups suportados da V4.0, adotando uma politica de restauracao mais conservadora.

---

## Principais recursos

### Game Session Optimizer

O Game Boost e o motor de otimizacao por sessao. Quando ativado:

- **Classifica todos os processos** em categorias (protegidos, jogo, background opcional, indesejados conhecidos, desconhecidos).
- **Protege processos criticos** do sistema, perifericos, seguranca e os proprios executaveis do AIKA.
- **Processos UNKNOWN nunca sao encerrados** — apenas categorias explicitamente mapeadas.
- **Reduz a prioridade** de processos de fundo conhecidos para liberar recursos.
- **Aplica HIGH_PRIORITY_CLASS** aos executaveis do AIKA quando detectados.
- **Coleta metricas de CPU e RAM antes e depois** para exibir o impacto real.
- **Servicos seguros** (XblGameSave, XblAuthManager) podem ser pausados conforme o modo, com validacao de estado e retry.

O booster trabalha com um lock de sessao e restaura o estado ao final — servicos pausados sao religados e prioridades de fundo sao revertidas, com retry para operacoes que falharem.

### Auto Boost e Modo Agressivo

**Auto Boost** (opcional, configuravel):
- Detecta automaticamente quando uma nova sessao do AIKA e iniciada.
- Executa a otimizacao completa uma vez por sessao.
- Evita execucoes duplicadas quando a otimizacao ja preparou o ambiente.
- Ao final da sessao, o booster e restaurado automaticamente.

**Modo Agressivo** (opcional):
- Amplia o escopo do Game Boost para incluir o encerramento de navegadores (Chrome, Edge, Firefox, Opera, Brave e outros) e atualizadores.
- Pode pausar os servicos seguros da lista atual durante a sessao.
- Quando combinado com Auto Boost, exibe confirmacao antes de prosseguir.

**Modo Normal** e mais conservador: navegadores e atualizadores nao sao tocados, apenas processos de background nao essenciais tem a prioridade ajustada.

### Performance e Sistema

A aba Performance oferece ferramentas manuais e situacionais — nenhuma delas e ativada automaticamente pelo Game Boost:

- **Desativar MPO:** ajuste de compatibilidade para testar problemas de flicker ou stutter em combinacoes especificas de Windows e driver grafico.
- **Isolar CPU:** ajuste experimental de afinidade que remove o Core 0 do processo do jogo. O resultado varia conforme o processador.
- **Limpar Cache:** ferramenta de manutencao que apaga caches graficos (NVIDIA/AMD/DirectX). A recompilacao dos shaders ocorre na proxima execucao.
- **Ajustes de Rede:** configuracao de DNS (Google/Cloudflare), diagnostico de conectividade e limpeza de cache DNS.
- **Plano de Energia:** ativacao do modo de desempenho maximo do Windows.
- **Game Bar / FSE:** desativacao da Game Bar e ajustes de tela cheia exclusiva.
- **TCP NoDelay e Throttling:** configuracoes opcionais de rede via Registry.
- **Prioridade Global:** registro de Image File Execution Options para os executaveis do AIKA.

### Renderizador dgVoodoo2

Permite ao cliente AIKA (DirectX 9) utilizar DirectX 11 como backend grafico:

- Perfis **Performance**, **Balanced** e **Quality**, alem do modo **AUTO**, que seleciona um perfil automaticamente conforme o hardware detectado.
- Ativacao e restauracao com backup e verificacao de integridade dos arquivos.
- Utiliza os componentes dgVoodoo2 2.87.4 redistribuidos em `third_party/dgvoodoo2`.

### AutoMod

Sistema de substituicao de arquivos com seguranca:

- **Indexacao** da arvore de arquivos do jogo (`aika_index.json`).
- **Busca automatica** do arquivo correspondente pelo nome base.
- **Backup obrigatorio** antes de cada substituicao.
- **Validacao de extensao** — extensoes incompativeis sao recusadas.
- **Pipeline DDS -> JIT:** suporte a injecao de texturas DDS em arquivos `.jit` com deteccao de assinaturas (JT31/JT33/JT35/JT20).
- **Historico de mods** aplicados com suporte a restauracao individual ou em lote.
- **Integracao com Explorer:** duplo clique em `.jit` atualiza o historico do AutoMod.

### Audio

Substituicao de arquivos de audio com seguranca:
- Backup automatico do arquivo original.
- Copia do novo arquivo para o destino.
- Restauracao do backup original a qualquer momento.
- Pre-visualizacao temporaria do arquivo de audio.

### Texturas .JIT

Extracao de texturas do formato proprietario `.jit` utilizado pelo cliente do jogo:
- **Formatos suportados:** DDS embutido, JT31, JT33, JT35 e JT20.
- **Saida:** DDS (com geracao de cabecalho) ou TGA (para JT20 8-bit).
- **Validacao de dimensoes** (8 a 8192 pixels).
- Conversao silenciosa via linha de comando (`--jit-silent`).

### Organizador de Sets

Ferramenta de organizacao e conversao de assets:
- Percorre os arquivos do AIKA e identifica sets por convencoes de nome.
- **Organiza por classe** (Guerreiro, Templaria, Atirador, Dual, FC, Cleriga).
- Agrupa variantes pelo prefixo visual do ID: `1101`, `1102` e `1103` ficam em `Familia_Armadura_11`, mantendo cada ID em sua propria subpasta selecionavel.
- Reconhece sets completos antigos de 6 partes, completos atuais de 5 partes e aparencias parciais/individuais sem descartar nenhuma delas.
- Separa **Mesh**, **Texture** e **Objects** em pastas estruturadas.
- **Conversao MSH/MS3 -> OBJ** para visualizar armaduras e armas em 3D, preservando os arquivos originais.
- **Extracao JIT -> DDS/TGA** durante a organizacao.
- **Barra de progresso** com processamento em worker thread — a interface nao congela.
- **Cancelamento cooperativo:** interrompe o processo com seguranca preservando os arquivos ja concluidos.
- **Modo Seguro** que verifica as pastas de destino antes de sobrescrever.
- Gera `set_manifest.json` para cada variante, `family_manifest.json` para a familia visual e `weapon_manifest.json` para as armas mantidas separadamente.

### Injetor de Sets e Armas — modos separados

- O seletor superior alterna entre **SETS** e **ARMAS**, limpando selecoes e staging ao trocar de modo.
- No modo Sets, prepara uma variante de armadura doadora para um set alvo da mesma classe usando exclusivamente `.MSH` e `.JIT`.
- No modo Armas, prepara uma arma doadora para outra arma da mesma classe e tipo usando exclusivamente `.MS3` e `.JIT`.
- IDs de armas não são relacionados aos IDs das armaduras; doador e alvo são escolhidos manualmente dentro do modo Armas.
- O usuario seleciona a subpasta tecnica exata, como `Set_Armadura_1101`; a pasta `Familia_Armadura_11` serve apenas para agrupamento visual.
- Quando uma variante alvo `02`, `03` etc. não possui uma peça `.msh`, o Injetor procura essa mesma peça exclusivamente na variante-base `01` da mesma família e classe. Se existir, o arquivo doador é preparado para esse destino físico compartilhado e a interface exibe um aviso explícito. Esse fallback nunca é aplicado a `.jit`, não inventa texturas e não altera outras peças.
- Texturas de efeito com sufixo `EF` só substituem destinos `EF` equivalentes.
- `.OBJ`, `.DDS` e `.TGA` extraídos para visualização nunca são injetados.
- Oferece simulação, backup, validação por hash e rollback antes de alterar o cliente.
- O histórico de modificações ativas é exibido em cards agrupados por data, com horário, tipo, destino e seleção múltipla para restauração.

### Cores das Pedras

Ferramenta para gerenciar as cores das pedras do cliente:

- Leitura e edicao do perfil de cores (`itemlist6_color_profile.json`).
- Backup versionado por instalacao e restauracao.

### Integracao com Windows

- **Single Instance:** apenas uma instancia do aplicativo e executada por vez. Abrir novamente traz a janela existente.
- **Registro de handler .JIT:** o AIKA Optimizer se registra como manipulador para arquivos `.jit` (HKCU).
- **Duplo clique em .JIT** encaminha o arquivo para a instancia ativa ou inicia conversao silenciosa.
- **Conversao silenciosa** via `--jit-silent` para conversao em lote sem abrir a interface.
- **Inicializacao com Windows** (opcional, configuravel).
- **Bandeja do sistema:** fechar para a bandeja mantem o aplicativo ativo com Watchdog de sessao.
- **Iniciar minimizado** quando ativado com `--startup`.

### Cliente AIKA configuravel

O caminho do cliente AIKA e configuravel e validado (executaveis e estrutura reconhecidos), sem depender de um caminho fixo.

### Central de Ajuda

Central de ajuda integrada com navegacao por categoria, servindo como manual do usuario do AIKA Optimizer.

### Seguranca, backup e restauracao

O projeto adota uma abordagem defensiva:

- **Backup de arquivos:** todo arquivo modificado (mods, audio, texturas) recebe backup automatico antes da substituicao.
- **Backup de Registry:** chaves alteradas sao exportadas como `.reg` antes de qualquer modificacao.
- **Snapshot de sistema:** determinadas configuracoes sao salvas para referencia e restauracao.
- **Transacao com rollback:** o sistema de `TransacaoSistema` registra cada passo executado com seu respectivo callback de reversao. Em caso de falha, executa o rollback na ordem inversa.
- **Restauracao de servicos:** o booster mantem registro exato dos servicos que ele proprio pausou — apenas esses sao religados. Falhas de restauracao geram nova tentativa no proximo ciclo.
- **Prioridades com retry:** processos de fundo que tiveram prioridade alterada sao restaurados individualmente. Se a restauracao falhar, o estado e preservado para retry futuro.
- **Shutdown cooperativo:** ao fechar o aplicativo, tarefas longas (como o Organizador de Sets) sao canceladas em ponto seguro. Servicos, QoS e prioridades sao restaurados antes do encerramento.

> **Nota:** os mecanismos de backup e restauracao cobrem as operacoes gerenciadas pelo AIKA Optimizer. O aplicativo nao oferece garantia de rollback total do sistema nem afirma que nenhuma alteracao e permanente.

---

## Requisitos

- Windows 10 ou Windows 11 (64-bit).
- AIKA Online Brasil instalado (executaveis reconhecidos: `aclient.exe`, `aika.exe`, `aika_br.exe`, `aikabr.exe`, `gameengine.exe`).
- Privilegios de administrador para funcoes que modificam Registry, servicos, prioridades de processo ou associacoes de arquivo.
- Espaco em disco adicional para backups, extracoes e mods (a pasta `AikaOptimizer_Backups` e criada ao lado da instalacao do jogo).

---

## Instalacao

1. Baixe o instalador da V4.1 na pagina de [Releases](https://github.com/diegobfr07/AikaOptimizer/releases).
2. Execute o instalador e siga o assistente.
3. Autorize a elevacao de privilegios quando solicitada.
4. Abra o AIKA Optimizer V4.1 pelo atalho na Area de Trabalho.
5. Configure as opcoes desejadas na aba **Configuracoes**.
6. Selecione o jogo e aplique as otimizacoes conforme sua preferencia.

*(O instalador oficial da V4.1 utiliza Inno Setup e PyInstaller. O instalador e unsigned — o Windows SmartScreen pode exibir um aviso; confira o hash SHA-256 divulgado na pagina de Releases.)*

### Atualizacao (upgrade) da V4.0 para a V4.1

1. Baixe o instalador da V4.1 e execute-o sobre a instalacao existente.
2. E uma atualizacao legitima do mesmo produto (mesmo AppId) — nao cria instalacao paralela.
3. As configuracoes e backups da V4.0 sao preservados, e o autostart continua funcionando apos o upgrade.

### Restauracao

Os ajustes persistentes do sistema (Registry, associacoes de arquivo, prioridades) podem ser revertidos quando desejado pela aba **Restauracao/Seguranca** do aplicativo.

---

## Uso basico

### Otimizacao rapida
1. Abra o AIKA Optimizer.
2. Va ate a aba **Performance**.
3. Clique em **INICIAR OTIMIZACAO GLOBAL** para aplicar ajustes de sistema, rede e prioridade.
4. Inicie o AIKA pelo botao na interface ou manualmente.
5. Se o **Auto Boost** estiver ativo, o Game Session Optimizer sera acionado automaticamente quando o jogo for detectado.
6. Minimize para a bandeja — o aplicativo monitora a sessao e restaura os ajustes da sessao (Booster, prioridades e QoS) ao final.

### Aplicar mods
1. Certifique-se de que o jogo esta **fechado**.
2. Na aba **AutoMod**, reindexe os arquivos do jogo se necessario.
3. Selecione os arquivos de mod (`.bin`, `.jit`, `.dds`).
4. Aplique — o backup e feito automaticamente.
5. Para reverter, use a lista de historico na mesma aba.

### Extrair texturas
1. Arraste arquivos `.jit` para a area de drop ou use o seletor de arquivos.
2. As texturas serao extraidas como `.dds` ou `.tga` conforme o formato.
3. Tambem e possivel usar o **Organizador de Sets** para extracao em lote.

---

## Sobre falsos positivos

Ferramentas como o AIKA Optimizer podem ser sinalizadas por softwares de seguranca devido a natureza de suas operacoes (encerramento de processos, modificacao de Registry, comandos administrativos, associacao de arquivos, ajuste de prioridades e empacotamento PyInstaller).

**Recomendacoes:**
- Baixe sempre da [pagina oficial de Releases](https://github.com/diegobfr07/AikaOptimizer/releases).
- Verifique o hash do arquivo quando disponivel.
- O codigo-fonte e 100% aberto — audite voce mesmo.
- Se preferir, compile seu proprio executavel com PyInstaller a partir do codigo-fonte.
- Caso seu antivirus bloqueie o aplicativo, adicione uma excecao APOS verificar a autenticidade do arquivo.

---

## Desenvolvimento

### Estrutura do projeto

```
AikaOptimizer/
|-- main.py              # Interface PySide6 e fluxo principal
|-- config.py            # Configuracao, logging, helpers
|-- game_booster.py      # Game Session Optimizer, classificacao de processos
|-- performance.py       # MPO, CPU affinity, shader cache, MMCSS
|-- sistema.py           # Limpeza, DNS, plano de energia, prioridade global
|-- automod.py           # AutoMod: indexacao, injecao, historico
|-- audio.py             # Substituicao e restauracao de audio
|-- textura.py           # Extracao de texturas JIT -> DDS/TGA
|-- extractor_sets.py    # Organizador de Sets: backend puro
|-- set_injector.py      # Injetor de Sets e Armas (modos separados)
|-- jit_integration.py   # Integracao .JIT com Windows Explorer
|-- seguranca.py         # Backup, transacoes, rollback, snapshots
|-- dgvoodoo_service.py  # Renderizador dgVoodoo2 (backend)
|-- dgvoodoo_page.py     # Pagina do Renderizador (UI)
|-- dgvoodoo_config_engine.py # Engine de config do dgVoodoo.conf
|-- dgvoodoo_config_schema.py # Schema semantico do dgVoodoo.conf
|-- hardware_detector.py # Deteccao de hardware (perfil AUTO)
|-- help_page.py         # Central de Ajuda
|-- stone_color_page.py  # Cores das Pedras (UI)
|-- stone_color_service.py # Cores das Pedras (backend)
|-- itemlist6_color_engine.py # Engine do perfil de cores
|-- restore_list.py      # Lista de restauracao
|-- optimizer.py         # Fachada (importa todos os modulos)
|-- listadeset.py        # Ferramenta standalone preservada (tkinter)
|-- assets/              # Icones e recursos graficos
|-- third_party/         # Componentes de terceiros (dgVoodoo2)
|-- README.md
|-- THIRD_PARTY_NOTICES.md
```

> `monitor.py` e mantido como legacy e NAO faz parte do runtime atual: nao e importado e nao entra no build. `listadeset.py` e preservada como ferramenta standalone (tkinter).

### Executar em modo desenvolvimento

```bash
# Requer Python 3.11+ e PySide6
pip install PySide6 psutil winshell
python main.py
```

### Configuracao

- **Desenvolvimento:** `config.json` e lido/gravado no diretorio do projeto.
- **Build PyInstaller:** as preferencias do usuario sao armazenadas em `%LOCALAPPDATA%\AIKA Optimizer\config.json`.

---

## Desenvolvedor

**@diegobfr07** — Arquitetura de software, engenharia de sistemas e desenvolvimento de ferramentas para AIKA Online.

---

## Licenca

MIT License — Estude, modifique e compartilhe o projeto livremente, mantendo os devidos creditos aos desenvolvedores originais.

Terceiros redistribuidos (dgVoodoo2): veja [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

*Versao V4.1.0 — Testado em Windows 10 e Windows 11.*
