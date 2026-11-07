<template>
  <button
    :type="type"
    class="ros-btn"
    :class="classes"
    :disabled="disabled || loading"
    :aria-busy="loading ? 'true' : undefined"
  >
    <ROSSpinner v-if="loading" size="sm" herda aria-hidden="true" class="ros-btn__icone" />
    <q-icon v-else-if="icon" :name="icon" :size="tamanhoDoIcone" class="ros-btn__icone" />
    <span v-if="$slots.default || label" class="ros-btn__rotulo">
      <slot>{{ label }}</slot>
    </span>
    <q-icon v-if="iconRight" :name="iconRight" :size="tamanhoDoIcone" class="ros-btn__icone" />
  </button>
</template>

<script setup>
// O botão do sistema (Goal 63). Antes dele, 34 classes de botão escritas à mão nos
// apps, com alturas de 28 a 48px e seis jeitos de pintar o "primário". O desenho
// mora em `src/css/roqueos/botoes.scss`; este componente só escolhe as classes.
//
// Variantes: `tonal` (padrão, ação comum), `primary` (a ação principal da tela,
// clara com texto escuro), `ghost` (terciária), `danger`, `warning` e `accent`
// (tinta do app, para quando a cor do app precisa aparecer no botão). Carregando, quem avisa
// é o `aria-busy` do botão: o anel fica fora da árvore de acessibilidade, senão o leitor de
// tela leria "Carregando" dentro do nome do botão.
import { computed } from 'vue'
import ROSSpinner from './ROSSpinner.vue'

const props = defineProps({
  variant: {
    type: String,
    default: 'tonal',
    validator: (v) => ['tonal', 'primary', 'ghost', 'danger', 'warning', 'accent'].includes(v),
  },
  size: { type: String, default: 'md', validator: (v) => ['sm', 'md', 'lg'].includes(v) },
  label: { type: String, default: '' },
  icon: { type: String, default: '' },
  iconRight: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  block: { type: Boolean, default: false },
  type: { type: String, default: 'button' },
})

const classes = computed(() => [
  props.variant !== 'tonal' && `ros-btn--${props.variant}`,
  props.size !== 'md' && `ros-btn--${props.size}`,
  { 'ros-btn--block': props.block, 'ros-btn--carregando': props.loading },
])

const tamanhoDoIcone = computed(() => ({ sm: '16px', md: '18px', lg: '20px' })[props.size])
</script>
