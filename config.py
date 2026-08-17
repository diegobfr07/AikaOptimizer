import os
import sys
import threading
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import psutil
import winreg
import ctypes

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
ARQUIVO_HISTORICO_AUTOMOD = os.path.join(PASTA_BACKUP, "automod_history.json")

lock_otimizacao = threading.Lock()
snapshot_lock = threading.Lock()
_pid_jogo_cache = None
_pid_lock = threading.Lock()

# ========================================================
# FONTE ÚNICA DE VERDADE — NOMES DE EXECUTÁVEIS DO AIKA
# ========================================================
AIKA_GAME_EXES = {
    "aclient.exe",
    "aika.exe",
    "aika_br.exe",
    "aikabr.exe",
    "gameengine.exe",
}

AIKA_LAUNCHER_EXES = {
    "aikalauncher.exe",
}

os.makedirs(PASTA_BACKUP, exist_ok=True)

# ========================================================
# CONFIGURAÇÃO PERSISTENTE DO USUÁRIO (V4.0)
# ========================================================
import json as _json

_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))

# No build PyInstaller, usa %LOCALAPPDATA%\AIKA Optimizer\ para dados do usuário.
# Desenvolvimento (não frozen) mantém config.json ao lado do projeto.
if getattr(sys, 'frozen', False):
    _localappdata = os.environ.get("LOCALAPPDATA", "")
    if not _localappdata:
        # Fallback seguro baseado no perfil do usuário
        _localappdata = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    _CONFIG_DIR = os.path.join(_localappdata, "AIKA Optimizer")
    os.makedirs(_CONFIG_DIR, exist_ok=True)

ARQUIVO_CONFIG = os.path.join(_CONFIG_DIR, "config.json")

_config_cache = None
_config_lock = threading.Lock()

def _carregar_config():
    """Carrega config.json com cache em memória."""
    global _config_cache
    with _config_lock:
        if _config_cache is not None:
            return dict(_config_cache)
        try:
            if os.path.exists(ARQUIVO_CONFIG):
                with open(ARQUIVO_CONFIG, 'r', encoding='utf-8') as f:
                    _config_cache = _json.load(f)
            else:
                _config_cache = {}
        except Exception:
            _config_cache = {}
        return dict(_config_cache)

def _salvar_config(config_dict):
    """Salva config.json de forma atômica."""
    global _config_cache
    with _config_lock:
        _config_cache = dict(config_dict)
        try:
            os.makedirs(os.path.dirname(ARQUIVO_CONFIG), exist_ok=True)
            temp = ARQUIVO_CONFIG + ".tmp"
            with open(temp, 'w', encoding='utf-8') as f:
                _json.dump(_config_cache, f, indent=2)
            os.replace(temp, ARQUIVO_CONFIG)
        except Exception:
            pass

# --- MIGRAÇÃO DE CONFIG LEGADA (build frozen) ---
# Executada aqui (após _salvar_config) para que a função já exista.
if getattr(sys, 'frozen', False):
    _config_legado = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "config.json")
    if not os.path.exists(ARQUIVO_CONFIG) and os.path.exists(_config_legado):
        try:
            with open(_config_legado, 'r', encoding='utf-8') as _f_legado:
                _legado = _json.loads(_f_legado.read())
            if isinstance(_legado, dict):
                _salvar_config(_legado)
        except Exception:
            pass  # legado inválido → ignora e usa defaults


def obter_config(chave, padrao=None):
    """Obtém um valor da configuração persistente."""
    cfg = _carregar_config()
    return cfg.get(chave, padrao)

def definir_config(chave, valor):
    """Define um valor na configuração persistente."""
    cfg = _carregar_config()
    cfg[chave] = valor
    _salvar_config(cfg)

def is_modo_agressivo():
    """Verifica se o Modo Agressivo está ativo."""
    return obter_config("aggressive_mode", False)

def is_iniciar_com_windows():
    """Verifica se Inicializar com Windows está ativo."""
    return obter_config("start_with_windows", False)

def _montar_comando_startup():
    """Monta o comando canônico da entrada de inicialização (com --startup).

    Cobre PyInstaller/frozen (.exe) e execução por Python no desenvolvimento,
    com aspas corretas para caminhos com espaços. Sem hardcode de caminho.
    """
    import sys as _sys
    if getattr(_sys, 'frozen', False):
        # Build PyInstaller: sys.executable já é o .exe do aplicativo.
        return f'"{_sys.executable}" --startup'

    # Desenvolvimento: python <script> --startup
    script_path = os.path.abspath(_sys.argv[0]) if _sys.argv else os.path.join(_CONFIG_DIR, 'main.py')
    return f'"{_sys.executable}" "{script_path}" --startup'


def configurar_iniciar_com_windows(ativar):
    """
    Registra/remove o AIKA Optimizer da inicialização do Windows.
    Usa HKEY_CURRENT_USER - não requer administrador.
    """
    chave_run = r"Software\Microsoft\Windows\CurrentVersion\Run"
    nome_valor = "AIKA_Optimizer"

    try:
        if ativar:
            cmd = _montar_comando_startup()
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave_run, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, nome_valor, 0, winreg.REG_SZ, cmd)
            log(f"[CONFIG] Entrada de inicialização criada: {cmd}")
        else:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave_run, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, nome_valor)
                log("[CONFIG] Entrada de inicialização removida")
            except FileNotFoundError:
                pass  # Entrada já não existe
            except OSError:
                pass  # Entrada já não existe

        definir_config("start_with_windows", ativar)
        return True
    except Exception as e:
        log(f"[CONFIG] Erro ao configurar inicialização: {e}")
        return False


def migrar_startup_se_necessario():
    """Migração idempotente da entrada de inicialização para o formato atual (com --startup).

    - Entrada inexistente: não cria nada.
    - Entrada já correta: não escreve.
    - Entrada antiga: atualiza a MESMA entrada (não cria uma segunda).
    """
    chave_run = r"Software\Microsoft\Windows\CurrentVersion\Run"
    nome_valor = "AIKA_Optimizer"
    try:
        cmd_correto = _montar_comando_startup()

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave_run, 0, winreg.KEY_READ) as key:
                valor_atual, _tipo = winreg.QueryValueEx(key, nome_valor)
        except FileNotFoundError:
            return  # chave não existe → nada a migrar
        except OSError:
            return  # valor não existe → nada a migrar

        if valor_atual == cmd_correto:
            return  # já correto → zero escrita

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave_run, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, nome_valor, 0, winreg.REG_SZ, cmd_correto)
        log(f"[CONFIG] Entrada de inicialização migrada para: {cmd_correto}")
    except Exception as e:
        log(f"[CONFIG] Erro ao migrar inicialização: {e}")

def verificar_inicializacao_windows():
    """
    Verifica se a entrada de inicialização existe no registro.
    Retorna True se a entrada do AIKA Optimizer existir.
    """
    chave_run = r"Software\Microsoft\Windows\CurrentVersion\Run"
    nome_valor = "AIKA_Optimizer"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave_run, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, nome_valor)
            return True
    except (FileNotFoundError, OSError):
        return False
    except Exception:
        return False

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

def executar_comando_seguro(cmd, descricao="", timeout=30):
    try:
        creationflags = 0x08000000 if os.name == 'nt' else 0
        resultado = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=creationflags, timeout=timeout)
        return resultado.returncode == 0
    except subprocess.TimeoutExpired:
        nome = descricao or (cmd if isinstance(cmd, str) else " ".join(str(p) for p in cmd))
        log(f"[COMANDO] Timeout após {timeout}s: {nome}")
        return False
    except Exception:
        return False

def is_admin():
    """Verifica se o processo atual está elevado (administrador)."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def jogo_esta_aberto():
    global _pid_jogo_cache
    with _pid_lock:
        if _pid_jogo_cache and psutil.pid_exists(_pid_jogo_cache):
            try:
                nome = (psutil.Process(_pid_jogo_cache).name() or "").lower()
                if nome in AIKA_GAME_EXES:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            _pid_jogo_cache = None
    try:
        for proc in psutil.process_iter(['name', 'pid']):
            nome = (proc.info.get('name') or "").lower()
            if nome in AIKA_GAME_EXES:
                with _pid_lock:
                    _pid_jogo_cache = proc.info['pid']
                return True
    except Exception:
        pass
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