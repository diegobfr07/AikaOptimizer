# -*- coding: utf-8 -*-
"""Página Renderizador (dgVoodoo2) — AIKA Optimizer V4.1.

Componente visual isolado: apresenta o estado gráfico do cliente Aika e
expõe as operações ``ativar_dgvoodoo`` e ``restaurar_directx_original`` do
``dgvoodoo_service``. NÃO altera o cliente por conta própria — apenas chama
as APIs públicas do backend.

Pensada para ser integrada ao ``QStackedWidget`` do ``main.py`` (Etapa 3B),
mas funcional e testável isoladamente nesta Etapa 3A.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import dgvoodoo_service as backend
import hardware_detector as hd


# ---------------------------------------------------------------------------
# Paleta de estados (cor do indicador + cor do texto de status)
# ---------------------------------------------------------------------------

STATE_COLORS = {
    backend.Estado.ORIGINAL: ("#4FC3F7", "#E3F2FD"),
    backend.Estado.ATIVO: ("#4CAF50", "#E8F5E9"),
    backend.Estado.CONFLITO: ("#FF9800", "#FFF3E0"),
    backend.Estado.INCOMPLETO: ("#FF9800", "#FFF3E0"),
    backend.Estado.MODIFICADO_EXTERNAMENTE: ("#F44336", "#FFEBEE"),
    backend.Estado.TEMPLATE_AUSENTE: ("#F44336", "#FFEBEE"),
    backend.Estado.ERRO: ("#F44336", "#FFEBEE"),
    backend.Estado.JOGO_ABERTO: ("#FF9800", "#FFF3E0"),
}


def _resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return (base / name).resolve(strict=False)


# ---------------------------------------------------------------------------
# Layout responsivo dos cards de perfil (somente UI)
# ---------------------------------------------------------------------------
# Largura da PÁGINA (não do monitor) a partir da qual os 4 cards ficam em uma
# linha. Com a área de conteúdo = largura da página - 28 px (margens) e 3
# espaços de 8 px, 4 cards em 820 px resultam em ~192 px de largura útil por
# card — suficiente para os textos curtos com quebras, sem clipping.
PROFILE_LAYOUT_BREAKPOINT = 820

# Alturas mínimas dos cards por modo (texto completo sempre visível).
_PROFILE_HEIGHT_WIDE = 96
_PROFILE_HEIGHT_COMPACT = 120

# Ícones SVG da página (line-art magenta, sem emojis). Arquivos em assets/icons.
_PROFILE_ICONS = {
    "auto": "renderer_auto.svg",
    "performance": "renderer_performance.svg",
    "balanced": "renderer_balanced.svg",
    "quality": "renderer_quality.svg",
    "gpu": "renderer_gpu.svg",
    "refresh": "renderer_refresh.svg",
}


def _icon_svg(name: str) -> Path:
    """Resolve o caminho de um SVG da página (assets/icons/<name>)."""
    return _resource_path(Path("assets") / "icons" / name)


class ProfileCardButton(QPushButton):
    """Card clicável de perfil: ícone + título forte + descrição menor.

    Mantém as garantias funcionais dos cards antigos: checkable, exclusivo
    via QButtonGroup, propriedade ``profile`` e badge (somente AUTO). Todos os
    filhos (ícone/título/descrição/badge) são transparentes ao mouse para que
    o clique em qualquer área do card ative o botão.
    """

    def __init__(
        self,
        perfil: str,
        titulo: str,
        descricao: str,
        badge: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ProfileCardButton")
        self.setProperty("profile", perfil)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setText("")
        self.setIcon(QIcon())
        if badge:
            self.setProperty("badge", badge)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)
        layout.addStretch(1)

        icon_label = QLabel()
        icon_label.setObjectName("ProfileCardIcon")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        caminho = _icon_svg(_PROFILE_ICONS[perfil])
        pix = QPixmap(str(caminho))
        if not pix.isNull():
            pix = pix.scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label.setPixmap(pix)
        layout.addWidget(icon_label)

        title_label = QLabel(titulo)
        title_label.setObjectName("ProfileCardTitle")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(title_label)

        badge_label = QLabel(badge if badge else "")
        badge_label.setObjectName("ProfileCardBadge")
        badge_label.setAlignment(Qt.AlignCenter)
        badge_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        badge_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        if not badge:
            badge_label.hide()
        # AlignHCenter evita que o badge estique horizontalmente (sem barra).
        layout.addWidget(badge_label, 0, Qt.AlignHCenter)

        desc_label = QLabel(descricao)
        desc_label.setObjectName("ProfileCardDescription")
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        desc_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(desc_label)

        layout.addStretch(1)

        self._icon_label = icon_label
        self._title_label = title_label
        self._desc_label = desc_label
        self._badge_label = badge_label

    def setEnabled(self, enabled: bool) -> None:  # type: ignore[override]
        """Desabilita visualmente os filhos junto com o botão."""
        super().setEnabled(enabled)
        for child in (self._icon_label, self._title_label,
                      self._desc_label, self._badge_label):
            child.setEnabled(enabled)


class DgvoodooPage(QWidget):
    """Página Renderizador, incorporável e testável isoladamente.

    Operações são executadas por um ``executor`` injetado (quando fornecido),
    permitindo que o ``main.py`` as rode em background via
    ``executar_em_background``. Sem executor, as operações rodam de forma
    síncrona — útil para testes e para uso isolado.
    """

    log_emitted = Signal(str)
    settings_requested = Signal()
    hardware_detected = Signal(object)

    def __init__(
        self,
        client_provider: Callable[[], Optional[str]],
        executor: Optional[Callable[[Callable[[], None]], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.client_provider = client_provider
        self.executor = executor
        self._busy = False
        self._last_detection: Optional[backend.EstadoDetectado] = None
        self._profile_applied: str = backend.PERFIL_BALANCED
        self._profile_applied_resolved: str = backend.PERFIL_BALANCED
        self._profile_selected: str = backend.PERFIL_BALANCED
        # Cache da sessão: nenhuma persistência global de hardware nesta etapa.
        self._hardware_profile: Optional[object] = None
        self._hardware_detecting: bool = False
        # Detecção automática: apenas na primeira vez que a página é exibida.
        self._hardware_initial_requested: bool = False
        # Estado do layout responsivo dos cards de perfil (somente UI).
        self._profile_layout_order: list[str] = []
        self._profile_layout_wide: Optional[bool] = None
        self.hardware_detected.connect(self._on_hardware_detected)
        self._build_ui()
        self._apply_style()
        self.refresh_estado()

    def _build_ui(self) -> None:
        self.setObjectName("DgvoodooPage")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("DgvoodooScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("DgvoodooContent")
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(14, 12, 14, 12)
        self.content_layout.setSpacing(10)

        title = QLabel("Renderizador")
        title.setObjectName("DgvoodooTitle")
        subtitle = QLabel("Gerencie o renderizador gráfico utilizado pelo AIKA.")
        subtitle.setObjectName("DgvoodooDescription")
        subtitle.setWordWrap(True)
        self.content_layout.addWidget(title)
        self.content_layout.addWidget(subtitle)

        self._build_status_card()
        self._build_info_card()
        self._build_hardware_card()
        self._build_profile_card()
        self._build_action_card()
        self._build_about_card()

        self.content_layout.addStretch()
        scroll.setWidget(content)
        scroll.viewport().setAutoFillBackground(False)
        outer.addWidget(scroll)

    def _build_status_card(self) -> None:
        card, layout = self._card("STATUS")
        top = QHBoxLayout()
        top.setSpacing(10)
        self.status_indicator = QLabel("\u25cf")
        self.status_indicator.setObjectName("DgvoodooIndicator")
        self.status_label = QLabel("Verificando...")
        self.status_label.setObjectName("DgvoodooStatus")
        top.addWidget(self.status_indicator)
        top.addWidget(self.status_label, 1)
        layout.addLayout(top)

        self.status_detail = QLabel()
        self.status_detail.setObjectName("DgvoodooDetail")
        self.status_detail.setWordWrap(True)
        layout.addWidget(self.status_detail)
        self.content_layout.addWidget(card)

    def _build_info_card(self) -> None:
        card, layout = self._card("DETALHES")
        grid = QHBoxLayout()
        grid.setSpacing(12)

        backend_frame = QFrame()
        backend_frame.setObjectName("DgvoodooInfoBox")
        bl = QVBoxLayout(backend_frame)
        bl.setContentsMargins(10, 8, 10, 8)
        bt = QLabel("BACKEND")
        bt.setObjectName("DgvoodooInfoLabel")
        bv = QLabel("\u2014")
        bv.setObjectName("DgvoodooInfoValue")
        bv.setWordWrap(True)
        bl.addWidget(bt)
        bl.addWidget(bv)
        grid.addWidget(backend_frame, 1)
        self.backend_value = bv

        perfil_frame = QFrame()
        perfil_frame.setObjectName("DgvoodooInfoBox")
        pl = QVBoxLayout(perfil_frame)
        pl.setContentsMargins(10, 8, 10, 8)
        pt = QLabel("PERFIL")
        pt.setObjectName("DgvoodooInfoLabel")
        pv = QLabel("\u2014")
        pv.setObjectName("DgvoodooInfoValue")
        pv.setWordWrap(True)
        pl.addWidget(pt)
        pl.addWidget(pv)
        grid.addWidget(perfil_frame, 1)
        self.perfil_value = pv

        layout.addLayout(grid)
        self.info_card = card
        self.content_layout.addWidget(card)

    def _build_hardware_card(self) -> None:
        """Card permanente 'HARDWARE DETECTADO' (GPU/VRAM/Recomendação/Confiança).

        Vive sempre na página (não depende de AUTO). O conteúdo é preenchido
        pela detecção automática ao entrar na página, por REANALISAR ou ao
        selecionar AUTO. Não exibe detalhes técnicos (PNPID/Registro/etc).
        """
        card = QFrame()
        card.setObjectName("DgvoodooCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(7)

        header = QHBoxLayout()
        header.setSpacing(6)
        hw_icon = QLabel()
        hw_icon.setObjectName("DgvoodooHwIcon")
        hw_icon.setAttribute(Qt.WA_TransparentForMouseEvents)
        pix = QPixmap(str(_icon_svg(_PROFILE_ICONS["gpu"])))
        if not pix.isNull():
            hw_icon.setPixmap(pix.scaled(16, 16, Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation))
        heading = QLabel("HARDWARE DETECTADO")
        heading.setObjectName("DgvoodooCardTitle")
        header.addWidget(hw_icon)
        header.addWidget(heading)
        header.addStretch(1)
        # Ação secundária integrada ao cabeçalho (à direita).
        self.reanalyze_button = QPushButton("REANALISAR HARDWARE")
        self.reanalyze_button.setObjectName("DgvoodooMiniButton")
        self.reanalyze_button.setCursor(Qt.PointingHandCursor)
        self.reanalyze_button.setIcon(
            QIcon(str(_icon_svg(_PROFILE_ICONS["refresh"])))
        )
        self.reanalyze_button.clicked.connect(self._on_reanalyze_clicked)
        header.addWidget(self.reanalyze_button)
        layout.addLayout(header)

        # Linha/células com rótulo de categoria (muted) + valor.
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(4)

        def _celula(rotulo, papel="info"):
            box = QFrame()
            box.setObjectName("DgvoodooHardwareCell")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(10, 6, 10, 6)
            bl.setSpacing(1)
            cap = QLabel(rotulo)
            cap.setObjectName("DgvoodooHardwareLabel")
            bl.addWidget(cap)
            val = QLabel("—")
            if papel == "recomendacao":
                val.setObjectName("DgvoodooHardwareRecValue")
            elif papel == "confianca":
                val.setObjectName("DgvoodooHardwareConfValue")
            else:
                val.setObjectName("DgvoodooHardwareInfo")
            val.setProperty("hw_value_role", papel)
            val.setWordWrap(True)
            bl.addWidget(val)
            return box, val

        gpu_box, gpu_val = _celula("GPU", "info")
        vram_box, vram_val = _celula("VRAM", "info")
        rec_box, rec_val = _celula("PERFIL RECOMENDADO", "recomendacao")
        conf_box, conf_val = _celula("CONFIANÇA", "confianca")
        grid.addWidget(gpu_box, 0, 0)
        grid.addWidget(vram_box, 0, 1)
        grid.addWidget(rec_box, 1, 0)
        grid.addWidget(conf_box, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        self.hw_gpu_label = gpu_val
        self.hw_vram_label = vram_val
        self.hw_recomendacao_label = rec_val
        self.hw_confianca_label = conf_val

        self.hardware_card = card
        self.content_layout.addWidget(card)
        # Estado inicial: analisando (a detecção automática inicia ao entrar).
        self._mostrar_detectando_hardware()

    def _build_about_card(self) -> None:
        card, layout = self._card("SOBRE")
        text = QLabel(
            "O dgVoodoo2 permite que o AIKA utilize DirectX 11 como backend, "
            "mantendo a compatibilidade com o DirectX 9 do jogo."
        )
        text.setObjectName("DgvoodooAbout")
        text.setWordWrap(True)
        layout.addWidget(text)
        self.content_layout.addWidget(card)

    def _build_action_card(self) -> None:
        card, layout = self._card("AÇÃO")

        self.activate_button = QPushButton("ATIVAR DGVOODOO2")
        self.activate_button.setObjectName("DgvoodooPrimaryButton")
        self.activate_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.activate_button.setMinimumHeight(44)
        self.activate_button.clicked.connect(self._on_activate_clicked)
        layout.addWidget(self.activate_button)

        secondary_row = QHBoxLayout()
        secondary_row.setSpacing(8)

        self.reapply_button = QPushButton("REAPLICAR")
        self.reapply_button.setObjectName("DgvoodooSecondaryButton")
        self.reapply_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.reapply_button.clicked.connect(self._on_activate_clicked)
        secondary_row.addWidget(self.reapply_button)

        self.restore_button = QPushButton("RESTAURAR DIRECTX ORIGINAL")
        self.restore_button.setObjectName("DgvoodooSecondaryButton")
        self.restore_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.restore_button.clicked.connect(self._on_restore_clicked)
        secondary_row.addWidget(self.restore_button)

        layout.addLayout(secondary_row)
        self.content_layout.addWidget(card)

    def _build_profile_card(self) -> None:
        card, layout = self._card("PERFIL GRÁFICO")

        self._profile_buttons: dict[str, ProfileCardButton] = {}
        self._profile_group = QButtonGroup(self)
        self._profile_group.setExclusive(True)

        # Grid responsivo: 4 colunas (largo) ou 2x2 (largura reduzida).
        self._profile_grid = QGridLayout()
        self._profile_grid.setSpacing(8)
        self._profile_grid.setHorizontalSpacing(8)
        self._profile_grid.setVerticalSpacing(8)

        items = (
            (backend.PERFIL_AUTO, "AUTO",
             "Analisa seu hardware e recomenda\nautomaticamente o perfil ideal.",
             "RECOMENDADO"),
            (backend.PERFIL_PERFORMANCE, "DESEMPENHO",
             "Prioriza maior leveza e\nmenor carga gráfica.", ""),
            (backend.PERFIL_BALANCED, "EQUILIBRADO",
             "Equilíbrio entre desempenho\ne qualidade visual.", ""),
            (backend.PERFIL_QUALITY, "QUALIDADE",
             "Prioriza suavização e melhor\nacabamento da imagem.", ""),
        )
        self._profile_layout_order = [perfil for perfil, *_ in items]
        for idx, (perfil, titulo, descricao, badge) in enumerate(items):
            btn = ProfileCardButton(perfil, titulo, descricao, badge)
            btn.clicked.connect(
                lambda _=False, p=perfil: self._on_profile_selected(p)
            )
            self._profile_group.addButton(btn)
            self._profile_buttons[perfil] = btn
            self._profile_grid.addWidget(btn, 0, idx)  # posição inicial provisória

        layout.addLayout(self._profile_grid)
        # Aplica o modo responsivo inicial (segundo a largura já disponível).
        self._aplicar_layout_perfis(self.width() >= PROFILE_LAYOUT_BREAKPOINT)

        self.profile_status = QLabel()
        self.profile_status.setObjectName("DgvoodooProfileStatus")
        self.profile_status.setWordWrap(True)
        layout.addWidget(self.profile_status)

        self.apply_profile_button = QPushButton("APLICAR PERFIL")
        self.apply_profile_button.setObjectName("DgvoodooPrimaryButton")
        self.apply_profile_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.apply_profile_button.setMinimumHeight(44)
        self.apply_profile_button.clicked.connect(self._on_apply_profile_clicked)
        layout.addWidget(self.apply_profile_button)
        self.content_layout.addWidget(card)

    def _aplicar_layout_perfis(self, wide: bool) -> None:
        """Reorganiza os cards entre '4 colunas' e '2x2' SEM recriar widgets.

        Operação barata: só reposiciona os mesmos botões no grid e ajusta a
        altura mínima. Não acessa disco, não dispara detecção, não chama
        backend e não aplica perfil. Nada acontece se o modo não mudou.
        """
        if self._profile_layout_wide == wide:
            return
        altura = _PROFILE_HEIGHT_WIDE if wide else _PROFILE_HEIGHT_COMPACT
        for idx, perfil in enumerate(self._profile_layout_order):
            btn = self._profile_buttons[perfil]
            if wide:
                linha, coluna = 0, idx
            else:
                linha, coluna = idx // 2, idx % 2
            self._profile_grid.removeWidget(btn)
            self._profile_grid.addWidget(btn, linha, coluna)
            # Largura mínima 0: permite o grid distribuir e encolher quando a
            # janela é estreita (sem overflow estrutural). A altura garante o
            # texto completo visível verticalmente.
            btn.setMinimumSize(0, altura)
        self._profile_grid.setColumnStretch(0, 1)
        self._profile_grid.setColumnStretch(1, 1)
        if wide:
            self._profile_grid.setColumnStretch(2, 1)
            self._profile_grid.setColumnStretch(3, 1)
        else:
            self._profile_grid.setColumnStretch(2, 0)
            self._profile_grid.setColumnStretch(3, 0)
        self._profile_layout_wide = wide
        self._profile_grid.invalidate()

    def _atualizar_layout_responsivo(self) -> None:
        """Decide o modo a partir da largura REAL da página (não do monitor)."""
        if not self._profile_buttons:
            return
        self._aplicar_layout_perfis(self.width() >= PROFILE_LAYOUT_BREAKPOINT)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """Somente reorganiza o grid de perfil conforme a largura disponível."""
        super().resizeEvent(event)
        self._atualizar_layout_responsivo()

    def _card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("DgvoodooCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(7)
        heading = QLabel(title)
        heading.setObjectName("DgvoodooCardTitle")
        layout.addWidget(heading)
        self.content_layout.addWidget(card)
        return card, layout

    # ------------------------------------------------------------------
    # QSS
    # ------------------------------------------------------------------

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QWidget#DgvoodooPage, QWidget#DgvoodooContent,
            QScrollArea#DgvoodooScroll, QScrollArea#DgvoodooScroll > QWidget > QWidget {
                background-color: transparent;
            }
            QLabel#DgvoodooTitle { color: white; font-size: 20px; font-weight: bold; }
            QLabel#DgvoodooDescription { color: #A0A0B0; font-size: 13px; }
            QFrame#DgvoodooCard { background-color: rgba(255,255,255,10);
                border: 1px solid rgba(255,255,255,16); border-radius: 12px; }
            QLabel#DgvoodooCardTitle { color: #BF00FF; font-size: 11px; font-weight: bold; }
            QLabel#DgvoodooIndicator { font-size: 16px; font-weight: bold; }
            QLabel#DgvoodooStatus { color: white; font-size: 15px; font-weight: bold; }
            QLabel#DgvoodooDetail { color: #A0A0B0; font-size: 12px; }
            QFrame#DgvoodooInfoBox { background: rgba(0,0,0,45);
                border: 1px solid rgba(255,255,255,16); border-radius: 8px; }
            QLabel#DgvoodooInfoLabel { color: #8A8A9A; font-size: 10px; font-weight: bold; }
            QLabel#DgvoodooInfoValue { color: #D8D8E3; font-size: 12px; }
            QLabel#DgvoodooAbout { color: #CFC4D8; background: rgba(191,0,255,18);
                border-left: 3px solid #BF00FF; padding: 8px;
                font-size: 11px; }
            QPushButton#DgvoodooSecondaryButton { background: rgba(77,0,128,90); color: #E6E6F0;
                border: 1px solid rgba(191,0,255,90); border-radius: 7px;
                padding: 7px 12px; font-size: 11px; font-weight: bold; }
            QPushButton#DgvoodooSecondaryButton:hover { border-color: #BF00FF; }
            QPushButton#DgvoodooSecondaryButton:disabled { background: #29292F; color: #666;
                border-color: #3A3A42; }
            QPushButton#DgvoodooPrimaryButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #BF00FF, stop:1 #7A1FA8); color: white; border: 1px solid #BF00FF;
                border-radius: 9px; padding: 11px; font-size: 13px; font-weight: bold; }
            QPushButton#DgvoodooPrimaryButton:hover { border-color: #E066FF; }
            QPushButton#DgvoodooPrimaryButton:disabled { background: #29292F; color: #666;
                border-color: #3A3A42; }
            QPushButton#DgvoodooMiniButton { background: rgba(191,0,255,22);
                color: #D9C4EA; border: 1px solid rgba(191,0,255,80);
                border-radius: 12px; padding: 3px 10px; font-size: 10px;
                font-weight: 600; }
            QPushButton#DgvoodooMiniButton:hover { border-color: #BF00FF;
                color: #F0E2FA; background: rgba(191,0,255,30); }
            QPushButton#DgvoodooMiniButton:disabled { color: #6A6A7A;
                border-color: #3A3A42; background: transparent; }
            QPushButton#ProfileCardButton { background: rgba(0,0,0,45);
                border: 1px solid rgba(255,255,255,16); border-radius: 12px;
                padding: 0px; }
            QPushButton#ProfileCardButton:hover { border-color: #A55BD9;
                background: rgba(191,0,255,10); }
            QPushButton#ProfileCardButton:checked { border: 2px solid #BF00FF;
                background: rgba(191,0,255,24); }
            QLabel#ProfileCardIcon, QLabel#ProfileCardTitle,
            QLabel#ProfileCardDescription, QLabel#ProfileCardBadge {
                background: transparent; border: none; }
            QLabel#ProfileCardTitle { color: #FFFFFF; font-size: 12px;
                font-weight: 700; }
            QLabel#ProfileCardDescription { color: #A6A6B6; font-size: 11px;
                font-weight: 400; }
            QLabel#ProfileCardTitle:disabled { color: #666; }
            QLabel#ProfileCardDescription:disabled { color: #555; }
            QLabel#ProfileCardBadge { color: #EAD9F7; font-size: 9px;
                font-weight: bold; background: rgba(191,0,255,42);
                border: 1px solid rgba(191,0,255,110); border-radius: 9px;
                padding: 1px 10px; }
            QFrame#DgvoodooHardwareCell { background: rgba(0,0,0,40);
                border: 1px solid rgba(255,255,255,12); border-radius: 8px; }
            QLabel#DgvoodooHardwareLabel { color: #8A8A9A; font-size: 9px;
                font-weight: bold; }
            QLabel#DgvoodooHardwareInfo { color: #D8D8E3; font-size: 12px;
                background: transparent; }
            QLabel#DgvoodooHardwareRecValue { color: #E6C3F7; font-size: 13px;
                font-weight: 700; background: transparent; }
            QLabel#DgvoodooHardwareConfValue { color: #E8E8F0; font-size: 13px;
                font-weight: 600; background: transparent; }
            QLabel#DgvoodooHwIcon { background: transparent; }
            QLabel#DgvoodooProfileStatus { color: #A0A0B0; font-size: 11px; }
        """)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def refresh_estado(self) -> None:
        """Detecta o estado atual e atualiza a UI."""
        detection = backend.detectar_estado()
        self._last_detection = detection
        self._render_state(detection)

    def set_busy(self, busy: bool) -> None:
        """Desabilita/habilita botões durante operações em background."""
        self._busy = busy
        self._update_buttons()

    def do_activate(self) -> None:
        """Executa a ativação (pode rodar em background via executor)."""
        self._safe_call("Ativando", backend.ativar_dgvoodoo)

    def do_restore(self) -> None:
        """Executa a restauração (pode rodar em background via executor)."""
        self._safe_call("Restaurando", backend.restaurar_directx_original)

    def do_detect_hardware(self) -> None:
        """Executa a detecção de hardware no worker (resultado via signal)."""
        try:
            resultado = hd.detectar_hardware()
        except Exception:  # noqa: BLE001
            resultado = None
        # Entrega na UI thread (queued quando emitido de outra thread).
        self.hardware_detected.emit(resultado)

    def do_apply_profile(self) -> None:
        """Aplica o perfil gráfico selecionado (pode rodar em background)."""
        perfil = self._profile_selected
        if perfil == backend.PERFIL_AUTO:
            resolved = self._resolved_profile_aplicar()
            if resolved is None:
                self.log_emitted.emit(
                    "[AVISO] Detecte/reanalise o hardware antes de aplicar AUTO."
                )
                return
            nome = backend.PERFIL_NOME_EXIBICAO.get(resolved, resolved)

            def operacao_auto():
                return backend.aplicar_perfil(
                    backend.PERFIL_AUTO, resolved_profile=resolved
                )

            self._safe_call(f"Aplicando perfil AUTO → {nome}", operacao_auto)
            return
        nome = backend.PERFIL_NOME_EXIBICAO.get(perfil, perfil)

        def operacao():
            return backend.aplicar_perfil(perfil)

        self._safe_call(f"Aplicando perfil {nome}", operacao)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot()
    def _on_activate_clicked(self) -> None:
        if self._busy:
            return
        if self.executor is not None:
            self.executor(self.do_activate)
        else:
            self.do_activate()

    @Slot()
    def _on_restore_clicked(self) -> None:
        if self._busy:
            return
        if self.executor is not None:
            self.executor(self.do_restore)
        else:
            self.do_restore()

    @Slot()
    def _on_profile_selected(self, perfil: str) -> None:
        """Seleciona um card de perfil (não aplica automaticamente nada)."""
        if self._busy or self._hardware_detecting:
            return
        self._profile_selected = perfil
        if perfil == backend.PERFIL_AUTO:
            if self._hardware_profile is not None:
                # Cache da sessão: exibir o resultado existente sem redetectar.
                self._mostrar_resultado_hardware(self._hardware_profile)
            else:
                self._iniciar_deteccao_hardware()
        self._sync_profile_status()
        self._update_buttons()

    @Slot()
    def _on_apply_profile_clicked(self) -> None:
        if self._busy or self._hardware_detecting:
            return
        if self.executor is not None:
            self.executor(self.do_apply_profile)
        else:
            self.do_apply_profile()

    @Slot()
    def _on_reanalyze_clicked(self) -> None:
        """Executa nova detecção de hardware (nova leitura, sem cache)."""
        if self._busy or self._hardware_detecting:
            return
        self._hardware_profile = None
        self._iniciar_deteccao_hardware()

    @Slot(object)
    def _on_hardware_detected(self, resultado) -> None:
        """Recebe o resultado da detecção na UI thread e atualiza os widgets."""
        self._hardware_detecting = False
        self._hardware_profile = resultado
        if resultado is None:
            self.log_emitted.emit("[ERRO] Falha na detecção de hardware.")
            self._exibir_falha_hardware()
        else:
            recomendado = getattr(resultado, "recommended_profile", None)
            confianca = getattr(resultado, "confidence", "")
            if recomendado in backend.PERFIS_SUPORTADOS:
                nome = backend.PERFIL_NOME_EXIBICAO.get(recomendado, recomendado)
                self.log_emitted.emit(
                    f"[INFO] AUTO recomenda: {nome} (confiança {confianca})."
                )
            self._mostrar_resultado_hardware(resultado)
        self._sync_profile_status()
        self._update_buttons()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _safe_call(self, label: str, operation: Callable[[], backend.ResultadoOperacao]) -> None:
        self.log_emitted.emit(f"[INFO] {label} dgVoodoo2...")
        try:
            result = operation()
        except Exception as exc:  # noqa: BLE001
            self.log_emitted.emit(f"[ERRO] {label} falhou: {exc}")
            self.refresh_estado()
            return
        if result.ok:
            self.log_emitted.emit(f"[OK] {result.mensagem}")
        else:
            self.log_emitted.emit(f"[ERRO] {result.mensagem}")
        self.refresh_estado()
    # ------------------------------------------------------------------
    # Detecção de hardware (modo AUTO) — cache apenas na sessão
    # ------------------------------------------------------------------

    def _iniciar_deteccao_hardware(self) -> None:
        """Dispara a detecção pelo executor; NADA é aplicado no cliente."""
        if self._busy or self._hardware_detecting:
            return
        self._hardware_detecting = True
        self.log_emitted.emit("[INFO] Detectando hardware gráfico...")
        self._mostrar_detectando_hardware()
        if self.executor is not None:
            self.executor(self.do_detect_hardware)
        else:
            self.do_detect_hardware()
        self._update_buttons()

    def _resolved_profile_aplicar(self) -> Optional[str]:
        """Perfil resolvido para aplicar AUTO (detecção > estado persistido)."""
        hp = self._hardware_profile
        if hp is not None:
            rec = getattr(hp, "recommended_profile", None)
            if rec in backend.PERFIS_SUPORTADOS:
                return rec
        estado = getattr(self._last_detection, "estado_persistido", None)
        if isinstance(estado, dict):
            res = estado.get("resolved_profile")
            if res in backend.PERFIS_SUPORTADOS:
                return res
        return None

    @staticmethod
    def _gpu_principal(profile) -> Optional[object]:
        """GPU que motivou a recomendação (dGPU com mais VRAM, senão a 1ª)."""
        gpus = getattr(profile, "gpus", None) or []
        dedicadas = [g for g in gpus if getattr(g, "dedicated", False) is True]
        grupo = dedicadas or gpus
        if not grupo:
            return None
        return max(grupo, key=lambda g: getattr(g, "vram_mb", None) or 0)

    @staticmethod
    def _formatar_vram_mb(vram_mb) -> str:
        """Formata VRAM em GB aproximado (~6.0 GB), ou 'não informada'."""
        try:
            valor = int(vram_mb)
        except (TypeError, ValueError):
            return "não informada"
        if valor <= 0:
            return "não informada"
        return f"~{valor / 1024:.1f} GB"

    # Cores de confiança (reaproveitam a paleta de status da própria página).
    _CONFIANCA_CORES = {
        "alta": "#4CAF50",   # verde (mesmo do estado dgVoodoo2 Ativo)
        "média": "#FF9800",  # âmbar (mesmo dos estados CONFLITO/INCOMPLETO)
        "media": "#FF9800",
        "baixa": "#F44336",  # alerta (mesmo dos estados ERRO/MODIFICADO)
    }

    def _estilizar_confianca(self) -> None:
        """Aplica cor de estado ao valor de confiança (sem virar semáforo)."""
        texto = (self.hw_confianca_label.text() or "").strip().lower()
        cor = self._CONFIANCA_CORES.get(texto, "")
        if cor:
            self.hw_confianca_label.setStyleSheet(f"color: {cor};")
        else:
            self.hw_confianca_label.setStyleSheet("")

    def _mostrar_detectando_hardware(self) -> None:
        """Estado 'analisando' do card (card é permanente; nunca some)."""
        self.hw_gpu_label.setText("Analisando...")
        self.hw_vram_label.setText("—")
        self.hw_recomendacao_label.setText("Analisando...")
        self.hw_confianca_label.setText("—")
        self._estilizar_confianca()
        self.reanalyze_button.setEnabled(False)

    def _mostrar_resultado_hardware(self, profile) -> None:
        """Exibe GPU/VRAM/Recomendação/Confiança no card HARDWARE DETECTADO."""
        self.reanalyze_button.setEnabled(True)
        recomendado = getattr(profile, "recommended_profile", None)
        if recomendado not in backend.PERFIS_SUPORTADOS:
            recomendado = backend.PERFIL_BALANCED
        confianca = str(getattr(profile, "confidence", "") or "")

        gpu = self._gpu_principal(profile)
        if gpu is not None and getattr(gpu, "name", ""):
            self.hw_gpu_label.setText(gpu.name)
            self.hw_vram_label.setText(
                self._formatar_vram_mb(getattr(gpu, "vram_mb", None))
            )
        else:
            self.hw_gpu_label.setText("não identificada")
            self.hw_vram_label.setText("não informada")

        nome_rec = backend.PERFIL_NOME_EXIBICAO.get(recomendado, recomendado)
        if confianca.upper() == hd.CONFIANCA_BAIXA:
            self.hw_recomendacao_label.setText(
                "Equilibrado (por segurança) — não foi possível "
                "identificar completamente o hardware."
            )
            self.hw_confianca_label.setText("Baixa")
        else:
            self.hw_recomendacao_label.setText(nome_rec)
            conf_nome = {
                hd.CONFIANCA_ALTA: "Alta",
                hd.CONFIANCA_MEDIA: "Média",
                hd.CONFIANCA_BAIXA: "Baixa",
            }.get(confianca.upper(), confianca)
            self.hw_confianca_label.setText(conf_nome)
        self._estilizar_confianca()

    def _exibir_falha_hardware(self) -> None:
        """Falha/fallback elegante (sem traceback): hardware parcialmente visto."""
        self.reanalyze_button.setEnabled(True)
        self.hw_gpu_label.setText("Hardware parcialmente identificado")
        self.hw_vram_label.setText("—")
        self.hw_recomendacao_label.setText("Equilibrado")
        self.hw_confianca_label.setText("Baixa")
        self._estilizar_confianca()



    def _render_state(self, detection: backend.EstadoDetectado) -> None:
        estado = detection.estado
        indicator_color, text_color = STATE_COLORS.get(
            estado, ("#9E9E9E", "#F5F5F5")
        )
        self.status_indicator.setStyleSheet(f"color: {indicator_color};")
        self.status_label.setStyleSheet(f"color: {text_color};")

        status_text, detail = self._describe(estado, detection)
        self.status_label.setText(status_text)
        self.status_detail.setText(detail)

        if estado == backend.Estado.ATIVO:
            self.backend_value.setText("DirectX 11")
            self.info_card.show()
        elif estado == backend.Estado.ORIGINAL:
            self.backend_value.setText("DirectX 9")
            self.info_card.show()
        else:
            self.backend_value.setText("\u2014")
            self.info_card.hide()

        # Perfil aplicado (persistido): escolha (auto/manual) + efetivo.
        estado_persistido = detection.estado_persistido
        if estado == backend.Estado.ATIVO and isinstance(estado_persistido, dict):
            self._profile_applied = backend._perfil_escolhido_estado(estado_persistido)
            self._profile_applied_resolved = backend._perfil_efetivo_estado(
                estado_persistido
            )
        self.perfil_value.setText(self._descrever_aplicado())
        self._mark_profile_applied(self._profile_applied)
        self._sync_profile_status()

        self._update_buttons(estado)

    def _descrever_aplicado(self) -> str:
        """Texto 'Perfil atual': AUTO → Efetivo, ou nome do perfil manual."""
        if self._profile_applied == backend.PERFIL_AUTO:
            resolvido = self._profile_applied_resolved
            nome_resolvido = backend.PERFIL_NOME_EXIBICAO.get(
                resolvido, resolvido or backend.PERFIL_BALANCED
            )
            return f"AUTO → {nome_resolvido}"
        return backend.PERFIL_NOME_EXIBICAO.get(
            self._profile_applied, self._profile_applied
        )

    def _descrever_selecionado(self) -> str:
        """Texto da seleção atual (AUTO mostra a recomendação quando houver)."""
        if self._profile_selected == backend.PERFIL_AUTO:
            resolved = self._resolved_profile_aplicar()
            if resolved is not None:
                nome_resolvido = backend.PERFIL_NOME_EXIBICAO.get(resolved, resolved)
                return f"AUTO → {nome_resolvido}"
            return "AUTO"
        return backend.PERFIL_NOME_EXIBICAO.get(
            self._profile_selected, self._profile_selected
        )

    def _mark_profile_applied(self, perfil_escolhido: str) -> None:
        """Marca o card correspondente à ESCOLHA aplicada e sincroniza."""
        self._profile_selected = perfil_escolhido
        for p, btn in getattr(self, "_profile_buttons", {}).items():
            btn.setChecked(p == perfil_escolhido)

    def _sync_profile_status(self) -> None:
        """Exibe o perfil aplicado versus o selecionado (sem aplicar nada)."""
        nome_aplicado = self._descrever_aplicado()
        nome_selecionado = self._descrever_selecionado()
        if self._profile_selected == self._profile_applied:
            self.profile_status.setText(f"Perfil atual: {nome_aplicado}")
        else:
            self.profile_status.setText(
                f"Perfil atual: {nome_aplicado}  ·  Selecionado: {nome_selecionado}"
                "  (clique em APLICAR PERFIL para ativar)"
            )

    def _update_buttons(self, estado: Optional[backend.Estado] = None) -> None:
        if estado is None:
            estado = getattr(self._last_detection, "estado", None)

        busy = self._busy
        detectando = self._hardware_detecting

        can_activate = estado in (
            backend.Estado.ORIGINAL,
            backend.Estado.INCOMPLETO,
        )
        self.activate_button.setEnabled(can_activate and not busy and not detectando)
        self.activate_button.setText(
            "APLICANDO..." if busy and can_activate else "ATIVAR DGVOODOO2"
        )

        can_reapply = estado in (
            backend.Estado.ATIVO,
            backend.Estado.INCOMPLETO,
        )
        self.reapply_button.setEnabled(can_reapply and not busy and not detectando)
        self.reapply_button.setText(
            "APLICANDO..." if busy and can_reapply else "REAPLICAR"
        )

        can_restore = estado in (
            backend.Estado.ATIVO,
            backend.Estado.INCOMPLETO,
            backend.Estado.MODIFICADO_EXTERNAMENTE,
        )
        self.restore_button.setEnabled(can_restore and not busy and not detectando)
        self.restore_button.setText(
            "RESTAURANDO..." if busy and can_restore else "RESTAURAR DIRECTX ORIGINAL"
        )

        # Aplicar perfil: exige dgVoodoo ATIVO. AUTO exige resolved disponível.
        can_apply = estado == backend.Estado.ATIVO
        if self._profile_selected == backend.PERFIL_AUTO:
            can_apply = can_apply and self._resolved_profile_aplicar() is not None
        self.apply_profile_button.setEnabled(
            can_apply and not busy and not detectando
        )
        self.apply_profile_button.setText(
            "APLICANDO..." if busy and can_apply else "APLICAR PERFIL"
        )
        for btn in getattr(self, "_profile_buttons", {}).values():
            btn.setEnabled(not busy and not detectando)

        # Reanalisar hardware: habilitado sempre que não há operação em curso.
        if hasattr(self, "reanalyze_button"):
            self.reanalyze_button.setEnabled(not busy and not detectando)

    @staticmethod
    def _describe(estado: backend.Estado, detection: backend.EstadoDetectado) -> tuple[str, str]:
        if estado == backend.Estado.ORIGINAL:
            return (
                "DirectX 9 Original",
                "O AIKA está utilizando o renderizador padrão.",
            )
        if estado == backend.Estado.ATIVO:
            return (
                "dgVoodoo2 Ativo",
                "O AIKA está utilizando o dgVoodoo2.",
            )
        if estado == backend.Estado.CONFLITO:
            return (
                "Outro d3d9.dll detectado",
                detection.mensagem or "O Optimizer não substituirá esse arquivo automaticamente.",
            )
        if estado == backend.Estado.INCOMPLETO:
            return (
                "Instalação incompleta",
                detection.mensagem or "Arquivos esperados estão ausentes ou inconsistentes.",
            )
        if estado == backend.Estado.MODIFICADO_EXTERNAMENTE:
            return (
                "Arquivos modificados externamente",
                detection.mensagem or "O Optimizer não fará restauração automática para evitar perda de dados.",
            )
        if estado == backend.Estado.TEMPLATE_AUSENTE:
            return (
                "dgVoodoo2 não encontrado",
                detection.mensagem or "A instalação do AIKA Optimizer pode estar incompleta.",
            )
        if estado == backend.Estado.JOGO_ABERTO:
            return (
                "Jogo em execução",
                detection.mensagem or "Feche o AIKA e o launcher antes de alterar o renderizador.",
            )
        return (
            "Erro",
            detection.mensagem or "Não foi possível determinar o estado do renderizador.",
        )

    def showEvent(self, event):  # type: ignore[no-untyped-def]
        super().showEvent(event)
        self._atualizar_layout_responsivo()
        if not self._busy:
            QTimer.singleShot(0, self.refresh_estado)
        # Detecção automática de hardware: somente na primeira exibição da
        # página na sessão (uma vez por instância). Usa o fluxo assíncrono
        # existente; nada é aplicado no cliente.
        if (not self._hardware_initial_requested
                and not self._hardware_detecting
                and not self._busy
                and self._hardware_profile is None):
            self._hardware_initial_requested = True
            QTimer.singleShot(0, self._iniciar_deteccao_hardware)



