"""Superficies de integracao e o laco agente -> conserto -> re-scan."""

from .c4lib import *

SAIDA = "integracoes-agente"


def draw(theme):
    c = Canvas(1900, 1420, theme)
    P = PALETTE
    t = theme
    title_block(
        c,
        "RoqueShield — Como plugar em agente, API e esteira",
        "O que existe hoje está em cima; o que ainda não existe está embaixo, marcado. "
        "Nenhuma caixa desta página descreve capacidade que não esteja no código.",
    )
    brand(c)

    X, W = 56, 1788

    # ---------------- hoje
    c.pill(X, 176, "HOJE · EXISTE E ESTÁ TESTADO", P["green"], filled=True)
    y = 222
    (s1, s2, s3), y = row(
        c,
        X,
        y,
        [584, 584, 596],
        [
            dict(
                title="CLI  roqueshield · cai",
                tech="Typer · cliente da API, e o cai in-process",
                color=P["cyan"],
                desc="roqueshield scan start <alvo> --wait --fail-on high\n"
                "roqueshield report <scan_id> --format bundle -o bundle.json\n"
                "cai scan <alvo>  (in-process, dentro da imagem)\n\n"
                "Saída para CI: 0 ok, 1 achado no limite, 3 cobertura incompleta. "
                "Zero achado com scanner que não rodou nunca sai 0.",
            ),
            dict(
                title="API REST",
                tech="FastAPI · OpenAPI em /docs · fotografia no repo",
                color=P["accent"],
                desc="POST /targets → POST /scans → 202\n"
                "GET /scans/{id} · GET /findings?scan_id=…\n"
                "GET /ui/api/events (SSE, fase e log ao vivo)\n\n"
                "Token por usuário (X-API-Token), OIDC ou a sessão da tela. É o que o "
                "RoqueOS consome por trás do proxy, e o que um serviço externo consome direto.",
            ),
            dict(
                title="AI Fix Bundle",
                tech="JSON · schema 1.0.0 · contrato versionado",
                color=P["rose"],
                desc="GET /reports/{scan_id}/ai-bundle\n\n"
                "O formato desenhado para um agente ler: achado, arquivo, linha, "
                "severidade, CWE, evidência e remediação sugerida, já triados e "
                "deduplicados. docs/ai-fix-bundle-spec.md é o contrato, e ele tem "
                "número de versão porque quem consome precisa saber quando muda.",
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
                title="Servidor MCP",
                tech="JSON-RPC · stdio (roqueshield mcp) e HTTP (POST /mcp)",
                color=P["green"],
                desc="list_scans · get_scan · get_findings · get_ai_bundle · list_targets, e "
                "start_scan só com as ações ligadas e authorization_ref obrigatória.\n"
                "Achado e bundle de scan que falhou ou veio com cobertura incompleta voltam com "
                "isError e o motivo, nunca lista vazia: o silêncio não volta pela porta do protocolo.",
            )
        ],
        gap=24,
    )

    # ---------------- o laço
    y += 26
    c.pill(X, y, "O LAÇO · monta-se com o que já existe", P["cyan"], filled=True)
    y += 46
    passos = [
        (
            "1",
            "scan",
            "cai scan · POST /scans",
            P["accent"],
            "O agente dispara o scan no alvo — repositório, imagem ou URL do ambiente de teste.",
        ),
        (
            "2",
            "bundle",
            "GET …/ai-bundle",
            P["rose"],
            "Lê o JSON de contrato em vez de raspar HTML. Achado triado, com arquivo e linha.",
        ),
        (
            "3",
            "patch",
            "o agente edita o código",
            P["cyan"],
            "Aplica a correção no repositório, com o CWE e a remediação sugerida como contexto.",
        ),
        (
            "4",
            "re-scan",
            "novo POST /scans",
            P["accent"],
            "Roda de novo sobre o código corrigido. É o passo que separa conserto de "
            "alegação de conserto.",
        ),
        (
            "5",
            "compara",
            "deduped_key entre os dois scans",
            P["green"],
            "Achado que sumiu foi corrigido; achado que ficou volta ao passo 3; achado novo "
            "é regressão que o patch criou.",
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
        "enquanto sobrar achado, volta ao passo 3",
        color=P["cyan"],
        dash="6 5",
        mid=[(bs[-1].cx, ry), (bs[2].cx, ry)],
    )
    y = ry + 40
    c.para(
        X,
        y + 10,
        'O critério de parada não é "o agente disse que acabou": é o scan seguinte não '
        "achar mais nada da lista anterior, e o coverage_complete continuar verdadeiro. "
        "Scanner que deixou de rodar entre uma rodada e outra derruba os dois — e aparece "
        "em scanners_skipped em vez de virar zero achados.",
        size=12,
        fill=t["ink_soft"],
        max_w=1200,
    )
    y += 76

    # ---------------- roadmap
    sR = c.slot()
    c.pill(X + 24, y + 22, "ROADMAP · NÃO IMPLEMENTADO", P["red"], filled=True)
    c.para(
        X + 24,
        y + 74,
        "A peça abaixo NÃO existe no repositório hoje. Está desenhada aqui como proposta, "
        "não como funcionalidade: quem chegar procurando por ela no código não vai "
        "encontrar. .github/workflows/ não tem workflow_call nem action.yml.",
        size=12,
        fill=t["ink_soft"],
        max_w=W - 48,
    )

    ry = y + 152
    (m1,), _ = row(
        c,
        X + 24,
        ry,
        [W - 48],
        [
            dict(
                title="GitHub Action reutilizável",
                tech="proposta",
                color=P["gray"],
                desc="action.yml com workflow_call, para um repositório de terceiro chamar o "
                "RoqueShield no seu próprio pipeline e receber o AI Fix Bundle como "
                "artefato — e o resumo como comentário no PR.\n\n"
                "O que falta: o action.yml, a imagem publicada com tag estável para a "
                "Action fixar, o mapeamento de saída para o formato de anotação do GitHub, "
                "e a decisão de política sobre reprovar o build por severidade.",
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
        "fonte: orchestrator/cli.py · orchestrator/cliente/ · orchestrator/main.py · "
        "orchestrator/reporting/exporters/ai_bundle.py · docs/ai-fix-bundle-spec.md · "
        ".github/workflows/ci.yml",
        "github.com/roqueribeiro/roqueos-shield",
        y=m1.y + m1.h + 78,
    )
    c.h = int(m1.y + m1.h + 102)
    return c
