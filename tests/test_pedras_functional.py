# -*- coding: utf-8 -*-
"""Testes não destrutivos da integração funcional de Cores das Pedras."""

import ast
import hashlib
import os
import sys
import tempfile
import time
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import itemlist6_color_engine as engine  # noqa: E402
import stone_color_page as page_module  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


PROFILE_PATH = ROOT / "itemlist6_color_profile.json"


def compatible_binary(profile: engine.ColorProfile) -> bytes:
    size = engine.HEADER_SIZE + 31_000 * engine.RECORD_SIZE + engine.TRAILER_SIZE
    data = bytearray(size)
    data[:engine.HEADER_SIZE] = engine.EXPECTED_HEADER
    for entry in profile.entries:
        data[engine.color_offset(entry.record_id)] = entry.reference_source_byte
    data[-engine.TRAILER_SIZE:] = (123456789).to_bytes(engine.TRAILER_SIZE, "little")
    return bytes(data)


class TestPedrasFunctional(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.profile = engine.load_profile(PROFILE_PATH)
        cls.valid_data = compatible_binary(cls.profile)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.client = self.base / "Cliente"
        self.client.mkdir()
        self.output = self.base / "Saidas"

    def write_valid(self, relative="ItemList6.bin"):
        path = self.client / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.valid_data)
        return path

    def wait_page(self, page, timeout=10):
        deadline = time.monotonic() + timeout
        while page.active_thread is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()
        self.assertIsNone(page.active_thread)

    def test_01_cliente_nao_configurado(self):
        result = page_module.detect_itemlist6(None, PROFILE_PATH)
        self.assertEqual(result.state, page_module.STATE_ERROR)
        self.assertEqual(result.message, page_module.CLIENT_NOT_CONFIGURED)
        self.assertIsNone(result.selected)

    def test_02_arquivo_nao_encontrado(self):
        result = page_module.detect_itemlist6(self.client, PROFILE_PATH)
        self.assertEqual(result.candidates, ())
        self.assertIn("não foi encontrado", result.message)

    def test_03_arquivo_na_raiz_compativel(self):
        source = self.write_valid()
        result = page_module.detect_itemlist6(self.client, PROFILE_PATH)
        self.assertEqual(result.state, page_module.STATE_COMPATIBLE)
        self.assertEqual(result.selected.path, source.resolve())
        self.assertEqual(result.selected.compatible_records, 438)

    def test_04_arquivo_incompativel(self):
        data = bytearray(self.valid_data)
        data[engine.color_offset(self.profile.entries[0].record_id)] ^= 1
        (self.client / "ItemList6.bin").write_bytes(data)
        result = page_module.detect_itemlist6(self.client, PROFILE_PATH)
        self.assertEqual(result.state, page_module.STATE_INCOMPATIBLE)
        self.assertIsNone(result.selected)
        self.assertEqual(len(result.incompatible), 1)

    def test_05_raiz_e_ui_usam_somente_raiz(self):
        root_file = self.write_valid("ItemList6.bin")
        self.write_valid("UI/ItemList6.bin")
        result = page_module.detect_itemlist6(self.client, PROFILE_PATH)
        self.assertEqual(result.state, page_module.STATE_COMPATIBLE)
        self.assertEqual(result.selected.path, root_file.resolve())
        self.assertEqual(result.candidates, (root_file.resolve(),))

    def test_06_padrao_e_somente_cores_confirmadas(self):
        page = page_module.StoneColorPage(lambda: None, PROFILE_PATH, self.output)
        self.addCleanup(page.deleteLater)
        self.assertEqual(page.selected_codes(), (8, 7, 0))
        codes = [page.attack_combo.itemData(i) for i in range(page.attack_combo.count())]
        self.assertEqual(codes, [0, 4, 5, 6, 7, 8, 9])
        self.assertNotIn(1, codes)
        self.assertNotIn(2, codes)
        self.assertNotIn(3, codes)

    def test_07_geracao_nao_sobrescreve_entrada(self):
        source = self.write_valid()
        original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        analysis = page_module.detect_itemlist6(self.client, PROFILE_PATH).selected
        generated = page_module.generate_validated_copy(
            self.client, PROFILE_PATH, self.output, source, analysis.sha256, 8, 7, 0
        )
        self.assertNotEqual(generated.published.path, source)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original_hash)
        self.assertTrue(generated.published.path.is_file())

    def test_08_recusa_hash_alterado_apos_analise(self):
        source = self.write_valid()
        analysis = page_module.detect_itemlist6(self.client, PROFILE_PATH).selected
        changed = bytearray(source.read_bytes())
        changed[engine.HEADER_SIZE + 10] ^= 1
        source.write_bytes(changed)
        with self.assertRaises(engine.InputChangedError):
            page_module.generate_validated_copy(
                self.client, PROFILE_PATH, self.output, source, analysis.sha256, 8, 7, 0
            )
        self.assertFalse(self.output.exists())

    def test_09_diretorio_automatico_localappdata(self):
        local = self.base / "LocalAppData"
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
            output = page_module.default_output_directory()
        self.assertEqual(output, local / "AIKA Optimizer" / "Pedras" / "Gerados")
        self.assertFalse(str(output).startswith(str(ROOT)))

    def test_10_saida_validada_pelo_engine(self):
        source = self.write_valid()
        analysis = page_module.detect_itemlist6(self.client, PROFILE_PATH).selected
        generated = page_module.generate_validated_copy(
            self.client, PROFILE_PATH, self.output, source, analysis.sha256, 8, 7, 0
        )
        validated = engine.validate_output(
            source.read_bytes(), generated.published.path.read_bytes(), self.profile,
            attack_code=8, defense_code=7, common_code=0,
        )
        self.assertEqual(validated.sha256, generated.published.result.sha256)
        self.assertEqual(
            validated.attack_count + validated.defense_count + validated.common_count, 438
        )

    def test_11_uma_unica_qapplication_na_producao(self):
        calls = []
        for name in ("main.py", "stone_color_page.py"):
            tree = ast.parse((ROOT / name).read_text(encoding="utf-8-sig"))
            calls.extend(
                node for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "QApplication"
            )
        self.assertEqual(len(calls), 1)

    def test_12_pagina_permanece_no_indice_10(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8-sig")
        calls = [
            match.strip()
            for match in __import__("re").findall(
                r"self\.telas\.addWidget\(([^\n]+)\)", source
            )
        ]
        # Páginas de Pedras (10) e Renderizador (11) continuam antes da Ajuda,
        # que é a página final (12) e não desloca os índices anteriores.
        self.assertEqual(len(calls), 13)
        self.assertEqual(calls[-1], "self.ajuda_page")
        self.assertEqual(calls[-2], "self.dgvoodoo_page")
        self.assertEqual(calls[-3], "self.pedras_page")
        self.assertIn('criar_botao_menu("Pedras", 10', source)
        self.assertIn('criar_botao_menu("Renderizador", 11', source)
        self.assertIn('criar_botao_menu("Ajuda", 12', source)

    def test_13_worker_encerra_sem_thread_abandonada(self):
        self.write_valid()
        page = page_module.StoneColorPage(
            lambda: str(self.client), PROFILE_PATH, self.output
        )
        self.addCleanup(page.deleteLater)
        self.assertTrue(page.analyze_again())
        self.wait_page(page)
        self.assertIsNotNone(page.recognition)
        self.assertTrue(page.shutdown(1000))
        self.assertIsNone(page.active_thread)

    def test_14_perfil_relativo_e_conteudo(self):
        self.assertEqual(page_module.DEFAULT_PROFILE_PATH, PROFILE_PATH.resolve())
        counts = Counter(entry.group for entry in self.profile.entries)
        self.assertEqual(len(self.profile.entries), 438)
        self.assertEqual(counts, {"attack": 60, "defense": 60, "common": 318})

    def test_15_perfil_presente_nos_datas_do_spec(self):
        spec = (ROOT / "Aika_Optimizer_V4.1.spec").read_text(encoding="utf-8")
        self.assertIn("('itemlist6_color_profile.json', '.')", spec)

    def test_16_aceita_executavel_configurado_na_raiz(self):
        executable = self.client / "Aika.exe"
        executable.write_bytes(b"MZ")
        expected = self.write_valid("ItemList6.bin")
        result = page_module.detect_itemlist6(executable, PROFILE_PATH)
        self.assertEqual(result.selected.path, expected.resolve())
        self.assertEqual(result.candidates, (expected.resolve(),))

    def test_17_recusa_saida_dentro_do_cliente(self):
        source = self.write_valid()
        analysis = page_module.detect_itemlist6(self.client, PROFILE_PATH).selected
        with self.assertRaises(engine.UnsafeOutputPathError):
            page_module.generate_validated_copy(
                self.client, PROFILE_PATH, self.client / "Gerados",
                source, analysis.sha256, 8, 7, 0,
            )

    def test_18_geracao_assincrona_finaliza_sem_alterar_entrada(self):
        source = self.write_valid()
        original = hashlib.sha256(source.read_bytes()).hexdigest()
        page = page_module.StoneColorPage(
            lambda: str(self.client), PROFILE_PATH, self.output
        )
        self.addCleanup(page.deleteLater)
        page._analysis = page_module.detect_itemlist6(
            self.client, PROFILE_PATH
        ).selected
        page._set_state(page_module.STATE_COMPATIBLE, "pronto")
        self.assertTrue(page.generate_copy())
        self.wait_page(page, timeout=15)
        self.assertIsNotNone(page.published)
        self.assertTrue(page.published.path.is_file())
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original)
        self.assertTrue(page.shutdown(1000))

    def test_19_ausente_na_raiz_presente_em_ui_informa_ausencia(self):
        self.write_valid("UI/ItemList6.bin")
        result = page_module.detect_itemlist6(self.client, PROFILE_PATH)
        self.assertEqual(result.state, page_module.STATE_ERROR)
        self.assertEqual(result.candidates, ())
        self.assertIn("não foi encontrado na raiz", result.message)

    def test_20_raiz_incompativel_ui_compativel_recusa_raiz(self):
        bad = bytearray(self.valid_data)
        bad[engine.color_offset(self.profile.entries[0].record_id)] ^= 1
        (self.client / "ItemList6.bin").write_bytes(bad)
        self.write_valid("UI/ItemList6.bin")
        result = page_module.detect_itemlist6(self.client, PROFILE_PATH)
        self.assertEqual(result.state, page_module.STATE_INCOMPATIBLE)
        self.assertIsNone(result.selected)
        self.assertEqual(len(result.incompatible), 1)
        self.assertEqual(
            result.incompatible[0].path, (self.client / "ItemList6.bin").resolve()
        )

    def test_21_shutdown_durante_operacao_nao_abandona_thread(self):
        self.write_valid()
        page = page_module.StoneColorPage(
            lambda: str(self.client), PROFILE_PATH, self.output
        )
        self.addCleanup(page.deleteLater)
        real_analyze = page_module.engine.analyze_file

        def slow_analyze(path, profile):
            time.sleep(0.5)
            return real_analyze(path, profile)

        with patch.object(page_module.engine, "analyze_file", side_effect=slow_analyze):
            self.assertTrue(page.analyze_again())
            deadline = time.monotonic() + 3
            while (
                time.monotonic() < deadline
                and not (page.active_thread is not None and page.active_thread.isRunning())
            ):
                self.app.processEvents()
                time.sleep(0.01)
            self.assertTrue(
                page.active_thread is not None and page.active_thread.isRunning()
            )
            self.assertTrue(page.shutdown(5000))
        for _ in range(50):
            self.app.processEvents()
            time.sleep(0.01)
        self.assertIsNone(page.active_thread)


if __name__ == "__main__":
    unittest.main(verbosity=2)