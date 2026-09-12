# -*- coding: utf-8 -*-
"""Testes de higiene pré-release (fase Release Hygiene).

Cobrem, sem depender de clientes reais nem de binários de jogo:

- Fonte canônica de versão (config.VERSAO_APLICATIVO) == "V4.1.0";
- main.py referencia a fonte canônica (VERSION_LABEL = config.VERSAO_APLICATIVO);
- extractor_sets.py não grava mais o branding obsoleto "AIKA Optimizer V4.0"
  nos arquivos OBJ gerados;
- referência histórica/migração V4.0 é preservada em jit_integration;
- hashes certificados de dgVoodoo2 permanecem intactos;
- spec do PyInstaller continua incluindo assets, perfil de cores e
  third_party/dgvoodoo2;
- README não promete restauração total ao fechar sessão nem ganho garantido
  de FPS/ping;
- THIRD_PARTY_NOTICES.md documenta o dgVoodoo2;
- nenhum segredo/credencial conhecido foi introduzido em arquivos versionáveis.
"""

import hashlib
import os
import re
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

HASH_DLL = "db1c445f7bcf699df1e175e974c779bdc7e19a468680a44884b1ab7078888d04"
HASH_CONF = "3c7da2fac3eaad369df468e80c9ba9c4db632c419799b32bbc31279d10985801"

IGNORE_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache",
               "build", "dist", "installer"}


def _ler(rel):
    with open(os.path.join(RAIZ, rel), encoding="utf-8") as f:
        return f.read()


def _hash_file(rel):
    h = hashlib.sha256()
    with open(os.path.join(RAIZ, rel), "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _arquivos_versionaveis():
    exts = {".py", ".iss", ".spec", ".json", ".txt", ".md"}
    achados = []
    for root, dirs, files in os.walk(RAIZ):
        dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS)
        for nome in files:
            if os.path.splitext(nome)[1].lower() in exts:
                achados.append(os.path.join(root, nome))
    return achados


class TestFonteCanonicaVersao(unittest.TestCase):
    def test_versao_final_central(self):
        import config
        self.assertEqual(config.VERSAO_APLICATIVO, "V4.1.0")

    def test_main_referencia_fonte_canonica(self):
        self.assertIn("VERSION_LABEL = config.VERSAO_APLICATIVO", _ler("main.py"))

    def test_extractor_nao_grava_branding_v40(self):
        src = _ler("extractor_sets.py")
        self.assertNotIn("Convertido pelo AIKA Optimizer V4.0", src)
        # a saída gerada deve usar a constante centralizada
        self.assertIn("{VERSAO_APLICATIVO}", src)


class TestHistoricoV40Preservado(unittest.TestCase):
    def test_migracao_jit_v40_preservada(self):
        # referência histórica/migração V4.0 continua presente e intencional
        self.assertIn('NOME_REGISTRADO_LEGADO = "AIKA Optimizer V4.0"',
                      _ler("jit_integration.py"))


class TestHashesDgVoodoo(unittest.TestCase):
    def test_hashes_intactos(self):
        self.assertEqual(_hash_file("third_party/dgvoodoo2/D3D9.dll"), HASH_DLL)
        self.assertEqual(_hash_file("third_party/dgvoodoo2/dgVoodoo.conf"), HASH_CONF)


class TestSpecPackaging(unittest.TestCase):
    def test_spec_inclui_assets_perfil_e_dgvoodoo(self):
        spec = _ler("Aika_Optimizer_V4.1.spec")
        self.assertIn("('assets', 'assets')", spec)
        self.assertIn("('itemlist6_color_profile.json', '.')", spec)
        self.assertIn("('icone.ico', '.')", spec)
        self.assertIn("('aika.ico', '.')", spec)
        self.assertIn("third_party/dgvoodoo2", spec)

    def test_assets_de_ajuda_e_renderizador_existem(self):
        for rel in ("assets/icons/help.svg", "assets/icons/renderizador.svg"):
            self.assertTrue(os.path.isfile(os.path.join(RAIZ, rel)), rel)


class TestREADMEHonesidade(unittest.TestCase):
    def test_nao_promete_restauracao_total_ao_fechar(self):
        readme = _ler("README.md")
        self.assertNotIn("restaura o sistema ao final", readme)
        self.assertIn("nao oferece garantia de rollback total", readme)

    def test_nao_promete_ganho_garantido(self):
        readme = _ler("README.md").lower()
        for frase in ("aumenta fps", "mais fps", "reduz ping", "reduz latencia",
                      "ganho garantido"):
            self.assertNotIn(frase, readme)


class TestThirdPartyNotices(unittest.TestCase):
    def test_notices_documenta_dgvoodoo2(self):
        notices = _ler("THIRD_PARTY_NOTICES.md")
        self.assertIn("dgVoodoo2", notices)
        self.assertIn("2.87.4", notices)
        self.assertIn("dege.freeweb.hu", notices)
        self.assertIn("D3D9.dll", notices)
        self.assertIn("dgVoodoo.conf", notices)


class TestSemSegredos(unittest.TestCase):
    PADROES = [
        r"api_key\s*=\s*['\"][^'\"]+",
        r"password\s*=\s*['\"][^'\"]+",
        r"senha\s*=\s*['\"][^'\"]+",
        r"secret\s*=\s*['\"][^'\"]+",
        r"private_key\s*=\s*['\"]",
        r"credential\s*=\s*['\"][^'\"]+",
        r"token\s*=\s*['\"][A-Za-z0-9_\-]{8,}",
    ]

    def test_nenhum_segredo_conhecido(self):
        regexes = [re.compile(p) for p in self.PADROES]
        violacoes = []
        for caminho in _arquivos_versionaveis():
            rel = os.path.relpath(caminho, RAIZ)
            try:
                texto = open(caminho, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for rx in regexes:
                if rx.search(texto):
                    violacoes.append(rel)
                    break
        self.assertEqual(violacoes, [],
                         "possível segredo em arquivos versionáveis")


if __name__ == "__main__":
    unittest.main()
