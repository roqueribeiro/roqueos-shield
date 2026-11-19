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
        "description": (
            "Detalhe de um scan, incluindo a cobertura: que scanners rodaram e quais não, "
            "e por quê."
        ),
        "inputSchema": _schema({"scan_id": _ID}, ["scan_id"]),
    },
    {
        "name": "get_findings",
        "description": (
            "Os achados de um scan. Se o scan falhou ou a cobertura veio incompleta, "
            "o resultado vem "
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
        "description": (
            "O AI Fix Bundle do scan (schema 1.0.0): o que corrigir, onde, em que ordem, "
            "e como verificar."
        ),
        "inputSchema": _schema({"scan_id": _ID}, ["scan_id"]),
    },
    {
        "name": "list_targets",
        "description": "Os alvos registrados.",
        "inputSchema": _schema({}),
    },
    {
        "name": "gate_verdict",
        "description": (
            "O veredito de gate de um scan terminado: aprovado, reprovado ou nao_medido. "
            "Por padrão só achado NOVO (que não estava no último scan completo do mesmo "
            "alvo) com severidade no limite ou acima reprova. nao_medido volta como erro: "
            "scanner que não rodou não aprova código."
        ),
        "inputSchema": _schema(
            {
                "scan_id": _ID,
                "fail_on": {
                    "type": "string",
                    "enum": ["info", "low", "medium", "high", "critical"],
                },
                "all_findings": {
                    "type": "boolean",
                    "description": "true = bloqueia também achado já conhecido",
                },
            },
            ["scan_id"],
        ),
    },
]

# Só no MCP por stdio, que roda na máquina de quem chama e enxerga o disco dela. Não
# depende das ações ligadas: escanear o próprio código não toca alvo de terceiro. O
# servidor ainda exige `scans:run` e, com REQUIRE_AUTH_REF, a referência.
FERRAMENTAS_LOCAIS: list[dict[str, Any]] = [
    {
        "name": "scan_code",
        "description": (
            "Empacota uma pasta de código local (respeitando o .gitignore, sem a pasta "
            ".git), envia ao RoqueShield e dispara o scan de código (SAST, segredos, IaC, "
            "dependências). Use antes de entregar uma mudança. Com wait_seconds > 0 espera "
            "o fim e devolve o veredito do gate; senão devolve o scan_id para get_scan e "
            "gate_verdict."
        ),
        "inputSchema": _schema(
            {
                "path": {"type": "string", "description": "pasta absoluta do código"},
                "project": {
                    "type": "string",
                    "description": "nome do projeto (padrão: nome da pasta); o mesmo nome "
                    "em todo envio, para o gate saber o que é novo",
                },
                "authorization_ref": {"type": "string", "minLength": 3},
                "fail_on": {
                    "type": "string",
                    "enum": ["info", "low", "medium", "high", "critical"],
                },
                "wait_seconds": {"type": "integer", "minimum": 0, "maximum": 1800},
            },
            ["path"],
        ),
    },
]

FERRAMENTAS_DE_ACAO: list[dict[str, Any]] = [
    {
        "name": "start_scan",
        "description": (
            "Registra o alvo e dispara um scan. Só use contra alvo que o operador está "
            "autorizado a "
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


def _empacotar_pasta(caminho: str, projeto: Any) -> tuple[Any, str]:
    """Síncrono (disco), roda numa thread. Recusa caminho relativo: o cwd do servidor MCP
    é o de quem o lançou, e "." ali escanearia a pasta errada sem avisar."""
    from pathlib import Path

    from orchestrator.cliente.empacotar import EmpacotamentoFalhou, empacotar

    raiz = Path(caminho).expanduser()
    if not raiz.is_absolute():
        raise EmpacotamentoFalhou("path precisa ser absoluto")
    nome = str(projeto or raiz.resolve().name).strip().lower()
    return empacotar(raiz), nome


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
    def __init__(
        self, api: ApiAssincrona, *, acoes: bool = False, versao: str = "", local: bool = False
    ) -> None:
        self.api = api
        self.acoes = acoes
        self.local = local
        self.versao = versao
        self._acoes_por_nome: dict[str, Callable[[dict[str, Any]], Awaitable[Any]]] = {
            "list_scans": self._list_scans,
            "get_scan": self._get_scan,
            "get_findings": self._get_findings,
            "get_ai_bundle": self._get_ai_bundle,
            "list_targets": self._list_targets,
            "start_scan": self._start_scan,
            "gate_verdict": self._gate_verdict,
            "scan_code": self._scan_code,
        }

    def ferramentas(self) -> list[dict[str, Any]]:
        return (
            FERRAMENTAS_DE_LEITURA
            + (FERRAMENTAS_LOCAIS if self.local else [])
            + (FERRAMENTAS_DE_ACAO if self.acoes else [])
        )

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

    async def _gate_verdict(self, a: dict[str, Any]) -> Any:
        fail_on = str(a.get("fail_on") or "high")
        so_novos = "false" if a.get("all_findings") else "true"
        g = await self.api.get(f"/scans/{a['scan_id']}/gate?fail_on={fail_on}&so_novos={so_novos}")
        if isinstance(g, dict) and g.get("verdict") in ("nao_medido", "em_andamento"):
            raise ErroDeFerramenta(json.dumps(g, ensure_ascii=False))
        return g

    async def _scan_code(self, a: dict[str, Any]) -> Any:
        import asyncio

        from orchestrator.cliente.empacotar import EmpacotamentoFalhou

        if not self.local:
            raise ErroDeFerramenta("scan_code só existe no MCP por stdio (roqueshield mcp)")
        enviar = getattr(self.api, "enviar_codigo", None)
        if enviar is None:
            raise ErroDeFerramenta("este cliente não sabe enviar código")
        try:
            pacote, projeto = await asyncio.to_thread(
                _empacotar_pasta, str(a["path"]), a.get("project")
            )
        except EmpacotamentoFalhou as e:
            raise ErroDeFerramenta(str(e)) from e
        envio = await enviar(projeto, pacote.dados)
        corpo: dict[str, Any] = {
            "target_id": envio["target_id"],
            "code_upload_id": envio["upload_id"],
        }
        if a.get("authorization_ref"):
            corpo["authorization_ref"] = str(a["authorization_ref"])
        scan = await self.api.post("/scans", corpo)
        espera = max(0, min(int(a.get("wait_seconds") or 0), 1800))
        if not espera:
            return {
                "scan_id": scan["id"],
                "target": envio["target_value"],
                "arquivos": pacote.arquivos,
            }
        prazo = asyncio.get_running_loop().time() + espera
        while asyncio.get_running_loop().time() < prazo:
            s = await self.api.get(f"/ui/api/scans/{scan['id']}")
            if s.get("state") in ("done", "failed", "canceled"):
                return await self._gate_verdict({**a, "scan_id": scan["id"]})
            await asyncio.sleep(5)
        raise ErroDeFerramenta(
            json.dumps(
                {"erro": f"o scan não terminou em {espera}s", "scan_id": scan["id"]},
                ensure_ascii=False,
            )
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
                    "RoqueShield: teste de segurança. "
                    "Zero achado só é limpo com coverage_complete=true. "
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
