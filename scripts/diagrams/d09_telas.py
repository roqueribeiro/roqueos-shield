"""Telas do RoqueShield dentro do RoqueOS - DIAGRAMA, nao captura."""

from .c4lib import *

SEC = [
    ("Dashboard", PALETTE["rose"]),
    ("Novo scan", "#f97316"),
    ("IA", "#8b5cf6"),
    ("Escopo", "#22c55e"),
]


def chrome(c, x, y, w, h, sub, ativa):
    t = c.theme
    b = window(c, x, y, w, h, "RoqueShield", sub)
    c.rect(x + 1, y + 41, 150, h - 42, r=0, fill=t["node_fill"], opacity=0.5)
    yy = y + 56
    for nome, cor in SEC:
        yy = side_item(c, x + 10, yy, 132, nome, cor, active=(nome == ativa))
    c.line(x + 151, y + 41, x + 151, y + h, stroke=t["node_stroke"], sw=1)
    return b, x + 168, y + 58


SAIDA = "telas-roqueos"


def draw(theme):
    c = Canvas(1900, 1560, theme)
    P = PALETTE
    t = theme
    title_block(
        c,
        "RoqueShield — as telas dentro do RoqueOS",
        "O app é admin-only, aparece no Launchpad só quando a capability pentest está "
        "ligada, e abre numa janela de 1280×860. Quatro seções, mais o detalhe de um scan.",
    )
    brand(c)
    c.pill(
        1420, 176, "DIAGRAMA DE INTERFACE · NÃO É CAPTURA DE TELA", P["amber"], filled=True, size=10
    )

    CW, CH = 880, 560
    GX, GY = 56, 232

    # ---------------- 1. dashboard
    b, ix, iy = chrome(c, GX, GY, CW, CH, "GET /pentest/api/ui/api/scans", "Dashboard")
    c.text(ix, iy, "Postura de segurança", size=15, weight=650, fill=t["ink"])
    grade(c, ix + 46, iy + 74, 40, "B", P["amber"])
    c.text(ix + 100, iy + 60, "índice 78 / 100", size=12, weight=600, fill=t["ink"])
    c.text(
        ix + 100,
        iy + 80,
        "CVSS máximo 8.6  ·  4 controles do CWE Top 25",
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
        "Lista os scans com a distribuição de severidade em uma barra, o estado e a fase "
        "corrente. Vazio aqui usa o primitivo canônico de estado vazio do RoqueOS, não um "
        "texto solto.",
        size=11,
        fill=t["ink_soft"],
        max_w=CW,
    )

    # ---------------- 2. wizard
    X2 = GX + CW + 44
    b, ix, iy = chrome(c, X2, GY, CW, CH, "POST /pentest/api/scans", "Novo scan")
    c.text(ix, iy, "Novo scan", size=15, weight=650, fill=t["ink"])
    stepper(c, ix + 8, iy + 44, CW - 260, ["alvo", "perfil", "autenticação", "revisão"], 1)
    yy = iy + 100
    for nome, desc, cor, sel in [
        ("web", "zap + nuclei sobre a aplicação", P["accent"], False),
        ("network", "nmap e, se ligado, greenbone", P["cyan"], True),
        ("full", "tudo o que o tipo de alvo aceita", P["rose"], False),
        ("exposure", "trilha OSINT: dork, typosquat, segredo público", P["violet"], False),
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
        "Declaro que tenho autorização para testar este alvo",
        size=11,
        weight=600,
        fill=t["ink"],
    )
    c.text(
        ix + 40,
        yy + 46,
        "authorization_ref  ·  campo obrigatório quando REQUIRE_AUTH_REF",
        size=9.5,
        fill=P["red"],
        family=MONO,
    )
    c.para(
        X2,
        GY + CH + 16,
        "Quatro passos. A autenticação do passo 3 (headers e openapi_url) é efêmera: vai "
        "para o scanner e não persiste em lugar nenhum. O passo 4 exige a declaração de "
        "autorização antes de habilitar o botão.",
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
        "ai_triage  ·  62 %  ·  ao vivo pelo stream",
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
        250,
        92,
        "Compliance",
        "OWASP A01 · A03 · A05\nPCI DSS 6.2.4\nLGPD art. 46",
        color=P["amber"],
        badge="B · 78",
    )
    ui_card(
        c,
        ix + 262,
        yy,
        220,
        92,
        "Achados",
        "2 críticos · 6 altos\n11 médios · 9 baixos",
        color=P["red"],
        badge="32",
    )
    ui_card(
        c,
        ix + 494,
        yy,
        216,
        92,
        "Cobertura",
        "5 scanners rodaram\n1 pulado, e ele aparece",
        color=P["green"],
        badge="parcial",
    )
    yy += 104
    c.text(ix, yy + 14, "Relatórios", size=11.5, weight=650, fill=t["ink"])
    for i, (fmt, cor) in enumerate(
        [("PDF", P["red"]), ("MD", P["accent"]), ("JSON", P["amber"]), ("CSV", P["green"])]
    ):
        c.pill(ix + i * 78, yy + 26, fmt, cor, size=10, h=26, filled=True)
    c.text(
        ix + 330,
        yy + 44,
        "montados no cliente a partir do AI Fix Bundle",
        size=10,
        fill=t["ink_faint"],
    )
    yy += 66
    c.rect(ix, yy, CW - 200, 96, r=9, fill=t["node_fill"], stroke=t["node_stroke"], sw=1)
    c.text(ix + 14, yy + 22, "Log ao vivo", size=10.5, weight=650, fill=t["ink"])
    for i, ln in enumerate(
        [
            "[zap] spider concluído — 148 URLs",
            "[zap] fila passiva vazia, 512 alertas paginados",
            "[ai] triage 20/32 — 3 marcados falso positivo provável",
        ]
    ):
        c.text(ix + 14, yy + 44 + i * 16, ln, size=9.5, fill=t["ink_soft"], family=MONO)
    c.para(
        GX,
        GY2 + CH + 56,
        "O stepper acompanha as 8 fases pelo SSE, com polling de 4 s como rede de "
        "segurança. Os quatro formatos são montados no navegador a partir do AI Fix "
        "Bundle — o servidor emite o bundle, e o front faz PDF, MD, JSON e CSV.",
        size=11,
        fill=t["ink_soft"],
        max_w=CW,
    )

    # ---------------- 4. IA e escopo
    b, ix, iy = chrome(c, X2, GY2, CW, CH + 40, "POST /pentest/ai · /pentest/scope", "IA")
    c.text(ix, iy, "Provedor de IA", size=15, weight=650, fill=t["ink"])
    yy = iy + 30
    for rot, val in [
        ("Modelo", "anthropic/claude-…  ·  lista vem do provedor, não digitada"),
        ("Fallback", "ollama/llama3  ·  usado quando o principal falha"),
        ("Endpoint local", "http://ollama:11434  ·  para prompt que não pode sair"),
    ]:
        c.text(ix, yy + 16, rot, size=10, fill=t["ink_faint"], family=MONO)
        c.rect(ix + 120, yy, CW - 330, 30, r=7, fill=t["node_fill"], stroke=t["node_stroke"], sw=1)
        c.text(ix + 134, yy + 20, val, size=10.5, fill=t["ink_soft"])
        yy += 42
    c.para(
        ix,
        yy + 6,
        "A chave é gravada cifrada em AES pelo roqueos-server e NUNCA volta "
        "para a tela: o GET devolve mascarado.",
        size=10.5,
        fill=P["amber"],
        max_w=CW - 210,
    )
    yy += 56
    c.line(ix, yy, ix + CW - 210, yy, stroke=t["node_stroke"], sw=1)
    yy += 22
    c.text(ix, yy + 12, "Escopo", size=15, weight=650, fill=t["ink"])
    yy += 34
    for rot, est, cor in [
        ("lab-only", "ligado", P["green"]),
        ("exigir authorization_ref", "ligado", P["green"]),
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
        "As duas telas de governança. O escopo daqui é o mesmo gate que o servidor aplica "
        "no POST /scans: mudar aqui muda o que o portão 1 aceita, e não existe caminho que "
        "escape dele.",
        size=11,
        fill=t["ink_soft"],
        max_w=CW,
    )

    footer(
        c,
        "fonte: roqueos-front/src/components/roqueos/apps/ROSPentest.vue · "
        "src/config/apps.js · src/services/api/pentest.js · "
        "roqueos-server/src/modules/pentest/",
        "github.com/roqueribeiro/roqueos-shield",
        y=GY2 + CH + 160,
    )
    c.h = int(GY2 + CH + 184)
    return c
