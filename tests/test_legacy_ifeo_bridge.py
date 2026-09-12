# -*- coding: utf-8 -*-
"""Ponte legado IFEO V4.0 → Ownership V4.1 (backup_prioridade_*.reg).

Cobre parser restrito, adoção segura, consumo único por SHA-256, múltiplos
executáveis e integração. NENHUM teste toca Registry real, reg.exe real ou
arquivos reais de backup.
"""
import codecs
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
REG_DWORD = seguranca.IFEO_CPU_PRIORITY_CLASS_TYPE


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


def _reg_bytes(exe, perfoptions=False, cpu=None, extra_perf_values=(),
               extra_sections=(), encoding="utf-16-le-bom", raw=None):
    """Constrói bytes de um backup_prioridade_<exe>.reg (reg export V4.0)."""
    if raw is not None:
        return raw
    lines = ["Windows Registry Editor Version 5.00"]
    base = ("HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\"
            "Image File Execution Options\\" + exe)
    lines.append("")
    lines.append("[" + base + "]")
    if perfoptions:
        lines.append("")
        lines.append("[" + base + "\\PerfOptions]")
        if cpu is not None:
            lines.append('"CpuPriorityClass"=dword:%08x' % (cpu & 0xFFFFFFFF))
        for v in extra_perf_values:
            lines.append(v)
    for s in extra_sections:
        lines.append("")
        lines.append("[" + s + "]")
    text = "\r\n".join(lines) + "\r\n"
    if encoding == "utf-16-le-bom":
        return codecs.BOM_UTF16_LE + text.encode("utf-16-le")
    if encoding == "utf-8":
        return text.encode("utf-8")
    if encoding == "utf-8-bom":
        return codecs.BOM_UTF8 + text.encode("utf-8")
    if encoding == "utf-16-le":
        return text.encode("utf-16-le")
    if encoding == "cp1252":
        return text.encode("cp1252")
    raise ValueError(encoding)


class _Sandbox(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.reg_dir = os.path.join(self._td.name, "Registro_Sistema")
        self.ifeo_path = os.path.join(self.reg_dir, "ifeo_state.json")
        self.mig_path = os.path.join(self.reg_dir, "legacy_ifeo_migrations.json")
        self.backup_dir = os.path.join(self._td.name, "backup")
        self.estado_path = os.path.join(self.backup_dir, "estado_sistema.json")

        self._patches = [
            mock.patch.object(seguranca, "ARQUIVO_IFEO", self.ifeo_path),
            mock.patch.object(seguranca, "ARQUIVO_MIGRACOES_IFEO", self.mig_path),
            mock.patch.object(seguranca, "PASTA_BACKUP_REG", self.reg_dir),
            mock.patch.object(seguranca, "PASTA_BACKUP", self.backup_dir),
            mock.patch.object(seguranca, "ARQUIVO_ESTADO", self.estado_path),
            mock.patch.object(seguranca, "log"),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def _patch_winreg(self, fake):
        p = mock.patch.object(seguranca, "winreg", fake)
        p.start()
        self.addCleanup(p.stop)
        return fake

    def _escrever_reg(self, data, nome="backup_prioridade_aclient.exe.reg"):
        os.makedirs(self.reg_dir, exist_ok=True)
        caminho = os.path.join(self.reg_dir, nome)
        with open(caminho, "wb") as f:
            f.write(data)
        return caminho

    def _ler_metadata(self):
        if not os.path.isfile(self.ifeo_path):
            return None
        with open(self.ifeo_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _ler_migracoes(self):
        if not os.path.isfile(self.mig_path):
            return {}
        with open(self.mig_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _perf(self, fake, exe):
        return fake.keys.get(IFEO_BASE + "\\" + exe.lower() + "\\perfoptions")


class TestParser(_Sandbox):
    def _parse(self, data, exe=G_EXE):
        caminho = self._escrever_reg(data)
        return seguranca._parsear_backup_prioridade_legado(caminho, exe)

    def test_01_utf16le_bom_valido(self):
        res, err = self._parse(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self.assertIsNone(err)
        self.assertTrue(res["perfoptions_existed"])
        self.assertEqual(res["values_before"]["CpuPriorityClass"]["value"], 2)
        self.assertEqual(res["values_before"]["CpuPriorityClass"]["type"], REG_DWORD)

    def test_02_formato_exportado_normal(self):
        data = _reg_bytes(G_EXE, perfoptions=True, cpu=6,
                          extra_perf_values=['"IoPriority"=dword:00000003'])
        res, err = self._parse(data)
        self.assertIsNone(err)
        # Somente CpuPriorityClass interessa para ownership.
        self.assertEqual(set(res["values_before"].keys()), {"CpuPriorityClass"})

    def test_03_perfoptions_cpu_dword_presente(self):
        res, err = self._parse(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self.assertIsNone(err)
        self.assertEqual(res["values_before"]["CpuPriorityClass"]["value"], 2)

    def test_04_perfoptions_sem_cpu(self):
        res, err = self._parse(_reg_bytes(G_EXE, perfoptions=True, cpu=None))
        self.assertIsNone(err)
        self.assertTrue(res["perfoptions_existed"])
        self.assertEqual(res["values_before"], {})

    def test_05_perfoptions_ausente(self):
        res, err = self._parse(_reg_bytes(G_EXE, perfoptions=False))
        self.assertIsNone(err)
        self.assertFalse(res["perfoptions_existed"])
        self.assertEqual(res["values_before"], {})

    def test_06_arquivo_vazio(self):
        res, err = self._parse(b"")
        self.assertIsNone(res)
        self.assertIn("vazio", err)

    def test_07_arquivo_corrompido(self):
        res, err = self._parse(b"\x00\x01\x02 garbage no sections")
        self.assertIsNone(res)
        self.assertIsNotNone(err)

    def test_08_secao_exe_diferente(self):
        base = ("HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\"
                "Image File Execution Options\\aika.exe")
        data = _reg_bytes(G_EXE, perfoptions=True, cpu=2,
                          extra_sections=[base])
        res, err = self._parse(data)
        self.assertIsNone(res)
        self.assertIn("inesperado", err)

    def test_09_path_fora_ifo(self):
        data = _reg_bytes(G_EXE, perfoptions=True, cpu=2,
                          extra_sections=["HKEY_LOCAL_MACHINE\\SOFTWARE\\Evil\\Key"])
        res, err = self._parse(data)
        self.assertIsNone(res)
        self.assertIn("inesperado", err)

    def test_10_tipo_inesperado(self):
        data = _reg_bytes(G_EXE, perfoptions=True,
                          extra_perf_values=['"CpuPriorityClass"="2"'])
        res, err = self._parse(data)
        self.assertIsNone(res)
        self.assertIn("tipo inesperado", err)

    def test_11_dword_malformado(self):
        data = _reg_bytes(G_EXE, perfoptions=True,
                          extra_perf_values=['"CpuPriorityClass"=dword:zzzz'])
        res, err = self._parse(data)
        self.assertIsNone(res)
        self.assertIn("malformado", err)

    def test_12_filename_traversal_rejeitado(self):
        self.assertIsNone(seguranca._normalizar_nome_ifeo("..\\evil.exe"))
        self.assertIsNone(seguranca._normalizar_nome_ifeo("a/b.exe"))
        self.assertEqual(seguranca._tentar_adotar_ifeo_legado("..\\evil.exe"), seguranca.LEGADO_INVALIDO)


class TestAdocao(_Sandbox):
    def test_13_original_2_atual_6_adota_e_restaura(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        self.assertEqual(self._perf(fake, G_EXE)["CpuPriorityClass"], (2, REG_DWORD))
        ent = self._ler_metadata()["executables"][G_EXE]
        self.assertEqual(ent["values_before"]["CpuPriorityClass"]["value"], 2)
        self.assertEqual(ent["source"], "legacy_reg")

    def test_14_valor_ausente_remove_apenas_valor(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=None))
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {
            "CpuPriorityClass": (V, REG_DWORD), "IoPriority": (3, REG_DWORD)})))
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        perf = self._perf(fake, G_EXE)
        self.assertNotIn("CpuPriorityClass", perf)
        self.assertEqual(perf["IoPriority"], (3, REG_DWORD))

    def test_15_perfoptions_ausente_remove_subchave_se_vazia(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=False))
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        self.assertNotIn(IFEO_BASE + "\\" + G_EXE + "\\perfoptions", fake.keys)

    def test_16_valor_externo_preservado(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {
            "CpuPriorityClass": (V, REG_DWORD), "IoPriority": (3, REG_DWORD)})))
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        perf = self._perf(fake, G_EXE)
        self.assertEqual(perf["CpuPriorityClass"], (2, REG_DWORD))
        self.assertEqual(perf["IoPriority"], (3, REG_DWORD))

    def test_17_atual_1_nao_sobrescreve(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (1, REG_DWORD)})))
        self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_CONFLITO)
        self.assertIsNone(self._ler_metadata())
        self.assertEqual(self._perf(fake, G_EXE)["CpuPriorityClass"], (1, REG_DWORD))

    def test_18_atual_ausente_nao_inventa(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE)))
        self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_CONFLITO)
        self.assertIsNone(self._ler_metadata())
        self.assertNotIn(IFEO_BASE + "\\" + G_EXE + "\\perfoptions", fake.keys)

    def test_19_backup_invalido_nenhuma_alteracao(self):
        self._escrever_reg(b"Windows Registry Editor Version 5.00\r\n")
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_INVALIDO)
        self.assertIsNone(self._ler_metadata())
        self.assertEqual(self._perf(fake, G_EXE)["CpuPriorityClass"], (V, REG_DWORD))

    def test_20_sem_backup_nenhuma_restauracao(self):
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_SEM_BACKUP)
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        self.assertEqual(self._perf(fake, G_EXE)["CpuPriorityClass"], (V, REG_DWORD))


class TestUpgrade(_Sandbox):
    def test_21_upgrade_restaurar_sistema(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._escrever_reg(b"Windows Registry Editor Version 5.00\r\n", nome="backup_gamedvr.reg")
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        with mock.patch.object(seguranca, "restaurar_snapshot_sistema", return_value=seguranca.RESTAURACAO_SUCESSO), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True), \
             mock.patch.object(seguranca, "finalizar_snapshot_sistema"):
            ok, _ = seguranca.restaurar_registro_sistema()
        self.assertTrue(ok)
        self.assertEqual(self._perf(fake, G_EXE)["CpuPriorityClass"], (2, REG_DWORD))

    def test_22_upgrade_otimizar_sem_restaurar(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        ent = self._ler_metadata()["executables"][G_EXE]
        self.assertEqual(ent["values_before"]["CpuPriorityClass"]["value"], 2)
        self.assertEqual(ent["source"], "legacy_reg")

    def test_23_segunda_aplicacao_nao_baseline_6(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        self.assertEqual(self._ler_metadata()["executables"][G_EXE]["values_before"]["CpuPriorityClass"]["value"], 2)

    def test_24_restore_posterior_recupera_pre_v4(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        self.assertEqual(self._perf(fake, G_EXE)["CpuPriorityClass"], (2, REG_DWORD))


class TestConsumoUnico(_Sandbox):
    def test_25_marcado_por_sha256(self):
        data = _reg_bytes(G_EXE, perfoptions=True, cpu=2)
        caminho = self._escrever_reg(data)
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_ADOTADO)
        rec = self._ler_migracoes()["backup_prioridade_aclient.exe.reg"]
        self.assertTrue(rec["consumed"])
        self.assertEqual(rec["sha256"], seguranca._sha256_arquivo(caminho))

    def test_26_mesmo_backup_nao_readotado(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_ADOTADO)
        if os.path.exists(self.ifeo_path):
            os.remove(self.ifeo_path)
        self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_JA_COBERTO)
        self.assertIsNone(self._ler_metadata())

    def test_27_mesmo_nome_hash_diferente_reavaliado(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_ADOTADO)
        if os.path.exists(self.ifeo_path):
            os.remove(self.ifeo_path)
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=5))
        self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_ADOTADO)
        self.assertEqual(self._ler_metadata()["executables"][G_EXE]["values_before"]["CpuPriorityClass"]["value"], 5)

    def test_28_falha_antes_persistir_nao_marca(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        with mock.patch.object(seguranca, "_escrever_ifeo_metadata_atomico", side_effect=OSError("disco cheio")):
            self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_INVALIDO)
        self.assertEqual(self._ler_migracoes(), {})
        self.assertIsNone(self._ler_metadata())

    def test_29_backup_invalido_nao_marca(self):
        self._escrever_reg(b"Windows Registry Editor Version 5.00\r\n")
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_INVALIDO)
        self.assertEqual(self._ler_migracoes(), {})

    def test_30_artefato_original_nao_apagado(self):
        caminho = self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_ADOTADO)
        self.assertTrue(os.path.isfile(caminho))


class TestMultiplosExes(_Sandbox):
    def test_31_adocao_independente(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._patch_winreg(FakeIfeoReg({
            **_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)}),
            **_estado_ifeo(G_EXE2, {"CpuPriorityClass": (V, REG_DWORD)}),
        }))
        self.assertEqual(seguranca._adotar_legados_pendentes(), seguranca.RESTAURACAO_SUCESSO)
        meta = self._ler_metadata()["executables"]
        self.assertIn(G_EXE, meta)
        self.assertNotIn(G_EXE2, meta)

    def test_32_conflito_um_nao_altera_outro(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._escrever_reg(_reg_bytes(G_EXE2, perfoptions=True, cpu=4), nome="backup_prioridade_aika.exe.reg")
        fake = self._patch_winreg(FakeIfeoReg({
            **_estado_ifeo(G_EXE, {"CpuPriorityClass": (1, REG_DWORD)}),
            **_estado_ifeo(G_EXE2, {"CpuPriorityClass": (V, REG_DWORD)}),
        }))
        self.assertEqual(seguranca._adotar_legados_pendentes(), seguranca.RESTAURACAO_PARCIAL)
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_PARCIAL)
        self.assertEqual(self._perf(fake, G_EXE)["CpuPriorityClass"], (1, REG_DWORD))
        self.assertEqual(self._perf(fake, G_EXE2)["CpuPriorityClass"], (4, REG_DWORD))

    def test_33_sem_backup_nao_bloqueia_restore(self):
        self._escrever_reg(_reg_bytes(G_EXE2, perfoptions=True, cpu=4), nome="backup_prioridade_aika.exe.reg")
        fake = self._patch_winreg(FakeIfeoReg({
            **_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)}),
            **_estado_ifeo(G_EXE2, {"CpuPriorityClass": (V, REG_DWORD)}),
        }))
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        self.assertEqual(self._perf(fake, G_EXE)["CpuPriorityClass"], (V, REG_DWORD))
        self.assertEqual(self._perf(fake, G_EXE2)["CpuPriorityClass"], (4, REG_DWORD))

    def test_34_exe_fora_allowlist_rejeitado(self):
        self._escrever_reg(_reg_bytes("notepad.exe", perfoptions=True, cpu=2), nome="backup_prioridade_notepad.exe.reg")
        self._patch_winreg(FakeIfeoReg())
        self.assertEqual(seguranca._tentar_adotar_ifeo_legado("notepad.exe"), seguranca.LEGADO_INVALIDO)
        self.assertIsNone(self._ler_metadata())


class TestIntegracao(_Sandbox):
    def test_35_restaurar_registro_sistema_usa_ponte(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._escrever_reg(b"Windows Registry Editor Version 5.00\r\n", nome="backup_gamedvr.reg")
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        with mock.patch.object(seguranca, "restaurar_snapshot_sistema", return_value=seguranca.RESTAURACAO_SUCESSO), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex, \
             mock.patch.object(seguranca, "finalizar_snapshot_sistema"):
            ok, _ = seguranca.restaurar_registro_sistema()
        self.assertTrue(ok)
        self.assertEqual(self._perf(fake, G_EXE)["CpuPriorityClass"], (2, REG_DWORD))
        importados = [" ".join(str(a) for a in c.args[0]) for c in mex.call_args_list]
        self.assertFalse(any("backup_prioridade_aclient.exe.reg" in s for s in importados))
        self.assertFalse(any("delete" in s.lower() for s in importados))

    def test_36_moderno_prioridade_sobre_legado(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        os.makedirs(self.reg_dir, exist_ok=True)
        with open(self.ifeo_path, "w", encoding="utf-8") as f:
            json.dump({"format_version": 1, "executables": {
                G_EXE: {
                    "ifeo_key_existed": True,
                    "perfoptions_existed": True,
                    "values_before": {"CpuPriorityClass": {"type": REG_DWORD, "value": 5}},
                    "optimizer_values": {"CpuPriorityClass": {"type": REG_DWORD, "value": V}},
                },
            }}, f)
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        self.assertEqual(self._perf(fake, G_EXE)["CpuPriorityClass"], (5, REG_DWORD))

    def test_37_legado_nao_importado_via_reg_import(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._escrever_reg(b"Windows Registry Editor Version 5.00\r\n", nome="backup_gamedvr.reg")
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        with mock.patch.object(seguranca, "restaurar_snapshot_sistema", return_value=seguranca.RESTAURACAO_SUCESSO), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex, \
             mock.patch.object(seguranca, "finalizar_snapshot_sistema"):
            seguranca.restaurar_registro_sistema()
        importados = [" ".join(str(a) for a in c.args[0]) for c in mex.call_args_list]
        self.assertFalse(any("backup_prioridade" in s for s in importados))

    def test_38_nenhum_reg_delete_cego(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._escrever_reg(b"Windows Registry Editor Version 5.00\r\n", nome="backup_gamedvr.reg")
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        with mock.patch.object(seguranca, "restaurar_snapshot_sistema", return_value=seguranca.RESTAURACAO_SUCESSO), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex, \
             mock.patch.object(seguranca, "finalizar_snapshot_sistema"):
            seguranca.restaurar_registro_sistema()
        for c in mex.call_args_list:
            self.assertNotIn("delete", " ".join(str(a).lower() for a in c.args[0]))

    def test_39_snapshot_finaliza_sucesso(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._escrever_reg(b"Windows Registry Editor Version 5.00\r\n", nome="backup_gamedvr.reg")
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        with mock.patch.object(seguranca, "restaurar_snapshot_sistema", return_value=seguranca.RESTAURACAO_SUCESSO), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True), \
             mock.patch.object(seguranca, "finalizar_snapshot_sistema") as fin:
            ok, _ = seguranca.restaurar_registro_sistema()
        self.assertTrue(ok)
        fin.assert_called_once()

    def test_40_partial_preserva_metadata(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._escrever_reg(b"Windows Registry Editor Version 5.00\r\n", nome="backup_gamedvr.reg")
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (1, REG_DWORD)})))
        with mock.patch.object(seguranca, "restaurar_snapshot_sistema", return_value=seguranca.RESTAURACAO_SUCESSO), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True), \
             mock.patch.object(seguranca, "finalizar_snapshot_sistema") as fin:
            ok, _ = seguranca.restaurar_registro_sistema()
        self.assertFalse(ok)
        fin.assert_not_called()
        self.assertEqual(self._perf(fake, G_EXE)["CpuPriorityClass"], (1, REG_DWORD))


class TestIsolamento(_Sandbox):
    def test_41_nenhum_subprocess_real(self):
        guard = mock.Mock()
        guard.run = _proibido
        guard.check_output = _proibido
        guard.Popen = _proibido
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        with mock.patch.object(seguranca, "subprocess", guard):
            self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_ADOTADO)
            self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)

    def test_42_regexe_real_nunca_executado(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        with mock.patch.object(seguranca, "executar_comando_seguro", side_effect=_proibido):
            self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_ADOTADO)
            self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)

    def test_43_artefato_original_nao_modificado(self):
        data = _reg_bytes(G_EXE, perfoptions=True, cpu=2)
        caminho = self._escrever_reg(data)
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_ADOTADO)
        with open(caminho, "rb") as f:
            self.assertEqual(f.read(), data)

    def test_44_config_real_byte_identico(self):
        import config
        caminho = config.ARQUIVO_CONFIG
        if not os.path.isfile(caminho):
            self.skipTest("config.json real ausente")
        before = open(caminho, "rb").read()
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        seguranca._tentar_adotar_ifeo_legado(G_EXE)
        seguranca._restaurar_ifeo_ownership()
        self.assertEqual(open(caminho, "rb").read(), before)

    def test_45_estado_real_byte_identico(self):
        import config
        caminho = config.ARQUIVO_ESTADO
        before = open(caminho, "rb").read() if os.path.isfile(caminho) else None
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        seguranca._tentar_adotar_ifeo_legado(G_EXE)
        seguranca._restaurar_ifeo_ownership()
        after = open(caminho, "rb").read() if os.path.isfile(caminho) else None
        self.assertEqual(before, after)

    def test_46_bridge_nao_usa_shutil(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        with mock.patch.object(seguranca.shutil, "copy2", side_effect=_proibido), \
             mock.patch.object(seguranca.shutil, "copy", side_effect=_proibido), \
             mock.patch.object(seguranca.shutil, "move", side_effect=_proibido):
            self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_ADOTADO)
            self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)


class TestAmbiguidade(_Sandbox):
    def _legado_ambiguo(self, cpu=6):
        return _reg_bytes(G_EXE, perfoptions=True, cpu=cpu)

    def test_01_before_6_current_6_nao_adota(self):
        self._escrever_reg(self._legado_ambiguo(6))
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_AMBIGUO)
        self.assertIsNone(self._ler_metadata())
        self.assertEqual(self._perf(fake, G_EXE)["CpuPriorityClass"], (V, REG_DWORD))

    def test_02_nao_cria_baseline_confiavel(self):
        self._escrever_reg(self._legado_ambiguo(6))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        seguranca._tentar_adotar_ifeo_legado(G_EXE)
        self.assertIsNone(self._ler_metadata())

    def test_03_nao_marca_consumido(self):
        self._escrever_reg(self._legado_ambiguo(6))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        seguranca._tentar_adotar_ifeo_legado(G_EXE)
        self.assertEqual(self._ler_migracoes(), {})

    def test_04_nao_escreve_registry(self):
        self._escrever_reg(self._legado_ambiguo(6))
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        seguranca._tentar_adotar_ifeo_legado(G_EXE)
        self.assertEqual(self._perf(fake, G_EXE)["CpuPriorityClass"], (V, REG_DWORD))

    def test_05_restore_retorna_partial(self):
        self._escrever_reg(self._legado_ambiguo(6))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_PARCIAL)

    def test_06_before_6_current_1_nao_sobrescreve(self):
        self._escrever_reg(self._legado_ambiguo(6))
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (1, REG_DWORD)})))
        self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_AMBIGUO)
        self.assertEqual(self._perf(fake, G_EXE)["CpuPriorityClass"], (1, REG_DWORD))

    def test_07_before_6_current_ausente_nao_cria(self):
        self._escrever_reg(self._legado_ambiguo(6))
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE)))
        self.assertEqual(seguranca._tentar_adotar_ifeo_legado(G_EXE), seguranca.LEGADO_AMBIGUO)
        self.assertNotIn(IFEO_BASE + "\\" + G_EXE + "\\perfoptions", fake.keys)


    def test_08_before_2_current_6_continua(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        self.assertEqual(self._perf(fake, G_EXE)["CpuPriorityClass"], (2, REG_DWORD))

    def test_09_before_ausente_current_6_continua(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=None))
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        self.assertNotIn("CpuPriorityClass", self._perf(fake, G_EXE))

    def test_10_perfoptions_ausente_current_6_continua(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=False))
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        self.assertNotIn(IFEO_BASE + "\\" + G_EXE + "\\perfoptions", fake.keys)

    def test_11_multiplos_restaura_seguro_partial(self):
        self._escrever_reg(_reg_bytes(G_EXE, perfoptions=True, cpu=2))
        self._escrever_reg(_reg_bytes(G_EXE2, perfoptions=True, cpu=6), nome="backup_prioridade_aika.exe.reg")
        fake = self._patch_winreg(FakeIfeoReg({
            **_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)}),
            **_estado_ifeo(G_EXE2, {"CpuPriorityClass": (V, REG_DWORD)}),
        }))
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_PARCIAL)
        self.assertEqual(self._perf(fake, G_EXE)["CpuPriorityClass"], (2, REG_DWORD))
        self.assertEqual(self._perf(fake, G_EXE2)["CpuPriorityClass"], (V, REG_DWORD))

    def test_12_backup_ambiguo_intacto(self):
        data = self._legado_ambiguo(6)
        caminho = self._escrever_reg(data)
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        seguranca._tentar_adotar_ifeo_legado(G_EXE)
        with open(caminho, "rb") as f:
            self.assertEqual(f.read(), data)

    def test_13_hash_ambiguo_nao_consumido(self):
        self._escrever_reg(self._legado_ambiguo(6))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        seguranca._tentar_adotar_ifeo_legado(G_EXE)
        seguranca._restaurar_ifeo_ownership()
        self.assertEqual(self._ler_migracoes(), {})

    def test_14_moderno_prioridade_sobre_ambiguo(self):
        self._escrever_reg(self._legado_ambiguo(6))
        os.makedirs(self.reg_dir, exist_ok=True)
        with open(self.ifeo_path, "w", encoding="utf-8") as f:
            json.dump({"format_version": 1, "executables": {
                G_EXE: {
                    "ifeo_key_existed": True,
                    "perfoptions_existed": True,
                    "values_before": {"CpuPriorityClass": {"type": REG_DWORD, "value": 5}},
                    "optimizer_values": {"CpuPriorityClass": {"type": REG_DWORD, "value": V}},
                },
            }}, f)
        fake = self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca._restaurar_ifeo_ownership(), seguranca.RESTAURACAO_SUCESSO)
        self.assertEqual(self._perf(fake, G_EXE)["CpuPriorityClass"], (5, REG_DWORD))


    def test_15_snapshot_nao_finaliza_partial(self):
        self._escrever_reg(self._legado_ambiguo(6))
        self._escrever_reg(b"Windows Registry Editor Version 5.00\r\n", nome="backup_gamedvr.reg")
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        with mock.patch.object(seguranca, "restaurar_snapshot_sistema", return_value=seguranca.RESTAURACAO_SUCESSO), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True), \
             mock.patch.object(seguranca, "finalizar_snapshot_sistema") as fin:
            ok, _ = seguranca.restaurar_registro_sistema()
        self.assertFalse(ok)
        fin.assert_not_called()

    def test_16_otimizar_nao_baseline_falsa(self):
        self._escrever_reg(self._legado_ambiguo(6))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca.garantir_ifeo_ownership(G_EXE), seguranca.IFEO_NOOP)
        self.assertIsNone(self._ler_metadata())

    def test_17_nenhuma_escrita_desnecessaria(self):
        self._escrever_reg(self._legado_ambiguo(6))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        self.assertEqual(seguranca.garantir_ifeo_ownership(G_EXE), seguranca.IFEO_NOOP)

    def test_18_before_6_current_2_captura_nova_baseline(self):
        self._escrever_reg(self._legado_ambiguo(6))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (2, REG_DWORD)})))
        self.assertTrue(seguranca.garantir_ifeo_ownership(G_EXE))
        ent = self._ler_metadata()["executables"][G_EXE]
        self.assertEqual(ent["values_before"]["CpuPriorityClass"]["value"], 2)

    def test_19_backup_auditavel(self):
        data = self._legado_ambiguo(6)
        caminho = self._escrever_reg(data)
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        seguranca._tentar_adotar_ifeo_legado(G_EXE)
        self.assertTrue(os.path.isfile(caminho))
        self.assertTrue(os.path.getsize(caminho) > 0)

    def test_20_nenhum_consumo_falso(self):
        self._escrever_reg(self._legado_ambiguo(6))
        self._patch_winreg(FakeIfeoReg(_estado_ifeo(G_EXE, {"CpuPriorityClass": (V, REG_DWORD)})))
        seguranca._tentar_adotar_ifeo_legado(G_EXE)
        seguranca.garantir_ifeo_ownership(G_EXE)
        self.assertEqual(self._ler_migracoes(), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)










