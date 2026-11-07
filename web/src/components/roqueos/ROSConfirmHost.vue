<template>
  <ROSModal
    :model-value="!!pedido"
    type="confirm"
    size="sm"
    :camada="CAMADA"
    :variant="visto?.perigo ? 'danger' : visto?.aviso ? 'warning' : 'default'"
    :title="visto?.titulo || ''"
    :subtitle="visto?.mensagem || ''"
    :icon="visto?.icone || ''"
    @update:model-value="(aberto) => !aberto && cancelar()"
  >
    <template #footer>
      <button
        type="button"
        class="ros-modal__btn ros-modal__btn--cancel"
        :disabled="rodando"
        data-qa="confirmar-nao"
        @click="cancelar"
      >
        {{ $t('common.cancel') }}
      </button>
      <button
        type="button"
        class="ros-modal__btn"
        :class="classeDoSim"
        :disabled="rodando"
        :aria-busy="rodando ? 'true' : undefined"
        data-qa="confirmar-sim"
        @click="aceitar"
      >
        <ROSSpinner v-if="rodando" size="sm" herda aria-hidden="true" />
        <span v-else>{{ visto?.rotulo || $t('common.confirm') }}</span>
      </button>
    </template>
  </ROSModal>
</template>

<script setup>
// O modal de confirmação do sistema, montado uma vez no App (Goal 65). Desenha o pedido
// que `confirmar()` (src/composables/useConfirm.js) deixou na fila e devolve a resposta.
import { computed, shallowRef, watch } from 'vue'
import ROSModal from 'components/roqueos/ROSModal.vue'
import ROSSpinner from 'components/roqueos/ROSSpinner.vue'
import { pedidoDeConfirmacao } from 'src/composables/useConfirm'

// A confirmação pode vir de dentro de outro modal (sair do assistente de servidor sem
// salvar, remover algo de uma lista aberta num modal). O host é montado no primeiro pedido,
// e um modal montado depois dele fica na frente com o mesmo 9999: a pergunta abriria por
// baixo. Ela vai acima dos modais e dos menus (10001), abaixo da dica.
const CAMADA = 10002
const pedido = computed(() => pedidoDeConfirmacao.value)
// O último pedido continua desenhado enquanto o modal sai: sem isso o título e o botão
// somem antes da animação de saída terminar.
const visto = shallowRef(null)
watch(pedido, (p) => p && (visto.value = p), { immediate: true })
// A execução é do pedido, não do modal: um pedido novo que chega enquanto a ação de outro
// roda não herda o botão girando nem os botões travados.
const emExecucao = shallowRef(null)
const rodando = computed(() => !!pedido.value && emExecucao.value === pedido.value)
// Ação destrutiva sai vermelha (regra 10), aviso sai âmbar, o resto sai claro.
const classeDoSim = computed(() =>
  visto.value?.perigo
    ? 'ros-modal__btn--danger'
    : visto.value?.aviso
      ? 'ros-modal__btn--warning'
      : 'ros-modal__btn--confirm',
)

const cancelar = () => {
  if (rodando.value) return
  pedido.value?.responder(false)
}

const aceitar = async () => {
  const atual = pedido.value
  if (!atual || rodando.value) return
  if (!atual.acao) return atual.responder(true)
  atual.rodando = true
  emExecucao.value = atual
  try {
    await atual.acao()
    atual.responder(true)
  } catch (erro) {
    atual.responder(false, erro)
  } finally {
    atual.rodando = false
    if (emExecucao.value === atual) emExecucao.value = null
  }
}
</script>
