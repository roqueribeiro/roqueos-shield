<template>
  <span
    class="ros-badge"
    :class="classes"
    :role="ariaLabel ? 'img' : undefined"
    :aria-label="ariaLabel || undefined"
    :aria-hidden="dot && !ariaLabel ? 'true' : undefined"
  >
    <q-icon v-if="icon && !dot" :name="icon" :size="size === 'sm' ? '11px' : '13px'" />
    <template v-if="!dot">{{ texto }}</template>
  </span>
</template>

<script setup>
// O selo do sistema (Goal 64): estado ("Em uso", "Desativado", "Sistema") e contagem
// ("3", "99+"). Eram 42 classes `__badge` à mão, cada uma com uma altura, uma cor e um
// jeito de pintar o vermelho, várias com texto colorido sobre fundo da mesma cor abaixo
// de 4,5:1. Aqui o tom vira fundo a 16% e texto no tom (o vermelho clareado, porque o
// puro sobre o vidro dá 4,3), e o `solid` é para contagem sobre ícone.
//
// `aria-label` troca o que o leitor de tela diz ("3" vira "3 não lidas") e faz do selo uma
// imagem com nome (ARIA não deixa nomear um `<span>` genérico). `dot` é a bolinha sem
// texto: com `aria-label` ela se anuncia; sem, é decoração e fica fora da árvore.
import { computed } from 'vue'

const props = defineProps({
  label: { type: [String, Number], default: '' },
  tone: {
    type: String,
    default: 'neutral',
    validator: (v) => ['neutral', 'accent', 'success', 'warning', 'danger', 'info'].includes(v),
  },
  // Contagem acima disto vira "99+".
  max: { type: Number, default: 99 },
  dot: { type: Boolean, default: false },
  solid: { type: Boolean, default: false },
  icon: { type: String, default: '' },
  size: { type: String, default: 'md', validator: (v) => ['sm', 'md'].includes(v) },
  ariaLabel: { type: String, default: '' },
})

const texto = computed(() =>
  typeof props.label === 'number' && props.label > props.max ? `${props.max}+` : props.label,
)

const classes = computed(() => [
  `ros-badge--${props.tone}`,
  {
    'ros-badge--solido': props.solid,
    'ros-badge--ponto': props.dot,
    'ros-badge--sm': props.size === 'sm',
  },
])
</script>
