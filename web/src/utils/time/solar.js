/**
 * Solar position helpers — sunrise/sunset and current solar fraction
 * along the day arc, given (lat, lng, date).
 *
 * Implements simplified NOAA solar calculations:
 *   1. Julian date from input.
 *   2. Solar declination (angle between equator and direct sun line).
 *   3. Solar hour angle from local time.
 *   4. Sunrise/sunset hour angles via acos formula.
 *
 * Accuracy: ±2-5 minutes around the actual sunrise/sunset for most
 * mid-latitudes. Good enough for the visual arc indicator. Near the
 * poles during midnight-sun / polar-night seasons we return a flat
 * "always day" or "always night" indicator instead of NaN.
 *
 * No external dependencies.
 */

const toRad = (deg) => (deg * Math.PI) / 180
const toDeg = (rad) => (rad * 180) / Math.PI

/**
 * Day of the year (1..366) for the given date.
 */
function dayOfYear(date) {
  const start = new Date(date.getFullYear(), 0, 0)
  const diffMs = date - start
  return Math.floor(diffMs / 86400000)
}

/**
 * Solar declination in degrees for a given day of year.
 * Approximation: δ = 23.45 * sin(360/365 * (n - 81))
 */
function solarDeclination(date) {
  const n = dayOfYear(date)
  return 23.45 * Math.sin(toRad((360 / 365) * (n - 81)))
}

/**
 * Equation of time (minutes) — corrects for orbital eccentricity +
 * Earth's axial tilt. Simplified Spencer 1971-style.
 */
function equationOfTime(date) {
  const n = dayOfYear(date)
  const b = toRad((360 / 365) * (n - 81))
  return 9.87 * Math.sin(2 * b) - 7.53 * Math.cos(b) - 1.5 * Math.sin(b)
}

/**
 * Compute sunrise + sunset + solar noon for the given lat/lng/date.
 * Returns Date objects in UTC time (caller converts to local zone as needed).
 *
 * Special cases:
 *   - Polar day (sun never sets): returns `polarDay: true`.
 *   - Polar night (sun never rises): returns `polarNight: true`.
 *
 * @param {number} lat - degrees, +N
 * @param {number} lng - degrees, +E
 * @param {Date}   date - day to compute for (any time on that date works)
 * @returns {{ sunrise: Date|null, sunset: Date|null, solarNoon: Date,
 *             polarDay: boolean, polarNight: boolean }}
 */
export function getSunriseSunset(lat, lng, date = new Date()) {
  const dec = solarDeclination(date)
  const cosH =
    (Math.sin(toRad(-0.833)) - Math.sin(toRad(lat)) * Math.sin(toRad(dec))) /
    (Math.cos(toRad(lat)) * Math.cos(toRad(dec)))

  const eot = equationOfTime(date)
  const lngHourOffset = lng / 15 // hours
  // Solar noon in UTC, expressed as fraction-of-day hours.
  const solarNoonHours = 12 - lngHourOffset - eot / 60

  const makeUtcDate = (hoursFloat) => {
    const d = new Date(
      Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), 0, 0, 0, 0),
    )
    d.setUTCMilliseconds(Math.round(hoursFloat * 3600 * 1000))
    return d
  }

  const solarNoon = makeUtcDate(solarNoonHours)

  const halfDayHours = toDeg(Math.acos(cosH)) / 15
  if (Number.isNaN(halfDayHours)) {
    // Fora de [-1, 1] o sol não cruza o horizonte neste dia: acima de 1 é noite
    // polar, abaixo de -1 é dia polar. Quem já responde isso é o próprio
    // `Math.acos`, com NaN. As duas comparações separadas que estavam aqui
    // testavam uma borda (`cosH` exatamente 1) que nenhuma latitude real toca.
    const noitePolar = cosH >= 1
    return {
      sunrise: null,
      sunset: null,
      solarNoon,
      polarDay: !noitePolar,
      polarNight: noitePolar,
    }
  }

  const sunrise = makeUtcDate(solarNoonHours - halfDayHours)
  const sunset = makeUtcDate(solarNoonHours + halfDayHours)

  return { sunrise, sunset, solarNoon, polarDay: false, polarNight: false }
}

/**
 * Current solar fraction along the day arc, given lat/lng/now.
 *
 * Returns:
 *   - { phase: 'day', t: 0..1 }   — sun visible; t=0 at sunrise, 1 at sunset
 *   - { phase: 'night', t: 0..1 } — moon visible; t=0 at sunset, 1 at next sunrise
 *   - { phase: 'polar-day' }      — always-day season
 *   - { phase: 'polar-night' }    — always-night season
 *
 * @param {number} lat
 * @param {number} lng
 * @param {Date}   now
 */
export function getSolarFraction(lat, lng, now = new Date()) {
  const today = getSunriseSunset(lat, lng, now)
  if (today.polarDay) return { phase: 'polar-day', t: 0.5 }
  if (today.polarNight) return { phase: 'polar-night', t: 0.5 }

  const ms = now.getTime()
  const sr = today.sunrise.getTime()
  const ss = today.sunset.getTime()

  if (ms >= sr && ms <= ss) {
    const t = (ms - sr) / (ss - sr)
    return { phase: 'day', t: Math.max(0, Math.min(1, t)) }
  }

  // Night: either before today's sunrise (use yesterday's sunset)
  // or after today's sunset (use tomorrow's sunrise).
  if (ms < sr) {
    const yesterday = new Date(now.getTime() - 86400000)
    const y = getSunriseSunset(lat, lng, yesterday)
    if (!y.sunset) return { phase: 'night', t: 0.5 }
    const nightLen = sr - y.sunset.getTime()
    if (nightLen <= 0) return { phase: 'night', t: 0.5 }
    const t = (ms - y.sunset.getTime()) / nightLen
    return { phase: 'night', t: Math.max(0, Math.min(1, t)) }
  }

  // ms > ss
  const tomorrow = new Date(now.getTime() + 86400000)
  const tm = getSunriseSunset(lat, lng, tomorrow)
  if (!tm.sunrise) return { phase: 'night', t: 0.5 }
  const nightLen = tm.sunrise.getTime() - ss
  if (nightLen <= 0) return { phase: 'night', t: 0.5 }
  const t = (ms - ss) / nightLen
  return { phase: 'night', t: Math.max(0, Math.min(1, t)) }
}
