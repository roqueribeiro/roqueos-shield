"""Kali toolbox e o agente CAI dentro dele."""

from .c4lib import *

SAIDA = "agente-kali"


def draw(theme):
    c = Canvas(1900, 1240, theme)
    P = PALETTE
    t = theme
    title_block(
        c,
        tr(
            "RoqueShield: o Kali e o agente CAI dentro dele",
            "RoqueShield: Kali and the CAI agent inside it",
        ),
        tr(
            "Um sidecar Kali com as ferramentas, e um agente que executa nele sob coleira. "
            "O que está pintado como stub é stub: a coleira e o executor existem e são "
            "testados; o container cai-expert, não.",
            "A Kali sidecar with the tools, and an agent that runs commands in it on a leash. "
            "What is drawn as a stub is a stub: the leash and the executor exist and are "
            "tested; the cai-expert container is not.",
        ),
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
                desc=tr(
                    "A base é a rolling, não a kali-linux-large: o metapacote grande passa de "
                    "12 GB e traz centenas de ferramentas que ninguém chama. Aqui entram 19, "
                    "escolhidas uma a uma.",
                    "The base is rolling, not kali-linux-large: the large metapackage is over "
                    "12 GB and brings hundreds of tools nobody calls. Here 19 go in, picked "
                    "one by one.",
                ),
            ),
        ],
        gap=0,
    )
    for titulo, itens, cor in [
        (
            tr("Descoberta e rede", "Discovery and network"),
            "nmap · masscan · naabu 2.3.3 · amass · subfinder 2.6.6 · whois · dnsutils",
            P["kali"],
        ),
        (
            tr("Web e aplicação", "Web and application"),
            "ffuf · gobuster · dirsearch · sqlmap · nikto · httpx 1.6.9 · nuclei 3.3.5",
            P["amber"],
        ),
        (
            tr("Segredo em código", "Secrets in code"),
            "gitleaks 8.21.2 · trufflehog 3.83.7",
            P["rose"],
        ),
        (
            tr("IaC, imagem e cluster", "IaC, image and cluster"),
            "checkov · trivy 0.57.1 · kube-bench 0.10.5",
            P["green"],
        ),
        (
            tr("Domínio e scanner de rede", "Domain and network scanner"),
            tr(
                "dnstwist · gvm-tools + python-gvm (cliente GMP do Greenbone)",
                "dnstwist · gvm-tools + python-gvm (Greenbone GMP client)",
            ),
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
        tr("GATE DE BUILD", "BUILD GATE"),
        size=10,
        weight=700,
        fill=P["green"],
        spacing=1.1,
        family=MONO,
    )
    c.para(
        X1 + 38,
        y + 44,
        tr(
            "ARG NUCLEI_TEMPLATES_MIN=2000: o build conta os templates e "
            "falha abaixo do piso. Imagem que sobe sem template é um scanner "
            "que não acha nada e não avisa.",
            "ARG NUCLEI_TEMPLATES_MIN=2000: the build counts the templates and "
            "fails below the floor. An image that ships without templates is a "
            "scanner that finds nothing and says nothing.",
        ),
        size=10.5,
        fill=t["ink_soft"],
        max_w=W1 - 76,
    )
    y += 98
    c.into(
        sA,
        boundary,
        X1,
        202,
        W1,
        y - 202,
        tr("a imagem", "the image"),
        tr("19 ferramentas", "19 tools"),
        color=P["kali"],
    )
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
        tr(
            "_kali_available() confere o docker e sonda o container. Sem Kali, cai para o "
            "modo local: o orchestrator já embute nmap, nuclei e gitleaks.",
            "_kali_available() checks docker and probes the container. Without Kali it "
            "falls back to local mode: the orchestrator already bundles nmap, nuclei and "
            "gitleaks.",
        ),
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
        tr(
            "A coleira. Recusa comando fora da fase declarada, alvo fora do escopo e "
            "tentativa de injeção. Devolve ExecDecision, e to_audit() coloca a decisão na "
            "trilha, inclusive as recusas.",
            "The leash. Rejects commands outside the declared phase, targets out of scope "
            "and injection attempts. Returns ExecDecision, and to_audit() puts the decision "
            "in the trail, rejections included.",
        ),
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
        tr(
            'argv = ["docker", "exec", container, *command] entregue a '
            "asyncio.create_subprocess_exec como LISTA. Nunca shell=True, nunca string "
            "concatenada: não existe metacaractere para o agente escapar.",
            'argv = ["docker", "exec", container, *command] handed to '
            "asyncio.create_subprocess_exec as a LIST. Never shell=True, never a "
            "concatenated string: there is no metacharacter for the agent to escape.",
        ),
        color=P["kali"],
    )
    y = s3.y + s3.h + 26
    s4 = step(
        c,
        X2 + 22,
        y,
        W2 - 44,
        4,
        tr("lab_only_active() e dry_run", "lab_only_active() and dry_run"),
        tr(
            "Com lab-only ligado, endereço interno só passa se estiver na allow-list. "
            "Em dry_run a decisão "
            "é calculada e registrada, e nada executa.",
            "With lab-only on, an internal address passes only if allow-listed. "
            "In dry_run the decision is computed "
            "and recorded, and nothing runs.",
        ),
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
        tr("a coleira", "the leash"),
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
        tr(
            "Sai do pipeline de scan. Pega UM achado e investiga a fundo, em vez de "
            "triar todos por igual.",
            "Steps out of the scan pipeline. Takes ONE finding and digs into it, instead "
            "of triaging all of them the same way.",
        ),
        color=P["cyan"],
    )
    y = l1.y + l1.h + 22
    l2 = step(
        c,
        X3 + 22,
        y,
        W3 - 44,
        "↻",
        tr("laço de até max_steps", "loop of up to max_steps"),
        tr(
            "O modelo propõe um comando, parse_command interpreta, check_command decide, "
            "run_in_kali executa, a saída volta ao contexto. Repete até concluir ou "
            "estourar o teto.",
            "The model proposes a command, parse_command parses it, check_command decides, "
            "run_in_kali runs it, the output goes back into context. Repeats until done or "
            "the cap is hit.",
        ),
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
        tr(
            "Sem agente disponível, um prompt só, sem execução. Continua respondendo, "
            "e diz que foi por aqui.",
            "With no agent available, a single prompt, no execution. It still answers, "
            "and says it took this path.",
        ),
        color=P["gray"],
    )
    y = l3.y + l3.h + 22
    edge(c, (l1.cx, l1.y + l1.h), (l2.cx, l2.y - 2))
    edge(
        c,
        (l2.cx, l2.y + l2.h),
        (l3.cx, l3.y - 2),
        tr("sem agente", "no agent"),
        dash="5 4",
        color=P["gray"],
    )
    c.into(
        sC,
        boundary,
        X3,
        202,
        W3,
        y - 202 - 4,
        tr("a investigação", "the investigation"),
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
        tr(
            "O QUE AINDA NÃO É: dito aqui para não ser descoberto em produção",
            "WHAT IT IS NOT YET: said here so nobody finds out in production",
        ),
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
        [
            tr("peça", "piece"),
            tr("estado medido no código", "state measured in the code"),
            tr("consequência prática", "practical consequence"),
        ],
        [
            [
                tr("container cai-expert", "cai-expert container"),
                tr(
                    "docker/images/cai-expert/Dockerfile instala cai-framework com "
                    "|| true no final; o compose.agent.yml se declara stub no cabeçalho e o "
                    "CMD é um print de idle",
                    "docker/images/cai-expert/Dockerfile installs cai-framework with "
                    "|| true at the end; compose.agent.yml declares itself a stub in its "
                    "header and the CMD just prints idle",
                ),
                tr(
                    "A imagem sobe mesmo se a instalação falhar. Não conte com ela para operar.",
                    "The image builds even if the install fails. Do not rely on it in operation.",
                ),
            ],
            [
                "_cai_framework_available()",
                tr(
                    "hoje devolve apenas bool(settings.AGENT_ENABLED). Não verifica se o "
                    "framework está de fato instalado",
                    "today it only returns bool(settings.AGENT_ENABLED). It does not check "
                    "whether the framework is actually installed",
                ),
                tr(
                    "Com a flag ligada e o framework ausente, o caminho agêntico é tentado e "
                    "cai no fallback.",
                    "With the flag on and the framework missing, the agentic path is tried "
                    "and falls back.",
                ),
            ],
        ],
        [230, 700, 810],
        color=P["red"],
        rowh=None,
    )

    footer(
        c,
        tr("fonte: ", "source: ")
        + "docker/images/kali-toolbox/Dockerfile · orchestrator/ai/agentic/executor.py · "
        "orchestrator/ai/agentic/cai_expert.py · docker/compose.agent.yml",
        "github.com/roqueribeiro/roqueos-shield",
        y=yy + 66,
    )
    c.h = int(yy + 90)
    return c
