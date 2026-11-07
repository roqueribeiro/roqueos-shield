"""Primeiro uso e login por senha da tela standalone.

`GET /setup` diz se o shield ainda não tem nenhum usuário. `POST /setup` cria o
primeiro admin, e só funciona enquanto não existe usuário nenhum: depois devolve 410.
Não há como "refazer o setup" pela rede, de propósito.

`POST /auth/session` troca e-mail e senha por uma sessão no cookie `rs_session`
(httpOnly, SameSite=Strict). `DELETE /auth/session` apaga o cookie. O login OIDC
(`/auth/login`) continua como estava.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import select

from orchestrator.api.deps import COOKIE_SESSAO, PrincipalDep, SessionDep
from orchestrator.audit import log_audit_event
from orchestrator.auth import issue_session
from orchestrator.auth.senha import conferir, gerar_hash, problema_da_senha
from orchestrator.config import settings
from orchestrator.domain.roles import Role
from orchestrator.persistence.models import UserRow

log = structlog.get_logger(__name__)
router = APIRouter(tags=["conta"])

# Hash de uma senha que ninguém tem, para o login de e-mail inexistente gastar o mesmo
# tempo do login de senha errada (não dá para descobrir quem tem conta pelo relógio).
_HASH_FANTASMA = gerar_hash("roqueshield-usuario-que-nao-existe")


class SetupStatus(BaseModel):
    needs_setup: bool = Field(description="true enquanto não existe nenhum usuário")
    version: str


class SetupIn(BaseModel):
    email: str = Field(min_length=3, max_length=254, examples=["admin@empresa.com.br"])
    name: str | None = Field(default=None, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class SessaoOut(BaseModel):
    id: str
    email: str
    name: str | None
    role: str


def _cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        COOKIE_SESSAO,
        token,
        max_age=settings.SESSION_TTL_HOURS * 3600,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        path="/",
    )


async def _total_de_usuarios(session) -> int:
    return int((await session.exec(select(func.count()).select_from(UserRow))).one())


@router.get("/setup", response_model=SetupStatus)
async def setup_status(session: SessionDep) -> SetupStatus:
    """Sem autenticação: a tela precisa saber se mostra o primeiro uso ou o login."""
    from orchestrator.main import app

    return SetupStatus(needs_setup=await _total_de_usuarios(session) == 0, version=app.version)


@router.post("/setup", response_model=SessaoOut, status_code=status.HTTP_201_CREATED)
async def setup(
    body: SetupIn, request: Request, response: Response, session: SessionDep
) -> SessaoOut:
    if await _total_de_usuarios(session) > 0:
        raise HTTPException(status.HTTP_410_GONE, "o primeiro uso já foi feito")
    motivo = problema_da_senha(body.password)
    if motivo:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, motivo)
    user = UserRow(
        email=body.email.strip().lower(),
        name=body.name,
        role=Role.ADMIN.value,
        password_hash=gerar_hash(body.password),
        last_login_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    await log_audit_event(
        session,
        action="setup.admin_created",
        actor=user.email,
        resource_type="user",
        resource_id=user.id,
        metadata={"email": user.email},
    )
    await session.commit()
    _cookie(response, request, issue_session(user_id=user.id, email=user.email, role=user.role))
    return SessaoOut(id=str(user.id), email=user.email, name=user.name, role=user.role)


@router.post("/auth/session", response_model=SessaoOut)
async def login(
    body: LoginIn, request: Request, response: Response, session: SessionDep
) -> SessaoOut:
    email = body.email.strip().lower()
    user = (await session.exec(select(UserRow).where(UserRow.email == email))).first()
    ok = conferir(body.password, user.password_hash if user else _HASH_FANTASMA)
    if user is None or not ok or not user.active:
        await log_audit_event(
            session, action="user.login_failed", actor=email, metadata={"via": "senha"}
        )
        await session.commit()
        # Mesma mensagem para e-mail inexistente, senha errada e usuário desativado.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "e-mail ou senha inválidos")
    user.last_login_at = datetime.now(UTC)
    session.add(user)
    await log_audit_event(
        session,
        action="user.login",
        actor=user.email,
        resource_type="user",
        resource_id=user.id,
        metadata={"via": "senha"},
    )
    await session.commit()
    _cookie(response, request, issue_session(user_id=user.id, email=user.email, role=user.role))
    return SessaoOut(id=str(user.id), email=user.email, name=user.name, role=user.role)


@router.delete("/auth/session", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    response.delete_cookie(COOKIE_SESSAO, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/auth/session", response_model=SessaoOut)
async def quem_sou(principal: PrincipalDep, session: SessionDep) -> SessaoOut:
    nome = None
    if not principal.is_service:
        from uuid import UUID

        u = await session.get(UserRow, UUID(principal.id))
        nome = u.name if u else None
    return SessaoOut(id=principal.id, email=principal.email, name=nome, role=principal.role.value)
