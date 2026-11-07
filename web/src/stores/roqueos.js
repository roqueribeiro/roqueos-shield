/**
 * O pedaço do store do RoqueOS que a tela do RoqueShield usa, para o standalone.
 *
 * No RoqueOS `openWindow('pdfviewer')` abre o Roque PDF e `openWindow('texteditor')`
 * abre o Editor de Texto. Aqui não há janela de sistema: o arquivo é baixado pelo
 * navegador, com o mesmo nome que teria lá.
 */
import { reactive } from 'vue'
import { Notify } from 'quasar'
// O mesmo corte do RoqueOS (`stores/roqueos/uiViewport.js`): até 768px é celular.
const MOBILE_VIEWPORT_QUERY = '(max-width: 768px)'

const mq = typeof window !== 'undefined' ? window.matchMedia(MOBILE_VIEWPORT_QUERY) : null
const estado = reactive({ isMobileViewport: !!mq?.matches })
mq?.addEventListener?.('change', (e) => (estado.isMobileViewport = e.matches))

const TIPOS = { success: 'positive', error: 'negative', warning: 'warning', info: 'info' }

function baixar(bytesOuTexto, nome, tipo) {
  const blob = new Blob([bytesOuTexto], { type: tipo })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = nome
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 30_000)
}

const store = {
  get isMobileViewport() {
    return estado.isMobileViewport
  },
  showNotification({ message, type = 'info', timeout = 3000 } = {}) {
    Notify.create({ message, type: TIPOS[type] || 'info', timeout, position: 'bottom-right' })
  },
  openWindow(app, { props = {} } = {}) {
    if (app === 'pdfviewer') return baixar(props.fileData, props.fileName, 'application/pdf')
    const ext = String(props.fileName || '').split('.').pop()
    const tipo = { json: 'application/json', csv: 'text/csv', md: 'text/markdown' }[ext] || 'text/plain'
    return baixar(props.content ?? '', props.fileName || 'roqueshield.txt', tipo)
  },
}

export function useRoqueOSStore() {
  return store
}
