# -*- coding: utf-8 -*-
"""Página integrada e segura para geração de cópias do ItemList6."""

from __future__ import annotations

import os
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QThread, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import itemlist6_color_engine as engine
import stone_color_service as service


STATE_WAITING = "AGUARDANDO"
STATE_ANALYZING = "ANALISANDO"
STATE_COMPATIBLE = "COMPATÍVEL"
STATE_INCOMPATIBLE = "INCOMPATÍVEL"
STATE_ERROR = "ERRO"
STATE_GENERATING = "GERANDO"
STATE_APPLYING = "APLICANDO"
STATE_RESTORING = "RESTAURANDO"
STATE_PERSONALIZED = "PERSONALIZADO"
STATE_EXTERNAL = "ALTERAÇÃO EXTERNA"
STATE_BLOCKED = "BLOQUEADO"

CLIENT_NOT_CONFIGURED = (
    "Cliente do AIKA não configurado. Selecione o cliente em Configurações."
)


@dataclass(frozen=True)
class ConfirmedColor:
    name: str
    code: int
    sample: str


CONFIRMED_COLORS = (
    ConfirmedColor("Branco", 0, "#F2F2F2"),
    ConfirmedColor("Marrom/Ocre", 4, "#9A6B35"),
    ConfirmedColor("Amarelo", 5, "#F2D64B"),
    ConfirmedColor("Laranja", 6, "#F28C28"),
    ConfirmedColor("Roxo", 7, "#9B59FF"),
    ConfirmedColor("Vermelho", 8, "#FF3B3B"),
    ConfirmedColor("Preto", 9, "#111111"),
)

# Fonte única de apresentação: código interno -> nome humano visível.
NOME_POR_CODIGO = {cor.code: cor.name for cor in CONFIRMED_COLORS}


def nome_da_cor(codigo: int | None) -> str:
    """Nome visível a partir do código interno; fallback neutro sem código cru."""
    if codigo is None:
        return "Desconhecida"
    return NOME_POR_CODIGO.get(codigo, "Desconhecida")


def resumo_cores(ataque, defesa, demais, rotulo="Cores atuais") -> str:
    """Resumo legível: rótulo + nomes das categorias com os nomes das cores."""
    return (
        f"{rotulo}: Ataque PvP: {nome_da_cor(ataque)} · "
        f"Defesa PvP: {nome_da_cor(defesa)} · Demais: {nome_da_cor(demais)}."
    )


def resource_path(name: str) -> Path:
    """Resolve um recurso tanto na raiz fonte quanto em ``sys._MEIPASS``."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return (base / name).resolve(strict=False)


DEFAULT_PROFILE_PATH = resource_path("itemlist6_color_profile.json")


def default_output_directory() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = str(Path.home() / "AppData" / "Local")
    return Path(local_app_data) / "AIKA Optimizer" / "Pedras" / "Gerados"


def resolve_client_root(configured_client: str | os.PathLike[str] | None) -> Path | None:
    """Normaliza pasta ou executável configurado sem alterar a configuração central."""
    if not configured_client:
        return None
    candidate = Path(configured_client).expanduser().resolve(strict=False)
    if candidate.is_file():
        candidate = candidate.parent
    elif candidate.suffix.lower() == ".exe" and not candidate.is_dir():
        candidate = candidate.parent
    return candidate if candidate.is_dir() else None


def resolve_root_itemlist6(client_root: Path) -> Path | None:
    """Resolve exclusivamente <raiz do cliente>/ItemList6.bin, sem busca recursiva."""
    candidate = (client_root / "ItemList6.bin").resolve(strict=False)
    return candidate if candidate.is_file() else None


@dataclass(frozen=True)
class CandidateFailure:
    path: Path
    message: str


@dataclass(frozen=True)
class DetectionResult:
    client_root: Path | None
    candidates: tuple[Path, ...]
    compatible: tuple[engine.FileAnalysis, ...]
    incompatible: tuple[engine.FileAnalysis, ...]
    failures: tuple[CandidateFailure, ...]
    selected: engine.FileAnalysis | None
    state: str
    message: str


def detect_itemlist6(
    configured_client: str | os.PathLike[str] | None,
    profile_path: Path = DEFAULT_PROFILE_PATH,
) -> DetectionResult:
    """Localiza e analisa somente o ItemList6.bin da raiz do cliente."""
    client_root = resolve_client_root(configured_client)
    if client_root is None:
        return DetectionResult(
            None, (), (), (), (), None, STATE_ERROR, CLIENT_NOT_CONFIGURED
        )

    candidate = resolve_root_itemlist6(client_root)
    if candidate is None:
        return DetectionResult(
            client_root,
            (),
            (),
            (),
            (),
            None,
            STATE_ERROR,
            "ItemList6.bin não foi encontrado na raiz do cliente configurado.",
        )

    candidates = (candidate,)
    try:
        analysis = engine.analyze_file(candidate, engine.load_profile(Path(profile_path)))
    except BaseException as exc:
        return DetectionResult(
            client_root,
            candidates,
            (),
            (),
            (CandidateFailure(candidate, str(exc) or exc.__class__.__name__),),
            None,
            STATE_INCOMPATIBLE,
            f"ItemList6.bin da raiz não pôde ser validado: "
            f"{str(exc) or exc.__class__.__name__}",
        )

    if analysis.compatible:
        return DetectionResult(
            client_root,
            candidates,
            (analysis,),
            (),
            (),
            analysis,
            STATE_COMPATIBLE,
            "ItemList6.bin da raiz validado: 438/438 registros monitorados compatíveis.",
        )

    return DetectionResult(
        client_root,
        candidates,
        (),
        (analysis,),
        (),
        None,
        STATE_INCOMPATIBLE,
        f"ItemList6.bin da raiz incompatível: {len(analysis.mismatches)} "
        "divergências nos registros monitorados.",
    )


def unique_output_path(output_directory: Path, now: datetime | None = None) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    base = output_directory / f"ItemList6_Pedras_{stamp}.bin"
    if not base.exists():
        return base
    sequence = 1
    while True:
        candidate = output_directory / f"ItemList6_Pedras_{stamp}_{sequence:02d}.bin"
        if not candidate.exists():
            return candidate
        sequence += 1


def _path_is_within(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve(strict=False).relative_to(base.resolve(strict=False))
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class GenerationResult:
    detection: DetectionResult
    published: engine.PublishedOutput


def generate_validated_copy(
    configured_client: str | os.PathLike[str] | None,
    profile_path: Path,
    output_directory: Path,
    expected_input_path: Path,
    expected_input_sha256: str,
    attack_code: int,
    defense_code: int,
    common_code: int,
) -> GenerationResult:
    """Redetecta, reanalisa e publica somente uma cópia integralmente validada."""
    detection = detect_itemlist6(configured_client, profile_path)
    analysis = detection.selected
    if detection.state != STATE_COMPATIBLE or analysis is None:
        raise engine.IncompatibleUpdateError(detection.message)
    if analysis.path.resolve(strict=False) != expected_input_path.resolve(strict=False):
        raise engine.InputChangedError(
            "o ItemList6 compatível detectado mudou; analise novamente"
        )
    if analysis.sha256 != expected_input_sha256.upper():
        raise engine.InputChangedError(
            "a entrada foi modificada após a análise; analise o arquivo novamente"
        )
    output_directory = Path(output_directory).resolve(strict=False)
    if detection.client_root is not None and _path_is_within(
        detection.client_root, output_directory
    ):
        raise engine.UnsafeOutputPathError(
            "a pasta de saída não pode ficar dentro do cliente do jogo"
        )
    output_path = unique_output_path(output_directory)
    published = engine.generate_file(
        analysis.path,
        output_path,
        engine.load_profile(Path(profile_path)),
        expected_input_sha256=expected_input_sha256,
        attack_code=attack_code,
        defense_code=defense_code,
        common_code=common_code,
    )
    return GenerationResult(detection, published)


class StoneOperationWorker(QObject):
    completed = Signal(object)
    failed = Signal(str, str)
    log = Signal(str)

    def __init__(self, operation: str, **payload: object) -> None:
        super().__init__()
        self.operation = operation
        self.payload = payload

    @Slot()
    def run(self) -> None:
        try:
            if self.operation == "analysis":
                self.log.emit("Localizando e analisando ItemList6.bin em modo somente leitura.")
                result = service.recognize_state(
                    self.payload.get("configured_client"),
                    Path(self.payload["profile_path"]),
                    self.payload.get("storage_base"),
                )
                if result.kind == service.KIND_EXTERNAL_COMPATIBLE and result.client_root is not None:
                    service.ensure_base_preserved(
                        result.client_root,
                        Path(self.payload["profile_path"]),
                        self.payload.get("storage_base"),
                    )
            elif self.operation == "generation":
                self.log.emit("Gerando uma cópia validada a partir da base preservada.")
                result = service.prepare_colors(
                    self.payload.get("configured_client"),
                    Path(self.payload["profile_path"]),
                    Path(self.payload["output_directory"]),
                    int(self.payload["attack_code"]),
                    int(self.payload["defense_code"]),
                    int(self.payload["common_code"]),
                    self.payload.get("storage_base"),
                )
            elif self.operation == "apply":
                self.log.emit("Aplicando a cópia preparada no cliente.")
                result = service.apply_prepared(
                    self.payload["prepared"],
                    Path(self.payload["profile_path"]),
                    self.payload.get("storage_base"),
                )
            else:
                raise RuntimeError(f"operação desconhecida: {self.operation}")
            self.completed.emit(result)
        except BaseException as exc:
            message = str(exc) or exc.__class__.__name__
            technical = traceback.format_exc()
            # Erros operacionais esperados não exibem traceback completo no painel.
            if isinstance(exc, (engine.ValidationError, OSError)):
                technical = ""
            self.failed.emit(message, technical)


class StoneColorPage(QWidget):
    """Página incorporável; não cria QApplication nem altera o cliente do jogo."""

    log_emitted = Signal(str)
    settings_requested = Signal()
    analysis_completed = Signal(object)
    generation_completed = Signal(object)

    def __init__(
        self,
        client_provider: Callable[[], str | None],
        profile_path: Path | str | None = None,
        output_directory: Path | str | None = None,
        storage_base: Path | str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.client_provider = client_provider
        self.profile_path = Path(profile_path) if profile_path else DEFAULT_PROFILE_PATH
        self.output_directory = (
            Path(output_directory) if output_directory else default_output_directory()
        )
        self.storage_base = Path(storage_base) if storage_base else None
        self._analysis: engine.FileAnalysis | None = None
        self._prepared: service.PreparedCopy | None = None
        self._applied_success = False
        self._applied_sha256: str | None = None
        self._recognition: service.StonesRecognition | None = None
        self._colors_loaded_sha256: str | None = None
        self._loading_colors = False
        self._thread: QThread | None = None
        self._worker: QObject | None = None
        self._operation = ""
        self._state = STATE_WAITING
        self._shutdown_requested = False
        self._build_ui()
        self._apply_style()
        self.restore_defaults()
        self._set_state(STATE_WAITING, "Abra a página ou solicite uma nova análise.")

    @property
    def active_thread(self) -> QThread | None:
        return self._thread

    @property
    def analysis(self) -> engine.FileAnalysis | None:
        return self._analysis

    @property
    def recognition(self) -> service.StonesRecognition | None:
        return self._recognition

    @property
    def published(self) -> service.PreparedCopy | None:
        return self._prepared

    def selected_codes(self) -> tuple[int, int, int]:
        return (
            int(self.attack_combo.currentData()),
            int(self.defense_combo.currentData()),
            int(self.common_combo.currentData()),
        )

    def _build_ui(self) -> None:
        self.setObjectName("PedrasPage")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("PedrasScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("PedrasContent")
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(14, 12, 14, 12)
        self.content_layout.setSpacing(10)

        title = QLabel("Cores das Pedras")
        title.setObjectName("PedrasTitle")
        description = QLabel(
            "Escolha as cores que deseja usar no AIKA."
        )
        description.setObjectName("PedrasDescription")
        description.setWordWrap(True)
        self.content_layout.addWidget(title)
        self.content_layout.addWidget(description)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        self.progress.hide()
        self.content_layout.addWidget(self.progress)

        self._build_file_card()
        self._build_color_card()
        self._build_generation_card()
        self._build_result_card()
        self.content_layout.addStretch()
        scroll.setWidget(content)
        scroll.viewport().setAutoFillBackground(False)
        outer.addWidget(scroll)

    def _card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("PedrasCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(7)
        heading = QLabel(title)
        heading.setObjectName("PedrasCardTitle")
        layout.addWidget(heading)
        self.content_layout.addWidget(card)
        return card, layout

    def _build_file_card(self) -> None:
        _, layout = self._card("ESTADO DO ARQUIVO")
        top = QHBoxLayout()
        self.state_label = QLabel(STATE_WAITING)
        self.state_label.setObjectName("PedrasState")
        self.analyze_button = QPushButton("Analisar novamente")
        self.analyze_button.setObjectName("PedrasSecondaryButton")
        self.analyze_button.clicked.connect(self.analyze_again)
        top.addWidget(self.state_label)
        top.addStretch()
        top.addWidget(self.analyze_button)
        layout.addLayout(top)
        self.state_detail = QLabel()
        self.state_detail.setObjectName("PedrasMuted")
        self.state_detail.setWordWrap(True)
        layout.addWidget(self.state_detail)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(5)
        self.file_labels: dict[str, QLabel] = {}
        fields = (
            ("client", "Cliente configurado"),
            ("path", "ItemList6 detectado"),
            ("sha256", "SHA-256 da entrada"),
            ("size", "Tamanho"),
            ("records", "Registros reconhecidos"),
            ("compatibility", "Compatibilidade"),
        )
        for row, (key, label_text) in enumerate(fields):
            name = QLabel(label_text)
            name.setObjectName("PedrasFieldName")
            value = QLabel("—")
            value.setObjectName("PedrasFieldValue")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(name, row, 0, Qt.AlignTop)
            grid.addWidget(value, row, 1)
            self.file_labels[key] = value
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        self.settings_button = QPushButton("ABRIR CONFIGURAÇÕES")
        self.settings_button.setObjectName("PedrasSecondaryButton")
        self.settings_button.clicked.connect(self.settings_requested.emit)
        self.settings_button.hide()
        layout.addWidget(self.settings_button, 0, Qt.AlignLeft)

    def _build_color_card(self) -> None:
        _, layout = self._card("CONFIGURAÇÃO DE CORES")
        row = QHBoxLayout()
        row.setSpacing(10)
        self.attack_combo = self._selector(row, "Ataque PvP", "60 registros")
        self.defense_combo = self._selector(row, "Defesa PvP", "60 registros")
        self.common_combo = self._selector(
            row, "Demais pedras coloridas", "318 registros"
        )
        for combo in (self.attack_combo, self.defense_combo, self.common_combo):
            combo.currentIndexChanged.connect(self._on_color_changed)
        layout.addLayout(row)
        reset = QPushButton("RESTAURAR PADRÕES")
        reset.setObjectName("PedrasSecondaryButton")
        reset.clicked.connect(self.restore_defaults)
        layout.addWidget(reset, 0, Qt.AlignRight)

    def _selector(self, row: QHBoxLayout, title: str, count: str) -> QComboBox:
        frame = QFrame()
        frame.setObjectName("PedrasSelector")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        heading = QLabel(title)
        heading.setObjectName("PedrasSelectorTitle")
        helper = QLabel(count)
        helper.setObjectName("PedrasMuted")
        combo = QComboBox()
        combo.setIconSize(QPixmap(16, 16).size())
        for color in CONFIRMED_COLORS:
            sample = QPixmap(16, 16)
            sample.fill(QColor(color.sample))
            combo.addItem(QIcon(sample), color.name, color.code)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(heading)
        layout.addWidget(helper)
        layout.addWidget(combo)
        row.addWidget(frame, 1)
        return combo

    def _build_generation_card(self) -> None:
        _, layout = self._card("AÇÃO")
        notice = QLabel(
            "Gere uma cópia validada e, em seguida, aplique-a no ItemList6.bin do "
            "cliente. A base original é preservada e verificada antes de qualquer escrita."
        )
        notice.setObjectName("PedrasNotice")
        notice.setWordWrap(True)
        self.action_button = QPushButton("Gerar cópia")
        self.action_button.setObjectName("PedrasPrimaryButton")
        self.action_button.setEnabled(False)
        self.action_button.clicked.connect(self._on_action_clicked)
        layout.addWidget(notice)
        layout.addWidget(self.action_button)

    def _build_result_card(self) -> None:
        _, layout = self._card("RESULTADO")
        self.result_status = QLabel("Nenhuma cópia foi gerada nesta sessão.")
        self.result_status.setObjectName("PedrasMuted")
        self.result_status.setWordWrap(True)
        self.result_details = QLabel()
        self.result_details.setObjectName("PedrasFieldValue")
        self.result_details.setWordWrap(True)
        self.result_details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.open_folder_button = QPushButton("ABRIR PASTA DA CÓPIA")
        self.open_folder_button.setObjectName("PedrasSecondaryButton")
        self.open_folder_button.setEnabled(False)
        self.open_folder_button.clicked.connect(self.open_output_folder)
        layout.addWidget(self.result_status)
        layout.addWidget(self.result_details)
        layout.addWidget(self.open_folder_button, 0, Qt.AlignRight)

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QWidget#PedrasPage, QWidget#PedrasContent,
            QScrollArea#PedrasScroll, QScrollArea#PedrasScroll > QWidget > QWidget {
                background-color: transparent;
            }
            QLabel#PedrasTitle { color: white; font-size: 20px; font-weight: bold; }
            QLabel#PedrasDescription { color: #A0A0B0; font-size: 13px; }
            QFrame#PedrasCard { background-color: rgba(255,255,255,10);
                border: 1px solid rgba(255,255,255,16); border-radius: 12px; }
            QLabel#PedrasCardTitle { color: #BF00FF; font-size: 11px; font-weight: bold; }
            QLabel#PedrasFieldName { color: #8A8A9A; font-size: 11px; font-weight: bold; }
            QLabel#PedrasFieldValue { color: #D8D8E3; font-size: 11px; }
            QLabel#PedrasMuted { color: #8A8A9A; font-size: 11px; }
            QLabel#PedrasNotice { color: #CFC4D8; background: rgba(191,0,255,18);
                border-left: 3px solid #BF00FF; padding: 8px; }
            QFrame#PedrasSelector { background: rgba(0,0,0,45);
                border: 1px solid rgba(255,255,255,16); border-radius: 8px; }
            QLabel#PedrasSelectorTitle { color: white; font-size: 12px; font-weight: bold; }
            QComboBox { background: #101014; color: #E6E6F0; border: 1px solid #383841;
                border-radius: 6px; padding: 6px; }
            QComboBox::drop-down { border: none; width: 25px; }
            QComboBox QAbstractItemView {
                background-color: #15151C;
                color: #ECECF4;
                border: 1px solid #4D2760;
                selection-background-color: #4D1763;
                selection-color: #FFFFFF;
                outline: 0;
            }
            QComboBox QAbstractItemView::item {
                color: #ECECF4;
                background: transparent;
                padding: 5px 8px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: rgba(191, 0, 255, 60);
                color: #FFFFFF;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #7A1FA8;
                color: #FFFFFF;
            }
            QComboBox QAbstractItemView::item:disabled {
                color: #9A9AA6;
                background: transparent;
            }
            QPushButton#PedrasSecondaryButton { background: rgba(77,0,128,90); color: #E6E6F0;
                border: 1px solid rgba(191,0,255,90); border-radius: 7px;
                padding: 7px 12px; font-size: 11px; font-weight: bold; }
            QPushButton#PedrasSecondaryButton:hover { border-color: #BF00FF; }
            QPushButton#PedrasPrimaryButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #BF00FF, stop:1 #7A1FA8); color: white; border: 1px solid #BF00FF;
                border-radius: 9px; padding: 11px; font-size: 13px; font-weight: bold; }
            QPushButton#PedrasPrimaryButton:disabled { background: #29292F; color: #666;
                border-color: #3A3A42; }
            QProgressBar { background: #24242A; border: none; }
            QProgressBar::chunk { background: #BF00FF; }
        """)

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        if not self._busy() and not self._shutdown_requested:
            QTimer.singleShot(0, self.analyze_again)

    @Slot()
    def restore_defaults(self) -> None:
        for combo, code in (
            (self.attack_combo, 8),
            (self.defense_combo, 7),
            (self.common_combo, 0),
        ):
            index = combo.findData(code)
            combo.setCurrentIndex(index)

    def _configured_client(self) -> str | None:
        try:
            return self.client_provider()
        except Exception:
            return None

    @Slot()
    def analyze_again(self) -> bool:
        if self._busy() or self._shutdown_requested:
            return False
        self._analysis = None
        self._recognition = None
        self.open_folder_button.setEnabled(False)
        self._set_state(STATE_ANALYZING, "Localizando o arquivo no cliente configurado.")
        worker = StoneOperationWorker(
            "analysis",
            configured_client=self._configured_client(),
            profile_path=self.profile_path,
            storage_base=self.storage_base,
        )
        worker.completed.connect(self._analysis_finished)
        worker.failed.connect(self._operation_failed)
        self._start_worker(worker, "analysis")
        return True

    @Slot(object)
    def _analysis_finished(self, recognition: service.StonesRecognition) -> None:
        self._recognition = recognition
        self._analysis = None
        self.file_labels["client"].setText(
            str(recognition.client_root) if recognition.client_root else "Não configurado"
        )
        self.settings_button.setVisible(recognition.client_root is None)
        if recognition.file_sha256 is not None:
            self.file_labels["path"].setText(
                str(recognition.target_path) if recognition.target_path else "—"
            )
            self.file_labels["sha256"].setText(recognition.file_sha256)
            self.file_labels["size"].setText(
                f"{recognition.file_size:,} bytes".replace(",", ".")
                if recognition.file_size is not None else "—"
            )
            self.file_labels["records"].setText(
                str(recognition.record_count) if recognition.record_count is not None else "—"
            )
            if (
                recognition.kind == service.KIND_PERSONALIZED
                and recognition.base_compatible_records is not None
            ):
                self.file_labels["compatibility"].setText(
                    f"base verificada: {recognition.base_compatible_records}/438 registros"
                )
            else:
                self.file_labels["compatibility"].setText(
                    f"{recognition.compatible_records}/438 registros monitorados"
                )
        else:
            self.file_labels["path"].setText(
                str(recognition.target_path) if recognition.target_path else "Não encontrado"
            )
            self.file_labels["sha256"].setText("—")
            self.file_labels["size"].setText("—")
            self.file_labels["records"].setText("—")
            self.file_labels["compatibility"].setText(recognition.message)

        self._apply_recognition_state()
        if recognition.kind == service.KIND_PERSONALIZED:
            self._load_applied_colors(recognition)
        self._reconcile_preparation(recognition.file_sha256)
        self._update_action_button()
        self._emit_log(f"[Pedras] {self._state}: {recognition.message}")
        self.analysis_completed.emit(recognition)

    def _apply_recognition_state(self) -> None:
        rec = self._recognition
        if rec is None:
            return
        if rec.kind == service.KIND_PERSONALIZED:
            colors = rec.applied_colors or (None, None, None)
            if rec.base_valid:
                detail = (
                    f"{rec.message} {resumo_cores(colors[0], colors[1], colors[2])}"
                )
                self._set_state(STATE_PERSONALIZED, detail)
            else:
                self._set_state(STATE_BLOCKED, rec.message)
        elif rec.kind == service.KIND_BASE:
            self._set_state(STATE_COMPATIBLE, rec.message)
        elif rec.kind == service.KIND_EXTERNAL_COMPATIBLE:
            self._set_state(STATE_EXTERNAL, rec.message)
        elif rec.kind == service.KIND_EXTERNAL_INCOMPATIBLE:
            self._set_state(STATE_BLOCKED, rec.message)
        else:
            self._set_state(STATE_ERROR, rec.message)

    def _recognition_applicable(self, rec: service.StonesRecognition) -> bool:
        if rec.kind == service.KIND_PERSONALIZED:
            return rec.base_valid
        if rec.kind == service.KIND_BASE:
            return True
        if rec.kind == service.KIND_EXTERNAL_COMPATIBLE:
            return True
        return False

    def _analysis_valid(self) -> bool:
        rec = self._recognition
        if rec is not None:
            return self._recognition_applicable(rec)
        return self._analysis is not None

    def _reconcile_preparation(self, file_sha256: str | None) -> None:
        """Invalida preparação/sucesso se o conteúdo analisado mudou."""
        if file_sha256 is None:
            return
        if (
            self._prepared is not None
            and file_sha256 != self._prepared.observed_target_sha256
        ):
            self._prepared = None
        if self._applied_success and file_sha256 != self._applied_sha256:
            self._applied_success = False

    def _invalidate_preparation(self) -> None:
        self._prepared = None
        self._applied_success = False
        self._applied_sha256 = None
        self._update_action_button()

    @Slot()
    def _on_color_changed(self, *args) -> None:
        if self._loading_colors:
            return
        if self._prepared is not None or self._applied_success:
            self._invalidate_preparation()

    def _load_applied_colors(self, rec: service.StonesRecognition) -> None:
        """Carrega as cores já aplicadas nos seletores, uma vez por conteúdo."""
        colors = rec.applied_colors
        if not colors or all(c is None for c in colors):
            return
        if self._colors_loaded_sha256 == rec.file_sha256:
            return
        self._colors_loaded_sha256 = rec.file_sha256
        self._loading_colors = True
        try:
            for combo, code in (
                (self.attack_combo, colors[0]),
                (self.defense_combo, colors[1]),
                (self.common_combo, colors[2]),
            ):
                index = combo.findData(code)
                if index >= 0:
                    combo.setCurrentIndex(index)
        finally:
            self._loading_colors = False

    @Slot()
    def _on_action_clicked(self) -> None:
        if self._prepared is not None:
            self.apply_colors()
        else:
            self.generate_copy()

    def _update_action_button(self) -> None:
        if self._operation:
            if self._operation == "apply":
                self.action_button.setText("Aplicando…")
            elif self._operation == "generation":
                self.action_button.setText("Gerando…")
            else:
                self.action_button.setText("Processando…")
            self.action_button.setEnabled(False)
            return
        if self._shutdown_requested:
            self.action_button.setEnabled(False)
            return
        if self._prepared is not None:
            self.action_button.setText("Aplicar no AIKA")
            self.action_button.setEnabled(True)
            return
        if self._applied_success:
            self.action_button.setText("Cores aplicadas")
            self.action_button.setEnabled(False)
            return
        self.action_button.setText("Gerar cópia")
        self.action_button.setEnabled(self._analysis_valid())

    @Slot()
    def refresh_after_restore(self) -> None:
        """Chamado pela aba Restauração: invalida preparações obsoletas e reanalisa."""
        self._invalidate_preparation()
        self.open_folder_button.setEnabled(False)
        self.analyze_again()

    @Slot()
    def generate_copy(self) -> bool:
        if self._busy() or self._shutdown_requested or not self._analysis_valid():
            return False
        attack, defense, common = self.selected_codes()
        self.open_folder_button.setEnabled(False)
        self._set_state(
            STATE_GENERATING,
            "Gerando uma cópia validada a partir da base preservada em segundo plano.",
        )
        worker = StoneOperationWorker(
            "generation",
            configured_client=self._configured_client(),
            profile_path=self.profile_path,
            output_directory=self.output_directory,
            storage_base=self.storage_base,
            attack_code=attack,
            defense_code=defense,
            common_code=common,
        )
        worker.completed.connect(self._generation_finished)
        worker.failed.connect(self._operation_failed)
        self._start_worker(worker, "generation")
        return True

    @Slot(object)
    def _generation_finished(self, prepared: service.PreparedCopy) -> None:
        self._prepared = prepared
        self.result_status.setText("CÓPIA GERADA E VALIDADA — PRONTA PARA APLICAR")
        self.result_status.setStyleSheet("color: #65D68A; font-weight: bold;")
        self.result_details.setText(
            f"Caminho: {prepared.copy_path}\n"
            f"SHA-256 da cópia: {prepared.copy_sha256}\n"
            "Validação final: reprodução integral confirmada pelo engine"
        )
        self.open_folder_button.setEnabled(True)
        self._set_state(STATE_COMPATIBLE, "Cópia validada pronta; o original permaneceu somente leitura.")
        self._emit_log(f"[Pedras] Cópia validada: {prepared.copy_path}")
        self._update_action_button()

    @Slot()
    def apply_colors(self) -> bool:
        if self._busy() or self._shutdown_requested or self._prepared is None:
            return False
        self._set_state(
            STATE_APPLYING,
            "Aplicando a cópia preparada no cliente em segundo plano.",
        )
        worker = StoneOperationWorker(
            "apply",
            prepared=self._prepared,
            profile_path=self.profile_path,
            storage_base=self.storage_base,
        )
        worker.completed.connect(self._apply_finished)
        worker.failed.connect(self._operation_failed)
        self._start_worker(worker, "apply")
        return True

    @Slot(object)
    def _apply_finished(self, outcome: service.ApplyOutcome) -> None:
        self._prepared = None
        self._applied_success = True
        self._applied_sha256 = outcome.output_sha256
        self.open_folder_button.setEnabled(False)
        if outcome.applied:
            self.result_status.setText("CORES APLICADAS NO CLIENTE")
        else:
            self.result_status.setText("CORES JÁ APLICADAS (SEM ESCRITA)")
        self.result_status.setStyleSheet("color: #65D68A; font-weight: bold;")
        self.result_details.setText(outcome.message)
        self.file_labels["sha256"].setText(outcome.output_sha256)
        colors = self.selected_codes()
        self._set_state(
            STATE_PERSONALIZED,
            resumo_cores(colors[0], colors[1], colors[2], rotulo="Cores aplicadas"),
        )
        self._emit_log(f"[Pedras] {outcome.message}")
        self._update_action_button()

    @Slot(str, str)
    def _operation_failed(self, message: str, technical: str) -> None:
        recoverable = self._is_recoverable_failure(message)
        changed = "modificada após" in message or "mudou" in message
        if not recoverable:
            self._prepared = None
        if changed:
            self._applied_success = False
            self._applied_sha256 = None
        self.result_status.setText("OPERAÇÃO NÃO CONCLUÍDA")
        self.result_status.setStyleSheet("color: #FF6363; font-weight: bold;")
        self.result_details.setText(message)
        self._set_state(STATE_ERROR, message)
        self._emit_log(
            f"[Pedras] ERRO: {message}" + (f"\n{technical}" if technical else "")
        )
        self._update_action_button()

    @staticmethod
    def _is_recoverable_failure(message: str) -> bool:
        return "Feche o" in message or "Não foi possível verificar" in message

    def _start_worker(self, worker: StoneOperationWorker, operation: str) -> None:
        if self._busy():
            raise RuntimeError("já existe uma operação de Pedras em andamento")
        self._operation = operation
        self._set_busy(True)
        thread = QThread(self)
        self._thread = thread
        self._worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.log.connect(self._emit_log)
        worker.completed.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._worker_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot()
    def _worker_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._operation = ""
        self._set_busy(False)
        if self._shutdown_requested:
            return
        self._update_action_button()

    def _busy(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def _set_busy(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.analyze_button.setEnabled(not busy and not self._shutdown_requested)
        for combo in (self.attack_combo, self.defense_combo, self.common_combo):
            combo.setEnabled(not busy and not self._shutdown_requested)
        self._update_action_button()

    def _set_state(self, state: str, message: str) -> None:
        self._state = state
        self.state_label.setText(state)
        self.state_detail.setText(message)
        colors = {
            STATE_COMPATIBLE: ("#65D68A", "#173523"),
            STATE_ANALYZING: ("#D77AFF", "#2F1939"),
            STATE_GENERATING: ("#D77AFF", "#2F1939"),
            STATE_APPLYING: ("#D77AFF", "#2F1939"),
            STATE_RESTORING: ("#D77AFF", "#2F1939"),
            STATE_PERSONALIZED: ("#65D68A", "#173523"),
            STATE_EXTERNAL: ("#F2D64B", "#3A3310"),
            STATE_BLOCKED: ("#FF6B6B", "#3B181D"),
            STATE_INCOMPATIBLE: ("#FF6B6B", "#3B181D"),
            STATE_ERROR: ("#FF6B6B", "#3B181D"),
            STATE_WAITING: ("#C0C0C7", "#292930"),
        }
        foreground, background = colors[state]
        self.state_label.setStyleSheet(
            f"color: {foreground}; background: {background}; padding: 5px 9px; "
            "border-radius: 5px; font-weight: bold;"
        )

    @Slot(str)
    def _emit_log(self, message: str) -> None:
        if message.strip():
            self.log_emitted.emit(message.strip())

    @Slot()
    def open_output_folder(self) -> None:
        if self._prepared is None:
            return
        try:
            os.startfile(str(self._prepared.copy_path.parent))  # type: ignore[attr-defined]
        except OSError as exc:
            self._operation_failed(str(exc), traceback.format_exc())

    def request_shutdown(self) -> None:
        """Solicita parada cooperativa sem bloquear a thread da interface."""
        self._shutdown_requested = True
        self._set_busy(False)
        if self._thread is not None and self._thread.isRunning():
            self._thread.requestInterruption()
            self._thread.quit()

    def shutdown(self, wait_msecs: int = 5000) -> bool:
        """Solicita encerramento e aguarda por tempo limitado, sem terminar a thread."""
        self.request_shutdown()
        thread = self._thread
        if thread is None:
            return True
        try:
            return not thread.isRunning() or thread.wait(max(0, int(wait_msecs)))
        except RuntimeError:
            return True
