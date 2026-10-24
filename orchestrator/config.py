"""Application config — pydantic-settings."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # AI
    LLM_MODEL: str = "anthropic/claude-opus-4-7"
    LLM_FALLBACK_MODEL: str = "anthropic/claude-haiku-4-5-20251001"
    # api_base aplicado quando o LLM_MODEL é OpenAI-compat local (LM Studio, Ollama OpenAI mode).
    # Vazio = não passa api_base, usa o default do provider (Anthropic/OpenAI cloud).
    LLM_API_BASE: str = ""
    # api_key específico para o backend local. LM Studio ignora — qualquer string serve.
    # Se vazio + LLM_API_BASE setado, fallback "lm-studio".
    LLM_API_KEY: str = ""
    # SEC-03: quando o modelo primário é LOCAL (soberania de dados) e falha, o
    # gateway pode cair no LLM_FALLBACK_MODEL cloud — o que manda os findings pro
    # provider externo. Isso fura o isolamento que o modo local existe pra garantir.
    # True mantém o fallback (com log de aviso); em ambiente regulado, defina False
    # para PROIBIR o cruzamento local→cloud (o scan falha em vez de vazar).
    ALLOW_CLOUD_FALLBACK: bool = True
    # Modelo do LOOP AGÊNTICO (investigação). Separado do LLM_MODEL de propósito:
    # a triagem em massa pode rodar local barato (soberania), mas o loop com
    # ferramenta exige raciocínio e contexto grande — Qwen 27B q4 com 8-16k satura
    # em poucos turnos. Vazio = usa o LLM_MODEL.
    LLM_INVESTIGATION_MODEL: str = ""
    # Liga o loop agêntico da investigação (ReAct com ferramenta real no Kali).
    # A coleira (fase/escopo/anti-injeção/dry_run) vale sempre; ver
    # `orchestrator.ai.agentic.executor`. False volta ao parecer de um prompt só.
    AGENT_ENABLED: bool = True
    # Onde o comando do agente roda: "auto" (default: Kali se o container existir,
    # senão in-process), "kali" (isolado) ou "local". O stack que o RoqueShield
    # publica NÃO sobe o kali-toolbox — sem o modo local o agente não rodaria lá.
    # A coleira do executor é idêntica nos dois modos.
    AGENT_EXECUTOR: str = "auto"
    # Aliases legados (mantidos por compatibilidade, não usados pelo gateway)
    LLM_LOCAL_BASE_URL: str = "http://ollama:11434/v1"
    LLM_LOCAL_MODEL: str = "ollama/qwen2.5:32b-instruct-q4_K_M"

    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""

    # DB
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/cai.db"

    # Redis (Fase 2+)
    REDIS_URL: str = "redis://redis:6379/0"

    # Scanners
    # Ruleset do Semgrep embarcado na imagem (semgrep-rules, LGPL-2.1, pinado no
    # Dockerfile). Preferido sobre os packs `p/...` do registry porque funciona SEM
    # egress — num banco a rede é restrita, e sem alcançar o registry o semgrep sai
    # com código 0 e ZERO regras. Aponte para outro caminho se você mantém um
    # ruleset próprio; vazio ou inexistente cai nos packs do registry.
    SEMGREP_RULES_DIR: str = "/opt/semgrep-rules"
    ZAP_BASE_URL: str = "http://zap:8090"
    ZAP_API_KEY: str = ""
    TRIVY_SERVER_URL: str = "http://trivy:4954"

    # Greenbone (Fase 3, opt-in)
    GREENBONE_HOST: str = ""
    GREENBONE_PORT: int = 9390
    GREENBONE_USERNAME: str = "admin"
    GREENBONE_PASSWORD: str = ""

    # OSINT (Fase 2.5)
    GITHUB_TOKEN: str = ""
    SHODAN_API_KEY: str = ""
    CENSYS_API_ID: str = ""
    CENSYS_API_SECRET: str = ""

    # DefectDojo (Fase 5, opt-in)
    DEFECTDOJO_URL: str = ""
    DEFECTDOJO_API_KEY: str = ""

    # Phoenix tracing (Fase 4, opt-in)
    # Tracing Phoenix é opt-in de verdade: o endpoint tem default, então era ele que
    # "ligava" o tracing em todo boot e logava phoenix.imports_missing sem o extra.
    PHOENIX_ENABLED: bool = False
    PHOENIX_COLLECTOR_ENDPOINT: str = "http://phoenix:6006/v1/traces"

    # API auth (token simples; pentester comercial num engagement)
    APP_TOKEN: str = "dev-changeme"  # token simples API; trocar em prod
    # SEC-01: o APP_TOKEN mapeia para um principal de serviço ADMIN e é a chave de
    # sessão no fallback. Subir com o token de exemplo entrega admin a quem lê o
    # repo. O boot recusa isso (ver `insecure_boot_errors`); em dev local, para usar
    # o token de exemplo de propósito, setar ALLOW_INSECURE_APP_TOKEN=true.
    ALLOW_INSECURE_APP_TOKEN: bool = False
    # SEC-07: a trilha de auditoria só é imutável no Postgres COM as migrations
    # aplicadas (o trigger append-only da 0004 é PG-only). No default SQLite, o
    # audit_log é editável. True recusa subir sem trilha imutável (prod regulado).
    REQUIRE_IMMUTABLE_AUDIT: bool = False

    # Compliance gates — defaults seguros (lab-only).
    # Em prod regulado: LAB_ONLY=true + TARGET_ALLOWLIST=[escopo escrito do engagement]
    # + REQUIRE_AUTH_REF=true (forca operador a referenciar ticket/aprovacao no scan).
    LAB_ONLY: bool = True
    # Armazenado como string (CSV ou JSON-array); acessar via `.target_allowlist`.
    # Aceita: "juice-shop,dvwa,10.0.0.0/8" OU ["juice-shop","dvwa","10.0.0.0/8"]
    TARGET_ALLOWLIST: str = ""
    REQUIRE_AUTH_REF: bool = False

    # OIDC / SSO (Fase 6). Quando OIDC_ISSUER + CLIENT_ID + CLIENT_SECRET estão
    # setados, o login via IdP (Entra ID / Keycloak / Okta) é habilitado.
    OIDC_ISSUER: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_REDIRECT_URI: str = ""
    # Papel atribuído a um usuário recém-provisionado pelo SSO (fail-closed: viewer).
    OIDC_DEFAULT_ROLE: str = "viewer"
    # Chave HMAC pra assinar a sessão (JWT HS256). Vazio → cai no APP_TOKEN.
    SESSION_SECRET: str = ""
    SESSION_TTL_HOURS: int = 12

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # Reports
    REPORTS_DIR: Path = Path("./reports")

    @property
    def target_allowlist(self) -> list[str]:
        """Parseia TARGET_ALLOWLIST de string pra list. Aceita CSV ou JSON array.

        Ambos validos:
            TARGET_ALLOWLIST=juice-shop,dvwa,10.0.0.0/8
            TARGET_ALLOWLIST=["juice-shop","dvwa","10.0.0.0/8"]
        """
        raw = self.TARGET_ALLOWLIST.strip()
        if not raw:
            return []
        if raw.startswith("[") and raw.endswith("]"):
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                raise ValueError("TARGET_ALLOWLIST JSON deve ser array")
            return [str(x) for x in parsed]
        return [x.strip() for x in raw.split(",") if x.strip()]


# Tokens de exemplo que NÃO podem valer num deploy real (SEC-01).
_INSECURE_APP_TOKENS: frozenset[str] = frozenset(
    {"", "dev-changeme", "dev-changeme-with-strong-random", "changeme", "change-me"}
)


def insecure_boot_errors(s: Settings) -> list[str]:
    """Retorna a lista de problemas de segurança que impedem um boot seguro.

    Hoje cobre o APP_TOKEN de exemplo (SEC-01). Vazio no fim para um boot seguro.
    O guard é aplicado no lifespan (`orchestrator.main`); `ALLOW_INSECURE_APP_TOKEN`
    é o escape explícito para dev local.
    """
    errors: list[str] = []
    if s.ALLOW_INSECURE_APP_TOKEN:
        return errors
    if s.APP_TOKEN.strip().lower() in _INSECURE_APP_TOKENS:
        errors.append(
            "APP_TOKEN está com um valor de exemplo/vazio — ele concede ADMIN de serviço. "
            "Defina um APP_TOKEN forte (ex.: `openssl rand -hex 32`) ou, só em dev local, "
            "ALLOW_INSECURE_APP_TOKEN=true."
        )
    if s.REQUIRE_IMMUTABLE_AUDIT and audit_is_mutable(s):
        errors.append(
            "REQUIRE_IMMUTABLE_AUDIT=true mas o banco é SQLite — o trigger append-only "
            "do audit_log é Postgres-only, então a trilha seria editável. Use Postgres "
            "com `alembic upgrade head`."
        )
    return errors


def audit_is_mutable(s: Settings) -> bool:
    """True quando a trilha de auditoria NÃO tem garantia de imutabilidade.

    O trigger `audit_log_no_update` (migration 0004) existe só no Postgres. Em
    SQLite — o default — o audit_log é uma tabela comum e pode ser editada.
    """
    return s.DATABASE_URL.startswith("sqlite")


settings = Settings()
