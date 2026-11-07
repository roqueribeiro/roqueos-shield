/**
 * Date/time formatting helpers built on Intl.DateTimeFormat.
 *
 * Uses an internal cache keyed by `${locale}|${timeZone}|${optsJson}` so
 * we don't re-instantiate the same formatter on every tick (~1Hz updates
 * across menubar + N widgets multiply quickly).
 */

const _formatterCache = new Map()

const getFormatter = (locale, timeZone, options) => {
  const key = `${locale}|${timeZone || ''}|${JSON.stringify(options || {})}`
  let fmt = _formatterCache.get(key)
  if (!fmt) {
    const opts = { ...(options || {}) }
    if (timeZone) opts.timeZone = timeZone
    try {
      fmt = new Intl.DateTimeFormat(locale, opts)
    } catch {
      // Invalid timezone or option combo — fall back to runtime defaults.
      fmt = new Intl.DateTimeFormat(locale, options || {})
    }
    _formatterCache.set(key, fmt)
  }
  return fmt
}

/**
 * Format a Date as time only (HH:mm or h:mm a, depending on locale/opts).
 *
 * @param {Date}   date
 * @param {object} [opts]
 * @param {string} [opts.locale='en-US']
 * @param {string} [opts.timeZone]
 * @param {boolean}[opts.showSeconds=false]
 * @param {'12h'|'24h'|'auto'}[opts.format='auto']
 */
export const formatTime = (date, opts = {}) => {
  const { locale = 'en-US', timeZone, showSeconds = false, format = 'auto' } = opts
  const intlOpts = {
    hour: '2-digit',
    minute: '2-digit',
  }
  if (showSeconds) intlOpts.second = '2-digit'
  if (format === '12h') intlOpts.hour12 = true
  else if (format === '24h') intlOpts.hour12 = false
  return getFormatter(locale, timeZone, intlOpts).format(date)
}

/**
 * Format a Date as date only.
 *
 * @param {Date}   date
 * @param {object} [opts]
 * @param {string} [opts.locale='en-US']
 * @param {string} [opts.timeZone]
 * @param {'short'|'medium'|'long'|'full'} [opts.style='medium']
 * @param {boolean}[opts.includeWeekday=false]
 */
export const formatDate = (date, opts = {}) => {
  const { locale = 'en-US', timeZone, style = 'medium', includeWeekday = false } = opts
  const intlOpts = {}
  switch (style) {
    case 'short':
      intlOpts.day = 'numeric'
      intlOpts.month = 'short'
      break
    case 'long':
      intlOpts.day = 'numeric'
      intlOpts.month = 'long'
      intlOpts.year = 'numeric'
      break
    case 'full':
      intlOpts.day = 'numeric'
      intlOpts.month = 'long'
      intlOpts.year = 'numeric'
      intlOpts.weekday = 'long'
      return getFormatter(locale, timeZone, intlOpts).format(date)
    default:
      intlOpts.day = 'numeric'
      intlOpts.month = 'short'
      intlOpts.year = 'numeric'
  }
  if (includeWeekday) intlOpts.weekday = 'short'
  return getFormatter(locale, timeZone, intlOpts).format(date)
}

/**
 * Combined date + time, e.g. "Thu, 15 May 14:30".
 * Used by the menubar — single string, no separate calls.
 */
export const formatDateTime = (date, opts = {}) => {
  const datePart = formatDate(date, {
    ...opts,
    style: 'short',
    includeWeekday: opts.includeWeekday,
  })
  const timePart = formatTime(date, opts)
  return `${datePart} ${timePart}`
}

/**
 * Format a Date in a specific timezone — shorthand wrapper for the
 * common case in the World Clock cards.
 */
export const formatTimeWithTz = (date, timeZone, opts = {}) => {
  return formatTime(date, { ...opts, timeZone })
}

/**
 * Format the current weekday name in long form, in the given locale.
 * Used by the menubar popover header.
 */
export const formatWeekdayName = (date, opts = {}) => {
  const { locale = 'en-US', timeZone } = opts
  return getFormatter(locale, timeZone, { weekday: 'long' }).format(date)
}

/**
 * Resolve the 'auto' time format choice into '12h' or '24h' based on what
 * the runtime considers default for the given locale. Used by stores
 * exposing a reactive `effectiveFormat`.
 */
export const resolveAutoFormat = (locale = 'en-US') => {
  try {
    const fmt = new Intl.DateTimeFormat(locale, { hour: 'numeric' })
    const opts = fmt.resolvedOptions()
    return opts.hour12 ? '12h' : '24h'
  } catch {
    return '24h'
  }
}

/**
 * Reset the cache. Tests use this between cases that mutate Intl.
 */
export const _resetFormatterCache = () => {
  _formatterCache.clear()
}
