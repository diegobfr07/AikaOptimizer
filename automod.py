import os, json, shutil, stat
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
                
                # Só injeta se for arquivo de imagem (DDS ou TGA). Ignora .meta, .txt, etc.
                if ext_mod not in ['.dds', '.tga']:
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
                
                caminho_backup = os.path.join(PASTA_BACKUP, os.path.relpath(destino, PASTA_JOGO_PADRAO))
                if not os.path.exists(caminho_backup): fazer_backup_rapido(destino, caminho_backup)

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
                        
                except Exception as e: pass
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