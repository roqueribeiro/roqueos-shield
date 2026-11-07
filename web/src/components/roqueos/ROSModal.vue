<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div
        v-if="modelValue"
        class="ros-modal-overlay"
        :class="overlayClass"
        :style="camada ? { zIndex: camada } : undefined"
        @mousedown.self="handleBackdropMouseDown"
        @click.self="handleBackdropClick"
      >
        <div
          ref="modalRef"
          class="ros-modal"
          :class="modalClass"
          :style="modalStyle"
          role="dialog"
          aria-modal="true"
          tabindex="-1"
        >
          <div class="ros-modal__header">
            <div v-if="iconUrl" class="ros-modal__icon ros-modal__icon--image" :class="iconClass">
              <img :src="iconUrl" :alt="title" />
            </div>
            <div v-else-if="icon" class="ros-modal__icon" :class="iconClass">
              <q-icon :name="icon" size="24px" />
            </div>

            <div class="ros-modal__title">
              <h3>{{ title }}</h3>
              <p v-if="subtitle">{{ subtitle }}</p>
            </div>

            <div class="ros-modal__header-actions">
              <slot name="header-right" />
              <ROSIconButton
                v-if="showClose"
                icon="close"
                :label="$t('common.close')"
                :size="28"
                variant="tonal"
                class="ros-modal__action-btn--close"
                @click="requestClose"
              />
            </div>
          </div>

          <div
            v-if="$slots.default"
            ref="contentRef"
            class="ros-modal__content ros-scrollbar-hidden"
          >
            <slot />
          </div>

          <div
            v-if="$slots.footer"
            class="ros-modal__footer"
            :class="{ 'ros-modal__footer--no-content': !$slots.default }"
          >
            <slot name="footer" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { setModalLock } from 'src/utils/modalLockState'
// Publishes `--ros-keyboard-inset`, which overlays.scss uses to lift a centred
// modal off the OS keyboard so its footer buttons stay reachable while typing.
import { useKeyboardInset } from 'src/composables/useKeyboardInset'
import { useDebounced } from 'src/composables/useDebounced'
import { useViewport } from 'src/composables/useViewport'
import ROSIconButton from './ROSIconButton.vue'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  title: {
    type: String,
    required: true,
  },
  subtitle: {
    type: String,
    default: '',
  },
  icon: {
    type: String,
    default: '',
  },
  iconUrl: {
    type: String,
    default: '',
  },
  variant: {
    type: String,
    default: 'default',
    validator: (v) => ['default', 'danger', 'warning', 'info', 'success'].includes(v),
  },
  size: {
    type: String,
    default: 'md',
    validator: (v) => ['sm', 'md', 'lg', 'xl', 'fullscreen'].includes(v),
  },
  // Opt-in: on phones (≤768px) render as an edge-to-edge bottom sheet instead
  // of the default centered card. Reserve for genuinely full-screen content
  // (onboarding hero, large galleries). Most modals — even lg/xl forms/pickers
  // — should stay centered cards (the "Nova Pasta" standard) on mobile.
  mobileSheet: {
    type: Boolean,
    default: false,
  },
  width: {
    type: String,
    default: '',
  },
  minWidth: {
    type: String,
    default: '',
  },
  maxWidth: {
    type: String,
    default: '',
  },
  height: {
    type: String,
    default: '',
  },
  minHeight: {
    type: String,
    default: '',
  },
  maxHeight: {
    type: String,
    default: '',
  },
  type: {
    type: String,
    default: 'form',
    validator: (v) => ['form', 'confirm', 'alert', 'info', 'progress'].includes(v),
  },
  closeOnBackdrop: {
    type: Boolean,
    default: undefined,
  },
  closeOnEsc: {
    type: Boolean,
    default: true,
  },
  lockScroll: {
    type: Boolean,
    default: true,
  },
  showClose: {
    type: Boolean,
    default: true,
  },
  initialFocus: {
    type: String,
    default: '',
  },
  // A camada do fundo, para quem precisa abrir POR CIMA de outro modal já aberto (a
  // confirmação do sistema). Todo modal tem 9999 e, empatados, vence a ordem no `<body>`,
  // que é a da montagem do Teleport e não a da abertura.
  camada: {
    type: Number,
    default: 0,
  },
})

const emit = defineEmits(['update:modelValue', 'close', 'opened', 'closed'])

const { keyboardInset } = useKeyboardInset()
// A altura da tela é a do sistema (um listener só para todos os modais abertos).
const { altura: alturaDaTela } = useViewport()

const modalRef = ref(null)
const contentRef = ref(null)
// O corpo rola? Sem divisórias, a linha do cabeçalho e do rodapé só aparece quando há
// conteúdo passando por baixo delas (overlays.scss, `--rolando`).
const rolando = ref(false)
let observadorDoCorpo = null
let mutacoesDoCorpo = null
let lastActiveElement = null
let backdropMouseDown = false

const effectiveCloseOnBackdrop = computed(() => {
  if (typeof props.closeOnBackdrop === 'boolean') return props.closeOnBackdrop
  return props.type !== 'form'
})

const iconClass = computed(() => {
  const base = 'ros-modal__icon--' + props.variant
  return {
    [base]: props.variant !== 'default',
  }
})

// Confirmação e alerta leem como uma pergunta: ícone em cima, texto e botões
// centralizados. Só até `md`, onde o corpo é curto; lg/xl e a folha de baixo continuam
// com o cabeçalho lateral.
const centrado = computed(
  () =>
    ['confirm', 'alert'].includes(props.type) &&
    ['sm', 'md'].includes(props.size) &&
    !props.mobileSheet,
)

const modalClass = computed(() => {
  return {
    [`ros-modal--${props.size}`]: true,
    [`ros-modal--${props.variant}`]: props.variant !== 'default',
    'ros-modal--mobile-sheet': props.mobileSheet,
    'ros-modal--centrado': centrado.value,
    'ros-modal--rolando': rolando.value,
  }
})

const medirRolagem = () => {
  const el = contentRef.value
  rolando.value = !!el && el.scrollHeight > el.clientHeight + 1
}

const observarCorpo = async () => {
  await nextTick()
  // Fechou antes do tique: não sobra observador vivo até o desmonte.
  if (!props.modelValue) return
  medirRolagem()
  const el = contentRef.value
  if (!el || typeof ResizeObserver === 'undefined') return
  observadorDoCorpo?.disconnect()
  // Observador próprio, e não o useElementSize: aquele segue um elemento só, e aqui são o
  // corpo e cada filho dele, inclusive os que chegam depois.
  observadorDoCorpo = new ResizeObserver(medirRolagem)
  observadorDoCorpo.observe(el)
  // O corpo cresce por dentro sem mudar a própria caixa quando já bateu no max-height:
  // por isso os filhos também entram na observação, inclusive os que chegam depois (a
  // lista que carrega, o formulário que aparece quando o dado chega).
  const observarFilhos = () => {
    for (const filho of el.children) observadorDoCorpo?.observe(filho)
  }
  observarFilhos()
  if (typeof MutationObserver === 'undefined') return
  mutacoesDoCorpo?.disconnect()
  mutacoesDoCorpo = new MutationObserver(() => {
    observarFilhos()
    medirRolagem()
  })
  mutacoesDoCorpo.observe(el, { childList: true, subtree: true })
}

const pararDeObservar = () => {
  observadorDoCorpo?.disconnect()
  observadorDoCorpo = null
  mutacoesDoCorpo?.disconnect()
  mutacoesDoCorpo = null
  rolando.value = false
}

const modalStyle = computed(() => {
  if (props.size === 'fullscreen') {
    return {
      width: '100%',
      maxWidth: '100%',
      height: '100%',
      maxHeight: '100%',
    }
  }

  const style = {}

  // Re-declare the keyboard inset ON THIS ELEMENT. The stylesheet already
  // subtracts it from max-height, but Chrome (measured on Android) does not
  // reliably invalidate that rule when the variable changes up on <html>: the
  // identical expression applied inline resolved to 411px while the stylesheet
  // rule stayed at 771px, leaving the footer under the keyboard. An inline
  // custom property is a direct declaration on the element, so it always
  // invalidates, and the height maths stays in CSS where the Capacitor variant
  // can keep its own version.
  style['--ros-keyboard-inset'] = `${keyboardInset.value}px`

  if (props.width) {
    style.width = props.width
    // When width is provided, it should be able to exceed the default CSS max-width
    if (!props.maxWidth) {
      style.maxWidth = props.width
    }
  }

  if (props.minWidth) style.minWidth = props.minWidth
  if (props.maxWidth) style.maxWidth = props.maxWidth

  if (props.height) style.height = props.height
  if (props.minHeight) style.minHeight = props.minHeight
  // O `max-height` de quem chama não pode desligar o recuo do teclado: um `85dvh` inline
  // vencia o cálculo da folha de estilo e o rodapé do Ambientes do Roqueman ia para trás
  // do teclado (medido no cenário celular-teclado do modais.spec.js).
  if (props.maxHeight) {
    style.maxHeight = `min(${props.maxHeight}, calc(100dvh - 40px - var(--ros-keyboard-inset, 0px)))`
  }

  return style
})

const overlayClass = computed(() => {
  return {
    [`ros-modal-overlay--${props.variant}`]: props.variant !== 'default',
    // Size class kept on the overlay for any size-specific tweaks.
    [`ros-modal-overlay--${props.size}`]: true,
    // Mobile bottom-sheet is OPT-IN (overlays.scss @media 768px targets this).
    // By default every modal — including lg/xl — stays a centered card on
    // phones, matching the "Nova Pasta" standard.
    'ros-modal-overlay--mobile-sheet': props.mobileSheet,
  }
})

// Locks body scroll so swipes on the modal don't bleed into the page
// underneath. Counts modal instances so stacked modals work correctly:
// the body is frozen on the first open and unfrozen on the last close.
//
// On mobile (iOS Safari / Android Chrome) `overflow: hidden` is not
// enough — during an in-flight touch the browser keeps scrolling the
// body. The reliable fix is `position: fixed; top: -scrollY`, captured
// on lock and restored on unlock. The CSS for body.ros-modal-open lives
// in src/css/roqueos/core.scss.
const updateBodyLock = (open) => {
  if (!props.lockScroll) return
  // Reactive signal so the mobile home grid (a position:fixed sibling) can
  // display:none itself while the body is scroll-locked — otherwise it drifts
  // behind the modal on iOS (body position:fixed displaces fixed elements).
  // A tiny standalone module (no store/Firebase) so this low-level primitive
  // stays mountable in isolated tests.
  setModalLock(open)
  const body = document.body
  const current = Number.parseInt(body.dataset.rosModalCount || '0', 10)
  const next = open ? current + 1 : Math.max(0, current - 1)
  body.dataset.rosModalCount = String(next)

  if (next > 0 && current === 0) {
    // Only freeze the body when the page can ACTUALLY scroll. In the RoqueOS
    // app the layout is `position: fixed` (the body never scrolls), so the
    // freeze is pointless AND harmful: `body { position: fixed }` collapses
    // env(safe-area-inset-top) to 0 on iOS, which shoves fullscreen windows up
    // to the top the moment a modal appears (reported: delete-widget modal
    // breaks app navigation). Skipping it when there's nothing to scroll fixes
    // that, and landings (which DO scroll) still get the lock.
    // Two signals that the page can't scroll (so freezing is unnecessary AND
    // harmful on iOS):
    //  1) The RoqueOS app shell (.ros-layout) is position:fixed — the body
    //     NEVER scrolls in the app. This is the reliable signal; the
    //     scrollHeight heuristic below is fragile on iOS (100dvh ≠ innerHeight
    //     during URL-bar transitions, so it can wrongly report "scrollable").
    //  2) Fallback for non-app contexts (landings): the document doesn't
    //     overflow the viewport.
    const appRoot = typeof document !== 'undefined' ? document.querySelector('.ros-layout') : null
    const inFixedApp = !!appRoot && getComputedStyle(appRoot).position === 'fixed'
    const el = document.documentElement
    const scrollable = !inFixedApp && el.scrollHeight > (alturaDaTela.value || el.clientHeight) + 1
    if (!scrollable) {
      body.dataset.rosModalFrozen = '0'
      return
    }
    body.dataset.rosModalFrozen = '1'
    // First modal in the stack — capture scroll, freeze body.
    const scrollY = window.scrollY || document.documentElement.scrollTop || 0
    body.dataset.rosModalScrollY = String(scrollY)
    body.style.top = `-${scrollY}px`
    body.classList.add('ros-modal-open')
  } else if (next === 0 && current > 0) {
    // Last modal closed. If we never froze (non-scrollable page), nothing to do.
    if (body.dataset.rosModalFrozen !== '1') {
      delete body.dataset.rosModalFrozen
      return
    }
    delete body.dataset.rosModalFrozen
    // Thaw body and restore scroll without a visual jump (position: fixed snaps
    // the viewport to 0 otherwise).
    const scrollY = Number.parseInt(body.dataset.rosModalScrollY || '0', 10)
    body.classList.remove('ros-modal-open')
    body.style.top = ''
    delete body.dataset.rosModalScrollY
    if (scrollY > 0) {
      window.scrollTo(0, scrollY)
    }
    // The body just went back to `position: static`. Any layout state frozen
    // while it was fixed (notably the safe-area / menu-bar offset recompute,
    // skipped during `ros-modal-open`) must re-run with a clean body. Defer to
    // the next frame so the browser has actually settled `position: static`
    // before the recompute probes env() — firing synchronously can still read a
    // fixed body on iOS. The layout's recompute is also sticky-in-portrait, so
    // this is belt-and-suspenders.
    if (typeof window !== 'undefined') {
      requestAnimationFrame(() => window.dispatchEvent(new Event('resize')))
    }
  }
}

const focusInitial = async () => {
  await nextTick()

  if (props.initialFocus) {
    const el = modalRef.value?.querySelector(props.initialFocus)
    if (el && typeof el.focus === 'function') {
      el.focus()
      return
    }
  }

  // O fechar não leva o foco inicial: abrir um diálogo com o foco no X convida o Enter a
  // fechar o que acabou de abrir. Sem campo, o foco vai para o primeiro botão do rodapé
  // (numa confirmação, o Cancelar, que é o lado seguro). Controle desabilitado não recebe
  // foco: escolhê-lo deixava o foco no <body>, fora do modal (o "Executar tudo" do
  // Roqueman sem requisições).
  const firstFocusable = modalRef.value?.querySelector(
    [
      'input:not([disabled]):not([type="hidden"])',
      'textarea:not([disabled])',
      'select:not([disabled])',
      'button:not([disabled]):not(.ros-modal__action-btn--close)',
      '[tabindex]:not([tabindex="-1"])',
    ].join(', '),
  )
  if (firstFocusable && typeof firstFocusable.focus === 'function') {
    firstFocusable.focus()
    return
  }

  modalRef.value?.focus()
}

const requestClose = () => {
  emit('update:modelValue', false)
  emit('close')
}

// O Esc é um listener do próprio modal na janela, ligado ao abrir (`aoAbrir`) e desligado ao
// fechar (`soltar`), como já era antes do kit: a migração não o mexeu. Ele não passou para o
// useShortcuts porque aquele escuta desde a montagem, e todo modal do sistema nasce montado e
// fechado. Este listener não trata o empilhamento: com dois modais abertos, cada um escuta e
// nenhum olha se a tecla já foi tratada, então um Esc fecha os dois.
const onKeyDown = (event) => {
  if (!props.modelValue) return
  if (!props.closeOnEsc) return
  if (event.key !== 'Escape') return

  event.preventDefault()
  requestClose()
}

const handleBackdropMouseDown = () => {
  backdropMouseDown = true
}

const handleBackdropClick = () => {
  if (!backdropMouseDown) return
  backdropMouseDown = false

  if (!effectiveCloseOnBackdrop.value) return
  requestClose()
}

// Abrir e fechar moram em funções porque o modal também NASCE aberto: o diálogo global de
// acesso a container e o de progresso são montados com `v-if` e `:model-value="true"`, e um
// `watch` não dispara no valor inicial. Sem isso, o modal que nascia aberto ficava sem Esc,
// sem foco e sem travar o fundo, e no desmonte destravava o fundo de OUTRO modal aberto
// (o contador descia sem ter subido). `travado` guarda o que foi feito, para desfazer só isso.
let travado = false

// A segunda tentativa de foco (ver `aoAbrir`): a espera do sistema, que morre com o modal.
const refocar = useDebounced(() => {
  const a = document.activeElement
  const lost =
    !a ||
    a === document.body ||
    (!modalRef.value?.contains(a) && !a.closest('.ros-modal, .ros-sheet--open'))
  if (props.modelValue && lost) focusInitial()
}, 450)

const aoAbrir = async () => {
  lastActiveElement = document.activeElement
  if (!travado) updateBodyLock(true)
  travado = true
  window.addEventListener('keydown', onKeyDown)
  observarCorpo()
  await focusInitial()
  // Aberto a partir de um item de q-menu (o ⋮ → Renomear do Criar App), o foco sai do
  // campo logo depois: o q-menu, ao fechar, devolve o foco ao ⋮ que o abriu. No celular é
  // pior, o ⋮ mora numa sheet que desmonta e o foco cai no <body>; o teclado não abria
  // (22/09/2026). Uma segunda tentativa, só se o foco foi parar fora do modal E fora de
  // outra camada aberta por cima (um modal empilhado leva o foco de propósito).
  refocar()
  emit('opened')
}

const soltar = () => {
  refocar.cancelar()
  pararDeObservar()
  window.removeEventListener('keydown', onKeyDown)
  if (travado) updateBodyLock(false)
  travado = false
}

const aoFechar = () => {
  soltar()
  if (lastActiveElement && typeof lastActiveElement.focus === 'function') {
    lastActiveElement.focus()
  }
  emit('closed')
}

watch(
  () => props.modelValue,
  (open) => (open ? aoAbrir() : aoFechar()),
)

onMounted(() => {
  if (props.modelValue) aoAbrir()
})

// O global sai de cena pelo `v-if`, não pelo `modelValue`: o foco que estava dentro dele
// volta para quem o tinha, em vez de cair no <body>.
onBeforeUnmount(() => {
  const devolver = travado && !!modalRef.value?.contains(document.activeElement)
  soltar()
  if (devolver && lastActiveElement?.isConnected && typeof lastActiveElement.focus === 'function') {
    lastActiveElement.focus()
  }
})
</script>
