# -*- coding: utf-8 -*-
# =============================================================================
# SET_INJECTOR.PY — BACKEND PURO: Injetor separado de Sets e Armas do AIKA
# =============================================================================
# Opera sobre pastas organizadas pelo Extrator/Organizador de Sets.
# Fluxo: validar manifests → mapear doador→alvo → staging → simular → injetar.
# =============================================================================

import os
import json
import shutil
import hashlib
import time
import threading
from config import PASTA_JOGO_PADRAO, lock_otimizacao, normalizar_pasta_jogo, obter_pasta_backup_cliente
from seguranca import fazer_backup_rapido
from automod import (carregar_index_jogo, criar_index_jogo, registrar_mod_ativo,
                     carregar_historico_automod, salvar_historico_automod)
from extractor_sets import (
    MAPA_ARMAS,
    classificar_aparencia,
    separar_familia_variante,
)

# ---------------------------------------------------------------------------
# 1. LEITURA E VALIDAÇÃO DE MANIFEST
# ---------------------------------------------------------------------------
MANIFEST_SCHEMA = 1

# Somente assets binários originais do cliente podem chegar à injeção.
# OBJ/DDS/TGA e demais formatos gerados pelo Organizador servem apenas para
# visualização e nunca devem ser preparados, copiados ou injetados.
EXTENSOES_POR_ASSET = {
    "set": frozenset({".msh", ".jit", ".ef"}),
    "weapon": frozenset({".ms3", ".jit", ".ef"}),
}
EXTENSOES_INJETAVEIS = frozenset().union(*EXTENSOES_POR_ASSET.values())
TIPO_POR_EXTENSAO = {
    ".msh": "mesh",
    ".ms3": "object",
    ".jit": "texture",
    ".ef": "effect",
}
ARQUIVO_MANIFEST_STAGING = "staging_manifest.json"
ARQUIVO_MANIFEST_SET = "set_manifest.json"


def _extensao_injetavel(caminho_ou_nome, asset_kind=None):
    """Valida a extensão conforme o modo: set ou arma."""
    extensao = os.path.splitext(str(caminho_ou_nome))[1].lower()
    permitidas = EXTENSOES_POR_ASSET.get(asset_kind, EXTENSOES_INJETAVEIS)
    return extensao in permitidas


def _subtipo_asset(caminho_ou_nome):
    """
    Distingue textura base de textura de efeito.

    Exemplos:
      CH03033801.jit   -> base
      CH03033801EF.jit -> effect

    O sufixo EF faz parte do basename; a extensão continua sendo .jit.
    """
    nome = os.path.basename(str(caminho_ou_nome))
    stem, extensao = os.path.splitext(nome)
    if extensao.lower() == ".ef" or (extensao.lower() == ".jit" and stem.upper().endswith("EF")):
        return "effect"
    return "base"


def _validar_item_injetavel(item, rotulo="Arquivo"):
    """Valida extensão e categoria sem confiar apenas no manifesto."""
    if not isinstance(item, dict):
        return f"{rotulo} inválido."

    basename = item.get("basename") or ""
    extensao = (item.get("extensao") or os.path.splitext(basename)[1]).lower()
    tipo = item.get("tipo")
    subtipo = item.get("subtipo") or _subtipo_asset(basename)
    asset_kind = item.get("asset_kind", "set")
    permitidas = EXTENSOES_POR_ASSET.get(asset_kind)

    if permitidas is None:
        return f"{rotulo} com tipo de asset desconhecido: {asset_kind}."
    if extensao not in permitidas:
        lista = ", ".join(sorted(permitidas))
        return (
            f"{rotulo} não injetável: {basename or '<sem nome>'} "
            f"(extensão {extensao or '<ausente>'}). Permitidos no modo "
            f"{asset_kind}: {lista}."
        )

    tipo_esperado = TIPO_POR_EXTENSAO[extensao]
    if tipo != tipo_esperado:
        return (
            f"{rotulo} com tipo incompatível: {basename} "
            f"({extensao} deve pertencer à categoria {tipo_esperado}, não {tipo})."
        )

    if os.path.splitext(basename)[1].lower() != extensao:
        return f"{rotulo} com extensão inconsistente: {basename}."

    subtipo_esperado = _subtipo_asset(basename)
    if subtipo != subtipo_esperado:
        return (
            f"{rotulo} com subtipo inconsistente: {basename} "
            f"(esperado {subtipo_esperado}, recebido {subtipo})."
        )

    return None


def _validar_mapeados(mapeados):
    """Defesa em profundidade para todas as operações após o mapeamento."""
    if not isinstance(mapeados, (list, tuple)):
        return "Mapa Doador → Alvo inválido."

    destinos = set()
    for item in mapeados:
        if not isinstance(item, dict):
            return "Entrada inválida no mapa Doador → Alvo."

        acao = item.get("action", "replace")
        alvo = item.get("alvo")
        erro = _validar_item_injetavel(alvo, "Arquivo alvo")
        if erro:
            return erro

        if acao == "delete":
            if (
                alvo.get("asset_kind", "set") != "set"
                or (alvo.get("subtipo") or _subtipo_asset(alvo["basename"])) != "effect"
            ):
                return f"Remoção inválida fora de um efeito EF de SET: {alvo['basename']}."
            doador = None
        elif acao == "replace":
            doador = item.get("doador")
            erro = _validar_item_injetavel(doador, "Arquivo doador")
            if erro:
                return erro
        else:
            return f"Ação desconhecida no mapa Doador → Alvo: {acao}."

        if doador and doador["extensao"].lower() != alvo["extensao"].lower():
            return (
                f"Correspondência proibida: {doador['basename']} → {alvo['basename']}. "
                "As extensões devem ser idênticas."
            )
        if doador and doador["tipo"] != alvo["tipo"]:
            return (
                f"Correspondência proibida: {doador['basename']} → {alvo['basename']}. "
                "Os tipos de asset devem ser idênticos."
            )
        tipo_asset_doador = doador.get("asset_kind", "set") if doador else "set"
        tipo_asset_alvo = alvo.get("asset_kind", "set")
        if tipo_asset_doador != tipo_asset_alvo:
            return (
                f"Correspondência proibida: {doador['basename']} → {alvo['basename']}. "
                "Sets e armas não podem ser combinados."
            )
        subtipo_doador = (
            doador.get("subtipo") or _subtipo_asset(doador["basename"])
            if doador else "effect"
        )
        subtipo_alvo = alvo.get("subtipo") or _subtipo_asset(alvo["basename"])
        if subtipo_doador != subtipo_alvo:
            return (
                f"Correspondência proibida: {doador['basename']} → {alvo['basename']}. "
                "Textura base só pode substituir base; textura EF só pode substituir EF."
            )
        if doador and not doador.get("hash"):
            return f"Não foi possível validar o hash do doador: {doador['basename']}."

        chave_destino = alvo["basename"].lower()
        if chave_destino in destinos:
            return f"Destino duplicado no mapeamento: {alvo['basename']}."
        destinos.add(chave_destino)

    return None


def _validar_staging(mapeados, pasta_staging):
    """Bloqueia staging adulterado, sujo ou com extensões não injetáveis."""
    if not os.path.isdir(pasta_staging):
        return "Pasta de staging não encontrada."

    esperados = {
        item["alvo"]["basename"].lower(): item for item in mapeados
        if item.get("action", "replace") == "replace"
    }
    encontrados = {}

    for raiz, _, nomes in os.walk(pasta_staging):
        for nome in nomes:
            caminho = os.path.join(raiz, nome)
            rel = os.path.relpath(caminho, pasta_staging).replace("\\", "/")

            if rel == ARQUIVO_MANIFEST_STAGING:
                continue

            chave = nome.lower()
            item_esperado = esperados.get(chave)
            tipo_asset = (
                item_esperado["alvo"].get("asset_kind", "set")
                if item_esperado else None
            )
            if not _extensao_injetavel(nome, tipo_asset):
                return (
                    f"Staging inválido: arquivo não injetável encontrado: {rel}."
                )

            if "/" in rel:
                return f"Staging inválido: arquivo fora da raiz: {rel}."

            if chave in encontrados:
                return f"Staging inválido: arquivo duplicado: {nome}."
            encontrados[chave] = caminho

    extras = sorted(set(encontrados) - set(esperados))
    if extras:
        return f"Staging contém arquivo injetável não mapeado: {extras[0]}."

    ausentes = sorted(set(esperados) - set(encontrados))
    if ausentes:
        return f"Arquivo preparado ausente no staging: {ausentes[0]}."

    for chave, item in esperados.items():
        caminho = encontrados[chave]
        hash_atual = _sha256_file(caminho)
        hash_esperado = item["doador"].get("hash")
        if not hash_atual or hash_atual != hash_esperado:
            return f"Hash inválido no staging: {item['alvo']['basename']}."

    return None


def _sha256_file(path):
    """SHA-256 de um arquivo (leitura em blocos)."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _size_file(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return -1


def _carregar_indice_cliente_atualizado(pasta_jogo):
    """
    Reconstrói o índice para a pasta solicitada e descarta entradas obsoletas.

    O índice do AutoMod é persistente e pode ter sido criado para outro
    cliente. O Injetor não pode confiar em um JSON antigo antes de substituir
    arquivos, por isso força a atualização em cada simulação/injeção.

    Retorna (indice, pasta_absoluta, erro).
    """
    pasta_absoluta = os.path.abspath(os.path.normpath(pasta_jogo))
    if not os.path.isdir(pasta_absoluta):
        return None, pasta_absoluta, (
            f"Pasta do cliente não encontrada: {pasta_absoluta}"
        )

    if not criar_index_jogo(pasta_absoluta):
        return None, pasta_absoluta, (
            f"Não foi possível atualizar o índice do cliente: {pasta_absoluta}"
        )

    index_bruto = carregar_index_jogo(pasta_absoluta)
    if not isinstance(index_bruto, dict) or not index_bruto:
        return None, pasta_absoluta, (
            f"Nenhum arquivo foi indexado no cliente: {pasta_absoluta}"
        )

    index_validado = {}
    duplicados = {}
    raiz_normalizada = os.path.normcase(pasta_absoluta)
    for caminho in index_bruto.values():
        if not isinstance(caminho, str):
            continue
        caminho_absoluto = os.path.abspath(os.path.normpath(caminho))
        if not os.path.isfile(caminho_absoluto):
            continue
        try:
            dentro_da_raiz = (
                os.path.commonpath([raiz_normalizada, os.path.normcase(caminho_absoluto)])
                == raiz_normalizada
            )
        except (OSError, ValueError):
            dentro_da_raiz = False
        if not dentro_da_raiz:
            continue
        chave = os.path.basename(caminho_absoluto).lower()
        if chave in index_validado and index_validado[chave] != caminho_absoluto:
            duplicados.setdefault(chave, [index_validado[chave]]).append(caminho_absoluto)
        else:
            index_validado[chave] = caminho_absoluto

    for chave, caminhos in duplicados.items():
        index_validado[chave] = tuple(sorted(set(caminhos), key=str.lower))

    if not index_validado:
        return None, pasta_absoluta, (
            f"O índice atualizado não contém arquivos válidos em: {pasta_absoluta}"
        )

    return index_validado, pasta_absoluta, None



def _resolver_destino_indice(index, basename):
    valor = index.get(basename.lower())
    if isinstance(valor, tuple):
        relativos = ", ".join(valor[:5])
        return None, f"Destino ambíguo para {basename}: {len(valor)} arquivos encontrados ({relativos})."
    return valor, None

def _identificar_nome_arma(caminho_ou_nome):
    """Interpreta PREFIXO(2) + TIPO(3) + ID(5) + EF opcional."""
    nome = os.path.basename(str(caminho_ou_nome))
    stem, extensao = os.path.splitext(nome)
    stem = stem.upper()
    extensao = extensao.lower()
    efeito = extensao == ".ef" or (extensao == ".jit" and stem.endswith("EF"))
    identidade = stem[:-2] if (extensao == ".jit" and stem.endswith("EF")) else stem
    if len(identidade) != 10:
        return None

    prefixo = identidade[:2]
    tipo_arma = identidade[2:5]
    id_arma = identidade[5:10]
    if prefixo not in MAPA_ARMAS:
        return None
    if not tipo_arma.isalnum() or not id_arma.isalnum():
        return None
    return {
        "weapon_prefix": prefixo,
        "weapon_type": tipo_arma,
        "weapon_id": id_arma,
        "class_name": MAPA_ARMAS[prefixo],
        "effect": efeito,
    }


def _arquivos_relativos_diretos(pasta_asset, subpasta):
    pasta = os.path.join(pasta_asset, subpasta)
    if not os.path.isdir(pasta):
        return []
    return [
        f"{subpasta}/{nome}"
        for nome in sorted(os.listdir(pasta), key=str.lower)
        if os.path.isfile(os.path.join(pasta, nome))
    ]


def _inferir_manifest_arma(pasta_arma):
    """Reconhece uma arma organizada antes do weapon_manifest.json."""
    objetos = _arquivos_relativos_diretos(pasta_arma, "Objects")
    texturas = _arquivos_relativos_diretos(pasta_arma, "Texture")
    binarios = [
        rel for rel in objetos + texturas
        if os.path.splitext(rel)[1].lower() in EXTENSOES_POR_ASSET["weapon"]
    ]
    if not binarios:
        return None, (
            "Nenhum weapon_manifest.json ou arquivo original .MS3/.JIT "
            "foi encontrado na pasta de arma."
        )

    identidades = []
    for rel in binarios:
        identidade = _identificar_nome_arma(rel)
        if identidade is None:
            return None, f"Nome de arquivo de arma não reconhecido: {os.path.basename(rel)}."
        identidades.append(identidade)
    chaves = {
        (item["weapon_prefix"], item["weapon_type"], item["weapon_id"])
        for item in identidades
    }
    if len(chaves) != 1:
        return None, "A pasta contém arquivos originais de armas diferentes."
    prefixo, tipo_arma, id_arma = next(iter(chaves))
    if not any(os.path.splitext(rel)[1].lower() == ".ms3" for rel in objetos):
        return None, "Arquivo 3D original .MS3 não encontrado na pasta Objects."
    return {
        "schema_version": MANIFEST_SCHEMA,
        "asset_kind": "weapon",
        "weapon_prefix": prefixo,
        "weapon_type": tipo_arma,
        "weapon_id": id_arma,
        "class_code": prefixo,
        "class_name": MAPA_ARMAS[prefixo],
        "files": {"objects": objetos, "texture": texturas},
        "inferred_manifest": True,
    }, None


def ler_manifest_asset(pasta_asset, expected_kind=None):
    """Lê um set ou arma, mantendo os dois modos rigorosamente separados."""
    caminho_set = os.path.join(pasta_asset, ARQUIVO_MANIFEST_SET)
    caminho_arma = os.path.join(pasta_asset, "weapon_manifest.json")
    if os.path.isfile(caminho_set):
        caminho = caminho_set
        tipo_detectado = "set"
    elif os.path.isfile(caminho_arma):
        caminho = caminho_arma
        tipo_detectado = "weapon"
    else:
        if os.path.isfile(os.path.join(pasta_asset, "family_manifest.json")):
            return None, (
                "Selecione uma variante dentro da família, por exemplo "
                "Set_Armadura_1101, e não a pasta Familia_Armadura_11."
            )
        if expected_kind == "weapon":
            return _inferir_manifest_arma(pasta_asset)
        return None, "set_manifest.json não encontrado na pasta selecionada."

    if expected_kind and tipo_detectado != expected_kind:
        esperado = "set de armadura" if expected_kind == "set" else "arma"
        encontrado = "set de armadura" if tipo_detectado == "set" else "arma"
        return None, (
            f"Modo incompatível: foi selecionada uma pasta de {encontrado}, "
            f"mas o modo atual aceita somente {esperado}."
        )

    try:
        with open(caminho, "r", encoding="utf-8") as f:
            manifesto = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return None, f"Manifesto inválido ou ilegível: {e}"

    if not isinstance(manifesto, dict):
        return None, "Manifesto não é um objeto JSON válido."
    schema = manifesto.get("schema_version")
    if schema != MANIFEST_SCHEMA:
        return None, (
            f"Versão do manifesto ({schema}) não suportada "
            f"(esperado {MANIFEST_SCHEMA})."
        )

    tipo_asset = manifesto.get("asset_kind") or tipo_detectado
    if tipo_asset != tipo_detectado:
        return None, (
            f"Tipo do manifesto ({tipo_asset}) contradiz o arquivo "
            f"selecionado ({tipo_detectado})."
        )
    if tipo_asset == "set":
        obrigatorios = ("class_code", "class_name", "set_id")
    elif tipo_asset == "weapon":
        obrigatorios = (
            "class_code", "class_name", "weapon_prefix",
            "weapon_type", "weapon_id",
        )
    else:
        return None, f"Tipo de asset desconhecido no manifesto: {tipo_asset}."
    if any(not manifesto.get(campo) for campo in obrigatorios):
        return None, "Manifesto incompleto: identidade obrigatória ausente."

    # O diretório técnico faz parte da identidade produzida pelo Organizador.
    # Um manifesto movido/stale não pode preparar arquivos para outro asset.
    nome_pasta = os.path.basename(os.path.normpath(pasta_asset))
    if tipo_asset == "set":
        nome_esperado = f"Set_Armadura_{manifesto['set_id']}"
        if nome_pasta.lower() != nome_esperado.lower():
            return None, (
                f"Manifesto contradiz a pasta selecionada: esperado "
                f"{nome_esperado}, encontrado {nome_pasta}."
            )
        familia_id, variante_id = separar_familia_variante(manifesto["set_id"])
        if manifesto.get("visual_family_id", familia_id) != familia_id:
            return None, "Manifesto possui família incompatível com o set_id."
        if manifesto.get("variant_id", variante_id) != variante_id:
            return None, "Manifesto possui variante incompatível com o set_id."
        pasta_familia = os.path.basename(os.path.dirname(os.path.normpath(pasta_asset)))
        familia_esperada = f"Familia_Armadura_{familia_id}"
        pasta_classe = os.path.basename(
            os.path.dirname(os.path.dirname(os.path.normpath(pasta_asset)))
        )
        if (
            pasta_familia.lower() != familia_esperada.lower()
            or pasta_classe.lower() != str(manifesto["class_name"]).lower()
        ):
            return None, (
                "Manifesto contradiz a hierarquia da pasta selecionada: "
                f"esperado {manifesto['class_name']}/{familia_esperada}/{nome_esperado}."
            )
    else:
        nome_esperado = f"{manifesto['weapon_type']}_{manifesto['weapon_id']}"
        if nome_pasta.lower() != nome_esperado.lower():
            return None, (
                f"Manifesto contradiz a pasta selecionada: esperado "
                f"{nome_esperado}, encontrado {nome_pasta}."
            )
        pasta_armas = os.path.basename(os.path.dirname(os.path.normpath(pasta_asset)))
        pasta_classe = os.path.basename(
            os.path.dirname(os.path.dirname(os.path.normpath(pasta_asset)))
        )
        if (
            pasta_armas.lower() != "armas"
            or pasta_classe.lower() != str(manifesto["class_name"]).lower()
        ):
            return None, (
                "Manifesto contradiz a hierarquia da pasta selecionada: "
                f"esperado {manifesto['class_name']}/Armas/{nome_esperado}."
            )

    # Referências derivadas (OBJ/DDS/TGA/PNG) são opcionais para o Injetor.
    # Já todo payload nativo declarado deve existir e permanecer confinado à
    # pasta selecionada; manifesto stale ou com '..' não pode preparar dados.
    raiz_asset = os.path.normcase(os.path.realpath(os.path.abspath(pasta_asset)))
    files_section = manifesto.get("files", {})
    if not isinstance(files_section, dict):
        return None, "Seção files do manifesto deve ser um objeto JSON."
    for relativos in files_section.values():
        if not isinstance(relativos, list):
            continue
        for rel in relativos:
            if not isinstance(rel, str) or not _extensao_injetavel(rel, tipo_asset):
                continue
            caminho_referenciado = os.path.realpath(
                os.path.abspath(os.path.join(pasta_asset, rel.replace("/", os.sep)))
            )
            try:
                dentro_asset = (
                    os.path.commonpath([
                        raiz_asset, os.path.normcase(caminho_referenciado)
                    ]) == raiz_asset
                )
            except (OSError, ValueError):
                dentro_asset = False
            if not dentro_asset:
                return None, f"Payload nativo fora da pasta do asset: {rel}."
            if not os.path.isfile(caminho_referenciado):
                return None, f"Payload nativo apontado não encontrado: {rel}."

    manifesto["asset_kind"] = tipo_asset
    return manifesto, None


def ler_manifest_set(pasta_set):
    """Alias de compatibilidade para leitura de set."""
    return ler_manifest_asset(pasta_set, expected_kind="set")


def listar_arquivos_asset(pasta_asset, manifesto):
    """Lista binários originais permitidos pelo modo do manifesto."""
    tipo_asset = manifesto.get("asset_kind", "set")
    files_section = manifesto.get("files", {})
    categorias = (
        (("mesh", "mesh"), ("texture", None))
        if tipo_asset == "set"
        else (("objects", "object"), ("texture", None))
    )

    arquivos = []
    for secao, tipo_esperado_secao in categorias:
        for rel in files_section.get(secao, []):
            caminho = os.path.join(pasta_asset, rel.replace("/", os.sep))
            if not os.path.isfile(caminho):
                continue
            basename = os.path.basename(caminho)
            extensao = os.path.splitext(basename)[1].lower()
            if extensao not in EXTENSOES_POR_ASSET.get(tipo_asset, ()):
                continue
            tipo_real = TIPO_POR_EXTENSAO[extensao]
            if tipo_esperado_secao is not None and tipo_real != tipo_esperado_secao:
                continue
            tipo = tipo_real

            parte = None
            if tipo_asset == "set":
                nome_base = os.path.splitext(basename)[0].upper()
                nome_identidade = (
                    nome_base[:-2]
                    if extensao == ".jit" and nome_base.endswith("EF")
                    else nome_base
                )
                if not nome_identidade.startswith("CH") or len(nome_identidade) < 10:
                    continue
                if nome_identidade[2:4] != str(manifesto["class_code"])[-2:].upper():
                    continue
                if nome_identidade[6:10] != str(manifesto["set_id"]).upper():
                    continue
                parte = nome_identidade[4:6]
                slot = parte
            else:
                identidade = _identificar_nome_arma(basename)
                if identidade is None:
                    continue
                if (
                    identidade["weapon_prefix"] != manifesto["weapon_prefix"]
                    or identidade["weapon_type"] != manifesto["weapon_type"]
                    or identidade["weapon_id"] != manifesto["weapon_id"]
                ):
                    continue
                slot = "model" if tipo == "object" else _subtipo_asset(basename)

            arquivos.append({
                "relpath": rel,
                "basename": basename,
                "tipo": tipo,
                "extensao": extensao,
                "size": _size_file(caminho),
                "hash": _sha256_file(caminho),
                "parte": parte,
                "slot": slot,
                "asset_kind": tipo_asset,
                "subtipo": _subtipo_asset(basename),
                "caminho_real": caminho,
            })
    return arquivos


def listar_arquivos_set(pasta_set, manifesto):
    """Compatibilidade com integrações anteriores."""
    return listar_arquivos_asset(pasta_set, manifesto)


# ---------------------------------------------------------------------------
# 2. MAPEAMENTO DOADOR → ALVO
# ---------------------------------------------------------------------------
def _carregar_variante_base_alvo(info_alvo):
    """
    Localiza a variante física final 01 da mesma classe/família do alvo.

    A base serve ao fallback pontual de MSH e à sincronização da família quando
    ela possui mais peças MSH que a variante selecionada. Arquivos inexistentes
    nunca são herdados ou inventados.
    Retorna (arquivos_base, metadados, erro_informativo).
    """
    if info_alvo.get("asset_kind", "set") != "set":
        return [], None, None

    set_id = str(info_alvo.get("set_id") or "")
    familia_id, variante_id = separar_familia_variante(set_id)
    if not familia_id or variante_id == "01":
        return [], None, None

    set_id_base = f"{familia_id}01"
    pasta_base = os.path.join(
        os.path.dirname(os.path.abspath(info_alvo["pasta"])),
        f"Set_Armadura_{set_id_base}",
    )
    if not os.path.isdir(pasta_base):
        return [], None, (
            f"Variante base Set_Armadura_{set_id_base} não encontrada "
            "ao lado do set alvo."
        )

    manifesto_base, erro = ler_manifest_asset(
        pasta_base, expected_kind="set"
    )
    if erro:
        return [], None, f"Variante base {set_id_base} inválida: {erro}"
    if manifesto_base.get("class_code") != info_alvo.get("class_code"):
        return [], None, "A variante base localizada pertence a outra classe."

    familia_base, variante_base = separar_familia_variante(
        manifesto_base.get("set_id", "")
    )
    if familia_base != familia_id or variante_base != "01":
        return [], None, "A pasta localizada não é a base 01 da família alvo."

    arquivos = listar_arquivos_asset(pasta_base, manifesto_base)
    arquivos_mesh = [
        arquivo for arquivo in arquivos
        if arquivo.get("tipo") == "mesh" and arquivo.get("extensao") == ".msh"
    ]
    metadados = {
        "set_alvo_logico": set_id,
        "set_destino_fisico": set_id_base,
        "pasta_base": pasta_base,
        "arquivos_base": arquivos,
        "slots_mesh_base": sorted({
            arquivo.get("slot") if arquivo.get("slot") is not None
            else arquivo.get("parte")
            for arquivo in arquivos_mesh
        }),
    }
    return arquivos, metadados, None


def _resolver_estrutura_efetiva(info):
    arquivos_proprios = list(info.get("arquivos") or [])
    _, metadados_base, erro_base = _carregar_variante_base_alvo(info)
    arquivos_base = (metadados_base or {}).get("arquivos_base") or []

    def chave_recurso(arquivo):
        slot = (
            arquivo.get("slot") if arquivo.get("slot") is not None
            else arquivo.get("parte")
        )
        subtipo = arquivo.get("subtipo") or _subtipo_asset(arquivo.get("basename", ""))
        if arquivo.get("tipo") == "mesh" and arquivo.get("extensao") == ".msh":
            recurso = "msh"
        elif arquivo.get("extensao") == ".jit" and subtipo == "base":
            recurso = "jit"
        elif subtipo == "effect":
            recurso = "ef"
        else:
            return None
        return slot, recurso

    recursos_efetivos = {}
    for arquivo in arquivos_proprios:
        chave = chave_recurso(arquivo)
        if chave is not None:
            recursos_efetivos[chave] = arquivo
    herdados = []
    for arquivo in arquivos_base:
        chave = chave_recurso(arquivo)
        if chave is not None and chave not in recursos_efetivos:
            recursos_efetivos[chave] = arquivo
            herdados.append(arquivo)
    arquivos_efetivos = list(recursos_efetivos.values())
    estrutura = {}
    for arquivo in arquivos_efetivos:
        slot = (
            arquivo.get("slot") if arquivo.get("slot") is not None
            else arquivo.get("parte")
        )
        if slot is None:
            continue
        assinatura = estrutura.setdefault(slot, {
            "msh": False, "jit": False, "ef": False,
        })
        subtipo = arquivo.get("subtipo") or _subtipo_asset(arquivo.get("basename", ""))
        if arquivo.get("tipo") == "mesh" and arquivo.get("extensao") == ".msh":
            assinatura["msh"] = True
        elif arquivo.get("extensao") == ".jit" and subtipo == "base":
            assinatura["jit"] = True
        elif subtipo == "effect":
            assinatura["ef"] = True
    return {
        "estrutura": estrutura,
        "arquivos_efetivos": arquivos_efetivos,
        "arquivos_base_herdados": herdados,
        "usa_base": bool(herdados),
        "metadados_base": metadados_base,
        "erro_base": erro_base,
    }


def analisar_compatibilidade_estrutural(info_doador, info_alvo):
    if (
        info_doador.get("asset_kind", "set") != "set"
        or info_alvo.get("asset_kind", "set") != "set"
    ):
        return {"compativel": True, "divergencias": []}

    doador = _resolver_estrutura_efetiva(info_doador)
    alvo = _resolver_estrutura_efetiva(info_alvo)
    divergencias = []
    slots = sorted(set(doador["estrutura"]) | set(alvo["estrutura"]))
    for slot in slots:
        assinatura_doador = doador["estrutura"].get(
            slot, {"msh": False, "jit": False, "ef": False}
        )
        assinatura_alvo = alvo["estrutura"].get(
            slot, {"msh": False, "jit": False, "ef": False}
        )
        campos = [
            campo for campo in ("msh", "jit", "ef")
            if assinatura_doador[campo] != assinatura_alvo[campo]
        ]
        if campos:
            divergencias.append({
                "slot": slot,
                "doador": dict(assinatura_doador),
                "alvo": dict(assinatura_alvo),
                "campos": campos,
            })

    return {
        "compativel": not divergencias,
        "divergencias": divergencias,
        "doador": doador,
        "alvo": alvo,
    }


def _mensagem_incompatibilidade_estrutural(info_doador, info_alvo, analise):
    linhas = [
        "=== APARÊNCIAS INCOMPATÍVEIS ===",
        "",
        f"Doador: {info_doador.get('class_name')} Set {info_doador.get('set_id')}",
        f"Alvo: {info_alvo.get('class_name')} Set {info_alvo.get('set_id')}",
        "",
    ]
    for divergencia in analise.get("divergencias", []):
        doador = divergencia["doador"]
        alvo = divergencia["alvo"]
        sim_nao = lambda valor: "SIM" if valor else "NÃO"
        linhas.extend([
            f"Parte {divergencia['slot']}:",
            "Doador: "
            f"MSH {sim_nao(doador['msh'])} | JIT {sim_nao(doador['jit'])} | EF {sim_nao(doador['ef'])}",
            "Alvo efetivo: "
            f"MSH {sim_nao(alvo['msh'])} | JIT {sim_nao(alvo['jit'])} | EF {sim_nao(alvo['ef'])}",
            "",
        ])
    for lado, titulo in (("doador", "Doador"), ("alvo", "Alvo")):
        erro_base = (analise.get(lado) or {}).get("erro_base")
        if erro_base:
            linhas.append(f"{titulo}: {erro_base}")
    linhas.extend([
        "A injeção foi bloqueada porque as duas aparências possuem estruturas diferentes.",
        "Isso evita efeitos residuais incorretos, partes invisíveis e corrupção visual.",
        "Use outra aparência estruturalmente compatível.",
        "Status: INCOMPATÍVEL",
    ])
    return "\n".join(linhas)


def criar_mapa_doador_alvo(arquivos_doador, arquivos_alvo,
                            arquivos_base_alvo=None,
                            metadados_base=None):
    """
    Cria correspondências por slot + tipo + extensão + subtipo (base/EF).

    Retorna (mapeados, ignorados) onde:
      - mapeados: lista de dicts {doador, alvo}
      - ignorados: lista de dicts {arquivo, motivo}
    """
    # O subtipo impede colisão entre textura base e EF do mesmo slot.
    alvo_index = {}
    for a in arquivos_alvo:
        if _validar_item_injetavel(a, "Arquivo alvo"):
            continue
        subtipo = a.get("subtipo") or _subtipo_asset(a["basename"])
        slot = a.get("slot") if a.get("slot") is not None else a.get("parte")
        chave = (slot, a["tipo"], a["extensao"], subtipo)
        alvo_index[chave] = a

    # O arquivo da variante selecionada sempre vence; a base 01 só cobre um
    # recurso estrutural ausente no slot.
    base_index = {}
    for a in arquivos_base_alvo or []:
        if _validar_item_injetavel(a, "Arquivo base do alvo"):
            continue
        subtipo = a.get("subtipo") or _subtipo_asset(a["basename"])
        slot = a.get("slot") if a.get("slot") is not None else a.get("parte")
        chave = (slot, a.get("tipo"), a.get("extensao"), subtipo)
        base_index[chave] = a

    mapeados = []
    ignorados = []

    for d in arquivos_doador:
        erro_item = _validar_item_injetavel(d, "Arquivo doador")
        if erro_item:
            ignorados.append({
                "arquivo": d,
                "motivo": "IGNORADO — extensão de visualização/não injetável",
            })
            continue

        subtipo = d.get("subtipo") or _subtipo_asset(d["basename"])
        slot = d.get("slot") if d.get("slot") is not None else d.get("parte")
        chave = (slot, d["tipo"], d["extensao"], subtipo)
        alvo = alvo_index.get(chave)
        destino_compartilhado = False
        if (
            alvo is None
            and d.get("asset_kind", "set") == "set"
        ):
            alvo_base = base_index.get(chave)
            if alvo_base is not None:
                alvo = dict(alvo_base)
                alvo["destino_compartilhado"] = True
                alvo["set_alvo_logico"] = (metadados_base or {}).get(
                    "set_alvo_logico"
                )
                alvo["set_destino_fisico"] = (metadados_base or {}).get(
                    "set_destino_fisico"
                )
                destino_compartilhado = True
        if alvo is None:
            ignorados.append({
                "arquivo": d,
                "motivo": (
                    f"Sem destino no alvo (slot={slot}, tipo={d['tipo']}, "
                    f"ext={d['extensao']}, subtipo={subtipo})"
                ),
            })
        else:
            mapeados.append({
                "doador": d,
                "alvo": alvo,
                "destino_compartilhado": destino_compartilhado,
            })

    return mapeados, ignorados


def criar_mapa_para_infos(info_doador, info_alvo):
    """Cria o mapa completo, incluindo fallback físico na base 01 do alvo."""
    arquivos_base = []
    metadados_base = None
    aviso_base = None
    arquivos_doador = info_doador["arquivos"]
    if (
        info_doador.get("asset_kind", "set") == "set"
        and info_alvo.get("asset_kind", "set") == "set"
    ):
        analise = analisar_compatibilidade_estrutural(info_doador, info_alvo)
        if not analise["compativel"]:
            ignorados_incompativeis = [{
                "arquivo": {"basename": "Compatibilidade estrutural"},
                "motivo": _mensagem_incompatibilidade_estrutural(
                    info_doador, info_alvo, analise
                ),
                "incompatibilidade": analise,
            }]
            for divergencia in analise["divergencias"]:
                arquivo_slot = next((
                    arquivo for arquivo in analise["doador"]["arquivos_efetivos"]
                    if (arquivo.get("slot") if arquivo.get("slot") is not None
                        else arquivo.get("parte")) == divergencia["slot"]
                ), {"basename": f"Parte {divergencia['slot']}",
                    "parte": divergencia["slot"], "slot": divergencia["slot"]})
                ignorados_incompativeis.append({
                    "arquivo": arquivo_slot,
                    "motivo": (
                        f"Estrutura incompatível na parte {divergencia['slot']}: "
                        f"{', '.join(campo.upper() for campo in divergencia['campos'])}"
                    ),
                })
            return [], ignorados_incompativeis
        arquivos_doador = analise["doador"]["arquivos_efetivos"]
        arquivos_base, metadados_base, aviso_base = _carregar_variante_base_alvo(
            info_alvo
        )

    slots_mesh_alvo = {
        arquivo.get("slot") if arquivo.get("slot") is not None
        else arquivo.get("parte")
        for arquivo in info_alvo["arquivos"]
        if arquivo.get("tipo") == "mesh" and arquivo.get("extensao") == ".msh"
    }
    slots_mesh_base = set((metadados_base or {}).get("slots_mesh_base") or [])
    sincronizar_base = bool(
        info_doador.get("asset_kind", "set") == "set"
        and info_alvo.get("asset_kind", "set") == "set"
        and metadados_base
        and len(slots_mesh_base) > len(slots_mesh_alvo)
    )

    if sincronizar_base:
        # A aparência da base é preparada primeiro; depois a variante alvo é
        # aplicada diretamente. O fallback pontual não participa deste caminho,
        # evitando dois mapeamentos para o mesmo destino físico.
        mapeados_base, _ignorados_base = criar_mapa_doador_alvo(
            arquivos_doador,
            metadados_base.get("arquivos_base") or [],
        )
        mapeados_variante, _ignorados_variante = criar_mapa_doador_alvo(
            arquivos_doador,
            info_alvo["arquivos"],
        )

        for item in mapeados_base:
            alvo = dict(item["alvo"])
            alvo.update({
                "destino_compartilhado": True,
                "sincronizacao_base_familia": True,
                "escopo_destino": "base_familia",
                "set_alvo_logico": info_alvo.get("set_id"),
                "set_destino_fisico": metadados_base.get("set_destino_fisico"),
            })
            item["alvo"] = alvo
            item["destino_compartilhado"] = True
            item["sincronizacao_base_familia"] = True
            item["escopo_destino"] = "base_familia"

        for item in mapeados_variante:
            alvo = dict(item["alvo"])
            alvo.update({
                "sincronizacao_base_familia": False,
                "escopo_destino": "variante_alvo",
                "set_alvo_logico": info_alvo.get("set_id"),
                "set_destino_fisico": info_alvo.get("set_id"),
            })
            item["alvo"] = alvo
            item["sincronizacao_base_familia"] = False
            item["escopo_destino"] = "variante_alvo"

        # Em estruturas incomuns, a variante pode apontar para o mesmo basename
        # físico da base. A variante principal vence e cada destino aparece uma vez.
        basenames_variante = {
            item["alvo"]["basename"].lower() for item in mapeados_variante
        }
        mapeados_base = [
            item for item in mapeados_base
            if item["alvo"]["basename"].lower() not in basenames_variante
        ]
        mapeados = mapeados_base + mapeados_variante
        doadores_mapeados = {
            item["doador"].get("caminho_real") or item["doador"].get("basename")
            for item in mapeados
            if item.get("action", "replace") == "replace"
        }
        ignorados = [
            {
                "arquivo": arquivo,
                "motivo": (
                    "Sem destino equivalente na base 01 nem na variante alvo "
                    f"(slot={arquivo.get('slot') or arquivo.get('parte')}, "
                    f"tipo={arquivo.get('tipo')}, ext={arquivo.get('extensao')})"
                ),
            }
            for arquivo in arquivos_doador
            if (arquivo.get("caminho_real") or arquivo.get("basename"))
            not in doadores_mapeados
        ]
        return mapeados, ignorados

    mapeados, ignorados = criar_mapa_doador_alvo(
        arquivos_doador,
        info_alvo["arquivos"],
        arquivos_base_alvo=arquivos_base,
        metadados_base=metadados_base,
    )
    # Só exibe o aviso sobre a base ausente quando existe, de fato, algum MSH
    # do doador sem slot direto na variante selecionada. Assim uma variante
    # completa não recebe um alerta irrelevante apenas por não ter a pasta 01.
    slots_mesh_doador = {
        arquivo.get("slot") if arquivo.get("slot") is not None
        else arquivo.get("parte")
        for arquivo in info_doador["arquivos"]
        if arquivo.get("tipo") == "mesh" and arquivo.get("extensao") == ".msh"
    }
    if aviso_base and (slots_mesh_doador - slots_mesh_alvo):
        ignorados.append({
            "arquivo": {"basename": "Variante base 01"},
            "motivo": aviso_base,
            "aviso": True,
        })
    return mapeados, ignorados


# ---------------------------------------------------------------------------
# 3. STAGING (PREPARAÇÃO)
# ---------------------------------------------------------------------------
def preparar_set_staging(mapeados, pasta_staging):
    """
    Copia arquivos do doador para staging, renomeando para o basename do alvo.
    Gera manifesto da preparação.

    Retorna (manifesto_preparacao, erro).
    """
    if not mapeados:
        return None, "Operação incompatível ou sem arquivos mapeados. Preparação bloqueada."
    erro_mapa = _validar_mapeados(mapeados)
    if erro_mapa:
        return None, erro_mapa

    os.makedirs(pasta_staging, exist_ok=True)
    staging_files = []

    for item in mapeados:
        if item.get("action", "replace") == "delete":
            continue
        doador = item["doador"]
        alvo = item["alvo"]
        origem = doador["caminho_real"]
        destino = os.path.join(pasta_staging, alvo["basename"])

        tipo_asset = doador.get("asset_kind", "set")
        if (
            not _extensao_injetavel(origem, tipo_asset)
            or not _extensao_injetavel(destino, tipo_asset)
        ):
            return None, (
                f"Extensão bloqueada na preparação: {doador['basename']} → {alvo['basename']}."
            )

        try:
            shutil.copy2(origem, destino)
        except OSError as e:
            return None, f"Erro ao copiar {doador['basename']}: {e}"

        hash_preparado = _sha256_file(destino)
        if hash_preparado != doador["hash"]:
            return None, (
                f"Hash divergente após cópia: {doador['basename']} "
                f"(orig={doador['hash'][:16]}... copia={hash_preparado[:16]}...)"
            )

        staging_files.append({
            "doador_basename": doador["basename"],
            "alvo_basename": alvo["basename"],
            "tipo": doador["tipo"],
            "parte": doador["parte"],
            "slot": doador.get("slot"),
            "asset_kind": doador.get("asset_kind", "set"),
            "extensao": doador["extensao"],
            "subtipo": doador.get("subtipo") or _subtipo_asset(doador["basename"]),
            "size": doador["size"],
            "hash_doador": doador["hash"],
            "hash_preparado": hash_preparado,
            "destino_compartilhado": bool(
                item.get("destino_compartilhado")
                or alvo.get("destino_compartilhado")
            ),
            "sincronizacao_base_familia": bool(
                item.get("sincronizacao_base_familia")
                or alvo.get("sincronizacao_base_familia")
            ),
            "escopo_destino": (
                item.get("escopo_destino")
                or alvo.get("escopo_destino")
                or "variante_alvo"
            ),
            "set_alvo_logico": alvo.get("set_alvo_logico"),
            "set_destino_fisico": alvo.get("set_destino_fisico"),
            "status": "OK",
        })

    manifesto = {
        "schema_version": 1,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_preparados": len(staging_files),
        "total_efeitos_remover": sum(
            1 for item in mapeados if item.get("action") == "delete"
        ),
        "efeitos_remover": [
            {
                "action": "delete",
                "alvo_basename": item["alvo"]["basename"],
                "parte": item["alvo"].get("parte"),
                "slot": item["alvo"].get("slot"),
                "motivo": item.get("motivo"),
                "sincronizacao_base_familia": bool(
                    item.get("sincronizacao_base_familia")
                    or item["alvo"].get("sincronizacao_base_familia")
                ),
                "escopo_destino": (
                    item.get("escopo_destino")
                    or item["alvo"].get("escopo_destino")
                    or "variante_alvo"
                ),
            }
            for item in mapeados if item.get("action") == "delete"
        ],
        "total_destinos_compartilhados": sum(
            1 for arquivo in staging_files
            if arquivo.get("destino_compartilhado")
        ),
        "sincronizacao_base_familia": any(
            arquivo.get("sincronizacao_base_familia")
            for arquivo in staging_files
        ),
        "total_sincronizacao_base": sum(
            1 for arquivo in staging_files
            if arquivo.get("sincronizacao_base_familia")
        ),
        "total_variante_alvo": sum(
            1 for arquivo in staging_files
            if not arquivo.get("sincronizacao_base_familia")
        ),
        "files": staging_files,
    }

    caminho_manifesto = os.path.join(pasta_staging, ARQUIVO_MANIFEST_STAGING)
    tmp = caminho_manifesto + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifesto, f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho_manifesto)

    erro_staging = _validar_staging(mapeados, pasta_staging)
    if erro_staging:
        return None, erro_staging

    return manifesto, None


# ---------------------------------------------------------------------------
# 4. SIMULAÇÃO (DRY RUN)
# ---------------------------------------------------------------------------
def simular_injecao(mapeados, pasta_jogo=None):
    pasta_jogo = normalizar_pasta_jogo(pasta_jogo)
    """
    Simula a injeção: localiza destinos no cliente, verifica existência,
    planeja backup. Não modifica nada.

    Retorna dict com plano de substituição.
    """
    if not mapeados:
        return {"erro": "Operação incompatível ou sem arquivos mapeados. Simulação bloqueada."}
    erro_mapa = _validar_mapeados(mapeados)
    if erro_mapa:
        return {"erro": erro_mapa}

    index, pasta_jogo, erro_indice = _carregar_indice_cliente_atualizado(
        pasta_jogo
    )
    if erro_indice:
        return {"erro": erro_indice}

    plano = {
        "substituicoes": [],
        "remocoes_ef": [],
        "ignorados": [],
        "total": 0,
        "total_efeitos_remover": 0,
        "total_destinos_afetados": 0,
        "total_destinos_compartilhados": 0,
        "sincronizacao_base_familia": False,
        "total_sincronizacao_base": 0,
        "total_variante_alvo": 0,
        "pasta_jogo": pasta_jogo,
        "total_indexados": len(index),
        "indice_atualizado": True,
    }

    for item in mapeados:
        alvo = item["alvo"]
        basename_lower = alvo["basename"].lower()
        destino_cliente, erro_destino = _resolver_destino_indice(index, basename_lower)
        if erro_destino:
            return {"erro": erro_destino}

        if destino_cliente is None:
            plano["ignorados"].append({
                "basename": alvo["basename"],
                "motivo": "Arquivo não encontrado no cliente.",
            })
            continue

        tipo_asset = alvo.get("asset_kind", "set")
        if not _extensao_injetavel(destino_cliente, tipo_asset):
            return {
                "erro": (
                    f"Destino não injetável resolvido no cliente: {destino_cliente}."
                )
            }

        # Verificar se o backup já existe
        rel = os.path.relpath(destino_cliente, pasta_jogo).replace("\\", "/")
        caminho_backup = os.path.join(obter_pasta_backup_cliente(pasta_jogo), rel)

        if item.get("action") == "delete":
            plano["remocoes_ef"].append({
                "action": "delete",
                "alvo_basename": alvo["basename"],
                "destino_cliente": destino_cliente,
                "caminho_backup": caminho_backup,
                "backup_existente": os.path.isfile(caminho_backup) and _size_file(caminho_backup) > 0,
                "tamanho_alvo_atual": _size_file(destino_cliente),
                "parte": alvo.get("parte"),
                "slot": alvo.get("slot"),
                "motivo": item.get("motivo"),
                "sincronizacao_base_familia": bool(
                    item.get("sincronizacao_base_familia")
                    or alvo.get("sincronizacao_base_familia")
                ),
                "escopo_destino": (
                    item.get("escopo_destino")
                    or alvo.get("escopo_destino")
                    or "variante_alvo"
                ),
            })
            plano["total_efeitos_remover"] += 1
            continue

        plano["substituicoes"].append({
            "doador_basename": item["doador"]["basename"],
            "alvo_basename": alvo["basename"],
            "destino_cliente": destino_cliente,
            "caminho_backup": caminho_backup,
            "backup_existente": os.path.exists(caminho_backup),
            "tamanho_alvo_atual": _size_file(destino_cliente),
            "destino_compartilhado": bool(
                item.get("destino_compartilhado")
                or alvo.get("destino_compartilhado")
            ),
            "sincronizacao_base_familia": bool(
                item.get("sincronizacao_base_familia")
                or alvo.get("sincronizacao_base_familia")
            ),
            "escopo_destino": (
                item.get("escopo_destino")
                or alvo.get("escopo_destino")
                or "variante_alvo"
            ),
            "set_alvo_logico": alvo.get("set_alvo_logico"),
            "set_destino_fisico": alvo.get("set_destino_fisico"),
        })
        plano["total"] += 1
        if item.get("destino_compartilhado") or alvo.get("destino_compartilhado"):
            plano["total_destinos_compartilhados"] += 1
        if item.get("sincronizacao_base_familia") or alvo.get("sincronizacao_base_familia"):
            plano["sincronizacao_base_familia"] = True
            plano["total_sincronizacao_base"] += 1
        else:
            plano["total_variante_alvo"] += 1

    plano["total_destinos_afetados"] = plano["total"] + plano["total_efeitos_remover"]
    return plano



def _copiar_atomico_validado(origem, destino, hash_esperado=None):
    import tempfile, stat
    modo = os.stat(destino).st_mode if os.path.exists(destino) else None
    fd, tmp = tempfile.mkstemp(prefix=f".{os.path.basename(destino)}.", suffix=".set.tmp", dir=os.path.dirname(destino))
    os.close(fd)
    try:
        shutil.copy2(origem, tmp)
        hash_tmp = _sha256_file(tmp)
        if hash_esperado and hash_tmp != hash_esperado:
            raise OSError("hash do temporário diverge do staging")
        if os.path.exists(destino):
            try: os.chmod(destino, stat.S_IWRITE)
            except OSError: pass
        os.replace(tmp, destino); tmp = None
        if modo is not None:
            try: os.chmod(destino, modo)
            except OSError: pass
        if hash_esperado and _sha256_file(destino) != hash_esperado:
            raise OSError("hash final diverge do staging")
    finally:
        if tmp and os.path.exists(tmp):
            try: os.remove(tmp)
            except OSError: pass


# ---------------------------------------------------------------------------
# 5. INJEÇÃO
# ---------------------------------------------------------------------------
def injetar_set(mapeados, pasta_staging, pasta_jogo=None):
    pasta_jogo = normalizar_pasta_jogo(pasta_jogo)
    """
    Executa a injeção real: backup → substituição → validação → histórico.
    Rollback automático em caso de falha.

    Retorna (dict_resultado, erro).
    """
    if not mapeados:
        return None, "Operação incompatível ou sem arquivos mapeados. Injeção bloqueada."
    erro_mapa = _validar_mapeados(mapeados)
    if erro_mapa:
        return None, erro_mapa

    erro_staging = _validar_staging(mapeados, pasta_staging)
    if erro_staging:
        return None, erro_staging

    with lock_otimizacao:
        index, pasta_jogo, erro_indice = _carregar_indice_cliente_atualizado(
            pasta_jogo
        )
        if erro_indice:
            return None, erro_indice

        # Pré-validação completa: nenhuma escrita começa enquanto todos os
        # destinos, arquivos preparados, hashes e backups não estiverem OK.
        operacoes = []
        for item in mapeados:
            alvo = item["alvo"]
            acao = item.get("action", "replace")
            basename_lower = alvo["basename"].lower()
            destino_cliente, erro_destino = _resolver_destino_indice(index, basename_lower)
            if erro_destino:
                return None, erro_destino

            if destino_cliente is None:
                if acao == "delete":
                    continue
                return None, (
                    f"Arquivo alvo não encontrado no cliente: {alvo['basename']}. "
                    "Nenhum arquivo foi substituído."
                )

            tipo_asset = alvo.get("asset_kind", "set")
            if not _extensao_injetavel(destino_cliente, tipo_asset):
                return None, (
                    f"Destino não injetável bloqueado: {destino_cliente}."
                )

            origem_staging = None
            if acao == "replace":
                # Caminho do arquivo preparado no staging
                origem_staging = os.path.join(pasta_staging, alvo["basename"])
                if not os.path.isfile(origem_staging):
                    return None, (
                        f"Arquivo preparado não encontrado no staging: "
                        f"{alvo['basename']}. Nenhum arquivo foi substituído."
                    )

                if not _extensao_injetavel(origem_staging, tipo_asset):
                    return None, f"Arquivo de staging não injetável bloqueado: {origem_staging}."

                hash_staging = _sha256_file(origem_staging)
                if not hash_staging or hash_staging != item["doador"]["hash"]:
                    return None, f"Hash do staging inválido para {alvo['basename']}."

            rel = os.path.relpath(destino_cliente, pasta_jogo).replace("\\", "/")
            caminho_backup = os.path.join(obter_pasta_backup_cliente(pasta_jogo), rel)
            operacoes.append({
                "action": acao,
                "item": item,
                "alvo": alvo,
                "origem_staging": origem_staging,
                "destino_cliente": destino_cliente,
                "caminho_backup": caminho_backup,
            })

        # Todos os backups são garantidos antes da primeira substituição.
        for operacao in operacoes:
            caminho_backup = operacao["caminho_backup"]
            backup_valido = (
                os.path.isfile(caminho_backup)
                and os.path.getsize(caminho_backup) > 0
            )
            if not backup_valido:
                if not fazer_backup_rapido(
                    operacao["destino_cliente"], caminho_backup
                ):
                    return None, (
                        f"Falha ao criar backup de "
                        f"{operacao['alvo']['basename']}. "
                        "Nenhum arquivo foi substituído."
                    )
            if (
                not os.path.isfile(caminho_backup)
                or os.path.getsize(caminho_backup) <= 0
            ):
                return None, (
                    f"Backup inválido de {operacao['alvo']['basename']}. "
                    "Nenhum arquivo foi substituído."
                )

        substituidos = []
        efeitos_removidos = []
        rollback_stack = []
        for operacao in [o for o in operacoes if o["action"] == "replace"]:
            item = operacao["item"]
            alvo = operacao["alvo"]
            origem_staging = operacao["origem_staging"]
            destino_cliente = operacao["destino_cliente"]
            caminho_backup = operacao["caminho_backup"]
            rollback_stack.append((caminho_backup, destino_cliente))

            # Substituição atômica + validação
            hash_esperado = item["doador"]["hash"]
            try:
                _copiar_atomico_validado(origem_staging, destino_cliente, hash_esperado)
            except OSError as e:
                rollback_ok, rollback_erros = _rollback_parcial(rollback_stack, pasta_jogo)
                detalhe = "rollback OK" if rollback_ok else f"rollback com falhas: {rollback_erros}"
                return None, f"Falha na substituição de {alvo['basename']}: {e}. {detalhe}."

            substituidos.append({
                "doador_basename": item["doador"]["basename"],
                "alvo_basename": alvo["basename"],
                "destino": destino_cliente,
                "backup": caminho_backup,
                "destino_compartilhado": bool(
                    item.get("destino_compartilhado")
                    or alvo.get("destino_compartilhado")
                ),
                "sincronizacao_base_familia": bool(
                    item.get("sincronizacao_base_familia")
                    or alvo.get("sincronizacao_base_familia")
                ),
                "escopo_destino": (
                    item.get("escopo_destino")
                    or alvo.get("escopo_destino")
                    or "variante_alvo"
                ),
                "set_alvo_logico": alvo.get("set_alvo_logico"),
                "set_destino_fisico": alvo.get("set_destino_fisico"),
            })

        for operacao in [o for o in operacoes if o["action"] == "delete"]:
            alvo = operacao["alvo"]
            destino_cliente = operacao["destino_cliente"]
            caminho_backup = operacao["caminho_backup"]
            rollback_stack.append((caminho_backup, destino_cliente))
            try:
                os.remove(destino_cliente)
                if os.path.exists(destino_cliente):
                    raise OSError("arquivo EF permaneceu no destino")
            except OSError as e:
                rollback_ok, rollback_erros = _rollback_parcial(rollback_stack, pasta_jogo)
                detalhe = "rollback OK" if rollback_ok else f"rollback com falhas: {rollback_erros}"
                return None, f"Falha na remoção de {alvo['basename']}: {e}. {detalhe}."

            efeitos_removidos.append({
                "action": "DELETE",
                "alvo_basename": alvo["basename"],
                "destino": destino_cliente,
                "backup": caminho_backup,
                "parte": alvo.get("parte"),
                "slot": alvo.get("slot"),
                "motivo": operacao["item"].get("motivo"),
                "sincronizacao_base_familia": bool(
                    operacao["item"].get("sincronizacao_base_familia")
                    or alvo.get("sincronizacao_base_familia")
                ),
                "escopo_destino": (
                    operacao["item"].get("escopo_destino")
                    or alvo.get("escopo_destino")
                    or "variante_alvo"
                ),
                "set_alvo_logico": alvo.get("set_alvo_logico"),
                "set_destino_fisico": alvo.get("set_destino_fisico"),
            })

        # Histórico faz parte da transação: preserve o estado anterior do cliente.
        historico_antes = carregar_historico_automod(pasta_jogo)
        for operacao in operacoes:
            origem_historico = (
                operacao["origem_staging"]
                if operacao["action"] == "replace"
                else operacao["caminho_backup"]
            )
            nome_historico = (
                operacao["item"]["doador"]["basename"]
                if operacao["action"] == "replace"
                else f"{operacao['alvo']['basename']} [REMOVIDO]"
            )
            if not registrar_mod_ativo(
                operacao["destino_cliente"],
                origem_historico,
                pasta_jogo,
                mod_nome=nome_historico,
                categoria=operacao["alvo"].get("asset_kind", "set"),
            ):
                rollback_ok, rollback_erros = _rollback_parcial(rollback_stack, pasta_jogo)
                historico_ok = salvar_historico_automod(historico_antes, pasta_jogo)
                detalhe = "rollback OK" if rollback_ok else f"rollback com falhas: {rollback_erros}"
                if not historico_ok:
                    detalhe += "; restauração do histórico também falhou"
                return None, f"Falha ao persistir histórico de {operacao['alvo']['basename']}; {detalhe}."

        historico_atual = carregar_historico_automod(pasta_jogo)
        for operacao in operacoes:
            rel = os.path.relpath(
                operacao["destino_cliente"], pasta_jogo
            ).replace("\\", "/")
            item_historico = historico_atual.get("items", {}).get(rel.lower())
            if item_historico is not None:
                item_historico["operation"] = (
                    "DELETE" if operacao["action"] == "delete" else "REPLACE"
                )
        if not salvar_historico_automod(historico_atual, pasta_jogo):
            rollback_ok, rollback_erros = _rollback_parcial(rollback_stack, pasta_jogo)
            historico_ok = salvar_historico_automod(historico_antes, pasta_jogo)
            detalhe = "rollback OK" if rollback_ok else f"rollback com falhas: {rollback_erros}"
            if not historico_ok:
                detalhe += "; restauração do histórico também falhou"
            return None, f"Falha ao persistir tipos de operação no histórico; {detalhe}."

        resultado = {
            "substituidos": substituidos,
            "efeitos_removidos": efeitos_removidos,
            "falhas": [],
            "total_substituidos": len(substituidos),
            "total_efeitos_removidos": len(efeitos_removidos),
            "total_falhas": 0,
            "total_destinos_compartilhados": sum(
                1 for item in substituidos
                if item.get("destino_compartilhado")
            ),
            "sincronizacao_base_familia": any(
                item.get("sincronizacao_base_familia")
                for item in substituidos
            ),
            "total_sincronizacao_base": sum(
                1 for item in substituidos
                if item.get("sincronizacao_base_familia")
            ),
            "total_variante_alvo": sum(
                1 for item in substituidos
                if not item.get("sincronizacao_base_familia")
            ),
        }
        return resultado, None


def _rollback_parcial(rollback_stack, pasta_jogo):
    """Restaura arquivos substituídos, valida hash e reporta falhas."""
    erros = []
    for caminho_backup, destino in reversed(rollback_stack):
        try:
            if not os.path.isfile(caminho_backup):
                raise OSError("backup ausente")
            _copiar_atomico_validado(caminho_backup, destino, _sha256_file(caminho_backup))
        except Exception as e:
            erros.append(f"{os.path.basename(destino)}: {e}")
    return not erros, erros


def restaurar_ef_removido(chave_mod, pasta_jogo=None):
    pasta_jogo = normalizar_pasta_jogo(pasta_jogo)
    with lock_otimizacao:
        dados = carregar_historico_automod(pasta_jogo)
        item = dados.get("items", {}).get(chave_mod)
        if item is None:
            return False, "Item não encontrado no histórico."
        if item.get("operation") != "DELETE":
            return False, "O item não registra uma remoção EF."
        target_rel = item.get("target_relpath") or item.get("backup_relpath")
        if not target_rel:
            return False, "Caminho relativo ausente no histórico."
        destino = os.path.abspath(os.path.join(
            pasta_jogo, target_rel.replace("/", os.sep)
        ))
        try:
            if os.path.commonpath([pasta_jogo, destino]) != pasta_jogo:
                return False, "Destino fora da pasta do jogo (bloqueado)."
        except (OSError, ValueError):
            return False, "Destino fora da pasta do jogo (bloqueado)."
        caminho_backup = os.path.join(
            obter_pasta_backup_cliente(pasta_jogo),
            target_rel.replace("/", os.sep),
        )
        if not os.path.isfile(caminho_backup) or _size_file(caminho_backup) <= 0:
            return False, "Backup original não encontrado."

        destino_existia = os.path.isfile(destino)
        rollback_destino = destino + ".ef.restore.rollback"
        try:
            if destino_existia:
                shutil.copy2(destino, rollback_destino)
            _copiar_atomico_validado(
                caminho_backup, destino, _sha256_file(caminho_backup)
            )
        except Exception as e:
            if os.path.exists(rollback_destino):
                try: os.remove(rollback_destino)
                except OSError: pass
            return False, f"Não foi possível restaurar {item.get('target_name') or os.path.basename(destino)}: {e}"

        historico_antes = json.loads(json.dumps(dados))
        del dados["items"][chave_mod]
        if not salvar_historico_automod(dados, pasta_jogo):
            try:
                if destino_existia:
                    _copiar_atomico_validado(
                        rollback_destino, destino, _sha256_file(rollback_destino)
                    )
                elif os.path.exists(destino):
                    os.remove(destino)
            except Exception as e:
                return False, f"Histórico falhou e rollback do arquivo também falhou: {e}"
            finally:
                if os.path.exists(rollback_destino):
                    try: os.remove(rollback_destino)
                    except OSError: pass
            salvar_historico_automod(historico_antes, pasta_jogo)
            return False, "O EF não foi restaurado porque o histórico não pôde ser persistido; rollback aplicado."

        if os.path.exists(rollback_destino):
            try: os.remove(rollback_destino)
            except OSError: pass
        return True, f"{item.get('target_name') or os.path.basename(destino)} restaurado para o original."


# ---------------------------------------------------------------------------
# 6. WORKER (para uso com QThread)
# ---------------------------------------------------------------------------
class SetInjectorWorker:
    """Encapsula os modos independentes de Sets e Armas em background."""

    def __init__(self):
        self._cancel_event = threading.Event()

    def cancel(self):
        self._cancel_event.set()

    def _cancelado(self):
        return self._cancel_event.is_set()

    def validar_pasta(self, pasta, expected_kind=None):
        """Valida uma pasta no modo explicitamente selecionado pela interface."""
        manifesto, erro = ler_manifest_asset(pasta, expected_kind=expected_kind)
        if erro:
            return None, erro

        arquivos = listar_arquivos_asset(pasta, manifesto)
        if not arquivos:
            return None, "Nenhum arquivo original injetável foi encontrado."

        tipo_asset = manifesto.get("asset_kind", "set")
        partes = sorted({
            arquivo["parte"] for arquivo in arquivos
            if arquivo["extensao"] == ".msh" and arquivo.get("parte")
        })
        familia_id, variante_id = separar_familia_variante(
            manifesto.get("set_id", "")
        )
        info = {
            "pasta": pasta,
            "asset_kind": tipo_asset,
            "class_code": manifesto["class_code"],
            "class_name": manifesto["class_name"],
            "set_id": manifesto.get("set_id"),
            "visual_family_id": manifesto.get("visual_family_id", familia_id),
            "variant_id": manifesto.get("variant_id", variante_id),
            "weapon_prefix": manifesto.get("weapon_prefix"),
            "weapon_type": manifesto.get("weapon_type"),
            "weapon_id": manifesto.get("weapon_id"),
            "available_parts": partes,
            "piece_count": len(partes),
            "appearance_scope": manifesto.get(
                "appearance_scope", classificar_aparencia(partes)
            ),
            "total_meshes": sum(1 for a in arquivos if a["extensao"] == ".msh"),
            "total_ms3": sum(1 for a in arquivos if a["extensao"] == ".ms3"),
            "total_textures": sum(1 for a in arquivos if a["extensao"] == ".jit"),
            "total_effects": sum(
                1 for a in arquivos
                if a["extensao"] == ".jit" and a["subtipo"] == "effect"
            ),
            "arquivos": arquivos,
            "manifesto": manifesto,
            "manifest_inferred": bool(manifesto.get("inferred_manifest")),
        }
        return info, None

    def preparar(self, info_doador, info_alvo, pasta_staging):
        """Prepara o set em staging. Retorna (manifesto, ignorados, erro)."""
        if self._cancelado():
            return None, None, "Cancelado."

        tipo_doador = info_doador.get("asset_kind", "set")
        tipo_alvo = info_alvo.get("asset_kind", "set")
        if tipo_doador != tipo_alvo:
            return None, None, "Não é permitido combinar uma armadura com uma arma."

        if tipo_doador == "set":
            if info_doador["class_code"] != info_alvo["class_code"]:
                return None, None, (
                    f"Classes diferentes: doador={info_doador['class_name']} "
                    f"({info_doador['class_code']}) vs alvo={info_alvo['class_name']} "
                    f"({info_alvo['class_code']})."
                )
        elif tipo_doador == "weapon":
            if info_doador["weapon_prefix"] != info_alvo["weapon_prefix"]:
                return None, None, (
                    "Armas de classes diferentes não podem ser combinadas: "
                    f"{info_doador['class_name']} → {info_alvo['class_name']}."
                )
            if info_doador["weapon_type"] != info_alvo["weapon_type"]:
                return None, None, (
                    "Tipos de arma diferentes não podem ser combinados: "
                    f"{info_doador['weapon_type']} → {info_alvo['weapon_type']}."
                )
        else:
            return None, None, f"Tipo de asset desconhecido: {tipo_doador}."

        mapeados, ignorados = criar_mapa_para_infos(
            info_doador, info_alvo
        )

        if not mapeados:
            incompatibilidade = next(
                (item for item in ignorados if item.get("incompatibilidade")), None
            )
            if incompatibilidade:
                return None, ignorados, incompatibilidade["motivo"]
            return None, ignorados, "Nenhum arquivo pôde ser mapeado entre doador e alvo."

        if self._cancelado():
            return None, None, "Cancelado."

        # Limpar staging anterior
        if os.path.isdir(pasta_staging):
            try:
                shutil.rmtree(pasta_staging)
            except OSError:
                pass

        manifesto, erro = preparar_set_staging(mapeados, pasta_staging)
        if erro:
            return None, ignorados, erro

        return manifesto, ignorados, None

    def simular(self, mapeados, pasta_jogo=None):
        """Simula a injeção. Retorna (plano, erro)."""
        if self._cancelado():
            return None, "Cancelado."
        plano = simular_injecao(mapeados, pasta_jogo)
        if "erro" in plano:
            return None, plano["erro"]
        return plano, None

    def injetar(self, mapeados, pasta_staging, pasta_jogo=None):
        """Executa a injeção real. Retorna (resultado, erro)."""
        if self._cancelado():
            return None, "Cancelado."
        return injetar_set(mapeados, pasta_staging, pasta_jogo)
