# -*- coding: utf-8 -*-
"""Estágio 5A — Primeira integração gradual ao serviço (somente aplicar_perfil).

O caminho de APLICAÇÃO DE PERFIL agora usa os bytes do engine, mas SOMENTE
depois de o PARITY GUARD comparar byte a byte com o gerador legado:

  legacy_bytes == engine_bytes  -> segue com os bytes do engine
  legacy_bytes != engine_bytes  -> ABORTA antes de escrever (sem fallback)

Cobertura (1-27 da especificação):
- serviço importa/usa engine apenas no caminho aplicar_perfil;
- Performance/Balanced/Quality/AUTO geram os hashes certificados Stage 4;
- parity guard passa no fluxo real e bloqueia divergência simulada;
- divergência não toca dgVoodoo.conf nem estado.json;
- persistência manual/AUTO inalterada; sem BOM;
- DLL não reinstalada; backup não recapturado; template intacto;
- Ativar/Reaplicar/Restaurar intactos no legado; UI/hardware intactos.
NENHUM teste toca cliente real.
"""
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

FROZEN = {
    None: "3ca4b70641ee1348e9da7b4f3a5d27979bfefe82a3c89d19c80ad61b9d4e0e12",
    "performance": "0337905f4b82adec730c21292f527904bf3355c26ca74952b2e18c9b0134aeb5",
    "balanced": "3ca4b70641ee1348e9da7b4f3a5d27979bfefe82a3c89d19c80ad61b9d4e0e12",
    "quality": "ab8f2fcc04fa94d5c5b90d3858d725de83a5946073cc29fc7a0528ae102700dd",
}

AA = {svc.PERFIL_PERFORMANCE: "appdriven", svc.PERFIL_BALANCED: "2x", svc.PERFIL_QUALITY: "4x"}
FILTRO = {svc.PERFIL_PERFORMANCE: "trilinear", svc.PERFIL_BALANCED: "16", svc.PERFIL_QUALITY: "16"}


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


class BaseStage5A(unittest.TestCase):
    """Cliente temporário + config mockada (nunca cliente real)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="aika_stage5a_")
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

    def ler_chave(self, secao, chave):
        return _ler_chave(self.conf_bytes().decode("utf-8-sig"), secao, chave)

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


class TestEscopoIntegracao(BaseStage5A):
    """1, 21, 22, 23 — integração restrita a aplicar_perfil."""

    def _fonte(self, nome):
        with open(os.path.join(ROOT, nome), encoding="utf-8") as f:
            return f.read()

    def test_01_servico_usa_engine_apenas_no_caminho_aplicar_perfil(self):
        fonte = self._fonte("dgvoodoo_service.py")
        self.assertIn("import dgvoodoo_config_engine", fonte)
        self.assertIn("import dgvoodoo_config_schema", fonte)
        # Análise estática por função (AST): o engine só pode ser referenciado
        # por _gerar_engine_bytes/_resumo_diff_geracao (geração em memória) e o
        # parity guard é chamado por aplicar_perfil e, desde o Stage 5B, também
        # por ativar_dgvoodoo (guard compartilhado base/perfil). Restaurar nunca.
        import ast
        arv = ast.parse(fonte)
        refs = {}
        for no in arv.body:
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                alvos = set()
                for n in ast.walk(no):
                    if isinstance(n, ast.Name) and n.id in (
                            "_config_engine", "_config_schema", "_paridade_geracao"):
                        alvos.add(n.id)
                refs[no.name] = alvos
        usam_engine = {nome for nome, alvos in refs.items()
                       if {"_config_engine", "_config_schema"} & alvos}
        self.assertEqual(
            usam_engine, {"_gerar_engine_bytes", "_resumo_diff_geracao"},
            "engine referenciado fora da geração em memória (5A/5B)")
        chamam_guard = {nome for nome, alvos in refs.items()
                        if "_paridade_geracao" in alvos}
        self.assertEqual(
            chamam_guard, {"aplicar_perfil", "ativar_dgvoodoo"},
            "parity guard chamado fora de aplicar_perfil/ativar_dgvoodoo")
        # Restaurar fica integralmente no legado (nenhum engine/guard).
        self.assertNotIn("restaurar_directx_original", usam_engine)
        self.assertNotIn("restaurar_directx_original", chamam_guard)

    def test_21_22_ativar_reaplicar_legado_integral(self):
        # Ativar e Reaplicar não passam pelo parity guard (região estática no
        # teste 01). Reaplicar é o caminho de ativação novamente (base fixa).
        self.ativar_limpo()
        self.ativar_limpo()
        self.assertEqual(self.estado()["status"], "active")
        self.assertEqual(self.estado().get("preset"), "Aika Recomendado")

    def test_23_restaurar_intacto(self):
        self.ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_QUALITY, self.cli)
        self.assertTrue(r.ok, r.mensagem)
        r = svc.restaurar_directx_original(self.cli)
        self.assertTrue(r.ok, r.mensagem)
        self.assertFalse(self.existe(svc.DGVOODOO_CONF))
        self.assertFalse(self.existe(svc.D3D9_DLL))

    def test_24_25_ui_e_hardware_detector_intactos(self):
        for nome in ("dgvoodoo_page.py", "hardware_detector.py",
                     "main.py", "config.py"):
            with open(os.path.join(ROOT, nome), encoding="utf-8") as f:
                fonte = f.read()
            self.assertNotIn("dgvoodoo_config_engine", fonte, nome)
            self.assertNotIn("dgvoodoo_config_schema", fonte, nome)


class TestPerfisCertificadosViaServico(BaseStage5A):
    """2-9 — bytes finais == hashes certificados; sem BOM; pós-escrita ok."""

    def _aplicar_e_conferir(self, perfil, esperado):
        r = svc.aplicar_perfil(perfil, self.cli)
        self.assertTrue(r.ok, r.mensagem)
        dados = self.conf_bytes()
        self.assertEqual(_h(dados), esperado, f"hash final {perfil}")
        self.assertNotEqual(dados[:3], b"\xef\xbb\xbf", "arquivo ativo com BOM")
        self.assertEqual(r.dados["conf_sha256"], esperado)
        texto = dados.decode("utf-8-sig")
        self.assertEqual(_ler_chave(texto, "[DirectX]", "Filtering"), FILTRO[perfil])
        self.assertEqual(_ler_chave(texto, "[DirectX]", "Antialiasing"), AA[perfil])
        return dados

    def test_ativar_gera_base_certificada(self):
        self.ativar_limpo()
        self.assertEqual(_h(self.conf_bytes()), FROZEN[None])

    def test_02_05_performance_auto_performance(self):
        self.ativar_limpo()
        self._aplicar_e_conferir(svc.PERFIL_PERFORMANCE, FROZEN["performance"])
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                               resolved_profile=svc.PERFIL_PERFORMANCE)
        self.assertTrue(r.ok, r.mensagem)
        self.assertEqual(_h(self.conf_bytes()), FROZEN["performance"])

    def test_03_06_balanced_auto_balanced(self):
        self.ativar_limpo()
        self._aplicar_e_conferir(svc.PERFIL_BALANCED, FROZEN["balanced"])
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                               resolved_profile=svc.PERFIL_BALANCED)
        self.assertTrue(r.ok, r.mensagem)
        self.assertEqual(_h(self.conf_bytes()), FROZEN["balanced"])

    def test_04_07_quality_auto_quality(self):
        self.ativar_limpo()
        self._aplicar_e_conferir(svc.PERFIL_QUALITY, FROZEN["quality"])
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                               resolved_profile=svc.PERFIL_QUALITY)
        self.assertTrue(r.ok, r.mensagem)
        self.assertEqual(_h(self.conf_bytes()), FROZEN["quality"])

    def test_08_auto_usa_hash_do_perfil_resolvido(self):
        self.ativar_limpo()
        mapa = {svc.PERFIL_PERFORMANCE: FROZEN["performance"],
                svc.PERFIL_BALANCED: FROZEN["balanced"],
                svc.PERFIL_QUALITY: FROZEN["quality"]}
        for resolved, esperado in mapa.items():
            with self.subTest(resolved=resolved):
                r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                                       resolved_profile=resolved)
                self.assertTrue(r.ok, r.mensagem)
                self.assertEqual(_h(self.conf_bytes()), esperado)

    def test_09_sem_bom_e_validacoes_pos_escrita(self):
        self.ativar_limpo()
        for perfil in (svc.PERFIL_PERFORMANCE, svc.PERFIL_BALANCED,
                       svc.PERFIL_QUALITY):
            with self.subTest(perfil=perfil):
                dados = self._aplicar_e_conferir(perfil, FROZEN[perfil])
                # Escrito == engine_bytes validados pelo guard.
                self.assertEqual(dados, svc._gerar_conf_perfil(perfil))


class TestParityGuard(BaseStage5A):
    """10-13 — guard passa no fluxo real e bloqueia divergência simulada."""

    def test_10_guard_legado_igual_engine_antes_da_escrita(self):
        self.ativar_limpo()
        for perfil in (svc.PERFIL_PERFORMANCE, svc.PERFIL_BALANCED,
                       svc.PERFIL_QUALITY):
            with self.subTest(perfil=perfil):
                g = svc._paridade_geracao(perfil)
                self.assertTrue(g["ok"])
                self.assertEqual(g["engine_bytes"], svc._gerar_conf_perfil(perfil))
                self.assertEqual(_h(g["engine_bytes"]), FROZEN[perfil])

    def test_11_12_13_divergencia_aborta_sem_tocar_conf_estado(self):
        self.ativar_limpo()
        # Estado e conf de referência após aplicação válida de performance.
        r = svc.aplicar_perfil(svc.PERFIL_PERFORMANCE, self.cli)
        self.assertTrue(r.ok, r.mensagem)
        conf_antes = self.conf_bytes()
        estado_antes = self.estado()
        dll_antes = self.ler(svc.D3D9_DLL)
        divergente = svc._gerar_engine_bytes(svc.PERFIL_BALANCED) + b"\r\n; simulado"
        with mock.patch.object(svc, "_gerar_engine_bytes",
                               return_value=divergente) as mk:
            r = svc.aplicar_perfil(svc.PERFIL_QUALITY, self.cli)
        mk.assert_called_once_with(svc.PERFIL_QUALITY)
        self.assertFalse(r.ok)
        self.assertIn("DIVERGÊNCIA LEGADO×ENGINE", r.mensagem)
        self.assertIn("perfil=quality", r.mensagem)
        self.assertIn("legacy_sha256=", r.mensagem)
        self.assertIn("engine_sha256=", r.mensagem)
        self.assertIn("legacy_size=", r.mensagem)
        self.assertIn("engine_size=", r.mensagem)
        self.assertIn("diff=", r.mensagem)
        self.assertEqual(self.conf_bytes(), conf_antes,
                         "conf anterior deve permanecer byte-idêntico")
        self.assertEqual(self.ler(svc.D3D9_DLL), dll_antes)
        self.assertEqual(self.estado(), estado_antes,
                         "estado.json não pode mudar na divergência")


class TestPersistenciaEValidacoes(BaseStage5A):
    """14-20 — regras atuais preservadas; proteções intactas."""

    def test_14_perfil_invalido_rejeitado(self):
        self.ativar_limpo()
        conf_antes = self.conf_bytes()
        estado_antes = self.estado()
        r = svc.aplicar_perfil("ultra", self.cli)
        self.assertFalse(r.ok)
        self.assertEqual(self.conf_bytes(), conf_antes)
        self.assertEqual(self.estado(), estado_antes)

    def test_15_auto_sem_resolved_rejeitado(self):
        self.ativar_limpo()
        conf_antes = self.conf_bytes()
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli)
        self.assertFalse(r.ok)
        self.assertEqual(self.conf_bytes(), conf_antes)

    def test_16_manual_remove_resolved_profile(self):
        self.ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                               resolved_profile=svc.PERFIL_QUALITY)
        self.assertTrue(r.ok, r.mensagem)
        self.assertEqual(self.estado()["resolved_profile"], "quality")
        r = svc.aplicar_perfil(svc.PERFIL_BALANCED, self.cli)
        self.assertTrue(r.ok, r.mensagem)
        e = self.estado()
        self.assertEqual(e["preset"], "balanced")
        self.assertNotIn("resolved_profile", e)

    def test_17_auto_persiste_resolved_profile(self):
        self.ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                               resolved_profile=svc.PERFIL_PERFORMANCE)
        self.assertTrue(r.ok, r.mensagem)
        e = self.estado()
        self.assertEqual(e["preset"], "auto")
        self.assertEqual(e["resolved_profile"], "performance")

    def test_18_19_dll_nao_reinstalada_e_backup_nao_recapturado(self):
        self.ativar_limpo()
        e = self.estado()
        dll_antes = self.ler(svc.D3D9_DLL)
        original = e["conf"].get("original_sha256")
        backup = e["conf"].get("backup_path")
        for perfil in (svc.PERFIL_PERFORMANCE, svc.PERFIL_QUALITY,
                       svc.PERFIL_BALANCED):
            r = svc.aplicar_perfil(perfil, self.cli)
            self.assertTrue(r.ok, r.mensagem)
        self.assertEqual(self.ler(svc.D3D9_DLL), dll_antes)
        self.assertEqual(self.estado()["conf"].get("original_sha256"), original)
        self.assertEqual(self.estado()["conf"].get("backup_path"), backup)

    def test_20_template_intacto(self):
        self.ativar_limpo()
        self.template_intacto()
        for perfil in (svc.PERFIL_PERFORMANCE, svc.PERFIL_BALANCED,
                       svc.PERFIL_QUALITY):
            svc.aplicar_perfil(perfil, self.cli)
        self.template_intacto()


if __name__ == "__main__":
    unittest.main()



