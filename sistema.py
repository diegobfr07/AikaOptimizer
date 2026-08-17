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
    if not executar_comando_seguro(['powercfg', '/setactive', '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c']):
        raise Exception("Falha ao ativar modo de desempenho máximo")
    return True

def otimizar_rede_estabilidade():
    if not executar_comando_seguro(['ipconfig', '/flushdns']): raise Exception("Falha ao limpar cache DNS")
    return True

def prioridade_total():
    try:
        sucesso = False
        for exe in AIKA_GAME_EXES:
            chave = f"HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Image File Execution Options\\{exe}"
            fazer_backup_registro(chave, f"backup_prioridade_{exe}")
            cmd = ['reg', 'add', f"{chave}\\PerfOptions", '/v', 'CpuPriorityClass', '/t', 'REG_DWORD', '/d', '6', '/f']
            if executar_comando_seguro(cmd): sucesso = True

        for proc in psutil.process_iter(['name', 'pid']):
            nome = (proc.info.get('name') or "").lower()
            if nome in AIKA_GAME_EXES:
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
    except Exception: return False

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
        interfaces_alteradas = 0
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, interfaces_path, 0, winreg.KEY_READ) as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                subkey_name = winreg.EnumKey(key, i)
                subkey_path = f"{interfaces_path}\\{subkey_name}"
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey_path, 0, winreg.KEY_SET_VALUE) as subkey:
                        winreg.SetValueEx(subkey, "TcpAckFrequency", 0, winreg.REG_DWORD, 1)
                        winreg.SetValueEx(subkey, "TCPNoDelay", 0, winreg.REG_DWORD, 1)
                        interfaces_alteradas += 1
                except Exception as e:
                    log(f"[REDE] Falha ao aplicar TCP NoDelay em {subkey_name}: {e}")
        if interfaces_alteradas > 0:
            return True
        log("[REDE] Nenhuma interface TCP pôde ser alterada (TCP NoDelay).")
        return False
    except Exception as e: raise e

# ========================================================
# DIAGNÓSTICO DE REDE (LEITURA + FLUSH DNS)
# ========================================================
import subprocess
import json

_FLAGS_OCULTO = 0x08000000 if os.name == 'nt' else 0

def _executar_powershell_oculto(script, timeout=30):
    """Executa PowerShell com janela oculta e retorna o stdout (str) ou None."""
    try:
        resultado = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
            capture_output=True, text=True, timeout=timeout, creationflags=_FLAGS_OCULTO
        )
        return resultado.stdout
    except Exception:
        return None

def _executar_powershell_oculto_detalhe(script, timeout=30):
    """Executa PowerShell oculto e retorna (stdout, stderr) para diagnóstico."""
    try:
        resultado = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
            capture_output=True, text=True, timeout=timeout, creationflags=_FLAGS_OCULTO
        )
        return resultado.stdout, resultado.stderr
    except Exception as e:
        return None, str(e)

def _resumir_erro_powershell(stderr):
    """Extrai uma mensagem curta e legível do stderr do PowerShell."""
    if not stderr:
        return ""
    for linha in stderr.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if linha.lower().startswith("at "):
            continue
        if " : " in linha:
            linha = linha.split(" : ", 1)[1].strip()
        if linha:
            return linha
    return ""

def diagnosticar_rede():
    """Retorna {'adapter': str, 'dns': [str, ...]} do adaptador usado pela rota IPv4 padrão."""
    script = (
        "$r = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | "
        "Sort-Object RouteMetric | Select-Object -First 1; "
        "if (-not $r) { $r = Get-NetRoute -ErrorAction SilentlyContinue | Sort-Object RouteMetric | Select-Object -First 1 }; "
        "if ($r) { "
        "  $idx = $r.InterfaceIndex; "
        "  $a = Get-NetAdapter -InterfaceIndex $idx -ErrorAction SilentlyContinue; "
        "  $alias = if ($a) { $a.InterfaceAlias } else { ('Interface ' + $idx) }; "
        "  $dns = @(Get-DnsClientServerAddress -InterfaceIndex $idx -AddressFamily IPv4 -ErrorAction SilentlyContinue | ForEach-Object { $_.ServerAddresses } | Where-Object { $_ }); "
        "  [PSCustomObject]@{ adapter = $alias; dns = $dns } | ConvertTo-Json -Compress "
        "}"
    )
    saida = _executar_powershell_oculto(script, timeout=30)
    if not saida:
        return {"adapter": "Não identificado", "dns": []}
    try:
        dados = json.loads(saida.strip())
        adapter = str(dados.get("adapter") or "Não identificado")
        dns = dados.get("dns")
        if isinstance(dns, str):
            dns = [dns]
        elif dns is None:
            dns = []
        else:
            dns = [str(x) for x in dns]
        return {"adapter": adapter, "dns": dns}
    except Exception:
        return {"adapter": "Não identificado", "dns": []}

def testar_dns_latencia():
    """Mede latência de resolução DNS real (Resolve-DnsName -Server) de Google e Cloudflare.

    Retorna {'google_ms': float|None, 'cloudflare_ms': float|None, 'menor': str}.
    """
    script = (
        "function Medir($srv) { "
        "  $t = @(); "
        "  for ($i = 0; $i -lt 3; $i++) { "
        "    try { "
        "      $sw = [System.Diagnostics.Stopwatch]::StartNew(); "
        "      Resolve-DnsName -Name example.com -Server $srv -DnsOnly -ErrorAction Stop | Out-Null; "
        "      $sw.Stop(); "
        "      $t += $sw.Elapsed.TotalMilliseconds "
        "    } catch { } "
        "  }; "
        "  if ($t.Count -eq 0) { return $null }; "
        "  $s = $t | Sort-Object; "
        "  if ($s.Count % 2 -eq 1) { return $s[[int](($s.Count - 1) / 2)] } "
        "  else { return (($s[[int]($s.Count / 2)] + $s[[int]($s.Count / 2 - 1)]) / 2.0) } "
        "}; "
        "$g = Medir '8.8.8.8'; "
        "$c = Medir '1.1.1.1'; "
        "[PSCustomObject]@{ google = $g; cloudflare = $c } | ConvertTo-Json -Compress"
    )
    saida = _executar_powershell_oculto(script, timeout=45)
    resultado = {"google_ms": None, "cloudflare_ms": None, "menor": "N/D"}
    if saida:
        try:
            dados = json.loads(saida.strip())
            g = dados.get("google")
            c = dados.get("cloudflare")
            g = float(g) if isinstance(g, (int, float)) else None
            c = float(c) if isinstance(c, (int, float)) else None
            resultado["google_ms"] = g
            resultado["cloudflare_ms"] = c
            if g is not None and c is not None:
                if c < g:
                    resultado["menor"] = "Cloudflare"
                elif g < c:
                    resultado["menor"] = "Google"
                else:
                    resultado["menor"] = "Empate"
            elif g is not None:
                resultado["menor"] = "Google"
            elif c is not None:
                resultado["menor"] = "Cloudflare"
        except Exception:
            pass
    return resultado

def limpar_cache_dns():
    """Executa ipconfig /flushdns e retorna True em caso de sucesso."""
    try:
        resultado = subprocess.run(
            ['ipconfig', '/flushdns'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=30, creationflags=_FLAGS_OCULTO
        )
        return resultado.returncode == 0
    except Exception:
        return False

# ========================================================
# PRIORIDADE DE REDE — QoS NATIVO DO WINDOWS (ACTIVE STORE)
# ========================================================
QOS_POLICY_PREFIX = "AIKAOptimizer_"
AIKA_QOS_DSCP = 46

def _qos_policy_name(exe):
    """Nome único da política QoS para um executável (prefixo + nome sem extensão)."""
    return QOS_POLICY_PREFIX + os.path.splitext(exe)[0].upper()

def _qos_disponivel():
    """Verifica se os cmdlets NetQos estão disponíveis no sistema."""
    script = ("Get-Command New-NetQosPolicy, Get-NetQosPolicy, Remove-NetQosPolicy "
              "-ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count")
    saida = _executar_powershell_oculto(script, timeout=20)
    try:
        return int((saida or "").strip()) >= 3
    except Exception:
        return False

def _listar_politicas_qos_proprias():
    """Retorna a lista de nomes de políticas QoS do AIKA Optimizer (ActiveStore).

    Filtra OBRIGATORIAMENTE somente nomes com o prefixo QOS_POLICY_PREFIX,
    de forma CASE-INSENSITIVE (PowerShell `-like` já é case-insensitive e o
    filtro Python usa lower()) — nunca considera política de terceiros como
    própria.
    """
    script = ("Get-NetQosPolicy -PolicyStore ActiveStore -ErrorAction SilentlyContinue | "
              f"Where-Object {{ $_.Name -like '{QOS_POLICY_PREFIX}*' }} | "
              "Select-Object -ExpandProperty Name")
    saida = _executar_powershell_oculto(script, timeout=30)
    prefixo_lower = QOS_POLICY_PREFIX.lower()
    nomes = []
    if saida:
        for linha in saida.splitlines():
            linha = linha.strip()
            if linha and linha.lower().startswith(prefixo_lower):
                nomes.append(linha)
    return nomes

def obter_status_qos_aika():
    """Retorna o estado real das políticas QoS do AIKA Optimizer."""
    try:
        nomes = _listar_politicas_qos_proprias()
        ativas = len(nomes)
        return {
            "ok": True,
            "ativas": ativas,
            "politicas": nomes,
            "mensagem": f"{ativas} política(s) ativa(s)." if ativas else "Nenhuma política ativa.",
        }
    except Exception as e:
        return {"ok": False, "ativas": 0, "politicas": [], "mensagem": str(e)}

def aplicar_qos_aika():
    """Cria (idempotente) políticas QoS para os executáveis reais do AIKA."""
    try:
        if not is_admin():
            return {"ok": False, "requires_admin": True, "ativas": 0, "politicas": [],
                    "mensagem": "A prioridade de rede requer execução como administrador."}

        if not _qos_disponivel():
            return {"ok": False, "ativas": 0, "politicas": [], "mensagem": "NetQos indisponível neste Windows."}

        existentes = {n.lower() for n in _listar_politicas_qos_proprias()}
        aplicadas = []
        ultimo_erro = ""
        for exe in AIKA_GAME_EXES:
            nome_politica = _qos_policy_name(exe)
            if nome_politica.lower() in existentes:
                aplicadas.append(nome_politica)
                continue
            script = (
                f"New-NetQosPolicy -Name '{nome_politica}' "
                "-PolicyStore ActiveStore "
                f"-AppPathNameMatchCondition '{exe}' "
                f"-DSCPAction {AIKA_QOS_DSCP} "
                "-NetworkProfile All -ErrorAction SilentlyContinue"
            )
            _, stderr = _executar_powershell_oculto_detalhe(script, timeout=30)
            if nome_politica.lower() in {n.lower() for n in _listar_politicas_qos_proprias()}:
                aplicadas.append(nome_politica)
                log(f"[QOS] Política criada: {nome_politica}")
            else:
                log(f"[QOS] Falha ao criar política: {nome_politica}")
                if not ultimo_erro:
                    ultimo_erro = _resumir_erro_powershell(stderr)

        ativas = len(aplicadas)
        if ativas > 0:
            mensagem = f"{ativas} política(s) aplicada(s)."
        elif ultimo_erro:
            mensagem = f"Falha ao criar política: {ultimo_erro}"
        else:
            mensagem = "Nenhuma política pôde ser criada (verifique privilégios de administrador)."
        return {"ok": ativas > 0, "ativas": ativas, "politicas": aplicadas, "mensagem": mensagem}
    except Exception as e:
        log(f"[QOS] Erro ao aplicar: {e}")
        return {"ok": False, "ativas": 0, "politicas": [], "mensagem": str(e)}

def remover_qos_aika():
    """Remove SOMENTE políticas QoS do prefixo AIKAOptimizer_ (ActiveStore)."""
    try:
        nomes = _listar_politicas_qos_proprias()
        removidas = 0
        for nome in nomes:
            script = (f"Remove-NetQosPolicy -Name '{nome}' -PolicyStore ActiveStore "
                      "-Confirm:$false -ErrorAction SilentlyContinue")
            _executar_powershell_oculto(script, timeout=30)
            if nome.lower() not in {n.lower() for n in _listar_politicas_qos_proprias()}:
                removidas += 1
                log(f"[QOS] Política removida: {nome}")
        restantes = _listar_politicas_qos_proprias()
        return {
            "ok": len(restantes) == 0,
            "ativas": len(restantes),
            "politicas": restantes,
            "mensagem": f"{removidas} política(s) removida(s).",
        }
    except Exception as e:
        return {"ok": False, "ativas": 0, "politicas": [], "mensagem": str(e)}