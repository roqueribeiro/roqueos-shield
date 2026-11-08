"""C4: Codigo: ciclo de vida do adapter e o contrato do silencio."""

from .c4lib import *

SAIDA = "codigo"


def draw(theme):
    c = Canvas(1880, 1400, theme)
    P = PALETTE
    t = theme
    title_block(
        c,
        tr("RoqueShield: ciclo de vida de um scanner", "RoqueShield: lifecycle of a scanner"),
        tr(
            "O nível 4 desce ao código de _run_adapter(), em orchestrator/jobs/pipelines.py. "
            "Cada passo tem uma saída de erro explícita, e nenhuma delas devolve lista vazia.",
            "Level 4 goes down to the code of _run_adapter(), in orchestrator/jobs/pipelines.py. "
            "Every step has an explicit error exit, and none of them returns an empty list.",
        ),
        level=tr("C4  ·  CÓDIGO", "C4  ·  CODE"),
    )
    brand(c)

    LX, LW = 56, 620
    c.text(
        LX,
        196,
        tr("O CONTRATO ScannerAdapter", "THE ScannerAdapter CONTRACT"),
        size=11,
        weight=700,
        fill=P["rose"],
        spacing=1.1,
        family=MONO,
    )
    c.para(
        LX,
        220,
        tr(
            "orchestrator/adapters/base.py: cinco métodos assíncronos, mais um "
            "cleanup opcional detectado por getattr. Quinze adapters implementam "
            "este Protocol, e o pipeline não sabe o nome de nenhum deles.",
            "orchestrator/adapters/base.py: five async methods, plus an optional "
            "cleanup detected through getattr. Fifteen adapters implement this "
            "Protocol, and the pipeline does not know the name of any of them.",
        ),
        size=11,
        fill=t["ink_soft"],
        max_w=LW,
    )

    y = 286
    s1 = step(
        c,
        LX,
        y,
        LW,
        1,
        "await adapter.health()",
        tr(
            "Round-trip de verdade, não construção de cliente. O censys passava no "
            "health só instanciando o SDK, e a busca falhava depois, calada.",
            "A real round-trip, not building a client. censys used to pass health "
            "just by instantiating the SDK, and the search then failed silently.",
        ),
        color=P["rose"],
    )
    y = s1.y + s1.h + 46
    s2 = step(
        c,
        LX,
        y,
        LW,
        2,
        "handle = await adapter.start_scan(target, options)",
        tr(
            "Handle vazio ou sem native_id levanta AdapterUnavailableError. Aqui o "
            "adapter recusa tipo de alvo incompatível com ValueError.",
            "An empty handle, or one with no native_id, raises AdapterUnavailableError. "
            "This is where the adapter rejects an unsupported target type with ValueError.",
        ),
        color=P["rose"],
    )
    y = s2.y + s2.h + 46
    s3 = step(
        c,
        LX,
        y,
        LW,
        3,
        "loop: await adapter.poll(handle)",
        tr(
            "A cada 5 s, teto de 1800 s. FAILED e CANCELED levantam; estouro de timeout "
            "levanta. poll lê task.result(), não task.done(): terminar não é dar certo.",
            "Every 5 s, capped at 1800 s. FAILED and CANCELED raise; a timeout raises. "
            "poll reads task.result(), not task.done(): finishing is not succeeding.",
        ),
        color=P["rose"],
    )
    y = s3.y + s3.h + 46
    s4 = step(
        c,
        LX,
        y,
        LW,
        4,
        "raw = await adapter.fetch_results(handle)",
        tr(
            "Report ausente, vazio ou ilegível vira ScanIntegrityError. Nunca {}. "
            'Foi assim que gitleaks, dnstwist e kube_bench diziam "limpo" sem ter lido '
            "nada.",
            "A missing, empty or unreadable report becomes ScanIntegrityError. Never {}. "
            'That is how gitleaks, dnstwist and kube_bench used to say "clean" without '
            "reading anything.",
        ),
        color=P["rose"],
    )
    y = s4.y + s4.h + 46
    s5 = step(
        c,
        LX,
        y,
        LW,
        5,
        "findings = await adapter.normalize(raw)",
        tr(
            "Traduz a saída da ferramenta para Finding, com severity, confidence, CWE e evidência.",
            "Translates the tool output into Finding, with severity, confidence, CWE and evidence.",
        ),
        color=P["rose"],
    )
    y = s5.y + s5.h + 46
    s6 = step(
        c,
        LX,
        y,
        LW,
        6,
        "raw.coverage_gaps  →  Finding INFO",
        tr(
            "A conversão acontece em UM lugar. Quinze adapters lembrarem disso é "
            "convenção; um lugar é mecanismo.",
            "The conversion happens in ONE place. Fifteen adapters remembering it is "
            "a convention; one place is a mechanism.",
        ),
        color=P["amber"],
    )
    y = s6.y + s6.h + 46
    s7 = step(
        c,
        LX,
        y,
        LW,
        7,
        "finally: await adapter.cleanup(handle)",
        tr(
            "Cancela a task e apaga o workdir. Roda mesmo quando o passo anterior levantou.",
            "Cancels the task and deletes the workdir. Runs even when an earlier step raised.",
        ),
        color=P["green"],
    )

    for a, b in ((s1, s2), (s2, s3), (s3, s4), (s4, s5), (s5, s6), (s6, s7)):
        edge(c, (a.cx, a.y + a.h), (b.cx, b.y - 2))

    # saídas de erro, à direita da coluna
    EX = 740
    for src, txt in (
        (s1, "AdapterUnavailableError"),
        (s2, "AdapterUnavailableError"),
        (s3, "FAILED · CANCELED · timeout"),
        (s4, "ScanIntegrityError"),
    ):
        edge(c, (src.x + src.w, src.cy), (EX - 12, src.cy), None, color=P["red"], dash="5 4")
        c.text(EX, src.cy + 4, txt, size=10.5, fill=P["red"], weight=600, family=MONO)

    c.rect(
        EX - 16,
        s1.y - 6,
        336,
        s4.y + s4.h - s1.y + 12,
        r=10,
        fill="none",
        stroke=P["red"],
        sw=1.2,
        dash="6 5",
    )
    c.text(
        EX - 16 + 336,
        s4.y + s4.h + 26,
        tr("↓ tudo isto cai no mesmo lugar", "↓ all of this lands in one place"),
        size=10.5,
        fill=P["red"],
        anchor="end",
        weight=600,
        family=MONO,
    )
    ss = step(
        c,
        EX - 16,
        s5.y,
        336,
        "×",
        tr("scanners_skipped[nome] = motivo", "scanners_skipped[name] = reason"),
        tr(
            "Aparece no relatório, na resposta da API e na tela do RoqueShield. "
            "E quando NENHUM scanner rodou, o scan inteiro termina FAILED, não DONE "
            "com zero achados.",
            "Shows up in the report, in the API response and on the RoqueShield screen. "
            "And when NO scanner ran, the whole scan ends FAILED, not DONE with zero "
            "findings.",
        ),
        color=P["red"],
    )

    # ---------- coluna direita: os três níveis e o gate
    RX = 1136
    yy = table(
        c,
        RX,
        196,
        688,
        [
            tr("situação", "situation"),
            tr("o que o adapter faz", "what the adapter does"),
            tr("onde o usuário vê", "where the user sees it"),
        ],
        [
            [
                tr("Rodou e não achou", "Ran, found nothing"),
                tr("devolve []", "returns []"),
                tr("achado nenhum, cobertura completa", "no findings, full coverage"),
            ],
            [
                tr("Não deu para verificar", "Could not check"),
                "raise ScanIntegrityError",
                "scanners_skipped, coverage_complete: false",
            ],
            [
                tr("Verificou em parte", "Checked only part"),
                tr("preenche RawResults.coverage_gaps", "fills RawResults.coverage_gaps"),
                tr("achado INFO no relatório", "INFO finding in the report"),
            ],
        ],
        [204, 236, 248],
        color=P["rose"],
        title=tr("Os três níveis, e nunca o silêncio", "The three levels, and never silence"),
    )

    yy += 34
    c.text(
        RX,
        yy,
        tr("O MECANISMO, SENÃO ISTO É DECORAÇÃO", "THE MECHANISM, OR THIS IS DECORATION"),
        size=11,
        weight=700,
        fill=P["cyan"],
        spacing=1.1,
        family=MONO,
    )
    yy += 24
    g = step(
        c,
        RX,
        yy,
        688,
        "✓",
        "scripts/check_no_silence.py",
        tr(
            'Job "Contrato do silencio" no CI. Compara o CÓDIGO com a regra por AST, '
            "não por grep. Reprova except que termina vazio dentro do ciclo de vida do "
            "scan, poll que decide por task.done() sem ler o resultado, e dicionário de "
            "sucesso fabricado dentro de except. Escape explícito: "
            "# silencio-ok: motivo. O motivo escrito é o que denuncia se um dia "
            "liberarem um silêncio de verdade.",
            'CI job "Contrato do silencio". Checks the CODE against the rule by AST, '
            "not by grep. Fails an except that ends empty inside the scan lifecycle, a "
            "poll that decides on task.done() without reading the result, and a success "
            "dict fabricated inside except. Explicit escape: # silencio-ok: reason. The "
            "written reason is what gives it away if someone ever lets a real silence "
            "through.",
        ),
        color=P["cyan"],
    )
    yy = g.y + g.h + 26

    yy = table(
        c,
        RX,
        yy,
        688,
        [
            tr("burla que passou pelo gate v1", "bypass that beat gate v1"),
            tr("o que mudou", "what changed"),
        ],
        [
            [
                tr(
                    "if _ESTRITO: raise com a flag desligada",
                    "if _ESTRITO: raise with the flag off",
                ),
                tr(
                    "raise sob condição constante não conta",
                    "raise under a constant condition does not count",
                ),
            ],
            [
                tr(
                    ".append numa lista local que ninguém lê",
                    ".append to a local list nobody reads",
                ),
                tr(
                    "o destino precisa se chamar gap/erro/lacuna/errors",
                    "the target must be named gap/erro/lacuna/errors",
                ),
            ],
            [
                tr(
                    "silêncio movido para um helper _ler_report()",
                    "silence moved into a _ler_report() helper",
                ),
                tr(
                    "num adapter, toda função conta, menos health e cleanup",
                    "in an adapter every function counts, except health and cleanup",
                ),
            ],
            [
                'payload = texto if texto.strip() else ""',
                tr(
                    "fetch_results que constrói vazio e nunca levanta reprova",
                    "fetch_results that builds empty and never raises fails",
                ),
            ],
        ],
        [352, 336],
        color=P["amber"],
        title=tr(
            "O gate tem gate: 4 burlas viraram teste",
            "The gate has a gate: 4 bypasses became tests",
        ),
    )
    yy += 22
    c.para(
        RX,
        yy + 14,
        tr(
            "Uma auditoria adversarial burlou a primeira versão do gate de quatro formas e "
            "reintroduziu o silêncio no nmap com o CI verde. Um controle que o autor do "
            "código contorna em quatro tentativas não é controle. As quatro viraram "
            "tests/unit/test_gate_do_silencio.py.",
            "An adversarial audit beat the first version of the gate in four ways and put "
            "the silence back into nmap with CI green. A control the code author gets around "
            "in four tries is not a control. All four became "
            "tests/unit/test_gate_do_silencio.py.",
        ),
        size=11,
        fill=t["ink_soft"],
        max_w=688,
    )

    c.h = int(max(s7.y + s7.h, ss.y + ss.h, yy + 120) + 96)
    footer(
        c,
        tr("C4 model · nível 4 de 4 · fonte: ", "C4 model · level 4 of 4 · source: ")
        + "orchestrator/jobs/pipelines.py · orchestrator/adapters/base.py · "
        "scripts/check_no_silence.py",
        "github.com/roqueribeiro/roqueos-shield",
        y=c.h - 26,
    )
    return c
