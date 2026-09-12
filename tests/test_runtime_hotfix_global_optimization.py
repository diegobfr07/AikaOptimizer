# -*- coding: utf-8 -*-
"""Hotfix runtime V4.1 — Otimização Global (Build Candidate).

Cobre, sem tocar Registry/powercfg/PowerShell/psutil de processos reais,
cliente AIKA, config.json ou backups reais, os DOIS defeitos reais:

BUG #1 — backup_prioridade_aclient.exe.reg legado com before=6 e
CpuPriorityClass atual=6 fazia ``garantir_ifeo_ownership`` devolver ``False``;
``sistema.prioridade_total`` devolvia ``False`` e ``TransacaoSistema`` abortava
a Otimização Global ("prioridade_total retornou False"). Semântica corrigida:
tri-estado ``True`` (OWNERSHIP OK) / ``IFEO_NOOP`` (NO-OP seguro) / ``False``
(falha real).

BUG #2 — a Otimização Global JÁ roda fora da GUI (``executar_em_background``
→ ``TarefaWorker(QThread)``); as chamadas externas que podiam ficar penduradas
(powercfg / PowerShell) ganharam timeout e fallback seguro. A serialização do
botão (``tarefa_lock``/``executando_tarefa``) e a reabilitação
(``limpar_execucao``) continuam preservadas.
"""
import codecs
import inspect
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psutil  # noqa: E402

import main  # noqa: E402
import seguranca  # noqa: E402
import sistema  # noqa: E402


IFEO_BASE = seguranca.IFEO_BASE_KEY.lower()
G_EXE = "aclient.exe"
V = seguranca.IFEO_CPU_PRIORITY_CLASS_VALUE  # 6
REG_DWORD = seguranca.IFEO_CPU_PRIORITY_CLASS_TYPE


# ---------------------------------------------------------------------------
# Fakes de Registro IFEO (nenhum acesso ao Registry real)
# ---------------------------------------------------------------------------
class _KeyHandle:
    def __init__(self, path, reg):
        self.path = path
        self.reg = reg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeIfeoReg:
    HKEY_LOCAL_MACHINE = "HKLM"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    KEY_ALL_ACCESS = 3
    REG_DWORD = 4
    REG_SZ = 1

    def __init__(self, keys=None):
        self.keys = {k.lower(): dict(v) for k, v in (keys or {}).items()}

    def OpenKey(self, hive, path, res=0, access=0):
        if hive != self.HKEY_LOCAL_MACHINE:
            raise FileNotFoundError()
        p = path.lower()
        if p not in self.keys:
            raise FileNotFoundError()
        return _KeyHandle(p, self)

    def EnumValue(self, key, idx):
        vals = self.keys.get(key.path, {})
        nomes = sorted(vals.keys())
        if idx < 0 or idx >= len(nomes):
            raise OSError("fim")
        nome = nomes[idx]
        valor, tipo = vals[nome]
        return nome, valor, tipo

    def SetValueEx(self, key, nome, res, tipo, valor):
        self.keys.setdefault(key.path, {})[nome] = (valor, tipo)

    def DeleteValue(self, key, nome):
        self.keys.get(key.path, {}).pop(nome, None)

    def DeleteKey(self, key, subkey):
        self.keys.pop(key.path + "\\" + subkey.lower(), None)


def _estado_ifeo(exe, perfoptions_values=None, ifeo_key_exists=True):
    exe = exe.lower()
    keys = {}
    if ifeo_key_exists:
        keys[IFEO_BASE + "\\" + exe] = {}
        if perfoptions_values is not None:
            keys[IFEO_BASE + "\\" + exe + "\\perfoptions"] = dict(perfoptions_values)
    return keys


# ---------------------------------------------------------------------------
# Sandbox: paths de estado/IFEО/backup em TemporaryDirectory (nada real)
# ---------------------------------------------------------------------------
class _SandboxIFEO(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.reg_dir = os.path.join(self._td.name, "Registro_Sistema")
        self.ifeo_path = os.path.join(self.reg_dir, "ifeo_state.json")
        self.mig_path = os.path.join(self.reg_dir, "legacy_ifeo_migrations.json")
        self.backup_dir = os.path.join(self._td.name, "backup")
        self.estado_path = os.path.join(self.backup_dir, "estado_sistema.json")
        for p in (
            mock.patch.object(seguranca, "ARQUIVO_IFEO", self.ifeo_path),
            mock.patch.object(seguranca, "ARQUIVO_MIGRACOES_IFEO", self.mig_path),
            mock.patch.object(seguranca, "PASTA_BACKUP_REG", self.reg_dir),
            mock.patch.object(seguranca, "PASTA_BACKUP", self.backup_dir),
            mock.patch.object(seguranca, "ARQUIVO_ESTADO", self.estado_path),
            mock.patch.object(seguranca, "log"),
        ):
            p.start()
            self.addCleanup(p.stop)

    def _escrever_reg_legado(self, cpu_before, exe=G_EXE):
        os.makedirs(self.reg_dir, exist_ok=True)
        caminho = os.path.join(self.reg_dir, "backup_prioridade_%s.reg" % exe)
        with open(caminho, "wb") as f:
            f.write(_reg_bytes_legado(exe, cpu_before))
        return caminho

    def _patch_winreg(self, current_cpu, exe=G_EXE):
        fake = FakeIfeoReg(_estado_ifeo(exe, {"CpuPriorityClass": (current_cpu, REG_DWORD)}))
        p = mock.patch.object(seguranca, "winreg", fake)
        p.start()
        self.addCleanup(p.stop)
        return fake

    def _ler_metadata(self):
        if not os.path.isfile(self.ifeo_path):
            return None
        with open(self.ifeo_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _ler_migracoes(self):
        if not os.path.isfile(self.mig_path):
            return {}
        with open(self.mig_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _perf_cpu(self, fake, exe=G_EXE):
        return fake.keys.get(IFEO_BASE + "\\" + exe.lower() + "\\perfoptions", {}).get(
            "CpuPriorityClass")


# ---------------------------------------------------------------------------
# BUG #1 — prioridade_total com legado ambíguo é NO-OP seguro (não aborta)
# ---------------------------------------------------------------------------
class TestPrioridadeTotalLegadoAmbiguo(_SandboxIFEO):
    def _sandbox_prioridade(self, current_cpu=V):
        """Isola prioridade_total: sem processos reais, sem reg/backup reais."""
        fake = self._patch_winreg(current_cpu)
        reg_calls = []
        backup_calls = []
        for p in (
            mock.patch.object(sistema, "AIKA_GAME_EXES", {G_EXE}),
            mock.patch.object(sistema, "fazer_backup_registro",
                              side_effect=lambda *a, **k: backup_calls.append(a) or True),
            mock.patch.object(sistema, "executar_comando_seguro",
                              side_effect=lambda *a, **k: reg_calls.append(a) or True),
            mock.patch.object(sistema, "log"),
            mock.patch.object(psutil, "process_iter", return_value=[]),
        ):
            p.start()
            self.addCleanup(p.stop)
        return fake, reg_calls, backup_calls

    def test_01_ambiguo_nao_retorna_false(self):
        self._escrever_reg_legado(V)          # before = 6 (ambíguo)
        self._sandbox_prioridade(current_cpu=V)  # current = 6
        self.assertTrue(sistema.prioridade_total())

    def test_02_nenhum_reg_add_e_nenhum_backup(self):
        self._escrever_reg_legado(V)
        _, reg_calls, backup_calls = self._sandbox_prioridade(current_cpu=V)
        sistema.prioridade_total()
        self.assertEqual(reg_calls, [])
        self.assertEqual(backup_calls, [])

    def test_03_sem_baseline_falsa_e_registry_intacto(self):
        self._escrever_reg_legado(V)
        fake, _, _ = self._sandbox_prioridade(current_cpu=V)
        sistema.prioridade_total()
        self.assertIsNone(self._ler_metadata())          # nenhum ifeo_state.json
        self.assertEqual(self._perf_cpu(fake), (V, REG_DWORD))  # Registry inalterado


def _reg_bytes_legado(exe, cpu):
    """Bytes de backup_prioridade_<exe>.reg (reg export V4.0, UTF-16 LE + BOM)."""
    base = ("HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\"
            "Image File Execution Options\\" + exe)
    linhas = [
        "Windows Registry Editor Version 5.00",
        "",
        "[" + base + "]",
        "",
        "[" + base + "\\PerfOptions]",
        '"CpuPriorityClass"=dword:%08x' % (cpu & 0xFFFFFFFF),
    ]
    texto = "\r\n".join(linhas) + "\r\n"
    return codecs.BOM_UTF16_LE + texto.encode("utf-16-le")


# ---------------------------------------------------------------------------
# BUG #1 — demais cenários (case B/C/D, RESTORE e transação)
# ---------------------------------------------------------------------------
class TestPrioridadeTotalCasos(_SandboxIFEO):
    def _sandbox_prioridade(self, current_cpu=V):
        fake = self._patch_winreg(current_cpu)
        reg_calls = []
        backup_calls = []
        for p in (
            mock.patch.object(sistema, "AIKA_GAME_EXES", {G_EXE}),
            mock.patch.object(sistema, "fazer_backup_registro",
                              side_effect=lambda *a, **k: backup_calls.append(a) or True),
            mock.patch.object(sistema, "executar_comando_seguro",
                              side_effect=lambda *a, **k: reg_calls.append(a) or True),
            mock.patch.object(sistema, "log"),
            mock.patch.object(psutil, "process_iter", return_value=[]),
        ):
            p.start()
            self.addCleanup(p.stop)
        return fake, reg_calls, backup_calls

    def test_01_sem_consumo_do_backup_legado(self):
        self._escrever_reg_legado(V)
        self._sandbox_prioridade(current_cpu=V)
        sistema.prioridade_total()
        self.assertEqual(self._ler_migracoes(), {})

    def test_02_transacao_nao_dispara_rollback(self):
        self._escrever_reg_legado(V)
        self._sandbox_prioridade(current_cpu=V)
        transacao = seguranca.TransacaoSistema()
        resultado = transacao.executar(sistema.prioridade_total)  # não pode lançar
        self.assertTrue(resultado)
        self.assertEqual(transacao.passos_executados, [])

    def test_03_before_6_current_2_captura_baseline_e_aplica(self):
        self._escrever_reg_legado(V)                 # before = 6 (ambíguo)
        _, reg_calls, _ = self._sandbox_prioridade(current_cpu=2)
        self.assertTrue(sistema.prioridade_total())
        ent = self._ler_metadata()["executables"][G_EXE]
        self.assertEqual(ent["values_before"]["CpuPriorityClass"]["value"], 2)
        self.assertTrue(reg_calls)                   # reg add executado

    def test_04_sem_legado_captura_baseline_moderna(self):
        _, reg_calls, _ = self._sandbox_prioridade(current_cpu=2)  # sem .reg legado
        self.assertTrue(sistema.prioridade_total())
        ent = self._ler_metadata()["executables"][G_EXE]
        self.assertEqual(ent["values_before"]["CpuPriorityClass"]["value"], 2)
        self.assertTrue(reg_calls)

    def test_05_falha_real_ao_persistir_continua_bloqueando(self):
        _, reg_calls, _ = self._sandbox_prioridade(current_cpu=2)
        with mock.patch.object(seguranca, "_escrever_ifeo_metadata_atomico",
                               side_effect=OSError("disco cheio")):
            self.assertFalse(sistema.prioridade_total())
        self.assertEqual(reg_calls, [])              # NÃO aplicou reg add

    def test_06_metadata_corrompido_nao_vira_noop(self):
        os.makedirs(self.reg_dir, exist_ok=True)
        with open(self.ifeo_path, "w", encoding="utf-8") as f:
            f.write("{ isto nao e json valido")
        self._escrever_reg_legado(V)
        _, reg_calls, _ = self._sandbox_prioridade(current_cpu=V)
        self.assertFalse(sistema.prioridade_total())
        self.assertEqual(reg_calls, [])

    def test_07_restore_ambiguo_continua_partial(self):
        self._escrever_reg_legado(V)
        self._patch_winreg(V)
        self.assertEqual(seguranca._restaurar_ifeo_ownership(),
                         seguranca.RESTAURACAO_PARCIAL)

    def test_08_restore_ambiguo_nao_cria_baseline_nem_consumo(self):
        self._escrever_reg_legado(V)
        self._patch_winreg(V)
        seguranca._restaurar_ifeo_ownership()
        self.assertIsNone(self._ler_metadata())
        self.assertEqual(self._ler_migracoes(), {})

    def test_09_garantir_retorna_tri_estado_explicito(self):
        self._escrever_reg_legado(V)
        self._patch_winreg(V)
        self.assertEqual(seguranca.garantir_ifeo_ownership(G_EXE),
                         seguranca.IFEO_NOOP)
        self.assertNotEqual(seguranca.IFEO_NOOP, False)
        self.assertNotEqual(seguranca.IFEO_NOOP, True)


# ---------------------------------------------------------------------------
# BUG #2 — timeouts em chamadas externas que podiam ficar penduradas
# ---------------------------------------------------------------------------
class TestTimeoutChamadasExternas(unittest.TestCase):
    @staticmethod
    def _timeout(cmd="x"):
        return subprocess.TimeoutExpired(cmd, 1)

    def test_01_powercfg_getactivescheme_timeout_retorna_none(self):
        with mock.patch("subprocess.check_output", side_effect=self._timeout("powercfg")):
            self.assertIsNone(seguranca.obter_plano_energia_atual())

    def test_02_powercfg_list_timeout_retorna_none(self):
        with mock.patch("subprocess.check_output", side_effect=self._timeout("powercfg")):
            self.assertIsNone(seguranca.obter_planos_energia_disponiveis())

    def test_03_powershell_index_timeout_retorna_none(self):
        with mock.patch("subprocess.check_output", side_effect=self._timeout("powershell")):
            self.assertIsNone(seguranca._resolver_index_por_guid(
                "11111111-2222-3333-4444-555555555555"))

    def test_04_toda_chamada_check_output_tem_timeout_positivo(self):
        vistos = []

        def fake(*a, **k):
            vistos.append(k)
            raise self._timeout("x")

        with mock.patch("subprocess.check_output", side_effect=fake):
            seguranca.obter_plano_energia_atual()
            seguranca.obter_planos_energia_disponiveis()
            seguranca._resolver_index_por_guid("11111111-2222-3333-4444-555555555555")
        self.assertGreaterEqual(len(vistos), 3)
        for k in vistos:
            self.assertIn("timeout", k)
            self.assertGreater(float(k["timeout"]), 0)

    def test_05_timeout_nao_gera_loop_infinito(self):
        with mock.patch("subprocess.check_output", side_effect=self._timeout("powercfg")):
            for _ in range(10):
                self.assertIsNone(seguranca.obter_planos_energia_disponiveis())

    def test_06_powershell_json_tambem_trata_timeout(self):
        with mock.patch("subprocess.check_output", side_effect=self._timeout("powershell")):
            self.assertIsNone(seguranca._executar_powershell_json("Get-NetAdapter"))

    def test_07_constantes_de_timeout_validas(self):
        self.assertGreater(seguranca.POWERCFG_TIMEOUT, 0)
        self.assertGreater(seguranca.PS_QUERY_TIMEOUT, 0)


# ---------------------------------------------------------------------------
# BUG #2 — Otimização Global já roda fora da GUI (TarefaWorker/QThread)
# ---------------------------------------------------------------------------
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


class TestOtimizacaoGlobalForaDaGui(unittest.TestCase):
    def _fake_window(self):
        win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
        win.sinais = _Sinais()
        win.booster_panel = mock.Mock()
        win._suprimir_auto_boost_ate = 0
        tarefas = []
        win.executar_em_background = lambda tarefa, **k: tarefas.append(tarefa) or True
        return win, tarefas

    def test_01_pesado_nao_executa_sincronamente(self):
        win, tarefas = self._fake_window()
        executados = []
        with mock.patch.object(main.opt, "jogo_esta_aberto", return_value=False), \
             mock.patch.object(main.opt, "salvar_snapshot_sistema", return_value=True), \
             mock.patch.object(main.opt, "capturar_estado_sistema", return_value={}), \
             mock.patch.object(main.opt, "modo_desempenho_maximo",
                               side_effect=lambda: executados.append("plano") or "success"), \
             mock.patch.object(main.opt, "prioridade_total",
                               side_effect=lambda: executados.append("prio") or True), \
             mock.patch.object(main.opt, "game_session_optimizer",
                               side_effect=lambda **k: executados.append("gb") or {"status": "completed"}):
            win.iniciar_boost_seguro()
        # Nada pesado rodou na GUI: a tarefa apenas foi enfileirada p/ o worker.
        self.assertEqual(executados, [])
        self.assertEqual(len(tarefas), 1)

    def test_02_animacao_do_gauge_disparada_na_gui(self):
        win, _ = self._fake_window()
        with mock.patch.object(main.opt, "jogo_esta_aberto", return_value=False):
            win.iniciar_boost_seguro()
        win.booster_panel.boost_animation.assert_called_once()

    def test_03_janela_usa_executar_em_background(self):
        fonte = inspect.getsource(main.AikaOptimizerPro.iniciar_boost_seguro)
        self.assertIn("executar_em_background", fonte)
        self.assertIn("tarefa_transacao", fonte)


# ---------------------------------------------------------------------------
# BUG #1 + BUG #2 — fluxo global completo com IFEO legado ambíguo
# ---------------------------------------------------------------------------
class TestFluxoGlobalComIfeoAmbiguo(_SandboxIFEO):
    def _fake_window(self):
        win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
        win.sinais = _Sinais()
        win.booster_panel = mock.Mock()
        win._suprimir_auto_boost_ate = 0
        tarefas = []
        win.executar_em_background = lambda tarefa, **k: tarefas.append(tarefa) or True
        return win, tarefas

    def test_01_alcanca_game_booster_sem_erro_critico(self):
        self._escrever_reg_legado(V)              # before = 6 (ambíguo)
        self._patch_winreg(V)                     # current = 6
        reg_calls = []
        for p in (
            mock.patch.object(sistema, "AIKA_GAME_EXES", {G_EXE}),
            mock.patch.object(sistema, "fazer_backup_registro", return_value=True),
            mock.patch.object(sistema, "executar_comando_seguro",
                              side_effect=lambda *a, **k: reg_calls.append(a) or True),
            mock.patch.object(sistema, "log"),
        ):
            p.start()
            self.addCleanup(p.stop)

        win, tarefas = self._fake_window()
        alcancou = {"gb": False}
        memoria = SimpleNamespace(total=16 * 1024**3, used=8 * 1024**3,
                                  available=8 * 1024**3, percent=50.0)
        resultado_gb = {
            "status": "completed",
            "metricas_antes": {"cpu_percent": 10.0, "ram_percent": 40.0},
            "metricas_depois": {"cpu_percent": 9.0, "ram_percent": 39.0},
            "processos_encerrados": 0, "mem_associada_mb": 0.0,
        }

        def fake_gb(dry_run=False):
            alcancou["gb"] = True
            return resultado_gb

        with mock.patch.object(main.opt, "jogo_esta_aberto", return_value=False), \
             mock.patch.object(main.opt, "salvar_snapshot_sistema", return_value=True), \
             mock.patch.object(main.opt, "capturar_estado_sistema", return_value={}), \
             mock.patch.object(main.opt, "modo_desempenho_maximo", return_value="success"), \
             mock.patch.object(main.opt, "game_session_optimizer", side_effect=fake_gb), \
             mock.patch.object(main.opt, "obter_pasta_jogo_atual", return_value=""), \
             mock.patch.object(main.opt, "iniciar_jogo", return_value=True), \
             mock.patch("psutil.cpu_percent", return_value=3.0), \
             mock.patch("psutil.virtual_memory", return_value=memoria), \
             mock.patch("psutil.process_iter", return_value=[]):
            win.iniciar_boost_seguro()
            self.assertEqual(len(tarefas), 1)
            tarefas.pop(0)()      # executa a tarefa exatamente como o worker

        texto = "\n".join(a[0] for a in win.sinais.log_signal.valores)
        self.assertTrue(alcancou["gb"], "Game Booster precisa ser alcançado")
        self.assertIn("Ativando Game Session Optimizer", texto)
        self.assertNotIn("ERRO CRÍTICO", texto)
        self.assertNotIn("retornou False", texto)
        self.assertEqual(reg_calls, [])           # nenhum reg add (ambiguidade)
        self.assertIsNone(self._ler_metadata())   # nenhuma baseline falsa

    def test_02_fluxo_global_com_modo_desempenho_real(self):
        """Integration: usa o modo_desempenho_maximo REAL (só powercfg é simulado)."""
        self._escrever_reg_legado(V)              # before = 6 (ambíguo)
        self._patch_winreg(V)                     # current = 6
        cmd_calls = []
        for p in (
            mock.patch.object(sistema, "AIKA_GAME_EXES", {G_EXE}),
            mock.patch.object(sistema, "fazer_backup_registro", return_value=True),
            mock.patch.object(sistema, "executar_comando_seguro",
                              side_effect=lambda *a, **k: cmd_calls.append(a) or True),
            mock.patch.object(sistema, "obter_planos_energia_disponiveis",
                              return_value={sistema.GUID_ALTO_DESEMPENHO.lower()}),
            mock.patch.object(sistema, "obter_plano_energia_atual",
                              return_value="00000000-0000-0000-0000-000000000000"),
            mock.patch.object(sistema, "log"),
        ):
            p.start()
            self.addCleanup(p.stop)

        win, tarefas = self._fake_window()
        alcancou = {"gb": False}
        memoria = SimpleNamespace(total=16 * 1024**3, used=8 * 1024**3,
                                  available=8 * 1024**3, percent=50.0)
        resultado_gb = {
            "status": "completed",
            "metricas_antes": {"cpu_percent": 10.0, "ram_percent": 40.0},
            "metricas_depois": {"cpu_percent": 9.0, "ram_percent": 39.0},
            "processos_encerrados": 0, "mem_associada_mb": 0.0,
        }

        def fake_gb(dry_run=False):
            alcancou["gb"] = True
            return resultado_gb

        with mock.patch.object(main.opt, "jogo_esta_aberto", return_value=False), \
             mock.patch.object(main.opt, "salvar_snapshot_sistema", return_value=True), \
             mock.patch.object(main.opt, "capturar_estado_sistema", return_value={}), \
             mock.patch.object(main.opt, "game_session_optimizer", side_effect=fake_gb), \
             mock.patch.object(main.opt, "obter_pasta_jogo_atual", return_value=""), \
             mock.patch.object(main.opt, "iniciar_jogo", return_value=True), \
             mock.patch("psutil.cpu_percent", return_value=3.0), \
             mock.patch("psutil.virtual_memory", return_value=memoria), \
             mock.patch("psutil.process_iter", return_value=[]):
            win.iniciar_boost_seguro()
            self.assertEqual(len(tarefas), 1)
            tarefas.pop(0)()

        texto = "\n".join(a[0] for a in win.sinais.log_signal.valores)
        self.assertTrue(alcancou["gb"], "Game Booster precisa ser alcançado")
        self.assertNotIn("ERRO CRÍTICO", texto)
        self.assertNotIn("retornou False", texto)
        # modo_desempenho_maximo REAL chamou powercfg /setactive; NENHUM reg add.
        reg_add = [c for c in cmd_calls
                   if isinstance(c[0], list) and c[0] and c[0][0] == "reg"]
        self.assertEqual(reg_add, [])
        self.assertIsNone(self._ler_metadata())


# ---------------------------------------------------------------------------
# Serialização do botão / reabilitação após término
# ---------------------------------------------------------------------------
class TestSerializacaoBotao(unittest.TestCase):
    def _obj(self):
        obj = SimpleNamespace()
        obj._shutdown_pending = False
        obj._shutdown_finalizando = False
        obj.tarefa_lock = threading.Lock()
        obj.executando_tarefa = False
        obj.worker = None
        obj.sinais = _Sinais()
        obj._booster_restore_pending = False
        obj._auto_boost_pending = False
        obj.limpar_execucao = lambda: main.AikaOptimizerPro.limpar_execucao(obj)
        return obj

    @staticmethod
    def _fake_worker(_f):
        w = mock.Mock()
        w.finished = mock.Mock()
        w.resultado = mock.Mock()
        w.erro = mock.Mock()
        return w

    def test_01_segunda_otimizacao_rejeitada(self):
        obj = self._obj()
        with mock.patch.object(main, "TarefaWorker", side_effect=self._fake_worker):
            ok1 = main.AikaOptimizerPro.executar_em_background(obj, lambda: 1)
            ok2 = main.AikaOptimizerPro.executar_em_background(obj, lambda: 2)
        self.assertTrue(ok1)
        self.assertFalse(ok2)
        self.assertTrue(obj.executando_tarefa)
        textos = " ".join(a[0] for a in obj.sinais.log_signal.valores)
        self.assertIn("já está em andamento", textos)

    def test_02_limpar_execucao_reabilita(self):
        obj = self._obj()
        with mock.patch.object(main, "TarefaWorker", side_effect=self._fake_worker):
            main.AikaOptimizerPro.executar_em_background(obj, lambda: 1)
            self.assertTrue(obj.executando_tarefa)
            main.AikaOptimizerPro.limpar_execucao(obj)
            self.assertFalse(obj.executando_tarefa)
            ok = main.AikaOptimizerPro.executar_em_background(obj, lambda: 3)
        self.assertTrue(ok)

    def test_03_executar_em_background_respeita_shutdown(self):
        obj = self._obj()
        obj._shutdown_pending = True
        self.assertFalse(main.AikaOptimizerPro.executar_em_background(obj, lambda: 1))


# ---------------------------------------------------------------------------
# Worker: conclusão, erro e ausência de thread pendurada
# ---------------------------------------------------------------------------
class TestTarefaWorkerSinais(unittest.TestCase):
    def test_01_conclusao_sinalizada(self):
        with mock.patch.object(main.opt, "log"):
            w = main.TarefaWorker(lambda: {"ok": True})
            recebidos = []
            w.resultado.connect(lambda r: recebidos.append(r))
            w.run()
        self.assertEqual(recebidos, [{"ok": True}])

    def test_02_excecao_emite_erro_sem_travar(self):
        def boom():
            raise RuntimeError("falha simulada")

        with mock.patch.object(main.opt, "log"):
            w = main.TarefaWorker(boom)
            erros = []
            w.erro.connect(lambda m: erros.append(m))
            w.run()          # não pode propagar exceção (thread não fica pendurada)
        self.assertEqual(erros, ["falha simulada"])


# ---------------------------------------------------------------------------
# TransacaoSistema: rollback reverso e limitado (não bloqueia indefinidamente)
# ---------------------------------------------------------------------------
class TestTransacaoRollback(unittest.TestCase):
    def test_01_rollback_reverso_uma_vez_por_etapa(self):
        passos = []
        t = seguranca.TransacaoSistema()
        t.executar(lambda: True, rollback=lambda: passos.append("rb1"))
        with mock.patch.object(seguranca, "log"):
            with self.assertRaises(RuntimeError):
                t.executar(lambda: False, rollback=lambda: passos.append("rb2"))
        self.assertEqual(passos, ["rb2", "rb1"])

    def test_02_false_aborta_com_runtime_error(self):
        t = seguranca.TransacaoSistema()
        with mock.patch.object(seguranca, "log"):
            with self.assertRaises(RuntimeError):
                t.executar(lambda: False)


# ---------------------------------------------------------------------------
# Invariantes estruturais de responsividade (permitidas para o caso real)
# ---------------------------------------------------------------------------
class TestInvariantesResponsividade(unittest.TestCase):
    def test_01_worker_apenas_emite_signals(self):
        fonte = inspect.getsource(main.AikaOptimizerPro.iniciar_boost_seguro)
        for proibido in ("setText(", "setValue(", "setVisible(", ".append(",
                         "processEvents"):
            self.assertNotIn(proibido, fonte)
        self.assertIn("log_signal.emit", fonte)
        self.assertIn("metrics_signal.emit", fonte)

    def test_02_gauge_animado_por_timer_nao_bloqueante(self):
        fonte = inspect.getsource(main.GaugeWidget.boost_animation)
        self.assertIn("QTimer.singleShot", fonte)

    def test_03_metricas_atualizadas_por_qtimer(self):
        fonte = inspect.getsource(main.AikaOptimizerPro)
        self.assertIn("self.metrics_timer = QTimer(self)", fonte)
        self.assertIn("self.metrics_timer.start(", fonte)


if __name__ == "__main__":
    unittest.main(verbosity=2)




