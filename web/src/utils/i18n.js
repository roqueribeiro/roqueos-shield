import { i18n as i18nInstance } from 'src/boot/i18n'

export const t = (key, params = undefined, fallback = undefined) => {
  const i18n = i18nInstance
  const translate = i18n?.global?.t

  if (typeof translate !== 'function') {
    return fallback ?? key
  }

  const translated = translate(key, params)
  if (fallback && translated === key) {
    return fallback
  }

  return translated
}

export const te = (key) => {
  const i18n = i18nInstance
  const exists = i18n?.global?.te
  if (typeof exists !== 'function') return false
  return exists(key)
}
