import os, shutil, json, time, re, ipaddress, stat, subprocess, tempfile, hashlib, winreg
from config import *

def criar_substituto_old(destino):
    """Move destino para .old e retorna bool; nunca engole falha."""
    backup_old = destino + ".old"
    try:
        if os.path.exists(backup_old):
            os.remove(backup_old)
        os.replace(destino, backup_old)
        return True
    except Exception as e:
        log(f"[SEGURANÇA] Falha ao criar .old para {destino}: {e}")
        return False


def _sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def fazer_backup_rapido(caminho_original, caminho_backup):
    """Cria backup atômico e validado; backup existente não é sobrescrito."""
    temporario = None
    try:
        if not os.path.isfile(caminho_original):
            return False
        if os.path.isfile(caminho_backup):
            return os.path.getsize(caminho_backup) > 0
        os.makedirs(os.path.dirname(caminho_backup), exist_ok=True)
        fd, temporario = tempfile.mkstemp(prefix=".aika_backup_", suffix=".tmp", dir=os.path.dirname(caminho_backup))
        os.close(fd)
        shutil.copy2(caminho_original, temporario)
        if os.path.getsize(temporario) != os.path.getsize(caminho_original):
            raise OSError("tamanho do backup diverge do original")
        if _sha256_arquivo(temporario) != _sha256_arquivo(caminho_original):
            raise OSError("hash do backup diverge do original")
        os.replace(temporario, caminho_backup)
        temporario = None
        return True
    except Exception as e:
        log(f"[SEGURANÇA] Falha ao criar backup de {caminho_original}: {e}")
        return False
    finally:
        if temporario and os.path.exists(temporario):
            try: os.remove(temporario)
            except OSError: pass


EFEITOS_POLUIDOS_ARQUIVOS = frozenset({
    "weaponeff3.bin", "skilleff.bin", "skilleff2.bin", "skilleff3.bin",
    "particle.bin", "particle2.bin", "glow.bin", "gloweffect.bin",
    "mageff.bin", "maguiceff.bin",
})


def _restaurar_backup_atomico(caminho_backup, destino, hash_esperado=None):
    temporario = None
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    try:
        fd, temporario = tempfile.mkstemp(
            prefix=f".{os.path.basename(destino)}.",
            suffix=".restore.tmp", dir=os.path.dirname(destino),
        )
        os.close(fd)
        shutil.copy2(caminho_backup, temporario)
        hash_backup = hash_esperado or _sha256_arquivo(caminho_backup)
        if _sha256_arquivo(temporario) != hash_backup:
            raise OSError("hash temporário de restore divergente")
        if os.path.exists(destino):
            try: os.chmod(destino, stat.S_IWRITE)
            except OSError: pass
        os.replace(temporario, destino)
        temporario = None
        if _sha256_arquivo(destino) != hash_backup:
            raise OSError("hash final de restore divergente")
    finally:
        if temporario and os.path.exists(temporario):
            try: os.remove(temporario)
            except OSError: pass


def remover_arquivos_com_backup(pasta_jogo, nomes_arquivos,
                                 persistir_operacao=None):
    pasta_jogo = normalizar_pasta_jogo(pasta_jogo)
    nomes = {str(nome).lower() for nome in nomes_arquivos or []}
    with lock_otimizacao:
        if not pasta_jogo or not os.path.isdir(pasta_jogo):
            return {"status": "error", "files": [], "error": "Pasta do cliente inválida."}
        pasta_busca = os.path.join(pasta_jogo, "Data", "Effect")
        if not os.path.isdir(pasta_busca):
            pasta_busca = pasta_jogo

        operacoes = []
        for root, _dirs, files in os.walk(pasta_busca):
            for nome in files:
                if nome.lower() not in nomes:
                    continue
                caminho = os.path.realpath(os.path.join(root, nome))
                if not caminho_seguro(pasta_jogo, caminho):
                    return {"status": "error", "files": [], "error": "Arquivo fora do cliente."}
                try:
                    estado = os.stat(caminho, follow_symlinks=False)
                    if not stat.S_ISREG(estado.st_mode) or estado.st_size <= 0:
                        raise OSError("alvo não é arquivo regular válido")
                    relativo = os.path.relpath(caminho, pasta_jogo).replace("\\", "/")
                    backup = os.path.join(
                        obter_pasta_backup_cliente(pasta_jogo),
                        relativo.replace("/", os.sep),
                    )
                    if not os.path.exists(backup):
                        if not fazer_backup_rapido(caminho, backup):
                            raise OSError("falha ao criar backup")
                    if (
                        not os.path.isfile(backup)
                        or os.path.getsize(backup) <= 0
                        or os.path.getsize(backup) != estado.st_size
                    ):
                        raise OSError("backup ausente, vazio ou com tamanho divergente")
                    hash_original = _sha256_arquivo(caminho)
                    if _sha256_arquivo(backup) != hash_original:
                        raise OSError("SHA-256 do backup difere do arquivo atual")
                    operacoes.append({
                        "caminho": caminho, "backup": backup,
                        "target_relpath": relativo,
                        "target_name": os.path.basename(caminho),
                        "hash": hash_original, "size": estado.st_size,
                        "mode": estado.st_mode,
                    })
                except Exception as e:
                    return {"status": "error", "files": [], "error": str(e)}

        if not operacoes:
            return {"status": "already_removed", "files": [], "error": None}

        removidos = []
        try:
            for item in operacoes:
                if (
                    not os.path.isfile(item["caminho"])
                    or os.path.getsize(item["caminho"]) != item["size"]
                    or _sha256_arquivo(item["caminho"]) != item["hash"]
                    or _sha256_arquivo(item["backup"]) != item["hash"]
                ):
                    raise OSError(f"arquivo ou backup mudou: {item['target_name']}")
                try: os.chmod(item["caminho"], stat.S_IWRITE)
                except OSError: pass
                os.remove(item["caminho"])
                if os.path.exists(item["caminho"]):
                    raise OSError(f"arquivo permaneceu no cliente: {item['target_name']}")
                removidos.append(item)
            if persistir_operacao and not persistir_operacao(operacoes):
                raise OSError("não foi possível persistir o histórico da operação")
            return {"status": "removed", "files": operacoes, "error": None}
        except Exception as e:
            rollback_erros = []
            for item in reversed(removidos):
                try:
                    _restaurar_backup_atomico(
                        item["backup"], item["caminho"], item["hash"]
                    )
                    try: os.chmod(item["caminho"], item["mode"])
                    except OSError: pass
                except Exception as erro_rollback:
                    rollback_erros.append(
                        f"{item['target_name']}: {erro_rollback}"
                    )
            detalhe = str(e)
            if rollback_erros:
                detalhe += f"; rollback com falhas: {rollback_erros}"
            else:
                detalhe += "; rollback OK"
            return {"status": "error", "files": [], "error": detalhe}


def restaurar_arquivo_removido(target_relpath, pasta_jogo,
                                persistir_historico=None):
    pasta_jogo = normalizar_pasta_jogo(pasta_jogo)
    with lock_otimizacao:
        if not pasta_jogo or not target_relpath:
            return False, "Cliente ou caminho relativo inválido."
        destino = os.path.abspath(os.path.join(
            pasta_jogo, str(target_relpath).replace("/", os.sep)
        ))
        if not caminho_seguro(pasta_jogo, destino):
            return False, "Destino fora da pasta do jogo (bloqueado)."
        backup = os.path.join(
            obter_pasta_backup_cliente(pasta_jogo, criar=False),
            str(target_relpath).replace("/", os.sep),
        )
        if not os.path.isfile(backup) or os.path.getsize(backup) <= 0:
            return False, "Backup original não encontrado ou inválido."

        destino_existia = os.path.isfile(destino)
        anterior = None
        try:
            if destino_existia:
                with open(destino, "rb") as arquivo:
                    anterior = arquivo.read()
            hash_backup = _sha256_arquivo(backup)
            _restaurar_backup_atomico(backup, destino, hash_backup)
            if persistir_historico and not persistir_historico():
                raise OSError("não foi possível atualizar o histórico")
            return True, f"{os.path.basename(destino)} restaurado."
        except Exception as e:
            try:
                if destino_existia:
                    fd, temporario = tempfile.mkstemp(
                        prefix=f".{os.path.basename(destino)}.",
                        suffix=".rollback.tmp", dir=os.path.dirname(destino),
                    )
                    with os.fdopen(fd, "wb") as arquivo:
                        arquivo.write(anterior)
                        arquivo.flush(); os.fsync(arquivo.fileno())
                    os.replace(temporario, destino)
                elif os.path.exists(destino):
                    os.remove(destino)
            except Exception as rollback_e:
                return False, f"{e}; rollback também falhou: {rollback_e}"
            return False, f"Não foi possível restaurar {os.path.basename(destino)}: {e}"


# ========================================================
# IFEO / PerfOptions — OWNERSHIP (P1 #3)
# ========================================================
IFEO_BASE_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options"
IFEO_VALORES_OTIMIZADOR = ("CpuPriorityClass",)
IFEO_CPU_PRIORITY_CLASS_VALUE = 6
IFEO_CPU_PRIORITY_CLASS_TYPE = winreg.REG_DWORD
IFEO_FORMATO = 1
ARQUIVO_IFEO = os.path.join(PASTA_BACKUP_REG, "ifeo_state.json")
ARQUIVO_MIGRACOES_IFEO = os.path.join(PASTA_BACKUP_REG, "legacy_ifeo_migrations.json")

# Resultado tri-estado de garantir_ifeo_ownership (hotfix runtime V4.1):
#   True      → ownership garantido; mutação de Registry liberada;
#   IFEO_NOOP → legado ambíguo JÁ aplicado (CpuPriorityClass == valor do
#               Optimizer): NO-OP seguro — NÃO muta o Registry, NÃO cria
#               baseline falsa, NÃO consome o backup legado e NÃO bloqueia
#               a Otimização Global (o RESTORE do mesmo estado continua
#               conservador/PARTIAL, pois esta folga é só no APPLY);
#   False     → falha real (exe inválido, metadata IFEO inválida, captura ou
#               gravação falhou): mutação NÃO liberada e a etapa é reportada.
IFEO_NOOP = "noop"


def _normalizar_nome_ifeo(exe):
    """Valida/normaliza nome de executável IFEO (basename .exe, case-insensitive)."""
    if not isinstance(exe, str):
        return None
    nome = exe.strip().lower()
    if "/" in nome or "\\" in nome or ".." in nome:
        return None
    if not nome.endswith(".exe") or nome == ".exe":
        return None
    if not re.match(r"^[a-z0-9._\- ]+$", nome):
        return None
    return nome


def _executaveis_ifeo_permitidos():
    """Executáveis AIKA reconhecidos que podem receber IFEO (normalizados)."""
    nomes = set()
    for exe in AIKA_GAME_EXES:
        n = _normalizar_nome_ifeo(exe)
        if n:
            nomes.add(n)
    return nomes


def _ifeo_caminho_perfoptions(exe):
    exe = _normalizar_nome_ifeo(exe)
    if exe is None:
        return None
    return f"{IFEO_BASE_KEY}\\{exe}\\PerfOptions"


def _ifeo_caminho_chave(exe):
    exe = _normalizar_nome_ifeo(exe)
    if exe is None:
        return None
    return f"{IFEO_BASE_KEY}\\{exe}"


def _ler_perfoptions_ifeo(exe):
    """Lê valores de IFEO\\{exe}\\PerfOptions; None se PerfOptions não existir."""
    caminho = _ifeo_caminho_perfoptions(exe)
    if caminho is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, caminho, 0, winreg.KEY_READ) as key:
            valores = {}
            idx = 0
            while True:
                try:
                    nome, dado, tipo = winreg.EnumValue(key, idx)
                except OSError:
                    break
                valores[nome] = {"type": int(tipo), "value": dado}
                idx += 1
            return valores
    except (FileNotFoundError, OSError):
        return None


def _ifeo_key_existe(exe):
    caminho = _ifeo_caminho_chave(exe)
    if caminho is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, caminho, 0, winreg.KEY_READ):
            return True
    except (FileNotFoundError, OSError):
        return False


def _carregar_ifeo_metadata():
    if not os.path.isfile(ARQUIVO_IFEO):
        return None, None
    try:
        with open(ARQUIVO_IFEO, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except Exception as e:
        return None, f"ifeo_state.json corrompido/inválido: {e}"
    if not isinstance(dados, dict):
        return None, "ifeo_state.json não é um objeto JSON."
    if dados.get("format_version") != IFEO_FORMATO:
        return None, "formato de ifeo_state.json desconhecido."
    if not isinstance(dados.get("executables"), dict):
        return None, "executables inválido no ifeo_state.json."
    return dados, None


def _escrever_ifeo_metadata_atomico(dados):
    os.makedirs(PASTA_BACKUP_REG, exist_ok=True)
    tmp = ARQUIVO_IFEO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ARQUIVO_IFEO)
    return True


def _capturar_ifeo_ownership(exe):
    exe = _normalizar_nome_ifeo(exe)
    if exe is None:
        return None
    perfopts = _ler_perfoptions_ifeo(exe)
    values_before = {}
    if perfopts:
        for nome, info in perfopts.items():
            values_before[nome] = {"type": info["type"], "value": info["value"]}
    return {
        "ifeo_key_existed": _ifeo_key_existe(exe),
        "perfoptions_existed": perfopts is not None,
        "values_before": values_before,
        "optimizer_values": {
            "CpuPriorityClass": {
                "type": IFEO_CPU_PRIORITY_CLASS_TYPE,
                "value": IFEO_CPU_PRIORITY_CLASS_VALUE,
            },
        },
    }


def garantir_ifeo_ownership(exe):
    """Captura/persiste ownership IFEO antes da primeira mutação de um ciclo.

    Nunca sobrescreve o estado original já capturado (idempotente por exe).
    Retorna um tri-estado (não um simples bool):

    - ``True``      → ownership garantido; é seguro prosseguir com a
                      alteração de Registry;
    - ``IFEO_NOOP`` → legado ambíguo já aplicado (no-op seguro): NÃO mutar o
                      Registry, mas NÃO é falha (não bloqueia a Otimização
                      Global);
    - ``False``     → falha real: NÃO mutar e reportar a etapa.

    O RESTORE não é afetado: o backup legado ambíguo continua PARTIAL e não
    restaurável automaticamente.
    """
    exe = _normalizar_nome_ifeo(exe)
    if exe is None:
        return False
    status_legado = _tentar_adotar_ifeo_legado(exe)
    if status_legado == LEGADO_AMBIGUO:
        # Backup legado ambíguo: não criar baseline falsa. Se o valor atual já
        # for o do Optimizer, não há mutação real necessária → tratamos como
        # "já aplicado" sem reescrever o Registry.
        otim = {"type": IFEO_CPU_PRIORITY_CLASS_TYPE,
                "value": IFEO_CPU_PRIORITY_CLASS_VALUE}
        atual = _ler_cpu_priority_class_ifeo(exe)
        if atual is not None and _valor_ifeo_igual(atual, otim):
            log(f"[SEGURANÇA] IFEO/{exe}: prioridade persistente já está "
                f"aplicada, mas o backup legado não permite determinar com "
                f"segurança o estado original; o Optimizer continuará sem "
                f"alterar o IFEO (no-op seguro).")
            return IFEO_NOOP
        # current != 6: prossegue capturando o estado ATUAL como nova baseline
        # de um novo ciclo V4.1 (não do backup ambíguo).
    dados, erro = _carregar_ifeo_metadata()
    if erro:
        log(f"[SEGURANÇA] Metadata IFEO inválido; prioridade não aplicada: {erro}")
        return False
    if dados is None:
        dados = {"format_version": IFEO_FORMATO, "executables": {}}
    if exe in dados.get("executables", {}):
        return True
    entrada = _capturar_ifeo_ownership(exe)
    if entrada is None:
        return False
    dados["executables"][exe] = entrada
    try:
        _escrever_ifeo_metadata_atomico(dados)
    except Exception as e:
        log(f"[SEGURANÇA] Falha ao gravar metadata IFEO: {e}")
        return False
    dados2, erro2 = _carregar_ifeo_metadata()
    if erro2 or not dados2 or exe not in dados2.get("executables", {}):
        return False
    return True


# ========================================================
# PONTE LEGADO V4.0 → OWNERSHIP V4.1 (backup_prioridade_*.reg)
# ========================================================
# O arquivo .reg legado é tratado SOMENTE como fonte de evidência do estado
# anterior de CpuPriorityClass do executável AIKA correspondente. Nunca é
# importado (reg import), nunca executa conteúdo, nunca obedece caminhos
# Registry arbitrários e nunca restaura valores que o Optimizer não controlou.
LEGADO_FONTE_OWNERSHIP = "legacy_reg"
LEGADO_ADOTADO = "adotado"
LEGADO_JA_COBERTO = "ja_coberto"
LEGADO_SEM_BACKUP = "sem_backup"
LEGADO_CONFLITO = "conflito"
LEGADO_INVALIDO = "invalido"
LEGADO_AMBIGUO = "ambiguo"


def _decodificar_reg_legado(raw):
    """Decodifica .reg legado (reg export) detectando BOM; None se ilegível."""
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        try:
            texto = raw.decode("utf-16")
        except UnicodeDecodeError:
            return None
    elif raw.startswith(b"\xef\xbb\xbf"):
        try:
            texto = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return None
    else:
        try:
            texto = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                texto = raw.decode("cp1252")
            except UnicodeDecodeError:
                return None
    return texto.lstrip("\ufeff")


def _parsear_backup_prioridade_legado(caminho, exe_esperado):
    """Extrai SOMENTE PerfOptions/CpuPriorityClass do backup_prioridade_<exe>.reg.

    Parser restrito ao formato produzido por ``reg export`` para esse caso.
    Retorna (resultado, erro). resultado contém ``perfoptions_existed`` e
    ``values_before`` no MESMO formato do ownership moderno. Nunca interpreta
    caminhos Registry arbitrários — a chave é reconstruída internamente a
    partir da allowlist + BASE_IFEO.
    """
    exe = _normalizar_nome_ifeo(exe_esperado)
    if exe is None:
        return None, "executável inválido"
    try:
        with open(caminho, "rb") as f:
            raw = f.read()
    except OSError as e:
        return None, f"não foi possível ler o .reg: {e}"
    if not raw.strip():
        return None, "arquivo .reg vazio"
    texto = _decodificar_reg_legado(raw)
    if texto is None:
        return None, "encoding do .reg ilegível"

    base = "HKEY_LOCAL_MACHINE\\" + IFEO_BASE_KEY
    esperado_exe = (base + "\\" + exe).lower()
    esperado_perf = (esperado_exe + "\\PerfOptions").lower()

    secoes = []
    atual = None
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if linha.startswith("["):
            if not linha.endswith("]"):
                return None, "cabeçalho de seção malformado"
            nome = linha[1:-1].strip().lower()
            atual = [nome, []]
            secoes.append(atual)
            continue
        if atual is None:
            if linha.lower().startswith("windows registry editor version"):
                continue
            return None, "estrutura de .reg não reconhecida"
        atual[1].append(linha)

    nomes = [s[0] for s in secoes]
    if esperado_exe not in nomes:
        return None, "chave do executável esperado não encontrada no .reg"
    for nome in nomes:
        if nome not in (esperado_exe, esperado_perf):
            return None, "seção de chave/executável inesperado no .reg"

    perfoptions_existed = esperado_perf in nomes
    values_before = {}
    if perfoptions_existed:
        linhas_perf = next(s[1] for s in secoes if s[0] == esperado_perf)
        for ln in linhas_perf:
            m = re.match(r'^"([^"]+)"\s*=\s*(.*)$', ln)
            if not m:
                continue
            nome = m.group(1)
            if nome != "CpuPriorityClass":
                continue
            resto = m.group(2).strip()
            if resto == "-":
                continue
            if resto.lower().startswith("dword:"):
                hexstr = resto[6:].strip()
                try:
                    valor = int(hexstr, 16)
                except ValueError:
                    return None, "CpuPriorityClass dword malformado no .reg"
                if valor < 0 or valor > 0xFFFFFFFF:
                    return None, "CpuPriorityClass dword fora do intervalo"
                values_before["CpuPriorityClass"] = {
                    "type": IFEO_CPU_PRIORITY_CLASS_TYPE,
                    "value": valor,
                }
            else:
                return None, "CpuPriorityClass com tipo inesperado no .reg"

    return {
        "perfoptions_existed": perfoptions_existed,
        "values_before": values_before,
    }, None


def _carregar_migracoes_ifeo():
    if not os.path.isfile(ARQUIVO_MIGRACOES_IFEO):
        return {}
    try:
        with open(ARQUIVO_MIGRACOES_IFEO, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except Exception:
        return {}
    if not isinstance(dados, dict):
        return {}
    return dados


def _gravar_migracoes_ifeo_atomico(dados):
    os.makedirs(PASTA_BACKUP_REG, exist_ok=True)
    tmp = ARQUIVO_MIGRACOES_IFEO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ARQUIVO_MIGRACOES_IFEO)
    return True


def _ler_cpu_priority_class_ifeo(exe):
    perfopts = _ler_perfoptions_ifeo(exe)
    if perfopts is None:
        return None
    return perfopts.get("CpuPriorityClass")


def _tentar_adotar_ifeo_legado(exe):
    """Adota (com segurança) um backup_prioridade_<exe>.reg V4.0 para ownership.

    Só adota quando: não há ownership moderno para o exe; o .reg é válido e
    restrito ao exe esperado; e o estado ATUAL de CpuPriorityClass ainda é
    exatamente IFEO_CPU_PRIORITY_CLASS_VALUE (evidência de que a alteração
    legado continua presente). Persiste o ownership moderno atomicamente e só
    então marca o artefato como consumido por SHA-256 — antes de qualquer
    restauração no Registry.
    """
    exe = _normalizar_nome_ifeo(exe)
    if exe is None:
        return LEGADO_INVALIDO
    dados, erro = _carregar_ifeo_metadata()
    if erro:
        log(f"[SEGURANÇA] Metadata IFEO inválido; adoção legado não executada: {erro}")
        return LEGADO_INVALIDO
    if dados is not None and exe in dados.get("executables", {}):
        return LEGADO_JA_COBERTO  # ownership moderno já cobre (prioridade sobre legado)
    if exe not in _executaveis_ifeo_permitidos():
        return LEGADO_INVALIDO

    nome_backup = f"backup_prioridade_{exe}.reg"
    caminho = os.path.join(PASTA_BACKUP_REG, nome_backup)
    if not os.path.isfile(caminho) or os.path.getsize(caminho) == 0:
        return LEGADO_SEM_BACKUP  # sem artefato legado para adotar

    sha256 = _sha256_arquivo(caminho)
    migracoes = _carregar_migracoes_ifeo()
    registro = migracoes.get(nome_backup)
    if (isinstance(registro, dict) and registro.get("consumed")
            and registro.get("sha256") == sha256):
        return LEGADO_JA_COBERTO  # artefato já consumido (mesmo SHA-256)

    parseado, erro_parse = _parsear_backup_prioridade_legado(caminho, exe)
    if erro_parse:
        log(f"[SEGURANÇA] Backup legado IFEO inválido ({exe}): {erro_parse}")
        return LEGADO_INVALIDO

    # Evidência ambígua: backup legado com CpuPriorityClass == valor do Optimizer
    # não prova o estado original (pode ter sido recriado após uma aplicação
    # anterior). Nunca promover para baseline moderna confiável.
    before_cpu = parseado["values_before"].get("CpuPriorityClass")
    if before_cpu is not None and before_cpu.get("value") == IFEO_CPU_PRIORITY_CLASS_VALUE:
        log(f"[SEGURANÇA] Backup legado IFEO ambíguo ({exe}): CpuPriorityClass "
            f"já era o valor do Optimizer ({IFEO_CPU_PRIORITY_CLASS_VALUE}); "
            f"não é possível determinar com segurança o estado original.")
        return LEGADO_AMBIGUO

    otim = {"type": IFEO_CPU_PRIORITY_CLASS_TYPE,
            "value": IFEO_CPU_PRIORITY_CLASS_VALUE}
    atual = _ler_cpu_priority_class_ifeo(exe)
    if atual is None or not _valor_ifeo_igual(atual, otim):
        log(f"[SEGURANÇA] CpuPriorityClass atual ({exe}) não corresponde ao "
            f"valor legado; adoção não executada (estado externo preservado).")
        return LEGADO_CONFLITO

    entrada = {
        "ifeo_key_existed": True,
        "perfoptions_existed": parseado["perfoptions_existed"],
        "values_before": parseado["values_before"],
        "optimizer_values": {"CpuPriorityClass": otim},
        "source": LEGADO_FONTE_OWNERSHIP,
        "legacy_backup": {"filename": nome_backup, "sha256": sha256},
    }
    if dados is None:
        dados = {"format_version": IFEO_FORMATO, "executables": {}}
    dados["executables"][exe] = entrada
    try:
        _escrever_ifeo_metadata_atomico(dados)
    except Exception as e:
        log(f"[SEGURANÇA] Falha ao gravar ownership legado ({exe}): {e}")
        return LEGADO_INVALIDO
    dados2, erro2 = _carregar_ifeo_metadata()
    if erro2 or not dados2 or exe not in dados2.get("executables", {}):
        return LEGADO_INVALIDO

    migracoes[nome_backup] = {
        "sha256": sha256,
        "consumed": True,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    try:
        _gravar_migracoes_ifeo_atomico(migracoes)
    except Exception as e:
        log(f"[SEGURANÇA] Falha ao marcar backup legado consumido ({exe}): {e}")
    return LEGADO_ADOTADO


def _adotar_legados_pendentes():
    """Varre a allowlist e adota backups legados pendentes (por exe, isolado).

    Retorna RESTAURACAO_PARCIAL quando um backup legado VÁLIDO aponta para um
    estado atual que já não corresponde ao valor do Optimizer (conflito externo)
    ou quando o backup legado é ambíguo (CpuPriorityClass antes == valor do
    Optimizer). Artefatos ausentes/inválidos são apenas registrados — nunca
    bloqueiam a restauração segura dos demais executáveis.
    """
    resultado = RESTAURACAO_SUCESSO
    for exe in sorted(_executaveis_ifeo_permitidos()):
        try:
            status = _tentar_adotar_ifeo_legado(exe)
            if status in (LEGADO_CONFLITO, LEGADO_AMBIGUO):
                resultado = RESTAURACAO_PARCIAL
        except Exception as e:
            log(f"[SEGURANÇA] Erro ao adotar legado IFEO ({exe}): {e}")
    return resultado


def fazer_backup_registro(chave_completa, nome_arquivo):
    """Exporta backup de Registro e retorna True somente se o arquivo existir e não estiver vazio."""
    try:
        os.makedirs(PASTA_BACKUP_REG, exist_ok=True)
        destino = os.path.join(PASTA_BACKUP_REG, f"{nome_arquivo}.reg")
        if os.path.isfile(destino) and os.path.getsize(destino) > 0:
            return True
        if not executar_comando_seguro(['reg', 'export', chave_completa, destino, '/y']):
            log(f"[SEGURANÇA] Falha ao exportar backup de Registro ({nome_arquivo}).")
            return False
        ok = os.path.isfile(destino) and os.path.getsize(destino) > 0
        if not ok:
            log(f"[SEGURANÇA] Backup de Registro vazio/ausente ({nome_arquivo}).")
        return ok
    except Exception as e:
        log(f"[SEGURANÇA] Falha ao criar backup de Registro ({nome_arquivo}): {e}")
        return False


class TransacaoSistema:
    def __init__(self):
        self.passos_executados = []

    def executar(self, func, *args, rollback=None, rollback_args=None):
        try:
            # Registra o rollback ANTES da mutação: se a própria etapa falhar,
            # o estado imediatamente anterior ainda pode ser restaurado.
            if rollback:
                r_args = rollback_args if rollback_args else ()
                self.passos_executados.append((rollback, r_args))
            resultado = func(*args)
            if resultado is False:
                raise RuntimeError(f"{getattr(func, '__name__', func)} retornou False")
            return resultado
        except Exception as e:
            log(f"[FALHA CRÍTICA] Transação abortada na etapa: {func.__name__}")
            self.rollback_total()
            raise e

    def rollback_total(self):
        log("[SEGURANÇA] Iniciando Rollback automático...")
        for acao, r_args in reversed(self.passos_executados):
            try: acao(*r_args)
            except Exception as e:
                log(f"[SEGURANÇA] Falha durante ação de rollback ({getattr(acao, '__name__', acao)}): {e}")

# Timeout de consultas externas que podem ficar penduradas: powercfg é uma
# consulta local rápida — se exceder isso, tratamos como indisponível
# (fallback seguro) em vez de travar a tarefa indefinidamente.
POWERCFG_TIMEOUT = 15
PS_QUERY_TIMEOUT = 20


def obter_plano_energia_atual():
    try:
        # CORREÇÃO: Flag de invisibilidade adicionada aqui!
        creation_flags = 0x08000000 if os.name == 'nt' else 0
        res = subprocess.check_output(['powercfg', '/getactivescheme'], text=True, stderr=subprocess.DEVNULL, creationflags=creation_flags, timeout=POWERCFG_TIMEOUT)
        match = re.search(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', res)
        return match.group(0) if match else None
    except Exception: return None


GUID_ALTO_DESEMPENHO = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"


def _parsear_guids_powercfg(saida):
    """Extrai GUIDs de planos de energia de uma saída powercfg /list.

    Independe do nome localizado (PT-BR, EN, etc.): apenas os GUIDs importam.
    Normaliza para minúsculas para comparação estável.
    """
    return {g.lower() for g in re.findall(
        r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',
        saida or "",
    )}


def obter_planos_energia_disponiveis():
    """Retorna um set de GUIDs de planos de energia realmente disponíveis.

    Consulta ``powercfg /list``. Retorna None se a consulta falhar (acesso
    negado / powercfg indisponível / erro inesperado).
    """
    try:
        creation_flags = 0x08000000 if os.name == 'nt' else 0
        res = subprocess.check_output(
            ['powercfg', '/list'], text=True, stderr=subprocess.DEVNULL,
            creationflags=creation_flags, timeout=POWERCFG_TIMEOUT,
        )
        return _parsear_guids_powercfg(res)
    except Exception:
        return None


# ------------------------------------------------------------
# ESCOPO DE ADAPTADORES DE REDE (compartilhado com sistema.py)
# ------------------------------------------------------------
# Alterações de DNS (ação do usuário, snapshot e restore) só podem tocar
# adaptadores FÍSICOS ativos. VPN/adaptadores virtuais/desconectados nunca
# são alterados — e o restore do snapshot usa EXATAMENTE o mesmo filtro da
# alteração, garantindo que a restauração reverte somente o que foi mudado.
# Nota de design: se houver múltiplos adaptadores físicos ativos, o DNS é
# aplicado a todos eles — escolher um único adaptador exigiria heurística
# arriscada; o snapshot cobre exatamente o mesmo conjunto de adaptadores.
_PADRAO_ADAPTADORES_IGNORADOS = (
    "Virtual|VMware|Hyper-V|TAP|Wintun|WireGuard|OpenVPN|Tailscale|"
    "ZeroTier|Hamachi|Loopback|vEthernet|Wi-Fi Direct|Bluetooth"
)

def filtro_adaptadores_ativos_ps():
    """Pipeline PowerShell que seleciona apenas adaptadores físicos conectados.

    Retorno: "Get-NetAdapter | Where-Object { ... }" — pode ser concatenado
    com " | Set-DnsClientServerAddress ...", " | Get-DnsClientServerAddress ..."
    etc. Usado por alterar_dns (sistema.py), obter_dns_atual e
    restaurar_snapshot_sistema para garantir escopo idêntico nos três lados.
    """
    return ("Get-NetAdapter | Where-Object { $_.Status -eq 'Up' "
            "-and $_.InterfaceDescription -notmatch '" + _PADRAO_ADAPTADORES_IGNORADOS + "' }")

FORMATO_SNAPSHOT = 2
_INTERFACES_REG_PATH = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"

_GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

RESTAURACAO_SUCESSO = "success"
RESTAURACAO_PARCIAL = "partial"
RESTAURACAO_FALHA = "failure"


def _normalizar_interface_guid(guid):
    """Normaliza InterfaceGuid para comparação robusta e inequívoca.

    Aceita string com/sem chaves ``{ }``, maiúsculas/minúsculas, espaços e a
    representação textual de um objeto GUID. Retorna o GUID canônico em
    minúsculas (sem chaves) ou ``None`` se ausente/malformado/não-string.
    """
    if guid is None:
        return None
    try:
        s = str(guid)
    except Exception:
        return None
    s = s.strip().strip("{}").strip()
    s = s.lower()
    if not _GUID_RE.match(s):
        return None
    return s


def _combinar_resultados(*resultados):
    """Combina resultados de restauração (success/partial/failure).

    Regra: sucesso total só quando TODOS forem sucesso; falha total só quando
    TODOS forem falha; qualquer mistura é parcial.
    """
    resultados = list(resultados)
    if not resultados:
        return RESTAURACAO_SUCESSO
    if all(r == RESTAURACAO_SUCESSO for r in resultados):
        return RESTAURACAO_SUCESSO
    if all(r == RESTAURACAO_FALHA for r in resultados):
        return RESTAURACAO_FALHA
    return RESTAURACAO_PARCIAL


def _validar_ipv4(valor):
    """Retorna o IPv4 normalizado (str) ou None se não for IPv4 válido."""
    try:
        ip = ipaddress.ip_address(str(valor))
        return str(ip) if ip.version == 4 else None
    except (ValueError, TypeError):
        return None


def _executar_powershell_json(script, timeout=20):
    """Executa PowerShell oculto esperando saída JSON; retorna objeto ou None."""
    try:
        creation_flags = 0x08000000 if os.name == 'nt' else 0
        res = subprocess.check_output(
            ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
            text=True, stderr=subprocess.DEVNULL, creationflags=creation_flags, timeout=timeout,
        )
        if not res or not res.strip():
            return None
        return json.loads(res.strip())
    except Exception:
        return None


def _obter_adaptadores_ativos_detalhados():
    """Adaptadores físicos ativos com identidade estável (InterfaceGuid)."""
    script = (filtro_adaptadores_ativos_ps() +
              " | Select-Object InterfaceGuid, InterfaceAlias, InterfaceIndex | ConvertTo-Json -Compress")
    dados = _executar_powershell_json(script)
    if isinstance(dados, dict):
        dados = [dados]
    if not isinstance(dados, list):
        return []
    adaptadores = []
    for item in dados:
        if not isinstance(item, dict):
            continue
        guid = _normalizar_interface_guid(item.get("InterfaceGuid"))
        if guid is None:
            continue
        adaptadores.append({
            "interface_guid": guid,
            "interface_alias": str(item.get("InterfaceAlias") or ""),
            "interface_index": item.get("InterfaceIndex"),
        })
    return adaptadores


def _ler_dns_registro_interface(guid):
    """(mode, servers_ipv4) de uma interface a partir do Registro do Windows.

    Distinção automático × estático (IPv4): `Set-DnsClientServerAddress
    -ServerAddresses` grava o valor `NameServer` (configuração manual/estática);
    `-ResetServerAddresses` reverte para DHCP (automático). A presença de
    `NameServer` não vazio é a marca confiável de DNS manual IPv4.
    """
    try:
        chave = f"{_INTERFACES_REG_PATH}\\{{{guid}}}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, chave, 0, winreg.KEY_READ) as key:
            name_server = ""
            try:
                name_server = str(winreg.QueryValueEx(key, "NameServer")[0] or "").strip()
            except FileNotFoundError:
                name_server = ""
            if name_server:
                servidores = []
                for parte in re.split(r"[,\s]+", name_server):
                    ip = _validar_ipv4(parte)
                    if ip:
                        servidores.append(ip)
                return ("static", servidores)
            return ("automatic", [])
    except Exception:
        return ("automatic", [])


def obter_dns_atual():
    """DNS atual POR ADAPTADOR físico ativo (identidade estável por GUID).

    Retorna lista de dicts com interface_guid/interface_alias/interface_index,
    mode ('automatic'|'static') e servers_ipv4 (somente IPv4 — escopo da alteração).
    """
    try:
        interfaces = []
        for ad in _obter_adaptadores_ativos_detalhados():
            modo, servidores = _ler_dns_registro_interface(ad["interface_guid"])
            interfaces.append({
                "interface_guid": ad["interface_guid"],
                "interface_alias": ad["interface_alias"],
                "interface_index": ad["interface_index"],
                "mode": modo,
                "servers_ipv4": servidores,
            })
        return interfaces
    except Exception:
        return None


def capturar_estado_sistema():
    """Captura em memória (formato v2) — NÃO grava em disco.

    Representa o estado atual para rollback transacional imediato.
    """
    return {
        "format_version": FORMATO_SNAPSHOT,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "power_plan": obter_plano_energia_atual(),
        "dns_interfaces": obter_dns_atual() or [],
    }

def _escrever_estado_atomico(estado):
    os.makedirs(PASTA_BACKUP, exist_ok=True)
    temp_file = ARQUIVO_ESTADO + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(estado, f, indent=4)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_file, ARQUIVO_ESTADO)
    return True


def _validar_estado_v2(dados):
    if not isinstance(dados.get("power_plan"), (str, type(None))):
        return "power_plan inválido no snapshot v2."
    interfaces = dados.get("dns_interfaces") or []
    if not isinstance(interfaces, list):
        return "dns_interfaces não é lista no snapshot v2."
    for item in interfaces:
        if not isinstance(item, dict):
            return "interface de DNS inválida no snapshot v2."
        guid = item.get("interface_guid")
        if not isinstance(guid, str):
            return "interface_guid inválido no snapshot v2."
        if _normalizar_interface_guid(guid) is None:
            return "interface_guid malformado no snapshot v2."
        if item.get("mode") not in ("automatic", "static"):
            return f"mode de DNS desconhecido no snapshot v2: {item.get('mode')!r}."
        servidores = item.get("servers_ipv4") or []
        if not isinstance(servidores, list):
            return "servers_ipv4 não é lista no snapshot v2."
        if item.get("mode") == "static":
            for s in servidores:
                if _validar_ipv4(s) is None:
                    return f"DNS inválido no snapshot v2: {s!r}."
    return None


def _carregar_estado_snapshot():
    """Lê e valida estado_sistema.json. Retorna (dados, erro).

    erro None = arquivo válido (v1 ou v2); (None, None) = arquivo ausente;
    (None, msg) = corrompido/desconhecido — nunca sobrescreve o arquivo.
    """
    if not os.path.exists(ARQUIVO_ESTADO):
        return None, None
    try:
        with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except Exception as e:
        return None, f"estado_sistema.json corrompido/inválido: {e}"
    if not isinstance(dados, dict):
        return None, "estado_sistema.json não é um objeto JSON."
    if dados.get("format_version") == FORMATO_SNAPSHOT:
        erro = _validar_estado_v2(dados)
        if erro:
            return None, erro
        return dados, None
    # v1 legado: power_plan + dns (lista plana) — reconhecido e preservado.
    if ("dns" in dados and "power_plan" in dados
            and isinstance(dados.get("dns"), (list, type(None)))
            and isinstance(dados.get("power_plan"), (str, type(None)))):
        return dados, None
    return None, "formato de estado_sistema.json desconhecido."


def salvar_snapshot_sistema():
    """Cria/preserva a BASELINE PERSISTENTE do ciclo de modificação.

    - Sem baseline válida: captura e persiste atomicamente.
    - Baseline válida (v1 ou v2): NÃO sobrescreve (idempotente).
    - Arquivo inválido/corrompido/desconhecido: NÃO sobrescreve; retorna False.
    """
    with snapshot_lock:
        try:
            os.makedirs(PASTA_BACKUP, exist_ok=True)
            if os.path.exists(ARQUIVO_ESTADO):
                _dados, erro = _carregar_estado_snapshot()
                if erro:
                    log(f"[SEGURANÇA] Snapshot existente inválido preservado: {erro}")
                    return False
                return True  # baseline válida já existe — não sobrescrever.
            return _escrever_estado_atomico(capturar_estado_sistema())
        except Exception as e:
            log(f"[SEGURANÇA] Falha ao salvar snapshot do sistema: {e}")
            return False

def _resolver_index_por_guid(guid):
    """InterfaceIndex atual de um adaptador localizado por GUID estável (ou None)."""
    guid = _normalizar_interface_guid(guid)
    if guid is None:
        return None
    script = (f"Get-NetAdapter | Where-Object {{ $_.InterfaceGuid -eq '{guid}' }} "
              "| Select-Object -First 1 -ExpandProperty InterfaceIndex")
    try:
        creation_flags = 0x08000000 if os.name == 'nt' else 0
        res = subprocess.check_output(
            ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
            text=True, stderr=subprocess.DEVNULL, creationflags=creation_flags,
            timeout=PS_QUERY_TIMEOUT,
        )
        res = (res or "").strip()
        return int(res) if res else None
    except Exception:
        return None


def _aplicar_dns_interface(interface):
    """Aplica o DNS de UMA interface do snapshot (por GUID) — IPv4 apenas."""
    if not isinstance(interface, dict):
        return False
    guid = _normalizar_interface_guid(interface.get("interface_guid"))
    if guid is None:
        log("[SEGURANÇA] Interface de snapshot com GUID inválido/ausente; ignorada.")
        return False
    index = _resolver_index_por_guid(guid)
    if index is None:
        log(f"[SEGURANÇA] Adaptador {guid} não localizado para restauração de DNS.")
        return False
    if interface.get("mode") == "static":
        validos = [str(s) for s in (interface.get("servers_ipv4") or []) if _validar_ipv4(s)]
        if not validos:
            log(f"[SEGURANÇA] Interface {guid} estática sem DNS válido.")
            return False
        dns_list = ",".join([f"'{d}'" for d in validos])
        cmd = ['powershell', '-Command',
               f"Set-DnsClientServerAddress -InterfaceIndex {index} -ServerAddresses ({dns_list})"]
    else:
        cmd = ['powershell', '-Command',
               f"Set-DnsClientServerAddress -InterfaceIndex {index} -ResetServerAddresses"]
    if not executar_comando_seguro(cmd):
        log(f"[SEGURANÇA] Falha ao restaurar DNS da interface {guid}.")
        return False
    return True


def _restaurar_dns_legado(dns):
    """Restauração conservadora do DNS de snapshot v1 (lista plana).

    O formato v1 NÃO associa DNS a adaptador nem guarda o modo
    automático/estático. Nunca inventamos associação: a ausência de
    informação leva a comportamento conservador, não a chute.

    - Lista vazia/ausente: não altera DNS (não comprova associação/modo).
    - 1 adaptador físico elegível: aplica a lista nele (best effort legado).
    - 2+ adaptadores: ambíguo -> NÃO aplica; resultado parcial.
    - 0 adaptadores: nada a alterar; resultado parcial.

    Retorna RESTAURACAO_SUCESSO / RESTAURACAO_PARCIAL / RESTAURACAO_FALHA.
    """
    dns_validos = []
    if isinstance(dns, list):
        for d in dns:
            ip = _validar_ipv4(d)
            if ip:
                dns_validos.append(ip)

    if not dns_validos:
        log("[SEGURANÇA] Snapshot v1 com DNS vazio/ausente: restauração conservadora "
            "(formato antigo não comprova associação/modo; DNS não alterado).")
        return RESTAURACAO_PARCIAL

    adaptadores = _obter_adaptadores_ativos_detalhados()

    if len(adaptadores) == 0:
        log("[SEGURANÇA] Snapshot v1: nenhum adaptador físico elegível; DNS não alterado.")
        return RESTAURACAO_PARCIAL

    if len(adaptadores) > 1:
        log("[SEGURANÇA] Snapshot antigo não possui informação suficiente para restaurar "
            f"o DNS com segurança em múltiplos adaptadores ({len(adaptadores)} elegíveis); "
            "DNS não alterado.")
        return RESTAURACAO_PARCIAL

    # Exatamente UM adaptador elegível — não há ambiguidade de destino.
    ad = adaptadores[0]
    index = ad.get("interface_index")
    if not isinstance(index, int):
        index = _resolver_index_por_guid(ad.get("interface_guid"))
    if index is None:
        log("[SEGURANÇA] Snapshot v1: adaptador único sem InterfaceIndex resolvível; "
            "DNS não restaurado.")
        return RESTAURACAO_PARCIAL

    dns_list = ",".join([f"'{d}'" for d in dns_validos])
    cmd = ['powershell', '-Command',
           f"Set-DnsClientServerAddress -InterfaceIndex {index} -ServerAddresses ({dns_list})"]
    if not executar_comando_seguro(cmd):
        log("[SEGURANÇA] Falha ao restaurar DNS do snapshot legado (v1) no adaptador único.")
        return RESTAURACAO_FALHA

    log("[SEGURANÇA] DNS do snapshot legado (v1) restaurado em adaptador único (best effort).")
    return RESTAURACAO_SUCESSO


def _restaurar_dns_estado(estado):
    """Restaura DNS (v2 por GUID ou v1 conservador). Retorna resultado 3-estados."""
    interfaces = estado.get("dns_interfaces")
    if interfaces is None and "dns" in estado:
        return _restaurar_dns_legado(estado.get("dns"))
    if not isinstance(interfaces, list):
        return RESTAURACAO_SUCESSO
    sucessos = 0
    falhas = 0
    for item in interfaces:
        if isinstance(item, dict) and _aplicar_dns_interface(item):
            sucessos += 1
        else:
            falhas += 1
    if falhas == 0:
        return RESTAURACAO_SUCESSO
    if sucessos == 0:
        return RESTAURACAO_FALHA
    return RESTAURACAO_PARCIAL


def restaurar_estado_sistema(estado, escopo=None):
    """Restaura uma estrutura de estado fornecida explicitamente.

    escopo: None (plano + DNS), 'plano' (somente plano — rollback transacional),
            'dns' (somente DNS).
    Retorna RESTAURACAO_SUCESSO / RESTAURACAO_PARCIAL / RESTAURACAO_FALHA.
    """
    if not isinstance(estado, dict):
        return RESTAURACAO_FALHA
    resultados = []
    if escopo in (None, "plano"):
        plano = estado.get("power_plan")
        if plano:
            if not executar_comando_seguro(['powercfg', '/setactive', str(plano)]):
                log("[SEGURANÇA] Falha ao restaurar plano de energia.")
                resultados.append(RESTAURACAO_FALHA)
            else:
                resultados.append(RESTAURACAO_SUCESSO)
        else:
            resultados.append(RESTAURACAO_SUCESSO)
    if escopo in (None, "dns"):
        resultados.append(_restaurar_dns_estado(estado))
    return _combinar_resultados(*resultados)


def restaurar_snapshot_sistema():
    """Lê a baseline persistente e restaura (plano + DNS). Retorna resultado 3-estados."""
    with snapshot_lock:
        try:
            dados, erro = _carregar_estado_snapshot()
            if erro:
                log(f"[SEGURANÇA] Snapshot inválido não restaurado: {erro}")
                return RESTAURACAO_FALHA
            if dados is None:
                return RESTAURACAO_FALHA
            return restaurar_estado_sistema(dados)
        except Exception as e:
            log(f"[SEGURANÇA] Falha ao restaurar snapshot do sistema: {e}")
            return RESTAURACAO_FALHA


def finalizar_snapshot_sistema():
    """Encerra a baseline SOMENTE após restauração concluída com sucesso."""
    with snapshot_lock:
        try:
            if os.path.exists(ARQUIVO_ESTADO):
                os.remove(ARQUIVO_ESTADO)
            tmp = ARQUIVO_ESTADO + ".tmp"
            if os.path.exists(tmp):
                os.remove(tmp)
            return not os.path.exists(ARQUIVO_ESTADO)
        except Exception as e:
            log(f"[SEGURANÇA] Falha ao finalizar snapshot: {e}")
            return False


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

def restaurar_tudo_jogo(pasta_jogo=None):
    """Restaura somente o namespace de backup do cliente informado, com replace atômico e falhas explícitas."""
    with lock_otimizacao:
        pasta_jogo = normalizar_pasta_jogo(pasta_jogo)
        pasta_backup_cliente = obter_pasta_backup_cliente(pasta_jogo, criar=False)
        if not os.path.isdir(pasta_backup_cliente):
            return False, "Nenhum backup encontrado para este cliente."

        ignorar = {"aika_index.json", "aika_index.json.meta", "automod_history.json"}
        backup_files = []
        for root, _dirs, files in os.walk(pasta_backup_cliente):
            for nome in files:
                if nome in ignorar or nome.endswith(".tmp"):
                    continue
                backup_files.append(os.path.join(root, nome))
        if not backup_files:
            return False, "Nenhum arquivo de jogo disponível para restauração neste cliente."

        restaurados = 0
        falhas = []
        for caminho_backup in backup_files:
            rel = os.path.relpath(caminho_backup, pasta_backup_cliente)
            destino = os.path.join(pasta_jogo, rel)
            if not caminho_seguro(pasta_jogo, destino):
                falhas.append((rel, "destino fora do cliente")); continue
            temp = None
            try:
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                fd, temp = tempfile.mkstemp(prefix=f".{os.path.basename(destino)}.", suffix=".restore.tmp", dir=os.path.dirname(destino))
                os.close(fd)
                shutil.copy2(caminho_backup, temp)
                if _sha256_arquivo(temp) != _sha256_arquivo(caminho_backup):
                    raise OSError("hash temporário de restore divergente")
                if os.path.exists(destino):
                    try: os.chmod(destino, stat.S_IWRITE)
                    except OSError: pass
                os.replace(temp, destino); temp = None
                if _sha256_arquivo(destino) != _sha256_arquivo(caminho_backup):
                    raise OSError("hash final de restore divergente")
                restaurados += 1
            except Exception as e:
                falhas.append((rel, str(e)))
            finally:
                if temp and os.path.exists(temp):
                    try: os.remove(temp)
                    except OSError: pass

        if falhas:
            log(f"[SEGURANÇA] Restore parcial: {restaurados} OK, {len(falhas)} falha(s).")
            return False, f"Restauração parcial: {restaurados} arquivo(s) restaurado(s), {len(falhas)} falha(s). Histórico foi preservado."
        return True, f"Sucesso! {restaurados} arquivo(s) restaurado(s)."


def _valor_ifeo_igual(a, b):
    if a is None or b is None:
        return False
    return a.get("type") == b.get("type") and a.get("value") == b.get("value")


def _remover_valor_ifeo(exe, nome):
    caminho = _ifeo_caminho_perfoptions(exe)
    if caminho is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, caminho, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, nome)
        return True
    except (FileNotFoundError, OSError):
        return False


def _definir_valor_ifeo(exe, nome, tipo, valor):
    caminho = _ifeo_caminho_perfoptions(exe)
    if caminho is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, caminho, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, nome, 0, tipo, valor)
        return True
    except (FileNotFoundError, OSError):
        return False


def _remover_perfoptions_ifeo(exe):
    caminho_chave = _ifeo_caminho_chave(exe)
    if caminho_chave is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, caminho_chave, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteKey(key, "PerfOptions")
        return True
    except (FileNotFoundError, OSError):
        return False


def _restaurar_ifeo_executavel(exe, entrada):
    """Restaura IFEO de UM executável com ownership comprovado (conservador)."""
    perfopts_atual = _ler_perfoptions_ifeo(exe)
    otim_values = entrada.get("optimizer_values") or {}
    values_before = entrada.get("values_before") or {}
    perfoptions_existed = bool(entrada.get("perfoptions_existed"))
    conflito = False

    for nome in IFEO_VALORES_OTIMIZADOR:
        otim = otim_values.get(nome)
        if otim is None:
            continue
        antes = values_before.get(nome)
        atual = (perfopts_atual or {}).get(nome)

        if atual is not None and _valor_ifeo_igual(atual, otim):
            # Estado atual ainda é o que o Optimizer escreveu → seguro.
            if antes is None:
                if not _remover_valor_ifeo(exe, nome):
                    conflito = True
            else:
                if not _definir_valor_ifeo(exe, nome, antes["type"], antes["value"]):
                    conflito = True
        elif atual is None and antes is not None:
            # Valor original existia e desapareceu depois da nossa aplicação.
            conflito = True
        elif atual is not None:
            # Valor atual difere do que o Optimizer escreveu → alteração externa.
            conflito = True

    if not perfoptions_existed and not conflito:
        perfopts_depois = _ler_perfoptions_ifeo(exe)
        if perfopts_depois is not None and len(perfopts_depois) == 0:
            _remover_perfoptions_ifeo(exe)

    if conflito:
        log(f"[SEGURANÇA] Conflito externo em IFEO/{exe}; restauração parcial preservada.")
        return RESTAURACAO_PARCIAL
    return RESTAURACAO_SUCESSO


def _restaurar_ifeo_ownership():
    """Restaura IFEO/PerfOptions SOMENTE com ownership comprovado.

    Nunca apaga o que não é comprovadamente nosso. Retorna
    RESTAURACAO_SUCESSO / RESTAURACAO_PARCIAL / RESTAURACAO_FALHA.
    """
    legacy_result = _adotar_legados_pendentes()
    dados, erro = _carregar_ifeo_metadata()
    if erro:
        log(f"[SEGURANÇA] Metadata IFEO inválido; restauração IFEO não executada: {erro}")
        return RESTAURACAO_FALHA
    if not dados or not dados.get("executables"):
        return legacy_result
    permitidos = _executaveis_ifeo_permitidos()
    resultados = []
    for exe, entrada in dados["executables"].items():
        exe_norm = _normalizar_nome_ifeo(exe)
        if exe_norm is None or exe_norm not in permitidos:
            log(f"[SEGURANÇA] Executável IFEO fora da allowlist ignorado: {exe!r}.")
            resultados.append(RESTAURACAO_FALHA)
            continue
        resultados.append(_restaurar_ifeo_executavel(exe_norm, entrada))
    normal = _combinar_resultados(*resultados)
    if legacy_result == RESTAURACAO_PARCIAL:
        return RESTAURACAO_PARCIAL
    return normal


def restaurar_registro_sistema():
    with lock_otimizacao:
        try:
            snapshot_resultado = RESTAURACAO_SUCESSO
            if os.path.exists(ARQUIVO_ESTADO):
                snapshot_resultado = restaurar_snapshot_sistema()
            ifeo_resultado = _restaurar_ifeo_ownership()
            if not os.path.isdir(PASTA_BACKUP_REG):
                return False, "Sem backup de registro."
            # IFEO/PerfOptions é restaurado por ownership (nunca por .reg cego).
            arquivos = [a for a in os.listdir(PASTA_BACKUP_REG)
                        if a.lower().endswith('.reg')
                        and not a.lower().startswith('backup_prioridade_')]
            if not arquivos:
                return False, "Pasta de backup existe, mas não contém arquivos .reg."
            restaurados = 0; falhas = []
            for arquivo in arquivos:
                caminho = os.path.join(PASTA_BACKUP_REG, arquivo)
                if executar_comando_seguro(['reg', 'import', caminho]):
                    restaurados += 1
                else:
                    falhas.append(arquivo)
            if falhas or snapshot_resultado != RESTAURACAO_SUCESSO or ifeo_resultado != RESTAURACAO_SUCESSO:
                estado_snapshot = "OK" if snapshot_resultado == RESTAURACAO_SUCESSO else snapshot_resultado
                return False, f"Restauração parcial do sistema: {restaurados}/{len(arquivos)} chaves importadas; {len(falhas)} falha(s); snapshot={estado_snapshot}; ifeo={ifeo_resultado}."
            # Baseline só é encerrada após a restauração geral (snapshot + registros)
            # ser considerada bem-sucedida. Falha parcial preserva o snapshot.
            finalizar_snapshot_sistema()
            return True, f"Sistema revertido! ({restaurados} chaves restauradas)"
        except Exception as e:
            return False, str(e)
