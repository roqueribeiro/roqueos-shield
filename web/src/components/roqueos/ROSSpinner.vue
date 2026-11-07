<template>
  <span
    class="ros-spinner"
    :class="[size !== 'md' && `ros-spinner--${size}`, { 'ros-spinner--herda': herda }]"
    role="status"
    :aria-label="label || $t('common.loading')"
  >
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle class="ros-spinner__trilha" cx="12" cy="12" r="9" />
      <circle class="ros-spinner__arco" cx="12" cy="12" r="9" />
    </svg>
  </span>
</template>

<script setup>
// O "carregando" do sistema (Goal 63). No lugar dos quatro `q-spinner*` em seis cores
// e de cada app escolhendo o seu, um anel só, na cor do accent do app (ou do texto,
// dentro de um botão), com `role="status"` para o leitor de tela anunciar.
defineProps({
  // sm 16px (dentro de botão e de linha), md 20px, lg 32px (área vazia carregando).
  size: { type: String, default: 'md', validator: (v) => ['sm', 'md', 'lg'].includes(v) },
  // O que o leitor de tela diz. Sem ele, "Carregando...".
  label: { type: String, default: '' },
  // Usa a cor do texto em volta em vez do accent (botão, chip).
  herda: { type: Boolean, default: false },
})
</script>
