# -*- coding: utf-8 -*-
# =============================================================================
# EXTRACTOR_SETS.PY — BACKEND PURO: Organizador de Sets do AIKA
# =============================================================================
# Extrai lógica de listadeset.py, removendo 100% de customtkinter/tkinter.
# Funções puras: build_dds_header, extrair_textura_jit, convert_msh_to_obj,
# convert_ms3_to_obj e organizar_e_converter_aika (com callback de progresso).
# =============================================================================

import json
import hashlib
import math
import os
import shutil
import struct
import time

from textura import extrair_textura_jit as _extrair_textura_jit_compartilhado
from config import VERSAO_APLICATIVO


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
# CONSTANTES DO ORGANIZADOR
# =============================================================================
MAPA_ARMADURAS = {
    "01": "Guerreiro",
    "02": "Templaria",
    "03": "Atirador",
    "04": "Dual",
    "05": "FC",
    "06": "Cleriga",
}

MAPA_ARMAS = {
    "FM": "Guerreiro",
    "FF": "Templaria",
    "SM": "Atirador",
    "SF": "Dual",
    "MM": "FC",
    "MF": "Cleriga",
}

PECAS_DO_SET = ["03", "04", "05", "06", "07", "08"]
MANIFEST_SCHEMA_VERSION = 1
PECAS_COMPLETO_ANTIGO = frozenset({"03", "04", "05", "06", "07", "08"})
PECAS_COMPLETO_ATUAL = frozenset({"03", "04", "06", "07", "08"})


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
    Usa o mesmo motor JIT -> DDS/TGA da aba de Texturas.

    Isso elimina a divergência antiga em que o Organizador e a aba de
    Texturas classificavam o mesmo .JIT de maneiras diferentes.
    """
    return _extrair_textura_jit_compartilhado(caminho_jit)


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
                if not all(math.isfinite(valor) for valor in (vx, vy, vz)):
                    raise ValueError("Vértice contém valores não finitos.")
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
                if not math.isfinite(tu) or not math.isfinite(tv):
                    raise ValueError("Coordenada UV contém valores não finitos.")
                uvs.append((tu, -tv))

            faces = []
            for _ in range(face_count // 3):
                f1, f2, f3 = struct.unpack('<3H', f.read(6))
                if any(indice >= vert_count for indice in (f1, f2, f3)):
                    raise ValueError("Face referencia um vértice inexistente.")
                faces.append((f1 + 1, f2 + 1, f3 + 1))

        with open(output_file, 'w') as out:
            out.write(f"# Convertido pelo AIKA Optimizer {VERSAO_APLICATIVO}\n")
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


def convert_ms3_to_obj(input_file):
    """
    Converte um arquivo de arma .MS3 do AIKA para Wavefront .OBJ.

    Há pelo menos duas variantes reais de MS3 no cliente:

    Layout intercalado:
      - cabeçalho de 0x74 bytes;
      - quantidade de vértices em 0x58 (uint32 little-endian);
      - quantidade de faces em 0x5C (uint32 little-endian);
      - vértices intercalados: posição float3 + normal float3;
      - um UV float2 para cada vértice;
      - faces triangulares com três índices uint16.

    Layout indexado (encontrado também em armas com textura TGA):
      - quantidade de posições únicas em 0x54;
      - quantidade de vértices expandidos em 0x58;
      - quantidade de faces em 0x5C;
      - posições únicas float3;
      - registros de vértice: índice da posição uint32 + UV float2;
      - faces triangulares com três índices uint16.

    No layout indexado, as normais não ficam gravadas no mesmo bloco. Elas são
    reconstruídas a partir das faces para que o OBJ seja exibido corretamente.

    A função valida todo o layout antes de criar o OBJ. Uma variante de MS3
    incompatível é ignorada com segurança, preservando sempre o original.
    Retorna (sucesso: bool, mensagem: str).
    """
    try:
        tamanho_cabecalho = 0x74
        tamanho_vertice = 24
        limite_elementos = 10_000_000

        if not os.path.isfile(input_file):
            raise ValueError("Arquivo MS3 não encontrado.")

        with open(input_file, "rb") as f:
            data = f.read()

        if len(data) < tamanho_cabecalho:
            raise ValueError("Arquivo MS3 menor que o cabeçalho esperado.")

        position_count = struct.unpack_from("<I", data, 0x54)[0]
        vertex_count = struct.unpack_from("<I", data, 0x58)[0]
        face_count = struct.unpack_from("<I", data, 0x5C)[0]
        if not (0 < vertex_count <= limite_elementos):
            raise ValueError(
                f"Quantidade de vértices inválida no MS3: {vertex_count}."
            )
        if not (0 < face_count <= limite_elementos):
            raise ValueError(
                f"Quantidade de faces inválida no MS3: {face_count}."
            )

        vertices = []
        normals = []
        uvs = []
        faces = []
        registros_indexados = None

        vertices_offset = tamanho_cabecalho
        uvs_offset = vertices_offset + vertex_count * tamanho_vertice
        faces_offset = uvs_offset + vertex_count * 8
        tamanho_intercalado = faces_offset + face_count * 6

        if tamanho_intercalado <= len(data):
            for indice in range(vertex_count):
                offset = vertices_offset + indice * tamanho_vertice
                posicao = struct.unpack_from("<3f", data, offset)
                normal = struct.unpack_from("<3f", data, offset + 12)
                if not all(math.isfinite(valor) for valor in posicao + normal):
                    raise ValueError(
                        f"Vértice {indice} contém valores não finitos."
                    )
                vertices.append(posicao)
                normals.append(normal)

            for indice in range(vertex_count):
                u, v = struct.unpack_from("<2f", data, uvs_offset + indice * 8)
                if not math.isfinite(u) or not math.isfinite(v):
                    raise ValueError(
                        f"Coordenada UV {indice} contém valores não finitos."
                    )
                # O MS3 usa a orientação vertical de textura do DirectX.
                uvs.append((u, 1.0 - v))

        else:
            if not (0 < position_count <= limite_elementos):
                raise ValueError(
                    "Quantidade de posições inválida no layout indexado do "
                    f"MS3: {position_count}."
                )

            registros_offset = vertices_offset + position_count * 12
            faces_offset = registros_offset + vertex_count * 12
            tamanho_indexado = faces_offset + face_count * 6
            if tamanho_indexado > len(data):
                raise ValueError(
                    "Estrutura MS3 incompatível: nenhum layout conhecido "
                    "cabe integralmente no arquivo."
                )

            posicoes = []
            for indice in range(position_count):
                posicao = struct.unpack_from(
                    "<3f", data, vertices_offset + indice * 12
                )
                if not all(math.isfinite(valor) for valor in posicao):
                    raise ValueError(
                        f"Posição {indice} contém valores não finitos."
                    )
                posicoes.append(posicao)

            registros_indexados = []
            for indice in range(vertex_count):
                offset = registros_offset + indice * 12
                position_index, u, v = struct.unpack_from("<I2f", data, offset)
                registros_indexados.append((position_index, u, v))

        for indice in range(face_count):
            face = struct.unpack_from("<3H", data, faces_offset + indice * 6)
            if any(vertex_index >= vertex_count for vertex_index in face):
                raise ValueError(
                    f"Face {indice} referencia um vértice inexistente."
                )
            faces.append(tuple(vertex_index + 1 for vertex_index in face))

        if registros_indexados is not None:
            # Alguns MS3 indexados declaram registros auxiliares depois da
            # geometria efetivamente usada. Somente registros referenciados
            # pelas faces pertencem ao OBJ; valide e remapeie esses registros
            # sem interpretar ou normalizar o payload não referenciado.
            referenciados = sorted({indice - 1 for face in faces for indice in face})
            remapeamento = {
                indice_ms3: indice_obj + 1
                for indice_obj, indice_ms3 in enumerate(referenciados)
            }
            for indice in referenciados:
                position_index, u, v = registros_indexados[indice]
                if position_index >= position_count:
                    raise ValueError(
                        f"Vértice {indice} referencia a posição inexistente "
                        f"{position_index}."
                    )
                if not math.isfinite(u) or not math.isfinite(v):
                    raise ValueError(
                        f"Coordenada UV {indice} contém valores não finitos."
                    )
                vertices.append(posicoes[position_index])
                uvs.append((u, 1.0 - v))
            faces = [
                tuple(remapeamento[indice - 1] for indice in face)
                for face in faces
            ]

        if not normals:
            acumuladas = [[0.0, 0.0, 0.0] for _ in vertices]
            for f1, f2, f3 in faces:
                p1, p2, p3 = vertices[f1 - 1], vertices[f2 - 1], vertices[f3 - 1]
                ax, ay, az = (p2[i] - p1[i] for i in range(3))
                bx, by, bz = (p3[i] - p1[i] for i in range(3))
                normal_face = (
                    ay * bz - az * by,
                    az * bx - ax * bz,
                    ax * by - ay * bx,
                )
                for vertex_index in (f1 - 1, f2 - 1, f3 - 1):
                    for eixo in range(3):
                        acumuladas[vertex_index][eixo] += normal_face[eixo]

            for nx, ny, nz in acumuladas:
                comprimento = math.sqrt(nx * nx + ny * ny + nz * nz)
                if comprimento > 1e-12:
                    normals.append(
                        (nx / comprimento, ny / comprimento, nz / comprimento)
                    )
                else:
                    normals.append((0.0, 0.0, 1.0))

        textura_raw = data[0x20:0x40].split(b"\0", 1)[0]
        textura = textura_raw.decode("ascii", errors="replace").strip()
        output_file = os.path.splitext(input_file)[0] + ".obj"
        output_temp = output_file + ".tmp"

        try:
            with open(output_temp, "w", encoding="utf-8", newline="\n") as out:
                out.write(f"# Convertido pelo AIKA Optimizer {VERSAO_APLICATIVO}\n")
                out.write(f"# Origem: {os.path.basename(input_file)}\n")
                if textura:
                    out.write(f"# Textura referenciada: {textura}\n")
                out.write(
                    f"# {len(vertices)} vértices, {len(faces)} faces\n\n"
                )
                out.write(f"o {os.path.splitext(os.path.basename(input_file))[0]}\n")
                for vx, vy, vz in vertices:
                    out.write(f"v {vx:.9g} {vy:.9g} {vz:.9g}\n")
                for tu, tv in uvs:
                    out.write(f"vt {tu:.9g} {tv:.9g}\n")
                for nx, ny, nz in normals:
                    out.write(f"vn {nx:.9g} {ny:.9g} {nz:.9g}\n")
                for f1, f2, f3 in faces:
                    out.write(
                        f"f {f1}/{f1}/{f1} "
                        f"{f2}/{f2}/{f2} "
                        f"{f3}/{f3}/{f3}\n"
                    )
            os.replace(output_temp, output_file)
        finally:
            if os.path.exists(output_temp):
                os.remove(output_temp)

        return True, ""
    except Exception as e:
        return False, str(e)


# =============================================================================
# 3. RECURSOS COMPARTILHADOS DE CLASSE (.BON / .AN2)
# =============================================================================
def identificar_recurso_classe(nome_arquivo, mapa_armaduras=None):
    """
    Identifica esqueletos e animações compartilhados por classe.

    Exemplos:
        CH03.bon     -> ("03", "bon")
        CH030383.an2 -> ("03", "an2")

    Retorna (classe_id, tipo) ou (None, None) quando o arquivo não pertence a
    uma das classes CH01..CH06 reconhecidas.
    """
    if mapa_armaduras is None:
        mapa_armaduras = MAPA_ARMADURAS

    nome_base, extensao = os.path.splitext(os.path.basename(nome_arquivo))
    nome_superior = nome_base.upper()
    extensao = extensao.lower()

    if not nome_superior.startswith("CH") or len(nome_superior) < 4:
        return None, None

    classe_id = nome_superior[2:4]
    if classe_id not in mapa_armaduras:
        return None, None

    # O arquivo de hierarquia da classe possui nome exato CHxx.bon.
    if extensao == ".bon" and nome_superior == f"CH{classe_id}":
        return classe_id, "bon"

    # Os clips usam o mesmo prefixo da classe: CH03xxxx.an2, por exemplo.
    if extensao == ".an2" and len(nome_superior) > 4:
        return classe_id, "an2"

    return None, None


def _hash_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _copiar_se_necessario(origem, destino):
    """Copia/atualiza quando o conteúdo mudou. Retorna True se gravou."""
    try:
        if os.path.exists(destino):
            if os.path.getsize(origem) == os.path.getsize(destino) and _hash_arquivo(origem) == _hash_arquivo(destino):
                return False
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        temporario = destino + ".organizer.tmp"
        shutil.copy2(origem, temporario)
        if _hash_arquivo(origem) != _hash_arquivo(temporario):
            raise OSError("hash da cópia do Organizador diverge da origem")
        os.replace(temporario, destino)
        return True
    except Exception:
        try:
            if os.path.exists(destino + ".organizer.tmp"):
                os.remove(destino + ".organizer.tmp")
        except OSError:
            pass
        raise


def _listar_arquivos_relativos(pasta_set, subpasta):
    """Lista arquivos diretos de uma subpasta usando caminhos JSON portáveis."""
    pasta = os.path.join(pasta_set, subpasta)
    if not os.path.isdir(pasta):
        return []
    return [
        f"{subpasta}/{nome}"
        for nome in sorted(os.listdir(pasta), key=str.lower)
        if os.path.isfile(os.path.join(pasta, nome))
    ]


def separar_familia_variante(set_id):
    """Separa o ID técnico de quatro caracteres em família e variante."""
    set_id = str(set_id).upper()
    if len(set_id) == 4 and set_id.isalnum():
        return set_id[:2], set_id[2:4]
    return set_id, ""


def caminho_pasta_set(diretorio_destino, nome_classe, set_id):
    """Retorna a pasta da variante dentro de sua família visual."""
    familia_id, _ = separar_familia_variante(set_id)
    return os.path.join(
        diretorio_destino,
        nome_classe,
        f"Familia_Armadura_{familia_id}",
        f"Set_Armadura_{set_id}",
    )


def migrar_pastas_sets_legadas(diretorio_destino, mapa_armaduras=None):
    """
    Move com segurança pastas planas Set_Armadura_xxxx para suas famílias.

    Uma pasta não é mesclada nem sobrescrita quando o destino novo já existe.
    Retorna (quantidade_movida, quantidade_ignorada, sets_encontrados).
    """
    if mapa_armaduras is None:
        mapa_armaduras = MAPA_ARMADURAS
    movidas = 0
    ignoradas = 0
    encontrados = set()
    for classe_id, nome_classe in mapa_armaduras.items():
        pasta_classe = os.path.join(diretorio_destino, nome_classe)
        if not os.path.isdir(pasta_classe):
            continue
        for nome in sorted(os.listdir(pasta_classe), key=str.lower):
            prefixo = "Set_Armadura_"
            if not nome.startswith(prefixo):
                continue
            set_id = nome[len(prefixo):]
            if len(set_id) != 4 or not set_id.isalnum():
                continue
            origem = os.path.join(pasta_classe, nome)
            if not os.path.isdir(origem):
                continue
            encontrados.add((classe_id, set_id))
            destino = caminho_pasta_set(
                diretorio_destino, nome_classe, set_id
            )
            if os.path.exists(destino):
                ignoradas += 1
                continue
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.move(origem, destino)
            movidas += 1
    return movidas, ignoradas, encontrados


def _partes_originais_set(pasta_set, set_id):
    """Obtém as partes pelos MSH originais; OBJ/JIT não definem completude."""
    partes = set()
    pasta_mesh = os.path.join(pasta_set, "Mesh")
    if not os.path.isdir(pasta_mesh):
        return []
    for nome in os.listdir(pasta_mesh):
        base, extensao = os.path.splitext(nome)
        if extensao.lower() != ".msh":
            continue
        if base.upper().startswith("CH") and len(base) >= 10:
            if base[6:10].upper() == str(set_id).upper():
                partes.add(base[4:6])
    return sorted(partes)


def classificar_aparencia(partes):
    """Classificação informativa; nunca rejeita aparências incompletas."""
    conjunto = frozenset(partes)
    if PECAS_COMPLETO_ANTIGO.issubset(conjunto):
        return "completo_6_partes"
    if conjunto == PECAS_COMPLETO_ATUAL:
        return "completo_5_partes"
    if len(conjunto) == 1:
        return "aparencia_individual"
    if conjunto:
        return "aparencia_parcial"
    return "somente_textura"


def _sha256_arquivo(caminho):
    hash_obj = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(65536), b""):
            hash_obj.update(bloco)
    return hash_obj.hexdigest()


def criar_manifest_familia(diretorio_destino, classe_id, set_ids,
                            mapa_armaduras=None):
    """Cria um índice visual da família sem fundir suas variantes técnicas."""
    if mapa_armaduras is None:
        mapa_armaduras = MAPA_ARMADURAS
    nome_classe = mapa_armaduras[classe_id]
    familias = {}
    for set_id in sorted({str(item) for item in set_ids}):
        familia_id, _ = separar_familia_variante(set_id)
        familias.setdefault(familia_id, []).append(set_id)

    alterados = 0
    for familia_id, variantes_ids in familias.items():
        pasta_familia = os.path.join(
            diretorio_destino, nome_classe, f"Familia_Armadura_{familia_id}"
        )
        variantes = []
        assinaturas = []
        for set_id in variantes_ids:
            _, variante_id = separar_familia_variante(set_id)
            pasta_set = caminho_pasta_set(diretorio_destino, nome_classe, set_id)
            partes = _partes_originais_set(pasta_set, set_id)
            hashes_mesh = {}
            for parte in partes:
                prefixo = f"CH{classe_id}{parte}{set_id}".upper()
                pasta_mesh = os.path.join(pasta_set, "Mesh")
                candidatos = [
                    nome for nome in os.listdir(pasta_mesh)
                    if nome.upper() == f"{prefixo}.MSH"
                ] if os.path.isdir(pasta_mesh) else []
                if candidatos:
                    hashes_mesh[parte] = _sha256_arquivo(
                        os.path.join(pasta_mesh, candidatos[0])
                    )
            assinaturas.append(hashes_mesh)
            variantes.append({
                "set_id": set_id,
                "variant_id": variante_id,
                "directory": f"Set_Armadura_{set_id}",
                "available_parts": partes,
                "piece_count": len(partes),
                "appearance_scope": classificar_aparencia(partes),
            })

        if len(assinaturas) < 2:
            status_geometria = "uma_variante"
        elif all(item == assinaturas[0] for item in assinaturas[1:]):
            status_geometria = "meshes_identicos"
        else:
            status_geometria = "nao_confirmado"

        manifesto = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "asset_kind": "armor_family",
            "visual_family_id": familia_id,
            "class_code": f"CH{classe_id}",
            "class_name": nome_classe,
            "geometry_status": status_geometria,
            "variants": variantes,
        }
        conteudo = json.dumps(
            manifesto, ensure_ascii=False, indent=2, sort_keys=False
        ) + "\n"
        caminho = os.path.join(pasta_familia, "family_manifest.json")
        anterior = None
        if os.path.isfile(caminho):
            try:
                with open(caminho, "r", encoding="utf-8") as arquivo:
                    anterior = arquivo.read()
            except (OSError, UnicodeError):
                pass
        if anterior != conteudo:
            os.makedirs(pasta_familia, exist_ok=True)
            temporario = caminho + ".tmp"
            with open(temporario, "w", encoding="utf-8", newline="\n") as arquivo:
                arquivo.write(conteudo)
            os.replace(temporario, caminho)
            alterados += 1
    return alterados


def criar_manifest_set(diretorio_destino, classe_id, set_id,
                       mapa_armaduras=None):
    """
    Cria/atualiza o set_manifest.json de um set já organizado.

    O manifesto referencia a biblioteca compartilhada Classe_CHxx; não duplica
    os arquivos .bon e .an2 dentro de cada set.

    Retorna True quando o manifesto foi criado/alterado e False quando o
    conteúdo existente já estava atualizado.
    """
    if mapa_armaduras is None:
        mapa_armaduras = MAPA_ARMADURAS
    if classe_id not in mapa_armaduras:
        raise ValueError(f"Classe CH{classe_id} não reconhecida.")

    nome_classe = mapa_armaduras[classe_id]
    pasta_classe = os.path.join(
        diretorio_destino, nome_classe, f"Classe_CH{classe_id}"
    )
    pasta_set = caminho_pasta_set(diretorio_destino, nome_classe, set_id)
    pasta_rig = os.path.join(pasta_classe, "Rig")
    pasta_animacoes = os.path.join(pasta_classe, "Animacoes")
    caminho_bon = os.path.join(pasta_rig, f"CH{classe_id}.bon")

    animacoes = []
    if os.path.isdir(pasta_animacoes):
        animacoes = [
            nome for nome in sorted(os.listdir(pasta_animacoes), key=str.lower)
            if nome.lower().endswith(".an2")
            and os.path.isfile(os.path.join(pasta_animacoes, nome))
        ]

    def _relativo(caminho):
        return os.path.relpath(caminho, pasta_set).replace(os.sep, "/")

    familia_id, variante_id = separar_familia_variante(set_id)
    partes_disponiveis = _partes_originais_set(pasta_set, set_id)
    manifesto = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "asset_kind": "set",
        "set_id": str(set_id),
        "visual_family_id": familia_id,
        "variant_id": variante_id,
        "class_code": f"CH{classe_id}",
        "class_name": nome_classe,
        "available_parts": partes_disponiveis,
        "piece_count": len(partes_disponiveis),
        "appearance_scope": classificar_aparencia(partes_disponiveis),
        "shared_class_assets": {
            "root": _relativo(pasta_classe),
            "skeleton": _relativo(caminho_bon)
            if os.path.isfile(caminho_bon) else None,
            "animations_directory": _relativo(pasta_animacoes)
            if os.path.isdir(pasta_animacoes) else None,
            "animations_pattern": f"CH{classe_id}*.an2",
            "animations_count": len(animacoes),
        },
        "files": {
            "mesh": _listar_arquivos_relativos(pasta_set, "Mesh"),
            "texture": _listar_arquivos_relativos(pasta_set, "Texture"),
            "objects": _listar_arquivos_relativos(pasta_set, "Objects"),
        },
    }

    conteudo = json.dumps(
        manifesto, ensure_ascii=False, indent=2, sort_keys=False
    ) + "\n"
    caminho_manifesto = os.path.join(pasta_set, "set_manifest.json")

    if os.path.isfile(caminho_manifesto):
        try:
            with open(caminho_manifesto, "r", encoding="utf-8") as f:
                if f.read() == conteudo:
                    return False
        except (OSError, UnicodeError):
            pass

    os.makedirs(pasta_set, exist_ok=True)
    caminho_temporario = caminho_manifesto + ".tmp"
    with open(caminho_temporario, "w", encoding="utf-8", newline="\n") as f:
        f.write(conteudo)
    os.replace(caminho_temporario, caminho_manifesto)
    return True


def criar_manifest_arma(diretorio_destino, prefixo_arma, tipo_arma, id_arma,
                        mapa_armas=None):
    """Cria/atualiza o weapon_manifest.json de uma arma organizada."""
    if mapa_armas is None:
        mapa_armas = MAPA_ARMAS

    prefixo_arma = str(prefixo_arma).upper()
    tipo_arma = str(tipo_arma).upper()
    id_arma = str(id_arma).upper()
    if prefixo_arma not in mapa_armas:
        raise ValueError(f"Prefixo de arma {prefixo_arma} não reconhecido.")
    if len(tipo_arma) != 3 or len(id_arma) != 5:
        raise ValueError("Identidade de arma inválida.")

    nome_classe = mapa_armas[prefixo_arma]
    pasta_arma = os.path.join(
        diretorio_destino,
        nome_classe,
        "Armas",
        f"{tipo_arma}_{id_arma}",
    )
    manifesto = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "asset_kind": "weapon",
        "weapon_prefix": prefixo_arma,
        "weapon_type": tipo_arma,
        "weapon_id": id_arma,
        "class_code": prefixo_arma,
        "class_name": nome_classe,
        "files": {
            "objects": _listar_arquivos_relativos(pasta_arma, "Objects"),
            "texture": _listar_arquivos_relativos(pasta_arma, "Texture"),
        },
    }

    conteudo = json.dumps(
        manifesto, ensure_ascii=False, indent=2, sort_keys=False
    ) + "\n"
    caminho_manifesto = os.path.join(pasta_arma, "weapon_manifest.json")
    if os.path.isfile(caminho_manifesto):
        try:
            with open(caminho_manifesto, "r", encoding="utf-8") as f:
                if f.read() == conteudo:
                    return False
        except (OSError, UnicodeError):
            pass

    os.makedirs(pasta_arma, exist_ok=True)
    caminho_temporario = caminho_manifesto + ".tmp"
    with open(caminho_temporario, "w", encoding="utf-8", newline="\n") as f:
        f.write(conteudo)
    os.replace(caminho_temporario, caminho_manifesto)
    return True


# =============================================================================
# 4. COR DO PROGRESSO (UTILITÁRIO)
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
# 5. MOTOR PRINCIPAL DE ORGANIZAÇÃO E CONVERSÃO
# =============================================================================
def organizar_e_converter_aika(diretorio_origem, diretorio_destino,
                                modo_seguro, extrair_3d, extrair_tex,
                                progress_callback=None, cancel_callback=None,
                                log_callback=None):
    """
    Percorre o diretório de origem, organiza arquivos por classes/sets,
    organiza .bon/.an2 em uma biblioteca compartilhada por classe e
    opcionalmente converte .msh/.ms3 -> .obj e extrai .jit -> .dds/.tga.

    Parâmetros:
        diretorio_origem  (str): Pasta com os arquivos do jogo.
        diretorio_destino (str): Pasta de destino organizada.
        modo_seguro       (bool): Adiciona sleep(0.01) entre iterações.
        extrair_3d        (bool): Converte .msh e .ms3 para .obj.
        extrair_tex       (bool): Extrai texturas de .jit.
        progress_callback (callable): Chamada com (porcentagem: float, texto: str).

    Retorna:
        dict com estatísticas, incluindo bon_copiados, an2_copiados e
        manifestos_criados. As chaves antigas são preservadas.
    """
    stats = {
        "copiados": 0,
        "msh_convertidos": 0,
        "ms3_convertidos": 0,
        "falhas_3d": 0,
        "jit_extraidos": 0,
        "bon_copiados": 0,
        "an2_copiados": 0,
        "manifestos_criados": 0,
        "manifestos_armas_criados": 0,
        "familias_criadas": 0,
        "pastas_legadas_migradas": 0,
        "pastas_legadas_ignoradas": 0,
        "classes_organizadas": 0,
    }

    def _emitir_log(mensagem):
        """Encaminha observabilidade sem interferir no processamento."""
        if log_callback is not None:
            try:
                log_callback(str(mensagem))
            except Exception:
                pass

    etapa_atual = "ORGANIZADOR"
    arquivo_atual = ""

    def _cancelado():
        if cancel_callback is None:
            return False
        try:
            return bool(cancel_callback())
        except Exception:
            return False

    try:
        diretorio_origem = os.path.realpath(os.path.abspath(diretorio_origem))
        diretorio_destino = os.path.realpath(os.path.abspath(diretorio_destino))
        _emitir_log("[INFO] Organizador iniciado...")
        _emitir_log(f"[INFO] Origem: {diretorio_origem}")
        _emitir_log(f"[INFO] Destino: {diretorio_destino}")
        try:
            if os.path.commonpath([diretorio_origem, diretorio_destino]) == diretorio_origem:
                stats["erro"] = "A pasta de destino não pode ser igual nem ficar dentro da pasta de origem."
                _emitir_log(f"[ERRO][PATH] {stats['erro']}")
                return stats
        except ValueError:
            pass
        if not os.path.exists(diretorio_destino):
            os.makedirs(diretorio_destino)

        mapa_armaduras = MAPA_ARMADURAS
        mapa_armas = MAPA_ARMAS
        pecas_do_set = PECAS_DO_SET
        movidas, ignoradas, sets_legados = migrar_pastas_sets_legadas(
            diretorio_destino, mapa_armaduras
        )
        stats["pastas_legadas_migradas"] = movidas
        stats["pastas_legadas_ignoradas"] = ignoradas
        sets_encontrados = set(sets_legados)
        armas_encontradas = set()
        classes_com_recursos = set()

        if progress_callback:
            progress_callback(0.0, "Mapeando arquivos... aguarde.")

        lista_arquivos = []
        etapa_atual = "SCAN"
        for raiz, diretorios, arquivos in os.walk(diretorio_origem):
            if _cancelado():
                stats["cancelado"] = True
                _emitir_log("[INFO] Organização cancelada pelo usuário.")
                return stats
            for arquivo in arquivos:
                if _cancelado():
                    stats["cancelado"] = True
                    _emitir_log("[INFO] Organização cancelada pelo usuário.")
                    return stats
                lista_arquivos.append((raiz, arquivo))

        total_arquivos = len(lista_arquivos)
        if total_arquivos == 0:
            stats["erro"] = "Nenhum arquivo encontrado na pasta de origem!"
            _emitir_log(f"[ERRO][SCAN] {stats['erro']}")
            return stats

        for index, (raiz, arquivo) in enumerate(lista_arquivos):
            if _cancelado():
                stats["cancelado"] = True
                _emitir_log("[INFO] Organização cancelada pelo usuário.")
                break
            arquivo_atual = arquivo
            nome_base, extensao = os.path.splitext(arquivo)
            extensao = extensao.lower()
            caminho_pasta_item = None
            chave_set = None
            chave_arma = None
            item_arma = False

            # Esqueleto/animações compartilhados da classe. Eles são copiados
            # uma única vez, e os sets apontam para essa biblioteca via JSON.
            classe_recurso, tipo_recurso = identificar_recurso_classe(
                arquivo, mapa_armaduras
            )
            if classe_recurso:
                etapa_atual = "COPY"
                nome_classe = mapa_armaduras[classe_recurso]
                subpasta_recurso = (
                    "Rig" if tipo_recurso == "bon" else "Animacoes"
                )
                pasta_recurso = os.path.join(
                    diretorio_destino,
                    nome_classe,
                    f"Classe_CH{classe_recurso}",
                    subpasta_recurso,
                )
                origem_recurso = os.path.join(raiz, arquivo)
                destino_recurso = os.path.join(pasta_recurso, arquivo)

                if _copiar_se_necessario(origem_recurso, destino_recurso):
                    stats["copiados"] += 1
                    if tipo_recurso == "bon":
                        stats["bon_copiados"] += 1
                    else:
                        stats["an2_copiados"] += 1
                classes_com_recursos.add(classe_recurso)

            # Armaduras (CH prefixo)
            if nome_base.upper().startswith('CH') and len(nome_base) >= 10:
                classe_id = nome_base[2:4]
                parte_id = nome_base[4:6]
                set_id = nome_base[6:10]
                if classe_id in mapa_armaduras and parte_id in pecas_do_set:
                    caminho_pasta_item = caminho_pasta_set(
                        diretorio_destino, mapa_armaduras[classe_id], set_id
                    )
                    chave_set = (classe_id, set_id)

            # Armas
            prefixo_arma = nome_base[:2].upper()
            if prefixo_arma in mapa_armas and len(nome_base) >= 10:
                tipo_arma = nome_base[2:5]
                id_arma = nome_base[5:10]
                item_arma = True
                chave_arma = (prefixo_arma, tipo_arma, id_arma)
                caminho_pasta_item = os.path.join(
                    diretorio_destino,
                    mapa_armas[prefixo_arma],
                    "Armas",
                    f"{tipo_arma}_{id_arma}"
                )

            if caminho_pasta_item:
                subpasta = ""
                if extensao == '.msh':
                    subpasta = "Mesh"
                elif extensao == '.obj':
                    subpasta = "Objects" if item_arma else "Mesh"
                elif extensao in ('.jit', '.ef'):
                    subpasta = "Texture"
                elif extensao == '.ms3':
                    subpasta = "Objects"

                if subpasta:
                    etapa_atual = "DIRECTORY"
                    caminho_final = os.path.join(caminho_pasta_item, subpasta)
                    if not os.path.exists(caminho_final):
                        os.makedirs(caminho_final)

                    origem = os.path.join(raiz, arquivo)
                    destino = os.path.join(caminho_final, arquivo)

                    etapa_atual = "COPY"
                    atualizado = _copiar_se_necessario(origem, destino)
                    if atualizado:
                        stats["copiados"] += 1
                    if chave_set:
                        sets_encontrados.add(chave_set)
                    if chave_arma:
                        armas_encontradas.add(chave_arma)

                    if extensao == '.msh' and extrair_3d:
                        etapa_atual = "MSH->OBJ"
                        caminho_obj = os.path.splitext(destino)[0] + ".obj"
                        if atualizado or not os.path.exists(caminho_obj):
                            sucesso, msg = convert_msh_to_obj(destino)
                            if sucesso:
                                stats["msh_convertidos"] += 1
                            else:
                                stats["falhas_3d"] += 1
                                motivo = msg or "conversão recusada pelo backend"
                                _emitir_log(
                                    f"[ERRO][MSH->OBJ] {arquivo} — {motivo}"
                                )

                    elif extensao == '.ms3' and extrair_3d:
                        etapa_atual = "MS3->OBJ"
                        caminho_obj = os.path.splitext(destino)[0] + ".obj"
                        if atualizado or not os.path.exists(caminho_obj):
                            sucesso, msg = convert_ms3_to_obj(destino)
                            if sucesso:
                                stats["ms3_convertidos"] += 1
                            else:
                                stats["falhas_3d"] += 1
                                motivo = msg or "conversão recusada pelo backend"
                                _emitir_log(
                                    f"[ERRO][MS3->OBJ] {arquivo} — {motivo}"
                                )

                    elif extensao == '.jit' and extrair_tex:
                        etapa_atual = "JIT"
                        caminho_dds = os.path.splitext(destino)[0] + ".dds"
                        caminho_tga = os.path.splitext(destino)[0] + ".tga"
                        if atualizado or (not os.path.exists(caminho_dds) and
                                not os.path.exists(caminho_tga)):
                            # remove saída antiga do outro tipo para não deixar preview stale
                            for antigo in (caminho_dds, caminho_tga):
                                if atualizado and os.path.exists(antigo):
                                    try: os.remove(antigo)
                                    except OSError: pass
                            sucesso, msg = extrair_textura_jit(destino)
                            if sucesso:
                                stats["jit_extraidos"] += 1
                            else:
                                motivo = msg or "extração recusada pelo backend"
                                _emitir_log(f"[ERRO][JIT] {arquivo} — {motivo}")

            porcentagem = (index + 1) / total_arquivos
            texto = (
                f"Processando: {index + 1} de {total_arquivos} "
                f"arquivos ({int(porcentagem * 100)}%)"
            )

            if progress_callback:
                progress_callback(porcentagem, texto)

            if modo_seguro:
                time.sleep(0.01)

        # Os manifestos são produzidos depois das cópias/conversões para
        # registrarem também OBJ, DDS e TGA eventualmente gerados.
        if not stats.get("cancelado"):
            etapa_atual = "MANIFEST"
            arquivo_atual = ""
            for classe_id, set_id in sorted(sets_encontrados):
                if criar_manifest_set(
                    diretorio_destino, classe_id, set_id, mapa_armaduras
                ):
                    stats["manifestos_criados"] += 1
            sets_por_classe = {}
            for classe_id, set_id in sets_encontrados:
                sets_por_classe.setdefault(classe_id, []).append(set_id)
            for classe_id, set_ids in sorted(sets_por_classe.items()):
                criados = criar_manifest_familia(
                    diretorio_destino, classe_id, set_ids, mapa_armaduras
                )
                stats["familias_criadas"] += criados
                stats["manifestos_criados"] += criados
            for prefixo_arma, tipo_arma, id_arma in sorted(armas_encontradas):
                if criar_manifest_arma(
                    diretorio_destino,
                    prefixo_arma,
                    tipo_arma,
                    id_arma,
                    mapa_armas,
                ):
                    stats["manifestos_criados"] += 1
                    stats["manifestos_armas_criados"] += 1

        stats["classes_organizadas"] = len(classes_com_recursos)

        if progress_callback and not stats.get("cancelado"):
            progress_callback(
                1.0,
                "Organização concluída: "
                f"{stats['msh_convertidos']} MSH e "
                f"{stats['ms3_convertidos']} MS3 convertidos, "
                f"{stats['bon_copiados']} BON, "
                f"{stats['an2_copiados']} AN2 e "
                f"{stats['manifestos_criados']} manifestos.",
            )

        if not stats.get("cancelado"):
            _emitir_log("[OK] Organização concluída.")
            _emitir_log(f"[INFO] Arquivos organizados: {stats['copiados']}")
            _emitir_log(f"[INFO] Armaduras 3D: {stats['msh_convertidos']}")
            _emitir_log(f"[INFO] Armas 3D: {stats['ms3_convertidos']}")
            _emitir_log(f"[INFO] Famílias organizadas: {stats['familias_criadas']}")
            _emitir_log(
                f"[INFO] Pastas antigas agrupadas: "
                f"{stats['pastas_legadas_migradas']}"
            )
            _emitir_log(f"[INFO] Texturas extraídas: {stats['jit_extraidos']}")
            prefixo_falhas = "[ERRO]" if stats["falhas_3d"] else "[INFO]"
            _emitir_log(
                f"{prefixo_falhas} Falhas de Conversão 3D: {stats['falhas_3d']}"
            )

        return stats

    except Exception as e:
        stats["erro"] = str(e)
        identificacao = f" {arquivo_atual}" if arquivo_atual else ""
        _emitir_log(
            f"[ERRO][{etapa_atual}]{identificacao} — "
            f"{type(e).__name__}: {e}"
        )
        return stats


# O Organizador usa o mesmo extrator canônico da aba Texturas.
from textura import extrair_textura_jit as _extrair_textura_jit_canonico
extrair_textura_jit = _extrair_textura_jit_canonico
