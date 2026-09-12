# -*- coding: utf-8 -*-
"""
CORREÇÃO CONTROLADA 02 — Testes não destrutivos da aba Performance.

Cobre:
- Cards da aba Performance conectados a callers (A-1);
- Isolar CPU: backend real, 1 CPU, jogo ausente, AccessDenied (A-2);
- MPO: winreg FALSO (nunca toca no Registry real);
- Limpar Cache: TemporaryDirectory (nunca apaga cache real);
- Turbo Boost: conectado ao fluxo canônico iniciar_boost_seguro (sem duplicação);
- Resultado honesto: backend False nunca é exibido como [OK];
- Threading: handlers usam executar_em_background (fora da GUI thread).

NÃO executa: kill real, Registry real, cache real, AIKA, alterações no Windows.
"""
import os
import sys
import types
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import performance  # noqa: E402


# ============================================================
# FAKES
# ============================================================
class FakeSignal:
    def __init__(self):
        self.recebidos = []

    def emit(self, *args):
        self.recebidos.append(args)


class FakeSinais:
    def __init__(self):
        self.log_signal = FakeSignal()

    def textos(self):
        return [r[0] for r in self.log_signal.recebidos if r and isinstance(r[0], str)]

    def tem_ok(self):
        return any("[OK]" in t for t in self.textos())

    def tem_erro(self):
        return any("[ERRO]" in t for t in self.textos())

    def tem_info(self):
        return any("[INFO]" in t for t in self.textos())


class FakeWinRegKey:
    """Substituto de chave HKLM para o MPO (nunca toca no Registry real)."""
    def __init__(self):
        self.valores = {}
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def janela_teste():
    """Cria instância de AikaOptimizerPro SEM __init__ (sem UI real)."""
    import main
    win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
    win.sinais = FakeSinais()
    win._tarefas_submetidas = []

    def fake_executar_em_background(f, resultado_callback=None,
                                    erro_callback=None, finalizado_callback=None):
        win._tarefas_submetidas.append(f)
        return True

    win.executar_em_background = fake_executar_em_background
    return win


# ============================================================
# 1) ESTRUTURA — CARDS POSSUEM CALLERS (A-1)
# ============================================================
class TestEstruturaCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fonte_main = (RAIZ / "main.py").read_text(encoding="utf-8")

    def test_card_glow_possui_signal_clicked(self):
        self.assertIn("clicked = Signal()", self.fonte_main)
        self.assertIn("self.clicked.emit()", self.fonte_main)

    def test_card_mpo_possui_caller(self):
        self.assertIn("card_mpo.clicked.connect(self.acao_desativar_mpo)", self.fonte_main)
        self.assertIn("def acao_desativar_mpo", self.fonte_main)
        self.assertIn("opt.desativar_mpo()", self.fonte_main)

    def test_card_isolar_cpu_possui_caller(self):
        self.assertIn("card_cpu.clicked.connect(self.acao_isolar_cpu)", self.fonte_main)
        self.assertIn("def acao_isolar_cpu", self.fonte_main)
        self.assertIn("opt.otimizar_afinidade_aika()", self.fonte_main)

    def test_card_turbo_boost_conecta_ao_fluxo_canonico(self):
        # Turbo Boost = mesma ação do botão global: sem segundo booster
        self.assertIn("card_turbo.clicked.connect(self.iniciar_boost_seguro)", self.fonte_main)
        # não há novo backend duplicado de Game Booster
        self.assertEqual(self.fonte_main.count("game_session_optimizer("), 1)

    def test_card_limpar_cache_possui_caller(self):
        self.assertIn("card_cache.clicked.connect(self.acao_limpar_cache)", self.fonte_main)
        self.assertIn("def acao_limpar_cache", self.fonte_main)
        self.assertIn("opt.limpar_shader_cache()", self.fonte_main)

    def test_watchdog_nao_aplica_afinidade_automatica(self):
        # A-2 (documentação): watchdog aplica apenas HIGH priority
        self.assertNotIn("+ afinidade (sem CPU 0) automaticamente", self.fonte_main)
        inicio = self.fonte_main.index("def _aplicar_otimizacao")
        fim = self.fonte_main.index("def run", inicio)
        self.assertNotIn("afinidade", self.fonte_main[inicio:fim].lower())


# ============================================================
# 2) HANDLERS — RESULTADO HONESTO E THREADING
# ============================================================
class TestHandlers(unittest.TestCase):
    def setUp(self):
        self.win = janela_teste()
        self.opt = __import__("optimizer")

    def test_mpo_false_nao_e_exibido_como_sucesso(self):
        with patch.object(self.opt, "desativar_mpo", return_value=False):
            self.win.acao_desativar_mpo()
            self.assertEqual(len(self.win._tarefas_submetidas), 1)
            self.win._tarefas_submetidas[-1]()  # executa a tarefa (simulando worker)
            self.assertFalse(self.win.sinais.tem_ok())
            self.assertTrue(self.win.sinais.tem_erro())

    def test_mpo_true_mostra_sucesso(self):
        with patch.object(self.opt, "desativar_mpo", return_value=True):
            self.win.acao_desativar_mpo()
            self.win._tarefas_submetidas[-1]()
            self.assertTrue(self.win.sinais.tem_ok())
            self.assertFalse(self.win.sinais.tem_erro())

    def test_isolar_cpu_com_jogo_fechado_e_tratado(self):
        with patch.object(self.opt, "jogo_esta_aberto", return_value=False), \
             patch.object(self.opt, "otimizar_afinidade_aika") as m:
            self.win.acao_isolar_cpu()
            self.win._tarefas_submetidas[-1]()
            m.assert_not_called()  # backend de afinidade não deve ser acionado
            self.assertTrue(self.win.sinais.tem_info())
            self.assertFalse(self.win.sinais.tem_ok())

    def test_isolar_cpu_backend_false_nao_e_sucesso(self):
        with patch.object(self.opt, "jogo_esta_aberto", return_value=True), \
             patch.object(self.opt, "otimizar_afinidade_aika", return_value=False):
            self.win.acao_isolar_cpu()
            self.win._tarefas_submetidas[-1]()
            self.assertFalse(self.win.sinais.tem_ok())
            self.assertTrue(self.win.sinais.tem_info())

    def test_isolar_cpu_backend_true_mostra_sucesso(self):
        with patch.object(self.opt, "jogo_esta_aberto", return_value=True), \
             patch.object(self.opt, "otimizar_afinidade_aika", return_value=True):
            self.win.acao_isolar_cpu()
            self.win._tarefas_submetidas[-1]()
            self.assertTrue(self.win.sinais.tem_ok())

    def test_limpar_cache_false_nao_e_sucesso(self):
        with patch.object(self.opt, "limpar_shader_cache", return_value=False):
            self.win.acao_limpar_cache()
            self.win._tarefas_submetidas[-1]()
            self.assertFalse(self.win.sinais.tem_ok())
            self.assertTrue(self.win.sinais.tem_erro())

    def test_limpar_cache_true_mostra_sucesso(self):
        with patch.object(self.opt, "limpar_shader_cache", return_value=True):
            self.win.acao_limpar_cache()
            self.win._tarefas_submetidas[-1]()
            self.assertTrue(self.win.sinais.tem_ok())

    def test_handlers_rodam_fora_da_gui_thread(self):
        # Handler deve apenas SUBMETER a tarefa (não executar inline na GUI thread)
        with patch.object(self.opt, "jogo_esta_aberto", return_value=True):
            antes = len(self.win._tarefas_submetidas)
            self.win.acao_isolar_cpu()
            self.assertEqual(len(self.win._tarefas_submetidas), antes + 1)
            self.assertEqual(self.win.sinais.textos(), [])  # nada executado inline


# ============================================================
# 3) BACKEND — ISOLAR CPU (A-2) com psutil FALSO
# ============================================================
class FakeProcAfinidade:
    def __init__(self, afinidade, erro_ao_definir=None):
        self._afinidade = list(afinidade)
        self._erro = erro_ao_definir
        self.definida = None

    def cpu_affinity(self, nova=None):
        if nova is None:
            if isinstance(self._erro, Exception):
                raise self._erro
            return list(self._afinidade)
        if isinstance(self._erro, Exception):
            raise self._erro
        if not nova:  # afinidade vazia NUNCA pode ser aplicada
            raise ValueError("mascara vazia")
        self.definida = list(nova)
        self._afinidade = list(nova)
        return None


class TestAfinidadeCPU(unittest.TestCase):
    def test_aplicar_afinidade_normal_remove_apenas_cpu0(self):
        proc = FakeProcAfinidade([0, 1, 2, 3])
        self.assertTrue(performance.aplicar_afinidade_sem_cpu0(proc))
        self.assertEqual(proc.definida, [1, 2, 3])

    def test_aplicar_afinidade_com_1_cpu_nao_gera_mascara_vazia(self):
        proc = FakeProcAfinidade([0])
        self.assertFalse(performance.aplicar_afinidade_sem_cpu0(proc))
        self.assertIsNone(proc.definida)  # nada foi aplicado

    def test_aplicar_afinidade_ja_otimizada_nao_toca_no_processo(self):
        proc = FakeProcAfinidade([1, 2, 3])
        self.assertFalse(performance.aplicar_afinidade_sem_cpu0(proc))
        self.assertIsNone(proc.definida)

    def test_aplicar_afinidade_access_denied_e_tratado(self):
        import psutil
        proc = FakeProcAfinidade([0, 1], erro_ao_definir=psutil.AccessDenied(pid=1, name="x"))
        self.assertFalse(performance.aplicar_afinidade_sem_cpu0(proc))
        self.assertIsNone(proc.definida)

    def test_aplicar_afinidade_no_such_process_e_tratado(self):
        import psutil
        proc = FakeProcAfinidade([0, 1], erro_ao_definir=psutil.NoSuchProcess(pid=1))
        self.assertFalse(performance.aplicar_afinidade_sem_cpu0(proc))

    def test_otimizar_afinidade_so_toca_processos_do_aika(self):
        import psutil
        import performance as perf
        chamadas = []

        def _aplica(p):
            chamadas.append(p)
            return True

        fake_psutil = types.SimpleNamespace(
            process_iter=lambda fields: [
                types.SimpleNamespace(info={"name": "aika.exe", "pid": 10}),
                types.SimpleNamespace(info={"name": "notepad.exe", "pid": 20}),
            ],
            AccessDenied=psutil.AccessDenied,
            NoSuchProcess=psutil.NoSuchProcess,
        )
        original = perf.aplicar_afinidade_sem_cpu0
        perf.psutil = fake_psutil
        perf.aplicar_afinidade_sem_cpu0 = _aplica
        try:
            resultado = perf.otimizar_afinidade_aika()
        finally:
            perf.aplicar_afinidade_sem_cpu0 = original
            perf.psutil = __import__("psutil")
        self.assertTrue(resultado)
        self.assertEqual(len(chamadas), 1)  # apenas o processo do AIKA


# ============================================================
# 4) BACKEND — MPO com winreg FALSO (nunca Registry real)
# ============================================================
class TestMPO(unittest.TestCase):
    def test_mpo_aplica_valor_com_backup(self):
        fake_wr = types.SimpleNamespace(
            HKEY_LOCAL_MACHINE=0x80000002,
            KEY_SET_VALUE=0x0002,
            REG_DWORD=4,
            OpenKey=lambda hive, chave, reserved, access: FakeWinRegKey(),
            SetValueEx=lambda key, nome, res, tipo, val: key.valores.__setitem__(nome, val),
        )
        with patch.object(performance, "winreg", fake_wr), \
             patch.object(performance, "fazer_backup_registro", return_value=True):
            self.assertTrue(performance.desativar_mpo())

    def test_mpo_sem_backup_falha_sem_escrever(self):
        chamadas = []
        fake_wr = types.SimpleNamespace(
            HKEY_LOCAL_MACHINE=0x80000002, KEY_SET_VALUE=2, REG_DWORD=4,
            OpenKey=lambda *a: FakeWinRegKey(),
            SetValueEx=lambda *a: chamadas.append(a),
        )
        with patch.object(performance, "winreg", fake_wr), \
             patch.object(performance, "fazer_backup_registro", return_value=False):
            self.assertFalse(performance.desativar_mpo())
            self.assertEqual(chamadas, [])

    def test_mpo_erro_de_registro_retorna_false(self):
        def abrir(*a):
            raise PermissionError("acesso negado")
        fake_wr = types.SimpleNamespace(
            HKEY_LOCAL_MACHINE=0x80000002, KEY_SET_VALUE=2, REG_DWORD=4,
            OpenKey=abrir, SetValueEx=lambda *a: None,
        )
        with patch.object(performance, "winreg", fake_wr), \
             patch.object(performance, "fazer_backup_registro", return_value=True):
            self.assertFalse(performance.desativar_mpo())


# ============================================================
# 5) BACKEND — LIMPAR CACHE em TemporaryDirectory (nunca real)
# ============================================================
class TestLimparCache(unittest.TestCase):
    def _ambiente(self, tmp):
        local = tmp / "localappdata"
        (local / "D3DSCache").mkdir(parents=True)
        (local / "D3DSCache" / "a.bin").write_bytes(b"x")
        jogo = tmp / "cliente"
        cache_jogo = jogo / "Data" / "Shaders" / "Cache"
        cache_jogo.mkdir(parents=True)
        (cache_jogo / "s.cso").write_bytes(b"y")
        return local, jogo

    def test_limpa_caches_existentes(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            local, jogo = self._ambiente(tmp)
            with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}), \
                 patch.object(performance, "obter_pasta_jogo_atual", return_value=str(jogo)):
                self.assertTrue(performance.limpar_shader_cache())
            self.assertFalse((local / "D3DSCache").exists())
            self.assertFalse((jogo / "Data" / "Shaders" / "Cache").exists())

    def test_nada_encontrado_retorna_true_sem_erro(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            local = tmp / "localappdata"
            local.mkdir()
            jogo = tmp / "cliente"
            jogo.mkdir()
            with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}), \
                 patch.object(performance, "obter_pasta_jogo_atual", return_value=str(jogo)):
                self.assertTrue(performance.limpar_shader_cache())

    def test_pasta_bloqueada_nao_e_sucesso(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            local, jogo = self._ambiente(tmp)

            def rmtree_falho(p, *a, **k):
                # simula arquivos em uso: não remove nada
                return None

            with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}), \
                 patch.object(performance, "obter_pasta_jogo_atual", return_value=str(jogo)), \
                 patch.object(performance.shutil, "rmtree", rmtree_falho):
                self.assertFalse(performance.limpar_shader_cache())
            # diretórios continuam lá (nada foi apagado de verdade)
            self.assertTrue((local / "D3DSCache").exists())
            self.assertTrue((jogo / "Data" / "Shaders" / "Cache").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)




