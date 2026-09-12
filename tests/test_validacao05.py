# -*- coding: utf-8 -*-
"""Validação 05 — regressão permanente do motor AutoMod/Texturas.

Exclusivamente arquivos binários sintéticos, TemporaryDirectory e mocks.
Não toca cliente AIKA, Registro, processos, serviços ou arquivos do usuário.
"""
import hashlib
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import automod  # noqa: E402
import textura  # noqa: E402


def gravar(caminho, dados):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(dados)
    return str(caminho)


def sha256_bytes(dados):
    return hashlib.sha256(dados).hexdigest()


def payload_dxt(magic, width=8, height=8, byte=0x5A):
    bloco = 8 if magic == b"JT31" else 16
    tamanho = max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * bloco
    return bytes([byte]) * tamanho


def jit_dxt(magic=b"JT31", width=8, height=8, prefix=b"", tail=b"", byte=0x5A):
    return (prefix + magic + struct.pack("<II", width, height)
            + payload_dxt(magic, width, height, byte) + tail)


def jit20(width=2, height=2, prefix=b"", tail=b"", indices=None):
    paleta = bytearray()
    for i in range(256):
        paleta.extend((i, (i * 3) & 0xFF, (255 - i) & 0xFF, 255))
    if indices is None:
        indices = bytes(i % 256 for i in range(width * height))
    return (prefix + b"JT20" + struct.pack("<II", width, height)
            + bytes(paleta) + bytes(indices) + tail)


def dds_bytes(fourcc=b"DXT1", width=8, height=8, byte=0x33, mipmaps=1):
    bloco = 8 if fourcc == b"DXT1" else 16
    total = 0
    w, h = width, height
    for _ in range(mipmaps):
        total += max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * bloco
        w, h = max(1, w // 2), max(1, h // 2)
    return textura.build_dds_header(width, height, fourcc, mipmaps, total) + bytes([byte]) * total


def tga_true(width=2, height=2, bpp=24, pixels=None, rle=False, trailer=b""):
    bytes_pixel = bpp // 8
    if pixels is None:
        pixels = [bytes((i * 7 & 0xFF, i * 11 & 0xFF, i * 13 & 0xFF,
                         255))[:bytes_pixel] for i in range(width * height)]
    header = bytearray(18)
    header[2] = 10 if rle else 2
    struct.pack_into("<HH", header, 12, width, height)
    header[16] = bpp
    header[17] = 0x20 | (8 if bpp == 32 else 0)
    if rle:
        # Um pacote raw mantém todos os pixels e cobre o caminho RLE.
        corpo = bytes([len(pixels) - 1]) + b"".join(pixels)
    else:
        corpo = b"".join(pixels)
    return bytes(header) + corpo + trailer


def tga_paletted(width=2, height=2, rle=False, trailer=b""):
    header = bytearray(18)
    header[1] = 1
    header[2] = 9 if rle else 1
    struct.pack_into("<H", header, 3, 0)
    struct.pack_into("<H", header, 5, 2)
    header[7] = 24
    struct.pack_into("<HH", header, 12, width, height)
    header[16] = 8
    header[17] = 0x20
    paleta = b"\x00\x00\xFF" + b"\x00\xFF\x00"
    indices = bytes(i % 2 for i in range(width * height))
    corpo = (bytes([len(indices) - 1]) + indices) if rle else indices
    return bytes(header) + paleta + corpo + trailer


class SandboxAutomod(unittest.TestCase):
    """Isola backup, índice e histórico por cliente dentro do teste."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.raiz = Path(self._td.name)
        self.backups = self.raiz / "_backups"

        def backup_cliente(pasta_jogo=None, criar=True):
            raiz = os.path.normcase(os.path.abspath(str(pasta_jogo)))
            identidade = hashlib.sha256(raiz.encode("utf-8")).hexdigest()[:16]
            destino = self.backups / identidade
            if criar:
                destino.mkdir(parents=True, exist_ok=True)
            return str(destino)

        self._patch_backup = patch.object(
            automod, "obter_pasta_backup_cliente", side_effect=backup_cliente)
        self._patch_backup.start()
        self.addCleanup(self._patch_backup.stop)

    def cliente(self, nome="ClienteA"):
        pasta = self.raiz / nome
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta

    def backup_path(self, cliente, destino):
        paths = automod._paths_cliente(str(cliente))
        return Path(paths["backup"]) / Path(destino).relative_to(cliente)

    def injetar(self, fontes, cliente):
        logs = []
        resultado = automod.injetar_mods(
            [str(f) for f in fontes], str(cliente), log_callback=logs.append)
        return resultado, logs


# ---------------------------------------------------------------------------
# 1. DETECTOR CANÔNICO — 8 testes
# ---------------------------------------------------------------------------
class TestDetectorCanonico(unittest.TestCase):
    def test_01_automod_usa_detector_canonico(self):
        self.assertIs(automod.detectar_textura_jit_bytes,
                      textura.detectar_textura_jit_bytes)
        dados = jit_dxt(b"JT33")
        self.assertEqual(automod.detectar_formato_jit(dados)["tipo"], "JT33")

    def test_02_detecta_jt31(self):
        info = textura.detectar_textura_jit_bytes(jit_dxt(b"JT31"))
        self.assertEqual((info["tipo"], info["fourcc"]), ("JT31", b"DXT1"))

    def test_03_detecta_jt33(self):
        info = textura.detectar_textura_jit_bytes(jit_dxt(b"JT33"))
        self.assertEqual((info["tipo"], info["fourcc"]), ("JT33", b"DXT3"))

    def test_04_detecta_jt35(self):
        info = textura.detectar_textura_jit_bytes(jit_dxt(b"JT35"))
        self.assertEqual((info["tipo"], info["fourcc"]), ("JT35", b"DXT5"))

    def test_05_detecta_jt20(self):
        info = textura.detectar_textura_jit_bytes(jit20(3, 2))
        self.assertEqual((info["tipo"], info["width"], info["height"]),
                         ("JT20", 3, 2))

    def test_06_falso_jt20_nao_impede_jt35_posterior(self):
        falso = b"JT20" + struct.pack("<II", 8, 8) + b"CURTO"
        dados = falso + b"PREFIXO" + jit_dxt(b"JT35", byte=0x77)
        info = textura.detectar_textura_jit_bytes(dados)
        self.assertEqual(info["tipo"], "JT35")
        self.assertTrue(any(item[1] == "JT20" for item in info["rejeitados"]))

    def test_07_detecta_dds_embutido(self):
        info = textura.detectar_textura_jit_bytes(b"PROPRIETARIO" + dds_bytes(b"DXT1"))
        self.assertEqual((info["tipo"], info["fourcc"]), ("DDS", b"DXT1"))
        self.assertEqual(info["offset"], len(b"PROPRIETARIO"))

    def test_08_detecta_tga_embutido(self):
        info = textura.detectar_textura_jit_bytes(b"PFX" + tga_true(2, 2, 32))
        self.assertEqual((info["tipo"], info["bpp"], info["offset"]),
                         ("TGA", 32, 3))


# ---------------------------------------------------------------------------
# 2. JIT -> DDS — 4 testes (total 12)
# ---------------------------------------------------------------------------
class TestExtracaoDds(unittest.TestCase):
    def _extrair(self, dados, nome="tex.jit"):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        caminho = Path(gravar(Path(td.name) / nome, dados))
        ok, msg = textura.extrair_textura_jit(str(caminho))
        saida = caminho.with_suffix(".dds")
        return ok, msg, saida

    def test_09_jt31_offset_zero_para_dxt1(self):
        payload = payload_dxt(b"JT31", 8, 4, 0x11)
        ok, msg, saida = self._extrair(b"JT31" + struct.pack("<II", 8, 4) + payload)
        self.assertTrue(ok, msg)
        dados = saida.read_bytes()
        self.assertEqual((dados[:4], dados[84:88]), (b"DDS ", b"DXT1"))
        self.assertEqual(struct.unpack_from("<II", dados, 12), (4, 8))
        self.assertEqual(dados[128:], payload)

    def test_10_jt33_com_prefixo_para_dxt3(self):
        ok, msg, saida = self._extrair(jit_dxt(b"JT33", prefix=b"PFX", byte=0x22))
        self.assertTrue(ok, msg)
        self.assertEqual(saida.read_bytes()[84:88], b"DXT3")

    def test_11_jt35_com_trailer_para_dxt5_sem_copiar_trailer(self):
        payload = payload_dxt(b"JT35", byte=0x44)
        ok, msg, saida = self._extrair(jit_dxt(b"JT35", tail=b"TRAILER", byte=0x44))
        self.assertTrue(ok, msg)
        dados = saida.read_bytes()
        self.assertEqual(dados[84:88], b"DXT5")
        self.assertEqual(dados[128:], payload)

    def test_12_payload_dxt_truncado_falha(self):
        dados = b"JT31" + struct.pack("<II", 8, 8) + b"CURTO"
        ok, _, saida = self._extrair(dados)
        self.assertFalse(ok)
        self.assertFalse(saida.exists())


# ---------------------------------------------------------------------------
# 3. JT20 -> TGA — 4 testes (total 16)
# ---------------------------------------------------------------------------
class TestExtracaoJt20(unittest.TestCase):
    def _extrair(self, dados):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        caminho = Path(gravar(Path(td.name) / "tex.jit", dados))
        ok, msg = textura.extrair_textura_jit(str(caminho))
        return ok, msg, caminho.with_suffix(".tga")

    def test_13_paleta_indices_e_tga_final(self):
        ok, msg, saida = self._extrair(jit20(2, 2, indices=b"\x00\x01\x02\x03"))
        self.assertTrue(ok, msg)
        dados = saida.read_bytes()
        self.assertEqual((dados[2], dados[16]), (2, 32))
        self.assertEqual(struct.unpack_from("<HH", dados, 12), (2, 2))
        self.assertEqual(len(dados), 18 + 16)

    def test_14_jt20_valido_apos_prefixo(self):
        ok, msg, saida = self._extrair(jit20(2, 1, prefix=b"CABECALHO"))
        self.assertTrue(ok, msg)
        self.assertEqual(struct.unpack_from("<HH", saida.read_bytes(), 12), (2, 1))

    def test_15_paleta_truncada_falha(self):
        dados = b"JT20" + struct.pack("<II", 2, 2) + bytes(100)
        ok, _, saida = self._extrair(dados)
        self.assertFalse(ok)
        self.assertFalse(saida.exists())

    def test_16_indices_truncados_e_falso_positivo_falham(self):
        dados = b"JT20" + struct.pack("<II", 4, 4) + bytes(1024) + bytes(3)
        ok, msg, saida = self._extrair(dados)
        self.assertFalse(ok)
        self.assertIn("rejeitados", msg.lower())
        self.assertFalse(saida.exists())


# ---------------------------------------------------------------------------
# 4. DDS/TGA EMBUTIDOS — 6 testes (total 22)
# ---------------------------------------------------------------------------
class TestFormatosEmbutidos(unittest.TestCase):
    def _extrair(self, dados):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        caminho = Path(gravar(Path(td.name) / "emb.jit", dados))
        ok, msg = textura.extrair_textura_jit(str(caminho))
        return ok, msg, caminho

    def test_17_dds_embutido_preserva_do_magic_ao_eof(self):
        dds = dds_bytes(b"DXT5", 4, 4) + b"TRAILER"
        ok, msg, caminho = self._extrair(b"PREFIX" + dds)
        self.assertTrue(ok, msg)
        self.assertEqual(caminho.with_suffix(".dds").read_bytes(), dds)

    def test_18_tga_true_color_24_bpp(self):
        tga = tga_true(2, 2, 24)
        ok, msg, caminho = self._extrair(tga)
        self.assertTrue(ok, msg)
        self.assertEqual(caminho.with_suffix(".tga").read_bytes(), tga)

    def test_19_tga_32_bpp_com_prefixo_e_trailer(self):
        tga = tga_true(2, 1, 32, trailer=b"FOOTER")
        ok, msg, caminho = self._extrair(b"PFX" + tga)
        self.assertTrue(ok, msg)
        self.assertEqual(caminho.with_suffix(".tga").read_bytes(), tga)

    def test_20_tga_rle_suportado(self):
        tga = tga_true(3, 1, 24, rle=True)
        ok, msg, caminho = self._extrair(b"HEAD" + tga)
        self.assertTrue(ok, msg)
        self.assertEqual(caminho.with_suffix(".tga").read_bytes(), tga)

    def test_21_tga_paletizado_suportado(self):
        tga = tga_paletted(2, 2)
        ok, msg, caminho = self._extrair(b"X" + tga)
        self.assertTrue(ok, msg)
        self.assertEqual(caminho.with_suffix(".tga").read_bytes(), tga)

    def test_22_tga_truncado_ou_alem_dos_limites_falha(self):
        for dados in (tga_true(2, 2, 24)[:-2],
                      bytes(12) + struct.pack("<HH", 5000, 1) + b"\x18\x20"):
            ok, _, caminho = self._extrair(dados)
            self.assertFalse(ok)
            self.assertFalse(caminho.with_suffix(".tga").exists())


# ---------------------------------------------------------------------------
# 5. DDS -> JIT — 4 testes (total 26)
# ---------------------------------------------------------------------------
class TestDdsParaJit(unittest.TestCase):
    def _converter(self, dds, template):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        p_dds = gravar(Path(td.name) / "novo.dds", dds)
        p_jit = gravar(Path(td.name) / "alvo.jit", template)
        return automod.converter_dds_para_jit(p_dds, p_jit)

    def test_23_dxt1_reconstroi_jt31(self):
        dados, formato, info = self._converter(
            dds_bytes(b"DXT1", 4, 8, 0x11), jit_dxt(b"JT35"))
        self.assertEqual((dados[:4], formato["tipo_resultante"]), (b"JT31", "JT31"))
        self.assertEqual(struct.unpack_from("<II", dados, 4), (4, 8))
        self.assertEqual(dados[12:], info["payload_all"])

    def test_24_template_jt35_com_dxt3_vira_jt33_preservando_prefixo_cauda(self):
        prefixo, cauda = b"PROPRIETARIO", b"CAUDA"
        dados, formato, info = self._converter(
            dds_bytes(b"DXT3", 8, 4, 0x22),
            jit_dxt(b"JT35", prefix=prefixo, tail=cauda))
        self.assertTrue(dados.startswith(prefixo + b"JT33"))
        self.assertTrue(dados.endswith(cauda))
        self.assertEqual(formato["tipo_resultante"], "JT33")
        self.assertTrue(formato["formato_alterado"])
        self.assertIn(info["payload_all"], dados)

    def test_25_dxt5_reconstroi_jt35(self):
        dados, formato, _ = self._converter(
            dds_bytes(b"DXT5", 8, 8, 0x55), jit_dxt(b"JT31"))
        self.assertEqual(dados[:4], b"JT35")
        self.assertEqual(formato["tipo_resultante"], "JT35")

    def test_26_dds_embutido_substitui_bloco_e_preserva_envelope(self):
        antigo = dds_bytes(b"DXT1", 4, 4, 0x10)
        novo = dds_bytes(b"DXT5", 8, 8, 0x20)
        prefixo, cauda = b"PREFIX", b"TAIL"
        dados, formato, _ = self._converter(novo, prefixo + antigo + cauda)
        self.assertEqual(dados, prefixo + novo + cauda)
        self.assertEqual(formato["tipo_resultante"], "DDS")


# ---------------------------------------------------------------------------
# 6. TGA -> JIT — 7 testes (total 33)
# ---------------------------------------------------------------------------
class TestTgaParaJit(unittest.TestCase):
    def _converter(self, tga, template):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        p_tga = gravar(Path(td.name) / "novo.tga", tga)
        p_jit = gravar(Path(td.name) / "alvo.jit", template)
        return automod.converter_tga_para_jit(p_tga, p_jit)

    def test_27_tga_embutido_preserva_prefixo_e_cauda(self):
        antigo = tga_true(2, 2, 24)
        novo = tga_true(1, 2, 32)
        dados, formato, _ = self._converter(novo, b"PFX" + antigo + b"TAIL")
        self.assertEqual(dados, b"PFX" + novo + b"TAIL")
        self.assertEqual(formato["tipo_resultante"], "TGA")

    def test_28_tga_24_bpp_para_jt20(self):
        dados, formato, info = self._converter(tga_true(2, 2, 24), jit20(2, 2))
        self.assertEqual((dados[:4], formato["tipo_resultante"]), (b"JT20", "JT20"))
        self.assertEqual(len(dados), 12 + 1024 + 4)
        self.assertEqual(len(info["pixels"]), 4)

    def test_29_tga_32_bpp_para_jt20(self):
        dados, _, _ = self._converter(tga_true(2, 1, 32), jit20(2, 1))
        self.assertEqual(struct.unpack_from("<II", dados, 4), (2, 1))

    def test_30_tga_rle_para_jt20(self):
        dados, _, info = self._converter(tga_true(3, 1, 24, rle=True), jit20(3, 1))
        self.assertEqual(dados[:4], b"JT20")
        self.assertEqual(info["image_type"], 10)

    def test_31_tga_paletizado_para_jt20(self):
        dados, _, info = self._converter(tga_paletted(2, 2), jit20(2, 2))
        self.assertEqual(dados[:4], b"JT20")
        self.assertEqual(info["image_type"], 1)

    def test_32_mais_de_256_cores_usa_quantizacao_existente(self):
        width, height = 17, 16
        pixels = [bytes((i & 0xFF, (i >> 8) & 0xFF, (i * 17) & 0xFF))
                  for i in range(width * height)]
        dados, _, _ = self._converter(
            tga_true(width, height, 24, pixels=pixels), jit20(1, 1, tail=b"TAIL"))
        self.assertEqual(struct.unpack_from("<II", dados, 4), (width, height))
        self.assertEqual(len(dados[12 + 1024:-4]), width * height)
        self.assertTrue(dados.endswith(b"TAIL"))

    def test_33_dimensoes_novas_sao_preservadas_e_tga_invalido_falha(self):
        dados, _, _ = self._converter(tga_true(3, 2, 24), jit20(1, 1))
        self.assertEqual(struct.unpack_from("<II", dados, 4), (3, 2))
        with self.assertRaises(ValueError):
            self._converter(b"TGA-INVALIDO", jit20(1, 1))


# ---------------------------------------------------------------------------
# 7–10. DIRETO, TRANSAÇÕES, ÍNDICE E RESTORE — 9 testes (total 42)
# ---------------------------------------------------------------------------
class TestAutoModTransacional(SandboxAutomod):
    def test_34_extensoes_nativas_copiam_bytes_sem_parser_novo(self):
        for extensao in (".jit", ".msh", ".ms3", ".bin", ".ef"):
            fonte = gravar(self.raiz / f"fonte{extensao}", b"NATIVO-" + extensao.encode())
            destino = gravar(self.raiz / f"destino{extensao}", b"ORIGINAL")
            dados, operacao, formato, info = automod.preparar_textura_para_injecao(
                fonte, destino)
            self.assertEqual(dados, Path(fonte).read_bytes())
            self.assertEqual(operacao, "COPY DIRETO")
            self.assertIsNone(formato)
            self.assertIsNone(info)

    def test_35_jit_direto_backup_sha_historico_e_original_preservado(self):
        cliente = self.cliente()
        destino = Path(gravar(cliente / "Data" / "tex.jit", jit_dxt(b"JT31", byte=0x10)))
        original = destino.read_bytes()
        fonte = Path(gravar(self.raiz / "mods" / "tex.jit", jit_dxt(b"JT31", byte=0x20)))
        resultado, _ = self.injetar([fonte], cliente)
        self.assertEqual(resultado, 1)
        self.assertEqual(destino.read_bytes(), fonte.read_bytes())
        backup = self.backup_path(cliente, destino)
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(sha256_bytes(backup.read_bytes()), sha256_bytes(original))
        self.assertFalse(list(destino.parent.glob("*.automod.tmp")))
        historico = automod.carregar_historico_automod(str(cliente))
        self.assertIn("data/tex.jit", historico["items"])

        # Segunda alteração não pode substituir o backup original.
        fonte.write_bytes(jit_dxt(b"JT31", byte=0x30))
        resultado, _ = self.injetar([fonte], cliente)
        self.assertEqual(resultado, 1)
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(automod.carregar_historico_automod(
            str(cliente))["items"]["data/tex.jit"]["injection_count"], 2)

    def test_36_falha_de_backup_impede_escrita(self):
        cliente = self.cliente()
        destino = Path(gravar(cliente / "Data" / "a.bin", b"ORIGINAL"))
        fonte = Path(gravar(self.raiz / "mods" / "a.bin", b"MOD"))
        with patch.object(automod, "fazer_backup_rapido", return_value=False):
            resultado, logs = self.injetar([fonte], cliente)
        self.assertEqual(resultado, 0)
        self.assertEqual(destino.read_bytes(), b"ORIGINAL")
        self.assertTrue(any("backup obrigatório falhou" in item for item in logs))

    def test_37_falha_de_escrita_aplica_rollback(self):
        cliente = self.cliente()
        destino = Path(gravar(cliente / "Data" / "a.bin", b"ORIGINAL"))
        fonte = Path(gravar(self.raiz / "mods" / "a.bin", b"MOD"))
        real = automod._escrever_atomico_validado
        chamadas = {"n": 0}

        def falha_depois_de_corromper(caminho, dados):
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                Path(caminho).write_bytes(b"PARCIAL")
                raise OSError("falha simulada")
            return real(caminho, dados)

        with patch.object(automod, "_escrever_atomico_validado",
                          side_effect=falha_depois_de_corromper):
            resultado, _ = self.injetar([fonte], cliente)
        self.assertEqual(resultado, 0)
        self.assertEqual(destino.read_bytes(), b"ORIGINAL")
        self.assertEqual(chamadas["n"], 2)

    def test_38_falha_de_historico_aplica_rollback(self):
        cliente = self.cliente()
        destino = Path(gravar(cliente / "Data" / "a.bin", b"ORIGINAL"))
        fonte = Path(gravar(self.raiz / "mods" / "a.bin", b"MOD"))
        with patch.object(automod, "registrar_mod_ativo", return_value=False):
            resultado, logs = self.injetar([fonte], cliente)
        self.assertEqual(resultado, 0)
        self.assertEqual(destino.read_bytes(), b"ORIGINAL")
        self.assertTrue(any("histórico" in item for item in logs))

    def test_39_indice_por_cliente_stale_removido_novo_arquivo_e_rebuild(self):
        a, b = self.cliente("ClienteA"), self.cliente("ClienteB")
        alvo_a = Path(gravar(a / "Data" / "existente.bin", b"A"))
        removido = Path(gravar(a / "Data" / "removido.bin", b"R"))
        alvo_b = Path(gravar(b / "Data" / "existente.bin", b"B"))
        self.assertTrue(automod.criar_index_jogo(str(a)))
        self.assertTrue(automod.criar_index_jogo(str(b)))
        paths_a, paths_b = automod._paths_cliente(str(a)), automod._paths_cliente(str(b))
        self.assertNotEqual(paths_a["index"], paths_b["index"])
        index_a = automod.carregar_index_jogo(str(a))
        valido, _ = automod._indice_valido(index_a, str(b), paths_a["index_meta"])
        self.assertFalse(valido)

        removido.unlink()
        index_a = automod.carregar_index_jogo(str(a))
        self.assertNotIn(str(removido), index_a.values())
        novo_alvo = Path(gravar(a / "Data" / "novo.bin", b"VELHO"))
        fonte = Path(gravar(self.raiz / "mods" / "novo.bin", b"NOVO"))
        resultado, _ = self.injetar([fonte], a)
        self.assertEqual(resultado, 1)  # ausência no índice aciona rebuild previsto
        self.assertEqual(novo_alvo.read_bytes(), b"NOVO")
        self.assertEqual(alvo_a.read_bytes(), b"A")
        self.assertEqual(alvo_b.read_bytes(), b"B")

    def test_40_basename_duplicado_e_path_fora_nunca_sao_escolhidos(self):
        cliente = self.cliente()
        a = Path(gravar(cliente / "A" / "dup.jit", jit_dxt()))
        b = Path(gravar(cliente / "B" / "dup.jit", jit_dxt(byte=0x20)))
        fora = Path(gravar(self.raiz / "fora" / "dup.jit", jit_dxt(byte=0x30)))
        index = {"a": str(a), "b": str(b), "fora": str(fora)}
        with self.assertRaisesRegex(ValueError, "ambíguo"):
            automod._encontrar_destino(index, "dup", ".jit", str(cliente))
        with self.assertRaises(FileNotFoundError):
            automod._encontrar_destino({"fora": str(fora)}, "dup", ".jit",
                                       str(cliente))

    def test_41_restore_individual_isolado_por_cliente(self):
        a, b = self.cliente("ClienteA"), self.cliente("ClienteB")
        destino_a = Path(gravar(a / "Data" / "mesmo.bin", b"ORIGINAL-A"))
        destino_b = Path(gravar(b / "Data" / "mesmo.bin", b"ORIGINAL-B"))
        fonte = Path(gravar(self.raiz / "mods" / "mesmo.bin", b"MOD-A"))
        self.assertEqual(self.injetar([fonte], a)[0], 1)
        chave = automod._chave_destino(str(destino_a), str(a))
        ok_b, _ = automod.restaurar_mod_individual(chave, str(b))
        self.assertFalse(ok_b)
        self.assertEqual(destino_b.read_bytes(), b"ORIGINAL-B")
        ok_a, _ = automod.restaurar_mod_individual(chave, str(a))
        self.assertTrue(ok_a)
        self.assertEqual(destino_a.read_bytes(), b"ORIGINAL-A")
        self.assertFalse(automod.carregar_historico_automod(str(a))["items"])

    def test_42_restore_multiplo_restaura_validos_e_reporta_falha(self):
        cliente = self.cliente()
        destinos, fontes = [], []
        for nome in ("um.bin", "dois.ef"):
            destinos.append(Path(gravar(cliente / "Data" / nome,
                                        ("ORIGINAL-" + nome).encode())))
            fontes.append(Path(gravar(self.raiz / "mods" / nome,
                                      ("MOD-" + nome).encode())))
        self.assertEqual(self.injetar(fontes, cliente)[0], 2)
        chaves = [automod._chave_destino(str(d), str(cliente)) for d in destinos]
        resultado = automod.restaurar_mods_selecionados(
            chaves + ["ausente.bin"], str(cliente))
        self.assertEqual(len(resultado["restaurados"]), 2)
        self.assertEqual(len(resultado["falhas"]), 1)
        for destino, nome in zip(destinos, ("um.bin", "dois.ef")):
            self.assertEqual(destino.read_bytes(), ("ORIGINAL-" + nome).encode())


if __name__ == "__main__":
    unittest.main(verbosity=2)