# -*- coding: utf-8 -*-
"""Serviço puro de detecção de hardware gráfico (V2.3A).

Coleta informações das GPUs via ``Win32_VideoController`` (PowerShell/CIM),
normaliza os dados e recomenda um dos perfis gráficos já validados do
dgVoodoo2 (``performance`` | ``balanced`` | ``quality``).

Regras:
- SEM PySide6; SEM widgets; SEM efeitos colaterais no import.
- Detecção ocorre SOMENTE quando uma função pública é chamada.
- A consulta é SOMENTE LEITURA (sem admin, sem tocar Registro/driver).
- NUNCA altera dgVoodoo.conf, estado.json, Adapters ou perfil.
- Na dúvida: retorna ``balanced`` (fallback seguro).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Reuso do executor PowerShell existente (helper interno do projeto).
from sistema import _executar_powershell_oculto


# ---------------------------------------------------------------------------
# Perfis canônicos (espelham dgvoodoo_service sem criar acoplamento)
# ---------------------------------------------------------------------------

PERFIL_PERFORMANCE = "performance"
PERFIL_BALANCED = "balanced"
PERFIL_QUALITY = "quality"

CONFIANCA_ALTA = "ALTA"
CONFIANCA_MEDIA = "MEDIA"
CONFIANCA_BAIXA = "BAIXA"

VENDOR_NVIDIA = "nvidia"
VENDOR_AMD = "amd"
VENDOR_INTEL = "intel"
VENDOR_UNKNOWN = "unknown"

# Faixa plausível de VRAM (em MB). Abaixo/acima => desconhecido.
VRAM_MIN_MB = 256
VRAM_MAX_MB = 64 * 1024  # 64 GB

# Limiares da heurística conservadora (em MB).
VRAM_LIMITE_PERFORMANCE_MB = 2 * 1024  # VRAM <= 2 GB -> performance
VRAM_LIMITE_QUALITY_MB = 6 * 1024      # VRAM >= 6 GB -> quality


# ---------------------------------------------------------------------------
# Estruturas de dados
# ---------------------------------------------------------------------------

@dataclass
class GpuInfo:
    """Informação normalizada de uma GPU.

    ``integrated``/``dedicated`` são ``bool | None``: nunca transformar
    dúvida em certeza falsa. ``None`` = desconhecido.
    """
    name: str = ""
    vendor: str = VENDOR_UNKNOWN
    vram_mb: Optional[int] = None
    integrated: Optional[bool] = None
    dedicated: Optional[bool] = None
    status_ok: Optional[bool] = None
    video_mode: Optional[str] = None
    vram_source: Optional[str] = None  # "system" | "wmi" | None


@dataclass
class HardwareProfile:
    """Recomendação resultante da análise das GPUs coletadas."""
    gpus: list = field(default_factory=list)
    recommended_profile: str = PERFIL_BALANCED
    reason: str = ""
    confidence: str = CONFIANCA_BAIXA


# ---------------------------------------------------------------------------
# Normalização de fabricante (VEN_xxxx no PNPDeviceID)
# ---------------------------------------------------------------------------

_VENDOR_POR_VEN = {
    "10de": VENDOR_NVIDIA,
    "1002": VENDOR_AMD,
    "8086": VENDOR_INTEL,
}


def _extrair_vendor(pnp_device_id: Optional[str]) -> str:
    """Identifica o fabricante por ``VEN_xxxx`` no PNPDeviceID.

    Caso o ID esteja ausente ou sem VEN, tenta uma leitura conservadora
    pelo nome; caso contrário retorna ``unknown``.
    """
    if pnp_device_id:
        match = re.search(r"VEN_([0-9A-Fa-f]{4})", pnp_device_id)
        if match:
            return _VENDOR_POR_VEN.get(match.group(1).lower(), VENDOR_UNKNOWN)

    # Fallback apenas por marcadores inequívocos no nome (nunca por fabricante sozinho).
    if pnp_device_id:
        pid = pnp_device_id.lower()
        if "nvidia" in pid:
            return VENDOR_NVIDIA
        if "amd" in pid or "ati" in pid:
            return VENDOR_AMD
        if "intel" in pid:
            return VENDOR_INTEL
    return VENDOR_UNKNOWN


# ---------------------------------------------------------------------------
# Normalização de VRAM (AdapterRAM da WMI vem em bytes e pode ser truncado)
# ---------------------------------------------------------------------------

def _normalizar_vram_mb(adapter_ram: Any) -> Optional[int]:
    """Converte AdapterRAM (bytes) para MB de forma defensiva.

    Valores ausentes, zero, negativos, não numéricos ou fora da faixa
    plausível (256 MB..64 GB) resultam em ``None`` (desconhecido).
    """
    if adapter_ram is None:
        return None
    if isinstance(adapter_ram, str):
        adapter_ram = adapter_ram.strip()
        if not adapter_ram or not adapter_ram.lstrip("-").isdigit():
            return None
    try:
        valor = int(adapter_ram)
    except (TypeError, ValueError):
        return None
    if valor <= 0:
        return None
    vram_mb = valor / (1024 * 1024)  # AdapterRAM da WMI é reportado em bytes
    if vram_mb < VRAM_MIN_MB or vram_mb > VRAM_MAX_MB:
        return None
    return int(vram_mb)


# ---------------------------------------------------------------------------
# Classificação integrada/dedicada — conservadora, por marcadores de nome
# ---------------------------------------------------------------------------

_RE_INTEGRADA = re.compile(
    r"intel\s*\(r\)\s*(hd|uhd|iris)|"
    r"intel\s+(hd|uhd)\s+graphics|"
    r"radeon\s*\(tm\)\s+graphics\b|"
    r"amd\s+radeon\s+graphics\b|"
    r"\b(integrated|intel\s+graphics)\b",
    re.IGNORECASE,
)

_RE_DEDICADA = re.compile(
    r"\bnvidia\b|\bgeforce\b|\bgtx\b|\brtx\b|\bquadro\b|"
    r"\brates?|radeon\s+(rx|pro|vega)\b|"
    r"intel\s+arc\b",
    re.IGNORECASE,
)


def _classificar_tipo(nome: str) -> tuple[Optional[bool], Optional[bool]]:
    """Retorna ``(integrated, dedicated)`` de forma conservadora.

    Só preenche quando há marcadores inequívocos. Dúvida => ``None``.
    """
    if not nome:
        return None, None
    eh_integrada = bool(_RE_INTEGRADA.search(nome))
    eh_dedicada = bool(_RE_DEDICADA.search(nome))
    if eh_integrada and not eh_dedicada:
        return True, False
    if eh_dedicada and not eh_integrada:
        return False, True
    return None, None


# ---------------------------------------------------------------------------
# Coleta via Win32_VideoController (somente leitura)
# ---------------------------------------------------------------------------

_WMI_SCRIPT = (
    "$g = Get-CimInstance Win32_VideoController; "
    "$out = $g | ForEach-Object { [PSCustomObject]@{ "
    "Name = $_.Name; "
    "PNPDeviceID = $_.PNPDeviceID; "
    "AdapterRAM = $_.AdapterRAM; "
    "DriverVersion = $_.DriverVersion; "
    "Status = $_.Status; "
    "VideoModeDescription = $_.VideoModeDescription } }; "
    "$out | ConvertTo-Json -Compress -Depth 3"
)


def _status_ok(status: Any) -> Optional[bool]:
    """Normaliza Status da WMI. Só ``OK`` (case-insensitive) é True."""
    if status is None:
        return None
    if isinstance(status, str) and status.strip().upper() == "OK":
        return True
    return False


def _vram_wmi_suspeita_teto(vram_mb: Optional[int]) -> bool:
    """Indica se um valor de VRAM vindo do AdapterRAM (32-bit) está próximo
    do teto de 4 GB (≈4095–4096 MB), o que sugere possível truncamento.

    Valores nesta faixa NÃO devem ser usados como certeza de que a placa
    possui exatamente ~4 GB de VRAM.
    """
    if vram_mb is None:
        return False
    return 4090 <= vram_mb <= 4100


def _vram_nominal_mb(vram_mb: Optional[int]) -> Optional[int]:
    """Ajusta o valor reportado para o tamanho nominal da VRAM, quando a
    diferença for pequena (≤ 8 MiB) — reserva típica de firmware/driver.

    VRAM dedicada é sempre múltipla de 256 MiB (2048, 4096, 6144, ...). Uma
    placa de 6 GB pode reportar ~6141 MB dedicados; o ajuste devolve 6144.
    Valores longe de um múltiplo nominal são mantidos (nada é inventado).
    """
    if vram_mb is None:
        return vram_mb
    nominal = round(vram_mb / 256) * 256
    if nominal >= VRAM_MIN_MB and abs(nominal - vram_mb) <= 8:
        return nominal
    return vram_mb


def _parsear_item_gpu(item: Any) -> Optional[GpuInfo]:
    """Converte um item do JSON (dict) em ``GpuInfo`` normalizado."""
    if not isinstance(item, dict):
        return None
    nome = str(item.get("Name") or "").strip()
    if not nome:
        return None
    pnp = item.get("PNPDeviceID")
    pnp = str(pnp) if pnp is not None else None
    integrated, dedicated = _classificar_tipo(nome)
    vram_mb = _normalizar_vram_mb(item.get("AdapterRAM"))
    return GpuInfo(
        name=nome,
        vendor=_extrair_vendor(pnp),
        vram_mb=vram_mb,
        vram_source=("wmi" if vram_mb is not None else None),
        integrated=integrated,
        dedicated=dedicated,
        status_ok=_status_ok(item.get("Status")),
        video_mode=str(item.get("VideoModeDescription") or "") or None,
    )


def _coletar_gpus_via_wmi() -> list[GpuInfo]:
    """Executa a consulta WMI e normaliza a saída em ``list[GpuInfo]``.

    Nunca levanta exceção: qualquer falha (PowerShell, JSON, conversão)
    retorna lista vazia — o chamador deve cair no fallback seguro.
    """
    try:
        stdout = _executar_powershell_oculto(_WMI_SCRIPT, timeout=30)
    except Exception:
        return []
    if not stdout or not stdout.strip():
        return []
    try:
        dados = json.loads(stdout)
    except (ValueError, TypeError):
        return []
    if isinstance(dados, dict):
        dados = [dados]
    if not isinstance(dados, list):
        return []
    gpus: list[GpuInfo] = []
    for item in dados:
        gpu = _parsear_item_gpu(item)
        if gpu is not None:
            gpus.append(gpu)
    return gpus


# ---------------------------------------------------------------------------
# VRAM dedicada real (64-bit) — Registro do sistema
# ---------------------------------------------------------------------------
# O AdapterRAM do Win32_VideoController é UInt32 e sofre truncamento (ex.:
# GPUs com 6 GB reportam ~4095 MB). O driver também grava a VRAM real
# (QWORD, 64-bit) em:
#   HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-...}\<0000..>
#   HardwareInformation.qwMemorySize  (em bytes)
# Esta leitura é somente-leitura, sem COM, e fornece o valor 64-bit real.

_REG_CLASS_DISPLAY = (
    r"SYSTEM\CurrentControlSet\Control\Class"
    r"\{4d36e968-e325-11ce-bfc1-08002be10318}"
)


def _vram_system_adaptadores() -> list[dict]:
    """Lê a VRAM 64-bit real de cada adaptador de vídeo no Registro.

    Retorna lista de dicts: ``{"name", "vram_mb"}``. Nunca levanta.
    """
    try:
        import winreg
    except Exception:
        return []
    resultado: list[dict] = []
    try:
        raiz = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _REG_CLASS_DISPLAY)
    except OSError:
        return []
    try:
        idx = 0
        while True:
            try:
                sub = winreg.EnumKey(raiz, idx)
            except OSError:
                break
            idx += 1
            try:
                sk = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                    _REG_CLASS_DISPLAY + "\\" + sub)
            except OSError:
                continue
            try:
                try:
                    desc = winreg.QueryValueEx(sk, "DriverDesc")[0]
                    desc = str(desc) if desc else ""
                except OSError:
                    desc = ""
                try:
                    qw = winreg.QueryValueEx(sk,
                                             "HardwareInformation.qwMemorySize")[0]
                    qw_bytes = int(qw)
                except OSError:
                    qw_bytes = 0
                vram_mb = _normalizar_vram_mb(qw_bytes) if qw_bytes else None
                if desc or vram_mb is not None:
                    resultado.append({"name": desc, "vram_mb": vram_mb})
            finally:
                try:
                    winreg.CloseKey(sk)
                except Exception:
                    pass
    finally:
        try:
            winreg.CloseKey(raiz)
        except Exception:
            pass
    return resultado


def _vram_system_enriquecer() -> list[dict]:
    """Wrapper de leitura do Registro (nunca levanta)."""
    try:
        return _vram_system_adaptadores()
    except Exception:
        return []


def _nome_gpu_normalizado(nome: Optional[str]) -> str:
    """Normaliza o nome de GPU para comparação (case/pontuação/parênteses)."""
    if not nome:
        return ""
    texto = nome.lower()
    texto = re.sub(r"\([^)]*\)", "", texto)  # remove (R), (TM), sufixos
    texto = re.sub(r"\b(laptop|gpu|graphics)\b", "", texto)
    return re.sub(r"[^a-z0-9]+", "", texto)


def _associar_vram_sistema(gpus: list[GpuInfo], sistema_list: list[dict]) -> None:
    """Associa cada GPU (WMI) à VRAM 64-bit do Registro, de forma segura.

    Critérios em ordem:
    1. nome normalizado único no Registro;
    2. único WMI + único Registro (fallback por contagem, não ambíguo).

    VRAM inválida (fora da faixa, zero) é ignorada. Nada é inventado.
    """
    if not gpus or not sistema_list:
        return

    por_nome: dict[str, list[dict]] = {}
    for d in sistema_list:
        por_nome.setdefault(_nome_gpu_normalizado(d.get("name")), []).append(d)

    for gpu in gpus:
        nome_n = _nome_gpu_normalizado(gpu.name)
        candidatos = por_nome.get(nome_n, [])
        if len(candidatos) == 1:
            vram = candidatos[0].get("vram_mb")
            if vram is not None and VRAM_MIN_MB <= vram <= VRAM_MAX_MB:
                gpu.vram_mb = vram
                gpu.vram_source = "system"
            continue
        if len(candidatos) > 1:
            continue  # ambíguo: não misturar VRAM entre GPUs do mesmo nome
        # Fallback por contagem (sem nome correspondente) apenas se inequívoco.
        if len(gpus) == 1 and len(sistema_list) == 1:
            vram = sistema_list[0].get("vram_mb")
            if vram is not None and VRAM_MIN_MB <= vram <= VRAM_MAX_MB:
                gpu.vram_mb = vram
                gpu.vram_source = "system"


def _coletar_gpus() -> list[GpuInfo]:
    """Coleta via WMI e enriquece a VRAM com a fonte 64-bit do sistema."""
    gpus = _coletar_gpus_via_wmi()
    if not gpus:
        return gpus
    sistema_list = _vram_system_enriquecer()
    if sistema_list:
        _associar_vram_sistema(gpus, sistema_list)
    return gpus


# Heurística conservadora de recomendação
# ---------------------------------------------------------------------------

def _gpus_utilizaveis(gpus: list[GpuInfo]) -> list[GpuInfo]:
    """GPUs com Status OK (ou status desconhecido) — não descartadas."""
    return [g for g in gpus if g.status_ok is not False]


def recomendar_perfil(gpus: list[GpuInfo]) -> HardwareProfile:
    """Recomenda um dos 3 perfis validados a partir das GPUs coletadas.

    Separada da coleta para permitir testes sem executar PowerShell.
    Na dúvida => ``balanced`` (fallback universal).
    """
    if not gpus:
        return HardwareProfile(
            gpus=[], recommended_profile=PERFIL_BALANCED,
            reason="Nenhuma GPU detectada ou falha na coleta.",
            confidence=CONFIANCA_BAIXA,
        )

    utilizaveis = _gpus_utilizaveis(gpus)
    hibrido = len(gpus) > 1  # várias GPUs -> potencial notebook híbrido

    dgpus = [g for g in utilizaveis if g.dedicated is True]
    dgpus.sort(key=lambda g: g.vram_mb or 0, reverse=True)

    if dgpus:
        melhor = dgpus[0]
        vram = melhor.vram_mb
        if vram is not None and (vram < VRAM_MIN_MB or vram > VRAM_MAX_MB):
            vram = None  # valor implausível => desconhecido
        if vram is not None:
            # Decisão pela VRAM nominal (ex.: 6141 MB dedicado => 6 GB nominal).
            vram = _vram_nominal_mb(vram)
        confianca = CONFIANCA_MEDIA if hibrido else CONFIANCA_ALTA
        # AdapterRAM WMI próximo do teto 32-bit (~4 GB) não é certeza forte.
        if melhor.vram_source == "wmi" and _vram_wmi_suspeita_teto(vram):
            confianca = CONFIANCA_MEDIA
        if vram is not None and vram >= VRAM_LIMITE_QUALITY_MB:
            return HardwareProfile(
                gpus=list(gpus), recommended_profile=PERFIL_QUALITY,
                reason=f"GPU dedicada {melhor.name} com VRAM válida "
                       f"({vram} MB).",
                confidence=confianca,
            )
        if vram is not None and vram <= VRAM_LIMITE_PERFORMANCE_MB:
            return HardwareProfile(
                gpus=list(gpus), recommended_profile=PERFIL_PERFORMANCE,
                reason=f"GPU dedicada {melhor.name} com VRAM limitada "
                       f"({vram} MB).",
                confidence=confianca,
            )
        if vram is not None:
            aviso = ""
            if melhor.vram_source == "wmi" and _vram_wmi_suspeita_teto(vram):
                aviso = " (AdapterRAM possivelmente truncado; VRAM real pode ser maior)"
            return HardwareProfile(
                gpus=list(gpus), recommended_profile=PERFIL_BALANCED,
                reason=f"GPU dedicada {melhor.name} com VRAM intermediária "
                       f"({vram} MB).{aviso}",
                confidence=confianca,
            )
        return HardwareProfile(
            gpus=list(gpus), recommended_profile=PERFIL_BALANCED,
            reason=f"GPU dedicada {melhor.name} detectada, mas VRAM "
                   "indisponível. Fallback equilibrado.",
            confidence=CONFIANCA_MEDIA,
        )

    igpus = [g for g in utilizaveis if g.integrated is True]
    if igpus:
        return HardwareProfile(
            gpus=list(gpus), recommended_profile=PERFIL_PERFORMANCE,
            reason="Somente GPU integrada detectada.",
            confidence=(
                CONFIANCA_ALTA if len(igpus) == len(utilizaveis)
                else CONFIANCA_MEDIA
            ),
        )

    return HardwareProfile(
        gpus=list(gpus), recommended_profile=PERFIL_BALANCED,
        reason="Dados de hardware ambíguos ou incompletos. Fallback equilibrado.",
        confidence=CONFIANCA_BAIXA,
    )


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def detectar_gpus() -> list[GpuInfo]:
    """Coleta e normaliza as GPUs da máquina (WMI + VRAM 64-bit do sistema)."""
    return _coletar_gpus()


def detectar_hardware() -> HardwareProfile:
    """Detecta as GPUs e recomenda um perfil (sem aplicar nada)."""
    gpus = _coletar_gpus()
    return recomendar_perfil(gpus)


__all__ = [
    "GpuInfo",
    "HardwareProfile",
    "PERFIL_PERFORMANCE",
    "PERFIL_BALANCED",
    "PERFIL_QUALITY",
    "CONFIANCA_ALTA",
    "CONFIANCA_MEDIA",
    "CONFIANCA_BAIXA",
    "VENDOR_NVIDIA",
    "VENDOR_AMD",
    "VENDOR_INTEL",
    "VENDOR_UNKNOWN",
    "detectar_gpus",
    "recomendar_perfil",
    "detectar_hardware",
    "_extrair_vendor",
    "_normalizar_vram_mb",
    "_classificar_tipo",
    "_vram_wmi_suspeita_teto",
    "_vram_nominal_mb",
    "_vram_system_adaptadores",
    "_vram_system_enriquecer",
    "_associar_vram_sistema",
    "_nome_gpu_normalizado",
    "_coletar_gpus",
]

