<template>
  <div class="ros-modal__input-group">
    <label v-if="label" :for="inputId">{{ label }}</label>

    <slot v-if="$slots.default" :id="inputId" :inputClass="computedInputClass" />

    <input
      v-else
      :id="inputId"
      :value="modelValue"
      :type="type"
      :placeholder="placeholder"
      :disabled="disabled"
      :readonly="readonly"
      :name="name"
      :autocomplete="autocomplete"
      :maxlength="maxlength"
      :class="computedInputClass"
      v-bind="attrs"
      @input="onInput"
      @keyup.enter="onEnter"
    />
  </div>
</template>

<script setup>
import { computed, ref, useAttrs } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  modelValue: {
    type: [String, Number],
    default: '',
  },
  label: {
    type: String,
    default: '',
  },
  type: {
    type: String,
    default: 'text',
  },
  placeholder: {
    type: String,
    default: '',
  },
  id: {
    type: String,
    default: '',
  },
  name: {
    type: String,
    default: '',
  },
  autocomplete: {
    type: String,
    default: '',
  },
  maxlength: {
    type: [Number, String],
    default: undefined,
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  readonly: {
    type: Boolean,
    default: false,
  },
  inputClass: {
    type: [String, Array, Object],
    default: '',
  },
})

const emit = defineEmits(['update:modelValue', 'enter'])

const attrs = useAttrs()

const randomId = ref(`ros-form-field-${Math.random().toString(36).slice(2, 10)}`)

const inputId = computed(() => props.id || randomId.value)

const computedInputClass = computed(() => {
  return ['ros-modal__input', props.inputClass]
})

const onInput = (e) => emit('update:modelValue', e?.target?.value ?? '')

const onEnter = () => emit('enter')
</script>
