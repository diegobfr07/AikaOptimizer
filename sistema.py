import os, winreg, psutil, winshell
from config import *
from seguranca import fazer_backup_registro, criar_ponto_restauracao, salvar_snapshot_sistema

def apagar_arquivos_pasta(caminho_pasta):
    if not os.path.exists(caminho_pasta): return
    for root, dirs, files in os.walk(caminho_pasta):
        for f in files:
            try:
                caminho = os.path.join(root, f)
                os.chmod(caminho, __import__('stat').S_IWRITE)
                os.remove(caminho)
            except Exception: pass 

def limpar_profundo(esvaziar_lixeira=False):
    try:
        criar_ponto_restauracao()
        if esvaziar_lixeira:
            try: winshell.recycle_bin().empty(confirm=False, show_progress=False, sound=False)
            except Exception: pass
        windir = os.environ.get('WINDIR', r'C:\Windows')
        pastas = [os.environ.get('TEMP'), os.path.join(windir, 'Temp'), os.path.join(windir, 'SoftwareDistribution', 'Download')]
        for pasta in pastas:
            if pasta: apagar_arquivos_pasta(pasta)
        return True
    except Exception as e: raise e

def modo_desempenho_maximo():
    executar_comando_seguro(['powercfg', '/setactive', '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c'])
    return True

def otimizar_rede_estabilidade():
    if not executar_comando_seguro(['ipconfig', '/flushdns']): raise Exception("Falha ao limpar cache DNS")
    return True

def prioridade_total():
    try:
        sucesso = False
        lista_exes = ["aika.exe", "aika_br.exe", "aikabr.exe", "GameEngine.exe", "aikalauncher.exe"]
        for exe in lista_exes:
            chave = f"HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Image File Execution Options\\{exe}"
            fazer_backup_registro(chave, f"backup_prioridade_{exe}")
            cmd = ['reg', 'add', f"{chave}\\PerfOptions", '/v', 'CpuPriorityClass', '/t', 'REG_DWORD', '/d', '6', '/f']
            if executar_comando_seguro(cmd): sucesso = True

        for proc in psutil.process_iter(['name', 'pid']):
            nome = proc.info['name']
            if nome and nome.lower() in lista_exes:
                pid = proc.info['pid']
                try:
                    p = psutil.Process(pid)
                    if hasattr(psutil, "ABOVE_NORMAL_PRIORITY_CLASS"): p.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
                    if hasattr(psutil, "IOPRIO_HIGH"): p.ionice(psutil.IOPRIO_HIGH)
                    sucesso = True
                except Exception:
                    try:
                        cmd = ['powershell', '-Command', f"(Get-Process -Id {pid}).PriorityClass = 'AboveNormal'"]
                        if executar_comando_seguro(cmd): sucesso = True
                    except Exception: pass
        return sucesso
    except Exception: return False

def desativar_game_bar():
    try:
        fazer_backup_registro(r"HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR", "backup_gamedvr")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\GameDVR", 0, winreg.KEY_SET_VALUE) as key1:
            winreg.SetValueEx(key1, "AppCaptureEnabled", 0, winreg.REG_DWORD, 0)
            winreg.SetValueEx(key1, "GameDVR_Enabled", 0, winreg.REG_DWORD, 0)

        fazer_backup_registro(r"HKCU\System\GameConfigStore", "backup_gameconfigstore")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"System\GameConfigStore", 0, winreg.KEY_SET_VALUE) as key2:
            winreg.SetValueEx(key2, "GameDVR_Enabled", 0, winreg.REG_DWORD, 0)
            winreg.SetValueEx(key2, "GameDVR_FSEBehaviorMode", 0, winreg.REG_DWORD, 2)
            winreg.SetValueEx(key2, "GameDVR_HonorUserFSEBehaviorMode", 0, winreg.REG_DWORD, 0)
        return True
    except Exception: return True

def alterar_dns(escolha):
    salvar_snapshot_sistema()
    try:
        base_cmd = "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | "
        if escolha == "Google": cmd = ['powershell', '-Command', base_cmd + "Set-DnsClientServerAddress -ServerAddresses ('8.8.8.8','8.8.4.4')"]
        elif escolha == "Cloudflare": cmd = ['powershell', '-Command', base_cmd + "Set-DnsClientServerAddress -ServerAddresses ('1.1.1.1','1.0.0.1')"]
        else: cmd = ['powershell', '-Command', base_cmd + "Set-DnsClientServerAddress -ResetServerAddresses"]
        return executar_comando_seguro(cmd)
    except Exception: return False

def otimizar_tcp_nodelay():
    try:
        interfaces_path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
        fazer_backup_registro(f"HKLM\\{interfaces_path}", "backup_tcp_nodelay")
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, interfaces_path, 0, winreg.KEY_READ) as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                subkey_name = winreg.EnumKey(key, i)
                subkey_path = f"{interfaces_path}\\{subkey_name}"
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey_path, 0, winreg.KEY_SET_VALUE) as subkey:
                        winreg.SetValueEx(subkey, "TcpAckFrequency", 0, winreg.REG_DWORD, 1)
                        winreg.SetValueEx(subkey, "TCPNoDelay", 0, winreg.REG_DWORD, 1)
                except Exception: pass
        return True
    except Exception as e: raise e