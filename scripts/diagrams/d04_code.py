"""C4 — Codigo: ciclo de vida do adapter e o contrato do silencio."""

from .c4lib import *

SAIDA = "c4-code"


def draw(theme):
    c = Canvas(1880, 1400, theme)
    P = PALETTE
    t = theme
    title_block(
        c,
        "RoqueShield — Ciclo de vida de um scanner",
        "O nível 4 desce ao código de _run_adapter(), em orchestrator/jobs/pipelines.py. "
        "Cada passo tem uma saída de erro explícita, e nenhuma delas devolve lista vazia.",
        level="C4  ·  CÓDIGO",
    )
    brand(c)

    LX, LW = 56, 620
    c.text(
        LX,
        196,
        "O CONTRATO ScannerAdapter",
        size=11,
        weight=700,
        fill=P["rose"],
        spacing=1.1,
        family=MONO,
    )
    c.para(
        LX,
        220,
        "orchestrator/adapters/base.py — cinco métodos assíncronos, mais um "
        "cleanup opcional detectado por getattr. Quinze adapters implementam "
        "este Protocol, e o pipeline não sabe o nome de nenhum deles.",
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
        "Round-trip de verdade, não construção de cliente. O censys passava no "
        "health só instanciando o SDK, e a busca falhava depois, calada.",
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
        "Handle vazio ou sem native_id levanta AdapterUnavailableError. Aqui o "
        "adapter recusa tipo de alvo incompatível com ValueError.",
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
        "A cada 5 s, teto de 1800 s. FAILED e CANCELED levantam; estouro de timeout "
        "levanta. poll lê task.result(), não task.done(): terminar não é dar certo.",
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
        "Report ausente, vazio ou ilegível vira ScanIntegrityError. Nunca {}. "
        'Foi assim que gitleaks, dnstwist e kube_bench diziam "limpo" sem ter lido '
        "nada.",
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
        "Traduz a saída da ferramenta para Finding, com severity, confidence, CWE e evidência.",
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
        "A conversão acontece em UM lugar. Quinze adapters lembrarem disso é "
        "convenção; um lugar é mecanismo.",
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
        "Cancela a task e apaga o workdir. Roda mesmo quando o passo anterior levantou.",
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
        "↓ tudo isto cai no mesmo lugar",
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
        "scanners_skipped[nome] = motivo",
        "Aparece no relatório, na resposta da API e na tela do RoqueShield. "
        "E quando NENHUM scanner rodou, o scan inteiro termina FAILED — não DONE "
        "com zero achados.",
        color=P["red"],
    )

    # ---------- coluna direita: os três níveis e o gate
    RX = 1136
    yy = table(
        c,
        RX,
        196,
        688,
        ["situação", "o que o adapter faz", "onde o usuário vê"],
        [
            ["Rodou e não achou", "devolve []", "achado nenhum, cobertura completa"],
            [
                "Não deu para verificar",
                "raise ScanIntegrityError",
                "scanners_skipped, coverage_complete: false",
            ],
            ["Verificou em parte", "preenche RawResults.coverage_gaps", "achado INFO no relatório"],
        ],
        [204, 236, 248],
        color=P["rose"],
        title="Os três níveis — e nunca o silêncio",
    )

    yy += 34
    c.text(
        RX,
        yy,
        "O MECANISMO, SENÃO ISTO É DECORAÇÃO",
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
        'Job "Contrato do silencio" no CI. Compara o CÓDIGO com a regra por AST, '
        "não por grep. Reprova except que termina vazio dentro do ciclo de vida do "
        "scan, poll que decide por task.done() sem ler o resultado, e dicionário de "
        "sucesso fabricado dentro de except. Escape explícito: "
        "# silencio-ok: motivo — e o motivo escrito é o que denuncia se um dia "
        "liberarem um silêncio de verdade.",
        color=P["cyan"],
    )
    yy = g.y + g.h + 26

    yy = table(
        c,
        RX,
        yy,
        688,
        ["burla que passou pelo gate v1", "o que mudou"],
        [
            ["if _ESTRITO: raise com a flag desligada", "raise sob condição constante não conta"],
            [
                ".append numa lista local que ninguém lê",
                "o destino precisa se chamar gap/erro/lacuna/errors",
            ],
            [
                "silêncio movido para um helper _ler_report()",
                "num adapter, toda função conta, menos health e cleanup",
            ],
            [
                'payload = texto if texto.strip() else ""',
                "fetch_results que constrói vazio e nunca levanta reprova",
            ],
        ],
        [352, 336],
        color=P["amber"],
        title="O gate tem gate: 4 burlas viraram teste",
    )
    yy += 22
    c.para(
        RX,
        yy + 14,
        "Uma auditoria adversarial burlou a primeira versão do gate de quatro formas e "
        "reintroduziu o silêncio no nmap com o CI verde. Um controle que o autor do "
        "código contorna em quatro tentativas não é controle. As quatro viraram "
        "tests/unit/test_gate_do_silencio.py.",
        size=11,
        fill=t["ink_soft"],
        max_w=688,
    )

    c.h = int(max(s7.y + s7.h, ss.y + ss.h, yy + 120) + 96)
    footer(
        c,
        "C4 model · nível 4 de 4 · fonte: orchestrator/jobs/pipelines.py · "
        "orchestrator/adapters/base.py · scripts/check_no_silence.py",
        "github.com/roqueribeiro/roqueos-shield",
        y=c.h - 26,
    )
    return c
