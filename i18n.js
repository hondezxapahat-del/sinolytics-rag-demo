// Lightweight EN/ZH interface dictionary + toggle. No framework, no build
// step — matches the rest of this project's plain HTML/JS pages.
// See docs/TechSpec_v1.2.md §4.4.
//
// Usage per page:
//   <script src="i18n.js"></script>
//   ... at the end of the page's own <script>: initLanguageToggle();
//
// Static text: tag the element with data-i18n="key" (uses textContent),
// data-i18n-html="key" (uses innerHTML, for markup like <span> accents),
// or data-i18n-placeholder="key" (for <input>/<textarea> placeholders).
// A chip-style element can also carry data-i18n-q="key" to swap a
// data-q attribute (the literal question text sent to the backend)
// alongside its visible label.
//
// Dynamic/JS-generated text: call t('key') to read the current language's
// string directly. Register onLanguageChange(fn) for anything that needs
// to re-render itself (not just static markup) when the language flips.

const I18N_DICT = {
  en: {
    account_logout: "Log out",
    account_signin: "Sign in",

    idx_cta: "Start Your Consultation",
    idx_meta_founded: "Founded",
    idx_meta_offices: "Offices",
    idx_meta_hub: "Geolytics Hub",
    idx_sub: "We turn regulatory complexity, supply chain exposure, and shifting policy signals into clear, decision-ready intelligence — built by analysts who read Beijing and Brussels equally well.",
    idx_headline_html: 'Your <span>China Strategy</span><br>& Geopolitics<br>Experts',

    login_title_signin: "Sign in",
    login_title_signup: "Create an account",
    login_label_username: "Username",
    login_label_password: "Password",
    login_btn_signin: "Sign in",
    login_btn_signup: "Sign up",
    login_toggle_to_signup_pre: "No account yet?",
    login_toggle_to_signup_link: "Sign up",
    login_toggle_to_signin_pre: "Already have an account?",
    login_toggle_to_signin_link: "Sign in",

    ask_new_chat: "+ New chat",
    ask_greeting_html: 'What would you like to know about<br><span class="accent">China\'s policy landscape</span>?',
    ask_chip1_label: "Why are Chinese AI models cheaper?",
    ask_chip1_q: "Why are Chinese AI models so much cheaper?",
    ask_chip2_label: "Battery supply chain risks",
    ask_chip2_q: "What are the key risks in China's battery supply chain?",
    ask_chip3_label: "China's export controls strategy",
    ask_chip3_q: "How is China using export controls as a geopolitical tool?",
    ask_chip4_label: "Show EV price trend chart",
    ask_chip4_q: "Show me a chart of the EV price trend over the past year",
    ask_placeholder: "Ask a follow-up, or start a new topic…",
    ask_hint: "Answers may combine internal reports and live web results — sources are always labeled.",
    ask_no_conversations: "No conversations yet.",
    ask_load_history_error: "Couldn't load history.",
    ask_delete_confirm: 'Delete "{title}"?',
    ask_thinking_1: "Reading your question…",
    ask_thinking_2: "Searching internal reports…",
    ask_thinking_3: "Checking relevance of sources…",
    ask_thinking_4: "Drafting a structured answer…",
    ask_tag_web: "Live web search",
    ask_tag_prediction: "Trend prediction",
    ask_tag_internal: "Internal knowledge",
    ask_note_web_html: "<b>Note:</b> preliminary signal from a live web search — pending expert review, not a finalized Sinolytics assessment.",
    ask_note_internal_prefix_html: "<b>Based on our prior analysis:</b> ",
    ask_internal_analysis_label: "Sinolytics' prior analysis on this topic",
    ask_prediction_label: "Human-confirmed prediction",
    ask_prediction_pending_label: "Related internal analysis (prediction pending human review)",
    ask_source_prefix: "Source:",
    ask_session_expired: "Session expired",
    ask_conversation_load_error_prefix: "Couldn't load this conversation:",
    ask_generic_error_prefix: "Something went wrong:",
  },
  zh: {
    account_logout: "登出",
    account_signin: "登录",

    idx_cta: "开始咨询",
    idx_meta_founded: "创立",
    idx_meta_offices: "办公地点",
    idx_meta_hub: "地缘信息中心",
    idx_sub: "我们将复杂的监管环境、供应链风险和不断变化的政策信号，转化为清晰、可直接用于决策的洞察——由同样精通北京与布鲁塞尔视角的分析师团队打造。",
    idx_headline_html: '您的<span>中国战略</span><br>与地缘政治专家',

    login_title_signin: "登录",
    login_title_signup: "创建账号",
    login_label_username: "用户名",
    login_label_password: "密码",
    login_btn_signin: "登录",
    login_btn_signup: "注册",
    login_toggle_to_signup_pre: "还没有账号？",
    login_toggle_to_signup_link: "注册",
    login_toggle_to_signin_pre: "已经有账号？",
    login_toggle_to_signin_link: "登录",

    ask_new_chat: "+ 新对话",
    ask_greeting_html: '想了解<span class="accent">中国政策动态</span>的哪些方面？',
    ask_chip1_label: "中国AI模型为何更便宜？",
    ask_chip1_q: "为什么中国的AI模型价格便宜这么多？",
    ask_chip2_label: "电池供应链风险",
    ask_chip2_q: "中国电池供应链面临哪些主要风险？",
    ask_chip3_label: "中国的出口管制策略",
    ask_chip3_q: "中国如何将出口管制用作地缘政治工具？",
    ask_chip4_label: "查看电动车价格趋势图",
    ask_chip4_q: "给我看一下过去一年电动车价格趋势的图表",
    ask_placeholder: "追问一个问题，或开始新的话题…",
    ask_hint: "回答可能综合内部报告与实时网络结果——来源始终会标注清楚。",
    ask_no_conversations: "暂无对话记录。",
    ask_load_history_error: "历史记录加载失败。",
    ask_delete_confirm: '删除"{title}"？',
    ask_thinking_1: "正在阅读你的问题…",
    ask_thinking_2: "正在搜索内部报告…",
    ask_thinking_3: "正在核对资料相关性…",
    ask_thinking_4: "正在撰写结构化回答…",
    ask_tag_web: "实时网络搜索",
    ask_tag_prediction: "趋势预测",
    ask_tag_internal: "内部知识库",
    ask_note_web_html: "<b>提示：</b>这是来自实时网络搜索的初步信号——尚待专家审核，并非 Sinolytics 的最终结论。",
    ask_note_internal_prefix_html: "<b>基于我们此前的分析：</b>",
    ask_internal_analysis_label: "Sinolytics 关于该话题的既有分析",
    ask_prediction_label: "已经过人工确认的预测",
    ask_prediction_pending_label: "相关内部分析（预测尚待人工审核）",
    ask_source_prefix: "来源：",
    ask_session_expired: "登录已过期",
    ask_conversation_load_error_prefix: "对话加载失败：",
    ask_generic_error_prefix: "出错了：",
  },
};

function getLanguage() {
  return localStorage.getItem('site_language') || 'en';
}

const _languageChangeHandlers = [];

function onLanguageChange(fn) {
  _languageChangeHandlers.push(fn);
}

function t(key) {
  const dict = I18N_DICT[getLanguage()] || I18N_DICT.en;
  return dict[key] !== undefined ? dict[key] : key;
}

function applyLanguage(lang) {
  const dict = I18N_DICT[lang] || I18N_DICT.en;
  document.documentElement.lang = lang;

  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const key = el.getAttribute('data-i18n');
    if (dict[key] !== undefined) el.textContent = dict[key];
  });
  document.querySelectorAll('[data-i18n-html]').forEach((el) => {
    const key = el.getAttribute('data-i18n-html');
    if (dict[key] !== undefined) el.innerHTML = dict[key];
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
    const key = el.getAttribute('data-i18n-placeholder');
    if (dict[key] !== undefined) el.placeholder = dict[key];
  });
  document.querySelectorAll('[data-i18n-q]').forEach((el) => {
    const key = el.getAttribute('data-i18n-q');
    if (dict[key] !== undefined) el.setAttribute('data-q', dict[key]);
  });
  document.querySelectorAll('.lang-toggle').forEach((btn) => {
    btn.textContent = lang === 'en' ? '中文' : 'EN';
  });

  _languageChangeHandlers.forEach((fn) => fn(lang));
}

function setLanguage(lang) {
  localStorage.setItem('site_language', lang);
  applyLanguage(lang);
}

// Call once per page, after the page's own DOM/listeners are set up.
function initLanguageToggle() {
  applyLanguage(getLanguage());
  document.querySelectorAll('.lang-toggle').forEach((btn) => {
    btn.addEventListener('click', () => {
      setLanguage(getLanguage() === 'en' ? 'zh' : 'en');
    });
  });
}
