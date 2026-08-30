"""C1 — System Context. Um sistema = uma caixa. Decomposicao fica no C2."""

from .c4lib import *

SAIDA = "c1-context"


def draw(theme):
    c = Canvas(1600, 940, theme)
    P = PALETTE
    title_block(
        c,
        "RoqueShield — Contexto do sistema",
        "Quem usa, o que a plataforma varre, e de quem ela depende. No nível 1 o "
        "RoqueShield é uma caixa só: a decomposição interna está no C2.",
        level="C1  ·  CONTEXTO",
    )
    brand(c)

    op = node(
        c,
        56,
        196,
        288,
        146,
        "Operador de segurança",
        "pessoa · papel admin",
        "Registra o alvo, declara a autorização do teste, dispara o scan e "
        "revisa os achados antes de assinar o relatório.",
        color=P["violet"],
        kind="person",
    )
    dev = node(
        c,
        56,
        368,
        288,
        146,
        "Time de desenvolvimento",
        "pessoa",
        "Recebe achado já triado, com impacto de negócio e remediação "
        "sugerida. Não precisa abrir a ferramenta.",
        color=P["violet"],
        kind="person",
    )
    ag = node(
        c,
        56,
        540,
        288,
        160,
        "Agente de IA",
        "Claude Code · Cursor · CI",
        "Lê o AI Fix Bundle pela CLI ou pela API REST, aplica o patch e "
        "dispara um novo scan. É o laço que fecha sem humano no meio.",
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
        "Plataforma de teste de segurança contínuo. Orquestra 15 scanners "
        "sobre 7 tipos de ativo, deduplica os achados, tria cada um com LLM "
        "e emite quatro saídas: relatório técnico, relatório executivo, "
        "compliance com nota A–F e o AI Fix Bundle que um agente consome.\n\n"
        "A regra que governa o projeto: zero achado só pode significar alvo "
        "limpo. Scanner que não rodou aparece em scanners_skipped, e cobertura "
        "parcial vira achado INFO no relatório — nunca silêncio.",
        color=P["rose"],
    )
    c.pill(556, 496, "Apache 2.0 · open source", P["rose"], filled=True)
    c.pill(556 + 156, 496, "admin-only", P["amber"], filled=True)
    c.pill(556 + 156 + 122, 496, "self-hosted", P["green"], filled=True)

    tgt = node(
        c,
        524,
        620,
        464,
        148,
        "Alvos autorizados",
        "7 tipos de ativo",
        "host  ·  url  ·  domain  ·  port  ·  image  ·  repo  ·  k8s_resource\n\n"
        "O gate de escopo recusa alvo fora da allow-list antes de qualquer "
        "pacote sair, e o modo lab-only vem ligado por padrão.",
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
        "Embarca o RoqueShield como app admin-only do sistema operacional. "
        "Provisiona a stack por Docker e faz proxy reverso injetando o token "
        "server-side: o browser nunca vê a credencial.",
        color=P["accent"],
    )
    llm = node(
        c,
        1176,
        400,
        368,
        160,
        "Provedor de LLM",
        "litellm",
        "Anthropic, OpenAI, OpenRouter ou modelo local (Ollama, LM Studio). "
        "Todo prompt passa pelo scrubber antes de sair da máquina.",
        color=P["amber"],
    )
    dd = node(
        c,
        1176,
        586,
        368,
        130,
        "DefectDojo",
        "REST · opcional",
        "Destino de export dos achados para quem já tem gestão de vulnerabilidade centralizada.",
        color=P["gray"],
    )

    edge(
        c,
        op.right,
        sys_.pt("left", 0.16),
        "autoriza e dispara",
        "authorization_ref",
        color=P["violet"],
        mid=[(434, 269), (434, 266)],
    )
    edge(
        c,
        sys_.pt("left", 0.52),
        dev.right,
        "entrega achado triado",
        "relatório + bundle",
        color=P["violet"],
        mid=[(434, 400), (434, 441)],
    )
    edge(
        c,
        ag.right,
        sys_.pt("left", 0.875),
        "consulta e re-dispara",
        "CLI · REST",
        color=P["cyan"],
        mid=[(434, 620), (434, 500)],
    )
    edge(
        c,
        ros.left,
        sys_.pt("right", 0.18),
        "provisiona e faz proxy",
        "HTTP + SSE",
        color=P["accent"],
        mid=[(1082, 285), (1082, 273)],
    )
    edge(
        c,
        sys_.pt("right", 0.55),
        llm.left,
        "tria e enriquece",
        "prompt sanitizado",
        color=P["amber"],
        mid=[(1082, 391), (1082, 480)],
    )
    edge(
        c,
        sys_.pt("right", 0.895),
        dd.left,
        "exporta achados",
        "opcional",
        color=P["gray"],
        mid=[(1082, 507), (1082, 651)],
    )
    edge(
        c,
        sys_.bottom,
        tgt.top,
        "varre sob autorização",
        "nmap · zap · nuclei · trivy · semgrep …",
        color=P["red"],
    )

    legend(
        c,
        56,
        730,
        [
            (P["rose"], "RoqueShield · este repositório"),
            (P["accent"], "Sistema da família RoqueOS"),
            (P["violet"], "Pessoa"),
            (P["cyan"], "Agente automatizado"),
            (P["amber"], "Serviço externo"),
            (P["red"], "Alvo do teste"),
            (P["gray"], "Integração opcional"),
            (P["green"], "Postura / conformidade"),
        ],
        cols=2,
        box_w=468,
    )

    footer(
        c,
        "C4 model · nível 1 de 4 · regenerável por scripts/gen_diagrams.py",
        "github.com/roqueribeiro/roqueos-shield",
    )
    return c
