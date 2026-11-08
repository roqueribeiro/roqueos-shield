"""A esteira de um scan, fase a fase."""

from .c4lib import *

SAIDA = "esteira"


def draw(theme):
    c = Canvas(1900, 1190, theme)
    P = PALETTE
    t = theme
    title_block(
        c,
        tr("RoqueShield: a esteira de um scan", "RoqueShield: the scan pipeline"),
        tr(
            "Do POST até o relatório. Os três portões da entrada acontecem antes de qualquer "
            "pacote sair, e a fase corrente é transmitida por SSE enquanto tudo isso roda.",
            "From the POST to the report. The three entry gates run before any packet "
            "leaves, and the current phase is streamed over SSE while all of this runs.",
        ),
    )
    brand(c)

    X = 56
    # ---------- entrada e portoes
    c.pill(X, 176, tr("ENTRADA", "ENTRY"), P["accent"], filled=True)
    y = 216
    (e1, e2, e3, e4), y = row(
        c,
        X,
        y,
        [424, 424, 424, 432],
        [
            dict(
                title="POST /scans",
                tech="api/routers/scans.py",
                color=P["accent"],
                desc=tr(
                    "target_id, scanners, profile, options, auth. O corpo com header de "
                    "autenticação do alvo é separado do que persiste: split_scan_auth guarda "
                    "o efêmero em memória e redige o resto na auditoria.",
                    "target_id, scanners, profile, options, auth. The target auth headers are "
                    "split from what gets stored: split_scan_auth keeps the ephemeral part in "
                    "memory and redacts the rest in the audit trail.",
                ),
            ),
            dict(
                title=tr("portão 1 · escopo", "gate 1 · scope"),
                tech="validate_target_value()",
                color=P["red"],
                desc=tr(
                    "Alvo fora do escopo devolve 403 e o scan não nasce. Com lab-only "
                    "ligado, endereço interno só passa se estiver na allow-list.",
                    "A target out of scope gets 403 and the scan is never created. "
                    "With lab-only on, an internal address passes only if it is on the allow-list.",
                ),
            ),
            dict(
                title=tr("portão 2 · autorização", "gate 2 · authorization"),
                tech="REQUIRE_AUTH_REF",
                color=P["red"],
                desc=tr(
                    "Quando ligado, scan sem authorization_ref é 403. É o campo que amarra o "
                    "teste ao documento que autorizou o teste.",
                    "When on, a scan without authorization_ref gets 403. It is the field that "
                    "ties the test to the document that authorized it.",
                ),
            ),
            dict(
                title=tr("portão 3 · auditoria", "gate 3 · audit"),
                tech="log_audit_event()",
                color=P["red"],
                desc=tr(
                    "scan.create entra na trilha no MESMO commit do ScanRow. Ou os dois "
                    "existem, ou nenhum: não há scan sem registro de quem pediu.",
                    "scan.create goes into the trail in the SAME commit as the ScanRow. Both "
                    "exist or neither does: no scan without a record of who asked for it.",
                ),
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
        tr(
            "202 Accepted  →  arq enfileira  →  o worker acorda",
            "202 Accepted  →  arq enqueues  →  the worker wakes up",
        ),
        tr(
            "resposta imediata · job_id = scan-<uuid>",
            "immediate response · job_id = scan-<uuid>",
        ),
        tr(
            "A API responde antes de qualquer scanner rodar. Daqui em diante o cliente "
            "acompanha por GET /scans/{id} ou pelo stream de eventos, e o worker é quem "
            "faz o trabalho.",
            "The API answers before any scanner runs. From here on the client follows "
            "along through GET /scans/{id} or the event stream, and the worker does the "
            "work.",
        ),
        color=P["violet"],
    )
    y = q.y + q.h + 34

    # ---------- as fases
    c.pill(
        X, y, tr("AS 8 FASES DE run_scan()", "THE 8 PHASES OF run_scan()"), P["rose"], filled=True
    )
    y += 40
    fases = [
        (
            "queued",
            tr("job aceito", "job accepted"),
            P["gray"],
            tr(
                "O ScanRow vai para RUNNING e a primeira fase é emitida no stream.",
                "The ScanRow moves to RUNNING and the first phase goes out on the stream.",
            ),
        ),
        (
            "<scanner>_running",
            tr("um por vez", "one at a time"),
            P["amber"],
            tr(
                "Um adapter de cada vez, em sequência, não em paralelo. A fase leva o nome do "
                "scanner, e é por isso que a tela mostra nmap_running e zap_running.",
                "One adapter at a time, in sequence, not in parallel. The phase carries the "
                "scanner name, which is why the screen shows nmap_running and zap_running.",
            ),
        ),
        (
            "dedup",
            "heuristic_dedup",
            P["accent"],
            tr(
                "Determinístico: mantém a maior severidade por deduped_key. Chave rotacionada não "
                "colapsa, porque o fingerprint entra como discriminador.",
                "Deterministic: keeps the highest severity per deduped_key. A rotated key does "
                "not collapse, because the fingerprint is part of the key.",
            ),
        ),
        (
            "ai_triage",
            "triage_batch",
            P["cyan"],
            tr(
                "Tria TODO achado, inclusive low e info. Marca falso positivo provável, impacto de "
                "negócio, remediação e severidade ajustada.",
                "Triages EVERY finding, low and info included. Flags likely false positives, "
                "business impact, remediation and adjusted severity.",
            ),
        ),
        (
            "reporting",
            "render_html",
            P["green"],
            tr(
                "O relatório sai ANTES da persistência, de propósito: o caminho precisa existir "
                "para entrar na linha do scan, senão GET /reports/{id} dava 404 para sempre.",
                "The report comes out BEFORE persistence, on purpose: its path must exist to "
                "go into the scan row, or GET /reports/{id} would return 404 forever.",
            ),
        ),
        (
            "persisting",
            "_persist_findings",
            P["green"],
            tr(
                "Grava os achados e fecha o estado. Nenhum scanner rodou? O scan termina FAILED, "
                "não DONE com zero achados.",
                "Writes the findings and closes the state. No scanner ran? The scan ends "
                "FAILED, not DONE with zero findings.",
            ),
        ),
        (
            "done | failed",
            tr("estado final", "final state"),
            P["rose"],
            tr(
                "cleanup() de cada adapter roda no finally, tenha dado certo ou não.",
                "Each adapter's cleanup() runs in finally, whether it worked or not.",
            ),
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
    c.pill(X, y, tr("O QUE SAI", "WHAT COMES OUT"), P["green"], filled=True)
    y += 40
    (o1, o2, o3, o4), yo = row(
        c,
        X,
        y,
        [424, 424, 424, 432],
        [
            dict(
                title=tr("Relatório técnico", "Technical report"),
                tech="GET /reports/{id}",
                color=P["green"],
                desc=tr(
                    "HTML gerado pelo Jinja e gravado em disco. É o que o operador assina.",
                    "HTML rendered by Jinja and written to disk. It is what the operator signs.",
                ),
            ),
            dict(
                title=tr("Relatório executivo", "Executive report"),
                tech="GET /reports/{id}/executive",
                color=P["green"],
                desc=tr(
                    "HTML montado sob demanda, nunca gravado. Para quem decide, não para quem "
                    "corrige.",
                    "HTML built on demand, never stored. For whoever decides, not whoever fixes.",
                ),
            ),
            dict(
                title="Compliance",
                tech="GET /reports/{id}/compliance",
                color=P["green"],
                desc=tr(
                    "JSON com OWASP Top 10 2021, PCI DSS 4.0, LGPD, CWE Top 25, CVSS máximo e "
                    "nota A–F.",
                    "JSON with OWASP Top 10 2021, PCI DSS 4.0, LGPD, CWE Top 25, maximum CVSS "
                    "and an A–F grade.",
                ),
            ),
            dict(
                title="AI Fix Bundle",
                tech="GET /reports/{id}/ai-bundle",
                color=P["cyan"],
                desc=tr(
                    "JSON de contrato, schema 1.0.0. É por aqui que um agente entra para "
                    "consertar o código.",
                    "Contract JSON, schema 1.0.0. This is the way in for an agent that will "
                    "fix the code.",
                ),
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
        tr("ENQUANTO ISSO, NO STREAM", "MEANWHILE, ON THE STREAM"),
        size=11,
        weight=700,
        fill=P["violet"],
        spacing=1.1,
        family=MONO,
    )
    c.para(
        X + 22,
        sy + 54,
        tr(
            "GET /ui/api/events transmite phase e log em text/event-stream. O EventSource "
            "não manda header, então este é o único endpoint que aceita a credencial em "
            "?token=. A tela do RoqueOS deduplica fase repetida, segura no máximo 400 "
            "linhas no DOM e mantém um polling de 4 s como rede de segurança para quando o "
            "stream não sobe.",
            "GET /ui/api/events streams phase and log as text/event-stream. EventSource "
            "cannot send headers, so this is the only endpoint that accepts the credential "
            "in ?token=. The RoqueOS screen drops "
            "repeated phases, keeps at most 400 lines in the DOM and runs a 4 s poll as a "
            "safety net for when the stream does not come up.",
        ),
        size=11.5,
        fill=t["ink_soft"],
        max_w=1740,
    )

    footer(
        c,
        tr("fonte: ", "source: ")
        + "orchestrator/jobs/pipelines.py · orchestrator/api/routers/scans.py · "
        "orchestrator/api/routers/ui.py",
        "github.com/roqueribeiro/roqueos-shield",
        y=sy + 148,
    )
    c.h = int(sy + 172)
    return c
