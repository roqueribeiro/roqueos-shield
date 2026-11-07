<template>
  <div class="entrada">
    <ROSCard class="entrada__cartao">
      <div class="entrada__marca">
        <span class="entrada__logo"><q-icon name="security" size="26px" /></span>
        <div>
          <h1 class="entrada__titulo">RoqueShield</h1>
          <p class="entrada__sub">{{ t('shield.entrada.loginSub') }}</p>
        </div>
      </div>

      <div v-if="etapa === 'carregando'" class="entrada__estado" role="status">
        <ROSSpinner size="lg" />
        <span>{{ t('shield.entrada.carregando') }}</span>
      </div>

      <div v-else-if="etapa === 'sem-servidor'" class="entrada__estado" role="alert">
        <q-icon name="cloud_off" size="22px" />
        <span>{{ t('shield.entrada.semServidor') }}</span>
        <ROSButton variant="secondary" icon="refresh" @click="emit('tentar')">
          {{ t('shield.entrada.tentar') }}
        </ROSButton>
      </div>

      <form v-else class="entrada__form" novalidate @submit.prevent="enviar">
        <h2 class="entrada__h2">
          {{ etapa === 'setup' ? t('shield.entrada.setupTitulo') : t('shield.entrada.loginTitulo') }}
        </h2>
        <p v-if="etapa === 'setup'" class="entrada__dica">{{ t('shield.entrada.setupSub') }}</p>

        <ROSFormField
          v-model="email"
          type="email"
          name="email"
          autocomplete="username"
          :label="t('shield.entrada.email')"
        />
        <ROSFormField
          v-if="etapa === 'setup'"
          v-model="nome"
          name="name"
          autocomplete="name"
          :label="t('shield.entrada.nome')"
        />
        <ROSFormField
          v-model="senha"
          type="password"
          name="password"
          :autocomplete="etapa === 'setup' ? 'new-password' : 'current-password'"
          :label="t('shield.entrada.senha')"
        />
        <p v-if="etapa === 'setup'" class="entrada__dica">{{ t('shield.entrada.senhaDica') }}</p>
        <p v-if="erro" class="entrada__erro" role="alert">{{ erro }}</p>

        <ROSButton type="submit" variant="primary" block :loading="enviando" :disabled="!podeEnviar">
          {{ etapa === 'setup' ? t('shield.entrada.criar') : t('shield.entrada.entrar') }}
        </ROSButton>
      </form>

      <footer class="entrada__rodape">
        <span v-if="versao">{{ t('shield.entrada.versao', { v: versao }) }}</span>
        <a href="/docs" target="_blank" rel="noopener">{{ t('shield.entrada.api') }}</a>
      </footer>
    </ROSCard>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { post } from 'src/services/http'
import ROSCard from '../roqueos/ROSCard.vue'
import ROSButton from '../roqueos/ROSButton.vue'
import ROSFormField from '../roqueos/ROSFormField.vue'
import ROSSpinner from '../roqueos/ROSSpinner.vue'

const props = defineProps({
  etapa: { type: String, required: true },
  versao: { type: String, default: '' },
})
const emit = defineEmits(['entrou', 'tentar'])
const { t } = useI18n()

const email = ref('')
const nome = ref('')
const senha = ref('')
const erro = ref('')
const enviando = ref(false)

const podeEnviar = computed(
  () => email.value.includes('@') && (props.etapa === 'setup' ? senha.value.length >= 10 : !!senha.value),
)

async function enviar() {
  if (!podeEnviar.value || enviando.value) return
  enviando.value = true
  erro.value = ''
  try {
    const conta =
      props.etapa === 'setup'
        ? await post('/setup', { email: email.value, name: nome.value || null, password: senha.value })
        : await post('/auth/session', { email: email.value, password: senha.value })
    senha.value = ''
    emit('entrou', conta)
  } catch (e) {
    erro.value =
      e?.status === 401
        ? t('shield.entrada.erroLogin')
        : typeof e?.detail === 'string'
          ? e.detail
          : t('shield.entrada.erroGenerico')
  } finally {
    enviando.value = false
  }
}
</script>

<style scoped>
.entrada {
  flex: 1;
  display: grid;
  place-items: center;
  padding: var(--ros-space-6) var(--ros-space-4);
}
.entrada__cartao {
  width: min(440px, 100%);
  display: flex;
  flex-direction: column;
  gap: var(--ros-space-5);
}
.entrada__marca {
  display: flex;
  align-items: center;
  gap: var(--ros-space-3);
}
.entrada__logo {
  display: inline-grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: var(--ros-radius-lg);
  background: rgba(225, 29, 72, 0.16);
  color: #fb7185;
  flex-shrink: 0;
}
.entrada__titulo {
  margin: 0;
  font-size: var(--ros-text-xl);
  font-weight: 700;
  line-height: 1.2;
}
.entrada__sub,
.entrada__dica {
  margin: 0;
  color: var(--ros-text-muted);
  font-size: var(--ros-text-sm);
}
.entrada__h2 {
  margin: 0;
  font-size: var(--ros-text-lg);
  font-weight: 600;
}
.entrada__form {
  display: flex;
  flex-direction: column;
  gap: var(--ros-space-3);
}
.entrada__estado {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--ros-space-3);
  text-align: center;
  color: var(--ros-text-muted);
  padding: var(--ros-space-4) 0;
}
.entrada__erro {
  margin: 0;
  color: #fb7185;
  font-size: var(--ros-text-sm);
}
.entrada__rodape {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: var(--ros-space-2);
  font-size: var(--ros-text-xs);
  color: var(--ros-text-muted);
}
.entrada__rodape a {
  color: inherit;
}
</style>
