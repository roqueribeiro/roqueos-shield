// Os idiomas da tela standalone: os mesmos dez do RoqueOS, só com os namespaces que
// a tela do RoqueShield usa (pentest, common, errors, aiProvider), mais `shield`,
// que só existe aqui. Todos entram no bundle: são poucos KB por idioma.
import shield from './shield'

const modulos = import.meta.glob('./*/*.js', { eager: true })

export const IDIOMAS = ['pt-BR', 'en-US', 'es-ES', 'fr-FR', 'de-DE', 'ja-JP', 'zh-CN', 'hi-IN', 'ru-RU', 'ar-AR']

const messages = {}
for (const [caminho, mod] of Object.entries(modulos)) {
  const [, idioma, arquivo] = caminho.match(/^\.\/([^/]+)\/([^/]+)\.js$/) || []
  if (!idioma) continue
  messages[idioma] = messages[idioma] || {}
  messages[idioma][arquivo] = mod.default
}
for (const idioma of IDIOMAS) {
  messages[idioma] = messages[idioma] || {}
  if (shield[idioma]) messages[idioma].shield = shield[idioma]
}

const CHAVE = 'roqueshield.idioma'

export function idiomaInicial() {
  try {
    const salvo = localStorage.getItem(CHAVE)
    if (salvo && IDIOMAS.includes(salvo)) return salvo
  } catch {
    // armazenamento bloqueado: segue pelo navegador
  }
  const nav = (navigator.languages || [navigator.language || 'pt-BR']).map(String)
  for (const n of nav) {
    const exato = IDIOMAS.find((i) => i.toLowerCase() === n.toLowerCase())
    if (exato) return exato
    const base = IDIOMAS.find((i) => i.slice(0, 2) === n.slice(0, 2).toLowerCase())
    if (base) return base
  }
  return 'pt-BR'
}

export default messages
