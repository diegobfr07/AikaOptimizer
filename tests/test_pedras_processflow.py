# -*- coding: utf-8 -*-
"""Testes de detecção de processos e fluxo preparar→aplicar das Pedras."""

import hashlib
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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


def _fake_proc(name, pid, exe=None, exe_error=None):
    proc = Mock()
    proc.info = {"name": name, "pid": pid}
    if exe_error is not None:
        proc.exe.side_effect = exe_error
    else:
        proc.exe.return_value = exe
    return proc


class TestProcessDetection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.client = self.base / "Cliente"
        self.client.mkdir()

    def test_no_process_returns_empty(self):
        with patch("psutil.process_iter", return_value=[]):
            det = service.detect_relevant_processes(str(self.client))
        self.assertEqual(det.matches, ())
        self.assertIsNone(det.verify_error)
        self.assertFalse(det.blocked)

    def test_real_process_in_selected_client_blocks(self):
        exe = str(self.client / "AIKALauncher.exe")
        proc = _fake_proc("AIKALauncher.exe", 1234, exe=exe)
        with patch("psutil.process_iter", return_value=[proc]):
            det = service.detect_relevant_processes(str(self.client))
        self.assertEqual(len(det.matches), 1)
        m = det.matches[0]
        self.assertEqual(m.name, "AIKALauncher.exe")
        self.assertEqual(m.pid, 1234)
        self.assertEqual(m.exe, exe)
        self.assertIn("caminho no cliente selecionado", m.rule)

    def test_other_installation_not_blocked(self):
        other = str(self.base / "Outro" / "AIKALauncher.exe")
        proc = _fake_proc("AIKALauncher.exe", 1234, exe=other)
        with patch("psutil.process_iter", return_value=[proc]):
            det = service.detect_relevant_processes(str(self.client))
        self.assertEqual(det.matches, ())

    def test_partial_aika_name_not_blocked(self):
        proc = _fake_proc("myaikatool.exe", 1234, exe=str(self.client / "myaikatool.exe"))
        with patch("psutil.process_iter", return_value=[proc]):
            det = service.detect_relevant_processes(str(self.client))
        self.assertEqual(det.matches, ())

    def test_own_optimizer_not_blocked(self):
        proc = _fake_proc("python.exe", os.getpid(), exe=sys.executable)
        with patch("psutil.process_iter", return_value=[proc]):
            det = service.detect_relevant_processes(str(self.client))
        self.assertEqual(det.matches, ())

    def test_exe_access_denied_falls_back_to_name_match(self):
        import psutil
        proc = _fake_proc("aikalauncher.exe", 1234, exe_error=psutil.AccessDenied(pid=1234))
        with patch("psutil.process_iter", return_value=[proc]):
            det = service.detect_relevant_processes(str(self.client))
        self.assertEqual(len(det.matches), 1)
        self.assertIsNone(det.matches[0].exe)
        self.assertIn("caminho indisponível", det.matches[0].rule)

    def test_process_disappearing_during_enumeration_skipped(self):
        import psutil
        proc = Mock()
        proc.info = Mock()
        proc.info.get.side_effect = psutil.NoSuchProcess(1234)
        with patch("psutil.process_iter", return_value=[proc]):
            det = service.detect_relevant_processes(str(self.client))
        self.assertEqual(det.matches, ())
        self.assertIsNone(det.verify_error)

    def test_enumeration_failure_sets_verify_error(self):
        with patch("psutil.process_iter", side_effect=RuntimeError("boom")):
            det = service.detect_relevant_processes(str(self.client))
        self.assertIsNotNone(det.verify_error)
        self.assertTrue(det.blocked)

    def test_require_processes_closed_message_includes_pid(self):
        exe = str(self.client / "AIKALauncher.exe")
        proc = _fake_proc("AIKALauncher.exe", 777, exe=exe)
        with patch("psutil.process_iter", return_value=[proc]):
            with self.assertRaises(service.ProcessRunningError) as ctx:
                service._require_processes_closed(str(self.client))
        self.assertIn("AIKALauncher.exe", str(ctx.exception))
        self.assertIn("PID 777", str(ctx.exception))

    def test_require_processes_closed_verify_error(self):
        with patch("psutil.process_iter", side_effect=RuntimeError("boom")):
            with self.assertRaises(service.ProcessVerifyError) as ctx:
                service._require_processes_closed(str(self.client))
        self.assertIn("Não foi possível verificar", str(ctx.exception))
class TestPrepareApply(unittest.TestCase):
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

    def write_valid(self, data=None):
        path = self.client / "ItemList6.bin"
        path.write_bytes(data if data is not None else self.valid)
        return path

    def test_prepare_then_apply_bytes_match(self):
        self.write_valid()
        prepared = service.prepare_colors(
            str(self.client), PROFILE_PATH, self.out, 8, 7, 0, self.store,
        )
        self.assertTrue(prepared.copy_path.is_file())
        self.assertEqual(service.sha256_file(prepared.copy_path), prepared.copy_sha256)
        outcome = service.apply_prepared(prepared, PROFILE_PATH, self.store)
        self.assertTrue(outcome.applied)
        self.assertEqual(_sha((self.client / "ItemList6.bin").read_bytes()), prepared.copy_sha256)

    def test_apply_prepared_target_changed_blocks(self):
        self.write_valid()
        prepared = service.prepare_colors(
            str(self.client), PROFILE_PATH, self.out, 8, 7, 0, self.store,
        )
        changed = _compatible_bytes(self.profile, trailer=424242)
        (self.client / "ItemList6.bin").write_bytes(changed)
        with self.assertRaises(engine.InputChangedError):
            service.apply_prepared(prepared, PROFILE_PATH, self.store)

    def test_apply_prepared_tampered_copy_blocks(self):
        self.write_valid()
        prepared = service.prepare_colors(
            str(self.client), PROFILE_PATH, self.out, 8, 7, 0, self.store,
        )
        prepared.copy_path.write_bytes(b"tampered")
        with self.assertRaises(service.StonesBlockedError):
            service.apply_prepared(prepared, PROFILE_PATH, self.store)

    def test_apply_prepared_missing_copy_blocks(self):
        self.write_valid()
        prepared = service.prepare_colors(
            str(self.client), PROFILE_PATH, self.out, 8, 7, 0, self.store,
        )
        prepared.copy_path.unlink()
        with self.assertRaises(service.StonesBlockedError):
            service.apply_prepared(prepared, PROFILE_PATH, self.store)

    def test_change_colors_after_apply_uses_base(self):
        self.write_valid()
        before = _sha((self.client / "ItemList6.bin").read_bytes())
        prepared = service.prepare_colors(
            str(self.client), PROFILE_PATH, self.out, 8, 7, 0, self.store,
        )
        service.apply_prepared(prepared, PROFILE_PATH, self.store)
        personalized = (self.client / "ItemList6.bin").read_bytes()
        base_bytes = engine.read_binary_file(service._base_file(str(self.client), before, self.store))
        expected = engine.apply_colors(base_bytes, self.profile, attack_code=5, defense_code=6, common_code=4)
        wrong = engine.apply_colors(personalized, self.profile, attack_code=5, defense_code=6, common_code=4)
        prepared2 = service.prepare_colors(
            str(self.client), PROFILE_PATH, self.out, 5, 6, 4, self.store,
        )
        self.assertEqual(prepared2.copy_sha256, expected.sha256)
        self.assertNotEqual(prepared2.copy_sha256, wrong.sha256)

    def test_process_block_then_retry(self):
        self.write_valid()
        prepared = service.prepare_colors(
            str(self.client), PROFILE_PATH, self.out, 8, 7, 0, self.store,
        )
        with patch.object(service, "_require_processes_closed",
                          side_effect=service.ProcessRunningError("Feche o launcher do Aika")):
            with self.assertRaises(service.ProcessRunningError):
                service.apply_prepared(prepared, PROFILE_PATH, self.store)
        # Preparação continua íntegra; nova tentativa sem bloqueio aplica.
        outcome = service.apply_prepared(prepared, PROFILE_PATH, self.store)
        self.assertTrue(outcome.applied)


class TestPageFlow(unittest.TestCase):
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

    def _make_page(self):
        import stone_color_page as page_module
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        (self.client / "ItemList6.bin").write_bytes(self.valid)
        page = page_module.StoneColorPage(
            lambda: str(self.client), PROFILE_PATH, self.out, storage_base=self.store,
        )
        self.addCleanup(page.deleteLater)
        return app, page

    def test_color_change_invalidates_preparation(self):
        app, page = self._make_page()
        prepared = service.prepare_colors(
            str(self.client), PROFILE_PATH, self.out, 8, 7, 0, self.store,
        )
        page._prepared = prepared
        page._update_action_button()
        self.assertEqual(page.action_button.text(), "Aplicar no AIKA")
        idx = page.attack_combo.findData(5)
        page.attack_combo.setCurrentIndex(idx)
        self.assertIsNone(page._prepared)
        self.assertEqual(page.action_button.text(), "Gerar cópia")

    def test_reconcile_clears_stale_preparation(self):
        app, page = self._make_page()
        prepared = service.prepare_colors(
            str(self.client), PROFILE_PATH, self.out, 8, 7, 0, self.store,
        )
        page._prepared = prepared
        changed = _compatible_bytes(self.profile, trailer=999)
        (self.client / "ItemList6.bin").write_bytes(changed)
        analysis = engine.analyze_file(self.client / "ItemList6.bin", self.profile)
        page._reconcile_preparation(analysis)
        self.assertIsNone(page._prepared)

    def test_refresh_after_restore_invalidates(self):
        app, page = self._make_page()
        prepared = service.prepare_colors(
            str(self.client), PROFILE_PATH, self.out, 8, 7, 0, self.store,
        )
        page._prepared = prepared
        page._applied_success = True
        page._applied_sha256 = prepared.copy_sha256
        page.refresh_after_restore()
        self.assertIsNone(page._prepared)
        self.assertFalse(page._applied_success)
        self.assertTrue(page.shutdown(3000))


if __name__ == "__main__":
    unittest.main(verbosity=2)

