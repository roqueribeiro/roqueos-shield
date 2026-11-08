"""Telas do RoqueShield dentro do RoqueOS - DIAGRAMA, nao captura."""

from .c4lib import *


def secoes():
    # funcao, nao constante: o idioma so e conhecido na hora de desenhar
    return [
        ("Dashboard", PALETTE["rose"]),
        (tr("Novo scan", "New scan"), "#f97316"),
        (tr("IA", "AI"), "#8b5cf6"),
        (tr("Escopo", "Scope"), "#22c55e"),
    ]


def chrome(c, x, y, w, h, sub, ativa):
    t = c.theme
    b = window(c, x, y, w, h, "RoqueShield", sub)
    c.rect(x + 1, y + 41, 150, h - 42, r=0, fill=t["node_fill"], opacity=0.5)
    yy = y + 56
    for nome, cor in secoes():
        yy = side_item(c, x + 10, yy, 132, nome, cor, active=(nome == ativa))
    c.line(x + 151, y + 41, x + 151, y + h, stroke=t["node_stroke"], sw=1)
    return b, x + 168, y + 58


SAIDA = "telas"


def draw(theme):
    c = Canvas(1900, 1560, theme)
    P = PALETTE
    t = theme
    title_block(
        c,
        tr("RoqueShield: as telas dentro do RoqueOS", "RoqueShield: the screens inside RoqueOS"),
        tr(
            "O app é admin-only, aparece no Launchpad só quando a capability pentest está "
            "ligada, e abre numa janela de 1280×860. Quatro seções, mais o detalhe de um scan.",
            "The app is admin-only, shows up in the Launchpad only when the pentest capability "
            "is on, and opens in a 1280×860 window. Four sections, plus the scan detail.",
        ),
    )
    brand(c)
    rotulo = tr("DIAGRAMA DE INTERFACE · NÃO É CAPTURA DE TELA", "UI DIAGRAM · NOT A SCREENSHOT")
    # alinhado pela direita: o rotulo muda de largura com o idioma
    c.pill(
        c.w - 48 - (text_width(rotulo, 10, weight=600, mono=True) + 24),
        176,
        rotulo,
        P["amber"],
        filled=True,
        size=10,
    )

    CW, CH = 880, 560
    GX, GY = 56, 232

    # ---------------- 1. dashboard
    b, ix, iy = chrome(c, GX, GY, CW, CH, "GET /pentest/api/ui/api/scans", "Dashboard")
    c.text(
        ix, iy, tr("Postura de segurança", "Security posture"), size=15, weight=650, fill=t["ink"]
    )
    grade(c, ix + 46, iy + 74, 40, "B", P["amber"])
    c.text(
        ix + 100,
        iy + 60,
        tr("índice 78 / 100", "score 78 / 100"),
        size=12,
        weight=600,
        fill=t["ink"],
    )
    c.text(
        ix + 100,
        iy + 80,
        tr(
            "CVSS máximo 8.6  ·  4 controles do CWE Top 25",
            "max CVSS 8.6  ·  4 CWE Top 25 controls",
        ),
        size=10.5,
        fill=t["ink_soft"],
    )
    c.text(
        ix + 100,
        iy + 100,
        "OWASP A01, A03, A05  ·  PCI DSS 6.2.4  ·  LGPD art. 46",
        size=10.5,
        fill=t["ink_soft"],
    )
    yy = iy + 140
    for nome, alvo, dist, est in [
        ("scan-8f2c", "https://juice-shop:3000", (2, 6, 11, 9, 4), "done"),
        ("scan-7a19", "github.com/acme/api", (0, 3, 7, 12, 2), "done"),
        ("scan-6b03", "acme/backend:1.4.2", (1, 1, 4, 6, 1), "running"),
    ]:
        c.rect(ix, yy, CW - 200, 62, r=9, fill=t["node_fill"], stroke=t["node_stroke"], sw=1)
        c.text(ix + 14, yy + 24, nome, size=11.5, weight=650, fill=t["ink"], family=MONO)
        c.text(ix + 110, yy + 24, alvo, size=10.5, fill=t["ink_soft"])
        col = P["green"] if est == "done" else P["accent"]
        c.pill(ix + CW - 200 - 92, yy + 12, est, col, size=9, h=18, filled=True)
        sevbar(c, ix + 14, yy + 38, CW - 240, dist)
        yy += 72
    c.para(
        GX,
        GY + CH + 16,
        tr(
            "Lista os scans com a distribuição de severidade em uma barra, o estado e a fase "
            "corrente. Vazio aqui usa o primitivo canônico de estado vazio do RoqueOS, não um "
            "texto solto.",
            "Lists the scans with the severity spread in one bar, the state and the current "
            "phase. When empty it uses the canonical RoqueOS empty-state primitive, not a "
            "loose line of text.",
        ),
        size=11,
        fill=t["ink_soft"],
        max_w=CW,
    )

    # ---------------- 2. wizard
    X2 = GX + CW + 36  # a segunda janela fecha na margem de 48
    novo = tr("Novo scan", "New scan")
    b, ix, iy = chrome(c, X2, GY, CW, CH, "POST /pentest/api/scans", novo)
    c.text(ix, iy, novo, size=15, weight=650, fill=t["ink"])
    stepper(
        c,
        ix + 8,
        iy + 44,
        CW - 260,
        [
            tr("alvo", "target"),
            tr("perfil", "profile"),
            tr("autenticação", "authentication"),
            tr("revisão", "review"),
        ],
        1,
    )
    yy = iy + 100
    for nome, desc, cor, sel in [
        (
            "web",
            tr("zap + nuclei sobre a aplicação", "zap + nuclei against the app"),
            P["accent"],
            False,
        ),
        (
            "network",
            tr("nmap e, se ligado, greenbone", "nmap and, if on, greenbone"),
            P["cyan"],
            True,
        ),
        (
            "full",
            tr("tudo o que o tipo de alvo aceita", "everything the target type supports"),
            P["rose"],
            False,
        ),
        (
            "exposure",
            tr(
                "trilha OSINT: dork, typosquat, segredo público",
                "OSINT track: dorks, typosquats, public secrets",
            ),
            P["violet"],
            False,
        ),
    ]:
        h = 54
        c.rect(
            ix,
            yy,
            CW - 200,
            h,
            r=9,
            fill=t["node_fill"],
            stroke=cor if sel else t["node_stroke"],
            sw=1.6 if sel else 1,
        )
        c.circle(
            ix + 20,
            yy + h / 2,
            7,
            fill=cor if sel else "none",
            stroke=cor if sel else t["ink_faint"],
            sw=1.5,
        )
        c.text(ix + 40, yy + 24, nome, size=11.5, weight=650, fill=t["ink"], family=MONO)
        c.text(ix + 40, yy + 40, desc, size=10, fill=t["ink_soft"])
        yy += 62
    c.rect(ix, yy + 6, CW - 200, 56, r=9, fill=t["node_fill"], stroke=P["red"], sw=1.4)
    c.circle(ix + 20, yy + 34, 7, fill=P["red"], stroke="none")
    c.text(
        ix + 40,
        yy + 28,
        tr(
            "Declaro que tenho autorização para testar este alvo",
            "I declare I am authorized to test this target",
        ),
        size=11,
        weight=600,
        fill=t["ink"],
    )
    c.text(
        ix + 40,
        yy + 46,
        tr(
            "authorization_ref  ·  campo obrigatório quando REQUIRE_AUTH_REF",
            "authorization_ref  ·  required when REQUIRE_AUTH_REF",
        ),
        size=9.5,
        fill=P["red"],
        family=MONO,
    )
    c.para(
        X2,
        GY + CH + 16,
        tr(
            "Quatro passos. A autenticação do passo 3 (headers e openapi_url) é efêmera: vai "
            "para o scanner e não persiste em lugar nenhum. O passo 4 exige a declaração de "
            "autorização antes de habilitar o botão.",
            "Four steps. The step 3 authentication (headers and openapi_url) is ephemeral: it "
            "goes to the scanner and is stored nowhere. Step 4 requires the authorization "
            "declaration before the button is enabled.",
        ),
        size=11,
        fill=t["ink_soft"],
        max_w=CW,
    )

    # ---------------- 3. detalhe
    GY2 = GY + CH + 110
    b, ix, iy = chrome(c, GX, GY2, CW, CH + 40, "SSE /pentest/api/ui/api/events", "Dashboard")
    c.text(ix, iy, "scan-8f2c  ·  https://juice-shop:3000", size=14, weight=650, fill=t["ink"])
    stepper(
        c,
        ix + 8,
        iy + 46,
        CW - 250,
        ["queued", "nmap", "zap", "dedup", "ai_triage", "report", "persist", "done"],
        4,
    )
    c.text(
        ix + 8,
        iy + 100,
        tr(
            "ai_triage  ·  62 %  ·  ao vivo pelo stream",
            "ai_triage  ·  62 %  ·  live from the stream",
        ),
        size=10.5,
        fill=P["accent"],
        family=MONO,
        weight=600,
    )
    yy = iy + 122
    ui_card(
        c,
        ix,
        yy,
        240,
        92,
        "Compliance",
        "OWASP A01 · A03 · A05\nPCI DSS 6.2.4\nLGPD art. 46",
        color=P["amber"],
        badge="B · 78",
    )
    ui_card(
        c,
        ix + 252,
        yy,
        214,
        92,
        tr("Achados", "Findings"),
        tr("2 críticos · 6 altos\n11 médios · 9 baixos", "2 critical · 6 high\n11 medium · 9 low"),
        color=P["red"],
        badge="32",
    )
    ui_card(
        c,
        ix + 478,
        yy,
        212,  # termina 22 px antes da borda da janela
        92,
        tr("Cobertura", "Coverage"),
        tr(
            "5 scanners rodaram\n1 pulado, e ele aparece", "5 scanners ran\n1 skipped, and it shows"
        ),
        color=P["green"],
        badge=tr("parcial", "partial"),
    )
    yy += 104
    c.text(ix, yy + 14, tr("Relatórios", "Reports"), size=11.5, weight=650, fill=t["ink"])
    for i, (fmt, cor) in enumerate(
        [("PDF", P["red"]), ("MD", P["accent"]), ("JSON", P["amber"]), ("CSV", P["green"])]
    ):
        c.pill(ix + i * 78, yy + 26, fmt, cor, size=10, h=26, filled=True)
    c.text(
        ix + 330,
        yy + 44,
        tr(
            "montados no cliente a partir do AI Fix Bundle",
            "built on the client from the AI Fix Bundle",
        ),
        size=10,
        fill=t["ink_faint"],
    )
    yy += 66
    c.rect(ix, yy, CW - 200, 96, r=9, fill=t["node_fill"], stroke=t["node_stroke"], sw=1)
    c.text(ix + 14, yy + 22, tr("Log ao vivo", "Live log"), size=10.5, weight=650, fill=t["ink"])
    for i, ln in enumerate(
        [
            tr("[zap] spider concluído: 148 URLs", "[zap] spider done: 148 URLs"),
            tr(
                "[zap] fila passiva vazia, 512 alertas paginados",
                "[zap] passive queue empty, 512 alerts paged",
            ),
            tr(
                "[ai] triage 20/32: 3 marcados falso positivo provável",
                "[ai] triage 20/32: 3 flagged as likely false positive",
            ),
        ]
    ):
        c.text(ix + 14, yy + 44 + i * 16, ln, size=9.5, fill=t["ink_soft"], family=MONO)
    c.para(
        GX,
        GY2 + CH + 56,
        tr(
            "O stepper acompanha as 8 fases pelo SSE, com polling de 4 s como rede de "
            "segurança. Os quatro formatos são montados no navegador a partir do AI Fix "
            "Bundle: o servidor emite o bundle, e o front faz PDF, MD, JSON e CSV.",
            "The stepper follows the 8 phases over SSE, with a 4 s poll as a safety net. "
            "The four formats are built in the browser from the AI Fix Bundle: the server "
            "emits the bundle, and the front end makes PDF, MD, JSON and CSV.",
        ),
        size=11,
        fill=t["ink_soft"],
        max_w=CW,
    )

    # ---------------- 4. IA e escopo
    b, ix, iy = chrome(c, X2, GY2, CW, CH + 40, "POST /pentest/ai · /pentest/scope", tr("IA", "AI"))
    c.text(ix, iy, tr("Provedor de IA", "AI provider"), size=15, weight=650, fill=t["ink"])
    yy = iy + 30
    for rot, val in [
        (
            tr("Modelo", "Model"),
            tr(
                "anthropic/claude-…  ·  lista vem do provedor, não digitada",
                "anthropic/claude-…  ·  list comes from the provider, not typed",
            ),
        ),
        (
            "Fallback",
            tr(
                "ollama/llama3  ·  usado quando o principal falha",
                "ollama/llama3  ·  used when the primary fails",
            ),
        ),
        (
            tr("Endpoint local", "Local endpoint"),
            tr(
                "http://ollama:11434  ·  para prompt que não pode sair",
                "http://ollama:11434  ·  for prompts that cannot leave",
            ),
        ),
    ]:
        c.text(ix, yy + 16, rot, size=10, fill=t["ink_faint"], family=MONO)
        c.rect(ix + 120, yy, CW - 330, 30, r=7, fill=t["node_fill"], stroke=t["node_stroke"], sw=1)
        c.text(ix + 134, yy + 20, val, size=10.5, fill=t["ink_soft"])
        yy += 42
    c.para(
        ix,
        yy + 6,
        tr(
            "A chave é gravada cifrada em AES pelo roqueos-server e NUNCA volta "
            "para a tela: o GET devolve mascarado.",
            "roqueos-server stores the key AES-encrypted and it NEVER comes back "
            "to the screen: the GET returns it masked.",
        ),
        size=10.5,
        fill=P["amber"],
        max_w=CW - 210,
    )
    yy += 56
    c.line(ix, yy, ix + CW - 210, yy, stroke=t["node_stroke"], sw=1)
    yy += 22
    c.text(ix, yy + 12, tr("Escopo", "Scope"), size=15, weight=650, fill=t["ink"])
    yy += 34
    for rot, est, cor in [
        ("lab-only", tr("ligado", "on"), P["green"]),
        (
            tr("exigir authorization_ref", "require authorization_ref"),
            tr("ligado", "on"),
            P["green"],
        ),
        ("allow-list", "localhost · juice-shop · dvwa · webgoat", P["accent"]),
    ]:
        c.rect(ix, yy, CW - 210, 38, r=8, fill=t["node_fill"], stroke=t["node_stroke"], sw=1)
        c.text(ix + 14, yy + 24, rot, size=11, weight=600, fill=t["ink"])
        c.text(
            ix + CW - 224, yy + 24, est, size=10, fill=cor, anchor="end", family=MONO, weight=600
        )
        yy += 46
    c.para(
        X2,
        GY2 + CH + 56,
        tr(
            "As duas telas de governança. O escopo daqui é o mesmo gate que o servidor aplica "
            "no POST /scans: mudar aqui muda o que o portão 1 aceita, e não existe caminho que "
            "escape dele.",
            "The two governance screens. The scope here is the same gate the server enforces "
            "on POST /scans: changing it here changes what gate 1 accepts, and there is no "
            "path around it.",
        ),
        size=11,
        fill=t["ink_soft"],
        max_w=CW,
    )

    footer(
        c,
        tr("fonte: ", "source: ") + "roqueos-front/src/components/roqueos/apps/ROSPentest.vue · "
        "src/config/apps.js · src/services/api/pentest.js · "
        "roqueos-server/src/modules/pentest/",
        "github.com/roqueribeiro/roqueos-shield",
        y=GY2 + CH + 160,
    )
    c.h = int(GY2 + CH + 184)
    return c
