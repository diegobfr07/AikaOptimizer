import os, winreg, psutil, winshell
from config import *
from seguranca import (fazer_backup_registro, criar_ponto_restauracao,
                       salvar_snapshot_sistema, filtro_adaptadores_ativos_ps,
                       garantir_ifeo_ownership, IFEO_CPU_PRIORITY_CLASS_VALUE,
                       IFEO_NOOP,
                       obter_planos_energia_disponiveis, obter_plano_energia_atual,
                       GUID_ALTO_DESEMPENHO)

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

# Resultados não-fatais da etapa de plano de energia (fallback seguro).
PLANO_SUCESSO = "success"   # plano Alto Desempenho ativado com sucesso
PLANO_NOOP = "noop"         # plano Alto Desempenho já ativo (idempotente)
PLANO_SKIP = "skip"         # plano indisponível ou consulta falhou (não-fatal)
PLANO_FALHA = "failed"      # tentou ativar e falhou (falha local, não-fatal)


def modo_desempenho_maximo():
    """Ativa o plano Alto Desempenho se disponível; NUNCA derruba a otimização.

    A ausência do plano (ou falha na consulta/ativação) é tratada como
    capacidade indisponível, não como erro fatal. Retorna PLANO_SUCESSO /
    PLANO_NOOP / PLANO_SKIP / PLANO_FALHA. Nunca lança exceção por
    indisponibilidade do plano e nunca cria planos novos.
    """
    planos = obter_planos_energia_disponiveis()
    if planos is None:
        log("[AVISO] Não foi possível consultar os planos de energia; ajuste de plano ignorado.")
        return PLANO_SKIP
    if GUID_ALTO_DESEMPENHO not in planos:
        log("[AVISO] Plano Alto Desempenho não está disponível neste Windows; ajuste ignorado.")
        return PLANO_SKIP
    atual = obter_plano_energia_atual()
    if atual and atual.lower() == GUID_ALTO_DESEMPENHO:
        return PLANO_NOOP  # já ativo — idempotente, sem alteração
    if not executar_comando_seguro(['powercfg', '/setactive', GUID_ALTO_DESEMPENHO]):
        log("[AVISO] Não foi possível alterar o plano de energia; demais otimizações continuarão.")
        return PLANO_FALHA
    return PLANO_SUCESSO

def otimizar_rede_estabilidade():
    if not executar_comando_seguro(['ipconfig', '/flushdns']): raise Exception("Falha ao limpar cache DNS")
    return True

def _prioridade_igual(valor, atributo):
    """True se ``valor`` representa a classe de prioridade ``atributo``."""
    if not hasattr(psutil, atributo):
        return False
    try:
        return int(valor) == int(getattr(psutil, atributo))
    except (TypeError, ValueError):
        return valor == getattr(psutil, atributo)


def prioridade_total():
    try:
        sucesso = False
        for exe in AIKA_GAME_EXES:
            chave = f"HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Image File Execution Options\\{exe}"
            status_ownership = garantir_ifeo_ownership(exe)
            if status_ownership == IFEO_NOOP:
                # Legado ambíguo JÁ aplicado: o estado persistente desejado
                # (CpuPriorityClass == valor do Optimizer) já está presente no
                # Registry. NÃO reescrever, NÃO criar baseline falsa, NÃO
                # bloquear a Otimização Global. O RESTORE do mesmo estado
                # permanece conservador (PARTIAL) — a folga é só no APPLY.
                log(f"[SEGURANÇA] Prioridade persistente de {exe} já aplicada "
                    f"(backup legado ambíguo preservado; IFEO não alterado).")
                sucesso = True
                continue
            if status_ownership is False:
                log(f"[SEGURANÇA] Prioridade não aplicada a {exe}: ownership IFEO não garantido.")
                continue
            if not fazer_backup_registro(chave, f"backup_prioridade_{exe}"):
                log(f"[SEGURANÇA] Prioridade não aplicada a {exe}: backup de Registro falhou.")
                continue
            cmd = ['reg', 'add', f"{chave}\\PerfOptions", '/v', 'CpuPriorityClass', '/t', 'REG_DWORD', '/d', str(IFEO_CPU_PRIORITY_CLASS_VALUE), '/f']
            if executar_comando_seguro(cmd): sucesso = True

        for proc in psutil.process_iter(['name', 'pid']):
            nome = (proc.info.get('name') or "").lower()
            if nome not in AIKA_GAME_EXES:
                continue
            pid = proc.info['pid']
            try:
                p = psutil.Process(pid)
                # Idempotência multi-instância (AUD prioridade): NUNCA rebaixar
                # um Aika ativo. Preserva ABOVE/HIGH e só eleva para
                # ABOVE_NORMAL quando a atual estiver abaixo desse piso.
                atual = None
                try:
                    atual = p.nice()
                except Exception:
                    atual = None
                acima_do_piso = (
                    _prioridade_igual(atual, "ABOVE_NORMAL_PRIORITY_CLASS")
                    or _prioridade_igual(atual, "HIGH_PRIORITY_CLASS")
                )
                if hasattr(psutil, "ABOVE_NORMAL_PRIORITY_CLASS"):
                    if atual is not None and not acima_do_piso:
                        p.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
                elif atual is not None and not _prioridade_igual(atual, "HIGH_PRIORITY_CLASS"):
                    cmd = ['powershell', '-Command', f"(Get-Process -Id {pid}).PriorityClass = 'AboveNormal'"]
                    executar_comando_seguro(cmd)
                if hasattr(psutil, "IOPRIO_HIGH"):
                    try:
                        p.ionice(psutil.IOPRIO_HIGH)
                    except Exception:
                        pass
                sucesso = True
            except Exception:
                # Falha pontual de um PID não impede os demais; nunca rebaixar.
                log(f"[SISTEMA] Prioridade não aplicada ao PID {pid} (preservado sem rebaixamento).")
        return sucesso
    except Exception: return False

def desativar_game_bar():
    """Desativa a Game Bar/GameDVR (captura e overlay) e configura o modo de
    comportamento de tela cheia do Windows (GameDVR_FSEBehaviorMode=2) no
    HKCU do usuário. NÃO aplica IFEO/FullscreenOptimizations por executável —
    o efeito real é: Game Bar/GameDVR off + preferência de tela cheia do
    Windows ajustada para não interferir no jogo.
    """
    try:
        if not fazer_backup_registro(r"HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR", "backup_gamedvr"):
            return False
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\GameDVR", 0, winreg.KEY_SET_VALUE) as key1:
            winreg.SetValueEx(key1, "AppCaptureEnabled", 0, winreg.REG_DWORD, 0)
            winreg.SetValueEx(key1, "GameDVR_Enabled", 0, winreg.REG_DWORD, 0)

        if not fazer_backup_registro(r"HKCU\System\GameConfigStore", "backup_gameconfigstore"):
            return False
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"System\GameConfigStore", 0, winreg.KEY_SET_VALUE) as key2:
            winreg.SetValueEx(key2, "GameDVR_Enabled", 0, winreg.REG_DWORD, 0)
            winreg.SetValueEx(key2, "GameDVR_FSEBehaviorMode", 0, winreg.REG_DWORD, 2)
            winreg.SetValueEx(key2, "GameDVR_HonorUserFSEBehaviorMode", 0, winreg.REG_DWORD, 0)
        return True
    except Exception: return False

def alterar_dns(escolha):
    """Altera o DNS somente nos adaptadores FÍSICOS ativos — o MESMO escopo
    usado pelo snapshot (obter_dns_atual) e pela restauração
    (restaurar_snapshot_sistema). VPN, adaptadores virtuais, Loopback e
    interfaces desconectadas nunca são tocadas. Se houver múltiplos
    adaptadores físicos ativos, aplica a todos (o snapshot cobre o mesmo
    conjunto; não há heurística de escolha de um único adaptador)."""
    if not salvar_snapshot_sistema():
        return False
    try:
        base_cmd = filtro_adaptadores_ativos_ps() + " | "
        if escolha == "Google": cmd = ['powershell', '-Command', base_cmd + "Set-DnsClientServerAddress -ServerAddresses ('8.8.8.8','8.8.4.4')"]
        elif escolha == "Cloudflare": cmd = ['powershell', '-Command', base_cmd + "Set-DnsClientServerAddress -ServerAddresses ('1.1.1.1','1.0.0.1')"]
        else: cmd = ['powershell', '-Command', base_cmd + "Set-DnsClientServerAddress -ResetServerAddresses"]
        return executar_comando_seguro(cmd)
    except Exception: return False

def _normalizar_guid_interface(valor):
    """Normaliza um GUID de interface (remove chaves, uppercase)."""
    return str(valor or "").strip().strip('{}').upper()

def _obter_guids_adaptadores_ativos():
    """GUIDs de interface (Tcpip\\Parameters\\Interfaces) dos adaptadores
    físicos ativos — mesmo filtro usado pelo DNS. Conjunto vazio significa
    que não foi possível identificar (ex.: PowerShell indisponível/offline)."""
    script = filtro_adaptadores_ativos_ps() + " | Select-Object -ExpandProperty InterfaceGuid"
    saida = _executar_powershell_oculto(script, timeout=20)
    guids = set()
    if saida:
        for linha in saida.splitlines():
            linha = linha.strip()
            if linha:
                guids.add(_normalizar_guid_interface(linha))
    return guids

def otimizar_tcp_nodelay():
    """Aplica TcpAckFrequency=1/TCPNoDelay=1 SOMENTE nas subchaves de interface
    dos adaptadores físicos ativos (mesmo filtro do DNS). Interfaces virtuais,
    VPN, loopback e desconectadas NÃO são alteradas. Se não for possível
    identificar o adaptador ativo, nada é alterado (nada de aplicar em todas).
    O backup de Registro da árvore de interfaces é preservado (restore .reg).
    """
    try:
        interfaces_path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
        guids_ativos = _obter_guids_adaptadores_ativos()
        if not guids_ativos:
            log("[REDE] Adaptador de rede ativo não identificado — TCP NoDelay não aplicado (nenhuma interface alterada).")
            return False
        if not fazer_backup_registro(f"HKLM\\{interfaces_path}", "backup_tcp_nodelay"):
            raise RuntimeError("Backup de Registro do TCP NoDelay falhou")
        interfaces_alteradas = 0
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, interfaces_path, 0, winreg.KEY_READ) as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                subkey_name = winreg.EnumKey(key, i)
                if _normalizar_guid_interface(subkey_name) not in guids_ativos:
                    continue  # fora do escopo: virtual/VPN/desconectada/não ativa
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
        ok = len(restantes) == 0
        mensagem = (f"{removidas} política(s) removida(s)." if ok
                    else f"{removidas} política(s) removida(s); {len(restantes)} restante(s) no ActiveStore.")
        return {
            "ok": ok,
            "ativas": len(restantes),
            "politicas": restantes,
            "mensagem": mensagem,
        }
    except Exception as e:
        return {"ok": False, "ativas": 0, "politicas": [], "mensagem": str(e)}