<template>
  <div
    class="ros-search"
    :class="{ 'ros-search--sm': size === 'sm', 'ros-search--desabilitado': disabled }"
  >
    <q-icon name="search" :size="size === 'sm' ? '16px' : '18px'" class="ros-search__lupa" />
    <input
      ref="campo"
      :value="texto"
      type="search"
      class="ros-search__campo"
      :placeholder="placeholder || $t('common.search')"
      :aria-label="label || placeholder || $t('common.search')"
      :disabled="disabled"
      :autofocus="autofocus"
      autocomplete="off"
      spellcheck="false"
      enterkeyhint="search"
      @input="aoDigitar"
      @keydown.enter="aoConfirmar"
      @keydown.esc="aoEsc"
    />
    <kbd v-if="shortcut && !texto" class="ros-search__atalho" aria-hidden="true">{{
      shortcut
    }}</kbd>
    <ROSIconButton
      v-if="texto"
      icon="close"
      :label="$t('common.clear')"
      :size="28"
      class="ros-search__limpar"
      @click="limpar"
    />
  </div>
</template>

<script setup>
// O campo de busca do sistema (Goal 63). Os apps tinham 23 versões dele, cada uma com
// a lupa num lugar e a maioria sem jeito de limpar. Este tem lupa, "x" que limpa e
// devolve o foco, Esc que limpa (e só deixa o Esc subir, para fechar um modal, quando
// já está vazio), Enter que emite `search`, e `debounce` para quem filtra no servidor.
import { onBeforeUnmount, ref, watch } from 'vue'
import ROSIconButton from './ROSIconButton.vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  // Nome para o leitor de tela; sem ele, vale o placeholder.
  label: { type: String, default: '' },
  // Milissegundos entre a última tecla e o `update:modelValue`. 0 emite a cada tecla.
  debounce: { type: Number, default: 0 },
  // Dica de atalho mostrada no canto quando o campo está vazio ("/", "Ctrl K").
  shortcut: { type: String, default: '' },
  size: { type: String, default: 'md', validator: (v) => ['sm', 'md'].includes(v) },
  disabled: { type: Boolean, default: false },
  autofocus: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'search'])

const campo = ref(null)
const texto = ref(props.modelValue)
let espera = null

watch(
  () => props.modelValue,
  (v) => {
    if (v !== texto.value) texto.value = v
  },
)

const cancelarEspera = () => {
  if (espera) clearTimeout(espera)
  espera = null
}

const publicar = (v) => {
  cancelarEspera()
  emit('update:modelValue', v)
}

const aoDigitar = (e) => {
  texto.value = e.target.value
  if (!props.debounce) return publicar(texto.value)
  cancelarEspera()
  espera = setTimeout(() => publicar(texto.value), props.debounce)
}

const aoConfirmar = () => {
  publicar(texto.value)
  emit('search', texto.value)
}

const limpar = () => {
  texto.value = ''
  publicar('')
  campo.value?.focus()
}

const aoEsc = (e) => {
  if (!texto.value) return
  e.stopPropagation()
  limpar()
}

onBeforeUnmount(cancelarEspera)

defineExpose({ focus: () => campo.value?.focus() })
</script>
