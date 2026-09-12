# -*- coding: utf-8 -*-
"""Correção 06C — MS3 indexado valida somente registros referenciados."""
import math
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import extractor_sets as exts  # noqa: E402
from tests.test_validacao06 import ms3_bytes  # noqa: E402


def indexed_ms3(position_count=3, records=None, faces=((0, 1, 2),), trailer=b""):
    """Produz o layout indexado já reconhecido pelo conversor."""
    if records is None:
        records = [(0, 0.0, 0.0), (1, 1.0, 0.0), (2, 0.0, 1.0)]
    header = bytearray(0x74)
    header[0x20:0x28] = b"arma.tga"
    struct.pack_into("<I", header, 0x54, position_count)
    struct.pack_into("<I", header, 0x58, len(records))
    struct.pack_into("<I", header, 0x5C, len(faces))
    data = bytearray(header)
    for i in range(position_count):
        data.extend(struct.pack("<3f", float(i), float(i % 2), 0.0))
    for registro in records:
        if isinstance(registro, bytes):
            if len(registro) != 12:
                raise ValueError("registro raw deve ter 12 bytes")
            data.extend(registro)
        else:
            data.extend(struct.pack("<I2f", *registro))
    for face in faces:
        data.extend(struct.pack("<3H", *face))
    data.extend(trailer)
    return bytes(data)


def converter(dados):
    td = tempfile.TemporaryDirectory()
    caminho = Path(td.name) / "arma.ms3"
    caminho.write_bytes(dados)
    ok, msg = exts.convert_ms3_to_obj(str(caminho))
    obj = caminho.with_suffix(".obj")
    conteudo = obj.read_text(encoding="utf-8") if obj.exists() else ""
    return td, ok, msg, conteudo


def linhas_obj(conteudo, prefixo):
    return [linha for linha in conteudo.splitlines() if linha.startswith(prefixo)]


class TestMs3IndexedReferenciado(unittest.TestCase):
    def test_01_indexed_normal_todos_utilizados_pass(self):
        td, ok, msg, obj = converter(indexed_ms3())
        self.addCleanup(td.cleanup)
        self.assertTrue(ok, msg)
        self.assertEqual(len(linhas_obj(obj, "v ")), 3)
        self.assertEqual(len(linhas_obj(obj, "vt ")), 3)
        self.assertIn("f 1/1/1 2/2/2 3/3/3", obj)

    def test_02_nan_em_registro_nao_usado_pass(self):
        registros = [(0, 0.0, 0.0), (1, 1.0, 0.0), (2, 0.0, 1.0),
                     (999999, math.nan, math.nan)]
        td, ok, msg, obj = converter(indexed_ms3(records=registros))
        self.addCleanup(td.cleanup)
        self.assertTrue(ok, msg)
        self.assertEqual(len(linhas_obj(obj, "v ")), 3)

    def test_03_infinity_em_registro_nao_usado_pass(self):
        registros = [(0, 0.0, 0.0), (1, 1.0, 0.0), (2, 0.0, 1.0),
                     (0xFFFFFFFF, math.inf, -math.inf)]
        td, ok, msg, _ = converter(indexed_ms3(records=registros))
        self.addCleanup(td.cleanup)
        self.assertTrue(ok, msg)

    def test_04_nan_em_registro_usado_fail(self):
        registros = [(0, 0.0, 0.0), (1, math.nan, 0.0), (2, 0.0, 1.0)]
        td, ok, msg, obj = converter(indexed_ms3(records=registros))
        self.addCleanup(td.cleanup)
        self.assertFalse(ok)
        self.assertIn("UV 1", msg)
        self.assertFalse(obj)

    def test_05_infinity_em_registro_usado_fail(self):
        registros = [(0, 0.0, 0.0), (1, 1.0, math.inf), (2, 0.0, 1.0)]
        td, ok, msg, _ = converter(indexed_ms3(records=registros))
        self.addCleanup(td.cleanup)
        self.assertFalse(ok)
        self.assertIn("UV 1", msg)

    def test_06_position_index_invalido_em_registro_usado_fail(self):
        registros = [(0, 0.0, 0.0), (99, 1.0, 0.0), (2, 0.0, 1.0)]
        td, ok, msg, _ = converter(indexed_ms3(records=registros))
        self.addCleanup(td.cleanup)
        self.assertFalse(ok)
        self.assertIn("posição inexistente 99", msg)

    def test_07_payload_auxiliar_nao_usado_pass(self):
        auxiliar = bytes.fromhex("d0 d0 d0 ff d0 d0 d0 ff 64 00 3a 00")
        registros = [(0, 0.0, 0.0), (1, 1.0, 0.0), (2, 0.0, 1.0), auxiliar]
        td, ok, msg, obj = converter(indexed_ms3(records=registros))
        self.addCleanup(td.cleanup)
        self.assertTrue(ok, msg)
        self.assertNotIn("nan", obj.lower())
        self.assertEqual(len(linhas_obj(obj, "v ")), 3)

    def test_08_referencias_nao_continuas_sao_remapeadas(self):
        registros = [
            (0, 0.0, 0.0),
            bytes.fromhex("d0 d0 d0 ff d0 d0 d0 ff d0 d0 d0 ff"),
            (1, 0.5, 0.0),
            (0xFFFFFFFF, math.nan, math.nan),
            bytes.fromhex("64 00 69 00 64 00 3a 00 25 00 00 00"),
            (2, 0.0, 0.5),
        ]
        td, ok, msg, obj = converter(
            indexed_ms3(records=registros, faces=((0, 2, 5),)))
        self.addCleanup(td.cleanup)
        self.assertTrue(ok, msg)
        self.assertEqual(len(linhas_obj(obj, "v ")), 3)
        self.assertEqual(len(linhas_obj(obj, "vt ")), 3)
        self.assertIn("f 1/1/1 2/2/2 3/3/3", obj)
        self.assertNotIn("f 1/1/1 3/3/3 6/6/6", obj)

    def test_09_face_fora_do_declared_count_fail(self):
        td, ok, msg, _ = converter(indexed_ms3(faces=((0, 1, 3),)))
        self.addCleanup(td.cleanup)
        self.assertFalse(ok)
        self.assertIn("Face 0", msg)

    def test_10_interleaved_mantem_comportamento(self):
        td, ok, msg, obj = converter(ms3_bytes())
        self.addCleanup(td.cleanup)
        self.assertTrue(ok, msg)
        self.assertEqual(len(linhas_obj(obj, "v ")), 3)
        self.assertIn("f 1/1/1 2/2/2 3/3/3", obj)
        td2, ok2, msg2, _ = converter(ms3_bytes(nan=True))
        self.addCleanup(td2.cleanup)
        self.assertFalse(ok2)
        self.assertIn("Vértice 0 contém valores não finitos", msg2)

    def test_11_sfrif00038_equivalente_interleaved_pass(self):
        dados = ms3_bytes(indices=(0, 1, 2)) + bytes(42)
        td, ok, msg, _ = converter(dados)
        self.addCleanup(td.cleanup)
        self.assertTrue(ok, msg)

    def test_12_sfrif00039_equivalente_indexed_pass(self):
        registros = [(0, 0.1, 0.2), (1, 0.3, 0.4), (2, 0.5, 0.6),
                     (0, 0.7, 0.8), (1, 0.9, 1.0), (2, 0.2, 0.4)]
        faces = ((0, 2, 5), (0, 5, 1), (1, 5, 4), (1, 4, 3))
        td, ok, msg, obj = converter(
            indexed_ms3(records=registros, faces=faces, trailer=bytes(42)))
        self.addCleanup(td.cleanup)
        self.assertTrue(ok, msg)
        self.assertEqual(len(linhas_obj(obj, "v ")), 6)
        self.assertEqual(len(linhas_obj(obj, "f ")), 4)

    def test_13_sfrif00041_equivalente_interleaved_pass(self):
        td, ok, msg, obj = converter(ms3_bytes() + bytes(range(42)))
        self.addCleanup(td.cleanup)
        self.assertTrue(ok, msg)
        self.assertEqual(len(linhas_obj(obj, "vn ")), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)