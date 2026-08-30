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
                title="CLI  cai",
                tech="Typer · mesma imagem do orchestrator",
                color=P["cyan"],
                desc="cai scan <alvo> --asset-type url --criticality high\n"
                'cai exposure "Empresa" --domains ex.com --github-orgs ex\n'
                "cai bundle <scan_id> --out bundle.json\n\n"
                "Roda in-process, sem subir API. É o caminho mais curto para um agente que "
                "já tem shell — Claude Code, Cursor, um passo de CI.",
            ),
            dict(
                title="API REST",
                tech="FastAPI · 33 rotas · OpenAPI em /docs",
                color=P["accent"],
                desc="POST /targets → POST /scans → 202\n"
                "GET /scans/{id} · GET /findings?scan_id=…\n"
                "GET /ui/api/events (SSE, fase e log ao vivo)\n\n"
                "Autenticação por X-API-Key + X-API-Secret ou OIDC. É o que o RoqueOS "
                "consome por trás do proxy, e é o que um serviço externo consome direto.",
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
        "As duas peças abaixo NÃO existem no repositório hoje. Estão desenhadas aqui como "
        "proposta, não como funcionalidade: quem chegar procurando por elas no código não "
        "vai encontrar. Medido em 2026-08-30: zero ocorrência de MCP em orchestrator/, e "
        ".github/workflows/ tem um arquivo só, o ci.yml, sem workflow_call e sem action.yml.",
        size=12,
        fill=t["ink_soft"],
        max_w=W - 48,
    )

    ry = y + 152
    (m1, m2), _ = row(
        c,
        X + 24,
        ry,
        [860, 856],
        [
            dict(
                title="Servidor MCP",
                tech="proposta",
                color=P["gray"],
                desc="Tools que fariam sentido, uma por caso de uso real que hoje exige shell: "
                "shield_scan(alvo, perfil), shield_status(scan_id), "
                "shield_findings(scan_id, severidade), shield_bundle(scan_id) e "
                "shield_compare(scan_a, scan_b).\n\n"
                "O que falta: o servidor em si, o transporte, a autenticação por token de "
                "serviço e um teste que prove que a tool devolve erro quando o scan falhou "
                "— em vez de lista vazia, que é justamente o silêncio que o resto do "
                "projeto combate.",
            ),
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
        "fonte: orchestrator/cli.py · orchestrator/main.py · "
        "orchestrator/reporting/exporters/ai_bundle.py · docs/ai-fix-bundle-spec.md · "
        ".github/workflows/ci.yml",
        "github.com/roqueribeiro/roqueos-shield",
        y=m1.y + m1.h + 78,
    )
    c.h = int(m1.y + m1.h + 102)
    return c
