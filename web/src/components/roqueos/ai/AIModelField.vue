<template>
  <div class="ai-model-field">
    <label v-if="label" class="ai-model-field__label">{{ label }}</label>

    <button type="button" class="ai-model-field__trigger" @click="open = true">
      <span class="ai-model-field__icon" aria-hidden="true">
        <q-icon name="smart_toy" size="18px" />
      </span>
      <span class="ai-model-field__text">
        <template v-if="modelValue?.model">
          <span class="ai-model-field__model">{{ modelShortLabel(modelValue.model) }}</span>
          <span class="ai-model-field__meta">
            {{ providerLabel(modelValue) }}
            <template v-if="modelValue.fallbackModel">
              · {{ t('aiProvider.fallbackShort') }}: {{ modelShortLabel(modelValue.fallbackModel) }}
            </template>
            <template v-if="modelValue.ownModel"> · {{ t('aiProvider.ownShort') }}</template>
          </span>
        </template>
        <!-- O convite do campo ainda sem modelo (como o placeholder de um select), não um estado vazio. -->
        <span v-else class="ai-model-field__placeholder">{{ t('aiProvider.chooseModelCta') }}</span>
      </span>
      <q-icon name="tune" size="18px" class="ai-model-field__edit" />
    </button>

    <AIProviderSheet
      v-model="open"
      mode="picker"
      :accent="accent"
      :title="label || t('aiProvider.title')"
      :initial="modelValue || {}"
      @save="onSave"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AIProviderSheet from './AIProviderSheet.vue'
import { AI_PROVIDER_BY_ID, modelShortLabel, providerFromModelId } from 'src/constants/aiProviders'

/**
 * AIModelField — the ONE drop-in "which AI model runs this?" control, used by
 * every surface that calls an agent (Chat, Automations, Flows, Pentest). It
 * shows the chosen model and opens the canonical `AIProviderSheet` picker; the
 * model list + keys + local-LLM/tunnel come from the central AI Providers hub.
 *
 * `modelValue` is the surface's AI config:
 *   { model, fallbackModel?, provider?, ownModel?, apiBase?, apiKey? }
 * By default (`ownModel` false) the key is resolved server-side from the central
 * config — the surface stores only the model id. `ownModel` true carries a
 * per-item key/endpoint override.
 */
defineProps({
  modelValue: { type: Object, default: () => ({}) },
  label: { type: String, default: '' },
  accent: { type: String, default: '#5856d6' },
})
const emit = defineEmits(['update:modelValue'])

const { t } = useI18n()
const open = ref(false)

const providerLabel = (v) => {
  const id = v?.provider || providerFromModelId(v?.model)
  if (id === 'local') return t('aiProvider.localOption')
  return AI_PROVIDER_BY_ID[id]?.label || id || ''
}

const onSave = (cfg) => {
  emit('update:modelValue', {
    model: cfg.model || '',
    fallbackModel: cfg.fallbackModel || '',
    provider: cfg.provider || providerFromModelId(cfg.model) || '',
    ownModel: !!cfg.ownModel,
    // For a LOCAL model keep the endpoint so the server hits the right connection.
    apiBase: cfg.apiBase || '',
    // The key is stored only for an explicit per-item override; else central.
    apiKey: cfg.ownModel ? cfg.apiKey || '' : '',
  })
}
</script>

<style scoped lang="scss">
@import 'src/css/roqueos/tokens.scss';

.ai-model-field {
  // Cores de identidade deste app. Ficam aqui, e não em `tokens-root.scss`,
  // porque são do app e não do sistema — mas ficam como custom property
  // para que um tema consiga alcançá-las.
  --ai-model-field-line-1: rgba(88, 86, 214, 0.5);
  --ai-model-field-bg-1: rgba(88, 86, 214, 0.14);
}

.ai-model-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ai-model-field__label {
  font-size: var(--ros-text-sm);
  font-weight: 600;
  color: $ros-text-muted;
}
.ai-model-field__trigger {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid $ros-border-subtle;
  border-radius: var(--ros-radius-md);
  background: $ros-fill-04;
  color: $ros-text;
  cursor: pointer;
  text-align: left;
  transition: all var(--ros-duration-fast) ease;
  &:hover {
    background: $ros-fill-08;
    border-color: var(--ai-model-field-line-1);
  }
}
.ai-model-field__icon {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  border-radius: var(--ros-radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  color: v-bind(accent);
  background: var(--ai-model-field-bg-1);
}
.ai-model-field__text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.ai-model-field__model {
  font-size: var(--ros-text-base);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ai-model-field__meta {
  font-size: var(--ros-text-xs);
  color: $ros-text-subtle;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ai-model-field__placeholder {
  font-size: var(--ros-text-base);
  color: $ros-text-subtle;
}
.ai-model-field__edit {
  flex-shrink: 0;
  color: $ros-text-muted;
}
</style>
