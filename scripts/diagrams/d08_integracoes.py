"""Superficies de integracao e o laco agente -> conserto -> re-scan."""

from .c4lib import *

SAIDA = "integracoes"


def draw(theme):
    c = Canvas(1900, 1420, theme)
    P = PALETTE
    t = theme
    title_block(
        c,
        tr(
            "RoqueShield: como plugar em agente, API e esteira",
            "RoqueShield: plugging into agents, APIs and pipelines",
        ),
        tr(
            "O que existe hoje está em cima; o que ainda não existe está embaixo, marcado. "
            "Nenhuma caixa desta página descreve capacidade que não esteja no código.",
            "What exists today is on top; what does not exist yet is below, marked. "
            "No box on this page describes a capability that is not in the code.",
        ),
    )
    brand(c)

    X, W = 56, 1788

    # ---------------- hoje
    c.pill(
        X,
        176,
        tr("HOJE · EXISTE E ESTÁ TESTADO", "TODAY · EXISTS AND IS TESTED"),
        P["green"],
        filled=True,
    )
    y = 222
    (s1, s2, s3), y = row(
        c,
        X,
        y,
        [580, 580, 580],  # 3*580 + 2*24 = 1788 = W
        [
            dict(
                title="CLI  roqueshield · cai",
                tech=tr(
                    "Typer · cliente da API, e o cai in-process",
                    "Typer · API client, and cai in-process",
                ),
                color=P["cyan"],
                desc=tr(
                    "roqueshield scan start <alvo> --wait --fail-on high\n"
                    "roqueshield report <scan_id> --format bundle -o bundle.json\n"
                    "cai scan <alvo>  (in-process, dentro da imagem)\n\n"
                    "Saída para CI: 0 ok, 1 achado no limite, 3 cobertura incompleta. "
                    "Zero achado com scanner que não rodou nunca sai 0.",
                    "roqueshield scan start <target> --wait --fail-on high\n"
                    "roqueshield report <scan_id> --format bundle -o bundle.json\n"
                    "cai scan <target>  (in-process, inside the image)\n\n"
                    "Exit codes for CI: 0 ok, 1 finding at the threshold, 3 incomplete "
                    "coverage. Zero findings with a scanner that did not run never exits 0.",
                ),
            ),
            dict(
                title="API REST",
                tech=tr(
                    "FastAPI · OpenAPI em /docs · fotografia no repo",
                    "FastAPI · OpenAPI at /docs · snapshot in the repo",
                ),
                color=P["accent"],
                desc="POST /targets → POST /scans → 202\n"
                "GET /scans/{id} · GET /findings?scan_id=…\n"
                + tr(
                    "GET /ui/api/events (SSE, fase e log ao vivo)\n\n"
                    "Token por usuário (X-API-Token), OIDC ou a sessão da tela. É o que o "
                    "RoqueOS consome por trás do proxy, e o que um serviço externo consome direto.",
                    "GET /ui/api/events (SSE, live phase and log)\n\n"
                    "Per-user token (X-API-Token), OIDC or the screen session. It is what "
                    "RoqueOS consumes behind the proxy, and what an external service calls "
                    "directly.",
                ),
            ),
            dict(
                title="AI Fix Bundle",
                tech=tr(
                    "JSON · schema 1.0.0 · contrato versionado",
                    "JSON · schema 1.0.0 · versioned contract",
                ),
                color=P["rose"],
                desc="GET /reports/{scan_id}/ai-bundle\n\n"
                + tr(
                    "O formato desenhado para um agente ler: achado, arquivo, linha, "
                    "severidade, CWE, evidência e remediação sugerida, já triados e "
                    "deduplicados. docs/AI-FIX-BUNDLE.md é o contrato, e ele tem "
                    "número de versão porque quem consome precisa saber quando muda.",
                    "The format designed for an agent to read: finding, file, line, "
                    "severity, CWE, evidence and suggested fix, already triaged and "
                    "deduplicated. docs/AI-FIX-BUNDLE.md is the contract, and it has a "
                    "version number because consumers need to know when it changes.",
                ),
            ),
        ],
        gap=24,
    )
    (s4,), y = row(
        c,
        X,
        y + 20,
        [W],
        [
            dict(
                title=tr("Servidor MCP", "MCP server"),
                tech=tr(
                    "JSON-RPC · stdio (roqueshield mcp) e HTTP (POST /mcp)",
                    "JSON-RPC · stdio (roqueshield mcp) and HTTP (POST /mcp)",
                ),
                color=P["green"],
                desc="list_scans · get_scan · get_findings · get_ai_bundle · list_targets, "
                + tr(
                    "e start_scan só com as ações ligadas e authorization_ref obrigatória.\n"
                    "Achado e bundle de scan que falhou ou veio com cobertura incompleta voltam "
                    "com isError e o motivo, nunca lista vazia: o silêncio não volta pela porta "
                    "do protocolo.",
                    "and start_scan only with actions enabled and authorization_ref required.\n"
                    "Findings and bundles from a scan that failed or has incomplete coverage "
                    "come back with isError and the reason, never an empty list: silence does "
                    "not sneak back in through the protocol.",
                ),
            )
        ],
        gap=24,
    )

    # ---------------- o laço
    y += 26
    c.pill(
        X,
        y,
        tr("O LAÇO · monta-se com o que já existe", "THE LOOP · built from what already exists"),
        P["cyan"],
        filled=True,
    )
    y += 46
    passos = [
        (
            "1",
            "scan",
            "cai scan · POST /scans",
            P["accent"],
            tr(
                "O agente dispara o scan no alvo: repositório, imagem ou URL do ambiente de teste.",
                "The agent starts the scan on the target: repository, image or test "
                "environment URL.",
            ),
        ),
        (
            "2",
            "bundle",
            "GET …/ai-bundle",
            P["rose"],
            tr(
                "Lê o JSON de contrato em vez de raspar HTML. Achado triado, com arquivo e linha.",
                "Reads the contract JSON instead of scraping HTML. Triaged findings, with file "
                "and line.",
            ),
        ),
        (
            "3",
            "patch",
            tr("o agente edita o código", "the agent edits the code"),
            P["cyan"],
            tr(
                "Aplica a correção no repositório, com o CWE e a remediação sugerida "
                "como contexto.",
                "Applies the fix in the repository, with the CWE and the suggested fix as context.",
            ),
        ),
        (
            "4",
            "re-scan",
            tr("novo POST /scans", "new POST /scans"),
            P["accent"],
            tr(
                "Roda de novo sobre o código corrigido. É o passo que separa conserto de "
                "alegação de conserto.",
                "Runs again on the fixed code. This is the step that separates a fix from "
                "a claimed fix.",
            ),
        ),
        (
            "5",
            tr("compara", "compare"),
            tr("deduped_key entre os dois scans", "deduped_key across both scans"),
            P["green"],
            tr(
                "Achado que sumiu foi corrigido; achado que ficou volta ao passo 3; achado novo "
                "é regressão que o patch criou.",
                "A finding that is gone was fixed; one that stayed goes back to step 3; a new "
                "one is a regression the patch introduced.",
            ),
        ),
    ]
    cw = 336
    bs = []
    for i, (n, nome, tech, cor, desc) in enumerate(passos):
        bx = X + i * (cw + 22)
        b = step(c, bx, y, cw, n, nome, desc, color=cor, h=132)
        c.text(bx + 54, b.y + b.h - 14, tech, size=9.5, fill=cor, family=MONO, weight=600)
        bs.append(b)
    # pares consecutivos: os comprimentos diferem por 1 de proposito
    for a, b in zip(bs, bs[1:], strict=False):
        edge(c, (a.x + a.w, a.cy), (b.x - 2, b.cy), None, color=P["cyan"])
    # retorno
    ry = bs[0].y + bs[0].h + 34
    edge(
        c,
        (bs[-1].cx, bs[-1].y + bs[-1].h),
        (bs[2].cx, bs[2].y + bs[2].h + 2),
        tr("enquanto sobrar achado, volta ao passo 3", "while findings remain, back to step 3"),
        color=P["cyan"],
        dash="6 5",
        mid=[(bs[-1].cx, ry), (bs[2].cx, ry)],
    )
    y = ry + 40
    c.para(
        X,
        y + 10,
        tr(
            'O critério de parada não é "o agente disse que acabou": é o scan seguinte não '
            "achar mais nada da lista anterior, e o coverage_complete continuar verdadeiro. "
            "Scanner que deixou de rodar entre uma rodada e outra derruba os dois, e aparece "
            "em scanners_skipped em vez de virar zero achados.",
            'The stop condition is not "the agent said it is done": it is the next scan '
            "finding nothing from the previous list, with coverage_complete still true. A "
            "scanner that stopped running between rounds breaks both, and shows up in "
            "scanners_skipped instead of turning into zero findings.",
        ),
        size=12,
        fill=t["ink_soft"],
        max_w=1200,
    )
    y += 76

    # ---------------- roadmap
    sR = c.slot()
    c.pill(
        X + 24,
        y + 22,
        tr("ROADMAP · NÃO IMPLEMENTADO", "ROADMAP · NOT IMPLEMENTED"),
        P["red"],
        filled=True,
    )
    fim = c.para(
        X + 24,
        y + 74,
        tr(
            "A peça abaixo NÃO existe no repositório hoje. Está desenhada aqui como proposta, "
            "não como funcionalidade: quem chegar procurando por ela no código não vai "
            "encontrar. .github/workflows/ não tem workflow_call nem action.yml.",
            "The piece below does NOT exist in the repository today. It is drawn here as a "
            "proposal, not a feature: anyone looking for it in the code will not find it. "
            ".github/workflows/ has no workflow_call and no action.yml.",
        ),
        size=12,
        fill=t["ink_soft"],
        max_w=W - 48,
    )

    # a caixa segue o texto, que tem uma linha em PT e pode ter duas em EN
    ry = fim + 44
    (m1,), _ = row(
        c,
        X + 24,
        ry,
        [W - 48],
        [
            dict(
                title=tr("GitHub Action reutilizável", "Reusable GitHub Action"),
                tech=tr("proposta", "proposal"),
                color=P["gray"],
                desc=tr(
                    "action.yml com workflow_call, para um repositório de terceiro chamar o "
                    "RoqueShield no seu próprio pipeline e receber o AI Fix Bundle como "
                    "artefato, e o resumo como comentário no PR.\n\n"
                    "O que falta: o action.yml, a imagem publicada com tag estável para a "
                    "Action fixar, o mapeamento de saída para o formato de anotação do GitHub, "
                    "e a decisão de política sobre reprovar o build por severidade.",
                    "action.yml with workflow_call, so a third-party repository can call "
                    "RoqueShield in its own pipeline and get the AI Fix Bundle as an "
                    "artifact, plus the summary as a PR comment.\n\n"
                    "What is missing: the action.yml, an image published with a stable tag "
                    "for the Action to pin, mapping the output to GitHub's annotation format, "
                    "and the policy decision on failing the build by severity.",
                ),
            ),
        ],
        gap=24,
    )

    c.into(
        sR,
        lambda cc, *a, **k: cc.rect(*a, **k),
        X,
        y,
        W,
        m1.y + m1.h + 30 - y,
        r=14,
        fill=t["bg_alt"],
        stroke=P["red"],
        sw=1.6,
        dash="8 6",
    )

    footer(
        c,
        tr("fonte: ", "source: ")
        + "orchestrator/cli.py · orchestrator/cliente/ · orchestrator/main.py · "
        "orchestrator/reporting/exporters/ai_bundle.py · docs/AI-FIX-BUNDLE.md · "
        ".github/workflows/ci.yml",
        "github.com/roqueribeiro/roqueos-shield",
        y=m1.y + m1.h + 78,
    )
    c.h = int(m1.y + m1.h + 102)
    return c
