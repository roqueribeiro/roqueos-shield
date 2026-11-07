<template>
  <label
    class="ros-checkbox"
    :class="[
      `ros-checkbox--${size}`,
      {
        'ros-checkbox--checked': modelValue === true,
        'ros-checkbox--indeterminate': indeterminate,
        'ros-checkbox--disabled': disabled,
      },
    ]"
    :aria-disabled="disabled || undefined"
  >
    <input
      ref="inputRef"
      type="checkbox"
      class="ros-checkbox__native"
      :checked="modelValue === true"
      :disabled="disabled"
      :aria-label="ariaLabel || undefined"
      @change="onChange"
      @click.stop
    />
    <span class="ros-checkbox__box" aria-hidden="true">
      <q-icon v-if="indeterminate" name="remove" class="ros-checkbox__mark" size="14px" />
      <q-icon v-else-if="modelValue === true" name="check" class="ros-checkbox__mark" size="14px" />
    </span>
    <span v-if="$slots.default" class="ros-checkbox__label">
      <slot />
    </span>
  </label>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  /**
   * Tri-state visual for "select all" headers when only some rows are
   * selected. Renders a `–` mark instead of the check.
   */
  indeterminate: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  ariaLabel: { type: String, default: '' },
  /**
   * `sm` (16×16) for dense tables, `md` (18×18) default, `lg` (22×22) for
   * touch-friendly contexts.
   */
  size: {
    type: String,
    default: 'md',
    validator: (v) => ['sm', 'md', 'lg'].includes(v),
  },
})

const emit = defineEmits(['update:modelValue', 'change'])

const inputRef = ref(null)

// Indeterminate is purely a visual prop; HTMLInputElement requires it set
// imperatively via JS (no HTML attribute exists). Sync whenever it changes.
watch(
  () => props.indeterminate,
  (val) => {
    if (inputRef.value) inputRef.value.indeterminate = !!val
  },
  { immediate: true },
)

const onChange = (event) => {
  if (props.disabled) return
  const next = event.target.checked
  emit('update:modelValue', next)
  emit('change', next)
}
</script>

<style scoped lang="scss">
@import 'src/css/roqueos/tokens.scss';

.ros-checkbox {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
  vertical-align: middle;
  line-height: 1;

  &--disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  &__native {
    // Visually hide but keep the native input accessible to screen readers,
    // keyboard, and form association. The :focus-visible state on the input
    // bubbles to the visible box via :has() — supported across modern browsers.
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    padding: 0;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  &__box {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    background: $ros-surface-0;
    border: 1px solid $ros-border-subtle;
    border-radius: var(--ros-radius-sm, 4px);
    color: transparent;
    transition:
      background var(--ros-duration-fast, var(--ros-duration-fast)) var(--ros-ease-default, ease),
      border-color var(--ros-duration-fast, var(--ros-duration-fast)) var(--ros-ease-default, ease),
      color var(--ros-duration-fast, var(--ros-duration-fast)) var(--ros-ease-default, ease);
  }

  &--sm &__box {
    width: 16px;
    height: 16px;
  }

  &--md &__box {
    width: 18px;
    height: 18px;
  }

  &--lg &__box {
    width: 22px;
    height: 22px;
  }

  &:hover:not(.ros-checkbox--disabled) &__box {
    border-color: rgba(var(--ros-accent-rgb), 0.55);
    background: $ros-surface-1;
  }

  &--checked &__box,
  &--indeterminate &__box {
    background: $ros-accent;
    border-color: $ros-accent;
    color: var(--ros-text-100);
  }

  // Keyboard focus styling — ring around the box.
  &__native:focus-visible + &__box {
    box-shadow: 0 0 0 3px rgba(var(--ros-accent-rgb), 0.35);
  }

  &__mark {
    pointer-events: none;
  }

  &__label {
    color: $ros-text;
    font-size: var(--ros-text-base);
    line-height: 1.2;
  }
}
</style>
