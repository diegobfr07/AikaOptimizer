# -*- coding: utf-8 -*-
"""Testes de integração da página Renderizador no main.py.

Valida que a página foi corretamente integrada ao QStackedWidget,
sidebar e sistema de navegação — sem executar operações reais do dgVoodoo.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

import config  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(sys.argv)

import dgvoodoo_service as backend
from dgvoodoo_page import DgvoodooPage


def _detection(estado, mensagem=""):
    return backend.EstadoDetectado(
        estado=estado, cliente=r"C:\fake", mensagem=mensagem,
    )


class TestIntegracaoRenderizador(unittest.TestCase):
    """Valida a integração estrutural da página ao aplicativo."""

    def test_pagina_instancia_com_provider(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ORIGINAL)):
            page = DgvoodooPage(client_provider=lambda: r"C:\fake")
        self.assertIsNotNone(page)
        self.assertTrue(page.activate_button.isEnabled())

    def test_executor_adapter_chama_funcao(self):
        recebido = []

        def fake_executor(fn):
            recebido.append(fn)

        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ORIGINAL)):
            page = DgvoodooPage(client_provider=lambda: r"C:\fake",
                                executor=fake_executor)
        page._on_activate_clicked()
        self.assertEqual(len(recebido), 1)

    def test_executor_none_execucao_sincrona(self):
        """Sem executor, a operação roda síncrona e atualiza o estado."""
        estado_atual = {"estado": backend.Estado.ORIGINAL}

        def mock_detectar(*args, **kwargs):
            return _detection(estado_atual["estado"])

        with mock.patch.object(backend, "detectar_estado", side_effect=mock_detectar):
            page = DgvoodooPage(client_provider=lambda: r"C:\fake")
            with mock.patch.object(backend, "ativar_dgvoodoo",
                                   return_value=backend.ResultadoOperacao(
                                       ok=True, estado=backend.Estado.ATIVO, mensagem="ok")):
                estado_atual["estado"] = backend.Estado.ATIVO
                page._on_activate_clicked()
        self.assertIn("dgVoodoo2 Ativo", page.status_label.text())

    def test_pagina_exibe_todos_os_estados(self):
        """A página deve tratar todos os estados sem quebrar."""
        for estado in backend.Estado:
            with mock.patch.object(backend, "detectar_estado",
                                   return_value=_detection(estado)):
                page = DgvoodooPage(client_provider=lambda: r"C:\fake")
            self.assertIsNotNone(page.status_label.text())
            self.assertTrue(len(page.status_label.text()) > 0)

    def test_nao_modifica_cliente_real(self):
        """Nenhum teste de integração deve tocar o cliente real."""
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ORIGINAL)) as m:
            DgvoodooPage(client_provider=lambda: r"C:\fake")
        m.assert_called()

    def test_signal_log_emitted(self):
        """A página emite sinal de log."""
        estado_atual = {"estado": backend.Estado.ORIGINAL}

        def mock_detectar(*args, **kwargs):
            return _detection(estado_atual["estado"])

        with mock.patch.object(backend, "detectar_estado", side_effect=mock_detectar):
            page = DgvoodooPage(client_provider=lambda: r"C:\fake")
            recebidos = []
            page.log_emitted.connect(lambda msg: recebidos.append(msg))
            with mock.patch.object(backend, "ativar_dgvoodoo",
                                   return_value=backend.ResultadoOperacao(
                                       ok=True, estado=backend.Estado.ATIVO, mensagem="ativado")):
                estado_atual["estado"] = backend.Estado.ATIVO
                page._on_activate_clicked()
        self.assertTrue(len(recebidos) > 0)

    def test_executor_adapter_delega_para_background(self):
        """O adapter _executor_dgvoodoo deve delegar para executar_em_background,
        nunca executar fn() síncrona na thread chamadora."""
        import main as main_module
        from main import AikaOptimizerPro

        # Criar instância sem mostrar a janela (offscreen) — evita tarefas reais.
        with mock.patch.object(main_module.opt, "obter_pasta_jogo_atual",
                               return_value=r"C:\fake"), \
             mock.patch.object(config, "ARQUIVO_CONFIG", os.path.join(tempfile.mkdtemp(), "config.json")), \
             mock.patch.object(config, "PASTA_BACKUP", os.path.join(tempfile.mkdtemp(), "backup")):
            janela = AikaOptimizerPro()
        try:
            # Captura as funções chamadas pelo adapter.
            chamadas = []
            original_executar = janela.executar_em_background

            def spy_executar(f, resultado_callback=None, erro_callback=None,
                             finalizado_callback=None):
                chamadas.append(("background", f))
                # Simular conclusão chamando finalizado na UI thread
                if finalizado_callback is not None:
                    finalizado_callback()

            with mock.patch.object(janela, "executar_em_background",
                                   side_effect=spy_executar):
                # fn é um bound method da página (do_activate/do_restore)
                fn = janela.dgvoodoo_page.do_activate
                janela._executor_dgvoodoo(fn)

            # Deve ter delegado ao background, e não executado síncrono.
            self.assertEqual(len(chamadas), 1)
            self.assertEqual(chamadas[0][0], "background")
            # A função passada ao background NÃO foi executada (retornaria True
            # de executar_em_background apenas se iniciada).
        finally:
            janela.deleteLater()
            main_module._ = None  # noqa

    def test_executor_adapter_delega_deteccao_auto_para_background(self):
        """A detecção AUTO usa o executor existente (não roda no clique)."""
        import main as main_module
        from main import AikaOptimizerPro
        import hardware_detector as hd

        with mock.patch.object(main_module.opt, "obter_pasta_jogo_atual",
                               return_value=r"C:\fake"), \
             mock.patch.object(config, "ARQUIVO_CONFIG", os.path.join(tempfile.mkdtemp(), "config.json")), \
             mock.patch.object(config, "PASTA_BACKUP", os.path.join(tempfile.mkdtemp(), "backup")):
            janela = AikaOptimizerPro()
        try:
            chamadas = []

            def spy_executar(f, resultado_callback=None, erro_callback=None,
                             finalizado_callback=None):
                chamadas.append(f)

            with mock.patch.object(janela, "executar_em_background",
                                   side_effect=spy_executar):
                with mock.patch.object(hd, "detectar_hardware",
                                       return_value=None) as m:
                    fn = janela.dgvoodoo_page.do_detect_hardware
                    janela._executor_dgvoodoo(fn)
                    # A detecção NÃO executou na thread chamadora.
                    m.assert_not_called()
            self.assertEqual(len(chamadas), 1)
        finally:
            janela.deleteLater()
            main_module._ = None  # noqa
    def test_executor_adapter_nao_executa_fn_na_thread_chamadora(self):

        """Prova que fn NÃO roda síncrono: executar_em_background é quem roda."""
        import main as main_module
        from main import AikaOptimizerPro

        fn_executado = []

        with mock.patch.object(main_module.opt, "obter_pasta_jogo_atual",
                               return_value=r"C:\fake"), \
             mock.patch.object(config, "ARQUIVO_CONFIG", os.path.join(tempfile.mkdtemp(), "config.json")), \
             mock.patch.object(config, "PASTA_BACKUP", os.path.join(tempfile.mkdtemp(), "backup")):
            janela = AikaOptimizerPro()
        try:
            def fn_marcador():
                fn_executado.append(True)

            # Se _executor_dgvoodoo executasse fn direto (como o adapter antigo),
            # fn_marcador rodaria aqui. Como deve delegar, NÃO roda aqui.
            with mock.patch.object(janela, "executar_em_background",
                                   side_effect=lambda f, **kw: None):
                janela._executor_dgvoodoo(fn_marcador)

            self.assertEqual(fn_executado, [],
                             "fn foi executado na thread chamadora — adapter não delegou!")
        finally:
            janela.deleteLater()
            main_module._ = None  # noqa


if __name__ == "__main__":
    unittest.main()
