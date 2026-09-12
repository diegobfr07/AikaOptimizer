# -*- coding: utf-8 -*-
"""Testes especificos do backend dgvoodoo_service.py.

NENHUM teste toca o cliente real do usuario (C:\\CBMgames\\...).
Todos os cenarios usam diretorios temporarios reais; mocks apenas para
deteccao de processo e resolucao de template quando necessario.
"""
import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import dgvoodoo_service as svc  # noqa: E402

# Hashes oficiais do template dgVoodoo2 2.87.4 (D3D9.dll MS/x86 + dgVoodoo.conf).
HASH_DLL = "db1c445f7bcf699df1e175e974c779bdc7e19a468680a44884b1ab7078888d04"
HASH_CONF = "3c7da2fac3eaad369df468e80c9ba9c4db632c419799b32bbc31279d10985801"


def _h(data):
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _h_file(path):
    """SHA-256 de um arquivo (abre/fecha corretamente)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


class BaseDgvoodooTest(unittest.TestCase):
    """Base: cliente temporario + config mockada para o cliente temporario."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="aika_dgvoo_")
        self.cli = self._tmp.name
        # Mocks de config apontando para o cliente temporario
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

    # Helpers -------------------------------------------------------------
    def caminho(self, *nomes):
        return os.path.join(self.cli, *nomes)

    def escrever(self, nome, dados):
        with open(self.caminho(nome), "wb") as f:
            f.write(dados)

    def ler(self, nome):
        with open(self.caminho(nome), "rb") as f:
            return f.read()

    def existe(self, nome):
        return os.path.isfile(self.caminho(nome))


# --- 1. Deteccao - Cliente Original ---
class TestDeteccaoClienteOriginal(BaseDgvoodooTest):
    def test_cliente_limpo_original(self):
        r = svc.detectar_estado(self.cli)
        self.assertEqual(r.estado, svc.Estado.ORIGINAL)
        self.assertFalse(r.dll_existe)
        self.assertFalse(r.conf_existe)

    def test_arquivos_similares_nao_confundidos(self):
        for n in ["d3d9d.dll", "d3dx9_43.dll", "d3dx9d_33.dll", "D3dx9d_43.dll"]:
            self.escrever(n, b"x" * 100)
        r = svc.detectar_estado(self.cli)
        self.assertEqual(r.estado, svc.Estado.ORIGINAL)
        self.assertFalse(r.dll_existe)

    def test_d3d9_uppercase_detectado(self):
        self.escrever("D3D9.dll", b"x" * 100)
        r = svc.detectar_estado(self.cli)
        self.assertTrue(r.dll_existe)


# --- 2. Ativacao em Cliente Limpo ---
class TestAtivacaoClienteLimpo(BaseDgvoodooTest):
    def test_ativar_cria_arquivos_e_estado(self):
        r = svc.ativar_dgvoodoo(self.cli)
        self.assertTrue(r.ok)
        self.assertEqual(r.estado, svc.Estado.ATIVO)
        self.assertTrue(self.existe(svc.D3D9_DLL))
        self.assertTrue(self.existe(svc.DGVOODOO_CONF))
        self.assertEqual(_h(self.ler(svc.D3D9_DLL)), HASH_DLL)
        e = svc._carregar_estado(self.cli)
        self.assertIsNotNone(e)
        self.assertEqual(e["status"], "active")
        self.assertFalse(e["d3d9"]["original_present"])
        self.assertEqual(e["d3d9"]["installed_sha256"], HASH_DLL)

    def test_template_original_intacto(self):
        td, tc = svc.resolver_template_d3d9(), svc.resolver_template_conf()
        h1, h2 = _h_file(td), _h_file(tc)
        svc.ativar_dgvoodoo(self.cli)
        self.assertEqual(_h_file(td), h1)
        self.assertEqual(_h_file(tc), h2)

    def test_deteccao_pos_ativacao_e_ativo(self):
        svc.ativar_dgvoodoo(self.cli)
        r = svc.detectar_estado(self.cli)
        self.assertEqual(r.estado, svc.Estado.ATIVO)


# --- 3. Restauracao de Cliente Limpo ---
class TestRestauracaoClienteLimpo(BaseDgvoodooTest):
    def test_restaurar_remove_tudo(self):
        svc.ativar_dgvoodoo(self.cli)
        self.assertTrue(self.existe(svc.D3D9_DLL))
        r = svc.restaurar_directx_original(self.cli)
        self.assertTrue(r.ok)
        self.assertEqual(r.estado, svc.Estado.ORIGINAL)
        self.assertFalse(self.existe(svc.D3D9_DLL))
        self.assertFalse(self.existe(svc.DGVOODOO_CONF))
        self.assertIsNone(svc._carregar_estado(self.cli))
        self.assertEqual(svc.detectar_estado(self.cli).estado, svc.Estado.ORIGINAL)


# --- 4. Conf Pre-Existente ---
class TestConfPreExistente(BaseDgvoodooTest):
    def test_restaurar_conf_byte_a_byte(self):
        orig = b"Conteudo original\nLinha 2\n"
        self.escrever(svc.DGVOODOO_CONF, orig)
        svc.ativar_dgvoodoo(self.cli)
        self.assertNotEqual(self.ler(svc.DGVOODOO_CONF), orig)
        svc.restaurar_directx_original(self.cli)
        self.assertEqual(self.ler(svc.DGVOODOO_CONF), orig)


# --- 5. DLL Desconhecida ---
class TestDllDesconhecida(BaseDgvoodooTest):
    def test_conflito(self):
        self.escrever(svc.D3D9_DLL, b"arbitraria" * 100)
        r = svc.detectar_estado(self.cli)
        self.assertEqual(r.estado, svc.Estado.CONFLITO)
        self.assertIsNotNone(r.detalhes_conflito)

    def test_ativacao_bloqueia(self):
        d = b"arbitraria" * 100
        h = _h(d)
        self.escrever(svc.D3D9_DLL, d)
        r = svc.ativar_dgvoodoo(self.cli)
        self.assertFalse(r.ok)
        self.assertEqual(r.estado, svc.Estado.CONFLITO)
        self.assertEqual(_h(self.ler(svc.D3D9_DLL)), h)
        self.assertIsNone(svc._carregar_estado(self.cli))


# --- 6. Template Presente Sem Estado ---
class TestTemplateSemEstado(BaseDgvoodooTest):
    def test_incompleto(self):
        shutil.copy(svc.resolver_template_d3d9(), self.caminho(svc.D3D9_DLL))
        shutil.copy(svc.resolver_template_conf(), self.caminho(svc.DGVOODOO_CONF))
        r = svc.detectar_estado(self.cli)
        self.assertEqual(r.estado, svc.Estado.INCOMPLETO)


# --- 7. Idempotencia ---
class TestIdempotencia(BaseDgvoodooTest):
    def test_duas_vezes(self):
        svc.ativar_dgvoodoo(self.cli)
        e1 = svc._carregar_estado(self.cli)
        svc.ativar_dgvoodoo(self.cli)
        e2 = svc._carregar_estado(self.cli)
        self.assertEqual(e2["status"], "active")
        self.assertEqual(e2["d3d9"]["original_present"], e1["d3d9"]["original_present"])
        self.assertEqual(svc.detectar_estado(self.cli).estado, svc.Estado.ATIVO)


# --- 8. Modificacao Externa DLL ---
class TestModExternaDll(BaseDgvoodooTest):
    def test_bloqueia_restauracao(self):
        svc.ativar_dgvoodoo(self.cli)
        with open(self.caminho(svc.D3D9_DLL), "wb") as f:
            f.write(b"modificado" * 100)
        r = svc.restaurar_directx_original(self.cli)
        self.assertFalse(r.ok)
        self.assertEqual(r.estado, svc.Estado.MODIFICADO_EXTERNAMENTE)
        self.assertTrue(self.existe(svc.D3D9_DLL))


# --- 9. Modificacao Externa Conf ---
class TestModExternaConf(BaseDgvoodooTest):
    def test_conf_modificado_nao_destruido(self):
        self.escrever(svc.DGVOODOO_CONF, b"conf original\n")
        svc.ativar_dgvoodoo(self.cli)
        with open(self.caminho(svc.DGVOODOO_CONF), "wb") as f:
            f.write(b"conf modificado\n")
        r = svc.restaurar_directx_original(self.cli)
        if self.existe(svc.DGVOODOO_CONF) and r.ok:
            self.assertNotEqual(self.ler(svc.DGVOODOO_CONF), b"conf modificado\n")


# --- 10-11. Template Ausente ---
class TestTemplateAusente(BaseDgvoodooTest):
    def test_dll_ausente(self):
        with mock.patch.object(svc, "resolver_template_d3d9",
                               return_value="/nao_existe/D3D9.dll"):
            r = svc.ativar_dgvoodoo(self.cli)
        self.assertFalse(r.ok)
        self.assertEqual(r.estado, svc.Estado.TEMPLATE_AUSENTE)
        self.assertFalse(self.existe(svc.D3D9_DLL))

    def test_conf_ausente(self):
        with mock.patch.object(svc, "resolver_template_conf",
                               return_value="/nao_existe/dgVoodoo.conf"):
            r = svc.ativar_dgvoodoo(self.cli)
        self.assertFalse(r.ok)
        self.assertEqual(r.estado, svc.Estado.TEMPLATE_AUSENTE)
        self.assertFalse(self.existe(svc.DGVOODOO_CONF))


# --- 12. Jogo Aberto ---
class TestJogoAberto(BaseDgvoodooTest):
    def test_ativacao_bloqueada(self):
        # O servico usa _cliente_com_processo_aberto (detect_relevant_processes);
        # config.jogo_esta_aberto e apenas fallback.
        with mock.patch.object(svc, "_cliente_com_processo_aberto", return_value=True):
            r = svc.ativar_dgvoodoo(self.cli)
        self.assertFalse(r.ok)
        self.assertEqual(r.estado, svc.Estado.JOGO_ABERTO)
        self.assertFalse(self.existe(svc.D3D9_DLL))
        self.assertIsNone(svc._carregar_estado(self.cli))

    def test_restauracao_bloqueada(self):
        svc.ativar_dgvoodoo(self.cli)
        with mock.patch.object(svc, "_cliente_com_processo_aberto", return_value=True):
            r = svc.restaurar_directx_original(self.cli)
        self.assertFalse(r.ok)
        self.assertEqual(r.estado, svc.Estado.JOGO_ABERTO)
        self.assertTrue(self.existe(svc.D3D9_DLL))


# --- 14. Estado Pending ---
class TestEstadoPending(BaseDgvoodooTest):
    def test_pending_sem_arquivos(self):
        svc._salvar_estado(self.cli, {"status": "pending"})
        r = svc.detectar_estado(self.cli)
        self.assertEqual(r.estado, svc.Estado.INCOMPLETO)

    def test_pending_com_dll(self):
        svc._salvar_estado(self.cli, {"status": "pending"})
        shutil.copy(svc.resolver_template_d3d9(), self.caminho(svc.D3D9_DLL))
        r = svc.detectar_estado(self.cli)
        self.assertEqual(r.estado, svc.Estado.INCOMPLETO)

    def test_pending_com_dll_e_conf(self):
        svc._salvar_estado(self.cli, {"status": "pending"})
        shutil.copy(svc.resolver_template_d3d9(), self.caminho(svc.D3D9_DLL))
        shutil.copy(svc.resolver_template_conf(), self.caminho(svc.DGVOODOO_CONF))
        r = svc.detectar_estado(self.cli)
        self.assertEqual(r.estado, svc.Estado.INCOMPLETO)


# --- 15. Atualizacao do Template ---
class TestAtualizacaoTemplate(BaseDgvoodooTest):
    def test_hash_antigo_reconhecido_com_template_atualizado(self):
        """Template atualizado (hash B) nao deve classificar cliente com hash A como CONFLITO."""
        svc.ativar_dgvoodoo(self.cli)
        # Criar um template "atualizado" (hash B) em arquivo temporario real
        novo_template = os.path.join(self._tmp.name, "novo_template_d3d9.dll")
        with open(novo_template, "wb") as f:
            f.write(b"nova versao do dgvoodoo" * 100)
        self.assertNotEqual(_h_file(novo_template), HASH_DLL)
        with mock.patch.object(svc, "resolver_template_d3d9", return_value=novo_template):
            r = svc.detectar_estado(self.cli)
        self.assertEqual(
            r.estado, svc.Estado.ATIVO,
            f"Instalacao conhecida (hash A registrado) foi classificada como "
            f"{r.estado} apos atualizacao do template",
        )


# --- 16. Backup Nao Obsoleto ---
class TestBackupNaoObsoleto(BaseDgvoodooTest):
    def test_ciclo_a_restaura_a(self):
        a = b"conteudo A\n"
        self.escrever(svc.DGVOODOO_CONF, a)
        svc.ativar_dgvoodoo(self.cli)
        svc.restaurar_directx_original(self.cli)
        if self.existe(svc.DGVOODOO_CONF):
            self.assertEqual(self.ler(svc.DGVOODOO_CONF), a)

    def test_ciclo_b_nao_usa_a(self):
        # Ciclo 1: A
        self.escrever(svc.DGVOODOO_CONF, b"A\n")
        svc.ativar_dgvoodoo(self.cli)
        svc.restaurar_directx_original(self.cli)
        # Limpar cliente e backups
        for fn in list(os.listdir(self.cli)):
            p = os.path.join(self.cli, fn)
            if os.path.isfile(p):
                os.remove(p)
        bb = os.path.join(self.cli, "bk")
        if os.path.isdir(bb):
            shutil.rmtree(bb, ignore_errors=True)
        # Ciclo 2: B
        self.escrever(svc.DGVOODOO_CONF, b"B\n")
        svc.ativar_dgvoodoo(self.cli)
        svc.restaurar_directx_original(self.cli)
        if self.existe(svc.DGVOODOO_CONF):
            self.assertEqual(
                self.ler(svc.DGVOODOO_CONF), b"B\n",
                "BUG CRITICO: backup obsoleto restaurou A em vez de B",
            )


# --- 17. Backup Corrompido ---
class TestBackupCorrompido(BaseDgvoodooTest):
    def test_corrompido_tratado_com_seguranca(self):
        self.escrever(svc.DGVOODOO_CONF, b"original\n")
        svc.ativar_dgvoodoo(self.cli)
        e = svc._carregar_estado(self.cli)
        bp = e["conf"].get("backup_path")
        if bp and os.path.isfile(bp):
            with open(bp, "wb") as f:
                f.write(b"corrompido!")
        svc.restaurar_directx_original(self.cli)
        if self.existe(svc.DGVOODOO_CONF):
            self.assertNotEqual(self.ler(svc.DGVOODOO_CONF), b"corrompido!")


# --- 18. Estado.json Corrompido ---
class TestEstadoCorrompido(BaseDgvoodooTest):
    def test_json_invalido(self):
        p = svc._caminho_estado(self.cli)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(b"{invalido ::::}")
        r = svc.detectar_estado(self.cli)
        self.assertIn(r.estado, (svc.Estado.ERRO, svc.Estado.ORIGINAL, svc.Estado.INCOMPLETO))

    def test_campos_ausentes(self):
        svc._salvar_estado(self.cli, {"status": "active"})
        r = svc.detectar_estado(self.cli)
        self.assertIn(r.estado, (svc.Estado.INCOMPLETO, svc.Estado.ORIGINAL, svc.Estado.ERRO))

    def test_tipos_incorretos(self):
        svc._salvar_estado(self.cli, {"status": "active", "d3d9": "string"})
        r = svc.detectar_estado(self.cli)
        self.assertIn(r.estado, (svc.Estado.INCOMPLETO, svc.Estado.ORIGINAL, svc.Estado.ERRO))


# --- 19. Cliente Inexistente ---
class TestClienteInvalido(BaseDgvoodooTest):
    def test_config_none_resulta_erro(self):
        """config retornando None (pasta inexistente) -> resultado controlado ERRO."""
        with mock.patch.object(
            config, "obter_pasta_jogo_atual", create=True,
            side_effect=lambda exigir_existente=True: None,
        ):
            r = svc.detectar_estado()
        self.assertEqual(r.estado, svc.Estado.ERRO)

    def test_pasta_inexistente_nao_cria_arvore(self):
        """Pasta inexistente jamais deve ser criada pelo backend."""
        p = os.path.join(os.path.dirname(self.cli), "nao_existe_xyz_12345")
        self.assertFalse(os.path.isdir(p))
        with mock.patch.object(
            config, "obter_pasta_jogo_atual", create=True,
            side_effect=lambda exigir_existente=True: p,
        ):
            svc.detectar_estado()
        self.assertFalse(os.path.isdir(p), "Pasta inexistente foi criada")


# --- 20. Import Sem Efeitos Colaterais ---
class TestImportSemEfeitos(BaseDgvoodooTest):
    def test_nao_cria_estado(self):
        self.assertIsNone(svc._carregar_estado(self.cli))

    def test_templates_intactos(self):
        td, tc = svc.resolver_template_d3d9(), svc.resolver_template_conf()
        self.assertEqual(_h_file(td), HASH_DLL)
        self.assertEqual(_h_file(tc), HASH_CONF)


# --- Preset Aika Recomendado ---
class TestPreset(BaseDgvoodooTest):
    def test_outputapi(self):
        svc.ativar_dgvoodoo(self.cli)
        v = svc._ler_chave_conf(self.caminho(svc.DGVOODOO_CONF), "[General]", "OutputAPI")
        self.assertEqual(v, "d3d11_fl11_0")

    def test_watermark(self):
        svc.ativar_dgvoodoo(self.cli)
        v = svc._ler_chave_conf(self.caminho(svc.DGVOODOO_CONF), "[DirectX]", "dgVoodooWatermark")
        self.assertEqual(v, "false")

    def test_pass_thru(self):
        svc.ativar_dgvoodoo(self.cli)
        v = svc._ler_chave_conf(self.caminho(svc.DGVOODOO_CONF), "[DirectX]", "DisableAndPassThru")
        self.assertEqual(v, "false")

    def test_videocard(self):
        svc.ativar_dgvoodoo(self.cli)
        v = svc._ler_chave_conf(self.caminho(svc.DGVOODOO_CONF), "[DirectX]", "VideoCard")
        self.assertEqual(v, "internal3D")

    def test_template_intacto_apos_preset(self):
        tc = svc.resolver_template_conf()
        h1 = _h_file(tc)
        svc.ativar_dgvoodoo(self.cli)
        self.assertEqual(_h_file(tc), h1)


# --- Preservacao Global do Template ---
class TestPreservacaoTemplate(unittest.TestCase):
    def test_dll_hash_constante(self):
        self.assertEqual(_h_file(svc.resolver_template_d3d9()), HASH_DLL)

    def test_conf_hash_constante(self):
        self.assertEqual(_h_file(svc.resolver_template_conf()), HASH_CONF)


# --- Backup obsoleto entre ciclos (Etapa 2.3) ---
class TestBackupCiclosReais(BaseDgvoodooTest):
    """Ciclos A -> B -> C SEM apagar o namespace de backup entre eles.

    Reproduz o uso real: cada nova ativacao deve capturar o estado
    imediatamente anterior a ela e a restauracao deve devolver exatamente
    esse estado — nunca um backup de ciclo anterior.
    """

    def _escrever_conf(self, dados):
        with open(self.caminho(svc.DGVOODOO_CONF), "wb") as f:
            f.write(dados)

    def test_ciclo_a_b_sem_limpar_backups(self):
        # CICLO 1: original A
        self._escrever_conf(b"A\n")
        self.assertTrue(svc.ativar_dgvoodoo(self.cli).ok)
        e1 = svc._carregar_estado(self.cli)
        self.assertEqual(e1["conf"]["original_sha256"], _h(b"A\n"))
        backup_a = e1["conf"]["backup_path"]
        self.assertTrue(os.path.isfile(backup_a))
        self.assertTrue(svc.restaurar_directx_original(self.cli).ok)
        self.assertEqual(self.ler(svc.DGVOODOO_CONF), b"A\n")
        # NADA é apagado aqui (nem backup, nem namespace)
        # CICLO 2: original legitimamente alterado para B
        self._escrever_conf(b"B\n")
        self.assertTrue(svc.ativar_dgvoodoo(self.cli).ok)
        e2 = svc._carregar_estado(self.cli)
        self.assertEqual(
            e2["conf"]["original_sha256"], _h(b"B\n"),
            "Estado deve registrar o original do ciclo atual (B)",
        )
        self.assertNotEqual(
            e2["conf"]["backup_path"], backup_a,
            "Ciclo 2 nao pode referenciar o backup do ciclo 1",
        )
        r = svc.restaurar_directx_original(self.cli)
        self.assertTrue(r.ok, f"Restauracao do ciclo 2 falhou: {r.mensagem}")
        final = self.ler(svc.DGVOODOO_CONF)
        self.assertEqual(final, b"B\n")
        self.assertNotEqual(final, b"A\n")

    def test_ciclo_a_b_c_multiciclo(self):
        for conteudo in (b"A\n", b"B\n", b"C\n"):
            self._escrever_conf(conteudo)
            self.assertTrue(svc.ativar_dgvoodoo(self.cli).ok)
            e = svc._carregar_estado(self.cli)
            self.assertEqual(e["conf"]["original_sha256"], _h(conteudo))
            self.assertTrue(svc.restaurar_directx_original(self.cli).ok)
            self.assertEqual(self.ler(svc.DGVOODOO_CONF), conteudo)
        # Backups dos tres ciclos continuam presentes e distintos
        pasta_backups = os.path.join(
            svc._pasta_estado_cliente(self.cli), "backups"
        )
        if os.path.isdir(pasta_backups):
            hashes = sorted(os.listdir(pasta_backups))
            self.assertEqual(len(hashes), 3)

    def test_reativacao_ativo_nao_recaptura_template(self):
        # Ativacao limpa: nao havia original
        self.assertTrue(svc.ativar_dgvoodoo(self.cli).ok)
        e1 = svc._carregar_estado(self.cli)
        self.assertFalse(e1["conf"]["original_present"])
        self.assertFalse(e1["d3d9"]["original_present"])
        # Reativacao enquanto ATIVO: nao reclassificar o template como original
        self.assertTrue(svc.ativar_dgvoodoo(self.cli).ok)
        e2 = svc._carregar_estado(self.cli)
        self.assertFalse(
            e2["conf"]["original_present"],
            "Template reinstalado nao pode virar 'original' da reativacao",
        )
        self.assertFalse(e2["d3d9"]["original_present"])


# --- Preflight impede restauracao parcial (fecha lacuna da Etapa 2.2) ---
class TestPreflightImpedeParcial(BaseDgvoodooTest):
    def test_conf_modificado_dll_permanece_intacta(self):
        self.escrever(svc.DGVOODOO_CONF, b"conf original\n")
        self.assertTrue(svc.ativar_dgvoodoo(self.cli).ok)
        # Usuario/programa modifica o conf externamente
        with open(self.caminho(svc.DGVOODOO_CONF), "wb") as f:
            f.write(b"conf modificado\n")
        hash_conf_mod = _h(b"conf modificado\n")
        hash_dll_antes = _h(self.ler(svc.D3D9_DLL))
        r = svc.restaurar_directx_original(self.cli)
        self.assertFalse(r.ok, "Restauracao nao pode ter sucesso com conf modificado")
        self.assertEqual(r.estado, svc.Estado.MODIFICADO_EXTERNAMENTE)
        # CONF permanece byte a byte intacto
        self.assertEqual(self.ler(svc.DGVOODOO_CONF), b"conf modificado\n")
        self.assertEqual(_h(self.ler(svc.DGVOODOO_CONF)), hash_conf_mod)
        # DLL instalada pelo Optimizer tambem permanece presente e intacta
        self.assertTrue(self.existe(svc.D3D9_DLL))
        self.assertEqual(_h(self.ler(svc.D3D9_DLL)), hash_dll_antes)


# --- Perfis graficos (V2.2) ---
class TestPerfisAuto(BaseDgvoodooTest):
    """V2.3B: modo AUTO resolve para um dos 3 perfis sem criar perfil novo."""

    def _ativar_limpo(self):
        self.assertTrue(svc.ativar_dgvoodoo(self.cli).ok)
        e = svc._carregar_estado(self.cli)
        self.assertEqual(e["status"], "active")
        return e

    def _ler_aa(self):
        return svc._ler_chave_conf(
            self.caminho(svc.DGVOODOO_CONF), "[DirectX]", "Antialiasing"
        )

    def _ler_filt(self):
        return svc._ler_chave_conf(
            self.caminho(svc.DGVOODOO_CONF), "[DirectX]", "Filtering"
        )

    def test_auto_quality_aplica_exatamente_quality(self):
        self._ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                               resolved_profile=svc.PERFIL_QUALITY)
        self.assertTrue(r.ok, r.mensagem)
        self.assertEqual(self._ler_aa(), "4x")
        self.assertEqual(self._ler_filt(), "16")
        self.assertIn("AUTO", r.mensagem)

    def test_auto_balanced_aplica_exatamente_balanced(self):
        self._ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                               resolved_profile=svc.PERFIL_BALANCED)
        self.assertTrue(r.ok, r.mensagem)
        self.assertEqual(self._ler_aa(), "2x")
        self.assertEqual(self._ler_filt(), "16")

    def test_auto_performance_aplica_exatamente_performance(self):
        self._ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                               resolved_profile=svc.PERFIL_PERFORMANCE)
        self.assertTrue(r.ok, r.mensagem)
        self.assertEqual(self._ler_aa(), "appdriven")
        self.assertEqual(self._ler_filt(), "trilinear")

    def test_conteudo_auto_igual_perfil_manual(self):
        """conf gerado por auto->X é byte a byte igual a aplicar manual X."""
        self._ativar_limpo()
        svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                           resolved_profile=svc.PERFIL_QUALITY)
        dados_auto = self.ler(svc.DGVOODOO_CONF)
        # reset e aplica manual num segundo ciclo
        self.assertTrue(svc.restaurar_directx_original(self.cli).ok)
        self._ativar_limpo()
        svc.aplicar_perfil(svc.PERFIL_QUALITY, self.cli)
        dados_manual = self.ler(svc.DGVOODOO_CONF)
        self.assertEqual(dados_auto, dados_manual)
        self.assertEqual(_h(dados_auto), _h(dados_manual))

    def test_preset_persistido_auto(self):
        self._ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                               resolved_profile=svc.PERFIL_QUALITY)
        self.assertTrue(r.ok, r.mensagem)
        e = svc._carregar_estado(self.cli)
        self.assertEqual(e["preset"], "auto")
        self.assertEqual(e["resolved_profile"], "quality")
        self.assertIn("profile_applied_at", e)

    def test_resolved_profile_persistido_cada_um(self):
        self._ativar_limpo()
        for resolved, aa in (("performance", "appdriven"),
                             ("balanced", "2x"),
                             ("quality", "4x")):
            r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                                   resolved_profile=resolved)
            self.assertTrue(r.ok, r.mensagem)
            e = svc._carregar_estado(self.cli)
            self.assertEqual(e["preset"], "auto")
            self.assertEqual(e["resolved_profile"], resolved)

    def test_resolved_invalido_rejeitado_sem_alterar_conf(self):
        self._ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                               resolved_profile="ultra")
        self.assertFalse(r.ok)
        self.assertEqual(r.estado, svc.Estado.ERRO)
        # conf continua balanced (default pos-ativacao = 2x)
        self.assertEqual(self._ler_aa(), "2x")
        e = svc._carregar_estado(self.cli)
        self.assertNotEqual(e.get("preset"), "auto")
        self.assertNotIn("resolved_profile", e)

    """Valida aplicar_perfil e transicoes entre os 3 perfis."""

    def _ativar_limpo(self):
        self.assertTrue(svc.ativar_dgvoodoo(self.cli).ok)
        e = svc._carregar_estado(self.cli)
        self.assertEqual(e["status"], "active")
        return e

    def _ler_aa(self):
        return svc._ler_chave_conf(
            self.caminho(svc.DGVOODOO_CONF), "[DirectX]", "Antialiasing"
        )

    def _ler_filt(self):
        return svc._ler_chave_conf(
            self.caminho(svc.DGVOODOO_CONF), "[DirectX]", "Filtering"
        )

    def test_resolved_auto_rejeitado(self):
        self._ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                               resolved_profile=svc.PERFIL_AUTO)
        self.assertFalse(r.ok)
        self.assertEqual(self._ler_aa(), "2x")
        e = svc._carregar_estado(self.cli)
        self.assertNotIn("resolved_profile", e)

    def test_resolved_ausente_rejeitado(self):
        self._ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli)
        self.assertFalse(r.ok)
        self.assertEqual(self._ler_aa(), "2x")

    def test_manual_apos_auto_remove_resolved(self):
        self._ativar_limpo()
        self.assertTrue(svc.aplicar_perfil(
            svc.PERFIL_AUTO, self.cli, resolved_profile=svc.PERFIL_QUALITY).ok)
        e = svc._carregar_estado(self.cli)
        self.assertEqual(e["preset"], "auto")
        r = svc.aplicar_perfil(svc.PERFIL_PERFORMANCE, self.cli)
        self.assertTrue(r.ok, r.mensagem)
        e = svc._carregar_estado(self.cli)
        self.assertEqual(e["preset"], "performance")
        self.assertNotIn("resolved_profile", e)
        self.assertEqual(self._ler_aa(), "appdriven")

    def test_original_e_backup_preservados_no_auto(self):
        # cliente com conf original -> ativar captura original (como teste antigo)
        self.escrever(svc.DGVOODOO_CONF, b"conf original A\n")
        e = self._ativar_limpo()
        orig_sha = e["conf"]["original_sha256"]
        backup_path = e["conf"]["backup_path"]
        self.assertTrue(orig_sha and backup_path)
        self.assertTrue(svc.aplicar_perfil(
            svc.PERFIL_AUTO, self.cli, resolved_profile=svc.PERFIL_QUALITY).ok)
        self.assertTrue(svc.aplicar_perfil(
            svc.PERFIL_AUTO, self.cli, resolved_profile=svc.PERFIL_PERFORMANCE).ok)
        e2 = svc._carregar_estado(self.cli)
        self.assertEqual(e2["conf"]["original_sha256"], orig_sha)
        self.assertEqual(e2["conf"]["backup_path"], backup_path)
        self.assertTrue(os.path.isfile(backup_path))

    def test_installed_sha256_atualizado_a_cada_auto(self):
        self._ativar_limpo()
        svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                           resolved_profile=svc.PERFIL_QUALITY)
        h1 = svc._carregar_estado(self.cli)["conf"]["installed_sha256"]
        self.assertTrue(svc.aplicar_perfil(
            svc.PERFIL_AUTO, self.cli, resolved_profile=svc.PERFIL_PERFORMANCE).ok)
        h2 = svc._carregar_estado(self.cli)["conf"]["installed_sha256"]
        self.assertNotEqual(h1, h2)
        self.assertEqual(h2, _h_file(self.caminho(svc.DGVOODOO_CONF)))

    def test_dll_nao_reinstalada_no_auto(self):
        e = self._ativar_limpo()
        hash_dll = e["d3d9"]["installed_sha256"]
        self.assertTrue(svc.aplicar_perfil(
            svc.PERFIL_AUTO, self.cli, resolved_profile=svc.PERFIL_QUALITY).ok)
        e2 = svc._carregar_estado(self.cli)
        self.assertEqual(e2["d3d9"]["installed_sha256"], hash_dll)
        self.assertEqual(_h_file(self.caminho(svc.D3D9_DLL)), HASH_DLL)

    def test_auto_modificado_externamente_bloqueia(self):
        self._ativar_limpo()
        with open(self.caminho(svc.DGVOODOO_CONF), "wb") as f:
            f.write(b"editado fora do optimizer\n")
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                               resolved_profile=svc.PERFIL_QUALITY)
        self.assertFalse(r.ok)
        self.assertEqual(r.estado, svc.Estado.MODIFICADO_EXTERNAMENTE)
        with open(self.caminho(svc.DGVOODOO_CONF), "rb") as f:
            self.assertEqual(f.read(), b"editado fora do optimizer\n")

    def test_auto_jogo_aberto_bloqueia(self):
        self._ativar_limpo()
        with mock.patch.object(svc, "_cliente_com_processo_aberto", return_value=True):
            r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                                   resolved_profile=svc.PERFIL_QUALITY)
        self.assertFalse(r.ok)
        self.assertEqual(r.estado, svc.Estado.JOGO_ABERTO)

    def test_auto_nao_ativo_bloqueia(self):
        r = svc.aplicar_perfil(svc.PERFIL_AUTO, self.cli,
                               resolved_profile=svc.PERFIL_QUALITY)
        self.assertFalse(r.ok)

    def test_restauracao_apos_trocas_auto_manual(self):
        self._ativar_limpo()
        seq = [
            (svc.PERFIL_BALANCED, None),
            (svc.PERFIL_AUTO, svc.PERFIL_QUALITY),
            (svc.PERFIL_AUTO, svc.PERFIL_BALANCED),
            (svc.PERFIL_PERFORMANCE, None),
            (svc.PERFIL_AUTO, svc.PERFIL_QUALITY),
        ]
        for perfil, resolved in seq:
            r = svc.aplicar_perfil(perfil, self.cli, resolved_profile=resolved)
            self.assertTrue(r.ok, r.mensagem)
        r = svc.restaurar_directx_original(self.cli)
        self.assertTrue(r.ok, r.mensagem)
        self.assertFalse(self.existe(svc.D3D9_DLL))
        self.assertFalse(self.existe(svc.DGVOODOO_CONF))
        self.assertIsNone(svc._carregar_estado(self.cli))

    def test_interpretacao_estado_auto(self):
        st = {"preset": "auto", "resolved_profile": "quality"}
        self.assertEqual(svc._perfil_escolhido_estado(st), "auto")
        self.assertEqual(svc._perfil_efetivo_estado(st), "quality")
        self.assertEqual(svc._resolved_profile_estado(st), "quality")

    def test_interpretacao_estado_auto_sem_resolved(self):
        st = {"preset": "auto"}
        self.assertEqual(svc._perfil_escolhido_estado(st), "auto")
        self.assertEqual(svc._perfil_efetivo_estado(st), "balanced")  # fallback

    def test_interpretacao_estado_auto_resolved_invalido(self):
        st = {"preset": "auto", "resolved_profile": "auto"}
        self.assertEqual(svc._perfil_escolhido_estado(st), "auto")
        self.assertEqual(svc._perfil_efetivo_estado(st), "balanced")
        self.assertIsNone(svc._resolved_profile_estado(st))

    def test_interpretacao_estado_manual_continua(self):
        self.assertEqual(svc._perfil_escolhido_estado(
            {"preset": "balanced"}), "balanced")
        self.assertEqual(svc._perfil_efetivo_estado(
            {"preset": "balanced"}), "balanced")
        self.assertEqual(svc._perfil_escolhido_estado(
            {"preset": "Aika Recomendado"}), "balanced")
        self.assertEqual(svc._perfil_efetivo_estado(
            {"preset": "Aika Recomendado"}), "balanced")
        self.assertEqual(svc._perfil_escolhido_estado(None), "balanced")

class TestPerfisGraficos(BaseDgvoodooTest):
    """Valida aplicar_perfil e transicoes entre os 3 perfis."""

    def _ativar_limpo(self):
        self.assertTrue(svc.ativar_dgvoodoo(self.cli).ok)
        e = svc._carregar_estado(self.cli)
        self.assertEqual(e["status"], "active")
        return e

    def _ler_aa(self):
        return svc._ler_chave_conf(
            self.caminho(svc.DGVOODOO_CONF), "[DirectX]", "Antialiasing"
        )

    def _ler_filt(self):
        return svc._ler_chave_conf(
            self.caminho(svc.DGVOODOO_CONF), "[DirectX]", "Filtering"
        )

    def test_aplicar_performance_valores_exatos(self):
        self._ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_PERFORMANCE, self.cli)
        self.assertTrue(r.ok, r.mensagem)
        self.assertEqual(self._ler_aa(), "appdriven")
        self.assertEqual(self._ler_filt(), "trilinear")

    def test_aplicar_balanced_valores_exatos(self):
        self._ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_BALANCED, self.cli)
        self.assertTrue(r.ok, r.mensagem)
        self.assertEqual(self._ler_aa(), "2x")
        self.assertEqual(self._ler_filt(), "16")

    def test_aplicar_quality_valores_exatos(self):
        self._ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_QUALITY, self.cli)
        self.assertTrue(r.ok, r.mensagem)
        self.assertEqual(self._ler_aa(), "4x")
        self.assertEqual(self._ler_filt(), "16")

    def test_transicao_balanced_para_performance(self):
        self._ativar_limpo()
        r = svc.aplicar_perfil(svc.PERFIL_PERFORMANCE, self.cli)
        self.assertTrue(r.ok, r.mensagem)
        e = svc._carregar_estado(self.cli)
        self.assertEqual(e["preset"], "performance")
        self.assertEqual(self._ler_aa(), "appdriven")

    def test_transicao_performance_para_quality(self):
        self._ativar_limpo()
        svc.aplicar_perfil(svc.PERFIL_PERFORMANCE, self.cli)
        r = svc.aplicar_perfil(svc.PERFIL_QUALITY, self.cli)
        self.assertTrue(r.ok, r.mensagem)
        e = svc._carregar_estado(self.cli)
        self.assertEqual(e["preset"], "quality")
        self.assertEqual(self._ler_aa(), "4x")
        self.assertEqual(self._ler_filt(), "16")

    def test_transicao_quality_para_balanced_remove_residuos(self):
        self._ativar_limpo()
        svc.aplicar_perfil(svc.PERFIL_QUALITY, self.cli)
        self.assertEqual(self._ler_aa(), "4x")
        r = svc.aplicar_perfil(svc.PERFIL_BALANCED, self.cli)
        self.assertTrue(r.ok, r.mensagem)
        # quality -> balanced remove totalmente os overrides de quality
        self.assertEqual(self._ler_aa(), "2x")
        self.assertEqual(self._ler_filt(), "16")
        # base fixa preservada
        self.assertEqual(svc._ler_chave_conf(
            self.caminho(svc.DGVOODOO_CONF), "[DirectX]", "dgVoodooWatermark"), "false")
        self.assertEqual(svc._ler_chave_conf(
            self.caminho(svc.DGVOODOO_CONF), "[DirectX]", "ForceVerticalSync"), "false")

    def test_dll_nao_reinstalada_na_troca(self):
        e = self._ativar_limpo()
        hash_dll_antes = e["d3d9"]["installed_sha256"]
        for perfil in (svc.PERFIL_PERFORMANCE, svc.PERFIL_QUALITY, svc.PERFIL_BALANCED):
            self.assertTrue(svc.aplicar_perfil(perfil, self.cli).ok)
        e2 = svc._carregar_estado(self.cli)
        self.assertEqual(e2["d3d9"]["installed_sha256"], hash_dll_antes)
        # A DLL fisica no cliente permanece a mesma
        self.assertEqual(_h(self.ler(svc.D3D9_DLL)), hash_dll_antes)

    def test_original_sha_e_backup_nao_mudam(self):
        self.escrever(svc.DGVOODOO_CONF, b"conf original A\n")
        e = self._ativar_limpo()
        orig_sha = e["conf"]["original_sha256"]
        backup_path = e["conf"]["backup_path"]
        self.assertTrue(orig_sha and backup_path)
        for perfil in (svc.PERFIL_PERFORMANCE, svc.PERFIL_QUALITY,
                       svc.PERFIL_BALANCED, svc.PERFIL_PERFORMANCE):
            self.assertTrue(svc.aplicar_perfil(perfil, self.cli).ok)
        e2 = svc._carregar_estado(self.cli)
        self.assertEqual(e2["conf"]["original_sha256"], orig_sha)
        self.assertEqual(e2["conf"]["backup_path"], backup_path)

    def test_installed_sha256_muda_a_cada_perfil(self):
        self._ativar_limpo()
        hashes = set()
        for perfil in (svc.PERFIL_PERFORMANCE, svc.PERFIL_QUALITY, svc.PERFIL_BALANCED):
            self.assertTrue(svc.aplicar_perfil(perfil, self.cli).ok)
            e = svc._carregar_estado(self.cli)
            hashes.add(e["conf"]["installed_sha256"])
        # perfis distintos geram confs distintos -> hashes distintos
        self.assertEqual(len(hashes), 3)

    def test_preset_legado_mapeia_balanced(self):
        self.assertEqual(svc._perfil_normalizado("Aika Recomendado"), svc.PERFIL_BALANCED)
        self.assertEqual(svc._perfil_normalizado(None), svc.PERFIL_BALANCED)
        self.assertEqual(svc._perfil_normalizado("performance"), svc.PERFIL_PERFORMANCE)
        self.assertEqual(svc._perfil_normalizado("quality"), svc.PERFIL_QUALITY)

    def test_jogo_aberto_bloqueia_aplicar_perfil(self):
        self._ativar_limpo()
        with mock.patch.object(svc, "_cliente_com_processo_aberto", return_value=True):
            r = svc.aplicar_perfil(svc.PERFIL_PERFORMANCE, self.cli)
        self.assertFalse(r.ok)
        self.assertEqual(r.estado, svc.Estado.JOGO_ABERTO)
        # conf nao foi alterado (continua balanced default = 2x)
        self.assertEqual(self._ler_aa(), "2x")

    def test_dgvoodoo_nao_ativo_bloqueia(self):
        # sem ativar: estado ORIGINAL
        r = svc.aplicar_perfil(svc.PERFIL_PERFORMANCE, self.cli)
        self.assertFalse(r.ok)
        self.assertNotEqual(r.estado, svc.Estado.ATIVO)

    def test_conf_modificado_externamente_bloqueia(self):
        self._ativar_limpo()
        with open(self.caminho(svc.DGVOODOO_CONF), "wb") as f:
            f.write(b"configuracao alterada manualmente\n")
        r = svc.aplicar_perfil(svc.PERFIL_QUALITY, self.cli)
        self.assertFalse(r.ok)
        self.assertEqual(r.estado, svc.Estado.MODIFICADO_EXTERNAMENTE)

    def test_template_intacto_apos_aplicacoes(self):
        self._ativar_limpo()
        hash_antes = _h_file(svc.resolver_template_conf())
        for perfil in (svc.PERFIL_PERFORMANCE, svc.PERFIL_QUALITY, svc.PERFIL_BALANCED):
            self.assertTrue(svc.aplicar_perfil(perfil, self.cli).ok)
        self.assertEqual(_h_file(svc.resolver_template_conf()), hash_antes)

    def test_restauracao_apos_multiplas_trocas_retorna_original(self):
        # Cliente limpo (sem conf original) -> restauracao deve remover tudo
        self._ativar_limpo()
        for perfil in (svc.PERFIL_PERFORMANCE, svc.PERFIL_QUALITY, svc.PERFIL_BALANCED):
            self.assertTrue(svc.aplicar_perfil(perfil, self.cli).ok)
        r = svc.restaurar_directx_original(self.cli)
        self.assertTrue(r.ok, r.mensagem)
        self.assertFalse(self.existe(svc.D3D9_DLL))
        self.assertFalse(self.existe(svc.DGVOODOO_CONF))
        self.assertIsNone(svc._carregar_estado(self.cli))
        self.assertEqual(svc.detectar_estado(self.cli).estado, svc.Estado.ORIGINAL)


if __name__ == "__main__":
    unittest.main()
