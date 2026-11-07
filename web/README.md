# web/ — a tela do RoqueShield standalone

A versão da tela do RoqueShield que roda fora do RoqueOS, servida pelo próprio shield
na raiz (`/`). Vue 3 + Quasar + Vite, JavaScript, yarn.

## De onde veio

Portada do `roqueos-front` em 06/11/2026, por decisão do founder: a tela do RoqueOS
continua no RoqueOS, e o shield ganha a sua versão. A partir daqui as duas evoluem
separadas. O que veio de lá, sem mudança de comportamento:

- `src/components/roqueos/apps/ROSPentest.vue` e `apps/pentest/` (telas, estilos,
  composables, utilitários);
- os primitivos ROS que essas telas usam (`src/components/roqueos/ROS*.vue`) e os
  estilos globais do RoqueOS (`src/css/roqueos/`);
- `src/utils/pentest/` (gerador de PDF e exportadores);
- os namespaces `pentest`, `common`, `errors` e `aiProvider` dos dez idiomas.

O que é só do standalone, no lugar do que o RoqueOS dava:

| No RoqueOS | Aqui |
| --- | --- |
| `stores/roqueos` (janelas, notificação) | `src/stores/roqueos.js`: o PDF e os arquivos são baixados |
| `services/api/pentest.js` via `roqueos-server` | `src/services/api/pentest.js` direto no shield, cookie de sessão |
| central de Provedores de IA | `src/components/roqueos/ai/AIProviderSheet.vue`, com a chave |
| login do RoqueOS | `src/components/shield/TelaEntrada.vue` (primeiro uso e login) |
| analytics | nada: o standalone não manda telemetria |

## Rodar

```bash
yarn install
yarn dev     # :9100, repassa a API para o shield em :8080
yarn build   # saída em ../orchestrator/web_dist, que o FastAPI serve em /
```

## Testes e capturas

```bash
scripts/web_e2e.sh        # e2e em 1440 e 390 contra um shield descartável (o CI roda)
node scripts/idade-do-lock.mjs   # nenhuma dependência com menos de 14 dias (o CI roda)
```

As capturas de tela da documentação (`docs/assets/screens/{en-US,pt-BR}`) saem de
`e2e/capturas.mjs`, nunca de print à mão: quando a tela mudar, refaça com

```bash
SHIELD_URL=http://127.0.0.1:8080 E2E_EMAIL=… E2E_SENHA=… \
  SETUP_URL=http://127.0.0.1:8081 ../scripts/doc_capturas.sh
```

contra um shield com ao menos um scan terminado (`SETUP_URL` é um container novo, para a
tela de primeiro uso). Nenhum segredo vai para a imagem: o primeiro uso é capturado com o
código vazio.
