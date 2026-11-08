"""Infraestrutura e implantacao."""

from .c4lib import *

SAIDA = "infra"


def draw(theme):
    c = Canvas(1880, 1180, theme)
    P = PALETTE
    t = theme
    title_block(
        c,
        tr(
            "RoqueShield: infraestrutura e implantação",
            "RoqueShield: infrastructure and deployment",
        ),
        tr(
            "Dois caminhos de subida, a mesma imagem. À esquerda o modo que o RoqueOS "
            "provisiona sozinho; à direita o compose para quem roda a plataforma fora do "
            "RoqueOS. Portas e volumes são os medidos no compose, não os do manual.",
            "Two ways to bring it up, one image. On the left, the mode RoqueOS provisions "
            "by itself; on the right, compose for running the platform outside RoqueOS. "
            "Ports and volumes are the ones measured in compose, not the ones in the manual.",
        ),
    )
    brand(c)

    # ---------------- modo RoqueOS
    LX, LW = 56, 900
    c.pill(
        LX,
        176,
        tr("MODO 1 · dentro do RoqueOS", "MODE 1 · inside RoqueOS"),
        P["accent"],
        filled=True,
    )
    c.para(
        LX,
        224,
        tr(
            "O app RoqueShield chama POST /pentest/provision. O roqueos-server gera o YAML "
            "(pentest-compose.util.ts), sobe a stack pelo ComposeStacksService e conecta o "
            "orchestrator à rede do próprio servidor. Nenhuma porta do RoqueShield é "
            "publicada no host: quem entra, entra pelo proxy.",
            "The RoqueShield app calls POST /pentest/provision. roqueos-server generates the "
            "YAML (pentest-compose.util.ts), brings the stack up through ComposeStacksService "
            "and attaches the orchestrator to the server's own network. No RoqueShield port "
            "is published on the host: the only way in is through the proxy.",
        ),
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
        tr("container existente", "existing container"),
        tr(
            "Proxy ALL /pentest/api/* → orchestrator:8080, injetando X-API-Token. "
            "SSE com X-Accel-Buffering: no e timeout 0; REST com teto de 60 s.",
            "Proxies ALL /pentest/api/* → orchestrator:8080, injecting X-API-Token. "
            "SSE with X-Accel-Buffering: no and timeout 0; REST capped at 60 s.",
        ),
        color=P["accent"],
    )
    orc = node(
        c,
        LX + 452,
        y,
        400,
        None,
        "roqueos-pentest-orchestrator",
        tr(":8080 interno", ":8080 internal"),
        "entrypoint: until alembic upgrade head; ... done && exec uvicorn. "
        + tr(
            "O retry existe porque create_all sozinho perde o trigger de auditoria.",
            "The retry exists because create_all alone loses the audit trigger.",
        ),
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
                desc=tr("volume de dados da stack", "stack data volume"),
            ),
            dict(
                title="…-redis",
                tech=tr("fila", "queue"),
                color=P["green"],
                desc=tr("sem volume", "no volume"),
            ),
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
                title="…-zap",
                tech="daemon :8090",
                color=P["amber"],
                desc=tr("interno à rede da stack", "internal to the stack network"),
            ),
            dict(
                title="…-trivy",
                tech="server :4954",
                color=P["amber"],
                desc=tr("interno à rede da stack", "internal to the stack network"),
            ),
            dict(
                title="…-kali-toolbox",
                tech="toggle",
                color=P["kali"],
                desc=tr("opt-in pelo painel", "opt-in from the panel"),
            ),
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
        tr("host do RoqueOS Server", "RoqueOS Server host"),
        tr("rede roqueos-network", "network roqueos-network"),
        color=P["accent"],
    )
    yl = y

    # ---------------- modo compose
    RX, RW = 996, 828
    c.pill(
        RX,
        176,
        tr("MODO 2 · compose autônomo", "MODE 2 · standalone compose"),
        P["rose"],
        filled=True,
    )
    c.para(
        RX,
        224,
        tr(
            "make up sobe o núcleo; os demais arquivos são profiles opt-in. Aqui a porta "
            "8080 é publicada no host e o dashboard em /ui fica acessível direto. "
            "É o modo de desenvolvimento e o de quem não usa o RoqueOS.",
            "make up starts the core; the other files are opt-in profiles. Here port 8080 "
            "is published on the host and the dashboard at /ui is reachable directly. "
            "It is the development mode and the mode for anyone not using RoqueOS.",
        ),
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
                tech=tr("núcleo", "core"),
                color=P["rose"],
                desc=tr(
                    "orchestrator (8080 publicada) · worker · postgres · redis · ollama. "
                    "Volumes pgdata e ollama_models.",
                    "orchestrator (8080 published) · worker · postgres · redis · ollama. "
                    "Volumes pgdata and ollama_models.",
                ),
            ),
            dict(
                title="compose.scanners.yml",
                tech="profile",
                color=P["amber"],
                desc=tr(
                    "zap · trivy · kali-toolbox (build local). Volumes trivy_cache e "
                    "kali_workspace.",
                    "zap · trivy · kali-toolbox (local build). Volumes trivy_cache and "
                    "kali_workspace.",
                ),
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
                desc=tr(
                    "7 serviços e 5 volumes (gvm_data, gvm_pg, gvm_redis, openvas_data, "
                    "openvas_log). O feed leva de 30 min a 3 h.",
                    "7 services and 5 volumes (gvm_data, gvm_pg, gvm_redis, openvas_data, "
                    "openvas_log). The feed takes 30 min to 3 h.",
                ),
            ),
            dict(
                title="compose.lab.yml",
                tech="profile",
                color=P["red"],
                desc=tr(
                    "juice-shop · dvwa · webgoat. Alvos de laboratório: entram na allow-list "
                    "por opção (TARGET_ALLOWLIST=juice-shop,dvwa).",
                    "juice-shop · dvwa · webgoat. Lab targets: they enter the allow-list "
                    "by choice (TARGET_ALLOWLIST=juice-shop,dvwa).",
                ),
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
                desc=tr(
                    "phoenix (Arize) para rastrear as chamadas de LLM. Volume phoenix_data.",
                    "phoenix (Arize) to trace LLM calls. Volume phoenix_data.",
                ),
            ),
            dict(
                title="compose.proxy.yml · agent.yml",
                tech="profile",
                color=P["gray"],
                desc=tr(
                    "caddy com Caddyfile próprio; cai-expert declarado stub no cabeçalho do "
                    "arquivo.",
                    "caddy with its own Caddyfile; cai-expert declared a stub in the file header.",
                ),
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
        tr("qualquer host com Docker", "any host with Docker"),
        tr("rede cai-net · name: cai", "network cai-net · name: cai"),
        color=P["rose"],
    )

    # ---------------- portas e volumes
    yb = max(yl, y) + 22
    ytab = table(
        c,
        LX,
        yb,
        900,
        [
            tr("porta", "port"),
            tr("quem escuta", "who listens"),
            tr("exposta ao host?", "exposed on the host?"),
        ],
        [
            [
                "8080",
                "orchestrator (FastAPI)",
                tr(
                    "compose: sim · RoqueOS: NÃO, só pela rede interna",
                    "compose: yes · RoqueOS: NO, internal network only",
                ),
            ],
            ["8090", "zap daemon", tr("não", "no")],
            ["4954", "trivy server", tr("não", "no")],
            [
                "11434",
                "ollama",
                tr("compose: sim, se o profile subir", "compose: yes, if the profile is up"),
            ],
            [
                "9392 · 9390",
                tr("greenbone GSA e GMP", "greenbone GSA and GMP"),
                tr("compose: sim, se o profile subir", "compose: yes, if the profile is up"),
            ],
        ],
        [140, 320, 440],
        color=P["accent"],
        title=tr("Portas, e quem realmente as vê", "Ports, and who actually sees them"),
    )

    ytab2 = table(
        c,
        RX,
        yb,
        828,
        [tr("o que garante", "guarantee"), tr("onde está", "where it lives")],
        [
            [
                tr("Trilha imutável", "Immutable trail"),
                tr(
                    "TRIGGER audit_log_no_update no Postgres. Em SQLite não "
                    "existe, e o main.py loga audit.mutable_trail avisando.",
                    "TRIGGER audit_log_no_update in Postgres. It does not exist "
                    "in SQLite, and main.py logs audit.mutable_trail as a warning.",
                ),
            ],
            [
                tr("Segredo em repouso", "Secrets at rest"),
                tr(
                    "Chaves de IA e APP_TOKEN cifrados em AES pelo "
                    "roqueos-server (ENCRYPTION_KEY). O container não guarda "
                    "chave em claro no disco.",
                    "AI keys and APP_TOKEN AES-encrypted by roqueos-server "
                    "(ENCRYPTION_KEY). The container keeps no plaintext key "
                    "on disk.",
                ),
            ],
            [
                tr("Imagem multi-arch", "Multi-arch image"),
                tr(
                    "A stack não subia em Apple Silicon; o Dockerfile "
                    "resolve amd64 e arm64 e valida --version de cada "
                    "binário no build.",
                    "The stack did not start on Apple Silicon; the Dockerfile "
                    "resolves amd64 and arm64 and checks --version of every "
                    "binary at build time.",
                ),
            ],
            [
                tr("Regra de scanner", "Scanner rules"),
                tr(
                    "Semgrep com commit pinado e semgrep --validate como "
                    "gate de build; nuclei com piso de 2000 templates.",
                    "Semgrep pinned to a commit with semgrep --validate as a "
                    "build gate; nuclei with a floor of 2000 templates.",
                ),
            ],
        ],
        [190, 638],
        color=P["green"],
        title=tr("O que a implantação garante", "What the deployment guarantees"),
    )

    footer(
        c,
        tr("fonte: ", "source: ") + "docker/compose*.yml · docker/images/*/Dockerfile · "
        "roqueos-server/src/modules/pentest/pentest-compose.util.ts",
        "github.com/roqueribeiro/roqueos-shield",
        y=max(ytab, ytab2) + 72,
    )
    c.h = int(max(ytab, ytab2) + 96)
    return c
