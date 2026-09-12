# -*- coding: utf-8 -*-
"""Correção 08A — recuperação automática do cliente global."""
import hashlib
import inspect
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import automod  # noqa: E402
import config  # noqa: E402
import main  # noqa: E402


HASHES_CONGELADOS = {
    "automod.py": "F9422E65FA542D6D5A28CE2E3DD6D025544669601EA2522F42415BDA09E69609",
    "textura.py": "A890FDA024E47C57817F25E5845CE239F5C7F83CF571F1A674F9AD8F426CB8DE",
    "extractor_sets.py": "D3F01604DB2DF2A74FF6D9317FD177A8A3DA42CD92F6769D7B8DF34B21BCD58F",
    "set_injector.py": "D2765BBD157138F6A6AD4DB5997AAF69A212118349CD88257B5BFB2727E00919",
}


class FakeSignal:
    def __init__(self):
        self.valores = []

    def emit(self, *args):
        self.valores.append(args)


class FakeSinais:
    def __init__(self):
        self.log_signal = FakeSignal()
        self.automod_history_signal = FakeSignal()


class SandboxConfig(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.br = self.root / "CBMgames" / "AikaOnlineBrasil"
        self.config_file = self.root / "config.json"
        self.backup = self.root / "AikaOptimizer_Backups"
        self._originais = (
            config.ARQUIVO_CONFIG,
            config.PASTA_JOGO_PADRAO,
            config.PASTA_BACKUP,
        )
        config.ARQUIVO_CONFIG = str(self.config_file)
        config.PASTA_JOGO_PADRAO = str(self.br)
        config.PASTA_BACKUP = str(self.backup)
        self._log_patch = patch.object(config, "log", lambda *a, **k: None)
        self._log_patch.start()
        self.resetar_runtime()

    def tearDown(self):
        self._log_patch.stop()
        config.ARQUIVO_CONFIG, config.PASTA_JOGO_PADRAO, config.PASTA_BACKUP = (
            self._originais
        )
        self.resetar_runtime()
        self.temp.cleanup()

    def resetar_runtime(self):
        config._config_cache = None
        config._mensagens_recuperacao_cliente.clear()
        config._ultimo_estado_cliente_reportado = None

    def criar_cliente(self, pasta):
        pasta = Path(pasta)
        (pasta / "Mesh").mkdir(parents=True)
        (pasta / "ItemList6.bin").write_bytes(b"x")
        return str(pasta)

    def gravar_config(self, dados):
        self.config_file.write_text(
            json.dumps(dados, ensure_ascii=False), encoding="utf-8"
        )
        self.resetar_runtime()

    def ler_config(self):
        return json.loads(self.config_file.read_text(encoding="utf-8"))


class TestRecuperacaoClienteGlobal(SandboxConfig):
    def test_01_config_inexistente_br_valido_vira_padrao(self):
        br = self.criar_cliente(self.br)
        self.assertEqual(config.obter_pasta_jogo_atual(True), str(Path(br).resolve()))
        self.assertEqual(self.ler_config()["game_client_path"], br)

    def test_02_config_sem_cliente_br_valido_vira_padrao(self):
        br = self.criar_cliente(self.br)
        self.gravar_config({"auto_boost": True})
        self.assertEqual(config.obter_config("game_client_path"), br)
        self.assertTrue(config.obter_config("auto_boost"))

    def test_03_cliente_salvo_valido_e_preservado(self):
        salvo = self.criar_cliente(self.root / "ClienteSalvo")
        self.criar_cliente(self.br)
        self.gravar_config({"game_client_path": salvo})
        self.assertEqual(config.obter_pasta_jogo_atual(True), str(Path(salvo).resolve()))
        self.assertEqual(self.ler_config()["game_client_path"], salvo)

    def test_04_cliente_privado_valido_nao_e_sobrescrito_pelo_br(self):
        chile = self.criar_cliente(self.root / "AikaChile")
        br = self.criar_cliente(self.br)
        self.gravar_config({"game_client_path": chile})
        self.assertNotEqual(config.obter_pasta_jogo_atual(True), str(Path(br).resolve()))
        self.assertEqual(config.obter_config("game_client_path"), chile)

    def test_05_cliente_stale_com_br_valido_ativa_fallback(self):
        morto = str(self.root / "AikaKingdomRemovido")
        br = self.criar_cliente(self.br)
        self.gravar_config({"game_client_path": morto})
        self.assertEqual(config.obter_pasta_jogo_atual(True), str(Path(br).resolve()))
        logs = "\n".join(config.consumir_mensagens_recuperacao_cliente())
        self.assertIn(morto, logs)
        self.assertIn("Cliente padrão restaurado", logs)

    def test_06_cliente_stale_e_br_ausente_fica_nao_configurado(self):
        morto = str(self.root / "AikaKingdomRemovido")
        self.gravar_config({"game_client_path": morto})
        self.assertIsNone(config.obter_pasta_jogo_atual(True))
        self.assertIsNone(config.obter_config("game_client_path", None))
        logs = "\n".join(config.consumir_mensagens_recuperacao_cliente())
        self.assertIn("Nenhum cliente AIKA válido configurado", logs)

    def test_07_json_malformado_com_br_valido_recupera_sem_crash(self):
        br = self.criar_cliente(self.br)
        self.config_file.write_text('{"game_client_path": ', encoding="utf-8")
        self.resetar_runtime()
        self.assertEqual(config.obter_pasta_jogo_atual(True), str(Path(br).resolve()))
        self.assertEqual(self.ler_config()["game_client_path"], br)

    def test_08_campo_cliente_tipo_invalido_recupera_com_seguranca(self):
        br = self.criar_cliente(self.br)
        self.gravar_config({"game_client_path": ["invalido"], "auto_boost": True})
        self.assertEqual(config.obter_config("game_client_path"), br)
        self.assertTrue(config.obter_config("auto_boost"))

    def test_09_fallback_br_atualiza_persistencia(self):
        morto = str(self.root / "Kingdom")
        br = self.criar_cliente(self.br)
        self.gravar_config({"game_client_path": morto})
        config.obter_pasta_jogo_atual(True)
        persistido = self.ler_config()
        self.assertEqual(persistido["game_client_path"], br)
        self.assertNotIn(morto, json.dumps(persistido))

    def test_10_fallback_remove_estado_stale_do_cliente_anterior(self):
        morto = str(self.root / "Kingdom")
        br = self.criar_cliente(self.br)
        config._config_cache = {"game_client_path": morto, "network_priority": True}
        identidade_antiga = config.identidade_cliente(morto)
        atual = config.obter_pasta_jogo_atual(True)
        self.assertEqual(atual, str(Path(br).resolve()))
        self.assertEqual(config._config_cache["game_client_path"], br)
        self.assertNotEqual(config.identidade_cliente(atual), identidade_antiga)

    def test_11_nenhum_getter_atual_retorna_cliente_antigo(self):
        morto = str(self.root / "Kingdom")
        br = self.criar_cliente(self.br)
        self.gravar_config({"game_client_path": morto})
        atuais = {
            config.obter_config("game_client_path"),
            config.normalizar_pasta_jogo(None),
            config.obter_pasta_jogo_atual(),
            config.obter_pasta_jogo_atual(True),
        }
        self.assertEqual(atuais, {str(Path(br).resolve())})
        self.assertNotIn(morto, atuais)

    def test_12_automod_recebe_br_pelo_fluxo_publico_existente(self):
        morto = str(self.root / "Kingdom")
        br = self.criar_cliente(self.br)
        self.gravar_config({"game_client_path": morto})
        self.assertEqual(automod._normalizar_pasta_jogo(None), str(Path(br).resolve()))

        win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
        win.arquivos_mod_selecionados = [str(self.root / "mod.jit")]
        win.sinais = FakeSinais()
        tarefas = []
        win.executar_em_background = tarefas.append
        recebidos = []
        with patch.object(main.opt, "injetar_mods",
                          side_effect=lambda mods, pasta, **kw: recebidos.append(pasta) or 1), \
             patch.object(main.opt, "listar_mods_ativos", return_value=[]):
            win.acao_injetar_mods()
            tarefas[0]()
        self.assertEqual(recebidos, [str(Path(br).resolve())])

    def test_13_selecao_manual_valida_continua_funcionando(self):
        self.criar_cliente(self.br)
        config.obter_pasta_jogo_atual(True)
        manual = self.criar_cliente(self.root / "ClienteManual")
        self.assertTrue(config.definir_config("game_client_path", manual))
        self.assertEqual(config.obter_pasta_jogo_atual(True), str(Path(manual).resolve()))
        self.assertEqual(self.ler_config()["game_client_path"], manual)

    def test_14_restart_apos_fallback_continua_usando_br(self):
        morto = str(self.root / "Kingdom")
        br = self.criar_cliente(self.br)
        self.gravar_config({"game_client_path": morto})
        config.obter_pasta_jogo_atual(True)
        config._config_cache = None
        config._ultimo_estado_cliente_reportado = None
        self.assertEqual(config.obter_pasta_jogo_atual(True), str(Path(br).resolve()))
        self.assertEqual(self.ler_config()["game_client_path"], br)

    def test_15_outras_configuracoes_validas_sao_preservadas(self):
        self.criar_cliente(self.br)
        self.gravar_config({
            "game_client_path": str(self.root / "Removido"),
            "sets_source_path": str(self.root / "SetsOrigem"),
            "auto_boost": True,
            "close_to_tray": False,
            "sets_output_path": str(self.root / "SetsOrganizados"),
        })
        config.obter_pasta_jogo_atual(True)
        cfg = self.ler_config()
        self.assertTrue(cfg["auto_boost"])
        self.assertFalse(cfg["close_to_tray"])
        self.assertEqual(cfg["sets_output_path"], str(self.root / "SetsOrganizados"))
        self.assertEqual(cfg["sets_source_path"], str(self.root / "SetsOrigem"))

    def test_16_cliente_destino_do_injetor_permanece_independente(self):
        self.criar_cliente(self.br)
        destino_local = self.criar_cliente(self.root / "DestinoLocalInjetor")
        win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
        win._inj_cliente_destino = destino_local
        config.obter_pasta_jogo_atual(True)
        self.assertEqual(win._inj_cliente_destino, destino_local)
        fonte = inspect.getsource(main.AikaOptimizerPro.selecionar_cliente_destino_injetor)
        self.assertNotIn("definir_config", fonte)

    def test_17_nucleos_congelados_permanecem_intactos(self):
        for nome, esperado in HASHES_CONGELADOS.items():
            atual = hashlib.sha256((RAIZ / nome).read_bytes()).hexdigest().upper()
            self.assertEqual(atual, esperado, nome)


if __name__ == "__main__":
    unittest.main(verbosity=2)