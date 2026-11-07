import { ref, onMounted, onUnmounted } from 'vue'

/**
 * How much of the screen the MOBILE OS KEYBOARD is currently covering, in px.
 *
 * ⚠️ ISTO VALE NO NAVEGADOR, E **NÃO** DENTRO DO APP NATIVO. A frase que estava
 * aqui — "nem iOS nem Android encolhem o layout viewport" — é verdadeira no
 * Safari e no Chrome, e FALSA no RoqueOS empacotado. Medido em 30/08/2026 com o
 * teclado aberto, no WebView do Capacitor de verdade:
 *
 *              sem teclado   com teclado   inset que este arquivo publica
 *   iOS            874           539                    0
 *   Android        839           527                    0
 *
 * Nos dois casos `innerHeight` e `visualViewport.height` encolhem JUNTOS, então
 * `hidden` dá zero e o inset é zero — e está CERTO, porque o viewport já
 * encolheu e o `100dvh` acompanhou. iOS por `resize: KeyboardResize.Native` na
 * `capacitor.config.ts`; Android pelo `adjustResize` padrão.
 *
 * Ou seja: no app este composable é inerte de propósito, e quem levanta o
 * conteúdo é o próprio encolhimento do WebView. Ele continua necessário no
 * NAVEGADOR, onde nada encolhe e só o `visualViewport` conta a verdade.
 *
 * ⚠️ Escrevi um vigia inteiro (`tecladoNaoDesalinha`) em cima da frase errada
 * que estava aqui, e ele nunca executou uma vez nas duas plataformas. Antes de
 * confiar nesta prosa de novo, meça no aparelho: o harness está em
 * `~/workspaces/_qa-teclado/`.
 *
 * Two consumers, one source:
 *   - the returned `keyboardInset` ref, for components that need the number
 *     (a sheet lifting itself);
 *   - the `--ros-keyboard-inset` CSS variable on `<html>`, so stylesheets can
 *     react without every component wiring a prop (see `overlays.scss`).
 *
 * The listener is shared: N open overlays cost one `visualViewport` handler.
 */

const keyboardInset = ref(0)
let refCount = 0
let detach = null

// The visual viewport also shrinks when a browser URL bar expands, which is not
// a keyboard and must not shove panels around. A keyboard is far taller than
// any browser chrome, so a floor cleanly separates the two.
const MIN_KEYBOARD_PX = 100

const measure = () => {
  const vv = typeof window !== 'undefined' ? window.visualViewport : null
  if (!vv) return 0
  // The slice of the layout viewport hidden below the visual one.
  const hidden = window.innerHeight - (vv.height + vv.offsetTop)
  return hidden > MIN_KEYBOARD_PX ? Math.round(hidden) : 0
}

const apply = () => {
  const next = measure()
  if (next === keyboardInset.value) return
  keyboardInset.value = next
  if (typeof document !== 'undefined') {
    document.documentElement.style.setProperty('--ros-keyboard-inset', `${next}px`)
  }
}

const start = () => {
  const vv = typeof window !== 'undefined' ? window.visualViewport : null
  if (!vv || detach) return
  // `scroll` matters as much as `resize`: iOS pans the visual viewport when a
  // focused field would otherwise sit under the keyboard, which moves offsetTop
  // without changing height.
  vv.addEventListener('resize', apply)
  vv.addEventListener('scroll', apply)
  detach = () => {
    vv.removeEventListener('resize', apply)
    vv.removeEventListener('scroll', apply)
    detach = null
  }
  apply()
}

const stop = () => {
  if (detach) detach()
  keyboardInset.value = 0
  if (typeof document !== 'undefined') {
    document.documentElement.style.setProperty('--ros-keyboard-inset', '0px')
  }
}

export function useKeyboardInset() {
  onMounted(() => {
    refCount += 1
    start()
  })

  onUnmounted(() => {
    refCount = Math.max(0, refCount - 1)
    // Only the last overlay to close tears the listener down, and it resets the
    // variable so a stale inset never keeps a later panel pushed up.
    if (refCount === 0) stop()
  })

  return { keyboardInset }
}

// Exposed for tests: they need to drive the measurement without a real keyboard.
export const __internals = { measure, apply, MIN_KEYBOARD_PX }
