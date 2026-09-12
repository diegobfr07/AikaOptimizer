import os, shutil, tempfile, stat, hashlib
from config import *
from seguranca import fazer_backup_rapido


def _sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


# ============================================================
# DETECÇÃO DE FORMATO PELO CONTEÚDO (não pela extensão)
# ============================================================
def detectar_formato_audio(caminho):
    """Detecta o formato real do áudio pelo cabeçalho (magic), não pela extensão.

    Retorna 'WAV', 'OGG', 'MP3', 'M4A' ou 'UNKNOWN'.
    Um .bin do jogo pode conter RIFF/WAVE internamente — a extensão não decide.
    """
    try:
        with open(caminho, "rb") as f:
            cab = f.read(16)
    except Exception:
        return "UNKNOWN"
    if len(cab) < 4:
        return "UNKNOWN"
    # WAV: RIFF....WAVE
    if cab[:4] == b"RIFF" and cab[8:12] == b"WAVE":
        return "WAV"
    # OGG: OggS
    if cab[:4] == b"OggS":
        return "OGG"
    # MP3: tag ID3 ou frame MPEG sync (0xFF seguido de 3 bits altos)
    if cab[:3] == b"ID3":
        return "MP3"
    if cab[0] == 0xFF and (cab[1] & 0xE0) == 0xE0:
        return "MP3"
    # M4A/MP4: container ISO BMFF — 'ftyp' no offset 4
    if len(cab) >= 8 and cab[4:8] == b"ftyp":
        return "M4A"
    return "UNKNOWN"


_DESCRICAO_FORMATO = {
    "WAV": "WAV/PCM",
    "OGG": "OGG",
    "MP3": "MP3",
    "M4A": "M4A/MP4",
}


def _descrever_formato(fmt):
    return _DESCRICAO_FORMATO.get(fmt, "desconhecido")


def validar_compatibilidade_audio(novo_audio, arquivo_alvo):
    """Confere se o novo áudio pode substituir o original sem conversão.

    O projeto não possui conversor multimídia: formatos diferentes são
    recusados com instrução clara (nada é copiado nem feito backup).
    Retorna (ok, mensagem).
    """
    fmt_novo = detectar_formato_audio(novo_audio)
    fmt_alvo = detectar_formato_audio(arquivo_alvo)
    if fmt_alvo == "UNKNOWN":
        return False, ("Formato do áudio original não reconhecido — substituição "
                       "bloqueada para proteger o arquivo do jogo.")
    if fmt_novo == "UNKNOWN":
        return False, "Formato do novo áudio não reconhecido. Use um arquivo de áudio válido."
    if fmt_novo == fmt_alvo:
        return True, ""
    desc_novo = _descrever_formato(fmt_novo)
    desc_alvo = _descrever_formato(fmt_alvo)
    return False, (f"O áudio selecionado usa {desc_novo}, mas o arquivo original usa "
                   f"{desc_alvo}. Converta o arquivo para {desc_alvo} antes de injetar.")


def _replace_atomico(fonte, destino):
    modo = os.stat(destino).st_mode if os.path.exists(destino) else None
    fd, tmp = tempfile.mkstemp(prefix=f".{os.path.basename(destino)}.", suffix=".audio.tmp", dir=os.path.dirname(destino))
    os.close(fd)
    try:
        shutil.copy2(fonte, tmp)
        if os.path.getsize(tmp) != os.path.getsize(fonte) or _sha256(tmp) != _sha256(fonte):
            raise OSError("validação do arquivo temporário falhou")
        if os.path.exists(destino):
            try: os.chmod(destino, stat.S_IWRITE)
            except OSError: pass
        os.replace(tmp, destino); tmp = None
        if modo is not None:
            try: os.chmod(destino, modo)
            except OSError: pass
        if _sha256(destino) != _sha256(fonte):
            raise OSError("validação pós-escrita falhou")
    finally:
        if tmp and os.path.exists(tmp):
            try: os.remove(tmp)
            except OSError: pass


def substituir_audio_customizado(novo_audio, arquivo_alvo, pasta_jogo=None):
    pasta_jogo = normalizar_pasta_jogo(pasta_jogo)
    with lock_otimizacao:
        try:
            novo_audio = os.path.abspath(os.path.normpath(novo_audio)); arquivo_alvo = os.path.abspath(os.path.normpath(arquivo_alvo))
            if not caminho_seguro(pasta_jogo, arquivo_alvo): return False, "Caminho alvo fora do cliente selecionado."
            if not os.path.isfile(novo_audio) or not os.path.isfile(arquivo_alvo): return False, "Arquivo não encontrado."
            if os.path.getsize(novo_audio) <= 0: return False, "Novo áudio está vazio."
            # Compatibilidade ANTES de qualquer alteração: sem formato igual, nada é feito.
            ok_fmt, msg_fmt = validar_compatibilidade_audio(novo_audio, arquivo_alvo)
            if not ok_fmt:
                return False, msg_fmt
            relativo = os.path.relpath(arquivo_alvo, pasta_jogo)
            caminho_backup = os.path.join(obter_pasta_backup_cliente(pasta_jogo), relativo)
            if not fazer_backup_rapido(arquivo_alvo, caminho_backup):
                return False, "Falha ao criar/validar backup. Áudio não foi alterado."
            _replace_atomico(novo_audio, arquivo_alvo)
            return True, "Áudio substituído com escrita atômica."
        except Exception as e:
            return False, str(e)


def restaurar_audio_original(arquivo_alvo, pasta_jogo=None):
    pasta_jogo = normalizar_pasta_jogo(pasta_jogo)
    with lock_otimizacao:
        try:
            arquivo_alvo = os.path.abspath(os.path.normpath(arquivo_alvo))
            if not caminho_seguro(pasta_jogo, arquivo_alvo): return False, "Caminho alvo fora do cliente selecionado."
            relativo = os.path.relpath(arquivo_alvo, pasta_jogo)
            caminho_backup = os.path.join(obter_pasta_backup_cliente(pasta_jogo, criar=False), relativo)
            if not os.path.isfile(caminho_backup) or os.path.getsize(caminho_backup) <= 0:
                return False, "Sem backup válido para este cliente."
            _replace_atomico(caminho_backup, arquivo_alvo)
            return True, "Áudio restaurado!"
        except Exception as e:
            return False, str(e)


_SUFIXO_PREVIA = {
    "WAV": ".wav",
    "OGG": ".ogg",
    "MP3": ".mp3",
    "M4A": ".m4a",
}


def preparar_previa_audio(caminho_bin):
    """Cria prévia temporária com a EXTENSÃO coerente com o formato real.

    O arquivo do jogo nunca é alterado. Formato não reconhecido → None
    (a UI informa o erro; nunca finge que é WAV).
    """
    try:
        fmt = detectar_formato_audio(caminho_bin)
        sufixo = _SUFIXO_PREVIA.get(fmt)
        if not sufixo:
            return None
        fd, caminho_temp = tempfile.mkstemp(suffix=sufixo, prefix='aika_audio_')
        os.close(fd)
        shutil.copyfile(caminho_bin, caminho_temp)
        return caminho_temp
    except Exception:
        return None


def limpar_pasta_temp_audio():
    try:
        pasta = tempfile.gettempdir()
        for f in os.listdir(pasta):
            if f.startswith('aika_audio_'):
                try: os.remove(os.path.join(pasta, f))
                except Exception: pass
    except Exception: pass
