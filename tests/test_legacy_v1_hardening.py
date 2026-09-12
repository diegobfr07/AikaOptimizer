# -*- coding: utf-8 -*-
"""Hardening final do P1 #2 — restauração segura de snapshot legado v1.

Cobre: política conservadora v1 (casos A/B/C/D), normalização de InterfaceGuid,
critério NameServer (automático × estático), lifecycle de resultado parcial e
regressão v2. NENHUM teste executa powercfg/reg/PowerShell/Registry reais.
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


G_ETH = "11111111-2222-3333-4444-555555555555"
G_WIFI = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
G_ETH2 = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
G_ETH3 = "33333333-4444-5555-6666-777777777777"
G_VIRT = "99999999-8888-7777-6666-555555555555"


def _ad(guid, alias="", index=0):
    return {"interface_guid": guid, "interface_alias": alias or guid,
            "interface_index": index}


def _iface(guid, mode="automatic", servers=None, alias="", index=0):
    return {
        "interface_guid": guid,
        "interface_alias": alias or guid,
        "interface_index": index,
        "mode": mode,
        "servers_ipv4": list(servers or []),
    }


class _Sandbox(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.backup_dir = os.path.join(self._td.name, "backup")
        self.reg_dir = os.path.join(self.backup_dir, "Registro_Sistema")
        self.estado_path = os.path.join(self.backup_dir, "estado_sistema.json")

        subprocess_guard = mock.Mock()
        subprocess_guard.run = _proibido
        subprocess_guard.check_output = _proibido
        subprocess_guard.Popen = _proibido

        self._patches = [
            mock.patch.object(seguranca, "PASTA_BACKUP", self.backup_dir),
            mock.patch.object(seguranca, "PASTA_BACKUP_REG", self.reg_dir),
            mock.patch.object(seguranca, "ARQUIVO_ESTADO", self.estado_path),
            mock.patch.object(seguranca, "log"),
            mock.patch.object(seguranca, "subprocess", subprocess_guard),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def _escrever(self, dados):
        os.makedirs(self.backup_dir, exist_ok=True)
        with open(self.estado_path, "w", encoding="utf-8") as f:
            json.dump(dados, f)

    def _ler(self):
        with open(self.estado_path, "r", encoding="utf-8") as f:
            return json.load(f)


class TestV1Restauracao(_Sandbox):
    def test_v1_um_adaptador_aplica_dns_so_nele(self):
        self._escrever({"power_plan": None, "dns": ["8.8.8.8", "1.1.1.1"], "timestamp": 1})
        with mock.patch.object(seguranca, "_obter_adaptadores_ativos_detalhados",
                               return_value=[_ad(G_ETH, "Ethernet", 12)]), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertEqual(seguranca.restaurar_snapshot_sistema(), seguranca.RESTAURACAO_SUCESSO)
        cmd = " ".join(str(x) for x in mex.call_args.args[0])
        self.assertIn("InterfaceIndex 12", cmd)
        self.assertIn("8.8.8.8", cmd)
        self.assertIn("1.1.1.1", cmd)

    def test_v1_dois_adaptadores_nao_aplica_dns(self):
        self._escrever({"power_plan": None, "dns": ["8.8.8.8"], "timestamp": 1})
        ads = [_ad(G_ETH, "Ethernet", 12), _ad(G_WIFI, "Wi-Fi", 7)]
        with mock.patch.object(seguranca, "_obter_adaptadores_ativos_detalhados", return_value=ads), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertEqual(seguranca.restaurar_snapshot_sistema(), seguranca.RESTAURACAO_PARCIAL)
        mex.assert_not_called()

    def test_v1_tres_adaptadores_nao_aplica_dns(self):
        self._escrever({"power_plan": None, "dns": ["8.8.8.8"], "timestamp": 1})
        ads = [_ad(G_ETH, "Ethernet", 12), _ad(G_WIFI, "Wi-Fi", 7),
               _ad(G_ETH2, "Ethernet 2", 8)]
        with mock.patch.object(seguranca, "_obter_adaptadores_ativos_detalhados", return_value=ads), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertEqual(seguranca.restaurar_snapshot_sistema(), seguranca.RESTAURACAO_PARCIAL)
        mex.assert_not_called()

    def test_v1_nenhum_adaptador_nada_altera(self):
        self._escrever({"power_plan": None, "dns": ["8.8.8.8"], "timestamp": 1})
        with mock.patch.object(seguranca, "_obter_adaptadores_ativos_detalhados", return_value=[]), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertEqual(seguranca.restaurar_snapshot_sistema(), seguranca.RESTAURACAO_PARCIAL)
        mex.assert_not_called()

    def test_v1_multiplos_adaptadores_resultado_parcial(self):
        self._escrever({"power_plan": "PLAN-X", "dns": ["8.8.8.8"], "timestamp": 1})
        ads = [_ad(G_ETH, "Ethernet", 12), _ad(G_WIFI, "Wi-Fi", 7)]
        with mock.patch.object(seguranca, "_obter_adaptadores_ativos_detalhados", return_value=ads), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True):
            self.assertEqual(seguranca.restaurar_snapshot_sistema(), seguranca.RESTAURACAO_PARCIAL)

    def test_v1_ambiguo_snapshot_preservado(self):
        self._escrever({"power_plan": "PLAN-X", "dns": ["8.8.8.8"], "timestamp": 1})
        ads = [_ad(G_ETH, "Ethernet", 12), _ad(G_WIFI, "Wi-Fi", 7)]
        with mock.patch.object(seguranca, "_obter_adaptadores_ativos_detalhados", return_value=ads), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True):
            seguranca.restaurar_snapshot_sistema()
        self.assertTrue(os.path.isfile(self.estado_path))

    def test_v1_ambiguo_power_plan_ainda_restaurado(self):
        self._escrever({"power_plan": "PLAN-X", "dns": ["8.8.8.8"], "timestamp": 1})
        ads = [_ad(G_ETH, "Ethernet", 12), _ad(G_WIFI, "Wi-Fi", 7)]
        with mock.patch.object(seguranca, "_obter_adaptadores_ativos_detalhados", return_value=ads), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertEqual(seguranca.restaurar_snapshot_sistema(), seguranca.RESTAURACAO_PARCIAL)
        self.assertEqual(len(mex.call_args_list), 1)
        cmd = " ".join(str(x) for x in mex.call_args_list[0].args[0])
        self.assertIn("powercfg", cmd)
        self.assertIn("PLAN-X", cmd)

    def test_v1_ambiguo_snapshot_nao_finalizado(self):
        self._escrever({"power_plan": "PLAN-X", "dns": ["8.8.8.8"], "timestamp": 1})
        os.makedirs(self.reg_dir, exist_ok=True)
        with open(os.path.join(self.reg_dir, "backup.reg"), "w") as f:
            f.write("Windows Registry Editor Version 5.00\n")
        ads = [_ad(G_ETH, "Ethernet", 12), _ad(G_WIFI, "Wi-Fi", 7)]
        with mock.patch.object(seguranca, "_obter_adaptadores_ativos_detalhados", return_value=ads), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True), \
             mock.patch.object(seguranca, "finalizar_snapshot_sistema") as fin:
            ok, _ = seguranca.restaurar_registro_sistema()
        self.assertFalse(ok)
        fin.assert_not_called()
        self.assertTrue(os.path.isfile(self.estado_path))

    def test_v1_um_adaptador_nao_toca_virtual(self):
        self._escrever({"power_plan": None, "dns": ["8.8.8.8"], "timestamp": 1})
        with mock.patch.object(seguranca, "_obter_adaptadores_ativos_detalhados",
                               return_value=[_ad(G_ETH, "Ethernet", 12)]), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            seguranca.restaurar_snapshot_sistema()
        cmd = " ".join(str(x) for x in mex.call_args.args[0])
        self.assertIn("InterfaceIndex 12", cmd)
        self.assertNotIn(G_VIRT, cmd)

    def test_v1_nunca_replica_dns_em_multiplas_interfaces(self):
        self._escrever({"power_plan": None, "dns": ["8.8.8.8", "1.1.1.1"], "timestamp": 1})
        ads = [_ad(G_ETH, "Ethernet", 12), _ad(G_WIFI, "Wi-Fi", 7),
               _ad(G_ETH2, "Ethernet 2", 8)]
        with mock.patch.object(seguranca, "_obter_adaptadores_ativos_detalhados", return_value=ads), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            seguranca.restaurar_snapshot_sistema()
        mex.assert_not_called()


class TestGUIDNormalizacao(_Sandbox):
    def test_guid_chaves_igual_sem_chaves(self):
        self.assertEqual(
            seguranca._normalizar_interface_guid("{ABCDEF12-3456-7890-ABCD-EF1234567890}"),
            "abcdef12-3456-7890-abcd-ef1234567890")

    def test_guid_upper_lower(self):
        self.assertEqual(
            seguranca._normalizar_interface_guid("ABCDEF12-3456-7890-ABCD-EF1234567890"),
            "abcdef12-3456-7890-abcd-ef1234567890")

    def test_guid_whitespace_normalizado(self):
        self.assertEqual(
            seguranca._normalizar_interface_guid("  abcdef12-3456-7890-abcd-ef1234567890  "),
            "abcdef12-3456-7890-abcd-ef1234567890")

    def test_guid_invalido_rejeitado(self):
        self.assertIsNone(seguranca._normalizar_interface_guid("nao-e-um-guid"))

    def test_guid_vazio_rejeitado(self):
        self.assertIsNone(seguranca._normalizar_interface_guid(""))
        self.assertIsNone(seguranca._normalizar_interface_guid("   "))
        self.assertIsNone(seguranca._normalizar_interface_guid(None))

    def test_guid_nao_string_rejeitado(self):
        self.assertIsNone(seguranca._normalizar_interface_guid(12345))

    def test_lookup_nao_cai_para_alias(self):
        self.assertIsNone(seguranca._resolver_index_por_guid("nao-e-um-guid"))
        self.assertIsNone(seguranca._resolver_index_por_guid(""))


class _FakeKey:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeWinreg:
    HKEY_LOCAL_MACHINE = 1
    KEY_READ = 2

    def __init__(self, values):
        self._values = values

    def OpenKey(self, *a, **k):
        return _FakeKey()

    def QueryValueEx(self, key, nome):
        if nome in self._values:
            return (self._values[nome], 1)
        raise FileNotFoundError()


class TestNameServer(_Sandbox):
    def _ler_dns(self, name_server=None, dhcp=None):
        values = {}
        if name_server is not None:
            values["NameServer"] = name_server
        if dhcp is not None:
            values["DhcpNameServer"] = dhcp
        with mock.patch.object(seguranca, "winreg", _FakeWinreg(values)):
            return seguranca._ler_dns_registro_interface(G_ETH)

    def test_nameserver_ausente_automatic(self):
        self.assertEqual(self._ler_dns(name_server=None), ("automatic", []))

    def test_nameserver_vazio_automatic(self):
        self.assertEqual(self._ler_dns(name_server=""), ("automatic", []))

    def test_nameserver_espacos_automatic(self):
        self.assertEqual(self._ler_dns(name_server="   "), ("automatic", []))

    def test_nameserver_um_ipv4_static(self):
        self.assertEqual(self._ler_dns(name_server="8.8.8.8"), ("static", ["8.8.8.8"]))

    def test_nameserver_dois_ipv4_static(self):
        self.assertEqual(self._ler_dns(name_server="8.8.8.8 8.8.4.4"),
                         ("static", ["8.8.8.8", "8.8.4.4"]))

    def test_dhcpnameserver_com_nameserver_vazio_automatic(self):
        self.assertEqual(self._ler_dns(name_server="", dhcp="1.1.1.1"), ("automatic", []))

    def test_automatico_nao_transformar_dhcp_em_static(self):
        interface = _iface(G_ETH, "automatic", [])
        with mock.patch.object(seguranca, "_resolver_index_por_guid", return_value=12), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertTrue(seguranca._aplicar_dns_interface(interface))
        cmd = " ".join(str(x) for x in mex.call_args.args[0])
        self.assertIn("ResetServerAddresses", cmd)
        self.assertNotIn("1.1.1.1", cmd)
        self.assertNotIn("8.8.8.8", cmd)


class TestLifecycleV1(_Sandbox):
    def test_restore_v1_parcial_preserva_arquivo(self):
        self._escrever({"power_plan": "PLAN-X", "dns": ["8.8.8.8"], "timestamp": 1})
        ads = [_ad(G_ETH, "Ethernet", 12), _ad(G_WIFI, "Wi-Fi", 7)]
        with mock.patch.object(seguranca, "_obter_adaptadores_ativos_detalhados", return_value=ads), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True):
            self.assertEqual(seguranca.restaurar_snapshot_sistema(), seguranca.RESTAURACAO_PARCIAL)
        self.assertTrue(os.path.isfile(self.estado_path))

    def test_restore_v1_total_um_adaptador_pode_finalizar(self):
        self._escrever({"power_plan": None, "dns": ["8.8.8.8"], "timestamp": 1})
        os.makedirs(self.reg_dir, exist_ok=True)
        with open(os.path.join(self.reg_dir, "backup.reg"), "w") as f:
            f.write("Windows Registry Editor Version 5.00\n")
        with mock.patch.object(seguranca, "_obter_adaptadores_ativos_detalhados",
                               return_value=[_ad(G_ETH, "Ethernet", 12)]), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True), \
             mock.patch.object(seguranca, "finalizar_snapshot_sistema") as fin:
            ok, _ = seguranca.restaurar_registro_sistema()
        self.assertTrue(ok)
        fin.assert_called_once()

    def test_apos_finalizar_proxima_modificacao_gera_v2(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value={"format_version": 2, "power_plan": "P1",
                                             "dns_interfaces": []}):
            seguranca.salvar_snapshot_sistema()
        seguranca.finalizar_snapshot_sistema()
        self.assertFalse(os.path.exists(self.estado_path))
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value={"format_version": 2, "power_plan": "P2",
                                             "dns_interfaces": []}):
            self.assertTrue(seguranca.salvar_snapshot_sistema())
        self.assertEqual(self._ler()["format_version"], 2)
        self.assertEqual(self._ler()["power_plan"], "P2")

    def test_restore_v2_total_continua_finalizando(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value={"format_version": 2, "power_plan": "P1",
                                             "dns_interfaces": []}):
            seguranca.salvar_snapshot_sistema()
        os.makedirs(self.reg_dir, exist_ok=True)
        with open(os.path.join(self.reg_dir, "backup.reg"), "w") as f:
            f.write("Windows Registry Editor Version 5.00\n")
        with mock.patch.object(seguranca, "executar_comando_seguro", return_value=True), \
             mock.patch.object(seguranca, "finalizar_snapshot_sistema") as fin:
            ok, _ = seguranca.restaurar_registro_sistema()
        self.assertTrue(ok)
        fin.assert_called_once()

    def test_restore_v2_parcial_continua_preservando(self):
        estado = {"format_version": 2, "power_plan": "P1", "dns_interfaces": [
            _iface(G_ETH, "static", ["8.8.8.8"])]}
        with mock.patch.object(seguranca, "capturar_estado_sistema", return_value=estado):
            seguranca.salvar_snapshot_sistema()
        os.makedirs(self.reg_dir, exist_ok=True)
        with open(os.path.join(self.reg_dir, "backup.reg"), "w") as f:
            f.write("Windows Registry Editor Version 5.00\n")
        with mock.patch.object(seguranca, "_resolver_index_por_guid", return_value=None), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True), \
             mock.patch.object(seguranca, "finalizar_snapshot_sistema") as fin:
            ok, _ = seguranca.restaurar_registro_sistema()
        self.assertFalse(ok)
        fin.assert_not_called()
        self.assertTrue(os.path.isfile(self.estado_path))


class TestV2Regressao(_Sandbox):
    def test_v2_restaura_ethernet_e_wifi_individualmente(self):
        estado = {"format_version": 2, "power_plan": None, "dns_interfaces": [
            _iface(G_ETH, "static", ["8.8.8.8"], index=12),
            _iface(G_WIFI, "automatic", [], index=7)]}
        with mock.patch.object(seguranca, "_resolver_index_por_guid", side_effect=[12, 7]), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertEqual(seguranca._restaurar_dns_estado(estado), seguranca.RESTAURACAO_SUCESSO)
        cmds = [" ".join(str(x) for x in c[0][0]) for c in mex.call_args_list]
        self.assertTrue(any("8.8.8.8" in c and "InterfaceIndex 12" in c for c in cmds))
        self.assertTrue(any("ResetServerAddresses" in c and "InterfaceIndex 7" in c for c in cmds))

    def test_v2_alias_igual_nao_associa_errado(self):
        estado = {"format_version": 2, "power_plan": None, "dns_interfaces": [
            _iface(G_ETH, "static", ["8.8.8.8"], alias="Ethernet", index=12),
            _iface(G_ETH2, "static", ["1.1.1.1"], alias="Ethernet", index=13)]}
        with mock.patch.object(seguranca, "_resolver_index_por_guid", side_effect=[12, 13]), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            seguranca._restaurar_dns_estado(estado)
        cmds = [" ".join(str(x) for x in c[0][0]) for c in mex.call_args_list]
        self.assertTrue(any("8.8.8.8" in c and "InterfaceIndex 12" in c for c in cmds))
        self.assertTrue(any("1.1.1.1" in c and "InterfaceIndex 13" in c for c in cmds))

    def test_v2_index_alterado_apos_snapshot_resolve_por_guid(self):
        interface = _iface(G_ETH, "static", ["8.8.8.8"], index=999)
        with mock.patch.object(seguranca, "_resolver_index_por_guid", return_value=42) as res, \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertTrue(seguranca._aplicar_dns_interface(interface))
        res.assert_called_once_with(G_ETH)
        cmd = " ".join(str(x) for x in mex.call_args.args[0])
        self.assertIn("InterfaceIndex 42", cmd)


if __name__ == "__main__":
    unittest.main(verbosity=2)





