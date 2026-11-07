"""Configuração de IA e de escopo pela API (a tela de Ajustes do standalone).

Mesma forma de dado do `/pentest/ai` e `/pentest/scope` do `roqueos-server`. Escrita
exige `config:manage`, vai para a trilha de auditoria (sem o valor de segredo) e vale
sem reiniciar: este processo aplica na hora, e o worker no próximo job.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from orchestrator.api.deps import Principal, RequireConfigManage, SessionDep
from orchestrator.audit import log_audit_event
from orchestrator.runtime_settings import (
    CAMPOS_ESCOPO,
    CAMPOS_IA,
    SemChaveDeCifra,
    escopo,
    gravar,
    ia_mascarada,
)

router = APIRouter(prefix="/settings", tags=["settings"])


class IaOut(BaseModel):
    model: str
    fallbackModel: str
    investigationModel: str
    apiBase: str
    hasApiKey: bool
    hasAnthropicKey: bool
    hasOpenaiKey: bool
    hasOpenrouterKey: bool
    isLocal: bool
    locked: list[str] = Field(description="campos definidos pelo ambiente; a tela não troca")


class IaIn(BaseModel):
    """Só o que vier é gravado. Chave: string vazia apaga, ausente mantém."""

    model_config = ConfigDict(extra="forbid")
    model: str | None = Field(default=None, examples=["anthropic/claude-sonnet-4-6"])
    fallbackModel: str | None = None
    investigationModel: str | None = None
    apiBase: str | None = Field(default=None, examples=["http://host.docker.internal:1234/v1"])
    apiKey: str | None = None
    anthropicKey: str | None = None
    openaiKey: str | None = None
    openrouterKey: str | None = None


class EscopoOut(BaseModel):
    labOnly: bool
    allowlist: list[str]
    requireAuthRef: bool
    allowCloudFallback: bool
    locked: list[str]


class EscopoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    labOnly: bool | None = None
    allowlist: list[str] | None = Field(
        default=None, examples=[["app.empresa.com.br", "10.0.0.0/8"]]
    )
    requireAuthRef: bool | None = None
    allowCloudFallback: bool | None = None


async def _salvar(session, campos, body: BaseModel, principal: Principal, acao: str) -> list[str]:
    valores: dict[str, Any] = body.model_dump(exclude_unset=True)
    try:
        gravadas = await gravar(session, campos, valores, ator=principal.email)
    except SemChaveDeCifra as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    secretos = {c.chave for c in campos if c.secreto}
    await log_audit_event(
        session,
        action=acao,
        actor=principal.email,
        resource_type="settings",
        # valor de segredo nunca vai para a trilha: só que foi trocado
        metadata={k: ("(trocado)" if k in secretos else valores[k]) for k in gravadas},
    )
    await session.commit()
    return gravadas


@router.get("/ai", response_model=IaOut)
async def get_ai(_p: Principal = RequireConfigManage) -> dict[str, Any]:
    return ia_mascarada()


@router.put("/ai", response_model=IaOut)
async def put_ai(
    body: IaIn, session: SessionDep, principal: Principal = RequireConfigManage
) -> dict[str, Any]:
    await _salvar(session, CAMPOS_IA, body, principal, "settings.ai")
    return ia_mascarada()


@router.get("/scope", response_model=EscopoOut)
async def get_scope(_p: Principal = RequireConfigManage) -> dict[str, Any]:
    return escopo()


@router.put("/scope", response_model=EscopoOut)
async def put_scope(
    body: EscopoIn, session: SessionDep, principal: Principal = RequireConfigManage
) -> dict[str, Any]:
    await _salvar(session, CAMPOS_ESCOPO, body, principal, "settings.scope")
    return escopo()
