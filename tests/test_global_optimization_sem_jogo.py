# -*- coding: utf-8 -*-
"""Otimização Global com o cliente AIKA FECHADO (processo inexistente).

CAUSA RAIZ CORRIGIDA
--------------------
``sistema.prioridade_total`` abortava a etapa de prioridade quando
``fazer_backup_registro`` devolvia ``False``. Isso ocorria SEMPRE que a chave
IFEO do executável AINDA NÃO EXISTIA, porque ``reg export`` de uma chave
inexistente retorna código 1 (comportamento real do Windows, reproduzido
neste ambiente). Na primeira otimização — cliente nunca inicializado — e com
NENHUM processo AIKA em execução, o segundo laço de ``prioridade_total``
(elevação por PID) não roda, então ``sucesso`` permanecia ``False``:

    prioridade_total() -> False
      -> TransacaoSistema.executar levanta RuntimeError
      -> rollback_total()
      -> "[ERRO] ERRO CRÍTICO: prioridade_total retornou False"

Com o cliente ABERTO a mesma falha de backup era MASCARADA pelo laço de
processos (que define ``sucesso = True``) — o que explica o sintoma relatado
("com o jogo fechado dá erro crítico; com o jogo aberto funciona").

CORREÇÃO (cirúrgica, em ``seguranca.fazer_backup_registro``)
-----------------------------------------------------------
A ausência da chave IFEO é o estado inicial NORMAL e não é erro: não há
estado anterior a preservar, e a baseline do estado original já é registrada
pelo ownership moderno (``ifeo_state.json``, via ``garantir_ifeo_ownership``),
que é justamente o que a restauração usa — ``restaurar_registro_sistema``
exclui ``backup_prioridade_*`` do ``reg import`` cego. Logo, o artefato legado
de prioridade é considerado satisfeito (sem exportar) quando a chave não
existe, permitindo que o fluxo siga até aplicar o IFEO ``CpuPriorityClass``.

Este arquivo prova, SEM tocar Registry/powercfg/psutil reais:
- ausência do processo + chave IFEO inexistente NÃO vira erro crítico;
- a prioridade persistente (IFEO CpuPriorityClass=6) continua sendo aplicada;
- a ausência de processo NÃO dispara rollback global;
- processo presente continua recebendo prioridade (caminho preservado);
- erro REAL continua erro: backup de chave EXISTENTE que falha, ``reg add``
  negado, metadata IFEO corrompida e artefatos de terceiros;
- o watchdog continua aplicando a prioridade quando o jogo abre depois.
"""
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psutil  # noqa: E402

import main  # noqa: E402
import seguranca  # noqa: E402
import sistema  # noqa: E402


EXE = "aclient.exe"
IFEO_BASE = seguranca.IFEO_BASE_KEY
V = seguranca.IFEO_CPU_PRIORITY_CLASS_VALUE          # 6
REG_DWORD = seguranca.IFEO_CPU_PRIORITY_CLASS_TYPE


def _sem_hive(caminho):
    """Normaliza um caminho de Registro removendo o prefixo da hive."""
    texto = str(caminho).lower()
    for prefixo in ("hkey_local_machine\\", "hklm\\"):
        if texto.startswith(prefixo):
            return texto[len(prefixo):]
    return texto


def _chave_ifeo(exe=EXE):
    return (IFEO_BASE + "\\" + exe).lower()


class _Chave:
    def __init__(self, valores):
        self.valores = dict(valores)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeWinreg:
    """winreg mínimo do IFEO: SOMENTE as chaves declaradas existem (leitura)."""

    HKEY_LOCAL_MACHINE = "HKLM"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    KEY_ALL_ACCESS = 3
    REG_DWORD = 4
    REG_SZ = 1

    def __init__(self, chaves=None):
        self.chaves = {k.lower(): dict(v) for k, v in (chaves or {}).items()}

    def OpenKey(self, hive, caminho, res=0, acesso=0):
        if hive != self.HKEY_LOCAL_MACHINE:
            raise FileNotFoundError(caminho)
        nome = caminho.lower()
        if nome not in self.chaves:
            raise FileNotFoundError(caminho)
        return _Chave(self.chaves[nome])

    def EnumValue(self, chave, indice):
        nomes = sorted(chave.valores)
        if indice >= len(nomes):
            raise OSError("fim")
        nome = nomes[indice]
        valor, tipo = chave.valores[nome]
        return nome, valor, tipo


class FakeProc:
    """Processo falso com leitura/escrita de prioridade controlada."""

    def __init__(self, pid, inicial=psutil.NORMAL_PRIORITY_CLASS, nome=EXE):
        self.pid = pid
        self.info = {"name": nome, "pid": pid, "create_time": float(pid)}
        self._nice = inicial
        self.set_attempts = []

    def name(self):
        return self.info["name"]

    def exe(self):
        return "C:\\CBMgames\\AikaOnlineBrasil\\" + self.info["name"]

    def nice(self, valor=None):
        if valor is None:
            return self._nice
        self.set_attempts.append(valor)
        self._nice = valor
        return self._nice

    def ionice(self, valor=None):
        return 0


class _Sandbox(unittest.TestCase):
    """Isola estado/backup/Registry: nada real é lido ou alterado."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.reg_dir = os.path.join(self._td.name, "Registro_Sistema")
        self.base_dir = os.path.join(self._td.name, "backup")
        self.ifeo_path = os.path.join(self.reg_dir, "ifeo_state.json")
        self.mig_path = os.path.join(self.reg_dir, "legacy_ifeo_migrations.json")
        self.logs = []
        self.cmds = []
        self.chaves_winreg = set()
        for patch_ in (
            mock.patch.object(seguranca, "PASTA_BACKUP_REG", self.reg_dir),
            mock.patch.object(seguranca, "ARQUIVO_IFEO", self.ifeo_path),
            mock.patch.object(seguranca, "ARQUIVO_MIGRACOES_IFEO", self.mig_path),
            mock.patch.object(seguranca, "PASTA_BACKUP", self.base_dir),
            mock.patch.object(seguranca, "ARQUIVO_ESTADO",
                              os.path.join(self.base_dir, "estado_sistema.json")),
            mock.patch.object(seguranca, "log", self.logs.append),
            mock.patch.object(sistema, "log", self.logs.append),
            mock.patch.object(sistema, "AIKA_GAME_EXES", {EXE}),
        ):
            patch_.start()
            self.addCleanup(patch_.stop)

    # ------------------------------------------------------------------
    def _instalar(self, chave_ifeo_existe=False, reg_add_ok=True,
                  export_ok=True, processos=()):
        """Registry falso + 'reg' honesto (export de chave inexistente falha)."""
        self.chaves_winreg = set()
        if chave_ifeo_existe:
            self.chaves_winreg.add(_chave_ifeo())
            self.chaves_winreg.add(_chave_ifeo() + "\\perfoptions")
        fake_winreg = FakeWinreg({c: {} for c in self.chaves_winreg})

        def comando(cmd, *args, **kwargs):
            lista = list(cmd) if isinstance(cmd, (list, tuple)) else [cmd]
            self.cmds.append(lista)
            if len(lista) >= 4 and lista[0] == "reg" and lista[1] == "export":
                # 'reg export' REAL: falha (código 1) se a chave não existir.
                if not export_ok:
                    return False
                if _sem_hive(lista[2]) not in self.chaves_winreg:
                    return False
                destino = lista[3]
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                with open(destino, "wb") as arquivo:
                    arquivo.write(b"Windows Registry Editor Version 5.00\r\n")
                return True
            if len(lista) >= 2 and lista[0] == "reg" and lista[1] == "add":
                return reg_add_ok
            return True

        for patch_ in (
            mock.patch.object(seguranca, "winreg", fake_winreg),
            mock.patch.object(seguranca, "executar_comando_seguro", comando),
            mock.patch.object(sistema, "executar_comando_seguro", comando),
            mock.patch.object(psutil, "process_iter", return_value=list(processos)),
        ):
            patch_.start()
            self.addCleanup(patch_.stop)
        return fake_winreg

    # ------------------------------------------------------------------
    def _reg_adds(self):
        return [c for c in self.cmds
                if len(c) >= 2 and c[0] == "reg" and c[1] == "add"]

    def _exports(self):
        return [c for c in self.cmds
                if len(c) >= 2 and c[0] == "reg" and c[1] == "export"]

    def _artefato(self, exe=EXE):
        return os.path.join(self.reg_dir, "backup_prioridade_%s.reg" % exe)

    def _texto_logs(self):
        return "\n".join(str(x) for x in self.logs)


class _Sinal:
    def __init__(self):
        self.valores = []

    def emit(self, *args):
        self.valores.append(args)


class _Sinais:
    def __init__(self):
        self.log_signal = _Sinal()
        self.metrics_signal = _Sinal()
        self.booster_visible_signal = _Sinal()


class _TransacaoEspia(seguranca.TransacaoSistema):
    """Transação real que apenas registra se rollback_total foi acionado."""

    def __init__(self):
        super().__init__()
        self.rollbacks = 0

    def rollback_total(self):
        self.rollbacks += 1
        return super().rollback_total()


# ---------------------------------------------------------------------------
# CENÁRIO A — cliente FECHADO e chave IFEO ainda inexistente
# ---------------------------------------------------------------------------
class TestPrioridadeComClienteFechado(_Sandbox):
    """A ausência normal do processo/cliente NÃO pode virar erro crítico."""

    def test_01_chave_ausente_nao_e_erro_e_aplica_ifeo(self):
        self._instalar(chave_ifeo_existe=False, processos=[])
        self.assertTrue(sistema.prioridade_total(),
                        "prioridade_total com o jogo fechado não pode retornar False")
        adds = self._reg_adds()
        self.assertEqual(len(adds), 1, "o IFEO persistente precisa ser aplicado")
        linha = " ".join(str(x) for x in adds[0])
        self.assertIn(EXE, linha)
        self.assertIn("CpuPriorityClass", linha)
        self.assertIn(str(V), linha)

    def test_02_nenhuma_exportacao_e_nenhum_artefato_falso(self):
        self._instalar(chave_ifeo_existe=False, processos=[])
        sistema.prioridade_total()
        self.assertEqual(self._exports(), [], "não há estado anterior a exportar")
        self.assertFalse(os.path.exists(self._artefato()),
                         "nenhum .reg falso pode ser criado")

    def test_03_baseline_de_ownership_registrada_sem_chave(self):
        self._instalar(chave_ifeo_existe=False, processos=[])
        sistema.prioridade_total()
        with open(self.ifeo_path, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        entrada = dados["executables"][EXE]
        self.assertFalse(entrada["ifeo_key_existed"])
        self.assertFalse(entrada["perfoptions_existed"])
        self.assertEqual(entrada["values_before"], {})

    def test_04_transacao_nao_aborta_e_nao_faz_rollback(self):
        self._instalar(chave_ifeo_existe=False, processos=[])
        transacao = seguranca.TransacaoSistema()
        self.assertTrue(transacao.executar(sistema.prioridade_total))
        self.assertEqual(transacao.passos_executados, [],
                         "nenhuma ação de rollback deve ser registrada/executada")


# ---------------------------------------------------------------------------
# CENÁRIO D — erros REAIS continuam sendo erros
# ---------------------------------------------------------------------------
class TestErrosReaisContinuamErros(_Sandbox):
    def test_05_chave_existente_backup_falho_continua_bloqueando(self):
        self._instalar(chave_ifeo_existe=True, export_ok=False, processos=[])
        self.assertFalse(sistema.prioridade_total())
        self.assertEqual(self._reg_adds(), [])
        self.assertIn("backup de Registro falhou", self._texto_logs())

    def test_06_chave_existente_backup_ok_continua_aplicando(self):
        self._instalar(chave_ifeo_existe=True, export_ok=True, processos=[])
        self.assertTrue(sistema.prioridade_total())
        self.assertTrue(os.path.isfile(self._artefato()),
                        "com a chave existente o backup .reg continua obrigatório")
        self.assertEqual(len(self._reg_adds()), 1)

    def test_07_reg_add_negado_continua_sendo_erro(self):
        self._instalar(chave_ifeo_existe=False, reg_add_ok=False, processos=[])
        self.assertFalse(sistema.prioridade_total(),
                         "permissão negada na escrita não pode ser mascarada")
        self.assertEqual(len(self._reg_adds()), 1, "a tentativa real foi feita")

    def test_08_metadata_ifeo_corrompida_continua_bloqueando(self):
        self._instalar(chave_ifeo_existe=True, processos=[])
        os.makedirs(self.reg_dir, exist_ok=True)
        with open(self.ifeo_path, "w", encoding="utf-8") as arquivo:
            arquivo.write("{ isto nao e json valido")
        self.assertFalse(sistema.prioridade_total())
        self.assertEqual(self._reg_adds(), [])

    def test_09_artefato_de_terceiro_continua_estrito(self):
        self._instalar(chave_ifeo_existe=False, processos=[])
        # 'backup_gamedvr' não pertence ao namespace de prioridade: a ausência da
        # chave continua sendo falha de exportação (comportamento preservado).
        self.assertFalse(seguranca.fazer_backup_registro(
            r"HKLM\Software\Microsoft\Windows\CurrentVersion\GameDVR",
            "backup_gamedvr"))
        self.assertEqual(len(self._exports()), 1)

    def test_10_exe_fora_da_allowlist_nao_vira_noop(self):
        self._instalar(chave_ifeo_existe=False, processos=[])
        self.assertFalse(seguranca.fazer_backup_registro(
            r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File "
            r"Execution Options\notepad.exe",
            "backup_prioridade_notepad.exe"))
        self.assertEqual(len(self._exports()), 1)


# ---------------------------------------------------------------------------
# CENÁRIO C — cliente JÁ aberto: caminho preservado
# ---------------------------------------------------------------------------
class TestClienteAberto(_Sandbox):
    def test_11_processo_presente_recebe_prioridade(self):
        proc = FakeProc(4242)
        info = SimpleNamespace(info={"name": EXE, "pid": 4242})
        self._instalar(chave_ifeo_existe=False, processos=[info])
        with mock.patch.object(psutil, "Process", return_value=proc):
            self.assertTrue(sistema.prioridade_total())
        self.assertEqual(proc.set_attempts, [psutil.ABOVE_NORMAL_PRIORITY_CLASS])

    def test_12_processo_em_high_nao_e_rebaixado(self):
        proc = FakeProc(4242, inicial=psutil.HIGH_PRIORITY_CLASS)
        info = SimpleNamespace(info={"name": EXE, "pid": 4242})
        self._instalar(chave_ifeo_existe=False, processos=[info])
        with mock.patch.object(psutil, "Process", return_value=proc):
            self.assertTrue(sistema.prioridade_total())
        self.assertEqual(proc.set_attempts, [])
        self.assertEqual(proc._nice, psutil.HIGH_PRIORITY_CLASS)


# ---------------------------------------------------------------------------
# CENÁRIO A (fim a fim) — fluxo real da Otimização Global com o cliente FECHADO
# ---------------------------------------------------------------------------
class TestOtimizacaoGlobalComClienteFechado(_Sandbox):
    """Exercita o caminho real iniciar_boost_seguro -> tarefa -> TransacaoSistema."""

    def _janela(self):
        win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
        win.sinais = _Sinais()
        win.booster_panel = mock.Mock()
        win._suprimir_auto_boost_ate = 0
        win._auto_boost_pending = False
        win._booster_restore_pending = False
        tarefas = []
        win.executar_em_background = lambda tarefa, **kwargs: tarefas.append(tarefa) or True
        return win, tarefas

    def _rodar(self, transacao=None):
        memoria = SimpleNamespace(total=16 * 1024**3, used=8 * 1024**3,
                                  available=8 * 1024**3, percent=50.0)
        resultado_gb = {
            "status": "completed",
            "metricas_antes": {"cpu_percent": 10.0, "ram_percent": 40.0},
            "metricas_depois": {"cpu_percent": 9.0, "ram_percent": 39.0},
            "processos_encerrados": 0, "mem_associada_mb": 0.0,
        }
        alcancou = {"gb": False}

        def fake_gb(dry_run=False):
            alcancou["gb"] = True
            return resultado_gb

        win, tarefas = self._janela()
        patches = [
            mock.patch.object(main.opt, "jogo_esta_aberto", return_value=False),
            mock.patch.object(main.opt, "salvar_snapshot_sistema", return_value=True),
            mock.patch.object(main.opt, "capturar_estado_sistema", return_value={}),
            mock.patch.object(main.opt, "modo_desempenho_maximo", return_value="success"),
            mock.patch.object(main.opt, "game_session_optimizer", side_effect=fake_gb),
            mock.patch.object(main.opt, "obter_pasta_jogo_atual", return_value=""),
            mock.patch.object(main.opt, "iniciar_jogo", return_value=True),
            mock.patch("psutil.cpu_percent", return_value=3.0),
            mock.patch("psutil.virtual_memory", return_value=memoria),
        ]
        if transacao is not None:
            patches.append(mock.patch.object(main.opt, "TransacaoSistema",
                                             lambda: transacao))
        for patch_ in patches:
            patch_.start()
            self.addCleanup(patch_.stop)
        win.iniciar_boost_seguro()
        self.assertEqual(len(tarefas), 1)
        tarefas.pop(0)()          # executa exatamente como o worker faria
        return win, alcancou

    def test_13_fluxo_global_sem_jogo_nao_vira_erro_critico(self):
        self._instalar(chave_ifeo_existe=False, processos=[])
        win, alcancou = self._rodar()
        texto = "\n".join(str(a[0]) for a in win.sinais.log_signal.valores)
        self.assertTrue(alcancou["gb"], "o Game Session Optimizer deve ser alcançado")
        self.assertIn("Ativando Game Session Optimizer", texto)
        self.assertIn("OTIMIZAÇÃO COMPLETA FINALIZADA COM SUCESSO", texto)
        self.assertNotIn("ERRO CRÍTICO", texto)
        self.assertNotIn("retornou False", texto)
        self.assertEqual(len(self._reg_adds()), 1)

    def test_14_ausencia_de_processo_nao_dispara_rollback(self):
        self._instalar(chave_ifeo_existe=False, processos=[])
        espia = _TransacaoEspia()
        win, alcancou = self._rodar(transacao=espia)
        texto = "\n".join(str(a[0]) for a in win.sinais.log_signal.valores)
        self.assertTrue(alcancou["gb"])
        self.assertEqual(espia.rollbacks, 0, "rollback global não pode ser disparado")
        self.assertNotIn("Rollback automático", texto)


# ---------------------------------------------------------------------------
# CENÁRIO B — o cliente abre DEPOIS: prioridade continua sendo aplicada
# ---------------------------------------------------------------------------
class TestMecanismoAutomaticoPosterior(unittest.TestCase):
    """O watchdog aplica HIGH por PID assim que o processo aparece."""

    def test_15_watchdog_aplica_prioridade_quando_cliente_abre(self):
        procs = {4242: FakeProc(4242)}
        watchdog = main.AikaWatchdogThread(parent=None)
        with mock.patch.object(watchdog, "_listar_pids_jogo",
                               return_value={4242: 4242.0}), \
             mock.patch.object(psutil, "process_iter", return_value=[
                 SimpleNamespace(info={"name": EXE, "pid": 4242})]), \
             mock.patch.object(psutil, "Process",
                               side_effect=lambda pid: procs[pid]):
            watchdog._processar_ciclo()
        self.assertEqual(procs[4242]._nice, psutil.HIGH_PRIORITY_CLASS)

    def test_16_watchdog_sem_processo_nao_falha(self):
        watchdog = main.AikaWatchdogThread(parent=None)
        with mock.patch.object(watchdog, "_listar_pids_jogo", return_value={}):
            watchdog._processar_ciclo()
        self.assertEqual(watchdog.current_pids, {})


if __name__ == "__main__":
    unittest.main()
