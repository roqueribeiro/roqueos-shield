<template>
  <section class="ros-pentest__pane ros-pentest__ajustes usuarios">
    <header class="usuarios__cab">
      <div>
        <h3>{{ t('shield.usuarios.titulo') }}</h3>
        <p>{{ t('shield.usuarios.intro') }}</p>
      </div>
      <ROSButton variant="accent" icon="person_add" @click="abrirCriacao">
        {{ t('shield.usuarios.novo') }}
      </ROSButton>
    </header>

    <div v-if="carregando" class="usuarios__estado" role="status">
      <ROSSpinner />
    </div>
    <p v-else-if="erroDaLista" class="usuarios__erro" role="alert">{{ erroDaLista }}</p>

    <ul v-else class="usuarios__lista" :aria-label="t('shield.usuarios.titulo')">
      <li
        v-for="u in usuarios"
        :key="u.id"
        class="usuarios__item"
        :class="{ 'usuarios__item--inativo': !u.active }"
      >
        <div class="usuarios__quem">
          <span class="usuarios__avatar" aria-hidden="true"><q-icon name="person" size="18px" /></span>
          <div class="usuarios__nomes">
            <span class="usuarios__nome">{{ u.name || u.email }}</span>
            <span v-if="u.name" class="usuarios__email">{{ u.email }}</span>
            <span class="usuarios__marcas">
              <ROSBadge v-if="u.id === conta?.id" size="sm" tone="accent" :label="t('shield.usuarios.voce')" />
              <ROSBadge v-if="!u.active" size="sm" tone="danger" :label="t('shield.usuarios.inativo')" />
              <ROSBadge
                size="sm"
                :tone="u.has_password ? 'success' : 'neutral'"
                :icon="u.has_password ? 'password' : 'key'"
                :label="u.has_password ? t('shield.usuarios.comSenha') : t('shield.usuarios.soToken')"
              />
            </span>
          </div>
        </div>

        <div class="usuarios__acoes">
          <ROSSelectField
            inline
            class="usuarios__papel"
            :model-value="u.role"
            :options="opcoesDePapel"
            :disabled="!u.active || ocupado === u.id"
            :aria-label="t('shield.usuarios.papel')"
            @update:model-value="(p) => mudarPapel(u, p)"
          />
          <ROSIconButton
            icon="password"
            :label="t('shield.usuarios.definirSenha')"
            :disabled="!u.active"
            @click="abrirSenha(u)"
          />
          <ROSIconButton
            icon="autorenew"
            :label="t('shield.usuarios.girarToken')"
            :disabled="!u.active"
            @click="girarToken(u)"
          />
          <ROSIconButton
            icon="person_off"
            danger
            :label="t('shield.usuarios.desativar')"
            :disabled="!u.active || u.id === conta?.id"
            @click="desativar(u)"
          />
        </div>
      </li>
    </ul>

    <p class="usuarios__nota">
      <q-icon name="info" size="16px" />
      <span>{{ t('shield.usuarios.notaToken') }}</span>
    </p>

    <!-- Criar -->
    <ROSModal v-model="criando" :title="t('shield.usuarios.novo')" icon="person_add" size="sm">
      <form id="form-novo-usuario" class="usuarios__form" novalidate @submit.prevent="criar">
        <ROSFormField v-model="novo.email" type="email" name="email" autocomplete="off" :label="t('shield.entrada.email')" />
        <ROSFormField v-model="novo.name" name="name" autocomplete="off" :label="t('shield.entrada.nome')" />
        <ROSSelectField v-model="novo.role" :options="opcoesDePapel" :label="t('shield.usuarios.papel')" />
        <ROSFormField
          v-model="novo.password"
          type="password"
          name="new-password"
          autocomplete="new-password"
          :label="t('shield.usuarios.senhaOpcional')"
        />
        <p class="usuarios__dica">{{ t('shield.usuarios.senhaOpcionalDica') }}</p>
        <p v-if="erroDoForm" class="usuarios__erro" role="alert">{{ erroDoForm }}</p>
      </form>
      <template #footer>
        <ROSButton variant="ghost" @click="criando = false">{{ t('common.cancel') }}</ROSButton>
        <ROSButton
          type="submit"
          form="form-novo-usuario"
          variant="primary"
          icon="check"
          :loading="enviando"
          :disabled="!novo.email.trim()"
        >
          {{ t('shield.usuarios.criar') }}
        </ROSButton>
      </template>
    </ROSModal>

    <!-- Senha -->
    <ROSModal
      v-model="trocandoSenha"
      :title="t('shield.usuarios.definirSenha')"
      :subtitle="alvoDaSenha?.email"
      icon="password"
      size="sm"
    >
      <form id="form-senha" class="usuarios__form" novalidate @submit.prevent="salvarSenha">
        <ROSFormField
          v-model="senhaNova"
          type="password"
          name="new-password"
          autocomplete="new-password"
          :label="t('shield.entrada.senha')"
        />
        <p class="usuarios__dica">{{ t('shield.entrada.senhaDica') }}</p>
        <p v-if="erroDoForm" class="usuarios__erro" role="alert">{{ erroDoForm }}</p>
      </form>
      <template #footer>
        <ROSButton variant="ghost" @click="trocandoSenha = false">{{ t('common.cancel') }}</ROSButton>
        <ROSButton type="submit" form="form-senha" variant="primary" icon="check" :loading="enviando" :disabled="!senhaNova">
          {{ t('shield.usuarios.salvarSenha') }}
        </ROSButton>
      </template>
    </ROSModal>

    <!-- Token, mostrado uma vez -->
    <ROSModal
      v-model="mostrandoToken"
      :title="t('shield.usuarios.tokenTitulo')"
      :subtitle="tokenDe"
      icon="key"
      variant="warning"
      size="sm"
      @closed="token = ''"
    >
      <p class="usuarios__dica">{{ t('shield.usuarios.tokenUmaVez') }}</p>
      <div class="usuarios__token">
        <code class="usuarios__token-txt">{{ token }}</code>
        <ROSIconButton icon="content_copy" variant="tonal" :label="t('shield.usuarios.copiar')" @click="copiar" />
      </div>
      <p class="usuarios__dica">{{ t('shield.usuarios.tokenUso') }}</p>
      <template #footer>
        <ROSButton variant="primary" @click="mostrandoToken = false">{{ t('shield.usuarios.guardei') }}</ROSButton>
      </template>
    </ROSModal>
  </section>
</template>

<script setup>
/**
 * Usuários do standalone. No RoqueOS quem cuida de conta é o próprio sistema; aqui o
 * shield é o sistema inteiro, então alguém precisa criar o operador do CI e girar o
 * token dele. Só o admin vê esta seção (a API exige users:manage de qualquer jeito).
 *
 * O token aparece uma vez, no modal, e some quando ele fecha: a API guarda só o hash.
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Notify } from 'quasar'
import { get, patch, post, put } from 'src/services/http'
import { confirmar } from 'src/composables/useConfirm'
import ROSBadge from 'src/components/roqueos/ROSBadge.vue'
import ROSButton from 'src/components/roqueos/ROSButton.vue'
import ROSFormField from 'src/components/roqueos/ROSFormField.vue'
import ROSIconButton from 'src/components/roqueos/ROSIconButton.vue'
import ROSModal from 'src/components/roqueos/ROSModal.vue'
import ROSSelectField from 'src/components/roqueos/ROSSelectField.vue'
import ROSSpinner from 'src/components/roqueos/ROSSpinner.vue'

defineProps({ conta: { type: Object, default: null } })

const { t } = useI18n()
const PAPEIS = ['admin', 'operator', 'auditor', 'viewer']
const opcoesDePapel = computed(() =>
  PAPEIS.map((p) => ({ value: p, label: t(`shield.usuarios.papeis.${p}`) })),
)

const usuarios = ref([])
const carregando = ref(true)
const erroDaLista = ref('')
const ocupado = ref(null)
const enviando = ref(false)
const erroDoForm = ref('')

const criando = ref(false)
const novo = reactive({ email: '', name: '', role: 'operator', password: '' })

const trocandoSenha = ref(false)
const alvoDaSenha = ref(null)
const senhaNova = ref('')

const mostrandoToken = ref(false)
const token = ref('')
const tokenDe = ref('')

function mensagem(e) {
  // O 409 de papel e desativação é sempre a trava do último admin; o texto da API é
  // só em português, então a tela usa o dela.
  if (e?.status === 409 && /admin/.test(String(e.detail))) return t('shield.usuarios.notaToken')
  return typeof e?.detail === 'string' ? e.detail : t('shield.entrada.erroGenerico')
}
function avisar(msg, tipo = 'positive') {
  Notify.create({ type: tipo, message: msg, position: 'top' })
}

async function carregar() {
  carregando.value = true
  erroDaLista.value = ''
  try {
    usuarios.value = await get('/users')
  } catch (e) {
    erroDaLista.value = mensagem(e)
  } finally {
    carregando.value = false
  }
}

function trocar(atualizado) {
  usuarios.value = usuarios.value.map((u) => (u.id === atualizado.id ? atualizado : u))
}

function mostrarToken(resposta) {
  token.value = resposta.api_token
  tokenDe.value = resposta.email || ''
  mostrandoToken.value = true
}

function abrirCriacao() {
  Object.assign(novo, { email: '', name: '', role: 'operator', password: '' })
  erroDoForm.value = ''
  criando.value = true
}

// A API valida de novo (e é ela que vale); aqui é só para a mensagem sair no idioma da tela.
const senhaCurta = (s) => s && s.length < 10

async function criar() {
  erroDoForm.value = ''
  if (senhaCurta(novo.password)) {
    erroDoForm.value = t('shield.entrada.senhaDica')
    return
  }
  enviando.value = true
  try {
    const corpo = { email: novo.email.trim(), role: novo.role }
    if (novo.name.trim()) corpo.name = novo.name.trim()
    if (novo.password) corpo.password = novo.password
    const r = await post('/users', corpo)
    const { api_token: _token, ...usuario } = r
    usuarios.value = [...usuarios.value, usuario]
    criando.value = false
    mostrarToken(r)
  } catch (e) {
    erroDoForm.value = mensagem(e)
  } finally {
    enviando.value = false
  }
}

async function mudarPapel(u, papel) {
  if (papel === u.role) return
  ocupado.value = u.id
  try {
    trocar(await patch(`/users/${u.id}/role`, { role: papel }))
    avisar(t('shield.usuarios.papelMudou'))
  } catch (e) {
    avisar(mensagem(e), 'negative')
  } finally {
    ocupado.value = null
  }
}

function abrirSenha(u) {
  alvoDaSenha.value = u
  senhaNova.value = ''
  erroDoForm.value = ''
  trocandoSenha.value = true
}

async function salvarSenha() {
  erroDoForm.value = ''
  if (senhaCurta(senhaNova.value)) {
    erroDoForm.value = t('shield.entrada.senhaDica')
    return
  }
  enviando.value = true
  try {
    trocar(await put(`/users/${alvoDaSenha.value.id}/password`, { password: senhaNova.value }))
    trocandoSenha.value = false
    avisar(t('shield.usuarios.senhaSalva'))
  } catch (e) {
    erroDoForm.value = mensagem(e)
  } finally {
    enviando.value = false
  }
}

async function girarToken(u) {
  const ok = await confirmar({
    titulo: t('shield.usuarios.girarToken'),
    mensagem: t('shield.usuarios.girarAviso', { email: u.email }),
    rotulo: t('shield.usuarios.girar'),
    aviso: true,
    icone: 'autorenew',
  })
  if (!ok) return
  try {
    const r = await post(`/users/${u.id}/rotate-token`)
    const { api_token: _token, ...usuario } = r
    trocar(usuario)
    mostrarToken(r)
  } catch (e) {
    avisar(mensagem(e), 'negative')
  }
}

async function desativar(u) {
  const ok = await confirmar({
    titulo: t('shield.usuarios.desativar'),
    mensagem: t('shield.usuarios.desativarAviso', { email: u.email }),
    rotulo: t('shield.usuarios.desativar'),
    perigo: true,
    icone: 'person_off',
  })
  if (!ok) return
  try {
    trocar(await post(`/users/${u.id}/deactivate`))
  } catch (e) {
    avisar(mensagem(e), 'negative')
  }
}

async function copiar() {
  try {
    await navigator.clipboard.writeText(token.value)
    avisar(t('shield.usuarios.copiado'))
  } catch {
    avisar(t('shield.usuarios.copiarFalhou'), 'warning')
  }
}

onMounted(carregar)
</script>

<style scoped lang="scss">
@import 'src/css/roqueos/tokens.scss';

// Os estilos de ajustes do ROSPentest são scoped nele e não alcançam este filho:
// as regras abaixo repetem as mesmas medidas (ros-pentest.scss, .ros-pentest__ajustes-*).
.usuarios__cab {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--ros-space-3);
  flex-wrap: wrap;
  h3 {
    margin: 0 0 4px;
    font-size: var(--ros-text-xl);
    font-weight: 700;
    letter-spacing: -0.3px;
  }
  p {
    margin: 0;
    max-width: 52ch;
    font-size: var(--ros-text-base);
    line-height: 1.5;
    color: $ros-text-muted;
  }
}
.usuarios__nota {
  display: flex;
  align-items: flex-start;
  gap: var(--ros-space-2);
  margin: 0;
  padding: var(--ros-space-3);
  border-radius: var(--ros-radius-md);
  font-size: var(--ros-text-sm);
  line-height: 1.5;
  color: $ros-text-muted;
  background: var(--ros-fill-03);
  .q-icon {
    flex: none;
    margin-top: 2px;
  }
}
.usuarios__estado {
  display: flex;
  justify-content: center;
  padding: var(--ros-space-6);
}
.usuarios__lista {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--ros-space-2);
}
.usuarios__item {
  display: flex;
  gap: var(--ros-space-3);
  padding: var(--ros-space-3) var(--ros-space-4);
  border-radius: var(--ros-radius-md);
  background: $ros-fill-04;
  border: 1px solid $ros-border-muted;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}
.usuarios__item--inativo {
  opacity: 0.6;
}
.usuarios__quem {
  display: flex;
  align-items: center;
  gap: var(--ros-space-3);
  min-width: 0;
  flex: 1 1 240px;
}
.usuarios__avatar {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex: none;
  border-radius: 50%;
  background: $ros-fill-08;
}
.usuarios__nomes {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
}
.usuarios__nome {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.usuarios__email {
  font-size: var(--ros-text-sm);
  color: $ros-text-muted;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.usuarios__marcas {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}
.usuarios__acoes {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: none;
}
.usuarios__papel {
  width: 150px;
}
.usuarios__form {
  display: flex;
  flex-direction: column;
  gap: var(--ros-space-2);
}
.usuarios__dica {
  margin: 0;
  font-size: var(--ros-text-sm);
  opacity: 0.75;
}
.usuarios__erro {
  margin: 0;
  color: rgb(var(--ros-danger-strong-rgb));
  font-size: var(--ros-text-sm);
}
.usuarios__token {
  display: flex;
  align-items: center;
  gap: var(--ros-space-2);
  margin: var(--ros-space-3) 0;
  padding: var(--ros-space-2) var(--ros-space-3);
  border-radius: var(--ros-radius-md);
  background: $ros-fill-08;
}
.usuarios__token-txt {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: var(--ros-text-sm);
  user-select: all;
}
@media (max-width: 768px) {
  .usuarios__acoes {
    width: 100%;
    justify-content: flex-end;
  }
  .usuarios__papel {
    flex: 1;
    width: auto;
  }
}
</style>
