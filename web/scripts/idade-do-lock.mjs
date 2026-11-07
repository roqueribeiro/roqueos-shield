// Idade mínima do lockfile da tela: nenhuma versão resolvida pode ter menos de 14 dias
// no registry. Versão recém-publicada é a janela de ataque de supply chain (pacote
// sequestrado costuma ser despublicado em dias). Medido em 2026-11-06: o lock gerado
// naquela noite trazia 68 versões com menos de 14 dias, entre elas sass e rollup
// publicados horas antes; os pins ficam em `resolutions` do package.json.
//
//   node scripts/idade-do-lock.mjs [yarn.lock]
//
// Alias `npm:` (string-width-cjs etc.) não tem entrada própria no registry e é listado
// à parte, sem reprovar.
import { readFileSync } from 'node:fs'
const lock = readFileSync(process.argv[2] || 'yarn.lock', 'utf8')
const pares = new Set()
for (const bloco of lock.split('\n\n')) {
  const cab = bloco.split('\n').find((l) => l && !l.startsWith('#') && !l.startsWith(' '))
  const ver = bloco.match(/\n  version "([^"]+)"/)
  if (!cab || !ver) continue
  const primeiro = cab.replace(/^"/, '').split(/,\s*/)[0].replace(/"/g, '')
  const nome = primeiro.slice(0, primeiro.lastIndexOf('@'))
  pares.add(`${nome}@@${ver[1]}`)
}
const agora = Date.now()
const LIMITE = 14 * 864e5
const lista = [...pares]
const novos = []
const faltando = []
let i = 0
async function trabalhador() {
  while (i < lista.length) {
    const [nome, ver] = lista[i++].split('@@')
    try {
      const r = await fetch(`https://registry.yarnpkg.com/${nome.replace('/', '%2f')}`, {
        headers: { Accept: 'application/json' },
      })
      const j = await r.json()
      const t = j.time?.[ver]
      if (!t) faltando.push(`${nome}@${ver}`)
      else if (agora - Date.parse(t) < LIMITE) novos.push(`${nome}@${ver} ${t.slice(0, 10)}`)
    } catch (e) {
      faltando.push(`${nome}@${ver} (${e.message})`)
    }
  }
}
await Promise.all(Array.from({ length: 16 }, trabalhador))
console.log(`pacotes: ${lista.length}`)
console.log(`publicados há menos de 14 dias: ${novos.length}`)
novos.forEach((n) => console.log('  ' + n))
console.log(`sem data no registry: ${faltando.length}`)
faltando.forEach((n) => console.log('  ' + n))
if (novos.length) process.exitCode = 1
