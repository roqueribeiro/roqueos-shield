export default {
  auth: {
    emailNotVerifiedBeforeLogin: 'Пожалуйста, подтвердите email перед входом.',
    userNotAuthenticated: 'Пользователь не аутентифицирован',
  },
  env: {
    missingRequired: 'Missing required environment variable: {key}',
  },
  chat: {
    localModelUnreachable:
      'Не удалось связаться с локальной моделью. В «Настройки → Провайдеры ИИ» проверьте, что её адрес работает и сервер RoqueOS может до него достучаться.',
    aiKeyMissing:
      'Настройте ключ провайдера ИИ в «Настройки → Провайдеры ИИ», чтобы использовать этого агента.',
    aiNeedsServerMode: 'Для ответа ИИ-чату нужен активный режим сервера. Подключитесь к серверу.',
    apiKeyNotConfiguredForAgent: 'API-ключ не настроен для этого агента',
    assistantNeedsServerMode:
      'Ассистенту нужен активный режим сервера, чтобы управлять рабочим столом.',
    assistantConnectFailed:
      'Не удалось подключиться к ассистенту. Проверьте режим сервера и повторите попытку.',
    assistantFailed: 'Ассистент не смог выполнить запрос. Попробуйте ещё раз.',
    providerNotSupported: 'Провайдер "{provider}" не поддерживается',
    agentNotFoundOrNoPermission: 'Агент не найден или нет прав доступа',
    openAiApiError: 'Ошибка OpenAI API',
    anthropicApiError: 'Ошибка Anthropic API',
    geminiApiError: 'Ошибка Gemini API',
    groqApiError: 'Ошибка Groq API',
    mistralApiError: 'Ошибка Mistral API',
    openRouterApiError: 'Ошибка OpenRouter API',
  },
  remoteDesktop: {
    websocketNotConnected: 'WebSocket не подключен',
    connectionError: 'Ошибка подключения',
  },
  api: {
    requestFailed: 'Запрос не выполнен',
    httpStatus: 'HTTP {status}',
    uploadFailed: 'Ошибка загрузки',
    uploadFailedWithStatus: 'Ошибка загрузки: {status}',
  },
  googleDrive: {
    notConnected: 'Нет подключения к Google Drive',
    downloadFailed: 'Ошибка скачивания',
    getFileContentFailed: 'Не удалось получить содержимое файла',
    uploadFailed: 'Ошибка загрузки',
    exportFailed: 'Ошибка экспорта',
  },
  appStore: {
    failedToFetchCatalog: 'Не удалось загрузить каталог',
    invalidCatalogStructure: 'Неверная структура каталога',
    invalidJsonFormat: 'Неверный формат JSON',
  },
  fileStorage: {
    fileNotFound: 'Файл не найден',
    folderIntoItself: 'Папку нельзя переместить внутрь неё самой.',
  },
  http: {
    timeout: 'Время ожидания запроса истекло ({ms} мс).',
    httpErrorStatus: 'HTTP ошибка! статус: {status}',
    networkError: 'Ошибка сети. Проверьте подключение.',
  },
  loadFailed: 'Не удалось загрузить',
  appLoadError: 'Не удалось загрузить приложение. Проверьте подключение и повторите попытку.',
  generic: 'Произошла непредвиденная ошибка',
  appOffline: 'Нет подключения',
  appOfflineMessage:
    'Это приложение ещё не сохранено на этом устройстве. Подключитесь к интернету и повторите попытку: после первого запуска оно откроется и без сети.',
  operationFailed: 'Не удалось выполнить операцию. Попробуйте ещё раз.',
  copyFailed: 'Не удалось скопировать.',
  featureDisabledByServerTitle: 'Функция недоступна',
  featureDisabledByServer:
    'Эта функция не включена на активном сервере. Подключитесь к совместимому серверу, чтобы использовать её.',
  clipboardAccess: 'Не удалось получить доступ к буферу обмена. Проверьте разрешения браузера.',
  notFound: {
    titlePart2: 'Найдена',
    openApp: 'Открыть RoqueOS',
  },
}
