/**
 * AI provider registry — the single source of truth for which LLM providers the
 * system-wide AI config supports. Drives the canonical AIProviderSheet + the
 * Settings "AI Providers" hub. "Maximum compatibility": every cloud provider
 * below is listed live from its `/models` endpoint server-side (see the server
 * `llm` module), plus a `local` connection type (OpenAI-compatible: LM Studio /
 * Ollama / any) handled via saved connections, not this list.
 *
 * `keyField` MUST match the field the server DTO expects (SetLlmConfigDto /
 * ListLlmModelsDto). `idPrefix` is the litellm-style prefix used in model ids
 * (e.g. `openai/gpt-4o`) so we can map a stored model id back to its provider.
 */

export const AI_PROVIDERS = [
  {
    id: 'openai',
    label: 'OpenAI',
    keyField: 'openaiKey',
    idPrefix: 'openai/',
    keyHint: 'sk-…',
    docUrl: 'https://platform.openai.com/api-keys',
  },
  {
    id: 'anthropic',
    label: 'Anthropic',
    keyField: 'anthropicKey',
    idPrefix: 'anthropic/',
    keyHint: 'sk-ant-…',
    docUrl: 'https://console.anthropic.com/settings/keys',
  },
  {
    id: 'openrouter',
    label: 'OpenRouter',
    keyField: 'openrouterKey',
    idPrefix: 'openrouter/',
    keyHint: 'sk-or-…',
    docUrl: 'https://openrouter.ai/keys',
  },
  {
    id: 'google',
    label: 'Google Gemini',
    keyField: 'googleKey',
    idPrefix: 'gemini/',
    keyHint: 'AIza…',
    docUrl: 'https://aistudio.google.com/apikey',
  },
  {
    id: 'groq',
    label: 'Groq',
    keyField: 'groqKey',
    idPrefix: 'groq/',
    keyHint: 'gsk_…',
    docUrl: 'https://console.groq.com/keys',
  },
  {
    id: 'mistral',
    label: 'Mistral',
    keyField: 'mistralKey',
    idPrefix: 'mistral/',
    keyHint: '',
    docUrl: 'https://console.mistral.ai/api-keys',
  },
  {
    id: 'deepseek',
    label: 'DeepSeek',
    keyField: 'deepseekKey',
    idPrefix: 'deepseek/',
    keyHint: 'sk-…',
    docUrl: 'https://platform.deepseek.com/api_keys',
  },
  {
    id: 'xai',
    label: 'xAI (Grok)',
    keyField: 'xaiKey',
    idPrefix: 'xai/',
    keyHint: 'xai-…',
    docUrl: 'https://console.x.ai',
  },
  {
    id: 'together',
    label: 'Together AI',
    keyField: 'togetherKey',
    idPrefix: 'together_ai/',
    keyHint: '',
    docUrl: 'https://api.together.xyz/settings/api-keys',
  },
]

/** Provider id → descriptor. */
export const AI_PROVIDER_BY_ID = Object.fromEntries(AI_PROVIDERS.map((p) => [p.id, p]))

/** All the DTO key field names (openaiKey, anthropicKey, …) — used to build/collect the keys payload. */
export const AI_PROVIDER_KEY_FIELDS = AI_PROVIDERS.map((p) => p.keyField)

/**
 * Map a stored litellm-style model id back to a provider id.
 * `openai/gpt-4o` → `openai`, `gemini/…` → `google`. An id with no known prefix
 * (a raw local model name) resolves to `local`.
 */
export const providerFromModelId = (modelId) => {
  if (!modelId || typeof modelId !== 'string') return null
  const match = AI_PROVIDERS.find((p) => modelId.startsWith(p.idPrefix))
  if (match) return match.id
  // No known cloud prefix → a local (OpenAI-compatible) model name.
  return 'local'
}

/** Human label for a model id (drops the provider prefix for cloud ids). */
export const modelShortLabel = (modelId) => {
  if (!modelId || typeof modelId !== 'string') return ''
  const match = AI_PROVIDERS.find((p) => modelId.startsWith(p.idPrefix))
  return match ? modelId.slice(match.idPrefix.length) : modelId
}
