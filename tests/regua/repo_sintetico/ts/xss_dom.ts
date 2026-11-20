export function mostrarNome(): void {
  const alvo = document.getElementById('nome') as HTMLElement
  alvo.innerHTML = decodeURIComponent(window.location.hash.slice(1))
}
