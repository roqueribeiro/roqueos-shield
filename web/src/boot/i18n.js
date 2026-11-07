import { defineBoot } from '#q-app/wrappers'
import { createI18n } from 'vue-i18n'
import messages, { idiomaInicial } from 'src/i18n'
import { marcarIdiomaDoDocumento } from 'src/utils/idiomaDoDocumento'

export let i18n = null

export default defineBoot(({ app }) => {
  const locale = idiomaInicial()
  i18n = createI18n({
    legacy: false,
    globalInjection: true,
    locale,
    // Chave que falta no idioma escolhido cai no inglês e, por fim, no português.
    fallbackLocale: { 'pt-BR': ['pt-BR'], default: ['en-US', 'pt-BR'] },
    messages,
    missingWarn: false,
    fallbackWarn: false,
  })
  marcarIdiomaDoDocumento(locale)
  // `utils/format.js` lê o idioma daqui (como no RoqueOS). Sem isto, data e tempo
  // relativo saíam em português na tela em inglês ("em 3 horas", "7 de nov.").
  globalThis.__ROS_I18N__ = i18n
  app.use(i18n)
})
