import os, shutil, json, time, re, ipaddress, stat, subprocess
from config import *

def criar_substituto_old(destino):
    backup_old = destino + ".old"
    try: os.replace(destino, backup_old)
    except OSError:
        if os.path.exists(backup_old):
            try: os.remove(backup_old)
            except Exception: pass
        try: os.replace(destino, backup_old)
        except Exception: pass

def fazer_backup_rapido(caminho_original, caminho_backup):
    try:
        if not os.path.exists(caminho_original): return False
        os.makedirs(os.path.dirname(caminho_backup), exist_ok=True)
        shutil.copyfile(caminho_original, caminho_backup)
        return True
    except Exception: return False

def fazer_backup_registro(chave_completa, nome_arquivo):
    try:
        os.makedirs(PASTA_BACKUP_REG, exist_ok=True)
        destino = os.path.join(PASTA_BACKUP_REG, f"{nome_arquivo}.reg")
        if not os.path.exists(destino): executar_comando_seguro(['reg', 'export', chave_completa, destino, '/y'])
    except Exception: pass

class TransacaoSistema:
    def __init__(self):
        self.passos_executados = []

    def executar(self, func, *args, rollback=None, rollback_args=None):
        try:
            resultado = func(*args)
            if rollback:
                r_args = rollback_args if rollback_args else ()
                self.passos_executados.append((rollback, r_args))
            return resultado
        except Exception as e:
            log(f"[FALHA CRÍTICA] Transação abortada na etapa: {func.__name__}")
            self.rollback_total()
            raise e

    def rollback_total(self):
        log("[SEGURANÇA] Iniciando Rollback automático...")
        for acao, r_args in reversed(self.passos_executados):
            try: acao(*r_args)
            except Exception: pass

def obter_plano_energia_atual():
    try:
        # CORREÇÃO: Flag de invisibilidade adicionada aqui!
        creation_flags = 0x08000000 if os.name == 'nt' else 0
        res = subprocess.check_output(['powercfg', '/getactivescheme'], text=True, stderr=subprocess.DEVNULL, creationflags=creation_flags)
        match = re.search(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', res)
        return match.group(0) if match else None
    except Exception: return None

def obter_dns_atual():
    try:
        # CORREÇÃO: Flag de invisibilidade adicionada aqui!
        creation_flags = 0x08000000 if os.name == 'nt' else 0
        cmd = "Get-NetAdapter | Where-Object {$_.Status -eq 'Up' -and $_.InterfaceDescription -notmatch 'Virtual|VMware|Hyper-V|TAP'} | Get-DnsClientServerAddress | Select-Object -ExpandProperty ServerAddresses"
        res = subprocess.check_output(['powershell', '-Command', cmd], text=True, stderr=subprocess.DEVNULL, creationflags=creation_flags)
        ips = [linha.strip() for linha in res.splitlines() if linha.strip()]
        return ips if ips else None
    except Exception: return None

def salvar_snapshot_sistema():
    with snapshot_lock:
        try:
            estado = {"power_plan": obter_plano_energia_atual(), "dns": obter_dns_atual(), "timestamp": time.time()}
            temp_file = ARQUIVO_ESTADO + ".tmp"
            with open(temp_file, "w") as f: json.dump(estado, f, indent=4)
            os.replace(temp_file, ARQUIVO_ESTADO)
        except Exception: pass

def restaurar_snapshot_sistema():
    if not os.path.exists(ARQUIVO_ESTADO): return
    try:
        with open(ARQUIVO_ESTADO, "r") as f: estado = json.load(f)
        if estado.get("power_plan"):
            executar_comando_seguro(['powercfg', '/setactive', estado.get("power_plan")])
        if estado.get("dns"):
            dns_validos = []
            for d in estado["dns"]:
                try: dns_validos.append(str(ipaddress.ip_address(d)))
                except ValueError: pass
            if dns_validos:
                dns_list = ",".join([f"'{d}'" for d in dns_validos])
                executar_comando_seguro(['powershell', '-Command', f"Get-NetAdapter | Where-Object {{$_.Status -eq 'Up'}} | Set-DnsClientServerAddress -ServerAddresses ({dns_list})"])
        else:
            executar_comando_seguro(['powershell', '-Command', "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Set-DnsClientServerAddress -ResetServerAddresses"])
    except Exception: pass

def criar_ponto_restauracao():
    try:
        marcador = os.path.join(PASTA_BACKUP, "ponto_restauracao_criado.txt")
        if os.path.exists(marcador): return True
        cmd = ['powershell', '-ExecutionPolicy', 'Bypass', '-Command', 'Checkpoint-Computer -Description "AikaOptimizer_Backup_Seguranca" -RestorePointType "MODIFY_SETTINGS"']
        if executar_comando_seguro(cmd):
            os.makedirs(PASTA_BACKUP, exist_ok=True)
            with open(marcador, 'w') as f: f.write("Criado.")
            return True
        return False
    except Exception: return False

def restaurar_tudo_jogo(pasta_jogo=PASTA_JOGO_PADRAO):
    with lock_otimizacao:
        try:
            if not os.path.exists(PASTA_BACKUP): return False, "Nenhum backup encontrado."
            arquivos_restaurados = 0
            backup_files = []
            for root, dirs, files in os.walk(PASTA_BACKUP):
                if "Registro_Sistema" in root: continue
                for file in files:
                    if file in ["aika_optimizer.log", "ponto_restauracao_criado.txt", "estado_sistema.json", "estado_sistema.json.tmp", "aika_index.json"]: continue
                    backup_files.append(os.path.join(root, file))

            BATCH_SIZE = 50
            for i in range(0, len(backup_files), BATCH_SIZE):
                batch = backup_files[i:i+BATCH_SIZE]
                for caminho_backup in batch:
                    caminho_destino = os.path.join(pasta_jogo, os.path.relpath(caminho_backup, PASTA_BACKUP))
                    if not caminho_seguro(pasta_jogo, caminho_destino): continue
                    
                    os.makedirs(os.path.dirname(caminho_destino), exist_ok=True)
                    try:
                        if os.path.exists(caminho_destino):
                            os.chmod(caminho_destino, stat.S_IWRITE)
                            criar_substituto_old(caminho_destino)
                        shutil.copyfile(caminho_backup, caminho_destino)
                        arquivos_restaurados += 1
                    except Exception: pass
                if i + BATCH_SIZE < len(backup_files): time.sleep(0.05)
            return True, f"Sucesso! {arquivos_restaurados} arquivos restaurados."
        except Exception as e: return False, f"Erro: {str(e)}"

def restaurar_registro_sistema():
    with lock_otimizacao:
        try:
            restaurar_snapshot_sistema()
            for exe in ["aika.exe", "aika_br.exe", "aikabr.exe", "GameEngine.exe", "gameengine.exe"]:
                chave_ifeo = f"HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Image File Execution Options\\{exe}\\PerfOptions"
                executar_comando_seguro(['reg', 'delete', chave_ifeo, '/f'])
            if not os.path.exists(PASTA_BACKUP_REG): return False, "Sem backup de registro."
            restaurados = 0
            for arquivo in os.listdir(PASTA_BACKUP_REG):
                if arquivo.endswith(".reg"):
                    if executar_comando_seguro(['reg', 'import', os.path.join(PASTA_BACKUP_REG, arquivo)]): restaurados += 1
            return True, f"Sistema revertido! ({restaurados} chaves restauradas)"
        except Exception as e: return False, str(e)