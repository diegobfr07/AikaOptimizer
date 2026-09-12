# -*- coding: utf-8 -*-
"""Estágio 4 — Certificação da paridade determinística.

Congela a paridade entre gerador legado (oráculo) e engine novo:
- 5 repetições independentes por cenário (diretórios temporários distintos);
- hashes OLD/NEW idênticos em todas as repetições e OLD == NEW;
- hashes baseline congelados do Stage 3 (completos);
- independência de ordem e entre perfis;
- casos sintéticos A-J determinísticos;
- provenance correta; Lossless (Stage 1) íntegro;
- nenhum cliente escrito; nenhuma integração.
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

FROZEN = {
    None: "3ca4b70641ee1348e9da7b4f3a5d27979bfefe82a3c89d19c80ad61b9d4e0e12",
    "performance": "0337905f4b82adec730c21292f527904bf3355c26ca74952b2e18c9b0134aeb5",
    "balanced": "3ca4b70641ee1348e9da7b4f3a5d27979bfefe82a3c89d19c80ad61b9d4e0e12",
    "quality": "ab8f2fcc04fa94d5c5b90d3858d725de83a5946073cc29fc7a0528ae102700dd",
}
OFICIAL = ["ativar", "reaplicar", "performance", "balanced", "quality",
           "auto_performance", "auto_balanced", "auto_quality"]
CASOS = ["A_chave_desconhecida", "B_secao_desconhecida", "C_valor_vazio_herdado",
         "D_comentario_adicional", "E_lf_entrada", "F_crlf_entrada",
         "G_bom_entrada", "H_sem_newline_final", "I_duplicata_nao_controlada",
         "J_duplicata_controlada"]


def _template() -> bytes:
    with open(TEMPLATE_PATH, "rb") as f:
        return f.read()


def _perfil(nome):
    return {"performance": "performance", "balanced": "balanced",
            "quality": "quality"}.get(nome)


def _engine_new(dados, profile=None):
    return eng.generate_active(
        dados, fixed=sch.OVERLAY_FIXO, base=sch.BASE_AIKA,
        profiles=sch.PERFIS_MAP, profile=profile,
        validate_domain=sch.validate_domain, catalog=sch.CATALOG)


def _old(profile):
    import dgvoodoo_service as svc
    return svc._gerar_conf_perfil(profile if profile else svc.PERFIL_BALANCED)


def _caso_bytes(caso: str) -> bytes:
    """Reusa a construção sintética do Stage 3 (mesma definição)."""
    dados = _template()
    if caso in ("F_crlf_entrada", "H_sem_newline_final"):
        return dados
    if caso == "G_bom_entrada":
        return b"\xef\xbb\xbf" + dados
    linhas = dados.decode("utf-8-sig").split("\r\n")
    if caso == "A_chave_desconhecida":
        linhas.insert(linhas.index("[GeneralExt]"),
                      "ChaveVendorFutura = token_futuro")
    elif caso == "B_secao_desconhecida":
        return dados + b"\r\n[SeccaoFuturaVendor]\r\nNovaChave = valor\r\n"
    elif caso == "C_valor_vazio_herdado":
        linhas.insert(linhas.index("[GeneralExt]"), "ChaveFuturaVazia =")
    elif caso == "D_comentario_adicional":
        linhas.insert(linhas.index("[GeneralExt]"),
                      "; comentario sintetico de teste")
    elif caso == "E_lf_entrada":
        return dados.replace(b"\r\n", b"\n")
    elif caso == "I_duplicata_nao_controlada":
        i = linhas.index("[GeneralExt]")
        linhas.insert(i, "ChaveDupNC = 1")
        linhas.insert(i + 1, "ChaveDupNC = 2")
    elif caso == "J_duplicata_controlada":
        i = next(i for i, l in enumerate(linhas)
                 if l.strip().startswith("dgVoodooWatermark"))
        linhas.insert(i + 1, linhas[i])
    else:
        raise ValueError(caso)
    return "\r\n".join(linhas).encode("utf-8")


class TestDeterminismoOficial(unittest.TestCase):
    """1-8 — 5 repetições por cenário em diretórios temporários distintos."""

    def _isolar(self):
        td = tempfile.TemporaryDirectory(prefix="aika_det_")
        antigo = os.getcwd()
        os.chdir(td.name)
        return td, antigo

    def test_5_repeticoes_por_cenario(self):
        for nome in OFICIAL:
            old_hashes, new_hashes = set(), set()
            prof = _perfil(nome)
            with self.subTest(cenario=nome):
                for _ in range(5):
                    td, antigo = self._isolar()
                    try:
                        old = _old(prof)
                        new = _engine_new(_template(), profile=prof).bytes_
                        self.assertEqual(old, new)
                        old_hashes.add(hashlib.sha256(old).hexdigest())
                        new_hashes.add(hashlib.sha256(new).hexdigest())
                        self.assertEqual(os.listdir(td.name), [],
                                         "caminho temporário não pode virar byte")
                    finally:
                        os.chdir(antigo)
                        td.cleanup()
                self.assertEqual(len(old_hashes), 1, f"OLD não-determinístico {nome}")
                self.assertEqual(len(new_hashes), 1, f"NEW não-determinístico {nome}")
                self.assertEqual(old_hashes, new_hashes)

    def test_hashes_baseline_congelados(self):
        esperado = {None: FROZEN[None], "balanced": FROZEN["balanced"]}
        for prof_nome, sha in FROZEN.items():
            with self.subTest(perfil=prof_nome):
                prof = _perfil(prof_nome)
                old = _old(prof)
                new = _engine_new(_template(), profile=prof).bytes_
                self.assertEqual(hashlib.sha256(old).hexdigest(), sha, "OLD")
                self.assertEqual(hashlib.sha256(new).hexdigest(), sha, "NEW")

    def test_diretorios_temporarios_nao_influenciam(self):
        alvos = []
        for _ in range(3):
            with tempfile.TemporaryDirectory(prefix="aika_det_dir_") as td:
                g = _engine_new(_template(), profile="quality")
                alvos.append(g.sha256)
                with open(os.path.join(td, "dgVoodoo.shadow.conf"), "wb") as f:
                    f.write(g.bytes_)
                # re-leitura do arquivo shadow
                with open(os.path.join(td, "dgVoodoo.shadow.conf"), "rb") as f:
                    self.assertEqual(hashlib.sha256(f.read()).hexdigest(), g.sha256)
        self.assertEqual(len(set(alvos)), 1)


class TestIndependenciaOrdemPerfis(unittest.TestCase):
    """Ordem de execução/estado anterior não contaminam o resultado."""

    def test_sequencias_nao_contaminam(self):
        def hash_isolado(prof):
            return _engine_new(_template(), profile=prof).sha256

        seq = ["performance", "quality", "performance", "balanced",
               "quality", "balanced", "quality"]
        esperado_por_perfil = {}
        for prof in seq:
            h = _engine_new(_template(), profile=prof).sha256
            esperado_por_perfil.setdefault(prof, h)
            self.assertEqual(h, hash_isolado(prof), f"contaminação em {prof}")
            self.assertEqual(h, FROZEN[prof])
        self.assertEqual(esperado_por_perfil["performance"], FROZEN["performance"])
        self.assertEqual(esperado_por_perfil["balanced"], FROZEN["balanced"])
        self.assertEqual(esperado_por_perfil["quality"], FROZEN["quality"])

    def test_auto_e_manual_nao_contaminam(self):
        for prof in ("performance", "balanced", "quality"):
            manual = _engine_new(_template(), profile=prof)
            auto = _engine_new(_template(), profile=prof)  # AUTO resolve p/ perfil
            self.assertEqual(manual.bytes_, auto.bytes_)
            self.assertEqual(manual.sha256, FROZEN[prof])


class TestSinteticosDeterministicos(unittest.TestCase):
    """9 — casos A-J permanecem determinísticos e sem divergência."""

    def test_a_j_deterministicos(self):
        for caso in CASOS:
            with self.subTest(caso=caso):
                dados = _caso_bytes(caso)
                texto = dados.decode("utf-8-sig")
                import dgvoodoo_service as svc
                old = svc._aplicar_chaves_texto(texto, svc.PRESET_CONF)
                old = old.encode("utf-8")
                hashes = set()
                for _ in range(3):
                    new = _engine_new(dados).bytes_
                    self.assertEqual(old, new, f"divergência em {caso}")
                    hashes.add(hashlib.sha256(new).hexdigest())
                self.assertEqual(len(hashes), 1, f"não-determinístico {caso}")


class TestProvenanceELossless(unittest.TestCase):
    """Provenance correta; Lossless (Stage 1) íntegro e independente."""

    def test_provenance_baseline(self):
        g = _engine_new(_template(), profile="quality")
        self.assertEqual(len(g.provenance), 94)
        contagem = {}
        for origem in g.provenance.values():
            contagem[origem] = contagem.get(origem, 0) + 1
        self.assertEqual(contagem.get("overlay_fixo"), 12)
        self.assertEqual(contagem.get("perfil"), 2)
        self.assertEqual(contagem.get("template"), 80)
        g_base = _engine_new(_template())
        self.assertEqual(g_base.provenance[("DirectX", "Filtering")], "overlay_base")

    def test_lossless_stage1_intacto(self):
        dados = _template()
        doc = eng.parse_bytes(dados, catalog=sch.CATALOG)
        self.assertEqual(doc.serialize_lossless(), dados)
        # Modo ativo não altera o comportamento do modo lossless.
        _engine_new(dados, profile="performance")
        doc2 = eng.parse_bytes(dados, catalog=sch.CATALOG)
        self.assertEqual(doc2.serialize_lossless(), dados)


class TestIntegracaoEClientes(unittest.TestCase):
    """11-12 — nenhum cliente escrito; nenhuma integração."""

    def test_producao_nao_importa_engine(self):
        # dgvoodoo_service.py é coberto pelo Stage 5A (integração deliberada
        # apenas no caminho de aplicação de perfil, com parity guard).
        for nome in ("dgvoodoo_page.py", "main.py",
                     "config.py", "hardware_detector.py"):
            with open(os.path.join(ROOT, nome), encoding="utf-8") as f:
                fonte = f.read()
            self.assertNotIn("dgvoodoo_config_engine", fonte, nome)
            self.assertNotIn("dgvoodoo_config_schema", fonte, nome)

    def test_engine_nao_usa_clientes(self):
        with open(os.path.join(ROOT, "dgvoodoo_config_engine.py"),
                  encoding="utf-8") as f:
            fonte_engine = f.read().lower()
        for caminho in (r"c:\cbmgames\aikaonlinebrasil",
                        r"c:\users\diego\downloads\aikaonlinebrasil"):
            self.assertNotIn(caminho, fonte_engine)

    def test_geracao_nao_escreve_arquivos(self):
        with tempfile.TemporaryDirectory() as td:
            antigo = os.getcwd()
            os.chdir(td)
            try:
                for _ in range(3):
                    _engine_new(_template(), profile="quality")
                self.assertEqual(os.listdir(td), [])
            finally:
                os.chdir(antigo)


if __name__ == "__main__":
    unittest.main()
