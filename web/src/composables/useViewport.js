import { computed, onScopeDispose, readonly, ref } from 'vue'

/**
 * O tamanho da tela e as quebras do sistema, num lugar só (Goal 65).
 *
 *   const { celular, tablet, toque, semHover } = useViewport()
 *
 * Eram 83 `window.innerWidth` e `matchMedia` à mão em 47 arquivos, com quatro números de
 * quebra diferentes (600, 640, 768 e 769) e listeners de `resize` que ninguém removia.
 * As quebras são as da regra: celular abaixo de 600, tablet abaixo de 768. Um listener
 * só serve todo mundo, e sai quando o último componente desmonta.
 */
export const QUEBRA_CELULAR = 600
export const QUEBRA_TABLET = 768

const largura = ref(typeof window === 'undefined' ? 1024 : window.innerWidth)
const altura = ref(typeof window === 'undefined' ? 768 : window.innerHeight)
const toque = ref(false)
// `toque` é o ponteiro grosso (pointer: coarse); `semHover` é não ter como passar por cima
// (hover: none). Um aparelho híbrido (tela de toque com mouse ou caneta) é toque e tem
// hover: o gesto que é só de dedo pede os dois.
const semHover = ref(false)
let usuarios = 0
let consultaDeToque = null
let consultaDeHover = null

const medir = () => {
  largura.value = window.innerWidth
  altura.value = window.innerHeight
}
const aoTrocarToque = (e) => (toque.value = e.matches)
const aoTrocarHover = (e) => (semHover.value = e.matches)

function ligar() {
  medir()
  window.addEventListener('resize', medir, { passive: true })
  if (typeof window.matchMedia === 'function') {
    consultaDeToque = window.matchMedia('(pointer: coarse)')
    toque.value = consultaDeToque.matches
    consultaDeToque.addEventListener?.('change', aoTrocarToque)
    consultaDeHover = window.matchMedia('(hover: none)')
    semHover.value = consultaDeHover.matches
    consultaDeHover.addEventListener?.('change', aoTrocarHover)
  }
}

function desligar() {
  window.removeEventListener('resize', medir)
  consultaDeToque?.removeEventListener?.('change', aoTrocarToque)
  consultaDeHover?.removeEventListener?.('change', aoTrocarHover)
  consultaDeToque = null
  consultaDeHover = null
}

export function useViewport() {
  if (typeof window !== 'undefined') {
    if (usuarios++ === 0) ligar()
    onScopeDispose(() => {
      if (--usuarios === 0) desligar()
    })
  }
  return {
    largura: readonly(largura),
    altura: readonly(altura),
    toque: readonly(toque),
    semHover: readonly(semHover),
    celular: computed(() => largura.value < QUEBRA_CELULAR),
    tablet: computed(() => largura.value < QUEBRA_TABLET),
  }
}
