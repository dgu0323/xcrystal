// XCrystal Background Service Worker
// Handles API requests to bypass CORS restrictions; caches by id then text

let serverUrl = "http://localhost:5678";
const analysisCache = new Map(); // key -> result
const CACHE_MAX = 1000;

function cacheKey(id, tweet) {
  if (id) return "id:" + String(id);
  return "text:" + String(tweet || "");
}

function cacheSet(key, value) {
  if (analysisCache.size >= CACHE_MAX) {
    const first = analysisCache.keys().next().value;
    analysisCache.delete(first);
  }
  analysisCache.set(key, value);
}

// Load config on startup
chrome.storage.local.get(["serverUrl"], (result) => {
  if (result.serverUrl) {
    serverUrl = result.serverUrl;
  }
});

// Listen for config changes
chrome.storage.onChanged.addListener((changes) => {
  if (changes.serverUrl) {
    serverUrl = changes.serverUrl.newValue;
  }
});

// Message handler
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "analyze") {
    const key = cacheKey(request.id, request.tweet);
    if (analysisCache.has(key)) {
      console.log("Background: cache hit", key);
      sendResponse({ success: true, data: analysisCache.get(key), cached: true });
      return false;
    }

    console.log("Background: analyzing tweet via", serverUrl);

    fetch(serverUrl + "/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tweet: request.tweet, id: request.id })
    })
    .then(response => {
      if (!response.ok) {
        throw new Error("Server error: " + response.status);
      }
      return response.json();
    })
    .then(result => {
      console.log("Background: got result", result);
      cacheSet(key, result);
      sendResponse({ success: true, data: result });
    })
    .catch(error => {
      console.error("Background: analysis failed", error);
      sendResponse({ success: false, error: error.message });
    });

    return true; // Keep message channel open for async response
  }

  if (request.action === "checkServer" || request.action === "health") {
    fetch(serverUrl + "/health")
      .then(response => response.json())
      .then(data => {
        // Support both popup shapes: {success,data} and raw {status:"ok"}
        sendResponse({ success: true, data: data, status: data && data.status });
      })
      .catch(error => {
        sendResponse({ success: false, error: error.message });
      });

    return true;
  }

  if (request.action === "clearCache") {
    analysisCache.clear();
    sendResponse({ success: true });
    return false;
  }

  if (request.action === "cacheSize") {
    sendResponse({ success: true, size: analysisCache.size });
    return false;
  }
});
