# -*- coding: utf-8 -*-
"""Correção 07B — sincronização genérica da base 01 em variantes parciais."""
import inspect
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
import set_injector as sinj  # noqa: E402
from tests.test_validacao07 import (  # noqa: E402
    Sandbox, criar_asset_set, criar_asset_arma, gravar, arquivos_bytes,
)
from tests.test_correcao07a import janela_base, cliente_valido  # noqa: E402


PARTES_BASE = ("03", "04", "06", "07", "08")
PARTES_VARIANTE = ("03", "04", "07", "08")


class FamilyScenario(Sandbox):
    def familia(self, *, base_parts=PARTES_BASE,
                variant_parts=PARTES_VARIANTE):
        doador = criar_asset_set(
            self.organizados / "doador", "3801", partes=PARTES_BASE)
        raiz_alvo = self.organizados / "alvo"
        base = criar_asset_set(raiz_alvo, "3001", partes=base_parts)
        variante = criar_asset_set(raiz_alvo, "3002", partes=variant_parts)
        di = self.validar(doador, "set")
        bi = self.validar(base, "set")
        vi = self.validar(variante, "set")
        return doador, base, variante, di, bi, vi

    def preparar_familia(self, **kwargs):
        doador, base, variante, di, bi, vi = self.familia(**kwargs)
        staging = self.root / "staging_family"
        manifesto, ignorados, erro = sinj.SetInjectorWorker().preparar(
            di, vi, str(staging))
        self.assertIsNone(erro, erro)
        mapeados, _ = sinj.criar_mapa_para_infos(di, vi)
        return base, variante, bi, vi, staging, manifesto, ignorados, mapeados

    def cliente_familia(self, bi, vi):
        cliente = self.root / "ClienteBR"
        for info in (bi, vi):
            for item in info["arquivos"]:
                gravar(cliente / "Data" / item["basename"],
                       b"ORIGINAL-" + item["basename"].encode())
        return cliente


class TestMapeamentoFamilia(FamilyScenario):
    def test_01_variante_parcial_com_base_mais_completa_ativa_sync(self):
        _, _, _, di, _, vi = self.familia()
        mapeados, ignorados = sinj.criar_mapa_para_infos(di, vi)
        base = [x for x in mapeados if x.get("sincronizacao_base_familia")]
        variante = [x for x in mapeados if not x.get("sincronizacao_base_familia")]
        self.assertTrue(base)
        self.assertTrue(variante)
        self.assertEqual({x["alvo"]["set_destino_fisico"] for x in base}, {"3001"})
        self.assertEqual({x["alvo"]["set_destino_fisico"] for x in variante}, {"3002"})

    def test_02_base_nao_mais_completa_preserva_comportamento_antigo(self):
        _, _, _, di, _, vi = self.familia(
            base_parts=PARTES_VARIANTE, variant_parts=PARTES_VARIANTE)
        mapeados, _ = sinj.criar_mapa_para_infos(di, vi)
        self.assertFalse(any(x.get("sincronizacao_base_familia") for x in mapeados))
        self.assertTrue(all(x["alvo"]["basename"].find("3002") >= 0
                            for x in mapeados))

    def test_03_base_01_selecionada_diretamente_nao_duplica(self):
        _, _, _, di, bi, _ = self.familia()
        mapeados, _ = sinj.criar_mapa_para_infos(di, bi)
        self.assertFalse(any(x.get("sincronizacao_base_familia") for x in mapeados))
        nomes = [x["alvo"]["basename"].lower() for x in mapeados]
        self.assertEqual(len(nomes), len(set(nomes)))

    def test_04_fluxo_arma_permanece_inalterado(self):
        d = criar_asset_arma(self.organizados / "d", "SM", "RIF", "00044")
        a = criar_asset_arma(self.organizados / "a", "SM", "RIF", "00036")
        di, ai = self.validar(d, "weapon"), self.validar(a, "weapon")
        mapeados, ignorados = sinj.criar_mapa_para_infos(di, ai)
        self.assertTrue(mapeados)
        self.assertFalse(any(x.get("sincronizacao_base_familia") for x in mapeados))
        self.assertEqual({x["alvo"]["weapon_id"] if "weapon_id" in x["alvo"] else
                          sinj._identificar_nome_arma(x["alvo"]["basename"])["weapon_id"]
                          for x in mapeados}, {"00036"})

    def test_05_sem_destinos_fisicos_duplicados(self):
        _, _, _, di, _, vi = self.familia()
        mapeados, _ = sinj.criar_mapa_para_infos(di, vi)
        destinos = [x["alvo"]["basename"].lower() for x in mapeados]
        self.assertEqual(len(destinos), len(set(destinos)))

    def test_06_ordem_base_primeiro_variante_depois(self):
        _, _, _, di, _, vi = self.familia()
        mapeados, _ = sinj.criar_mapa_para_infos(di, vi)
        escopos = [x.get("escopo_destino") for x in mapeados]
        ultimo_base = max(i for i, x in enumerate(escopos) if x == "base_familia")
        primeiro_variante = min(i for i, x in enumerate(escopos) if x == "variante_alvo")
        self.assertLess(ultimo_base, primeiro_variante)


class TestStagingSimulacaoInjecao(FamilyScenario):
    def test_07_staging_inclui_base_e_variante(self):
        _, _, _, _, staging, manifesto, _, mapeados = self.preparar_familia()
        self.assertTrue(manifesto["sincronizacao_base_familia"])
        self.assertGreater(manifesto["total_sincronizacao_base"], 0)
        self.assertGreater(manifesto["total_variante_alvo"], 0)
        nomes = {p.name.lower() for p in staging.iterdir() if p.is_file()}
        for item in mapeados:
            self.assertIn(item["alvo"]["basename"].lower(), nomes)

    def test_08_simulacao_resolve_destinos_base_e_variante(self):
        _, _, bi, vi, _, _, _, mapeados = self.preparar_familia()
        cliente = self.cliente_familia(bi, vi)
        plano = sinj.simular_injecao(mapeados, str(cliente))
        self.assertNotIn("erro", plano)
        self.assertTrue(plano["sincronizacao_base_familia"])
        self.assertGreater(plano["total_sincronizacao_base"], 0)
        self.assertGreater(plano["total_variante_alvo"], 0)
        destinos = [x["destino_cliente"] for x in plano["substituicoes"]]
        self.assertTrue(any("3001" in os.path.basename(x) for x in destinos))
        self.assertTrue(any("3002" in os.path.basename(x) for x in destinos))

    def test_09_injecao_recebe_todos_destinos_e_preserva_transacao(self):
        _, _, bi, vi, staging, _, _, mapeados = self.preparar_familia()
        cliente = self.cliente_familia(bi, vi)
        resultado, erro = sinj.injetar_set(mapeados, str(staging), str(cliente))
        self.assertIsNone(erro, erro)
        self.assertEqual(resultado["total_substituidos"], len(mapeados))
        self.assertEqual(resultado["total_sincronizacao_base"],
                         sum(x.get("sincronizacao_base_familia", False)
                             for x in mapeados))
        self.assertGreater(resultado["total_variante_alvo"], 0)
        for item in resultado["substituidos"]:
            self.assertTrue(Path(item["backup"]).is_file())

    def test_10_backup_de_todos_antes_da_primeira_escrita(self):
        _, _, bi, vi, staging, _, _, mapeados = self.preparar_familia()
        cliente = self.cliente_familia(bi, vi)
        eventos = []
        real_backup = sinj.fazer_backup_rapido
        real_write = sinj._copiar_atomico_validado
        def backup(o, d): eventos.append("backup"); return real_backup(o, d)
        def write(o, d, h=None): eventos.append("write"); return real_write(o, d, h)
        with patch.object(sinj, "fazer_backup_rapido", side_effect=backup), \
             patch.object(sinj, "_copiar_atomico_validado", side_effect=write):
            resultado, erro = sinj.injetar_set(mapeados, str(staging), str(cliente))
        self.assertIsNone(erro, erro)
        primeiro_write = eventos.index("write")
        self.assertEqual(eventos[:primeiro_write], ["backup"] * len(mapeados))


class TestUiEClienteExplicito(FamilyScenario):
    def test_11_ui_preparacao_simulacao_resumo_explicitos(self):
        fonte = Path(main.__file__).read_text(encoding="utf-8").lower()
        self.assertIn("sincronização da base da família", fonte)
        self.assertIn("arquivos para a base", fonte)
        self.assertIn("atualizados na variante", fonte)

    def test_12_popup_confirma_base_e_variante(self):
        with tempfile.TemporaryDirectory() as td:
            cliente = main.AikaOptimizerPro._normalizar_cliente_destino_injetor(
                cliente_valido(td, "BR"))
            win = janela_base(cliente, cliente)
            win._inj_mapeados = [{
                "sincronizacao_base_familia": True,
                "destino_compartilhado": True,
                "alvo": {
                    "sincronizacao_base_familia": True,
                    "destino_compartilhado": True,
                },
            }]
            with patch("main.opt.jogo_esta_aberto", return_value=False), \
                 patch("main.QMessageBox.question", return_value=main.QMessageBox.No) as popup:
                win.acao_injetar_set()
        texto = popup.call_args.args[2].lower()
        self.assertIn("sincronização da base da família", texto)
        self.assertIn("base 01", texto)
        self.assertIn("variante alvo", texto)
        self.assertIn("mesma aparência", texto)

    def test_13_cliente_explicito_continua_obrigatorio_e_prioritario(self):
        sim = inspect.getsource(main.AikaOptimizerPro.acao_simular_injecao)
        inj = inspect.getsource(main.AikaOptimizerPro.acao_injetar_set)
        self.assertIn("_inj_cliente_destino", sim)
        self.assertIn("cliente_destino", inj)
        self.assertNotIn("obter_pasta_jogo_atual", sim)
        self.assertNotIn("obter_pasta_jogo_atual", inj)


if __name__ == "__main__":
    unittest.main(verbosity=2)