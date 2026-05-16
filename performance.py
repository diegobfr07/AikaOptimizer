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

def otimizar_afinidade_aika():
    lista_exes = ["aika.exe", "aika_br.exe", "gameengine.exe", "aikabr.exe", "aikalauncher.exe"]
    sucesso = False
    try:
        for proc in psutil.process_iter(['name', 'pid']):
            nome = proc.info['name']
            if nome and nome.lower() in lista_exes:
                pid = proc.info['pid']
                cpu_count = psutil.cpu_count(logical=False) or psutil.cpu_count()
                
                if cpu_count >= 4: alvo, mask = list(range(1, cpu_count)), (1 << cpu_count) - 2
                elif cpu_count >= 2: alvo, mask = [1], 2
                else: alvo, mask = [0], 1
                
                try:
                    p = psutil.Process(pid)
                    p.cpu_affinity(alvo)
                    sucesso = True
                    log(f"[CPU] Processo {nome} isolado nos núcleos: {alvo}")
                except Exception:
                    try:
                        cmd = ['powershell', '-Command', f"(Get-Process -Id {pid}).ProcessorAffinity = {mask}"]
                        if executar_comando_seguro(cmd):
                            sucesso = True
                            log(f"[CPU] Processo {nome} isolado via PowerShell.")
                    except Exception: pass
    except Exception: pass
    return sucesso