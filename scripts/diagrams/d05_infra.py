"""Infraestrutura e implantacao."""

from .c4lib import *

SAIDA = "infra-deploy"


def draw(theme):
    c = Canvas(1880, 1180, theme)
    P = PALETTE
    t = theme
    title_block(
        c,
        "RoqueShield — Infraestrutura e implantação",
        "Dois caminhos de subida, a mesma imagem. À esquerda o modo que o RoqueOS "
        "provisiona sozinho; à direita o compose para quem roda a plataforma fora do "
        "RoqueOS. Portas e volumes são os medidos no compose, não os do manual.",
    )
    brand(c)

    # ---------------- modo RoqueOS
    LX, LW = 56, 900
    c.pill(LX, 176, "MODO 1 · dentro do RoqueOS", P["accent"], filled=True)
    c.para(
        LX,
        224,
        "O app RoqueShield chama POST /pentest/provision. O roqueos-server gera o YAML "
        "(pentest-compose.util.ts), sobe a stack pelo ComposeStacksService e conecta o "
        "orchestrator à rede do próprio servidor. Nenhuma porta do RoqueShield é "
        "publicada no host: quem entra, entra pelo proxy.",
        size=11.5,
        fill=t["ink_soft"],
        max_w=LW,
    )

    sH = c.slot()
    y = 320
    prox = node(
        c,
        LX + 24,
        y,
        400,
        None,
        "roqueos-server",
        "container existente",
        "Proxy ALL /pentest/api/* → orchestrator:8080, injetando X-API-Token. "
        "SSE com X-Accel-Buffering: no e timeout 0; REST com teto de 60 s.",
        color=P["accent"],
    )
    orc = node(
        c,
        LX + 452,
        y,
        400,
        None,
        "roqueos-pentest-orchestrator",
        ":8080 interno",
        "entrypoint: until alembic upgrade head; ... done && exec uvicorn. "
        "O retry existe porque create_all sozinho perde o trigger de auditoria.",
        color=P["rose"],
    )
    y = max(prox.y + prox.h, orc.y + orc.h) + 26
    (w2, pg2, rd2), y = row(
        c,
        LX + 24,
        y,
        [270, 270, 270],
        [
            dict(
                title="…-worker",
                tech="entrypoint arq",
                color=P["rose"],
                desc="orchestrator.jobs.queue.WorkerSettings",
            ),
            dict(
                title="…-postgres",
                tech="user/db cai",
                color=P["green"],
                desc="volume de dados da stack",
            ),
            dict(title="…-redis", tech="fila", color=P["green"], desc="sem volume"),
        ],
        gap=25,
    )
    (z2, t2, k2), y = row(
        c,
        LX + 24,
        y,
        [270, 270, 270],
        [
            dict(
                title="…-zap", tech="daemon :8090", color=P["amber"], desc="interno à rede da stack"
            ),
            dict(
                title="…-trivy",
                tech="server :4954",
                color=P["amber"],
                desc="interno à rede da stack",
            ),
            dict(title="…-kali-toolbox", tech="toggle", color=P["kali"], desc="opt-in pelo painel"),
        ],
        gap=25,
    )
    c.into(
        sH,
        boundary,
        LX,
        296,
        LW,
        y - 296 - 6,
        "host do RoqueOS Server",
        "rede roqueos-network",
        color=P["accent"],
    )
    yl = y

    # ---------------- modo compose
    RX, RW = 996, 828
    c.pill(RX, 176, "MODO 2 · compose autônomo", P["rose"], filled=True)
    c.para(
        RX,
        224,
        "make up sobe o núcleo; os demais arquivos são profiles opt-in. Aqui a porta "
        "8080 é publicada no host e o dashboard em /ui fica acessível direto. "
        "É o modo de desenvolvimento e o de quem não usa o RoqueOS.",
        size=11.5,
        fill=t["ink_soft"],
        max_w=RW,
    )

    sK = c.slot()
    y = 320
    (f1, f2), y = row(
        c,
        RX + 24,
        y,
        [378, 378],
        [
            dict(
                title="docker/compose.yml",
                tech="núcleo",
                color=P["rose"],
                desc="orchestrator (8080 publicada) · worker · postgres · redis · ollama. "
                "Volumes pgdata e ollama_models.",
            ),
            dict(
                title="compose.scanners.yml",
                tech="profile",
                color=P["amber"],
                desc="zap · trivy · kali-toolbox (build local). Volumes trivy_cache e "
                "kali_workspace.",
            ),
        ],
        gap=24,
    )
    (f3, f4), y = row(
        c,
        RX + 24,
        y,
        [378, 378],
        [
            dict(
                title="compose.greenbone.yml",
                tech="profile",
                color=P["gray"],
                desc="7 serviços e 5 volumes (gvm_data, gvm_pg, gvm_redis, openvas_data, "
                "openvas_log). O feed leva de 30 min a 3 h.",
            ),
            dict(
                title="compose.lab.yml",
                tech="profile",
                color=P["red"],
                desc="juice-shop · dvwa · webgoat. Os alvos de laboratório que a allow-list "
                "já traz liberados.",
            ),
        ],
        gap=24,
    )
    (f5, f6), y = row(
        c,
        RX + 24,
        y,
        [378, 378],
        [
            dict(
                title="compose.observability.yml",
                tech="profile",
                color=P["cyan"],
                desc="phoenix (Arize) para rastrear as chamadas de LLM. Volume phoenix_data.",
            ),
            dict(
                title="compose.proxy.yml · agent.yml",
                tech="profile",
                color=P["gray"],
                desc="caddy com Caddyfile próprio; cai-expert declarado stub no cabeçalho do "
                "arquivo.",
            ),
        ],
        gap=24,
    )
    c.into(
        sK,
        boundary,
        RX,
        296,
        RW,
        y - 296 - 6,
        "qualquer host com Docker",
        "rede cai-net · name: cai",
        color=P["rose"],
    )

    # ---------------- portas e volumes
    yb = max(yl, y) + 22
    ytab = table(
        c,
        LX,
        yb,
        900,
        ["porta", "quem escuta", "exposta ao host?"],
        [
            ["8080", "orchestrator (FastAPI)", "compose: sim · RoqueOS: NÃO, só pela rede interna"],
            ["8090", "zap daemon", "não"],
            ["4954", "trivy server", "não"],
            ["11434", "ollama", "compose: sim, se o profile subir"],
            ["9392 · 9390", "greenbone GSA e GMP", "compose: sim, se o profile subir"],
        ],
        [140, 320, 440],
        color=P["accent"],
        title="Portas, e quem realmente as vê",
    )

    ytab2 = table(
        c,
        RX,
        yb,
        828,
        ["o que garante", "onde está"],
        [
            [
                "Trilha imutável",
                "TRIGGER audit_log_no_update no Postgres. Em SQLite não "
                "existe, e o main.py loga audit.mutable_trail avisando.",
            ],
            [
                "Segredo em repouso",
                "Chaves de IA e APP_TOKEN cifrados em AES pelo "
                "roqueos-server (ENCRYPTION_KEY). O container não guarda "
                "chave em claro no disco.",
            ],
            [
                "Imagem multi-arch",
                "A stack não subia em Apple Silicon; o Dockerfile "
                "resolve amd64 e arm64 e valida --version de cada "
                "binário no build.",
            ],
            [
                "Regra de scanner",
                "Semgrep com commit pinado e semgrep --validate como "
                "gate de build; nuclei com piso de 2000 templates.",
            ],
        ],
        [190, 638],
        color=P["green"],
        title="O que a implantação garante",
    )

    footer(
        c,
        "fonte: docker/compose*.yml · docker/images/*/Dockerfile · "
        "roqueos-server/src/modules/pentest/pentest-compose.util.ts",
        "github.com/roqueribeiro/roqueos-shield",
        y=max(ytab, ytab2) + 72,
    )
    c.h = int(max(ytab, ytab2) + 96)
    return c
