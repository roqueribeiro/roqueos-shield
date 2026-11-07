import { onMounted, ref, watch } from 'vue'
import { useElementSize } from 'src/composables/useElementSize'

/**
 * A fileira que rola de lado com a barra escondida, e as setas que a tornam alcançável
 * no mouse (Goal 71). As abas do sistema (ROSTabs) e as de documento (ROSDocumentTabs)
 * escondem a barra de rolagem (regra 21): no dedo o arrasto alcança tudo, mas no mouse a
 * roda é vertical, e a aba que não cabia não tinha como ser alcançada (o Chat a 1440:
 * 276px de trilho para 482 de abas; o Navegador com 10 abas: 3 fora).
 *
 *   const fileira = ref(null)   // o elemento que rola; o pai dele é o trilho, com as setas
 *   const { transborda, noInicio, noFim, rtl, medir, rolar, trazerParaVista } =
 *     useFileiraComSetas(fileira)
 *
 * `transborda` diz se as setas aparecem, `noInicio`/`noFim` apagam a seta da ponta,
 * `rolar(-1 | 1)` anda ~70% da largura visível e `trazerParaVista(el)` põe um item inteiro
 * dentro da fileira sem mexer em outra rolagem da tela. Quem muda o conteúdo sem mudar a
 * largura (outra aba, outro idioma) chama `medir()` depois do DOM.
 *
 * Cabe ou não cabe se conta contra o trilho inteiro, sem as setas: medido contra a
 * fileira, a seta que aparece rouba a largura que faltava e nunca mais some. A folga
 * (padding) do trilho não pode mudar com as setas, por isso mesmo.
 */
export function useFileiraComSetas(fileira, { desligada = () => false } = {}) {
  const transborda = ref(false)
  const noInicio = ref(true)
  const noFim = ref(false)
  const rtl = ref(false)

  // No RTL o Chromium conta o scrollLeft de 0 para baixo: o módulo vale nas duas direções.
  const medir = () => {
    const el = fileira.value
    if (!el?.parentElement) return
    const trilho = getComputedStyle(el.parentElement)
    const folgas = (parseFloat(trilho.paddingLeft) || 0) + (parseFloat(trilho.paddingRight) || 0)
    const cabe = el.parentElement.clientWidth - folgas
    transborda.value = !desligada() && el.scrollWidth > cabe + 1
    const sobra = el.scrollWidth - el.clientWidth
    const andado = Math.abs(el.scrollLeft)
    noInicio.value = andado <= 1
    noFim.value = andado >= sobra - 1
  }

  const rolar = (sentido) => {
    const el = fileira.value
    if (!el) return
    const passo = Math.max(el.clientWidth * 0.7, 40) * sentido * (rtl.value ? -1 : 1)
    el.scrollBy?.({ left: passo, behavior: 'smooth' })
  }

  // As contas são na tela, então valem no RTL; o `scrollIntoView` arrastava também a janela.
  const trazerParaVista = (item) => {
    const el = fileira.value
    if (!el || !item) return
    const f = el.getBoundingClientRect()
    const a = item.getBoundingClientRect()
    const folga = 8
    if (a.left < f.left) el.scrollBy?.({ left: a.left - f.left - folga })
    else if (a.right > f.right) el.scrollBy?.({ left: a.right - f.right + folga })
  }

  // A fileira muda de largura com a janela; as fontes chegam depois da montagem.
  const { largura } = useElementSize(fileira)
  watch(largura, medir)
  onMounted(() => {
    if (fileira.value) rtl.value = getComputedStyle(fileira.value).direction === 'rtl'
    medir()
    document.fonts?.ready?.then(medir)
  })

  return { transborda, noInicio, noFim, rtl, medir, rolar, trazerParaVista }
}
