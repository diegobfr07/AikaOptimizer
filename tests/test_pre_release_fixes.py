# -*- coding: utf-8 -*-
"""Testes das correções cirúrgicas pós-auditoria (AUD-01, AUD-02, AUD-03).

AUD-01 — packaging: spec do PyInstaller passa a incluir third_party/dgvoodoo2
         (D3D9.dll + dgVoodoo.conf) e o resolvedor encontra os arquivos no
         layout frozen (simulação do onedir/_MEIPASS).
AUD-02 — requirements.txt em UTF-8 sem BOM, conteúdo/pins preservados e
         interpretável pelo pip.
AUD-03 — importar config.py não cria diretório nem arquivo de log; criação é
         lazy/idempotente; caminhos públicos preservados; snapshot continua
         criando o diretório quando executado.
NENHUM teste escreve em C:\\CBMgames nem toca clientes Aika.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

HASH_DLL = "db1c445f7bcf699df1e175e974c779bdc7e19a468680a44884b1ab7078888d04"
HASH_CONF = "3c7da2fac3eaad369df468e80c9ba9c4db632c419799b32bbc31279d10985801"


def _rodar(script):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    r = subprocess.run([PY, "-B", "-c", script], capture_output=True,
                       text=True, cwd=RAIZ, env=env, timeout=180)
    if r.returncode != 0:
        raise AssertionError(f"subprocess falhou:\n{r.stdout}\n{r.stderr}")
    return r.stdout


class TestAud01Packaging(unittest.TestCase):
    """AUD-01 — third_party/dgvoodoo2 empacotado e resolvível no frozen."""

    def test_spec_inclui_third_party_dgvoodoo2(self):
        with open(os.path.join(RAIZ, "Aika_Optimizer_V4.1.spec"),
                  encoding="utf-8") as f:
            spec = f.read()
        self.assertIn("'third_party/dgvoodoo2', 'third_party/dgvoodoo2'", spec,
                      "spec precisa incluir a pasta no datas")

    def test_arquivos_fonte_existem_e_hashes(self):
        for rel, esperado in (("third_party/dgvoodoo2/D3D9.dll", HASH_DLL),
                              ("third_party/dgvoodoo2/dgVoodoo.conf", HASH_CONF)):
            with open(os.path.join(RAIZ, rel), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), esperado, rel)

    def test_destino_compativel_com_resolvedor(self):
        import dgvoodoo_service as svc
        self.assertEqual(svc.TEMPLATE_REL_PATH, "third_party/dgvoodoo2")
        with open(os.path.join(RAIZ, "Aika_Optimizer_V4.1.spec"),
                  encoding="utf-8") as f:
            self.assertIn(f"'third_party/dgvoodoo2', '{svc.TEMPLATE_REL_PATH}'", f.read())

    def test_layout_frozen_meipass_resolve_templates(self):
        import unittest.mock as mock
        import dgvoodoo_service as svc
        with tempfile.TemporaryDirectory(prefix="aika_frozen_") as td:
            pasta = os.path.join(td, "third_party", "dgvoodoo2")
            os.makedirs(pasta)
            with open(os.path.join(RAIZ, "third_party/dgvoodoo2/D3D9.dll"), "rb") as s:
                with open(os.path.join(pasta, "D3D9.dll"), "wb") as d:
                    d.write(s.read())
            with open(os.path.join(RAIZ, "third_party/dgvoodoo2/dgVoodoo.conf"), "rb") as s:
                with open(os.path.join(pasta, "dgVoodoo.conf"), "wb") as d:
                    d.write(s.read())
            with mock.patch.object(sys, "frozen", True, create=True), \
                 mock.patch.object(sys, "executable",
                                   os.path.join(td, "app.exe"), create=True), \
                 mock.patch.object(sys, "_MEIPASS", td, create=True):
                caminho_dll = svc.resolver_template_d3d9()
                caminho_conf = svc.resolver_template_conf()
            self.assertEqual(os.path.normcase(os.path.normpath(caminho_dll)),
                             os.path.normcase(os.path.normpath(
                                 os.path.join(pasta, "D3D9.dll"))))
            self.assertEqual(os.path.normcase(os.path.normpath(caminho_conf)),
                             os.path.normcase(os.path.normpath(
                                 os.path.join(pasta, "dgVoodoo.conf"))))
            self.assertTrue(os.path.isfile(caminho_dll) and os.path.isfile(caminho_conf))


class TestAud02Requirements(unittest.TestCase):
    """AUD-02 — requirements em UTF-8 sem BOM e interpretável pelo pip."""

    ESPERADO = [
        "customtkinter==6.0.0", "darkdetect==0.8.0", "packaging==26.3",
        "psutil==7.2.2", "PySide6==6.11.2", "PySide6_Addons==6.11.2",
        "PySide6_Essentials==6.11.2", "pywin32==312", "shiboken6==6.11.2",
        "winshell==0.6",
    ]

    def test_utf8_sem_bom(self):
        with open(os.path.join(RAIZ, "requirements.txt"), "rb") as f:
            raw = f.read()
        self.assertNotEqual(raw[:3], b"\xef\xbb\xbf", "BOM UTF-8 presente")
        self.assertNotEqual(raw[:2], b"\xff\xfe", "ainda UTF-16?")
        raw.decode("utf-8")  # deve decodificar sem erro

    def test_conteudo_preservado(self):
        with open(os.path.join(RAIZ, "requirements.txt"), encoding="utf-8") as f:
            linhas = [l.strip() for l in f.read().splitlines() if l.strip()]
        self.assertEqual(linhas, self.ESPERADO)

    def test_pip_consegue_interpretar(self):
        from pip._internal.network.session import PipSession  # type: ignore
        from pip._internal.req.req_file import parse_requirements  # type: ignore
        caminho = os.path.join(RAIZ, "requirements.txt")
        reqs = list(parse_requirements(caminho, session=PipSession()))
        self.assertEqual(len(reqs), 10)
        nomes = []
        for r in reqs:
            texto = getattr(r, "requirement", "") or repr(r)
            nomes.append(texto.split("==")[0].strip() if "==" in texto else texto)
        self.assertEqual(len(nomes), 10)
        self.assertIn("customtkinter", nomes)
        self.assertIn("winshell", nomes)


class TestAud03ConfigSemSideEffect(unittest.TestCase):
    """AUD-03 — import de config sem escrita; criação lazy/idempotente."""

    def _script_import(self):
        return (
            "import os, sys, json\n"
            "sys.path.insert(0, r'%s')\n"
            "calls = []\n"
            "real_mk = os.makedirs\n"
            "def _spy(*a, **k):\n"
            "    calls.append(a); return real_mk(*a, **k)\n"
            "from unittest import mock\n"
            "with mock.patch('os.makedirs', side_effect=_spy), \\\n"
            "     mock.patch('logging.handlers.RotatingFileHandler',\n"
            "                side_effect=RuntimeError('handler no import')) as mh:\n"
            "    import config  # noqa\n"
            "print(json.dumps({'makedirs': [list(map(str, c)) for c in calls],\n"
            "                  'rfh': mh.call_count}))" % RAIZ
        )

    def test_01_import_nao_cria_backup_nem_log(self):
        saida = _rodar(self._script_import())
        dados = json.loads(saida.strip().splitlines()[-1])
        self.assertEqual(dados["makedirs"], [],
                         "import de config não pode criar diretório")
        self.assertEqual(dados["rfh"], 0,
                         "import de config não pode abrir handler de log")

    def test_02_caminhos_publicos_inalterados(self):
        import config
        self.assertEqual(config.PASTA_BACKUP,
                         r"C:\CBMgames\AikaOptimizer_Backups")
        self.assertEqual(config.PASTA_BACKUP_REG,
                         r"C:\CBMgames\AikaOptimizer_Backups\Registro_Sistema")
        self.assertEqual(config.ARQUIVO_ESTADO,
                         r"C:\CBMgames\AikaOptimizer_Backups\estado_sistema.json")

    def _script_lazy_log(self):
        return (
            "import os, sys, json, tempfile, shutil\n"
            "sys.path.insert(0, r'%s')\n"
            "import config\n"
            "publico = config.PASTA_BACKUP\n"
            "td = tempfile.mkdtemp(prefix='cfg_aud03_')\n"
            "config.PASTA_BACKUP = td\n"
            "ok1 = config._garantir_pasta_backup()\n"
            "ok2 = config._garantir_pasta_backup()\n"
            "config._garantir_log_arquivo()\n"
            "config._garantir_log_arquivo()\n"
            "config.log('[AUD03] teste lazy log')\n"
            "config._garantir_log_arquivo()\n"
            "handlers = [type(h).__name__ for h in config.logger.handlers]\n"
            "arquivo = os.path.join(td, 'aika_optimizer.log')\n"
            "conteudo = ''\n"
            "if os.path.isfile(arquivo):\n"
            "    conteudo = open(arquivo, encoding='utf-8', errors='replace').read()\n"
            "print(json.dumps({'publico': publico, 'ok1': ok1, 'ok2': ok2,\n"
            "                  'handlers': handlers,\n"
            "                  'existe_log': os.path.isfile(arquivo),\n"
            "                  'contem_msg': '[AUD03] teste lazy log' in conteudo}))\n"
            "shutil.rmtree(td, ignore_errors=True)" % RAIZ
        )

    def test_03_log_lazy_idempotente_e_funcional(self):
        dados = json.loads(_rodar(self._script_lazy_log()).strip().splitlines()[-1])
        self.assertEqual(dados["publico"], r"C:\CBMgames\AikaOptimizer_Backups")
        self.assertTrue(dados["ok1"] and dados["ok2"])
        self.assertEqual(dados["handlers"].count("RotatingFileHandler"), 1,
                         "inicialização repetida não pode duplicar handler")
        self.assertTrue(dados["existe_log"])
        self.assertTrue(dados["contem_msg"])

    def _script_snapshot(self):
        return (
            "import os, sys, json, tempfile, shutil\n"
            "sys.path.insert(0, r'%s')\n"
            "import seguranca as seg\n"
            "td = tempfile.mkdtemp(prefix='snap_aud03_')\n"
            "seg.PASTA_BACKUP = td\n"
            "seg.ARQUIVO_ESTADO = os.path.join(td, 'estado_sistema.json')\n"
            "seg.obter_plano_energia_atual = lambda: 'plano_teste'\n"
            "seg.obter_dns_atual = lambda: []\n"
            "ok = seg.salvar_snapshot_sistema()\n"
            "print(json.dumps({'ok': ok,\n"
            "                  'existe': os.path.isfile(seg.ARQUIVO_ESTADO)}))\n"
            "shutil.rmtree(td, ignore_errors=True)" % RAIZ
        )

    def test_04_snapshot_cria_diretorio_quando_executado(self):
        dados = json.loads(_rodar(self._script_snapshot()).strip().splitlines()[-1])
        self.assertTrue(dados["ok"])
        self.assertTrue(dados["existe"])


if __name__ == "__main__":
    unittest.main()


