#!/usr/bin/env python3
"""XCryptoLens / XCrystal API Server — laya-backed tweet analyzer."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, jsonify, request
from flask_cors import CORS
from laya import load

# 串行化推理：GPU(Metal) 上并发 predict 会触发断言崩溃
PREDICT_LOCK = threading.Lock()

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Config: .env next to this file, real env vars override
# ---------------------------------------------------------------------------
def _parse_env_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key:
            out[key] = val
    return out


def _cfg(name: str, default: str = "") -> str:
    if name in os.environ and os.environ[name] != "":
        return os.environ[name]
    return _ENV_FILE.get(name, default)


_ENV_FILE = _parse_env_file(HERE / ".env")

LAYA_MODEL_PATH = _cfg("LAYA_MODEL_PATH", str(HERE / "models" / "multilingual"))
SERVER_HOST = _cfg("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(_cfg("SERVER_PORT", "5678"))
CACHE_SIZE = int(_cfg("CACHE_SIZE", "1000"))
LOG_FILE = _cfg("LOG_FILE", "server.log")
if not os.path.isabs(LOG_FILE):
    LOG_FILE = str(HERE / LOG_FILE)

# Direction uncertainty: mark uncertain when max direction probability < this
def _float_cfg(name: str, default: float, lo: float = 0.0, hi: float = 1.0) -> float:
    raw = _cfg(name, str(default))
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return default
    if not (lo < val < hi):
        return default
    return val


UNCERTAIN_THRESHOLD = _float_cfg("UNCERTAIN_THRESHOLD", 0.60)
# Cap volatile when collision rules fire
COLLISION_VOLATILE_CAP = 0.1
# URL preprocessing before inference: "domain" | "remove" | "off"
# domain → replace each URL with "[link: example.com]"; remove → strip entirely
URL_PREPROCESS = (_cfg("URL_PREPROCESS", "remove") or "remove").strip().lower()
if URL_PREPROCESS not in ("domain", "remove", "off"):
    URL_PREPROCESS = "remove"
# Low-relevance gate: if volatile stays below this after scope gating, treat as gated
LOW_RELEVANCE_GATE = float(_cfg("LOW_RELEVANCE_GATE", "0.35"))

# Best variant from prompt experiments (simple_rel): Grok direction/scope/impact
# with a simpler relevance noul. Key stays `volatile` for frontend compatibility.
QUESTIONS = {
    "volatile": {
        "type": "noul",
        "instructions": (
            "Does this post mention a cryptocurrency, a crypto company/exchange/protocol, "
            "a crypto ETF, or a macro/geopolitical event that clearly affects financial markets "
            "or risk assets? Answer false for stock tickers, fashion 'link in bio', lifestyle, "
            "and politics with no market hook."
        ),
        "criteria": {
            "true": "Mentions BTC/ETH/crypto/token/chain/exchange/DeFi/ETF, or rates/war/sanctions that move markets or risk assets.",
            "false": "Stock/brand ticker only, 'link in bio', lifestyle, pure politics, no market/crypto hook.",
        },
    },
    "scope": {
        "type": "choice",
        "instructions": "Which layer does this hit?",
        "criteria": {
            "btc_eth_macro": "BTC, ETH, crypto ETFs, or a macro/geopolitical shock that reprices crypto as a risk or liquidity asset.",
            "sector": "L2, DeFi, memes, AI-crypto, RWA, stables, one chain.",
            "single_asset": "One token, protocol, or exchange.",
            "none": "No crypto transmission.",
        },
    },
    "direction": {
        "type": "choice",
        "instructions": "Is the new information good or bad for the assets in scope? Judge the event, not a price forecast.",
        "criteria": {
            "bullish": "Easier liquidity or higher risk appetite: cuts, dovish surprise, dollar down, ETF inflow, peace/de-escalation, listing, partnership, product live, legal win, buyback.",
            "bearish": "Tighter liquidity or risk-off: hikes, hawkish surprise, dollar spike, war escalation, sanctions, banking stress, hack, halt, depeg, unlock dump, lawsuit, ban, delist.",
            "neutral": "Opinion, joke, old news, mixed macro (hawkish and dovish in one post), or no new fact.",
        },
    },
    "impact": {
        "type": "score",
        "instructions": "How much can this move the assets in scope in hours to a few days?",
        "criteria": [
            "low: recycled headline, pundit take, minor data in-line",
            "medium: real data surprise, limited regional conflict, mid-tier listing or outage",
            "high: FOMC surprise, sudden escalation, ETF flow shock, large unlock, top-venue listing, $10M+ exploit, chain halt",
            "extreme: emergency rate move, systemic war/sanctions shock, ETF approve/ban, exchange solvency, stable depeg, event that reprices BTC/ETH itself",
        ],
    },
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_log = logging.getLogger("xcrystal")
_log.setLevel(logging.INFO)
_fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
_fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
_fh.setFormatter(_fmt)
_log.addHandler(_fh)
_sh = logging.StreamHandler()
_sh.setFormatter(_fmt)
_log.addHandler(_sh)

# ---------------------------------------------------------------------------
# Crypto ticker whitelist + collision heuristics
# ---------------------------------------------------------------------------
_CASHTAG_RE = re.compile(r"(?<![A-Za-z0-9_])\$([A-Za-z]{1,12})\b")
_CRYPTO_KEYWORD_RE = re.compile(
    r"(?i)\b("
    r"bitcoin|btc|ethereum|eth|crypto|cryptocurrency|defi|nft|token|blockchain|"
    r"stablecoin|usdc|usdt|solana|binance|coinbase|okx|kraken|uniswap|"
    r"liquidation|airdrop|halving|web3|web\s*3|on-?chain|mempool|"
    r"satoshi|altcoin|memecoin|perp|perpetual|"
    r"hack|exploit|bridge|drained|ftx|wormhole|depeg|unlock"
    r")\b"
    r"|比特币|以太坊|加密货币|加密|币圈|代币|区块链|公链|链上|上链|交易所|稳定币|合约|空投|黑客|脱锚|提现|看多|看空"
)

# Phrase collisions: fashion/lifestyle that look like crypto tickers
_PHRASE_COLLISION_RE = re.compile(
    r"(?i)("
    r"link\s+in\s+bio"
    r"|links?\s+in\s+(my\s+)?bio"
    r"|code\s+SOL\b"
    r"|use\s+code\s+[A-Z0-9]+"
    r")"
)


# ---------------------------------------------------------------------------
# URL preprocessing (strip / replace before inference; keep original for logs)
# ---------------------------------------------------------------------------
# http(s), www., and bare domain/path (e.g. pan.quark.cn/s/xxx). Does NOT match
# bare 0x… / base58 addresses in plain text — those stay as crypto signals.
_URL_RE = re.compile(
    r"(?i)"
    r"(?:"
    r"(?:https?://|www\.)[^\s<>\[\]\"']+"
    r"|"
    r"(?<![A-Za-z0-9@./_-])"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}"
    r"(?:/[^\s<>\[\]\"']*)?"
    r")"
)
_TRAIL_PUNCT_RE = re.compile(r"[),.;:!?\u3002\uff0c\uff01\uff1f\u201d\u2019]+$")


def _url_domain(raw: str) -> str:
    s = raw.strip()
    s = _TRAIL_PUNCT_RE.sub("", s)
    if s.lower().startswith("www."):
        s = "https://" + s
    elif not re.match(r"(?i)^https?://", s):
        s = "https://" + s
    try:
        from urllib.parse import urlparse
        host = urlparse(s).hostname or ""
    except Exception:
        host = ""
    if not host:
        # fallback: take first path segment-ish
        host = re.split(r"[/?#]", raw.strip())[0]
        host = re.sub(r"(?i)^https?://", "", host)
        host = re.sub(r"(?i)^www\.", "", host)
    return host.lower().lstrip(".")


def preprocess_tweet_urls(tweet: str, mode: Optional[str] = None) -> Tuple[str, int]:
    """Return (text_for_inference, n_urls_replaced). mode: domain|remove|off."""
    mode = (mode or URL_PREPROCESS or "remove").lower()
    if mode == "off" or not tweet:
        return tweet, 0

    def repl(m: re.Match) -> str:
        raw = m.group(0)
        cleaned = _TRAIL_PUNCT_RE.sub("", raw)
        trail = raw[len(cleaned):] if len(raw) > len(cleaned) else ""
        if mode == "remove":
            return trail
        domain = _url_domain(cleaned)
        if not domain:
            return trail
        return f"[link: {domain}]" + trail

    out, n = _URL_RE.subn(repl, tweet)
    # collapse leftover multi-spaces / blank lines from removals
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip(), n


def _has_crypto_signal(text: str) -> bool:
    """True if tweet has crypto keywords or a whitelisted cashtag (not URL hex)."""
    text = text or ""
    if _CRYPTO_KEYWORD_RE.search(text):
        return True
    for m in _CASHTAG_RE.finditer(text):
        if m.group(1).upper() in CRYPTO_TICKERS:
            return True
    return False


def apply_scope_gate(
    result: Dict[str, Any],
    scope_probs: Optional[Dict[str, float]] = None,
    original_text: str = "",
) -> None:
    """Cap relevance when scope is none; gate UI when likely irrelevant.

    Formula: if scope == "none", volatile = min(volatile, 1 - p(none)).
    Gate (hide direction/impact) only when the tweet looks non-crypto: no crypto
    keyword / whitelisted cashtag, or volatile after the cap is below
    LOW_RELEVANCE_GATE, or a collision rule already fired. Avoids wiping
    direction/impact on genuine crypto posts where the model picks scope=none.
    """
    scope_probs = scope_probs or {}
    scope = result.get("scope")
    vol = float(result.get("volatile") or 0.0)
    p_none = float(scope_probs.get("none", 0.0))
    flags = list(result.get("rule_flags") or [])
    collision = any(
        f == "phrase_collision" or str(f).startswith("cashtag_collision") for f in flags
    )
    crypto = _has_crypto_signal(original_text)

    if scope == "none":
        if p_none <= 0.0:
            p_none = float(result.get("scope_prob") or 0.0)
        cap = max(0.0, min(1.0, 1.0 - p_none))
        vol = min(vol, cap)
        result["volatile"] = vol

        # Crypto signal: only cap volatile, keep direction/impact visible.
        # Gate when no crypto signal, or collision rules already fired.
        should_gate = (not crypto) or collision
        if should_gate:
            # Extra display dampening so gated UI % stays clearly low
            vol = min(vol, LOW_RELEVANCE_GATE)
            result["volatile"] = vol
            result["gated"] = True
            result["relevant"] = False
            result["direction"] = "neutral"
            result["uncertain"] = False
            if "scope_gate" not in flags:
                flags.append("scope_gate")
            result["rule_flags"] = flags
        else:
            result["gated"] = False
            result["relevant"] = True
            if "scope_vol_cap" not in flags:
                flags.append("scope_vol_cap")
            result["rule_flags"] = flags
    elif vol < LOW_RELEVANCE_GATE and not crypto:
        result["gated"] = True
        result["relevant"] = False
        result["direction"] = "neutral"
        result["uncertain"] = False
        result["scope"] = "none"
        if "low_relevance_gate" not in flags:
            flags.append("low_relevance_gate")
        result["rule_flags"] = flags
    else:
        result["gated"] = False
        result["relevant"] = True


def _load_crypto_tickers(path: Path) -> set:
    tickers = set()
    if not path.is_file():
        _log.warning("crypto_tickers.txt missing at %s", path)
        return tickers
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tickers.add(line.lstrip("$").upper())
    return tickers


CRYPTO_TICKERS = _load_crypto_tickers(HERE / "crypto_tickers.txt")


def apply_collision_rules(tweet: str, result: Dict[str, Any]) -> List[str]:
    """Mutate result in place when cashtag/phrase collisions fire. Return rule_flags."""
    flags: List[str] = []
    text = tweet or ""
    cashtags = [m.group(1).upper() for m in _CASHTAG_RE.finditer(text)]
    has_crypto_kw = bool(_CRYPTO_KEYWORD_RE.search(text))
    phrase_hit = bool(_PHRASE_COLLISION_RE.search(text))

    if phrase_hit and not has_crypto_kw:
        # e.g. "link in bio" / "code SOL at checkout" without other crypto signal
        flags.append("phrase_collision")

    if cashtags:
        crypto_tags = [t for t in cashtags if t in CRYPTO_TICKERS]
        non_crypto = [t for t in cashtags if t not in CRYPTO_TICKERS]
        if non_crypto and not crypto_tags and not has_crypto_kw:
            flags.append("cashtag_collision:" + ",".join(non_crypto))

    if flags:
        result["volatile"] = min(float(result.get("volatile") or 0.0), COLLISION_VOLATILE_CAP)
        result["scope"] = "none"
        result["scope_prob"] = 1.0
        result["direction"] = "neutral"
        result["direction_prob"] = 1.0
        result["direction_confidence"] = 1.0
        result["uncertain"] = False
        # keep impact as model said but strength will drop with volatile
        result["rule_flags"] = flags
    else:
        result["rule_flags"] = []
    return result.get("rule_flags") or []


# ---------------------------------------------------------------------------
# LRU cache
# ---------------------------------------------------------------------------
class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = max(1, int(capacity))
        self._data: OrderedDict = OrderedDict()

    def get(self, key: str):
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def set(self, key: str, value):
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        while len(self._data) > self.capacity:
            self._data.popitem(last=False)


_cache = LRUCache(CACHE_SIZE)


def _cache_key(tweet_id: Optional[str], tweet: str) -> str:
    if tweet_id:
        return "id:" + str(tweet_id)
    return "text:" + hashlib.sha256(tweet.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
app = Flask(__name__)
CORS(app)

_log.info("Loading Laya model from %s ...", LAYA_MODEL_PATH)
agent = load(LAYA_MODEL_PATH, device=os.environ.get("LAYA_DEVICE") or None)
_log.info("Model loaded.")


def _impact_short_label(answers: dict) -> Tuple[str, float]:
    """laya legend values are criteria strings verbatim; take word before ':'."""
    impact = answers["impact"]
    score = float(impact["score"])
    legend = impact.get("legend") or {}
    raw = legend.get(str(round(score)), "")
    if not raw:
        # fallback: nearest index
        idx = max(0, min(3, int(round(score))))
        raw = legend.get(str(idx), str(idx))
    short = str(raw).split(":")[0].strip().lower()
    if short not in ("low", "medium", "high", "extreme"):
        # last resort map by rounded score
        short = ["low", "medium", "high", "extreme"][max(0, min(3, int(round(score))))]
    return short, score


def analyze_tweet(tweet: str, tweet_id: Optional[str] = None) -> Dict[str, Any]:
    """Core analyze path (used by HTTP handler and offline eval)."""
    # Cache by original text / id so preprocessing changes don't fragment keys oddly;
    # collision rules also see the original (cashtags live outside URLs).
    original = tweet or ""
    key = _cache_key(tweet_id, original)
    cached = _cache.get(key)
    if cached is not None:
        out = dict(cached)
        out["cached"] = True
        return out

    inference_text, n_urls = preprocess_tweet_urls(original)
    if not inference_text.strip():
        # URL-only / empty after strip — treat as unrelated without calling the model
        inference_text = original

    # Metal/MPS 不支持多个线程同时推理，否则进程会崩溃（Abort trap: 6），所以这里排队执行
    with PREDICT_LOCK:
        out_pred = agent.predict(inference_text, QUESTIONS)
    answers = out_pred["answers"]

    volatile = float(answers["volatile"]["noul"])
    direction = answers["direction"]["choice"]
    dir_probs = dict(answers["direction"]["probabilities"])
    direction_prob = float(dir_probs.get(direction, 0.0))
    direction_confidence = float(max(dir_probs.values()) if dir_probs else 0.0)
    uncertain = direction_confidence < UNCERTAIN_THRESHOLD

    scope = answers["scope"]["choice"]
    scope_probs = dict(answers["scope"]["probabilities"])
    scope_prob = float(scope_probs.get(scope, 0.0))

    impact_label, impact_score = _impact_short_label(answers)
    strength = volatile * impact_score / 3.0

    result: Dict[str, Any] = {
        "success": True,
        "tweet": original[:100],
        "volatile": volatile,
        "scope": scope,
        "scope_prob": scope_prob,
        "direction": direction,
        "direction_prob": direction_prob,
        "direction_confidence": direction_confidence,
        "uncertain": uncertain,
        "impact": impact_label,
        "impact_score": impact_score,
        "strength": strength,
        "probabilities": {
            "direction": dir_probs,
            "impact": dict(answers["impact"]["probabilities"]),
            "scope": scope_probs,
        },
        "answer_confidence": {
            "volatile": answers["volatile"].get("answer_confidence"),
            "scope": answers["scope"].get("answer_confidence"),
            "direction": answers["direction"].get("answer_confidence"),
            "impact": answers["impact"].get("answer_confidence"),
        },
        "rule_flags": [],
        "gated": False,
        "relevant": True,
        "urls_stripped": n_urls,
        "cached": False,
    }

    apply_collision_rules(original, result)
    apply_scope_gate(result, scope_probs, original_text=original)
    # recompute strength after possible volatile cap / gate
    result["strength"] = float(result["volatile"]) * float(result["impact_score"]) / 3.0

    _cache.set(key, {k: v for k, v in result.items() if k != "cached"})
    return result


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json or {}
    tweet = data.get("tweet", "")
    tweet_id = data.get("id")
    if not tweet:
        return jsonify({"error": "No tweet provided"}), 400
    t0 = time.time()
    try:
        result = analyze_tweet(tweet, tweet_id)
        ms = round((time.time() - t0) * 1000)
        _log.info(
            "analyze id=%s len=%d vol=%.3f scope=%s dir=%s imp=%s uncertain=%s gated=%s flags=%s ms=%d",
            tweet_id or "-",
            len(tweet),
            result.get("volatile", 0),
            result.get("scope"),
            result.get("direction"),
            result.get("impact"),
            result.get("uncertain"),
            result.get("gated"),
            result.get("rule_flags"),
            ms,
        )
        return jsonify(result)
    except Exception as e:
        _log.exception("analyze failed")
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "model": LAYA_MODEL_PATH,
        "uncertain_threshold": UNCERTAIN_THRESHOLD,
        "cache_size": CACHE_SIZE,
        "crypto_tickers": len(CRYPTO_TICKERS),
        "url_preprocess": URL_PREPROCESS,
        "low_relevance_gate": LOW_RELEVANCE_GATE,
    })


if __name__ == "__main__":
    print(f"Starting server on http://{SERVER_HOST}:{SERVER_PORT}")
    print(f"Model: {LAYA_MODEL_PATH}")
    print(f"Log: {LOG_FILE}")
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False)
