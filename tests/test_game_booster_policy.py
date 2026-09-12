# -*- coding: utf-8 -*-
"""Hardening do Game Booster — política de classificação de processos (P2 #1).

Garante que o MODO NORMAL é conservador (não encerra aplicativos legítimos de
fundo como torrents, download managers, limpadores, navegadores e comunicação)
e que apenas MODO AGRESSIVO pode encerrá-los. NENHUM teste executa terminate/
kill reais, Registry real ou psutil real (sempre fake/mock).
"""
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import game_booster as gb  # noqa: E402
from game_booster import CategoriaProcesso  # noqa: E402


class FakeProc:
    """Processo falso compatível com classificar_processo/_validar/_quer_encerrar."""

    def __init__(self, pid=1234, name="x.exe", exe=None, user=None,
                 parent=None, survive=True):
        self.pid = pid
        self.info = {"name": name, "pid": pid, "memory_info": None}
        self._exe = exe
        self._user = user
        self._parent = parent
        self._survive = survive
        self.terminate_calls = 0
        self.kill_calls = 0

    def name(self):
        return self.info.get("name")

    def exe(self):
        if self._exe is None:
            raise gb.psutil.AccessDenied()
        return self._exe

    def username(self):
        if self._user is None:
            raise gb.psutil.AccessDenied()
        return self._user

    def parent(self):
        return self._parent

    def children(self, recursive=True):
        return []

    def terminate(self):
        self.terminate_calls += 1
        if not self._survive:
            self._survive = False

    def kill(self):
        self.kill_calls += 1

    def is_running(self):
        return self._survive


def _metricas():
    return {
        "cpu_percent": 10.0, "ram_percent": 50.0,
        "ram_total_gb": 16.0, "ram_usada_gb": 8.0, "ram_disponivel_gb": 8.0,
        "total_procs": 1, "telemetry_errors": [],
    }


class TestClassificacao(unittest.TestCase):
    """Classificação: mapeia cada processo para a categoria correta."""

    def _cat(self, name, exe=None, user="desktop\\usuario"):
        return gb.classificar_processo(FakeProc(name=name, exe=exe, user=user))

    def test_01_aika_e_game(self):
        proc = FakeProc(name="aika.exe", exe=r"c:\cbmgames\aika\aika.exe",
                        user="desktop\\u")
        self.assertEqual(gb.classificar_processo(proc), CategoriaProcesso.GAME)

    def test_02_optimizer_e_protected(self):
        self.assertEqual(self._cat("aikaoptimizer.exe"), CategoriaProcesso.PROTECTED)
        self.assertEqual(self._cat("python.exe"), CategoriaProcesso.PROTECTED)

    def test_03_windows_critico_e_protected(self):
        for n in ("explorer.exe", "dwm.exe", "csrss.exe", "winlogon.exe",
                  "lsass.exe", "services.exe", "svchost.exe"):
            self.assertEqual(self._cat(n), CategoriaProcesso.PROTECTED, n)

    def test_04_qbittorrent_nao_e_unwanted(self):
        self.assertNotIn("qbittorrent.exe", gb.PROCESSOS_KNOWN_UNWANTED)
        self.assertIn("qbittorrent.exe", gb.PROCESSOS_OPTIONAL_BG)
        self.assertEqual(self._cat("qbittorrent.exe"), CategoriaProcesso.OPTIONAL_BACKGROUND)

    def test_05_utorrent_nao_e_unwanted(self):
        self.assertNotIn("utorrent.exe", gb.PROCESSOS_KNOWN_UNWANTED)
        self.assertEqual(self._cat("utorrent.exe"), CategoriaProcesso.OPTIONAL_BACKGROUND)

    def test_06_idman_nao_e_unwanted(self):
        for n in ("idman.exe", "idm.exe"):
            self.assertNotIn(n, gb.PROCESSOS_KNOWN_UNWANTED)
            self.assertEqual(self._cat(n), CategoriaProcesso.OPTIONAL_BACKGROUND)

    def test_07_ccleaner_nao_e_unwanted(self):
        for n in ("ccleaner.exe", "ccleaner64.exe", "ccupdate.exe"):
            self.assertNotIn(n, gb.PROCESSOS_KNOWN_UNWANTED)
            self.assertEqual(self._cat(n), CategoriaProcesso.OPTIONAL_BACKGROUND)

    def test_08_navegador_nao_e_unwanted(self):
        for n in ("chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe"):
            self.assertNotEqual(self._cat(n), CategoriaProcesso.KNOWN_UNWANTED, n)

    def test_09_comunicacao_nao_e_unwanted(self):
        for n in ("discord.exe", "whatsapp.exe", "teams.exe", "skype.exe", "qq.exe"):
            self.assertNotEqual(self._cat(n), CategoriaProcesso.KNOWN_UNWANTED, n)

    def test_10_desconhecido_e_unknown(self):
        self.assertEqual(
            self._cat("xyztotalmentedesconhecido.exe"), CategoriaProcesso.UNKNOWN)

    def test_11_unwanted_real_mantido(self):
        for n in ("bytefence.exe", "webcompanion.exe",
                  "lavasoft.wca.exe", "hao123.exe"):
            self.assertEqual(self._cat(n), CategoriaProcesso.KNOWN_UNWANTED, n)


class TestModoNormal(unittest.TestCase):
    """MODO NORMAL deve ser conservador: só KNOWN_UNWANTED realmente justificável."""

    def _nao_encerra(self, nome, exe=None):
        cat = gb.classificar_processo(FakeProc(name=nome, exe=exe, user="desktop\\usuario"))
        return gb._quer_encerrar(cat, False, nome)

    def test_12_game_nunca_encerrado(self):
        cat = gb.classificar_processo(
            FakeProc(name="aika.exe", exe=r"c:\cbmgames\aika\aika.exe", user="desktop\\u"))
        self.assertFalse(gb._quer_encerrar(cat, False, "aika.exe"))

    def test_13_protected_nunca_encerrado(self):
        for n in ("explorer.exe", "dwm.exe", "aikaoptimizer.exe", "discord.exe"):
            self.assertFalse(self._nao_encerra(n), n)

    def test_14_optional_background_preservado(self):
        self.assertFalse(self._nao_encerra("qbittorrent.exe"))
        self.assertFalse(self._nao_encerra("ccleaner.exe"))

    def test_15_unknown_preservado(self):
        self.assertFalse(self._nao_encerra("xyztotalmentedesconhecido.exe"))

    def test_16_download_preservado(self):
        for n in ("idman.exe", "idm.exe"):
            self.assertFalse(self._nao_encerra(n), n)

    def test_17_torrent_preservado(self):
        for n in ("qbittorrent.exe", "utorrent.exe", "bittorrent.exe"):
            self.assertFalse(self._nao_encerra(n), n)

    def test_18_navegador_preservado(self):
        for n in ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"):
            self.assertFalse(self._nao_encerra(n), n)

    def test_19_comunicacao_preservada(self):
        for n in ("discord.exe", "whatsapp.exe", "teams.exe", "qq.exe"):
            self.assertFalse(self._nao_encerra(n), n)

    def test_20_apenas_known_unwanted_candidato(self):
        # No modo normal, somente KNOWN_UNWANTED (real PUP/adware) é candidato.
        self.assertTrue(self._nao_encerra("bytefence.exe"))
        self.assertFalse(self._nao_encerra("qbittorrent.exe"))
        self.assertFalse(self._nao_encerra("idman.exe"))
        self.assertFalse(self._nao_encerra("ccleaner.exe"))
        self.assertFalse(self._nao_encerra("chrome.exe"))
        self.assertFalse(self._nao_encerra("discord.exe"))


class TestModoAgressivo(unittest.TestCase):
    """MODO AGRESSIVO pode encerrar OPTIONAL_BACKGROUND, mas nunca os protegidos."""

    def test_21_game_continua_preservado(self):
        cat = gb.classificar_processo(
            FakeProc(name="aika.exe", exe=r"c:\cbmgames\aika\aika.exe", user="desktop\\u"))
        self.assertFalse(gb._quer_encerrar(cat, True, "aika.exe"))

    def test_22_protected_continua_preservado(self):
        for n in ("explorer.exe", "aikaoptimizer.exe", "discord.exe", "avp.exe"):
            cat = gb.classificar_processo(FakeProc(name=n, user="desktop\\usuario"))
            self.assertFalse(gb._quer_encerrar(cat, True, n), n)

    def test_23_critico_continua_preservado(self):
        for n in ("csrss.exe", "lsass.exe", "winlogon.exe", "services.exe"):
            cat = gb.classificar_processo(FakeProc(name=n, user="system"))
            self.assertFalse(gb._quer_encerrar(cat, True, n), n)

    def test_24_optional_background_candidato(self):
        cat = gb.classificar_processo(FakeProc(name="qbittorrent.exe", user="desktop\\usuario"))
        self.assertTrue(gb._quer_encerrar(cat, True, "qbittorrent.exe"))
        cat2 = gb.classificar_processo(FakeProc(name="ccleaner.exe", user="desktop\\usuario"))
        self.assertTrue(gb._quer_encerrar(cat2, True, "ccleaner.exe"))

    def test_25_unknown_nao_morto_cego(self):
        cat = gb.classificar_processo(FakeProc(name="xyztotalmentedesconhecido.exe", user="desktop\\usuario"))
        self.assertFalse(gb._quer_encerrar(cat, True, "xyztotalmentedesconhecido.exe"))

    def test_26_multiplos_aikas_vivos(self):
        for exe in gb.AIKA_GAME_EXES:
            for _ in range(3):
                cat = gb.classificar_processo(FakeProc(name=exe, user="desktop\\usuario"))
                self.assertFalse(gb._quer_encerrar(cat, True, exe), exe)
                self.assertFalse(gb._quer_encerrar(cat, False, exe), exe)

    def test_27_optimizer_vivo(self):
        cat = gb.classificar_processo(FakeProc(name="aikaoptimizer.exe", user="desktop\\usuario"))
        self.assertFalse(gb._quer_encerrar(cat, False, "aikaoptimizer.exe"))
        self.assertFalse(gb._quer_encerrar(cat, True, "aikaoptimizer.exe"))


class TestDryRun(unittest.TestCase):
    def _rodar_dry(self, procs):
        anterior = gb.BOOSTER_ATIVO
        gb.BOOSTER_ATIVO = False
        self.addCleanup(lambda: setattr(gb, "BOOSTER_ATIVO", anterior))
        with mock.patch.object(gb.psutil, "process_iter", return_value=procs), \
             mock.patch.object(gb, "coletar_metricas", return_value=_metricas()), \
             mock.patch.object(gb, "obter_pid_janela_focada", return_value=None), \
             mock.patch.object(gb.time, "sleep"), \
             mock.patch.object(gb, "_log_metricas_snapshot"), \
             mock.patch.object(gb, "_log_resultado_telemetria"), \
             mock.patch.object(gb, "log"):
            return gb.game_session_optimizer(dry_run=True)

    def test_28_29_dry_run_nao_chama_terminate_ou_kill(self):
        proc = FakeProc(name="bytefence.exe", user="desktop\\usuario")
        self._rodar_dry([proc])
        self.assertEqual(proc.terminate_calls, 0)
        self.assertEqual(proc.kill_calls, 0)

    def test_30_dry_run_mesma_selecao_da_execucao(self):
        # A decisão (classificar + _quer_encerrar) independe de dry_run.
        proc = FakeProc(name="bytefence.exe", user="desktop\\usuario")
        cat = gb.classificar_processo(proc)
        self.assertEqual(cat, CategoriaProcesso.KNOWN_UNWANTED)
        # Em execução real, seria selecionado; em dry_run, apenas registrado.
        self.assertTrue(gb._quer_encerrar(cat, False, "bytefence.exe"))

    def test_31_dry_run_inclui_categoria_correta(self):
        proc = FakeProc(name="bytefence.exe", user="desktop\\usuario")
        resultado = self._rodar_dry([proc])
        self.assertEqual(resultado["processos_encerrados"], 0)
        cats = {d.get("categoria") for d in resultado["detalhes_encerramentos"]}
        self.assertIn("KNOWN_UNWANTED", cats)


class TestErros(unittest.TestCase):
    def _proc_falha(self, exc):
        proc = FakeProc(name="teste.exe")

        def terminate_raises():
            raise exc

        proc.terminate = terminate_raises
        return proc

    def test_32_access_denied_nao_quebra(self):
        proc = self._proc_falha(gb.psutil.AccessDenied())
        with mock.patch.object(gb.psutil, "wait_procs", return_value=([], [])):
            self.assertFalse(gb.matar_processo_e_filhos(proc))

    def test_33_no_such_process_nao_quebra(self):
        proc = self._proc_falha(gb.psutil.NoSuchProcess(1234))
        with mock.patch.object(gb.psutil, "wait_procs", return_value=([], [])):
            self.assertFalse(gb.matar_processo_e_filhos(proc))

    def test_34_zombie_process_nao_quebra(self):
        zombie = getattr(gb.psutil, "ZombieProcess", None)
        if zombie is None:
            self.skipTest("psutil.ZombieProcess indisponível")
        proc = self._proc_falha(zombie(1234))
        with mock.patch.object(gb.psutil, "wait_procs", return_value=([], [])):
            self.assertFalse(gb.matar_processo_e_filhos(proc))

    def test_35_processo_desaparecendo_na_enumecao(self):
        proc = FakeProc(name="x.exe")
        proc.info = None

        def nome_sumiu():
            raise gb.psutil.NoSuchProcess(999)

        def exe_sumiu():
            raise gb.psutil.NoSuchProcess(999)

        def user_sumiu():
            raise gb.psutil.NoSuchProcess(999)

        proc.name = nome_sumiu
        proc.exe = exe_sumiu
        proc.username = user_sumiu
        self.assertEqual(gb.classificar_processo(proc), CategoriaProcesso.UNKNOWN)

    def test_36_erro_em_um_nao_bloqueia_outros(self):
        class Ruim(FakeProc):
            def exe(self):
                raise gb.psutil.AccessDenied()

        bom = FakeProc(name="bytefence.exe", user="desktop\\usuario")
        self.assertEqual(gb.classificar_processo(Ruim(name="x.exe")), CategoriaProcesso.UNKNOWN)
        self.assertEqual(gb.classificar_processo(bom), CategoriaProcesso.KNOWN_UNWANTED)


class TestRegressao(unittest.TestCase):
    def test_37_prioridade_aika_intacta(self):
        self.assertTrue(hasattr(gb, "aplicar_high_priority_aika_detalhado"))
        self.assertEqual(
            gb.AIKA_GAME_EXES,
            {"aclient.exe", "aika.exe", "aika_br.exe", "aikabr.exe", "gameengine.exe"})

    def test_38_watchdog_nao_alterado(self):
        # O watchdog continua referenciando os mesmos executáveis do jogo.
        self.assertLessEqual(gb.AIKA_GAME_EXES, gb.PROCESSOS_PROTEGIDOS)

    def test_39_multi_instancia_intacta(self):
        for exe in gb.AIKA_GAME_EXES:
            self.assertIn(exe, gb.PROCESSOS_PROTEGIDOS)
            self.assertNotIn(exe, gb.PROCESSOS_MATAR)

    def test_40_modo_agressivo_config_intacto(self):
        self.assertTrue(callable(gb.is_modo_agressivo))
        self.assertIsInstance(gb.is_modo_agressivo(), bool)

    def test_41_backend_nao_relacionado_inalterado(self):
        # Softwares de segurança real continuam protegidos (nunca encerrados).
        for n in ("360safe.exe", "360se.exe", "avp.exe", "windefend.exe"):
            self.assertIn(n, gb.PROCESSOS_PROTEGIDOS, n)
        # A lista KNOWN_UNWANTED agora só contém PUP/adware/hijacker reais.
        self.assertEqual(
            set(gb.PROCESSOS_KNOWN_UNWANTED),
            {"bytefence.exe", "bytefenceservice.exe",
             "webcompanion.exe", "webcompanionhelper.exe", "webcompanionupdater.exe",
             "lavasoft.wca.exe", "lavasoft.webcompanion.exe",
             "baidu.exe", "baiduan.exe", "hao123.exe"})


class TestLimpezaPoliticaLegada(unittest.TestCase):
    """Garante que a segunda política de kill (finalizar_bloatwares) foi eliminada."""

    def test_finalizar_bloatwares_nao_existe(self):
        self.assertFalse(hasattr(gb, "finalizar_bloatwares"))

    def test_heuristica_kill_legada_ausente(self):
        import pathlib
        src = pathlib.Path(gb.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"utorrent" in nome', src)
        self.assertNotIn('"ccleaner" in nome', src)
        self.assertNotIn('"update" in nome', src)
        self.assertNotIn('mem_mb > 50', src)

    def test_politica_unica_central_presente(self):
        # A única fonte de decisão de kill é a classificação + matriz Normal/Agressivo.
        self.assertTrue(callable(gb.classificar_processo))
        self.assertTrue(callable(gb._quer_encerrar))


if __name__ == "__main__":
    unittest.main(verbosity=2)



