#!/usr/bin/env python3
"""Prompt variant experiments for laya QUESTIONS. Train=original 25, heldout=new 25."""
import json, os, sys, time, traceback
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from laya_config import get_model_path

MODEL_PATH = get_model_path()
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "variant_results")

# ---------------------------------------------------------------------------
# Variants (start from Grok original)
# ---------------------------------------------------------------------------
GROK = {
    "volatile": {
        "type": "noul",
        "instructions": "This post can move crypto prices, even if the headline is macro or geopolitics.",
        "criteria": {
            "true": "Tokens, chains, exchanges, DeFi, NFT, RWA, L2, stables, ETFs, unlocks, liquidations; OR macro/geopolitics that changes liquidity or risk appetite for crypto (rates, FOMC, DXY, liquidity, war, sanctions, oil shock, Iran/Israel/Taiwan, banking stress) when the link is crypto, BTC, ETH, ETF, risk assets, or safe-haven flows.",
            "false": "Pure politics, war, or rates with no market/risk-asset/crypto hook. Stock or brand ticker collision. Personal/lifestyle posts.",
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

# V1: simpler relevance question + keep rest of grok
V_SIMPLE_REL = {
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
    "scope": dict(GROK["scope"]),
    "direction": dict(GROK["direction"]),
    "impact": dict(GROK["impact"]),
}

# V2: direction criteria reordered — put common bullish crypto events first; explicit cut/listing
V_DIR_FIRST = {
    "volatile": dict(GROK["volatile"]),
    "scope": dict(GROK["scope"]),
    "direction": {
        "type": "choice",
        "instructions": (
            "Is this news good or bad for the crypto assets in scope? "
            "Judge the event itself (not a price chart). "
            "Rate cuts, listings, ETF inflows, product launches, and legal wins are bullish. "
            "Rate hikes, hacks, halts, depegs, unlock dumps, bans, and war escalations are bearish. "
            "Opinions, jokes, old news, and mixed hawkish+dovish posts are neutral."
        ),
        "criteria": {
            "bullish": "listing on major exchange; ETF inflow/approval; rate cut or dovish Fed; product live; partnership; peace/de-escalation; legal win; buyback; dollar down.",
            "bearish": "hack/exploit; chain halt; depeg; unlock dump; rate hike or hawkish Fed; war escalation; sanctions; banking stress; lawsuit; ban; delisting; dollar spike.",
            "neutral": "opinion, joke, recycled old news, mixed macro (hawkish and dovish together), or no new fact.",
        },
    },
    "impact": dict(GROK["impact"]),
}

# V3: short question-style instructions throughout
V_SHORT = {
    "volatile": {
        "type": "noul",
        "instructions": "Is this about crypto, crypto markets, or a macro/geopolitical shock to risk assets?",
        "criteria": {
            "true": "crypto/token/chain/exchange/ETF, or rates/war/sanctions that move markets.",
            "false": "stocks-only, lifestyle, fashion link-in-bio, pure politics.",
        },
    },
    "scope": {
        "type": "choice",
        "instructions": "What does this mainly affect?",
        "criteria": {
            "btc_eth_macro": "BTC, ETH, crypto ETFs, or broad macro/geopolitics that moves crypto.",
            "sector": "one chain, DeFi, L2, memes, RWA, stables as a group.",
            "single_asset": "one token, one protocol, or one exchange.",
            "none": "not about crypto markets.",
        },
    },
    "direction": {
        "type": "choice",
        "instructions": "Is the event good or bad for those assets?",
        "criteria": {
            "bullish": "cut, listing, ETF inflow/approve, launch, peace, legal win.",
            "bearish": "hike, hack, halt, depeg, unlock dump, war, ban, delist.",
            "neutral": "opinion, joke, old news, mixed, or no new fact.",
        },
    },
    "impact": {
        "type": "score",
        "instructions": "How large is the likely price move in hours to a few days?",
        "criteria": [
            "low: opinion, old news, in-line data",
            "medium: mid-tier listing, limited conflict, mild surprise",
            "high: FOMC surprise, big unlock, top listing, $10M+ hack, chain halt",
            "extreme: ETF approve/ban, stable depeg, exchange insolvency, systemic shock",
        ],
    },
}

# V4: Chinese instructions (model is multilingual)
V_ZH = {
    "volatile": {
        "type": "noul",
        "instructions": "这条内容是否涉及加密货币、加密公司/交易所，或会影响金融市场/风险资产的宏观与地缘事件？股票代码撞车、生活日常、纯政治请判否。",
        "criteria": {
            "true": "提到币/链/交易所/DeFi/ETF，或利率/战争/制裁等会扰动市场的事件。",
            "false": "仅股票或品牌、link in bio、生活日常、无市场含义的政治。",
        },
    },
    "scope": {
        "type": "choice",
        "instructions": "主要影响哪一层？",
        "criteria": {
            "btc_eth_macro": "BTC/ETH/加密ETF，或会重定价加密的宏观/地缘冲击。",
            "sector": "某条链、DeFi、L2、Meme、RWA、稳定币板块。",
            "single_asset": "单一代币、协议或交易所。",
            "none": "与加密市场无关。",
        },
    },
    "direction": {
        "type": "choice",
        "instructions": "对相关资产是利好还是利空？降息、上架、ETF流入、产品上线是利好；加息、黑客、停机、脱锚、解锁抛压、战争升级是利空；观点/旧闻/混杂为中性。",
        "criteria": {
            "bullish": "降息、上架、ETF流入/批准、上线、和解、胜诉。",
            "bearish": "加息、黑客、停机、脱锚、解锁抛压、战争、制裁、禁令。",
            "neutral": "观点、玩笑、旧闻、混杂宏观，或无新事实。",
        },
    },
    "impact": {
        "type": "score",
        "instructions": "数小时到数天内可能造成多大价格波动？",
        "criteria": [
            "low: 观点、旧闻、符合预期的数据",
            "medium: 中等上架、有限冲突、温和意外",
            "high: FOMC意外、大额解锁、头部上架、千万级黑客、链停机",
            "extreme: ETF批准/禁令、稳定币脱锚、交易所兑付危机、系统性冲击",
        ],
    },
}

# V5: combo — simple relevance + event-first direction + clearer scope + short impact
V_COMBO = {
    "volatile": {
        "type": "noul",
        "instructions": (
            "Does this post mention cryptocurrency, a crypto firm/exchange/protocol, a crypto ETF, "
            "or a macro/geopolitical event that affects financial markets or risk assets? "
            "False for stock-only tickers, fashion 'link in bio', lifestyle, and politics with no market hook."
        ),
        "criteria": {
            "true": "crypto/token/chain/exchange/DeFi/ETF mentioned, OR rates/FOMC/war/sanctions/oil that move markets or risk assets.",
            "false": "stock/brand ticker only; 'link in bio' / shopping; lifestyle; pure politics with no market link.",
        },
    },
    "scope": {
        "type": "choice",
        "instructions": (
            "Which layer of crypto does this hit? "
            "Use btc_eth_macro for BTC, ETH, crypto ETFs, Fed/rates, or geopolitics that moves risk assets. "
            "Use sector for one chain or a vertical (DeFi, L2, memes, RWA, stables). "
            "Use single_asset for one token, protocol, or exchange. "
            "Use none if there is no crypto market link."
        ),
        "criteria": {
            "btc_eth_macro": "BTC, ETH, crypto ETF, Fed/rates/FOMC/DXY, or geopolitics that reprices risk assets.",
            "sector": "one chain (e.g. Solana), DeFi, L2, memes, AI-crypto, RWA, or stablecoins as a class.",
            "single_asset": "one named token, one protocol, or one exchange.",
            "none": "no crypto market transmission.",
        },
    },
    "direction": {
        "type": "choice",
        "instructions": (
            "Is the event good or bad for those assets? Judge the event, not a price forecast. "
            "Bullish examples: rate cut, dovish Fed, exchange listing, ETF inflow/approval, product launch, peace. "
            "Bearish examples: rate hike, hawkish Fed, hack, chain halt, depeg, unlock dump, war escalation, ban. "
            "Neutral: opinion, joke, old news, mixed hawkish+dovish, or no new fact."
        ),
        "criteria": {
            "bullish": "rate cut / dovish; listing; ETF inflow or approval; product live; partnership; peace; legal win.",
            "bearish": "rate hike / hawkish; hack/exploit; halt; depeg; unlock dump; war escalation; sanctions; ban; delist.",
            "neutral": "opinion, joke, old news, mixed macro, or no new fact.",
        },
    },
    "impact": {
        "type": "score",
        "instructions": "How large a price move in hours to a few days for the assets in scope?",
        "criteria": [
            "low: opinion, recycled headline, in-line data",
            "medium: mild data surprise, limited conflict, mid-tier listing/outage",
            "high: FOMC surprise, sudden escalation, large unlock, top-venue listing, $10M+ exploit, chain halt",
            "extreme: ETF approve/ban, stablecoin depeg, exchange solvency crisis, systemic war/sanctions, emergency rate move",
        ],
    },
}

# V6: even clearer bullish/bearish with explicit "Fed cut = bullish" in instructions
V_EXPLICIT = {
    "volatile": dict(V_COMBO["volatile"]),
    "scope": dict(V_COMBO["scope"]),
    "direction": {
        "type": "choice",
        "instructions": (
            "Classify the event's sign for crypto. "
            "bullish if liquidity eases or demand rises: a Fed RATE CUT is bullish; an exchange LISTING is bullish; "
            "ETF inflows/approvals, product launches, and de-escalation are bullish. "
            "bearish if liquidity tightens or supply/risk rises: a Fed RATE HIKE is bearish; hacks, halts, depegs, "
            "token unlock dumps, bans, and war escalations are bearish. "
            "neutral for opinions, jokes, old news, or mixed hawkish+dovish in one post."
        ),
        "criteria": {
            "bullish": "Fed cut or dovish surprise; exchange listing; ETF inflow/approval; launch; peace; legal win.",
            "bearish": "Fed hike or hawkish surprise; hack; halt; depeg; unlock dump; war; ban; delist.",
            "neutral": "opinion, joke, old news, mixed, or no new fact.",
        },
    },
    "impact": dict(V_COMBO["impact"]),
}

VARIANTS = OrderedDict([
    ("grok", GROK),
    ("simple_rel", V_SIMPLE_REL),
    ("dir_first", V_DIR_FIRST),
    ("short", V_SHORT),
    ("zh", V_ZH),
    ("combo", V_COMBO),
    ("explicit", V_EXPLICIT),
])

# ---------------------------------------------------------------------------
# Tweet sets
# ---------------------------------------------------------------------------
# Original train set (from compare_questions.py) — expected: (rel, scope, dir, impact)
TRAIN = [
    ("fed_cut", "BREAKING: Fed cuts rates by 50bps in a surprise move. Powell signals more cuts are coming.", (True, "btc_eth_macro", "bullish", "high")),
    ("cpi_inline", "US CPI YoY comes in at 3.1%, exactly in line with expectations.", (True, "btc_eth_macro", "neutral", "low")),
    ("iran_israel", "Iran launches missiles at Israel. Oil jumps 8%, Bitcoin drops 5% within the hour.", (True, "btc_eth_macro", "bearish", "high")),
    ("senate_bill", "Senate passes the infrastructure bill 68-32 after weeks of debate.", (False, "none", "neutral", "low")),
    ("tsla_earnings", "$TSLA earnings beat, stock up 10% after hours on strong deliveries.", (False, "none", "neutral", "low")),
    ("sol_halt", "Solana mainnet has been halted for 5 hours. Validators are coordinating a restart.", (True, "sector", "bearish", "high")),
    ("exploit", "Lending protocol Nimbus exploited for $120M. Attacker is bridging funds to Ethereum right now.", (True, "single_asset", "bearish", "high")),
    ("binance_listing", "Binance will list $ABC. Spot trading opens today at 10:00 UTC.", (True, "single_asset", "bullish", "high")),
    ("usdc_depeg", "USDC depegs to $0.88 after Circle discloses $3.3B stuck at a failed bank.", (True, "sector", "bearish", "extreme")),
    ("eth_etf", "SEC approves spot Ethereum ETF applications from all major issuers.", (True, "btc_eth_macro", "bullish", "extreme")),
    ("gm", "GM crypto fam ☀️ coffee and charts, let's have a great day", (False, "none", "neutral", "low")),
    ("opinion", "I think BTC hits 200k by the end of the year. Not financial advice.", (True, "btc_eth_macro", "neutral", "low")),
    ("etf_inflow", "Spot Bitcoin ETFs saw $1.2B in net inflows yesterday, the largest day since launch.", (True, "btc_eth_macro", "bullish", "high")),
    ("unlock", "Reminder: 1.1B $ARB (~$1B) unlocks next week, about 87% of circulating supply.", (True, "single_asset", "bearish", "high")),
    ("tariff_truce", "US and China agree to a 90-day tariff truce. Nasdaq futures up 3%, risk assets rallying.", (True, "btc_eth_macro", "bullish", "medium")),
    ("fed_mixed", "Fed minutes: officials see rate cuts later this year but warn inflation remains sticky.", (True, "btc_eth_macro", "neutral", "low")),
    ("iphone", "Apple announces the iPhone 17 with a bigger battery and a new camera.", (False, "none", "neutral", "low")),
    ("zh_hike", "美联储意外加息50个基点，美元指数暴涨，比特币跌破6万美元。", (True, "btc_eth_macro", "bearish", "extreme")),
    ("zh_withdraw", "某头部交易所突然暂停提现，官方称系统维护，社区担心交易所资不抵债。", (True, "single_asset", "bearish", "extreme")),
    ("zh_lunch", "今天的午饭太好吃了，强烈推荐公司楼下这家拉面。", (False, "none", "neutral", "low")),
    ("uni_v4", "Uniswap v4 is now live on Ethereum mainnet, with hooks.", (True, "single_asset", "bullish", "medium")),
    ("throwback", "Throwback: remember when BTC hit 69k in November 2021?", (True, "btc_eth_macro", "neutral", "low")),
    ("ticker_link", "New summer collection just dropped 👗 $LINK in bio!", (False, "none", "neutral", "low")),
    ("mixer_sanction", "US Treasury sanctions a crypto mixer; several DeFi frontends start blocking US users.", (True, "sector", "bearish", "medium")),
    ("taiwan", "China announces live-fire drills encircling Taiwan. Asian stocks slide, gold spikes.", (True, "btc_eth_macro", "bearish", "high")),
]

# Held-out: DIFFERENT made-up tweets (mix EN/ZH, collisions, macro, etc.)
HELDOUT = [
    ("ecb_cut", "ECB cuts deposit rate by 25bps; euro softens, risk assets bid in European hours.", (True, "btc_eth_macro", "bullish", "medium")),
    ("nfp_hot", "US payrolls smash expectations at +350k. Bond yields spike; traders price out two cuts.", (True, "btc_eth_macro", "bearish", "high")),
    ("korea_ban_rumor", "South Korea lawmakers float a blanket ban on domestic crypto trading apps.", (True, "sector", "bearish", "high")),
    ("coinbase_outage", "Coinbase spot matching engine offline for 40 minutes during a volatility spike.", (True, "single_asset", "bearish", "medium")),
    ("okx_list_pepe", "OKX will list PEPE perpetual futures with up to 50x leverage at 08:00 UTC.", (True, "single_asset", "bullish", "medium")),
    ("dai_softpeg", "DAI drifts to $0.97 after a large Maker vault liquidation cascade.", (True, "sector", "bearish", "high")),
    ("btc_etf_outflow", "Spot Bitcoin ETFs post $480M net outflows, third consecutive red day.", (True, "btc_eth_macro", "bearish", "high")),
    ("apt_unlock", "Aptos foundation unlocks 11M $APT tomorrow (~$80M at spot).", (True, "single_asset", "bearish", "medium")),
    ("bridge_hack", "Wormhole-style bridge on ChainX drained for $45M overnight; explorers confirm.", (True, "single_asset", "bearish", "high")),
    ("base_tvl", "Base chain TVL crosses $10B for the first time as Superchain activity heats up.", (True, "sector", "bullish", "medium")),
    ("aapl_split", "$AAPL announces 4-for-1 stock split after record iPhone sales quarter.", (False, "none", "neutral", "low")),
    ("nike_dunk", "Just dropped: limited Nike Dunks — use code SOL at checkout 🔥", (False, "none", "neutral", "low")),
    ("link_in_bio2", "My new coaching program is live — full details, link in bio ✨", (False, "none", "neutral", "low")),
    ("eth_as_name", "Congrats to Eth Thompson on the new VP role at the bank!", (False, "none", "neutral", "low")),
    ("sol_spanish", "El sol está fuerte hoy en Barcelona, perfect day for the beach ☀️", (False, "none", "neutral", "low")),
    ("zh_etf", "香港比特币现货ETF今日净流入破纪录，机构买盘强劲。", (True, "btc_eth_macro", "bullish", "high")),
    ("zh_hack", "某DeFi借贷协议遭闪电贷攻击，损失约8000万美元，代币暴跌40%。", (True, "single_asset", "bearish", "high")),
    ("zh_weather", "周末上海多云转晴，适合出去走走。", (False, "none", "neutral", "low")),
    ("oil_shock2", "Hormuz shipping disrupted; Brent crude +12%. Equity futures red, gold bid.", (True, "btc_eth_macro", "bearish", "high")),
    ("dovish_powell", "Powell: 'progress on inflation opens the door to easing later this year.'", (True, "btc_eth_macro", "bullish", "medium")),
    ("old_ftx", "Remember FTX collapsing in 2022? Wild times. Anyway, happy Friday.", (True, "btc_eth_macro", "neutral", "low")),
    ("meme_opinion", "Honestly $DOGE is going to the moon, trust me bro.", (True, "single_asset", "neutral", "low")),
    ("sec_ripple", "Court rules in favor of Ripple on secondary XRP sales; $XRP spikes 20%.", (True, "single_asset", "bullish", "high")),
    ("stable_yield", "BlackRock's BUIDL tokenized fund hits $1B AUM on Ethereum.", (True, "sector", "bullish", "medium")),
    ("nvda_ai", "$NVDA guidance raised on AI chip demand; semis rip after hours.", (False, "none", "neutral", "low")),
]

SETS = OrderedDict([("train", TRAIN), ("heldout", HELDOUT)])


def parse(ans, key):
    a = ans.get(key)
    if a is None:
        return None
    if "noul" in a:
        return {"value": a["noul"], "answer_confidence": a.get("answer_confidence")}
    if "choice" in a:
        return {"value": a["choice"], "probs": a.get("probabilities"),
                "answer_confidence": a.get("answer_confidence")}
    if "score" in a:
        score = a["score"]
        legend = a.get("legend") or {}
        label = legend.get(str(round(score)), str(round(score, 2)))
        short = str(label).split(":")[0].strip()
        return {"value": short, "raw_label": label, "score": score,
                "probs": a.get("probabilities"), "answer_confidence": a.get("answer_confidence")}
    return {"value": a}


def score_variant(rows, vname):
    n = rel_ok = sc_ok = sc_n = dir_ok = imp_ok = errs = 0
    ms = []
    n_rel = 0
    for r in rows:
        v = r["variants"][vname]
        if not v.get("ok"):
            errs += 1
            continue
        n += 1
        ms.append(v["ms"])
        e = r["expected"]
        rel = v["volatile"]["value"] if v.get("volatile") else None
        if isinstance(rel, (int, float)) and (rel >= 0.5) == e[0]:
            rel_ok += 1
        elif isinstance(rel, bool) and rel == e[0]:
            rel_ok += 1
        if v.get("scope"):
            sc_n += 1
            sc_ok += v["scope"]["value"] == e[1]
        if e[0]:
            n_rel += 1
            dir_ok += (v.get("direction") or {}).get("value") == e[2]
            imp_ok += (v.get("impact") or {}).get("value") == e[3]
    avg_ms = round(sum(ms) / len(ms)) if ms else None
    # Combined favoring direction + relevance: 0.4*rel + 0.4*dir + 0.1*scope + 0.1*impact
    rel_p = rel_ok / n if n else 0
    dir_p = dir_ok / n_rel if n_rel else 0
    sc_p = sc_ok / sc_n if sc_n else 0
    imp_p = imp_ok / n_rel if n_rel else 0
    combined = 0.4 * rel_p + 0.4 * dir_p + 0.1 * sc_p + 0.1 * imp_p
    return {
        "rel": f"{rel_ok}/{n}", "scope": f"{sc_ok}/{sc_n}" if sc_n else "-",
        "dir": f"{dir_ok}/{n_rel}", "imp": f"{imp_ok}/{n_rel}",
        "ms": avg_ms, "errs": errs, "combined": round(combined, 4),
        "rel_p": rel_p, "dir_p": dir_p, "sc_p": sc_p, "imp_p": imp_p,
    }


def run():
    os.makedirs(OUT, exist_ok=True)
    from laya import load
    print("Loading", MODEL_PATH)
    agent = load(MODEL_PATH, device="cpu")
    print("Loaded.\n")

    all_summaries = {}
    for set_name, tweets in SETS.items():
        print(f"===== SET {set_name} ({len(tweets)}) =====")
        results = []
        for tid, text, exp in tweets:
            row = {"id": tid, "text": text, "expected": list(exp), "variants": {}}
            for vname, qs in VARIANTS.items():
                t0 = time.time()
                try:
                    out = agent.predict(text, qs)
                    ans = out["answers"]
                    row["variants"][vname] = {
                        "ok": True,
                        "ms": round((time.time() - t0) * 1000),
                        **{k: parse(ans, k) for k in ("volatile", "scope", "direction", "impact")},
                    }
                except Exception as e:
                    row["variants"][vname] = {
                        "ok": False, "error": f"{type(e).__name__}: {e}",
                        "trace": traceback.format_exc(limit=2),
                    }
            results.append(row)
            print(f"  done {tid}")

        path = os.path.join(OUT, f"{set_name}_results.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)

        summary = {vn: score_variant(results, vn) for vn in VARIANTS}
        all_summaries[set_name] = summary

    # Combined across sets (equal weight train+heldout combined scores)
    print("\n===== SUMMARY =====")
    lines = ["# Prompt variant comparison", "",
             "Scoring: combined = 0.4*rel + 0.4*dir + 0.1*scope + 0.1*impact", ""]
    for set_name, summary in all_summaries.items():
        lines += [f"## {set_name}", "",
                  "| variant | rel | scope | dir | impact | avg_ms | errs | combined |",
                  "|---|---|---|---|---|---|---|---|"]
        for vn, s in summary.items():
            lines.append(
                f"| {vn} | {s['rel']} | {s['scope']} | {s['dir']} | {s['imp']} | {s['ms']} | {s['errs']} | {s['combined']} |"
            )
            print(f"{set_name}/{vn}: rel={s['rel']} dir={s['dir']} scope={s['scope']} imp={s['imp']} "
                  f"ms={s['ms']} combined={s['combined']}")
        lines.append("")

    # Pick best by mean combined across sets
    means = {}
    for vn in VARIANTS:
        means[vn] = round(
            (all_summaries["train"][vn]["combined"] + all_summaries["heldout"][vn]["combined"]) / 2, 4
        )
    best = max(means, key=means.get)
    lines += ["## Mean combined (train+heldout)/2", "",
              "| variant | mean_combined |", "|---|---|"]
    for vn, m in sorted(means.items(), key=lambda x: -x[1]):
        mark = " ← BEST" if vn == best else ""
        lines.append(f"| {vn} | {m}{mark} |")
        print(f"mean {vn}: {m}{' ← BEST' if vn == best else ''}")

    # Save chosen QUESTIONS
    chosen = VARIANTS[best]
    with open(os.path.join(OUT, "chosen_questions.json"), "w", encoding="utf-8") as f:
        json.dump({"variant": best, "questions": chosen, "means": means}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    # also dump tweet sets for Mac copy
    with open(os.path.join(HERE, "train_tweets.json"), "w", encoding="utf-8") as f:
        json.dump([{"id": a, "text": b, "expected": list(c)} for a, b, c in TRAIN], f, ensure_ascii=False, indent=2)
    with open(os.path.join(HERE, "heldout_tweets.json"), "w", encoding="utf-8") as f:
        json.dump([{"id": a, "text": b, "expected": list(c)} for a, b, c in HELDOUT], f, ensure_ascii=False, indent=2)
    print("\nBEST:", best)
    print("Wrote", OUT)


if __name__ == "__main__":
    run()
