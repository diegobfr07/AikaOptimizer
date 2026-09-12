# -*- coding: utf-8 -*-
"""Hardening de snapshot/rollback/DNS — baseline persistente vs transacional.

Cobre: baseline idempotente (não sobrescreve), DNS por adaptador (GUID +
automático/estático), rollback transacional de menor escopo, lifecycle de
finalização, compatibilidade v1 e isolamento (nenhum comando real do Windows).
NENHUM teste executa powercfg/Set-DnsClientServerAddress/reg/Registry reais.
"""
import json
import hashlib
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import seguranca  # noqa: E402
import sistema  # noqa: E402


def _iface(guid, mode="automatic", servers=None, alias="", index=0):
    return {
        "interface_guid": guid,
        "interface_alias": alias or guid,
        "interface_index": index,
        "mode": mode,
        "servers_ipv4": list(servers or []),
    }

G_ETH = "11111111-2222-3333-4444-555555555555"
G_WIFI = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
G_ETH1 = "66666666-7777-8888-9999-000000000000"
G_ETH2 = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
G_AUSENTE = "99999999-8888-7777-6666-555555555555"
G_TESTE = "22222222-3333-4444-5555-666666666666"


def _proibido(*a, **k):
    raise AssertionError("teste não pode executar comando real do Windows")


class SnapshotSandbox(unittest.TestCase):
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

    def _captura_v2(self, plan="PLAN-X", dns=None, created="2026-09-10T00:00:00"):
        return {"format_version": 2, "created_at": created,
                "power_plan": plan, "dns_interfaces": list(dns or [])}

    def _escrever(self, dados):
        os.makedirs(self.backup_dir, exist_ok=True)
        with open(self.estado_path, "w", encoding="utf-8") as f:
            json.dump(dados, f)

    def _ler_raw(self):
        with open(self.estado_path, "r", encoding="utf-8") as f:
            return f.read()

    def _ler(self):
        with open(self.estado_path, "r", encoding="utf-8") as f:
            return json.load(f)
class TestBaseline(SnapshotSandbox):
    def test_01_primeiro_salvar_cria_baseline(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(plan="PLAN-ORIGINAL")):
            self.assertTrue(seguranca.salvar_snapshot_sistema())
        self.assertTrue(os.path.isfile(self.estado_path))
        self.assertEqual(self._ler()["format_version"], 2)
        self.assertEqual(self._ler()["power_plan"], "PLAN-ORIGINAL")

    def test_02_segundo_salvar_nao_sobrescreve(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(plan="PLAN-A")):
            self.assertTrue(seguranca.salvar_snapshot_sistema())
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(plan="PLAN-B")) as cap:
            self.assertTrue(seguranca.salvar_snapshot_sistema())
            cap.assert_not_called()
        self.assertEqual(self._ler()["power_plan"], "PLAN-A")

    def test_03_terceiro_salvar_nao_sobrescreve(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(plan="PLAN-A")):
            seguranca.salvar_snapshot_sistema()
        for _ in range(2):
            with mock.patch.object(seguranca, "capturar_estado_sistema",
                                   return_value=self._captura_v2(plan="PLAN-C")):
                seguranca.salvar_snapshot_sistema()
        self.assertEqual(self._ler()["power_plan"], "PLAN-A")

    def test_04_timestamp_original_permanece(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(created="2020-01-01T00:00:00")):
            seguranca.salvar_snapshot_sistema()
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(created="2099-01-01T00:00:00")):
            seguranca.salvar_snapshot_sistema()
        self.assertEqual(self._ler()["created_at"], "2020-01-01T00:00:00")

    def test_05_power_plan_original_permanece(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(plan="GUID-ORIGINAL")):
            seguranca.salvar_snapshot_sistema()
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(plan="GUID-NOVO")):
            seguranca.salvar_snapshot_sistema()
        self.assertEqual(self._ler()["power_plan"], "GUID-ORIGINAL")

    def test_06_dns_original_permanece(self):
        original = [_iface("ETH", "static", ["10.0.0.1"])]
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(dns=original)):
            seguranca.salvar_snapshot_sistema()
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(dns=[_iface("ETH", "static", ["8.8.8.8"])])):
            seguranca.salvar_snapshot_sistema()
        self.assertEqual(self._ler()["dns_interfaces"], original)

    def test_07_snapshot_corrompido_nao_sobrescrito(self):
        os.makedirs(self.backup_dir, exist_ok=True)
        with open(self.estado_path, "w", encoding="utf-8") as f:
            f.write("{corrompido")
        before = self._ler_raw()
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2()) as cap:
            self.assertFalse(seguranca.salvar_snapshot_sistema())
            cap.assert_not_called()
        self.assertEqual(self._ler_raw(), before)

    def test_08_formato_desconhecido_nao_sobrescrito(self):
        self._escrever({"foo": "bar"})
        before = self._ler_raw()
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2()) as cap:
            self.assertFalse(seguranca.salvar_snapshot_sistema())
            cap.assert_not_called()
        self.assertEqual(self._ler_raw(), before)

    def test_09_escrita_nova_e_atomica(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2()):
            self.assertTrue(seguranca.salvar_snapshot_sistema())
        self.assertTrue(os.path.isfile(self.estado_path))
        self.assertFalse(os.path.exists(self.estado_path + ".tmp"))

    def test_10_concorrencia_nao_cria_duas_baselines(self):
        planos = iter(["PLAN-%d" % i for i in range(10)])
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               side_effect=lambda: self._captura_v2(plan=next(planos))):
            threads = [threading.Thread(target=seguranca.salvar_snapshot_sistema)
                       for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(self._ler()["power_plan"], "PLAN-0")
class TestPlan(SnapshotSandbox):
    def test_11_balanced_3_otimizacoes_restore_balanced(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(plan="BALANCED-GUID")):
            self.assertTrue(seguranca.salvar_snapshot_sistema())
        for _ in range(3):
            with mock.patch.object(seguranca, "capturar_estado_sistema",
                                   return_value=self._captura_v2(plan="HIGH-PERF")):
                self.assertTrue(seguranca.salvar_snapshot_sistema())
        with mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertEqual(seguranca.restaurar_snapshot_sistema(), seguranca.RESTAURACAO_SUCESSO)
        cmd = " ".join(str(x) for x in mex.call_args.args[0])
        self.assertIn("BALANCED-GUID", cmd)

    def test_12_outro_guid_restore_guid_original(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(plan="GUID-1234")):
            seguranca.salvar_snapshot_sistema()
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(plan="GUID-9999")):
            seguranca.salvar_snapshot_sistema()
        with mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            seguranca.restaurar_snapshot_sistema()
        self.assertIn("GUID-1234", " ".join(str(x) for x in mex.call_args.args[0]))

    def test_13_rollback_usa_estado_imediato_nao_baseline(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(plan="ORIGINAL")):
            seguranca.salvar_snapshot_sistema()
        estado_imediato = self._captura_v2(plan="PRE-TRANSACAO")
        rest = mock.MagicMock(return_value=True)
        t = seguranca.TransacaoSistema()

        def falha():
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            t.executar(falha, rollback=lambda: rest(estado_imediato, escopo="plano"))
        rest.assert_called_once_with(estado_imediato, escopo="plano")

    def test_14_rollback_plano_nao_toca_dns(self):
        estado = self._captura_v2(plan="PRE-TRANSACAO",
                                  dns=[_iface("ETH", "static", ["8.8.8.8"])])
        with mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex, \
             mock.patch.object(seguranca, "_resolver_index_por_guid") as res:
            self.assertEqual(seguranca.restaurar_estado_sistema(estado, escopo="plano"), seguranca.RESTAURACAO_SUCESSO)
        res.assert_not_called()
        cmd = " ".join(str(x) for x in mex.call_args.args[0])
        self.assertIn("powercfg", cmd)
        self.assertNotIn("DnsClientServerAddress", cmd)
class TestDns(SnapshotSandbox):
    def test_15_google_cloudflare_restore_preserva_original(self):
        original = [_iface("ETH", "static", ["10.0.0.1"])]
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(dns=original)):
            seguranca.salvar_snapshot_sistema()
        for dns in ([_iface("ETH", "static", ["8.8.8.8", "8.8.4.4"])],
                    [_iface("ETH", "static", ["1.1.1.1", "1.0.0.1"])]):
            with mock.patch.object(seguranca, "capturar_estado_sistema",
                                   return_value=self._captura_v2(dns=dns)):
                seguranca.salvar_snapshot_sistema()
        self.assertEqual(self._ler()["dns_interfaces"], original)

    def test_16_automatico_google_cloudflare_restore_automatico(self):
        original = [_iface("WIFI", "automatic", [])]
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(dns=original)):
            seguranca.salvar_snapshot_sistema()
        for _ in range(2):
            with mock.patch.object(seguranca, "capturar_estado_sistema",
                                   return_value=self._captura_v2(dns=[_iface("WIFI", "static", ["8.8.8.8"])])):
                seguranca.salvar_snapshot_sistema()
        self.assertEqual(self._ler()["dns_interfaces"], original)

    def test_17_estatico_google_automatico_restore_estatico(self):
        original = [_iface("ETH", "static", ["10.1.1.1", "10.1.1.2"])]
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(dns=original)):
            seguranca.salvar_snapshot_sistema()
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(dns=[_iface("ETH", "static", ["8.8.8.8"])])):
            seguranca.salvar_snapshot_sistema()
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(dns=[_iface("ETH", "automatic", [])])):
            seguranca.salvar_snapshot_sistema()
        self.assertEqual(self._ler()["dns_interfaces"], original)

    def test_18_ethernet_estatico_wifi_automatico_individualmente(self):
        estado = {"power_plan": None, "format_version": 2,
                  "dns_interfaces": [
                      _iface(G_ETH, "static", ["8.8.8.8", "8.8.4.4"], index=12),
                      _iface(G_WIFI, "automatic", [], index=7),
                  ]}
        with mock.patch.object(seguranca, "_resolver_index_por_guid", side_effect=[12, 7]), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertEqual(seguranca._restaurar_dns_estado(estado), seguranca.RESTAURACAO_SUCESSO)
        cmds = [" ".join(str(x) for x in c[0][0]) for c in mex.call_args_list]
        self.assertTrue(any("8.8.8.8" in c and "InterfaceIndex 12" in c for c in cmds))
        self.assertTrue(any("ResetServerAddresses" in c and "InterfaceIndex 7" in c for c in cmds))
        self.assertFalse(any("8.8.8.8" in c and "InterfaceIndex 7" in c for c in cmds))

    def test_19_ethernet_automatico_wifi_estatico(self):
        estado = {"power_plan": None, "format_version": 2,
                  "dns_interfaces": [
                      _iface(G_ETH, "automatic", [], index=12),
                      _iface(G_WIFI, "static", ["1.1.1.1", "1.0.0.1"], index=7),
                  ]}
        with mock.patch.object(seguranca, "_resolver_index_por_guid", side_effect=[12, 7]), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertEqual(seguranca._restaurar_dns_estado(estado), seguranca.RESTAURACAO_SUCESSO)
        cmds = [" ".join(str(x) for x in c[0][0]) for c in mex.call_args_list]
        self.assertTrue(any("ResetServerAddresses" in c and "InterfaceIndex 12" in c for c in cmds))
        self.assertTrue(any("1.1.1.1" in c and "InterfaceIndex 7" in c for c in cmds))

    def test_20_duas_interfaces_estaticas_diferentes(self):
        estado = {"power_plan": None, "format_version": 2,
                  "dns_interfaces": [
                      _iface(G_ETH1, "static", ["8.8.8.8", "8.8.4.4"], index=10),
                      _iface(G_ETH2, "static", ["1.1.1.1", "1.0.0.1"], index=11),
                  ]}
        with mock.patch.object(seguranca, "_resolver_index_por_guid", side_effect=[10, 11]), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertEqual(seguranca._restaurar_dns_estado(estado), seguranca.RESTAURACAO_SUCESSO)
        cmds = [" ".join(str(x) for x in c[0][0]) for c in mex.call_args_list]
        self.assertTrue(any("8.8.8.8" in c and "InterfaceIndex 10" in c for c in cmds))
        self.assertTrue(any("1.1.1.1" in c and "InterfaceIndex 11" in c for c in cmds))
        self.assertFalse(any("8.8.8.8" in c and "InterfaceIndex 11" in c for c in cmds))
    def test_21_novo_adaptador_nao_tocado(self):
        estado = {"power_plan": None, "format_version": 2,
                  "dns_interfaces": [_iface(G_ETH, "static", ["8.8.8.8"], index=12)]}
        with mock.patch.object(seguranca, "_resolver_index_por_guid", return_value=12), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertEqual(seguranca._restaurar_dns_estado(estado), seguranca.RESTAURACAO_SUCESSO)
        self.assertEqual(mex.call_count, 1)

    def test_22_adaptador_ausente_nao_transfere(self):
        estado = {"power_plan": None, "format_version": 2,
                  "dns_interfaces": [_iface(G_AUSENTE, "static", ["8.8.8.8"], index=99)]}
        with mock.patch.object(seguranca, "_resolver_index_por_guid", return_value=None), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertEqual(seguranca._restaurar_dns_estado(estado), seguranca.RESTAURACAO_FALHA)
        mex.assert_not_called()

    def test_23_identidade_por_guid_nao_apenas_index(self):
        interface = _iface(G_TESTE, "static", ["8.8.8.8"], index=999)
        with mock.patch.object(seguranca, "_resolver_index_por_guid", return_value=42) as res, \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertTrue(seguranca._aplicar_dns_interface(interface))
        res.assert_called_once_with(G_TESTE)
        cmd = " ".join(str(x) for x in mex.call_args.args[0])
        self.assertIn("InterfaceIndex 42", cmd)

    def test_24_dns_invalido_rejeitado_com_seguranca(self):
        self._escrever({"format_version": 2, "power_plan": None,
                        "dns_interfaces": [_iface(G_ETH, "static", ["nao-e-ip"])]})
        dados, erro = seguranca._carregar_estado_snapshot()
        self.assertIsNone(dados)
        self.assertIn("DNS inválido", erro)

    def test_25_adaptadores_virtuais_nao_entram(self):
        with mock.patch.object(seguranca, "_executar_powershell_json", return_value=[]) as mex:
            seguranca._obter_adaptadores_ativos_detalhados()
        self.assertIn(seguranca.filtro_adaptadores_ativos_ps(), mex.call_args.args[0])


class TestDistincaoDns(SnapshotSandbox):
    def _fake_winreg(self, name_server):
        class FakeKey:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class FakeWinreg:
            HKEY_LOCAL_MACHINE = 1
            KEY_READ = 2

            def OpenKey(self, hive, path, res, access):
                return FakeKey()

            def QueryValueEx(self, key, nome):
                if nome == "NameServer" and name_server is not None:
                    return (name_server, 1)
                raise FileNotFoundError()

        return FakeWinreg()

    def test_name_server_presente_e_estatico(self):
        with mock.patch.object(seguranca, "winreg", self._fake_winreg("8.8.8.8, 8.8.4.4")):
            modo, servidores = seguranca._ler_dns_registro_interface("GUID")
        self.assertEqual(modo, "static")
        self.assertEqual(servidores, ["8.8.8.8", "8.8.4.4"])

    def test_sem_name_server_automatico(self):
        with mock.patch.object(seguranca, "winreg", self._fake_winreg(None)):
            modo, servidores = seguranca._ler_dns_registro_interface("GUID")
        self.assertEqual(modo, "automatic")
        self.assertEqual(servidores, [])

    def test_ipv6_ignorado_no_registro(self):
        with mock.patch.object(seguranca, "winreg",
                               self._fake_winreg("8.8.8.8, 2001:4860:4860::8888")):
            modo, servidores = seguranca._ler_dns_registro_interface("GUID")
        self.assertEqual(modo, "static")
        self.assertEqual(servidores, ["8.8.8.8"])
class TestLifecycle(SnapshotSandbox):
    def test_26_restore_bem_sucedido_permite_finalizar(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2()):
            seguranca.salvar_snapshot_sistema()
        self.assertTrue(os.path.isfile(self.estado_path))
        self.assertTrue(seguranca.finalizar_snapshot_sistema())
        self.assertFalse(os.path.exists(self.estado_path))

    def test_27_apos_finalizar_nova_baseline(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(plan="OLD")):
            seguranca.salvar_snapshot_sistema()
        seguranca.finalizar_snapshot_sistema()
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(plan="NEW")):
            self.assertTrue(seguranca.salvar_snapshot_sistema())
        self.assertEqual(self._ler()["power_plan"], "NEW")

    def test_28_restore_parcial_mantem_baseline(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2()):
            seguranca.salvar_snapshot_sistema()
        os.makedirs(seguranca.PASTA_BACKUP_REG, exist_ok=True)
        with open(os.path.join(seguranca.PASTA_BACKUP_REG, "backup.reg"), "w") as f:
            f.write("Windows Registry Editor Version 5.00\n")
        with mock.patch.object(seguranca, "restaurar_snapshot_sistema", return_value=False), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True), \
             mock.patch.object(seguranca, "finalizar_snapshot_sistema") as fin:
            ok, _ = seguranca.restaurar_registro_sistema()
        self.assertFalse(ok)
        fin.assert_not_called()
        self.assertTrue(os.path.isfile(self.estado_path))

    def test_29_falha_plano_mantem_baseline(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(plan="GUID")):
            seguranca.salvar_snapshot_sistema()
        with mock.patch.object(seguranca, "executar_comando_seguro", return_value=False):
            self.assertEqual(seguranca.restaurar_snapshot_sistema(), seguranca.RESTAURACAO_PARCIAL)
        self.assertTrue(os.path.isfile(self.estado_path))

    def test_30_falha_dns_mantem_baseline(self):
        estado = self._captura_v2(plan="GUID", dns=[_iface(G_ETH, "static", ["8.8.8.8"])])
        with mock.patch.object(seguranca, "capturar_estado_sistema", return_value=estado):
            seguranca.salvar_snapshot_sistema()
        with mock.patch.object(seguranca, "executar_comando_seguro", side_effect=[True, False]), \
             mock.patch.object(seguranca, "_resolver_index_por_guid", return_value=12):
            self.assertEqual(seguranca.restaurar_snapshot_sistema(), seguranca.RESTAURACAO_PARCIAL)
        self.assertTrue(os.path.isfile(self.estado_path))

    def test_31_snapshot_nao_apagado_prematuramente(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2()):
            seguranca.salvar_snapshot_sistema()
        with mock.patch.object(seguranca, "executar_comando_seguro", return_value=True):
            seguranca.restaurar_snapshot_sistema()
        self.assertTrue(os.path.isfile(self.estado_path))


class TestLegacy(SnapshotSandbox):
    def test_32_formato_v1_reconhecido(self):
        self._escrever({"power_plan": "GUID-LEGADO", "dns": ["1.1.1.1"], "timestamp": 123})
        dados, erro = seguranca._carregar_estado_snapshot()
        self.assertIsNone(erro)
        self.assertEqual(dados["power_plan"], "GUID-LEGADO")

    def test_33_v1_nao_sobrescrito(self):
        self._escrever({"power_plan": "GUID-LEGADO", "dns": ["1.1.1.1"], "timestamp": 123})
        before = self._ler_raw()
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2()) as cap:
            self.assertTrue(seguranca.salvar_snapshot_sistema())
            cap.assert_not_called()
        self.assertEqual(self._ler_raw(), before)

    def test_34_v1_um_adaptador_aplica_dns_nele(self):
        self._escrever({"power_plan": None, "dns": ["8.8.8.8", "1.1.1.1"], "timestamp": 123})
        ad = [{"interface_guid": G_ETH, "interface_alias": "Ethernet", "interface_index": 12}]
        with mock.patch.object(seguranca, "_obter_adaptadores_ativos_detalhados", return_value=ad), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertEqual(seguranca.restaurar_snapshot_sistema(), seguranca.RESTAURACAO_SUCESSO)
        cmd = " ".join(str(x) for x in mex.call_args.args[0])
        self.assertIn("InterfaceIndex 12", cmd)
        self.assertIn("8.8.8.8", cmd)
        self.assertIn("1.1.1.1", cmd)
        self.assertNotIn(seguranca.filtro_adaptadores_ativos_ps(), cmd)

    def test_35_v1_multiplos_adaptadores_nao_aplica(self):
        self._escrever({"power_plan": None, "dns": ["8.8.8.8"], "timestamp": 123})
        ads = [
            {"interface_guid": G_ETH, "interface_alias": "Ethernet", "interface_index": 12},
            {"interface_guid": G_WIFI, "interface_alias": "Wi-Fi", "interface_index": 7},
        ]
        with mock.patch.object(seguranca, "_obter_adaptadores_ativos_detalhados", return_value=ads), \
             mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertEqual(seguranca.restaurar_snapshot_sistema(), seguranca.RESTAURACAO_PARCIAL)
        mex.assert_not_called()

    def test_36_novo_snapshot_usa_format_version(self):
        with mock.patch.object(seguranca, "obter_plano_energia_atual", return_value="GUID"), \
             mock.patch.object(seguranca, "obter_dns_atual", return_value=[]):
            estado = seguranca.capturar_estado_sistema()
        self.assertEqual(estado["format_version"], 2)
        self.assertIn("dns_interfaces", estado)
class TestIntegration(SnapshotSandbox):
    def test_37_alterar_dns_preserva_baseline_antes_mutacao(self):
        ordem = []

        def snap():
            ordem.append("snap")
            return True

        def mut(*a):
            ordem.append("mut")
            return True

        with mock.patch.object(sistema, "salvar_snapshot_sistema", side_effect=snap), \
             mock.patch.object(sistema, "executar_comando_seguro", side_effect=mut):
            self.assertTrue(sistema.alterar_dns("Google"))
        self.assertEqual(ordem, ["snap", "mut"])

    def test_38_otimizacao_global_preserva_baseline(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(plan="ORIGINAL")):
            seguranca.salvar_snapshot_sistema()
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(plan="HIGH-PERF")):
            seguranca.salvar_snapshot_sistema()
        self.assertEqual(self._ler()["power_plan"], "ORIGINAL")

    def test_39_repeticao_otimizacao_nao_substitui_baseline(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(plan="ORIGINAL")):
            seguranca.salvar_snapshot_sistema()
        for i in range(3):
            with mock.patch.object(seguranca, "capturar_estado_sistema",
                                   return_value=self._captura_v2(plan="HP-%d" % i)):
                seguranca.salvar_snapshot_sistema()
        self.assertEqual(self._ler()["power_plan"], "ORIGINAL")

    def test_40_restaurar_sistema_usa_baseline_persistente(self):
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2(plan="ORIGINAL")):
            seguranca.salvar_snapshot_sistema()
        with mock.patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
            self.assertEqual(seguranca.restaurar_snapshot_sistema(), seguranca.RESTAURACAO_SUCESSO)
        self.assertIn("ORIGINAL", " ".join(str(x) for x in mex.call_args.args[0]))

    def test_41_transacao_usa_estado_imediato_rollback(self):
        estado_imediato = self._captura_v2(plan="PRE")
        rest = mock.MagicMock(return_value=True)
        t = seguranca.TransacaoSistema()

        def falha():
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            t.executar(falha, rollback=lambda: rest(estado_imediato, escopo="plano"))
        rest.assert_called_once_with(estado_imediato, escopo="plano")


def _sha256_file(caminho):
    with open(caminho, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class TestIsolamento(SnapshotSandbox):
    def test_42_nenhum_comando_real_executado(self):
        with mock.patch.object(seguranca, "obter_plano_energia_atual", return_value="GUID"), \
             mock.patch.object(seguranca, "obter_dns_atual", return_value=[]):
            estado = seguranca.capturar_estado_sistema()
        self.assertEqual(estado["format_version"], 2)

    def test_43_config_json_real_byte_identico(self):
        import config
        caminho = config.ARQUIVO_CONFIG
        if not os.path.isfile(caminho):
            self.skipTest("config.json real ausente")
        before = _sha256_file(caminho)
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2()):
            seguranca.salvar_snapshot_sistema()
        self.assertEqual(_sha256_file(caminho), before)

    def test_44_estado_sistema_real_byte_identico(self):
        import config
        caminho = config.ARQUIVO_ESTADO
        exists = os.path.isfile(caminho)
        before = _sha256_file(caminho) if exists else None
        with mock.patch.object(seguranca, "capturar_estado_sistema",
                               return_value=self._captura_v2()):
            seguranca.salvar_snapshot_sistema()
        after = _sha256_file(caminho) if os.path.isfile(caminho) else None
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main(verbosity=2)






