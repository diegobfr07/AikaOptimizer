# -*- coding: utf-8 -*-
"""Testes de integração do sincronismo de estado Pedras × Restauração."""

import hashlib
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import itemlist6_color_engine as engine  # noqa: E402
import stone_color_service as service  # noqa: E402

PROFILE_PATH = ROOT / "itemlist6_color_profile.json"


def _compatible_bytes(profile, trailer=123456789):
    size = engine.HEADER_SIZE + 31_000 * engine.RECORD_SIZE + engine.TRAILER_SIZE
    data = bytearray(size)
    data[: engine.HEADER_SIZE] = engine.EXPECTED_HEADER
    for entry in profile.entries:
        data[engine.color_offset(entry.record_id)] = entry.reference_source_byte
    data[-engine.TRAILER_SIZE:] = trailer.to_bytes(engine.TRAILER_SIZE, "little")
    return bytes(data)


def _sha(data):
    return hashlib.sha256(data).hexdigest().upper()


class TestStateSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = engine.load_profile(PROFILE_PATH)
        cls.valid = _compatible_bytes(cls.profile)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.client = self.base / "Cliente"
        self.client.mkdir()
        self.store = self.base / "store"
        self.out = self.base / "Saidas"
        patcher = patch.object(
            service, "detect_relevant_processes",
            return_value=service.ProcessDetection((), None),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write_valid(self, data=None):
        path = self.client / "ItemList6.bin"
        path.write_bytes(data if data is not None else self.valid)
        return path

    def _apply(self, a=8, d=7, c=0):
        prepared = service.prepare_colors(
            str(self.client), PROFILE_PATH, self.out, a, d, c, self.store,
        )
        return service.apply_prepared(prepared, PROFILE_PATH, self.store)

    def _wait(self, page, app, timeout=20):
        deadline = time.monotonic() + timeout
        while page.active_thread is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()
        self.assertIsNone(page.active_thread)

    def test_apply_then_recognize_personalized(self):
        self._write_valid()
        self._apply(8, 7, 0)
        rec = service.recognize_state(str(self.client), PROFILE_PATH, self.store)
        self.assertEqual(rec.kind, service.KIND_PERSONALIZED)
        self.assertTrue(rec.base_valid)
        self.assertEqual(rec.base_compatible_records, 438)
        self.assertEqual(rec.applied_colors, (8, 7, 0))

    def test_new_session_recognizes_personalized_and_enables_generation(self):
        from PySide6.QtWidgets import QApplication
        import stone_color_page as page_module
        app = QApplication.instance() or QApplication([])
        self._write_valid()
        self._apply(8, 7, 0)
        page = page_module.StoneColorPage(
            lambda: str(self.client), PROFILE_PATH, self.out, storage_base=self.store,
        )
        self.addCleanup(page.deleteLater)
        self.assertTrue(page.analyze_again())
        self._wait(page, app)
        self.assertEqual(page.recognition.kind, service.KIND_PERSONALIZED)
        self.assertTrue(page.recognition.base_valid)
        self.assertEqual(page._state, page_module.STATE_PERSONALIZED)
        self.assertTrue(page._analysis_valid())
        self.assertEqual(page.action_button.text(), "Gerar cópia")
        self.assertTrue(page.action_button.isEnabled())
        self.assertIn("base verificada: 438/438", page.file_labels["compatibility"].text())
    def test_reanalyze_known_output_not_incompatible(self):
        from PySide6.QtWidgets import QApplication
        import stone_color_page as page_module
        app = QApplication.instance() or QApplication([])
        self._write_valid()
        self._apply(8, 7, 0)
        page = page_module.StoneColorPage(
            lambda: str(self.client), PROFILE_PATH, self.out, storage_base=self.store,
        )
        self.addCleanup(page.deleteLater)
        self.assertTrue(page.analyze_again())
        self._wait(page, app)
        self.assertTrue(page.analyze_again())
        self._wait(page, app)
        self.assertEqual(page.recognition.kind, service.KIND_PERSONALIZED)
        self.assertNotEqual(page._state, page_module.STATE_INCOMPATIBLE)
        self.assertNotIn("INCOMPATÍVEL", page.state_detail.text())

    def test_color_change_enables_regeneration(self):
        from PySide6.QtWidgets import QApplication
        import stone_color_page as page_module
        app = QApplication.instance() or QApplication([])
        self._write_valid()
        self._apply(8, 7, 0)
        page = page_module.StoneColorPage(
            lambda: str(self.client), PROFILE_PATH, self.out, storage_base=self.store,
        )
        self.addCleanup(page.deleteLater)
        self.assertTrue(page.analyze_again())
        self._wait(page, app)
        idx = page.attack_combo.findData(5)
        page.attack_combo.setCurrentIndex(idx)
        self.assertEqual(page.action_button.text(), "Gerar cópia")
        self.assertTrue(page.action_button.isEnabled())

    def test_restore_then_page_updated(self):
        from PySide6.QtWidgets import QApplication
        import stone_color_page as page_module
        app = QApplication.instance() or QApplication([])
        self._write_valid()
        before = _sha((self.client / "ItemList6.bin").read_bytes())
        self._apply(8, 7, 0)
        page = page_module.StoneColorPage(
            lambda: str(self.client), PROFILE_PATH, self.out, storage_base=self.store,
        )
        self.addCleanup(page.deleteLater)
        self.assertTrue(page.analyze_again())
        self._wait(page, app)
        service.restore_colors(str(self.client), PROFILE_PATH, self.store)
        page.refresh_after_restore()
        self._wait(page, app)
        self.assertEqual(page.recognition.kind, service.KIND_BASE)
        self.assertEqual(_sha((self.client / "ItemList6.bin").read_bytes()), before)

    def test_corrupted_base_blocks_generation(self):
        self._write_valid()
        before = _sha((self.client / "ItemList6.bin").read_bytes())
        self._apply(8, 7, 0)
        base_file = service._base_file(str(self.client), before, self.store)
        base_file.write_bytes(b"corrompido")
        rec = service.recognize_state(str(self.client), PROFILE_PATH, self.store)
        self.assertEqual(rec.kind, service.KIND_PERSONALIZED)
        self.assertFalse(rec.base_valid)
        self.assertIsNotNone(rec.base_error)


if __name__ == "__main__":
    unittest.main(verbosity=2)

