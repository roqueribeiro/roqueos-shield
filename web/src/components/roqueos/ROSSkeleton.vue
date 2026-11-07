<template>
  <div class="ros-skeleton" role="status" :aria-label="label || $t('common.loading')">
    <template v-if="variant === 'item'">
      <div v-for="n in count" :key="n" class="ros-skeleton__item" aria-hidden="true">
        <span class="ros-skeleton__peca ros-skeleton__circulo" />
        <div class="ros-skeleton__textos">
          <span
            class="ros-skeleton__peca ros-skeleton__linha"
            :style="{ width: larguraDa(n, 0) }"
          />
          <span
            class="ros-skeleton__peca ros-skeleton__linha"
            :style="{ width: larguraDa(n, 1) }"
          />
        </div>
      </div>
    </template>
    <template v-else>
      <span
        v-for="n in count"
        :key="n"
        class="ros-skeleton__peca"
        :class="`ros-skeleton__${PECA[variant]}`"
        :style="estiloDa(n)"
        aria-hidden="true"
      />
    </template>
  </div>
</template>

<script setup>
// O esqueleto do sistema (Goal 63): a forma do que vai chegar, no lugar de um
// spinner no meio de uma área vazia. Lista que carrega mostra linhas, grade mostra
// blocos, e a tela não pula quando o dado chega. O brilho para no Modo Economia e em
// quem pediu menos movimento (kit.scss).
const PECA = { line: 'linha', block: 'bloco', circle: 'circulo' }
// As linhas variam de largura para não parecerem uma tabela vazia.
const LARGURAS = ['92%', '76%', '84%', '64%', '88%', '70%']

const props = defineProps({
  // line, block, circle ou item (círculo e duas linhas, a linha de uma lista).
  variant: {
    type: String,
    default: 'line',
    validator: (v) => ['line', 'block', 'circle', 'item'].includes(v),
  },
  count: { type: Number, default: 3 },
  width: { type: String, default: '' },
  height: { type: String, default: '' },
  label: { type: String, default: '' },
})

const larguraDa = (n, deslocamento) => LARGURAS[(n * 2 + deslocamento) % LARGURAS.length]

const estiloDa = (n) => ({
  width: props.width || (props.variant === 'line' ? larguraDa(n, 0) : undefined),
  height: props.height || undefined,
})
</script>
