# -*- coding: utf-8 -*-
"""Testes do Estágio 1 — dgvoodoo_config_engine (SOMENTE LEITURA).

Cobre os 25 itens obrigatórios + garantias (duplicatas preservadas,
desconhecidas preservadas, BOM preservado no modo lossless, nenhum import
do engine por módulos de produção).

NENHUM teste grava dgVoodoo.conf nem toca produção/cliente.
"""
import ast
import hashlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dgvoodoo_config_engine as eng  # noqa: E402
import dgvoodoo_config_schema as sch  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(ROOT, "third_party", "dgvoodoo2", "dgVoodoo.conf")

HASH_TEMPLATE = "3c7da2fac3eaad369df468e80c9ba9c4db632c419799b32bbc31279d10985801"
HASH_QUALIDADE = "ab8f2fcc04fa94d5c5b90d3858d725de83a5946073cc29fc7a0528ae102700dd"
BOM = b"\xef\xbb\xbf"


def _h(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _template_bytes() -> bytes:
    with open(TEMPLATE_PATH, "rb") as f:
        return f.read()


def _qualidade_bytes() -> bytes:
    """Fixture segura: conf Quality auditado (hash A) gerado em memória."""
    import dgvoodoo_service as svc
    return svc._gerar_conf_perfil(svc.PERFIL_QUALITY)


class TestTemplateAdotado(unittest.TestCase):
    """1, 3, 4, 12, 19 — template 2.87.4 adotado pelo projeto."""

    def test_01_template_e_2874_esperado(self):
        dados = _template_bytes()
        self.assertEqual(_h(dados), HASH_TEMPLATE)

    def test_12_utf8_sem_bom(self):
        dados = _template_bytes()
        self.assertFalse(dados.startswith(BOM))
        doc = eng.parse_bytes(dados, catalog=sch.CATALOG)
        self.assertFalse(doc.bom)
        self.assertEqual(doc.metadata().encoding, "utf-8")

    def test_19_round_trip_byte_a_byte_template(self):
        dados = _template_bytes()
        doc = eng.parse_bytes(dados, catalog=sch.CATALOG)
        self.assertEqual(doc.serialize_lossless(), dados)
        self.assertEqual(doc.sha256(), HASH_TEMPLATE)

    def test_04_94_chaves_ativas(self):
        doc = eng.parse_bytes(_template_bytes(), catalog=sch.CATALOG)
        self.assertEqual(doc.metadata().active_key_count, 94)
        self.assertEqual(sch.total_esperado(), 94)
        self.assertEqual(doc.metadata().section_count, 7)
        self.assertEqual(doc.sections(), [
            "General", "GeneralExt", "Glide", "GlideExt",
            "DirectX", "DirectXExt", "Debug",
        ])

    def test_94_chaves_sem_desconhecidas_no_template(self):
        doc = eng.parse_bytes(_template_bytes(), catalog=sch.CATALOG)
        diag = doc.diagnostic()
        self.assertEqual(diag.unknown_sections, [])
        self.assertEqual(diag.unknown_keys, [])
        self.assertFalse(doc.metadata().has_duplicates)


class TestGlobalVersion(unittest.TestCase):
    """3 — Version é global: section=None, key=Version; nunca [GLOBAL]."""

    def test_03_version_global(self):
        doc = eng.parse_bytes(_template_bytes(), catalog=sch.CATALOG)
        occ = doc.get(None, "Version")
        self.assertEqual(len(occ), 1)
        self.assertEqual(occ[0].section, None)
        self.assertEqual(occ[0].key, "Version")
        self.assertEqual(occ[0].value, "0x287")
        nodes = doc.origem_da_chave(None, "Version")
        self.assertTrue(nodes)
        self.assertIn("Version", nodes[0].raw)

    def test_nao_cria_secao_global_no_arquivo(self):
        doc = eng.parse_bytes(_template_bytes(), catalog=sch.CATALOG)
        out = doc.serialize_lossless()
        self.assertNotIn(b"[GLOBAL]", out)

    def test_consulta_get_padrao(self):
        doc = eng.parse_bytes(_template_bytes(), catalog=sch.CATALOG)
        # Valores literais do template adotado (V), não do overlay.
        self.assertEqual(doc.get("General", "OutputAPI")[0].value, "bestavailable")
        self.assertEqual(doc.get("General", "Adapters")[0].value, "all")
        self.assertEqual(doc.get("DirectX", "dgVoodooWatermark")[0].value, "true")
        self.assertEqual(doc.get("DirectX", "Antialiasing")[0].value, "appdriven")
        self.assertEqual(doc.get("General", "OutputAPI")[0].section, "General")


class TestQualityAuditado(unittest.TestCase):
    """2 — conf Quality auditado (amostra A) como fixture segura."""

    def test_02_qualidade_hash_e_estrutura(self):
        dados = _qualidade_bytes()
        self.assertEqual(_h(dados), HASH_QUALIDADE)
        doc = eng.parse_bytes(dados, catalog=sch.CATALOG)
        self.assertEqual(doc.metadata().active_key_count, 94)
        self.assertFalse(doc.bom)
        self.assertEqual(doc.serialize_lossless(), dados)
        self.assertEqual(doc.get("DirectX", "Antialiasing")[0].value, "4x")
        self.assertEqual(doc.get("DirectX", "dgVoodooWatermark")[0].value, "false")
        self.assertEqual(doc.get("DirectX", "Filtering")[0].value, "16")


class TestParsingDocumental(unittest.TestCase):
    """5-9, 12-18, 20 — itens documentais isolados."""

    def test_05_valor_vazio(self):
        dados = b"[General]\nChaveVazia =\n"
        doc = eng.parse_bytes(dados)
        occ = doc.get("General", "ChaveVazia")
        self.assertEqual(len(occ), 1)
        self.assertTrue(occ[0].value_empty)
        self.assertEqual(occ[0].value, "")

    def test_06_linha_comentada(self):
        dados = b";LogToFile = false\n"
        doc = eng.parse_bytes(dados)
        self.assertEqual(doc.lines[0].kind, eng.LineKind.COMMENT)
        self.assertEqual(doc.metadata().active_key_count, 0)

    def test_07_comentario_normal_preservado(self):
        dados = _template_bytes()
        doc = eng.parse_bytes(dados, catalog=sch.CATALOG)
        comentarios = [n for n in doc.lines if n.kind is eng.LineKind.COMMENT]
        self.assertTrue(len(comentarios) > 0)
        self.assertTrue(all(n.raw.lstrip().startswith(";") for n in comentarios))

    def test_08_secao_desconhecida(self):
        dados = b"[Foo]\nBar = 1\n"
        doc = eng.parse_bytes(dados, catalog=sch.CATALOG)
        self.assertEqual(doc.unknown_sections(), ["Foo"])
        self.assertIn("Seção desconhecida", doc.diagnostic().warnings[0])
        # preservada e round-trip idêntico
        self.assertEqual(doc.serialize_lossless(), dados)

    def test_09_chave_desconhecida(self):
        dados = b"[General]\nNovaChaveVendor = 99\n"
        doc = eng.parse_bytes(dados, catalog=sch.CATALOG)
        self.assertEqual(doc.unknown_keys(), [("General", "NovaChaveVendor", 1)])
        self.assertIn("Chave desconhecida", doc.diagnostic().warnings[0])
        self.assertEqual(doc.serialize_lossless(), dados)

    def test_09b_herdada_desconhecida_preservada_sem_rejeicao(self):
        """unknown_to_schema: valor herdado não é rejeitado nem alterado."""
        dados = b"[DirectX]\nFiltering = trilinear_extra_futuro\n"
        doc = eng.parse_bytes(dados, catalog=sch.CATALOG)
        occ = doc.get("DirectX", "Filtering")
        self.assertEqual(occ[0].value, "trilinear_extra_futuro")
        self.assertEqual(doc.serialize_lossless(), dados)

    def test_10_duplicata_mesma_secao(self):
        dados = b"[General]\nKey = 1\nKey = 2\n"
        doc = eng.parse_bytes(dados, catalog=None)
        self.assertEqual(doc.count("General", "Key"), 2)
        self.assertEqual([o.value for o in doc.get("General", "Key")], ["1", "2"])
        dups = doc.duplicates()
        self.assertEqual(dups[("General", "Key")], [1, 2])
        diag = doc.diagnostic()
        self.assertTrue(diag.duplicates)
        self.assertTrue(any("Duplicata" in w for w in diag.warnings))
        # não deduplica; não escolhe vencedora; round-trip íntegro
        self.assertEqual(doc.serialize_lossless(), dados)

    def test_11_mesma_chave_em_secoes_diferentes(self):
        doc = eng.parse_bytes(_template_bytes(), catalog=sch.CATALOG)
        # "Antialiasing" e "VideoCard" existem em Glide e DirectX como
        # campos distintos (identidade = seção + chave).
        self.assertEqual(doc.count("Glide", "Antialiasing"), 1)
        self.assertEqual(doc.count("DirectX", "Antialiasing"), 1)
        self.assertNotEqual(
            doc.get("Glide", "VideoCard")[0].value,  # voodoo_2
            doc.get("DirectX", "VideoCard")[0].value)  # internal3D
        self.assertEqual(doc.duplicates(), {})

    def test_13_bom_artificial_detectado_e_preservado(self):
        base = b"[General]\nOutputAPI = bestavailable\n"
        dados = BOM + base
        doc = eng.parse_bytes(dados)
        self.assertTrue(doc.bom)
        self.assertEqual(doc.metadata().bom, True)
        self.assertIn("BOM UTF-8 detectado", doc.diagnostic().warnings[0])
        self.assertEqual(doc.serialize_lossless(), dados)

    def test_14_crlf(self):
        dados = b"[General]\r\nA = 1\r\n"
        doc = eng.parse_bytes(dados)
        self.assertEqual(doc.metadata().newline_style, "crlf")
        self.assertEqual(doc.serialize_lossless(), dados)

    def test_15_lf(self):
        dados = b"[General]\nA = 1\n"
        doc = eng.parse_bytes(dados)
        self.assertEqual(doc.metadata().newline_style, "lf")
        self.assertEqual(doc.serialize_lossless(), dados)

    def test_16_com_newline_final(self):
        self.assertTrue(eng.parse_bytes(b"A = 1\n").metadata().has_final_newline)
        self.assertTrue(eng.parse_bytes(b"A = 1\r\n").metadata().has_final_newline)

    def test_17_sem_newline_final(self):
        doc = eng.parse_bytes(b"A = 1")
        self.assertFalse(doc.metadata().has_final_newline)
        self.assertEqual(doc.serialize_lossless(), b"A = 1")

    def test_18_espacos_antes_depois_igual(self):
        dados = b"  Chave  =  valor  \n"
        doc = eng.parse_bytes(dados)
        no = doc.lines[0]
        self.assertEqual(no.kind, eng.LineKind.KEYVALUE)
        self.assertEqual(no.key, "Chave")
        self.assertEqual(no.value, "valor")
        self.assertEqual(no.raw, "  Chave  =  valor  ")
        self.assertEqual(doc.serialize_lossless(), dados)

    def test_20_unicode_invalido_explicito(self):
        dados = b"\xff\xfe\x00[General]\x00"
        with self.assertRaises(UnicodeDecodeError):
            eng.parse_bytes(dados)


class TestDiff(unittest.TestCase):
    """21-24 — diff não destrutivo."""

    def test_21_diff_valor(self):
        a = b"[General]\nOutputAPI = bestavailable\n"
        b = b"[General]\nOutputAPI = d3d11_fl11_0\n"
        r = eng.diff_documents(a, b)
        self.assertFalse(r.same)
        self.assertIn("valor", r.categories)

    def test_22_diff_somente_formatacao(self):
        a = b"[General]\nOutputAPI = bestavailable\n"
        b = b"[General]\n  OutputAPI   =   bestavailable  \n"
        r = eng.diff_documents(a, b)
        self.assertFalse(r.same)
        self.assertIn("formatting", r.categories)
        self.assertNotIn("valor", r.categories)
        self.assertNotIn("secao", r.categories)
        self.assertNotIn("chave", r.categories)

    def test_23_diff_bom(self):
        a = b"[General]\nOutputAPI = bestavailable\n"
        b = BOM + a
        r = eng.diff_documents(a, b)
        self.assertFalse(r.same)
        self.assertIn("bom", r.categories)
        self.assertIn("bytes", r.categories)

    def test_24_diff_newline(self):
        a = b"[General]\nA = 1\n"
        b = b"[General]\r\nA = 1\r\n"
        r = eng.diff_documents(a, b)
        self.assertFalse(r.same)
        self.assertIn("newline", r.categories)

    def test_diff_identico(self):
        dados = _template_bytes()
        r = eng.diff_documents(dados, dados)
        self.assertTrue(r.same)
        self.assertEqual(r.categories, [])

    def test_diff_comentario(self):
        a = b";abc\n[General]\nA = 1\n"
        b = b";xyz\n[General]\nA = 1\n"
        r = eng.diff_documents(a, b)
        self.assertIn("comentario", r.categories)

    def test_diff_linha_desconhecida(self):
        a = b"[General]\nA = 1\n"
        b = b"[General]\nA = 1\nlinha totalmente estranha\n"
        r = eng.diff_documents(a, b)
        self.assertIn("linha_desconhecida", r.categories)


class TestMetadadosEOrigem(unittest.TestCase):
    def test_metadata_template(self):
        dados = _template_bytes()
        doc = eng.parse_bytes(dados, catalog=sch.CATALOG)
        m = doc.metadata()
        self.assertEqual(m.sha256, HASH_TEMPLATE)
        self.assertEqual(m.size, len(dados))
        self.assertEqual(m.first_bytes, dados[:8].hex(" ").upper())
        self.assertEqual(m.line_count, len(doc.lines))
        self.assertEqual(m.section_count, 7)
        self.assertEqual(m.active_key_count, 94)
        self.assertFalse(m.bom)
        self.assertEqual(m.newline_style, "crlf")
        self.assertFalse(m.has_final_newline)
        self.assertFalse(m.has_duplicates)

    def test_origem_documental_template(self):
        doc = eng.parse_bytes(_template_bytes(), catalog=sch.CATALOG)
        no = doc.origem_da_chave("DirectX", "dgVoodooWatermark")[0]
        self.assertIn("dgVoodooWatermark", no.raw)
        self.assertEqual(no.section, "DirectX")
        no_global = doc.origem_da_chave(None, "Version")[0]
        self.assertEqual(no_global.is_global, True)

    def test_index_sem_perda_de_duplicatas(self):
        dados = b"[General]\nA = 1\nA = 2\n"
        doc = eng.parse_bytes(dados)
        self.assertEqual(len(doc.get("General", "A")), 2)
        self.assertEqual(doc.count("General", "A"), 2)


class TestSchemaDescritivo(unittest.TestCase):
    def test_describe_fixas_e_perfil(self):
        meta = sch.describe("DirectX", "dgVoodooWatermark")
        self.assertEqual(meta.regra_aika, "fixo:false")
        self.assertIn("trilinear", sch.describe("DirectX", "Filtering").perfil)
        self.assertTrue(sch.is_known(None, "Version"))
        self.assertFalse(sch.is_known("General", "Inexistente"))
        self.assertIsNone(sch.describe("General", "Inexistente"))

    def test_fixas_overlay_sao_12_fora_version(self):
        fixas_sem_version = {(s, k) for (s, k) in sch.FIXAS if s is not None}
        self.assertEqual(len(fixas_sem_version), 12)
        self.assertEqual(len(sch.PERFIS), 2)


class TestSomenteLeitura(unittest.TestCase):
    """25 + garantia de não-integração."""

    def test_25_nenhuma_funcao_escreve_em_disco(self):
        with tempfile.TemporaryDirectory() as td:
            antigo = os.getcwd()
            os.chdir(td)
            try:
                dados = _template_bytes()
                doc = eng.parse_bytes(dados, catalog=sch.CATALOG)
                doc.serialize_lossless()
                doc.metadata()
                doc.diagnostic()
                eng.diff_documents(dados, BOM + dados)
                eng.parse_bytes(b"[General]\r\nA = 1\r\n")
                self.assertEqual(os.listdir(td), [])
            finally:
                os.chdir(antigo)

    def test_pagina_main_hardware_detector_nao_importam_engine(self):
        # dgvoodoo_service.py é coberto pelo Stage 5A (integração deliberada
        # apenas no caminho de aplicação de perfil, com parity guard).
        for nome in ("dgvoodoo_page.py", "main.py",
                     "hardware_detector.py"):
            with open(os.path.join(ROOT, nome), encoding="utf-8") as f:
                fonte = f.read()
            self.assertNotIn("dgvoodoo_config_engine", fonte,
                             f"{nome} não pode importar o engine")
            self.assertNotIn("dgvoodoo_config_schema", fonte,
                             f"{nome} não pode importar o schema")


if __name__ == "__main__":
    unittest.main()
