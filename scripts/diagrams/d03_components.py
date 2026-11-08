"""C3: Componentes do orchestrator."""

from .c4lib import *

SAIDA = "componentes"


def draw(theme):
    c = Canvas(1900, 1230, theme)
    P = PALETTE
    t = theme
    title_block(
        c,
        tr(
            "RoqueShield: componentes do orchestrator",
            "RoqueShield: orchestrator components",
        ),
        tr(
            "O que existe dentro da imagem que o container orchestrator e o worker "
            "compartilham. Cada caixa é um módulo Python real, com o caminho do arquivo.",
            "What lives inside the image shared by the orchestrator container and the "
            "worker. Each box is a real Python module, with its file path.",
        ),
        level=tr("C3  ·  COMPONENTES", "C3  ·  COMPONENTS"),
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
                desc=tr(
                    "14 módulos, 51 rotas: targets, scans, findings, reports, exposure, "
                    "investigate, ui, users, auth, conta, settings, system, mcp, health. "
                    "O router ui/ carrega o SSE em /ui/api/events.",
                    "14 modules, 51 routes: targets, scans, findings, reports, exposure, "
                    "investigate, ui, users, auth, conta, settings, system, mcp, health. "
                    "The ui/ router carries the SSE at /ui/api/events.",
                ),
            ),
            dict(
                title="deps",
                tech="api/deps.py",
                color=P["rose"],
                desc=tr(
                    "Resolve identidade por X-API-Token, Bearer OIDC ou cookie de sessão, e injeta "
                    "a sessão do banco. É onde o papel do usuário entra na requisição.",
                    "Resolves identity from X-API-Token, Bearer OIDC or the session cookie, and injects "
                    "the database session. This is where the user role enters the request.",
                ),
            ),
            dict(
                title="main",
                tech="main.py",
                color=P["rose"],
                desc=tr(
                    "Monta o FastAPI, registra os routers, serve /ui estático e avisa "
                    "audit.mutable_trail quando o banco não é Postgres, porque aí a trilha "
                    "não é imutável.",
                    "Builds the FastAPI app, registers the routers, serves static /ui and "
                    "warns audit.mutable_trail when the database is not Postgres, because "
                    "then the trail is not immutable.",
                ),
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
        tr("camada de API", "API layer"),
        tr("processo orchestrator", "orchestrator process"),
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
                desc=tr(
                    "Target, Finding, Evidence, AITriage, RawResults, AssetType (7 valores). "
                    "Finding é frozen no que importa e carrega deduped_key.",
                    "Target, Finding, Evidence, AITriage, RawResults, AssetType (7 values). "
                    "Finding is frozen where it matters and carries deduped_key.",
                ),
            ),
            dict(
                title="target_validator",
                tech="domain/target_validator.py",
                color=P["accent"],
                desc=tr(
                    "Gate de escopo. Recusa alvo fora da allow-list ANTES de qualquer pacote "
                    "sair. Devolve 403, não warning.",
                    "Scope gate. Rejects targets outside the allow-list BEFORE any packet "
                    "leaves. Returns 403, not a warning.",
                ),
            ),
            dict(
                title="dedup",
                tech="domain/dedup.py",
                color=P["accent"],
                desc=tr(
                    "heuristic_dedup: determinístico, mantém a maior severidade por "
                    "deduped_key. Existe dedupe semântico por LLM, e ele NÃO é chamado no "
                    "pipeline.",
                    "heuristic_dedup: deterministic, keeps the highest severity per "
                    "deduped_key. A semantic LLM dedupe exists, and the pipeline does NOT "
                    "call it.",
                ),
            ),
            dict(
                title="scrubber",
                tech="domain/scrubber.py",
                color=P["accent"],
                desc=tr(
                    "Último ponto antes de qualquer texto sair para um LLM externo. "
                    "scrub e scrub_dict.",
                    "The last stop before any text goes out to an external LLM. "
                    "scrub and scrub_dict.",
                ),
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
        tr("domínio", "domain"),
        tr("regra que não depende de I/O", "rules with no I/O"),
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
                desc=tr(
                    "O coração. resolve_scanners (pedido > profile > default do tipo), "
                    "_build_adapters (factory de 9), _run_adapter (o ciclo de vida) e "
                    "run_scan (as 8 fases). Converte coverage_gaps em achado INFO num lugar só.",
                    "The core. resolve_scanners (request > profile > type default), "
                    "_build_adapters (factory of 9), _run_adapter (the lifecycle) and "
                    "run_scan (the 8 phases). Turns coverage_gaps into INFO findings in "
                    "one place.",
                ),
            ),
            dict(
                title="queue · workers",
                tech="jobs/queue.py · jobs/workers.py",
                color=P["violet"],
                desc=tr(
                    "WorkerSettings do arq sobre Redis. run_scan_job e run_exposure_job. "
                    "É o que deixa a API responder 202 e o scan levar meia hora.",
                    "arq WorkerSettings on Redis. run_scan_job and run_exposure_job. "
                    "It lets the API answer 202 while the scan takes half an hour.",
                ),
            ),
            dict(
                title="exposure",
                tech="jobs/exposure.py",
                color=P["violet"],
                desc=tr(
                    "Trilha OSINT. Instancia 6 adapters direto, sem passar pela factory. "
                    "Por isso um scanner pode existir e nunca ser construído.",
                    "OSINT track. Instantiates 6 adapters directly, bypassing the factory. "
                    "That is why a scanner can exist and never be built.",
                ),
            ),
        ],
        gap=24,
    )
    c.into(
        sC,
        boundary,
        X,
        y,
        W,
        y2 - y - 4,
        tr("orquestração", "orchestration"),
        tr("processo worker", "worker process"),
        color=P["violet"],
    )

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
                + tr(
                    "normalize), ScanIntegrityError, read_jsonl e coverage_gap_finding.",
                    "normalize), ScanIntegrityError, read_jsonl and coverage_gap_finding.",
                ),
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
                desc=tr(
                    "litellm. complete, complete_json, complete_with_tools. Prompt caching "
                    "da Anthropic, fallback local→nuvem e telemetria por chamada em ai_runs.",
                    "litellm. complete, complete_json, complete_with_tools. Anthropic "
                    "prompt caching, local→cloud fallback and per-call telemetry in ai_runs.",
                ),
            ),
            dict(
                title="analyzer · agentic",
                tech="ai/analyzer.py · ai/agentic/",
                color=P["cyan"],
                desc=tr(
                    "triage_batch tria TODO achado, inclusive low e info. executor.py é a "
                    "coleira do agente; cai_expert.py é o laço de investigação.",
                    "triage_batch triages EVERY finding, low and info included. executor.py "
                    "is the agent's leash; cai_expert.py is the investigation loop.",
                ),
            ),
        ],
        gap=24,
    )
    c.into(
        sE,
        boundary,
        X + 604,
        y,
        580,
        yb - y - 4,
        tr("inteligência", "intelligence"),
        "ai/",
        color=P["cyan"],
    )

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
                desc=tr(
                    "renderer (HTML técnico e executivo), compliance (OWASP, PCI DSS, LGPD, "
                    "CWE Top 25, nota A–F), coverage e os exporters ai_bundle e defectdojo.",
                    "renderer (technical and executive HTML), compliance (OWASP, PCI DSS, "
                    "LGPD, CWE Top 25, A–F grade), coverage and the ai_bundle and "
                    "defectdojo exporters.",
                ),
            ),
            dict(
                title="persistence",
                tech="persistence/",
                color=P["green"],
                desc=tr(
                    "SQLModel: 9 tabelas. audit_log é append-only por TRIGGER, e as 7 "
                    "migrations do Alembic são o que garante o trigger existir.",
                    "SQLModel: 9 tables. audit_log is append-only through a TRIGGER, and "
                    "the 7 Alembic migrations are what guarantee the trigger exists.",
                ),
            ),
        ],
        gap=24,
    )
    c.into(
        sF,
        boundary,
        X + 1208,
        y,
        580,
        yc - y - 4,
        tr("saída e estado", "output and state"),
        color=P["green"],
    )

    ymax = max(ya, yb, yc)

    # ---- arestas verticais entre camadas
    edge(
        c,
        (r1.cx, r1.y + r1.h + 4),
        (d2.cx, d2.y),
        tr("valida escopo e grava auditoria", "checks scope, writes audit"),
        mid=[(r1.cx, r1.y + r1.h + 22), (d2.cx, r1.y + r1.h + 22)],
    )
    edge(
        c,
        (r2.cx, r2.y + r2.h + 4),
        (j2.cx, j2.y),
        tr("enfileira", "enqueues"),
        mid=[(r2.cx, j1.y - 26), (j2.cx, j1.y - 26)],
    )
    # triagem antes: o rotulo de start/poll, pintado depois, cobre a linha que o cruza
    edge(
        c,
        (j1.cx + 120, j1.y + j1.h + 4),
        (i2.cx, i2.y),
        tr("tria", "triage"),
        color=P["cyan"],
        mid=[(j1.cx + 120, j1.y + j1.h + 34), (i2.cx, j1.y + j1.h + 34)],
        label_dy=-14,
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
        (j3.cx, j3.y + j3.h + 4),
        (p1.cx, p1.y),
        tr("renderiza e persiste", "renders and persists"),
        color=P["green"],
        mid=[(j3.cx, j3.y + j3.h + 22), (p1.cx, j3.y + j3.h + 22)],
    )

    # ---- nota do contrato
    ny = ymax + 16
    c.rect(X, ny, W, 96, r=12, fill=t["bg_alt"], stroke=P["rose"], sw=1.2, dash="6 5")
    c.text(
        X + 22,
        ny + 30,
        tr("O CONTRATO DO SILÊNCIO", "THE SILENCE CONTRACT"),
        size=11,
        weight=700,
        fill=P["rose"],
        spacing=1.2,
        family=MONO,
    )
    c.para(
        X + 22,
        ny + 54,
        tr(
            "Um scanner quebrado produz exatamente a mesma saída de um alvo seguro: zero "
            "achados. Por isso o adapter escolhe sempre um de três níveis: devolve [] quando "
            "rodou e não achou, levanta ScanIntegrityError quando não deu para verificar, ou "
            'preenche coverage_gaps quando verificou em parte. O job "Contrato do silencio" '
            "do CI compara o código com essa regra por AST, e o nível 4 deste modelo mostra como.",
            "A broken scanner produces exactly the same output as a safe target: zero "
            "findings. So an adapter always picks one of three levels: return [] when it ran "
            "and found nothing, raise ScanIntegrityError when it could not check, or fill "
            'coverage_gaps when it checked only part. The CI job "Contrato do silencio" '
            "checks the code against this rule by AST, and level 4 of this model shows how.",
        ),
        size=11.5,
        fill=t["ink_soft"],
        max_w=W - 44,
    )

    footer(
        c,
        tr(
            "C4 model · nível 3 de 4 · fonte: árvore de orchestrator/",
            "C4 model · level 3 of 4 · source: the orchestrator/ tree",
        ),
        "github.com/roqueribeiro/roqueos-shield",
        y=ny + 132,
    )
    c.h = int(ny + 150)
    return c
