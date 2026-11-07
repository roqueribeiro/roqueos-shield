<template>
  <ROSAppLoader
    :state="loaderState"
    :icon="icon"
    :image="image"
    :accent="accent"
    :title="loaderTitle"
    :subtitle="subtitle"
    :error-message="state === 'loading' ? '' : errorMessage"
    :show-bar="false"
    :show-retry="showRetry"
    @retry="$emit('retry')"
  >
    <!-- Multi-stage progress: each step shows done ✓ / active ⟳ / pending ○. -->
    <ol v-if="state === 'loading'" class="ros-loader-steps">
      <li
        v-for="(s, i) in steps"
        :key="s.key"
        class="ros-loader-steps__item"
        :class="{
          'is-done': i < activeIndex,
          'is-active': i === activeIndex,
          'is-pending': i > activeIndex,
        }"
      >
        <span class="ros-loader-steps__mark">
          <q-icon v-if="i < activeIndex" name="check" size="14px" />
          <ROSSpinner v-else-if="i === activeIndex" size="sm" herda />
          <span v-else class="ros-loader-steps__dot" />
        </span>
        <span class="ros-loader-steps__label">{{ s.label }}</span>
      </li>
    </ol>
  </ROSAppLoader>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import ROSAppLoader from './ROSAppLoader.vue'
import ROSSpinner from './ROSSpinner.vue'

const props = defineProps({
  // 'loading' | 'offline' | 'error'
  state: { type: String, default: 'loading' },
  icon: { type: String, default: 'widgets' },
  image: { type: String, default: '' },
  accent: { type: String, default: '#007aff' },
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  // [{ key, label }] — the ordered stages.
  steps: { type: Array, default: () => [] },
  // The key of the stage currently in progress (when the app drives it).
  currentKey: { type: String, default: '' },
  // For apps that provision in a single opaque call (Cloud Gaming / Windows
  // Apps): walk the steps on a timer so the user sees progress. The last step
  // stays active until the parent leaves the loading state.
  autoAdvance: { type: Boolean, default: false },
  advanceMs: { type: Number, default: 4500 },
  errorMessage: { type: String, default: '' },
  showRetry: { type: Boolean, default: true },
})

defineEmits(['retry'])

// Offline maps to the muted hero, error to the red hero.
const loaderState = computed(() => {
  if (props.state === 'offline') return 'no-server'
  if (props.state === 'error') return 'error'
  return 'loading'
})

const loaderTitle = computed(() => props.title)

// Timer-driven progress for the auto-advance mode.
const autoIndex = ref(0)
let timer = null
const stopAuto = () => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}
const startAuto = () => {
  stopAuto()
  autoIndex.value = 0
  timer = setInterval(() => {
    if (autoIndex.value < props.steps.length - 1) autoIndex.value++
    else stopAuto()
  }, props.advanceMs)
}
watch(
  () => [props.autoAdvance, props.state],
  () => {
    if (props.autoAdvance && props.state === 'loading') startAuto()
    else stopAuto()
  },
  { immediate: true },
)
onUnmounted(stopAuto)

const activeIndex = computed(() => {
  if (props.autoAdvance) return autoIndex.value
  const i = props.steps.findIndex((s) => s.key === props.currentKey)
  return i < 0 ? 0 : i
})
</script>

<style scoped lang="scss">
@import 'src/css/roqueos/tokens.scss';

// Sits inside ROSAppLoader's slot, so it inherits --ros-loader-accent.
.ros-loader-steps {
  list-style: none;
  margin: 4px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  text-align: left;

  &__item {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: var(--ros-text-base);
    transition: color var(--ros-duration-slow) ease;

    &.is-done {
      color: $ros-text;
    }
    &.is-active {
      color: $ros-text;
      font-weight: 600;
    }
    &.is-pending {
      color: $ros-text-subtle;
    }
  }

  &__mark {
    width: 22px;
    height: 22px;
    flex-shrink: 0;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--ros-text-100);
  }
  .is-done &__mark {
    background: var(--ros-loader-accent);
  }
  .is-active &__mark {
    background: rgba(var(--ros-loader-accent-rgb), 0.2);
    color: var(--ros-loader-accent);
  }
  .is-pending &__mark {
    background: $ros-fill-08;
  }

  &__dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: rgba(var(--ros-fill-rgb), 0.3);
  }
}
</style>
