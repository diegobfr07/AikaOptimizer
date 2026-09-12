# -*- coding: utf-8 -*-
"""Correção 08C — compatibilidade estrutural efetiva do Injetor de Sets."""
import hashlib
import inspect
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
os.sys.path.insert(0, str(RAIZ))

import main  # noqa: E402
import set_injector as sinj  # noqa: E402
from tests.test_correcao07a import cliente_valido, janela_base  # noqa: E402
from tests.test_correcao08b import (  # noqa: E402
    Cenario08B, criar_set, remocoes,
)
from tests.test_validacao07 import (  # noqa: E402
    arquivos_bytes, criar_asset_arma, criar_asset_set, gravar,
)


PARTES_5 = ("03", "04", "06", "07", "08")
PARTES_4 = ("03", "04", "07", "08")

HASHES_CONGELADOS = {
    "automod.py": "F9422E65FA542D6D5A28CE2E3DD6D025544669601EA2522F42415BDA09E69609",
    "textura.py": "A890FDA024E47C57817F25E5845CE239F5C7F83CF571F1A674F9AD8F426CB8DE",
    "extractor_sets.py": "D3F01604DB2DF2A74FF6D9317FD177A8A3DA42CD92F6769D7B8DF34B21BCD58F",
}


class Cenario08C(Cenario08B):
    def infos(self, doador, alvo):
        return self.validar(doador, "set"), self.validar(alvo, "set")

    def analisar(self, doador, alvo):
        di, ai = self.infos(doador, alvo)
        return di, ai, sinj.analisar_compatibilidade_estrutural(di, ai)

    def familia_alvo(self, *, efeitos=(), jit_partes=PARTES_5):
        raiz = self.organizados / "alvo"
        base = criar_set(
            raiz, "3001", partes=PARTES_5, efeitos=efeitos,
            jit_partes=jit_partes,
        )
        variante = criar_set(
            raiz, "3002", partes=PARTES_4,
            efeitos=tuple(p for p in efeitos if p in PARTES_4),
            jit_partes=tuple(p for p in jit_partes if p in PARTES_4),
        )
        return base, variante

    def familia_compativel(self, *, efeitos=()):
        doador = criar_set(
            self.organizados / "doador", "3801", partes=PARTES_5,
            efeitos=efeitos,
        )
        base, variante = self.familia_alvo(efeitos=efeitos)
        di, bi, vi = (
            self.validar(doador, "set"), self.validar(base, "set"),
            self.validar(variante, "set"),
        )
        return doador, base, variante, di, bi, vi


class TestCompatibilidadePorSlot(Cenario08C):
    def test_01_ef_sim_sim_compativel(self):
        d = criar_set(self.organizados / "d", "3801", efeitos=("03",))
        a = criar_set(self.organizados / "a", "3001", efeitos=("03",))
        _, _, analise = self.analisar(d, a)
        self.assertTrue(analise["compativel"])

    def test_02_ef_nao_nao_compativel(self):
        d = criar_set(self.organizados / "d", "3801")
        a = criar_set(self.organizados / "a", "3001")
        _, _, analise = self.analisar(d, a)
        self.assertTrue(analise["compativel"])

    def test_03_ef_nao_sim_incompativel(self):
        d = criar_set(self.organizados / "d", "3801")
        a = criar_set(self.organizados / "a", "3001", efeitos=("03",))
        _, _, analise = self.analisar(d, a)
        self.assertFalse(analise["compativel"])
        self.assertEqual(analise["divergencias"][0]["campos"], ["ef"])

    def test_04_ef_sim_nao_incompativel(self):
        d = criar_set(self.organizados / "d", "3801", efeitos=("03",))
        a = criar_set(self.organizados / "a", "3001")
        _, _, analise = self.analisar(d, a)
        self.assertFalse(analise["compativel"])
        self.assertEqual(analise["divergencias"][0]["campos"], ["ef"])

    def test_05_por_slot_nao_por_ef_count(self):
        partes = ("03", "04")
        d = criar_set(self.organizados / "d", "3801", partes=partes, efeitos=("03",))
        a = criar_set(self.organizados / "a", "3001", partes=partes, efeitos=("04",))
        di, ai, analise = self.analisar(d, a)
        self.assertEqual(di["total_effects"], ai["total_effects"])
        self.assertFalse(analise["compativel"])
        self.assertEqual({x["slot"] for x in analise["divergencias"]}, {"03", "04"})

    def test_06_hibrido_com_assinaturas_iguais_compativel(self):
        partes = ("03", "04")
        d = criar_set(self.organizados / "d", "3801", partes=partes, efeitos=("03",))
        a = criar_set(self.organizados / "a", "3001", partes=partes, efeitos=("03",))
        _, _, analise = self.analisar(d, a)
        self.assertTrue(analise["compativel"])

    def test_07_hibrido_com_uma_divergencia_bloqueia_tudo(self):
        partes = ("03", "04")
        d = criar_set(self.organizados / "d", "3801", partes=partes, efeitos=("03",))
        a = criar_set(self.organizados / "a", "3001", partes=partes, efeitos=partes)
        di, ai, analise = self.analisar(d, a)
        mapa, ignorados = sinj.criar_mapa_para_infos(di, ai)
        self.assertFalse(analise["compativel"])
        self.assertFalse(mapa)
        self.assertIn("Parte 04", ignorados[0]["motivo"])


class TestEstruturaEfetivaFamilia(Cenario08C):
    def test_08_variante_4_mais_base_resulta_em_5_partes(self):
        _, variante = self.familia_alvo()
        vi = self.validar(variante, "set")
        efetiva = sinj._resolver_estrutura_efetiva(vi)
        self.assertEqual(set(efetiva["estrutura"]), set(PARTES_5))
        self.assertTrue(efetiva["usa_base"])

    def test_09_doador_5_vs_variante_4_mais_base_compativel(self):
        _, _, _, di, _, vi = self.familia_compativel()
        analise = sinj.analisar_compatibilidade_estrutural(di, vi)
        mapa, _ = sinj.criar_mapa_para_infos(di, vi)
        self.assertTrue(analise["compativel"])
        self.assertTrue(mapa)
        self.assertTrue(any(x.get("sincronizacao_base_familia") for x in mapa))

    def test_10_doador_variante_resolve_a_propria_base(self):
        raiz_doador = self.organizados / "doador"
        criar_set(raiz_doador, "3601", partes=PARTES_5)
        doador = criar_set(raiz_doador, "3602", partes=PARTES_4)
        alvo = criar_set(self.organizados / "alvo", "3001", partes=PARTES_5)
        di, ai, analise = self.analisar(doador, alvo)
        mapa, _ = sinj.criar_mapa_para_infos(di, ai)
        self.assertTrue(analise["doador"]["usa_base"])
        self.assertTrue(analise["compativel"])
        self.assertTrue(any(x["doador"]["parte"] == "06" for x in mapa))

    def test_11_base_necessaria_ausente_bloqueia_sem_crash(self):
        doador = criar_set(self.organizados / "d", "3801", partes=PARTES_5)
        alvo = criar_set(self.organizados / "a", "3002", partes=PARTES_4)
        di, ai = self.infos(doador, alvo)
        manifesto, _, erro = sinj.SetInjectorWorker().preparar(
            di, ai, str(self.root / "staging_ausente")
        )
        self.assertIsNone(manifesto)
        self.assertIn("Variante base", erro)
        self.assertIn("INCOMPATÍVEL", erro)

    def test_12_base_de_classe_diferente_nunca_e_usada(self):
        raiz = self.organizados / "alvo"
        criar_asset_set(
            raiz, "3001", classe="04", nome_classe="Atirador",
            partes=PARTES_5, extensoes=(".msh", ".jit"),
        )
        alvo = criar_set(raiz, "3002", partes=PARTES_4)
        doador = criar_set(self.organizados / "d", "3801", partes=PARTES_5)
        di, ai, analise = self.analisar(doador, alvo)
        mapa, _ = sinj.criar_mapa_para_infos(di, ai)
        self.assertFalse(analise["compativel"])
        self.assertIn("outra classe", analise["alvo"]["erro_base"])
        self.assertFalse(mapa)


class TestBloqueiosSemEscrita(Cenario08C):
    def incompativel(self):
        doador = criar_set(self.organizados / "d", "3801")
        alvo = criar_set(self.organizados / "a", "3001", efeitos=("03",))
        return doador, alvo, *self.infos(doador, alvo)

    def test_13_preparacao_incompativel_nao_cria_staging(self):
        _, _, di, ai = self.incompativel()
        staging = self.root / "staging_proibido"
        manifesto, _, erro = sinj.SetInjectorWorker().preparar(di, ai, str(staging))
        self.assertIsNone(manifesto)
        self.assertIn("INCOMPATÍVEIS", erro)
        self.assertFalse(staging.exists())

    def test_14_ui_mantem_simular_e_injetar_desabilitados(self):
        win = janela_base()
        win._inj_preparado = True
        win._inj_mapeados = [{"x": 1}]
        win._inj_staging = "antigo"
        win._atualizar_botoes_injetor = main.AikaOptimizerPro._atualizar_botoes_injetor.__get__(win)
        win._on_injetor_worker_resultado({
            "acao": "preparar",
            "erro": "=== APARÊNCIAS INCOMPATÍVEIS ===\nStatus: INCOMPATÍVEL",
        })
        win._atualizar_botoes_injetor()
        self.assertFalse(win._inj_preparado)
        self.assertFalse(win.btn_simular.enabled)
        self.assertFalse(win.btn_injetar.enabled)

    def test_15_injecao_rejeita_plano_incompativel(self):
        resultado, erro = sinj.injetar_set([], str(self.root / "sem_staging"), str(self.root))
        self.assertIsNone(resultado)
        self.assertIn("Injeção bloqueada", erro)

    def test_16_cliente_permanece_byte_a_byte(self):
        _, _, di, ai = self.incompativel()
        cliente = self.cliente_para_infos(ai)
        antes = arquivos_bytes(cliente)
        manifesto, _, _ = sinj.SetInjectorWorker().preparar(
            di, ai, str(self.root / "staging_proibido")
        )
        self.assertIsNone(manifesto)
        self.assertEqual(arquivos_bytes(cliente), antes)

    def test_17_nenhum_ef_e_deletado_em_nova_operacao(self):
        _, _, di, ai = self.incompativel()
        with patch.object(sinj.os, "remove") as remover:
            manifesto, _, erro = sinj.SetInjectorWorker().preparar(
                di, ai, str(self.root / "staging_proibido")
            )
        self.assertIsNone(manifesto)
        self.assertIn("INCOMPATÍVEIS", erro)
        remover.assert_not_called()

    def test_18_operacao_compativel_sem_ef_nao_cria_delete(self):
        d = criar_set(self.organizados / "d", "3801")
        a = criar_set(self.organizados / "a", "3001")
        di, ai = self.infos(d, a)
        mapa, _ = sinj.criar_mapa_para_infos(di, ai)
        self.assertTrue(mapa)
        self.assertFalse(remocoes(mapa))


class TestCompatibilidadeLegadaERegressoes(Cenario08C):
    def test_19_historico_delete_legado_continua_restauravel(self):
        cliente, _, mapa, staging = self.cenario_legado_delete()
        ef = cliente / "Data" / remocoes(mapa)[0]["alvo"]["basename"]
        original = ef.read_bytes()
        resultado, erro = sinj.injetar_set(mapa, str(staging), str(cliente))
        self.assertIsNone(erro, erro)
        self.assertFalse(ef.exists())
        self.restaurar_historico(cliente)
        self.assertEqual(ef.read_bytes(), original)
        self.assertEqual(resultado["total_efeitos_removidos"], 1)

    def test_20_rollback_delete_legado_recria_bytes(self):
        cliente, _, mapa, staging = self.cenario_legado_delete()
        antes = arquivos_bytes(cliente)
        with patch.object(sinj, "registrar_mod_ativo", return_value=False):
            resultado, erro = sinj.injetar_set(mapa, str(staging), str(cliente))
        self.assertIsNone(resultado)
        self.assertIn("rollback OK", erro)
        self.assertEqual(arquivos_bytes(cliente), antes)

    def cenario_legado_delete(self):
        d = criar_set(self.organizados / "d", "3801")
        a = criar_set(self.organizados / "a", "3001", efeitos=("03",))
        di, ai = self.infos(d, a)
        mapa, _ = sinj.criar_mapa_doador_alvo(di["arquivos"], ai["arquivos"])
        alvo_ef = next(x for x in ai["arquivos"] if x["subtipo"] == "effect")
        mapa.append({"action": "delete", "alvo": alvo_ef, "motivo": "legado 08B"})
        staging = self.root / "staging_delete_legado"
        manifesto, erro = sinj.preparar_set_staging(mapa, str(staging))
        self.assertIsNone(erro, erro); self.assertIsNotNone(manifesto)
        return self.cliente_para_infos(ai), ai, mapa, staging

    def test_21_sincronizacao_base_07b_permanece_funcional(self):
        _, _, _, di, bi, vi = self.familia_compativel()
        staging = self.root / "staging_sync"
        manifesto, _, erro = sinj.SetInjectorWorker().preparar(di, vi, str(staging))
        self.assertIsNone(erro, erro)
        self.assertTrue(manifesto["sincronizacao_base_familia"])
        cliente = self.cliente_para_infos(bi, vi)
        resultado, erro = sinj.injetar_set(
            sinj.criar_mapa_para_infos(di, vi)[0], str(staging), str(cliente)
        )
        self.assertIsNone(erro, erro)
        self.assertGreater(resultado["total_sincronizacao_base"], 0)

    def test_22_cliente_destino_explicito_continua_obrigatorio(self):
        fonte = inspect.getsource(main.AikaOptimizerPro.acao_simular_injecao)
        self.assertIn("_inj_cliente_destino", fonte)
        win = janela_base(cliente=None)
        with patch("main.QMessageBox.warning") as aviso:
            win.acao_simular_injecao()
        aviso.assert_called_once()
        self.assertFalse(win._tarefas)

    def test_23_mudanca_de_cliente_invalida_simulacao(self):
        with tempfile.TemporaryDirectory() as td:
            a = main.AikaOptimizerPro._normalizar_cliente_destino_injetor(cliente_valido(td, "A"))
            b = cliente_valido(td, "B")
            win = janela_base(a, a)
            with patch("main.QFileDialog.getExistingDirectory", return_value=b):
                win.selecionar_cliente_destino_injetor()
        self.assertIsNone(win._inj_cliente_simulado)
        self.assertEqual(win._inj_simulacao_total, 0)

    def test_24_armas_permanecem_inalteradas(self):
        d = criar_asset_arma(self.organizados / "d", "FM", "001", "00001",
                             extensoes=(".ms3", ".jit"))
        a = criar_asset_arma(self.organizados / "a", "FM", "001", "00002",
                             extensoes=(".ms3", ".jit", ".ef"))
        di = self.validar(d, "weapon"); ai = self.validar(a, "weapon")
        mapa, _ = sinj.criar_mapa_para_infos(di, ai)
        self.assertTrue(mapa)
        self.assertFalse(remocoes(mapa))

    def test_25_payload_nao_contem_formatos_derivados(self):
        d = criar_set(self.organizados / "d", "3801", derivados=True)
        a = criar_set(self.organizados / "a", "3001", derivados=True)
        di, ai = self.infos(d, a)
        mapa, _ = sinj.criar_mapa_para_infos(di, ai)
        staging = self.root / "staging_payload"
        manifesto, erro = sinj.preparar_set_staging(mapa, str(staging))
        self.assertIsNone(erro, erro)
        proibidas = {".obj", ".dds", ".tga", ".png"}
        self.assertFalse(any(Path(x["alvo_basename"]).suffix.lower() in proibidas
                             for x in manifesto["files"]))

    def test_26_game_open_guard_permanece_antes_da_injecao(self):
        with tempfile.TemporaryDirectory() as td:
            cliente = main.AikaOptimizerPro._normalizar_cliente_destino_injetor(
                cliente_valido(td, "BR"))
            win = janela_base(cliente, cliente)
            with patch("main.opt.jogo_esta_aberto", return_value=True), \
                 patch("main.QMessageBox.warning") as aviso, \
                 patch("main.QMessageBox.question") as popup:
                win.acao_injetar_set()
        aviso.assert_called_once(); popup.assert_not_called()
        self.assertFalse(win._tarefas)

    def test_27_mensagem_lista_slots_divergentes(self):
        partes = ("03", "04")
        d = criar_set(self.organizados / "d", "3801", partes=partes)
        a = criar_set(self.organizados / "a", "3001", partes=partes, efeitos=partes)
        di, ai = self.infos(d, a)
        manifesto, _, erro = sinj.SetInjectorWorker().preparar(
            di, ai, str(self.root / "staging_mensagem")
        )
        self.assertIsNone(manifesto)
        for texto in ("Parte 03", "Parte 04", "Doador:", "Alvo efetivo:",
                      "EF NÃO", "EF SIM", "Status: INCOMPATÍVEL"):
            self.assertIn(texto, erro)

    def test_28_nucleos_congelados_permanecem_intactos(self):
        for nome, esperado in HASHES_CONGELADOS.items():
            atual = hashlib.sha256((RAIZ / nome).read_bytes()).hexdigest().upper()
            self.assertEqual(atual, esperado, nome)


class TestCasoReal3601Para3002(Cenario08C):
    def test_29_caso_real_bloqueia_quatro_mismatches_ef_com_zero_write(self):
        doador = criar_set(
            self.organizados / "doador", "3601", partes=PARTES_5,
            jit_partes=PARTES_4, efeitos=(),
        )
        raiz_alvo = self.organizados / "alvo"
        base = criar_set(
            raiz_alvo, "3001", partes=PARTES_5,
            jit_partes=PARTES_4, efeitos=PARTES_4,
        )
        variante = criar_set(
            raiz_alvo, "3002", partes=PARTES_4,
            jit_partes=PARTES_4, efeitos=PARTES_4,
        )
        di = self.validar(doador, "set")
        bi = self.validar(base, "set")
        vi = self.validar(variante, "set")
        analise = sinj.analisar_compatibilidade_estrutural(di, vi)
        mapa, ignorados = sinj.criar_mapa_para_infos(di, vi)
        cliente = self.cliente_para_infos(bi, vi, nome="ClienteSintetico")
        antes = arquivos_bytes(cliente)
        staging = self.root / "staging_real"
        manifesto, _, erro = sinj.SetInjectorWorker().preparar(di, vi, str(staging))
        plano = sinj.simular_injecao(mapa, str(cliente))
        resultado, erro_injecao = sinj.injetar_set(mapa, str(staging), str(cliente))

        self.assertFalse(analise["compativel"])
        self.assertEqual({x["slot"] for x in analise["divergencias"]}, set(PARTES_4))
        self.assertTrue(all(x["campos"] == ["ef"] for x in analise["divergencias"]))
        self.assertFalse(mapa); self.assertFalse(remocoes(mapa))
        self.assertIsNone(manifesto); self.assertIn("INCOMPATÍVEIS", erro)
        self.assertIn("Simulação bloqueada", plano["erro"])
        self.assertIsNone(resultado); self.assertIn("Injeção bloqueada", erro_injecao)
        self.assertEqual(arquivos_bytes(cliente), antes)
        self.assertFalse(staging.exists())
        self.assertEqual(ignorados[0]["incompatibilidade"]["divergencias"],
                         analise["divergencias"])


if __name__ == "__main__":
    unittest.main(verbosity=2)