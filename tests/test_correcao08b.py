# -*- coding: utf-8 -*-
"""Correção 08B — remoção transacional de EF residual no Injetor de Sets."""
import hashlib
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
import main  # noqa: E402
import set_injector as sinj  # noqa: E402
from tests.test_correcao07a import cliente_valido, janela_base  # noqa: E402
from tests.test_validacao07 import (  # noqa: E402
    Sandbox, arquivos_bytes, criar_asset_arma, criar_asset_set, gravar,
)


HASHES_CONGELADOS = {
    "automod.py": "F9422E65FA542D6D5A28CE2E3DD6D025544669601EA2522F42415BDA09E69609",
    "textura.py": "A890FDA024E47C57817F25E5845CE239F5C7F83CF571F1A674F9AD8F426CB8DE",
    "extractor_sets.py": "D3F01604DB2DF2A74FF6D9317FD177A8A3DA42CD92F6769D7B8DF34B21BCD58F",
}


def criar_set(base, set_id, *, partes=("03",), efeitos=(), jit_partes=None,
              derivados=True):
    pasta = criar_asset_set(
        base, set_id, partes=partes, extensoes=(".msh", ".jit"),
        derivados=derivados,
    )
    manifesto_path = pasta / "set_manifest.json"
    manifesto = json.loads(manifesto_path.read_text(encoding="utf-8"))
    if jit_partes is not None:
        permitidas = set(jit_partes)
        novas = []
        for rel in manifesto["files"]["texture"]:
            if Path(rel).suffix.lower() != ".jit":
                novas.append(rel)
                continue
            parte = Path(rel).stem[4:6]
            if parte in permitidas:
                novas.append(rel)
            else:
                (pasta / rel).unlink()
        manifesto["files"]["texture"] = novas
    for parte in efeitos:
        nome = f"CH03{parte}{set_id}EF.jit"
        rel = f"Texture/{nome}"
        gravar(pasta / rel, f"EF-{set_id}-{parte}".encode())
        manifesto["files"]["texture"].append(rel)
    manifesto_path.write_text(json.dumps(manifesto, indent=2), encoding="utf-8")
    return pasta


def remocoes(mapeados):
    return [item for item in mapeados if item.get("action") == "delete"]


def substituicoes(mapeados):
    return [item for item in mapeados if item.get("action", "replace") == "replace"]


class Cenario08B(Sandbox):
    def preparar(self, doador, alvo):
        di = self.validar(doador, "set")
        ai = self.validar(alvo, "set")
        mapeados, ignorados = sinj.criar_mapa_para_infos(di, ai)
        staging = self.root / f"staging_{len(list(self.root.glob('staging_*')))}"
        manifesto, erro = sinj.preparar_set_staging(mapeados, str(staging))
        self.assertIsNone(erro, erro)
        return di, ai, mapeados, ignorados, staging, manifesto

    def cliente_para_infos(self, *infos, nome="ClienteBR"):
        cliente = self.root / nome
        for info in infos:
            for item in info["arquivos"]:
                gravar(
                    cliente / "Data" / item["basename"],
                    b"ORIGINAL-" + item["basename"].encode(),
                )
        return cliente

    def familia(self):
        doador = criar_set(
            self.organizados / "doador", "3801",
            partes=("03", "04", "06", "07", "08"), efeitos=(),
        )
        raiz_alvo = self.organizados / "alvo"
        base = criar_set(
            raiz_alvo, "3001", partes=("03", "04", "06", "07", "08"),
            efeitos=("03", "04", "06", "07", "08"),
        )
        variante = criar_set(
            raiz_alvo, "3002", partes=("03", "04", "07", "08"),
            efeitos=("03", "04", "07", "08"),
        )
        di = self.validar(doador, "set")
        bi = self.validar(base, "set")
        vi = self.validar(variante, "set")
        mapeados, _ = sinj.criar_mapa_para_infos(di, vi)
        staging = self.root / "staging_familia"
        manifesto = None
        if mapeados:
            manifesto, erro = sinj.preparar_set_staging(mapeados, str(staging))
            self.assertIsNone(erro, erro)
        return doador, base, variante, di, bi, vi, mapeados, staging, manifesto

    def restaurar_historico(self, cliente):
        cliente = str(cliente)
        with patch.object(automod, "normalizar_pasta_jogo", side_effect=self.normalize), \
             patch.object(automod, "obter_pasta_backup_cliente", side_effect=self.backup_dir), \
             patch.object(
                 automod, "carregar_historico_automod",
                 side_effect=lambda p=None: json.loads(json.dumps(self.history.get(
                     self.normalize(p),
                     {"version": 2, "game_root": self.normalize(p), "items": {}},
                 ))),
             ), \
             patch.object(automod, "salvar_historico_automod", side_effect=lambda dados, p=None: self._salvar_restore(dados, p)):
            chaves = list(self.history[self.normalize(cliente)]["items"])
            for chave in chaves:
                item = self.history[self.normalize(cliente)]["items"][chave]
                if item.get("operation") == "DELETE":
                    ok, mensagem = sinj.restaurar_ef_removido(chave, cliente)
                else:
                    ok, mensagem = automod.restaurar_mod_individual(chave, cliente)
                self.assertTrue(ok, mensagem)

    def _salvar_restore(self, dados, pasta=None):
        chave = self.normalize(pasta or dados.get("game_root"))
        self.history[chave] = json.loads(json.dumps(dados))
        return True


class TestMapeamentoPorParte(Cenario08B):
    def test_01_doador_com_ef_alvo_com_ef_substitui_sem_remover(self):
        doador = criar_set(self.organizados / "d", "3801", efeitos=("03",))
        alvo = criar_set(self.organizados / "a", "3001", efeitos=("03",))
        _, _, mapa, _, _, _ = self.preparar(doador, alvo)
        self.assertFalse(remocoes(mapa))
        efeitos = [x for x in substituicoes(mapa)
                   if x["alvo"].get("subtipo") == "effect"]
        self.assertEqual(len(efeitos), 1)

    def test_02_doador_sem_ef_alvo_com_ef_agora_e_incompativel(self):
        doador = criar_set(self.organizados / "d", "3801")
        alvo = criar_set(self.organizados / "a", "3001", efeitos=("03",))
        di = self.validar(doador, "set"); ai = self.validar(alvo, "set")
        mapa, ignorados = sinj.criar_mapa_para_infos(di, ai)
        self.assertFalse(mapa)
        self.assertIn("INCOMPATÍVEIS", ignorados[0]["motivo"])

    def test_03_sem_ef_em_ambos_nao_remove(self):
        doador = criar_set(self.organizados / "d", "3801")
        alvo = criar_set(self.organizados / "a", "3001")
        _, _, mapa, _, _, manifesto = self.preparar(doador, alvo)
        self.assertFalse(remocoes(mapa))
        self.assertEqual(manifesto["total_efeitos_remover"], 0)

    def test_04_decisao_por_slot_nao_por_contagem_global(self):
        partes = ("03", "04")
        doador = criar_set(self.organizados / "d", "3801", partes=partes, efeitos=("03",))
        alvo = criar_set(self.organizados / "a", "3001", partes=partes, efeitos=("04",))
        di = self.validar(doador, "set")
        ai = self.validar(alvo, "set")
        self.assertEqual(di["total_effects"], ai["total_effects"])
        mapa, ignorados = sinj.criar_mapa_para_infos(di, ai)
        self.assertFalse(mapa)
        self.assertIn("Parte 03", ignorados[0]["motivo"])
        self.assertIn("Parte 04", ignorados[0]["motivo"])

    def test_05_doador_hibrido_com_divergencia_bloqueia_tudo(self):
        partes = ("03", "04")
        doador = criar_set(self.organizados / "d", "3801", partes=partes, efeitos=("03",))
        alvo = criar_set(self.organizados / "a", "3001", partes=partes, efeitos=partes)
        di = self.validar(doador, "set"); ai = self.validar(alvo, "set")
        mapa, ignorados = sinj.criar_mapa_para_infos(di, ai)
        self.assertFalse(mapa)
        self.assertIn("Parte 04", ignorados[0]["motivo"])

    def test_06_base_01_divergente_bloqueia_sem_remocoes(self):
        _, _, _, _, _, _, mapa, _, _ = self.familia()
        self.assertFalse(mapa)
        self.assertFalse(remocoes(mapa))

    def test_07_variante_divergente_bloqueia_sem_remocoes(self):
        _, _, _, _, _, _, mapa, _, _ = self.familia()
        self.assertFalse(mapa)
        self.assertFalse(remocoes(mapa))


class TestPreparacaoSimulacaoUi(Cenario08B):
    def test_08_preparacao_nao_remove_arquivo_real(self):
        doador = criar_set(self.organizados / "d", "3801")
        alvo = criar_set(self.organizados / "a", "3001", efeitos=("03",))
        antes = arquivos_bytes(alvo)
        di = self.validar(doador, "set"); ai = self.validar(alvo, "set")
        staging = self.root / "staging_incompativel"
        manifesto, _, erro = sinj.SetInjectorWorker().preparar(di, ai, str(staging))
        self.assertEqual(arquivos_bytes(alvo), antes)
        self.assertIsNone(manifesto)
        self.assertIn("INCOMPATÍVEIS", erro)
        self.assertFalse(staging.exists())

    def test_09_simulacao_e_read_only_e_mostra_backup(self):
        doador = criar_set(self.organizados / "d", "3801")
        alvo = criar_set(self.organizados / "a", "3001", efeitos=("03",))
        di = self.validar(doador, "set"); ai = self.validar(alvo, "set")
        mapa, _ = sinj.criar_mapa_para_infos(di, ai)
        cliente = self.cliente_para_infos(ai)
        antes = arquivos_bytes(cliente)
        plano = sinj.simular_injecao(mapa, str(cliente))
        self.assertIn("Simulação bloqueada", plano["erro"])
        self.assertEqual(arquivos_bytes(cliente), antes)

    def test_10_popup_informa_quantidade_de_ef_a_remover(self):
        with tempfile.TemporaryDirectory() as td:
            cliente = main.AikaOptimizerPro._normalizar_cliente_destino_injetor(
                cliente_valido(td, "BR"))
            win = janela_base(cliente, cliente)
            win._inj_mapeados = [
                {"action": "delete", "alvo": {"basename": "aEF.jit"}},
                {"action": "delete", "alvo": {"basename": "bEF.jit"}},
                {"alvo": {"basename": "base.jit"}},
            ]
            win._inj_simulacao_total = 1
            with patch("main.opt.jogo_esta_aberto", return_value=False), \
                 patch("main.QMessageBox.question", return_value=main.QMessageBox.No) as popup:
                win.acao_injetar_set()
        texto = popup.call_args.args[2]
        self.assertNotIn("arquivos de efeito antigos", texto)
        self.assertNotIn("serão removidos", texto)
        self.assertIn(cliente, texto)


class TestTransacaoHistoricoRestore(Cenario08B):
    def cenario(self, partes=("03", "04")):
        doador = criar_set(self.organizados / "d", "3801", partes=partes)
        alvo = criar_set(self.organizados / "a", "3001", partes=partes, efeitos=partes)
        di = self.validar(doador, "set")
        ai = self.validar(alvo, "set")
        mapa, _ = sinj.criar_mapa_doador_alvo(di["arquivos"], ai["arquivos"])
        for alvo_ef in ai["arquivos"]:
            if alvo_ef.get("subtipo") == "effect":
                mapa.append({
                    "action": "delete",
                    "alvo": alvo_ef,
                    "motivo": "operação DELETE legada da 08B",
                })
        staging = self.root / "staging_legado_08b"
        manifesto, erro = sinj.preparar_set_staging(mapa, str(staging))
        self.assertIsNone(erro, erro)
        cliente = self.cliente_para_infos(ai)
        return cliente, ai, mapa, staging

    def test_11_backup_de_todos_ef_antes_da_primeira_remocao(self):
        cliente, _, mapa, staging = self.cenario()
        eventos = []
        backup_real = sinj.fazer_backup_rapido
        remove_real = os.remove
        nomes_ef = {x["alvo"]["basename"] for x in remocoes(mapa)}

        def backup(origem, destino):
            eventos.append(("backup", os.path.basename(origem)))
            return backup_real(origem, destino)

        def remover(caminho):
            if os.path.basename(caminho) in nomes_ef:
                eventos.append(("delete", os.path.basename(caminho)))
            return remove_real(caminho)

        with patch.object(sinj, "fazer_backup_rapido", side_effect=backup), \
             patch.object(sinj.os, "remove", side_effect=remover):
            resultado, erro = sinj.injetar_set(mapa, str(staging), str(cliente))
        self.assertIsNone(erro, erro)
        primeiro_delete = next(i for i, evento in enumerate(eventos) if evento[0] == "delete")
        backups_ef = {nome for tipo, nome in eventos[:primeiro_delete]
                      if tipo == "backup" and nome in nomes_ef}
        self.assertEqual(backups_ef, nomes_ef)
        self.assertEqual(resultado["total_efeitos_removidos"], len(nomes_ef))

    def test_12_backup_falho_de_um_ef_aborta_toda_operacao(self):
        cliente, _, mapa, staging = self.cenario()
        antes = arquivos_bytes(cliente)
        backup_real = sinj.fazer_backup_rapido
        ef_falho = remocoes(mapa)[-1]["alvo"]["basename"]

        def backup(origem, destino):
            if os.path.basename(origem) == ef_falho:
                return False
            return backup_real(origem, destino)

        with patch.object(sinj, "fazer_backup_rapido", side_effect=backup):
            resultado, erro = sinj.injetar_set(mapa, str(staging), str(cliente))
        self.assertIsNone(resultado)
        self.assertIn("Falha ao criar backup", erro)
        self.assertEqual(arquivos_bytes(cliente), antes)
        self.assertFalse(self.history)

    def test_13_commit_remove_ef_fisicamente(self):
        cliente, _, mapa, staging = self.cenario()
        destinos = [cliente / "Data" / x["alvo"]["basename"] for x in remocoes(mapa)]
        resultado, erro = sinj.injetar_set(mapa, str(staging), str(cliente))
        self.assertIsNone(erro, erro)
        self.assertEqual(resultado["total_efeitos_removidos"], len(destinos))
        self.assertTrue(all(not destino.exists() for destino in destinos))

    def test_14_falha_apos_remocao_recria_ef_byte_a_byte(self):
        cliente, _, mapa, staging = self.cenario()
        antes = arquivos_bytes(cliente)
        removidos = []
        remove_real = os.remove
        nomes_ef = {x["alvo"]["basename"] for x in remocoes(mapa)}

        def remover(caminho):
            if os.path.basename(caminho) in nomes_ef:
                removidos.append(caminho)
            return remove_real(caminho)

        with patch.object(sinj.os, "remove", side_effect=remover), \
             patch.object(sinj, "registrar_mod_ativo", return_value=False):
            resultado, erro = sinj.injetar_set(mapa, str(staging), str(cliente))
        self.assertIsNone(resultado)
        self.assertTrue(removidos)
        self.assertIn("rollback OK", erro)
        self.assertEqual(arquivos_bytes(cliente), antes)

    def test_15_falha_na_escrita_de_historico_de_outro_arquivo_restaura_ef(self):
        cliente, _, mapa, staging = self.cenario()
        antes = arquivos_bytes(cliente)
        chamadas = {"n": 0}

        def registrar(*_args, **_kwargs):
            chamadas["n"] += 1
            return chamadas["n"] < 2

        with patch.object(sinj, "registrar_mod_ativo", side_effect=registrar):
            resultado, erro = sinj.injetar_set(mapa, str(staging), str(cliente))
        self.assertIsNone(resultado)
        self.assertIn("histórico", erro)
        self.assertEqual(arquivos_bytes(cliente), antes)

    def test_16_historico_registra_delete(self):
        cliente, _, mapa, staging = self.cenario(partes=("03",))
        resultado, erro = sinj.injetar_set(mapa, str(staging), str(cliente))
        self.assertIsNone(erro, erro)
        itens = self.history[self.normalize(cliente)]["items"]
        chave = os.path.relpath(
            resultado["efeitos_removidos"][0]["destino"], cliente
        ).replace("\\", "/").lower()
        self.assertEqual(itens[chave]["operation"], "DELETE")

    def test_17_restore_recria_ef_com_hash_original(self):
        cliente, _, mapa, staging = self.cenario(partes=("03",))
        ef = cliente / "Data" / remocoes(mapa)[0]["alvo"]["basename"]
        hash_original = hashlib.sha256(ef.read_bytes()).hexdigest()
        resultado, erro = sinj.injetar_set(mapa, str(staging), str(cliente))
        self.assertIsNone(erro, erro)
        self.assertFalse(ef.exists())
        self.restaurar_historico(cliente)
        self.assertTrue(ef.is_file())
        self.assertEqual(hashlib.sha256(ef.read_bytes()).hexdigest(), hash_original)

    def test_18_historico_antigo_sem_operation_continua_restauravel(self):
        cliente = self.root / "ClienteAntigo"
        destino = cliente / "Data" / "CH03033001.jit"
        gravar(destino, b"MODIFICADO")
        backup = Path(self.backup_dir(cliente)) / "Data" / destino.name
        gravar(backup, b"ORIGINAL-ANTIGO")
        chave_cliente = self.normalize(cliente)
        chave_item = "data/ch03033001.jit"
        self.history[chave_cliente] = {
            "version": 2, "game_root": chave_cliente,
            "items": {chave_item: {
                "target_relpath": "Data/CH03033001.jit",
                "backup_relpath": "Data/CH03033001.jit",
                "target_name": destino.name,
            }},
        }
        self.restaurar_historico(cliente)
        self.assertEqual(destino.read_bytes(), b"ORIGINAL-ANTIGO")


class TestRegressoesEIntegridade(Cenario08B):
    def test_19_cliente_destino_explicito_permanece_usado(self):
        doador = criar_set(self.organizados / "d", "3801")
        alvo = criar_set(self.organizados / "a", "3001")
        _, ai, mapa, _, staging, _ = self.preparar(doador, alvo)
        cliente_a = self.cliente_para_infos(ai, nome="ClienteA")
        cliente_b = self.cliente_para_infos(ai, nome="ClienteB")
        antes_a = arquivos_bytes(cliente_a)
        resultado, erro = sinj.injetar_set(mapa, str(staging), str(cliente_b))
        self.assertIsNone(erro, erro)
        self.assertEqual(arquivos_bytes(cliente_a), antes_a)
        self.assertTrue(all(str(cliente_b) in x["destino"]
                            for x in resultado["substituidos"] + resultado["efeitos_removidos"]))

    def test_20_game_open_guard_bloqueia_remocao(self):
        with tempfile.TemporaryDirectory() as td:
            cliente = main.AikaOptimizerPro._normalizar_cliente_destino_injetor(
                cliente_valido(td, "BR"))
            win = janela_base(cliente, cliente)
            win._inj_mapeados = [{"action": "delete", "alvo": {"basename": "aEF.jit"}}]
            with patch("main.opt.jogo_esta_aberto", return_value=True), \
                 patch("main.QMessageBox.warning") as aviso, \
                 patch("main.QMessageBox.question") as popup:
                win.acao_injetar_set()
        aviso.assert_called_once()
        popup.assert_not_called()
        self.assertFalse(win._tarefas)

    def test_21_arma_nao_recebe_acao_delete(self):
        doador = criar_asset_arma(
            self.organizados / "d", "FM", "001", "00001",
            extensoes=(".ms3", ".jit"),
        )
        alvo = criar_asset_arma(
            self.organizados / "a", "FM", "001", "00002",
            extensoes=(".ms3", ".jit", ".ef"),
        )
        di = self.validar(doador, "weapon")
        ai = self.validar(alvo, "weapon")
        mapa, _ = sinj.criar_mapa_para_infos(di, ai)
        self.assertFalse(remocoes(mapa))
        self.assertTrue(all(x["alvo"].get("asset_kind") == "weapon" for x in mapa))

    def test_22_payload_nao_contem_obj_dds_tga_png(self):
        doador = criar_set(self.organizados / "d", "3801", derivados=True)
        alvo = criar_set(self.organizados / "a", "3001", derivados=True)
        _, _, mapa, _, staging, _ = self.preparar(doador, alvo)
        proibidas = {".obj", ".dds", ".tga", ".png"}
        self.assertTrue(all(Path(x["alvo"]["basename"]).suffix.lower() not in proibidas
                            for x in mapa))
        self.assertFalse(any(p.suffix.lower() in proibidas for p in staging.iterdir()))

    def test_23_nucleos_congelados_intactos(self):
        for nome, esperado in HASHES_CONGELADOS.items():
            atual = hashlib.sha256((RAIZ / nome).read_bytes()).hexdigest().upper()
            self.assertEqual(atual, esperado, nome)


class TestSmokeSintetico(Cenario08B):
    def test_24_preparar_simular_injetar_e_restore_familiar(self):
        partes_base = ("03", "04", "06", "07", "08")
        partes_variante = ("03", "04", "07", "08")
        doador = criar_set(
            self.organizados / "doador", "3801", partes=partes_base,
            jit_partes=("03", "04", "06", "07"), efeitos=(),
        )
        raiz_alvo = self.organizados / "alvo"
        base = criar_set(raiz_alvo, "3001", partes=partes_base, efeitos=partes_base)
        variante = criar_set(
            raiz_alvo, "3002", partes=partes_variante, efeitos=partes_variante,
        )
        di = self.validar(doador, "set")
        bi = self.validar(base, "set")
        vi = self.validar(variante, "set")
        self.assertEqual(di["total_meshes"], 5)
        self.assertEqual(di["total_textures"], 4)
        self.assertEqual(di["total_effects"], 0)

        mapa, ignorados = sinj.criar_mapa_para_infos(di, vi)
        staging = self.root / "staging_smoke"
        manifesto, erro = sinj.preparar_set_staging(mapa, str(staging))
        cliente = self.cliente_para_infos(bi, vi, nome="ClienteSmoke")
        originais = arquivos_bytes(cliente)

        plano = sinj.simular_injecao(mapa, str(cliente))
        resultado, erro_injecao = sinj.injetar_set(mapa, str(staging), str(cliente))
        self.assertFalse(mapa)
        self.assertIsNone(manifesto)
        self.assertIn("Preparação bloqueada", erro)
        self.assertIn("Parte 03", ignorados[0]["motivo"])
        self.assertIn("Parte 04", ignorados[0]["motivo"])
        self.assertIn("Parte 07", ignorados[0]["motivo"])
        self.assertIn("Parte 08", ignorados[0]["motivo"])
        self.assertIn("Simulação bloqueada", plano["erro"])
        self.assertIsNone(resultado)
        self.assertIn("Injeção bloqueada", erro_injecao)
        self.assertEqual(arquivos_bytes(cliente), originais)
        self.assertFalse(staging.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)