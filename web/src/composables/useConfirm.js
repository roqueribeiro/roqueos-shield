import { shallowRef } from 'vue'

/**
 * Pedir confirmação numa linha (Goal 65).
 *
 *   if (await confirmar({ titulo, mensagem, perigo: true, rotulo: t('common.remove') })) ...
 *
 * Cada tela escrevia o próprio `ROSModal type="confirm"`: um `ref(false)`, o modal, os
 * dois botões e o estado de carregando, 15 a 25 linhas por pergunta, 78 `showDeleteConfirm`
 * só de exclusão. O modal agora mora uma vez só (`ROSConfirmHost`, montado no layout) e
 * desenha o pedido da vez. Com `acao`, o botão gira enquanto ela roda e o modal só fecha
 * quando ela termina; se ela lançar erro, o modal fecha e a promessa rejeita com ele.
 *
 * Um pedido por vez: um segundo `confirmar` enquanto há um aberto responde `false` ao
 * primeiro, como se a pessoa tivesse cancelado. Se a ação do primeiro já está rodando, ela
 * não é cancelada: termina por trás e responde o que de fato aconteceu. O pedido novo pode
 * rodar a sua ação ao mesmo tempo (remover duas imagens seguidas não espera a primeira),
 * e cada botão gira só para a ação dele.
 */
export const pedidoDeConfirmacao = shallowRef(null)

export function confirmar({
  titulo,
  mensagem = '',
  rotulo = '',
  perigo = false,
  aviso = false,
  icone = '',
  acao = null,
} = {}) {
  const anterior = pedidoDeConfirmacao.value
  if (anterior && !anterior.rodando) anterior.responder(false)
  return new Promise((resolve, reject) => {
    const pedido = {
      titulo,
      mensagem,
      rotulo,
      perigo,
      aviso,
      icone: icone || (perigo ? 'delete' : aviso ? 'warning' : 'help_outline'),
      acao,
      // O host liga enquanto a ação roda (ver ROSConfirmHost).
      rodando: false,
      responder: (sim, erro) => {
        if (pedidoDeConfirmacao.value === pedido) pedidoDeConfirmacao.value = null
        if (erro) reject(erro)
        else resolve(sim)
      },
    }
    pedidoDeConfirmacao.value = pedido
  })
}

export function useConfirm() {
  return { confirmar }
}
