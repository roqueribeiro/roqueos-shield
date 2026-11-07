export default {
  auth: {
    emailNotVerifiedBeforeLogin: 'Bitte bestätige deine E-Mail, bevor du dich anmeldest.',
    userNotAuthenticated: 'Benutzer nicht authentifiziert',
  },
  env: {
    missingRequired: 'Missing required environment variable: {key}',
  },
  chat: {
    localModelUnreachable:
      'Das lokale Modell ist nicht erreichbar. Prüfe unter Einstellungen → KI-Anbieter, ob die Adresse läuft und der RoqueOS-Server sie erreicht.',
    aiKeyMissing:
      'Konfiguriere den KI-Anbieter-Schlüssel unter Einstellungen → KI-Anbieter, um diesen Agenten zu nutzen.',
    aiNeedsServerMode:
      'Der KI-Chat benötigt den aktiven Servermodus, um zu antworten. Mit einem Server verbinden.',
    apiKeyNotConfiguredForAgent: 'API-Schlüssel ist für diesen Agenten nicht konfiguriert',
    assistantNeedsServerMode:
      'Der Assistent benötigt den aktiven Servermodus, um auf deinem Desktop zu handeln.',
    assistantConnectFailed:
      'Verbindung zum Assistenten fehlgeschlagen. Prüfe den Servermodus und versuche es erneut.',
    assistantFailed:
      'Der Assistent konnte die Anfrage nicht abschließen. Bitte versuche es erneut.',
    providerNotSupported: 'Anbieter "{provider}" wird nicht unterstützt',
    agentNotFoundOrNoPermission: 'Agent nicht gefunden oder keine Berechtigung',
    openAiApiError: 'OpenAI API-Fehler',
    anthropicApiError: 'Anthropic API-Fehler',
    geminiApiError: 'Gemini API-Fehler',
    groqApiError: 'Groq API-Fehler',
    mistralApiError: 'Mistral API-Fehler',
    openRouterApiError: 'OpenRouter API-Fehler',
  },
  remoteDesktop: {
    websocketNotConnected: 'WebSocket nicht verbunden',
    connectionError: 'Verbindungsfehler',
  },
  api: {
    requestFailed: 'Anfrage fehlgeschlagen',
    httpStatus: 'HTTP {status}',
    uploadFailed: 'Upload fehlgeschlagen',
    uploadFailedWithStatus: 'Upload fehlgeschlagen: {status}',
  },
  googleDrive: {
    notConnected: 'Nicht mit Google Drive verbunden',
    downloadFailed: 'Download fehlgeschlagen',
    getFileContentFailed: 'Dateiinhalt konnte nicht geladen werden',
    uploadFailed: 'Upload fehlgeschlagen',
    exportFailed: 'Export fehlgeschlagen',
  },
  appStore: {
    failedToFetchCatalog: 'Katalog konnte nicht geladen werden',
    invalidCatalogStructure: 'Ungültige Katalogstruktur',
    invalidJsonFormat: 'Ungültiges JSON-Format',
  },
  fileStorage: {
    fileNotFound: 'Datei nicht gefunden',
    folderIntoItself: 'Ein Ordner kann nicht in sich selbst verschoben werden.',
  },
  http: {
    timeout: 'Die Anfrage hat das Zeitlimit überschritten ({ms} ms).',
    httpErrorStatus: 'HTTP-Fehler! Status: {status}',
    networkError: 'Netzwerkfehler. Überprüfen Sie Ihre Verbindung.',
  },
  loadFailed: 'Laden fehlgeschlagen',
  appLoadError:
    'Die App konnte nicht geladen werden. Überprüfen Sie Ihre Verbindung und versuchen Sie es erneut.',
  generic: 'Ein unerwarteter Fehler ist aufgetreten',
  appOffline: 'Keine Verbindung',
  appOfflineMessage:
    'Diese App ist auf diesem Gerät noch nicht gespeichert. Stellen Sie eine Internetverbindung her und versuchen Sie es erneut: Nach dem ersten Mal öffnet sie sich auch offline.',
  operationFailed: 'Vorgang konnte nicht abgeschlossen werden. Bitte erneut versuchen.',
  copyFailed: 'Konnte nicht kopiert werden.',
  featureDisabledByServerTitle: 'Funktion nicht verfügbar',
  featureDisabledByServer:
    'Diese Funktion ist auf dem aktiven Server nicht aktiviert. Verbinden Sie sich mit einem kompatiblen Server, um sie zu verwenden.',
  clipboardAccess:
    'Zugriff auf die Zwischenablage nicht möglich. Überprüfen Sie die Browser-Berechtigungen.',
  notFound: {
    titlePart2: 'Gefunden',
    openApp: 'RoqueOS öffnen',
  },
}
