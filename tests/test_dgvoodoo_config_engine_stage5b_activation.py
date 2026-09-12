# -*- coding: utf-8 -*-
"""Estágio 5B — Integração de Ativar/Reaplicar ao engine (com parity guard).

Ativar dgVoodoo e Reaplicar/Aika Recomendado passam a ter a origem dos bytes
do dgVoodoo.conf no ENGINE, mas SOMENTE após o parity guard comparar byte a
byte com o produtor legado em memória:

  legacy(base) == engine(base)  -> grava ENGINE_BYTES
  legacy(base) != engine(base)  -> ABORTA antes de qualquer mutação (estado
                                   PENDING inclusive); sem fallback silencioso

Cobertura (1-31 da especificação):
- Ativar/Reaplicar usam engine + parity guard e geram o hash certificado;
- sem BOM, CRLF, Filtering=16, Antialiasing=2x, watermark=false,
  OutputAPI=d3d11_fl11_0;
- divergências forçadas (Ativar e Reaplicar) bloqueiam sem tocar arquivos/
  estado e sem usar fallback;
- persistência/estado semanticamente iguais; Reaplicar nunca reaplica perfil
  ou AUTO; Restaurar/backup/DLL/template intactos;
- Stage 5A (perfis/AUTO) continua; nenhum cliente real é tocado.
NENHUM teste toca cliente real.
"""
import ast
import hashlib
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import dgvoodoo_service as svc  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(ROOT, "third_party", "dgvoodoo2", "dgVoodoo.conf")
DLL_PATH = os.path.join(ROOT, "third_party", "dgvoodoo2", "D3D9.dll")

HASH_TEMPLATE = "3c7da2fac3eaad369df468e80c9ba9c4db632c419799b32bbc31279d10985801"
HASH_DLL = "db1c445f7bcf699df1e175e974c779bdc7e19a468680a44884b1ab7078888d04"
HASH_ENGINE = "77060a2f48c61414867c5ef9de5c098707686dc427dbcefa1063b497d5038995"
HASH_SCHEMA = "8f63b09123096af80774c9e5cdc47248e9844270c3138645c1d5d33fcb29ee21"

FROZEN_BASE = "3ca4b70641ee1348e9da7b4f3a5d27979bfefe82a3c89d19c80ad61b9d4e0e12"
FROZEN = {
    "performance": "0337905f4b82adec730c21292f527904bf3355c26ca74952b2e18c9b0134aeb5",
    "balanced": FROZEN_BASE,
    "quality": "ab8f2fcc04fa94d5c5b90d3858d725de83a5946073cc29fc7a0528ae102700dd",
}
AA = {svc.PERFIL_PERFORMANCE: "appdriven", svc.PERFIL_BALANCED: "2x", svc.PERFIL_QUALITY: "4x"}
FILTRO = {svc.PERFIL_PERFORMANCE: "trilinear", svc.PERFIL_BALANCED: "16", svc.PERFIL_QUALITY: "16"}
TAMANHO_BASE = 21891


def _h(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _h_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _ler_chave(texto: str, secao, chave):
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


class BaseStage5B(unittest.TestCase):
    """Cliente temporário + config mockada (nunca cliente real)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="aika_stage5b_")
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

    # Helpers ---------------------------------------------------------------
    def caminho(self, *nomes):
        return os.path.join(self.cli, *nomes)

    def ler(self, nome):
        with open(self.caminho(nome), "rb") as f:
            return f.read()

    def existe(self, nome):
        return os.path.isfile(self.caminho(nome))

    def conf_bytes(self):
        return self.ler(svc.DGVOODOO_CONF)

    def conf_texto(self):
        return self.conf_bytes().decode("utf-8")

    def ler_chave(self, secao, chave):
        return _ler_chave(self.conf_texto(), secao, chave)

    def ativar_limpo(self):
        r = svc.ativar_dgvoodoo(self.cli)
        self.assertTrue(r.ok, r.mensagem)
        return r

    def estado(self):
        e = svc._carregar_estado(self.cli)
        self.assertIsNotNone(e)
        return e

    def template_intacto(self):
        self.assertEqual(_h_file(TEMPLATE_PATH), HASH_TEMPLATE)
        self.assertEqual(_h_file(DLL_PATH), HASH_DLL)

    def _conferir_base(self, tag):
        dados = self.conf_bytes()
        texto = dados.decode("utf-8")
        self.assertEqual(_h(dados), FROZEN_BASE, f"hash certificado {tag}")
        self.assertEqual(len(dados), TAMANHO_BASE, f"tamanho esperado {tag}")
        self.assertNotEqual(dados[:3], b"\xef\xbb\xbf", "BOM presente")
        # CRLF: remover \r\n não pode sobrar \n isolado.
        self.assertEqual(dados.replace(b"\r\n", b"").count(b"\n"), 0, "LF isolado")
        self.assertEqual(_ler_chave(texto, "[DirectX]", "Filtering"), "16")
        self.assertEqual(_ler_chave(texto, "[DirectX]", "Antialiasing"), "2x")
        self.assertEqual(_ler_chave(texto, "[DirectX]", "dgVoodooWatermark"), "false")
        self.assertEqual(_ler_chave(texto, "[General]", "OutputAPI"), "d3d11_fl11_0")
        return dados


class TestAtivacaoEngineEParidade(BaseStage5B):
    """1-12 — Ativar/Reaplicar pelo engine, guard ok, hash e invariantes."""

    def test_01_baseline_stage5a_intacta(self):
        # O módulo 5A (aplicar_perfil) continua válido e o escopo estático do
        # serviço agora cobre os dois caminhos integrados (5A e 5B).
        import tests.test_dgvoodoo_config_engine_stage5a_integration as m5a  # noqa: F401
        self.assertIsNotNone(m5a.FROZEN)
        with open(os.path.join(ROOT, "dgvoodoo_service.py"), encoding="utf-8") as f:
            arv = ast.parse(f.read())
        refs = {}
        for no in arv.body:
            if isinstance(no, ast.FunctionDef):
                alvos = {n.id for n in ast.walk(no)
                         if isinstance(n, ast.Name) and n.id in (
                             "_config_engine", "_config_schema", "_paridade_geracao")}
                if alvos:
                    refs[no.name] = alvos
        self.assertEqual({n for n, a in refs.items()
                          if {"_config_engine", "_config_schema"} & a},
                         {"_gerar_engine_bytes", "_resumo_diff_geracao"})
        self.assertEqual({n for n, a in refs.items() if "_paridade_geracao" in a},
                         {"aplicar_perfil", "ativar_dgvoodoo"})

    def test_02_03_ativar_reaplicar_usam_engine_com_guard(self):
        real = svc._gerar_engine_bytes
        with mock.patch.object(svc, "_gerar_engine_bytes", wraps=real) as spy:
            self.ativar_limpo()
        self.assertIn((None,), [c.args for c in spy.call_args_list],
                      "engine chamado com perfil None (base)")
        g = svc._paridade_geracao(None, operacao="ativar/reaplicar")
        self.assertTrue(g["ok"])
        self.assertEqual(g["engine_bytes"], svc._gerar_conf_base())
        self.assertEqual(_h(g["engine_bytes"]), FROZEN_BASE)
        self.assertEqual(self.conf_bytes(), g["engine_bytes"],
                         "conf gravado deve ser EXATAMENTE os engine_bytes")
        # Reaplicar = novo ciclo público de ativação; engine chamado de novo.
        with mock.patch.object(svc, "_gerar_engine_bytes", wraps=real) as spy2:
            r2 = svc.ativar_dgvoodoo(self.cli)
        self.assertTrue(r2.ok, r2.mensagem)
        self.assertIn((None,), [c.args for c in spy2.call_args_list])
        self.assertEqual(self.conf_bytes(), g["engine_bytes"])
        self.assertEqual(self.estado()["status"], "active")

    def test_04_05_ativar_reaplicar_hash_certificado(self):
        self.ativar_limpo()
        self._conferir_base("Ativar")
        self.ativar_limpo()  # Reaplicar
        self._conferir_base("Reaplicar")
        self.assertEqual(self.estado().get("preset"), "Aika Recomendado")

    def test_06_a_11_invariantes_pos_escrita(self):
        self.ativar_limpo()
        self._conferir_base("Ativar")
        self.ativar_limpo()  # Reaplicar com invariantes idênticas
        self._conferir_base("Reaplicar")

    def test_12_legado_igual_engine_antes_da_escrita(self):
        g = svc._paridade_geracao(None, operacao="ativar/reaplicar")
        self.assertTrue(g["ok"])
        self.assertEqual(g["engine_bytes"], svc._gerar_conf_base())
        self.assertEqual(_h(g["engine_bytes"]), FROZEN_BASE)
        self.assertEqual(len(g["engine_bytes"]), TAMANHO_BASE)


class TestDivergenciaForcada(BaseStage5B):
    """13-15 — divergência simulada bloqueia sem fallback e sem mutação."""

    def _bytes_divergentes(self):
        return svc._gerar_engine_bytes(None) + b"\r\n; simulado 5B"

    def test_13_15_divergencia_ativar_bloqueia_sem_fallback(self):
        divergente = self._bytes_divergentes()
        with mock.patch.object(svc, "_gerar_engine_bytes",
                               return_value=divergente) as mk:
            r = svc.ativar_dgvoodoo(self.cli)
        mk.assert_called_once_with(None)
        self.assertFalse(r.ok)
        m = r.mensagem
        self.assertIn("DIVERGÊNCIA LEGADO×ENGINE", m)
        self.assertIn("operacao=ativar/reaplicar", m)
        self.assertIn("perfil=base", m)
        self.assertIn("legacy_sha256=", m)
        self.assertIn("engine_sha256=", m)
        self.assertIn("legacy_size=", m)
        self.assertIn("engine_size=", m)
        self.assertIn("diff=", m)
        # Guard roda ANTES do estado PENDING e de qualquer escrita:
        self.assertEqual(os.listdir(self.cli), [],
                         "nenhum arquivo pode ser criado na divergência")
        self.assertIsNone(svc._carregar_estado(self.cli),
                          "estado não pode existir (nem pending)")
        self.assertFalse(self.existe(svc.DGVOODOO_CONF))
        self.assertFalse(self.existe(svc.D3D9_DLL))

    def test_14_15_divergencia_reaplicar_bloqueia_preservando(self):
        self.ativar_limpo()
        conf_antes = self.conf_bytes()
        dll_antes = self.ler(svc.D3D9_DLL)
        estado_antes = self.estado()
        divergente = self._bytes_divergentes()
        with mock.patch.object(svc, "_gerar_engine_bytes",
                               return_value=divergente) as mk:
            r = svc.ativar_dgvoodoo(self.cli)  # Reaplicar
        mk.assert_called_once_with(None)
        self.assertFalse(r.ok)
        self.assertIn("DIVERGÊNCIA LEGADO×ENGINE", r.mensagem)
        # Sem fallback silencioso e sem qualquer mudança:
        self.assertEqual(self.conf_bytes(), conf_antes,
                         "conf deve permanecer o instalado (base certificada)")
        self.assertEqual(_h(self.conf_bytes()), FROZEN_BASE)
        self.assertEqual(self.ler(svc.D3D9_DLL), dll_antes)
        self.assertEqual(self.estado(), estado_antes,
                         "estado.json não pode mudar na divergência")
        self.assertEqual(self.estado()["status"], "active")
        self.assertEqual(self.estado()["conf"]["installed_sha256"], FROZEN_BASE)


class TestEstadoEPersistencia(BaseStage5B):
    """16-21 — estado normal idêntico; Reaplicar nunca reaplica perfil/AUTO."""

    def _campos_semantica(self, e):
        return {k: e.get(k) for k in ("format_version", "status", "preset",
                                      "backend", "template_version")}

    def test_16_estado_normal_ativar_igual_anterior(self):
        self.ativar_limpo()
        e = self.estado()
        self.assertEqual(self._campos_semantica(e),
                         {"format_version": 1, "status": "active",
                          "preset": "Aika Recomendado", "backend": "d3d11_fl11_0",
                          "template_version": e["template_version"]})
        self.assertEqual(e["conf"]["installed_sha256"], FROZEN_BASE)
        self.assertNotIn("resolved_profile", e)

    def test_17_estado_normal_reaplicar_igual_anterior(self):
        self.ativar_limpo()
        e1 = self.estado()
        self.ativar_limpo()
        e2 = self.estado()
        self.assertEqual(self._campos_semantica(e1), self._campos_semantica(e2))
        self.assertEqual(e1["conf"]["installed_sha256"], FROZEN_BASE)
        self.assertEqual(e2["conf"]["installed_sha256"], FROZEN_BASE)
        # Semântica de originais/herança preservada no novo ciclo:
        self.assertEqual(e1["conf"]["original_present"], e2["conf"]["original_present"])
        self.assertEqual(e1["conf"].get("original_sha256"), e2["conf"].get("original_sha256"))
        self.assertNotIn("resolved_profile", e1)
        self.assertNotIn("resolved_profile", e2)

    def test_18_19_20_21_reaplicar_nao_reaplica_perfil_ou_auto(self):
        self.ativar_limpo()
        for perfil, esperado in (
                (svc.PERFIL_QUALITY, FROZEN["quality"]),
                (svc.PERFIL_PERFORMANCE, FROZEN["performance"])):
            with self.subTest(perfil=perfil):
                r = svc.aplicar_perfil(perfil, self.cli)
                self.assertTrue(r.ok, r.mensagem)
                self.assertEqual(_h(self.conf_bytes()), esperado)
                self.ativar_limpo()  # Reaplicar
                self._conferir_base("Reaplicar pós-" + perfil)
                e = self.estado()
                self.assertEqual(e["preset"], "Aika Recomendado")
                self.assertNotIn("resolved_profile", e)
        # AUTO (mesmo resolvido para Quality) também é reconstruído como base:
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                               resolved_profile=svc.PERFIL_QUALITY)
        self.assertTrue(r.ok, r.mensagem)
        self.assertEqual(self.estado()["resolved_profile"], "quality")
        self.ativar_limpo()  # Reaplicar
        self._conferir_base("Reaplicar pós-AUTO")
        e = self.estado()
        self.assertEqual(e["preset"], "Aika Recomendado")
        self.assertNotIn("resolved_profile", e,
                         "Reaplicar não pode herdar resolved_profile de AUTO")


class TestIntactosEStage5A(BaseStage5B):
    """22-31 — Restaurar/backup/DLL/template e continuidade do Stage 5A."""

    def test_22_restaurar_nao_usa_engine(self):
        with open(os.path.join(ROOT, "dgvoodoo_service.py"), encoding="utf-8") as f:
            arv = ast.parse(f.read())
        for no in arv.body:
            if isinstance(no, ast.FunctionDef) and \
                    no.name == "restaurar_directx_original":
                ids = {n.id for n in ast.walk(no)
                       if isinstance(n, ast.Name)}
                self.assertNotIn("_config_engine", ids)
                self.assertNotIn("_paridade_geracao", ids)
                break
        else:  # pragma: no cover
            self.fail("restaurar_directx_original não encontrada")
        self.ativar_limpo()
        r = svc.restaurar_directx_original(self.cli)
        self.assertTrue(r.ok, r.mensagem)
        self.assertFalse(self.existe(svc.DGVOODOO_CONF))
        self.assertFalse(self.existe(svc.D3D9_DLL))

    def test_23_backup_e_restauracao_bytes_intactos(self):
        # Conf original pré-existente é capturado e restaurado byte a byte.
        original = b"conf original customizado\r\n[General]\r\nOutputAPI = bestavailable\r\n"
        with open(self.caminho(svc.DGVOODOO_CONF), "wb") as f:
            f.write(original)
        self.ativar_limpo()
        e = self.estado()
        self.assertTrue(e["conf"]["original_present"])
        self.assertIsNotNone(e["conf"].get("backup_path"))
        r = svc.restaurar_directx_original(self.cli)
        self.assertTrue(r.ok, r.mensagem)
        with open(self.caminho(svc.DGVOODOO_CONF), "rb") as f:
            self.assertEqual(f.read(), original, "conf original restaurado byte a byte")
        self.assertFalse(self.existe(svc.D3D9_DLL))

    def test_24_dll_instalada_identica(self):
        self.ativar_limpo()
        self.assertEqual(_h_file(self.caminho(svc.D3D9_DLL)), HASH_DLL)
        dll_antes = self.ler(svc.D3D9_DLL)
        for perfil in (svc.PERFIL_QUALITY, svc.PERFIL_PERFORMANCE):
            svc.aplicar_perfil(perfil, self.cli)
        self.ativar_limpo()  # Reaplicar
        self.assertEqual(self.ler(svc.D3D9_DLL), dll_antes)
        self.assertEqual(_h_file(self.caminho(svc.D3D9_DLL)), HASH_DLL)

    def test_25_template_e_codigo_intactos(self):
        self.template_intacto()
        self.assertEqual(_h_file(os.path.join(ROOT, "dgvoodoo_config_engine.py")),
                         HASH_ENGINE)
        self.assertEqual(_h_file(os.path.join(ROOT, "dgvoodoo_config_schema.py")),
                         HASH_SCHEMA)
        self.ativar_limpo()
        self.ativar_limpo()
        self.template_intacto()

    def test_26_27_28_29_perfis_e_auto_stage5a_continuam(self):
        self.ativar_limpo()
        for perfil, esperado in (
                (svc.PERFIL_PERFORMANCE, FROZEN["performance"]),
                (svc.PERFIL_BALANCED, FROZEN["balanced"]),
                (svc.PERFIL_QUALITY, FROZEN["quality"])):
            with self.subTest(perfil=perfil):
                r = svc.aplicar_perfil(perfil, self.cli)
                self.assertTrue(r.ok, r.mensagem)
                dados = self.conf_bytes()
                self.assertEqual(_h(dados), esperado)
                texto = dados.decode("utf-8")
                self.assertEqual(_ler_chave(texto, "[DirectX]", "Filtering"),
                                 FILTRO[perfil])
                self.assertEqual(_ler_chave(texto, "[DirectX]", "Antialiasing"),
                                 AA[perfil])
        for resolved, esperado in (
                (svc.PERFIL_PERFORMANCE, FROZEN["performance"]),
                (svc.PERFIL_BALANCED, FROZEN["balanced"]),
                (svc.PERFIL_QUALITY, FROZEN["quality"])):
            with self.subTest(auto=resolved):
                r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                                       resolved_profile=resolved)
                self.assertTrue(r.ok, r.mensagem)
                self.assertEqual(_h(self.conf_bytes()), esperado)

    def test_30_stages_1_a_4_disponiveis(self):
        # Os módulos dos Stages 1-4 continuam importáveis/descobríveis.
        for nome in ("test_dgvoodoo_config_engine",
                     "test_dgvoodoo_config_engine_stage2",
                     "test_dgvoodoo_config_engine_stage3_parity",
                     "test_dgvoodoo_config_engine_stage4_determinism"):
            mod = __import__("tests." + nome, fromlist=["*"])  # noqa: F401
            self.assertIsNotNone(mod)

    def test_31_nenhum_cliente_real_tocado(self):
        # Todos os fluxos desta fase usam apenas diretórios temporários
        # (BaseStage5B). Garantia estática: os módulos envolvidos na geração
        # e no serviço nunca referenciam os clientes reais do usuário.
        caminhos_reais = (r"c:\cbmgames\aikaonlinebrasil",
                          r"c:\users\diego\downloads\aikaonlinebrasil")
        for nome in ("dgvoodoo_config_engine.py", "dgvoodoo_config_schema.py",
                     "dgvoodoo_service.py"):
            with open(os.path.join(ROOT, nome), encoding="utf-8") as f:
                fonte = f.read().lower()
            for caminho in caminhos_reais:
                self.assertNotIn(caminho, fonte, nome)


if __name__ == "__main__":
    unittest.main()




