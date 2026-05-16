import os, subprocess, psutil, ctypes, time
from config import log, lock_otimizacao

# ========================================================
# CONFIGURAÇÕES ULTIMATE EDITION (V1.0 MASTER CLASS)
# ========================================================
MODO_AGRESSIVO = True
DESATIVAR_SYSMAIN = False 

MEU_PID = os.getpid()
BOOSTER_ATIVO = False
PRIORIDADES_ALTERADAS = {}

# Luxo Arquitetural: Memória de foco recente (Cooldown de Alt+Tab)
ULTIMOS_FOCADOS = {}
COOLDOWN_FOCO_SEGUNDOS = 15

# ========================================================
# ARQUITETURA DE LISTAS E BLINDAGEM DE KERNEL
# ========================================================

NAVEGADORES = {
    "msedge.exe", "chrome.exe", "firefox.exe", "opera.exe", "opera_gx.exe", "brave.exe", "vivaldi.exe", "yandex.exe"
}

PROCESSOS_MATAR = {
    "googleupdate.exe", "googlecrashhandler.exe", "msedgeupdate.exe", 
    "ccxprocess.exe", "adobearm.exe", "adobeupdateservice.exe", "acrotray.exe", "software_reporter_tool.exe", "autoupdater.exe",
    "onedrive.exe", "googledrivesync.exe", "googledrivefs.exe", "dropbox.exe", "dropboxupdate.exe", 
    "mega.exe", "megasync.exe", "boxsync.exe", "icloud.exe", "nextcloud.exe",
    "epicgameslauncher.exe", "epicwebhelper.exe", "origin.exe", "originwebhelperservice.exe", 
    "eadesktop.exe", "ubisoftconnect.exe", "upc.exe", "uplay.exe", "battle.net.exe", "agent.exe", 
    "riotclientservices.exe", "riotclientux.exe", "goggalaxy.exe", "leagueclient.exe",
    "skype.exe", "skypeapp.exe", "teams.exe", "ms-teams.exe", "zoom.exe", "webex.exe",
    "utorrent.exe", "bittorrent.exe", "qbittorrent.exe", "idm.exe", "idman.exe",
    "ccleaner.exe", "ccleaner64.exe", "ccupdate.exe", "advancedsystemcare.exe", "driverbooster.exe", 
    "wisecare365.exe", "glaryutilities.exe", "baidu.exe", "baiduan.exe", "hao123.exe", "360safe.exe", "qq.exe",
    "warsaw.exe", "gastecnologia.exe", "diebold.exe"
}

if MODO_AGRESSIVO:
    PROCESSOS_MATAR.update(NAVEGADORES)

PROCESSOS_REDUZIR_PRIORIDADE = {
    "discord.exe", "discordptb.exe", "discordcanary.exe", "ts3client_win64.exe",
    "spotify.exe", "spotifywebhelper.exe", "vlc.exe", "itunes.exe",
    "obs64.exe", "obs.exe", "bandicam.exe", "fraps.exe", "action.exe", "shadowplayhelper.exe",
    "steam.exe", "steamwebhelper.exe", "code.exe", "whatsapp.exe"
}

if not MODO_AGRESSIVO:
    PROCESSOS_REDUZIR_PRIORIDADE.update(NAVEGADORES)

PROCESSOS_NAO_TRIMAR = {
    "discord.exe", "discordptb.exe", "discordcanary.exe", 
    "obs64.exe", "obs.exe", "steam.exe", "steamwebhelper.exe"
}

PROCESSOS_PROTEGIDOS = {
    "aika.exe", "aika_br.exe", "aikabr.exe", "gameengine.exe", "aikalauncher.exe",
    "msmpeng.exe", "avp.exe", "avgui.exe", "avguard.exe", "nortonsecurity.exe", "ekrn.exe", "bdagent.exe",
    "razer synapse 3.exe", "razer synapse service.exe", "rzsynapse.exe", "rzsdkserver.exe",
    "lghub.exe", "ghub.exe", "logioptions.exe", "logioptionsplus.exe",
    "redragon.exe", "keyboarddriverutility.exe", "rdrgn.exe",
    "icue.exe", "corsair.service.exe", "steelseriesengine.exe", "gg.exe", "ngenuity.exe",
    "armourycrate.user.session.helper.exe", "armourycrate.service.exe",
    "autohotkey.exe", "macrorecorder.exe", "bloody6.exe", "bloody7.exe",
    "msiafterburner.exe", "rtss.exe", "rivatunerstatisticsserver.exe"
}

# ========================================================
# ARMADURA DO KERNEL (NUNCA TOCAR NESTES PROCESSOS)
# ========================================================
PROCESSOS_CRITICOS = {
    "csrss.exe", "wininit.exe", "services.exe", "lsass.exe", 
    "winlogon.exe", "smss.exe", "system", "registry", "explorer.exe", "svchost.exe"
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
    agora = time.time()
    
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
                
                if nome not in PROCESSOS_NAO_TRIMAR:
                    mem_mb = proc.info['memory_info'].rss / (1024 * 1024) if proc.info['memory_info'] else 0
                    
                    foi_focado_recentemente = False
                    if pid in ULTIMOS_FOCADOS and (agora - ULTIMOS_FOCADOS[pid]) < COOLDOWN_FOCO_SEGUNDOS:
                        foi_focado_recentemente = True

                    if mem_mb >= 150 and not foi_focado_recentemente: 
                        if _esvaziar_memoria(pid):
                            liberado += 1
                            
        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
        except Exception as e: 
            log(f"Falha inesperada ao otimizar RAM de {proc.info.get('name', 'PID ' + str(pid))}: {e}")
            
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
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied): 
        return False
    except Exception as e: 
        log(f"Erro inesperado ao matar arvore de processos: {e}")
        return False

def finalizar_bloatwares(pid_focado):
    encerrados = 0
    for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            pid = proc.info['pid']
            nome = (proc.info['name'] or "").lower()
            
            if pid == MEU_PID or pid == pid_focado or nome in PROCESSOS_PROTEGIDOS:
                continue

            # Escudo de Segurança: Pula processos vitais do Windows
            if nome in PROCESSOS_CRITICOS:
                continue

            if nome in PROCESSOS_MATAR:
                mem_mb = proc.info['memory_info'].rss / (1024 * 1024) if proc.info['memory_info'] else 0
                
                if mem_mb > 50 or "update" in nome or "utorrent" in nome or "ccleaner" in nome:
                    if matar_processo_e_filhos(proc):
                        encerrados += 1
                        
        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
        except Exception as e: 
            log(f"Falha inesperada ao finalizar {proc.info.get('name', 'PID ' + str(pid))}: {e}")
            
    return encerrados

def obter_startupinfo_invisivel():
    si = None
    try:
        if os.name == 'nt':
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    except Exception as e:
        log(f"Erro ao configurar terminal invisivel: {e}")
    return si

def parar_servicos_pesados():
    parados = 0
    creation_flags = 0x08000000 if os.name == 'nt' else 0
    si = obter_startupinfo_invisivel()
    
    for servico in SERVICOS_SAFE_STOP:
        try:
            status = subprocess.run(["sc", "query", servico], capture_output=True, text=True, creationflags=creation_flags, startupinfo=si, timeout=5)
            if "RUNNING" in status.stdout.upper():
                subprocess.run(["sc", "stop", servico], capture_output=True, creationflags=creation_flags, startupinfo=si, timeout=5)
                SERVICOS_PARADOS.add(servico)
                parados += 1
        except subprocess.TimeoutExpired: 
            log(f"Timeout ao parar {servico}")
        except Exception as e: 
            log(f"Erro inesperado ao parar serviço {servico}: {e}")
    return parados

def restaurar_prioridades():
    restaurados = 0
    for pid in list(PRIORIDADES_ALTERADAS.keys()):
        try:
            estado = PRIORIDADES_ALTERADAS[pid]
            p = psutil.Process(pid)
            
            # Validação Definitiva Anti-PID Reciclado (Precisão Matemática)
            if 'create_time' in estado and estado['create_time'] != 0:
                if p.create_time() != estado['create_time']:
                    continue  # O PID existe, mas é outro programa. Ignora!

            if 'nice' in estado and estado['nice'] is not None:
                p.nice(estado['nice'])
            if 'ionice' in estado and estado['ionice'] is not None and hasattr(p, 'ionice'):
                p.ionice(estado['ionice'])
            restaurados += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
        except Exception as e:
            log(f"Erro inesperado ao restaurar prioridade do PID {pid}: {e}")
            
    PRIORIDADES_ALTERADAS.clear()
    return restaurados

def restaurar_servicos_pesados():
    restaurados = 0
    creation_flags = 0x08000000 if os.name == 'nt' else 0
    si = obter_startupinfo_invisivel()
    
    for servico in list(SERVICOS_PARADOS):
        try:
            subprocess.run(["sc", "start", servico], capture_output=True, creationflags=creation_flags, startupinfo=si, timeout=5)
            restaurados += 1
        except subprocess.TimeoutExpired: 
            log(f"Timeout ao iniciar {servico}")
        except Exception as e: 
            log(f"Erro inesperado ao iniciar serviço {servico}: {e}")
            
    SERVICOS_PARADOS.clear()
    return restaurados

def ativar_game_booster():
    global BOOSTER_ATIVO
    with lock_otimizacao:
        if BOOSTER_ATIVO: 
            return 0, 0, 0
            
        BOOSTER_ATIVO = True
        try:
            pid_focado = obter_pid_janela_focada()
            p_mortos = finalizar_bloatwares(pid_focado)
            ram_otimizados = otimizar_ram_processos(pid_focado)
            s_parados = parar_servicos_pesados()
            
            return p_mortos, ram_otimizados, s_parados
        except Exception as e:
            log(f"Erro Crítico ao Ativar Booster: {e}")
            BOOSTER_ATIVO = False
            return 0, 0, 0

def desativar_game_booster():
    global BOOSTER_ATIVO
    with lock_otimizacao:
        if not BOOSTER_ATIVO:
            return 0
            
        try:
            restaurar_prioridades()  
            s_restaurados = restaurar_servicos_pesados()
            return s_restaurados
        except Exception as e:
            log(f"Erro Crítico ao Desativar Booster: {e}")
            return 0
        finally:
            BOOSTER_ATIVO = False