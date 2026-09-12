# -*- coding: utf-8 -*-
"""Seletor SETS/ARMAS do Injetor — botão segmentado sem indicador de radio.

Comprova que o ajuste é apenas visual (QSS localizado em #InjModeBtn):
a seleção exclusiva, os labels por modo e o backend permanecem intactos.
"""
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import main  # noqa: E402
import config  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

_app = QApplication.instance() or QApplication([])

# Mesmo congelamento usado nas fases anteriores (backend intacto).
HASH_SET_INJECTOR = (
    "D2765BBD157138F6A6AD4DB5997AAF69A212118349CD88257B5BFB2727E00919"
)


def _fonte_main():
    return Path(main.__file__).read_text(encoding="utf-8")


def _bloco_injmode():
    """Trecho do QSS que define o seletor SETS/ARMAS (até o botão seguinte)."""
    fonte = _fonte_main()
    inicio = fonte.index("QRadioButton#InjModeBtn {{")
    fim = fonte.index("QPushButton#InjExecBtn {{", inicio)
    return fonte[inicio:fim]


class TestSeletorSetsArmas(unittest.TestCase):
    """Mantém QRadioButton + QButtonGroup, sem indicador visível."""

    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.mkdtemp(prefix="aika_inj_test_")
        with mock.patch.object(main.opt, "obter_pasta_jogo_atual",
                               return_value=cls.pasta), \
             mock.patch.object(config, "ARQUIVO_CONFIG", os.path.join(cls.pasta, "config.json")), \
             mock.patch.object(config, "PASTA_BACKUP", os.path.join(cls.pasta, "backup")), \
             mock.patch.object(config, "PASTA_JOGO_PADRAO", cls.pasta):
            cls.janela = main.AikaOptimizerPro()
        cls.janela._force_exit = True
        cls.janela.setMinimumSize(1, 1)
        cls.janela.resize(1024, 680)
        cls.janela.show()
        cls.janela.telas.setCurrentIndex(7)  # Injetor Sets/Arm
        _app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.janela._force_exit = True
        cls.janela.close()
        _app.processEvents()
        cls.janela.deleteLater()
        _app.processEvents()

    def setUp(self):
        if not self.janela.rb_inj_sets.isChecked():
            self.janela.rb_inj_sets.click()
        _app.processEvents()

    def _titulos(self):
        j = self.janela
        return (
            j.lbl_inj_t.text(),
            j.lbl_inj_doador_titulo.findChildren(QLabel)[-1].text(),
            j.lbl_inj_alvo_titulo.findChildren(QLabel)[-1].text(),
        )
    def test_01_sets_inicial_e_grupo_exclusivo(self):
        j = self.janela
        self.assertTrue(j.grupo_modo_injetor.exclusive())
        self.assertTrue(j.rb_inj_sets.isChecked())
        self.assertFalse(j.rb_inj_armas.isChecked())
        self.assertEqual(j._inj_modo, "set")
        self.assertEqual(
            self._titulos(),
            ("Injetor de Sets", "APARÊNCIA DOADORA", "SET ALVO"),
        )

    def test_02_armas_muda_labels_e_exclusividade(self):
        j = self.janela
        j.rb_inj_armas.click()
        _app.processEvents()
        self.assertTrue(j.rb_inj_armas.isChecked())
        self.assertFalse(j.rb_inj_sets.isChecked())
        self.assertEqual(j._inj_modo, "weapon")
        self.assertEqual(
            self._titulos(),
            ("Injetor de Armas", "ARMA DOADORA", "ARMA ALVO"),
        )

    def test_03_voltar_para_sets_restaura(self):
        j = self.janela
        j.rb_inj_armas.click()
        _app.processEvents()
        j.rb_inj_sets.click()
        _app.processEvents()
        self.assertTrue(j.rb_inj_sets.isChecked())
        self.assertFalse(j.rb_inj_armas.isChecked())
        self.assertEqual(j._inj_modo, "set")
        self.assertEqual(
            self._titulos(),
            ("Injetor de Sets", "APARÊNCIA DOADORA", "SET ALVO"),
        )

    def test_04_trocar_modo_nao_executa_backend(self):
        j = self.janela
        with mock.patch.object(j, "executar_em_background") as spy:
            j.rb_inj_armas.click()
            _app.processEvents()
            j.rb_inj_sets.click()
            _app.processEvents()
            spy.assert_not_called()

    def test_05_layout_estavel_ao_alternar(self):
        j = self.janela
        antes = (j.rb_inj_sets.geometry().getRect(),
                 j.rb_inj_armas.geometry().getRect())
        j.rb_inj_armas.click()
        _app.processEvents()
        depois = (j.rb_inj_sets.geometry().getRect(),
                  j.rb_inj_armas.geometry().getRect())
        self.assertEqual(antes, depois)

    def test_06_sem_espaco_reservado_para_indicador(self):
        j = self.janela
        for botao in (j.rb_inj_sets, j.rb_inj_armas):
            with self.subTest(botao=botao.text()):
                self.assertEqual(botao.width(), botao.sizeHint().width())
                self.assertLessEqual(botao.height(), 40)
    def test_07_qss_neutraliza_o_indicador(self):
        bloco = _bloco_injmode()
        for token in (
            "spacing: 0px;",
            "QRadioButton#InjModeBtn::indicator:unchecked",
            "QRadioButton#InjModeBtn::indicator:checked",
            "width: 0px;",
            "height: 0px;",
            "margin: 0px;",
            "padding: 0px;",
            "border: none;",
            "background: transparent;",
            "image: none;",
        ):
            self.assertIn(token, bloco)

    def test_08_selecao_depende_do_estado_checked(self):
        self.assertIn("QRadioButton#InjModeBtn:checked {{", _fonte_main())

    def test_09_estilo_global_de_radio_intacto(self):
        fonte = _fonte_main()
        # Bloco global (Org Sets: Turbo/Seguro) permanece como estava.
        self.assertIn(
            "QRadioButton {{\n                color: #C0C0CC;", fonte
        )
        self.assertIn("spacing: 8px;", fonte)
        self.assertIn("QRadioButton::indicator:checked {{", fonte)
        self.assertIn("image: url({check_sets});", fonte)
        # O seletor do Injetor mantém o próprio fundo (correção local).
        self.assertIn(
            "background-color: rgba(20, 20, 30, 180);", _bloco_injmode()
        )

    def test_10_backend_do_injetor_intacto(self):
        atual = hashlib.sha256(
            (RAIZ / "set_injector.py").read_bytes()
        ).hexdigest().upper()
        self.assertEqual(atual, HASH_SET_INJECTOR)


if __name__ == "__main__":
    unittest.main(verbosity=2)


