export default {
  auth: {
    emailNotVerifiedBeforeLogin: 'कृपया लॉगिन से पहले अपना ईमेल सत्यापित करें।',
    userNotAuthenticated: 'उपयोगकर्ता प्रमाणित नहीं है',
  },
  env: {
    missingRequired: 'Missing required environment variable: {key}',
  },
  chat: {
    localModelUnreachable:
      'लोकल मॉडल तक नहीं पहुँच सका। सेटिंग्स → AI प्रोवाइडर में देखें कि उसका पता चालू है और RoqueOS सर्वर उस तक पहुँच सकता है।',
    aiKeyMissing:
      'इस एजेंट का उपयोग करने के लिए सेटिंग्स → AI प्रोवाइडर में AI प्रोवाइडर कुंजी कॉन्फ़िगर करें।',
    aiNeedsServerMode:
      'AI चैट को उत्तर देने के लिए सर्वर मोड सक्रिय चाहिए। किसी सर्वर से कनेक्ट करें।',
    apiKeyNotConfiguredForAgent: 'इस एजेंट के लिए API कुंजी कॉन्फ़िगर नहीं है',
    assistantNeedsServerMode: 'डेस्कटॉप पर कार्य करने के लिए असिस्टेंट को सर्वर मोड सक्रिय चाहिए।',
    assistantConnectFailed:
      'असिस्टेंट से कनेक्ट नहीं हो सका। सर्वर मोड जाँचें और पुनः प्रयास करें।',
    assistantFailed: 'असिस्टेंट अनुरोध पूरा नहीं कर सका। कृपया पुनः प्रयास करें।',
    providerNotSupported: 'प्रदाता "{provider}" समर्थित नहीं है',
    agentNotFoundOrNoPermission: 'एजेंट नहीं मिला या अनुमति नहीं है',
    openAiApiError: 'OpenAI API त्रुटि',
    anthropicApiError: 'Anthropic API त्रुटि',
    geminiApiError: 'Gemini API त्रुटि',
    groqApiError: 'Groq API त्रुटि',
    mistralApiError: 'Mistral API त्रुटि',
    openRouterApiError: 'OpenRouter API त्रुटि',
  },
  remoteDesktop: {
    websocketNotConnected: 'WebSocket कनेक्ट नहीं है',
    connectionError: 'कनेक्शन त्रुटि',
  },
  api: {
    requestFailed: 'अनुरोध विफल',
    httpStatus: 'HTTP {status}',
    uploadFailed: 'अपलोड विफल',
    uploadFailedWithStatus: 'अपलोड विफल: {status}',
  },
  googleDrive: {
    notConnected: 'Google Drive से कनेक्ट नहीं है',
    downloadFailed: 'डाउनलोड विफल',
    getFileContentFailed: 'फ़ाइल सामग्री प्राप्त करने में विफल',
    uploadFailed: 'अपलोड विफल',
    exportFailed: 'एक्सपोर्ट विफल',
  },
  appStore: {
    failedToFetchCatalog: 'कैटलॉग प्राप्त करने में विफल',
    invalidCatalogStructure: 'अमान्य कैटलॉग संरचना',
    invalidJsonFormat: 'अमान्य JSON प्रारूप',
  },
  fileStorage: {
    fileNotFound: 'फ़ाइल नहीं मिली',
    folderIntoItself: 'किसी फ़ोल्डर को उसी के अंदर नहीं ले जाया जा सकता।',
  },
  http: {
    timeout: 'अनुरोध समय समाप्त हो गया ({ms} ms)।',
    httpErrorStatus: 'HTTP त्रुटि! स्थिति: {status}',
    networkError: 'नेटवर्क त्रुटि। अपना कनेक्शन जांचें।',
  },
  loadFailed: 'लोड करने में विफल',
  appLoadError: 'ऐप लोड नहीं हो सका। अपना कनेक्शन जांचें और पुनः प्रयास करें।',
  generic: 'एक अप्रत्याशित त्रुटि हुई',
  appOffline: 'कनेक्शन नहीं है',
  appOfflineMessage:
    'यह ऐप अभी इस डिवाइस पर सहेजा नहीं गया है। इंटरनेट से जुड़ें और फिर से कोशिश करें: पहली बार के बाद यह ऑफ़लाइन भी खुलेगा।',
  operationFailed: 'ऑपरेशन पूरा नहीं हो सका। कृपया पुनः प्रयास करें।',
  copyFailed: 'कॉपी नहीं किया जा सका।',
  featureDisabledByServerTitle: 'सुविधा अनुपलब्ध',
  featureDisabledByServer:
    'यह सुविधा सक्रिय सर्वर पर सक्षम नहीं है। इसका उपयोग करने के लिए एक संगत सर्वर से कनेक्ट करें।',
  clipboardAccess: 'क्लिपबोर्ड तक पहुंच नहीं हो सकी। ब्राउज़र अनुमतियां जांचें।',
  notFound: {
    titlePart2: 'मिली',
    openApp: 'RoqueOS खोलें',
  },
}
