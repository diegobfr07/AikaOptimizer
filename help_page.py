# -*- coding: utf-8 -*-
"""Central de Ajuda do AIKA Optimizer (V4.1) — página SOMENTE LEITURA.

Explica cada área do aplicativo em linguagem simples e cognitivamente
acessível. A página não modifica configuração, não toca o Registro do
Windows, não acessa o cliente do AIKA, não executa serviços e não inicia
threads de sistema: ela apenas navega/rola o conteúdo.

Todo o texto fica centralizado em ``HELP_SECTIONS`` (uma tupla de
seções); a classe ``HelpPage`` apenas renderiza esses dados.
"""
from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

# Rótulo de cada bloco dentro de um tema da Ajuda. O bloco "oque" é a
# descrição principal e NÃO recebe rótulo (o nome da função já o anuncia).
_LABEL_BLOCO = {
    "oque": "O QUE FAZ",  # mantido por semântica; não é renderizado
    "quando": "Quando usar",
    "como": "Como usar",
    "altera": "O que muda",
    "desfazer": "Como desfazer",
    "compat": "Compatibilidade",
    "aviso": "AVISO",
}

# Blocos renderizados como texto simples, sem rótulo próprio.
_SEM_ROTULO = {"p", "oque"}

# Rótulos compactos usados APENAS nos cards de navegação. O título completo
# da categoria continua no cabeçalho do conteúdo (ex.: "Texturas (.JIT)").
_CARD_LABELS = {
    "texturas": "Texturas",
    "injetor": "Injetor",
}

_QSS = """
    QWidget#HelpPage, QWidget#HelpSelector, QWidget#HelpContent,
    QScrollArea#HelpScroll, QScrollArea#HelpScroll > QWidget > QWidget,
    QStackedWidget#HelpStack {
        background-color: transparent;
    }
    QLabel#HelpTitle {
        color: white;
        font-size: 20px;
        font-weight: bold;
    }
    QLabel#HelpSubtitle {
        color: #A0A0B0;
        font-size: 13px;
    }
    QLabel#HelpSectionTitle {
        color: white;
        font-size: 17px;
        font-weight: bold;
        padding-bottom: 4px;
        border-bottom: 2px solid #BF00FF;
    }
    QLabel#HelpThemeTitle {
        color: #BF00FF;
        font-size: 14px;
        font-weight: bold;
        margin-top: 2px;
    }
    QLabel#HelpBlockLabel {
        color: #D6D6DE;
        font-size: 11px;
        font-weight: bold;
        margin-top: 3px;
    }
    QLabel#HelpParagraph {
        color: #D6D6DE;
        font-size: 13px;
        background: transparent;
        border: none;
    }
    QFrame#HelpContentCard {
        background-color: rgba(10, 10, 18, 140);
        border: 1px solid rgba(191, 0, 255, 70);
        border-radius: 10px;
    }
    QPushButton#HelpNavButton {
        background-color: rgba(20, 18, 30, 0.85);
        color: #A9A9BC;
        border: 1px solid rgba(120, 120, 150, 0.35);
        border-radius: 8px;
        padding: 7px 10px;
        font-size: 12px;
        font-weight: bold;
        text-align: center;
    }
    QPushButton#HelpNavButton:hover {
        background-color: rgba(60, 30, 90, 0.85);
        border: 1px solid rgba(191, 0, 255, 120);
        color: #E6E6F0;
    }
    QPushButton#HelpNavButton:checked {
        background-color: rgba(77, 0, 128, 0.75);
        border: 1px solid #BF00FF;
        color: white;
    }
    QPushButton#HelpNavButton:checked:hover {
        background-color: rgba(90, 0, 150, 0.85);
        border: 1px solid #BF00FF;
        color: white;
    }
    QFrame#HelpWarning {
        background-color: rgba(255, 80, 80, 0.12);
        border: 1px solid rgba(255, 110, 110, 0.5);
        border-radius: 8px;
    }
    QLabel#HelpWarningLabel {
        color: #FF8A8A;
        font-size: 11px;
        font-weight: bold;
    }
    QLabel#HelpWarningText {
        color: #FFC9C9;
        font-size: 13px;
    }
"""


# =============================================================================
# CONTEÚDO CENTRAL DA AJUDA
# =============================================================================
# Cada seção tem: id (âncora), rotulo (usado na navegação e no título da
# seção) e temas. Cada tema possui blocos. Bloco = tupla (tipo, lista de
# parágrafos). Tipos: p | oque | quando | como | altera | desfazer | compat |
# aviso.
# =============================================================================

HELP_SECTIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "performance",
        "rotulo": "Performance",
        "temas": (
            {
                "titulo": "Painel da página inicial",
                "blocos": (
                    ("oque", (
                        "Mostra em tempo real o uso de CPU e RAM, a quantidade de "
                        "processos abertos e o estado do AIKA.",
                        "Se houver mais de uma conta aberta, todas são reconhecidas.",
                    )),
                ),
            },
            {
                "titulo": "Desativar MPO",
                "blocos": (
                    ("oque", (
                        "Pode corrigir piscadas, microtravadas ou brilho estranho "
                        "causados pela composição de imagem do Windows em alguns PCs.",
                        "O ajuste desativa o recurso MPO do Windows.",
                    )),
                    ("quando", (
                        "Use somente se você estiver com problema gráfico.",
                    )),
                    ("desfazer", (
                        "Use RESTAURAR SISTEMA na página Segurança.",
                    )),
                ),
            },
            {
                "titulo": "Isolar CPU",
                "blocos": (
                    ("oque", (
                        "Faz o AIKA deixar de usar o primeiro núcleo lógico do "
                        "processador durante a sessão.",
                    )),
                    ("quando", (
                        "Use com o jogo aberto.",
                        "O resultado varia conforme o processador.",
                    )),
                    ("desfazer", (
                        "Reinicie o jogo. O Windows volta a usar todos os núcleos.",
                    )),
                ),
            },
            {
                "titulo": "Turbo Boost",
                "blocos": (
                    ("oque", (
                        "Executa a mesma Otimização Global da página inicial.",
                    )),
                    ("p", (
                        "Esse botão não altera o recurso Turbo Boost do processador.",
                    )),
                    ("desfazer", (
                        "Ao fechar o AIKA Optimizer, os ajustes voltam ao normal.",
                    )),
                ),
            },
            {
                "titulo": "Limpar Cache",
                "blocos": (
                    ("oque", (
                        "Remove caches gráficos que o Windows e o jogo podem recriar.",
                    )),
                    ("quando", (
                        "Use quando o jogo mostrar gráficos estranhos depois de "
                        "uma atualização ou da troca de placa de vídeo.",
                    )),
                    ("p", (
                        "Na primeira abertura depois da limpeza, o jogo pode "
                        "demorar um pouco mais enquanto recria o cache.",
                    )),
                ),
            },
            {
                "titulo": "Otimização Global",
                "blocos": (
                    ("oque", (
                        "Reduz a concorrência de programas em segundo plano e "
                        "prioriza o AIKA durante a sessão de jogo.",
                        "O programa acompanha o jogo e pode aplicar as regras de "
                        "rede previstas na configuração.",
                    )),
                    ("como", (
                        "Clique no botão INICIAR OTIMIZAÇÃO GLOBAL.",
                        "Aguarde a otimização terminar.",
                        "Se o AIKA estiver fechado, o AIKA Optimizer tentará "
                        "abri-lo ao concluir.",
                    )),
                    ("desfazer", (
                        "Ao fechar o AIKA Optimizer, os ajustes da sessão são "
                        "devolvidos ao normal quando possível.",
                    )),
                ),
            },
            {
                "titulo": "Modo Agressivo",
                "blocos": (
                    ("oque", (
                        "Versão mais forte da otimização: também pode fechar "
                        "navegadores e atualizadores e pausar serviços pesados.",
                        "Processos protegidos e o próprio AIKA nunca são fechados.",
                    )),
                    ("aviso", (
                        "Salve o que estiver fazendo nos navegadores antes de usar.",
                    )),
                ),
            },
        ),
    },
    {
        "id": "sistema",
        "rotulo": "Sistema",
        "temas": (
            {
                "titulo": "Servidor DNS",
                "blocos": (
                    ("oque", (
                        "Troca o servidor DNS usado pelo Windows.",
                        "Você pode escolher Google, Cloudflare ou restaurar a "
                        "configuração automática do Windows.",
                    )),
                    ("como", (
                        "Clique no cartão Google DNS, Cloudflare ou Restaurar Padrão.",
                        "Confira o resultado no diagnóstico de rede logo abaixo.",
                    )),
                    ("p", (
                        "DNS não aumenta FPS e não garante ping menor.",
                    )),
                    ("desfazer", (
                        "Clique em Restaurar Padrão ou use RESTAURAR SISTEMA na "
                        "página Segurança.",
                    )),
                ),
            },
            {
                "titulo": "Diagnóstico de rede",
                "blocos": (
                    ("oque", (
                        "Mostra o adaptador de rede ativo e o DNS em uso.",
                    )),
                    ("p", (
                        "ATUALIZAR relê as informações.",
                        "TESTAR DNS mede a resposta dos servidores DNS.",
                        "LIMPAR CACHE DNS apaga a memória temporária de nomes do Windows.",
                    )),
                ),
            },
            {
                "titulo": "Prioridade de Rede",
                "blocos": (
                    ("oque", (
                        "Dá preferência ao tráfego de rede do AIKA no Windows, para "
                        "ele competir menos com outros programas.",
                    )),
                    ("p", (
                        "Não corrige problemas da sua conexão nem garante ping menor.",
                    )),
                    ("desfazer", (
                        "Desmarque a opção. Ao fechar o AIKA Optimizer, as regras "
                        "criadas também são removidas.",
                    )),
                ),
            },
            {
                "titulo": "Modo Tela Cheia (FSE)",
                "blocos": (
                    ("oque", (
                        "Otimiza o modo tela cheia e desativa a Game Bar/GameDVR.",
                        "Não altera a resolução do jogo por si só.",
                    )),
                    ("quando", (
                        "Use se o jogo em tela cheia sofrer cortes ou interferência "
                        "da Game Bar.",
                    )),
                    ("desfazer", (
                        "Use RESTAURAR SISTEMA na página Segurança.",
                    )),
                ),
            },
            {
                "titulo": "Remover Efeitos Poluídos",
                "blocos": (
                    ("oque", (
                        "Remove efeitos visuais pesados do jogo para deixar a imagem "
                        "mais limpa.",
                        "É uma mudança visual: não altera dano ou status do personagem.",
                    )),
                    ("altera", (
                        "Remove arquivos de efeitos visuais do jogo, com backup antes "
                        "da remoção.",
                    )),
                    ("desfazer", (
                        "Use a página Restauração para desfazer individualmente, ou "
                        "RESTAURAR JOGO na página Segurança.",
                    )),
                ),
            },
            {
                "titulo": "Reduzir Delay (TCP)",
                "blocos": (
                    ("oque", (
                        "Ativa uma configuração de rede do Windows chamada TCP "
                        "NoDelay, para reduzir a latência da troca de pacotes.",
                    )),
                    ("p", (
                        "O efeito depende da sua rede e não é garantia de ping menor.",
                    )),
                    ("desfazer", (
                        "Use RESTAURAR SISTEMA na página Segurança.",
                    )),
                ),
            },
        ),
    },
    {
        "id": "automod",
        "rotulo": "AutoMod",
        "temas": (
            {
                "titulo": "AutoMod",
                "blocos": (
                    ("oque", (
                        "Substitui arquivos do jogo por modificações compatíveis e "
                        "guarda o original em backup.",
                    )),
                    ("como", (
                        "Clique em SELECIONAR ARQUIVOS e escolha os arquivos.",
                        "Confira a lista exibida.",
                        "Clique em INJETAR MODS NO AIKA.",
                    )),
                    ("compat", (
                        "O programa encontra o arquivo do jogo pelo nome. É preciso "
                        "existir um arquivo correspondente.",
                        "Texturas .JIT, .DDS e .TGA são convertidas quando o arquivo "
                        "do jogo é .JIT.",
                        "Formatos como .png, .jpg e .txt não são injetáveis.",
                    )),
                    ("p", (
                        "Em muitos casos, texturas e áudios podem ser trocados com o "
                        "jogo aberto. Se um arquivo estiver em uso, feche o jogo e "
                        "tente novamente.",
                    )),
                    ("desfazer", (
                        "Use a página Restauração para desfazer cada injeção.",
                    )),
                ),
            },
        ),
    },
    {
        "id": "audio",
        "rotulo": "Áudio",
        "temas": (
            {
                "titulo": "Injetor de Áudio Customizado",
                "blocos": (
                    ("oque", (
                        "Troca um som do AIKA por um arquivo de áudio seu. O original "
                        "fica guardado em backup.",
                    )),
                    ("como", (
                        "Em 01 Áudio original, escolha o som do jogo com SELECIONAR e "
                        "confira com OUVIR.",
                        "Em 02 Novo áudio, escolha o seu arquivo (MP3, WAV, OGG ou M4A) "
                        "e confira com OUVIR.",
                        "Clique em INJETAR NOVO ÁUDIO.",
                    )),
                    ("p", (
                        "Se o formato não for compatível, o programa avisa e não altera "
                        "o arquivo.",
                        "Feche o jogo se a troca falhar com mensagem de arquivo em uso.",
                    )),
                    ("desfazer", (
                        "Clique em Restaurar áudio original, na própria página.",
                    )),
                ),
            },
        ),
    },
    {
        "id": "texturas",
        "rotulo": "Texturas (.JIT)",
        "temas": (
            {
                "titulo": "Extrator de Texturas",
                "blocos": (
                    ("oque", (
                        "Extrai as texturas guardadas dentro de um arquivo .JIT e gera "
                        "um arquivo .DDS ou .TGA.",
                    )),
                    ("como", (
                        "Clique em SELECIONAR .JIT e escolha um ou vários arquivos.",
                        "Clique em EXTRAIR TEXTURAS.",
                        "O arquivo convertido fica na mesma pasta do .JIT original.",
                    )),
                    ("p", (
                        "Você também pode arrastar arquivos .JIT para a área da página.",
                        "Texturas com paleta de cores viram TGA; as demais viram DDS.",
                    )),
                    ("p", (
                        "O .JIT original não é alterado. Se já existir uma conversão, "
                        "o programa pergunta antes de substituir.",
                    )),
                ),
            },
            {
                "titulo": "Abrir .JIT pelo Windows",
                "blocos": (
                    ("oque", (
                        "O AIKA Optimizer pode abrir arquivos .JIT pelo Explorador "
                        "do Windows.",
                    )),
                    ("p", (
                        "Com a associação ativa, ao dar dois cliques em um arquivo "
                        ".JIT, o AIKA Optimizer faz a conversão automaticamente.",
                        "A opção fica em Configurações. Desmarcá-la remove a associação, "
                        "e o programa respeita a sua escolha.",
                    )),
                ),
            },
        ),
    },
    {
        "id": "org_sets",
        "rotulo": "Org. Sets",
        "temas": (
            {
                "titulo": "Organizador de Sets",
                "blocos": (
                    ("oque", (
                        "Copia os arquivos de aparência do AIKA para uma pasta sua, "
                        "organizados por classe e conjunto.",
                        "O jogo não é alterado: a leitura é no AIKA e a gravação é na "
                        "pasta escolhida.",
                    )),
                    ("p", (
                        "Separa por classe: Guerreiro, Templaria, Atirador, Dual, FC "
                        "e Cleriga.",
                    )),
                    ("como", (
                        "Em PASTA DO AIKA – ORIGEM, escolha onde o jogo está instalado.",
                        "Em PASTA DE SAÍDA – DESTINO, escolha onde salvar os resultados.",
                        "Marque as opções extras, se quiser: Extrair Modelos 3D e/ou "
                        "Extrair Texturas.",
                        "Escolha o ritmo: Turbo (para SSD) ou Seguro (para HD).",
                        "Clique em INICIAR EXTRAÇÃO TOTAL.",
                    )),
                    ("compat", (
                        "Os extras convertem modelos (.MSH/.MS3) e texturas (.JIT) em "
                        "arquivos de visualização (.OBJ/.DDS/.TGA).",
                        "Executar novamente copia apenas o que falta ou foi alterado.",
                    )),
                    ("desfazer", (
                        "Apague a pasta de destino criada. O jogo não é afetado.",
                    )),
                ),
            },
        ),
    },
    {
        "id": "injetor",
        "rotulo": "Injetor Sets/Arm",
        "temas": (
            {
                "titulo": "Injetor de Sets e Armas",
                "blocos": (
                    ("oque", (
                        "Copia a aparência de um conjunto (ou arma) para outro item "
                        "do jogo.",
                        "O programa usa as pastas criadas pelo Organizador de Sets.",
                    )),
                    ("como", (
                        "Escolha o tipo: SETS ou ARMAS.",
                        "Escolha a aparência doadora.",
                        "Escolha o item alvo que receberá a aparência.",
                        "Em Selecionar Cliente, aponte a pasta do AIKA que receberá "
                        "a mudança.",
                        "Clique em PREPARAR e confira o relatório.",
                        "Clique em SIMULAR INJEÇÃO para ver o que será feito.",
                        "Clique em INJETAR NO AIKA para aplicar.",
                    )),
                    ("altera", (
                        "Substitui os modelos e texturas do item alvo pelos do doador.",
                    )),
                    ("aviso", (
                        "Feche o AIKA antes de injetar: com o jogo aberto a injeção "
                        "é bloqueada.",
                    )),
                    ("desfazer", (
                        "Use a página Restauração para reverter a injeção.",
                    )),
                ),
            },
        ),
    },
    {
        "id": "pedras",
        "rotulo": "Pedras",
        "temas": (
            {
                "titulo": "Cores das Pedras",
                "blocos": (
                    ("oque", (
                        "Muda apenas a cor visual das pedras do AIKA para facilitar a "
                        "identificação.",
                    )),
                    ("como", (
                        "Escolha a cor de Ataque PvP.",
                        "Escolha a cor de Defesa PvP.",
                        "Escolha a cor das demais pedras coloridas.",
                        "Clique em Gerar cópia e, em seguida, em Aplicar no AIKA.",
                    )),
                    ("p", (
                        "O programa verifica o arquivo antes de alterar.",
                        "Se uma atualização do jogo mudar sua estrutura, a aplicação "
                        "é bloqueada para proteger o jogo.",
                    )),
                    ("desfazer", (
                        "Use a linha das Pedras na página Restauração.",
                        "RESTAURAR PADRÕES, na própria página, volta as cores "
                        "escolhidas ao padrão.",
                    )),
                ),
            },
        ),
    },
    {
        "id": "renderizador",
        "rotulo": "Renderizador",
        "temas": (
            {
                "titulo": "Renderizador",
                "blocos": (
                    ("oque", (
                        "Usa o dgVoodoo2 para executar o DirectX 9 do AIKA através "
                        "do DirectX 11.",
                    )),
                    ("p", (
                        "O resultado depende da placa de vídeo; não há garantia de "
                        "aumento de FPS.",
                    )),
                ),
            },
            {
                "titulo": "Perfil AUTO",
                "blocos": (
                    ("oque", (
                        "Analisa o hardware e escolhe um dos três perfis.",
                    )),
                ),
            },
            {
                "titulo": "Perfil Desempenho",
                "blocos": (
                    ("oque", (
                        "Prioriza leveza. Indicado para PCs mais modestos ou vídeo "
                        "integrado.",
                    )),
                ),
            },
            {
                "titulo": "Perfil Equilibrado",
                "blocos": (
                    ("oque", (
                        "Equilíbrio entre desempenho e qualidade de imagem.",
                    )),
                ),
            },
            {
                "titulo": "Perfil Qualidade",
                "blocos": (
                    ("oque", (
                        "Filtragem e suavização mais altas. Indicado para máquinas "
                        "com maior capacidade gráfica.",
                    )),
                ),
            },
            {
                "titulo": "Ativar, Reaplicar e Restaurar",
                "blocos": (
                    ("oque", (
                        "ATIVAR DGVOODOO2 habilita o Renderizador no jogo.",
                        "REAPLICAR reconstrói a configuração base recomendada — não "
                        "reaplica o último perfil escolhido.",
                        "RESTAURAR DIRECTX ORIGINAL devolve o DirectX original do jogo.",
                    )),
                    ("p", (
                        "Feche o jogo antes de ativar, reaplicar ou restaurar.",
                    )),
                ),
            },
        ),
    },
    {
        "id": "restauracao",
        "rotulo": "Restauração",
        "temas": (
            {
                "titulo": "Página Restauração",
                "blocos": (
                    ("oque", (
                        "Lista as modificações registradas pelo AIKA Optimizer.",
                        "Cada linha é uma operação: mods injetados, sets e armas "
                        "aplicados, efeitos removidos e as cores das Pedras.",
                    )),
                    ("como", (
                        "Escolha uma data no filtro, se quiser.",
                        "Marque as operações que deseja desfazer.",
                        "Clique em RESTAURAR SELECIONADAS.",
                    )),
                    ("p", (
                        "A restauração devolve os arquivos ao estado anterior. Nas "
                        "Pedras, volta à base preservada.",
                        "Só é possível restaurar operações com backup válido.",
                    )),
                ),
            },
        ),
    },
    {
        "id": "seguranca",
        "rotulo": "Segurança",
        "temas": (
            {
                "titulo": "Central de Restauração e Segurança",
                "blocos": (
                    ("oque", (
                        "Reúne as restaurações gerais em dois botões.",
                        "RESTAURAR SISTEMA desfaz os ajustes do Windows.",
                        "RESTAURAR JOGO devolve os arquivos do AIKA ao original.",
                    )),
                ),
            },
            {
                "titulo": "Restaurar Sistema",
                "blocos": (
                    ("oque", (
                        "Reverte os ajustes do Windows feitos pelo AIKA Optimizer "
                        "(DNS, MPO, Game Bar, TCP e prioridades).",
                        "Também devolve as configurações do booster ao normal.",
                    )),
                    ("p", (
                        "Restaura o que o AIKA Optimizer alterou. Mudanças feitas "
                        "manualmente depois podem não ser desfeitas.",
                    )),
                ),
            },
            {
                "titulo": "Restaurar Jogo",
                "blocos": (
                    ("oque", (
                        "Devolve os arquivos do AIKA alterados pelo programa ao "
                        "estado original, usando os backups.",
                        "Ao final, o histórico de modificações do jogo é limpo.",
                    )),
                ),
            },
        ),
    },
    {
        "id": "configuracoes",
        "rotulo": "Configurações",
        "temas": (
            {
                "titulo": "Inicialização e Janela",
                "blocos": (
                    ("p", (
                        "Inicializar com o Windows: o AIKA Optimizer abre ao entrar "
                        "no Windows.",
                        "Iniciar minimizado: ao iniciar com o Windows, o AIKA "
                        "Optimizer abre direto na bandeja.",
                        "Fechar para bandeja: fechar a janela mantém o programa na "
                        "bandeja.",
                    )),
                ),
            },
            {
                "titulo": "Game Booster",
                "blocos": (
                    ("p", (
                        "Auto Boost: executa a Otimização Global uma vez quando uma "
                        "nova sessão do AIKA é detectada.",
                        "Modo Agressivo: permite fechar navegadores e atualizadores. "
                        "Processos protegidos permanecem intactos.",
                    )),
                ),
            },
            {
                "titulo": "Cliente do AIKA",
                "blocos": (
                    ("p", (
                        "Define a pasta onde o jogo está instalado. Essa pasta é "
                        "usada pelas funções que precisam localizar os arquivos do AIKA.",
                    )),
                ),
            },
            {
                "titulo": "Integração com o Windows",
                "blocos": (
                    ("oque", (
                        "Abrir arquivos .JIT com o AIKA Optimizer.",
                    )),
                    ("p", (
                        "Marcado = associação ativa; desmarcado = associação removida.",
                        "O programa respeita a sua escolha e não reativa a associação "
                        "sozinho depois de você desmarcar.",
                    )),
                ),
            },
        ),
    },

)


# =============================================================================
# FUNÇÃO DE APOIO AOS TESTES: retorna todos os textos visíveis da Ajuda.
# =============================================================================
def coletar_textos() -> list[str]:
    """Lista os textos renderizados pela página (títulos + parágrafos)."""
    textos: list[str] = []
    for secao in HELP_SECTIONS:
        textos.append(secao["rotulo"])
        for tema in secao["temas"]:
            textos.append(tema["titulo"])
            for _tipo, paragrafos in tema["blocos"]:
                textos.extend(paragrafos)
    return textos


def ids_das_secoes() -> tuple[str, ...]:
    """Ids das seções principais, na ordem em que aparecem na página."""
    return tuple(secao["id"] for secao in HELP_SECTIONS)


def rotulos_das_secoes() -> tuple[str, ...]:
    """Rótulos das seções principais (usados também na navegação)."""
    return tuple(secao["rotulo"] for secao in HELP_SECTIONS)


def rotulos_dos_cards() -> tuple[str, ...]:
    """Rótulos compactos dos cards (o conteúdo mantém o título completo)."""
    return tuple(
        _CARD_LABELS.get(secao["id"], secao["rotulo"]) for secao in HELP_SECTIONS
    )


# =============================================================================
# PÁGINA (SOMENTE LEITURA)
# =============================================================================


class HelpPage(QWidget):
    """Central de Ajuda com navegação por categoria (somente leitura).

    Estrutura: cabeçalho -> seletor com 12 cards -> conteúdo DA CATEGORIA
    SELECIONADA em um ``QStackedWidget`` interno (um QScrollArea por
    categoria). Navega apenas: nenhum backend, arquivo, Registro ou thread
    de sistema é tocado.
    """

    _COLUNAS_PADRAO = 4
    _COLUNAS_ESTREITAS = 3
    _BREAKPOINT_4_COLUNAS = 780
    _LARGURA_CARD_MIN = 148
    _LARGURA_CARD_MAX = 186
    _MARGENS_PAGINA = 28

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HelpPage")
        self._categorias: tuple[str, ...] = tuple(s["id"] for s in HELP_SECTIONS)
        self._botoes: dict[str, QPushButton] = {}
        self._paginas: dict[str, QScrollArea] = {}
        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)
        self._cards_host: QWidget | None = None
        self._cards_grid = QGridLayout()
        self._stack: QStackedWidget | None = None
        self._scroll: QScrollArea | None = None  # scroll da categoria atual
        self._construir()
        self._aplicar_estilo()
        self._refluxo_cards()
        self.selecionar_categoria(self._categorias[0])

    # ------------------------------------------------------------------
    # API pública (navegação por categoria)
    # ------------------------------------------------------------------
    def categorias(self) -> tuple[str, ...]:
        return self._categorias

    def categoria_atual(self) -> str:
        if self._stack is None:
            return self._categorias[0]
        return self._categorias[self._stack.currentIndex()]

    def selecionar_categoria(self, ident: str) -> None:
        """Destaca o card e mostra SOMENTE o conteúdo da categoria."""
        if ident not in self._paginas:
            raise KeyError(ident)
        indice = self._categorias.index(ident)
        if self._stack is not None:
            self._stack.setCurrentIndex(indice)
        botao = self._botoes[ident]
        if not botao.isChecked():
            botao.setChecked(True)
        self._scroll = self._paginas[ident]
        self._scroll.verticalScrollBar().setValue(0)

    def scroll_ate(self, ident: str) -> None:
        """Compatibilidade: seleciona a categoria (sempre abre no topo)."""
        self.selecionar_categoria(ident)

    def cards(self) -> tuple[QPushButton, ...]:
        return tuple(self._botoes[ident] for ident in self._categorias)

    def botao_da_categoria(self, ident: str) -> QPushButton:
        return self._botoes[ident]

    def scroll_da_categoria(self, ident: str) -> QScrollArea:
        return self._paginas[ident]
    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------
    def _construir(self) -> None:
        externo = QVBoxLayout(self)
        externo.setContentsMargins(14, 12, 14, 8)
        externo.setSpacing(8)

        titulo = QLabel("Ajuda")
        titulo.setObjectName("HelpTitle")
        titulo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        subtitulo = QLabel(
            "Entenda cada função do AIKA Optimizer e veja como utilizá-la."
        )
        subtitulo.setObjectName("HelpSubtitle")
        subtitulo.setWordWrap(True)
        subtitulo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        externo.addWidget(titulo)
        externo.addWidget(subtitulo)

        self._construir_seletor(externo)

        cartao = QFrame()
        cartao.setObjectName("HelpContentCard")
        cartao_layout = QVBoxLayout(cartao)
        cartao_layout.setContentsMargins(12, 10, 12, 10)
        cartao_layout.setSpacing(0)
        self._stack = QStackedWidget()
        self._stack.setObjectName("HelpStack")
        self._stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        for secao in HELP_SECTIONS:
            pagina = self._criar_pagina_categoria(secao)
            self._paginas[secao["id"]] = pagina
            self._stack.addWidget(pagina)
        cartao_layout.addWidget(self._stack)
        externo.addWidget(cartao, 1)

    def _construir_seletor(self, externo: QVBoxLayout) -> None:
        linha = QHBoxLayout()
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(0)
        linha.addStretch(1)
        self._cards_host = QWidget()
        self._cards_host.setObjectName("HelpSelector")
        self._cards_host.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._cards_grid.setContentsMargins(0, 0, 0, 0)
        self._cards_grid.setHorizontalSpacing(6)
        self._cards_grid.setVerticalSpacing(6)
        self._cards_host.setLayout(self._cards_grid)
        linha.addWidget(self._cards_host, 0)
        linha.addStretch(1)
        externo.addLayout(linha)

        for secao in HELP_SECTIONS:
            ident, rotulo = secao["id"], secao["rotulo"]
            botao = QPushButton(_CARD_LABELS.get(ident, rotulo))
            botao.setObjectName("HelpNavButton")
            botao.setProperty("categoria", ident)
            botao.setCheckable(True)
            botao.setCursor(Qt.PointingHandCursor)
            botao.setFocusPolicy(Qt.NoFocus)
            botao.setMinimumHeight(32)
            botao.clicked.connect(
                lambda _=False, i=ident: self.selecionar_categoria(i)
            )
            self._grupo.addButton(botao)
            self._botoes[ident] = botao

    def _criar_pagina_categoria(self, secao: dict[str, Any]) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("HelpScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        conteudo = QWidget()
        conteudo.setObjectName("HelpContent")
        conteudo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout = QVBoxLayout(conteudo)
        layout.setContentsMargins(2, 2, 6, 8)
        layout.setSpacing(4)
        cabecalho = QLabel(secao["rotulo"])
        cabecalho.setObjectName("HelpSectionTitle")
        cabecalho.setWordWrap(True)
        cabecalho.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(cabecalho)
        for indice, tema in enumerate(secao["temas"]):
            # Espaço entre funções (nome roxo + respiro separa os assuntos).
            if indice > 0:
                layout.addSpacing(8)
            self._adicionar_tema(layout, tema)
        layout.addStretch(1)
        scroll.setWidget(conteudo)
        scroll.viewport().setAutoFillBackground(False)
        return scroll

    def _adicionar_tema(self, layout: QVBoxLayout, tema: dict[str, Any]) -> None:
        bloco = QVBoxLayout()
        bloco.setContentsMargins(0, 0, 0, 0)
        bloco.setSpacing(3)
        titulo = QLabel(str(tema["titulo"]))
        titulo.setObjectName("HelpThemeTitle")
        titulo.setWordWrap(True)
        titulo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        bloco.addWidget(titulo)
        for tipo, paragrafos in tema["blocos"]:
            self._adicionar_bloco(bloco, tipo, paragrafos)
        layout.addLayout(bloco)

    def _adicionar_bloco(
        self, layout: QVBoxLayout, tipo: str, paragrafos: Sequence[str]
    ) -> None:
        if tipo == "aviso":
            self._adicionar_aviso(layout, paragrafos)
            return
        rotulo = _LABEL_BLOCO.get(tipo)
        if rotulo and tipo not in _SEM_ROTULO:
            marcador = QLabel(rotulo)
            marcador.setObjectName("HelpBlockLabel")
            marcador.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            layout.addWidget(marcador)
        for indice, paragrafo in enumerate(paragrafos, start=1):
            texto = f"{indice}. {paragrafo}" if tipo == "como" else paragrafo
            linha = QLabel(texto)
            linha.setObjectName("HelpParagraph")
            linha.setWordWrap(True)
            linha.setTextFormat(Qt.PlainText)
            linha.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            layout.addWidget(linha)

    def _adicionar_aviso(
        self, layout: QVBoxLayout, paragrafos: Sequence[str]
    ) -> None:
        cartao = QFrame()
        cartao.setObjectName("HelpWarning")
        lay = QVBoxLayout(cartao)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(3)
        marcador = QLabel("AVISO")
        marcador.setObjectName("HelpWarningLabel")
        lay.addWidget(marcador)
        for paragrafo in paragrafos:
            linha = QLabel(paragrafo)
            linha.setObjectName("HelpWarningText")
            linha.setWordWrap(True)
            linha.setTextFormat(Qt.PlainText)
            linha.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            lay.addWidget(linha)
        layout.addWidget(cartao)

    def _aplicar_estilo(self) -> None:
        self.setStyleSheet(_QSS)

    # ------------------------------------------------------------------
    # Layout dos cards (4 colunas; 3 apenas em largura estreita)
    # ------------------------------------------------------------------
    def _refluxo_cards(self) -> None:
        """Distribui os cards em 4 colunas (3 abaixo do breakpoint).

        A grade usa largura fixa centralizada, limitada pela largura da
        página: os cards nunca esticam exageradamente em telas grandes nem
        ficam espremidos (o que cortaria rótulos) em telas menores.
        """
        if self._cards_host is None or not self._botoes:
            return
        colunas = (
            self._COLUNAS_PADRAO
            if self.width() >= self._BREAKPOINT_4_COLUNAS
            else self._COLUNAS_ESTREITAS
        )
        while self._cards_grid.count():
            self._cards_grid.takeAt(0)
        for indice, ident in enumerate(self._categorias):
            self._cards_grid.addWidget(
                self._botoes[ident], indice // colunas, indice % colunas
            )
            self._botoes[ident].show()
        for coluna in range(colunas):
            self._cards_grid.setColumnStretch(coluna, 1)
        for coluna in range(colunas, self._cards_grid.columnCount()):
            self._cards_grid.setColumnStretch(coluna, 0)

        espaco = self._cards_grid.horizontalSpacing()
        largura_ideal = colunas * self._LARGURA_CARD_MAX + (colunas - 1) * espaco
        largura_minima = colunas * self._LARGURA_CARD_MIN + (colunas - 1) * espaco
        disponivel = max(largura_minima, self.width() - self._MARGENS_PAGINA)
        self._cards_host.setFixedWidth(min(largura_ideal, disponivel))
        for ident in self._categorias:
            self._botoes[ident].setMinimumWidth(self._LARGURA_CARD_MIN)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._refluxo_cards()
