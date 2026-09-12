# -*- coding: utf-8 -*-
"""Cobertura da lista compacta e ordenável da página Restauração."""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import main  # noqa: E402
import restore_list as rlist  # noqa: E402
import stone_color_service as stones  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QTreeWidgetItem  # noqa: E402
from tests.test_correcao09a import item, itens_operacao  # noqa: E402


def operacao(itens):
    return main._agrupar_operacoes_historico(itens)[0]


def reconhecimento(kind, *, base_sha="BASE", file_sha="FILE", base_valid=True):
    return stones.StonesRecognition(
        Path(r"C:\Cliente"), Path(r"C:\Cliente\ItemList6.bin"), kind,
        file_sha, 1234, True, 438, base_sha, (8, 7, 0), "estado",
        438, 438 if base_valid else None, None if base_valid else "base ausente",
    )


def resumo_pedras(rec, bases=None):
    return {
        "client_root": r"C:\Cliente",
        "target": r"C:\Cliente\ItemList6.bin",
        "recognition": rec,
        "bases": list(bases or []),
    }


def ids(widget):
    return [
        widget.topLevelItem(i).data(rlist.COL_CHECKBOX, Qt.UserRole + 1)
        for i in range(widget.topLevelItemCount())
    ]


def rows_for_operations(*operations):
    return [rlist.build_operation_row(operation) for operation in operations]


def operation_items(widget):
    return [
        widget.topLevelItem(i)
        for i in range(widget.topLevelItemCount())
        if widget.topLevelItem(i).data(
            rlist.COL_CHECKBOX, Qt.UserRole + 2
        ) == "operation"
    ]


class TestBuildersOperacoes(unittest.TestCase):
    def test_01_arquivo_unico_exibe_nome_extensao_e_timestamp_real(self):
        row = rlist.build_operation_row(operacao([
            item("Data/Zeta.JIT", "op-z", timestamp="2026-08-02 03:04:05")
        ]))
        self.assertEqual(row["name"], "Zeta.JIT")
        self.assertEqual(row["tipo"], ".jit")
        self.assertEqual(row["sort_data"], "2026-08-02 03:04:05")
        self.assertEqual(row["data_display"], "02/08/2026 03:04")

    def test_02_multi_arquivo_permanece_uma_unidade(self):
        row = rlist.build_operation_row(operacao(itens_operacao(25)))
        self.assertIn("25 arquivos", row["name"])
        self.assertEqual(row["tipo"], ".jit")
        self.assertEqual(len(row["tooltip"].splitlines()), 25)

    def test_03_extensoes_mistas(self):
        itens = [
            item("Data/a.jit", "mix"),
            item("Data/b.wav", "mix"),
        ]
        self.assertEqual(rlist.build_operation_row(operacao(itens))["tipo"], "Vários")

    def test_04_legado_tem_id_estavel_e_rotulo(self):
        row = rlist.build_operation_row(operacao([item("Data/antigo.jit")]))
        self.assertEqual(row["operation_id"], "legacy:Data/antigo.jit")
        self.assertEqual(row["modificacao"], "Modificação antiga")


class TestOrdenacaoEIdentidade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget = rlist.RestoreListWidget()
        ops = [
            operacao([item("Data/zeta.wav", "op-z", timestamp="2026-01-01 09:00:00",
                            tipo="AUDIO", cliente=r"C:\B")]),
            operacao([item("Data/alpha.jit", "op-a", timestamp="2026-03-01 09:00:00",
                            tipo="TEXTURE", cliente=r"C:\A")]),
            operacao([item("Data/meio.bin", "op-m", timestamp="2026-02-01 09:00:00",
                            tipo="AUTOMOD", cliente=r"C:\C")]),
        ]
        self.widget.populate([rlist.build_operation_row(op) for op in ops])

    def test_05_inicial_data_decrescente(self):
        self.assertEqual(ids(self.widget), ["op-a", "op-m", "op-z"])

    def test_06_ordenacao_nome(self):
        self.widget.sortByColumn(rlist.COL_NOME, Qt.AscendingOrder)
        self.assertEqual(ids(self.widget), ["op-a", "op-m", "op-z"])

    def test_07_ordenacao_tipo(self):
        self.widget.sortByColumn(rlist.COL_TIPO, Qt.AscendingOrder)
        self.assertEqual(ids(self.widget), ["op-m", "op-a", "op-z"])

    def test_08_botao_apos_ordenar_emite_identidade_correta(self):
        emitidas = []
        self.widget.restaurar_operacao.connect(emitidas.append)
        self.widget.sortByColumn(rlist.COL_NOME, Qt.DescendingOrder)
        linha = self.widget.topLevelItem(0)
        self.widget.itemWidget(linha, rlist.COL_ACAO).click()
        self.assertEqual(emitidas, [(r"C:\B", "op-z")])

    def test_09_mesmo_id_em_clientes_distintos_nao_colide(self):
        rows = [
            rlist.build_operation_row(operacao([
                item("Data/igual.jit", "duplicado", cliente=cliente)
            ])) for cliente in (r"C:\ClienteA", r"C:\ClienteB")
        ]
        self.widget.populate(rows, {(r"C:\ClienteB", "duplicado")})
        estados = {
            self.widget.topLevelItem(i).data(rlist.COL_CHECKBOX, Qt.UserRole + 3):
            self.widget.topLevelItem(i).checkState(rlist.COL_CHECKBOX)
            for i in range(2)
        }
        self.assertEqual(estados[r"C:\ClienteA"], Qt.Unchecked)
        self.assertEqual(estados[r"C:\ClienteB"], Qt.Checked)


class TestLinhaPedras(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_10_personalizada_usa_base_vinculada_nao_a_mais_recente(self):
        rec = reconhecimento(stones.KIND_PERSONALIZED, base_sha="BASE-ANTIGA")
        row = rlist.build_pedras_row(resumo_pedras(rec, [
            {"sha256": "BASE-ANTIGA", "captured_at": "2026-01-02 03:04:05"},
            {"sha256": "BASE-NOVA", "captured_at": "2026-09-05 20:00:00"},
        ]))
        self.assertTrue(row["restorable"])
        self.assertEqual(row["sort_data"], "2026-01-02 03:04:05")
        self.assertEqual(row["pedras_state"], "Personalização reconhecida")

    def test_11_ja_restaurada_fica_desabilitada(self):
        rec = reconhecimento(stones.KIND_BASE, base_sha=None, file_sha="BASE")
        row = rlist.build_pedras_row(resumo_pedras(rec, [
            {"sha256": "BASE", "captured_at": "2026-02-01 10:00:00"}
        ]))
        self.assertFalse(row["restorable"])
        self.assertEqual(row["pedras_state"], "Já restaurado")

    def test_12_processo_aberto_bloqueia_restauracao(self):
        rec = reconhecimento(stones.KIND_PERSONALIZED)
        row = rlist.build_pedras_row(resumo_pedras(rec, [
            {"sha256": "BASE", "captured_at": "2026-02-01 10:00:00"}
        ]), processo_aberto=True)
        self.assertFalse(row["restorable"])
        self.assertIn("Feche o jogo", row["pedras_state"])

    def test_13_base_ausente_ou_invalida_bloqueia(self):
        rec = reconhecimento(stones.KIND_PERSONALIZED, base_valid=False)
        row = rlist.build_pedras_row(resumo_pedras(rec, [
            {"sha256": "BASE", "captured_at": "2026-02-01 10:00:00"}
        ]))
        self.assertFalse(row["restorable"])
        self.assertEqual(row["pedras_state"], "Base indisponível")

    def test_14_pedras_nao_possui_checkbox_de_lote(self):
        rec = reconhecimento(stones.KIND_PERSONALIZED)
        row = rlist.build_pedras_row(resumo_pedras(rec, [
            {"sha256": "BASE", "captured_at": "2026-02-01 10:00:00"}
        ]))
        widget = rlist.RestoreListWidget()
        widget.populate([row])
        linha = widget.topLevelItem(0)
        self.assertFalse(bool(linha.flags() & Qt.ItemIsUserCheckable))
        self.assertEqual(widget.operacoes_visiveis(), [])

    def test_15_botao_pedras_respeita_estado_e_emite_sinal_proprio(self):
        rec = reconhecimento(stones.KIND_PERSONALIZED)
        resumo = resumo_pedras(rec, [
            {"sha256": "BASE", "captured_at": "2026-02-01 10:00:00"}
        ])
        widget = rlist.RestoreListWidget()
        widget.populate([rlist.build_pedras_row(resumo)])
        chamadas = []
        widget.restaurar_pedras.connect(lambda: chamadas.append(True))
        widget.itemWidget(widget.topLevelItem(0), rlist.COL_ACAO).click()
        self.assertEqual(chamadas, [True])


class TestSelecionarTodasECorrecaoBotao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _widget_com_operacoes(self, quantidade=3):
        widget = rlist.RestoreListWidget()
        operations = [
            operacao(itens_operacao(
                1, f"op-{indice:02d}",
                timestamp=f"2026-09-{indice + 1:02d} 10:00:00",
            ))
            for indice in range(quantidade)
        ]
        widget.populate(rows_for_operations(*operations))
        return widget

    def test_21_selecionar_todas_e_segundo_clique_desmarca(self):
        widget = self._widget_com_operacoes(3)
        emitidos = []
        widget.selecao_em_lote.connect(
            lambda identidades, marcado: emitidos.append((set(identidades), marcado))
        )
        mestre = widget.header().checkbox_mestre

        self.assertEqual(mestre.checkState(), Qt.Unchecked)
        mestre.click()
        self.assertEqual(mestre.checkState(), Qt.Checked)
        self.assertTrue(all(
            item.checkState(rlist.COL_CHECKBOX) == Qt.Checked
            for item in operation_items(widget)
        ))
        self.assertEqual(emitidos[-1], (set(widget.operacoes_elegiveis()), True))

        mestre.click()
        self.assertEqual(mestre.checkState(), Qt.Unchecked)
        self.assertTrue(all(
            item.checkState(rlist.COL_CHECKBOX) == Qt.Unchecked
            for item in operation_items(widget)
        ))
        self.assertEqual(emitidos[-1], (set(widget.operacoes_elegiveis()), False))

    def test_22_selecao_individual_parcial_e_clique_seleciona_todas(self):
        widget = self._widget_com_operacoes(3)
        itens = operation_items(widget)
        itens[0].setCheckState(rlist.COL_CHECKBOX, Qt.Checked)
        mestre = widget.header().checkbox_mestre
        self.assertEqual(mestre.checkState(), Qt.PartiallyChecked)

        mestre.click()
        self.assertEqual(mestre.checkState(), Qt.Checked)
        self.assertTrue(all(
            item.checkState(rlist.COL_CHECKBOX) == Qt.Checked for item in itens
        ))

    def test_23_sem_elegiveis_desabilita_e_desmarca(self):
        widget = rlist.RestoreListWidget()
        widget.populate([])
        mestre = widget.header().checkbox_mestre
        self.assertFalse(mestre.isEnabled())
        self.assertEqual(mestre.checkState(), Qt.Unchecked)

        pedras = rlist.build_pedras_row(None)
        widget.populate([pedras])
        self.assertFalse(mestre.isEnabled())
        self.assertEqual(mestre.checkState(), Qt.Unchecked)

    def test_24_pedras_detalhes_e_desabilitados_sao_excluidos(self):
        widget = self._widget_com_operacoes(2)
        operacoes = operation_items(widget)
        operacoes[1].setDisabled(True)

        pedras = rlist.build_pedras_row(None)
        widget._populating = True
        widget._add_row(pedras, set())
        widget._populating = False
        detalhe = QTreeWidgetItem(operacoes[0])
        detalhe.setText(rlist.COL_NOME, "detalhe filho")
        detalhe.setFlags(Qt.NoItemFlags)
        widget.atualizar_checkbox_mestre()

        identidade_elegivel = widget._identidade_item(operacoes[0])
        self.assertEqual(widget.operacoes_elegiveis(), [identidade_elegivel])
        widget.header().checkbox_mestre.click()
        self.assertEqual(operacoes[0].checkState(rlist.COL_CHECKBOX), Qt.Checked)
        self.assertEqual(operacoes[1].checkState(rlist.COL_CHECKBOX), Qt.Unchecked)

    def test_25_inclui_operacoes_abaixo_da_area_visivel(self):
        widget = self._widget_com_operacoes(40)
        widget.resize(700, 120)
        widget.show()
        self.app.processEvents()
        itens = operation_items(widget)
        self.assertFalse(widget.visualItemRect(itens[-1]).intersects(widget.viewport().rect()))

        widget.header().checkbox_mestre.click()
        self.assertEqual(len(widget.operacoes_elegiveis()), 40)
        self.assertTrue(all(
            item.checkState(rlist.COL_CHECKBOX) == Qt.Checked for item in itens
        ))

    def test_26_ordenacao_preserva_ids_e_estado_mestre(self):
        widget = self._widget_com_operacoes(4)
        selecionadas = {
            rlist.operation_key(r"C:\Cliente\AikaOnlineBrasil", "op-01"),
            rlist.operation_key(r"C:\Cliente\AikaOnlineBrasil", "op-03"),
        }
        widget.populate([
            rlist.build_operation_row(operacao(itens_operacao(
                1, f"op-{indice:02d}",
                timestamp=f"2026-09-{indice + 1:02d} 10:00:00",
            ))) for indice in range(4)
        ], selecionadas)
        widget.sortByColumn(rlist.COL_NOME, Qt.DescendingOrder)

        marcadas = {
            widget._identidade_item(item)
            for item in operation_items(widget)
            if item.checkState(rlist.COL_CHECKBOX) == Qt.Checked
        }
        self.assertEqual(marcadas, selecionadas)
        self.assertEqual(widget.header().checkbox_mestre.checkState(), Qt.PartiallyChecked)

    def test_27_atualizacao_recalcula_estado_e_multi_arquivo_e_unidade(self):
        widget = rlist.RestoreListWidget()
        multi = operacao(itens_operacao(25, "multi"))
        outra = operacao(itens_operacao(1, "outra"))
        chave_multi = rlist.operation_key(
            r"C:\Cliente\AikaOnlineBrasil", "multi"
        )
        widget.populate(rows_for_operations(multi), {chave_multi})
        self.assertEqual(widget.operacoes_elegiveis(), [chave_multi])
        self.assertEqual(widget.header().checkbox_mestre.checkState(), Qt.Checked)

        widget.populate(rows_for_operations(multi, outra), {chave_multi})
        self.assertEqual(len(widget.operacoes_elegiveis()), 2)
        self.assertEqual(widget.header().checkbox_mestre.checkState(), Qt.PartiallyChecked)

    def test_28_checkbox_acessivel_e_nao_altera_ordenacao(self):
        widget = self._widget_com_operacoes(3)
        widget.sortByColumn(rlist.COL_TIPO, Qt.AscendingOrder)
        coluna_antes = widget.sortColumn()
        ordem_antes = widget.header().sortIndicatorOrder()
        mestre = widget.header().checkbox_mestre
        self.assertEqual(mestre.accessibleName(), rlist.SELECT_ALL_TOOLTIP)
        self.assertEqual(mestre.toolTip(), rlist.SELECT_ALL_TOOLTIP)

        mestre.click()
        self.assertEqual(widget.sortColumn(), coluna_antes)
        self.assertEqual(widget.header().sortIndicatorOrder(), ordem_antes)

    def test_29_selecionar_todas_nao_solicita_restauracao(self):
        widget = self._widget_com_operacoes(3)
        restauracoes = []
        pedras = []
        widget.restaurar_operacao.connect(restauracoes.append)
        widget.restaurar_pedras.connect(lambda: pedras.append(True))

        widget.header().checkbox_mestre.click()
        self.assertEqual(restauracoes, [])
        self.assertEqual(pedras, [])

    def test_30_dimensoes_comportam_texto_borda_e_padding(self):
        widget = self._widget_com_operacoes(1)
        item = operation_items(widget)[0]
        botao = widget.itemWidget(item, rlist.COL_ACAO)
        texto = botao.fontMetrics().horizontalAdvance(botao.text())
        hint = botao.sizeHint()

        self.assertGreaterEqual(hint.height(), rlist.RESTORE_BUTTON_MIN_HEIGHT)
        self.assertGreaterEqual(
            hint.width(), texto + rlist.RESTORE_BUTTON_HORIZONTAL_SPACE
        )
        self.assertGreaterEqual(
            item.sizeHint(rlist.COL_NOME).height(),
            hint.height() + rlist.RESTORE_ACTION_CELL_MARGIN,
        )
        self.assertGreaterEqual(
            widget.columnWidth(rlist.COL_ACAO),
            hint.width() + rlist.RESTORE_ACTION_CELL_MARGIN,
        )

    def test_31_pagina_filtro_todas_seleciona_ids_e_clientes_exatos(self):
        from tests.test_correcao09b import PaginaRestauracao

        itens = [
            item("Data/a.jit", "op-a", timestamp="2026-09-01 10:00:00",
                 cliente=r"C:\ClienteA"),
            item("Data/b.jit", "op-b", timestamp="2026-09-02 10:00:00",
                 cliente=r"C:\ClienteB"),
        ]
        win, _ = PaginaRestauracao.criar(itens)
        with unittest.mock.patch.object(
            win, "_on_restaurar_mod_selecionado"
        ) as restaurar:
            win.lista_restauracao.header().checkbox_mestre.click()

        self.assertEqual(win._restauracao_selecionadas, {
            (r"C:\ClienteA", "op-a"),
            (r"C:\ClienteB", "op-b"),
        })
        self.assertTrue(win.btn_restaurar_mod.isEnabled())
        self.assertEqual(win.btn_restaurar_mod.text(), "RESTAURAR SELECIONADAS (2)")
        restaurar.assert_not_called()

    def test_32_filtro_data_seleciona_somente_operacoes_da_data(self):
        from tests.test_correcao09b import PaginaRestauracao

        itens = itens_operacao(1, "antiga", timestamp="2026-09-01 10:00:00")
        itens += itens_operacao(1, "nova", timestamp="2026-09-02 10:00:00")
        win, _ = PaginaRestauracao.criar(itens)
        indice = win.cmb_filtro_restauracao.findData("2026-09-01")
        win.cmb_filtro_restauracao.setCurrentIndex(indice)
        win.lista_restauracao.header().checkbox_mestre.click()

        self.assertEqual(win._restauracao_selecionadas, {
            (r"C:\Cliente\AikaOnlineBrasil", "antiga")
        })
        self.assertEqual(win.lista_restauracao.operacoes_elegiveis(), [
            (r"C:\Cliente\AikaOnlineBrasil", "antiga")
        ])

    def test_33_mudar_filtro_remove_ocultas_e_recalcula_mestre(self):
        from tests.test_correcao09b import PaginaRestauracao

        itens = itens_operacao(1, "antiga", timestamp="2026-09-01 10:00:00")
        itens += itens_operacao(1, "nova", timestamp="2026-09-02 10:00:00")
        win, _ = PaginaRestauracao.criar(itens)
        win.lista_restauracao.header().checkbox_mestre.click()
        self.assertEqual(len(win._restauracao_selecionadas), 2)

        indice = win.cmb_filtro_restauracao.findData("2026-09-01")
        win.cmb_filtro_restauracao.setCurrentIndex(indice)
        self.assertEqual(win._restauracao_selecionadas, {
            (r"C:\Cliente\AikaOnlineBrasil", "antiga")
        })
        self.assertEqual(
            win.lista_restauracao.header().checkbox_mestre.checkState(),
            Qt.Checked,
        )

    def test_34_atualizar_registros_recalcula_estado_mestre(self):
        from tests.test_correcao09b import PaginaRestauracao

        iniciais = itens_operacao(1, "op-a")
        win, _ = PaginaRestauracao.criar(iniciais)
        win.lista_restauracao.header().checkbox_mestre.click()
        self.assertEqual(
            win.lista_restauracao.header().checkbox_mestre.checkState(),
            Qt.Checked,
        )

        atualizados = iniciais + itens_operacao(1, "op-b")
        win._atualizar_historico_automod(atualizados)
        self.assertEqual(win._restauracao_selecionadas, {
            (r"C:\Cliente\AikaOnlineBrasil", "op-a")
        })
        self.assertEqual(
            win.lista_restauracao.header().checkbox_mestre.checkState(),
            Qt.PartiallyChecked,
        )

    def test_35_mudanca_elegibilidade_remove_operacao_marcada(self):
        widget = self._widget_com_operacoes(2)
        alteradas = []
        widget.selecao_alterada.connect(
            lambda identidade, marcado: alteradas.append(
                (identidade, marcado)
            )
        )
        widget.header().checkbox_mestre.click()
        item = operation_items(widget)[0]
        identidade = widget._identidade_item(item)
        item.setDisabled(True)

        self.assertEqual(item.checkState(rlist.COL_CHECKBOX), Qt.Unchecked)
        self.assertNotIn(identidade, widget.operacoes_elegiveis())
        self.assertEqual(alteradas[-1], (identidade, False))
        self.assertEqual(
            widget.header().checkbox_mestre.checkState(), Qt.Checked
        )

    def test_36_selecao_mestre_alimenta_fluxo_com_clientes_exatos(self):
        from unittest.mock import MagicMock, patch
        from tests.test_correcao09b import PaginaRestauracao

        itens = [
            item("Data/a.jit", "op-a", cliente=r"C:\ClienteA"),
            item("Data/b.jit", "op-b", cliente=r"C:\ClienteB"),
        ]
        win, _ = PaginaRestauracao.criar(itens)
        win.lista_restauracao.header().checkbox_mestre.click()
        win.sinais = MagicMock()

        class FakeMessageBox:
            Warning = 1
            AcceptRole = 2
            RejectRole = 3

            def __init__(self, *_): self.restaurar = None
            def setWindowTitle(self, *_): pass
            def setIcon(self, *_): pass
            def setText(self, *_): pass
            def setInformativeText(self, *_): pass
            def setDefaultButton(self, *_): pass
            def exec(self): pass

            def addButton(self, texto, *_):
                botao = object()
                if texto == "RESTAURAR":
                    self.restaurar = botao
                return botao

            def clickedButton(self): return self.restaurar

        with patch.object(main, "QMessageBox", FakeMessageBox), \
             patch.object(main, "_restaurar_chaves_historico",
                          return_value={"restaurados": [], "falhas": []}) as restaurar, \
             patch.object(main.opt, "listar_mods_ativos", return_value=[]), \
             patch.object(win, "executar_em_background",
                          side_effect=lambda tarefa: tarefa()):
            win._on_restaurar_mod_selecionado()

        chamadas = {
            (tuple(chamada.args[0]), chamada.args[1])
            for chamada in restaurar.call_args_list
        }
        self.assertEqual(chamadas, {
            (("Data/a.jit",), r"C:\ClienteA"),
            (("Data/b.jit",), r"C:\ClienteB"),
        })


class TestVazioFiltroESelecao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_16_lista_vazia_exibe_estado_vazio(self):
        widget = rlist.RestoreListWidget()
        widget.populate([])
        self.assertEqual(widget.topLevelItemCount(), 1)
        self.assertIn("Nenhum backup", widget.topLevelItem(0).text(rlist.COL_NOME))
        self.assertEqual(widget.operacoes_visiveis(), [])

    def test_17_repopular_preserva_checks_visiveis(self):
        row = rlist.build_operation_row(operacao(itens_operacao(2, "op-a")))
        widget = rlist.RestoreListWidget()
        chave = (r"C:\Cliente\AikaOnlineBrasil", "op-a")
        widget.populate([row], {chave})
        self.assertEqual(widget.topLevelItem(0).checkState(rlist.COL_CHECKBOX), Qt.Checked)

    def test_18_filtro_remove_selecao_oculta_e_pedras_fora_da_data(self):
        from unittest.mock import patch
        from tests.test_correcao09b import PaginaRestauracao

        itens = itens_operacao(1, "antiga", timestamp="2026-01-01 10:00:00")
        itens += itens_operacao(1, "nova", timestamp="2026-02-01 10:00:00")
        with patch.object(main.opt, "listar_mods_ativos", return_value=itens), \
             patch.object(main.opt, "obter_pasta_jogo_atual", return_value=r"C:\Fake"):
            win, _ = PaginaRestauracao.criar(itens)
        win._restauracao_selecionadas = {
            (r"C:\Cliente\AikaOnlineBrasil", "antiga"),
            (r"C:\Cliente\AikaOnlineBrasil", "nova"),
        }
        indice = win.cmb_filtro_restauracao.findData("2026-01-01")
        win.cmb_filtro_restauracao.setCurrentIndex(indice)
        self.assertEqual(
            win._restauracao_selecionadas,
            {(r"C:\Cliente\AikaOnlineBrasil", "antiga")},
        )
        self.assertEqual(win.lista_restauracao.operacoes_visiveis(), [
            (r"C:\Cliente\AikaOnlineBrasil", "antiga")
        ])
        kinds = [
            win.lista_restauracao.topLevelItem(i).data(
                rlist.COL_CHECKBOX, Qt.UserRole + 2
            ) for i in range(win.lista_restauracao.topLevelItemCount())
        ]
        self.assertNotIn("pedras", kinds)

    def test_19_lote_agrupa_chaves_por_cliente_de_origem(self):
        grupos = main._agrupar_chaves_por_cliente([
            {"game_root": r"C:\ClienteA", "keys": ["a.jit", "comum.jit"]},
            {"game_root": r"C:\ClienteB", "keys": ["b.jit", "comum.jit"]},
            {"game_root": r"C:\ClienteA", "keys": ["a.jit", "c.jit"]},
        ])
        self.assertEqual(grupos, {
            r"C:\ClienteA": ["a.jit", "comum.jit", "c.jit"],
            r"C:\ClienteB": ["b.jit", "comum.jit"],
        })

    def test_20_fluxo_de_lote_restaura_cada_cliente_separadamente(self):
        from unittest.mock import MagicMock, patch
        from tests.test_correcao09b import PaginaRestauracao

        itens = [
            item("Data/igual.jit", "op-a", cliente=r"C:\ClienteA"),
            item("Data/igual.jit", "op-b", cliente=r"C:\ClienteB"),
        ]
        win, _ = PaginaRestauracao.criar(itens)
        win._restauracao_selecionadas = {
            (r"C:\ClienteA", "op-a"), (r"C:\ClienteB", "op-b")
        }
        win.sinais = MagicMock()

        class FakeMessageBox:
            Warning = 1
            AcceptRole = 2
            RejectRole = 3

            def __init__(self, *_):
                self.restaurar = None

            def setWindowTitle(self, *_): pass
            def setIcon(self, *_): pass
            def setText(self, *_): pass
            def setInformativeText(self, *_): pass
            def setDefaultButton(self, *_): pass
            def exec(self): pass

            def addButton(self, texto, *_):
                botao = object()
                if texto == "RESTAURAR":
                    self.restaurar = botao
                return botao

            def clickedButton(self):
                return self.restaurar

        with patch.object(main, "QMessageBox", FakeMessageBox), \
             patch.object(main, "_restaurar_chaves_historico",
                          return_value={"restaurados": ["igual.jit"], "falhas": []}) as restaurar, \
             patch.object(main.opt, "listar_mods_ativos", return_value=[]), \
             patch.object(win, "executar_em_background", side_effect=lambda tarefa: tarefa()):
            win._on_restaurar_mod_selecionado()

        self.assertEqual(restaurar.call_count, 2)
        chamadas = {
            (tuple(chamada.args[0]), chamada.args[1])
            for chamada in restaurar.call_args_list
        }
        self.assertEqual(chamadas, {
            (("Data/igual.jit",), r"C:\ClienteA"),
            (("Data/igual.jit",), r"C:\ClienteB"),
        })


if __name__ == "__main__":
    unittest.main(verbosity=2)