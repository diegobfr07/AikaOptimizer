# -*- coding: utf-8 -*-
"""Correção 09A — histórico e restore agrupados por operação."""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import main  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QListWidget, QPushButton  # noqa: E402


HASHES_CONGELADOS = {
    "automod.py": "F9422E65FA542D6D5A28CE2E3DD6D025544669601EA2522F42415BDA09E69609",
    "textura.py": "A890FDA024E47C57817F25E5845CE239F5C7F83CF571F1A674F9AD8F426CB8DE",
    "extractor_sets.py": "D3F01604DB2DF2A74FF6D9317FD177A8A3DA42CD92F6769D7B8DF34B21BCD58F",
    "set_injector.py": "D2765BBD157138F6A6AD4DB5997AAF69A212118349CD88257B5BFB2727E00919",
}


def item(chave, operation_id=None, timestamp="2026-09-02 22:49:00",
         tipo="SET_INJECTION", cliente=r"C:\Cliente\AikaOnlineBrasil",
         origem="3801", alvo="3002", operacao_arquivo="REPLACE"):
    dados = {
        "chave": chave,
        "target_relpath": chave,
        "target_name": os.path.basename(chave),
        "last_applied": timestamp,
        "injection_count": 1,
        "game_root": cliente,
        "operation": operacao_arquivo,
    }
    if operation_id:
        dados.update({
            "operation_id": operation_id,
            "operation_type": tipo,
            "operation_timestamp": timestamp,
            "operation_source": origem,
            "operation_target": alvo,
            "operation_class": "Atirador",
            "operation_client": os.path.basename(os.path.normpath(cliente)),
        })
    return dados


def itens_operacao(quantidade, operation_id="op-set", **kwargs):
    return [item(f"Data/{operation_id}_arquivo_{indice:02d}.jit", operation_id, **kwargs)
            for indice in range(quantidade)]


class JanelaHistorico:
    @staticmethod
    def criar(itens):
        QApplication.instance() or QApplication([])
        win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
        win.lista_historico = QListWidget()
        win.btn_restaurar_mod = QPushButton()
        win._atualizando_historico = False
        win.lista_historico.itemChanged.connect(win._on_item_historico_alterado)
        win.lista_historico.itemClicked.connect(win._on_item_historico_clicado)
        win._atualizar_historico_automod(itens)
        return win

    @staticmethod
    def por_tipo(win, tipo):
        resultado = []
        for indice in range(win.lista_historico.count()):
            candidato = win.lista_historico.item(indice)
            dados = candidato.data(Qt.UserRole)
            if isinstance(dados, dict) and dados.get("kind") == tipo:
                resultado.append(candidato)
        return resultado


class TestAgrupamentoOperacoes(unittest.TestCase):
    def test_01_vinte_cinco_arquivos_mesmo_id_uma_operacao(self):
        operacoes = main._agrupar_operacoes_historico(itens_operacao(25))
        self.assertEqual(len(operacoes), 1)
        self.assertEqual(len(operacoes[0]["keys"]), 25)

    def test_02_operacao_um_arquivo_um_card(self):
        win = JanelaHistorico.criar(itens_operacao(1))
        self.assertEqual(len(JanelaHistorico.por_tipo(win, "operation")), 1)

    def test_03_duas_operacoes_mesmo_dia_sao_dois_cards(self):
        itens = itens_operacao(2, "op-a") + itens_operacao(3, "op-b")
        win = JanelaHistorico.criar(itens)
        self.assertEqual(len(JanelaHistorico.por_tipo(win, "operation")), 2)
        self.assertIn("2 operações", JanelaHistorico.por_tipo(win, "date")[0].text())

    def test_04_horarios_diferentes_nao_misturam_operacoes(self):
        itens = itens_operacao(2, "op-a", timestamp="2026-09-02 20:00:00")
        itens += itens_operacao(2, "op-b", timestamp="2026-09-02 21:00:00")
        operacoes = main._agrupar_operacoes_historico(itens)
        self.assertEqual({op["operation_id"] for op in operacoes}, {"op-a", "op-b"})

    def test_05_set_vinte_cinco_selecao_unica_expande_chaves(self):
        operacao = main._agrupar_operacoes_historico(itens_operacao(25))[0]
        chaves = main._chaves_das_operacoes([operacao])
        self.assertEqual(len(chaves), 25)
        self.assertEqual(main._rotulo_tipo_operacao(operacao["operation_type"]),
                         "INJEÇÃO DE SET")
        with patch.object(main.opt, "listar_mods_ativos",
                          return_value=operacao["items"]), \
             patch.object(main.opt, "restaurar_mods_selecionados",
                          return_value={"restaurados": list(chaves), "falhas": []}) as restaurar:
            resultado = main._restaurar_chaves_historico(chaves, operacao["game_root"])
        restaurar.assert_called_once_with(chaves, operacao["game_root"])
        self.assertEqual(len(resultado["restaurados"]), 25)

    def test_06_arma_tres_arquivos_uma_operacao(self):
        itens = itens_operacao(
            3, "op-arma", tipo="WEAPON_INJECTION",
            origem="RIF00044", alvo="RIF00036",
        )
        operacoes = main._agrupar_operacoes_historico(itens)
        self.assertEqual(len(operacoes), 1)
        self.assertEqual(len(operacoes[0]["keys"]), 3)
        self.assertEqual(main._subtitulo_operacao(operacoes[0]),
                         "RIF00044 → RIF00036")

    def test_07_automod_multiplos_arquivos_uma_operacao(self):
        itens = itens_operacao(7, "op-automod", tipo="AUTOMOD",
                               origem=None, alvo=None)
        operacoes = main._agrupar_operacoes_historico(itens)
        self.assertEqual(len(operacoes), 1)
        self.assertEqual(operacoes[0]["operation_type"], "AUTOMOD")
        self.assertEqual(len(operacoes[0]["items"]), 7)


class TestDetalhesESelecao(unittest.TestCase):
    def test_08_expansao_mostra_todos_arquivos(self):
        win = JanelaHistorico.criar(itens_operacao(5))
        card = JanelaHistorico.por_tipo(win, "operation")[0]
        win._on_item_historico_clicado(card)
        detalhes = JanelaHistorico.por_tipo(win, "detail")
        self.assertEqual(len(detalhes), 5)
        self.assertTrue(all(not detalhe.isHidden() for detalhe in detalhes))

    def test_09_arquivos_ocultos_por_padrao(self):
        win = JanelaHistorico.criar(itens_operacao(5))
        detalhes = JanelaHistorico.por_tipo(win, "detail")
        self.assertTrue(detalhes)
        self.assertTrue(all(detalhe.isHidden() for detalhe in detalhes))

    def test_10_marcar_operacao_seleciona_todas_chaves_internas(self):
        win = JanelaHistorico.criar(itens_operacao(4))
        card = JanelaHistorico.por_tipo(win, "operation")[0]
        card.setCheckState(Qt.Checked)
        marcadas = win._operacoes_historico_marcadas()
        self.assertEqual(len(marcadas), 1)
        self.assertEqual(len(marcadas[0][1]["keys"]), 4)

    def test_11_desmarcar_operacao_remove_selecao_interna(self):
        win = JanelaHistorico.criar(itens_operacao(4))
        card = JanelaHistorico.por_tipo(win, "operation")[0]
        card.setCheckState(Qt.Checked)
        card.setCheckState(Qt.Unchecked)
        self.assertFalse(win._operacoes_historico_marcadas())

    def test_12_selecao_data_marca_todas_operacoes_do_dia(self):
        itens = itens_operacao(2, "op-a") + itens_operacao(3, "op-b")
        win = JanelaHistorico.criar(itens)
        data = JanelaHistorico.por_tipo(win, "date")[0]
        data.setCheckState(Qt.Checked)
        self.assertEqual(len(win._operacoes_historico_marcadas()), 2)


class TestRestorePorOperacao(unittest.TestCase):
    def test_13_restaurar_uma_nao_inclui_outra_do_mesmo_dia(self):
        op_a, op_b = main._agrupar_operacoes_historico(
            itens_operacao(2, "op-a", timestamp="2026-09-02 22:00:00")
            + itens_operacao(3, "op-b", timestamp="2026-09-02 21:00:00")
        )
        chaves = main._chaves_das_operacoes([op_a])
        self.assertEqual(set(chaves), set(op_a["keys"]))
        self.assertFalse(set(chaves) & set(op_b["keys"]))

    def test_14_multiplas_restaura_somente_selecionadas(self):
        operacoes = main._agrupar_operacoes_historico(
            itens_operacao(2, "op-a")
            + itens_operacao(3, "op-b", timestamp="2026-09-01 21:00:00")
            + itens_operacao(4, "op-c", timestamp="2026-08-31 21:00:00")
        )
        selecionadas = [op for op in operacoes if op["operation_id"] != "op-b"]
        chaves = main._chaves_das_operacoes(selecionadas)
        op_b = next(op for op in operacoes if op["operation_id"] == "op-b")
        self.assertEqual(len(chaves), 6)
        self.assertFalse(set(chaves) & set(op_b["keys"]))
        todos_itens = [arquivo for op in operacoes for arquivo in op["items"]]
        with patch.object(main.opt, "listar_mods_ativos", return_value=todos_itens), \
             patch.object(main.opt, "restaurar_mods_selecionados",
                          return_value={"restaurados": list(chaves), "falhas": []}) as restaurar:
            main._restaurar_chaves_historico(chaves, r"C:\Cliente")
        restaurar.assert_called_once_with(chaves, r"C:\Cliente")


class TestLegacyMetadadosEIntegridade(unittest.TestCase):
    def test_15_historico_legacy_continua_carregando(self):
        operacoes = main._agrupar_operacoes_historico([item("Data/antigo.jit")])
        self.assertEqual(len(operacoes), 1)
        self.assertTrue(operacoes[0]["legacy"])
        self.assertEqual(operacoes[0]["operation_type"], "LEGACY")

    def test_16_legacy_ambiguo_nao_e_agrupado_por_timestamp(self):
        antigos = [item("Data/a.jit"), item("Data/b.jit")]
        operacoes = main._agrupar_operacoes_historico(antigos)
        self.assertEqual(len(operacoes), 2)
        self.assertEqual(len({op["operation_id"] for op in operacoes}), 2)

    def test_17_delete_legado_usa_restore_especializado(self):
        itens = [item("Data/a.jit"), item("Data/bEF.jit", operacao_arquivo="DELETE")]
        with patch.object(main.opt, "listar_mods_ativos", return_value=itens), \
             patch.object(main.opt, "restaurar_mods_selecionados",
                          return_value={"restaurados": ["a.jit"], "falhas": []}) as normal, \
             patch.object(main.sinj, "restaurar_ef_removido",
                          return_value=(True, "ok")) as delete:
            resultado = main._restaurar_chaves_historico(
                ["Data/a.jit", "Data/bEF.jit"], r"C:\Cliente"
            )
        normal.assert_called_once_with(["Data/a.jit"], r"C:\Cliente")
        delete.assert_called_once_with("Data/bEF.jit", r"C:\Cliente")
        self.assertEqual(len(resultado["restaurados"]), 2)

    def test_18_cliente_correto_permanece_associado(self):
        cliente = r"D:\Jogos\AikaBR"
        operacao = main._agrupar_operacoes_historico(
            itens_operacao(2, cliente=cliente)
        )[0]
        self.assertEqual(operacao["game_root"], cliente)
        self.assertEqual(operacao["client_name"], "AikaBR")

    def test_19_anotacao_nao_altera_backup_ou_itens_alheios(self):
        historico = {
            "version": 2,
            "game_root": r"C:\Cliente",
            "items": {
                "data/a.jit": {
                    "backup_relpath": "Data/a.jit", "injection_count": 2,
                    "last_applied": "2026-09-02 22:00:00",
                },
                "data/b.jit": {
                    "backup_relpath": "Data/b.jit", "injection_count": 1,
                    "last_applied": "2026-09-01 21:00:00",
                },
            },
        }
        salvo = []
        original = json.loads(json.dumps(historico))
        with patch.object(main.opt, "carregar_historico_automod", return_value=historico), \
             patch.object(main.opt, "salvar_historico_automod",
                          side_effect=lambda dados, pasta: salvo.append(dados) or True):
            ok, afetadas = main._anotar_operacao_historico(
                r"C:\Cliente", {}, {"operation_id": "op"},
                chaves_exatas=["data/a.jit"],
            )
        self.assertTrue(ok)
        self.assertEqual(afetadas, ["data/a.jit"])
        self.assertEqual(salvo[0]["items"]["data/a.jit"]["backup_relpath"],
                         original["items"]["data/a.jit"]["backup_relpath"])
        self.assertNotIn("operation_id", salvo[0]["items"]["data/b.jit"])

    def test_20_motores_congelados_byte_a_byte(self):
        for nome, esperado in HASHES_CONGELADOS.items():
            atual = hashlib.sha256((RAIZ / nome).read_bytes()).hexdigest().upper()
            self.assertEqual(atual, esperado, nome)


if __name__ == "__main__":
    unittest.main(verbosity=2)