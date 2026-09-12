# -*- coding: utf-8 -*-
"""Testes não destrutivos do serviço operacional de Cores das Pedras."""

import hashlib
import json
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


class TestStonesService(unittest.TestCase):
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
        patcher = patch.object(
            service, "detect_relevant_processes",
            return_value=service.ProcessDetection((), None),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_valid(self, data=None, relative="ItemList6.bin"):
        path = self.client / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if data is not None else self.valid)
        return path

    def read_target(self):
        return (self.client / "ItemList6.bin").read_bytes()

    def metadata(self):
        md = service.metadata_path(str(self.client), self.store)
        if not md.is_file():
            return {}
        return json.loads(md.read_text(encoding="utf-8"))

    def test_first_apply_creates_and_verifies_backup_before_write(self):
        self.write_valid()
        before = _sha(self.read_target())
        outcome = service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        self.assertTrue(outcome.applied)
        self.assertEqual(outcome.base_sha256, before)
        base_file = service._base_file(str(self.client), before, self.store)
        self.assertTrue(base_file.is_file())
        self.assertEqual(service.sha256_file(base_file), before)
        self.assertNotEqual(_sha(self.read_target()), before)
        self.assertEqual(_sha(self.read_target()), outcome.output_sha256)
        self.assertEqual([b["sha256"] for b in self.metadata()["bases"]], [before])

    def test_backup_failure_blocks_apply(self):
        self.write_valid()
        before = _sha(self.read_target())
        with patch.object(service, "capture_base",
                          side_effect=engine.ValidationError("backup falhou")):
            with self.assertRaises(engine.ValidationError):
                service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        self.assertEqual(_sha(self.read_target()), before)
    def test_apply_then_restore_recovers_base_exactly(self):
        self.write_valid()
        before = _sha(self.read_target())
        service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        outcome = service.restore_colors(str(self.client), PROFILE_PATH, self.store)
        self.assertTrue(outcome.restored)
        self.assertEqual(_sha(self.read_target()), before)
        self.assertEqual(outcome.base_sha256, before)

    def test_reapply_same_colors_no_write(self):
        self.write_valid()
        service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        after_first = _sha(self.read_target())
        outcome = service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        self.assertFalse(outcome.applied)
        self.assertEqual(_sha(self.read_target()), after_first)

    def test_change_colors_uses_preserved_base(self):
        self.write_valid()
        before = _sha(self.read_target())
        service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        personalized = self.read_target()
        base_bytes = engine.read_binary_file(service._base_file(str(self.client), before, self.store))
        expected = engine.apply_colors(base_bytes, self.profile, attack_code=5, defense_code=6, common_code=4)
        wrong = engine.apply_colors(personalized, self.profile, attack_code=5, defense_code=6, common_code=4)
        outcome = service.apply_colors(str(self.client), PROFILE_PATH, 5, 6, 4, self.store)
        self.assertTrue(outcome.applied)
        self.assertEqual(outcome.output_sha256, expected.sha256)
        self.assertNotEqual(outcome.output_sha256, wrong.sha256)

    def test_new_compatible_version_preserves_base_without_applying(self):
        self.write_valid()
        service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        n_bases = len(self.metadata()["bases"])
        new_data = _compatible_bytes(self.profile, trailer=987654321)
        self.write_valid(new_data)
        new_hash = _sha(new_data)
        rec = service.recognize_state(str(self.client), PROFILE_PATH, self.store)
        self.assertEqual(rec.kind, service.KIND_EXTERNAL_COMPATIBLE)
        service.ensure_base_preserved(str(self.client), PROFILE_PATH, self.store)
        self.assertEqual(_sha(self.read_target()), new_hash)
        self.assertEqual(len(self.metadata()["bases"]), n_bases + 1)
        self.assertIn(new_hash, [b["sha256"] for b in self.metadata()["bases"]])

    def test_same_content_does_not_duplicate_backup(self):
        self.write_valid()
        service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        n_bases = len(self.metadata()["bases"])
        service.ensure_base_preserved(str(self.client), PROFILE_PATH, self.store)
        service.ensure_base_preserved(str(self.client), PROFILE_PATH, self.store)
        self.assertEqual(len(self.metadata()["bases"]), n_bases)

    def test_external_incompatible_blocks_write(self):
        bad = bytearray(self.valid)
        bad[engine.color_offset(self.profile.entries[0].record_id)] ^= 1
        self.write_valid(bytes(bad))
        before = _sha(self.read_target())
        with self.assertRaises(engine.IncompatibleUpdateError):
            service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        self.assertEqual(_sha(self.read_target()), before)
    def test_old_restore_does_not_overwrite_external_update(self):
        self.write_valid()
        service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        new_data = _compatible_bytes(self.profile, trailer=55555)
        self.write_valid(new_data)
        before = _sha(self.read_target())
        with self.assertRaises(service.StonesBlockedError):
            service.restore_colors(str(self.client), PROFILE_PATH, self.store)
        self.assertEqual(_sha(self.read_target()), before)

    def test_isolation_between_two_clients(self):
        self.write_valid()
        other = self.base / "OutroCliente"
        other.mkdir()
        (other / "ItemList6.bin").write_bytes(self.valid)
        service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        rec_other = service.recognize_state(str(other), PROFILE_PATH, self.store)
        self.assertNotEqual(rec_other.kind, service.KIND_PERSONALIZED)
        self.assertEqual(_sha((other / "ItemList6.bin").read_bytes()), _sha(self.valid))

    def test_ui_itemlist6_not_touched(self):
        self.write_valid()
        ui = self.write_valid(relative="UI/ItemList6.bin")
        ui_hash = _sha(ui.read_bytes())
        service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        self.assertEqual(_sha(ui.read_bytes()), ui_hash)

    def test_corrupted_base_blocks_apply(self):
        self.write_valid()
        before = _sha(self.read_target())
        service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        base_file = service._base_file(str(self.client), before, self.store)
        base_file.write_bytes(b"corrompido")
        with self.assertRaises(engine.ValidationError):
            service.apply_colors(str(self.client), PROFILE_PATH, 5, 6, 4, self.store)

    def test_missing_base_blocks_restore(self):
        self.write_valid()
        before = _sha(self.read_target())
        service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        service._base_file(str(self.client), before, self.store).unlink()
        with self.assertRaises(engine.ValidationError):
            service.restore_colors(str(self.client), PROFILE_PATH, self.store)

    def test_corrupted_metadata_blocks_apply(self):
        self.write_valid()
        service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        before = _sha(self.read_target())
        service.metadata_path(str(self.client), self.store).write_text("{corrompido", encoding="utf-8")
        rec = service.recognize_state(str(self.client), PROFILE_PATH, self.store)
        self.assertEqual(rec.kind, service.KIND_EXTERNAL_INCOMPATIBLE)
        with self.assertRaises(engine.IncompatibleUpdateError):
            service.apply_colors(str(self.client), PROFILE_PATH, 5, 6, 4, self.store)
        self.assertEqual(_sha(self.read_target()), before)
    def test_target_change_before_replace_blocks_write(self):
        self.write_valid()
        before_bytes = self.read_target()
        changed = _compatible_bytes(self.profile, trailer=424242)
        with patch.object(service, "read_stable",
                          side_effect=[before_bytes, changed, changed]):
            with self.assertRaises(engine.InputChangedError):
                service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        self.assertEqual(_sha(self.read_target()), _sha(before_bytes))

    def test_write_failure_blocks_replace(self):
        self.write_valid()
        before = _sha(self.read_target())
        with patch.object(service, "_atomic_replace",
                          side_effect=PermissionError("acesso negado")):
            with self.assertRaises(PermissionError):
                service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        self.assertEqual(_sha(self.read_target()), before)

    def test_metadata_failure_after_replace_then_reconcile(self):
        self.write_valid()
        real_write = service._write_metadata
        count = [0]

        def flaky(path, md):
            count[0] += 1
            if count[0] == 3:
                raise OSError("disco cheio")
            return real_write(path, md)

        with patch.object(service, "_write_metadata", side_effect=flaky):
            outcome = service.apply_colors(str(self.client), PROFILE_PATH, 8, 7, 0, self.store)
        self.assertTrue(outcome.applied)
        self.assertEqual([t["state"] for t in self.metadata().get("pending", [])], ["pending"])
        resolved = service.reconcile_transaction(str(self.client), self.store)
        self.assertIn("finalized", resolved)
        md2 = self.metadata()
        self.assertEqual(md2.get("pending", []), [])
        self.assertEqual(len(md2["applications"]), 1)

    def test_shutdown_during_apply_does_not_abandon_thread(self):
        from PySide6.QtWidgets import QApplication
        import stone_color_page as page_module
        app = QApplication.instance() or QApplication([])
        self.write_valid()
        page = page_module.StoneColorPage(
            lambda: str(self.client), PROFILE_PATH, self.base / "Saidas",
            storage_base=self.store,
        )
        self.addCleanup(page.deleteLater)
        prepared = service.prepare_colors(
            str(self.client), PROFILE_PATH, self.base / "Saidas", 8, 7, 0, self.store,
        )
        page._prepared = prepared
        page._set_state(page_module.STATE_COMPATIBLE, "pronto")
        real_apply = service.apply_prepared

        def slow_apply(*args, **kwargs):
            time.sleep(0.5)
            return real_apply(*args, **kwargs)

        with patch.object(page_module.service, "apply_prepared", side_effect=slow_apply):
            self.assertTrue(page.apply_colors())
            deadline = time.monotonic() + 3
            while (time.monotonic() < deadline
                   and not (page.active_thread is not None and page.active_thread.isRunning())):
                app.processEvents()
                time.sleep(0.01)
            self.assertTrue(page.active_thread is not None and page.active_thread.isRunning())
            self.assertTrue(page.shutdown(5000))
        for _ in range(50):
            app.processEvents()
            time.sleep(0.01)
        self.assertIsNone(page.active_thread)


if __name__ == "__main__":
    unittest.main(verbosity=2)



