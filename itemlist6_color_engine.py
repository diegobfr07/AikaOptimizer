#!/usr/bin/env python3
"""Lógica binária reutilizável para perfis de cor do ItemList6.

Este módulo usa apenas a biblioteca padrão, não possui interface gráfica e não
conhece caminhos da instalação do jogo. Todas as transformações são feitas em
memória; a política de publicação em disco pertence ao aplicativo chamador.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


HEADER_SIZE = 12
EXPECTED_HEADER = b"BR00022I\x00\x00\x00\x00"
RECORD_SIZE = 464
COLOR_FIELD_OFFSET = 427
TRAILER_SIZE = 4
UINT32_MASK = 0xFFFFFFFF
PROFILE_SCHEMA = "itemlist6-color-profile-v2"
LEGACY_PROFILE_SCHEMA = "itemlist6-color-profile-v1"
EXPECTED_PROFILE_SIZE = 438
EXPECTED_DISTRIBUTION = {4: 92, 5: 136, 6: 60, 7: 90, 8: 30, 9: 30}


def expand_ranges(ranges: Iterable[tuple[int, int]]) -> tuple[int, ...]:
    return tuple(value for start, end in ranges for value in range(start, end + 1))


ATTACK_RANGES = (
    (20_389, 20_403),
    (20_419, 20_433),
    (24_870, 24_884),
    (25_867, 25_881),
)
DEFENSE_RANGES = (
    (20_404, 20_418),
    (20_434, 20_448),
    (24_885, 24_899),
    (25_882, 25_896),
)
ATTACK_IDS = expand_ranges(ATTACK_RANGES)
DEFENSE_IDS = expand_ranges(DEFENSE_RANGES)


class ValidationError(RuntimeError):
    """Uma pré-condição ou invariante de integridade falhou."""


class IncompatibleUpdateError(ValidationError):
    """A estrutura ou um byte monitorado não corresponde ao perfil."""


class InputChangedError(ValidationError):
    """A entrada mudou no disco desde a análise."""


class OutputExistsError(ValidationError):
    """O destino já existe e não pode ser sobrescrito."""


class UnsafeOutputPathError(ValidationError):
    """O destino coincide com a entrada."""


class PublicationError(ValidationError):
    """Uma saída não pôde ser gravada ou publicada com segurança."""


@dataclass(frozen=True)
class StructureInfo:
    size: int
    header: bytes
    body_size: int
    record_count: int
    trailer: bytes
    trailer_u32le: int


@dataclass(frozen=True)
class ProfileEntry:
    record_id: int
    original_code: int
    group: str
    reference_source_byte: int

    @property
    def original_logical_code(self) -> int:
        """Nome explícito usado pelo schema v2, preservando a API Python anterior."""
        return self.original_code


@dataclass(frozen=True)
class ColorProfile:
    entries: tuple[ProfileEntry, ...]
    source_official_sha256: str
    source_white_sha256: str


@dataclass(frozen=True)
class ReferenceComparison:
    different_bytes: int
    body_differences: int
    trailer_differences: int
    distribution: dict[int, int]
    trailer_delta: int


@dataclass(frozen=True)
class RecordFieldDifference:
    record_id: int
    field_offset: int
    absolute_offset: int
    old_byte: int
    new_byte: int


@dataclass(frozen=True)
class VersionComparison:
    different_bytes: int
    contiguous_regions: int | None
    header_differences: int
    body_differences: int
    trailer_differences: int
    affected_records: tuple[int, ...]
    field_counts: dict[int, int]
    details: tuple[RecordFieldDifference, ...]
    added_records: int
    removed_records: int


@dataclass(frozen=True)
class CompatibilityMismatch:
    record_id: int
    absolute_offset: int
    old_byte: int
    new_byte: int


@dataclass(frozen=True)
class FileAnalysis:
    path: Path
    sha256: str
    structure: StructureInfo
    compatible_records: int
    mismatches: tuple[CompatibilityMismatch, ...]

    @property
    def compatible(self) -> bool:
        return not self.mismatches


@dataclass(frozen=True)
class PublishedOutput:
    path: Path
    result: "ApplyResult"


@dataclass(frozen=True)
class ApplyResult:
    data: bytes
    logical_delta: int
    old_trailer: bytes
    new_trailer: bytes
    changed_color_bytes: int
    changed_trailer_bytes: int
    changed_bytes: int
    attack_count: int
    defense_count: int
    common_count: int
    sha256: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def hex_bytes(data: bytes) -> str:
    return data.hex(" ").upper()


def color_offset(record_id: int) -> int:
    return HEADER_SIZE + record_id * RECORD_SIZE + COLOR_FIELD_OFFSET


def validate_structure(data: bytes, *, minimum_record_id: int | None = None) -> StructureInfo:
    if len(data) < HEADER_SIZE + TRAILER_SIZE:
        raise ValidationError(f"arquivo pequeno demais: {len(data)} bytes")
    if data[:HEADER_SIZE] != EXPECTED_HEADER:
        raise ValidationError(
            f"cabeçalho {hex_bytes(data[:HEADER_SIZE])}; esperado {hex_bytes(EXPECTED_HEADER)}"
        )
    body_size = len(data) - HEADER_SIZE - TRAILER_SIZE
    remainder = body_size % RECORD_SIZE
    if remainder:
        raise ValidationError(
            f"estrutura incompatível: ({len(data)} - 12 - 4) % 464 = {remainder}"
        )
    record_count = body_size // RECORD_SIZE
    if minimum_record_id is not None and record_count <= minimum_record_id:
        raise ValidationError(
            f"há {record_count} registros; o ID obrigatório {minimum_record_id} não existe"
        )
    trailer = data[-TRAILER_SIZE:]
    return StructureInfo(
        size=len(data),
        header=data[:HEADER_SIZE],
        body_size=body_size,
        record_count=record_count,
        trailer=trailer,
        trailer_u32le=int.from_bytes(trailer, "little"),
    )


def _validate_code(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255:
        raise ValidationError(f"{label} deve ser inteiro entre 0 e 255; recebido {value!r}")
    return value


def _validate_profile(profile: ColorProfile) -> ColorProfile:
    if len(profile.entries) != EXPECTED_PROFILE_SIZE:
        raise ValidationError(
            f"perfil contém {len(profile.entries)} registros; esperado {EXPECTED_PROFILE_SIZE}"
        )
    ids = [entry.record_id for entry in profile.entries]
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        raise ValidationError("IDs do perfil devem ser únicos e estar em ordem crescente")
    if any(record_id < 0 for record_id in ids):
        raise ValidationError("perfil contém ID negativo")
    for entry in profile.entries:
        _validate_code(entry.original_code, f"código original do registro {entry.record_id}")
        _validate_code(
            entry.reference_source_byte,
            f"byte oficial de referência do registro {entry.record_id}",
        )
        if entry.group not in {"attack", "defense", "common"}:
            raise ValidationError(
                f"grupo inválido no registro {entry.record_id}: {entry.group!r}"
            )

    distribution = Counter(entry.original_code for entry in profile.entries)
    if dict(sorted(distribution.items())) != EXPECTED_DISTRIBUTION:
        raise ValidationError(
            f"distribuição do perfil {dict(sorted(distribution.items()))}; "
            f"esperada {EXPECTED_DISTRIBUTION}"
        )
    attack = {entry.record_id for entry in profile.entries if entry.group == "attack"}
    defense = {entry.record_id for entry in profile.entries if entry.group == "defense"}
    common = {entry.record_id for entry in profile.entries if entry.group == "common"}
    if attack != set(ATTACK_IDS):
        raise ValidationError("grupo de ataque do perfil não coincide com as quatro faixas oficiais")
    if defense != set(DEFENSE_IDS):
        raise ValidationError("grupo de defesa do perfil não coincide com as quatro faixas oficiais")
    if attack & defense:
        raise ValidationError("grupos de ataque e defesa se sobrepõem")
    if len(attack) != 60 or len(defense) != 60 or len(common) != 318:
        raise ValidationError(
            f"grupos inválidos: ataque={len(attack)}, defesa={len(defense)}, comum={len(common)}"
        )
    if attack | defense | common != set(ids):
        raise ValidationError("classificação do perfil não cobre exatamente os 438 IDs")
    for label, digest in (
        ("source_official_sha256", profile.source_official_sha256),
        ("source_white_sha256", profile.source_white_sha256),
    ):
        if len(digest) != 64 or any(c not in "0123456789ABCDEF" for c in digest.upper()):
            raise ValidationError(f"{label} inválido")
    return profile


def build_profile_from_references(
    official: bytes, white_baseline: bytes
) -> tuple[ColorProfile, ReferenceComparison]:
    official_info = validate_structure(official)
    white_info = validate_structure(white_baseline)
    if official_info.record_count != 31_000 or white_info.record_count != 31_000:
        raise ValidationError("referências antigas não possuem exatamente 31.000 registros")
    if len(official) != len(white_baseline):
        raise ValidationError("referências oficial e branca possuem tamanhos diferentes")

    all_positions = [i for i, (a, b) in enumerate(zip(official, white_baseline)) if a != b]
    body_end = len(official) - TRAILER_SIZE
    body_positions = [i for i in all_positions if HEADER_SIZE <= i < body_end]
    outside = [i for i in all_positions if not HEADER_SIZE <= i < body_end]
    if len(body_positions) != EXPECTED_PROFILE_SIZE:
        raise ValidationError(
            f"Original × MOD possui {len(body_positions)} diferenças no corpo; esperado 438"
        )
    if any(position < body_end for position in outside):
        raise ValidationError("Original × MOD possui diferença no cabeçalho")
    if any(position < len(official) - TRAILER_SIZE for position in outside):
        raise ValidationError("Original × MOD possui diferença fora do campo e do rodapé")

    entries: list[ProfileEntry] = []
    seen: set[int] = set()
    distribution: Counter[int] = Counter()
    attack = set(ATTACK_IDS)
    defense = set(DEFENSE_IDS)
    for position in body_positions:
        record_id, field = divmod(position - HEADER_SIZE, RECORD_SIZE)
        if field != COLOR_FIELD_OFFSET:
            raise ValidationError(
                f"diferença de corpo no registro {record_id}, campo {field}; esperado campo 427"
            )
        if record_id in seen:
            raise ValidationError(f"mais de uma diferença no registro {record_id}")
        seen.add(record_id)
        original_code = (official[position] - white_baseline[position]) & 0xFF
        distribution[original_code] += 1
        group = "attack" if record_id in attack else "defense" if record_id in defense else "common"
        entries.append(
            ProfileEntry(record_id, original_code, group, official[position])
        )

    if dict(sorted(distribution.items())) != EXPECTED_DISTRIBUTION:
        raise ValidationError(
            f"distribuição lógica {dict(sorted(distribution.items()))}; "
            f"esperada {EXPECTED_DISTRIBUTION}"
        )
    if not attack <= seen or not defense <= seen:
        raise ValidationError("os 120 registros PvP não pertencem integralmente ao perfil")

    logical_sum = sum(entry.original_code for entry in entries)
    trailer_delta = white_info.trailer_u32le - official_info.trailer_u32le
    if trailer_delta != -logical_sum:
        raise ValidationError(
            f"delta do rodapé Original × MOD {trailer_delta:+d}; esperado {-logical_sum:+d}"
        )
    profile = _validate_profile(
        ColorProfile(
            entries=tuple(sorted(entries, key=lambda item: item.record_id)),
            source_official_sha256=sha256_bytes(official),
            source_white_sha256=sha256_bytes(white_baseline),
        )
    )
    comparison = ReferenceComparison(
        different_bytes=len(all_positions),
        body_differences=len(body_positions),
        trailer_differences=len(outside),
        distribution=dict(sorted(distribution.items())),
        trailer_delta=trailer_delta,
    )
    return profile, comparison


def profile_to_dict(profile: ColorProfile) -> dict[str, Any]:
    _validate_profile(profile)
    return {
        "schema": PROFILE_SCHEMA,
        "layout": {
            "header_size": HEADER_SIZE,
            "record_size": RECORD_SIZE,
            "color_field_offset": COLOR_FIELD_OFFSET,
            "trailer_size": TRAILER_SIZE,
        },
        "sources": {
            "official_sha256": profile.source_official_sha256,
            "white_baseline_sha256": profile.source_white_sha256,
        },
        "distribution": {str(k): v for k, v in EXPECTED_DISTRIBUTION.items()},
        "group_counts": {"attack": 60, "defense": 60, "common": 318},
        "records": [
            {
                "record_id": entry.record_id,
                "original_logical_code": entry.original_logical_code,
                "group": entry.group,
                "reference_source_byte": entry.reference_source_byte,
            }
            for entry in profile.entries
        ],
    }


def profile_to_bytes(profile: ColorProfile) -> bytes:
    return (json.dumps(profile_to_dict(profile), ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def parse_profile_bytes(payload: bytes) -> ColorProfile:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"perfil JSON inválido: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") not in {
        PROFILE_SCHEMA,
        LEGACY_PROFILE_SCHEMA,
    }:
        raise ValidationError(
            f"schema do perfil deve ser {PROFILE_SCHEMA!r} "
            f"(ou legado {LEGACY_PROFILE_SCHEMA!r})"
        )
    schema = value["schema"]
    expected_layout = {
        "header_size": HEADER_SIZE,
        "record_size": RECORD_SIZE,
        "color_field_offset": COLOR_FIELD_OFFSET,
        "trailer_size": TRAILER_SIZE,
    }
    if value.get("layout") != expected_layout:
        raise ValidationError(f"layout do perfil inválido: {value.get('layout')!r}")
    sources = value.get("sources")
    records = value.get("records")
    if not isinstance(sources, dict) or not isinstance(records, list):
        raise ValidationError("fontes ou registros ausentes no perfil")
    entries: list[ProfileEntry] = []
    for index, item in enumerate(records):
        if not isinstance(item, dict):
            raise ValidationError(f"registro {index} do perfil não é um objeto")
        record_id = item.get("record_id")
        original_code = item.get(
            "original_logical_code",
            item.get("original_code"),
        )
        group = item.get("group")
        reference_source_byte = item.get("reference_source_byte")
        if not isinstance(record_id, int) or isinstance(record_id, bool):
            raise ValidationError(f"record_id inválido na posição {index}")
        if not isinstance(group, str):
            raise ValidationError(f"grupo inválido na posição {index}")
        if schema == LEGACY_PROFILE_SCHEMA and reference_source_byte is None:
            raise ValidationError(
                "perfil legado não contém reference_source_byte; regenere-o a partir "
                "da referência oficial antiga"
            )
        entries.append(
            ProfileEntry(
                record_id,
                _validate_code(original_code, "original_logical_code"),
                group,
                _validate_code(reference_source_byte, "reference_source_byte"),
            )
        )
    profile = ColorProfile(
        entries=tuple(entries),
        source_official_sha256=str(sources.get("official_sha256", "")).upper(),
        source_white_sha256=str(sources.get("white_baseline_sha256", "")).upper(),
    )
    profile = _validate_profile(profile)
    expected_distribution = {str(k): v for k, v in EXPECTED_DISTRIBUTION.items()}
    if value.get("distribution") != expected_distribution:
        raise ValidationError("metadado de distribuição do perfil divergiu")
    if value.get("group_counts") != {"attack": 60, "defense": 60, "common": 318}:
        raise ValidationError("metadado de grupos do perfil divergiu")
    return profile


def load_profile(path: Path) -> ColorProfile:
    try:
        with path.open("rb") as handle:
            payload = handle.read()
    except OSError as exc:
        raise ValidationError(f"não foi possível abrir o perfil {path}: {exc}") from exc
    return parse_profile_bytes(payload)


def read_binary_file(path: Path) -> bytes:
    """Lê uma entrada exclusivamente em modo binário de leitura."""
    if not path.is_file():
        raise ValidationError(f"arquivo inexistente: {path}")
    try:
        with path.open("rb") as handle:
            return handle.read()
    except PermissionError as exc:
        raise ValidationError(f"permissão negada ao ler {path}") from exc
    except OSError as exc:
        raise ValidationError(f"erro de leitura em {path}: {exc}") from exc


def compare_structured_versions(old: bytes, new: bytes) -> VersionComparison:
    old_info = validate_structure(old)
    new_info = validate_structure(new)
    header_differences = sum(a != b for a, b in zip(old_info.header, new_info.header))
    details: list[RecordFieldDifference] = []
    field_counts: Counter[int] = Counter()
    for record_id in range(min(old_info.record_count, new_info.record_count)):
        base = HEADER_SIZE + record_id * RECORD_SIZE
        old_record = old[base : base + RECORD_SIZE]
        new_record = new[base : base + RECORD_SIZE]
        for field, (old_byte, new_byte) in enumerate(zip(old_record, new_record)):
            if old_byte != new_byte:
                details.append(
                    RecordFieldDifference(record_id, field, base + field, old_byte, new_byte)
                )
                field_counts[field] += 1
    added_records = max(0, new_info.record_count - old_info.record_count)
    removed_records = max(0, old_info.record_count - new_info.record_count)
    body_differences = len(details) + (added_records + removed_records) * RECORD_SIZE
    trailer_differences = sum(a != b for a, b in zip(old_info.trailer, new_info.trailer))
    different_bytes = header_differences + body_differences + trailer_differences

    contiguous_regions: int | None = None
    if len(old) == len(new):
        positions = [i for i, (a, b) in enumerate(zip(old, new)) if a != b]
        contiguous_regions = sum(
            1 for index, position in enumerate(positions) if index == 0 or position != positions[index - 1] + 1
        )
        if len(positions) != different_bytes:
            raise ValidationError("contagem estruturada divergiu da comparação byte a byte")
    return VersionComparison(
        different_bytes=different_bytes,
        contiguous_regions=contiguous_regions,
        header_differences=header_differences,
        body_differences=body_differences,
        trailer_differences=trailer_differences,
        affected_records=tuple(sorted({item.record_id for item in details})),
        field_counts=dict(sorted(field_counts.items())),
        details=tuple(details),
        added_records=added_records,
        removed_records=removed_records,
    )


def profile_compatibility(
    old_official: bytes, updated_official: bytes, profile: ColorProfile
) -> tuple[CompatibilityMismatch, ...]:
    old_info = validate_structure(old_official)
    new_info = validate_structure(updated_official, minimum_record_id=max(e.record_id for e in profile.entries))
    if old_info.record_count <= max(entry.record_id for entry in profile.entries):
        raise ValidationError("referência antiga não contém todos os IDs do perfil")
    mismatches = []
    for entry in profile.entries:
        offset = color_offset(entry.record_id)
        if old_official[offset] != updated_official[offset]:
            mismatches.append(
                CompatibilityMismatch(
                    entry.record_id,
                    offset,
                    old_official[offset],
                    updated_official[offset],
                )
            )
    return tuple(mismatches)


def profile_compatibility_from_reference(
    source: bytes, profile: ColorProfile
) -> tuple[CompatibilityMismatch, ...]:
    """Valida um BIN usando apenas os bytes oficiais incorporados no perfil."""
    profile = _validate_profile(profile)
    validate_structure(source, minimum_record_id=max(e.record_id for e in profile.entries))
    mismatches = []
    for entry in profile.entries:
        offset = color_offset(entry.record_id)
        current = source[offset]
        if current != entry.reference_source_byte:
            mismatches.append(
                CompatibilityMismatch(
                    entry.record_id,
                    offset,
                    entry.reference_source_byte,
                    current,
                )
            )
    return tuple(mismatches)


def analyze_file(path: Path, profile: ColorProfile) -> FileAnalysis:
    """Lê e analisa um único BIN sem abri-lo para escrita."""
    resolved = path.resolve(strict=False)
    data = read_binary_file(resolved)
    structure = validate_structure(
        data, minimum_record_id=max(entry.record_id for entry in profile.entries)
    )
    mismatches = profile_compatibility_from_reference(data, profile)
    return FileAnalysis(
        path=resolved,
        sha256=sha256_bytes(data),
        structure=structure,
        compatible_records=len(profile.entries) - len(mismatches),
        mismatches=mismatches,
    )


def _destination(entry: ProfileEntry, attack_code: int, defense_code: int, common_code: int) -> int:
    if entry.group == "attack":
        return attack_code
    if entry.group == "defense":
        return defense_code
    return common_code


def apply_colors(
    source: bytes,
    profile: ColorProfile,
    *,
    attack_code: int = 8,
    defense_code: int = 7,
    common_code: int = 0,
) -> ApplyResult:
    profile = _validate_profile(profile)
    attack_code = _validate_code(attack_code, "attack_code")
    defense_code = _validate_code(defense_code, "defense_code")
    common_code = _validate_code(common_code, "common_code")
    info = validate_structure(source, minimum_record_id=max(e.record_id for e in profile.entries))
    output = bytearray(source)
    logical_delta = 0
    for entry in profile.entries:
        offset = color_offset(entry.record_id)
        destination = _destination(entry, attack_code, defense_code, common_code)
        output[offset] = (source[offset] + destination - entry.original_code) & 0xFF
        logical_delta += destination - entry.original_code
    new_trailer_u32 = (info.trailer_u32le + logical_delta) & UINT32_MASK
    output[-TRAILER_SIZE:] = new_trailer_u32.to_bytes(TRAILER_SIZE, "little")
    result_data = bytes(output)
    changed_positions = {i for i, (a, b) in enumerate(zip(source, result_data)) if a != b}
    color_offsets = {color_offset(entry.record_id) for entry in profile.entries}
    trailer_offsets = set(range(len(source) - TRAILER_SIZE, len(source)))
    unexpected = changed_positions - color_offsets - trailer_offsets
    if unexpected:
        raise ValidationError(f"transformação alterou offsets não autorizados: {sorted(unexpected)[:10]}")
    counts = Counter(entry.group for entry in profile.entries)
    return ApplyResult(
        data=result_data,
        logical_delta=logical_delta,
        old_trailer=info.trailer,
        new_trailer=result_data[-TRAILER_SIZE:],
        changed_color_bytes=len(changed_positions & color_offsets),
        changed_trailer_bytes=len(changed_positions & trailer_offsets),
        changed_bytes=len(changed_positions),
        attack_count=counts["attack"],
        defense_count=counts["defense"],
        common_count=counts["common"],
        sha256=sha256_bytes(result_data),
    )


def reproduce_independently(
    source: bytes,
    profile: ColorProfile,
    *,
    attack_code: int = 8,
    defense_code: int = 7,
    common_code: int = 0,
) -> bytes:
    """Segunda reprodução: deriva primeiro o baseline branco de cada registro."""
    validate_structure(source, minimum_record_id=max(e.record_id for e in profile.entries))
    destinations = {"attack": attack_code, "defense": defense_code, "common": common_code}
    for label, value in destinations.items():
        destinations[label] = _validate_code(value, f"{label}_code")
    reproduced = bytearray(source)
    additions = 0
    subtractions = 0
    for entry in profile.entries:
        offset = color_offset(entry.record_id)
        white_byte = (source[offset] - entry.original_code) & 0xFF
        reproduced[offset] = (white_byte + destinations[entry.group]) & 0xFF
        additions += destinations[entry.group]
        subtractions += entry.original_code
    trailer_value = int.from_bytes(source[-TRAILER_SIZE:], "little")
    reproduced[-TRAILER_SIZE:] = (
        (trailer_value + additions - subtractions) & UINT32_MASK
    ).to_bytes(TRAILER_SIZE, "little")
    return bytes(reproduced)


def validate_output(
    source: bytes,
    output: bytes,
    profile: ColorProfile,
    *,
    attack_code: int = 8,
    defense_code: int = 7,
    common_code: int = 0,
) -> ApplyResult:
    source_info = validate_structure(source, minimum_record_id=max(e.record_id for e in profile.entries))
    output_info = validate_structure(output, minimum_record_id=max(e.record_id for e in profile.entries))
    if len(source) != len(output):
        raise ValidationError("o tamanho da saída divergiu da entrada atualizada")
    if output_info.header != source_info.header:
        raise ValidationError("o cabeçalho da saída divergiu da entrada atualizada")
    expected = apply_colors(
        source,
        profile,
        attack_code=attack_code,
        defense_code=defense_code,
        common_code=common_code,
    )
    if output != expected.data:
        positions = [i for i, (a, b) in enumerate(zip(output, expected.data)) if a != b]
        raise ValidationError(f"saída divergiu da reprodução esperada nos offsets {positions[:10]}")

    destinations = {"attack": attack_code, "defense": defense_code, "common": common_code}
    observed: Counter[tuple[str, int]] = Counter()
    for entry in profile.entries:
        offset = color_offset(entry.record_id)
        white_byte = (source[offset] - entry.original_code) & 0xFF
        logical_code = (output[offset] - white_byte) & 0xFF
        observed[(entry.group, logical_code)] += 1
    required = Counter(
        {
            ("attack", attack_code): 60,
            ("defense", defense_code): 60,
            ("common", common_code): 318,
        }
    )
    if observed != required:
        raise ValidationError(f"códigos lógicos finais inválidos: {dict(observed)}")
    independently = reproduce_independently(
        source,
        profile,
        attack_code=attack_code,
        defense_code=defense_code,
        common_code=common_code,
    )
    if independently != output:
        raise ValidationError("segunda reprodução independente divergiu da saída")
    return expected


def _same_path_or_file(first: Path, second: Path) -> bool:
    if first.resolve(strict=False) == second.resolve(strict=False):
        return True
    try:
        return first.exists() and second.exists() and os.path.samefile(first, second)
    except OSError:
        return False


def _publish_no_overwrite(temporary: Path, destination: Path) -> None:
    """Publica atomicamente por hard link, recusando uma corrida de sobrescrita."""
    try:
        os.link(temporary, destination)
    except FileExistsError as exc:
        raise OutputExistsError(f"saída já existente: {destination}") from exc
    except PermissionError as exc:
        raise PublicationError(f"permissão negada ao publicar {destination}") from exc
    except OSError as exc:
        raise PublicationError(f"erro ao publicar {destination}: {exc}") from exc
    temporary.unlink()


def generate_file(
    input_path: Path,
    output_path: Path,
    profile: ColorProfile,
    *,
    expected_input_sha256: str,
    attack_code: int = 8,
    defense_code: int = 7,
    common_code: int = 0,
) -> PublishedOutput:
    """Gera, valida e publica um BIN usando apenas entrada, perfil e códigos.

    A entrada é relida somente para leitura e precisa manter o SHA-256 analisado.
    O temporário é criado no diretório final, recebe ``flush``/``fsync``, é
    relido, validado e só então publicado sem possibilidade de sobrescrita.
    """
    input_path = input_path.resolve(strict=False)
    output_path = output_path.resolve(strict=False)
    if _same_path_or_file(input_path, output_path):
        raise UnsafeOutputPathError("a saída não pode ser igual à entrada")
    if output_path.exists():
        raise OutputExistsError(f"saída já existente: {output_path}")
    if not output_path.parent.is_dir():
        raise PublicationError(f"pasta de saída inexistente: {output_path.parent}")

    source = read_binary_file(input_path)
    source_sha256 = sha256_bytes(source)
    if source_sha256 != expected_input_sha256.upper():
        raise InputChangedError(
            "a entrada foi modificada após a análise; analise o arquivo novamente"
        )
    mismatches = profile_compatibility_from_reference(source, profile)
    if mismatches:
        raise IncompatibleUpdateError(
            f"{len(mismatches)} dos 438 registros monitorados mudaram"
        )

    result = apply_colors(
        source,
        profile,
        attack_code=attack_code,
        defense_code=defense_code,
        common_code=common_code,
    )
    validate_output(
        source,
        result.data,
        profile,
        attack_code=attack_code,
        defense_code=defense_code,
        common_code=common_code,
    )

    descriptor = -1
    temporary: Path | None = None
    committed = False
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(result.data)
            handle.flush()
            os.fsync(handle.fileno())

        disk_output = read_binary_file(temporary)
        disk_result = validate_output(
            source,
            disk_output,
            profile,
            attack_code=attack_code,
            defense_code=defense_code,
            common_code=common_code,
        )
        if disk_output != result.data or disk_result.sha256 != result.sha256:
            raise PublicationError("falha na validação final do arquivo temporário")
        if sha256_bytes(read_binary_file(input_path)) != source_sha256:
            raise InputChangedError("a entrada mudou durante a geração")

        _publish_no_overwrite(temporary, output_path)
        temporary = None
        committed = True
        published = read_binary_file(output_path)
        published_result = validate_output(
            source,
            published,
            profile,
            attack_code=attack_code,
            defense_code=defense_code,
            common_code=common_code,
        )
        if published != result.data or published_result.sha256 != result.sha256:
            raise PublicationError("falha na validação final do arquivo publicado")
        if sha256_bytes(read_binary_file(input_path)) != source_sha256:
            raise InputChangedError("a entrada mudou durante a publicação")
        return PublishedOutput(output_path, published_result)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if committed:
            output_path.unlink(missing_ok=True)
        raise