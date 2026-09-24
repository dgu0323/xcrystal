// XCrystal - Popup Script
// Canonical chrome.storage.local keys: language, mode, serverUrl

let currentLang = "zh";
let currentMode = "manual";
let currentServerUrl = "http://localhost:5678";
let serverOk = false;

document.addEventListener("DOMContentLoaded", async () => {
  console.log("XCrystal: Popup loaded");

  try {
    const stored = await chrome.storage.local.get(["language", "lang", "mode", "serverUrl"]);
    currentLang = stored.language || stored.lang || "zh";
    currentMode = stored.mode || "manual";
    currentServerUrl = stored.serverUrl || "http://localhost:5678";
    console.log("XCrystal: Language", currentLang, "Mode", currentMode, "Server", currentServerUrl);
  } catch (e) {
    console.error("XCrystal: Failed to load settings:", e);
  }

  setXCrystalLang(currentLang);
  updateUI();
  checkServer();

  const langZhBtn = document.getElementById("langZh");
  const langEnBtn = document.getElementById("langEn");
  const modeManualBtn = document.getElementById("modeManual");
  const modeAutoBtn = document.getElementById("modeAuto");
  const serverUrlInput = document.getElementById("serverUrl");

  if (langZhBtn) langZhBtn.addEventListener("click", () => switchLang("zh"));
  if (langEnBtn) langEnBtn.addEventListener("click", () => switchLang("en"));
  if (modeManualBtn) modeManualBtn.addEventListener("click", () => switchMode("manual"));
  if (modeAutoBtn) modeAutoBtn.addEventListener("click", () => switchMode("auto"));
  if (serverUrlInput) {
    serverUrlInput.value = currentServerUrl;
    serverUrlInput.addEventListener("change", async (e) => {
      const newUrl = e.target.value.trim().replace(/\/+$/, "");
      if (newUrl && newUrl !== currentServerUrl) {
        currentServerUrl = newUrl;
        await chrome.storage.local.set({ serverUrl: newUrl });
        console.log("XCrystal: Server URL updated:", newUrl);
        checkServer();
      }
    });
  }
});

function updateUI() {
  setXCrystalLang(currentLang);
  const isZh = currentLang === "zh";
  const isAuto = currentMode === "auto";

  document.getElementById("subtitle").textContent = t("subtitle");
  document.getElementById("statusText").textContent = serverOk
    ? t("serverConnected")
    : t("serverDisconnected");

  document.getElementById("modeLabel").textContent = t("analysisMode");
  document.getElementById("langLabel").textContent = t("language");
  document.getElementById("serverLabel").textContent = t("server");

  document.getElementById("modeManual").classList.toggle("active", !isAuto);
  document.getElementById("modeAuto").classList.toggle("active", isAuto);
  document.getElementById("modeManual").textContent = t("manual");
  document.getElementById("modeAuto").textContent = t("auto");

  document.getElementById("modeDesc").textContent = isAuto
    ? t("autoModeDesc")
    : t("manualModeDesc");

  document.getElementById("langZh").classList.toggle("active", isZh);
  document.getElementById("langEn").classList.toggle("active", !isZh);

  const serverUrlInput = document.getElementById("serverUrl");
  if (serverUrlInput && document.activeElement !== serverUrlInput) {
    serverUrlInput.value = currentServerUrl;
  }
}

async function switchLang(lang) {
  currentLang = lang === "en" ? "en" : "zh";
  setXCrystalLang(currentLang);
  try {
    // Canonical key: language (also clear legacy ambiguity by writing language only)
    await chrome.storage.local.set({ language: currentLang });
  } catch (e) {
    console.error("Failed to save language:", e);
  }
  updateUI();
}

async function switchMode(mode) {
  currentMode = mode === "auto" ? "auto" : "manual";
  try {
    await chrome.storage.local.set({ mode: currentMode });
  } catch (e) {
    console.error("Failed to save mode:", e);
  }
  updateUI();
}

async function checkServer() {
  const statusDot = document.getElementById("statusDot");
  const statusText = document.getElementById("statusText");

  try {
    const response = await new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ action: "health" }, (res) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve(res);
        }
      });
    });

    const status =
      (response && response.status) ||
      (response && response.data && response.data.status);
    serverOk = !!(response && response.success !== false && status === "ok");

    if (serverOk) {
      statusDot.classList.add("connected");
      statusText.textContent = t("serverConnected");
    } else {
      throw new Error("Server error");
    }
  } catch (error) {
    serverOk = false;
    statusDot.classList.remove("connected");
    statusText.textContent = t("serverDisconnected");
  }
}
