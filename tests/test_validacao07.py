# -*- coding: utf-8 -*-
"""Validação 07 — Injetor de Sets/Armas, somente TemporaryDirectory/mocks."""
import hashlib
import inspect
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import automod  # noqa: E402
import set_injector as sinj  # noqa: E402


def gravar(caminho, dados):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(dados)
    return caminho


def hash_bytes(dados):
    return hashlib.sha256(dados).hexdigest()


def arquivos_bytes(raiz):
    raiz = Path(raiz)
    return {str(p.relative_to(raiz)): p.read_bytes()
            for p in raiz.rglob("*") if p.is_file()}


def criar_asset_set(base, set_id, *, classe="03", partes=("03",),
                    extensoes=(".msh", ".jit", ".ef"), derivados=True,
                    nome_classe="Atirador"):
    familia, variante = set_id[:2], set_id[2:]
    pasta = Path(base) / nome_classe / f"Familia_Armadura_{familia}" / f"Set_Armadura_{set_id}"
    mesh, texture = [], []
    for parte in partes:
        stem = f"CH{classe}{parte}{set_id}"
        for ext in extensoes:
            sub = "Mesh" if ext == ".msh" else "Texture"
            rel = f"{sub}/{stem}{ext}"
            gravar(pasta / rel, f"SET-{set_id}-{parte}-{ext}".encode())
            (mesh if sub == "Mesh" else texture).append(rel)
        if derivados:
            gravar(pasta / "Mesh" / f"{stem}.obj", b"OBJ-DERIVADO")
            gravar(pasta / "Texture" / f"{stem}.dds", b"DDS-DERIVADO")
            gravar(pasta / "Texture" / f"{stem}.tga", b"TGA-DERIVADO")
            gravar(pasta / "Texture" / f"{stem}.png", b"PNG-DERIVADO")
            mesh.append(f"Mesh/{stem}.obj")
            texture.extend((f"Texture/{stem}.dds", f"Texture/{stem}.tga",
                            f"Texture/{stem}.png"))
    manifesto = {
        "schema_version": 1, "asset_kind": "set", "set_id": set_id,
        "visual_family_id": familia, "variant_id": variante,
        "class_code": f"CH{classe}", "class_name": nome_classe,
        "files": {"mesh": mesh, "texture": texture, "objects": []},
    }
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "set_manifest.json").write_text(
        json.dumps(manifesto, indent=2), encoding="utf-8")
    return pasta


def criar_asset_arma(base, prefixo, tipo, ident, *,
                     extensoes=(".ms3", ".jit", ".ef"), derivados=True,
                     nome_classe=None):
    nome_classe = nome_classe or sinj.MAPA_ARMAS[prefixo]
    pasta = Path(base) / nome_classe / "Armas" / f"{tipo}_{ident}"
    objects, texture = [], []
    stem = f"{prefixo}{tipo}{ident}"
    for ext in extensoes:
        sub = "Objects" if ext == ".ms3" else "Texture"
        rel = f"{sub}/{stem}{ext}"
        gravar(pasta / rel, f"WEAPON-{stem}-{ext}".encode())
        (objects if sub == "Objects" else texture).append(rel)
    if derivados:
        gravar(pasta / "Objects" / f"{stem}.obj", b"OBJ-DERIVADO")
        gravar(pasta / "Texture" / f"{stem}.dds", b"DDS-DERIVADO")
        gravar(pasta / "Texture" / f"{stem}.tga", b"TGA-DERIVADO")
        gravar(pasta / "Texture" / f"{stem}.png", b"PNG-DERIVADO")
        objects.append(f"Objects/{stem}.obj")
        texture.extend((f"Texture/{stem}.dds", f"Texture/{stem}.tga",
                        f"Texture/{stem}.png"))
    manifesto = {
        "schema_version": 1, "asset_kind": "weapon",
        "weapon_prefix": prefixo, "weapon_type": tipo, "weapon_id": ident,
        "class_code": prefixo, "class_name": nome_classe,
        "files": {"objects": objects, "texture": texture},
    }
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "weapon_manifest.json").write_text(
        json.dumps(manifesto, indent=2), encoding="utf-8")
    return pasta


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = Path(self.td.name)
        self.organizados = self.root / "organizados"
        self.backups = self.root / "backups"
        self.history = {}

        def normalize(p=None):
            return os.path.abspath(os.path.normpath(str(p or self.root / "ClienteA")))

        def backup_dir(p=None, criar=True):
            key = hashlib.sha256(normalize(p).encode()).hexdigest()[:16]
            path = self.backups / key
            if criar:
                path.mkdir(parents=True, exist_ok=True)
            return str(path)

        def criar_index(p):
            return Path(p).is_dir()

        def carregar_index(p):
            index = {}
            for i, arquivo in enumerate(Path(p).rglob("*")):
                if arquivo.is_file():
                    index[f"{i}:{arquivo.name.lower()}"] = str(arquivo)
            return index

        def backup(origem, destino):
            try:
                destino = Path(destino)
                if destino.is_file():
                    return destino.stat().st_size > 0
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(origem, destino)
                return destino.is_file() and destino.read_bytes() == Path(origem).read_bytes()
            except OSError:
                return False

        def carregar_hist(p=None):
            key = normalize(p)
            return json.loads(json.dumps(self.history.get(
                key, {"version": 2, "game_root": key, "items": {}})))

        def salvar_hist(dados, p=None):
            key = normalize(p or dados.get("game_root"))
            self.history[key] = json.loads(json.dumps(dados))
            return True

        def registrar(destino, mod, p=None, mod_nome=None, categoria=None):
            key = normalize(p)
            dados = carregar_hist(key)
            rel = os.path.relpath(destino, key).replace("\\", "/")
            dados["items"][rel.lower()] = {
                "target_relpath": rel, "backup_relpath": rel,
                "target_name": os.path.basename(destino),
                "mod_name": mod_nome or os.path.basename(mod),
                "category": categoria, "game_root": key, "last_applied": "TESTE",
            }
            return salvar_hist(dados, key)

        patches = [
            patch.object(sinj, "normalizar_pasta_jogo", side_effect=normalize),
            patch.object(sinj, "obter_pasta_backup_cliente", side_effect=backup_dir),
            patch.object(sinj, "criar_index_jogo", side_effect=criar_index),
            patch.object(sinj, "carregar_index_jogo", side_effect=carregar_index),
            patch.object(sinj, "fazer_backup_rapido", side_effect=backup),
            patch.object(sinj, "carregar_historico_automod", side_effect=carregar_hist),
            patch.object(sinj, "salvar_historico_automod", side_effect=salvar_hist),
            patch.object(sinj, "registrar_mod_ativo", side_effect=registrar),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.normalize, self.backup_dir = normalize, backup_dir

    def validar(self, pasta, kind):
        info, erro = sinj.SetInjectorWorker().validar_pasta(str(pasta), kind)
        self.assertIsNone(erro, erro)
        return info

    def preparar(self, doador, alvo, kind="set"):
        di, ai = self.validar(doador, kind), self.validar(alvo, kind)
        staging = self.root / f"staging_{kind}"
        manifesto, ignorados, erro = sinj.SetInjectorWorker().preparar(
            di, ai, str(staging))
        self.assertIsNone(erro, erro)
        mapeados, _ = sinj.criar_mapa_para_infos(di, ai)
        return di, ai, staging, manifesto, ignorados, mapeados

    def cliente_com_alvos(self, info_alvo, nome="ClienteA"):
        cliente = self.root / nome
        for item in info_alvo["arquivos"]:
            gravar(cliente / "Data" / item["basename"],
                   b"CLIENTE-ORIGINAL-" + item["basename"].encode())
        return cliente


class TestPayloadManifestos(Sandbox):
    def test_01_set_aceita_msh_jit_ef(self):
        p = criar_asset_set(self.organizados, "1101")
        info = self.validar(p, "set")
        self.assertEqual({a["extensao"] for a in info["arquivos"]},
                         {".msh", ".jit", ".ef"})

    def test_02_set_ignora_obj_dds_tga_png(self):
        info = self.validar(criar_asset_set(self.organizados, "1101"), "set")
        self.assertFalse({".obj", ".dds", ".tga", ".png"} &
                         {a["extensao"] for a in info["arquivos"]})

    def test_03_arma_aceita_ms3_jit_ef(self):
        info = self.validar(criar_asset_arma(self.organizados, "SM", "RIF", "00001"), "weapon")
        self.assertEqual({a["extensao"] for a in info["arquivos"]},
                         {".ms3", ".jit", ".ef"})

    def test_04_arma_ignora_obj_dds_tga_png(self):
        info = self.validar(criar_asset_arma(self.organizados, "SM", "RIF", "00001"), "weapon")
        self.assertFalse({".obj", ".dds", ".tga", ".png"} &
                         {a["extensao"] for a in info["arquivos"]})

    def test_05_msh_nao_entra_em_arma(self):
        p = criar_asset_arma(self.organizados, "SM", "RIF", "00001")
        gravar(p / "Objects" / "SMRIF00001.msh", b"MSH")
        m = json.loads((p / "weapon_manifest.json").read_text())
        m["files"]["objects"].append("Objects/SMRIF00001.msh")
        (p / "weapon_manifest.json").write_text(json.dumps(m))
        info = self.validar(p, "weapon")
        self.assertNotIn(".msh", {a["extensao"] for a in info["arquivos"]})

    def test_06_ms3_nao_entra_em_set(self):
        p = criar_asset_set(self.organizados, "1101")
        gravar(p / "Mesh" / "CH03031101.ms3", b"MS3")
        m = json.loads((p / "set_manifest.json").read_text())
        m["files"]["mesh"].append("Mesh/CH03031101.ms3")
        (p / "set_manifest.json").write_text(json.dumps(m))
        info = self.validar(p, "set")
        self.assertNotIn(".ms3", {a["extensao"] for a in info["arquivos"]})

    def test_07_manifesto_set_valido_consumido(self):
        p = criar_asset_set(self.organizados, "1203", partes=("03", "06"))
        info = self.validar(p, "set")
        self.assertEqual((info["class_code"], info["visual_family_id"],
                          info["variant_id"], info["set_id"]),
                         ("CH03", "12", "03", "1203"))
        self.assertEqual(info["available_parts"], ["03", "06"])

    def test_08_manifesto_arma_valido_dois_prefixos(self):
        sm = self.validar(criar_asset_arma(self.organizados, "SM", "RIF", "00001"), "weapon")
        fm = self.validar(criar_asset_arma(self.organizados, "FM", "SWD", "00002"), "weapon")
        self.assertEqual((sm["weapon_prefix"], sm["weapon_type"]), ("SM", "RIF"))
        self.assertEqual((fm["weapon_prefix"], fm["weapon_type"]), ("FM", "SWD"))

    def test_09_modo_set_arma_sao_incompativeis(self):
        p = criar_asset_arma(self.organizados, "SM", "RIF", "00001")
        info, erro = sinj.SetInjectorWorker().validar_pasta(str(p), "set")
        self.assertIsNone(info)
        self.assertIn("Modo incompatível", erro)

    def test_10_manifesto_invalido_retorna_erro_sem_exception(self):
        p = self.organizados / "Atirador" / "Familia_Armadura_11" / "Set_Armadura_1101"
        p.mkdir(parents=True)
        (p / "set_manifest.json").write_text("{invalido", encoding="utf-8")
        info, erro = sinj.SetInjectorWorker().validar_pasta(str(p), "set")
        self.assertIsNone(info)
        self.assertIn("Manifesto inválido", erro)

    def test_11_manifesto_contraditorio_com_diretorio_e_rejeitado(self):
        p = criar_asset_set(self.organizados, "1101")
        errado = p.parent / "Set_Armadura_9999"
        p.rename(errado)
        info, erro = sinj.SetInjectorWorker().validar_pasta(str(errado), "set")
        self.assertIsNone(info)
        self.assertIsNotNone(erro)

    def test_11b_familia_ou_classe_do_diretorio_contraditoria_rejeitada(self):
        p = criar_asset_set(self.organizados, "1101")
        destino = self.organizados / "Guerreiro" / "Familia_Armadura_99" / p.name
        destino.parent.mkdir(parents=True)
        p.rename(destino)
        info, erro = sinj.SetInjectorWorker().validar_pasta(str(destino), "set")
        self.assertIsNone(info)
        self.assertIn("contradiz", erro)

    def test_11c_diretorio_tecnico_de_arma_contraditorio_rejeitado(self):
        p = criar_asset_arma(self.organizados, "SM", "RIF", "00001")
        destino = p.parent / "RIF_99999"
        p.rename(destino)
        info, erro = sinj.SetInjectorWorker().validar_pasta(str(destino), "weapon")
        self.assertIsNone(info)
        self.assertIn("contradiz", erro)

    def test_11d_manifesto_stale_com_nativo_ausente_rejeitado(self):
        p = criar_asset_set(self.organizados, "1101")
        (p / "Mesh" / "CH03031101.msh").unlink()
        info, erro = sinj.SetInjectorWorker().validar_pasta(str(p), "set")
        self.assertIsNone(info)
        self.assertIn("não encontrado", erro)

    def test_11e_path_nativo_fora_da_pasta_asset_rejeitado(self):
        p = criar_asset_set(self.organizados, "1101")
        externo = gravar(p.parent / "CH03031101.msh", b"EXTERNO")
        manifesto = json.loads((p / "set_manifest.json").read_text())
        manifesto["files"]["mesh"] = ["../CH03031101.msh"]
        (p / "set_manifest.json").write_text(json.dumps(manifesto))
        info, erro = sinj.SetInjectorWorker().validar_pasta(str(p), "set")
        self.assertIsNone(info)
        self.assertIn("fora da pasta", erro)

    def test_11f_secao_files_invalida_retorna_erro_controlado(self):
        p = criar_asset_set(self.organizados, "1101")
        manifesto = json.loads((p / "set_manifest.json").read_text())
        manifesto["files"] = ["não", "é", "objeto"]
        (p / "set_manifest.json").write_text(json.dumps(manifesto))
        info, erro = sinj.SetInjectorWorker().validar_pasta(str(p), "set")
        self.assertIsNone(info)
        self.assertIn("files", erro)

    def test_11g_asset_kind_contraditorio_com_manifesto_rejeitado(self):
        p = criar_asset_set(self.organizados, "1101")
        manifesto = json.loads((p / "set_manifest.json").read_text())
        manifesto.update({
            "asset_kind": "weapon", "weapon_prefix": "SM",
            "weapon_type": "RIF", "weapon_id": "00001",
            "class_code": "SM",
        })
        (p / "set_manifest.json").write_text(json.dumps(manifesto))
        # Move para uma hierarquia cujo nome seria válido para a identidade de
        # arma. Assim a rejeição depende do tipo do arquivo de manifesto, não
        # de uma divergência acidental no nome do diretório.
        destino = self.organizados / "Atirador" / "Armas" / "RIF_00001"
        destino.parent.mkdir(parents=True, exist_ok=True)
        p.rename(destino)
        info, erro = sinj.ler_manifest_asset(str(destino), expected_kind="set")
        self.assertIsNone(info)
        self.assertIn("tipo", erro.lower())


class TestPreparacaoSimulacao(Sandbox):
    def _set_pair(self):
        return (criar_asset_set(self.organizados / "d", "1101", partes=("03", "04")),
                criar_asset_set(self.organizados / "a", "1202", partes=("03", "04")))

    def _weapon_pair(self):
        return (criar_asset_arma(self.organizados / "d", "SM", "RIF", "00001"),
                criar_asset_arma(self.organizados / "a", "SM", "RIF", "00002"))

    def test_12_preparacao_set_nao_altera_cliente_nem_organizado(self):
        d, a = self._set_pair(); cliente = self.root / "ClienteA"; cliente.mkdir()
        antes_d, antes_a, antes_c = arquivos_bytes(d), arquivos_bytes(a), arquivos_bytes(cliente)
        _, _, staging, manifest, _, _ = self.preparar(d, a)
        self.assertEqual((arquivos_bytes(d), arquivos_bytes(a), arquivos_bytes(cliente)),
                         (antes_d, antes_a, antes_c))
        self.assertTrue((staging / "staging_manifest.json").is_file())
        self.assertEqual(manifest["total_preparados"], 6)

    def test_13_preparacao_arma_copia_so_nativos(self):
        _, _, staging, manifest, _, _ = self.preparar(*self._weapon_pair(), kind="weapon")
        exts = {p.suffix.lower() for p in staging.iterdir() if p.is_file()}
        self.assertTrue({".ms3", ".jit", ".ef"}.issubset(exts))
        self.assertFalse({".obj", ".dds", ".tga", ".png"} & exts)
        self.assertEqual(manifest["total_preparados"], 3)

    def test_14_ausencia_legitima_nao_inventa_peca(self):
        d = criar_asset_set(self.organizados / "d", "1101", partes=("03", "05"))
        a = criar_asset_set(self.organizados / "a", "1201", partes=("03",))
        di, ai = self.validar(d, "set"), self.validar(a, "set")
        mapeados, ignorados = sinj.criar_mapa_para_infos(di, ai)
        self.assertTrue(all(x["doador"]["parte"] == "03" for x in mapeados))
        self.assertTrue(any(x["arquivo"].get("parte") == "05" for x in ignorados
                            if isinstance(x.get("arquivo"), dict)))

    def test_15_simulacao_set_read_only(self):
        d, a = self._set_pair(); _, ai, staging, _, _, mapped = self.preparar(d, a)
        cliente = self.cliente_com_alvos(ai)
        antes = arquivos_bytes(cliente); backup_antes = arquivos_bytes(self.backups)
        plano = sinj.simular_injecao(mapped, str(cliente))
        self.assertNotIn("erro", plano)
        self.assertEqual(plano["total"], len(mapped))
        self.assertEqual(arquivos_bytes(cliente), antes)
        self.assertEqual(arquivos_bytes(self.backups), backup_antes)
        self.assertFalse(self.history)

    def test_16_simulacao_arma_read_only(self):
        d, a = self._weapon_pair(); _, ai, _, _, _, mapped = self.preparar(d, a, "weapon")
        cliente = self.cliente_com_alvos(ai)
        antes = arquivos_bytes(cliente)
        plano = sinj.simular_injecao(mapped, str(cliente))
        self.assertEqual(plano["total"], 3)
        self.assertEqual(arquivos_bytes(cliente), antes)

    def test_17_destino_inexistente_e_informado(self):
        d, a = self._set_pair(); _, ai, _, _, _, mapped = self.preparar(d, a)
        cliente = self.cliente_com_alvos(ai)
        alvo = next(cliente.rglob(mapped[0]["alvo"]["basename"])); alvo.unlink()
        plano = sinj.simular_injecao(mapped, str(cliente))
        self.assertTrue(plano["ignorados"])
        self.assertIn("não encontrado", plano["ignorados"][0]["motivo"])

    def test_18_basename_ambiguo_nao_escolhe_primeiro(self):
        d, a = self._set_pair(); _, ai, _, _, _, mapped = self.preparar(d, a)
        cliente = self.cliente_com_alvos(ai)
        nome = mapped[0]["alvo"]["basename"]
        gravar(cliente / "Outro" / nome, b"DUPLICADO")
        plano = sinj.simular_injecao(mapped, str(cliente))
        self.assertIn("ambíguo", plano["erro"])

    def test_19_path_fora_do_cliente_e_filtrado(self):
        cliente = self.root / "ClienteA"; cliente.mkdir()
        dentro = gravar(cliente / "Data" / "alvo.msh", b"DENTRO")
        fora = gravar(self.root / "fora" / "alvo.msh", b"FORA")
        with patch.object(sinj, "carregar_index_jogo",
                          return_value={"in": str(dentro), "out": str(fora)}):
            index, _, erro = sinj._carregar_indice_cliente_atualizado(str(cliente))
        self.assertIsNone(erro)
        self.assertEqual(index, {"alvo.msh": str(dentro)})

    def test_20_cliente_inexistente_rejeitado(self):
        plano = sinj.simular_injecao([], str(self.root / "inexistente"))
        self.assertIn("erro", plano)


class TestTransacaoHistoricoRestore(Sandbox):
    def _cenario(self, kind="set", count_parts=("03",)):
        if kind == "set":
            d = criar_asset_set(self.organizados / "d", "1101", partes=count_parts)
            a = criar_asset_set(self.organizados / "a", "1201", partes=count_parts)
        else:
            d = criar_asset_arma(self.organizados / "d", "SM", "RIF", "00001")
            a = criar_asset_arma(self.organizados / "a", "SM", "RIF", "00002")
        _, ai, staging, _, _, mapped = self.preparar(d, a, kind)
        cliente = self.cliente_com_alvos(ai)
        return cliente, ai, staging, mapped

    def test_21_cliente_b_ativo_nunca_escreve_a(self):
        cliente_b, ai, staging, mapped = self._cenario()
        cliente_a = self.cliente_com_alvos(ai, "ClienteOutro")
        antes_a = arquivos_bytes(cliente_a)
        resultado, erro = sinj.injetar_set(mapped, str(staging), str(cliente_b))
        self.assertIsNone(erro, erro)
        self.assertEqual(resultado["total_substituidos"], len(mapped))
        self.assertEqual(arquivos_bytes(cliente_a), antes_a)

    def test_22_backup_falho_impede_qualquer_escrita(self):
        cliente, _, staging, mapped = self._cenario(count_parts=("03", "04"))
        antes = arquivos_bytes(cliente)
        with patch.object(sinj, "fazer_backup_rapido", return_value=False), \
             patch.object(sinj, "_copiar_atomico_validado") as copiar:
            resultado, erro = sinj.injetar_set(mapped, str(staging), str(cliente))
        self.assertIsNone(resultado); self.assertIn("backup", erro.lower())
        copiar.assert_not_called(); self.assertEqual(arquivos_bytes(cliente), antes)

    def test_23_todos_backups_antes_da_primeira_escrita(self):
        cliente, _, staging, mapped = self._cenario(count_parts=("03", "04"))
        eventos=[]; real_backup=sinj.fazer_backup_rapido; real_copy=sinj._copiar_atomico_validado
        def backup(o,d): eventos.append("backup"); return real_backup(o,d)
        def copy(o,d,h=None): eventos.append("write"); return real_copy(o,d,h)
        with patch.object(sinj, "fazer_backup_rapido", side_effect=backup), \
             patch.object(sinj, "_copiar_atomico_validado", side_effect=copy):
            resultado, erro = sinj.injetar_set(mapped, str(staging), str(cliente))
        self.assertIsNone(erro, erro); self.assertIsNotNone(resultado)
        primeiro_write = eventos.index("write")
        self.assertEqual(eventos[:primeiro_write], ["backup"] * len(mapped))

    def test_24_backup_preexistente_vazio_impede_escrita(self):
        cliente, _, staging, mapped = self._cenario()
        alvo = next(cliente.rglob(mapped[0]["alvo"]["basename"]))
        backup = Path(self.backup_dir(cliente)) / alvo.relative_to(cliente)
        gravar(backup, b"")
        antes = arquivos_bytes(cliente)
        resultado, erro = sinj.injetar_set(mapped, str(staging), str(cliente))
        self.assertIsNone(resultado)
        self.assertIsNotNone(erro)
        self.assertEqual(arquivos_bytes(cliente), antes)

    def test_25_falha_no_meio_provoca_rollback_total(self):
        cliente, _, staging, mapped = self._cenario(count_parts=("03", "04"))
        antes = arquivos_bytes(cliente); real=sinj._copiar_atomico_validado; n={"v":0}
        def falhar(o,d,h=None):
            n["v"] += 1
            if n["v"] == 3: raise OSError("falha no terceiro")
            return real(o,d,h)
        with patch.object(sinj, "_copiar_atomico_validado", side_effect=falhar):
            resultado, erro = sinj.injetar_set(mapped, str(staging), str(cliente))
        self.assertIsNone(resultado); self.assertIn("rollback OK", erro)
        self.assertEqual(arquivos_bytes(cliente), antes)
        self.assertFalse(self.history)

    def test_26_hash_final_e_validado(self):
        with tempfile.TemporaryDirectory() as td:
            origem=gravar(Path(td)/"o", b"NOVO"); destino=gravar(Path(td)/"d", b"VELHO")
            with self.assertRaisesRegex(OSError, "hash"):
                sinj._copiar_atomico_validado(str(origem), str(destino), hash_bytes(b"OUTRO"))

    def test_27_historico_somente_apos_sucesso(self):
        cliente, _, staging, mapped = self._cenario()
        resultado, erro = sinj.injetar_set(mapped, str(staging), str(cliente))
        self.assertIsNone(erro, erro); self.assertIsNotNone(resultado)
        itens = self.history[self.normalize(cliente)]["items"]
        self.assertEqual(len(itens), len(mapped))
        self.assertEqual({x["category"] for x in itens.values()}, {"set"})

    def test_28_falha_historico_reverte_arquivos_e_historico(self):
        cliente, _, staging, mapped = self._cenario()
        antes=arquivos_bytes(cliente); calls={"n":0}
        def registrar(*args,**kwargs): calls["n"]+=1; return False
        with patch.object(sinj, "registrar_mod_ativo", side_effect=registrar):
            resultado, erro=sinj.injetar_set(mapped,str(staging),str(cliente))
        self.assertIsNone(resultado); self.assertIn("histórico", erro)
        self.assertEqual(arquivos_bytes(cliente), antes)

    def _restore(self, kind):
        cliente, _, staging, mapped = self._cenario(kind)
        originals=arquivos_bytes(cliente)
        resultado, erro=sinj.injetar_set(mapped,str(staging),str(cliente))
        self.assertIsNone(erro, erro)
        # Exercita o contrato canônico de restore com o mesmo namespace temporário.
        with patch.object(automod, "normalizar_pasta_jogo", side_effect=self.normalize), \
             patch.object(automod, "obter_pasta_backup_cliente", side_effect=self.backup_dir), \
             patch.object(automod, "carregar_historico_automod",
                          side_effect=lambda p=None: json.loads(json.dumps(self.history.get(self.normalize(p), {"version":2,"game_root":self.normalize(p),"items":{}})))), \
             patch.object(automod, "salvar_historico_automod", return_value=True):
            for item in resultado["substituidos"]:
                rel=os.path.relpath(item["destino"], cliente).replace("\\","/")
                ok,msg=automod.restaurar_mod_individual(rel.lower(),str(cliente))
                self.assertTrue(ok,msg)
        self.assertEqual(arquivos_bytes(cliente), originals)

    def test_29_restore_set_funciona(self): self._restore("set")
    def test_30_restore_arma_funciona(self): self._restore("weapon")

    def test_31_restore_nao_cruza_clientes(self):
        cliente_a, ai, staging, mapped = self._cenario()
        resultado, erro=sinj.injetar_set(mapped,str(staging),str(cliente_a)); self.assertIsNone(erro)
        cliente_b=self.cliente_com_alvos(ai,"ClienteB"); antes=arquivos_bytes(cliente_b)
        self.assertNotEqual(self.backup_dir(cliente_a), self.backup_dir(cliente_b))
        self.assertEqual(arquivos_bytes(cliente_b), antes)


class TestUiThreading(unittest.TestCase):
    def test_32_jogo_aberto_bloqueia_antes_do_worker(self):
        import main
        win=main.AikaOptimizerPro.__new__(main.AikaOptimizerPro)
        win._inj_preparado=True; win._inj_mapeados=[{"x":1}]; win._inj_staging="staging"
        win._inj_modo="set"; win.executar_em_background=MagicMock()
        win._inj_cliente_destino="C:\\cliente_teste"
        win._inj_cliente_simulado="C:\\cliente_teste"
        win._inj_simulacao_total=1
        with patch("main.opt.jogo_esta_aberto", return_value=True), \
             patch.object(main.AikaOptimizerPro, "_validar_cliente_destino_injetor",
                          return_value=("C:\\cliente_teste", None)), \
             patch("main.QMessageBox.warning") as aviso, \
             patch("main.QMessageBox.question") as pergunta:
            win.acao_injetar_set()
        aviso.assert_called_once(); pergunta.assert_not_called()
        win.executar_em_background.assert_not_called()

    def test_33_exception_worker_e_capturada_em_signal(self):
        import main
        erros=[]
        worker=main.TarefaWorker(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        worker.erro.connect(erros.append); worker.run()
        self.assertEqual(erros,["boom"])

    def test_34_worker_backend_nao_toca_qwidget(self):
        fonte=inspect.getsource(sinj.SetInjectorWorker)
        for proibido in ("QWidget", "QMessageBox", "setText", "setPlainText", "show()"):
            self.assertNotIn(proibido, fonte)

    def test_35_handlers_usam_background_e_guard(self):
        import main
        fonte_p=inspect.getsource(main.AikaOptimizerPro.acao_preparar_set)
        fonte_s=inspect.getsource(main.AikaOptimizerPro.acao_simular_injecao)
        fonte_i=inspect.getsource(main.AikaOptimizerPro.acao_injetar_set)
        self.assertIn("_executar_operacao_injetor", fonte_p)
        self.assertIn("_executar_operacao_injetor", fonte_s)
        self.assertIn("_executar_operacao_injetor", fonte_i)
        self.assertIn("jogo_esta_aberto", fonte_i)


if __name__ == "__main__":
    unittest.main(verbosity=2)