# -*- coding: utf-8 -*-
"""Validação Controlada 06 — Organizador de Sets.

Somente TemporaryDirectory, arquivos binários sintéticos e mocks. Não acessa
cliente AIKA, Blender, Registry, processos, serviços ou arquivos do usuário.
"""
import hashlib
import json
import math
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import extractor_sets as exts  # noqa: E402
import set_injector as sinj  # noqa: E402
import textura  # noqa: E402


def gravar(caminho, dados):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(dados)
    return str(caminho)


def sha256(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def msh_bytes(vertices=None, uvs=None, indices=(0, 1, 2), vert_size=0x24):
    vertices = vertices or ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    uvs = uvs or ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))
    data = bytearray(struct.pack("<9I", 0, 0, 0, 0, vert_size, 0, 0,
                                 len(vertices), len(indices)))
    for vertice, uv in zip(vertices, uvs):
        registro = bytearray(vert_size)
        struct.pack_into("<3f", registro, 0, *vertice)
        struct.pack_into("<2f", registro, vert_size - 8, *uv)
        data.extend(registro)
    for indice in indices:
        data.extend(struct.pack("<H", indice))
    return bytes(data)


def ms3_bytes(indices=(0, 1, 2), nan=False):
    vertices = ((math.nan if nan else 0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    header = bytearray(0x74)
    header[0x20:0x28] = b"arma.jit"
    struct.pack_into("<I", header, 0x54, 3)
    struct.pack_into("<I", header, 0x58, 3)
    struct.pack_into("<I", header, 0x5C, 1)
    data = bytearray(header)
    for v in vertices:
        data.extend(struct.pack("<3f3f", *v, 0.0, 0.0, 1.0))
    for uv in ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)):
        data.extend(struct.pack("<2f", *uv))
    data.extend(struct.pack("<3H", *indices))
    return bytes(data)


def jt31_bytes(width=8, height=8, byte=0x5A):
    tamanho = max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * 8
    return b"PREFIXO" + b"JT31" + struct.pack("<II", width, height) + bytes([byte]) * tamanho


def arvore_bytes(raiz):
    raiz = Path(raiz)
    return {
        str(p.relative_to(raiz)).replace(os.sep, "/"): p.read_bytes()
        for p in raiz.rglob("*") if p.is_file()
    }


def executar_fixture(td, modo_seguro=False, extrair_3d=True, extrair_tex=True,
                     progress_callback=None, cancel_callback=None):
    origem = Path(td) / "cliente"
    destino = Path(td) / "saida"
    origem.mkdir(parents=True, exist_ok=True)
    # Classe Atirador, família 11, variantes 01 e 02.
    gravar(origem / "CH03.bon", b"BON-SINTETICO")
    gravar(origem / "CH030383.an2", b"AN2-SINTETICO")
    gravar(origem / "CH03031101.msh", msh_bytes())
    gravar(origem / "CH03041101.msh", msh_bytes(vertices=((0, 0, 0), (2, 0, 0), (0, 2, 0))))
    gravar(origem / "CH03031101.jit", jt31_bytes())
    gravar(origem / "CH03031102.msh", msh_bytes(vertices=((0, 0, 0), (3, 0, 0), (0, 3, 0))))
    # Arma de Atirador: prefixo SM, tipo ABC, id 12345.
    gravar(origem / "SMABC12345.ms3", ms3_bytes())
    gravar(origem / "SMABC12345.jit", jt31_bytes(byte=0x33))
    antes = arvore_bytes(origem)
    stats = exts.organizar_e_converter_aika(
        str(origem), str(destino), modo_seguro, extrair_3d, extrair_tex,
        progress_callback=progress_callback, cancel_callback=cancel_callback,
    )
    return origem, destino, antes, stats


class TestClassificacao(unittest.TestCase):
    def test_todas_as_classes_suportadas_sao_distintas(self):
        self.assertEqual(exts.MAPA_ARMADURAS, {
            "01": "Guerreiro", "02": "Templaria", "03": "Atirador",
            "04": "Dual", "05": "FC", "06": "Cleriga",
        })
        self.assertEqual(len(set(exts.MAPA_ARMADURAS.values())), 6)

    def test_prefixos_de_armas_mapeiam_classes_corretas(self):
        self.assertEqual(exts.MAPA_ARMAS, {
            "FM": "Guerreiro", "FF": "Templaria", "SM": "Atirador",
            "SF": "Dual", "MM": "FC", "MF": "Cleriga",
        })

    def test_familia_variante_e_base(self):
        self.assertEqual(exts.separar_familia_variante("1101"), ("11", "01"))
        self.assertEqual(exts.separar_familia_variante("1102"), ("11", "02"))
        self.assertEqual(exts.separar_familia_variante("1201"), ("12", "01"))

    def test_pecas_e_escopos(self):
        self.assertEqual(exts.PECAS_DO_SET, ["03", "04", "05", "06", "07", "08"])
        self.assertEqual(exts.classificar_aparencia(["03"]), "aparencia_individual")
        self.assertEqual(exts.classificar_aparencia(["03", "04"]), "aparencia_parcial")
        self.assertEqual(exts.classificar_aparencia(["03", "04", "06", "07", "08"]),
                         "completo_5_partes")
        self.assertEqual(exts.classificar_aparencia(exts.PECAS_DO_SET),
                         "completo_6_partes")

    def test_bon_an2_e_rejeicoes(self):
        self.assertEqual(exts.identificar_recurso_classe("CH03.bon"), ("03", "bon"))
        self.assertEqual(exts.identificar_recurso_classe("CH030383.an2"), ("03", "an2"))
        self.assertEqual(exts.identificar_recurso_classe("CH07.bon"), (None, None))
        self.assertEqual(exts.identificar_recurso_classe("CH03qualquer.bon"), (None, None))


class TestMshParaObj(unittest.TestCase):
    def _converter(self, dados):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        caminho = gravar(Path(td.name) / "modelo.msh", dados)
        return caminho, exts.convert_msh_to_obj(caminho)

    def test_valido_vertices_uv_faces(self):
        caminho, (ok, msg) = self._converter(msh_bytes())
        self.assertTrue(ok, msg)
        obj = Path(caminho).with_suffix(".obj").read_text(encoding="cp1252")
        self.assertEqual(sum(l.startswith("v ") for l in obj.splitlines()), 3)
        self.assertEqual(sum(l.startswith("vt ") for l in obj.splitlines()), 3)
        self.assertIn("f 1/1 2/2 3/3", obj)

    def test_truncado_e_pequeno_falham_sem_obj(self):
        for dados in (b"curto", msh_bytes()[:-2]):
            caminho, (ok, _) = self._converter(dados)
            self.assertFalse(ok)
            self.assertFalse(Path(caminho).with_suffix(".obj").exists())

    def test_indice_fora_do_range_falha(self):
        caminho, (ok, _) = self._converter(msh_bytes(indices=(0, 1, 9)))
        self.assertFalse(ok)
        self.assertFalse(Path(caminho).with_suffix(".obj").exists())

    def test_nan_e_infinito_falham(self):
        for valor in (math.nan, math.inf, -math.inf):
            vertices = ((valor, 0, 0), (1, 0, 0), (0, 1, 0))
            caminho, (ok, _) = self._converter(msh_bytes(vertices=vertices))
            self.assertFalse(ok)
            self.assertFalse(Path(caminho).with_suffix(".obj").exists())


class TestMs3ParaObj(unittest.TestCase):
    def _converter(self, dados):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        caminho = gravar(Path(td.name) / "arma.ms3", dados)
        return caminho, exts.convert_ms3_to_obj(caminho)

    def test_valido_gera_obj_com_normais(self):
        caminho, (ok, msg) = self._converter(ms3_bytes())
        self.assertTrue(ok, msg)
        obj = Path(caminho).with_suffix(".obj").read_text(encoding="utf-8")
        self.assertIn("# Textura referenciada: arma.jit", obj)
        self.assertEqual(sum(l.startswith("vn ") for l in obj.splitlines()), 3)
        self.assertIn("f 1/1/1 2/2/2 3/3/3", obj)

    def test_pequeno_truncado_indice_e_nan_falham(self):
        # Trunca abaixo do tamanho mínimo dos dois layouts conhecidos. Cortar
        # apenas dois bytes do layout intercalado ainda forma, legitimamente,
        # um layout indexado estruturalmente completo e não deve ser rejeitado.
        casos = (b"curto", ms3_bytes()[:193], ms3_bytes(indices=(0, 1, 9)),
                 ms3_bytes(nan=True))
        for dados in casos:
            caminho, (ok, _) = self._converter(dados)
            self.assertFalse(ok)
            self.assertFalse(Path(caminho).with_suffix(".obj").exists())


class TestIntegracaoJit(unittest.TestCase):
    def test_organizador_reusa_funcao_canonica(self):
        self.assertIs(exts.extrair_textura_jit, textura.extrair_textura_jit)

    def test_jit_do_organizador_vira_dds_no_local_correto(self):
        with tempfile.TemporaryDirectory() as td:
            _, destino, _, stats = executar_fixture(td, extrair_3d=False)
            dds = destino / "Atirador" / "Familia_Armadura_11" / \
                "Set_Armadura_1101" / "Texture" / "CH03031101.dds"
            self.assertNotIn("erro", stats)
            self.assertTrue(dds.is_file())
            dados = dds.read_bytes()
            self.assertEqual(dados[:4], b"DDS ")
            self.assertEqual(dados[84:88], b"DXT1")


class TestOrganizacaoManifestos(unittest.TestCase):
    def test_arquivos_sinteticos_das_seis_classes_nao_se_misturam(self):
        with tempfile.TemporaryDirectory() as td:
            origem = Path(td) / "cliente"
            destino = Path(td) / "saida"
            origem.mkdir()
            for classe_id in exts.MAPA_ARMADURAS:
                gravar(origem / f"CH{classe_id}031101.msh", msh_bytes())
            stats = exts.organizar_e_converter_aika(
                str(origem), str(destino), False, False, False)
            self.assertNotIn("erro", stats)
            for classe_id, nome_classe in exts.MAPA_ARMADURAS.items():
                esperado = destino / nome_classe / "Familia_Armadura_11" / \
                    "Set_Armadura_1101" / "Mesh" / f"CH{classe_id}031101.msh"
                self.assertTrue(esperado.is_file(), str(esperado))
                arquivos_classe = [p.name for p in (destino / nome_classe).rglob("*.msh")]
                self.assertEqual(arquivos_classe, [f"CH{classe_id}031101.msh"])

    def test_familias_diferentes_ficam_separadas(self):
        with tempfile.TemporaryDirectory() as td:
            origem = Path(td) / "cliente"
            destino = Path(td) / "saida"
            origem.mkdir()
            gravar(origem / "CH03031101.msh", msh_bytes())
            gravar(origem / "CH03031201.msh", msh_bytes())
            stats = exts.organizar_e_converter_aika(
                str(origem), str(destino), False, False, False)
            self.assertNotIn("erro", stats)
            base = destino / "Atirador"
            f11 = json.loads((base / "Familia_Armadura_11" /
                              "family_manifest.json").read_text(encoding="utf-8"))
            f12 = json.loads((base / "Familia_Armadura_12" /
                              "family_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([v["set_id"] for v in f11["variants"]], ["1101"])
            self.assertEqual([v["set_id"] for v in f12["variants"]], ["1201"])

    def test_familias_variantes_armas_e_recursos_compartilhados(self):
        with tempfile.TemporaryDirectory() as td:
            origem, destino, antes, stats = executar_fixture(td)
            base = destino / "Atirador"
            familia = base / "Familia_Armadura_11"
            self.assertTrue((familia / "Set_Armadura_1101").is_dir())
            self.assertTrue((familia / "Set_Armadura_1102").is_dir())
            self.assertFalse((base / "Familia_Armadura_12").exists())
            self.assertTrue((base / "Classe_CH03" / "Rig" / "CH03.bon").is_file())
            self.assertTrue((base / "Classe_CH03" / "Animacoes" / "CH030383.an2").is_file())
            self.assertTrue((base / "Armas" / "ABC_12345" / "Objects" /
                             "SMABC12345.ms3").is_file())
            self.assertEqual(arvore_bytes(origem), antes)
            self.assertEqual(stats["bon_copiados"], 1)
            self.assertEqual(stats["an2_copiados"], 1)

    def test_set_manifest_conteudo_paths_e_derivados(self):
        with tempfile.TemporaryDirectory() as td:
            _, destino, _, _ = executar_fixture(td)
            pasta = destino / "Atirador" / "Familia_Armadura_11" / "Set_Armadura_1101"
            manifest = json.loads((pasta / "set_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["asset_kind"], "set")
            self.assertEqual(manifest["class_code"], "CH03")
            self.assertEqual(manifest["visual_family_id"], "11")
            self.assertEqual(manifest["variant_id"], "01")
            self.assertEqual(manifest["available_parts"], ["03", "04"])
            for secao in ("mesh", "texture", "objects"):
                for rel in manifest["files"][secao]:
                    self.assertTrue((pasta / Path(rel)).is_file(), rel)
            shared = manifest["shared_class_assets"]
            self.assertTrue((pasta / Path(shared["skeleton"])).resolve().is_file())
            self.assertFalse(any(p.suffix.lower() in (".bon", ".an2")
                                 for p in pasta.rglob("*")))

            # O consumidor separa os originais injetáveis dos previews OBJ/DDS.
            info, erro = sinj.ler_manifest_set(str(pasta))
            self.assertIsNone(erro)
            payloads = sinj.listar_arquivos_set(str(pasta), info)
            self.assertTrue(payloads)
            self.assertTrue(all(p["extensao"] in (".msh", ".jit", ".ef")
                                for p in payloads))
            self.assertFalse(any(p["extensao"] in (".obj", ".dds", ".tga")
                                 for p in payloads))

    def test_family_manifest_nao_funde_variantes(self):
        with tempfile.TemporaryDirectory() as td:
            _, destino, _, _ = executar_fixture(td)
            caminho = destino / "Atirador" / "Familia_Armadura_11" / "family_manifest.json"
            manifest = json.loads(caminho.read_text(encoding="utf-8"))
            self.assertEqual(manifest["asset_kind"], "armor_family")
            self.assertEqual(manifest["visual_family_id"], "11")
            self.assertEqual([v["set_id"] for v in manifest["variants"]], ["1101", "1102"])
            self.assertEqual([v["variant_id"] for v in manifest["variants"]], ["01", "02"])

    def test_weapon_manifest_e_payload_nao_inclui_obj_dds(self):
        with tempfile.TemporaryDirectory() as td:
            _, destino, _, _ = executar_fixture(td)
            pasta = destino / "Atirador" / "Armas" / "ABC_12345"
            manifest = json.loads((pasta / "weapon_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["asset_kind"], "weapon")
            self.assertEqual((manifest["weapon_prefix"], manifest["weapon_type"],
                              manifest["weapon_id"]), ("SM", "ABC", "12345"))
            info, erro = sinj.ler_manifest_asset(str(pasta), expected_kind="weapon")
            self.assertIsNone(erro)
            payloads = sinj.listar_arquivos_asset(str(pasta), info)
            self.assertTrue(any(p["extensao"] == ".ms3" for p in payloads))
            self.assertTrue(any(p["extensao"] == ".jit" for p in payloads))
            self.assertFalse(any(p["extensao"] in (".obj", ".dds", ".tga")
                                 for p in payloads))


class TestRerunCaminhosModosCancelamento(unittest.TestCase):
    def test_rerun_atualiza_alterado_e_adiciona_peca(self):
        with tempfile.TemporaryDirectory() as td:
            origem, destino, _, _ = executar_fixture(td, extrair_3d=False, extrair_tex=False)
            alterado = msh_bytes(vertices=((0, 0, 0), (7, 0, 0), (0, 7, 0)))
            gravar(origem / "CH03031101.msh", alterado)
            gravar(origem / "CH03051101.msh", msh_bytes())
            stats = exts.organizar_e_converter_aika(str(origem), str(destino), False, False, False)
            pasta = destino / "Atirador" / "Familia_Armadura_11" / "Set_Armadura_1101"
            self.assertEqual((pasta / "Mesh" / "CH03031101.msh").read_bytes(), alterado)
            manifest = json.loads((pasta / "set_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["available_parts"], ["03", "04", "05"])
            self.assertGreaterEqual(stats["copiados"], 2)

    def test_destino_igual_ou_dentro_da_origem_e_bloqueado(self):
        with tempfile.TemporaryDirectory() as td:
            origem = Path(td) / "origem"
            origem.mkdir()
            gravar(origem / "CH01031101.msh", msh_bytes())
            for destino in (origem, origem / "saida"):
                stats = exts.organizar_e_converter_aika(str(origem), str(destino), False, False, False)
                self.assertIn("erro", stats)
                self.assertIn("não pode", stats["erro"])

    def test_origem_dentro_do_destino_e_valida_sem_loop(self):
        with tempfile.TemporaryDirectory() as td:
            destino = Path(td) / "destino"
            origem = destino / "entrada"
            origem.mkdir(parents=True)
            gravar(origem / "CH01031101.msh", msh_bytes())
            stats = exts.organizar_e_converter_aika(str(origem), str(destino), False, False, False)
            self.assertNotIn("erro", stats)
            self.assertTrue((destino / "Guerreiro" / "Familia_Armadura_11" /
                             "Set_Armadura_1101" / "Mesh" / "CH01031101.msh").is_file())

    def test_turbo_e_seguro_geram_mesma_arvore(self):
        with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
            _, d1, _, s1 = executar_fixture(td1, modo_seguro=False)
            with patch.object(exts.time, "sleep") as dormir:
                _, d2, _, s2 = executar_fixture(td2, modo_seguro=True)
            self.assertEqual(arvore_bytes(d1), arvore_bytes(d2))
            self.assertGreater(dormir.call_count, 0)
            for chave in ("copiados", "msh_convertidos", "ms3_convertidos",
                          "jit_extraidos", "manifestos_criados"):
                self.assertEqual(s1[chave], s2[chave])

    def test_cancelamento_imediato_nao_copia_nem_anuncia_conclusao(self):
        with tempfile.TemporaryDirectory() as td:
            eventos = []
            origem, destino, antes, stats = executar_fixture(
                td, progress_callback=lambda p, t: eventos.append((p, t)),
                cancel_callback=lambda: True)
            self.assertTrue(stats.get("cancelado"))
            self.assertEqual(stats["copiados"], 0)
            self.assertFalse(destino.exists() and any(destino.rglob("*")))
            self.assertEqual(arvore_bytes(origem), antes)
            self.assertFalse(any(p == 1.0 and "concluída" in t.lower() for p, t in eventos))

    def test_progresso_termina_em_um_sem_cancelamento(self):
        with tempfile.TemporaryDirectory() as td:
            eventos = []
            executar_fixture(td, extrair_3d=False, extrair_tex=False,
                             progress_callback=lambda p, t: eventos.append((p, t)))
            self.assertEqual(eventos[0][0], 0.0)
            self.assertEqual(eventos[-1][0], 1.0)
            self.assertIn("concluída", eventos[-1][1].lower())


class TestThreadingECongelamento(unittest.TestCase):
    def test_worker_qthread_chama_backend_com_cancel_callback(self):
        import inspect
        import main
        self.assertTrue(issubclass(main.ExtractorWorker, main.QThread))
        fonte = inspect.getsource(main.ExtractorWorker.run)
        self.assertIn("organizar_e_converter_aika", fonte)
        self.assertIn("cancel_callback=self._cancel_event.is_set", fonte)
        for proibido in ("setText", "QMessageBox", "repaint", "processEvents"):
            self.assertNotIn(proibido, fonte)

    def test_motores_congelados_nao_sao_importados_para_escrita(self):
        # Integração do Organizador deve apenas reutilizar textura; AutoMod não participa.
        fonte = Path(exts.__file__).read_text(encoding="utf-8")
        self.assertNotIn("import automod", fonte)
        self.assertIn("from textura import extrair_textura_jit", fonte)


if __name__ == "__main__":
    unittest.main(verbosity=2)