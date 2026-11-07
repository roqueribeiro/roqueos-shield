"""Users router — gestão de usuários nomeados + papéis (RBAC). Admin-only.

Auth por **token por-usuário**: o token em claro só aparece UMA vez (na criação
ou na rotação) — guardamos apenas o hash. Toda mutação é auditada
(`user.create` / `user.deactivate` / `user.rotate_token`) com o `actor` real.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlmodel import col, select

from orchestrator.api.deps import (
    Principal,
    SessionDep,
    require_permission,
    token_hash,
)
from orchestrator.audit import log_audit_event
from orchestrator.auth.senha import gerar_hash, problema_da_senha
from orchestrator.domain.roles import Permission, Role
from orchestrator.persistence.models import UserRow

router = APIRouter(prefix="/users", tags=["users"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Gate de RBAC reutilizado por todos os endpoints deste router.
_ADMIN = Depends(require_permission(Permission.USERS_MANAGE))


def _new_token() -> str:
    """Token por-usuário opaco (mostrado uma vez)."""
    return "cai_" + secrets.token_urlsafe(32)


class UserCreate(BaseModel):
    email: str
    name: str | None = None
    role: Role = Role.VIEWER
    # Opcional: com senha, a pessoa entra pela tela; sem, só por token ou OIDC.
    password: str | None = Field(default=None, max_length=256)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("e-mail inválido")
        return v


class RoleUpdate(BaseModel):
    role: Role


class PasswordUpdate(BaseModel):
    password: str = Field(min_length=1, max_length=256)


async def _rebaixar_se_sobrar_admin(session: SessionDep, alvo: UUID, valores: dict) -> None:
    """Aplica a mudança num UPDATE só, condicionado a existir OUTRO admin ativo.

    A checagem e a escrita no mesmo comando: no SQLite o SELECT de antes não segura
    lock, e dois admins se rebaixando juntos liam "sobra o outro" e zeravam os admins
    (provado pela revisão). Linha nenhuma alterada = era o último: 409.
    """
    from sqlalchemy import exists, update
    from sqlalchemy.orm import aliased

    outro = aliased(UserRow)
    stmt = (
        update(UserRow)
        .where(
            col(UserRow.id) == alvo,
            exists().where(
                col(outro.role) == Role.ADMIN.value,
                col(outro.active).is_(True),
                col(outro.id) != alvo,
            ),
        )
        .values(**valores)
        .execution_options(synchronize_session=False)
    )
    r = await session.exec(stmt)
    if r.rowcount == 0:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "é o último admin ativo")


async def _sobra_admin_ativo(session: SessionDep, sem: UUID) -> bool:
    """Existe outro admin ativo além de `sem`? Sem isto o shield podia ficar sem
    ninguém que gerencie usuários, e no standalone não há RoqueOS por fora para
    consertar.

    No Postgres, um lock de transação serializa quem rebaixa ou desativa admin: sem
    ele, dois admins se rebaixando ao mesmo tempo liam "sobra o outro" e o shield ficava
    sem nenhum. A garantia de verdade, nos dois bancos, é o UPDATE condicional de
    `_rebaixar_se_sobrar_admin`; esta leitura só dá a resposta cedo.
    """
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy import text

        await session.exec(text("SELECT pg_advisory_xact_lock(73113)"))  # type: ignore[call-overload]
    outros = (
        await session.exec(
            select(UserRow).where(
                UserRow.role == Role.ADMIN.value,
                col(UserRow.active).is_(True),
                UserRow.id != sem,
            )
        )
    ).first()
    return outros is not None


class UserOut(BaseModel):
    id: UUID
    email: str
    name: str | None
    role: str
    active: bool
    created_at: datetime
    last_login_at: datetime | None
    has_password: bool = False


class UserCreated(UserOut):
    api_token: str = Field(description="Token do usuário — mostrado UMA vez.")


def _to_out(u: UserRow) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        name=u.name,
        role=u.role,
        active=u.active,
        created_at=u.created_at,
        last_login_at=u.last_login_at,
        has_password=bool(u.password_hash),
    )


@router.post("", response_model=UserCreated, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate, session: SessionDep, principal: Principal = _ADMIN
) -> UserCreated:
    # O login normaliza o e-mail; criar sem normalizar fazia "Ana@X.com" nunca entrar.
    email = body.email.strip().lower()
    existing = (await session.exec(select(UserRow).where(UserRow.email == email))).first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "e-mail já cadastrado")

    if body.password is not None and (motivo := problema_da_senha(body.password)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, motivo)
    token = _new_token()
    user = UserRow(
        email=email,
        name=body.name,
        role=body.role.value,
        api_token_hash=token_hash(token),
        password_hash=gerar_hash(body.password) if body.password else None,
    )
    session.add(user)
    await session.flush()
    await log_audit_event(
        session,
        action="user.create",
        actor=principal.email,
        resource_type="user",
        resource_id=user.id,
        metadata={"email": user.email, "role": user.role},
    )
    await session.commit()
    await session.refresh(user)
    return UserCreated(**_to_out(user).model_dump(), api_token=token)


@router.get("", response_model=list[UserOut])
async def list_users(session: SessionDep, _admin: Principal = _ADMIN) -> list[UserOut]:
    rows = (await session.exec(select(UserRow).order_by(col(UserRow.created_at)))).all()
    return [_to_out(u) for u in rows]


@router.patch("/{user_id}/role", response_model=UserOut)
async def set_role(
    user_id: UUID,
    body: RoleUpdate,
    session: SessionDep,
    principal: Principal = _ADMIN,
) -> UserOut:
    user = await session.get(UserRow, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "usuário não encontrado")
    if (
        user.role == Role.ADMIN.value
        and body.role is not Role.ADMIN
        and not await _sobra_admin_ativo(session, user.id)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "é o último admin ativo")
    if user.role == Role.ADMIN.value and body.role is not Role.ADMIN:
        await _rebaixar_se_sobrar_admin(session, user.id, {"role": body.role.value})
        await session.refresh(user)
    user.role = body.role.value
    session.add(user)
    await log_audit_event(
        session,
        action="user.set_role",
        actor=principal.email,
        resource_type="user",
        resource_id=user.id,
        metadata={"role": user.role},
    )
    await session.commit()
    await session.refresh(user)
    return _to_out(user)


@router.post("/{user_id}/deactivate", response_model=UserOut)
async def deactivate_user(
    user_id: UUID, session: SessionDep, principal: Principal = _ADMIN
) -> UserOut:
    user = await session.get(UserRow, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "usuário não encontrado")
    if user.role == Role.ADMIN.value and not await _sobra_admin_ativo(session, user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "é o último admin ativo")
    if user.role == Role.ADMIN.value:
        await _rebaixar_se_sobrar_admin(session, user.id, {"active": False})
        await session.refresh(user)
    user.active = False
    user.session_version = int(user.session_version or 0) + 1
    session.add(user)
    await log_audit_event(
        session,
        action="user.deactivate",
        actor=principal.email,
        resource_type="user",
        resource_id=user.id,
    )
    await session.commit()
    await session.refresh(user)
    return _to_out(user)


@router.post("/{user_id}/rotate-token", response_model=UserCreated)
async def rotate_token(
    user_id: UUID, session: SessionDep, principal: Principal = _ADMIN
) -> UserCreated:
    user = await session.get(UserRow, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "usuário não encontrado")
    token = _new_token()
    user.api_token_hash = token_hash(token)
    session.add(user)
    await log_audit_event(
        session,
        action="user.rotate_token",
        actor=principal.email,
        resource_type="user",
        resource_id=user.id,
    )
    await session.commit()
    await session.refresh(user)
    return UserCreated(**_to_out(user).model_dump(), api_token=token)


@router.put("/{user_id}/password", response_model=UserOut)
async def set_password(
    user_id: UUID, body: PasswordUpdate, session: SessionDep, principal: Principal = _ADMIN
) -> UserOut:
    """Define (ou troca) a senha de login da tela. A senha não vai para a trilha."""
    user = await session.get(UserRow, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "usuário não encontrado")
    if motivo := problema_da_senha(body.password):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, motivo)
    user.password_hash = gerar_hash(body.password)
    # Senha trocada (muitas vezes por suspeita de vazamento) derruba as sessões abertas.
    user.session_version = int(user.session_version or 0) + 1
    session.add(user)
    await log_audit_event(
        session,
        action="user.set_password",
        actor=principal.email,
        resource_type="user",
        resource_id=user.id,
    )
    await session.commit()
    await session.refresh(user)
    return _to_out(user)
