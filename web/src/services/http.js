/**
 * Cliente HTTP da tela standalone.
 *
 * A sessão é o cookie `rs_session` (httpOnly): o JavaScript não vê credencial
 * nenhuma. Toda escrita leva o cabeçalho `X-RoqueShield`, que o shield exige em
 * escrita por cookie (é o que impede CSRF: outro site não consegue pôr cabeçalho
 * próprio sem preflight, e o shield não libera CORS).
 */
const ESCRITA = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])
const ouvintesDe401 = new Set()

export function aoPerderSessao(fn) {
  ouvintesDe401.add(fn)
  return () => ouvintesDe401.delete(fn)
}

export class ErroHttp extends Error {
  constructor(status, detalhe) {
    super(typeof detalhe === 'string' ? detalhe : `HTTP ${status}`)
    this.status = status
    this.detail = detalhe
  }
}

export async function http(metodo, caminho, corpo) {
  const headers = { Accept: 'application/json' }
  if (ESCRITA.has(metodo)) headers['X-RoqueShield'] = '1'
  if (corpo !== undefined) headers['Content-Type'] = 'application/json'
  const r = await fetch(caminho, {
    method: metodo,
    headers,
    credentials: 'same-origin',
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  })
  if (r.status === 204) return null
  const tipo = r.headers.get('content-type') || ''
  const dado = tipo.includes('json') ? await r.json().catch(() => null) : await r.text()
  if (!r.ok) {
    if (r.status === 401) ouvintesDe401.forEach((fn) => fn())
    throw new ErroHttp(r.status, dado?.detail ?? dado)
  }
  return dado
}

export const get = (c) => http('GET', c)
export const post = (c, b = {}) => http('POST', c, b)
export const put = (c, b = {}) => http('PUT', c, b)
export const del = (c) => http('DELETE', c)
