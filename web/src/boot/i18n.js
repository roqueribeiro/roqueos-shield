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
  app.use(i18n)
})
