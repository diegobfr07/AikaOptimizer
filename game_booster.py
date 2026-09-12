import os, subprocess, psutil, ctypes, time, math
from config import log, lock_otimizacao, is_modo_agressivo, AIKA_GAME_EXES, AIKA_LAUNCHER_EXES
from enum import Enum

# ========================================================
# CONFIGURAÇÕES ULTIMATE EDITION (V1.0 MASTER CLASS)
# ========================================================
DESATIVAR_SYSMAIN = False 

MEU_PID = os.getpid()
BOOSTER_ATIVO = False
PRIORIDADES_ALTERADAS = {}

# Luxo Arquitetural: Memória de foco recente (Cooldown de Alt+Tab)
ULTIMOS_FOCADOS = {}
COOLDOWN_FOCO_SEGUNDOS = 15

# ========================================================
# NOVA ARQUITETURA: SISTEMA DE CATEGORIZAÇÃO (V4.0)
# ========================================================

class CategoriaProcesso(Enum):
    """Classificação completa de processos para decisão segura."""
    PROTECTED           = "PROTECTED"            # Nunca encerrar (kernel, AV, jogo, periféricos)
    GAME                = "GAME"                 # Aika.exe e componentes do jogo
    OPTIONAL_BACKGROUND = "OPTIONAL_BACKGROUND"  # Pode encerrar se regra explícita (navegadores, Spotify, etc.)
    KNOWN_UNWANTED      = "KNOWN_UNWANTED"       # PUP/adware/bundled (ByteFence, Web Companion, etc.)
    UNKNOWN             = "UNKNOWN"              # NÃO encerrar

# ========================================================
# MODO DRY RUN (TESTE SEM ENCERRAMENTO REAL)
# ========================================================
DRY_RUN = False  # True = detecta e classifica sem encerrar

# ========================================================
# ARQUITETURA DE LISTAS E BLINDAGEM DE KERNEL
# ========================================================

NAVEGADORES = {
    # PRINCIPAIS
    "msedge.exe", "chrome.exe", "firefox.exe", "opera.exe", "opera_gx.exe",
    "brave.exe", "vivaldi.exe", "yandex.exe",
    # CHROMIUM / ALTERNATIVOS
    "chromium.exe", "arc.exe", "thorium.exe", "ulaa.exe", "wavebrowser.exe",
    "sidekick.exe", "ghostbrowser.exe", "catsxp.exe",
    # SECURITY / PRIVACY BROWSERS
    "avastbrowser.exe", "avgbrowser.exe", "ccleanerbrowser.exe",
    # OUTROS CHROMIUM HISTÓRICOS/ALTERNATIVOS
    "dragon.exe", "chromodo.exe", "slimjet.exe", "iron.exe", "maxthon.exe",
    "whale.exe", "360chrome.exe", "360se.exe", "sogouexplorer.exe",
    "liebao.exe", "torch.exe", "urbrowser.exe",
    # FIREFOX-BASED / ALTERNATIVOS
    "zen.exe", "librewolf.exe", "waterfox.exe", "floorp.exe", "palemoon.exe", "basilisk.exe",
}

# Nomes genéricos que só são tratados como navegador quando o path bate
# com um fabricante/browser conhecido (segurança > cobertura).
GENERIC_BROWSER_PATH_HINTS = {
    "browser.exe": (
        "\\yandex\\",
        "\\yandexbrowser\\",
        "\\coccoc\\",
    ),
}

# ========================================================
# LISTA DE PROCESSOS OPCIONAIS DE FUNDO (OPTIONAL_BACKGROUND)
# Encerrados apenas quando há regra explícita
# ========================================================
PROCESSOS_OPTIONAL_BG = {
    # Navegadores
    "msedge.exe", "chrome.exe", "firefox.exe", "opera.exe", "opera_gx.exe", 
    "brave.exe", "vivaldi.exe", "yandex.exe",
    # Aplicativos de sincronização
    "onedrive.exe", "googledrivesync.exe", "googledrivefs.exe", "dropbox.exe", 
    "dropboxupdate.exe", "mega.exe", "megasync.exe", "boxsync.exe", 
    "icloud.exe", "nextcloud.exe",
    # Música/Streaming
    "spotify.exe", "spotifywebhelper.exe",
    # Launchers secundários
    "epicgameslauncher.exe", "epicwebhelper.exe", "origin.exe", 
    "originwebhelperservice.exe", "eadesktop.exe", "ubisoftconnect.exe", 
    "upc.exe", "uplay.exe", "battle.net.exe",
    # (removido "agent.exe": nome generico; sem identidade segura nao encerra)
    "riotclientservices.exe", "riotclientux.exe", "goggalaxy.exe", "leagueclient.exe",
    # Atualizadores
    "googleupdate.exe", "googlecrashhandler.exe", "msedgeupdate.exe",
    "adobearm.exe", "adobeupdateservice.exe", "acrotray.exe",
    # Comunicação (não encerrar automaticamente)
    # "discord.exe", "teams.exe", "skype.exe" -> NÃO estão aqui, são protegidos
    # Torrents legítimos (modo normal preserva; agressivo pode encerrar)
    "utorrent.exe", "bittorrent.exe", "qbittorrent.exe",
    # Download managers legítimos
    "idm.exe", "idman.exe",
    # Limpadores/otimizadores legítimos (não são adware por natureza)
    "ccleaner.exe", "ccleaner64.exe", "ccupdate.exe",
    "advancedsystemcare.exe", "driverbooster.exe",
    "wisecare365.exe", "glaryutilities.exe",
    # Componentes legítimos de fundo (Google/Adobe) e comunicação
    "software_reporter_tool.exe", "ccxprocess.exe", "qq.exe",
}

# ========================================================
# LISTA DE PROCESSOS INDESEJADOS CONHECIDOS (KNOWN_UNWANTED)
# Softwares bundled/adware/PUP documentados
# ========================================================
PROCESSOS_KNOWN_UNWANTED = {
    # PUPs e Adware conhecidos (claramente indesejados por natureza)
    "bytefence.exe", "bytefenceservice.exe",
    "webcompanion.exe", "webcompanionhelper.exe", "webcompanionupdater.exe",
    "lavasoft.wca.exe", "lavasoft.webcompanion.exe",
    # Browser hijackers / PUP de navegador
    "baidu.exe", "baiduan.exe", "hao123.exe",
    # Observacoes: torrents, download managers, limpadores, driverbooster,
    # software_reporter_tool (Google), ccxprocess (Adobe) e qq.exe sao
    # aplicativos legitimos -> movidos para PROCESSOS_OPTIONAL_BG.
}

# ========================================================
# PROCESSOS A ENCERRAR (UNIÃO DE OPTIONAL_BG + KNOWN_UNWANTED 
# quando regra explícita permite)
# ========================================================
PROCESSOS_MATAR = PROCESSOS_OPTIONAL_BG | PROCESSOS_KNOWN_UNWANTED

if is_modo_agressivo():
    # Modo agressivo: inclui navegadores na lista de encerramento
    PROCESSOS_MATAR.update(NAVEGADORES)

PROCESSOS_REDUZIR_PRIORIDADE = {
    "discord.exe", "discordptb.exe", "discordcanary.exe", "ts3client_win64.exe",
    "spotify.exe", "spotifywebhelper.exe", "vlc.exe", "itunes.exe",
    "obs64.exe", "obs.exe", "bandicam.exe", "fraps.exe", "action.exe", "shadowplayhelper.exe",
    "steam.exe", "steamwebhelper.exe", "code.exe", "whatsapp.exe"
}

if not is_modo_agressivo():
    PROCESSOS_REDUZIR_PRIORIDADE.update(NAVEGADORES)

PROCESSOS_NAO_TRIMAR = {
    "discord.exe", "discordptb.exe", "discordcanary.exe", 
    "obs64.exe", "obs.exe", "steam.exe", "steamwebhelper.exe"
}

PROCESSOS_PROTEGIDOS = {
    # === AIKA E COMPONENTES DO JOGO ===
    "aclient.exe", "aika.exe", "aika_br.exe", "aikabr.exe", "gameengine.exe", "aikalauncher.exe",
    # === STEAM, DISCORD E COMUNICAÇÃO (NUNCA ENCERRAR AUTOMATICAMENTE) ===
    "steam.exe", "steamservice.exe", "steamclient.exe",
    "discord.exe", "discordptb.exe", "discordcanary.exe",
    "skype.exe", "skypeapp.exe", "teams.exe", "ms-teams.exe", 
    "zoom.exe", "webex.exe", "whatsapp.exe",
    # === ANTIVÍRUS E SEGURANÇA (NUNCA ENCERRAR) ===
    "msmpeng.exe", "msseces.exe", "nissrv.exe", "securityhealthservice.exe",
    "securityhealthsystray.exe", "windefend.exe", "smartscreen.exe",
    "avp.exe", "avgui.exe", "avguard.exe", "nortonsecurity.exe", 
    "ekrn.exe", "bdagent.exe", "mcshield.exe", "mcafeefire.exe",
    # === PERIFÉRICOS E DRIVERS ===
    "razer synapse 3.exe", "razer synapse service.exe", "rzsynapse.exe", "rzsdkserver.exe",
    "lghub.exe", "ghub.exe", "logioptions.exe", "logioptionsplus.exe",
    "redragon.exe", "keyboarddriverutility.exe", "rdrgn.exe",
    "icue.exe", "corsair.service.exe", "steelseriesengine.exe", "gg.exe", "ngenuity.exe",
    "armourycrate.user.session.helper.exe", "armourycrate.service.exe",
    # === FERRAMENTAS DE JOGO ===
    "autohotkey.exe", "macrorecorder.exe", "bloody6.exe", "bloody7.exe",
    "msiafterburner.exe", "rtss.exe", "rivatunerstatisticsserver.exe",
    "obs64.exe", "obs.exe",
    # === ANTI-CHEAT/GAMEGUARD ===
    "gameguard.exe", "gamemon.des", "gamemon64.des", 
    "easyanticheat.exe", "eacservice.exe", "battleye.exe", "beservice.exe",
    "npggnt.des", "npptnt2.exe", "xigncode.exe", "wellbia.dll",
    # === PRÓPRIO AIKA OPTIMIZER ===
    "aikaoptimizer.exe", "python.exe",
}

# Reforço: proteção explícita dos executáveis do Aika (defense in depth)
PROCESSOS_PROTEGIDOS |= AIKA_GAME_EXES | AIKA_LAUNCHER_EXES
PROCESSOS_PROTEGIDOS |= {"warsaw.exe", "gbpsv.exe", "core.exe", "g-buster browser defense.exe", "gas tecnologia.exe", "gastecnologia.exe", "diebold.exe"}

# ========================================================
# SOFTWARES REAIS DE SEGURANCA (NUNCA ENCERRAR PELO AIKA OPTIMIZER)
# O 360 Total Security e equivalentes nao podem ser derrubados pelo booster:
# ferias disso desabilitaria a defesa do usuario durante a sessao (CRITICO).
# ========================================================
PROCESSOS_SEGURANCA_PROTEGIDOS = {
    "360safe.exe",   # 360 Total Security (protecao principal)
    "360se.exe",     # navegador/componente 360
    "360tray.exe",
    "360sd.exe",
    "360svc.exe",
}
PROCESSOS_PROTEGIDOS |= PROCESSOS_SEGURANCA_PROTEGIDOS

# ========================================================
# NOMES GENERICOS SEM IDENTIDADE SEGURA
# Nomes demasiado genericos jamais podem ser encerrados apenas porque
# coincidem com uma entrada da kill-list. Se nao houver como provar que
# pertencem ao software alvo, o processo e tratado como UNKNOWN (nao encerra).
# ========================================================
NOMES_GENERICOS_INSECUROS = frozenset({"agent.exe", "autoupdater.exe"})

# ========================================================
# ARMADURA DO KERNEL (NUNCA TOCAR NESTES PROCESSOS)
# ========================================================
PROCESSOS_CRITICOS = {
    # Kernel e Sistema
    "system", "system idle process", "registry",
    "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "svchost.exe",
    # Gerenciador de Janelas
    "dwm.exe", "explorer.exe",
    # Sessão e Autenticação
    "logonui.exe", "userinit.exe", "fontdrvhost.exe",
    # Gerenciamento
    "taskhostw.exe", "taskhost.exe", "wlms.exe",
    "spoolsv.exe", "sihost.exe",
    # WMI e Instrumentação
    "wmiprvse.exe", "winmgmt.exe",
    # Runtime
    "runtimebroker.exe", "shellexperiencehost.exe",
    "searchindexer.exe", "searchhost.exe", "searchapp.exe",
    "startmenuexperiencehost.exe", "textinputhost.exe",
    "systemsettingsbroker.exe", "applicationframehost.exe",
    # Segurança adicional
    "audiodg.exe", "conhost.exe",
    # Processos do próprio AIKA Optimizer
    "python.exe", "pythonw.exe",
}

SERVICOS_SAFE_STOP = ["XblGameSave", "XblAuthManager"]
if DESATIVAR_SYSMAIN:
    SERVICOS_SAFE_STOP.append("SysMain")

SERVICOS_PARADOS = set()

# ========================================================
# FUNÇÕES DE KERNEL E HEURÍSTICA
# ========================================================

def obter_pid_janela_focada():
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if hwnd:
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            valor_pid = pid.value
            
            agora = time.time()
            ULTIMOS_FOCADOS[valor_pid] = agora
            
            pids_para_remover = [p for p, t in ULTIMOS_FOCADOS.items() if (agora - t) > 60]
            for p in pids_para_remover:
                ULTIMOS_FOCADOS.pop(p, None)
                
            return valor_pid
    except Exception as e:
        log(f"Erro ao obter janela focada: {e}")
    return None

def _esvaziar_memoria(pid):
    handle = None
    try:
        FLAGS = 0x0400 | 0x0100 | 0x1000 
        handle = ctypes.windll.kernel32.OpenProcess(FLAGS, False, pid)
        if handle:
            # Captura a resposta Booleana da API do Windows para auditoria 100% real
            resultado = ctypes.windll.psapi.EmptyWorkingSet(handle)
            time.sleep(0.01)  
            return bool(resultado)
    except Exception as e:
        log(f"Erro inesperado ao trimar PID {pid}: {e}")
    finally:
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
    return False

def otimizar_ram_processos(pid_focado):
    liberado = 0
    
    for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'create_time']):
        try:
            pid = proc.info['pid']
            nome = (proc.info['name'] or "").lower()
            
            if pid == MEU_PID or pid == pid_focado or nome in PROCESSOS_PROTEGIDOS:
                continue

            # Escudo de Segurança: Pula processos vitais do Windows
            if nome in PROCESSOS_CRITICOS:
                continue

            if nome in PROCESSOS_REDUZIR_PRIORIDADE:
                if pid not in PRIORIDADES_ALTERADAS:
                    estado = {}
                    try: estado['nice'] = proc.nice()
                    except Exception: pass
                    
                    if hasattr(proc, 'ionice'):
                        try: estado['ionice'] = proc.ionice()
                        except Exception: pass
                    
                    # Defesa contra PID Reciclado
                    try: estado['create_time'] = proc.info['create_time']
                    except Exception: estado['create_time'] = 0
                        
                    PRIORIDADES_ALTERADAS[pid] = estado

                if hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS"):
                    try: proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                    except Exception: pass
                
                if hasattr(proc, "ionice"):
                    try: proc.ionice(psutil.IOPRIO_LOW)
                    except Exception: pass
        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
        except Exception as e: 
            log(f"Falha inesperada ao ajustar prioridade de {proc.info.get('name', 'PID ' + str(pid))}: {e}")
            
    return liberado

def matar_processo_e_filhos(p):
    try:
        children = []
        try:
            children = p.children(recursive=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
        
        for child in children:
            try: child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied): pass
        
        p.terminate()
        
        _, alive = psutil.wait_procs(children + [p], timeout=3)
        for p_alive in alive:
            try: p_alive.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied): pass

        # So conta como encerrado se o processo-alvo de fato morreu.
        # AccessDenied/falha/processo ainda vivo NAO infla a metrica.
        try:
            if psutil.pid_exists(p.pid) and psutil.Process(p.pid).is_running():
                return False
        except psutil.NoSuchProcess:
            return True
        except Exception:
            return False
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied): 
        return False
    except Exception as e: 
        log(f"Erro inesperado ao matar arvore de processos: {e}")
        return False

def obter_startupinfo_invisivel():
    si = None
    try:
        if os.name == 'nt':
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    except Exception as e:
        log(f"Erro ao configurar terminal invisível: {e}")
    return si

def _obter_estado_servico(servico, creation_flags, si):
    """Retorna o estado de um serviço Windows via 'sc query'.

    Retorna uma string: 'RUNNING', 'STOPPED', 'STOP_PENDING', ou None (erro/indisponível).
    Não lança exceção desnecessariamente.
    """
    try:
        r = subprocess.run(
            ["sc", "query", servico],
            capture_output=True, text=True,
            creationflags=creation_flags, startupinfo=si, timeout=5
        )
        stdout = r.stdout.upper() if r.stdout else ""
        if "RUNNING" in stdout:
            return "RUNNING"
        if "STOP_PENDING" in stdout:
            return "STOP_PENDING"
        if "STOPPED" in stdout:
            return "STOPPED"
        return None
    except subprocess.TimeoutExpired:
        log(f"Timeout ao consultar estado de {servico}")
        return None
    except Exception as e:
        log(f"Erro ao consultar estado de {servico}: {e}")
        return None


def parar_servicos_pesados():
    """Para serviços seguros com validação real do resultado.

    Somente conta como parado quando:
    1. Serviço estava RUNNING antes;
    2. sc stop retornou sucesso (returncode == 0);
    3. Estado final confirmado como STOPPED (após janela curta).
    """
    parados = 0
    creation_flags = 0x08000000 if os.name == 'nt' else 0
    si = obter_startupinfo_invisivel()

    for servico in SERVICOS_SAFE_STOP:
        try:
            estado_inicial = _obter_estado_servico(servico, creation_flags, si)
            if estado_inicial != "RUNNING":
                # Já parado ou em estado indeterminado → não tentamos parar
                continue

            r = subprocess.run(
                ["sc", "stop", servico],
                capture_output=True, creationflags=creation_flags,
                startupinfo=si, timeout=5
            )
            if r.returncode != 0:
                log(f"[SERVICO] Falha ao parar {servico} (returncode={r.returncode})")
                continue

            # Aguarda curta janela para transição (STOP_PENDING → STOPPED)
            confirmado = False
            for _ in range(4):  # ~2s máximo
                time.sleep(0.5)
                estado = _obter_estado_servico(servico, creation_flags, si)
                if estado == "STOPPED":
                    confirmado = True
                    break
                if estado == "RUNNING":
                    # Voltou a rodar → falha
                    break

            if confirmado:
                SERVICOS_PARADOS.add(servico)
                parados += 1
            else:
                log(f"[SERVICO] {servico}: stop enviado mas estado final não confirmado como STOPPED")

        except subprocess.TimeoutExpired:
            log(f"Timeout ao parar {servico}")
        except Exception as e:
            log(f"Erro inesperado ao parar serviço {servico}: {e}")

    return parados

def restaurar_prioridades():
    """Restaura prioridades originais, PID por PID, com retry.

    Cada PID e tratado individualmente:
    - Sucesso na restauracao -> removido do dicionario, contabilizado.
    - Processo nao existe mais (NoSuchProcess) -> removido, NAO conta.
    - PID reutilizado (create_time diferente) -> removido, NAO conta.
    - AccessDenied ou outra falha real -> MANTEM para retry futuro.

    NAO executa PRIORIDADES_ALTERADAS.clear() cegamente.
    """
    restaurados = 0
    for pid in list(PRIORIDADES_ALTERADAS.keys()):
        try:
            estado = PRIORIDADES_ALTERADAS[pid]
            # Verificar se processo ainda existe
            if not psutil.pid_exists(pid):
                PRIORIDADES_ALTERADAS.pop(pid, None)
                continue
            p = psutil.Process(pid)

            # Validacao Definitiva Anti-PID Reciclado (Precisao Matematica)
            if 'create_time' in estado and estado['create_time'] != 0:
                if p.create_time() != estado['create_time']:
                    # PID reutilizado por outro processo -> remove estado
                    PRIORIDADES_ALTERADAS.pop(pid, None)
                    continue

            # Tentativa real de restauracao
            try:
                if 'nice' in estado and estado['nice'] is not None:
                    p.nice(estado['nice'])
                if 'ionice' in estado and estado['ionice'] is not None and hasattr(p, 'ionice'):
                    p.ionice(estado['ionice'])
            except psutil.AccessDenied:
                log(f"[PRIORIDADE] AccessDenied ao restaurar PID {pid} - mantendo para retry")
                continue
            except Exception as e:
                log(f"[PRIORIDADE] Erro ao restaurar PID {pid}: {e} - mantendo para retry")
                continue

            # Restauracao completa com sucesso
            PRIORIDADES_ALTERADAS.pop(pid, None)
            restaurados += 1

        except psutil.NoSuchProcess:
            PRIORIDADES_ALTERADAS.pop(pid, None)
        except psutil.AccessDenied:
            log(f"[PRIORIDADE] AccessDenied ao acessar PID {pid} - mantendo para retry")
        except Exception as e:
            log(f"[PRIORIDADE] Erro inesperado ao processar PID {pid}: {e}")

    return restaurados

def restaurar_servicos_pesados():
    """Restaura serviços com validação real do resultado.

    Para cada serviço registrado em SERVICOS_PARADOS:
    1. Se já estiver RUNNING → remove do set (não conta como restaurado por nós);
    2. Executa sc start e valida returncode;
    3. Confirma estado em janela curta;
    4. Somente se realmente voltou → incrementa restaurados e remove do set;
    5. Se falhar → mantém no set para retry futuro.
    NÃO executa SERVICOS_PARADOS.clear() cegamente.
    """
    restaurados = 0
    creation_flags = 0x08000000 if os.name == 'nt' else 0
    si = obter_startupinfo_invisivel()

    for servico in list(SERVICOS_PARADOS):
        try:
            estado_atual = _obter_estado_servico(servico, creation_flags, si)
            if estado_atual == "RUNNING":
                # Já foi restaurado por outro meio → remove do set sem contar
                SERVICOS_PARADOS.discard(servico)
                continue

            r = subprocess.run(
                ["sc", "start", servico],
                capture_output=True, creationflags=creation_flags,
                startupinfo=si, timeout=5
            )
            if r.returncode != 0:
                log(f"[SERVICO] Falha ao iniciar {servico} (returncode={r.returncode})")
                # Mantém no set para retry futuro
                continue

            # Aguarda curta janela para transição
            confirmado = False
            for _ in range(4):  # ~2s máximo
                time.sleep(0.5)
                estado = _obter_estado_servico(servico, creation_flags, si)
                if estado == "RUNNING":
                    confirmado = True
                    break

            if confirmado:
                SERVICOS_PARADOS.discard(servico)
                restaurados += 1
            else:
                log(f"[SERVICO] {servico}: start enviado mas estado final não confirmado como RUNNING")
                # Mantém no set para retry futuro

        except subprocess.TimeoutExpired:
            log(f"Timeout ao iniciar {servico}")
        except Exception as e:
            log(f"Erro inesperado ao iniciar serviço {servico}: {e}")

    return restaurados

# ========================================================
# GAME SESSION OPTIMIZER V4.0
# NOVAS FUNÇÕES DE CLASSIFICAÇÃO, MÉTRICAS E SEGURANÇA
# ========================================================

def _obter_caminho_exe(proc):
    """Obtém o caminho completo do executável com segurança."""
    try:
        return proc.exe().lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    except Exception:
        return None

def _obter_usuario(proc):
    """Obtém o nome do usuário dono do processo."""
    try:
        return proc.username().lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    except Exception:
        return None

def _obter_processo_pai(proc):
    """Obtém (nome, pid) do processo pai com segurança."""
    try:
        parent = proc.parent()
        if parent:
            nome = parent.name() or ""
            return nome.lower(), parent.pid
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    except Exception:
        pass
    return None, None

def coletar_metricas():
    """
    Coleta métricas reais: CPU %, RAM disponível/usada, total de processos.
    Cada grupo é independente: falha em CPU não invalida RAM (e vice-versa).
    Valores indisponíveis são None; nunca são substituídos por zero sintético.
    """
    metricas = {
        "cpu_percent": None,
        "ram_total_gb": None,
        "ram_usada_gb": None,
        "ram_disponivel_gb": None,
        "ram_percent": None,
        "total_procs": None,
        "telemetry_errors": [],
    }

    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        if not isinstance(cpu_percent, (int, float)) or not math.isfinite(cpu_percent):
            raise ValueError("leitura de CPU não finita")
        metricas["cpu_percent"] = cpu_percent
    except Exception as e:
        metricas["telemetry_errors"].append("CPU")
        log(f"[TELEMETRIA][AVISO] CPU indisponível: {e}")

    try:
        mem = psutil.virtual_memory()
        ram_total_gb = mem.total / (1024 ** 3)
        ram_usada_gb = mem.used / (1024 ** 3)
        ram_disponivel_gb = mem.available / (1024 ** 3)
        ram_percent = mem.percent
        valores_ram = (ram_total_gb, ram_usada_gb, ram_disponivel_gb, ram_percent)
        if not all(isinstance(valor, (int, float)) and math.isfinite(valor)
                   for valor in valores_ram):
            raise ValueError("leitura de RAM não finita")
        metricas.update({
            "ram_total_gb": round(ram_total_gb, 1),
            "ram_usada_gb": round(ram_usada_gb, 1),
            "ram_disponivel_gb": round(ram_disponivel_gb, 1),
            "ram_percent": ram_percent,
        })
    except Exception as e:
        metricas["telemetry_errors"].append("RAM")
        log(f"[TELEMETRIA][AVISO] RAM indisponível: {e}")

    try:
        metricas["total_procs"] = len(list(psutil.process_iter()))
    except Exception as e:
        metricas["telemetry_errors"].append("PROCESSOS")
        log(f"[TELEMETRIA][AVISO] Contagem de processos indisponível: {e}")

    return metricas


def _texto_metrica(valor, sufixo=""):
    if isinstance(valor, (int, float)) and math.isfinite(valor):
        return f"{valor}{sufixo}"
    return "indisponível"


def _delta_metrica(antes, depois):
    if (isinstance(antes, (int, float)) and math.isfinite(antes)
            and isinstance(depois, (int, float)) and math.isfinite(depois)):
        return round(antes - depois, 1)
    return None

def classificar_processo(proc):
    """
    Classifica um processo em uma das 5 categorias usando múltiplas validações:
    nome, caminho, processo pai, usuário.
    NÃO confia apenas no nome do .exe.
    """
    try:
        pid = proc.pid
        nome = ""
        if hasattr(proc, 'info') and proc.info:
            nome = (proc.info.get('name') or "").lower().strip()
        if not nome:
            try:
                nome = (proc.name() or "").lower().strip()
            except Exception:
                pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return CategoriaProcesso.UNKNOWN

    # 1. PROTEÇÃO ABSOLUTA: Kernel e processos críticos do Windows
    if nome in PROCESSOS_CRITICOS:
        return CategoriaProcesso.PROTECTED

    # 2. PROTEÇÃO POR NOME: Jogo, AV, periféricos, anti-cheat
    if nome in PROCESSOS_PROTEGIDOS:
        caminho = _obter_caminho_exe(proc)
        if caminho:
            if "\\windows\\system32\\" in caminho:
                return CategoriaProcesso.PROTECTED
            if "\\windows defender\\" in caminho or "\\microsoft security client\\" in caminho:
                return CategoriaProcesso.PROTECTED
            if "\\cbmgames\\" in caminho or "aika" in caminho:
                return CategoriaProcesso.GAME
        return CategoriaProcesso.PROTECTED

    # 3. CLASSIFICAÇÃO POR CATEGORIA
    if nome in PROCESSOS_OPTIONAL_BG:
        return CategoriaProcesso.OPTIONAL_BACKGROUND
    if nome in PROCESSOS_KNOWN_UNWANTED:
        return CategoriaProcesso.KNOWN_UNWANTED

    # 4. VALIDAÇÃO ADICIONAL POR CAMINHO
    caminho = _obter_caminho_exe(proc)
    if caminho:
        if caminho.startswith("c:\\windows\\"):
            return CategoriaProcesso.PROTECTED
        if "windows defender" in caminho or "microsoft security" in caminho:
            return CategoriaProcesso.PROTECTED
        if any(ac in caminho for ac in ["gameguard", "easyanticheat", "battleye",
                                          "xigncode", "npggnt", "gamemon"]):
            return CategoriaProcesso.PROTECTED
        if "cbmgames" in caminho or "aikaonline" in caminho:
            return CategoriaProcesso.GAME

    # 5. Processos do usuário SYSTEM são geralmente serviços
    usuario = _obter_usuario(proc)
    if usuario and "system" in usuario and nome not in PROCESSOS_OPTIONAL_BG:
        if nome not in PROCESSOS_KNOWN_UNWANTED:
            return CategoriaProcesso.PROTECTED

    return CategoriaProcesso.UNKNOWN

def _validar_processo_para_encerramento(proc, categoria):
    """
    Validação final antes de encerrar: verifica PID, caminho, parent, usuário.
    Retorna (seguro, motivo).
    """
    pid = proc.pid
    nome = ""
    if hasattr(proc, 'info') and proc.info:
        nome = (proc.info.get('name') or "").lower().strip()
    if not nome:
        try:
            nome = (proc.name() or "").lower().strip()
        except Exception:
            pass

    if pid == MEU_PID:
        return False, "próprio processo do AIKA Optimizer"

    if categoria in (CategoriaProcesso.PROTECTED, CategoriaProcesso.GAME):
        return False, f"categoria {categoria.value}"

    if categoria == CategoriaProcesso.UNKNOWN:
        return False, "categoria UNKNOWN"

    caminho = _obter_caminho_exe(proc)
    if caminho:
        if caminho.startswith("c:\\windows\\"):
            return False, "executável localizado na pasta do Windows"
        if any(ac in caminho for ac in ["gameguard", "easyanticheat", "battleye",
                                          "xigncode", "npggnt", "gamemon"]):
            return False, "componente de anti-cheat detectado pelo caminho"
        if any(seg in caminho for seg in ["windows defender", "microsoft security client",
                                            "antivirus", "antimalware"]):
            return False, "software de segurança detectado pelo caminho"

    nome_pai, pid_pai = _obter_processo_pai(proc)
    if nome_pai in PROCESSOS_CRITICOS:
        return False, f"processo pai crítico ({nome_pai})"

    usuario = _obter_usuario(proc)
    if usuario and ("system" in usuario or "local service" in usuario or "network service" in usuario):
        if categoria != CategoriaProcesso.KNOWN_UNWANTED:
            return False, f"executando como {usuario} sem classificação UNWANTED"

    return True, ""


def _eh_navegador(nome, caminho):
    """Determina se um processo é um navegador reconhecido (nome ou nome genérico + path)."""
    if nome in NAVEGADORES:
        return True
    if nome in GENERIC_BROWSER_PATH_HINTS:
        if caminho and any(h in caminho for h in GENERIC_BROWSER_PATH_HINTS[nome]):
            return True
    return False


def _caminho_suspeito_navegador(caminho):
    """Rejeita navegador em local protegido/suspeito."""
    if not caminho:
        return False
    if caminho.startswith("c:\\windows\\"):
        return True
    if "system32" in caminho or "syswow64" in caminho:
        return True
    if any(t in caminho for t in ["cbmgames", "aika", "gameguard", "easyanticheat",
                                  "battleye", "xigncode", "windows defender",
                                  "antivirus", "antimalware"]):
        return True
    return False


def _validar_navegador_para_encerramento(proc, nome):
    """Validação dedicada para navegador reconhecido (Modo Agressivo).

    NÃO bloqueia por parent crítico — correção central do bug do Chromium
    (processo principal com parent=explorer.exe).
    """
    pid = proc.pid
    if pid == MEU_PID:
        return False, "próprio processo do AIKA Optimizer"
    caminho = _obter_caminho_exe(proc)
    if nome in GENERIC_BROWSER_PATH_HINTS:
        if not caminho or not any(h in caminho for h in GENERIC_BROWSER_PATH_HINTS[nome]):
            return False, "nome genérico sem path de navegador conhecido"
    if _caminho_suspeito_navegador(caminho):
        return False, "caminho protegido/suspeito"
    usuario = _obter_usuario(proc)
    if usuario and ("system" in usuario or "local service" in usuario or "network service" in usuario):
        return False, f"executando como {usuario}"
    return True, ""


def encerrar_navegadores_agressivos(pid_focado, dry_run, resultado):
    """Encerra navegadores no modo agressivo e só contabiliza PIDs realmente finalizados."""
    if not is_modo_agressivo():
        return set()
    navegadores = {}
    for proc in psutil.process_iter(['pid','name','memory_info','exe']):
        try:
            pid=proc.info['pid']; nome=(proc.info.get('name') or '').lower().strip()
            if pid in (MEU_PID,pid_focado) or nome in PROCESSOS_PROTEGIDOS or nome in PROCESSOS_CRITICOS: continue
            caminho=_obter_caminho_exe(proc)
            if not _eh_navegador(nome,caminho): continue
            seguro,_=_validar_navegador_para_encerramento(proc,nome)
            if seguro: navegadores.setdefault(nome,[]).append((pid,proc,nome))
        except (psutil.NoSuchProcess,psutil.AccessDenied): pass
        except Exception as e: log(f"[GAME SESSION] Erro ao varrer navegador: {e}")
    tratados=set()
    for nome,lista in navegadores.items():
        procs=[p for _,p,_ in lista]
        mem_antes={}
        for pid,p,n in lista:
            try: mem_antes[pid]=(p.info.get('memory_info').rss/(1024*1024)) if p.info.get('memory_info') else 0
            except Exception: mem_antes[pid]=0
        if dry_run:
            for pid,p,n in lista:
                resultado['detalhes_encerramentos'].append({'pid':pid,'nome':n,'categoria':'OPTIONAL_BACKGROUND','mem_mb':round(mem_antes[pid],1),'encerrado':False,'motivo':'DRY_RUN'})
            continue
        for pid,p,n in lista:
            tratados.add(pid)
            try: p.terminate()
            except (psutil.NoSuchProcess,psutil.AccessDenied): pass
        try: _,alive=psutil.wait_procs(procs,timeout=3)
        except Exception: alive=procs
        for p in alive:
            try: p.kill()
            except (psutil.NoSuchProcess,psutil.AccessDenied): pass
        try: _,alive_final=psutil.wait_procs(procs,timeout=1)
        except Exception: alive_final=alive
        vivos={getattr(p,'pid',None) for p in alive_final}
        encerrados=0
        for pid,p,n in lista:
            morto = pid not in vivos and not psutil.pid_exists(pid)
            if morto:
                encerrados += 1; resultado['processos_encerrados'] += 1; resultado['mem_associada_mb'] += mem_antes.get(pid,0)
            resultado['detalhes_encerramentos'].append({'pid':pid,'nome':n,'categoria':'OPTIONAL_BACKGROUND','mem_mb':round(mem_antes.get(pid,0),1),'encerrado':bool(morto),'motivo':'' if morto else 'Processo permaneceu ativo/AccessDenied'})
        log(f"[GAME SESSION] Browser {nome} encerrado: {encerrados}/{len(lista)} processos")
    return tratados

def prioridade_e_high(valor):
    """Compara a representação do psutil/Windows com HIGH_PRIORITY_CLASS."""
    if not hasattr(psutil, "HIGH_PRIORITY_CLASS"):
        return False
    try:
        return int(valor) == int(psutil.HIGH_PRIORITY_CLASS)
    except (TypeError, ValueError):
        return valor == psutil.HIGH_PRIORITY_CLASS


def nome_prioridade_windows(valor):
    """Nome legível da prioridade observada, sem inferir estado ausente."""
    if valor is None:
        return "indisponível"
    classes = (
        ("IDLE", "IDLE_PRIORITY_CLASS"),
        ("BELOW_NORMAL", "BELOW_NORMAL_PRIORITY_CLASS"),
        ("NORMAL", "NORMAL_PRIORITY_CLASS"),
        ("ABOVE_NORMAL", "ABOVE_NORMAL_PRIORITY_CLASS"),
        ("HIGH", "HIGH_PRIORITY_CLASS"),
    )
    for nome, atributo in classes:
        if hasattr(psutil, atributo):
            try:
                if int(valor) == int(getattr(psutil, atributo)):
                    return nome
            except (TypeError, ValueError):
                if valor == getattr(psutil, atributo):
                    return nome
    return str(valor)


def _pid_ainda_existe(pid):
    try:
        return bool(psutil.pid_exists(pid))
    except Exception:
        return None


def avaliar_prioridade_processo_aika(proc, nome=None, aplicar=True):
    """Lê, opcionalmente aplica HIGH e confirma o estado por releitura."""
    pid = getattr(proc, "pid", "?")
    if nome is None:
        try:
            nome = (getattr(proc, "info", {}).get("name") or proc.name() or "").lower()
        except Exception:
            nome = "aika.exe"
    detalhe = {
        "pid": pid,
        "name": nome,
        "before": None,
        "before_name": "indisponível",
        "requested": "HIGH_PRIORITY",
        "after": None,
        "after_name": "indisponível",
        "result": None,
        "operation": "READ_PRIORITY",
        "error_type": None,
        "error_message": None,
        "pid_exists_after": None,
    }

    try:
        antes = proc.nice()
        detalhe["before"] = antes
        detalhe["before_name"] = nome_prioridade_windows(antes)
    except psutil.NoSuchProcess as e:
        detalhe.update(result="disappeared", error_type=type(e).__name__,
                       error_message=str(e), pid_exists_after=False)
        return detalhe
    except Exception as e:
        detalhe.update(result="failed", error_type=type(e).__name__,
                       error_message=str(e), pid_exists_after=_pid_ainda_existe(pid))
        return detalhe

    if prioridade_e_high(antes):
        detalhe.update(result="already_high", operation="NONE", after=antes,
                       after_name=nome_prioridade_windows(antes),
                       pid_exists_after=True)
        return detalhe
    if not aplicar:
        detalhe.update(result="not_high", operation="READ_PRIORITY", after=antes,
                       after_name=nome_prioridade_windows(antes),
                       pid_exists_after=True)
        return detalhe

    detalhe["operation"] = "SET_HIGH_PRIORITY"
    try:
        if hasattr(psutil, "HIGH_PRIORITY_CLASS"):
            proc.nice(psutil.HIGH_PRIORITY_CLASS)
        else:
            PROCESS_HIGH_PRIORITY_CLASS = 0x00000080
            handle = ctypes.windll.kernel32.OpenProcess(0x0200, False, pid)
            if not handle:
                raise OSError("não foi possível abrir o processo")
            try:
                if not ctypes.windll.kernel32.SetPriorityClass(
                        handle, PROCESS_HIGH_PRIORITY_CLASS):
                    raise OSError("SetPriorityClass retornou falha")
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
    except psutil.NoSuchProcess as e:
        detalhe.update(result="disappeared", error_type=type(e).__name__,
                       error_message=str(e), pid_exists_after=False)
        return detalhe
    except Exception as e:
        detalhe.update(result="failed", error_type=type(e).__name__,
                       error_message=str(e), pid_exists_after=_pid_ainda_existe(pid))
        try:
            depois = proc.nice()
            detalhe["after"] = depois
            detalhe["after_name"] = nome_prioridade_windows(depois)
        except Exception:
            pass
        return detalhe

    detalhe["operation"] = "VERIFY_HIGH_PRIORITY"
    try:
        depois = proc.nice()
        detalhe["after"] = depois
        detalhe["after_name"] = nome_prioridade_windows(depois)
        detalhe["pid_exists_after"] = True
    except psutil.NoSuchProcess as e:
        detalhe.update(result="disappeared", error_type=type(e).__name__,
                       error_message=str(e), pid_exists_after=False)
        return detalhe
    except Exception as e:
        detalhe.update(result="failed", error_type=type(e).__name__,
                       error_message=f"releitura após setter: {e}",
                       pid_exists_after=_pid_ainda_existe(pid))
        return detalhe

    if prioridade_e_high(depois):
        detalhe["result"] = "changed"
    else:
        detalhe.update(result="failed", error_type="PriorityVerificationError",
                       error_message="releitura não confirmou HIGH_PRIORITY")
    return detalhe


def _log_detalhe_prioridade(detalhe):
    prefixo = f"[AIKA PRIORITY] {detalhe['name']} (PID {detalhe['pid']})"
    if detalhe["result"] == "already_high":
        log(f"{prefixo}: já estava em HIGH_PRIORITY")
    elif detalhe["result"] == "changed":
        log(f"{prefixo}: {detalhe['before_name']} -> HIGH_PRIORITY confirmado")
    elif detalhe["result"] == "disappeared":
        log(f"{prefixo}: processo desapareceu durante a análise")
    elif detalhe["result"] == "failed":
        log(
            f"{prefixo}: falha ao aplicar HIGH_PRIORITY | "
            f"etapa={detalhe['operation']} | antes={detalhe['before_name']} | "
            f"erro={detalhe['error_type']}: "
            f"{detalhe['error_message'] or 'sem mensagem'} | "
            f"pid_ativo={detalhe['pid_exists_after']} | depois={detalhe['after_name']}"
        )


def aplicar_high_priority_aika_detalhado(incluir_detalhes=False):
    """Aplica apenas HIGH; detalhes por PID são opcionais por compatibilidade."""
    relatorio = {
        "detected": 0, "already_high": 0, "changed": 0,
        "failed": 0, "disappeared": 0, "details": [],
    }
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            pid = getattr(proc, "pid", "?")
            try:
                nome = (proc.info.get('name') or "").lower()
                if nome not in AIKA_GAME_EXES:
                    continue
                pid = proc.info['pid']
                relatorio["detected"] += 1
                caminho = _obter_caminho_exe(proc)
                if caminho and ("\\windows\\system32\\" in caminho.lower()
                                and "aika" not in caminho.lower()
                                and "cbmgames" not in caminho.lower()):
                    detalhe = {
                        "pid": pid, "name": nome, "before": None,
                        "before_name": "indisponível", "requested": "HIGH_PRIORITY",
                        "after": None, "after_name": "indisponível",
                        "result": "failed", "operation": "VALIDATE_PROCESS",
                        "error_type": "InvalidProcessPath",
                        "error_message": "executável não parece ser um AIKA genuíno",
                        "pid_exists_after": _pid_ainda_existe(pid),
                    }
                else:
                    detalhe = avaliar_prioridade_processo_aika(proc, nome, aplicar=True)
                relatorio["details"].append(detalhe)
                resultado = detalhe["result"]
                if resultado in ("already_high", "changed", "failed", "disappeared"):
                    relatorio[resultado] += 1
                _log_detalhe_prioridade(detalhe)
            except psutil.NoSuchProcess as e:
                detalhe = {
                    "pid": pid, "name": "aika.exe", "before": None,
                    "before_name": "indisponível", "requested": "HIGH_PRIORITY",
                    "after": None, "after_name": "indisponível",
                    "result": "disappeared", "operation": "READ_PROCESS",
                    "error_type": type(e).__name__,
                    "error_message": str(e), "pid_exists_after": False,
                }
                relatorio["disappeared"] += 1
                relatorio["details"].append(detalhe)
                _log_detalhe_prioridade(detalhe)
            except Exception as e:
                detalhe = {
                    "pid": pid, "name": "aika.exe", "before": None,
                    "before_name": "indisponível", "requested": "HIGH_PRIORITY",
                    "after": None, "after_name": "indisponível",
                    "result": "failed", "operation": "READ_PROCESS",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "pid_exists_after": _pid_ainda_existe(pid),
                }
                relatorio["failed"] += 1
                relatorio["details"].append(detalhe)
                _log_detalhe_prioridade(detalhe)
    except Exception as e:
        relatorio["failed"] += 1
        log(f"[AIKA PRIORITY] Erro na enumeração: {type(e).__name__}: {e}")
    if not incluir_detalhes:
        relatorio.pop("details", None)
    return relatorio


def aplicar_high_priority_aika():
    """Compatibilidade: retorna somente quantas prioridades foram alteradas."""
    return aplicar_high_priority_aika_detalhado()["changed"]


def _quer_encerrar(categoria, modo_agressivo, nome=None):
    """Decide se uma categoria permite encerramento automatico.

    - PROTECTED / GAME / UNKNOWN: nunca encerrar.
    - KNOWN_UNWANTED: encerra, exceto nomes genericos sem identidade segura.
    - OPTIONAL_BACKGROUND: somente em modo agressivo.
    Nomes genericos (NOMES_GENERICOS_INSECUROS) nunca sao encerrados apenas
    pelo nome, mesmo que estejam em uma kill-list. Nome ausente/desconhecido
    tambem bloqueia: sem identidade, nao ha como provar o alvo.
    """
    if not nome or nome in NOMES_GENERICOS_INSECUROS:
        return False
    if categoria in (CategoriaProcesso.PROTECTED, CategoriaProcesso.GAME,
                     CategoriaProcesso.UNKNOWN):
        return False
    if categoria == CategoriaProcesso.KNOWN_UNWANTED:
        return True
    if categoria == CategoriaProcesso.OPTIONAL_BACKGROUND:
        return bool(modo_agressivo)
    return False


def _novo_resultado_sessao(dry_run=False, status="completed"):
    """Cria um resultado independente para cada acionamento do booster."""
    return {
        "status": status,
        "dry_run": dry_run,
        "metricas_antes": {},
        "metricas_depois": {},
        "processos_encerrados": 0,
        "mem_associada_mb": 0,
        "processos_avaliados": 0,
        "categorias_encontradas": {cat.value: 0 for cat in CategoriaProcesso},
        "detalhes_encerramentos": [],
        "aika_priority_applied": 0,
        "aika_priority_report": {
            "detected": 0,
            "already_high": 0,
            "changed": 0,
            "failed": 0,
            "disappeared": 0,
            "details": [],
        },
        "ram_trimmed": 0,
        "servicos_parados": 0,
    }


def _log_metricas_snapshot(rotulo, metricas):
    log(
        f"[GAME SESSION] Métricas {rotulo}: "
        f"CPU {_texto_metrica(metricas.get('cpu_percent'), '%')} | "
        f"RAM {_texto_metrica(metricas.get('ram_usada_gb'), 'GB')}/"
        f"{_texto_metrica(metricas.get('ram_total_gb'), 'GB')} "
        f"({_texto_metrica(metricas.get('ram_percent'), '%')}) | "
        f"{_texto_metrica(metricas.get('total_procs'))} processos"
    )


def _log_resultado_telemetria(resultado, prefixo=""):
    antes = resultado["metricas_antes"]
    depois = resultado["metricas_depois"]
    delta_cpu = _delta_metrica(
        antes.get("cpu_percent"), depois.get("cpu_percent")
    )
    delta_ram = _delta_metrica(
        antes.get("ram_percent"), depois.get("ram_percent")
    )
    log(f"[GAME SESSION] {prefixo}RESULTADO FINAL:")
    log(f"  {resultado['processos_encerrados']} processos encerrados | "
        f"{resultado['mem_associada_mb']:.0f} MB associados")
    log(
        f"  CPU antes: {_texto_metrica(antes.get('cpu_percent'), '%')} | "
        f"depois: {_texto_metrica(depois.get('cpu_percent'), '%')} | "
        f"Delta: {_texto_metrica(delta_cpu, '%')}"
    )
    log(
        f"  RAM antes: {_texto_metrica(antes.get('ram_percent'), '%')} | "
        f"depois: {_texto_metrica(depois.get('ram_percent'), '%')} | "
        f"Delta: {_texto_metrica(delta_ram, '%')}"
    )
    log(
        f"  Processos antes: {_texto_metrica(antes.get('total_procs'))} | "
        f"depois: {_texto_metrica(depois.get('total_procs'))}"
    )
    prioridade = resultado["aika_priority_report"]
    log(
        f"  AIKA: {prioridade['detected']} detectados | "
        f"{prioridade['already_high']} já HIGH | "
        f"{prioridade['changed']} alterados | "
        f"{prioridade['failed']} falhas | "
        f"{prioridade['disappeared']} desapareceram"
    )


def _reavaliar_booster_ativo(dry_run=False):
    """Gera nova telemetria sem repetir as fases destrutivas do booster."""
    resultado = _novo_resultado_sessao(dry_run, status="already_active")
    resultado["message"] = "Booster já estava ativo; telemetria renovada"
    resultado["metricas_antes"] = coletar_metricas()
    _log_metricas_snapshot("ANTES (REENTRADA)", resultado["metricas_antes"])
    if not dry_run:
        prioridade = aplicar_high_priority_aika_detalhado(incluir_detalhes=True)
        resultado["aika_priority_report"] = prioridade
        resultado["aika_priority_applied"] = prioridade["changed"]
    time.sleep(0.5)
    resultado["metricas_depois"] = coletar_metricas()
    _log_metricas_snapshot("DEPOIS (REENTRADA)", resultado["metricas_depois"])
    _log_resultado_telemetria(resultado)
    return resultado


def game_session_optimizer(dry_run=False):
    """
    GAME SESSION OPTIMIZER V4.0
    Motor principal de otimização para sessão de jogo.

    - dry_run=True: detecta e classifica sem encerrar (modo teste)
    - dry_run=False: executa encerramentos reais

    Retorna dict com métricas e resultados detalhados.
    """
    global BOOSTER_ATIVO, DRY_RUN

    with lock_otimizacao:
        if BOOSTER_ATIVO:
            return _reavaliar_booster_ativo(dry_run)

        DRY_RUN = dry_run
        BOOSTER_ATIVO = True

        resultado = _novo_resultado_sessao(dry_run)
        try:
            # FASE 0: Coletar métricas antes
            resultado["metricas_antes"] = coletar_metricas()
            antes = resultado["metricas_antes"]
            prefixo = "[DRY RUN] " if dry_run else ""
            _log_metricas_snapshot("ANTES", antes)

            pid_focado = obter_pid_janela_focada()

            # FASE 1.5: Encerramento de famílias de navegadores (Modo Agressivo)
            pids_navegadores_tratados = set()
            if is_modo_agressivo():
                pids_navegadores_tratados = encerrar_navegadores_agressivos(pid_focado, dry_run, resultado)

            # FASE 1: CLASSIFICAÇÃO DE TODOS OS PROCESSOS
            log(f"[GAME SESSION] {prefixo}Classificando processos...")

            for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'exe']):
                try:
                    pid = proc.info['pid']
                    nome = (proc.info.get('name') or "").lower().strip()
                    if pid == MEU_PID:
                        continue
                    if pid in pids_navegadores_tratados:
                        continue

                    categoria = classificar_processo(proc)
                    resultado["categorias_encontradas"][categoria.value] += 1
                    resultado["processos_avaliados"] += 1

                    # Decisão de encerramento
                    deve_encerrar = _quer_encerrar(
                        categoria,
                        is_modo_agressivo(),
                        nome,
                    )

                    if not deve_encerrar:
                        continue

                    # Validação final de segurança
                    seguro, motivo = _validar_processo_para_encerramento(proc, categoria)

                    mem_mb = 0
                    try:
                        if proc.info.get('memory_info'):
                            mem_mb = proc.info['memory_info'].rss / (1024 * 1024)
                    except Exception:
                        pass

                    if seguro:
                        if dry_run:
                            log(f"[DRY RUN] Seria encerrado: {nome} (PID {pid}) "
                                f"[{categoria.value}] — {mem_mb:.0f} MB")
                            resultado["detalhes_encerramentos"].append({
                                "pid": pid, "nome": nome,
                                "categoria": categoria.value,
                                "mem_mb": round(mem_mb, 1),
                                "encerrado": False, "motivo": "DRY_RUN"
                            })
                        else:
                            log(f"[GAME SESSION] Encerrando: {nome} (PID {pid}) "
                                f"[{categoria.value}] — {mem_mb:.0f} MB")
                            encerrado = matar_processo_e_filhos(proc)

                            if encerrado:
                                resultado["processos_encerrados"] += 1
                                resultado["mem_associada_mb"] += mem_mb
                                resultado["detalhes_encerramentos"].append({
                                    "pid": pid, "nome": nome,
                                    "categoria": categoria.value,
                                    "mem_mb": round(mem_mb, 1),
                                    "encerrado": True
                                })
                    else:
                        log(f"{prefixo}BLOQUEADO: {nome} (PID {pid}) "
                            f"[{categoria.value}] — {motivo}")

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                except Exception as e:
                    log(f"[GAME SESSION] Erro ao processar PID "
                        f"{proc.info.get('pid', '?')}: {e}")
            # FASE 3: Ajuste de prioridade de processos de fundo
            log(f"[GAME SESSION] {prefixo}Ajustando prioridade de processos de fundo...")
            if not dry_run:
                resultado["ram_trimmed"] = otimizar_ram_processos(pid_focado)

            # FASE 4: Parar serviços pesados (somente no Modo Agressivo)
            if is_modo_agressivo():
                log(f"[GAME SESSION] {prefixo}Parando serviços desnecessários...")
                if not dry_run:
                    resultado["servicos_parados"] = parar_servicos_pesados()
                else:
                    log(f"[DRY RUN] Serviços que seriam parados: {SERVICOS_SAFE_STOP}")
            else:
                log(f"[GAME SESSION] {prefixo}Serviços preservados (modo normal).")

            # FASE 5: HIGH PRIORITY para Aika.exe
            log(f"[GAME SESSION] {prefixo}Aplicando HIGH PRIORITY ao Aika.exe...")
            if not dry_run:
                prioridade = aplicar_high_priority_aika_detalhado(incluir_detalhes=True)
                resultado["aika_priority_report"] = prioridade
                resultado["aika_priority_applied"] = prioridade["changed"]
            else:
                log("[DRY RUN] Aika.exe receberia HIGH_PRIORITY_CLASS se em execução")

            # FASE 6: Coletar métricas depois
            time.sleep(0.5)
            resultado["metricas_depois"] = coletar_metricas()
            depois = resultado["metricas_depois"]

            # Log final com métricas reais
            _log_resultado_telemetria(resultado, prefixo)
            log(f"  Distribuição: {resultado['categorias_encontradas']}")

            return resultado

        except Exception as e:
            log(f"[GAME SESSION] Erro Crítico: {e}")
            resultado["status"] = "error"
            resultado["message"] = str(e)
            BOOSTER_ATIVO = False
            return resultado

def ativar_game_booster():
    """
    Versão de compatibilidade.
    Delega para o novo Game Session Optimizer V4.0.
    Mantém retorno (p_mortos, ram_otimizados, s_parados) para main.py.
    """
    resultado = game_session_optimizer(dry_run=False)
    
    if resultado.get("status") == "error":
        return 0, 0, 0
    
    return (
        resultado.get("processos_encerrados", 0),
        resultado.get("ram_trimmed", 0),
        resultado.get("servicos_parados", 0),
    )

def desativar_game_booster():
    global BOOSTER_ATIVO
    with lock_otimizacao:
        # Permite nova tentativa de cleanup mesmo com BOOSTER_ATIVO=False
        # se houver estado pendente (serviços que falharam na restauração anterior).
        if not BOOSTER_ATIVO:
            if not PRIORIDADES_ALTERADAS and not SERVICOS_PARADOS:
                return 0
            # Estado residual: tenta cleanup mesmo sem booster ativo
            log("[BOOSTER] Cleanup residual detectado (serviços ou prioridades pendentes)")

        try:
            restaurar_prioridades()
            s_restaurados = restaurar_servicos_pesados()
            return s_restaurados
        except Exception as e:
            log(f"Erro Crítico ao Desativar Booster: {e}")
            return 0
        finally:
            BOOSTER_ATIVO = False