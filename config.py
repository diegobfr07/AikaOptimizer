import os
import sys
import threading
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import psutil
import winreg
import ctypes
import hashlib

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

PASTA_JOGO_PADRAO = r"C:\CBMgames\AikaOnlineBrasil"
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
# VERSÃO CANÔNICA DO PRODUTO (FONTE ÚNICA)
# ========================================================
# Rótulo usado pela interface, por arquivos gerados e por mensagens.
# Promovida de "V4.1.0-dev" para "V4.1.0" no gate de build candidate.
VERSAO_APLICATIVO = "V4.1.0"

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

# Estruturas nativas características do cliente AIKA (derivadas de
# set_injector._validar_cliente_destino_injetor e do cliente real).
AIKA_CLIENT_DIRS = {"mesh", "objects", "texture"}

# A criação física de PASTA_BACKUP passou a ser LAZY (AUD-03): importar este
# módulo NÃO cria diretório nem abre log. Os recursos são criados por
# _garantir_pasta_backup()/_garantir_log_arquivo() apenas quando necessários.

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
_mensagens_recuperacao_cliente = []
_ultimo_estado_cliente_reportado = None


def validar_pasta_cliente_aika(caminho):
    """Indica se ``caminho`` aparenta ser a raiz de um cliente AIKA.

    Marcadores FORTES: executável/launcher reconhecido (AIKA_GAME_EXES /
    AIKA_LAUNCHER_EXES); ou ``ItemList6.bin`` na raiz acompanhado de pelo
    menos uma estrutura nativa (AIKA_CLIENT_DIRS). ``Data/`` sozinho é
    marcador AUXILIAR e NÃO valida um cliente.
    """
    if not isinstance(caminho, (str, os.PathLike)):
        return False
    texto = os.path.normpath(str(caminho).strip())
    if not texto:
        return False
    raiz = os.path.abspath(texto)
    if not os.path.isdir(raiz):
        return False
    try:
        entradas = os.listdir(raiz)
    except OSError:
        return False
    nomes = {nome.lower() for nome in entradas}

    # Forte: executável/launcher AIKA reconhecido.
    if nomes & (AIKA_GAME_EXES | AIKA_LAUNCHER_EXES):
        return True

    # Forte: ItemList6.bin na raiz + estrutura nativa complementar.
    if "itemlist6.bin" in nomes and os.path.isfile(os.path.join(raiz, "itemlist6.bin")):
        if any(
            d in nomes and os.path.isdir(os.path.join(raiz, d))
            for d in AIKA_CLIENT_DIRS
        ):
            return True

    return False


def _cliente_global_valido(caminho):
    """Valida a raiz global pela validação canônica de cliente."""
    return validar_pasta_cliente_aika(caminho)


def _registrar_estado_cliente(mensagens, estado):
    global _ultimo_estado_cliente_reportado
    if estado == _ultimo_estado_cliente_reportado:
        return
    _ultimo_estado_cliente_reportado = estado
    _mensagens_recuperacao_cliente.extend(mensagens)
    for mensagem in mensagens:
        try:
            log(mensagem)
        except Exception:
            pass


def consumir_mensagens_recuperacao_cliente():
    """Entrega uma única vez as mensagens de recuperação para o log da UI."""
    with _config_lock:
        mensagens = list(_mensagens_recuperacao_cliente)
        _mensagens_recuperacao_cliente.clear()
        return mensagens


def _salvar_config_bloqueado(config_dict):
    """Persistência atômica; requer _config_lock já adquirido."""
    global _config_cache
    anterior = dict(_config_cache) if isinstance(_config_cache, dict) else None
    novo = dict(config_dict)
    temp = ARQUIVO_CONFIG + ".tmp"
    try:
        os.makedirs(os.path.dirname(ARQUIVO_CONFIG), exist_ok=True)
        with open(temp, 'w', encoding='utf-8') as f:
            _json.dump(novo, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, ARQUIVO_CONFIG)
        _config_cache = novo
        return True
    except Exception:
        _config_cache = anterior
        try:
            if os.path.exists(temp):
                os.remove(temp)
        except OSError:
            pass
        return False


def _recuperar_cliente_global_bloqueado(config_dict, config_malformado=False):
    """Resolve o cliente canônico sem confundir com a origem do Org. Sets.

    Prioridade: ``game_client_path`` válido → legado migrável comprovadamente
    cliente → padrão válido → não configurado. ``sets_source_path`` é preservado
    como configuração independente do Organizador de Sets.
    """
    cfg = dict(config_dict) if isinstance(config_dict, dict) else {}
    salvo = cfg.get("game_client_path")
    if validar_pasta_cliente_aika(salvo):
        _registrar_estado_cliente([], ("valido", os.path.normcase(salvo)))
        return cfg

    tinha_cliente = "game_client_path" in cfg
    if tinha_cliente:
        cfg.pop("game_client_path", None)

    # Legado: sets_source_path só migra se for comprovadamente cliente AIKA.
    legado = cfg.get("sets_source_path")
    if validar_pasta_cliente_aika(legado):
        cfg["game_client_path"] = legado
        _registrar_estado_cliente(
            [f"[OK] Cliente do AIKA reconhecido a partir da configuração anterior:\n{legado}"],
            ("migrado", os.path.normcase(str(legado))),
        )
        _salvar_config_bloqueado(cfg)
        return cfg

    if validar_pasta_cliente_aika(PASTA_JOGO_PADRAO):
        cfg["game_client_path"] = PASTA_JOGO_PADRAO
        mensagens = []
        if isinstance(salvo, str) and salvo.strip():
            mensagens.append(
                f"[AVISO] Cliente configurado anteriormente não foi encontrado:\n{salvo}"
            )
        mensagens.append(f"[OK] Cliente padrão restaurado:\n{PASTA_JOGO_PADRAO}")
        _registrar_estado_cliente(
            mensagens, ("fallback", os.path.normcase(str(salvo)))
        )
        _salvar_config_bloqueado(cfg)
        return cfg

    mensagens = []
    if isinstance(salvo, str) and salvo.strip():
        mensagens.append(
            f"[AVISO] Cliente configurado anteriormente não foi encontrado:\n{salvo}"
        )
    mensagens.append(
        "[ERRO] Nenhum cliente AIKA válido configurado.\n"
        "Selecione a pasta do cliente em Configurações."
    )
    _registrar_estado_cliente(
        mensagens, ("nao_configurado", os.path.normcase(str(salvo)))
    )
    if tinha_cliente or config_malformado:
        _salvar_config_bloqueado(cfg)
    return cfg

def _carregar_config():
    """Carrega config.json com cache em memória."""
    global _config_cache
    with _config_lock:
        if _config_cache is not None:
            _config_cache = _recuperar_cliente_global_bloqueado(_config_cache)
            return dict(_config_cache)
        config_malformado = False
        try:
            if os.path.exists(ARQUIVO_CONFIG):
                with open(ARQUIVO_CONFIG, 'r', encoding='utf-8') as f:
                    _config_cache = _json.load(f)
                if not isinstance(_config_cache, dict):
                    config_malformado = True
                    _config_cache = {}
            else:
                _config_cache = {}
        except Exception:
            config_malformado = True
            _config_cache = {}
        _config_cache = _recuperar_cliente_global_bloqueado(
            _config_cache, config_malformado=config_malformado
        )
        return dict(_config_cache)

def _salvar_config(config_dict):
    """Salva config.json de forma atômica e informa sucesso/falha."""
    with _config_lock:
        return _salvar_config_bloqueado(config_dict)

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
    """Define um valor na configuração persistente. Retorna bool."""
    if chave == "game_client_path" and not validar_pasta_cliente_aika(valor):
        return False
    cfg = _carregar_config()
    cfg[chave] = valor
    return _salvar_config(cfg)


def normalizar_pasta_jogo(pasta_jogo=None):
    """Normaliza a raiz canônica do cliente (game_client_path)."""
    if not pasta_jogo:
        pasta_jogo = obter_config("game_client_path", None)
    if not isinstance(pasta_jogo, str) or not pasta_jogo.strip():
        return None
    return os.path.abspath(os.path.normpath(os.path.realpath(str(pasta_jogo))))


def obter_pasta_jogo_atual(exigir_existente=False):
    """Fonte única de verdade para o cliente canônico no runtime."""
    pasta = normalizar_pasta_jogo(None)
    if not pasta or (exigir_existente and not validar_pasta_cliente_aika(pasta)):
        return None
    return pasta


def identidade_cliente(pasta_jogo=None):
    """Identidade estável por caminho real do cliente (não contém dados pessoais)."""
    raiz = os.path.normcase(normalizar_pasta_jogo(pasta_jogo))
    digest = hashlib.sha256(raiz.encode("utf-8", errors="surrogatepass")).hexdigest()[:16]
    nome = os.path.basename(raiz.rstrip(os.sep)) or "cliente"
    nome = "".join(c if c.isalnum() or c in "-_" else "_" for c in nome)[:40]
    return f"{nome}_{digest}"


def obter_pasta_backup_cliente(pasta_jogo=None, criar=True):
    """Namespace de backup exclusivo para a raiz real do cliente."""
    destino = os.path.join(PASTA_BACKUP, "Clientes", identidade_cliente(pasta_jogo))
    if criar:
        os.makedirs(destino, exist_ok=True)
    return destino


def obter_arquivo_index_cliente(pasta_jogo=None):
    return os.path.join(obter_pasta_backup_cliente(pasta_jogo), "aika_index.json")


def obter_arquivo_historico_cliente(pasta_jogo=None):
    return os.path.join(obter_pasta_backup_cliente(pasta_jogo), "automod_history.json")

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

_log_lock = threading.Lock()


def _garantir_pasta_backup() -> bool:
    """Cria BACKUP_ROOT somente quando necessário (idempotente)."""
    try:
        os.makedirs(PASTA_BACKUP, exist_ok=True)
        return True
    except OSError:
        return False


def _garantir_log_arquivo() -> None:
    """Habilita o log em arquivo uma única vez (lazy e idempotente — AUD-03).

    Importar ``config`` NÃO cria diretório nem arquivo de log; o handler só é
    criado na primeira chamada a ``log()``. Se a pasta padrão não puder ser
    criada, registra no stderr (StreamHandler) sem derrubar a aplicação.
    """
    with _log_lock:
        if any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
            return
        if not _garantir_pasta_backup():
            if not any(isinstance(h, logging.StreamHandler)
                       for h in logger.handlers):
                logger.addHandler(logging.StreamHandler())
            return
        handler = RotatingFileHandler(
            os.path.join(PASTA_BACKUP, "aika_optimizer.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        ))
        logger.addHandler(handler)


def log(mensagem, exception=False):
    _garantir_log_arquivo()
    if exception:
        logger.exception(mensagem)  # Regista o Stack Trace completo
    else:
        logger.info(mensagem)

def caminho_seguro(base, alvo):
    try:
        base_real = os.path.normcase(os.path.realpath(os.path.abspath(base)))
        alvo_real = os.path.normcase(os.path.realpath(os.path.abspath(alvo)))
        return os.path.commonpath([base_real, alvo_real]) == base_real
    except (OSError, ValueError, TypeError):
        return False

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

def iniciar_jogo(pasta_jogo=None):
    pasta_jogo = normalizar_pasta_jogo(pasta_jogo)
    for exe in ["AikaLauncher.exe", "aika_br.exe", "aika.exe", "GameEngine.exe"]:
        caminho = os.path.join(pasta_jogo, exe)
        if os.path.exists(caminho):
            try:
                os.startfile(caminho)
                return True
            except Exception: pass
    return False