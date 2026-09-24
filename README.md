# XCrystal <img src="assets/icon.png" width="32" height="32" alt="XCrystal">

[English](README.md) | [中文](README.zh-CN.md)

[Laya](https://github.com/NandhaKishorM/laya)-powered crypto analysis Chrome extension for X (Twitter), plus a local analysis server on `localhost:5678`.

> 💡 **Open-source alternative to Jev** — powered by Laya, free and local

**🆓 100% Local, Zero Cost** — analysis runs on your machine

**⚡ Fast** — local inference; no cloud round-trip for the model

<p align="center">
  <img src="assets/timeline.png" alt="Analysis bar on an X tweet" width="720">
</p>
<p align="center"><em>Analysis bar on a tweet: relevance %, scope, direction, and impact.</em></p>

## What it is

**XCrystal** is two parts that work together:

1. **Chrome MV3 extension** (`xcrystal_extension/`) — injects an analysis bar on X/Twitter tweets, intercepts GraphQL for full text (including long “note” tweets), and talks to the local analysis server on `127.0.0.1:5678`.
2. **Local Laya analysis server** (`server.py` in this repo) — Flask + flask-cors, default `http://127.0.0.1:5678`. Scores each tweet for crypto **relevance**, **scope**, **direction**, and **impact**.

## Directory layout

```
./                             # project / repo root (server-side lives here)
├── README.md / README.zh-CN.md
├── LICENSE                    # MIT
├── requirements.txt           # pinned Python deps
├── assets/                    # README screenshots + icon.png
├── server.py                  # API server (Flask)
├── start.sh                   # starts server (reads VENV_PATH from env / .env)
├── .env.example               # copy to .env (gitignored)
├── crypto_tickers.txt         # cashtag whitelist for rule layer
├── laya_config.py             # shared LAYA_MODEL_PATH helper for scripts
├── prompt_tests/              # eval + tweet sets (see prompt_tests/README.md)
└── xcrystal_extension/        # Chrome extension only
    ├── manifest.json
    ├── background.js          # API proxy + client cache
    ├── content.js             # tweet bar + auto/manual mode
    ├── page_hook.js           # MAIN-world GraphQL intercept
    ├── popup.html / popup.js
    ├── i18n.js
    ├── styles.css
    ├── config.json
    └── icons/
```

## Setup

### Prerequisites

- Python 3.10+ recommended (developed/tested on **Python 3.14**; 3.9 may work but is untested here)
- Chrome
- Laya multilingual model on disk
- A Python virtualenv (see below; `./start.sh` reads `VENV_PATH`)

### Hardware (rough)

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 8GB | 16GB+ |
| GPU | CUDA / Apple MPS | Apple Silicon / NVIDIA |
| Storage | ~2GB+ for model | — |

### 1. Virtualenv & deps

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# pins: laya==0.3.11, flask==3.1.3, flask-cors==6.0.5
```

### 2. Model

```bash
# Optional mirror for users in China
export HF_ENDPOINT=https://hf-mirror.com

hf download convaiinnovations/laya --include "multilingual/**" --local-dir ./models
# → ./models/multilingual/
```

Or set `LAYA_MODEL_PATH` to a local directory (e.g. `/path/to/laya/multilingual`) or a Hugging Face repo id that `laya.load` accepts (e.g. `convaiinnovations/laya`).

### 3. Configure `.env`

```bash
cp .env.example .env
# edit LAYA_MODEL_PATH and others
```

| Variable | Description | Example |
|----------|-------------|---------|
| `LAYA_MODEL_PATH` | Local model dir or HF repo id for `laya.load` | `/path/to/laya/multilingual` |
| `VENV_PATH` | Virtualenv for `./start.sh` | `.venv` |
| `SERVER_HOST` | Bind host | `127.0.0.1` |
| `SERVER_PORT` | Bind port | `5678` |
| `CACHE_SIZE` | Server LRU cache entries | `1000` |
| `LOG_FILE` | Log file (relative → next to `server.py`) | `server.log` |
| `URL_PREPROCESS` | URL strip mode before inference | `remove` / `domain` / `off` |
| `LOW_RELEVANCE_GATE` | Cap / gate threshold when scoped none | `0.35` |
| `LAYA_DEVICE` | Optional device for `laya.load` (unset = auto) | `mps` / `cuda` / `cpu` |

**Env vars override `.env`.** `./start.sh` resolves the venv as: env `VENV_PATH` → `.env` `VENV_PATH` → `./.venv`. Inference is serialized with `PREDICT_LOCK` (see [Concurrency](#concurrency-pytorch-mps)).

### 4. Start the server

```bash
cd /path/to/repo                 # project / repo root
./start.sh
# or: source .venv/bin/activate && python server.py
```

`./start.sh` activates the virtualenv from `VENV_PATH` (environment or `.env`, default `./.venv`), quietly ensures `flask` / `flask-cors` are installed, then runs `python server.py`. Prefer `pip install -r requirements.txt` once when setting up.

**Health check** (extension talks to this local server; root `/` has no handler):

```bash
curl -s http://127.0.0.1:5678/health   # expect {"status":"ok", ...}
```

### 5. Load the Chrome extension

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. **Load unpacked** → select the `xcrystal_extension` folder
4. After editing extension files, click **Reload** on the card

Default API URL: `http://localhost:5678` (changeable in the popup).

## The four indicators

Shown on the tweet bar. Labels are bilingual via `i18n.js`.

| UI | Meaning |
|----|---------|
| **% (Relevance)** | Probability the tweet can affect crypto prices. JSON key is `volatile` (legacy name — **not** “volatility”). |
| **Scope** | Only meaningful when relevant. When `gated`, the bar shows **Not related** instead of direction/impact. |
| **Direction** | bullish / bearish / neutral — judges the **event**, not a price forecast. Grey **uncertain** / 不确定 when max direction probability &lt; `UNCERTAIN_THRESHOLD` (default `0.60`, configurable via env / `.env`). |
| **Impact** | low / medium / high / extreme — move potential over **hours to a few days**. |

### Scope values

| Value | EN / ZH | Meaning |
|-------|---------|---------|
| `btc_eth_macro` | BTC/ETH & macro / 大盘/宏观 | BTC, ETH, crypto ETFs, or macro/geopolitical shocks that reprice crypto |
| `sector` | Sector / 板块 | L2, DeFi, memes, AI-crypto, RWA, stablecoins, one chain |
| `single_asset` | Single asset / 单币 | One token, protocol, or exchange |
| `none` | None / 无关 | No crypto transmission |

### Impact examples (from server prompts)

| Level | Examples |
|-------|----------|
| **low** | Recycled headline, pundit take, minor data in-line |
| **medium** | Real data surprise, limited regional conflict, mid-tier listing or outage |
| **high** | FOMC surprise, sudden escalation, ETF flow shock, large unlock, top-venue listing, $10M+ exploit, chain halt |
| **extreme** | Emergency rate move, systemic war/sanctions shock, ETF approve/ban, exchange solvency, stablecoin depeg |

## Screenshots

| | |
|:--:|:--:|
| ![Timeline analysis bar](assets/timeline.png) | ![Manual mode](assets/manual-mode.png) |
| *Analysis bar after scoring (%, scope, direction, impact).* | *Manual mode: click the crystal to analyze a tweet.* |

<p align="center">
  <img src="assets/settings.png" alt="Extension popup settings" width="320">
</p>
<p align="center"><em>Popup: server connection, Manual/Auto mode, language, and server URL (<code>http://localhost:5678</code>).</em></p>

## How tweet extraction works

1. **`page_hook.js`** runs in the **MAIN** world (`manifest.json`) and hooks `fetch` / XHR for X GraphQL tweet ops.
2. It prefers `note_tweet` full text for long posts, expands t.co URLs, and includes one level of **quoted** tweet.
3. **`content.js`** merges GraphQL text with DOM fallback; quoted text is appended as `QT: ...` so timeline and detail pages feed the same input when GraphQL is available.
4. Caching: **background.js** caches by tweet `id` (else text); **server.py** also LRUs by `id:` / text hash.

## Rule layer

After the model runs, `apply_collision_rules` in `server.py` can cap relevance and force neutral/`none` scope:

- **`crypto_tickers.txt`** — editable cashtag whitelist. Non-whitelist `$TICKER` alone (no other crypto keywords) → `cashtag_collision:...`
- **“link in bio”** / similar lifestyle phrases without crypto keywords → `phrase_collision`
- On hit: `volatile` capped to `0.1`, `scope=none`, `direction=neutral`; flags appear in `rule_flags`

## URL preprocessing & scope gating

Before inference, `server.py` strips URLs from the tweet text (original text is kept for logging and the cache key). Default mode is **`remove`** (`URL_PREPROCESS=remove|domain|off`):

- **`remove`** (default) — delete `http(s)://…`, `www.…`, and bare domain/path links such as `pan.quark.cn/s/…`. Chosen because hex/hash path segments in URLs were mistaken for tx hashes and pushed relevance near 1.0.
- **`domain`** — replace each URL with `[link: example.com]` (keeps a weak domain hint).
- **`off`** — no stripping.

Bare `0x…` contract addresses and Solana-style addresses in **plain text** are **not** stripped (they are real crypto signals). Only hex that lives *inside* URLs is removed.

### Scope gating

When the model picks `scope=none`:

1. Cap relevance: `volatile = min(volatile, 1 - p(none))`.
2. If the tweet has **no** crypto keyword / whitelisted cashtag (or a collision rule fired), mark `gated=true` / `relevant=false`, neutralize direction for display, and further cap `volatile` at `LOW_RELEVANCE_GATE` (default `0.35`). The extension then shows only **%** and **Not related / 无关**.
3. If a crypto signal is present, only the relevance cap applies (`rule_flags` may include `scope_vol_cap`) so direction/impact stay visible.

**Limitation:** the small model still over-scores some non-crypto posts (e.g. “GM crypto fam”, names containing “Eth”, Spanish “sol”). URL stripping + gating fix the hex-in-URL false positives; keyword collisions remain imperfect.

## Extension settings

Popup (`popup.js` + `chrome.storage.local`):

| Setting | Values | Behavior |
|---------|--------|----------|
| **Mode** | manual / auto | Auto analyzes tweets entering the viewport (IntersectionObserver), **max 2 concurrent** (`MAX_IN_FLIGHT` in `content.js`) |
| **Language** | zh / en | Live switch; bar labels refresh without reload |
| **Server URL** | string | Default `http://localhost:5678` (localhost / 127.0.0.1 only in `host_permissions`) |

Both mode and language apply live via `storage.onChanged`. Pointing the popup at a non-local API host is not covered by the default manifest permissions.

## Concurrency (PyTorch MPS)

On Mac, **PyTorch MPS is not thread-safe**. Concurrent `predict` used to crash the process with **`Abort trap: 6`**. The default server serializes all inference with **`PREDICT_LOCK`**. Keep concurrency low on the client (extension auto mode already caps at 2).

## Customization

Tune behavior without rewriting the extension:

- **Prompts** — edit the `QUESTIONS` dict in `server.py` (relevance / scope / direction / impact wording and choices), then restart the server.
- **Thresholds & server** — copy `.env.example` → `.env` and adjust knobs the server actually reads, for example:

```bash
UNCERTAIN_THRESHOLD=0.60   # direction → uncertain below this max prob
LOW_RELEVANCE_GATE=0.35    # gated % cap when scope is none
URL_PREPROCESS=remove      # remove | domain | off
CACHE_SIZE=1000
SERVER_PORT=5678
# LAYA_DEVICE=mps          # optional: mps | cuda | cpu
```

- **Cashtag rules** — edit `crypto_tickers.txt` (whitelist used by `apply_collision_rules`).
- **Prompt experiments** — use `prompt_tests/` (`eval_server.py`, `prompt_variants.py`, `compare_questions.py`) to compare variants before changing `QUESTIONS`.

## Testing

See `prompt_tests/README.md` for details.

```bash
# API server (from project / repo root)
./start.sh

# Offline evals (from prompt_tests/)
cd prompt_tests
python3 eval_server.py

# Optional: re-run prompt variant harness
LAYA_MODEL_PATH=/path/to/multilingual python3 prompt_variants.py

# Optional: compare three QUESTIONS variants (writes compare_results.md / .json here)
python3 compare_questions.py
```

Use the same venv / model path as the server (`LAYA_MODEL_PATH` / `XCRYSTAL_ROOT` overrides as documented in `prompt_tests/README.md`).

## Known limitations

Treat results as a **reference signal**, not trading advice. The small Laya model misjudges some cases:

- **False-high relevance** — partially mitigated by URL stripping + scope gating (hex-in-URL cases now gate). Remaining hard cases: lifestyle posts that literally say “crypto”, person names like “Eth”, Spanish “sol”.
- **Direction** can be **confidently wrong** on some macro tweets (e.g. rate cuts labeled bearish with probability ≫ 0.60); raising `UNCERTAIN_THRESHOLD` only catches soft borderline cases.
- **Impact** tiers are mostly **high / extreme**: on the local model, `impact_score` clusters in a narrow band (~1.65–2.88) and barely separates expected low/medium/high/extreme.
- **Scope** often returns `none` or `sector` even for clear BTC/ETH headlines; gating caps % when `none` but keeps direction when crypto keywords are present.

The rule layer catches some cashtag / “link in bio” collisions but not all false positives.

## Usage (quick)

- **Manual**: click the crystal on a tweet bar.
- **Auto**: popup → Auto; visible tweets analyze as they enter the viewport.
- **Popup**: mode / language / server URL and connection status (no paste-to-analyze box).

## Debug

- Server log: `tail -f server.log`
- Page console (F12) and `chrome://extensions` → Inspect service worker / content scripts
- Reload the extension after JS/CSS changes

## Contributing

Contributions welcome — open a Pull Request.

## License

[MIT](LICENSE) © 2026 [@james_chenerge](https://x.com/james_chenerge)
