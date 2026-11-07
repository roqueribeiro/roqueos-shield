/**
 * Utility to open external URLs safely across platforms.
 *
 * The hard case is Capacitor (mobile): the WebView serving the RoqueOS
 * frontend has the same origin as the host page (https://roqueos.com.br),
 * so calling window.open(url) keeps the URL inside the WebView. For an
 * `http://192.168.x.x:PORT` LAN target, the browser blocks it as mixed
 * content and renders a blank screen the user can't escape — they're
 * stuck and have to kill the app.
 *
 * The native wrapper (roqueos-mobile) exposes
 * `window.RoqueOSNative.openExternal(url)` which delegates to the
 * Capacitor Browser plugin (Chrome Custom Tabs on Android,
 * SFSafariViewController on iOS) — that's the only reliable way to
 * pop out of the WebView and into the system browser.
 *
 * On the Electron wrapper, `window.electronAPI.openExternal(url)` does
 * the equivalent (BrowserWindow → shell.openExternal).
 *
 * Order of preference:
 *   1. Native bridge (Capacitor / Electron) — proper system browser.
 *   2. window.open(url, '_blank') — works on PWA / regular web.
 *   3. <a target="_blank"> + click — last-resort fallback for popup
 *      blockers and old WebViews.
 */

/**
 * Check if running inside Capacitor native app
 */
export function isCapacitorNative() {
  return !!(
    window.Capacitor &&
    window.Capacitor.isNativePlatform &&
    window.Capacitor.isNativePlatform()
  )
}

/**
 * Check if running inside Electron wrapper
 */
export function isElectron() {
  return !!window.electronAPI?.isElectron
}

/**
 * Open URL in the system's default browser.
 * Returns true if a native bridge was used, false if a fallback ran.
 */
export async function openExternalUrl(url) {
  if (!url) return false

  // 0. Esquema PRÓPRIO de outro app (`cadentia://`, `whatsapp://`, `tel:`).
  //
  // Isto não é navegação web e não pode ir para a ponte: tanto o
  // `RoqueOSNative.openExternal` quanto o plugin Browser abrem um
  // SFSafariViewController (iOS) ou Custom Tab (Android), que são NAVEGADORES.
  // Eles entendem http(s) e engolem um esquema próprio sem erro nenhum, então
  // o "Voltar ao Cadentia" ficava sem fazer nada e sem nada no console.
  //
  // Navegar direto resolve nos dois mundos: dentro do app a navegação cai no
  // `decidePolicyFor` do wrapper, que já entrega ao sistema via
  // `UIApplication.shared.open`; num navegador comum o próprio iOS/Android
  // resolve o esquema (o iOS pergunta antes, que é o certo).
  //
  // Electron fica de fora porque o `shell.openExternal` dele já trata esquema
  // próprio corretamente, e lá `window.location` sairia da janela do app.
  if (!/^https?:/i.test(url) && !isElectron()) {
    window.location.href = url
    return true
  }

  // 1. Native bridge — preferred path. The bridge knows how to escape
  // the WebView; window.open does not on Capacitor.
  //
  // Each native branch ALWAYS returns. Without an explicit return on
  // the failure path the function falls through to step 4 (window.open)
  // AND step 5 (anchor click), which on desktop browsers opens TWO
  // tabs for one user click. Returning `true` on attempt acknowledges
  // we tried; the bridge is the authoritative path on its platform.
  const bridge = window.RoqueOSNative
  if (bridge && typeof bridge.openExternal === 'function') {
    try {
      const result = await bridge.openExternal(url)
      if (result !== false) return true
    } catch (err) {
      console.warn('[openExternal] RoqueOSNative.openExternal failed:', err)
    }
    return false
  }

  // 2. Electron wrapper — uses shell.openExternal under the hood.
  if (isElectron() && typeof window.electronAPI?.openExternal === 'function') {
    try {
      await window.electronAPI.openExternal(url)
      return true
    } catch (err) {
      console.warn('[openExternal] electronAPI.openExternal failed:', err)
    }
    return false
  }

  // 3. Capacitor without a bridge override — try the plugin directly.
  // This shouldn't normally happen (the wrapper always exposes the
  // bridge) but covers the case where the front loads in a Capacitor
  // shell that didn't run exposeNativeAPI yet.
  if (isCapacitorNative() && window.Capacitor?.Plugins?.Browser?.open) {
    try {
      await window.Capacitor.Plugins.Browser.open({ url })
      return true
    } catch (err) {
      console.warn('[openExternal] Capacitor Browser plugin failed:', err)
    }
    return false
  }

  // 4. Web fallback — synthetic anchor click with target="_blank", tried FIRST.
  // `window.open` is silently blocked in iOS standalone PWAs (display-mode:
  // standalone) even from a real user gesture — it returns without opening and
  // without throwing, so the user taps "open" and nothing happens. A real
  // anchor click reliably hands off to the system browser there (and opens a
  // single tab on desktop too). This is the dependable cross-platform path.
  try {
    const link = document.createElement('a')
    link.href = url
    link.target = '_blank'
    link.rel = 'noopener noreferrer'
    document.body.appendChild(link)
    link.click()
    // `link.remove()` is a no-op if the node was already detached — removeChild
    // throws NotFoundError in that case (e.g. the document was reset before this
    // deferred cleanup ran), surfacing as an unhandled error in the test runner.
    setTimeout(() => link.remove(), 100)
    return false
  } catch (err) {
    console.warn('[openExternal] anchor open failed, trying window.open:', err)
  }

  // 5. Last resort: window.open (covers environments where synthetic anchor
  // clicks are blocked but window.open is allowed).
  try {
    window.open(url, '_blank', 'noopener,noreferrer')
  } catch (err) {
    console.warn('[openExternal] window.open threw:', err)
  }
  return false
}
