<template>
  <button
    :type="type"
    class="ros-icon-btn"
    :class="classes"
    :disabled="disabled"
    :aria-label="label"
    :title="tooltip && disabled ? label : undefined"
    :aria-pressed="toggle ? String(active) : undefined"
  >
    <q-icon :name="icon" :size="tamanhoDoIcone" />
    <ROSTooltip v-if="tooltip && !disabled" :text="label" :shortcut="shortcut" />
    <slot />
  </button>
</template>

<script setup>
// O botão de ícone do sistema (Goal 63). Três tamanhos (28, 32, 36) no lugar dos dez
// que o código tinha, e o `label` é obrigatório: um ícone sem nome é um botão que o
// leitor de tela anuncia como "botão" e que ninguém sabe o que faz. No toque, a área
// de clique cresce até 44px por um pseudo-elemento, sem mexer no desenho
// (`src/css/roqueos/botoes.scss`).
//
// A dica (Goal 66) é a do sistema, com o atalho ao lado (`shortcut`), e não o `title`
// nativo, que cada sistema operacional desenha de um jeito. Botão desabilitado não recebe
// evento de mouse e a dica do Quasar não abriria: aí volta o `title`, que o navegador
// mostra mesmo assim, para dizer por que está travado. O slot recebe o que se pendura no
// botão (um `q-menu`).
import { computed } from 'vue'
import ROSTooltip from './ROSTooltip.vue'

const props = defineProps({
  icon: { type: String, required: true },
  label: { type: String, required: true },
  size: { type: [Number, String], default: 32, validator: (v) => [28, 32, 36].includes(Number(v)) },
  // `plain` (transparente até o hover) ou `tonal` (com fundo).
  variant: { type: String, default: 'plain', validator: (v) => ['plain', 'tonal'].includes(v) },
  square: { type: Boolean, default: false },
  active: { type: Boolean, default: false },
  // Liga e desliga (negrito, quebra de linha, seguir o log): anuncia `aria-pressed`.
  toggle: { type: Boolean, default: false },
  danger: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  // A dica repete o rótulo para quem usa mouse.
  tooltip: { type: Boolean, default: true },
  shortcut: { type: String, default: '' },
  type: { type: String, default: 'button' },
})

const classes = computed(() => [
  Number(props.size) !== 32 && `ros-icon-btn--${props.size}`,
  {
    'ros-icon-btn--tonal': props.variant === 'tonal',
    'ros-icon-btn--quadrado': props.square,
    'ros-icon-btn--ativo': props.active,
    'ros-icon-btn--perigo': props.danger,
  },
])

const tamanhoDoIcone = computed(() => ({ 28: '16px', 32: '18px', 36: '20px' })[Number(props.size)])
</script>
