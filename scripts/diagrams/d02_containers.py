"""C2 — Containers."""

from .c4lib import *

SAIDA = "c2-containers"


def draw(theme):
    c = Canvas(1852, 990, theme)
    P = PALETTE
    title_block(
        c,
        "RoqueShield — Containers",
        "Cada caixa é um processo com imagem própria. Tudo dentro da fronteira sobe "
        "como uma stack Docker só, provisionada pelo RoqueOS ou por docker compose. "
        "Serviço marcado opt-in não sobe por padrão.",
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
                desc="Provisiona a stack, guarda o token cifrado em AES e faz proxy de "
                "/pentest/api/* injetando X-API-Token.",
            ),
            dict(
                title="CLI  cai",
                tech="Typer",
                color=P["cyan"],
                desc="scan · exposure · serve · bundle. Mesma imagem do orchestrator, "
                "outro entrypoint.",
            ),
            dict(
                title="Agente / CI",
                tech="HTTP",
                color=P["cyan"],
                desc="Fala REST e lê o AI Fix Bundle direto, sem passar pelo RoqueOS.",
            ),
        ],
    )
    c.para(
        70,
        718,
        "Autenticação: X-API-Key + X-API-Secret, ou OIDC. O SSE usa "
        "session-token curto na query porque EventSource não carrega "
        "header — a apiKey nunca vai na URL.",
        size=10.5,
        fill=theme["ink_faint"],
        max_w=262,
    )

    # ---------- coluna B: a stack
    sB = c.slot()
    W = [346, 346]
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
                desc="33 rotas em 10 routers. Valida escopo, grava a trilha de auditoria "
                "no mesmo commit do scan, enfileira o job e transmite fase por SSE "
                "em /ui/api/events. Serve o dashboard estático em /ui.",
            ),
            dict(
                title="worker",
                tech="arq · mesma imagem",
                color=P["rose"],
                desc="Roda run_scan_job e run_exposure_job: é quem executa os adapters, "
                "chama o LLM e escreve o relatório. Entrypoint arq, não uvicorn.",
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
                "audit_log. A trilha é append-only por TRIGGER no banco, não por "
                "disciplina de código.",
            ),
            dict(
                title="redis",
                tech="redis:7-alpine",
                color=P["green"],
                desc="Fila do arq. É o que separa a resposta 202 do scan que leva meia hora.",
            ),
        ],
        gap=24,
    )
    y += 38  # corredor: tres arestas rotuladas nao cabem em 24px
    W3 = [222, 222, 222]
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
                desc="DAST de aplicação web. Spider e fila passiva; varredura ativa é opt-in.",
            ),
            dict(
                title="trivy",
                tech="trivy · :4954",
                color=P["amber"],
                desc="Modo server. Imagem de container e dependência de repositório.",
            ),
            dict(
                title="kali-toolbox",
                tech="kali-rolling",
                color=P["kali"],
                desc="19 ferramentas de pentest. É onde o agente executa comando.",
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
                desc="LLM local, para quando o prompt não pode sair da rede.",
            ),
            dict(
                title="greenbone",
                tech="opt-in · 7 serviços",
                color=P["gray"],
                desc="Scanner de rede autenticado. O feed leva de 30 min a 3 h.",
            ),
            dict(
                title="cai-expert",
                tech="STUB",
                color=P["gray"],
                desc="Container do agente. O compose se declara stub e o build usa || true.",
            ),
        ],
        gap=24,
    )
    c.rect(exp.x, exp.y, exp.w, exp.h, r=12, fill="none", stroke=P["red"], sw=1.6, dash="5 4")
    c.text(
        exp.x + exp.w,
        exp.y + exp.h + 24,
        "não operacional",
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
                title="Provedor de LLM",
                tech="litellm",
                color=P["amber"],
                desc="Anthropic · OpenAI · OpenRouter · endpoint local. O gateway faz "
                "fallback local→nuvem e grava telemetria em ai_runs.",
            ),
            dict(
                title="Alvos",
                tech="7 tipos de ativo",
                color=P["red"],
                desc="Só o que a allow-list permite. lab-only vem ligado: juice-shop, "
                "dvwa, webgoat.",
            ),
            dict(
                title="DefectDojo",
                tech="REST · opcional",
                color=P["gray"],
                desc="Export dos achados para gestão centralizada.",
            ),
        ],
    )

    # fronteiras fecham agora que a altura do conteúdo é conhecida
    c.into(sA, boundary, 48, 186, 306, 646, "quem entra", color=P["violet"])
    b = c.into(
        sB,
        boundary,
        402,
        168,
        740,
        exp.y + exp.h + 64 - 168,
        "stack roqueos-pentest",
        "rede roqueos-network",
        color=P["rose"],
    )
    c.into(sC, boundary, 1258, 186, 306, dd.y + dd.h + 28 - 186, "fora da stack", color=P["gray"])

    # ---------- arestas
    edge(
        c,
        ros.right,
        api.pt("left", 0.2),
        "proxy",
        "HTTP + SSE",
        color=P["accent"],
        mid=[(378, ros.cy), (378, api.y + api.h * 0.2)],
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
        ag.right,
        api.pt("left", 0.85),
        "REST",
        "X-API-Key",
        color=P["cyan"],
        mid=[(378, ag.cy), (378, api.y + api.h * 0.85)],
    )
    edge(c, api.right, wrk.left, "enfileira", "arq")
    edge(c, api.bottom, pg.top, "lê e grava", "SQLModel")
    edge(c, wrk.bottom, rd.top, "consome", "job")
    edge(
        c,
        wrk.pt("left", 0.75),
        (pg.x + pg.w, pg.y + 30),
        "grava achado",
        color=P["green"],
        mid=[(wrk.x - 12, wrk.y + wrk.h * 0.75), (wrk.x - 12, pg.y + 30)],
    )
    edge(
        c,
        (wrk.cx, rd.y + rd.h),
        (zap.cx, zap.y),
        "start · poll · fetch",
        "contrato do adapter",
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
        "argv, nunca shell",
        color=P["kali"],
        mid=[(rd.cx + 120, rd.y + rd.h + 48), (kali.x + kali.w * 0.72, rd.y + rd.h + 48)],
        label_dx=0,
        label_dy=-4,
    )
    edge(
        c,
        wrk.right,
        llm.left,
        "tria",
        "prompt sanitizado",
        color=P["amber"],
        mid=[(1200, wrk.cy), (1200, llm.cy)],
    )
    edge(
        c,
        (b.x + b.w, zap.cy),
        tgt.pt("left", 0.7),
        "varre",
        color=P["red"],
        mid=[(1186, zap.cy), (1186, tgt.y + tgt.h * 0.7)],
        label_dy=54,
    )
    edge(
        c,
        (b.x + b.w, pg.cy + 40),
        dd.pt("left", 0.4),
        "exporta",
        color=P["gray"],
        mid=[(1222, pg.cy + 40), (1222, dd.y + dd.h * 0.4)],
        label_dy=-48,
    )

    legend(
        c,
        1258,
        726,
        [
            (P["rose"], "Processo do RoqueShield"),
            (P["green"], "Armazenamento"),
            (P["amber"], "Scanner ou serviço externo"),
            (P["kali"], "Toolbox de pentest"),
            (P["accent"], "Família RoqueOS"),
            (P["cyan"], "Cliente automatizado"),
            (P["gray"], "Opt-in ou opcional"),
            (P["red"], "Alvo, ou peça declarada stub"),
        ],
        cols=1,
        box_w=306,
    )

    footer(
        c,
        "C4 model · nível 2 de 4 · fonte: docker/compose*.yml · orchestrator/main.py · "
        "orchestrator/jobs/queue.py",
        "github.com/roqueribeiro/roqueos-shield",
    )
    return c
