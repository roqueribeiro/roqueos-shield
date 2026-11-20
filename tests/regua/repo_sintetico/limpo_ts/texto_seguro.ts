export function mostrarNome(nome: string): void {
  const alvo = document.getElementById('nome') as HTMLElement
  alvo.textContent = nome
}
