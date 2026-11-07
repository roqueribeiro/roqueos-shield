<template>
  <div
    class="ros-segmented"
    :class="{
      'ros-segmented--sm': size === 'sm',
      'ros-segmented--block': block,
      'ros-segmented--quebra': quebrar,
    }"
    :style="quebrar ? { '--ros-seg-n': options.length } : undefined"
    role="radiogroup"
    :aria-label="label || undefined"
  >
    <button
      v-for="(op, i) in options"
      :key="op.value"
      type="button"
      role="radio"
      class="ros-segmented__opcao"
      :class="{ 'ros-segmented__opcao--ativa': op.value === modelValue }"
      :aria-checked="op.value === modelValue ? 'true' : 'false'"
      :tabindex="i === indiceDoFoco ? 0 : -1"
      :disabled="disabled || op.disabled"
      @click="escolher(op.value)"
      @keydown="aoTeclar($event, i)"
    >
      <q-icon v-if="op.icon" :name="op.icon" :size="size === 'sm' ? '15px' : '17px'" />
      <span v-if="op.label" class="ros-segmented__rotulo">{{ op.label }}</span>
      <span v-if="op.badge" class="ros-segmented__selo">{{ op.badge }}</span>
    </button>
  </div>
</template>

<script setup>
// O controle segmentado do sistema (Goal 63): duas a cinco opções exclusivas lado a
// lado, como "Não lidas | Todas" ou "Grade | Lista". Era escrito à mão em sete
// lugares, quatro deles marcados como `tablist` (que é outra coisa: aba troca de
// painel, segmento troca um valor). Aqui é `radiogroup` com setas, Home e End, e o
// foco mora só na opção escolhida, como manda o padrão de grupo de rádio.
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number, Boolean], default: null },
  // [{ value, label, icon?, badge?, disabled? }]
  options: { type: Array, required: true },
  label: { type: String, default: '' },
  size: { type: String, default: 'md', validator: (v) => ['sm', 'md'].includes(v) },
  block: { type: Boolean, default: false },
  // As opções descem em linhas quando não cabem lado a lado, e o rótulo quebra em vez
  // de cortar. Para rótulos que não podem virar reticência (o formato do relatório).
  quebrar: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const indiceDoFoco = computed(() => {
  const i = props.options.findIndex((op) => op.value === props.modelValue)
  return i >= 0 ? i : 0
})

const escolher = (valor) => {
  if (valor !== props.modelValue) emit('update:modelValue', valor)
}

const habilitados = () => props.options.map((op, i) => (op.disabled ? -1 : i)).filter((i) => i >= 0)

const aoTeclar = (e, atual) => {
  const lista = habilitados()
  const pos = lista.indexOf(atual)
  const proximo = lista[(pos + 1) % lista.length]
  const anterior = lista[(pos - 1 + lista.length) % lista.length]
  // Em árabe a fileira corre da direita para a esquerda, e a seta segue o olho.
  const rtl = getComputedStyle(e.currentTarget).direction === 'rtl'
  const destinos = {
    ArrowRight: rtl ? anterior : proximo,
    ArrowLeft: rtl ? proximo : anterior,
    ArrowDown: proximo,
    ArrowUp: anterior,
    Home: lista[0],
    End: lista[lista.length - 1],
  }
  if (!(e.key in destinos) || pos < 0) return
  e.preventDefault()
  const alvo = destinos[e.key]
  escolher(props.options[alvo].value)
  // O foco vai pelo DOM, que o v-for mantém na ordem da lista. O array de `ref` de um
  // v-for não garante essa ordem depois que a lista muda.
  e.currentTarget.parentElement?.children[alvo]?.focus()
}
</script>
