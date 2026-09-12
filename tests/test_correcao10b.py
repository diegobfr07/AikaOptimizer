# -*- coding: utf-8 -*-
"""Correção 10B — telemetria reentrante e relatório honesto do AIKA."""
import hashlib
import json
import math
import os
import sys
import types
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


def metricas(cpu, ram):
    return {
        "cpu_percent": cpu,
        "ram_total_gb": 16.0 if ram is not None else None,
        "ram_usada_gb": 8.0 if ram is not None else None,
        "ram_disponivel_gb": 8.0 if ram is not None else None,
        "ram_percent": ram,
        "total_procs": 100,
        "telemetry_errors": [],
    }


def relatorio_prioridade(detected=0, already_high=0, changed=0,
                         failed=0, disappeared=0):
    return {
        "detected": detected,
        "already_high": already_high,
        "changed": changed,
        "failed": failed,
        "disappeared": disappeared,
    }


def resultado_ui(antes, depois, prioridade=None, servicos=0):
    return {
        "status": "completed",
        "metricas_antes": antes,
        "metricas_depois": depois,
        "processos_encerrados": 0,
        "mem_associada_mb": 0,
        "aika_priority_applied": (prioridade or {}).get("changed", 0),
        "aika_priority_report": prioridade or relatorio_prioridade(),
        "servicos_parados": servicos,
    }


class FakeProc:
    def __init__(self, pid, prioridade, erro_leitura=None, erro_escrita=None):
        self.pid = pid
        self.info = {"pid": pid, "name": "aika.exe"}
        self.prioridade = prioridade
        self.erro_leitura = erro_leitura
        self.erro_escrita = erro_escrita
        self.prioridades_definidas = []

    def exe(self):
        return r"C:\CBMgames\AikaOnlineBrasil\Aika.exe"

    def nice(self, *args):
        if not args:
            if self.erro_leitura:
                raise self.erro_leitura
            return self.prioridade
        if self.erro_escrita:
            raise self.erro_escrita
        self.prioridade = args[0]
        self.prioridades_definidas.append(args[0])


class TestTelemetriaReentrante(unittest.TestCase):
    def setUp(self):
        self.booster_antes = gb.BOOSTER_ATIVO
        gb.BOOSTER_ATIVO = False

    def tearDown(self):
        gb.BOOSTER_ATIVO = self.booster_antes

    def executar_tres_vezes(self):
        leituras = [
            metricas(11.1, 41.1), metricas(10.1, 40.1),
            metricas(21.2, 51.2), metricas(20.2, 50.2),
            metricas(31.3, 61.3), metricas(30.3, 60.3),
        ]
        prioridade = relatorio_prioridade(2, 2, 0, 0, 0)
        with patch.object(gb, "coletar_metricas", side_effect=leituras) as coletar, \
             patch.object(gb, "aplicar_high_priority_aika_detalhado",
                          return_value=prioridade), \
             patch.object(gb, "obter_pid_janela_focada", return_value=None), \
             patch.object(gb, "is_modo_agressivo", return_value=False), \
             patch.object(gb.psutil, "process_iter", return_value=[]), \
             patch.object(gb, "otimizar_ram_processos", return_value=0), \
             patch.object(gb.time, "sleep"):
            resultados = [gb.game_session_optimizer(False) for _ in range(3)]
        self.assertEqual(coletar.call_count, 6)
        return resultados

    def test_01_primeira_execucao_retorna_cpu_ram_validos(self):
        primeira = self.executar_tres_vezes()[0]
        self.assertEqual(primeira["status"], "completed")
        self.assertEqual(primeira["metricas_antes"]["cpu_percent"], 11.1)
        self.assertEqual(primeira["metricas_depois"]["ram_percent"], 40.1)

    def test_02_segunda_execucao_mesma_sessao_tem_metricas_validas(self):
        segunda = self.executar_tres_vezes()[1]
        self.assertEqual(segunda["status"], "already_active")
        self.assertEqual(segunda["metricas_antes"]["cpu_percent"], 21.2)
        self.assertEqual(segunda["metricas_depois"]["ram_percent"], 50.2)

    def test_03_terceira_execucao_continua_independente(self):
        resultados = self.executar_tres_vezes()
        terceira = resultados[2]
        self.assertEqual(terceira["metricas_antes"]["cpu_percent"], 31.3)
        self.assertEqual(terceira["metricas_depois"]["cpu_percent"], 30.3)
        self.assertEqual(len({id(item) for item in resultados}), 3)

    def test_04_metricas_anteriores_nao_sao_reutilizadas(self):
        resultados = self.executar_tres_vezes()
        pares = [
            (item["metricas_antes"]["cpu_percent"],
             item["metricas_depois"]["cpu_percent"])
            for item in resultados
        ]
        self.assertEqual(pares, [(11.1, 10.1), (21.2, 20.2), (31.3, 30.3)])
        self.assertEqual(len({id(item["metricas_antes"]) for item in resultados}), 3)

    def test_05_resultado_da_segunda_execucao_nao_e_none(self):
        segunda = self.executar_tres_vezes()[1]
        self.assertIsInstance(segunda, dict)
        self.assertTrue(segunda["metricas_antes"])
        self.assertTrue(segunda["metricas_depois"])

    def test_06_falha_real_cpu_e_indisponivel_com_aviso(self):
        memoria = types.SimpleNamespace(
            total=16 * 1024**3, used=8 * 1024**3,
            available=8 * 1024**3, percent=50.0,
        )
        with patch.object(gb.psutil, "cpu_percent", side_effect=OSError("CPU")), \
             patch.object(gb.psutil, "virtual_memory", return_value=memoria), \
             patch.object(gb.psutil, "process_iter", return_value=[]), \
             patch.object(gb, "log") as log:
            dados = gb.coletar_metricas()
        self.assertIsNone(dados["cpu_percent"])
        self.assertEqual(dados["ram_percent"], 50.0)
        self.assertIn("CPU", dados["telemetry_errors"])
        self.assertTrue(any("AVISO" in str(call) and "CPU indisponível" in str(call)
                            for call in log.call_args_list))

    def test_07_falha_real_ram_tem_tratamento_equivalente(self):
        with patch.object(gb.psutil, "cpu_percent", return_value=12.5), \
             patch.object(gb.psutil, "virtual_memory", side_effect=OSError("RAM")), \
             patch.object(gb.psutil, "process_iter", return_value=[]), \
             patch.object(gb, "log") as log:
            dados = gb.coletar_metricas()
        self.assertEqual(dados["cpu_percent"], 12.5)
        self.assertIsNone(dados["ram_percent"])
        self.assertIn("RAM", dados["telemetry_errors"])
        self.assertTrue(any("AVISO" in str(call) and "RAM indisponível" in str(call)
                            for call in log.call_args_list))

    def test_08_boost_sucesso_com_telemetria_falha_mantem_motor_ok(self):
        falha = metricas(None, None)
        prioridade = relatorio_prioridade()
        with patch.object(gb, "coletar_metricas", side_effect=[falha, dict(falha)]), \
             patch.object(gb, "aplicar_high_priority_aika_detalhado",
                          return_value=prioridade), \
             patch.object(gb, "obter_pid_janela_focada", return_value=None), \
             patch.object(gb, "is_modo_agressivo", return_value=False), \
             patch.object(gb.psutil, "process_iter", return_value=[]), \
             patch.object(gb, "otimizar_ram_processos", return_value=0), \
             patch.object(gb.time, "sleep"):
            resultado = gb.game_session_optimizer(False)
        linhas = main._linhas_relatorio_game_booster(resultado)
        self.assertEqual(resultado["status"], "completed")
        self.assertTrue(linhas[0].startswith("[OK] GAME BOOST ATIVO"))
        self.assertTrue(any(linha.startswith("[AVISO]") for linha in linhas))
        self.assertNotIn("None%", " ".join(linhas))
        self.assertNotIn("?%", " ".join(linhas))


class TestRelatorioPrioridade(unittest.TestCase):
    def relatar(self, processos):
        with patch.object(gb.psutil, "process_iter", return_value=processos):
            return gb.aplicar_high_priority_aika_detalhado()

    def test_09_dois_aikas_ja_high_sao_detectados(self):
        high = gb.psutil.HIGH_PRIORITY_CLASS
        relatorio = self.relatar([FakeProc(1, high), FakeProc(2, high)])
        self.assertEqual(relatorio, relatorio_prioridade(2, 2, 0, 0, 0))

    def test_10_log_dois_high_nao_usa_texto_ambiguo_antigo(self):
        resultado = resultado_ui(
            metricas(10, 40), metricas(9, 39),
            relatorio_prioridade(2, 2, 0, 0, 0),
        )
        texto = "\n".join(main._linhas_relatorio_game_booster(resultado))
        self.assertIn("2 processos detectados", texto)
        self.assertIn("2 já em HIGH_PRIORITY", texto)
        self.assertIn("0 prioridades alteradas", texto)
        self.assertNotIn("Aika HIGH_PRIORITY: 0 processos", texto)

    def test_11_um_high_um_normal_contabiliza_uma_alteracao(self):
        high = gb.psutil.HIGH_PRIORITY_CLASS
        normal = gb.psutil.NORMAL_PRIORITY_CLASS
        segundo = FakeProc(2, normal)
        relatorio = self.relatar([FakeProc(1, high), segundo])
        self.assertEqual(relatorio, relatorio_prioridade(2, 1, 1, 0, 0))
        self.assertEqual(segundo.prioridades_definidas, [high])

    def test_12_nenhum_aika_nao_crasha_e_e_info(self):
        relatorio = self.relatar([])
        linhas = main._linhas_relatorio_game_booster(resultado_ui(
            metricas(10, 40), metricas(9, 39), relatorio,
        ))
        self.assertEqual(relatorio["detected"], 0)
        self.assertTrue(any(linha.startswith("[INFO] AIKA: 0 processos detectados")
                            for linha in linhas))

    def test_13_processo_desaparece_durante_analise(self):
        processo = FakeProc(
            7, gb.psutil.NORMAL_PRIORITY_CLASS,
            erro_leitura=gb.psutil.NoSuchProcess(7),
        )
        relatorio = self.relatar([processo])
        self.assertEqual(relatorio["detected"], 1)
        self.assertEqual(relatorio["disappeared"], 1)
        self.assertEqual(relatorio["changed"], 0)

    def test_14_access_denied_e_contabilizado_honestamente(self):
        processo = FakeProc(
            8, gb.psutil.NORMAL_PRIORITY_CLASS,
            erro_escrita=gb.psutil.AccessDenied(8),
        )
        relatorio = self.relatar([processo])
        self.assertEqual(relatorio["detected"], 1)
        self.assertEqual(relatorio["failed"], 1)
        self.assertEqual(relatorio["changed"], 0)

    def test_15_servicos_parados_continuam_no_relatorio(self):
        linhas = main._linhas_relatorio_game_booster(resultado_ui(
            metricas(10, 40), metricas(9, 39),
            relatorio_prioridade(1, 1, 0, 0, 0), servicos=3,
        ))
        self.assertIn("Serviços: 3 parados", "\n".join(linhas))


class TestPreservacaoEIntegracao(unittest.TestCase):
    def test_16_politica_de_kill_permanece_inalterada(self):
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

    def test_17_afinidade_permanece_byte_a_byte(self):
        atual = hashlib.sha256((RAIZ / "performance.py").read_bytes()).hexdigest().upper()
        self.assertEqual(atual, PERFORMANCE_HASH)

    def test_18_qos_permanece_byte_a_byte(self):
        atual = hashlib.sha256((RAIZ / "sistema.py").read_bytes()).hexdigest().upper()
        self.assertEqual(atual, SISTEMA_HASH)

    def test_19_painel_aika_continua_recebendo_status_do_watchdog(self):
        win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
        win.booster_panel = Mock()
        win._on_watchdog_status(True, 101, "ATIVO / HIGH (2)")
        win.booster_panel.atualizar_status_aika.assert_called_once_with(
            True, 101, prioridade="ATIVO / HIGH (2)",
        )

    def test_20_motores_congelados_permanecem_byte_a_byte(self):
        for nome, esperado in HASHES_CONGELADOS.items():
            atual = hashlib.sha256((RAIZ / nome).read_bytes()).hexdigest().upper()
            self.assertEqual(atual, esperado, nome)

    def test_21_dois_cliques_seguidos_sem_reiniciar_tem_metricas(self):
        class Sinal:
            def __init__(self):
                self.valores = []
            def emit(self, *args):
                self.valores.append(args)

        class Sinais:
            def __init__(self):
                self.log_signal = Sinal()
                self.metrics_signal = Sinal()
                self.booster_visible_signal = Sinal()

        class Transacao:
            def executar(self, *_args, **_kwargs):
                return True
            def rollback_total(self):
                return None

        win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
        win.sinais = Sinais()
        win.booster_panel = Mock()
        win._suprimir_auto_boost_ate = 0
        tarefas = []
        win.executar_em_background = lambda tarefa, **_kwargs: tarefas.append(tarefa) or True
        respostas = [
            resultado_ui(metricas(10.1, 40.1), metricas(9.1, 39.1)),
            {**resultado_ui(metricas(20.2, 50.2), metricas(19.2, 49.2)),
             "status": "already_active"},
        ]
        memoria = types.SimpleNamespace(
            total=16 * 1024**3, used=8 * 1024**3,
            available=8 * 1024**3, percent=50.0,
        )
        with patch.object(main.opt, "jogo_esta_aberto", return_value=True), \
             patch.object(main.opt, "TransacaoSistema", return_value=Transacao()), \
             patch.object(main.opt, "game_session_optimizer", side_effect=respostas), \
             patch("psutil.cpu_percent", return_value=15.0), \
             patch("psutil.virtual_memory", return_value=memoria), \
             patch("psutil.process_iter", return_value=[]):
            win.iniciar_boost_seguro()
            tarefas.pop(0)()
            win.iniciar_boost_seguro()
            tarefas.pop(0)()

        texto = "\n".join(args[0] for args in win.sinais.log_signal.valores)
        self.assertIn("CPU antes: 10.1%", texto)
        self.assertIn("CPU antes: 20.2%", texto)
        self.assertNotIn("?%", texto)
        self.assertNotIn("None", texto)
        self.assertFalse(any(math.isnan(valor) for valor in (10.1, 20.2)))


if __name__ == "__main__":
    unittest.main(verbosity=2)