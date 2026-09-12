# -*- coding: utf-8 -*-
"""dgvoodoo_config_engine — ESTÁGIO 1 (SOMENTE LEITURA).

Engine documental para ``dgVoodoo.conf`` (dgVoodoo2 2.87.4 adotado/validado
pelo projeto). Lê bytes; preserva estrutura (Document Model/Lossless);
constrói índice semântico separado (Section, Key)->ocorrências; detecta
chave global/seções/chaves/valores/vazios/comentários/linhas vazias/
desconhecidas (catálogo)/duplicatas/BOM/terminadores/newline final; calcula
metadados; round-trip LOSSLESS byte a byte; diagnóstico e diff não
destrutivos; origem documental da chave.

PROIBIDO NESTA FASE: gravar dgVoodoo.conf; serialização ativa (UTF-8 sem BOM
+ CRLF é modo futuro); normalizar/corrigir valores; resolver overlay/perfil;
escrever em disco por padrão.
"""
from __future__ import annotations

import difflib
import enum
import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

UTF8_BOM = b"\xef\xbb\xbf"


class LineKind(enum.Enum):
    SECTION = "section"      # [Seção]
    KEYVALUE = "keyvalue"    # chave = valor
    COMMENT = "comment"      # linha iniciada por ';'
    EMPTY = "empty"          # linha vazia
    UNKNOWN = "unknown"      # linha não classificável


@dataclass
class LineNode:
    """Nó do Document Model: uma linha física preservada."""

    kind: LineKind
    raw: str
    eol: str
    line_index: int
    section: Optional[str] = None
    key: Optional[str] = None
    value: Optional[str] = None
    value_empty: bool = False
    value_clean: Optional[str] = None
    inline_comment: Optional[str] = None
    is_global: bool = False
    unknown: bool = False

    @property
    def identity(self) -> Tuple[Optional[str], Optional[str]]:
        return (self.section, self.key)

    @property
    def location(self) -> str:
        if self.kind is LineKind.KEYVALUE:
            if self.is_global:
                return f"[GLOBAL].{self.key}"
            return f"[{self.section}].{self.key}"
        if self.kind is LineKind.SECTION:
            return f"[{self.section}]"
        return f"{self.kind.value}@{self.line_index}"


@dataclass
class Occurrence:
    """Ocorrência de uma chave (índice não destrói duplicatas)."""

    section: Optional[str]
    key: str
    value: Optional[str]
    value_empty: bool
    line_index: int
    is_global: bool


@dataclass
class DocumentMetadata:
    sha256: str
    size: int
    first_bytes: str
    line_count: int
    section_count: int
    active_key_count: int
    bom: bool
    encoding: str
    newline_style: str
    has_final_newline: bool
    has_duplicates: bool


@dataclass
class ReadDiagnostic:
    sections: List[str]
    keys: List[Tuple[Optional[str], str]]
    occurrence_counts: Dict[Tuple[Optional[str], str], int]
    duplicates: Dict[Tuple[Optional[str], str], List[int]]
    unknown_sections: List[str]
    unknown_keys: List[Tuple[Optional[str], str, int]]
    warnings: List[str]


@dataclass
class DiffEntry:
    category: str
    description: str
    detail: str = ""


@dataclass
class DiffReport:
    same: bool
    categories: List[str]
    entries: List[DiffEntry] = field(default_factory=list)


Catalog = Dict[Optional[str], Set[str]]


def _split_physical_lines(text: str) -> List[Tuple[str, str]]:
    """Divide preservando conteúdo e terminador; sem linha fantasma final."""
    linhas: List[Tuple[str, str]] = []
    i = 0
    n = len(text)
    while i < n:
        j = i
        while j < n and text[j] not in "\r\n":
            j += 1
        content = text[i:j]
        term = ""
        if j < n:
            if text[j] == "\r":
                if j + 1 < n and text[j + 1] == "\n":
                    term = "\r\n"
                    j += 2
                else:
                    term = "\r"
                    j += 1
            else:  # '\n'
                term = "\n"
                j += 1
        linhas.append((content, term))
        i = j
    return linhas


_INLINE_RE = re.compile(r"\s;(?P<rest>.*)$")


def _decodificar(data: bytes) -> Tuple[bool, str]:
    """UTF-8 tolerante a BOM. Falha de decodificação é explícita."""
    bom = data.startswith(UTF8_BOM)
    payload = data[3:] if bom else data
    texto = payload.decode("utf-8")  # UnicodeDecodeError propaga
    return bom, texto


def _classificar_linha(content: str):
    """Classifica e decompõe uma linha (sem terminador). Retorna
    (kind, seção/chave, valor, valor_clean, vazio, inline_comment, _)."""
    stripped = content.strip()
    if stripped == "":
        return (LineKind.EMPTY, None, None, None, False, None, None)
    if stripped.startswith(";"):
        return (LineKind.COMMENT, None, None, None, False, None, None)
    if stripped.startswith("[") and stripped.endswith("]"):
        return (LineKind.SECTION, stripped[1:-1].strip(), None, None, False, None, None)
    if "=" in content:
        idx = content.index("=")
        chave = content[:idx].strip()
        if not chave:
            return (LineKind.UNKNOWN, None, None, None, False, None, None)
        direito = content[idx + 1:]
        valor = direito.strip()
        vazio = valor == ""
        inline = None
        limpo = valor
        m = _INLINE_RE.search(direito)
        if m is not None:
            inline = m.group("rest").strip()
            limpo = direito[:m.start()].rstrip()
        return (LineKind.KEYVALUE, chave, valor, limpo, vazio, inline, None)
    return (LineKind.UNKNOWN, None, None, None, False, None, None)


class DgVoodooDocument:
    """Document Model lossless de um dgVoodoo.conf (somente leitura)."""

    def __init__(self, bom: bool, lines: List[LineNode],
                 source_name: Optional[str] = None,
                 catalog: Optional[Catalog] = None) -> None:
        self.bom = bom
        self.encoding = "utf-8"
        self.lines = lines
        self.source_name = source_name
        self._catalog = catalog
        self._text: Optional[str] = None
        self._occurrences: Optional[List[Occurrence]] = None
        self._secoes: Optional[List[str]] = None

    # --- conteúdo ---------------------------------------------------------
    @property
    def content(self) -> str:
        """Texto decodificado (sem o BOM)."""
        if self._text is None:
            self._text = "".join(n.raw + n.eol for n in self.lines)
        return self._text

    def serialize_lossless(self) -> bytes:
        """Modo A (Lossless Round-Trip): reproduz os bytes de entrada."""
        dados = self.content.encode("utf-8")
        return (UTF8_BOM + dados) if self.bom else dados

    def original_bytes(self) -> bytes:
        return self.serialize_lossless()

    def sha256(self) -> str:
        return hashlib.sha256(self.serialize_lossless()).hexdigest()

    # --- índice semântico -------------------------------------------------
    def occurrences(self) -> List[Occurrence]:
        if self._occurrences is None:
            occ = []
            for n in self.lines:
                if n.kind is LineKind.KEYVALUE and n.key is not None:
                    occ.append(Occurrence(
                        section=n.section, key=n.key, value=n.value,
                        value_empty=n.value_empty, line_index=n.line_index,
                        is_global=n.is_global,
                    ))
            self._occurrences = occ
        return self._occurrences

    def get(self, section: Optional[str], key: str) -> List[Occurrence]:
        """Todas as ocorrências de (section, key), na ordem do arquivo."""
        return [o for o in self.occurrences()
                if o.section == section and o.key == key]

    def get_node(self, section: Optional[str], key: str) -> List[LineNode]:
        return [n for n in self.lines if n.kind is LineKind.KEYVALUE
                and n.section == section and n.key == key]

    def count(self, section: Optional[str], key: str) -> int:
        return len(self.get(section, key))

    def sections(self) -> List[str]:
        """Seções na ordem de primeira aparição."""
        if self._secoes is None:
            seen: List[str] = []
            for n in self.lines:
                if n.kind is LineKind.SECTION and n.section is not None \
                        and n.section not in seen:
                    seen.append(n.section)
            self._secoes = seen
        return list(self._secoes)

    def keys(self) -> List[Tuple[Optional[str], str]]:
        return [(o.section, o.key) for o in self.occurrences()]

    def duplicates(self) -> Dict[Tuple[Optional[str], str], List[int]]:
        """(section,key) -> linhas físicas quando há mais de uma ocorrência."""
        d: Dict[Tuple[Optional[str], str], List[int]] = {}
        for n in self.lines:
            if n.kind is LineKind.KEYVALUE and n.key is not None:
                d.setdefault((n.section, n.key), []).append(n.line_index)
        return {k: v for k, v in d.items() if len(v) > 1}


    # --- desconhecidas (catálogo opcional) --------------------------------
    def unknown_sections(self) -> List[str]:
        if self._catalog is None:
            return []
        return [s for s in self.sections() if s not in self._catalog]

    def unknown_keys(self) -> List[Tuple[Optional[str], str, int]]:
        if self._catalog is None:
            return []
        saida = []
        for n in self.lines:
            if n.kind is LineKind.KEYVALUE and n.key is not None:
                if self._catalog.get(n.section) is None or n.key not in self._catalog[n.section]:
                    saida.append((n.section, n.key, n.line_index))
        return saida

    def mark_unknown(self) -> None:
        """Marca nós unknown segundo o catálogo (não muta valores/linhas)."""
        if self._catalog is None:
            return
        for n in self.lines:
            if n.kind is LineKind.KEYVALUE and n.key is not None:
                if self._catalog.get(n.section) is None or n.key not in self._catalog[n.section]:
                    n.unknown = True

    # --- diagnóstico --------------------------------------------------------
    def diagnostic(self) -> ReadDiagnostic:
        counts: Dict[Tuple[Optional[str], str], int] = {}
        for o in self.occurrences():
            counts[(o.section, o.key)] = counts.get((o.section, o.key), 0) + 1
        dups = self.duplicates()
        warnings: List[str] = []
        if self.bom:
            warnings.append("BOM UTF-8 detectado (preservado no modo lossless).")
        for (sec, key), linhas in dups.items():
            nome = f"[GLOBAL].{key}" if sec is None else f"[{sec}].{key}"
            warnings.append(f"Duplicata: {nome} em {len(linhas)} ocorrências "
                            f"(linhas {linhas}).")
        des = self.unknown_sections()
        for s in des:
            warnings.append(f"Seção desconhecida do catálogo: [{s}].")
        for sec, key, ln in self.unknown_keys():
            nome = f"[GLOBAL].{key}" if sec is None else f"[{sec}].{key}"
            warnings.append(f"Chave desconhecida do catálogo: {nome} (linha {ln}).")
        return ReadDiagnostic(
            sections=self.sections(),
            keys=self.keys(),
            occurrence_counts=counts,
            duplicates=dups,
            unknown_sections=des,
            unknown_keys=self.unknown_keys(),
            warnings=warnings,
        )

    def metadata(self) -> DocumentMetadata:
        dados = self.serialize_lossless()
        return DocumentMetadata(
            sha256=hashlib.sha256(dados).hexdigest(),
            size=len(dados),
            first_bytes=dados[:8].hex(" ").upper(),
            line_count=len(self.lines),
            section_count=len(self.sections()),
            active_key_count=sum(1 for n in self.lines if n.kind is LineKind.KEYVALUE),
            bom=self.bom,
            encoding=self.encoding,
            newline_style=_newline_style(self.lines),
            has_final_newline=_tem_newline_final(self.content),
            has_duplicates=bool(self.duplicates()),
        )

    def origem_da_chave(self, section: Optional[str], key: str) -> List[LineNode]:
        """Origem documental: nós da linha no documento lido (ordem)."""
        return self.get_node(section, key)


def _newline_style(lines: List[LineNode]) -> str:
    crlf = sum(1 for n in lines if n.eol == "\r\n")
    lf = sum(1 for n in lines if n.eol == "\n")
    cr = sum(1 for n in lines if n.eol == "\r")
    ativos = [k for k, c in (("crlf", crlf), ("lf", lf), ("cr", cr)) if c > 0]
    return "mixed" if len(ativos) > 1 else (ativos[0] if ativos else "none")


def _tem_newline_final(texto: str) -> bool:
    return texto != "" and (texto.endswith("\n") or texto.endswith("\r"))


def _parse_payload(bom: bool, texto: str, source_name: Optional[str],
                   catalog: Optional[Catalog]) -> DgVoodooDocument:
    linhas_fisicas = _split_physical_lines(texto)
    nodes: List[LineNode] = []
    secao_atual: Optional[str] = None
    for idx, (content, eol) in enumerate(linhas_fisicas):
        kind, k_or_s, valor, limpo, vazio, inline, _ = _classificar_linha(content)
        no = LineNode(kind=kind, raw=content, eol=eol, line_index=idx,
                      value=valor, value_empty=vazio, value_clean=limpo,
                      inline_comment=inline)
        if kind is LineKind.SECTION:
            secao_atual = k_or_s
            no.section = k_or_s
        elif kind is LineKind.KEYVALUE:
            no.section = secao_atual
            no.key = k_or_s
            no.is_global = secao_atual is None
        else:
            no.section = secao_atual
        nodes.append(no)
    doc = DgVoodooDocument(bom=bom, lines=nodes, source_name=source_name,
                           catalog=catalog)
    doc.mark_unknown()
    return doc


def parse_bytes(data: bytes, *, source_name: Optional[str] = None,
                catalog: Optional[Catalog] = None) -> DgVoodooDocument:
    """Lê bytes UTF-8 (BOM tolerado) e devolve o Document Model."""
    bom, texto = _decodificar(data)
    return _parse_payload(bom, texto, source_name, catalog)


def read_file(path: str, *, catalog: Optional[Catalog] = None) -> DgVoodooDocument:
    """Somente leitura: abre em rb e faz parse. Nunca grava."""
    with open(path, "rb") as f:
        data = f.read()
    return parse_bytes(data, source_name=path, catalog=catalog)


# ---------------------------------------------------------------------------
# Diff não destrutivo
# ---------------------------------------------------------------------------

def _como_documento(obj) -> DgVoodooDocument:
    if isinstance(obj, DgVoodooDocument):
        return obj
    if isinstance(obj, (bytes, bytearray)):
        return parse_bytes(bytes(obj))
    raise TypeError("diff espera bytes ou DgVoodooDocument")


def _item_semantico(n: LineNode) -> tuple:
    if n.kind is LineKind.KEYVALUE:
        return (n.kind.value, n.section, n.key, n.value, n.is_global)
    if n.kind is LineKind.SECTION:
        return (n.kind.value, n.section)
    if n.kind is LineKind.COMMENT:
        return (n.kind.value, n.raw)
    if n.kind is LineKind.EMPTY:
        return (n.kind.value,)
    return (n.kind.value, n.raw)


def _categorias_duplicatas(a: DgVoodooDocument, b: DgVoodooDocument) -> bool:
    return sorted(a.duplicates().keys()) != sorted(b.duplicates().keys()) or \
        sorted((k, tuple(v)) for k, v in a.duplicates().items()) != \
        sorted((k, tuple(v)) for k, v in b.duplicates().items())


def diff_documents(a, b) -> DiffReport:
    """Compara dois documentos (bytes ou DgVoodooDocument) sem mutar nada."""
    da = _como_documento(a)
    db = _como_documento(b)
    cats: List[str] = []
    entries: List[DiffEntry] = []

    def add(cat: str, desc: str, det: str = "") -> None:
        if cat not in cats:
            cats.append(cat)
        entries.append(DiffEntry(category=cat, description=desc, detail=det))

    bytes_a = da.serialize_lossless()
    bytes_b = db.serialize_lossless()
    if bytes_a != bytes_b:
        add("bytes", "bytes divergem", f"{da.sha256()} != {db.sha256()}")
    if da.bom != db.bom:
        add("bom", "BOM difere", f"a={da.bom} b={db.bom}")
    if da.encoding != db.encoding:
        add("encoding", "encoding observado difere",
            f"a={da.encoding} b={db.encoding}")

    style_a = _newline_style(da.lines)
    style_b = _newline_style(db.lines)
    if style_a != style_b or [n.eol for n in da.lines] != [n.eol for n in db.lines]:
        add("newline", "terminadores diferem", f"{style_a} vs {style_b}")
    if da.metadata().has_final_newline != db.metadata().has_final_newline:
        add("newline_final", "newline final difere",
            f"a={da.metadata().has_final_newline} b={db.metadata().has_final_newline}")

    if da.sections() != db.sections():
        add("secao", "seções/ordem diferem", f"{da.sections()} vs {db.sections()}")

    sa = [_item_semantico(n) for n in da.lines]
    sb = [_item_semantico(n) for n in db.lines]

    if sa == sb:
        same = bytes_a == bytes_b
        if not same:
            add("formatting", "apenas formatação (espaços/valor bruto)", "")
        return DiffReport(same=same, categories=cats, entries=entries)

    sm = difflib.SequenceMatcher(None, sa, sb, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            for k in range(max(i2 - i1, j2 - j1)):
                item_a = sa[i1 + k] if i1 + k < i2 else None
                item_b = sb[j1 + k] if j1 + k < j2 else None
                if item_a is None or item_b is None:
                    continue
                cat, det = _categoria_substituicao(item_a, item_b)
                add(cat, "linha substituída", det)
        elif tag in ("insert", "delete"):
            itens = sb[j1:j2] if tag == "insert" else sa[i1:i2]
            for item in itens:
                cat, det = _categoria_item(item, tag)
                add(cat, f"ocorrência {tag}", det)

    # apenas ordem (mesmo multiconjunto)
    if sa != sb and sorted(map(repr, sa)) == sorted(map(repr, sb)):
        add("ordem", "mesmas linhas em ordem diferente", "")

    if _categorias_duplicatas(da, db):
        add("duplicata", "duplicatas diferem",
            f"a={da.duplicates()} b={db.duplicates()}")

    same = False
    return DiffReport(same=same, categories=cats, entries=entries)


def _categoria_substituicao(item_a: tuple, item_b: tuple) -> Tuple[str, str]:
    kind_a, kind_b = item_a[0], item_b[0]
    if kind_a == "keyvalue" and kind_b == "keyvalue":
        if item_a[1:3] == item_b[1:3]:
            return ("valor", f"{_rotulo(item_a[1], item_a[2])}: "
                             f"{item_a[3]!r} -> {item_b[3]!r}")
        return ("chave", f"{_rotulo(item_a[1], item_a[2])} -> "
                         f"{_rotulo(item_b[1], item_b[2])}")
    mapa = {
        "comment": ("comentario", "comentário alterado"),
        "empty": ("formatting", "linha vazia alterada"),
        "unknown": ("linha_desconhecida", "linha desconhecida alterada"),
        "section": ("secao", "seção alterada"),
    }
    if kind_a == kind_b and kind_a in mapa:
        cat, desc = mapa[kind_a]
        return (cat, f"{desc}: {item_a!r} -> {item_b!r}")
    return ("linha", f"linha substituída: {item_a!r} -> {item_b!r}")


def _rotulo(section: Optional[str], key: str) -> str:
    return f"[GLOBAL].{key}" if section is None else f"[{section}].{key}"


def _categoria_item(item: tuple, tag: str) -> Tuple[str, str]:
    if item[0] == "keyvalue":
        if tag == "insert":
            return ("chave", f"{_rotulo(item[1], item[2])}={item[3]!r} inserida")
        return ("chave", f"{_rotulo(item[1], item[2])}={item[3]!r} removida")
    if item[0] == "section":
        return ("secao", f"[{item[1]}] {tag}")
    if item[0] == "comment":
        return ("comentario", f"linha de comentário {tag}: {item[1]!r}")
    if item[0] == "empty":
        return ("formatting", f"linha vazia {tag}")
    return ("linha_desconhecida", f"linha desconhecida {tag}: {item[1]!r}")


# ---------------------------------------------------------------------------
# Estágio 2 — Active AIKA Serialization (geração shadow, somente memória)
# ---------------------------------------------------------------------------

LayerMapping = Dict[str, Dict[str, str]]  # seção -> {chave: valor}


@dataclass
class ActiveGeneration:
    """Resultado da geração shadow (Modo B). Nada é gravado por padrão."""

    bytes_: bytes
    provenance: Dict[Tuple[Optional[str], str], str]
    applied: Dict[Tuple[Optional[str], str], str]
    warnings: List[str]

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.bytes_).hexdigest()

    @property
    def size(self) -> int:
        return len(self.bytes_)


def _substituir_valor_linha(content: str, chave: str, valor: str) -> Optional[str]:
    """Espelha a substituição do gerador atual: preserva o prefixo até o
    whitespace após '=' e descarta o restante (comentário inline incluído).
    Retorna None se o padrão não casar."""
    m = re.match(r"^(\s*" + re.escape(chave) + r"\s*=\s*)(.*)$", content)
    if m is None:
        return None
    return m.group(1) + valor


def generate_active(data,
                    *,
                    fixed: LayerMapping,
                    base: Optional[LayerMapping] = None,
                    profiles: Optional[Dict[str, LayerMapping]] = None,
                    profile: Optional[str] = None,
                    validate_domain=None,
                    catalog: Optional[Catalog] = None) -> ActiveGeneration:
    """Modo B — gera em memória a configuração ativa equivalente ao gerador
    atual (template + overlay fixo + base + perfil), UTF-8 SEM BOM, CRLF, sem
    newline final, sem alterar o template.

    fixed: 12 invariantes (obrigatórias; ausência -> erro bloqueante).
    base: Balanced base (Filtering/Antialiasing na ativação/Reaplicar).
    profiles/profile: perfil efetivo (performance/balanced/quality).
    validate_domain: (identity, valor) -> Optional[str]; erro bloqueia.
    """
    doc = _como_documento(data)
    mapa_perfil = None
    if profile is not None:
        if not profiles or profile not in profiles:
            raise ValueError(f"Perfil desconhecido: {profile!r}")
        mapa_perfil = profiles[profile]

    # domínio: valores que as camadas do AIKA pretendem escrever
    alvos: LayerMapping = {}
    for origem in (fixed, base or {}, mapa_perfil or {}):
        for secao, chaves in origem.items():
            alvos.setdefault(secao, {}).update(chaves)
    if validate_domain is not None:
        for secao, chaves in alvos.items():
            for chave, valor in chaves.items():
                erro = validate_domain((secao, chave), valor)
                if erro:
                    raise ValueError(
                        f"Valor de overlay/perfil fora de domínio: "
                        f"[{secao}].{chave}={valor!r} ({erro})")

    # invariantes obrigatórias precisam existir no template
    for secao, chaves in fixed.items():
        for chave in chaves:
            if doc.count(secao, chave) < 1:
                nome = f"[GLOBAL].{chave}" if secao is None else f"[{secao}].{chave}"
                raise ValueError(
                    f"Chave obrigatória ausente do template: {nome}. "
                    f"Não insiro automaticamente.")


    merged: Dict[Tuple[Optional[str], str], str] = {}
    for secao, chaves in alvos.items():
        for chave, valor in chaves.items():
            merged[(secao, chave)] = valor

    # provenance
    fixed_set = {(s, k) for s, m in fixed.items() for k in m}
    base_set = {(s, k) for s, m in (base or {}).items() for k in m}
    perfil_set = {(s, k) for s, m in (mapa_perfil or {}).items() for k in m}

    linhas_saida: List[str] = []
    for n in doc.lines:
        if n.kind is LineKind.KEYVALUE and n.key is not None:
            ident = (n.section, n.key)
            valor = merged.get(ident)
            if valor is not None:
                novo = _substituir_valor_linha(n.raw, n.key, valor)
                linhas_saida.append(novo if novo is not None else n.raw)
                continue
        linhas_saida.append(n.raw)

    texto_ativo = "\r\n".join(linhas_saida)  # mesmo join do gerador atual
    dados = texto_ativo.encode("utf-8")  # SEM BOM

    # provenance para todas as identidades efetivas do documento final
    prov: Dict[Tuple[Optional[str], str], str] = {}
    for o in _como_documento(dados).occurrences():
        ident = (o.section, o.key)
        if ident in fixed_set:
            prov[ident] = "overlay_fixo"
        elif mapa_perfil is not None and ident in perfil_set:
            prov[ident] = "perfil"
        elif ident in base_set:
            prov[ident] = "overlay_base"
        else:
            prov[ident] = "template"

    warnings: List[str] = []
    if catalog is not None:
        for o in _como_documento(dados).occurrences():
            ident = (o.section, o.key)
            cat = catalog.get(o.section)
            if cat is not None and o.key not in cat:
                warnings.append(
                    f"unknown_to_schema: [{o.section or 'GLOBAL'}].{o.key} "
                    f"preservado (linha {o.line_index}).")
    return ActiveGeneration(bytes_=dados, provenance=prov,
                            applied=dict(merged), warnings=warnings)


def write_shadow(generacao: ActiveGeneration, caminho: str) -> None:
    """Materialização explícita de bytes shadow (apenas testes/temp)."""
    with open(caminho, "wb") as f:
        f.write(generacao.bytes_)


__all__ = [
    "LineKind", "LineNode", "Occurrence", "DocumentMetadata", "ReadDiagnostic",
    "DiffEntry", "DiffReport", "DgVoodooDocument", "parse_bytes", "read_file",
    "diff_documents", "ActiveGeneration", "generate_active", "write_shadow",
    "LayerMapping",
]
