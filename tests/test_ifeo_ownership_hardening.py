# -*- coding: utf-8 -*-
"""Hardening IFEO/PerfOptions — ownership/proveniência (P1 #3).

Garante que o Optimizer só desfaz no Registry aquilo que consegue provar que
ele próprio alterou. NENHUM teste toca Registry real, reg.exe real, powercfg
real ou arquivos reais de backup.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import seguranca  # noqa: E402


def _proibido(*a, **k):
    raise AssertionError("teste não pode executar comando real do Windows")


IFEO_BASE = seguranca.IFEO_BASE_KEY.lower()
G_EXE = "aclient.exe"
G_EXE2 = "aika.exe"
G_EXE3 = "aika_br.exe"
V = seguranca.IFEO_CPU_PRIORITY_CLASS_VALUE  # 6


class _KeyHandle:
    def __init__(self, path, reg):
        self.path = path
        self.reg = reg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeIfeoReg:
    HKEY_LOCAL_MACHINE = "HKLM"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    KEY_ALL_ACCESS = 3
    REG_DWORD = 4
    REG_SZ = 1

    def __init__(self, keys=None):
        self.keys = {k.lower(): dict(v) for k, v in (keys or {}).items()}

    def OpenKey(self, hive, path, res=0, access=0):
        if hive != self.HKEY_LOCAL_MACHINE:
            raise FileNotFoundError()
        p = path.lower()
        if p not in self.keys:
            raise FileNotFoundError()
        return _KeyHandle(p, self)

    def EnumValue(self, key, idx):
        vals = self.keys.get(key.path, {})
        nomes = sorted(vals.keys())
        if idx < 0 or idx >= len(nomes):
            raise OSError("fim")
        nome = nomes[idx]
        valor, tipo = vals[nome]
        return nome, valor, tipo

    def SetValueEx(self, key, nome, res, tipo, valor):
        self.keys.setdefault(key.path, {})[nome] = (valor, tipo)

    def DeleteValue(self, key, nome):
        self.keys.get(key.path, {}).pop(nome, None)

    def DeleteKey(self, key, subkey):
        p = key.path + "\\" + subkey.lower()
        self.keys.pop(p, None)


def _estado_ifeo(exe, perfoptions_values=None, ifeo_key_exists=True):
    exe = exe.lower()
    keys = {}
    if ifeo_key_exists:
        keys[IFEO_BASE + "\\" + exe] = {}
        if perfoptions_values is not None:
            keys[IFEO_BASE + "\\" + exe + "\\perfoptions"] = dict(perfoptions_values)
    return keys


def _entrada(perfoptions_existed, values_before=None):
    return {
        "ifeo_key_existed": True,
        "perfoptions_existed": perfoptions_existed,
        "values_before": values_before or {},
        "optimizer_values": {"CpuPriorityClass": {"type": FakeIfeoReg.REG_DWORD, "value": V}},
    }


class _Sandbox(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.reg_dir = os.path.join(self._td.name, "Registro_Sistema")
        self.ifeo_path = os.path.join(self.reg_dir, "ifeo_state.json")
        self.backup_dir = os.path.join(self._td.name, "backup")
        self.estado_path = os.path.join(self.backup_dir, "estado_sistema.json")

        subprocess_guard = mock.Mock()
        subprocess_guard.run = _proibido
        subprocess_guard.check_output = _proibido
        subprocess_guard.Popen = _proibido

        self._patches = [
            mock.patch.object(seguranca, "ARQUIVO_IFEO", self.ifeo_path),
            mock.patch.object(seguranca, "PASTA_BACKUP_REG", self.reg_dir),
            mock.patch.object(seguranca, "PASTA_BACKUP", self.backup_dir),
            mock.patch.object(seguranca, "ARQUIVO_ESTADO", self.estado_path),
            mock.patch.object(seguranca, "log"),
            mock.patch.object(seguranca, "subprocess", subprocess_guard),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def _patch_winreg(self, fake):
        p = mock.patch.object(seguranca, "winreg", fake)
        p.start()
        self.addCleanup(p.stop)
        return fake

    def _escrever_metadata(self, executables):
        os.makedirs(self.reg_dir, exist_ok=True)
        with open(self.ifeo_path, "w", encoding="utf-8") as f:
            json.dump({"format_version": 1, "executables": executables}, f)

    def _ler_metadata(self):
        with open(self.ifeo_path, "r", encoding="utf-8") as f:
            return json.load(f)


class TestOwnershipCapture(_Sandbox):
    def test_primeira_alteracao_captura_original(self):
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (2, 4)})))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        ent = self._ler_metadata()["executables"][G_EXE]
        self.assertEqual(self._ler_metadata()["format_version"], 1)
        self.assertTrue(ent["perfoptions_existed"])
        self.assertEqual(ent["values_before"]["CpuPriorityClass"], {"type": 4, "value": 2})

    def test_segunda_alteracao_nao_sobrescreve_original(self):
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (2, 4)})))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"]["CpuPriorityClass"] = (V, 4)
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        self.assertEqual(self._ler_metadata()["executables"][G_EXE]["values_before"]["CpuPriorityClass"],
                         {"type": 4, "value": 2})

    def test_terceira_alteracao_nao_sobrescreve_original(self):
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (2, 4)})))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"]["CpuPriorityClass"] = (V, 4)
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        self.assertEqual(self._ler_metadata()["executables"][G_EXE]["values_before"]["CpuPriorityClass"],
                         {"type": 4, "value": 2})

    def test_metadata_escrito_atomicamente(self):
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE)))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        self.assertFalse(os.path.exists(self.ifeo_path + ".tmp"))
        self.assertTrue(os.path.isfile(self.ifeo_path))

    def test_falha_ao_salvar_impede_alteracao(self):
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE)))
        with mock.patch.object(seguranca, "_escrever_ifeo_metadata_atomico", side_effect=OSError("disco cheio")):
            self.assertFalse(seguranca.garantir_ifeo_ownership(G_EXE))

    def test_metadata_corrompido_impede_restore(self):
        os.makedirs(self.reg_dir, exist_ok=True)
        with open(self.ifeo_path, "w", encoding="utf-8") as f:
            f.write("{json invalido")
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, 4)})))
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_FALHA)
        self.assertEqual(fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"]["CpuPriorityClass"], (V, 4))

    def test_formato_futuro_impede_restore(self):
        os.makedirs(self.reg_dir, exist_ok=True)
        with open(self.ifeo_path, "w", encoding="utf-8") as f:
            json.dump({"format_version": 999, "executables": {}}, f)
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, 4)})))
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_FALHA)
        self.assertEqual(fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"]["CpuPriorityClass"], (V, 4))


class TestChaveNaoExistia(_Sandbox):
    def test_restore_remove_valor_criado_e_subchave_vazia(self):
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE)))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"] = {"CpuPriorityClass": (V, 4)}
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        self.assertNotIn(IFEO_BASE + "\\" + G_EXE + "\\perfoptions", fake.keys)

    def test_perfoptions_com_valor_externo_nao_removido(self):
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE)))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"] = {
            "CpuPriorityClass": (V, 4), "IoPriority": (3, 4)}
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        perf = fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"]
        self.assertNotIn("CpuPriorityClass", perf)
        self.assertEqual(perf["IoPriority"], (3, 4))


class TestChaveJaExistia(_Sandbox):
    def test_restore_devolve_original_tipo_e_preserva_outros(self):
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (2, 4), "IoPriority": (3, 4)})))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"]["CpuPriorityClass"] = (V, 4)
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        perf = fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"]
        self.assertEqual(perf["CpuPriorityClass"], (2, 4))
        self.assertEqual(perf["IoPriority"], (3, 4))
        self.assertIn(IFEO_BASE + "\\" + G_EXE + "\\perfoptions", fake.keys)


class TestValorNaoExistia(_Sandbox):
    def test_restore_remove_apenas_valor_criado(self):
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"IoPriority": (3, 4)})))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"]["CpuPriorityClass"] = (V, 4)
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        perf = fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"]
        self.assertNotIn("CpuPriorityClass", perf)
        self.assertEqual(perf["IoPriority"], (3, 4))
        self.assertIn(IFEO_BASE + "\\" + G_EXE + "\\perfoptions", fake.keys)


class TestConflitoExterno(_Sandbox):
    def test_conflito_nao_sobrescreve_e_preserva_metadata(self):
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (2, 4)})))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"]["CpuPriorityClass"] = (1, 4)
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_PARCIAL)
        self.assertEqual(fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"]["CpuPriorityClass"], (1, 4))
        self.assertTrue(os.path.isfile(self.ifeo_path))

    def test_conflito_registrado_no_log(self):
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (2, 4)})))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"]["CpuPriorityClass"] = (1, 4)
        seguranca._restaurar_ifeo_ownership()
        self.assertTrue(any("Conflito" in str(c.args[0]) for c in seguranca.log.call_args_list))


class TestMultiplosExecutaveis(_Sandbox):
    def test_restaurados_independentemente(self):
        fake = self._patch_winreg(FakeIfeoReg({
            **_estado_ifeo(G_EXE, {"CpuPriorityClass": (2, 4)}),
            **_estado_ifeo(G_EXE2, {"CpuPriorityClass": (3, 4)}),
        }))
        self._escrever_metadata({
            G_EXE: _entrada(True, {"CpuPriorityClass": {"type": 4, "value": 2}}),
            G_EXE2: _entrada(True, {"CpuPriorityClass": {"type": 4, "value": 3}}),
        })
        fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"]["CpuPriorityClass"] = (V, 4)
        fake.keys[IFEO_BASE + "\\" + G_EXE2 + "\\perfoptions"]["CpuPriorityClass"] = (V, 4)
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        self.assertEqual(fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"]["CpuPriorityClass"], (2, 4))
        self.assertEqual(fake.keys[IFEO_BASE + "\\" + G_EXE2 + "\\perfoptions"]["CpuPriorityClass"], (3, 4))

    def test_conflito_em_um_nao_destroi_outro(self):
        fake = self._patch_winreg(FakeIfeoReg({
            **_estado_ifeo(G_EXE, {"CpuPriorityClass": (2, 4)}),
            **_estado_ifeo(G_EXE2, {"CpuPriorityClass": (3, 4)}),
        }))
        self._escrever_metadata({
            G_EXE: _entrada(True, {"CpuPriorityClass": {"type": 4, "value": 2}}),
            G_EXE2: _entrada(True, {"CpuPriorityClass": {"type": 4, "value": 3}}),
        })
        fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"]["CpuPriorityClass"] = (V, 4)
        fake.keys[IFEO_BASE + "\\" + G_EXE2 + "\\perfoptions"]["CpuPriorityClass"] = (1, 4)
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_PARCIAL)
        self.assertEqual(fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"]["CpuPriorityClass"], (2, 4))
        self.assertEqual(fake.keys[IFEO_BASE + "\\" + G_EXE2 + "\\perfoptions"]["CpuPriorityClass"], (1, 4))

    def test_sem_backup_nao_tocado(self):
        fake = self._patch_winreg(FakeIfeoReg({
            **_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, 4)}),
            **_estado_ifeo(G_EXE2, {"CpuPriorityClass": (7, 4)}),
        }))
        self._escrever_metadata({G_EXE: _entrada(False)})
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        self.assertNotIn(IFEO_BASE + "\\" + G_EXE + "\\perfoptions", fake.keys)
        self.assertEqual(fake.keys[IFEO_BASE + "\\" + G_EXE2 + "\\perfoptions"]["CpuPriorityClass"], (7, 4))

    def test_fora_allowlist_rejeitado(self):
        self._patch_winreg(FakeIfeoReg())
        self._escrever_metadata({"notepad.exe": _entrada(True, {"CpuPriorityClass": {"type": 4, "value": 2}})})
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_FALHA)

    def test_path_traversal_rejeitado(self):
        self._patch_winreg(FakeIfeoReg())
        self._escrever_metadata({"..\\evil.exe": _entrada(True)})
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_FALHA)

    def test_case_insensitive(self):
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, 4)})))
        self._escrever_metadata({"ACLIENT.EXE": _entrada(False)})
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        self.assertNotIn(IFEO_BASE + "\\" + G_EXE + "\\perfoptions", fake.keys)


class TestBackupAusente(_Sandbox):
    def test_sem_metadata_nenhum_delete(self):
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (7, 4)})))
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        self.assertIn("CpuPriorityClass", fake.keys[IFEO_BASE + "\\" + G_EXE + "\\perfoptions"])

    def test_sem_reg_nenhum_comando_destrutivo_e_parcial(self):
        with mock.patch.object(seguranca, "restaurar_snapshot_sistema", return_value=seguranca.RESTAURACAO_SUCESSO), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            ok, _ = seguranca.restaurar_registro_sistema()
        self.assertFalse(ok)
        for c in mex.call_args_list:
            self.assertNotIn("delete", " ".join(str(a).lower() for a in c.args[0]))


class TestLegado(_Sandbox):
    def test_reg_legado_nao_importado_nem_apagado(self):
        os.makedirs(self.reg_dir, exist_ok=True)
        legado = os.path.join(self.reg_dir, "backup_prioridade_aclient.exe.reg")
        outro = os.path.join(self.reg_dir, "backup_gamedvr.reg")
        with open(legado, "w") as f:
            f.write("Windows Registry Editor Version 5.00\n")
        with open(outro, "w") as f:
            f.write("Windows Registry Editor Version 5.00\n")
        with mock.patch.object(seguranca, "restaurar_snapshot_sistema", return_value=seguranca.RESTAURACAO_SUCESSO), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            ok, _ = seguranca.restaurar_registro_sistema()
        self.assertTrue(ok)
        importados = [" ".join(str(a) for a in c.args[0]) for c in mex.call_args_list]
        self.assertTrue(any("backup_gamedvr.reg" in s for s in importados))
        self.assertFalse(any("backup_prioridade_aclient.exe.reg" in s for s in importados))
        self.assertTrue(os.path.isfile(legado))


class TestIntegracaoRestaurar(_Sandbox):
    def _preparar(self):
        os.makedirs(self.reg_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
        with open(os.path.join(self.reg_dir, "backup.reg"), "w") as f:
            f.write("Windows Registry Editor Version 5.00\n")
        with open(self.estado_path, "w", encoding="utf-8") as f:
            json.dump({"format_version": 2, "power_plan": None, "dns_interfaces": []}, f)

    def test_snapshot_success_ifeo_success_finaliza(self):
        self._preparar()
        with mock.patch.object(seguranca, "restaurar_snapshot_sistema", return_value=seguranca.RESTAURACAO_SUCESSO), \
             mock.patch.object(seguranca, "_restaurar_ifeo_ownership", return_value=seguranca.RESTAURACAO_SUCESSO), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True), \
             mock.patch.object(seguranca, "finalizar_snapshot_sistema") as fin:
            ok, _ = seguranca.restaurar_registro_sistema()
        self.assertTrue(ok)
        fin.assert_called_once()

    def test_snapshot_success_ifeo_partial_preserva(self):
        self._preparar()
        with mock.patch.object(seguranca, "restaurar_snapshot_sistema", return_value=seguranca.RESTAURACAO_SUCESSO), \
             mock.patch.object(seguranca, "_restaurar_ifeo_ownership", return_value=seguranca.RESTAURACAO_PARCIAL), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True), \
             mock.patch.object(seguranca, "finalizar_snapshot_sistema") as fin:
            ok, _ = seguranca.restaurar_registro_sistema()
        self.assertFalse(ok)
        fin.assert_not_called()

    def test_snapshot_partial_ifeo_success_preserva(self):
        self._preparar()
        with mock.patch.object(seguranca, "restaurar_snapshot_sistema", return_value=seguranca.RESTAURACAO_PARCIAL), \
             mock.patch.object(seguranca, "_restaurar_ifeo_ownership", return_value=seguranca.RESTAURACAO_SUCESSO), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True), \
             mock.patch.object(seguranca, "finalizar_snapshot_sistema") as fin:
            ok, _ = seguranca.restaurar_registro_sistema()
        self.assertFalse(ok)
        fin.assert_not_called()

    def test_ifeo_failure_preserva(self):
        self._preparar()
        with mock.patch.object(seguranca, "restaurar_snapshot_sistema", return_value=seguranca.RESTAURACAO_SUCESSO), \
             mock.patch.object(seguranca, "_restaurar_ifeo_ownership", return_value=seguranca.RESTAURACAO_FALHA), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True), \
             mock.patch.object(seguranca, "finalizar_snapshot_sistema") as fin:
            ok, _ = seguranca.restaurar_registro_sistema()
        self.assertFalse(ok)
        fin.assert_not_called()


class TestIsolamento(_Sandbox):
    def test_nenhum_subprocess_real(self):
        with self.assertRaises(AssertionError):
            seguranca.subprocess.run(["echo", "x"])

    def test_config_real_byte_identico(self):
        import config
        caminho = config.ARQUIVO_CONFIG
        if not os.path.isfile(caminho):
            self.skipTest("config.json real ausente")
        before = open(caminho, "rb").read()
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE)))
        seguranca.garantir_ifeo_ownership(G_EXE)
        seguranca._restaurar_ifeo_ownership()
        self.assertEqual(open(caminho, "rb").read(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)



