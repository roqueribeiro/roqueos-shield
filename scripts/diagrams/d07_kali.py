"""Kali toolbox e o agente CAI dentro dele."""

from .c4lib import *

SAIDA = "kali-cai-agente"


def draw(theme):
    c = Canvas(1900, 1240, theme)
    P = PALETTE
    t = theme
    title_block(
        c,
        "RoqueShield — O Kali e o agente CAI dentro dele",
        "Um sidecar Kali com as ferramentas, e um agente que executa nele sob coleira. "
        "O que está pintado como stub é stub: a coleira e o executor existem e são "
        "testados; o container cai-expert, não.",
    )
    brand(c)

    # ---------------- coluna 1: a imagem
    X1, W1 = 56, 560
    sA = c.slot()
    y = 236
    (im,), y = row(
        c,
        X1 + 22,
        y,
        [W1 - 44],
        [
            dict(
                title="kalilinux/kali-rolling",
                tech="docker/images/kali-toolbox/Dockerfile",
                color=P["kali"],
                desc="A base é a rolling, não a kali-linux-large: o metapacote grande passa de "
                "12 GB e traz centenas de ferramentas que ninguém chama. Aqui entram 19, "
                "escolhidas uma a uma.",
            ),
        ],
        gap=0,
    )
    for titulo, itens, cor in [
        (
            "Descoberta e rede",
            "nmap · masscan · naabu 2.3.3 · amass · subfinder 2.6.6 · whois · dnsutils",
            P["kali"],
        ),
        (
            "Web e aplicação",
            "ffuf · gobuster · dirsearch · sqlmap · nikto · httpx 1.6.9 · nuclei 3.3.5",
            P["amber"],
        ),
        ("Segredo em código", "gitleaks 8.21.2 · trufflehog 3.83.7", P["rose"]),
        ("IaC, imagem e cluster", "checkov · trivy 0.57.1 · kube-bench 0.10.5", P["green"]),
        (
            "Domínio e scanner de rede",
            "dnstwist · gvm-tools + python-gvm (cliente GMP do Greenbone)",
            P["violet"],
        ),
    ]:
        c.text(X1 + 22, y + 20, titulo, size=12, weight=650, fill=cor)
        yy = c.para(X1 + 22, y + 40, itens, size=11, fill=t["ink_soft"], max_w=W1 - 44)
        y = yy + 24
    c.rect(X1 + 22, y, W1 - 44, 74, r=10, fill=t["bg_alt"], stroke=P["green"], sw=1.2)
    c.text(
        X1 + 38,
        y + 24,
        "GATE DE BUILD",
        size=10,
        weight=700,
        fill=P["green"],
        spacing=1.1,
        family=MONO,
    )
    c.para(
        X1 + 38,
        y + 44,
        "ARG NUCLEI_TEMPLATES_MIN=2000 — o build conta os templates e "
        "falha abaixo do piso. Imagem que sobe sem template é um scanner "
        "que não acha nada e não avisa.",
        size=10.5,
        fill=t["ink_soft"],
        max_w=W1 - 76,
    )
    y += 98
    c.into(sA, boundary, X1, 202, W1, y - 202, "a imagem", "19 ferramentas", color=P["kali"])
    y1 = y

    # ---------------- coluna 2: a coleira
    X2, W2 = 648, 600
    sB = c.slot()
    y = 236
    s1 = step(
        c,
        X2 + 22,
        y,
        W2 - 44,
        1,
        "resolve_executor(container=…)",
        "_kali_available() confere o docker e sonda o container. Sem Kali, cai para o "
        "modo local — o orchestrator já embute nmap, nuclei e gitleaks.",
        color=P["kali"],
    )
    y = s1.y + s1.h + 26
    s2 = step(
        c,
        X2 + 22,
        y,
        W2 - 44,
        2,
        "check_command(cmd, phase, scope)",
        "A coleira. Recusa comando fora da fase declarada, alvo fora do escopo e "
        "tentativa de injeção. Devolve ExecDecision, e to_audit() coloca a decisão na "
        "trilha — inclusive as recusas.",
        color=P["red"],
    )
    y = s2.y + s2.h + 26
    s3 = step(
        c,
        X2 + 22,
        y,
        W2 - 44,
        3,
        "run_in_kali(...)",
        'argv = ["docker", "exec", container, *command] entregue a '
        "asyncio.create_subprocess_exec como LISTA. Nunca shell=True, nunca string "
        "concatenada: não existe metacaractere para o agente escapar.",
        color=P["kali"],
    )
    y = s3.y + s3.h + 26
    s4 = step(
        c,
        X2 + 22,
        y,
        W2 - 44,
        4,
        "lab_only_active() e dry_run",
        "Com lab-only ligado, só os alvos de laboratório passam. Em dry_run a decisão "
        "é calculada e registrada, e nada executa.",
        color=P["red"],
    )
    y = s4.y + s4.h + 26
    for a, b in ((s1, s2), (s2, s3), (s3, s4)):
        edge(c, (a.cx, a.y + a.h), (b.cx, b.y - 2))
    c.into(
        sB,
        boundary,
        X2,
        202,
        W2,
        y - 202 - 4,
        "a coleira",
        "ai/agentic/executor.py",
        color=P["red"],
    )
    y2 = y

    # ---------------- coluna 3: o laço e o estado real
    X3, W3 = 1280, 564
    sC = c.slot()
    y = 236
    l1 = step(
        c,
        X3 + 22,
        y,
        W3 - 44,
        "▸",
        "POST /investigate/{finding_id}",
        "Sai do pipeline de scan. Pega UM achado e investiga a fundo, em vez de "
        "triar todos por igual.",
        color=P["cyan"],
    )
    y = l1.y + l1.h + 22
    l2 = step(
        c,
        X3 + 22,
        y,
        W3 - 44,
        "↻",
        "laço de até max_steps",
        "O modelo propõe um comando, parse_command interpreta, check_command decide, "
        "run_in_kali executa, a saída volta ao contexto. Repete até concluir ou "
        "estourar o teto.",
        color=P["cyan"],
    )
    y = l2.y + l2.h + 22
    l3 = step(
        c,
        X3 + 22,
        y,
        W3 - 44,
        "↓",
        "_investigate_fallback()",
        "Sem agente disponível, um prompt só, sem execução. Continua respondendo — "
        "e diz que foi por aqui.",
        color=P["gray"],
    )
    y = l3.y + l3.h + 22
    edge(c, (l1.cx, l1.y + l1.h), (l2.cx, l2.y - 2))
    edge(c, (l2.cx, l2.y + l2.h), (l3.cx, l3.y - 2), "sem agente", dash="5 4", color=P["gray"])
    c.into(
        sC,
        boundary,
        X3,
        202,
        W3,
        y - 202 - 4,
        "a investigação",
        "ai/agentic/cai_expert.py",
        color=P["cyan"],
    )
    y3 = y

    # ---------------- o que ainda não é
    yb = max(y1, y2, y3) + 24
    c.rect(X1, yb, 1788, 172, r=12, fill=t["bg_alt"], stroke=P["red"], sw=1.4, dash="7 6")
    c.text(
        X1 + 24,
        yb + 32,
        "O QUE AINDA NÃO É — dito aqui para não ser descoberto em produção",
        size=11.5,
        weight=700,
        fill=P["red"],
        spacing=0.8,
        family=MONO,
    )
    yy = table(
        c,
        X1 + 24,
        yb + 48,
        1740,
        ["peça", "estado medido no código", "consequência prática"],
        [
            [
                "container cai-expert",
                "docker/images/cai-expert/Dockerfile instala cai-framework com "
                "|| true no final; o compose.agent.yml se declara stub no cabeçalho e o "
                "CMD é um print de idle",
                "A imagem sobe mesmo se a instalação falhar. Não conte com ela para operar.",
            ],
            [
                "_cai_framework_available()",
                "hoje devolve apenas bool(settings.AGENT_ENABLED) — não verifica se o "
                "framework está de fato instalado",
                "Com a flag ligada e o framework ausente, o caminho agêntico é tentado e "
                "cai no fallback.",
            ],
        ],
        [230, 700, 810],
        color=P["red"],
        rowh=None,
    )

    footer(
        c,
        "fonte: docker/images/kali-toolbox/Dockerfile · orchestrator/ai/agentic/executor.py · "
        "orchestrator/ai/agentic/cai_expert.py · docker/compose.agent.yml",
        "github.com/roqueribeiro/roqueos-shield",
        y=yy + 66,
    )
    c.h = int(yy + 90)
    return c
