# -*- coding: utf-8 -*-
"""Remoção segura de efeitos poluídos e restauração integrada ao histórico."""
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import main  # noqa: E402
import automod  # noqa: E402
import seguranca  # noqa: E402


HASHES_CONGELADOS = {
    "automod.py": "F9422E65FA542D6D5A28CE2E3DD6D025544669601EA2522F42415BDA09E69609",
    "set_injector.py": "D2765BBD157138F6A6AD4DB5997AAF69A212118349CD88257B5BFB2727E00919",
    "textura.py": "A890FDA024E47C57817F25E5845CE239F5C7F83CF571F1A674F9AD8F426CB8DE",
    "extractor_sets.py": "D3F01604DB2DF2A74FF6D9317FD177A8A3DA42CD92F6769D7B8DF34B21BCD58F",
}


def gravar(caminho, dados):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(dados)
    return caminho


class SandboxEfeitos(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.raiz = Path(self._td.name)
        self.cliente = self.raiz / "ClienteTeste"
        self.efeitos = self.cliente / "Data" / "Effect"
        self.efeitos.mkdir(parents=True)
        self.backup = self.raiz / "Backups" / "ClienteTeste"

        def backup_cliente(_pasta_jogo=None, criar=True):
            if criar:
                self.backup.mkdir(parents=True, exist_ok=True)
            return str(self.backup)

        self._patches = [
            patch.object(seguranca, "obter_pasta_backup_cliente",
                         side_effect=backup_cliente),
            patch.object(automod, "obter_pasta_backup_cliente",
                         side_effect=backup_cliente),
            patch.object(main.opt, "obter_pasta_backup_cliente",
                         side_effect=backup_cliente),
        ]
        for remendo in self._patches:
            remendo.start()
            self.addCleanup(remendo.stop)

    def alvo(self, nome, dados):
        return gravar(self.efeitos / nome, dados)

    def backup_de(self, alvo):
        return self.backup / alvo.relative_to(self.cliente)

    def remover(self, nomes, persistir=None):
        return seguranca.remover_arquivos_com_backup(
            str(self.cliente), nomes, persistir_operacao=persistir,
        )


class TestRemocaoTransacional(SandboxEfeitos):
    def test_01_backup_remocao_e_um_id_para_varios_arquivos(self):
        weapon = self.alvo("WeaponEff3.bin", b"WEAPON-ORIGINAL")
        skill = self.alvo("SkillEff.bin", b"SKILL-ORIGINAL")
        capturado = []
        metadados = {
            "operation_id": "remove-polluted-001",
            "operation_type": "REMOVE_POLLUTED_EFFECTS",
            "operation_timestamp": "2026-09-03 10:00:00",
            "operation_source": "WeaponEff3.bin + 1 arquivo(s)",
        }

        def persistir(arquivos):
            capturado.extend(arquivos)
            return main._registrar_remocao_historico(
                str(self.cliente), arquivos, metadados,
            )

        resultado = self.remover(
            {"weaponeff3.bin", "skilleff.bin"}, persistir,
        )

        self.assertEqual(resultado["status"], "removed")
        self.assertFalse(weapon.exists())
        self.assertFalse(skill.exists())
        self.assertEqual(self.backup_de(weapon).read_bytes(), b"WEAPON-ORIGINAL")
        self.assertEqual(self.backup_de(skill).read_bytes(), b"SKILL-ORIGINAL")
        self.assertEqual(len(capturado), 2)
        historico = main.opt.carregar_historico_automod(str(self.cliente))
        itens = list(historico["items"].values())
        self.assertEqual(len(itens), 2)
        self.assertEqual({item["operation_id"] for item in itens},
                         {"remove-polluted-001"})
        self.assertEqual({item["operation_type"] for item in itens},
                         {"REMOVE_POLLUTED_EFFECTS"})
        self.assertEqual({item["operation"] for item in itens}, {"DELETE"})
        self.assertEqual(len(main._agrupar_operacoes_historico(
            main.opt.listar_mods_ativos(str(self.cliente)))), 1)

    def test_02_arquivos_ausentes_sao_noop_sem_historico(self):
        persistir = unittest.mock.Mock(return_value=True)
        resultado = self.remover(seguranca.EFEITOS_POLUIDOS_ARQUIVOS, persistir)
        self.assertEqual(resultado, {
            "status": "already_removed", "files": [], "error": None,
        })
        persistir.assert_not_called()

    def test_03_falha_de_backup_nao_remove_nem_persiste(self):
        weapon = self.alvo("WeaponEff3.bin", b"WEAPON")
        skill = self.alvo("SkillEff.bin", b"SKILL")
        persistir = unittest.mock.Mock(return_value=True)
        real_backup = seguranca.fazer_backup_rapido

        def backup(origem, destino):
            if os.path.basename(origem).lower() == "skilleff.bin":
                return False
            return real_backup(origem, destino)

        with patch.object(seguranca, "fazer_backup_rapido", side_effect=backup):
            resultado = self.remover(
                {"weaponeff3.bin", "skilleff.bin"}, persistir,
            )

        self.assertEqual(resultado["status"], "error")
        self.assertEqual(weapon.read_bytes(), b"WEAPON")
        self.assertEqual(skill.read_bytes(), b"SKILL")
        persistir.assert_not_called()

    def test_04_falha_de_historico_reverte_lote_byte_a_byte(self):
        weapon = self.alvo("WeaponEff3.bin", b"\x00WEAPON\xff")
        skill = self.alvo("SkillEff.bin", b"\x10SKILL\x20")
        antes = {weapon: weapon.read_bytes(), skill: skill.read_bytes()}

        resultado = self.remover(
            {"weaponeff3.bin", "skilleff.bin"}, lambda _arquivos: False,
        )

        self.assertEqual(resultado["status"], "error")
        self.assertIn("rollback OK", resultado["error"])
        for caminho, dados in antes.items():
            self.assertEqual(caminho.read_bytes(), dados)


class TestRestauracaoTransacional(SandboxEfeitos):
    def preparar_remocao_com_historico(self):
        alvo = self.alvo("WeaponEff3.bin", b"ORIGINAL-WEAPON")
        metadados = {
            "operation_id": "remove-polluted-restore",
            "operation_type": "REMOVE_POLLUTED_EFFECTS",
            "operation_timestamp": "2026-09-03 11:00:00",
            "operation_source": "WeaponEff3.bin",
        }

        def persistir(arquivos):
            return main._registrar_remocao_historico(
                str(self.cliente), arquivos, metadados,
            )

        resultado = self.remover({"weaponeff3.bin"}, persistir)
        self.assertEqual(resultado["status"], "removed")
        chave = "data/effect/weaponeff3.bin"
        return alvo, chave

    def test_05_restore_seletivo_recria_e_remove_historico_no_sucesso(self):
        alvo, chave = self.preparar_remocao_com_historico()
        self.assertFalse(alvo.exists())

        resultado = main._restaurar_chaves_historico(
            [chave], str(self.cliente),
        )

        self.assertEqual(resultado["falhas"], [])
        self.assertEqual(resultado["restaurados"], ["WeaponEff3.bin"])
        self.assertEqual(alvo.read_bytes(), b"ORIGINAL-WEAPON")
        historico = main.opt.carregar_historico_automod(str(self.cliente))
        self.assertNotIn(chave, historico["items"])

    def test_06_falha_de_historico_remove_destino_novo_restaurado(self):
        alvo = self.alvo("WeaponEff3.bin", b"ORIGINAL")
        resultado = self.remover({"weaponeff3.bin"})
        self.assertEqual(resultado["status"], "removed")
        self.assertFalse(alvo.exists())

        ok, mensagem = seguranca.restaurar_arquivo_removido(
            "Data/Effect/WeaponEff3.bin", str(self.cliente),
            persistir_historico=lambda: False,
        )

        self.assertFalse(ok)
        self.assertIn("histórico", mensagem)
        self.assertFalse(alvo.exists())

    def test_07_falha_de_historico_reverte_destino_preexistente(self):
        alvo = self.alvo("WeaponEff3.bin", b"ORIGINAL")
        resultado = self.remover({"weaponeff3.bin"})
        self.assertEqual(resultado["status"], "removed")
        gravar(alvo, b"ESTADO-MODIFICADO")

        ok, _mensagem = seguranca.restaurar_arquivo_removido(
            "Data/Effect/WeaponEff3.bin", str(self.cliente),
            persistir_historico=lambda: False,
        )

        self.assertFalse(ok)
        self.assertEqual(alvo.read_bytes(), b"ESTADO-MODIFICADO")

    def test_08_restore_geral_recria_arquivo_removido(self):
        alvo = self.alvo("WeaponEff3.bin", b"ORIGINAL-GERAL")
        resultado = self.remover({"weaponeff3.bin"})
        self.assertEqual(resultado["status"], "removed")

        ok, mensagem = seguranca.restaurar_tudo_jogo(str(self.cliente))

        self.assertTrue(ok, mensagem)
        self.assertEqual(alvo.read_bytes(), b"ORIGINAL-GERAL")


class TestRoteamentoEInterface(unittest.TestCase):
    def test_09_delete_novo_usa_generico_e_delete_ef_usa_legado(self):
        cliente = r"C:\ClienteTeste"
        itens = [
            {
                "chave": "data/effect/weaponeff3.bin",
                "target_relpath": "Data/Effect/WeaponEff3.bin",
                "target_name": "WeaponEff3.bin",
                "operation": "DELETE",
                "operation_type": "REMOVE_POLLUTED_EFFECTS",
            },
            {
                "chave": "data/antigoef.jit",
                "target_relpath": "Data/antigoEF.jit",
                "target_name": "antigoEF.jit",
                "operation": "DELETE",
            },
        ]
        with patch.object(main.opt, "listar_mods_ativos", return_value=itens), \
             patch.object(main.opt, "restaurar_mods_selecionados",
                          return_value={"restaurados": [], "falhas": []}), \
             patch.object(main.opt, "restaurar_arquivo_removido",
                          return_value=(True, "ok")) as generico, \
             patch.object(main.sinj, "restaurar_ef_removido",
                          return_value=(True, "ok")) as legado:
            resultado = main._restaurar_chaves_historico(
                [item["chave"] for item in itens], cliente,
            )

        generico.assert_called_once()
        self.assertEqual(generico.call_args.args[:2],
                         ("Data/Effect/WeaponEff3.bin", cliente))
        self.assertTrue(callable(
            generico.call_args.kwargs["persistir_historico"]))
        legado.assert_called_once_with("data/antigoef.jit", cliente)
        self.assertEqual(resultado["restaurados"],
                         ["antigoEF.jit", "WeaponEff3.bin"])

    def test_10_rotulo_resumo_e_um_card_por_operacao(self):
        arquivos = [
            {"target_name": "SkillEff.bin"},
            {"target_name": "WeaponEff3.bin"},
        ]
        resumo = main._resumo_arquivos_removidos(arquivos)
        itens = []
        for indice, nome in enumerate(("WeaponEff3.bin", "SkillEff.bin")):
            itens.append({
                "chave": f"data/effect/{nome.lower()}",
                "target_relpath": f"Data/Effect/{nome}",
                "target_name": nome,
                "operation": "DELETE",
                "operation_id": "remove-polluted-card",
                "operation_type": "REMOVE_POLLUTED_EFFECTS",
                "operation_timestamp": "2026-09-03 12:00:00",
                "operation_source": resumo,
                "game_root": r"C:\ClienteTeste",
            })
        operacoes = main._agrupar_operacoes_historico(itens)
        self.assertEqual(main._rotulo_tipo_operacao(
            "REMOVE_POLLUTED_EFFECTS"), "REMOVER EFEITOS POLUÍDOS")
        self.assertEqual(resumo, "WeaponEff3.bin + 1 arquivo(s)")
        self.assertEqual(len(operacoes), 1)
        self.assertEqual(len(operacoes[0]["keys"]), 2)
        self.assertEqual(main._subtitulo_operacao(operacoes[0]), resumo)

    def test_11_motores_congelados_permanecem_byte_a_byte(self):
        for nome, esperado in HASHES_CONGELADOS.items():
            atual = hashlib.sha256((RAIZ / nome).read_bytes()).hexdigest().upper()
            self.assertEqual(atual, esperado, nome)

    def test_12_acao_weapon_cria_operacao_e_atualiza_so_no_sucesso(self):
        cliente = r"C:\ClienteTeste"
        arquivo = {
            "target_relpath": "Data/Effect/WeaponEff3.bin",
            "target_name": "WeaponEff3.bin",
        }
        win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
        win.sinais = unittest.mock.Mock()
        win.executar_em_background = lambda tarefa: tarefa()
        metadados = []

        def remover(pasta, nomes, persistir_operacao=None):
            self.assertEqual(pasta, cliente)
            self.assertEqual(nomes, main.opt.EFEITOS_POLUIDOS_ARQUIVOS)
            self.assertTrue(persistir_operacao([arquivo]))
            return {"status": "removed", "files": [arquivo], "error": None}

        def registrar(pasta, arquivos, meta):
            self.assertEqual((pasta, arquivos), (cliente, [arquivo]))
            metadados.append(meta)
            return True

        ativos = [{"chave": "data/effect/weaponeff3.bin"}]
        with patch.object(main.opt, "obter_pasta_jogo_atual",
                          return_value=cliente), \
             patch.object(main.opt, "remover_arquivos_com_backup",
                          side_effect=remover), \
             patch.object(main, "_registrar_remocao_historico",
                          side_effect=registrar), \
             patch.object(main.opt, "listar_mods_ativos",
                          return_value=ativos) as listar, \
             patch.object(main.opt, "remover_efeitos_pesados_aika") as antigo:
            win.acao_weapon()

        self.assertEqual(len(metadados), 1)
        self.assertTrue(metadados[0]["operation_id"].startswith(
            "remove_polluted_effects-"))
        self.assertEqual(metadados[0]["operation_type"],
                         "REMOVE_POLLUTED_EFFECTS")
        self.assertEqual(metadados[0]["operation_source"], "WeaponEff3.bin")
        antigo.assert_not_called()
        listar.assert_called_once_with(cliente)
        win.sinais.automod_history_signal.emit.assert_called_once_with(ativos)

    def test_13_acao_weapon_nao_atualiza_historico_em_noop_ou_erro(self):
        cliente = r"C:\ClienteTeste"
        for resultado in (
            {"status": "already_removed", "files": [], "error": None},
            {"status": "error", "files": [], "error": "falha simulada"},
        ):
            with self.subTest(status=resultado["status"]):
                win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
                win.sinais = unittest.mock.Mock()
                win.executar_em_background = lambda tarefa: tarefa()
                with patch.object(main.opt, "obter_pasta_jogo_atual",
                                  return_value=cliente), \
                     patch.object(main.opt, "remover_arquivos_com_backup",
                                  return_value=resultado), \
                     patch.object(main.opt, "listar_mods_ativos") as listar:
                    win.acao_weapon()
                listar.assert_not_called()
                win.sinais.automod_history_signal.emit.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)