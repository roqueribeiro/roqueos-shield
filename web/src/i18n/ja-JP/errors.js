export default {
  auth: {
    emailNotVerifiedBeforeLogin: 'ログインする前にメールを確認してください。',
    userNotAuthenticated: 'ユーザーが認証されていません',
  },
  env: {
    missingRequired: 'Missing required environment variable: {key}',
  },
  chat: {
    localModelUnreachable:
      'ローカルモデルに接続できません。設定 → AIプロバイダー で、アドレスが稼働していて RoqueOS サーバーから届くか確認してください。',
    aiKeyMissing:
      'このエージェントを使うには、設定 → AIプロバイダー でAIプロバイダーのキーを設定してください。',
    aiNeedsServerMode:
      'AIチャットが応答するにはサーバーモードを有効にする必要があります。サーバーに接続してください。',
    apiKeyNotConfiguredForAgent: 'このエージェントのAPIキーが設定されていません',
    assistantNeedsServerMode:
      'アシスタントがデスクトップを操作するには、サーバーモードを有効にする必要があります。',
    assistantConnectFailed:
      'アシスタントに接続できませんでした。サーバーモードを確認して、もう一度お試しください。',
    assistantFailed: 'アシスタントはリクエストを完了できませんでした。もう一度お試しください。',
    providerNotSupported: 'プロバイダー「{provider}」はサポートされていません',
    agentNotFoundOrNoPermission: 'エージェントが見つからないか権限がありません',
    openAiApiError: 'OpenAI API エラー',
    anthropicApiError: 'Anthropic API エラー',
    geminiApiError: 'Gemini API エラー',
    groqApiError: 'Groq API エラー',
    mistralApiError: 'Mistral API エラー',
    openRouterApiError: 'OpenRouter API エラー',
  },
  remoteDesktop: {
    websocketNotConnected: 'WebSocket が接続されていません',
    connectionError: '接続エラー',
  },
  api: {
    requestFailed: 'リクエストに失敗しました',
    httpStatus: 'HTTP {status}',
    uploadFailed: 'アップロードに失敗しました',
    uploadFailedWithStatus: 'アップロードに失敗しました: {status}',
  },
  googleDrive: {
    notConnected: 'Google Drive に接続されていません',
    downloadFailed: 'ダウンロードに失敗しました',
    getFileContentFailed: 'ファイル内容の取得に失敗しました',
    uploadFailed: 'アップロードに失敗しました',
    exportFailed: 'エクスポートに失敗しました',
  },
  appStore: {
    failedToFetchCatalog: 'カタログの取得に失敗しました',
    invalidCatalogStructure: '無効なカタログ構造',
    invalidJsonFormat: '無効なJSON形式',
  },
  fileStorage: {
    fileNotFound: 'ファイルが見つかりません',
    folderIntoItself: 'フォルダーをそれ自体の中に移動することはできません。',
  },
  http: {
    timeout: 'リクエストがタイムアウトしました（{ms} ms）。',
    httpErrorStatus: 'HTTPエラー! status: {status}',
    networkError: 'ネットワークエラー。接続を確認してください。',
  },
  loadFailed: '読み込みに失敗しました',
  appLoadError: 'アプリを読み込めませんでした。接続を確認して再試行してください。',
  generic: '予期しないエラーが発生しました',
  appOffline: 'オフラインです',
  appOfflineMessage:
    'このアプリはまだこのデバイスに保存されていません。インターネットに接続してもう一度お試しください。一度開けば、次からはオフラインでも開けます。',
  operationFailed: '操作を完了できませんでした。もう一度お試しください。',
  copyFailed: 'コピーできませんでした。',
  featureDisabledByServerTitle: '機能を利用できません',
  featureDisabledByServer:
    'この機能はアクティブなサーバーで有効になっていません。互換性のあるサーバーに接続して使用してください。',
  clipboardAccess: 'クリップボードにアクセスできませんでした。ブラウザの権限を確認してください。',
  notFound: {
    titlePart2: '見つかりません',
    openApp: 'RoqueOS を開く',
  },
}
