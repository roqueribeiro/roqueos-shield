import { getCurrentScope, onScopeDispose, ref } from 'vue'
import { useRoqueOSStore } from 'stores/roqueos'
import { t } from 'src/utils/i18n'
import { copiarTexto } from 'src/utils/clipboard'

/**
 * Copiar com aviso do sistema e estado de "copiado" (Goal 65).
 *
 * `copiar(texto)` copia, mostra "Copiado" (ou o erro amigável) pela notificação do
 * sistema e deixa `copiado` verdadeiro por um segundo e meio, para o botão trocar o ícone
 * para um check. `{ aviso: false }` cala a notificação (o botão já mostra o check).
 */
export function useClipboard({ duracao = 1500 } = {}) {
  const copiado = ref(false)
  let relogio = null

  const copiar = async (texto, { aviso = true, mensagem } = {}) => {
    const ok = await copiarTexto(texto)
    if (aviso) {
      useRoqueOSStore().showNotification({
        message: ok ? mensagem || t('common.copied') : t('common.copyFailed'),
        type: ok ? 'success' : 'error',
        timeout: 2000,
      })
    }
    if (ok) {
      copiado.value = true
      clearTimeout(relogio)
      relogio = setTimeout(() => (copiado.value = false), duracao)
    }
    return ok
  }

  if (getCurrentScope()) onScopeDispose(() => clearTimeout(relogio))
  return { copiar, copiado }
}
