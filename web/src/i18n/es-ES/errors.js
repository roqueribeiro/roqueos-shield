export default {
  copyFailed: 'No se pudo copiar.',
  featureDisabledByServerTitle: 'Función no disponible',
  featureDisabledByServer:
    'Esta función no está habilitada en el servidor activo. Conéctate a un servidor compatible para usarla.',
  auth: {
    emailNotVerifiedBeforeLogin: 'Por favor, verifica tu correo antes de iniciar sesión.',
    userNotAuthenticated: 'Usuario no autenticado',
  },
  env: {
    missingRequired: 'Missing required environment variable: {key}',
  },
  chat: {
    localModelUnreachable:
      'No pude comunicarme con el modelo local. En Ajustes → Proveedores de IA, comprueba que su dirección esté activa y que el servidor RoqueOS pueda alcanzarla.',
    aiKeyMissing:
      'Configura la clave del proveedor de IA en Ajustes → Proveedores de IA para usar este agente.',
    aiNeedsServerMode:
      'El chat con IA necesita el Modo Servidor activo para responder. Conéctate a un servidor.',
    apiKeyNotConfiguredForAgent: 'Clave de API no configurada para este agente',
    assistantNeedsServerMode:
      'El asistente necesita el Modo Servidor activo para actuar en tu escritorio.',
    assistantConnectFailed:
      'No se pudo conectar con el asistente. Comprueba el Modo Servidor e inténtalo de nuevo.',
    assistantFailed: 'El asistente no pudo completar la solicitud. Inténtalo de nuevo.',
    providerNotSupported: 'Proveedor "{provider}" no es compatible',
    agentNotFoundOrNoPermission: 'Agente no encontrado o sin permiso',
    openAiApiError: 'Error en la API de OpenAI',
    anthropicApiError: 'Error en la API de Anthropic',
    geminiApiError: 'Error en la API de Gemini',
    groqApiError: 'Error en la API de Groq',
    mistralApiError: 'Error en la API de Mistral',
    openRouterApiError: 'Error en la API de OpenRouter',
  },
  remoteDesktop: {
    websocketNotConnected: 'WebSocket no conectado',
    connectionError: 'Error de conexión',
  },
  api: {
    requestFailed: 'La solicitud falló',
    httpStatus: 'HTTP {status}',
    uploadFailed: 'La carga falló',
    uploadFailedWithStatus: 'La carga falló: {status}',
    loadFailed: 'Error al cargar',
    appLoadError: 'No se pudo cargar la aplicación. Verifica tu conexión e inténtalo de nuevo.',
    generic: 'Ocurrió un error inesperado',
  },
  googleDrive: {
    notConnected: 'No conectado a Google Drive',
    downloadFailed: 'La descarga falló',
    getFileContentFailed: 'No se pudo obtener el contenido del archivo',
    uploadFailed: 'La carga falló',
    exportFailed: 'La exportación falló',
  },
  appStore: {
    failedToFetchCatalog: 'No se pudo obtener el catálogo',
    invalidCatalogStructure: 'Estructura de catálogo inválida',
    invalidJsonFormat: 'Formato JSON inválido',
  },
  fileStorage: {
    fileNotFound: 'Archivo no encontrado',
    folderIntoItself: 'Una carpeta no puede moverse dentro de sí misma.',
  },
  http: {
    timeout: 'La solicitud superó el tiempo límite ({ms} ms).',
    httpErrorStatus: 'Error HTTP! estado: {status}',
    networkError: 'Error de red. Verifica tu conexión.',
  },
  loadFailed: 'Error al cargar',
  appLoadError: 'No se pudo cargar la aplicación. Verifica tu conexión e inténtalo de nuevo.',
  generic: 'Ocurrió un error inesperado',
  appOffline: 'Sin conexión',
  appOfflineMessage:
    'Esta app todavía no está guardada en este dispositivo. Conéctate a internet e inténtalo de nuevo: después de la primera vez, se abre sin conexión.',
  operationFailed: 'No se pudo completar la operación. Inténtalo de nuevo.',
  clipboardAccess: 'No se pudo acceder al portapapeles. Verifica los permisos del navegador.',
  notFound: {
    titlePart2: 'Encontrada',
    openApp: 'Abrir RoqueOS',
  },
}
