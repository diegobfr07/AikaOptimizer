# -*- coding: utf-8 -*-
"""Hotfix de UNINSTALL do Installer Candidate V4.1.0 (processo vivo na bandeja).

BUG REAL (validacao humana):
    apos o uninstall, a janela nao estava aberta, mas o AIKA Optimizer continuou
    executando na bandeja; {app} (C:\\Program Files\\AIKA Optimizer) permaneceu
    bloqueada/"em uso" e so foi liberada apos finalizar o processo manualmente.

CAUSA RAIZ CONFIRMADA NO CODIGO:
    - main.py -> closeEvent(): com close_to_tray ativo, WM_CLOSE vira
      event.ignore() + esconder_para_bandeja() (hide-to-tray) — o processo NAO
      encerra;
    - a diretiva CloseApplications (Windows Restart Manager) vale apenas para o
      Setup: o uninstaller do Inno NAO usa Restart Manager;
    - sem ninguem encerrando o processo, {app}\\Aika_Optimizer_V4.1.exe e
      {app}\\_internal\\*.dll ficam bloqueados e a pasta nao pode ser removida.

Estes testes sao ESTATICOS (leem o script de instalacao). Nao executam o
uninstaller, nao tocam em clientes AIKA e nao escrevem em C:\\CBMgames.

Provas exigidas pela fase:
 1. o uninstall possui mecanismo de encerramento do EXE V4.1;
 2. o nome usado e EXATO (sem wildcard);
 3. nao existe wildcard perigoso;
 4. nenhum executavel do cliente AIKA e alvo;
 5. python.exe nunca e alvo;
 6. o cleanup de autostart (HKCU Run) permanece;
 7. os dados do usuario continuam preservados;
 8. AppId nao mudou;
 9. DefaultDirName nao mudou;
10. o payload continua o mesmo;
11. o Build Candidate EXE continua com o mesmo SHA-256.
"""

import hashlib
import json
import os
import re
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

ISS = "Projeto Brutal.iss"
MANIFESTO_FASE = "docs/release/INSTALLER_CANDIDATE_MANIFEST_V4.1.0_uninstall_hotfix.json"

EXE_V41 = "Aika_Optimizer_V4.1.exe"
EXE_V40 = "Aika_Optimizer_V4.0.exe"
SHA_EXE_V41 = "68287AE09F52B118F97380407742FB460EC8E71CA9013A2BF5F6DAF5DCF9167F"

# Executaveis do cliente AIKA (config.py / README) que NUNCA podem ser alvo.
EXES_CLIENTE_AIKA = (
    "aclient.exe", "aika.exe", "aika_br.exe", "aikabr.exe", "gameengine.exe",
)


def _ler(rel):
    with open(os.path.join(RAIZ, rel), encoding="utf-8") as f:
        return f.read()


def _sha256_file(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _defines_string(texto):
    """Mapa nome -> valor dos ``#define X "..."`` do ISPP."""
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r'^#define\s+(\w+)\s+"([^"]*)"\s*$', texto, re.M)
    }


def _expandido():
    """Script com as expansoes ISPP ``{#Nome}`` aplicadas (comando efetivo)."""
    texto = _ler(ISS)
    defines = _defines_string(texto)
    return re.sub(r"\{#(\w+)\}",
                  lambda m: defines.get(m.group(1), m.group(0)),
                  texto)


def _secao(texto, nome):
    """Linhas efetivas (sem comentarios/linhas vazias) da secao ``[nome]``."""
    linhas = texto.splitlines()
    inicio = None
    for i, linha in enumerate(linhas):
        if linha.strip().lower() == "[%s]" % nome.lower():
            inicio = i + 1
            break
    if inicio is None:
        return []
    corpo = []
    for linha in linhas[inicio:]:
        limpa = linha.strip()
        if limpa.startswith("[") and limpa.endswith("]"):
            break
        if not limpa or limpa.startswith(";"):
            continue
        corpo.append(limpa)
    return corpo


def _alvos_im(texto):
    """Todos os nomes passados a ``/IM`` (formato Inno com aspas dobradas)."""
    return re.findall(r'/IM\s+""([^"]+)""', texto)


def _sem_comentarios(texto):
    """Remove linhas de comentario (``;`` nas secoes ISS e ``//`` no [Code]).

    Necessario porque os comentarios documentam explicitamente o que NUNCA deve
    ser feito (ex.: "nunca usar wildcard Aika*.exe"), e os invariantes precisam
    julgar apenas o CONTEUDO EFETIVO do script.
    """
    linhas = []
    for linha in texto.splitlines():
        limpa = linha.strip()
        if limpa.startswith(";") or limpa.startswith("//"):
            continue
        linhas.append(linha)
    return "\n".join(linhas)



class TestUninstallEncerraProcesso(unittest.TestCase):
    """1-6 — mecanismo de encerramento no uninstall, exato e restrito."""

    def setUp(self):
        self.efetivo = _expandido()
        self.uninstall_run = _secao(self.efetivo, "UninstallRun")

    def test_01_uninstall_possui_mecanismo_de_encerramento(self):
        self.assertTrue(self.uninstall_run, "secao [UninstallRun] ausente")
        encerramento = [l for l in self.uninstall_run if "taskkill" in l.lower()]
        self.assertTrue(encerramento, "[UninstallRun] sem taskkill")
        self.assertTrue(any(EXE_V41 in l for l in encerramento),
                        "[UninstallRun] nao encerra o EXE V4.1")

    def test_02_nome_do_executavel_e_exato(self):
        linha = [l for l in self.uninstall_run
                 if "taskkill" in l.lower() and EXE_V41 in l][0]
        # argumento /IM entre aspas com o nome EXATO do produto
        self.assertIn('/IM ""%s""' % EXE_V41, linha)
        self.assertIn("{sys}\\taskkill.exe", linha)
        self.assertIn("EncerrarAikaOptimizerV41", linha)

    def test_03_nenhum_wildcard_perigoso(self):
        texto = _sem_comentarios(self.efetivo)
        for alvo in _alvos_im(texto):
            self.assertNotIn("*", alvo, "wildcard no /IM")
            self.assertNotIn("?", alvo, "curinga no /IM")
            self.assertNotIn("\\", alvo, "caminho no /IM")
        # o conteudo efetivo nao pode conter padroes amplos conhecidos
        # (arquivo fonte de dados do build e a excecao legitima: dist\...\*)
        for padrao in ("Aika*.exe", "AiKA*.exe", "*.exe\""):
            self.assertNotIn(padrao, texto)

    def test_04_nenhum_executavel_do_cliente_aika_e_alvo(self):
        texto = _sem_comentarios(self.efetivo).lower()
        for exe_cliente in EXES_CLIENTE_AIKA:
            self.assertNotIn(exe_cliente, texto,
                             "cliente AIKA referenciado no script")

    def test_05_python_exe_nunca_e_alvo(self):
        texto = _sem_comentarios(self.efetivo).lower()
        self.assertNotIn("python.exe", texto)
        self.assertNotIn("pythonw", texto)
        for alvo in _alvos_im(self.efetivo):
            self.assertFalse(alvo.lower().startswith("python"))

    def test_06_apenas_os_dois_exes_do_produto_sao_alvos(self):
        self.assertEqual(set(_alvos_im(self.efetivo)), {EXE_V41, EXE_V40})

    def test_07_encerramento_oculto_aguardado_e_idempotente(self):
        self.assertTrue(self.uninstall_run)
        for linha in self.uninstall_run:
            self.assertIn("runhidden", linha)
            self.assertIn("waituntilterminated", linha)
            self.assertIn("/F", linha)
            # RunOnceId evita entradas duplicadas em upgrade/instalacao repetida
            self.assertIn("RunOnceId:", linha)

    def test_08_encerramento_fora_da_secao_run(self):
        # o encerramento pertence ao uninstall, nunca ao [Run] de instalacao
        self.assertFalse(any("taskkill" in l.lower()
                             for l in _secao(self.efetivo, "Run")))


class TestUpgradeV40(unittest.TestCase):
    """Compatibilidade do upgrade V4.0 -> V4.1 com o app aberto/na bandeja."""

    def test_01_close_applications_e_restart_manager_preservados(self):
        texto = _ler(ISS)
        self.assertIn("CloseApplications=yes", texto)
        self.assertIn("RestartApplications=no", texto)

    def test_02_prepare_to_install_encerra_os_nomes_exatos(self):
        texto = _expandido()
        self.assertIn(
            "function PrepareToInstall(var NeedsRestart: Boolean): String;", texto)
        inicio = texto.index("function PrepareToInstall")
        fim = texto.index("procedure CurUninstallStepChanged")
        corpo = texto[inicio:fim]
        self.assertIn("{sys}\\taskkill.exe", corpo)
        self.assertIn("ewWaitUntilTerminated", corpo)
        self.assertIn(EXE_V41, corpo)
        self.assertIn(EXE_V40, corpo)

    def test_03_nome_legado_V40_confirmado_no_historico(self):
        # nome real e conhecido do EXE da V4.0 (nao inventado)
        self.assertIn('#define MyAppExeNameLegado "%s"' % EXE_V40, _ler(ISS))


class TestCleanupEPreservacao(unittest.TestCase):
    """7, 8, 9, 10 — autostart, dados do usuario, AppId, DefaultDirName, payload."""

    def test_01_autostart_cleanup_permanece(self):
        registry = _secao(_ler(ISS), "Registry")
        alvo = [l for l in registry
                if "CurrentVersion\\Run" in l and "AIKA_Optimizer" in l]
        self.assertTrue(alvo, "entrada HKCU Run do Optimizer nao removida")
        linha = alvo[0]
        self.assertIn("HKCU", linha)
        self.assertIn("uninsdeletevalue", linha)
        self.assertIn("dontcreatekey", linha)

    def test_02_nome_do_valor_run_casa_com_o_aplicativo(self):
        cfg = _ler("config.py")
        self.assertIn('nome_valor = "AIKA_Optimizer"', cfg)
        self.assertIn(r"Software\Microsoft\Windows\CurrentVersion\Run", cfg)

        registry = _secao(_ler(ISS), "Registry")
        linha = [l for l in registry if "CurrentVersion\\Run" in l][0]
        valor = re.search(r'ValueName:\s*"([^"]+)"', linha).group(1)
        self.assertEqual(valor, "AIKA_Optimizer")

    def test_03_dados_do_usuario_preservados(self):
        texto = _ler(ISS)
        # nenhuma secao de delete amplo no uninstall
        self.assertNotIn("[UninstallDelete]", texto)
        for linha in _secao(texto, "InstallDelete"):
            self.assertNotIn("config.json", linha.lower())
            self.assertNotIn("backup", linha.lower())
            self.assertNotIn("localappdata", linha.lower())
        # notas de preservacao mantidas
        self.assertIn("preferencias do usuario sao preservadas", texto)
        self.assertIn(
            "Backups do jogo (AikaOptimizer_Backups) tambem NAO sao tocados",
            texto)

    def test_04_appid_preservado(self):
        self.assertIn(
            "AppId={{2F4C311D-A712-433E-9AA7-C03E9ABE914D}", _ler(ISS))

    def test_05_default_dirname_preservado(self):
        self.assertIn("DefaultDirName={autopf}\\{#MyAppName}", _ler(ISS))
        self.assertIn('Source: "{#SourcePath}\\dist\\Aika_Optimizer_V4.1\\*"',
                      _ler(ISS))

    def test_06_payload_inalterado(self):
        texto = _ler(ISS)
        self.assertIn('Source: "{#SourcePath}\\dist\\Aika_Optimizer_V4.1\\*"',
                      texto)
        self.assertIn('Source: "{#SourcePath}\\README.md"', texto)
        self.assertIn('Source: "{#SourcePath}\\THIRD_PARTY_NOTICES.md"', texto)
        self.assertIn('#define MyAppExeName "%s"' % EXE_V41, texto)

    def test_07_cleanup_jit_condicional_preservado(self):
        texto = _ler(ISS)
        self.assertIn("procedure CurUninstallStepChanged", texto)
        self.assertIn("CurUninstallStep = usUninstall", texto)
        self.assertIn("AIKAOptimizer.JIT", texto)


class TestBuildCandidatePreservado(unittest.TestCase):
    """11 — o Build Candidate EXE continua com o mesmo SHA-256."""

    def test_01_manifesto_da_fase_registra_o_sha(self):
        dados = json.loads(_ler(MANIFESTO_FASE))
        self.assertEqual(dados["build_candidate_exe"]["sha256"].upper(),
                         SHA_EXE_V41)
        self.assertEqual(dados["build_candidate_exe"]["name"], EXE_V41)

    def test_02_exe_em_disco_mantem_o_sha(self):
        caminho = os.path.join(RAIZ, "dist", "Aika_Optimizer_V4.1", EXE_V41)
        if not os.path.isfile(caminho):
            self.skipTest("build onedir ausente (dist/ nao e versionado)")
        self.assertEqual(_sha256_file(caminho).upper(), SHA_EXE_V41)

    def test_03_installer_anterior_marcado_como_reprovado(self):
        dados = json.loads(_ler(MANIFESTO_FASE))
        anterior = dados["previous_installer"]
        self.assertEqual(
            anterior["sha256"].upper(),
            "6590C2182F43BE8EFE9E16BF661DEC88DDE713F6302688BD3DCF8BDCD39238B5")
        self.assertTrue(anterior["status"].startswith("REPROVADO"))

    def test_04_novo_installer_registrado_com_sha_proprio(self):
        dados = json.loads(_ler(MANIFESTO_FASE))
        novo = dados["new_installer"]
        self.assertEqual(len(novo["sha256"]), 64)
        self.assertNotEqual(novo["sha256"].upper(),
                            dados["previous_installer"]["sha256"].upper())


if __name__ == "__main__":
    unittest.main(verbosity=2)


