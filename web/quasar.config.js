// Tela do RoqueShield standalone. SPA servida pelo FastAPI do shield em `/`; a API
// mora no mesmo endereço, então não há CORS nem token no navegador (cookie de sessão).
import { defineConfig } from '#q-app/wrappers'

export default defineConfig(() => ({
  boot: ['i18n'],
  css: ['app.scss'],
  extras: ['material-icons'],
  build: {
    target: { browser: ['es2022', 'firefox115', 'chrome115', 'safari14'], node: 'node22' },
    vueRouterMode: 'hash',
    sourcemap: false,
    distDir: '../orchestrator/web_dist',
    publicPath: '/',
  },
  devServer: {
    port: 9100,
    open: false,
    // Em dev o shield roda em :8080; o Vite repassa a API para lá.
    proxy: Object.fromEntries(
      ['/setup', '/auth', '/settings', '/system', '/scans', '/targets', '/findings', '/reports', '/ui/api', '/users', '/health', '/investigate', '/exposure'].map(
        (p) => [p, { target: 'http://127.0.0.1:8080', changeOrigin: false }],
      ),
    ),
  },
  framework: {
    config: { dark: true },
    plugins: ['Notify', 'Dialog'],
  },
}))
