# -*- coding: utf-8 -*-
"""Testes da página Renderizador (dgvoodoo_page.py).

Testa a camada de apresentação: dado um estado do backend (mockado),
a página deve exibir os textos, cores e habilitação corretos.
NÃO testa a lógica interna do backend (já coberta pelos 43 testes).
"""
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QSizePolicy
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

_app = QApplication.instance() or QApplication(sys.argv)

from dgvoodoo_page import DgvoodooPage
import dgvoodoo_service as backend
import hardware_detector as hd


def _detection(estado, mensagem=""):
    return backend.EstadoDetectado(
        estado=estado,
        cliente=r"C:\CBMgames\AikaOnlineBrasil",
        mensagem=mensagem,
    )


def _detection_estado(estado, estado_persistido=None, mensagem=""):
    return backend.EstadoDetectado(
        estado=estado,
        cliente=r"C:\CBMgames\AikaOnlineBrasil",
        mensagem=mensagem,
        estado_persistido=estado_persistido,
    )


def _gpu(nome="NVIDIA GeForce RTX 4050 Laptop GPU", vram_mb=6141,
         dedicated=True):
    return hd.GpuInfo(name=nome, vram_mb=vram_mb, dedicated=dedicated)


def _perfil_hw(recomendado=hd.PERFIL_QUALITY, confianca=hd.CONFIANCA_ALTA,
               gpus=None):
    return hd.HardwareProfile(
        gpus=gpus if gpus is not None else [_gpu()],
        recommended_profile=recomendado,
        reason="diagnostico",
        confidence=confianca,
    )


def _executor_sync(fn):
    fn()


class TestPaginaInstancia(unittest.TestCase):
    def test_instancia_sem_erro(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ORIGINAL)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertIsNotNone(page)
        self.assertIsNotNone(page.activate_button)
        self.assertIsNotNone(page.restore_button)
        self.assertIsNotNone(page.reapply_button)


class TestEstadoOriginal(unittest.TestCase):
    def test_texto_status_original(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ORIGINAL)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertIn("DirectX 9", page.status_label.text())
        self.assertIn("renderizador padrão", page.status_detail.text())

    def test_botoes_original(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ORIGINAL)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertTrue(page.activate_button.isEnabled())
        self.assertFalse(page.restore_button.isEnabled())


class TestEstadoAtivo(unittest.TestCase):
    def test_texto_status_ativo(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ATIVO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertIn("dgVoodoo2 Ativo", page.status_label.text())

    def test_info_card_ativo(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ATIVO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertEqual(page.backend_value.text(), "DirectX 11")
        # Perfil legado da V1 é normalizado para "Equilibrado"
        self.assertEqual(page.perfil_value.text(), "Equilibrado")

    def test_botoes_ativo(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ATIVO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertFalse(page.activate_button.isEnabled())
        self.assertTrue(page.reapply_button.isEnabled())
        self.assertTrue(page.restore_button.isEnabled())


class TestEstadoConflito(unittest.TestCase):
    def test_texto_conflito(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.CONFLITO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertIn("d3d9.dll detectado", page.status_label.text())

    def test_nao_afirma_dxvk(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.CONFLITO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertNotIn("DXVK", page.status_label.text())

    def test_ativar_desabilitado_conflito(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.CONFLITO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertFalse(page.activate_button.isEnabled())


class TestEstadoIncompleto(unittest.TestCase):
    def test_texto_incompleto(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.INCOMPLETO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertIn("Instalação incompleta", page.status_label.text())

    def test_ativar_habilitado_incompleto(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.INCOMPLETO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertTrue(page.activate_button.isEnabled())


class TestEstadoModificadoExternamente(unittest.TestCase):
    def test_texto_modificado(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.MODIFICADO_EXTERNAMENTE)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertIn("modificados externamente", page.status_label.text())

    def test_ativar_desabilitado_modificado(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.MODIFICADO_EXTERNAMENTE)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertFalse(page.activate_button.isEnabled())


class TestEstadoTemplateAusente(unittest.TestCase):
    def test_texto_template_ausente(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.TEMPLATE_AUSENTE)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertIn("não encontrado", page.status_label.text())

    def test_ativar_desabilitado_template_ausente(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.TEMPLATE_AUSENTE)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertFalse(page.activate_button.isEnabled())


class TestEstadoErro(unittest.TestCase):
    def test_texto_erro(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ERRO, "falha X")):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertIn("Erro", page.status_label.text())
        self.assertIn("falha X", page.status_detail.text())

    def test_pagina_nao_quebra_erro(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ERRO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertIsNotNone(page.status_label.text())


class TestEstadoJogoAberto(unittest.TestCase):
    def test_texto_jogo_aberto(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.JOGO_ABERTO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertIn("Jogo em execução", page.status_label.text())


class TestRefresh(unittest.TestCase):
    def test_refresh_atualiza_estado(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ORIGINAL)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertIn("DirectX 9", page.status_label.text())

        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ATIVO)):
            page.refresh_estado()
        self.assertIn("dgVoodoo2 Ativo", page.status_label.text())


class TestOperacaoEmAndamento(unittest.TestCase):
    def test_set_busy_desabilita_botoes(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ORIGINAL)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertTrue(page.activate_button.isEnabled())
        page.set_busy(True)
        self.assertFalse(page.activate_button.isEnabled())
        page.set_busy(False)
        self.assertTrue(page.activate_button.isEnabled())


class TestBotaoAtivar(unittest.TestCase):
    def test_clique_ativa_backend(self):
        """Após clicar em Ativar, o backend é chamado e o estado atualiza."""
        estado_atual = {"estado": backend.Estado.ORIGINAL}

        def mock_detectar(*args, **kwargs):
            return _detection(estado_atual["estado"])

        with mock.patch.object(backend, "detectar_estado", side_effect=mock_detectar):
            page = DgvoodooPage(client_provider=lambda: "cli")
            with mock.patch.object(backend, "ativar_dgvoodoo",
                                   return_value=backend.ResultadoOperacao(
                                       ok=True, estado=backend.Estado.ATIVO, mensagem="ok")):
                # Após a operação, o estado detectado será ATIVO
                estado_atual["estado"] = backend.Estado.ATIVO
                page._on_activate_clicked()
        self.assertIn("dgVoodoo2 Ativo", page.status_label.text())


class TestBotaoRestaurar(unittest.TestCase):
    def test_clique_restaura_backend(self):
        """Após clicar em Restaurar, o backend é chamado e o estado atualiza."""
        estado_atual = {"estado": backend.Estado.ATIVO}

        def mock_detectar(*args, **kwargs):
            return _detection(estado_atual["estado"])

        with mock.patch.object(backend, "detectar_estado", side_effect=mock_detectar):
            page = DgvoodooPage(client_provider=lambda: "cli")
            with mock.patch.object(backend, "restaurar_directx_original",
                                   return_value=backend.ResultadoOperacao(
                                       ok=True, estado=backend.Estado.ORIGINAL, mensagem="ok")):
                estado_atual["estado"] = backend.Estado.ORIGINAL
                page._on_restore_clicked()
        self.assertIn("DirectX 9", page.status_label.text())


class TestExecutorInjetado(unittest.TestCase):
    def test_executor_recebe_callback(self):
        recebido = []

        def meu_executor(fn):
            recebido.append(fn)

        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ORIGINAL)):
            page = DgvoodooPage(client_provider=lambda: "cli", executor=meu_executor)
        page._on_activate_clicked()
        self.assertEqual(len(recebido), 1)
        self.assertTrue(callable(recebido[0]))


class TestPerfisUI(unittest.TestCase):
    def test_quatro_cards_existem(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ATIVO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertEqual(len(page._profile_buttons), 4)
        for perfil in (backend.PERFIL_AUTO,) + backend.PERFIS_SUPORTADOS:
            self.assertIn(perfil, page._profile_buttons)

    def test_auto_card_vem_primeiro(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ATIVO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        ordem = list(page._profile_buttons.keys())
        self.assertEqual(ordem[0], backend.PERFIL_AUTO)
        self.assertEqual(ordem[1:], list(backend.PERFIS_SUPORTADOS))

    def test_auto_possui_badge_recomendado(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ATIVO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertEqual(page._profile_buttons[backend.PERFIL_AUTO].property("badge"),
                         "RECOMENDADO")

    def test_equilibrado_sem_badge_duplicado(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ATIVO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertIsNone(page._profile_buttons[backend.PERFIL_BALANCED].property("badge"))

    def test_equilibrado_aplicado_padrao(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ATIVO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        # Sem preset persistido, perfil aplicado default = balanced
        self.assertEqual(page._profile_applied, backend.PERFIL_BALANCED)
        btn = page._profile_buttons[backend.PERFIL_BALANCED]
        self.assertTrue(btn.isChecked())

    def test_selecao_nao_aplica_automaticamente(self):
        chamadas = []
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ATIVO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        with mock.patch.object(backend, "aplicar_perfil",
                               side_effect=lambda *a, **k: chamadas.append(1)):
            page._on_profile_selected(backend.PERFIL_QUALITY)
        self.assertEqual(chamadas, [])
        self.assertEqual(page._profile_selected, backend.PERFIL_QUALITY)
        self.assertNotEqual(page._profile_selected, page._profile_applied)

    def test_botao_aplicar_chama_backend(self):
        estado_atual = {"estado": backend.Estado.ATIVO, "preset": "balanced"}

        def mock_detectar(*args, **kwargs):
            return _detection(estado_atual["estado"])

        with mock.patch.object(backend, "detectar_estado", side_effect=mock_detectar):
            page = DgvoodooPage(client_provider=lambda: "cli")
            page._on_profile_selected(backend.PERFIL_PERFORMANCE)
            with mock.patch.object(
                    backend, "aplicar_perfil",
                    return_value=backend.ResultadoOperacao(
                        ok=True, estado=backend.Estado.ATIVO, mensagem="ok",
                        dados={"perfil": "performance"})) as m:
                page._on_apply_profile_clicked()
            self.assertEqual(m.call_count, 1)
            args = m.call_args[0]
            self.assertEqual(args[0], backend.PERFIL_PERFORMANCE)

    def test_original_desabilita_aplicar(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ORIGINAL)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertFalse(page.apply_profile_button.isEnabled())

    def test_ativo_habilita_aplicar(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ATIVO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertTrue(page.apply_profile_button.isEnabled())

    def test_conflito_bloqueia_aplicar(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.CONFLITO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertFalse(page.apply_profile_button.isEnabled())

    def test_modificado_bloqueia_aplicar(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.MODIFICADO_EXTERNAMENTE)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertFalse(page.apply_profile_button.isEnabled())

    def test_busy_desabilita_perfis(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection(backend.Estado.ATIVO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        self.assertTrue(page.apply_profile_button.isEnabled())
        page.set_busy(True)
        self.assertFalse(page.apply_profile_button.isEnabled())
        for btn in page._profile_buttons.values():
            self.assertFalse(btn.isEnabled())
        page.set_busy(False)
        self.assertTrue(page.apply_profile_button.isEnabled())


class TestAutoUI(unittest.TestCase):
    """V2.3B: comportamento do card AUTO na página Renderizador."""

    def _page(self, estado=backend.Estado.ATIVO, executor=None,
              estado_persistido=None):
        with mock.patch.object(
                backend, "detectar_estado",
                return_value=_detection_estado(estado, estado_persistido)):
            return DgvoodooPage(client_provider=lambda: "cli", executor=executor)

    def test_selecionar_auto_nao_aplica_perfil(self):
        page = self._page()
        chamadas = []
        with mock.patch.object(backend, "aplicar_perfil",
                               side_effect=lambda *a, **k: chamadas.append(1)):
            with mock.patch.object(hd, "detectar_hardware",
                                   return_value=_perfil_hw()):
                page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertEqual(chamadas, [])

    def test_selecionar_auto_dispara_deteccao_via_executor(self):
        recebidas = []
        executor = lambda fn: recebidas.append(fn)  # noqa: E731
        page = self._page(executor=executor)
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()) as m:
            page._on_profile_selected(backend.PERFIL_AUTO)
            # A detecção NÃO rodou ainda: foi delegada ao executor.
            m.assert_not_called()
        self.assertEqual(len(recebidas), 1)
        self.assertEqual(recebidas[0], page.do_detect_hardware)

    def test_detectar_hardware_nao_roda_sincrono_no_clique(self):
        """Prova que o clique NÃO executa a detecção na thread da UI."""
        recebidas = []
        executor = lambda fn: recebidas.append(fn)  # noqa: E731
        page = self._page(executor=executor)
        chamado = []
        with mock.patch.object(
                hd, "detectar_hardware",
                side_effect=lambda: chamado.append(1) or _perfil_hw()):
            page._on_profile_selected(backend.PERFIL_AUTO)
            self.assertEqual(chamado, [])  # nada rodou no clique
            # Simula o worker: roda a fn registrada e entrega via sinal.
            for fn in recebidas:
                fn()
            self.assertEqual(len(chamado), 1)

    def test_resultado_chega_via_signal(self):
        """A UI atualiza por meio do sinal hardware_detected (thread-safe)."""
        page = self._page(executor=_executor_sync)
        profile = _perfil_hw()
        recebidos = []
        page.hardware_detected.connect(lambda p: recebidos.append(p))
        with mock.patch.object(hd, "detectar_hardware", return_value=profile):
            page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertEqual(recebidos, [profile])
        self.assertIs(page._hardware_profile, profile)
        self.assertFalse(page._hardware_detecting)

    def test_gpu_e_vram_exibidas(self):
        page = self._page(executor=_executor_sync)
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()):
            page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertIn("NVIDIA GeForce RTX 4050 Laptop GPU",
                      page.hw_gpu_label.text())
        self.assertIn("6.0 GB", page.hw_vram_label.text())

    def test_recomendacao_e_confianca_exibidas(self):
        page = self._page(executor=_executor_sync)
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()):
            page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertIn("Qualidade", page.hw_recomendacao_label.text())
        self.assertIn("Alta", page.hw_confianca_label.text())

    def test_fallback_balanced_baixa_mensagem_amigavel(self):
        page = self._page(executor=_executor_sync)
        fallback = _perfil_hw(recomendado=hd.PERFIL_BALANCED,
                              confianca=hd.CONFIANCA_BAIXA)
        with mock.patch.object(hd, "detectar_hardware", return_value=fallback):
            page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertIn("por segurança", page.hw_recomendacao_label.text())
        self.assertIn("Baixa", page.hw_confianca_label.text())

    def test_auto_sem_deteccao_mantem_aplicar_desabilitado(self):
        recebidas = []
        executor = lambda fn: recebidas.append(fn)  # noqa: E731
        page = self._page(executor=executor)
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()):
            page._on_profile_selected(backend.PERFIL_AUTO)
        # Detecção pendente e sem resolved -> aplicar desabilitado.
        self.assertFalse(page.apply_profile_button.isEnabled())

    def test_auto_detectado_ativo_habilita_aplicar(self):
        page = self._page(executor=_executor_sync)
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()):
            page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertTrue(page.apply_profile_button.isEnabled())

    def test_auto_detectado_original_mantem_aplicar_desabilitado(self):
        page = self._page(estado=backend.Estado.ORIGINAL,
                          executor=_executor_sync)
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()):
            page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertFalse(page.apply_profile_button.isEnabled())

    def test_aplicar_auto_chama_backend_uma_vez(self):
        page = self._page(executor=_executor_sync)
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()):
            page._on_profile_selected(backend.PERFIL_AUTO)
        with mock.patch.object(
                backend, "aplicar_perfil",
                return_value=backend.ResultadoOperacao(
                    ok=True, estado=backend.Estado.ATIVO, mensagem="ok")) as m:
            page._on_apply_profile_clicked()
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertEqual(args[0], backend.PERFIL_AUTO)
        self.assertEqual(kwargs.get("resolved_profile"),
                         backend.PERFIL_QUALITY)

    def test_resolved_passado_ao_backend_e_o_recomendado(self):
        page = self._page(executor=_executor_sync)
        perfil = _perfil_hw(recomendado=hd.PERFIL_QUALITY)
        with mock.patch.object(hd, "detectar_hardware", return_value=perfil):
            page._on_profile_selected(backend.PERFIL_AUTO)
        with mock.patch.object(
                backend, "aplicar_perfil",
                return_value=backend.ResultadoOperacao(
                    ok=True, estado=backend.Estado.ATIVO, mensagem="ok")) as m:
            page._on_apply_profile_clicked()
        m.assert_called_once()
        self.assertEqual(m.call_args[0][0], backend.PERFIL_AUTO)
        self.assertEqual(m.call_args.kwargs["resolved_profile"],
                         perfil.recommended_profile)

    def test_manual_continua_funcionando(self):
        page = self._page(executor=_executor_sync)
        page._on_profile_selected(backend.PERFIL_PERFORMANCE)
        with mock.patch.object(
                backend, "aplicar_perfil",
                return_value=backend.ResultadoOperacao(
                    ok=True, estado=backend.Estado.ATIVO, mensagem="ok")) as m:
            page._on_apply_profile_clicked()
        m.assert_called_once_with(backend.PERFIL_PERFORMANCE)
        self.assertNotIn("resolved_profile", m.call_args.kwargs)

    def test_reinicio_preset_auto_quality_renderiza(self):
        """Abrir com estado persistido auto/quality seleciona AUTO e mostra."""
        estado_persistido = {"preset": "auto", "resolved_profile": "quality"}
        page = self._page(estado_persistido=estado_persistido)
        self.assertEqual(page._profile_applied, backend.PERFIL_AUTO)
        self.assertEqual(page._profile_applied_resolved, backend.PERFIL_QUALITY)
        self.assertEqual(page.perfil_value.text(), "AUTO → Qualidade")
        self.assertTrue(page._profile_buttons[backend.PERFIL_AUTO].isChecked())
        self.assertIn("AUTO → Qualidade", page.profile_status.text())


    def test_detectar_novamente_executa_nova_leitura(self):
        page = self._page(executor=_executor_sync)
        primeiro = _perfil_hw(recomendado=hd.PERFIL_BALANCED)
        segundo = _perfil_hw(recomendado=hd.PERFIL_QUALITY)
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=primeiro) as m:
            page._on_profile_selected(backend.PERFIL_AUTO)
            self.assertEqual(m.call_count, 1)
            # Selecionar AUTO novamente usa o cache (sem nova detecção).
            page._on_profile_selected(backend.PERFIL_AUTO)
            self.assertEqual(m.call_count, 1)
            # Reanalisar força nova leitura.
            m.return_value = segundo
            page._on_reanalyze_clicked()
            self.assertEqual(m.call_count, 2)
            self.assertIs(page._hardware_profile, segundo)
            self.assertEqual(page._resolved_profile_aplicar(),
                             backend.PERFIL_QUALITY)

    def test_busy_impede_deteccao_duplicada(self):
        recebidas = []
        executor = lambda fn: recebidas.append(fn)  # noqa: E731
        page = self._page(executor=executor)
        page.set_busy(True)
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()):
            page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertEqual(recebidas, [])

    def test_detectando_impede_aplicacao_duplicada(self):
        recebidas = []
        executor = lambda fn: recebidas.append(fn)  # noqa: E731
        page = self._page(executor=executor)
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()):
            page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertTrue(page._hardware_detecting)
        with mock.patch.object(backend, "aplicar_perfil",
                               return_value=backend.ResultadoOperacao(
                                   ok=True, estado=backend.Estado.ATIVO,
                                   mensagem="ok")) as m:
            page._on_apply_profile_clicked()
        m.assert_not_called()

    def test_nenhuma_deteccao_no_import(self):
        page = self._page()
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()) as m:
            # Abrir e usar perfil manual não detecta nada.
            page._on_profile_selected(backend.PERFIL_PERFORMANCE)
            m.assert_not_called()

    def test_perfil_manual_nao_dispara_deteccao_automatica(self):
        page = self._page(executor=_executor_sync)
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()) as m:
            page.refresh_estado()
            m.assert_not_called()

    def test_falha_deteccao_mensagem_amigavel(self):
        page = self._page(executor=_executor_sync)
        with mock.patch.object(hd, "detectar_hardware", return_value=None):
            page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertIn("Equilibrado", page.hw_recomendacao_label.text())
        self.assertFalse(page.apply_profile_button.isEnabled())


class TestAutoOffscreenLayout(unittest.TestCase):
    """Valida layout offscreen com o novo card HARDWARE permanente."""

    def test_layout_offscreen_quatro_cards_e_hardware_visivel(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection_estado(backend.Estado.ATIVO)):
            page = DgvoodooPage(client_provider=lambda: "cli")
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()):
            page.resize(1100, 900)
            page.show()  # forçar layout em offscreen
            QApplication.processEvents()  # dispara detecção automática (mock)
            self.assertEqual(len(page._profile_buttons), 4)
            # Card de hardware é permanente e legível.
            self.assertFalse(page.hardware_card.isHidden())
            self.assertIn("RTX 4050", page.hw_gpu_label.text())
            self.assertIn("Qualidade", page.hw_recomendacao_label.text())
        # Estado AUTO persistido renderiza sem exceção.
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection_estado(
                                   backend.Estado.ATIVO,
                                   {"preset": "auto", "resolved_profile": "balanced"})):
            page.refresh_estado()
        self.assertEqual(page.perfil_value.text(), "AUTO → Equilibrado")
        page.hide()


class TestResponsiveLayout(unittest.TestCase):
    """V2.3D: cards de perfil reorganizam 4 colunas <-> 2x2 conforme largura."""

    def setUp(self):
        # A detecção automática dispara ao mostrar a página: sempre mockada
        # para nunca tocar WMI/Registro/PowerShell reais.
        p = mock.patch.object(hd, "detectar_hardware", return_value=_perfil_hw())
        p.start()
        self.addCleanup(p.stop)

    def _page(self, estado=backend.Estado.ATIVO, executor=None,
              estado_persistido=None):
        """Cria página mantendo detectar_estado mockado durante todo o teste."""
        p = mock.patch.object(
            backend, "detectar_estado",
            return_value=_detection_estado(estado, estado_persistido))
        p.start()
        self.addCleanup(p.stop)
        return DgvoodooPage(client_provider=lambda: "cli", executor=executor)

    @staticmethod
    def _show(page, w, h):
        page.resize(w, h)
        page.show()
        QApplication.processEvents()

    def _geos(self, page):
        return {p: page._profile_buttons[p].geometry() for p in page._profile_buttons}

    def test_pagina_abre_sem_excecao(self):
        page = self._page()
        self._show(page, 900, 800)
        self.assertIsNotNone(page.layout())
        page.hide()

    def test_quatro_cards_sao_os_mesmos_widgets(self):
        page = self._page()
        ids = {p: id(page._profile_buttons[p]) for p in page._profile_buttons}
        self._show(page, 1100, 800)
        self._show(page, 650, 800)
        self._show(page, 1200, 800)
        self.assertEqual({p: id(page._profile_buttons[p]) for p in page._profile_buttons},
                         ids)
        page.hide()

    def test_button_group_continua_exclusivo(self):
        page = self._page()
        self.assertTrue(page._profile_group.exclusive())
        self.assertEqual(page._profile_group.buttons(),
                         list(page._profile_buttons.values()))
        page.hide()

    def test_modo_largo_quatro_cards_na_mesma_linha(self):
        page = self._page()
        self._show(page, 1200, 800)
        self.assertTrue(page._profile_layout_wide)
        geos = self._geos(page)
        ordem = [backend.PERFIL_AUTO, backend.PERFIL_PERFORMANCE,
                 backend.PERFIL_BALANCED, backend.PERFIL_QUALITY]
        ys = [geos[p].y() for p in ordem]
        xs = [geos[p].x() for p in ordem]
        self.assertLessEqual(max(ys) - min(ys), 4)  # mesma linha
        self.assertEqual(xs, sorted(xs))  # colunas crescentes
        self.assertLess(xs[0], xs[1])
        self.assertLess(xs[1], xs[2])
        self.assertLess(xs[2], xs[3])
        page.hide()

    def test_modo_compacto_vira_2x2(self):
        page = self._page()
        self._show(page, 640, 800)
        self.assertFalse(page._profile_layout_wide)
        geos = self._geos(page)
        a = geos[backend.PERFIL_AUTO]
        d = geos[backend.PERFIL_PERFORMANCE]
        e = geos[backend.PERFIL_BALANCED]
        q = geos[backend.PERFIL_QUALITY]
        # linha 0: AUTO | DESEMPENHO ; linha 1: EQUILIBRADO | QUALIDADE
        self.assertLessEqual(abs(a.y() - d.y()), 4)
        self.assertLess(a.x(), d.x())
        self.assertLessEqual(abs(e.y() - q.y()), 4)  # EQUILIBRADO | QUALIDADE
        self.assertLess(e.x(), q.x())
        self.assertGreater(e.y(), a.y() + 8)
        page.hide()

    def test_voltar_de_2x2_para_4_colunas(self):
        page = self._page()
        self._show(page, 640, 800)
        self.assertFalse(page._profile_layout_wide)
        self._show(page, 1200, 800)
        self.assertTrue(page._profile_layout_wide)
        geos = self._geos(page)
        ys = [geos[p].y() for p in page._profile_buttons]
        self.assertLessEqual(max(ys) - min(ys), 4)
        page.hide()

    def test_checked_preservado_ao_reorganizar(self):
        page = self._page()
        self._show(page, 1100, 800)
        # Marca o card como aplicado (mecanismo real usado por _render_state).
        page._mark_profile_applied(backend.PERFIL_PERFORMANCE)
        btn = page._profile_buttons[backend.PERFIL_PERFORMANCE]
        self.assertTrue(btn.isChecked())
        self.assertEqual(page._profile_selected, backend.PERFIL_PERFORMANCE)
        self._show(page, 620, 800)
        self.assertFalse(page._profile_layout_wide)
        self.assertTrue(btn.isChecked())
        self._show(page, 1200, 800)
        self.assertTrue(page._profile_layout_wide)
        self.assertTrue(btn.isChecked())
        self.assertEqual(page._profile_selected, backend.PERFIL_PERFORMANCE)
        page.hide()

    def test_sinais_continuam_apos_resize(self):
        page = self._page()
        self._show(page, 900, 800)
        self._show(page, 640, 800)
        page._on_profile_selected(backend.PERFIL_QUALITY)
        self.assertEqual(page._profile_selected, backend.PERFIL_QUALITY)
        with mock.patch.object(
                backend, "aplicar_perfil",
                return_value=backend.ResultadoOperacao(
                    ok=True, estado=backend.Estado.ATIVO, mensagem="ok")) as m:
            page._on_apply_profile_clicked()
        m.assert_called_once_with(backend.PERFIL_QUALITY)
        page.hide()

    def test_auto_painel_hardware_visivel_apos_resize(self):
        page = self._page(executor=_executor_sync)
        self._show(page, 900, 800)
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()):
            page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertFalse(page.hardware_card.isHidden())
        self._show(page, 640, 800)
        self.assertFalse(page.hardware_card.isHidden())
        self.assertIn("RTX 4050", page.hw_gpu_label.text())
        page.hide()

    def test_perfil_atual_correto_apos_resize(self):
        page = self._page(estado_persistido={"preset": "auto",
                                             "resolved_profile": "quality"})
        self._show(page, 900, 800)
        self.assertEqual(page.perfil_value.text(), "AUTO → Qualidade")
        self._show(page, 620, 800)
        self.assertEqual(page.perfil_value.text(), "AUTO → Qualidade")
        page.hide()

    def test_aplicar_enable_segundo_estado_funcional(self):
        ativo = self._page(estado=backend.Estado.ATIVO)
        self._show(ativo, 640, 800)
        self.assertTrue(ativo.apply_profile_button.isEnabled())
        ativo.hide()
        original = self._page(estado=backend.Estado.ORIGINAL)
        self._show(original, 640, 800)
        self.assertFalse(original.apply_profile_button.isEnabled())
        original.hide()



    def test_resize_nao_dispara_deteccao_hardware(self):
        page = self._page()
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()) as m:
            for w in (1200, 640, 900, 500, 1300):
                page.resize(w, 700)
            m.assert_not_called()
        page.hide()

    def test_resize_nao_chama_backend(self):
        with mock.patch.object(backend, "detectar_estado",
                               return_value=_detection_estado(
                                   backend.Estado.ATIVO)) as det:
            page = DgvoodooPage(client_provider=lambda: "cli")
            det.reset_mock()
            with mock.patch.object(backend, "aplicar_perfil") as ap:
                for w in (1200, 640, 900, 500, 1300):
                    page.resize(w, 700)
                ap.assert_not_called()
            det.assert_not_called()
        page.hide()

    def test_sem_clipping_estrutural_em_varias_dimensoes(self):
        page = self._page()
        # Larguras coerentes com a aplicação real. Em offscreen as métricas de
        # fonte são infladas (sem fontes reais), então valida-se a geometria
        # nos modos 2x2 (640) e 4 colunas (1200+); a reorganização estrutural
        # em qualquer largura é coberta pelos testes de posição de grid.
        for w, h in ((640, 760), (1200, 800), (1600, 900)):
            self._show(page, w, h)
            for p, btn in page._profile_buttons.items():
                g = btn.geometry()
                self.assertGreaterEqual(g.x(), 0, p)
                self.assertGreaterEqual(g.y(), 0, p)
                self.assertLessEqual(g.x() + g.width(), page.width(), p)
        page.hide()

    def test_posicoes_de_grid_em_largura_estreita(self):
        """Em 500 px (extremo) o grid ainda é 2x2 e organizado."""
        page = self._page()
        self._show(page, 500, 700)
        self.assertFalse(page._profile_layout_wide)

        def pos(perfil):
            btn = page._profile_buttons[perfil]
            for i in range(page._profile_grid.count()):
                if page._profile_grid.itemAt(i).widget() is btn:
                    r, c, *_ = page._profile_grid.getItemPosition(i)
                    return (r, c)
            return None

        esperado = {
            backend.PERFIL_AUTO: (0, 0),
            backend.PERFIL_PERFORMANCE: (0, 1),
            backend.PERFIL_BALANCED: (1, 0),
            backend.PERFIL_QUALITY: (1, 1),
        }
        for perfil, rc in esperado.items():
            self.assertEqual(pos(perfil), rc, perfil)
        page.hide()

    def test_resize_repetido_sem_excecao(self):
        page = self._page()
        self._show(page, 900, 800)
        for i in range(20):
            w = 480 + (i * 40) % 1000
            page.resize(w, 700 + (i % 3) * 50)
            QApplication.processEvents()
        self.assertTrue(page._profile_layout_wide in (True, False))
        page.hide()


class TestPremiumVisualCards(unittest.TestCase):
    """V2.4: cards de perfil premium (ícones SVG, hierarquia, sem emojis)."""

    def setUp(self):
        self._patch_backend = mock.patch.object(
            backend, "detectar_estado",
            return_value=_detection_estado(backend.Estado.ATIVO))
        self._patch_backend.start()
        self.addCleanup(self._patch_backend.stop)
        self._patch_hw = mock.patch.object(hd, "detectar_hardware",
                                          return_value=_perfil_hw())
        self._patch_hw.start()
        self.addCleanup(self._patch_hw.stop)

    def _page(self):
        return DgvoodooPage(client_provider=lambda: "cli")

    def test_cards_sem_emojis_decorativos(self):
        page = self._page()
        emojis = set("✦⚡⚖✨")
        for perfil, btn in page._profile_buttons.items():
            texto = btn._title_label.text() + btn._desc_label.text()
            self.assertFalse(any(ch in texto for ch in emojis), perfil)

    def test_quatro_cards_possuem_icone_svg(self):
        page = self._page()
        for perfil, btn in page._profile_buttons.items():
            pix = btn._icon_label.pixmap()
            self.assertIsNotNone(pix, perfil)
            self.assertFalse(pix.isNull(), perfil)

    def test_auto_possui_badge_recomendado(self):
        page = self._page()
        btn = page._profile_buttons[backend.PERFIL_AUTO]
        self.assertEqual(btn.property("badge"), "RECOMENDADO")
        self.assertFalse(btn._badge_label.isHidden())

    def test_equilibrado_sem_badge_recomendado(self):
        page = self._page()
        btn = page._profile_buttons[backend.PERFIL_BALANCED]
        self.assertIsNone(btn.property("badge"))
        self.assertTrue(btn._badge_label.isHidden())

    def test_titulo_e_descricao_sao_widgets_distintos(self):
        page = self._page()
        for btn in page._profile_buttons.values():
            self.assertEqual(btn._title_label.objectName(),
                             "ProfileCardTitle")
            self.assertEqual(btn._desc_label.objectName(),
                             "ProfileCardDescription")
            self.assertIsNot(btn._title_label, btn._desc_label)
            self.assertNotEqual(btn._title_label.text().strip(), "")
            self.assertNotEqual(btn._desc_label.text().strip(), "")

    def test_cards_checkable(self):
        page = self._page()
        for btn in page._profile_buttons.values():
            self.assertTrue(btn.isCheckable())

    def test_button_group_exclusivo_quatro_botoes(self):
        page = self._page()
        self.assertTrue(page._profile_group.exclusive())
        self.assertEqual(len(page._profile_group.buttons()), 4)

    def test_clique_no_conteudo_interno_ativa_card(self):
        page = self._page()
        btn = page._profile_buttons[backend.PERFIL_QUALITY]
        page.show()
        QApplication.processEvents()
        # Clique na área do título (child transparente -> evento cai no card).
        QTest.mouseClick(btn, Qt.LeftButton, Qt.NoModifier,
                         btn._title_label.geometry().center())
        self.assertEqual(page._profile_selected, backend.PERFIL_QUALITY)
        page.hide()

    def test_layout_largo_quatro_colunas(self):
        page = self._page()
        page.resize(1200, 800)
        page.show()
        QApplication.processEvents()
        self.assertTrue(page._profile_layout_wide)
        ys = [page._profile_buttons[p].geometry().y()
              for p in page._profile_buttons]
        self.assertLessEqual(max(ys) - min(ys), 4)
        page.hide()

    def test_layout_estreito_2x2(self):
        page = self._page()
        page.resize(640, 800)
        page.show()
        QApplication.processEvents()
        self.assertFalse(page._profile_layout_wide)
        a = page._profile_buttons[backend.PERFIL_AUTO].geometry()
        q = page._profile_buttons[backend.PERFIL_QUALITY].geometry()
        self.assertGreater(q.y(), a.y())
        page.hide()

    def test_identidade_preservada_no_resize(self):
        page = self._page()
        ids = {p: id(page._profile_buttons[p]) for p in page._profile_buttons}
        for w in (1200, 640, 1200, 500, 1300):
            page.resize(w, 800)
            QApplication.processEvents()
        self.assertEqual({p: id(page._profile_buttons[p])
                          for p in page._profile_buttons}, ids)
        page.hide()

    def test_checked_preservado_no_resize(self):
        page = self._page()
        page._mark_profile_applied(backend.PERFIL_BALANCED)
        btn = page._profile_buttons[backend.PERFIL_BALANCED]
        for w in (1200, 640, 900):
            page.resize(w, 800)
            QApplication.processEvents()
            self.assertTrue(btn.isChecked())
        self.assertEqual(page._profile_selected, backend.PERFIL_BALANCED)
        page.hide()


class TestPremiumHardwareCard(unittest.TestCase):
    """V2.4: card HARDWARE DETECTADO permanente e legível."""

    def setUp(self):
        p = mock.patch.object(backend, "detectar_estado",
                              return_value=_detection_estado(backend.Estado.ATIVO))
        p.start()
        self.addCleanup(p.stop)

    def _page(self, executor=None):
        return DgvoodooPage(client_provider=lambda: "cli", executor=executor)

    def test_hardware_card_existe_e_visivel(self):
        page = self._page()
        self.assertIsNotNone(page.hardware_card)
        self.assertFalse(page.hardware_card.isHidden())

    def test_gpu_vram_recomendacao_confianca_exibidos(self):
        page = self._page(executor=_executor_sync)
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()):
            page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertIn("RTX 4050", page.hw_gpu_label.text())
        self.assertIn("6.0 GB", page.hw_vram_label.text())
        self.assertIn("Qualidade", page.hw_recomendacao_label.text())
        self.assertIn("Alta", page.hw_confianca_label.text())

    def test_reanalisar_dentro_do_hardware_card(self):
        page = self._page()
        self.assertIs(page.reanalyze_button.parent(), page.hardware_card)

    def test_fallback_equilibrado_baixa(self):
        page = self._page(executor=_executor_sync)
        fb = _perfil_hw(recomendado=hd.PERFIL_BALANCED,
                        confianca=hd.CONFIANCA_BAIXA)
        with mock.patch.object(hd, "detectar_hardware", return_value=fb):
            page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertIn("Equilibrado", page.hw_recomendacao_label.text())
        self.assertIn("Baixa", page.hw_confianca_label.text())

    def test_estado_analisando_inicial(self):
        page = self._page()
        self.assertIn("Analisando", page.hw_gpu_label.text())
        self.assertIn("—", page.hw_vram_label.text())

    def test_hardware_card_legivel_em_largura_estreita(self):
        page = self._page()
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()):
            page.resize(620, 800)
            page.show()
            QApplication.processEvents()
        self.assertFalse(page.hardware_card.isHidden())
        self.assertGreaterEqual(page.hardware_card.geometry().width(), 100)
        page.hide()


class TestDetecaoAutomatica(unittest.TestCase):
    """V2.4: detecção automática de hardware ao entrar na página (lazy)."""

    def _mk(self, estado=backend.Estado.ATIVO, executor=None):
        p = mock.patch.object(backend, "detectar_estado",
                              return_value=_detection_estado(estado))
        p.start()
        self.addCleanup(p.stop)
        hm = mock.Mock(return_value=_perfil_hw())
        ph = mock.patch.object(hd, "detectar_hardware", hm)
        ph.start()
        self.addCleanup(ph.stop)
        return DgvoodooPage(client_provider=lambda: "cli", executor=executor), hm

    def test_instanciar_sem_mostrar_nao_detecta(self):
        page, h = self._mk()
        h.assert_not_called()
        page.deleteLater()

    def test_primeira_exibicao_dispara_deteccao(self):
        page, h = self._mk(executor=_executor_sync)
        page.show()
        QApplication.processEvents()
        self.assertEqual(h.call_count, 1)
        page.hide()

    def test_deteccao_usa_executor(self):
        recebidas = []
        page, h = self._mk(executor=lambda fn: recebidas.append(fn))
        page.show()
        QApplication.processEvents()
        self.assertEqual(recebidas, [page.do_detect_hardware])
        h.assert_not_called()  # executor não executou; nada rodou no clique
        page.hide()

    def test_deteccao_nao_roda_sincrono_na_ui(self):
        recebidas = []
        page, h = self._mk(executor=lambda fn: recebidas.append(fn))
        page.show()
        QApplication.processEvents()
        h.assert_not_called()  # pesado não roda na UI thread
        for fn in recebidas:
            fn()
        self.assertEqual(h.call_count, 1)
        page.hide()

    def test_resultado_chega_via_signal_threadsafe(self):
        page, h = self._mk(executor=_executor_sync)
        recebidos = []
        page.hardware_detected.connect(lambda p: recebidos.append(p))
        page.show()
        QApplication.processEvents()
        self.assertEqual(len(recebidos), 1)
        self.assertIsNotNone(page._hardware_profile)
        self.assertIn("RTX 4050", page.hw_gpu_label.text())
        page.hide()

    def test_show_repetido_nao_detecta_novamente(self):
        page, h = self._mk(executor=_executor_sync)
        for _ in range(3):
            page.show()
            QApplication.processEvents()
            page.hide()
        self.assertEqual(h.call_count, 1)
        page.hide()

    def test_sair_voltar_sessao_usa_cache(self):
        page, h = self._mk(executor=_executor_sync)
        page.show()
        QApplication.processEvents()
        page.hide()
        self.assertEqual(h.call_count, 1)
        page.show()
        QApplication.processEvents()
        page.hide()
        self.assertEqual(h.call_count, 1)  # cache da sessão
        page.hide()

    def test_selecionar_auto_apos_deteccao_automatica_usa_cache(self):
        page, h = self._mk(executor=_executor_sync)
        page.show()
        QApplication.processEvents()
        self.assertEqual(h.call_count, 1)
        page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertEqual(h.call_count, 1)  # reutiliza cache, sem nova detecção
        self.assertEqual(page._profile_selected, backend.PERFIL_AUTO)
        page.hide()

    def test_selecionar_auto_nao_aplica_perfil(self):
        page, h = self._mk(executor=_executor_sync)
        page.show()
        QApplication.processEvents()
        chamadas = []
        with mock.patch.object(backend, "aplicar_perfil",
                               side_effect=lambda *a, **k: chamadas.append(1)):
            page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertEqual(chamadas, [])
        page.hide()

    def test_reanalisar_forca_nova_deteccao(self):
        page, h = self._mk(executor=_executor_sync)
        page.show()
        QApplication.processEvents()
        self.assertEqual(h.call_count, 1)
        page._on_reanalyze_clicked()
        self.assertEqual(h.call_count, 2)
        page.hide()

    def test_reanalisar_nao_aplica_perfil(self):
        page, h = self._mk(executor=_executor_sync)
        page.show()
        QApplication.processEvents()
        chamadas = []
        with mock.patch.object(backend, "aplicar_perfil",
                               side_effect=lambda *a, **k: chamadas.append(1)):
            page._on_reanalyze_clicked()
        self.assertEqual(chamadas, [])
        page.hide()

    def test_resize_nao_dispara_deteccao(self):
        page, h = self._mk()
        for w in (1200, 640, 900):
            page.resize(w, 700)
        h.assert_not_called()
        page.hide()

    def test_deteccao_automatica_em_original(self):
        page, h = self._mk(estado=backend.Estado.ORIGINAL,
                           executor=_executor_sync)
        page.show()
        QApplication.processEvents()
        self.assertEqual(h.call_count, 1)
        page._on_profile_selected(backend.PERFIL_AUTO)
        # ORIGINAL: Aplicar continua desabilitado (dgVoodoo não ativo).
        self.assertFalse(page.apply_profile_button.isEnabled())
        page.hide()

    def test_ativo_auto_hardware_permite_aplicar(self):
        page, h = self._mk(executor=_executor_sync)
        page.show()
        QApplication.processEvents()
        page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertTrue(page.apply_profile_button.isEnabled())
        page.hide()


class TestFinalVisualPolish(unittest.TestCase):
    """V2.4.1: badge compacto, cabeçalho do hardware e hierarquia visual."""

    def setUp(self):
        p = mock.patch.object(backend, "detectar_estado",
                              return_value=_detection_estado(backend.Estado.ATIVO))
        p.start()
        self.addCleanup(p.stop)
        self._hm = mock.Mock(return_value=_perfil_hw())
        ph = mock.patch.object(hd, "detectar_hardware", self._hm)
        ph.start()
        self.addCleanup(ph.stop)

    def _page(self, executor=None):
        return DgvoodooPage(client_provider=lambda: "cli", executor=executor)

    def test_badge_auto_recomendado(self):
        page = self._page()
        self.assertEqual(page._profile_buttons[backend.PERFIL_AUTO].property("badge"),
                         "RECOMENDADO")

    def test_equilibrado_sem_badge(self):
        page = self._page()
        btn = page._profile_buttons[backend.PERFIL_BALANCED]
        self.assertIsNone(btn.property("badge"))
        self.assertTrue(btn._badge_label.isHidden())

    def test_badge_politica_nao_expande_horizontal(self):
        page = self._page()
        lbl = page._profile_buttons[backend.PERFIL_AUTO]._badge_label
        self.assertEqual(lbl.sizePolicy().horizontalPolicy(), QSizePolicy.Fixed)

    def test_badge_sizehint_compacto(self):
        page = self._page()
        lbl = page._profile_buttons[backend.PERFIL_AUTO]._badge_label
        self.assertGreater(lbl.sizeHint().width(), 0)
        self.assertLess(lbl.sizeHint().width(), 200)

    def test_badge_visivel_em_4_colunas_e_compacto(self):
        page = self._page()
        page.resize(1200, 800)
        page.show()
        QApplication.processEvents()
        self.assertTrue(page._profile_layout_wide)
        btn = page._profile_buttons[backend.PERFIL_AUTO]
        lbl = btn._badge_label
        self.assertFalse(lbl.isHidden())
        self.assertLess(lbl.width(), btn.width() // 2)
        page.hide()

    def test_badge_visivel_em_2x2_e_compacto(self):
        page = self._page()
        page.resize(640, 800)
        page.show()
        QApplication.processEvents()
        self.assertFalse(page._profile_layout_wide)
        btn = page._profile_buttons[backend.PERFIL_AUTO]
        lbl = btn._badge_label
        self.assertFalse(lbl.isHidden())
        self.assertLess(lbl.width(), btn.width() // 2)
        page.hide()

    def test_clique_no_badge_ativa_card(self):
        page = self._page()
        btn = page._profile_buttons[backend.PERFIL_AUTO]
        page.show()
        QApplication.processEvents()
        QTest.mouseClick(btn, Qt.LeftButton, Qt.NoModifier,
                         btn._badge_label.geometry().center())
        self.assertEqual(page._profile_selected, backend.PERFIL_AUTO)
        page.hide()

    def test_checked_nao_afetado_pelo_badge(self):
        page = self._page()
        page._mark_profile_applied(backend.PERFIL_AUTO)
        btn = page._profile_buttons[backend.PERFIL_AUTO]
        self.assertTrue(btn.isChecked())
        self.assertFalse(btn._badge_label.isHidden())

    def test_titulo_hardware_presente(self):
        page = self._page()
        self.assertIn("HARDWARE DETECTADO",
                      [c.text() for c in page.hardware_card.findChildren(QLabel)])

    def test_reanalisar_associado_ao_hardware_card(self):
        page = self._page()
        self.assertIs(page.reanalyze_button.parent(), page.hardware_card)

    def test_reanalisar_tem_icone_refresh(self):
        page = self._page()
        self.assertFalse(page.reanalyze_button.icon().isNull())

    def test_cabecalho_sem_overflow_largo_e_compacto(self):
        for w in (1200, 640):
            page = self._page()
            page.resize(w, 800)
            page.show()
            QApplication.processEvents()
            btn = page.reanalyze_button
            card = page.hardware_card
            self.assertLessEqual(btn.geometry().right(),
                                 card.geometry().right(), f"w={w}")
            page.hide()

    def test_reanalisar_via_botao_forca_nova_deteccao(self):
        page = self._page(executor=_executor_sync)
        page.show()
        QApplication.processEvents()
        self.assertEqual(self._hm.call_count, 1)
        page.reanalyze_button.click()
        self.assertEqual(self._hm.call_count, 2)
        page.hide()

    def test_reanalisar_via_botao_nao_aplica_perfil(self):
        page = self._page(executor=_executor_sync)
        page.show()
        QApplication.processEvents()
        with mock.patch.object(backend, "aplicar_perfil") as ap:
            page.reanalyze_button.click()
            ap.assert_not_called()
        page.hide()

    def test_hierarquia_recomendacao_distinta(self):
        page = self._page()
        self.assertEqual(page.hw_recomendacao_label.objectName(),
                         "DgvoodooHardwareRecValue")
        self.assertEqual(page.hw_gpu_label.objectName(), "DgvoodooHardwareInfo")
        self.assertEqual(page.hw_recomendacao_label.property("hw_value_role"),
                         "recomendacao")
        self.assertEqual(page.hw_gpu_label.property("hw_value_role"), "info")

    def test_confianca_possui_estado(self):
        page = self._page()
        self.assertEqual(page.hw_confianca_label.objectName(),
                         "DgvoodooHardwareConfValue")
        self.assertEqual(page.hw_confianca_label.property("hw_value_role"),
                         "confianca")

    def test_confianca_alta_verde(self):
        page = self._page(executor=_executor_sync)
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()):
            page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertIn("4CAF50", page.hw_confianca_label.styleSheet())
        self.assertIn("Alta", page.hw_confianca_label.text())

    def test_confianca_media_ambar(self):
        page = self._page(executor=_executor_sync)
        med = _perfil_hw(recomendado=hd.PERFIL_QUALITY,
                         confianca=hd.CONFIANCA_MEDIA)
        with mock.patch.object(hd, "detectar_hardware", return_value=med):
            page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertIn("FF9800", page.hw_confianca_label.styleSheet())
        self.assertIn("Média", page.hw_confianca_label.text())

    def test_confianca_baixa_alerta_fallback_legivel(self):
        page = self._page(executor=_executor_sync)
        fb = _perfil_hw(recomendado=hd.PERFIL_BALANCED,
                        confianca=hd.CONFIANCA_BAIXA)
        with mock.patch.object(hd, "detectar_hardware", return_value=fb):
            page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertIn("Baixa", page.hw_confianca_label.text())
        self.assertIn("F44336", page.hw_confianca_label.styleSheet())
        self.assertIn("Equilibrado", page.hw_recomendacao_label.text())

    def test_atualizar_resultado_atualiza_estado_visual(self):
        page = self._page(executor=_executor_sync)
        with mock.patch.object(hd, "detectar_hardware",
                               return_value=_perfil_hw()):
            page._on_profile_selected(backend.PERFIL_AUTO)
        self.assertIn("4CAF50", page.hw_confianca_label.styleSheet())
        page._exibir_falha_hardware()
        self.assertIn("Baixa", page.hw_confianca_label.text())
        self.assertIn("F44336", page.hw_confianca_label.styleSheet())


if __name__ == "__main__":
    unittest.main()

