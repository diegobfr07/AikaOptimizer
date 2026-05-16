# -*- coding: utf-8 -*-
import sys
import os
import ctypes
import threading
import string
import traceback

# --- O TOQUE FINAL PARA O ÍCONE NA BARRA DE TAREFAS ---
# Isso avisa o Windows quem é o dono do app ANTES da interface carregar
try:
    meu_app_id = 'cbm.aikaoptimizer.v3'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(meu_app_id)
except Exception:
    pass
# -----------------------------------------------------

try:
    from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QLabel,
                                   QTextEdit, QWidget, QVBoxLayout, QHBoxLayout,
                                   QGridLayout, QFrame, QGraphicsDropShadowEffect,
                                   QStackedWidget, QButtonGroup, QFileDialog, QMessageBox,
                                   QSystemTrayIcon, QMenu)
    from PySide6.QtGui import QCursor, QColor, QPainter, QPainterPath, QPen, QPixmap, QIcon
    from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup, Signal, QObject, QUrl, QThread, QTimer
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

    # Importação à prova de falhas para o QAction (dependendo da versão do teu PySide6)
    try:
        from PySide6.QtGui import QAction
    except ImportError:
        from PySide6.QtWidgets import QAction

    import optimizer as opt

except Exception as e:
    ctypes.windll.user32.MessageBoxW(0, f"Erro nas importações iniciais:\n\n{traceback.format_exc()}", "Crash Report - Aika Optimizer", 0x10)
    sys.exit(1)


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def resolver_caminho(caminho_relativo):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, caminho_relativo)

class TarefaWorker(QThread):
    def __init__(self, func):
        super().__init__()
        self.func = func
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if not self._is_cancelled:
            try:
                self.func()
            except Exception:
                pass

class SinaisUI(QObject):
    log_signal = Signal(str)

class AikaCardGlow(QWidget):
    def __init__(self, parent, image_path, titulo):
        super().__init__(parent)
        self.setFixedSize(150, 190)
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(8)

        self.caixa_imagem = QFrame()
        self.caixa_imagem.setFixedSize(145, 145)
        self.caixa_imagem.setStyleSheet("background-color: transparent;")

        layout_caixa = QVBoxLayout(self.caixa_imagem)
        layout_caixa.setContentsMargins(0, 0, 0, 0)
        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setStyleSheet("border-radius: 18px;")

        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            self.lbl_image.setPixmap(pixmap.scaled(145, 145, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        else:
            self.lbl_image.setText("AIKA")
            self.lbl_image.setStyleSheet("color: #BF00FF; font-weight: bold; font-size: 20px;")

        layout_caixa.addWidget(self.lbl_image)

        self.lbl_titulo = QLabel(titulo)
        self.lbl_titulo.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_titulo.setAlignment(Qt.AlignCenter)

        layout_principal.addWidget(self.caixa_imagem, 0, Qt.AlignCenter)
        layout_principal.addWidget(self.lbl_titulo, 0, Qt.AlignTop | Qt.AlignHCenter)

class AikaOptimizerPro(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AIKA OPTIMIZER V3.0")
        self.resize(1024, 680)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        caminho_icone = resolver_caminho("icone.ico")
        self.setWindowIcon(QIcon(caminho_icone))

        self.sinais = SinaisUI()
        self.sinais.log_signal.connect(self.atualizar_log)

        self.tarefa_lock = threading.Lock()
        self.executando_tarefa = False
        self.dragPos = None
        self.worker = None

        opt.limpar_pasta_temp_audio()
        opt.ativar_timer_resolution()

        # ========================================================
        # TRAY ICON (BANDEJA DO SISTEMA - SEGUNDO PLANO)
        # ========================================================
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(caminho_icone))

        tray_menu = QMenu()
        
        acao_restaurar = QAction("Abrir Aika Optimizer", self)
        acao_restaurar.triggered.connect(self.showNormal)
        tray_menu.addAction(acao_restaurar)

        acao_boost = QAction("🚀 Game Boost", self)
        acao_boost.triggered.connect(self.iniciar_boost_seguro)
        tray_menu.addAction(acao_boost)

        tray_menu.addSeparator()

        acao_sair = QAction("Sair", self)
        acao_sair.triggered.connect(self.fechar_app)
        tray_menu.addAction(acao_sair)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.clique_na_tray)
        self.tray_icon.show()
        # ========================================================

        # PADRONIZAÇÃO DOS BOTÕES COM HOVER DO MAC_OS (100% SEGURO)
        estilo_global = """
            * { font-family: 'Segoe UI', 'Roboto', 'Open Sans', sans-serif; }
            QWidget#CentralWidget { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #050508, stop:1 #111118); border: 2px solid #2A004D; border-radius: 18px; }
            QLabel#Titulo { color: white; font-size: 22px; font-weight: bold; letter-spacing: 1px; }
            QFrame#AikaCard { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0A0A0E, stop:1 #12121A); border: 3px solid #3d0066; border-radius: 20px; }
            QTextEdit#AikaTerminal { background-color: rgba(5, 5, 8, 200); border: 2px solid #4D0080; border-radius: 12px; color: #BF00FF; font-family: 'Consolas', 'Courier New', monospace; font-size: 13px; padding: 10px; }
            QScrollBar:vertical { width: 0px; }
            
            /* PADRONIZAÇÃO DOS BOTÕES SUPERIORES */
            QPushButton.WinButton { 
                background-color: transparent; 
                border-radius: 12px; 
                color: #BF00FF; 
                font-size: 15px; 
                font-weight: bold;
                font-family: 'Arial';
            }
            
            /* Cores macOS no Hover */
            QPushButton#BtnClose:hover { background-color: #ff605c; color: white; }
            QPushButton#BtnMin:hover { background-color: #ffbd44; color: #050508; }
            QPushButton#BtnMax:hover { background-color: #00ca4e; color: white; }

            QFrame#Sidebar { background-color: rgba(10, 10, 15, 150); border-right: 2px solid #2A004D; border-radius: 15px; }
            QPushButton.MenuButton { background-color: transparent; color: #888899; text-align: left; padding: 12px 20px; font-size: 15px; font-weight: bold; border: none; border-left: 4px solid transparent; }
            QPushButton.MenuButton:checked { color: #BF00FF; border-left: 4px solid #BF00FF; background-color: rgba(191, 0, 255, 0.1); }
            QPushButton.ToolButton { background-color: rgba(77, 0, 128, 0.2); border: 1px solid #4D0080; border-radius: 8px; color: white; font-weight: bold; padding: 10px 15px; font-size: 13px; }
            QPushButton.ToolButton:hover { background-color: rgba(191, 0, 255, 0.3); border: 1px solid #BF00FF; }
        """
        self.central_widget = QWidget()
        self.central_widget.setObjectName("CentralWidget")
        self.central_widget.setStyleSheet(estilo_global)
        self.setCentralWidget(self.central_widget)
        layout_principal = QVBoxLayout(self.central_widget)

        layout_titulo = QHBoxLayout()
        layout_titulo.setContentsMargins(0, 5, 0, 5)
        
        self.lbl_logo = QLabel()
        logo_pixmap = QPixmap(caminho_icone)
        self.lbl_logo.setPixmap(logo_pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        self.lbl_titulo = QLabel("AIKA OPTIMIZER V3.0")
        self.lbl_titulo.setObjectName("Titulo")

        # Layout agrupado para os controles do topo
        layout_controles = QHBoxLayout()
        layout_controles.setSpacing(8)

        # Botão Minimizar (Caractere Hífen)
        btn_min = QPushButton("-")
        btn_min.setObjectName("BtnMin")
        btn_min.setFixedSize(24, 24)
        btn_min.setProperty("class", "WinButton")
        btn_min.clicked.connect(self.minimizar_para_tray)

        # Botão Maximizar (Caractere Letra 'O' Maiúscula)
        self.btn_max = QPushButton("O") 
        self.btn_max.setObjectName("BtnMax")
        self.btn_max.setFixedSize(24, 24)
        self.btn_max.setProperty("class", "WinButton")
        self.btn_max.clicked.connect(self.alternar_maximizacao)

        # Botão Fechar (Caractere Letra 'X' Maiúscula)
        btn_close = QPushButton("X")
        btn_close.setObjectName("BtnClose")
        btn_close.setFixedSize(24, 24)
        btn_close.setProperty("class", "WinButton")
        btn_close.clicked.connect(self.fechar_app)

        layout_controles.addWidget(btn_min)
        layout_controles.addWidget(self.btn_max)
        layout_controles.addWidget(btn_close)

        layout_titulo.addWidget(self.lbl_logo)
        layout_titulo.addWidget(self.lbl_titulo)
        layout_titulo.addStretch() 
        layout_titulo.addLayout(layout_controles)
        layout_principal.addLayout(layout_titulo)

        layout_corpo = QHBoxLayout()

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(200)
        layout_sidebar = QVBoxLayout(sidebar)
        self.grupo_menu = QButtonGroup(self)
        
        self.btn_aba_performance = self.criar_botao_menu("🚀 Performance", 0)
        self.btn_aba_ferramentas = self.criar_botao_menu("🛠️ Sistema", 1)
        self.btn_aba_automod     = self.criar_botao_menu("📦 AutoMod", 2)
        self.btn_aba_audio       = self.criar_botao_menu("🎵 Áudio", 3)
        self.btn_aba_extrator_jit= self.criar_botao_menu("🎨 Texturas (.JIT)", 4)
        self.btn_aba_restore     = self.criar_botao_menu("🛡️ Segurança", 5)
        
        layout_sidebar.addWidget(self.btn_aba_performance)
        layout_sidebar.addWidget(self.btn_aba_ferramentas)
        layout_sidebar.addWidget(self.btn_aba_automod)
        layout_sidebar.addWidget(self.btn_aba_audio)
        layout_sidebar.addWidget(self.btn_aba_extrator_jit)
        layout_sidebar.addWidget(self.btn_aba_restore)
        layout_sidebar.addStretch()
        layout_corpo.addWidget(sidebar)

        self.telas = QStackedWidget()

        # --- TELA 0: PERFORMANCE ---
        page_perf = QWidget()
        layout_perf = QVBoxLayout(page_perf)
        layout_perf.setContentsMargins(10, 20, 10, 10)

        def obter_imagem(nome_base):
            caminho_png = resolver_caminho(f"{nome_base}.png")
            caminho_jpg = resolver_caminho(f"{nome_base}.jpg")
            return caminho_png if os.path.exists(caminho_png) else caminho_jpg

        grid_cards = QGridLayout()
        grid_cards.addWidget(AikaCardGlow(self, obter_imagem("Desempenho"), "Desativar\nMPO"), 0, 0)
        grid_cards.addWidget(AikaCardGlow(self, obter_imagem("Teclado"), "Isolar\nCPU"), 0, 1)
        grid_cards.addWidget(AikaCardGlow(self, obter_imagem("Rede"), "Turbo\nBoost"), 0, 2) 
        grid_cards.addWidget(AikaCardGlow(self, obter_imagem("Limpeza"), "Limpar\nCache"), 0, 3)
        layout_perf.addLayout(grid_cards)

        layout_perf.addStretch(1)

        desc_perf = QLabel("💡 <b>Otimizações Exclusivas da Joy Impact Engine:</b><br>"
                           "• <b>Desativar MPO:</b> Remove o Multiplane Overlay do Windows, eliminando travamentos e 'flickers' crônicos do DirectX 9.<br>"
                           "• <b>Isolar CPU:</b> Isola o Aika do Core 0 (núcleo ocupado pelo sistema) para eliminar de vez o Stuttering (engasgos).<br>"
                           "• <b>Turbo Boost:</b> Eleva a prioridade de renderização gráfica e ativa o Game Booster silencioso, fechando processos inúteis.<br>"
                           "• <b>Limpar Cache:</b> Apaga arquivos de cache antigos da NVIDIA/AMD, forçando uma renderização limpa e fluida das skills.<br>"
                           "• <b>Timer Resolution 1ms:</b> Injetado direto no Kernel do Windows para garantir o menor input-lag possível no PvP.")
        desc_perf.setWordWrap(True)
        desc_perf.setStyleSheet("color: #A0A0B0; font-size: 13px; background-color: rgba(255,255,255,10); padding: 12px; border-radius: 8px;")
        desc_perf.setAlignment(Qt.AlignLeft)
        layout_perf.addWidget(desc_perf)
        layout_perf.addSpacing(15)

        self.btn_boost = QPushButton("⚡ INICIAR OTIMIZAÇÃO GLOBAL")
        self.btn_boost.setMinimumHeight(80)
        self.btn_boost.setMinimumWidth(450)
        self.btn_boost.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_boost.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #BF00FF, stop:1 #660099); color: white; font-weight: bold; font-size: 20px; border-radius: 15px; border: 2px solid #BF00FF;")
        self.btn_glow = QGraphicsDropShadowEffect(self)
        self.btn_glow.setBlurRadius(35)
        self.btn_glow.setColor(QColor(191, 0, 255, 180))
        self.btn_glow.setOffset(0, 0)
        self.btn_boost.setGraphicsEffect(self.btn_glow)
        self.setup_botao_pulsar()

        self.btn_boost.clicked.connect(self.iniciar_boost_seguro)

        layout_perf.addWidget(self.btn_boost, 0, Qt.AlignCenter)
        layout_perf.addStretch(1)
        self.telas.addWidget(page_perf)

        # --- TELA 1: SISTEMA ---
        page_sys = QWidget()
        layout_sys = QVBoxLayout(page_sys)
        layout_sys.setSpacing(12)
        
        lbl_sys_t = QLabel("🛠️ Configurações Avançadas do Sistema")
        lbl_sys_t.setStyleSheet("color: white; font-size: 20px; font-weight: bold; margin-bottom: 0px;")
        layout_sys.addWidget(lbl_sys_t)
        
        lbl_dns = QLabel("Seleção de Servidor DNS:")
        lbl_dns.setStyleSheet("color: #BF00FF; font-weight: bold;")
        layout_sys.addWidget(lbl_dns)
        
        grid_dns = QGridLayout()
        grid_dns.addWidget(self.criar_botao_ferramenta("Google DNS (8.8.8.8)", lambda: self.acao_dns("Google")), 0, 0)
        grid_dns.addWidget(self.criar_botao_ferramenta("Cloudflare DNS (1.1.1.1)", lambda: self.acao_dns("Cloudflare")), 0, 1)
        grid_dns.addWidget(self.criar_botao_ferramenta("Restaurar Padrão", lambda: self.acao_dns("Padrao")), 0, 2)
        layout_sys.addLayout(grid_dns)

        lbl_m = QLabel("Otimizações Aika Online (Hot-Swap):")
        lbl_m.setStyleSheet("color: #BF00FF; font-weight: bold; margin-top: 5px;")
        layout_sys.addWidget(lbl_m)
        
        grid_m = QGridLayout()
        grid_m.setVerticalSpacing(10)
        lay_cpu = self.criar_botao_com_desc("🔥 Isolar Núcleos (Afinidade)", self.acao_afinidade, "Se o jogo já estiver aberto, força o processo a desocupar o núcleo 0 imediatamente.")
        lay_gb = self.criar_botao_com_desc("🚫 Modo Tela Cheia (FSE)", self.acao_gamebar, "Desliga a Game Bar e ativa o Modo Tela Cheia Exclusivo, vital para jogos antigos.")
        lay_wp = self.criar_botao_com_desc("🗑️ Remover Efeitos Poluídos", self.acao_weapon, "Apaga os arquivos visuais pesados com segurança (ex: WeaponEff3.bin). Elimina o lag visual.")
        lay_tcp = self.criar_botao_com_desc("⚡ Reduzir Delay (TCP)", self.acao_tcp_nodelay, "Aplica TCP NoDelay na sua placa de rede, enviando pacotes de dados instantaneamente.")
        grid_m.addLayout(lay_cpu, 0, 0)
        grid_m.addLayout(lay_gb, 0, 1)
        grid_m.addLayout(lay_wp, 1, 0)
        grid_m.addLayout(lay_tcp, 1, 1)
        layout_sys.addLayout(grid_m)
        
        layout_sys.addStretch()
        self.telas.addWidget(page_sys)

        # --- TELA 2: AUTOMOD ---
        page_automod = QWidget()
        layout_automod = QVBoxLayout(page_automod)
        layout_automod.setSpacing(15)
        lbl_automod_t = QLabel("📦 AutoMod - Injetor de Modificações Nativas")
        lbl_automod_t.setStyleSheet("color: white; font-size: 20px; font-weight: bold; margin-bottom: 5px;")
        layout_automod.addWidget(lbl_automod_t)

        desc_automod = QLabel("💡 <b>Novo Indexador JSON:</b> A injeção agora varre a pasta do jogo instantaneamente usando indexação inteligente. Pode injetar texturas e áudios com o jogo aberto (Hot-Swapping) sem engasgar o PC!")
        desc_automod.setWordWrap(True)
        desc_automod.setStyleSheet("color: #A0A0B0; font-size: 13px; background-color: rgba(255,255,255,10); padding: 12px; border-radius: 8px;")
        layout_automod.addWidget(desc_automod)

        lay_status_mods = QHBoxLayout()
        self.lbl_mods_selecionados = QLabel("Nenhum arquivo de modificação carregado.")
        self.lbl_mods_selecionados.setStyleSheet("color: #888; font-size: 13px; font-family: 'Consolas', monospace; padding: 5px;")

        self.btn_limpar_mods = QPushButton("🗑️ Limpar Seleção")
        self.btn_limpar_mods.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_limpar_mods.setStyleSheet("background-color: rgba(255, 34, 34, 0.8); color: white; font-weight: bold; border-radius: 5px; padding: 5px 15px; border: 1px solid #FF2222;")
        self.btn_limpar_mods.hide()
        self.btn_limpar_mods.clicked.connect(self.limpar_selecao_mods)

        lay_status_mods.addWidget(self.lbl_mods_selecionados)
        lay_status_mods.addWidget(self.btn_limpar_mods)
        layout_automod.addLayout(lay_status_mods)

        self.terminal_automod = QTextEdit()
        self.terminal_automod.setReadOnly(True)
        self.terminal_automod.setPlaceholderText("Lista de arquivos selecionados aparecerá aqui...")
        self.terminal_automod.setStyleSheet("background-color: rgba(0, 0, 0, 80); border: 1px solid #3d0066; border-radius: 8px; color: #AAA; font-family: 'Consolas', monospace; font-size: 11px;")
        self.terminal_automod.setFixedHeight(115)
        layout_automod.addWidget(self.terminal_automod)

        layout_automod.addWidget(self.criar_botao_ferramenta("📂 Selecionar Arquivos de Mod", self.selecionar_arquivos_mod))

        btn_inj_mod = QPushButton("⚙️ INJETAR MODS NO AIKA")
        btn_inj_mod.setStyleSheet("background: #BF00FF; color: white; padding: 15px; border-radius: 12px; font-weight: bold; font-size: 16px;")
        btn_inj_mod.setCursor(QCursor(Qt.PointingHandCursor))
        btn_inj_mod.clicked.connect(self.acao_injetar_mods)

        layout_automod.addStretch()
        layout_automod.addWidget(btn_inj_mod)
        self.telas.addWidget(page_automod)

        # --- TELA 3: ÁUDIO ---
        page_audio = QWidget()
        layout_audio = QVBoxLayout(page_audio)
        layout_audio.setSpacing(15)
        lbl_audio_t = QLabel("🎵 Injetor de Áudio Customizado")
        lbl_audio_t.setStyleSheet("color: white; font-size: 20px; font-weight: bold; margin-bottom: 5px;")
        layout_audio.addWidget(lbl_audio_t)
        desc_audio = QLabel("💡 <b>Como funciona:</b> Escolha qualquer música (MP3 ou WAV) e o sistema converte e aplica no jogo. O arquivo original ficará preservado no nosso Snapshot de Segurança.")
        desc_audio.setWordWrap(True)
        desc_audio.setStyleSheet("color: #A0A0B0; font-size: 13px; background-color: rgba(255,255,255,10); padding: 12px; border-radius: 8px;")
        layout_audio.addWidget(desc_audio)

        self.estilo_default_lbl = "color: #888; font-size: 13px; margin-top: 5px; padding: 2px;"

        self.lbl_alvo = QLabel("1. Arquivo Original do Jogo: Nenhum selecionado")
        self.lbl_alvo.setStyleSheet(self.estilo_default_lbl)
        
        lay_aud_jogo = QHBoxLayout()
        btn_alvo = self.criar_botao_ferramenta("📂 Buscar .bin na Pasta Sound", self.selecionar_audio_jogo)
        self.btn_play_jogo = self.criar_botao_ferramenta("▶️ Ouvir Original", self.tocar_audio_jogo)
        lay_aud_jogo.addWidget(btn_alvo)
        lay_aud_jogo.addWidget(self.btn_play_jogo)

        self.lbl_novo_audio = QLabel("2. Sua Nova Música/Efeito: Nenhum selecionado")
        self.lbl_novo_audio.setStyleSheet(self.estilo_default_lbl.replace("margin-top: 5px;", ""))

        lay_aud_btns = QHBoxLayout()
        btn_novo = self.criar_botao_ferramenta("🎵 Escolher Música (MP3/WAV)", self.selecionar_arquivo_audio)
        self.btn_play_novo = self.criar_botao_ferramenta("▶️ Ouvir Novo", self.tocar_previa)
        lay_aud_btns.addWidget(btn_novo)
        lay_aud_btns.addWidget(self.btn_play_novo)

        self.btn_conv_aud = QPushButton("🔄 INJETAR NOVO ÁUDIO")
        self.btn_conv_aud.setStyleSheet("background: #BF00FF; color: white; padding: 15px; border-radius: 12px; font-weight: bold; font-size: 16px;")
        self.btn_conv_aud.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_conv_aud.clicked.connect(self.acao_substituir_audio)

        btn_restaurar_1 = QPushButton("↩️ RESTAURAR APENAS ESTE ÁUDIO")
        btn_restaurar_1.setStyleSheet("background: rgba(255, 34, 34, 0.7); border: 1px solid #FF2222; color: white; padding: 15px; border-radius: 12px; font-weight: bold; font-size: 14px;")
        btn_restaurar_1.setCursor(QCursor(Qt.PointingHandCursor))
        btn_restaurar_1.clicked.connect(self.acao_restaurar_audio)

        layout_audio.addWidget(self.lbl_alvo)
        layout_audio.addLayout(lay_aud_jogo)
        layout_audio.addWidget(self.lbl_novo_audio)
        layout_audio.addLayout(lay_aud_btns)
        layout_audio.addStretch()
        layout_audio.addWidget(self.btn_conv_aud)
        layout_audio.addWidget(btn_restaurar_1)
        self.telas.addWidget(page_audio)

        # --- TELA 4: EXTRATOR JIT ---
        page_jit = QWidget()
        layout_jit = QVBoxLayout(page_jit)
        layout_jit.setSpacing(15)
        
        lbl_jit_t = QLabel("🎨 Extrator de Texturas (.JIT para .DDS/.TGA)")
        lbl_jit_t.setStyleSheet("color: white; font-size: 20px; font-weight: bold; margin-bottom: 5px;")
        layout_jit.addWidget(lbl_jit_t)

        desc_jit = QLabel("💡 <b>Motor Coringa Nativo:</b> Extrai texturas encriptadas. Se for TGA padrão, salva direto. Se for o misterioso JT20 (8-bits com paleta), converte para TGA 32-bits na mesma hora!")
        desc_jit.setWordWrap(True)
        desc_jit.setStyleSheet("color: #A0A0B0; font-size: 13px; background-color: rgba(255,255,255,10); padding: 12px; border-radius: 8px;")
        layout_jit.addWidget(desc_jit)

        self.lbl_jit_selecionado = QLabel("Nenhuma textura selecionada.")
        self.lbl_jit_selecionado.setStyleSheet(self.estilo_default_lbl)
        layout_jit.addWidget(self.lbl_jit_selecionado)

        lay_btn_jit = QHBoxLayout()
        lay_btn_jit.addWidget(self.criar_botao_ferramenta("📂 Buscar Texturas (.JIT)", self.selecionar_arquivos_jit))
        lay_btn_jit.addWidget(self.criar_botao_ferramenta("📁 Abrir Pasta", self.abrir_pasta_textura_jit))
        layout_jit.addLayout(lay_btn_jit)
        
        layout_jit.addStretch()

        btn_extrair_jit = QPushButton("🎨 EXTRAIR TEXTURAS AGORA")
        btn_extrair_jit.setStyleSheet("background: #6A0DAD; color: white; padding: 15px; border-radius: 12px; font-weight: bold; font-size: 16px;")
        btn_extrair_jit.setCursor(QCursor(Qt.PointingHandCursor))
        btn_extrair_jit.clicked.connect(self.acao_extrair_jit)
        layout_jit.addWidget(btn_extrair_jit)

        self.telas.addWidget(page_jit)

        # --- TELA 5: RESTAURAÇÃO ---
        page_restore = QWidget()
        layout_restore = QVBoxLayout(page_restore)
        layout_restore.setSpacing(25)

        lbl_res_t = QLabel("🛡️ Central de Restauração e Segurança do Sistema")
        lbl_res_t.setStyleSheet("color: white; font-size: 20px; font-weight: bold; margin-bottom: 5px;")
        layout_restore.addWidget(lbl_res_t)

        desc_res = QLabel("💡 <b>Auditoria Ativa:</b> O processo de restauração trabalha em lotes inteligentes para garantir que o seu disco rígido não congele.<br><br>"
                          "Desfaça todas as modificações e reverta o sistema ou os arquivos do jogo para o estado original com total segurança.")
        desc_res.setWordWrap(True)
        desc_res.setStyleSheet("color: #A0A0B0; font-size: 14px; background-color: rgba(255,255,255,10); padding: 15px; border-radius: 8px; line-height: 1.5;")
        layout_restore.addWidget(desc_res)

        btn_res_all = QPushButton("🎮 DESFAZER MODIFICAÇÕES NO JOGO")
        btn_res_all.setStyleSheet("background: #FF1111; color: white; padding: 25px; border-radius: 15px; font-weight: bold; font-size: 16px; border: 2px solid #880000;")
        btn_res_all.setCursor(QCursor(Qt.PointingHandCursor))
        btn_res_all.clicked.connect(self.acao_restaurar_tudo)

        btn_res_sys = QPushButton("🖥️ DESFAZER TWEAKS DE SISTEMA E BOOSTER")
        btn_res_sys.setStyleSheet("background: #FF8800; color: white; padding: 25px; border-radius: 15px; font-weight: bold; font-size: 16px; border: 2px solid #CC6600;")
        btn_res_sys.setCursor(QCursor(Qt.PointingHandCursor))
        btn_res_sys.clicked.connect(self.acao_restaurar_sistema)

        layout_restore.addStretch()
        layout_restore.addWidget(btn_res_sys)
        layout_restore.addWidget(btn_res_all)
        self.telas.addWidget(page_restore)

        # LAYOUT FINAL DIREITA E LOGS INICIAIS
        layout_direita = QVBoxLayout()
        layout_direita.addWidget(self.telas)
        self.log_box = QTextEdit()
        self.log_box.setObjectName("AikaTerminal")
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(115)

        self.log_box.setText(">> 🟢 MOTOR DX9 E KERNEL BLINDADOS INICIALIZADOS...\n>> 🟢 PRONTO PARA ALTA PERFORMANCE NA JOY IMPACT ENGINE.")
        layout_direita.addWidget(self.log_box)
        layout_corpo.addLayout(layout_direita)
        layout_principal.addLayout(layout_corpo)

        # SISTEMAS AUXILIARES
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.5)
        self.btn_aba_performance.setChecked(True)

    # ========================================================
    # FUNÇÕES DE UI E CONTROLE (TRAY ICON)
    # ========================================================
    def minimizar_para_tray(self):
        self.hide() # Apenas esconde a tela silenciosamente
        
    def clique_na_tray(self, reason):
        # Se o usuário clicar (simples ou duplo) no ícone do relógio, volta a tela
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.showNormal()
            self.activateWindow()

    def alternar_maximizacao(self):
        if self.isMaximized():
            self.showNormal()
            self.btn_max.setText("O") # Ícone Textual Seguro
        else:
            self.showMaximized()
            self.btn_max.setText("O") # Ícone Textual Seguro

    def criar_botao_com_desc(self, t, a, d):
        lay = QVBoxLayout()
        lay.setSpacing(2)
        btn = self.criar_botao_ferramenta(t, a)
        lay.addWidget(btn)
        lbl = QLabel(d)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: #A0A0B0; font-size: 11px; padding: 0px 5px;")
        lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lay.addWidget(lbl)
        lay.addStretch()
        return lay

    def setup_botao_pulsar(self):
        a1 = QPropertyAnimation(self.btn_glow, b"color")
        a1.setDuration(800)
        a1.setStartValue(QColor(191,0,255,50))
        a1.setEndValue(QColor(191,0,255,255))
        a2 = QPropertyAnimation(self.btn_glow, b"color")
        a2.setDuration(800)
        a2.setStartValue(QColor(191,0,255,255))
        a2.setEndValue(QColor(191,0,255,50))
        self.btn_anim = QSequentialAnimationGroup()
        self.btn_anim.addAnimation(a1)
        self.btn_anim.addAnimation(a2)
        self.btn_anim.setLoopCount(-1)
        self.btn_anim.start()

    def criar_botao_menu(self, t, i):
        btn = QPushButton(t)
        btn.setProperty("class", "MenuButton")
        btn.setCheckable(True)
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.grupo_menu.addButton(btn, i)
        btn.clicked.connect(lambda: self.telas.setCurrentIndex(i))
        return btn

    def criar_botao_ferramenta(self, t, a):
        btn = QPushButton(t)
        btn.setProperty("class", "ToolButton")
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.clicked.connect(a)
        return btn

    def atualizar_log(self, m):
        self.log_box.append(f">> {m}")
        self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())

    def limpar_execucao(self):
        with self.tarefa_lock:
            self.executando_tarefa = False
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def executar_em_background(self, f):
        with self.tarefa_lock:
            if self.executando_tarefa:
                self.sinais.log_signal.emit("🟡 Uma tarefa já está em andamento. Aguarde...")
                return
            self.executando_tarefa = True

        self.worker = TarefaWorker(f)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.finished.connect(self.limpar_execucao)
        self.worker.start()

    # ========================================================
    # AÇÕES DO SISTEMA E OTIMIZAÇÕES
    # ========================================================
    def iniciar_boost_seguro(self):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Limpeza Opcional da Lixeira")
        msg_box.setText("Deseja esvaziar a Lixeira do Windows durante a otimização?\n\nArquivos excluídos não poderão ser recuperados.")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.button(QMessageBox.Yes).setText("Sim, Limpar")
        msg_box.button(QMessageBox.No).setText("Não, Manter")

        estilo_msgbox = "QMessageBox { background-color: #0A0A0E; border: 2px solid #2A004D; } QLabel { color: white; font-size: 14px; font-weight: bold; } QPushButton { background-color: rgba(77, 0, 128, 0.3); border: 1px solid #4D0080; border-radius: 8px; color: white; font-weight: bold; padding: 8px 15px; font-size: 13px; min-width: 80px; } QPushButton:hover { background-color: #BF00FF; border: 1px solid white; }"
        msg_box.setStyleSheet(estilo_msgbox)
        limpar_lix = (msg_box.exec() == QMessageBox.Yes)

        def tarefa_transacao():
            self.sinais.log_signal.emit("🟢 Iniciando Otimização Global DX9...")
            transacao = opt.TransacaoSistema()
            try:
                transacao.executar(opt.salvar_snapshot_sistema)
                transacao.executar(opt.limpar_profundo, limpar_lix)
                transacao.executar(opt.limpar_shader_cache)
                transacao.executar(opt.modo_desempenho_maximo, rollback=opt.restaurar_snapshot_sistema)
                transacao.executar(opt.desativar_mpo)
                transacao.executar(opt.otimizar_multimidia_jogos) 
                transacao.executar(opt.prioridade_total)         
                transacao.executar(opt.otimizar_rede_estabilidade)
                
                self.sinais.log_signal.emit("🟢 Ativando Turbo Boost (Limpando RAM e Bloatwares)...")
                p_mortos, r_otimizados, s_parados = opt.ativar_game_booster()
                self.sinais.log_signal.emit(f"🟢 TURBO ON: {p_mortos} Processos mortos | {r_otimizados} Apps hibernados | {s_parados} Serviços parados.")

                self.sinais.log_signal.emit("🟢 Gerando Índice I/O Inteligente do jogo para o AutoMod...")
                transacao.executar(opt.criar_index_jogo)
                
                opt.otimizar_afinidade_aika()
                
                self.sinais.log_signal.emit("🟢 OTIMIZAÇÃO COMPLETA FINALIZADA COM SUCESSO!")
                if not opt.jogo_esta_aberto():
                    self.sinais.log_signal.emit("🟢 Iniciando o jogo agora...")
                    opt.iniciar_jogo()
            except Exception as e:
                self.sinais.log_signal.emit(f"🔴 ERRO CRÍTICO: {e}")
                self.sinais.log_signal.emit("🟡 Rollback ativado para segurança.")

        self.executar_em_background(tarefa_transacao)

    # ========================================================
    # EVENTOS DE MODDING, EXTRAÇÃO E ÁUDIO
    # ========================================================
    def encontrar_pasta_sound(self):
        p = r"C:\CBMgames\AikaOnlineBrasil\Sound"
        if os.path.exists(p): return p
        for d in string.ascii_uppercase:
            c = os.path.join(f"{d}:\\", "CBMgames", "AikaOnlineBrasil", "Sound")
            if os.path.exists(c): return c
        return ""

    ESTILO_NEON_CARREGADO = "color: #00FF00; font-size: 13px; font-weight: bold; background-color: rgba(0, 50, 0, 150); border: 1px solid #00FF00; padding: 5px; border-radius: 5px;"

    def selecionar_audio_jogo(self):
        f, _ = QFileDialog.getOpenFileName(self, "Selecionar Original", self.encontrar_pasta_sound(), "Aika (*.bin *.wav);;Tudo (*.*)")
        if f:
            self.arquivo_alvo_jogo = f
            self.lbl_alvo.setText(f"1. Original: {f.split('/')[-1]}")
            self.lbl_alvo.setStyleSheet(self.ESTILO_NEON_CARREGADO + " margin-top: 5px;")

    def tocar_audio_jogo(self):
        if not hasattr(self, 'arquivo_alvo_jogo'): return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState: self.player.stop()
        caminho_wav = opt.preparar_previa_audio(self.arquivo_alvo_jogo)
        if caminho_wav:
            self.player.setSource(QUrl.fromLocalFile(caminho_wav))
            self.player.play()
            QTimer.singleShot(10000, opt.limpar_pasta_temp_audio)

    def selecionar_arquivo_audio(self):
        f, _ = QFileDialog.getOpenFileName(self, "Selecionar Novo", "", "Áudio (*.mp3 *.wav *.ogg *.m4a)")
        if f:
            self.arquivo_audio_selecionado = f
            self.lbl_novo_audio.setText(f"2. Novo: {f.split('/')[-1]}")
            self.lbl_novo_audio.setStyleSheet(self.ESTILO_NEON_CARREGADO)

    def tocar_previa(self):
        if not hasattr(self, 'arquivo_audio_selecionado'): return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.stop()
            self.btn_play_novo.setText("▶️ Ouvir Novo")
        else:
            self.player.setSource(QUrl.fromLocalFile(self.arquivo_audio_selecionado))
            self.player.play()
            self.btn_play_novo.setText("⏹️ Parar Novo")

    def selecionar_arquivos_mod(self):
        f, _ = QFileDialog.getOpenFileNames(self, "Mods", "", "Tudo (*.*)")
        if f:
            self.arquivos_mod_selecionados = f
            self.lbl_mods_selecionados.setText(f"🔥 {len(f)} mods prontos para injeção.")
            self.lbl_mods_selecionados.setStyleSheet("color: #00FF00; font-size: 13px; font-weight: bold; background-color: rgba(0, 50, 0, 150); border: 1px solid #00FF00; padding: 5px; border-radius: 5px;")
            self.btn_limpar_mods.show()
            self.terminal_automod.clear()
            for caminho in f: self.terminal_automod.append(f"• {caminho.split('/')[-1]}")

    def limpar_selecao_mods(self):
        self.arquivos_mod_selecionados = []
        self.lbl_mods_selecionados.setText("Nenhum arquivo de modificação carregado.")
        self.lbl_mods_selecionados.setStyleSheet("color: #888; font-size: 13px; font-family: 'Consolas', monospace; padding: 5px;")
        self.terminal_automod.clear()
        self.btn_limpar_mods.hide()

    def acao_injetar_mods(self):
        mods = getattr(self, 'arquivos_mod_selecionados', None)
        if not mods: return
        def tarefa():
            r = opt.injetar_mods(mods)
            if r >= 0: self.sinais.log_signal.emit(f"🟢 OK: {r} mods injetados instantaneamente via JSON Index.")
            else: self.sinais.log_signal.emit("🔴 ERRO: Falha ao injetar mods ou índice não foi gerado.")
        self.executar_em_background(tarefa)

    def selecionar_arquivos_jit(self):
        pasta_base = r"C:\CBMgames\AikaOnlineBrasil" if os.path.exists(r"C:\CBMgames\AikaOnlineBrasil") else ""
        f, _ = QFileDialog.getOpenFileNames(self, "Selecionar Texturas .JIT", pasta_base, "Aika Texture (*.jit)")
        if f:
            self.arquivos_jit_selecionados = f
            self.lbl_jit_selecionado.setText(f"🎨 {len(f)} textura(s) selecionada(s).")
            self.lbl_jit_selecionado.setStyleSheet(self.ESTILO_NEON_CARREGADO)

    def abrir_pasta_textura_jit(self):
        if hasattr(self, 'arquivos_jit_selecionados') and self.arquivos_jit_selecionados:
            try: os.startfile(os.path.dirname(self.arquivos_jit_selecionados[0]))
            except: pass

    def acao_extrair_jit(self):
        jits = getattr(self, 'arquivos_jit_selecionados', None)
        if not jits: return
        def tarefa():
            self.sinais.log_signal.emit(f"🟡 Extraindo {len(jits)} textura(s)...")
            sucesso_count = 0
            for jit in jits:
                ok, msg = opt.extrair_textura_jit(jit)
                if ok: sucesso_count += 1
                self.sinais.log_signal.emit(f"{'🟢' if ok else '🔴'} {os.path.basename(jit)}: {msg}")
            self.sinais.log_signal.emit(f"✅ LOTE CONCLUÍDO: {sucesso_count}/{len(jits)} extraídos!")
        self.executar_em_background(tarefa)

    def acao_substituir_audio(self):
        alvo = getattr(self, 'arquivo_alvo_jogo', None)
        novo = getattr(self, 'arquivo_audio_selecionado', None)
        if not alvo or not novo: return
        def tarefa():
            s, m = opt.substituir_audio_customizado(novo, alvo)
            self.sinais.log_signal.emit("🟢 Sucesso! Áudio injetado." if s else f"🔴 ERRO: {m}")
        self.executar_em_background(tarefa)

    def acao_restaurar_audio(self):
        alvo = getattr(self, 'arquivo_alvo_jogo', None)
        if not alvo: return
        def tarefa():
            s, m = opt.restaurar_audio_original(alvo)
            self.sinais.log_signal.emit(f"🟢 {m}" if s else f"🔴 {m}")
        self.executar_em_background(tarefa)

    def acao_restaurar_tudo(self):
        def tarefa():
            self.sinais.log_signal.emit("🟡 INICIANDO RESTAURAÇÃO EM LOTES (Poupando HDD)...")
            s, m = opt.restaurar_tudo_jogo()
            self.sinais.log_signal.emit(f"🟢 {m}" if s else f"🔴 {m}")
        self.executar_em_background(tarefa)

    def acao_restaurar_sistema(self):
        def tarefa():
            self.sinais.log_signal.emit("🟡 INICIANDO ROLLBACK DO SISTEMA...")
            opt.desativar_game_booster() # Desliga o booster se estiver ativo
            s, m = opt.restaurar_registro_sistema()
            self.sinais.log_signal.emit(f"🟢 {m}" if s else f"🔴 {m}")
        self.executar_em_background(tarefa)

    def acao_dns(self, p):
        def tarefa():
            if opt.alterar_dns(p): self.sinais.log_signal.emit(f"🟢 DNS {p} aplicado.")
        self.executar_em_background(tarefa)

    def acao_afinidade(self):
        def tarefa():
            if opt.otimizar_afinidade_aika(): self.sinais.log_signal.emit("🟢 Afinidade isolada com sucesso! Sem stutters.")
            else: self.sinais.log_signal.emit("🟡 Jogo não encontrado ou não foi possível fixar afinidade.")
        self.executar_em_background(tarefa)

    def acao_gamebar(self):
        def tarefa():
            if opt.desativar_game_bar(): self.sinais.log_signal.emit("🟢 Game Bar desativada e Fullscreen Exclusivo forçado.")
        self.executar_em_background(tarefa)

    def acao_weapon(self):
        def tarefa():
            status = opt.remover_efeitos_pesados_aika()
            if status == 1: 
                self.sinais.log_signal.emit("🟢 Mega-pack de Efeitos removido (Arquivos limpos com segurança)!")
            elif status == 2: 
                self.sinais.log_signal.emit("🟡 Os Efeitos já estão anulados (Arquivos já foram removidos).")
            elif status == 0:
                self.sinais.log_signal.emit("🟡 Arquivos não encontrados (Ou já foram removidos).")
            else:
                self.sinais.log_signal.emit("🔴 Erro ao tentar processar os arquivos de efeitos.")
        self.executar_em_background(tarefa)

    def acao_tcp_nodelay(self):
        def tarefa():
            try:
                if opt.otimizar_tcp_nodelay(): self.sinais.log_signal.emit("🟢 Rotas TCP otimizadas com sucesso!")
            except Exception as e: pass
        self.executar_em_background(tarefa)

    def fechar_app(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.quit()
            if not self.worker.wait(2000): self.worker.terminate()
        
        try:
            self.tray_icon.hide()
        except Exception: pass
        
        opt.desativar_game_booster() # Segurança para não deixar serviços do Windows parados
        opt.limpar_pasta_temp_audio()
        opt.restaurar_timer_resolution()
        self.close()

    # BLOQUEIA O ARRASTAR CASO A TELA ESTEJA MAXIMIZADA
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton: 
            self.dragPos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.isMaximized():
            return 
            
        if event.buttons() == Qt.LeftButton and self.dragPos:
            delta = event.globalPosition().toPoint() - self.dragPos
            self.move(self.pos() + delta)
            self.dragPos = event.globalPosition().toPoint()
            event.accept()

if __name__ == "__main__":
    try:
        if not is_admin():
            caminho_script = os.path.abspath(__file__)
            diretorio_atual = os.path.dirname(caminho_script)
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{caminho_script}"', diretorio_atual, 1)
            sys.exit()
            
        app = QApplication(sys.argv)
        window = AikaOptimizerPro()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        erro_msg = f"ERRO CRÍTICO AO INICIAR O PROGRAMA:\n\n{traceback.format_exc()}"
        ctypes.windll.user32.MessageBoxW(0, erro_msg, "Crash Report - Aika Optimizer", 0x10)