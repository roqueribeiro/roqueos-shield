/**
 * O `lang` do <html> é o idioma da sessão. O pacote de idioma do Quasar escrevia
 * `en-US` no app inteiro (medido em 15/10 no /app e no /tv, em pt-BR e em árabe),
 * e leitor de tela e voz da TV liam o português com pronúncia de inglês. O boot do
 * i18n marca o idioma inicial e o de cada troca.
 */
export function marcarIdiomaDoDocumento(locale, doc = globalThis.document) {
  if (doc && locale) doc.documentElement.lang = locale
}
