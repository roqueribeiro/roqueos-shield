"""`roqueshield`: a CLI que fala com um RoqueShield rodando.

Diferente do `cai` (que roda o pipeline no próprio processo, dentro da imagem), esta
é cliente: serve no notebook, no CI e dentro do container (`docker exec`).

Códigos de saída, o contrato para pipeline:

    0  terminou, cobertura completa, nada no limite do --fail-on
    1  terminou, cobertura completa, e há achado no limite do --fail-on ou acima
    2  erro de uso, de conexão ou de credencial
    3  o scan falhou ou a cobertura veio INCOMPLETA (algum scanner não rodou)

O 3 vence o 0 e o 1 de propósito: zero achado com scanner que não rodou não é alvo
limpo, é vetor não verificado (a regra do silêncio do RoqueShield, levada ao CI).
"""

from __future__ import annotations

import getpass
import json
import sys
import time
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from orchestrator.cliente import api as apimod

app = typer.Typer(
    name="roqueshield",
    help="Cliente do RoqueShield: scans, achados, relatórios e o servidor MCP.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
scan_app = typer.Typer(help="Disparar, acompanhar e apagar scans.", no_args_is_help=True)
settings_app = typer.Typer(help="Configuração de IA e de escopo.", no_args_is_help=True)
app.add_typer(scan_app, name="scan")
app.add_typer(settings_app, name="settings")

out = Console()
err = Console(stderr=True)

SEVERIDADES = ["info", "low", "medium", "high", "critical"]
FINAIS = {"done", "failed", "canceled"}


class Saida:
    OK = 0
    ACHADO = 1
    USO = 2
    INCOMPLETO = 3


def _api() -> apimod.Api:
    try:
        return apimod.Api(apimod.carregar())
    except apimod.SemConfig as e:
        err.print(f"[red]{e}[/red]")
        raise typer.Exit(Saida.USO) from e


def _chamar(fn: Any, *a: Any, **kw: Any) -> Any:
    try:
        return fn(*a, **kw)
    except apimod.ErroDaApi as e:
        err.print(f"[red]a API recusou ({e.status}): {e.detalhe}[/red]")
        raise typer.Exit(Saida.USO) from e
    except Exception as e:  # httpx: conexão recusada, DNS, timeout
        err.print(f"[red]sem conexão com o RoqueShield: {type(e).__name__}: {e}[/red]")
        raise typer.Exit(Saida.USO) from e


def codigo_de_saida(scan: dict[str, Any], fail_on: str | None) -> int:
    """A regra dos códigos, isolada para teste."""
    if scan.get("state") != "done" or not scan.get("coverage_complete"):
        return Saida.INCOMPLETO
    if fail_on:
        limite = SEVERIDADES.index(fail_on)
        cont = scan.get("severity_counts") or {}
        if any(cont.get(s, 0) > 0 for s in SEVERIDADES[limite:]):
            return Saida.ACHADO
    return Saida.OK


def _resumo(scan: dict[str, Any]) -> None:
    cont = scan.get("severity_counts") or {}
    alvo = (scan.get("target") or {}).get("value", "?")
    out.print(f"[bold]{alvo}[/bold]  estado={scan.get('state')}  scan={scan.get('id')}")
    out.print("  " + "  ".join(f"{s}={cont.get(s, 0)}" for s in reversed(SEVERIDADES)))
    if scan.get("scanners_ran"):
        out.print(f"  rodaram: {', '.join(scan['scanners_ran'])}")
    pulados = scan.get("scanners_skipped") or {}
    for nome, motivo in pulados.items():
        out.print(f"  [yellow]não rodou: {nome}: {motivo}[/yellow]")
    if scan.get("state") == "done" and not scan.get("coverage_complete"):
        out.print(
            "  [yellow]cobertura INCOMPLETA: zero achado aqui não quer dizer alvo limpo[/yellow]"
        )


def _esperar(api: apimod.Api, scan_id: str, intervalo: float, prazo: float) -> dict[str, Any]:
    inicio = time.monotonic()
    ultima = None
    while True:
        s = _chamar(api.get, f"/ui/api/scans/{scan_id}")
        fase = (s.get("current_phase"), s.get("phase_progress"))
        if fase != ultima:
            ultima = fase
            pct = f" {fase[1]}%" if fase[1] is not None else ""
            err.print(f"  fase: {fase[0] or s.get('state')}{pct}")
        if s.get("state") in FINAIS:
            return s
        if time.monotonic() - inicio > prazo:
            err.print(f"[red]o scan não terminou em {int(prazo)}s[/red]")
            raise typer.Exit(Saida.INCOMPLETO)
        time.sleep(intervalo)


@app.command()
def login(
    server: Annotated[
        str, typer.Option("--server", "-s", help="Endereço do shield, ex.: http://localhost:8080")
    ],
    token: Annotated[
        str | None, typer.Option(help="Token de usuário. Sem ele, a CLI pergunta sem eco.")
    ] = None,
) -> None:
    """Guarda o endereço e o token (crie o token na tela, em Usuários, ou em POST /users)."""
    tok = token or getpass.getpass("Token: ")
    cfg = apimod.Config(server.rstrip("/"), tok.strip())
    eu = _chamar(apimod.Api(cfg).get, "/auth/session")
    arq = apimod.salvar(cfg)
    out.print(f"ok: {eu.get('email')} ({eu.get('role')}) em {cfg.servidor}. Configuração em {arq}")


@app.command()
def status() -> None:
    """Versão do shield, quem está logado e o estado de cada dependência."""
    api = _api()
    h = _chamar(api.get, "/health")
    eu = _chamar(api.get, "/auth/session")
    out.print(
        f"RoqueShield {h.get('version')} em {api.cfg.servidor}: {eu.get('email')} ({eu.get('role')})"
    )
    try:
        full = api.get("/health/full")
        out.print(f"  geral: {full.get('overall')}")
        for item in full.get("components") or []:
            out.print(f"  {item.get('name')}: {item.get('status')}")
    except Exception as e:  # noqa: BLE001  /health/full pode exigir outro papel
        err.print(f"[dim]saúde detalhada indisponível: {type(e).__name__}[/dim]")


@scan_app.command("start")
def scan_start(
    alvo: Annotated[str, typer.Argument(help="URL, domínio, host, imagem ou repositório")],
    tipo: Annotated[str, typer.Option("--type", help="url|domain|host|port|image|repo")] = "url",
    perfil: Annotated[
        str,
        typer.Option(
            "--profile",
            help="web|network|full|active (full e active ligam o ZAP active scan)",
        ),
    ] = "web",
    scanner: Annotated[
        list[str] | None, typer.Option("--scanner", help="Repetir para mais de um")
    ] = None,
    auth_ref: Annotated[
        str | None, typer.Option("--auth-ref", help="Referência da autorização (ticket)")
    ] = None,
    esperar: Annotated[bool, typer.Option("--wait/--no-wait", help="Acompanha até o fim")] = False,
    fail_on: Annotated[
        str | None, typer.Option("--fail-on", help="info|low|medium|high|critical")
    ] = None,
    intervalo: Annotated[float, typer.Option(help="Segundos entre leituras")] = 5.0,
    prazo: Annotated[float, typer.Option(help="Segundos até desistir")] = 7200.0,
) -> None:
    """Registra o alvo e dispara o scan. Com --wait, sai pelo contrato de códigos."""
    if fail_on and fail_on not in SEVERIDADES:
        err.print(f"[red]--fail-on aceita: {', '.join(SEVERIDADES)}[/red]")
        raise typer.Exit(Saida.USO)
    api = _api()
    alvo_criado = _chamar(api.post, "/targets", {"asset_type": tipo, "value": alvo})
    corpo: dict[str, Any] = {"target_id": alvo_criado["id"], "profile": perfil}
    if scanner:
        corpo["scanners"] = scanner
    if auth_ref:
        corpo["authorization_ref"] = auth_ref
    scan = _chamar(api.post, "/scans", corpo)
    out.print(f"scan {scan['id']} criado ({perfil})")
    if not esperar:
        return
    final = _esperar(api, scan["id"], intervalo, prazo)
    _resumo(final)
    raise typer.Exit(codigo_de_saida(final, fail_on))


@scan_app.command("watch")
def scan_watch(
    scan_id: str,
    fail_on: Annotated[str | None, typer.Option("--fail-on")] = None,
    intervalo: Annotated[float, typer.Option()] = 5.0,
    prazo: Annotated[float, typer.Option()] = 7200.0,
) -> None:
    """Acompanha um scan até o fim e sai pelo contrato de códigos."""
    final = _esperar(_api(), scan_id, intervalo, prazo)
    _resumo(final)
    raise typer.Exit(codigo_de_saida(final, fail_on))


@scan_app.command("list")
def scan_list(limite: Annotated[int, typer.Option("--limit")] = 20) -> None:
    """Os scans mais recentes."""
    linhas = _chamar(_api().get, f"/ui/api/scans?limit={limite}")
    t = Table("scan", "alvo", "estado", "fase", "achados")
    for s in linhas:
        cont = s.get("severity_counts") or {}
        t.add_row(
            s["id"],
            s.get("target_value") or "?",
            s.get("state"),
            s.get("current_phase") or "",
            str(sum(cont.values())),
        )
    out.print(t)


@scan_app.command("show")
def scan_show(scan_id: str, como_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Detalhe de um scan: estado, contagem por severidade e cobertura."""
    s = _chamar(_api().get, f"/ui/api/scans/{scan_id}")
    if como_json:
        out.print_json(json.dumps(s))
    else:
        _resumo(s)


@scan_app.command("rm")
def scan_rm(
    scan_id: str, sim: Annotated[bool, typer.Option("--yes", help="Não pergunta")] = False
) -> None:
    """Apaga um scan e os achados dele (fica na trilha de auditoria)."""
    if not sim and not typer.confirm(f"apagar o scan {scan_id}?"):
        raise typer.Exit(Saida.USO)
    _chamar(_api().delete, f"/scans/{scan_id}")
    out.print("apagado")


@app.command()
def findings(
    scan_id: str,
    severidade: Annotated[str | None, typer.Option("--severity")] = None,
    limite: Annotated[int, typer.Option("--limit")] = 200,
    como_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Os achados de um scan."""
    q = f"/ui/api/findings?scan_id={scan_id}&limit={limite}"
    if severidade:
        q += f"&severity={severidade}"
    linhas = _chamar(_api().get, q)
    if como_json:
        out.print_json(json.dumps(linhas))
        return
    t = Table("severidade", "título", "ferramenta", "onde")
    for f in linhas:
        t.add_row(
            f.get("severity", ""),
            f.get("title", ""),
            f.get("source_tool", ""),
            str(f.get("location") or f.get("url") or ""),
        )
    out.print(t)


FORMATOS = {
    "bundle": ("/reports/{id}/ai-bundle", "json"),
    "compliance": ("/reports/{id}/compliance", "json"),
    "html": ("/reports/{id}", "html"),
    "executive": ("/reports/{id}/executive", "html"),
}


@app.command()
def report(
    scan_id: str,
    formato: Annotated[
        str, typer.Option("--format", help="bundle|compliance|html|executive")
    ] = "bundle",
    saida: Annotated[
        Path | None, typer.Option("--output", "-o", help="Arquivo; sem ele, stdout")
    ] = None,
) -> None:
    """Baixa um relatório. `bundle` é o AI Fix Bundle que outro agente consome para corrigir."""
    if formato not in FORMATOS:
        err.print(f"[red]--format aceita: {', '.join(FORMATOS)}[/red]")
        raise typer.Exit(Saida.USO)
    caminho, tipo = FORMATOS[formato]
    dado = _chamar(_api().get, caminho.format(id=scan_id))
    texto = json.dumps(dado, indent=2, ensure_ascii=False) if tipo == "json" else str(dado)
    if saida:
        saida.write_text(texto, encoding="utf-8")
        err.print(f"escrito {saida}")
    else:
        sys.stdout.write(texto + ("\n" if not texto.endswith("\n") else ""))


@settings_app.command("ai")
def settings_ai() -> None:
    """A configuração de IA em uso (sem chave)."""
    out.print_json(json.dumps(_chamar(_api().get, "/settings/ai")))


@settings_app.command("scope")
def settings_scope(
    allow: Annotated[
        list[str] | None,
        typer.Option(
            "--allow",
            help="Substitui a TARGET_ALLOWLIST inteira (repetir; host, IP, CIDR, *.dominio). "
            "Com LAB_ONLY, libera rede interna; link-local nunca, loopback só pelo endereço",
        ),
    ] = None,
    exigir_ref: Annotated[
        bool | None,
        typer.Option(
            "--require-auth-ref/--no-require-auth-ref",
            help="Exige authorization_ref em todo scan (REQUIRE_AUTH_REF)",
        ),
    ] = None,
) -> None:
    """Mostra o escopo; com opções, troca. Ler e trocar exigem config:manage.

    Campo definido por variável de ambiente fica travado e volta em `locked`: a troca
    por aqui não vale para ele.
    """
    api = _api()
    corpo: dict[str, Any] = {}
    if allow is not None:
        corpo["allowlist"] = allow
    if exigir_ref is not None:
        corpo["requireAuthRef"] = exigir_ref
    dado = (
        _chamar(api.put, "/settings/scope", corpo) if corpo else _chamar(api.get, "/settings/scope")
    )
    out.print_json(json.dumps(dado))


@app.command("reset-password")
def reset_password(
    email: Annotated[str, typer.Argument(help="E-mail da conta (ex.: o admin esquecido)")],
) -> None:
    """Troca a senha de uma conta. Pede a senha nova sem eco.

    É o caminho de quem esqueceu a senha do admin: dentro do container a CLI já usa o
    APP_TOKEN, então `docker exec -it roqueshield roqueshield reset-password admin@x`
    resolve sem copiar token nenhum para a tela.
    """
    api = _api()
    alvo = email.strip().lower()
    usuarios = _chamar(api.get, "/users")
    conta = next((u for u in usuarios if u.get("email") == alvo), None)
    if conta is None:
        err.print(f"[red]nenhuma conta com o e-mail {alvo}[/red]")
        raise typer.Exit(Saida.USO)
    senha = getpass.getpass("Senha nova (10+ caracteres): ")
    if senha != getpass.getpass("De novo: "):
        err.print("[red]as duas não batem; nada foi trocado[/red]")
        raise typer.Exit(Saida.USO)
    _chamar(api.put, f"/users/{conta['id']}/password", {"password": senha})
    out.print(f"senha de {alvo} trocada; as sessões abertas dessa conta foram encerradas")


@app.command()
def logs(
    servico: Annotated[str, typer.Argument(help="orchestrator|worker|redis|zap")],
    seguir: Annotated[bool, typer.Option("--follow", "-f")] = False,
    ultimas: Annotated[int, typer.Option("--tail")] = 100,
) -> None:
    """Log de um serviço do container (credencial já vem redigida)."""
    api = _api()
    desde: str | None = None
    while True:
        q = f"/system/logs/{servico}?tail={ultimas}" + (f"&since={desde}" if desde else "")
        r = _chamar(api.get, q)
        for linha in r.get("lines", []):
            sys.stdout.write(f"{linha['ts']} {linha['text']}\n")
            desde = linha["ts"] or desde
        sys.stdout.flush()
        if not seguir:
            return
        time.sleep(2)


@app.command()
def mcp(
    server: Annotated[
        str | None, typer.Option("--server", help="Sobrescreve o endereço salvo")
    ] = None,
) -> None:
    """Servidor MCP por stdio, para Claude Desktop, Claude Code ou Cursor."""
    from orchestrator.cliente.mcp_stdio import rodar

    cfg = apimod.carregar()
    if server:
        cfg = apimod.Config(server.rstrip("/"), cfg.token)
    rodar(cfg)


def main() -> None:
    # Sem prog_name, a ajuda dizia `python -m orchestrator.cliente.cli`.
    app(prog_name="roqueshield")


if __name__ == "__main__":
    main()
