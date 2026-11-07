// O Quasar exige um roteador. A tela do RoqueShield navega por estado (seções e
// abas), como no RoqueOS, então ele tem uma rota só e não desenha nada.
import { defineRouter } from '#q-app/wrappers'
import { createRouter, createWebHashHistory } from 'vue-router'

export default defineRouter(() =>
  createRouter({
    history: createWebHashHistory(),
    routes: [{ path: '/:qualquer(.*)*', component: { render: () => null } }],
  }),
)
