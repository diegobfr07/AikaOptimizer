import os, struct
from config import *

# Constantes DX9 para criar um DDS perfeito
DDSD_CAPS = 0x1; DDSD_HEIGHT = 0x2; DDSD_WIDTH = 0x4; DDSD_PITCH = 0x8
DDSD_PIXELFORMAT = 0x1000; DDSD_MIPMAPCOUNT = 0x20000; DDSD_LINEARSIZE = 0x80000
DDSCAPS_COMPLEX = 0x8; DDSCAPS_TEXTURE = 0x1000; DDSCAPS_MIPMAP = 0x400000
DDPF_FOURCC = 0x4

def build_dds_header(width, height, fourcc, mipmaps, linear_size):
    header = bytearray(128)
    header[0:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)
    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_LINEARSIZE
    if mipmaps > 1: flags |= DDSD_MIPMAPCOUNT
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
        caps |= DDSCAPS_COMPLEX
        caps |= DDSCAPS_MIPMAP
    struct.pack_into("<I", header, 108, caps)
    return bytes(header)

def extrair_textura_jit(caminho_jit):
    try:
        if not os.path.exists(caminho_jit) or os.path.getsize(caminho_jit) < 24: return False, "Arquivo inválido."
        with open(caminho_jit, "rb") as f: data = f.read()

        base = os.path.splitext(caminho_jit)[0]
        
        achados = []
        for magic in [b'DDS ', b'JT31', b'JT33', b'JT35', b'JT20']:
            off = data.find(magic)
            if off != -1:
                if magic == b'DDS ':
                    achados.append((off, "DDS"))
                else:
                    if off + 12 <= len(data):
                        w = struct.unpack("<I", data[off+4:off+8])[0]
                        h = struct.unpack("<I", data[off+8:off+12])[0]
                        if 8 <= w <= 8192 and 8 <= h <= 8192: 
                            achados.append((off, magic.decode()))
        
        if achados:
            achados.sort(key=lambda x: x[0])
            offset, tipo = achados[0]
            
            # 1. TEXTURAS DXT COM CABEÇALHO SIMPLIFICADO (Modo Raiz)
            if tipo in ["JT31", "JT33", "JT35"]:
                width = struct.unpack("<I", data[offset+4:offset+8])[0]
                height = struct.unpack("<I", data[offset+8:offset+12])[0]
                fourcc_map = {"JT31": (b"DXT1", 8), "JT33": (b"DXT3", 16), "JT35": (b"DXT5", 16)}
                fourcc, block_size = fourcc_map[tipo]

                # Tamanho apenas da imagem principal
                blocks_x = max(1, (width + 3) // 4)
                blocks_y = max(1, (height + 3) // 4)
                base_size = blocks_x * blocks_y * block_size
                
                payload = data[offset + 12 : offset + 12 + base_size]
                dds_hdr = build_dds_header(width, height, fourcc, 1, base_size)
                
                out = base + ".dds"
                with open(out, "wb") as f:
                    f.write(dds_hdr)
                    f.write(payload)

                return True, f"SUCESSO! Extraído DDS Simples ({width}x{height})."

            # 2. ARMAS/ITENS (JT20 para TGA)
            elif tipo == "JT20":
                width = struct.unpack("<I", data[offset+4:offset+8])[0]
                height = struct.unpack("<I", data[offset+8:offset+12])[0]
                size_pixels = width * height
                
                palette = data[offset+12 : offset+12 + 1024]
                pixels = data[offset+12 + 1024 : offset+12 + 1024 + size_pixels]

                rgba = bytearray()
                for idx in pixels:
                    if idx * 4 + 3 < len(palette):
                        b, g, r, a = palette[idx*4], palette[idx*4+1], palette[idx*4+2], palette[idx*4+3]
                    else:
                        b, g, r, a = 0, 0, 0, 0
                    rgba.extend([b, g, r, a])

                tga = bytearray(18)
                tga[2] = 2
                struct.pack_into("<H", tga, 12, width)
                struct.pack_into("<H", tga, 14, height)
                tga[16], tga[17] = 32, 0x28

                out = base + ".tga"
                with open(out, "wb") as f: f.write(tga); f.write(rgba)
                
                return True, f"SUCESSO! Extraído JT20 como TGA ({width}x{height})."

            # 3. DDS EMBUTIDO DIRETAMENTE
            elif tipo == "DDS":
                out = base + ".dds"
                payload = data[offset:]
                with open(out, "wb") as f: f.write(payload)
                return True, "SUCESSO! Textura DDS Nativa extraída."

        # 4. SCANNER INTELIGENTE DE TGA
        offset_tga = -1
        for off in range(0, min(8192, len(data) - 18)):
            img_type = data[off + 2]
            if img_type in [1, 2, 3, 9, 10, 11]:
                bpp = data[off + 16]
                if bpp in [8, 15, 16, 24, 32]:
                    w = struct.unpack('<H', data[off+12:off+14])[0]
                    h = struct.unpack('<H', data[off+14:off+16])[0]
                    if 8 <= w <= 4096 and 8 <= h <= 4096:
                        offset_tga = off
                        break
        
        if offset_tga != -1:
            payload = data[offset_tga:]
            out = base + ".tga"
            with open(out, "wb") as f: f.write(payload)
            return True, f"SUCESSO! TGA de Interface extraído."

        return False, "Nenhuma textura válida (DDS/JT/TGA) encontrada no arquivo."
    except Exception as e: return False, f"Erro: {str(e)}"