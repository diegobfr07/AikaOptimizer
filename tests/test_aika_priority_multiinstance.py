# -*- coding: utf-8 -*-
"""Correção cirúrgica — idempotência de prioridade Aika + múltiplas instâncias.

Valida:
- nunca rebaixar prioridade de Aika ativo (HIGH preservado em reexecução);
- tratamento por PID (1, 2 e 3 processos simultâneos), com isolamento de
  falhas (AccessDenied em um PID não bloqueia os demais);
- watchdog garante/recupera HIGH por PID em todo ciclo;
- card/status agregado não reporta HIGH quando as prioridades são mistas.
Usa apenas processos falsos (nunca toca processos reais/clientes).
"""
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

import psutil

import config  # noqa: E402
import main as main_module  # noqa: E402
import sistema  # noqa: E402

AIKA = "aika.exe"


class FakeProc:
    """Processo falso com leitura/escrita de prioridade controlada."""

    def __init__(self, pid, inicial=psutil.NORMAL_PRIORITY_CLASS):
        self.pid = pid
        self._nice = inicial
        self.deny_set = False
        self.deny_read = False
        self.set_attempts = []
        self.ionice_calls = 0

    def name(self):
        return AIKA

    def nice(self, valor=None):
        if valor is None:
            if self.deny_read:
                raise psutil.AccessDenied(self.pid, "leitura negada (fake)")
            return self._nice
        self.set_attempts.append(valor)
        if self.deny_set:
            raise psutil.AccessDenied(self.pid, "escrita negada (fake)")
        self._nice = valor
        return self._nice

    def ionice(self, valor=None):
        if valor is not None:
            self.ionice_calls += 1
        return 0

    def create_time(self):
        return 1000 + self.pid


def _criar_watchdog(pids_e_estados):
    """Watchdog com psutil.Process fake (nunca executa run/start)."""
    w = main_module.AikaWatchdogThread(parent=None)
    procs = {}
    infos = []
    for pid, estado in pids_e_estados.items():
        procs[pid] = FakeProc(pid, inicial=estado)
        infos.append(SimpleNamespace(
            name=AIKA, pid=pid,
            info={"name": AIKA, "pid": pid, "create_time": 1000 + pid},
        ))
    lista = mock.patch.object(w, "_listar_pids_jogo",
                              return_value={p.pid: p.create_time()
                                            for p in procs.values()})
    proc_iter = mock.patch.object(
        psutil, "process_iter",
        return_value=[SimpleNamespace(info={"name": AIKA, "pid": pid})
                      for pid in pids_e_estados])
    proc_cls = mock.patch.object(psutil, "Process",
                                 side_effect=lambda pid: procs[pid])
    return w, procs, [lista, proc_iter, proc_cls]


class TestPrioridadeTotalSemRebaixar(unittest.TestCase):
    """sistema.prioridade_total nunca rebaixa; eleva até ABOVE por PID."""

    def _cena(self, estados):
        procs = {pid: FakeProc(pid, inicial=estado)
                 for pid, estado in estados.items()}
        patches = [
            mock.patch.object(sistema, "fazer_backup_registro",
                              return_value=True),
            mock.patch.object(sistema, "garantir_ifeo_ownership",
                              return_value=True),
            mock.patch.object(sistema, "executar_comando_seguro",
                              return_value=True),
            mock.patch.object(sistema, "log", return_value=None),
            mock.patch.object(psutil, "process_iter", return_value=[
                SimpleNamespace(info={"name": AIKA, "pid": pid})
                for pid in estados]),
            mock.patch.object(psutil, "Process",
                              side_effect=lambda pid: procs[pid]),
        ]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        return procs

    def test_01_high_nao_e_rebaixado(self):
        procs = self._cena({1: psutil.HIGH_PRIORITY_CLASS})
        self.assertTrue(sistema.prioridade_total())
        self.assertEqual(procs[1]._nice, psutil.HIGH_PRIORITY_CLASS)
        self.assertEqual(procs[1].set_attempts, [],
                         "nenhuma escrita pode ocorrer sobre HIGH")

    def test_02_high_segunda_execucao_continua_high(self):
        procs = self._cena({1: psutil.HIGH_PRIORITY_CLASS})
        sistema.prioridade_total()
        sistema.prioridade_total()
        self.assertEqual(procs[1]._nice, psutil.HIGH_PRIORITY_CLASS)
        self.assertEqual(procs[1].set_attempts, [])

    def test_03_above_normal_preservado(self):
        procs = self._cena({1: psutil.ABOVE_NORMAL_PRIORITY_CLASS})
        sistema.prioridade_total()
        self.assertEqual(procs[1]._nice, psutil.ABOVE_NORMAL_PRIORITY_CLASS)
        self.assertEqual(procs[1].set_attempts, [])

    def test_04_normal_sobe_para_above(self):
        procs = self._cena({1: psutil.NORMAL_PRIORITY_CLASS})
        sistema.prioridade_total()
        self.assertEqual(procs[1]._nice, psutil.ABOVE_NORMAL_PRIORITY_CLASS)

    def test_05_pids_independentes(self):
        procs = self._cena({
            1: psutil.HIGH_PRIORITY_CLASS,
            2: psutil.NORMAL_PRIORITY_CLASS,
            3: psutil.ABOVE_NORMAL_PRIORITY_CLASS,
        })
        sistema.prioridade_total()
        self.assertEqual(procs[1]._nice, psutil.HIGH_PRIORITY_CLASS)
        self.assertEqual(procs[2]._nice, psutil.ABOVE_NORMAL_PRIORITY_CLASS)
        self.assertEqual(procs[3]._nice, psutil.ABOVE_NORMAL_PRIORITY_CLASS)

    def test_06_leitura_negada_nao_rebaixa(self):
        procs = self._cena({1: psutil.HIGH_PRIORITY_CLASS})
        procs[1].deny_read = True
        sistema.prioridade_total()
        self.assertEqual(procs[1].set_attempts, [],
                         "sem leitura não se pode arriscar rebaixar")


class TestWatchdogMultiInstancia(unittest.TestCase):
    """Watchdog garante HIGH por PID em todos os ciclos; agrega status."""

    def _ciclar(self, w, n=1):
        for _ in range(n):
            w._processar_ciclo()

    def test_07_um_above_vira_high(self):
        w, procs, ps = _criar_watchdog({10: psutil.ABOVE_NORMAL_PRIORITY_CLASS})
        for p in ps:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in ps])
        self._ciclar(w)
        self.assertEqual(procs[10]._nice, psutil.HIGH_PRIORITY_CLASS)

    def test_08_high_segunda_otimizacao_continua_high(self):
        w, procs, ps = _criar_watchdog({10: psutil.ABOVE_NORMAL_PRIORITY_CLASS})
        for p in ps:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in ps])
        self._ciclar(w, 2)
        self.assertEqual(procs[10]._nice, psutil.HIGH_PRIORITY_CLASS)

    def test_09_high_com_acesso_negado_nao_cai(self):
        w, procs, ps = _criar_watchdog({10: psutil.HIGH_PRIORITY_CLASS})
        for p in ps:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in ps])
        procs[10].deny_set = True
        self._ciclar(w, 2)
        self.assertEqual(procs[10]._nice, psutil.HIGH_PRIORITY_CLASS)

    def test_10_dois_processos_encontrados_e_tratados(self):
        w, procs, ps = _criar_watchdog({
            1: psutil.ABOVE_NORMAL_PRIORITY_CLASS,
            2: psutil.NORMAL_PRIORITY_CLASS,
        })
        for p in ps:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in ps])
        self._ciclar(w)
        self.assertEqual(procs[1]._nice, psutil.HIGH_PRIORITY_CLASS)
        self.assertEqual(procs[2]._nice, psutil.HIGH_PRIORITY_CLASS)

    def test_11_tres_processos_encontrados_e_tratados(self):
        w, procs, ps = _criar_watchdog({
            1: psutil.ABOVE_NORMAL_PRIORITY_CLASS,
            2: psutil.NORMAL_PRIORITY_CLASS,
            3: psutil.ABOVE_NORMAL_PRIORITY_CLASS,
        })
        for p in ps:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in ps])
        self._ciclar(w)
        for pid in (1, 2, 3):
            self.assertEqual(procs[pid]._nice, psutil.HIGH_PRIORITY_CLASS)

    def test_12_accessdenied_em_um_pid_nao_bloqueia_outros(self):
        w, procs, ps = _criar_watchdog({
            100: psutil.HIGH_PRIORITY_CLASS,
            200: psutil.ABOVE_NORMAL_PRIORITY_CLASS,
            300: psutil.NORMAL_PRIORITY_CLASS,
        })
        for p in ps:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in ps])
        procs[200].deny_set = True
        self._ciclar(w)
        self.assertEqual(procs[100]._nice, psutil.HIGH_PRIORITY_CLASS)
        self.assertEqual(procs[200]._nice, psutil.ABOVE_NORMAL_PRIORITY_CLASS,
                         "falha não pode rebaixar nem simular sucesso")
        self.assertEqual(procs[300]._nice, psutil.HIGH_PRIORITY_CLASS,
                         "AccessDenied de um PID não pode impedir os demais")

    def test_13_high_de_um_pid_nunca_e_reduzido_por_outro(self):
        w, procs, ps = _criar_watchdog({
            1: psutil.HIGH_PRIORITY_CLASS,
            2: psutil.ABOVE_NORMAL_PRIORITY_CLASS,
            3: psutil.NORMAL_PRIORITY_CLASS,
        })
        for p in ps:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in ps])
        procs[2].deny_set = True
        procs[3].deny_set = True
        self._ciclar(w, 3)
        self.assertEqual(procs[1]._nice, psutil.HIGH_PRIORITY_CLASS)
        self.assertEqual(procs[1].set_attempts, [],
                         "PID em HIGH nunca é reescrito para baixo")

    def test_14_processo_desaparece_sem_crash(self):
        w, procs, ps = _criar_watchdog({5: psutil.NORMAL_PRIORITY_CLASS})
        for p in ps:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in ps])
        self._ciclar(w)
        w._listar_pids_jogo.return_value = {}  # processo some no ciclo seguinte
        self._ciclar(w)
        self.assertEqual(w.current_pids, {})
        self.assertEqual(w._prioridades_observadas, {})

    def test_15_tres_vezes_idempotente(self):
        w, procs, ps = _criar_watchdog({
            1: psutil.NORMAL_PRIORITY_CLASS,
            2: psutil.ABOVE_NORMAL_PRIORITY_CLASS,
            3: psutil.NORMAL_PRIORITY_CLASS,
        })
        for p in ps:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in ps])
        self._ciclar(w, 3)
        for pid in (1, 2, 3):
            self.assertEqual(procs[pid]._nice, psutil.HIGH_PRIORITY_CLASS)

    def test_16_status_agregado_nao_mente(self):
        w, _, ps = _criar_watchdog({
            1: psutil.HIGH_PRIORITY_CLASS,
            2: psutil.HIGH_PRIORITY_CLASS,
        })
        for p in ps:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in ps])
        w._prioridades_observadas = {1: "HIGH", 2: "ABOVE_NORMAL"}
        texto, estados = w._texto_status_prioridade({1: 1, 2: 2})
        self.assertIn("PRIORIDADE MISTA", texto)
        self.assertEqual(set(estados), {"HIGH", "ABOVE_NORMAL"})
        w._prioridades_observadas[3] = "HIGH"
        texto3, _ = w._texto_status_prioridade({1: 1, 2: 2, 3: 3})
        self.assertNotIn("HIGH", texto, "misto nunca afirma HIGH")
        self.assertIn("(2)", texto)
        self.assertIn("(3)", texto3)


if __name__ == "__main__":
    unittest.main()


