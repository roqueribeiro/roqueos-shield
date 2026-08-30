"""C3 — Componentes do orchestrator."""

from .c4lib import *

SAIDA = "c3-components"


def draw(theme):
    c = Canvas(1900, 1230, theme)
    P = PALETTE
    t = theme
    title_block(
        c,
        "RoqueShield — Componentes do orchestrator",
        "O que existe dentro da imagem que o container orchestrator e o worker "
        "compartilham. Cada caixa é um módulo Python real, com o caminho do arquivo.",
        level="C3  ·  COMPONENTES",
    )
    brand(c)

    X, W = 56, 1788

    # ---- camada de API
    sA = c.slot()
    (r1, r2, r3), y = row(
        c,
        X + 22,
        210,
        [566, 566, 566],
        [
            dict(
                title="routers",
                tech="api/routers/*.py",
                color=P["rose"],
                desc="10 módulos, 33 rotas: targets, scans, findings, reports, exposure, "
                "investigate, ui, users, auth, health. O router ui/ carrega o SSE em "
                "/ui/api/events.",
            ),
            dict(
                title="deps",
                tech="api/deps.py",
                color=P["rose"],
                desc="Resolve identidade por X-API-Key + X-API-Secret ou por OIDC, e injeta "
                "a sessão do banco. É onde o papel do usuário entra na requisição.",
            ),
            dict(
                title="main",
                tech="main.py",
                color=P["rose"],
                desc="Monta o FastAPI, registra os routers, serve /ui estático e avisa "
                "audit.mutable_trail quando o banco não é Postgres — porque aí a trilha "
                "não é imutável.",
            ),
        ],
        gap=24,
    )
    c.into(
        sA,
        boundary,
        X,
        176,
        W,
        y - 176 - 4,
        "camada de API",
        "processo orchestrator",
        color=P["rose"],
    )

    # ---- domínio
    y += 20
    sB = c.slot()
    (d1, d2, d3, d4), y2 = row(
        c,
        X + 22,
        y + 44,
        [420, 420, 420, 420],
        [
            dict(
                title="schemas",
                tech="domain/schemas.py",
                color=P["accent"],
                desc="Target, Finding, Evidence, AITriage, RawResults, AssetType (7 valores). "
                "Finding é frozen no que importa e carrega deduped_key.",
            ),
            dict(
                title="target_validator",
                tech="domain/target_validator.py",
                color=P["accent"],
                desc="Gate de escopo. Recusa alvo fora da allow-list ANTES de qualquer pacote "
                "sair. Devolve 403, não warning.",
            ),
            dict(
                title="dedup",
                tech="domain/dedup.py",
                color=P["accent"],
                desc="heuristic_dedup: determinístico, mantém a maior severidade por "
                "deduped_key. Existe dedupe semântico por LLM, e ele NÃO é chamado no "
                "pipeline.",
            ),
            dict(
                title="scrubber",
                tech="domain/scrubber.py",
                color=P["accent"],
                desc="Último ponto antes de qualquer texto sair para um LLM externo. "
                "scrub e scrub_dict.",
            ),
        ],
        gap=24,
    )
    c.into(
        sB,
        boundary,
        X,
        y,
        W,
        y2 - y - 4,
        "domínio",
        "regra que não depende de I/O",
        color=P["accent"],
    )

    # ---- jobs
    y = y2 + 20
    sC = c.slot()
    (j1, j2, j3), y2 = row(
        c,
        X + 22,
        y + 44,
        [566, 566, 566],
        [
            dict(
                title="pipelines",
                tech="jobs/pipelines.py",
                color=P["violet"],
                desc="O coração. resolve_scanners (pedido > profile > default do tipo), "
                "_build_adapters (factory de 9), _run_adapter (o ciclo de vida) e "
                "run_scan (as 8 fases). Converte coverage_gaps em achado INFO num lugar só.",
            ),
            dict(
                title="queue · workers",
                tech="jobs/queue.py · jobs/workers.py",
                color=P["violet"],
                desc="WorkerSettings do arq sobre Redis. run_scan_job e run_exposure_job. "
                "É o que deixa a API responder 202 e o scan levar meia hora.",
            ),
            dict(
                title="exposure",
                tech="jobs/exposure.py",
                color=P["violet"],
                desc="Trilha OSINT. Instancia 6 adapters direto, sem passar pela factory — "
                "por isso um scanner pode existir e nunca ser construído.",
            ),
        ],
        gap=24,
    )
    c.into(sC, boundary, X, y, W, y2 - y - 4, "orquestração", "processo worker", color=P["violet"])

    # ---- três colunas de baixo
    y = y2 + 20
    sD, sE, sF = c.slot(), c.slot(), c.slot()
    (a1, a2), ya = row(
        c,
        X + 22,
        y + 44,
        [256, 256],
        [
            dict(
                title="base",
                tech="adapters/base.py",
                color=P["amber"],
                desc="Protocol ScannerAdapter (health, start_scan, poll, fetch_results, "
                "normalize), ScanIntegrityError, read_jsonl e coverage_gap_finding.",
            ),
            dict(
                title="15 adapters",
                tech="adapters/*.py",
                color=P["amber"],
                desc="nmap, zap, nuclei, greenbone, trivy, semgrep, gitleaks, trufflehog, "
                "checkov, dnstwist, subdomain_takeover, shodan, censys, "
                "github_exposure, kube_bench.",
            ),
        ],
        gap=24,
    )
    c.into(sD, boundary, X, y, 580, ya - y - 4, "scanners", "adapters/", color=P["amber"])

    (i1, i2), yb = row(
        c,
        X + 626,
        y + 44,
        [256, 256],
        [
            dict(
                title="gateway",
                tech="ai/gateway.py",
                color=P["cyan"],
                desc="litellm. complete, complete_json, complete_with_tools. Prompt caching "
                "da Anthropic, fallback local→nuvem e telemetria por chamada em ai_runs.",
            ),
            dict(
                title="analyzer · agentic",
                tech="ai/analyzer.py · ai/agentic/",
                color=P["cyan"],
                desc="triage_batch tria TODO achado, inclusive low e info. executor.py é a "
                "coleira do agente; cai_expert.py é o laço de investigação.",
            ),
        ],
        gap=24,
    )
    c.into(sE, boundary, X + 604, y, 580, yb - y - 4, "inteligência", "ai/", color=P["cyan"])

    (p1, p2), yc = row(
        c,
        X + 1230,
        y + 44,
        [256, 256],
        [
            dict(
                title="reporting",
                tech="reporting/",
                color=P["green"],
                desc="renderer (HTML técnico e executivo), compliance (OWASP, PCI DSS, LGPD, "
                "CWE Top 25, nota A–F), coverage e os exporters ai_bundle e defectdojo.",
            ),
            dict(
                title="persistence",
                tech="persistence/",
                color=P["green"],
                desc="SQLModel: 9 tabelas. audit_log é append-only por TRIGGER, e as 7 "
                "migrations do Alembic são o que garante o trigger existir.",
            ),
        ],
        gap=24,
    )
    c.into(sF, boundary, X + 1208, y, 580, yc - y - 4, "saída e estado", color=P["green"])

    ymax = max(ya, yb, yc)

    # ---- arestas verticais entre camadas
    edge(
        c,
        (r1.cx, r1.y + r1.h + 4),
        (d2.cx, d2.y),
        "valida escopo e grava auditoria",
        mid=[(r1.cx, r1.y + r1.h + 22), (d2.cx, r1.y + r1.h + 22)],
    )
    edge(
        c,
        (r2.cx, r2.y + r2.h + 4),
        (j2.cx, j2.y),
        "enfileira",
        mid=[(r2.cx, j1.y - 26), (j2.cx, j1.y - 26)],
    )
    edge(
        c,
        (j1.cx, j1.y + j1.h + 4),
        (a2.cx, a2.y),
        "start · poll · fetch · normalize",
        color=P["amber"],
        mid=[(j1.cx, j1.y + j1.h + 22), (a2.cx, j1.y + j1.h + 22)],
    )
    edge(
        c,
        (j1.cx + 120, j1.y + j1.h + 4),
        (i2.cx, i2.y),
        "tria",
        color=P["cyan"],
        mid=[(j1.cx + 120, j1.y + j1.h + 34), (i2.cx, j1.y + j1.h + 34)],
        label_dy=-14,
    )
    edge(
        c,
        (j3.cx, j3.y + j3.h + 4),
        (p1.cx, p1.y),
        "renderiza e persiste",
        color=P["green"],
        mid=[(j3.cx, j3.y + j3.h + 22), (p1.cx, j3.y + j3.h + 22)],
    )

    # ---- nota do contrato
    ny = ymax + 16
    c.rect(X, ny, W, 96, r=12, fill=t["bg_alt"], stroke=P["rose"], sw=1.2, dash="6 5")
    c.text(
        X + 22,
        ny + 30,
        "O CONTRATO DO SILÊNCIO",
        size=11,
        weight=700,
        fill=P["rose"],
        spacing=1.2,
        family=MONO,
    )
    c.para(
        X + 22,
        ny + 54,
        "Um scanner quebrado produz exatamente a mesma saída de um alvo seguro: zero achados. Por isso o adapter escolhe "
        "sempre um de três níveis — devolve [] quando rodou e não achou, levanta ScanIntegrityError quando não deu para "
        'verificar, ou preenche coverage_gaps quando verificou em parte. O job "Contrato do silencio" do CI compara o '
        "código com essa regra por AST, e o nível 4 deste modelo mostra como.",
        size=11.5,
        fill=t["ink_soft"],
        max_w=W - 44,
    )

    footer(
        c,
        "C4 model · nível 3 de 4 · fonte: árvore de orchestrator/",
        "github.com/roqueribeiro/roqueos-shield",
        y=ny + 132,
    )
    c.h = int(ny + 150)
    return c
