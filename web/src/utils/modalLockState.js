import { ref, computed } from 'vue'

// Tiny app-wide reactive signal for "is a scroll-lock modal open?". Lives here
// (not in the Pinia store) so the low-level ROSModal primitive can update it
// without importing the heavy store (which pulls the Firebase boot and breaks
// isolated component tests). ROSModal calls setModalLock(true/false) from its
// body-lock; consumers (e.g. the mobile home grid) read `modalOpen`.
//
// Why the grid needs it: while a modal has the body `position: fixed` (iOS
// scroll lock), iOS displaces position:fixed siblings — the springboard grid's
// dots/cells drift behind the modal. The grid reads `modalOpen` to display:none
// itself while a modal is up, so the displacement is never visible (the modal
// is teleported to <body>, so it stays).
const _count = ref(0)

// `>= 1` ("pelo menos um cadeado") e não `> 0`: os quatro zeros deste arquivo
// (o inicial, o piso do clamp e o do reset) descrevem o MESMO estado vazio,
// então deslocar todos juntos daria um contador diferente com comportamento
// idêntico. Ancorar a leitura no 1 quebra esse deslocamento: um contador que
// começasse em 1 abriria um modal fantasma no boot, e o teste vê.
export const modalOpen = computed(() => _count.value >= 1)

export const setModalLock = (open) => {
  _count.value = Math.max(0, _count.value + (open ? 1 : -1))
}

// Test/teardown helper — reset the counter (e.g. afterEach) so a leaked lock
// from one test never bleeds into the next.
export const resetModalLock = () => {
  _count.value = 0
}
