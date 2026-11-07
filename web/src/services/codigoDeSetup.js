/**
 * O código de primeiro uso que o instalador põe no endereço: `http://localhost:8080/#setup=...`.
 *
 * Fica no fragmento (depois do `#`) de propósito: o navegador não manda fragmento ao
 * servidor, então ele não aparece em log de acesso nem de proxy. Lido UMA vez, na
 * importação, antes do roteador (que é por hash) tocar no endereço, e apagado da
 * barra e do histórico na hora: quem olhar a tela depois, ou voltar a página, não vê.
 *
 * Só preenche o campo. Quem cria a conta é o `POST /setup`, que confere o código.
 */
let codigo = ''

try {
  const m = /^#setup=([A-Za-z0-9_-]{8,128})$/.exec(window.location.hash || '')
  if (m) {
    codigo = m[1]
    window.history.replaceState(null, '', window.location.pathname + window.location.search)
  }
} catch {
  codigo = ''
}

/** Devolve o código uma vez e esquece: a tela não guarda além do campo. */
export function tomarCodigoDeSetup() {
  const c = codigo
  codigo = ''
  return c
}
