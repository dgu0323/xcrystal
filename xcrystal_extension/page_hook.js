// XCrystal - MAIN world GraphQL hook
// 拦截 X 自己的 GraphQL 响应，按推文 ID 缓存完整正文（含 note_tweet 长推文）
(function () {
  if (window.__xcrystalHookInstalled) return;
  window.__xcrystalHookInstalled = true;

  const SOURCE = "xcrystal-page-hook";
  const GRAPHQL_RE = /\/i\/api\/graphql\/([^/]+)\/(\w+)/;
  const TWEET_OPS = new Set([
    "HomeTimeline", "HomeLatestTimeline", "TweetDetail", "UserTweets",
    "UserTweetsAndReplies", "UserMedia", "SearchTimeline", "ListLatestTweetsTimeline",
    "Bookmarks", "Likes", "TweetResultByRestId", "TweetResultsByRestIds",
    "CommunityTweetsTimeline",
  ]);

  // 从真实请求里抓取 TweetDetail 的 queryId / features，以及 bearer，用于缓存未命中时主动拉取
  const gqlMeta = { tweetDetail: null, bearer: null };

  const post = (msg) => window.postMessage({ source: SOURCE, ...msg }, window.location.origin);

  function unwrapTweet(obj) {
    if (!obj || typeof obj !== "object") return null;
    if (obj.__typename === "TweetWithVisibilityResults" && obj.tweet) return obj.tweet;
    if (obj.__typename === "Tweet" || (obj.rest_id && obj.legacy)) return obj;
    return null;
  }

  function getFullText(tweet) {
    const note = tweet.note_tweet?.note_tweet_results?.result;
    if (note && typeof note.text === "string" && note.text.length) {
      return { text: note.text, source: "note_tweet", entities: note.entity_set || null };
    }
    const legacy = tweet.legacy || {};
    return { text: legacy.full_text || legacy.text || "", source: "legacy", entities: legacy.entities || null };
  }

  // 把 t.co 短链替换成真实链接，让时间线和详情页的文本完全一致
  function expandUrls(text, entities) {
    const urls = entities?.urls || [];
    let out = text;
    for (const u of urls) {
      if (u?.url && u?.expanded_url) out = out.split(u.url).join(u.expanded_url);
    }
    // 去掉末尾指向媒体的 t.co 链接（legacy.full_text 里会带）
    return out.replace(/\s*https:\/\/t\.co\/\w+\s*$/, "").trim();
  }

  function summarizeTweet(tweet, depth = 0) {
    if (!tweet) return null;
    const id = tweet.rest_id || tweet.legacy?.id_str;
    if (!id) return null;
    const legacy = tweet.legacy || {};
    const t = getFullText(tweet);
    const user = tweet.core?.user_results?.result || {};
    const quotedRaw = unwrapTweet(tweet.quoted_status_result?.result);
    return {
      id: String(id),
      text: expandUrls(t.text, t.entities),
      text_source: t.source,
      author: {
        id: user.rest_id || null,
        name: user.core?.name || user.legacy?.name || null,
        screen_name: user.core?.screen_name || user.legacy?.screen_name || null,
      },
      created_at: legacy.created_at || null,
      metrics: {
        reply: legacy.reply_count, retweet: legacy.retweet_count,
        like: legacy.favorite_count, quote: legacy.quote_count,
        view: tweet.views?.count ?? null,
      },
      media: (legacy.extended_entities?.media || []).map((m) => ({ type: m.type, url: m.media_url_https })),
      // 只解析一层引用，避免无限递归
      quoted: depth === 0 && quotedRaw ? summarizeTweet(quotedRaw, 1) : null,
    };
  }

  function collect(node, out, seen) {
    if (!node || typeof node !== "object") return;
    if (Array.isArray(node)) { for (const n of node) collect(n, out, seen); return; }
    const tweet = unwrapTweet(node);
    if (tweet) {
      const s = summarizeTweet(tweet);
      if (s && !seen.has(s.id)) { seen.add(s.id); out.push(s); }
    }
    for (const k in node) {
      const v = node[k];
      if (v && typeof v === "object") collect(v, out, seen);
    }
  }

  function handleResponse(url, data) {
    try {
      const out = [];
      collect(data, out, new Set());
      if (out.length) post({ type: "TWEETS", tweets: out });
    } catch (e) {
      console.warn("XCrystal hook parse error", e);
    }
  }

  function captureMeta(url, authHeader) {
    const m = url.match(GRAPHQL_RE);
    if (!m) return;
    if (authHeader) gqlMeta.bearer = authHeader;
    if (m[2] === "TweetDetail") {
      // X 的 TweetDetail 是 GET，参数在 query string 里
      try {
        const u = new URL(url, location.origin);
        gqlMeta.tweetDetail = {
          queryId: m[1],
          features: u.searchParams.get("features") || "{}",
          fieldToggles: u.searchParams.get("fieldToggles") || "{}",
          variables: JSON.parse(u.searchParams.get("variables") || "{}"),
        };
      } catch (_) {}
    }
  }

  const isTweetOp = (url) => {
    const m = typeof url === "string" && url.match(GRAPHQL_RE);
    return !!(m && TWEET_OPS.has(m[2]));
  };

  // ---- fetch hook ----
  const origFetch = window.fetch;
  window.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : input?.url || "";
    if (isTweetOp(url)) {
      let auth = null;
      try { auth = new Headers(init?.headers || input?.headers).get("authorization"); } catch (_) {}
      captureMeta(url, auth);
    }
    const res = await origFetch.apply(this, arguments);
    if (isTweetOp(url)) {
      res.clone().json().then((d) => handleResponse(url, d)).catch(() => {});
    }
    return res;
  };

  // ---- XHR hook（X 网页端主要用 XHR 发 GraphQL 请求）----
  const XHR = XMLHttpRequest.prototype;
  const origOpen = XHR.open, origSend = XHR.send, origSetHeader = XHR.setRequestHeader;
  XHR.open = function (method, url) {
    this.__xcUrl = String(url || "");
    this.__xcAuth = null;
    return origOpen.apply(this, arguments);
  };
  XHR.setRequestHeader = function (name, value) {
    if (String(name).toLowerCase() === "authorization") this.__xcAuth = value;
    return origSetHeader.apply(this, arguments);
  };
  XHR.send = function () {
    const url = this.__xcUrl || "";
    if (isTweetOp(url)) {
      captureMeta(url, this.__xcAuth);
      this.addEventListener("load", function () {
        try {
          const data = this.responseType === "json" ? this.response : JSON.parse(this.responseText);
          handleResponse(url, data);
        } catch (_) {}
      });
    }
    return origSend.apply(this, arguments);
  };

  // ---- 缓存未命中时，按 ID 主动请求 TweetDetail ----
  async function fetchTweetDetail(tweetId) {
    const meta = gqlMeta.tweetDetail;
    if (!meta || !gqlMeta.bearer) throw new Error("no TweetDetail meta yet (open any tweet page once)");
    const variables = { ...meta.variables, focalTweetId: String(tweetId) };
    delete variables.cursor;
    const url = `${location.origin}/i/api/graphql/${meta.queryId}/TweetDetail?` +
      new URLSearchParams({ variables: JSON.stringify(variables), features: meta.features, fieldToggles: meta.fieldToggles });
    const ct0 = document.cookie.match(/(?:^|;\s*)ct0=([^;]+)/)?.[1];
    const res = await origFetch(url, {
      credentials: "include",
      headers: {
        authorization: gqlMeta.bearer,
        "x-csrf-token": ct0 ? decodeURIComponent(ct0) : "",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "content-type": "application/json",
      },
    });
    if (!res.ok) throw new Error(`TweetDetail HTTP ${res.status}`);
    handleResponse(url, await res.json());
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    const msg = event.data;
    if (msg?.source !== "xcrystal-content" || msg.type !== "FETCH_TWEET") return;
    fetchTweetDetail(msg.tweetId)
      .then(() => post({ type: "FETCH_DONE", tweetId: msg.tweetId, ok: true }))
      .catch((e) => post({ type: "FETCH_DONE", tweetId: msg.tweetId, ok: false, error: String(e?.message || e) }));
  });

  console.log("XCrystal: MAIN-world GraphQL hook installed");
})();
