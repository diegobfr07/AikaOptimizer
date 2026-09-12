# -*- coding: utf-8 -*-
"""Lista ordenável da Restauração, inspirada no modo Detalhes do Windows Explorer.

Módulo de apresentação pura: transforma operações do histórico e o estado de
Cores das Pedras em linhas ordenáveis, sem tocar em backups, metadados ou na
lógica de restauração. As ações permanecem vinculadas ao ``operation_id``
estável e ao cliente, nunca ao número visual da linha.
"""

from __future__ import annotations

import os
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHeaderView,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
)

from stone_color_service import (
    KIND_BASE,
    KIND_EXTERNAL_COMPATIBLE,
    KIND_EXTERNAL_INCOMPATIBLE,
    KIND_PERSONALIZED,
)

COL_CHECKBOX = 0
COL_NOME = 1
COL_TIPO = 2
COL_MODIFICACAO = 3
COL_DATA = 4
COL_ACAO = 5

COLUNAS = ["", "Nome / arquivo", "Tipo", "Modificação", "Data do backup", "Ação"]
SORTABLE = (COL_NOME, COL_TIPO, COL_MODIFICACAO, COL_DATA)
SELECT_ALL_TOOLTIP = "Selecionar todas as operações disponíveis neste filtro"
RESTORE_ROW_HEIGHT = 36
RESTORE_BUTTON_MIN_HEIGHT = 28
RESTORE_BUTTON_HORIZONTAL_SPACE = 28
RESTORE_ACTION_CELL_MARGIN = 8
RESTORE_ACTION_MIN_WIDTH = 112


def operation_key(client_root: Any, operation_id: Any) -> tuple[str, str]:
    """Identidade visual estável; evita colisões entre clientes distintos."""
    return str(client_root or ""), str(operation_id or "")


def extensao_normalizada(nome: Any) -> str:
    if not nome:
        return ""
    return os.path.splitext(str(nome))[1].lower()


def _nome_item(item: dict) -> str:
    nome = item.get("target_name") or ""
    if not nome:
        rel = (item.get("target_relpath") or item.get("chave") or "").replace("\\", "/")
        nome = os.path.basename(rel)
    return nome


def _resumo_tipo(operacao: dict) -> str:
    tipo = str(operacao.get("operation_type") or "").upper()
    return {
        "SET_INJECTION": "Injetor Sets/Arm",
        "WEAPON_INJECTION": "Injetor Sets/Arm",
        "AUTOMOD": "AutoMod",
        "REMOVE_POLLUTED_EFFECTS": "Remoção de efeitos poluídos",
        "AUDIO": "Áudio",
        "TEXTURE": "Textura",
        "LEGACY": "Modificação antiga",
    }.get(tipo, "Modificação")


def _modificacao_operacao(operacao: dict) -> str:
    tipo = str(operacao.get("operation_type") or "").upper()
    if tipo == "REMOVE_POLLUTED_EFFECTS":
        return "Remoção de efeitos poluídos"
    if tipo == "AUTOMOD":
        return "AutoMod — substituição"
    if tipo in ("SET_INJECTION", "WEAPON_INJECTION"):
        return "Injetor Sets/Arm — substituição"
    if tipo == "AUDIO":
        return "Áudio — substituição"
    if tipo == "TEXTURE":
        return "Textura — substituição"
    if operacao.get("legacy"):
        return "Modificação antiga"
    return "Modificação"


def _nome_arquivo_operacao(operacao: dict) -> str:
    items = operacao.get("items") or []
    if len(items) == 1:
        return _nome_item(items[0]) or "Arquivo"
    return f"{_resumo_tipo(operacao)} — {len(items)} arquivos"


def _tipo_operacao(operacao: dict) -> str:
    items = operacao.get("items") or []
    exts = {extensao_normalizada(_nome_item(i)) for i in items}
    exts.discard("")
    if not exts:
        return ""
    if len(exts) == 1:
        return next(iter(exts))
    return "Vários"


def _tooltip_operacao(operacao: dict) -> str:
    items = operacao.get("items") or []
    if len(items) == 1:
        item = items[0]
        rel = (item.get("target_relpath") or item.get("chave") or "").replace("\\", "/")
        return rel or _nome_item(item)
    linhas = []
    for item in items:
        rel = (item.get("target_relpath") or item.get("chave") or "").replace("\\", "/")
        linhas.append(rel or _nome_item(item))
    return "\n".join(linhas)


def _data_display(timestamp: Any) -> str:
    ts = str(timestamp or "")
    if not ts:
        return "Não informada"
    try:
        ano, mes, dia = ts[0:4], ts[5:7], ts[8:10]
        if not (ano.isdigit() and mes.isdigit() and dia.isdigit()):
            return "Não informada"
        horario = ts[11:16] if len(ts) >= 16 else ""
        return f"{dia}/{mes}/{ano} {horario}".strip()
    except Exception:
        return "Não informada"


def build_operation_row(operacao: dict) -> dict:
    """Constrói a linha de uma operação do histórico (com metadados estáveis)."""
    timestamp = str(operacao.get("operation_timestamp") or "")
    modificacao = _modificacao_operacao(operacao)
    tipo = _tipo_operacao(operacao)
    return {
        "kind": "operation",
        "operation_id": operacao["operation_id"],
        "client_root": operacao.get("game_root") or "",
        "name": _nome_arquivo_operacao(operacao),
        "tipo": tipo,
        "modificacao": modificacao,
        "data_display": _data_display(timestamp),
        "sort_name": _nome_arquivo_operacao(operacao).lower(),
        "sort_tipo": tipo,
        "sort_modificacao": modificacao.lower(),
        "sort_data": timestamp,
        "tooltip": _tooltip_operacao(operacao),
        "checkable": True,
        "restorable": True,
        "button_text": "Restaurar",
    }


def _base_correspondente(rec, bases):
    """Base vinculada ao estado atual (nunca a mais recente por data)."""
    if rec is None:
        return None
    base_sha = rec.base_sha256
    if not base_sha and getattr(rec, "kind", "") == KIND_BASE:
        base_sha = rec.file_sha256
    if base_sha:
        for base in bases:
            if base.get("sha256") == base_sha:
                return base
    return None


def _pedras_estado(rec, bases, processo_aberto):
    if not bases:
        return "Base indisponível", False
    if rec is None:
        return "Base indisponível", False
    if rec.kind == KIND_PERSONALIZED:
        if not getattr(rec, "base_valid", True):
            return "Base indisponível", False
        if processo_aberto:
            return "Feche o jogo e o launcher para restaurar", False
        return "Personalização reconhecida", True
    if rec.kind == KIND_BASE:
        return "Já restaurado", False
    if rec.kind in (KIND_EXTERNAL_COMPATIBLE, KIND_EXTERNAL_INCOMPATIBLE):
        return "Sem personalização registrada", False
    return "Base indisponível", False


def build_pedras_row(resumo, processo_aberto=False) -> dict:
    """Constrói a linha de Cores das Pedras a partir do resumo do serviço."""
    resumo = resumo or {}
    rec = resumo.get("recognition")
    bases = resumo.get("bases") or []
    base = _base_correspondente(rec, bases)
    data_ts = (base.get("captured_at") or "") if base else ""
    estado, restorable = _pedras_estado(rec, bases, processo_aberto)
    return {
        "kind": "pedras",
        "operation_id": "pedras",
        "client_root": resumo.get("client_root") or "",
        "name": "ItemList6.bin",
        "tipo": ".bin",
        "modificacao": "Cores das Pedras",
        "data_display": _data_display(data_ts),
        "sort_name": "itemlist6.bin",
        "sort_tipo": ".bin",
        "sort_modificacao": "cores das pedras",
        "sort_data": data_ts,
        "tooltip": resumo.get("target") or "",
        "checkable": False,
        "restorable": restorable,
        "button_text": "Restaurar",
        "pedras_state": estado,
    }


class _SortItem(QTreeWidgetItem):
    def __init__(self, stable_key: str, *args):
        super().__init__(*args)
        self._stable_key = stable_key

    def __lt__(self, other):
        tree = self.treeWidget()
        col = tree.sortColumn() if tree is not None else COL_DATA
        if col not in SORTABLE:
            col = COL_DATA
        a = self.data(col, Qt.UserRole)
        b = other.data(col, Qt.UserRole)
        a = "" if a is None else a
        b = "" if b is None else b
        if a == b:
            return self._stable_key < other._stable_key
        return a < b


class _MasterCheckBox(QCheckBox):
    """Checkbox tri-state cujo clique parcial seleciona tudo diretamente."""

    def nextCheckState(self):
        novo = Qt.Unchecked if self.checkState() == Qt.Checked else Qt.Checked
        self.setCheckState(novo)


class RestoreHeader(QHeaderView):
    selecionar_todas = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.checkbox_mestre = _MasterCheckBox(self)
        self.checkbox_mestre.setObjectName("RestoreSelectAllCheckBox")
        self.checkbox_mestre.setTristate(True)
        self.checkbox_mestre.setAccessibleName(SELECT_ALL_TOOLTIP)
        self.checkbox_mestre.setToolTip(SELECT_ALL_TOOLTIP)
        self.checkbox_mestre.setCursor(Qt.PointingHandCursor)
        self.checkbox_mestre.setFixedSize(22, 22)
        self.checkbox_mestre.clicked.connect(self._checkbox_clicado)
        self.sectionResized.connect(lambda *_: self._reposicionar_checkbox())

    def _checkbox_clicado(self, _marcado=False):
        self.selecionar_todas.emit(self.checkbox_mestre.checkState() == Qt.Checked)

    def atualizar_estado(self, marcados, total):
        self.checkbox_mestre.setEnabled(total > 0)
        if not total or not marcados:
            estado = Qt.Unchecked
        elif marcados == total:
            estado = Qt.Checked
        else:
            estado = Qt.PartiallyChecked
        self.checkbox_mestre.setCheckState(estado)

    def _reposicionar_checkbox(self):
        if self.count() <= COL_CHECKBOX:
            return
        largura = self.sectionSize(COL_CHECKBOX)
        x = self.sectionViewportPosition(COL_CHECKBOX)
        x += max(0, (largura - self.checkbox_mestre.width()) // 2)
        y = max(0, (self.height() - self.checkbox_mestre.height()) // 2)
        self.checkbox_mestre.move(x, y)
        self.checkbox_mestre.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposicionar_checkbox()

    def showEvent(self, event):
        super().showEvent(event)
        self._reposicionar_checkbox()


class RestoreRowButton(QPushButton):
    """Botão com size hint compatível com fonte, padding, borda e linha compacta."""

    def sizeHint(self):
        hint = super().sizeHint()
        largura = max(
            hint.width(),
            self.fontMetrics().horizontalAdvance(self.text())
            + RESTORE_BUTTON_HORIZONTAL_SPACE,
            RESTORE_ACTION_MIN_WIDTH - RESTORE_ACTION_CELL_MARGIN,
        )
        return QSize(largura, max(hint.height(), RESTORE_BUTTON_MIN_HEIGHT))

    def minimumSizeHint(self):
        return self.sizeHint()


class RestoreListWidget(QTreeWidget):
    selecao_alterada = Signal(object, bool)
    selecao_em_lote = Signal(object, bool)
    restaurar_operacao = Signal(object)
    restaurar_pedras = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeader(RestoreHeader(self))
        self.setColumnCount(len(COLUNAS))
        self.setHeaderLabels(COLUNAS)
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setSelectionMode(QTreeWidget.NoSelection)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._populating = False
        self._sort_column = COL_DATA
        self._sort_order = Qt.DescendingOrder

        header = self.header()
        header.setSectionResizeMode(COL_CHECKBOX, QHeaderView.Fixed)
        header.setSectionResizeMode(COL_NOME, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_TIPO, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_MODIFICACAO, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_DATA, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_ACAO, QHeaderView.Fixed)
        header.setStretchLastSection(False)
        self.setColumnWidth(COL_CHECKBOX, 30)
        self.setColumnWidth(COL_ACAO, RESTORE_ACTION_MIN_WIDTH)

        self.itemChanged.connect(self._on_item_changed)
        header.selecionar_todas.connect(self._selecionar_todas)
        self.sortByColumn(self._sort_column, self._sort_order)

    def sortByColumn(self, column, order):
        if column not in SORTABLE:
            return
        self._sort_column = column
        self._sort_order = order
        super().sortByColumn(column, order)

    def populate(self, rows, selected_keys=None):
        selected_keys = set(selected_keys or ())
        self._populating = True
        try:
            self.clear()
            if not rows:
                self._add_vazio()
            else:
                for row in rows:
                    self._add_row(row, selected_keys)
        finally:
            self._populating = False
        self.sortByColumn(self._sort_column, self._sort_order)
        self.atualizar_checkbox_mestre()

    def _add_vazio(self):
        item = _SortItem("")
        item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
        item.setText(COL_NOME, "Nenhum backup para o filtro/cliente selecionado.")
        item.setText(COL_MODIFICACAO, "")
        item.setSizeHint(COL_NOME, QSize(0, RESTORE_ROW_HEIGHT))
        self.addTopLevelItem(item)

    def _add_row(self, row, selected_keys):
        stable_key = operation_key(row.get("client_root"), row.get("operation_id"))
        item = _SortItem("\x00".join(stable_key))
        item.setData(COL_CHECKBOX, Qt.UserRole + 1, row.get("operation_id"))
        item.setData(COL_CHECKBOX, Qt.UserRole + 2, row.get("kind"))
        item.setData(COL_CHECKBOX, Qt.UserRole + 3, row.get("client_root") or "")
        item.setData(COL_NOME, Qt.UserRole, row.get("sort_name"))
        item.setData(COL_TIPO, Qt.UserRole, row.get("sort_tipo"))
        item.setData(COL_MODIFICACAO, Qt.UserRole, row.get("sort_modificacao"))
        item.setData(COL_DATA, Qt.UserRole, row.get("sort_data"))

        if row.get("checkable"):
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            estado = Qt.Checked if stable_key in selected_keys else Qt.Unchecked
            item.setCheckState(COL_CHECKBOX, estado)
        else:
            item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
        item.setText(COL_NOME, row.get("name", ""))
        item.setToolTip(COL_NOME, row.get("tooltip", ""))
        item.setText(COL_TIPO, row.get("tipo", ""))
        modificacao = row.get("modificacao", "")
        if row.get("kind") == "pedras" and row.get("pedras_state"):
            modificacao = f"{modificacao} — {row['pedras_state']}"
        item.setText(COL_MODIFICACAO, modificacao)
        item.setToolTip(COL_MODIFICACAO, row.get("pedras_state") or row.get("tooltip", ""))
        item.setText(COL_DATA, row.get("data_display", ""))
        item.setSizeHint(COL_NOME, QSize(0, RESTORE_ROW_HEIGHT))

        btn = RestoreRowButton(row.get("button_text", "Restaurar"))
        btn.setObjectName("RestoreRowButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setEnabled(bool(row.get("restorable")))
        btn.setMinimumHeight(RESTORE_BUTTON_MIN_HEIGHT)
        largura_botao = btn.sizeHint().width()
        btn.setMinimumWidth(largura_botao)
        self.setColumnWidth(
            COL_ACAO,
            max(self.columnWidth(COL_ACAO), largura_botao + RESTORE_ACTION_CELL_MARGIN),
        )
        if row.get("kind") == "pedras":
            btn.clicked.connect(self.restaurar_pedras.emit)
            if not row.get("restorable"):
                btn.setToolTip(row.get("pedras_state") or "")
        else:
            identidade = stable_key
            btn.clicked.connect(
                lambda _checked=False, key=identidade: self.restaurar_operacao.emit(key)
            )
        self.addTopLevelItem(item)
        self.setItemWidget(item, COL_ACAO, btn)

    def _on_item_changed(self, item, column):
        if self._populating:
            return
        if column != COL_CHECKBOX:
            return
        if item.data(COL_CHECKBOX, Qt.UserRole + 2) != "operation":
            return
        identidade = operation_key(
            item.data(COL_CHECKBOX, Qt.UserRole + 3),
            item.data(COL_CHECKBOX, Qt.UserRole + 1),
        )
        elegivel = (
            not item.isHidden()
            and bool(item.flags() & Qt.ItemIsEnabled)
            and bool(item.flags() & Qt.ItemIsUserCheckable)
        )
        marcado = elegivel and item.checkState(COL_CHECKBOX) == Qt.Checked
        if not elegivel and item.checkState(COL_CHECKBOX) != Qt.Unchecked:
            self._populating = True
            try:
                item.setCheckState(COL_CHECKBOX, Qt.Unchecked)
            finally:
                self._populating = False
        self.selecao_alterada.emit(identidade, marcado)
        self.atualizar_checkbox_mestre()

    def _itens_elegiveis(self):
        itens = []
        for indice in range(self.topLevelItemCount()):
            item = self.topLevelItem(indice)
            flags = item.flags()
            if (
                not item.isHidden()
                and item.data(COL_CHECKBOX, Qt.UserRole + 2) == "operation"
                and bool(flags & Qt.ItemIsEnabled)
                and bool(flags & Qt.ItemIsUserCheckable)
            ):
                itens.append(item)
        return itens

    @staticmethod
    def _identidade_item(item):
        return operation_key(
            item.data(COL_CHECKBOX, Qt.UserRole + 3),
            item.data(COL_CHECKBOX, Qt.UserRole + 1),
        )

    def atualizar_checkbox_mestre(self):
        itens = self._itens_elegiveis()
        marcados = sum(
            item.checkState(COL_CHECKBOX) == Qt.Checked for item in itens
        )
        self.header().atualizar_estado(marcados, len(itens))

    def atualizar_elegibilidade(self):
        """Remove da seleção operações que deixaram de ser elegíveis."""
        elegiveis = set(self._itens_elegiveis())
        removidas = set()
        self._populating = True
        try:
            for indice in range(self.topLevelItemCount()):
                item = self.topLevelItem(indice)
                if (
                    item not in elegiveis
                    and item.data(COL_CHECKBOX, Qt.UserRole + 2) == "operation"
                    and item.checkState(COL_CHECKBOX) == Qt.Checked
                ):
                    removidas.add(self._identidade_item(item))
                    item.setCheckState(COL_CHECKBOX, Qt.Unchecked)
        finally:
            self._populating = False
        self.atualizar_checkbox_mestre()
        if removidas:
            self.selecao_em_lote.emit(removidas, False)

    def _selecionar_todas(self, marcado):
        itens = self._itens_elegiveis()
        if not itens:
            self.atualizar_checkbox_mestre()
            return
        estado = Qt.Checked if marcado else Qt.Unchecked
        self._populating = True
        try:
            for item in itens:
                if item.checkState(COL_CHECKBOX) != estado:
                    item.setCheckState(COL_CHECKBOX, estado)
        finally:
            self._populating = False
        identidades = {self._identidade_item(item) for item in itens}
        self.atualizar_checkbox_mestre()
        self.selecao_em_lote.emit(identidades, marcado)

    def operacoes_elegiveis(self):
        return [self._identidade_item(item) for item in self._itens_elegiveis()]

    def operacoes_visiveis(self):
        ids = []
        for indice in range(self.topLevelItemCount()):
            item = self.topLevelItem(indice)
            if item.data(COL_CHECKBOX, Qt.UserRole + 2) == "operation":
                ids.append(operation_key(
                    item.data(COL_CHECKBOX, Qt.UserRole + 3),
                    item.data(COL_CHECKBOX, Qt.UserRole + 1),
                ))
        return ids


