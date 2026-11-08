/* Fonte do styles.css do dashboard antigo em /ui.
 *
 * Antes o Tailwind vinha do play-cdn (cdn.tailwindcss.com), que compila as classes no
 * navegador e por isso exige script de terceiro e 'unsafe-eval'. Agora o CSS sai
 * pronto daqui e é servido do mesmo endereço, sob o CSP estrito do /ui.
 *
 * Regenerar depois de mexer em classe no HTML ou no app.js (yarn, nunca npm):
 *
 *   mkdir -p /tmp/tw && cd /tmp/tw && yarn add --exact tailwindcss@3.4.19
 *   /tmp/tw/node_modules/.bin/tailwindcss \
 *     -c <repo>/orchestrator/static/tailwind/tailwind.config.cjs \
 *     -i <repo>/orchestrator/static/tailwind/input.css \
 *     -o <repo>/orchestrator/static/styles.css --minify
 *
 * tests/unit/test_w4_ui_csp.py confere que toda classe estática do HTML existe no
 * styles.css: classe nova sem regenerar reprova.
 */
const path = require('path')
const raiz = path.join(__dirname, '..')

module.exports = {
  darkMode: 'class',
  content: [
    path.join(raiz, 'index.html'),
    path.join(raiz, 'cockpit.html'),
    path.join(raiz, 'app.js'),
  ],
  theme: {
    extend: {
      colors: {
        bg: '#0b1220', panel: '#111a2c', border: '#1e293b',
        accent: '#3b82f6', accent2: '#8b5cf6',
        ok: '#10b981', warn: '#f59e0b', down: '#ef4444', muted: '#64748b',
      },
    },
  },
  plugins: [],
}
