# -*- coding: utf-8 -*-
# =============================================================================
# EXTRACTOR_SETS.PY — BACKEND PURO: Organizador de Sets do AIKA
# =============================================================================
# Extrai lógica de listadeset.py, removendo 100% de customtkinter/tkinter.
# Funções puras: build_dds_header, extrair_textura_jit, convert_msh_to_obj,
# organizar_e_converter_aika (com callback de progresso).
# =============================================================================

import os
import shutil
import struct
import time


# =============================================================================
# CONSTANTES DDS
# =============================================================================
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


# =============================================================================
# 1. MOTOR DE TEXTURAS (JIT -> DDS/TGA)
# =============================================================================
def build_dds_header(width, height, fourcc, mipmaps, linear_size):
    """Constrói um cabeçalho DDS de 128 bytes padrão."""
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

def extrair_textura_jit(caminho_jit):
    """
    Extrai textura de um arquivo .JIT e salva como .DDS ou .TGA.
    Retorna (sucesso: bool, mensagem: str).
    """
    try:
        if not os.path.exists(caminho_jit) or os.path.getsize(caminho_jit) < 24:
            return False, "Arquivo inválido."

        with open(caminho_jit, "rb") as f:
            data = f.read()

        base = os.path.splitext(caminho_jit)[0]
        achados = []
        for magic in [b'DDS ', b'JT31', b'JT33', b'JT35', b'JT20']:
            off = data.find(magic)
            if off != -1:
                if magic == b'DDS ':
                    achados.append((off, "DDS"))
                else:
                    if off + 12 <= len(data):
                        w = struct.unpack("<I", data[off + 4 : off + 8])[0]
                        h = struct.unpack("<I", data[off + 8 : off + 12])[0]
                        if 8 <= w <= 8192 and 8 <= h <= 8192:
                            achados.append((off, magic.decode()))

        if achados:
            achados.sort(key=lambda x: x[0])
            offset, tipo = achados[0]

            if tipo in ["JT31", "JT33", "JT35"]:
                width = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
                height = struct.unpack("<I", data[offset + 8 : offset + 12])[0]
                fourcc_map = {
                    "JT31": (b"DXT1", 8),
                    "JT33": (b"DXT3", 16),
                    "JT35": (b"DXT5", 16),
                }
                fourcc, block_size = fourcc_map[tipo]
                blocks_x = max(1, (width + 3) // 4)
                blocks_y = max(1, (height + 3) // 4)
                base_size = blocks_x * blocks_y * block_size
                payload = data[offset + 12 : offset + 12 + base_size]
                dds_hdr = build_dds_header(width, height, fourcc, 1, base_size)
                out = base + ".dds"
                with open(out, "wb") as f:
                    f.write(dds_hdr)
                    f.write(payload)
                return True, ""

            elif tipo == "JT20":
                width = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
                height = struct.unpack("<I", data[offset + 8 : offset + 12])[0]
                size_pixels = width * height
                palette = data[offset + 12 : offset + 12 + 1024]
                pixels = data[offset + 12 + 1024 : offset + 12 + 1024 + size_pixels]
                rgba = bytearray()
                for idx in pixels:
                    if idx * 4 + 3 < len(palette):
                        b = palette[idx * 4]
                        g = palette[idx * 4 + 1]
                        r = palette[idx * 4 + 2]
                        a = palette[idx * 4 + 3]
                    else:
                        b, g, r, a = 0, 0, 0, 0
                    rgba.extend([b, g, r, a])
                tga = bytearray(18)
                tga[2] = 2
                struct.pack_into("<H", tga, 12, width)
                struct.pack_into("<H", tga, 14, height)
                tga[16], tga[17] = 32, 0x28
                out = base + ".tga"
                with open(out, "wb") as f:
                    f.write(tga)
                    f.write(rgba)
                return True, ""

            elif tipo == "DDS":
                out = base + ".dds"
                payload = data[offset:]
                with open(out, "wb") as f:
                    f.write(payload)
                return True, ""

        # Fallback: procura TGA raw
        offset_tga = -1
        for off in range(min(8192, len(data) - 18)):
            img_type = data[off + 2]
            if img_type in [1, 2, 3, 9, 10, 11]:
                bpp = data[off + 16]
                if bpp in [8, 15, 16, 24, 32]:
                    w = struct.unpack("<H", data[off + 12 : off + 14])[0]
                    h = struct.unpack("<H", data[off + 14 : off + 16])[0]
                    if 8 <= w <= 4096 and 8 <= h <= 4096:
                        offset_tga = off
                        break
        if offset_tga != -1:
            payload = data[offset_tga:]
            out = base + ".tga"
            with open(out, "wb") as f:
                f.write(payload)
            return True, ""

        return False, "Formato não suportado."
    except Exception as e:
        return False, str(e)
# =============================================================================
# 2. MOTOR DE GEOMETRIA (MSH -> OBJ)
# =============================================================================
def convert_msh_to_obj(input_file):
    """
    Converte um arquivo .MSH para Wavefront .OBJ.
    Retorna (sucesso: bool, mensagem: str).
    """
    try:
        output_file = os.path.splitext(input_file)[0] + ".obj"
        with open(input_file, 'rb') as f:
            header_data = f.read(36)
            if len(header_data) < 36:
                raise ValueError("Arquivo inválido.")

            vals = struct.unpack('<9I', header_data)
            unk01, unk02, unk03, count01 = vals[0:4]
            vert_size = vals[4]
            unk06 = vals[5]
            bone_count = vals[6]
            vert_count = vals[7]
            face_count = vals[8]

            f.seek((0x40 * bone_count) + (4 * bone_count), 1)
            vertices = []
            uvs = []

            for _ in range(vert_count):
                vx, vy, vz = struct.unpack('<3f', f.read(12))
                vertices.append((vx, vy, vz))
                if vert_size == 0x24:
                    f.seek(16, 1)
                elif vert_size == 0x28:
                    f.seek(20, 1)
                elif vert_size == 0x2C:
                    f.seek(24, 1)
                else:
                    f.seek(vert_size - 20, 1)

                tu, tv = struct.unpack('<2f', f.read(8))
                uvs.append((tu, -tv))

            faces = []
            for _ in range(face_count // 3):
                f1, f2, f3 = struct.unpack('<3H', f.read(6))
                faces.append((f1 + 1, f2 + 1, f3 + 1))

        with open(output_file, 'w') as out:
            out.write("# Convertido pelo AIKA Optimizer V4.0\n")
            out.write(f"# {len(vertices)} vértices, {len(faces)} faces\n\n")
            for v in vertices:
                out.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
            for uv in uvs:
                out.write(f"vt {uv[0]:.6f} {uv[1]:.6f}\n")
            for face in faces:
                out.write(
                    f"f {face[0]}/{face[0]} "
                    f"{face[1]}/{face[1]} "
                    f"{face[2]}/{face[2]}\n"
                )

        return True, ""
    except Exception as e:
        return False, str(e)
# =============================================================================
# 3. COR DO PROGRESSO (UTILITÁRIO)
# =============================================================================
def calcular_cor_progresso(porcentagem):
    """
    Retorna uma cor hexadecimal baseada no progresso (0.0 a 1.0).
    Vai de vermelho -> amarelo -> verde.
    """
    if porcentagem <= 0.5:
        p = porcentagem * 2
        r = 255
        g = int(50 + (150 * p))
        b = 50
    else:
        p = (porcentagem - 0.5) * 2
        r = int(255 - (255 * p))
        g = 200
        b = 50
    return f"#{r:02x}{g:02x}{b:02x}"


# =============================================================================
# 4. MOTOR PRINCIPAL DE ORGANIZAÇÃO E CONVERSÃO
# =============================================================================
def organizar_e_converter_aika(diretorio_origem, diretorio_destino,
                                modo_seguro, extrair_3d, extrair_tex,
                                progress_callback=None, cancel_callback=None):
    """
    Percorre o diretório de origem, organiza arquivos por classes/sets
    e opcionalmente converte .msh -> .obj e extrai .jit -> .dds/.tga.

    Parâmetros:
        diretorio_origem  (str): Pasta com os arquivos do jogo.
        diretorio_destino (str): Pasta de destino organizada.
        modo_seguro       (bool): Adiciona sleep(0.01) entre iterações.
        extrair_3d        (bool): Converte .msh para .obj.
        extrair_tex       (bool): Extrai texturas de .jit.
        progress_callback (callable): Chamada com (porcentagem: float, texto: str).

    Retorna:
        dict com chaves: copiados, msh_convertidos, jit_extraidos, erro (opcional).
    """
    stats = {"copiados": 0, "msh_convertidos": 0, "jit_extraidos": 0}

    def _cancelado():
        if cancel_callback is None:
            return False
        try:
            return bool(cancel_callback())
        except Exception:
            return False

    try:
        if not os.path.exists(diretorio_destino):
            os.makedirs(diretorio_destino)

        mapa_armaduras = {
            "01": "Guerreiro", "02": "Templaria", "03": "Atirador",
            "04": "Dual", "05": "FC", "06": "Cleriga"
        }
        mapa_armas = {
            "FM": "Guerreiro", "FF": "Templaria", "SM": "Atirador",
            "SF": "Dual", "MM": "FC", "MF": "Cleriga"
        }
        pecas_do_set = ["03", "04", "05", "06", "07", "08"]

        if progress_callback:
            progress_callback(0.0, "Mapeando arquivos... aguarde.")

        lista_arquivos = []
        for raiz, diretorios, arquivos in os.walk(diretorio_origem):
            if _cancelado():
                stats["cancelado"] = True
                return stats
            for arquivo in arquivos:
                if _cancelado():
                    stats["cancelado"] = True
                    return stats
                lista_arquivos.append((raiz, arquivo))

        total_arquivos = len(lista_arquivos)
        if total_arquivos == 0:
            stats["erro"] = "Nenhum arquivo encontrado na pasta de origem!"
            return stats

        for index, (raiz, arquivo) in enumerate(lista_arquivos):
            if _cancelado():
                stats["cancelado"] = True
                break
            nome_base, extensao = os.path.splitext(arquivo)
            extensao = extensao.lower()
            caminho_pasta_item = None

            # Armaduras (CH prefixo)
            if nome_base.upper().startswith('CH') and len(nome_base) >= 10:
                classe_id = nome_base[2:4]
                parte_id = nome_base[4:6]
                set_id = nome_base[6:10]
                if classe_id in mapa_armaduras and parte_id in pecas_do_set:
                    caminho_pasta_item = os.path.join(
                        diretorio_destino,
                        mapa_armaduras[classe_id],
                        f"Set_Armadura_{set_id}"
                    )

            # Armas
            prefixo_arma = nome_base[:2].upper()
            if prefixo_arma in mapa_armas and len(nome_base) >= 10:
                tipo_arma = nome_base[2:5]
                id_arma = nome_base[5:10]
                caminho_pasta_item = os.path.join(
                    diretorio_destino,
                    mapa_armas[prefixo_arma],
                    "Armas",
                    f"{tipo_arma}_{id_arma}"
                )

            if caminho_pasta_item:
                subpasta = ""
                if extensao in ['.msh', '.obj']:
                    subpasta = "Mesh"
                elif extensao == '.jit':
                    subpasta = "Texture"
                elif extensao == '.ms3':
                    subpasta = "Objects"

                if subpasta:
                    caminho_final = os.path.join(caminho_pasta_item, subpasta)
                    if not os.path.exists(caminho_final):
                        os.makedirs(caminho_final)

                    origem = os.path.join(raiz, arquivo)
                    destino = os.path.join(caminho_final, arquivo)

                    if not os.path.exists(destino):
                        shutil.copy2(origem, destino)
                        stats["copiados"] += 1

                    if extensao == '.msh' and extrair_3d:
                        caminho_obj = os.path.splitext(destino)[0] + ".obj"
                        if not os.path.exists(caminho_obj):
                            sucesso, msg = convert_msh_to_obj(destino)
                            if sucesso:
                                stats["msh_convertidos"] += 1

                    elif extensao == '.jit' and extrair_tex:
                        caminho_dds = os.path.splitext(destino)[0] + ".dds"
                        caminho_tga = os.path.splitext(destino)[0] + ".tga"
                        if (not os.path.exists(caminho_dds) and
                                not os.path.exists(caminho_tga)):
                            sucesso, msg = extrair_textura_jit(destino)
                            if sucesso:
                                stats["jit_extraidos"] += 1

            porcentagem = (index + 1) / total_arquivos
            texto = (
                f"Processando: {index + 1} de {total_arquivos} "
                f"arquivos ({int(porcentagem * 100)}%)"
            )

            if progress_callback:
                progress_callback(porcentagem, texto)

            if modo_seguro:
                time.sleep(0.01)

        return stats

    except Exception as e:
        stats["erro"] = str(e)
        return stats


