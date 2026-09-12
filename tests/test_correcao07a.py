# -*- coding: utf-8 -*-
"""Correção 07A — Cliente Destino explícito no Injetor."""
import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import main  # noqa: E402


# Atualizado pela Correção 07B: sincronização genérica da base 01 para
# variantes parciais. A suíte 07A continua protegendo o cliente explícito.
HASH_SET_INJECTOR = "D2765BBD157138F6A6AD4DB5997AAF69A212118349CD88257B5BFB2727E00919"
HASH_AUTOMOD = "F9422E65FA542D6D5A28CE2E3DD6D025544669601EA2522F42415BDA09E69609"
HASH_TEXTURA = "A890FDA024E47C57817F25E5845CE239F5C7F83CF571F1A674F9AD8F426CB8DE"
HASH_EXTRACTOR = "D3F01604DB2DF2A74FF6D9317FD177A8A3DA42CD92F6769D7B8DF34B21BCD58F"


class FakeWidget:
    def __init__(self):
        self.textos = []
        self.enabled = None
    def setText(self, texto): self.textos.append(texto)
    def setStyleSheet(self, *_): pass
    def append(self, texto): self.textos.append(texto)
    def setPlainText(self, texto): self.textos = [texto]
    def setEnabled(self, valor): self.enabled = valor


class FakeSignal:
    def __init__(self): self.valores = []
    def emit(self, *args): self.valores.append(args)


class FakeSinais:
    def __init__(self):
        self.log_signal = FakeSignal()
        self.automod_history_signal = FakeSignal()


def janela_base(cliente=None, simulado=None):
    win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
    win._inj_preparado = True
    win._inj_mapeados = [{"alvo": {"basename": "alvo.jit"}}]
    win._inj_staging = "staging"
    win._inj_modo = "set"
    win._inj_cliente_destino = cliente
    win._inj_cliente_simulado = simulado
    win._inj_simulacao_total = 1
    win._inj_doador_info = {"pasta": "Doador Kingdom"}
    win._inj_alvo_info = {"pasta": "Alvo BR"}
    win._inj_busy = False
    win._inj_ignorados = []
    win.sinais = FakeSinais()
    win.terminal_injetor = FakeWidget()
    win.lbl_info_cliente_injetor = FakeWidget()
    win.btn_sel_cliente_injetor = FakeWidget()
    win.rb_inj_sets = FakeWidget(); win.rb_inj_armas = FakeWidget()
    win.btn_sel_doador = FakeWidget(); win.btn_sel_alvo = FakeWidget()
    win.btn_preparar = FakeWidget(); win.btn_simular = FakeWidget(); win.btn_injetar = FakeWidget()
    win._atualizar_botoes_injetor = MagicMock()
    win._tarefas = []
    def executar(acao, mensagem, tarefa): win._tarefas.append((acao, mensagem, tarefa))
    win._executar_operacao_injetor = executar
    return win


def cliente_valido(base, nome):
    pasta = Path(base) / nome
    (pasta / "Objects").mkdir(parents=True)
    (pasta / "Texture").mkdir()
    return str(pasta)


class TestInterfaceEValidacao(unittest.TestCase):
    def test_01_interface_possui_cliente_destino_explicito(self):
        fonte = Path(main.__file__).read_text(encoding="utf-8")
        self.assertIn("CLIENTE DESTINO DA INJEÇÃO", fonte)
        self.assertIn("btn_sel_cliente_injetor", fonte)
        self.assertIn("lbl_info_cliente_injetor", fonte)

    def test_02_preparacao_continua_independente_do_cliente(self):
        fonte = inspect.getsource(main.AikaOptimizerPro.acao_preparar_set)
        self.assertNotIn("_inj_cliente_destino", fonte)
        self.assertIn("worker.preparar", fonte)

    def test_03_simulacao_sem_cliente_e_bloqueada(self):
        win = janela_base()
        with patch("main.QMessageBox.warning") as aviso:
            win.acao_simular_injecao()
        aviso.assert_called_once()
        self.assertIn("Cliente Destino", aviso.call_args.args[2])
        self.assertFalse(win._tarefas)

    def test_04_injecao_sem_cliente_e_bloqueada(self):
        win = janela_base()
        with patch("main.QMessageBox.warning") as aviso, \
             patch("main.QMessageBox.question") as pergunta:
            win.acao_injetar_set()
        aviso.assert_called_once(); pergunta.assert_not_called()
        self.assertFalse(win._tarefas)

    def test_05_pasta_organizada_nao_e_cliente(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "SET AIKA BR" / "Atirador" / "Armas"
            p.mkdir(parents=True)
            cliente, erro = main.AikaOptimizerPro._validar_cliente_destino_injetor(
                str(Path(td) / "SET AIKA BR"))
        self.assertIsNone(cliente)
        self.assertIn("pasta organizada", erro)

    def test_06_cliente_real_plausivel_e_aceito(self):
        with tempfile.TemporaryDirectory() as td:
            esperado = cliente_valido(td, "AIKA BR")
            cliente, erro = main.AikaOptimizerPro._validar_cliente_destino_injetor(esperado)
        self.assertIsNone(erro)
        self.assertEqual(cliente, main.AikaOptimizerPro._normalizar_cliente_destino_injetor(esperado))


class FakeInjectorWorker:
    simulados = []
    injetados = []
    def simular(self, mapeados, cliente):
        self.simulados.append(cliente)
        return ({"pasta_jogo": cliente, "total_indexados": 2, "total": 1,
                 "ignorados": [], "substituicoes": [{
                     "doador_basename": "doador.jit",
                     "alvo_basename": "alvo.jit",
                     "destino_cliente": os.path.join(cliente, "Texture", "alvo.jit"),
                     "caminho_backup": os.path.join(cliente, "backup", "alvo.jit"),
                     "backup_existente": False,
                     "destino_compartilhado": False,
                 }],
                 "total_destinos_compartilhados": 0}, None)
    def injetar(self, mapeados, staging, cliente):
        self.injetados.append(cliente)
        return ({"total_substituidos": 1, "total_falhas": 0,
                 "substituidos": [], "falhas": [],
                 "total_destinos_compartilhados": 0}, None)


class TestOrquestracaoCliente(unittest.TestCase):
    def setUp(self):
        FakeInjectorWorker.simulados.clear(); FakeInjectorWorker.injetados.clear()

    def test_07_doador_kingdom_alvo_br_destinos_usam_br(self):
        with tempfile.TemporaryDirectory() as td:
            br = cliente_valido(td, "BR")
            normal = main.AikaOptimizerPro._normalizar_cliente_destino_injetor(br)
            win = janela_base(normal)
            with patch("main.sinj.SetInjectorWorker", FakeInjectorWorker):
                win.acao_simular_injecao(); payload = win._tarefas[0][2]()
            win._on_injetor_worker_resultado(payload)
        self.assertEqual(FakeInjectorWorker.simulados, [normal])
        self.assertEqual(win._inj_cliente_simulado, normal)
        texto = "\n".join(win.terminal_injetor.textos)
        self.assertIn(f"CLIENTE DESTINO: {normal}", texto)
        self.assertIn(os.path.join(normal, "Texture", "alvo.jit"), texto)

    def test_08_cliente_explicito_br_supera_global_kingdom(self):
        with tempfile.TemporaryDirectory() as td:
            br = cliente_valido(td, "BR"); kingdom = cliente_valido(td, "Kingdom")
            normal_br = main.AikaOptimizerPro._normalizar_cliente_destino_injetor(br)
            win = janela_base(normal_br)
            with patch("main.opt.obter_pasta_jogo_atual", return_value=kingdom) as global_path, \
                 patch("main.sinj.SetInjectorWorker", FakeInjectorWorker):
                win.acao_simular_injecao(); win._tarefas[0][2]()
            global_path.assert_not_called()
        self.assertEqual(FakeInjectorWorker.simulados, [normal_br])

    def test_09_trocar_cliente_invalida_simulacao(self):
        with tempfile.TemporaryDirectory() as td:
            a = cliente_valido(td, "A"); b = cliente_valido(td, "B")
            na = main.AikaOptimizerPro._normalizar_cliente_destino_injetor(a)
            win = janela_base(na, na)
            with patch("main.QFileDialog.getExistingDirectory", return_value=b):
                win.selecionar_cliente_destino_injetor()
        self.assertIsNone(win._inj_cliente_simulado)
        self.assertEqual(win._inj_simulacao_total, 0)
        self.assertTrue(any("simulação novamente" in x for x in win.terminal_injetor.textos))

    def test_10_injecao_apos_troca_e_bloqueada(self):
        with tempfile.TemporaryDirectory() as td:
            a = main.AikaOptimizerPro._normalizar_cliente_destino_injetor(cliente_valido(td,"A"))
            b = main.AikaOptimizerPro._normalizar_cliente_destino_injetor(cliente_valido(td,"B"))
            win = janela_base(b, a)
            with patch("main.QMessageBox.warning") as aviso, \
                 patch("main.QMessageBox.question") as pergunta:
                win.acao_injetar_set()
        aviso.assert_called_once(); pergunta.assert_not_called()
        self.assertIn("simulação", aviso.call_args.args[2])

    def test_11_nova_simulacao_em_b_libera_injecao_em_b(self):
        with tempfile.TemporaryDirectory() as td:
            b = main.AikaOptimizerPro._normalizar_cliente_destino_injetor(cliente_valido(td,"B"))
            win = janela_base(b)
            with patch("main.sinj.SetInjectorWorker", FakeInjectorWorker):
                win.acao_simular_injecao(); payload = win._tarefas.pop()[2]()
                win._on_injetor_worker_resultado(payload)
                with patch("main.opt.jogo_esta_aberto", return_value=False), \
                     patch("main.QMessageBox.question", return_value=main.QMessageBox.Yes):
                    win.acao_injetar_set(); result = win._tarefas.pop()[2]()
        self.assertIsNone(result["erro"])
        self.assertEqual(FakeInjectorWorker.injetados, [b])

    def test_12_backend_recebe_cliente_explicito_para_backup_e_historico(self):
        fonte = inspect.getsource(main.AikaOptimizerPro.acao_injetar_set)
        self.assertIn("worker.injetar(\n                mapeados, staging, cliente_destino", fonte)
        self.assertIn("listar_mods_ativos(cliente_destino)", fonte)
        self.assertNotIn("obter_pasta_jogo_atual", fonte)

    def test_13_popup_mostra_cliente_e_quantidade(self):
        with tempfile.TemporaryDirectory() as td:
            cliente = main.AikaOptimizerPro._normalizar_cliente_destino_injetor(
                cliente_valido(td, "BR"))
            win = janela_base(cliente, cliente); win._inj_simulacao_total = 13
            with patch("main.opt.jogo_esta_aberto", return_value=False), \
                 patch("main.QMessageBox.question", return_value=main.QMessageBox.No) as pergunta:
                win.acao_injetar_set()
        texto = pergunta.call_args.args[2]
        self.assertIn(cliente, texto); self.assertIn("13 arquivos", texto)
        self.assertIn("Backups", texto)

    def test_14_set_usa_cliente_explicito(self):
        self.test_07_doador_kingdom_alvo_br_destinos_usam_br()

    def test_15_arma_usa_mesmo_cliente_explicito(self):
        with tempfile.TemporaryDirectory() as td:
            cliente = main.AikaOptimizerPro._normalizar_cliente_destino_injetor(
                cliente_valido(td, "BR"))
            win = janela_base(cliente); win._inj_modo = "weapon"
            with patch("main.sinj.SetInjectorWorker", FakeInjectorWorker):
                win.acao_simular_injecao(); win._tarefas[0][2]()
        self.assertEqual(FakeInjectorWorker.simulados, [cliente])

    def test_16_base_compartilhada_permanece_no_popup(self):
        fonte = inspect.getsource(main.AikaOptimizerPro.acao_injetar_set)
        self.assertIn("variante-base 01", fonte.lower())
        self.assertIn("destino_compartilhado", fonte)

    def test_17_game_open_guard_permanece(self):
        with tempfile.TemporaryDirectory() as td:
            c = main.AikaOptimizerPro._normalizar_cliente_destino_injetor(
                cliente_valido(td, "BR")); win = janela_base(c,c)
            with patch("main.opt.jogo_esta_aberto", return_value=True), \
                 patch("main.QMessageBox.warning") as aviso, \
                 patch("main.QMessageBox.question") as pergunta:
                win.acao_injetar_set()
        aviso.assert_called_once(); pergunta.assert_not_called(); self.assertFalse(win._tarefas)

    def test_18_worker_threading_permanece(self):
        sim = inspect.getsource(main.AikaOptimizerPro.acao_simular_injecao)
        inj = inspect.getsource(main.AikaOptimizerPro.acao_injetar_set)
        self.assertIn("_executar_operacao_injetor", sim)
        self.assertIn("_executar_operacao_injetor", inj)
        self.assertIn("SetInjectorWorker", sim); self.assertIn("SetInjectorWorker", inj)

    def test_19_set_injector_nao_foi_alterado(self):
        import hashlib
        self.assertEqual(hashlib.sha256((RAIZ/"set_injector.py").read_bytes()).hexdigest().upper(),
                         HASH_SET_INJECTOR)

    def test_20_nucleos_congelados_intactos(self):
        import hashlib
        esperados = {"automod.py": HASH_AUTOMOD, "textura.py": HASH_TEXTURA,
                     "extractor_sets.py": HASH_EXTRACTOR}
        for nome, esperado in esperados.items():
            self.assertEqual(hashlib.sha256((RAIZ/nome).read_bytes()).hexdigest().upper(), esperado)


if __name__ == "__main__":
    unittest.main(verbosity=2)