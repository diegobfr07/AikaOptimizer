# -*- coding: utf-8 -*-
"""Serviço operacional de Cores das Pedras (V4.1.0).

Backup versionado por instalação, reconhecimento de estado por conteúdo e
aplicação/restauração transacionais do ``<raiz do cliente>/ItemList6.bin``.

Este módulo não possui interface gráfica e reutiliza a lógica binária congelada
em ``itemlist6_color_engine`` para analisar, gerar e validar. A publicação no
cliente é feita aqui de forma atômica, no mesmo volume, com registro durável de
intenção antes da substituição. Nunca usa ``UI/ItemList6.bin`` nem subpastas.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import config
import itemlist6_color_engine as engine


METADATA_FORMAT_VERSION = 1
STORAGE_SUBDIR = "Pedras"
BASES_SUBDIR = "bases"

_lock = threading.RLock()  # exclusão mútua das operações de Pedras do app

KIND_NOT_CONFIGURED = "not_configured"
KIND_MISSING = "missing"
KIND_BASE = "base"
KIND_PERSONALIZED = "personalized"
KIND_EXTERNAL_COMPATIBLE = "external_compatible"
KIND_EXTERNAL_INCOMPATIBLE = "external_incompatible"


class StonesError(engine.ValidationError):
    """Falha operacional de Pedras (não é necessariamente problema de conteúdo)."""


class ProcessRunningError(StonesError):
    """Jogo/launcher aberto: escrita bloqueada."""


class StonesBlockedError(StonesError):
    """Escrita bloqueada por estado externo pendente de análise segura."""


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _new_id() -> str:
    return (
        f"pedras-{datetime.now().strftime('%Y%m%d%H%M%S')}-"
        f"{os.getpid()}-{threading.get_ident()}"
    )


def sha256_file(path: Path) -> str:
    digest = __import__("hashlib").sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_stable(path: Path) -> bytes:
    """Lê duas vezes e exige estabilidade, reduzindo a janela de corrida."""
    first = engine.read_binary_file(path)
    second = engine.read_binary_file(path)
    if first != second:
        raise engine.InputChangedError("o arquivo mudou durante a leitura; analise novamente")
    return first


def _atomic_write(path: Path, data: bytes) -> None:
    directory = os.path.dirname(str(path))
    os.makedirs(directory, exist_ok=True)
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=directory)
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


def _atomic_replace(target: Path, data: bytes) -> None:
    """Substitui o alvo atomicamente; nunca remove o original antes da escrita."""
    directory = os.path.dirname(str(target))
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=directory)
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            try:
                os.chmod(target, stat.S_IWRITE)
            except OSError:
                pass
        os.replace(temporary, target)
        temporary = None
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


class ProcessVerifyError(StonesError):
    """Não foi possível verificar se o jogo/launcher está em execução."""


@dataclass(frozen=True)
class ProcessMatch:
    name: str
    pid: int
    exe: str | None
    rule: str


@dataclass(frozen=True)
class ProcessDetection:
    matches: tuple[ProcessMatch, ...]
    verify_error: str | None

    @property
    def blocked(self) -> bool:
        return bool(self.matches) or self.verify_error is not None


def _process_label(name: str) -> str:
    lowered = (name or "").lower()
    if lowered in config.AIKA_LAUNCHER_EXES:
        return "launcher do Aika"
    return "jogo do Aika"


def detect_relevant_processes(client_root: Any) -> ProcessDetection:
    """Localiza processos do jogo/launcher realmente ligados ao cliente selecionado.

    Usa nome exato + caminho normalizado quando disponível. Nunca bloqueia por
    simples ocorrência de "aika" em nomes/títulos/argumentos, nem por processos
    de outra instalação. Processos inacessíveis/encerrados durante a enumeração
    são ignorados; a impossibilidade total de verificar é reportada à parte.
    """
    root, _ = resolve_target(client_root)
    root_norm = os.path.normcase(os.path.abspath(str(root))) if root is not None else None
    exes = set(config.AIKA_GAME_EXES) | set(config.AIKA_LAUNCHER_EXES)
    try:
        import psutil
    except Exception as exc:
        return ProcessDetection((), f"não foi possível carregar psutil: {exc}")
    try:
        procs = list(psutil.process_iter(["name", "pid"]))
    except Exception as exc:
        return ProcessDetection((), f"não foi possível enumerar processos: {exc}")

    matches: list[ProcessMatch] = []
    for proc in procs:
        try:
            name = (proc.info.get("name") or "").lower()
            pid = int(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue  # processo encerrou/ficou inacessível durante a enumeração
        if name not in exes:
            continue
        exe = None
        try:
            exe = proc.exe()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            exe = None
        if exe:
            exe_norm = os.path.normcase(os.path.abspath(exe))
            if root_norm is not None and not (
                exe_norm == root_norm or exe_norm.startswith(root_norm + os.sep)
            ):
                # Nome alvo, mas de outra instalação: não bloqueia o cliente selecionado.
                continue
            rule = "nome exato + caminho no cliente selecionado"
        else:
            rule = "nome exato (caminho indisponível)"
        matches.append(ProcessMatch(proc.info.get("name") or name, pid, exe, rule))
    return ProcessDetection(tuple(matches), None)


def _require_processes_closed(client_root: Any) -> None:
    detection = detect_relevant_processes(client_root)
    if detection.matches:
        match = detection.matches[0]
        detail = f"{match.name} (PID {match.pid})"
        if match.exe:
            detail += f" — {match.exe}"
        else:
            detail += " — caminho indisponível"
        raise ProcessRunningError(
            f"Feche o {_process_label(match.name)} antes de aplicar ou restaurar: {detail}."
        )
    if detection.verify_error:
        raise ProcessVerifyError(
            "Não foi possível verificar se o jogo/launcher do Aika está em execução: "
            f"{detection.verify_error}"
        )
def resolve_target(client_root: Any) -> tuple[Path | None, Path | None]:
    """Normaliza a raiz do cliente e retorna (raiz, alvo). Sem busca em subpastas."""
    raw = config.normalizar_pasta_jogo(None if client_root is None else str(client_root))
    if not raw or not os.path.isdir(raw):
        return None, None
    root = Path(raw)
    return root, root / "ItemList6.bin"


def storage_dir(client_root: Any, storage_base: Any = None, create: bool = True) -> Path:
    """Namespace persistente de Pedras exclusivo para a instalação do cliente."""
    root, _ = resolve_target(client_root)
    if storage_base is not None:
        ident = config.identidade_cliente(str(root))
        return Path(storage_base) / "Clientes" / ident / STORAGE_SUBDIR
    return Path(config.obter_pasta_backup_cliente(str(root), criar=create)) / STORAGE_SUBDIR


def bases_dir(client_root: Any, storage_base: Any = None, create: bool = True) -> Path:
    directory = storage_dir(client_root, storage_base, create=create) / BASES_SUBDIR
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    return directory


def metadata_path(client_root: Any, storage_base: Any = None, create: bool = True) -> Path:
    return storage_dir(client_root, storage_base, create=create) / "metadata.json"


def _profile_hash(profile_path: Any) -> str:
    try:
        return engine.sha256_bytes(Path(profile_path).read_bytes())
    except OSError as exc:
        raise engine.ValidationError(f"não foi possível ler o perfil: {exc}") from exc


def _empty_metadata(target: Path, profile_hash: str) -> dict[str, Any]:
    return {
        "format_version": METADATA_FORMAT_VERSION,
        "target": str(target),
        "profile_sha256": profile_hash,
        "bases": [],
        "applications": [],
        "pending": [],
        "blocked": [],
        "restorations": [],
    }


def _load_metadata(path: Path) -> dict[str, Any] | None:
    """Metadados ausentes/corrompidos retornam None (nunca presumem origem)."""
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_metadata(path: Path, metadata: dict[str, Any]) -> None:
    payload = json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8")
    _atomic_write(path, payload)


def _base_file(client_root: Any, sha256: str, storage_base: Any = None) -> Path:
    return bases_dir(client_root, storage_base) / f"{sha256}.bin"


def _read_base(client_root: Any, base_sha256: str, storage_base: Any = None) -> bytes:
    if not base_sha256:
        raise StonesBlockedError("a base vinculada não pôde ser identificada")
    data = engine.read_binary_file(_base_file(client_root, base_sha256, storage_base))
    if engine.sha256_bytes(data) != base_sha256:
        raise engine.ValidationError("backup da base corrompido ou divergente; não é seguro continuar")
    return data
@dataclass(frozen=True)
class StonesRecognition:
    client_root: Path | None
    target_path: Path | None
    kind: str
    file_sha256: str | None
    file_size: int | None
    compatible: bool
    compatible_records: int
    base_sha256: str | None
    applied_colors: tuple[int, int, int] | None
    message: str
    record_count: int | None = None
    base_compatible_records: int | None = None
    base_error: str | None = None

    @property
    def base_valid(self) -> bool:
        return self.base_compatible_records is not None and self.base_error is None


def classify_from_facts(
    client_root: Any,
    target_path: Any,
    digest: str,
    size: int,
    compatible: bool,
    compatible_records: int,
    storage_base: Any = None,
) -> StonesRecognition:
    """Classifica um arquivo já analisado contra bases/saídas/intenções registradas."""
    root, target = resolve_target(client_root)
    if root is None or target is None:
        return StonesRecognition(root, target, KIND_NOT_CONFIGURED, digest, size,
                                 compatible, compatible_records, None, None,
                                 "Cliente do Aika não configurado.")
    metadata = _load_metadata(metadata_path(client_root, storage_base, create=False))
    base_hashes: set[str] = set()
    outputs: dict[str, dict[str, Any]] = {}
    if metadata:
        base_hashes = {
            b.get("sha256") for b in metadata.get("bases", [])
            if isinstance(b, dict) and b.get("sha256")
        }
        for app in metadata.get("applications", []):
            if isinstance(app, dict) and app.get("sha256"):
                outputs[app["sha256"]] = app
        for txn in metadata.get("pending", []):
            if isinstance(txn, dict) and txn.get("state") == "pending" and txn.get("expected_sha256"):
                outputs.setdefault(txn["expected_sha256"], txn)
    if digest in base_hashes:
        return StonesRecognition(root, target, KIND_BASE, digest, size, compatible,
                                 compatible_records, digest, None,
                                 "Arquivo igual à base preservada (sem personalização correspondente).")
    if digest in outputs:
        app = outputs[digest]
        colors = (app.get("attack"), app.get("defense"), app.get("common"))
        return StonesRecognition(root, target, KIND_PERSONALIZED, digest, size, compatible,
                                 compatible_records, app.get("base_sha256"), colors,
                                 "Personalização reconhecida; trocar cores gera a partir da base preservada.")
    if compatible:
        return StonesRecognition(root, target, KIND_EXTERNAL_COMPATIBLE, digest, size, True,
                                 compatible_records, None, None,
                                 "Conteúdo novo/alterado sem personalização registrada. "
                                 "Clique em Aplicar no Aika para preservar e personalizar.")
    return StonesRecognition(root, target, KIND_EXTERNAL_INCOMPATIBLE, digest, size, False,
                             compatible_records, None, None,
                             "Arquivo alterado externamente e incompatível com o perfil; aplicação bloqueada.")


def _validate_base(client_root: Any, base_sha256: str, profile: engine.ColorProfile, storage_base: Any):
    """Valida a base preservada: existência, integridade e compatibilidade com o engine."""
    if not base_sha256:
        return None, "vínculo com a base ausente"
    bfile = _base_file(client_root, base_sha256, storage_base)
    if not bfile.is_file():
        return None, "backup da base ausente"
    try:
        data = engine.read_binary_file(bfile)
    except engine.ValidationError as exc:
        return None, f"backup da base ilegível: {exc}"
    if engine.sha256_bytes(data) != base_sha256:
        return None, "backup da base corrompido (hash divergente)"
    try:
        analysis = engine.analyze_file(bfile, profile)
    except engine.ValidationError as exc:
        return None, f"base não validada pelo engine: {exc}"
    return analysis.compatible_records, None


def recognize_state(client_root: Any, profile_path: Any, storage_base: Any = None) -> StonesRecognition:
    root, target = resolve_target(client_root)
    if root is None:
        return StonesRecognition(None, None, KIND_NOT_CONFIGURED, None, None, False, 0,
                                 None, None, "Cliente do Aika não configurado.")
    if not target.is_file():
        return StonesRecognition(root, target, KIND_MISSING, None, None, False, 0,
                                 None, None, "ItemList6.bin não encontrado na raiz do cliente configurado.")
    try:
        data = read_stable(target)
    except engine.ValidationError as exc:
        return StonesRecognition(root, target, KIND_EXTERNAL_INCOMPATIBLE, None, None,
                                 False, 0, None, None, str(exc))
    digest = engine.sha256_bytes(data)
    try:
        profile = engine.load_profile(Path(profile_path))
        analysis = engine.analyze_file(target, profile)
        compatible = analysis.compatible
        compatible_records = analysis.compatible_records
        record_count = analysis.structure.record_count
    except engine.ValidationError as exc:
        return StonesRecognition(root, target, KIND_EXTERNAL_INCOMPATIBLE, digest, len(data),
                                 False, 0, None, None, f"ItemList6.bin não pôde ser validado: {exc}")
    rec = classify_from_facts(root, target, digest, len(data), compatible,
                              compatible_records, storage_base)
    base_records = None
    base_error = None
    if rec.kind == KIND_PERSONALIZED:
        base_records, base_error = _validate_base(root, rec.base_sha256, profile, storage_base)
    message = rec.message
    if rec.kind == KIND_PERSONALIZED:
        if base_error is not None:
            message = f"Personalização reconhecida, mas a base preservada é inválida: {base_error}."
        else:
            message = (
                "Personalização reconhecida; base verificada "
                f"({base_records}/438 registros). Trocar cores gera a partir da base preservada."
            )
    return StonesRecognition(
        rec.client_root, rec.target_path, rec.kind, rec.file_sha256, rec.file_size,
        rec.compatible, rec.compatible_records, rec.base_sha256, rec.applied_colors,
        message, record_count, base_records, base_error,
    )
def capture_base(
    client_root: Any,
    profile_path: Any,
    storage_base: Any = None,
    *,
    data: bytes | None = None,
) -> dict[str, Any]:
    """Preserva (deduplicada por hash) uma cópia estável da entrada como base."""
    with _lock:
        root, target = resolve_target(client_root)
        if root is None:
            raise engine.ValidationError("cliente não configurado")
        if not target.is_file():
            raise engine.ValidationError("ItemList6.bin não encontrado na raiz do cliente")
        content = data if data is not None else read_stable(target)
        digest = engine.sha256_bytes(content)
        md_path = metadata_path(client_root, storage_base)
        metadata = _load_metadata(md_path) or _empty_metadata(target, _profile_hash(profile_path))
        record = next(
            (b for b in metadata.get("bases", [])
             if isinstance(b, dict) and b.get("sha256") == digest),
            None,
        )
        if record is None:
            bfile = _base_file(client_root, digest, storage_base)
            if not bfile.exists():
                _atomic_write(bfile, content)
            if sha256_file(bfile) != digest:
                raise engine.ValidationError("falha ao validar a base preservada")
            record = {
                "sha256": digest,
                "size": len(content),
                "backup_path": f"{BASES_SUBDIR}/{digest}.bin",
                "captured_at": _now_iso(),
                "kind": "preserved",
            }
            metadata.setdefault("bases", []).append(record)
            _write_metadata(md_path, metadata)
        return record


def ensure_base_preserved(client_root: Any, profile_path: Any, storage_base: Any = None):
    """Preserva a base de uma entrada compatível (idempotente); nunca aplica cores."""
    root, target = resolve_target(client_root)
    if root is None or not target.is_file():
        return None
    with _lock:
        profile = engine.load_profile(Path(profile_path))
        data = read_stable(target)
        digest = engine.sha256_bytes(data)
        md_path = metadata_path(client_root, storage_base)
        metadata = _load_metadata(md_path)
        if metadata:
            base_hashes = {b.get("sha256") for b in metadata.get("bases", []) if isinstance(b, dict)}
            if digest in base_hashes:
                return None
            outputs = {a.get("sha256") for a in metadata.get("applications", []) if isinstance(a, dict)}
            if digest in outputs:
                return None
        mismatches = engine.profile_compatibility_from_reference(data, profile)
        if mismatches:
            return None
        return capture_base(client_root, profile_path, storage_base, data=data)


def _reconcile_pending(client_root: Any, storage_base: Any = None) -> list[str]:
    """Reconcilia transações interrompidas; nunca sobrescreve conteúdo externo."""
    root, target = resolve_target(client_root)
    if root is None or not target.is_file():
        return []
    md_path = metadata_path(client_root, storage_base)
    metadata = _load_metadata(md_path)
    if not metadata:
        return []
    pending = [t for t in metadata.get("pending", [])
               if isinstance(t, dict) and t.get("state") == "pending"]
    if not pending:
        return []
    try:
        current = read_stable(target)
    except engine.ValidationError:
        return []
    current_sha = engine.sha256_bytes(current)
    resolved: list[str] = []
    for txn in pending:
        expected = txn.get("expected_sha256")
        base_sha = txn.get("base_sha256")
        if not expected or not base_sha:
            continue
        if current_sha == expected:
            txn["state"] = "complete"
            txn["completed_at"] = _now_iso()
            metadata.setdefault("applications", []).append({
                "sha256": expected,
                "base_sha256": base_sha,
                "attack": txn.get("attack"),
                "defense": txn.get("defense"),
                "common": txn.get("common"),
                "applied_at": _now_iso(),
                "state": "complete",
            })
            resolved.append("finalized")
        elif current_sha == base_sha:
            txn["state"] = "rolled_back"
            resolved.append("cleared")
        else:
            txn["state"] = "blocked_external"
            txn["resolved_at"] = _now_iso()
            metadata.setdefault("blocked", []).append(txn)
            resolved.append("blocked")
    metadata["pending"] = []
    _write_metadata(md_path, metadata)
    return resolved


def reconcile_transaction(client_root: Any, storage_base: Any = None) -> list[str]:
    """Versão pública (idempotente) da reconciliação de transações interrompidas."""
    with _lock:
        return _reconcile_pending(client_root, storage_base)
@dataclass(frozen=True)
class ApplyOutcome:
    applied: bool
    output_sha256: str
    base_sha256: str
    target_path: Path
    message: str


def _select_base_sha256(
    data: bytes, digest: str, metadata: dict[str, Any], profile: engine.ColorProfile
) -> str:
    """Escolhe a base correta; nunca gera a partir de saída personalizada."""
    base_hashes = {
        b.get("sha256") for b in metadata.get("bases", [])
        if isinstance(b, dict) and b.get("sha256")
    }
    outputs: dict[str, dict[str, Any]] = {}
    for app in metadata.get("applications", []):
        if isinstance(app, dict) and app.get("sha256"):
            outputs[app["sha256"]] = app
    for txn in metadata.get("pending", []):
        if isinstance(txn, dict) and txn.get("state") == "pending" and txn.get("expected_sha256"):
            outputs.setdefault(txn["expected_sha256"], txn)
    if digest in base_hashes:
        return digest
    if digest in outputs:
        base_sha = outputs[digest].get("base_sha256")
        if base_sha:
            return base_sha
        raise StonesBlockedError("o vínculo com a base desta personalização está ausente.")
    mismatches = engine.profile_compatibility_from_reference(data, profile)
    if mismatches:
        raise engine.IncompatibleUpdateError(
            "arquivo alterado externamente e incompatível com o perfil; aplicação bloqueada"
        )
    return digest


def _finalize_apply(
    metadata: dict[str, Any], txn: dict[str, Any], base_sha: str,
    attack: int, defense: int, common: int, output_sha: str,
) -> None:
    metadata["pending"] = [
        t for t in metadata.get("pending", [])
        if t.get("transaction_id") != txn["transaction_id"]
    ]
    metadata.setdefault("applications", []).append({
        "sha256": output_sha,
        "base_sha256": base_sha,
        "attack": int(attack),
        "defense": int(defense),
        "common": int(common),
        "applied_at": _now_iso(),
        "state": "complete",
    })


def apply_colors(
    client_root: Any,
    profile_path: Any,
    attack_code: int,
    defense_code: int,
    common_code: int,
    storage_base: Any = None,
) -> ApplyOutcome:
    """Aplica as cores no cliente, com backup verificado antes da escrita."""
    _require_processes_closed(client_root)
    with _lock:
        _reconcile_pending(client_root, storage_base)
        root, target = resolve_target(client_root)
        if root is None:
            raise engine.ValidationError("cliente não configurado")
        if not target.is_file():
            raise engine.ValidationError("ItemList6.bin não encontrado na raiz do cliente")
        profile = engine.load_profile(Path(profile_path))
        data = read_stable(target)
        digest = engine.sha256_bytes(data)
        md_path = metadata_path(client_root, storage_base)
        metadata = _load_metadata(md_path) or _empty_metadata(target, _profile_hash(profile_path))

        base_sha = _select_base_sha256(data, digest, metadata, profile)

        if base_sha == digest:
            capture_base(client_root, profile_path, storage_base, data=data)
        base_bytes = _read_base(client_root, base_sha, storage_base)

        result = engine.apply_colors(
            base_bytes, profile,
            attack_code=attack_code, defense_code=defense_code, common_code=common_code,
        )
        engine.validate_output(
            base_bytes, result.data, profile,
            attack_code=attack_code, defense_code=defense_code, common_code=common_code,
        )
        output_sha = result.sha256

        if output_sha == digest:
            return ApplyOutcome(
                False, output_sha, base_sha, target,
                "As cores já estão aplicadas; nenhuma escrita foi necessária.",
            )

        current = read_stable(target)
        if engine.sha256_bytes(current) != digest:
            raise engine.InputChangedError("o arquivo mudou durante a operação; analise novamente")

        txn = {
            "transaction_id": _new_id(),
            "base_sha256": base_sha,
            "attack": int(attack_code),
            "defense": int(defense_code),
            "common": int(common_code),
            "expected_sha256": output_sha,
            "target": str(target),
            "started_at": _now_iso(),
            "state": "pending",
        }
        metadata = _load_metadata(md_path) or _empty_metadata(target, _profile_hash(profile_path))
        metadata.setdefault("pending", []).append(txn)
        _write_metadata(md_path, metadata)

        _atomic_replace(target, result.data)

        applied = read_stable(target)
        if engine.sha256_bytes(applied) != output_sha:
            raise engine.PublicationError("falha na verificação do arquivo aplicado; tente novamente")

        _finalize_apply(metadata, txn, base_sha, attack_code, defense_code, common_code, output_sha)
        try:
            _write_metadata(md_path, metadata)
        except OSError:
            return ApplyOutcome(
                True, output_sha, base_sha, target,
                "Cores aplicadas, mas o registro ficou pendente e será reconciliado "
                "na próxima execução.",
            )
        return ApplyOutcome(True, output_sha, base_sha, target, "Cores aplicadas no cliente.")


def _path_is_within(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve(strict=False).relative_to(base.resolve(strict=False))
        return True
    except ValueError:
        return False


def _unique_output_path(output_directory: Path) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = output_directory / f"ItemList6_Pedras_{stamp}.bin"
    if not base.exists():
        return base
    seq = 1
    while True:
        candidate = output_directory / f"ItemList6_Pedras_{stamp}_{seq:02d}.bin"
        if not candidate.exists():
            return candidate
        seq += 1


@dataclass(frozen=True)
class PreparedCopy:
    client_root: Path
    target_path: Path
    observed_target_sha256: str
    base_sha256: str
    profile_sha256: str
    attack_code: int
    defense_code: int
    common_code: int
    copy_path: Path
    copy_sha256: str

    @property
    def path(self) -> Path:
        return self.copy_path


def prepare_colors(
    client_root: Any,
    profile_path: Any,
    output_directory: Any,
    attack_code: int,
    defense_code: int,
    common_code: int,
    storage_base: Any = None,
) -> PreparedCopy:
    """Gera uma cópia externa validada a partir da base e registra a preparação."""
    root, target = resolve_target(client_root)
    if root is None:
        raise engine.ValidationError("cliente não configurado")
    if not target.is_file():
        raise engine.ValidationError("ItemList6.bin não encontrado na raiz do cliente")
    profile = engine.load_profile(Path(profile_path))
    data = read_stable(target)
    digest = engine.sha256_bytes(data)
    md_path = metadata_path(client_root, storage_base)
    metadata = _load_metadata(md_path) or _empty_metadata(target, _profile_hash(profile_path))
    base_sha = _select_base_sha256(data, digest, metadata, profile)
    if base_sha == digest:
        capture_base(client_root, profile_path, storage_base, data=data)
    base_file = _base_file(client_root, base_sha, storage_base)
    output_directory = Path(output_directory).resolve(strict=False)
    if _path_is_within(root, output_directory):
        raise engine.UnsafeOutputPathError(
            "a pasta de saída não pode ficar dentro do cliente do jogo"
        )
    output_path = _unique_output_path(output_directory)
    published = engine.generate_file(
        base_file,
        output_path,
        profile,
        expected_input_sha256=base_sha,
        attack_code=attack_code,
        defense_code=defense_code,
        common_code=common_code,
    )
    return PreparedCopy(
        root,
        target,
        digest,
        base_sha,
        _profile_hash(profile_path),
        int(attack_code),
        int(defense_code),
        int(common_code),
        published.path,
        published.result.sha256,
    )


def apply_prepared(
    prepared: PreparedCopy, profile_path: Any, storage_base: Any = None
) -> ApplyOutcome:
    """Aplica exatamente os bytes da cópia preparada, revalidando todas as condições."""
    _require_processes_closed(prepared.client_root)
    with _lock:
        _reconcile_pending(prepared.client_root, storage_base)
        root, target = resolve_target(prepared.client_root)
        if root is None:
            raise engine.ValidationError("cliente não configurado")
        if not target.is_file():
            raise engine.ValidationError("ItemList6.bin não encontrado na raiz do cliente")
        if root != prepared.client_root or target != prepared.target_path:
            raise StonesBlockedError("o cliente ou alvo mudou; gere a cópia novamente")

        current = read_stable(target)
        if engine.sha256_bytes(current) != prepared.observed_target_sha256:
            raise engine.InputChangedError(
                "o arquivo mudou desde a preparação; gere a cópia novamente"
            )
        if not prepared.copy_path.is_file():
            raise StonesBlockedError("a cópia preparada foi removida; gere a cópia novamente")
        if sha256_file(prepared.copy_path) != prepared.copy_sha256:
            raise StonesBlockedError("a cópia preparada foi alterada; gere a cópia novamente")
        if _profile_hash(profile_path) != prepared.profile_sha256:
            raise StonesBlockedError("o perfil mudou; gere a cópia novamente")

        profile = engine.load_profile(Path(profile_path))
        base_bytes = _read_base(prepared.client_root, prepared.base_sha256, storage_base)
        expected = engine.apply_colors(
            base_bytes,
            profile,
            attack_code=prepared.attack_code,
            defense_code=prepared.defense_code,
            common_code=prepared.common_code,
        )
        if expected.sha256 != prepared.copy_sha256:
            raise StonesBlockedError(
                "a cópia não corresponde à base e às cores selecionadas; gere a cópia novamente"
            )

        if prepared.copy_sha256 == prepared.observed_target_sha256:
            return ApplyOutcome(
                False, prepared.copy_sha256, prepared.base_sha256, target,
                "As cores já estão aplicadas; nenhuma escrita foi necessária.",
            )

        current2 = read_stable(target)
        if engine.sha256_bytes(current2) != prepared.observed_target_sha256:
            raise engine.InputChangedError(
                "o arquivo mudou durante a operação; gere a cópia novamente"
            )
        copy_bytes = engine.read_binary_file(prepared.copy_path)
        if engine.sha256_bytes(copy_bytes) != prepared.copy_sha256:
            raise StonesBlockedError("a cópia preparada foi alterada; gere a cópia novamente")

        md_path = metadata_path(prepared.client_root, storage_base)
        metadata = _load_metadata(md_path) or _empty_metadata(target, _profile_hash(profile_path))
        txn = {
            "transaction_id": _new_id(),
            "base_sha256": prepared.base_sha256,
            "attack": int(prepared.attack_code),
            "defense": int(prepared.defense_code),
            "common": int(prepared.common_code),
            "expected_sha256": prepared.copy_sha256,
            "target": str(target),
            "started_at": _now_iso(),
            "state": "pending",
        }
        metadata.setdefault("pending", []).append(txn)
        _write_metadata(md_path, metadata)

        _atomic_replace(target, copy_bytes)

        applied = read_stable(target)
        if engine.sha256_bytes(applied) != prepared.copy_sha256:
            raise engine.PublicationError("falha na verificação do arquivo aplicado; tente novamente")

        _finalize_apply(
            metadata, txn, prepared.base_sha256,
            prepared.attack_code, prepared.defense_code, prepared.common_code,
            prepared.copy_sha256,
        )
        try:
            _write_metadata(md_path, metadata)
        except OSError:
            return ApplyOutcome(
                True, prepared.copy_sha256, prepared.base_sha256, target,
                "Cores aplicadas, mas o registro ficou pendente e será reconciliado "
                "na próxima execução.",
            )
        return ApplyOutcome(
            True, prepared.copy_sha256, prepared.base_sha256, target,
            "Cores aplicadas no cliente.",
        )
@dataclass(frozen=True)
class RestoreOutcome:
    restored: bool
    base_sha256: str
    target_path: Path
    message: str


def restore_colors(client_root: Any, profile_path: Any, storage_base: Any = None) -> RestoreOutcome:
    """Restaura a base preservada vinculada ao conteúdo personalizado atual."""
    _require_processes_closed(client_root)
    with _lock:
        _reconcile_pending(client_root, storage_base)
        root, target = resolve_target(client_root)
        if root is None:
            raise engine.ValidationError("cliente não configurado")
        if not target.is_file():
            raise engine.ValidationError("ItemList6.bin não encontrado na raiz do cliente")
        data = read_stable(target)
        digest = engine.sha256_bytes(data)
        md_path = metadata_path(client_root, storage_base)
        metadata = _load_metadata(md_path)
        if not metadata:
            raise StonesBlockedError("Nenhum backup de Pedras registrado para este cliente.")

        base_hashes = {
            b.get("sha256") for b in metadata.get("bases", [])
            if isinstance(b, dict) and b.get("sha256")
        }
        if digest in base_hashes:
            return RestoreOutcome(False, digest, target,
                                  "O arquivo já está igual à base preservada (já restaurado).")

        outputs: dict[str, dict[str, Any]] = {}
        for app in metadata.get("applications", []):
            if isinstance(app, dict) and app.get("sha256"):
                outputs[app["sha256"]] = app
        for txn in metadata.get("pending", []):
            if isinstance(txn, dict) and txn.get("state") == "pending" and txn.get("expected_sha256"):
                outputs.setdefault(txn["expected_sha256"], txn)

        base_sha = outputs.get(digest, {}).get("base_sha256")
        if not base_sha:
            raise StonesBlockedError(
                "O arquivo mudou externamente e não há vínculo seguro com uma base; "
                "a restauração obsoleta foi bloqueada."
            )
        base_bytes = _read_base(client_root, base_sha, storage_base)

        current = read_stable(target)
        if engine.sha256_bytes(current) != digest:
            raise engine.InputChangedError("o arquivo mudou durante a operação; analise novamente")

        _atomic_replace(target, base_bytes)

        restored = read_stable(target)
        if engine.sha256_bytes(restored) != base_sha:
            raise engine.PublicationError("falha na verificação do arquivo restaurado; tente novamente")

        metadata = _load_metadata(md_path) or {}
        for app in metadata.get("applications", []):
            if isinstance(app, dict) and app.get("sha256") == digest:
                app["restored_at"] = _now_iso()
                break
        metadata.setdefault("restorations", []).append({
            "base_sha256": base_sha,
            "from_sha256": digest,
            "restored_at": _now_iso(),
        })
        try:
            _write_metadata(md_path, metadata)
        except OSError:
            pass
        return RestoreOutcome(True, base_sha, target,
                              "Cores restauradas para a base preservada.")


def list_stones_backups(
    client_root: Any, profile_path: Any = None, storage_base: Any = None
) -> dict[str, Any]:
    """Resumo persistente para a aba Restauração (não força restauração antiga)."""
    root, target = resolve_target(client_root)
    metadata = None
    if root is not None:
        metadata = _load_metadata(metadata_path(client_root, storage_base, create=False))
    recognition = None
    if profile_path is not None and root is not None:
        try:
            recognition = recognize_state(client_root, profile_path, storage_base)
        except Exception:
            recognition = None
    return {
        "client_root": str(root) if root else None,
        "target": str(target) if target else None,
        "bases": list((metadata or {}).get("bases", [])),
        "applications": list((metadata or {}).get("applications", [])),
        "recognition": recognition,
    }





