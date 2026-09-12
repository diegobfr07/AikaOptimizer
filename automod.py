import os, json, shutil, stat, time, threading, struct, hashlib, tempfile
from config import *
from seguranca import fazer_backup_rapido, criar_substituto_old
from textura import detectar_textura_jit_bytes, _validar_tga_embutido

_ARQUIVO_INDEX_META = ARQUIVO_INDEX + ".meta"  # legado; novos índices são por cliente


def _paths_cliente(pasta_jogo):
    pasta_jogo = _normalizar_pasta_jogo(pasta_jogo)
    if not pasta_jogo:
        return None
    backup = obter_pasta_backup_cliente(pasta_jogo)
    indice = os.path.join(backup, "aika_index.json")
    return {
        "backup": backup,
        "index": indice,
        "index_meta": indice + ".meta",
        "history": os.path.join(backup, "automod_history.json"),
    }
_ASSINATURAS_JIT = (b"JT31", b"JT33", b"JT35", b"JT20", b"DDS ")


def _normalizar_pasta_jogo(pasta_jogo):
    if pasta_jogo is None:
        pasta_jogo = normalizar_pasta_jogo(None)
    if not pasta_jogo:
        return None
    return os.path.abspath(os.path.normpath(pasta_jogo))


def _caminho_no_cliente(pasta_jogo, caminho):
    try:
        raiz = os.path.normcase(os.path.realpath(pasta_jogo))
        alvo = os.path.normcase(os.path.realpath(caminho))
        return os.path.commonpath([raiz, alvo]) == raiz
    except (OSError, ValueError, TypeError):
        return False


def criar_index_jogo(pasta_jogo=None):
    """Cria o índice persistente e grava a raiz à qual ele pertence."""
    pasta_jogo = _normalizar_pasta_jogo(pasta_jogo)
    if not pasta_jogo:
        return False
    try:
        if not os.path.isdir(pasta_jogo):
            log(f"[AutoMod][ERRO] Pasta do cliente inexistente: {pasta_jogo}")
            return False
        index = {}
        for root, _dirs, files in os.walk(pasta_jogo):
            for nome in files:
                caminho = os.path.join(root, nome)
                chave = nome.lower()
                if chave in index:
                    rel = os.path.relpath(caminho, pasta_jogo).replace("\\", "/")
                    chave = f"__duplicate__/{rel.lower()}"
                index[chave] = caminho
        paths = _paths_cliente(pasta_jogo)
        temporario = paths["index"] + ".tmp"
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump(index, f)
            f.flush(); os.fsync(f.fileno())
        os.replace(temporario, paths["index"])
        with open(paths["index_meta"] + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"version": 3, "game_root": pasta_jogo}, f)
            f.flush(); os.fsync(f.fileno())
        os.replace(paths["index_meta"] + ".tmp", paths["index_meta"])
        return True
    except Exception as e:
        log(f"[AutoMod][ERRO] Falha ao criar índice: {e}")
        return False


def _indice_valido(index, pasta_jogo, meta_path=None):
    if not isinstance(index, dict) or not index:
        return False, "índice vazio ou inválido"
    try:
        with open(meta_path or _paths_cliente(pasta_jogo)["index_meta"], "r", encoding="utf-8") as f:
            meta = json.load(f)
        if not isinstance(meta.get("game_root"), str) or not meta["game_root"].strip():
            return False, "metadados do índice não identificam o cliente"
        raiz_index = _normalizar_pasta_jogo(meta["game_root"])
    except Exception:
        return False, "índice legado sem identificação do cliente"
    if os.path.normcase(raiz_index) != os.path.normcase(pasta_jogo):
        return False, f"índice pertence a outro cliente: {raiz_index}"
    for caminho in index.values():
        if not isinstance(caminho, str) or not os.path.isfile(caminho):
            return False, f"caminho obsoleto no índice: {caminho}"
        if not _caminho_no_cliente(pasta_jogo, caminho):
            return False, f"caminho fora do cliente no índice: {caminho}"
    return True, ""


def carregar_index_jogo(pasta_jogo=None):
    """Carrega o índice isolado do cliente; reconstrói automaticamente se stale."""
    pasta_jogo = _normalizar_pasta_jogo(pasta_jogo)
    if not pasta_jogo:
        return {}
    paths = _paths_cliente(pasta_jogo)
    index = {}
    try:
        with open(paths["index"], "r", encoding="utf-8") as f:
            index = json.load(f)
    except Exception:
        pass
    valido, motivo = _indice_valido(index, pasta_jogo, paths["index_meta"])
    if not valido:
        log(f"[AutoMod] Índice será reconstruído: {motivo}.")
        if not criar_index_jogo(pasta_jogo):
            return {}
        try:
            with open(paths["index"], "r", encoding="utf-8") as f:
                index = json.load(f)
        except Exception as e:
            log(f"[AutoMod][ERRO] Índice reconstruído não pôde ser lido: {e}")
            return {}
    return index


def _emitir_automod(mensagem, callback=None):
    log(mensagem)
    if callback:
        try:
            callback(mensagem)
            return
        except Exception as e:
            log(f"[AutoMod][ERRO] Falha no callback de log: {e}")
    try:
        print(mensagem)
    except Exception:
        pass


def _sha256_bytes(dados):
    return hashlib.sha256(dados).hexdigest()


def _ler_arquivo(caminho):
    with open(caminho, "rb") as f:
        return f.read()


def detectar_formato_jit(dados):
    """
    Usa exatamente o mesmo detector do extrator.

    Isso evita a regressão em que o extrator classificava um arquivo como
    JT33 e o AutoMod classificava os mesmos bytes como JT35/JT20.
    """
    info = detectar_textura_jit_bytes(dados)
    return {"tipo": info["tipo"], "offset": info["offset"], **info}


def _analisar_dds(dados):
    """Analisa DDS sem bloquear formatos nativos que podem viver embutidos em JIT."""
    if len(dados) < 128 or dados[:4] != b"DDS ":
        raise ValueError("DDS inválido: assinatura/cabeçalho de 128 bytes ausente")
    if struct.unpack_from("<I", dados, 4)[0] != 124:
        raise ValueError("DDS inválido: tamanho do cabeçalho diferente de 124")
    if struct.unpack_from("<I", dados, 76)[0] != 32:
        raise ValueError("DDS inválido: pixel format diferente de 32 bytes")

    altura, largura = struct.unpack_from("<II", dados, 12)
    mipmaps = struct.unpack_from("<I", dados, 28)[0] or 1
    fourcc_header = dados[84:88]
    header_size = 128
    formato = fourcc_header
    dxgi = None

    if fourcc_header == b"DX10":
        if len(dados) < 148:
            raise ValueError("DDS DX10 inválido: cabeçalho de 148 bytes incompleto")
        dxgi = struct.unpack_from("<I", dados, 128)[0]
        formato = {
            71: b"DXT1", 72: b"DXT1",
            74: b"DXT3", 75: b"DXT3",
            77: b"DXT5", 78: b"DXT5",
        }.get(dxgi, b"DX10")
        header_size = 148

    if not (1 <= largura <= 16384 and 1 <= altura <= 16384):
        raise ValueError(f"DDS inválido: dimensões {largura}x{altura}")

    info = {
        "width": largura,
        "height": altura,
        "mipmaps": mipmaps,
        "fourcc": formato,
        "source_fourcc": fourcc_header,
        "dxgi": dxgi,
        "header_size": header_size,
        "base_size": None,
        "total_payload_size": None,
        "payload": None,
        "payload_all": None,
        "dds_size": len(dados),
        "jit_magic": None,
    }

    if formato in (b"DXT1", b"DXT3", b"DXT5"):
        bloco = 8 if formato == b"DXT1" else 16
        total_payload = 0
        w, h = largura, altura
        for _ in range(mipmaps):
            total_payload += max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * bloco
            w = max(1, w // 2)
            h = max(1, h // 2)

        if len(dados) < header_size + total_payload:
            raise ValueError(
                f"DDS truncado: payload {len(dados) - header_size}, "
                f"esperado {total_payload} para {mipmaps} mipmap(s)"
            )

        base_size = max(1, (largura + 3) // 4) * max(1, (altura + 3) // 4) * bloco
        info.update({
            "base_size": base_size,
            "total_payload_size": total_payload,
            "payload": dados[header_size:header_size + base_size],
            "payload_all": dados[header_size:header_size + total_payload],
            "dds_size": header_size + total_payload,
            "jit_magic": {b"DXT1": b"JT31", b"DXT3": b"JT33", b"DXT5": b"JT35"}[formato],
        })

    return info


def _analisar_tga_basico(dados):
    if len(dados) < 18:
        raise ValueError("TGA inválido: cabeçalho de 18 bytes ausente")

    id_size = dados[0]
    color_map_type = dados[1]
    image_type = dados[2]
    color_map_first = struct.unpack_from("<H", dados, 3)[0]
    color_map_length = struct.unpack_from("<H", dados, 5)[0]
    color_map_bpp = dados[7]
    largura, altura = struct.unpack_from("<HH", dados, 12)
    bpp, descriptor = dados[16], dados[17]

    if image_type not in (1, 2, 3, 9, 10, 11):
        raise ValueError(f"TGA inválido: image type {image_type} não suportado")
    if color_map_type not in (0, 1):
        raise ValueError("TGA inválido: color map type não suportado")
    if bpp not in (8, 15, 16, 24, 32):
        raise ValueError(f"TGA inválido: profundidade {bpp} bits não suportada")
    if color_map_type and color_map_bpp not in (8, 15, 16, 24, 32):
        raise ValueError("TGA inválido: profundidade da paleta não suportada")
    if not (1 <= largura <= 8192 and 1 <= altura <= 8192):
        raise ValueError(f"TGA inválido: dimensões {largura}x{altura}")

    return {
        "width": largura,
        "height": altura,
        "id_size": id_size,
        "color_map_type": color_map_type,
        "color_map_first": color_map_first,
        "color_map_length": color_map_length,
        "color_map_bpp": color_map_bpp,
        "image_type": image_type,
        "bpp": bpp,
        "descriptor": descriptor,
    }


def _cor_tga_para_bgra(raw, bpp, grayscale=False):
    if grayscale:
        if bpp == 8:
            v = raw[0]
            return (v, v, v, 255)
        if bpp == 16:
            v, a = raw[0], raw[1]
            return (v, v, v, a)
        raise ValueError(f"TGA grayscale {bpp} bits não suportado")

    if bpp == 8:
        v = raw[0]
        return (v, v, v, 255)
    if bpp in (15, 16):
        valor = int.from_bytes(raw[:2], "little")
        b = ((valor >> 0) & 0x1F) * 255 // 31
        g = ((valor >> 5) & 0x1F) * 255 // 31
        r = ((valor >> 10) & 0x1F) * 255 // 31
        a = 255 if bpp == 15 else (255 if (valor & 0x8000) else 0)
        return (b, g, r, a)
    if bpp == 24:
        b, g, r = raw[:3]
        return (b, g, r, 255)
    if bpp == 32:
        b, g, r, a = raw[:4]
        return (b, g, r, a)
    raise ValueError(f"TGA {bpp} bits não suportado")


def _analisar_tga(dados):
    """
    Decodifica TGA comum, RLE e paletizado para BGRA.

    A versão anterior aceitava esses formatos ao extrair, mas o AutoMod novo
    só aceitava true-color não comprimido 24/32 bits. Essa assimetria era uma
    das causas de TGA extraído corretamente não poder ser reinjetado.
    """
    info = _analisar_tga_basico(dados)
    cursor = 18 + info["id_size"]
    if cursor > len(dados):
        raise ValueError("TGA inválido: campo ID truncado")

    palette = None
    if info["color_map_type"]:
        entry_bytes = (info["color_map_bpp"] + 7) // 8
        palette = []
        for _ in range(info["color_map_length"]):
            if cursor + entry_bytes > len(dados):
                raise ValueError("TGA truncado: paleta incompleta")
            raw = dados[cursor:cursor + entry_bytes]
            cursor += entry_bytes
            palette.append(_cor_tga_para_bgra(raw, info["color_map_bpp"]))

    pixel_bytes = (info["bpp"] + 7) // 8
    total = info["width"] * info["height"]
    rle = info["image_type"] in (9, 10, 11)
    color_mapped = info["image_type"] in (1, 9)
    grayscale = info["image_type"] in (3, 11)

    def ler_pixel():
        nonlocal cursor
        if cursor + pixel_bytes > len(dados):
            raise ValueError("TGA truncado: pixel incompleto")
        raw = dados[cursor:cursor + pixel_bytes]
        cursor += pixel_bytes
        if color_mapped:
            if palette is None:
                raise ValueError("TGA paletizado sem paleta")
            indice = int.from_bytes(raw, "little") - info["color_map_first"]
            if not (0 <= indice < len(palette)):
                raise ValueError("TGA paletizado contém índice fora da paleta")
            return palette[indice]
        return _cor_tga_para_bgra(raw, info["bpp"], grayscale=grayscale)

    pixels = []
    if not rle:
        for _ in range(total):
            pixels.append(ler_pixel())
    else:
        while len(pixels) < total:
            if cursor >= len(dados):
                raise ValueError("TGA RLE truncado")
            packet = dados[cursor]
            cursor += 1
            count = (packet & 0x7F) + 1
            if len(pixels) + count > total:
                raise ValueError("TGA RLE produz pixels além das dimensões declaradas")
            if packet & 0x80:
                pixel = ler_pixel()
                pixels.extend([pixel] * count)
            else:
                for _ in range(count):
                    pixels.append(ler_pixel())

    largura, altura = info["width"], info["height"]
    linhas = [pixels[y * largura:(y + 1) * largura] for y in range(altura)]
    # bit 5: origem superior. Canonizamos para top-left, igual ao TGA gerado
    # pelo extrator JT20 (descriptor 0x28).
    if not (info["descriptor"] & 0x20):
        linhas.reverse()
    # bit 4: origem à direita.
    if info["descriptor"] & 0x10:
        linhas = [list(reversed(linha)) for linha in linhas]
    pixels = [pixel for linha in linhas for pixel in linha]

    info = dict(info)
    info["pixels"] = pixels
    info["consumed_size"] = cursor
    return info


def _paletizar_bgra(pixels):
    mapa = {}
    paleta = []
    indices = bytearray()
    for pixel in pixels:
        indice = mapa.get(pixel)
        if indice is None:
            if len(paleta) >= 256:
                mapa = None
                break
            indice = len(paleta)
            mapa[pixel] = indice
            paleta.append(pixel)
        indices.append(indice)
    if mapa is not None:
        paleta.extend([(0, 0, 0, 0)] * (256 - len(paleta)))
        return b"".join(bytes(cor) for cor in paleta), bytes(indices)

    # Quantização determinística 3-3-2 para TGAs editados com mais de 256 cores.
    somas = [[0, 0, 0, 0, 0] for _ in range(256)]
    indices = bytearray()
    for b, g, r, a in pixels:
        indice = ((r >> 5) << 5) | ((g >> 5) << 2) | (b >> 6)
        indices.append(indice)
        item = somas[indice]
        item[0] += b; item[1] += g; item[2] += r; item[3] += a; item[4] += 1
    paleta = bytearray()
    for b, g, r, a, total in somas:
        if total:
            paleta.extend((b // total, g // total, r // total, a // total))
        else:
            paleta.extend((0, 0, 0, 0))
    return bytes(paleta), bytes(indices)



def _tamanho_dds_total(dados, offset=0):
    """Tamanho da textura DDS embutida; para formato desconhecido usa até EOF."""
    info = _analisar_dds(dados[offset:])
    if info["total_payload_size"] is None:
        return len(dados) - offset
    tamanho = info["header_size"] + info["total_payload_size"]
    if offset + tamanho > len(dados):
        raise ValueError("DDS embutido original está truncado")
    return tamanho


def _tamanho_tga_embutido(dados, offset):
    info = _validar_tga_embutido(dados, offset)
    if not info:
        raise ValueError("TGA embutido original possui estrutura inválida")
    return info["validated_end"] - offset


def _tamanho_payload_jt_original(original, tipo, offset):
    if tipo not in ("JT31", "JT33", "JT35"):
        raise ValueError(f"template {tipo} não é DXT simplificado")
    if offset + 12 > len(original):
        raise ValueError(f"JIT original {tipo} está truncado")
    largura, altura = struct.unpack_from("<II", original, offset + 4)
    if not (1 <= largura <= 16384 and 1 <= altura <= 16384):
        raise ValueError(f"JIT original {tipo} tem dimensões inválidas")
    bloco = 8 if tipo == "JT31" else 16
    tamanho = max(1, (largura + 3)//4) * max(1, (altura + 3)//4) * bloco
    if offset + 12 + tamanho > len(original):
        raise ValueError(f"JIT original {tipo} está truncado")
    return tamanho


def converter_dds_para_jit(caminho_dds, caminho_jit_original):
    """
    DDS -> JIT com a compatibilidade da V4 Original.

    Ponto principal da recuperação: JT31/JT33/JT35 são formatos de compressão
    da textura, não uma obrigação imutável do arquivo-alvo. Se um DDS editado
    está em DXT3 e o template atual está em JT35, o AutoMod converte o container
    para JT33 — exatamente como a versão publicada fazia — em vez de rejeitar.

    As proteções novas que não interferem na funcionalidade continuam:
    backup, destino seguro, escrita atômica e preservação da cauda do template.
    """
    dds_bytes = _ler_arquivo(caminho_dds)
    dds = _analisar_dds(dds_bytes)
    original = _ler_arquivo(caminho_jit_original)
    formato = detectar_formato_jit(original)
    tipo, offset = formato["tipo"], formato["offset"]

    # DDS nativo embutido: substitui o DDS completo e preserva eventual trailer
    # do JIT quando o tamanho original é calculável.
    if tipo == "DDS":
        tamanho_original = _tamanho_dds_total(original, offset)
        reconstruido = original[:offset] + dds_bytes + original[offset + tamanho_original:]
        formato = dict(formato)
        formato["tipo_resultante"] = "DDS"
        return reconstruido, formato, dds

    if tipo not in ("JT31", "JT33", "JT35"):
        raise ValueError(f"DDS não é compatível com o template {tipo}")

    if dds["jit_magic"] is None or dds["payload_all"] is None:
        nome = dds["source_fourcc"].decode("ascii", errors="replace")
        raise ValueError(
            f"DDS {nome} pode ser usado como DDS embutido, mas não pode ser convertido "
            "para JT31/JT33/JT35"
        )

    tamanho_original = _tamanho_payload_jt_original(original, tipo, offset)
    fim_original = offset + 12 + tamanho_original

    magic_resultante = dds["jit_magic"]
    tipo_resultante = magic_resultante.decode("ascii")

    # Mantém prefixo e cauda do JIT, mas deixa o DDS definir compressão,
    # dimensões e mipmaps/payload, como no pipeline estável.
    reconstruido = (
        original[:offset]
        + magic_resultante
        + struct.pack("<II", dds["width"], dds["height"])
        + dds["payload_all"]
        + original[fim_original:]
    )

    formato = dict(formato)
    formato["tipo_resultante"] = tipo_resultante
    formato["formato_alterado"] = tipo_resultante != tipo
    return reconstruido, formato, dds


def converter_tga_para_jit(caminho_tga, caminho_jit_original):
    """TGA -> JIT, aceitando também TGA RLE/paletizado gerado por editores."""
    tga_bytes = _ler_arquivo(caminho_tga)
    tga = _analisar_tga(tga_bytes)
    original = _ler_arquivo(caminho_jit_original)
    formato = detectar_formato_jit(original)
    tipo, offset = formato["tipo"], formato["offset"]

    if tipo == "TGA":
        tamanho_original = _tamanho_tga_embutido(original, offset)
        reconstruido = original[:offset] + tga_bytes + original[offset + tamanho_original:]
        formato = dict(formato)
        formato["tipo_resultante"] = "TGA"
        return reconstruido, formato, tga

    if tipo != "JT20":
        raise ValueError(f"TGA não é compatível com o template {tipo}")

    largura_original, altura_original = struct.unpack_from("<II", original, offset + 4)
    fim_original = offset + 12 + 1024 + largura_original * altura_original
    if fim_original > len(original):
        raise ValueError("JIT original JT20 está truncado")

    paleta, indices = _paletizar_bgra(tga["pixels"])
    reconstruido = (
        original[:offset]
        + b"JT20"
        + struct.pack("<II", tga["width"], tga["height"])
        + paleta
        + indices
        + original[fim_original:]
    )
    formato = dict(formato)
    formato["tipo_resultante"] = "JT20"
    return reconstruido, formato, tga


def preparar_textura_para_injecao(fonte, destino_original):
    ext_fonte = os.path.splitext(fonte)[1].lower()
    ext_destino = os.path.splitext(destino_original)[1].lower()
    if ext_fonte == ".dds" and ext_destino == ".jit":
        dados, formato, info = converter_dds_para_jit(fonte, destino_original)
        return dados, f"DDS -> {formato.get('tipo_resultante', formato['tipo'])}" + (f" (template {formato['tipo']})" if formato.get("formato_alterado") else ""), formato, info
    if ext_fonte == ".tga" and ext_destino == ".jit":
        dados, formato, info = converter_tga_para_jit(fonte, destino_original)
        return dados, f"TGA -> {formato.get('tipo_resultante', formato['tipo'])}", formato, info
    if ext_fonte != ext_destino:
        raise ValueError(f"formato fonte {ext_fonte} incompatível com destino {ext_destino}")
    dados = _ler_arquivo(fonte)
    if not dados:
        raise ValueError("arquivo fonte vazio")
    return dados, "COPY DIRETO", None, None


def _encontrar_destino(index, nome_base, ext_mod, pasta_jogo, fonte=None):
    candidatos = []
    for caminho in index.values():
        if not isinstance(caminho, str) or not os.path.isfile(caminho):
            continue
        nome, ext = os.path.splitext(os.path.basename(caminho).lower())
        if nome != nome_base:
            continue
        if ext_mod in (".dds", ".tga"):
            if ext != ".jit":
                continue
        elif ext != ext_mod:
            continue
        if _caminho_no_cliente(pasta_jogo, caminho):
            candidatos.append(os.path.abspath(caminho))
    candidatos = sorted(set(candidatos), key=lambda p: p.lower())
    if not candidatos:
        raise FileNotFoundError(f"basename '{nome_base}' não encontrado no cliente")
    if len(candidatos) > 1 and fonte:
        pasta_fonte = os.path.normcase(os.path.realpath(os.path.dirname(fonte)))
        mesma_pasta = [
            caminho for caminho in candidatos
            if os.path.normcase(os.path.realpath(os.path.dirname(caminho))) == pasta_fonte
        ]
        if len(mesma_pasta) == 1:
            return mesma_pasta[0]
    if len(candidatos) > 1:
        relativos = ", ".join(os.path.relpath(p, pasta_jogo) for p in candidatos[:5])
        raise ValueError(f"basename ambíguo ({len(candidatos)} destinos): {relativos}")
    return candidatos[0]


def _escrever_atomico_validado(destino, dados):
    modo_original = os.stat(destino).st_mode
    descritor, temporario = tempfile.mkstemp(
        prefix=os.path.basename(destino) + ".", suffix=".automod.tmp",
        dir=os.path.dirname(destino),
    )
    try:
        with os.fdopen(descritor, "wb") as f:
            f.write(dados)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temporario, modo_original)
        if os.path.getsize(temporario) != len(dados):
            raise OSError("tamanho temporário diverge do arquivo preparado")
        if _sha256_bytes(_ler_arquivo(temporario)) != _sha256_bytes(dados):
            raise OSError("hash temporário diverge do arquivo preparado")
        try:
            os.chmod(destino, stat.S_IWRITE)
        except OSError:
            pass
        os.replace(temporario, destino)
        os.chmod(destino, modo_original)
        if os.path.getsize(destino) != len(dados):
            raise OSError("tamanho final diverge do arquivo preparado")
        if _sha256_bytes(_ler_arquivo(destino)) != _sha256_bytes(dados):
            raise OSError("hash final diverge do arquivo preparado")
    finally:
        if os.path.exists(temporario):
            try:
                os.remove(temporario)
            except OSError:
                pass


def injetar_mods(lista_arquivos_mods, pasta_jogo=None, log_callback=None):
    pasta_jogo = _normalizar_pasta_jogo(pasta_jogo)
    if not pasta_jogo:
        _emitir_automod("[AutoMod][ERRO] Cliente do AIKA não configurado.", log_callback)
        return -1
    with lock_otimizacao:
        if not os.path.isdir(pasta_jogo):
            _emitir_automod(
                f"[AutoMod][ERRO] Pasta do cliente inexistente: {pasta_jogo}", log_callback
            )
            return -1
        index = carregar_index_jogo(pasta_jogo)
        if not index:
            _emitir_automod("[AutoMod][ERRO] Índice do cliente vazio.", log_callback)
            return -1
        arquivos_substituidos = 0
        for mod_caminho in lista_arquivos_mods or []:
            fonte = os.path.abspath(os.path.normpath(mod_caminho))
            nome_base, ext_mod = os.path.splitext(os.path.basename(fonte).lower())
            _emitir_automod(f"[AutoMod] Fonte: {fonte}", log_callback)
            _emitir_automod(f"[AutoMod] Formato fonte: {ext_mod or '(sem extensão)'}", log_callback)
            destino = None
            try:
                if not os.path.isfile(fonte):
                    raise FileNotFoundError("arquivo fonte inexistente")
                if ext_mod in (".meta", ".old", ".png", ".jpg", ".txt", ".ini"):
                    raise ValueError(f"extensão não injetável: {ext_mod}")
                try:
                    destino = _encontrar_destino(
                        index, nome_base, ext_mod, pasta_jogo, fonte
                    )
                except FileNotFoundError:
                    _emitir_automod(
                        "[AutoMod] Destino ausente no índice; atualizando cliente.",
                        log_callback,
                    )
                    if not criar_index_jogo(pasta_jogo):
                        raise OSError("não foi possível atualizar o índice do cliente")
                    index = carregar_index_jogo(pasta_jogo)
                    destino = _encontrar_destino(
                        index, nome_base, ext_mod, pasta_jogo, fonte
                    )
                _emitir_automod(f"[AutoMod] Destino encontrado: {destino}", log_callback)
                ext_destino = os.path.splitext(destino)[1].lower()
                _emitir_automod(f"[AutoMod] Formato destino: {ext_destino}", log_callback)
                if os.path.samefile(fonte, destino):
                    raise ValueError("fonte e destino são o mesmo arquivo")

                dados, operacao, formato, info = preparar_textura_para_injecao(fonte, destino)
                _emitir_automod(f"[AutoMod] Operação escolhida: {operacao}", log_callback)
                if formato:
                    _emitir_automod(
                        f"[AutoMod] JIT original: {formato['tipo']} (offset {formato['offset']})",
                        log_callback,
                    )
                if info and "width" in info:
                    detalhe = info.get("fourcc", b"")
                    if isinstance(detalhe, bytes):
                        detalhe = detalhe.decode("ascii", errors="replace")
                    _emitir_automod(
                        f"[AutoMod] Textura válida: {detalhe or ext_mod[1:].upper()} "
                        f"{info['width']}x{info['height']}", log_callback
                    )

                relativo = os.path.relpath(destino, pasta_jogo)
                caminho_backup = os.path.join(_paths_cliente(pasta_jogo)["backup"], relativo)
                backup_ok = os.path.isfile(caminho_backup) and os.path.getsize(caminho_backup) > 0
                if not backup_ok:
                    backup_ok = fazer_backup_rapido(destino, caminho_backup)
                _emitir_automod(
                    f"[AutoMod] Backup: {'OK - ' + caminho_backup if backup_ok else 'FALHOU'}",
                    log_callback,
                )
                if not backup_ok:
                    raise OSError("backup obrigatório falhou; destino não foi alterado")

                dados_anteriores = _ler_arquivo(destino)
                try:
                    _escrever_atomico_validado(destino, dados)
                    if not registrar_mod_ativo(destino, fonte, pasta_jogo):
                        raise OSError("não foi possível persistir o histórico")
                except Exception as erro_escrita:
                    try:
                        _escrever_atomico_validado(destino, dados_anteriores)
                    except Exception as erro_rollback:
                        raise OSError(
                            f"{erro_escrita}; rollback também falhou: {erro_rollback}"
                        ) from erro_rollback
                    raise OSError(
                        f"{erro_escrita}; estado anterior restaurado automaticamente"
                    ) from erro_escrita
                arquivos_substituidos += 1
                _emitir_automod("[AutoMod] Resultado: OK", log_callback)
            except Exception as e:
                alvo = destino or "não encontrado"
                _emitir_automod(
                    f"[AutoMod][ERRO] {os.path.basename(fonte)} -> {alvo}: {e}", log_callback
                )
                _emitir_automod("[AutoMod] Resultado: FALHOU", log_callback)
        return arquivos_substituidos

def remover_efeitos_pesados_aika(pasta_jogo=None):
    pasta_jogo = _normalizar_pasta_jogo(pasta_jogo)
    if not pasta_jogo:
        log("[ERRO] Cliente do AIKA não configurado para remoção de efeitos.")
        return -1
    with lock_otimizacao:
        try:
            efeitos_alvo = ["weaponeff3.bin", "skilleff.bin", "skilleff2.bin", "skilleff3.bin", "particle.bin", "particle2.bin", "glow.bin", "gloweffect.bin", "mageff.bin", "maguiceff.bin"]

            def _sha256_arquivo(caminho):
                import hashlib
                hash_obj = hashlib.sha256()
                with open(caminho, "rb") as arquivo:
                    for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
                        hash_obj.update(bloco)
                return hash_obj.hexdigest()

            raiz_jogo = os.path.normcase(
                os.path.realpath(os.path.abspath(pasta_jogo))
            )
            if not os.path.isdir(raiz_jogo):
                log(f"[ERRO] Pasta do jogo inválida para remoção de efeitos: {pasta_jogo}")
                return -1

            def _pertence_ao_jogo(caminho):
                try:
                    caminho_real = os.path.normcase(
                        os.path.realpath(os.path.abspath(caminho))
                    )
                    return os.path.commonpath(
                        [raiz_jogo, caminho_real]
                    ) == raiz_jogo
                except (OSError, ValueError):
                    return False

            pasta_efeitos = os.path.join(pasta_jogo, "Data", "Effect")
            if not os.path.exists(pasta_efeitos): pasta_efeitos = pasta_jogo

            # Fase 1: localiza o lote inteiro e valida todos os backups antes
            # que qualquer arquivo do cliente seja removido.
            alvos_encontrados = []
            for root, dirs, files in os.walk(pasta_efeitos):
                for file in files:
                    if file.lower() in efeitos_alvo:
                        caminho = os.path.realpath(os.path.join(root, file))
                        if not _pertence_ao_jogo(caminho):
                            log(f"[ERRO] Remoção de efeitos abortada: caminho fora da pasta do jogo: {caminho}")
                            return -1
                        try:
                            estado_original = os.stat(caminho, follow_symlinks=False)
                        except OSError as e:
                            log(f"[ERRO] Remoção de efeitos abortada: não foi possível validar {caminho}: {e}")
                            return -1
                        if not stat.S_ISREG(estado_original.st_mode):
                            log(f"[ERRO] Remoção de efeitos abortada: alvo não é arquivo regular: {caminho}")
                            return -1

                        relativo = os.path.relpath(caminho, raiz_jogo)
                        caminho_backup = os.path.join(_paths_cliente(pasta_jogo)["backup"], relativo)
                        backup_existia = os.path.lexists(caminho_backup)
                        if not backup_existia:
                            if not fazer_backup_rapido(caminho, caminho_backup):
                                log(f"[ERRO] Remoção de efeitos abortada: falha ao criar backup de {os.path.basename(caminho)}.")
                                return -1

                        try:
                            estado_backup = os.stat(
                                caminho_backup, follow_symlinks=False
                            )
                            if not stat.S_ISREG(estado_backup.st_mode):
                                raise ValueError("backup não é um arquivo regular")
                            if estado_backup.st_size <= 0:
                                raise ValueError("backup está vazio")
                            if estado_backup.st_size != estado_original.st_size:
                                raise ValueError(
                                    "tamanho do backup difere do arquivo atual"
                                )
                            hash_original = _sha256_arquivo(caminho)
                            hash_backup = _sha256_arquivo(caminho_backup)
                            if hash_backup != hash_original:
                                raise ValueError(
                                    "SHA-256 do backup difere do arquivo atual"
                                )
                        except Exception as e:
                            origem_backup = "existente" if backup_existia else "recém-criado"
                            log(
                                f"[ERRO] Remoção de efeitos abortada: backup {origem_backup} "
                                f"de {os.path.basename(caminho)} é inválido ({e}). "
                                "O backup não foi sobrescrito e nenhum efeito foi removido."
                            )
                            return -1

                        alvos_encontrados.append({
                            "caminho": caminho,
                            "backup": caminho_backup,
                            "tamanho": estado_original.st_size,
                            "hash": hash_original,
                            "modo": estado_original.st_mode,
                        })

            if not alvos_encontrados:
                pasta_backup_efeitos = os.path.join(_paths_cliente(pasta_jogo)["backup"], "Data", "Effect")
                if os.path.exists(pasta_backup_efeitos):
                    backups_feitos = [f.lower() for f in os.listdir(pasta_backup_efeitos)]
                    if any(efeito in backups_feitos for efeito in efeitos_alvo):
                        return 2
                return 0

            # Fase 2: todos os backups do lote já foram validados. Qualquer
            # falha de remoção restaura atomicamente os itens removidos aqui.
            removidos = []
            try:
                for item in alvos_encontrados:
                    caminho = item["caminho"]
                    caminho_backup = item["backup"]

                    # Revalida imediatamente antes da remoção para detectar
                    # alterações externas ocorridas após a pré-validação.
                    if (
                        not os.path.isfile(caminho)
                        or os.path.getsize(caminho) != item["tamanho"]
                        or _sha256_arquivo(caminho) != item["hash"]
                        or not os.path.isfile(caminho_backup)
                        or os.path.getsize(caminho_backup) != item["tamanho"]
                        or _sha256_arquivo(caminho_backup) != item["hash"]
                    ):
                        raise RuntimeError(
                            f"arquivo ou backup mudou após a pré-validação: {os.path.basename(caminho)}"
                        )

                    os.chmod(caminho, stat.S_IWRITE)
                    try:
                        os.remove(caminho)
                    except Exception:
                        if os.path.exists(caminho):
                            try:
                                os.chmod(caminho, item["modo"])
                            except OSError:
                                pass
                        raise
                    removidos.append(item)
                log(f"[AUTOMOD] {len(removidos)} arquivo(s) de efeitos removido(s) com backup validado.")
                return 1
            except Exception as erro_remocao:
                log(f"[ERRO] Falha ao remover efeitos: {erro_remocao}. Iniciando rollback dos arquivos já removidos.")
                rollback_falhou = False
                for item in reversed(removidos):
                    caminho = item["caminho"]
                    temporario = None
                    try:
                        import tempfile
                        descritor, temporario = tempfile.mkstemp(
                            prefix=f".{os.path.basename(caminho)}.",
                            suffix=".aika_rollback.tmp",
                            dir=os.path.dirname(caminho),
                        )
                        os.close(descritor)
                        shutil.copyfile(item["backup"], temporario)
                        os.chmod(temporario, item["modo"])
                        if (
                            os.path.getsize(temporario) != item["tamanho"]
                            or _sha256_arquivo(temporario) != item["hash"]
                        ):
                            raise ValueError("arquivo temporário de rollback não confere")
                        os.replace(temporario, caminho)
                        temporario = None
                        if (
                            not os.path.isfile(caminho)
                            or os.path.getsize(caminho) != item["tamanho"]
                            or _sha256_arquivo(caminho) != item["hash"]
                        ):
                            raise ValueError("arquivo restaurado não confere")
                    except Exception as erro_rollback:
                        rollback_falhou = True
                        log(f"[ERRO] Rollback falhou para {caminho}: {erro_rollback}")
                    finally:
                        if temporario and os.path.exists(temporario):
                            try:
                                os.remove(temporario)
                            except OSError:
                                pass

                if rollback_falhou:
                    log("[ERRO] Rollback incompleto: um ou mais efeitos não foram restaurados corretamente.")
                else:
                    log("[OK] Rollback concluído: todos os efeitos removidos nesta operação foram restaurados e validados.")
                return -1
        except Exception as e:
            log(f"[ERRO] Remoção de efeitos abortada: {e}")
            return -1

# ========================================================
# HISTÓRICO DE MODIFICAÇÕES ATIVAS (AUTOMOD)
# ========================================================
_historico_lock = threading.Lock()

def _chave_destino(destino, pasta_jogo=None):
    pasta_jogo = _normalizar_pasta_jogo(pasta_jogo)
    """Chave única normalizada (relpath lowercase com separadores '/')."""
    if not pasta_jogo:
        return destino.replace("\\", "/").lower()
    try:
        rel = os.path.relpath(destino, pasta_jogo)
    except Exception:
        rel = destino
    return rel.replace("\\", "/").lower()

def carregar_historico_automod(pasta_jogo=None):
    """Histórico isolado por cliente. Retorna schema seguro vazio se ausente/corrompido."""
    pasta_jogo = _normalizar_pasta_jogo(pasta_jogo)
    if not pasta_jogo:
        return {"version": 2, "game_root": "", "items": {}}
    arquivo = _paths_cliente(pasta_jogo)["history"]
    vazio = {"version": 2, "game_root": pasta_jogo, "items": {}}
    if not os.path.exists(arquivo):
        return vazio
    try:
        with open(arquivo, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if not isinstance(dados, dict) or not isinstance(dados.get("items"), dict):
            return vazio
        if os.path.normcase(_normalizar_pasta_jogo(dados.get("game_root") or pasta_jogo)) != os.path.normcase(pasta_jogo):
            log("[AUTOMOD] Histórico pertence a outro cliente; ignorado com segurança.")
            return vazio
        dados["version"] = 2
        dados["game_root"] = pasta_jogo
        return dados
    except Exception as e:
        log(f"[AUTOMOD] Histórico ilegível (estado seguro): {e}")
        return vazio


def salvar_historico_automod(dados, pasta_jogo=None):
    pasta_jogo = _normalizar_pasta_jogo(pasta_jogo or dados.get("game_root"))
    if not pasta_jogo:
        return False
    arquivo = _paths_cliente(pasta_jogo)["history"]
    try:
        dados = dict(dados)
        dados["version"] = 2; dados["game_root"] = pasta_jogo
        tmp = arquivo + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=2)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, arquivo)
        return True
    except Exception as e:
        log(f"[AUTOMOD] Erro ao salvar histórico: {e}")
        return False


def listar_mods_ativos(pasta_jogo=None):
    dados = carregar_historico_automod(pasta_jogo)
    itens = []
    for chave, item in dados.get("items", {}).items():
        copia = dict(item); copia["chave"] = chave; itens.append(copia)
    return itens


def registrar_mod_ativo(destino, mod_caminho, pasta_jogo=None, mod_nome=None, categoria=None):
    pasta_jogo = _normalizar_pasta_jogo(pasta_jogo)
    if not pasta_jogo:
        return False
    with _historico_lock:
        dados = carregar_historico_automod(pasta_jogo)
        chave = _chave_destino(destino, pasta_jogo)
        rel = os.path.relpath(destino, pasta_jogo).replace("\\", "/")
        item = dados["items"].setdefault(chave, {})
        item.update({
            "target_relpath": rel,
            "target_name": os.path.basename(destino),
            "mod_name": mod_nome or os.path.basename(mod_caminho),
            "backup_relpath": rel,
            "game_root": pasta_jogo,
            "last_applied": time.strftime("%Y-%m-%d %H:%M:%S"),
            "injection_count": item.get("injection_count", 0) + 1,
        })
        if categoria: item["category"] = categoria
        return salvar_historico_automod(dados, pasta_jogo)


def restaurar_mod_individual(chave_mod, pasta_jogo=None):
    pasta_jogo = _normalizar_pasta_jogo(pasta_jogo)
    if not pasta_jogo:
        return False, "Cliente do AIKA não configurado."
    with lock_otimizacao:
        with _historico_lock:
            dados = carregar_historico_automod(pasta_jogo)
            item = dados.get("items", {}).get(chave_mod)
            if item is None: return False, "Item não encontrado no histórico."
            target_rel = item.get("target_relpath") or item.get("backup_relpath")
            if not target_rel: return False, "Caminho relativo ausente no histórico."
            destino = os.path.join(pasta_jogo, target_rel.replace("/", os.sep))
            caminho_backup = os.path.join(_paths_cliente(pasta_jogo)["backup"], target_rel.replace("/", os.sep))
            nome = item.get("target_name") or os.path.basename(destino)
            if not _caminho_no_cliente(pasta_jogo, destino): return False, "Destino fora da pasta do jogo (bloqueado)."
            if not os.path.isfile(caminho_backup): return False, "Backup original não encontrado."
            try:
                dados_backup = _ler_arquivo(caminho_backup)
                dados_antes_restore = _ler_arquivo(destino) if os.path.isfile(destino) else None
                _escrever_atomico_validado(destino, dados_backup)
            except Exception as e:
                return False, f"Não foi possível restaurar {nome}: {e}"
            historico_antes = json.loads(json.dumps(dados))
            del dados["items"][chave_mod]
            if not salvar_historico_automod(dados, pasta_jogo):
                # Histórico faz parte da transação: volta o arquivo ao estado modificado.
                if dados_antes_restore is not None:
                    try:
                        _escrever_atomico_validado(destino, dados_antes_restore)
                    except Exception as rollback_e:
                        return False, f"Histórico falhou e rollback do arquivo também falhou: {rollback_e}"
                salvar_historico_automod(historico_antes, pasta_jogo)
                return False, f"{nome} não foi restaurado porque o histórico não pôde ser persistido; rollback aplicado."
            return True, f"{nome} restaurado para o original."


def limpar_historico_automod(pasta_jogo=None):
    pasta_jogo = _normalizar_pasta_jogo(pasta_jogo)
    if not pasta_jogo:
        return False
    with _historico_lock:
        return salvar_historico_automod({"version": 2, "game_root": pasta_jogo, "items": {}}, pasta_jogo)


def restaurar_mods_selecionados(chaves, pasta_jogo=None):
    pasta_jogo = _normalizar_pasta_jogo(pasta_jogo)
    if not pasta_jogo:
        return {"restaurados": [], "falhas": []}
    restaurados, falhas = [], []
    for chave in chaves:
        dados = carregar_historico_automod(pasta_jogo)
        item = dados.get("items", {}).get(chave)
        nome = (item or {}).get("target_name") or chave
        ok, msg = restaurar_mod_individual(chave, pasta_jogo)
        if ok: restaurados.append(nome)
        else: falhas.append((nome, msg))
    return {"restaurados": restaurados, "falhas": falhas}
