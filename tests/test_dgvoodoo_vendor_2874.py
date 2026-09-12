# -*- coding: utf-8 -*-
"""Testes da migração do vendor dgVoodoo2 2.87.3 -> 2.87.4 (ETAPA 10).

Cobre identidade/hash/arquitetura do template 2.87.4, Version do conf,
geração por perfil a partir do template OFICIAL 2.87.4, watermark=false sem
duplicidade, template intacto, ativação/restauração/MODIFICADO_EXTERNAMENTE
em tmp_path e lógica AUTO. NENHUM teste toca cliente real.
"""
import hashlib
import os
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import dgvoodoo_service as svc  # noqa: E402

HASH_DLL = "db1c445f7bcf699df1e175e974c779bdc7e19a468680a44884b1ab7078888d04"
HASH_CONF = "3c7da2fac3eaad369df468e80c9ba9c4db632c419799b32bbc31279d10985801"
VERSION_CONF_ESPERADA = "0x287"
MACHINE_X86 = 0x14C
PRODUCT_VERSION_DLL = "2.8.7.4"

AA = {svc.PERFIL_PERFORMANCE: "appdriven", svc.PERFIL_BALANCED: "2x", svc.PERFIL_QUALITY: "4x"}
FILTRO = {svc.PERFIL_PERFORMANCE: "trilinear", svc.PERFIL_BALANCED: "16", svc.PERFIL_QUALITY: "16"}


def _h(data):
    d = hashlib.sha256()
    d.update(data)
    return d.hexdigest()


def _h_file(path):
    d = hashlib.sha256()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            d.update(bloco)
    return d.hexdigest()


def _machine_pe(path):
    """Arquitetura PE sem executar o binário."""
    with open(path, "rb") as f:
        dados = f.read()
    assert dados[:2] == b"MZ"
    (e_lfanew,) = struct.unpack_from("<I", dados, 0x3C)
    assert dados[e_lfanew:e_lfanew + 4] == b"PE\x00\x00"
    (machine,) = struct.unpack_from("<H", dados, e_lfanew + 4)
    return machine


def _versao_dll(path):
    """ProductVersion/FileDescription do recurso VS_VERSION_INFO."""
    import ctypes
    from ctypes import wintypes

    out = {}
    size = ctypes.windll.version.GetFileVersionInfoSizeW(path, None)
    if not size:
        return out
    buf = ctypes.create_string_buffer(size)
    if not ctypes.windll.version.GetFileVersionInfoW(path, 0, size, buf):
        return out
    length = wintypes.UINT()
    ptr = ctypes.c_void_p()
    if ctypes.windll.version.VerQueryValueW(buf, "\\VarFileInfo\\Translation",
                                            ctypes.byref(ptr), ctypes.byref(length)):
        raw = ctypes.string_at(ptr, length.value)
        lang = int.from_bytes(raw[0:2], "little")
        codepage = int.from_bytes(raw[2:4], "little")
        for campo in ("ProductVersion", "FileDescription"):
            sub = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\{campo}"
            p2 = ctypes.c_void_p()
            l2 = wintypes.UINT()
            if ctypes.windll.version.VerQueryValueW(buf, sub, ctypes.byref(p2), ctypes.byref(l2)):
                out[campo] = ctypes.wstring_at(p2, l2.value).rstrip("\x00")
    return out


def _ler_chave_texto(texto, secao, chave):
    """Lê chave/valor de texto de conf (secao None = topo/fora de seção)."""
    secao_atual = None
    for ln in texto.splitlines():
        t = ln.strip()
        if not t or t.startswith(";"):
            continue
        if t.startswith("[") and t.endswith("]"):
            secao_atual = t
            continue
        if secao_atual == secao and "=" in t and t.split("=", 1)[0].strip() == chave:
            return t.split("=", 1)[1].strip()
    return None


def _ocorrencias_chave(texto, chave):
    n = 0
    for ln in texto.splitlines():
        t = ln.strip()
        if not t or t.startswith(";") or "=" not in t:
            continue
        if t.split("=", 1)[0].strip() == chave:
            n += 1
    return n


def _version_fora_secao(texto):
    for ln in texto.splitlines():
        t = ln.strip()
        if not t or t.startswith(";") or t.startswith("["):
            continue
        if "=" in t and t.split("=", 1)[0].strip() == "Version":
            return t.split("=", 1)[1].strip()
    return None


class BaseVendorTest(unittest.TestCase):
    """Base: cliente temporário + config mockada (nunca cliente real)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="aika_vendor2874_")
        self.cli = self._tmp.name
        self._patches = []
        p1 = mock.patch.object(
            config, "obter_pasta_jogo_atual", create=True,
            side_effect=lambda exigir_existente=True: self.cli,
        )
        p2 = mock.patch.object(
            config, "obter_pasta_backup_cliente", create=True,
            side_effect=lambda p, criar=False: os.path.join(self.cli, "bk"),
        )
        p3 = mock.patch.object(
            config, "caminho_seguro", create=True,
            side_effect=lambda b, a, *x, **y: True,
        )
        p4 = mock.patch.object(config, "jogo_esta_aberto", create=True, return_value=False)
        for p in (p1, p2, p3, p4):
            p.start()
            self._patches.append(p)

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def caminho(self, *nomes):
        return os.path.join(self.cli, *nomes)

    def escrever(self, nome, dados):
        with open(self.caminho(nome), "wb") as f:
            f.write(dados)

    def ler(self, nome):
        with open(self.caminho(nome), "rb") as f:
            return f.read()

    def ler_chave(self, nome, secao, chave):
        return _ler_chave_texto(self.ler(nome).decode("utf-8-sig"), secao, chave)

    def existe_arquivo(self, nome):
        return os.path.isfile(self.caminho(nome))

    def ativar_limpo(self):
        r = svc.ativar_dgvoodoo(self.cli)
        self.assertTrue(r.ok, r.mensagem)
        return r


# --- Identidade do template 2.87.4 ----------------------------------------
class TestTemplateIdentidade2874(unittest.TestCase):
    """1-5. DLL 2.87.4, x86, hashes e Version do conf."""

    def test_template_dll_eh_2874(self):
        info = _versao_dll(svc.resolver_template_d3d9())
        self.assertEqual(info.get("ProductVersion"), PRODUCT_VERSION_DLL)
        self.assertIn("2.87.4", info.get("FileDescription", ""))

    def test_template_dll_eh_x86(self):
        self.assertEqual(_machine_pe(svc.resolver_template_d3d9()), MACHINE_X86)

    def test_hash_dll_correto(self):
        self.assertEqual(_h_file(svc.resolver_template_d3d9()), HASH_DLL)

    def test_hash_conf_correto(self):
        self.assertEqual(_h_file(svc.resolver_template_conf()), HASH_CONF)

    def test_version_conf_correta(self):
        with open(svc.resolver_template_conf(), "r", encoding="utf-8-sig") as f:
            texto = f.read()
        self.assertEqual(_ocorrencias_chave(texto, "Version"), 1)
        self.assertEqual(_version_fora_secao(texto), VERSION_CONF_ESPERADA)


# --- Geração por perfil a partir do template OFICIAL 2.87.4 ----------------
class TestGeracaoPerfis2874(BaseVendorTest):
    """6-8 e 17. Geração determinística (performance/balanced/quality)."""

    def _gerar_e_checar(self, perfil):
        antes_conf = _h_file(svc.resolver_template_conf())
        antes_dll = _h_file(svc.resolver_template_d3d9())
        dados = svc._gerar_conf_perfil(perfil)
        self.assertEqual(_h_file(svc.resolver_template_conf()), antes_conf,
                         "Template conf alterado pela geração")
        self.assertEqual(_h_file(svc.resolver_template_d3d9()), antes_dll,
                         "Template DLL alterado pela geração")
        texto = dados.decode("utf-8-sig")
        self.assertTrue(len(dados) >= 3 and dados[:3] != b"\xef\xbb\xbf",
                        "conf gerado nao pode iniciar com BOM UTF-8 (dgVoodoo ignora)")
        self.assertEqual(dados[0:1], b";", "conf deve iniciar com o cabecalho ; (sem BOM)")
        self.assertEqual(_ler_chave_texto(texto, "[General]", "OutputAPI"), "d3d11_fl11_0")
        self.assertEqual(_ler_chave_texto(texto, "[General]", "Adapters"), "1")
        self.assertEqual(_ler_chave_texto(texto, "[DirectX]", "VideoCard"), "internal3D")
        self.assertEqual(_ler_chave_texto(texto, "[DirectX]", "dgVoodooWatermark"), "false")
        self.assertEqual(_ler_chave_texto(texto, "[DirectX]", "Antialiasing"), AA[perfil])
        self.assertEqual(_ler_chave_texto(texto, "[DirectX]", "Filtering"), FILTRO[perfil])
        return dados

    def test_geracao_performance(self):
        self._gerar_e_checar(svc.PERFIL_PERFORMANCE)

    def test_geracao_balanced(self):
        self._gerar_e_checar(svc.PERFIL_BALANCED)

    def test_geracao_quality(self):
        self._gerar_e_checar(svc.PERFIL_QUALITY)

    def test_template_2874_intacto_apos_geracoes(self):
        hc = _h_file(svc.resolver_template_conf())
        hd = _h_file(svc.resolver_template_d3d9())
        for perfil in (svc.PERFIL_PERFORMANCE, svc.PERFIL_BALANCED, svc.PERFIL_QUALITY):
            svc._gerar_conf_perfil(perfil)
        self.assertEqual(_h_file(svc.resolver_template_conf()), hc)
        self.assertEqual(_h_file(svc.resolver_template_d3d9()), hd)


# --- Watermark ------------------------------------------------------------------
class TestWatermarkSempreFalse(BaseVendorTest):
    """12-16. dgVoodooWatermark=false em todo fluxo, sem duplicidade."""

    def _checar_sem_duplicidade(self):
        texto = self.ler(svc.DGVOODOO_CONF).decode("utf-8-sig")
        self.assertEqual(_ocorrencias_chave(texto, "dgVoodooWatermark"), 1,
                         "dgVoodooWatermark deve aparecer uma única vez")
        self.assertEqual(_ler_chave_texto(texto, "[DirectX]", "dgVoodooWatermark"), "false")

    def test_watermark_false_performance(self):
        self.ativar_limpo()
        self.assertTrue(svc.aplicar_perfil(svc.PERFIL_PERFORMANCE, self.cli).ok)
        self._checar_sem_duplicidade()

    def test_watermark_false_balanced(self):
        self.ativar_limpo()
        self.assertTrue(svc.aplicar_perfil(svc.PERFIL_BALANCED, self.cli).ok)
        self._checar_sem_duplicidade()

    def test_watermark_false_quality(self):
        self.ativar_limpo()
        self.assertTrue(svc.aplicar_perfil(svc.PERFIL_QUALITY, self.cli).ok)
        self._checar_sem_duplicidade()

    def test_watermark_false_auto_todos_resolvidos(self):
        self.ativar_limpo()
        for resolved in (svc.PERFIL_PERFORMANCE, svc.PERFIL_BALANCED, svc.PERFIL_QUALITY):
            r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli, resolved_profile=resolved)
            self.assertTrue(r.ok, r.mensagem)
            self._checar_sem_duplicidade()

    def test_watermark_false_na_ativacao(self):
        self.ativar_limpo()
        self._checar_sem_duplicidade()
        self.assertEqual(self.ler_chave(svc.DGVOODOO_CONF, "[DirectX]", "dgVoodooWatermark"),
                         "false")
        self.assertEqual(self.ler_chave(svc.DGVOODOO_CONF, "[General]", "OutputAPI"),
                         "d3d11_fl11_0")


# --- AUTO não regrediu ---------------------------------------------------------
class TestAutoNaoRegrediu(BaseVendorTest):
    """9-11 e 24. auto->perfil aplica exatamente o perfil resolvido."""

    def _ler_aa(self):
        return self.ler_chave(svc.DGVOODOO_CONF, "[DirectX]", "Antialiasing")

    def test_auto_performance(self):
        self.ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli, resolved_profile=svc.PERFIL_PERFORMANCE)
        self.assertTrue(r.ok)
        self.assertEqual(self._ler_aa(), "appdriven")
        e = svc._carregar_estado(self.cli)
        self.assertEqual(e["preset"], "auto")
        self.assertEqual(e["resolved_profile"], "performance")

    def test_auto_balanced(self):
        self.ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli, resolved_profile=svc.PERFIL_BALANCED)
        self.assertTrue(r.ok)
        self.assertEqual(self._ler_aa(), "2x")
        e = svc._carregar_estado(self.cli)
        self.assertEqual(e["resolved_profile"], "balanced")

    def test_auto_quality(self):
        self.ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli, resolved_profile=svc.PERFIL_QUALITY)
        self.assertTrue(r.ok)
        self.assertEqual(self._ler_aa(), "4x")
        e = svc._carregar_estado(self.cli)
        self.assertEqual(e["resolved_profile"], "quality")

    def test_auto_resolvido_ausente_rejeitado(self):
        self.ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli)
        self.assertFalse(r.ok)
        self.assertEqual(self._ler_aa(), "2x", "conf default pós-ativação = balanced")

    def test_auto_nao_reinstala_dll(self):
        self.ativar_limpo()
        hash_dll = svc._carregar_estado(self.cli)["d3d9"]["installed_sha256"]
        self.assertTrue(svc.aplicar_perfil(
            svc.PERFIL_AUTO, self.cli, resolved_profile=svc.PERFIL_QUALITY).ok)
        e2 = svc._carregar_estado(self.cli)
        self.assertEqual(e2["d3d9"]["installed_sha256"], hash_dll)
        self.assertEqual(_h(self.ler(svc.D3D9_DLL)), HASH_DLL)

    def test_manual_apos_auto_remove_resolvido(self):
        self.ativar_limpo()
        self.assertTrue(svc.aplicar_perfil(
            svc.PERFIL_AUTO, self.cli, resolved_profile=svc.PERFIL_QUALITY).ok)
        self.assertTrue(svc.aplicar_perfil(svc.PERFIL_PERFORMANCE, self.cli).ok)
        e = svc._carregar_estado(self.cli)
        self.assertEqual(e["preset"], "performance")
        self.assertNotIn("resolved_profile", e)
        self.assertEqual(self._ler_aa(), "appdriven")


# --- Ativação / restauração / estado em tmp_path --------------------------------
class TestAtivacaoRestauracao2874(BaseVendorTest):
    """18-21. Ativação instala os bytes novos do template 2.87.4."""

    def test_ativacao_instala_dll_2874(self):
        self.ativar_limpo()
        self.assertEqual(_h(self.ler(svc.D3D9_DLL)), HASH_DLL)
        self.assertEqual(_h(self.ler(svc.D3D9_DLL)),
                         _h_file(svc.resolver_template_d3d9()))

    def test_dll_instalada_igual_template(self):
        self.ativar_limpo()
        with open(svc.resolver_template_d3d9(), "rb") as f:
            tpl = f.read()
        self.assertEqual(self.ler(svc.D3D9_DLL), tpl)

    def test_conf_instalado_preset_correto(self):
        self.ativar_limpo()
        dados_cliente = self.ler(svc.DGVOODOO_CONF)
        self.assertTrue(len(dados_cliente) >= 3 and dados_cliente[:3] != b"\xef\xbb\xbf",
                        "conf instalado na ativacao nao pode ter BOM UTF-8")
        gerado = svc._gerar_conf_perfil(svc.PERFIL_BALANCED)
        self.assertEqual(_h(dados_cliente), _h(gerado),
                         "Conf pós-ativação deve equivaler à base balanced (V1 validada).")
        texto = dados_cliente.decode("utf-8-sig")
        self.assertEqual(_ler_chave_texto(texto, "[General]", "OutputAPI"), "d3d11_fl11_0")
        self.assertEqual(_ler_chave_texto(texto, "[DirectX]", "Antialiasing"), "2x")
        self.assertEqual(_ler_chave_texto(texto, "[DirectX]", "Filtering"), "16")
        self.assertEqual(_ler_chave_texto(texto, "[DirectX]", "dgVoodooWatermark"), "false")
        e = svc._carregar_estado(self.cli)
        self.assertEqual(e["status"], "active")
        self.assertEqual(e["d3d9"]["installed_sha256"], HASH_DLL)

    def test_restauracao_devolve_original(self):
        orig = b"conf original do cliente\n"
        self.escrever(svc.DGVOODOO_CONF, orig)
        self.ativar_limpo()
        self.assertTrue(self.existe_arquivo(svc.D3D9_DLL))
        r = svc.restaurar_directx_original(self.cli)
        self.assertTrue(r.ok, r.mensagem)
        self.assertEqual(r.estado, svc.Estado.ORIGINAL)
        self.assertFalse(self.existe_arquivo(svc.D3D9_DLL))
        self.assertEqual(self.ler(svc.DGVOODOO_CONF), orig)

    def test_estado_backup_coerente(self):
        orig = b"original A\n"
        self.escrever(svc.DGVOODOO_CONF, orig)
        self.ativar_limpo()
        e = svc._carregar_estado(self.cli)
        self.assertTrue(e["conf"]["original_present"])
        self.assertTrue(e["conf"]["original_sha256"])
        self.assertTrue(os.path.isfile(e["conf"]["backup_path"]))
        self.assertFalse(e["d3d9"]["original_present"])
        self.assertTrue(svc.restaurar_directx_original(self.cli).ok)
        self.assertEqual(self.ler(svc.DGVOODOO_CONF), orig)
        self.assertIsNone(svc._carregar_estado(self.cli))

    def test_modificado_externamente_bloqueia(self):
        self.ativar_limpo()
        with open(self.caminho(svc.DGVOODOO_CONF), "wb") as f:
            f.write(b"modificado externamente\n")
        r = svc.restaurar_directx_original(self.cli)
        self.assertFalse(r.ok)
        self.assertEqual(r.estado, svc.Estado.MODIFICADO_EXTERNAMENTE)
        self.assertTrue(self.existe_arquivo(svc.D3D9_DLL))
        self.assertEqual(self.ler(svc.DGVOODOO_CONF), b"modificado externamente\n")

    def test_deteccao_pos_ativacao_ativo(self):
        self.ativar_limpo()
        r = svc.detectar_estado(self.cli)
        self.assertEqual(r.estado, svc.Estado.ATIVO)


# --- Retrocompatibilidade / template swap --------------------------------------
class TestRetroCompatibilidade(BaseVendorTest):
    """Instalação antiga (2.87.3) não é interpretada como 2.87.4."""

    def test_dll_antiga_com_registro_continua_ativo(self):
        # Simula instalação antiga (2.87.3) registrada pelo Optimizer: o hash
        # instalado registrado é o do arquivo no disco e NÃO é o template 2.87.4.
        dll_antiga = b"dll 2.87.3 instalada anteriormente pelo Optimizer"
        self.escrever(svc.D3D9_DLL, dll_antiga)
        hash_antigo = _h(dll_antiga)
        self.assertNotEqual(hash_antigo, HASH_DLL)
        with open(svc.resolver_template_conf(), "r", encoding="utf-8-sig") as f:
            texto_conf = f.read()
        self.escrever(svc.DGVOODOO_CONF, texto_conf.encode("utf-8"))
        estado = {
            "format_version": 1, "status": "active",
            "preset": "Aika Recomendado", "backend": "d3d11_fl11_0",
            "d3d9": {"original_present": False, "installed_sha256": hash_antigo},
            "conf": {"original_present": False,
                     "installed_sha256": _h(self.ler(svc.DGVOODOO_CONF))},
        }
        svc._salvar_estado(self.cli, estado)
        # Reconhecida como instalação nossa (ATIVO) — nunca CONFLITO.
        r = svc.detectar_estado(self.cli)
        self.assertEqual(r.estado, svc.Estado.ATIVO)
        # Reativação substitui pelos bytes novos 2.87.4.
        r = svc.ativar_dgvoodoo(self.cli)
        self.assertTrue(r.ok, r.mensagem)
        self.assertEqual(_h(self.ler(svc.D3D9_DLL)), HASH_DLL)

    def test_dll_desconhecida_sem_registro_conflito(self):
        # Sem registro e DLL != template atual -> CONFLITO (nada presumido).
        self.escrever(svc.D3D9_DLL, b"dll totalmente desconhecida")
        r = svc.detectar_estado(self.cli)
        self.assertEqual(r.estado, svc.Estado.CONFLITO)
        self.assertIsNotNone(r.detalhes_conflito)


if __name__ == "__main__":
    unittest.main()
