# -*- coding: utf-8 -*-
"""Correção 06A — observabilidade do Organizador, sem alterar conversores."""
import hashlib
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

import extractor_sets as exts  # noqa: E402
from tests.test_validacao06 import msh_bytes, ms3_bytes, jt31_bytes, gravar  # noqa: E402


HASH_MSH_ANTES = "c569eb530cdac2edd0926e015ad811a3bc37affdcf4acc0057da923ed81ff248"
# Atualizado pela Release Hygiene: o cabeçalho OBJ agora usa a versão canônica
# (config.VERSAO_APLICATIVO) em vez de "V4.0" hardcoded. JIT continua congelado.
HASH_MS3_ANTES = "2d086d454f770b99cc2286263b65399084848f70ce7b368506cb597f8f3010c6"
HASH_JIT_ANTES = "73187558f8f3480412d4a61d94a8c4e10c9634f49907e7e8c8b79d9eafcbc450"


def hash_funcao(funcao):
    return hashlib.sha256(inspect.getsource(funcao).encode()).hexdigest()


def executar_com_arquivo(nome, dados, *, extrair_3d=True, extrair_tex=True,
                         cancel_callback=None):
    td = tempfile.TemporaryDirectory()
    origem = Path(td.name) / "origem"
    destino = Path(td.name) / "destino"
    origem.mkdir()
    gravar(origem / nome, dados)
    logs = []
    stats = exts.organizar_e_converter_aika(
        str(origem), str(destino), False, extrair_3d, extrair_tex,
        cancel_callback=cancel_callback, log_callback=logs.append,
    )
    return td, stats, logs


class TestFalhasIndividuais(unittest.TestCase):
    def test_01_falha_msh_contem_nome_e_motivo(self):
        with patch.object(exts, "convert_msh_to_obj",
                          return_value=(False, "índice de face fora da faixa")):
            td, stats, logs = executar_com_arquivo("CH03031101.msh", msh_bytes())
            self.addCleanup(td.cleanup)
        linha = next(item for item in logs if "[ERRO][MSH->OBJ]" in item)
        self.assertIn("CH03031101.msh", linha)
        self.assertIn("índice de face fora da faixa", linha)
        self.assertEqual(stats["falhas_3d"], 1)

    def test_02_falha_ms3_contem_nome_e_motivo(self):
        with patch.object(exts, "convert_ms3_to_obj",
                          return_value=(False, "formato/layout não reconhecido")):
            td, stats, logs = executar_com_arquivo("SMABC12345.ms3", ms3_bytes())
            self.addCleanup(td.cleanup)
        linha = next(item for item in logs if "[ERRO][MS3->OBJ]" in item)
        self.assertIn("SMABC12345.ms3", linha)
        self.assertIn("formato/layout não reconhecido", linha)
        self.assertEqual(stats["falhas_3d"], 1)

    def test_03_exception_global_expoe_tipo_etapa_arquivo_e_motivo(self):
        with patch.object(exts, "_copiar_se_necessario",
                          side_effect=PermissionError("acesso negado")):
            td, stats, logs = executar_com_arquivo(
                "CH03031101.msh", msh_bytes(), extrair_3d=False)
            self.addCleanup(td.cleanup)
        self.assertIn("erro", stats)
        linha = next(item for item in logs if "[ERRO][COPY]" in item)
        self.assertIn("CH03031101.msh", linha)
        self.assertIn("PermissionError", linha)
        self.assertIn("acesso negado", linha)

    def test_04_false_sem_motivo_ainda_gera_mensagem_minima(self):
        with patch.object(exts, "convert_msh_to_obj", return_value=(False, "")):
            td, _, logs = executar_com_arquivo("CH03031101.msh", msh_bytes())
            self.addCleanup(td.cleanup)
        linha = next(item for item in logs if "[ERRO][MSH->OBJ]" in item)
        self.assertIn("conversão recusada pelo backend", linha)

    def test_05_falha_jit_e_logada_com_nome_e_motivo(self):
        with patch.object(exts, "extrair_textura_jit",
                          return_value=(False, "formato de textura não reconhecido")):
            td, stats, logs = executar_com_arquivo(
                "CH03031101.jit", jt31_bytes(), extrair_3d=False)
            self.addCleanup(td.cleanup)
        linha = next(item for item in logs if "[ERRO][JIT]" in item)
        self.assertIn("CH03031101.jit", linha)
        self.assertIn("formato de textura não reconhecido", linha)
        self.assertEqual(stats["jit_extraidos"], 0)


class TestCancelamentoResumoRuido(unittest.TestCase):
    def test_06_cancelamento_e_info_e_nunca_erro(self):
        td, stats, logs = executar_com_arquivo(
            "CH03031101.msh", msh_bytes(), cancel_callback=lambda: True)
        self.addCleanup(td.cleanup)
        cancel_logs = [item for item in logs if "cancelada pelo usuário" in item]
        self.assertEqual(cancel_logs, ["[INFO] Organização cancelada pelo usuário."])
        self.assertTrue(stats["cancelado"])
        self.assertFalse(any("[ERRO]" in item for item in cancel_logs))
        self.assertFalse(any("Organização concluída" in item for item in logs))

    def test_07_resumo_final_contem_todos_os_contadores_relevantes(self):
        td, stats, logs = executar_com_arquivo(
            "CH03031101.msh", msh_bytes(), extrair_tex=False)
        self.addCleanup(td.cleanup)
        esperados = (
            "[OK] Organização concluída.",
            f"[INFO] Arquivos organizados: {stats['copiados']}",
            f"[INFO] Armaduras 3D: {stats['msh_convertidos']}",
            f"[INFO] Armas 3D: {stats['ms3_convertidos']}",
            f"[INFO] Famílias organizadas: {stats['familias_criadas']}",
            f"[INFO] Pastas antigas agrupadas: {stats['pastas_legadas_migradas']}",
            f"[INFO] Texturas extraídas: {stats['jit_extraidos']}",
            f"[INFO] Falhas de Conversão 3D: {stats['falhas_3d']}",
        )
        for linha in esperados:
            self.assertIn(linha, logs)

    def test_08_milhares_de_sucessos_nao_geram_log_individual(self):
        with tempfile.TemporaryDirectory() as td:
            origem = Path(td) / "origem"
            destino = Path(td) / "destino"
            origem.mkdir()
            for indice in range(1500):
                gravar(origem / f"arquivo_{indice:04d}.txt", b"ignorado")
            logs = []
            stats = exts.organizar_e_converter_aika(
                str(origem), str(destino), False, False, False,
                log_callback=logs.append)
        self.assertNotIn("erro", stats)
        # O volume é constante (início + caminhos + resumo), não proporcional
        # aos 1.500 arquivos processados.
        self.assertLessEqual(len(logs), 12)
        self.assertFalse(any("arquivo_" in item for item in logs))
        self.assertEqual(sum("Organização concluída" in item for item in logs), 1)


class TestWorkerEIntegridade(unittest.TestCase):
    def test_09_worker_repassa_log_por_signal_sem_widget(self):
        import main
        recebidos = []

        def backend(*args, **kwargs):
            kwargs["log_callback"]("[ERRO][JIT] arquivo.jit — motivo")
            return {"copiados": 0}

        worker = main.ExtractorWorker("origem", "destino", False, False, False)
        worker.log.connect(recebidos.append)
        with patch.object(main.exts, "organizar_e_converter_aika",
                          side_effect=backend):
            worker.run()  # síncrono e não destrutivo; valida apenas o transporte
        self.assertEqual(recebidos, ["[ERRO][JIT] arquivo.jit — motivo"])
        fonte = inspect.getsource(main.ExtractorWorker.run)
        for proibido in ("setText", "QMessageBox", "QWidget", "repaint"):
            self.assertNotIn(proibido, fonte)

    def test_10_conversores_e_extrator_nao_foram_alterados(self):
        self.assertEqual(hash_funcao(exts.convert_msh_to_obj), HASH_MSH_ANTES)
        self.assertEqual(hash_funcao(exts.convert_ms3_to_obj), HASH_MS3_ANTES)
        self.assertEqual(hash_funcao(exts.extrair_textura_jit), HASH_JIT_ANTES)


if __name__ == "__main__":
    unittest.main(verbosity=2)