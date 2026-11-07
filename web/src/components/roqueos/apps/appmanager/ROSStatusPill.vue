<template>
  <span class="ros-status-pill" :class="[`ros-status-pill--${tone}`, `ros-status-pill--${size}`]">
    <span v-if="dot" class="ros-status-pill__dot" aria-hidden="true" />
    <q-icon v-else-if="icon" :name="icon" :size="size === 'sm' ? '13px' : '15px'" />
    <span class="ros-status-pill__label">{{ label }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

// Canonical container status/health pill. Maps a Docker state or health string
// to a tone + icon + localized label so every surface (detail header, list,
// info tab) reads identically.
const props = defineProps({
  status: { type: String, default: '' },
  // 'state' → running/exited/… ; 'health' → healthy/unhealthy/starting
  kind: { type: String, default: 'state' },
  size: { type: String, default: 'md' }, // 'sm' | 'md'
  dot: { type: Boolean, default: true }, // show a dot instead of the icon
})

const { t } = useI18n()

const STATE_MAP = {
  running: { tone: 'success', icon: 'play_circle' },
  paused: { tone: 'warn', icon: 'pause_circle' },
  restarting: { tone: 'warn', icon: 'restart_alt' },
  removing: { tone: 'warn', icon: 'hourglass_empty' },
  created: { tone: 'neutral', icon: 'fiber_new' },
  exited: { tone: 'danger', icon: 'stop_circle' },
  dead: { tone: 'danger', icon: 'dangerous' },
}
const HEALTH_MAP = {
  healthy: { tone: 'success', icon: 'favorite' },
  starting: { tone: 'warn', icon: 'hourglass_top' },
  unhealthy: { tone: 'danger', icon: 'heart_broken' },
}

const key = computed(() => String(props.status || '').toLowerCase())
const meta = computed(() => {
  const map = props.kind === 'health' ? HEALTH_MAP : STATE_MAP
  return map[key.value] || { tone: 'neutral', icon: 'help' }
})
const tone = computed(() => meta.value.tone)
const icon = computed(() => meta.value.icon)
const label = computed(() => {
  if (!key.value) return ''
  const i18nKey = `appManager.containerSettings.${props.kind === 'health' ? 'health' : 'state'}.${key.value}`
  const translated = t(i18nKey)
  // vue-i18n returns the key itself when missing — fall back to the raw status.
  return translated === i18nKey ? props.status : translated
})
</script>

<style lang="scss" scoped>
@import 'src/css/roqueos/tokens.scss';

.ros-status-pill {
  // Cores de identidade deste app. Ficam aqui, e não em `tokens-root.scss`,
  // porque são do app e não do sistema — mas ficam como custom property
  // para que um tema consiga alcançá-las.
  --ros-status-pill-fg-1: #4ade80;
  --ros-status-pill-bg-1: rgba(52, 199, 89, 0.14);
  --ros-status-pill-line-1: rgba(52, 199, 89, 0.28);
  --ros-status-pill-fg-2: #fbbf24;
  --ros-status-pill-bg-2: rgba(255, 159, 10, 0.14);
  --ros-status-pill-line-2: rgba(255, 159, 10, 0.28);
  --ros-status-pill-fg-3: #ff6b6b;
  --ros-status-pill-bg-3: rgba(255, 59, 48, 0.14);
  --ros-status-pill-line-3: rgba(255, 59, 48, 0.28);
  --ros-status-pill-bg-4: rgba(52, 199, 89, 0.2);
  --ros-status-pill-bg-5: rgba(255, 159, 10, 0.2);
  --ros-status-pill-bg-6: rgba(255, 59, 48, 0.2);
}

.ros-status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: var(--ros-radius-pill);
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
  border: 1px solid transparent;

  &--md {
    padding: 4px 10px;
    font-size: var(--ros-text-sm);
  }
  &--sm {
    padding: 3px 8px;
    font-size: var(--ros-text-xs);
    gap: 5px;
  }

  &__dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: currentColor;
    flex-shrink: 0;
  }
  &__label {
    overflow: hidden;
    text-overflow: ellipsis;
  }

  // tones — tinted bg + matching text/border, token-aligned with the system.
  &--success {
    color: var(--ros-status-pill-fg-1);
    background: var(--ros-status-pill-bg-1);
    border-color: var(--ros-status-pill-line-1);
  }
  &--warn {
    color: var(--ros-status-pill-fg-2);
    background: var(--ros-status-pill-bg-2);
    border-color: var(--ros-status-pill-line-2);
  }
  &--danger {
    color: var(--ros-status-pill-fg-3);
    background: var(--ros-status-pill-bg-3);
    border-color: var(--ros-status-pill-line-3);
  }
  &--neutral {
    color: var(--ros-text-70);
    background: $ros-fill-08;
    border-color: var(--ros-line-14);
  }
}

html[data-low-end='1'] .ros-status-pill {
  &--success {
    background: var(--ros-status-pill-bg-4);
  }
  &--warn {
    background: var(--ros-status-pill-bg-5);
  }
  &--danger {
    background: var(--ros-status-pill-bg-6);
  }
}
</style>
