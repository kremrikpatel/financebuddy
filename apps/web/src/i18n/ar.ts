export default {
  translation: {
    app: {
      name: "FinanceBuddy",
      tagline: "مدربك المالي بالذكاء الاصطناعي",
    },
    nav: {
      dashboard: "لوحة التحكم",
      transactions: "المعاملات",
      budgets: "الميزانيات",
      goals: "الأهداف",
      debts: "سداد الديون",
      chat: "المدرب المالي",
      connections: "الحسابات المرتبطة",
      settings: "الإعدادات",
      logout: "تسجيل الخروج",
      primary: "Main navigation", // TODO-i18n: English placeholder
      openMenu: "Open menu", // TODO-i18n: English placeholder
    },
    auth: {
      welcome: "مرحبًا بعودتك",
      signIn: "تسجيل الدخول",
      signUp: "إنشاء حساب",
      email: "البريد الإلكتروني",
      password: "كلمة المرور",
      name: "الاسم الكامل",
      mfaCode: "رمز التحقق 2FA",
      mfaPrompt: "أدخل الرمز من تطبيق المصادقة الخاص بك",
      haveAccount: "هل لديك حساب بالفعل؟",
      noAccount: "مستخدم جديد؟",
      usePasskey: "استخدام مفتاح المرور / البصمة",
      mode: "Sign in or create an account", // TODO-i18n: English placeholder
      passwordHint: "At least 10 characters", // TODO-i18n: English placeholder
      mfaContinue: "Enter your 2FA code to continue.", // TODO-i18n: English placeholder
    },
    dash: {
      netWorth: "صافي الثروة",
      thisMonth: "إنفاق هذا الشهر",
      income: "الدخل (آخر 30 يومًا)",
      savingsRate: "معدل الادخار",
      cashflow: "التدفق النقدي والتوقعات",
      alerts: "التنبيهات",
      topCategories: "أهم الفئات",
      reviewNeeded: "تحتاج إلى مراجعة التصنيف",
      quickAdd: "إضافة مصروف سريع",
      quickAddHint: "مثال: \"12.40 قهوة في ستاربكس\"",
      add: "إضافة",
      forecast: "التوقعات",
      cashflowSummary: "Monthly net cash flow for {{count}} periods, the last two are forecasts.", // TODO-i18n: English placeholder
      net: "Net", // TODO-i18n: English placeholder
      noSpending: "No spending in the last 30 days.", // TODO-i18n: English placeholder
      allClear: "All clear, no alerts", // TODO-i18n: English placeholder
      quickAddLabel: "What did you spend?", // TODO-i18n: English placeholder
      chooseAccount: "Choose an account", // TODO-i18n: English placeholder
      at: "at", // TODO-i18n: English placeholder
      parse: "Read expense", // TODO-i18n: English placeholder
    },
    txns: {
      title: "المعاملات",
      search: "البحث في المتاجر والمعاملات…",
      needsReview: "المعاملات للمراجعة فقط",
      importCsv: "استيراد CSV/OFX",
      scanReceipt: "مسح الإيصال",
      split: "تقسيم بالذكاء الاصطناعي",
      confirmCategory: "تأكيد الفئة",
      uncategorized: "غير مصنف",
      category: "Category", // TODO-i18n: English placeholder
      allCategories: "All categories", // TODO-i18n: English placeholder
      emptyTitle: "No transactions yet", // TODO-i18n: English placeholder
      emptyBody: "Import a CSV or connect a bank to see your spending here.", // TODO-i18n: English placeholder
      date: "Date", // TODO-i18n: English placeholder
      merchant: "Merchant", // TODO-i18n: English placeholder
      amount: "Amount", // TODO-i18n: English placeholder
      splitBadge: "Split", // TODO-i18n: English placeholder
      review: "Review", // TODO-i18n: English placeholder
      learned: "Learned", // TODO-i18n: English placeholder
      categoryFor: "Category for {{merchant}}", // TODO-i18n: English placeholder
      createAccountFirst: "Create an account first.", // TODO-i18n: English placeholder
      chooseFile: "File", // TODO-i18n: English placeholder
      importHint: "CSV, OFX or QFX. Duplicates are skipped automatically.", // TODO-i18n: English placeholder
      importResult: "Imported {{created}}, skipped {{duplicates}} duplicates.", // TODO-i18n: English placeholder
      import: "Import", // TODO-i18n: English placeholder
      ocrUnavailable: "Receipt scanning is unavailable right now.", // TODO-i18n: English placeholder
      scan: "Scan", // TODO-i18n: English placeholder
    },
    budgets: {
      title: "الميزانيات",
      strategy: "الاستراتيجية",
      envelope: "طريقة الأظرف",
      zeroBased: "الميزانية الصفرية",
      allocated: "المخصص",
      spent: "المنفق",
      remaining: "المتبقي",
      suggestions: "اقتراحات الذكاء الاصطناعي (متوسط 3 أشهر)",
      create: "إنشاء ميزانية",
      overspent: "تجاوز الميزانية",
      assignLeft: "المتبقي للتخصيص",
      meterLabel: "{{name}}: {{pct}}% used", // TODO-i18n: English placeholder
      emptyTitle: "No budget yet", // TODO-i18n: English placeholder
      emptyBody: "Create your first envelope budget to get AI-suggested allocations.", // TODO-i18n: English placeholder
      name: "Budget name", // TODO-i18n: English placeholder
      plannedIncome: "Planned monthly income ({{currency}})", // TODO-i18n: English placeholder
      allocations: "Monthly allocations ({{currency}})", // TODO-i18n: English placeholder
      useAverage: "Use 3-month average", // TODO-i18n: English placeholder
    },
    goals: {
      title: "الأهداف",
      newGoal: "هدف جديد",
      target: "المبلغ المستهدف",
      saved: "المدخر",
      monthly: "المساهمة الشهرية",
      onTrack: "على المسار الصحيح",
      behind: "متأخر عن الجدول",
      contribute: "إضافة أموال",
      done: "Done", // TODO-i18n: English placeholder
      ofTarget: "of {{amount}}", // TODO-i18n: English placeholder
      meterLabel: "{{name}}: {{pct}}% saved", // TODO-i18n: English placeholder
      perMonth: "About {{amount}}/month", // TODO-i18n: English placeholder
      monthsLeft_one: "{{count}} month left", // TODO-i18n: English placeholder
      monthsLeft_other: "{{count}} months left", // TODO-i18n: English placeholder
      byDate: "by {{date}}", // TODO-i18n: English placeholder
      contributeTo: "Amount to add to {{name}}", // TODO-i18n: English placeholder
      amount: "Amount", // TODO-i18n: English placeholder
      emptyTitle: "No goals yet", // TODO-i18n: English placeholder
      emptyBody: "Create one and the AI advisor will track it for you.", // TODO-i18n: English placeholder
      name: "Goal name", // TODO-i18n: English placeholder
      namePlaceholder: "e.g. Emergency fund", // TODO-i18n: English placeholder
      targetAmount: "Target amount ({{currency}})", // TODO-i18n: English placeholder
      strategy: "Contribution strategy", // TODO-i18n: English placeholder
      fixedMonthly: "Fixed monthly amount", // TODO-i18n: English placeholder
      percentIncome: "% of income (adjusts automatically)", // TODO-i18n: English placeholder
      percentLabel: "Percent of income", // TODO-i18n: English placeholder
      targetDate: "Target date", // TODO-i18n: English placeholder
    },
    debts: {
      title: "سداد الديون",
      avalanche: "طريقة الانهيار الجليدي (أعلى فائدة أولاً)",
      snowball: "طريقة كرة الثلج (أصغر رصيد أولاً)",
      extraPayment: "دفعة شهرية إضافية",
      compare: "مقارنة الاستراتيجيات",
      interestSaved: "الفائدة الموفرة بطريقة الانهيار",
      addDebt: "إضافة دين",
      emptyTitle: "No debts tracked", // TODO-i18n: English placeholder
      emptyBody: "Track your first debt to unlock payoff simulations.", // TODO-i18n: English placeholder
      months_one: "{{count}} month", // TODO-i18n: English placeholder
      months_other: "{{count}} months", // TODO-i18n: English placeholder
      interest: "{{amount}} interest", // TODO-i18n: English placeholder
      monthsFaster_one: "{{count}} month faster", // TODO-i18n: English placeholder
      monthsFaster_other: "{{count}} months faster", // TODO-i18n: English placeholder
      trajectory: "Paydown trajectory", // TODO-i18n: English placeholder
      trajectorySummary: "Total remaining balance over the next {{count}} months using the avalanche strategy.", // TODO-i18n: English placeholder
      balance: "Balance", // TODO-i18n: English placeholder
      payoffOrder: "Payoff order", // TODO-i18n: English placeholder
      name: "Name", // TODO-i18n: English placeholder
      namePlaceholder: "e.g. Credit card", // TODO-i18n: English placeholder
      balanceLabel: "Balance ({{currency}})", // TODO-i18n: English placeholder
      apr: "APR %", // TODO-i18n: English placeholder
      minPayment: "Minimum payment", // TODO-i18n: English placeholder
    },
    coach: {
      title: "المدرب المالي",
      placeholder: "اسأل أي شيء حول أموالك وميزانيتك…",
      voice: "الإدخال الصوتي",
      modes: {
        auto: "تلقائي",
        coach: "مدرب التدفق النقدي",
        fraud: "فحص الاحتيال",
        budget: "الميزانيات",
        goals: "الأهداف",
        assistant: "General", // TODO-i18n: English placeholder
      },
      placeholderTab: "Ask about {{tab}}…", // TODO-i18n: English placeholder
      dockLabel: "Ask the AI coach about {{tab}}", // TODO-i18n: English placeholder
      open: "Open AI coach", // TODO-i18n: English placeholder
      send: "Send", // TODO-i18n: English placeholder
      stop: "Stop", // TODO-i18n: English placeholder
      newChat: "New chat", // TODO-i18n: English placeholder
      openInHub: "Open in AI Coach", // TODO-i18n: English placeholder
      contextOf: "Using what's on {{tab}}", // TODO-i18n: English placeholder
      emptyTitle: "Ask about {{tab}}", // TODO-i18n: English placeholder
      emptyBody: "The coach can see a summary of this page. Try one of these:", // TODO-i18n: English placeholder
      checkingData: "Checking your data…", // TODO-i18n: English placeholder
      errorReply: "The coach couldn't answer. Try again.", // TODO-i18n: English placeholder
      stopped: "Stopped", // TODO-i18n: English placeholder
      copy: "Copy", // TODO-i18n: English placeholder
      copied: "Copied", // TODO-i18n: English placeholder
      degradedTitle: "Basic mode", // TODO-i18n: English placeholder
      degradedBody: "No AI provider is configured, so answers come from built-in rules.", // TODO-i18n: English placeholder
      disclaimer: "Educational guidance, not financial advice.", // TODO-i18n: English placeholder
      hub: {
        conversations: "Conversations", // TODO-i18n: English placeholder
        search: "Search conversations", // TODO-i18n: English placeholder
        filterTab: "Filter by tab", // TODO-i18n: English placeholder
        filterDate: "Filter by date", // TODO-i18n: English placeholder
        allTabs: "All tabs", // TODO-i18n: English placeholder
        emptyTitle: "No conversations yet", // TODO-i18n: English placeholder
        emptyBody: "Ask the coach from any tab and the conversation shows up here.", // TODO-i18n: English placeholder
        pinned: "Pinned", // TODO-i18n: English placeholder
        pin: "Pin", // TODO-i18n: English placeholder
        unpin: "Unpin", // TODO-i18n: English placeholder
        rename: "Rename conversation", // TODO-i18n: English placeholder
        jumpBack: "Back to {{tab}}", // TODO-i18n: English placeholder
        pending_one: "{{count}} change waiting for you", // TODO-i18n: English placeholder
        pending_other: "{{count}} changes waiting for you", // TODO-i18n: English placeholder
        pendingBadge_one: "{{count}} to review", // TODO-i18n: English placeholder
        pendingBadge_other: "{{count}} to review", // TODO-i18n: English placeholder
        fromThread: "From \"{{title}}\" · {{tab}}", // TODO-i18n: English placeholder
        back: "Back to conversations", // TODO-i18n: English placeholder
        startedOn: "Started on {{tab}}", // TODO-i18n: English placeholder
        deleteTitle: "Delete conversation?", // TODO-i18n: English placeholder
        deleteBody: "\"{{title}}\" and its messages will be removed. This can't be undone.", // TODO-i18n: English placeholder
        range: {
          all: "Any time", // TODO-i18n: English placeholder
          today: "Today", // TODO-i18n: English placeholder
          week: "Last 7 days", // TODO-i18n: English placeholder
          month: "Last 30 days", // TODO-i18n: English placeholder
        },
      },
      blocks: {
        chart: "Chart", // TODO-i18n: English placeholder
        spendByCategory: "Spend by category", // TODO-i18n: English placeholder
        forecast: "Projected net cash flow", // TODO-i18n: English placeholder
        transactions_one: "{{count}} transaction", // TODO-i18n: English placeholder
        transactions_other: "{{count}} transactions", // TODO-i18n: English placeholder
        budget: "{{name}} · {{month}}", // TODO-i18n: English placeholder
        over: "{{amount}} over", // TODO-i18n: English placeholder
        left: "{{amount}} left", // TODO-i18n: English placeholder
      },
      action: {
        createGoal: "Create goal \"{{name}}\"", // TODO-i18n: English placeholder
        createBudget: "Create budget \"{{name}}\"", // TODO-i18n: English placeholder
        recategorize: "Move {{merchant}} to {{category}}", // TODO-i18n: English placeholder
        recategorizeBody_one: "{{count}} transaction ({{total}}) will be recategorized.", // TODO-i18n: English placeholder
        recategorizeBody_other: "{{count}} transactions ({{total}}) will be recategorized.", // TODO-i18n: English placeholder
        generic: "Suggested change", // TODO-i18n: English placeholder
        applied: "Applied", // TODO-i18n: English placeholder
        dismissed: "Dismissed", // TODO-i18n: English placeholder
        failed: "Couldn't apply this change.", // TODO-i18n: English placeholder
        nothingChanges: "Nothing changes until you confirm.", // TODO-i18n: English placeholder
      },
      prompts: {
        dashboard: {
          p1: "How is my cash flow trending?", // TODO-i18n: English placeholder
          p2: "What changed most this month?", // TODO-i18n: English placeholder
          p3: "Give me three ways to save this month", // TODO-i18n: English placeholder
        },
        transactions: {
          p1: "Find duplicate or unusual charges", // TODO-i18n: English placeholder
          p2: "What are my largest expenses this month?", // TODO-i18n: English placeholder
          p3: "Have any subscriptions gone up?", // TODO-i18n: English placeholder
        },
        budgets: {
          p1: "Where am I overspending this month?", // TODO-i18n: English placeholder
          p2: "Suggest a budget based on my spending", // TODO-i18n: English placeholder
          p3: "Which envelope should I adjust first?", // TODO-i18n: English placeholder
        },
        goals: {
          p1: "How do I reach my goal 2 months sooner?", // TODO-i18n: English placeholder
          p2: "Am I on track for all my goals?", // TODO-i18n: English placeholder
          p3: "Set up an emergency fund goal", // TODO-i18n: English placeholder
        },
        debts: {
          p1: "Avalanche or snowball for me?", // TODO-i18n: English placeholder
          p2: "How much interest do I save with 100 extra a month?", // TODO-i18n: English placeholder
          p3: "Which debt should I pay first?", // TODO-i18n: English placeholder
        },
        tax: {
          p1: "What deductions might I be missing?", // TODO-i18n: English placeholder
          p2: "Explain my estimated tax", // TODO-i18n: English placeholder
          p3: "How is my quarterly BAS calculated?", // TODO-i18n: English placeholder
        },
        family: {
          p1: "How much has the household spent this month?", // TODO-i18n: English placeholder
          p2: "Is anyone close to their limit?", // TODO-i18n: English placeholder
          p3: "Suggest fair monthly limits", // TODO-i18n: English placeholder
        },
        connections: {
          p1: "Which accounts should I connect first?", // TODO-i18n: English placeholder
          p2: "How is my bank data protected?", // TODO-i18n: English placeholder
          p3: "Why is a sync failing?", // TODO-i18n: English placeholder
        },
        aieval: {
          p1: "Explain how questions are routed", // TODO-i18n: English placeholder
          p2: "How is my personal data masked?", // TODO-i18n: English placeholder
          p3: "Why was this answer slow?", // TODO-i18n: English placeholder
        },
        settings: {
          p1: "How does the vault protect my data?", // TODO-i18n: English placeholder
          p2: "Should I turn on 2FA?", // TODO-i18n: English placeholder
          p3: "What does AI Diagnostics do?", // TODO-i18n: English placeholder
        },
        coach: {
          p1: "Give me a quick check-up of my finances", // TODO-i18n: English placeholder
          p2: "What should I focus on this month?", // TODO-i18n: English placeholder
          p3: "Help me build an emergency fund", // TODO-i18n: English placeholder
          p4: "Find subscriptions I could cancel", // TODO-i18n: English placeholder
        },
      },
    },
    common: {
      save: "حفظ",
      cancel: "إلغاء",
      delete: "حذف",
      loading: "جارٍ التحميل…",
      currency: "العملة",
      language: "اللغة",
      theme: "المظهر",
      dark: "داكن",
      light: "فاتح",
      useLight: "Switch to light theme", // TODO-i18n: English placeholder
      useDark: "Switch to dark theme", // TODO-i18n: English placeholder
      dismiss: "Dismiss", // TODO-i18n: English placeholder
      close: "Close", // TODO-i18n: English placeholder
      retry: "Try again", // TODO-i18n: English placeholder
      errorTitle: "Something went wrong", // TODO-i18n: English placeholder
      errorBody: "We couldn't load this. Check your connection and try again.", // TODO-i18n: English placeholder
      account: "Account", // TODO-i18n: English placeholder
      add: "Add", // TODO-i18n: English placeholder
      optional: "Optional", // TODO-i18n: English placeholder
      confirm: "Confirm", // TODO-i18n: English placeholder
    },
    settings: {
      title: "الإعدادات",
      security: "الأمان",
      vault: "خزنة المعرفة الصفرية",
      vaultSetup: "تعيين عبارة مرور الخزنة (تشفير الملاحظات طرفًا لطرف)",
      passkeys: "مفاتيح المرور والمصادقة الحيوية",
      registerPasskey: "تسجيل هذا الجهاز",
      sessions: "الجلسات النشطة",
      revokeAll: "إلغاء جميع الجلسات",
      profile: "Profile", // TODO-i18n: English placeholder
      mfaOn: "2FA on", // TODO-i18n: English placeholder
      mfaOff: "2FA off", // TODO-i18n: English placeholder
      baseCurrency: "Base currency {{currency}}", // TODO-i18n: English placeholder
      preferences: "Preferences", // TODO-i18n: English placeholder
      revokeHelp: "Signs you out everywhere, including this device.", // TODO-i18n: English placeholder
      disableMfa: "Turn off 2FA", // TODO-i18n: English placeholder
      recoveryCodes: "Recovery codes. Store them somewhere safe:", // TODO-i18n: English placeholder
      enableMfa: "Turn on 2FA", // TODO-i18n: English placeholder
      addSecret: "Add this secret to your authenticator app:", // TODO-i18n: English placeholder
      verifyCode: "Verification code", // TODO-i18n: English placeholder
      vaultRegistered: "Your vault is registered. Sensitive fields and notes are end-to-end encrypted.", // TODO-i18n: English placeholder
      vaultUnlocked: "Vault unlocked for this session", // TODO-i18n: English placeholder
      vaultLockedMsg: "Vault locked.", // TODO-i18n: English placeholder
      lockVault: "Lock vault", // TODO-i18n: English placeholder
      vaultPassphrase: "Vault passphrase", // TODO-i18n: English placeholder
      vaultUnlockedMsg: "Vault unlocked.", // TODO-i18n: English placeholder
      vaultUnlockFailed: "Couldn't unlock the vault: {{detail}}", // TODO-i18n: English placeholder
      unlockVault: "Unlock vault", // TODO-i18n: English placeholder
      vaultMinLength: "At least 8 characters", // TODO-i18n: English placeholder
      vaultCreatedMsg: "Vault created on this device.", // TODO-i18n: English placeholder
      createVault: "Create vault", // TODO-i18n: English placeholder
      noPasskeys: "No passkeys registered.", // TODO-i18n: English placeholder
    },
    family: {
      createFailed: "Couldn't create the family group.", // TODO-i18n: English placeholder
      inviteFailed: "Couldn't invite that member.", // TODO-i18n: English placeholder
      updateFailed: "Couldn't update that member.", // TODO-i18n: English placeholder
      removeFailed: "Couldn't remove that member.", // TODO-i18n: English placeholder
      groupBadge: "Family group", // TODO-i18n: English placeholder
      acrossMembers_one: "Across {{count}} active member", // TODO-i18n: English placeholder
      acrossMembers_other: "Across {{count}} active members", // TODO-i18n: English placeholder
      registeredTotal_one: "{{count}} registered in total", // TODO-i18n: English placeholder
      registeredTotal_other: "{{count}} registered in total", // TODO-i18n: English placeholder
      withLimits: "With active spending limits", // TODO-i18n: English placeholder
      limitMeter: "{{name}}: {{pct}}% of monthly limit used", // TODO-i18n: English placeholder
      pctUsed: "{{pct}}% used", // TODO-i18n: English placeholder
      remainingAmount: "{{amount}} remaining", // TODO-i18n: English placeholder
      removeNamed: "Remove {{name}}", // TODO-i18n: English placeholder
    },
    tax: {
      saveProfileFailed: "Couldn't save the tax profile.", // TODO-i18n: English placeholder
      addDeductionFailed: "Couldn't add the deduction.", // TODO-i18n: English placeholder
      fy: "FY {{year}}", // TODO-i18n: English placeholder
      atoBrackets: "ATO standard brackets", // TODO-i18n: English placeholder
      gstRegisteredBadge: "GST registered (10%)", // TODO-i18n: English placeholder
      noGst: "No GST", // TODO-i18n: English placeholder
      abnValue: "ABN {{abn}}", // TODO-i18n: English placeholder
      noAbn: "No ABN recorded", // TODO-i18n: English placeholder
      australia: "Australia", // TODO-i18n: English placeholder
      effectiveRateValue: "Effective rate {{pct}}%", // TODO-i18n: English placeholder
      marginalRateValue: "Top marginal rate {{pct}}%", // TODO-i18n: English placeholder
      grossIncomeValue: "Gross income {{amount}}", // TODO-i18n: English placeholder
      claimedEntries_one: "{{count}} claimed entry", // TODO-i18n: English placeholder
      claimedEntries_other: "{{count}} claimed entries", // TODO-i18n: English placeholder
      bracketsTitle: "Progressive tax calculation", // TODO-i18n: English placeholder
      ratePct: "{{pct}}% tax", // TODO-i18n: English placeholder
      taxable: "Taxable", // TODO-i18n: English placeholder
      tax: "Tax", // TODO-i18n: English placeholder
      suggestionCount_one: "{{count}} suggestion", // TODO-i18n: English placeholder
      suggestionCount_other: "{{count}} suggestions", // TODO-i18n: English placeholder
      matchPct: "{{pct}}% match", // TODO-i18n: English placeholder
      deduction: "Deduction", // TODO-i18n: English placeholder
      generalBusiness: "General business", // TODO-i18n: English placeholder
      receipt: "Receipt", // TODO-i18n: English placeholder
      deleteDeduction: "Delete deduction", // TODO-i18n: English placeholder
      g1Help: "Gross sales including GST", // TODO-i18n: English placeholder
      g1aHelp: "1/11th of total GST sales", // TODO-i18n: English placeholder
      g1bHelp: "GST input credits claimed", // TODO-i18n: English placeholder
      amountCurrency: "Amount ({{currency}})", // TODO-i18n: English placeholder
      gstAutoHint: "Leave empty to use 1/11th", // TODO-i18n: English placeholder
    },
    connections: {
      portalOpened: "Opened the connection portal for {{name}}.", // TODO-i18n: English placeholder
      linkTokenReady: "Link token ready: {{token}}", // TODO-i18n: English placeholder
      connectedGeneric: "{{name}} connected.", // TODO-i18n: English placeholder
      providerUnavailable: "Provider unavailable. The sandbox banking flow is active.", // TODO-i18n: English placeholder
      stripeConnected: "Stripe business account connected.", // TODO-i18n: English placeholder
      stripeFailed: "Couldn't connect that Stripe key.", // TODO-i18n: English placeholder
      synced_one: "Synced {{count}} new transaction.", // TODO-i18n: English placeholder
      synced_other: "Synced {{count}} new transactions.", // TODO-i18n: English placeholder
      syncedWithAccounts_one: "Synced {{count}} new transaction ({{accounts}}).", // TODO-i18n: English placeholder
      syncedWithAccounts_other: "Synced {{count}} new transactions ({{accounts}}).", // TODO-i18n: English placeholder
      syncError: "Sync failed: {{detail}}", // TODO-i18n: English placeholder
      disconnected: "Connection removed.", // TODO-i18n: English placeholder
      regionFilter: "Filter providers by region", // TODO-i18n: English placeholder
      banksSupported: "{{count}} major banks supported", // TODO-i18n: English placeholder
      relinkNamed: "Re-link {{name}}", // TODO-i18n: English placeholder
      connectNamed: "Connect {{name}}", // TODO-i18n: English placeholder
      relink: "Re-link", // TODO-i18n: English placeholder
      connect: "Connect", // TODO-i18n: English placeholder
      businessBadge: "Business & accounting", // TODO-i18n: English placeholder
      globalProviders: "Global open banking providers", // TODO-i18n: English placeholder
      sandbox: "Sandbox", // TODO-i18n: English placeholder
      global: "Global", // TODO-i18n: English placeholder
      disconnectNamed: "Disconnect {{name}}", // TODO-i18n: English placeholder
      stripeKeyHint: "Use a restricted or secret key from the Stripe Dashboard (sk_test_, sk_live_ or rk_live_).", // TODO-i18n: English placeholder
    },
    aiEval: {
      refresh: "Refresh logs", // TODO-i18n: English placeholder
      acrossSessions: "Across all sessions", // TODO-i18n: English placeholder
      ms: "{{ms}} ms", // TODO-i18n: English placeholder
      supervisorModel: "Supervisor + model execution", // TODO-i18n: English placeholder
      promptCompletion: "Prompt + completion", // TODO-i18n: English placeholder
      redactions: "Account and card redactions", // TODO-i18n: English placeholder
      defaultQuery: "Financial query", // TODO-i18n: English placeholder
      tokensInOut: "{{in}} in / {{out}} out", // TODO-i18n: English placeholder
      pagination: "Log pages", // TODO-i18n: English placeholder
      showing: "Showing {{from}}-{{to}} of {{total}}", // TODO-i18n: English placeholder
      prev: "Previous page", // TODO-i18n: English placeholder
      next: "Next page", // TODO-i18n: English placeholder
      pageOf: "Page {{page}} of {{total}}", // TODO-i18n: English placeholder
    },
    alerts: {
      label: "Alerts", // TODO-i18n: English placeholder
      labelUnread_one: "Alerts, {{count}} unread", // TODO-i18n: English placeholder
      labelUnread_other: "Alerts, {{count}} unread", // TODO-i18n: English placeholder
      empty: "No alerts. All clear.", // TODO-i18n: English placeholder
    },
  },
};
