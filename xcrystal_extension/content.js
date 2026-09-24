// XCrystal Content Script
// Canonical chrome.storage.local keys: language (+legacy lang), mode, serverUrl
(function() {
  "use strict";

  let currentLang = "zh";
  let currentMode = "manual"; // "manual" | "auto"
  const tweetStore = new Map();
  const HOOK_SOURCE = "xcrystal-page-hook";
  const CONTENT_SOURCE = "xcrystal-content";
  const ATTR_ANALYZING = "data-xcrystal-analyzing";
  const ATTR_DONE = "data-xcrystal-done";
  const MAX_IN_FLIGHT = 2;

  // bar -> { status: 'idle'|'loading'|'done'|'error', result?: object }
  const barState = new WeakMap();
  const autoQueue = [];
  let inFlight = 0;
  let intersectionObserver = null;

  function t(key) {
    if (typeof I18N !== "undefined") {
      const table = I18N[currentLang] || I18N.zh || {};
      if (table[key]) return table[key];
      if (I18N.zh && I18N.zh[key]) return I18N.zh[key];
    }
    return key;
  }

  function syncLangGlobal() {
    if (typeof window !== "undefined") {
      window.__xcrystal_lang = currentLang;
    }
    if (typeof setXCrystalLang === "function") {
      setXCrystalLang(currentLang);
    }
  }

  function loadConfig() {
    return new Promise((resolve) => {
      chrome.storage.local.get(["language", "lang", "mode", "serverUrl"], (result) => {
        currentLang = result.language || result.lang || "zh";
        currentMode = result.mode === "auto" ? "auto" : "manual";
        syncLangGlobal();
        resolve(result);
      });
    });
  }

  function getTweetId(article) {
    const timeEl = article.querySelector("time");
    if (timeEl && timeEl.parentElement) {
      const href = timeEl.parentElement.getAttribute("href");
      if (href) {
        const match = href.match(/\/status\/(\d+)/);
        return match ? match[1] : null;
      }
    }
    const m = location.pathname.match(/\/status\/(\d+)/);
    if (m && article.querySelector('[data-testid="tweetText"], [data-testid="User-Name"]')) {
      const articles = document.querySelectorAll('article[data-testid="tweet"]');
      if (articles.length && articles[0] === article) return m[1];
    }
    return null;
  }

  function getDomMainTextEl(article) {
    const nodes = article.querySelectorAll('[data-testid="tweetText"]');
    for (const el of nodes) {
      if (!el.closest('div[role="link"]')) return el;
    }
    return null;
  }

  function getDomMainText(article) {
    const el = getDomMainTextEl(article);
    return el ? el.innerText.trim() : "";
  }

  function requestTweetDetail(tweetId, timeoutMs) {
    return new Promise((resolve) => {
      if (!tweetId) { resolve(false); return; }
      if (tweetStore.has(tweetId)) { resolve(true); return; }
      const timer = setTimeout(() => {
        window.removeEventListener("message", onMsg);
        resolve(tweetStore.has(tweetId));
      }, timeoutMs || 2500);
      function onMsg(event) {
        if (event.source !== window) return;
        const msg = event.data;
        if (!msg || msg.source !== HOOK_SOURCE) return;
        if (msg.type === "TWEETS" && Array.isArray(msg.tweets)) {
          for (const tw of msg.tweets) {
            if (tw && tw.id) tweetStore.set(String(tw.id), tw);
          }
          if (tweetStore.has(tweetId)) {
            clearTimeout(timer);
            window.removeEventListener("message", onMsg);
            resolve(true);
          }
        }
        if (msg.type === "FETCH_DONE" && String(msg.tweetId) === String(tweetId)) {
          clearTimeout(timer);
          window.removeEventListener("message", onMsg);
          resolve(!!msg.ok && tweetStore.has(tweetId));
        }
      }
      window.addEventListener("message", onMsg);
      window.postMessage(
        { source: CONTENT_SOURCE, type: "FETCH_TWEET", tweetId: String(tweetId) },
        window.location.origin
      );
    });
  }

  function formatStoredTweet(tw) {
    if (!tw) return "";
    let text = tw.text || "";
    if (tw.quoted && tw.quoted.text) {
      text = text + "\n\nQT: " + tw.quoted.text;
    }
    return text.trim();
  }

  async function resolveTweetPayload(article) {
    const id = getTweetId(article);
    const domText = getDomMainText(article);

    if (id && !tweetStore.has(id)) {
      await requestTweetDetail(id, 2500);
    }

    if (id && tweetStore.has(id)) {
      const tw = tweetStore.get(id);
      const full = formatStoredTweet(tw);
      if (full) {
        return { id, tweet: full, source: tw.text_source || "graphql" };
      }
    }

    if (domText) {
      return { id, tweet: domText, source: "dom" };
    }

    return { id, tweet: "", source: "none" };
  }

  function renderResultHtml(result) {
    const relevancePercent = Math.round((result.volatile || 0) * 100);

    // Gated / not related: show only % + 无关/Not related (no direction/impact)
    const gated = result.gated === true || result.relevant === false;
    if (gated) {
      return `
      <span class="xcrystal-tag xcrystal-tag-primary">${relevancePercent}%</span>
      <span class="xcrystal-tag xcrystal-scope-none xcrystal-gated">${t("not_related")}</span>
    `;
    }

    const impactKey = result.impact || "medium";
    const impactEmoji = { low: "💧", medium: "💥", high: "🔥", extreme: "☄️" }[impactKey] || "💥";

    // Scope tag (graceful if older server omits scope)
    let scopeHtml = "";
    if (result.scope) {
      const scopeKey = result.scope;
      scopeHtml = `<span class="xcrystal-tag xcrystal-scope-${scopeKey}">${t(scopeKey)}</span>`;
    }

    // Direction: show Uncertain (grey) when server marks uncertain
    let dirHtml;
    if (result.uncertain) {
      dirHtml = `<span class="xcrystal-tag xcrystal-dir-uncertain">${t("uncertain")}</span>`;
    } else {
      const dirKey = result.direction || "neutral";
      const dirEmoji = { bullish: "📈", bearish: "📉", neutral: "➡️" }[dirKey] || "➡️";
      dirHtml = `<span class="xcrystal-tag xcrystal-dir-${dirKey}">${dirEmoji}${t(dirKey)}</span>`;
    }

    return `
      <span class="xcrystal-tag xcrystal-tag-primary">${relevancePercent}%</span>
      ${scopeHtml}
      ${dirHtml}
      <span class="xcrystal-tag xcrystal-impact-${impactKey}">${impactEmoji}${t(impactKey)}</span>
    `;
  }

  function paintIdleBar(bar, article) {
    bar.innerHTML = "";
    const img = document.createElement("img");
    img.className = "xcrystal-crystal";
    img.src = chrome.runtime.getURL("icons/icon48.png");
    img.title = t("clickToAnalyze");
    img.addEventListener("click", function(e) {
      e.preventDefault();
      e.stopPropagation();
      analyzeTweet(article, { auto: false });
    });
    const hint = document.createElement("span");
    hint.className = "xcrystal-hint";
    hint.textContent = t("clickToAnalyze");
    bar.appendChild(img);
    bar.appendChild(hint);
    barState.set(bar, { status: "idle" });
  }

  function paintLoadingBar(bar) {
    bar.innerHTML = `
      <img class="xcrystal-crystal" src="${chrome.runtime.getURL("icons/icon48.png")}">
      <span class="xcrystal-loading"></span>
      <span class="xcrystal-hint">${t("analyzing")}</span>
    `;
    const prev = barState.get(bar) || {};
    barState.set(bar, { status: "loading", result: prev.result });
  }

  function paintDoneBar(bar, result) {
    bar.innerHTML = `
      <img class="xcrystal-crystal" src="${chrome.runtime.getURL("icons/icon48.png")}">
      ${renderResultHtml(result)}
    `;
    barState.set(bar, { status: "done", result });
  }

  function paintErrorBar(bar) {
    bar.innerHTML = `
      <img class="xcrystal-crystal" src="${chrome.runtime.getURL("icons/icon48.png")}">
      <span class="xcrystal-error">${t("analysisFailed")}</span>
    `;
    barState.set(bar, { status: "error" });
  }

  function refreshAllBarLabels() {
    document.querySelectorAll(".xcrystal-bar").forEach((bar) => {
      const st = barState.get(bar);
      if (!st) return;
      if (st.status === "idle") {
        const article = bar.closest('article[data-testid="tweet"]');
        if (article) paintIdleBar(bar, article);
      } else if (st.status === "loading") {
        paintLoadingBar(bar);
      } else if (st.status === "done" && st.result) {
        paintDoneBar(bar, st.result);
      } else if (st.status === "error") {
        paintErrorBar(bar);
      }
    });
  }

  async function analyzeTweet(article, opts) {
    const auto = !!(opts && opts.auto);
    const bar = article.querySelector(".xcrystal-bar");
    if (!bar) return;

    // Idempotent guards — set BEFORE await
    if (article.getAttribute(ATTR_ANALYZING) === "1") return;
    if (auto && article.getAttribute(ATTR_DONE) === "1") return;

    article.setAttribute(ATTR_ANALYZING, "1");
    paintLoadingBar(bar);

    try {
      const payload = await resolveTweetPayload(article);
      if (!payload.tweet) {
        paintErrorBar(bar);
        article.removeAttribute(ATTR_ANALYZING);
        // Don't mark done on empty — may get text later after GraphQL
        return;
      }

      const response = await new Promise((resolve, reject) => {
        chrome.runtime.sendMessage(
          { action: "analyze", tweet: payload.tweet, id: payload.id },
          (result) => {
            if (chrome.runtime.lastError) {
              reject(new Error(chrome.runtime.lastError.message));
            } else {
              resolve(result);
            }
          }
        );
      });

      if (!response || !response.success) {
        throw new Error((response && response.error) || "unknown");
      }

      paintDoneBar(bar, response.data);
      article.setAttribute(ATTR_DONE, "1");
    } catch (error) {
      console.error("XCrystal: analysis failed", error);
      paintErrorBar(bar);
      // Allow retry later in auto (don't set ATTR_DONE)
    } finally {
      article.removeAttribute(ATTR_ANALYZING);
    }
  }

  function shouldAutoAnalyze(article) {
    if (currentMode !== "auto") return false;
    if (!article || !article.isConnected) return false;
    if (article.getAttribute(ATTR_ANALYZING) === "1") return false;
    if (article.getAttribute(ATTR_DONE) === "1") return false;
    if (!article.querySelector(".xcrystal-bar")) return false;
    return true;
  }

  function enqueueAuto(article) {
    if (!shouldAutoAnalyze(article)) return;
    if (autoQueue.indexOf(article) !== -1) return;
    autoQueue.push(article);
    pumpQueue();
  }

  function pumpQueue() {
    while (inFlight < MAX_IN_FLIGHT && autoQueue.length > 0) {
      if (currentMode !== "auto") {
        autoQueue.length = 0;
        break;
      }
      const article = autoQueue.shift();
      if (!shouldAutoAnalyze(article)) continue;
      // Rough viewport check as safety net
      const rect = article.getBoundingClientRect();
      const margin = 200;
      const inView =
        rect.bottom >= -margin &&
        rect.top <= (window.innerHeight || 0) + margin;
      if (!inView) continue;

      inFlight++;
      Promise.resolve()
        .then(() => analyzeTweet(article, { auto: true }))
        .finally(() => {
          inFlight--;
          pumpQueue();
        });
    }
  }

  function clearAutoQueue() {
    autoQueue.length = 0;
  }

  function scanVisibleForAuto() {
    if (currentMode !== "auto") return;
    document.querySelectorAll('article[data-testid="tweet"]').forEach((article) => {
      if (!shouldAutoAnalyze(article)) return;
      const rect = article.getBoundingClientRect();
      const margin = 200;
      if (rect.bottom >= -margin && rect.top <= (window.innerHeight || 0) + margin) {
        enqueueAuto(article);
      }
    });
  }

  function ensureIntersectionObserver() {
    if (intersectionObserver) return;
    intersectionObserver = new IntersectionObserver(
      (entries) => {
        if (currentMode !== "auto") return;
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const article = entry.target;
          if (article && article.matches && article.matches('article[data-testid="tweet"]')) {
            enqueueAuto(article);
          }
        }
      },
      { root: null, rootMargin: "120px 0px", threshold: 0.05 }
    );
  }

  function observeArticle(article) {
    ensureIntersectionObserver();
    try {
      intersectionObserver.observe(article);
    } catch (_) {}
  }

  function createBar(article) {
    const bar = document.createElement("div");
    bar.className = "xcrystal-bar";
    paintIdleBar(bar, article);
    return bar;
  }

  function placeBar(article, bar) {
    const tweetText = getDomMainTextEl(article);
    if (tweetText) {
      const wrapper = tweetText.parentElement;
      if (wrapper && wrapper.parentElement) {
        wrapper.parentElement.insertBefore(bar, wrapper);
        return;
      }
      if (tweetText.parentElement) {
        tweetText.parentElement.insertBefore(bar, tweetText);
        return;
      }
    }

    const userName = article.querySelector('[data-testid="User-Name"]');
    if (userName) {
      let node = userName;
      while (node.parentElement && node.parentElement !== article) {
        const parent = node.parentElement;
        const grand = parent.parentElement;
        if (grand) {
          const siblings = Array.from(grand.children);
          const hasAvatarSibling = siblings.some(
            (c) => c !== parent && c.querySelector && c.querySelector('[data-testid="UserAvatar-Container"]')
          );
          if (hasAvatarSibling && siblings.includes(parent)) {
            if (node.nextSibling) parent.insertBefore(bar, node.nextSibling);
            else parent.appendChild(bar);
            return;
          }
        }
        node = parent;
      }
      const block = userName.closest("div") || userName;
      if (block.parentElement) {
        if (block.nextSibling) block.parentElement.insertBefore(bar, block.nextSibling);
        else block.parentElement.appendChild(bar);
        return;
      }
    }

    article.appendChild(bar);
  }

  function injectBar(article) {
    if (article.querySelector(".xcrystal-bar")) {
      observeArticle(article);
      if (currentMode === "auto") enqueueAuto(article);
      return;
    }

    const bar = createBar(article);
    placeBar(article, bar);
    observeArticle(article);
    if (currentMode === "auto") enqueueAuto(article);
  }

  function processTweets() {
    document.querySelectorAll('article[data-testid="tweet"]').forEach(injectBar);
  }

  function watchTweets() {
    const observer = new MutationObserver(function(mutations) {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node.nodeType !== Node.ELEMENT_NODE) continue;
          if (node.matches && node.matches('article[data-testid="tweet"]')) {
            injectBar(node);
          } else if (node.querySelectorAll) {
            node.querySelectorAll('article[data-testid="tweet"]').forEach(injectBar);
          }
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  function listenPageHook() {
    window.addEventListener("message", function(event) {
      if (event.source !== window) return;
      const msg = event.data;
      if (!msg || msg.source !== HOOK_SOURCE) return;
      if (msg.type === "TWEETS" && Array.isArray(msg.tweets)) {
        for (const tw of msg.tweets) {
          if (tw && tw.id) tweetStore.set(String(tw.id), tw);
        }
      }
    });
  }

  function onStorageChanged(changes, area) {
    if (area && area !== "local") return;

    if (changes.language || changes.lang) {
      const next =
        (changes.language && changes.language.newValue) ||
        (changes.lang && changes.lang.newValue) ||
        currentLang;
      currentLang = next === "en" ? "en" : "zh";
      syncLangGlobal();
      refreshAllBarLabels();
    }

    if (changes.mode) {
      const next = changes.mode.newValue === "auto" ? "auto" : "manual";
      const prev = currentMode;
      currentMode = next;
      if (next === "manual") {
        clearAutoQueue();
      } else if (next === "auto" && prev !== "auto") {
        scanVisibleForAuto();
      }
    }
  }

  async function init() {
    console.log("XCrystal: initializing...");
    await loadConfig();
    listenPageHook();
    ensureIntersectionObserver();
    processTweets();
    watchTweets();
    chrome.storage.onChanged.addListener(onStorageChanged);
    if (currentMode === "auto") scanVisibleForAuto();
    console.log("XCrystal: ready! mode=", currentMode, "lang=", currentLang);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
