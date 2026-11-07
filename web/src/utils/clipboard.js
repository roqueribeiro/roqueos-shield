/**
 * Copiar texto para a área de transferência, com o caminho antigo de reserva (Goal 65).
 *
 * `navigator.clipboard` só existe em contexto seguro (https, localhost) e no iOS antigo
 * recusa fora de um gesto do usuário; o `execCommand('copy')` com um `<textarea>`
 * escondido cobre esses dois. Eram 28 cópias à mão em 24 arquivos, metade sem a reserva
 * e quase todas sem avisar se deu certo. Quem quer o aviso usa `useClipboard`.
 * @param {string} texto
 * @returns {Promise<boolean>} se copiou
 */
export async function copiarTexto(texto) {
  const valor = String(texto ?? '')
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(valor)
      return true
    }
  } catch {
    // Sem permissão ou fora de contexto seguro: tenta o caminho antigo abaixo.
  }
  try {
    const campo = document.createElement('textarea')
    campo.value = valor
    campo.setAttribute('readonly', '')
    Object.assign(campo.style, { position: 'fixed', top: '0', left: '0', opacity: '0' })
    document.body.appendChild(campo)
    campo.select()
    const ok = document.execCommand('copy')
    campo.remove()
    return ok
  } catch {
    return false
  }
}
