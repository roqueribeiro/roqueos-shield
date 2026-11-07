<template>
  <component
    :is="inline ? 'div' : ROSFormField"
    v-bind="inline ? {} : { label }"
    :class="wrapClass"
  >
    <q-select
      :model-value="modelValue"
      :options="options"
      behavior="menu"
      dense
      outlined
      dark
      emit-value
      map-options
      :disable="disabled"
      :popup-content-class="computedPopupContentClass"
      :class="computedClass"
      v-bind="attrsDoSelect"
      @update:model-value="(val) => emit('update:modelValue', val)"
    />
  </component>
</template>

<script setup>
import { computed, useAttrs } from 'vue'
import ROSFormField from './ROSFormField.vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  modelValue: {
    type: [String, Number, Boolean, Object, Array],
    default: null,
  },
  options: {
    type: Array,
    default: () => [],
  },
  label: {
    type: String,
    default: '',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  compact: {
    type: Boolean,
    default: false,
  },
  // `inline`: o seletor sozinho, sem o rótulo e sem a margem de campo de formulário,
  // para barra de ferramentas e filtro (Roquebase, Logs de API, Detalhe do container).
  // Antes disso, quem precisava de um seletor numa barra escrevia <select> nativo, que
  // abre o popup do sistema operacional, branco no tema escuro. O comentário mora aqui e
  // não no template: um comentário na raiz do template vira um segundo nó em dev.
  inline: {
    type: Boolean,
    default: false,
  },
  popupContentClass: {
    type: String,
    default: 'ros-qselect-popup ros-scrollbar-dark',
  },
})

const emit = defineEmits(['update:modelValue'])

const attrs = useAttrs()

// A classe de quem chama já entra por `computedClass` (ou pela caixa, no `inline`);
// passada de novo pelo v-bind, ela caía duas vezes no mesmo elemento.
const attrsDoSelect = computed(() =>
  Object.fromEntries(Object.entries(attrs).filter(([k]) => k !== 'class')),
)

const computedClass = computed(() => {
  return [
    'ros-qselect',
    { 'ros-qselect--compact': props.compact || props.inline },
    props.inline ? null : attrs.class,
  ]
})

// No `inline` a classe de quem chama vai na caixa de fora, que é quem ocupa o lugar
// na barra; no campo de formulário ela continua no q-select, como sempre foi.
const wrapClass = computed(() => (props.inline ? attrs.class : null))

const computedPopupContentClass = computed(() => {
  return [props.popupContentClass, attrs['popup-content-class'], attrs.popupContentClass]
    .filter(Boolean)
    .join(' ')
})
</script>
