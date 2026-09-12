# -*- coding: utf-8 -*-
"""Estágio 3 — Prova formal/automatizada de paridade (gerador legado x engine).

- O gerador legado é usado SOMENTE como ORÁCULO de teste (helpers isolados
  em memória ou _gerar_conf_perfil do serviço, que NUNCA é alterado).
- 8 cenários oficiais: BYTE_EQUAL e SEMANTIC_EQUAL obrigatórios (8/8).
- Casos sintéticos (em memória) A–J: cobrem robustez comportamental;
  divergências são classificadas/registradas (nenhuma esperada).
- Provenance validada contra baseline documental (94 chaves).
- Nada escreve em cliente Aika; template/DLL/estado não são tocados.
"""
import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dgvoodoo_config_engine as eng  # noqa: E402
import dgvoodoo_config_schema as sch  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(ROOT, "third_party", "dgvoodoo2", "dgVoodoo.conf")

OFICIAL = {
    "ativar_inicial": None,
    "reaplicar": None,
    "performance": "performance",
    "balanced": "balanced",
    "quality": "quality",
    "auto_performance": "performance",
    "auto_balanced": "balanced",
    "auto_quality": "quality",
}


def _template() -> bytes:
    with open(TEMPLATE_PATH, "rb") as f:
        return f.read()


def _oraculo_oficial(profile) -> bytes:
    """Oráculo legado oficial (mesma entrada = template em disco)."""
    import dgvoodoo_service as svc
    return svc._gerar_conf_perfil(profile if profile else svc.PERFIL_BALANCED)


def _legacy_apply_texto(texto: str, profile=None) -> bytes:
    """Oráculo legado sobre texto arbitrário (sem tocar disco)."""
    import dgvoodoo_service as svc
    res = svc._aplicar_chaves_texto(texto, svc.PRESET_CONF)
    if profile:
        res = svc._aplicar_chaves_texto(res, svc.PERFIS_CONF[profile])
    return res.encode("utf-8")


def _engine_new(dados, profile=None):
    return eng.generate_active(
        dados, fixed=sch.OVERLAY_FIXO, base=sch.BASE_AIKA,
        profiles=sch.PERFIS_MAP, profile=profile,
        validate_domain=sch.validate_domain, catalog=sch.CATALOG)


def _medir(dados: bytes) -> dict:
    doc = eng.parse_bytes(dados, catalog=sch.CATALOG)
    m = doc.metadata()
    return {
        "sha256": hashlib.sha256(dados).hexdigest(),
        "size": len(dados),
        "bom": dados.startswith(b"\xef\xbb\xbf"),
        "encoding": "utf-8",
        "newline_style": m.newline_style,
        "final_newline": m.has_final_newline,
        "sections": m.section_count,
        "active_keys": m.active_key_count,
        "keys_order": doc.keys(),
        "comments": sum(1 for n in doc.lines if n.kind is eng.LineKind.COMMENT),
        "empty_values": sum(1 for o in doc.occurrences() if o.value_empty),
        "unknown_sections": doc.unknown_sections(),
        "unknown_keys": doc.unknown_keys(),
        "duplicates": dict(doc.duplicates()),
    }


def matriz_paridade():
    """Matriz estruturada (reproduzível; sem tocar em clientes)."""
    linhas = []
    for nome, prof in OFICIAL.items():
        old = _oraculo_oficial(prof)
        new = _engine_new(_template(), profile=prof)
        rep = eng.diff_documents(old, new.bytes_)
        mo, mn = _medir(old), _medir(new.bytes_)
        linha = {
            "cenario": nome,
            "OLD_SHA256": mo["sha256"],
            "NEW_SHA256": mn["sha256"],
            "OLD_SIZE": mo["size"],
            "NEW_SIZE": mn["size"],
            "BYTE_EQUAL": old == new.bytes_,
            "SEMANTIC_EQUAL": rep.same,
            "diff_categories": rep.categories,
            "OLD_bom": mo["bom"], "NEW_bom": mn["bom"],
            "OLD_newline": mo["newline_style"], "NEW_newline": mn["newline_style"],
            "OLD_final_nl": mo["final_newline"], "NEW_final_nl": mn["final_newline"],
            "OLD_sections": mo["sections"], "NEW_sections": mn["sections"],
            "OLD_keys": mo["active_keys"], "NEW_keys": mn["active_keys"],
            "resultado": "PASS" if (old == new.bytes_ and rep.same) else "FAIL",
        }
        linhas.append(linha)
    return linhas


class TestMatrizOficial(unittest.TestCase):
    """5-8 — matriz formal 8/8: byte-level e semântico."""

    def test_08_cenarios_byte_e_semantico(self):
        matriz = matriz_paridade()
        self.assertEqual(len(matriz), 8)
        for linha in matriz:
            with self.subTest(cenario=linha["cenario"]):
                self.assertTrue(linha["BYTE_EQUAL"], linha)
                self.assertTrue(linha["SEMANTIC_EQUAL"], linha)
                self.assertEqual(linha["OLD_SHA256"], linha["NEW_SHA256"])
                self.assertEqual(linha["OLD_SIZE"], linha["NEW_SIZE"])
                self.assertFalse(linha["NEW_bom"], "saída ativa sem BOM")
                self.assertEqual(linha["NEW_newline"], "crlf")
                self.assertEqual(linha["OLD_newline"], linha["NEW_newline"])
                self.assertEqual(linha["OLD_final_nl"], linha["NEW_final_nl"])
                self.assertEqual(linha["OLD_sections"], linha["NEW_sections"])
                self.assertEqual(linha["OLD_keys"], linha["NEW_keys"])
                self.assertEqual(linha["resultado"], "PASS")


def _linhas(data: bytes) -> list:
    return data.decode("utf-8-sig").split("\r\n")


def _construir_variante(caso: str) -> bytes:
    """Cópias em memória do template para casos A–J (template real intacto)."""
    dados = _template()
    if caso == "A_chave_desconhecida":  # chave desconhecida herdada
        linhas = _linhas(dados)
        idx = linhas.index("[GeneralExt]")
        linhas.insert(idx, "ChaveVendorFutura = token_futuro")
        return "\r\n".join(linhas).encode("utf-8")
    if caso == "B_secao_desconhecida":  # seção desconhecida herdada
        return dados + b"\r\n[SeccaoFuturaVendor]\r\nNovaChave = valor\r\n"
    if caso == "C_valor_vazio_herdado":  # valor vazio herdado
        linhas = _linhas(dados)
        idx = linhas.index("[GeneralExt]")
        linhas.insert(idx, "ChaveFuturaVazia =")
        return "\r\n".join(linhas).encode("utf-8")
    if caso == "D_comentario_adicional":  # comentário adicional
        linhas = _linhas(dados)
        idx = linhas.index("[GeneralExt]")
        linhas.insert(idx, "; comentario sintetico de teste")
        return "\r\n".join(linhas).encode("utf-8")
    if caso == "E_lf_entrada":  # LF na entrada
        return dados.replace(b"\r\n", b"\n")
    if caso == "F_crlf_entrada":  # CRLF na entrada (template real)
        return dados
    if caso == "G_bom_entrada":  # BOM UTF-8 apenas na entrada
        return b"\xef\xbb\xbf" + dados
    if caso == "H_sem_newline_final":  # sem newline final (template real)
        return dados
    if caso == "I_duplicata_nao_controlada":
        linhas = _linhas(dados)
        idx = linhas.index("[GeneralExt]")
        linhas.insert(idx, "ChaveDupNC = 1")
        linhas.insert(idx + 1, "ChaveDupNC = 2")
        return "\r\n".join(linhas).encode("utf-8")
    if caso == "J_duplicata_controlada":  # duplica dgVoodooWatermark (controlada)
        linhas = _linhas(dados)
        idx = next(i for i, l in enumerate(linhas)
                   if l.strip().startswith("dgVoodooWatermark"))
        linhas.insert(idx + 1, linhas[idx])
        return "\r\n".join(linhas).encode("utf-8")
    raise ValueError(caso)


def _texto_para_oraculo(dados: bytes, caso: str) -> str:
    """Texto entregue ao oráculo legado (BOM só é questão de bytes de entrada)."""
    if caso == "G_bom_entrada":
        return dados.decode("utf-8-sig")
    return dados.decode("utf-8-sig")


def casos_sinteticos():
    """Executa A–J; retorna relatório de comportamento (classificado)."""
    relatorio = []
    for caso in ("A_chave_desconhecida", "B_secao_desconhecida",
                 "C_valor_vazio_herdado", "D_comentario_adicional",
                 "E_lf_entrada", "F_crlf_entrada", "G_bom_entrada",
                 "H_sem_newline_final", "I_duplicata_nao_controlada",
                 "J_duplicata_controlada"):
        dados = _construir_variante(caso)
        old = _legacy_apply_texto(_texto_para_oraculo(dados, caso))
        new = _engine_new(dados).bytes_
        rep = eng.diff_documents(old, new)
        relatorio.append({
            "caso": caso,
            "OLD_SHA256": hashlib.sha256(old).hexdigest(),
            "NEW_SHA256": hashlib.sha256(new).hexdigest(),
            "BYTE_EQUAL": old == new,
            "SEMANTIC_EQUAL": rep.same,
            "diff_categories": rep.categories,
            "classificacao": ("paridade" if old == new else "divergencia"),
        })
    return relatorio


class TestCasosSinteticos(unittest.TestCase):
    """A–J — robustez; divergência é classificada/registrada (esperado: 0)."""

    def test_casos_a_j(self):
        rel = casos_sinteticos()
        self.assertEqual(len(rel), 10)
        for linha in rel:
            with self.subTest(caso=linha["caso"]):
                self.assertTrue(linha["BYTE_EQUAL"],
                                f"divergência em {linha}")
                self.assertTrue(linha["SEMANTIC_EQUAL"])

    def test_duplicata_controlada_observacao(self):
        dados = _construir_variante("J_duplicata_controlada")
        doc_entrada = eng.parse_bytes(dados, catalog=sch.CATALOG)
        self.assertEqual(doc_entrada.count("DirectX", "dgVoodooWatermark"), 2)
        new = _engine_new(dados)
        doc_saida = eng.parse_bytes(new.bytes_, catalog=sch.CATALOG)
        # legado e engine preservam TODAS as ocorrências (não deduplicam)
        self.assertEqual(doc_saida.count("DirectX", "dgVoodooWatermark"), 2)
        self.assertEqual(
            [o.value for o in doc_saida.get("DirectX", "dgVoodooWatermark")],
            ["false", "false"])


class TestProvenanceBaseline(unittest.TestCase):
    """Provenance do engine validada contra a baseline auditada (94)."""

    def test_baseline_94(self):
        g = _engine_new(_template(), profile="quality")
        self.assertEqual(len(g.provenance), 94)
        contagem = {}
        for origem in g.provenance.values():
            contagem[origem] = contagem.get(origem, 0) + 1
        self.assertEqual(contagem.get("overlay_fixo"), 12)
        self.assertEqual(contagem.get("perfil"), 2)
        self.assertEqual(contagem.get("template"), 80)

    def test_base_ativa_overlay_base(self):
        g = _engine_new(_template())
        self.assertEqual(g.provenance[("DirectX", "Filtering")], "overlay_base")
        self.assertEqual(g.provenance[("DirectX", "Antialiasing")], "overlay_base")


class TestNaoIntegracaoEIntactos(unittest.TestCase):
    def test_producao_nao_importa_engine(self):
        # dgvoodoo_service.py é coberto pelo Stage 5A (integração deliberada
        # apenas no caminho de aplicação de perfil, com parity guard).
        for nome in ("dgvoodoo_page.py", "main.py",
                     "config.py", "hardware_detector.py"):
            with open(os.path.join(ROOT, nome), encoding="utf-8") as f:
                fonte = f.read()
            self.assertNotIn("dgvoodoo_config_engine", fonte, nome)
            self.assertNotIn("dgvoodoo_config_schema", fonte, nome)

    def test_template_intacto(self):
        import hashlib
        with open(TEMPLATE_PATH, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(),
                             "3c7da2fac3eaad369df468e80c9ba9c4db632c419799b32bbc31279d10985801")


if __name__ == "__main__":
    print("\n===== MATRIZ FORMAL (8 cenários) =====")
    for linha in matriz_paridade():
        print(f"{linha['cenario']:16} BYTE={linha['BYTE_EQUAL']} "
              f"SEM={linha['SEMANTIC_EQUAL']} OLD={linha['OLD_SHA256'][:16]} "
              f"NEW={linha['NEW_SHA256'][:16]} {linha['resultado']}")
    print("\n===== CASOS SINTÉTICOS A–J =====")
    for c in casos_sinteticos():
        print(f"{c['caso']:28} BYTE={c['BYTE_EQUAL']} "
              f"SEM={c['SEMANTIC_EQUAL']} {c['classificacao']}")
    unittest.main()
