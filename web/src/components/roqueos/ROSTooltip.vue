<template>
  <q-tooltip
    class="ros-tooltip"
    :anchor="posicao.anchor"
    :self="posicao.self"
    :offset="posicao.offset"
    :delay="delay"
    :hide-delay="0"
    :max-width="maxWidth"
    transition-show="fade"
    transition-hide="fade"
  >
    <slot>{{ text }}</slot>
    <kbd v-if="shortcut" class="ros-tooltip__atalho">{{ shortcut }}</kbd>
  </q-tooltip>
</template>

<script setup>
// A dica do sistema (Goal 64). Cento e treze `<q-tooltip>` usavam o desenho de fábrica
// do Quasar (cinza chapado, 10px, abaixo do piso de 11 da escala), porque a regra que
// os vestia morava dentro de `.ros-layout` e a dica é teleportada para o `<body>`: a
// regra nunca casou. O desenho agora é global (`kit.scss`), e este componente dá o
// resto: posição por nome, espera antes de aparecer (passar o mouse por cima de uma
// barra não acende seis dicas) e o atalho de teclado ao lado do texto.
//
// A dica repete o nome de um controle, nunca é o único lugar dele: o botão de ícone
// continua com `aria-label` (o ROSIconButton exige), porque no toque a dica não abre.
import { computed } from 'vue'

const props = defineProps({
  text: { type: String, default: '' },
  placement: {
    type: String,
    default: 'bottom',
    validator: (v) => ['top', 'bottom', 'left', 'right'].includes(v),
  },
  delay: { type: Number, default: 400 },
  shortcut: { type: String, default: '' },
  maxWidth: { type: String, default: '280px' },
})

const POSICOES = {
  top: { anchor: 'top middle', self: 'bottom middle', offset: [0, 8] },
  bottom: { anchor: 'bottom middle', self: 'top middle', offset: [0, 8] },
  left: { anchor: 'center left', self: 'center right', offset: [8, 0] },
  right: { anchor: 'center right', self: 'center left', offset: [8, 0] },
}

const posicao = computed(() => POSICOES[props.placement])
</script>
