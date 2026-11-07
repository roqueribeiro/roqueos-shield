<template>
  <q-dialog
    :model-value="modelValue"
    position="left"
    full-height
    transition-show="slide-right"
    transition-hide="slide-left"
    class="ros-drawer-dialog"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div
      ref="drawerRef"
      class="ros-drawer"
      :class="{ 'ros-drawer--dragging': dragging }"
      :style="drawerStyle"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
    >
      <!-- Header: a custom #header slot wins (escape hatch); otherwise the
           built-in branded header (icon/image + title + auto close) renders
           when any of title/icon/image is provided. -->
      <div v-if="$slots.header" class="ros-drawer__header">
        <slot name="header" />
      </div>
      <div v-else-if="hasBuiltinHeader" class="ros-drawer__header ros-drawer__header--builtin">
        <span v-if="image || icon" class="ros-drawer__brand" aria-hidden="true">
          <img v-if="image" :src="image" :alt="title || ''" class="ros-drawer__brand-img" />
          <q-icon v-else :name="icon" size="22px" />
        </span>
        <span class="ros-drawer__title">{{ title }}</span>
        <ROSIconButton
          v-if="!hideClose"
          icon="close"
          :label="t('common.close')"
          square
          class="ros-drawer__close"
          @click="close"
        />
      </div>

      <!-- Content -->
      <div class="ros-drawer__content ros-scrollbar-hidden">
        <!-- Declarative convenience: pass :sections to render the whole nav
             from data (uses the same primitives). Rich drawers use the slot. -->
        <template v-if="!$slots.default && sections.length">
          <ROSDrawerSection
            v-for="(section, si) in sections"
            :key="section.id || si"
            :title="section.title"
            :action-icon="section.action?.icon"
            :action-label="section.action?.label"
            @action="$emit('section-action', section)"
          >
            <ROSDrawerItem
              v-for="item in section.items"
              :key="item.id"
              :icon="item.icon"
              :image="item.image"
              :label="item.label"
              :active="item.active"
              :count="item.count ?? null"
              :badge="item.badge ?? null"
              :loading="item.loading"
              :variant="item.variant || 'default'"
              :disconnected="item.disconnected"
              @click="$emit('item-click', item)"
            />
          </ROSDrawerSection>
        </template>
        <slot v-else />
      </div>

      <!-- Footer -->
      <div
        v-if="$slots.footer"
        class="ros-drawer__footer"
        :class="{ 'ros-drawer__footer--flush': flushFooter }"
      >
        <slot name="footer" />
      </div>
    </div>
  </q-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolveAccent } from 'src/composables/useAppAccent'
import ROSDrawerSection from './ROSDrawerSection.vue'
import ROSDrawerItem from './ROSDrawerItem.vue'
import ROSIconButton from './ROSIconButton.vue'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  // Built-in header (optional — pass nothing to keep a headerless drawer or
  // use the #header slot for a fully custom one).
  title: { type: String, default: '' },
  icon: { type: String, default: '' },
  image: { type: String, default: '' },
  // App accent (hex) — drives the active-item bar/colour of nested
  // ROSDrawerItem via CSS vars. Sanitized (near-white/black → blue).
  accent: { type: String, default: '#007aff' },
  hideClose: { type: Boolean, default: false },
  // Removes the footer padding so a flush bar (e.g. a mini-player) can fill it.
  // The bar is responsible for its own safe-area-bottom inset.
  flushFooter: { type: Boolean, default: false },
  // Swipe-left-to-close on touch devices (iOS-style). On by default.
  swipeClose: { type: Boolean, default: true },
  // Declarative convenience: [{ id?, title?, action?: { icon, label },
  // items: [{ id, icon, image, label, active, count, badge, loading,
  // variant, disconnected }] }]. Rendered only when no default slot is given.
  sections: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'item-click', 'section-action'])

const { t } = useI18n()

const hasBuiltinHeader = computed(() => !!(props.title || props.icon || props.image))

const accentStyle = computed(() => {
  const a = resolveAccent(props.accent)
  return { '--ros-drawer-accent': a.hex, '--ros-drawer-accent-rgb': a.rgb }
})

const close = () => emit('update:modelValue', false)

// ---------------------------------------------------------------------------
// Swipe-to-close (touch/pen only, axis-locked so it never steals the vertical
// list scroll). Drag the panel left; release past 1/3 width → it slides out
// and closes, otherwise it snaps back.
// ---------------------------------------------------------------------------
const drawerRef = ref(null)
const dragX = ref(0)
const dragging = ref(false)
const settling = ref(false)
let startX = 0
let startY = 0
let decided = null // null = undecided, true = horizontal-close, false = ignore
let width = 280

const onPointerDown = (e) => {
  if (!props.swipeClose || e.pointerType === 'mouse') return
  startX = e.clientX
  startY = e.clientY
  decided = null
  dragging.value = false
  settling.value = false
}

const onPointerMove = (e) => {
  if (!props.swipeClose || decided === false) return
  const dx = e.clientX - startX
  const dy = e.clientY - startY
  if (decided === null) {
    if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return
    // Engage only on a clearly horizontal, leftward gesture.
    if (Math.abs(dx) > Math.abs(dy) && dx < 0) {
      decided = true
      dragging.value = true
      width = drawerRef.value?.offsetWidth || 280
      try {
        drawerRef.value?.setPointerCapture(e.pointerId)
      } catch {
        // setPointerCapture can throw if the pointer is already released
      }
    } else {
      decided = false
      return
    }
  }
  if (decided === true) {
    dragX.value = Math.max(dx, -width) // leftward only
  }
}

const onPointerUp = () => {
  if (decided === true) {
    if (-dragX.value > width * 0.33) {
      // Past threshold → slide fully out, then close the dialog.
      settling.value = true
      dragX.value = -width
      setTimeout(() => {
        close()
        dragX.value = 0
        settling.value = false
      }, 200)
    } else {
      // Snap back.
      settling.value = true
      dragX.value = 0
      setTimeout(() => {
        settling.value = false
      }, 220)
    }
  }
  dragging.value = false
  decided = null
}

const drawerStyle = computed(() => ({
  ...accentStyle.value,
  transform: dragX.value ? `translateX(${dragX.value}px)` : '',
  transition: settling.value ? 'transform 0.2s ease' : 'none',
}))
</script>

<style lang="scss" scoped>
@import 'src/css/roqueos/tokens.scss';

.ros-drawer {
  --ros-drawer-accent: #{$ros-accent};
  --ros-drawer-accent-rgb: 0, 122, 255;

  width: 280px;
  max-width: 85vw;
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  // Dark frosted glass tuned for legibility over wallpapers/coloured apps
  // (the generic liquid-glass tint is too transparent for a text panel).
  background: var(--ros-drawer-bg-1);
  backdrop-filter: blur(var(--ros-blur-xl)) saturate(180%);
  -webkit-backdrop-filter: blur(var(--ros-blur-xl)) saturate(180%);
  // Thin right-edge highlight reads as glass thickness.
  box-shadow:
    inset -1px 0 0 var(--ros-drawer-shadow-1),
    8px 0 32px var(--ros-drawer-shadow-2);
  // Keep vertical list scroll native; we drive the horizontal swipe ourselves.
  touch-action: pan-y;

  &--dragging {
    cursor: grabbing;
  }

  &__header {
    display: flex;
    align-items: center;
    gap: 10px;
    // The drawer PANEL is already inset below the notch (the q-dialog__inner
    // gets the safe-area inset — see the :deep rule below), so the header uses
    // plain padding. The title sits right at the top of the panel, with no
    // empty notch strip inside the glass.
    padding: 12px 12px 10px;
    border-bottom: 1px solid $ros-border-subtle;
    flex-shrink: 0;
    font-size: 15px;
    font-weight: 600;
    color: $ros-text;

    // Slotted headers often drop in an <h3>; normalize it to a compact title.
    :deep(h3) {
      margin: 0;
      font-size: 15px;
      font-weight: 600;
      line-height: 1.2;
    }
  }

  &__brand {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    flex-shrink: 0;
    border-radius: var(--ros-radius-sm);
    color: var(--ros-drawer-accent);
    background: rgba(var(--ros-drawer-accent-rgb), 0.16);
  }

  &__brand-img {
    width: 20px;
    height: 20px;
    object-fit: contain;
  }

  &__title {
    flex: 1;
    min-width: 0;
    font-size: 15px;
    font-weight: 600;
    color: $ros-text;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  &__content {
    flex: 1;
    overflow-y: auto;
    padding: 8px;

    // Premium entrance — sections fade up in a gentle cascade.
    > * {
      animation: ros-drawer-rise 0.4s cubic-bezier(0.22, 1, 0.36, 1) both;
    }
    > *:nth-child(2) {
      animation-delay: 0.05s;
    }
    > *:nth-child(3) {
      animation-delay: 0.1s;
    }
    > *:nth-child(4) {
      animation-delay: 0.15s;
    }
    > *:nth-child(5) {
      animation-delay: 0.2s;
    }
  }

  &__footer {
    // Panel is already inset above the home indicator (q-dialog__inner), so
    // plain padding — the last item sits right at the panel's bottom edge.
    padding: 16px;
    border-top: 1px solid $ros-border-subtle;
    flex-shrink: 0;

    // Flush bar (e.g. mini-player) — no padding; the bar owns its safe area.
    &--flush {
      padding: 0;
    }
  }

  // Low-end mode — opaque, no blur, no entrance.
  html[data-low-end='1'] & {
    background: var(--ros-drawer-bg-2);
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
    box-shadow: 4px 0 16px var(--ros-shadow-40);

    .ros-drawer__content > * {
      animation: none;
    }
  }
}

@keyframes ros-drawer-rise {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .ros-drawer__content > * {
    animation: none;
  }
}

// Dialog wrapper styles
:deep(.ros-drawer-dialog) {
  .q-dialog__backdrop {
    background: var(--ros-scrim-50);
  }

  // Inset the whole drawer PANEL inside the device safe area, so the glass is
  // a clean panel from just below the status bar to just above the home
  // indicator — no empty notch/home-indicator strip *inside* the drawer. The
  // .ros-drawer (height:100%) fills the inner's content box, so it stays a
  // full-height panel (footer still pins to the bottom) but starts/ends within
  // the safe area. Header/footer then use plain padding (title at the top).
  // canonical safe-area expr: var set by capacitor-safe-area.js, env() for PWA.
  .q-dialog__inner {
    box-sizing: border-box;
    padding-top: var(--safe-area-inset-top, env(safe-area-inset-top, 0px));
    padding-bottom: var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px));
  }
}
</style>
