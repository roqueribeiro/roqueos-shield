export default {
  auth: {
    emailNotVerifiedBeforeLogin: 'Please verify your email before signing in.',
    userNotAuthenticated: 'User not authenticated',
  },
  env: {
    missingRequired: 'Missing required environment variable: {key}',
  },
  chat: {
    localModelUnreachable:
      'Could not reach the local model. In Settings → AI Providers, check that its address is up and that the RoqueOS server can reach it.',
    aiKeyMissing: 'Configure your AI provider key in Settings → AI Providers to use this agent.',
    aiNeedsServerMode: 'AI chat needs Server Mode active to reply. Connect to a server.',
    apiKeyNotConfiguredForAgent: 'API key is not configured for this agent',
    assistantNeedsServerMode: 'The assistant needs Server Mode active to act on your desktop.',
    assistantConnectFailed: 'Could not connect to the assistant. Check Server Mode and try again.',
    assistantFailed: 'The assistant could not complete the request. Please try again.',
    providerNotSupported: 'Provider "{provider}" is not supported',
    agentNotFoundOrNoPermission: 'Agent not found or you do not have permission',
    openAiApiError: 'OpenAI API error',
    anthropicApiError: 'Anthropic API error',
    geminiApiError: 'Gemini API error',
    groqApiError: 'Groq API error',
    mistralApiError: 'Mistral API error',
    openRouterApiError: 'OpenRouter API error',
  },
  remoteDesktop: {
    websocketNotConnected: 'WebSocket not connected',
    connectionError: 'Connection error',
  },
  api: {
    requestFailed: 'Request failed',
    httpStatus: 'HTTP {status}',
    uploadFailed: 'Upload failed',
    uploadFailedWithStatus: 'Upload failed: {status}',
  },
  googleDrive: {
    notConnected: 'Not connected to Google Drive',
    downloadFailed: 'Download failed',
    getFileContentFailed: 'Failed to get file content',
    uploadFailed: 'Upload failed',
    exportFailed: 'Export failed',
  },
  appStore: {
    failedToFetchCatalog: 'Failed to fetch catalog',
    invalidCatalogStructure: 'Invalid catalog structure',
    invalidJsonFormat: 'Invalid JSON format',
  },
  fileStorage: {
    fileNotFound: 'File not found',
    folderIntoItself: 'A folder cannot be moved inside itself.',
  },
  http: {
    timeout: 'The request timed out ({ms} ms).',
    httpErrorStatus: 'HTTP Error! status: {status}',
    networkError: 'Network error. Check your connection.',
  },
  loadFailed: 'Failed to load',
  appLoadError: 'Could not load the application. Check your connection and try again.',
  generic: 'An unexpected error occurred',
  appOffline: 'No connection',
  appOfflineMessage:
    "This app isn't saved on this device yet. Connect to the internet and try again: after the first time, it opens offline.",
  operationFailed: 'Could not complete the operation. Please try again.',
  copyFailed: 'Could not copy.',
  featureDisabledByServerTitle: 'Feature unavailable',
  featureDisabledByServer:
    'This feature is not enabled on the active server. Connect to a compatible server to use it.',
  clipboardAccess: 'Could not access clipboard. Check browser permissions.',
  notFound: {
    titlePart2: 'Found',
    openApp: 'Open RoqueOS',
  },
}
