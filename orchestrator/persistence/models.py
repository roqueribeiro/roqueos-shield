"""Persistence models (SQLModel) — Target, Scan, FindingRow, AIRun."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Text
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel

from orchestrator.domain.schemas import Severity


class UTCDateTime(TypeDecorator[datetime]):
    """`DateTime(timezone=True)` que devolve sempre com fuso UTC.

    O SQLite não guarda fuso: a data volta "ingênua" e a API a serializava sem `Z`
    ("2026-11-07T11:51:15"). O navegador lê isso como hora LOCAL, e no Brasil o scan
    feito agora aparecia "em 3 horas". Tudo aqui é gravado em UTC (`datetime.now(UTC)`),
    então data sem fuso que sai do banco é UTC. No Postgres nada muda.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class ScanState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"


class FindingStatus(StrEnum):
    """Estado de RESOLUÇÃO de um problema (workflow), ortogonal à severity.

    Atrelado ao `deduped_key` (identidade determinística do problema), não a um
    FindingRow (instância de um scan) — ver `FindingStatusRow`.
    """

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"
    WONT_FIX = "wont_fix"
    RISK_ACCEPTED = "risk_accepted"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TargetRow(SQLModel, table=True):
    __tablename__ = "targets"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    asset_type: str
    value: str = Field(index=True)
    label: str | None = None
    criticality: str = Severity.MEDIUM.value
    contains_pii: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=UTCDateTime())


class ScanRow(SQLModel, table=True):
    __tablename__ = "scans"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    target_id: UUID = Field(foreign_key="targets.id", index=True)
    state: str = Field(default=ScanState.PENDING.value, index=True)
    profile: str = "web"  # web | network | full | active | exposure (PERFIS_DO_SCAN)
    requested_scanners: list[str] = Field(default_factory=list, sa_type=JSON)
    options: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    actor: str | None = None
    # Referência formal à autorização (ticket, change, aprovação por escrito).
    # Exigido quando settings.REQUIRE_AUTH_REF=true.
    authorization_ref: str | None = Field(default=None, index=True)
    started_at: datetime | None = Field(default=None, sa_type=UTCDateTime())
    finished_at: datetime | None = Field(default=None, sa_type=UTCDateTime())
    errors: list[str] = Field(default_factory=list, sa_type=JSON)
    # COBERTURA — quem realmente rodou e quem não rodou, com o motivo.
    # Existe porque `state=done` + zero achados tem dois significados opostos: alvo
    # limpo, ou scanner que não rodou. Sem estas duas colunas, o pipeline calculava a
    # diferença e ela morria no worker: a API, a tela e o Fix Bundle continuavam
    # dizendo "todos os scanners pedidos rodaram". Estruturado de propósito — o
    # bundle deduzia cobertura fazendo string-parsing de mensagem de erro.
    scanners_ran: list[str] = Field(default_factory=list, sa_type=JSON)
    scanners_skipped: dict[str, str] = Field(default_factory=dict, sa_type=JSON)
    report_path: str | None = None
    # Granularidade de fase: queued|nmap_running|zap_spider|zap_passive|zap_active|
    # dedup|ai_triage|persisting|reporting|done|failed
    current_phase: str | None = Field(default=None, index=True)
    phase_progress: int | None = None  # 0-100 quando aplicável (ex: ZAP spider %)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=UTCDateTime())


class AuditLogRow(SQLModel, table=True):
    """Audit log append-only.

    Em Postgres, UPDATE/DELETE são rejeitados pelo trigger `audit_log_no_update`
    instalado pela migration 0004. Em SQLite (dev), o trigger não existe — o
    contrato é mantido apenas no código (`orchestrator.audit.logger`).
    """

    __tablename__ = "audit_log"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    actor: str | None = Field(default=None, index=True)
    action: str = Field(index=True)  # ex: "scan.create", "target.create"
    resource_type: str | None = None  # ex: "scan", "target"
    resource_id: UUID | None = Field(default=None, index=True)
    authorization_ref: str | None = Field(default=None, index=True)
    request_hash: str | None = None  # sha256 do body da requisição (sem PII)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=UTCDateTime(), index=True)


class FindingRow(SQLModel, table=True):
    __tablename__ = "findings"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    scan_id: UUID = Field(foreign_key="scans.id", index=True)
    target_id: UUID = Field(foreign_key="targets.id", index=True)
    # Ativo do inventário (Frente A). Opcional: findings antigos e scans sem
    # agregação de ativo ficam com None. Preenchido no pipeline após o dedup.
    asset_id: UUID | None = Field(default=None, foreign_key="assets.id", index=True)
    deduped_key: str = Field(index=True)
    source_tool: str = Field(index=True)
    source_rule_id: str | None = None
    vuln_id: str | None = Field(default=None, index=True)
    title: str
    severity: str = Field(index=True)
    confidence: str = "firm"
    payload: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    discovered_at: datetime = Field(default_factory=_utcnow, sa_type=UTCDateTime())


class FindingStatusRow(SQLModel, table=True):
    """Estado de resolução (triage de workflow) de um problema único.

    Keyed por `deduped_key` (a IDENTIDADE determinística do problema — ver
    `Finding._build_dedup_key`), NÃO por finding id. Razão: `findings` é
    write-once e um re-scan cria novos FindingRow com o MESMO `deduped_key`;
    o estado "resolvido/aceito/falso-positivo" pertence ao PROBLEMA, então
    precisa sobreviver entre scans. Quem corrige um problema no código-alvo e
    re-escaneia continua vendo "resolvido" (e se o problema sumir do re-scan,
    fica confirmado). Toda mudança aqui também gera entrada no `audit_log`
    (ver `api/routers/findings.py::resolve_finding`).

    `last_*`/`target_value` são um snapshot denormalizado do último finding
    visto com essa key — dá contexto na listagem/auditoria sem JOIN e mesmo se
    o FindingRow for podado.
    """

    __tablename__ = "finding_status"

    deduped_key: str = Field(primary_key=True)
    status: str = Field(default=FindingStatus.OPEN.value, index=True)
    note: str | None = None
    updated_by: str | None = Field(default=None, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=UTCDateTime())
    resolved_at: datetime | None = Field(default=None, sa_type=UTCDateTime())
    # snapshot denormalizado do último finding com essa key (contexto sem JOIN)
    last_severity: str | None = Field(default=None, index=True)
    last_title: str | None = None
    target_value: str | None = Field(default=None, index=True)


class AssetRow(SQLModel, table=True):
    """Ativo do inventário, persistente ENTRE scans (Frente A).

    A identidade é `asset_key` — determinística (`orchestrator.domain.assets.asset_key`),
    no mesmo molde da `Finding.deduped_key`: o mesmo host/porta/URL em dois scans tem a
    MESMA `asset_key`, então a linha é reusada (upsert) e o `id` UUID permanece estável.
    Por isso o finding aponta para `assets.id` e o id sobrevive entre scans — o que muda é
    só `last_seen`/`last_scan_id`. `first_seen` nunca é reescrito.
    """

    __tablename__ = "assets"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    # Identidade determinística (sha256[:32]). Única: é por ela que o upsert acha a linha.
    asset_key: str = Field(index=True, unique=True)
    asset_type: str = Field(index=True)  # host|url|port|image|repo|domain|k8s_resource
    value: str = Field(index=True)  # valor normalizado do alvo (host:porta/proto, URL, ...)
    label: str | None = None
    first_seen: datetime = Field(default_factory=_utcnow, sa_type=UTCDateTime())
    last_seen: datetime = Field(default_factory=_utcnow, sa_type=UTCDateTime())
    # Scan em que foi visto por último — âncora para "sumiu" vs "não verificado".
    last_scan_id: UUID | None = Field(default=None, foreign_key="scans.id", index=True)
    technologies: list[str] = Field(default_factory=list, sa_type=JSON)
    # Texto livre (banner, título) passa pelo scrubber ANTES de entrar aqui.
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class AssetObservationRow(SQLModel, table=True):
    """Uma observação de um ativo num scan específico (Frente A).

    Uma linha por (ativo, scan): é o registro de que aquele scan VIU aquele ativo.
    A ausência de linha para um scan, combinada com a cobertura do scan
    (`ScanRow.scanners_ran`/`scanners_skipped`), é o que distingue "sumiu" de
    "não verificado" — ver `orchestrator.domain.assets.classificar_presenca`.
    """

    __tablename__ = "asset_observations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    asset_id: UUID = Field(foreign_key="assets.id", index=True)
    scan_id: UUID = Field(foreign_key="scans.id", index=True)
    observed_at: datetime = Field(default_factory=_utcnow, sa_type=UTCDateTime())
    source_tool: str | None = Field(default=None, index=True)  # quem viu (nmap, zap, ...)
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class EvidenceSnapshotRow(SQLModel, table=True):
    """Registro write-once de um corpo de evidência (Frente C).

    Imutável como o `audit_log`: em Postgres o trigger `evidence_snapshots_no_update`
    (migration 0011) rejeita UPDATE/DELETE; em SQLite o contrato vive no código (o
    armazém `orchestrator.evidence.store` grava o blob uma vez e nunca reescreve).

    `sha256` endereça o corpo GRAVADO (redigido por padrão, ou cifrado) no armazém.
    `original_sha256` é o hash do corpo antes de redigir/cifrar — proveniência, sem
    guardar o original. A retenção apaga o blob em disco e mantém esta linha: hash e
    registro ficam, o corpo some.
    """

    __tablename__ = "evidence_snapshots"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    sha256: str = Field(index=True)  # endereço do corpo gravado no armazém
    original_sha256: str = Field(index=True)  # hash do original (antes de redigir/cifrar)
    content_type: str = "text/plain"
    size_bytes: int = 0
    encrypted: bool = False  # o blob é o original cifrado (opção de engajamento)?
    # scan_id é informativo (SEM FK de propósito): a evidência é imutável e sobrevive à
    # remoção do scan. Uma FK aqui, combinada com o trigger append-only, impediria apagar
    # um scan que gravou evidência (nem DELETE nem o SET NULL do ON DELETE passariam).
    scan_id: UUID | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=UTCDateTime(), index=True)


class EvidenceLinkRow(SQLModel, table=True):
    """Vínculo achado↔evidência com papel (Frente C).

    Keyed pelo `deduped_key` (a identidade do PROBLEMA, como o `FindingStatusRow`), para
    a evidência de prova sobreviver ao re-scan: quem corrige e re-escaneia continua vendo
    a prova (`proof`) e a linha de base (`baseline`). `evidence_version` sobe a cada
    vínculo novo do mesmo problema; um relatório gravado sobre uma versão antiga é
    rejeitado (a checagem em si é da Frente D).
    """

    __tablename__ = "evidence_links"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    deduped_key: str = Field(index=True)
    snapshot_id: UUID = Field(foreign_key="evidence_snapshots.id", index=True)
    # baseline (antes) | proof (o achado) | verification (reteste) | supporting (apoio)
    papel: str = Field(default="supporting", index=True)
    ordem: int = 0
    nota: str | None = None
    evidence_version: int = 1
    created_at: datetime = Field(default_factory=_utcnow, sa_type=UTCDateTime())


class CommandApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"  # tempo limite estourou com a pendência aberta — fecha fechado


class CommandApprovalRow(SQLModel, table=True):
    """Pendência de aprovação de um comando (Frente E, modo `ask`).

    A coleira decide primeiro (continua igual); o que passou vira uma pendência aqui para
    uma pessoa aprovar ou negar. Tempo limite nega (fecha fechado): uma pendência além de
    `expires_at` conta como negada, nunca como liberada. `command` é guardado REDIGIDO
    pelo scrubber. Quatro olhos (opcional): quem propôs não aprova o próprio comando.
    Toda decisão também gera entrada no `audit_log`.
    """

    __tablename__ = "command_approvals"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    reference_type: str = Field(default="investigation", index=True)  # investigation|scan
    reference_id: UUID | None = Field(default=None, index=True)
    command: str  # texto do comando, redigido pelo scrubber
    proposed_by: str | None = Field(default=None, index=True)
    status: str = Field(default=CommandApprovalStatus.PENDING.value, index=True)
    decided_by: str | None = None
    decided_at: datetime | None = Field(default=None, sa_type=UTCDateTime())
    reason: str | None = None
    expires_at: datetime = Field(default_factory=_utcnow, sa_type=UTCDateTime(), index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=UTCDateTime())


class UserRow(SQLModel, table=True):
    """Usuário nomeado + papel (RBAC).

    Auth por **token por-usuário** (hash SHA-256 — o token em claro só aparece
    UMA vez, na criação/rotação). `idp_subject` reservado pro login OIDC/SSO
    (Fase 6). O `APP_TOKEN` global continua válido como principal de serviço
    (admin) — ver `orchestrator.api.deps`.
    """

    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(index=True, unique=True)
    name: str | None = None
    role: str = Field(default="viewer", index=True)  # admin|operator|auditor|viewer
    # SHA-256 do token por-usuário (nunca guardamos o token em claro).
    api_token_hash: str | None = Field(default=None, index=True, unique=True)
    # scrypt da senha (login da tela standalone). None = usuário sem senha, entra por
    # token ou OIDC. Formato em `orchestrator.auth.senha`.
    password_hash: str | None = None
    # Sobe no logout, na troca de senha e na desativação; o JWT de sessão carrega a
    # versão do login e deixa de valer quando ela muda (`orchestrator.auth.session`).
    session_version: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    idp_subject: str | None = Field(default=None, index=True)  # OIDC `sub` (Fase 6)
    active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=UTCDateTime())
    last_login_at: datetime | None = Field(default=None, sa_type=UTCDateTime())


class AIRun(SQLModel, table=True):
    """Telemetria de cada chamada LLM — custo, latência, tokens, cache hit."""

    __tablename__ = "ai_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    scan_id: UUID | None = Field(default=None, foreign_key="scans.id", index=True)
    purpose: str  # "triage" | "investigation" | "report_narrative"
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    latency_ms: int = 0
    estimated_cost_usd: float = 0.0
    finding_count: int = 0
    success: bool = True
    error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=UTCDateTime())


class AppSettingRow(SQLModel, table=True):
    """Configuração editável em runtime (IA e escopo), uma linha por campo.

    O ambiente vence: campo cuja variável veio no ambiente do processo fica travado
    e esta tabela não o sobrescreve (`orchestrator.runtime_settings`). Valor secreto
    (chave de API) é gravado cifrado com `SECRETS_KEY`, nunca em claro.
    """

    __tablename__ = "app_settings"

    key: str = Field(primary_key=True)
    # TEXT, como a migration 0008 cria: valor JSON sem limite de tamanho. O modelo dizia
    # `str` (VARCHAR) e o schema do standalone (create_all) divergia do de produção.
    value: str = Field(sa_type=Text)  # JSON; segredo vai como "enc:v1:<fernet>"
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=UTCDateTime())
    updated_by: str | None = None
