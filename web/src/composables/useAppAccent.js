// Só o `resolveAccent` do RoqueOS: a tela standalone tem um app só, com o accent dele.
const FALLBACK = { hex: '#007aff', rgb: '0, 122, 255' }

export function resolveAccent(hex) {
  if (!hex || typeof hex !== 'string') return FALLBACK
  const m = hex
    .trim()
    .replace(/^#/, '')
    .match(/^([0-9a-fA-F]{6})$/)
  if (!m) return FALLBACK
  const int = parseInt(m[1], 16)
  const r = (int >> 16) & 255
  const g = (int >> 8) & 255
  const b = int & 255
  const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
  if (lum > 0.82 || lum < 0.12) return FALLBACK
  return { hex: `#${m[1].toLowerCase()}`, rgb: `${r}, ${g}, ${b}` }
}
