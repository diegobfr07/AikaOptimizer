# -*- coding: utf-8 -*-
"""
Testes NÃO destrutivos — Correção Controlada 01 (Game Booster + Shutdown).

Cobertura exigida:
  - PROTECTED nunca é encerrado
  - UNKNOWN nunca é encerrado
  - 360safe.exe / 360se.exe não são encerrados (segurança real)
  - agent.exe / autoupdater.exe genéricos, sem identidade segura, não encerrados
  - jogo (AIKA) nunca é encerrado
  - dry_run não encerra nada (execução real do motor em modo DRY RUN —
    apenas leitura/classificação; nenhuma chamada destrutiva ocorre)
  - falha/AccessDenied não é contabilizada como encerramento
  - shutdown não executa a rotina pesada diretamente na GUI thread

NÃO executa: kill real, serviço real, Registry real, cliente AIKA, QoS real.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import game_booster as gb
from game_booster import CategoriaProcesso


class FakeProc:
    """Processo falso compatível com classificar_processo/_validar_processo."""

    def __init__(self, pid=1234, name="x.exe", exe=None, user=None,
                 parent=None, survive=True):
        self.pid = pid
        self.info = {"name": name, "pid": pid, "memory_info": None}
        self._exe = exe          # caminho completo (lowercase) ou None
        self._user = user        # usuário (lowercase) ou None
        self._parent = parent    # FakeProc ou None
        self._survive = survive  # se False, "morre" ao terminate()
        self.terminate_calls = 0
        self.kill_calls = 0

    def name(self):
        return self.info.get("name")

    def exe(self):
        # _obter_caminho_exe espera exceção AccessDenied para path ausente
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

    def is_running(self):
        return self._survive


class FakesTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # 1. PROTECTED nunca é encerrado
    # ------------------------------------------------------------------
    def test_protected_nunca_encerrado(self):
        protegidos = [
            ("explorer.exe", None),
            ("csrss.exe", None),
            ("dwm.exe", None),
            ("svchost.exe", "c:\\windows\\system32\\svchost.exe"),
            ("360safe.exe", None),
            ("360se.exe", None),
            ("360tray.exe", None),
            ("360sd.exe", None),
            ("360svc.exe", None),
            ("avp.exe", "c:\\program files\\kaspersky\\avp.exe"),
            ("windefend.exe", None),
        ]
        for nome, exe in protegidos:
            proc = FakeProc(name=nome, exe=exe)
            cat = gb.classificar_processo(proc)
            self.assertEqual(
                cat, CategoriaProcesso.PROTECTED,
                f"{nome} deveria ser PROTECTED, veio {cat}")
            self.assertFalse(
                gb._quer_encerrar(cat, True, nome),
                f"PROTECTED {nome} NÃO pode ser encerrado nem no modo agressivo")

    # ------------------------------------------------------------------
    # 2. UNKNOWN nunca é encerrado
    # ------------------------------------------------------------------
    def test_unknown_nunca_encerrado(self):
        proc = FakeProc(name="xyztotalmentedesconhecido.exe",
                        exe="c:\\usuarios\\teste\\app\\xyz.exe",
                        user="desktop\\usuario")
        cat = gb.classificar_processo(proc)
        self.assertEqual(cat, CategoriaProcesso.UNKNOWN)
        self.assertFalse(gb._quer_encerrar(cat, False, "xyztotalmentedesconhecido.exe"))
        self.assertFalse(gb._quer_encerrar(cat, True, "xyztotalmentedesconhecido.exe"))
        # sem nome (None) também bloqueia
        self.assertFalse(gb._quer_encerrar(CategoriaProcesso.KNOWN_UNWANTED, True, None))

    # ------------------------------------------------------------------
    # 3. 360safe.exe / 360se.exe (segurança real) não são encerrados
    # ------------------------------------------------------------------
    def test_360safe_nunca_encerrado(self):
        for nome in ("360safe.exe", "360se.exe", "360tray.exe", "360sd.exe", "360svc.exe"):
            self.assertNotIn(
                nome, gb.PROCESSOS_KNOWN_UNWANTED,
                f"{nome} não pode estar na kill-list KNOWN_UNWANTED")
            self.assertNotIn(
                nome, gb.PROCESSOS_MATAR,
                f"{nome} não pode estar na kill-list final")
            self.assertIn(
                nome, gb.PROCESSOS_PROTEGIDOS,
                f"{nome} deve estar explicitamente protegido")
            # Classificador real: checagem PROTECTED vem antes de KNOWN_UNWANTED
            proc = FakeProc(name=nome, exe="c:\\360\\safe.exe", user="desktop\\u")
            cat = gb.classificar_processo(proc)
            self.assertEqual(cat, CategoriaProcesso.PROTECTED)
            self.assertFalse(gb._quer_encerrar(cat, True, nome))

    def test_seguranca_conjunto_protegido(self):
        for nome in gb.PROCESSOS_SEGURANCA_PROTEGIDOS:
            self.assertIn(nome, gb.PROCESSOS_PROTEGIDOS)

    # ------------------------------------------------------------------
    # 4. agent.exe / autoupdater.exe genéricos não são encerrados
    # ------------------------------------------------------------------
    def test_agente_generico_nao_encerrado(self):
        for nome in ("agent.exe", "autoupdater.exe"):
            self.assertNotIn(
                nome, gb.PROCESSOS_MATAR,
                f"{nome} (genérico) não pode estar em nenhuma kill-list")
            self.assertNotIn(nome, gb.PROCESSOS_OPTIONAL_BG)
            self.assertNotIn(nome, gb.PROCESSOS_KNOWN_UNWANTED)
            # Barreira dupla: mesmo se alguém re-adicionar às listas,
            # _quer_encerrar bloqueia pelo nome genérico.
            self.assertFalse(gb._quer_encerrar(CategoriaProcesso.OPTIONAL_BACKGROUND, True, nome))
            self.assertFalse(gb._quer_encerrar(CategoriaProcesso.KNOWN_UNWANTED, False, nome))
            # Classificação real de um agent.exe qualquer → UNKNOWN
            proc = FakeProc(name=nome, exe="c:\\programas\\outro\\agent.exe",
                            user="desktop\\usuario")
            cat = gb.classificar_processo(proc)
            self.assertEqual(
                cat, CategoriaProcesso.UNKNOWN,
                f"{nome} sem identidade segura deve ser tratado como UNKNOWN")

    # ------------------------------------------------------------------
    # 5. Jogo (AIKA) nunca é encerrado
    # ------------------------------------------------------------------
    def test_jogo_nunca_encerrado(self):
        for nome in gb.AIKA_GAME_EXES | gb.AIKA_LAUNCHER_EXES:
            self.assertIn(nome, gb.PROCESSOS_PROTEGIDOS)
            self.assertNotIn(nome, gb.PROCESSOS_MATAR)
            cat = gb.classificar_processo(FakeProc(name=nome, exe=None))
            self.assertIn(cat, (CategoriaProcesso.PROTECTED, CategoriaProcesso.GAME))
            self.assertFalse(gb._quer_encerrar(cat, True, nome))
        # caminho do cliente → GAME, e GAME nunca é alvo
        proc = FakeProc(name="aika.exe",
                        exe="c:\\cbmgames\\aika\\aika.exe", user="desktop\\u")
        cat = gb.classificar_processo(proc)
        self.assertEqual(cat, CategoriaProcesso.GAME)
        self.assertFalse(gb._quer_encerrar(cat, False, "aika.exe"))
        self.assertFalse(gb._quer_encerrar(cat, True, "aika.exe"))

    # ------------------------------------------------------------------
    # 6. DRY RUN não encerra nada (motor real em modo leitura)
    # ------------------------------------------------------------------
    def test_dry_run_nao_encerra_nada(self):
        resultado = gb.game_session_optimizer(dry_run=True)
        self.assertEqual(resultado["status"], "completed")
        self.assertTrue(resultado["dry_run"])
        self.assertEqual(resultado["processos_encerrados"], 0)
        for detalhe in resultado["detalhes_encerramentos"]:
            self.assertFalse(
                detalhe.get("encerrado", False),
                f"DRY RUN não pode encerrar: {detalhe}")
            self.assertEqual(detalhe.get("motivo"), "DRY_RUN")

    # ------------------------------------------------------------------
    # 7. AccessDenied / sobrevivência não contam como encerramento
    # ------------------------------------------------------------------
    def test_accessdenied_nao_contabiliza(self):
        proc = FakeProc(name="teste.exe")

        def terminate_denied():
            raise gb.psutil.AccessDenied()

        proc.terminate = terminate_denied
        with mock.patch.object(gb.psutil, "wait_procs", return_value=([], [])):
            self.assertFalse(gb.matar_processo_e_filhos(proc))

    def test_processo_vivo_nao_contabiliza(self):
        # terminate "funciona" mas o processo continua vivo → NÃO conta
        proc = FakeProc(name="teste.exe", survive=True)
        with mock.patch.object(gb.psutil, "wait_procs", return_value=([], [proc])), \
             mock.patch.object(gb.psutil, "pid_exists", return_value=True), \
             mock.patch.object(gb.psutil, "Process", return_value=proc):
            self.assertFalse(gb.matar_processo_e_filhos(proc))

    def test_processo_morto_contabiliza(self):
        proc = FakeProc(name="teste.exe", survive=False)
        with mock.patch.object(gb.psutil, "wait_procs", return_value=([], [])), \
             mock.patch.object(gb.psutil, "pid_exists", return_value=False):
            self.assertTrue(gb.matar_processo_e_filhos(proc))


class ShutdownTests(unittest.TestCase):
    """Verifica que o cleanup pesado do shutdown NÃO roda na GUI thread."""

    @classmethod
    def setUpClass(cls):
        import main  # import pesado — feito apenas uma vez

        cls.main = main

    def test_rotina_e_modulo_nao_metodo(self):
        self.assertTrue(callable(self.main._rotina_cleanup_shutdown))
        # Não pode ser um método da janela (que rodaria na GUI thread)
        self.assertFalse(
            hasattr(self.main.AikaOptimizerPro, "_rotina_cleanup_shutdown"))

    def test_finalizacao_usa_worker_e_timeout(self):
        import inspect
        fonte = inspect.getsource(self.main.AikaOptimizerPro._finalizar_shutdown_seguro)
        self.assertIn("TarefaWorker(_rotina_cleanup_shutdown)", fonte)
        self.assertIn("QTimer.singleShot", fonte)
        # A rotina pesada NÃO pode ser chamada diretamente aqui
        self.assertNotIn("opt.desativar_game_booster(", fonte)
        self.assertNotIn("opt.remover_qos_aika(", fonte)

    def test_cleanup_worker_com_timeout(self):
        self.assertTrue(hasattr(self.main, "SHUTDOWN_CLEANUP_TIMEOUT_MS"))
        self.assertGreater(self.main.SHUTDOWN_CLEANUP_TIMEOUT_MS, 0)
        # wait limitado no aboutToQuit — nunca espera indefinidamente
        import inspect
        fonte = inspect.getsource(self.main._aguardar_cleanup_shutdown)
        self.assertIn("worker.wait(", fonte)

    def test_aguardar_cleanup_tolerante_a_falhas(self):
        # RuntimeError (objeto C++ já destruído) não pode propagar
        worker_ruim = mock.Mock()
        worker_ruim.isRunning.side_effect = RuntimeError("wrapped C/C++ deleted")
        janela = mock.Mock()
        janela._shutdown_worker = worker_ruim
        self.main._aguardar_cleanup_shutdown(janela)  # não levanta
        worker_ruim.wait.assert_not_called()

        # worker parado → sem wait
        worker_parado = mock.Mock()
        worker_parado.isRunning.return_value = False
        janela._shutdown_worker = worker_parado
        self.main._aguardar_cleanup_shutdown(janela)
        worker_parado.wait.assert_not_called()

        # worker rodando → espera limitada
        worker_vivo = mock.Mock()
        worker_vivo.isRunning.return_value = True
        janela._shutdown_worker = worker_vivo
        self.main._aguardar_cleanup_shutdown(janela)
        worker_vivo.wait.assert_called_once()

        # sem worker → não levanta
        self.main._aguardar_cleanup_shutdown(mock.Mock(spec=[]))

    def test_rotina_cleanup_trata_falhas(self):
        # Falha no Booster → não propaga; QoS ainda tentada
        with mock.patch.object(self.main.opt, "desativar_game_booster",
                               side_effect=RuntimeError("falha simulada")), \
             mock.patch.object(self.main.opt, "remover_qos_aika",
                               return_value=None), \
             mock.patch.object(self.main.opt, "log", return_value=None):
            res = self.main._rotina_cleanup_shutdown()
        self.assertEqual(res, {"booster": False, "qos": True})

        # Falha em ambos → flags falsas, sem exceção
        with mock.patch.object(self.main.opt, "desativar_game_booster",
                               side_effect=RuntimeError("falha simulada")), \
             mock.patch.object(self.main.opt, "remover_qos_aika",
                               side_effect=RuntimeError("falha simulada")), \
             mock.patch.object(self.main.opt, "log", return_value=None):
            res = self.main._rotina_cleanup_shutdown()
        self.assertEqual(res, {"booster": False, "qos": False})

        # Sucesso em ambos
        with mock.patch.object(self.main.opt, "desativar_game_booster",
                               return_value=None), \
             mock.patch.object(self.main.opt, "remover_qos_aika",
                               return_value=None):
            res = self.main._rotina_cleanup_shutdown()
        self.assertEqual(res, {"booster": True, "qos": True})


if __name__ == "__main__":
    unittest.main(verbosity=2)


