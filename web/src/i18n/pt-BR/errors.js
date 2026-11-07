export default {
  auth: {
    emailNotVerifiedBeforeLogin: 'Por favor, verifique seu email antes de fazer login.',
    userNotAuthenticated: 'Usuário não autenticado',
  },
  env: {
    missingRequired: 'Variável de ambiente obrigatória ausente: {key}',
  },
  chat: {
    localModelUnreachable:
      'Não consegui falar com o modelo local. Confira em Ajustes → Provedores de IA se o endereço está no ar e se o servidor RoqueOS alcança ele.',
    aiKeyMissing:
      'Configure a chave do provedor de IA em Ajustes → Provedores de IA para usar este agente.',
    aiNeedsServerMode:
      'A IA precisa do Modo Servidor ativo para responder. Conecte-se a um servidor.',
    apiKeyNotConfiguredForAgent: 'Chave de API não configurada para este agente',
    assistantNeedsServerMode:
      'O assistente precisa do Modo Servidor ativo para agir na área de trabalho.',
    assistantConnectFailed:
      'Não foi possível conectar ao assistente. Verifique o Modo Servidor e tente novamente.',
    assistantFailed: 'O assistente não conseguiu concluir a solicitação. Tente novamente.',
    providerNotSupported: 'Provider "{provider}" não suportado',
    agentNotFoundOrNoPermission: 'Agente não encontrado ou sem permissão',
    openAiApiError: 'Erro na API OpenAI',
    anthropicApiError: 'Erro na API Anthropic',
    geminiApiError: 'Erro na API Gemini',
    groqApiError: 'Erro na API Groq',
    mistralApiError: 'Erro na API Mistral',
    openRouterApiError: 'Erro na API OpenRouter',
  },
  remoteDesktop: {
    websocketNotConnected: 'WebSocket não conectado',
    connectionError: 'Erro de conexão',
  },
  api: {
    requestFailed: 'Falha na requisição',
    httpStatus: 'HTTP {status}',
    uploadFailed: 'Falha no upload',
    uploadFailedWithStatus: 'Falha no upload: {status}',
  },
  googleDrive: {
    notConnected: 'Não conectado ao Google Drive',
    downloadFailed: 'Falha no download',
    getFileContentFailed: 'Falha ao obter conteúdo do arquivo',
    uploadFailed: 'Falha no upload',
    exportFailed: 'Falha ao exportar',
  },
  appStore: {
    failedToFetchCatalog: 'Falha ao buscar catálogo',
    invalidCatalogStructure: 'Estrutura do catálogo inválida',
    invalidJsonFormat: 'Formato de JSON inválido',
  },
  fileStorage: {
    fileNotFound: 'Arquivo não encontrado',
    folderIntoItself: 'Uma pasta não pode ir para dentro dela mesma.',
  },
  http: {
    timeout: 'A requisição excedeu o tempo limite ({ms} ms).',
    httpErrorStatus: 'Erro HTTP! status: {status}',
    networkError: 'Erro de rede. Verifique sua conexão.',
  },
  loadFailed: 'Falha ao carregar',
  appLoadError: 'Não foi possível carregar o aplicativo. Verifique sua conexão e tente novamente.',
  generic: 'Ocorreu um erro inesperado',
  appOffline: 'Sem conexão',
  appOfflineMessage:
    'Este app ainda não está guardado neste aparelho. Conecte-se à internet e tente de novo: depois da primeira vez, ele abre offline.',
  operationFailed: 'Não foi possível concluir a operação. Tente novamente.',
  copyFailed: 'Não foi possível copiar.',
  featureDisabledByServerTitle: 'Recurso indisponível',
  featureDisabledByServer:
    'Este recurso não está habilitado no servidor ativo. Conecte-se a um servidor compatível para usá-lo.',
  clipboardAccess:
    'Não foi possível acessar a área de transferência. Verifique as permissões do navegador.',
  notFound: {
    titlePart2: 'Encontrada',
    openApp: 'Abrir RoqueOS',
  },
}
