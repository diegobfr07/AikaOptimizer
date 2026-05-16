import os, shutil, tempfile, stat
from config import *
from seguranca import fazer_backup_rapido, criar_substituto_old

def substituir_audio_customizado(novo_audio, arquivo_alvo):
    with lock_otimizacao:
        try:
            novo_audio, arquivo_alvo = os.path.normpath(novo_audio), os.path.normpath(arquivo_alvo)
            if not caminho_seguro(PASTA_JOGO_PADRAO, arquivo_alvo): return False, "Caminho inválido."
            if not os.path.exists(novo_audio) or not os.path.exists(arquivo_alvo): return False, "Arquivo não encontrado."

            caminho_backup = os.path.join(PASTA_BACKUP, os.path.relpath(arquivo_alvo, PASTA_JOGO_PADRAO))
            if not os.path.exists(caminho_backup): fazer_backup_rapido(arquivo_alvo, caminho_backup)

            try: os.chmod(arquivo_alvo, stat.S_IWRITE); criar_substituto_old(arquivo_alvo)
            except Exception: pass
            
            try:
                shutil.copyfile(novo_audio, arquivo_alvo)
                return True, "Sucesso"
            except Exception: return False, "Falha ao sobrescrever."
        except Exception as e: return False, str(e)

def restaurar_audio_original(arquivo_alvo):
    with lock_otimizacao:
        try:
            arquivo_alvo = os.path.normpath(arquivo_alvo)
            caminho_backup = os.path.join(PASTA_BACKUP, os.path.relpath(arquivo_alvo, PASTA_JOGO_PADRAO))
            if os.path.exists(caminho_backup) and os.path.getsize(caminho_backup) > 0:
                try: os.chmod(arquivo_alvo, stat.S_IWRITE); criar_substituto_old(arquivo_alvo)
                except Exception: pass
                try:
                    shutil.copyfile(caminho_backup, arquivo_alvo)
                    return True, "Áudio restaurado!"
                except Exception: return False, "Falha ao restaurar."
            return False, "Sem backup."
        except Exception as e: return False, str(e)

def preparar_previa_audio(caminho_bin):
    try:
        os.makedirs(PASTA_BACKUP, exist_ok=True)
        fd, caminho_wav_temp = tempfile.mkstemp(suffix='.wav', prefix='aika_audio_', dir=PASTA_BACKUP)
        os.close(fd) 
        shutil.copyfile(caminho_bin, caminho_wav_temp)
        return caminho_wav_temp
    except Exception: return None

def limpar_pasta_temp_audio():
    try:
        for f in os.listdir(PASTA_BACKUP):
            if f.startswith('aika_audio_') and f.endswith('.wav'):
                try: os.remove(os.path.join(PASTA_BACKUP, f))
                except Exception: pass
    except Exception: pass