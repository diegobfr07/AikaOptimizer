# -*- coding: utf-8 -*-
"""Hardening do plano de energia / fallback seguro (P2 #2).

Garante que a ausência do plano Alto Desempenho (ou falha na consulta/ativação)
NUNCA derruba a Otimização Global e nunca cria planos novos. NENHUM teste
executa powercfg real, Registry real ou processo real.
"""
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import seguranca  # noqa: E402
import sistema  # noqa: E402

GUID_HP = sistema.GUID_ALTO_DESEMPENHO
GUID_BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"
GUID_OEM = "abcdef12-3456-7890-abcd-ef1234567890"


def _saida_en():
    return (
        "Existing Power Schemes (* Active)\n"
        "-----------------------------------\n"
        f"Power Scheme GUID: {GUID_BALANCED}  (Balanced) *\n"
        f"Power Scheme GUID: {GUID_HP}  (High performance)\n"
    )


def _saida_ptbr():
    return (
        "Esquemas de Energia Existentes (* Ativo)\n"
        "-----------------------------------\n"
        f"GUID do Esquema de Energia: {GUID_BALANCED}  (Equilibrado) *\n"
        f"GUID do Esquema de Energia: {GUID_HP}  (Alto desempenho)\n"
    )


class TestParser(unittest.TestCase):
    def test_01_balanced_e_high_performance(self):
        guids = seguranca._parsear_guids_powercfg(_saida_en())
        self.assertEqual(guids, {GUID_BALANCED, GUID_HP})

    def test_02_high_performance_ptbr(self):
        guids = seguranca._parsear_guids_powercfg(_saida_ptbr())
        self.assertIn(GUID_HP, guids)
        self.assertIn(GUID_BALANCED, guids)

    def test_03_high_performance_ingles(self):
        guids = seguranca._parsear_guids_powercfg(_saida_en())
        self.assertIn(GUID_HP, guids)

    def test_04_independe_do_nome_localizado(self):
        # Nomes diferentes, mesmos GUIDs -> mesmo resultado.
        self.assertEqual(
            seguranca._parsear_guids_powercfg(_saida_en()),
            seguranca._parsear_guids_powercfg(_saida_ptbr()),
        )

    def test_05_tolera_capitalizacao_e_espacos(self):
        saida = f"Power Scheme GUID:   {GUID_HP.upper()}    (HIGH PERFORMANCE) \n"
        guids = seguranca._parsear_guids_powercfg(saida)
        self.assertEqual(guids, {GUID_HP})

    def test_06_sem_high_performance_reconhecido(self):
        saida = f"Power Scheme GUID: {GUID_BALANCED}  (Balanced) *\n"
        guids = seguranca._parsear_guids_powercfg(saida)
        self.assertNotIn(GUID_HP, guids)
        self.assertEqual(guids, {GUID_BALANCED})


class TestEnumeracao(unittest.TestCase):
    def test_07_list_falhando_nao_retorna_planos(self):
        with mock.patch.object(seguranca.subprocess, "check_output",
                               side_effect=OSError("access denied")):
            self.assertIsNone(seguranca.obter_planos_energia_disponiveis())


class TestAplicacao(unittest.TestCase):
    def _modo(self, planos, atual, setactive_result=True):
        with mock.patch.object(sistema, "obter_planos_energia_disponiveis", return_value=planos), \
             mock.patch.object(sistema, "obter_plano_energia_atual", return_value=atual), \
             mock.patch.object(sistema, "executar_comando_seguro", return_value=setactive_result) as mex, \
             mock.patch.object(sistema, "log"):
            res = sistema.modo_desempenho_maximo()
        return res, mex

    def test_08_hp_disponivel_ativa(self):
        res, mex = self._modo({GUID_BALANCED, GUID_HP}, GUID_BALANCED, True)
        self.assertEqual(res, sistema.PLANO_SUCESSO)
        mex.assert_called_once()
        self.assertIn(GUID_HP, mex.call_args.args[0])

    def test_09_hp_ja_ativo_idempotente(self):
        res, mex = self._modo({GUID_BALANCED, GUID_HP}, GUID_HP, True)
        self.assertEqual(res, sistema.PLANO_NOOP)
        mex.assert_not_called()

    def test_10_hp_ausente_skip(self):
        res, mex = self._modo({GUID_BALANCED}, GUID_BALANCED, True)
        self.assertEqual(res, sistema.PLANO_SKIP)

    def test_11_hp_ausente_nao_setactive(self):
        res, mex = self._modo({GUID_BALANCED}, GUID_BALANCED, True)
        mex.assert_not_called()

    def test_12_list_falha_skip_sem_setactive(self):
        res, mex = self._modo(None, GUID_BALANCED, True)
        self.assertEqual(res, sistema.PLANO_SKIP)
        mex.assert_not_called()

    def test_13_nao_cria_plano_nem_duplicatescheme(self):
        # Nunca tenta /duplicatescheme nem qualquer criação de plano.
        res, mex = self._modo({GUID_BALANCED}, GUID_BALANCED, True)
        for call in mex.call_args_list:
            cmd = [str(x) for x in call.args[0]]
            self.assertNotIn("/duplicatescheme", cmd)
            self.assertNotIn("duplicatescheme", " ".join(cmd))

    def test_14_setactive_falha_nao_sucesso_falso(self):
        res, mex = self._modo({GUID_BALANCED, GUID_HP}, GUID_BALANCED, False)
        self.assertEqual(res, sistema.PLANO_FALHA)
        self.assertNotEqual(res, sistema.PLANO_SUCESSO)

    def test_15_falha_local_nao_derruba_transacao(self):
        t = seguranca.TransacaoSistema()
        with mock.patch.object(sistema, "obter_planos_energia_disponiveis", return_value={GUID_BALANCED, GUID_HP}), \
             mock.patch.object(sistema, "obter_plano_energia_atual", return_value=GUID_BALANCED), \
             mock.patch.object(sistema, "executar_comando_seguro", return_value=False), \
             mock.patch.object(sistema, "log"):
            resultado = t.executar(sistema.modo_desempenho_maximo)
        self.assertEqual(resultado, sistema.PLANO_FALHA)

    def test_16_plano_atual_permanece_sem_alteracao(self):
        # /setactive falha → o plano atual (Balanced) não muda; retorna FALHA.
        res, mex = self._modo({GUID_BALANCED, GUID_HP}, GUID_BALANCED, False)
        self.assertEqual(res, sistema.PLANO_FALHA)
        mex.assert_called_once()  # tentou, mas não "fingiu" sucesso


class TestRollback(unittest.TestCase):
    def test_17_rollback_restaura_plano_anterior(self):
        t = seguranca.TransacaoSistema()
        chamadas = []

        def rollback_plano():
            chamadas.append("rollback_plano")
            return True

        def falha():
            raise RuntimeError("boom")

        with mock.patch.object(seguranca, "log"):
            t.executar(lambda: True, rollback=rollback_plano)
            with self.assertRaises(RuntimeError):
                t.executar(falha)
        self.assertEqual(chamadas, ["rollback_plano"])

    def test_18_skip_plano_ausente_nao_rollback(self):
        t = seguranca.TransacaoSistema()
        chamadas = []
        with mock.patch.object(sistema, "obter_planos_energia_disponiveis", return_value={GUID_BALANCED}), \
             mock.patch.object(sistema, "obter_plano_energia_atual", return_value=GUID_BALANCED), \
             mock.patch.object(sistema, "executar_comando_seguro", return_value=True), \
             mock.patch.object(sistema, "log"):
            res = t.executar(sistema.modo_desempenho_maximo, rollback=lambda: chamadas.append("rb"))
        self.assertEqual(res, sistema.PLANO_SKIP)
        self.assertEqual(chamadas, [])

    def test_19_falha_sem_alteracao_sem_rollback_desnecessario(self):
        t = seguranca.TransacaoSistema()
        chamadas = []
        with mock.patch.object(sistema, "obter_planos_energia_disponiveis", return_value={GUID_BALANCED, GUID_HP}), \
             mock.patch.object(sistema, "obter_plano_energia_atual", return_value=GUID_BALANCED), \
             mock.patch.object(sistema, "executar_comando_seguro", return_value=False), \
             mock.patch.object(sistema, "log"):
            res = t.executar(sistema.modo_desempenho_maximo, rollback=lambda: chamadas.append("rb"))
        self.assertEqual(res, sistema.PLANO_FALHA)
        self.assertEqual(chamadas, [])

    def test_20_rollback_plano_nao_toca_dns(self):
        estado = {"format_version": 2, "power_plan": GUID_BALANCED,
                  "dns_interfaces": [{"interface_guid": "x"}]}
        with mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            res = seguranca.restaurar_estado_sistema(estado, escopo="plano")
        self.assertEqual(res, seguranca.RESTAURACAO_SUCESSO)
        for call in mex.call_args_list:
            self.assertNotIn("DnsClientServerAddress", " ".join(str(x) for x in call.args[0]))

    def test_21_baseline_nao_afetada_pelo_plano(self):
        with mock.patch.object(sistema, "obter_planos_energia_disponiveis", return_value={GUID_BALANCED}), \
             mock.patch.object(sistema, "obter_plano_energia_atual", return_value=GUID_BALANCED), \
             mock.patch.object(sistema, "executar_comando_seguro", return_value=True), \
             mock.patch.object(sistema, "log"), \
             mock.patch.object(seguranca, "salvar_snapshot_sistema") as salvar, \
             mock.patch.object(seguranca, "_escrever_estado_atomico") as escrever:
            sistema.modo_desempenho_maximo()
        salvar.assert_not_called()
        escrever.assert_not_called()


class TestRestore(unittest.TestCase):
    def _restaurar_plano(self, guid, result=True):
        estado = {"format_version": 2, "power_plan": guid, "dns_interfaces": []}
        with mock.patch.object(seguranca, "executar_comando_seguro", return_value=result) as mex:
            res = seguranca.restaurar_estado_sistema(estado, escopo="plano")
        return res, mex

    def test_22_plano_oem_restaurado_por_guid(self):
        res, mex = self._restaurar_plano(GUID_OEM, True)
        self.assertEqual(res, seguranca.RESTAURACAO_SUCESSO)
        self.assertIn(GUID_OEM, [str(x) for x in mex.call_args.args[0]])

    def test_23_plano_balanced_restaurado(self):
        res, mex = self._restaurar_plano(GUID_BALANCED, True)
        self.assertEqual(res, seguranca.RESTAURACAO_SUCESSO)

    def test_24_plano_high_performance_restaurado(self):
        res, mex = self._restaurar_plano(GUID_HP, True)
        self.assertEqual(res, seguranca.RESTAURACAO_SUCESSO)
        self.assertIn(GUID_HP, [str(x) for x in mex.call_args.args[0]])

    def test_25_guid_original_ausente_nao_escolhe_outro(self):
        estado = {"format_version": 2, "power_plan": GUID_OEM, "dns_interfaces": []}
        with mock.patch.object(seguranca, "executar_comando_seguro", return_value=False) as mex:
            res = seguranca.restaurar_estado_sistema(estado, escopo="plano")
        self.assertEqual(res, seguranca.RESTAURACAO_FALHA)
        for call in mex.call_args_list:
            self.assertIn(GUID_OEM, [str(x) for x in call.args[0]])

    def test_26_restore_parcial_preserva_baseline(self):
        # Falha ao restaurar plano não reporta SUCCESS → baseline não é finalizada.
        estado = {"format_version": 2, "power_plan": GUID_OEM, "dns_interfaces": []}
        with mock.patch.object(seguranca, "executar_comando_seguro", return_value=False):
            res = seguranca.restaurar_estado_sistema(estado, escopo=None)
        self.assertNotEqual(res, seguranca.RESTAURACAO_SUCESSO)


class TestOtimizacaoGlobal(unittest.TestCase):
    def _fluxo(self, planos, atual, setactive_result=True):
        t = seguranca.TransacaoSistema()
        proximas = []
        with mock.patch.object(sistema, "obter_planos_energia_disponiveis", return_value=planos), \
             mock.patch.object(sistema, "obter_plano_energia_atual", return_value=atual), \
             mock.patch.object(sistema, "executar_comando_seguro", return_value=setactive_result), \
             mock.patch.object(sistema, "log"):
            res = t.executar(sistema.modo_desempenho_maximo)
            t.executar(lambda: proximas.append("proxima") or True)
        return res, proximas

    def test_27_pc_com_hp_fluxo_continua(self):
        res, proximas = self._fluxo({GUID_BALANCED, GUID_HP}, GUID_BALANCED, True)
        self.assertEqual(res, sistema.PLANO_SUCESSO)
        self.assertEqual(proximas, ["proxima"])

    def test_28_pc_sem_hp_fluxo_continua(self):
        res, proximas = self._fluxo({GUID_BALANCED}, GUID_BALANCED, True)
        self.assertEqual(res, sistema.PLANO_SKIP)
        self.assertEqual(proximas, ["proxima"])

    def test_29_list_falha_fluxo_continua(self):
        res, proximas = self._fluxo(None, GUID_BALANCED, True)
        self.assertEqual(res, sistema.PLANO_SKIP)
        self.assertEqual(proximas, ["proxima"])

    def test_30_setactive_falha_fluxo_continua(self):
        res, proximas = self._fluxo({GUID_BALANCED, GUID_HP}, GUID_BALANCED, False)
        self.assertEqual(res, sistema.PLANO_FALHA)
        self.assertEqual(proximas, ["proxima"])

    def test_31_modo_nunca_lanca(self):
        for planos, atual, setact in [
            ({GUID_BALANCED, GUID_HP}, GUID_BALANCED, True),
            ({GUID_BALANCED, GUID_HP}, GUID_HP, True),
            ({GUID_BALANCED}, GUID_BALANCED, True),
            (None, GUID_BALANCED, True),
            ({GUID_BALANCED, GUID_HP}, GUID_BALANCED, False),
        ]:
            with mock.patch.object(sistema, "obter_planos_energia_disponiveis", return_value=planos), \
                 mock.patch.object(sistema, "obter_plano_energia_atual", return_value=atual), \
                 mock.patch.object(sistema, "executar_comando_seguro", return_value=setact), \
                 mock.patch.object(sistema, "log"):
                sistema.modo_desempenho_maximo()  # nunca lança

    def test_32_resultado_distingue_estados(self):
        # SUCCESS / SKIP / FALHA são distintos — não mascaramos energia ignorada.
        self.assertNotEqual(sistema.PLANO_SUCESSO, sistema.PLANO_SKIP)
        self.assertNotEqual(sistema.PLANO_SUCESSO, sistema.PLANO_FALHA)
        self.assertNotEqual(sistema.PLANO_SKIP, sistema.PLANO_FALHA)

    def test_33_34_clientes_e_game_booster_intactos(self):
        import game_booster as gb
        self.assertTrue(callable(gb.game_session_optimizer))
        self.assertTrue(callable(gb.classificar_processo))
        self.assertEqual(
            gb.AIKA_GAME_EXES,
            {"aclient.exe", "aika.exe", "aika_br.exe", "aikabr.exe", "gameengine.exe"})


class TestIsolamento(unittest.TestCase):
    def test_35_obter_planos_usa_subprocess_mockavel(self):
        with mock.patch.object(seguranca.subprocess, "check_output",
                               return_value=_saida_en()):
            self.assertIn(GUID_HP, seguranca.obter_planos_energia_disponiveis())

    def test_36_sem_duplicatescheme_no_source(self):
        import pathlib
        for mod in (sistema, seguranca):
            src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
            self.assertNotIn("/duplicatescheme", src)
            self.assertNotIn("duplicatescheme", src)

    def test_37_config_real_nao_muda(self):
        import config
        import hashlib
        caminho = config.ARQUIVO_CONFIG
        if not os.path.isfile(caminho):
            self.skipTest("config.json real ausente")
        before = hashlib.sha256(open(caminho, "rb").read()).hexdigest()
        with mock.patch.object(sistema, "obter_planos_energia_disponiveis", return_value={GUID_BALANCED}), \
             mock.patch.object(sistema, "obter_plano_energia_atual", return_value=GUID_BALANCED), \
             mock.patch.object(sistema, "executar_comando_seguro", return_value=True), \
             mock.patch.object(sistema, "log"):
            sistema.modo_desempenho_maximo()
        self.assertEqual(hashlib.sha256(open(caminho, "rb").read()).hexdigest(), before)

    def test_38_estado_real_nao_muda(self):
        import config
        import hashlib
        caminho = config.ARQUIVO_ESTADO
        before = hashlib.sha256(open(caminho, "rb").read()).hexdigest() if os.path.isfile(caminho) else None
        with mock.patch.object(sistema, "obter_planos_energia_disponiveis", return_value={GUID_BALANCED}), \
             mock.patch.object(sistema, "obter_plano_energia_atual", return_value=GUID_BALANCED), \
             mock.patch.object(sistema, "executar_comando_seguro", return_value=True), \
             mock.patch.object(sistema, "log"):
            sistema.modo_desempenho_maximo()
        after = hashlib.sha256(open(caminho, "rb").read()).hexdigest() if os.path.isfile(caminho) else None
        self.assertEqual(before, after)

    def test_39_clientes_reais_nao_mudam(self):
        # A etapa de plano não toca clientes AIKA (não referencia pasta do jogo).
        import inspect
        src = inspect.getsource(sistema.modo_desempenho_maximo)
        self.assertNotIn("PASTA_JOGO", src)
        self.assertNotIn("aikaonline", src.lower())
        self.assertNotIn("cbmgames", src.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)



