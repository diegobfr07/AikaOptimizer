# -*- coding: utf-8 -*-
"""Serviço puro do módulo Renderizador (dgVoodoo2).

Backend SEM interface gráfica: detecta o estado gráfico do cliente Aika e
gerencia a instalação/restauração de dgVoodoo2 de forma transacional e
recuperável, operando somente com cópias na pasta do cliente.

Regras fundamentais:
- Nunca modifica ``third_party/dgvoodoo2/*`` (templates/base).
- Considera SOMENTE o arquivo de nome exato ``d3d9.dll`` no cliente.
  ``d3d9d.dll``, ``d3dx9_43.dll``, ``d3dx9d_33.dll`` e ``D3dx9d_43.dll``
  são originais do cliente e NUNCA são tocadas.
- Nunca sobrescreve/remove/renomeia um d3d9.dll não reconhecido.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

import config
import seguranca

# Estágio 5A — integração gradual do engine de configuração.
# O engine é importado SOMENTE para o caminho de aplicação de perfil e é usado
# com PARITY GUARD: legado continua sendo o oráculo de segurança e o produtor
# oficial de Ativar/Reaplicar. Nenhuma responsabilidade do serviço é movida.
import dgvoodoo_config_engine as _config_engine  # noqa: E402
import dgvoodoo_config_schema as _config_schema  # noqa: E402

# ---------------------------------------------------------------------------
# Nomes lógicos
# ---------------------------------------------------------------------------

D3D9_DLL = "d3d9.dll"
DGVOODOO_CONF = "dgVoodoo.conf"


def _nome_exato_d3d9(nome: str) -> bool:
    """True somente para o nome exato ``d3d9.dll`` (case-insensitive)."""
    return isinstance(nome, str) and nome.strip().lower() == D3D9_DLL


# ---------------------------------------------------------------------------
# Templates (somente leitura)
# ---------------------------------------------------------------------------

TEMPLATE_REL_PATH = "third_party/dgvoodoo2"


def _resolver_template(caminho_relativo: str) -> str:
    """Resolve um arquivo de template em dev e em build PyInstaller.

    Nunca depende do CWD. Em build frozen tenta ``sys.executable`` e
    ``sys._MEIPASS``; em desenvolvimento usa o diretório deste módulo.
    """
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        candidato = os.path.join(base, caminho_relativo)
        if os.path.isfile(candidato):
            return candidato
        base = getattr(sys, "_MEIPASS", None)
        if base:
            candidato = os.path.join(base, caminho_relativo)
            if os.path.isfile(candidato):
                return candidato
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, caminho_relativo)


def resolver_template_d3d9() -> str:
    """Caminho absoluto do template ``D3D9.dll`` (third_party/dgvoodoo2)."""
    return _resolver_template(os.path.join(TEMPLATE_REL_PATH, "D3D9.dll"))


def resolver_template_conf() -> str:
    """Caminho absoluto do template ``dgVoodoo.conf``."""
    return _resolver_template(os.path.join(TEMPLATE_REL_PATH, "dgVoodoo.conf"))


def validar_templates() -> list[str]:
    """Retorna lista de erros; vazia se os dois templates existem."""
    erros = []
    for caminho in (resolver_template_d3d9(), resolver_template_conf()):
        if not os.path.isfile(caminho):
            erros.append(f"Template ausente: {caminho}")
        elif os.path.getsize(caminho) <= 0:
            erros.append(f"Template vazio: {caminho}")
    return erros
# ---------------------------------------------------------------------------
# Estado persistente (namespace por cliente)
# ---------------------------------------------------------------------------

NOME_SUBDIR = "dgvoodoo"
ARQUIVO_ESTADO = "estado.json"


def _pasta_estado_cliente(pasta_jogo: str) -> str:
    """Namespace persistente do módulo dentro do backup do cliente."""
    return os.path.join(
        config.obter_pasta_backup_cliente(pasta_jogo, criar=True),
        NOME_SUBDIR,
    )


def _caminho_estado(pasta_jogo: str) -> str:
    return os.path.join(_pasta_estado_cliente(pasta_jogo), ARQUIVO_ESTADO)


def _sha256_arquivo(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _escrita_atomica(caminho: str, dados: bytes) -> None:
    """Escrita atômica com tmp+flush+fsync+os.replace no padrão das Pedras."""
    diretorio = os.path.dirname(caminho)
    os.makedirs(diretorio, exist_ok=True)
    descritor = -1
    temporario = None
    try:
        descritor, nome = tempfile.mkstemp(
            prefix=f".{os.path.basename(caminho)}.",
            suffix=".tmp",
            dir=diretorio,
        )
        temporario = nome
        with os.fdopen(descritor, "wb") as handle:
            descritor = -1
            handle.write(dados)
            handle.flush()
            os.fsync(handle.fileno())
        if os.path.exists(caminho):
            try:
                os.chmod(caminho, stat.S_IWRITE)
            except OSError:
                pass
        os.replace(temporario, caminho)
        temporario = None
    finally:
        if descritor >= 0:
            try:
                os.close(descritor)
            except OSError:
                pass
        if temporario is not None and os.path.exists(temporario):
            try:
                os.unlink(temporario)
            except OSError:
                pass


def _carregar_estado(pasta_jogo: str) -> Optional[dict]:
    """Carrega estado.json; retorna None se ausente/corrompido/inválido."""
    caminho = _caminho_estado(pasta_jogo)
    try:
        if not os.path.isfile(caminho):
            return None
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if not isinstance(dados, dict):
            return None
        return dados
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None


def _salvar_estado(pasta_jogo: str, estado: dict) -> None:
    payload = json.dumps(estado, ensure_ascii=False, indent=2).encode("utf-8")
    _escrita_atomica(_caminho_estado(pasta_jogo), payload)


def _remover_estado(pasta_jogo: str) -> None:
    caminho = _caminho_estado(pasta_jogo)
    try:
        if os.path.isfile(caminho):
            os.chmod(caminho, stat.S_IWRITE)
            os.remove(caminho)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Lock único por cliente
# ---------------------------------------------------------------------------

_locks_por_cliente: dict[str, threading.RLock] = {}
_locks_guard: threading.Lock = threading.Lock()


def _lock_do_cliente(pasta_jogo: str) -> threading.RLock:
    chave = os.path.normcase(os.path.abspath(pasta_jogo))
    with _locks_guard:
        lock = _locks_por_cliente.get(chave)
        if lock is None:
            lock = threading.RLock()
            _locks_por_cliente[chave] = lock
        return lock


# ---------------------------------------------------------------------------
# Estados do serviço
# ---------------------------------------------------------------------------

class Estado(Enum):
    ORIGINAL = "original"
    ATIVO = "ativo"
    CONFLITO = "conflito"
    INCOMPLETO = "incompleto"
    MODIFICADO_EXTERNAMENTE = "modificado_externamente"
    TEMPLATE_AUSENTE = "template_ausente"
    ERRO = "erro"
    JOGO_ABERTO = "jogo_aberto"


@dataclass
class EstadoDetectado:
    estado: Estado
    cliente: str
    dll_existe: bool = False
    dll_hash_atual: Optional[str] = None
    conf_existe: bool = False
    template_hash: Optional[str] = None
    mensagem: str = ""
    detalhes_conflito: Optional[dict] = None
    estado_persistido: Optional[dict] = None


@dataclass
class ResultadoOperacao:
    ok: bool
    estado: Estado
    mensagem: str
    dados: Optional[dict] = None
# ---------------------------------------------------------------------------
# Preset "Aika Recomendado" (grafia real confirmada no template)
# ---------------------------------------------------------------------------

PRESET_CONF = {
    # Base fixa do Aika sobre o template OFICIAL dgVoodoo2 2.87.4.
    # Valores obrigatorios: OutputAPI = d3d11_fl11_0 (DX11, nunca DX12)
    # e dgVoodooWatermark = false (watermark nunca exibida).
    #
    # Os demais valores abaixo preservam a configuracao validada em campo
    # (template 2.87.3 do Aika + PRESET). No conf OFICIAL 2.87.4 os
    # defaults mudaram (Adapters=all, FullScreenMode=true,
    # DisableScreenSaver=false, VRAM=256, FastVideoMemoryAccess=false,
    # KeepFilterIfPointSampled=false, AA/Filtering=appdriven, watermark=true)
    # e, para nao alterar o comportamento do cliente, sao fixados aqui.
    "[General]": {
        "OutputAPI": "d3d11_fl11_0",
        "Adapters": "1",
        "FullScreenMode": "false",
        "DisableScreenSaver": "true",
    },
    "[DirectX]": {
        "DisableAndPassThru": "false",
        "VideoCard": "internal3D",
        "VRAM": "1024",
        "Filtering": "16",
        "Antialiasing": "2x",
        "KeepFilterIfPointSampled": "true",
        "AppControlledScreenMode": "true",
        "DisableAltEnterToToggleScreenMode": "true",
        "FastVideoMemoryAccess": "true",
        "dgVoodooWatermark": "false",
    },
}


# ---------------------------------------------------------------------------
# Perfis gráficos (V2.2) — sobre a BASE validada em campo
# ---------------------------------------------------------------------------

PERFIL_PERFORMANCE = "performance"
PERFIL_BALANCED = "balanced"
PERFIL_QUALITY = "quality"
PERFIL_AUTO = "auto"

# Perfis gráficos que possuem configuração própria no conf.
PERFIS_SUPORTADOS = (PERFIL_PERFORMANCE, PERFIL_BALANCED, PERFIL_QUALITY)

# Escolhas do usuário: AUTO resolve internamente para um dos 3 perfis.
PERFIS_ESCOLHIVEIS = (PERFIL_AUTO,) + PERFIS_SUPORTADOS

# Nomes de exibição (usados por UI/log).
PERFIL_NOME_EXIBICAO = {
    PERFIL_PERFORMANCE: "Desempenho",
    PERFIL_BALANCED: "Equilibrado",
    PERFIL_QUALITY: "Qualidade",
}

PERFIL_AUTO_LABEL = "AUTO"

# Valores canônicos do preset legado da V1.
PRESET_LEGADO_AIKA = "Aika Recomendado"

# Diferenciais de cada perfil sobre o template. O perfil "balanced"
# corresponde EXATAMENTE à configuração validada em campo (V1).
PERFIS_CONF = {
    PERFIL_PERFORMANCE: {
        "[DirectX]": {
            "Antialiasing": "appdriven",
            "Filtering": "trilinear",
        },
    },
    PERFIL_BALANCED: {
        "[DirectX]": {
            "Antialiasing": "2x",
            "Filtering": "16",
        },
    },
    PERFIL_QUALITY: {
        "[DirectX]": {
            "Antialiasing": "4x",
            "Filtering": "16",
        },
    },
}

def _perfil_normalizado(preset: Optional[str]) -> str:
    """Mapeia o valor de ``preset`` persistido para um perfil canônico.

    O preset legado da V1 ("Aika Recomendado") é interpretado como balanced.
    Valores ausentes/desconhecidos caem no fallback seguro (balanced).
    """
    if preset in PERFIS_SUPORTADOS:
        return preset
    if preset == PRESET_LEGADO_AIKA:
        return PERFIL_BALANCED
    return PERFIL_BALANCED


def _resolved_profile_estado(estado: Optional[dict]) -> Optional[str]:
    """Retorna ``resolved_profile`` persistido se for um dos 3 perfis gráficos.

    AUTO resolve internamente para performance|balanced|quality. Qualquer
    outro valor persistido (incluindo ``auto``) é ignorado.
    """
    if not isinstance(estado, dict):
        return None
    resolved = estado.get("resolved_profile")
    if resolved in PERFIS_SUPORTADOS:
        return resolved
    return None


def _perfil_escolhido_estado(estado: Optional[dict]) -> str:
    """Perfil ESCOLHIDO pelo usuário, normalizado para exibição/UI.

    Retorna ``auto`` quando o preset persistido é AUTO; caso contrário,
    normaliza para um dos 3 perfis (preservando o legado "Aika Recomendado"
    -> balanced). NUNCA converte ``auto`` em balanced cegamente.
    """
    if not isinstance(estado, dict):
        return PERFIL_BALANCED
    preset = estado.get("preset")
    if preset == PERFIL_AUTO:
        return PERFIL_AUTO
    return _perfil_normalizado(preset)


def _perfil_efetivo_estado(estado: Optional[dict]) -> str:
    """Perfil EFETIVAMENTE aplicado no dgVoodoo.conf, normalizado.

    - preset manual (ou legado): o próprio perfil normalizado;
    - preset AUTO: o ``resolved_profile`` persistido (fallback balanced se
      ausente/inválido — nunca aplica "auto" como configuração).
    """
    if not isinstance(estado, dict):
        return PERFIL_BALANCED
    preset = estado.get("preset")
    if preset == PERFIL_AUTO:
        resolved = _resolved_profile_estado(estado)
        return resolved if resolved is not None else PERFIL_BALANCED
    return _perfil_normalizado(preset)


def _ler_chave_conf(caminho: str, secao: str, chave: str) -> Optional[str]:
    """Lê o valor de uma chave na seção indicada de um .conf (sem modificar)."""
    try:
        with open(caminho, "r", encoding="utf-8-sig") as f:
            linhas = f.read().splitlines()
    except OSError:
        return None
    secao_atual = None
    for ln in linhas:
        texto = ln.strip()
        if texto.startswith("[") and texto.endswith("]"):
            secao_atual = texto
            continue
        if secao_atual != secao or "=" not in ln:
            continue
        if ln.split("=", 1)[0].strip() == chave:
            return ln.split("=", 1)[1].strip()
    return None


def _aplicar_chaves_texto(texto: str, mapeamento: dict) -> str:
    """Aplica ``{secao: {chave: valor}}`` sobre o texto de um .conf.

    Preserva comentários e a formatação original (espaçamento antes do '=').
    Valores ``None`` não alteram a linha (a linha original é preservada).
    """
    linhas = texto.splitlines()
    secao_atual = None
    novas = []
    for ln in linhas:
        texto_linha = ln.strip()
        if texto_linha.startswith("[") and texto_linha.endswith("]"):
            secao_atual = texto_linha
            novas.append(ln)
            continue
        alterada = False
        if secao_atual in mapeamento and "=" in ln:
            chave = ln.split("=", 1)[0].strip()
            valor = mapeamento[secao_atual].get(chave)
            if valor is not None:
                match = re.match(r"^(\s*" + re.escape(chave) + r"\s*=\s*)(.*)$", ln)
                if match:
                    novas.append(match.group(1) + valor)
                    alterada = True
        if not alterada:
            novas.append(ln)
    return "\r\n".join(novas)  # o template usa quebras CRLF


def _aplicar_chaves(caminho_conf: str, mapeamento: dict) -> list[str]:
    """Aplica chaves (``{secao: {chave: valor}}``) a um .conf, atômico."""
    try:
        with open(caminho_conf, "r", encoding="utf-8-sig") as f:
            texto_original = f.read()
    except OSError as exc:
        raise RuntimeError(f"Não foi possível ler o dgVoodoo.conf: {exc}")
    texto_novo = _aplicar_chaves_texto(texto_original, mapeamento)
    # SEM BOM: dgVoodoo (2.87+) ignora dgVoodoo.conf iniciado com BOM UTF-8.
    _escrita_atomica(caminho_conf, texto_novo.encode("utf-8"))
    alteradas = []
    for secao, chaves in mapeamento.items():
        for chave, valor in chaves.items():
            if valor is not None:
                alteradas.append(f"{secao} {chave}={valor}")
    return alteradas


def _aplicar_preset(caminho_conf: str) -> list[str]:
    """Aplica o preset fixo "Aika Recomendado" na CÓPIA do cliente.

    Mantém o comportamento histórico da V1: substitui as chaves do
    PRESET_CONF (base fixa) preservando as demais opções.
    """
    return _aplicar_chaves(caminho_conf, PRESET_CONF)


def _gerar_conf_perfil(perfil: str) -> bytes:
    """Gera o dgVoodoo.conf de forma DETERMINÍSTICA.

    template original (third_party)
      + PRESET_CONF (base fixa da aplicação)
      + PERFIS_CONF[perfil] (diferenciais)

    Nunca altera o template. Nunca herda resíduos de perfis anteriores.
    """
    if perfil not in PERFIS_CONF:
        raise ValueError(f"Perfil desconhecido: {perfil!r}")
    try:
        with open(resolver_template_conf(), "r", encoding="utf-8-sig") as f:
            texto = f.read()
    except OSError as exc:
        raise RuntimeError(f"Não foi possível ler o template dgVoodoo.conf: {exc}")
    texto = _aplicar_chaves_texto(texto, PRESET_CONF)
    texto = _aplicar_chaves_texto(texto, PERFIS_CONF[perfil])
    # SEM BOM: conf valido para o dgVoodoo (mesmo formato dos confs oficiais/CPL).
    return texto.encode("utf-8")


def _gerar_conf_base() -> bytes:
    """Bytes da base Aika Recomendado/Balanced (Ativar/Reaplicar) em memória.

    Espelha o produtor legado de ativação: template original + PRESET_CONF.
    Nunca altera arquivo. Serve de ORÁCULO (LEGACY_BYTES) no parity guard do
    Stage 5B para Ativar/Reaplicar.
    """
    try:
        with open(resolver_template_conf(), "r", encoding="utf-8-sig") as f:
            texto = f.read()
    except OSError as exc:
        raise RuntimeError(f"Não foi possível ler o template dgVoodoo.conf: {exc}")
    # SEM BOM: conf valido para o dgVoodoo (mesmo formato dos confs oficiais/CPL).
    return _aplicar_chaves_texto(texto, PRESET_CONF).encode("utf-8")


# ---------------------------------------------------------------------------
# Estágio 5A — engine (somente leitura) + parity guard para aplicar_perfil
# ---------------------------------------------------------------------------

def _gerar_engine_bytes(perfil: Optional[str] = None) -> bytes:
    """Gera os bytes efetivos pelo engine (template + overlay + base/perfil).

    ``perfil=None`` representa a base Aika Recomendado/Balanced usada por
    Ativar/Reaplicar; ``perfil='performance'|'balanced'|'quality'`` representa
    o perfil efetivo. Apenas leitura: nunca escreve arquivo, nunca altera
    estado e não tem efeitos colaterais. O serviço permanece dono da
    escrita/hash/estado.
    """
    with open(resolver_template_conf(), "rb") as f:
        dados_template = f.read()
    geracao = _config_engine.generate_active(
        dados_template,
        fixed=_config_schema.OVERLAY_FIXO,
        base=_config_schema.BASE_AIKA,
        profiles=_config_schema.PERFIS_MAP,
        profile=perfil,
        validate_domain=_config_schema.validate_domain,
        catalog=_config_schema.CATALOG,
    )
    return geracao.bytes_


def _resumo_diff_geracao(a: bytes, b: bytes) -> str:
    """Resumo curto das categorias divergentes (sem despejar o arquivo)."""
    try:
        rel = _config_engine.diff_documents(a, b)
        return ",".join(rel.categories[:8]) or "categorias divergentes"
    except Exception:
        return "diff indisponível"


def _paridade_geracao(
    perfil: Optional[str] = None,
    operacao: Optional[str] = None,
) -> dict:
    """PARITY GUARD: só libera os bytes do engine se legado == engine.

    - ``perfil`` None  -> base Aika Recomendado/Balanced (Ativar/Reaplicar),
      legado = ``_gerar_conf_base()``;
    - ``perfil`` dado  -> perfil efetivo (Stage 5A),
      legado = ``_gerar_conf_perfil(perfil)``.

    ``operacao`` é um rótulo diagnóstico opcional (ex.: "ativar/reaplicar").
    Calcula em memória e NUNCA faz fallback silencioso: se divergir, retorna
    erro bloqueante (mensagem com operação/SHA-256/tamanho/diff do par) e o
    chamador aborta antes de escrever dgVoodoo.conf/estado/hash.
    """
    if perfil is None:
        legacy_bytes = _gerar_conf_base()
        engine_bytes = _gerar_engine_bytes(None)
        rotulo = "perfil=base"
        prefixo = (
            "DIVERGÊNCIA LEGADO×ENGINE — ativação/reaplicar abortada antes "
            "da escrita."
        )
    else:
        legacy_bytes = _gerar_conf_perfil(perfil)
        engine_bytes = _gerar_engine_bytes(perfil)
        rotulo = f"perfil={perfil}"
        prefixo = (
            "DIVERGÊNCIA LEGADO×ENGINE — aplicação de perfil abortada antes "
            "da escrita."
        )
    if legacy_bytes == engine_bytes:
        return {"ok": True, "engine_bytes": engine_bytes}
    op = f"operacao={operacao} " if operacao else ""
    return {
        "ok": False,
        "mensagem": (
            f"{prefixo} Nenhum arquivo/estado foi alterado. "
            f"{op}{rotulo} "
            f"legacy_sha256={hashlib.sha256(legacy_bytes).hexdigest()} "
            f"engine_sha256={hashlib.sha256(engine_bytes).hexdigest()} "
            f"legacy_size={len(legacy_bytes)} engine_size={len(engine_bytes)} "
            f"diff={_resumo_diff_geracao(legacy_bytes, engine_bytes)}"
        ),
    }


# ---------------------------------------------------------------------------
# Processos relevantes (jogo/launcher)
# ---------------------------------------------------------------------------

def _cliente_com_processo_aberto(pasta_jogo: str) -> bool:
    """Retorna True se processos relevantes do Aika estão em execução.

    Usa a infraestrutura real do módulo de Pedras, que cobre os executáveis
    de jogo e do launcher e valida o caminho do processo contra o cliente.
    Nunca mata processos.
    """
    try:
        from stone_color_service import detect_relevant_processes  # type: ignore
    except Exception:
        # Fallback conservador: usa a checagem de jogo já existente.
        try:
            return bool(config.jogo_esta_aberto())
        except Exception:
            return False
    try:
        deteccao = detect_relevant_processes(pasta_jogo)
        return bool(deteccao.matches)
    except Exception:
        try:
            return bool(config.jogo_esta_aberto())
        except Exception:
            return False
# ---------------------------------------------------------------------------
# Detecção de estado
# ---------------------------------------------------------------------------

def detectar_estado(pasta_jogo: Optional[str] = None) -> EstadoDetectado:
    """Detecta o estado gráfico do renderizador no cliente.

    A detecção é SOMENTE LEITURA: não escreve, não remove e não altera
    nenhum arquivo. Considera exclusivamente ``cliente/d3d9.dll``.
    """
    cliente = config.obter_pasta_jogo_atual(exigir_existente=True)
    if not cliente:
        return EstadoDetectado(
            estado=Estado.ERRO,
            cliente="",
            mensagem="Nenhum cliente AIKA válido configurado.",
        )
    if not config.caminho_seguro(cliente, cliente):
        return EstadoDetectado(
            estado=Estado.ERRO,
            cliente=cliente,
            mensagem="Caminho do cliente inválido ou inacessível.",
        )

    erros_template = validar_templates()
    template_hash = None
    caminho_template_dll = resolver_template_d3d9()
    try:
        template_hash = _sha256_arquivo(caminho_template_dll)
    except OSError:
        template_hash = None

    if erros_template:
        return EstadoDetectado(
            estado=Estado.TEMPLATE_AUSENTE,
            cliente=cliente,
            mensagem="; ".join(erros_template),
            template_hash=template_hash,
        )

    caminho_dll = os.path.join(cliente, D3D9_DLL)
    caminho_conf = os.path.join(cliente, DGVOODOO_CONF)
    dll_existe = os.path.isfile(caminho_dll)
    conf_existe = os.path.isfile(caminho_conf)
    dll_hash_atual = _sha256_arquivo(caminho_dll) if dll_existe else None
    estado_persistido = _carregar_estado(cliente)

    base = EstadoDetectado(
        estado=Estado.ORIGINAL,
        cliente=cliente,
        dll_existe=dll_existe,
        dll_hash_atual=dll_hash_atual,
        conf_existe=conf_existe,
        template_hash=template_hash,
        estado_persistido=estado_persistido,
    )

    if not dll_existe:
        base.mensagem = "DirectX 9 Original (sem d3d9.dll)."
        if estado_persistido and estado_persistido.get("status") == "active":
            base.estado = Estado.INCOMPLETO
            base.mensagem = (
                "Instalação incompleta: estado registrado como ativo, "
                "mas d3d9.dll ausente no cliente."
            )
        elif estado_persistido and _estado_persistido_instalado(estado_persistido):
            base.estado = Estado.INCOMPLETO
            base.mensagem = (
                "Instalação incompleta: registro do Optimizer indica "
                "instalação anterior, mas d3d9.dll não existe."
            )
        else:
            base.estado = Estado.ORIGINAL
        return base

    instalado_hash = _hash_instalado_do_estado(estado_persistido)
    if instalado_hash and dll_hash_atual == instalado_hash:
        if conf_existe:
            base.estado = Estado.ATIVO
            base.mensagem = "dgVoodoo2 Ativo (d3d9.dll reconhecida)."
        else:
            base.estado = Estado.INCOMPLETO
            base.mensagem = (
                "Instalação incompleta: d3d9.dll reconhecida, mas "
                "dgVoodoo.conf ausente no cliente."
            )
        return base

    if dll_hash_atual == template_hash:
        # DLL do template atual presente sem registro persistente: instalação
        # reconhecida por hash do template (ex.: template atualizado).
        base.estado = Estado.INCOMPLETO
        base.mensagem = (
            "d3d9.dll corresponde ao template atual, mas não há registro "
            "persistente de instalação do Optimizer."
        )
        return base

    base.estado = Estado.CONFLITO
    base.mensagem = (
        "d3d9.dll existente não pertence a uma instalação reconhecida "
        "pelo Optimizer (pode ser DXVK, outro wrapper ou DLL desconhecida)."
    )
    base.detalhes_conflito = {
        "arquivo": D3D9_DLL,
        "hash_atual": dll_hash_atual,
        "hash_template": template_hash,
        "hash_instalado_registrado": instalado_hash,
        "dll_dx_originais_preservadas": True,
    }
    return base


def _estado_persistido_instalado(estado: dict) -> bool:
    """True se há registro prévio de instalação (qualquer fase)."""
    return bool(estado.get("d3d9") or estado.get("status"))


def _hash_instalado_do_estado(estado: Optional[dict]) -> Optional[str]:
    """Hash da DLL que foi efetivamente instalada pelo Optimizer."""
    if not estado:
        return None
    registro = estado.get("d3d9")
    if isinstance(registro, dict):
        return registro.get("installed_sha256")
    return None
# ---------------------------------------------------------------------------
# Cópia segura de arquivos (padrão do projeto)
# ---------------------------------------------------------------------------

def _copiar_arquivo_atomico(origem: str, destino: str) -> str:
    """Copia origem -> destino com escrita atômica e validação SHA-256.

    O destino é escrito via temporário no MESMO diretório e substituído
    por os.replace. Retorna o hash do arquivo instalado.
    """
    if not os.path.isfile(origem):
        raise RuntimeError(f"Arquivo origem não encontrado: {origem}")
    with open(origem, "rb") as f:
        dados = f.read()
    _escrita_atomica(destino, dados)
    hash_instalado = _sha256_arquivo(destino)
    hash_origem = _sha256_arquivo(origem)
    if hash_instalado != hash_origem:
        raise RuntimeError(
            f"Falha na validação pós-cópia de {os.path.basename(destino)}"
        )
    return hash_instalado


def _remover_arquivo_seguro(caminho: str, hash_esperado: str) -> None:
    """Remove um arquivo somente se o hash atual for o esperado.

    Se o arquivo mudou externamente, NÃO remove e levanta erro.
    """
    if not os.path.isfile(caminho):
        return
    hash_atual = _sha256_arquivo(caminho)
    if hash_atual != hash_esperado:
        raise RuntimeError(
            f"{os.path.basename(caminho)} foi modificado externamente "
            f"(hash atual {hash_atual} != esperado {hash_esperado})"
        )
    try:
        os.chmod(caminho, stat.S_IWRITE)
    except OSError:
        pass
    os.remove(caminho)


def _backup_original(pasta_jogo: str, nome_arquivo: str,
                     hash_original: Optional[str] = None) -> Optional[dict]:
    """Backup VERSIONADO por SHA-256 do original (domínio exclusivo dgVoodoo).

    Estrutura:
        <estado_dir>/backups/<sha256_do_original>/<nome_arquivo>

    Cada original distinto possui seu próprio backup — nunca há sobrescrita
    nem reuso obsoleto entre ciclos de ativação/restauração. Se o backup
    deste mesmo hash já existe e é válido, ele é reutilizado (idempotente).
    A cópia usa ``seguranca.fazer_backup_rapido`` (validada, atômica).
    Retorna metadados ou None se o arquivo não existe.
    """
    origem = os.path.join(pasta_jogo, nome_arquivo)
    if not os.path.isfile(origem):
        return None
    if hash_original is None:
        hash_original = _sha256_arquivo(origem)
    backup_path = os.path.join(
        _pasta_estado_cliente(pasta_jogo), "backups", hash_original, nome_arquivo
    )
    # Reuso idempotente: backup deste mesmo original já capturado e válido
    if os.path.isfile(backup_path) and _sha256_arquivo(backup_path) == hash_original:
        return {
            "original_present": True,
            "original_sha256": hash_original,
            "backup_path": backup_path,
        }
    if not seguranca.fazer_backup_rapido(origem, backup_path):
        raise RuntimeError(f"Falha ao criar backup validado de {nome_arquivo}.")
    # Nunca registrar backup_path de arquivo inexistente ou com hash divergente
    if (not os.path.isfile(backup_path)
            or _sha256_arquivo(backup_path) != hash_original):
        raise RuntimeError(f"Backup de {nome_arquivo} inválido após criação.")
    return {
        "original_present": True,
        "original_sha256": hash_original,
        "backup_path": backup_path,
    }
# ---------------------------------------------------------------------------
# Ativação
# ---------------------------------------------------------------------------

def _agora_iso() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat(timespec="seconds")


def _versao_metadados_template() -> str:
    """Versão/texto de identificação do template atual (melhor esforço)."""
    try:
        caminho = resolver_template_d3d9()
        import ctypes

        from ctypes import wintypes

        return os.path.basename(caminho)
    except Exception:
        return "d3d9.dll"


def _marcar_estado_recuperavel(pasta_jogo: str, estado: dict, erro: BaseException) -> None:
    """Registra estado coerente após falha (nunca deixa 'active' se falhou)."""
    estado["status"] = "failed"
    estado["last_error"] = str(erro)
    _salvar_estado(pasta_jogo, estado)


def ativar_dgvoodoo(pasta_jogo: Optional[str] = None) -> ResultadoOperacao:
    """Instala dgVoodoo2 no cliente de forma transacional e recuperável.

    PENDING -> validar -> backup -> copiar DLL -> preparar CONF (bytes do
    engine validados pelo parity guard do Stage 5B) -> gravar -> validar ->
    ACTIVE. Em falha, registra estado recuperável e faz rollback best-effort
    dos arquivos já alterados.
    """
    cliente = config.obter_pasta_jogo_atual(exigir_existente=True)
    if not cliente:
        return ResultadoOperacao(
            ok=False,
            estado=Estado.ERRO,
            mensagem="Nenhum cliente AIKA válido configurado.",
        )
    if not config.caminho_seguro(cliente, cliente):
        return ResultadoOperacao(
            ok=False,
            estado=Estado.ERRO,
            mensagem="Caminho do cliente inválido ou inacessível.",
        )

    with _lock_do_cliente(cliente):
        erros_template = validar_templates()
        if erros_template:
            return ResultadoOperacao(
                ok=False,
                estado=Estado.TEMPLATE_AUSENTE,
                mensagem="; ".join(erros_template),
            )
        if _cliente_com_processo_aberto(cliente):
            return ResultadoOperacao(
                ok=False,
                estado=Estado.JOGO_ABERTO,
                mensagem=(
                    "O jogo ou launcher do Aika está em execução. "
                    "Feche-o antes de alterar o renderizador."
                ),
            )

        detectado = detectar_estado(cliente)
        if detectado.estado == Estado.CONFLITO:
            return ResultadoOperacao(
                ok=False,
                estado=Estado.CONFLITO,
                mensagem=detectado.mensagem,
                dados=detectado.detalhes_conflito,
            )

        # ---- Estágio 5B: PARITY GUARD de Ativar/Reaplicar ANTES de qualquer
        #      mutação (inclusive do estado PENDING). Gera a base em memória
        #      (legado e engine); divergência aborta sem tocar arquivo/estado.
        try:
            _guard = _paridade_geracao(None, operacao="ativar/reaplicar")
        except Exception as exc:
            return ResultadoOperacao(
                ok=False,
                estado=Estado.ERRO,
                mensagem=f"Falha ao gerar base dgVoodoo.conf: {exc}",
            )
        if not _guard["ok"]:
            return ResultadoOperacao(
                ok=False,
                estado=Estado.ERRO,
                mensagem=_guard["mensagem"],
            )

        # ---- registro PENDING (write-ahead) ----
        estado_anterior = _carregar_estado(cliente)
        estado_atual = {
            "format_version": 1,
            "status": "pending",
            "preset": "Aika Recomendado",
            "backend": "d3d11_fl11_0",
            "installed_at": _agora_iso(),
            "template_version": _versao_metadados_template(),
            "d3d9": {
                "original_present": False,
                "original_sha256": None,
                "backup_path": None,
                "installed_sha256": None,
            },
            "conf": {
                "original_present": False,
                "original_sha256": None,
                "backup_path": None,
                "installed_sha256": None,
            },
        }
        _salvar_estado(cliente, estado_atual)

        # ---- backup dos originais (se existirem) ----
        if os.path.isfile(os.path.join(cliente, D3D9_DLL)):
            instalado = _hash_instalado_do_estado(estado_anterior)
            atual = _sha256_arquivo(os.path.join(cliente, D3D9_DLL))
            if instalado and atual != instalado:
                _marcar_estado_recuperavel(
                    cliente, estado_atual,
                    RuntimeError("d3d9.dll mudou externamente; reativação abortada."),
                )
                return ResultadoOperacao(
                    ok=False,
                    estado=Estado.MODIFICADO_EXTERNAMENTE,
                    mensagem=(
                        "d3d9.dll foi modificado externamente após a "
                        "instalação do Optimizer. Reativação abortada."
                    ),
                )
        try:
            # Captura VERSIONADA dos originais deste ciclo (d3d9 e conf):
            # - arquivo ausente: nada a capturar;
            # - arquivo == installed_sha256 registrado (ou template, no caso
            #   da DLL): é a nossa própria instalação anterior (reativação)
            #   -> apenas herda o original já registrado; nunca reclassifica
            #   a instalação do Optimizer como original;
            # - arquivo != instalado e o original registrado é o MESMO hash
            #   -> reutiliza o backup versionado daquele hash;
            # - arquivo != instalado e original novo/diferente -> captura
            #   novo backup versionado por SHA-256 (cada ciclo aponta para
            #   o seu próprio original — corrige backup obsoleto).
            hash_template_dll = _sha256_arquivo(resolver_template_d3d9())
            for chave, nome, caminho in (
                ("d3d9", D3D9_DLL, os.path.join(cliente, D3D9_DLL)),
                ("conf", DGVOODOO_CONF, os.path.join(cliente, DGVOODOO_CONF)),
            ):
                if not os.path.isfile(caminho):
                    continue
                hash_atual = _sha256_arquivo(caminho)
                anterior = (estado_anterior or {}).get(chave)
                instalado_anterior = (anterior or {}).get("installed_sha256")
                # 1) É a nossa própria instalação anterior -> nunca vira original
                if (instalado_anterior and hash_atual == instalado_anterior) or (
                        chave == "d3d9" and hash_atual == hash_template_dll):
                    if isinstance(anterior, dict) and anterior.get("original_present"):
                        estado_atual[chave].update(anterior)
                    continue
                # 2) Mesmo original do ciclo anterior -> reutilizar backup versionado
                if (isinstance(anterior, dict) and anterior.get("original_present")
                        and anterior.get("original_sha256") == hash_atual):
                    estado_atual[chave].update(anterior)
                    continue
                # 3) Original novo/diferente -> capturar backup versionado
                meta = _backup_original(cliente, nome, hash_atual)
                if meta:
                    estado_atual[chave].update(meta)
        except Exception as exc:
            _marcar_estado_recuperavel(cliente, estado_atual, exc)
            return ResultadoOperacao(
                ok=False,
                estado=Estado.ERRO,
                mensagem=f"Falha ao capturar backups dos originais: {exc}",
            )
        _salvar_estado(cliente, estado_atual)

        # ---- cópia e validação dos arquivos ----
        try:
            hash_template_dll = _sha256_arquivo(resolver_template_d3d9())
            hash_instalado_dll = _copiar_arquivo_atomico(
                resolver_template_d3d9(), os.path.join(cliente, D3D9_DLL)
            )
            if hash_instalado_dll != hash_template_dll:
                raise RuntimeError("Hash da DLL instalada divergiu do template.")
            # Estágio 5B: origem dos bytes do conf = ENGINE (validado no parity
            # guard, antes de qualquer mutação). A escrita continua no serviço.
            _escrita_atomica(
                os.path.join(cliente, DGVOODOO_CONF), _guard["engine_bytes"]
            )
            if not os.path.isfile(os.path.join(cliente, D3D9_DLL)):
                raise RuntimeError("d3d9.dll não encontrada após instalação.")
            caminho_conf = os.path.join(cliente, DGVOODOO_CONF)
            if not os.path.isfile(caminho_conf):
                raise RuntimeError("dgVoodoo.conf não encontrada após instalação.")
            # Validação pós-escrita (Stage 5B): bytes gravados == engine_bytes,
            # sem BOM e invariantes da base Aika Recomendado/Balanced.
            with open(caminho_conf, "rb") as _f_escrito:
                _escrito = _f_escrito.read()
            if _escrito != _guard["engine_bytes"]:
                raise RuntimeError("dgVoodoo.conf gravado divergiu dos engine_bytes")
            if _escrito[:3] == b"\xef\xbb\xbf":
                raise RuntimeError("dgVoodoo.conf gravado com BOM UTF-8")
            for _secao, _chave, _valor in (
                ("[DirectX]", "Filtering", "16"),
                ("[DirectX]", "Antialiasing", "2x"),
                ("[General]", "OutputAPI", "d3d11_fl11_0"),
                ("[DirectX]", "dgVoodooWatermark", "false"),
            ):
                if _ler_chave_conf(caminho_conf, _secao, _chave) != _valor:
                    raise RuntimeError(
                        f"Validação pós-instalação falhou: {_secao} {_chave}"
                    )
        except Exception as exc:
            if os.path.isfile(os.path.join(cliente, D3D9_DLL)):
                try:
                    os.chmod(os.path.join(cliente, D3D9_DLL), stat.S_IWRITE)
                    os.remove(os.path.join(cliente, D3D9_DLL))
                except Exception:
                    pass
            caminho_conf = os.path.join(cliente, DGVOODOO_CONF)
            if os.path.isfile(caminho_conf):
                try:
                    os.chmod(caminho_conf, stat.S_IWRITE)
                    os.remove(caminho_conf)
                except Exception:
                    pass
            _marcar_estado_recuperavel(cliente, estado_atual, exc)
            return ResultadoOperacao(
                ok=False,
                estado=Estado.ERRO,
                mensagem=f"Falha durante a instalação: {exc}",
            )

        estado_atual["status"] = "active"
        estado_atual["d3d9"]["installed_sha256"] = hash_instalado_dll
        estado_atual["conf"]["installed_sha256"] = _sha256_arquivo(
            os.path.join(cliente, DGVOODOO_CONF)
        )
        _salvar_estado(cliente, estado_atual)

        return ResultadoOperacao(
            ok=True,
            estado=Estado.ATIVO,
            mensagem="dgVoodoo2 ativado com sucesso.",
            dados={
                "preset": "Aika Recomendado",
                "backend": "d3d11_fl11_0",
                                "d3d9_sha256": hash_instalado_dll,
            },
        )


def restaurar_directx_original(pasta_jogo=None):
    """Restaura o estado gráfico original do cliente.

    - Se havia d3d9.dll original: restaura exatamente do backup validado.
    - Se não havia: remove o d3d9.dll e dgVoodoo.conf instalados pelo Optimizer.
    Nunca remove/restaura arquivos modificados externamente.
    """
    cliente = config.obter_pasta_jogo_atual(exigir_existente=True)
    if not cliente:
        return ResultadoOperacao(
            ok=False, estado=Estado.ERRO,
            mensagem="Nenhum cliente AIKA válido configurado.",
        )
    if not config.caminho_seguro(cliente, cliente):
        return ResultadoOperacao(
            ok=False, estado=Estado.ERRO,
            mensagem="Caminho do cliente inválido ou inacessível.",
        )
    with _lock_do_cliente(cliente):
        if _cliente_com_processo_aberto(cliente):
            return ResultadoOperacao(
                ok=False, estado=Estado.JOGO_ABERTO,
                mensagem="O jogo ou launcher do Aika está em execução.",
            )

        estado = _carregar_estado(cliente)
        if not estado:
            return ResultadoOperacao(
                ok=False, estado=Estado.ORIGINAL,
                mensagem="Nenhuma instalação do Optimizer encontrada.",
            )

        if estado.get("status") != "active":
            return ResultadoOperacao(
                ok=False, estado=Estado.ERRO,
                mensagem="Nenhuma instalação ativa do Optimizer encontrada.",
            )

        # --- PREFLIGHT: classifica TODOS os componentes antes de qualquer
        #     mutação, garantindo que nenhuma restauração parcial ocorra ---
        planos = []
        for registro, nome, caminho in (
            (estado.get("d3d9", {}), D3D9_DLL, os.path.join(cliente, D3D9_DLL)),
            (estado.get("conf", {}), DGVOODOO_CONF, os.path.join(cliente, DGVOODOO_CONF)),
        ):
            hash_instalado = registro.get("installed_sha256")
            hash_original = registro.get("original_sha256")
            hash_atual = (_sha256_arquivo(caminho)
                          if os.path.isfile(caminho) else None)

            if hash_atual is None:
                acao = "nada"  # arquivo ausente: nada a remover/restaurar
            elif registro.get("original_present"):
                backup_path = registro.get("backup_path")
                if hash_atual == hash_instalado:
                    # CASO A: instalado intacto -> seguro restaurar o original
                    if (not backup_path or not os.path.isfile(backup_path)
                            or _sha256_arquivo(backup_path) != hash_original):
                        return ResultadoOperacao(
                            ok=False, estado=Estado.ERRO,
                            mensagem=(
                                f"Backup de {nome} ausente ou inválido; "
                                "restauração abortada sem alterar o cliente."
                            ),
                        )
                    acao = "restaurar_backup"
                elif hash_atual == hash_original:
                    acao = "nada"  # CASO B: já corresponde ao original
                else:
                    # CASO C: modificação externa -> abortar sem mutar nada
                    return ResultadoOperacao(
                        ok=False, estado=Estado.MODIFICADO_EXTERNAMENTE,
                        mensagem=(
                            f"{nome} foi modificado após a instalação; "
                            "restauração abortada sem alterar o cliente."
                        ),
                    )
            else:
                if hash_atual != hash_instalado:
                    # CASO C: modificação externa -> abortar sem mutar nada
                    return ResultadoOperacao(
                        ok=False, estado=Estado.MODIFICADO_EXTERNAMENTE,
                        mensagem=(
                            f"{nome} foi modificado após a instalação; "
                            "restauração abortada sem alterar o cliente."
                        ),
                    )
                acao = "remover"

            planos.append((acao, caminho, registro.get("backup_path")))

        # --- MUTAÇÃO: somente após o preflight validar 100% dos componentes ---
        try:
            for acao, caminho, backup_path in planos:
                if acao == "remover":
                    os.chmod(caminho, stat.S_IWRITE)
                    os.remove(caminho)
                elif acao == "restaurar_backup":
                    _copiar_arquivo_atomico(backup_path, caminho)
        except Exception as exc:
            _marcar_estado_recuperavel(cliente, estado, exc)
            return ResultadoOperacao(
                ok=False, estado=Estado.ERRO,
                mensagem=f"Falha ao restaurar arquivos originais: {exc}",
            )

        _remover_estado(cliente)
        return ResultadoOperacao(
            ok=True, estado=Estado.ORIGINAL,
            mensagem="DirectX original restaurado com sucesso.",
        )


# ---------------------------------------------------------------------------
# Perfis gráficos (V2.2)
# ---------------------------------------------------------------------------

def aplicar_perfil(perfil, pasta_jogo=None, resolved_profile=None):
    """Aplica um perfil gráfico na cópia ``cliente\\dgVoodoo.conf``.

    Escolhas: ``auto`` | ``performance`` | ``balanced`` | ``quality``.

    - Perfil manual: aplica EXATAMENTE o perfil informado e persiste
      ``preset=<perfil>`` (sem ``resolved_profile``).
    - Perfil AUTO: o parâmetro ``resolved_profile`` (obrigatório) define qual
      dos 3 perfis é efetivamente gravado. Persiste ``preset="auto"`` e
      ``resolved_profile=<perfil resolvido>``. ``resolved_profile`` inválido
      (ou ``auto``) é REJEITADO sem tocar no conf nem no estado.

    Regras:
    - exige dgVoodoo ATIVO (não instala nada se ORIGINAL);
    - bloqueia com JOGO_ABERTO se o Aika/launcher estiver em execução;
    - não reinstala ``d3d9.dll`` nem recaptura o original;
    - trabalha SOMENTE na cópia do cliente (template intacto);
    - gera o conf de forma determinística (template + PRESET_CONF + perfil);
    - valida o arquivo antes de confirmar;
    - atualiza ``conf.installed_sha256`` e ``preset`` no estado persistente,
      preservando ``original_sha256``/``backup_path`` (restauração intacta);
    - proteção MODIFICADO_EXTERNAMENTE: se o conf atual divergir do hash
      instalado registrado, aborta sem sobrescrever.
    """
    cliente = config.obter_pasta_jogo_atual(exigir_existente=True)
    if not cliente:
        return ResultadoOperacao(
            ok=False, estado=Estado.ERRO,
            mensagem="Nenhum cliente AIKA válido configurado.",
        )
    if not config.caminho_seguro(cliente, cliente):
        return ResultadoOperacao(
            ok=False, estado=Estado.ERRO,
            mensagem="Caminho do cliente inválido ou inacessível.",
        )
    if perfil not in PERFIS_ESCOLHIVEIS:
        return ResultadoOperacao(
            ok=False, estado=Estado.ERRO,
            mensagem=(
                f"Perfil desconhecido: {perfil!r}. "
                f"Use {', '.join(PERFIS_ESCOLHIVEIS)}."
            ),
        )
    if perfil == PERFIL_AUTO:
        if resolved_profile not in PERFIS_SUPORTADOS:
            return ResultadoOperacao(
                ok=False, estado=Estado.ERRO,
                mensagem=(
                    f"Perfil AUTO exige resolved_profile válido "
                    f"({', '.join(PERFIS_SUPORTADOS)}); recebido "
                    f"{resolved_profile!r}."
                ),
            )
        perfil_aplicado = resolved_profile
        preset_aplicado = PERFIL_AUTO
    else:
        perfil_aplicado = perfil
        preset_aplicado = perfil

    with _lock_do_cliente(cliente):
        erros_template = validar_templates()
        if erros_template:
            return ResultadoOperacao(
                ok=False, estado=Estado.TEMPLATE_AUSENTE,
                mensagem="; ".join(erros_template),
            )
        if _cliente_com_processo_aberto(cliente):
            return ResultadoOperacao(
                ok=False, estado=Estado.JOGO_ABERTO,
                mensagem="O jogo ou launcher do Aika está em execução. "
                         "Feche-o antes de alterar o perfil gráfico.",
            )

        estado = _carregar_estado(cliente)
        if not estado or estado.get("status") != "active":
            return ResultadoOperacao(
                ok=False, estado=Estado.ERRO,
                mensagem="dgVoodoo2 não está ativo. Ative-o antes de aplicar um perfil.",
            )

        caminho_conf = os.path.join(cliente, DGVOODOO_CONF)
        if not os.path.isfile(caminho_conf):
            return ResultadoOperacao(
                ok=False, estado=Estado.ERRO,
                mensagem="dgVoodoo.conf não encontrado no cliente.",
            )

        # Proteção MODIFICADO_EXTERNAMENTE: só alteramos a NOSSA configuração.
        registro_conf = estado.get("conf") or {}
        hash_instalado = registro_conf.get("installed_sha256")
        if hash_instalado:
            hash_atual = _sha256_arquivo(caminho_conf)
            if hash_atual != hash_instalado:
                return ResultadoOperacao(
                    ok=False, estado=Estado.MODIFICADO_EXTERNAMENTE,
                    mensagem=(
                        "dgVoodoo.conf foi modificado externamente após a "
                        "instalação. Aplicação do perfil abortada."
                    ),
                )

        # Estágio 5A — PARITY GUARD antes de qualquer escrita: gera legado e
        # engine em memória, compara byte a byte e só segue com os bytes do
        # engine se idênticos. Divergência NUNCA faz fallback e NUNCA escreve.
        try:
            _guard = _paridade_geracao(perfil_aplicado)
        except Exception as exc:
            _marcar_estado_recuperavel(cliente, estado, exc)
            return ResultadoOperacao(
                ok=False, estado=Estado.ERRO,
                mensagem=f"Falha ao gerar configuração do perfil {perfil_aplicado}: {exc}",
            )
        if not _guard["ok"]:
            return ResultadoOperacao(
                ok=False, estado=Estado.ERRO,
                mensagem=_guard["mensagem"],
            )
        dados = _guard["engine_bytes"]
        try:
            _escrita_atomica(caminho_conf, dados)
            # Validação pós-escrita (Stage 5A): arquivo ativo SEM BOM e bytes
            # escritos idênticos aos engine_bytes validados pela paridade.
            with open(caminho_conf, "rb") as _f_conf:
                escrito = _f_conf.read()
            if escrito[:3] == b"\xef\xbb\xbf":
                raise RuntimeError("conf ativo gravado com BOM UTF-8")
            if escrito != dados:
                raise RuntimeError("hash do conf gravado diverge dos bytes validados")
        except Exception as exc:
            _marcar_estado_recuperavel(cliente, estado, exc)
            return ResultadoOperacao(
                ok=False, estado=Estado.ERRO,
                mensagem=f"Falha ao aplicar perfil {perfil_aplicado}: {exc}",
            )

        # Validação do conteúdo final (chaves do perfil presentes).
        overrides = PERFIS_CONF[perfil_aplicado].get("[DirectX]", {})
        for chave, valor_esperado in overrides.items():
            valor_real = _ler_chave_conf(caminho_conf, "[DirectX]", chave)
            if valor_real != valor_esperado:
                _marcar_estado_recuperavel(cliente, estado, RuntimeError(
                    f"Validação do perfil falhou: {chave} esperava "
                    f"{valor_esperado}, obteve {valor_real}"
                ))
                return ResultadoOperacao(
                    ok=False, estado=Estado.ERRO,
                    mensagem=f"Validação do perfil {perfil_aplicado} falhou.",
                )

        novo_hash = _sha256_arquivo(caminho_conf)
        estado["conf"]["installed_sha256"] = novo_hash
        estado["preset"] = preset_aplicado
        if preset_aplicado == PERFIL_AUTO:
            estado["resolved_profile"] = perfil_aplicado
        else:
            # Perfil manual: remover resíduo de AUTO anterior.
            estado.pop("resolved_profile", None)
        estado["profile_applied_at"] = _agora_iso()
        _salvar_estado(cliente, estado)

        if preset_aplicado == PERFIL_AUTO:
            nome_efetivo = PERFIL_NOME_EXIBICAO.get(perfil_aplicado, perfil_aplicado)
            mensagem_ok = f"Perfil AUTO → {nome_efetivo} aplicado com sucesso."
        else:
            nome_exibicao = PERFIL_NOME_EXIBICAO.get(perfil_aplicado, perfil_aplicado)
            mensagem_ok = f"Perfil {nome_exibicao} aplicado com sucesso."
        return ResultadoOperacao(
            ok=True, estado=Estado.ATIVO,
            mensagem=mensagem_ok,
            dados={
                "perfil": perfil_aplicado,
                "preset": preset_aplicado,
                "resolved_profile": (
                    perfil_aplicado if preset_aplicado == PERFIL_AUTO else None
                ),
                "conf_sha256": novo_hash,
            },
        )


# ---------------------------------------------------------------------------
# Utilitário de diagnóstico público
# ---------------------------------------------------------------------------
def diagnosticar(pasta_jogo=None):
    """Retorna detalhes completos do estado detectado (apenas leitura)."""
    return detectar_estado(pasta_jogo)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
__all__ = [
    "D3D9_DLL",
    "DGVOODOO_CONF",
    "TEMPLATE_REL_PATH",
    "NOME_SUBDIR",
    "ARQUIVO_ESTADO",
    "PRESET_CONF",
    "PERFIL_PERFORMANCE",
    "PERFIL_BALANCED",
    "PERFIL_QUALITY",
    "PERFIL_AUTO",
    "PERFIS_SUPORTADOS",
    "PERFIS_ESCOLHIVEIS",
    "PERFIS_CONF",
    "PERFIL_NOME_EXIBICAO",
    "PRESET_LEGADO_AIKA",
    "Estado",
    "EstadoDetectado",
    "ResultadoOperacao",
    "resolver_template_d3d9",
    "resolver_template_conf",
    "validar_templates",
    "detectar_estado",
    "diagnosticar",
    "ativar_dgvoodoo",
    "restaurar_directx_original",
    "aplicar_perfil",
    "_perfil_normalizado",
    "_perfil_escolhido_estado",
    "_perfil_efetivo_estado",
    "_resolved_profile_estado",
    "_gerar_conf_perfil",
]

