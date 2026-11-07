/**
 * Números, tamanhos, datas e tempos, no idioma de quem usa (Goal 65).
 *
 * Era a fonte única que quase ninguém usava: 4 arquivos importavam daqui, e 95 escreviam
 * o seu `formatBytes`, `formatDate` ou `formatDuration`, a maioria com o português
 * cravado ("2 dias atrás") num sistema de dez idiomas e o ponto decimal do inglês. Tudo
 * aqui sai do `Intl`, no idioma corrente do i18n (lido de `globalThis.__ROS_I18N__`,
 * publicado pelo boot, para não criar ciclo de import), com recuo para pt-BR.
 *
 * Data e hora com fuso e formato 12/24h continuam em `src/utils/time/timeFormatter.js`
 * (o relógio do sistema); `formatDate` e `formatDateTime` daqui são o atalho com o idioma
 * já escolhido. Catraca: `comportamento-tem-dono.spec.js` conta o `format*` escrito à mão.
 */
import {
  formatDate as dataNoFuso,
  formatDateTime as dataEHoraNoFuso,
  formatTime as horaNoFuso,
} from 'src/utils/time/timeFormatter'

export function idioma() {
  try {
    const l = globalThis.__ROS_I18N__?.global?.locale
    return (typeof l === 'string' ? l : l?.value) || 'pt-BR'
  } catch {
    return 'pt-BR'
  }
}

const cache = new Map()
const formatador = (Tipo, opcoes = {}) => {
  const chave = `${Tipo.name}|${idioma()}|${JSON.stringify(opcoes)}`
  if (!cache.has(chave)) cache.set(chave, new Tipo(idioma(), opcoes))
  return cache.get(chave)
}

const valido = (d) => {
  // `new Date(null)` é 1970, e "sem data" não pode virar 21:00 de 31/12/1969.
  if (d === null || d === undefined || d === '') return null
  const data = d instanceof Date ? d : new Date(d)
  return Number.isNaN(data.getTime()) ? null : data
}

/** 1234.5 → "1.234,5" (pt-BR), "1,234.5" (en-US). */
export function formatNumber(n, opcoes = {}) {
  const v = Number(n)
  return Number.isFinite(v) ? formatador(Intl.NumberFormat, opcoes).format(v) : ''
}

/** 0.256 → "26%". */
export function formatPercent(fracao, casas = 0) {
  return formatNumber(fracao, { style: 'percent', maximumFractionDigits: casas })
}

const UNIDADES = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']

/** 1536 → "1,5 KB". Base 1024, uma casa decimal por padrão, nunca "NaN undefined". */
export function formatBytes(bytes, casas = 1) {
  const n = Number(bytes)
  if (!Number.isFinite(n) || n <= 0) return `${formatNumber(0)} B`
  const i = Math.max(0, Math.min(Math.floor(Math.log(n) / Math.log(1024)), UNIDADES.length - 1))
  const valor = n / 1024 ** i
  return `${formatNumber(valor, { maximumFractionDigits: i === 0 ? 0 : casas })} ${UNIDADES[i]}`
}

/** Segundos de mídia → "3:07", "1:02:07". */
export function formatDuration(segundos) {
  // Stream ao vivo e áudio sem cabeçalho dão Infinity ou NaN: vira 0:00, nunca "Infinity:NaN".
  const n = Number(segundos)
  const total = Number.isFinite(n) ? Math.max(0, Math.floor(n)) : 0
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = String(total % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`
}

/**
 * Milissegundos de uso → "45 min", "2 h 30 min", "1.234 h" (Goal 75). É tempo de uso somado,
 * não duração de mídia: acima de um dia continua em horas, que é como se compara uso. Abaixo
 * de um minuto (e sem valor) é "0 min".
 */
export function formatTempoDeUso(ms) {
  const n = Number(ms)
  const minutos = Number.isFinite(n) ? Math.max(0, Math.floor(n / 60000)) : 0
  const horas = Math.floor(minutos / 60)
  const resto = minutos % 60
  const hora = (v) => formatNumber(v, { style: 'unit', unit: 'hour', unitDisplay: 'short' })
  const minuto = (v) => formatNumber(v, { style: 'unit', unit: 'minute', unitDisplay: 'short' })
  if (!horas) return minuto(resto)
  if (horas >= 100 || !resto) return hora(horas)
  return `${hora(horas)} ${minuto(resto)}`
}

/** "10 de out. de 2026" (pt-BR), "Oct 10, 2026" (en-US). `estilo`: short, medium, long, full. */
export function formatDate(data, estilo = 'medium') {
  const d = valido(data)
  return d ? dataNoFuso(d, { locale: idioma(), style: estilo }) : ''
}

/**
 * Um dia do calendário ('2026-10-10', como os resumos de uso guardam) → "10 de out.", e com
 * `semana` → "sáb., 10 de out." (Goal 75). O dia é montado no relógio de quem olha: um
 * `new Date('2026-10-10')` seria meia-noite UTC e cairia no dia 9 no Brasil.
 */
export function formatDiaCurto(dia, { semana = false } = {}) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dia || ''))
  if (!m) return ''
  const opcoes = { day: 'numeric', month: 'short', ...(semana ? { weekday: 'short' } : {}) }
  return formatador(Intl.DateTimeFormat, opcoes).format(new Date(+m[1], +m[2] - 1, +m[3]))
}

/**
 * O país pelo código ISO de duas letras (o `countryId` do GA4) → "Brasil", "Estados Unidos",
 * no idioma de quem usa. Código que não é de país ("(not set)", vazio) devolve null, para quem
 * chama escrever "país desconhecido" no idioma dele.
 */
export function formatPais(codigo) {
  const c = String(codigo || '').toUpperCase()
  if (!/^[A-Z]{2}$/.test(c)) return null
  try {
    return formatador(Intl.DisplayNames, { type: 'region' }).of(c) || c
  } catch {
    return c
  }
}

/** "10 de out. 14:30". */
export function formatDateTime(data) {
  const d = valido(data)
  return d ? dataEHoraNoFuso(d, { locale: idioma() }) : ''
}

/** "14:30" (ou "2:30 PM", conforme o idioma). */
export function formatTime(data, { segundos = false } = {}) {
  const d = valido(data)
  return d ? horaNoFuso(d, { locale: idioma(), showSeconds: segundos }) : ''
}

const DEGRAUS = [
  ['year', 365 * 24 * 3600],
  ['month', 30 * 24 * 3600],
  ['week', 7 * 24 * 3600],
  ['day', 24 * 3600],
  ['hour', 3600],
  ['minute', 60],
]

/** "há 2 dias", "em 3 horas", "agora". `agora` é parâmetro para o teste. */
export function formatRelativeTime(data, agora = Date.now()) {
  const d = valido(data)
  if (!d) return ''
  const segundos = Math.round((d.getTime() - agora) / 1000)
  const rtf = formatador(Intl.RelativeTimeFormat, { numeric: 'auto' })
  for (const [unidade, tamanho] of DEGRAUS) {
    if (Math.abs(segundos) >= tamanho) return rtf.format(Math.round(segundos / tamanho), unidade)
  }
  return rtf.format(0, 'second')
}
