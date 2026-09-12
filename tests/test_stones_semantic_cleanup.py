# -*- coding: utf-8 -*-
"""Limpeza semântica da UI da página Pedras.

Prova que códigos internos (0/4/5/6/7/8/9) nunca aparecem em textos
visíveis e que os nomes humanos continuam fiéis ao mapeamento validado.
"""
import os
import sys
import unittest
from types import SimpleNamespace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import stone_color_page as page_module  # noqa: E402
import stone_color_service as service  # noqa: E402


def _nova_pagina():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    page = page_module.StoneColorPage(
        lambda: None, page_module.DEFAULT_PROFILE_PATH
    )
    return app, page


class TestMapeamentoCodigoParaNome(unittest.TestCase):
    """Código interno -> nome humano (fonte única do catálogo)."""

    def test_01_codigo_8_exibe_vermelho(self):
        self.assertEqual(page_module.nome_da_cor(8), "Vermelho")

    def test_02_codigo_7_exibe_roxo(self):
        self.assertEqual(page_module.nome_da_cor(7), "Roxo")

    def test_03_codigo_0_exibe_branco(self):
        self.assertEqual(page_module.nome_da_cor(0), "Branco")

    def test_04_demais_codigos_convertem(self):
        esperado = {
            4: "Marrom/Ocre",
            5: "Amarelo",
            6: "Laranja",
            9: "Preto",
        }
        for codigo, nome in esperado.items():
            self.assertEqual(page_module.nome_da_cor(codigo), nome)

    def test_05_mapeamento_derivado_do_catalogo_unico(self):
        self.assertEqual(
            page_module.NOME_POR_CODIGO,
            {c.code: c.name for c in page_module.CONFIRMED_COLORS},
        )


class TestResumoVisivel(unittest.TestCase):
    """O texto resumido mostra nomes, nunca códigos crus."""

    def test_06_cores_atuais_usam_nomes_humanos(self):
        texto = page_module.resumo_cores(8, 7, 0)
        self.assertIn("Cores atuais", texto)
        self.assertIn("Ataque PvP: Vermelho", texto)
        self.assertIn("Defesa PvP: Roxo", texto)
        self.assertIn("Demais: Branco", texto)
        for vazamento in ("Ataque=8", "Defesa=7", "Comum=0", "=8", "=7", "=0"):
            self.assertNotIn(vazamento, texto)
        self.assertFalse(any(c.isdigit() for c in texto))

    def test_07_cores_aplicadas_usam_nomes_humanos(self):
        texto = page_module.resumo_cores(8, 7, 0, rotulo="Cores aplicadas")
        self.assertIn("Cores aplicadas: Ataque PvP: Vermelho", texto)
        self.assertIn("Defesa PvP: Roxo", texto)
        self.assertIn("Demais: Branco", texto)
        self.assertFalse(any(c.isdigit() for c in texto))

    def test_08_resumo_com_combos_nao_padrao(self):
        texto = page_module.resumo_cores(9, 5, 4)
        self.assertIn("Ataque PvP: Preto", texto)
        self.assertIn("Defesa PvP: Amarelo", texto)
        self.assertIn("Demais: Marrom/Ocre", texto)
        self.assertFalse(any(c.isdigit() for c in texto))


class TestEstadoDoArquivo(unittest.TestCase):
    """Bloco ESTADO DO ARQUIVO exibe apenas nomes de cores."""

    def setUp(self):
        self.app, self.page = _nova_pagina()
        self.addCleanup(self.page.deleteLater)

    def test_09_personalizacao_reconhecida_sem_codigos(self):
        rec = SimpleNamespace(
            kind=service.KIND_PERSONALIZED,
            base_valid=True,
            message="Personalização reconhecida; base verificada (438/438 registros).",
            applied_colors=(8, 7, 0),
        )
        self.page._recognition = rec
        self.page._apply_recognition_state()
        texto = self.page.state_detail.text()
        self.assertIn("Vermelho", texto)
        self.assertIn("Roxo", texto)
        self.assertIn("Branco", texto)
        self.assertNotIn("Ataque=", texto)
        self.assertNotIn("Defesa=", texto)
        self.assertNotIn("Comum=", texto)
        for vazamento in (": 8", "=8", ": 7", "=7", ": 0", "=0"):
            self.assertNotIn(vazamento, texto)
        self.assertNotIn("Ataque PvP: 8", texto)
        self.assertNotIn("Defesa PvP: 7", texto)
        self.assertNotIn("Demais: 0", texto)

    def test_10_aplicacao_estado_com_nomes(self):
        estados = []
        self.page._set_state = lambda estado, msg: estados.append(msg)
        outcome = SimpleNamespace(
            applied=True, output_sha256="SHA-256-X", message="Cores aplicadas no cliente."
        )
        self.page._apply_finished(outcome)
        self.assertTrue(estados)
        texto = estados[-1]
        self.assertIn("Cores aplicadas: Ataque PvP: Vermelho", texto)
        self.assertIn("Defesa PvP: Roxo", texto)
        self.assertIn("Demais: Branco", texto)
        self.assertNotIn("Ataque=", texto)
        self.assertFalse(any(c.isdigit() for c in texto))


class TestVazamentosRestantes(unittest.TestCase):
    """Varredura localizada: nenhum W+n/código cru nos textos visíveis."""

    def setUp(self):
        self.app, self.page = _nova_pagina()
        self.addCleanup(self.page.deleteLater)

    def test_11_nenhum_w_em_textos_visiveis_da_pagina(self):
        from PySide6.QtWidgets import QAbstractButton, QComboBox, QLabel

        textos = []
        for w in self.page.findChildren(QLabel):
            textos.append(w.text())
        for w in self.page.findChildren(QAbstractButton):
            textos.append(w.text())
        for w in self.page.findChildren(QComboBox):
            for i in range(w.count()):
                textos.append(w.itemText(i))
        conteudo = "\n".join(textos)
        self.assertNotIn("W+", conteudo)
        self.assertNotIn("(W+", conteudo)
        self.assertNotIn("Comum", conteudo)

    def test_12_codigo_desconhecido_nao_causa_crash(self):
        self.assertEqual(page_module.nome_da_cor(3), "Desconhecida")
        self.assertEqual(page_module.nome_da_cor(None), "Desconhecida")
        texto = page_module.resumo_cores(None, 99, 8)
        self.assertIn("Desconhecida", texto)
        self.assertIn("Vermelho", texto)

    def test_13_combos_continuam_com_dados_internos(self):
        self.assertEqual(self.page.selected_codes(), (8, 7, 0))
        ataque = self.page.attack_combo
        ataque.setCurrentIndex(ataque.findData(9))
        self.assertEqual(ataque.currentData(), 9)
        self.assertEqual(ataque.currentText(), "Preto")
        self.page.restore_defaults()
        self.assertEqual(self.page.selected_codes(), (8, 7, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)

