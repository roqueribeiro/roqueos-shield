<template>
  <ROSModal
    :model-value="modelValue"
    :title="title || t('aiProvider.title')"
    icon="smart_toy"
    size="md"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <div class="ai-sheet">
      <ROSSegmented v-model="provedor" block quebrar :options="opcoesDeProvedor" :label="t('shield.ia.provedor')" />

      <ROSFormField
        v-if="provedor === 'local'"
        v-model="apiBase"
        :label="t('shield.ia.endereco')"
        placeholder="http://host.docker.internal:1234/v1"
        autocomplete="off"
      />
      <ROSFormField
        v-model="chave"
        type="password"
        autocomplete="new-password"
        :label="provedor === 'local' ? t('shield.ia.chaveLocal') : t('shield.ia.chave')"
        :placeholder="temChaveGuardada ? t('shield.ia.chaveGuardada') : dicaDaChave"
      />

      <div class="ai-sheet__lista">
        <ROSButton variant="secondary" icon="refresh" :loading="buscando" @click="buscar">
          {{ t('shield.ia.listar') }}
        </ROSButton>
        <span v-if="aviso" class="ai-sheet__aviso">{{ aviso }}</span>
      </div>

      <ROSSelectField
        v-model="modelo"
        :label="t('shield.ia.modelo')"
        :options="opcoesDeModelo"
        use-input
        new-value-mode="add-unique"
        :disabled="!opcoesDeModelo.length && !modelo"
      />
      <ROSSelectField
        v-model="reserva"
        :label="t('shield.ia.reserva')"
        :options="[{ label: t('shield.ia.semReserva'), value: '' }, ...opcoesDeModelo]"
      />
      <p class="ai-sheet__nota">
        <q-icon name="lock" size="14px" />
        <span>{{ t('shield.ia.notaChave') }}</span>
      </p>
    </div>

    <template #footer>
      <ROSButton variant="ghost" @click="emit('update:modelValue', false)">{{ t('common.cancel') }}</ROSButton>
      <ROSButton variant="primary" icon="check" :disabled="!modelo" @click="salvar">
        {{ t('shield.ia.usar') }}
      </ROSButton>
    </template>
  </ROSModal>
</template>

<script setup>
/**
 * Escolha do modelo de IA no standalone.
 *
 * No RoqueOS este é o `AIProviderSheet` da central de Provedores de IA dos Ajustes:
 * a chave mora lá e cada app só escolhe o modelo. Fora do RoqueOS não há central,
 * então a escolha traz a própria chave (`ownModel: true`). A lista de modelos vem do
 * shield (`POST /settings/ai/models`), que chama o provedor do lado do servidor: a
 * chave digitada aqui vai para o shield e não volta.
 *
 * Mesmo contrato do de lá: `v-model` abre e fecha, `initial` é a config atual, e
 * `save` devolve `{ model, fallbackModel, provider, ownModel, apiBase, apiKey }`.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import pentestApi from 'src/services/api/pentest'
import { AI_PROVIDER_BY_ID, providerFromModelId } from 'src/constants/aiProviders'
import ROSModal from '../ROSModal.vue'
import ROSSegmented from '../ROSSegmented.vue'
import ROSFormField from '../ROSFormField.vue'
import ROSSelectField from '../ROSSelectField.vue'
import ROSButton from '../ROSButton.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  accent: { type: String, default: '' },
  mode: { type: String, default: 'picker' },
  initial: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['update:modelValue', 'save'])
const { t } = useI18n()

const PROVEDORES = ['anthropic', 'openai', 'openrouter', 'local']
const opcoesDeProvedor = computed(() =>
  PROVEDORES.map((id) => ({ value: id, label: id === 'local' ? t('shield.ia.local') : AI_PROVIDER_BY_ID[id]?.label || id })),
)

const provedor = ref('anthropic')
const apiBase = ref('')
const chave = ref('')
const modelo = ref('')
const reserva = ref('')
const grupos = ref([])
const buscando = ref(false)
const aviso = ref('')
const temChaveGuardada = ref(false)

const dicaDaChave = computed(() => AI_PROVIDER_BY_ID[provedor.value]?.keyHint || '')
const opcoesDeModelo = computed(() =>
  grupos.value
    .filter((g) => g.provider === provedor.value)
    .flatMap((g) => g.models.map((m) => ({ label: m.label, value: m.id }))),
)

watch(
  () => props.modelValue,
  (aberto) => {
    if (!aberto) return
    const i = props.initial || {}
    provedor.value = i.apiBase ? 'local' : providerFromModelId(i.model) || 'anthropic'
    apiBase.value = i.apiBase || ''
    modelo.value = i.model || ''
    reserva.value = i.fallbackModel || ''
    chave.value = ''
    temChaveGuardada.value = !!i.ownModel
    aviso.value = ''
  },
  { immediate: true },
)

async function buscar() {
  buscando.value = true
  aviso.value = ''
  try {
    const corpo = {}
    if (provedor.value === 'local') {
      corpo.apiBase = apiBase.value
      if (chave.value) corpo.apiKey = chave.value
    } else if (chave.value) {
      corpo[AI_PROVIDER_BY_ID[provedor.value].keyField] = chave.value
    }
    const r = await pentestApi.listAiModels(corpo)
    grupos.value = r?.groups || []
    if ((r?.errors || []).includes(provedor.value)) aviso.value = t('shield.ia.listaCurada')
    else if (!opcoesDeModelo.value.length) aviso.value = t('shield.ia.semModelos')
  } catch {
    aviso.value = t('shield.ia.semModelos')
  } finally {
    buscando.value = false
  }
}

function salvar() {
  emit('save', {
    model: modelo.value,
    fallbackModel: reserva.value,
    provider: provedor.value,
    ownModel: true,
    apiBase: provedor.value === 'local' ? apiBase.value : '',
    apiKey: chave.value,
  })
  emit('update:modelValue', false)
}
</script>

<style scoped>
.ai-sheet {
  display: flex;
  flex-direction: column;
  gap: var(--ros-space-3);
}
.ai-sheet__lista {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ros-space-2);
}
.ai-sheet__aviso,
.ai-sheet__nota {
  font-size: var(--ros-text-sm);
  color: var(--ros-text-muted);
}
.ai-sheet__nota {
  display: flex;
  align-items: flex-start;
  gap: var(--ros-space-2);
  margin: 0;
}
</style>
