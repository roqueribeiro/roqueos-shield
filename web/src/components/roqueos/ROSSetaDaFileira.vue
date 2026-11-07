<template>
  <button
    type="button"
    class="ros-seta-da-fileira"
    tabindex="-1"
    aria-hidden="true"
    :disabled="apagada"
    @mousedown.prevent
  >
    <q-icon :name="icone" :size="tamanho" />
  </button>
</template>

<script setup>
// A seta de uma fileira que rola de lado sem barra pintada (Goal 71): as abas do sistema,
// as de documento e a fileira de documentos do Editor. A barra é escondida (regra 21), e
// no mouse a roda é vertical: sem a seta, o que não cabia não tinha como ser alcançado.
//
// Ela é só do mouse. Fica fora do Tab e da árvore de acessibilidade (o teclado anda pelas
// setas do teclado, e a fileira traz o item com foco para a vista), e o clique não tira o
// foco de onde ele estava. Na ponta, a seta daquele lado apaga em vez de sumir, e a fileira
// não pula de lugar. O clique é de quem usa (`@click`), com o `rolar` do
// `useFileiraComSetas`. No RTL a seta do início aponta para a direita.
import { computed } from 'vue'

const props = defineProps({
  lado: { type: String, required: true, validator: (v) => ['inicio', 'fim'].includes(v) },
  rtl: { type: Boolean, default: false },
  apagada: { type: Boolean, default: false },
  tamanho: { type: String, default: '20px' },
})

const icone = computed(() =>
  (props.lado === 'inicio') !== props.rtl ? 'chevron_left' : 'chevron_right',
)
</script>

<style lang="scss">
// Mora no componente, e não no kit global: só as fileiras que transbordam a carregam, e a
// abertura do /app não paga por ela (teto de 151 KB, Goal 71).
// A seta de uma fileira que rola sem barra pintada (ROSSetaDaFileira; Goal 71): nas abas
// do sistema, nas de documento e na fileira de documentos do Editor. Fora do Tab e da árvore
// de acessibilidade, ela só existe para o mouse. Na ponta, a seta daquele lado apaga (como
// as do Quasar de antes) em vez de sumir, e a fileira não pula de lugar.
.ros-seta-da-fileira {
  // Por cima da fileira: no dedo o alvo dela entra uns pixels na fileira, e a aba da ponta
  // (pintada depois) roubava o toque da seta do início (régua de toque a 390, Goal 71).
  position: relative;
  z-index: 1;
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--ros-space-8);
  padding: 0;
  border: none;
  border-radius: var(--ros-radius-sm);
  background: transparent;
  color: var(--ros-text-80);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition:
    background var(--ros-duration-fast) var(--ros-ease-default),
    color var(--ros-duration-fast) var(--ros-ease-default),
    opacity var(--ros-duration-fast) var(--ros-ease-default);

  // No dedo o alvo chega a 44 de largura sem a seta crescer (a receita do kit).
  @media (pointer: coarse) {
    &::after {
      content: '';
      position: absolute;
      inset: 0 min(0px, calc((100% - 44px) / 2));
    }
  }

  &:hover:not(:disabled) {
    background: var(--ros-fill-08);
    color: var(--ros-text-100);
  }

  &:disabled {
    opacity: 0.3;
    cursor: default;
  }
}
</style>
