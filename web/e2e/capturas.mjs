// Capturas da tela standalone para a documentação (docs/assets/screens/<idioma>/).
//
//   SHIELD_URL=http://127.0.0.1:8080 E2E_EMAIL=admin@... E2E_SENHA=... \
//   CAPTURA_IDIOMA=pt-BR CAPTURA_SAIDA=../docs/assets/screens/pt-BR node e2e/capturas.mjs
//
// Precisa de um shield com pelo menos um scan terminado (o detalhe é a parte que mais
// explica a ferramenta). Grava PNG em 2x; quem chama converte para WebP
// (scripts/doc_capturas.sh). Nada secreto vai para a imagem: o primeiro uso é capturado
// com o código vazio, e nenhuma tela que mostra token (o modal de usuário novo) é
// fotografada.
import { mkdirSync } from 'node:fs'
import { chromium } from '@playwright/test'

const BASE = process.env.SHIELD_URL || 'http://127.0.0.1:8080'
const EMAIL = process.env.E2E_EMAIL
const SENHA = process.env.E2E_SENHA
const IDIOMA = process.env.CAPTURA_IDIOMA || 'en-US'
const SAIDA = process.env.CAPTURA_SAIDA || new URL('./capturas', import.meta.url).pathname
mkdirSync(SAIDA, { recursive: true })

// Rótulos da navegação por idioma (os mesmos de src/i18n).
const NAV = {
  'pt-BR': { scans: 'Scans', ia: 'IA', escopo: 'Escopo', usuarios: 'Usuários', novo: 'Novo scan', avancar: /Avançar/ },
  'en-US': { scans: 'Scans', ia: 'AI', escopo: 'Scope', usuarios: 'Users', novo: 'New scan', avancar: /Next/ },
}[IDIOMA]

const b = await chromium.launch()
const espera = (p, ms) => p.waitForTimeout(ms)

async function contexto(largura, altura) {
  const ctx = await b.newContext({
    viewport: { width: largura, height: altura },
    deviceScaleFactor: 2,
    locale: IDIOMA,
  })
  return { ctx, p: await ctx.newPage() }
}

async function entrar(p) {
  await p.goto(`${BASE}/`)
  await p.waitForSelector('input[name=email]')
  await p.fill('input[name=email]', EMAIL)
  await p.fill('input[name=password]', SENHA)
  await p.click('button[type=submit]')
  await p.waitForSelector('.ros-pentest', { timeout: 15000 })
  await espera(p, 1500)
}

async function ir(p, celular, rotulo) {
  if (celular) {
    await p.getByRole('button', { name: /menu/i }).first().click()
    await espera(p, 500)
  }
  const nav = celular ? p.locator('.q-dialog') : p.locator('.ros-pentest__sidebar')
  await nav.getByText(rotulo, { exact: true }).first().click()
  await espera(p, 1200)
}

const foto = (p, nome) => p.screenshot({ path: `${SAIDA}/${nome}.png` })

// --- primeiro uso: num shield que ainda não foi configurado ---------------------
// (CAPTURA_PRIMEIRO_USO=1 contra um container novo; só esta tela, com o código vazio)
if (process.env.CAPTURA_PRIMEIRO_USO === '1') {
  const { ctx, p } = await contexto(1440, 900)
  await p.goto(`${BASE}/`)
  await p.waitForSelector('input[name=setup_code]')
  await espera(p, 600)
  await foto(p, '00-primeiro-uso')
  // Como o install.sh abre a tela: código no fragmento, campo escondido. O código aqui
  // é falso (só zeros): a tela não o mostra, e o shield nem chega a vê-lo.
  // Página nova: o código só é lido no carregamento, como quando o instalador abre.
  await ctx.close()
  const novo = await contexto(1440, 900)
  await novo.p.goto(`${BASE}/#setup=${'0'.repeat(24)}`)
  await novo.p.waitForSelector('.entrada__ok')
  await espera(novo.p, 600)
  await foto(novo.p, '00-primeiro-uso-instalador')
  await novo.ctx.close()
  await b.close()
  process.exit(0)
}
if (!EMAIL || !SENHA) throw new Error('defina E2E_EMAIL e E2E_SENHA')

// --- desktop ---------------------------------------------------------------
{
  const { ctx, p } = await contexto(1440, 900)
  await p.goto(`${BASE}/`)
  await p.waitForSelector('input[name=email]')
  await foto(p, '01-login')
  await entrar(p)
  await foto(p, '02-scans')

  // detalhe do scan mais recente, aba a aba
  await p.locator('.ros-pentest-scans__item').first().click()
  await espera(p, 2000)
  const abas = p.locator('[role=tab]')
  const nomesDasAbas = ['03-detalhe-resumo', '04-detalhe-execucao', '05-detalhe-ia', '06-detalhe-achados']
  for (let i = 0; i < Math.min(await abas.count(), nomesDasAbas.length); i++) {
    await abas.nth(i).click()
    await espera(p, 1800)
    await foto(p, nomesDasAbas[i])
  }

  await ir(p, false, NAV.scans)
  await p.getByRole('button', { name: NAV.novo }).filter({ visible: true }).first().click()
  await espera(p, 1000)
  await foto(p, '07-novo-scan')
  // O erro mais comum de quem começa: testar o app da própria máquina por localhost.
  await p.locator('.ros-pentest__alvo-input input, input.ros-pentest__alvo-input').first().fill('http://localhost:3000')
  await p.getByRole('button', { name: NAV.avancar }).filter({ visible: true }).last().click()
  await p.waitForSelector('.ros-pentest__bloqueio')
  await espera(p, 600)
  await foto(p, '12-alvo-localhost')

  await ir(p, false, NAV.ia)
  await foto(p, '08-ia')
  await ir(p, false, NAV.escopo)
  await foto(p, '09-escopo')
  await ir(p, false, NAV.usuarios)
  await foto(p, '10-usuarios')

  await p.goto(`${BASE}/docs`)
  await p.waitForSelector('.swagger-ui .opblock', { timeout: 20000 })
  await espera(p, 800)
  await foto(p, '11-swagger')
  await ctx.close()
}

// --- celular ---------------------------------------------------------------
{
  const { ctx, p } = await contexto(390, 844)
  await entrar(p)
  await foto(p, '20-celular-scans')
  await p.locator('.ros-pentest-scans__item').first().click()
  await espera(p, 2000)
  await foto(p, '21-celular-detalhe')
  await p.getByRole('button', { name: /menu/i }).first().click()
  await espera(p, 600)
  await foto(p, '22-celular-menu')
  await ctx.close()
}

await b.close()
console.log(`capturas em ${SAIDA}`)
