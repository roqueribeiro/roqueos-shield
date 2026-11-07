<template>
  <span class="ros-chip" :class="classes">
    <button
      v-if="interativo"
      type="button"
      class="ros-chip__corpo"
      :disabled="disabled"
      :aria-pressed="selecionavel ? String(selected) : undefined"
      @click="clicar"
    >
      <q-icon v-if="icon" :name="icon" :size="tamanhoDoIcone" />
      <span class="ros-chip__rotulo">{{ label }}</span>
    </button>
    <span v-else class="ros-chip__corpo">
      <q-icon v-if="icon" :name="icon" :size="tamanhoDoIcone" />
      <span class="ros-chip__rotulo">{{ label }}</span>
    </span>
    <button
      v-if="removable"
      type="button"
      class="ros-chip__remover"
      :disabled="disabled"
      :aria-label="$t('common.removeNamed', { name: label })"
      :title="$t('common.removeNamed', { name: label })"
      @click.stop="emit('remove')"
    >
      <q-icon name="close" :size="tamanhoDoIcone" />
    </button>
  </span>
</template>

<script setup>
// A etiqueta do sistema (Goal 64): metadado ("GPT-4", "3 ferramentas"), filtro que liga
// e desliga ("Áudio", "Vídeo") e valor pronto que se escolhe ("5 min", "120 bpm"). Os
// apps tinham 76 `__chip` e 26 `__pill`, cada um com uma altura. Três jeitos de usar:
//
// - só `label`: etiqueta parada, um `<span>`.
// - `v-model:selected`: filtro, um botão com `aria-pressed`.
// - `clickable`: ação sem estado (o valor pronto), um botão.
//
// `removable` põe um "x" com nome próprio ("Remover Áudio"). Ele é irmão do corpo e não
// filho, porque botão dentro de botão não é HTML válido e o leitor de tela engole o de
// dentro.
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  icon: { type: String, default: '' },
  // `null` = não é filtro. `true`/`false` = filtro, ligado ou desligado.
  selected: { type: Boolean, default: null },
  clickable: { type: Boolean, default: false },
  removable: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  size: { type: String, default: 'md', validator: (v) => ['sm', 'md'].includes(v) },
})

const emit = defineEmits(['update:selected', 'click', 'remove'])

const selecionavel = computed(() => props.selected !== null)
const interativo = computed(() => selecionavel.value || props.clickable)
const tamanhoDoIcone = computed(() => (props.size === 'sm' ? '13px' : '15px'))

const classes = computed(() => ({
  'ros-chip--sm': props.size === 'sm',
  'ros-chip--interativo': interativo.value,
  'ros-chip--ligado': props.selected === true,
  'ros-chip--removivel': props.removable,
  'ros-chip--desabilitado': props.disabled,
}))

const clicar = (e) => {
  if (selecionavel.value) emit('update:selected', !props.selected)
  emit('click', e)
}
</script>
