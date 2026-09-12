import os
import struct

from config import *


# Constantes DX9 para criar DDS.
DDSD_CAPS = 0x1
DDSD_HEIGHT = 0x2
DDSD_WIDTH = 0x4
DDSD_PITCH = 0x8
DDSD_PIXELFORMAT = 0x1000
DDSD_MIPMAPCOUNT = 0x20000
DDSD_LINEARSIZE = 0x80000
DDSCAPS_COMPLEX = 0x8
DDSCAPS_TEXTURE = 0x1000
DDSCAPS_MIPMAP = 0x400000
DDPF_FOURCC = 0x4


_DXT_INFO = {
    b"JT31": (b"DXT1", 8),
    b"JT33": (b"DXT3", 16),
    b"JT35": (b"DXT5", 16),
}


def build_dds_header(width, height, fourcc, mipmaps, linear_size):
    header = bytearray(128)
    header[0:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)

    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_LINEARSIZE
    if mipmaps > 1:
        flags |= DDSD_MIPMAPCOUNT

    struct.pack_into("<I", header, 8, flags)
    struct.pack_into("<I", header, 12, height)
    struct.pack_into("<I", header, 16, width)
    struct.pack_into("<I", header, 20, linear_size)
    struct.pack_into("<I", header, 24, 0)
    struct.pack_into("<I", header, 28, mipmaps)
    struct.pack_into("<I", header, 76, 32)
    struct.pack_into("<I", header, 80, DDPF_FOURCC)
    header[84:88] = fourcc

    caps = DDSCAPS_TEXTURE
    if mipmaps > 1:
        caps |= DDSCAPS_COMPLEX | DDSCAPS_MIPMAP
    struct.pack_into("<I", header, 108, caps)
    return bytes(header)


def _escrever_atomico(caminho, conteudo):
    """Evita deixar DDS/TGA parcial caso a escrita falhe."""
    tmp = caminho + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(conteudo)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, caminho)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def _ocorrencias(data, magic):
    """Retorna todas as ocorrências da assinatura, não só a primeira."""
    inicio = 0
    while True:
        offset = data.find(magic, inicio)
        if offset < 0:
            return
        yield offset
        inicio = offset + 1


def _dimensoes_validas(width, height, max_dim=8192):
    # Existem texturas reais muito estreitas (ex.: 2x256).
    return 1 <= width <= max_dim and 1 <= height <= max_dim


def _validar_jt_dxt(data, offset, magic):
    if offset + 12 > len(data):
        return None, "cabeçalho incompleto"

    width, height = struct.unpack_from("<II", data, offset + 4)
    if not _dimensoes_validas(width, height):
        return None, f"dimensões inválidas ({width}x{height})"

    fourcc, block_size = _DXT_INFO[magic]
    payload_size = max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * block_size
    payload_start = offset + 12
    payload_end = payload_start + payload_size
    if payload_end > len(data):
        return None, (
            f"payload insuficiente: precisa {payload_size} bytes, "
            f"há {max(0, len(data) - payload_start)}"
        )

    return {
        "tipo": magic.decode("ascii"),
        "offset": offset,
        "width": width,
        "height": height,
        "fourcc": fourcc,
        "payload_start": payload_start,
        "payload_end": payload_end,
        "payload_size": payload_size,
    }, None


def _validar_jt20(data, offset):
    if offset + 12 > len(data):
        return None, "cabeçalho incompleto"

    width, height = struct.unpack_from("<II", data, offset + 4)
    if not _dimensoes_validas(width, height):
        return None, f"dimensões inválidas ({width}x{height})"

    palette_start = offset + 12
    palette_end = palette_start + 1024
    indices_end = palette_end + width * height

    if palette_end > len(data):
        return None, "paleta incompleta"
    if indices_end > len(data):
        return None, (
            f"índices insuficientes: precisa {width * height} bytes, "
            f"há {max(0, len(data) - palette_end)}"
        )

    return {
        "tipo": "JT20",
        "offset": offset,
        "width": width,
        "height": height,
        "palette_start": palette_start,
        "palette_end": palette_end,
        "indices_start": palette_end,
        "indices_end": indices_end,
    }, None


def _validar_dds_embutido(data, offset):
    """
    Mantém a tolerância da versão estável: qualquer DDS com header plausível
    pode ser extraído. A validação evita confundir uma string 'DDS ' aleatória.
    """
    if offset + 128 > len(data):
        return None, "header DDS incompleto"
    if data[offset:offset + 4] != b"DDS ":
        return None, "magic DDS ausente"
    if struct.unpack_from("<I", data, offset + 4)[0] != 124:
        return None, "dwSize DDS inválido"
    if struct.unpack_from("<I", data, offset + 76)[0] != 32:
        return None, "pixel format DDS inválido"

    height = struct.unpack_from("<I", data, offset + 12)[0]
    width = struct.unpack_from("<I", data, offset + 16)[0]
    if not _dimensoes_validas(width, height, 16384):
        return None, f"dimensões DDS inválidas ({width}x{height})"

    return {
        "tipo": "DDS",
        "offset": offset,
        "width": width,
        "height": height,
        "fourcc": data[offset + 84:offset + 88],
    }, None


def _tga_header(data, offset=0):
    if offset + 18 > len(data):
        return None
    id_len = data[offset]
    cmap_type = data[offset + 1]
    image_type = data[offset + 2]
    cmap_first = struct.unpack_from("<H", data, offset + 3)[0]
    cmap_len = struct.unpack_from("<H", data, offset + 5)[0]
    cmap_bpp = data[offset + 7]
    width, height = struct.unpack_from("<HH", data, offset + 12)
    bpp = data[offset + 16]
    descriptor = data[offset + 17]

    if image_type not in (1, 2, 3, 9, 10, 11):
        return None
    if cmap_type not in (0, 1):
        return None
    if not _dimensoes_validas(width, height, 4096):
        return None
    if bpp not in (8, 15, 16, 24, 32):
        return None
    if cmap_type and cmap_bpp not in (8, 15, 16, 24, 32):
        return None

    return {
        "offset": offset,
        "id_len": id_len,
        "cmap_type": cmap_type,
        "image_type": image_type,
        "cmap_first": cmap_first,
        "cmap_len": cmap_len,
        "cmap_bpp": cmap_bpp,
        "width": width,
        "height": height,
        "bpp": bpp,
        "descriptor": descriptor,
    }


def _validar_tga_embutido(data, offset):
    """Valida também TGA RLE/paletizado usado por arquivos antigos."""
    info = _tga_header(data, offset)
    if not info:
        return None

    cursor = offset + 18 + info["id_len"]
    if cursor > len(data):
        return None

    if info["cmap_type"]:
        cmap_entry_bytes = (info["cmap_bpp"] + 7) // 8
        cursor += info["cmap_len"] * cmap_entry_bytes
        if cursor > len(data):
            return None

    pixel_bytes = (info["bpp"] + 7) // 8
    total_pixels = info["width"] * info["height"]

    if info["image_type"] in (1, 2, 3):
        end = cursor + total_pixels * pixel_bytes
        if end > len(data):
            return None
    else:
        produced = 0
        while produced < total_pixels:
            if cursor >= len(data):
                return None
            packet = data[cursor]
            cursor += 1
            count = (packet & 0x7F) + 1
            if produced + count > total_pixels:
                return None
            cursor += pixel_bytes if packet & 0x80 else count * pixel_bytes
            if cursor > len(data):
                return None
            produced += count
        end = cursor

    info = dict(info)
    info["tipo"] = "TGA"
    info["validated_end"] = end
    return info


def detectar_textura_jit_bytes(data):
    """
    Detector único usado por extração e AutoMod.

    Regra de compatibilidade:
    - uma assinatura encontrada NÃO é aceita automaticamente;
    - candidato estruturalmente inválido é ignorado;
    - continua procurando outras ocorrências e outros formatos;
    - escolhe o candidato válido de menor offset.

    Isso recupera a tolerância da V4 estável sem voltar a aceitar arquivo
    truncado como sucesso.
    """
    validos = []
    rejeitados = []

    for magic in (b"JT31", b"JT33", b"JT35"):
        for offset in _ocorrencias(data, magic):
            info, motivo = _validar_jt_dxt(data, offset, magic)
            if info:
                validos.append(info)
            else:
                rejeitados.append((offset, magic.decode("ascii"), motivo))

    for offset in _ocorrencias(data, b"JT20"):
        info, motivo = _validar_jt20(data, offset)
        if info:
            validos.append(info)
        else:
            rejeitados.append((offset, "JT20", motivo))

    for offset in _ocorrencias(data, b"DDS "):
        info, motivo = _validar_dds_embutido(data, offset)
        if info:
            validos.append(info)
        else:
            rejeitados.append((offset, "DDS", motivo))

    if validos:
        validos.sort(key=lambda item: item["offset"])
        escolhido = dict(validos[0])
        escolhido["rejeitados"] = rejeitados
        return escolhido

    limite = max(0, min(8192, len(data) - 18))
    for offset in range(limite + 1):
        tga = _validar_tga_embutido(data, offset)
        if tga:
            tga = dict(tga)
            tga["rejeitados"] = rejeitados
            return tga

    if rejeitados:
        resumo = "; ".join(
            f"{tipo}@0x{offset:X}: {motivo}"
            for offset, tipo, motivo in rejeitados[:6]
        )
        raise ValueError(
            "Nenhuma textura estruturalmente válida encontrada. "
            f"Candidatos rejeitados: {resumo}"
        )

    raise ValueError("Nenhuma textura válida (DDS/JT/TGA) encontrada no arquivo.")


def extrair_textura_jit(caminho_jit):
    """Extrai JIT -> DDS/TGA mantendo compatibilidade com a V4 estável."""
    try:
        if not os.path.isfile(caminho_jit) or os.path.getsize(caminho_jit) < 18:
            return False, "Arquivo JIT inválido ou muito pequeno."

        with open(caminho_jit, "rb") as f:
            data = f.read()

        base = os.path.splitext(caminho_jit)[0]
        try:
            candidato = detectar_textura_jit_bytes(data)
        except ValueError as e:
            return False, str(e)

        tipo = candidato["tipo"]
        offset = candidato["offset"]

        if tipo in ("JT31", "JT33", "JT35"):
            payload = data[candidato["payload_start"]:candidato["payload_end"]]
            header = build_dds_header(
                candidato["width"],
                candidato["height"],
                candidato["fourcc"],
                1,
                candidato["payload_size"],
            )
            out = base + ".dds"
            _escrever_atomico(out, header + payload)
            return True, (
                f"Extraído {tipo} -> DDS "
                f"({candidato['width']}x{candidato['height']})."
            )

        if tipo == "JT20":
            palette = data[candidato["palette_start"]:candidato["palette_end"]]
            indices = data[candidato["indices_start"]:candidato["indices_end"]]
            rgba = bytearray()
            for idx in indices:
                pos = idx * 4
                rgba.extend(palette[pos:pos + 4])

            tga = bytearray(18)
            tga[2] = 2
            struct.pack_into("<H", tga, 12, candidato["width"])
            struct.pack_into("<H", tga, 14, candidato["height"])
            tga[16] = 32
            tga[17] = 0x28
            out = base + ".tga"
            _escrever_atomico(out, bytes(tga) + bytes(rgba))
            return True, (
                f"Extraído JT20 -> TGA "
                f"({candidato['width']}x{candidato['height']})."
            )

        if tipo == "DDS":
            # Comportamento da versão estável: entrega o DDS nativo a partir
            # do magic até EOF. Isso preserva formatos/mipmaps não DXT também.
            out = base + ".dds"
            _escrever_atomico(out, data[offset:])
            return True, (
                f"DDS embutido extraído "
                f"({candidato['width']}x{candidato['height']})."
            )

        if tipo == "TGA":
            # Também preserva trailer/footer quando existe, como a V4 estável.
            out = base + ".tga"
            _escrever_atomico(out, data[offset:])
            return True, (
                f"TGA embutido extraído "
                f"({candidato['width']}x{candidato['height']}, "
                f"tipo {candidato['image_type']}, {candidato['bpp']} bpp)."
            )

        return False, "Formato de textura JIT não reconhecido."

    except Exception as e:
        return False, f"Erro ao extrair textura: {e}"
