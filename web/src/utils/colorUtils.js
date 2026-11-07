/**
 * Small hex-colour helpers shared across the UI.
 *
 * IMPORTANT (Safari 14 — an explicit build target in quasar.config.js): CSS
 * `color-mix()` is NOT supported until Safari 16.2, so any tint/shade that must
 * render on the supported matrix has to be produced as a concrete `rgba()`.
 * `hexToRgbTriplet` returns the "r, g, b" string to feed a CSS var consumed as
 * `rgba(var(--x-rgb), 0.4)`.
 */

const FALLBACK = '#666666'

const parseHex = (color) => {
  let hex = String(color || FALLBACK).replace('#', '')
  // Expand shorthand (#abc → #aabbcc).
  if (hex.length === 3) {
    hex = hex
      .split('')
      .map((c) => c + c)
      .join('')
  }
  const num = Number.parseInt(hex, 16)
  if (hex.length !== 6 || Number.isNaN(num)) return null
  return {
    r: (num >> 16) & 0xff,
    g: (num >> 8) & 0xff,
    b: num & 0xff,
  }
}

/**
 * Deterministic, pleasant hex colour from an arbitrary string (app name) — used
 * for premium fallback icon tiles so each app gets its own consistent hue
 * instead of a flat gray. Saturated/medium-lightness so a white glyph reads on top.
 */
export const colorFromString = (str) => {
  const s = String(str || '')
  let hash = 0
  for (let i = 0; i < s.length; i++) hash = (s.charCodeAt(i) + ((hash << 5) - hash)) | 0
  const hue = Math.abs(hash) % 360
  // HSL(hue, 58%, 48%) → hex
  const h = hue / 360
  const sat = 0.58
  const lig = 0.48
  const hue2rgb = (p, q, t) => {
    if (t < 0) t += 1
    if (t > 1) t -= 1
    if (t < 1 / 6) return p + (q - p) * 6 * t
    if (t < 1 / 2) return q
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6
    return p
  }
  const q = lig < 0.5 ? lig * (1 + sat) : lig + sat - lig * sat
  const p = 2 * lig - q
  const r = Math.round(hue2rgb(p, q, h + 1 / 3) * 255)
  const g = Math.round(hue2rgb(p, q, h) * 255)
  const b = Math.round(hue2rgb(p, q, h - 1 / 3) * 255)
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`
}

/** "#5856d6" → "88, 86, 214" — for `rgba(var(--x-rgb), alpha)`. */
export const hexToRgbTriplet = (color) => {
  const rgb = parseHex(color)
  if (!rgb) return '102, 102, 102'
  return `${rgb.r}, ${rgb.g}, ${rgb.b}`
}

/** Darken (amount > 0) or lighten (amount < 0) a hex colour by a flat amount. */
export const shadeHex = (color, amount) => {
  const rgb = parseHex(color)
  if (!rgb) return FALLBACK
  const clamp = (v) => Math.min(255, Math.max(0, v - amount))
  const r = clamp(rgb.r)
  const g = clamp(rgb.g)
  const b = clamp(rgb.b)
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`
}

/** Darken a hex colour (alias — positive amount = darker). */
export const darkenHex = (color, amount) => shadeHex(color, Math.abs(amount))

/** Lighten a hex colour (positive amount = lighter). */
export const lightenHex = (color, amount) => shadeHex(color, -Math.abs(amount))

const luminancia = ({ r, g, b }) => {
  const canal = (v) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)
}

/** Contraste WCAG entre duas cores {r, g, b}. */
export const contraste = (a, b) => {
  const [l1, l2] = [luminancia(a), luminancia(b)].sort((x, y) => y - x)
  return (l1 + 0.05) / (l2 + 0.05)
}

// A superfície escura de referência do sistema (o vidro do tema padrão).
const SUPERFICIE = { r: 30, g: 30, b: 30 }
const BRANCO = { r: 255, g: 255, b: 255 }
const PRETO = { r: 0, g: 0, b: 0 }

const mistura = (a, b, t) => ({
  r: Math.round(a.r + (b.r - a.r) * t),
  g: Math.round(a.g + (b.g - a.g) * t),
  b: Math.round(a.b + (b.b - a.b) * t),
})

/**
 * O accent do app como custom property da janela (Goal 63): a cor dele em tripla, e
 * uma versão clara o bastante para ser TEXTO sobre o vidro escuro (4,5:1 ou mais).
 * Branco sobre o accent reprova o contraste em todos os temas, então a cor do app
 * entra como tinta de fundo e como texto clareado, e como fundo cheio com texto branco
 * só na versão escurecida (`--ros-app-accent-fill-rgb`). Cor quase branca, quase preta ou cinza (RoqueClaw, Terminal, os apps de
 * sistema em #6b7280) não vira accent: devolve {} e a janela fica com o do tema.
 */
export const estiloDoAccent = (cor) => {
  const rgb = cor ? parseHex(cor) : null
  if (!rgb) return {}
  const lum = luminancia(rgb)
  const croma = Math.max(rgb.r, rgb.g, rgb.b) - Math.min(rgb.r, rgb.g, rgb.b)
  if (lum > 0.82 || lum < 0.03 || croma < 24) return {}
  // O pior fundo em que esse texto aparece é o próprio accent a 24% sobre o vidro (o
  // botão `accent` no hover, a aba ativa tingida). Medido contra o vidro puro, o roxo
  // do App Maker dava 4,24:1 no botão: passava na régua e reprovava na tela.
  const fundo = mistura(SUPERFICIE, rgb, 0.24)
  let texto = rgb
  for (let passo = 0.05; contraste(texto, fundo) < 4.5 && passo <= 1; passo += 0.05) {
    texto = mistura(rgb, BRANCO, passo)
  }
  // E o accent como fundo cheio com texto branco (a aba ativa da pílula, Goal 71): a cor
  // escurecida só o necessário para o branco dar 4,5:1. O ciano do Chat dava 2,4.
  let cheio = rgb
  for (let passo = 0.05; contraste(BRANCO, cheio) < 4.5 && passo <= 1; passo += 0.05) {
    cheio = mistura(rgb, PRETO, passo)
  }
  return {
    '--ros-app-accent-rgb': `${rgb.r}, ${rgb.g}, ${rgb.b}`,
    '--ros-app-accent-text-rgb': `${texto.r}, ${texto.g}, ${texto.b}`,
    '--ros-app-accent-fill-rgb': `${cheio.r}, ${cheio.g}, ${cheio.b}`,
  }
}
