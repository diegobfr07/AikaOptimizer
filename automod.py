import os, json, shutil, stat, time, threading
from config import *
from seguranca import fazer_backup_rapido, criar_substituto_old

def criar_index_jogo(pasta_jogo=PASTA_JOGO_PADRAO):
    try:
        index = {}
        for root, dirs, files in os.walk(pasta_jogo):
            for f in files: index[f.lower()] = os.path.join(root, f)
        os.makedirs(PASTA_BACKUP, exist_ok=True)
        with open(ARQUIVO_INDEX, 'w') as f: json.dump(index, f)
        return True
    except Exception: return False

def carregar_index_jogo(pasta_jogo=PASTA_JOGO_PADRAO):
    if not os.path.exists(ARQUIVO_INDEX): criar_index_jogo(pasta_jogo)
    try:
        with open(ARQUIVO_INDEX, 'r') as f: return json.load(f)
    except Exception: return {}

def injetar_mods(lista_arquivos_mods, pasta_jogo=PASTA_JOGO_PADRAO):
    with lock_otimizacao:
        try:
            index = carregar_index_jogo(pasta_jogo)
            if not index: return -1
            arquivos_substituidos = 0

            for mod_caminho in lista_arquivos_mods:
                nome_base_mod, ext_mod = os.path.splitext(os.path.basename(mod_caminho).lower())
                
                # Permite injetar .bin, .jit, .dds, .tga, etc. Só ignora arquivos que são obviamente lixo.
                if ext_mod in ['.meta', '.old', '.png', '.jpg', '.txt', '.ini']:
                    continue

                destino = None
                
                # Varre a pasta do jogo buscando o arquivo original (ignorando nossos próprios mods soltos)
                extensoes_proibidas = ('.dds', '.tga', '.meta', '.old', '.png', '.jpg')
                for nome_index, caminho_index in index.items():
                    if os.path.splitext(nome_index)[0] == nome_base_mod:
                        if not nome_index.endswith(extensoes_proibidas):
                            destino = caminho_index
                            break
                
                if not destino or not caminho_seguro(pasta_jogo, destino): continue

                # Bloqueia raw copy de formato incompatível (exceto .dds, que tem pipeline próprio)
                ext_destino = os.path.splitext(destino)[1].lower()
                if ext_mod != '.dds' and ext_mod != ext_destino:
                    log(f"[AUTOMOD] Formato incompatível: arquivo {os.path.basename(mod_caminho)} não pode substituir destino {os.path.basename(destino)}.")
                    continue
                
                caminho_backup = os.path.join(PASTA_BACKUP, os.path.relpath(destino, PASTA_JOGO_PADRAO))
                if not os.path.exists(caminho_backup):
                    if not fazer_backup_rapido(destino, caminho_backup):
                        log(f"[ERRO] Backup de {os.path.basename(destino)} falhou. Mod não aplicado.")
                        continue

                antes = arquivos_substituidos
                try:
                    # SALVA O MODO ORIGINAL
                    modo_original = os.stat(destino).st_mode
                    os.chmod(destino, stat.S_IWRITE)

                    try: # INICIA O BLOCO BLINDADO (Tudo aqui dentro tem seguro)
                        if ext_mod == '.dds':
                            with open(destino, "rb") as f: jit_original = bytearray(f.read())
                            with open(mod_caminho, "rb") as f: tex = f.read()

                            # Verifica se realmente é uma textura DDS válida
                            if len(tex) < 128 or tex[0:4] != b'DDS ':
                                continue 

                            # Acha a assinatura no arquivo JIT original
                            assinaturas = [b'JT31', b'JT33', b'JT35', b'JT20', b'DDS ']
                            offset = -1
                            tipo_original = None
                            for ass in assinaturas:
                                off = jit_original.find(ass)
                                if off != -1:
                                    offset = off
                                    tipo_original = ass
                                    break
                            
                            if offset != -1:
                                header_size = 128
                                fourcc = tex[84:88]
                                if len(tex) > 88 and fourcc == b"DX10":
                                    header_size += 20
                                
                                if len(tex) <= header_size:
                                    continue

                                height_dds = tex[12:16]
                                width_dds = tex[16:20]
                                payload_dds = tex[header_size:]

                                if tipo_original in [b'JT31', b'JT33', b'JT35']:
                                    if fourcc == b'DXT1': magic_jit = b'JT31'
                                    elif fourcc == b'DXT3': magic_jit = b'JT33'
                                    elif fourcc in [b'DXT5', b'DX10']: magic_jit = b'JT35'
                                    else: magic_jit = b'JT35'

                                    jit_novo = bytearray()
                                    jit_novo.extend(jit_original[:offset]) 
                                    jit_novo.extend(magic_jit)             
                                    jit_novo.extend(width_dds)             
                                    jit_novo.extend(height_dds)            
                                    jit_novo.extend(payload_dds)           
                                    
                                    with open(destino, "wb") as f: f.write(jit_novo)
                                    arquivos_substituidos += 1
                                    
                                elif tipo_original == b'DDS ':
                                    jit_novo = jit_original[:offset] + tex
                                    with open(destino, "wb") as f: f.write(jit_novo)
                                    arquivos_substituidos += 1
                                    
                        else:
                            shutil.copyfile(mod_caminho, destino)
                            arquivos_substituidos += 1
                            
                    finally:
                        # MÁGICA FINAL: Este código roda SEMPRE, aconteça o que acontecer, garantindo a proteção do arquivo!
                        os.chmod(destino, modo_original)
                        
                except Exception as e:
                    log(f"[AUTOMOD] Erro ao injetar {os.path.basename(destino)}: {e}")

                if arquivos_substituidos > antes:
                    registrar_mod_ativo(destino, mod_caminho, pasta_jogo)
            return arquivos_substituidos
        except Exception: return -1

def remover_efeitos_pesados_aika(pasta_jogo=PASTA_JOGO_PADRAO):
    with lock_otimizacao:
        try:
            arquivos_modificados = 0
            efeitos_alvo = ["weaponeff3.bin", "skilleff.bin", "skilleff2.bin", "skilleff3.bin", "particle.bin", "particle2.bin", "glow.bin", "gloweffect.bin", "mageff.bin", "maguiceff.bin"]
            
            pasta_efeitos = os.path.join(pasta_jogo, "Data", "Effect")
            if not os.path.exists(pasta_efeitos): pasta_efeitos = pasta_jogo
            
            for root, dirs, files in os.walk(pasta_efeitos):
                for file in files:
                    if file.lower() in efeitos_alvo:
                        caminho = os.path.join(root, file)
                        if not caminho_seguro(pasta_jogo, caminho): continue
                        
                        caminho_backup = os.path.join(PASTA_BACKUP, os.path.relpath(caminho, PASTA_JOGO_PADRAO))
                        if not os.path.exists(caminho_backup): 
                            fazer_backup_rapido(caminho, caminho_backup)
                        
                        try:
                            os.chmod(caminho, stat.S_IWRITE)
                            os.remove(caminho) 
                            arquivos_modificados += 1
                        except Exception: pass
            
            if arquivos_modificados > 0:
                return 1
            else:
                pasta_backup_efeitos = os.path.join(PASTA_BACKUP, "Data", "Effect")
                if os.path.exists(pasta_backup_efeitos):
                    backups_feitos = [f.lower() for f in os.listdir(pasta_backup_efeitos)]
                    if any(efeito in backups_feitos for efeito in efeitos_alvo):
                        return 2
                
                return 0
        except Exception: return -1

# ========================================================
# HISTÓRICO DE MODIFICAÇÕES ATIVAS (AUTOMOD)
# ========================================================
_historico_lock = threading.Lock()

def _chave_destino(destino, pasta_jogo=PASTA_JOGO_PADRAO):
    """Chave única normalizada (relpath lowercase com separadores '/')."""
    try:
        rel = os.path.relpath(destino, pasta_jogo)
    except Exception:
        rel = destino
    return rel.replace("\\", "/").lower()

def carregar_historico_automod():
    """Retorna {'version':1,'items':{}} — vazio se ausente/corrompido."""
    vazio = {"version": 1, "items": {}}
    if not os.path.exists(ARQUIVO_HISTORICO_AUTOMOD):
        return vazio
    try:
        with open(ARQUIVO_HISTORICO_AUTOMOD, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if not isinstance(dados, dict):
            return vazio
        dados.setdefault("version", 1)
        dados.setdefault("items", {})
        return dados
    except Exception as e:
        log(f"[AUTOMOD] Histórico ilegível (estado seguro): {e}")
        return vazio

def salvar_historico_automod(dados):
    """Escrita atômica (tmp -> os.replace)."""
    try:
        os.makedirs(PASTA_BACKUP, exist_ok=True)
        tmp = ARQUIVO_HISTORICO_AUTOMOD + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=2)
        os.replace(tmp, ARQUIVO_HISTORICO_AUTOMOD)
        return True
    except Exception as e:
        log(f"[AUTOMOD] Erro ao salvar histórico: {e}")
        return False

def listar_mods_ativos():
    """Retorna lista de itens ativos, cada um com a chave ('chave')."""
    dados = carregar_historico_automod()
    itens = []
    for chave, item in dados.get("items", {}).items():
        copia = dict(item)
        copia["chave"] = chave
        itens.append(copia)
    return itens

def registrar_mod_ativo(destino, mod_caminho, pasta_jogo=PASTA_JOGO_PADRAO):
    """Registra/atualiza UMA entrada ativa por destino (não duplica)."""
    with _historico_lock:
        dados = carregar_historico_automod()
        chave = _chave_destino(destino, pasta_jogo)
        rel = os.path.relpath(destino, pasta_jogo).replace("\\", "/")
        item = dados["items"].get(chave)
        if item is None:
            item = {}
            dados["items"][chave] = item
        item["target_relpath"] = rel
        item["target_name"] = os.path.basename(destino)
        item["mod_name"] = os.path.basename(mod_caminho)
        item["backup_relpath"] = rel
        item["last_applied"] = time.strftime("%Y-%m-%d %H:%M:%S")
        item["injection_count"] = item.get("injection_count", 0) + 1
        salvar_historico_automod(dados)

def restaurar_mod_individual(chave_mod, pasta_jogo=PASTA_JOGO_PADRAO):
    """Restaura UM arquivo do histórico. Retorna (True, msg) / (False, msg)."""
    with lock_otimizacao:
        with _historico_lock:
            dados = carregar_historico_automod()
            item = dados.get("items", {}).get(chave_mod)
            if item is None:
                return False, "Item não encontrado no histórico."

            target_rel = item.get("target_relpath") or item.get("backup_relpath")
            if not target_rel:
                return False, "Caminho relativo ausente no histórico."

            destino = os.path.join(pasta_jogo, target_rel.replace("/", os.sep))
            caminho_backup = os.path.join(PASTA_BACKUP, target_rel.replace("/", os.sep))
            nome = item.get("target_name") or os.path.basename(destino)

            if not caminho_seguro(pasta_jogo, destino):
                return False, "Destino fora da pasta do jogo (bloqueado)."
            if not os.path.exists(caminho_backup):
                return False, "Backup original não encontrado."

            tmp_destino = destino + ".restaurando.tmp"
            try:
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                shutil.copyfile(caminho_backup, tmp_destino)
                try:
                    shutil.copymode(caminho_backup, tmp_destino)
                except Exception:
                    pass
                if os.path.exists(destino):
                    try:
                        os.chmod(destino, stat.S_IWRITE)
                    except Exception:
                        pass
                os.replace(tmp_destino, destino)
            except Exception as e:
                if os.path.exists(tmp_destino):
                    try:
                        os.remove(tmp_destino)
                    except Exception:
                        pass
                return False, f"Não foi possível restaurar {nome}: {e}"

            del dados["items"][chave_mod]
            salvar_historico_automod(dados)
            return True, f"{nome} restaurado para o original."

def limpar_historico_automod():
    """Limpa o histórico (usado após restauração total)."""
    with _historico_lock:
        return salvar_historico_automod({"version": 1, "items": {}})

def restaurar_mods_selecionados(chaves, pasta_jogo=PASTA_JOGO_PADRAO):
    """Restaura vários mods em sequência, reutilizando restaurar_mod_individual.

    Retorna {'restaurados': [nomes...], 'falhas': [(nome, motivo), ...]}.
    Falhas parciais não desfazem os sucessos.
    """
    restaurados = []
    falhas = []
    for chave in chaves:
        dados = carregar_historico_automod()
        item = dados.get("items", {}).get(chave)
        nome = (item or {}).get("target_name") or chave
        ok, msg = restaurar_mod_individual(chave, pasta_jogo)
        if ok:
            restaurados.append(nome)
        else:
            prefixo = f"Não foi possível restaurar {nome}: "
            motivo = msg[len(prefixo):] if msg.startswith(prefixo) else msg
            falhas.append((nome, motivo))
    return {"restaurados": restaurados, "falhas": falhas}