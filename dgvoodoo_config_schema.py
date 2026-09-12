# -*- coding: utf-8 -*-
"""dgvoodoo_config_schema — ESTÁGIO 1 (SOMENTE LEITURA/DESCRITIVO).

Catálogo semântico do dgVoodoo.conf adotado/validado pelo projeto
(dgVoodoo2 2.87.4), derivado de:
- Mapa_dgVoodoo_2.87.4_Aika.md (classes 1-6, tipos, domínios, lacunas);
- Overlay_AIKA_dgVoodoo_2.87.4_Auditado_codigo.md (14 controladas =
  12 fixas + 2 de perfil; 80 herdadas; 94 ativas + ;LogToFile comentada).

Nesta fase o schema é um índice DESCRITIVO: marca unknown_to_schema
(herdado: preservar, nunca rejeitar); NÃO normaliza, NÃO corrige, NÃO
escreve, NÃO resolve camadas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from dgvoodoo_config_engine import Catalog

GLOBAL_KEY = "Version"
GLOBAL_LABEL = "[GLOBAL].Version"  # notação documental apenas


@dataclass(frozen=True)
class FieldMeta:
    tipo: str
    classe: str
    congelado: bool = True
    regra_aika: str = ""
    perfil: str = ""
    lacuna: str = ""
    evidencia: str = ""
    dominio: str = ""


# (chave, tipo, classe) — tipo/convenção do Mapa (B/E/I/S/L); classe 1..6.
_KEYS: Dict[str, List[Tuple[str, str, str]]] = {
    "General": [
        ("OutputAPI", "E", "1"), ("Adapters", "E/I", "4"),
        ("FullScreenOutput", "E/I", "4"), ("FullScreenMode", "B", "4"),
        ("ScalingMode", "E", "4"), ("ProgressiveScanlineOrder", "B", "4"),
        ("EnumerateRefreshRates", "B", "4"), ("Brightness", "I", "3"),
        ("Color", "I", "3"), ("Contrast", "I", "3"),
        ("InheritColorProfileInFullScreenMode", "B", "4"),
        ("KeepWindowAspectRatio", "B", "3"), ("CaptureMouse", "B", "3"),
        ("CenterAppWindow", "B", "4"), ("DisableScreenSaver", "B", "3"),
    ],
    "GeneralExt": [
        ("DesktopResolution", "S", "4"), ("DesktopBitDepth", "I", "4"),
        ("DeframerSize", "I", "4"), ("ImageScaleFactor", "I/S", "4"),
        ("CursorScaleFactor", "I", "3"), ("DisplayROI", "S", "4"),
        ("Resampling", "E", "3"), ("PresentationModel", "E", "4"),
        ("ColorSpace", "E", "4"), ("WatermarkDisplayDuration", "I", "5"),
        ("FreeMouse", "B", "4"), ("WindowedAttributes", "L", "4"),
        ("FullscreenAttributes", "L", "4"), ("FPSLimit", "I", "3"),
        ("Environment", "E", "5"), ("SystemHookFlags", "L", "4"),
    ],
    "Glide": [
        ("VideoCard", "E", "5"), ("OnboardRAM", "I", "5"),
        ("MemorySizeOfTMU", "I", "5"), ("NumberOfTMUs", "I", "5"),
        ("TMUFiltering", "E", "5"), ("DisableMipmapping", "B", "5"),
        ("Resolution", "S", "5"), ("Antialiasing", "E", "5"),
        ("EnableGlideGammaRamp", "B", "5"), ("ForceVerticalSync", "B", "5"),
        ("ForceEmulatingTruePCIAccess", "B", "5"),
        ("16BitDepthBuffer", "B", "5"), ("3DfxWatermark", "B", "5"),
        ("3DfxSplashScreen", "B", "5"), ("PointcastPalette", "B", "5"),
        ("EnableInactiveAppState", "B", "5"),
    ],
    "GlideExt": [
        ("DitheringEffect", "E", "5"), ("Dithering", "E", "5"),
        ("DitherOrderedMatrixSizeScale", "I", "5"),
    ],
    "DirectX": [
        ("DisableAndPassThru", "B", "1"), ("VideoCard", "E", "4"),
        ("VRAM", "I", "6"), ("Filtering", "E/I", "2"),
        ("Mipmapping", "E", "4"), ("KeepFilterIfPointSampled", "B", "3"),
        ("Resolution", "S", "4"), ("Antialiasing", "E", "2"),
        ("AppControlledScreenMode", "B", "4"),
        ("DisableAltEnterToToggleScreenMode", "B", "4"),
        ("Bilinear2DOperations", "B", "6"), ("PhongShadingWhenPossible", "B", "6"),
        ("ForceVerticalSync", "B", "3"), ("dgVoodooWatermark", "B", "1"),
        ("FastVideoMemoryAccess", "B", "6"), ("DisableD3DTnLDevice", "B", "6"),
    ],
    "DirectXExt": [
        ("AdapterIDType", "E", "4"), ("VendorID", "I", "4"),
        ("DeviceID", "I", "4"), ("SubsystemID", "I", "4"),
        ("RevisionID", "I", "4"), ("DefaultEnumeratedResolutions", "E", "4"),
        ("ExtraEnumeratedResolutions", "L", "4"),
        ("EnumeratedResolutionBitdepths", "L", "4"),
        ("DitheringEffect", "E", "4"), ("Dithering", "E", "4"),
        ("DitherOrderedMatrixSizeScale", "I", "4"),
        ("DepthBuffersBitDepth", "E", "4"), ("Default3DRenderFormat", "E", "4"),
        ("MaxVSConstRegisters", "I", "4"), ("D3D12BoundsChecking", "B", "5"),
        ("NPatchTesselationLevel", "I", "4"),
        ("DisplayOutputEnableMask", "I", "4"), ("MSD3DDeviceNames", "B", "4"),
        ("RTTexturesForceScaleAndMSAA", "B", "4"),
        ("SmoothedDepthSampling", "B", "4"),
        ("DeferredScreenModeSwitch", "B", "4"),
        ("PrimarySurfaceBatchedUpdate", "B", "6"), ("SuppressAMDBlacklist", "B", "4"),
    ],
    "Debug": [
        ("Info", "E", "5"), ("Warning", "E", "5"), ("Error", "E", "5"),
        ("MaxTraceLevel", "I", "5"),
    ],
}


# Opção comentada conhecida (não ativa): ;LogToFile = false
COMMENTED_OPTIONS: Dict[str, Set[str]] = {"Debug": {"LogToFile"}}

# -- Fixas do overlay (valores efetivos documentados) -----------------------
# Version é estrutural (classe 1), literal preservado — não é "fixa" de perfil.
FIXAS: Dict[Tuple[Optional[str], str], str] = {
    (None, "Version"): "0x287",
    ("General", "OutputAPI"): "d3d11_fl11_0",
    ("General", "Adapters"): "1",
    ("General", "FullScreenMode"): "false",
    ("General", "DisableScreenSaver"): "true",
    ("DirectX", "DisableAndPassThru"): "false",
    ("DirectX", "VideoCard"): "internal3D",
    ("DirectX", "VRAM"): "1024",
    ("DirectX", "KeepFilterIfPointSampled"): "true",
    ("DirectX", "AppControlledScreenMode"): "true",
    ("DirectX", "DisableAltEnterToToggleScreenMode"): "true",
    ("DirectX", "FastVideoMemoryAccess"): "true",
    ("DirectX", "dgVoodooWatermark"): "false",  # obrigatória
}
# Overlay: 12 fixas (sem contar Version estrutural) + 2 de perfil = 14
# explicitamente atribuídas.

PERFIS: Dict[Tuple[Optional[str], str], str] = {
    ("DirectX", "Filtering"): "base=16 | performance=trilinear | balanced=16 | quality=16",
    ("DirectX", "Antialiasing"): "base=2x | performance=appdriven | balanced=2x | quality=4x",
}
PERFIL_FILTERING = ("DirectX", "Filtering")
PERFIL_ANTIALIASING = ("DirectX", "Antialiasing")

KNOWN_GLOBAL: Set[str] = {GLOBAL_KEY}
KNOWN_SECTIONS: Set[str] = set(_KEYS.keys())


def _build() -> Tuple[Dict[Tuple[Optional[str], str], FieldMeta], Catalog]:
    metas: Dict[Tuple[Optional[str], str], FieldMeta] = {}
    catalog: Catalog = {None: set(KNOWN_GLOBAL)}
    for secao, lista in _KEYS.items():
        catalog[secao] = set()
        for chave, tipo, classe in lista:
            ident = (secao, chave)
            metas[ident] = FieldMeta(tipo=tipo, classe=classe)
            catalog[secao].add(chave)
    # metadados específicos das controladas
    for ident, valor in FIXAS.items():
        meta = metas.get(ident)
        if meta is None:
            continue
        regra = f"fixo:{valor}"
        if ident == (None, "Version"):
            regra = "estrutural: literal preservado do template"
        metas[ident] = FieldMeta(
            tipo=meta.tipo, classe=meta.classe, congelado=True,
            regra_aika=regra, lacuna=meta.lacuna, evidencia="Overlay/Mapa",
        )
    for ident, txt in PERFIS.items():
        meta = metas.get(ident)
        if meta is None:
            continue
        metas[ident] = FieldMeta(
            tipo=meta.tipo, classe=meta.classe, congelado=True,
            regra_aika="base + perfil", perfil=txt,
            evidencia="Overlay (PERFIS_CONF)",
        )
    # Fixas obrigatórias mantêm dgVoodooWatermark e OutputAPI explícitos.
    return metas, catalog


FIELD_META, CATALOG = _build()


def is_known(section: Optional[str], key: str) -> bool:
    if section is None:
        return key in CATALOG.get(None, set())
    return key in CATALOG.get(section, set())


def describe(section: Optional[str], key: str) -> Optional[FieldMeta]:
    """Metadados descritivos do campo, ou None se desconhecido do schema."""
    return FIELD_META.get((section, key))


def total_esperado() -> int:
    """94 chaves ativas (1 global + 93 em seções)."""
    return 1 + sum(len(v) for sec, v in CATALOG.items() if sec is not None)


# ---------------------------------------------------------------------------
# Estágio 2 — camadas de geração (somente leitura/descritivo) e domínios
# ---------------------------------------------------------------------------

# 12 invariantes do overlay fixo AIKA (arquitetura aprovada).
OVERLAY_FIXO: Dict[str, Dict[str, str]] = {
    "General": {
        "OutputAPI": "d3d11_fl11_0",
        "Adapters": "1",
        "FullScreenMode": "false",
        "DisableScreenSaver": "true",
    },
    "DirectX": {
        "DisableAndPassThru": "false",
        "VideoCard": "internal3D",
        "VRAM": "1024",
        "KeepFilterIfPointSampled": "true",
        "AppControlledScreenMode": "true",
        "DisableAltEnterToToggleScreenMode": "true",
        "FastVideoMemoryAccess": "true",
        "dgVoodooWatermark": "false",
    },
}

# Base Balanced (Ativar/Reaplicar): Filtering/Antialiasing.
BASE_AIKA: Dict[str, Dict[str, str]] = {
    "DirectX": {"Filtering": "16", "Antialiasing": "2x"},
}

# Perfis existentes (nenhum quarto perfil; AUTO é resolvido fora do engine).
PERFIS_MAP: Dict[str, Dict[str, Dict[str, str]]] = {
    "performance": {"DirectX": {"Filtering": "trilinear", "Antialiasing": "appdriven"}},
    "balanced": {"DirectX": {"Filtering": "16", "Antialiasing": "2x"}},
    "quality": {"DirectX": {"Filtering": "16", "Antialiasing": "4x"}},
}

_BOOLS = frozenset({"true", "false"})
_OUTPUT_API = frozenset({
    "d3d11warp", "d3d11_fl10_0", "d3d11_fl10_1", "d3d11_fl11_0",
    "d3d12_fl11_0", "d3d12_fl12_0", "bestavailable",
})
_DIRECTX_VIDEOCARD = frozenset({
    "svga", "internal3D", "geforce_ti_4800", "ati_radeon_8500",
    "matrox_parhelia-512", "geforce_fx_5700_ultra", "geforce_9800_gt",
})
_FILTERING_ENUM = frozenset({
    "appdriven", "pointsampled", "bilinear", "pointmip", "linearmip",
    "trilinear",
})
_ANTIALIASING = frozenset({"off", "appdriven", "2x", "4x", "8x"})

import re as _re  # noqa: E402


def validate_domain(identity: Tuple[Optional[str], str], value: str) -> Optional[str]:
    """Valida um valor que overlay/perfil/personalização pretende ESCREVER.

    Retorna None (ok) ou mensagem de erro. Domínio desconhecido não bloqueia.
    Herança do template desconhecida NÃO passa por aqui (ver engine).
    """
    secao, chave = identity
    if chave in _BOOLS or chave in (
            "DisableAndPassThru", "FullScreenMode", "DisableScreenSaver",
            "KeepFilterIfPointSampled", "AppControlledScreenMode",
            "DisableAltEnterToToggleScreenMode", "FastVideoMemoryAccess",
            "dgVoodooWatermark"):
        return None if value in _BOOLS else f"esperado booleano true/false"
    if secao == "General" and chave == "OutputAPI":
        return None if value in _OUTPUT_API else f"OutputAPI fora do domínio"
    if secao == "General" and chave == "Adapters":
        if value == "all" or value.isdigit() and int(value) >= 1:
            return None
        return "Adapters deve ser 'all' ou ordinal >= 1"
    if secao == "DirectX" and chave == "VideoCard":
        return None if value in _DIRECTX_VIDEOCARD else f"VideoCard fora do domínio"
    if secao == "DirectX" and chave == "VRAM":
        if value.isdigit() and int(value) > 0:
            return None
        if _re.fullmatch(r"\d+GB", value):
            return None
        return "VRAM deve ser MB (número) ou NGB"
    if secao == "DirectX" and chave == "Filtering":
        if value in _FILTERING_ENUM:
            return None
        if value.isdigit() and 1 <= int(value) <= 16:
            return None
        return "Filtering fora do domínio (enum ou aniso 1..16)"
    if secao == "DirectX" and chave == "Antialiasing":
        return None if value in _ANTIALIASING else "Antialiasing fora do domínio"
    return None  # domínio não comprovado/desconhecido -> não bloqueia


__all__ = [
    "GLOBAL_KEY", "GLOBAL_LABEL", "FieldMeta", "FIXAS", "PERFIS",
    "PERFIL_FILTERING", "PERFIL_ANTIALIASING", "KNOWN_GLOBAL", "KNOWN_SECTIONS",
    "COMMENTED_OPTIONS", "FIELD_META", "CATALOG", "is_known", "describe",
    "total_esperado", "OVERLAY_FIXO", "BASE_AIKA", "PERFIS_MAP",
    "validate_domain",
]
