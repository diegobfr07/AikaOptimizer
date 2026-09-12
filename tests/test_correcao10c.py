# -*- coding: utf-8 -*-
"""Correção 10C — prioridade real e coerência entre Game Booster e Watchdog."""
import hashlib
import inspect
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import game_booster as gb  # noqa: E402
import main  # noqa: E402


HASHES_CONGELADOS = {
    "automod.py": "F9422E65FA542D6D5A28CE2E3DD6D025544669601EA2522F42415BDA09E69609",
    "set_injector.py": "D2765BBD157138F6A6AD4DB5997AAF69A212118349CD88257B5BFB2727E00919",
    "textura.py": "A890FDA024E47C57817F25E5845CE239F5C7F83CF571F1A674F9AD8F426CB8DE",
    "extractor_sets.py": "D3F01604DB2DF2A74FF6D9317FD177A8A3DA42CD92F6769D7B8DF34B21BCD58F",
}
PERFORMANCE_HASH = "73228644700C4A4B2E5DC554E59E86623C34BBB47CEEADEFC11F54C83031A292"
SISTEMA_HASH = "FD66D4CEF6B942CB7C735856EA00E816F03911DEDF46F109EF6F86C87100DE4B"
KILL_POLICY_HASH = "42BD8487A3963C94AF395C7C6BAC5C2A5032912FC8BDA9C3A9B2E6E688432662"
SERVICES_HASH = "22449D79DD456F32F4E037A968667448C3F8B06FE5FE8240256271BCD0874520"


class FakeProc:
    def __init__(self, pid=10, name="aikabr.exe", priority=None,
                 read_error=None, write_error=None, confirmed=None):
        self.pid = pid
        self.info = {"pid": pid, "name": name, "create_time": float(pid)}
        self.priority = (gb.psutil.NORMAL_PRIORITY_CLASS
                         if priority is None else priority)
        self.read_error = read_error
        self.write_error = write_error
        self.confirmed = confirmed
        self.set_calls = []
        self.read_calls = 0

    def exe(self):
        return rf"C:\CBMgames\AikaOnlineBrasil\{self.info['name']}"

    def name(self):
        return self.info["name"]

    def nice(self, *args):
        if not args:
            self.read_calls += 1
            if self.read_error:
                raise self.read_error
            return self.priority
        self.set_calls.append(args[0])
        if self.write_error:
            raise self.write_error
        self.priority = args[0] if self.confirmed is None else self.confirmed


def prioridade_report(processos, incluir_detalhes=False):
    with patch.object(gb.psutil, "process_iter", return_value=processos), \
         patch.object(gb.psutil, "pid_exists", return_value=True):
        return gb.aplicar_high_priority_aika_detalhado(incluir_detalhes)


def metricas(cpu, ram):
    return {
        "cpu_percent": cpu, "ram_percent": ram,
        "ram_total_gb": 16.0, "ram_usada_gb": 8.0,
        "ram_disponivel_gb": 8.0, "total_procs": 100,
        "telemetry_errors": [],
    }


def resultado_ui(relatorio):
    return {
        "status": "completed",
        "metricas_antes": metricas(10.0, 40.0),
        "metricas_depois": metricas(9.0, 39.0),
        "processos_encerrados": 0,
        "mem_associada_mb": 0,
        "servicos_parados": 0,
        "aika_priority_applied": relatorio.get("changed", 0),
        "aika_priority_report": relatorio,
    }


def watchdog(processos_por_ciclo):
    worker = main.AikaWatchdogThread.__new__(main.AikaWatchdogThread)
    worker._running = True
    worker._sessao_ativa = False
    worker.current_pids = {}
    worker._prioridades_observadas = {}
    worker._ultimo_status_emitido = None
    worker._ciclos_sem_jogo = 0
    worker.status_signal = Mock()
    worker.session_started_signal = Mock()
    worker.session_ended_signal = Mock()
    mapas = [{proc.pid: proc for proc in ciclo} for ciclo in processos_por_ciclo]
    indices = iter(range(len(mapas)))

    def listar():
        indice = next(indices)
        worker._mapa_ciclo = mapas[indice]
        return {
            pid: proc.info.get("create_time")
            for pid, proc in worker._mapa_ciclo.items()
        }

    worker._listar_pids_jogo = listar
    with patch("psutil.Process", side_effect=lambda pid: worker._mapa_ciclo[pid]), \
         patch.object(gb.psutil, "pid_exists", return_value=True):
        for _ in mapas:
            worker._processar_ciclo()
    return worker


class TestPrioridadeVerificada(unittest.TestCase):
    def test_01_processo_realmente_high(self):
        proc = FakeProc(priority=gb.psutil.HIGH_PRIORITY_CLASS)
        resultado = prioridade_report([proc])
        self.assertEqual(resultado, {
            "detected": 1, "already_high": 1, "changed": 0,
            "failed": 0, "disappeared": 0,
        })
        self.assertEqual(proc.set_calls, [])

    def test_02_normal_alterado_com_sucesso(self):
        proc = FakeProc(priority=gb.psutil.NORMAL_PRIORITY_CLASS)
        resultado = prioridade_report([proc])
        self.assertEqual(resultado["detected"], 1)
        self.assertEqual(resultado["already_high"], 0)
        self.assertEqual(resultado["changed"], 1)
        self.assertEqual(resultado["failed"], 0)

    def test_03_releitura_confirma_high_apos_setter(self):
        proc = FakeProc(priority=gb.psutil.NORMAL_PRIORITY_CLASS)
        detalhe = gb.avaliar_prioridade_processo_aika(proc, aplicar=True)
        self.assertEqual(proc.set_calls, [gb.psutil.HIGH_PRIORITY_CLASS])
        self.assertGreaterEqual(proc.read_calls, 2)
        self.assertEqual(detalhe["after"], gb.psutil.HIGH_PRIORITY_CLASS)
        self.assertEqual(detalhe["result"], "changed")

    def test_04_setter_sem_confirmacao_nao_e_sucesso(self):
        proc = FakeProc(priority=gb.psutil.NORMAL_PRIORITY_CLASS,
                        confirmed=gb.psutil.NORMAL_PRIORITY_CLASS)
        detalhe = gb.avaliar_prioridade_processo_aika(proc, aplicar=True)
        self.assertEqual(detalhe["result"], "failed")
        self.assertEqual(detalhe["error_type"], "PriorityVerificationError")
        self.assertEqual(detalhe["operation"], "VERIFY_HIGH_PRIORITY")
        self.assertEqual(prioridade_report([FakeProc(
            priority=gb.psutil.NORMAL_PRIORITY_CLASS,
            confirmed=gb.psutil.NORMAL_PRIORITY_CLASS,
        )])["changed"], 0)

    def test_05_access_denied_ao_ler_e_honesto(self):
        proc = FakeProc(read_error=gb.psutil.AccessDenied(10))
        resultado = prioridade_report([proc], incluir_detalhes=True)
        self.assertEqual((resultado["detected"], resultado["failed"]), (1, 1))
        self.assertEqual(resultado["details"][0]["error_type"], "AccessDenied")
        self.assertEqual(resultado["details"][0]["operation"], "READ_PRIORITY")
        self.assertIsNone(resultado["details"][0]["before"])

    def test_06_access_denied_ao_alterar_e_honesto(self):
        proc = FakeProc(priority=gb.psutil.ABOVE_NORMAL_PRIORITY_CLASS,
                        write_error=gb.psutil.AccessDenied(10))
        resultado = prioridade_report([proc], incluir_detalhes=True)
        detalhe = resultado["details"][0]
        self.assertEqual((resultado["changed"], resultado["failed"]), (0, 1))
        self.assertEqual(detalhe["before_name"], "ABOVE_NORMAL")
        self.assertEqual(detalhe["error_type"], "AccessDenied")
        self.assertEqual(detalhe["operation"], "SET_HIGH_PRIORITY")

    def test_07_no_such_process_e_desaparecido(self):
        proc = FakeProc(read_error=gb.psutil.NoSuchProcess(10))
        resultado = prioridade_report([proc], incluir_detalhes=True)
        self.assertEqual(resultado["disappeared"], 1)
        self.assertEqual(resultado["failed"], 0)
        self.assertEqual(resultado["details"][0]["result"], "disappeared")

    def test_08_pid_troca_ou_desaparece_sem_crash(self):
        antigo = FakeProc(pid=10, priority=gb.psutil.HIGH_PRIORITY_CLASS)
        novo = FakeProc(pid=11, priority=gb.psutil.NORMAL_PRIORITY_CLASS)
        worker = watchdog([[antigo], [novo]])
        self.assertNotIn(10, worker.current_pids)
        self.assertIn(11, worker.current_pids)
        self.assertEqual(worker._prioridades_observadas[11], "HIGH")

    def test_09_dois_processos_um_high_um_alterado(self):
        processos = [
            FakeProc(pid=1, priority=gb.psutil.HIGH_PRIORITY_CLASS),
            FakeProc(pid=2, priority=gb.psutil.NORMAL_PRIORITY_CLASS),
        ]
        resultado = prioridade_report(processos)
        self.assertEqual(resultado, {
            "detected": 2, "already_high": 1, "changed": 1,
            "failed": 0, "disappeared": 0,
        })

    def test_10_dois_processos_um_high_um_access_denied(self):
        processos = [
            FakeProc(pid=1, priority=gb.psutil.HIGH_PRIORITY_CLASS),
            FakeProc(pid=2, priority=gb.psutil.ABOVE_NORMAL_PRIORITY_CLASS,
                     write_error=gb.psutil.AccessDenied(2)),
        ]
        resultado = prioridade_report(processos)
        self.assertEqual(resultado, {
            "detected": 2, "already_high": 1, "changed": 0,
            "failed": 1, "disappeared": 0,
        })


class TestWatchdogReal(unittest.TestCase):
    def test_11_watchdog_high_real_exibe_high(self):
        proc = FakeProc(priority=gb.psutil.HIGH_PRIORITY_CLASS)
        worker = watchdog([[proc]])
        worker.status_signal.emit.assert_called_once_with(
            True, proc.pid, "ATIVO / HIGH",
        )

    def test_12_watchdog_normal_nao_pode_exibir_high(self):
        proc = FakeProc(priority=gb.psutil.NORMAL_PRIORITY_CLASS,
                        write_error=gb.psutil.AccessDenied(10))
        worker = watchdog([[proc]])
        texto = worker.status_signal.emit.call_args.args[2]
        self.assertEqual(texto, "ATIVO / NORMAL")
        self.assertNotIn("HIGH", texto)

    def test_13_watchdog_sem_processo_fica_offline(self):
        worker = watchdog([[], []])
        worker.status_signal.emit.assert_called_once_with(False, 0, "OFFLINE")

    def test_14_backend_e_watchdog_interpretam_high_igual(self):
        for valor, esperado in (
            (gb.psutil.HIGH_PRIORITY_CLASS, True),
            (gb.psutil.NORMAL_PRIORITY_CLASS, False),
            (gb.psutil.ABOVE_NORMAL_PRIORITY_CLASS, False),
        ):
            detalhe = gb.avaliar_prioridade_processo_aika(
                FakeProc(priority=valor), aplicar=False,
            )
            estado = main.AikaWatchdogThread._estado_prioridade_observado(detalhe)
            self.assertEqual(gb.prioridade_e_high(valor), esperado)
            self.assertEqual(estado == "HIGH", esperado)

    def test_15_constante_high_windows_e_comparada_corretamente(self):
        class InteiroWindows:
            def __int__(self):
                return int(gb.psutil.HIGH_PRIORITY_CLASS)
        self.assertTrue(gb.prioridade_e_high(InteiroWindows()))
        self.assertFalse(gb.prioridade_e_high(gb.psutil.NORMAL_PRIORITY_CLASS))

    def test_24_multiplos_processos_mantem_contagem(self):
        processos = [
            FakeProc(pid=21, priority=gb.psutil.HIGH_PRIORITY_CLASS),
            FakeProc(pid=22, priority=gb.psutil.HIGH_PRIORITY_CLASS),
        ]
        worker = watchdog([processos])
        worker.status_signal.emit.assert_called_once_with(
            True, 21, "ATIVO / HIGH (2)",
        )


class TestLogsERegressoes(unittest.TestCase):
    def detalhe_access_denied(self):
        proc = FakeProc(pid=1234, priority=gb.psutil.ABOVE_NORMAL_PRIORITY_CLASS,
                        write_error=gb.psutil.AccessDenied(1234))
        return prioridade_report([proc], incluir_detalhes=True)

    def test_16_log_inclui_motivo_concreto(self):
        linhas = main._linhas_relatorio_game_booster(
            resultado_ui(self.detalhe_access_denied())
        )
        texto = "\n".join(linhas)
        self.assertIn("PID 1234", texto)
        self.assertIn("prioridade antes: ABOVE_NORMAL", texto)
        self.assertIn("erro: AccessDenied", texto)
        self.assertIn("tentativa: HIGH_PRIORITY", texto)

    def test_17_log_ui_nao_expoe_traceback(self):
        relatorio = self.detalhe_access_denied()
        relatorio["details"][0]["error_message"] = (
            "Traceback (most recent call last):\n" + "x" * 500
        )
        texto = "\n".join(main._linhas_relatorio_game_booster(
            resultado_ui(relatorio)
        ))
        self.assertNotIn("Traceback", texto)
        linha = texto.splitlines()[-1]
        self.assertLess(len(linha), 450)

    def test_18_realtime_priority_nunca_e_usado(self):
        fontes = "\n".join((
            inspect.getsource(gb.avaliar_prioridade_processo_aika),
            inspect.getsource(gb.aplicar_high_priority_aika_detalhado),
            inspect.getsource(main.AikaWatchdogThread),
        ))
        self.assertNotIn("REALTIME_PRIORITY_CLASS", fontes)
        self.assertIn("HIGH_PRIORITY_CLASS", fontes)

    def test_19_telemetria_10b_primeira_segunda_terceira(self):
        anterior = gb.BOOSTER_ATIVO
        gb.BOOSTER_ATIVO = True
        leituras = [
            metricas(10, 40), metricas(9, 39),
            metricas(20, 50), metricas(19, 49),
            metricas(30, 60), metricas(29, 59),
        ]
        prioridade = {
            "detected": 0, "already_high": 0, "changed": 0,
            "failed": 0, "disappeared": 0,
        }
        try:
            with patch.object(gb, "coletar_metricas", side_effect=leituras), \
                 patch.object(gb, "aplicar_high_priority_aika_detalhado",
                              return_value=prioridade), \
                 patch.object(gb.time, "sleep"):
                resultados = [gb.game_session_optimizer(False) for _ in range(3)]
        finally:
            gb.BOOSTER_ATIVO = anterior
        self.assertEqual([
            item["metricas_antes"]["cpu_percent"] for item in resultados
        ], [10, 20, 30])
        self.assertEqual(len({id(item) for item in resultados}), 3)

    def test_20_kill_policy_intacta(self):
        politica = {
            "PROCESSOS_OPTIONAL_BG": sorted(gb.PROCESSOS_OPTIONAL_BG),
            "PROCESSOS_KNOWN_UNWANTED": sorted(gb.PROCESSOS_KNOWN_UNWANTED),
            "PROCESSOS_MATAR": sorted(gb.PROCESSOS_MATAR),
            "PROCESSOS_REDUZIR_PRIORIDADE": sorted(gb.PROCESSOS_REDUZIR_PRIORIDADE),
            "SERVICOS_SAFE_STOP": list(gb.SERVICOS_SAFE_STOP),
        }
        atual = hashlib.sha256(json.dumps(
            politica, sort_keys=True, ensure_ascii=False,
        ).encode()).hexdigest().upper()
        self.assertEqual(atual, KILL_POLICY_HASH)

    def test_21_afinidade_intacta(self):
        atual = hashlib.sha256((RAIZ / "performance.py").read_bytes()).hexdigest().upper()
        self.assertEqual(atual, PERFORMANCE_HASH)

    def test_22_qos_intacto(self):
        atual = hashlib.sha256((RAIZ / "sistema.py").read_bytes()).hexdigest().upper()
        self.assertEqual(atual, SISTEMA_HASH)

    def test_23_servicos_intactos(self):
        atual = hashlib.sha256(json.dumps(
            list(gb.SERVICOS_SAFE_STOP), ensure_ascii=False,
        ).encode()).hexdigest().upper()
        self.assertEqual(atual, SERVICES_HASH)

    def test_25_motores_congelados_intactos(self):
        for nome, esperado in HASHES_CONGELADOS.items():
            atual = hashlib.sha256((RAIZ / nome).read_bytes()).hexdigest().upper()
            self.assertEqual(atual, esperado, nome)


if __name__ == "__main__":
    unittest.main(verbosity=2)