import { t } from 'src/utils/i18n'

export const getUserErrorMessage = (err, { fallbackKey = 'errors.generic' } = {}) => {
  const code = err?.code || null
  const msg = err?.message || ''
  const lower = String(msg).toLowerCase()

  if (code === 'permission-denied' || lower.includes('insufficient permissions')) {
    return t('errors.loadFailed')
  }

  if (
    code === 'ERR_NETWORK' ||
    lower.includes('failed to fetch') ||
    lower.includes('network error') ||
    lower.includes('net::err_connection_refused') ||
    lower.includes('net::err_connection_reset') ||
    lower.includes('net::err_name_not_resolved')
  ) {
    return t('errors.http.networkError')
  }

  return t(fallbackKey)
}

export const logTechnicalError = (context, err) => {
  console.error(context, err)
}
