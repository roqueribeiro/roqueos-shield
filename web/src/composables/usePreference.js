import { effectScope, getCurrentScope, onScopeDispose, ref, watch } from 'vue'

/**
 * Uma preferência local do aparelho, reativa e guardada (Goal 65).
 *
 *   const colunas = usePreference('finder:colunas', 4)
 *
 * Era `localStorage.getItem` à mão em 36 arquivos, com três defeitos que se repetiam: o
 * `JSON.parse` sem `try` (um valor torto derrubava a tela), o acesso sem `try` (o Safari
 * em janela privada e o iframe sem armazenamento lançam), e o valor que não acompanhava
 * a outra aba. Aqui o valor torto vira o padrão, a escrita que falha fica só na memória,
 * e a outra aba avisa pelo evento `storage`.
 *
 * É preferência DO APARELHO. O que segue a conta (tema, papel de parede) mora nas
 * preferências do usuário no Firestore, não aqui.
 */
// Texto vai cru e o resto vai em JSON: é o formato que as chaves de antes já usavam
// (`localStorage.setItem('x__view', 'grade')`), então migrar uma tela não apaga a
// preferência de quem já tinha escolhido.
const ler = (chave, padrao, valido) => {
  try {
    const bruto = window.localStorage.getItem(chave)
    if (bruto === null) return padrao
    const valor = typeof padrao === 'string' ? bruto : JSON.parse(bruto)
    return !valido || valido(valor) ? valor : padrao
  } catch {
    return padrao
  }
}

const gravar = (chave, valor) => {
  try {
    if (valor === undefined) window.localStorage.removeItem(chave)
    else
      window.localStorage.setItem(chave, typeof valor === 'string' ? valor : JSON.stringify(valor))
  } catch {
    // Sem armazenamento (janela privada, iframe, cota cheia): o valor vive na memória.
  }
}

// UM ESTADO POR CHAVE NA ABA (revisão do Goal 69). Duas telas abertas com a mesma chave (duas
// janelas do Video Player, dois terminais) leem e gravam o MESMO ref. Com uma cópia por tela,
// a que gravava por último apagava o que a outra tinha gravado: o evento `storage` só chega
// às OUTRAS abas, então nenhuma das duas via a mudança da vizinha. A entrada guarda quem a
// usa e sai com o último (o listener da outra aba e o watch que grava saem junto).
const entradas = new Map()

// Cópia de quem chega de fora: o objeto de uma chamada solta não pode virar o mesmo objeto
// da entrada (mexer num mexeria no outro sem passar pelo watch de nenhum).
const copia = (v) => (v !== null && typeof v === 'object' ? JSON.parse(JSON.stringify(v)) : v)

// A entrada vive fora do componente que a criou (`effectScope` solto): se a primeira tela
// fecha e a segunda continua, o watch que grava continua com ela. O padrão e o `valido` são
// os de quem chegou primeiro; telas que dividem uma chave dividem também o que ela guarda.
function criarEntrada(chave, doPadrao, valido) {
  const escopo = effectScope(true)
  const valor = ref(ler(chave, doPadrao(), valido))
  // O que veio de fora (a outra aba, ou uma chamada solta nesta) já está guardado: gravar de
  // volta recriaria a chave que ela acabou de apagar. O watch é síncrono para a marca valer
  // só para esta troca.
  let deFora = false
  const receber = (novo) => {
    deFora = true
    valor.value = novo
    deFora = false
  }
  escopo.run(() =>
    watch(
      valor,
      (v) => {
        if (!deFora) gravar(chave, v)
      },
      { deep: true, flush: 'sync' },
    ),
  )
  const daOutraAba = (e) => {
    if (e.key !== chave) return
    receber(e.newValue === null ? doPadrao() : ler(chave, doPadrao(), valido))
  }
  window.addEventListener('storage', daOutraAba)
  return {
    valor,
    usuarios: 0,
    // A chamada solta gravou: a entrada passa a valer o mesmo, sem gravar de novo.
    daChamadaSolta: (v) => receber(v === undefined ? doPadrao() : copia(v)),
    desligar: () => {
      escopo.stop()
      window.removeEventListener('storage', daOutraAba)
    },
  }
}

// Fora de um componente não há quem remova o listener, nem quem diga quando sair: a chamada
// solta tem o seu ref (num laço, acumularia um listener por volta). O que ela grava chega à
// entrada viva da mesma chave, se houver, para a tela aberta não gravar por cima depois.
function avulsa(chave, doPadrao, valido) {
  const valor = ref(typeof window === 'undefined' ? doPadrao() : ler(chave, doPadrao(), valido))
  watch(
    valor,
    (v) => {
      gravar(chave, v)
      entradas.get(chave)?.daChamadaSolta(v)
    },
    { deep: true, flush: 'sync' },
  )
  return valor
}

/**
 * @param {string} chave
 * @param {*} padrao valor sem nada guardado (o tipo dele decide se guarda cru ou em JSON)
 * @param {{ valido?: (v: any) => boolean }} [opcoes] o guardado que não passa vira o padrão
 */
export function usePreference(chave, padrao, { valido } = {}) {
  // Cópia do padrão a cada uso: mexer em `valor.value.x` não pode alterar o objeto que a
  // tela passou, senão "voltar ao padrão" volta para o que foi mexido.
  const doPadrao = () =>
    padrao !== null && typeof padrao === 'object' ? JSON.parse(JSON.stringify(padrao)) : padrao
  if (typeof window === 'undefined' || !getCurrentScope()) return avulsa(chave, doPadrao, valido)

  let entrada = entradas.get(chave)
  if (!entrada) {
    entrada = criarEntrada(chave, doPadrao, valido)
    entradas.set(chave, entrada)
  }
  entrada.usuarios++
  onScopeDispose(() => {
    if (--entrada.usuarios > 0) return
    entrada.desligar()
    entradas.delete(chave)
  })
  return entrada.valor
}
