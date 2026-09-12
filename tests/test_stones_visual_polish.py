# -*- coding: utf-8 -*-
"""Refinamento visual final da página Pedras.

Cobre:
- labels visíveis SEM "(W+n)" e valores internos W preservados;
- seletores padrão (Vermelho=8, Roxo=7, Branco=0);
- swatches mantidos;
- contraste do popup do QComboBox (fundo escuro + texto claro).
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import stone_color_page as page_module  # noqa: E402

CODIGO_POR_NOME = {c.name: c.code for c in page_module.CONFIRMED_COLORS}


def _nova_pagina():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    page = page_module.StoneColorPage(
        lambda: None, page_module.DEFAULT_PROFILE_PATH
    )
    return app, page


class TestLabelsSemCodigosInternos(unittest.TestCase):
    """Parte A: a UI mostra apenas o nome da cor; o W interno fica no data."""

    def setUp(self):
        self._cleanup = []
        self.app, self.page = _nova_pagina()
        self._cleanup.append(self.page.deleteLater)

    def tearDown(self):
        for fn in self._cleanup:
            fn()

    def test_01_nenhum_texto_visivel_contem_w(self):
        for combo in (
            self.page.attack_combo,
            self.page.defense_combo,
            self.page.common_combo,
        ):
            for i in range(combo.count()):
                self.assertNotIn("(W+", combo.itemText(i))
                self.assertNotIn("W+", combo.itemText(i))
                self.assertEqual(
                    combo.itemText(i),
                    page_module.CONFIRMED_COLORS[i].name,
                )

    def test_02_vermelho_continua_w8(self):
        self.assertEqual(self.page.attack_combo.currentText(), "Vermelho")
        self.assertEqual(self.page.attack_combo.currentData(), 8)
        idx = self.page.attack_combo.findData(8)
        self.assertEqual(self.page.attack_combo.itemText(idx), "Vermelho")

    def test_03_roxo_continua_w7(self):
        self.assertEqual(self.page.defense_combo.currentText(), "Roxo")
        self.assertEqual(self.page.defense_combo.currentData(), 7)
        idx = self.page.defense_combo.findData(7)
        self.assertEqual(self.page.defense_combo.itemText(idx), "Roxo")

    def test_04_branco_continua_w0(self):
        self.assertEqual(self.page.common_combo.currentText(), "Branco")
        self.assertEqual(self.page.common_combo.currentData(), 0)
        idx = self.page.common_combo.findData(0)
        self.assertEqual(self.page.common_combo.itemText(idx), "Branco")

    def test_05_todas_as_cores_mantem_valores_internos(self):
        combo = self.page.attack_combo
        self.assertEqual(combo.count(), len(page_module.CONFIRMED_COLORS))
        for i, cor in enumerate(page_module.CONFIRMED_COLORS):
            self.assertEqual(combo.itemText(i), cor.name)
            self.assertEqual(combo.itemData(i), cor.code)
        self.assertEqual(
            set(combo.itemData(i) for i in range(combo.count())),
            {0, 4, 5, 6, 7, 8, 9},
        )

    def test_06_swatches_preservados(self):
        combo = self.page.attack_combo
        for i, cor in enumerate(page_module.CONFIRMED_COLORS):
            icone = combo.itemIcon(i)
            self.assertFalse(icone.isNull())
            img = icone.pixmap(16, 16).toImage()
            pixel = img.pixelColor(8, 8).name()
            self.assertEqual(pixel, cor.sample.lower())

    def test_07_selecao_por_nome_nao_gera_w_no_texto(self):
        combo = self.page.attack_combo
        combo.setCurrentIndex(combo.findData(9))
        self.assertEqual(combo.currentText(), "Preto")
        self.assertEqual(combo.currentData(), 9)

    def test_08_restaurar_padroes_mantem_codigos_internos(self):
        for combo, nome in (
            (self.page.attack_combo, "Preto"),
            (self.page.defense_combo, "Amarelo"),
            (self.page.common_combo, "Vermelho"),
        ):
            combo.setCurrentIndex(combo.findData(CODIGO_POR_NOME[nome]))
        self.page.restore_defaults()
        self.assertEqual(self.page.selected_codes(), (8, 7, 0))
        self.assertEqual(self.page.attack_combo.currentText(), "Vermelho")
        self.assertEqual(self.page.defense_combo.currentText(), "Roxo")
        self.assertEqual(self.page.common_combo.currentText(), "Branco")


class TestContrastePopup(unittest.TestCase):
    """Parte B: item view do QComboBox legível no tema escuro."""

    def test_10_qss_local_estiliza_item_view(self):
        app, page = _nova_pagina()
        self.addCleanup(page.deleteLater)
        qss = page.styleSheet()
        self.assertIn("QComboBox QAbstractItemView", qss)
        self.assertIn("background-color: #15151C", qss)
        self.assertIn("color: #ECECF4", qss)
        self.assertIn("selection-background-color: #4D1763", qss)
        self.assertIn("selection-color: #FFFFFF", qss)
        self.assertIn("QComboBox QAbstractItemView::item:hover", qss)
        self.assertIn("QComboBox QAbstractItemView::item:selected", qss)
        self.assertIn("QComboBox QAbstractItemView::item:disabled", qss)

    def test_11_popup_aberto_tem_paleta_clara_sobre_fundo_escuro(self):
        from PySide6.QtGui import QPalette

        app, page = _nova_pagina()
        self.addCleanup(page.deleteLater)
        with patch.object(page, "analyze_again", return_value=False):
            page.resize(900, 700)
            page.show()
            app.processEvents()
            page.attack_combo.showPopup()
            app.processEvents()
            app.processEvents()
            view = page.attack_combo.view()
            pal = view.palette()
            self.assertEqual(pal.color(QPalette.Base).name(), "#15151c")
            self.assertEqual(pal.color(QPalette.Text).name(), "#ececf4")
            self.assertEqual(
                pal.color(QPalette.HighlightedText).name(), "#ffffff"
            )
            page.hide()


if __name__ == "__main__":
    unittest.main(verbosity=2)

