"""FastAPI dependencies: auth (principal + RBAC), DB session, audit context.

Modelo de autenticação (backward-compatible):

1. **Token de serviço** (`APP_TOKEN`) — o token global compartilhado continua
   válido e mapeia para um `Principal` de **serviço com papel ADMIN**. É o que
   a integração RoqueShield injeta (`X-API-Token`), então nada quebra.
2. **Token por-usuário** — cada `UserRow` tem um token (hash SHA-256); o
   `Principal` carrega a identidade real (id/email) + o papel do usuário.

`require_permission(perm)` é o gate de RBAC; o `Principal` retornado também
serve como `actor` real no audit log (antes era string livre).
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPBearer
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from orchestrator.auth.session import verify_session
from orchestrator.config import settings
from orchestrator.domain.roles import Permission, Role, coerce_role, has_permission
from orchestrator.persistence.db import get_session
from orchestrator.persistence.models import UserRow

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Cookie da sessão da tela standalone (httpOnly: o JavaScript não lê, então um XSS
# não leva a sessão). O mesmo JWT do login OIDC, em outro transporte.
COOKIE_SESSAO = "rs_session"
# Cabeçalho que a tela manda em toda escrita. Navegador não deixa outro site pôr
# cabeçalho próprio num request sem preflight de CORS, e nós não liberamos CORS:
# isto é o que impede um formulário de outro site de usar o cookie (CSRF).
CABECALHO_CSRF = "X-RoqueShield"
_METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS"})

# Declarados como esquema de segurança para o Swagger mostrar o botão Authorize e
# saber pôr a credencial em toda chamada. auto_error=False: quem decide o 401 é o
# get_principal, que conhece as quatro formas de entrar.
_ESQUEMA_TOKEN = APIKeyHeader(
    name="X-API-Token",
    auto_error=False,
    scheme_name="ApiToken",
    description="Token de usuário (crie em Usuários) ou o APP_TOKEN de serviço.",
)
_ESQUEMA_BEARER = HTTPBearer(
    auto_error=False,
    scheme_name="Sessao",
    description="Sessão JWT do login OIDC.",
)


@dataclass(frozen=True)
class Principal:
    """Identidade autenticada (usuário nomeado ou principal de serviço)."""

    id: str
    email: str
    role: Role
    is_service: bool


# Principal do token de serviço (`APP_TOKEN`) — admin, sem hit no DB.
SERVICE_PRINCIPAL = Principal(id="service", email="service@local", role=Role.ADMIN, is_service=True)


def token_hash(token: str) -> str:
    """SHA-256 hex do token por-usuário (o que guardamos no DB)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def get_principal(
    session: SessionDep,
    x_api_token: Annotated[str | None, Security(_ESQUEMA_TOKEN)] = None,
    bearer: Annotated[object | None, Security(_ESQUEMA_BEARER)] = None,
    rs_session: Annotated[str | None, Cookie(alias=COOKIE_SESSAO, include_in_schema=False)] = None,
    request: Request = None,  # type: ignore[assignment]  # o FastAPI sempre injeta; None só em chamada direta
) -> Principal:
    """Resolve o `Principal` a partir das credenciais do request.

    Ordem:
    1. `X-API-Token` = `APP_TOKEN` → principal de serviço ADMIN (timing-safe, sem DB).
    2. `X-API-Token` = token por-usuário → lookup por hash.
    3. `Authorization: Bearer <session-jwt>` (login OIDC/SSO) → valida a sessão e
       **re-busca o usuário no DB** (papel/ativo correntes — revoga na hora).
    4. Cookie `rs_session` (login por senha da tela standalone) → o mesmo JWT; em
       escrita exige o cabeçalho `X-RoqueShield` (CSRF).

    401 se nenhuma credencial válida.
    """
    # 1 + 2) X-API-Token
    if x_api_token:
        if hmac.compare_digest(x_api_token, settings.APP_TOKEN):
            return SERVICE_PRINCIPAL
        user = (
            await session.exec(
                select(UserRow).where(UserRow.api_token_hash == token_hash(x_api_token))
            )
        ).first()
        if user is not None and user.active:
            return Principal(
                id=str(user.id),
                email=user.email,
                role=coerce_role(user.role),
                is_service=False,
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-API-Token inválido")

    # 3) sessão OIDC (Bearer JWT), ou 4) a mesma sessão no cookie da tela
    jwt_sessao: str | None = None
    credencial = getattr(bearer, "credentials", None)
    if credencial:
        jwt_sessao = credencial
    elif rs_session:
        # Sem request (chamada direta, fora de HTTP) conta como escrita: falha fechado.
        metodo = request.method if request is not None else "POST"
        tem_csrf = bool(request is not None and request.headers.get(CABECALHO_CSRF))
        if metodo not in _METODOS_SEGUROS and not tem_csrf:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"escrita por cookie exige o cabeçalho {CABECALHO_CSRF}",
            )
        jwt_sessao = rs_session
    if jwt_sessao is not None:
        claims = verify_session(jwt_sessao)
        if claims:
            try:
                user = await session.get(UserRow, UUID(claims["sub"]))
            except (ValueError, KeyError):
                user = None
            # Versão da sessão: logout, troca de senha e desativação sobem a do usuário
            # e derrubam todo JWT emitido antes. JWT antigo sem `sv` vale como 0.
            if (
                user is not None
                and user.active
                and int(claims.get("sv", 0)) == int(user.session_version or 0)
            ):
                return Principal(
                    id=str(user.id),
                    email=user.email,
                    role=coerce_role(user.role),
                    is_service=False,
                )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="sessão inválida ou expirada"
        )

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="credenciais ausentes")


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require_permission(permission: Permission) -> Callable[[Principal], Awaitable[Principal]]:
    """Factory de dependency: exige `permission` do principal autenticado.

    Retorna o `Principal` (pra o endpoint usar como `actor`), ou 403.
    """

    async def _dep(principal: PrincipalDep) -> Principal:
        if not has_permission(principal.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"permissão insuficiente ({permission.value})",
            )
        return principal

    return _dep


# Gates de RBAC prontos pra usar como default de parâmetro nos routers:
#   async def endpoint(..., _principal: Principal = RequireScansRead): ...
RequireScansRun = Depends(require_permission(Permission.SCANS_RUN))
RequireScansRead = Depends(require_permission(Permission.SCANS_READ))
RequireUsersManage = Depends(require_permission(Permission.USERS_MANAGE))
RequireAuditRead = Depends(require_permission(Permission.AUDIT_READ))
RequireConfigManage = Depends(require_permission(Permission.CONFIG_MANAGE))


# --- backward-compat -------------------------------------------------------
# Endpoints legados usam `_token: TokenDep` só pra exigir autenticação. Mantido
# funcionando (agora aceita token de serviço OU de usuário); novos endpoints
# devem usar `PrincipalDep` / `require_permission` / os gates acima.
async def require_token(principal: PrincipalDep) -> str:
    return principal.email


TokenDep = Annotated[str, Depends(require_token)]
