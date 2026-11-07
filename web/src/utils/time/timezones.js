/**
 * Timezone helpers built on top of native Intl APIs — zero external deps.
 *
 * All functions are pure (no side effects, no caching of mutable state)
 * EXCEPT the IANA zone list, which is fetched once and memoized — the
 * list never changes during a runtime session.
 */

// Cached output of Intl.supportedValuesOf('timeZone'). About 430 entries
// in modern browsers; safe to keep in memory indefinitely.
let _ianaZones = null

/**
 * The IANA timezone the system is currently configured to.
 * Falls back to 'UTC' if the runtime cannot resolve it (very rare —
 * jsdom in tests sometimes returns undefined).
 */
export const getCurrentSystemTimezone = () => {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
    return tz || 'UTC'
  } catch {
    return 'UTC'
  }
}

/**
 * All IANA timezones the runtime knows about. Sorted alphabetically.
 * Returns ['UTC'] as last-resort fallback if the runtime doesn't have
 * `Intl.supportedValuesOf` (Safari < 15.4, Node < 18).
 */
export const getAllIanaZones = () => {
  if (_ianaZones) return _ianaZones
  try {
    if (typeof Intl.supportedValuesOf === 'function') {
      _ianaZones = Intl.supportedValuesOf('timeZone').slice().sort()
      return _ianaZones
    }
  } catch {
    // fall through
  }
  _ianaZones = ['UTC']
  return _ianaZones
}

/**
 * True if the given string is a recognized IANA timezone in this runtime.
 */
export const isValidTimezone = (tz) => {
  if (!tz || typeof tz !== 'string') return false
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: tz })
    return true
  } catch {
    return false
  }
}

/**
 * The current UTC offset for `tz` at the given `date`, in minutes.
 * Positive for east of UTC, negative for west. Honors DST automatically.
 *
 * Implementation: format the same instant in both tz and UTC, then diff.
 * Faster than parsing offset strings and works in every browser that
 * supports `Intl.DateTimeFormat({ timeZone })`.
 */
export const getOffsetMinutes = (tz, date = new Date()) => {
  if (!isValidTimezone(tz)) return 0
  const tzString = date.toLocaleString('en-US', { timeZone: tz })
  const utcString = date.toLocaleString('en-US', { timeZone: 'UTC' })
  const tzMs = Date.parse(tzString)
  const utcMs = Date.parse(utcString)
  if (Number.isNaN(tzMs) || Number.isNaN(utcMs)) return 0
  return Math.round((tzMs - utcMs) / 60000)
}

/**
 * Human-friendly offset between two timezones, e.g. "+5h 30min", "-1d 2h",
 * "+12h", "Same time". Used in the World Clock card label.
 */
export const getOffsetLabel = (
  targetTz,
  baseTz = getCurrentSystemTimezone(),
  date = new Date(),
) => {
  const targetMin = getOffsetMinutes(targetTz, date)
  const baseMin = getOffsetMinutes(baseTz, date)
  const diff = targetMin - baseMin
  if (diff === 0) return 'Same time'

  // `< 0` e não `> 0`: a linha acima já devolveu 'Same time' para diff zero,
  // então o zero nunca chega aqui e as duas formas decidem igual. Fica a que
  // não deixa um comparador impossível de matar.
  const sign = diff < 0 ? '-' : '+'
  const abs = Math.abs(diff)
  const days = Math.floor(abs / (24 * 60))
  const hours = Math.floor((abs % (24 * 60)) / 60)
  const minutes = abs % 60

  const parts = []
  if (days) parts.push(`${days}d`)
  if (hours) parts.push(`${hours}h`)
  if (minutes) parts.push(`${minutes}min`)
  return `${sign}${parts.join(' ')}`
}

/**
 * True if DST is currently active in the given timezone.
 * Determined by comparing winter (Jan 15) and summer (Jul 15) offsets:
 * if they differ, DST exists in this zone, and we check which season
 * matches today.
 */
export const isDstActive = (tz, now = new Date()) => {
  if (!isValidTimezone(tz)) return false
  const winter = new Date(now.getFullYear(), 0, 15)
  const summer = new Date(now.getFullYear(), 6, 15)
  const winterOffset = getOffsetMinutes(tz, winter)
  const summerOffset = getOffsetMinutes(tz, summer)
  if (winterOffset === summerOffset) return false
  const currentOffset = getOffsetMinutes(tz, now)
  // Northern hemisphere: summer = larger offset (DST). Southern: opposite.
  // Simpler: the larger offset is the DST one.
  return currentOffset === Math.max(winterOffset, summerOffset)
}

/**
 * Day/night classification for a given timezone using local hour ranges.
 * - day:      6 ≤ hour < 18
 * - twilight: 5 ≤ hour < 6 OR 18 ≤ hour < 20
 * - night:    everything else
 *
 * Pure local-hour heuristic — does NOT use lat/lng or solar calculations.
 * Good enough for the visual dot indicator in the World Clock card.
 */
export const getDayNightStatus = (tz, date = new Date()) => {
  if (!isValidTimezone(tz)) return 'day'
  const hour = Number(
    date.toLocaleString('en-US', { timeZone: tz, hour: 'numeric', hour12: false }),
  )
  if (Number.isNaN(hour)) return 'day'
  if (hour >= 6 && hour < 18) return 'day'
  if (hour === 5 || (hour >= 18 && hour < 20)) return 'twilight'
  return 'night'
}

/**
 * Reset the IANA zone cache. Used in tests that mock Intl.supportedValuesOf.
 * Not exported in production — internal escape hatch via globalThis.
 */
export const _resetTimezoneCache = () => {
  _ianaZones = null
}
