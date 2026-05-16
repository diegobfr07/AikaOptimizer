import os
import threading
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import psutil
import winreg

def descobrir_pasta_jogo():
    # Tenta descobrir o caminho real de instalação pelo Registo do Windows
    chaves = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\AikaOnlineBrasil",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\AikaOnlineBrasil",
        r"SOFTWARE\WOW6432Node\CBMgames\AikaOnlineBrasil"
    ]
    for chave in chaves:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, chave) as key:
                caminho = winreg.QueryValueEx(key, "InstallLocation")[0]
                if os.path.exists(caminho):
                    return caminho
        except Exception:
            pass
    # Fallback para o caminho padrão se o registo falhar
    return r"C:\CBMgames\AikaOnlineBrasil"

PASTA_JOGO_PADRAO = descobrir_pasta_jogo()
PASTA_BACKUP = os.path.join(os.path.dirname(PASTA_JOGO_PADRAO), "AikaOptimizer_Backups")
PASTA_BACKUP_REG = os.path.join(PASTA_BACKUP, "Registro_Sistema")
ARQUIVO_ESTADO = os.path.join(PASTA_BACKUP, "estado_sistema.json")
ARQUIVO_INDEX = os.path.join(PASTA_BACKUP, "aika_index.json")

lock_otimizacao = threading.Lock()
snapshot_lock = threading.Lock()
_pid_jogo_cache = None
_pid_lock = threading.Lock()

os.makedirs(PASTA_BACKUP, exist_ok=True)

logger = logging.getLogger("AikaOptimizer")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = RotatingFileHandler(os.path.join(PASTA_BACKUP, 'aika_optimizer.log'), maxBytes=5*1024*1024, backupCount=3)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

def log(mensagem, exception=False):
    if exception:
        logger.exception(mensagem) # Regista o Stack Trace completo (Dica do DeepSeek)
    else:
        logger.info(mensagem)

def caminho_seguro(base, alvo):
    try:
        base_real = os.path.realpath(base)
        alvo_real = os.path.realpath(alvo)
        if not base_real.endswith(os.sep): base_real += os.sep
        return alvo_real.startswith(base_real)
    except Exception: return False

def executar_comando_seguro(cmd, descricao=""):
    try:
        creationflags = 0x08000000 if os.name == 'nt' else 0
        resultado = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
        return resultado.returncode == 0
    except Exception: return False

def jogo_esta_aberto():
    global _pid_jogo_cache
    with _pid_lock:
        if _pid_jogo_cache and psutil.pid_exists(_pid_jogo_cache):
            try:
                if psutil.Process(_pid_jogo_cache).name().lower() in ['aika.exe', 'aika_br.exe', 'aikabr.exe', 'gameengine.exe', 'aikalauncher.exe']: return True
            except psutil.NoSuchProcess: _pid_jogo_cache = None
    try:
        for proc in psutil.process_iter(['name', 'pid']):
            nome = proc.info['name']
            if nome and nome.lower() in ['aika.exe', 'aika_br.exe', 'aikabr.exe', 'gameengine.exe', 'aikalauncher.exe']:
                with _pid_lock: _pid_jogo_cache = proc.info['pid']
                return True
    except Exception: pass
    return False

def iniciar_jogo(pasta_jogo=PASTA_JOGO_PADRAO):
    for exe in ["AikaLauncher.exe", "aika_br.exe", "aika.exe", "GameEngine.exe"]:
        caminho = os.path.join(pasta_jogo, exe)
        if os.path.exists(caminho):
            try:
                os.startfile(caminho)
                return True
            except Exception: pass
    return False