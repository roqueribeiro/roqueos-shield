<template>
  <div class="ros-toggle-field">
    <div class="ros-toggle-field__content">
      <div class="ros-toggle-field__text">
        <div class="ros-toggle-field__label">{{ label }}</div>
        <div v-if="description" class="ros-toggle-field__description">{{ description }}</div>
      </div>

      <!-- O interruptor leva o rótulo como nome: sem isso o leitor de tela anuncia só
           "interruptor", e o texto ao lado não está ligado a ele. -->
      <q-toggle
        :model-value="modelValue"
        :aria-label="label"
        :color="color"
        :dark="dark"
        :size="size"
        :disable="disabled"
        @update:model-value="(val) => emit('update:modelValue', val)"
      />
    </div>
  </div>
</template>

<script setup>
defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  label: {
    type: String,
    required: true,
  },
  description: {
    type: String,
    default: '',
  },
  color: {
    type: String,
    default: 'primary',
  },
  dark: {
    type: Boolean,
    default: true,
  },
  size: {
    type: String,
    default: 'lg',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue'])
</script>

<style lang="scss" scoped>
@use 'src/css/roqueos/tokens' as *;
@import 'src/css/roqueos/tokens.scss';

.ros-toggle-field {
  &__content {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }

  &__text {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  &__label {
    font-size: var(--ros-text-md);
    color: $ros-text;
    font-weight: 500;
  }

  &__description {
    font-size: var(--ros-text-base);
    color: $ros-text-muted;
    line-height: 1.5;
  }
}
</style>
