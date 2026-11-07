// O Quasar exige um roteador. A tela do RoqueShield navega por estado (seções e
// abas), como no RoqueOS, então ele tem uma rota só e não desenha nada.
import { defineRouter } from '#q-app/wrappers'
import { createRouter, createWebHashHistory } from 'vue-router'
// Antes do roteador existir: ele é por hash e normaliza o `#setup=` do instalador.
import 'src/services/codigoDeSetup'

export default defineRouter(() =>
  createRouter({
    history: createWebHashHistory(),
    routes: [{ path: '/:qualquer(.*)*', component: { render: () => null } }],
  }),
)
