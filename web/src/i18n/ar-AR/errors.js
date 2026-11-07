export default {
  auth: {
    emailNotVerifiedBeforeLogin: 'يرجى التحقق من بريدك الإلكتروني قبل تسجيل الدخول.',
    userNotAuthenticated: 'المستخدم غير مسجل الدخول',
  },
  env: {
    missingRequired: 'Missing required environment variable: {key}',
  },
  chat: {
    localModelUnreachable:
      'تعذّر الوصول إلى النموذج المحلي. في الإعدادات ← مزودو الذكاء الاصطناعي، تأكد من أن عنوانه يعمل وأن خادم RoqueOS يمكنه الوصول إليه.',
    aiKeyMissing:
      'قم بضبط مفتاح مزود الذكاء الاصطناعي في الإعدادات ← مزودو الذكاء الاصطناعي لاستخدام هذا الوكيل.',
    aiNeedsServerMode: 'تحتاج محادثة الذكاء الاصطناعي إلى تفعيل وضع الخادم للرد. اتصل بخادم.',
    apiKeyNotConfiguredForAgent: 'مفتاح API غير مُعد لهذا الوكيل',
    assistantNeedsServerMode: 'يحتاج المساعد إلى تفعيل وضع الخادم للتحكم في سطح المكتب.',
    assistantConnectFailed: 'تعذّر الاتصال بالمساعد. تحقق من وضع الخادم وحاول مرة أخرى.',
    assistantFailed: 'لم يتمكن المساعد من إكمال الطلب. حاول مرة أخرى.',
    providerNotSupported: 'المزود "{provider}" غير مدعوم',
    agentNotFoundOrNoPermission: 'الوكيل غير موجود أو لا تملك الصلاحية',
    openAiApiError: 'خطأ في واجهة OpenAI',
    anthropicApiError: 'خطأ في واجهة Anthropic',
    geminiApiError: 'خطأ في واجهة Gemini',
    groqApiError: 'خطأ في واجهة Groq',
    mistralApiError: 'خطأ في واجهة Mistral',
    openRouterApiError: 'خطأ في واجهة OpenRouter',
  },
  remoteDesktop: {
    websocketNotConnected: 'WebSocket غير متصل',
    connectionError: 'خطأ في الاتصال',
  },
  api: {
    requestFailed: 'فشل الطلب',
    httpStatus: 'HTTP {status}',
    uploadFailed: 'فشل الرفع',
    uploadFailedWithStatus: 'فشل الرفع: {status}',
  },
  googleDrive: {
    notConnected: 'غير متصل بـ Google Drive',
    downloadFailed: 'فشل التنزيل',
    getFileContentFailed: 'فشل الحصول على محتوى الملف',
    uploadFailed: 'فشل الرفع',
    exportFailed: 'فشل التصدير',
  },
  appStore: {
    failedToFetchCatalog: 'فشل جلب الكتالوج',
    invalidCatalogStructure: 'بنية كتالوج غير صالحة',
    invalidJsonFormat: 'تنسيق JSON غير صالح',
  },
  fileStorage: {
    fileNotFound: 'الملف غير موجود',
    folderIntoItself: 'لا يمكن نقل مجلد إلى داخله.',
  },
  http: {
    timeout: 'انتهت مهلة الطلب ({ms} مللي ثانية).',
    httpErrorStatus: 'خطأ HTTP! الحالة: {status}',
    networkError: 'خطأ في الشبكة. تحقق من اتصالك.',
  },
  loadFailed: 'فشل التحميل',
  appLoadError: 'تعذر تحميل التطبيق. تحقق من اتصالك وحاول مرة أخرى.',
  generic: 'حدث خطأ غير متوقع',
  appOffline: 'لا يوجد اتصال',
  appOfflineMessage:
    'لم يُحفظ هذا التطبيق على هذا الجهاز بعد. اتصل بالإنترنت وحاول مرة أخرى: بعد المرة الأولى سيفتح دون اتصال.',
  operationFailed: 'تعذر إكمال العملية. حاول مرة أخرى.',
  copyFailed: 'تعذر النسخ.',
  featureDisabledByServerTitle: 'الميزة غير متاحة',
  featureDisabledByServer: 'هذه الميزة غير مفعّلة على الخادم النشط. اتصل بخادم متوافق لاستخدامها.',
  clipboardAccess: 'تعذر الوصول إلى الحافظة. تحقق من أذونات المتصفح.',
  notFound: {
    titlePart2: 'موجودة',
    openApp: 'فتح RoqueOS',
  },
}
