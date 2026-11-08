"""Servidor MCP do RoqueShield: o protocolo, sem transporte.

Escrito à mão, e não com o SDK `mcp`: o lockfile já carrega duas versões dele
(a 1.x do semgrep e a 2.x do arize-phoenix, em extras diferentes), e a resolução não
fecha com uma terceira exigência. O que o RoqueShield precisa do protocolo é pouco
(initialize, ping, tools/list, tools/call), e cabe aqui com teste.

Cada ferramenta chama a API REST com a credencial de quem chamou, então vale o RBAC
de sempre. Duas regras que a proposta em docs/INTEGRATIONS.md já pedia:

1. **Ferramenta não devolve vazio quando o scan falhou.** Achados e bundle de um scan
   que falhou ou que veio com cobertura incompleta voltam com `isError: true` e o
   motivo, junto com o que existe. Um agente que lê lista vazia conclui "limpo".
2. **Disparar scan é ação com peso legal.** `start_scan` só aparece com as ações
   ligadas, e exige `authorization_ref`.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

VERSOES = ("2025-06-18", "2025-03-26", "2024-11-05")
NOME = "roqueshield"


class ApiAssincrona(Protocol):
    async def get(self, caminho: str) -> Any: ...
    async def post(self, caminho: str, corpo: Any = None) -> Any: ...


class ErroDeFerramenta(Exception):
    """Vira `isError: true` no resultado, não erro de protocolo."""


def _schema(props: dict[str, Any], obrigatorios: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": obrigatorios or [],
        "additionalProperties": False,
    }


_ID = {"type": "string", "description": "id do scan (UUID)"}

FERRAMENTAS_DE_LEITURA: list[dict[str, Any]] = [
    {
        "name": "list_scans",
        "description": "Os scans mais recentes, com estado, fase e contagem por severidade.",
        "inputSchema": _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 200}}),
    },
    {
        "name": "get_scan",
        "description": "Detalhe de um scan, incluindo a cobertura: que scanners rodaram e quais não, e por quê.",
        "inputSchema": _schema({"scan_id": _ID}, ["scan_id"]),
    },
    {
        "name": "get_findings",
        "description": (
            "Os achados de um scan. Se o scan falhou ou a cobertura veio incompleta, o resultado vem "
            "marcado como erro: zero achado de scanner que não rodou não é alvo limpo."
        ),
        "inputSchema": _schema(
            {
                "scan_id": _ID,
                "severity": {
                    "type": "string",
                    "enum": ["info", "low", "medium", "high", "critical"],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            },
            ["scan_id"],
        ),
    },
    {
        "name": "get_ai_bundle",
        "description": "O AI Fix Bundle do scan (schema 1.0.0): o que corrigir, onde, em que ordem, e como verificar.",
        "inputSchema": _schema({"scan_id": _ID}, ["scan_id"]),
    },
    {
        "name": "list_targets",
        "description": "Os alvos registrados.",
        "inputSchema": _schema({}),
    },
]

FERRAMENTAS_DE_ACAO: list[dict[str, Any]] = [
    {
        "name": "start_scan",
        "description": (
            "Registra o alvo e dispara um scan. Só use contra alvo que o operador está autorizado a "
            "testar; a referência da autorização é obrigatória e vai para a trilha de auditoria."
        ),
        "inputSchema": _schema(
            {
                "target": {
                    "type": "string",
                    "description": "URL, domínio, host, imagem ou repositório",
                },
                "asset_type": {
                    "type": "string",
                    # Sem k8s_resource: nenhum scanner do pipeline aceita o tipo, e o
                    # POST /scans o recusa com 422.
                    "enum": ["url", "domain", "host", "port", "image", "repo"],
                },
                # Os profiles que o pipeline executa (PERFIS_DO_SCAN). `exposure` roda o
                # pipeline OSINT sobre o domínio do alvo.
                "profile": {
                    "type": "string",
                    "enum": ["web", "network", "full", "active", "exposure"],
                },
                "authorization_ref": {
                    "type": "string",
                    "minLength": 3,
                    "description": "ticket ou mudança que autoriza",
                },
            },
            ["target", "authorization_ref"],
        ),
    },
]


def _incompleto(scan: dict[str, Any]) -> str | None:
    if scan.get("state") == "failed":
        return "o scan FALHOU"
    if scan.get("state") != "done":
        return f"o scan ainda não terminou (estado {scan.get('state')})"
    if not scan.get("coverage_complete"):
        pulados = scan.get("scanners_skipped") or {}
        lista = "; ".join(f"{k}: {v}" for k, v in pulados.items()) or "sem detalhe"
        return f"cobertura INCOMPLETA, estes vetores não foram verificados: {lista}"
    return None


class Servidor:
    def __init__(self, api: ApiAssincrona, *, acoes: bool = False, versao: str = "") -> None:
        self.api = api
        self.acoes = acoes
        self.versao = versao
        self._acoes_por_nome: dict[str, Callable[[dict[str, Any]], Awaitable[Any]]] = {
            "list_scans": self._list_scans,
            "get_scan": self._get_scan,
            "get_findings": self._get_findings,
            "get_ai_bundle": self._get_ai_bundle,
            "list_targets": self._list_targets,
            "start_scan": self._start_scan,
        }

    def ferramentas(self) -> list[dict[str, Any]]:
        return FERRAMENTAS_DE_LEITURA + (FERRAMENTAS_DE_ACAO if self.acoes else [])

    # --- ferramentas -----------------------------------------------------------

    async def _list_scans(self, a: dict[str, Any]) -> Any:
        return await self.api.get(f"/ui/api/scans?limit={int(a.get('limit', 20))}")

    async def _get_scan(self, a: dict[str, Any]) -> Any:
        return await self.api.get(f"/ui/api/scans/{a['scan_id']}")

    async def _get_findings(self, a: dict[str, Any]) -> Any:
        scan = await self.api.get(f"/ui/api/scans/{a['scan_id']}")
        q = f"/ui/api/findings?scan_id={a['scan_id']}&limit={int(a.get('limit', 200))}"
        if a.get("severity"):
            q += f"&severity={a['severity']}"
        achados = await self.api.get(q)
        motivo = _incompleto(scan)
        if motivo:
            raise ErroDeFerramenta(
                json.dumps({"erro": motivo, "achados_parciais": achados}, ensure_ascii=False)
            )
        return achados

    async def _get_ai_bundle(self, a: dict[str, Any]) -> Any:
        scan = await self.api.get(f"/ui/api/scans/{a['scan_id']}")
        bundle = await self.api.get(f"/reports/{a['scan_id']}/ai-bundle")
        motivo = _incompleto(scan)
        if motivo:
            raise ErroDeFerramenta(
                json.dumps({"erro": motivo, "bundle_parcial": bundle}, ensure_ascii=False)
            )
        return bundle

    async def _list_targets(self, a: dict[str, Any]) -> Any:
        return await self.api.get("/targets")

    async def _start_scan(self, a: dict[str, Any]) -> Any:
        if not self.acoes:
            raise ErroDeFerramenta("ações desligadas neste servidor MCP")
        ref = str(a.get("authorization_ref") or "").strip()
        if len(ref) < 3:
            raise ErroDeFerramenta("authorization_ref é obrigatório para disparar scan")
        alvo = await self.api.post(
            "/targets", {"asset_type": a.get("asset_type", "url"), "value": a["target"]}
        )
        return await self.api.post(
            "/scans",
            {"target_id": alvo["id"], "profile": a.get("profile", "web"), "authorization_ref": ref},
        )

    # --- protocolo -------------------------------------------------------------

    async def tratar(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        """Uma mensagem JSON-RPC. Notificação (sem id) não tem resposta."""
        metodo = msg.get("method")
        mid = msg.get("id")
        if mid is None:
            return None
        try:
            resultado = await self._despachar(metodo, msg.get("params") or {})
        except _ErroRpc as e:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": e.codigo, "message": e.mensagem}}
        return {"jsonrpc": "2.0", "id": mid, "result": resultado}

    async def _despachar(self, metodo: Any, p: dict[str, Any]) -> Any:
        if metodo == "initialize":
            pedida = p.get("protocolVersion")
            return {
                "protocolVersion": pedida if pedida in VERSOES else VERSOES[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": NOME, "version": self.versao},
                "instructions": (
                    "RoqueShield: teste de segurança. Zero achado só é limpo com coverage_complete=true. "
                    "Ferramenta que volta com isError explica o que não foi verificado."
                ),
            }
        if metodo == "ping":
            return {}
        if metodo == "tools/list":
            return {"tools": self.ferramentas()}
        if metodo == "tools/call":
            nome = str(p.get("name") or "")
            if nome not in {f["name"] for f in self.ferramentas()}:
                raise _ErroRpc(-32602, f"ferramenta desconhecida: {nome}")
            args = p.get("arguments") or {}
            try:
                dado = await self._acoes_por_nome[nome](args)
            except ErroDeFerramenta as e:
                return {"content": [{"type": "text", "text": str(e)}], "isError": True}
            except KeyError as e:
                return {
                    "content": [{"type": "text", "text": f"argumento faltando: {e}"}],
                    "isError": True,
                }
            except Exception as e:  # noqa: BLE001  erro da API vira erro da ferramenta, legível
                return {
                    "content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}],
                    "isError": True,
                }
            return {
                "content": [{"type": "text", "text": json.dumps(dado, ensure_ascii=False)}],
                "isError": False,
            }
        raise _ErroRpc(-32601, f"método não suportado: {metodo}")


class _ErroRpc(Exception):
    def __init__(self, codigo: int, mensagem: str) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
