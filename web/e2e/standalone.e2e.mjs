// E2e da tela standalone contra um shield de verdade (uvicorn com SQLite novo).
//
//   SHIELD_URL=http://127.0.0.1:8099 E2E_SENHA=... node e2e/standalone.e2e.mjs
//
// Num banco vazio ele passa pelo primeiro uso (cria o admin pela tela). Depois, em 1440
// e 390: login, cada seção sem transbordo horizontal, e o fluxo de Usuários inteiro
// (criar só com token, token mostrado uma vez e aceito pela API, senha curta recusada,
// senha salva, 409 do último admin, desativar pelo confirmar() e o token parar de valer).
// Sai com código 1 na primeira asserção falsa. Prints vão para E2E_SHOTS (padrão:
// e2e/shots, fora do git), com o token borrado antes.
import assert from 'node:assert/strict'
import { mkdirSync } from 'node:fs'
import { chromium } from '@playwright/test'

const BASE = process.env.SHIELD_URL || 'http://127.0.0.1:8099'
const EMAIL = process.env.E2E_EMAIL || 'admin@roqueshield.local'
const SENHA = process.env.E2E_SENHA
// O e2e lê o código como quem instala: do arquivo de segredos do container (aqui, o
// script exporta o que o `segredos` gerou).
const SHOTS = process.env.E2E_SHOTS || new URL('./shots', import.meta.url).pathname
assert.ok(SENHA && SENHA.length >= 10, 'E2E_SENHA precisa de pelo menos 10 caracteres')
mkdirSync(SHOTS, { recursive: true })

const VIEWPORTS = [
  ['1440', { width: 1440, height: 900 }],
  ['390', { width: 390, height: 844 }],
]
const SECOES = ['Scans', 'IA', 'Escopo', 'Usuários']
const espera = (p, ms) => p.waitForTimeout(ms)
const ok = (m) => console.log(`  ok  ${m}`)

const b = await chromium.launch()
const erros = []

async function abrir(vp, nome) {
  const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: 1, locale: 'pt-BR' })
  const p = await ctx.newPage()
  p.on('pageerror', (e) => erros.push(`${nome} pageerror: ${e.message}`))
  p.on('console', (m) => /Content Security Policy|Refused to/.test(m.text()) && erros.push(`${nome} CSP: ${m.text()}`))
  return { ctx, p }
}

const transbordo = (p) => p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)

async function irPara(p, nome, secao) {
  if (nome === '390') {
    await p.getByRole('button', { name: /menu/i }).first().click()
    await espera(p, 500)
  }
  // No celular a navegação abre num diálogo por cima da página; no desktop, a barra lateral.
  // O título da página repete o nome da seção, então o clique mira só a navegação.
  const nav = nome === '390' ? p.locator('.q-dialog') : p.locator('.ros-pentest__sidebar')
  await nav.getByText(secao, { exact: true }).first().click()
  await espera(p, 900)
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

try {
  const setup = await (await fetch(`${BASE}/setup`)).json()
  if (setup.needs_setup) {
    // Como o install.sh abre a tela: código no fragmento, campo escondido, barra limpa.
    {
      const { ctx, p } = await abrir(VIEWPORTS[0][1], 'instalador')
      await p.goto(`${BASE}/#setup=${process.env.SETUP_CODE || ''}`)
      await p.waitForSelector('.entrada__ok')
      assert.equal(await p.locator('input[name=setup_code]').count(), 0, 'campo do código à vista')
      assert.ok(!p.url().includes('setup='), `o código ficou no endereço: ${p.url()}`)
      await ctx.close()
      ok('o código do instalador vem pelo fragmento e some da barra')
    }
    const { ctx, p } = await abrir(VIEWPORTS[0][1], 'setup')
    await p.goto(`${BASE}/`)
    await p.waitForSelector('input[name=name]')
    await p.screenshot({ path: `${SHOTS}/setup.png` })
    await p.fill('input[name=email]', EMAIL)
    await p.fill('input[name=name]', 'Admin E2E')
    await p.fill('input[name=password]', SENHA)
    // Sem o código de primeiro uso o setup é recusado (403) e a tela diz por quê.
    await p.fill('input[name=setup_code]', 'codigo-errado')
    await p.click('button[type=submit]')
    await p.waitForSelector('.entrada__erro', { timeout: 5000 })
    assert.equal((await (await fetch(`${BASE}/setup`)).json()).needs_setup, true, 'setup aceitou código errado')
    await p.fill('input[name=setup_code]', process.env.SETUP_CODE || '')
    await p.click('button[type=submit]')
    await p.waitForSelector('.ros-pentest', { timeout: 15000 })
    ok('primeiro uso recusa código errado, cria o admin com o certo e entra')
    await ctx.close()
  }
  assert.equal((await (await fetch(`${BASE}/setup`)).json()).needs_setup, false, 'setup ainda pendente')

  for (const [nome, vp] of VIEWPORTS) {
    const { ctx, p } = await abrir(vp, nome)
    await entrar(p)
    await p.screenshot({ path: `${SHOTS}/${nome}-entrou.png` })
    ok(`${nome} login`)

    if (nome === '1440') {
      // Alvo que o escopo recusa: explicado no passo 1, com o caminho certo.
      await p.getByRole('button', { name: 'Novo scan' }).filter({ visible: true }).first().click()
      await espera(p, 600)
      const alvo = p.locator('input').filter({ visible: true }).first()
      const avancar = p.getByRole('button', { name: /Avançar/ }).filter({ visible: true }).last()
      await alvo.fill('http://localhost:3000')
      await avancar.click()
      await p.waitForSelector('.ros-pentest__bloqueio')
      await p.screenshot({ path: `${SHOTS}/${nome}-alvo-localhost.png` })
      await p.getByRole('button', { name: /Usar host\.docker\.internal/ }).click()
      await espera(p, 800)
      assert.equal(await alvo.inputValue(), 'http://host.docker.internal:3000', 'a troca do host não aconteceu')
      ok(`${nome} localhost explicado e trocado por host.docker.internal`)

      await alvo.fill('http://10.20.30.40/')
      await avancar.click()
      await p.waitForSelector('.ros-pentest__bloqueio')
      await espera(p, 800)
      await p.screenshot({ path: `${SHOTS}/${nome}-alvo-rede-interna.png` })
      await p.getByRole('button', { name: /Liberar 10\.20\.30\.40/ }).first().click()
      await espera(p, 400)
      await p.locator('.ros-modal').getByRole('button', { name: /Liberar 10\.20\.30\.40/ }).last().click()
      await p.waitForSelector('text=Qual a profundidade da varredura?', { timeout: 5000 })
      const cookie = (await ctx.cookies()).map((c) => `${c.name}=${c.value}`).join('; ')
      const escopo = await (await fetch(`${BASE}/settings/scope`, { headers: { cookie } })).json()
      assert.ok(escopo.allowlist.includes('10.20.30.40'), 'liberar não gravou no escopo')
      ok(`${nome} rede interna liberada no escopo pela tela, e o assistente segue`)
    }

    for (const secao of SECOES) {
      await irPara(p, nome, secao)
      const t = await transbordo(p)
      await p.screenshot({ path: `${SHOTS}/${nome}-${secao.toLowerCase()}.png` })
      assert.equal(t, 0, `${nome} ${secao}: transbordo horizontal de ${t}px`)
    }
    ok(`${nome} ${SECOES.length} seções sem transbordo`)

    // Usuários: a última seção visitada.
    const email = `ci-${nome}-${Date.now()}@roqueshield.local`
    await p.getByRole('button', { name: 'Novo usuário' }).click()
    await espera(p, 400)
    await p.locator('#form-novo-usuario input[name=email]').fill(email)
    await p.getByRole('button', { name: 'Criar e mostrar token' }).click()
    await p.waitForSelector('.usuarios__token-txt')
    const token = await p.locator('.usuarios__token-txt').innerText()
    assert.ok(token.length >= 32, `token curto demais (${token.length})`)
    const r = await fetch(`${BASE}/auth/session`, { headers: { 'X-API-Token': token } })
    assert.equal(r.status, 200, `o token mostrado não autentica na API (${r.status})`)
    await p.evaluate(() =>
      document.querySelectorAll('.usuarios__token-txt').forEach((e) => (e.textContent = '•'.repeat(24))),
    )
    await p.screenshot({ path: `${SHOTS}/${nome}-token.png` })
    await p.getByRole('button', { name: 'Já guardei' }).click()
    await espera(p, 600)
    const item = p.locator('.usuarios__item', { hasText: email })
    assert.equal(await item.count(), 1, 'usuário novo não apareceu na lista')
    assert.equal(await item.getByText('só token').count(), 1, 'usuário sem senha sem o selo "só token"')
    ok(`${nome} criar com token, e o token autentica na API`)

    await item.getByRole('button', { name: 'Definir senha' }).click()
    await espera(p, 400)
    await p.locator('#form-senha input[type=password]').fill('curta')
    await p.locator('.ros-modal').getByRole('button', { name: 'Salvar senha' }).click()
    await espera(p, 400)
    assert.equal(await p.locator('#form-senha [role=alert]').count(), 1, 'senha curta passou sem aviso')
    await p.locator('#form-senha input[type=password]').fill('outra-senha-forte-456')
    await p.locator('.ros-modal').getByRole('button', { name: 'Salvar senha' }).click()
    await espera(p, 900)
    assert.equal(await item.getByText('senha e token').count(), 1, 'senha salva sem o selo')
    ok(`${nome} senha curta recusada, senha boa salva`)

    const eu = p.locator('.usuarios__item', { hasText: EMAIL })
    await eu.locator('.q-select').click()
    await espera(p, 300)
    await p.locator('.q-menu .q-item', { hasText: 'Operador' }).click()
    await espera(p, 1200)
    const cookie = (await ctx.cookies()).map((c) => `${c.name}=${c.value}`).join('; ')
    const sessao = await (await fetch(`${BASE}/auth/session`, { headers: { cookie } })).json()
    assert.equal(sessao.role, 'admin', 'o último admin foi rebaixado')
    ok(`${nome} último admin não rebaixa`)

    await item.getByRole('button', { name: 'Desativar' }).click()
    await espera(p, 500)
    await p.screenshot({ path: `${SHOTS}/${nome}-confirmar.png` })
    await p.locator('.ros-modal').getByRole('button', { name: 'Desativar' }).last().click()
    await espera(p, 900)
    assert.equal(await item.getByText('desativado').count(), 1, 'desativar não refletiu na lista')
    const r2 = await fetch(`${BASE}/auth/session`, { headers: { 'X-API-Token': token } })
    assert.equal(r2.status, 401, `token de usuário desativado ainda autentica (${r2.status})`)
    ok(`${nome} desativar pelo confirmar() corta o token`)

    await ctx.close()
  }
  assert.deepEqual(erros, [], `erros de página:\n${erros.join('\n')}`)
  console.log('e2e standalone: tudo verde')
} catch (e) {
  console.error(`FALHOU: ${e.message}`)
  process.exitCode = 1
} finally {
  await b.close()
}
