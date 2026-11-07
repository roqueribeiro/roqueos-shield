<template>
  <div class="ros-drawer-section">
    <div v-if="title || actionIcon" class="ros-drawer-section__head">
      <span class="ros-drawer-section__title">{{ title }}</span>
      <ROSIconButton
        v-if="actionIcon"
        :icon="actionIcon"
        :label="actionLabel"
        :size="28"
        class="ros-drawer-section__action"
        @click="$emit('action', $event)"
      />
    </div>
    <div class="ros-drawer-section__items">
      <slot />
    </div>
  </div>
</template>

<script setup>
// Drawer section header (uppercase muted label) + optional trailing action
// button (e.g. "+" to create a playlist). Companion of ROSDrawerItem.
// A ação é o botão de ícone do kit: o `actionLabel` vira o nome e a dica.
import ROSIconButton from './ROSIconButton.vue'

defineProps({
  title: { type: String, default: '' },
  actionIcon: { type: String, default: '' },
  actionLabel: { type: String, default: '' },
})

defineEmits(['action'])
</script>

<style lang="scss" scoped>
@import 'src/css/roqueos/tokens.scss';

.ros-drawer-section {
  margin-bottom: 4px;

  &:last-child {
    margin-bottom: 0;
  }

  &__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 10px 5px;
  }

  &__title {
    font-size: var(--ros-text-xs);
    font-weight: 600;
    color: $ros-text-subtle;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
}
</style>
