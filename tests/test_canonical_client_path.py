# -*- coding: utf-8 -*-
"""Correção canônica do cliente AIKA (game_client_path != sets_source_path).

Cobre: validação de cliente, resolvedor canônico, migração legada, separação
de responsabilidades com o Org. Sets, integração com AutoMod/Pedras/Renderizador/
Injetor, UI do card Cliente do AIKA e higiene (nenhum cliente real é tocado).
"""
import inspect
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import automod  # noqa: E402
import config  # noqa: E402
import main  # noqa: E402

from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

_app = QApplication.instance() or QApplication([])


def _criar_cliente(pasta, marcador="coerente"):
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    if marcador == "coerente":
        (pasta / "Mesh").mkdir(exist_ok=True)
        (pasta / "ItemList6.bin").write_bytes(b"x")
    elif marcador == "data":
        (pasta / "Data").mkdir(exist_ok=True)
    elif marcador == "itemlist6":
        (pasta / "ItemList6.bin").write_bytes(b"x")
    elif marcador == "exe":
        (pasta / "aika.exe").write_bytes(b"MZ")
    return str(pasta)


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.br = self.root / "CBMgames" / "AikaOnlineBrasil"
        self.config_file = self.root / "config.json"
        self.backup = self.root / "AikaOptimizer_Backups"
        self._orig = (
            config.ARQUIVO_CONFIG,
            config.PASTA_JOGO_PADRAO,
            config.PASTA_BACKUP,
        )
        config.ARQUIVO_CONFIG = str(self.config_file)
        config.PASTA_JOGO_PADRAO = str(self.br)
        config.PASTA_BACKUP = str(self.backup)
        self._log_patch = mock.patch.object(config, "log", lambda *a, **k: None)
        self._log_patch.start()
        self._automod_log_patch = mock.patch.object(automod, "log", lambda *a, **k: None)
        self._automod_log_patch.start()
        self.resetar()

    def tearDown(self):
        self._log_patch.stop()
        self._automod_log_patch.stop()
        (config.ARQUIVO_CONFIG, config.PASTA_JOGO_PADRAO, config.PASTA_BACKUP) = self._orig
        self.resetar()
        self.temp.cleanup()

    def resetar(self):
        config._config_cache = None
        config._mensagens_recuperacao_cliente.clear()
        config._ultimo_estado_cliente_reportado = None

    def gravar(self, dados):
        self.config_file.write_text(
            json.dumps(dados, ensure_ascii=False), encoding="utf-8"
        )
        self.resetar()

    def ler(self):
        return json.loads(self.config_file.read_text(encoding="utf-8"))


class TestValidacaoCliente(unittest.TestCase):
    def test_pasta_inexistente_rejeitada(self):
        self.assertFalse(config.validar_pasta_cliente_aika(None))
        self.assertFalse(config.validar_pasta_cliente_aika(""))
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(
                config.validar_pasta_cliente_aika(os.path.join(td, "nao_existe"))
            )

    def test_pasta_vazia_invalida(self):
        with tempfile.TemporaryDirectory() as td:
            raiz = Path(td) / "Vazia"
            raiz.mkdir()
            self.assertFalse(config.validar_pasta_cliente_aika(str(raiz)))

    def test_pasta_qualquer_com_data_invalida(self):
        with tempfile.TemporaryDirectory() as td:
            raiz = Path(td) / "ComData"
            (raiz / "Data").mkdir(parents=True)
            self.assertFalse(config.validar_pasta_cliente_aika(str(raiz)))

    def test_pasta_arquivos_comuns_com_data_invalida(self):
        with tempfile.TemporaryDirectory() as td:
            raiz = Path(td) / "Comum"
            (raiz / "Data").mkdir(parents=True)
            (raiz / "arquivo.txt").write_text("x", encoding="utf-8")
            (raiz / "foto.png").write_bytes(b"x")
            self.assertFalse(config.validar_pasta_cliente_aika(str(raiz)))

    def test_executavel_reconhecido_valido(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertTrue(config.validar_pasta_cliente_aika(_criar_cliente(td, "exe")))

    def test_cliente_fixture_minimo_coerente_valido(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertTrue(
                config.validar_pasta_cliente_aika(_criar_cliente(td, "coerente"))
            )

    def test_cliente_privado_outro_exe_suportado_valido(self):
        with tempfile.TemporaryDirectory() as td:
            pasta = Path(td) / "Privado"
            pasta.mkdir(parents=True)
            (pasta / "gameengine.exe").write_bytes(b"MZ")
            self.assertTrue(config.validar_pasta_cliente_aika(str(pasta)))

    def test_itemlist6_sozinho_invalido(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(
                config.validar_pasta_cliente_aika(_criar_cliente(td, "itemlist6"))
            )

    def test_marcador_em_subdiretorio_errado_nao_aceito(self):
        with tempfile.TemporaryDirectory() as td:
            raiz = Path(td) / "Sub"
            (raiz / "subdir").mkdir(parents=True)
            (raiz / "subdir" / "ItemList6.bin").write_bytes(b"x")
            (raiz / "subdir" / "aika.exe").write_bytes(b"MZ")
            self.assertFalse(config.validar_pasta_cliente_aika(str(raiz)))


class TestResolvedorCanonico(Sandbox):
    def test_game_client_path_valido_preferido(self):
        cliente = _criar_cliente(self.root / "ClienteGlobal")
        _criar_cliente(self.br)
        self.gravar({
            "game_client_path": cliente,
            "sets_source_path": str(self.root / "OrigemOrganizada"),
        })
        self.assertEqual(
            config.obter_pasta_jogo_atual(True), str(Path(cliente).resolve())
        )
        self.assertEqual(config.obter_config("game_client_path"), cliente)
        self.assertEqual(
            config.obter_config("sets_source_path"), str(self.root / "OrigemOrganizada")
        )

    def test_pasta_padrao_valida_detectada(self):
        br = _criar_cliente(self.br)
        self.assertEqual(config.obter_pasta_jogo_atual(True), str(Path(br).resolve()))
        self.assertEqual(self.ler()["game_client_path"], br)

    def test_pasta_padrao_invalida_nao_tratada_como_valida(self):
        self.gravar({})
        self.assertIsNone(config.obter_pasta_jogo_atual(True))
        self.assertNotIn("game_client_path", self.ler())

    def test_sets_source_path_continua_independente(self):
        cliente = _criar_cliente(self.root / "ClienteGlobal")
        self.gravar({"game_client_path": cliente})
        self.assertTrue(
            config.definir_config("sets_source_path", str(self.root / "PastaQualquer"))
        )
        self.assertEqual(config.obter_config("game_client_path"), cliente)

    def test_game_client_path_nao_altera_org_sets(self):
        cliente1 = _criar_cliente(self.root / "C1")
        cliente2 = _criar_cliente(self.root / "C2")
        origem = str(self.root / "SetsOrigem")
        self.gravar({"game_client_path": cliente1, "sets_source_path": origem})
        self.assertTrue(config.definir_config("game_client_path", cliente2))
        self.assertEqual(config.obter_config("game_client_path"), cliente2)
        self.assertEqual(config.obter_config("sets_source_path"), origem)

    def test_config_antiga_sem_game_client_path_carrega(self):
        self.gravar({"auto_boost": True})
        self.assertTrue(config.obter_config("auto_boost"))
        self.assertNotIn("game_client_path", self.ler())


class TestMigracaoLegada(Sandbox):
    def test_legado_valido_migra(self):
        cliente = _criar_cliente(self.root / "ClienteLegado")
        self.gravar({"sets_source_path": cliente})
        self.assertEqual(
            config.obter_pasta_jogo_atual(True), str(Path(cliente).resolve())
        )
        cfg = self.ler()
        self.assertEqual(cfg["game_client_path"], cliente)
        self.assertEqual(cfg["sets_source_path"], cliente)

    def test_legado_invalido_nao_migra(self):
        self.gravar({"sets_source_path": str(self.root / "PastaQualquer")})
        self.assertIsNone(config.obter_pasta_jogo_atual(True))
        self.assertNotIn("game_client_path", self.ler())
        self.assertEqual(
            self.ler()["sets_source_path"], str(self.root / "PastaQualquer")
        )

    def test_org_sets_pasta_aleatoria_nao_vira_cliente(self):
        pasta = self.root / "Organizados"
        pasta.mkdir(parents=True)
        (pasta / "set_manifest.json").write_text("{}", encoding="utf-8")
        self.gravar({"sets_source_path": str(pasta)})
        self.assertIsNone(config.obter_pasta_jogo_atual(True))
        self.assertNotIn("game_client_path", self.ler())
        self.assertEqual(self.ler()["sets_source_path"], str(pasta))


class TestFixturesMigracao(Sandbox):
    def test_A_instalacao_nova_fica_nao_configurado(self):
        self.gravar({})
        self.assertIsNone(config.obter_pasta_jogo_atual(True))

    def test_B_instalacao_atual_usa_game_client_path(self):
        cliente = _criar_cliente(self.root / "Atual")
        self.gravar({"game_client_path": cliente})
        self.assertEqual(
            config.obter_pasta_jogo_atual(True), str(Path(cliente).resolve())
        )

    def test_C_instalacao_antiga_migra_com_seguranca(self):
        cliente = _criar_cliente(self.root / "Antiga")
        self.gravar({"sets_source_path": cliente})
        self.assertEqual(
            config.obter_pasta_jogo_atual(True), str(Path(cliente).resolve())
        )
        self.assertEqual(self.ler()["game_client_path"], cliente)

    def test_D_org_sets_nao_confunde_pasta_com_cliente(self):
        pasta = self.root / "Organizacao"
        pasta.mkdir()
        (pasta / "set_manifest.json").write_text("{}", encoding="utf-8")
        self.gravar({"sets_source_path": str(pasta)})
        self.assertIsNone(config.obter_pasta_jogo_atual(True))
        self.assertNotIn("game_client_path", self.ler())


class TestSelecaoManual(Sandbox):
    def test_selecao_manual_valida_persiste(self):
        cliente = _criar_cliente(self.root / "ManualValido")
        self.assertTrue(config.definir_config("game_client_path", cliente))
        self.assertEqual(
            config.obter_pasta_jogo_atual(True), str(Path(cliente).resolve())
        )
        self.assertEqual(self.ler()["game_client_path"], cliente)

    def test_selecao_manual_invalida_nao_persiste(self):
        self.gravar({})
        pasta = self.root / "Aleatoria"
        pasta.mkdir()
        self.assertFalse(config.definir_config("game_client_path", str(pasta)))
        self.assertNotIn("game_client_path", self.ler())

    def test_cancelar_dialog_nao_altera_valor_atual(self):
        cliente = _criar_cliente(self.root / "Atual")
        self.gravar({"game_client_path": cliente})
        win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
        win.atualizar_log = lambda m: None
        win._atualizar_card_cliente_aika = lambda: None
        with mock.patch.object(main.opt, "obter_pasta_jogo_atual", return_value=cliente), \
             mock.patch.object(main.opt, "definir_config") as definir, \
             mock.patch("main.QFileDialog.getExistingDirectory", return_value=""):
            win.selecionar_cliente_aika()
        definir.assert_not_called()


class TestCardUI(unittest.TestCase):
    def _stub(self):
        win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
        win.lbl_cliente_aika_caminho = QLabel("Não configurado")
        win.btn_cliente_aika = QPushButton("SELECIONAR PASTA")
        return win

    def test_ui_mostra_cliente_valido(self):
        with tempfile.TemporaryDirectory() as td:
            pasta = str(Path(td) / "Cliente")
            win = self._stub()
            with mock.patch.object(main.opt, "obter_pasta_jogo_atual", return_value=pasta):
                win._atualizar_card_cliente_aika()
            self.assertEqual(win.btn_cliente_aika.text(), "ALTERAR")
            self.assertEqual(win.lbl_cliente_aika_caminho.toolTip(), pasta)

    def test_ui_mostra_nao_configurado(self):
        win = self._stub()
        with mock.patch.object(main.opt, "obter_pasta_jogo_atual", return_value=None):
            win._atualizar_card_cliente_aika()
        self.assertEqual(win.btn_cliente_aika.text(), "SELECIONAR PASTA")
        self.assertEqual(win.lbl_cliente_aika_caminho.text(), "Não configurado")


class TestIntegracao(Sandbox):
    def test_automod_resolve_fonte_canonica(self):
        cliente = _criar_cliente(self.root / "ClienteGlobal")
        _criar_cliente(self.br)
        self.gravar({
            "game_client_path": cliente,
            "sets_source_path": str(self.root / "Organizados"),
        })
        self.assertEqual(automod._normalizar_pasta_jogo(None), str(Path(cliente).resolve()))

    def test_pedras_resolve_fonte_canonica(self):
        import stone_color_service as svc
        cliente = _criar_cliente(self.root / "ClienteGlobal")
        _criar_cliente(self.br)
        self.gravar({"game_client_path": cliente})
        raiz, alvo = svc.resolve_target(None)
        self.assertEqual(str(raiz), str(Path(cliente).resolve()))
        self.assertEqual(str(alvo), str(Path(cliente).resolve() / "ItemList6.bin"))

    def test_renderizador_resolve_fonte_canonica(self):
        import dgvoodoo_service as dsvc  # noqa: F401
        cliente = _criar_cliente(self.root / "ClienteGlobal")
        _criar_cliente(self.br)
        self.gravar({"game_client_path": cliente})
        self.assertEqual(
            config.obter_pasta_jogo_atual(exigir_existente=True),
            str(Path(cliente).resolve()),
        )
        fonte = (RAIZ / "dgvoodoo_service.py").read_text(encoding="utf-8")
        self.assertIn("config.obter_pasta_jogo_atual", fonte)

    def test_iniciar_jogo_usa_fonte_canonica(self):
        cliente = _criar_cliente(self.root / "ClienteGlobal")
        (Path(cliente) / "aika.exe").write_bytes(b"MZ")
        self.gravar({"game_client_path": cliente})
        with mock.patch("os.startfile") as startfile:
            self.assertTrue(config.iniciar_jogo())
        startfile.assert_called_once()
        self.assertTrue(os.path.normcase(startfile.call_args.args[0]).endswith("aika.exe"))

    def test_injetor_mantem_selecao_propria(self):
        fonte = inspect.getsource(main.AikaOptimizerPro.selecionar_cliente_destino_injetor)
        self.assertNotIn("game_client_path", fonte)
        self.assertNotIn("definir_config", fonte)

    def test_pedras_backend_nao_alterado(self):
        fonte = (RAIZ / "stone_color_service.py").read_text(encoding="utf-8")
        self.assertNotIn("game_client_path", fonte)
        self.assertIn("config.normalizar_pasta_jogo", fonte)
        self.assertIn("def apply_colors", fonte)
        self.assertIn("def recognize_state", fonte)

    def test_dgvoodoo_config_engine_intacto(self):
        fonte = (RAIZ / "dgvoodoo_config_engine.py").read_text(encoding="utf-8")
        self.assertNotIn("game_client_path", fonte)
        self.assertNotIn("validar_pasta_cliente_aika", fonte)
        schema = (RAIZ / "dgvoodoo_config_schema.py").read_text(encoding="utf-8")
        self.assertNotIn("game_client_path", schema)


class TestBypass(Sandbox):
    def _padrao_invalido(self):
        (self.br / "Data").mkdir(parents=True)
        return str(self.br)

    def test_pasta_padrao_inexistente_nenhum_cliente(self):
        self.gravar({})
        self.assertIsNone(config.obter_pasta_jogo_atual(True))

    def test_pasta_padrao_existente_invalida_rejeitada(self):
        self._padrao_invalido()
        self.gravar({})
        self.assertIsNone(config.obter_pasta_jogo_atual(True))
        self.assertNotIn("game_client_path", self.ler())

    def test_pasta_padrao_valida_aceita(self):
        _criar_cliente(self.br)
        self.gravar({})
        self.assertEqual(
            config.obter_pasta_jogo_atual(True), str(Path(self.br).resolve())
        )

    def test_automod_padrao_invalido_bloqueia(self):
        self._padrao_invalido()
        self.gravar({})
        self.assertIsNone(automod._normalizar_pasta_jogo(None))
        self.assertFalse(automod.criar_index_jogo(None))
        self.assertEqual(automod.carregar_index_jogo(None), {})
        self.assertEqual(
            automod.injetar_mods([], None, log_callback=lambda m: None), -1
        )

    def test_pedras_padrao_invalido_bloqueia(self):
        import stone_color_service as svc
        self._padrao_invalido()
        self.gravar({})
        self.assertEqual(svc.resolve_target(None), (None, None))

    def test_renderizador_padrao_invalido_bloqueia(self):
        self._padrao_invalido()
        self.gravar({})
        self.assertIsNone(config.obter_pasta_jogo_atual(exigir_existente=True))

    def test_nenhum_fallback_cru_no_automod(self):
        fonte = (RAIZ / "automod.py").read_text(encoding="utf-8")
        self.assertNotIn("or PASTA_JOGO_PADRAO", fonte)


class TestIsolamento(unittest.TestCase):
    def test_config_json_real_nao_alterado(self):
        repo = os.path.dirname(os.path.abspath(config.__file__))
        real = os.path.join(repo, "config.json")
        before = open(real, "rb").read() if os.path.exists(real) else None
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(config, "ARQUIVO_CONFIG", os.path.join(td, "config.json")), \
                 mock.patch.object(config, "PASTA_BACKUP", os.path.join(td, "backup")), \
                 mock.patch.object(config, "PASTA_JOGO_PADRAO", os.path.join(td, "padrao")), \
                 mock.patch.object(config, "log", lambda *a, **k: None):
                config._config_cache = None
                config._mensagens_recuperacao_cliente.clear()
                config._ultimo_estado_cliente_reportado = None
                config.obter_config("auto_boost", False)
                config._config_cache = None
                config._mensagens_recuperacao_cliente.clear()
                config._ultimo_estado_cliente_reportado = None
        after = open(real, "rb").read() if os.path.exists(real) else None
        self.assertEqual(before, after)


class TestHigiene(unittest.TestCase):
    def test_nenhum_teste_toca_cliente_real(self):
        fonte = (RAIZ / "tests" / "test_canonical_client_path.py").read_text(
            encoding="utf-8"
        )
        for sinal in (r"C:\CBMgames" + "\\AikaOnlineBrasil",
                      r"C:\Users\diego\Downloads" + "\\AikaOnlineBrasil"):
            self.assertNotIn(sinal, fonte)


if __name__ == "__main__":
    unittest.main(verbosity=2)



