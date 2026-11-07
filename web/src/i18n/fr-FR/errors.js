export default {
  auth: {
    emailNotVerifiedBeforeLogin: 'Veuillez vérifier votre e-mail avant de vous connecter.',
    userNotAuthenticated: 'Utilisateur non authentifié',
  },
  env: {
    missingRequired: 'Missing required environment variable: {key}',
  },
  chat: {
    localModelUnreachable:
      'Impossible de joindre le modèle local. Dans Réglages → Fournisseurs d’IA, vérifiez que son adresse répond et que le serveur RoqueOS peut l’atteindre.',
    aiKeyMissing:
      'Configurez la clé du fournisseur d’IA dans Réglages → Fournisseurs d’IA pour utiliser cet agent.',
    aiNeedsServerMode:
      'Le chat IA nécessite le Mode Serveur actif pour répondre. Connectez-vous à un serveur.',
    apiKeyNotConfiguredForAgent: 'Clé API non configurée pour cet agent',
    assistantNeedsServerMode:
      "L'assistant nécessite le Mode Serveur actif pour agir sur votre bureau.",
    assistantConnectFailed:
      "Impossible de se connecter à l'assistant. Vérifiez le Mode Serveur et réessayez.",
    assistantFailed: "L'assistant n'a pas pu terminer la demande. Veuillez réessayer.",
    providerNotSupported: 'Fournisseur "{provider}" non pris en charge',
    agentNotFoundOrNoPermission: 'Agent introuvable ou autorisation insuffisante',
    openAiApiError: 'Erreur API OpenAI',
    anthropicApiError: 'Erreur API Anthropic',
    geminiApiError: 'Erreur API Gemini',
    groqApiError: 'Erreur API Groq',
    mistralApiError: 'Erreur API Mistral',
    openRouterApiError: 'Erreur API OpenRouter',
  },
  remoteDesktop: {
    websocketNotConnected: 'WebSocket non connecté',
    connectionError: 'Erreur de connexion',
  },
  api: {
    requestFailed: 'La requête a échoué',
    httpStatus: 'HTTP {status}',
    uploadFailed: 'Échec du téléversement',
    uploadFailedWithStatus: 'Échec du téléversement : {status}',
  },
  googleDrive: {
    notConnected: 'Non connecté à Google Drive',
    downloadFailed: 'Échec du téléchargement',
    getFileContentFailed: "Impossible d'obtenir le contenu du fichier",
    uploadFailed: 'Échec du téléversement',
    exportFailed: "Échec de l'export",
  },
  appStore: {
    failedToFetchCatalog: 'Impossible de récupérer le catalogue',
    invalidCatalogStructure: 'Structure du catalogue invalide',
    invalidJsonFormat: 'Format JSON invalide',
  },
  fileStorage: {
    fileNotFound: 'Fichier introuvable',
    folderIntoItself: 'Un dossier ne peut pas être déplacé dans lui-même.',
  },
  http: {
    timeout: 'La requête a expiré ({ms} ms).',
    httpErrorStatus: 'Erreur HTTP ! statut : {status}',
    networkError: 'Erreur réseau. Vérifiez votre connexion.',
  },
  loadFailed: 'Échec du chargement',
  appLoadError: "Impossible de charger l'application. Vérifiez votre connexion et réessayez.",
  generic: "Une erreur inattendue s'est produite",
  appOffline: 'Pas de connexion',
  appOfflineMessage:
    "Cette app n'est pas encore enregistrée sur cet appareil. Connectez-vous à Internet et réessayez : après la première fois, elle s'ouvre hors ligne.",
  operationFailed: "Impossible de terminer l'opération. Veuillez réessayer.",
  copyFailed: 'Impossible de copier.',
  featureDisabledByServerTitle: 'Fonctionnalité indisponible',
  featureDisabledByServer:
    "Cette fonctionnalité n'est pas activée sur le serveur actif. Connectez-vous à un serveur compatible pour l'utiliser.",
  clipboardAccess:
    "Impossible d'accéder au presse-papiers. Vérifiez les autorisations du navigateur.",
  notFound: {
    titlePart2: 'Trouvée',
    openApp: 'Ouvrir RoqueOS',
  },
}
