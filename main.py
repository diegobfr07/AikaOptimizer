# -*- coding: utf-8 -*-
import sys
import os
import subprocess
import ctypes
import threading
import string
import traceback
import time

# --- O TOQUE FINAL PARA O ÍCONE NA BARRA DE TAREFAS ---
# Isso avisa o Windows quem é o dono do app ANTES da interface carregar
try:
    meu_app_id = 'cbm.aikaoptimizer.v4'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(meu_app_id)
except Exception:
    pass
# -----------------------------------------------------

try:
    from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QLabel,
                                   QTextEdit, QWidget, QVBoxLayout, QHBoxLayout,
                                   QGridLayout, QFrame, QGraphicsDropShadowEffect,
                                   QStackedWidget, QButtonGroup, QFileDialog, QMessageBox,
                                   QSystemTrayIcon, QMenu, QCheckBox, QProgressBar,
                                   QComboBox, QLineEdit, QSizePolicy, QRadioButton,
                                   QListWidget, QListWidgetItem, QAbstractItemView, QScrollArea)
    from PySide6.QtGui import QCursor, QColor, QPainter, QPainterPath, QPen, QPixmap, QIcon, QFont
    from PySide6.QtCore import Qt, QCoreApplication, QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup, Signal, QObject, QUrl, QThread, QTimer, QRectF, Property, QSize
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtNetwork import QLocalServer, QLocalSocket

    # Importação à prova de falhas para o QAction (dependendo da versão do teu PySide6)
    try:
        from PySide6.QtGui import QAction
    except ImportError:
        from PySide6.QtWidgets import QAction

    import optimizer as opt
    import extractor_sets as exts
    import jit_integration

except Exception as e:
    ctypes.windll.user32.MessageBoxW(0, f"Erro nas importações iniciais:\n\n{traceback.format_exc()}", "Crash Report - Aika Optimizer", 0x10)
    sys.exit(1)

# --- MENSAGEM INTERNA DE ATIVAÇÃO (SINGLE INSTANCE) ---
# Enviado por uma segunda execução para solicitar que a instância
# existente seja mostrada/restaurada.
APP_ACTIVATE_MESSAGE = "__AIKA_OPTIMIZER_ACTIVATE__"


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
                try:
                    opt.log("Erro em tarefa em segundo plano", exception=True)
                except Exception:
                    import traceback
                    traceback.print_exc()

class ClickableFrame(QFrame):
    """QFrame clicável em toda a sua área (filhos transparentes para mouse)."""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class JitDropZone(QFrame):
    """Área de drop para arquivos .JIT (aceita apenas arquivos .jit válidos)."""
    arquivos_soltos = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def _extrair_jits(self, mime):
        caminhos = []
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    p = url.toLocalFile()
                    if os.path.isfile(p) and os.path.splitext(p)[1].lower() == ".jit":
                        caminhos.append(os.path.abspath(os.path.normpath(p)))
        return caminhos

    def dragEnterEvent(self, event):
        if self._extrair_jits(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._extrair_jits(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        caminhos = self._extrair_jits(event.mimeData())
        if caminhos:
            self.arquivos_soltos.emit(caminhos)
            event.acceptProposedAction()
        else:
            event.ignore()


class ExtractorWorker(QThread):
    """Worker thread para o Organizador de Sets — não congela a UI."""
    progresso = Signal(float, str)   # (porcentagem, texto_status)
    finalizado = Signal(dict)        # stats dict
    erro = Signal(str)               # mensagem de erro
    cancelado = Signal(dict)         # stats dict (cancelamento cooperativo)

    def __init__(self, origem, destino, modo_seguro, extrair_3d, extrair_tex):
        super().__init__()
        self.origem = origem
        self.destino = destino
        self.modo_seguro = modo_seguro
        self.extrair_3d = extrair_3d
        self.extrair_tex = extrair_tex
        self._cancel_event = threading.Event()

    def cancel(self):
        self._cancel_event.set()

    def _cancel_requested(self):
        return self._cancel_event.is_set()

    def run(self):
        def _progresso(pct, texto):
            self.progresso.emit(pct, texto)

        resultado = exts.organizar_e_converter_aika(
            self.origem, self.destino,
            self.modo_seguro, self.extrair_3d, self.extrair_tex,
            progress_callback=_progresso,
            cancel_callback=self._cancel_event.is_set
        )

        if resultado.get("cancelado"):
            self.cancelado.emit(resultado)
        elif "erro" in resultado:
            self.erro.emit(resultado["erro"])
        else:
            self.finalizado.emit(resultado)

class GameBoosterPanel(QFrame):
    """Painel visual de métricas do Game Session Optimizer."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BoosterPanel")
        self.setStyleSheet("""
            #BoosterPanel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(10,10,20,200), stop:1 rgba(15,15,30,200));
                border: none;
                border-radius: 14px;
                padding: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        # Linha horizontal: 4 colunas balanceadas
        row = QHBoxLayout()
        row.setSpacing(10)

        # CPU — Gauge Circular
        self.gauge_cpu = GaugeWidget("CPU")
        self.gauge_cpu.setMinimumSize(130, 130)
        row.addWidget(self.gauge_cpu, 1, Qt.AlignCenter)

        # RAM — Gauge Circular
        self.gauge_ram = GaugeWidget("RAM")
        self.gauge_ram.setMinimumSize(130, 130)
        row.addWidget(self.gauge_ram, 1, Qt.AlignCenter)

        # Processes — Card Texto
        proc_frame = self._criar_metrica_card("PROCESSES", "#FFD700")
        proc_icon = QLabel()
        proc_icon.setPixmap(QPixmap(resolver_caminho("assets/icons/processos.svg")).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        proc_icon.setAlignment(Qt.AlignCenter)
        proc_icon.setFixedHeight(32)
        proc_frame.layout().addWidget(proc_icon, 0, Qt.AlignCenter)
        self.lbl_proc_total = QLabel("--")
        self.lbl_proc_total.setStyleSheet("color: #FFD700; font-family: 'Segoe UI'; font-size: 22px; font-weight: 700;")
        self.lbl_proc_total.setAlignment(Qt.AlignCenter)
        self.lbl_proc_total.setMinimumHeight(28)
        proc_frame.layout().addWidget(self.lbl_proc_total, 0, Qt.AlignCenter)
        row.addWidget(proc_frame, 0)

        # Aika Status — Card Texto
        aika_frame = self._criar_metrica_card("AIKA.EXE", "#BF00FF")
        aika_icon = QLabel()
        aika_icon.setPixmap(QPixmap(resolver_caminho("aika.ico")).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        aika_icon.setAlignment(Qt.AlignCenter)
        aika_icon.setFixedHeight(32)
        aika_frame.layout().addWidget(aika_icon, 0, Qt.AlignCenter)
        self.lbl_aika_status = QLabel("--")
        self.lbl_aika_status.setStyleSheet("color: #BF00FF; font-family: 'Segoe UI'; font-size: 12px; font-weight: 600;")
        self.lbl_aika_status.setAlignment(Qt.AlignCenter)
        self.lbl_aika_status.setMinimumHeight(20)
        self.lbl_aika_status.setWordWrap(True)
        aika_frame.layout().addWidget(self.lbl_aika_status, 0, Qt.AlignCenter)
        row.addWidget(aika_frame, 0)

        layout.addLayout(row)
        self.setFixedHeight(195)
        self._ram_used_gb = 0.0
        self._ram_total_gb = 0.0

    def _criar_metrica_card(self, rotulo, cor):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: rgba(5,5,15,180);
                border: 1px solid transparent;
                border-radius: 10px;
            }}
        """)
        frame.setFixedWidth(110)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(3)
        lbl = QLabel(rotulo)
        lbl.setStyleSheet(f"color: {cor}; font-family: 'Segoe UI'; font-size: 10px; font-weight: 600;")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedHeight(16)
        lay.addWidget(lbl, 0, Qt.AlignTop)
        return frame

    def atualizar_metricas(self, cpu, ram_pct, ram_usada_gb, ram_total_gb, total_procs):
        self.gauge_cpu.set_value(cpu)
        self.gauge_ram.set_value(ram_pct)
        self._ram_used_gb = ram_usada_gb
        self._ram_total_gb = ram_total_gb
        self.lbl_proc_total.setText(str(total_procs))

    def boost_animation(self):
        """Dispara animação visual de startup nos dois gauges."""
        self.gauge_cpu.boost_animation()
        self.gauge_ram.boost_animation()
        
    def atualizar_status_aika(self, ativo, pid=None, prioridade=None):
        if ativo:
            texto = f"PID {pid}" if pid else "ATIVO"
            if prioridade:
                texto = prioridade
            self.lbl_aika_status.setText(texto)
            self.lbl_aika_status.setStyleSheet("color: #00FF88; font-family: 'Segoe UI'; font-size: 12px; font-weight: 600;")
        else:
            self.lbl_aika_status.setText("OFFLINE")
            self.lbl_aika_status.setStyleSheet("color: #FF4B4B; font-family: 'Segoe UI'; font-size: 12px; font-weight: 600;")

class SinaisUI(QObject):
    log_signal = Signal(str)
    metrics_signal = Signal(float, float, float, float, int, bool)  # cpu, ram_pct, ram_used_gb, ram_total_gb, total_procs, aika_ativo
    booster_visible_signal = Signal(bool)
    rede_alterada_signal = Signal()  # emitido após troca de DNS com sucesso (refresca o diagnóstico)
    automod_history_signal = Signal(object)  # lista de mods ativos (para a UI do AutoMod)
    jit_quick_signal = Signal(str, bool, str, str)  # (caminho, ok, msg, saida)

# ========================================================
# GAUGE WIDGET — Anel Circular 360° com QPainter + Animação
# ========================================================
class GaugeWidget(QWidget):
    """Medidor estilo dashboard gamer — anel circular completo com animação."""

    def __init__(self, titulo="", parent=None):
        super().__init__(parent)
        self._titulo = titulo
        self._target_value = 0.0       # valor final (0-100)
        self._display_value = 0.0      # valor animado em tela
        self.setMinimumSize(130, 130)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._anim = None

    def _get_display_value(self):
        return self._display_value

    def _set_display_value(self, v):
        self._display_value = v
        self.update()

    displayValue = Property(float, _get_display_value, _set_display_value)

    def set_value(self, value):
        """Define o valor alvo (0-100) e dispara animação suave."""
        self._target_value = max(0.0, min(100.0, value))

        if self._anim and self._anim.state() == QPropertyAnimation.Running:
            self._anim.stop()

        self._anim = QPropertyAnimation(self, b"displayValue")
        self._anim.setDuration(400)
        self._anim.setStartValue(self._display_value)
        self._anim.setEndValue(self._target_value)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()

    def boost_animation(self):
        """Animação de startup: sobe pra 100%, pausa, volta ao valor real."""
        if self._anim and self._anim.state() == QPropertyAnimation.Running:
            self._anim.stop()

        # Etapa 1: sobe rápido pra 100%
        self._anim = QPropertyAnimation(self, b"displayValue")
        self._anim.setDuration(180)
        self._anim.setStartValue(self._display_value)
        self._anim.setEndValue(100.0)
        self._anim.setEasingCurve(QEasingCurve.OutQuad)
        self._anim.start()

        # Etapa 2 + 3: após pausa de 400ms, desce pro valor real
        def _volta_ao_real():
            self._anim = QPropertyAnimation(self, b"displayValue")
            self._anim.setDuration(600)
            self._anim.setStartValue(100.0)
            self._anim.setEndValue(self._target_value)
            self._anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anim.start()

        QTimer.singleShot(600, _volta_ao_real)

    def _cor_para_pct(self, pct):
        """Verde (0–59) → amarelo/laranja (60–79) → vermelho (80–100)."""
        if pct <= 59:
            return "#00FF88"
        elif pct <= 79:
            return "#FFB800"
        else:
            return "#FF4B4B"

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        painter = QPainter()
        if not painter.begin(self):
            return

        try:
            painter.setRenderHint(QPainter.Antialiasing)

            # -- Geometria do anel circular (360°) --
            margin = 10
            lado = min(w, h) - 2 * margin
            if lado <= 20:
                return

            cx = w / 2.0
            cy = h / 2.0
            arc_x = cx - lado / 2.0
            arc_y = cy - lado / 2.0
            arc_rect = QRectF(arc_x, arc_y, lado, lado)

            pen_width = max(8, int(lado / 8))
            pen = QPen()
            pen.setWidth(pen_width)
            pen.setCapStyle(Qt.RoundCap)

            # -- Anel de fundo (360°, from 6h clockwise) --
            pen.setColor(QColor(40, 40, 55, 180))
            painter.setPen(pen)
            painter.drawArc(arc_rect, -90 * 16, -360 * 16)

            # -- Anel preenchido (cor dinâmica, sentido horário from 6h) --
            valor_tela = self._display_value
            cor_dinamica = self._cor_para_pct(valor_tela)
            pen.setColor(QColor(cor_dinamica))
            painter.setPen(pen)
            fill_span = int(360 * valor_tela / 100.0)
            if fill_span > 0:
                painter.drawArc(arc_rect, -90 * 16, -fill_span * 16)

            # -- Texto: porcentagem (centro do círculo) --
            font_size_pct = max(20, int(lado / 4.5))
            font_pct = QFont("Segoe UI", font_size_pct, QFont.Bold)
            painter.setFont(font_pct)
            painter.setPen(QColor("#FFFFFF"))
            pct_rect = QRectF(arc_x, arc_y + lado * 0.25, lado, lado * 0.4)
            painter.drawText(pct_rect, Qt.AlignHCenter | Qt.AlignVCenter,
                             f"{int(round(valor_tela))}%")

            # -- Texto: título (abaixo da porcentagem) --
            font_size_tit = max(11, int(lado / 8))
            font_tit = QFont("Segoe UI", font_size_tit, QFont.DemiBold)
            painter.setFont(font_tit)
            painter.setPen(QColor(cor_dinamica))
            tit_rect = QRectF(arc_x, arc_y + lado * 0.55, lado, lado * 0.3)
            painter.drawText(tit_rect, Qt.AlignHCenter | Qt.AlignTop, self._titulo)

        finally:
            if painter.isActive():
                painter.end()

# ========================================================
# AIKA WATCHDOG — Thread que monitora e aplica HIGH priority
# ========================================================
class AikaWatchdogThread(QThread):
    """Monitora os processos reais do Aika (AClient/Aika) a cada 5s e aplica HIGH_PRIORITY_CLASS + afinidade (sem CPU 0) automaticamente."""
    status_signal = Signal(bool, int, str)  # ativo, pid representativo, texto
    session_started_signal = Signal()  # transição: sem AIKA -> com AIKA
    session_ended_signal = Signal()    # transição: com AIKA -> sem AIKA

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self._sessao_ativa = False
        self.current_pids = {}  # pid -> create_time (para detectar PID reciclado)
        self._ultimo_status_emitido = None  # (ativo, qtd): evita reemitir o mesmo estado
        self._ciclos_sem_jogo = 0  # ciclos consecutivos sem processo (tolerância anti-falso-OFFLINE)

    def stop(self):
        self._running = False

    def _listar_pids_jogo(self):
        import psutil
        pids = {}
        try:
            for proc in psutil.process_iter(['name', 'pid', 'create_time']):
                nome = (proc.info.get('name') or "").lower()
                if nome not in opt.AIKA_GAME_EXES:
                    continue
                pid = proc.info['pid']
                try:
                    create_time = proc.info.get('create_time')
                    if create_time is None:
                        create_time = psutil.Process(pid).create_time()
                except Exception:
                    create_time = None
                pids[pid] = create_time
        except Exception:
            pass
        return pids

    def _aplicar_otimizacao(self, proc):
        import psutil
        try:
            if proc.nice() != psutil.HIGH_PRIORITY_CLASS:
                proc.nice(psutil.HIGH_PRIORITY_CLASS)
        except Exception:
            pass

    def run(self):
        import psutil
        while self._running:
            try:
                pids_atuais = self._listar_pids_jogo()

                # Aplica otimização a processos novos e reconcilia o cache
                for pid, create_time in pids_atuais.items():
                    conhecido = self.current_pids.get(pid)
                    if conhecido is None or (create_time is not None and conhecido != create_time):
                        try:
                            self._aplicar_otimizacao(psutil.Process(pid))
                        except Exception:
                            pass
                    self.current_pids[pid] = create_time

                # Remove PIDs que sumiram
                for pid in list(self.current_pids.keys()):
                    if pid not in pids_atuais:
                        del self.current_pids[pid]

                qtd = len(self.current_pids)
                sessao_ativa = qtd > 0
                if sessao_ativa and not self._sessao_ativa:
                    self.session_started_signal.emit()
                elif not sessao_ativa and self._sessao_ativa:
                    self.session_ended_signal.emit()
                self._sessao_ativa = sessao_ativa

                # Status visual: fonte única de verdade, só emite em MUDANÇA real.
                if qtd > 0:
                    # jogo ativo: reseta a tolerância imediatamente
                    self._ciclos_sem_jogo = 0
                    pid_principal = next(iter(self.current_pids))
                    texto = f"ATIVO / HIGH ({qtd})" if qtd > 1 else "ATIVO / HIGH"
                    chave = (True, qtd)
                    if chave != self._ultimo_status_emitido:
                        self._ultimo_status_emitido = chave
                        self.status_signal.emit(True, pid_principal, texto)
                else:
                    # OFFLINE só após ciclos consecutivos sem processo (anti-falso-negativo)
                    self._ciclos_sem_jogo += 1
                    if self._ciclos_sem_jogo >= 2:
                        chave = (False, 0)
                        if chave != self._ultimo_status_emitido:
                            self._ultimo_status_emitido = chave
                            self.status_signal.emit(False, 0, "OFFLINE")
            except Exception:
                pass

            # Sleep 5 segundos (checa a cada 100ms pelo stop)
            for _ in range(50):
                if not self._running:
                    break
                self.msleep(100)

class NetworkDiagWorker(QThread):
    """Executa diagnóstico de rede (adapter/DNS, teste de latência, flush) fora da UI thread."""
    resultado_signal = Signal(str, object)  # acao ('status'|'test_dns'|'flush_dns'), dados
    erro_signal = Signal(str, str)          # acao, mensagem

    def __init__(self, acao, parent=None):
        super().__init__(parent)
        self.acao = acao

    def run(self):
        try:
            if self.acao == 'status':
                self.resultado_signal.emit('status', opt.diagnosticar_rede())
            elif self.acao == 'test_dns':
                self.resultado_signal.emit('test_dns', opt.testar_dns_latencia())
            elif self.acao == 'flush_dns':
                self.resultado_signal.emit('flush_dns', opt.limpar_cache_dns())
        except Exception as e:
            self.erro_signal.emit(self.acao, str(e))


class QosWorker(QThread):
    """Aplica/remove/consulta políticas QoS do AIKA fora da UI thread."""
    resultado_signal = Signal(str, object)  # acao ('apply'|'remove'|'status'), dados
    erro_signal = Signal(str, str)

    def __init__(self, acao, parent=None):
        super().__init__(parent)
        self.acao = acao

    def run(self):
        try:
            if self.acao == 'apply':
                self.resultado_signal.emit('apply', opt.aplicar_qos_aika())
            elif self.acao == 'remove':
                self.resultado_signal.emit('remove', opt.remover_qos_aika())
            elif self.acao == 'status':
                self.resultado_signal.emit('status', opt.obter_status_qos_aika())
        except Exception as e:
            self.erro_signal.emit(self.acao, str(e))


def carregar_icone_svg(nome_arquivo, cor=None, tamanho=20):
    """Carrega um arquivo SVG como QIcon."""
    caminho = resolver_caminho(f"assets/icons/{nome_arquivo}")
    if os.path.exists(caminho):
        icon = QIcon(caminho)
        if not icon.isNull():
            return icon
    # Fallback: retorna ícone vazio
    return QIcon()

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
    def __init__(self, jit_args=None, jit_server=None):
        super().__init__()
        self.setWindowTitle("AIKA OPTIMIZER V4.0")
        self.resize(1024, 680)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        caminho_icone = resolver_caminho("icone.ico")
        self.setWindowIcon(QIcon(caminho_icone))

        self.sinais = SinaisUI()
        self.sinais.log_signal.connect(self.atualizar_log)
        self.sinais.rede_alterada_signal.connect(self._on_rede_alterada)
        self.sinais.automod_history_signal.connect(self._atualizar_historico_automod)
        self.sinais.jit_quick_signal.connect(self._on_jit_rapido_concluido)

        self.tarefa_lock = threading.Lock()
        self.executando_tarefa = False
        self.dragPos = None
        self.worker = None
        self._sets_worker = None
        self._jit_args_iniciais = jit_args or []
        self._jit_quick_queue = []
        self._jit_convertendo = False
        self._jit_arquivo_atual = None
        self._jit_server = None
        self._jit_worker = None
        self._jit_substituir = True
        self._jit_ultima_saida = ""
        self._watchdog = None
        self._force_exit = False
        self._shutdown_pending = False
        self._shutdown_finalizando = False
        self._shutdown_log_emitido = False
        self._auto_boost_pending = False
        self._suprimir_auto_boost_ate = 0.0
        self._booster_restore_pending = False
        self._booster_restore_em_andamento = False
        self._notificou_tray = False
        self._diag_worker = None
        self._diag_busy = False
        self._qos_worker = None
        self._qos_busy = False
        self._sessao_ativa = False
        self._qos_ativas = 0
        self._qos_erro = False
        self._qos_desired_enabled = opt.obter_config("network_priority", False)
        self._qos_reconcile_pending = False
        self._qos_decidir_pendente = False
        self._qos_aplicando = False

        opt.limpar_pasta_temp_audio()
        opt.migrar_startup_se_necessario()

        # ========================================================
        # TRAY ICON (BANDEJA DO SISTEMA - SEGUNDO PLANO)
        # ========================================================
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(caminho_icone))

        tray_menu = QMenu()
        
        acao_restaurar = QAction("Abrir Aika Optimizer", self)
        acao_restaurar.triggered.connect(self.showNormal)
        tray_menu.addAction(acao_restaurar)

        acao_boost = QAction("Game Boost", self)
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

            QFrame#Sidebar { background-color: rgba(7, 7, 12, 180); border: none; border-radius: 12px; }
            QPushButton.MenuButton { background-color: transparent; color: #888899; text-align: left; padding: 12px 20px; font-size: 15px; font-weight: bold; border: none; border-left: 4px solid transparent; }
            QPushButton.MenuButton:hover { color: #C691FF; background-color: rgba(191, 0, 255, 0.06); }
            QPushButton.MenuButton:checked { color: #BF00FF; border-left: 4px solid #BF00FF; background-color: rgba(191, 0, 255, 0.1); }
            QPushButton.MenuButton:checked:hover { background-color: rgba(191, 0, 255, 0.16); }
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

        self.lbl_titulo = QLabel("AIKA OPTIMIZER V4.0")
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
        btn_close.clicked.connect(self.solicitar_fechamento_janela)

        layout_controles.addWidget(btn_min)
        layout_controles.addWidget(self.btn_max)
        layout_controles.addWidget(btn_close)

        layout_titulo.addWidget(self.lbl_logo)
        layout_titulo.addWidget(self.lbl_titulo)
        layout_titulo.addStretch() 
        layout_titulo.addLayout(layout_controles)
        layout_principal.addLayout(layout_titulo)

        layout_corpo = QHBoxLayout()
        layout_corpo.setSpacing(10)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(200)
        layout_sidebar = QVBoxLayout(sidebar)
        self.grupo_menu = QButtonGroup(self)
        
        self.btn_aba_performance = self.criar_botao_menu("Performance", 0, carregar_icone_svg("performance.svg"))
        self.btn_aba_ferramentas = self.criar_botao_menu("Sistema", 1, carregar_icone_svg("sistema.svg"))
        self.btn_aba_automod     = self.criar_botao_menu("AutoMod", 2, carregar_icone_svg("processes.svg"))
        self.btn_aba_audio       = self.criar_botao_menu("Áudio", 3, carregar_icone_svg("audio.svg"))
        self.btn_aba_extrator_jit= self.criar_botao_menu("Texturas (.JIT)", 4, carregar_icone_svg("texturas.svg"))
        self.btn_aba_restore     = self.criar_botao_menu("Segurança", 5, carregar_icone_svg("protected.svg"))
        self.btn_aba_sets       = self.criar_botao_menu("Org. Sets", 6, carregar_icone_svg("sets.svg"))
        self.btn_aba_config     = self.criar_botao_menu("Configurações", 7, carregar_icone_svg("settings.svg"))
        
        layout_sidebar.addWidget(self.btn_aba_performance)
        layout_sidebar.addWidget(self.btn_aba_ferramentas)
        layout_sidebar.addWidget(self.btn_aba_automod)
        layout_sidebar.addWidget(self.btn_aba_audio)
        layout_sidebar.addWidget(self.btn_aba_extrator_jit)
        layout_sidebar.addWidget(self.btn_aba_restore)
        layout_sidebar.addWidget(self.btn_aba_sets)
        layout_sidebar.addWidget(self.btn_aba_config)
        layout_sidebar.addStretch()
        layout_corpo.addWidget(sidebar)

        self.telas = QStackedWidget()

        # --- TELA 0: PERFORMANCE ---
        page_perf = QWidget()
        layout_perf = QVBoxLayout(page_perf)
        layout_perf.setContentsMargins(10, 20, 10, 10)

        def obter_imagem(nome_base):
            caminho_png = resolver_caminho(f"assets/images/{nome_base}.png")
            caminho_jpg = resolver_caminho(f"assets/images/{nome_base}.jpg")
            return caminho_png if os.path.exists(caminho_png) else caminho_jpg

        grid_cards = QGridLayout()
        grid_cards.addWidget(AikaCardGlow(self, obter_imagem("desativar_mpo"), "Desativar\nMPO"), 0, 0)
        grid_cards.addWidget(AikaCardGlow(self, obter_imagem("isolar_cpu"), "Isolar\nCPU"), 0, 1)
        grid_cards.addWidget(AikaCardGlow(self, obter_imagem("limpar_cache"), "Turbo\nBoost"), 0, 2) 
        grid_cards.addWidget(AikaCardGlow(self, obter_imagem("turbo_boost"), "Limpar\nCache"), 0, 3)
        layout_perf.addLayout(grid_cards)

        layout_perf.addStretch(1)

        desc_perf = QLabel("<b>Otimizações e ferramentas para jogos DX9:</b><br>"
                           "• <b>Desativar MPO:</b> "
                           "Ajuste de compatibilidade para testar problemas de flicker ou "
                           "stutter em algumas combinações de Windows e driver gráfico.<br>"
                           "• <b>Isolar CPU:</b> "
                           "Ajuste experimental de afinidade que remove o Core 0 do processo "
                           "do jogo. O resultado pode variar conforme o processador.<br>"
                           "• <b>Turbo Boost:</b> "
                           "Reduz a concorrência de processos em segundo plano e prioriza o "
                           "AIKA durante a sessão de jogo.<br>"
                           "• <b>Limpar Cache:</b> "
                           "Ferramenta de manutenção para solucionar problemas de cache gráfico. "
                           "A recompilação do cache pode ocorrer na próxima execução.")
        desc_perf.setWordWrap(True)
        desc_perf.setStyleSheet("color: #A0A0B0; font-size: 13px; background-color: rgba(255,255,255,10); padding: 12px; border-radius: 8px;")
        desc_perf.setAlignment(Qt.AlignLeft)
        layout_perf.addWidget(desc_perf)
        layout_perf.addSpacing(10)
        
        # Game Session Optimizer Metrics Panel
        self.booster_panel = GameBoosterPanel()
        layout_perf.addWidget(self.booster_panel, 0, Qt.AlignCenter)
        layout_perf.addSpacing(10)

        self.btn_boost = QPushButton("INICIAR OTIMIZAÇÃO GLOBAL")
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
        estilo_sistema = """
            QFrame#SysCard, QFrame#SysDnsCard {
                background-color: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 16);
                border-radius: 12px;
            }
            QFrame#SysDnsCard:hover {
                background-color: rgba(255, 255, 255, 22);
                border: 1px solid rgba(191, 0, 255, 90);
            }
            QLabel#SysSection {
                color: #BF00FF;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton#SysDnsTitle {
                background-color: transparent;
                color: white;
                text-align: left;
                font-size: 14px;
                font-weight: bold;
                border: none;
                padding: 0px;
            }
            QPushButton#SysDnsTitle:hover {
                color: #BF00FF;
            }
            QFrame#SysDnsCard:hover QPushButton#SysDnsTitle {
                color: #BF00FF;
            }
            QPushButton#SysApply {
                background-color: rgba(77, 0, 128, 120);
                color: #E6E6F0;
                border: 1px solid rgba(191, 0, 255, 90);
                border-radius: 8px;
                padding: 7px 18px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton#SysApply:hover {
                background-color: rgba(191, 0, 255, 70);
                border: 1px solid #BF00FF;
                color: white;
            }
        """
        page_sys = QWidget()
        page_sys.setObjectName("SysPage")
        page_sys.setStyleSheet(estilo_sistema)
        layout_sys = QVBoxLayout(page_sys)
        layout_sys.setContentsMargins(14, 8, 14, 8)
        layout_sys.setSpacing(8)

        lbl_sys_t = QLabel("Configurações Avançadas do Sistema")
        lbl_sys_t.setStyleSheet("color: white; font-size: 20px; font-weight: bold; background: transparent;")
        layout_sys.addWidget(lbl_sys_t)

        lbl_sys_desc = QLabel("Ajustes de rede, CPU e compatibilidade para reduzir latência e melhorar estabilidade do Aika.")
        lbl_sys_desc.setWordWrap(True)
        lbl_sys_desc.setStyleSheet("color: #A0A0B0; font-size: 13px; background: transparent;")
        layout_sys.addWidget(lbl_sys_desc)

        # Seção DNS
        layout_sys.addWidget(self.criar_titulo_secao("SERVIDOR DNS", carregar_icone_svg("network.svg")))
        lbl_dns_desc = QLabel("Escolha o resolvedor utilizado pelo Windows durante a sessão.")
        lbl_dns_desc.setWordWrap(True)
        lbl_dns_desc.setStyleSheet("color: #8A8A9A; font-size: 12px; background: transparent;")
        layout_sys.addWidget(lbl_dns_desc)

        row_dns = QHBoxLayout()
        row_dns.setSpacing(12)
        row_dns.addWidget(self.criar_card_dns("Google DNS", "8.8.8.8 / 8.8.4.4", lambda: self.acao_dns("Google")), 1)
        row_dns.addWidget(self.criar_card_dns("Cloudflare", "1.1.1.1 / 1.0.0.1", lambda: self.acao_dns("Cloudflare")), 1)
        row_dns.addWidget(self.criar_card_dns("Restaurar Padrão", "Configuração automática do Windows", lambda: self.acao_dns("Padrao")), 1)
        layout_sys.addLayout(row_dns)

        # Seção Diagnóstico de Rede
        card_rede = QFrame()
        card_rede.setObjectName("SysCard")
        lay_rede = QVBoxLayout(card_rede)
        lay_rede.setContentsMargins(16, 12, 16, 12)
        lay_rede.setSpacing(8)

        cab_rede = QHBoxLayout()
        cab_rede.setSpacing(8)
        lbl_rede_h = QLabel("DIAGNÓSTICO DE REDE")
        lbl_rede_h.setObjectName("SysSection")
        cab_rede.addWidget(lbl_rede_h)
        cab_rede.addStretch()

        btn_atualizar = QPushButton("ATUALIZAR")
        btn_atualizar.setObjectName("SysApply")
        btn_atualizar.setCursor(QCursor(Qt.PointingHandCursor))
        btn_atualizar.clicked.connect(lambda: self._rodar_diagnostico('status'))
        btn_testar = QPushButton("TESTAR DNS")
        btn_testar.setObjectName("SysApply")
        btn_testar.setCursor(QCursor(Qt.PointingHandCursor))
        btn_testar.clicked.connect(lambda: self._rodar_diagnostico('test_dns'))
        btn_flush = QPushButton("LIMPAR CACHE DNS")
        btn_flush.setObjectName("SysApply")
        btn_flush.setCursor(QCursor(Qt.PointingHandCursor))
        btn_flush.clicked.connect(lambda: self._rodar_diagnostico('flush_dns'))

        cab_rede.addWidget(btn_atualizar)
        cab_rede.addWidget(btn_testar)
        cab_rede.addWidget(btn_flush)
        lay_rede.addLayout(cab_rede)

        lin_infos = QHBoxLayout()
        lin_infos.setSpacing(16)

        col_adapter = QVBoxLayout()
        col_adapter.setSpacing(2)
        lbl_adapter_t = QLabel("ADAPTADOR ATIVO")
        lbl_adapter_t.setStyleSheet("color: #8A8A9A; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        self.lbl_adapter_val = QLabel("Não identificado")
        self.lbl_adapter_val.setStyleSheet("color: #E0E0E0; font-size: 13px; background: transparent; border: none;")
        col_adapter.addWidget(lbl_adapter_t)
        col_adapter.addWidget(self.lbl_adapter_val)

        col_dns = QVBoxLayout()
        col_dns.setSpacing(2)
        lbl_dns_t = QLabel("DNS ATUAL")
        lbl_dns_t.setStyleSheet("color: #8A8A9A; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        self.lbl_dns_val = QLabel("—")
        self.lbl_dns_val.setStyleSheet("color: #E0E0E0; font-size: 13px; background: transparent; border: none;")
        col_dns.addWidget(lbl_dns_t)
        col_dns.addWidget(self.lbl_dns_val)

        col_teste = QVBoxLayout()
        col_teste.setSpacing(2)
        lbl_teste_t = QLabel("ÚLTIMO TESTE")
        lbl_teste_t.setStyleSheet("color: #8A8A9A; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        self.lbl_teste_val = QLabel("Ainda não executado")
        self.lbl_teste_val.setStyleSheet("color: #8A8A9A; font-size: 12px; background: transparent; border: none;")
        col_teste.addWidget(lbl_teste_t)
        col_teste.addWidget(self.lbl_teste_val)

        lin_infos.addLayout(col_adapter, 1)
        lin_infos.addLayout(col_dns, 1)
        lin_infos.addLayout(col_teste, 1)
        lay_rede.addLayout(lin_infos)

        layout_sys.addWidget(card_rede)

        # Seção Prioridade de Rede
        card_qos = QFrame()
        card_qos.setObjectName("SysCard")
        lay_qos = QVBoxLayout(card_qos)
        lay_qos.setContentsMargins(14, 10, 14, 10)
        lay_qos.setSpacing(6)

        cab_qos = QHBoxLayout()
        cab_qos.setSpacing(8)
        lbl_qos_t = QLabel("PRIORIDADE DE REDE")
        lbl_qos_t.setObjectName("SysSection")
        cab_qos.addWidget(lbl_qos_t)
        cab_qos.addStretch()
        self.chk_network_priority = QCheckBox("Priorizar tráfego do AIKA")
        check_qos = resolver_caminho("assets/icons/check_green.svg").replace("\\", "/")
        self.chk_network_priority.setStyleSheet(f"""
            QCheckBox {{
                color: #C0C0CC; font-size: 13px; spacing: 8px; background: transparent;
            }}
            QCheckBox::indicator {{ width: 18px; height: 18px; }}
            QCheckBox::indicator:unchecked {{
                border: 2px solid #4D0080; border-radius: 4px; background: rgba(10,10,20,200);
            }}
            QCheckBox::indicator:checked {{
                border: 2px solid #00FF88; border-radius: 4px; background: rgba(10,10,20,200);
                image: url({check_qos});
            }}
        """)
        self.chk_network_priority.setCursor(QCursor(Qt.PointingHandCursor))
        self.chk_network_priority.stateChanged.connect(self.acao_toggle_network_priority)
        cab_qos.addWidget(self.chk_network_priority)
        lay_qos.addLayout(cab_qos)

        lbl_qos_desc = QLabel("Prioriza o tráfego do AIKA no Windows para reduzir competição com aplicativos em segundo plano.")
        lbl_qos_desc.setWordWrap(True)
        lbl_qos_desc.setStyleSheet("color: #8A8A9A; font-size: 11px; background: transparent; border: none;")
        lay_qos.addWidget(lbl_qos_desc)

        lin_qos_status = QHBoxLayout()
        lin_qos_status.setSpacing(16)
        self.lbl_qos_jogo = QLabel("JOGO: AGUARDANDO")
        self.lbl_qos_jogo.setStyleSheet("color: #8A8A9A; font-size: 11px; background: transparent; border: none;")
        self.lbl_qos_estado = QLabel("QoS: INATIVO")
        self.lbl_qos_estado.setStyleSheet("color: #8A8A9A; font-size: 11px; background: transparent; border: none;")
        self.lbl_qos_politicas = QLabel("POLÍTICAS: 0")
        self.lbl_qos_politicas.setStyleSheet("color: #E0E0E0; font-size: 11px; background: transparent; border: none;")
        lin_qos_status.addWidget(self.lbl_qos_jogo)
        lin_qos_status.addWidget(self.lbl_qos_estado)
        lin_qos_status.addWidget(self.lbl_qos_politicas)
        lin_qos_status.addStretch()
        lay_qos.addLayout(lin_qos_status)

        layout_sys.addWidget(card_qos)

        # inicializar checkbox a partir da config (sem disparar callback)
        self.chk_network_priority.blockSignals(True)
        self.chk_network_priority.setChecked(opt.obter_config("network_priority", False))
        self.chk_network_priority.blockSignals(False)
        self._atualizar_status_qos()

        # Seção Otimizações
        layout_sys.addWidget(self.criar_titulo_secao("OTIMIZAÇÕES", carregar_icone_svg("cpu.svg")))

        grid_m = QGridLayout()
        grid_m.setHorizontalSpacing(12)
        grid_m.setVerticalSpacing(12)
        grid_m.addWidget(self.criar_card_sistema("Modo Tela Cheia (FSE)", "Desliga a Game Bar e ativa o Modo Tela Cheia Exclusivo, vital para jogos antigos.", carregar_icone_svg("performance.svg"), self.acao_gamebar), 0, 0)
        grid_m.addWidget(self.criar_card_sistema("Remover Efeitos Poluídos", "Apaga os arquivos visuais pesados com segurança (ex: WeaponEff3.bin). Elimina o lag visual.", carregar_icone_svg("protected.svg"), self.acao_weapon), 0, 1)
        grid_m.addWidget(self.criar_card_sistema("Reduzir Delay (TCP)", "Aplica TCP NoDelay na sua placa de rede, enviando pacotes de dados instantaneamente.", carregar_icone_svg("network.svg"), self.acao_tcp_nodelay), 0, 2)
        grid_m.setColumnStretch(0, 1)
        grid_m.setColumnStretch(1, 1)
        grid_m.setColumnStretch(2, 1)
        layout_sys.addLayout(grid_m)

        layout_sys.addStretch()
        self.telas.addWidget(page_sys)

        # --- TELA 2: AUTOMOD ---
        estilo_automod = """
            QFrame#AutoModWorkspace {
                background-color: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 16);
                border-radius: 12px;
            }
            QLabel#AutoModSection {
                color: #BF00FF;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton#AutoModSelectBtn {
                background-color: rgba(77, 0, 128, 120);
                color: #E6E6F0;
                border: 1px solid rgba(191, 0, 255, 90);
                border-radius: 8px;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#AutoModSelectBtn:hover {
                background-color: rgba(191, 0, 255, 70);
                border: 1px solid #BF00FF;
                color: white;
            }
            QPushButton#AutoModClearBtn {
                background-color: rgba(255, 60, 60, 40);
                color: #FFB3B3;
                border: 1px solid rgba(255, 60, 60, 90);
                border-radius: 8px;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#AutoModClearBtn:hover {
                background-color: rgba(255, 60, 60, 90);
                border: 1px solid #FF5555;
                color: white;
            }
            QTextEdit#AutoModList {
                background-color: rgba(0, 0, 0, 80);
                border: 1px solid rgba(255, 255, 255, 16);
                border-radius: 8px;
                color: #B0B0BC;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                padding: 8px;
            }
            QPushButton#AutoModInjectBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #BF00FF, stop:1 #7A1FA8);
                color: white;
                padding: 14px;
                border-radius: 12px;
                font-weight: bold;
                font-size: 16px;
                border: 1px solid rgba(191, 0, 255, 120);
            }
            QPushButton#AutoModInjectBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #D24BFF, stop:1 #8A2BBF);
                border: 1px solid #BF00FF;
            }
            QListWidget#AutoModHistory {
                background-color: rgba(0, 0, 0, 60);
                border: 1px solid rgba(255, 255, 255, 16);
                border-radius: 8px;
                color: #E0E0E0;
                font-size: 12px;
                padding: 4px;
            }
            QListWidget#AutoModHistory::item {
                padding: 6px;
                border-radius: 4px;
            }
            QListWidget#AutoModHistory::item:selected {
                background-color: rgba(191, 0, 255, 40);
                color: white;
            }
            QPushButton#AutoModRestoreBtn {
                background-color: rgba(255, 150, 0, 30);
                color: #FFC966;
                border: 1px solid rgba(255, 150, 0, 90);
                border-radius: 8px;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#AutoModRestoreBtn:hover {
                background-color: rgba(255, 150, 0, 70);
                border: 1px solid #FFA500;
                color: white;
            }
            QPushButton#AutoModRestoreBtn:disabled {
                background-color: rgba(60, 60, 70, 60);
                color: #666;
                border: 1px solid rgba(255, 255, 255, 10);
            }
        """
        page_automod = QWidget()
        page_automod.setObjectName("AutoModPage")
        page_automod.setStyleSheet(estilo_automod)
        layout_automod = QVBoxLayout(page_automod)
        layout_automod.setContentsMargins(14, 12, 14, 12)
        layout_automod.setSpacing(12)

        lbl_automod_t = QLabel("AutoMod - Injetor de Modificações Nativas")
        lbl_automod_t.setStyleSheet("color: white; font-size: 20px; font-weight: bold; background: transparent;")
        layout_automod.addWidget(lbl_automod_t)

        lbl_automod_desc = QLabel("Selecione mods e injete arquivos no Aika utilizando o indexador inteligente do projeto.")
        lbl_automod_desc.setWordWrap(True)
        lbl_automod_desc.setStyleSheet("color: #A0A0B0; font-size: 13px; background: transparent;")
        layout_automod.addWidget(lbl_automod_desc)

        lbl_automod_nota = QLabel("Hot-Swapping: texturas e áudios podem ser injetados com o jogo aberto, sem engasgos.")
        lbl_automod_nota.setWordWrap(True)
        lbl_automod_nota.setStyleSheet("color: #8A8A9A; font-size: 12px; background: transparent;")
        layout_automod.addWidget(lbl_automod_nota)

        # Workspace de arquivos
        workspace = QFrame()
        workspace.setObjectName("AutoModWorkspace")
        lay_ws = QVBoxLayout(workspace)
        lay_ws.setContentsMargins(16, 14, 16, 14)
        lay_ws.setSpacing(10)

        lbl_ws_titulo = QLabel("ARQUIVOS PARA INJEÇÃO")
        lbl_ws_titulo.setObjectName("AutoModSection")
        lay_ws.addWidget(lbl_ws_titulo)

        self.lbl_mods_selecionados = QLabel("Nenhum arquivo de modificação carregado.")
        self.lbl_mods_selecionados.setStyleSheet("color: #8A8A9A; font-size: 13px; background: transparent; border: none; padding: 0px;")
        lay_ws.addWidget(self.lbl_mods_selecionados)

        lay_botoes = QHBoxLayout()
        lay_botoes.setSpacing(10)
        btn_sel_mod = QPushButton("SELECIONAR ARQUIVOS")
        btn_sel_mod.setObjectName("AutoModSelectBtn")
        btn_sel_mod.setCursor(QCursor(Qt.PointingHandCursor))
        btn_sel_mod.setFocusPolicy(Qt.NoFocus)
        btn_sel_mod.clicked.connect(self.selecionar_arquivos_mod)
        lay_botoes.addWidget(btn_sel_mod)

        self.btn_limpar_mods = QPushButton("LIMPAR SELEÇÃO")
        self.btn_limpar_mods.setObjectName("AutoModClearBtn")
        self.btn_limpar_mods.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_limpar_mods.setFocusPolicy(Qt.NoFocus)
        self.btn_limpar_mods.clicked.connect(self.limpar_selecao_mods)
        self.btn_limpar_mods.hide()
        lay_botoes.addWidget(self.btn_limpar_mods)
        lay_botoes.addStretch()
        lay_ws.addLayout(lay_botoes)

        self.terminal_automod = QTextEdit()
        self.terminal_automod.setObjectName("AutoModList")
        self.terminal_automod.setReadOnly(True)
        self.terminal_automod.setPlaceholderText("Lista de arquivos selecionados aparecerá aqui...")
        self.terminal_automod.setFixedHeight(90)
        lay_ws.addWidget(self.terminal_automod)

        layout_automod.addWidget(workspace)

        btn_inj_mod = QPushButton("INJETAR MODS NO AIKA")
        btn_inj_mod.setObjectName("AutoModInjectBtn")
        btn_inj_mod.setCursor(QCursor(Qt.PointingHandCursor))
        btn_inj_mod.clicked.connect(self.acao_injetar_mods)
        layout_automod.addWidget(btn_inj_mod)

        # Histórico de modificações ativas
        card_hist = QFrame()
        card_hist.setObjectName("AutoModWorkspace")
        lay_hist = QVBoxLayout(card_hist)
        lay_hist.setContentsMargins(14, 10, 14, 10)
        lay_hist.setSpacing(8)

        lbl_hist_t = QLabel("MODIFICAÇÕES ATIVAS")
        lbl_hist_t.setObjectName("AutoModSection")
        lay_hist.addWidget(lbl_hist_t)

        lbl_hist_desc = QLabel("Arquivos atualmente modificados pelo AutoMod.")
        lbl_hist_desc.setWordWrap(True)
        lbl_hist_desc.setStyleSheet("color: #8A8A9A; font-size: 11px; background: transparent; border: none;")
        lay_hist.addWidget(lbl_hist_desc)

        self.lista_historico = QListWidget()
        self.lista_historico.setObjectName("AutoModHistory")
        self.lista_historico.setSelectionMode(QAbstractItemView.MultiSelection)
        self.lista_historico.setFixedHeight(140)
        self.lista_historico.itemSelectionChanged.connect(self._on_selecao_historico)
        lay_hist.addWidget(self.lista_historico)

        self.btn_restaurar_mod = QPushButton("RESTAURAR SELECIONADO")
        self.btn_restaurar_mod.setObjectName("AutoModRestoreBtn")
        self.btn_restaurar_mod.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_restaurar_mod.setFocusPolicy(Qt.NoFocus)
        self.btn_restaurar_mod.setEnabled(False)
        self.btn_restaurar_mod.clicked.connect(self._on_restaurar_mod_selecionado)
        lay_hist.addWidget(self.btn_restaurar_mod, 0, Qt.AlignLeft)

        layout_automod.addWidget(card_hist)
        self._atualizar_historico_automod()

        layout_automod.addStretch()
        self.telas.addWidget(page_automod)

        # --- TELA 3: ÁUDIO ---
        estilo_audio = """
            QFrame#AudioCard {
                background-color: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 16);
                border-radius: 12px;
            }
            QPushButton#AudioActionBtn {
                background-color: rgba(77, 0, 128, 120);
                color: #E6E6F0;
                border: 1px solid rgba(191, 0, 255, 90);
                border-radius: 8px;
                padding: 7px 14px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#AudioActionBtn:hover {
                background-color: rgba(191, 0, 255, 70);
                border: 1px solid #BF00FF;
                color: white;
            }
            QPushButton#AudioInjectBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #BF00FF, stop:1 #7A1FA8);
                color: white;
                padding: 14px;
                border-radius: 12px;
                font-weight: bold;
                font-size: 16px;
                border: 1px solid rgba(191, 0, 255, 120);
            }
            QPushButton#AudioInjectBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #D24BFF, stop:1 #8A2BBF);
                border: 1px solid #BF00FF;
            }
            QPushButton#AudioRestoreBtn {
                background-color: rgba(255, 60, 60, 40);
                color: #FFB3B3;
                border: 1px solid rgba(255, 60, 60, 90);
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#AudioRestoreBtn:hover {
                background-color: rgba(255, 60, 60, 90);
                border: 1px solid #FF5555;
                color: white;
            }
        """
        page_audio = QWidget()
        page_audio.setObjectName("AudioPage")
        page_audio.setStyleSheet(estilo_audio)
        layout_audio = QVBoxLayout(page_audio)
        layout_audio.setContentsMargins(14, 12, 14, 12)
        layout_audio.setSpacing(12)

        lbl_audio_t = QLabel("Injetor de Áudio Customizado")
        lbl_audio_t.setStyleSheet("color: white; font-size: 20px; font-weight: bold; background: transparent;")
        layout_audio.addWidget(lbl_audio_t)

        lbl_audio_desc = QLabel("Substitua um áudio do jogo mantendo o arquivo original protegido no Snapshot de Segurança.")
        lbl_audio_desc.setWordWrap(True)
        lbl_audio_desc.setStyleSheet("color: #A0A0B0; font-size: 13px; background: transparent;")
        layout_audio.addWidget(lbl_audio_desc)

        self.estilo_default_lbl = "color: #8A8A9A; font-size: 13px; background: transparent; border: none; padding: 0px;"

        # Card 01 — Áudio original
        card_orig = QFrame()
        card_orig.setObjectName("AudioCard")
        lay_orig = QVBoxLayout(card_orig)
        lay_orig.setContentsMargins(14, 12, 14, 12)
        lay_orig.setSpacing(8)

        lay_orig.addWidget(self.criar_header_secao("01  ÁUDIO ORIGINAL", carregar_icone_svg("audio.svg")))

        self.lbl_alvo = QLabel("Nenhum arquivo original selecionado.")
        self.lbl_alvo.setStyleSheet(self.estilo_default_lbl)
        lay_orig.addWidget(self.lbl_alvo)

        lay_aud_jogo = QHBoxLayout()
        lay_aud_jogo.setSpacing(10)
        btn_alvo = QPushButton("SELECIONAR")
        btn_alvo.setObjectName("AudioActionBtn")
        btn_alvo.setCursor(QCursor(Qt.PointingHandCursor))
        btn_alvo.setFocusPolicy(Qt.NoFocus)
        btn_alvo.clicked.connect(self.selecionar_audio_jogo)
        lay_aud_jogo.addWidget(btn_alvo)

        self.btn_play_jogo = QPushButton("OUVIR")
        self.btn_play_jogo.setObjectName("AudioActionBtn")
        self.btn_play_jogo.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_play_jogo.setFocusPolicy(Qt.NoFocus)
        self.btn_play_jogo.clicked.connect(self.tocar_audio_jogo)
        lay_aud_jogo.addWidget(self.btn_play_jogo)
        lay_aud_jogo.addStretch()
        lay_orig.addLayout(lay_aud_jogo)

        # Card 02 — Novo áudio
        card_novo = QFrame()
        card_novo.setObjectName("AudioCard")
        lay_novo = QVBoxLayout(card_novo)
        lay_novo.setContentsMargins(14, 12, 14, 12)
        lay_novo.setSpacing(8)

        lay_novo.addWidget(self.criar_header_secao("02  NOVO ÁUDIO", carregar_icone_svg("audio.svg")))

        self.lbl_novo_audio = QLabel("Nenhum novo áudio selecionado.")
        self.lbl_novo_audio.setStyleSheet(self.estilo_default_lbl)
        lay_novo.addWidget(self.lbl_novo_audio)

        lay_aud_btns = QHBoxLayout()
        lay_aud_btns.setSpacing(10)
        btn_novo = QPushButton("SELECIONAR")
        btn_novo.setObjectName("AudioActionBtn")
        btn_novo.setCursor(QCursor(Qt.PointingHandCursor))
        btn_novo.setFocusPolicy(Qt.NoFocus)
        btn_novo.clicked.connect(self.selecionar_arquivo_audio)
        lay_aud_btns.addWidget(btn_novo)

        self.btn_play_novo = QPushButton("OUVIR")
        self.btn_play_novo.setObjectName("AudioActionBtn")
        self.btn_play_novo.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_play_novo.setFocusPolicy(Qt.NoFocus)
        self.btn_play_novo.clicked.connect(self.tocar_previa)
        lay_aud_btns.addWidget(self.btn_play_novo)
        lay_aud_btns.addStretch()
        lay_novo.addLayout(lay_aud_btns)

        cards_audio = QHBoxLayout()
        cards_audio.setSpacing(12)
        cards_audio.addWidget(card_orig, 1)
        cards_audio.addWidget(card_novo, 1)
        layout_audio.addLayout(cards_audio)

        self.btn_conv_aud = QPushButton("INJETAR NOVO ÁUDIO")
        self.btn_conv_aud.setObjectName("AudioInjectBtn")
        self.btn_conv_aud.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_conv_aud.clicked.connect(self.acao_substituir_audio)
        layout_audio.addWidget(self.btn_conv_aud)

        btn_restaurar_1 = QPushButton("Restaurar áudio original")
        btn_restaurar_1.setObjectName("AudioRestoreBtn")
        btn_restaurar_1.setCursor(QCursor(Qt.PointingHandCursor))
        btn_restaurar_1.clicked.connect(self.acao_restaurar_audio)
        layout_audio.addWidget(btn_restaurar_1, 0, Qt.AlignLeft)

        layout_audio.addStretch()
        self.telas.addWidget(page_audio)

        # --- TELA 4: EXTRATOR JIT ---
        estilo_jit = """
            QFrame#JitWorkspace {
                background-color: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 16);
                border-radius: 12px;
            }
            QPushButton#JitActionBtn {
                background-color: rgba(77, 0, 128, 120);
                color: #E6E6F0;
                border: 1px solid rgba(191, 0, 255, 90);
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#JitActionBtn:hover {
                background-color: rgba(191, 0, 255, 70);
                border: 1px solid #BF00FF;
                color: white;
            }
            QPushButton#JitExtractBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #BF00FF, stop:1 #7A1FA8);
                color: white;
                padding: 14px;
                border-radius: 12px;
                font-weight: bold;
                font-size: 16px;
                border: 1px solid rgba(191, 0, 255, 120);
            }
            QPushButton#JitExtractBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #D24BFF, stop:1 #8A2BBF);
                border: 1px solid #BF00FF;
            }
            QFrame#JitDropZone {
                background-color: rgba(255, 255, 255, 8);
                border: 1px dashed rgba(191, 0, 255, 100);
                border-radius: 10px;
            }
        """
        page_jit = QWidget()
        page_jit.setObjectName("JitPage")
        page_jit.setStyleSheet(estilo_jit)
        layout_jit = QVBoxLayout(page_jit)
        layout_jit.setContentsMargins(14, 12, 14, 12)
        layout_jit.setSpacing(12)

        lbl_jit_t = QLabel("Extrator de Texturas")
        lbl_jit_t.setStyleSheet("color: white; font-size: 20px; font-weight: bold; background: transparent;")
        layout_jit.addWidget(lbl_jit_t)

        lbl_jit_desc = QLabel("Converta arquivos .JIT para formatos utilizáveis.")
        lbl_jit_desc.setWordWrap(True)
        lbl_jit_desc.setStyleSheet("color: #A0A0B0; font-size: 13px; background: transparent;")
        layout_jit.addWidget(lbl_jit_desc)

        lbl_jit_nota = QLabel("Se for o JT20 (8-bits com paleta), o motor converte automaticamente para TGA 32-bits.")
        lbl_jit_nota.setWordWrap(True)
        lbl_jit_nota.setStyleSheet("color: #8A8A9A; font-size: 12px; background: transparent;")
        layout_jit.addWidget(lbl_jit_nota)

        workspace_jit = QFrame()
        workspace_jit.setObjectName("JitWorkspace")
        lay_ws_jit = QVBoxLayout(workspace_jit)
        lay_ws_jit.setContentsMargins(16, 14, 16, 14)
        lay_ws_jit.setSpacing(10)

        lay_ws_jit.addWidget(self.criar_header_secao("TEXTURA / ARQUIVOS DE ORIGEM", carregar_icone_svg("texturas.svg")))

        self.lbl_jit_selecionado = QLabel("Nenhuma textura selecionada.")
        self.lbl_jit_selecionado.setStyleSheet(self.estilo_default_lbl)
        lay_ws_jit.addWidget(self.lbl_jit_selecionado)

        lay_btn_jit = QHBoxLayout()
        lay_btn_jit.setSpacing(10)
        btn_buscar_jit = QPushButton("SELECIONAR .JIT")
        btn_buscar_jit.setObjectName("JitActionBtn")
        btn_buscar_jit.setCursor(QCursor(Qt.PointingHandCursor))
        btn_buscar_jit.setFocusPolicy(Qt.NoFocus)
        btn_buscar_jit.clicked.connect(self.selecionar_arquivos_jit)
        lay_btn_jit.addWidget(btn_buscar_jit)

        btn_abrir_jit = QPushButton("ABRIR PASTA")
        btn_abrir_jit.setObjectName("JitActionBtn")
        btn_abrir_jit.setCursor(QCursor(Qt.PointingHandCursor))
        btn_abrir_jit.setFocusPolicy(Qt.NoFocus)
        btn_abrir_jit.clicked.connect(self.abrir_pasta_textura_jit)
        lay_btn_jit.addWidget(btn_abrir_jit)
        lay_btn_jit.addStretch()
        lay_ws_jit.addLayout(lay_btn_jit)

        lbl_jit_formatos = QLabel("Formatos de saída: DDS / TGA")
        lbl_jit_formatos.setStyleSheet("color: #8A8A9A; font-size: 12px; background: transparent; border: none;")
        lay_ws_jit.addWidget(lbl_jit_formatos)

        layout_jit.addWidget(workspace_jit)

        btn_extrair_jit = QPushButton("EXTRAIR TEXTURAS")
        btn_extrair_jit.setObjectName("JitExtractBtn")
        btn_extrair_jit.setCursor(QCursor(Qt.PointingHandCursor))
        btn_extrair_jit.clicked.connect(self.acao_extrair_jit)
        layout_jit.addWidget(btn_extrair_jit)

        # --- CONVERSÃO RÁPIDA (Drag & Drop + integração com o Windows) ---
        layout_jit.addWidget(self.criar_header_secao("CONVERSÃO RÁPIDA", carregar_icone_svg("texturas.svg")))

        self.drop_zone_jit = JitDropZone()
        self.drop_zone_jit.setObjectName("JitDropZone")
        self.drop_zone_jit.arquivos_soltos.connect(self.receber_jit_externo)
        lay_drop = QVBoxLayout(self.drop_zone_jit)
        lay_drop.setContentsMargins(16, 14, 16, 14)
        lay_drop.setSpacing(6)

        lbl_drop_titulo = QLabel("Arraste arquivos .JIT aqui ou abra-os diretamente pelo Explorador do Windows.")
        lbl_drop_titulo.setWordWrap(True)
        lbl_drop_titulo.setAlignment(Qt.AlignCenter)
        lbl_drop_titulo.setStyleSheet("color: #A0A0B0; font-size: 12px; background: transparent; border: none;")
        lay_drop.addWidget(lbl_drop_titulo)

        self.lbl_jit_quick_arquivo = QLabel("AGUARDANDO ARQUIVO .JIT")
        self.lbl_jit_quick_arquivo.setAlignment(Qt.AlignCenter)
        self.lbl_jit_quick_arquivo.setStyleSheet("color: #8A8A9A; font-size: 12px; background: transparent; border: none;")
        lay_drop.addWidget(self.lbl_jit_quick_arquivo)

        self.lbl_jit_quick_status = QLabel("")
        self.lbl_jit_quick_status.setAlignment(Qt.AlignCenter)
        self.lbl_jit_quick_status.setStyleSheet("color: #00D4FF; font-size: 12px; background: transparent; border: none;")
        lay_drop.addWidget(self.lbl_jit_quick_status)

        self.lbl_jit_quick_saida = QLabel("")
        self.lbl_jit_quick_saida.setAlignment(Qt.AlignCenter)
        self.lbl_jit_quick_saida.setStyleSheet("color: #4CAF50; font-size: 12px; background: transparent; border: none;")
        lay_drop.addWidget(self.lbl_jit_quick_saida)

        self.btn_jit_abrir_local = QPushButton("ABRIR LOCAL")
        self.btn_jit_abrir_local.setObjectName("JitActionBtn")
        self.btn_jit_abrir_local.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_jit_abrir_local.setVisible(False)
        self.btn_jit_abrir_local.clicked.connect(self.abrir_local_jit_rapido)
        row_drop_btn = QHBoxLayout()
        row_drop_btn.addStretch()
        row_drop_btn.addWidget(self.btn_jit_abrir_local)
        row_drop_btn.addStretch()
        lay_drop.addLayout(row_drop_btn)

        layout_jit.addWidget(self.drop_zone_jit)

        layout_jit.addStretch()
        self.telas.addWidget(page_jit)

        # --- TELA 5: RESTAURAÇÃO ---
        estilo_restore = """
            QFrame#RestoreCard {
                background-color: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 16);
                border-radius: 12px;
            }
            QPushButton#RestoreSystemBtn {
                background-color: rgba(255, 150, 0, 30);
                color: #FFC966;
                border: 1px solid rgba(255, 150, 0, 90);
                border-radius: 8px;
                padding: 10px 18px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#RestoreSystemBtn:hover {
                background-color: rgba(255, 150, 0, 70);
                border: 1px solid #FFA500;
                color: white;
            }
            QPushButton#RestoreGameBtn {
                background-color: rgba(255, 60, 60, 40);
                color: #FFB3B3;
                border: 1px solid rgba(255, 60, 60, 90);
                border-radius: 8px;
                padding: 10px 18px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#RestoreGameBtn:hover {
                background-color: rgba(255, 60, 60, 90);
                border: 1px solid #FF5555;
                color: white;
            }
        """
        page_restore = QWidget()
        page_restore.setObjectName("RestorePage")
        page_restore.setStyleSheet(estilo_restore)
        layout_restore = QVBoxLayout(page_restore)
        layout_restore.setContentsMargins(14, 12, 14, 12)
        layout_restore.setSpacing(12)

        lbl_res_t = QLabel("Central de Restauração e Segurança")
        lbl_res_t.setStyleSheet("color: white; font-size: 20px; font-weight: bold; background: transparent;")
        layout_restore.addWidget(lbl_res_t)

        lbl_res_desc = QLabel("As restaurações revertem alterações realizadas pelo AIKA Optimizer, devolvendo o sistema ou os arquivos do jogo ao estado original.")
        lbl_res_desc.setWordWrap(True)
        lbl_res_desc.setStyleSheet("color: #A0A0B0; font-size: 13px; background: transparent;")
        layout_restore.addWidget(lbl_res_desc)

        card_sys = QFrame()
        card_sys.setObjectName("RestoreCard")
        lay_card_sys = QVBoxLayout(card_sys)
        lay_card_sys.setContentsMargins(16, 14, 16, 14)
        lay_card_sys.setSpacing(8)

        lay_card_sys.addWidget(self.criar_header_secao("SISTEMA E BOOSTER", carregar_icone_svg("protected.svg")))

        lbl_sys_desc = QLabel("Reverte ajustes aplicados ao Windows e configurações do booster.")
        lbl_sys_desc.setWordWrap(True)
        lbl_sys_desc.setStyleSheet("color: #8A8A9A; font-size: 12px; background: transparent; border: none;")
        lay_card_sys.addWidget(lbl_sys_desc)

        btn_res_sys = QPushButton("RESTAURAR SISTEMA")
        btn_res_sys.setObjectName("RestoreSystemBtn")
        btn_res_sys.setCursor(QCursor(Qt.PointingHandCursor))
        btn_res_sys.setFocusPolicy(Qt.NoFocus)
        btn_res_sys.clicked.connect(self.acao_restaurar_sistema)
        lin_sys = QHBoxLayout()
        lin_sys.addWidget(btn_res_sys)
        lin_sys.addStretch()
        lay_card_sys.addLayout(lin_sys)

        card_jogo = QFrame()
        card_jogo.setObjectName("RestoreCard")
        lay_card_jogo = QVBoxLayout(card_jogo)
        lay_card_jogo.setContentsMargins(16, 14, 16, 14)
        lay_card_jogo.setSpacing(8)

        lay_card_jogo.addWidget(self.criar_header_secao("MODIFICAÇÕES DO JOGO", carregar_icone_svg("warning.svg")))

        lbl_jogo_desc = QLabel("Restaura arquivos modificados do Aika para o snapshot/estado protegido pelo sistema.")
        lbl_jogo_desc.setWordWrap(True)
        lbl_jogo_desc.setStyleSheet("color: #8A8A9A; font-size: 12px; background: transparent; border: none;")
        lay_card_jogo.addWidget(lbl_jogo_desc)

        btn_res_all = QPushButton("RESTAURAR JOGO")
        btn_res_all.setObjectName("RestoreGameBtn")
        btn_res_all.setCursor(QCursor(Qt.PointingHandCursor))
        btn_res_all.setFocusPolicy(Qt.NoFocus)
        btn_res_all.clicked.connect(self.acao_restaurar_tudo)
        lin_jogo = QHBoxLayout()
        lin_jogo.addWidget(btn_res_all)
        lin_jogo.addStretch()
        lay_card_jogo.addLayout(lin_jogo)

        layout_restore.addWidget(card_sys)
        layout_restore.addWidget(card_jogo)
        layout_restore.addStretch()
        self.telas.addWidget(page_restore)

        # --- TELA 6: ORGANIZADOR DE SETS ---
        check_sets = resolver_caminho("assets/icons/check_green.svg").replace("\\", "/")
        estilo_sets = f"""
            QLineEdit {{
                background: rgba(0, 0, 0, 60);
                color: white;
                border: 1px solid rgba(255, 255, 255, 16);
                border-radius: 8px;
                padding: 9px;
                font-size: 13px;
            }}
            QLineEdit:focus {{ border: 1px solid #BF00FF; }}
            QPushButton#SetsBrowseBtn {{
                background-color: rgba(77, 0, 128, 90);
                border: 1px solid rgba(191, 0, 255, 60);
                border-radius: 8px;
            }}
            QPushButton#SetsBrowseBtn:hover {{
                background-color: rgba(191, 0, 255, 70);
                border: 1px solid #BF00FF;
            }}
            QFrame#SetsSubCard {{
                background-color: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 16);
                border-radius: 12px;
            }}
            QCheckBox {{
                color: #C0C0CC;
                font-size: 13px;
                spacing: 8px;
                background: transparent;
            }}
            QCheckBox::indicator {{ width: 18px; height: 18px; }}
            QCheckBox::indicator:unchecked {{
                border: 2px solid #4D0080;
                border-radius: 3px;
                background: rgba(10,10,20,200);
            }}
            QCheckBox::indicator:checked {{
                border: 2px solid #00FF88;
                border-radius: 3px;
                background: rgba(10,10,20,200);
                image: url({check_sets});
            }}
            QRadioButton {{
                color: #C0C0CC;
                font-size: 13px;
                spacing: 8px;
                background: transparent;
            }}
            QRadioButton:disabled {{
                color: #6A6A7A;
            }}
            QRadioButton::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 3px;
            }}
            QRadioButton::indicator:unchecked {{
                border: 2px solid #4D0080;
                border-radius: 3px;
                background: rgba(10,10,20,200);
            }}
            QRadioButton::indicator:checked {{
                border: 2px solid #00FF88;
                border-radius: 3px;
                background: rgba(10,10,20,200);
                image: url({check_sets});
            }}
            QRadioButton::indicator:disabled {{
                border: 2px solid #3A3A46;
                border-radius: 3px;
                background: rgba(20,20,28,200);
            }}
            QRadioButton::indicator:checked:disabled {{
                border: 2px solid #2E7D5B;
                border-radius: 3px;
                background: rgba(20,20,28,200);
                image: url({check_sets});
            }}
            QProgressBar {{
                background: #1A1A2E; border: 1px solid rgba(255, 255, 255, 16); border-radius: 8px;
                height: 22px; text-align: center; color: white; font-size: 12px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #BF00FF, stop:1 #00D4FF);
                border-radius: 7px;
            }}
            QPushButton#SetsExecBtn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4D0080, stop:1 #BF00FF);
                color: white; font-weight: bold; font-size: 15px;
                padding: 14px; border-radius: 12px; border: none;
            }}
            QPushButton#SetsExecBtn:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #BF00FF, stop:1 #00D4FF);
            }}
            QPushButton#SetsExecBtn:disabled {{ background: #333; color: #666; }}
            QPushButton#SetsOpenBtn {{
                background-color: rgba(0, 212, 255, 30);
                border: 1px solid rgba(0, 212, 255, 80);
                color: #00D4FF; font-weight: bold; font-size: 12px;
                padding: 8px 14px; border-radius: 8px;
            }}
            QPushButton#SetsOpenBtn:hover {{
                background-color: rgba(0, 212, 255, 60);
                border: 1px solid #00D4FF;
            }}
            QPushButton#SetsOpenBtn:disabled {{ background: #2A2A36; color: #666; border: 1px solid #3A3A46; }}
        """
        page_sets = QWidget()
        page_sets.setObjectName("SetsPage")
        page_sets.setStyleSheet(estilo_sets)
        layout_sets = QVBoxLayout(page_sets)
        layout_sets.setSpacing(7)
        layout_sets.setContentsMargins(14, 12, 14, 12)

        lbl_sets_t = QLabel("Organizador de Sets")
        lbl_sets_t.setStyleSheet("color: white; font-size: 20px; font-weight: bold; background: transparent;")
        layout_sets.addWidget(lbl_sets_t)

        lbl_sets_d = QLabel("Organize sets, armas e seus arquivos por classe para facilitar a identificação e edição dos equipamentos do AIKA.")
        lbl_sets_d.setStyleSheet("color: #A0A0B0; font-size: 13px; background: transparent;")
        lbl_sets_d.setWordWrap(True)
        lbl_sets_d.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout_sets.addWidget(lbl_sets_d)

        lbl_sets_nota = QLabel("Opcionalmente, extraia os modelos 3D e as texturas durante a organização para visualizar cada set.")
        lbl_sets_nota.setStyleSheet("color: #8A8A9A; font-size: 12px; background: transparent;")
        lbl_sets_nota.setWordWrap(True)
        lbl_sets_nota.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout_sets.addWidget(lbl_sets_nota)

        layout_sets.addWidget(self.criar_header_secao("PASTAS", carregar_icone_svg("folder.svg")))

        # --- ORIGEM: PASTA DO AIKA ---
        lbl_origem_titulo = QLabel("PASTA DO AIKA — ORIGEM")
        lbl_origem_titulo.setStyleSheet("color: #E0E0E8; font-size: 13px; font-weight: 600; background: transparent;")
        layout_sets.addWidget(lbl_origem_titulo)

        lbl_origem_desc = QLabel("Selecione a pasta onde o AIKA está instalado.")
        lbl_origem_desc.setStyleSheet("color: #A0A0B0; font-size: 12px; background: transparent;")
        lbl_origem_desc.setWordWrap(True)
        lbl_origem_desc.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout_sets.addWidget(lbl_origem_desc)

        lbl_origem_ex = QLabel("Ex.: C:\\CBMgames\\AikaOnlineBrasil")
        lbl_origem_ex.setStyleSheet("color: #7A7A86; font-size: 11px; background: transparent;")
        layout_sets.addWidget(lbl_origem_ex)

        row_origem = QHBoxLayout()
        row_origem.setSpacing(8)
        self.le_origem_sets = QLineEdit()
        self.le_origem_sets.setPlaceholderText("Pasta de origem com os arquivos do jogo...")
        btn_browse_o = QPushButton()
        btn_browse_o.setObjectName("SetsBrowseBtn")
        btn_browse_o.setIcon(carregar_icone_svg("folder.svg"))
        btn_browse_o.setIconSize(QSize(18, 18))
        btn_browse_o.setFixedSize(38, 38)
        btn_browse_o.setCursor(QCursor(Qt.PointingHandCursor))
        btn_browse_o.setToolTip("Selecionar pasta de instalação do AIKA")
        btn_browse_o.clicked.connect(self.selecionar_origem_sets)
        row_origem.addWidget(self.le_origem_sets, 1)
        row_origem.addWidget(btn_browse_o)
        layout_sets.addLayout(row_origem)

        # --- DESTINO: PASTA DE SAÍDA ---
        lbl_destino_titulo = QLabel("PASTA DE SAÍDA — DESTINO")
        lbl_destino_titulo.setStyleSheet("color: #E0E0E8; font-size: 13px; font-weight: 600; background: transparent;")
        layout_sets.addWidget(lbl_destino_titulo)

        lbl_destino_desc = QLabel("Escolha onde os sets organizados e os arquivos extraídos serão salvos.")
        lbl_destino_desc.setStyleSheet("color: #A0A0B0; font-size: 12px; background: transparent;")
        lbl_destino_desc.setWordWrap(True)
        lbl_destino_desc.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout_sets.addWidget(lbl_destino_desc)

        row_destino = QHBoxLayout()
        row_destino.setSpacing(8)
        self.le_destino_sets = QLineEdit()
        self.le_destino_sets.setPlaceholderText("Pasta de destino para a saída organizada...")
        btn_browse_d = QPushButton()
        btn_browse_d.setObjectName("SetsBrowseBtn")
        btn_browse_d.setIcon(carregar_icone_svg("folder.svg"))
        btn_browse_d.setIconSize(QSize(18, 18))
        btn_browse_d.setFixedSize(38, 38)
        btn_browse_d.setCursor(QCursor(Qt.PointingHandCursor))
        btn_browse_d.setToolTip("Selecionar pasta onde os resultados serão salvos")
        btn_browse_d.clicked.connect(self.selecionar_destino_sets)
        row_destino.addWidget(self.le_destino_sets, 1)
        row_destino.addWidget(btn_browse_d)
        layout_sets.addLayout(row_destino)

        # Preenche origem/destino com prioridade: caminho salvo -> padrão do jogo -> vazio
        saved_origem = opt.obter_config("sets_source_path", "")
        if saved_origem and os.path.isdir(saved_origem):
            self.le_origem_sets.setText(saved_origem)
        elif os.path.isdir(opt.PASTA_JOGO_PADRAO):
            self.le_origem_sets.setText(opt.PASTA_JOGO_PADRAO)

        saved_destino = opt.obter_config("sets_output_path", "")
        if saved_destino and os.path.isdir(saved_destino):
            self.le_destino_sets.setText(saved_destino)

        # EXTRAÇÕES OPCIONAIS + PROCESSAMENTO
        sub_conteudo = QFrame()
        sub_conteudo.setObjectName("SetsSubCard")
        sub_conteudo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay_conteudo = QVBoxLayout(sub_conteudo)
        lay_conteudo.setContentsMargins(12, 10, 12, 10)
        lay_conteudo.setSpacing(5)
        lay_conteudo.addWidget(self.criar_header_secao("EXTRAÇÕES OPCIONAIS", carregar_icone_svg("sets.svg")))

        lbl_conteudo_desc = QLabel("Escolha quais arquivos auxiliares deseja gerar durante a organização.")
        lbl_conteudo_desc.setWordWrap(True)
        lbl_conteudo_desc.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        lbl_conteudo_desc.setStyleSheet("color: #8A8A9A; font-size: 11px; background: transparent; border: none;")
        lay_conteudo.addWidget(lbl_conteudo_desc)

        self.chk_sets_3d = QCheckBox("Extrair Modelo 3D")
        self.chk_sets_3d.setChecked(True)
        self.chk_sets_3d.setCursor(QCursor(Qt.PointingHandCursor))
        lay_conteudo.addWidget(self.chk_sets_3d)

        lbl_3d_sub = QLabel("Converte .MSH → .OBJ durante a organização, permitindo visualizar e identificar o set em programas 3D.")
        lbl_3d_sub.setWordWrap(True)
        lbl_3d_sub.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        lbl_3d_sub.setStyleSheet("color: #8A8A9A; font-size: 11px; background: transparent; border: none; padding-left: 26px;")
        lay_conteudo.addWidget(lbl_3d_sub)

        self.chk_sets_tex = QCheckBox("Extrair Texturas")
        self.chk_sets_tex.setChecked(True)
        self.chk_sets_tex.setCursor(QCursor(Qt.PointingHandCursor))
        lay_conteudo.addWidget(self.chk_sets_tex)

        lbl_tex_sub = QLabel("Extrai e converte .JIT → .DDS/.TGA durante a organização, permitindo visualizar as texturas do set.")
        lbl_tex_sub.setWordWrap(True)
        lbl_tex_sub.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        lbl_tex_sub.setStyleSheet("color: #8A8A9A; font-size: 11px; background: transparent; border: none; padding-left: 26px;")
        lay_conteudo.addWidget(lbl_tex_sub)

        lbl_conteudo_nota = QLabel("Estas opções são complementares. Os sets serão organizados mesmo que nenhuma extração seja selecionada.")
        lbl_conteudo_nota.setWordWrap(True)
        lbl_conteudo_nota.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        lbl_conteudo_nota.setStyleSheet("color: #6A6A7A; font-size: 11px; background: transparent; border: none;")
        lay_conteudo.addWidget(lbl_conteudo_nota)

        lay_conteudo.addStretch()

        sub_modo = QFrame()
        sub_modo.setObjectName("SetsSubCard")
        sub_modo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay_modo = QVBoxLayout(sub_modo)
        lay_modo.setContentsMargins(12, 10, 12, 10)
        lay_modo.setSpacing(5)
        lay_modo.addWidget(self.criar_header_secao("PROCESSAMENTO", carregar_icone_svg("cpu.svg")))

        lbl_modo_desc = QLabel("Escolha o ritmo de processamento dos arquivos.")
        lbl_modo_desc.setWordWrap(True)
        lbl_modo_desc.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        lbl_modo_desc.setStyleSheet("color: #8A8A9A; font-size: 11px; background: transparent; border: none;")
        lay_modo.addWidget(lbl_modo_desc)

        self.grupo_modo_sets = QButtonGroup(self)
        self.grupo_modo_sets.setExclusive(True)

        self.rb_sets_turbo = QRadioButton("Modo Turbo")
        self.rb_sets_turbo.setCursor(QCursor(Qt.PointingHandCursor))
        self.rb_sets_turbo.setChecked(True)
        self.grupo_modo_sets.addButton(self.rb_sets_turbo)
        lay_modo.addWidget(self.rb_sets_turbo)

        lbl_turbo_sub = QLabel("Processa os arquivos na velocidade máxima, sem pausa artificial entre as operações.")
        lbl_turbo_sub.setWordWrap(True)
        lbl_turbo_sub.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        lbl_turbo_sub.setStyleSheet("color: #8A8A9A; font-size: 11px; background: transparent; border: none; padding-left: 26px;")
        lay_modo.addWidget(lbl_turbo_sub)

        lbl_turbo_rec = QLabel("Indicado para SSD/NVMe e PCs modernos")
        lbl_turbo_rec.setWordWrap(True)
        lbl_turbo_rec.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        lbl_turbo_rec.setStyleSheet("color: #6FB8CC; font-size: 10px; background: transparent; border: none; padding-left: 26px;")
        lay_modo.addWidget(lbl_turbo_rec)

        lay_modo.addSpacing(6)

        self.rb_sets_seguro = QRadioButton("Modo Seguro")
        self.rb_sets_seguro.setCursor(QCursor(Qt.PointingHandCursor))
        self.grupo_modo_sets.addButton(self.rb_sets_seguro)
        lay_modo.addWidget(self.rb_sets_seguro)

        lbl_seguro_sub = QLabel("Adiciona pequenas pausas durante o processamento para reduzir a carga contínua de disco.")
        lbl_seguro_sub.setWordWrap(True)
        lbl_seguro_sub.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        lbl_seguro_sub.setStyleSheet("color: #8A8A9A; font-size: 11px; background: transparent; border: none; padding-left: 26px;")
        lay_modo.addWidget(lbl_seguro_sub)

        lbl_seguro_rec = QLabel("Indicado para HDs mais lentos")
        lbl_seguro_rec.setWordWrap(True)
        lbl_seguro_rec.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        lbl_seguro_rec.setStyleSheet("color: #6FB8CC; font-size: 10px; background: transparent; border: none; padding-left: 26px;")
        lay_modo.addWidget(lbl_seguro_rec)

        lay_modo.addStretch()

        row_opcoes = QHBoxLayout()
        row_opcoes.setSpacing(10)
        row_opcoes.addWidget(sub_conteudo, 1)
        row_opcoes.addWidget(sub_modo, 1)
        layout_sets.addLayout(row_opcoes)

        self.pbar_sets = QProgressBar()
        self.pbar_sets.setRange(0, 100)
        self.pbar_sets.setValue(0)
        self.pbar_sets.setTextVisible(True)
        layout_sets.addWidget(self.pbar_sets)

        self.lbl_status_sets = QLabel("Pronto para iniciar.")
        self.lbl_status_sets.setStyleSheet("color: #AAA; font-size: 12px; padding: 2px; background: transparent;")
        layout_sets.addWidget(self.lbl_status_sets)

        self.btn_abrir_saida_sets = QPushButton("ABRIR RESULTADOS")
        self.btn_abrir_saida_sets.setObjectName("SetsOpenBtn")
        self.btn_abrir_saida_sets.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_abrir_saida_sets.setVisible(False)
        self.btn_abrir_saida_sets.setFixedWidth(200)
        self.btn_abrir_saida_sets.clicked.connect(self.abrir_pasta_saida_sets)

        row_abrir_sets = QHBoxLayout()
        row_abrir_sets.addStretch()
        row_abrir_sets.addWidget(self.btn_abrir_saida_sets)
        row_abrir_sets.addStretch()
        layout_sets.addLayout(row_abrir_sets)

        # "ABRIR RESULTADOS" fica oculto até uma execução bem-sucedida
        self.le_destino_sets.textChanged.connect(lambda _: self._atualizar_botao_abrir_saida())
        self._atualizar_botao_abrir_saida()

        self.btn_exec_sets = QPushButton("INICIAR EXTRAÇÃO TOTAL")
        self.btn_exec_sets.setObjectName("SetsExecBtn")
        self.btn_exec_sets.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_exec_sets.clicked.connect(self._on_sets_main_button_clicked)
        layout_sets.addWidget(self.btn_exec_sets)

        layout_sets.addStretch()

        # QScrollArea: garante que TODO o conteúdo fique acessível no tamanho
        # padrão (1024x680) sem clipping. A scrollbar vertical aparece somente
        # quando o conteúdo exceder a área visível (Qt.ScrollBarAsNeeded).
        scroll_sets = QScrollArea()
        scroll_sets.setWidgetResizable(True)
        scroll_sets.setFrameShape(QFrame.NoFrame)
        scroll_sets.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_sets.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_sets.setWidget(page_sets)
        scroll_sets.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:vertical { background: rgba(0,0,0,60); width: 8px; margin: 0; }"
            "QScrollBar::handle:vertical { background: #4D0080; border-radius: 4px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )
        scroll_sets.viewport().setAutoFillBackground(False)
        self.telas.addWidget(scroll_sets)

        # --- TELA 7: CONFIGURAÇÕES ---
        check_icon_path = resolver_caminho("assets/icons/check_green.svg").replace("\\", "/")
        estilo_config = f"""
            QCheckBox {{
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
                spacing: 0px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
            }}
            QCheckBox::indicator:unchecked {{
                border: 2px solid #4D0080;
                border-radius: 4px;
                background: rgba(10,10,20,200);
            }}
            QCheckBox::indicator:checked {{
                border: 2px solid #00FF88;
                border-radius: 4px;
                background: rgba(10,10,20,200);
                image: url({check_icon_path});
            }}
        """
        page_config = QWidget()
        page_config.setObjectName("ConfigPage")
        page_config.setStyleSheet(estilo_config)
        layout_config = QVBoxLayout(page_config)
        layout_config.setContentsMargins(14, 12, 14, 12)
        layout_config.setSpacing(12)

        lbl_config_t = QLabel("Configurações")
        lbl_config_t.setStyleSheet("color: white; font-size: 20px; font-weight: bold; background: transparent;")
        layout_config.addWidget(lbl_config_t)

        lbl_config_d = QLabel("Preferências do AIKA Optimizer V4.0")
        lbl_config_d.setStyleSheet("color: #8A8A9A; font-size: 12px; background: transparent;")
        layout_config.addWidget(lbl_config_d)

        self.chk_startup = QCheckBox("")
        self.chk_startup.setCursor(QCursor(Qt.PointingHandCursor))
        self.chk_startup.stateChanged.connect(self.acao_toggle_startup)

        self.chk_start_minimized = QCheckBox("")
        self.chk_start_minimized.setCursor(QCursor(Qt.PointingHandCursor))
        self.chk_start_minimized.stateChanged.connect(self.acao_toggle_start_minimized)

        self.chk_close_to_tray = QCheckBox("")
        self.chk_close_to_tray.setCursor(QCursor(Qt.PointingHandCursor))
        self.chk_close_to_tray.stateChanged.connect(self.acao_toggle_close_to_tray)

        self.chk_auto_boost = QCheckBox("")
        self.chk_auto_boost.setCursor(QCursor(Qt.PointingHandCursor))
        self.chk_auto_boost.stateChanged.connect(self.acao_toggle_auto_boost)

        self.chk_aggressive = QCheckBox("")
        self.chk_aggressive.setCursor(QCursor(Qt.PointingHandCursor))
        self.chk_aggressive.stateChanged.connect(self.acao_toggle_aggressive)

        grupo_inicio = self.criar_grupo_config("INICIALIZAÇÃO E JANELA", [
            (carregar_icone_svg("sistema.svg"), "Inicializar com o Windows", "Inicia automaticamente com a sessão do Windows. Utiliza HKEY_CURRENT_USER — não requer privilégios de administrador.", self.chk_startup),
            (carregar_icone_svg("minimize.svg"), "Iniciar minimizado", "Quando iniciado automaticamente com o Windows, permanece apenas na bandeja do sistema.", self.chk_start_minimized),
            (carregar_icone_svg("tray.svg"), "Fechar para bandeja", "O botão X oculta a janela e mantém o Watchdog ativo. Use 'Sair' na bandeja para encerrar o aplicativo.", self.chk_close_to_tray),
        ])

        grupo_booster = self.criar_grupo_config("GAME BOOSTER", [
            (carregar_icone_svg("performance.svg"), "Auto Boost", "Executa a otimização global automaticamente uma vez quando uma nova sessão do AIKA for detectada. Se o Modo Agressivo estiver ativo, navegadores poderão ser encerrados automaticamente.", self.chk_auto_boost),
            (carregar_icone_svg("game_booster.svg"), "Modo Agressivo", "Encerra navegadores (Chrome, Edge, Firefox, Opera, Brave) e atualizadores durante a otimização. Processos protegidos permanecem intactos.", self.chk_aggressive),
        ])

        row_config = QHBoxLayout()
        row_config.setSpacing(12)
        row_config.addWidget(grupo_inicio, 1)
        row_config.addWidget(grupo_booster, 1)
        layout_config.addLayout(row_config)

        # --- INTEGRAÇÃO COM WINDOWS (.JIT) ---
        self.chk_jit_windows = QCheckBox("")
        self.chk_jit_windows.setCursor(QCursor(Qt.PointingHandCursor))
        self.chk_jit_windows.stateChanged.connect(self.acao_toggle_jit_windows)

        self.lbl_jit_assoc_status = QLabel("ASSOCIAÇÃO: INATIVA")
        self.lbl_jit_assoc_status.setStyleSheet("color: #8A8A9A; font-size: 11px; background: transparent; border: none;")

        self.btn_jit_reparar = QPushButton("REPARAR")
        self.btn_jit_reparar.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_jit_reparar.setVisible(False)
        self.btn_jit_reparar.setStyleSheet(
            "background-color: rgba(255, 150, 0, 30); color: #FFC966;"
            "border: 1px solid rgba(255, 150, 0, 90); border-radius: 8px;"
            "padding: 6px 14px; font-size: 12px; font-weight: bold;"
        )
        self.btn_jit_reparar.clicked.connect(self.acao_reparar_jit_windows)

        grupo_jit = self.criar_grupo_config("INTEGRAÇÃO COM WINDOWS", [
            (carregar_icone_svg("texturas.svg"), "Abrir arquivos .JIT com o AIKA Optimizer",
             "Permite converter arquivos .JIT diretamente pelo Explorador do Windows com duplo clique.",
             self.chk_jit_windows),
        ])
        layout_config.addWidget(grupo_jit)

        row_jit_status = QHBoxLayout()
        row_jit_status.addWidget(self.lbl_jit_assoc_status)
        row_jit_status.addWidget(self.btn_jit_reparar)
        row_jit_status.addStretch()
        layout_config.addLayout(row_jit_status)

        layout_config.addStretch()
        self.telas.addWidget(page_config)

        # Sincronizar checkboxes com estado atual
        self.sincronizar_config_checkboxes()

        # LAYOUT FINAL DIREITA E LOGS INICIAIS
        layout_direita = QVBoxLayout()
        layout_direita.addWidget(self.telas)
        self.log_box = QTextEdit()
        self.log_box.setObjectName("AikaTerminal")
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(115)

        self.log_box.setText(">> [OK] MOTOR DX9 E KERNEL BLINDADOS INICIALIZADOS...\n>> [OK] PRONTO PARA ALTA PERFORMANCE NA JOY IMPACT ENGINE.")
        layout_direita.addWidget(self.log_box)
        layout_corpo.addLayout(layout_direita)
        layout_principal.addLayout(layout_corpo)

        # SISTEMAS AUXILIARES
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.5)
        self.btn_aba_performance.setChecked(True)
        
        # Timer para atualização de métricas visuais (LEVE, sem psutil)
        self._metrics_cache = {"cpu": 0, "ram_pct": 0, "ram_used": 0, "ram_total": 0, "procs": 0, "aika": False}
        self.metrics_timer = QTimer(self)
        self.metrics_timer.timeout.connect(self._refresh_metrics_display)
        self.metrics_timer.start(2000)

        # Conectar signals do worker para o painel (cross-thread seguro)
        self.sinais.metrics_signal.connect(self._on_worker_metrics)
        self.sinais.booster_visible_signal.connect(self.booster_panel.setVisible)

        # Coleta inicial de métricas (roda uma vez no startup)
        QTimer.singleShot(1000, self._coletar_metricas_startup)

        # Inicia Aika Watchdog (monitora e aplica HIGH priority automaticamente)
        self._watchdog = AikaWatchdogThread(self)
        self._watchdog.status_signal.connect(self._on_watchdog_status)
        self._watchdog.session_started_signal.connect(self._on_sessao_iniciada)
        self._watchdog.session_ended_signal.connect(self._on_sessao_encerrada)
        self._watchdog.start()

        # Registra se o processo está elevado (uma vez, após a inicialização)
        if opt.is_admin():
            self.sinais.log_signal.emit("[INFO] Processo elevado: SIM")
        else:
            self.sinais.log_signal.emit("[INFO] Processo elevado: NÃO")

        # Reconciliação inicial do QoS (limpeza de políticas residuais)
        QTimer.singleShot(5000, self._reconciliar_qos_startup)

        # --- INTEGRAÇÃO .JIT: servidor single-instance + status + args iniciais ---
        if jit_server is not None:
            # Servidor já adquirido no __main__ — apenas conecta os sinais
            self._jit_server = jit_server
            self._jit_server.newConnection.connect(self._on_jit_conexao_nova)
        else:
            # Fallback: tenta adquirir aqui (compatibilidade com caminhos alternativos)
            self._iniciar_servidor_jit()
        self._atualizar_status_jit_windows()
        if self._jit_args_iniciais:
            QTimer.singleShot(300, lambda: self.receber_jit_externo(self._jit_args_iniciais))

    def _on_watchdog_status(self, ativo, pid, texto):
        """Recebe status do watchdog e atualiza o card AIKA.EXE."""
        try:
            self.booster_panel.atualizar_status_aika(ativo, pid, prioridade=texto)
        except Exception:
            pass

    def _on_sessao_iniciada(self):
        """Nova sessão do AIKA detectada (transição sem-AIKA -> com-AIKA)."""
        self._sessao_ativa = True
        self._qos_erro = False  # nova sessão: permite nova tentativa
        self._atualizar_status_qos()

        # QoS: reconciliar (aplica se habilitado)
        if self._qos_desired_enabled:
            self._reconciliar_qos()

        if not opt.obter_config("auto_boost", False):
            return

        # Supressão temporária: sessão já preparada pela Otimização Global
        agora = time.monotonic()
        if self._suprimir_auto_boost_ate > 0:
            if agora <= self._suprimir_auto_boost_ate:
                self._suprimir_auto_boost_ate = 0.0
                self.sinais.log_signal.emit("[INFO] Sessão já preparada pela Otimização Global. Auto Boost duplicado ignorado.")
                return
            else:
                self._suprimir_auto_boost_ate = 0.0

        if self.executando_tarefa:
            self._auto_boost_pending = True
            self.sinais.log_signal.emit("[INFO] AIKA detectado. Auto Boost aguardando a tarefa atual.")
            return
        self.sinais.log_signal.emit("[INFO] AIKA detectado. Auto Boost iniciado.")
        self.iniciar_boost_seguro()

    def _on_sessao_encerrada(self):
        """Todos os processos do AIKA fecharam: reseta o estado da sessão."""
        self._sessao_ativa = False
        self._auto_boost_pending = False
        self._qos_erro = False  # sessão encerrada: ERRO deixa de ser relevante
        self._atualizar_status_qos()
        # QoS: reconciliar (remove políticas ao encerrar a sessão)
        if self._qos_desired_enabled:
            self._reconciliar_qos()
        # Restaura o Game Booster (prioridades/serviços) em background
        self._solicitar_restauracao_booster()

    def _solicitar_restauracao_booster(self):
        """Restaura o Game Booster (desativar_game_booster) sem bloquear a UI."""
        if self._shutdown_pending or self._shutdown_finalizando:
            return  # shutdown já cuida de desativar_game_booster
        if self._booster_restore_em_andamento:
            return  # já restaurando (idempotente)
        if self.executando_tarefa:
            self._booster_restore_pending = True
            return
        self._booster_restore_pending = False
        self._booster_restore_em_andamento = True

        def tarefa_restaurar():
            try:
                opt.desativar_game_booster()
            except Exception as e:
                self.sinais.log_signal.emit(f"[ERRO] Falha ao restaurar Game Booster: {e}")
            finally:
                self._booster_restore_em_andamento = False

        self.executar_em_background(tarefa_restaurar)

    def _coletar_metricas_startup(self):
        """Coleta métricas leves uma única vez no startup para popular o dashboard."""
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            procs = len(list(psutil.process_iter()))
            aika = opt.jogo_esta_aberto()
            self._on_worker_metrics(
                cpu, mem.percent, mem.used / (1024**3),
                mem.total / (1024**3), procs, aika
            )
        except Exception:
            pass

    def _refresh_metrics_display(self):
        """Apenas renderiza dados cacheados — NUNCA chama psutil na UI thread.

        O card AIKA.EXE é atualizado EXCLUSIVAMENTE pelo AikaWatchdogThread
        (fonte única de verdade), para evitar flickering.
        """
        try:
            c = self._metrics_cache
            self.booster_panel.atualizar_metricas(
                c["cpu"], c["ram_pct"], c["ram_used"], c["ram_total"], c["procs"]
            )
        except Exception:
            pass

    def _on_worker_metrics(self, cpu, ram_pct, ram_used, ram_total, procs, aika):
        """Recebe métricas do worker thread via signal (thread-safe)."""
        self._metrics_cache = {
            "cpu": cpu, "ram_pct": ram_pct, "ram_used": ram_used,
            "ram_total": ram_total, "procs": procs, "aika": aika
        }

    # ========================================================
    # FUNÇÕES DE UI E CONTROLE (TRAY ICON)
    # ========================================================
    def minimizar_para_tray(self):
        self.hide() # Apenas esconde a tela silenciosamente

    def esconder_para_bandeja(self):
        """Oculta a janela mantendo o app ativo na bandeja (close_to_tray)."""
        self.hide()
        if not self._notificou_tray:
            self._notificou_tray = True
            try:
                self.tray_icon.showMessage("AIKA Optimizer", "AIKA Optimizer continua ativo na bandeja.", QSystemTrayIcon.Information, 3000)
            except Exception:
                pass

    def solicitar_fechamento_janela(self):
        """Chamado pelo botão X. Se close_to_tray, oculta; senão encerra de verdade."""
        if opt.obter_config("close_to_tray", False):
            self.esconder_para_bandeja()
        else:
            self.fechar_app()

    def closeEvent(self, event):
        """Alt+F4 / close() do sistema: respeita close_to_tray e _force_exit."""
        if self._force_exit:
            event.accept()
            return
        if opt.obter_config("close_to_tray", False):
            event.ignore()
            self.esconder_para_bandeja()
        else:
            self.fechar_app()
            event.ignore()

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

    def criar_botao_menu(self, texto, indice, icone_svg=None):
        btn = QPushButton(texto)
        btn.setProperty("class", "MenuButton")
        btn.setCheckable(True)
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        if icone_svg:
            btn.setIcon(icone_svg)
            btn.setIconSize(btn.iconSize())
        self.grupo_menu.addButton(btn, indice)
        btn.clicked.connect(lambda: self.telas.setCurrentIndex(indice))
        return btn

    def criar_botao_ferramenta(self, t, a):
        btn = QPushButton(t)
        btn.setProperty("class", "ToolButton")
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.clicked.connect(a)
        return btn

    def criar_titulo_secao(self, texto, icone=None):
        """Cabeçalho discreto de seção (apenas visual)."""
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        if icone is not None and not icone.isNull():
            lbl_icone = QLabel()
            lbl_icone.setPixmap(icone.pixmap(16, 16))
            lbl_icone.setFixedSize(16, 16)
            lay.addWidget(lbl_icone)
        lbl = QLabel(texto)
        lbl.setObjectName("SysSection")
        lay.addWidget(lbl)
        lay.addStretch()
        return w

    def criar_card_dns(self, titulo, subtitulo, callback):
        """Card de servidor DNS inteiramente clicável (título + subtítulo + área)."""
        card = ClickableFrame()
        card.setObjectName("SysDnsCard")
        card.setMinimumWidth(200)
        card.clicked.connect(callback)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(4)
        btn = QPushButton(titulo)
        btn.setObjectName("SysDnsTitle")
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lay.addWidget(btn)
        lbl = QLabel(subtitulo)
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lbl.setStyleSheet("color: #8A8A9A; font-size: 11px; background: transparent; border: none;")
        lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lay.addWidget(lbl)
        lay.addStretch()
        return card

    def criar_card_sistema(self, titulo, descricao, icone, callback):
        """Card de otimização: ícone + título + descrição + ação (apenas visual)."""
        card = QFrame()
        card.setObjectName("SysCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        cabecalho = QHBoxLayout()
        cabecalho.setSpacing(8)
        if icone is not None and not icone.isNull():
            lbl_icone = QLabel()
            lbl_icone.setPixmap(icone.pixmap(22, 22))
            lbl_icone.setFixedSize(22, 22)
            cabecalho.addWidget(lbl_icone)
        lbl_titulo = QLabel(titulo)
        lbl_titulo.setStyleSheet("color: white; font-size: 14px; font-weight: bold; background: transparent; border: none;")
        cabecalho.addWidget(lbl_titulo)
        cabecalho.addStretch()
        lay.addLayout(cabecalho)

        lbl_desc = QLabel(descricao)
        lbl_desc.setWordWrap(True)
        lbl_desc.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lbl_desc.setMinimumHeight(32)
        lbl_desc.setStyleSheet("color: #A0A0B0; font-size: 12px; background: transparent; border: none;")
        lay.addWidget(lbl_desc)

        btn = QPushButton("APLICAR")
        btn.setObjectName("SysApply")
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.setFocusPolicy(Qt.NoFocus)
        btn.clicked.connect(callback)
        lin_btn = QHBoxLayout()
        lin_btn.addWidget(btn)
        lin_btn.addStretch()
        lay.addLayout(lin_btn)

        lay.addStretch()
        return card

    def criar_header_secao(self, texto, icone=None):
        """Cabeçalho de seção genérico (apenas visual)."""
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        if icone is not None and not icone.isNull():
            lbl_icone = QLabel()
            lbl_icone.setPixmap(icone.pixmap(18, 18))
            lbl_icone.setFixedSize(18, 18)
            lay.addWidget(lbl_icone)
        lbl = QLabel(texto)
        lbl.setStyleSheet("color: #BF00FF; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        lay.addWidget(lbl)
        lay.addStretch()
        return w

    def criar_grupo_config(self, titulo, linhas):
        """Card de grupo de configurações: cabeçalho + N linhas (ícone + título + checkbox + descrição)."""
        card = QFrame()
        card.setStyleSheet("background-color: rgba(255, 255, 255, 10); border: 1px solid rgba(255, 255, 255, 16); border-radius: 12px;")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        lbl_titulo = QLabel(titulo)
        lbl_titulo.setStyleSheet("color: #BF00FF; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        lay.addWidget(lbl_titulo)

        for icone, tit, desc, chk in linhas:
            topo = QHBoxLayout()
            topo.setSpacing(8)
            if icone is not None and not icone.isNull():
                lbl_ic = QLabel()
                lbl_ic.setPixmap(icone.pixmap(18, 18))
                lbl_ic.setFixedSize(18, 18)
                lbl_ic.setStyleSheet("background: transparent; border: none; padding: 0px; margin: 0px;")
                topo.addWidget(lbl_ic)
            else:
                espacador = QLabel()
                espacador.setFixedSize(18, 18)
                espacador.setStyleSheet("background: transparent; border: none;")
                topo.addWidget(espacador)
            lbl_t = QLabel(tit)
            lbl_t.setStyleSheet("color: white; font-size: 13px; font-weight: bold; background: transparent; border: none;")
            topo.addWidget(lbl_t)
            topo.addStretch()
            topo.addWidget(chk)
            lay.addLayout(topo)
            if desc:
                lbl_d = QLabel(desc)
                lbl_d.setWordWrap(True)
                lbl_d.setStyleSheet("color: #8A8A9A; font-size: 11px; background: transparent; border: none; padding-left: 26px;")
                lay.addWidget(lbl_d)
        lay.addStretch()
        return card

    def atualizar_log(self, m):
        self.log_box.append(f">> {m}")
        self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())

    def _rodar_diagnostico(self, acao):
        """Inicia diagnóstico de rede em background (não bloqueia a UI)."""
        if self._shutdown_pending or self._shutdown_finalizando:
            return
        if self._diag_busy:
            return
        self._diag_busy = True
        self._diag_worker = NetworkDiagWorker(acao)
        self._diag_worker.resultado_signal.connect(self._on_diag_resultado)
        self._diag_worker.erro_signal.connect(self._on_diag_erro)
        self._diag_worker.finished.connect(self._diag_finalizado)
        self._diag_worker.start()

    def _diag_finalizado(self):
        self._diag_busy = False
        if self._diag_worker:
            self._diag_worker.deleteLater()
            self._diag_worker = None

    def _on_diag_erro(self, acao, msg):
        self.sinais.log_signal.emit(f"[ERRO] Diagnóstico de rede ({acao}): {msg}")

    def _on_diag_resultado(self, acao, dados):
        try:
            if acao == 'status':
                adapter = dados.get("adapter", "Não identificado") if isinstance(dados, dict) else "Não identificado"
                dns = dados.get("dns", []) if isinstance(dados, dict) else []
                self.lbl_adapter_val.setText(adapter if adapter else "Não identificado")
                self.lbl_dns_val.setText(", ".join(dns) if dns else "—")
            elif acao == 'test_dns':
                g = dados.get("google_ms") if isinstance(dados, dict) else None
                c = dados.get("cloudflare_ms") if isinstance(dados, dict) else None
                menor = dados.get("menor", "N/D") if isinstance(dados, dict) else "N/D"
                linhas = [
                    f"Google: {f'{g:.1f} ms' if g is not None else 'N/D'}",
                    f"Cloudflare: {f'{c:.1f} ms' if c is not None else 'N/D'}",
                    f"Menor: {menor}",
                ]
                self.lbl_teste_val.setText("  |  ".join(linhas))
            elif acao == 'flush_dns':
                if dados:
                    self.sinais.log_signal.emit("[OK] Cache DNS do Windows limpo com sucesso.")
                else:
                    self.sinais.log_signal.emit("[ERRO] Não foi possível limpar o cache DNS.")
        except Exception:
            pass

    def _on_rede_alterada(self):
        """Após troca de DNS com sucesso, atualiza o diagnóstico automaticamente."""
        self._rodar_diagnostico('status')

    # ------------------------------------------------------------
    # PRIORIDADE DE REDE (QoS)
    # ------------------------------------------------------------
    def _rodar_qos(self, acao):
        """Executa operação QoS em background (apply/remove/status)."""
        if self._shutdown_pending or self._shutdown_finalizando:
            return
        if self._qos_busy:
            self._qos_reconcile_pending = True
            return
        self._qos_busy = True
        if acao == 'apply':
            self._qos_aplicando = True
        self._qos_worker = QosWorker(acao)
        self._qos_worker.resultado_signal.connect(self._on_qos_resultado)
        self._qos_worker.erro_signal.connect(self._on_qos_erro)
        self._qos_worker.finished.connect(self._qos_finalizado)
        self._qos_worker.start()

    def _qos_finalizado(self):
        self._qos_busy = False
        if self._qos_worker:
            self._qos_worker.deleteLater()
            self._qos_worker = None
        if self._qos_decidir_pendente:
            self._qos_decidir_pendente = False
            self._qos_reconcile_pending = False
            self._decidir_acao_qos()
        elif self._qos_reconcile_pending:
            self._qos_reconcile_pending = False
            self._reconciliar_qos()

    def _on_qos_erro(self, acao, msg):
        self._qos_erro = True
        if acao == 'apply':
            self._qos_aplicando = False
        verbo = "aplicar" if acao == 'apply' else "remover"
        self.sinais.log_signal.emit(f"[ERRO] Não foi possível {verbo} a prioridade de rede: {msg}")
        self._atualizar_status_qos()

    def _on_qos_resultado(self, acao, dados):
        try:
            self._qos_ativas = int(dados.get("ativas", 0)) if isinstance(dados, dict) else 0
            if acao == 'apply':
                self._qos_aplicando = False
                if dados.get("ok"):
                    self._qos_erro = False
                    if self._qos_desired_enabled:
                        n = self._qos_ativas
                        pal = "política aplicada" if n == 1 else "políticas aplicadas"
                        self.sinais.log_signal.emit(f"[OK] QoS do AIKA ativado: {n} {pal}.")
                else:
                    self._qos_erro = True
                    if dados.get("requires_admin"):
                        self.sinais.log_signal.emit("[ERRO] A prioridade de rede requer execução como administrador.")
                    else:
                        self.sinais.log_signal.emit(f"[ERRO] Não foi possível aplicar a prioridade de rede: {dados.get('mensagem', '')}")
            elif acao == 'remove':
                if dados.get("ok"):
                    self._qos_erro = False
                    self.sinais.log_signal.emit("[OK] QoS do AIKA removido.")
                else:
                    self._qos_erro = True
                    self.sinais.log_signal.emit(f"[ERRO] Não foi possível remover a prioridade de rede: {dados.get('mensagem', '')}")
            elif acao == 'status':
                # estado real consultado; decide a ação no fim do worker
                self._qos_decidir_pendente = True
        except Exception:
            pass
        self._atualizar_status_qos()

    def _atualizar_status_qos(self):
        """Atualiza os três indicadores de status da seção Prioridade de Rede."""
        try:
            jogo = "ATIVO" if self._sessao_ativa else "AGUARDANDO"
            cor_jogo = "#00FF88" if self._sessao_ativa else "#8A8A9A"
            self.lbl_qos_jogo.setText(f"JOGO: {jogo}")
            self.lbl_qos_jogo.setStyleSheet(f"color: {cor_jogo}; font-size: 11px; background: transparent; border: none;")

            if not self._qos_desired_enabled:
                estado, cor = "INATIVO", "#8A8A9A"
            elif not self._sessao_ativa:
                estado, cor = "AGUARDANDO", "#FFA500"
            elif self._qos_erro:
                estado, cor = "ERRO", "#FF4444"
            elif self._qos_aplicando:
                estado, cor = "APLICANDO", "#00BFFF"
            elif self._qos_ativas > 0:
                estado, cor = "ATIVO", "#00FF88"
            else:
                # ON + jogo ativo + 0 políticas: prestes a aplicar (nunca AGUARDANDO)
                estado, cor = "APLICANDO", "#00BFFF"
            self.lbl_qos_estado.setText(f"QoS: {estado}")
            self.lbl_qos_estado.setStyleSheet(f"color: {cor}; font-size: 11px; background: transparent; border: none;")

            self.lbl_qos_politicas.setText(f"POLÍTICAS: {self._qos_ativas}")
            self.lbl_qos_politicas.setStyleSheet("color: #E0E0E0; font-size: 11px; background: transparent; border: none;")
        except Exception:
            pass

    def acao_toggle_network_priority(self, state):
        """Ativa/desativa a prioridade de rede (QoS) do AIKA."""
        ativar = (state == Qt.Checked.value)
        opt.definir_config("network_priority", ativar)
        self._qos_desired_enabled = ativar
        self._qos_erro = False  # nova intenção: permite nova tentativa
        if ativar:
            if self._sessao_ativa:
                self.sinais.log_signal.emit("[INFO] Prioridade de rede ativada.")
            else:
                self.sinais.log_signal.emit("[INFO] Prioridade de rede ativada. Aguardando o AIKA.")
        else:
            self.sinais.log_signal.emit("[INFO] Prioridade de rede desativada.")
        self._atualizar_status_qos()
        self._reconciliar_qos()

    def _reconciliar_qos(self):
        """Inicia a reconciliação: consulta o estado real e então decide a ação."""
        if self._qos_busy:
            self._qos_reconcile_pending = True
            return
        self._qos_reconcile_pending = False
        self._rodar_qos('status')

    def _decidir_acao_qos(self):
        """Decide apply/remove/nada com base no estado desejado + sessão + estado real."""
        if not self._qos_desired_enabled:
            if self._qos_ativas > 0:
                self._rodar_qos('remove')
            else:
                self._atualizar_status_qos()
        elif not self._sessao_ativa:
            if self._qos_ativas > 0:
                self._rodar_qos('remove')
            else:
                self._atualizar_status_qos()
        else:
            # desejado ON + sessão ativa
            if self._qos_erro:
                self._atualizar_status_qos()  # não retenta automaticamente
            elif self._qos_ativas == 0:
                self._rodar_qos('apply')
            else:
                self._atualizar_status_qos()

    def _reconciliar_qos_startup(self):
        """Reconcilia o estado QoS no início (limpeza de políticas residuais)."""
        self._reconciliar_qos()

    def limpar_execucao(self):
        with self.tarefa_lock:
            self.executando_tarefa = False
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
        # PRIMEIRO: restauração pendente do Game Booster
        if self._booster_restore_pending:
            self._booster_restore_pending = False
            self._solicitar_restauracao_booster()
            return
        # DEPOIS: Auto Boost pendente de uma nova sessão
        if self._auto_boost_pending:
            self._auto_boost_pending = False
            if opt.obter_config("auto_boost", False) and opt.jogo_esta_aberto():
                self.sinais.log_signal.emit("[INFO] Executando Auto Boost pendente.")
                self.iniciar_boost_seguro()

    def executar_em_background(self, f):
        if self._shutdown_pending or self._shutdown_finalizando:
            return
        with self.tarefa_lock:
            if self.executando_tarefa:
                self.sinais.log_signal.emit("[INFO] Uma tarefa já está em andamento. Aguarde...")
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
        jogo_estava_aberto_no_inicio = opt.jogo_esta_aberto()
        # Animação visual nos gauges (sobe pra 100%, pausa, volta ao real)
        self.booster_panel.boost_animation()

        def tarefa_transacao():
            self.sinais.booster_visible_signal.emit(True)
            self.sinais.log_signal.emit("[OK] Iniciando Otimização Global DX9...")
            
            # Iniciar timer de métricas no worker (evita psutil na UI thread)
            worker_metrics_active = [True]
            def emit_worker_metrics():
                if not worker_metrics_active[0]:
                    return
                try:
                    import psutil
                    cpu = psutil.cpu_percent(interval=0.1)
                    mem = psutil.virtual_memory()
                    procs = len(list(psutil.process_iter()))
                    aika = opt.jogo_esta_aberto()
                    self.sinais.metrics_signal.emit(
                        cpu, mem.percent, mem.used / (1024**3),
                        mem.total / (1024**3), procs, aika
                    )
                except Exception:
                    pass
            
            # Emitir métricas iniciais
            emit_worker_metrics()
            
            transacao = opt.TransacaoSistema()
            try:
                transacao.executar(opt.salvar_snapshot_sistema)
                transacao.executar(opt.modo_desempenho_maximo, rollback=opt.restaurar_snapshot_sistema)
                transacao.executar(opt.prioridade_total)
                
                self.sinais.log_signal.emit("[OK] Ativando Game Session Optimizer V4.0...")
                resultado = opt.game_session_optimizer(dry_run=False)
                emit_worker_metrics()  # Métricas pós-otimização
                if resultado.get("status") == "error":
                    self.sinais.log_signal.emit(f"[ERRO] Erro: {resultado.get('message', 'Falha desconhecida')}")
                    transacao.rollback_total()
                    raise Exception(resultado.get('message', 'Falha desconhecida'))
                else:
                    antes = resultado.get("metricas_antes", {})
                    depois = resultado.get("metricas_depois", {})
                    delta_cpu = round(antes.get('cpu_percent', 0) - depois.get('cpu_percent', 0), 1)
                    delta_ram = round(antes.get('ram_percent', 0) - depois.get('ram_percent', 0), 1)
                    
                    self.sinais.log_signal.emit(
                        f"[OK] GAME BOOST ATIVO: "
                        f"{resultado.get('processos_encerrados', 0)} processos encerrados | "
                        f"{resultado.get('mem_associada_mb', 0):.0f} MB associados | "
                        f"CPU antes: {antes.get('cpu_percent', '?')}% | "
                        f"CPU depois: {depois.get('cpu_percent', '?')}% | "
                        f"RAM antes: {antes.get('ram_percent', '?')}% | "
                        f"RAM depois: {depois.get('ram_percent', '?')}%"
                    )
                    self.sinais.log_signal.emit(
                        f"[OK] Aika HIGH_PRIORITY: {resultado.get('aika_priority_applied', 0)} processos | "
                        f"Serviços: {resultado.get('servicos_parados', 0)} parados"
                    )

                self.sinais.log_signal.emit("[OK] OTIMIZAÇÃO COMPLETA FINALIZADA COM SUCESSO!")
                emit_worker_metrics()
                worker_metrics_active[0] = False
                if not opt.jogo_esta_aberto():
                    if not jogo_estava_aberto_no_inicio:
                        self._suprimir_auto_boost_ate = time.monotonic() + 120
                    self.sinais.log_signal.emit("[OK] Iniciando o jogo agora...")
                    opt.iniciar_jogo()
            except Exception as e:
                self.sinais.log_signal.emit(f"[ERRO] ERRO CRÍTICO: {e}")
                self.sinais.log_signal.emit("[INFO] Rollback automático executado quando disponível. Ajustes de Registro podem permanecer; use a aba Segurança para restauração completa.")
                worker_metrics_active[0] = False

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
            self.btn_play_novo.setText("Ouvir Novo")
        else:
            self.player.setSource(QUrl.fromLocalFile(self.arquivo_audio_selecionado))
            self.player.play()
            self.btn_play_novo.setText("Parar Novo")

    def selecionar_arquivos_mod(self):
        f, _ = QFileDialog.getOpenFileNames(self, "Mods", "", "Tudo (*.*)")
        if f:
            self.arquivos_mod_selecionados = f
            n = len(f)
            texto = "1 arquivo pronto para injeção" if n == 1 else f"{n} arquivos prontos para injeção"
            self.lbl_mods_selecionados.setText(texto)
            self.lbl_mods_selecionados.setStyleSheet("color: #00FF88; font-size: 13px; background: transparent; border: none; padding: 0px;")
            self.btn_limpar_mods.show()
            self.terminal_automod.clear()
            for caminho in f: self.terminal_automod.append(f"• {caminho.split('/')[-1]}")

    def limpar_selecao_mods(self):
        self.arquivos_mod_selecionados = []
        self.lbl_mods_selecionados.setText("Nenhum arquivo de modificação carregado.")
        self.lbl_mods_selecionados.setStyleSheet("color: #8A8A9A; font-size: 13px; background: transparent; border: none; padding: 0px;")
        self.terminal_automod.clear()
        self.btn_limpar_mods.hide()

    def _atualizar_historico_automod(self, itens=None):
        """Renderiza a lista de modificações ativas (nome por padrão; caminho em tooltip)."""
        try:
            if itens is None:
                itens = opt.listar_mods_ativos()
            self.lista_historico.clear()
            if not itens:
                item_vazio = QListWidgetItem("Nenhuma modificação ativa.")
                item_vazio.setFlags(Qt.NoItemFlags)
                item_vazio.setForeground(QColor(138, 138, 154))
                self.lista_historico.addItem(item_vazio)
            else:
                # contagem de basenames para desambiguar homônimos
                nomes = [it.get("target_name") or it.get("target_relpath") or "?" for it in itens]
                contagem = {}
                for n in nomes:
                    contagem[n] = contagem.get(n, 0) + 1

                for it in itens:
                    nome = it.get("target_name") or it.get("target_relpath") or "?"
                    rel = it.get("target_relpath") or ""
                    texto = nome
                    if contagem.get(nome, 0) > 1:
                        partes = rel.replace("\\", "/").split("/")
                        if len(partes) >= 2 and partes[-2]:
                            texto = f"{nome} — {partes[-2]}"
                    item = QListWidgetItem(texto)
                    item.setData(Qt.UserRole, it.get("chave"))
                    item.setToolTip(rel)
                    self.lista_historico.addItem(item)
            self.btn_restaurar_mod.setEnabled(False)
            self.btn_restaurar_mod.setText("RESTAURAR SELECIONADOS")
        except Exception:
            pass

    def _on_selecao_historico(self):
        n = len(self.lista_historico.selectedItems())
        if n == 0:
            self.btn_restaurar_mod.setEnabled(False)
            self.btn_restaurar_mod.setText("RESTAURAR SELECIONADOS")
        elif n == 1:
            self.btn_restaurar_mod.setEnabled(True)
            self.btn_restaurar_mod.setText("RESTAURAR SELECIONADO")
        else:
            self.btn_restaurar_mod.setEnabled(True)
            self.btn_restaurar_mod.setText(f"RESTAURAR SELECIONADOS ({n})")

    def _on_restaurar_mod_selecionado(self):
        itens = self.lista_historico.selectedItems()
        chaves = [it.data(Qt.UserRole) for it in itens if it.data(Qt.UserRole)]
        if not chaves:
            return
        n = len(chaves)

        msgbox = QMessageBox(self)
        msgbox.setWindowTitle("Restaurar modificações")
        msgbox.setIcon(QMessageBox.Warning)
        if n == 1:
            nome = itens[0].text()
            msgbox.setText(f"Restaurar \"{nome}\" para o arquivo original?")
            msgbox.setInformativeText("Somente esta modificação será desfeita. Os demais mods permanecerão ativos.")
        else:
            msgbox.setText(f"Restaurar {n} modificações selecionadas?")
            msgbox.setInformativeText("Somente os itens selecionados serão restaurados. As demais modificações permanecerão ativas.")
        btn_restaurar = msgbox.addButton("RESTAURAR", QMessageBox.AcceptRole)
        btn_cancelar = msgbox.addButton("CANCELAR", QMessageBox.RejectRole)
        msgbox.setDefaultButton(btn_cancelar)
        msgbox.exec()
        if msgbox.clickedButton() != btn_restaurar:
            return

        def tarefa():
            res = opt.restaurar_mods_selecionados(chaves)
            restaurados = res.get("restaurados", [])
            falhas = res.get("falhas", [])
            if not falhas:
                if len(restaurados) == 1:
                    self.sinais.log_signal.emit(f"[OK] {restaurados[0]} restaurado para o original.")
                else:
                    self.sinais.log_signal.emit(f"[OK] {len(restaurados)} modificações restauradas para o original.")
            else:
                self.sinais.log_signal.emit(f"[INFO] {len(restaurados)} modificações restauradas | {len(falhas)} falhou.")
                for nome, motivo in falhas:
                    self.sinais.log_signal.emit(f"[ERRO] {nome}: {motivo}")
            self.sinais.automod_history_signal.emit(opt.listar_mods_ativos())
        self.executar_em_background(tarefa)

    def acao_injetar_mods(self):
        mods = getattr(self, 'arquivos_mod_selecionados', None)
        if not mods: return
        def tarefa():
            r = opt.injetar_mods(mods)
            if r >= 0:
                self.sinais.log_signal.emit(f"[OK] {r} mods injetados. Histórico atualizado.")
            else:
                self.sinais.log_signal.emit("[ERRO] ERRO: Falha ao injetar mods ou índice não foi gerado.")
            self.sinais.automod_history_signal.emit(opt.listar_mods_ativos())
        self.executar_em_background(tarefa)

    def selecionar_arquivos_jit(self):
        pasta_base = r"C:\CBMgames\AikaOnlineBrasil" if os.path.exists(r"C:\CBMgames\AikaOnlineBrasil") else ""
        f, _ = QFileDialog.getOpenFileNames(self, "Selecionar Texturas .JIT", pasta_base, "Aika Texture (*.jit)")
        if f:
            self.arquivos_jit_selecionados = f
            self.lbl_jit_selecionado.setText(f"{len(f)} textura(s) selecionada(s).")
            self.lbl_jit_selecionado.setStyleSheet(self.ESTILO_NEON_CARREGADO)

    def abrir_pasta_textura_jit(self):
        if hasattr(self, 'arquivos_jit_selecionados') and self.arquivos_jit_selecionados:
            try: os.startfile(os.path.dirname(self.arquivos_jit_selecionados[0]))
            except: pass

    def acao_extrair_jit(self):
        jits = getattr(self, 'arquivos_jit_selecionados', None)
        if not jits: return
        def tarefa():
            self.sinais.log_signal.emit(f"[INFO] Extraindo {len(jits)} textura(s)...")
            sucesso_count = 0
            for jit in jits:
                ok, msg = opt.extrair_textura_jit(jit)
                if ok: sucesso_count += 1
                self.sinais.log_signal.emit(f"{'[OK]' if ok else '[ERRO]'} {os.path.basename(jit)}: {msg}")
            self.sinais.log_signal.emit(f"[OK] LOTE CONCLUÍDO: {sucesso_count}/{len(jits)} extraídos!")
        self.executar_em_background(tarefa)

    # ========================================================
    # JIT QUICK CONVERT — pipeline único (manual / drag-drop / Windows / IPC)
    # ========================================================
    def receber_jit_externo(self, caminhos):
        """Recebe arquivos .JIT de fonte externa (drag-drop, Windows, IPC)."""
        self.trazer_para_frente_jit()
        self.processar_jit_rapido(caminhos)

    def trazer_para_frente_jit(self):
        """Traz a janela para frente e abre a aba Texturas (.JIT)."""
        try:
            if self.isMinimized():
                self.showNormal()
            else:
                self.show()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass
        # Aba Texturas (.JIT) — índice 4 no QStackedWidget
        self.telas.setCurrentIndex(4)
        if hasattr(self, 'btn_aba_extrator_jit'):
            self.btn_aba_extrator_jit.setChecked(True)

    def _jit_saida_existe(self, caminho):
        base = os.path.splitext(caminho)[0]
        return os.path.exists(base + ".dds") or os.path.exists(base + ".tga")

    def processar_jit_rapido(self, caminhos):
        """Pipeline único: valida, deduplica, trata overwrite e enfileira."""
        validos = []
        for c in caminhos:
            c = os.path.abspath(os.path.normpath(c))
            if os.path.isfile(c) and os.path.splitext(c)[1].lower() == ".jit":
                if not validos or validos[-1] != c:
                    validos.append(c)
        if not validos:
            return

        existentes = [c for c in validos if self._jit_saida_existe(c)]
        self._jit_substituir = True
        if existentes:
            box = QMessageBox(self)
            box.setWindowTitle("Arquivo de saída já existe")
            box.setText(f"{len(existentes)} arquivo(s) já possuem saída (.dds/.tga). Deseja substituir?")
            btn_sub = box.addButton("SUBSTITUIR", QMessageBox.AcceptRole)
            box.addButton("CANCELAR", QMessageBox.RejectRole)
            box.exec()
            self._jit_substituir = (box.clickedButton() == btn_sub)
        if not self._jit_substituir:
            self.sinais.log_signal.emit("[INFO] Conversão cancelada (saídas existentes preservadas).")
            return

        self._jit_quick_queue.extend(validos)
        self.sinais.log_signal.emit(f"[INFO] {len(validos)} arquivo(s) JIT adicionado(s) à fila.")
        self._processar_proximo_jit()

    def _processar_proximo_jit(self):
        if self._shutdown_pending or self._shutdown_finalizando:
            return
        if self._jit_convertendo or not self._jit_quick_queue:
            return
        caminho = self._jit_quick_queue.pop(0)
        self._jit_convertendo = True
        self._jit_arquivo_atual = caminho

        self.lbl_jit_quick_arquivo.setText(os.path.basename(caminho))
        self.lbl_jit_quick_status.setText("CONVERTENDO...")
        self.lbl_jit_quick_status.setStyleSheet("color: #00D4FF; font-size: 12px; background: transparent; border: none;")
        self.lbl_jit_quick_saida.setText("")
        self.btn_jit_abrir_local.setVisible(False)
        self.sinais.log_signal.emit(f"[INFO] Convertendo {os.path.basename(caminho)}...")

        def tarefa():
            ok, msg = opt.extrair_textura_jit(caminho)
            saida = ""
            if ok:
                base = os.path.splitext(caminho)[0]
                if os.path.exists(base + ".dds"):
                    saida = base + ".dds"
                elif os.path.exists(base + ".tga"):
                    saida = base + ".tga"
            self.sinais.jit_quick_signal.emit(caminho, ok, msg, saida)

        self._jit_worker = TarefaWorker(tarefa)
        self._jit_worker.finished.connect(self._jit_worker.deleteLater)
        self._jit_worker.start()

    def _on_jit_rapido_concluido(self, caminho, ok, msg, saida):
        self._jit_convertendo = False
        self._jit_ultima_saida = saida
        nome = os.path.basename(caminho)
        if ok:
            self.lbl_jit_quick_status.setText("CONCLUÍDO")
            self.lbl_jit_quick_status.setStyleSheet("color: #4CAF50; font-size: 12px; background: transparent; border: none;")
            self.lbl_jit_quick_saida.setText(os.path.basename(saida) if saida else msg)
            self.btn_jit_abrir_local.setVisible(bool(saida))
            self.sinais.log_signal.emit(f"[OK] {nome} convertido para {os.path.basename(saida) if saida else msg}.")
        else:
            self.lbl_jit_quick_status.setText("ERRO")
            self.lbl_jit_quick_status.setStyleSheet("color: #FF4444; font-size: 12px; background: transparent; border: none;")
            self.lbl_jit_quick_saida.setText("")
            self.btn_jit_abrir_local.setVisible(False)
            self.sinais.log_signal.emit(f"[ERRO] Falha ao converter {nome}: {msg}")
        self._processar_proximo_jit()

    def abrir_local_jit_rapido(self):
        saida = getattr(self, '_jit_ultima_saida', '')
        if saida and os.path.exists(saida):
            try:
                subprocess.Popen(["explorer.exe", "/select,", os.path.normpath(saida)])
            except Exception:
                try:
                    os.startfile(os.path.dirname(saida))
                except Exception:
                    pass

    # ========================================================
    # INTEGRAÇÃO COM WINDOWS (.JIT) — registro/desregistro/status
    # ========================================================
    def acao_toggle_jit_windows(self, state):
        ativar = (state == Qt.Checked.value)
        try:
            if ativar:
                jit_integration.registrar_integracao_windows()
                if jit_integration.obter_status_associacao_jit() in ("ATIVA", "DISPONÍVEL"):
                    opt.definir_config("jit_windows_integration", True)
                    self.sinais.log_signal.emit("[OK] Integração .JIT com o Windows ATIVADA.")
                else:
                    self.sinais.log_signal.emit("[ERRO] Não foi possível validar a associação .JIT.")
            else:
                jit_integration.desregistrar_integracao_windows()
                opt.definir_config("jit_windows_integration", False)
                self.sinais.log_signal.emit("[OK] Integração .JIT com o Windows DESATIVADA.")
        except Exception as e:
            self.sinais.log_signal.emit(f"[ERRO] Falha na integração .JIT: {e}")
        self._atualizar_status_jit_windows()

    def acao_reparar_jit_windows(self):
        try:
            jit_integration.registrar_integracao_windows()
            self.sinais.log_signal.emit("[OK] Associação .JIT reparada.")
        except Exception as e:
            self.sinais.log_signal.emit(f"[ERRO] Falha ao reparar associação .JIT: {e}")
        self._atualizar_status_jit_windows()

    def _atualizar_status_jit_windows(self):
        status = jit_integration.obter_status_associacao_jit()
        if status == "ATIVA":
            self.lbl_jit_assoc_status.setText("ASSOCIAÇÃO: ATIVA")
            self.lbl_jit_assoc_status.setStyleSheet("color: #4CAF50; font-size: 11px; background: transparent; border: none;")
            self.btn_jit_reparar.setVisible(False)
        elif status == "DISPONÍVEL":
            self.lbl_jit_assoc_status.setText("ASSOCIAÇÃO: DISPONÍVEL")
            self.lbl_jit_assoc_status.setStyleSheet("color: #FFC966; font-size: 11px; background: transparent; border: none;")
            self.btn_jit_reparar.setVisible(False)
        elif status == "REQUER REPARO":
            self.lbl_jit_assoc_status.setText("ASSOCIAÇÃO: REQUER REPARO")
            self.lbl_jit_assoc_status.setStyleSheet("color: #FFC966; font-size: 11px; background: transparent; border: none;")
            self.btn_jit_reparar.setVisible(True)
        else:
            self.lbl_jit_assoc_status.setText("ASSOCIAÇÃO: INATIVA")
            self.lbl_jit_assoc_status.setStyleSheet("color: #8A8A9A; font-size: 11px; background: transparent; border: none;")
            self.btn_jit_reparar.setVisible(False)

    # ========================================================
    # SINGLE-INSTANCE (QLocalServer / QLocalSocket)
    # ========================================================
    def _iniciar_servidor_jit(self):
        """Cria o QLocalServer para single-instance e integração JIT.

        NÃO remove o servidor cegamente. Primeiro tenta listen().
        Se falhar, verifica se existe uma instância real respondendo.
        Somente remove o endpoint se confirmar que está stale (crash antigo).
        """
        try:
            self._jit_server = QLocalServer()
            self._jit_server.newConnection.connect(self._on_jit_conexao_nova)
            # Tentativa 1: listen direto (sem removeServer cego)
            if self._jit_server.listen(jit_integration.SERVER_NAME):
                return True
            # Falhou — pode ser instância viva ou endpoint stale.
            # Verifica se existe uma instância real respondendo.
            sock = QLocalSocket()
            sock.connectToServer(jit_integration.SERVER_NAME)
            if sock.waitForConnected(500):
                # Existe um processo respondendo → NÃO remover o servidor
                sock.disconnectFromServer()
                self._jit_server = None
                return False
            # Ninguém respondeu → endpoint stale de crash antigo
            QLocalServer.removeServer(jit_integration.SERVER_NAME)
            if self._jit_server.listen(jit_integration.SERVER_NAME):
                return True
            self._jit_server = None
            return False
        except Exception:
            self._jit_server = None
            return False

    def _on_jit_conexao_nova(self):
        if not self._jit_server:
            return
        while self._jit_server.hasPendingConnections():
            sock = self._jit_server.nextPendingConnection()
            if sock:
                sock.readyRead.connect(lambda s=sock: self._on_jit_dados_recebidos(s))

    def _on_jit_dados_recebidos(self, sock):
        try:
            data = bytes(sock.readAll())
            sock.disconnectFromServer()
            texto = data.decode("utf-8", errors="ignore").strip()

            # Mensagem interna de ativação (segunda execução normal)
            if texto == APP_ACTIVATE_MESSAGE:
                if self._shutdown_pending or self._shutdown_finalizando:
                    return
                self.showNormal()
                self.show()
                self.raise_()
                self.activateWindow()
                return

            # Mensagem interna de refresh do histórico (injeção via Explorer)
            if texto == jit_integration.MENSAGEM_REFRESH_HISTORICO:
                self.sinais.automod_history_signal.emit(opt.listar_mods_ativos())
                return

            caminhos = jit_integration.decodificar_mensagem(data)
            if caminhos:
                self.sinais.log_signal.emit(f"[INFO] Arquivo JIT recebido do Windows: {os.path.basename(caminhos[0])}")
                self.receber_jit_externo(caminhos)
        except Exception:
            pass

    def acao_substituir_audio(self):
        alvo = getattr(self, 'arquivo_alvo_jogo', None)
        novo = getattr(self, 'arquivo_audio_selecionado', None)
        if not alvo or not novo: return
        def tarefa():
            s, m = opt.substituir_audio_customizado(novo, alvo)
            self.sinais.log_signal.emit("[OK] Sucesso! Áudio injetado." if s else f"[ERRO] ERRO: {m}")
        self.executar_em_background(tarefa)

    def acao_restaurar_audio(self):
        alvo = getattr(self, 'arquivo_alvo_jogo', None)
        if not alvo: return
        def tarefa():
            s, m = opt.restaurar_audio_original(alvo)
            self.sinais.log_signal.emit(f"[OK] {m}" if s else f"[ERRO] {m}")
        self.executar_em_background(tarefa)

    def acao_restaurar_tudo(self):
        def tarefa():
            self.sinais.log_signal.emit("[INFO] INICIANDO RESTAURAÇÃO EM LOTES (Poupando HDD)...")
            s, m = opt.restaurar_tudo_jogo()
            self.sinais.log_signal.emit(f"[OK] {m}" if s else f"[ERRO] {m}")
            if s:
                opt.limpar_historico_automod()
                self.sinais.automod_history_signal.emit([])
        self.executar_em_background(tarefa)

    def acao_restaurar_sistema(self):
        def tarefa():
            self.sinais.log_signal.emit("[INFO] INICIANDO ROLLBACK DO SISTEMA...")
            opt.desativar_game_booster() # Desliga o booster se estiver ativo
            s, m = opt.restaurar_registro_sistema()
            self.sinais.log_signal.emit(f"[OK] {m}" if s else f"[ERRO] {m}")
        self.executar_em_background(tarefa)

    def acao_dns(self, p):
        def tarefa():
            if opt.alterar_dns(p):
                self.sinais.log_signal.emit(f"[OK] DNS {p} aplicado.")
                self.sinais.rede_alterada_signal.emit()
        self.executar_em_background(tarefa)

    def acao_gamebar(self):
        def tarefa():
            if opt.desativar_game_bar(): self.sinais.log_signal.emit("[OK] Game Bar desativada e Fullscreen Exclusivo forçado.")
        self.executar_em_background(tarefa)

    def acao_weapon(self):
        def tarefa():
            status = opt.remover_efeitos_pesados_aika()
            if status == 1: 
                self.sinais.log_signal.emit("[OK] Mega-pack de Efeitos removido (Arquivos limpos com segurança)!")
            elif status == 2: 
                self.sinais.log_signal.emit("[INFO] Os Efeitos já estão anulados (Arquivos já foram removidos).")
            elif status == 0:
                self.sinais.log_signal.emit("[INFO] Arquivos não encontrados (Ou já foram removidos).")
            else:
                self.sinais.log_signal.emit("[ERRO] Erro ao tentar processar os arquivos de efeitos.")
        self.executar_em_background(tarefa)

    def acao_tcp_nodelay(self):
        def tarefa():
            try:
                if opt.otimizar_tcp_nodelay(): self.sinais.log_signal.emit("[OK] Rotas TCP otimizadas com sucesso!")
            except Exception as e: pass
        self.executar_em_background(tarefa)

    def acao_toggle_startup(self, state):
        """Ativa/desativa inicialização com o Windows."""
        ativar = (state == Qt.Checked.value)
        try:
            sucesso = opt.configurar_iniciar_com_windows(ativar)
            if sucesso:
                if ativar:
                    self.atualizar_log("[OK] Inicialização com o Windows ATIVADA.")
                else:
                    self.atualizar_log("[OK] Inicialização com o Windows DESATIVADA.")
            else:
                self.atualizar_log("[ERRO] Falha ao modificar o registro. Execute como administrador?")
                # Reverter checkbox
                self.chk_startup.blockSignals(True)
                self.chk_startup.setChecked(not ativar)
                self.chk_startup.blockSignals(False)
        except Exception as e:
            self.atualizar_log(f"[ERRO] {str(e)}")

    def acao_toggle_aggressive(self, state):
        """Ativa/desativa Modo Agressivo."""
        ativar = (state == Qt.Checked.value)
        if ativar and self.chk_auto_boost.isChecked():
            resp = QMessageBox.question(
                self, "Confirmar Modo Agressivo",
                "O Auto Boost está ativo. Com o Modo Agressivo habilitado, navegadores podem ser encerrados automaticamente quando o AIKA for detectado.\n\nDeseja continuar?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if resp != QMessageBox.Yes:
                self.chk_aggressive.blockSignals(True)
                self.chk_aggressive.setChecked(False)
                self.chk_aggressive.blockSignals(False)
                return
        try:
            opt.definir_config("aggressive_mode", ativar)
            if ativar:
                self.atualizar_log("[INFO] Modo Agressivo ATIVADO. Navegadores serão encerrados durante a otimização.")
            else:
                self.atualizar_log("[OK] Modo Agressivo DESATIVADO. Comportamento padrão restaurado.")
        except Exception as e:
            self.atualizar_log(f"[ERRO] {str(e)}")

    def acao_toggle_start_minimized(self, state):
        """Ativa/desativa início minimizado (somente em inicialização automática)."""
        ativar = (state == Qt.Checked.value)
        opt.definir_config("start_minimized", ativar)
        if ativar:
            self.atualizar_log("[OK] Início minimizado ATIVADO. Em inicialização automática, o aplicativo permanecerá na bandeja.")
        else:
            self.atualizar_log("[OK] Início minimizado DESATIVADO.")

    def acao_toggle_close_to_tray(self, state):
        """Ativa/desativa fechar para a bandeja."""
        ativar = (state == Qt.Checked.value)
        opt.definir_config("close_to_tray", ativar)
        if ativar:
            self.atualizar_log("[OK] Fechar para a bandeja ATIVADO. O botão X ocultará a janela.")
        else:
            self.atualizar_log("[OK] Fechar para a bandeja DESATIVADO.")

    def acao_toggle_auto_boost(self, state):
        """Ativa/desativa Auto Boost (otimização automática ao detectar nova sessão do AIKA)."""
        ativar = (state == Qt.Checked.value)
        if ativar and self.chk_aggressive.isChecked():
            resp = QMessageBox.question(
                self, "Confirmar Auto Boost",
                "O Modo Agressivo está ativo. Com Auto Boost habilitado, navegadores podem ser encerrados automaticamente quando o AIKA for detectado.\n\nDeseja continuar?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if resp != QMessageBox.Yes:
                self.chk_auto_boost.blockSignals(True)
                self.chk_auto_boost.setChecked(False)
                self.chk_auto_boost.blockSignals(False)
                return
        opt.definir_config("auto_boost", ativar)
        if ativar:
            self.atualizar_log("[OK] Auto Boost ATIVADO. A otimização global será executada uma vez por sessão do AIKA.")
        else:
            self.atualizar_log("[OK] Auto Boost DESATIVADO.")

    def sincronizar_config_checkboxes(self):
        """Sincroniza os checkboxes da aba Configurações com o estado atual."""
        try:
            # Inicializar com Windows
            startup_checked = opt.verificar_inicializacao_windows()
            self.chk_startup.blockSignals(True)
            self.chk_startup.setChecked(startup_checked)
            self.chk_startup.blockSignals(False)

            # Iniciar minimizado
            start_minimized = opt.obter_config("start_minimized", False)
            self.chk_start_minimized.blockSignals(True)
            self.chk_start_minimized.setChecked(start_minimized)
            self.chk_start_minimized.blockSignals(False)

            # Fechar para bandeja
            close_to_tray = opt.obter_config("close_to_tray", False)
            self.chk_close_to_tray.blockSignals(True)
            self.chk_close_to_tray.setChecked(close_to_tray)
            self.chk_close_to_tray.blockSignals(False)

            # Auto Boost
            auto_boost = opt.obter_config("auto_boost", False)
            self.chk_auto_boost.blockSignals(True)
            self.chk_auto_boost.setChecked(auto_boost)
            self.chk_auto_boost.blockSignals(False)

            # Modo Agressivo
            aggressive = opt.is_modo_agressivo()
            self.chk_aggressive.blockSignals(True)
            self.chk_aggressive.setChecked(aggressive)
            self.chk_aggressive.blockSignals(False)

            # Integração .JIT com Windows
            jit_windows = opt.obter_config("jit_windows_integration", False)
            self.chk_jit_windows.blockSignals(True)
            self.chk_jit_windows.setChecked(jit_windows)
            self.chk_jit_windows.blockSignals(False)
        except Exception:
            pass

        # ========================================================
    # ORGANIZADOR DE SETS — EXTRATOR
    # ========================================================
    def selecionar_origem_sets(self):
        """Abre o seletor de pasta para a ORIGEM (arquivos do jogo) e persiste."""
        pasta = QFileDialog.getExistingDirectory(self, "Selecionar Pasta de Origem",
                                                 self.le_origem_sets.text().strip() or opt.PASTA_JOGO_PADRAO)
        if pasta:
            self.le_origem_sets.setText(pasta)
            opt.definir_config("sets_source_path", pasta)

    def selecionar_destino_sets(self):
        """Abre o seletor de pasta para o DESTINO (output organizado) e persiste."""
        pasta = QFileDialog.getExistingDirectory(self, "Selecionar Pasta de Destino",
                                                 self.le_destino_sets.text().strip())
        if pasta:
            self.le_destino_sets.setText(pasta)
            opt.definir_config("sets_output_path", pasta)

    def abrir_pasta_saida_sets(self):
        """Abre a raiz de saída no Explorador de Arquivos (ação separada; NÃO usa QFileDialog)."""
        caminho = self.le_destino_sets.text().strip()
        if not caminho:
            self.atualizar_log("[ERRO] Pasta de saída não definida.")
            return
        caminho = os.path.abspath(os.path.normpath(caminho))
        if not os.path.isdir(caminho):
            self.atualizar_log("[ERRO] Pasta de saída não encontrada.")
            return
        self.atualizar_log(f"[INFO] Abrindo resultado no Explorador: {caminho}")
        try:
            subprocess.Popen(["explorer.exe", caminho])
            self.atualizar_log("[OK] Pasta de saída aberta no Explorador de Arquivos.")
        except Exception as e:
            self.atualizar_log(f"[ERRO] Não foi possível abrir a pasta de saída: {e}")

    def _atualizar_botao_abrir_saida(self):
        """Habilita 'ABRIR RESULTADOS' apenas quando há um destino válido."""
        destino = self.le_destino_sets.text().strip()
        self.btn_abrir_saida_sets.setEnabled(bool(destino) and os.path.isdir(destino))

    def _on_sets_main_button_clicked(self):
        """Botão principal do Sets: inicia ou cancela conforme estado."""
        if self._sets_worker is not None and self._sets_worker.isRunning():
            # Cancelamento cooperativo
            self._sets_worker.cancel()
            self.btn_exec_sets.setText("CANCELANDO...")
            self.btn_exec_sets.setEnabled(False)
            self.lbl_status_sets.setText("Cancelamento solicitado. Finalizando o arquivo atual...")
            self.lbl_status_sets.setStyleSheet("color: #FFA500; font-size: 12px; padding: 4px;")
        else:
            self.executar_extracao_sets()


    def executar_extracao_sets(self):
        if self._shutdown_pending or self._shutdown_finalizando:
            return
        origem = self.le_origem_sets.text().strip()
        destino = self.le_destino_sets.text().strip()

        if not origem or not os.path.exists(origem):
            QMessageBox.warning(self, "Caminho Inválido",
                                "Selecione uma pasta de origem válida!")
            return

        if not destino:
            QMessageBox.warning(self, "Caminho Inválido",
                                "Selecione uma pasta de destino!")
            return

        modo_seguro = self.rb_sets_seguro.isChecked()
        extrair_3d = self.chk_sets_3d.isChecked()
        extrair_tex = self.chk_sets_tex.isChecked()

        # Configura controles durante a execução — botão vira CANCELAR (habilitado)
        self.btn_exec_sets.setText("CANCELAR")
        self.btn_exec_sets.setEnabled(True)
        self.btn_abrir_saida_sets.setVisible(False)
        self.le_origem_sets.setEnabled(False)
        self.le_destino_sets.setEnabled(False)
        self.chk_sets_3d.setEnabled(False)
        self.chk_sets_tex.setEnabled(False)
        self.rb_sets_turbo.setEnabled(False)
        self.rb_sets_seguro.setEnabled(False)
        self.pbar_sets.setValue(0)
        self.lbl_status_sets.setText("Iniciando extração...")
        self.lbl_status_sets.setStyleSheet("color: #BF00FF; font-size: 12px; padding: 4px;")

        self._sets_worker = ExtractorWorker(origem, destino, modo_seguro,
                                             extrair_3d, extrair_tex)
        self._sets_worker.progresso.connect(self._on_sets_progress)
        self._sets_worker.finalizado.connect(self._on_sets_finalizado)
        self._sets_worker.erro.connect(self._on_sets_erro)
        self._sets_worker.cancelado.connect(self._on_sets_cancelado)
        self._sets_worker.finished.connect(self._on_sets_worker_finished)
        self._sets_worker.finished.connect(self._sets_worker.deleteLater)
        self._sets_worker.start()

    def _on_sets_progress(self, pct, texto):
        self.pbar_sets.setValue(int(pct * 100))
        cor = exts.calcular_cor_progresso(pct)
        self.pbar_sets.setStyleSheet(f"""
            QProgressBar {{
                background: #1A1A2E; border: 1px solid #4D0080; border-radius: 8px;
                height: 22px; text-align: center; color: white; font-size: 12px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {cor}, stop:1 #00D4FF);
                border-radius: 7px;
            }}
        """)
        self.lbl_status_sets.setText(texto)

    def _on_sets_finalizado(self, stats):
        self.pbar_sets.setValue(100)
        self.pbar_sets.setStyleSheet("""
            QProgressBar {
                background: #1A1A2E; border: 1px solid #4D0080; border-radius: 8px;
                height: 22px; text-align: center; color: white; font-size: 12px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4CAF50, stop:1 #00FF88);
                border-radius: 7px;
            }
        """)
        self.lbl_status_sets.setText("CONCLUÍDO 100%")
        self.lbl_status_sets.setStyleSheet("color: #4CAF50; font-size: 12px; padding: 4px;")

        self.btn_abrir_saida_sets.setVisible(True)
        self.btn_abrir_saida_sets.setEnabled(True)
        self.btn_exec_sets.setText("EXECUTAR NOVAMENTE")

        relatorio = (
            f"Processo Concluído!\n\n"
            f"Arquivos Organizados: {stats.get('copiados', 0)}\n"
            f"Modelos 3D Gerados (.obj): {stats.get('msh_convertidos', 0)}\n"
            f"Texturas Extraídas (.dds/.tga): {stats.get('jit_extraidos', 0)}"
        )
        QMessageBox.information(self, "Extração Concluída", relatorio)

        self._restaurar_ui_sets()

    def _on_sets_erro(self, msg):
        self.pbar_sets.setValue(0)
        self.lbl_status_sets.setText(f"ERRO: {msg}")
        self.lbl_status_sets.setStyleSheet("color: #FF4444; font-size: 12px; padding: 4px;")
        self.btn_abrir_saida_sets.setVisible(False)
        self.btn_exec_sets.setText("TENTAR NOVAMENTE")
        QMessageBox.critical(self, "Erro na Extração",
                             f"Ocorreu um erro durante o processo:\n\n{msg}")
        self._restaurar_ui_sets()

    def _on_sets_cancelado(self, stats):
        if self._shutdown_pending or self._shutdown_finalizando:
            self.sinais.log_signal.emit("[INFO] Organizador de Sets cancelado com segurança.")
            return
        self.sinais.log_signal.emit("[INFO] Organização de Sets cancelada pelo usuário.")
        self.lbl_status_sets.setText("CANCELADO")
        self.lbl_status_sets.setStyleSheet("color: #FFA500; font-size: 12px; padding: 4px;")
        self.btn_abrir_saida_sets.setVisible(False)
        self.btn_exec_sets.setText("EXECUTAR NOVAMENTE")
        self._restaurar_ui_sets()

    def _on_sets_worker_finished(self):
        self._sets_worker = None
        if self._shutdown_pending and not self._shutdown_finalizando:
            QTimer.singleShot(0, self._tentar_finalizar_shutdown)

    def _restaurar_ui_sets(self):
        self.btn_exec_sets.setEnabled(True)
        self.le_origem_sets.setEnabled(True)
        self.le_destino_sets.setEnabled(True)
        self.chk_sets_3d.setEnabled(True)
        self.chk_sets_tex.setEnabled(True)
        self.rb_sets_turbo.setEnabled(True)
        self.rb_sets_seguro.setEnabled(True)

    def fechar_app(self):
        self._force_exit = True
        if self._shutdown_pending or self._shutdown_finalizando:
            return
        self._shutdown_pending = True
        # Solicita parada cooperativa (sem matar threads)
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
        if self._sets_worker and self._sets_worker.isRunning():
            try:
                self._sets_worker.cancel()
            except RuntimeError:
                pass
        if self._watchdog and self._watchdog.isRunning():
            self._watchdog.stop()
        self._tentar_finalizar_shutdown()

    def _tentar_finalizar_shutdown(self):
        if self._shutdown_finalizando:
            return
        workers = (self.worker, self._sets_worker, self._jit_worker,
                   self._diag_worker, self._qos_worker, self._watchdog)
        for w in workers:
            if w is None:
                continue
            try:
                if w.isRunning():
                    if not self._shutdown_log_emitido:
                        self._shutdown_log_emitido = True
                        self.sinais.log_signal.emit("[INFO] Aguardando tarefa em andamento finalizar para encerrar com segurança.")
                    QTimer.singleShot(100, self._tentar_finalizar_shutdown)
                    return
            except RuntimeError:
                # QThread já destruído (deleteLater) — ignora
                continue
        self._finalizar_shutdown_seguro()

    def _finalizar_shutdown_seguro(self):
        if self._shutdown_finalizando:
            return
        self._shutdown_finalizando = True
        try:
            self.tray_icon.hide()
        except Exception:
            pass
        opt.desativar_game_booster() # Segurança para não deixar serviços do Windows parados
        opt.limpar_pasta_temp_audio()
        opt.remover_qos_aika()  # Remove políticas QoS próprias no encerramento real
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

def _adquirir_single_instance():
    """Adquire o QLocalServer ANTES da criação da MainWindow.

    Esta é a garantia definitiva de single-instance.
    Deve ser chamada após QApplication e antes de AikaOptimizerPro.

    Returns:
        (server, acquired): server é o QLocalServer já em listen(),
        ou None. acquired é True se conseguiu, False se já existe
        uma instância real.
    """
    try:
        server = QLocalServer()
        # Tentativa 1: listen direto (sem removeServer cego)
        if server.listen(jit_integration.SERVER_NAME):
            return server, True
        # Falhou — verifica se há instância real respondendo
        sock = QLocalSocket()
        sock.connectToServer(jit_integration.SERVER_NAME)
        if sock.waitForConnected(500):
            # Existe um processo respondendo → NÃO remover
            sock.disconnectFromServer()
            return None, False
        # Ninguém respondeu → endpoint stale de crash antigo
        QLocalServer.removeServer(jit_integration.SERVER_NAME)
        if server.listen(jit_integration.SERVER_NAME):
            return server, True
        return None, False
    except Exception:
        return None, False


def _existe_instancia():
    """Verifica se já existe uma instância respondendo no SERVER_NAME.

    Conecta e desconecta sem enviar payload — não causa efeitos colaterais
    na instância existente. Retorna True se conectou com sucesso.
    """
    sock = QLocalSocket()
    sock.connectToServer(jit_integration.SERVER_NAME)
    if sock.waitForConnected(500):
        sock.disconnectFromServer()
        return True
    return False


def _encaminhar_para_instancia_existente(payload):
    """Envia um payload binário para uma instância existente via QLocalSocket.

    Retorna True se conseguiu conectar e enviar; False caso contrário.
    Timeout total ~1000 ms — não bloqueia por vários segundos.
    """
    sock = QLocalSocket()
    sock.connectToServer(jit_integration.SERVER_NAME)
    if not sock.waitForConnected(800):
        return False
    try:
        sock.write(payload)
        sock.flush()
        sock.waitForBytesWritten(500)
        sock.disconnectFromServer()
        return True
    except Exception:
        return False


def _encaminhar_jit_para_instancia_existente(caminhos):
    """Wrapper que encaminha caminhos .JIT para uma instância existente."""
    return _encaminhar_para_instancia_existente(
        jit_integration.codificar_mensagem(caminhos)
    )


def _elevar_processo(argv):
    """Reexecuta o processo atual como administrador, preservando os argumentos."""
    frozen = getattr(sys, 'frozen', False)
    executavel = os.path.abspath(sys.executable)
    if frozen:
        diretorio_atual = os.path.dirname(executavel)
        parametros = ""
        for a in argv[1:]:
            parametros += f' "{a}"'
    else:
        caminho_script = os.path.abspath(__file__)
        diretorio_atual = os.path.dirname(caminho_script)
        parametros = f'"{caminho_script}"'
        for a in argv[1:]:
            parametros += f' "{a}"'
    ctypes.windll.shell32.ShellExecuteW(None, "runas", executavel, parametros, diretorio_atual, 1)


if __name__ == "__main__":
    try:
        # ----- MODO SILENCIOSO (--jit-silent): duplo clique .JIT -----
        # Detectado ANTES de autoelevacao / GUI / QApplication / Watchdog / trapa.
        if "--jit-silent" in sys.argv:
            _ok = jit_integration.converter_silencioso(sys.argv, opt.extrair_textura_jit)
            sys.exit(0 if _ok else 1)

        # ----- MODO INJEÇÃO (--jit-inject): contexto Explorer -----
        # Detectado ANTES de GUI / QApplication / Watchdog / tray.
        if "--jit-inject" in sys.argv:
            if not opt.is_admin():
                _elevar_processo(sys.argv)
                sys.exit()
            _ok = jit_integration.injetar_silencioso(sys.argv, opt.injetar_mods)
            sys.exit(0 if _ok else 1)

        # ----- MODO INJEÇÃO DDS (--dds-inject): contexto Explorer -----
        # Detectado ANTES de GUI / QApplication / Watchdog / tray.
        if "--dds-inject" in sys.argv:
            if not opt.is_admin():
                _elevar_processo(sys.argv)
                sys.exit()
            _ok = jit_integration.injetar_dds_silencioso(sys.argv, opt.injetar_mods)
            sys.exit(0 if _ok else 1)

        startup_flag = '--startup' in sys.argv
        jit_args = jit_integration.obter_caminhos_jit_dos_argumentos(sys.argv)

        if not opt.is_admin():
            # --- VERIFICAÇÃO PRÉ-ELEVAÇÃO (evita UAC duplicado) ---
            # Tenta conectar a uma instância existente antes de pedir elevação.
            try:
                _app_tmp = QCoreApplication(sys.argv)
                if jit_args:
                    # Duplo clique .JIT → encaminha para instância existente
                    if _encaminhar_jit_para_instancia_existente(jit_args):
                        sys.exit(0)
                elif startup_flag:
                    # --startup com instância já ativa → encerra silenciosamente
                    if _existe_instancia():
                        sys.exit(0)
                else:
                    # Abertura normal → pede para instância existente se mostrar
                    if _encaminhar_para_instancia_existente(APP_ACTIVATE_MESSAGE.encode("utf-8")):
                        sys.exit(0)
            except Exception:
                pass

            _elevar_processo(sys.argv)
            sys.exit()

        # ---------- PROCESSO ELEVADO ----------

        app = QApplication(sys.argv)

        # --- AQUISIÇÃO DEFINITIVA DO SINGLE INSTANCE (ANTES da MainWindow) ---
        # Esta é a garantia final: a MainWindow só é criada após conquistar o server.
        server, acquired = _adquirir_single_instance()
        if not acquired:
            # Perdeu a disputa: encaminha e encerra sem jamais criar janela/Watchdog/tray
            if jit_args:
                try:
                    _encaminhar_jit_para_instancia_existente(jit_args)
                except Exception:
                    pass
            elif not startup_flag:
                # Abertura normal: envia ACTIVATE para instância existente
                try:
                    _encaminhar_para_instancia_existente(APP_ACTIVATE_MESSAGE.encode("utf-8"))
                except Exception:
                    pass
            # --startup ou falha ao enviar: encerra silenciosamente
            sys.exit(0)

        window = AikaOptimizerPro(jit_args, jit_server=server)
        if startup_flag and opt.obter_config("start_minimized", False):
            # Início automático com start_minimized: permanece apenas na bandeja (sem flicker)
            pass
        else:
            window.show()
        sys.exit(app.exec())
    except Exception as e:
        erro_msg = f"ERRO CRÍTICO AO INICIAR O PROGRAMA:\n\n{traceback.format_exc()}"
        ctypes.windll.user32.MessageBoxW(0, erro_msg, "Crash Report - Aika Optimizer", 0x10)
