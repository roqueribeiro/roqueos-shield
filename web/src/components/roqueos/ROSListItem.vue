<template>
  <component :is="tag" class="ros-list-item" :class="classes">
    <span v-if="icon || $slots.leading" class="ros-list-item__inicio" aria-hidden="true">
      <slot name="leading">
        <q-icon :name="icon" :size="dense ? '18px' : '20px'" />
      </slot>
    </span>
    <button
      v-if="clickable"
      type="button"
      class="ros-list-item__textos ros-list-item__alvo"
      :disabled="disabled"
      :aria-current="active ? 'true' : undefined"
      @click="emit('click', $event)"
    >
      <span class="ros-list-item__titulo">
        <slot>{{ title }}</slot>
      </span>
      <span v-if="subtitle" class="ros-list-item__subtitulo">{{ subtitle }}</span>
    </button>
    <span v-else class="ros-list-item__textos">
      <span class="ros-list-item__titulo">
        <slot>{{ title }}</slot>
      </span>
      <span v-if="subtitle" class="ros-list-item__subtitulo">{{ subtitle }}</span>
    </span>
    <span v-if="meta || $slots.trailing" class="ros-list-item__fim">
      <slot name="trailing">
        <span class="ros-list-item__meta">{{ meta }}</span>
      </slot>
    </span>
  </component>
</template>

<script setup>
// A linha de lista do sistema (Goal 64): ícone, título, subtítulo e, no fim, um
// metadado ou ações. Os apps escreviam a linha clicável de 84 jeitos (`__item`,
// `__row`), metade sem foco de teclado porque era um `<div @click>`.
//
// `clickable`: a linha inteira abre alguma coisa. O alvo é o bloco de texto, um botão
// de verdade, e um pseudo-elemento dele cobre a linha (o mesmo "link esticado" do
// ROSCard). As ações do fim (`#trailing`) ficam por cima, como botões próprios.
// Dentro de `<ul>`, passe `tag="li"`.
import { computed } from 'vue'

const props = defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  icon: { type: String, default: '' },
  meta: { type: String, default: '' },
  clickable: { type: Boolean, default: false },
  active: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  dense: { type: Boolean, default: false },
  tag: { type: String, default: 'div' },
})

const emit = defineEmits(['click'])

const classes = computed(() => ({
  'ros-list-item--clicavel': props.clickable,
  'ros-list-item--ativo': props.active,
  'ros-list-item--desabilitado': props.disabled,
  'ros-list-item--denso': props.dense,
}))
</script>
