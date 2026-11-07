<template>
  <div class="ros-empty" :class="{ 'ros-empty--sm': size === 'sm' }">
    <div v-if="icon" class="ros-empty__icone" aria-hidden="true">
      <q-icon :name="icon" :size="size === 'sm' ? '22px' : '28px'" />
    </div>
    <p class="ros-empty__titulo">{{ title }}</p>
    <p v-if="description" class="ros-empty__texto">{{ description }}</p>
    <div v-if="$slots.actions" class="ros-empty__acoes">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup>
// O estado vazio do sistema (Goal 63): ícone num ladrilho na cor do app, título, uma
// frase e, quase sempre, uma saída. Os apps tinham onze versões, de ícone cinza de
// 80px sozinho a "Nenhum item." em texto miúdo, e a maioria sem ação. A ação é um
// slot para que oferecer uma custe uma linha: lista vazia sem saída diz "você não
// tem nada" e deixa a pessoa ali. Para o app inteiro vazio, o ROSAppLoader continua.
defineProps({
  icon: { type: String, default: 'inbox' },
  title: { type: String, required: true },
  description: { type: String, default: '' },
  size: { type: String, default: 'md', validator: (v) => ['sm', 'md'].includes(v) },
})
</script>
