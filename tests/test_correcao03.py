# -*- coding: utf-8 -*-
"""
CORREÇÃO CONTROLADA 03 — Testes não destrutivos da aba Sistema.

Cobre: mensagens honestas ([ERRO] em falha), escopo DNS/TCP (só adaptadores
físicos ativos), snapshot/restore com o MESMO escopo, QoS idempotente com
falha de PowerShell reportada, e threading (fora da GUI thread).

NÃO executa: DNS real, Registry real, QoS real, PowerShell real, Windows real.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import seguranca  # noqa: E402
import sistema  # noqa: E402


# ============================================================
# FAKES
# ============================================================
class FakeSignal:
    def __init__(self):
        self.recebidos = []

    def emit(self, *args):
        self.recebidos.append(args)


class FakeSinais:
    def __init__(self):
        self.log_signal = FakeSignal()
        self.rede_alterada_signal = FakeSignal()

    def textos(self):
        return [r[0] for r in self.log_signal.recebidos if r and isinstance(r[0], str)]

    def tem_ok(self):
        return any("[OK]" in t for t in self.textos())

    def tem_erro(self):
        return any("[ERRO]" in t for t in self.textos())


class FakeKey:
    def __init__(self, name):
        self.name = name

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeWinreg:
    """winreg falso — nunca toca no Registry real."""

    HKEY_LOCAL_MACHINE = -2147483648
    HKEY_CURRENT_USER = -2147483647
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_DWORD = 4

    def __init__(self, subkey_names):
        self._subkeys = list(subkey_names)
        self.valores = {}  # (caminho, nome) -> valor

    def QueryInfoKey(self, key):
        return (len(self._subkeys), 0, 0)

    def EnumKey(self, key, i):
        return self._subkeys[i]

    def OpenKey(self, hive, path, res, access):
        return FakeKey(path)

    def SetValueEx(self, key, nome, res, tipo, valor):
        self.valores[(key.name, nome)] = valor


def janela_teste():
    """Instância de AikaOptimizerPro SEM __init__ (sem UI real)."""
    import main
    win = main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
    win.sinais = FakeSinais()
    win._tarefas_submetidas = []

    def fake_executar_em_background(f, *a, **k):
        win._tarefas_submetidas.append(f)
        return True

    win.executar_em_background = fake_executar_em_background
    return win


def _cmd(call_arg):
    """Converte argumento de comando (lista ou str) em texto para asserções."""
    if isinstance(call_arg, (list, tuple)):
        return " ".join(str(x) for x in call_arg)
    return str(call_arg)


def filtro_fragmento():
    """Fragmento do pipeline compartilhado de adaptadores físicos ativos."""
    return seguranca.filtro_adaptadores_ativos_ps()


FISICO = "AAAA1111-2222-3333-4444-555555555555"
VIRTUAL = "BBBB2222-3333-4444-5555-666666666666"

_INTERFACES_PATH = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"


# ============================================================
# 1) MENSAGENS — FALHA GERA [ERRO], SUCESSO GERA [OK]
# ============================================================
class TestMensagensHonestas(unittest.TestCase):
    def _rodar(self, win):
        for t in win._tarefas_submetidas:
            t()

    def test_falha_dns_gera_erro(self):
        win = janela_teste()
        with patch("main.opt") as opt_falso:
            opt_falso.alterar_dns.return_value = False
            win.acao_dns("Google")
            self._rodar(win)
            self.assertTrue(win.sinais.tem_erro())
            self.assertFalse(win.sinais.tem_ok())

    def test_sucesso_dns_gera_ok(self):
        win = janela_teste()
        with patch("main.opt") as opt_falso:
            opt_falso.alterar_dns.return_value = True
            win.acao_dns("Google")
            self._rodar(win)
            self.assertTrue(win.sinais.tem_ok())
            self.assertFalse(win.sinais.tem_erro())

    def test_excecao_dns_gera_erro(self):
        win = janela_teste()
        with patch("main.opt") as opt_falso:
            opt_falso.alterar_dns.side_effect = RuntimeError("boom")
            win.acao_dns("Google")
            self._rodar(win)
            self.assertTrue(win.sinais.tem_erro())
            self.assertTrue(any("boom" in t for t in win.sinais.textos()))

    def test_falha_gamebar_gera_erro(self):
        win = janela_teste()
        with patch("main.opt") as opt_falso:
            opt_falso.desativar_game_bar.return_value = False
            win.acao_gamebar()
            self._rodar(win)
            self.assertTrue(win.sinais.tem_erro())
            self.assertFalse(win.sinais.tem_ok())

    def test_falha_tcp_gera_erro(self):
        win = janela_teste()
        with patch("main.opt") as opt_falso:
            opt_falso.otimizar_tcp_nodelay.return_value = False
            win.acao_tcp_nodelay()
            self._rodar(win)
            self.assertTrue(win.sinais.tem_erro())
            self.assertFalse(win.sinais.tem_ok())

    def test_excecao_tcp_gera_erro(self):
        win = janela_teste()
        with patch("main.opt") as opt_falso:
            opt_falso.otimizar_tcp_nodelay.side_effect = RuntimeError("backup falhou")
            win.acao_tcp_nodelay()
            self._rodar(win)
            self.assertTrue(win.sinais.tem_erro())
            self.assertTrue(any("backup falhou" in t for t in win.sinais.textos()))



# ============================================================
# 2) ESCOPO DNS — SISTEMA + SNAPSHOT (SEGURANCA)
# ============================================================
class TestEscopoDns(unittest.TestCase):
    def test_filtro_compartilhado(self):
        # Mesmo objeto importado por sistema.py — escopo idêntico nos 3 lados.
        self.assertIs(sistema.filtro_adaptadores_ativos_ps,
                      seguranca.filtro_adaptadores_ativos_ps)

    def test_filtro_exclui_virtual_vpn_desconectado(self):
        f = filtro_fragmento()
        self.assertIn("Status -eq 'Up'", f)
        for token in ("VMware", "Hyper-V", "TAP", "vEthernet", "Loopback",
                      "WireGuard", "OpenVPN"):
            self.assertIn(token, f)

    def _alterar(self, snapshot_ok=True):
        with patch.object(sistema, "salvar_snapshot_sistema", return_value=snapshot_ok), \
             patch.object(sistema, "executar_comando_seguro", return_value=True) as mex:
            ok = sistema.alterar_dns("Google")
        return ok, mex

    def test_dns_google_cmd_correto(self):
        ok, mex = self._alterar()
        self.assertTrue(ok)
        cmd = _cmd(mex.call_args.args[0])
        self.assertIn("Set-DnsClientServerAddress", cmd)
        self.assertIn("8.8.8.8", cmd)
        self.assertIn(filtro_fragmento(), cmd)  # só adaptadores físicos ativos

    def test_dns_padrao_reseta(self):
        with patch.object(sistema, "salvar_snapshot_sistema", return_value=True), \
             patch.object(sistema, "executar_comando_seguro", return_value=True) as mex:
            self.assertTrue(sistema.alterar_dns("Padrao"))
            self.assertIn("ResetServerAddresses", _cmd(mex.call_args.args[0]))

    def test_snapshot_falho_nao_altera_dns(self):
        ok, mex = self._alterar(snapshot_ok=False)
        self.assertFalse(ok)
        mex.assert_not_called()

    def test_gamebar_backup_falho_retorna_false(self):
        with patch.object(sistema, "fazer_backup_registro", return_value=False):
            self.assertFalse(sistema.desativar_game_bar())



# ============================================================
# 3) SNAPSHOT DNS — MESMO ESCOPO DA ALTERAÇÃO
# ============================================================
class TestSnapshotMesmoEscopo(unittest.TestCase):
    def test_obter_dns_retorna_por_adaptador(self):
        ad = [{"interface_guid": "AAAA1111-2222-3333-4444-555555555555",
               "interface_alias": "Ethernet", "interface_index": 12}]
        with patch.object(seguranca, "_obter_adaptadores_ativos_detalhados", return_value=ad), \
             patch.object(seguranca, "_ler_dns_registro_interface", return_value=("static", ["8.8.8.8", "1.1.1.1"])):
            interfaces = seguranca.obter_dns_atual()
        self.assertEqual(interfaces, [{
            "interface_guid": "AAAA1111-2222-3333-4444-555555555555",
            "interface_alias": "Ethernet",
            "interface_index": 12,
            "mode": "static",
            "servers_ipv4": ["8.8.8.8", "1.1.1.1"],
        }])

    def test_obter_adaptadores_detalhados_usa_filtro(self):
        with patch.object(seguranca, "_executar_powershell_json", return_value=[]) as mex:
            seguranca._obter_adaptadores_ativos_detalhados()
        self.assertIn(filtro_fragmento(), mex.call_args.args[0])

    def _estado(self, td, dns):
        caminho = os.path.join(td, "estado.json")
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump({"power_plan": None, "dns": dns}, f)
        return caminho

    def test_restaurar_v1_um_adaptador_aplica_dns(self):
        with tempfile.TemporaryDirectory() as td:
            ad = [{"interface_guid": "AAAA1111-2222-3333-4444-555555555555",
                   "interface_alias": "Ethernet", "interface_index": 12}]
            with patch.object(seguranca, "ARQUIVO_ESTADO", self._estado(td, ["8.8.8.8", "1.1.1.1"])), \
                 patch.object(seguranca, "_obter_adaptadores_ativos_detalhados", return_value=ad), \
                 patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
                self.assertEqual(seguranca.restaurar_snapshot_sistema(), seguranca.RESTAURACAO_SUCESSO)
                cmd = _cmd(mex.call_args.args[0])
                self.assertIn("InterfaceIndex 12", cmd)
                self.assertIn("8.8.8.8", cmd)
                self.assertIn("1.1.1.1", cmd)

    def test_restaurar_ip_invalido_ignorado(self):
        with tempfile.TemporaryDirectory() as td:
            ad = [{"interface_guid": "AAAA1111-2222-3333-4444-555555555555",
                   "interface_alias": "Ethernet", "interface_index": 12}]
            with patch.object(seguranca, "ARQUIVO_ESTADO", self._estado(td, ["nao-e-ip", "1.1.1.1"])), \
                 patch.object(seguranca, "_obter_adaptadores_ativos_detalhados", return_value=ad), \
                 patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
                self.assertEqual(seguranca.restaurar_snapshot_sistema(), seguranca.RESTAURACAO_SUCESSO)
                cmd = _cmd(mex.call_args.args[0])
                self.assertIn("1.1.1.1", cmd)
                self.assertNotIn("nao-e-ip", cmd)

    def test_restaurar_v1_dns_vazio_conservador(self):
        with tempfile.TemporaryDirectory() as td:
            ad = [{"interface_guid": "AAAA1111-2222-3333-4444-555555555555",
                   "interface_alias": "Ethernet", "interface_index": 12}]
            with patch.object(seguranca, "ARQUIVO_ESTADO", self._estado(td, None)), \
                 patch.object(seguranca, "_obter_adaptadores_ativos_detalhados", return_value=ad), \
                 patch.object(seguranca, "executar_comando_seguro", return_value=True) as mex:
                self.assertEqual(seguranca.restaurar_snapshot_sistema(), seguranca.RESTAURACAO_PARCIAL)
                mex.assert_not_called()



# ============================================================
# 4) TCP NODELAY — ESCOPO
# ============================================================
class TestEscopoTcp(unittest.TestCase):
    @patch.object(sistema, "fazer_backup_registro", return_value=True)
    def test_aplica_somente_na_interface_ativa(self, mb):
        fake = FakeWinreg(["{" + FISICO + "}", "{" + VIRTUAL + "}"])
        with patch.object(sistema, "winreg", fake), \
             patch.object(sistema, "_obter_guids_adaptadores_ativos",
                          return_value={FISICO.upper()}):
            self.assertTrue(sistema.otimizar_tcp_nodelay())
        chave_fisica = _INTERFACES_PATH + "\\{" + FISICO + "}"
        self.assertEqual(fake.valores[(chave_fisica, "TcpAckFrequency")], 1)
        self.assertEqual(fake.valores[(chave_fisica, "TCPNoDelay")], 1)
        self.assertEqual(len(fake.valores), 2)  # interface virtual NÃO tocada

    @patch.object(sistema, "fazer_backup_registro", return_value=False)
    def test_backup_falho_levanta_erro(self, mb):
        # Handler (acao_tcp_nodelay) captura e emite [ERRO] — testado acima.
        fake = FakeWinreg(["{" + FISICO + "}"])
        with patch.object(sistema, "winreg", fake), \
             patch.object(sistema, "_obter_guids_adaptadores_ativos",
                          return_value={FISICO.upper()}):
            with self.assertRaises(RuntimeError):
                sistema.otimizar_tcp_nodelay()
        self.assertEqual(fake.valores, {})

    @patch.object(sistema, "fazer_backup_registro", return_value=True)
    def test_sem_adaptador_ativo_nada_alterado(self, mb):
        fake = FakeWinreg(["{" + VIRTUAL + "}"])
        with patch.object(sistema, "winreg", fake), \
             patch.object(sistema, "_obter_guids_adaptadores_ativos", return_value=set()):
            self.assertFalse(sistema.otimizar_tcp_nodelay())
        self.assertEqual(fake.valores, {})
        mb.assert_not_called()  # nem backup é criado quando nada será alterado

    @patch.object(sistema, "fazer_backup_registro", return_value=True)
    def test_normalizacao_guid(self, mb):
        # GUID com chaves/minúsculas da Registry casa com GUID normalizado do PS.
        fake = FakeWinreg(["{" + FISICO.lower() + "}"])
        with patch.object(sistema, "winreg", fake), \
             patch.object(sistema, "_obter_guids_adaptadores_ativos",
                          return_value={FISICO.upper()}):
            self.assertTrue(sistema.otimizar_tcp_nodelay())
        self.assertEqual(len(fake.valores), 2)


# === CONTINUA5 ===
