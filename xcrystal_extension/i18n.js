// XCrystal Internationalization — shared by popup and content_scripts
const I18N = {
  zh: {
    clickToAnalyze: "点击分析此推文",
    analyzing: "分析中...",
    analysisFailed: "分析失败",
    error: "错误",
    title: "XCrystal",
    subtitle: "加密货币推文分析",
    mode: "分析模式",
    analysisMode: "分析模式",
    manual: "手动",
    auto: "自动",
    language: "语言",
    server: "服务器",
    serverUrl: "服务器地址",
    serverConnected: "服务器已连接",
    serverDisconnected: "服务器未连接",
    startServer: "启动 server.py",
    cache: "缓存",
    entries: "条",
    clearCache: "清空缓存",
    save: "保存",
    saved: "已保存",
    autoModeDesc: "自动模式：可见推文自动分析",
    manualModeDesc: "手动模式：点击按钮分析推文",
    bullish: "看涨",
    bearish: "看跌",
    neutral: "中性",
    uncertain: "不确定",
    low: "低",
    medium: "中",
    high: "高",
    extreme: "极高",
    btc_eth_macro: "大盘/宏观",
    sector: "板块",
    single_asset: "单币",
    none: "无关",
    not_related: "无关",
  },
  en: {
    clickToAnalyze: "Click to analyze",
    analyzing: "Analyzing...",
    analysisFailed: "Analysis failed",
    error: "Error",
    title: "XCrystal",
    subtitle: "Crypto Tweet Analysis",
    mode: "Analysis Mode",
    analysisMode: "Analysis Mode",
    manual: "Manual",
    auto: "Auto",
    language: "Language",
    server: "Server",
    serverUrl: "Server URL",
    serverConnected: "Server Connected",
    serverDisconnected: "Server Disconnected",
    startServer: "Start server.py",
    cache: "Cache",
    entries: "entries",
    clearCache: "Clear Cache",
    save: "Save",
    saved: "Saved",
    autoModeDesc: "Auto mode: visible tweets are analyzed automatically",
    manualModeDesc: "Manual mode: click the button to analyze a tweet",
    bullish: "Bullish",
    bearish: "Bearish",
    neutral: "Neutral",
    uncertain: "Uncertain",
    low: "Low",
    medium: "Medium",
    high: "High",
    extreme: "Extreme",
    btc_eth_macro: "BTC/ETH & macro",
    sector: "Sector",
    single_asset: "Single asset",
    none: "None",
    not_related: "Not related",
  }
};

function t(key) {
  const lang =
    (typeof window !== "undefined" && window.__xcrystal_lang) ||
    (typeof currentLang !== "undefined" && currentLang) ||
    "zh";
  const table = I18N[lang] || I18N.zh;
  return (table && table[key]) || (I18N.zh && I18N.zh[key]) || key;
}

function setXCrystalLang(lang) {
  if (typeof window !== "undefined") {
    window.__xcrystal_lang = lang === "en" ? "en" : "zh";
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { I18N, t, setXCrystalLang };
}
