import { getCurrentScope, onScopeDispose } from 'vue'

/**
 * A função que espera a pessoa parar (Goal 65).
 *
 *   const buscar = useDebounced((termo) => api.buscar(termo), 300)
 *   buscar('ng'); buscar('ngi')   // só a última roda, 300ms depois
 *
 * Eram 31 `clearTimeout` + `setTimeout` escritos à mão, e o defeito repetido era o mesmo:
 * o componente desmontava com a espera armada e a função rodava depois, num estado que já
 * não existia. Aqui a espera morre com o componente. `.cancelar()` desarma e `.agora()`
 * roda o pendente na hora (o Enter de uma busca, o salvar ao fechar).
 */
export function useDebounced(fn, espera = 300) {
  let relogio = null
  let pendentes = null

  const atrasada = (...args) => {
    pendentes = args
    clearTimeout(relogio)
    relogio = setTimeout(() => {
      relogio = null
      const a = pendentes
      pendentes = null
      fn(...a)
    }, espera)
  }
  atrasada.cancelar = () => {
    clearTimeout(relogio)
    relogio = null
    pendentes = null
  }
  atrasada.agora = () => {
    if (!pendentes) return
    const a = pendentes
    atrasada.cancelar()
    fn(...a)
  }
  if (getCurrentScope()) onScopeDispose(atrasada.cancelar)
  return atrasada
}
