# -*- coding: utf-8 -*-
"""Testes do Estágio 2 — geração shadow (Active AIKA Serialization).

O gerador atual (dgvoodoo_service) é usado SOMENTE como referência OLD nos
testes; nunca é modificado. Engine gera em memória (NEW) e a paridade
OLD==NEW é o objetivo. NENHUM arquivo é gravado no cliente/jogo.
"""
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


def _template() -> bytes:
    with open(TEMPLATE_PATH, "rb") as f:
        return f.read()


def _old(profile):
    """Referência OLD: gerador atual (em memória, sem gravar nada)."""
    import dgvoodoo_service as svc
    return svc._gerar_conf_perfil(profile if profile else svc.PERFIL_BALANCED)


def _new(profile=None):
    return eng.generate_active(
        _template(), fixed=sch.OVERLAY_FIXO, base=sch.BASE_AIKA,
        profiles=sch.PERFIS_MAP, profile=profile,
        validate_domain=sch.validate_domain, catalog=sch.CATALOG)


def _minimal_com_requisitos(extra="") -> bytes:
    """Template mínimo contendo as 12 invariantes + extras opcionais."""
    texto = (
        "Version                              = 0x287\r\n"
        "\r\n"
        "[General]\r\n"
        "OutputAPI                            = bestavailable\r\n"
        "Adapters                             = all\r\n"
        "FullScreenMode                       = true\r\n"
        "DisableScreenSaver                   = false\r\n"
        + extra +
        "\r\n"
        "[DirectX]\r\n"
        "DisableAndPassThru                   = false\r\n"
        "VideoCard                            = internal3D\r\n"
        "VRAM                                 = 256\r\n"
        "KeepFilterIfPointSampled             = false\r\n"
        "AppControlledScreenMode              = true\r\n"
        "DisableAltEnterToToggleScreenMode    = true\r\n"
        "FastVideoMemoryAccess                = false\r\n"
        "dgVoodooWatermark                    = true\r\n"
    )
    return texto.encode("utf-8")


class TestActiveBasico(unittest.TestCase):
    """1-3 — Modo B: sem BOM, CRLF, mesma política de newline final."""

    def test_01_active_sem_bom(self):
        g = _new()
        self.assertFalse(g.bytes_.startswith(b"\xef\xbb\xbf"))
        doc = eng.parse_bytes(g.bytes_)
        self.assertFalse(doc.bom)

    def test_02_crlf(self):
        g = _new(profile="quality")
        doc = eng.parse_bytes(g.bytes_)
        self.assertEqual(doc.metadata().newline_style, "crlf")

    def test_03_mesma_politica_newline_final(self):
        g = _new()
        ref = eng.parse_bytes(_old(None))
        self.assertEqual(eng.parse_bytes(g.bytes_).metadata().has_final_newline,
                         ref.metadata().has_final_newline)
        self.assertFalse(ref.metadata().has_final_newline)


class TestInvariantes(unittest.TestCase):
    """4 — 12 invariantes presentes no efetivo."""

    def test_04_12_invariantes(self):
        g = _new()
        doc = eng.parse_bytes(g.bytes_)
        total = 0
        for secao, chaves in sch.OVERLAY_FIXO.items():
            for chave, valor in chaves.items():
                self.assertEqual(doc.get(secao, chave)[0].value, valor,
                                 f"{secao}.{chave}")
                total += 1
        self.assertEqual(total, 12)


class TestCenariosPerfil(unittest.TestCase):
    """5-12 — Perfis, Ativar, Reaplicar e AUTO (OLD == NEW)."""

    def _assert_par(self, profile, old_profile):
        old = _old(old_profile)
        g = _new(profile=profile)
        self.assertEqual(g.bytes_, old, f"OLD!=NEW para {profile}")

    def test_05_performance(self):
        self._assert_par("performance", "performance")
        self.assertEqual(eng.parse_bytes(_new("performance").bytes_)
                         .get("DirectX", "Antialiasing")[0].value, "appdriven")
        self.assertEqual(eng.parse_bytes(_new("performance").bytes_)
                         .get("DirectX", "Filtering")[0].value, "trilinear")

    def test_06_balanced(self):
        self._assert_par("balanced", "balanced")
        d = eng.parse_bytes(_new("balanced").bytes_)
        self.assertEqual(d.get("DirectX", "Antialiasing")[0].value, "2x")
        self.assertEqual(d.get("DirectX", "Filtering")[0].value, "16")

    def test_07_quality(self):
        self._assert_par("quality", "quality")
        d = eng.parse_bytes(_new("quality").bytes_)
        self.assertEqual(d.get("DirectX", "Antialiasing")[0].value, "4x")
        self.assertEqual(d.get("DirectX", "Filtering")[0].value, "16")

    def test_08_ativar(self):
        # Ativar = base Aika Recomendado/Balanced (AA 2x, Filtering 16).
        self._assert_par(None, None)
        d = eng.parse_bytes(_new(None).bytes_)
        self.assertEqual(d.get("DirectX", "Antialiasing")[0].value, "2x")
        self.assertEqual(d.get("DirectX", "Filtering")[0].value, "16")

    def test_09_reaplicar(self):
        # Reaplicar reconstrói a base; não usa o último perfil.
        self.assertEqual(_new(None).bytes_, _new(None).bytes_)
        self._assert_par(None, None)

    def test_10_auto_performance(self):
        self._assert_par("performance", "performance")

    def test_11_auto_balanced(self):
        self._assert_par("balanced", "balanced")

    def test_12_auto_quality(self):
        self._assert_par("quality", "quality")

    def test_13_nenhum_token_auto(self):
        for prof in ("performance", "balanced", "quality"):
            texto = _new(profile=prof).bytes_.decode("utf-8")
            linhas_auto = [l for l in texto.splitlines()
                           if l.strip().lower().startswith("auto")]
            self.assertEqual(linhas_auto, [])
            self.assertNotIn("resolved_profile", texto)
            self.assertNotIn("preset", texto)
        # AUTO não é perfil do engine
        with self.assertRaises(ValueError):
            _new(profile="auto")


class TestParidadeOficial(unittest.TestCase):
    """30 — matriz OLD × NEW para os 8 cenários + integridade estrutural."""

    def test_30_matriz_old_new(self):
        cenarios = {
            "ativar_inicial": None,
            "reaplicar": None,
            "performance": "performance",
            "balanced": "balanced",
            "quality": "quality",
            "auto_performance": "performance",
            "auto_balanced": "balanced",
            "auto_quality": "quality",
        }
        for nome, prof in cenarios.items():
            old = _old(prof)
            g = _new(profile=prof)
            self.assertEqual(g.bytes_, old, f"bytes {nome}")
            self.assertEqual(g.sha256, hashlib.sha256(old).hexdigest(), nome)
            self.assertEqual(g.size, len(old), nome)
            self.assertFalse(old.startswith(b"\xef\xbb\xbf"), nome)
            rep = eng.diff_documents(old, g.bytes_)
            self.assertTrue(rep.same, f"diff {nome}: {rep.categories}")

    def test_14_template_intacto(self):
        antes = hashlib.sha256(_template()).hexdigest()
        for prof in (None, "performance", "balanced", "quality"):
            _new(profile=prof)
        with open(TEMPLATE_PATH, "rb") as f:
            conteudo = f.read()
        self.assertEqual(hashlib.sha256(conteudo).hexdigest(), antes)
        self.assertEqual(hashlib.sha256(conteudo).hexdigest(), HASH_TEMPLATE)


class TestErrosEPreservacao(unittest.TestCase):
    """15-22 — erros bloqueantes e preservação."""

    def _gen(self, dados, fixed=None, profile=None):
        return eng.generate_active(
            dados, fixed=fixed or sch.OVERLAY_FIXO, base=sch.BASE_AIKA,
            profiles=sch.PERFIS_MAP, profile=profile,
            validate_domain=sch.validate_domain, catalog=sch.CATALOG)

    def test_15_chave_fixa_ausente_erro(self):
        texto = _template().decode("utf-8")
        sem = "\r\n".join(l for l in texto.splitlines()
                          if not l.strip().startswith("dgVoodooWatermark"))
        with self.assertRaises(ValueError) as ctx:
            self._gen(sem.encode("utf-8"))
        self.assertIn("obrigatória ausente", str(ctx.exception))
        self.assertIn("dgVoodooWatermark", str(ctx.exception))

    def test_16_perfil_invalido_erro(self):
        with self.assertRaises(ValueError):
            self._gen(_template(), profile="ultra")

    def test_17_overlay_fora_de_dominio_erro(self):
        fixed_bad = {"General": {"FullScreenMode": "talvez"}}
        # domínio do FullScreenMode é comprovado (booleano) -> bloqueia
        with self.assertRaises(ValueError) as ctx:
            self._gen(_template(), fixed=fixed_bad)
        self.assertIn("fora de domínio", str(ctx.exception))

    def test_18_herdada_desconhecida_preservada(self):
        dados = _template().replace(
            b"\r\nKeepWindowAspectRatio",
            b"\r\nNovaChaveVendorFutura = abc123\r\nKeepWindowAspectRatio")
        g = self._gen(dados)
        doc = eng.parse_bytes(g.bytes_, catalog=sch.CATALOG)
        self.assertEqual(doc.get("General", "NovaChaveVendorFutura")[0].value,
                         "abc123")
        self.assertTrue(any("unknown_to_schema" in w for w in g.warnings))

    def test_19_comentario_nao_alvo_preservado(self):
        dados = _template()
        antes = sum(1 for n in eng.parse_bytes(dados).lines
                    if n.kind is eng.LineKind.COMMENT)
        for prof in (None, "performance", "balanced", "quality"):
            g = self._gen(dados, profile=prof)
            doc = eng.parse_bytes(g.bytes_)
            depois = sum(1 for n in doc.lines if n.kind is eng.LineKind.COMMENT)
            self.assertEqual(depois, antes)

    def test_20_ordem_preservada(self):
        dados = _template()
        doc_t = eng.parse_bytes(dados)
        for prof in (None, "performance", "quality"):
            doc_g = eng.parse_bytes(self._gen(dados, profile=prof).bytes_)
            self.assertEqual(doc_g.keys(), doc_t.keys())
            self.assertEqual(doc_g.sections(), doc_t.sections())

    def test_21_valores_vazios_preservados(self):
        dados = _minimal_com_requisitos(extra="CampoVazio =\r\n")
        g = self._gen(dados)
        doc = eng.parse_bytes(g.bytes_)
        self.assertTrue(doc.get("General", "CampoVazio")[0].value_empty)
        self.assertEqual(doc.serialize_lossless().decode("utf-8")
                         .count("CampoVazio =\r\n"), 1)

    def test_22_duplicatas_nao_deduplicadas(self):
        dados = _minimal_com_requisitos(extra="Duplicada = 1\r\nDuplicada = 2\r\n")
        g = self._gen(dados)
        doc = eng.parse_bytes(g.bytes_)
        self.assertEqual(doc.count("General", "Duplicada"), 2)
        self.assertTrue(doc.duplicates())


class TestSomenteLeituraShadow(unittest.TestCase):
    """23-26 — memória/tempfile; sem escrita em cliente; sem import."""

    def test_23_output_em_memoria_por_padrao(self):
        with tempfile.TemporaryDirectory() as td:
            antigo = os.getcwd()
            os.chdir(td)
            try:
                _new()
                _new(profile="quality")
                self.assertEqual(os.listdir(td), [])
            finally:
                os.chdir(antigo)

    def test_24_materializacao_somente_tempfile(self):
        with tempfile.TemporaryDirectory(prefix="shadow_") as td:
            alvo = os.path.join(td, "dgVoodoo.shadow.conf")
            eng.write_shadow(_new(profile="quality"), alvo)
            with open(alvo, "rb") as f:
                self.assertEqual(f.read(), _new(profile="quality").bytes_)
            self.assertEqual(sorted(os.listdir(td)), ["dgVoodoo.shadow.conf"])

    def test_25_engine_nao_usa_cliente_aika(self):
        for caminho_cliente in (r"C:\CBMgames\AikaOnlineBrasil",
                                r"C:\Users\diego\Downloads\AikaOnlineBrasil"):
            with open(os.path.join(ROOT, "dgvoodoo_config_engine.py"),
                      encoding="utf-8") as f:
                self.assertNotIn(caminho_cliente.lower(), f.read().lower())

    def test_26_producao_nao_importa_engine(self):
        # dgvoodoo_service.py é coberto pelo Stage 5A (integração deliberada
        # apenas no caminho de aplicação de perfil, com parity guard).
        for nome in ("dgvoodoo_page.py", "main.py",
                     "hardware_detector.py", "config.py"):
            with open(os.path.join(ROOT, nome), encoding="utf-8") as f:
                fonte = f.read()
            self.assertNotIn("dgvoodoo_config_engine", fonte, nome)
            self.assertNotIn("dgvoodoo_config_schema", fonte, nome)


class TestProvenance(unittest.TestCase):
    """27-29 — provenance validada contra a baseline documental."""

    def test_27_doze_fixas_overlay_fixo(self):
        g = _new()
        fixas = {(s, k) for s, ch in sch.OVERLAY_FIXO.items() for k in ch}
        for ident in fixas:
            self.assertEqual(g.provenance[ident], "overlay_fixo", str(ident))
        self.assertEqual(
            sum(1 for v in g.provenance.values() if v == "overlay_fixo"), 12)

    def test_28_perfil_e_base_filtering_antialiasing(self):
        g_base = _new(None)
        self.assertEqual(g_base.provenance[("DirectX", "Filtering")],
                         "overlay_base")
        self.assertEqual(g_base.provenance[("DirectX", "Antialiasing")],
                         "overlay_base")
        for prof in ("performance", "balanced", "quality"):
            g = _new(profile=prof)
            self.assertEqual(g.provenance[("DirectX", "Filtering")], "perfil")
            self.assertEqual(g.provenance[("DirectX", "Antialiasing")], "perfil")

    def test_29_oitenta_herdadas_template(self):
        g = _new(profile="quality")
        herdadas = [ident for ident, origem in g.provenance.items()
                    if origem == "template"]
        self.assertEqual(len(herdadas), 80)
        self.assertEqual(len(g.provenance), 94)


if __name__ == "__main__":
    unittest.main()
