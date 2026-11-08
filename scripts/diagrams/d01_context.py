"""C1: System Context. Um sistema = uma caixa. Decomposicao fica no C2."""

from .c4lib import *

SAIDA = "contexto"


def draw(theme):
    c = Canvas(1600, 940, theme)
    P = PALETTE
    title_block(
        c,
        tr("RoqueShield: contexto do sistema", "RoqueShield: system context"),
        tr(
            "Quem usa, o que a plataforma varre, e de quem ela depende. No nível 1 o "
            "RoqueShield é uma caixa só: a decomposição interna está no C2.",
            "Who uses it, what the platform scans, and what it depends on. At level 1 "
            "RoqueShield is a single box: the internal breakdown is in C2.",
        ),
        level=tr("C1  ·  CONTEXTO", "C1  ·  CONTEXT"),
    )
    brand(c)

    op = node(
        c,
        56,
        196,
        288,
        146,
        tr("Operador de segurança", "Security operator"),
        tr("pessoa · papel admin", "person · admin role"),
        tr(
            "Registra o alvo, declara a autorização do teste, dispara o scan e "
            "revisa os achados antes de assinar o relatório.",
            "Registers the target, declares the test authorization, starts the scan "
            "and reviews the findings before signing the report.",
        ),
        color=P["violet"],
        kind="person",
    )
    dev = node(
        c,
        56,
        368,
        288,
        146,
        tr("Time de desenvolvimento", "Development team"),
        tr("pessoa", "person"),
        tr(
            "Recebe achado já triado, com impacto de negócio e remediação "
            "sugerida. Não precisa abrir a ferramenta.",
            "Gets findings already triaged, with business impact and a suggested "
            "fix. No need to open the tool.",
        ),
        color=P["violet"],
        kind="person",
    )
    ag = node(
        c,
        56,
        540,
        288,
        160,
        tr("Agente de IA", "AI agent"),
        "Claude Code · Cursor · CI",
        tr(
            "Lê o AI Fix Bundle pela CLI ou pela API REST, aplica o patch e "
            "dispara um novo scan. É o laço que fecha sem humano no meio.",
            "Reads the AI Fix Bundle through the CLI or the REST API, applies the "
            "patch and starts a new scan. The loop closes with no human in between.",
        ),
        color=P["cyan"],
    )

    sys_ = node(
        c,
        524,
        206,
        464,
        336,
        "RoqueShield",
        "Python 3.13 · FastAPI · arq · Postgres",
        tr(
            "Plataforma de teste de segurança contínuo. Orquestra 15 scanners "
            "sobre 7 tipos de ativo, deduplica os achados, tria cada um com LLM "
            "e emite quatro saídas: relatório técnico, relatório executivo, "
            "compliance com nota A–F e o AI Fix Bundle que um agente consome.\n\n"
            "A regra que governa o projeto: zero achado só pode significar alvo "
            "limpo. Scanner que não rodou aparece em scanners_skipped, e cobertura "
            "parcial vira achado INFO no relatório. Nunca silêncio.",
            "Continuous security testing platform. Runs 15 scanners across 7 asset "
            "types, deduplicates the findings, triages each one with an LLM and "
            "produces four outputs: technical report, executive report, compliance "
            "with an A–F grade, and the AI Fix Bundle an agent consumes.\n\n"
            "The rule that governs the project: zero findings can only mean a clean "
            "target. A scanner that did not run shows up in scanners_skipped, and "
            "partial coverage becomes an INFO finding in the report. Never silence.",
        ),
        color=P["rose"],
    )
    px = 556
    px += c.pill(px, 496, "Apache 2.0 · open source", P["rose"], filled=True) + 8
    px += c.pill(px, 496, "admin-only", P["amber"], filled=True) + 8
    c.pill(px, 496, "self-hosted", P["green"], filled=True)

    tgt = node(
        c,
        524,
        620,
        464,
        148,
        tr("Alvos autorizados", "Authorized targets"),
        tr("7 tipos de ativo", "7 asset types"),
        "host  ·  url  ·  domain  ·  port  ·  image  ·  repo  ·  k8s_resource\n\n"
        + tr(
            "O gate de escopo recusa alvo fora da allow-list antes de qualquer "
            "pacote sair, e o modo lab-only vem ligado por padrão.",
            "The scope gate rejects any target outside the allow-list before a "
            "single packet leaves, and lab-only mode is on by default.",
        ),
        color=P["red"],
    )

    ros = node(
        c,
        1176,
        196,
        368,
        178,
        "RoqueOS",
        "Vue 3 + Quasar · NestJS",
        tr(
            "Embarca o RoqueShield como app admin-only do sistema operacional. "
            "Provisiona a stack por Docker e faz proxy reverso injetando o token "
            "server-side: o browser nunca vê a credencial.",
            "Ships RoqueShield as an admin-only app of the operating system. "
            "Provisions the stack through Docker and reverse-proxies it, injecting "
            "the token server-side: the browser never sees the credential.",
        ),
        color=P["accent"],
    )
    llm = node(
        c,
        1176,
        400,
        368,
        160,
        tr("Provedor de LLM", "LLM provider"),
        "litellm",
        tr(
            "Anthropic, OpenAI, OpenRouter ou modelo local (Ollama, LM Studio). "
            "Todo prompt passa pelo scrubber antes de sair da máquina.",
            "Anthropic, OpenAI, OpenRouter or a local model (Ollama, LM Studio). "
            "Every prompt goes through the scrubber before it leaves the machine.",
        ),
        color=P["amber"],
    )
    dd = node(
        c,
        1176,
        586,
        368,
        130,
        "DefectDojo",
        tr("REST · opcional", "REST · optional"),
        tr(
            "Destino de export dos achados para quem já tem gestão de vulnerabilidade centralizada.",
            "Export target for teams that already run centralized vulnerability management.",
        ),
        color=P["gray"],
    )

    edge(
        c,
        op.right,
        sys_.pt("left", 0.16),
        tr("autoriza e dispara", "authorizes and starts"),
        "authorization_ref",
        color=P["violet"],
        mid=[(434, 269), (434, 266)],
    )
    edge(
        c,
        sys_.pt("left", 0.52),
        dev.right,
        tr("entrega achado triado", "delivers triaged findings"),
        tr("relatório + bundle", "report + bundle"),
        color=P["violet"],
        mid=[(434, 400), (434, 441)],
    )
    edge(
        c,
        ag.right,
        sys_.pt("left", 0.875),
        tr("consulta e re-dispara", "queries and re-runs"),
        "CLI · REST",
        color=P["cyan"],
        mid=[(434, 620), (434, 500)],
    )
    edge(
        c,
        ros.left,
        sys_.pt("right", 0.18),
        tr("provisiona e faz proxy", "provisions and proxies"),
        "HTTP + SSE",
        color=P["accent"],
        mid=[(1082, 285), (1082, 273)],
    )
    edge(
        c,
        sys_.pt("right", 0.55),
        llm.left,
        tr("tria e enriquece", "triages and enriches"),
        tr("prompt sanitizado", "scrubbed prompt"),
        color=P["amber"],
        mid=[(1082, 391), (1082, 480)],
    )
    edge(
        c,
        sys_.pt("right", 0.895),
        dd.left,
        tr("exporta achados", "exports findings"),
        tr("opcional", "optional"),
        color=P["gray"],
        mid=[(1082, 507), (1082, 651)],
    )
    edge(
        c,
        sys_.bottom,
        tgt.top,
        tr("varre sob autorização", "scans under authorization"),
        "nmap · zap · nuclei · trivy · semgrep …",
        color=P["red"],
    )

    legend(
        c,
        56,
        730,
        [
            (P["rose"], tr("RoqueShield · este repositório", "RoqueShield · this repository")),
            (P["accent"], tr("Sistema da família RoqueOS", "RoqueOS family system")),
            (P["violet"], tr("Pessoa", "Person")),
            (P["cyan"], tr("Agente automatizado", "Automated agent")),
            (P["amber"], tr("Serviço externo", "External service")),
            (P["red"], tr("Alvo do teste", "Test target")),
            (P["gray"], tr("Integração opcional", "Optional integration")),
            (P["green"], tr("Postura / conformidade", "Posture / compliance")),
        ],
        cols=2,
        box_w=468,
    )

    footer(
        c,
        tr(
            "C4 model · nível 1 de 4 · regenerável por scripts/gen_diagrams.py",
            "C4 model · level 1 of 4 · regenerated by scripts/gen_diagrams.py",
        ),
        "github.com/roqueribeiro/roqueos-shield",
    )
    return c
