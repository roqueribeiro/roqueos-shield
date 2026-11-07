<template>
  <component :is="tag" class="ros-card" :class="classes">
    <header v-if="temCabeca" class="ros-card__cabeca">
      <slot name="icon">
        <span
          v-if="icon"
          class="ros-card__icone"
          :class="{ 'ros-card__icone--cor': iconColor }"
          :style="iconColor ? { background: iconColor } : undefined"
          aria-hidden="true"
        >
          <q-icon :name="icon" size="20px" />
        </span>
      </slot>
      <div class="ros-card__titulos">
        <slot name="header">
          <button
            v-if="interactive"
            type="button"
            class="ros-card__titulo ros-card__alvo"
            :disabled="disabled"
            :aria-current="active ? 'true' : undefined"
            @click="emit('click', $event)"
          >
            {{ title }}
          </button>
          <p v-else-if="title" class="ros-card__titulo">{{ title }}</p>
          <p v-if="subtitle" class="ros-card__subtitulo">{{ subtitle }}</p>
        </slot>
      </div>
      <div v-if="$slots.actions" class="ros-card__acoes">
        <slot name="actions" />
      </div>
    </header>
    <div v-if="$slots.default" class="ros-card__corpo">
      <slot />
    </div>
    <footer v-if="$slots.footer" class="ros-card__pe">
      <slot name="footer" />
    </footer>
  </component>
</template>

<script setup>
// O cartão do sistema (Goal 64): superfície com cabeçalho (ícone, título, subtítulo,
// ações), corpo e pé. Eram 214 classes `__card` em 36 arquivos, cada uma com um raio,
// uma borda e uma sombra.
//
// `interactive`: o cartão inteiro abre alguma coisa. O alvo é o TÍTULO, um botão de
// verdade, e um pseudo-elemento dele cobre o cartão (o "link esticado"). Assim o
// teclado chega nele, o leitor de tela anuncia o título como nome, e as ações do
// cabeçalho continuam sendo botões próprios por cima, sem botão dentro de botão.
//
// `#icon` troca o ladrilho do ícone por outro desenho, e `icon-color` pinta o ladrilho.
// O subtítulo corta em duas linhas: descrição longa é do corpo, não do cabeçalho.
import { computed, useSlots } from 'vue'

const props = defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  icon: { type: String, default: '' },
  // A cor própria do item (o avatar de um agente): o ladrilho fica cheio dela, com o
  // ícone claro. Sem ela, o ladrilho é a tinta do accent do app.
  iconColor: { type: String, default: '' },
  // `surface` (preenchido) ou `outlined` (só a borda, para cartão dentro de cartão).
  variant: {
    type: String,
    default: 'surface',
    validator: (v) => ['surface', 'outlined'].includes(v),
  },
  padding: {
    type: String,
    default: 'md',
    validator: (v) => ['none', 'sm', 'md', 'lg'].includes(v),
  },
  interactive: { type: Boolean, default: false },
  active: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  tag: { type: String, default: 'div' },
})

const emit = defineEmits(['click'])
const slots = useSlots()

// O alvo do cartão interativo é o título: sem ele, o cartão parece clicável e o teclado
// não chega. Em desenvolvimento, avisa em vez de falhar calado.
if (import.meta.env.DEV && props.interactive && !props.title) {
  console.warn('[ROSCard] interactive precisa de title: é ele o botão que o teclado alcança')
}

const temCabeca = computed(
  () =>
    !!(props.title || props.icon || props.subtitle || slots.header || slots.icon || slots.actions),
)

const classes = computed(() => [
  `ros-card--${props.variant}`,
  props.padding !== 'md' && `ros-card--pad-${props.padding}`,
  {
    'ros-card--interativo': props.interactive,
    'ros-card--ativo': props.active,
    'ros-card--desabilitado': props.disabled,
  },
])
</script>
