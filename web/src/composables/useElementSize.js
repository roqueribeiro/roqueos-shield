import { onScopeDispose, ref, watch } from 'vue'

/**
 * O tamanho de um elemento, reativo (Goal 65).
 *
 *   const caixa = ref(null)
 *   const { largura, altura } = useElementSize(caixa)
 *
 * Eram 15 `ResizeObserver` à mão, e mais de um sem `disconnect` no desmontar. Aqui o
 * observador segue o elemento (se o `ref` troca de nó, ele troca junto) e morre com o
 * componente. Sem `ResizeObserver` (jsdom, navegador velho), fica no tamanho da montagem.
 *
 * O padrão é o tamanho na tela (`getBoundingClientRect`, com o zoom da escala da interface e
 * as transformações). Quem compara com uma largura medida em CSS (a barra que recolhe abaixo
 * de N px) pede `{ layout: true }`: o tamanho da caixa (`offsetWidth`), que a animação de
 * abrir a janela (escala de 0,3 a 1) não encolhe. Medida na tela, a barra do RoqueCode media
 * uns 270px no começo da animação, recolhia, e o ResizeObserver não avisava de novo quando
 * a escala voltava a 1 (transformação não muda o tamanho da caixa). Goal 71.
 */
export function useElementSize(alvo, { layout = false } = {}) {
  const largura = ref(0)
  const altura = ref(0)
  let observador = null

  const medir = (el) => {
    if (layout) {
      largura.value = el.offsetWidth
      altura.value = el.offsetHeight
      return
    }
    const r = el.getBoundingClientRect()
    largura.value = Math.round(r.width)
    altura.value = Math.round(r.height)
  }

  const parar = watch(
    alvo,
    (el) => {
      observador?.disconnect()
      observador = null
      if (!el) return
      medir(el)
      if (typeof ResizeObserver === 'undefined') return
      observador = new ResizeObserver(() => medir(el))
      observador.observe(el)
    },
    { immediate: true, flush: 'post' },
  )

  onScopeDispose(() => {
    parar()
    observador?.disconnect()
  })
  return { largura, altura }
}
