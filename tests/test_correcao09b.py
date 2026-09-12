# -*- coding: utf-8 -*-
"""Correção 09B — aba dedicada de restauração seletiva."""
import hashlib
import inspect
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import main  # noqa: E402
import restore_list  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QStackedWidget  # noqa: E402
from tests.test_correcao09a import item, itens_operacao  # noqa: E402


HASHES_CONGELADOS = {
    "automod.py": "F9422E65FA542D6D5A28CE2E3DD6D025544669601EA2522F42415BDA09E69609",
    "textura.py": "A890FDA024E47C57817F25E5845CE239F5C7F83CF571F1A674F9AD8F426CB8DE",
    "extractor_sets.py": "D3F01604DB2DF2A74FF6D9317FD177A8A3DA42CD92F6769D7B8DF34B21BCD58F",
    "set_injector.py": "D2765BBD157138F6A6AD4DB5997AAF69A212118349CD88257B5BFB2727E00919",
}


class PaginaRestauracao:
    @staticmethod
    def criar(itens):
        win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
        win.telas = QStackedWidget()
        with patch.object(main.opt, "listar_mods_ativos", return_value=itens), \
             patch.object(main.opt, "obter_pasta_jogo_atual", return_value=r"C:\Fake"):
            page = win._criar_pagina_restauracao()
        return win, page

    @staticmethod
    def linhas(win):
        resultado = []
        for indice in range(win.lista_restauracao.topLevelItemCount()):
            item_w = win.lista_restauracao.topLevelItem(indice)
            if item_w.data(restore_list.COL_CHECKBOX, Qt.UserRole + 2) == "operation":
                resultado.append(item_w)
        return resultado

    @staticmethod
    def ids(win):
        return [item_w.data(restore_list.COL_CHECKBOX, Qt.UserRole + 1)
                for item_w in PaginaRestauracao.linhas(win)]


class TestNavegacaoESeparacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.fonte = Path(main.__file__).read_text(encoding="utf-8")

    def test_01_sidebar_contem_restauracao(self):
        self.assertIn('criar_botao_menu("Restauração", 8', self.fonte)
        self.assertIn("btn_aba_restauracao", self.fonte)

    def test_02_ordem_injetor_restauracao_configuracoes(self):
        inicio = self.fonte.index("layout_sidebar.addWidget(self.btn_aba_injetor)")
        meio = self.fonte.index("layout_sidebar.addWidget(self.btn_aba_restauracao)")
        fim = self.fonte.index("layout_sidebar.addWidget(self.btn_aba_config)")
        self.assertLess(inicio, meio)
        self.assertLess(meio, fim)

    def test_03_automod_nao_renderiza_modificacoes_ativas(self):
        trecho = self.fonte[
            self.fonte.index("# --- TELA 2: AUTOMOD ---"):
            self.fonte.index("# --- TELA 3: ÁUDIO ---")
        ]
        self.assertNotIn("MODIFICAÇÕES ATIVAS", trecho)
        self.assertNotIn("lista_historico", trecho)

    def test_04_automod_mantem_selecao_e_injecao(self):
        trecho = self.fonte[
            self.fonte.index("# --- TELA 2: AUTOMOD ---"):
            self.fonte.index("# --- TELA 3: ÁUDIO ---")
        ]
        self.assertIn("SELECIONAR ARQUIVOS", trecho)
        self.assertIn("INJETAR MODS NO AIKA", trecho)
        self.assertIn("acao_injetar_mods", trecho)


class TestPaginaListaEFiltro(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_05_aba_renderiza_historico(self):
        win, page = PaginaRestauracao.criar(itens_operacao(3))
        self.assertEqual(page.objectName(), "RestauracaoPage")
        self.assertEqual(len(PaginaRestauracao.linhas(win)), 1)

    def test_06_operacao_09a_permanece_linha_unica(self):
        win, _ = PaginaRestauracao.criar(itens_operacao(5))
        self.assertEqual(PaginaRestauracao.ids(win), ["op-set"])

    def test_07_vinte_cinco_arquivos_uma_linha(self):
        win, _ = PaginaRestauracao.criar(itens_operacao(25))
        linhas = PaginaRestauracao.linhas(win)
        self.assertEqual(len(linhas), 1)
        self.assertIn("25 arquivos", linhas[0].text(restore_list.COL_NOME))

    def test_08_duas_operacoes_duas_linhas(self):
        itens = itens_operacao(2, "op-a") + itens_operacao(3, "op-b")
        win, _ = PaginaRestauracao.criar(itens)
        self.assertEqual(len(PaginaRestauracao.linhas(win)), 2)

    def test_09_data_exibida_na_coluna(self):
        win, _ = PaginaRestauracao.criar(itens_operacao(2))
        linha = PaginaRestauracao.linhas(win)[0]
        self.assertEqual(linha.text(restore_list.COL_DATA), "02/09/2026 22:49")

    def test_10_ordenacao_inicial_data_decrescente(self):
        itens = itens_operacao(1, "op-a", timestamp="2026-09-02 20:00:00")
        itens += itens_operacao(1, "op-b", timestamp="2026-09-01 20:00:00")
        win, _ = PaginaRestauracao.criar(itens)
        self.assertEqual(PaginaRestauracao.ids(win), ["op-a", "op-b"])

    def test_12_filtro_data_exibe_somente_dia_escolhido(self):
        itens = itens_operacao(2, "op-a", timestamp="2026-09-02 20:00:00")
        itens += itens_operacao(3, "op-b", timestamp="2026-09-01 20:00:00")
        win, _ = PaginaRestauracao.criar(itens)
        indice = win.cmb_filtro_restauracao.findData("2026-09-01")
        win.cmb_filtro_restauracao.setCurrentIndex(indice)
        self.assertEqual(PaginaRestauracao.ids(win), ["op-b"])

    def test_13_todas_exibe_todas_as_datas(self):
        itens = itens_operacao(2, "op-a", timestamp="2026-09-02 20:00:00")
        itens += itens_operacao(3, "op-b", timestamp="2026-09-01 20:00:00")
        win, _ = PaginaRestauracao.criar(itens)
        win.cmb_filtro_restauracao.setCurrentIndex(0)
        self.assertEqual(len(PaginaRestauracao.linhas(win)), 2)


class TestListaSelecaoERestore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_14_checkbox_operacao_funciona(self):
        win, _ = PaginaRestauracao.criar(itens_operacao(2))
        linha = PaginaRestauracao.linhas(win)[0]
        linha.setCheckState(restore_list.COL_CHECKBOX, Qt.Checked)
        self.assertEqual(
            win._restauracao_selecionadas,
            {(r"C:\Cliente\AikaOnlineBrasil", "op-set")},
        )
        self.assertTrue(win.btn_restaurar_mod.isEnabled())

    def test_15_selecionar_duas_operacoes(self):
        itens = itens_operacao(2, "op-a") + itens_operacao(3, "op-b")
        win, _ = PaginaRestauracao.criar(itens)
        for linha in PaginaRestauracao.linhas(win):
            linha.setCheckState(restore_list.COL_CHECKBOX, Qt.Checked)
        self.assertEqual(
            win._restauracao_selecionadas,
            {
                (r"C:\Cliente\AikaOnlineBrasil", "op-a"),
                (r"C:\Cliente\AikaOnlineBrasil", "op-b"),
            },
        )

    def test_16_restaurar_selecionadas_usa_fluxo_09a(self):
        itens = itens_operacao(2, "op-a") + itens_operacao(3, "op-b")
        win, _ = PaginaRestauracao.criar(itens)
        win._restauracao_selecionadas = {
            (r"C:\Cliente\AikaOnlineBrasil", "op-a"),
            (r"C:\Cliente\AikaOnlineBrasil", "op-b"),
        }
        win.sinais = MagicMock()
        class FakeMessageBox:
            Warning = 1; AcceptRole = 2; RejectRole = 3
            def __init__(self, *_): self.restaurar = None
            def setWindowTitle(self, *_): pass
            def setIcon(self, *_): pass
            def setText(self, *_): pass
            def setInformativeText(self, *_): pass
            def addButton(self, texto, *_):
                botao = object()
                if texto == "RESTAURAR": self.restaurar = botao
                return botao
            def setDefaultButton(self, *_): pass
            def exec(self): pass
            def clickedButton(self): return self.restaurar
        chaves = main._chaves_das_operacoes(win._restauracao_operacoes)
        with patch.object(main, "QMessageBox", FakeMessageBox), \
             patch.object(main, "_restaurar_chaves_historico",
                          return_value={"restaurados": list(chaves), "falhas": []}) as restaurar, \
             patch.object(main.opt, "listar_mods_ativos", return_value=[]), \
             patch.object(win, "executar_em_background",
                          side_effect=lambda tarefa: tarefa()):
            win._on_restaurar_mod_selecionado()
        restaurar.assert_called_once()
        self.assertEqual(restaurar.call_args.args[0], chaves)
        self.assertEqual(len(chaves), 5)

    def test_17_botao_solicita_somente_aquela_operacao(self):
        itens = itens_operacao(2, "op-a") + itens_operacao(3, "op-b")
        win, _ = PaginaRestauracao.criar(itens)
        with patch.object(win, "_on_restaurar_mod_selecionado") as restaurar:
            win._restaurar_operacao_direta("op-b")
        self.assertEqual(
            win._restauracao_selecionadas,
            {(r"C:\Cliente\AikaOnlineBrasil", "op-b")},
        )
        restaurar.assert_called_once()

    def test_18_multiplos_arquivos_resumo_sem_detalhes_permanentes(self):
        win, _ = PaginaRestauracao.criar(itens_operacao(3))
        linha = PaginaRestauracao.linhas(win)[0]
        self.assertIn("3 arquivos", linha.text(restore_list.COL_NOME))
        self.assertIn("Data/op-set_arquivo_00.jit", linha.toolTip(restore_list.COL_NOME))


class TestLegacySegurancaEIntegridade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_20_legacy_mostra_modificacao_antiga(self):
        win, _ = PaginaRestauracao.criar([item("Data/antigo.jit")])
        linha = PaginaRestauracao.linhas(win)[0]
        self.assertEqual(linha.text(restore_list.COL_MODIFICACAO), "Modificação antiga")
        self.assertTrue(win._restauracao_operacoes[0]["legacy"])

    def test_21_delete_legacy_continua_no_restore_especializado(self):
        historico = [item("Data/antigoEF.jit", operacao_arquivo="DELETE")]
        with patch.object(main.opt, "listar_mods_ativos", return_value=historico), \
             patch.object(main.opt, "restaurar_mods_selecionados",
                          return_value={"restaurados": [], "falhas": []}), \
             patch.object(main.sinj, "restaurar_ef_removido",
                          return_value=(True, "ok")) as delete:
            resultado = main._restaurar_chaves_historico(
                ["Data/antigoEF.jit"], r"C:\Fake"
            )
        delete.assert_called_once()
        self.assertEqual(resultado["restaurados"], ["antigoEF.jit"])

    def test_22_seguranca_mantem_restauracao_geral(self):
        fonte = Path(main.__file__).read_text(encoding="utf-8")
        trecho = fonte[
            fonte.index("# --- TELA 5: RESTAURAÇÃO ---"):
            fonte.index("# --- TELA 6: ORGANIZADOR DE SETS ---")
        ]
        self.assertIn("RESTAURAR JOGO", trecho)
        self.assertIn("acao_restaurar_tudo", trecho)

    def test_23_motores_congelados_permanecem_intactos(self):
        for nome, esperado in HASHES_CONGELADOS.items():
            atual = hashlib.sha256((RAIZ / nome).read_bytes()).hexdigest().upper()
            self.assertEqual(atual, esperado, nome)

    def test_24_nenhum_backup_e_movido_ou_alterado(self):
        fonte = inspect.getsource(main.AikaOptimizerPro._criar_pagina_restauracao)
        self.assertNotIn("shutil", fonte)
        self.assertNotIn("os.remove", fonte)
        self.assertNotIn("os.replace", fonte)
        self.assertNotIn("backup_relpath", fonte)

    def test_25_pagina_sintetica_nao_acessa_cliente_real(self):
        with patch.object(main.opt, "listar_mods_ativos", return_value=[]) as listar, \
             patch.object(main.opt, "obter_pasta_jogo_atual", return_value=r"C:\Fake") as cliente:
            win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
            win.telas = QStackedWidget()
            win._criar_pagina_restauracao()
        cliente.assert_called_once()
        listar.assert_called_once_with(r"C:\Fake")


if __name__ == "__main__":
    unittest.main(verbosity=2)