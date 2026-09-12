# -*- coding: utf-8 -*-
"""Refinamento final de Configurações: .JIT coerente + nivelamento dos cards.

Valida (sem tocar Registry/config reais — tudo simulado):
- checkbox reflete o ESTADO REAL da associação no Registro;
- sincronização não dispara criação/remoção;
- marcar cria / desmarcar remove; falhas nunca deixam a UI mentindo;
- instalação nova = associação ativa por padrão no primeiro uso;
- escolha explícita do usuário é respeitada (nunca reativar no restart);
- label "ASSOCIAÇÃO: ATIVA/INATIVA" removida da UI;
- texto de "Fechar para bandeja" atualizado;
- política de altura compartilhada entre os cards superiores.
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from PySide6.QtCore import Qt

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import main as main_module  # noqa: E402


class FakeCheck:
    def __init__(self):
        self._v = False
        self.checked_calls = []
        self.signals_blocked = []

    def blockSignals(self, valor):
        self.signals_blocked.append(bool(valor))

    def setChecked(self, valor):
        self._v = bool(valor)
        self.checked_calls.append(bool(valor))

    def isChecked(self):
        return self._v


class FakeLog:
    def __init__(self):
        self.msg = []

    def emit(self, m):
        self.msg.append(m)


def _montar(status_inicial="INATIVA", user_set=False, integration=False):
    """Janela stub sem construir a janela real (sem Registry/config reais)."""
    janela = SimpleNamespace(
        chk_jit_windows=FakeCheck(),
        sinais=SimpleNamespace(log_signal=FakeLog()),
    )
    cls = main_module.AikaOptimizerPro
    janela._estado_associacao_jit_ativa = cls._estado_associacao_jit_ativa.__get__(
        janela, cls)
    janela._sincronizar_checkbox_jit = cls._sincronizar_checkbox_jit.__get__(
        janela, cls)

    estado = {"status": status_inicial}
    config_valores = {"jit_windows_user_set": user_set,
                      "jit_windows_integration": integration}
    config_gravados = {}

    def _status():
        return estado["status"]

    def _obter(chave, padrao=None):
        return config_valores.get(chave, padrao)

    def _definir(chave, valor):
        config_valores[chave] = valor
        config_gravados[chave] = valor

    patches = [
        mock.patch.object(main_module.opt, "obter_config", side_effect=_obter),
        mock.patch.object(main_module.opt, "definir_config", side_effect=_definir),
        mock.patch.object(main_module.jit_integration,
                          "obter_status_associacao_jit", side_effect=_status),
        mock.patch.object(main_module.jit_integration,
                          "registrar_integracao_windows",
                          side_effect=lambda: estado.update(status="ATIVA")),
        mock.patch.object(main_module.jit_integration,
                          "desregistrar_integracao_windows",
                          side_effect=lambda: estado.update(status="INATIVA")),
    ]
    for p in patches:
        p.start()
    return janela, estado, config_gravados, patches


class TestCheckboxJITEstadoReal(unittest.TestCase):
    """Items 1-7: checkbox representa o estado real do Registro."""

    def tearDown(self):
        if hasattr(self, "_patches"):
            for p in self._patches:
                p.stop()

    def test_01_associacao_ativa_marca_checkbox(self):
        janela, *_ = _montar(status_inicial="ATIVA")
        main_module.AikaOptimizerPro._sincronizar_checkbox_jit(janela)
        self.assertTrue(janela.chk_jit_windows.isChecked())

    def test_02_associacao_inativa_desmarca_checkbox(self):
        janela, *_ = _montar(status_inicial="INATIVA")
        main_module.AikaOptimizerPro._sincronizar_checkbox_jit(janela)
        self.assertFalse(janela.chk_jit_windows.isChecked())

    def test_03_sincronizacao_nao_dispara_registry(self):
        janela, _, _, ps = _montar(status_inicial="ATIVA")
        self._patches = ps
        main_module.AikaOptimizerPro._sincronizar_checkbox_jit(janela)
        main_module.jit_integration.registrar_integracao_windows.assert_not_called()
        main_module.jit_integration.desregistrar_integracao_windows.assert_not_called()

    def test_04_marcar_cria_associacao(self):
        janela, estado, cfg, ps = _montar(status_inicial="INATIVA")
        self._patches = ps
        estado["status"] = "INATIVA"
        main_module.AikaOptimizerPro.acao_toggle_jit_windows(janela, Qt.Checked.value)
        main_module.jit_integration.registrar_integracao_windows.assert_called_once()
        self.assertTrue(janela.chk_jit_windows.isChecked())
        self.assertTrue(cfg.get("jit_windows_user_set"))
        self.assertTrue(cfg.get("jit_windows_integration"))

    def test_05_desmarcar_remove_associacao(self):
        janela, estado, cfg, ps = _montar(status_inicial="ATIVA")
        self._patches = ps
        estado["status"] = "ATIVA"
        main_module.AikaOptimizerPro.acao_toggle_jit_windows(janela, Qt.Unchecked.value)
        main_module.jit_integration.desregistrar_integracao_windows.assert_called_once()
        self.assertFalse(janela.chk_jit_windows.isChecked())
        self.assertFalse(cfg.get("jit_windows_integration"))

    def test_06_falha_ao_associar_nao_deixa_marcado_falsamente(self):
        janela, estado, cfg, ps = _montar(status_inicial="INATIVA")
        self._patches = ps
        # registrar não muda o estado real (falha silenciosa)
        main_module.jit_integration.registrar_integracao_windows.side_effect = \
            lambda: None
        main_module.AikaOptimizerPro.acao_toggle_jit_windows(janela, Qt.Checked.value)
        self.assertFalse(janela.chk_jit_windows.isChecked(),
                         "falha não pode deixar o checkbox marcado")
        self.assertNotEqual(cfg.get("jit_windows_integration"), True)

    def test_07_falha_ao_remover_nao_mente_na_ui(self):
        janela, estado, _, ps = _montar(status_inicial="ATIVA")
        self._patches = ps
        main_module.jit_integration.desregistrar_integracao_windows.side_effect = \
            lambda: None  # não remove: estado permanece ATIVA
        main_module.AikaOptimizerPro.acao_toggle_jit_windows(janela, Qt.Unchecked.value)
        self.assertTrue(janela.chk_jit_windows.isChecked(),
                        "UI deve refletir o estado real (ainda associado)")
        self.assertTrue(any("Não foi possível remover" in m
                            for m in janela.sinais.log_signal.msg))


class TestDefaultAssociacao(unittest.TestCase):
    """Items 8-10: padrão no primeiro uso + escolha do usuário respeitada."""

    def tearDown(self):
        if hasattr(self, "_patches"):
            for p in self._patches:
                p.stop()

    def test_08_instalacao_nova_ativa_por_padrao(self):
        janela, estado, cfg, ps = _montar(status_inicial="INATIVA")
        self._patches = ps
        main_module.AikaOptimizerPro._garantir_associacao_padrao_jit(janela)
        main_module.jit_integration.registrar_integracao_windows.assert_called_once()
        self.assertEqual(estado["status"], "ATIVA")
        self.assertTrue(cfg.get("jit_windows_integration"))

    def test_09_usuario_desativou_e_escolha_permanece(self):
        # Simula: usuário desmarcou (user_set=True, integration=False) → restart.
        janela, _, cfg, ps = _montar(status_inicial="INATIVA",
                                     user_set=True, integration=False)
        self._patches = ps
        main_module.AikaOptimizerPro._garantir_associacao_padrao_jit(janela)
        main_module.jit_integration.registrar_integracao_windows.assert_not_called()
        self.assertFalse(cfg.get("jit_windows_integration", False))

    def test_10_estado_nao_depende_apenas_de_config_obsoleto(self):
        # config diz True, mas o Registro real diz INATIVA → checkbox desmarcado.
        janela, *_ = _montar(status_inicial="INATIVA", integration=True)
        main_module.AikaOptimizerPro._sincronizar_checkbox_jit(janela)
        self.assertFalse(janela.chk_jit_windows.isChecked())


class TestTextosELayout(unittest.TestCase):
    """Items 11-14: labels removidos, textos/layout corretos."""

    def test_11_label_associacao_solta_removida(self):
        with open(os.path.join(RAIZ, "main.py"), encoding="utf-8") as f:
            fonte = f.read()
        self.assertNotIn("ASSOCIAÇÃO:", fonte)
        self.assertNotIn("lbl_jit_assoc_status", fonte)
        self.assertNotIn("btn_jit_reparar", fonte)

    def test_12_texto_fechar_para_bandeja_atualizado(self):
        with open(os.path.join(RAIZ, "main.py"), encoding="utf-8") as f:
            fonte = f.read()
        self.assertIn("Ao clicar no X, o aplicativo vai para a bandeja.", fonte)
        self.assertNotIn("continua em segundo plano", fonte)

    def test_13_cards_superiores_nivelados(self):
        with open(os.path.join(RAIZ, "main.py"), encoding="utf-8") as f:
            fonte = f.read()
        self.assertIn("altura_maxima = max(", fonte)
        self.assertIn("setMinimumHeight(altura_maxima)", fonte)
        self.assertIn("Qt.AlignTop", fonte)

    def test_14_demais_opcoes_continuam_conectadas(self):
        with open(os.path.join(RAIZ, "main.py"), encoding="utf-8") as f:
            fonte = f.read()
        for alvo in ("acao_toggle_startup", "acao_toggle_start_minimized",
                     "acao_toggle_close_to_tray", "acao_toggle_auto_boost",
                     "acao_toggle_aggressive"):
            self.assertIn(f".stateChanged.connect(self.{alvo})", fonte)


if __name__ == "__main__":
    unittest.main()


