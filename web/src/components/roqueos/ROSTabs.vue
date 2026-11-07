<template>
  <div
    class="ros-tabs"
    :class="{
      'ros-tabs--pilula': variant === 'pilula',
      'ros-tabs--quebra': quebrar,
      'ros-tabs--ladrilho': ladrilho,
      'ros-tabs--transborda': transborda,
    }"
  >
    <!-- As setas aparecem quando a fileira não cabe (ROSSetaDaFileira, só do mouse). -->
    <ROSSetaDaFileira
      v-if="transborda"
      lado="inicio"
      :rtl="rtl"
      :apagada="noInicio"
      :tamanho="tamanhoDoIcone"
      class="ros-tabs__seta"
      @click="rolar(-1)"
    />
    <div
      ref="fileira"
      class="ros-tabs__fileira"
      role="tablist"
      :aria-label="label || undefined"
      @scroll.passive="medir"
    >
      <button
        v-for="(aba, i) in tabs"
        :id="idBase ? `${idBase}-aba-${aba.value}` : undefined"
        :key="aba.value"
        type="button"
        role="tab"
        class="ros-tabs__aba"
        :class="{ 'ros-tabs__aba--ativa': aba.value === modelValue }"
        :aria-selected="aba.value === modelValue ? 'true' : 'false'"
        :aria-controls="idBase ? `${idBase}-painel-${aba.value}` : undefined"
        :tabindex="i === indiceDoFoco ? 0 : -1"
        :disabled="aba.disabled"
        @click="escolher(aba.value)"
        @keydown="aoTeclar($event, i)"
      >
        <q-icon v-if="aba.icon" :name="aba.icon" class="ros-tabs__icone" :size="tamanhoDoIcone" />
        <span class="ros-tabs__rotulo">{{ aba.label }}</span>
        <span v-if="aba.badge" class="ros-tabs__selo">{{ aba.badge }}</span>
      </button>
    </div>
    <ROSSetaDaFileira
      v-if="transborda"
      lado="fim"
      :rtl="rtl"
      :apagada="noFim"
      :tamanho="tamanhoDoIcone"
      class="ros-tabs__seta"
      @click="rolar(1)"
    />
  </div>
</template>

<script setup>
// As abas do sistema (Goal 63): uma fileira que troca de painel, com o traço da aba
// ativa no accent do app. Cada app desenhava as suas (pílula azul com brilho no
// DockerInfra, sublinhado no Admin, chip no Detalhe do container). Teclado como manda
// o padrão de abas: o foco mora na aba ativa, setas trocam e ativam, Home e End vão
// às pontas. `id-base` liga cada aba ao painel dela (`<id-base>-painel-<valor>`).
//
// Duas caras: `linha` (o traço embaixo, o padrão) e `pilula` (Goal 71, pedido do
// founder: o filtro segmentado do Chat de antes do Goal 67, um trilho arredondado com
// ícone sobre o rótulo e a ativa cheia no accent). E, nas duas, quando a fileira não cabe,
// aparecem setas nas pontas: com a barra de rolagem escondida, a aba de fora não tinha
// como ser alcançada com o mouse (Chat a 1440, Goal 71: 276px visíveis para 482 de abas).
import { computed, nextTick, ref, watch } from 'vue'
import { useFileiraComSetas } from 'src/composables/useFileiraComSetas'
import ROSSetaDaFileira from './ROSSetaDaFileira.vue'

const props = defineProps({
  modelValue: { type: [String, Number], default: null },
  // [{ value, label, icon?, badge?, disabled? }]
  tabs: { type: Array, required: true },
  label: { type: String, default: '' },
  idBase: { type: String, default: '' },
  variant: {
    type: String,
    default: 'linha',
    validator: (v) => ['linha', 'pilula'].includes(v),
  },
  // As abas descem para a linha de baixo em vez de rolar (a barra lateral estreita do Paint).
  quebrar: { type: Boolean, default: false },
  // No trilho estreito (até 560px) as abas viram ladrilhos de largura igual, ícone sobre
  // o rótulo, todas numa fileira só. Para poucas abas (2 a 5) que precisam estar à vista.
  ladrilho: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const tamanhoDoIcone = computed(() => (props.variant === 'pilula' ? '16px' : '17px'))

const indiceDoFoco = computed(() => {
  const i = props.tabs.findIndex((aba) => aba.value === props.modelValue)
  return i >= 0 ? i : 0
})

const escolher = (valor) => {
  if (valor !== props.modelValue) emit('update:modelValue', valor)
}

// --- o que não cabe: as setas (useFileiraComSetas) ----------------------------------

const fileira = ref(null)
const { transborda, noInicio, noFim, rtl, medir, rolar, trazerParaVista } = useFileiraComSetas(
  fileira,
  { desligada: () => props.quebrar || props.ladrilho },
)
watch(
  () => props.tabs,
  () => nextTick(medir),
  { deep: true },
)
// A aba escolhida (no clique numa aba cortada, ou de fora, pelo app) entra inteira.
watch(
  () => props.modelValue,
  () =>
    nextTick(() => {
      trazerParaVista(fileira.value?.children[indiceDoFoco.value])
      medir()
    }),
)

const aoTeclar = (e, atual) => {
  const lista = props.tabs.map((aba, i) => (aba.disabled ? -1 : i)).filter((i) => i >= 0)
  const pos = lista.indexOf(atual)
  const proxima = lista[(pos + 1) % lista.length]
  const anterior = lista[(pos - 1 + lista.length) % lista.length]
  const ehRtl = getComputedStyle(e.currentTarget).direction === 'rtl'
  const destinos = {
    ArrowRight: ehRtl ? anterior : proxima,
    ArrowLeft: ehRtl ? proxima : anterior,
    Home: lista[0],
    End: lista[lista.length - 1],
  }
  if (!(e.key in destinos) || pos < 0) return
  e.preventDefault()
  const alvo = destinos[e.key]
  escolher(props.tabs[alvo].value)
  // O foco vai pelo DOM, que o v-for mantém na ordem da lista. O array de `ref` de um
  // v-for não garante essa ordem depois que a lista muda.
  const destino = e.currentTarget.parentElement?.children[alvo]
  destino?.focus({ preventScroll: true })
  trazerParaVista(destino)
}
</script>

<style lang="scss">
// A variante pílula mora no componente, e não no kit global: só quem usa abas a carrega,
// e a abertura do /app não paga por ela (teto de 151 KB, Goal 71).
.ros-tabs {
  // --- pílula (Goal 71) -----------------------------------------------------
  //
  // O filtro do Chat de antes do Goal 67, como ele aparecia na tela: o trilho no
  // preenchimento terciário com 4px de folga, cada opção com o ícone sobre o rótulo, a
  // ativa cheia no accent e o selo de contagem preso no canto. O raio da opção é o do
  // trilho menos a folga, para as curvas ficarem paralelas.
  &--pilula {
    padding: var(--ros-space-1);
    border-bottom: none;
    border-radius: var(--ros-radius-lg);
    background: var(--ros-fill-07);
  }

  &--pilula &__fileira {
    gap: 6px;
  }

  // As setas encostam na borda do trilho, por cima da folga das pontas (como as de antes).
  // A folga do trilho não muda com elas: é com ela que o "cabe ou não cabe" se conta.
  &--pilula &__seta {
    width: 36px;
    border-radius: calc(var(--ros-radius-lg) - var(--ros-space-1));
    color: var(--ros-text-100);

    &:first-child {
      margin-inline-start: calc(-1 * var(--ros-space-1));
    }

    &:last-child {
      margin-inline-end: calc(-1 * var(--ros-space-1));
    }
  }

  &--pilula &__aba {
    flex-direction: column;
    justify-content: center;
    gap: 5px;
    min-width: 60px;
    min-height: 26px;
    padding: var(--ros-space-2) 10px;
    border-radius: calc(var(--ros-radius-lg) - var(--ros-space-1));
    color: var(--ros-text-muted);
    font-weight: var(--ros-font-semibold);
    letter-spacing: 0.1px;
    line-height: 1;
    transition:
      background var(--ros-duration-fast) var(--ros-ease-default),
      color var(--ros-duration-fast) var(--ros-ease-default);

    &::after {
      display: none;
    }

    &:hover {
      background: var(--ros-hover-bg);
      color: var(--ros-text);
    }

    &:focus-visible {
      outline-offset: 2px;
      border-radius: calc(var(--ros-radius-lg) - var(--ros-space-1));
    }
  }

  // Cheia no accent do app escurecido até o branco dar 4,5:1 (o azul puro com branco dá
  // 4,0 e o ciano do Chat 2,4): a mesma cor, o texto claro de antes, e o contraste em dia.
  &--pilula &__aba--ativa,
  &--pilula &__aba--ativa:hover {
    background: rgb(var(--ros-app-accent-fill-rgb));
    color: rgb(var(--ros-on-accent-rgb));
  }

  &--pilula &__icone {
    width: 24px;
    height: 24px;
  }

  &--pilula &__selo {
    position: absolute;
    top: 2px;
    right: 2px;
    min-width: 16px;
    height: 16px;
    padding: 0 5px;
    background: rgb(var(--ros-app-accent-text-rgb));
    color: rgb(var(--ros-scrim-rgb));
    line-height: 16px;
  }
}
</style>
