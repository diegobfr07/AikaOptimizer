# -*- coding: utf-8 -*-
"""Correção 09D — ícone próprio e layout responsivo da Restauração."""
import hashlib
import os
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import main  # noqa: E402
import restore_list  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QHeaderView  # noqa: E402


HASHES_CONGELADOS = {
    "automod.py": "F9422E65FA542D6D5A28CE2E3DD6D025544669601EA2522F42415BDA09E69609",
    "textura.py": "A890FDA024E47C57817F25E5845CE239F5C7F83CF571F1A674F9AD8F426CB8DE",
    "extractor_sets.py": "D3F01604DB2DF2A74FF6D9317FD177A8A3DA42CD92F6769D7B8DF34B21BCD58F",
    "set_injector.py": "D2765BBD157138F6A6AD4DB5997AAF69A212118349CD88257B5BFB2727E00919",
}


class TestIconeELayout09D(unittest.TestCase):
    def test_01_restore_svg_existe_e_e_valido(self):
        caminho = RAIZ / "assets" / "icons" / "restore.svg"
        self.assertTrue(caminho.is_file())
        ET.parse(caminho)

    def test_02_restauracao_usa_icone_distinto_da_seguranca(self):
        fonte = Path(main.__file__).read_text(encoding="utf-8")
        self.assertIn(
            'btn_aba_restore     = self.criar_botao_menu("Segurança", 5, carregar_icone_svg("protected.svg"))',
            fonte,
        )
        self.assertIn(
            'btn_aba_restauracao= self.criar_botao_menu("Restauração", 8, carregar_icone_svg("restore.svg"))',
            fonte,
        )
        restore = hashlib.sha256(
            (RAIZ / "assets" / "icons" / "restore.svg").read_bytes()
        ).hexdigest()
        seguranca = hashlib.sha256(
            (RAIZ / "assets" / "icons" / "protected.svg").read_bytes()
        ).hexdigest()
        self.assertNotEqual(restore, seguranca)

    def test_03_restauracao_usa_lista_unica_sem_grade_de_cards(self):
        fonte = Path(main.__file__).read_text(encoding="utf-8")
        self.assertIn("rlist.RestoreListWidget()", fonte)
        self.assertNotIn("class ResponsiveRestoreGrid", fonte)
        self.assertNotIn("class RestoreOperationCard", fonte)

    def test_04_colunas_principais_expandem_com_a_janela(self):
        QApplication.instance() or QApplication([])
        lista = restore_list.RestoreListWidget()
        self.assertEqual(lista.header().sectionResizeMode(restore_list.COL_NOME), QHeaderView.Stretch)
        self.assertEqual(lista.header().sectionResizeMode(restore_list.COL_MODIFICACAO), QHeaderView.Stretch)

    def test_05_lista_compacta_nao_usa_rolagem_horizontal(self):
        QApplication.instance() or QApplication([])
        lista = restore_list.RestoreListWidget()
        self.assertTrue(lista.uniformRowHeights())
        self.assertEqual(lista.horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)

    def test_06_motores_congelados_permanecem_intactos(self):
        for nome, esperado in HASHES_CONGELADOS.items():
            atual = hashlib.sha256((RAIZ / nome).read_bytes()).hexdigest().upper()
            self.assertEqual(atual, esperado, nome)


if __name__ == "__main__":
    unittest.main(verbosity=2)