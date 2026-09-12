# -*- coding: utf-8 -*-
# =============================================================================
# JIT_INTEGRATION.PY — Integração do AIKA Optimizer com o Windows para .JIT
# =============================================================================
# Responsabilidades:
#   - detectar argumentos .JIT da linha de comando (case-insensitive);
#   - registrar/desregistrar a associação .JIT no Windows (HKCU\Software\Classes);
#   - montar o comando de abertura corretamente em dev/frozen;
#   - fornecer o estado REAL da associação no Registro;
#   - fornecer infraestrutura de single-instance (nome do servidor + mensagens).
#
# A conversão propriamente dita continua usando o backend existente
# (opt.extrair_textura_jit). Este módulo NÃO reimplementa o conversor.
# =============================================================================

import os
import sys
import winreg

PROGID = "AIKAOptimizer.JIT"
SERVER_NAME = "AIKAOptimizerV4_Instance"
EXTENSAO = ".jit"
MENSAGEM_REFRESH_HISTORICO = "AUTOMOD_HISTORY_REFRESH"

# Identidade registrada no Windows (Default Apps). Mantemos o nome atual V4.1 e
# o nome legado V4.0 apenas para migração/desregistro seguro (nunca de terceiros).
NOME_REGISTRADO = "AIKA Optimizer V4.1"
NOME_REGISTRADO_LEGADO = "AIKA Optimizer V4.0"


def _caminho_projeto():
    """Diretório do projeto (onde main.py e icone.ico vivem)."""
    return os.path.dirname(os.path.abspath(__file__))


def _caminho_main_py():
    return os.path.join(_caminho_projeto(), "main.py")


# ---------------------------------------------------------------------------
# 1. DETECÇÃO DE ARGUMENTOS .JIT
# ---------------------------------------------------------------------------
def obter_caminhos_jit_dos_argumentos(argv):
    """Extrai caminhos .JIT válidos de sys.argv (case-insensitive).

    - Ignora flags (--*);
    - valida extensão .jit (case-insensitive);
    - valida que o arquivo existe e é um arquivo regular.
    Retorna uma lista de caminhos absolutos normalizados.
    """
    caminhos = []
    for a in argv[1:]:
        if not a or a.startswith("--"):
            continue
        if os.path.splitext(a)[1].lower() != EXTENSAO:
            continue
        p = os.path.abspath(os.path.normpath(a))
        if os.path.isfile(p):
            caminhos.append(p)
    return caminhos


# ---------------------------------------------------------------------------
# 2. COMANDO DE ABERTURA (DEV / FROZEN)
# ---------------------------------------------------------------------------
def montar_comando_abertura():
    """Comando registrado no Windows (sem o %1, acrescentado pelo shell).

    Dev:    "python.exe" "C:\\...\\main.py" "%1"
    Frozen: "C:\\...\\AIKAOptimizer.exe" "%1"
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --jit-silent "%1"'
    pythonw = _caminho_pythonw() or sys.executable
    return f'"{pythonw}" "{_caminho_main_py()}" --jit-silent "%1"'


def montar_comando_injecao():
    """Comando registrado no Windows para o verbo de injeção (sem o %1).

    Dev:    "pythonw.exe" "C:\\...\\main.py" --jit-inject "%1"
    Frozen: "C:\\...\\AIKAOptimizer.exe" --jit-inject "%1"
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --jit-inject "%1"'
    pythonw = _caminho_pythonw() or sys.executable
    return f'"{pythonw}" "{_caminho_main_py()}" --jit-inject "%1"'


def montar_comando_injecao_dds():
    """Comando registrado no Windows para o verbo DDS de injeção (sem o %1).

    Dev:    "pythonw.exe" "C:\\...\\main.py" --dds-inject "%1"
    Frozen: "C:\\...\\AIKAOptimizer.exe" --dds-inject "%1"
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --dds-inject "%1"'
    pythonw = _caminho_pythonw() or sys.executable
    return f'"{pythonw}" "{_caminho_main_py()}" --dds-inject "%1"'


def montar_default_icon():
    """Ícone do ProgID. Frozen usa o próprio .exe; dev usa icone.ico se existir."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}",0'
    icone = os.path.join(_caminho_projeto(), "icone.ico")
    if os.path.exists(icone):
        return f'"{icone}",0'
    return f'"{sys.executable}",0'


# ---------------------------------------------------------------------------
# 3. REGISTRO / DESREGISTRO NO WINDOWS (HKCU\Software\Classes)
# ---------------------------------------------------------------------------
def notificar_shell_associacao():
    """Notifica o Shell (SHChangeNotify) de que as associações mudaram."""
    try:
        import ctypes
        SHCNE_ASSOCCHANGED = 0x08000000
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, 0, None, None)
    except Exception:
        pass


def _chave_existe(caminho):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, caminho):
            return True
    except Exception:
        return False


def _remover_valor(caminho, nome):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, caminho, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, nome)
    except Exception:
        pass


def _tem_openwithprogid():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.jit\OpenWithProgids") as k:
            try:
                winreg.QueryValueEx(k, PROGID)
                return True
            except Exception:
                return False
    except Exception:
        return False


def _tem_registered_app():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\RegisteredApplications") as k:
            try:
                winreg.QueryValueEx(k, NOME_REGISTRADO)
                return True
            except Exception:
                return False
    except Exception:
        return False


def registrar_integracao_windows():
    """Registra o AIKA Optimizer como handler de .JIT no Windows 11.

    - ProgID + DefaultIcon + shell/open/command;
    - .jit/OpenWithProgids (anúncio ao Shell);
    - Capabilities + RegisteredApplications (Default Apps);
    - valor default de .jit só se vazio ou já nosso.
    NÃO manipula a escolha padrão (UserChoice) do Windows.
    """
    comando = montar_comando_abertura()
    icone = montar_default_icon()

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\AIKAOptimizer.JIT") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "AIKA JIT Texture")

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\AIKAOptimizer.JIT\DefaultIcon") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, icone)

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\AIKAOptimizer.JIT\shell\open\command") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, comando)

    # Verbo "Extrair textura" (reutiliza o modo silencioso --jit-silent)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\AIKAOptimizer.JIT\shell\extract") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "AIKA Optimizer — Extrair textura")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\AIKAOptimizer.JIT\shell\extract\command") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, comando)

    # Verbo "Injetar no AIKA" (modo --jit-inject)
    comando_injecao = montar_comando_injecao()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\AIKAOptimizer.JIT\shell\inject") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "AIKA Optimizer — Injetar no AIKA")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\AIKAOptimizer.JIT\shell\inject\command") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, comando_injecao)

    # Verbo DDS "Injetar no AIKA" (associação secundária via SystemFileAssociations)
    comando_dds = montar_comando_injecao_dds()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\SystemFileAssociations\.dds\shell\AIKAOptimizer.Inject") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "AIKA Optimizer — Injetar no AIKA")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\SystemFileAssociations\.dds\shell\AIKAOptimizer.Inject\command") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, comando_dds)

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.jit\OpenWithProgids") as k:
        winreg.SetValueEx(k, PROGID, 0, winreg.REG_SZ, "")

    atual = _valor_atual_dot_jit()
    if atual is None or atual == "" or atual.lower() == PROGID.lower():
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.jit") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, PROGID)

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\AIKAOptimizer\Capabilities") as k:
        winreg.SetValueEx(k, "ApplicationName", 0, winreg.REG_SZ, NOME_REGISTRADO)
        winreg.SetValueEx(k, "ApplicationDescription", 0, winreg.REG_SZ,
                          "Ferramentas de otimização e modding para AIKA.")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\AIKAOptimizer\Capabilities\FileAssociations") as k:
        winreg.SetValueEx(k, ".jit", 0, winreg.REG_SZ, PROGID)

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\RegisteredApplications") as k:
        winreg.SetValueEx(k, NOME_REGISTRADO, 0, winreg.REG_SZ,
                          r"Software\AIKAOptimizer\Capabilities")

    # Migração: remove apenas a entrada legada própria (V4.0), se existir,
    # evitando duas entradas visíveis em RegisteredApplications.
    _remover_valor(r"Software\RegisteredApplications", NOME_REGISTRADO_LEGADO)

    notificar_shell_associacao()


def _valor_atual_dot_jit():
    """Valor (default) atual da chave HKCU\\Software\\Classes\\.jit, ou None."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.jit") as k:
            return winreg.QueryValueEx(k, None)[0]
    except Exception:
        return None


def _apagar_arvore(caminho):
    """Remove recursivamente uma chave de registro (bottom-up)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, caminho, 0,
                            winreg.KEY_READ | winreg.KEY_WRITE) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                    _apagar_arvore(caminho + "\\" + sub)
                except OSError:
                    break
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, caminho)
    except Exception:
        pass


def desregistrar_integracao_windows():
    """Remove SOMENTE as entradas pertencentes ao AIKA Optimizer.

    - Remove a árvore do ProgID;
    - remove nosso valor em .jit/OpenWithProgids (preservando outros);
    - remove o default de .jit apenas se for nosso (case-insensitive);
    - remove RegisteredApplications + Capabilities.
    Nunca apaga associação de terceiros.
    """
    _apagar_arvore(r"Software\Classes\AIKAOptimizer.JIT")
    _apagar_arvore(r"Software\Classes\SystemFileAssociations\.dds\shell\AIKAOptimizer.Inject")

    _remover_valor(r"Software\Classes\.jit\OpenWithProgids", PROGID)

    atual = _valor_atual_dot_jit()
    if atual is not None and atual.lower() == PROGID.lower():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.jit", 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, None)
        except Exception:
            pass

    _remover_valor(r"Software\RegisteredApplications", NOME_REGISTRADO)
    _remover_valor(r"Software\RegisteredApplications", NOME_REGISTRADO_LEGADO)
    _apagar_arvore(r"Software\AIKAOptimizer\Capabilities")

    notificar_shell_associacao()


def obter_status_associacao_jit():
    """Estado real da associação no Registro.

    Retorna:
      "ATIVA"          — somos o default efetivo de .jit.
      "DISPONÍVEL"     — registrado como handler, mas outro app/default ativo.
      "INATIVA"        — nossas entradas não existem.
      "REQUER REPARO"  — configuração parcial/quebrada.
    """
    progid = _chave_existe(r"Software\Classes\AIKAOptimizer.JIT")
    comando = _chave_existe(r"Software\Classes\AIKAOptimizer.JIT\shell\open\command")
    extract = _chave_existe(r"Software\Classes\AIKAOptimizer.JIT\shell\extract\command")
    inject = _chave_existe(r"Software\Classes\AIKAOptimizer.JIT\shell\inject\command")
    openwith = _tem_openwithprogid()
    atual = _valor_atual_dot_jit()
    nosso_default = (atual is not None and atual.lower() == PROGID.lower())

    if not progid and not comando and not openwith:
        return "INATIVA"
    completo = progid and comando and extract and inject and openwith
    if not completo:
        return "REQUER REPARO"
    if nosso_default:
        return "ATIVA"
    return "DISPONÍVEL"


def diagnosticar_associacao_jit():
    """Resumo somente leitura do estado do Registro (para o terminal)."""
    return [
        ("ProgID JIT", _chave_existe(r"Software\Classes\AIKAOptimizer.JIT")),
        ("Comando JIT", _chave_existe(r"Software\Classes\AIKAOptimizer.JIT\shell\open\command")),
        ("Verbo Extract", _chave_existe(r"Software\Classes\AIKAOptimizer.JIT\shell\extract")),
        ("Comando Extract", _chave_existe(r"Software\Classes\AIKAOptimizer.JIT\shell\extract\command")),
        ("Verbo Inject", _chave_existe(r"Software\Classes\AIKAOptimizer.JIT\shell\inject")),
        ("Comando Inject", _chave_existe(r"Software\Classes\AIKAOptimizer.JIT\shell\inject\command")),
        ("DDS Inject Verb", _chave_existe(r"Software\Classes\SystemFileAssociations\.dds\shell\AIKAOptimizer.Inject")),
        ("DDS Inject Command", _chave_existe(r"Software\Classes\SystemFileAssociations\.dds\shell\AIKAOptimizer.Inject\command")),
        ("DefaultIcon JIT", _chave_existe(r"Software\Classes\AIKAOptimizer.JIT\DefaultIcon")),
        ("OpenWithProgids", _tem_openwithprogid()),
        ("RegisteredApplications", _tem_registered_app()),
        ("Capabilities", _chave_existe(r"Software\AIKAOptimizer\Capabilities")),
        ("FileAssociations", _chave_existe(r"Software\AIKAOptimizer\Capabilities\FileAssociations")),
    ]


def codificar_mensagem(caminhos):
    """Serializa uma lista de caminhos para envio via QLocalSocket."""
    return "\n".join(caminhos).encode("utf-8")


def decodificar_mensagem(data):
    """Desserializa a mensagem recebida via QLocalSocket."""
    try:
        texto = data.decode("utf-8")
    except Exception:
        return []
    return [p for p in texto.split("\n") if p.strip()]


def notificar_refresh_historico():
    """Notifica a instância principal (se aberta) para reler o histórico do AutoMod.

    Usa o QLocalSocket existente. Falha silenciosamente se não houver instância
    aberta — nunca transforma uma injeção bem-sucedida em erro.
    """
    try:
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtNetwork import QLocalSocket
        if QCoreApplication.instance() is None:
            QCoreApplication([])
        sock = QLocalSocket()
        sock.connectToServer(SERVER_NAME)
        if not sock.waitForConnected(800):
            return False
        sock.write(MENSAGEM_REFRESH_HISTORICO.encode("utf-8"))
        sock.flush()
        sock.waitForBytesWritten(800)
        sock.disconnectFromServer()
        return True
    except Exception:
        return False



# ---------------------------------------------------------------------------
# 6. MODO SILENCIOSO (--jit-silent) — duplo clique .JIT sem GUI/terminal/UAC
# ---------------------------------------------------------------------------
def _caminho_pythonw():
    """Descobre pythonw.exe a partir de sys.executable (DEV silencioso)."""
    if getattr(sys, "frozen", False):
        return None
    exe = os.path.abspath(sys.executable)
    if os.path.basename(exe).lower() == "pythonw.exe":
        return exe
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.isfile(pythonw):
        return pythonw
    return None


def _log_silencioso(msg):
    """Log discreto em arquivo temporario (sem terminal)."""
    try:
        import tempfile
        caminho = os.path.join(tempfile.gettempdir(), "aikaoptimizer_jit_silent.log")
        with open(caminho, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _lock_conversao():
    """Adquire mutex nomeado cross-process para serializar conversoes."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h = kernel32.CreateMutexW(None, False, "AIKAOptimizerJIT_Silent")
        if not h:
            return None
        if kernel32.WaitForSingleObject(h, 30000) != 0:
            kernel32.CloseHandle(h)
            return None
        return h
    except Exception:
        return None


def _unlock_conversao(h):
    try:
        if h:
            import ctypes
            ctypes.windll.kernel32.ReleaseMutex(h)
            ctypes.windll.kernel32.CloseHandle(h)
    except Exception:
        pass


def converter_silencioso(argv, conversor):
    """Converte .JIT silenciosamente usando a funcao canonica passada.

    - nao abre GUI, terminal nem pede UAC;
    - reutiliza o conversor existente (opt.extrair_textura_jit);
    - serializa a escrita com mutex nomeado.
    Retorna True se ao menos um arquivo foi convertido.
    """
    caminhos = obter_caminhos_jit_dos_argumentos(argv)
    if not caminhos:
        _log_silencioso("--jit-silent: nenhum arquivo .jit em argv")
        return False

    mutex = _lock_conversao()
    ok_count = 0
    try:
        for c in caminhos:
            try:
                ok, msg = conversor(c)
            except Exception as e:
                ok, msg = False, str(e)
            if ok:
                ok_count += 1
            _log_silencioso(f"[{'OK' if ok else 'ERRO'}] {os.path.basename(c)}: {msg}")
    finally:
        _unlock_conversao(mutex)
    return ok_count > 0


# ---------------------------------------------------------------------------
# 7. MODO INJEÇÃO (--jit-inject) — contexto Explorer: injetar DDS no JIT
# ---------------------------------------------------------------------------
def _mostrar_feedback(mensagem, ok):
    """Caixa de diálogo nativa mínima (sem terminal/GUI principal)."""
    try:
        import ctypes
        titulo = "AIKA Optimizer"
        flags = 0x40 if ok else 0x10  # MB_ICONINFORMATION / MB_ICONERROR
        ctypes.windll.user32.MessageBoxW(0, mensagem, titulo, flags)
    except Exception:
        pass


def _validar_dds(caminho_dds):
    """Valida minimamente um DDS. Retorna (ok, msg)."""
    if not os.path.isfile(caminho_dds):
        return False, "DDS correspondente não encontrado."
    try:
        if os.path.getsize(caminho_dds) < 128:
            return False, "DDS inválido (arquivo muito pequeno)."
        with open(caminho_dds, "rb") as f:
            magic = f.read(4)
    except Exception:
        return False, "Não foi possível ler o DDS."
    if magic != b"DDS ":
        return False, "DDS inválido (assinatura não reconhecida)."
    return True, ""


def _injetar_jit(caminho_jit, injetor):
    """Valida e injeta o próprio JIT no jogo. Retorna (ok, msg)."""
    from config import obter_pasta_jogo_atual, caminho_seguro

    caminho_jit = os.path.abspath(os.path.normpath(caminho_jit))

    if not os.path.isfile(caminho_jit):
        return False, "Arquivo .JIT não encontrado."
    if os.path.splitext(caminho_jit)[1].lower() != ".jit":
        return False, "Extensão inválida (esperado .jit)."
    try:
        if os.path.getsize(caminho_jit) == 0:
            return False, "Arquivo .JIT vazio."
    except Exception:
        return False, "Não foi possível ler o arquivo .JIT."

    pasta_jogo = obter_pasta_jogo_atual()
    if caminho_seguro(pasta_jogo, caminho_jit):
        return False, "Este arquivo já está na pasta do AIKA. Selecione um JIT externo/modificado para injetar."

    try:
        resultado = injetor([caminho_jit], pasta_jogo)
    except Exception as e:
        return False, "Erro na injeção: " + str(e)

    if resultado is None or resultado < 0:
        return False, "Índice do jogo inexistente ou erro na injeção."
    if resultado == 0:
        return False, "Nenhum destino correspondente foi encontrado no AIKA ou o backup falhou."
    return True, "Arquivo JIT injetado com sucesso no AIKA."


def injetar_silencioso(argv, injetor):
    """Injeta o próprio JIT selecionado no jogo, silenciosamente.

    - não abre GUI/terminal;
    - reutiliza o backend canônico (opt.injetar_mods);
    - valida o JIT antes de injetar;
    - registra resultado em log temporário e mostra feedback nativo.
    Retorna True se ao menos um arquivo foi injetado.
    """
    caminhos = obter_caminhos_jit_dos_argumentos(argv)
    if not caminhos:
        _log_silencioso("--jit-inject: nenhum arquivo .jit em argv")
        _mostrar_feedback("Nenhum arquivo .JIT informado.", False)
        return False

    mutex = _lock_conversao()
    ok_global = False
    try:
        for c in caminhos:
            ok, msg = _injetar_jit(c, injetor)
            if ok:
                ok_global = True
            _log_silencioso(f"[{'OK' if ok else 'ERRO'}] {os.path.basename(c)}: {msg}")
            _mostrar_feedback(msg, ok)
    finally:
        _unlock_conversao(mutex)
    if ok_global:
        notificar_refresh_historico()
    return ok_global


# ---------------------------------------------------------------------------
# 8. MODO INJEÇÃO DDS (--dds-inject) — contexto Explorer: injetar DDS no jogo
# ---------------------------------------------------------------------------
def obter_caminhos_dds_dos_argumentos(argv):
    """Extrai caminhos .DDS válidos de sys.argv (case-insensitive)."""
    caminhos = []
    for a in argv[1:]:
        if not a or a.startswith("--"):
            continue
        if os.path.splitext(a)[1].lower() != ".dds":
            continue
        p = os.path.abspath(os.path.normpath(a))
        if os.path.isfile(p):
            caminhos.append(p)
    return caminhos


def _injetar_dds(caminho_dds, injetor):
    """Valida e injeta um DDS diretamente. Retorna (ok, msg)."""
    ok, _msg = _validar_dds(caminho_dds)
    if not ok:
        return False, "Arquivo DDS inválido."

    try:
        resultado = injetor([caminho_dds])
    except Exception as e:
        return False, "Erro na injeção: " + str(e)

    if resultado is None or resultado < 0:
        return False, "Índice do jogo inexistente ou erro na injeção."
    if resultado == 0:
        return False, "Nenhum arquivo correspondente foi encontrado no AIKA ou o backup falhou."
    return True, "Textura injetada com sucesso no AIKA."


def injetar_dds_silencioso(argv, injetor):
    """Injeta um DDS diretamente no jogo, silenciosamente.

    - não abre GUI/terminal;
    - reutiliza o backend canônico (opt.injetar_mods);
    - valida o DDS antes de injetar;
    - registra resultado em log temporário e mostra feedback nativo.
    Retorna True se ao menos um arquivo foi injetado.
    """
    caminhos = obter_caminhos_dds_dos_argumentos(argv)
    if not caminhos:
        _log_silencioso("--dds-inject: nenhum arquivo .dds em argv")
        _mostrar_feedback("Nenhum arquivo DDS informado.", False)
        return False

    mutex = _lock_conversao()
    ok_global = False
    try:
        for c in caminhos:
            ok, msg = _injetar_dds(c, injetor)
            if ok:
                ok_global = True
            _log_silencioso(f"[{'OK' if ok else 'ERRO'}] {os.path.basename(c)}: {msg}")
            _mostrar_feedback(msg, ok)
    finally:
        _unlock_conversao(mutex)
    if ok_global:
        notificar_refresh_historico()
    return ok_global

