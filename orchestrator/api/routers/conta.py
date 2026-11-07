"""Primeiro uso e login por senha da tela standalone.

`GET /setup` diz se o shield ainda não tem nenhum usuário. `POST /setup` cria o
primeiro admin, e só funciona enquanto não existe usuário nenhum: depois devolve 410.
Não há como "refazer o setup" pela rede, de propósito.

O setup exige prova de acesso ao container: o código de primeiro uso (`SETUP_CODE`,
gerado em `$DATA_DIR/secrets/SETUP_CODE`) ou o `APP_TOKEN` no `X-API-Token`. Sem isso,
quem alcançasse a porta antes do dono virava admin. E ele é serializado por uma linha
sentinela de chave fixa em `app_settings`: dois POST simultâneos não criam dois admins.

O login por senha tem freio de tentativa (`orchestrator.auth.limite`).

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
from orchestrator.auth.limite import freio
from orchestrator.auth.senha import conferir, gerar_hash, problema_da_senha
from orchestrator.config import settings
from orchestrator.domain.roles import Role
from orchestrator.persistence.models import AppSettingRow, UserRow

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
    setup_code: str | None = Field(
        default=None,
        max_length=256,
        description="Código de primeiro uso (`docker exec <container> cat /data/secrets/SETUP_CODE`). "
        "Dispensado com o APP_TOKEN no X-API-Token.",
    )


# Chave fixa: o INSERT da segunda tentativa de setup bate na PK e falha.
_SENTINELA_DO_SETUP = "setup.done"


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
        # Atrás de um proxy TLS que o uvicorn não reconhece (FORWARDED_ALLOW_IPS), o
        # esquema chega como http: COOKIE_SECURE=true força o Secure.
        secure=settings.COOKIE_SECURE or request.url.scheme == "https",
        path="/",
    )


def _pode_fazer_setup(body: SetupIn, request: Request) -> bool:
    import hmac

    token = request.headers.get("x-api-token") or ""
    if token and hmac.compare_digest(token.encode(), settings.APP_TOKEN.encode()):
        return True
    codigo = (body.setup_code or "").strip()
    return bool(
        settings.SETUP_CODE
        and codigo
        and hmac.compare_digest(codigo.encode(), settings.SETUP_CODE.encode())
    )


def _origem(request: Request) -> str:
    return request.client.host if request.client else "?"


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
    from sqlalchemy.exc import IntegrityError

    if await _total_de_usuarios(session) > 0:
        raise HTTPException(status.HTTP_410_GONE, "o primeiro uso já foi feito")
    if not _pode_fazer_setup(body, request):
        await log_audit_event(
            session, action="setup.denied", actor=body.email, metadata={"origem": _origem(request)}
        )
        await session.commit()
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "código de primeiro uso ausente ou errado: "
            "docker exec <container> cat /data/secrets/SETUP_CODE",
        )
    motivo = problema_da_senha(body.password)
    if motivo:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, motivo)
    session.add(
        AppSettingRow(
            key=_SENTINELA_DO_SETUP,
            value='"admin"',
            updated_at=datetime.now(UTC),
            updated_by=body.email.strip().lower(),
        )
    )
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(status.HTTP_410_GONE, "o primeiro uso já foi feito") from e
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
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(status.HTTP_410_GONE, "o primeiro uso já foi feito") from e
    _cookie(response, request, _sessao_de(user))
    return SessaoOut(id=str(user.id), email=user.email, name=user.name, role=user.role)


def _sessao_de(user: UserRow) -> str:
    return issue_session(
        user_id=user.id, email=user.email, role=user.role, versao=user.session_version
    )


@router.post("/auth/session", response_model=SessaoOut)
async def login(
    body: LoginIn, request: Request, response: Response, session: SessionDep
) -> SessaoOut:
    email = body.email.strip().lower()
    origem = _origem(request)
    chaves = (f"par:{email}|{origem}", f"ip:{origem}")
    espera = freio.espera(*chaves)
    if espera > 0:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "muitas tentativas; espere antes de tentar de novo",
            headers={"Retry-After": str(int(espera) + 1)},
        )
    user = (await session.exec(select(UserRow).where(UserRow.email == email))).first()
    # Usuário sem senha (só token ou OIDC) também paga o scrypt: senão respondia em 5 ms
    # e o relógio contava quem existe.
    hash_alvo = user.password_hash if user is not None and user.password_hash else _HASH_FANTASMA
    ok = conferir(body.password, hash_alvo) and user is not None and bool(user.password_hash)
    if user is None or not ok or not user.active:
        freio.falhou(*chaves)
        await log_audit_event(
            session,
            action="user.login_failed",
            actor=email,
            metadata={"via": "senha", "origem": origem},
        )
        await session.commit()
        # Mesma mensagem para e-mail inexistente, senha errada e usuário desativado.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "e-mail ou senha inválidos")
    freio.acertou(*chaves)
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
    _cookie(response, request, _sessao_de(user))
    return SessaoOut(id=str(user.id), email=user.email, name=user.name, role=user.role)


@router.delete("/auth/session", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, session: SessionDep) -> Response:
    """Sai: apaga o cookie e derruba as sessões do usuário (todas, não só esta).

    Apagar só o cookie deixava o JWT valendo até expirar para quem tivesse copiado.
    Sem sessão válida, só apaga o cookie (sair nunca falha).
    """
    from uuid import UUID

    from orchestrator.auth.session import verify_session

    claims = verify_session(request.cookies.get(COOKIE_SESSAO))
    if claims:
        try:
            user = await session.get(UserRow, UUID(claims["sub"]))
        except (ValueError, KeyError):
            user = None
        if user is not None and int(claims.get("sv", 0)) == int(user.session_version or 0):
            user.session_version = int(user.session_version or 0) + 1
            session.add(user)
            await log_audit_event(
                session,
                action="user.logout",
                actor=user.email,
                resource_type="user",
                resource_id=user.id,
            )
            await session.commit()
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
