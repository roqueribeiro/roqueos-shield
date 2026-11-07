<template>
  <Teleport to="body">
    <div
      v-if="rendered"
      ref="rootRef"
      class="ros-sheet"
      :class="{ 'ros-sheet--open': shown, 'ros-sheet--elevated': elevated }"
      :style="accentStyle"
      tabindex="-1"
      @keydown="onKeydown"
    >
      <div class="ros-sheet__backdrop" @click="onBackdrop" />

      <div ref="panelRef" class="ros-sheet__panel" :style="panelStyle">
        <!-- Drag handle (drag down to close) -->
        <div class="ros-sheet__handle" @pointerdown="onDragStart">
          <span class="ros-sheet__grip" aria-hidden="true" />
        </div>

        <!-- Header (props-driven; #header slot is the escape hatch) -->
        <div v-if="$slots.header" class="ros-sheet__head">
          <slot name="header" />
        </div>
        <div v-else-if="hasBuiltinHeader" class="ros-sheet__head">
          <span v-if="icon || image" class="ros-sheet__icon" aria-hidden="true">
            <img v-if="image" :src="image" :alt="title || ''" class="ros-sheet__icon-img" />
            <q-icon v-else :name="icon" size="20px" />
          </span>
          <div class="ros-sheet__head-text">
            <span class="ros-sheet__title">{{ title }}</span>
            <span v-if="subtitle" class="ros-sheet__subtitle">{{ subtitle }}</span>
          </div>
          <slot name="actions" />
          <ROSIconButton
            v-if="!hideClose"
            icon="close"
            :label="t('common.close')"
            :size="36"
            variant="tonal"
            class="ros-sheet__close"
            @click="close"
          />
        </div>

        <!-- Scrollable body (hidden scrollbar — iOS-sheet style, canonical
             `.ros-scrollbar-hidden` shared with modal content + drawer body) -->
        <div class="ros-sheet__body ros-scrollbar-hidden">
          <slot />
        </div>

        <!-- Sticky footer (optional action bar) -->
        <div v-if="$slots.footer" class="ros-sheet__footer">
          <slot name="footer" />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolveAccent } from 'src/composables/useAppAccent'
import { useKeyboardInset } from 'src/composables/useKeyboardInset'
import ROSIconButton from './ROSIconButton.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // Built-in header (optional; use the #header slot for a fully custom one).
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  icon: { type: String, default: '' },
  image: { type: String, default: '' },
  // App/feature accent (hex) — drives the radial glow, top border + icon tint.
  // Sanitized (near-white/black → blue) via useAppAccent.
  accent: { type: String, default: '#007aff' },
  hideClose: { type: Boolean, default: false },
  closeOnBackdrop: { type: Boolean, default: true },
  // Panel max-height (mobile). Desktop caps a touch lower for the float.
  maxHeight: { type: String, default: '92%' },
  // Desktop floating-sheet width.
  desktopWidth: { type: String, default: '560px' },
  // Raise the sheet ABOVE the modal tier (ROSModal = 9999) so a sheet opened
  // FROM a modal (e.g. the AI model picker inside the Chat "edit agent" modal)
  // sits on top and stays interactive. Its own dropdowns (`.ros-qselect-popup`
  // = 10001) still render above it. Leave off for sheets that host a nested
  // ROSModal (which must stay on top of the sheet).
  elevated: { type: Boolean, default: false },
  // Pixels of screen the panel must leave free at the bottom, for a docked
  // virtual keyboard. The keyboard reports its own height, so the panel rides
  // above it the way it would above a native keyboard.
  bottomOffset: { type: Number, default: 0 },
})

const emit = defineEmits(['update:modelValue', 'closed', 'opened'])

const { t } = useI18n()

const hasBuiltinHeader = computed(() => !!(props.title || props.icon || props.image))

const accentStyle = computed(() => {
  const a = resolveAccent(props.accent)
  return {
    '--ros-sheet-accent': a.hex,
    '--ros-sheet-accent-rgb': a.rgb,
    '--ros-sheet-max-h': props.maxHeight,
    '--ros-sheet-desktop-w': props.desktopWidth,
  }
})

const rootRef = ref(null)
const panelRef = ref(null)

// Two-phase open: `rendered` mounts the overlay, `shown` toggles the CSS that
// animates the backdrop + panel slide. Keeps the drag transform from fighting
// a Vue <transition>.
const rendered = ref(false)
const shown = ref(false)
let closeTimer = null

const close = () => emit('update:modelValue', false)
const onBackdrop = () => {
  if (props.closeOnBackdrop) close()
}

// ---- drag-to-close ------------------------------------------------------
const dragY = ref(0)
const snapping = ref(false)
const CLOSE_THRESHOLD = 110
let startY = 0
let dragging = false

// A sheet is pinned to the bottom of the LAYOUT viewport, which the OS keyboard
// never shrinks, so a sheet with a text field kept its footer (and often the
// field itself) behind the keyboard. `bottomOffset` already existed for the
// in-house keyboard; the OS one now feeds the same lift. Whichever is taller
// wins, since only one of them is ever up at a time.
const { keyboardInset } = useKeyboardInset()
const effectiveBottomOffset = computed(() => Math.max(props.bottomOffset, keyboardInset.value))

const panelStyle = computed(() => {
  // A docked keyboard owns the bottom of the screen (and its safe area), so the
  // panel sits on top of it instead of reserving the inset a second time.
  const offset = effectiveBottomOffset.value
  const room = offset > 0 ? { marginBottom: `${offset}px` } : {}
  const safe = offset > 0 ? { '--ros-sheet-bottom-safe': '0px' } : {}
  if (dragY.value > 0 || snapping.value) {
    return {
      ...room,
      ...safe,
      transform: `translateY(${dragY.value}px)`,
      transition: snapping.value ? 'transform 0.26s var(--ros-ease-default, ease)' : 'none',
    }
  }
  return { ...room, ...safe }
})

const onDragMove = (e) => {
  if (!dragging) return
  dragY.value = Math.max(0, e.clientY - startY)
}
const onDragEnd = () => {
  if (!dragging) return
  dragging = false
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', onDragEnd)
  if (dragY.value > CLOSE_THRESHOLD) {
    dragY.value = 0 // clear inline transform so the close animation runs
    close()
  } else {
    snapping.value = true
    dragY.value = 0
    setTimeout(() => {
      snapping.value = false
    }, 280)
  }
}
const onDragStart = (e) => {
  dragging = true
  startY = e.clientY
  snapping.value = false
  e.currentTarget.setPointerCapture?.(e.pointerId)
  window.addEventListener('pointermove', onDragMove)
  window.addEventListener('pointerup', onDragEnd)
}

// ---- open/close ---------------------------------------------------------
const doOpen = async () => {
  if (closeTimer) {
    clearTimeout(closeTimer)
    closeTimer = null
  }
  rendered.value = true
  await nextTick()
  requestAnimationFrame(() => {
    shown.value = true
  })
  await nextTick()
  rootRef.value?.focus?.()
  emit('opened')
}

const doClose = () => {
  shown.value = false
  closeTimer = setTimeout(() => {
    rendered.value = false
    emit('closed')
  }, 300)
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) doOpen()
    else doClose()
  },
  { immediate: true },
)

const onKeydown = (e) => {
  if (e.key === 'Escape') {
    close()
    e.preventDefault()
  }
}

onBeforeUnmount(() => {
  if (closeTimer) clearTimeout(closeTimer)
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', onDragEnd)
})
</script>

<style scoped lang="scss">
@import 'src/css/roqueos/tokens.scss';

.ros-sheet {
  // Cores de identidade deste app. Ficam aqui, e não em `tokens-root.scss`,
  // porque são do app e não do sistema — mas ficam como custom property
  // para que um tema consiga alcançá-las.
  --ros-sheet-bg-1: rgba(24, 22, 28, 0.98);
  --ros-sheet-bg-2: rgba(24, 22, 28, 0.99);
}

// Canonical iOS-style bottom sheet — extracted from MusicPracticeSheet so the
// exact "slides up from the bottom" visual is reusable system-wide. Mobile: a
// bottom sheet (drag handle, rounded top, partial height). Desktop: a centered
// floating sheet. Accent is injected per-use via CSS vars (useAppAccent).
.ros-sheet {
  --ros-sheet-accent: #{$ros-accent};
  --ros-sheet-accent-rgb: 0, 122, 255;
  --ros-sheet-max-h: 92%;
  --ros-sheet-desktop-w: 560px;

  position: fixed;
  inset: 0;
  z-index: 7000; // above windows/dock, below nothing app-critical
  display: flex;

  // Opened from a modal (ROSModal = 9999): sit above it. Below the select/menu
  // popup tier (10001) so this sheet's own dropdowns still open on top.
  &--elevated {
    z-index: 10000;
  }
  flex-direction: column;
  justify-content: flex-end;
  color: var(--ros-text-100);

  &__backdrop {
    position: absolute;
    inset: 0;
    background: var(--ros-scrim-55);
    opacity: 0;
    transition: opacity var(--ros-duration-slow) var(--ros-ease-default, ease);
    backdrop-filter: blur(var(--ros-blur-xs));
    -webkit-backdrop-filter: blur(var(--ros-blur-xs));
  }

  &__panel {
    position: relative;
    z-index: 1;
    width: 100%;
    max-height: var(--ros-sheet-max-h);
    display: flex;
    flex-direction: column;
    overflow: hidden; // body scrolls, header/footer stay put
    // Bottom safe-area lives on the PANEL (not the body) so it clears WHATEVER
    // is last — the footer when there is one, the body when there isn't. With
    // it on the body only, a footer button sat flush against the home indicator
    // and got clipped (reported on iPhone). 16px base + inset; var-first.
    padding: 0 18px calc(16px + var(--ros-sheet-bottom-safe, env(safe-area-inset-bottom, 0px)));
    border-radius: 22px 22px 0 0;
    background:
      radial-gradient(
        ellipse 90% 50% at 50% 0%,
        rgba(var(--ros-sheet-accent-rgb), 0.14),
        transparent 65%
      ),
      var(--ros-sheet-bg-1);
    border-top: 1px solid rgba(var(--ros-sheet-accent-rgb), 0.25);
    box-shadow: 0 -18px 50px var(--ros-shadow-50);
    // NO backdrop-filter on the panel — the bg is ~opaque, and animating a
    // transform on a backdrop-filtered element janks the slide (recomputes the
    // blur every frame → the "amateur" feel the founder flagged). The backdrop
    // (separate element) keeps its blur.
    transform: translateY(100%);
    // iOS sheet easing — smooth decelerate, no overshoot/bounce.
    transition: transform var(--ros-duration-slower) cubic-bezier(0.32, 0.72, 0, 1);

    // Desktop: centered floating sheet instead of a full-width bottom bar.
    @media (min-width: 768px) {
      width: var(--ros-sheet-desktop-w);
      max-width: 92%;
      margin: 0 auto 18px;
      max-height: 88%;
      border-radius: 22px;
      border: 1px solid rgba(var(--ros-sheet-accent-rgb), 0.22);
    }
  }

  &--open {
    .ros-sheet__backdrop {
      opacity: 1;
    }
    .ros-sheet__panel {
      transform: translateY(0);
    }
  }

  &__handle {
    flex-shrink: 0;
    display: flex;
    justify-content: center;
    padding: 10px 0 6px;
    cursor: grab;
    touch-action: none;

    &:active {
      cursor: grabbing;
    }
  }
  &__grip {
    width: 42px;
    height: 5px;
    border-radius: var(--ros-radius-pill);
    background: rgba(var(--ros-fill-rgb), 0.28);
  }

  &__head {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 4px 0 14px;
    min-width: 0;
  }
  &__icon {
    flex-shrink: 0;
    width: 40px;
    height: 40px;
    border-radius: var(--ros-radius-md);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--ros-sheet-accent);
    background: rgba(var(--ros-sheet-accent-rgb), 0.14);
    box-shadow: inset 0 0 0 1px rgba(var(--ros-sheet-accent-rgb), 0.25);
  }
  &__icon-img {
    width: 22px;
    height: 22px;
    object-fit: contain;
  }
  &__head-text {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  &__title {
    font-size: 15px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  &__subtitle {
    font-size: var(--ros-text-sm);
    color: var(--ros-text-55);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  &__body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    // A sheet is a vertical panel — it must NEVER scroll horizontally. Setting
    // only overflow-y:auto makes the browser compute overflow-x as auto too, so
    // any element a hair too wide spawns a horizontal scrollbar. Pin it hidden.
    overflow-x: hidden;
    -webkit-overflow-scrolling: touch;
    // Bottom safe-area is reserved on the PANEL (see `&__panel`), so the body
    // needs no inset here — the panel padding clears the last body item AND the
    // footer uniformly. Hidden scrollbar via the shared `.ros-scrollbar-hidden`
    // utility (on the element class) — same treatment as modal content + drawer.
  }

  &__footer {
    flex-shrink: 0;
    padding-top: 14px;
    margin-top: 4px;
    // Sheet footer = full-width tap targets. A single action button fills the
    // row; two split evenly. Mobile-first — no cramped left-aligned buttons.
    display: flex;
    gap: 10px;

    > * {
      flex: 1;
    }
  }

  // Low-end mode — drop blur + heavy transitions, keep the slide.
  html[data-low-end='1'] & {
    .ros-sheet__backdrop {
      backdrop-filter: none;
      -webkit-backdrop-filter: none;
    }
    .ros-sheet__panel {
      backdrop-filter: none;
      -webkit-backdrop-filter: none;
      background: var(--ros-sheet-bg-2);
      transition: transform var(--ros-duration-normal) ease;
    }
  }
}

@media (prefers-reduced-motion: reduce) {
  .ros-sheet__panel,
  .ros-sheet__backdrop {
    transition: none;
  }
}
</style>
