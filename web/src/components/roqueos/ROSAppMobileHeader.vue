<template>
  <div class="ros-app-mobile-header">
    <ROSIconButton
      icon="menu"
      :label="t('common.menu')"
      :size="36"
      :tooltip="false"
      class="ros-app-mobile-header__btn"
      @click="$emit('open')"
    />

    <span class="ros-app-mobile-header__title">{{ title }}</span>

    <!-- Right slot for an optional action (e.g. refresh). Falls back to a
         spacer the same width as the menu button so the title stays centred. -->
    <div class="ros-app-mobile-header__action">
      <slot name="action">
        <span class="ros-app-mobile-header__spacer" aria-hidden="true" />
      </slot>
    </div>
  </div>
</template>

<script setup>
// Canonical mobile header band — the fixed top strip with a hamburger that
// opens the app's ROSDrawer. Replaces the ~10 per-app inline reimplementations
// (MapsMobileHeader, GoogleMobileHeader) and the divergent ones that baked a
// refresh button into the bar (Admin/ServerAdmin → pass it via #action).
import { useI18n } from 'vue-i18n'
import ROSIconButton from './ROSIconButton.vue'

defineProps({
  title: { type: String, default: '' },
})

defineEmits(['open'])

const { t } = useI18n()
</script>

<style lang="scss" scoped>
@import 'src/css/roqueos/tokens.scss';

.ros-app-mobile-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: $ros-surface-0;
  border-bottom: 1px solid $ros-border-muted;
  flex-shrink: 0;

  &__title {
    flex: 1;
    min-width: 0;
    text-align: center;
    font-size: var(--ros-text-md);
    font-weight: 600;
    color: $ros-text;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  // Mirrors the menu button width (the 36px ROSIconButton) so the title is optically
  // centred.
  &__action {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    min-width: 36px;
    flex-shrink: 0;
  }

  &__spacer {
    width: 36px;
    height: 36px;
  }

  // No toque o menu, o espaçador e a faixa da ação têm 44 (o menu de 36 reprovava a régua
  // da QA no celular: o título em volta pegava o dedo a 21px do centro). Os três juntos
  // mantêm o título no centro óptico.
  @media (pointer: coarse) {
    &__btn.ros-icon-btn {
      width: 44px;
      height: 44px;
    }

    &__action {
      min-width: 44px;
    }

    &__spacer {
      width: 44px;
      height: 44px;
    }
  }

  // The action slot's own button matches the menu button's hit area.
  :deep(.ros-app-mobile-header__action-btn) {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border: none;
    border-radius: var(--ros-radius-sm);
    background: transparent;
    color: $ros-text;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    transition: background var(--ros-transition-fast);

    &:hover {
      background: $ros-hover-bg;
    }
    &:active {
      transform: scale(0.94);
    }

    // No toque, 44 (com 40 a régua da QA reprovava o atualizar da Administração do
    // servidor: o cabeçalho em volta pegava o dedo). Goal 70.
    @media (pointer: coarse) {
      width: 44px;
      height: 44px;
    }
  }
}
</style>
