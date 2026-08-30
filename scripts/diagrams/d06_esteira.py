"""A esteira de um scan, fase a fase."""

from .c4lib import *

SAIDA = "esteira-scan"


def draw(theme):
    c = Canvas(1900, 1190, theme)
    P = PALETTE
    t = theme
    title_block(
        c,
        "RoqueShield — A esteira de um scan",
        "Do POST até o relatório. Os três portões da entrada acontecem antes de qualquer "
        "pacote sair, e a fase corrente é transmitida por SSE enquanto tudo isso roda.",
    )
    brand(c)

    X = 56
    # ---------- entrada e portoes
    c.pill(X, 176, "ENTRADA", P["accent"], filled=True)
    y = 216
    (e1, e2, e3, e4), y = row(
        c,
        X,
        y,
        [430, 430, 430, 442],
        [
            dict(
                title="POST /scans",
                tech="api/routers/scans.py",
                color=P["accent"],
                desc="target_id, scanners, profile, options, auth. O corpo com header de "
                "autenticação do alvo é separado do que persiste: split_scan_auth guarda "
                "o efêmero em memória e redige o resto na auditoria.",
            ),
            dict(
                title="portão 1 · escopo",
                tech="validate_target_value()",
                color=P["red"],
                desc="Alvo fora da allow-list devolve 403 e o scan não nasce. Com lab-only "
                "ligado, só juice-shop, dvwa, webgoat e localhost passam.",
            ),
            dict(
                title="portão 2 · autorização",
                tech="REQUIRE_AUTH_REF",
                color=P["red"],
                desc="Quando ligado, scan sem authorization_ref é 403. É o campo que amarra o "
                "teste ao documento que autorizou o teste.",
            ),
            dict(
                title="portão 3 · auditoria",
                tech="log_audit_event()",
                color=P["red"],
                desc="scan.create entra na trilha no MESMO commit do ScanRow. Ou os dois "
                "existem, ou nenhum: não há scan sem registro de quem pediu.",
            ),
        ],
        gap=24,
    )

    y += 8
    q = node(
        c,
        X,
        y,
        1776,
        None,
        "202 Accepted  →  arq enfileira  →  o worker acorda",
        "resposta imediata · job_id = scan-<uuid>",
        "A API responde antes de qualquer scanner rodar. Daqui em diante o cliente "
        "acompanha por GET /scans/{id} ou pelo stream de eventos, e o worker é quem "
        "faz o trabalho.",
        color=P["violet"],
    )
    y = q.y + q.h + 34

    # ---------- as fases
    c.pill(X, y, "AS 8 FASES DE run_scan()", P["rose"], filled=True)
    y += 40
    fases = [
        (
            "queued",
            "job aceito",
            P["gray"],
            "O ScanRow vai para RUNNING e a primeira fase é emitida no stream.",
        ),
        (
            "<scanner>_running",
            "um por vez",
            P["amber"],
            "Um adapter de cada vez, em sequência, não em paralelo. A fase leva o nome do "
            "scanner, e é por isso que a tela mostra nmap_running e zap_running.",
        ),
        (
            "dedup",
            "heuristic_dedup",
            P["accent"],
            "Determinístico: mantém a maior severidade por deduped_key. Chave rotacionada não "
            "colapsa, porque o fingerprint entra como discriminador.",
        ),
        (
            "ai_triage",
            "triage_batch",
            P["cyan"],
            "Tria TODO achado, inclusive low e info. Marca falso positivo provável, impacto de "
            "negócio, remediação e severidade ajustada.",
        ),
        (
            "reporting",
            "render_html",
            P["green"],
            "O relatório sai ANTES da persistência, de propósito: o caminho precisa existir "
            "para entrar na linha do scan, senão GET /reports/{id} dava 404 para sempre.",
        ),
        (
            "persisting",
            "_persist_findings",
            P["green"],
            "Grava os achados e fecha o estado. Nenhum scanner rodou? O scan termina FAILED, "
            "não DONE com zero achados.",
        ),
        (
            "done | failed",
            "estado final",
            P["rose"],
            "cleanup() de cada adapter roda no finally, tenha dado certo ou não.",
        ),
    ]
    cw, gap = 244, 12
    boxes = []
    for i, (nm, sub, col, desc) in enumerate(fases):
        bx = X + i * (cw + gap)
        b = chip(c, bx, y, cw, nm, sub, color=col)
        boxes.append(b)
        c.para(bx + 4, y + 88, desc, size=10.5, fill=t["ink_soft"], max_w=cw - 22)
    # pares consecutivos: os comprimentos diferem por 1 de proposito
    for a, b in zip(boxes, boxes[1:], strict=False):
        edge(c, (a.x + a.w, a.cy), (b.x - 2, b.cy), None)
    y += 220

    # ---------- saidas
    c.pill(X, y, "O QUE SAI", P["green"], filled=True)
    y += 40
    (o1, o2, o3, o4), yo = row(
        c,
        X,
        y,
        [430, 430, 430, 442],
        [
            dict(
                title="Relatório técnico",
                tech="GET /reports/{id}",
                color=P["green"],
                desc="HTML gerado pelo Jinja e gravado em disco. É o que o operador assina.",
            ),
            dict(
                title="Relatório executivo",
                tech="GET /reports/{id}/executive",
                color=P["green"],
                desc="HTML montado sob demanda, nunca gravado. Para quem decide, não para quem "
                "corrige.",
            ),
            dict(
                title="Compliance",
                tech="GET /reports/{id}/compliance",
                color=P["green"],
                desc="JSON com OWASP Top 10 2021, PCI DSS 4.0, LGPD, CWE Top 25, CVSS máximo e "
                "nota A–F.",
            ),
            dict(
                title="AI Fix Bundle",
                tech="GET /reports/{id}/ai-bundle",
                color=P["cyan"],
                desc="JSON de contrato, schema 1.0.0. É por aqui que um agente entra para "
                "consertar o código.",
            ),
        ],
        gap=24,
    )

    # ---------- SSE
    sy = yo + 12
    c.rect(X, sy, 1776, 92, r=12, fill=t["bg_alt"], stroke=P["violet"], sw=1.2, dash="6 5")
    c.text(
        X + 22,
        sy + 30,
        "ENQUANTO ISSO, NO STREAM",
        size=11,
        weight=700,
        fill=P["violet"],
        spacing=1.1,
        family=MONO,
    )
    c.para(
        X + 22,
        sy + 54,
        "GET /ui/api/events transmite phase e log em text/event-stream. O front do RoqueOS liga um EventSource com "
        "session-token curto na query — EventSource não carrega header, e a apiKey não vai na URL — deduplica fase repetida, "
        "segura no máximo 400 linhas no DOM e mantém um polling de 4 s como rede de segurança para quando o stream não sobe.",
        size=11.5,
        fill=t["ink_soft"],
        max_w=1740,
    )

    footer(
        c,
        "fonte: orchestrator/jobs/pipelines.py · orchestrator/api/routers/scans.py · "
        "orchestrator/api/routers/ui.py",
        "github.com/roqueribeiro/roqueos-shield",
        y=sy + 148,
    )
    c.h = int(sy + 172)
    return c
