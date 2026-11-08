"""C2: Containers."""

from .c4lib import *

SAIDA = "containers"


def draw(theme):
    c = Canvas(1852, 990, theme)
    P = PALETTE
    title_block(
        c,
        "RoqueShield: containers",
        tr(
            "Cada caixa é um processo com imagem própria. Tudo dentro da fronteira sobe "
            "como uma stack Docker só, provisionada pelo RoqueOS ou por docker compose. "
            "Serviço marcado opt-in não sobe por padrão.",
            "Each box is a process with its own image. Everything inside the boundary "
            "comes up as one Docker stack, provisioned by RoqueOS or by docker compose. "
            "Services marked opt-in do not start by default.",
        ),
        level="C2  ·  CONTAINERS",
    )
    brand(c)

    # ---------- coluna A: quem entra
    sA = c.slot()
    (ros, cli, ag), _ = stack_col(
        c,
        70,
        228,
        262,
        [
            dict(
                title="RoqueOS Server",
                tech="NestJS · dockerode",
                color=P["accent"],
                desc=tr(
                    "Provisiona a stack, guarda o token cifrado em AES e faz proxy de "
                    "/pentest/api/* injetando X-API-Token.",
                    "Provisions the stack, keeps the token AES-encrypted and proxies "
                    "/pentest/api/* injecting X-API-Token.",
                ),
            ),
            dict(
                title="CLI  cai",
                tech="Typer",
                color=P["cyan"],
                desc=tr(
                    "scan · exposure · serve · bundle. Mesma imagem do orchestrator, "
                    "outro entrypoint.",
                    "scan · exposure · serve · bundle. Same image as the orchestrator, "
                    "different entrypoint.",
                ),
            ),
            dict(
                title=tr("Agente / CI", "Agent / CI"),
                tech="HTTP",
                color=P["cyan"],
                desc=tr(
                    "Fala REST e lê o AI Fix Bundle direto, sem passar pelo RoqueOS.",
                    "Speaks REST and reads the AI Fix Bundle directly, bypassing RoqueOS.",
                ),
            ),
        ],
    )
    c.para(
        70,
        718,
        tr(
            "Autenticação: X-API-Token (de serviço ou por usuário), Bearer OIDC "
            "ou o cookie de sessão da tela. Só o SSE aceita a credencial em "
            "?token=, porque EventSource não manda header.",
            "Auth: X-API-Token (service or per-user), Bearer OIDC or the UI "
            "session cookie. Only the SSE stream accepts the credential in "
            "?token=, because EventSource cannot send headers.",
        ),
        size=10.5,
        fill=theme["ink_faint"],
        max_w=262,
    )

    # ---------- coluna B: a stack
    sB = c.slot()
    W = [330, 330]  # 2*330+24 = 684: cabe na fronteira com 28 de folga dos dois lados
    (api, wrk), y = row(
        c,
        430,
        222,
        W,
        [
            dict(
                title="orchestrator",
                tech="FastAPI · uvicorn · :8080",
                color=P["rose"],
                desc=tr(
                    "51 rotas em 14 routers. Valida escopo, grava a trilha de auditoria "
                    "no mesmo commit do scan, enfileira o job e transmite fase por SSE "
                    "em /ui/api/events. Serve a tela em / (o painel antigo em /ui só sem o build).",
                    "51 routes in 14 routers. Checks scope, writes the audit trail in "
                    "the same commit as the scan, enqueues the job and streams phases "
                    "over SSE at /ui/api/events. Serves the UI at / "
                    "(the old /ui dashboard only without the build).",
                ),
            ),
            dict(
                title="worker",
                tech=tr("arq · mesma imagem", "arq · same image"),
                color=P["rose"],
                desc=tr(
                    "Roda run_scan_job e run_exposure_job: é quem executa os adapters, "
                    "chama o LLM e escreve o relatório. Entrypoint arq, não uvicorn.",
                    "Runs run_scan_job and run_exposure_job: it executes the adapters, "
                    "calls the LLM and writes the report. arq entrypoint, not uvicorn.",
                ),
            ),
        ],
        gap=24,
    )
    (pg, rd), y = row(
        c,
        430,
        y,
        W,
        [
            dict(
                title="postgres",
                tech="postgres:16-alpine",
                color=P["green"],
                desc="targets · scans · findings · finding_status · users · ai_runs · "
                + tr(
                    "audit_log. A trilha é append-only por TRIGGER no banco, não por "
                    "disciplina de código.",
                    "audit_log. The trail is append-only through a database TRIGGER, "
                    "not through coding discipline.",
                ),
            ),
            dict(
                title="redis",
                tech="redis:7-alpine",
                color=P["green"],
                desc=tr(
                    "Fila do arq. É o que separa a resposta 202 do scan que leva meia hora.",
                    "The arq queue. It is what separates the 202 response from a scan that "
                    "takes half an hour.",
                ),
            ),
        ],
        gap=24,
    )
    y += 38  # corredor: tres arestas rotuladas nao cabem em 24px
    W3 = [212, 212, 212]
    (zap, tri, kali), y = row(
        c,
        430,
        y,
        W3,
        [
            dict(
                title="zap",
                tech="zap-stable · :8090",
                color=P["amber"],
                desc=tr(
                    "DAST de aplicação web. Spider e fila passiva; varredura ativa é opt-in.",
                    "Web application DAST. Spider and passive queue; active scan is opt-in.",
                ),
            ),
            dict(
                title="trivy",
                tech="trivy · :4954",
                color=P["amber"],
                desc=tr(
                    "Modo server. Imagem de container e dependência de repositório.",
                    "Server mode. Container images and repository dependencies.",
                ),
            ),
            dict(
                title="kali-toolbox",
                tech="kali-rolling",
                color=P["kali"],
                desc=tr(
                    "19 ferramentas de pentest. É onde o agente executa comando.",
                    "19 pentest tools. This is where the agent runs commands.",
                ),
            ),
        ],
        gap=24,
    )
    (olm, grb, exp), y = row(
        c,
        430,
        y,
        W3,
        [
            dict(
                title="ollama",
                tech="opt-in",
                color=P["gray"],
                desc=tr(
                    "LLM local, para quando o prompt não pode sair da rede.",
                    "Local LLM, for when the prompt cannot leave the network.",
                ),
            ),
            dict(
                title="greenbone",
                tech=tr("opt-in · 7 serviços", "opt-in · 7 services"),
                color=P["gray"],
                desc=tr(
                    "Scanner de rede autenticado. O feed leva de 30 min a 3 h.",
                    "Authenticated network scanner. The feed takes 30 min to 3 h.",
                ),
            ),
            dict(
                title="cai-expert",
                tech="STUB",
                color=P["gray"],
                desc=tr(
                    "Container do agente. O compose se declara stub e o build usa || true.",
                    "Agent container. The compose file says it is a stub and the build "
                    "uses || true.",
                ),
            ),
        ],
        gap=24,
    )
    c.rect(exp.x, exp.y, exp.w, exp.h, r=12, fill="none", stroke=P["red"], sw=1.6, dash="5 4")
    c.text(
        exp.x + exp.w,
        exp.y + exp.h + 24,
        tr("não operacional", "not operational"),
        size=10,
        fill=P["red"],
        anchor="end",
        weight=600,
        family=MONO,
    )

    # ---------- coluna C: fora
    sC = c.slot()
    (llm, tgt, dd), _ = stack_col(
        c,
        1280,
        228,
        262,
        [
            dict(
                title=tr("Provedor de LLM", "LLM provider"),
                tech="litellm",
                color=P["amber"],
                desc=tr(
                    "Anthropic · OpenAI · OpenRouter · endpoint local. O gateway faz "
                    "fallback local→nuvem e grava telemetria em ai_runs.",
                    "Anthropic · OpenAI · OpenRouter · local endpoint. The gateway falls "
                    "back local→cloud and records telemetry in ai_runs.",
                ),
            ),
            dict(
                title=tr("Alvos", "Targets"),
                tech=tr("7 tipos de ativo", "7 asset types"),
                color=P["red"],
                desc=tr(
                    "Com lab-only (padrão), endereço interno só se estiver na "
                    "allow-list, que vem vazia. Lab: juice-shop, dvwa.",
                    "With lab-only (default), an internal address only if it is on "
                    "the allow-list, which ships empty. Lab: juice-shop, dvwa.",
                ),
            ),
            dict(
                title="DefectDojo",
                tech=tr("REST · opcional", "REST · optional"),
                color=P["gray"],
                desc=tr(
                    "Export dos achados para gestão centralizada.",
                    "Exports findings to centralized management.",
                ),
            ),
        ],
    )

    # fronteiras fecham agora que a altura do conteúdo é conhecida
    c.into(sA, boundary, 48, 186, 306, 646, tr("quem entra", "who comes in"), color=P["violet"])
    b = c.into(
        sB,
        boundary,
        402,
        168,
        740,
        exp.y + exp.h + 64 - 168,
        "stack roqueos-pentest",
        tr("rede roqueos-network", "network roqueos-network"),
        color=P["rose"],
    )
    c.into(
        sC,
        boundary,
        1258,
        186,
        306,
        dd.y + dd.h + 28 - 186,
        tr("fora da stack", "outside the stack"),
        color=P["gray"],
    )

    # ---------- arestas
    # ordem de baixo para cima: o rotulo pintado depois cobre a linha vertical que o cruza
    edge(
        c,
        ag.right,
        api.pt("left", 0.85),
        "REST",
        "X-API-Token",
        color=P["cyan"],
        mid=[(378, ag.cy), (378, api.y + api.h * 0.85)],
    )
    edge(
        c,
        cli.right,
        api.pt("left", 0.55),
        "in-process",
        "run_scan()",
        color=P["cyan"],
        mid=[(378, cli.cy), (378, api.y + api.h * 0.55)],
    )
    edge(
        c,
        ros.right,
        api.pt("left", 0.2),
        "proxy",
        "HTTP + SSE",
        color=P["accent"],
        mid=[(378, ros.cy), (378, api.y + api.h * 0.2)],
    )
    edge(c, api.right, wrk.left, tr("enfileira", "enqueues"), "arq")
    edge(c, api.bottom, pg.top, tr("lê e grava", "reads, writes"), "SQLModel")
    edge(c, wrk.bottom, rd.top, tr("consome", "consumes"), "job")
    edge(
        c,
        wrk.pt("left", 0.75),
        (pg.x + pg.w, pg.y + 30),
        tr("grava achado", "writes findings"),
        color=P["green"],
        mid=[(wrk.x - 12, wrk.y + wrk.h * 0.75), (wrk.x - 12, pg.y + 30)],
    )
    edge(
        c,
        (wrk.cx, rd.y + rd.h),
        (zap.cx, zap.y),
        "start · poll · fetch",
        tr("contrato do adapter", "adapter contract"),
        color=P["amber"],
        mid=[(wrk.cx, rd.y + rd.h + 20), (zap.cx, rd.y + rd.h + 20)],
    )
    edge(
        c,
        (wrk.cx + 40, rd.y + rd.h),
        (tri.cx, tri.y),
        None,
        color=P["amber"],
        mid=[(wrk.cx + 40, rd.y + rd.h + 44), (tri.cx, rd.y + rd.h + 44)],
    )
    edge(
        c,
        (rd.cx + 120, rd.y + rd.h),
        kali.pt("top", 0.72),
        "docker exec",
        tr("argv, nunca shell", "argv, never shell"),
        color=P["kali"],
        mid=[(rd.cx + 120, rd.y + rd.h + 48), (kali.x + kali.w * 0.72, rd.y + rd.h + 48)],
        label_dx=0,
        label_dy=-4,
    )
    edge(
        c,
        wrk.right,
        llm.left,
        tr("tria", "triage"),
        tr("prompt sanitizado", "scrubbed prompt"),
        color=P["amber"],
        mid=[(1200, wrk.cy), (1200, llm.cy)],
    )
    edge(
        c,
        (b.x + b.w, zap.cy),
        tgt.pt("left", 0.7),
        tr("varre", "scans"),
        color=P["red"],
        mid=[(1186, zap.cy), (1186, tgt.y + tgt.h * 0.7)],
        label_dy=54,
    )
    edge(
        c,
        (b.x + b.w, pg.cy + 40),
        dd.pt("left", 0.4),
        tr("exporta", "exports"),
        color=P["gray"],
        mid=[(1222, pg.cy + 40), (1222, dd.y + dd.h * 0.4)],
        label_dy=-48,
    )

    legend(
        c,
        1258,
        726,
        [
            (P["rose"], tr("Processo do RoqueShield", "RoqueShield process")),
            (P["green"], tr("Armazenamento", "Storage")),
            (P["amber"], tr("Scanner ou serviço externo", "Scanner or external service")),
            (P["kali"], tr("Toolbox de pentest", "Pentest toolbox")),
            (P["accent"], tr("Família RoqueOS", "RoqueOS family")),
            (P["cyan"], tr("Cliente automatizado", "Automated client")),
            (P["gray"], tr("Opt-in ou opcional", "Opt-in or optional")),
            (P["red"], tr("Alvo, ou peça declarada stub", "Target, or a declared stub")),
        ],
        cols=1,
        box_w=306,
    )

    footer(
        c,
        tr("C4 model · nível 2 de 4 · fonte: ", "C4 model · level 2 of 4 · source: ")
        + "docker/compose*.yml · orchestrator/main.py · orchestrator/jobs/queue.py",
        "github.com/roqueribeiro/roqueos-shield",
    )
    return c
