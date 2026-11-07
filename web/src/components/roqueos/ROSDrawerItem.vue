<template>
  <button
    class="ros-drawer-item"
    :class="[
      `ros-drawer-item--${variant}`,
      { 'ros-drawer-item--active': active, 'ros-drawer-item--disconnected': disconnected },
    ]"
    @click="$emit('click', $event)"
    @contextmenu="$emit('contextmenu', $event)"
  >
    <span class="ros-drawer-item__icon" aria-hidden="true">
      <img v-if="image" :src="image" :alt="label || ''" class="ros-drawer-item__icon-img" />
      <q-icon v-else :name="icon || 'circle'" size="20px" />
    </span>

    <span class="ros-drawer-item__label">{{ label }}</span>

    <ROSSpinner v-if="loading" size="sm" herda class="ros-drawer-item__spinner" />
    <slot v-else name="trailing">
      <span v-if="count !== null && count !== undefined" class="ros-drawer-item__count">{{
        count
      }}</span>
      <ROSBadge v-else-if="badge !== null && badge !== undefined" :label="badge" size="sm" />
    </slot>
  </button>
</template>

<script setup>
// Canonical drawer navigation row — the single source of the item look that
// used to be copy-pasted across every *MobileDrawer (Finder, Music, PDF…).
// Active state + the accent left-bar derive from `--ros-drawer-accent`, which
// ROSDrawer sets from its `accent` prop — so each app's colour flows in.
// O carregando e o selo do fim são os do kit (ROSSpinner e ROSBadge).
import ROSBadge from './ROSBadge.vue'
import ROSSpinner from './ROSSpinner.vue'

defineProps({
  icon: { type: String, default: '' },
  image: { type: String, default: '' },
  label: { type: String, default: '' },
  active: { type: Boolean, default: false },
  // Trailing count (e.g. playlist track count) or badge (e.g. trash count).
  count: { type: [String, Number], default: null },
  badge: { type: [String, Number], default: null },
  // Shows a spinner instead of the trailing slot (e.g. while navigating).
  loading: { type: Boolean, default: false },
  // 'default' | 'add' (muted "+ add" row) | 'danger'
  variant: { type: String, default: 'default' },
  // Dims the row (e.g. a disconnected cloud service).
  disconnected: { type: Boolean, default: false },
})

defineEmits(['click', 'contextmenu'])
</script>

<style lang="scss" scoped>
@import 'src/css/roqueos/tokens.scss';

.ros-drawer-item {
  position: relative;
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  // 10px padding around a 20px line lands at 40px, under the 44px tap-target
  // bar (rule 35). Content is already centred, so this only grows short rows.
  min-height: 44px;
  border: none;
  background: transparent;
  border-radius: var(--ros-radius-sm);
  color: $ros-text-strong;
  cursor: pointer;
  text-align: left;
  -webkit-tap-highlight-color: transparent;
  transition:
    background var(--ros-duration-fast) ease,
    transform var(--ros-duration-fast) ease;

  &:hover {
    background: $ros-hover-bg;
  }
  &:active {
    transform: scale(0.98);
  }

  &__icon {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    width: 20px;
    height: 20px;
    opacity: 0.8;
  }

  &__icon-img {
    width: 20px;
    height: 20px;
    object-fit: contain;
    border-radius: var(--ros-radius-xs);
  }

  &__label {
    flex: 1;
    min-width: 0;
    font-size: var(--ros-text-base);
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  &__count {
    font-size: var(--ros-text-xs);
    color: $ros-text-subtle;
    flex-shrink: 0;
  }

  &__spinner {
    flex-shrink: 0;
  }

  // Active — accent tint + left bar + accent icon (per-app via CSS var).
  &--active {
    background: rgba(var(--ros-drawer-accent-rgb), 0.2);
    color: var(--ros-text-100);

    .ros-drawer-item__icon {
      opacity: 1;
      color: var(--ros-drawer-accent);
    }

    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 50%;
      transform: translateY(-50%);
      width: 3px;
      height: 60%;
      background: var(--ros-drawer-accent);
      border-radius: 0 var(--ros-radius-pill) var(--ros-radius-pill) 0;
    }

    &:hover {
      background: rgba(var(--ros-drawer-accent-rgb), 0.24);
    }
  }

  // "Add" affordance — muted until hovered.
  &--add {
    color: $ros-text-subtle;

    .ros-drawer-item__icon {
      opacity: 0.6;
    }
    &:hover {
      color: $ros-text;
      .ros-drawer-item__icon {
        opacity: 0.9;
      }
    }
  }

  &--danger {
    color: $ros-danger;
    .ros-drawer-item__icon {
      color: $ros-danger;
    }
  }

  &--disconnected {
    opacity: 0.55;
  }
}
</style>
