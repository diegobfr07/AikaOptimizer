import ctypes, winreg, psutil, os, shutil
from config import *
from seguranca import fazer_backup_registro

def ativar_timer_resolution():
    try: ctypes.windll.winmm.timeBeginPeriod(1); log("[KERNEL] Timer Resolution cravado em 1ms.")
    except Exception: pass

def restaurar_timer_resolution():
    try: ctypes.windll.winmm.timeEndPeriod(1)
    except Exception: pass

def desativar_mpo():
    try:
        chave = r"SOFTWARE\Microsoft\Windows\Dwm"
        fazer_backup_registro("HKLM\\" + chave, "backup_mpo")
        # Correção Red Team: Gerenciador de contexto para não vazar a chave no Kernel
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, chave, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "OverlayTestMode", 0, winreg.REG_DWORD, 5)
        log("[REGISTRO] MPO desativado.")
        return True
    except Exception: return False

def limpar_shader_cache():
    try:
        localappdata = os.environ.get('LOCALAPPDATA', '')
        pastas = [os.path.join(localappdata, 'D3DSCache'), os.path.join(localappdata, 'NVIDIA', 'DXCache'), os.path.join(localappdata, 'AMD', 'DxCache')]
        
        pasta_cache_jogo = os.path.join(PASTA_JOGO_PADRAO, "Data", "Shaders", "Cache")
        if os.path.exists(pasta_cache_jogo) and caminho_seguro(PASTA_JOGO_PADRAO, pasta_cache_jogo):
            pastas.append(pasta_cache_jogo)

        for p in pastas:
            if os.path.exists(p): shutil.rmtree(p, ignore_errors=True)
        return True
    except Exception as e:
        log("Erro ao limpar shader cache", exception=True)
        return False

def otimizar_multimidia_jogos():
    try:
        chave_base = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
        fazer_backup_registro("HKLM\\" + chave_base, "backup_multimidia")
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, chave_base, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "NetworkThrottlingIndex", 0, winreg.REG_DWORD, 0xFFFFFFFF)
            winreg.SetValueEx(key, "SystemResponsiveness", 0, winreg.REG_DWORD, 0)

        chave_tasks = chave_base + r"\Tasks\Games"
        fazer_backup_registro("HKLM\\" + chave_tasks, "backup_mmcss_games")
        with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, chave_tasks) as key:
            winreg.SetValueEx(key, "GPU Priority", 0, winreg.REG_DWORD, 8) 
            winreg.SetValueEx(key, "Priority", 0, winreg.REG_DWORD, 6)
            winreg.SetValueEx(key, "Scheduling Category", 0, winreg.REG_SZ, "High")
            winreg.SetValueEx(key, "SFIO Priority", 0, winreg.REG_SZ, "High")
        return True
    except Exception: return False

def aplicar_afinidade_sem_cpu0(proc):
    """Remove somente a CPU lógica 0 da afinidade atual do processo, preservando as demais CPUs.

    Retorna True se a afinidade foi alterada; False se já otimizado, sem acesso ou sem CPUs disponíveis.
    """
    try:
        afinidade_atual = proc.cpu_affinity()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    except Exception:
        return False

    if not afinidade_atual:
        return False

    if 0 not in afinidade_atual:
        # CPU 0 já não faz parte da afinidade → já otimizado
        return False

    nova_afinidade = [cpu for cpu in afinidade_atual if cpu != 0]
    if not nova_afinidade:
        return False

    try:
        proc.cpu_affinity(nova_afinidade)
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    except Exception:
        return False


def otimizar_afinidade_aika():
    """Aplica afinidade (remove somente CPU 0) a TODOS os processos reais do jogo."""
    processados = 0
    try:
        for proc in psutil.process_iter(['name', 'pid']):
            nome = (proc.info.get('name') or "").lower()
            if nome not in AIKA_GAME_EXES:
                continue
            pid = proc.info['pid']
            try:
                if aplicar_afinidade_sem_cpu0(proc):
                    processados += 1
                    log(f"[CPU] CPU 0 removida do processo {nome} (PID {pid}).")
                else:
                    log(f"[CPU] {nome} (PID {pid}) já otimizado ou sem acesso.")
            except Exception as e:
                log(f"[CPU] Erro ao processar {nome} (PID {pid}): {e}")
    except Exception as e:
        log(f"[CPU] Erro na enumeração: {e}")
    return processados > 0