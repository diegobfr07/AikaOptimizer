# -*- coding: utf-8 -*-
"""Central de Ajuda — navegação por categoria (V4.1).

Comprova a nova experiência: 12 cards no topo, apenas UM selecionado e
somente o conteúdo da categoria escolhida é exibido abaixo.

Cobre: seleção inicial em Performance, troca de categoria por clique,
um único conteúdo visível por vez, scroll por categoria (topo ao trocar,
vertical ligado, horizontal desligado), card selecionado distinguível,
hover sem trocar seleção, layout 4x3, ausência de backend/cliente,
posição da Ajuda na sidebar, conteúdo editorial e resoluções alvo.
"""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import help_page  # noqa: E402
from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QFrame,
    QLabel,
    QStackedWidget,
)

_app = QApplication.instance() or QApplication([])

import main  # noqa: E402
import config  # noqa: E402

ROTULOS_ESPERADOS = (
    "Performance",
    "Sistema",
    "AutoMod",
    "Áudio",
    "Texturas (.JIT)",
    "Org. Sets",
    "Injetor Sets/Arm",
    "Pedras",
    "Renderizador",
    "Restauração",
    "Segurança",
    "Configurações",
)

IDS_ESPERADOS = (
    "performance",
    "sistema",
    "automod",
    "audio",
    "texturas",
    "org_sets",
    "injetor",
    "pedras",
    "renderizador",
    "restauracao",
    "seguranca",
    "configuracoes",
)

# Rótulos compactos exibidos nos cards (o conteúdo mantém o título completo).
CARDS_ESPERADOS = (
    "Performance",
    "Sistema",
    "AutoMod",
    "Áudio",
    "Texturas",
    "Org. Sets",
    "Injetor",
    "Pedras",
    "Renderizador",
    "Restauração",
    "Segurança",
    "Configurações",
)

# Layout padrão pedido: 4 colunas x 3 linhas, na ordem das categorias.
GRID_ESPERADO = tuple((i // 4, i % 4) for i in range(12))


def _fonte_main():
    return Path(main.__file__).read_text(encoding="utf-8")


def _fonte_help():
    return Path(help_page.__file__).read_text(encoding="utf-8")


def _regra_qss(seletor):
    """Extrai a regra de estilo (texto entre '{' e '}') de um seletor."""
    fonte = _fonte_help()
    inicio = fonte.index(seletor + " {")
    fim = fonte.index("}", inicio)
    return fonte[inicio:fim]


def _encerrar_janela(janela):
    """Fecha a janela sem disparar o cleanup pesado de shutdown (testes)."""
    janela._force_exit = True
    janela.close()
    _app.processEvents()
    janela.deleteLater()
    _app.processEvents()


def _janela():
    """Instancia a janela principal com cliente falso (sem tocar disco)."""
    pasta = tempfile.mkdtemp(prefix="aika_help_test_")
    with mock.patch.object(main.opt, "obter_pasta_jogo_atual", return_value=pasta), \
         mock.patch.object(config, "ARQUIVO_CONFIG", os.path.join(pasta, "config.json")), \
         mock.patch.object(config, "PASTA_BACKUP", os.path.join(pasta, "backup")), \
         mock.patch.object(config, "PASTA_JOGO_PADRAO", pasta):
        janela = main.AikaOptimizerPro()
    janela.setMinimumSize(1, 1)
    return janela

class TestNavegacaoPorCategoria(unittest.TestCase):
    """12 cards, seleção única e conteúdo exclusivo da categoria ativa."""

    def setUp(self):
        self.page = help_page.HelpPage()
        self.page.setMinimumSize(1, 1)
        self.page.resize(796, 508)
        self.page.show()
        _app.processEvents()
        self.addCleanup(self.page.deleteLater)

    def _visiveis(self):
        return [
            ident
            for ident, pagina in self.page._paginas.items()
            if pagina.isVisible()
        ]

    def test_01_existem_12_cards_de_categoria(self):
        self.assertEqual(len(self.page.categorias()), 12)
        self.assertEqual(len(self.page.cards()), 12)
        self.assertEqual(
            tuple(b.text() for b in self.page.cards()), CARDS_ESPERADOS
        )
        self.assertEqual(help_page.rotulos_dos_cards(), CARDS_ESPERADOS)
        # Os títulos completos permanecem no conteúdo das categorias.
        self.assertEqual(help_page.rotulos_das_secoes(), ROTULOS_ESPERADOS)

    def test_02_performance_e_selecionado_inicialmente(self):
        self.assertEqual(self.page.categoria_atual(), "performance")
        self.assertTrue(
            self.page.botao_da_categoria("performance").isChecked()
        )

    def test_03_apenas_um_card_possui_estado_selecionado(self):
        marcados = [b for b in self.page.cards() if b.isChecked()]
        self.assertEqual(len(marcados), 1)

    def test_04_clicar_sistema_seleciona_sistema(self):
        self.page.botao_da_categoria("sistema").click()
        _app.processEvents()
        self.assertEqual(self.page.categoria_atual(), "sistema")
        self.assertTrue(self.page.botao_da_categoria("sistema").isChecked())

    def test_05_performance_deixa_de_estar_selecionada(self):
        self.page.botao_da_categoria("sistema").click()
        _app.processEvents()
        self.assertFalse(
            self.page.botao_da_categoria("performance").isChecked()
        )
        self.assertEqual(
            sum(1 for b in self.page.cards() if b.isChecked()), 1
        )

    def test_06_stack_muda_para_sistema(self):
        self.page.botao_da_categoria("sistema").click()
        _app.processEvents()
        self.assertIs(
            self.page._stack.currentWidget(),
            self.page.scroll_da_categoria("sistema"),
        )
        self.assertIsInstance(self.page._stack, QStackedWidget)

    def test_07_somente_conteudo_de_sistema_visivel(self):
        self.page.botao_da_categoria("sistema").click()
        _app.processEvents()
        self.assertEqual(self._visiveis(), ["sistema"])

    def test_08_clicar_pedras_mostra_somente_pedras(self):
        self.page.botao_da_categoria("pedras").click()
        _app.processEvents()
        self.assertEqual(self.page.categoria_atual(), "pedras")
        self.assertEqual(self._visiveis(), ["pedras"])

    def test_09_clicar_renderizador_mostra_somente_renderizador(self):
        self.page.botao_da_categoria("renderizador").click()
        _app.processEvents()
        self.assertEqual(self.page.categoria_atual(), "renderizador")
        self.assertEqual(self._visiveis(), ["renderizador"])

    def test_10_cada_card_aponta_para_a_secao_correta(self):
        for ident in IDS_ESPERADOS:
            with self.subTest(categoria=ident):
                self.page.botao_da_categoria(ident).click()
                _app.processEvents()
                self.assertEqual(self.page.categoria_atual(), ident)
                self.assertEqual(self._visiveis(), [ident])

    def test_11_sem_conteudos_empilhados_simultaneamente(self):
        for ident in IDS_ESPERADOS:
            self.page.selecionar_categoria(ident)
            _app.processEvents()
            visiveis = self._visiveis()
            self.assertEqual(len(visiveis), 1, f"empilhado em {ident}")
            self.assertEqual(self.page._stack.count(), 12)
    def test_12_troca_de_categoria_reposiciona_scroll_no_topo(self):
        barra = self.page.scroll_da_categoria("performance").verticalScrollBar()
        self.page.selecionar_categoria("performance")
        barra.setValue(barra.maximum())
        self.assertGreater(barra.value(), 0)
        self.page.selecionar_categoria("sistema")
        self.page.selecionar_categoria("performance")
        _app.processEvents()
        self.assertEqual(barra.value(), 0)

    def test_13_scroll_vertical_funciona_em_categoria_longa(self):
        maxima = 0
        for ident in IDS_ESPERADOS:
            self.page.selecionar_categoria(ident)
            _app.processEvents()
            maxima = max(
                maxima,
                self.page.scroll_da_categoria(ident)
                .verticalScrollBar()
                .maximum(),
            )
        self.assertGreater(maxima, 0)

    def test_14_horizontal_scrollbar_permanece_desativada(self):
        for ident in IDS_ESPERADOS:
            scroll = self.page.scroll_da_categoria(ident)
            with self.subTest(categoria=ident):
                self.assertEqual(
                    scroll.horizontalScrollBarPolicy(),
                    help_page.Qt.ScrollBarAlwaysOff,
                )
                self.assertEqual(
                    scroll.horizontalScrollBar().maximum(), 0
                )

    def test_15_card_selecionado_tem_estado_distinguivel(self):
        ativo = self.page.botao_da_categoria("performance")
        inativo = self.page.botao_da_categoria("sistema")
        self.assertTrue(ativo.isChecked())
        self.assertFalse(inativo.isChecked())
        self.assertEqual(ativo.property("categoria"), "performance")
        # Regra visual de destaque existe para o estado :checked.
        self.assertIn("HelpNavButton:checked", _fonte_help())
        self.assertIn("#BF00FF", _fonte_help())

    def test_16_hover_nao_altera_selecao(self):
        alvo = self.page.botao_da_categoria("pedras")
        _app.sendEvent(alvo, QEvent(QEvent.Enter))
        _app.sendEvent(alvo, QEvent(QEvent.HoverEnter))
        _app.processEvents()
        self.assertFalse(alvo.isChecked())
        self.assertEqual(self.page.categoria_atual(), "performance")
        _app.sendEvent(alvo, QEvent(QEvent.Leave))

    def test_17_layout_4_colunas_por_3_linhas(self):
        grid = self.page._cards_grid
        posicoes = []
        for indice in range(grid.count()):
            linha, coluna = grid.getItemPosition(indice)[:2]
            posicoes.append((linha, coluna))
        self.assertEqual(tuple(posicoes), GRID_ESPERADO)

    def test_18_cards_compactos_sem_descricao(self):
        for botao in self.page.cards():
            with self.subTest(card=botao.text()):
                self.assertNotIn("\n", botao.text())
                self.assertLessEqual(botao.height(), 46)
                self.assertGreaterEqual(botao.minimumHeight(), 24)
                # Nenhum rótulo pode ser cortado no card.
                self.assertGreaterEqual(
                    botao.width(), botao.sizeHint().width()
                )

    def test_19_titulo_completo_no_conteudo_da_categoria(self):
        for ident, rotulo in zip(IDS_ESPERADOS, ROTULOS_ESPERADOS):
            pagina = self.page.scroll_da_categoria(ident)
            cabecalho = pagina.widget().findChild(QLabel, "HelpSectionTitle")
            with self.subTest(categoria=ident):
                self.assertIsNotNone(cabecalho)
                self.assertEqual(cabecalho.text(), rotulo)


class TestIntegracaoEBackend(unittest.TestCase):
    """A página continua integrada à sidebar e não executa backend."""

    def test_19_pagina_ajuda_existe_e_na_posicao(self):
        fonte = _fonte_main()
        self.assertIn("from help_page import HelpPage", fonte)
        self.assertIn('criar_botao_menu("Ajuda", 12', fonte)
        self.assertIn("self.ajuda_page = HelpPage()", fonte)
        self.assertIn("self.telas.addWidget(self.ajuda_page)", fonte)

    def test_20_configuracoes_continua_ultima_pagina_da_sidebar(self):
        fonte = _fonte_main()
        ajuda = fonte.index("layout_sidebar.addWidget(self.btn_aba_ajuda)")
        config = fonte.index("layout_sidebar.addWidget(self.btn_aba_config)")
        self.assertLess(ajuda, config)
        trecho = fonte[
            config + len("layout_sidebar.addWidget(self.btn_aba_config)"):
            config + 400
        ]
        self.assertNotIn("addWidget(self.btn_aba_", trecho)

    def test_21_abrir_ajuda_nao_executa_backend(self):
        janela = _janela()
        try:
            self.assertEqual(janela.telas.currentIndex(), 0)
            with mock.patch.object(janela, "executar_em_background") as spy:
                janela.telas.setCurrentIndex(12)
                _app.processEvents()
                self.assertEqual(janela.telas.currentIndex(), 12)
                pagina = janela.ajuda_page
                pagina.botao_da_categoria("sistema").click()
                pagina.botao_da_categoria("pedras").click()
                pagina.botao_da_categoria("configuracoes").click()
                _app.processEvents()
                self.assertEqual(pagina.categoria_atual(), "configuracoes")
                spy.assert_not_called()
        finally:
            _encerrar_janela(janela)

class TestConteudoEditorial(unittest.TestCase):
    """Conteúdo preservado, sem links quebrados/placeholders e enxuto."""

    def test_22_conteudo_sem_links_quebrados(self):
        conteudo = "\n".join(help_page.coletar_textos())
        for sinal in ("http://", "https://", "www.", "](", "#/"):
            self.assertNotIn(sinal, conteudo)

    def test_23_conteudo_sem_placeholders_ou_todo(self):
        conteudo = "\n".join(help_page.coletar_textos())
        for marcador in ("TODO", "FIXME", "XXX", "LOREM", "PLACEHOLDER",
                         "INSIRA"):
            self.assertIsNone(
                re.search(rf"\b{marcador}\b", conteudo, re.IGNORECASE),
                f"Marcador residual encontrado: {marcador}",
            )

    def test_24_blocos_com_tipos_validos(self):
        permitidos = {"p", "oque", "quando", "como", "altera",
                      "desfazer", "compat", "aviso"}
        for secao in help_page.HELP_SECTIONS:
            for tema in secao["temas"]:
                self.assertTrue(tema["blocos"])
                for tipo, paragrafos in tema["blocos"]:
                    self.assertIn(tipo, permitidos)
                    self.assertTrue(paragrafos)

    def test_25_avisos_reservados_a_risco_real(self):
        avisos = 0
        for secao in help_page.HELP_SECTIONS:
            for tema in secao["temas"]:
                for tipo, _paragrafos in tema["blocos"]:
                    if tipo == "aviso":
                        avisos += 1
        # Sem poluição: poucas caixas de alerta, todas com risco real.
        self.assertGreaterEqual(avisos, 1)
        self.assertLessEqual(avisos, 3)


class TestEditorialFinal(unittest.TestCase):
    """Pente-fino final: fidelidade ao comportamento real e português."""

    @classmethod
    def setUpClass(cls):
        cls.textos = tuple(help_page.coletar_textos())

    def _contem(self, trecho):
        return any(trecho in t for t in self.textos)

    def test_32_otimizacao_global_tenta_iniciar_o_aika(self):
        self.assertTrue(self._contem("Se o AIKA estiver fechado"))
        self.assertTrue(self._contem("tentará abri-lo ao concluir"))
        self.assertFalse(self._contem("Abra o jogo normalmente"))

    def test_33_injetor_sem_instrucao_fixa_set_alvo(self):
        self.assertTrue(self._contem("Escolha a aparência doadora"))
        self.assertTrue(
            self._contem("Escolha o item alvo que receberá a aparência")
        )
        for texto in self.textos:
            self.assertNotIn("Em SET ALVO", texto)
            self.assertNotIn("Em ARMA ALVO", texto)

    def test_34_iniciar_minimizado_contextualizado_com_windows(self):
        candidatos = [t for t in self.textos if "Iniciar minimizado" in t]
        self.assertTrue(candidatos)
        self.assertTrue(all("Windows" in t for t in candidatos))

    def test_35_auto_boost_uma_vez_por_nova_sessao(self):
        candidatos = [t for t in self.textos if "Auto Boost" in t]
        self.assertTrue(candidatos)
        self.assertTrue(
            any("nova sessão" in t and "uma vez" in t for t in candidatos)
        )

    def test_36_renderizador_sem_frase_ambigua_de_fps(self):
        self.assertFalse(self._contem("não há garantia de FPS"))
        self.assertTrue(self._contem("aumento de FPS"))

    def test_37_dns_com_redacao_natural(self):
        self.assertTrue(self._contem("configuração automática do Windows"))
        self.assertFalse(self._contem("restaurar o automático"))

    def test_38_jit_duplo_clique_correto(self):
        self.assertTrue(self._contem("ao dar dois cliques"))
        self.assertFalse(self._contem("dois cliques em um .JIT convertem"))

    def test_39_org_sets_manual_e_nomes_preservados(self):
        self.assertTrue(self._contem("Executar novamente copia apenas"))
        self.assertFalse(self._contem("Rodar de novo"))
        # Templaria/Cleriga são nomes reais de pasta do Organizador: preservar.
        self.assertTrue(self._contem("Templaria"))
        self.assertTrue(self._contem("Cleriga"))

    def test_40_portugues_sem_mojibake_ou_espaco_duplo(self):
        mojibake = ("Ã£", "Ã©", "Ã¡", "Ã³", "Ãº", "Ã§", "Ãµ", "Ãª", "Ã­",
                    "Ã‡", "Ã‰", "Ãƒ")
        for texto in self.textos:
            for sequencia in mojibake:
                self.assertNotIn(sequencia, texto)
            self.assertNotIn("  ", texto)


class TestHierarquiaVisual(unittest.TestCase):
    """Hierarquia: função em roxo, subtítulos neutros, sem 'O QUE FAZ'."""

    def setUp(self):
        self.page = help_page.HelpPage()
        self.page.setMinimumSize(1, 1)
        self.page.resize(796, 508)
        self.page.show()
        _app.processEvents()
        self.addCleanup(self.page.deleteLater)

    def _rotulos(self, ident):
        pagina = self.page.scroll_da_categoria(ident)
        return [lbl.text() for lbl in pagina.widget().findChildren(QLabel)]

    def test_26_nome_da_funcao_usa_destaque_roxo(self):
        regra = _regra_qss("QLabel#HelpThemeTitle")
        self.assertIn("#BF00FF", regra)
        self.assertIn("14px", regra)
        self.assertIn("bold", regra)

    def test_27_subtitulos_nao_usam_roxo(self):
        regra = _regra_qss("QLabel#HelpBlockLabel")
        self.assertNotIn("#BF00FF", regra)
        self.assertIn("#D6D6DE", regra)
        self.assertIn("11px", regra)

    def test_28_o_que_faz_nao_e_renderizado(self):
        for ident in IDS_ESPERADOS:
            with self.subTest(categoria=ident):
                self.assertNotIn("O QUE FAZ", self._rotulos(ident))

    def test_29_tipo_oque_preservado_semanticamente(self):
        tipos = {
            tipo
            for secao in help_page.HELP_SECTIONS
            for tema in secao["temas"]
            for tipo, _p in tema["blocos"]
        }
        self.assertIn("oque", tipos)
        self.assertIn("oque", help_page._SEM_ROTULO)

    def test_30_subtitulos_auxiliares_em_sentence_case(self):
        self.assertEqual(help_page._LABEL_BLOCO["quando"], "Quando usar")
        self.assertEqual(help_page._LABEL_BLOCO["como"], "Como usar")
        self.assertEqual(help_page._LABEL_BLOCO["altera"], "O que muda")
        self.assertEqual(help_page._LABEL_BLOCO["desfazer"], "Como desfazer")
        self.assertEqual(help_page._LABEL_BLOCO["compat"], "Compatibilidade")
        visiveis = set()
        for ident in IDS_ESPERADOS:
            visiveis.update(self._rotulos(ident))
        for rotulo in ("Quando usar", "Como usar", "O que muda",
                       "Como desfazer", "Compatibilidade"):
            self.assertIn(rotulo, visiveis)

    def test_31_aviso_so_onde_ha_risco_real(self):
        # Modo Agressivo (Performance) mantém caixa de aviso.
        perf = self.page.scroll_da_categoria("performance")
        self.assertTrue(perf.widget().findChildren(QFrame, "HelpWarning"))
        # Injetor avisa que a injeção é bloqueada com o jogo aberto.
        inj = self.page.scroll_da_categoria("injetor")
        self.assertTrue(inj.widget().findChildren(QFrame, "HelpWarning"))
        # AutoMod trata compatibilidade como texto neutro, sem caixa vermelha.
        auto = self.page.scroll_da_categoria("automod")
        self.assertEqual(
            auto.widget().findChildren(QFrame, "HelpWarning"), []
        )
        self.assertIn("Compatibilidade", self._rotulos("automod"))


class TestSomenteLeitura(unittest.TestCase):
    """A página Ajuda não pode tocar backend, sistema ou cliente."""

    PROIBIDOS = (
        "winreg",
        "subprocess",
        "ctypes",
        "psutil",
        "shutil",
        "QThread",
        "executar_em_background",
        "obter_pasta_jogo",
        "registrar_integracao_windows",
        "desregistrar_integracao_windows",
    )

    def test_26_nenhuma_funcao_chama_backend_mutavel(self):
        fonte = _fonte_help()
        for proibido in self.PROIBIDOS:
            self.assertNotIn(proibido, fonte)
        imports = [
            linha.strip()
            for linha in fonte.splitlines()
            if linha.startswith(("import ", "from "))
        ]
        for linha in imports:
            if linha.startswith("from PySide6"):
                continue
            self.assertTrue(
                linha.startswith("from __future__")
                or linha.startswith("from typing"),
                f"Importação de backend na Ajuda: {linha}",
            )

    def test_27_nenhum_cliente_aika_e_tocado(self):
        fonte = _fonte_help()
        for sinal in ("ItemList6", "AIKA_GAME_EXES", "PASTA_JOGO_PADRAO",
                      "Data\\Effect", "caminho_seguro", "fazer_backup"):
            self.assertNotIn(sinal, fonte)


class TestResolucoes(unittest.TestCase):
    """Renderiza nas resoluções alvo: um conteúdo, cards legíveis, sem scroll X."""

    def _medir(self, largura, altura):
        janela = _janela()
        try:
            janela.resize(largura, altura)
            janela.show()
            janela.telas.setCurrentIndex(12)
            _app.processEvents()
            pagina = janela.ajuda_page
            self.assertEqual(janela.telas.currentIndex(), 12)
            self.assertEqual(pagina.width(), janela.telas.width())

            visiveis = [
                ident
                for ident, p in pagina._paginas.items()
                if p.isVisible()
            ]
            self.assertEqual(visiveis, ["performance"])

            for botao in pagina.cards():
                self.assertGreater(botao.width(), 0)
                self.assertLessEqual(botao.height(), 46)
                self.assertTrue(botao.text())
                self.assertGreaterEqual(
                    botao.width(), botao.sizeHint().width(),
                    f"Card cortado em {largura}x{altura}: {botao.text()}",
                )

            scroll = pagina.scroll_da_categoria("performance")
            self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
            self.assertGreater(scroll.verticalScrollBar().maximum(), 0)

            posicoes = [
                pagina._cards_grid.getItemPosition(i)[:2]
                for i in range(pagina._cards_grid.count())
            ]
            self.assertEqual(tuple(posicoes), GRID_ESPERADO)
        finally:
            _encerrar_janela(janela)

    def test_28_renderiza_em_1024x680(self):
        self._medir(1024, 680)

    def test_29_renderiza_em_1366x728(self):
        self._medir(1366, 728)

    def test_30_renderiza_em_1920x1040(self):
        self._medir(1920, 1040)


if __name__ == "__main__":
    unittest.main(verbosity=2)



