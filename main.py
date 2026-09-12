 # -*- coding: utf-8 -*-
import sys
import os
import subprocess
import ctypes
import threading
import string
import traceback
import time
import tempfile
import math

import config

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
    import set_injector as sinj
    from stone_color_page import StoneColorPage
    from dgvoodoo_page import DgvoodooPage
    from help_page import HelpPage
    import restore_list as rlist

except Exception as e:
    ctypes.windll.user32.MessageBoxW(0, f"Erro nas importações iniciais:\n\n{traceback.format_exc()}", "Crash Report - AIKA Optimizer", 0x10)
    sys.exit(1)

# --- MENSAGEM INTERNA DE ATIVAÇÃO (SINGLE INSTANCE) ---
# Enviado por uma segunda execução para solicitar que a instância
# existente seja mostrada/restaurada.
APP_ACTIVATE_MESSAGE = "__AIKA_OPTIMIZER_ACTIVATE__"

# Tempo maximo (ms) que o encerramento espera o cleanup pesado (restaurar
# Booster + remover QoS) antes de forcar o fechamento da janela. Mantem a
# interface responsiva durante o shutdown.
SHUTDOWN_CLEANUP_TIMEOUT_MS = 12000

# --- IDENTIDADE DA VERSÃO ---
# Rótulo único usado nos textos visíveis da interface para evitar divergência.
# Valor canônico centralizado em config.VERSAO_APLICATIVO.
VERSION_LABEL = config.VERSAO_APLICATIVO


def resolver_caminho(caminho_relativo):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, caminho_relativo)


def _novo_operation_id(tipo_operacao):
    return (
        f"{tipo_operacao.lower()}-{time.time_ns()}-"
        f"{os.getpid()}-{threading.get_ident()}"
    )


def _formatar_percentual_telemetria(valor):
    if isinstance(valor, (int, float)) and math.isfinite(valor):
        return f"{valor}%"
    return "indisponível"


def _quantidade_texto(valor, singular, plural=None):
    return f"{valor} {singular if valor == 1 else (plural or singular + 's')}"


def _falhas_telemetria_resultado(resultado):
    falhas = []
    for rotulo, chave in (("antes", "metricas_antes"),
                          ("depois", "metricas_depois")):
        metricas = resultado.get(chave) or {}
        for recurso, campo in (("CPU", "cpu_percent"),
                               ("RAM", "ram_percent")):
            valor = metricas.get(campo)
            if not isinstance(valor, (int, float)) or not math.isfinite(valor):
                falhas.append(f"{recurso} {rotulo}")
    return falhas


def _linhas_relatorio_game_booster(resultado):
    antes = resultado.get("metricas_antes") or {}
    depois = resultado.get("metricas_depois") or {}
    linhas = [
        f"[OK] GAME BOOST ATIVO: "
        f"{resultado.get('processos_encerrados', 0)} processos encerrados | "
        f"{resultado.get('mem_associada_mb', 0):.0f} MB associados | "
        f"CPU antes: {_formatar_percentual_telemetria(antes.get('cpu_percent'))} | "
        f"CPU depois: {_formatar_percentual_telemetria(depois.get('cpu_percent'))} | "
        f"RAM antes: {_formatar_percentual_telemetria(antes.get('ram_percent'))} | "
        f"RAM depois: {_formatar_percentual_telemetria(depois.get('ram_percent'))}"
    ]
    falhas_telemetria = _falhas_telemetria_resultado(resultado)
    if falhas_telemetria:
        linhas.append(
            "[AVISO] Métricas de CPU/RAM parcialmente indisponíveis: "
            + ", ".join(falhas_telemetria) + "."
        )

    prioridade = resultado.get("aika_priority_report") or {}
    detectados = prioridade.get("detected", 0)
    ja_high = prioridade.get("already_high", 0)
    alterados = prioridade.get(
        "changed", resultado.get("aika_priority_applied", 0)
    )
    falhas = prioridade.get("failed", 0)
    desapareceram = prioridade.get("disappeared", 0)
    if detectados == 0 and not falhas:
        nivel = "[INFO]"
    elif falhas or desapareceram:
        nivel = "[AVISO]"
    else:
        nivel = "[OK]"
    linhas.append(
        f"{nivel} AIKA: {_quantidade_texto(detectados, 'processo')} detectado"
        f"{'s' if detectados != 1 else ''} | "
        f"{ja_high} já em HIGH_PRIORITY | "
        f"{_quantidade_texto(alterados, 'prioridade')} alterada"
        f"{'s' if alterados != 1 else ''} | "
        f"{_quantidade_texto(falhas, 'falha')} | "
        f"{_quantidade_texto(desapareceram, 'processo')} desaparecido"
        f"{'s' if desapareceram != 1 else ''} durante a análise | "
        f"Serviços: {resultado.get('servicos_parados', 0)} parados"
    )
    for detalhe in prioridade.get("details", []):
        estado = detalhe.get("result")
        if estado not in ("failed", "disappeared"):
            continue
        pid = detalhe.get("pid", "?")
        nome = detalhe.get("name") or "Aika.exe"
        antes = detalhe.get("before_name") or "indisponível"
        depois = detalhe.get("after_name") or "indisponível"
        if estado == "disappeared":
            linhas.append(
                f"[INFO] AIKA PID {pid} {nome}: processo desapareceu "
                f"durante a análise; prioridade antes: {antes}."
            )
            continue
        tipo_erro = detalhe.get("error_type") or "Erro"
        etapa = detalhe.get("operation") or "indisponível"
        mensagem_bruta = str(detalhe.get("error_message") or "sem mensagem")
        if "Traceback" in mensagem_bruta:
            mensagem_bruta = mensagem_bruta.split("Traceback", 1)[0].strip()
            if not mensagem_bruta:
                mensagem_bruta = "detalhes disponíveis no log técnico"
        mensagem = " ".join(mensagem_bruta.split())[:180]
        pid_ativo = detalhe.get("pid_exists_after")
        pid_texto = "sim" if pid_ativo is True else "não" if pid_ativo is False else "indisponível"
        linhas.append(
            f"[AVISO] AIKA PID {pid} {nome}: prioridade antes: {antes} | "
            f"tentativa: HIGH_PRIORITY | etapa: {etapa} | resultado: FALHA | "
            f"erro: {tipo_erro}: {mensagem} | PID ainda ativo: {pid_texto} | "
            f"prioridade depois: {depois}."
        )
    return linhas


def _snapshot_itens_historico(itens):
    return {
        item.get("chave"): (
            item.get("injection_count"), item.get("last_applied")
        )
        for item in itens or [] if item.get("chave")
    }


def _anotar_operacao_historico(pasta_jogo, snapshot_antes, metadados,
                                chaves_exatas=None):
    try:
        dados = opt.carregar_historico_automod(pasta_jogo)
        if not isinstance(dados, dict) or not isinstance(dados.get("items"), dict):
            return False, []
        modo_exato = chaves_exatas is not None
        exatas = {
            str(chave).replace("\\", "/").lower()
            for chave in chaves_exatas or []
        }
        afetadas = []
        for chave, item in dados["items"].items():
            if modo_exato:
                alterado = chave.lower() in exatas
            else:
                anterior = (snapshot_antes or {}).get(chave)
                atual = (item.get("injection_count"), item.get("last_applied"))
                alterado = anterior is None or anterior != atual
            if alterado:
                item.update(metadados)
                afetadas.append(chave)
        if not afetadas:
            return False, []
        return bool(opt.salvar_historico_automod(dados, pasta_jogo)), afetadas
    except Exception:
        return False, []


def _rotulo_tipo_operacao(tipo):
    return {
        "SET_INJECTION": "INJEÇÃO DE SET",
        "WEAPON_INJECTION": "INJEÇÃO DE ARMA",
        "AUTOMOD": "AUTOMOD",
        "AUDIO": "ÁUDIO",
        "TEXTURE": "TEXTURA",
        "REMOVE_POLLUTED_EFFECTS": "REMOVER EFEITOS POLUÍDOS",
        "LEGACY": "MODIFICAÇÃO ANTIGA",
    }.get(str(tipo or "").upper(), "MODIFICAÇÃO")


def _agrupar_operacoes_historico(itens):
    operacoes = {}
    for indice, item_original in enumerate(itens or []):
        item = dict(item_original)
        chave = item.get("chave")
        operation_id = item.get("operation_id")
        legado = not bool(operation_id)
        if legado:
            operation_id = f"legacy:{chave or indice}"
        chave_grupo = (item.get("game_root") or "", operation_id)
        operacao = operacoes.setdefault(chave_grupo, {
            "operation_id": operation_id,
            "operation_type": item.get("operation_type") or "LEGACY",
            "operation_timestamp": (
                item.get("operation_timestamp") or item.get("last_applied") or ""
            ),
            "source_id": item.get("operation_source"),
            "target_id": item.get("operation_target"),
            "class_name": item.get("operation_class"),
            "base_sync": bool(item.get("operation_base_sync")),
            "game_root": item.get("game_root") or "",
            "client_name": item.get("operation_client"),
            "legacy": legado,
            "items": [],
            "keys": [],
        })
        operacao["items"].append(item)
        if chave:
            operacao["keys"].append(chave)
    resultado = list(operacoes.values())
    resultado.sort(
        key=lambda operacao: operacao.get("operation_timestamp") or "",
        reverse=True,
    )
    return resultado


def _agrupar_operacoes_por_data(operacoes):
    grupos = {}
    for operacao in operacoes or []:
        timestamp = str(operacao.get("operation_timestamp") or "")
        data_iso = timestamp[:10] if len(timestamp) >= 10 else "sem_data"
        grupos.setdefault(data_iso, []).append(operacao)
    return [(data, grupos[data]) for data in sorted(grupos, reverse=True)]


def _subtitulo_operacao(operacao):
    origem = operacao.get("source_id")
    alvo = operacao.get("target_id")
    tipo = operacao.get("operation_type")
    if tipo == "REMOVE_POLLUTED_EFFECTS":
        return origem or "Arquivos de efeitos removidos"
    if origem and alvo:
        prefixo = "Set " if tipo == "SET_INJECTION" else ""
        destino = "Set " if tipo == "SET_INJECTION" else ""
        return f"{prefixo}{origem} → {destino}{alvo}"
    if operacao.get("legacy"):
        item = (operacao.get("items") or [{}])[0]
        return item.get("target_name") or item.get("target_relpath") or "Arquivo antigo"
    return operacao.get("class_name") or "Operação registrada"


def _resumo_arquivos_removidos(arquivos):
    nomes = sorted({
        item.get("target_name") for item in arquivos or []
        if item.get("target_name")
    }, key=str.lower)
    if not nomes:
        return "Arquivos de efeitos removidos"
    destaque = next(
        (nome for nome in nomes if nome.lower() == "weaponeff3.bin"),
        nomes[0],
    )
    restantes = len(nomes) - 1
    return destaque if not restantes else f"{destaque} + {restantes} arquivo(s)"


def _chaves_das_operacoes(operacoes):
    return list(dict.fromkeys(
        chave for operacao in operacoes or []
        for chave in operacao.get("keys", [])
    ))

def _agrupar_chaves_por_cliente(operacoes):
    """Mantém cada unidade restaurável vinculada ao cliente de origem."""
    grupos = {}
    for operacao in operacoes or []:
        cliente = operacao.get("game_root") or ""
        chaves = grupos.setdefault(cliente, [])
        for chave in operacao.get("keys", []):
            if chave not in chaves:
                chaves.append(chave)
    return grupos



def _registrar_remocao_historico(pasta_jogo, arquivos, metadados):
    try:
        dados = opt.carregar_historico_automod(pasta_jogo)
        if not isinstance(dados, dict) or not isinstance(dados.get("items"), dict):
            return False
        timestamp = metadados.get("operation_timestamp") or time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        for arquivo in arquivos:
            relativo = arquivo["target_relpath"].replace("\\", "/")
            chave = relativo.lower()
            item = dados["items"].setdefault(chave, {})
            item.update({
                "target_relpath": relativo,
                "target_name": arquivo["target_name"],
                "mod_name": metadados.get("operation_type"),
                "backup_relpath": relativo,
                "game_root": pasta_jogo,
                "last_applied": timestamp,
                "injection_count": item.get("injection_count", 0) + 1,
                "category": "system",
                "operation": "DELETE",
                **metadados,
            })
        return bool(opt.salvar_historico_automod(dados, pasta_jogo))
    except Exception:
        return False


def _excluir_item_historico(chave, pasta_jogo):
    try:
        dados = opt.carregar_historico_automod(pasta_jogo)
        if chave not in dados.get("items", {}):
            return False
        del dados["items"][chave]
        return bool(opt.salvar_historico_automod(dados, pasta_jogo))
    except Exception:
        return False


def _filtrar_operacoes_por_data(operacoes, data_iso=None):
    if not data_iso:
        return list(operacoes or [])
    return [
        operacao for operacao in operacoes or []
        if str(operacao.get("operation_timestamp") or "")[:10] == data_iso
    ]


def _restaurar_chaves_historico(chaves, pasta_jogo):
    historico = {
        item.get("chave"): item
        for item in opt.listar_mods_ativos(pasta_jogo)
    }
    chaves_delete_poluidos = [
        chave for chave in chaves
        if historico.get(chave, {}).get("operation") == "DELETE"
        and historico.get(chave, {}).get("operation_type") == "REMOVE_POLLUTED_EFFECTS"
    ]
    chaves_delete_ef = [
        chave for chave in chaves
        if historico.get(chave, {}).get("operation") == "DELETE"
        and historico.get(chave, {}).get("operation_type") != "REMOVE_POLLUTED_EFFECTS"
    ]
    chaves_anteriores = [
        chave for chave in chaves
        if chave not in chaves_delete_poluidos and chave not in chaves_delete_ef
    ]
    resultado = opt.restaurar_mods_selecionados(chaves_anteriores, pasta_jogo)
    for chave in chaves_delete_ef:
        item = historico.get(chave, {})
        nome = item.get("target_name") or chave
        ok, mensagem = sinj.restaurar_ef_removido(chave, pasta_jogo)
        if ok:
            resultado["restaurados"].append(nome)
        else:
            resultado["falhas"].append((nome, mensagem))
    for chave in chaves_delete_poluidos:
        item = historico.get(chave, {})
        nome = item.get("target_name") or chave
        relativo = item.get("target_relpath") or item.get("backup_relpath") or chave
        ok, mensagem = opt.restaurar_arquivo_removido(
            relativo.replace("\\", "/"), pasta_jogo,
            persistir_historico=lambda c=chave: _excluir_item_historico(c, pasta_jogo),
        )
        if ok:
            resultado["restaurados"].append(nome)
        else:
            resultado["falhas"].append((nome, mensagem))
    return resultado


def _rotina_cleanup_shutdown():
    """Rotina pesada de encerramento, EXECUTADA FORA da thread da GUI.

    Restaura o Game Booster e remove as politicas QoS do AIKA. Nunca toca
    diretamente em widgets — apenas em modulos backend. Rodada de forma
    isolada (ex.: por um TarefaWorker) para o fechamento nao travar a janela.
    Retorna um dict com o resultado de cada etapa.
    """
    resultado = {"booster": False, "qos": False}
    try:
        opt.desativar_game_booster()
        resultado["booster"] = True
    except Exception as e:
        try:
            opt.log(f"[SHUTDOWN] Falha ao restaurar Game Booster: {e}")
        except Exception:
            pass
    try:
        opt.remover_qos_aika()
        resultado["qos"] = True
    except Exception as e:
        try:
            opt.log(f"[SHUTDOWN] Falha ao remover QoS: {e}")
        except Exception:
            pass
    return resultado

class TarefaWorker(QThread):
    resultado = Signal(object)
    erro = Signal(str)

    def __init__(self, func):
        super().__init__()
        self.func = func
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if not self._is_cancelled:
            try:
                resultado = self.func()
                self.resultado.emit(resultado)
            except Exception as e:
                try:
                    opt.log("Erro em tarefa em segundo plano", exception=True)
                except Exception:
                    traceback.print_exc()
                self.erro.emit(str(e) or e.__class__.__name__)

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
    log = Signal(str)                # observabilidade do backend no terminal

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
            cancel_callback=self._cancel_event.is_set,
            log_callback=self.log.emit,
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
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(5)

        # Linha horizontal: 4 colunas balanceadas
        row = QHBoxLayout()
        row.setSpacing(10)

        # CPU — Gauge Circular
        self.gauge_cpu = GaugeWidget("CPU")
        self.gauge_cpu.setMinimumSize(120, 120)
        row.addWidget(self.gauge_cpu, 1, Qt.AlignCenter)

        # RAM — Gauge Circular
        self.gauge_ram = GaugeWidget("RAM")
        self.gauge_ram.setMinimumSize(120, 120)
        row.addWidget(self.gauge_ram, 1, Qt.AlignCenter)

        # Processes — Card Texto
        proc_frame = self._criar_metrica_card("PROCESSES", "#FFD700")
        proc_icon = QLabel()
        proc_icon.setPixmap(QPixmap(resolver_caminho("assets/icons/processos.svg")).scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        proc_icon.setAlignment(Qt.AlignCenter)
        proc_icon.setFixedHeight(28)
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
        aika_icon.setPixmap(QPixmap(resolver_caminho("aika.ico")).scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        aika_icon.setAlignment(Qt.AlignCenter)
        aika_icon.setFixedHeight(28)
        aika_frame.layout().addWidget(aika_icon, 0, Qt.AlignCenter)
        self.lbl_aika_status = QLabel("--")
        self.lbl_aika_status.setStyleSheet("color: #BF00FF; font-family: 'Segoe UI'; font-size: 12px; font-weight: 600;")
        self.lbl_aika_status.setAlignment(Qt.AlignCenter)
        self.lbl_aika_status.setMinimumHeight(20)
        self.lbl_aika_status.setWordWrap(True)
        aika_frame.layout().addWidget(self.lbl_aika_status, 0, Qt.AlignCenter)
        row.addWidget(aika_frame, 0)

        layout.addLayout(row)
        self.setFixedHeight(178)
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
    """Monitora os processos reais do Aika (AClient/Aika) a cada 5s e aplica HIGH_PRIORITY_CLASS automaticamente.

    Nota: a afinidade (Isolar CPU / sem CPU 0) NÃO é aplicada automaticamente aqui —
    é uma ação explícita do usuário no card 'Isolar CPU' da aba Performance.
    """
    status_signal = Signal(bool, int, str)  # ativo, pid representativo, texto
    session_started_signal = Signal()  # transição: sem AIKA -> com AIKA
    session_ended_signal = Signal()    # transição: com AIKA -> sem AIKA

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self._sessao_ativa = False
        self.current_pids = {}  # pid -> create_time (para detectar PID reciclado)
        self._prioridades_observadas = {}  # pid -> estado real lido do Windows
        self._ultimo_status_emitido = None  # inclui quantidade e prioridades observadas
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
        return opt.avaliar_prioridade_processo_aika(proc, aplicar=True)

    def _observar_prioridade(self, proc):
        return opt.avaliar_prioridade_processo_aika(proc, aplicar=False)

    @staticmethod
    def _estado_prioridade_observado(detalhe):
        valor = detalhe.get("after")
        if valor is None:
            valor = detalhe.get("before")
        if opt.prioridade_e_high(valor):
            return "HIGH"
        nome = opt.nome_prioridade_windows(valor)
        return nome if nome != "indisponível" else "PRIORIDADE INDISPONÍVEL"

    def _texto_status_prioridade(self, pids_atuais):
        qtd = len(pids_atuais)
        estados = [
            self._prioridades_observadas.get(pid, "PRIORIDADE INDISPONÍVEL")
            for pid in pids_atuais
        ]
        unicos = set(estados)
        estado = estados[0] if len(unicos) == 1 else "PRIORIDADE MISTA"
        texto = f"ATIVO / {estado}"
        if qtd > 1:
            texto += f" ({qtd})"
        return texto, tuple(estados)

    def _processar_ciclo(self):
        import psutil
        pids_atuais = self._listar_pids_jogo()

        for pid, create_time in pids_atuais.items():
            try:
                proc = psutil.Process(pid)
                # Garante HIGH por PID em TODOS os ciclos: preserva quem já está
                # HIGH (already_high -> sem escrita) e reaplica HIGH em quem ficou
                # abaixo (recuperação automática). Falha de um PID nunca bloqueia
                # os demais, e nenhum PID é rebaixado por esta rotina.
                detalhe = self._aplicar_otimizacao(proc)
                self._prioridades_observadas[pid] = (
                    self._estado_prioridade_observado(detalhe)
                )
            except Exception:
                self._prioridades_observadas[pid] = "PRIORIDADE INDISPONÍVEL"
            self.current_pids[pid] = create_time

        for pid in list(self.current_pids.keys()):
            if pid not in pids_atuais:
                del self.current_pids[pid]
                self._prioridades_observadas.pop(pid, None)

        qtd = len(self.current_pids)
        sessao_ativa = qtd > 0
        if sessao_ativa and not self._sessao_ativa:
            self.session_started_signal.emit()
        elif not sessao_ativa and self._sessao_ativa:
            self.session_ended_signal.emit()
        self._sessao_ativa = sessao_ativa

        if qtd > 0:
            self._ciclos_sem_jogo = 0
            pid_principal = next(iter(self.current_pids))
            texto, estados = self._texto_status_prioridade(self.current_pids)
            chave = (True, qtd, estados)
            if chave != self._ultimo_status_emitido:
                self._ultimo_status_emitido = chave
                self.status_signal.emit(True, pid_principal, texto)
        else:
            self._ciclos_sem_jogo += 1
            if self._ciclos_sem_jogo >= 2:
                chave = (False, 0)
                if chave != self._ultimo_status_emitido:
                    self._ultimo_status_emitido = chave
                    self.status_signal.emit(False, 0, "OFFLINE")

    def run(self):
        import psutil
        while self._running:
            try:
                self._processar_ciclo()
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
    clicked = Signal()

    def __init__(self, parent, image_path, titulo):
        super().__init__(parent)
        self.setFixedSize(140, 158)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(4)

        self.caixa_imagem = QFrame()
        self.caixa_imagem.setFixedSize(116, 116)
        self.caixa_imagem.setStyleSheet("background-color: transparent;")

        layout_caixa = QVBoxLayout(self.caixa_imagem)
        layout_caixa.setContentsMargins(0, 0, 0, 0)
        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setStyleSheet("border-radius: 18px;")

        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            self.lbl_image.setPixmap(pixmap.scaled(125, 125, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.lbl_image.setText("AIKA")
            self.lbl_image.setStyleSheet("color: #BF00FF; font-weight: bold; font-size: 20px;")

        layout_caixa.addWidget(self.lbl_image)

        self.lbl_titulo = QLabel(titulo)
        self.lbl_titulo.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_titulo.setAlignment(Qt.AlignCenter)
        self.lbl_titulo.setFixedHeight(38)

        layout_principal.addWidget(self.caixa_imagem, 0, Qt.AlignCenter)
        layout_principal.addWidget(self.lbl_titulo, 0, Qt.AlignTop | Qt.AlignHCenter)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class AikaOptimizerPro(QMainWindow):
    def __init__(self, jit_args=None, jit_server=None):
        super().__init__()
        self.setWindowTitle(f"AIKA OPTIMIZER {VERSION_LABEL}")
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
        self._shutdown_closed = False
        self._shutdown_worker = None
        self._shutdown_closed = False
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
        
        acao_restaurar = QAction("Abrir AIKA Optimizer", self)
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
            QScrollBar:vertical {
                background-color: #1B1B24;
                width: 10px;
                margin: 2px 1px 2px 1px;
                border: none;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #6A2382;
                min-height: 24px;
                border-radius: 3px;
                margin: 1px;
            }
            QScrollBar::handle:vertical:hover { background-color: #9A31BC; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

            QScrollBar:horizontal {
                background-color: #1B1B24;
                height: 10px;
                margin: 1px 2px 1px 2px;
                border: none;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal {
                background-color: #6A2382;
                min-width: 24px;
                border-radius: 3px;
                margin: 1px;
            }
            QScrollBar::handle:horizontal:hover { background-color: #9A31BC; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

            QToolTip {
                background-color: #1B1B24;
                color: #E6E6F0;
                border: 1px solid #4D0080;
                border-radius: 6px;
                padding: 6px 8px;
                font-size: 12px;
            }
            QPushButton:disabled { color: #6A6A7A; }
            
            /* PADRONIZAÇÃO DOS BOTÕES SUPERIORES */
            QPushButton.WinButton { 
                background-color: transparent; 
                border-radius: 12px; 
                color: #BF00FF; 
                font-size: 15px; 
                font-weight: bold;
                font-family: 'Segoe UI';
            }
            
            /* Cores macOS no Hover */
            QPushButton#BtnClose:hover { background-color: #ff605c; color: white; }
            QPushButton#BtnMin:hover { background-color: #ffbd44; color: #050508; }
            QPushButton#BtnMax:hover { background-color: #00ca4e; color: white; }

            QFrame#Sidebar { background-color: rgba(7, 7, 12, 180); border: none; border-radius: 12px; }
            QPushButton.MenuButton { background-color: transparent; color: #888899; text-align: left; padding: 8px 16px; font-size: 14px; font-weight: bold; border: none; border-left: 4px solid transparent; }
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

        self.lbl_titulo = QLabel(f"AIKA OPTIMIZER {VERSION_LABEL}")
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
        self.btn_aba_injetor    = self.criar_botao_menu("Injetor Sets/Arm", 7, carregar_icone_svg("injector.svg"))
        self.btn_aba_restauracao= self.criar_botao_menu("Restauração", 8, carregar_icone_svg("restore.svg"))
        self.btn_aba_config     = self.criar_botao_menu("Configurações", 9, carregar_icone_svg("settings.svg"))
        self.btn_aba_pedras     = self.criar_botao_menu("Pedras", 10, carregar_icone_svg("pedras.svg"))
        
        layout_sidebar.addWidget(self.btn_aba_performance)
        layout_sidebar.addWidget(self.btn_aba_ferramentas)
        layout_sidebar.addWidget(self.btn_aba_automod)
        layout_sidebar.addWidget(self.btn_aba_audio)
        layout_sidebar.addWidget(self.btn_aba_extrator_jit)
        layout_sidebar.addWidget(self.btn_aba_sets)
        layout_sidebar.addWidget(self.btn_aba_injetor)
        layout_sidebar.addWidget(self.btn_aba_pedras)
        self.btn_aba_renderizador = self.criar_botao_menu("Renderizador", 11, carregar_icone_svg("renderizador.svg"))
        layout_sidebar.addWidget(self.btn_aba_renderizador)
        layout_sidebar.addStretch()
        layout_sidebar.addWidget(self.btn_aba_restauracao)
        layout_sidebar.addWidget(self.btn_aba_restore)
        self.btn_aba_ajuda = self.criar_botao_menu("Ajuda", 12, carregar_icone_svg("help.svg"))
        layout_sidebar.addWidget(self.btn_aba_ajuda)
        layout_sidebar.addWidget(self.btn_aba_config)
        layout_corpo.addWidget(sidebar)

        self.telas = QStackedWidget()
        self.telas.currentChanged.connect(self._on_tela_alterada)

        # --- TELA 0: PERFORMANCE ---
        page_perf = QWidget()
        layout_perf = QVBoxLayout(page_perf)
        layout_perf.setContentsMargins(12, 12, 12, 10)

        def obter_imagem(nome_base):
            caminho_png = resolver_caminho(f"assets/images/{nome_base}.png")
            caminho_jpg = resolver_caminho(f"assets/images/{nome_base}.jpg")
            return caminho_png if os.path.exists(caminho_png) else caminho_jpg

        grid_cards = QGridLayout()
        card_mpo = AikaCardGlow(self, obter_imagem("desativar_mpo"), "Desativar\nMPO")
        card_mpo.clicked.connect(self.acao_desativar_mpo)
        grid_cards.addWidget(card_mpo, 0, 0)
        card_cpu = AikaCardGlow(self, obter_imagem("isolar_cpu"), "Isolar\nCPU")
        card_cpu.clicked.connect(self.acao_isolar_cpu)
        grid_cards.addWidget(card_cpu, 0, 1)
        card_turbo = AikaCardGlow(self, obter_imagem("turbo_boost"), "Turbo\nBoost")
        card_turbo.clicked.connect(self.iniciar_boost_seguro)
        grid_cards.addWidget(card_turbo, 0, 2)
        card_cache = AikaCardGlow(self, obter_imagem("limpar_cache"), "Limpar\nCache")
        card_cache.clicked.connect(self.acao_limpar_cache)
        grid_cards.addWidget(card_cache, 0, 3)
        layout_perf.addLayout(grid_cards)

        layout_perf.addSpacing(6)

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
        desc_perf.setStyleSheet("color: #A0A0B0; font-size: 12px; background-color: rgba(255,255,255,10); padding: 9px; border-radius: 8px;")
        desc_perf.setAlignment(Qt.AlignLeft)
        layout_perf.addWidget(desc_perf)
        layout_perf.addSpacing(8)
        
        # Game Session Optimizer Metrics Panel
        self.booster_panel = GameBoosterPanel()
        layout_perf.addWidget(self.booster_panel, 0, Qt.AlignCenter)
        layout_perf.addSpacing(8)

        self.btn_boost = QPushButton("INICIAR OTIMIZAÇÃO GLOBAL")
        self.btn_boost.setMinimumHeight(64)
        self.btn_boost.setMinimumWidth(430)
        self.btn_boost.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_boost.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #BF00FF, stop:1 #660099); color: white; font-weight: bold; font-size: 17px; border-radius: 12px; border: 2px solid #BF00FF;")
        self.btn_glow = QGraphicsDropShadowEffect(self)
        self.btn_glow.setBlurRadius(30)
        self.btn_glow.setColor(QColor(191, 0, 255, 150))
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

        lbl_sys_desc = QLabel("Ajustes de rede, CPU e compatibilidade para reduzir latência e melhorar estabilidade do AIKA.")
        lbl_sys_desc.setWordWrap(True)
        lbl_sys_desc.setStyleSheet("color: #A0A0B0; font-size: 13px; background: transparent;")
        layout_sys.addWidget(lbl_sys_desc)

        # Seção DNS
        layout_sys.addWidget(self.criar_titulo_secao("SERVIDOR DNS", carregar_icone_svg("network.svg")))
        lbl_dns_desc = QLabel("Escolha qual servidor DNS o Windows usará para se conectar.")
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
        grid_m.addWidget(self.criar_card_sistema("Modo Tela Cheia (FSE)", "Otimiza o modo tela cheia e desativa Game Bar/GameDVR.", carregar_icone_svg("performance.svg"), self.acao_gamebar), 0, 0)
        grid_m.addWidget(self.criar_card_sistema("Remover Efeitos Poluídos", "Remove efeitos visuais pesados para reduzir a poluição visual.", carregar_icone_svg("protected.svg"), self.acao_weapon), 0, 1)
        grid_m.addWidget(self.criar_card_sistema("Reduzir Delay (TCP)", "Ativa TCP NoDelay para reduzir a latência de rede.", carregar_icone_svg("network.svg"), self.acao_tcp_nodelay), 0, 2)
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
                padding: 6px;
                outline: none;
            }
            QListWidget#AutoModHistory::item {
                background-color: rgba(255, 255, 255, 8);
                border: 1px solid rgba(255, 255, 255, 18);
                border-radius: 8px;
                margin: 3px 2px;
                padding: 9px 11px;
            }
            QListWidget#AutoModHistory::item:selected {
                background-color: rgba(191, 0, 255, 48);
                border: 1px solid rgba(191, 0, 255, 150);
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

        lbl_automod_desc = QLabel("Selecione arquivos de modificação e envie-os para o AIKA.")
        lbl_automod_desc.setWordWrap(True)
        lbl_automod_desc.setStyleSheet("color: #A0A0B0; font-size: 13px; background: transparent;")
        layout_automod.addWidget(lbl_automod_desc)

        lbl_automod_nota = QLabel("Hot-Swapping: texturas e áudios podem ser injetados com o jogo aberto, sem precisar reiniciá-lo.")
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

        layout_automod.addStretch()
        scroll_automod = QScrollArea()
        scroll_automod.setWidgetResizable(True)
        scroll_automod.setFrameShape(QFrame.NoFrame)
        scroll_automod.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_automod.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_automod.setWidget(page_automod)
        scroll_automod.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        scroll_automod.viewport().setAutoFillBackground(False)
        self.telas.addWidget(scroll_automod)

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

        lbl_audio_desc = QLabel("Substitua um som do jogo por um arquivo seu, mantendo o original protegido.")
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

        lbl_jogo_desc = QLabel("Restaura arquivos modificados do AIKA para o snapshot/estado protegido pelo sistema.")
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

        lbl_3d_sub = QLabel("Converte armaduras .MSH e armas .MS3 → .OBJ durante a organização, permitindo visualizar e identificar os modelos em programas 3D.")
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
        )
        scroll_sets.viewport().setAutoFillBackground(False)
        self.telas.addWidget(scroll_sets)

        # --- TELA 7: INJETOR DE SETS E ARMAS ---
        check_inj = resolver_caminho("assets/icons/check_green.svg").replace("\\", "/")
        estilo_injetor = f"""
            QFrame#InjCard {{
                background-color: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 16);
                border-radius: 12px;
            }}
            QPushButton#InjSelectBtn {{
                background-color: rgba(77, 0, 128, 120);
                color: #E6E6F0;
                border: 1px solid rgba(191, 0, 255, 90);
                border-radius: 8px;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton#InjSelectBtn:hover {{
                background-color: rgba(191, 0, 255, 70);
                border: 1px solid #BF00FF;
                color: white;
            }}
            QRadioButton#InjModeBtn {{
                background-color: rgba(20, 20, 30, 180);
                color: #A0A0B0;
                border: 1px solid rgba(255, 255, 255, 22);
                border-radius: 9px;
                padding: 9px 22px;
                font-size: 12px;
                font-weight: bold;
                spacing: 0px;
            }}
            QRadioButton#InjModeBtn::indicator,
            QRadioButton#InjModeBtn::indicator:unchecked,
            QRadioButton#InjModeBtn::indicator:checked,
            QRadioButton#InjModeBtn::indicator:disabled,
            QRadioButton#InjModeBtn::indicator:checked:disabled {{
                width: 0px;
                height: 0px;
                margin: 0px;
                padding: 0px;
                border: none;
                border-radius: 0px;
                background: transparent;
                image: none;
            }}
            QRadioButton#InjModeBtn:checked {{
                background-color: rgba(191, 0, 255, 65);
                color: white;
                border: 1px solid #BF00FF;
            }}
            QPushButton#InjExecBtn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4D0080, stop:1 #BF00FF);
                color: white; font-weight: bold; font-size: 15px;
                padding: 14px; border-radius: 12px; border: none;
            }}
            QPushButton#InjExecBtn:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #BF00FF, stop:1 #00D4FF);
            }}
            QPushButton#InjExecBtn:disabled {{ background: #333; color: #666; }}
            QPushButton#InjInjectBtn {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #BF00FF, stop:1 #7A1FA8);
                color: white; font-weight: bold; font-size: 16px;
                padding: 14px; border-radius: 12px;
                border: 1px solid rgba(191, 0, 255, 120);
            }}
            QPushButton#InjInjectBtn:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #D24BFF, stop:1 #8A2BBF);
                border: 1px solid #BF00FF;
            }}
            QPushButton#InjInjectBtn:disabled {{ background: #333; color: #666; border: 1px solid #444; }}
            QTextEdit#InjResult {{
                background-color: rgba(0, 0, 0, 80);
                border: 1px solid rgba(255, 255, 255, 16);
                border-radius: 8px;
                color: #B0B0BC;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                padding: 8px;
            }}
        """
        page_injetor = QWidget()
        page_injetor.setObjectName("InjPage")
        page_injetor.setStyleSheet(estilo_injetor)
        layout_inj = QVBoxLayout(page_injetor)
        layout_inj.setSpacing(7)
        layout_inj.setContentsMargins(14, 12, 14, 12)

        self.lbl_inj_t = QLabel("Injetor de Sets")
        self.lbl_inj_t.setStyleSheet("color: white; font-size: 20px; font-weight: bold; background: transparent;")
        layout_inj.addWidget(self.lbl_inj_t)

        self.lbl_inj_d = QLabel("Use a aparência de uma variante de armadura em outro set da mesma classe. Somente .MSH e .JIT entram neste modo.")
        self.lbl_inj_d.setStyleSheet("color: #A0A0B0; font-size: 13px; background: transparent;")
        self.lbl_inj_d.setWordWrap(True)
        layout_inj.addWidget(self.lbl_inj_d)

        card_modo = QFrame()
        card_modo.setObjectName("InjCard")
        lay_modo = QHBoxLayout(card_modo)
        lay_modo.setContentsMargins(14, 9, 14, 9)
        lay_modo.setSpacing(8)
        lbl_modo = QLabel("TIPO DE MODIFICAÇÃO")
        lbl_modo.setStyleSheet("color: #BF00FF; font-size: 11px; font-weight: bold; background: transparent; border: none;")
        lay_modo.addWidget(lbl_modo)
        lay_modo.addStretch()
        self.rb_inj_sets = QRadioButton("SETS")
        self.rb_inj_armas = QRadioButton("ARMAS")
        for botao in (self.rb_inj_sets, self.rb_inj_armas):
            botao.setObjectName("InjModeBtn")
            botao.setCursor(QCursor(Qt.PointingHandCursor))
            lay_modo.addWidget(botao)
        self.grupo_modo_injetor = QButtonGroup(self)
        self.grupo_modo_injetor.addButton(self.rb_inj_sets)
        self.grupo_modo_injetor.addButton(self.rb_inj_armas)
        self.rb_inj_sets.setChecked(True)
        self.rb_inj_sets.toggled.connect(self._on_modo_injetor_alterado)
        self.rb_inj_armas.toggled.connect(self._on_modo_injetor_alterado)
        layout_inj.addWidget(card_modo)

        # --- APARÊNCIA DOADORA ---
        card_doador = QFrame()
        card_doador.setObjectName("InjCard")
        lay_doador = QVBoxLayout(card_doador)
        lay_doador.setContentsMargins(14, 10, 14, 10)
        lay_doador.setSpacing(5)
        self.lbl_inj_doador_titulo = self.criar_header_secao("APARÊNCIA DOADORA", carregar_icone_svg("sets.svg"))
        lay_doador.addWidget(self.lbl_inj_doador_titulo)

        row_doador = QHBoxLayout()
        row_doador.setSpacing(8)
        self.btn_sel_doador = QPushButton("Selecionar Pasta")
        self.btn_sel_doador.setObjectName("InjSelectBtn")
        self.btn_sel_doador.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_sel_doador.clicked.connect(self.selecionar_pasta_doador)
        row_doador.addWidget(self.btn_sel_doador)
        row_doador.addStretch()
        lay_doador.addLayout(row_doador)

        self.lbl_info_doador = QLabel("Nenhuma pasta selecionada.")
        self.lbl_info_doador.setStyleSheet("color: #8A8A9A; font-size: 12px; background: transparent; border: none;")
        self.lbl_info_doador.setWordWrap(True)
        lay_doador.addWidget(self.lbl_info_doador)

        layout_inj.addWidget(card_doador)

        # --- ALVO ---
        card_alvo = QFrame()
        card_alvo.setObjectName("InjCard")
        lay_alvo = QVBoxLayout(card_alvo)
        lay_alvo.setContentsMargins(14, 10, 14, 10)
        lay_alvo.setSpacing(5)
        self.lbl_inj_alvo_titulo = self.criar_header_secao("SET ALVO", carregar_icone_svg("sets.svg"))
        lay_alvo.addWidget(self.lbl_inj_alvo_titulo)

        row_alvo = QHBoxLayout()
        row_alvo.setSpacing(8)
        self.btn_sel_alvo = QPushButton("Selecionar Pasta")
        self.btn_sel_alvo.setObjectName("InjSelectBtn")
        self.btn_sel_alvo.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_sel_alvo.clicked.connect(self.selecionar_pasta_alvo)
        row_alvo.addWidget(self.btn_sel_alvo)
        row_alvo.addStretch()
        lay_alvo.addLayout(row_alvo)

        self.lbl_info_alvo = QLabel("Nenhuma pasta selecionada.")
        self.lbl_info_alvo.setStyleSheet("color: #8A8A9A; font-size: 12px; background: transparent; border: none;")
        self.lbl_info_alvo.setWordWrap(True)
        lay_alvo.addWidget(self.lbl_info_alvo)

        layout_inj.addWidget(card_alvo)

        # --- CLIENTE REAL QUE RECEBERÁ A INJEÇÃO ---
        card_cliente_destino = QFrame()
        card_cliente_destino.setObjectName("InjCard")
        lay_cliente_destino = QVBoxLayout(card_cliente_destino)
        lay_cliente_destino.setContentsMargins(14, 10, 14, 10)
        lay_cliente_destino.setSpacing(5)
        lay_cliente_destino.addWidget(
            self.criar_header_secao(
                "CLIENTE DESTINO DA INJEÇÃO",
                carregar_icone_svg("sets.svg"),
            )
        )

        row_cliente_destino = QHBoxLayout()
        row_cliente_destino.setSpacing(8)
        self.btn_sel_cliente_injetor = QPushButton("Selecionar Cliente")
        self.btn_sel_cliente_injetor.setObjectName("InjSelectBtn")
        self.btn_sel_cliente_injetor.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_sel_cliente_injetor.clicked.connect(
            self.selecionar_cliente_destino_injetor
        )
        row_cliente_destino.addWidget(self.btn_sel_cliente_injetor)
        row_cliente_destino.addStretch()
        lay_cliente_destino.addLayout(row_cliente_destino)

        self.lbl_info_cliente_injetor = QLabel(
            "Nenhum cliente destino selecionado."
        )
        self.lbl_info_cliente_injetor.setStyleSheet(
            "color: #8A8A9A; font-size: 12px; "
            "background: transparent; border: none;"
        )
        self.lbl_info_cliente_injetor.setWordWrap(True)
        lay_cliente_destino.addWidget(self.lbl_info_cliente_injetor)
        layout_inj.addWidget(card_cliente_destino)

        # --- AÇÕES ---
        row_acoes = QHBoxLayout()
        row_acoes.setSpacing(10)
        self.btn_preparar = QPushButton("PREPARAR")
        self.btn_preparar.setObjectName("InjExecBtn")
        self.btn_preparar.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_preparar.setEnabled(False)
        self.btn_preparar.clicked.connect(self.acao_preparar_set)
        row_acoes.addWidget(self.btn_preparar, 1)

        self.btn_simular = QPushButton("SIMULAR INJEÇÃO")
        self.btn_simular.setObjectName("InjExecBtn")
        self.btn_simular.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_simular.setEnabled(False)
        self.btn_simular.clicked.connect(self.acao_simular_injecao)
        row_acoes.addWidget(self.btn_simular, 1)

        self.btn_injetar = QPushButton("INJETAR NO AIKA")
        self.btn_injetar.setObjectName("InjInjectBtn")
        self.btn_injetar.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_injetar.setEnabled(False)
        self.btn_injetar.clicked.connect(self.acao_injetar_set)
        row_acoes.addWidget(self.btn_injetar, 1)
        layout_inj.addLayout(row_acoes)

        # --- RESULTADO ---
        self.terminal_injetor = QTextEdit()
        self.terminal_injetor.setObjectName("InjResult")
        self.terminal_injetor.setReadOnly(True)
        self.terminal_injetor.setPlaceholderText("Resultado da preparação / simulação aparecerá aqui...")
        self.terminal_injetor.setFixedHeight(130)
        layout_inj.addWidget(self.terminal_injetor)

        layout_inj.addStretch()

        # ScrollArea para o Injetor
        scroll_inj = QScrollArea()
        scroll_inj.setWidgetResizable(True)
        scroll_inj.setFrameShape(QFrame.NoFrame)
        scroll_inj.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_inj.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_inj.setWidget(page_injetor)
        scroll_inj.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        scroll_inj.viewport().setAutoFillBackground(False)
        self.telas.addWidget(scroll_inj)

        # Estado interno do Injetor
        self._inj_doador_info = None
        self._inj_alvo_info = None
        self._inj_mapeados = None
        self._inj_ignorados = None
        self._inj_staging = None
        self._inj_preparado = False
        self._inj_busy = False
        self._inj_operacao = None
        self._inj_modo = "set"
        self._inj_cliente_destino = None
        self._inj_cliente_simulado = None
        self._inj_simulacao_total = 0

        # --- TELA 8: RESTAURAÇÃO SELETIVA ---
        self.telas.addWidget(self._criar_pagina_restauracao())

        # --- TELA 9: CONFIGURAÇÕES ---
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

        lbl_config_d = QLabel(f"Preferências do AIKA Optimizer {VERSION_LABEL}")
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
            (carregar_icone_svg("sistema.svg"), "Inicializar com o Windows", "", self.chk_startup),
            (carregar_icone_svg("minimize.svg"), "Iniciar minimizado", "Ao iniciar com o Windows, permanece na bandeja do sistema.", self.chk_start_minimized),
            (carregar_icone_svg("tray.svg"), "Fechar para bandeja", "Ao clicar no X, o aplicativo vai para a bandeja.", self.chk_close_to_tray),
        ])

        grupo_booster = self.criar_grupo_config("GAME BOOSTER", [
            (carregar_icone_svg("performance.svg"), "Auto Boost", "Executa a otimização global automaticamente quando o AIKA é detectado.", self.chk_auto_boost),
            (carregar_icone_svg("game_booster.svg"), "Modo Agressivo", "Durante a otimização, pode fechar navegadores e atualizadores. Processos protegidos permanecem intactos.", self.chk_aggressive),
        ])

        # Nivela os dois cards superiores: mesma altura mínima compartilhada
        # (calculada pelo conteúdo natural), sem números arbitrários.
        grupo_inicio.layout().activate()
        grupo_booster.layout().activate()
        altura_maxima = max(
            grupo_inicio.minimumSizeHint().height(),
            grupo_booster.minimumSizeHint().height(),
        )
        grupo_inicio.setMinimumHeight(altura_maxima)
        grupo_booster.setMinimumHeight(altura_maxima)

        row_config = QHBoxLayout()
        row_config.setSpacing(12)
        row_config.addWidget(grupo_inicio, 1, Qt.AlignTop)
        row_config.addWidget(grupo_booster, 1, Qt.AlignTop)
        layout_config.addLayout(row_config)

        # --- CLIENTE DO AIKA ---
        self.card_cliente_aika = QFrame()
        self.card_cliente_aika.setStyleSheet(
            "background-color: rgba(255, 255, 255, 10); "
            "border: 1px solid rgba(255, 255, 255, 16); border-radius: 12px;"
        )
        lay_cliente = QVBoxLayout(self.card_cliente_aika)
        lay_cliente.setContentsMargins(14, 12, 14, 12)
        lay_cliente.setSpacing(8)

        lbl_cliente_titulo = QLabel("CLIENTE DO AIKA")
        lbl_cliente_titulo.setStyleSheet(
            "color: #BF00FF; font-size: 11px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        lay_cliente.addWidget(lbl_cliente_titulo)

        row_cliente = QHBoxLayout()
        row_cliente.setSpacing(8)
        icone_cliente = QLabel()
        icone_cliente.setPixmap(carregar_icone_svg("sistema.svg").pixmap(18, 18))
        icone_cliente.setFixedSize(18, 18)
        icone_cliente.setStyleSheet(
            "background: transparent; border: none; padding: 0px; margin: 0px;"
        )
        row_cliente.addWidget(icone_cliente)

        lbl_cliente_item = QLabel("Cliente do AIKA")
        lbl_cliente_item.setStyleSheet(
            "color: white; font-size: 13px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        row_cliente.addWidget(lbl_cliente_item)
        row_cliente.addStretch()

        self.btn_cliente_aika = QPushButton("SELECIONAR PASTA")
        self.btn_cliente_aika.setObjectName("ConfigClienteBtn")
        self.btn_cliente_aika.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_cliente_aika.setStyleSheet(
            "background: rgba(77,0,128,90); color: #E6E6F0; "
            "border: 1px solid rgba(191,0,255,90); border-radius: 7px; "
            "padding: 7px 12px; font-size: 11px; font-weight: bold;"
        )
        self.btn_cliente_aika.clicked.connect(self.selecionar_cliente_aika)
        row_cliente.addWidget(self.btn_cliente_aika)
        lay_cliente.addLayout(row_cliente)

        self.lbl_cliente_aika_caminho = QLabel("Não configurado")
        self.lbl_cliente_aika_caminho.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_cliente_aika_caminho.setStyleSheet(
            "color: #8A8A9A; font-size: 11px; background: transparent; "
            "border: none; padding-left: 26px;"
        )
        lay_cliente.addWidget(self.lbl_cliente_aika_caminho)

        lbl_cliente_desc = QLabel("Pasta onde o AIKA está instalado.")
        lbl_cliente_desc.setWordWrap(True)
        lbl_cliente_desc.setStyleSheet(
            "color: #8A8A9A; font-size: 11px; background: transparent; "
            "border: none; padding-left: 26px;"
        )
        lay_cliente.addWidget(lbl_cliente_desc)

        layout_config.addWidget(self.card_cliente_aika)

        # --- INTEGRAÇÃO COM WINDOWS (.JIT) ---
        self.chk_jit_windows = QCheckBox("")
        self.chk_jit_windows.setCursor(QCursor(Qt.PointingHandCursor))
        self.chk_jit_windows.stateChanged.connect(self.acao_toggle_jit_windows)

        grupo_jit = self.criar_grupo_config("INTEGRAÇÃO COM WINDOWS", [
            (carregar_icone_svg("texturas.svg"), "Abrir arquivos .JIT com o AIKA Optimizer",
             "Permite abrir arquivos .JIT diretamente pelo Explorador do Windows.",
             self.chk_jit_windows),
        ])
        layout_config.addWidget(grupo_jit)

        layout_config.addStretch()
        self.telas.addWidget(page_config)

        # --- TELA 10: CORES DAS PEDRAS ---
        self.pedras_page = StoneColorPage(
            client_provider=lambda: opt.obter_pasta_jogo_atual(exigir_existente=True),
        )
        self.pedras_page.log_emitted.connect(self.sinais.log_signal.emit)
        self.pedras_page.settings_requested.connect(self._abrir_configuracoes_pelas_pedras)
        self.telas.addWidget(self.pedras_page)

        # --- TELA 11: RENDERIZADOR (dgVoodoo2) ---
        self.dgvoodoo_page = DgvoodooPage(
            client_provider=lambda: opt.obter_pasta_jogo_atual(exigir_existente=True),
            executor=self._executor_dgvoodoo,
        )
        self.dgvoodoo_page.log_emitted.connect(self.sinais.log_signal.emit)
        self.telas.addWidget(self.dgvoodoo_page)

        # --- TELA 12: AJUDA (somente leitura, navegação interna própria) ---
        self.ajuda_page = HelpPage()
        self.telas.addWidget(self.ajuda_page)

        # Sincronizar checkboxes com estado atual
        self.sincronizar_config_checkboxes()

        # LAYOUT FINAL DIREITA E LOGS INICIAIS
        layout_direita = QVBoxLayout()
        layout_direita.addWidget(self.telas)
        self.log_box = QTextEdit()
        self.log_box.setObjectName("AikaTerminal")
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(96)

        self.log_box.setText(">> [OK] MOTOR DX9 E KERNEL BLINDADOS INICIALIZADOS...\n>> [OK] PRONTO PARA ALTA PERFORMANCE NA JOY IMPACT ENGINE.")
        for mensagem_cliente in opt.consumir_mensagens_recuperacao_cliente():
            self.sinais.log_signal.emit(mensagem_cliente)
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
        self._sincronizar_checkbox_jit()
        if self._jit_args_iniciais:
            QTimer.singleShot(300, lambda: self.receber_jit_externo(self._jit_args_iniciais))

        # Política de tamanho inicial responsivo (notebooks/telas menores):
        # limita a janela à área útil real do monitor (availableGeometry),
        # com margem de segurança e centralização. Não maximiza. O usuário
        # continua podendo redimensionar/maximizar normalmente.
        try:
            tela_primaria = QApplication.primaryScreen()
            if tela_primaria is not None:
                geo = tela_primaria.availableGeometry()
                margem = 28
                largura_alvo = min(self.width(), max(640, geo.width() - 2 * margem))
                altura_alvo = min(self.height(), max(480, geo.height() - 2 * margem))
                if largura_alvo < self.width() or altura_alvo < self.height():
                    self.resize(largura_alvo, altura_alvo)
                x = geo.x() + max(0, (geo.width() - self.width()) // 2)
                y = geo.y() + max(0, (geo.height() - self.height()) // 2)
                self.move(x, y)
        except Exception:
            pass

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

    def _abrir_configuracoes_pelas_pedras(self):
        self.telas.setCurrentIndex(9)
        self.btn_aba_config.setChecked(True)

    def _criar_pagina_restauracao(self):
        page = QWidget()
        page.setObjectName("RestauracaoPage")
        check_restore = resolver_caminho("assets/icons/check_green.svg").replace("\\", "/")
        page.setStyleSheet("""
            QWidget#RestauracaoPage {
                background-color: #08080D;
                color: #E6E6F0;
            }
            QWidget#RestauracaoPage QLabel {
                color: #D8D8E3;
                background-color: transparent;
            }
            QLabel#RestoreTitle {
                color: #FFFFFF;
                font-size: 20px;
                font-weight: bold;
            }
            QLabel#RestoreSubtitle {
                color: #A8A8B8;
            }
            QWidget#RestauracaoPage QCheckBox {
                color: #E2E2EC;
                spacing: 8px;
                background-color: transparent;
                font-weight: 600;
            }
            QWidget#RestauracaoPage QCheckBox::indicator {
                width: 17px;
                height: 17px;
            }
            QWidget#RestauracaoPage QCheckBox::indicator:unchecked {
                background-color: #09090E;
                border: 2px solid #5A2B72;
                border-radius: 4px;
            }
            QWidget#RestauracaoPage QCheckBox::indicator:unchecked:hover {
                border: 2px solid #BF00FF;
            }
            QWidget#RestauracaoPage QCheckBox::indicator:checked {
                background-color: #140B1C;
                border: 2px solid #BF00FF;
                border-radius: 4px;
                image: url(__CHECK_RESTORE__);
            }
            QWidget#RestauracaoPage QCheckBox::indicator:indeterminate {
                background-color: #BF00FF;
                border: 2px solid #E4A6FF;
                border-radius: 4px;
            }
            QComboBox#RestoreDateFilter {
                background-color: #101018;
                color: #ECECF4;
                border: 1px solid #4D2760;
                border-radius: 7px;
                padding: 7px 28px 7px 10px;
                min-width: 145px;
            }
            QComboBox#RestoreDateFilter:hover, QComboBox#RestoreDateFilter:focus {
                border: 1px solid #BF00FF;
                background-color: #15131E;
            }
            QComboBox#RestoreDateFilter::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox#RestoreDateFilter QAbstractItemView {
                background-color: #101018;
                color: #ECECF4;
                border: 1px solid #4D2760;
                selection-background-color: #4D1763;
                selection-color: #FFFFFF;
                outline: none;
            }
            QPushButton#RestoreSelectedButton {
                background-color: #2B1038;
                color: #E6E6F0;
                border: 1px solid #6C2A86;
                border-radius: 7px;
                padding: 7px 13px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton#RestoreSelectedButton:hover {
                background-color: #52136B;
                border: 1px solid #BF00FF;
                color: #FFFFFF;
            }
            QPushButton#RestoreSelectedButton:pressed {
                background-color: #741A96;
            }
            QPushButton#RestoreSelectedButton:disabled {
                background-color: #15151C;
                color: #666675;
                border: 1px solid #292932;
            }
            QTreeWidget#RestoreTable {
                background-color: #0A0A10;
                alternate-background-color: #0E0E15;
                border: 1px solid #24202D;
                border-radius: 8px;
                color: #D8D8E3;
                outline: none;
            }
            QTreeWidget#RestoreTable::item {
                padding: 4px 2px;
                border-bottom: 1px solid #1A1720;
            }
            QTreeWidget#RestoreTable::item:selected {
                background-color: #241633;
                color: #FFFFFF;
            }
            QTreeWidget#RestoreTable::indicator {
                width: 16px;
                height: 16px;
            }
            QTreeWidget#RestoreTable::indicator:unchecked {
                background-color: #09090E;
                border: 2px solid #5A2B72;
                border-radius: 4px;
            }
            QTreeWidget#RestoreTable::indicator:unchecked:hover {
                border: 2px solid #BF00FF;
            }
            QTreeWidget#RestoreTable::indicator:checked {
                background-color: #140B1C;
                border: 2px solid #BF00FF;
                border-radius: 4px;
                image: url(__CHECK_RESTORE__);
            }
            QTreeWidget#RestoreTable QHeaderView::section {
                background-color: #120D19;
                color: #BF00FF;
                font-weight: bold;
                border: none;
                border-bottom: 1px solid #352044;
                padding: 6px 8px;
            }
            QTreeWidget#RestoreTable QHeaderView::section:hover {
                background-color: #1B1224;
            }
            QPushButton#RestoreRowButton {
                background-color: #2B1038;
                color: #E6E6F0;
                border: 1px solid #6C2A86;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
                text-align: center;
            }
            QPushButton#RestoreRowButton:hover {
                background-color: #52136B;
                border: 1px solid #BF00FF;
                color: #FFFFFF;
            }
            QPushButton#RestoreRowButton:pressed {
                background-color: #741A96;
            }
            QPushButton#RestoreRowButton:disabled {
                background-color: #15151C;
                color: #666675;
                border: 1px solid #292932;
            }
        """.replace("__CHECK_RESTORE__", check_restore))
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(10)

        titulo = QLabel("Restauração")
        titulo.setObjectName("RestoreTitle")
        layout.addWidget(titulo)
        subtitulo = QLabel("Restaure modificações anteriores por operação ou data.")
        subtitulo.setObjectName("RestoreSubtitle")
        layout.addWidget(subtitulo)

        topo = QHBoxLayout()
        topo.addWidget(QLabel("Data:"))
        self.cmb_filtro_restauracao = QComboBox()
        self.cmb_filtro_restauracao.setObjectName("RestoreDateFilter")
        self.cmb_filtro_restauracao.addItem("Todas", None)
        self.cmb_filtro_restauracao.currentIndexChanged.connect(
            self._aplicar_filtro_restauracao
        )
        topo.addWidget(self.cmb_filtro_restauracao)
        topo.addStretch()
        self.btn_restaurar_mod = QPushButton("RESTAURAR SELECIONADAS")
        self.btn_restaurar_mod.setObjectName("RestoreSelectedButton")
        self.btn_restaurar_mod.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_restaurar_mod.setEnabled(False)
        self.btn_restaurar_mod.clicked.connect(self._on_restaurar_mod_selecionado)
        topo.addWidget(self.btn_restaurar_mod)
        layout.addLayout(topo)

        self.lista_restauracao = rlist.RestoreListWidget()
        self.lista_restauracao.setObjectName("RestoreTable")
        self.lista_restauracao.selecao_alterada.connect(self._selecionar_operacao_restauracao)
        self.lista_restauracao.selecao_em_lote.connect(self._selecionar_operacoes_restauracao)
        self.lista_restauracao.restaurar_operacao.connect(self._restaurar_operacao_direta)
        self.lista_restauracao.restaurar_pedras.connect(self._on_restaurar_pedras)
        layout.addWidget(self.lista_restauracao, 1)

        self.lista_historico = QListWidget()
        self.lista_historico.setVisible(False)
        self._restauracao_operacoes = []
        self._restauracao_selecionadas = set()
        self._pedras_resumo = None
        self._pedras_processo_aberto = False
        self._atualizar_historico_automod()
        QTimer.singleShot(0, self._atualizar_pedras_restauracao)
        return page

    def _on_tela_alterada(self, indice):
        # Ao entrar na aba Restauração (índice 8), atualiza o estado de Pedras.
        if indice == 8 and hasattr(self, "lista_restauracao"):
            QTimer.singleShot(0, self._atualizar_pedras_restauracao)
        elif indice == 11 and hasattr(self, "dgvoodoo_page"):
            QTimer.singleShot(0, self.dgvoodoo_page.refresh_estado)

    def _atualizar_pedras_restauracao(self):
        try:
            self._render_pedras_restauracao()
        except Exception:
            return

    def _render_pedras_restauracao(self):
        try:
            import stone_color_service as svc
        except Exception:
            return
        resumo = None
        processo_aberto = False
        try:
            client_root = opt.obter_pasta_jogo_atual()
            profile = resolver_caminho("itemlist6_color_profile.json")
            resumo = svc.list_stones_backups(client_root, profile)
            det = svc.detect_relevant_processes(client_root)
            processo_aberto = bool(det.matches)
        except Exception:
            resumo = None
            processo_aberto = False
        self._pedras_resumo = resumo
        self._pedras_processo_aberto = processo_aberto
        self._renderizar_lista_restauracao()

    def _on_restaurar_pedras(self):
        try:
            import stone_color_service as svc
        except Exception as exc:
            self.sinais.log_signal.emit(f"[ERRO] Falha ao carregar o serviço de Pedras: {exc}")
            return

        def tarefa():
            self.sinais.log_signal.emit("[INFO] Restaurando cores das pedras para a base preservada...")
            client_root = opt.obter_pasta_jogo_atual()
            profile = resolver_caminho("itemlist6_color_profile.json")
            return svc.restore_colors(client_root, profile)

        def sucesso(resultado):
            if resultado is not None and getattr(resultado, "restored", False):
                self.sinais.log_signal.emit(f"[OK] {resultado.message}")
                if hasattr(self, "pedras_page"):
                    QTimer.singleShot(0, self.pedras_page.refresh_after_restore)

        def erro(mensagem):
            self.sinais.log_signal.emit(f"[ERRO] {mensagem}")

        def concluido():
            QTimer.singleShot(0, self._atualizar_pedras_restauracao)

        self.executar_em_background(
            tarefa, resultado_callback=sucesso, erro_callback=erro, finalizado_callback=concluido
        )

    def _datas_disponiveis_restauracao(self, operacoes):
        datas = {
            str(op.get("operation_timestamp") or "")[:10]
            for op in operacoes
            if len(str(op.get("operation_timestamp") or "")) >= 10
        }
        return sorted(datas, reverse=True)

    def _aplicar_filtro_restauracao(self):
        self._renderizar_lista_restauracao()

    def _renderizar_lista_restauracao(self):
        if not hasattr(self, "lista_restauracao"):
            return
        data_iso = self.cmb_filtro_restauracao.currentData()
        operacoes = _filtrar_operacoes_por_data(self._restauracao_operacoes, data_iso)
        rows = [rlist.build_operation_row(op) for op in operacoes]
        pedras = rlist.build_pedras_row(self._pedras_resumo, self._pedras_processo_aberto)
        if not data_iso or (pedras.get("sort_data") and str(pedras["sort_data"])[:10] == data_iso):
            rows.append(pedras)
        visiveis = {
            rlist.operation_key(row.get("client_root"), row.get("operation_id"))
            for row in rows if row.get("kind") == "operation"
        }
        self._restauracao_selecionadas.intersection_update(visiveis)
        self.lista_restauracao.populate(rows, self._restauracao_selecionadas)
        self._atualizar_botao_restauracao()

    def _selecionar_operacao_restauracao(self, identidade, marcado):
        if marcado:
            self._restauracao_selecionadas.add(identidade)
        else:
            self._restauracao_selecionadas.discard(identidade)
        self._atualizar_botao_restauracao()

    def _selecionar_operacoes_restauracao(self, identidades, marcado):
        identidades = set(identidades or ())
        if marcado:
            self._restauracao_selecionadas.update(identidades)
        else:
            self._restauracao_selecionadas.difference_update(identidades)
        self._atualizar_botao_restauracao()

    def _atualizar_botao_restauracao(self):
        quantidade = len(self._restauracao_selecionadas)
        self.btn_restaurar_mod.setEnabled(quantidade > 0)
        texto = "RESTAURAR SELECIONADAS"
        if quantidade:
            texto += f" ({quantidade})"
        self.btn_restaurar_mod.setText(texto)

    def _restaurar_operacao_direta(self, identidade):
        if not isinstance(identidade, tuple):
            correspondencias = [
                rlist.operation_key(op.get("game_root"), op.get("operation_id"))
                for op in self._restauracao_operacoes
                if op.get("operation_id") == identidade
            ]
            if len(correspondencias) != 1:
                return
            identidade = correspondencias[0]
        self._restauracao_selecionadas = {identidade}
        self._on_restaurar_mod_selecionado()

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

    def _executor_dgvoodoo(self, fn):
        """Executor adapter para a página Renderizador.

        Delega a operação para a infraestrutura real de background
        (executar_em_background / TarefaWorker), garantindo que a operação
        pesada (SHA-256, backup, cópia atômica) rode fora da UI thread.

        Para evitar que o refresh interno da página (atualização de widgets)
        execute na worker thread, substituímos temporariamente refresh_estado
        por um no-op durante a operação. O refresh real acontece na UI thread,
        no callback de finalização.
        """
        page = getattr(fn, "__self__", None)
        if page is not None:
            original_refresh = page.refresh_estado
            page.refresh_estado = lambda: None

            def on_finished():
                page.refresh_estado = original_refresh
                original_refresh()
        else:
            on_finished = None

        def wrapper():
            fn()

        self.executar_em_background(wrapper, finalizado_callback=on_finished)

    def executar_em_background(self, f, resultado_callback=None,
                               erro_callback=None, finalizado_callback=None):
        if self._shutdown_pending or self._shutdown_finalizando:
            return False
        with self.tarefa_lock:
            if self.executando_tarefa:
                self.sinais.log_signal.emit("[INFO] Uma tarefa já está em andamento. Aguarde...")
                return False
            self.executando_tarefa = True

        self.worker = TarefaWorker(f)
        if resultado_callback is not None:
            self.worker.resultado.connect(resultado_callback)
        if erro_callback is not None:
            self.worker.erro.connect(erro_callback)
        if finalizado_callback is not None:
            self.worker.finished.connect(finalizado_callback)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.finished.connect(self.limpar_execucao)
        self.worker.start()
        return True

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
                estado_antes_plano = [None]
                def preparar_rollback_plano():
                    estado_antes_plano[0] = opt.capturar_estado_sistema()
                    return True
                transacao.executar(preparar_rollback_plano)
                transacao.executar(
                    opt.modo_desempenho_maximo,
                    rollback=lambda: opt.restaurar_estado_sistema(estado_antes_plano[0], escopo="plano"),
                )
                transacao.executar(opt.prioridade_total)
                
                self.sinais.log_signal.emit(f"[OK] Ativando Game Session Optimizer {VERSION_LABEL}...")
                resultado = opt.game_session_optimizer(dry_run=False)
                emit_worker_metrics()  # Métricas pós-otimização
                if resultado.get("status") == "error":
                    self.sinais.log_signal.emit(f"[ERRO] Erro: {resultado.get('message', 'Falha desconhecida')}")
                    transacao.rollback_total()
                    raise Exception(resultado.get('message', 'Falha desconhecida'))
                else:
                    for linha in _linhas_relatorio_game_booster(resultado):
                        self.sinais.log_signal.emit(linha)

                self.sinais.log_signal.emit("[OK] OTIMIZAÇÃO COMPLETA FINALIZADA COM SUCESSO!")
                emit_worker_metrics()
                worker_metrics_active[0] = False
                if not opt.jogo_esta_aberto():
                    if not jogo_estava_aberto_no_inicio:
                        self._suprimir_auto_boost_ate = time.monotonic() + 120
                    self.sinais.log_signal.emit("[OK] Iniciando o jogo agora...")
                    opt.iniciar_jogo(opt.obter_pasta_jogo_atual())
            except Exception as e:
                self.sinais.log_signal.emit(f"[ERRO] ERRO CRÍTICO: {e}")
                self.sinais.log_signal.emit("[INFO] Rollback automático executado quando disponível. Ajustes de Registro podem permanecer; use a aba Segurança para restauração completa.")
                worker_metrics_active[0] = False

        self.executar_em_background(tarefa_transacao)

    def acao_desativar_mpo(self):
        """Card 'Desativar MPO': executa o backend real em background com resultado honesto."""
        def tarefa():
            if opt.desativar_mpo():
                self.sinais.log_signal.emit("[OK] MPO (Multiplane Overlay) desativado no Registro. Reinicie o PC (ou o app gráfico) para o efeito valer.")
            else:
                self.sinais.log_signal.emit("[ERRO] Não foi possível desativar o MPO. Execute o AIKA Optimizer como administrador.")
        self.executar_em_background(tarefa)

    def acao_isolar_cpu(self):
        """Card 'Isolar CPU': ação explícita do usuário — aplica afinidade (remove CPU 0) aos processos do AIKA."""
        def tarefa():
            if not opt.jogo_esta_aberto():
                self.sinais.log_signal.emit("[INFO] O AIKA não está aberto. Abra o jogo e clique em 'Isolar CPU' novamente.")
                return
            if opt.otimizar_afinidade_aika():
                self.sinais.log_signal.emit("[OK] Afinidade aplicada: CPU 0 removida dos processos do AIKA.")
            else:
                self.sinais.log_signal.emit("[INFO] Nenhum ajuste aplicado (jogo já otimizado, sem acesso ao processo ou sem CPUs disponíveis para isolar).")
        self.executar_em_background(tarefa)

    def acao_limpar_cache(self):
        """Card 'Limpar Cache': limpeza de cache de shaders (D3DSCache/NVIDIA/AMD e cache do cliente selecionado) em background."""
        def tarefa():
            if opt.limpar_shader_cache():
                self.sinais.log_signal.emit("[OK] Cache de shaders limpo (D3DSCache/NVIDIA/AMD e cache do cliente selecionado). O cache será recompilado na próxima execução.")
            else:
                self.sinais.log_signal.emit("[ERRO] Falha ao limpar o cache de shaders (algumas pastas não puderam ser removidas — arquivos em uso?).")
        self.executar_em_background(tarefa)

    # ========================================================
    # EVENTOS DE MODDING, EXTRAÇÃO E ÁUDIO
    # ========================================================
    def encontrar_pasta_sound(self):
        pasta_jogo = opt.obter_pasta_jogo_atual()
        if not pasta_jogo:
            return ""
        pasta_sound = os.path.join(pasta_jogo, "Sound")
        return pasta_sound if os.path.isdir(pasta_sound) else ""

    ESTILO_NEON_CARREGADO = "color: #00FF00; font-size: 13px; font-weight: bold; background-color: rgba(0, 50, 0, 150); border: 1px solid #00FF00; padding: 5px; border-radius: 5px;"

    def selecionar_audio_jogo(self):
        f, _ = QFileDialog.getOpenFileName(self, "Selecionar Original", self.encontrar_pasta_sound(), "AIKA (*.bin *.wav);;Tudo (*.*)")
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
        else:
            # Formato real não reconhecido pelo conteúdo — não fingir que é WAV.
            self.sinais.log_signal.emit("[ERRO] Formato de áudio original não reconhecido para prévia.")

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

    def _renderizar_operacoes_historico(self, itens):
        operacoes = _agrupar_operacoes_historico(itens)
        for data_iso, grupo in _agrupar_operacoes_por_data(operacoes):
            partes_data = data_iso.split("-")
            if data_iso == "sem_data" or len(partes_data) != 3:
                data_exibida = "DATA NÃO REGISTRADA"
            else:
                ano, mes, dia = partes_data
                data_exibida = f"{dia}/{mes}/{ano}"
            quantidade = len(grupo)
            sufixo = "operação" if quantidade == 1 else "operações"
            cabecalho = QListWidgetItem(
                f"{data_exibida}  •  {quantidade} {sufixo}"
            )
            cabecalho.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            cabecalho.setCheckState(Qt.Unchecked)
            cabecalho.setData(Qt.UserRole, {
                "kind": "date",
                "operation_ids": [op["operation_id"] for op in grupo],
                "keys": [chave for op in grupo for chave in op["keys"]],
            })
            cabecalho.setForeground(QColor(210, 120, 255))
            fonte = cabecalho.font()
            fonte.setBold(True)
            cabecalho.setFont(fonte)
            cabecalho.setSizeHint(QSize(0, 34))
            self.lista_historico.addItem(cabecalho)
            for operacao in grupo:
                self._adicionar_card_operacao_historico(operacao)

    def _adicionar_card_operacao_historico(self, operacao):
        timestamp = str(operacao.get("operation_timestamp") or "")
        horario = timestamp[11:16] if len(timestamp) >= 16 else "--:--"
        quantidade = len(operacao["keys"])
        cliente = (
            operacao.get("client_name")
            or os.path.basename(os.path.normpath(operacao.get("game_root") or ""))
            or "não identificado"
        )
        extras = []
        if operacao.get("class_name"):
            extras.append(operacao["class_name"])
        if operacao.get("base_sync"):
            extras.append("Base 01 sincronizada")
        texto = (
            f"{horario}  •  {_rotulo_tipo_operacao(operacao['operation_type'])}\n"
            f"{_subtitulo_operacao(operacao)}\n"
            f"{' • '.join(extras) + ' • ' if extras else ''}"
            f"{quantidade} arquivo(s) • Cliente: {cliente}\n"
            "Ver detalhes"
        )
        card = QListWidgetItem(texto)
        card.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
        card.setCheckState(Qt.Unchecked)
        card.setData(Qt.UserRole, {
            "kind": "operation",
            "operation_id": operacao["operation_id"],
            "keys": list(operacao["keys"]),
            "operation_type": operacao["operation_type"],
            "subtitle": _subtitulo_operacao(operacao),
            "game_root": operacao.get("game_root"),
        })
        card.setData(Qt.UserRole + 1, _subtitulo_operacao(operacao))
        card.setSizeHint(QSize(0, 92))
        self.lista_historico.addItem(card)
        for arquivo in operacao["items"]:
            rel = arquivo.get("target_relpath") or arquivo.get("target_name") or "?"
            detalhe = QListWidgetItem(f"    {rel}")
            detalhe.setFlags(Qt.NoItemFlags)
            detalhe.setData(Qt.UserRole, {
                "kind": "detail",
                "operation_id": operacao["operation_id"],
            })
            detalhe.setForeground(QColor(150, 150, 165))
            detalhe.setSizeHint(QSize(0, 24))
            self.lista_historico.addItem(detalhe)
            detalhe.setHidden(True)

    def _atualizar_historico_automod(self, itens=None):
        """Atualiza a lista de operações e o histórico legado oculto."""
        try:
            if itens is None:
                itens = opt.listar_mods_ativos(opt.obter_pasta_jogo_atual())
            if hasattr(self, "lista_restauracao"):
                self._restauracao_operacoes = _agrupar_operacoes_historico(itens)
                ids_atuais = {
                    rlist.operation_key(
                        operacao.get("game_root"), operacao["operation_id"]
                    )
                    for operacao in self._restauracao_operacoes
                }
                self._restauracao_selecionadas.intersection_update(ids_atuais)
                datas = self._datas_disponiveis_restauracao(
                    self._restauracao_operacoes
                )
                filtro_atual = self.cmb_filtro_restauracao.currentData()
                self.cmb_filtro_restauracao.blockSignals(True)
                self.cmb_filtro_restauracao.clear()
                self.cmb_filtro_restauracao.addItem("Todas", None)
                for data_iso in datas:
                    ano, mes, dia = data_iso.split("-")
                    self.cmb_filtro_restauracao.addItem(
                        f"{dia}/{mes}/{ano}", data_iso
                    )
                indice = self.cmb_filtro_restauracao.findData(filtro_atual)
                self.cmb_filtro_restauracao.setCurrentIndex(
                    indice if indice >= 0 else 0
                )
                self.cmb_filtro_restauracao.blockSignals(False)
                self._aplicar_filtro_restauracao()
                return
            self._atualizando_historico = True
            self.lista_historico.clear()
            if not itens:
                item_vazio = QListWidgetItem("Nenhuma modificação ativa.")
                item_vazio.setFlags(Qt.NoItemFlags)
                item_vazio.setForeground(QColor(138, 138, 154))
                self.lista_historico.addItem(item_vazio)
            else:
                self._renderizar_operacoes_historico(itens)
            self.btn_restaurar_mod.setEnabled(False)
            self.btn_restaurar_mod.setText("RESTAURAR SELECIONADAS")
        except Exception:
            pass
        finally:
            self._atualizando_historico = False

    def _on_item_historico_clicado(self, item):
        payload = item.data(Qt.UserRole)
        if not isinstance(payload, dict) or payload.get("kind") != "operation":
            return
        operation_id = payload.get("operation_id")
        detalhes = []
        for indice in range(self.lista_historico.count()):
            candidato = self.lista_historico.item(indice)
            dados = candidato.data(Qt.UserRole)
            if (
                isinstance(dados, dict)
                and dados.get("kind") == "detail"
                and dados.get("operation_id") == operation_id
            ):
                detalhes.append(candidato)
        expandir = bool(detalhes and detalhes[0].isHidden())
        for detalhe in detalhes:
            detalhe.setHidden(not expandir)

    def _on_item_historico_alterado(self, item):
        if getattr(self, "_atualizando_historico", False):
            return
        payload = item.data(Qt.UserRole)
        if isinstance(payload, dict) and payload.get("kind") == "date":
            operation_ids = set(payload.get("operation_ids") or [])
            self._atualizando_historico = True
            try:
                for indice in range(self.lista_historico.count()):
                    candidato = self.lista_historico.item(indice)
                    dados = candidato.data(Qt.UserRole)
                    if (
                        isinstance(dados, dict)
                        and dados.get("kind") == "operation"
                        and dados.get("operation_id") in operation_ids
                    ):
                        candidato.setCheckState(item.checkState())
            finally:
                self._atualizando_historico = False
        self._on_selecao_historico()

    def _operacoes_historico_marcadas(self):
        operacoes = []
        for indice in range(self.lista_historico.count()):
            item = self.lista_historico.item(indice)
            payload = item.data(Qt.UserRole)
            if (
                isinstance(payload, dict)
                and payload.get("kind") == "operation"
                and item.checkState() == Qt.Checked
            ):
                operacoes.append((item, payload))
        return operacoes

    def _on_selecao_historico(self):
        n = len(self._operacoes_historico_marcadas())
        if n == 0:
            self.btn_restaurar_mod.setEnabled(False)
            self.btn_restaurar_mod.setText("RESTAURAR SELECIONADAS")
        elif n == 1:
            self.btn_restaurar_mod.setEnabled(True)
            self.btn_restaurar_mod.setText("RESTAURAR OPERAÇÃO")
        else:
            self.btn_restaurar_mod.setEnabled(True)
            self.btn_restaurar_mod.setText(f"RESTAURAR OPERAÇÕES ({n})")

    def _on_restaurar_mod_selecionado(self):
        if hasattr(self, "_restauracao_selecionadas"):
            selecionadas = [
                operacao for operacao in self._restauracao_operacoes
                if rlist.operation_key(
                    operacao.get("game_root"), operacao["operation_id"]
                ) in self._restauracao_selecionadas
            ]
            operacoes = [(None, {
                "keys": operacao["keys"],
                "operation_type": operacao["operation_type"],
                "subtitle": _subtitulo_operacao(operacao),
                "game_root": operacao.get("game_root"),
            }) for operacao in selecionadas]
            itens = []
        else:
            operacoes = self._operacoes_historico_marcadas()
            itens = [item for item, _ in operacoes]
        grupos_cliente = _agrupar_chaves_por_cliente(
            [{"game_root": payload.get("game_root"), "keys": payload.get("keys", [])}
             for _, payload in operacoes]
        )
        if not any(grupos_cliente.values()):
            return
        n = len(operacoes)
        total_arquivos = sum(len(chaves) for chaves in grupos_cliente.values())

        msgbox = QMessageBox(self)
        msgbox.setWindowTitle("Restaurar operações")
        msgbox.setIcon(QMessageBox.Warning)
        if n == 1:
            payload = operacoes[0][1]
            nome = payload.get("subtitle")
            if not nome and itens:
                nome = itens[0].data(Qt.UserRole + 1) or itens[0].text().splitlines()[0]
            tipo = _rotulo_tipo_operacao(payload.get("operation_type"))
            msgbox.setText(f"Restaurar operação?\n\n{tipo}\n{nome}")
            msgbox.setInformativeText(
                f"{total_arquivos} arquivo(s) serão restaurados.\n"
                f"Cliente: {payload.get('game_root') or 'não identificado'}"
            )
        else:
            msgbox.setText(f"Restaurar {n} operações selecionadas?")
            msgbox.setInformativeText(
                f"{total_arquivos} arquivo(s) serão restaurados. "
                "As demais operações permanecerão ativas."
            )
        btn_restaurar = msgbox.addButton("RESTAURAR", QMessageBox.AcceptRole)
        btn_cancelar = msgbox.addButton("CANCELAR", QMessageBox.RejectRole)
        msgbox.setDefaultButton(btn_cancelar)
        msgbox.exec()
        if msgbox.clickedButton() != btn_restaurar:
            return

        def tarefa():
            restaurados = []
            falhas = []
            cliente_atual = None
            for cliente, chaves_cliente in grupos_cliente.items():
                if not cliente:
                    cliente_atual = cliente_atual or opt.obter_pasta_jogo_atual()
                res = _restaurar_chaves_historico(
                    chaves_cliente, cliente or cliente_atual
                )
                restaurados.extend(res.get("restaurados", []))
                falhas.extend(res.get("falhas", []))
            if not falhas:
                if len(restaurados) == 1:
                    self.sinais.log_signal.emit(f"[OK] {restaurados[0]} restaurado para o original.")
                else:
                    self.sinais.log_signal.emit(f"[OK] {len(restaurados)} modificações restauradas para o original.")
            else:
                self.sinais.log_signal.emit(f"[INFO] {len(restaurados)} modificações restauradas | {len(falhas)} falhou.")
                for nome, motivo in falhas:
                    self.sinais.log_signal.emit(f"[ERRO] {nome}: {motivo}")
            self.sinais.automod_history_signal.emit(opt.listar_mods_ativos(opt.obter_pasta_jogo_atual()))
        self.executar_em_background(tarefa)

    def acao_injetar_mods(self):
        mods = getattr(self, 'arquivos_mod_selecionados', None)
        if not mods: return
        pasta_jogo = opt.obter_pasta_jogo_atual(exigir_existente=True)
        if not pasta_jogo:
            self.sinais.log_signal.emit(
                "[ERRO] Nenhum cliente AIKA válido configurado.\n"
                "Selecione a pasta do cliente em Configurações."
            )
            return
        operation_id = _novo_operation_id("automod")
        def tarefa():
            snapshot_antes = _snapshot_itens_historico(
                opt.listar_mods_ativos(pasta_jogo)
            )
            r = opt.injetar_mods(
                mods, pasta_jogo,
                log_callback=self.sinais.log_signal.emit,
            )
            if r > 0:
                _anotar_operacao_historico(
                    pasta_jogo, snapshot_antes, {
                        "operation_id": operation_id,
                        "operation_type": "AUTOMOD",
                        "operation_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "operation_client": os.path.basename(os.path.normpath(pasta_jogo)),
                    }
                )
                self.sinais.log_signal.emit(f"[OK] {r} mods injetados. Histórico atualizado.")
            elif r == 0:
                self.sinais.log_signal.emit("[ERRO] 0 mods injetados. Consulte os motivos detalhados acima.")
            else:
                self.sinais.log_signal.emit("[ERRO] ERRO: Falha ao injetar mods ou índice não foi gerado.")
            self.sinais.automod_history_signal.emit(opt.listar_mods_ativos(opt.obter_pasta_jogo_atual()))
        self.executar_em_background(tarefa)

    def selecionar_arquivos_jit(self):
        pasta_jogo = opt.obter_pasta_jogo_atual()
        pasta_base = pasta_jogo if pasta_jogo and os.path.isdir(pasta_jogo) else ""
        f, _ = QFileDialog.getOpenFileNames(self, "Selecionar Texturas .JIT", pasta_base, "AIKA Texture (*.jit)")
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
    def _estado_associacao_jit_ativa(self) -> bool:
        """Associação .JIT considerada ativa (handler nosso presente/completo)."""
        return jit_integration.obter_status_associacao_jit() in ("ATIVA", "DISPONÍVEL")

    def _sincronizar_checkbox_jit(self) -> None:
        """Checkbox reflete o ESTADO REAL do Registro (sem disparar handlers)."""
        try:
            ativa = self._estado_associacao_jit_ativa()
            self.chk_jit_windows.blockSignals(True)
            self.chk_jit_windows.setChecked(ativa)
            self.chk_jit_windows.blockSignals(False)
        except Exception:
            pass

    def acao_toggle_jit_windows(self, state):
        ativar = (state == Qt.Checked.value)
        opt.definir_config("jit_windows_user_set", True)
        try:
            if ativar:
                jit_integration.registrar_integracao_windows()
            else:
                jit_integration.desregistrar_integracao_windows()
            status = jit_integration.obter_status_associacao_jit()
            ok = (
                status in ("ATIVA", "DISPONÍVEL")
                if ativar else status == "INATIVA"
            )
            opt.definir_config("jit_windows_integration", ok and ativar)
            if ok:
                self.sinais.log_signal.emit(
                    "[OK] Integração .JIT com o Windows ATIVADA."
                    if ativar else
                    "[OK] Integração .JIT com o Windows DESATIVADA."
                )
            elif ativar:
                self.sinais.log_signal.emit(
                    "[ERRO] Não foi possível validar a associação .JIT.")
            else:
                self.sinais.log_signal.emit(
                    "[ERRO] Não foi possível remover a associação .JIT.")
        except Exception as e:
            self.sinais.log_signal.emit(f"[ERRO] Falha na integração .JIT: {e}")
        finally:
            # Nunca deixa o checkbox marcado falsamente: reflete o estado real.
            self._sincronizar_checkbox_jit()

    def _garantir_associacao_padrao_jit(self) -> None:
        """Instalação nova: associação .JIT ATIVA por padrão (primeiro uso).

        Respeita escolha explícita do usuário: se ``jit_windows_user_set`` for
        True (usuário já marcou/desmarcou manualmente) nada é feito; a opção
        nunca é reativada silenciosamente após uma escolha explícita.
        """
        try:
            if opt.obter_config("jit_windows_user_set", False):
                return
            if opt.obter_config("jit_windows_integration", False):
                return
            if self._estado_associacao_jit_ativa():
                opt.definir_config("jit_windows_integration", True)
                return
            jit_integration.registrar_integracao_windows()
            if self._estado_associacao_jit_ativa():
                opt.definir_config("jit_windows_integration", True)
                self.sinais.log_signal.emit(
                    "[OK] Associação .JIT ativada por padrão.")
        except Exception as e:
            self.sinais.log_signal.emit(
                f"[AVISO] Não foi possível ativar a associação .JIT padrão: {e}")
        finally:
            self._sincronizar_checkbox_jit()

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
                self.sinais.automod_history_signal.emit(opt.listar_mods_ativos(opt.obter_pasta_jogo_atual()))
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
            pasta_jogo = opt.obter_pasta_jogo_atual()
            s, m = opt.substituir_audio_customizado(novo, alvo, pasta_jogo)
            self.sinais.log_signal.emit("[OK] Sucesso! Áudio injetado." if s else f"[ERRO] ERRO: {m}")
        self.executar_em_background(tarefa)

    def acao_restaurar_audio(self):
        alvo = getattr(self, 'arquivo_alvo_jogo', None)
        if not alvo: return
        def tarefa():
            pasta_jogo = opt.obter_pasta_jogo_atual()
            s, m = opt.restaurar_audio_original(alvo, pasta_jogo)
            self.sinais.log_signal.emit(f"[OK] {m}" if s else f"[ERRO] {m}")
        self.executar_em_background(tarefa)

    def acao_restaurar_tudo(self):
        def tarefa():
            self.sinais.log_signal.emit("[INFO] INICIANDO RESTAURAÇÃO EM LOTES (Poupando HDD)...")
            pasta_jogo = opt.obter_pasta_jogo_atual()
            s, m = opt.restaurar_tudo_jogo(pasta_jogo)
            self.sinais.log_signal.emit(f"[OK] {m}" if s else f"[ERRO] {m}")
            if s:
                opt.limpar_historico_automod(pasta_jogo)
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
            try:
                if opt.alterar_dns(p):
                    rotulo = "Restaurar Padrão" if p == "Padrao" else p
                    self.sinais.log_signal.emit(f"[OK] DNS {rotulo} aplicado nos adaptadores de rede físicos ativos.")
                    self.sinais.rede_alterada_signal.emit()
                else:
                    self.sinais.log_signal.emit(
                        f"[ERRO] Falha ao aplicar o DNS ({p}). Verifique privilégios de administrador e o adaptador de rede ativo.")
            except Exception as e:
                self.sinais.log_signal.emit(f"[ERRO] Falha ao aplicar o DNS ({p}): {e}")
        self.executar_em_background(tarefa)

    def acao_gamebar(self):
        def tarefa():
            try:
                if opt.desativar_game_bar():
                    self.sinais.log_signal.emit("[OK] Game Bar/GameDVR desativada; comportamento de tela cheia do Windows ajustado.")
                else:
                    self.sinais.log_signal.emit("[ERRO] Falha ao desativar a Game Bar (verifique privilégios/permissões de Registro).")
            except Exception as e:
                self.sinais.log_signal.emit(f"[ERRO] Falha ao desativar a Game Bar: {e}")
        self.executar_em_background(tarefa)

    def acao_weapon(self):
        def tarefa():
            pasta_jogo = opt.obter_pasta_jogo_atual()
            if not pasta_jogo:
                self.sinais.log_signal.emit(
                    "[ERRO] Nenhum cliente AIKA válido configurado para remover efeitos."
                )
                return
            operation_id = _novo_operation_id("remove_polluted_effects")
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            metadados = {
                "operation_id": operation_id,
                "operation_type": "REMOVE_POLLUTED_EFFECTS",
                "operation_timestamp": timestamp,
                "operation_client": os.path.basename(os.path.normpath(pasta_jogo)),
            }

            def persistir(arquivos):
                metadados_lote = dict(metadados)
                metadados_lote["operation_source"] = _resumo_arquivos_removidos(
                    arquivos
                )
                return _registrar_remocao_historico(
                    pasta_jogo, arquivos, metadados_lote
                )

            resultado = opt.remover_arquivos_com_backup(
                pasta_jogo, opt.EFEITOS_POLUIDOS_ARQUIVOS,
                persistir_operacao=persistir,
            )
            status = resultado.get("status")
            if status == "removed":
                arquivos = resultado.get("files", [])
                self.sinais.log_signal.emit(
                    f"[OK] Backups criados/verificados: {len(arquivos)} arquivo(s)."
                )
                self.sinais.log_signal.emit(
                    f"[OK] Efeitos poluídos removidos: {len(arquivos)} arquivo(s)."
                )
                self.sinais.log_signal.emit(
                    "[OK] Operação registrada no histórico de Restauração."
                )
                self.sinais.automod_history_signal.emit(
                    opt.listar_mods_ativos(pasta_jogo)
                )
            elif status == "already_removed":
                self.sinais.log_signal.emit(
                    "[INFO] Efeitos poluídos já estão removidos."
                )
            else:
                self.sinais.log_signal.emit(
                    f"[ERRO] Erro ao remover efeitos poluídos: {resultado.get('error')}"
                )
        self.executar_em_background(tarefa)

    def acao_tcp_nodelay(self):
        def tarefa():
            try:
                if opt.otimizar_tcp_nodelay():
                    self.sinais.log_signal.emit("[OK] TCP NoDelay aplicado no adaptador de rede físico ativo.")
                else:
                    self.sinais.log_signal.emit(
                        "[ERRO] TCP NoDelay não aplicado: adaptador de rede ativo não identificado ou sem permissão (nenhuma interface alterada).")
            except Exception as e:
                self.sinais.log_signal.emit(f"[ERRO] Falha ao aplicar TCP NoDelay: {e}")
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

            # Integração .JIT com Windows — estado REAL do Registro (checkbox
            # não pode divergir da associação efetiva; sem disparar handlers).
            self._sincronizar_checkbox_jit()

            # Cliente do AIKA (fonte canônica game_client_path).
            self._atualizar_card_cliente_aika()
        except Exception:
            pass

    def _atualizar_card_cliente_aika(self):
        """Reflete o cliente canônico no card da página Configurações."""
        try:
            caminho = opt.obter_pasta_jogo_atual(exigir_existente=True)
            if not caminho:
                self.lbl_cliente_aika_caminho.setText("Não configurado")
                self.lbl_cliente_aika_caminho.setToolTip("")
                self.btn_cliente_aika.setText("SELECIONAR PASTA")
                return
            metrics = self.lbl_cliente_aika_caminho.fontMetrics()
            elidido = metrics.elidedText(caminho, Qt.ElideMiddle, 420)
            self.lbl_cliente_aika_caminho.setText(elidido)
            self.lbl_cliente_aika_caminho.setToolTip(caminho)
            self.btn_cliente_aika.setText("ALTERAR")
        except Exception:
            pass

    def selecionar_cliente_aika(self):
        """Seleciona/valida a pasta do cliente do AIKA e persiste em game_client_path."""
        atual = opt.obter_pasta_jogo_atual(exigir_existente=True)
        pasta = QFileDialog.getExistingDirectory(
            self, "Selecionar Pasta do Cliente do AIKA",
            atual or opt.PASTA_JOGO_PADRAO,
        )
        if not pasta:
            return
        if not opt.validar_pasta_cliente_aika(pasta):
            QMessageBox.warning(
                self, "Cliente Inválido",
                "A pasta selecionada não parece ser um cliente compatível do AIKA.",
            )
            return
        if not opt.definir_config("game_client_path", pasta):
            QMessageBox.warning(
                self, "Erro",
                "Não foi possível salvar a pasta do cliente do AIKA.",
            )
            return
        self._atualizar_card_cliente_aika()
        self.atualizar_log(f"[OK] Cliente do AIKA definido: {pasta}")

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
        self._sets_worker.log.connect(self.sinais.log_signal.emit)
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
            f"Armaduras 3D Geradas (.MSH → .OBJ): {stats.get('msh_convertidos', 0)}\n"
            f"Armas 3D Geradas (.MS3 → .OBJ): {stats.get('ms3_convertidos', 0)}\n"
            f"Famílias de Armadura Organizadas: {stats.get('familias_criadas', 0)}\n"
            f"Pastas Antigas Agrupadas: {stats.get('pastas_legadas_migradas', 0)}\n"
            f"Falhas de Conversão 3D: {stats.get('falhas_3d', 0)}\n"
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
            return
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

    # ========================================================
    # INJETOR DE SETS — AÇÕES
    # ========================================================
    def _invalidar_preparacao_injetor(self):
        """Impede reutilizar staging depois de trocar doador ou alvo."""
        self._inj_preparado = False
        self._inj_mapeados = None
        self._inj_ignorados = None
        self._inj_staging = None
        self._inj_cliente_simulado = None
        self._inj_simulacao_total = 0

    @staticmethod
    def _normalizar_cliente_destino_injetor(pasta):
        if not pasta:
            return None
        return os.path.normcase(
            os.path.realpath(os.path.abspath(os.path.normpath(str(pasta))))
        )

    @classmethod
    def _validar_cliente_destino_injetor(cls, pasta):
        """Validação mínima de uma instalação real, sem alterar config global."""
        caminho = cls._normalizar_cliente_destino_injetor(pasta)
        if not caminho or not os.path.isdir(caminho):
            return None, "A pasta selecionada não existe."
        pastas_nativas = ("Mesh", "Objects", "Texture")
        presentes = [
            nome for nome in pastas_nativas
            if os.path.isdir(os.path.join(caminho, nome))
        ]
        if not presentes:
            return None, (
                "A pasta selecionada parece ser uma pasta organizada de assets, "
                "não uma instalação válida do AIKA. Selecione a raiz do cliente "
                "que contém Mesh, Objects ou Texture."
            )
        return caminho, None

    def selecionar_cliente_destino_injetor(self):
        pasta = QFileDialog.getExistingDirectory(
            self, "Selecionar Cliente Destino da Injeção"
        )
        if not pasta:
            return
        cliente, erro = self._validar_cliente_destino_injetor(pasta)
        if erro:
            self._inj_cliente_destino = None
            self._inj_cliente_simulado = None
            self._inj_simulacao_total = 0
            QMessageBox.warning(self, "Cliente Inválido", erro)
            self.lbl_info_cliente_injetor.setText(f"ERRO: {erro}")
            self.lbl_info_cliente_injetor.setStyleSheet(
                "color: #FF4444; font-size: 12px; "
                "background: transparent; border: none;"
            )
            self._atualizar_botoes_injetor()
            return

        alterado = cliente != self._inj_cliente_destino
        self._inj_cliente_destino = cliente
        if alterado:
            self._inj_cliente_simulado = None
            self._inj_simulacao_total = 0
        self.lbl_info_cliente_injetor.setText(
            f"Cliente: {cliente}\nStatus: CLIENTE VÁLIDO"
        )
        self.lbl_info_cliente_injetor.setStyleSheet(
            "color: #00FF88; font-size: 12px; "
            "background: transparent; border: none;"
        )
        if alterado and self._inj_preparado:
            self.terminal_injetor.append(
                "[INFO] O Cliente Destino foi alterado. Execute a simulação novamente."
            )
        self._atualizar_botoes_injetor()

    def _on_modo_injetor_alterado(self):
        """Troca o fluxo inteiro sem reaproveitar seleção ou staging anterior."""
        modo = "weapon" if self.rb_inj_armas.isChecked() else "set"
        if getattr(self, "_inj_modo", None) == modo:
            return
        self._inj_modo = modo
        self._inj_doador_info = None
        self._inj_alvo_info = None
        self._invalidar_preparacao_injetor()
        self.lbl_info_doador.setText("Nenhuma pasta selecionada.")
        self.lbl_info_alvo.setText("Nenhuma pasta selecionada.")
        estilo_vazio = "color: #8A8A9A; font-size: 12px; background: transparent; border: none;"
        self.lbl_info_doador.setStyleSheet(estilo_vazio)
        self.lbl_info_alvo.setStyleSheet(estilo_vazio)
        self.terminal_injetor.clear()

        if modo == "weapon":
            self.lbl_inj_t.setText("Injetor de Armas")
            self.lbl_inj_d.setText(
                "Transforme uma arma doadora em outra arma da mesma classe e tipo. "
                "Somente .MS3 e .JIT entram neste modo; os IDs são escolhidos independentemente dos sets."
            )
            titulo_doador, titulo_alvo = "ARMA DOADORA", "ARMA ALVO"
        else:
            self.lbl_inj_t.setText("Injetor de Sets")
            self.lbl_inj_d.setText(
                "Use a aparência de uma variante de armadura em outro set da mesma classe. "
                "Somente .MSH e .JIT entram neste modo."
            )
            titulo_doador, titulo_alvo = "APARÊNCIA DOADORA", "SET ALVO"

        self.lbl_inj_doador_titulo.findChildren(QLabel)[-1].setText(titulo_doador)
        self.lbl_inj_alvo_titulo.findChildren(QLabel)[-1].setText(titulo_alvo)
        self._atualizar_botoes_injetor()

    def _formatar_info_asset_injetor(self, info):
        if info.get("asset_kind") == "weapon":
            origem = (
                "estrutura reconhecida" if info.get("manifest_inferred")
                else "manifesto validado"
            )
            return (
                f"Pasta: {info['pasta']}\n"
                f"Tipo: Arma {info['weapon_type']} | ID: {info['weapon_id']}\n"
                f"Classe: {info['class_name']} ({info['weapon_prefix']})\n"
                f"Modelos MS3: {info['total_ms3']} | "
                f"Texturas JIT: {info['total_textures']} | "
                f"Efeitos EF: {info['total_effects']}\n"
                f"Status: VÁLIDO ({origem})"
            )
        rotulos = {
            "completo_6_partes": "set completo antigo (6 partes)",
            "completo_5_partes": "set completo atual (5 partes)",
            "aparencia_individual": "aparência individual (1 parte)",
            "aparencia_parcial": "aparência parcial",
            "somente_textura": "somente textura",
        }
        partes = ", ".join(info.get("available_parts") or []) or "nenhuma MSH"
        return (
            f"Pasta: {info['pasta']}\n"
            f"Tipo: {rotulos.get(info.get('appearance_scope'), 'set de armadura')}\n"
            f"Classe: {info['class_name']} ({info['class_code']})\n"
            f"Família: {info['visual_family_id']} | Variante: {info['variant_id']} | "
            f"Set ID: {info['set_id']}\n"
            f"Partes MSH: {partes}\n"
            f"Meshes MSH: {info['total_meshes']} | "
            f"Texturas JIT: {info['total_textures']} | "
            f"Efeitos EF: {info['total_effects']}\n"
            "Status: VÁLIDO"
        )

    def selecionar_pasta_doador(self):
        pasta = QFileDialog.getExistingDirectory(self, "Selecionar Pasta Doadora")
        if not pasta:
            return
        self._invalidar_preparacao_injetor()
        info, erro = sinj.SetInjectorWorker().validar_pasta(
            pasta, expected_kind=self._inj_modo
        )
        if erro:
            QMessageBox.warning(self, "Pasta Inválida", f"Doador: {erro}")
            self.lbl_info_doador.setText(f"ERRO: {erro}")
            self.lbl_info_doador.setStyleSheet("color: #FF4444; font-size: 12px; background: transparent; border: none;")
            self._inj_doador_info = None
        else:
            self._inj_doador_info = info
            self.lbl_info_doador.setText(self._formatar_info_asset_injetor(info))
            self.lbl_info_doador.setStyleSheet("color: #00FF88; font-size: 12px; background: transparent; border: none;")
        self._atualizar_botoes_injetor()

    def selecionar_pasta_alvo(self):
        pasta = QFileDialog.getExistingDirectory(self, "Selecionar Pasta Alvo")
        if not pasta:
            return
        self._invalidar_preparacao_injetor()
        info, erro = sinj.SetInjectorWorker().validar_pasta(
            pasta, expected_kind=self._inj_modo
        )
        if erro:
            QMessageBox.warning(self, "Pasta Inválida", f"Alvo: {erro}")
            self.lbl_info_alvo.setText(f"ERRO: {erro}")
            self.lbl_info_alvo.setStyleSheet("color: #FF4444; font-size: 12px; background: transparent; border: none;")
            self._inj_alvo_info = None
        else:
            self._inj_alvo_info = info
            self.lbl_info_alvo.setText(self._formatar_info_asset_injetor(info))
            self.lbl_info_alvo.setStyleSheet("color: #00FF88; font-size: 12px; background: transparent; border: none;")
        self._atualizar_botoes_injetor()

    def _atualizar_botoes_injetor(self):
        ambos = self._inj_doador_info is not None and self._inj_alvo_info is not None
        livre = not self._inj_busy
        self.rb_inj_sets.setEnabled(livre)
        self.rb_inj_armas.setEnabled(livre)
        self.btn_sel_doador.setEnabled(livre)
        self.btn_sel_alvo.setEnabled(livre)
        self.btn_sel_cliente_injetor.setEnabled(livre)
        nome = "ARMA" if self._inj_modo == "weapon" else "SET"
        self.btn_preparar.setText(f"PREPARAR {nome}" if ambos else "PREPARAR")
        self.btn_preparar.setEnabled(ambos and livre)
        cliente_valido = bool(self._inj_cliente_destino)
        simulacao_valida = (
            cliente_valido
            and self._inj_cliente_simulado == self._inj_cliente_destino
        )
        self.btn_simular.setEnabled(
            self._inj_preparado and cliente_valido and livre
        )
        self.btn_injetar.setEnabled(
            self._inj_preparado and simulacao_valida and livre
        )

    def _executar_operacao_injetor(self, acao, mensagem, tarefa):
        """Inicia backend do Injetor sem permitir acesso à UI pelo worker."""
        self._inj_busy = True
        self._inj_operacao = acao
        self.terminal_injetor.clear()
        self.terminal_injetor.append(mensagem)
        self._atualizar_botoes_injetor()

        iniciado = self.executar_em_background(
            tarefa,
            resultado_callback=self._on_injetor_worker_resultado,
            erro_callback=self._on_injetor_worker_erro,
            finalizado_callback=self._on_injetor_worker_finalizado,
        )
        if not iniciado:
            self._inj_busy = False
            self._inj_operacao = None
            self.terminal_injetor.append(
                "Não foi possível iniciar: existe outra tarefa em andamento."
            )
            self._atualizar_botoes_injetor()

    def _on_injetor_worker_erro(self, erro):
        """Exibe exceções inesperadas do worker exclusivamente na UI thread."""
        acao = self._inj_operacao or "operação"
        if acao == "preparar":
            self._inj_preparado = False
            self._inj_mapeados = None
            self._inj_ignorados = None
        self.terminal_injetor.append(f"ERRO: {erro}")
        self.sinais.log_signal.emit(
            f"[ERRO] Injetor de Sets/Armas ({acao}): {erro}"
        )

    def _on_injetor_worker_finalizado(self):
        """Restaura os controles quando o worker encerra normalmente ou com erro."""
        self._inj_busy = False
        self._inj_operacao = None
        self._atualizar_botoes_injetor()

    def _on_injetor_worker_resultado(self, payload):
        """Aplica resultados do backend na thread principal do Qt."""
        if not isinstance(payload, dict):
            self._on_injetor_worker_erro("Resposta inválida da tarefa em background.")
            return

        acao = payload.get("acao")
        erro = payload.get("erro")
        if erro:
            if acao == "preparar":
                self._inj_preparado = False
                self._inj_mapeados = None
                self._inj_ignorados = None
            if "APARÊNCIAS INCOMPATÍVEIS" in erro:
                self._inj_staging = None
                self._inj_cliente_simulado = None
                self._inj_simulacao_total = 0
                self.terminal_injetor.setPlainText(erro)
            else:
                self.terminal_injetor.append(f"ERRO: {erro}")
            self.sinais.log_signal.emit(
                f"[ERRO] Injetor de Sets/Armas ({acao or 'operação'}): {erro}"
            )
            return

        if acao == "preparar":
            manifesto = payload["manifesto"]
            ignorados = payload["ignorados"]
            doador_info = payload["doador_info"]
            alvo_info = payload["alvo_info"]
            self._inj_mapeados = payload["mapeados"]
            self._inj_ignorados = ignorados
            self._inj_staging = payload["staging"]
            self._inj_preparado = True

            if doador_info.get("asset_kind") == "weapon":
                titulo_preparado = "ARMA PREPARADA"
                doador_descricao = (
                    f"{doador_info['class_name']} "
                    f"{doador_info['weapon_type']} {doador_info['weapon_id']}"
                )
                alvo_descricao = (
                    f"{alvo_info['class_name']} "
                    f"{alvo_info['weapon_type']} {alvo_info['weapon_id']}"
                )
            else:
                titulo_preparado = "SET PREPARADO"
                doador_descricao = (
                    f"{doador_info['class_name']} Set {doador_info['set_id']}"
                )
                alvo_descricao = (
                    f"{alvo_info['class_name']} Set {alvo_info['set_id']}"
                )

            linhas = [
                f"=== {titulo_preparado} ===",
                f"Doador: {doador_descricao}",
                f"Alvo:   {alvo_descricao}",
                f"Arquivos a substituir: {manifesto['total_preparados']}",
                "Destinos na base compartilhada 01: "
                f"{manifesto.get('total_destinos_compartilhados', 0)}",
                "Sincronização da base da família: "
                f"{'SIM' if manifesto.get('sincronizacao_base_familia') else 'NÃO'}",
                "Arquivos destinados à base: "
                f"{manifesto.get('total_sincronizacao_base', 0)}",
                "Arquivos destinados à variante: "
                f"{manifesto.get('total_variante_alvo', manifesto['total_preparados'])}",
                f"Arquivos ignorados: {len(ignorados)}",
                "",
            ]
            for arquivo in manifesto["files"]:
                if arquivo.get("asset_kind") == "weapon":
                    if arquivo["extensao"] == ".ms3":
                        detalhe = "modelo 3D da arma"
                    elif arquivo.get("subtipo") == "effect":
                        detalhe = "textura de efeito EF"
                    else:
                        detalhe = "textura base"
                else:
                    detalhe = f"{arquivo['tipo']} parte {arquivo['parte']}"
                    if arquivo.get("destino_compartilhado"):
                        detalhe += (
                            " — BASE COMPARTILHADA "
                            f"{arquivo.get('set_destino_fisico')} "
                            f"(alvo selecionado {arquivo.get('set_alvo_logico')})"
                        )
                    if arquivo.get("sincronizacao_base_familia"):
                        detalhe += " — SINCRONIZAÇÃO DA BASE DA FAMÍLIA"
                linhas.append(
                    f"  {arquivo['doador_basename']} → "
                    f"{arquivo['alvo_basename']} "
                    f"({detalhe})"
                )
            for remocao in manifesto.get("efeitos_remover", []):
                linhas.extend([
                    "",
                    f"[REMOVER EF] {remocao['alvo_basename']}",
                    f"Motivo: {remocao['motivo']}",
                ])
            if ignorados:
                linhas.extend(["", "--- IGNORADOS ---"])
                for ignorado in ignorados:
                    linhas.append(
                        f"  {ignorado['arquivo']['basename']}: "
                        f"{ignorado['motivo']}"
                    )
            linhas.extend(["", "Status: PRONTO PARA SIMULAR"])
            self.terminal_injetor.setPlainText("\n".join(linhas))
            self.sinais.log_signal.emit(
                f"[OK] {titulo_preparado.title()}: {manifesto['total_preparados']} "
                "arquivos em staging."
            )

        elif acao == "simular":
            plano = payload["plano"]
            cliente_simulado = self._normalizar_cliente_destino_injetor(
                payload.get("cliente_destino") or plano.get("pasta_jogo")
            )
            self._inj_cliente_simulado = cliente_simulado
            self._inj_simulacao_total = int(plano.get("total", 0))
            linhas = [
                "=== SIMULAÇÃO ===",
                f"Aparência doadora: {self._inj_doador_info['pasta']}",
                f"Aparência alvo: {self._inj_alvo_info['pasta']}",
                f"CLIENTE DESTINO: {plano['pasta_jogo']}",
                f"Arquivos indexados: {plano['total_indexados']}",
                f"Arquivos a substituir: {plano['total']}",
                "Total de destinos afetados: "
                f"{plano.get('total_destinos_afetados', plano['total'])}",
                "Destinos na base compartilhada 01: "
                f"{plano.get('total_destinos_compartilhados', 0)}",
                "Sincronização da base da família: "
                f"{'SIM' if plano.get('sincronizacao_base_familia') else 'NÃO'}",
                f"Arquivos para a base: {plano.get('total_sincronizacao_base', 0)}",
                f"Arquivos para a variante: {plano.get('total_variante_alvo', plano['total'])}",
                "Ignorados (não encontrados no cliente): "
                f"{len(plano['ignorados'])}",
                "",
            ]
            for substituicao in plano["substituicoes"]:
                linhas.append(
                    f"  {substituicao['doador_basename']} → "
                    f"{substituicao['destino_cliente']}"
                )
                if substituicao.get("destino_compartilhado"):
                    linhas.append(
                        "    [ATENÇÃO] Destino físico compartilhado: "
                        f"base {substituicao.get('set_destino_fisico')} "
                        f"para completar o alvo {substituicao.get('set_alvo_logico')}."
                    )
                if substituicao.get("sincronizacao_base_familia"):
                    linhas.append(
                        "    [SINCRONIZAÇÃO DA BASE DA FAMÍLIA] "
                        "este destino pertence à base 01."
                    )
                estado_backup = (
                    "(já existe)" if substituicao["backup_existente"]
                    else "(será criado)"
                )
                linhas.append(
                    f"    Backup: {substituicao['caminho_backup']} "
                    f"{estado_backup}"
                )
            for remocao in plano.get("remocoes_ef", []):
                estado_backup = (
                    "(já existe)" if remocao["backup_existente"]
                    else "(será criado)"
                )
                linhas.extend([
                    "",
                    "[REMOVER EF]",
                    remocao["destino_cliente"],
                    f"Motivo: {remocao['motivo']}",
                    f"Backup: {remocao['caminho_backup']} {estado_backup}",
                ])
            if plano["ignorados"]:
                linhas.extend(["", "--- NÃO ENCONTRADOS NO CLIENTE ---"])
                for ignorado in plano["ignorados"]:
                    linhas.append(
                        f"  {ignorado['basename']}: {ignorado['motivo']}"
                    )
            if plano["total"] == 0:
                linhas.extend([
                    "",
                    "ATENÇÃO: nenhum destino foi encontrado.",
                    "Confirme se 'Cliente analisado' é a instalação correta do AIKA.",
                ])
            self.terminal_injetor.setPlainText("\n".join(linhas))
            self.sinais.log_signal.emit(
                f"[OK] Simulação concluída: {plano['total']} arquivos seriam substituídos."
            )

        elif acao == "injetar":
            resultado = payload["resultado"]
            linhas = [
                "=== INJEÇÃO CONCLUÍDA ===",
                f"Substituídos: {resultado['total_substituidos']}",
                f"Efeitos EF removidos: {resultado.get('total_efeitos_removidos', 0)}",
                "Destinos na base compartilhada 01: "
                f"{resultado.get('total_destinos_compartilhados', 0)}",
                "Sincronização da base da família: "
                f"{'SIM' if resultado.get('sincronizacao_base_familia') else 'NÃO'}",
                "Atualizados na base: "
                f"{resultado.get('total_sincronizacao_base', 0)}",
                "Atualizados na variante: "
                f"{resultado.get('total_variante_alvo', resultado['total_substituidos'])}",
                f"Falhas: {resultado['total_falhas']}",
            ]
            for substituido in resultado["substituidos"]:
                linhas.append(
                    f"  ✓ {substituido['doador_basename']} → "
                    f"{substituido['destino']}"
                )
                if substituido.get("destino_compartilhado"):
                    linhas.append(
                        "    [BASE COMPARTILHADA] "
                        f"{substituido.get('set_destino_fisico')} "
                        f"completa o alvo {substituido.get('set_alvo_logico')}"
                    )
                if substituido.get("sincronizacao_base_familia"):
                    linhas.append("    [SINCRONIZAÇÃO DA BASE DA FAMÍLIA]")
            for removido in resultado.get("efeitos_removidos", []):
                linhas.append(f"  ✓ [REMOVER EF] {removido['destino']}")
                if removido.get("sincronizacao_base_familia"):
                    linhas.append("    [SINCRONIZAÇÃO DA BASE DA FAMÍLIA]")
            for falha in resultado["falhas"]:
                linhas.append(f"  ✗ {falha['basename']}: {falha['motivo']}")
            self.terminal_injetor.setPlainText("\n".join(linhas))
            self.sinais.log_signal.emit(
                f"[OK] Injeção concluída: "
                f"{resultado['total_substituidos']} substituídos, "
                f"{resultado.get('total_efeitos_removidos', 0)} efeitos EF removidos, "
                f"{resultado['total_falhas']} falhas."
            )
            self.sinais.automod_history_signal.emit(payload["historico"])

        self._atualizar_botoes_injetor()

    def acao_preparar_set(self):
        if not self._inj_doador_info or not self._inj_alvo_info:
            return
        staging = os.path.join(
            tempfile.gettempdir(), f"aika_injetor_{self._inj_modo}_staging"
        )
        self._inj_preparado = False
        self._inj_mapeados = None
        self._inj_ignorados = None
        self._inj_cliente_simulado = None
        self._inj_simulacao_total = 0
        doador_info = self._inj_doador_info
        alvo_info = self._inj_alvo_info

        def tarefa():
            worker = sinj.SetInjectorWorker()
            manifesto, ignorados, erro = worker.preparar(
                doador_info, alvo_info, staging
            )
            if erro:
                return {"acao": "preparar", "erro": erro}

            mapeados, _ = sinj.criar_mapa_para_infos(
                doador_info, alvo_info
            )
            return {
                "acao": "preparar",
                "erro": None,
                "manifesto": manifesto,
                "ignorados": ignorados,
                "mapeados": mapeados,
                "staging": staging,
                "doador_info": doador_info,
                "alvo_info": alvo_info,
            }

        if self._inj_modo == "weapon":
            mensagem = "Preparando arma (.MS3/.JIT)..."
        else:
            mensagem = "Preparando set (.MSH/.JIT)..."
        self._executar_operacao_injetor("preparar", mensagem, tarefa)

    def acao_simular_injecao(self):
        if not self._inj_preparado or not self._inj_mapeados:
            nome = "a arma" if self._inj_modo == "weapon" else "o set"
            QMessageBox.warning(self, "Preparação Necessária", f"Prepare {nome} antes de simular.")
            return
        cliente_destino, erro_cliente = self._validar_cliente_destino_injetor(
            self._inj_cliente_destino
        )
        if erro_cliente:
            QMessageBox.warning(
                self, "Cliente Destino Necessário",
                "Selecione o Cliente Destino da Injeção."
            )
            return
        self._inj_cliente_simulado = None
        self._inj_simulacao_total = 0
        mapeados = self._inj_mapeados

        def tarefa():
            worker = sinj.SetInjectorWorker()
            plano, erro = worker.simular(mapeados, cliente_destino)
            return {
                "acao": "simular", "erro": erro, "plano": plano,
                "cliente_destino": cliente_destino,
            }

        self._executar_operacao_injetor(
            "simular", "Simulando injeção...", tarefa
        )

    def acao_injetar_set(self):
        if not self._inj_preparado or not self._inj_mapeados or not self._inj_staging:
            nome = "a arma" if self._inj_modo == "weapon" else "o set"
            QMessageBox.warning(self, "Preparação Necessária", f"Prepare {nome} antes de injetar.")
            return
        cliente_destino, erro_cliente = self._validar_cliente_destino_injetor(
            self._inj_cliente_destino
        )
        if erro_cliente:
            QMessageBox.warning(
                self, "Cliente Destino Necessário",
                "Selecione o Cliente Destino da Injeção."
            )
            return
        if cliente_destino != self._inj_cliente_simulado:
            QMessageBox.warning(
                self, "Simulação Necessária",
                "O Cliente Destino foi alterado ou ainda não foi simulado. "
                "Execute a simulação novamente."
            )
            return
        if opt.jogo_esta_aberto():
            QMessageBox.warning(self, "Jogo Aberto", "Feche o AIKA antes de realizar a injeção.")
            return

        compartilhados = sum(
            1 for item in self._inj_mapeados
            if item.get("destino_compartilhado")
            or item.get("alvo", {}).get("destino_compartilhado")
        )
        aviso_compartilhado = ""
        if compartilhados:
            aviso_compartilhado = (
                f"\n\n[ATENÇÃO] {compartilhados} arquivo(s) serão gravados "
                "na variante-base 01 da família. Esse arquivo físico pode ser "
                "compartilhado por outras variantes da mesma família."
            )
        sincronizacao_base = any(
            item.get("sincronizacao_base_familia")
            or item.get("alvo", {}).get("sincronizacao_base_familia")
            for item in self._inj_mapeados
        )
        aviso_sincronizacao = ""
        if sincronizacao_base:
            aviso_sincronizacao = (
                "\n\n[SINCRONIZAÇÃO DA BASE DA FAMÍLIA]\n"
                "A variante alvo será aplicada e a base 01 da mesma família "
                "também será atualizada para garantir consistência visual.\n"
                "Isso pode fazer a base e a variante ficarem com a mesma aparência."
            )
        resp = QMessageBox.question(
            self, "Confirmar Injeção",
            "Cliente que será modificado:\n"
            f"{cliente_destino}\n\n"
            f"{self._inj_simulacao_total} arquivos serão substituídos.\n"
            "Backups serão criados antes da operação.\n\n"
            f"Deseja continuar?{aviso_sincronizacao}{aviso_compartilhado}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if resp != QMessageBox.Yes:
            return

        mapeados = self._inj_mapeados
        staging = self._inj_staging
        modo_injecao = self._inj_modo
        doador_info = self._inj_doador_info
        alvo_info = self._inj_alvo_info
        operation_id = _novo_operation_id(
            "weapon_injection" if modo_injecao == "weapon" else "set_injection"
        )

        def tarefa():
            worker = sinj.SetInjectorWorker()
            resultado, erro = worker.injetar(
                mapeados, staging, cliente_destino
            )
            if erro:
                return {"acao": "injetar", "erro": erro}
            if modo_injecao == "weapon":
                origem_id = f"{doador_info.get('weapon_type') or ''}{doador_info.get('weapon_id') or ''}"
                alvo_id = f"{alvo_info.get('weapon_type') or ''}{alvo_info.get('weapon_id') or ''}"
                tipo_operacao = "WEAPON_INJECTION"
            else:
                origem_id = doador_info.get("set_id")
                alvo_id = alvo_info.get("set_id")
                tipo_operacao = "SET_INJECTION"
            destinos = [
                item["destino"]
                for item in resultado.get("substituidos", [])
                + resultado.get("efeitos_removidos", [])
            ]
            chaves = [
                os.path.relpath(destino, cliente_destino).replace("\\", "/").lower()
                for destino in destinos
            ]
            _anotar_operacao_historico(
                cliente_destino, {}, {
                    "operation_id": operation_id,
                    "operation_type": tipo_operacao,
                    "operation_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "operation_source": origem_id,
                    "operation_target": alvo_id,
                    "operation_class": doador_info.get("class_name"),
                    "operation_base_sync": bool(resultado.get("sincronizacao_base_familia")),
                    "operation_client": os.path.basename(os.path.normpath(cliente_destino)),
                },
                chaves_exatas=chaves,
            )
            return {
                "acao": "injetar",
                "erro": None,
                "resultado": resultado,
                "historico": opt.listar_mods_ativos(cliente_destino),
            }

        self._executar_operacao_injetor(
            "injetar", "Injetando arquivos no AIKA...", tarefa
        )

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
        if hasattr(self, 'pedras_page'):
            self.pedras_page.request_shutdown()
        self._tentar_finalizar_shutdown()

    def _tentar_finalizar_shutdown(self):
        if self._shutdown_finalizando:
            return
        pedras_worker = (
            self.pedras_page.active_thread if hasattr(self, 'pedras_page') else None
        )
        workers = (self.worker, self._sets_worker, self._jit_worker,
                   self._diag_worker, self._qos_worker, self._watchdog,
                   pedras_worker)
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
        opt.limpar_pasta_temp_audio()

        # Rotina pesada (restaurar Booster + remover QoS) em background,
        # nunca na thread da GUI — impede "Nao Respondendo" ao fechar.
        # A referencia fica em self._shutdown_worker para a QThread nao ser
        # coletada pelo GC enquanto ainda roda.
        worker = TarefaWorker(_rotina_cleanup_shutdown)
        self._shutdown_worker = worker
        worker.finished.connect(self._concluir_fechamento)
        worker.finished.connect(worker.deleteLater)
        worker.start()

        # Seguranca: se o worker demorar, a janela fecha dentro do limite.
        QTimer.singleShot(SHUTDOWN_CLEANUP_TIMEOUT_MS, self._concluir_fechamento)

    def _concluir_fechamento(self):
        if getattr(self, "_shutdown_closed", False):
            return
        self._shutdown_closed = True
        try:
            self.close()
        except Exception:
            pass

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


def _aguardar_cleanup_shutdown(window):
    """Espera (limitada) o worker de cleanup ao sair do event loop.

    Chamado via app.aboutToQuit: a janela já está fechada/oculta, portanto
    uma espera curta aqui é invisível para o usuário e garante que o processo
    nunca termine com a QThread de cleanup ainda viva (evita crash no teardown).
    """
    worker = getattr(window, "_shutdown_worker", None)
    if worker is None:
        return
    try:
        if worker.isRunning():
            worker.wait(8000)  # teto: nunca espera indefinidamente
    except RuntimeError:
        pass  # objeto C++ já destruído (deleteLater) — nada a aguardar


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
        # Instalação nova: associação .JIT ativa por padrão (primeiro uso real;
        # respeita escolha explícita do usuário — nunca reativa após desmarcar).
        window._garantir_associacao_padrao_jit()
        # Cleanup de Booster/QoS roda em QThread; ao sair do loop, aguarda
        # no maximo 8s (janela ja fechada — sem risco de "Nao Respondendo").
        app.aboutToQuit.connect(lambda: _aguardar_cleanup_shutdown(window))
        if startup_flag and opt.obter_config("start_minimized", False):
            # Início automático com start_minimized: permanece apenas na bandeja (sem flicker)
            pass
        else:
            window.show()
        sys.exit(app.exec())
    except Exception as e:
        erro_msg = f"ERRO CRÍTICO AO INICIAR O PROGRAMA:\n\n{traceback.format_exc()}"
        ctypes.windll.user32.MessageBoxW(0, erro_msg, "Crash Report - AIKA Optimizer", 0x10)
