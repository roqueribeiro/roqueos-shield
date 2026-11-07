<template>
  <div class="shield-app">
    <TelaEntrada
      v-if="etapa !== 'app'"
      :etapa="etapa"
      :versao="versao"
      @entrou="entrou"
      @tentar="iniciar"
    />
    <ROSPentest v-else :conta="conta" @sair="sair" />
  </div>
</template>

<script setup>
/**
 * A casca do standalone: decide entre o primeiro uso, o login e a tela do
 * RoqueShield. No RoqueOS quem faz isso é o próprio sistema (login do RoqueOS,
 * janela do app); aqui o shield é o sistema inteiro.
 */
import { onMounted, onUnmounted, ref } from 'vue'
import ROSPentest from 'src/components/roqueos/apps/ROSPentest.vue'
import TelaEntrada from 'src/components/shield/TelaEntrada.vue'
import { aoPerderSessao, del, get } from 'src/services/http'

const etapa = ref('carregando') // carregando | sem-servidor | setup | login | app
const versao = ref('')
const conta = ref(null)

async function iniciar() {
  etapa.value = 'carregando'
  try {
    const s = await get('/setup')
    versao.value = s.version
    if (s.needs_setup) {
      etapa.value = 'setup'
      return
    }
  } catch {
    etapa.value = 'sem-servidor'
    return
  }
  try {
    conta.value = await get('/auth/session')
    etapa.value = 'app'
  } catch {
    etapa.value = 'login'
  }
}

function entrou(c) {
  conta.value = c
  etapa.value = 'app'
}

async function sair() {
  await del('/auth/session').catch(() => {})
  conta.value = null
  etapa.value = 'login'
}

let pararDeOuvir = null
onMounted(() => {
  // Sessão expirou no meio do uso: volta para o login em vez de mostrar erro em cada aba.
  pararDeOuvir = aoPerderSessao(() => {
    if (etapa.value === 'app') {
      conta.value = null
      etapa.value = 'login'
    }
  })
  iniciar()
})
onUnmounted(() => pararDeOuvir?.())
</script>

<style>
.shield-app {
  height: 100vh;
  height: 100dvh;
  display: flex;
  flex-direction: column;
}
.shield-app > .ros-pentest {
  flex: 1;
  min-height: 0;
}
</style>
